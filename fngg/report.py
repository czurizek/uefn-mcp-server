"""Text reports shared by the CLI and the MCP tools.

The dashboard is for browsing; these are for answering a specific question in a
terminal or handing a compact, already-interpreted answer to an assistant.
Same numbers, same cohorts - only the presentation differs.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .analytics.discovery import COMPONENT_HELP, COMPONENT_LABELS
from .analytics.kpis import KPI_LABELS, KPIS, format_kpi
from .genres import label_of

BAR_WIDTH = 22


def bar(pct: Optional[float], width: int = BAR_WIDTH) -> str:
    if pct is None:
        return "·" * width
    filled = int(round(max(0.0, min(100.0, pct)) / 100.0 * width))
    return "█" * filled + "░" * (width - filled)


def island_report(dataset, code: str) -> Optional[dict]:
    """Structured analysis for one island, or None if it is not in the database."""
    row = dataset.get(code)
    if not row:
        return None
    score = row.get("discovery")
    return {
        "code": row["code"],
        "title": row.get("title"),
        "creator_code": row.get("creator_code"),
        "genre": row.get("genre"),
        "genre_label": label_of(row.get("genre")),
        "genre_confidence": row.get("genre_confidence"),
        "genre_source": row.get("genre_source"),
        "age_days": row.get("age_days"),
        "discovery_score": row.get("discovery_score"),
        "cohort": {
            "key": score.cohort_key if score else None,
            "size": score.cohort_size if score else 0,
            "rank": row.get("genre_rank"),
            "of": row.get("genre_size"),
        },
        "components": row.get("discovery_components") or {},
        "levers": row.get("discovery_levers") or [],
        "row_fit": row.get("row_fit") or [],
        "metrics": {k: row.get(k) for k in KPIS},
        "percentiles": row.get("percentiles") or {},
        "momentum": {
            "growth_7d": row.get("growth_7d"),
            "growth_ccu_7d": row.get("growth_ccu_7d"),
            "direction": row.get("direction"),
            "reliable": row.get("momentum_reliable"),
            "rank_delta_7d": row.get("rank_delta_7d"),
            "history_points": row.get("history_points"),
        },
        "caveats": list(score.caveats) if score else [],
    }


def format_island_report(report: dict, *, width: int = 78) -> str:
    lines: list[str] = []
    add = lines.append

    title = report.get("title") or "(untitled)"
    add("=" * width)
    add(f"{title}")
    creator = f" · {report['creator_code']}" if report.get("creator_code") else ""
    add(f"{report['code']}{creator}")
    add("=" * width)

    confidence = report.get("genre_confidence")
    add(
        f"Genre    {report['genre_label']}"
        + (f"  ({report['genre_source']}, {confidence:.0%} confident)" if confidence else "")
    )
    cohort = report.get("cohort") or {}
    if cohort.get("rank"):
        add(f"Rank     #{cohort['rank']} of {cohort['of']} in this genre")
    if report.get("age_days") is not None:
        add(f"Age      {report['age_days']:.0f} days")

    score = report.get("discovery_score")
    add("")
    add(f"DISCOVERY FITNESS   {score:.1f} / 100" if score is not None else "DISCOVERY FITNESS   no data")
    add(f"  cohort: {cohort.get('key')} (n={cohort.get('size')})")
    add("")

    for name, label in COMPONENT_LABELS.items():
        pct = (report.get("components") or {}).get(name)
        value = f"p{pct:.0f}" if pct is not None else "  –"
        add(f"  {label:<14} {bar(pct)} {value}")

    levers = [l for l in report.get("levers") or [] if l["upside"] > 0]
    if levers:
        add("")
        add("WHERE THE POINTS ARE")
        for lever in levers:
            add(
                f"  +{lever['upside']:>5.1f}  {lever['label']:<14} "
                f"p{lever['percentile']:.0f} → p75, weighted {lever['weight']:.2f}"
            )
        top = levers[0]
        add("")
        add(f"  Fix first: {top['label']}. {COMPONENT_HELP.get(top['component'], '')}")

    fits = [f for f in report.get("row_fit") or [] if f.get("fit") is not None and f.get("eligible")]
    if fits:
        add("")
        add("DISCOVER ROW FIT")
        for entry in fits:
            add(f"  {entry['fit']:>5.0f}  {entry['label']}")

    momentum = report.get("momentum") or {}
    add("")
    add("MOMENTUM")
    if momentum.get("reliable"):
        growth = momentum.get("growth_7d")
        add(
            f"  7d players {growth * 100:+.1f}%   direction {momentum.get('direction')}"
            if growth is not None
            else f"  direction {momentum.get('direction')}"
        )
        if momentum.get("rank_delta_7d") is not None:
            delta = momentum["rank_delta_7d"]
            add(f"  rank change {delta:+d} places over 7 days")
    else:
        add(
            f"  not enough history yet ({momentum.get('history_points', 0)} readings). "
            "Epic does not backfill — keep polling."
        )

    add("")
    add("METRICS (value, then percentile in cohort)")
    for key in KPIS:
        value = format_kpi(key, (report.get("metrics") or {}).get(key))
        pct = (report.get("percentiles") or {}).get(key)
        marker = f"p{pct:>3.0f}" if pct is not None else "   –"
        add(f"  {KPI_LABELS[key]:<24} {value:>12}   {marker}  {bar(pct, 14)}")

    if report.get("caveats"):
        add("")
        add("CAVEATS")
        for caveat in report["caveats"]:
            add(f"  · {caveat}")

    return "\n".join(lines)


def format_leaderboard(rows: Sequence[dict], *, limit: int = 20) -> str:
    header = f"{'#':>3}  {'ISLAND':<34} {'GENRE':<18} {'FITNESS':>7} {'PLAYERS':>9} {'7D':>8}"
    lines = [header, "-" * len(header)]
    for position, row in enumerate(rows[:limit], start=1):
        score = row.get("discovery_score")
        growth = row.get("growth_7d")
        lines.append(
            f"{position:>3}  "
            f"{(row.get('title') or row['code'])[:34]:<34} "
            f"{label_of(row.get('genre'))[:18]:<18} "
            f"{(f'{score:.1f}' if score is not None else '-'):>7} "
            f"{format_kpi('unique_players', row.get('unique_players')):>9} "
            f"{(f'{growth * 100:+.1f}%' if growth is not None else '-'):>8}"
        )
    return "\n".join(lines)


__all__ = ["island_report", "format_island_report", "format_leaderboard", "bar"]
