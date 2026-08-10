# PSI Bushing Lookup

A cross-reference of every current Penn State Industries (pennstateind.com) pen/pencil kit and the bushing set it turns against, built by scraping their live product pages directly.

Penn State Industries publishes an official "Bushing Book" PDF, but it's out of date and missing kits (e.g. `PKJ316CH` isn't in it, despite being a currently sold kit). This project scrapes the site itself instead, so it stays accurate as PSI adds or retires kits.

## Using it

Live at **https://wwe-corey.github.io/psi-bushing-lookup/** (GitHub Pages, served from `docs/`), or open [`docs/index.html`](docs/index.html) directly in a browser — it's a single self-contained file, no server needed. It has three views:

- **By Kit Design** — the ~270 physical kit designs, color/finish variants merged into one row each (best-effort — see caveats below)
- **By Exact SKU** — every individual product SKU, one per row, no grouping. This is the guaranteed-accurate view; use it when you need certainty for a specific kit.
- **By Bushing Set** — reverse lookup: given a bushing set ID, which kit designs use it.

The design and SKU views also show **drill size** and **tube/barrel length** — useful for batching blank-cutting and drilling across kits that share a setup, so you're not swapping bits and re-measuring for every kit. Drill size is reliable (same source as bushings); tube length is best-effort (see caveats).

All three are searchable (kit name, SKU, bushing ID, drill size, or tube length) and there are CSV downloads for the design-level and flat views under `docs/`.

## How it was built

Five scripts, run in order, each reading the previous step's output from `data/`:

```
python3 scripts/01_fetch_ids.py          # -> data/all_ids.txt
python3 scripts/02_scrape_products.py    # -> data/scraped_raw.json
python3 scripts/03_fetch_instructions.py # -> data/instructions_raw.json
python3 scripts/04_process.py            # -> data/final_data.json, data/compact_data.json, docs/*.csv
python3 scripts/05_build_html.py         # -> docs/index.html
```

Steps 1, 2, 4, and 5 use only the Python 3 standard library. Step 3 needs **[pdfplumber](https://github.com/jsvine/pdfplumber)** (`pip install -r requirements.txt`) to parse PSI's instruction-sheet PDFs.

1. **`01_fetch_ids.py`** — fetches the pen-kits category page with the hidden `Per_Page=-1` query param (the only way to get the full list in one request; `?page=N` is silently ignored) and pulls every product ID out of the page's embedded Google Analytics `dataLayer` JSON.
2. **`02_scrape_products.py`** — fetches all ~700 individual product pages (10 concurrent requests) and extracts title, bushing set ID(s), drill size(s), instruction-PDF link, and category from each via regex against the page's own spec-table rows.
3. **`03_fetch_instructions.py`** — downloads each *unique* instruction PDF (one is normally shared by every color/finish variant of a kit, so this is a few hundred PDFs, not ~700) and parses tube/barrel length out of its parts-layout diagram. Tube length isn't published in the HTML at all — it only exists as a dimension callout inside that PDF, and neither the label wording nor the value format is consistent across kit families, so this uses word-position matching (pair a "Tube" label with the nearest number on the page) rather than assuming any fixed text pattern. It resolves roughly 70% of kits; the rest are left blank rather than guessed. See the module docstring for the format variants this handles.
4. **`04_process.py`** — excludes starter-set/variety-pack/bundle SKUs and one mislabeled bushing-set product, merges in drill size and tube length from steps 2–3, then groups the remaining SKUs into kit designs by stripping known finish/plating words (Chrome, Gun Metal, Antique Brass, 24kt Gold, etc.) from titles and grouping by (normalized name, bushing set).
5. **`05_build_html.py`** — renders `docs/index.html` from `data/compact_data.json`. Commit and push `docs/index.html` and the site at the Pages URL above updates automatically.

## Re-scraping

PSI adds and discontinues kits over time. To refresh:

```
python3 scripts/01_fetch_ids.py
python3 scripts/02_scrape_products.py
python3 scripts/03_fetch_instructions.py
python3 scripts/04_process.py
python3 scripts/05_build_html.py
```

`data/scraped_raw.json` and `data/instructions_raw.json` are the raw snapshots; everything downstream regenerates from them, so you only need to re-run steps 1–3 against the live site, then 4–5 are pure local processing.

## Caveats

- **Grouping is a heuristic.** Color/finish words don't sit in a consistent position in PSI's titles (sometimes trailing "...Pen Kit in Chrome", sometimes mid-title "Astra Golden Twist Pen Kit"), so the finish-word list in `04_process.py` is curated from a word-frequency pass over real titles, not exhaustive by construction. If a kit's design grouping looks wrong, check it against the **By Exact SKU** view, which never groups anything.
- **"Not listed by PSI"** (bushings, drill size) means the kit's own product page has no such field at all — confirmed by direct inspection, not a scraping failure. A handful of kits (mostly Protura and Pool Cue Chalk Holder variants) are like this on PSI's site itself.
- **"not extracted"** (tube length only) means something different: PSI *does* publish this value, inside the kit's instruction PDF, but the extraction heuristic in `03_fetch_instructions.py` couldn't pull it out reliably from that particular sheet's layout. It's a gap in this tool, not in PSI's data — check the instruction PDF directly (linked from the product page) if you need it for one of these kits.
- **Bundles/starter sets are excluded entirely** from both the design and flat views (they bundle multiple designs rather than being one distinct kit), but are counted in `data/final_data.json`'s `excluded_bundle` list if you want to see what was left out.

## Repo layout

```
scripts/     the 5 pipeline scripts, run in order
data/        scraped/processed data snapshots (regenerated by the pipeline)
docs/        the built page (index.html) and CSV exports — also what GitHub Pages serves
```
