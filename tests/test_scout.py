"""Offline tests for the scout package. No network, no pytest.

    python tests/test_scout.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point the database at a scratch file before anything imports the config.
_TMP = tempfile.mkdtemp(prefix="uefn-scout-test-")
os.environ["UEFN_SCOUT_DB"] = str(Path(_TMP) / "scout.sqlite3")

from scout import db, report, scoring  # noqa: E402
from scout.config import CATALOG_FILE, PROFILES_FILE, load_catalog, load_profiles  # noqa: E402
from scout.db import Finding  # noqa: E402
from scout.sources import ALL_SOURCES, build  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)


def make(name: str, description: str = "", stars: int = 0, updated: str = "2026-08-01T00:00:00Z",
         topics: list[str] | None = None, profile: str = "ai-3d") -> Finding:
    return Finding(
        uid=f"github:{name}",
        source="github",
        profile=profile,
        name=name,
        url=f"https://github.com/{name}",
        description=description,
        stars=stars,
        updated_at=updated,
        topics=topics or [],
    )


def test_data_files() -> None:
    print("data files")
    profiles = load_profiles()
    check(len(profiles) >= 5, "profiles.json loads at least 5 profiles")
    check("ai-3d" in profiles, "the 3D generation profile exists")
    check(all(p.queries for p in profiles.values()), "every profile has queries")

    catalog = load_catalog()
    required = {"uid", "name", "url", "profile", "summary", "uefn_fit"}
    check(all(required <= set(e) for e in catalog), "every catalog entry has the required fields")
    known = set(profiles)
    check(all(e["profile"] in known for e in catalog), "catalog entries reference real profiles")

    for path in (PROFILES_FILE, CATALOG_FILE):
        json.loads(path.read_text(encoding="utf-8"))
    check(True, "data files are valid JSON")


def test_scoring_gates_on_relevance() -> None:
    print("scoring")
    profiles = load_profiles()
    ai3d = profiles["ai-3d"]

    # The exact failure that motivated the multiplicative score: a hugely popular
    # package that merely says "Model Context Protocol" is not a 3D tool.
    sdk = make("modelcontextprotocol/typescript-sdk",
               "Model Context Protocol implementation for TypeScript", stars=50000)
    sdk_score, _ = scoring.score(sdk, ai3d)
    check(sdk_score == 0.0, "off-topic package scores zero however popular")

    meshy = make("meshy-dev/meshy-mcp-server",
                 "MCP server for Meshy AI 3D generation platform with PBR textures",
                 stars=60, topics=["mcp", "3d"])
    meshy_score, parts = scoring.score(meshy, ai3d)
    check(meshy_score > 60, f"an on-topic MCP server scores well (got {meshy_score})")
    check(parts["relevance"] > 0.5, "relevance reflects the boost terms")

    printing = make("some/slicer", "3D printing slicer with mesh repair", stars=900)
    check(scoring.score(printing, ai3d)[0] == 0.0, "a negative term vetoes the finding")

    stale = make("old/tool", "text-to-3d mesh generator with pbr and glb export",
                 stars=60, updated="2019-01-01T00:00:00Z")
    fresh = make("new/tool", "text-to-3d mesh generator with pbr and glb export",
                 stars=60, updated="2026-08-01T00:00:00Z")
    check(scoring.score(fresh, ai3d)[0] > scoring.score(stale, ai3d)[0],
          "a maintained project outranks an identical abandoned one")

    popular = make("a/one", "image-to-3d mesh glb generator", stars=5000)
    obscure = make("b/two", "image-to-3d mesh glb generator", stars=1)
    check(scoring.score(popular, ai3d)[0] > scoring.score(obscure, ai3d)[0],
          "adoption breaks ties between equally relevant tools")

    check(0.0 <= scoring.score(meshy, ai3d)[0] <= 100.0, "scores stay inside 0-100")


def test_database_roundtrip() -> None:
    print("database")
    with db.connect() as conn:
        item = make("meshy-dev/meshy-mcp-server", "3D mesh generation over mcp", stars=60)
        item.uid = f"ai-3d/{item.uid}"
        item.score = 71.0

        check(db.upsert(conn, item) is True, "a first sighting reports as new")
        check(db.upsert(conn, item) is False, "a second sighting reports as known")

        stored = db.get(conn, item.uid)
        check(stored is not None and stored["name"] == item.name, "the finding reads back")
        check(stored["first_seen"] == stored["last_seen"], "first_seen survives the update")

        item.stars = 120
        db.upsert(conn, item)
        check(db.get(conn, item.uid)["stars"] == 120, "volatile fields refresh")

        check(db.mark(conn, item.uid, "adopted", "wpieta w pipeline"), "a verdict is recorded")
        marked = db.get(conn, item.uid)
        check(marked["review_status"] == "adopted", "the verdict reads back")
        check(marked["note"] == "wpieta w pipeline", "the note reads back")

        db.upsert(conn, item)
        check(db.get(conn, item.uid)["review_status"] == "adopted",
              "a later scan does not clobber the verdict")

        check(db.mark(conn, "github:does/not-exist", "rejected") is False,
              "marking an unknown uid fails cleanly")
        try:
            db.mark(conn, item.uid, "bogus-status")
            check(False, "an invalid status is rejected")
        except ValueError:
            check(True, "an invalid status is rejected")

        check(len(db.query(conn, profile="ai-3d", min_score=50)) == 1, "queries filter by profile")
        check(len(db.query(conn, profile="ai-3d", min_score=95)) == 0, "queries filter by score")
        check(db.stats(conn)["total_findings"] == 1, "stats count the rows")


def test_report_rendering() -> None:
    print("reports")
    text = report.findings_report(profile="ai-3d", min_score=10)
    check("| Score |" in text, "the findings report renders a table")
    check("meshy" in text.lower(), "the stored finding appears in the report")

    empty = report.findings_report(profile="texturing", min_score=99)
    check("Brak wynikow" in empty, "an empty report says so instead of rendering junk")

    catalog = report.catalog_report()
    check(catalog.count("### ") >= 10, "the catalog renders every entry")
    check("priorytet" in report.catalog_report(tag="priority"), "tag filtering works")
    check("Brak wpisow" in report.catalog_report(tag="nie-ma-takiego-tagu"),
          "an unknown tag is handled")


def test_github_parsing() -> None:
    """GitHub is the source that matters most, so its parsing is tested against
    a captured API payload rather than left to a live call."""
    print("github parsing")
    from scout.sources import github as github_source

    payload = {
        "items": [
            {
                "full_name": "meshy-dev/meshy-mcp-server",
                "html_url": "https://github.com/meshy-dev/meshy-mcp-server",
                "description": "MCP server for Meshy AI 3D generation",
                "stargazers_count": 60,
                "pushed_at": "2026-07-01T10:00:00Z",
                "language": "TypeScript",
                "topics": ["mcp", "3d"],
                "archived": False,
            },
            {
                "full_name": "dead/project",
                "html_url": "https://github.com/dead/project",
                "description": "abandoned 3d thing",
                "stargazers_count": 999,
                "pushed_at": "2020-01-01T00:00:00Z",
                "topics": [],
                "archived": True,
            },
            # Duplicate of the first: two queries often return the same repo.
            {
                "full_name": "meshy-dev/meshy-mcp-server",
                "html_url": "https://github.com/meshy-dev/meshy-mcp-server",
                "description": "MCP server for Meshy AI 3D generation",
                "stargazers_count": 60,
                "pushed_at": "2026-07-01T10:00:00Z",
                "topics": ["mcp", "3d"],
                "archived": False,
            },
        ]
    }

    captured: list[str] = []

    def fake_http_json(url, headers=None, retries=3, backoff=2.0):  # noqa: ANN001
        captured.append(url)
        return payload

    original = github_source.http_json
    github_source.http_json = fake_http_json  # type: ignore[assignment]
    try:
        source = github_source.GitHubSource()
        profile = load_profiles()["ai-3d"]
        results = source.search(profile, limit=10)
    finally:
        github_source.http_json = original  # type: ignore[assignment]

    check(len(results) == 1, f"archived repos and duplicates are dropped (got {len(results)})")
    first = results[0]
    check(first.uid == "github:meshy-dev/meshy-mcp-server", "the uid is source-prefixed")
    check(first.stars == 60 and first.topics == ["mcp", "3d"], "metadata is mapped across")
    check(first.updated_at == "2026-07-01T10:00:00Z", "pushed_at is used as the freshness date")
    check(all("q=" in url and "sort=updated" in url for url in captured),
          "queries are URL-encoded with a sort order")


def test_source_construction() -> None:
    print("sources")
    sources = build(None)
    check(len(sources) >= 3, "the default source set builds")
    check(all(hasattr(s, "search") for s in sources), "every source exposes search()")
    try:
        build(["github", "nonexistent"])
        check(False, "an unknown source name is rejected")
    except ValueError:
        check(True, "an unknown source name is rejected")

    # Sources must return nothing rather than crash when a profile has no query for them.
    from scout.config import Profile

    bare = Profile(id="bare", title="t", why="w", queries={})
    for source in build(list(ALL_SOURCES)):
        check(source.search(bare, 5) == [], f"{source.name} handles a profile with no queries")


def main() -> int:
    for test in (
        test_data_files,
        test_scoring_gates_on_relevance,
        test_database_roundtrip,
        test_report_rendering,
        test_github_parsing,
        test_source_construction,
    ):
        test()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
