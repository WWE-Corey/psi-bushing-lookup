"""
Step 2 of the pipeline: fetch every product page and pull out title,
bushing set(s), and category.

Each kit's page has a row like:
    <tr><td><span class="emphasis">Bushings Needed:</span></td>
        <td><a href="/store/PKFSANDBU.html">Item #PKFSANDBU</a></td></tr>
We match the "Bushings Needed:" row, then pull every /store/<ID>.html link
inside its cell (a small number of kits list more than one bushing set).

Runs 10 requests concurrently; ~700 pages takes about a minute and a half.
"""
import re
import json
import time
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
IDS_PATH = ROOT / "data" / "all_ids.txt"
OUT_PATH = ROOT / "data" / "scraped_raw.json"

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
BUSH_ROW_RE = re.compile(r"Bushings Needed:.*?</td>\s*<td>(.*?)</td>", re.S)
BUSH_LINK_RE = re.compile(r'href="/store/([A-Za-z0-9\-]+)\.html"')
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

    cm = CATEGORY_RE.search(html)
    category = re.sub("<[^>]+>", "", cm.group(1)).strip() if cm else ""

    return {"kit_id": kit_id, "title": title, "bushings": bushings, "category": category}


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

    OUT_PATH.write_text(json.dumps({"results": results, "errors": errors}))
    print(f"wrote {OUT_PATH}")

    no_bushing = [r for r in results if not r["bushings"]]
    multi_bushing = [r for r in results if len(r["bushings"]) > 1]
    print("no bushing found:", len(no_bushing))
    print("multiple bushings:", len(multi_bushing))


if __name__ == "__main__":
    main()
