"""Zero-key demo mode: the repo must run end to end for someone with no
SerpApi/Groq/OpenAI credentials at all, and must never present replayed bytes
as a live analysis.
"""
import json

import pytest
from fastapi.testclient import TestClient

from patientzero_api.app import create_app
from patientzero_api.demo import (
    DEFAULT_SESSION_PATH,
    DemoSessionUnavailable,
    load_session,
    replay_events,
)
from patientzero_api.store import ReportStore


def _events(raw: str) -> list[tuple[str, dict]]:
    parsed = []
    for block in raw.strip().split("\n\n"):
        lines = dict(
            line.split(": ", 1) for line in block.strip().splitlines() if ": " in line
        )
        if "event" in lines:
            parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


def test_the_shipped_demo_session_loads():
    session = load_session()
    assert session["events"]
    assert session["claim"]


def test_the_shipped_demo_session_came_from_a_real_run():
    """Demo mode replays recorded reality; a hand-written session would make
    the demo a lie. A real run always bills at least one SerpApi call.
    """
    session = load_session()
    assert session["serpapi_usage"]["live_calls"] > 0
    assert session["duration_seconds"] > 0


def test_the_shipped_demo_session_ends_in_a_report_with_propagation():
    session = load_session()
    event, data = session["events"][-1]["event"], session["events"][-1]["data"]
    assert event == "report"
    claim = data["claims"][0]
    assert claim["propagation"]["trend"]
    assert claim["propagation"]["mentions"]


def test_load_session_raises_for_a_missing_file(tmp_path):
    with pytest.raises(DemoSessionUnavailable):
        load_session(tmp_path / "nope.json")


def test_load_session_raises_for_malformed_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DemoSessionUnavailable):
        load_session(path)


def test_load_session_raises_for_a_session_with_no_events(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"events": []}), encoding="utf-8")
    with pytest.raises(DemoSessionUnavailable):
        load_session(path)


def test_replay_preserves_recorded_order_and_compresses_the_gaps():
    session = {
        "events": [
            {"event": "progress", "offset": 0, "data": {"stage": "a"}},
            {"event": "progress", "offset": 60, "data": {"stage": "b"}},
        ]
    }
    slept = []
    out = list(replay_events(session, sleep=slept.append))

    assert [e for e, _ in out] == ["progress", "progress"]
    assert [d["stage"] for _, d in out] == ["a", "b"]
    # A 60s recorded gap must not become a 60s demo gap.
    assert slept and max(slept) <= 0.6


def test_demo_only_app_streams_a_replay_without_any_clients(tmp_path):
    app = create_app(
        serp_client=None,
        llm_client=None,
        store=ReportStore(db_path=str(tmp_path / "r.sqlite3")),
        demo_only=True,
    )
    client = TestClient(app)

    response = client.get("/api/analyze", params={"text": "anything at all"})
    assert response.status_code == 200
    events = _events(response.text)

    # The stream must announce itself as a replay before anything else, so the
    # UI can never render recorded output as a live result.
    assert events[0][0] == "demo"
    assert [e for e, _ in events][-1] == "report"


def test_health_reports_demo_mode(tmp_path):
    store = ReportStore(db_path=str(tmp_path / "r.sqlite3"))
    demo_app = TestClient(create_app(None, None, store, demo_only=True))
    assert demo_app.get("/api/health").json()["mode"] == "demo"


def test_demo_query_param_works_even_on_a_live_app(tmp_path):
    """Lets the demo be recorded/played on a fully configured machine."""
    app = create_app(
        serp_client=object(),
        llm_client=object(),
        store=ReportStore(db_path=str(tmp_path / "r.sqlite3")),
    )
    response = TestClient(app).get("/api/analyze", params={"text": "x", "demo": "true"})
    assert response.status_code == 200
    assert _events(response.text)[0][0] == "demo"


def test_default_session_path_ships_inside_the_package():
    assert DEFAULT_SESSION_PATH.name == "demo_session.json"
    assert DEFAULT_SESSION_PATH.parent.name == "patientzero_api"
