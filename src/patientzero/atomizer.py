"""Splits raw user input (a forward, a headline, a URL's text) into individually
checkable factual assertions. Returns an empty list — not an error — when the
input contains no verifiable claims (spec sec 6), e.g. pure opinion.
"""
import json

from patientzero.llm_client import LLMClient
from patientzero.models import Claim


def _build_prompt(text: str) -> str:
    return (
        "Extract every individually checkable factual assertion from the "
        "text below. Ignore opinions, greetings, and non-factual statements. "
        "Respond ONLY with a JSON array of strings, one per claim. If there are "
        "no checkable factual claims, respond with an empty array: []\n\n"
        f"Text:\n{text}"
    )


def atomize(text: str, llm: LLMClient) -> list[Claim]:
    prompt = _build_prompt(text)
    raw_response = llm.complete(prompt)

    try:
        parsed = json.loads(raw_response)
        if not isinstance(parsed, list):
            return []
    except json.JSONDecodeError:
        return []

    return [Claim(text=str(item), index=i) for i, item in enumerate(parsed) if str(item).strip()]
