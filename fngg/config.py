"""Paths, tunables and shared constants."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "fngg"
USER_AGENT = "fngg-map-analytics/0.1.0 (+local research tool)"

# ---------------------------------------------------------------- data location

def data_dir() -> Path:
    """Where the SQLite database and cache live.

    Override with FNGG_HOME. Defaults to ~/.fngg so the database survives a
    `git clean` of the checkout.
    """
    env = os.environ.get("FNGG_HOME")
    root = Path(env).expanduser() if env else Path.home() / f".{APP_NAME}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    env = os.environ.get("FNGG_DB")
    if env:
        p = Path(env).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return data_dir() / "fngg.sqlite3"


# ------------------------------------------------------------------- endpoints

ECOSYSTEM_BASE = os.environ.get(
    "FNGG_ECOSYSTEM_BASE", "https://api.fortnite.com/ecosystem/v1"
)
FORTNITE_GG_BASE = os.environ.get("FNGG_GG_BASE", "https://fortnite.gg")

# ------------------------------------------------------------------- http knobs

HTTP_TIMEOUT = float(os.environ.get("FNGG_HTTP_TIMEOUT", "20"))
HTTP_RETRIES = int(os.environ.get("FNGG_HTTP_RETRIES", "3"))
# Epic does not publish a rate limit. Be a good citizen: this is requests/second
# across the whole process, enforced by a token bucket in http_client.
RATE_LIMIT_RPS = float(os.environ.get("FNGG_RATE_LIMIT_RPS", "6"))

# ---------------------------------------------------------------- poll defaults

# Ecosystem metric intervals. `day` rolls over once a day (polling faster writes
# nothing new); `hour` and `minute` do move, at the cost of far more requests.
INTERVALS = ("day", "hour", "minute")
DEFAULT_INTERVAL = "day"

# How many islands the catalog sync will walk before stopping, so a first run on
# a laptop does not spend an hour paginating ~100 islands at a time.
DEFAULT_CATALOG_LIMIT = int(os.environ.get("FNGG_CATALOG_LIMIT", "5000"))

WEB_HOST = os.environ.get("FNGG_WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("FNGG_WEB_PORT", "8770"))
