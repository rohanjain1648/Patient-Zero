from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from patientzero.cache import Cache
from patientzero.llm_client import FakeLLMClient
from patientzero.serp_client import SerpClient
from patientzero_api.app import create_app
from patientzero_api.store import ReportStore

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "serpapi"


class FixtureRoutingClient(SerpClient):
    def search(self, params):
        params = dict(params)
        params["fixture"] = "origin_positive" if "tbs" in params else "origin_negative"
        return super().search(params)


def _make_client(monkeypatch, llm_responses):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    serp_client = FixtureRoutingClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    llm_client = FakeLLMClient(responses=llm_responses)
    store = ReportStore(db_path=":memory:")
    app = create_app(serp_client=serp_client, llm_client=llm_client, store=store)
    return TestClient(app), store


def test_analyze_streams_progress_events_then_a_report_event(monkeypatch):
    client, _store = _make_client(
        monkeypatch,
        llm_responses=[
            '["App test claim text"]',
            '[{"result_index": 0, "label": "support", "quote": "q"}]',
            '[{"result_index": 0, "label": "unclear", "quote": "q"}]',
        ],
    )

    with client.stream("GET", "/api/analyze", params={"text": "Some claim about App test claim text."}) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: progress" in body
    assert "event: report" in body
    assert '"stage": "atomizing"' in body
    assert "App test claim text" in body


def test_analyze_persists_the_report_and_it_can_be_fetched_back(monkeypatch):
    client, store = _make_client(
        monkeypatch,
        llm_responses=[
            '["Fetchable claim text"]',
            '[{"result_index": 0, "label": "support", "quote": "q"}]',
            '[{"result_index": 0, "label": "unclear", "quote": "q"}]',
        ],
    )

    with client.stream("GET", "/api/analyze", params={"text": "About Fetchable claim text."}) as response:
        body = "".join(response.iter_text())

    import json

    report_line = next(line for line in body.split("\n") if line.startswith("data: ") and "report_id" in line)
    report_id = json.loads(report_line[len("data: "):])["report_id"]

    fetched = client.get(f"/api/reports/{report_id}")
    assert fetched.status_code == 200
    assert fetched.json()["claims"][0]["claim"]["text"] == "Fetchable claim text"


def test_get_reports_returns_404_for_unknown_report_id(monkeypatch):
    client, _store = _make_client(monkeypatch, llm_responses=[])
    response = client.get("/api/reports/no-such-id")
    assert response.status_code == 404
