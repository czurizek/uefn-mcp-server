"""HTML rendering for the dashboard.

Pages are rendered server-side. The only client-side JavaScript is a theme
toggle and client-side table sorting - everything analytical happens in Python
so the same numbers back the dashboard, the CLI and the MCP tools.
"""

from __future__ import annotations

import html
from typing import Any, Iterable, Optional, Sequence

from .. import __version__
from ..analytics.discovery import CAVEATS, COMPONENT_HELP, COMPONENT_LABELS, ROW_ARCHETYPES
from ..analytics.kpis import KPI_HELP, KPI_LABELS, KPIS, NEUTRAL_KPIS, format_kpi
from ..genres import FOCUS_GENRES, GENRE_LABELS, label_of
from .assets import CSS, JS
from .charts import (
    bar_chart,
    compact,
    genre_color,
    genre_legend,
    line_chart,
    percentile_bar,
    scatter,
    score_dial,
    sparkline,
)

TABS = (
    ("discovery", "Discovery", "/"),
    ("browse", "Browse", "/browse"),
    ("movers", "Movers", "/movers"),
    ("retention", "Retention", "/retention"),
    ("engagement", "Engagement", "/engagement"),
    ("cohorts", "Benchmarks", "/cohorts"),
    ("compare", "Compare", "/compare"),
    ("status", "Status", "/status"),
)

COMPONENT_ORDER = ("scale", "retention", "depth", "advocacy", "momentum")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


# --------------------------------------------------------------------- layout


def layout(*, title: str, active: str, body: str, dataset=None) -> str:
    tabs = "".join(
        f'<a href="{esc(href)}" class="{"on" if key == active else ""}">{esc(label)}</a>'
        for key, label, href in TABS
    )
    footer = ""
    if dataset is not None:
        summary = dataset.summary()
        footer = (
            f"{summary['islands']} islands · {summary['scored']} scored · "
            f"{summary['with_history']} with usable history · "
            f"{summary['history_days']} days of local history · "
            f"generated {esc(summary['generated_at'])}"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · fngg</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%236ea8fe'/%3E%3Cpath d='M8 22V10h5m-5 6h4M17 22V10m0 0h4a4 4 0 010 8h-4' stroke='%230e1016' stroke-width='2.6' fill='none' stroke-linecap='round'/%3E%3C/svg%3E">
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <div class="topbar">
    <span class="brand"><span class="dot"></span>fngg <small>ISLAND ANALYTICS</small></span>
    <span class="spacer"></span>
    <form class="filters" action="/browse" method="get" style="margin:0">
      <input type="text" name="q" placeholder="Search title, code or creator…" style="width:230px">
      <button class="go" type="submit">Search</button>
    </form>
    <button class="themebtn" type="button" title="Toggle light / dark">◐ Theme</button>
  </div>
  <nav class="tabs">{tabs}</nav>
</header>
<main>{body}</main>
<footer class="foot">
  <div>{footer}</div>
  <div style="margin-top:6px">fngg v{esc(__version__)} · data from Epic's public Ecosystem API
  (<code>api.fortnite.com/ecosystem/v1</code>) plus your own local polling history.</div>
</footer>
<script>{JS}</script>
</body>
</html>"""


# ----------------------------------------------------------------- components


def stat(label: str, value: str, note: str = "") -> str:
    note_html = f'<div class="n">{esc(note)}</div>' if note else ""
    return f'<div class="stat"><div class="k">{esc(label)}</div><div class="v">{value}</div>{note_html}</div>'


def genre_chip(genre: Optional[str]) -> str:
    color = genre_color(genre)
    return (
        f'<span class="chip" style="color:{color};border-color:{color}44">'
        f'<i></i>{esc(label_of(genre))}</span>'
    )


def delta_span(value: Optional[float], *, as_pct: bool = True, invert: bool = False) -> str:
    if value is None:
        return '<span class="delta flat">–</span>'
    good = value > 0 if not invert else value < 0
    cls = "flat" if abs(value) < (0.005 if as_pct else 0.5) else ("up" if good else "down")
    text = f"{value * 100:+.1f}%" if as_pct else f"{value:+,.0f}"
    return f'<span class="delta {cls}">{esc(text)}</span>'


def rank_delta_span(value: Optional[int]) -> str:
    if value is None:
        return '<span class="delta flat">–</span>'
    cls = "flat" if value == 0 else ("up" if value > 0 else "down")
    arrow = "→" if value == 0 else ("▲" if value > 0 else "▼")
    return f'<span class="delta {cls}">{arrow} {abs(value)}</span>'


def island_link(row: dict) -> str:
    title = row.get("title") or "(untitled)"
    return (
        f'<span class="title-cell"><a href="/island/{esc(row.get("code"))}">{esc(title)}</a>'
        f'<span class="code">{esc(row.get("code"))}'
        + (f' · {esc(row.get("creator_code"))}' if row.get("creator_code") else "")
        + "</span></span>"
    )


def genre_selector(current: Optional[str], counts: Sequence[dict], *, action: str) -> str:
    options = ['<option value="all">All genres</option>']
    for entry in counts:
        selected = " selected" if entry["genre"] == current else ""
        star = "★ " if entry["focus"] else ""
        options.append(
            f'<option value="{esc(entry["genre"])}"{selected}>{star}{esc(entry["label"])} '
            f'({entry["count"]})</option>'
        )
    return (
        f'<form class="filters" method="get" action="{esc(action)}">'
        f'<select name="genre" onchange="this.form.submit()">{"".join(options)}</select>'
        f'<noscript><button class="go" type="submit">Apply</button></noscript></form>'
    )


def caveat_block(extra: Iterable[str] = ()) -> str:
    items = "".join(f"<li>{esc(c)}</li>" for c in list(CAVEATS) + list(extra))
    return (
        '<details class="caveats"><summary>How this score is built, and what it cannot see</summary>'
        f"<ul>{items}</ul></details>"
    )


def warning_notes(dataset) -> str:
    return "".join(f'<div class="note warn">{esc(w)}</div>' for w in dataset.warnings)


# ---------------------------------------------------------------- Discovery


def page_discovery(dataset, params: dict) -> str:
    genre = params.get("genre") or "all"
    rows = dataset.filter(genre=None if genre == "all" else genre)
    scored = [r for r in rows if r.get("discovery_score") is not None]
    scored.sort(key=lambda r: -r["discovery_score"])

    head = f"""
<div class="page-head">
  <div>
    <h1>Discovery</h1>
    <p class="lede">Where each island stands against <em>comparable</em> islands on the signals Epic
    says its algorithmic Discover rows respond to — audience size, how often players come back, and
    how long they stay. Every number is a percentile inside a genre cohort, so a 40 means
    "60% of islands like yours beat you here".</p>
  </div>
  <span class="spacer"></span>
  {genre_selector(genre, dataset.genre_counts(), action="/")}
</div>
{warning_notes(dataset)}
"""

    # Headline stats for the selected cohort.
    top = scored[0] if scored else None
    median = sorted(r["discovery_score"] for r in scored)[len(scored) // 2] if scored else None
    stats_html = f"""
<div class="grid four">
  {stat("Islands scored", str(len(scored)), f"cohort: {label_of(genre) if genre != 'all' else 'all genres'}")}
  {stat("Median fitness", f"{median:.1f}" if median is not None else "–", "50th percentile of this view")}
  {stat("Leader", esc((top or {}).get("title") or "–"), f"{top['discovery_score']:.1f} fitness" if top else "")}
  {stat("With trend data", str(sum(1 for r in rows if r.get('momentum_reliable'))), "needs 3+ days of polling")}
</div>
"""

    # Leaderboard.
    body_rows = []
    for position, row in enumerate(scored[:60], start=1):
        components = "".join(
            f'<td class="num" data-v="{row["discovery_components"].get(c) or -1}">'
            f'{percentile_bar(row["discovery_components"].get(c), width=62, label=False)}</td>'
            for c in COMPONENT_ORDER
        )
        best = row.get("best_row") or {}
        lever = row.get("discovery_top_lever") or {}
        body_rows.append(
            f"""<tr>
  <td class="rank">{position}</td>
  <td>{island_link(row)}</td>
  <td>{genre_chip(row.get("genre"))}</td>
  <td class="num" data-v="{row['discovery_score']}"><strong>{row['discovery_score']:.1f}</strong></td>
  {components}
  <td>{esc(best.get("label", "–"))}</td>
  <td><span class="dim">{esc(lever.get("label", "–"))}</span></td>
  <td>{sparkline(row.get("spark_players") or [], color=genre_color(row.get("genre")))}</td>
</tr>"""
        )

    component_headers = "".join(
        f'<th class="num" data-sort="num" title="{esc(COMPONENT_HELP.get(c, ""))}">'
        f'{esc(COMPONENT_LABELS.get(c, c))}</th>'
        for c in COMPONENT_ORDER
    )
    leaderboard = f"""
<section class="panel">
  <h2>Discovery Fitness leaderboard</h2>
  <div class="sub">Click any column to re-sort. The component columns are what the total is made of —
  a high total with one red component is the most fixable island on this list.</div>
  <div class="tablewrap">
  <table data-sortable>
    <thead><tr>
      <th>#</th><th data-sort="str">Island</th><th data-sort="str">Genre</th>
      <th class="num" data-sort="num">Fitness</th>
      {component_headers}
      <th data-sort="str">Best-fit row</th><th data-sort="str">Weakest lever</th><th>7d players</th>
    </tr></thead>
    <tbody>{"".join(body_rows) or '<tr><td colspan="12" class="muted">No scored islands yet — run <code>fngg poll</code>.</td></tr>'}</tbody>
  </table>
  </div>
  {caveat_block()}
</section>
"""

    return head + stats_html + leaderboard + _row_matrix(dataset, scored)


def _row_matrix(dataset, scored: Sequence[dict]) -> str:
    """Who fits each Discover row best - the 'other tabs' view."""
    panels = []
    for archetype in ROW_ARCHETYPES:
        key = archetype["key"]
        if archetype["curated"]:
            panels.append(
                f"""<section class="panel">
  <h2>{esc(archetype['label'])} <span class="chip">curated</span></h2>
  <div class="sub">{esc(archetype['note'])}</div>
</section>"""
            )
            continue

        ranked = []
        for row in scored:
            entry = next((e for e in row.get("row_fit") or [] if e["key"] == key), None)
            if entry and entry["fit"] is not None and entry["eligible"]:
                ranked.append((entry["fit"], row))
        ranked.sort(key=lambda pair: -pair[0])

        items = "".join(
            f"""<div class="rowfit-item">
  <span class="rf-label">{island_link(row)}</span>
  {percentile_bar(fit, width=150, label=False)}
  <span class="rf-score">{fit:.0f}</span>
</div>"""
            for fit, row in ranked[:6]
        )
        drivers = " · ".join(
            f"{COMPONENT_LABELS.get(c, c)} {int(w * 100)}%" for c, w in archetype["weights"].items()
        )
        panels.append(
            f"""<section class="panel">
  <h2>{esc(archetype['label'])}</h2>
  <div class="sub">{esc(archetype['note'])}<br><span class="muted">Weighting: {esc(drivers)}</span></div>
  <div class="rowfit">{items or '<div class="muted">No eligible islands.</div>'}</div>
</section>"""
        )

    return f"""
<h3 style="margin:26px 0 12px">Row-by-row fit — who is built for which tab</h3>
<p class="lede" style="margin-bottom:14px">The Discover surface is a stack of rows and they do not
reward the same things. An island can be a lock for Community Choice and invisible in Trending at the
same time. Same measurements, re-weighted per row.</p>
<div class="grid two">{''.join(panels)}</div>
"""


# ------------------------------------------------------------------- Browse


BROWSE_COLUMNS = (
    ("unique_players", "Players"),
    ("peak_ccu", "Peak CCU"),
    ("minutes_per_player", "Min/player"),
    ("replays_per_player", "Sessions/pl"),
    ("retention_d1", "D1"),
    ("retention_d7", "D7"),
    ("favorites_rate", "Fav rate"),
    ("discovery_score", "Fitness"),
)


def page_browse(dataset, params: dict) -> str:
    genre = params.get("genre") or "all"
    query = params.get("q") or ""
    creator = params.get("creator") or ""
    sort = params.get("sort") or "unique_players"
    tracked_only = params.get("tracked") == "1"
    try:
        min_players = float(params.get("min") or 0)
    except ValueError:
        min_players = 0.0

    rows = dataset.filter(
        genre=None if genre == "all" else genre,
        query=query or None,
        creator=creator or None,
        tracked_only=tracked_only,
        min_players=min_players or None,
    )
    rows = [r for r in rows if r.get(sort) is not None] + [r for r in rows if r.get(sort) is None]
    rows.sort(key=lambda r: (r.get(sort) is None, -(r.get(sort) or 0)))

    genre_options = "".join(
        f'<option value="{esc(g["genre"])}"{" selected" if g["genre"] == genre else ""}>'
        f'{"★ " if g["focus"] else ""}{esc(g["label"])} ({g["count"]})</option>'
        for g in dataset.genre_counts()
    )
    sort_options = "".join(
        f'<option value="{esc(key)}"{" selected" if key == sort else ""}>{esc(label)}</option>'
        for key, label in BROWSE_COLUMNS
    )

    filters = f"""
<form class="filters" method="get" action="/browse">
  <input type="text" name="q" value="{esc(query)}" placeholder="Title, code or creator…" style="width:220px">
  <select name="genre"><option value="all">All genres</option>{genre_options}</select>
  <select name="sort">{sort_options}</select>
  <input type="number" name="min" value="{int(min_players) or ''}" placeholder="Min players" style="width:120px">
  <label class="chip"><input type="checkbox" name="tracked" value="1" {"checked" if tracked_only else ""}> tracked only</label>
  <button class="go" type="submit">Apply</button>
</form>
"""

    body_rows = []
    for row in rows[:300]:
        cells = "".join(
            f'<td class="num" data-v="{row.get(key) if row.get(key) is not None else -1}">'
            f"{format_kpi(key, row.get(key)) if key != 'discovery_score' else (f'{row[key]:.1f}' if row.get(key) is not None else '–')}</td>"
            for key, _ in BROWSE_COLUMNS
        )
        tags = "".join(f'<span class="tag">{esc(t)}</span> ' for t in (row.get("tags") or [])[:3])
        body_rows.append(
            f"""<tr>
  <td>{island_link(row)}<div style="margin-top:3px">{tags}</div></td>
  <td>{genre_chip(row.get("genre"))}</td>
  {cells}
  <td>{delta_span(row.get("growth_7d"))}</td>
  <td>{sparkline(row.get("spark_players") or [], color=genre_color(row.get("genre")))}</td>
</tr>"""
        )

    headers = "".join(f'<th class="num" data-sort="num">{esc(label)}</th>' for _, label in BROWSE_COLUMNS)
    return f"""
<div class="page-head"><div>
  <h1>Browse islands</h1>
  <p class="lede">Every island in your local catalogue with its latest reading. Filter to a genre to
  make the numbers comparable — cross-genre comparisons of session length or retention are noise.</p>
</div></div>
{filters}
<section class="panel">
  <div class="sub">{len(rows)} match{"es" if len(rows) != 1 else ""}{" — showing first 300" if len(rows) > 300 else ""}</div>
  <div class="tablewrap">
  <table data-sortable>
    <thead><tr><th data-sort="str">Island</th><th data-sort="str">Genre</th>{headers}
      <th class="num" data-sort="num">7d</th><th>Trend</th></tr></thead>
    <tbody>{"".join(body_rows) or '<tr><td colspan="12" class="muted">Nothing matches those filters.</td></tr>'}</tbody>
  </table>
  </div>
</section>
"""


# ------------------------------------------------------------------- Movers


def page_movers(dataset, params: dict) -> str:
    genre = params.get("genre") or "all"
    genre_filter = None if genre == "all" else genre
    try:
        floor = float(params.get("min") or 50)
    except ValueError:
        floor = 50.0

    rising = dataset.movers(limit=20, genre=genre_filter, rising=True, min_players=floor)
    falling = dataset.movers(limit=20, genre=genre_filter, rising=False, min_players=floor)

    def table(rows: Sequence[dict], caption: str, note: str) -> str:
        body = "".join(
            f"""<tr>
  <td>{island_link(row)}</td>
  <td>{genre_chip(row.get("genre"))}</td>
  <td class="num" data-v="{row.get('unique_players') or 0}">{format_kpi("unique_players", row.get("unique_players"))}</td>
  <td class="num" data-v="{row.get('growth_7d') or 0}">{delta_span(row.get("growth_7d"))}</td>
  <td class="num" data-v="{row.get('growth_ccu_7d') or 0}">{delta_span(row.get("growth_ccu_7d"))}</td>
  <td class="num" data-v="{row.get('rank_delta_7d') or 0}">{rank_delta_span(row.get("rank_delta_7d"))}</td>
  <td class="num" data-v="{(row.get('momentum_players') or {}).get('volatility') or 0}">
    {esc(f"{(row.get('momentum_players') or {}).get('volatility'):.2f}") if (row.get('momentum_players') or {}).get('volatility') is not None else '–'}</td>
  <td>{sparkline(row.get("spark_players") or [], color=genre_color(row.get("genre")))}</td>
</tr>"""
            for row in rows
        )
        return f"""<section class="panel">
  <h2>{esc(caption)}</h2>
  <div class="sub">{esc(note)}</div>
  <div class="tablewrap"><table data-sortable>
    <thead><tr><th data-sort="str">Island</th><th data-sort="str">Genre</th>
      <th class="num" data-sort="num">Players</th><th class="num" data-sort="num">7d players</th>
      <th class="num" data-sort="num">7d CCU</th><th class="num" data-sort="num">Rank Δ</th>
      <th class="num" data-sort="num" title="Standard deviation over mean — high means spiky, not durable">Volatility</th>
      <th>Trend</th></tr></thead>
    <tbody>{body or '<tr><td colspan="8" class="muted">Not enough history yet.</td></tr>'}</tbody>
  </table></div>
</section>"""

    return f"""
<div class="page-head"><div>
  <h1>Movers</h1>
  <p class="lede">Rate of change is what the Trending row keys off, and it is the one Discover signal
  a small island can win outright. Rank Δ counts places gained inside the whole catalogue; volatility
  separates a real climb from a single loud evening.</p>
</div><span class="spacer"></span>{genre_selector(genre, dataset.genre_counts(), action="/movers")}</div>
{warning_notes(dataset)}
{table(rising, "Rising", f"Biggest 7-day gains in unique players, islands above {floor:.0f} players.")}
{table(falling, "Falling", "Steepest declines — worth checking against your own update and event calendar.")}
"""


# ---------------------------------------------------------------- Retention


def page_retention(dataset, params: dict) -> str:
    genre = params.get("genre") or "all"
    rows = dataset.filter(genre=None if genre == "all" else genre)
    points = [
        {
            "x": r["retention_d1"] * 100,
            "y": r["retention_d7"] * 100,
            "label": r.get("title") or r["code"],
            "code": r["code"],
            "color": genre_color(r.get("genre")),
            "size": 3.5 + min((r.get("unique_players") or 0) ** 0.32 / 6, 9),
        }
        for r in rows
        if r.get("retention_d1") and r.get("retention_d7")
    ]

    ranked = [r for r in rows if r.get("d7_over_d1") is not None]
    ranked.sort(key=lambda r: -r["d7_over_d1"])

    body = "".join(
        f"""<tr>
  <td>{island_link(row)}</td><td>{genre_chip(row.get("genre"))}</td>
  <td class="num" data-v="{row.get('retention_d1') or 0}">{format_kpi("retention_d1", row.get("retention_d1"))}</td>
  <td class="num" data-v="{row.get('retention_d7') or 0}">{format_kpi("retention_d7", row.get("retention_d7"))}</td>
  <td class="num" data-v="{row.get('d7_over_d1') or 0}">{format_kpi("d7_over_d1", row.get("d7_over_d1"))}</td>
  <td>{percentile_bar((row.get("percentiles") or {}).get("retention_d7"), width=110)}</td>
  <td class="num" data-v="{row.get('unique_players') or 0}">{format_kpi("unique_players", row.get("unique_players"))}</td>
</tr>"""
        for row in ranked[:50]
    )

    return f"""
<div class="page-head"><div>
  <h1>Retention</h1>
  <p class="lede">Return rate is the signal that separates an island people played once from one they
  came back to, and it is the heaviest weight in the personalised Discover rows. The ratio that
  matters most is D7 ÷ D1 — how much of your day-one audience survives the week.</p>
</div><span class="spacer"></span>{genre_selector(genre, dataset.genre_counts(), action="/retention")}</div>
<section class="panel">
  <h2>D1 against D7</h2>
  <div class="sub">Bubble size is audience. Top-right is a durable loop; bottom-right is a strong hook
  that leaks players inside the first week — usually a content-depth problem, not a marketing one.</div>
  {scatter(points, x_label="Day-1 retention (%)", y_label="Day-7 retention (%)",
           quadrant_labels=("Slow burn", "Durable loop", "Weak start", "Hook, then leak"))}
  {genre_legend([r.get("genre") for r in rows if r.get("retention_d1") and r.get("retention_d7")], GENRE_LABELS)}
</section>
<section class="panel">
  <h2>Curve hold — best D7 ÷ D1</h2>
  <div class="sub">Islands that keep the most of their day-one audience through day seven.</div>
  <div class="tablewrap"><table data-sortable>
    <thead><tr><th data-sort="str">Island</th><th data-sort="str">Genre</th>
      <th class="num" data-sort="num">D1</th><th class="num" data-sort="num">D7</th>
      <th class="num" data-sort="num">D7/D1</th><th>D7 vs cohort</th>
      <th class="num" data-sort="num">Players</th></tr></thead>
    <tbody>{body or '<tr><td colspan="7" class="muted">No retention data yet.</td></tr>'}</tbody>
  </table></div>
</section>
"""


# --------------------------------------------------------------- Engagement


def page_engagement(dataset, params: dict) -> str:
    genre = params.get("genre") or "all"
    rows = dataset.filter(genre=None if genre == "all" else genre)

    points = [
        {
            "x": r["minutes_per_player"],
            "y": r["replays_per_player"],
            "label": r.get("title") or r["code"],
            "code": r["code"],
            "color": genre_color(r.get("genre")),
            "size": 3.5 + min((r.get("unique_players") or 0) ** 0.32 / 6, 9),
        }
        for r in rows
        if r.get("minutes_per_player") and r.get("replays_per_player")
    ]

    hours = [
        {
            "x": r["unique_players"],
            "y": r["player_hours"],
            "label": r.get("title") or r["code"],
            "code": r["code"],
            "color": genre_color(r.get("genre")),
        }
        for r in rows
        if r.get("unique_players") and r.get("player_hours")
    ]

    return f"""
<div class="page-head"><div>
  <h1>Engagement shape</h1>
  <p class="lede">Two islands with identical player counts can be completely different businesses.
  This is the axis that separates them: an RP city earns its minutes from one very long session,
  an FFA map from many short ones. Both work — but they qualify for different Discover rows and
  should never be benchmarked against each other.</p>
</div><span class="spacer"></span>{genre_selector(genre, dataset.genre_counts(), action="/engagement")}</div>
<section class="panel">
  <h2>Session length against sessions per player</h2>
  <div class="sub">Bottom-right is the roleplay / open-world signature: long single sessions.
  Top-left is the arena signature: short rounds, played repeatedly. Bottom-left is the danger
  zone — short sessions that nobody repeats.</div>
  {scatter(points, x_label="Minutes per player", y_label="Sessions per player",
           quadrant_labels=("Fast repeat loop", "Deep and repeated", "Bounce risk", "Long single session"))}
  {genre_legend([r.get("genre") for r in rows if r.get("minutes_per_player") and r.get("replays_per_player")], GENRE_LABELS)}
</section>
<section class="panel">
  <h2>Audience against total player hours</h2>
  <div class="sub">Total minutes is what the Most Played row runs on, and it is where long-session
  genres punch above their headcount. Islands above the trend earn more hours per player than their
  size implies.</div>
  {scatter(hours, x_label="Unique players (log)", y_label="Player hours", x_log=True)}
  {genre_legend([r.get("genre") for r in rows if r.get("unique_players") and r.get("player_hours")], GENRE_LABELS)}
</section>
"""


# ---------------------------------------------------------------- Benchmarks


BENCHMARK_METRICS = (
    "unique_players", "peak_ccu", "minutes_per_player", "minutes_per_play",
    "replays_per_player", "retention_d1", "retention_d7", "d7_over_d1",
    "favorites_rate", "recommend_rate",
)


def page_cohorts(dataset, params: dict) -> str:
    genre = params.get("genre") or (FOCUS_GENRES[0] if FOCUS_GENRES else "all")
    stats_rows = dataset.cohorts.summary_table(genre, BENCHMARK_METRICS)
    cohort_key = dataset.cohorts.resolve_key(genre, "unique_players")

    body = "".join(
        f"""<tr>
  <td>{esc(KPI_LABELS.get(entry["metric"], entry["metric"]))}
      <div class="muted" style="font-size:11px">{esc(KPI_HELP.get(entry["metric"], ""))}</div></td>
  <td class="num">{entry["count"]}</td>
  <td class="num">{esc(format_kpi(entry["metric"], entry.get("p10")))}</td>
  <td class="num">{esc(format_kpi(entry["metric"], entry.get("p25")))}</td>
  <td class="num"><strong>{esc(format_kpi(entry["metric"], entry.get("p50")))}</strong></td>
  <td class="num">{esc(format_kpi(entry["metric"], entry.get("p75")))}</td>
  <td class="num">{esc(format_kpi(entry["metric"], entry.get("p90")))}</td>
</tr>"""
        for entry in stats_rows
    )

    fallback_note = ""
    if cohort_key != genre:
        pretty = "all islands" if cohort_key == "__all__" else cohort_key.replace("family:", "")
        fallback_note = (
            f'<div class="note warn">Not enough {esc(label_of(genre))} islands in your database for a '
            f'meaningful cohort, so these numbers fall back to <strong>{esc(pretty)}</strong>. '
            f"Sync more of the catalogue to sharpen them.</div>"
        )

    return f"""
<div class="page-head"><div>
  <h1>Benchmarks</h1>
  <p class="lede">What "good" looks like, per genre. Read your own island against the p50 column
  first, then p75 — the gap to p75 is what the Discovery lever list is quietly measuring.</p>
</div><span class="spacer"></span>{genre_selector(genre, dataset.genre_counts(), action="/cohorts")}</div>
{fallback_note}
<section class="panel">
  <h2>{esc(label_of(genre))} percentiles</h2>
  <div class="sub">Computed from the islands in your local database — the more of the catalogue you
  sync, the closer these get to the real distribution.</div>
  <div class="tablewrap"><table>
    <thead><tr><th>Metric</th><th class="num">n</th><th class="num">p10</th><th class="num">p25</th>
      <th class="num">Median</th><th class="num">p75</th><th class="num">p90</th></tr></thead>
    <tbody>{body or '<tr><td colspan="7" class="muted">No data for this cohort yet.</td></tr>'}</tbody>
  </table></div>
</section>
"""


# ------------------------------------------------------------------ Compare


def page_compare(dataset, params: dict) -> str:
    codes = [c.strip() for c in (params.get("codes") or "").split(",") if c.strip()]
    selected = [row for row in (dataset.get(code) for code in codes) if row]

    form = f"""
<form class="filters" method="get" action="/compare">
  <input type="text" name="codes" value="{esc(','.join(codes))}"
         placeholder="1234-5678-9012,2345-6789-0123" style="width:420px">
  <button class="go" type="submit">Compare</button>
</form>"""

    if not selected:
        suggestions = "".join(
            f'<a class="chip" href="/compare?codes={esc(r["code"])}" style="margin:3px">{esc(r.get("title") or r["code"])}</a>'
            for r in dataset.rows[:12]
        )
        return f"""
<div class="page-head"><div><h1>Compare</h1>
<p class="lede">Put two or more islands side by side on the same cohort percentiles. Most useful
against direct competitors in your own genre, where absolute numbers mislead but percentile gaps
do not.</p></div></div>
{form}
<section class="panel"><h2>Start from a top island</h2>
<div class="sub">Add more codes to the box above, comma separated.</div>{suggestions}</section>"""

    header = "".join(
        f'<th class="num">{island_link(row)}<br>{genre_chip(row.get("genre"))}</th>' for row in selected
    )
    metric_rows = []
    for metric in KPIS:
        cells = "".join(
            f'<td class="num">{esc(format_kpi(metric, row.get(metric)))}'
            f'<div>{percentile_bar((row.get("percentiles") or {}).get(metric), width=80, label=False)}</div></td>'
            for row in selected
        )
        metric_rows.append(
            f'<tr><td>{esc(KPI_LABELS.get(metric, metric))}</td>{cells}</tr>'
        )

    component_rows = []
    for component in COMPONENT_ORDER:
        cells = "".join(
            f'<td class="num">{percentile_bar((row.get("discovery_components") or {}).get(component), width=90)}</td>'
            for row in selected
        )
        component_rows.append(f'<tr><td>{esc(COMPONENT_LABELS[component])}</td>{cells}</tr>')

    fitness = "".join(
        f'<td class="num"><strong>{row["discovery_score"]:.1f}</strong></td>'
        if row.get("discovery_score") is not None
        else '<td class="num">–</td>'
        for row in selected
    )

    series = [
        {
            "label": row.get("title") or row["code"],
            "color": genre_color(row.get("genre")),
            "points": row.get("series_players") or [],
        }
        for row in selected
    ]

    return f"""
<div class="page-head"><div><h1>Compare</h1>
<p class="lede">Percentile bars are against each island's own genre cohort, so a bar reads the same
way for an RP city and an FFA arena even when the raw numbers are orders of magnitude apart.</p>
</div></div>
{form}
<section class="panel">
  <h2>Discovery components</h2>
  <div class="sub">Cohort percentile per component, plus the weighted total.</div>
  <div class="tablewrap"><table>
    <thead><tr><th>Component</th>{header}</tr></thead>
    <tbody>{''.join(component_rows)}<tr><td><strong>Discovery Fitness</strong></td>{fitness}</tr></tbody>
  </table></div>
</section>
<section class="panel">
  <h2>Players over time</h2>
  <div class="sub">Absolute counts, so genres at very different scales will not share
  a readable axis — the percentile tables above are the fair comparison.</div>
  {line_chart(series, y_label="unique players")}
</section>
<section class="panel">
  <h2>Metric by metric</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>Metric</th>{header}</tr></thead>
    <tbody>{''.join(metric_rows)}</tbody>
  </table></div>
</section>
"""


# ------------------------------------------------------------- island detail


def page_island(dataset, row: dict, history: Sequence[dict], gg_sample: Optional[dict],
                placements: Sequence[dict]) -> str:
    score = row.get("discovery")
    genre = row.get("genre")

    lever_bars = bar_chart(
        [
            {
                "label": lever["label"],
                "value": lever["upside"],
                "color": genre_color(genre),
                "display": f"+{lever['upside']:.1f}",
                "note": f"currently p{lever['percentile']:.0f}, weighted {lever['weight']:.2f}",
            }
            for lever in (row.get("discovery_levers") or [])
        ],
    )

    component_rows = "".join(
        f"""<div class="kpirow">
  <span class="kl" title="{esc(COMPONENT_HELP.get(c, ""))}">{esc(COMPONENT_LABELS[c])}</span>
  <span class="kv">{esc(f"{(row.get('discovery_components') or {}).get(c):.0f}") if (row.get('discovery_components') or {}).get(c) is not None else "–"}</span>
  {percentile_bar((row.get("discovery_components") or {}).get(c), width=140, label=False)}
</div>"""
        for c in COMPONENT_ORDER
    )

    kpi_rows = "".join(
        f"""<div class="kpirow">
  <span class="kl" title="{esc(KPI_HELP.get(k, ""))}">{esc(KPI_LABELS[k])}</span>
  <span class="kv">{esc(format_kpi(k, row.get(k)))}</span>
  {percentile_bar((row.get("percentiles") or {}).get(k), width=140) if k not in NEUTRAL_KPIS else '<span class="muted" style="font-size:11px">neutral</span>'}
</div>"""
        for k in KPIS
    )

    fit_items = "".join(
        f"""<div class="rowfit-item {"curated" if entry["curated"] else ""}">
  <span class="rf-label">{esc(entry["label"])}</span>
  {percentile_bar(entry["fit"], width=170, label=False) if entry["fit"] is not None else '<span class="muted">not modelled</span>'}
  <span class="rf-score">{f"{entry['fit']:.0f}" if entry["fit"] is not None else "–"}</span>
  <span class="rf-note">{esc(entry["note"])}</span>
</div>"""
        for entry in (row.get("row_fit") or [])
    )

    def series_for(metric: str, label: str, color: str) -> dict:
        return {
            "label": label,
            "color": color,
            "points": [(str(h["captured_at"])[:10], h.get(metric)) for h in history],
        }

    players_chart = line_chart(
        [series_for("unique_players", "Unique players", genre_color(genre)),
         series_for("peak_ccu", "Peak CCU", "var(--accent)")],
        y_label="players",
    )
    retention_chart = line_chart(
        [{"label": "D1", "color": "#3fb8a0",
          "points": [(str(h["captured_at"])[:10], (h.get("retention_d1") or 0) * 100) for h in history]},
         {"label": "D7", "color": "#f2725c",
          "points": [(str(h["captured_at"])[:10], (h.get("retention_d7") or 0) * 100) for h in history]}],
        y_label="retention %",
    )
    depth_chart = line_chart(
        [series_for("minutes_per_player", "Minutes / player", "#8b7bf7"),
         series_for("minutes_per_play", "Minutes / session", "#e8a33d")],
        y_label="minutes",
    )

    live = ""
    if gg_sample:
        live = stat("Live now (fortnite.gg)", compact(gg_sample.get("ccu")),
                    f"sampled {esc(str(gg_sample.get('observed_at'))[:16])}")

    placement_html = ""
    if placements:
        items = "".join(
            f'<div class="rowfit-item"><span class="rf-label">{esc(p.get("row_label") or p.get("row_key"))}</span>'
            f'<span class="dim">position {esc(p.get("position"))}</span>'
            f'<span class="rf-score">{esc(str(p.get("observed_at"))[:10])}</span></div>'
            for p in list(placements)[-8:][::-1]
        )
        placement_html = f"""<section class="panel">
  <h2>Observed Discover placements</h2>
  <div class="sub">Rows this island was actually seen in, newest first.</div>
  <div class="rowfit">{items}</div>
</section>"""

    top_lever = row.get("discovery_top_lever")
    verdict = ""
    if top_lever:
        verdict = (
            f'<div class="note"><strong>Biggest lever: {esc(top_lever["label"])}.</strong> '
            f'Sitting at p{top_lever["percentile"]:.0f} in the {esc(label_of(genre))} cohort, and it carries '
            f'{top_lever["weight"]:.0%} of the weight for this genre. Pulling it to the cohort\'s top quartile '
            f'is worth about {top_lever["upside"]:.1f} points of fitness — more than any other single move. '
            f'{esc(COMPONENT_HELP.get(top_lever["component"], ""))}</div>'
        )

    tags = "".join(f'<span class="tag">{esc(t)}</span> ' for t in (row.get("tags") or []))
    confidence = row.get("genre_confidence")
    genre_note = (
        f'<span class="muted" style="font-size:11.5px">classified from {esc(row.get("genre_source"))}'
        + (f", confidence {confidence:.0%}" if confidence else "")
        + "</span>"
    )

    return f"""
<div class="panel maphead">
  <div>{score_dial(row.get("discovery_score"))}
    <div class="muted" style="text-align:center;font-size:11px;margin-top:2px">FITNESS</div></div>
  <div class="idblock">
    <h1>{esc(row.get("title") or "(untitled)")}</h1>
    <div class="dim mono" style="margin:4px 0 8px">{esc(row.get("code"))}
      {" · " + esc(row.get("creator_code")) if row.get("creator_code") else ""}</div>
    <div>{genre_chip(genre)} {tags}</div>
    <div style="margin-top:6px">{genre_note}</div>
  </div>
  <div class="grid three" style="flex:2;min-width:300px">
    {stat("Players", format_kpi("unique_players", row.get("unique_players")),
          f"rank {row.get('genre_rank')} of {row.get('genre_size')} in {label_of(genre)}" if row.get("genre_rank") else "")}
    {stat("Peak CCU", format_kpi("peak_ccu", row.get("peak_ccu")), "")}
    {stat("7d trend", f'{(row.get("growth_7d") or 0) * 100:+.1f}%' if row.get("growth_7d") is not None else "–",
          esc(row.get("direction") or ""))}
    {live}
  </div>
</div>
{verdict}
<div class="grid two">
  <section class="panel">
    <h2>Discovery components</h2>
    <div class="sub">Percentile against {esc(label_of(genre))} islands
      (cohort of {score.cohort_size if score else 0}).</div>
    <div class="kpigrid">{component_rows}</div>
    {caveat_block()}
  </section>
  <section class="panel">
    <h2>Where the points are</h2>
    <div class="sub">Fitness gained by lifting each component to the cohort's 75th percentile.
    Longest bar first.</div>
    {lever_bars}
  </section>
</div>
<section class="panel">
  <h2>Audience over time</h2>
  <div class="sub">Only covers the period you have been polling — Epic does not backfill.</div>
  {players_chart}
</section>
<div class="grid two">
  <section class="panel"><h2>Retention</h2>{retention_chart}</section>
  <section class="panel"><h2>Session depth</h2>{depth_chart}</section>
</div>
<section class="panel">
  <h2>Discover row fit</h2>
  <div class="sub">The same measurements re-weighted for each row's documented behaviour.</div>
  <div class="rowfit">{fit_items}</div>
</section>
{placement_html}
<section class="panel">
  <h2>All metrics vs cohort</h2>
  <div class="tablewrap"><div class="kpigrid">{kpi_rows}</div></div>
</section>
"""


# ------------------------------------------------------------------- status


def page_status(dataset, db_stats: dict, runs: Sequence[dict], gg_report: Optional[dict]) -> str:
    run_rows = "".join(
        f"""<tr><td class="mono">{esc(str(r.get("started_at"))[:19])}</td>
  <td>{esc(r.get("kind"))}</td>
  <td class="num">{esc(r.get("ok"))}</td>
  <td class="num">{esc(r.get("failed"))}</td>
  <td class="dim">{esc(r.get("notes") or "")}</td></tr>"""
        for r in runs
    )

    gg_html = '<div class="muted">Not probed yet. Run <code>fngg probe</code>.</div>'
    if gg_report:
        blocks = []
        for kind, attempts in (gg_report.get("strategies") or {}).items():
            items = "".join(
                f'<div class="kpirow"><span class="kl mono" style="font-size:11px">{esc(a["url"])}</span>'
                f'<span class="kv" style="color:{"var(--good)" if a["ok"] else "var(--bad)"}">'
                f'{"ok" if a["ok"] else "fail"}</span>'
                f'<span class="muted" style="font-size:11px">{esc(a.get("detail", ""))[:70]}</span></div>'
                for a in attempts
            )
            blocks.append(f'<h3 style="margin:10px 0 6px">{esc(kind)}</h3>{items}')
        state = "usable" if gg_report.get("usable") else "not reachable"
        gg_html = (
            f'<div class="note {"" if gg_report.get("usable") else "warn"}">fortnite.gg is '
            f"<strong>{esc(state)}</strong> from this machine, checked "
            f'{esc(str(gg_report.get("checked_at"))[:19])}.</div>' + "".join(blocks)
        )

    history_days = db_stats.get("history_days", 0)
    history_note = (
        "Enough history for trend analysis."
        if history_days >= 3
        else "Momentum and rank deltas need roughly three days of polling before they mean anything."
    )

    return f"""
<div class="page-head"><div><h1>Status</h1>
<p class="lede">What is in the local database and where it came from.</p></div></div>
<div class="grid four">
  {stat("Islands", f"{db_stats.get('islands', 0):,}", "in local catalogue")}
  {stat("Snapshots", f"{db_stats.get('snapshots', 0):,}", "append-only readings")}
  {stat("History", f"{history_days:.1f}d", history_note)}
  {stat("Tracked", f"{db_stats.get('tracked', 0):,}", "polled first every run")}
</div>
<div class="note"><strong>Why history matters here.</strong> Epic's Ecosystem API returns one live
reading per metric and rejects requests for data older than about six days. A day you did not poll is
a day nobody can reconstruct later — not this tool, not any other. Keep <code>fngg watch</code>
running, or schedule <code>fngg poll</code> daily.</div>
<section class="panel">
  <h2>Recent runs</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>Started</th><th>Kind</th><th class="num">OK</th><th class="num">Failed</th><th>Notes</th></tr></thead>
    <tbody>{run_rows or '<tr><td colspan="5" class="muted">No runs recorded yet.</td></tr>'}</tbody>
  </table></div>
</section>
<section class="panel">
  <h2>fortnite.gg adapter</h2>
  <div class="sub">Optional source for live concurrency and observed Discover rows. Everything else
  works without it.</div>
  {gg_html}
</section>
<section class="panel">
  <h2>Database</h2>
  <div class="kpirow"><span class="kl">Path</span><span class="kv mono">{esc(db_stats.get("db_path"))}</span><span></span></div>
  <div class="kpirow"><span class="kl">fortnite.gg samples</span><span class="kv">{esc(db_stats.get("gg_samples", 0))}</span><span></span></div>
  <div class="kpirow"><span class="kl">Discover placements</span><span class="kv">{esc(db_stats.get("placements", 0))}</span><span></span></div>
</section>
"""


def page_error(message: str, detail: str = "") -> str:
    return f"""
<div class="page-head"><div><h1>{esc(message)}</h1>
<p class="lede">{esc(detail)}</p></div></div>
<section class="panel"><a href="/">← Back to Discovery</a></section>"""
