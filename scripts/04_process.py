"""
Step 4 of the pipeline: turn the raw per-SKU scrape (plus the parsed
instruction-PDF data from step 3) into two views:

  - flat_skus: every real individual kit SKU (bundles/starter-sets and one
    mislabeled bushing-product excluded), no grouping at all. This is the
    guaranteed-accurate view.
  - designs: the flat SKUs grouped into "kit designs" by stripping known
    finish/plating words (Chrome, Gun Metal, Antique Brass, 24kt Gold, ...)
    out of the title -- wherever they appear, not just as a suffix -- and
    grouping what's left by (normalized name, bushing set). This is a
    best-effort heuristic against inconsistent title formatting; when in
    doubt, trust flat_skus instead.

Each SKU/design also gets drill_sizes (from the HTML, reliable) and tubes
(from the instruction-PDF parse, best-effort -- see 03_fetch_instructions.py
for why this doesn't cover every kit). Where the automated parse found
nothing, data/tube_overrides.json fills the gap for kits someone has since
looked up by hand in the instruction PDF -- see that file's "_readme" entry.
data/kit_overrides.json fills per-SKU bushing/drill/tube gaps where PSI's own
product page omits a field a sibling color variant (or the instruction PDF's
accessories list) confirms -- also only ever fills a genuine gap, never
overrides a real scraped/parsed value.

Writes data/final_data.json (human-readable), data/compact_data.json (the
compact form the HTML page embeds), and the two CSVs under output/.
"""
import json
import re
import csv
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "scraped_raw.json"
INSTRUCTIONS_PATH = ROOT / "data" / "instructions_raw.json"
TUBE_OVERRIDES_PATH = ROOT / "data" / "tube_overrides.json"
KIT_OVERRIDES_PATH = ROOT / "data" / "kit_overrides.json"
FINAL_PATH = ROOT / "data" / "final_data.json"
COMPACT_PATH = ROOT / "data" / "compact_data.json"
OUTPUT_DIR = ROOT / "docs"

DRILL_BIT_SUFFIX_RE = re.compile(r"\s*Drill Bit\s*$", re.I)

# PSI's drill-bit link text mixes the actual size with marketing/qualifier
# words in no fixed position or order -- "Brad 7mm Point", "Premium 3/8in
# Acrylic", "Standard 7mm Drill Big" (typo, sic) -- so rather than trying to
# strip known qualifier words (an ever-growing list, same trap as the finish
# words above), this just pulls the size pattern out of the string wherever
# it appears and discards everything else.
DRILL_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mm|(\d+/\d+)\s*in", re.I)

# A handful of drill-bit SKUs (PSI's "Acrylic Drill Bit" line) never state a
# size in their link text on ANY page in the dataset, e.g. plain "Premium
# Acrylic Drill Bit". Those SKU ids encode the size themselves following
# PSI's own convention seen elsewhere (PK105MM == 10.5mm), so that's the
# last-resort fallback once no page's label text has the size either.
ACRYLIC_DRILL_ID_RE = re.compile(r"^PKADB(\d+)MM$", re.I)


def extract_drill_size(label):
    m = DRILL_SIZE_RE.search(label)
    if not m:
        return None
    return f"{m.group(1)}mm" if m.group(1) else f"{m.group(2)}in"


def drill_size_from_id(drill_id):
    m = ACRYLIC_DRILL_ID_RE.match(drill_id or "")
    if not m:
        return None
    digits = m.group(1)
    value = f"{digits[:-1]}.{digits[-1]}" if len(digits) >= 3 else digits
    return f"{value}mm"

BUNDLE_RE = re.compile(r"Starter Set|Variety (Set|Pack)|Combo Pack|Bundle|Bulk Pack", re.I)

# Products that show up in the pen-kits category but are actually bushing
# sets themselves, not distinct kit designs -- excluded from every view.
MISLABELED_BUSHING_IDS = {"PKOLIVEBU"}

# Finish/plating vocabulary, longest phrases first so e.g. "Satin Gun Metal"
# matches before "Gun Metal" before "Chrome" alone. Built from a word-frequency
# pass over ~580 real kit titles plus PSI's own common plating terminology.
FINISH_PHRASES = [
    "6061-T6 Black Anodized Aluminum", "6061-T6 Aluminum", "6061 T6 Aluminum",
    "303 Stainless Steel", "C3604 Brass",
    "Satin Gun Metal", "Satin Chrome", "Satin Nickel", "Satin Gold", "Satin Black",
    "Black Anodized Aluminum", "Black Chrome", "Black Titanium", "Black Enamel", "Matte Black",
    "Antique Brass", "Antique Pewter", "Antique Copper", "Antique Nickel", "Antique Bronze",
    "Brushed Nickel", "Brushed Chrome", "Brushed Gold",
    "Rose Gold", "24kt Gold", "22kt Gold", "14kt Gold",
    "Gun Metal", "Gunmetal",
    "Stainless Steel",
    "Chrome", "Golden", "Gold", "Brass", "Pewter", "Copper", "Nickel",
    "Titanium", "Rhodium", "Platinum", "Bronze", "Aluminum", "Steel", "Black",
]
FINISH_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in FINISH_PHRASES) + r")\b", re.I)


def clean_design_name(title):
    t = FINISH_RE.sub("", title)
    t = re.sub(r"\bin\b", "", t, flags=re.I)
    t = re.sub(r"\bwith\b\s*$", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" -,")
    return t


def clean_drill_label(label):
    return DRILL_BIT_SUFFIX_RE.sub("", label).strip()


def dedupe_tubes(tube_lists):
    seen, unique = set(), []
    for tubes in tube_lists:
        for t in tubes:
            key = (t["label"], round(t["inches"], 2) if t["inches"] is not None else t["raw"])
            if key not in seen:
                seen.add(key)
                unique.append(t)
    return unique


def main():
    raw_data = json.loads(RAW_PATH.read_text())
    raw = raw_data["results"]
    scraped_at = raw_data.get("scraped_at")

    instructions = json.loads(INSTRUCTIONS_PATH.read_text())["results"] if INSTRUCTIONS_PATH.exists() else {}
    tube_overrides = {k: v for k, v in json.loads(TUBE_OVERRIDES_PATH.read_text()).items()
                       if not k.startswith("_")} if TUBE_OVERRIDES_PATH.exists() else {}

    # Same-SKU cross-reference: a drill bit whose OWN label omits the size
    # (e.g. plain "Premium Acrylic Drill Bit") can borrow it from another
    # page that links the same drill-bit SKU with a fuller label.
    id_to_size = {}
    for r in raw:
        for d in r.get("drills", []):
            size = extract_drill_size(d["label"])
            if size:
                id_to_size.setdefault(d["id"], size)

    def resolve_drill_size(d):
        return (extract_drill_size(d["label"]) or id_to_size.get(d["id"])
                or drill_size_from_id(d["id"]) or clean_drill_label(d["label"]))

    for r in raw:
        r["drill_sizes"] = sorted({resolve_drill_size(d) for d in r.get("drills", [])})
        pdf_path = r.get("instructions_pdf")
        key = pdf_path.lower() if pdf_path else None
        tubes = instructions.get(key, {}).get("tubes", []) if key else []
        # Overrides only fill a genuine gap -- they never replace a real
        # (even if imperfect) automated result.
        r["tubes"] = tubes or tube_overrides.get(key, [])

    kit_overrides = {k: v for k, v in json.loads(KIT_OVERRIDES_PATH.read_text()).items()
                      if not k.startswith("_")} if KIT_OVERRIDES_PATH.exists() else {}
    for r in raw:
        o = kit_overrides.get(r["kit_id"])
        if not o:
            continue
        # Union rather than replace-if-empty: a kit can have a *partial* gap
        # (e.g. a two-tube kit where only the Lower Tube got auto-extracted),
        # so an override needs to be able to add just the missing piece
        # without disturbing whatever was already found.
        if o.get("bushings"):
            r["bushings"] = sorted(set(r["bushings"]) | set(o["bushings"]))
        if o.get("drills"):
            r["drill_sizes"] = sorted(set(r["drill_sizes"]) | set(o["drills"]))
        if o.get("tubes"):
            existing_labels = {t["label"] for t in r["tubes"]}
            r["tubes"] = r["tubes"] + [t for t in o["tubes"] if t["label"] not in existing_labels]
        if o.get("tubes_replace"):
            # Unlike "tubes" (add whatever's missing), this replaces the
            # whole list -- for when the automated parse found the right
            # *values* but mislabeled them (e.g. two same-length tubes both
            # tagged generic "Tube / Barrel" instead of Upper/Lower).
            r["tubes"] = o["tubes_replace"]

    kept, excluded_bundle, excluded_mislabeled = [], [], []
    for r in raw:
        if r["kit_id"] in MISLABELED_BUSHING_IDS:
            excluded_mislabeled.append(r)
        elif BUNDLE_RE.search(r["title"]):
            excluded_bundle.append(r)
        else:
            kept.append(r)

    print(f"kept: {len(kept)}  excluded_bundle: {len(excluded_bundle)}  "
          f"excluded_mislabeled: {len(excluded_mislabeled)}")

    groups = defaultdict(list)
    for r in kept:
        bushing_key = tuple(sorted(r["bushings"])) if r["bushings"] else ("__NONE__",)
        key = (clean_design_name(r["title"]).lower(), bushing_key)
        groups[key].append(r)

    design_rows = []
    for (_, bushing_key), members in groups.items():
        rep_title = min((m["title"] for m in members), key=len)
        design_rows.append({
            "design": clean_design_name(rep_title),
            "bushing_ids": [b for b in bushing_key if b != "__NONE__"],
            "sku_count": len(members),
            "skus": sorted(m["kit_id"] for m in members),
            "category": members[0]["category"],
            "drill_sizes": sorted({d for m in members for d in m["drill_sizes"]}),
            "tubes": dedupe_tubes(m["tubes"] for m in members),
        })
    design_rows.sort(key=lambda r: r["design"].lower())

    print(f"design-level rows: {len(design_rows)}")

    FINAL_PATH.write_text(json.dumps({
        "scraped_at": scraped_at,
        "flat_skus": kept,
        "designs": design_rows,
        "excluded_bundle_count": len(excluded_bundle),
        "excluded_bundle": [{"kit_id": r["kit_id"], "title": r["title"]} for r in excluded_bundle],
    }, indent=2))
    print(f"wrote {FINAL_PATH}")

    def tubes_c(tubes):
        return [{"l": t["label"], "v": t["raw"], "i": t["inches"]} for t in tubes]

    # Compact form for embedding in the HTML page, plus the bushing -> designs
    # reverse index used by the "By Bushing Set" view.
    designs_c = [{"d": r["design"], "b": r["bushing_ids"], "n": r["sku_count"],
                  "s": r["skus"], "c": r["category"],
                  "dr": r["drill_sizes"], "tu": tubes_c(r["tubes"])} for r in design_rows]
    flat_c = [{"k": r["kit_id"], "t": r["title"], "b": r["bushings"], "c": r["category"],
               "dr": r["drill_sizes"], "tu": tubes_c(r["tubes"])}
              for r in kept]

    rev = defaultdict(list)
    for r in designs_c:
        for b in r["b"]:
            rev[b].append({"d": r["d"], "s": r["s"]})
    reverse_c = [{"b": b, "designs": sorted(ds, key=lambda d: d["d"].lower())}
                 for b, ds in sorted(rev.items())]

    # drill size -> designs, for the "By Drill Size" batching view.
    rev_drill = defaultdict(list)
    for r in designs_c:
        for d in r["dr"]:
            rev_drill[d].append({"d": r["d"], "s": r["s"]})
    reverse_drill_c = [{"drill": d, "designs": sorted(ds, key=lambda x: x["d"].lower())}
                        for d, ds in sorted(rev_drill.items())]

    # tube length -> designs, for the "By Tube Length" batching view. Grouped
    # by rounded inches (not the raw string) so e.g. "1-31/32"" and a
    # differently-notated equivalent from another sheet land in one row.
    rev_tube = defaultdict(list)
    tube_display = {}
    for r in designs_c:
        for t in r["tu"]:
            if t["i"] is None:
                continue
            key = round(t["i"], 3)
            tube_display.setdefault(key, t["v"])
            rev_tube[key].append({"d": r["d"], "s": r["s"], "l": t["l"]})
    reverse_tube_c = [{"i": k, "v": tube_display[k], "designs": sorted(ds, key=lambda x: x["d"].lower())}
                       for k, ds in sorted(rev_tube.items())]

    COMPACT_PATH.write_text(json.dumps({
        "scraped_at": scraped_at,
        "designs": designs_c, "flat": flat_c, "reverse": reverse_c,
        "reverse_drill": reverse_drill_c, "reverse_tube": reverse_tube_c,
        "excluded_bundle_count": len(excluded_bundle),
        "excluded_bundle": [{"kit_id": r["kit_id"], "title": r["title"]} for r in excluded_bundle],
    }, separators=(",", ":")))
    print(f"wrote {COMPACT_PATH}")

    def tubes_csv(tubes):
        return ";".join(f'{t["label"]} {t["raw"]}' for t in tubes) or "NOT FOUND"

    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_DIR / "pen_kit_bushing_by_design.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Design", "Bushing IDs", "SKU Count", "SKUs", "Category", "Drill Size(s)", "Tube Length(s)"])
        for r in design_rows:
            w.writerow([r["design"], ";".join(r["bushing_ids"]) or "NOT LISTED",
                        r["sku_count"], ";".join(r["skus"]), r["category"],
                        ";".join(r["drill_sizes"]) or "NOT LISTED", tubes_csv(r["tubes"])])

    with open(OUTPUT_DIR / "pen_kit_bushing_flat.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Kit ID", "Title", "Bushing IDs", "Category", "Drill Size(s)", "Tube Length(s)"])
        for r in kept:
            w.writerow([r["kit_id"], r["title"], ";".join(r["bushings"]) or "NOT LISTED",
                        r["category"], ";".join(r["drill_sizes"]) or "NOT LISTED", tubes_csv(r["tubes"])])

    print(f"wrote CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
