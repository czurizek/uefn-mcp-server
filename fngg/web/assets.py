"""Inline CSS and JS for the dashboard.

Everything is inlined into the page. No CDN, no build step, no network at render
time - the dashboard has to work on a laptop with the game running and nothing
else, and it has to keep working if fortnite.gg is unreachable.
"""

CSS = """
:root {
  --bg: #0e1016; --bg-soft: #14171f; --panel: #171b25; --panel-2: #1c212d;
  --border: #262c3a; --border-soft: #1f2531;
  --fg: #e8ecf4; --fg-dim: #a2acc0; --muted: #6f7a8f;
  --accent: #6ea8fe; --accent-soft: #24344f;
  --good: #47c08a; --warn: #e0a94a; --bad: #ef6f5e;
  --track: #232937;
  --rp: #8b7bf7; --ffa: #f2725c; --ow: #3fb8a0;
  --radius: 10px; --radius-sm: 6px;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg: #f6f7fa; --bg-soft: #ffffff; --panel: #ffffff; --panel-2: #f2f4f8;
    --border: #dfe3ea; --border-soft: #e9ecf1;
    --fg: #161a22; --fg-dim: #4b5567; --muted: #7c8698;
    --accent: #2c62d6; --accent-soft: #e2eaff;
    --track: #e6e9ef;
  }
}
:root[data-theme="light"] {
  --bg: #f6f7fa; --bg-soft: #ffffff; --panel: #ffffff; --panel-2: #f2f4f8;
  --border: #dfe3ea; --border-soft: #e9ecf1;
  --fg: #161a22; --fg-dim: #4b5567; --muted: #7c8698;
  --accent: #2c62d6; --accent-soft: #e2eaff;
  --track: #e6e9ef;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: var(--sans); font-size: 14px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3 { margin: 0; font-weight: 620; letter-spacing: -0.01em; }
h1 { font-size: 19px; }
h2 { font-size: 15px; }
h3 { font-size: 13px; color: var(--fg-dim); text-transform: uppercase; letter-spacing: 0.06em; }
code, .mono { font-family: var(--mono); font-size: 0.92em; }
.muted { color: var(--muted); }
.dim { color: var(--fg-dim); }

/* ------------------------------------------------------------------ chrome */
header.top {
  position: sticky; top: 0; z-index: 20;
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
}
.topbar { display: flex; align-items: center; gap: 16px; padding: 10px 20px; flex-wrap: wrap; }
.brand { display: flex; align-items: baseline; gap: 9px; font-weight: 700; letter-spacing: -0.02em; }
.brand .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); align-self: center; }
.brand small { font-weight: 500; color: var(--muted); font-size: 11px; letter-spacing: 0.04em; }
nav.tabs { display: flex; gap: 2px; padding: 0 14px 0; overflow-x: auto; }
nav.tabs a {
  padding: 8px 13px; border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  color: var(--fg-dim); font-size: 13px; font-weight: 500; white-space: nowrap;
  border-bottom: 2px solid transparent;
}
nav.tabs a:hover { color: var(--fg); background: var(--panel-2); text-decoration: none; }
nav.tabs a.on { color: var(--fg); border-bottom-color: var(--accent); background: var(--panel-2); }
.spacer { flex: 1; }
.themebtn {
  background: var(--panel-2); border: 1px solid var(--border); color: var(--fg-dim);
  border-radius: var(--radius-sm); padding: 5px 10px; cursor: pointer; font-size: 12px;
}
.themebtn:hover { color: var(--fg); }

main { padding: 20px; max-width: 1500px; margin: 0 auto; }
.page-head { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.page-head .lede { color: var(--fg-dim); max-width: 780px; font-size: 13.5px; margin-top: 4px; }

/* ------------------------------------------------------------------ panels */
.panel {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 16px; margin-bottom: 16px;
}
.panel > h2 { margin-bottom: 3px; }
.panel > .sub { color: var(--muted); font-size: 12.5px; margin-bottom: 14px; }
.grid { display: grid; gap: 16px; }
.grid.two { grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); }
.grid.three { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.grid.four { grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }

/* ------------------------------------------------------------------- stats */
.stat { background: var(--panel-2); border: 1px solid var(--border-soft); border-radius: var(--radius); padding: 12px 14px; }
.stat .k { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
.stat .v { font-size: 22px; font-weight: 640; letter-spacing: -0.02em; margin-top: 3px; font-variant-numeric: tabular-nums; }
.stat .n { color: var(--fg-dim); font-size: 12px; margin-top: 2px; }

/* ------------------------------------------------------------------ tables */
.tablewrap { overflow-x: auto; border-radius: var(--radius-sm); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th {
  text-align: left; padding: 8px 10px; color: var(--muted); font-weight: 600;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border); white-space: nowrap; position: sticky; top: 0;
  background: var(--panel);
}
thead th a { color: inherit; }
tbody td { padding: 8px 10px; border-bottom: 1px solid var(--border-soft); vertical-align: middle; }
tbody tr:hover { background: var(--panel-2); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; font-family: var(--mono); }
.title-cell { display: flex; flex-direction: column; gap: 2px; min-width: 200px; }
.title-cell .code { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.rank { color: var(--muted); font-family: var(--mono); font-size: 12px; width: 34px; }

/* ------------------------------------------------------------------- chips */
.chip {
  display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px;
  border-radius: 999px; font-size: 11px; font-weight: 600; white-space: nowrap;
  border: 1px solid var(--border); background: var(--panel-2); color: var(--fg-dim);
}
.chip i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.chip.solid { color: #fff; border-color: transparent; }
.tag { font-size: 11px; color: var(--muted); background: var(--panel-2); border-radius: 4px; padding: 1px 6px; }
.delta { font-family: var(--mono); font-size: 12px; font-weight: 600; }
.delta.up { color: var(--good); } .delta.down { color: var(--bad); } .delta.flat { color: var(--muted); }

/* --------------------------------------------------------------- pct bars */
.pctbar { display: inline-flex; align-items: center; gap: 7px; }
.pcttrack { position: relative; display: inline-block; width: var(--w, 120px); height: 6px; background: var(--track); border-radius: 3px; overflow: hidden; }
.pctfill { display: block; height: 100%; border-radius: 3px; }
.pctfill.low { background: var(--bad); } .pctfill.mid { background: var(--warn); } .pctfill.high { background: var(--good); }
.pcttick { position: absolute; left: 50%; top: -1px; width: 1px; height: 8px; background: var(--muted); opacity: .55; }
.pctlabel { font-family: var(--mono); font-size: 11px; color: var(--fg-dim); min-width: 30px; }

/* ------------------------------------------------------------------ dials */
.dial { color: var(--accent); }
.dial.low { color: var(--bad); } .dial.mid { color: var(--warn); } .dial.high { color: var(--good); }
.dialnum { font-size: 25px; font-weight: 700; fill: var(--fg); font-family: var(--sans); }
.dial.empty { color: var(--muted); font-size: 12px; }

/* ----------------------------------------------------------------- charts */
.linechart { display: block; width: 100%; height: auto; }
.scatter { display: block; width: 100%; height: auto; max-width: 1100px; margin: 0 auto; }
svg .grid { stroke: var(--border-soft); stroke-width: 1; }
svg .axis { fill: var(--muted); font-size: 10px; font-family: var(--mono); }
svg .axistitle { fill: var(--fg-dim); font-size: 11px; }
svg .quadline { stroke: var(--border); stroke-dasharray: 3 3; }
svg .quadlabel { fill: var(--muted); font-size: 10px; }
.chart-empty { color: var(--muted); font-size: 13px; padding: 26px 0; text-align: center; border: 1px dashed var(--border); border-radius: var(--radius-sm); }
.legend { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 8px; font-size: 12px; color: var(--fg-dim); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-item i { width: 9px; height: 3px; border-radius: 2px; }
.spark { vertical-align: middle; }

/* ------------------------------------------------------------------- bars */
.barchart { display: flex; flex-direction: column; gap: 7px; }
.barrow { display: grid; grid-template-columns: 128px 1fr 62px; align-items: center; gap: 10px; font-size: 12.5px; }
.barlabel { color: var(--fg-dim); }
.bartrack { height: 8px; background: var(--track); border-radius: 4px; overflow: hidden; }
.barfill { display: block; height: 100%; border-radius: 4px; }
.barvalue { font-family: var(--mono); font-size: 12px; text-align: right; }
.barnote { grid-column: 2 / -1; color: var(--muted); font-size: 11px; }
.barrow.done .barlabel { color: var(--muted); }
.barmet { color: var(--good); font-size: 11.5px; }
.barrow.done .barvalue { color: var(--good); }

/* ----------------------------------------------------------------- forms */
form.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
input[type=text], input[type=number], select {
  background: var(--panel-2); border: 1px solid var(--border); color: var(--fg);
  border-radius: var(--radius-sm); padding: 6px 10px; font-size: 13px; font-family: inherit;
}
input:focus, select:focus { outline: 2px solid var(--accent-soft); border-color: var(--accent); }
button.go { background: var(--accent); color: #fff; border: none; border-radius: var(--radius-sm); padding: 7px 14px; font-size: 13px; font-weight: 600; cursor: pointer; }
button.go:hover { filter: brightness(1.08); }

/* ------------------------------------------------------------------ notes */
.note { border-left: 3px solid var(--accent); background: var(--accent-soft); color: var(--fg);
  padding: 10px 13px; border-radius: 0 var(--radius-sm) var(--radius-sm) 0; font-size: 13px; margin-bottom: 14px; }
.note.warn { border-left-color: var(--warn); background: color-mix(in srgb, var(--warn) 13%, transparent); }
.note.bad { border-left-color: var(--bad); background: color-mix(in srgb, var(--bad) 13%, transparent); }
.note strong { font-weight: 650; }
details.caveats { margin-top: 12px; font-size: 12.5px; color: var(--fg-dim); }
details.caveats summary { cursor: pointer; color: var(--muted); }
details.caveats ul { margin: 8px 0 0; padding-left: 18px; }
details.caveats li { margin-bottom: 4px; }

/* ------------------------------------------------------------ row-fit grid */
.rowfit { display: flex; flex-direction: column; gap: 8px; }
.rowfit-item { display: grid; grid-template-columns: 190px 1fr 46px; gap: 12px; align-items: center; padding: 8px 10px; border-radius: var(--radius-sm); background: var(--panel-2); border: 1px solid var(--border-soft); }
.rowfit-item.curated { opacity: .62; }
.rowfit-item .rf-label { font-weight: 600; font-size: 13px; }
.rowfit-item .rf-note { grid-column: 1 / -1; color: var(--muted); font-size: 11.5px; margin-top: -2px; }
.rowfit-item .rf-score { font-family: var(--mono); font-weight: 700; text-align: right; }

/* ------------------------------------------------------------- map header */
.maphead { display: flex; gap: 22px; align-items: center; flex-wrap: wrap; }
.maphead .idblock { flex: 1; min-width: 240px; }
.maphead h1 { font-size: 22px; }
.kpigrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }
.kpirow { display: grid; grid-template-columns: 1fr auto 150px; gap: 10px; align-items: center; padding: 7px 10px; border-radius: var(--radius-sm); background: var(--panel-2); border: 1px solid var(--border-soft); }
.kpirow .kl { font-size: 12.5px; color: var(--fg-dim); }
.kpirow .kv { font-family: var(--mono); font-size: 13px; font-weight: 600; }

footer.foot { color: var(--muted); font-size: 12px; padding: 18px 20px 34px; max-width: 1500px; margin: 0 auto; border-top: 1px solid var(--border); }
footer.foot code { color: var(--fg-dim); }

@media (max-width: 720px) {
  main { padding: 14px; }
  .barrow { grid-template-columns: 96px 1fr 54px; }
  .rowfit-item { grid-template-columns: 130px 1fr 40px; }
  .kpirow { grid-template-columns: 1fr auto; }
  .kpirow .pctbar { display: none; }
}
"""

JS = """
(function () {
  var KEY = 'fngg-theme';
  var root = document.documentElement;
  try {
    var saved = localStorage.getItem(KEY);
    if (saved) root.setAttribute('data-theme', saved);
  } catch (e) { /* private mode: fall back to system theme */ }

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('.themebtn');
    if (!btn) return;
    var current = root.getAttribute('data-theme');
    if (!current) {
      var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      current = prefersDark ? 'dark' : 'light';
    }
    var next = current === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem(KEY, next); } catch (e) {}
  });

  // Sortable tables: click a header to re-sort client-side, no round trip.
  document.querySelectorAll('table[data-sortable]').forEach(function (table) {
    table.querySelectorAll('thead th[data-sort]').forEach(function (th, index) {
      th.style.cursor = 'pointer';
      th.addEventListener('click', function () {
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        var numeric = th.dataset.sort === 'num';
        var asc = th.dataset.dir !== 'asc';
        table.querySelectorAll('thead th').forEach(function (o) { delete o.dataset.dir; });
        th.dataset.dir = asc ? 'asc' : 'desc';
        rows.sort(function (a, b) {
          var av = a.cells[index] ? (a.cells[index].dataset.v || a.cells[index].innerText) : '';
          var bv = b.cells[index] ? (b.cells[index].dataset.v || b.cells[index].innerText) : '';
          if (numeric) {
            var an = parseFloat(av), bn = parseFloat(bv);
            if (isNaN(an)) an = -Infinity;
            if (isNaN(bn)) bn = -Infinity;
            return asc ? an - bn : bn - an;
          }
          return asc ? av.localeCompare(bv) : bv.localeCompare(av);
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });
})();
"""
