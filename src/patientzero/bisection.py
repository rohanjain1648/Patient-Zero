# src/patientzero/bisection.py
"""Temporal bisection: find the earliest indexed-date window in which a claim's
corroborated evidence first appears (spec sec 4.1).

Algorithm:
  1. Exponential bracket probe at today-1y, today-3y, today-8y to find a window
     that already contains corroborated evidence (the "positive" bracket) and one
     that doesn't (the "negative" bracket).
  2. Bisect between the negative and positive bracket dates until the window is
     within ~1 month.
  3. Every probe's results must pass BOTH a relevance check (are these results
     actually about this claim?) AND a corroboration requirement (>=2 results)
     before the window counts as "positive". A window returning results is not
     the same as a window returning evidence for this claim.
"""
from datetime import date, timedelta
from typing import Callable

from patientzero.models import Claim, OriginCandidate, SearchResult
from patientzero.query_planner import build_date_restricted_query

BRACKET_OFFSETS_YEARS = (1, 3, 8)
MIN_CORROBORATION = 2
BISECTION_TOLERANCE_DAYS = 31
# Safety valve against a runaway loop, not the primary convergence driver.
# BISECTION_TOLERANCE_DAYS is what determines when we stop. The widest possible
# initial range (epoch to today, ~9700 days) needs ceil(log2(9700/31)) = 9 halvings
# to reach the tolerance, so this cap must comfortably exceed that.
MAX_BISECTION_STEPS = 40


def _is_positive_window(
    claim: Claim,
    serp_client,
    min_date: date,
    max_date: date,
    relevance_check: Callable[[Claim, list[SearchResult]], bool],
) -> bool:
    params = build_date_restricted_query(claim, min_date=min_date, max_date=max_date)
    results = serp_client.search_results(params)
    if len(results) < MIN_CORROBORATION:
        return False
    return relevance_check(claim, results)


def find_origin(
    claim: Claim,
    serp_client,
    today: date,
    relevance_check: Callable[[Claim, list[SearchResult]], bool],
) -> OriginCandidate:
    epoch = date(2000, 1, 1)

    # Step 1: bracket probe
    positive_max_date = None
    for years in BRACKET_OFFSETS_YEARS:
        candidate_max = today - timedelta(days=365 * years)
        if _is_positive_window(claim, serp_client, epoch, candidate_max, relevance_check):
            positive_max_date = candidate_max
            break

    if positive_max_date is None:
        # Even the widest bracket (8y) found no corroborated evidence at all.
        # Try the full range up to today as a last resort before giving up.
        if _is_positive_window(claim, serp_client, epoch, today, relevance_check):
            positive_max_date = today
        else:
            return OriginCandidate(date=None, confidence="unresolved", evidence_urls=[])

    # Step 2: bisect between epoch (negative, nothing before start of time) and
    # positive_max_date to narrow down the earliest positive window.
    low = epoch
    high = positive_max_date
    steps = 0
    while (high - low).days > BISECTION_TOLERANCE_DAYS and steps < MAX_BISECTION_STEPS:
        mid = low + (high - low) / 2
        if _is_positive_window(claim, serp_client, epoch, mid, relevance_check):
            high = mid
        else:
            low = mid
        steps += 1

    # Final evidence collection at the converged window for evidence_urls + confidence
    params = build_date_restricted_query(claim, min_date=epoch, max_date=high)
    results = serp_client.search_results(params)
    confidence = "high" if len(results) >= 3 else "medium"

    return OriginCandidate(
        date=high.isoformat(),
        confidence=confidence,
        evidence_urls=[r.link for r in results[:5]],
    )
