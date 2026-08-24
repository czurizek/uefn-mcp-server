"""MCP Server for Fortnite island analytics.

Exposes the `fngg` analytics engine to Claude Code, so island questions can be
asked in the same session where the map is being built in UEFN — "how does my RP
city compare to the cohort", "what is holding it out of Discover", "who is
rising in FFA this week".

Requires: pip install mcp

Usage:
    python fngg_mcp_server.py

Claude Code config (project .mcp.json or ~/.claude/settings.json):
    {
      "mcpServers": {
        "fngg": {
          "command": "python",
          "args": ["/path/to/uefn-mcp-server/fngg_mcp_server.py"]
        }
      }
    }

All data comes from Epic's public Ecosystem API and your own local polling
history. Nothing here talks to the UEFN editor — that is `mcp_server.py`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # mcp >= 2.0 renamed FastMCP to MCPServer; the tool/run API is unchanged.
    from mcp.server.mcpserver import MCPServer as _McpServer
except ImportError:  # pragma: no cover - depends on which SDK version is installed
    try:
        from mcp.server.fastmcp import FastMCP as _McpServer
    except ImportError:
        print(
            "This server requires the MCP SDK. Install it with:  pip install mcp",
            file=sys.stderr,
        )
        raise

from fngg import config, poll as poller, report as reporting, store
from fngg.analytics import build_dataset
from fngg.genres import GENRE_LABELS, all_genres, label_of
from fngg.sources import ecosystem, fortnitegg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Building a dataset walks the whole database, so hold one per process and
# rebuild only when the file changes. Tool calls arrive in bursts.
_cache: dict = {"dataset": None, "mtime": 0.0, "window": 7}


def _dataset(window_days: int = 7):
    try:
        mtime = Path(config.db_path()).stat().st_mtime
    except OSError:
        mtime = 0.0
    if (
        _cache["dataset"] is not None
        and _cache["mtime"] == mtime
        and _cache["window"] == window_days
    ):
        return _cache["dataset"]
    conn = store.connect()
    try:
        store.init_db(conn)
        dataset = build_dataset(conn, window_days=window_days)
    finally:
        conn.close()
    _cache.update({"dataset": dataset, "mtime": mtime, "window": window_days})
    return dataset


def _dump(payload) -> str:
    return json.dumps(payload, indent=2, default=str)


def _slim(row: dict) -> dict:
    """A row trimmed to what an assistant needs, without the nested internals."""
    return {
        "code": row.get("code"),
        "title": row.get("title"),
        "creator_code": row.get("creator_code"),
        "genre": row.get("genre"),
        "genre_label": label_of(row.get("genre")),
        "discovery_score": row.get("discovery_score"),
        "components": row.get("discovery_components"),
        "best_row": (row.get("best_row") or {}).get("label"),
        "top_lever": (row.get("discovery_top_lever") or {}).get("label"),
        "unique_players": row.get("unique_players"),
        "peak_ccu": row.get("peak_ccu"),
        "minutes_per_player": row.get("minutes_per_player"),
        "retention_d1": row.get("retention_d1"),
        "retention_d7": row.get("retention_d7"),
        "growth_7d": row.get("growth_7d"),
        "rank_delta_7d": row.get("rank_delta_7d"),
        "genre_rank": row.get("genre_rank"),
        "genre_size": row.get("genre_size"),
    }


def _no_data_hint() -> dict:
    return {
        "error": "no local data",
        "hint": (
            "Populate the database first: `fngg sync` pulls Epic's catalogue, `fngg poll` takes "
            "a reading, `fngg demo` loads sample data. Epic serves one live reading per metric "
            "and never backfills, so history only exists from the moment you start polling."
        ),
        "db_path": str(config.db_path()),
    }


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = _McpServer(
    "fngg",
    instructions=(
        "Fortnite island browsing and Discovery analytics, tuned for RP, FFA and open-world "
        "maps. Data comes from Epic's public Ecosystem API plus a local polling history.\n\n"
        "Two things to keep in mind when interpreting results:\n"
        "1. Every score is a PERCENTILE inside a genre cohort, not an absolute. A retention of "
        "14% is weak for an RP city and strong for a box-fight map, so cross-genre comparison "
        "of raw metrics is meaningless — compare percentiles instead.\n"
        "2. Discovery Fitness is a model built on Epic's *documented* Discover inputs, not "
        "Epic's actual ranking formula. Present it as a diagnostic, never as a prediction, and "
        "pass along its caveats when the user is making a decision on it.\n\n"
        "If a tool reports no local data, the fix is `fngg sync` then `fngg poll` "
        "(or `fngg demo` for sample data) — not retrying the tool."
    ),
)


# -- Analysis ---------------------------------------------------------------


@mcp.tool()
def island_report(code: str, as_text: bool = True) -> str:
    """Full Discovery analysis for one island: fitness score, component percentiles,
    the ranked list of levers worth fixing, Discover row fit, momentum and every
    metric against its genre cohort.

    Args:
        code: island code, e.g. "1865-4829-7018"
        as_text: formatted report (True) or raw structured data (False)
    """
    dataset = _dataset()
    data = reporting.island_report(dataset, code)
    if not data:
        return _dump(
            {
                "error": f"{code} is not in the local database",
                "hint": f"Add it with `fngg track {code}` then `fngg poll --tracked`.",
            }
        )
    return reporting.format_island_report(data) if as_text else _dump(data)


@mcp.tool()
def discovery_leaderboard(genre: str = "all", limit: int = 20) -> str:
    """Islands ranked by Discovery Fitness, optionally within one genre.

    Args:
        genre: "all", or one of rp, ffa, open_world, box_fight, zone_wars, practice,
               tycoon, horror, parkour, puzzle, racing, pve, party, battle_royale, music, other
        limit: how many to return
    """
    dataset = _dataset()
    if not dataset.rows:
        return _dump(_no_data_hint())
    rows = [
        r
        for r in dataset.filter(genre=None if genre == "all" else genre)
        if r.get("discovery_score") is not None
    ]
    rows.sort(key=lambda r: -r["discovery_score"])
    return _dump(
        {
            "genre": genre,
            "cohort_size": len(rows),
            "islands": [_slim(r) for r in rows[:limit]],
        }
    )


@mcp.tool()
def row_fit(code: str) -> str:
    """How well one island fits each Discover row (Popular, Trending, New Releases,
    By Players Like You, Community Choice, Top Charts), with the note on what each
    row actually rewards. Curated rows are reported as not-modelled.
    """
    dataset = _dataset()
    row = dataset.get(code)
    if not row:
        return _dump({"error": f"{code} is not in the local database"})
    return _dump(
        {
            "code": code,
            "title": row.get("title"),
            "genre": row.get("genre"),
            "rows": row.get("row_fit"),
            "components": row.get("discovery_components"),
        }
    )


@mcp.tool()
def movers(genre: str = "all", falling: bool = False, limit: int = 15, min_players: float = 50) -> str:
    """Biggest 7-day risers or fallers by unique players. Needs at least three days
    of local polling history to return anything.

    Args:
        genre: "all" or a specific genre
        falling: True for decliners instead of risers
        limit: how many to return
        min_players: ignore islands below this player count
    """
    dataset = _dataset()
    rows = dataset.movers(
        limit=limit,
        genre=None if genre == "all" else genre,
        rising=not falling,
        min_players=min_players,
    )
    if not rows:
        return _dump(
            {
                "islands": [],
                "note": (
                    "No island has enough polling history for trend analysis yet. Epic returns one "
                    "live reading and never backfills, so momentum appears after ~3 days of polling."
                ),
                "history_days": dataset.history_days,
            }
        )
    return _dump({"direction": "falling" if falling else "rising", "islands": [_slim(r) for r in rows]})


@mcp.tool()
def benchmarks(genre: str = "rp") -> str:
    """Percentile table (p10/p25/median/p75/p90) for every metric within one genre —
    what "good" actually looks like for that format.
    """
    dataset = _dataset()
    if not dataset.rows:
        return _dump(_no_data_hint())
    table = dataset.cohorts.summary_table(genre)
    resolved = dataset.cohorts.resolve_key(genre, "unique_players")
    return _dump(
        {
            "genre": genre,
            "genre_label": label_of(genre),
            "cohort_used": resolved,
            "fell_back": resolved != genre,
            "metrics": table,
        }
    )


@mcp.tool()
def search_islands(query: str = "", genre: str = "all", limit: int = 25, sort: str = "unique_players") -> str:
    """Search the local catalogue by title, code, creator or tag.

    Args:
        query: free text; empty returns the whole (filtered) catalogue
        genre: "all" or a specific genre
        limit: how many to return
        sort: any metric name, e.g. unique_players, peak_ccu, retention_d7, discovery_score
    """
    dataset = _dataset()
    if not dataset.rows:
        return _dump(_no_data_hint())
    rows = dataset.filter(genre=None if genre == "all" else genre, query=query or None)
    rows.sort(key=lambda r: (r.get(sort) is None, -(r.get(sort) or 0)))
    return _dump({"matches": len(rows), "islands": [_slim(r) for r in rows[:limit]]})


@mcp.tool()
def compare_islands(codes: str) -> str:
    """Compare islands side by side on cohort percentiles.

    Args:
        codes: comma-separated island codes
    """
    dataset = _dataset()
    wanted = [c.strip() for c in codes.split(",") if c.strip()]
    found = []
    missing = []
    for code in wanted:
        row = dataset.get(code)
        if row:
            entry = _slim(row)
            entry["percentiles"] = row.get("percentiles")
            entry["levers"] = row.get("discovery_levers")
            found.append(entry)
        else:
            missing.append(code)
    return _dump({"islands": found, "not_in_database": missing})


@mcp.tool()
def genre_breakdown() -> str:
    """How the local catalogue splits across genres, and how much history exists."""
    dataset = _dataset()
    return _dump(dataset.summary())


# -- Data management --------------------------------------------------------


@mcp.tool()
def track_island(code: str, remove: bool = False) -> str:
    """Mark an island as tracked so it is polled first on every run. Fetches its
    metadata from Epic if it is not in the local catalogue yet.
    """
    conn = store.connect()
    try:
        store.init_db(conn)
        if not store.get_island(conn, code):
            island = ecosystem.fetch_island(code)
            if not island:
                return _dump({"error": f"{code} is not public or not discoverable"})
            store.upsert_island(conn, island)
        store.set_tracked(conn, code, not remove)
        conn.commit()
        row = store.row_to_dict(store.get_island(conn, code))
    finally:
        conn.close()
    _cache["dataset"] = None
    return _dump({"tracked": not remove, "island": row})


@mcp.tool()
def set_genre(code: str, genre: str) -> str:
    """Override an island's genre when the automatic classifier gets it wrong.
    Pass "auto" to clear the override. This changes which cohort the island is
    benchmarked against, so it materially changes its scores.
    """
    if genre != "auto" and genre not in GENRE_LABELS:
        return _dump({"error": "unknown genre", "options": all_genres() + ["auto"]})
    conn = store.connect()
    try:
        store.init_db(conn)
        if not store.get_island(conn, code):
            return _dump({"error": f"{code} is not in the local database"})
        store.set_genre_override(conn, code, None if genre == "auto" else genre)
        conn.commit()
    finally:
        conn.close()
    _cache["dataset"] = None
    return _dump({"code": code, "genre": genre})


@mcp.tool()
def poll_now(limit: int = 200, tracked_only: bool = False, interval: str = "day") -> str:
    """Take a fresh metric reading from Epic and append it to the local history.

    Args:
        limit: maximum islands to poll this run
        tracked_only: only poll islands marked as tracked
        interval: "day" (default), "hour" or "minute"
    """
    lines: list[str] = []
    conn = store.connect()
    try:
        store.init_db(conn)
        result = poller.poll_all(
            conn,
            limit=limit,
            interval=interval,
            tracked_only=tracked_only,
            progress=lines.append,
        )
        result["database"] = store.stats(conn)
    finally:
        conn.close()
    _cache["dataset"] = None
    result["log"] = lines[-10:]
    return _dump(result)


@mcp.tool()
def sync_catalog(limit: int = 1000) -> str:
    """Walk Epic's island catalogue and add what it returns to the local database.
    Run this before polling so there is something to poll.
    """
    lines: list[str] = []
    conn = store.connect()
    try:
        store.init_db(conn)
        result = poller.sync_catalog(conn, limit=limit, progress=lines.append)
        result["islands_total"] = store.island_count(conn)
    finally:
        conn.close()
    _cache["dataset"] = None
    result["log"] = lines[-10:]
    return _dump(result)


@mcp.tool()
def database_stats() -> str:
    """What is in the local database: island count, snapshot count, how many days of
    history exist, and recent poll runs.
    """
    conn = store.connect()
    try:
        store.init_db(conn)
        stats = store.stats(conn)
        stats["recent_runs"] = [dict(r) for r in store.recent_runs(conn, 5)]
    finally:
        conn.close()
    return _dump(stats)


@mcp.tool()
def probe_fortnitegg(code: str = "1865-4829-7018") -> str:
    """Check whether fortnite.gg is reachable from this machine and which of the
    adapter's URL strategies return parseable island records. This source is
    optional — everything Ecosystem-backed works without it.
    """
    result = fortnitegg.probe(sample_code=code)
    conn = store.connect()
    try:
        store.init_db(conn)
        store.set_meta(conn, "gg_probe", json.dumps(result))
        conn.commit()
    finally:
        conn.close()
    return _dump(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
