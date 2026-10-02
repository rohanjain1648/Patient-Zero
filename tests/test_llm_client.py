import os

import pytest

from patientzero.llm_client import FakeLLMClient, FallbackLLMClient, LLMClientError


def test_fake_llm_client_returns_queued_responses_in_order():
    client = FakeLLMClient(responses=["first", "second"])
    assert client.complete("prompt 1") == "first"
    assert client.complete("prompt 2") == "second"


def test_fake_llm_client_raises_when_exhausted():
    client = FakeLLMClient(responses=["only one"])
    client.complete("prompt 1")
    with pytest.raises(LLMClientError):
        client.complete("prompt 2")


def test_fake_llm_client_records_prompts_it_received():
    client = FakeLLMClient(responses=["a"])
    client.complete("what was asked")
    assert client.received_prompts == ["what was asked"]


def test_fallback_llm_client_uses_primary_when_it_succeeds():
    primary = FakeLLMClient(responses=["from primary"])
    fallback = FakeLLMClient(responses=["from fallback"])
    client = FallbackLLMClient(primary=primary, fallback=fallback)

    result = client.complete("prompt")

    assert result == "from primary"
    assert fallback.received_prompts == []


def test_fallback_llm_client_falls_back_when_primary_raises():
    primary = FakeLLMClient(responses=[])  # exhausted immediately -> raises LLMClientError
    fallback = FakeLLMClient(responses=["from fallback"])
    client = FallbackLLMClient(primary=primary, fallback=fallback)

    result = client.complete("prompt")

    assert result == "from fallback"
    assert fallback.received_prompts == ["prompt"]


def test_fallback_llm_client_propagates_error_when_both_providers_fail():
    primary = FakeLLMClient(responses=[])
    fallback = FakeLLMClient(responses=[])
    client = FallbackLLMClient(primary=primary, fallback=fallback)

    with pytest.raises(LLMClientError):
        client.complete("prompt")


class _RecordingProvider:
    """Stands in for the groq / openai SDK client object."""

    def __init__(self):
        self.kwargs = None
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = type("M", (), {"content": "ok"})
        return type("R", (), {"choices": [type("C", (), {"message": message})]})


@pytest.mark.parametrize("client_name", ["GroqLLMClient", "OpenAILLMClient"])
def test_real_clients_decode_deterministically_by_default(client_name, monkeypatch):
    """Temperature must default to 0: a reworded claim changes the SerpApi
    query, which changes the cache key, which re-bills an identical input.
    """
    import patientzero.llm_client as mod

    provider = _RecordingProvider()
    client = object.__new__(getattr(mod, client_name))
    client._client = provider
    client._model = "m"
    client._temperature = mod.DEFAULT_TEMPERATURE

    assert client.complete("prompt") == "ok"
    assert provider.kwargs["temperature"] == 0.0


def test_default_temperature_is_zero():
    from patientzero.llm_client import DEFAULT_TEMPERATURE

    assert DEFAULT_TEMPERATURE == 0.0


def test_groq_model_is_overridable_by_environment(monkeypatch):
    """A decommissioned model name must be fixable without a code change."""
    import patientzero.llm_client as mod

    monkeypatch.setenv("GROQ_MODEL", "some/other-model")
    client = object.__new__(mod.GroqLLMClient)
    client._model = None or os.environ.get("GROQ_MODEL") or mod.DEFAULT_GROQ_MODEL
    assert client._model == "some/other-model"


def test_model_defaults_are_not_the_decommissioned_llama_name():
    from patientzero.llm_client import DEFAULT_GROQ_MODEL, DEFAULT_OPENAI_MODEL

    assert DEFAULT_GROQ_MODEL != "llama-3.3-70b-versatile"
    assert DEFAULT_OPENAI_MODEL
