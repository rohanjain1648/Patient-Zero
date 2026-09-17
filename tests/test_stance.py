from patientzero.models import Claim, SearchResult
from patientzero.llm_client import FakeLLMClient
from patientzero.stance import classify_stances


def _result(i):
    return SearchResult(title=f"title {i}", link=f"https://x.com/{i}", snippet=f"snippet {i}", domain="x.com", date=None)


def test_classify_stances_parses_json_response_into_stance_results():
    claim = Claim(text="Example claim", index=0)
    results = [_result(0), _result(1)]
    fake_response = (
        '[{"result_index": 0, "label": "support", "quote": "snippet 0 supports it"},'
        ' {"result_index": 1, "label": "refute", "quote": "snippet 1 contradicts it"}]'
    )
    llm = FakeLLMClient(responses=[fake_response])
    stances = classify_stances(claim, results, llm, batch_size=5)
    assert len(stances) == 2
    assert stances[0].label == "support"
    assert stances[0].claim_index == 0
    assert stances[1].label == "refute"


def test_classify_stances_batches_large_result_sets():
    claim = Claim(text="Example claim", index=0)
    results = [_result(i) for i in range(7)]
    batch1 = '[{"result_index": 0, "label": "support", "quote": "q0"}, {"result_index": 1, "label": "unrelated", "quote": "q1"}, {"result_index": 2, "label": "support", "quote": "q2"}, {"result_index": 3, "label": "support", "quote": "q3"}, {"result_index": 4, "label": "support", "quote": "q4"}]'
    batch2 = '[{"result_index": 5, "label": "unclear", "quote": "q5"}, {"result_index": 6, "label": "support", "quote": "q6"}]'
    llm = FakeLLMClient(responses=[batch1, batch2])
    stances = classify_stances(claim, results, llm, batch_size=5)
    assert len(stances) == 7
    assert llm.received_prompts.__len__() == 2


def test_classify_stances_marks_unparseable_response_as_unclear():
    claim = Claim(text="Example claim", index=0)
    results = [_result(0)]
    llm = FakeLLMClient(responses=["not valid json at all"])
    stances = classify_stances(claim, results, llm, batch_size=5)
    assert len(stances) == 1
    assert stances[0].label == "unclear"
