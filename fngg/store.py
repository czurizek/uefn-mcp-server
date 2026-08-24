"""SQLite persistence.

This database is the only place island history exists. Epic's API returns one
live reading per metric and refuses `from` values older than ~6 days, so a day
that was not polled is a day nobody can ever reconstruct. Everything here is
therefore append-only and deduplicated rather than overwritten.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

from . import config
from .sources.ecosystem import Island, MetricReading

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS islands (
    code                TEXT PRIMARY KEY,
    title               TEXT,
    creator_code        TEXT,
    category            TEXT,
    created_in          TEXT,
    tags_json           TEXT NOT NULL DEFAULT '[]',
    genre               TEXT,
    genre_confidence    REAL,
    genre_source        TEXT,
    genre_override      TEXT,
    first_seen          TEXT,
    last_seen           TEXT,
    last_polled         TEXT,
    missing_since       TEXT,
    tracked             INTEGER NOT NULL DEFAULT 0,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    code                        TEXT NOT NULL,
    interval                    TEXT NOT NULL,
    captured_at                 TEXT NOT NULL,
    unique_players              REAL,
    peak_ccu                    REAL,
    minutes_played              REAL,
    average_minutes_per_player  REAL,
    plays                       REAL,
    favorites                   REAL,
    recommendations             REAL,
    retention_d1                REAL,
    retention_d7                REAL,
    ingested_at                 TEXT NOT NULL,
    PRIMARY KEY (code, interval, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_captured
    ON snapshots (interval, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_code
    ON snapshots (code, interval, captured_at DESC);

-- Live concurrency / rank samples from fortnite.gg (optional source).
CREATE TABLE IF NOT EXISTS gg_samples (
    code            TEXT NOT NULL,
    observed_at     TEXT NOT NULL,
    ccu             REAL,
    peak_24h        REAL,
    rank_overall    INTEGER,
    favorites       REAL,
    source          TEXT,
    PRIMARY KEY (code, observed_at)
);

-- Observed Discover row placements: which row, which slot, when.
CREATE TABLE IF NOT EXISTS discovery_placements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    row_key     TEXT NOT NULL,
    row_label   TEXT,
    position    INTEGER,
    source      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_placement_unique
    ON discovery_placements (code, observed_at, row_key);
CREATE INDEX IF NOT EXISTS idx_placement_row
    ON discovery_placements (row_key, observed_at DESC);

CREATE TABLE IF NOT EXISTS poll_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    ok          INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

SNAPSHOT_COLUMNS = (
    "unique_players",
    "peak_ccu",
    "minutes_played",
    "average_minutes_per_player",
    "plays",
    "favorites",
    "recommendations",
    "retention_d1",
    "retention_d7",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    target = Path(path) if path else config.db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=30.0)
    conn.row_factory = sqlite3.Row
    # WAL lets the dashboard read while the poller writes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


@contextmanager
def open_db(path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------------------- meta kv


def get_meta(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: Optional[str]) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


# ------------------------------------------------------------------- islands


def upsert_island(conn: sqlite3.Connection, island: Island, *, seen_at: Optional[str] = None) -> None:
    now = seen_at or utcnow()
    conn.execute(
        """
        INSERT INTO islands (code, title, creator_code, category, created_in,
                             tags_json, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            title        = COALESCE(excluded.title, islands.title),
            creator_code = COALESCE(excluded.creator_code, islands.creator_code),
            category     = COALESCE(excluded.category, islands.category),
            created_in   = COALESCE(excluded.created_in, islands.created_in),
            tags_json    = CASE WHEN excluded.tags_json = '[]'
                                THEN islands.tags_json ELSE excluded.tags_json END,
            last_seen    = excluded.last_seen,
            missing_since = NULL
        """,
        (
            island.code,
            island.title,
            island.creator_code,
            island.category,
            island.created_in,
            json.dumps(island.tags, ensure_ascii=False),
            now,
            now,
        ),
    )


def upsert_islands(conn: sqlite3.Connection, islands: Iterable[Island]) -> int:
    now = utcnow()
    count = 0
    for island in islands:
        if not island.code:
            continue
        upsert_island(conn, island, seen_at=now)
        count += 1
    return count


def set_genre(
    conn: sqlite3.Connection,
    code: str,
    genre: str,
    confidence: float,
    source: str,
) -> None:
    conn.execute(
        "UPDATE islands SET genre=?, genre_confidence=?, genre_source=? WHERE code=?",
        (genre, confidence, source, code),
    )


def set_genre_override(conn: sqlite3.Connection, code: str, genre: Optional[str]) -> None:
    conn.execute("UPDATE islands SET genre_override=? WHERE code=?", (genre, code))


def set_tracked(conn: sqlite3.Connection, code: str, tracked: bool = True) -> None:
    conn.execute("UPDATE islands SET tracked=? WHERE code=?", (1 if tracked else 0, code))


def mark_missing(conn: sqlite3.Connection, code: str) -> None:
    """Island 404'd: no longer public/discoverable. Kept, not deleted."""
    conn.execute(
        "UPDATE islands SET missing_since = COALESCE(missing_since, ?) WHERE code=?",
        (utcnow(), code),
    )


def mark_polled(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("UPDATE islands SET last_polled=?, missing_since=NULL WHERE code=?", (utcnow(), code))


def get_island(conn: sqlite3.Connection, code: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM islands WHERE code=?", (code,)).fetchone()


def island_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM islands").fetchone()["n"])


def tracked_codes(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT code FROM islands WHERE tracked=1 ORDER BY code").fetchall()
    return [r["code"] for r in rows]


def poll_candidates(conn: sqlite3.Connection, limit: Optional[int] = None) -> list[str]:
    """Codes to poll next: tracked first, then least-recently polled.

    Islands that have 404'd for more than 14 days drop out of the rotation so a
    long dead tail does not eat the request budget.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(timespec="seconds")
    sql = """
        SELECT code FROM islands
        WHERE missing_since IS NULL OR missing_since > ?
        ORDER BY tracked DESC,
                 CASE WHEN last_polled IS NULL THEN 0 ELSE 1 END,
                 last_polled ASC
    """
    params: list[Any] = [cutoff]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [r["code"] for r in conn.execute(sql, params).fetchall()]


# ----------------------------------------------------------------- snapshots


def insert_snapshot(conn: sqlite3.Connection, reading: MetricReading) -> bool:
    """Append one reading. Returns True if it was new (dedup on captured_at)."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO snapshots
            (code, interval, captured_at, unique_players, peak_ccu, minutes_played,
             average_minutes_per_player, plays, favorites, recommendations,
             retention_d1, retention_d7, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reading.code,
            reading.interval,
            reading.captured_at,
            reading.unique_players,
            reading.peak_ccu,
            reading.minutes_played,
            reading.average_minutes_per_player,
            reading.plays,
            reading.favorites,
            reading.recommendations,
            reading.retention_d1,
            reading.retention_d7,
            utcnow(),
        ),
    )
    return cur.rowcount > 0


def insert_snapshots(conn: sqlite3.Connection, readings: Iterable[MetricReading]) -> int:
    return sum(1 for r in readings if insert_snapshot(conn, r))


def latest_snapshot(
    conn: sqlite3.Connection, code: str, interval: str = config.DEFAULT_INTERVAL
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM snapshots WHERE code=? AND interval=? "
        "ORDER BY captured_at DESC LIMIT 1",
        (code, interval),
    ).fetchone()


def snapshot_series(
    conn: sqlite3.Connection,
    code: str,
    interval: str = config.DEFAULT_INTERVAL,
    days: Optional[int] = None,
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM snapshots WHERE code=? AND interval=?"
    params: list[Any] = [code, interval]
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        sql += " AND captured_at >= ?"
        params.append(cutoff)
    sql += " ORDER BY captured_at ASC"
    return list(conn.execute(sql, params).fetchall())


def snapshot_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()["n"])


def latest_rows(
    conn: sqlite3.Connection,
    interval: str = config.DEFAULT_INTERVAL,
    *,
    limit: Optional[int] = None,
) -> list[sqlite3.Row]:
    """Most recent snapshot per island, joined onto island metadata.

    This is the workhorse behind every leaderboard in the dashboard.
    """
    sql = """
        SELECT i.code, i.title, i.creator_code, i.category, i.created_in,
               i.tags_json, i.genre, i.genre_confidence, i.genre_override,
               i.tracked, i.missing_since, i.first_seen, i.last_polled,
               s.captured_at, s.unique_players, s.peak_ccu, s.minutes_played,
               s.average_minutes_per_player, s.plays, s.favorites,
               s.recommendations, s.retention_d1, s.retention_d7
        FROM islands i
        JOIN snapshots s ON s.code = i.code AND s.interval = ?
        WHERE s.captured_at = (
            SELECT MAX(captured_at) FROM snapshots
            WHERE code = i.code AND interval = ?
        )
    """
    params: list[Any] = [interval, interval]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return list(conn.execute(sql, params).fetchall())


def snapshot_at_or_before(
    conn: sqlite3.Connection, code: str, when: str, interval: str = config.DEFAULT_INTERVAL
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM snapshots WHERE code=? AND interval=? AND captured_at <= ? "
        "ORDER BY captured_at DESC LIMIT 1",
        (code, interval, when),
    ).fetchone()


def history_span_days(conn: sqlite3.Connection, interval: str = config.DEFAULT_INTERVAL) -> float:
    row = conn.execute(
        "SELECT MIN(captured_at) AS lo, MAX(captured_at) AS hi FROM snapshots WHERE interval=?",
        (interval,),
    ).fetchone()
    if not row or not row["lo"] or not row["hi"]:
        return 0.0
    lo, hi = parse_ts(row["lo"]), parse_ts(row["hi"])
    if not lo or not hi:
        return 0.0
    return max((hi - lo).total_seconds() / 86400.0, 0.0)


# ------------------------------------------------------------- fortnite.gg


def insert_gg_sample(
    conn: sqlite3.Connection,
    code: str,
    observed_at: str,
    *,
    ccu: Optional[float] = None,
    peak_24h: Optional[float] = None,
    rank_overall: Optional[int] = None,
    favorites: Optional[float] = None,
    source: str = "fortnite.gg",
) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO gg_samples "
        "(code, observed_at, ccu, peak_24h, rank_overall, favorites, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, observed_at, ccu, peak_24h, rank_overall, favorites, source),
    )
    return cur.rowcount > 0


def gg_series(conn: sqlite3.Connection, code: str, days: Optional[int] = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM gg_samples WHERE code=?"
    params: list[Any] = [code]
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        sql += " AND observed_at >= ?"
        params.append(cutoff)
    sql += " ORDER BY observed_at ASC"
    return list(conn.execute(sql, params).fetchall())


def latest_gg_sample(conn: sqlite3.Connection, code: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM gg_samples WHERE code=? ORDER BY observed_at DESC LIMIT 1", (code,)
    ).fetchone()


# ------------------------------------------------------------- discovery rows


def insert_placement(
    conn: sqlite3.Connection,
    code: str,
    observed_at: str,
    row_key: str,
    *,
    row_label: Optional[str] = None,
    position: Optional[int] = None,
    source: str = "manual",
) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO discovery_placements "
        "(code, observed_at, row_key, row_label, position, source) VALUES (?, ?, ?, ?, ?, ?)",
        (code, observed_at, row_key, row_label, position, source),
    )
    return cur.rowcount > 0


def placements_for(conn: sqlite3.Connection, code: str, days: Optional[int] = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM discovery_placements WHERE code=?"
    params: list[Any] = [code]
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        sql += " AND observed_at >= ?"
        params.append(cutoff)
    sql += " ORDER BY observed_at ASC"
    return list(conn.execute(sql, params).fetchall())


def known_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT row_key, MAX(row_label) AS row_label, COUNT(*) AS observations, "
            "COUNT(DISTINCT code) AS islands, MAX(observed_at) AS last_seen "
            "FROM discovery_placements GROUP BY row_key ORDER BY observations DESC"
        ).fetchall()
    )


# ------------------------------------------------------------------ poll runs


def start_run(conn: sqlite3.Connection, kind: str) -> int:
    cur = conn.execute(
        "INSERT INTO poll_runs (kind, started_at) VALUES (?, ?)", (kind, utcnow())
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection, run_id: int, ok: int, failed: int, notes: str = ""
) -> None:
    conn.execute(
        "UPDATE poll_runs SET finished_at=?, ok=?, failed=?, notes=? WHERE id=?",
        (utcnow(), ok, failed, notes, run_id),
    )
    conn.commit()


def recent_runs(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return list(
        conn.execute("SELECT * FROM poll_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    )


# --------------------------------------------------------------------- utils


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse the ISO timestamps Epic returns, tolerating 'Z' and missing tz."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(str(value)[: len(fmt) + 2], fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def row_to_dict(row: Optional[sqlite3.Row]) -> dict:
    if row is None:
        return {}
    out = dict(row)
    if "tags_json" in out:
        try:
            out["tags"] = json.loads(out.pop("tags_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            out["tags"] = []
    return out


def rows_to_dicts(rows: Sequence[sqlite3.Row]) -> list[dict]:
    return [row_to_dict(r) for r in rows]


def stats(conn: sqlite3.Connection) -> dict:
    return {
        "islands": island_count(conn),
        "tracked": len(tracked_codes(conn)),
        "snapshots": snapshot_count(conn),
        "history_days": round(history_span_days(conn), 2),
        "gg_samples": int(conn.execute("SELECT COUNT(*) AS n FROM gg_samples").fetchone()["n"]),
        "placements": int(
            conn.execute("SELECT COUNT(*) AS n FROM discovery_placements").fetchone()["n"]
        ),
        "db_path": str(config.db_path()),
    }
