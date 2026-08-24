"""Momentum: what changed, how fast, and how reliably.

The awkward truth this module has to handle: on a fresh install there is no
history at all, because Epic serves one live reading and refuses to backfill. So
every function here returns None rather than a fake zero when the window is too
short, and `MomentumResult.window_days` tells the UI how much history the number
actually rests on. A 7-day growth figure computed from two days of polling is
worse than no figure, and is reported as such.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from ..store import parse_ts

# Growth blended into the Discovery "momentum" component.
COMPOSITE_METRICS = {"unique_players": 0.45, "minutes_played": 0.35, "peak_ccu": 0.20}

MIN_POINTS = 2


@dataclass
class MomentumResult:
    metric: str
    latest: Optional[float] = None
    previous: Optional[float] = None
    baseline: Optional[float] = None          # value at the start of the window
    change_abs: Optional[float] = None        # latest - baseline
    change_pct: Optional[float] = None        # fractional, 0.12 == +12%
    step_change_pct: Optional[float] = None   # latest vs the reading before it
    slope_per_day: Optional[float] = None     # least-squares trend
    volatility: Optional[float] = None        # stdev / mean over the window
    window_days: float = 0.0
    points: int = 0
    series: list[tuple[str, float]] = field(default_factory=list)

    @property
    def direction(self) -> str:
        if self.change_pct is None:
            return "unknown"
        if self.change_pct >= 0.15:
            return "surging"
        if self.change_pct >= 0.03:
            return "rising"
        if self.change_pct <= -0.15:
            return "collapsing"
        if self.change_pct <= -0.03:
            return "falling"
        return "flat"

    @property
    def reliable(self) -> bool:
        """Is there enough history for this to mean anything?"""
        return self.points >= 3 and self.window_days >= 2.0

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "latest": self.latest,
            "baseline": self.baseline,
            "change_abs": self.change_abs,
            "change_pct": self.change_pct,
            "step_change_pct": self.step_change_pct,
            "slope_per_day": self.slope_per_day,
            "volatility": self.volatility,
            "window_days": self.window_days,
            "points": self.points,
            "direction": self.direction,
            "reliable": self.reliable,
        }


def series_points(rows: Iterable[dict], metric: str) -> list[tuple[datetime, float]]:
    """(timestamp, value) pairs for one metric, sorted, nulls dropped."""
    points: list[tuple[datetime, float]] = []
    for row in rows:
        when = parse_ts(row.get("captured_at") or row.get("observed_at"))
        value = row.get(metric)
        if when is None or value is None:
            continue
        try:
            points.append((when, float(value)))
        except (TypeError, ValueError):
            continue
    points.sort(key=lambda p: p[0])
    return points


def linear_slope(points: Sequence[tuple[datetime, float]]) -> Optional[float]:
    """Least-squares slope in units per day."""
    if len(points) < MIN_POINTS:
        return None
    origin = points[0][0]
    xs = [(when - origin).total_seconds() / 86400.0 for when, _ in points]
    ys = [value for _, value in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return numerator / denominator


def compute_momentum(
    rows: Iterable[dict], metric: str, *, window_days: int = 7, now: Optional[datetime] = None
) -> MomentumResult:
    points = series_points(rows, metric)
    result = MomentumResult(metric=metric, points=len(points))
    if not points:
        return result

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    windowed = [p for p in points if p[0] >= cutoff]
    # Keep one reading from before the window so a sparse poller still has a
    # baseline to measure against instead of reporting no change.
    if len(windowed) < 2:
        earlier = [p for p in points if p[0] < cutoff]
        if earlier:
            windowed = [earlier[-1]] + windowed
    if not windowed:
        windowed = points[-2:]

    result.series = [(when.isoformat(), value) for when, value in windowed]
    result.points = len(windowed)
    result.latest = windowed[-1][1]
    result.baseline = windowed[0][1]
    result.window_days = round((windowed[-1][0] - windowed[0][0]).total_seconds() / 86400.0, 2)

    if len(windowed) >= 2:
        result.previous = windowed[-2][1]
        result.change_abs = result.latest - result.baseline
        if result.baseline:
            result.change_pct = round(result.change_abs / abs(result.baseline), 4)
        if result.previous:
            result.step_change_pct = round(
                (result.latest - result.previous) / abs(result.previous), 4
            )
        slope = linear_slope(windowed)
        result.slope_per_day = round(slope, 4) if slope is not None else None

        values = [v for _, v in windowed]
        mean = statistics.fmean(values)
        if len(values) >= 3 and mean:
            result.volatility = round(statistics.pstdev(values) / abs(mean), 4)

    return result


def composite_growth(rows: Iterable[dict], *, window_days: int = 7) -> Optional[float]:
    """One blended growth number across the metrics that signal traction.

    Weighted so a rise in unique players counts for more than a rise in peak
    concurrency, which can move on a single busy evening.
    """
    rows = list(rows)
    total_weight = 0.0
    total = 0.0
    for metric, weight in COMPOSITE_METRICS.items():
        momentum = compute_momentum(rows, metric, window_days=window_days)
        if momentum.change_pct is None:
            continue
        # Compress extremes: an island going 3 -> 300 players should not swamp
        # the cohort's percentile scale.
        compressed = math.copysign(math.log1p(abs(momentum.change_pct)), momentum.change_pct)
        total += compressed * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return round(total / total_weight, 5)


def rank_series(
    rows_by_code: dict[str, list[dict]], metric: str, *, top: Optional[int] = None
) -> dict[str, list[tuple[str, int]]]:
    """Rank of every island on `metric` at each timestamp where it was observed.

    Used by the dashboard to draw rank-over-time and to compute rank deltas,
    which read far more naturally than raw player deltas ("dropped 40 places"
    lands harder than "lost 812 uniques").
    """
    by_timestamp: dict[str, list[tuple[str, float]]] = {}
    for code, rows in rows_by_code.items():
        for row in rows:
            when = row.get("captured_at")
            value = row.get(metric)
            if not when or value is None:
                continue
            try:
                by_timestamp.setdefault(str(when)[:10], []).append((code, float(value)))
            except (TypeError, ValueError):
                continue

    out: dict[str, list[tuple[str, int]]] = {}
    for day, entries in by_timestamp.items():
        entries.sort(key=lambda e: e[1], reverse=True)
        if top:
            entries = entries[:top]
        for position, (code, _) in enumerate(entries, start=1):
            out.setdefault(code, []).append((day, position))
    for code in out:
        out[code].sort()
    return out


def rank_delta(history: Sequence[tuple[str, int]], *, window_days: int = 7) -> Optional[int]:
    """Positions gained since the start of the window. Positive is upward."""
    if len(history) < 2:
        return None
    latest_day, latest_rank = history[-1]
    target = parse_ts(latest_day)
    if target is None:
        return None
    cutoff = target - timedelta(days=window_days)
    baseline_rank = history[0][1]
    for day, rank in history:
        when = parse_ts(day)
        if when and when <= cutoff:
            baseline_rank = rank
    return baseline_rank - latest_rank


__all__ = [
    "MomentumResult",
    "COMPOSITE_METRICS",
    "series_points",
    "linear_slope",
    "compute_momentum",
    "composite_growth",
    "rank_series",
    "rank_delta",
]
