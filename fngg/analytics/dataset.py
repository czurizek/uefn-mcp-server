"""Assembles one enriched, analysed view of the database.

Everything the dashboard, the CLI and the MCP tools render comes from a
`Dataset`. Building it once per request keeps cohort percentiles internally
consistent - if two tabs built their own cohorts from different row sets, the
same island would score differently depending on which tab you were looking at.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .. import config, store
from ..genres import FOCUS_GENRES, classify, label_of
from .cohort import Cohorts
from .discovery import DiscoveryScore, row_fit, score_discovery
from .kpis import KPIS, derive_kpis
from .movers import composite_growth, compute_momentum, rank_delta, rank_series

# Metrics that get cohort percentiles. KPIs plus the blended growth number.
COHORT_METRICS = tuple(KPIS) + ("composite_growth",)


@dataclass
class Dataset:
    rows: list[dict]
    cohorts: Cohorts
    interval: str
    window_days: int
    generated_at: str
    history_days: float
    warnings: list[str] = field(default_factory=list)
    _index: dict[str, dict] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._index = {row["code"]: row for row in self.rows if row.get("code")}

    # ------------------------------------------------------------- access

    def get(self, code: str) -> Optional[dict]:
        return self._index.get(code)

    def __len__(self) -> int:
        return len(self.rows)

    def filter(
        self,
        *,
        genre: Optional[str] = None,
        query: Optional[str] = None,
        creator: Optional[str] = None,
        tracked_only: bool = False,
        min_players: Optional[float] = None,
    ) -> list[dict]:
        out = self.rows
        if genre and genre != "all":
            out = [r for r in out if r.get("genre") == genre]
        if creator:
            needle = creator.lower()
            out = [r for r in out if needle in (r.get("creator_code") or "").lower()]
        if tracked_only:
            out = [r for r in out if r.get("tracked")]
        if min_players is not None:
            out = [r for r in out if (r.get("unique_players") or 0) >= min_players]
        if query:
            needle = query.lower().strip()
            out = [
                r
                for r in out
                if needle in (r.get("title") or "").lower()
                or needle in (r.get("code") or "").lower()
                or needle in (r.get("creator_code") or "").lower()
                or any(needle in str(t).lower() for t in (r.get("tags") or []))
            ]
        return out

    def top(
        self, metric: str, limit: int = 25, *, genre: Optional[str] = None, descending: bool = True
    ) -> list[dict]:
        rows = [r for r in self.filter(genre=genre) if r.get(metric) is not None]
        rows.sort(key=lambda r: r[metric], reverse=descending)
        return rows[:limit]

    def movers(
        self, limit: int = 25, *, genre: Optional[str] = None, rising: bool = True,
        min_players: float = 50,
    ) -> list[dict]:
        rows = [
            r
            for r in self.filter(genre=genre, min_players=min_players)
            if r.get("growth_7d") is not None and r.get("momentum_reliable")
        ]
        rows.sort(key=lambda r: r["growth_7d"], reverse=rising)
        return rows[:limit]

    def genre_counts(self) -> list[dict]:
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row.get("genre") or "other"] = counts.get(row.get("genre") or "other", 0) + 1
        ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        return [
            {"genre": genre, "label": label_of(genre), "count": count, "focus": genre in FOCUS_GENRES}
            for genre, count in ordered
        ]

    def summary(self) -> dict:
        scored = [r for r in self.rows if r.get("discovery_score") is not None]
        with_history = [r for r in self.rows if r.get("momentum_reliable")]
        return {
            "islands": len(self.rows),
            "scored": len(scored),
            "with_history": len(with_history),
            "history_days": round(self.history_days, 2),
            "interval": self.interval,
            "window_days": self.window_days,
            "generated_at": self.generated_at,
            "genres": self.genre_counts(),
            "warnings": self.warnings,
        }


def _age_days(row: dict, now: datetime) -> Optional[float]:
    for key in ("created_in", "first_seen"):
        when = store.parse_ts(row.get(key))
        if when:
            return round((now - when).total_seconds() / 86400.0, 1)
    return None


def _load_series(
    conn: sqlite3.Connection, interval: str, window_days: int
) -> dict[str, list[dict]]:
    """Every snapshot in the window, grouped by island, in one query."""
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days * 3)).isoformat(
        timespec="seconds"
    )
    rows = conn.execute(
        "SELECT * FROM snapshots WHERE interval=? AND captured_at >= ? "
        "ORDER BY code, captured_at ASC",
        (interval, cutoff),
    ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        record = dict(row)
        # Momentum reads derived KPIs too (minutes per player etc.), so derive
        # them on every historical point, not just the latest one.
        record.update(derive_kpis(record))
        grouped.setdefault(record["code"], []).append(record)
    return grouped


def build_dataset(
    conn: sqlite3.Connection,
    *,
    interval: str = config.DEFAULT_INTERVAL,
    window_days: int = 7,
    persist_genres: bool = True,
) -> Dataset:
    now = datetime.now(timezone.utc)
    latest = store.latest_rows(conn, interval)
    warnings: list[str] = []

    rows: list[dict] = []
    for raw in latest:
        row = store.row_to_dict(raw)
        row.update(derive_kpis(row))

        classification = classify(
            title=row.get("title"),
            tags=row.get("tags") or [],
            category=row.get("category"),
            override=row.get("genre_override"),
            average_minutes_per_player=row.get("minutes_per_player"),
            plays=row.get("plays"),
            unique_players=row.get("unique_players"),
            retention_d1=row.get("retention_d1"),
        )
        row["genre"] = classification.genre
        row["genre_label"] = classification.label
        row["genre_confidence"] = classification.confidence
        row["genre_source"] = classification.source
        row["family"] = classification.family
        row["age_days"] = _age_days(row, now)
        rows.append(row)

    if persist_genres and rows:
        for row in rows:
            store.set_genre(
                conn, row["code"], row["genre"], row["genre_confidence"], row["genre_source"]
            )
        conn.commit()

    # ---------------------------------------------------------- momentum
    series = _load_series(conn, interval, window_days)
    for row in rows:
        history = series.get(row["code"], [])
        row["history_points"] = len(history)
        growth = composite_growth(history, window_days=window_days)
        row["composite_growth"] = growth

        players = compute_momentum(history, "unique_players", window_days=window_days, now=now)
        ccu = compute_momentum(history, "peak_ccu", window_days=window_days, now=now)
        minutes = compute_momentum(history, "minutes_played", window_days=window_days, now=now)
        row["momentum_players"] = players.to_dict()
        row["momentum_ccu"] = ccu.to_dict()
        row["momentum_minutes"] = minutes.to_dict()
        row["growth_7d"] = players.change_pct
        row["growth_ccu_7d"] = ccu.change_pct
        row["momentum_reliable"] = players.reliable
        row["direction"] = players.direction
        row["spark_players"] = [v for _, v in players.series]
        # to_dict() drops the raw series; keep it for the comparison chart.
        row["series_players"] = [(ts[:10], value) for ts, value in players.series]

    if not any(r.get("momentum_reliable") for r in rows):
        warnings.append(
            "No island has enough polling history yet for trend analysis. "
            "Epic serves one live reading and never backfills, so momentum appears "
            "after a few days of `fngg poll`."
        )

    # ------------------------------------------------------------ cohorts
    cohorts = Cohorts(rows, COHORT_METRICS)

    for row in rows:
        row["momentum_percentile"] = cohorts.percentile(
            row["genre"], "composite_growth", row.get("composite_growth")
        )
        score: DiscoveryScore = score_discovery(
            row, cohorts, momentum_percentile=row["momentum_percentile"]
        )
        row["discovery"] = score
        row["discovery_score"] = score.score
        row["discovery_components"] = score.components
        row["discovery_levers"] = score.levers
        row["discovery_top_lever"] = score.top_lever
        row["row_fit"] = row_fit(score, age_days=row.get("age_days"))
        row["best_row"] = next(
            (entry for entry in row["row_fit"] if entry["fit"] is not None and entry["eligible"]),
            None,
        )
        # Percentiles for the KPI table in map detail.
        row["percentiles"] = {
            metric: cohorts.percentile(row["genre"], metric, row.get(metric)) for metric in KPIS
        }

    # ------------------------------------------------------ ranks over time
    ranks = rank_series(series, "unique_players")
    for row in rows:
        history = ranks.get(row["code"], [])
        row["rank_history"] = history
        row["rank_now"] = history[-1][1] if history else None
        row["rank_delta_7d"] = rank_delta(history, window_days=window_days)

    # Cohort-local rank on today's numbers - useful even with zero history.
    for genre in {r["genre"] for r in rows}:
        peers = [r for r in rows if r["genre"] == genre and r.get("unique_players") is not None]
        peers.sort(key=lambda r: r["unique_players"], reverse=True)
        for position, peer in enumerate(peers, start=1):
            peer["genre_rank"] = position
            peer["genre_size"] = len(peers)

    rows.sort(key=lambda r: (r.get("discovery_score") is None, -(r.get("discovery_score") or 0)))

    return Dataset(
        rows=rows,
        cohorts=cohorts,
        interval=interval,
        window_days=window_days,
        generated_at=now.isoformat(timespec="seconds"),
        history_days=store.history_span_days(conn, interval),
        warnings=warnings,
    )


__all__ = ["Dataset", "build_dataset", "COHORT_METRICS"]
