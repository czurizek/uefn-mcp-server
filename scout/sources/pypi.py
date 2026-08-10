"""PyPI.

PyPI has no public search API any more, so this works differently: it downloads
the full project index once a day, matches names locally, and only then fetches
metadata for the handful of packages that actually matched.
"""

from __future__ import annotations

import re
import urllib.request

from ..config import HTTP_TIMEOUT, Profile, USER_AGENT
from ..db import Finding
from .base import Source, SourceError, cached_json, clip, http_json

INDEX_URL = "https://pypi.org/simple/"
INDEX_ACCEPT = "application/vnd.pypi.simple.v1+json"
PROJECT_URL = "https://pypi.org/pypi/{name}/json"

MAX_ENRICH_PER_QUERY = 6


def _download_index() -> list[str]:
    req = urllib.request.Request(
        INDEX_URL, headers={"User-Agent": USER_AGENT, "Accept": INDEX_ACCEPT}
    )
    try:
        with urllib.request.urlopen(req, timeout=max(HTTP_TIMEOUT, 90.0)) as response:
            import json as _json

            payload = _json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a SourceError below
        raise SourceError(f"could not fetch the PyPI index: {exc}") from exc
    return [p["name"] for p in payload.get("projects", []) if p.get("name")]


def _normalise(text: str) -> str:
    return re.sub(r"[-_.]+", "-", text.lower())


class PyPISource(Source):
    name = "pypi"

    def search(self, profile: Profile, limit: int) -> list[Finding]:
        queries = profile.queries.get("pypi", [])
        if not queries:
            return []

        index = cached_json("pypi-index", _download_index, max_age_hours=24.0)
        normalised = [(_normalise(n), n) for n in index]

        found: dict[str, Finding] = {}
        for query in queries:
            if len(found) >= limit:
                break
            # Multi-word queries: every word has to appear somewhere in the name.
            words = [_normalise(w) for w in query.split() if len(w) > 2]
            if not words:
                continue

            matches = [
                original
                for norm, original in normalised
                if all(word in norm for word in words)
            ]
            # Shortest names first: they are the canonical projects, not the forks.
            matches.sort(key=len)

            for package in matches[:MAX_ENRICH_PER_QUERY]:
                uid = f"pypi:{package}"
                if uid in found:
                    continue
                try:
                    meta = http_json(PROJECT_URL.format(name=package), retries=2)
                except SourceError:
                    continue

                info = meta.get("info", {})
                releases = meta.get("releases", {})
                latest = info.get("version", "")
                uploaded = ""
                for file_info in releases.get(latest, []) or []:
                    uploaded = file_info.get("upload_time_iso_8601", "") or ""
                    if uploaded:
                        break

                found[uid] = Finding(
                    uid=uid,
                    source=self.name,
                    profile=profile.id,
                    name=package,
                    url=info.get("project_url") or f"https://pypi.org/project/{package}/",
                    description=clip(info.get("summary")),
                    stars=0,
                    updated_at=uploaded,
                    language="python",
                    topics=[k.strip() for k in (info.get("keywords") or "").split(",") if k.strip()],
                )

        return list(found.values())[:limit]
