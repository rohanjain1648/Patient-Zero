"""Batched LLM stance classification. Never returns a raw TRUE/FALSE verdict —
labels are support/refute/unrelated/unclear, each with the justifying quote
(spec sec 1, 4.4). Malformed LLM output degrades to "unclear" for every result
in that batch rather than raising (spec sec 6).
"""
import json

from patientzero.llm_client import LLMClient
from patientzero.models import Claim, SearchResult, StanceResult

VALID_LABELS = {"support", "refute", "unrelated", "unclear"}


def _build_prompt(claim: Claim, batch: list[tuple[int, SearchResult]]) -> str:
    items = "\n".join(
        f'{{"result_index": {idx}, "title": {json.dumps(r.title)}, "snippet": {json.dumps(r.snippet)}}}'
        for idx, r in batch
    )
    return (
        f"Claim: {claim.text}\n\n"
        f"For each search result below, decide whether it supports, refutes, is "
        f"unrelated to, or is unclear about the claim. Respond ONLY with a JSON "
        f"array of objects: "
        f'[{{"result_index": <int>, "label": "support"|"refute"|"unrelated"|"unclear", '
        f'"quote": "<short justifying quote from the snippet>"}}]\n\n'
        f"Results:\n{items}"
    )


def classify_stances(
    claim: Claim, results: list[SearchResult], llm: LLMClient, batch_size: int = 5
) -> list[StanceResult]:
    indexed = list(enumerate(results))
    all_stances: list[StanceResult] = []

    for start in range(0, len(indexed), batch_size):
        batch = indexed[start : start + batch_size]
        prompt = _build_prompt(claim, batch)
        raw_response = llm.complete(prompt)

        try:
            parsed = json.loads(raw_response)
            by_index = {item["result_index"]: item for item in parsed}
        except (json.JSONDecodeError, TypeError, KeyError):
            by_index = {}

        for idx, _result in batch:
            item = by_index.get(idx)
            if item is None or item.get("label") not in VALID_LABELS:
                all_stances.append(
                    StanceResult(claim_index=claim.index, result_index=idx, label="unclear", quote="")
                )
            else:
                all_stances.append(
                    StanceResult(
                        claim_index=claim.index,
                        result_index=idx,
                        label=item["label"],
                        quote=item.get("quote", ""),
                    )
                )

    return all_stances
