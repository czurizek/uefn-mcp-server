"""SQLite storage. Its whole job is knowing what is genuinely new since last scan."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    uid           TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    profile       TEXT NOT NULL,
    name          TEXT NOT NULL,
    url           TEXT NOT NULL,
    description   TEXT,
    stars         INTEGER DEFAULT 0,
    updated_at    TEXT,
    language      TEXT,
    topics        TEXT,
    score         REAL DEFAULT 0,
    breakdown     TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    review_status TEXT DEFAULT 'new',
    note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_findings_profile ON findings(profile);
CREATE INDEX IF NOT EXISTS idx_findings_score   ON findings(score DESC);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    profiles   TEXT NOT NULL,
    sources    TEXT NOT NULL,
    seen       INTEGER DEFAULT 0,
    added      INTEGER DEFAULT 0,
    errors     TEXT
);
"""

REVIEW_STATUSES = ("new", "watching", "adopted", "rejected")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Finding:
    """One candidate tool, normalised across every source."""

    uid: str
    source: str
    profile: str
    name: str
    url: str
    description: str = ""
    stars: int = 0
    updated_at: str = ""
    language: str = ""
    topics: list[str] = field(default_factory=list)
    score: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)

    def haystack(self) -> str:
        return " ".join([self.name, self.description, " ".join(self.topics)]).lower()

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["topics"] = json.dumps(self.topics)
        row["breakdown"] = json.dumps(self.breakdown)
        return row


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert(conn: sqlite3.Connection, finding: Finding) -> bool:
    """Insert or refresh. Returns True when this uid had never been seen before."""
    now = utcnow()
    row = finding.to_row()
    existing = conn.execute(
        "SELECT uid FROM findings WHERE uid = ?", (finding.uid,)
    ).fetchone()

    if existing is None:
        conn.execute(
            """INSERT INTO findings
               (uid, source, profile, name, url, description, stars, updated_at,
                language, topics, score, breakdown, first_seen, last_seen)
               VALUES (:uid, :source, :profile, :name, :url, :description, :stars,
                       :updated_at, :language, :topics, :score, :breakdown, :first, :last)""",
            {**row, "first": now, "last": now},
        )
        return True

    # Keep first_seen and any human review verdict; refresh the volatile fields.
    conn.execute(
        """UPDATE findings SET
             name = :name, url = :url, description = :description, stars = :stars,
             updated_at = :updated_at, language = :language, topics = :topics,
             score = :score, breakdown = :breakdown, last_seen = :last
           WHERE uid = :uid""",
        {**row, "last": now},
    )
    return False


def record_run(
    conn: sqlite3.Connection,
    profiles: list[str],
    sources: list[str],
    seen: int,
    added: int,
    errors: list[str],
) -> int:
    cur = conn.execute(
        """INSERT INTO runs (started_at, profiles, sources, seen, added, errors)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (utcnow(), ",".join(profiles), ",".join(sources), seen, added, json.dumps(errors)),
    )
    return int(cur.lastrowid or 0)


def query(
    conn: sqlite3.Connection,
    profile: str | None = None,
    min_score: float = 0.0,
    new_only: bool = False,
    since_run: bool = False,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    sql = ["SELECT * FROM findings WHERE score >= ?"]
    args: list[Any] = [min_score]

    if profile:
        sql.append("AND profile = ?")
        args.append(profile)
    if status:
        sql.append("AND review_status = ?")
        args.append(status)
    if new_only:
        sql.append("AND first_seen = last_seen")
    if since_run:
        last = conn.execute("SELECT started_at FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if last:
            sql.append("AND first_seen >= ?")
            args.append(last["started_at"])

    sql.append("ORDER BY score DESC, stars DESC LIMIT ?")
    args.append(limit)

    rows = conn.execute(" ".join(sql), args).fetchall()
    return [_inflate(r) for r in rows]


def get(conn: sqlite3.Connection, uid: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM findings WHERE uid = ?", (uid,)).fetchone()
    return _inflate(row) if row else None


def mark(conn: sqlite3.Connection, uid: str, status: str, note: str | None = None) -> bool:
    if status not in REVIEW_STATUSES:
        raise ValueError(f"status must be one of {REVIEW_STATUSES}")
    cur = conn.execute(
        "UPDATE findings SET review_status = ?, note = COALESCE(?, note) WHERE uid = ?",
        (status, note, uid),
    )
    return cur.rowcount > 0


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) AS c FROM findings").fetchone()["c"]
    by_profile = {
        r["profile"]: r["c"]
        for r in conn.execute(
            "SELECT profile, COUNT(*) AS c FROM findings GROUP BY profile ORDER BY c DESC"
        )
    }
    runs = conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"]
    last = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "total_findings": total,
        "by_profile": by_profile,
        "runs": runs,
        "last_run": dict(last) if last else None,
        "db": str(db_path()),
    }


def _inflate(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["topics"] = json.loads(data.get("topics") or "[]")
    data["breakdown"] = json.loads(data.get("breakdown") or "{}")
    return data
