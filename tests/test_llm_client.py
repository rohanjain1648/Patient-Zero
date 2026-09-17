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
