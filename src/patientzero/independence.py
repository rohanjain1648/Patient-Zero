"""Combines echo-cluster output into a single independence score: how much of
the "142 sources agree" is actually independent corroboration vs syndicated
copies of the same 2-3 origins (spec sec 4.2).
"""
from datetime import date

from patientzero.models import EchoCluster, IndependenceScore, SearchResult

# Empirically-chosen normalization caps: beyond these, additional clusters/
# domains/days no longer meaningfully increase confidence.
CLUSTER_NORM_CAP = 5
DOMAIN_NORM_CAP = 10
TEMPORAL_NORM_CAP_DAYS = 1500


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def score_independence(
    results: list[SearchResult], clusters: list[EchoCluster]
) -> IndependenceScore:
    distinct_clusters = len(clusters)
    distinct_domains = len({r.domain for r in results})

    dates = [d for d in (_parse_date(r.date) for r in results) if d is not None]
    temporal_spread_days = (max(dates) - min(dates)).days if len(dates) >= 2 else 0

    cluster_component = min(distinct_clusters / CLUSTER_NORM_CAP, 1.0)
    domain_component = min(distinct_domains / DOMAIN_NORM_CAP, 1.0)
    temporal_component = min(temporal_spread_days / TEMPORAL_NORM_CAP_DAYS, 1.0)

    score = round(
        0.6 * cluster_component + 0.1 * domain_component + 0.3 * temporal_component, 4
    )
    score = max(0.0, min(1.0, score))

    return IndependenceScore(
        distinct_clusters=distinct_clusters,
        distinct_domains=distinct_domains,
        temporal_spread_days=temporal_spread_days,
        score=score,
    )
