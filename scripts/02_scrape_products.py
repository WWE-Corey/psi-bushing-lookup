"""
Step 2 of the pipeline: fetch every product page and pull out title,
bushing set(s), drill size(s), instruction-PDF link, and category.

Each kit's page has rows like:
    <tr><td><span class="emphasis">Bushings Needed:</span></td>
        <td><a href="/store/PKFSANDBU.html">Item #PKFSANDBU</a></td></tr>
    <tr><td><span class="emphasis">Drill Sizes Used:</span></td>
        <td><a href="/store/PKEXEC-38.html">3/8in Drill Bit</a></td></tr>
We match each row, then pull every /store/<ID>.html link (and, for drills,
its link text) inside its cell -- a small number of kits list more than one
bushing set or drill bit.

Each page also links its PDF instruction sheet under /library/<code>.pdf
(one sheet is typically shared by every color/finish variant of a kit).
Tube/barrel length isn't published in the HTML at all -- it's only in that
PDF's parts-layout diagram -- so we just capture the link here; a later
step (03_fetch_instructions.py) downloads and parses the PDFs themselves.

Runs 10 requests concurrently; ~700 pages takes about a minute and a half.
"""
import re
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
IDS_PATH = ROOT / "data" / "all_ids.txt"
OUT_PATH = ROOT / "data" / "scraped_raw.json"

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
BUSH_ROW_RE = re.compile(r"Bushings Needed:.*?</td>\s*<td>(.*?)</td>", re.S)
BUSH_LINK_RE = re.compile(r'href="/store/([A-Za-z0-9\-]+)\.html"')
DRILL_ROW_RE = re.compile(r"Drill Sizes Used:.*?</td>\s*<td>(.*?)</td>", re.S)
DRILL_LINK_RE = re.compile(r'<a href="/store/([A-Za-z0-9\-]+)\.html">([^<]*)</a>')
INSTR_PDF_RE = re.compile(r'href="(/library/[^"]+\.pdf)"', re.I)
CATEGORY_RE = re.compile(r"Category:</span></td>\s*<td>(.*?)</td>", re.S)


def fetch(kit_id):
    url = f"https://www.pennstateind.com/store/{kit_id}.html"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"kit_id": kit_id, "error": str(e)}

    tm = TITLE_RE.search(html)
    title = tm.group(1).strip() if tm else ""
    title = title.replace(" at Penn State Industries", "").strip()

    bm = BUSH_ROW_RE.search(html)
    bushings = BUSH_LINK_RE.findall(bm.group(1)) if bm else []

    dm = DRILL_ROW_RE.search(html)
    drills = [{"id": did, "label": label.strip()}
              for did, label in DRILL_LINK_RE.findall(dm.group(1))] if dm else []

    pm = INSTR_PDF_RE.search(html)
    instructions_pdf = pm.group(1) if pm else None

    cm = CATEGORY_RE.search(html)
    category = re.sub("<[^>]+>", "", cm.group(1)).strip() if cm else ""

    return {"kit_id": kit_id, "title": title, "bushings": bushings, "drills": drills,
            "instructions_pdf": instructions_pdf, "category": category}


def main():
    ids = [line.strip() for line in IDS_PATH.read_text().splitlines() if line.strip()]
    print(f"fetching {len(ids)} product pages...")

    results, errors = [], []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(fetch, kid): kid for kid in ids}
        done = 0
        for fut in as_completed(futures):
            r = fut.result()
            done += 1
            (errors if "error" in r else results).append(r)
            if done % 100 == 0:
                print(f"  {done}/{len(ids)} done ({time.time()-t0:.0f}s)")

    print(f"done in {time.time()-t0:.0f}s. ok={len(results)} errors={len(errors)}")

    scraped_at = datetime.now(timezone.utc).date().isoformat()
    OUT_PATH.write_text(json.dumps({"scraped_at": scraped_at, "results": results, "errors": errors}))
    print(f"wrote {OUT_PATH}")

    no_bushing = [r for r in results if not r["bushings"]]
    multi_bushing = [r for r in results if len(r["bushings"]) > 1]
    no_drill = [r for r in results if not r["drills"]]
    no_instructions = [r for r in results if not r["instructions_pdf"]]
    print("no bushing found:", len(no_bushing))
    print("multiple bushings:", len(multi_bushing))
    print("no drill size found:", len(no_drill))
    print("no instructions pdf found:", len(no_instructions))


if __name__ == "__main__":
    main()
