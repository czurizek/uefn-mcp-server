"""Command line interface.

    fngg demo          load sample data and look around immediately
    fngg sync          pull Epic's island catalogue into the local database
    fngg poll          take a metric reading for every island you track
    fngg watch         keep polling on a loop (this is what builds history)
    fngg serve         open the dashboard
    fngg report CODE   full analysis of one island in the terminal
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__, config, poll, report as reporting, seed, store
from .analytics import build_dataset
from .analytics.kpis import KPIS, format_kpi
from .genres import GENRE_LABELS, all_genres, label_of
from .sources import fortnitegg


def _dataset(conn, window_days: int = 7):
    return build_dataset(conn, window_days=window_days)


def _die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


# ------------------------------------------------------------------- commands


def cmd_demo(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        if args.reset:
            conn.executescript(
                "DELETE FROM snapshots; DELETE FROM islands; DELETE FROM gg_samples; "
                "DELETE FROM discovery_placements; DELETE FROM poll_runs;"
            )
            conn.commit()
            print("cleared existing data")
        info = seed.load_into(conn, count=args.count, days=args.days, seed=args.seed)
    print(
        f"loaded {info['islands']} sample islands with {info['snapshots']} snapshots "
        f"across {info['days']} days"
    )
    print(f"database: {config.db_path()}")
    print("\nthis is synthetic data for exploring the interface — run `fngg sync` for real islands")
    print("next: fngg serve")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        if args.fresh:
            store.set_meta(conn, "catalog_cursor", None)
            conn.commit()
        poll.sync_catalog(conn, limit=args.limit, resume=not args.fresh)
        print(f"\ncatalogue now holds {store.island_count(conn)} islands")
        print("next: fngg poll")
    return 0


def cmd_poll(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        poll.poll_all(
            conn,
            limit=args.limit,
            interval=args.interval,
            tracked_only=args.tracked,
        )
        if args.gg:
            codes = store.tracked_codes(conn) or store.poll_candidates(conn, limit=40)
            poll.poll_gg_live(conn, codes[:40])
            poll.poll_gg_discovery(conn)
        stats = store.stats(conn)
    print(f"\n{stats['snapshots']} readings stored, {stats['history_days']} days of history")
    if stats["history_days"] < 3:
        print("trend analysis needs roughly three days of polling — keep going")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        try:
            poll.watch(
                conn,
                every_minutes=args.every,
                limit=args.limit,
                interval=args.interval,
                tracked_only=args.tracked,
                with_gg=args.gg,
            )
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web.server import serve

    serve(args.host, args.port, open_browser=args.open)
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    print("probing fortnite.gg from this machine…\n")
    result = fortnitegg.probe(sample_code=args.code)
    for kind, attempts in result["strategies"].items():
        print(f"{kind}:")
        for attempt in attempts:
            mark = "ok  " if attempt["ok"] else "fail"
            extra = f"  ({attempt['records']} records)" if attempt.get("records") else ""
            print(f"  [{mark}] {attempt['url']}")
            print(f"         {attempt['detail'][:100]}{extra}")
        print()

    if result["usable"]:
        print("fortnite.gg is reachable and at least one parser found island records.")
    else:
        print("fortnite.gg produced no usable records from this machine.")
        print("Everything backed by Epic's Ecosystem API still works — this source is optional.")
        print(f"To add your own URL candidates, edit {config.data_dir() / 'fortnitegg_strategies.json'}")

    with store.open_db() as conn:
        store.set_meta(conn, "gg_probe", json.dumps(result))
        conn.commit()
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    print("capturing fortnite.gg page structure from this machine…\n")
    bundle = fortnitegg.capture(sample_code=args.code, fetch_scripts=args.scripts)

    reachable = False
    for kind, page in bundle["pages"].items():
        resolved = page.get("resolved_url")
        if not resolved:
            print(f"{kind:10} unreachable — {len(page.get('attempts', []))} URLs tried")
            continue
        reachable = True
        print(f"{kind:10} {resolved}")
        print(f"           {page.get('bytes', 0):,} bytes · "
              f"{page.get('island_codes_found', 0)} island codes · "
              f"{page.get('current_parser_count', 0)} parsed by the current adapter")
        if page.get("data_urls_in_markup"):
            print(f"           data-shaped URLs: {', '.join(page['data_urls_in_markup'][:4])}")
        for entry in page.get("script_scan") or []:
            if entry.get("data_urls"):
                print(f"           in {entry['url'].rsplit('/', 1)[-1]}: "
                      f"{', '.join(entry['data_urls'][:4])}")
        print()

    out = Path(args.out) if args.out else config.data_dir() / "fortnitegg-capture.json"
    out.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")

    if not reachable:
        print("\nfortnite.gg did not respond at all from this machine.")
        return 0

    print(
        "\nThis bundle holds public page metadata only — resolved URLs, JSON key names, "
        "and short markup snippets around island codes. Attach it when asking for exact "
        "parsers to be written against the live markup."
    )
    return 0


def cmd_track(args: argparse.Namespace) -> int:
    from .sources import ecosystem

    with store.open_db() as conn:
        for code in args.codes:
            existing = store.get_island(conn, code)
            if not existing:
                island = ecosystem.fetch_island(code)
                if not island:
                    print(f"  {code}: not public / not discoverable — skipped")
                    continue
                store.upsert_island(conn, island)
                print(f"  {code}: added ({island.title})")
            store.set_tracked(conn, code, not args.remove)
            print(f"  {code}: {'untracked' if args.remove else 'tracked'}")
        conn.commit()
        if not args.remove:
            print("\npolling these first from now on. Run `fngg poll` to take a reading.")
    return 0


def cmd_genre(args: argparse.Namespace) -> int:
    if args.genre not in GENRE_LABELS and args.genre != "auto":
        _die(f"unknown genre {args.genre!r}. Options: {', '.join(all_genres())}, or 'auto'")
    with store.open_db() as conn:
        if not store.get_island(conn, args.code):
            _die(f"{args.code} is not in the local database — `fngg track {args.code}` first")
        store.set_genre_override(conn, args.code, None if args.genre == "auto" else args.genre)
        conn.commit()
    target = "automatic classification" if args.genre == "auto" else label_of(args.genre)
    print(f"{args.code} → {target}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        dataset = _dataset(conn, args.window)
        data = reporting.island_report(dataset, args.code)
    if not data:
        _die(
            f"no local data for {args.code}. Try: fngg track {args.code} && fngg poll --tracked"
        )
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(reporting.format_island_report(data))
    return 0


def cmd_top(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        dataset = _dataset(conn, args.window)
        rows = dataset.filter(genre=args.genre)
        rows = [r for r in rows if r.get(args.metric) is not None]
        rows.sort(key=lambda r: -r[args.metric])
    if not rows:
        print("no islands match — run `fngg sync && fngg poll`, or `fngg demo` for sample data")
        return 0
    scope = label_of(args.genre) if args.genre and args.genre != "all" else "all genres"
    print(f"top {min(args.limit, len(rows))} by {args.metric} — {scope}\n")
    print(reporting.format_leaderboard(rows, limit=args.limit))
    return 0


def cmd_movers(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        dataset = _dataset(conn, args.window)
        rows = dataset.movers(
            limit=args.limit, genre=args.genre, rising=not args.falling, min_players=args.min
        )
    if not rows:
        print("no islands have enough polling history yet for trend analysis.")
        print("Epic serves one live reading and never backfills — keep `fngg watch` running.")
        return 0
    direction = "falling" if args.falling else "rising"
    print(f"{direction} — {args.window}d change in unique players\n")
    header = f"{'ISLAND':<34} {'GENRE':<18} {'PLAYERS':>9} {'CHANGE':>9} {'RANK Δ':>7}"
    print(header)
    print("-" * len(header))
    for row in rows:
        growth = row.get("growth_7d")
        delta = row.get("rank_delta_7d")
        print(
            f"{(row.get('title') or row['code'])[:34]:<34} "
            f"{label_of(row.get('genre'))[:18]:<18} "
            f"{format_kpi('unique_players', row.get('unique_players')):>9} "
            f"{(f'{growth * 100:+.1f}%' if growth is not None else '–'):>9} "
            f"{(f'{delta:+d}' if delta is not None else '–'):>7}"
        )
    return 0


def cmd_benchmarks(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        dataset = _dataset(conn)
        table = dataset.cohorts.summary_table(args.genre)
        resolved = dataset.cohorts.resolve_key(args.genre, "unique_players")
    print(f"{label_of(args.genre)} benchmarks (cohort: {resolved})\n")
    header = f"{'METRIC':<26} {'n':>4} {'p10':>10} {'p25':>10} {'p50':>10} {'p75':>10} {'p90':>10}"
    print(header)
    print("-" * len(header))
    for entry in table:
        metric = entry["metric"]
        print(
            f"{metric:<26} {entry['count']:>4} "
            + " ".join(f"{format_kpi(metric, entry.get(f'p{p}')):>10}" for p in (10, 25, 50, 75, 90))
        )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        stats = store.stats(conn)
        runs = store.recent_runs(conn, 5)
    for key, value in stats.items():
        print(f"{key:<16} {value}")
    if runs:
        print("\nrecent runs:")
        for run in runs:
            print(
                f"  {str(run['started_at'])[:19]}  {run['kind']:<14} "
                f"ok={run['ok']} failed={run['failed']}  {run['notes'] or ''}"
            )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    with store.open_db() as conn:
        dataset = _dataset(conn, args.window)
        rows = dataset.filter(genre=args.genre)

    fields = [
        "code", "title", "creator_code", "genre", "genre_confidence",
        "discovery_score", "growth_7d", "rank_delta_7d", "age_days", *KPIS,
    ]
    records = [{f: row.get(f) for f in fields} for row in rows]

    if args.format == "json":
        payload = json.dumps(records, indent=2, default=str)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(payload)
        else:
            print(payload)
    else:
        handle = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
        try:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
        finally:
            if args.out:
                handle.close()
    if args.out:
        print(f"wrote {len(records)} rows to {args.out}")
    return 0


# --------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fngg",
        description="Browse and analyse Fortnite islands, with Discovery analytics tuned for "
        "RP, FFA and open-world maps.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--version", action="version", version=f"fngg {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("demo", help="load synthetic data so you can explore the interface")
    p.add_argument("--count", type=int, default=140, help="islands to generate")
    p.add_argument("--days", type=int, default=21, help="days of history to fabricate")
    p.add_argument("--seed", type=int, default=20260824)
    p.add_argument("--reset", action="store_true", help="wipe existing data first")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("sync", help="pull Epic's island catalogue")
    p.add_argument("--limit", type=int, default=None, help="stop after N islands")
    p.add_argument("--fresh", action="store_true", help="ignore the saved resume cursor")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("poll", help="take one metric reading per island")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--interval", choices=config.INTERVALS, default=config.DEFAULT_INTERVAL)
    p.add_argument("--tracked", action="store_true", help="only islands you track")
    p.add_argument("--gg", action="store_true", help="also sample fortnite.gg")
    p.set_defaults(func=cmd_poll)

    p = sub.add_parser("watch", help="poll on a loop — this is what builds history")
    p.add_argument("--every", type=float, default=360.0, help="minutes between polls")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--interval", choices=config.INTERVALS, default=config.DEFAULT_INTERVAL)
    p.add_argument("--tracked", action="store_true")
    p.add_argument("--gg", action="store_true")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("serve", help="open the dashboard")
    p.add_argument("--host", default=config.WEB_HOST)
    p.add_argument("--port", type=int, default=config.WEB_PORT)
    p.add_argument("--open", action="store_true", help="open a browser window")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("probe", help="check what fortnite.gg exposes from this machine")
    p.add_argument("--code", default="1865-4829-7018", help="island code to test with")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("capture", help="dump fortnite.gg page structure for parser work")
    p.add_argument("--code", default="1865-4829-7018", help="island code to test with")
    p.add_argument("--scripts", action="store_true",
                   help="also download referenced JS bundles and scan them for API endpoints")
    p.add_argument("--out", default=None, help="output path (default: $FNGG_HOME/fortnitegg-capture.json)")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("track", help="mark islands as priority — polled first, every run")
    p.add_argument("codes", nargs="+")
    p.add_argument("--remove", action="store_true", help="untrack instead")
    p.set_defaults(func=cmd_track)

    p = sub.add_parser("genre", help="override the genre for one island")
    p.add_argument("code")
    p.add_argument("genre", help=f"one of: {', '.join(all_genres())}, or 'auto'")
    p.set_defaults(func=cmd_genre)

    p = sub.add_parser("report", help="full Discovery analysis for one island")
    p.add_argument("code")
    p.add_argument("--json", action="store_true")
    p.add_argument("--window", type=int, default=7)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("top", help="leaderboard")
    p.add_argument("--genre", default="all")
    p.add_argument("--metric", default="discovery_score", choices=["discovery_score", *KPIS])
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--window", type=int, default=7)
    p.set_defaults(func=cmd_top)

    p = sub.add_parser("movers", help="biggest risers and fallers")
    p.add_argument("--genre", default=None)
    p.add_argument("--falling", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--min", type=float, default=50, help="minimum unique players")
    p.add_argument("--window", type=int, default=7)
    p.set_defaults(func=cmd_movers)

    p = sub.add_parser("benchmarks", help="percentile table for a genre")
    p.add_argument("genre", nargs="?", default="rp")
    p.set_defaults(func=cmd_benchmarks)

    p = sub.add_parser("stats", help="what is in the local database")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("export", help="dump the analysed table")
    p.add_argument("--format", choices=["csv", "json"], default="csv")
    p.add_argument("--genre", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--window", type=int, default=7)
    p.set_defaults(func=cmd_export)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
