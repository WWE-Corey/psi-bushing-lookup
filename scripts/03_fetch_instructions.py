"""
Step 3 of the pipeline: download each unique instruction PDF referenced in
data/scraped_raw.json and parse tube/barrel length out of its parts-layout
diagram.

Tube length isn't published anywhere in the HTML -- it only appears as a
dimension callout in each kit's PDF instruction sheet (e.g. "Tube / Barrel
1-31/32""), and neither the label wording nor the value format is
consistent across kit families:

    Bolt Action (PKCP80XX):  "Tube / Barrel"            1-31/32"
    Anvil EDC (PKANVxx):     "Tube"                      2.647" (2-21/32")
    Big Ben Cigar (PKBIG):   "Upper Tube" / "Lower Tube" 1-15/16" / 2-1/16"
    Dog Click (PKDOGXX):     "Tube / Barrel"             3.310"
                              (value printed BEFORE the label in the PDF's
                              raw content-stream order)
    Classic Twist (PKPARK):  bare "Tube" x2 (upper+lower, undistinguished)

Because label/value order and even the presence of a distinguishing prefix
varies, this doesn't do sequential text parsing. Instead it uses
pdfplumber's per-word coordinates: find every word that is a "Tube" label
(optionally prefixed Upper/Lower/etc and suffixed "/ Barrel"), find every
word that looks like a standalone dimension, and pair each label with its
nearest dimension word by on-page distance -- capped at MAX_PAIR_DIST so a
label with nothing nearby is left unmatched rather than paired with
something wrong (e.g. "Overall Length" or "Blank Size" elsewhere on the
page). This is a heuristic against inconsistent, unstructured diagrams --
it will not resolve every kit. Kits it can't resolve get tubes: [] here and
can be checked by hand against their instruction PDF if needed.

Runs 8 downloads concurrently; a few hundred unique PDFs takes a few minutes.
"""
import re
import json
import time
import urllib.request
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "scraped_raw.json"
OUT_PATH = ROOT / "data" / "instructions_raw.json"

BASE_URL = "https://www.pennstateind.com"
MAX_PAIR_DIST = 75  # points; label<->dimension pairs farther apart than this are dropped
MIN_TUBE_INCHES = 0.5
MAX_TUBE_INCHES = 10
MODIFIERS = {"upper", "lower", "front", "back", "top", "bottom"}

QUOTE = '["”]'  # PSI's PDFs use the Unicode right double quote (”), not ASCII "
DIM_RE = re.compile(r'^(\d+-\d+/\d+|\d+/\d+|\d+\.\d+|\d+)' + QUOTE + r'$')

WHOLE_DASH_RE = re.compile(r'^(\d+)-$')
BARE_FRACTION_RE = re.compile(r'^\d+/\d+' + QUOTE + r'$')


def merge_split_mixed_numbers(words):
    """Some sheets render a mixed number like "1-31/32"" with a stray space
    after the dash, so pdfplumber tokenizes it as two words: "1-" and
    "31/32"". Left alone, only the fraction half gets parsed as the
    dimension, silently dropping the leading whole number (e.g. reporting
    0.97" instead of the real 1.97"). Merge that pattern back into one token
    before anything else runs.
    """
    merged = []
    i = 0
    while i < len(words):
        w = words[i]
        m = WHOLE_DASH_RE.match(w["text"])
        if m and i + 1 < len(words):
            nxt = words[i + 1]
            if BARE_FRACTION_RE.match(nxt["text"]) and abs(nxt["top"] - w["top"]) < 4 \
               and (nxt["x0"] - w["x1"]) < 20:
                merged.append({
                    "text": f'{m.group(1)}-{nxt["text"]}',
                    "x0": w["x0"], "x1": nxt["x1"],
                    "top": min(w["top"], nxt["top"]), "bottom": max(w["bottom"], nxt["bottom"]),
                })
                i += 2
                continue
        merged.append(w)
        i += 1
    return merged


def parse_inches(raw):
    s = raw.rstrip('"”')
    m = re.fullmatch(r'(\d+)-(\d+)/(\d+)', s)
    if m:
        whole, num, den = (int(x) for x in m.groups())
        return round(whole + num / den, 4)
    m = re.fullmatch(r'(\d+)/(\d+)', s)
    if m:
        num, den = (int(x) for x in m.groups())
        return round(num / den, 4)
    return round(float(s), 4)


def find_tube_labels(words):
    labels = []
    for i, w in enumerate(words):
        stripped = w["text"].strip(":,/")
        lower = stripped.lower()
        if lower not in ("tube", "tube/barrel"):
            continue

        prev = words[i - 1] if i > 0 else None
        prev_text = prev["text"].strip(":,") if prev else ""
        prev_is_modifier = bool(prev) and prev_text.lower() in MODIFIERS and prev_text[:1].isupper() \
            and abs(prev["top"] - w["top"]) < 4 and (w["x0"] - prev["x1"]) < 15

        # Case-sensitive by default: diagram labels are Title Case ("Tube"),
        # while body prose uses lowercase ("...clean the inside of the tube").
        # Exception: a capitalized Upper/Lower/etc modifier immediately
        # before it is distinctive enough that prose won't produce it by
        # accident, so that combination is allowed even if "tube" itself
        # is lowercase (some sheets print "Upper tube/barrel").
        if stripped[:1].islower() and not prev_is_modifier:
            continue

        # Skip descriptive captions like "Upper Barrel with Tube" -- these
        # reference a tube but aren't themselves a dimensioned label, and
        # pairing them with the nearest number is how false positives creep in.
        if prev_text.lower() == "with":
            continue

        x0, x1, top, bottom = w["x0"], w["x1"], w["top"], w["bottom"]
        prefix = f"{prev_text.capitalize()} " if prev_is_modifier else ""
        if prev_is_modifier:
            x0 = prev["x0"]

        combined = lower == "tube/barrel"
        suffix = " / Barrel" if combined else ""
        if not combined and i + 2 < len(words):
            nxt, nxt2 = words[i + 1], words[i + 2]
            if nxt["text"].strip() == "/" and nxt2["text"].strip(":,").lower() == "barrel" \
               and abs(nxt2["top"] - top) < 4 and (nxt2["x1"] - x1) < 60:
                suffix = " / Barrel"
                x1 = nxt2["x1"]

        labels.append({"label": f"{prefix}Tube{suffix}",
                        "cx": (x0 + x1) / 2, "cy": (top + bottom) / 2})
    return labels


def find_dimensions(words):
    dims = []
    for w in words:
        core = w["text"].strip().strip("()")  # unwrap parenthetical alt-forms, e.g. (2-21/32")
        if DIM_RE.match(core):
            dims.append({"raw": core, "cx": (w["x0"] + w["x1"]) / 2, "cy": (w["top"] + w["bottom"]) / 2})
    return dims


def diagram_region(words):
    """Vertical (top, bottom) band of the parts-layout diagram, bounded by
    the first "DIAGRAM" heading and whatever comes next. Most sheets title
    this section "DIAGRAM A" in some form, and where present it's the most
    reliable landmark -- restricting to this band keeps Kit-Features bullets
    (which incidentally title-case words like "Tube") and duplicated diagram
    content further down the page out of consideration. A few sheets have no
    such heading at all (the diagram is unlabeled); callers fall back to the
    whole page in that case.
    """
    tops = [w["top"] for w in words if w["text"].strip(":-/•") == "DIAGRAM"]
    if not tops:
        return None
    start = min(tops)
    ends = [t for t in tops if t > start + 5]
    end = min(ends) if ends else start + 400
    return start, end


def extract_tubes(pdf_bytes):
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:2]:
            all_words = merge_split_mixed_numbers(page.extract_words(x_tolerance=1.5, y_tolerance=3))
            region = diagram_region(all_words)
            if region is not None:
                top, bottom = region
                words = [w for w in all_words if top <= w["top"] <= bottom]
            else:
                words = all_words

            labels = find_tube_labels(words)
            if not labels:
                continue
            dims = find_dimensions(words)
            if not dims:
                continue

            found = []
            for lab in labels:
                best, best_dist = None, None
                for d in dims:
                    dist = ((lab["cx"] - d["cx"]) ** 2 + (lab["cy"] - d["cy"]) ** 2) ** 0.5
                    if best_dist is None or dist < best_dist:
                        best, best_dist = d, dist
                if best is not None and best_dist <= MAX_PAIR_DIST:
                    try:
                        inches = parse_inches(best["raw"])
                    except ValueError:
                        inches = None
                    # Sanity range for a pen/pencil tube segment. Values outside
                    # it are usually a mis-split token (e.g. a stray space
                    # breaking "1-11/32"" into "1-" and "11/32"", so only the
                    # tail gets parsed) rather than a real short/long tube --
                    # better to drop it than report a wrong number.
                    if inches is not None and MIN_TUBE_INCHES <= inches <= MAX_TUBE_INCHES:
                        found.append({"label": lab["label"], "raw": best["raw"], "inches": inches})

            if found:
                seen, unique = set(), []
                for f in found:
                    # Round to 0.01" so e.g. "2.03"" and "2-1/32"" (the same
                    # length in two notations) collapse into one entry.
                    key = (f["label"], round(f["inches"], 2) if f["inches"] is not None else f["raw"])
                    if key not in seen:
                        seen.add(key)
                        unique.append(f)
                return unique

    return []


def fetch_and_extract(pdf_path):
    url = BASE_URL + pdf_path
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            pdf_bytes = resp.read()
    except Exception as e:
        return {"path": pdf_path, "error": str(e)}

    try:
        tubes = extract_tubes(pdf_bytes)
    except Exception as e:
        return {"path": pdf_path, "error": f"parse failed: {e}"}

    return {"path": pdf_path, "tubes": tubes}


def main():
    raw = json.loads(RAW_PATH.read_text())
    scraped_at = raw.get("scraped_at")

    # De-dupe by lowercased path: the same PDF is sometimes linked with
    # different casing, and always shared across a kit's finish variants.
    unique_paths = {}
    for r in raw["results"]:
        p = r.get("instructions_pdf")
        if p:
            unique_paths.setdefault(p.lower(), p)
    paths = sorted(unique_paths.values())
    print(f"{len(paths)} unique instruction PDFs to fetch")

    results, errors = {}, []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_and_extract, p): p for p in paths}
        done = 0
        for fut in as_completed(futures):
            r = fut.result()
            done += 1
            if "error" in r:
                errors.append(r)
            else:
                results[r["path"].lower()] = r
            if done % 50 == 0:
                print(f"  {done}/{len(paths)} done ({time.time()-t0:.0f}s)")

    print(f"done in {time.time()-t0:.0f}s. ok={len(results)} errors={len(errors)}")

    resolved = sum(1 for r in results.values() if r["tubes"])
    print(f"tube length resolved: {resolved}/{len(results)}")

    OUT_PATH.write_text(json.dumps({"scraped_at": scraped_at, "results": results, "errors": errors}))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
