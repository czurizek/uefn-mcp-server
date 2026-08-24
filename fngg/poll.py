"""Catalogue sync and metric polling.

The polling loop is the whole point of this package. Epic's API returns a single
live reading per metric and rejects `from` values older than about six days, so
the local snapshot log is the only history that will ever exist for these
islands. A day not polled is a day permanently lost.

`day` is the right default cadence: that bucket only rolls over once a day, and
`insert_snapshot` dedups on `captured_at`, so polling it more often writes
nothing. Use `--interval hour` when you need finer resolution on a small tracked
set and can afford the extra requests.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from . import config, store
from .http_client import HttpError
from .sources import ecosystem
from .sources import fortnitegg as gg

Progress = Callable[[str], None]


def _default_progress(message: str) -> None:
    print(message, flush=True)


# ------------------------------------------------------------------ catalogue


def sync_catalog(
    conn: sqlite3.Connection,
    *,
    limit: Optional[int] = None,
    resume: bool = True,
    progress: Progress = _default_progress,
) -> dict:
    """Walk Epic's island catalogue and upsert what it returns.

    The cursor is checkpointed after every page, so an interrupted crawl of a
    large catalogue resumes where it stopped instead of restarting.
    """
    limit = limit if limit is not None else config.DEFAULT_CATALOG_LIMIT
    run_id = store.start_run(conn, "sync")
    cursor = store.get_meta(conn, "catalog_cursor") if resume else None
    if cursor:
        progress("resuming catalogue sync from saved cursor")

    seen = 0
    added = 0
    failed = 0
    before = store.island_count(conn)
    started = time.monotonic()

    try:
        for island, next_cursor in ecosystem.iter_islands(limit=limit, start_cursor=cursor):
            store.upsert_island(conn, island)
            seen += 1
            if seen % 100 == 0:
                store.set_meta(conn, "catalog_cursor", next_cursor)
                conn.commit()
                rate = seen / max(time.monotonic() - started, 0.001)
                progress(f"  {seen} islands ({rate:.0f}/s)")
            if next_cursor is None and seen % 100 != 0:
                store.set_meta(conn, "catalog_cursor", None)
    except HttpError as exc:
        failed += 1
        progress(f"  ! catalogue sync stopped: {exc}")
    finally:
        conn.commit()

    added = store.island_count(conn) - before
    notes = f"walked {seen}, new {added}"
    store.finish_run(conn, run_id, ok=seen, failed=failed, notes=notes)
    progress(f"catalogue: walked {seen} islands, {added} new, {failed} errors")
    return {"walked": seen, "added": added, "failed": failed}


# -------------------------------------------------------------------- metrics


def poll_metrics(
    conn: sqlite3.Connection,
    codes: Sequence[str],
    *,
    interval: str = config.DEFAULT_INTERVAL,
    progress: Progress = _default_progress,
    full_series: bool = False,
) -> dict:
    """Fetch the current reading for each code and append it to the log."""
    run_id = store.start_run(conn, f"poll:{interval}")
    written = 0
    duplicates = 0
    missing = 0
    failed = 0
    started = time.monotonic()

    for index, code in enumerate(codes, start=1):
        try:
            if full_series:
                readings = ecosystem.fetch_full_series(code, interval)
            else:
                reading = ecosystem.fetch_latest_metrics(code, interval)
                readings = [reading] if reading else []
        except HttpError as exc:
            failed += 1
            progress(f"  ! {code}: {exc}")
            continue

        if not readings:
            missing += 1
            store.mark_missing(conn, code)
        else:
            for reading in readings:
                if store.insert_snapshot(conn, reading):
                    written += 1
                else:
                    duplicates += 1
            store.mark_polled(conn, code)

        if index % 25 == 0:
            conn.commit()
            rate = index / max(time.monotonic() - started, 0.001)
            progress(f"  {index}/{len(codes)} polled ({rate:.1f}/s, {written} new)")

    conn.commit()
    notes = f"new {written}, dup {duplicates}, missing {missing}"
    store.finish_run(conn, run_id, ok=written, failed=failed, notes=notes)
    progress(
        f"poll: {written} new readings, {duplicates} already had this timestamp, "
        f"{missing} not discoverable, {failed} errors"
    )
    return {
        "written": written,
        "duplicates": duplicates,
        "missing": missing,
        "failed": failed,
    }


def poll_all(
    conn: sqlite3.Connection,
    *,
    limit: Optional[int] = None,
    interval: str = config.DEFAULT_INTERVAL,
    tracked_only: bool = False,
    progress: Progress = _default_progress,
) -> dict:
    codes = (
        store.tracked_codes(conn) if tracked_only else store.poll_candidates(conn, limit=limit)
    )
    if not codes:
        progress("nothing to poll — run `fngg sync` first, or `fngg track <code>`")
        return {"written": 0, "duplicates": 0, "missing": 0, "failed": 0}
    progress(f"polling {len(codes)} islands on the {interval} interval")
    return poll_metrics(conn, codes, interval=interval, progress=progress)


# ---------------------------------------------------------------- fortnite.gg


def poll_gg_live(
    conn: sqlite3.Connection, codes: Sequence[str], *, progress: Progress = _default_progress
) -> dict:
    """Sample live concurrency from fortnite.gg for the given islands."""
    run_id = store.start_run(conn, "gg:live")
    now = gg.now_iso()
    written = 0
    failed = 0
    for code in codes:
        try:
            sample = gg.fetch_island_live(code)
        except Exception as exc:  # adapter must never break the poll loop
            failed += 1
            progress(f"  ! {code}: {exc}")
            continue
        if not sample:
            failed += 1
            continue
        if store.insert_gg_sample(
            conn,
            code,
            now,
            ccu=sample.ccu,
            peak_24h=sample.peak_24h,
            rank_overall=sample.rank_overall,
            favorites=sample.favorites,
        ):
            written += 1
    conn.commit()
    store.finish_run(conn, run_id, ok=written, failed=failed, notes="fortnite.gg live samples")
    progress(f"fortnite.gg: {written} live samples, {failed} unavailable")
    return {"written": written, "failed": failed}


def poll_gg_discovery(conn: sqlite3.Connection, *, progress: Progress = _default_progress) -> dict:
    """Record which Discover rows islands are currently sitting in."""
    run_id = store.start_run(conn, "gg:discovery")
    now = gg.now_iso()
    written = 0
    try:
        entries = gg.fetch_discovery()
    except Exception as exc:
        store.finish_run(conn, run_id, ok=0, failed=1, notes=str(exc)[:200])
        progress(f"fortnite.gg discovery unavailable: {exc}")
        return {"written": 0, "failed": 1}

    for entry in entries:
        if not entry.code or not entry.row_key:
            continue
        if store.insert_placement(
            conn,
            entry.code,
            now,
            entry.row_key,
            row_label=entry.row_label,
            position=entry.position,
            source="fortnite.gg",
        ):
            written += 1
    conn.commit()
    store.finish_run(conn, run_id, ok=written, failed=0, notes=f"{len(entries)} tiles seen")
    progress(f"fortnite.gg: {written} Discover placements recorded")
    return {"written": written, "failed": 0}


# ---------------------------------------------------------------------- watch


def watch(
    conn: sqlite3.Connection,
    *,
    every_minutes: float = 360.0,
    limit: Optional[int] = None,
    interval: str = config.DEFAULT_INTERVAL,
    tracked_only: bool = False,
    with_gg: bool = False,
    progress: Progress = _default_progress,
) -> None:
    """Poll on a loop until interrupted.

    Six hours is the default because the `day` bucket only rolls over once a day
    and polling four times gives comfortable margin against a missed run without
    generating meaningful extra load.
    """
    progress(
        f"watching: polling every {every_minutes:.0f} min on the {interval} interval. "
        f"ctrl-c to stop."
    )
    while True:
        started = datetime.now(timezone.utc)
        progress(f"\n[{started.isoformat(timespec='seconds')}] poll starting")
        try:
            poll_all(
                conn, limit=limit, interval=interval, tracked_only=tracked_only, progress=progress
            )
            if with_gg:
                codes = store.tracked_codes(conn) or store.poll_candidates(conn, limit=40)
                poll_gg_live(conn, codes[:40], progress=progress)
                poll_gg_discovery(conn, progress=progress)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            progress(f"  ! poll failed, will retry next cycle: {exc}")

        try:
            time.sleep(every_minutes * 60)
        except KeyboardInterrupt:
            progress("\nstopped")
            return


__all__ = [
    "sync_catalog",
    "poll_metrics",
    "poll_all",
    "poll_gg_live",
    "poll_gg_discovery",
    "watch",
]
