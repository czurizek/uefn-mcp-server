"""Small stdlib HTTP helper: retries, backoff, gzip, and a global rate limit.

No third-party dependencies on purpose - this app should run from a fresh
checkout with nothing but CPython installed.
"""

from __future__ import annotations

import gzip
import json
import random
import threading
import time
import urllib.error
import urllib.request
import zlib
from typing import Any, Optional

from . import config

__all__ = ["HttpError", "NotFound", "get_json", "get_text", "RateLimiter"]


class HttpError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class NotFound(HttpError):
    """404 - for the Ecosystem API this means 'not public / not discoverable'."""


class RateLimiter:
    """Token bucket shared by every caller in the process."""

    def __init__(self, rps: float):
        self.rps = max(rps, 0.1)
        self._lock = threading.Lock()
        self._next_free = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            gap = 1.0 / self.rps
            start = max(now, self._next_free)
            self._next_free = start + gap
        wait = start - now
        if wait > 0:
            time.sleep(wait)


_limiter = RateLimiter(config.RATE_LIMIT_RPS)


def _decode(raw: bytes, encoding: str) -> bytes:
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def _request(url: str, *, headers: dict, timeout: float) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = (resp.headers.get("Content-Encoding") or "").lower()
            return resp.status, _decode(raw, enc), dict(resp.headers)
    except urllib.error.HTTPError as exc:  # 4xx / 5xx still carry a body
        raw = exc.read() if hasattr(exc, "read") else b""
        enc = (exc.headers.get("Content-Encoding") or "").lower() if exc.headers else ""
        try:
            raw = _decode(raw, enc)
        except Exception:
            pass
        return exc.code, raw, dict(exc.headers or {})


def fetch(
    url: str,
    *,
    accept: str = "application/json",
    timeout: Optional[float] = None,
    retries: Optional[int] = None,
    extra_headers: Optional[dict] = None,
) -> bytes:
    """GET a URL, retrying transient failures. Raises NotFound on 404."""
    timeout = config.HTTP_TIMEOUT if timeout is None else timeout
    retries = config.HTTP_RETRIES if retries is None else retries

    headers = {
        "Accept": accept,
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": config.USER_AGENT,
    }
    if extra_headers:
        headers.update(extra_headers)

    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        _limiter.acquire()
        try:
            status, body, resp_headers = _request(url, headers=headers, timeout=timeout)
        except Exception as exc:  # socket timeouts, DNS, TLS, connection resets
            last = HttpError(f"network error for {url}: {exc}")
            if attempt < retries:
                _sleep_backoff(attempt)
                continue
            raise last from exc

        if status == 404:
            raise NotFound(f"404 for {url}", status=404, body=_snip(body))

        if status == 429 or status >= 500:
            last = HttpError(f"HTTP {status} for {url}", status=status, body=_snip(body))
            if attempt < retries:
                retry_after = resp_headers.get("Retry-After")
                _sleep_backoff(attempt, retry_after)
                continue
            raise last

        if status >= 400:
            # 4xx other than 404/429 are not transient - fail immediately.
            raise HttpError(f"HTTP {status} for {url}", status=status, body=_snip(body))

        return body

    raise last or HttpError(f"request failed for {url}")


def _sleep_backoff(attempt: int, retry_after: Optional[str] = None) -> None:
    if retry_after:
        try:
            time.sleep(min(float(retry_after), 30.0))
            return
        except (TypeError, ValueError):
            pass
    # 0.5s, 1s, 2s ... with jitter so parallel callers do not resonate.
    time.sleep(0.5 * (2**attempt) + random.uniform(0, 0.25))


def _snip(body: bytes, limit: int = 400) -> str:
    try:
        text = body.decode("utf-8", "replace")
    except Exception:
        return ""
    return text[:limit]


def get_json(url: str, **kwargs: Any) -> Any:
    body = fetch(url, accept="application/json", **kwargs)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HttpError(f"invalid JSON from {url}: {exc}", body=_snip(body)) from exc


def get_text(url: str, **kwargs: Any) -> str:
    kwargs.setdefault("accept", "text/html,application/xhtml+xml,*/*;q=0.8")
    return fetch(url, **kwargs).decode("utf-8", "replace")
