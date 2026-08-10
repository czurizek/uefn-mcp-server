"""MCP Server for UEFN Scout.

Lets Claude Code run the discovery itself: search the web for UEFN-adjacent
tooling, read the curated catalog, and keep a review verdict per finding.

Requires: pip install mcp

Usage:
    python -m scout.mcp_scout

Claude Code config (.mcp.json):
    {
      "mcpServers": {
        "uefn-scout": {
          "command": "python",
          "args": ["-m", "scout.mcp_scout"],
          "cwd": "/path/to/uefn-mcp-server"
        }
      }
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python scout/mcp_scout.py` as well as `python -m scout.mcp_scout`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scout import db, engine, report  # type: ignore[no-redef]
    from scout.config import load_catalog, load_profiles  # type: ignore[no-redef]
    from scout.sources import ALL_SOURCES, DEFAULT_SOURCES  # type: ignore[no-redef]
else:
    from . import db, engine, report
    from .config import load_catalog, load_profiles
    from .sources import ALL_SOURCES, DEFAULT_SOURCES

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("uefn-scout")


@mcp.tool()
def scout_profiles() -> str:
    """List the search themes this scout knows about.

    Each profile is a topic (AI 3D generation, UEFN tooling, Blender bridge, ...)
    with its own queries and scoring rules. Call this first to pick a profile id.
    """
    profiles = load_profiles()
    payload = {
        pid: {
            "title": p.title,
            "why": p.why,
            "sources": list(p.queries),
            "weight": p.weight,
        }
        for pid, p in profiles.items()
    }
    return json.dumps(
        {
            "profiles": payload,
            "sources_available": sorted(ALL_SOURCES),
            "sources_default": list(DEFAULT_SOURCES),
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def scout_scan(
    profile: str = "",
    sources: str = "",
    limit: int = 30,
    min_score: float = 35.0,
) -> str:
    """Search the web now and store anything relevant that turns up.

    Args:
        profile: profile id to scan, or empty for all of them.
        sources: comma-separated source names, or empty for the default set
                 (github, mcp_registry, npm). "pypi" downloads a large index on
                 first use, so ask for it explicitly.
        limit: maximum results per source per profile.
        min_score: findings below this score are discarded rather than stored.

    Returns a markdown report of what is new since the previous scan.
    """
    profile_ids = [profile] if profile else None
    source_names = [s.strip() for s in sources.split(",") if s.strip()] or None

    try:
        result = engine.scan(
            profile_ids=profile_ids,
            source_names=source_names,
            per_source_limit=limit,
            min_score=min_score,
        )
    except ValueError as exc:
        return f"Error: {exc}"

    return report.scan_report(result)


@mcp.tool()
def scout_report(
    profile: str = "",
    min_score: float = 45.0,
    new_only: bool = False,
    status: str = "",
    limit: int = 25,
) -> str:
    """Read the stored findings without touching the network.

    Args:
        profile: restrict to one profile id, or empty for all.
        min_score: minimum score to include (0-100).
        new_only: only findings first seen during the most recent scan.
        status: filter by review verdict — new, watching, adopted or rejected.
        limit: maximum rows per profile.
    """
    return report.findings_report(
        profile=profile or None,
        min_score=min_score,
        new_only=new_only,
        limit=limit,
        status=status or None,
    )


@mcp.tool()
def scout_catalog(tag: str = "") -> str:
    """Read the hand-verified starting catalog.

    These entries were checked by a human and carry a "how does this fit UEFN"
    note, which scan results do not. Useful tags: priority, 3d-generation,
    blender, unreal, pipeline.
    """
    return report.catalog_report(tag=tag or None)


@mcp.tool()
def scout_mark(uid: str, status: str, note: str = "") -> str:
    """Record a verdict on a finding so later reports can skip or highlight it.

    Args:
        uid: finding id, e.g. "github:owner/repo" (see scout_report output).
        status: new, watching, adopted or rejected.
        note: free-text reasoning, kept alongside the finding.
    """
    try:
        with db.connect() as conn:
            ok = db.mark(conn, uid, status, note or None)
    except ValueError as exc:
        return f"Error: {exc}"
    return f"{uid} -> {status}" if ok else f"Error: no finding with uid {uid}"


@mcp.tool()
def scout_stats() -> str:
    """Database summary: how much has been collected and when the last scan ran."""
    with db.connect() as conn:
        return json.dumps(db.stats(conn), indent=2, ensure_ascii=False)


def main() -> None:
    # Catalog and profiles are parsed eagerly so a broken data file fails loudly.
    load_profiles()
    load_catalog()
    mcp.run()


if __name__ == "__main__":
    main()
