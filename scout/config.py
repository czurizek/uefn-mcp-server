"""Configuration: paths, profile loading, HTTP defaults."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
PROFILES_FILE = DATA_DIR / "profiles.json"
CATALOG_FILE = DATA_DIR / "catalog.json"

USER_AGENT = "uefn-scout/0.1 (+https://github.com/czurizek/uefn-mcp-server)"
HTTP_TIMEOUT = 25.0


def db_path() -> Path:
    """Where the findings database lives. Override with UEFN_SCOUT_DB."""
    override = os.environ.get("UEFN_SCOUT_DB")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".uefn-scout" / "scout.sqlite3"


def github_token() -> str | None:
    """Optional PAT. Without it GitHub allows ~10 searches/min, with it ~30."""
    for var in ("UEFN_SCOUT_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return None


@dataclass
class Profile:
    """One search theme: what to ask each source, and how to judge the answers."""

    id: str
    title: str
    why: str
    queries: dict[str, list[str]] = field(default_factory=dict)
    boost: list[str] = field(default_factory=list)
    require_any: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)
    weight: float = 1.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Profile":
        return cls(
            id=raw["id"],
            title=raw["title"],
            why=raw.get("why", ""),
            queries=raw.get("queries", {}),
            boost=[t.lower() for t in raw.get("boost", [])],
            require_any=[t.lower() for t in raw.get("require_any", [])],
            negative=[t.lower() for t in raw.get("negative", [])],
            weight=float(raw.get("weight", 1.0)),
        )


def load_profiles() -> dict[str, Profile]:
    raw = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    return {p["id"]: Profile.from_dict(p) for p in raw["profiles"]}


def load_catalog() -> list[dict[str, Any]]:
    """Hand-verified starting points, so the tool is useful before the first scan."""
    raw = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    return raw["entries"]
