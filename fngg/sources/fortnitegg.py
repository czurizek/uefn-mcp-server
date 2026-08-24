"""Optional adapter for fortnite.gg.

Why this exists
---------------
Epic's Ecosystem API gives authoritative daily metrics but not two things that
matter for Discover work: *live* concurrency right now, and which Discover row
an island is actually sitting in. fortnite.gg surfaces both. This adapter reads
them and feeds them into the same SQLite log as everything else.

Important caveat
----------------
fortnite.gg is a website, not a documented API. It has no published contract and
its markup can change without notice, so nothing here is hardcoded to a single
selector. Instead the adapter carries a list of *strategies* - candidate URLs
plus tolerant parsers - runs them in order, and gives up quietly if none work.
`fngg probe` reports exactly which strategies resolve from your machine.

The strategy table is also user-editable. Drop a JSON file at
``$FNGG_HOME/fortnitegg_strategies.json`` to add or reorder candidates without
editing this module::

    {
      "island": ["https://fortnite.gg/island?code={code}"],
      "browse": ["https://fortnite.gg/creative?sort=players"]
    }

The rest of the app never requires this adapter. If fortnite.gg is unreachable,
blocked, or restructured, every Ecosystem-backed feature still works.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Iterator, Optional

from .. import config
from ..http_client import HttpError, NotFound, get_text

CODE_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}\b")

# Candidate URL templates, tried in order. Unverified by design - `probe()`
# tells you which of these actually answer from your network.
DEFAULT_STRATEGIES: dict[str, list[str]] = {
    "island": [
        "https://fortnite.gg/island?code={code}",
        "https://fortnite.gg/creative?code={code}",
        "https://fortnite.gg/island/{code}",
    ],
    "browse": [
        "https://fortnite.gg/creative?sort=players",
        "https://fortnite.gg/creative",
        "https://fortnite.gg/discover",
    ],
    "discovery": [
        "https://fortnite.gg/discover",
        "https://fortnite.gg/creative?tab=discover",
    ],
}

# Keys we hope to find inside embedded JSON, mapped onto our own field names.
FIELD_ALIASES = {
    "ccu": ("ccu", "players", "playercount", "playersnow", "currentplayers", "live"),
    "peak_24h": ("peak", "peak24h", "peakccu", "peak_24h", "dailypeak", "peakplayers"),
    "favorites": ("favorites", "favourites", "favs", "favoritecount"),
    "rank_overall": ("rank", "position", "overallrank"),
    "title": ("title", "name", "islandname", "displayname"),
    "code": ("code", "islandcode", "mnemonic", "islandid"),
}


# --------------------------------------------------------------------- config


def load_strategies() -> dict[str, list[str]]:
    """DEFAULT_STRATEGIES, overlaid with the user's JSON file if present."""
    merged = {k: list(v) for k, v in DEFAULT_STRATEGIES.items()}
    path = config.data_dir() / "fortnitegg_strategies.json"
    if not path.exists():
        return merged
    try:
        custom = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return merged
    if not isinstance(custom, dict):
        return merged
    for key, urls in custom.items():
        if isinstance(urls, str):
            urls = [urls]
        if isinstance(urls, list):
            # User entries win: they go first, defaults stay as fallback.
            rest = [u for u in merged.get(key, []) if u not in urls]
            merged[key] = [str(u) for u in urls] + rest
    return merged


# ------------------------------------------------------------------- parsing


class _ScriptCollector(HTMLParser):
    """Collects <script> bodies and data-* attributes carrying JSON."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.data_blobs: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "script":
            self._in_script = True
        for name, value in attrs:
            if not value or not name.startswith("data-"):
                continue
            stripped = value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                self.data_blobs.append(stripped)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script and data.strip():
            self.scripts.append(data)


def _json_candidates(text: str) -> Iterator[Any]:
    """Yield every JSON object/array that can be decoded out of `text`.

    Uses raw_decode from each brace so it works on `var x = {...};` assignments
    and on JSON embedded in larger scripts, without regex-guessing the shape.
    """
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    while index < length:
        char = text.find("{", index)
        bracket = text.find("[", index)
        if char < 0 and bracket < 0:
            return
        start = min(x for x in (char, bracket) if x >= 0)
        try:
            obj, end = decoder.raw_decode(text, start)
        except ValueError:
            index = start + 1
            continue
        if isinstance(obj, (dict, list)) and obj:
            yield obj
        index = max(end, start + 1)


def find_embedded_json(html: str) -> list[Any]:
    parser = _ScriptCollector()
    try:
        parser.feed(html)
    except Exception:  # malformed markup should never take the app down
        pass
    found: list[Any] = []
    for blob in parser.data_blobs:
        try:
            found.append(json.loads(blob))
        except json.JSONDecodeError:
            continue
    for script in parser.scripts:
        found.extend(_json_candidates(script))
    return found


def _walk(obj: Any) -> Iterator[dict]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def parse_number(value: Any) -> Optional[float]:
    """Parse 12,345 / 12.3K / 1.2M / '1 234' into a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace(",", "").replace(" ", "").replace(" ", "")
    if not text:
        return None
    multiplier = 1.0
    if text[-1:].upper() in ("K", "M", "B"):
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9}[text[-1].upper()]
        text = text[:-1]
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0)) * multiplier
    except ValueError:
        return None


def _pick(record: dict, aliases: tuple[str, ...]) -> Any:
    lowered = {str(k).lower().replace("_", ""): v for k, v in record.items()}
    for alias in aliases:
        key = alias.lower().replace("_", "")
        if key in lowered and lowered[key] not in (None, ""):
            return lowered[key]
    return None


@dataclass
class GGIsland:
    code: Optional[str] = None
    title: Optional[str] = None
    ccu: Optional[float] = None
    peak_24h: Optional[float] = None
    favorites: Optional[float] = None
    rank_overall: Optional[int] = None
    row_key: Optional[str] = None
    row_label: Optional[str] = None
    position: Optional[int] = None
    source_url: Optional[str] = None

    def is_useful(self) -> bool:
        return bool(self.code) and any(
            v is not None for v in (self.ccu, self.peak_24h, self.favorites, self.rank_overall)
        )


def _record_to_island(record: dict) -> Optional[GGIsland]:
    code = _pick(record, FIELD_ALIASES["code"])
    code_text = str(code) if code is not None else ""
    if not CODE_RE.fullmatch(code_text.strip()):
        return None
    island = GGIsland(code=code_text.strip())
    island.title = _pick(record, FIELD_ALIASES["title"])
    island.ccu = parse_number(_pick(record, FIELD_ALIASES["ccu"]))
    island.peak_24h = parse_number(_pick(record, FIELD_ALIASES["peak_24h"]))
    island.favorites = parse_number(_pick(record, FIELD_ALIASES["favorites"]))
    rank = parse_number(_pick(record, FIELD_ALIASES["rank_overall"]))
    island.rank_overall = int(rank) if rank is not None else None
    return island if island.is_useful() else None


def parse_islands_from_html(html: str, source_url: str = "") -> list[GGIsland]:
    """Best-effort extraction of island records from any fortnite.gg page.

    Strategy order: embedded JSON first (structured, reliable when present),
    then a text scan that pairs island codes with nearby numbers.
    """
    out: dict[str, GGIsland] = {}
    for blob in find_embedded_json(html):
        for record in _walk(blob):
            island = _record_to_island(record)
            if island and island.code and island.code not in out:
                island.source_url = source_url
                out[island.code] = island
    if out:
        return list(out.values())

    # Fallback: no usable JSON. Pull codes with a following number from markup.
    text = re.sub(r"<[^>]+>", " ", html)
    for match in CODE_RE.finditer(text):
        code = match.group(0)
        if code in out:
            continue
        tail = text[match.end() : match.end() + 160]
        number = re.search(r"([\d][\d,\.\s]*[KMB]?)\s*(?:players|playing|online)", tail, re.I)
        island = GGIsland(code=code, source_url=source_url)
        if number:
            island.ccu = parse_number(number.group(1))
        if island.is_useful():
            out[code] = island
    return list(out.values())


# --------------------------------------------------------- discovery rows


ROW_HINT_RE = re.compile(
    r"(epic'?s?\s*picks|by\s*epic|popular|trending|new\s*releases?|featured|"
    r"community\s*choice|for\s*you|players\s*like\s*you|fortnite\s*originals|"
    r"top\s*(?:charts?|islands?|maps?)|recently\s*updated|rising)",
    re.I,
)


def row_key_for(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower()).strip("_") or "unknown"


def parse_discovery_rows(html: str, source_url: str = "") -> list[GGIsland]:
    """Pair island codes with the nearest preceding row heading.

    Discover rows are headings followed by a strip of island tiles, so the
    heading that most recently appeared before a code in document order is the
    row that code sits in. That holds across markup rewrites in a way that any
    specific CSS selector does not.
    """
    entries: list[GGIsland] = []
    plain = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", html, flags=re.S | re.I)
    plain = re.sub(r"<[^>]+>", "\n", plain)

    current_label: Optional[str] = None
    position = 0
    for line in plain.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = ROW_HINT_RE.search(stripped)
        if heading and len(stripped) <= 60:
            current_label = heading.group(0).strip()
            position = 0
            continue
        for match in CODE_RE.finditer(stripped):
            if not current_label:
                continue
            position += 1
            entries.append(
                GGIsland(
                    code=match.group(0),
                    row_key=row_key_for(current_label),
                    row_label=current_label,
                    position=position,
                    source_url=source_url,
                )
            )
    return entries


# ------------------------------------------------------------------ fetching


@dataclass
class StrategyResult:
    name: str
    url: str
    ok: bool
    detail: str = ""
    records: int = 0
    sample: list[str] = field(default_factory=list)


def _try_urls(kind: str, **fmt: Any) -> tuple[Optional[str], Optional[str], list[StrategyResult]]:
    """Try every URL for `kind`. Returns (html, winning_url, attempt log)."""
    attempts: list[StrategyResult] = []
    for template in load_strategies().get(kind, []):
        try:
            url = template.format(**fmt)
        except (KeyError, IndexError) as exc:
            attempts.append(StrategyResult(kind, template, False, f"bad template: {exc}"))
            continue
        try:
            html = get_text(url, retries=1)
        except NotFound:
            attempts.append(StrategyResult(kind, url, False, "404"))
            continue
        except HttpError as exc:
            attempts.append(StrategyResult(kind, url, False, str(exc)[:160]))
            continue
        except Exception as exc:  # never let a source take the app down
            attempts.append(StrategyResult(kind, url, False, f"{type(exc).__name__}: {exc}"[:160]))
            continue
        attempts.append(StrategyResult(kind, url, True, f"{len(html)} bytes"))
        return html, url, attempts
    return None, None, attempts


def fetch_island_live(code: str) -> Optional[GGIsland]:
    """Live concurrency for one island, or None if fortnite.gg is unusable."""
    html, url, _ = _try_urls("island", code=code)
    if not html:
        return None
    for island in parse_islands_from_html(html, url or ""):
        if island.code == code:
            return island
    # Page resolved but the code was not in a structured record - scan the text
    # for a "N players" figure, which is the one number these pages always show.
    match = re.search(r"([\d][\d,\.\s]*[KMB]?)\s*(?:players|playing)", re.sub(r"<[^>]+>", " ", html), re.I)
    if match:
        return GGIsland(code=code, ccu=parse_number(match.group(1)), source_url=url)
    return None


def fetch_browse(limit: int = 200) -> list[GGIsland]:
    html, url, _ = _try_urls("browse")
    if not html:
        return []
    islands = parse_islands_from_html(html, url or "")
    islands.sort(key=lambda i: (i.ccu is None, -(i.ccu or 0)))
    return islands[:limit]


def fetch_discovery() -> list[GGIsland]:
    html, url, _ = _try_urls("discovery")
    if not html:
        return []
    return parse_discovery_rows(html, url or "")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def probe(sample_code: str = "1865-4829-7018") -> dict:
    """Check what actually works from this machine.

    Returns a report the CLI prints and the dashboard shows, so a fortnite.gg
    change surfaces as a diagnosis rather than as silently missing data.
    """
    report: dict[str, Any] = {"checked_at": now_iso(), "strategies": {}, "usable": False}
    for kind, fmt in (("island", {"code": sample_code}), ("browse", {}), ("discovery", {})):
        html, url, attempts = _try_urls(kind, **fmt)
        parsed: list[GGIsland] = []
        if html:
            parsed = (
                parse_discovery_rows(html, url or "")
                if kind == "discovery"
                else parse_islands_from_html(html, url or "")
            )
            for attempt in attempts:
                if attempt.ok:
                    attempt.records = len(parsed)
                    attempt.sample = [i.code or "?" for i in parsed[:5]]
        report["strategies"][kind] = [vars(a) for a in attempts]
        if parsed:
            report["usable"] = True
    return report


__all__ = [
    "GGIsland",
    "StrategyResult",
    "load_strategies",
    "parse_number",
    "find_embedded_json",
    "parse_islands_from_html",
    "parse_discovery_rows",
    "row_key_for",
    "fetch_island_live",
    "fetch_browse",
    "fetch_discovery",
    "probe",
]
