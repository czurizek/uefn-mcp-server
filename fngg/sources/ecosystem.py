"""Client for Epic's public Fortnite Ecosystem Data API.

Base: https://api.fortnite.com/ecosystem/v1   (public, no authentication)

Endpoints used here:
    GET /islands                              cursor-paginated catalog (~100/page)
    GET /islands/{code}                       metadata for one island
    GET /islands/{code}/metrics/{interval}    interval in {day, hour, minute}

Two behaviours of this API drive the whole design of this package:

1. It is a live snapshot shaped like a time series. Every bucket in a metric
   series comes back `null` except the most recent populated one, so a single
   call gives you *one* real reading per metric, not a history.
2. `from` values older than roughly six days are rejected outright.

Together that means missed history is gone permanently - nobody can backfill it.
So `poll.py` writes every reading it sees into SQLite and that local log becomes
the history this app analyses.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from .. import config
from ..http_client import HttpError, NotFound, get_json

# Series returned by /metrics/{interval} that are plain {timestamp, value}.
VALUE_SERIES = (
    "uniquePlayers",
    "peakCCU",
    "minutesPlayed",
    "averageMinutesPerPlayer",
    "plays",
    "favorites",
    "recommendations",
)
# `retention` is shaped {timestamp, d1, d7} instead.
RETENTION_SERIES = "retention"


@dataclass
class Island:
    code: str
    title: Optional[str] = None
    creator_code: Optional[str] = None
    category: Optional[str] = None
    created_in: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_api(cls, entry: dict, fallback_code: str = "") -> "Island":
        tags = entry.get("tags")
        return cls(
            code=entry.get("code") or fallback_code,
            title=entry.get("title"),
            creator_code=entry.get("creatorCode"),
            category=entry.get("category"),
            created_in=entry.get("createdIn"),
            tags=[str(t) for t in tags] if isinstance(tags, list) else [],
        )


@dataclass
class MetricReading:
    """One island's most recent populated reading for each metric."""

    code: str
    interval: str
    captured_at: str
    unique_players: Optional[float] = None
    peak_ccu: Optional[float] = None
    minutes_played: Optional[float] = None
    average_minutes_per_player: Optional[float] = None
    plays: Optional[float] = None
    favorites: Optional[float] = None
    recommendations: Optional[float] = None
    retention_d1: Optional[float] = None
    retention_d7: Optional[float] = None

    def has_data(self) -> bool:
        return any(
            v is not None
            for v in (
                self.unique_players,
                self.peak_ccu,
                self.minutes_played,
                self.plays,
                self.favorites,
                self.recommendations,
                self.retention_d1,
                self.retention_d7,
            )
        )


def _url(path: str, params: Optional[dict] = None) -> str:
    url = f"{config.ECOSYSTEM_BASE}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url = f"{url}?{urllib.parse.urlencode(clean)}"
    return url


# ------------------------------------------------------------------- catalog


def fetch_islands_page(cursor: Optional[str] = None) -> tuple[list[Island], Optional[str]]:
    """One page of the island catalog. Returns (islands, next_cursor)."""
    body = get_json(_url("/islands", {"after": cursor}))
    data = body.get("data") if isinstance(body, dict) else None
    islands = [Island.from_api(e) for e in data] if isinstance(data, list) else []
    next_cursor = None
    if isinstance(body, dict):
        meta = body.get("meta")
        if isinstance(meta, dict):
            page = meta.get("page")
            if isinstance(page, dict):
                next_cursor = page.get("nextCursor") or None
    return islands, next_cursor


def iter_islands(
    limit: Optional[int] = None, start_cursor: Optional[str] = None
) -> Iterator[tuple[Island, Optional[str]]]:
    """Walk the catalog, yielding (island, cursor_that_produced_next_page).

    The cursor is yielded alongside each island so a long crawl can be resumed
    after an interruption instead of starting from page one again.
    """
    cursor = start_cursor
    seen = 0
    while True:
        islands, next_cursor = fetch_islands_page(cursor)
        if not islands:
            return
        for island in islands:
            yield island, next_cursor
            seen += 1
            if limit is not None and seen >= limit:
                return
        if not next_cursor:
            return
        cursor = next_cursor


def fetch_island(code: str) -> Optional[Island]:
    """Metadata for one island, or None if it is not public/discoverable."""
    try:
        body = get_json(_url(f"/islands/{urllib.parse.quote(str(code))}"))
    except NotFound:
        return None
    if not isinstance(body, dict):
        return None
    # Some deployments wrap the object in {"data": {...}} - accept both shapes.
    payload = body.get("data") if isinstance(body.get("data"), dict) else body
    return Island.from_api(payload, fallback_code=str(code))


# ------------------------------------------------------------------- metrics


def _latest_value(series: Any) -> Optional[tuple[float, str]]:
    """Last entry with a non-null `value`. Returns (value, timestamp)."""
    if not isinstance(series, list):
        return None
    for entry in reversed(series):
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if value is None:
            continue
        try:
            return float(value), str(entry.get("timestamp") or "")
        except (TypeError, ValueError):
            continue
    return None


def _latest_retention(series: Any) -> Optional[tuple[Optional[float], Optional[float], str]]:
    if not isinstance(series, list):
        return None
    for entry in reversed(series):
        if not isinstance(entry, dict):
            continue
        d1, d7 = entry.get("d1"), entry.get("d7")
        if d1 is None and d7 is None:
            continue
        return (
            _as_float(d1),
            _as_float(d7),
            str(entry.get("timestamp") or ""),
        )
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_metrics_raw(code: str, interval: str = config.DEFAULT_INTERVAL) -> Optional[dict]:
    """Raw metrics payload, or None if the island 404s (delisted/private)."""
    if interval not in config.INTERVALS:
        raise ValueError(f"interval must be one of {config.INTERVALS}, got {interval!r}")
    path = f"/islands/{urllib.parse.quote(str(code))}/metrics/{interval}"
    try:
        body = get_json(_url(path))
    except NotFound:
        return None
    return body if isinstance(body, dict) else None


def fetch_latest_metrics(
    code: str, interval: str = config.DEFAULT_INTERVAL
) -> Optional[MetricReading]:
    """Reduce a metrics payload to its single most recent populated reading."""
    body = fetch_metrics_raw(code, interval)
    if body is None:
        return None
    return reading_from_payload(code, interval, body)


def reading_from_payload(code: str, interval: str, body: dict) -> Optional[MetricReading]:
    """Pure reduction of an API payload - kept separate so tests can use fixtures."""
    # Payloads have occasionally been observed wrapped in {"data": {...}}.
    if isinstance(body.get("data"), dict) and not any(k in body for k in VALUE_SERIES):
        body = body["data"]

    values: dict[str, Optional[float]] = {}
    timestamps: list[str] = []
    for name in VALUE_SERIES:
        found = _latest_value(body.get(name))
        if found:
            values[name], ts = found[0], found[1]
            if ts:
                timestamps.append(ts)
        else:
            values[name] = None

    d1 = d7 = None
    retention = _latest_retention(body.get(RETENTION_SERIES))
    if retention:
        d1, d7, ts = retention
        if ts:
            timestamps.append(ts)

    reading = MetricReading(
        code=str(code),
        interval=interval,
        captured_at=max(timestamps) if timestamps else "",
        unique_players=values.get("uniquePlayers"),
        peak_ccu=values.get("peakCCU"),
        minutes_played=values.get("minutesPlayed"),
        average_minutes_per_player=values.get("averageMinutesPerPlayer"),
        plays=values.get("plays"),
        favorites=values.get("favorites"),
        recommendations=values.get("recommendations"),
        retention_d1=d1,
        retention_d7=d7,
    )
    if not reading.has_data():
        return None
    if not reading.captured_at:
        from datetime import datetime, timezone

        reading.captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return reading


def fetch_full_series(code: str, interval: str = config.DEFAULT_INTERVAL) -> list[MetricReading]:
    """Every populated bucket, not just the newest.

    Today Epic populates exactly one bucket per series, so this normally returns
    a single reading - but if that ever changes, polling picks the extra history
    up for free instead of silently discarding it.
    """
    body = fetch_metrics_raw(code, interval)
    if body is None:
        return []
    return readings_from_payload(code, interval, body)


def readings_from_payload(code: str, interval: str, body: dict) -> list[MetricReading]:
    if isinstance(body.get("data"), dict) and not any(k in body for k in VALUE_SERIES):
        body = body["data"]

    by_ts: dict[str, MetricReading] = {}

    def slot(ts: str) -> MetricReading:
        if ts not in by_ts:
            by_ts[ts] = MetricReading(code=str(code), interval=interval, captured_at=ts)
        return by_ts[ts]

    attr = {
        "uniquePlayers": "unique_players",
        "peakCCU": "peak_ccu",
        "minutesPlayed": "minutes_played",
        "averageMinutesPerPlayer": "average_minutes_per_player",
        "plays": "plays",
        "favorites": "favorites",
        "recommendations": "recommendations",
    }
    for name, field_name in attr.items():
        series = body.get(name)
        if not isinstance(series, list):
            continue
        for entry in series:
            if not isinstance(entry, dict):
                continue
            value = _as_float(entry.get("value"))
            ts = str(entry.get("timestamp") or "")
            if value is None or not ts:
                continue
            setattr(slot(ts), field_name, value)

    series = body.get(RETENTION_SERIES)
    if isinstance(series, list):
        for entry in series:
            if not isinstance(entry, dict):
                continue
            d1, d7 = _as_float(entry.get("d1")), _as_float(entry.get("d7"))
            ts = str(entry.get("timestamp") or "")
            if not ts or (d1 is None and d7 is None):
                continue
            row = slot(ts)
            row.retention_d1, row.retention_d7 = d1, d7

    return [by_ts[ts] for ts in sorted(by_ts) if by_ts[ts].has_data()]


__all__ = [
    "Island",
    "MetricReading",
    "HttpError",
    "NotFound",
    "fetch_islands_page",
    "iter_islands",
    "fetch_island",
    "fetch_metrics_raw",
    "fetch_latest_metrics",
    "fetch_full_series",
    "reading_from_payload",
    "readings_from_payload",
]
