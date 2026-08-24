"""Server-rendered SVG charts.

Charts are generated as inline SVG rather than handed to a JS library so the
dashboard has no external dependencies, works offline, and renders identically
when a page is saved or printed. Every chart is theme-aware: colours come from
CSS custom properties defined in assets.py, so light and dark both work without
re-rendering.
"""

from __future__ import annotations

import html
import math
from typing import Optional, Sequence

# Categorical palette. Chosen to stay distinguishable for the common forms of
# colour vision deficiency and to hold up on both light and dark backgrounds.
GENRE_COLORS = {
    "rp": "#8b7bf7",
    "ffa": "#f2725c",
    "open_world": "#3fb8a0",
    "box_fight": "#e8a33d",
    "zone_wars": "#d9739f",
    "practice": "#5fa8e8",
    "tycoon": "#b0995f",
    "horror": "#9b6bd6",
    "parkour": "#5cc98a",
    "puzzle": "#7f8fa6",
    "racing": "#e07a5f",
    "pve": "#4f9d8f",
    "party": "#c98ac9",
    "hide_and_seek": "#8aa3c9",
    "prop_hunt": "#a3b86c",
    "battle_royale": "#6c8ebf",
    "music": "#cf87b8",
    "other": "#8b93a3",
}

DEFAULT_COLOR = "var(--accent)"


def genre_color(genre: Optional[str]) -> str:
    return GENRE_COLORS.get(genre or "other", GENRE_COLORS["other"])


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _nice_bounds(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    lo, hi = min(values), max(values)
    non_negative = lo >= 0
    if lo == hi:
        pad = abs(lo) * 0.1 or 1.0
    else:
        pad = (hi - lo) * 0.08
    lo -= pad
    hi += pad
    # Padding must not invent negative values for a metric that cannot go there.
    if non_negative and lo < 0:
        lo = 0.0
    return lo, hi


def compact(value: Optional[float]) -> str:
    if value is None:
        return "–"
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            return f"{value / limit:.1f}{suffix}"
    if abs(value) < 10 and value != int(value):
        return f"{value:.2f}"
    return f"{value:,.0f}"


# ------------------------------------------------------------------ sparkline


def sparkline(
    values: Sequence[float],
    *,
    width: int = 110,
    height: int = 28,
    color: str = DEFAULT_COLOR,
    fill: bool = True,
) -> str:
    """Tiny trend line for table rows."""
    points = [v for v in values if v is not None]
    if len(points) < 2:
        return f'<svg class="spark" width="{width}" height="{height}" role="presentation"></svg>'

    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    step = width / (len(points) - 1)
    coords = [
        (i * step, height - 2 - ((v - lo) / span) * (height - 4)) for i, v in enumerate(points)
    ]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))
    area = ""
    if fill:
        area = (
            f'<path d="{path} L{coords[-1][0]:.1f},{height} L0,{height} Z" '
            f'fill="{color}" opacity="0.13" stroke="none"/>'
        )
    last_x, last_y = coords[-1]
    return (
        f'<svg class="spark" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="trend">{area}'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.1" fill="{color}"/></svg>'
    )


# ---------------------------------------------------------------- percentile


def percentile_bar(pct: Optional[float], *, width: int = 120, label: bool = True) -> str:
    """Horizontal 0-100 percentile bar with a median tick."""
    if pct is None:
        return '<span class="muted">–</span>'
    pct = max(0.0, min(100.0, float(pct)))
    tone = "low" if pct < 33 else ("mid" if pct < 66 else "high")
    text = f'<span class="pctlabel">p{pct:.0f}</span>' if label else ""
    return (
        f'<span class="pctbar" style="--w:{width}px" title="{pct:.1f}th percentile in cohort">'
        f'<span class="pcttrack"><span class="pctfill {tone}" style="width:{pct:.1f}%"></span>'
        f'<span class="pcttick"></span></span>{text}</span>'
    )


def score_dial(score: Optional[float], *, size: int = 92) -> str:
    """Radial gauge for the headline Discovery Fitness score."""
    if score is None:
        return '<div class="dial empty">no data</div>'
    score = max(0.0, min(100.0, float(score)))
    radius = size / 2 - 7
    circumference = 2 * math.pi * radius
    filled = circumference * (score / 100.0)
    tone = "low" if score < 33 else ("mid" if score < 66 else "high")
    center = size / 2
    return f"""<svg class="dial {tone}" width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="Discovery fitness {score:.0f} of 100">
  <circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="var(--track)" stroke-width="7"/>
  <circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="currentColor" stroke-width="7"
          stroke-linecap="round" stroke-dasharray="{filled:.2f} {circumference:.2f}"
          transform="rotate(-90 {center} {center})"/>
  <text x="{center}" y="{center + 1}" text-anchor="middle" dominant-baseline="middle"
        class="dialnum">{score:.0f}</text>
</svg>"""


# --------------------------------------------------------------- line chart


def line_chart(
    series: Sequence[dict],
    *,
    width: int = 1200,
    height: int = 260,
    y_label: str = "",
    show_legend: bool = True,
) -> str:
    """Multi-series line chart.

    series: [{"label": str, "color": str, "points": [(iso_ts, value), ...]}]
    """
    usable = [s for s in series if len([p for p in s.get("points", []) if p[1] is not None]) >= 2]
    if not usable:
        return '<div class="chart-empty">Not enough history yet — this fills in as you poll.</div>'

    pad_l, pad_r, pad_t, pad_b = 52, 14, 14, 26
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    all_values = [p[1] for s in usable for p in s["points"] if p[1] is not None]
    lo, hi = _nice_bounds(all_values)
    span = (hi - lo) or 1.0

    labels = sorted({p[0] for s in usable for p in s["points"]})
    index = {label: i for i, label in enumerate(labels)}
    steps = max(len(labels) - 1, 1)

    def x_of(label: str) -> float:
        return pad_l + (index[label] / steps) * plot_w

    def y_of(value: float) -> float:
        return pad_t + plot_h - ((value - lo) / span) * plot_h

    parts = [
        f'<svg class="linechart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="{_esc(y_label or "chart")}">'
    ]

    # Gridlines + y axis labels
    for i in range(5):
        value = lo + (span * i / 4)
        y = y_of(value)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
            f'class="grid"/>'
            f'<text x="{pad_l - 8}" y="{y + 3.5:.1f}" text-anchor="end" class="axis">'
            f"{_esc(compact(value))}</text>"
        )

    # X axis: first, middle and last tick only - dense date labels are unreadable.
    for label in ({labels[0], labels[len(labels) // 2], labels[-1]} if len(labels) > 2 else set(labels)):
        parts.append(
            f'<text x="{x_of(label):.1f}" y="{height - 8}" text-anchor="middle" class="axis">'
            f"{_esc(label[5:10] if len(label) >= 10 else label)}</text>"
        )

    for s in usable:
        color = s.get("color") or DEFAULT_COLOR
        points = [(p[0], p[1]) for p in s["points"] if p[1] is not None]
        path = " ".join(
            f"{'M' if i == 0 else 'L'}{x_of(label):.1f},{y_of(value):.1f}"
            for i, (label, value) in enumerate(points)
        )
        parts.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for label, value in points:
            parts.append(
                f'<circle cx="{x_of(label):.1f}" cy="{y_of(value):.1f}" r="2.4" fill="{color}">'
                f"<title>{_esc(s.get('label',''))} · {_esc(label[:10])} · {_esc(compact(value))}</title>"
                f"</circle>"
            )

    parts.append("</svg>")

    if show_legend and len(usable) > 1:
        chips = "".join(
            f'<span class="legend-item"><i style="background:{s.get("color") or DEFAULT_COLOR}"></i>'
            f"{_esc(s.get('label',''))}</span>"
            for s in usable
        )
        parts.append(f'<div class="legend">{chips}</div>')

    return "".join(parts)


# ------------------------------------------------------------------ scatter


def scatter(
    points: Sequence[dict],
    *,
    width: int = 1000,
    height: int = 460,
    x_label: str = "",
    y_label: str = "",
    x_log: bool = False,
    quadrant_labels: Optional[tuple[str, str, str, str]] = None,
) -> str:
    """Scatter plot. points: [{x, y, label, color, code, size}]"""
    usable = [p for p in points if p.get("x") is not None and p.get("y") is not None]
    if len(usable) < 2:
        return '<div class="chart-empty">Not enough islands with both metrics yet.</div>'

    pad_l, pad_r, pad_t, pad_b = 56, 16, 18, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def tx(value: float) -> float:
        return math.log10(max(value, 1e-6)) if x_log else value

    xs = [tx(p["x"]) for p in usable]
    ys = [p["y"] for p in usable]
    x_lo, x_hi = _nice_bounds(xs)
    y_lo, y_hi = _nice_bounds(ys)
    x_span = (x_hi - x_lo) or 1.0
    y_span = (y_hi - y_lo) or 1.0

    def x_of(value: float) -> float:
        return pad_l + ((tx(value) - x_lo) / x_span) * plot_w

    def y_of(value: float) -> float:
        return pad_t + plot_h - ((value - y_lo) / y_span) * plot_h

    parts = [
        f'<svg class="scatter" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="{_esc(y_label)} versus {_esc(x_label)}">'
    ]

    for i in range(5):
        y = pad_t + plot_h * i / 4
        value = y_hi - (y_span * i / 4)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" class="grid"/>'
            f'<text x="{pad_l - 8}" y="{y + 3.5:.1f}" text-anchor="end" class="axis">'
            f"{_esc(compact(value))}</text>"
        )
        x = pad_l + plot_w * i / 4
        xv = x_lo + (x_span * i / 4)
        shown = 10**xv if x_log else xv
        parts.append(
            f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + plot_h}" class="grid"/>'
            f'<text x="{x:.1f}" y="{height - 20}" text-anchor="middle" class="axis">'
            f"{_esc(compact(shown))}</text>"
        )

    # Median crosshair splits the plot into the four quadrants creators care about.
    if quadrant_labels:
        mid_x = pad_l + plot_w / 2
        mid_y = pad_t + plot_h / 2
        parts.append(
            f'<line x1="{mid_x}" y1="{pad_t}" x2="{mid_x}" y2="{pad_t + plot_h}" class="quadline"/>'
            f'<line x1="{pad_l}" y1="{mid_y}" x2="{width - pad_r}" y2="{mid_y}" class="quadline"/>'
        )
        tl, tr, bl, br = quadrant_labels
        parts.append(
            f'<text x="{pad_l + 8}" y="{pad_t + 14}" class="quadlabel">{_esc(tl)}</text>'
            f'<text x="{width - pad_r - 8}" y="{pad_t + 14}" text-anchor="end" class="quadlabel">{_esc(tr)}</text>'
            f'<text x="{pad_l + 8}" y="{pad_t + plot_h - 6}" class="quadlabel">{_esc(bl)}</text>'
            f'<text x="{width - pad_r - 8}" y="{pad_t + plot_h - 6}" text-anchor="end" class="quadlabel">{_esc(br)}</text>'
        )

    for p in usable:
        radius = float(p.get("size") or 4.5)
        color = p.get("color") or DEFAULT_COLOR
        code = p.get("code")
        circle = (
            f'<circle cx="{x_of(p["x"]):.1f}" cy="{y_of(p["y"]):.1f}" r="{radius:.1f}" '
            f'fill="{color}" fill-opacity="0.62" stroke="{color}" stroke-width="1">'
            f'<title>{_esc(p.get("label",""))}\n{_esc(x_label)}: {_esc(compact(p["x"]))}\n'
            f'{_esc(y_label)}: {_esc(compact(p["y"]))}</title></circle>'
        )
        parts.append(f'<a href="/island/{_esc(code)}">{circle}</a>' if code else circle)

    parts.append(
        f'<text x="{pad_l + plot_w / 2:.0f}" y="{height - 4}" text-anchor="middle" '
        f'class="axistitle">{_esc(x_label)}</text>'
        f'<text x="14" y="{pad_t + plot_h / 2:.0f}" text-anchor="middle" class="axistitle" '
        f'transform="rotate(-90 14 {pad_t + plot_h / 2:.0f})">{_esc(y_label)}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- bar chart


def bar_chart(items: Sequence[dict], *, width: int = 300, max_value: Optional[float] = None) -> str:
    """Horizontal bars. items: [{label, value, color, note}]"""
    usable = [i for i in items if i.get("value") is not None]
    if not usable:
        return '<div class="chart-empty">No data.</div>'
    top = max_value or max(abs(float(i["value"])) for i in usable) or 1.0
    rows = []
    for item in usable:
        value = float(item["value"])
        color = item.get("color") or DEFAULT_COLOR
        note = f'<span class="barnote">{_esc(item["note"])}</span>' if item.get("note") else ""
        if value <= 0:
            # Nothing to gain here - say so rather than drawing a zero-width bar.
            rows.append(
                f'<div class="barrow done"><span class="barlabel">{_esc(item["label"])}</span>'
                f'<span class="barmet">already at or above the cohort target</span>'
                f'<span class="barvalue">✓</span>{note}</div>'
            )
            continue
        pct = min(abs(value) / top * 100.0, 100.0)
        rows.append(
            f'<div class="barrow"><span class="barlabel">{_esc(item["label"])}</span>'
            f'<span class="bartrack"><span class="barfill" style="width:{pct:.1f}%;background:{color}"></span></span>'
            f'<span class="barvalue">{_esc(item.get("display") or compact(value))}</span>{note}</div>'
        )
    return f'<div class="barchart" style="--barw:{width}px">' + "".join(rows) + "</div>"


def genre_legend(genres: Sequence[str], labels: dict) -> str:
    """Colour key for scatter plots, listing only the genres actually plotted."""
    seen = []
    for genre in genres:
        if genre not in seen:
            seen.append(genre)
    if len(seen) < 2:
        return ""
    chips = "".join(
        f'<span class="legend-item"><i style="background:{genre_color(g)};'
        f'width:9px;height:9px;border-radius:50%"></i>{_esc(labels.get(g, g))}</span>'
        for g in seen
    )
    return f'<div class="legend">{chips}</div>'


__all__ = [
    "GENRE_COLORS",
    "genre_color",
    "compact",
    "sparkline",
    "percentile_bar",
    "score_dial",
    "line_chart",
    "scatter",
    "bar_chart",
    "genre_legend",
]
