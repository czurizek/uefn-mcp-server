"""Local dashboard server (stdlib http.server).

Binds to 127.0.0.1 by default. There is no authentication and none is wanted -
this is a local analysis tool reading a local database, and it should not be
exposed to a network.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from .. import config, store
from ..analytics import build_dataset
from ..analytics.kpis import derive_kpis
from . import render

# Rebuilding the dataset is ~0.1s for a few hundred islands, but the dashboard
# fires several requests per page view, so cache it briefly and invalidate on
# database mtime so a running poller's writes still show up promptly.
CACHE_TTL_SECONDS = 20.0


class DatasetCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dataset = None
        self._built_at = 0.0
        self._mtime = 0.0

    def _db_mtime(self) -> float:
        try:
            return Path(config.db_path()).stat().st_mtime
        except OSError:
            return 0.0

    def get(self, *, window_days: int = 7, force: bool = False):
        with self._lock:
            mtime = self._db_mtime()
            fresh = (
                self._dataset is not None
                and not force
                and (time.monotonic() - self._built_at) < CACHE_TTL_SECONDS
                and mtime == self._mtime
            )
            if fresh:
                return self._dataset
            conn = store.connect()
            try:
                store.init_db(conn)
                self._dataset = build_dataset(conn, window_days=window_days)
            finally:
                conn.close()
            self._built_at = time.monotonic()
            self._mtime = self._db_mtime()
            return self._dataset

    def invalidate(self) -> None:
        with self._lock:
            self._dataset = None


CACHE = DatasetCache()


def _params(query: str) -> dict[str, str]:
    parsed = urllib.parse.parse_qs(query, keep_blank_values=False)
    return {k: v[0] for k, v in parsed.items()}


class Handler(BaseHTTPRequestHandler):
    server_version = "fngg"
    protocol_version = "HTTP/1.1"

    # -------------------------------------------------------------- plumbing

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter than default
        if self.path.startswith("/api/"):
            return
        print(f"  {self.address_string()} {fmt % args}")

    def _send(self, body: str, *, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, data: Any, *, status: int = 200) -> None:
        self._send(
            json.dumps(data, indent=2, default=str),
            status=status,
            content_type="application/json; charset=utf-8",
        )

    # ----------------------------------------------------------------- routes

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = _params(parsed.query)

        try:
            self._route(path, params)
        except Exception:
            traceback.print_exc()
            self._send(
                render.layout(
                    title="Error",
                    active="",
                    body=render.page_error(
                        "Something broke rendering that page",
                        "The traceback is in the terminal running `fngg serve`.",
                    ),
                ),
                status=500,
            )

    def _route(self, path: str, params: dict) -> None:
        if path == "/favicon.ico":
            self._send("", status=404, content_type="text/plain")
            return

        if path.startswith("/api/"):
            self._api(path, params)
            return

        try:
            window = int(params.get("window") or 7)
        except ValueError:
            window = 7
        dataset = CACHE.get(window_days=max(2, min(window, 90)))

        if path == "/":
            body, title, active = render.page_discovery(dataset, params), "Discovery", "discovery"
        elif path == "/browse":
            body, title, active = render.page_browse(dataset, params), "Browse", "browse"
        elif path == "/movers":
            body, title, active = render.page_movers(dataset, params), "Movers", "movers"
        elif path == "/retention":
            body, title, active = render.page_retention(dataset, params), "Retention", "retention"
        elif path == "/engagement":
            body, title, active = render.page_engagement(dataset, params), "Engagement", "engagement"
        elif path == "/cohorts":
            body, title, active = render.page_cohorts(dataset, params), "Benchmarks", "cohorts"
        elif path == "/compare":
            body, title, active = render.page_compare(dataset, params), "Compare", "compare"
        elif path == "/status":
            body, title, active = self._status_body(dataset), "Status", "status"
        elif path.startswith("/island/"):
            code = urllib.parse.unquote(path[len("/island/"):])
            row = dataset.get(code)
            if not row:
                self._send(
                    render.layout(
                        title="Not found",
                        active="",
                        body=render.page_error(
                            f"No local data for {code}",
                            "Sync it with `fngg track <code>` then `fngg poll`.",
                        ),
                        dataset=dataset,
                    ),
                    status=404,
                )
                return
            body = self._island_body(dataset, row)
            title, active = row.get("title") or code, "browse"
        else:
            self._send(
                render.layout(
                    title="Not found", active="",
                    body=render.page_error("Page not found", path), dataset=dataset,
                ),
                status=404,
            )
            return

        self._send(render.layout(title=title, active=active, body=body, dataset=dataset))

    # ------------------------------------------------------------- page data

    def _island_body(self, dataset, row: dict) -> str:
        conn = store.connect()
        try:
            store.init_db(conn)
            history = [dict(r) for r in store.snapshot_series(conn, row["code"], dataset.interval, days=120)]
            for record in history:
                record.update(derive_kpis(record))
            gg = store.latest_gg_sample(conn, row["code"])
            placements = [dict(p) for p in store.placements_for(conn, row["code"], days=120)]
        finally:
            conn.close()
        return render.page_island(dataset, row, history, dict(gg) if gg else None, placements)

    def _status_body(self, dataset) -> str:
        conn = store.connect()
        try:
            store.init_db(conn)
            db_stats = store.stats(conn)
            runs = [dict(r) for r in store.recent_runs(conn, 15)]
            report_raw = store.get_meta(conn, "gg_probe")
        finally:
            conn.close()
        report = None
        if report_raw:
            try:
                report = json.loads(report_raw)
            except json.JSONDecodeError:
                report = None
        return render.page_status(dataset, db_stats, runs, report)

    # ------------------------------------------------------------------- api

    def _api(self, path: str, params: dict) -> None:
        dataset = CACHE.get()
        if path == "/api/summary":
            self._json(dataset.summary())
        elif path == "/api/islands":
            genre = params.get("genre")
            limit = int(params.get("limit") or 100)
            rows = dataset.filter(
                genre=None if genre in (None, "all") else genre, query=params.get("q")
            )
            self._json([_public_row(r) for r in rows[:limit]])
        elif path == "/api/discovery":
            genre = params.get("genre")
            rows = [r for r in dataset.filter(genre=None if genre in (None, "all") else genre)
                    if r.get("discovery_score") is not None]
            rows.sort(key=lambda r: -r["discovery_score"])
            self._json([_public_row(r) for r in rows[: int(params.get("limit") or 50)]])
        elif path.startswith("/api/island/"):
            code = urllib.parse.unquote(path[len("/api/island/"):])
            row = dataset.get(code)
            if not row:
                self._json({"error": "not found", "code": code}, status=404)
                return
            self._json(_public_row(row, full=True))
        else:
            self._json({"error": "unknown endpoint", "path": path}, status=404)


def _public_row(row: dict, *, full: bool = False) -> dict:
    """Strip un-serialisable internals before returning a row over HTTP."""
    out = {k: v for k, v in row.items() if k not in ("discovery", "_index")}
    if not full:
        for key in ("row_fit", "discovery_levers", "percentiles", "rank_history",
                    "momentum_ccu", "momentum_minutes"):
            out.pop(key, None)
    return out


def serve(host: Optional[str] = None, port: Optional[int] = None, *, open_browser: bool = False) -> None:
    host = host or config.WEB_HOST
    port = port or config.WEB_PORT

    conn = store.connect()
    try:
        store.init_db(conn)
        stats = store.stats(conn)
    finally:
        conn.close()

    url = f"http://{host}:{port}/"
    print(f"fngg dashboard  →  {url}")
    print(f"  database: {stats['db_path']}")
    print(f"  {stats['islands']} islands · {stats['snapshots']} snapshots · "
          f"{stats['history_days']}d of history")
    if stats["islands"] == 0:
        print("  no data yet — run `fngg demo` for sample data, or `fngg sync && fngg poll` for real data")
    print("  ctrl-c to stop\n")

    if open_browser:
        try:
            import webbrowser

            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        except Exception:
            pass

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


__all__ = ["serve", "Handler", "CACHE"]
