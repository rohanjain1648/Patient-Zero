"""Top-level orchestration: raw text in, a ClaimReport per atomized claim out.
This is the single entry point the FastAPI wrapper calls.
"""
from datetime import date
from typing import Callable

from patientzero.atomizer import atomize
from patientzero.bisection import find_origin
from patientzero.echo import cluster_results
from patientzero.independence import score_independence
from patientzero.llm_client import LLMClient, LLMClientError
from patientzero.models import Claim, ClaimReport, SearchResult
from patientzero.query_planner import build_locale_query
from patientzero.serp_client import SerpApiError, SerpClient
from patientzero.stance import classify_stances

DEFAULT_LOCALES = ["en", "hi"]

ProgressCallback = Callable[[str, dict], None]


def _relevance_check(claim: Claim, results: list[SearchResult]) -> bool:
    """Deterministic token-overlap heuristic for bisection's per-probe
    relevance check. Deliberately makes zero LLM calls: a window returning
    results is not the same as a window returning evidence for THIS claim
    (spec sec 4.1), but bisection's LLM-call cost must not scale with the
    number of probes (spec sec 5's credit-budget discipline).
    """
    if len(results) < 2:
        return False
    claim_tokens = set(claim.text.lower().split())
    if not claim_tokens:
        return False
    matches = 0
    for r in results:
        result_tokens = set((r.title + " " + r.snippet).lower().split())
        overlap = len(claim_tokens & result_tokens) / len(claim_tokens)
        if overlap >= 0.4:
            matches += 1
    return matches >= 2


def run_pipeline(
    text: str,
    serp_client: SerpClient,
    llm: LLMClient,
    today: date,
    locales: list[str] = None,
    on_progress: ProgressCallback | None = None,
) -> list[ClaimReport]:
    if locales is None:
        locales = DEFAULT_LOCALES
    if on_progress is None:
        on_progress = lambda stage, detail: None  # noqa: E731

    on_progress("atomizing", {})
    try:
        claims = atomize(text, llm)
    except LLMClientError:
        # Per spec sec 6: an atomizer failure degrades to an empty list of
        # reports, the same as the "no claims extracted" case.
        on_progress("atomize_failed", {})
        return []

    on_progress("claims_extracted", {"count": len(claims)})

    reports = []

    for claim in claims:
        on_progress("claim_started", {"claim_index": claim.index, "text": claim.text})
        try:
            origin = find_origin(claim, serp_client, today, relevance_check=_relevance_check)
            on_progress(
                "origin_search_complete",
                {"claim_index": claim.index, "confidence": origin.confidence},
            )

            locale_asymmetry = {}
            all_results_for_independence = []
            for locale in locales:
                params = build_locale_query(claim, hl=locale)
                results = serp_client.search_results(params)
                all_results_for_independence.extend(results)
                stances = classify_stances(claim, results, llm)
                locale_asymmetry[locale] = stances
                on_progress(
                    "locale_search_complete",
                    {"claim_index": claim.index, "locale": locale, "result_count": len(results)},
                )

            clusters = cluster_results(all_results_for_independence)
            independence = score_independence(all_results_for_independence, clusters)

            primary_stances = locale_asymmetry.get(locales[0], [])

            reports.append(
                ClaimReport(
                    claim=claim,
                    origin=origin,
                    independence=independence,
                    stances=primary_stances,
                    locale_asymmetry=locale_asymmetry,
                )
            )
            on_progress("claim_complete", {"claim_index": claim.index})
        except (SerpApiError, LLMClientError) as exc:
            # Per spec sec 6: all stages degrade to partial results rather
            # than raising. One claim's failure must not abort the whole
            # batch of claims already produced by this run.
            on_progress("claim_failed", {"claim_index": claim.index, "error": str(exc)})
            continue

    on_progress("pipeline_complete", {"report_count": len(reports)})
    return reports
