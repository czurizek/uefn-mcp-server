"""Discovery sources."""

from __future__ import annotations

from .base import Source, SourceError
from .github import GitHubSource
from .mcp_registry import McpRegistrySource
from .npm import NpmSource
from .pypi import PyPISource

ALL_SOURCES = {
    "github": GitHubSource,
    "mcp_registry": McpRegistrySource,
    "npm": NpmSource,
    "pypi": PyPISource,
}

# PyPI pulls a ~30 MB index on the first run, so it stays out of the default set.
DEFAULT_SOURCES = ("github", "mcp_registry", "npm")


def build(names: list[str] | None = None) -> list[Source]:
    selected = names or list(DEFAULT_SOURCES)
    unknown = [n for n in selected if n not in ALL_SOURCES]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)}")
    return [ALL_SOURCES[n]() for n in selected]


__all__ = ["ALL_SOURCES", "DEFAULT_SOURCES", "Source", "SourceError", "build"]
