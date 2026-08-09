"""
Step 3 of the pipeline: turn the raw per-SKU scrape into two views:

  - flat_skus: every real individual kit SKU (bundles/starter-sets and one
    mislabeled bushing-product excluded), no grouping at all. This is the
    guaranteed-accurate view.
  - designs: the flat SKUs grouped into "kit designs" by stripping known
    finish/plating words (Chrome, Gun Metal, Antique Brass, 24kt Gold, ...)
    out of the title -- wherever they appear, not just as a suffix -- and
    grouping what's left by (normalized name, bushing set). This is a
    best-effort heuristic against inconsistent title formatting; when in
    doubt, trust flat_skus instead.

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
FINAL_PATH = ROOT / "data" / "final_data.json"
COMPACT_PATH = ROOT / "data" / "compact_data.json"
OUTPUT_DIR = ROOT / "docs"

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


def main():
    raw = json.loads(RAW_PATH.read_text())["results"]

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
        })
    design_rows.sort(key=lambda r: r["design"].lower())

    print(f"design-level rows: {len(design_rows)}")

    FINAL_PATH.write_text(json.dumps({
        "flat_skus": kept,
        "designs": design_rows,
        "excluded_bundle_count": len(excluded_bundle),
        "excluded_bundle": [{"kit_id": r["kit_id"], "title": r["title"]} for r in excluded_bundle],
    }, indent=2))
    print(f"wrote {FINAL_PATH}")

    # Compact form for embedding in the HTML page, plus the bushing -> designs
    # reverse index used by the "By Bushing Set" view.
    designs_c = [{"d": r["design"], "b": r["bushing_ids"], "n": r["sku_count"],
                  "s": r["skus"], "c": r["category"]} for r in design_rows]
    flat_c = [{"k": r["kit_id"], "t": r["title"], "b": r["bushings"], "c": r["category"]}
              for r in kept]

    rev = defaultdict(set)
    for r in designs_c:
        for b in r["b"]:
            rev[b].add(r["d"])
    reverse_c = [{"b": b, "designs": sorted(ds)} for b, ds in sorted(rev.items())]

    COMPACT_PATH.write_text(json.dumps({
        "designs": designs_c, "flat": flat_c, "reverse": reverse_c,
        "excluded_bundle_count": len(excluded_bundle),
        "excluded_bundle": [{"kit_id": r["kit_id"], "title": r["title"]} for r in excluded_bundle],
    }, separators=(",", ":")))
    print(f"wrote {COMPACT_PATH}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_DIR / "pen_kit_bushing_by_design.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Design", "Bushing IDs", "SKU Count", "SKUs", "Category"])
        for r in design_rows:
            w.writerow([r["design"], ";".join(r["bushing_ids"]) or "NOT LISTED",
                        r["sku_count"], ";".join(r["skus"]), r["category"]])

    with open(OUTPUT_DIR / "pen_kit_bushing_flat.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Kit ID", "Title", "Bushing IDs", "Category"])
        for r in kept:
            w.writerow([r["kit_id"], r["title"], ";".join(r["bushings"]) or "NOT LISTED",
                        r["category"]])

    print(f"wrote CSVs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
