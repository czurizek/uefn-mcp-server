"""Analytics layer: KPIs, cohort benchmarks, Discovery modelling, momentum."""

from .kpis import KPIS, KPI_LABELS, derive_kpis, format_kpi
from .cohort import Cohorts, CohortStats, percentile_of
from .discovery import (
    DISCOVERY_COMPONENTS,
    ROW_ARCHETYPES,
    DiscoveryScore,
    score_discovery,
    row_fit,
)
from .movers import MomentumResult, compute_momentum, rank_series
from .dataset import Dataset, build_dataset

__all__ = [
    "KPIS",
    "KPI_LABELS",
    "derive_kpis",
    "format_kpi",
    "Cohorts",
    "CohortStats",
    "percentile_of",
    "DISCOVERY_COMPONENTS",
    "ROW_ARCHETYPES",
    "DiscoveryScore",
    "score_discovery",
    "row_fit",
    "MomentumResult",
    "compute_momentum",
    "rank_series",
    "Dataset",
    "build_dataset",
]
