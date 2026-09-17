"""Builds patientzero-core's I/O clients from environment variables. This is
the one place in the API layer that reads SERPAPI_API_KEY / GROQ_API_KEY /
OPENAI_API_KEY, so app.py and its tests never touch os.environ directly.
"""
import os

from patientzero.cache import Cache
from patientzero.llm_client import FallbackLLMClient, GroqLLMClient, LLMClient, OpenAILLMClient
from patientzero.serp_client import SerpClient

# Spec sec 5's credit budget: ~11-12 SerpApi calls per full analysis
# (3 bracket probes + up to several bisection steps + 3 locale/corroboration
# queries). This default gives headroom above that estimate while still
# enforcing the "hard per-run call cap" the spec marks mandatory — it was
# previously implemented as an opt-in SerpClient parameter but never given
# a default value anywhere in the running system.
DEFAULT_MAX_CALLS_PER_RUN = 20


def build_serp_client(
    cache_db_path: str,
    mock_dir: str | None = None,
    max_calls: int = DEFAULT_MAX_CALLS_PER_RUN,
) -> SerpClient:
    cache = Cache(db_path=cache_db_path)
    api_key = os.environ.get("SERPAPI_API_KEY")
    return SerpClient(api_key=api_key, cache=cache, mock_dir=mock_dir, max_calls=max_calls)


def build_llm_client() -> LLMClient:
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set; the API layer requires a real Groq "
            "API key for its primary LLM client"
        )
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set; the API layer requires a real OpenAI "
            "API key for its fallback LLM client"
        )
    return FallbackLLMClient(
        primary=GroqLLMClient(api_key=groq_key),
        fallback=OpenAILLMClient(api_key=openai_key),
    )
