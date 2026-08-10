"""Command line interface: python -m scout <command>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import db, engine, report
from .config import load_profiles
from .sources import ALL_SOURCES, DEFAULT_SOURCES


def _write_or_print(text: str, out: str | None) -> None:
    if out:
        path = Path(out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Zapisano: {path}")
    else:
        print(text)


def cmd_profiles(args: argparse.Namespace) -> int:
    profiles = load_profiles()
    if args.json:
        print(json.dumps({p.id: {"title": p.title, "why": p.why} for p in profiles.values()}, indent=2))
        return 0
    for profile in profiles.values():
        sources = ", ".join(profile.queries)
        print(f"{profile.id:<16} {profile.title}")
        print(f"{'':<16} {profile.why}")
        print(f"{'':<16} zrodla: {sources} | waga: {profile.weight}")
        print()
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    try:
        result = engine.scan(
            profile_ids=args.profile,
            source_names=args.source,
            per_source_limit=args.limit,
            min_score=args.min_score,
        )
    except ValueError as exc:
        print(f"Blad: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.__dict__, indent=2, default=str))
    else:
        _write_or_print(report.scan_report(result), args.out)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    text = report.findings_report(
        profile=args.profile,
        min_score=args.min_score,
        new_only=args.new,
        limit=args.limit,
        status=args.status,
    )
    _write_or_print(text, args.out)
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    _write_or_print(report.catalog_report(tag=args.tag), args.out)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    with db.connect() as conn:
        item = db.get(conn, args.uid)
    if not item:
        print(f"Nie znaleziono: {args.uid}", file=sys.stderr)
        return 1
    print(json.dumps(item, indent=2, ensure_ascii=False))
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    with db.connect() as conn:
        ok = db.mark(conn, args.uid, args.status, args.note)
    if not ok:
        print(f"Nie znaleziono: {args.uid}", file=sys.stderr)
        return 1
    print(f"{args.uid} -> {args.status}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    with db.connect() as conn:
        print(json.dumps(db.stats(conn), indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scout",
        description="Szuka w sieci narzedzi, ktore ulatwiaja prace w UEFN (MCP, generatory 3D, pipeline).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("profiles", help="pokaz tematy wyszukiwania")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_profiles)

    p = sub.add_parser("scan", help="przeszukaj zrodla i zapisz wyniki")
    p.add_argument("--profile", action="append", help="ogranicz do profilu (mozna podac wielokrotnie)")
    p.add_argument(
        "--source",
        action="append",
        choices=sorted(ALL_SOURCES),
        help=f"zrodla (domyslnie: {', '.join(DEFAULT_SOURCES)})",
    )
    p.add_argument("--limit", type=int, default=40, help="max wynikow na zrodlo/profil")
    p.add_argument("--min-score", type=float, default=35.0, help="prog zapisu do bazy")
    p.add_argument("--out", help="zapisz raport do pliku")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("report", help="raport z tego, co juz jest w bazie")
    p.add_argument("--profile")
    p.add_argument("--min-score", type=float, default=45.0)
    p.add_argument("--new", action="store_true", help="tylko nigdy wczesniej nie widziane")
    p.add_argument("--status", choices=db.REVIEW_STATUSES)
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--out")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("catalog", help="recznie zweryfikowany punkt startowy")
    p.add_argument("--tag", help="np. priority, blender, 3d-generation")
    p.add_argument("--out")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("show", help="szczegoly jednego znaleziska")
    p.add_argument("uid")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("mark", help="oznacz znalezisko po przejrzeniu")
    p.add_argument("uid")
    p.add_argument("status", choices=db.REVIEW_STATUSES)
    p.add_argument("--note")
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("stats", help="stan bazy")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
