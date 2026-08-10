"""The official Model Context Protocol registry — servers published for direct install."""

from __future__ import annotations

import urllib.parse

from ..config import Profile
from ..db import Finding
from .base import Source, SourceError, clip, http_json

API = "https://registry.modelcontextprotocol.io/v0/servers"


class McpRegistrySource(Source):
    name = "mcp_registry"

    def __init__(self, per_query: int = 20) -> None:
        self.per_query = per_query

    def search(self, profile: Profile, limit: int) -> list[Finding]:
        queries = profile.queries.get("mcp_registry", [])
        if not queries:
            return []

        found: dict[str, Finding] = {}
        errors: list[str] = []

        for query in queries:
            if len(found) >= limit:
                break
            params = urllib.parse.urlencode({"search": query, "limit": self.per_query})
            try:
                payload = http_json(f"{API}?{params}")
            except SourceError as exc:
                errors.append(f"{query!r}: {exc}")
                continue

            for entry in payload.get("servers", []):
                server = entry.get("server", {})
                name = server.get("name")
                if not name:
                    continue
                meta = entry.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
                if meta.get("status") not in (None, "active"):
                    continue

                uid = f"mcp:{name}"
                if uid in found:
                    continue

                repo = server.get("repository", {}) or {}
                packages = server.get("packages", []) or []
                # Package registry names are a strong "you can install this" signal.
                topics = ["mcp", "mcp-server"] + [
                    p.get("registryType", "") for p in packages if p.get("registryType")
                ]

                found[uid] = Finding(
                    uid=uid,
                    source=self.name,
                    profile=profile.id,
                    name=server.get("title") or name,
                    url=repo.get("url") or server.get("websiteUrl") or f"{API}?search={name}",
                    description=clip(server.get("description")),
                    stars=0,
                    updated_at=meta.get("updatedAt") or meta.get("publishedAt") or "",
                    language="",
                    topics=topics,
                )

        if errors and not found:
            raise SourceError("; ".join(errors))
        return list(found.values())[:limit]
