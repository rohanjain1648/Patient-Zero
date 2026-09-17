import pytest

from patientzero.llm_client import FakeLLMClient, LLMClientError


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
