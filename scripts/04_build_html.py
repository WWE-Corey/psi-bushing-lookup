"""
Step 4 of the pipeline: build the standalone, self-contained reference page
from data/compact_data.json. Writes output/index.html, which can be opened
directly in a browser or served as-is (e.g. via GitHub Pages).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPACT_PATH = ROOT / "data" / "compact_data.json"
OUT_PATH = ROOT / "output" / "index.html"

data_json = COMPACT_PATH.read_text()

html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pen Kit &rarr; Bushing Cross-Reference</title>
<style>
:root {
  --bg: #E7E3D6;
  --surface: #F4F1E7;
  --surface-alt: #E0DBC9;
  --ink: #241C15;
  --ink-dim: #5B5040;
  --line: #C8C0A9;
  --brass: #92672E;
  --brass-strong: #74501F;
  --brass-tint: #EDE0C6;
  --rust: #9C3F29;
  --rust-bg: #EFDACF;
  --focus: #3A6E8F;
  --shadow: rgba(36, 28, 21, 0.14);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #1E1811;
    --surface: #291F16;
    --surface-alt: #33271A;
    --ink: #ECE3D2;
    --ink-dim: #B4A688;
    --line: #4B3E2B;
    --brass: #D6A45F;
    --brass-strong: #EABB7B;
    --brass-tint: #3A2C18;
    --rust: #DD7A57;
    --rust-bg: #3E271C;
    --focus: #7FB3D5;
    --shadow: rgba(0, 0, 0, 0.45);
  }
}
:root[data-theme="dark"] {
  --bg: #1E1811;
  --surface: #291F16;
  --surface-alt: #33271A;
  --ink: #ECE3D2;
  --ink-dim: #B4A688;
  --line: #4B3E2B;
  --brass: #D6A45F;
  --brass-strong: #EABB7B;
  --brass-tint: #3A2C18;
  --rust: #DD7A57;
  --rust-bg: #3E271C;
  --focus: #7FB3D5;
  --shadow: rgba(0, 0, 0, 0.45);
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3 {
  font-family: "Roboto Slab", Rockwell, "Sitka Small", Georgia, serif;
  font-weight: 700;
  text-wrap: balance;
  margin: 0;
}
.mono {
  font-family: ui-monospace, "SF Mono", "Cascadia Mono", Consolas, monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}
a { color: var(--focus); }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

.wrap { max-width: 1080px; margin: 0 auto; padding: 0 24px 80px; }

header.hero {
  border-bottom: 1px solid var(--line);
  padding: 44px 0 28px;
  margin-bottom: 28px;
}
.eyebrow {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.11em;
  color: var(--brass);
}
h1 {
  font-size: clamp(28px, 4vw, 40px);
  margin-top: 8px;
  color: var(--ink);
}
.dek {
  color: var(--ink-dim);
  max-width: 62ch;
  margin-top: 12px;
  font-size: 15.5px;
}
.dek code {
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  background: var(--surface-alt);
  padding: 0.1em 0.35em;
  border-radius: 3px;
  font-size: 0.92em;
}

.stat-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  margin-top: 26px;
  border-radius: 2px;
  overflow: hidden;
}
.stat {
  background: var(--surface);
  padding: 14px 16px;
}
.stat .n {
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-variant-numeric: tabular-nums;
  font-size: 24px;
  font-weight: 600;
  color: var(--brass);
  display: block;
}
.stat .l {
  font-size: 12px;
  color: var(--ink-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.controls {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--bg);
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
  margin-bottom: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.tabs {
  display: flex;
  gap: 2px;
  background: var(--surface-alt);
  padding: 3px;
  border-radius: 6px;
  border: 1px solid var(--line);
}
.tab {
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink-dim);
  background: transparent;
  border: none;
  padding: 7px 14px;
  border-radius: 4px;
  cursor: pointer;
}
.tab[aria-selected="true"] {
  background: var(--surface);
  color: var(--brass-strong);
  box-shadow: 0 1px 2px var(--shadow);
}
.tab:hover:not([aria-selected="true"]) { color: var(--ink); }

.search-box { flex: 1 1 220px; min-width: 200px; position: relative; }
.search-box input {
  width: 100%;
  font: inherit;
  font-size: 14px;
  padding: 8px 12px 8px 32px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--ink);
}
.search-box::before {
  content: "";
  position: absolute;
  left: 11px; top: 50%;
  width: 12px; height: 12px;
  transform: translateY(-50%);
  border: 1.5px solid var(--ink-dim);
  border-radius: 50%;
  box-shadow: 4px 4px 0 -3px var(--ink-dim);
}
.count-note { font-size: 12.5px; color: var(--ink-dim); white-space: nowrap; }

.downloads { display: flex; gap: 10px; font-size: 12.5px; }
.downloads a {
  text-decoration: none;
  color: var(--ink-dim);
  border: 1px solid var(--line);
  padding: 4px 9px;
  border-radius: 5px;
}
.downloads a:hover { color: var(--brass-strong); border-color: var(--brass); }

.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; margin-top: 16px; }
table { width: 100%; border-collapse: collapse; font-size: 13.8px; }
thead th {
  text-align: left;
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-dim);
  font-weight: 600;
  padding: 10px 14px;
  background: var(--surface-alt);
  border-bottom: 1px solid var(--line);
  position: sticky;
  top: 61px;
}
tbody tr { background: var(--surface); border-bottom: 1px solid var(--line); }
tbody tr:nth-child(even) { background: var(--surface-alt); }
tbody tr:last-child { border-bottom: none; }
td { padding: 9px 14px; vertical-align: top; }
td.name { color: var(--ink); font-weight: 500; }
td.skus { color: var(--ink-dim); }
.sku-count {
  display: inline-block;
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-size: 11px;
  color: var(--ink-dim);
  background: var(--surface-alt);
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 1px 5px;
  margin-left: 6px;
}

.chip {
  display: inline-block;
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-size: 12px;
  color: var(--brass-strong);
  background: var(--brass-tint);
  border: 1px solid var(--brass);
  border-radius: 3px;
  padding: 1px 6px;
  margin: 1px 3px 1px 0;
  white-space: nowrap;
}
.flag {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--rust);
  background: var(--rust-bg);
  border: 1px solid var(--rust);
  border-radius: 3px;
  padding: 1px 6px;
  white-space: nowrap;
}
.cat { color: var(--ink-dim); font-size: 12.5px; }
.empty-state {
  padding: 40px 16px;
  text-align: center;
  color: var(--ink-dim);
  font-size: 14px;
}

details.notes {
  margin-top: 34px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  padding: 4px 0;
}
details.notes summary {
  cursor: pointer;
  padding: 12px 16px;
  font-weight: 600;
  font-size: 13.5px;
  color: var(--ink);
  list-style: none;
}
details.notes summary::-webkit-details-marker { display: none; }
details.notes summary::before {
  content: "\25B8";
  display: inline-block;
  margin-right: 8px;
  color: var(--brass);
  transition: transform 0.15s ease;
}
details.notes[open] summary::before { transform: rotate(90deg); }
.notes-body { padding: 4px 16px 16px; color: var(--ink-dim); font-size: 13.5px; }
.notes-body p { margin: 0 0 10px; }
.notes-body p:last-child { margin-bottom: 0; }
.notes-body ul { margin: 0 0 10px; padding-left: 20px; }
.notes-body li { margin-bottom: 4px; }

footer.page-foot {
  margin-top: 40px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  font-size: 12.5px;
  color: var(--ink-dim);
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
}
@media (max-width: 640px) {
  .stat-strip { grid-template-columns: repeat(2, 1fr); }
  thead th { position: static; }
}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <div class="eyebrow">Woodturning reference &middot; pennstateind.com</div>
    <h1>Pen Kit &rarr; Bushing Cross-Reference</h1>
    <p class="dek">Every current Penn State Industries pen/pencil kit, matched to the bushing set it turns against &mdash; built by scraping all live product pages directly (the official Bushing Book PDF is out of date and missing kits, e.g. <code>PKJ316CH</code>).</p>
    <div class="stat-strip">
      <div class="stat"><span class="n mono" id="stat-designs">&mdash;</span><span class="l">Kit designs</span></div>
      <div class="stat"><span class="n mono" id="stat-skus">&mdash;</span><span class="l">Individual SKUs</span></div>
      <div class="stat"><span class="n mono" id="stat-bushings">&mdash;</span><span class="l">Distinct bushing sets</span></div>
      <div class="stat"><span class="n mono" id="stat-flagged">&mdash;</span><span class="l">Not listed by PSI</span></div>
    </div>
  </header>

  <div class="controls">
    <div class="tabs" role="tablist" aria-label="View">
      <button class="tab" role="tab" data-view="design" aria-selected="true">By Kit Design</button>
      <button class="tab" role="tab" data-view="flat" aria-selected="false">By Exact SKU</button>
      <button class="tab" role="tab" data-view="reverse" aria-selected="false">By Bushing Set</button>
    </div>
    <div class="search-box">
      <input type="search" id="search" placeholder="Search kit, SKU, or bushing ID&hellip;" autocomplete="off">
    </div>
    <div class="count-note" id="count-note"></div>
  </div>

  <div class="table-wrap">
    <table id="table">
      <thead id="thead"></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty-state" id="empty-state" hidden>No matches. Try a different kit name, SKU, or bushing ID.</div>
  </div>

  <div class="downloads">
    <a href="pen_kit_bushing_by_design.csv" download>&darr; CSV &mdash; by design</a>
    <a href="pen_kit_bushing_flat.csv" download>&darr; CSV &mdash; by exact SKU</a>
  </div>

  <details class="notes">
    <summary>Methodology &amp; caveats</summary>
    <div class="notes-body">
      <p><strong>Source:</strong> live-scraped from every product page under pennstateind.com's pen-kits category (each page's own "Bushings Needed" field is authoritative here, not the printed Bushing Book).</p>
      <p><strong>"By Kit Design" grouping:</strong> the raw SKU list includes one page per color/finish variant of the same physical kit (e.g. Chrome, Gun Metal, Antique Brass). Starter-set/variety-pack/bundle SKUs and one mislabeled bushing-set product (<code>PKOLIVEBU</code>) are excluded first. The remaining individual kit SKUs are grouped into designs by stripping known finish/plating words (Chrome, Gun Metal, Antique Brass, 24kt Gold, Satin Nickel, etc.) from the title and grouping by the remaining name + bushing set. This is a best-effort heuristic against inconsistent title formatting &mdash; if you need certainty for a specific kit, cross-check it in the "By Exact SKU" view, which does no grouping at all.</p>
      <p><strong>"Not listed by PSI":</strong> these kits have no "Bushings Needed" field on their own product page at all &mdash; not a scraping gap, confirmed by direct inspection. Rather than guess, they're flagged as-is.</p>
      <p>See <code>README.md</code> for how to re-run the scrape and regenerate this page.</p>
    </div>
  </details>

  <footer class="page-foot">
    Personal woodturning reference &mdash; not affiliated with Penn State Industries. See README for data capture date.
  </footer>
</div>

<script id="app-data" type="application/json">__DATA_JSON__</script>
<script>
const DATA = JSON.parse(document.getElementById('app-data').textContent);
const $ = (sel, el) => (el || document).querySelector(sel);
const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));

document.getElementById('stat-designs').textContent = DATA.designs.length;
document.getElementById('stat-skus').textContent = DATA.flat.length;
document.getElementById('stat-bushings').textContent = DATA.reverse.length;
document.getElementById('stat-flagged').textContent = DATA.designs.filter(r => !r.b || r.b.length === 0).length;

function bushingCell(ids) {
  if (!ids || ids.length === 0) return '<span class="flag">Not listed by PSI</span>';
  return ids.map(id => `<span class="chip">${id}</span>`).join('');
}

const views = {
  design: {
    head: ['Kit design', 'Bushing set', 'SKUs', 'Category'],
    rows: () => DATA.designs,
    render: r => `
      <td class="name">${r.d}${r.n > 1 ? `<span class="sku-count">${r.n} colors</span>` : ''}</td>
      <td>${bushingCell(r.b)}</td>
      <td class="skus mono">${r.s.join(', ')}</td>
      <td class="cat">${r.c}</td>
    `,
    match: (r, q) => r.d.toLowerCase().includes(q) || r.s.some(s => s.toLowerCase().includes(q)) || r.b.some(b => b.toLowerCase().includes(q)),
  },
  flat: {
    head: ['SKU', 'Title', 'Bushing set', 'Category'],
    rows: () => DATA.flat,
    render: r => `
      <td class="name mono">${r.k}</td>
      <td>${r.t}</td>
      <td>${bushingCell(r.b)}</td>
      <td class="cat">${r.c}</td>
    `,
    match: (r, q) => r.k.toLowerCase().includes(q) || r.t.toLowerCase().includes(q) || r.b.some(b => b.toLowerCase().includes(q)),
  },
  reverse: {
    head: ['Bushing set', 'Used by kit designs'],
    rows: () => DATA.reverse,
    render: r => `
      <td class="name mono">${r.b}</td>
      <td>${r.designs.join(', ')}</td>
    `,
    match: (r, q) => r.b.toLowerCase().includes(q) || r.designs.some(d => d.toLowerCase().includes(q)),
  },
};

let activeView = 'design';

function renderTable() {
  const v = views[activeView];
  const q = $('#search').value.trim().toLowerCase();
  const all = v.rows();
  const filtered = q ? all.filter(r => v.match(r, q)) : all;

  $('#thead').innerHTML = `<tr>${v.head.map(h => `<th>${h}</th>`).join('')}</tr>`;
  $('#tbody').innerHTML = filtered.map(r => `<tr>${v.render(r)}</tr>`).join('');
  $('#empty-state').hidden = filtered.length !== 0;
  $('#table').style.display = filtered.length === 0 ? 'none' : '';
  $('#count-note').textContent = `${filtered.length} of ${all.length}`;
}

$$('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    activeView = btn.dataset.view;
    $$('.tab').forEach(b => b.setAttribute('aria-selected', b === btn ? 'true' : 'false'));
    renderTable();
  });
});

$('#search').addEventListener('input', renderTable);
renderTable();
</script>
</body>
</html>
'''

html = html.replace('__DATA_JSON__', data_json.replace('</script>', '<\\/script>'))

OUT_PATH.parent.mkdir(exist_ok=True)
OUT_PATH.write_text(html)
print(f"wrote {OUT_PATH} ({len(html)} bytes)")
