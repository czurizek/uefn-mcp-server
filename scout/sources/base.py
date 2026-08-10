"""Shared HTTP plumbing for the sources. Standard library only, on purpose:
this has to run inside whatever Python the user already has."""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..config import HTTP_TIMEOUT, USER_AGENT, db_path
from ..config import Profile
from ..db import Finding


class SourceError(RuntimeError):
    """A source failed in a way worth reporting but not worth aborting the scan."""


def cache_dir() -> Path:
    path = db_path().parent / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def http_json(
    url: str,
    headers: dict[str, str] | None = None,
    retries: int = 3,
    backoff: float = 2.0,
) -> Any:
    """GET + parse JSON, retrying on rate limits and transient server errors."""
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    request_headers.update(headers or {})

    last_error: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 403 here is nearly always the secondary rate limit; 5xx is transient.
            if exc.code in (403, 429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = backoff * (2**attempt)
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after and retry_after.isdigit():
                    wait = max(wait, float(retry_after))
                time.sleep(min(wait, 60.0))
                continue
            raise SourceError(f"HTTP {exc.code} for {url}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
                continue
            raise SourceError(f"{type(exc).__name__} for {url}: {exc}") from exc

    raise SourceError(f"gave up on {url}: {last_error}")


def cached_json(
    key: str,
    loader: Callable[[], Any],
    max_age_hours: float = 24.0,
) -> Any:
    """Cache expensive whole-index downloads on disk."""
    path = cache_dir() / f"{key}.json"
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            path.unlink(missing_ok=True)

    data = loader()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def clip(text: str | None, limit: int = 400) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Source:
    """Every source turns a profile's queries into normalised Findings."""

    name: str = "base"

    def search(self, profile: Profile, limit: int) -> list[Finding]:
        raise NotImplementedError
