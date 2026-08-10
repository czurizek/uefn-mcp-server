"""Markdown rendering — the format both you and Claude read fastest."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import db
from .config import load_catalog, load_profiles


def _age(iso: str) -> str:
    if not iso:
        return "?"
    try:
        stamp = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return "?"
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - stamp).days
    if days < 1:
        return "dzis"
    if days < 60:
        return f"{days} dni"
    if days < 730:
        return f"{days // 30} mies."
    return f"{days // 365} lat"


def _row(item: dict[str, Any]) -> str:
    stars = f"{item['stars']}" if item["stars"] else "-"
    return (
        f"| {item['score']:.0f} | [{item['name']}]({item['url']}) | {stars} | "
        f"{_age(item['updated_at'])} | {item['source']} | {item['description'] or ''} |"
    )


def findings_report(
    profile: str | None = None,
    min_score: float = 45.0,
    new_only: bool = False,
    limit: int = 25,
    status: str | None = None,
) -> str:
    profiles = load_profiles()
    targets = [profile] if profile else list(profiles)

    lines = ["# UEFN Scout — raport", ""]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    scope = "tylko nowe od ostatniego skanu" if new_only else f"prog scoringu >= {min_score:.0f}"
    lines.append(f"_Wygenerowano {generated} · {scope}_")
    lines.append("")

    total = 0
    with db.connect() as conn:
        info = db.stats(conn)
        for pid in targets:
            rows = db.query(
                conn,
                profile=pid,
                min_score=min_score,
                new_only=new_only,
                status=status,
                limit=limit,
            )
            if not rows:
                continue
            total += len(rows)
            meta = profiles.get(pid)
            lines.append(f"## {meta.title if meta else pid}")
            if meta and meta.why:
                lines.append(f"> {meta.why}")
            lines.append("")
            lines.append("| Score | Projekt | ★ | Ostatnia zmiana | Zrodlo | Opis |")
            lines.append("|---:|---|---:|---|---|---|")
            lines.extend(_row(r) for r in rows)
            lines.append("")

    if total == 0:
        lines.append("_Brak wynikow dla podanych filtrow. Uruchom `python -m scout scan` albo obniz `--min-score`._")
        lines.append("")

    lines.append("---")
    lines.append(
        f"_Baza: {info['total_findings']} znalezisk, {info['runs']} skanow._"
    )
    return "\n".join(lines)


def catalog_report(tag: str | None = None) -> str:
    entries = load_catalog()
    if tag:
        entries = [e for e in entries if tag.lower() in [t.lower() for t in e.get("tags", [])]]

    lines = ["# UEFN Scout — katalog zweryfikowany recznie", ""]
    if not entries:
        lines.append(f"_Brak wpisow z tagiem `{tag}`._")
        return "\n".join(lines)

    by_profile: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_profile.setdefault(entry.get("profile", "inne"), []).append(entry)

    profiles = load_profiles()
    for pid, items in by_profile.items():
        meta = profiles.get(pid)
        lines.append(f"## {meta.title if meta else pid}")
        lines.append("")
        for item in items:
            priority = " **[priorytet]**" if "priority" in item.get("tags", []) else ""
            lines.append(f"### [{item['name']}]({item['url']}){priority}")
            lines.append(f"- **Co to jest:** {item['summary']}")
            lines.append(f"- **Jak sie ma do UEFN:** {item['uefn_fit']}")
            lines.append(f"- **Tagi:** {', '.join(item.get('tags', []))}")
            lines.append("")
    return "\n".join(lines)


def scan_report(result: Any) -> str:
    lines = [f"# UEFN Scout — wynik skanu", "", result.summary(), ""]
    if result.new_findings:
        lines.append("## Nowe znaleziska")
        lines.append("")
        lines.append("| Score | Projekt | ★ | Profil | Opis |")
        lines.append("|---:|---|---:|---|---|")
        for item in result.new_findings[:30]:
            stars = item["stars"] or "-"
            lines.append(
                f"| {item['score']:.0f} | [{item['name']}]({item['url']}) | {stars} | "
                f"{item['profile']} | {item['description'] or ''} |"
            )
        lines.append("")
    else:
        lines.append("_Nic nowego — wszystko juz bylo w bazie._")
        lines.append("")

    if result.errors:
        lines.append("## Bledy zrodel")
        lines.extend(f"- {e}" for e in result.errors)
    return "\n".join(lines)
