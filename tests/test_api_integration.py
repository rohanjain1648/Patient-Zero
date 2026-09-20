"""Proves the API layer, not just the pipeline layer, runs end to end with
SERPAPI_MOCK=1 and no API key — the HTTP-boundary equivalent of
patientzero-core's own golden-claim regression test (spec sec 7). Uses
patientzero.serp_client.SerpClient directly (not build_serp_client, which
would need real GROQ_API_KEY/OPENAI_API_KEY-backed LLM clients to be meaningful) —
Task 5's factories are exercised on their own in test_api_clients.py; this
test's job is proving composition of app.py + store.py + pipeline.py.
"""
from pathlib import Path

from fastapi.testclient import TestClient

from patientzero.cache import Cache
from patientzero.llm_client import FakeLLMClient
from patientzero.serp_client import SerpClient
from patientzero_api.app import create_app
from patientzero_api.store import ReportStore

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "serpapi"


class FixtureRoutingSerpClient(SerpClient):
    def search(self, params):
        params = dict(params)
        params["fixture"] = "origin_negative"
        return super().search(params)


def test_full_stack_runs_with_serpapi_mock_and_zero_network(monkeypatch, tmp_path):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    serp_client = FixtureRoutingSerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR), max_calls=20)
    llm_client = FakeLLMClient(responses=["[]"])  # atomizer finds no checkable claims
    store = ReportStore(db_path=str(tmp_path / "reports.sqlite3"))

    app = create_app(serp_client=serp_client, llm_client=llm_client, store=store)
    client = TestClient(app)

    with client.stream("GET", "/api/analyze", params={"text": "I really love sunny weather!"}) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: report" in body
    assert '"claims": []' in body
