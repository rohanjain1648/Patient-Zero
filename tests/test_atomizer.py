from patientzero.llm_client import FakeLLMClient
from patientzero.atomizer import atomize


def test_atomize_parses_multiple_claims_from_json_response():
    llm = FakeLLMClient(responses=['["Claim one text", "Claim two text"]'])
    claims = atomize("Some forwarded message with two claims in it.", llm)
    assert len(claims) == 2
    assert claims[0].text == "Claim one text"
    assert claims[0].index == 0
    assert claims[1].index == 1


def test_atomize_returns_empty_list_for_pure_opinion_with_no_claims():
    llm = FakeLLMClient(responses=["[]"])
    claims = atomize("I really love sunny weather!", llm)
    assert claims == []


def test_atomize_returns_empty_list_on_unparseable_response_rather_than_raising():
    llm = FakeLLMClient(responses=["not json"])
    claims = atomize("Some input text", llm)
    assert claims == []
