"""Synthetic island data.

Two jobs. It is the fixture the test suite runs against, and it is what
`fngg demo` loads so the dashboard is explorable before you have collected any
real history - which matters here more than in most apps, because Epic never
backfills and a fresh database is genuinely empty on day one.

The distributions are shaped per genre from how these formats actually behave:
RP cities run 45-140 minute sessions with day-1 retention in the 20-40% band,
FFA maps run 6-22 minute sessions with far more sessions per player, and open
world sits between the two with the best day-7 hold. Everything downstream
(minutes played, peak CCU, favourites) is then derived from those so the rows
stay internally consistent instead of being independently random.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from . import store
from .genres import BOX_FIGHT, FFA, HORROR, OPEN_WORLD, PARKOUR, PRACTICE, PVE, RP, TYCOON, ZONE_WARS
from .sources.ecosystem import Island, MetricReading

# genre -> (players_lo, players_hi, minutes_lo, minutes_hi, d1_lo, d1_hi,
#           d7_ratio_lo, d7_ratio_hi, replays_lo, replays_hi, fav_lo, fav_hi)
PROFILES = {
    RP:         (200, 80_000, 45, 140, 0.18, 0.42, 0.30, 0.55, 1.1, 2.2, 0.045, 0.115),
    OPEN_WORLD: (150, 50_000, 28,  95, 0.15, 0.38, 0.32, 0.58, 1.2, 2.4, 0.035, 0.095),
    FFA:        (300, 60_000,  6,  22, 0.10, 0.30, 0.14, 0.34, 1.8, 4.5, 0.010, 0.042),
    BOX_FIGHT:  (150, 30_000,  5,  18, 0.09, 0.28, 0.12, 0.30, 2.0, 5.0, 0.008, 0.035),
    ZONE_WARS:  (120, 25_000,  8,  24, 0.10, 0.27, 0.13, 0.32, 1.7, 3.8, 0.010, 0.038),
    PRACTICE:   (200, 40_000, 10,  35, 0.12, 0.34, 0.18, 0.40, 1.6, 4.0, 0.012, 0.045),
    TYCOON:     (180, 45_000, 35, 120, 0.16, 0.40, 0.28, 0.52, 1.2, 2.6, 0.030, 0.090),
    PVE:        (100, 20_000, 22,  70, 0.13, 0.33, 0.22, 0.46, 1.3, 2.8, 0.025, 0.075),
    HORROR:     ( 80, 18_000, 15,  55, 0.08, 0.24, 0.10, 0.28, 1.1, 2.0, 0.020, 0.070),
    PARKOUR:    ( 90, 22_000, 12,  45, 0.09, 0.26, 0.12, 0.30, 1.2, 2.4, 0.015, 0.055),
}

TITLE_PARTS = {
    RP: (
        ["Los Angeles", "Miami", "Tokyo", "Greenview", "Northbridge", "Sunset Bay", "Ravenwood",
         "Silver Lake", "Kingsport", "Redhill"],
        ["City RP", "Life RP", "Roleplay", "Town Roleplay", "High School RP", "Police RP",
         "Hospital RP", "Family Life RP"],
    ),
    OPEN_WORLD: (
        ["Frostlands", "Verdant", "Ashfall", "Emberpeak", "Driftwood", "Ironvale", "Wildmoor"],
        ["Open World Survival", "Open World RPG", "Sandbox World", "Survival Craft",
         "Open World Adventure", "Exploration RPG"],
    ),
    FFA: (
        ["Neon", "Warehouse", "Rooftop", "Desert", "Skyline", "Bunker", "Harbor"],
        ["FFA Arena", "Free For All", "Team Deathmatch", "Gun Game FFA", "Infinite FFA",
         "Respawn Deathmatch"],
    ),
    BOX_FIGHT: (["Pro", "Clix", "Ranked", "Duo"], ["Box Fight", "Box Fights + Zone Wars", "Piece Control Boxfight"]),
    ZONE_WARS: (["Desert", "Tilted", "Downhill"], ["Zone Wars", "Endgame Zone Wars", "Late Game Zone Wars"]),
    PRACTICE: (["Aim", "Edit", "Raider"], ["Training Course", "Aim Trainer", "Edit Course", "Warm Up Map"]),
    TYCOON: (["Pizza", "Oil", "Mining", "Airport"], ["Tycoon", "Idle Tycoon", "Business Simulator"]),
    PVE: (["Zombie", "Horde", "Nightfall"], ["Survival PvE", "Tower Defense", "Co-op Horde"]),
    HORROR: (["Silent", "Abandoned", "Backrooms"], ["Horror Escape", "Scary Map", "Haunted House"]),
    PARKOUR: (["Rainbow", "Sky", "Neon"], ["Deathrun", "Parkour Tower", "Obby Course"]),
}

TAGS = {
    RP: ["Roleplay", "Adventure"],
    OPEN_WORLD: ["Open World", "Survival"],
    FFA: ["Deathmatch", "Combat", "Practice"],
    BOX_FIGHT: ["Combat", "Practice"],
    ZONE_WARS: ["Combat", "Practice"],
    PRACTICE: ["Practice", "Combat"],
    TYCOON: ["Simulation", "Idle"],
    PVE: ["Co-op", "Survival"],
    HORROR: ["Horror", "Adventure"],
    PARKOUR: ["Parkour", "Obstacle"],
}

CREATORS = ["nordvex", "atlasbuilt", "kryostudio", "pinehollow", "vaultworks", "lumenlabs",
            "ninebit", "greyfoxgames", "hexaform", "sablecore"]


def _code(rng: random.Random) -> str:
    return "-".join(f"{rng.randint(0, 9999):04d}" for _ in range(3))


def _title(rng: random.Random, genre: str) -> str:
    prefixes, suffixes = TITLE_PARTS.get(genre, (["Custom"], ["Map"]))
    title = f"{rng.choice(prefixes)} {rng.choice(suffixes)}"
    if rng.random() < 0.18:
        title = f"{title} {rng.choice(['v2', 'S2', '2.0', 'REMASTERED'])}"
    return title


def generate(
    count: int = 140, days: int = 21, seed: int = 20260824
) -> tuple[list[Island], list[MetricReading]]:
    """Build a catalogue and a day-by-day metric history for it."""
    rng = random.Random(seed)
    genres = list(PROFILES)
    # Weighted so the three focus genres dominate the sample, as they do in the
    # real Discover surface.
    weights = [4 if g in (RP, FFA, OPEN_WORLD) else 1 for g in genres]

    islands: list[Island] = []
    readings: list[MetricReading] = []
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    for _ in range(count):
        genre = rng.choices(genres, weights=weights, k=1)[0]
        profile = PROFILES[genre]
        p_lo, p_hi, m_lo, m_hi, d1_lo, d1_hi, r_lo, r_hi, rep_lo, rep_hi, f_lo, f_hi = profile

        code = _code(rng)
        age_days = rng.choice([rng.randint(2, 25), rng.randint(30, 400), rng.randint(30, 400)])
        island = Island(
            code=code,
            title=_title(rng, genre),
            creator_code=rng.choice(CREATORS),
            category="Island",
            created_in=(today - timedelta(days=age_days)).isoformat(timespec="seconds"),
            tags=rng.sample(TAGS.get(genre, ["Other"]), k=min(2, len(TAGS.get(genre, ["Other"])))),
        )
        islands.append(island)

        # Log-uniform so the catalogue has the long tail a real one does.
        base_players = _log_uniform(rng, p_lo, p_hi)
        minutes_per_player = rng.uniform(m_lo, m_hi)
        d1 = rng.uniform(d1_lo, d1_hi)
        d7 = d1 * rng.uniform(r_lo, r_hi)
        replays = rng.uniform(rep_lo, rep_hi)
        fav_rate = rng.uniform(f_lo, f_hi)
        peak_factor = rng.uniform(2.2, 4.4)

        # A per-island daily drift, so the movers tab has real risers and fallers.
        drift = rng.choice(
            [rng.uniform(-0.06, -0.015), rng.uniform(-0.01, 0.01), rng.uniform(0.015, 0.07)]
        )
        noise = rng.uniform(0.03, 0.12)

        history_days = min(days, max(age_days, 2))
        for offset in range(history_days, 0, -1):
            day = today - timedelta(days=offset - 1)
            steps = history_days - offset
            trend = (1 + drift) ** steps
            players = max(1.0, base_players * trend * rng.gauss(1.0, noise))
            session = max(1.0, minutes_per_player * rng.gauss(1.0, 0.05))
            minutes = players * session
            plays = players * replays * rng.gauss(1.0, 0.05)
            readings.append(
                MetricReading(
                    code=code,
                    interval="day",
                    captured_at=day.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    unique_players=round(players),
                    peak_ccu=round(max(1.0, (minutes / 1440.0) * peak_factor)),
                    minutes_played=round(minutes),
                    average_minutes_per_player=round(session, 2),
                    plays=round(plays),
                    favorites=round(players * fav_rate * rng.gauss(1.0, 0.08)),
                    recommendations=round(players * fav_rate * 0.25 * rng.gauss(1.0, 0.1)),
                    retention_d1=round(min(0.95, d1 * rng.gauss(1.0, 0.06)), 4),
                    retention_d7=round(min(0.9, d7 * rng.gauss(1.0, 0.08)), 4),
                )
            )

    return islands, readings


def _log_uniform(rng: random.Random, low: float, high: float) -> float:
    import math

    return math.exp(rng.uniform(math.log(low), math.log(high)))


def load_into(conn, *, count: int = 140, days: int = 21, seed: int = 20260824) -> dict:
    """Write a generated catalogue + history into an open database."""
    islands, readings = generate(count=count, days=days, seed=seed)
    store.upsert_islands(conn, islands)
    written = store.insert_snapshots(conn, readings)
    # Track a handful so the "tracked only" filter has something to show.
    for island in islands[:8]:
        store.set_tracked(conn, island.code, True)
    store.set_meta(conn, "demo_seeded_at", store.utcnow())
    conn.commit()
    return {"islands": len(islands), "snapshots": written, "days": days}


__all__ = ["generate", "load_into", "PROFILES"]
