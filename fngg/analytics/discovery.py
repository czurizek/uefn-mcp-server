"""Discovery Fitness: modelling why an island does or does not surface.

What this is
------------
Epic publishes *what* the algorithmic Discover rows respond to - number of
players, how many play in parties, and how often players come back - but not the
formula. This module is an explicit, inspectable model built on those documented
signals, not a reconstruction of Epic's ranking. It exists to answer a question
raw counters cannot: given islands that are actually comparable to yours, which
lever is holding you back?

Every score is a cohort percentile, so a component reading 30 means "70% of
comparable islands beat you here", which is directly actionable. Nothing is a
black box: `DiscoveryScore.components` carries the percentile per component and
`weights` carries exactly what each contributed.

Party-play percentage is a documented Discover input that no public API exposes.
It is deliberately absent rather than faked, and `DiscoveryScore.caveats` says so
on every score this module produces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..genres import (
    FFA,
    LONG_FORM,
    MIXED,
    OPEN_WORLD,
    RP,
    SHORT_LOOP,
    family_of,
)
from .cohort import Cohorts

# Each component is a weighted blend of KPI percentiles inside the cohort.
DISCOVERY_COMPONENTS: dict[str, dict[str, float]] = {
    "scale": {"unique_players": 0.60, "peak_ccu": 0.40},
    "retention": {"retention_d1": 0.45, "retention_d7": 0.40, "d7_over_d1": 0.15},
    "depth": {"minutes_per_player": 0.55, "minutes_per_play": 0.25, "replays_per_player": 0.20},
    "advocacy": {"favorites_rate": 0.65, "recommend_rate": 0.35},
    # "momentum" is supplied precomputed - it needs a time series, not one row.
}

COMPONENT_LABELS = {
    "scale": "Scale",
    "retention": "Retention",
    "depth": "Session depth",
    "advocacy": "Advocacy",
    "momentum": "Momentum",
}

COMPONENT_HELP = {
    "scale": "Unique players and peak concurrency. The raw-size input the popularity rows key off.",
    "retention": "D1 and D7 return rate, plus how much of D1 survives to D7.",
    "depth": "Minutes per player, session length, and sessions per player.",
    "advocacy": "Favourites and recommendations per player - the community signal.",
    "momentum": "Seven-day growth in players and minutes, relative to the cohort.",
}

# How much each component matters, by genre. An RP island lives or dies on
# retention and session depth; an FFA map is a throughput business where raw
# concurrency and momentum dominate and a 12-minute session is already good.
GENRE_WEIGHTS: dict[str, dict[str, float]] = {
    RP: {"retention": 0.32, "depth": 0.26, "scale": 0.18, "advocacy": 0.14, "momentum": 0.10},
    OPEN_WORLD: {"retention": 0.28, "depth": 0.24, "scale": 0.20, "advocacy": 0.14, "momentum": 0.14},
    FFA: {"scale": 0.30, "retention": 0.22, "momentum": 0.22, "advocacy": 0.14, "depth": 0.12},
}

FAMILY_WEIGHTS: dict[str, dict[str, float]] = {
    LONG_FORM: {"retention": 0.30, "depth": 0.25, "scale": 0.19, "advocacy": 0.14, "momentum": 0.12},
    SHORT_LOOP: {"scale": 0.29, "retention": 0.23, "momentum": 0.21, "advocacy": 0.14, "depth": 0.13},
    MIXED: {"scale": 0.24, "retention": 0.24, "depth": 0.20, "advocacy": 0.16, "momentum": 0.16},
}

# Percentile every component is measured against when reporting upside. Cohort
# top quartile is a realistic target; 100 would make every lever look infinite.
TARGET_PERCENTILE = 75.0

CAVEATS = (
    "Model built on Epic's documented Discover inputs (player numbers, party play, return rate) - not Epic's actual ranking formula.",
    "Party-play percentage is a documented input with no public data source, so it is not represented here.",
    "Epic's Picks and By Epic are editorially curated; no metric predicts them.",
    "Scores are percentiles within a genre cohort, so they move when the cohort moves, not only when you do.",
)


@dataclass
class DiscoveryScore:
    code: str
    genre: str
    score: Optional[float]
    components: dict[str, Optional[float]] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    cohort_key: str = ""
    cohort_size: int = 0
    data_completeness: float = 0.0
    caveats: tuple[str, ...] = CAVEATS

    @property
    def levers(self) -> list[dict]:
        """Components ranked by how many points fixing them would be worth.

        Upside is weight x distance to the cohort's 75th percentile, so a weak
        component that barely counts for this genre never outranks a nearly-as-
        weak component that counts double.
        """
        out = []
        for name, pct in self.components.items():
            if pct is None:
                continue
            weight = self.weights.get(name, 0.0)
            gap = max(TARGET_PERCENTILE - pct, 0.0)
            out.append(
                {
                    "component": name,
                    "label": COMPONENT_LABELS.get(name, name),
                    "percentile": pct,
                    "weight": weight,
                    "upside": round(weight * gap, 2),
                    "help": COMPONENT_HELP.get(name, ""),
                }
            )
        out.sort(key=lambda item: item["upside"], reverse=True)
        return out

    @property
    def top_lever(self) -> Optional[dict]:
        levers = [l for l in self.levers if l["upside"] > 0]
        return levers[0] if levers else None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "genre": self.genre,
            "score": self.score,
            "components": self.components,
            "weights": self.weights,
            "contributions": self.contributions,
            "missing": self.missing,
            "cohort_key": self.cohort_key,
            "cohort_size": self.cohort_size,
            "data_completeness": self.data_completeness,
            "levers": self.levers,
            "caveats": list(self.caveats),
        }


def weights_for(genre: Optional[str]) -> dict[str, float]:
    genre = genre or "other"
    if genre in GENRE_WEIGHTS:
        return dict(GENRE_WEIGHTS[genre])
    return dict(FAMILY_WEIGHTS.get(family_of(genre), FAMILY_WEIGHTS[MIXED]))


def score_discovery(
    row: dict,
    cohorts: Cohorts,
    *,
    momentum_percentile: Optional[float] = None,
) -> DiscoveryScore:
    """Score one island. `row` must already carry derived KPIs."""
    genre = row.get("genre") or "other"
    weights = weights_for(genre)

    components: dict[str, Optional[float]] = {}
    missing: list[str] = []

    for name, metric_weights in DISCOVERY_COMPONENTS.items():
        value = cohorts.blended_percentile(genre, row, metric_weights)
        components[name] = value
        if value is None:
            missing.append(name)
        else:
            for metric in metric_weights:
                if row.get(metric) is None:
                    missing.append(metric)

    components["momentum"] = momentum_percentile
    if momentum_percentile is None:
        missing.append("momentum")

    present = {k: v for k, v in components.items() if v is not None}
    total_weight = sum(weights.get(k, 0.0) for k in present)
    contributions: dict[str, float] = {}
    score: Optional[float] = None
    if total_weight > 0:
        raw = 0.0
        for name, pct in present.items():
            share = weights.get(name, 0.0) / total_weight
            contributions[name] = round(pct * share, 2)
            raw += pct * share
        score = round(raw, 2)

    completeness = round(total_weight / sum(weights.values()), 3) if weights else 0.0

    return DiscoveryScore(
        code=str(row.get("code") or ""),
        genre=genre,
        score=score,
        components=components,
        weights=weights,
        contributions=contributions,
        missing=sorted(set(missing)),
        cohort_key=cohorts.resolve_key(genre, "unique_players"),
        cohort_size=cohorts.size(genre, "unique_players"),
        data_completeness=completeness,
    )


# ------------------------------------------------------- Discover row fit
#
# The Discover surface is a stack of rows, and they do not reward the same
# things. An island can be a lock for "Community Choice" and invisible in
# "Trending" at the same time. Each archetype below re-weights the *same*
# components, so a single set of measurements explains placement across every
# tab rather than producing one undifferentiated "quality" number.

ROW_ARCHETYPES: list[dict] = [
    {
        "key": "epics_picks",
        "label": "Epic's Picks",
        "curated": True,
        "weights": {},
        "note": "Hand-curated by Epic. Metrics do not qualify you; submissions, polish and originality do.",
    },
    {
        "key": "by_epic",
        "label": "By Epic",
        "curated": True,
        "weights": {},
        "note": "Epic-made islands only. Not reachable by creator content.",
    },
    {
        "key": "popular",
        "label": "Popular",
        "curated": False,
        "weights": {"scale": 0.70, "retention": 0.20, "depth": 0.10},
        "note": "Raw audience size. Hardest row to enter cold and the most self-reinforcing once you are in.",
    },
    {
        "key": "trending",
        "label": "Trending / Rising",
        "curated": False,
        "weights": {"momentum": 0.65, "scale": 0.20, "retention": 0.15},
        "note": "Rate of change, not absolute size. The realistic first row for a small island - a good update window is worth more here than a big back catalogue.",
    },
    {
        "key": "new_releases",
        "label": "New Releases",
        "curated": False,
        "weights": {"retention": 0.40, "momentum": 0.35, "depth": 0.25},
        "note": "Time-boxed. Early retention decides whether the launch window converts into a durable row placement.",
        "recency_days": 30,
    },
    {
        "key": "players_like_you",
        "label": "By Players Like You",
        "curated": False,
        "weights": {"retention": 0.50, "depth": 0.30, "advocacy": 0.20},
        "note": "Personalised from play history. Rewards islands people return to, which is why RP and open world over-index here.",
    },
    {
        "key": "community_choice",
        "label": "Community Choice",
        "curated": False,
        "weights": {"advocacy": 0.60, "retention": 0.25, "depth": 0.15},
        "note": "Favourites and recommendations per player. The one row a small island can win on ratio rather than volume.",
    },
    {
        "key": "top_charts",
        "label": "Top Charts / Most Played",
        "curated": False,
        "weights": {"scale": 0.45, "depth": 0.40, "retention": 0.15},
        "note": "Driven by total minutes played, so long sessions substitute for headcount. Structurally favours RP and open world.",
    },
]


def row_fit(score: DiscoveryScore, *, age_days: Optional[float] = None) -> list[dict]:
    """Fit against each Discover row archetype, best first.

    Curated rows are reported as not-modelled rather than scored, so nothing in
    the UI implies a metric can earn an editorial slot.
    """
    results: list[dict] = []
    for archetype in ROW_ARCHETYPES:
        entry = {
            "key": archetype["key"],
            "label": archetype["label"],
            "curated": archetype["curated"],
            "note": archetype["note"],
            "fit": None,
            "eligible": True,
            "drivers": [],
        }

        if archetype["curated"]:
            entry["eligible"] = False
            results.append(entry)
            continue

        weights = archetype["weights"]
        total_weight = 0.0
        total = 0.0
        drivers = []
        for component, weight in weights.items():
            pct = score.components.get(component)
            if pct is None:
                continue
            total += pct * weight
            total_weight += weight
            drivers.append(
                {"component": component, "label": COMPONENT_LABELS.get(component, component),
                 "percentile": pct, "weight": weight}
            )
        if total_weight > 0:
            entry["fit"] = round(total / total_weight, 2)
        drivers.sort(key=lambda d: d["weight"], reverse=True)
        entry["drivers"] = drivers

        window = archetype.get("recency_days")
        if window and age_days is not None and age_days > window:
            entry["eligible"] = False
            entry["note"] = (
                f"{archetype['note']} This island is ~{age_days:.0f} days old, "
                f"past the ~{window}-day window."
            )

        results.append(entry)

    results.sort(key=lambda e: (e["curated"], not e["eligible"], -(e["fit"] or -1)))
    return results


__all__ = [
    "DISCOVERY_COMPONENTS",
    "COMPONENT_LABELS",
    "COMPONENT_HELP",
    "GENRE_WEIGHTS",
    "ROW_ARCHETYPES",
    "TARGET_PERCENTILE",
    "CAVEATS",
    "DiscoveryScore",
    "weights_for",
    "score_discovery",
    "row_fit",
]
