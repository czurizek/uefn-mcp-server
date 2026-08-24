"""Cohort benchmarks.

Every number in this app is judged against peers, never in absolute terms. A
14% day-7 retention is mediocre for an RP city and excellent for a box-fight
map, so "is 14% good?" is only answerable inside a cohort.

Cohorts fall back when they are too thin to be meaningful:
    exact genre  ->  session-shape family  ->  everything
A cohort of three islands would make percentiles noise, so MIN_COHORT guards it.
"""

from __future__ import annotations

import bisect
import statistics
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from ..genres import family_of

MIN_COHORT = 8
GLOBAL_KEY = "__all__"

PERCENTILE_POINTS = (10, 25, 50, 75, 90)


def percentile_of(sorted_values: Sequence[float], value: Optional[float]) -> Optional[float]:
    """Percentile rank of `value` within `sorted_values`, 0-100.

    Ties count as half, which keeps a metric where many islands share a value
    (retention rounded to 2 decimals, say) from collapsing to 0 or 100.
    """
    if value is None or not sorted_values:
        return None
    n = len(sorted_values)
    below = bisect.bisect_left(sorted_values, value)
    equal = bisect.bisect_right(sorted_values, value) - below
    return round(100.0 * (below + 0.5 * equal) / n, 2)


@dataclass
class CohortStats:
    key: str
    metric: str
    values: list[float] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def median(self) -> Optional[float]:
        return statistics.median(self.values) if self.values else None

    @property
    def mean(self) -> Optional[float]:
        return statistics.fmean(self.values) if self.values else None

    def quantile(self, pct: float) -> Optional[float]:
        if not self.values:
            return None
        if len(self.values) == 1:
            return self.values[0]
        position = (len(self.values) - 1) * (pct / 100.0)
        low = int(position)
        high = min(low + 1, len(self.values) - 1)
        weight = position - low
        return self.values[low] * (1 - weight) + self.values[high] * weight

    def summary(self) -> dict:
        return {
            "key": self.key,
            "metric": self.metric,
            "count": self.count,
            **{f"p{p}": self.quantile(p) for p in PERCENTILE_POINTS},
        }


class Cohorts:
    """Percentile lookups over a set of enriched island rows."""

    def __init__(self, rows: Iterable[dict], metrics: Sequence[str]):
        self.metrics = tuple(metrics)
        self._store: dict[tuple[str, str], CohortStats] = {}
        self._build(list(rows))

    def _build(self, rows: list[dict]) -> None:
        buckets: dict[tuple[str, str], list[float]] = {}
        for row in rows:
            genre = row.get("genre") or "other"
            keys = (genre, f"family:{family_of(genre)}", GLOBAL_KEY)
            for metric in self.metrics:
                value = row.get(metric)
                if value is None:
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                for key in keys:
                    buckets.setdefault((key, metric), []).append(numeric)

        for (key, metric), values in buckets.items():
            values.sort()
            self._store[(key, metric)] = CohortStats(key=key, metric=metric, values=values)

    # ------------------------------------------------------------ lookups

    def resolve_key(self, genre: Optional[str], metric: str) -> str:
        """The cohort actually used for this genre/metric after fallback."""
        genre = genre or "other"
        for key in (genre, f"family:{family_of(genre)}", GLOBAL_KEY):
            stats = self._store.get((key, metric))
            if stats and stats.count >= MIN_COHORT:
                return key
        return GLOBAL_KEY

    def stats(self, genre: Optional[str], metric: str) -> Optional[CohortStats]:
        return self._store.get((self.resolve_key(genre, metric), metric))

    def percentile(self, genre: Optional[str], metric: str, value: Optional[float]) -> Optional[float]:
        stats = self.stats(genre, metric)
        if not stats:
            return None
        return percentile_of(stats.values, value)

    def blended_percentile(
        self, genre: Optional[str], row: dict, weights: dict[str, float]
    ) -> Optional[float]:
        """Weighted mean of percentiles, renormalised over the parts present.

        An island missing `recommendations` should not score zero on advocacy -
        it should be judged on the advocacy signals it does have.
        """
        total_weight = 0.0
        total = 0.0
        for metric, weight in weights.items():
            pct = self.percentile(genre, metric, row.get(metric))
            if pct is None:
                continue
            total += pct * weight
            total_weight += weight
        if total_weight <= 0:
            return None
        return round(total / total_weight, 2)

    def summary_table(self, genre: Optional[str], metrics: Optional[Sequence[str]] = None) -> list[dict]:
        out = []
        for metric in metrics or self.metrics:
            stats = self.stats(genre, metric)
            if stats:
                out.append(stats.summary())
        return out

    def available_keys(self) -> list[str]:
        return sorted({key for key, _ in self._store})

    def size(self, genre: Optional[str], metric: str) -> int:
        stats = self.stats(genre, metric)
        return stats.count if stats else 0


__all__ = ["Cohorts", "CohortStats", "percentile_of", "MIN_COHORT", "GLOBAL_KEY"]
