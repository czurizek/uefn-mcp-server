"""GitHub code-hosting search — where nearly every MCP server and Blender addon lives."""

from __future__ import annotations

import time
import urllib.parse

from ..config import Profile, github_token
from ..db import Finding
from .base import Source, SourceError, clip, http_json

API = "https://api.github.com/search/repositories"


class GitHubSource(Source):
    name = "github"

    def __init__(self, per_query: int = 15) -> None:
        self.per_query = per_query
        self.token = github_token()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def search(self, profile: Profile, limit: int) -> list[Finding]:
        queries = profile.queries.get("github", [])
        if not queries:
            return []

        found: dict[str, Finding] = {}
        errors: list[str] = []

        for index, query in enumerate(queries):
            if len(found) >= limit:
                break
            params = urllib.parse.urlencode(
                {
                    "q": query,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": min(self.per_query, 50),
                }
            )
            try:
                payload = http_json(f"{API}?{params}", headers=self._headers())
            except SourceError as exc:
                errors.append(f"{query!r}: {exc}")
                continue

            for repo in payload.get("items", []):
                if repo.get("archived") or repo.get("disabled"):
                    continue
                uid = f"github:{repo['full_name']}"
                if uid in found:
                    continue
                found[uid] = Finding(
                    uid=uid,
                    source=self.name,
                    profile=profile.id,
                    name=repo["full_name"],
                    url=repo["html_url"],
                    description=clip(repo.get("description")),
                    stars=int(repo.get("stargazers_count") or 0),
                    updated_at=repo.get("pushed_at") or repo.get("updated_at") or "",
                    language=repo.get("language") or "",
                    topics=list(repo.get("topics") or []),
                )

            # Unauthenticated search allows ~10 req/min; stay under it.
            if index < len(queries) - 1:
                time.sleep(0.6 if self.token else 6.5)

        if errors and not found:
            raise SourceError("; ".join(errors))
        return list(found.values())[:limit]
