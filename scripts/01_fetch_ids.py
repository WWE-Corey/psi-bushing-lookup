"""
Step 1 of the pipeline: get the full list of current pen-kit product IDs.

pennstateind.com's category pages paginate at 48 items by default, and
?page=N / ?p=N / ?pg=N are all silently ignored. The real "show everything"
switch is a hidden Per_Page=-1 query param, found by inspecting the page's
own <select name="Per_Page"> element rather than guessing at URL patterns.

Product IDs are pulled from the page's embedded Google Analytics ecommerce
dataLayer JSON (`item_id: 'XXXXX'`), which is more reliable than parsing the
visual product-card HTML/links (inconsistent markup between card types).
"""
import re
import urllib.request
from pathlib import Path

CATEGORY_URL = "https://www.pennstateind.com/store/pen-kits.html?Per_Page=-1"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "all_ids.txt"

req = urllib.request.Request(CATEGORY_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as resp:
    html = resp.read().decode("utf-8", errors="replace")

ids = sorted(set(re.findall(r"item_id:\s*'([A-Z0-9-]+)'", html)))

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUT_PATH.write_text("\n".join(ids) + "\n")

print(f"found {len(ids)} product IDs, wrote {OUT_PATH}")
