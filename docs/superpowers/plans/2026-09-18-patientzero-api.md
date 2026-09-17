# Patient Zero API Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a thin FastAPI HTTP wrapper around the already-shipped `patientzero-core` pipeline, exposing one SSE endpoint that streams live progress while `run_pipeline` executes and a second endpoint to retrieve a previously completed report, backed by a second SQLite table for saved reports.

**Architecture:** `patientzero_api` is a new subpackage living alongside `patientzero` in the same `src/` tree and the same `patientzero-core` distribution (FastAPI/uvicorn are added as an optional `[api]` extra, so a judge who only wants the importable engine is not forced to install a web framework). The API layer does not reimplement any pipeline logic — it constructs `SerpClient`/`LLMClient` from environment variables, calls `patientzero.pipeline.run_pipeline` with a progress callback, serializes the resulting `ClaimReport` dataclasses to JSON, and persists them in a `ReportStore` (a second SQLite table, separate from the core package's response cache). SSE streaming works by running `run_pipeline` in a background thread that pushes `(event, data)` tuples onto a `queue.Queue`, while the request handler's generator drains that queue and yields SSE-formatted lines.

**Tech Stack:** Python ≥3.10 (unchanged), `fastapi`, `uvicorn[standard]` (new, optional `[api]` extra), `httpx` (new, dev-only, required by FastAPI's `TestClient`). No Next.js/frontend work — that is a separate follow-on plan per the spec's own schedule.

**Spec:** [docs/superpowers/specs/2026-09-17-patient-zero-design.md](../specs/2026-09-17-patient-zero-design.md) — this plan implements spec §3's "FastAPI ... SSE — live progress stream" architecture box and the "SQLite: response cache + saved reports" persistence line, plus carries forward spec §5's mandatory per-run call cap (added to `patientzero-core` already, but never wired to a default value anywhere — this plan wires it) and spec §6's degrade-to-partial-results discipline at the HTTP boundary.

## Global Constraints

- The FastAPI app is a thin HTTP wrapper over `patientzero-core`; it must not reimplement atomization, bisection, echo detection, independence scoring, or stance classification — it only calls `patientzero.pipeline.run_pipeline` (spec §3).
- SSE streaming exists specifically to show live progress as queries fan out and the report assembles (spec §3) — every major stage `run_pipeline` already passes through (atomize, per-claim origin search, per-locale search, claim complete) must emit at least one progress event through the new `on_progress` callback.
- SQLite is the only persistence mechanism — no Postgres, no queue, no microservices (spec §9). Saved reports live in their own SQLite file/table, separate from the core package's content-addressed response cache.
- `SERPAPI_MOCK=1` must work end to end through the API layer exactly as it does in `patientzero-core` directly, so the API's own tests run with zero network access and zero API key (spec §5, §7).
- The hard per-run SerpApi call cap (`SerpClient.max_calls`, already implemented in `patientzero-core`) must be given a real default value when the API layer constructs its `SerpClient` — this was flagged as a residual gap (opt-in but never wired) after the core plan's final review.
- No verdict language ("true"/"false") anywhere in code, comments, HTTP response field names, or SSE event names — reuse the existing "support"/"refute"/"unrelated"/"unclear" and "candidate origin"/confidence vocabulary unchanged (spec §1, §4.1).
- A judge who only wants the importable engine (`pip install patientzero-core`) must not be forced to install `fastapi`/`uvicorn` — those are an optional extra.

---

## File Structure

```
src/
├── patientzero/                    # existing, unchanged except pipeline.py (Task 1)
│   └── pipeline.py                 # MODIFY: add optional on_progress callback
└── patientzero_api/                # NEW subpackage, same distribution
    ├── __init__.py
    ├── serialization.py            # ClaimReport <-> plain dict (Task 2)
    ├── store.py                    # SQLite-backed saved-report store (Task 3)
    ├── sse.py                      # SSE wire-format helper (Task 4)
    ├── clients.py                  # env-based SerpClient/LLMClient factories (Task 5)
    └── app.py                      # FastAPI app: /api/analyze, /api/reports/{id} (Task 6)
tests/
├── test_pipeline.py                # MODIFY: add progress-callback test (Task 1)
├── test_api_serialization.py       # NEW (Task 2)
├── test_api_store.py               # NEW (Task 3)
├── test_api_sse.py                 # NEW (Task 4)
├── test_api_clients.py             # NEW (Task 5)
├── test_api_app.py                 # NEW (Task 6)
└── test_api_integration.py         # NEW (Task 7)
pyproject.toml                      # MODIFY: add [api] extra, add httpx to dev extra (Tasks 6, 7)
```

---

### Task 1: Progress-callback hook in `run_pipeline`

**Files:**
- Modify: `src/patientzero/pipeline.py`
- Modify (add a test): `tests/test_pipeline.py`

**Interfaces:**
- Consumes: nothing new — same imports `run_pipeline` already has.
- Produces: `run_pipeline(text, serp_client, llm, today, locales=None, on_progress=None)` — `on_progress` is `Callable[[str, dict], None] | None`, called with a stage name and a detail dict at each of: `"atomizing"`, `"atomize_failed"`, `"claims_extracted"`, `"claim_started"`, `"origin_search_complete"`, `"locale_search_complete"`, `"claim_failed"`, `"claim_complete"`, `"pipeline_complete"`. Existing callers that don't pass `on_progress` are unaffected (default `None` becomes a no-op internally). Task 6 (`app.py`) supplies a real callback that pushes onto a queue.

- [ ] **Step 1: Write the failing test**

Add this test to the end of `tests/test_pipeline.py` (imports already present in that file cover everything needed):

```python
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
```

- [ ] **Step 2: Run tests to verify the first new test fails**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: `test_run_pipeline_emits_progress_events_for_every_stage` FAILS with `TypeError: run_pipeline() got an unexpected keyword argument 'on_progress'`. The second new test passes already (it doesn't use the new parameter) — that's fine, it's there to lock in backward compatibility once Step 3 lands.

- [ ] **Step 3: Modify `pipeline.py` to add the callback**

Replace the full contents of `src/patientzero/pipeline.py` with:

```python
"""Top-level orchestration: raw text in, a ClaimReport per atomized claim out.
This is the single entry point the FastAPI wrapper calls.
"""
from datetime import date
from typing import Callable

from patientzero.atomizer import atomize
from patientzero.bisection import find_origin
from patientzero.echo import cluster_results
from patientzero.independence import score_independence
from patientzero.llm_client import LLMClient, LLMClientError
from patientzero.models import Claim, ClaimReport, SearchResult
from patientzero.query_planner import build_locale_query
from patientzero.serp_client import SerpApiError, SerpClient
from patientzero.stance import classify_stances

DEFAULT_LOCALES = ["en", "hi"]

ProgressCallback = Callable[[str, dict], None]


def _relevance_check(claim: Claim, results: list[SearchResult]) -> bool:
    """Deterministic token-overlap heuristic for bisection's per-probe
    relevance check. Deliberately makes zero LLM calls: a window returning
    results is not the same as a window returning evidence for THIS claim
    (spec sec 4.1), but bisection's LLM-call cost must not scale with the
    number of probes (spec sec 5's credit-budget discipline).
    """
    if len(results) < 2:
        return False
    claim_tokens = set(claim.text.lower().split())
    if not claim_tokens:
        return False
    matches = 0
    for r in results:
        result_tokens = set((r.title + " " + r.snippet).lower().split())
        overlap = len(claim_tokens & result_tokens) / len(claim_tokens)
        if overlap >= 0.4:
            matches += 1
    return matches >= 2


def run_pipeline(
    text: str,
    serp_client: SerpClient,
    llm: LLMClient,
    today: date,
    locales: list[str] = None,
    on_progress: ProgressCallback | None = None,
) -> list[ClaimReport]:
    if locales is None:
        locales = DEFAULT_LOCALES
    if on_progress is None:
        on_progress = lambda stage, detail: None  # noqa: E731

    on_progress("atomizing", {})
    try:
        claims = atomize(text, llm)
    except LLMClientError:
        # Per spec sec 6: an atomizer failure degrades to an empty list of
        # reports, the same as the "no claims extracted" case.
        on_progress("atomize_failed", {})
        return []

    on_progress("claims_extracted", {"count": len(claims)})

    reports = []

    for claim in claims:
        on_progress("claim_started", {"claim_index": claim.index, "text": claim.text})
        try:
            origin = find_origin(claim, serp_client, today, relevance_check=_relevance_check)
            on_progress(
                "origin_search_complete",
                {"claim_index": claim.index, "confidence": origin.confidence},
            )

            locale_asymmetry = {}
            all_results_for_independence = []
            for locale in locales:
                params = build_locale_query(claim, hl=locale)
                results = serp_client.search_results(params)
                all_results_for_independence.extend(results)
                stances = classify_stances(claim, results, llm)
                locale_asymmetry[locale] = stances
                on_progress(
                    "locale_search_complete",
                    {"claim_index": claim.index, "locale": locale, "result_count": len(results)},
                )

            clusters = cluster_results(all_results_for_independence)
            independence = score_independence(all_results_for_independence, clusters)

            primary_stances = locale_asymmetry.get(locales[0], [])

            reports.append(
                ClaimReport(
                    claim=claim,
                    origin=origin,
                    independence=independence,
                    stances=primary_stances,
                    locale_asymmetry=locale_asymmetry,
                )
            )
            on_progress("claim_complete", {"claim_index": claim.index})
        except (SerpApiError, LLMClientError) as exc:
            # Per spec sec 6: all stages degrade to partial results rather
            # than raising. One claim's failure must not abort the whole
            # batch of claims already produced by this run.
            on_progress("claim_failed", {"claim_index": claim.index, "error": str(exc)})
            continue

    on_progress("pipeline_complete", {"report_count": len(reports)})
    return reports
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS (5 passed — 3 pre-existing + 2 new)

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `python -m pytest -q`
Expected: all 48 tests pass (46 pre-existing + 2 new), output pristine.

- [ ] **Step 6: Commit**

```bash
git add src/patientzero/pipeline.py tests/test_pipeline.py
git commit -m "feat: add optional progress-callback hook to run_pipeline

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `ClaimReport` serialization

**Files:**
- Create: `src/patientzero_api/__init__.py`
- Create: `src/patientzero_api/serialization.py`
- Test: `tests/test_api_serialization.py`

**Interfaces:**
- Consumes: `Claim`, `OriginCandidate`, `IndependenceScore`, `StanceResult`, `ClaimReport` from `patientzero.models` (all frozen dataclasses, unchanged).
- Produces: `serialize_claim_report(report: ClaimReport) -> dict` and `claim_report_from_dict(data: dict) -> ClaimReport`. Task 3 (`store.py`) and Task 6 (`app.py`) both call these two functions directly — no other module builds its own dict shape for a `ClaimReport`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_serialization.py
from patientzero.models import Claim, ClaimReport, IndependenceScore, OriginCandidate, StanceResult
from patientzero_api.serialization import claim_report_from_dict, serialize_claim_report


def _sample_report() -> ClaimReport:
    claim = Claim(text="X causes Y", index=0)
    origin = OriginCandidate(date="2019-03-01", confidence="medium", evidence_urls=["https://a.com"])
    independence = IndependenceScore(
        distinct_clusters=3, distinct_domains=12, temporal_spread_days=400, score=0.6
    )
    en_stance = StanceResult(claim_index=0, result_index=0, label="support", quote="X does cause Y")
    hi_stance = StanceResult(claim_index=0, result_index=0, label="unclear", quote="")
    return ClaimReport(
        claim=claim,
        origin=origin,
        independence=independence,
        stances=[en_stance],
        locale_asymmetry={"en": [en_stance], "hi": [hi_stance]},
    )


def test_serialize_claim_report_produces_plain_json_safe_dict():
    data = serialize_claim_report(_sample_report())
    assert data["claim"] == {"text": "X causes Y", "index": 0}
    assert data["origin"]["confidence"] == "medium"
    assert data["independence"]["score"] == 0.6
    assert data["stances"][0]["label"] == "support"
    assert data["locale_asymmetry"]["hi"][0]["label"] == "unclear"
    # Every leaf value must be JSON-primitive (str/int/float/bool/None/list/dict) —
    # this is what makes the dict directly usable as an HTTP response body and
    # a SQLite TEXT column via json.dumps with no custom encoder.
    import json

    json.dumps(data)


def test_claim_report_from_dict_round_trips_serialize_claim_report():
    original = _sample_report()
    round_tripped = claim_report_from_dict(serialize_claim_report(original))
    assert round_tripped == original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_serialization.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero_api'`

- [ ] **Step 3: Create the package `__init__.py`**

```python
# src/patientzero_api/__init__.py
```

(Empty — this package has no top-level re-exports; every consumer imports the specific submodule it needs, matching the convention already established by `patientzero`.)

- [ ] **Step 4: Write `serialization.py`**

```python
# src/patientzero_api/serialization.py
"""Converts patientzero.models.ClaimReport (and its nested frozen dataclasses)
to and from plain JSON-safe dicts. Every HTTP response body and every row the
ReportStore (Task 3) writes to SQLite goes through these two functions — no
other module builds its own shape for a ClaimReport.
"""
from dataclasses import asdict

from patientzero.models import Claim, ClaimReport, IndependenceScore, OriginCandidate, StanceResult


def serialize_claim_report(report: ClaimReport) -> dict:
    return asdict(report)


def claim_report_from_dict(data: dict) -> ClaimReport:
    return ClaimReport(
        claim=Claim(**data["claim"]),
        origin=OriginCandidate(**data["origin"]),
        independence=IndependenceScore(**data["independence"]),
        stances=[StanceResult(**s) for s in data["stances"]],
        locale_asymmetry={
            locale: [StanceResult(**s) for s in stances]
            for locale, stances in data["locale_asymmetry"].items()
        },
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_api_serialization.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/patientzero_api/__init__.py src/patientzero_api/serialization.py tests/test_api_serialization.py
git commit -m "feat: add ClaimReport <-> dict serialization for the API layer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Saved-report SQLite store

**Files:**
- Create: `src/patientzero_api/store.py`
- Test: `tests/test_api_store.py`

**Interfaces:**
- Consumes: `serialize_claim_report`, `claim_report_from_dict` from `patientzero_api.serialization` (Task 2); `ClaimReport` from `patientzero.models`.
- Produces: `ReportStore(db_path: str)` with `save(report_id: str, claims: list[ClaimReport]) -> None` and `load(report_id: str) -> list[ClaimReport] | None`. Task 6 (`app.py`) calls both directly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_store.py
from patientzero.models import Claim, ClaimReport, IndependenceScore, OriginCandidate, StanceResult
from patientzero_api.store import ReportStore


def _sample_reports() -> list[ClaimReport]:
    claim = Claim(text="Store test claim", index=0)
    origin = OriginCandidate(date=None, confidence="unresolved", evidence_urls=[])
    independence = IndependenceScore(
        distinct_clusters=0, distinct_domains=0, temporal_spread_days=0, score=0.0
    )
    stance = StanceResult(claim_index=0, result_index=0, label="unrelated", quote="")
    return [
        ClaimReport(
            claim=claim,
            origin=origin,
            independence=independence,
            stances=[stance],
            locale_asymmetry={"en": [stance]},
        )
    ]


def test_load_missing_report_returns_none():
    store = ReportStore(db_path=":memory:")
    assert store.load("no-such-id") is None


def test_save_then_load_roundtrips():
    store = ReportStore(db_path=":memory:")
    reports = _sample_reports()
    store.save("report-1", reports)
    loaded = store.load("report-1")
    assert loaded == reports


def test_store_persists_to_file(tmp_path):
    db_path = str(tmp_path / "reports.sqlite3")
    reports = _sample_reports()

    store1 = ReportStore(db_path=db_path)
    store1.save("report-1", reports)
    del store1

    store2 = ReportStore(db_path=db_path)
    assert store2.load("report-1") == reports


def test_corrupted_stored_body_is_treated_as_a_miss_not_a_crash(tmp_path):
    db_path = str(tmp_path / "reports.sqlite3")
    store = ReportStore(db_path=db_path)
    store._conn.execute(
        "INSERT INTO reports (report_id, claims_json, created_at) VALUES (?, ?, ?)",
        ("corrupt-id", "not valid json {{{", "2026-09-18T00:00:00+00:00"),
    )
    store._conn.commit()
    assert store.load("corrupt-id") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero_api.store'`

- [ ] **Step 3: Write `store.py`**

```python
# src/patientzero_api/store.py
"""SQLite-backed store for completed analysis reports, separate from
patientzero-core's content-addressed SerpApi response cache (spec sec 3's
"SQLite: response cache + saved reports" line names these as two distinct
concerns). A corrupted stored row degrades to a miss rather than crashing
the request, matching the same lesson already applied to Cache.get in
patientzero-core.
"""
import json
import sqlite3
from datetime import datetime, timezone

from patientzero.models import ClaimReport
from patientzero_api.serialization import claim_report_from_dict, serialize_claim_report


class ReportStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS reports ("
            "report_id TEXT PRIMARY KEY, claims_json TEXT NOT NULL, created_at TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    def save(self, report_id: str, claims: list[ClaimReport]) -> None:
        body = json.dumps([serialize_claim_report(c) for c in claims])
        created_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO reports (report_id, claims_json, created_at) VALUES (?, ?, ?)",
            (report_id, body, created_at),
        )
        self._conn.commit()

    def load(self, report_id: str) -> list[ClaimReport] | None:
        row = self._conn.execute(
            "SELECT claims_json FROM reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            parsed = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None
        return [claim_report_from_dict(d) for d in parsed]

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_store.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero_api/store.py tests/test_api_store.py
git commit -m "feat: add SQLite-backed saved-report store

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: SSE wire-format helper

**Files:**
- Create: `src/patientzero_api/sse.py`
- Test: `tests/test_api_sse.py`

**Interfaces:**
- Consumes: nothing (stdlib `json` only).
- Produces: `format_sse_event(event: str, data: dict) -> str`. Task 6 (`app.py`) calls this for every event pushed onto the progress queue.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_sse.py
import json

from patientzero_api.sse import format_sse_event


def test_format_sse_event_produces_valid_sse_wire_format():
    formatted = format_sse_event("progress", {"stage": "atomizing"})
    lines = formatted.split("\n")
    assert lines[0] == "event: progress"
    assert lines[1].startswith("data: ")
    assert json.loads(lines[1][len("data: "):]) == {"stage": "atomizing"}
    assert formatted.endswith("\n\n")


def test_format_sse_event_handles_nested_and_unicode_data():
    formatted = format_sse_event("report", {"claims": [{"text": "दावा"}]})
    data_line = formatted.split("\n")[1]
    payload = json.loads(data_line[len("data: "):])
    assert payload["claims"][0]["text"] == "दावा"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_sse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero_api.sse'`

- [ ] **Step 3: Write `sse.py`**

```python
# src/patientzero_api/sse.py
"""Formats (event, data) pairs into the Server-Sent Events wire format:
"event: <name>\\ndata: <json>\\n\\n" — the blank line after the data line is
what tells the browser's EventSource one event has ended.
"""
import json


def format_sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_sse.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero_api/sse.py tests/test_api_sse.py
git commit -m "feat: add SSE wire-format helper

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Environment-based client factories

**Files:**
- Create: `src/patientzero_api/clients.py`
- Test: `tests/test_api_clients.py`

**Interfaces:**
- Consumes: `Cache` from `patientzero.cache`; `SerpClient` from `patientzero.serp_client`; `FallbackLLMClient`, `GroqLLMClient`, `OpenAILLMClient`, `LLMClient` from `patientzero.llm_client` (these four already exist — `patientzero-core`'s LLM layer was switched from Anthropic to a Groq-primary/OpenAI-fallback pair in a prior plan, `docs/superpowers/plans/2026-09-18-patientzero-llm-providers.md`).
- Produces: `build_serp_client(cache_db_path: str, mock_dir: str | None = None, max_calls: int = DEFAULT_MAX_CALLS_PER_RUN) -> SerpClient` and `build_llm_client() -> LLMClient` (raises `RuntimeError` if either `GROQ_API_KEY` or `OPENAI_API_KEY` is unset — the API layer requires both real keys, one per provider, since the fallback is only meaningful with both present; tests inject `FakeLLMClient` directly instead of calling this factory). Neither `app.py` (Task 6) nor the integration test (Task 7) calls either factory — `create_app` takes already-constructed clients as parameters (see Task 6's own Interfaces) — so these two functions exist for the not-yet-written `main.py`/uvicorn entry point named in "After This Plan," and are exercised only by this task's own tests within this plan.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_clients.py
import pytest

from patientzero.serp_client import SerpClient
from patientzero_api.clients import DEFAULT_MAX_CALLS_PER_RUN, build_llm_client, build_serp_client


def test_build_serp_client_wires_default_call_cap(tmp_path):
    client = build_serp_client(cache_db_path=str(tmp_path / "cache.sqlite3"), mock_dir="/tmp")
    assert isinstance(client, SerpClient)
    assert client.max_calls == DEFAULT_MAX_CALLS_PER_RUN


def test_build_serp_client_accepts_an_explicit_max_calls_override(tmp_path):
    client = build_serp_client(cache_db_path=str(tmp_path / "cache.sqlite3"), max_calls=5)
    assert client.max_calls == 5


def test_build_serp_client_reads_api_key_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key-123")
    client = build_serp_client(cache_db_path=str(tmp_path / "cache.sqlite3"))
    assert client.api_key == "test-key-123"


def test_build_llm_client_raises_a_clear_error_when_groq_key_is_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_llm_client()


def test_build_llm_client_raises_a_clear_error_when_openai_key_is_missing(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_llm_client()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_clients.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero_api.clients'`

- [ ] **Step 3: Write `clients.py`**

```python
# src/patientzero_api/clients.py
"""Builds patientzero-core's I/O clients from environment variables. This is
the one place in the API layer that reads SERPAPI_API_KEY / GROQ_API_KEY /
OPENAI_API_KEY, so app.py and its tests never touch os.environ directly.
"""
import os

from patientzero.cache import Cache
from patientzero.llm_client import FallbackLLMClient, GroqLLMClient, LLMClient, OpenAILLMClient
from patientzero.serp_client import SerpClient

# Spec sec 5's credit budget: ~11-12 SerpApi calls per full analysis
# (3 bracket probes + up to several bisection steps + 3 locale/corroboration
# queries). This default gives headroom above that estimate while still
# enforcing the "hard per-run call cap" the spec marks mandatory — it was
# previously implemented as an opt-in SerpClient parameter but never given
# a default value anywhere in the running system.
DEFAULT_MAX_CALLS_PER_RUN = 20


def build_serp_client(
    cache_db_path: str,
    mock_dir: str | None = None,
    max_calls: int = DEFAULT_MAX_CALLS_PER_RUN,
) -> SerpClient:
    cache = Cache(db_path=cache_db_path)
    api_key = os.environ.get("SERPAPI_API_KEY")
    return SerpClient(api_key=api_key, cache=cache, mock_dir=mock_dir, max_calls=max_calls)


def build_llm_client() -> LLMClient:
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set; the API layer requires a real Groq "
            "API key for its primary LLM client"
        )
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set; the API layer requires a real OpenAI "
            "API key for its fallback LLM client"
        )
    return FallbackLLMClient(
        primary=GroqLLMClient(api_key=groq_key),
        fallback=OpenAILLMClient(api_key=openai_key),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_clients.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero_api/clients.py tests/test_api_clients.py
git commit -m "feat: add env-based SerpClient/LLMClient factories with a wired call cap

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: FastAPI app — `/api/analyze` (SSE) and `/api/reports/{report_id}`

**Files:**
- Create: `src/patientzero_api/app.py`
- Test: `tests/test_api_app.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `run_pipeline` (with `on_progress`) from `patientzero.pipeline` (Task 1); `serialize_claim_report` from `patientzero_api.serialization` (Task 2); `ReportStore` from `patientzero_api.store` (Task 3); `format_sse_event` from `patientzero_api.sse` (Task 4). Does NOT call `patientzero_api.clients` directly in its signature — the caller (a future `main.py`/uvicorn entry point, or this task's own test) constructs the `SerpClient`/`LLMClient`/`ReportStore` and passes them in, keeping `app.py` testable without environment variables.
- Produces: `create_app(serp_client: SerpClient, llm_client: LLMClient, store: ReportStore) -> FastAPI`. Task 7 (integration test) is the only other consumer.

- [ ] **Step 1: Add the `[api]` optional dependency**

Modify `pyproject.toml` — replace the `[project.optional-dependencies]` block with:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]
llm = ["groq>=0.11", "openai>=1.40"]
api = ["fastapi>=0.115", "uvicorn[standard]>=0.30"]
```

(This adds the new `api` extra alongside the existing `llm` extra — unchanged from `patientzero-core`'s current `pyproject.toml` — rather than reintroducing the old `anthropic` extra, which no longer exists after `docs/superpowers/plans/2026-09-18-patientzero-llm-providers.md` replaced it.)

- [ ] **Step 2: Install the new extra locally so the failing test can even import FastAPI**

Run: `pip install -e ".[api]"`
Expected: installs `fastapi`, `uvicorn`, and their transitive dependencies (including `starlette`) into the active environment.

- [ ] **Step 3: Write the failing test**

```python
# tests/test_api_app.py
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_api_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero_api.app'`

- [ ] **Step 5: Write `app.py`**

```python
# src/patientzero_api/app.py
"""Thin FastAPI wrapper over patientzero.pipeline.run_pipeline. This module
contains no forensics logic of its own — it only wires HTTP <-> the pipeline,
per spec sec 3.
"""
import queue
import threading
import uuid
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from patientzero.llm_client import LLMClient
from patientzero.pipeline import run_pipeline
from patientzero.serp_client import SerpClient
from patientzero_api.serialization import serialize_claim_report
from patientzero_api.sse import format_sse_event
from patientzero_api.store import ReportStore

_DONE = object()


def create_app(serp_client: SerpClient, llm_client: LLMClient, store: ReportStore) -> FastAPI:
    app = FastAPI(title="Patient Zero API")

    @app.get("/api/analyze")
    def analyze(text: str = Query(..., min_length=1)):
        report_id = str(uuid.uuid4())
        events: "queue.Queue" = queue.Queue()

        def on_progress(stage: str, detail: dict) -> None:
            events.put(("progress", {"stage": stage, **detail}))

        def worker() -> None:
            try:
                reports = run_pipeline(
                    text, serp_client, llm_client, today=date.today(), on_progress=on_progress
                )
                store.save(report_id, reports)
                events.put(
                    (
                        "report",
                        {
                            "report_id": report_id,
                            "claims": [serialize_claim_report(r) for r in reports],
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # run_pipeline already degrades known failure modes (spec sec
                # 6) internally, so reaching here means something unexpected
                # broke. The stream must still terminate rather than hang the
                # HTTP connection open forever with no final event.
                events.put(("error", {"message": str(exc)}))
            finally:
                events.put(_DONE)

        threading.Thread(target=worker, daemon=True).start()

        def stream():
            while True:
                item = events.get()
                if item is _DONE:
                    break
                event, data = item
                yield format_sse_event(event, data)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/reports/{report_id}")
    def get_report(report_id: str):
        reports = store.load(report_id)
        if reports is None:
            raise HTTPException(status_code=404, detail="report not found")
        return {"report_id": report_id, "claims": [serialize_claim_report(r) for r in reports]}

    return app
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_api_app.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Run the full suite to confirm nothing regressed**

Run: `python -m pytest -q`
Expected: all tests pass (48 after Task 1 + 2 from Task 2 + 4 from Task 3 + 2 from Task 4 + 5 from Task 5 + 3 from this task = 64), output pristine.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/patientzero_api/app.py tests/test_api_app.py
git commit -m "feat: add FastAPI app with SSE /api/analyze and /api/reports/{id}

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: End-to-end integration test through the full stack

**Files:**
- Test: `tests/test_api_integration.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `SerpClient`/`Cache` from `patientzero.serp_client`/`patientzero.cache` and `FakeLLMClient` from `patientzero.llm_client` (constructed directly, the same way `tests/test_pipeline.py` and `tests/test_api_app.py` already do — Task 5's `build_serp_client`/`build_llm_client` are NOT consumed here, since `build_llm_client` requires real `GROQ_API_KEY`/`OPENAI_API_KEY` values that this offline test must not need; Task 5's factories are exercised only by their own `test_api_clients.py`); `create_app` from `patientzero_api.app` (Task 6); `ReportStore` from `patientzero_api.store` (Task 3).
- Produces: nothing new — this task only proves Tasks 1, 3, and 6 compose correctly end to end, satisfying spec §7's "the engine works with no key and no network" requirement at the HTTP layer, not just the pipeline layer.

- [ ] **Step 1: Add `httpx` to the `dev` extra**

`fastapi.testclient.TestClient` requires `httpx` to be installed. Modify `pyproject.toml`'s `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "httpx>=0.27"]
llm = ["groq>=0.11", "openai>=1.40"]
api = ["fastapi>=0.115", "uvicorn[standard]>=0.30"]
```

Run: `pip install -e ".[dev,api]"`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_api_integration.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_api_integration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'httpx'` if Step 1's install hasn't been run yet in this environment; once `httpx` is installed, this test should actually PASS immediately, since it only composes already-implemented Tasks 1-6. That is fine — Step 4 confirms it passes for the right reason (real composition, not a stub), not because something is still unimplemented.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_integration.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite one final time**

Run: `python -m pytest -q`
Expected: all tests pass, output pristine. This is the final gate for the whole plan.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/test_api_integration.py
git commit -m "test: add end-to-end API integration test with zero network and no API key

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## After This Plan

This plan produces a working FastAPI wrapper with SSE progress streaming and saved-report retrieval, fully testable with `SERPAPI_MOCK=1` and a `FakeLLMClient`. It does **not** cover:

- A `main.py`/`if __name__ == "__main__"` uvicorn entry point wiring `build_serp_client`/`build_llm_client`/`ReportStore` together for a real run (small, but deliberately left out so this plan's own tests never need real Groq/OpenAI keys).
- The Next.js frontend / 5-panel report UI (spec §3).
- CORS configuration for a browser-based frontend to actually call this API (will be needed once the frontend exists).
- Recording real fixtures from a live SerpApi key (spec §7's manual smoke-test step) — this plan's tests all still use the same recorded fixtures `patientzero-core` already ships.
- Rate limiting / auth on the API endpoints (not in spec; hackathon scope explicitly excludes user accounts, spec §9).

Each of these is small enough to fold into the frontend plan or a short follow-up, once this one is executed and reviewed.
