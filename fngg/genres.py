"""Genre classification for islands.

The point of this module is that a single global leaderboard is misleading. An
RP city with 90-minute sessions and a box-fight map with 4-minute sessions are
not competing for the same Discover slot and should never be benchmarked against
each other. Everything downstream - cohort percentiles, Discovery Fitness
weights, retention bands - keys off the genre assigned here.

Classification runs in three passes:
  1. a manual override, if the user set one;
  2. weighted keyword matching over title + tags + Epic category;
  3. a behavioural fallback from session length and replays-per-player, for
     islands whose text says nothing useful ("MY MAP v2").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

# --------------------------------------------------------------------- genres

RP = "rp"
FFA = "ffa"
OPEN_WORLD = "open_world"
BOX_FIGHT = "box_fight"
ZONE_WARS = "zone_wars"
PRACTICE = "practice"
TYCOON = "tycoon"
HORROR = "horror"
PARKOUR = "parkour"
PUZZLE = "puzzle"
RACING = "racing"
PVE = "pve"
PARTY = "party"
HIDE = "hide_and_seek"
PROP_HUNT = "prop_hunt"
BR = "battle_royale"
MUSIC = "music"
OTHER = "other"

# The three the dashboard treats as first-class, in the order they are shown.
FOCUS_GENRES = (RP, FFA, OPEN_WORLD)

GENRE_LABELS = {
    RP: "Roleplay",
    FFA: "FFA / Deathmatch",
    OPEN_WORLD: "Open World",
    BOX_FIGHT: "Box Fight",
    ZONE_WARS: "Zone Wars",
    PRACTICE: "Aim / Practice",
    TYCOON: "Tycoon / Idle",
    HORROR: "Horror",
    PARKOUR: "Parkour / Deathrun",
    PUZZLE: "Puzzle / Escape",
    RACING: "Racing",
    PVE: "PvE / Survival",
    PARTY: "Party / Minigames",
    HIDE: "Hide & Seek",
    PROP_HUNT: "Prop Hunt",
    BR: "Battle Royale",
    MUSIC: "Music / Social",
    OTHER: "Other",
}

# Session-shape families. Discovery weighting and retention bands differ sharply
# between them, so several analytics functions branch on the family, not the
# individual genre.
LONG_FORM = "long_form"    # sessions measured in tens of minutes, retention-led
SHORT_LOOP = "short_loop"  # fast rounds, throughput- and concurrency-led
MIXED = "mixed"

GENRE_FAMILY = {
    RP: LONG_FORM,
    OPEN_WORLD: LONG_FORM,
    TYCOON: LONG_FORM,
    PVE: LONG_FORM,
    FFA: SHORT_LOOP,
    BOX_FIGHT: SHORT_LOOP,
    ZONE_WARS: SHORT_LOOP,
    PRACTICE: SHORT_LOOP,
    PARKOUR: MIXED,
    PUZZLE: MIXED,
    HORROR: MIXED,
    RACING: SHORT_LOOP,
    PARTY: MIXED,
    HIDE: SHORT_LOOP,
    PROP_HUNT: SHORT_LOOP,
    BR: MIXED,
    MUSIC: LONG_FORM,
    OTHER: MIXED,
}


def family_of(genre: Optional[str]) -> str:
    return GENRE_FAMILY.get(genre or OTHER, MIXED)


def label_of(genre: Optional[str]) -> str:
    return GENRE_LABELS.get(genre or OTHER, "Other")


# ------------------------------------------------------------------- keywords
# (pattern, weight). Patterns are matched as whole words on normalised text, so
# "rp" hits "city rp" but not "corporate". Higher weight = stronger evidence.

KEYWORDS: dict[str, Sequence[tuple[str, float]]] = {
    RP: (
        ("roleplay", 5), ("role play", 5), ("rp", 3), ("life rp", 6), ("city rp", 6),
        ("school rp", 6), ("prison rp", 6), ("hospital", 2), ("police", 2),
        ("jobs", 2), ("job sim", 3), ("town", 2), ("city life", 4), ("family", 2),
        ("neighborhood", 3), ("story mode", 2), ("drama", 2), ("high school", 3),
        ("apartment", 2), ("restaurant", 2), ("hotel", 2), ("mall", 2),
        ("brookhaven", 5), ("bloxburg", 4), ("life simulator", 4), ("daily life", 4),
    ),
    FFA: (
        ("ffa", 6), ("free for all", 6), ("free-for-all", 6), ("deathmatch", 5),
        ("tdm", 4), ("team deathmatch", 5), ("gun game", 4), ("gungame", 4),
        ("shootout", 3), ("kill race", 4), ("1v1", 3), ("2v2", 2), ("arena", 2),
        ("respawn", 2), ("infinite", 1), ("pvp arena", 4), ("frag", 3),
        ("first to", 2), ("red vs blue", 3), ("gunfight", 3),
    ),
    OPEN_WORLD: (
        ("open world", 6), ("open-world", 6), ("openworld", 6), ("sandbox", 4),
        ("exploration", 3), ("explore", 2), ("survival", 3), ("rpg", 3),
        ("mmo", 4), ("quest", 2), ("adventure", 2), ("crafting", 3), ("craft", 2),
        ("biome", 2), ("world", 1), ("kingdom", 2), ("island life", 3),
        ("base building", 3), ("looting", 2),
    ),
    BOX_FIGHT: (
        ("box fight", 6), ("boxfight", 6), ("box pvp", 4), ("piece control", 4),
        ("build fight", 4), ("realistic", 2), ("mongraal", 2),
    ),
    ZONE_WARS: (
        ("zone wars", 6), ("zonewars", 6), ("zone war", 6), ("endgame", 3),
        ("storm", 2), ("late game", 3),
    ),
    PRACTICE: (
        ("aim", 4), ("aim trainer", 6), ("edit course", 6), ("edit", 2),
        ("warm up", 4), ("warmup", 4), ("training", 4), ("practice", 5),
        ("piece", 2), ("kovaaks", 4), ("raider", 2), ("free build", 3),
    ),
    TYCOON: (
        ("tycoon", 6), ("idle", 5), ("clicker", 5), ("simulator", 3),
        ("factory", 3), ("empire", 3), ("business", 3), ("farm", 2),
        ("money", 2), ("upgrade", 2), ("afk", 3),
    ),
    HORROR: (
        ("horror", 6), ("scary", 4), ("nightmare", 3), ("haunted", 4),
        ("granny", 3), ("backrooms", 5), ("survive the night", 4), ("creepy", 3),
    ),
    PARKOUR: (
        ("parkour", 6), ("deathrun", 6), ("death run", 6), ("obstacle", 3),
        ("obby", 5), ("jump", 2), ("climb", 2), ("tower of", 3),
    ),
    PUZZLE: (
        ("escape", 5), ("puzzle", 5), ("riddle", 4), ("find the", 3),
        ("hidden", 2), ("maze", 3), ("mystery", 3),
    ),
    RACING: (
        ("race", 4), ("racing", 5), ("drift", 4), ("kart", 4), ("circuit", 3),
        ("rally", 3), ("track", 2), ("speedrun", 3),
    ),
    PVE: (
        ("zombie", 4), ("horde", 4), ("wave", 2), ("tower defense", 5),
        ("td", 2), ("pve", 5), ("boss fight", 4), ("defend", 2), ("co-op", 3),
        ("coop", 3), ("raid", 3),
    ),
    PARTY: (
        ("mini game", 5), ("minigame", 5), ("party", 4), ("random", 2),
        ("fun", 1), ("board game", 4), ("trivia", 4), ("quiz", 4),
        ("bed wars", 4), ("bedwars", 4), ("murder mystery", 4),
    ),
    HIDE: (("hide and seek", 6), ("hide & seek", 6), ("hide n seek", 6), ("seeker", 3)),
    PROP_HUNT: (("prop hunt", 6), ("prophunt", 6), ("prop-hunt", 6)),
    BR: (("battle royale", 5), ("br map", 4), ("solo squad", 3), ("victory royale", 3)),
    MUSIC: (("music", 4), ("concert", 5), ("dance", 3), ("hangout", 4), ("chill", 3), ("lobby", 2)),
}

_COMPILED: dict[str, list[tuple[re.Pattern, float]]] = {
    genre: [
        (re.compile(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])"), weight)
        for word, weight in words
    ]
    for genre, words in KEYWORDS.items()
}


def normalise(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return f" {text.strip()} "


# ------------------------------------------------------------------- results


@dataclass
class Classification:
    genre: str
    confidence: float
    source: str
    scores: dict[str, float]

    @property
    def label(self) -> str:
        return label_of(self.genre)

    @property
    def family(self) -> str:
        return family_of(self.genre)


def score_text(title: Optional[str], tags: Iterable[str] = (), category: Optional[str] = None) -> dict[str, float]:
    """Keyword score per genre. Tags weigh more than the title - a creator who
    tags "Roleplay" is telling Epic's own taxonomy what this island is."""
    title_text = normalise(title or "")
    tag_text = normalise(" ".join(str(t) for t in (tags or [])))
    cat_text = normalise(category or "")

    scores: dict[str, float] = {}
    for genre, patterns in _COMPILED.items():
        total = 0.0
        for pattern, weight in patterns:
            if pattern.search(tag_text):
                total += weight * 1.5
            if pattern.search(title_text):
                total += weight
            if pattern.search(cat_text):
                total += weight * 1.2
        if total:
            scores[genre] = round(total, 2)
    return scores


def classify_behaviour(
    average_minutes_per_player: Optional[float],
    plays: Optional[float] = None,
    unique_players: Optional[float] = None,
    retention_d1: Optional[float] = None,
) -> Optional[tuple[str, float]]:
    """Fallback guess from how the island is actually played.

    This can only resolve to a *family-typical* genre, never a specific one, so
    it returns the family's representative genre with deliberately low
    confidence. RP and open world both live in long-form; open world is the
    safer default of the two because it makes weaker claims downstream.
    """
    minutes = average_minutes_per_player
    if minutes is None or minutes <= 0:
        return None

    replays = None
    if plays and unique_players and unique_players > 0:
        replays = plays / unique_players

    if minutes >= 45:
        # Long sessions plus sticky day-1 is the RP signature.
        if retention_d1 is not None and retention_d1 >= 0.25:
            return RP, 0.35
        return OPEN_WORLD, 0.3
    if minutes <= 12 and (replays is None or replays >= 1.8):
        return FFA, 0.3
    if minutes <= 25:
        return FFA, 0.2
    return OPEN_WORLD, 0.2


def classify(
    title: Optional[str] = None,
    tags: Iterable[str] = (),
    category: Optional[str] = None,
    *,
    override: Optional[str] = None,
    average_minutes_per_player: Optional[float] = None,
    plays: Optional[float] = None,
    unique_players: Optional[float] = None,
    retention_d1: Optional[float] = None,
) -> Classification:
    if override:
        return Classification(override, 1.0, "override", {})

    scores = score_text(title, tags, category)
    if scores:
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_genre, top_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        # Confidence blends absolute evidence with how clearly it beat the
        # next-best genre, so "roleplay tycoon" lands as a low-confidence RP
        # rather than a confident one.
        separation = (top_score - runner_up) / top_score if top_score else 0.0
        strength = min(top_score / 9.0, 1.0)
        confidence = round(max(0.25, min(0.98, 0.45 * strength + 0.55 * separation * strength + 0.25)), 3)
        return Classification(top_genre, confidence, "keywords", scores)

    guessed = classify_behaviour(average_minutes_per_player, plays, unique_players, retention_d1)
    if guessed:
        return Classification(guessed[0], guessed[1], "behaviour", {})

    return Classification(OTHER, 0.1, "unknown", {})


def classify_row(row: dict) -> Classification:
    """Classify from a store row / dict as produced by `store.row_to_dict`."""
    return classify(
        title=row.get("title"),
        tags=row.get("tags") or [],
        category=row.get("category"),
        override=row.get("genre_override"),
        average_minutes_per_player=row.get("average_minutes_per_player"),
        plays=row.get("plays"),
        unique_players=row.get("unique_players"),
        retention_d1=row.get("retention_d1"),
    )


def all_genres() -> list[str]:
    return list(GENRE_LABELS.keys())
