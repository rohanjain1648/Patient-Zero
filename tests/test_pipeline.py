from datetime import date
from pathlib import Path

from patientzero.cache import Cache
from patientzero.serp_client import SerpClient
from patientzero.llm_client import FakeLLMClient
from patientzero.pipeline import run_pipeline

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "serpapi"


def test_run_pipeline_produces_a_report_per_atomized_claim(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")

    class FixtureRoutingClient(SerpClient):
        def search(self, params):
            params = dict(params)
            params["fixture"] = "origin_positive" if "tbs" in params else "origin_negative"
            return super().search(params)

    serp_client = FixtureRoutingClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))

    llm = FakeLLMClient(
        responses=[
            '["Pipeline test claim text"]',              # atomizer
            '[{"result_index": 0, "label": "support", "quote": "q"}]',  # stance for en locale
            '[{"result_index": 0, "label": "unclear", "quote": "q"}]',  # stance for hi locale
        ]
    )

    reports = run_pipeline(
        "Some forwarded message containing the pipeline test claim.",
        serp_client,
        llm,
        today=date(2026, 9, 17),
        locales=["en", "hi"],
    )

    assert len(reports) == 1
    report = reports[0]
    assert report.claim.text == "Pipeline test claim text"
    assert report.origin.confidence in ("unresolved", "high", "medium")
    assert "en" in report.locale_asymmetry
    assert "hi" in report.locale_asymmetry


def test_run_pipeline_returns_empty_list_when_no_claims_extracted(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    serp_client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    llm = FakeLLMClient(responses=["[]"])  # atomizer finds nothing

    reports = run_pipeline("Just an opinion, no facts here.", serp_client, llm, today=date(2026, 9, 17))
    assert reports == []


def test_run_pipeline_degrades_to_empty_list_when_atomizer_fails(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    serp_client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    llm = FakeLLMClient(responses=[])  # exhausted immediately -> LLMClientError on first .complete() call (the atomizer's)

    reports = run_pipeline("Some text", serp_client, llm, today=date(2026, 9, 17))
    assert reports == []


def test_run_pipeline_emits_progress_events_for_every_stage(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")

    class FixtureRoutingClient(SerpClient):
        def search(self, params):
            params = dict(params)
            params["fixture"] = "origin_positive" if "tbs" in params else "origin_negative"
            return super().search(params)

    serp_client = FixtureRoutingClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    llm = FakeLLMClient(
        responses=[
            '["Pipeline test claim text"]',
            '[{"result_index": 0, "label": "support", "quote": "q"}]',
            '[{"result_index": 0, "label": "unclear", "quote": "q"}]',
        ]
    )

    events = []
    run_pipeline(
        "Some forwarded message containing the pipeline test claim.",
        serp_client,
        llm,
        today=date(2026, 9, 17),
        locales=["en", "hi"],
        on_progress=lambda stage, detail: events.append((stage, detail)),
    )

    stages = [stage for stage, _detail in events]
    assert stages[0] == "atomizing"
    assert "claims_extracted" in stages
    assert "claim_started" in stages
    assert "origin_search_complete" in stages
    assert stages.count("locale_search_complete") == 2  # en + hi
    assert "claim_complete" in stages
    assert stages[-1] == "pipeline_complete"


def test_run_pipeline_works_unchanged_when_on_progress_omitted(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    serp_client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    llm = FakeLLMClient(responses=["[]"])

    reports = run_pipeline("Just an opinion, no facts here.", serp_client, llm, today=date(2026, 9, 17))
    assert reports == []
