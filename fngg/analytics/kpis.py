"""Derived KPIs.

Epic hands you seven raw counters. On their own they only tell you how big an
island is. The ratios below are what actually separate a healthy RP city from a
churning one at the same player count - session depth, how often people come
back for a second run, and how many of them care enough to favourite it.
"""

from __future__ import annotations

from typing import Any, Optional

# Ordered: the dashboard renders KPI tables in this order.
KPIS = (
    "unique_players",
    "peak_ccu",
    "minutes_played",
    "player_hours",
    "minutes_per_player",
    "minutes_per_play",
    "replays_per_player",
    "retention_d1",
    "retention_d7",
    "d7_over_d1",
    "favorites_rate",
    "recommend_rate",
    "ccu_concentration",
    "hours_per_ccu",
)

KPI_LABELS = {
    "unique_players": "Unique players",
    "peak_ccu": "Peak CCU",
    "minutes_played": "Minutes played",
    "player_hours": "Player hours",
    "minutes_per_player": "Minutes / player",
    "minutes_per_play": "Minutes / session",
    "replays_per_player": "Sessions / player",
    "retention_d1": "Retention D1",
    "retention_d7": "Retention D7",
    "d7_over_d1": "D7 / D1 (curve hold)",
    "favorites_rate": "Favourite rate",
    "recommend_rate": "Recommend rate",
    "ccu_concentration": "CCU concentration",
    "hours_per_ccu": "Hours per peak CCU",
}

KPI_HELP = {
    "minutes_per_player": "Total minutes one unique player spent on the island that day.",
    "minutes_per_play": "Length of a single session. Short + high sessions/player is a healthy fast loop; short + low is a bounce.",
    "replays_per_player": "How many separate sessions each player started. Below 1.2 means almost nobody came back for a second round.",
    "d7_over_d1": "How much of your day-1 retention survives to day 7. Above 0.45 is a genuinely sticky loop.",
    "favorites_rate": "Favourites per unique player. Advocacy signal - it feeds the community-driven Discover rows.",
    "recommend_rate": "Recommendations per unique player.",
    "ccu_concentration": "Peak CCU divided by unique players. High means your audience shows up together (good for lobby fill); low means they trickle in all day.",
    "hours_per_ccu": "Player hours divided by peak CCU. Near 24 means the island was effectively full around the clock.",
}

# Percentage-shaped KPIs, rendered as % in the UI.
RATE_KPIS = {"retention_d1", "retention_d7", "d7_over_d1", "favorites_rate", "recommend_rate"}

# KPIs where lower is not automatically worse, so cohort colouring stays neutral.
NEUTRAL_KPIS = {"ccu_concentration", "minutes_per_play"}


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    try:
        return float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def derive_kpis(row: dict) -> dict[str, Optional[float]]:
    """Compute every derived KPI from one snapshot row.

    Missing inputs yield None rather than 0 - a zero would quietly drag cohort
    percentiles down and make an unpolled island look like a failing one.
    """
    unique = _num(row.get("unique_players"))
    ccu = _num(row.get("peak_ccu"))
    minutes = _num(row.get("minutes_played"))
    avg_minutes = _num(row.get("average_minutes_per_player"))
    plays = _num(row.get("plays"))
    favorites = _num(row.get("favorites"))
    recommends = _num(row.get("recommendations"))
    d1 = _num(row.get("retention_d1"))
    d7 = _num(row.get("retention_d7"))

    player_hours = minutes / 60.0 if minutes is not None else None

    # Epic supplies averageMinutesPerPlayer directly; fall back to the ratio when
    # that field is absent so partial payloads still produce a usable number.
    minutes_per_player = avg_minutes if avg_minutes is not None else _ratio(minutes, unique)

    return {
        "unique_players": unique,
        "peak_ccu": ccu,
        "minutes_played": minutes,
        "player_hours": player_hours,
        "minutes_per_player": minutes_per_player,
        "minutes_per_play": _ratio(minutes, plays),
        "replays_per_player": _ratio(plays, unique),
        "retention_d1": _normalise_rate(d1),
        "retention_d7": _normalise_rate(d7),
        "d7_over_d1": _ratio(_normalise_rate(d7), _normalise_rate(d1)),
        "favorites_rate": _ratio(favorites, unique),
        "recommend_rate": _ratio(recommends, unique),
        "ccu_concentration": _ratio(ccu, unique),
        "hours_per_ccu": _ratio(player_hours, ccu),
    }


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _normalise_rate(value: Optional[float]) -> Optional[float]:
    """Retention has been observed both as 0-1 and as 0-100. Store it as 0-1."""
    if value is None:
        return None
    return value / 100.0 if value > 1.5 else value


def format_kpi(name: str, value: Optional[float]) -> str:
    if value is None:
        return "–"
    if name in RATE_KPIS:
        return f"{value * 100:.1f}%"
    if name in ("unique_players", "peak_ccu", "minutes_played", "player_hours"):
        return _compact(value)
    return f"{value:,.2f}"


def _compact(value: float) -> str:
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            return f"{value / limit:.1f}{suffix}"
    return f"{value:,.0f}"
