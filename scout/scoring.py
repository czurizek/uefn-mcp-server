"""Relevance scoring.

A find is worth your attention when it is (a) about the right thing, (b) still
alive, (c) used by someone other than its author, and (d) something you can
actually plug in rather than a paper or a link list.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .config import Profile
from .db import Finding

# Signals that the thing is installable/callable rather than reading material.
ACTIONABLE = (
    "mcp", "mcp-server", "plugin", "addon", "cli", "api", "server",
    "sdk", "library", "pip install", "npm install", "extension",
)
# Signals that it is a list, a paper, or a demo.
INERT = (
    "awesome", "curated list", "paper", "arxiv", "survey", "benchmark",
    "course", "tutorial", "cheatsheet", "roadmap", "collection of links",
)

# Relevance multiplies the rest rather than adding to it: a wildly popular
# package that is only vaguely on-topic must not outrank a small exact match.
QUALITY_BASE = 0.25
QUALITY_WEIGHTS = {"freshness": 0.30, "adoption": 0.25, "actionable": 0.20}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9+._-]*", text.lower()))


def _phrase_hits(haystack: str, terms: list[str]) -> int:
    """Count matches, treating multi-word terms as phrases."""
    words = _tokens(haystack)
    hits = 0
    for term in terms:
        term = term.lower().strip()
        if not term:
            continue
        if " " in term or "-" in term:
            if term in haystack:
                hits += 1
        elif term in words:
            hits += 1
    return hits


def _days_since(iso: str) -> float | None:
    if not iso:
        return None
    text = iso.replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 86400.0)


def relevance(finding: Finding, profile: Profile) -> float:
    """0..1. Zero when a hard requirement is missing, so noise drops out entirely."""
    hay = finding.haystack()

    if profile.require_any and _phrase_hits(hay, profile.require_any) == 0:
        return 0.0
    if profile.negative and _phrase_hits(hay, profile.negative) > 0:
        return 0.0

    if not profile.boost:
        return 0.5
    hits = _phrase_hits(hay, profile.boost)
    # Saturating: 4 boost terms is already a strong match, more adds little.
    return min(1.0, 0.25 + 0.75 * (1 - math.exp(-hits / 2.5)))


def freshness(finding: Finding) -> float:
    """0..1 with a half-life of about six months; unknown dates get a neutral 0.4."""
    days = _days_since(finding.updated_at)
    if days is None:
        return 0.4
    return math.exp(-days / 260.0)


def adoption(finding: Finding) -> float:
    """0..1 on a log scale: 0 stars -> 0, ~30 -> 0.5, 1000+ -> ~1."""
    if finding.stars <= 0:
        return 0.0
    return min(1.0, math.log10(finding.stars + 1) / 3.0)


def actionability(finding: Finding) -> float:
    hay = finding.haystack()
    if _phrase_hits(hay, list(INERT)) > 0:
        return 0.15
    hits = _phrase_hits(hay, list(ACTIONABLE))
    return min(1.0, 0.3 + 0.35 * hits)


def score(finding: Finding, profile: Profile) -> tuple[float, dict[str, float]]:
    parts = {
        "relevance": relevance(finding, profile),
        "freshness": freshness(finding),
        "adoption": adoption(finding),
        "actionable": actionability(finding),
    }
    if parts["relevance"] == 0.0:
        return 0.0, parts

    quality = QUALITY_BASE + sum(QUALITY_WEIGHTS[k] * parts[k] for k in QUALITY_WEIGHTS)
    total = 100.0 * parts["relevance"] * quality * profile.weight
    return round(min(100.0, total), 1), {k: round(v, 3) for k, v in parts.items()}
