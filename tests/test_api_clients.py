import pytest

from patientzero.serp_client import SerpClient
from patientzero_api.clients import DEFAULT_MAX_CALLS_PER_RUN, build_llm_client, build_serp_client


def test_build_serp_client_wires_default_call_cap(tmp_path):
    client = build_serp_client(cache_db_path=str(tmp_path / "cache.sqlite3"), mock_dir="/tmp")
    assert isinstance(client, SerpClient)
    assert client.max_calls == DEFAULT_MAX_CALLS_PER_RUN


def test_build_serp_client_accepts_an_explicit_max_calls_override(tmp_path):
    client = build_serp_client(cache_db_path=str(tmp_path / "cache.sqlite3"), max_calls=5)
    assert client.max_calls == 5


def test_build_serp_client_reads_api_key_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-123")
    client = build_serp_client(cache_db_path=str(tmp_path / "cache.sqlite3"))
    assert client.api_key == "test-key-123"


def test_build_llm_client_raises_a_clear_error_when_groq_key_is_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_llm_client()


def test_build_llm_client_uses_groq_alone_when_openai_key_is_missing(monkeypatch):
    """The OpenAI fallback guards against a Groq outage; it is not required to
    run the system, so a Groq-only configuration must work.
    """
    from patientzero.llm_client import GroqLLMClient

    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = build_llm_client()

    assert isinstance(client, GroqLLMClient)


def test_build_llm_client_wraps_both_providers_when_both_keys_are_present(monkeypatch):
    from patientzero.llm_client import FallbackLLMClient

    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    assert isinstance(build_llm_client(), FallbackLLMClient)
