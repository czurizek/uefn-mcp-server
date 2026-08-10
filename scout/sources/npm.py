"""npm registry search — most TypeScript MCP servers ship here first."""

from __future__ import annotations

import urllib.parse

from ..config import Profile
from ..db import Finding
from .base import Source, SourceError, clip, http_json

API = "https://registry.npmjs.org/-/v1/search"


class NpmSource(Source):
    name = "npm"

    def __init__(self, per_query: int = 15) -> None:
        self.per_query = per_query

    def search(self, profile: Profile, limit: int) -> list[Finding]:
        queries = profile.queries.get("npm", [])
        if not queries:
            return []

        found: dict[str, Finding] = {}
        errors: list[str] = []

        for query in queries:
            if len(found) >= limit:
                break
            params = urllib.parse.urlencode({"text": query, "size": self.per_query})
            try:
                payload = http_json(f"{API}?{params}")
            except SourceError as exc:
                errors.append(f"{query!r}: {exc}")
                continue

            for entry in payload.get("objects", []):
                package = entry.get("package", {})
                name = package.get("name")
                if not name:
                    continue
                uid = f"npm:{name}"
                if uid in found:
                    continue
                links = package.get("links", {})
                found[uid] = Finding(
                    uid=uid,
                    source=self.name,
                    profile=profile.id,
                    name=name,
                    url=links.get("repository") or links.get("npm") or f"https://www.npmjs.com/package/{name}",
                    description=clip(package.get("description")),
                    # npm has no stars. Monthly downloads run orders of magnitude
                    # higher, so square-root them into a comparable range.
                    stars=int(min(2000.0, (entry.get("downloads", {}).get("monthly") or 0) ** 0.5)),
                    updated_at=package.get("date") or "",
                    language="javascript",
                    topics=list(package.get("keywords") or []),
                )

        if errors and not found:
            raise SourceError("; ".join(errors))
        return list(found.values())[:limit]
