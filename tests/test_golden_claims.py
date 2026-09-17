import json
from datetime import date
from pathlib import Path

from patientzero.cache import Cache
from patientzero.serp_client import SerpClient
from patientzero.llm_client import FakeLLMClient
from patientzero.pipeline import run_pipeline

FIXTURE_DIR = Path(__file__).parent / "fixtures"
GOLDEN_MANIFEST = FIXTURE_DIR / "golden_claims.json"


def test_no_clear_origin_golden_case_reports_unresolved(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cases = json.loads(GOLDEN_MANIFEST.read_text())
    case = next(c for c in cases if c["name"] == "no_clear_origin_case")

    class EmptyClient(SerpClient):
        def search(self, params):
            params = dict(params)
            params["fixture"] = "origin_negative"
            return super().search(params)

    cache = Cache(db_path=":memory:")
    serp_client = EmptyClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR / "serpapi"))
    llm = FakeLLMClient(responses=['["Extracted claim text"]', "[]", "[]"])

    reports = run_pipeline(case["input_text"], serp_client, llm, today=date(2026, 9, 17))

    assert len(reports) == 1
    assert reports[0].origin.confidence == case["expected_origin_confidence"]
