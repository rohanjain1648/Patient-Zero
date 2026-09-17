# Patient Zero Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `patientzero-core`, a standalone pip-installable Python package implementing the claim-provenance pipeline (cache, bisection origin-finding, echo detection, independence scoring, stance classification, atomization, orchestration) with a fixture-backed test suite that runs with zero network access and zero API key.

**Architecture:** Pure-function algorithmic core (bisection math, simhash clustering, independence scoring) is fully unit-tested with no I/O. All I/O (SerpApi calls, LLM calls) goes through small injectable client interfaces so the pipeline is testable end-to-end against recorded fixtures. A content-addressed SQLite cache sits in front of the SerpApi client so identical calls never hit the network twice, and a `SERPAPI_MOCK=1` env var forces fixture-only replay.

**Tech Stack:** Python ≥3.10, `requests`, stdlib `sqlite3`, `pytest`. No web framework yet — this plan produces the importable engine only; FastAPI/Next.js wrapper is a separate follow-on plan.

**Spec:** [docs/superpowers/specs/2026-09-17-patient-zero-design.md](../specs/2026-09-17-patient-zero-design.md) — this plan implements spec §3 (package decision), §4 (provenance algorithm), §5 (credit-budget guardrails), §6 (error handling), §7 (testing strategy).

## Global Constraints

- Python ≥3.10 (spec §... via serpapi-search-tools requirement; carried into this package for consistency).
- Every SerpApi network call MUST go through the cache layer (Task 3) — no exceptions, no direct `requests` calls elsewhere in the codebase (spec §3, §5).
- `SERPAPI_MOCK=1` MUST force fixture-only mode with zero live network calls (spec §5).
- No verdict language ("true"/"false") anywhere in code, comments, or output field names — use "support"/"refute"/"unrelated"/"unclear" and "candidate origin" (spec §1, §4.1).
- All stages must degrade to partial results rather than raising on failure, per spec §6.
- No Postgres, no queue, no microservices — SQLite + plain functions only (spec §9).

---

## File Structure

```
patientzero-core/
├── pyproject.toml
├── src/
│   └── patientzero/
│       ├── __init__.py
│       ├── models.py          # dataclasses shared across all stages
│       ├── cache.py           # content-addressed SQLite cache + SERPAPI_MOCK
│       ├── serp_client.py     # SerpApi HTTP gateway, cache-backed
│       ├── llm_client.py      # LLM client protocol + fake + Anthropic impl
│       ├── query_planner.py   # builds locale/date-restricted query params
│       ├── bisection.py       # temporal bisection origin-finding
│       ├── echo.py            # simhash clustering / echo detection
│       ├── independence.py    # independence scoring
│       ├── stance.py          # batched LLM stance classification
│       ├── atomizer.py        # LLM claim atomization
│       └── pipeline.py        # orchestrates all stages into a Report
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   └── serpapi/            # recorded raw SerpApi JSON responses
    ├── test_models.py
    ├── test_cache.py
    ├── test_serp_client.py
    ├── test_query_planner.py
    ├── test_bisection.py
    ├── test_echo.py
    ├── test_independence.py
    ├── test_stance.py
    ├── test_atomizer.py
    └── test_pipeline.py
```

---

### Task 1: Project scaffolding + data models

**Files:**
- Create: `pyproject.toml`
- Create: `src/patientzero/__init__.py`
- Create: `src/patientzero/models.py`
- Test: `tests/test_models.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: `SearchResult(title, link, snippet, domain, date)`, `Claim(text, index)`,
  `OriginCandidate(date, confidence, evidence_urls)`, `EchoCluster(result_indices, domain_count)`,
  `IndependenceScore(distinct_clusters, distinct_domains, temporal_spread_days, score)`,
  `StanceResult(claim_index, result_index, label, quote)`, `ClaimReport(claim, origin,
  independence, stances, locale_asymmetry)` — all as frozen dataclasses in `models.py`.
  Every later task imports these from `patientzero.models`.

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "patientzero-core"
version = "0.1.0"
description = "Claim provenance and propagation forensics engine, powered by SerpApi"
requires-python = ">=3.10"
dependencies = [
    "requests>=2.31",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]
anthropic = ["anthropic>=0.40"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Write the failing test for models**

```python
# tests/test_models.py
from patientzero.models import (
    SearchResult, Claim, OriginCandidate, EchoCluster,
    IndependenceScore, StanceResult, ClaimReport,
)

def test_search_result_is_immutable_and_holds_fields():
    r = SearchResult(
        title="Example headline",
        link="https://example.com/a",
        snippet="Some snippet text",
        domain="example.com",
        date="2020-01-15",
    )
    assert r.domain == "example.com"
    try:
        r.title = "changed"
        assert False, "SearchResult should be frozen"
    except AttributeError:
        pass

def test_claim_report_aggregates_all_stage_outputs():
    claim = Claim(text="X causes Y", index=0)
    origin = OriginCandidate(date="2019-03-01", confidence="medium", evidence_urls=["https://a.com"])
    independence = IndependenceScore(distinct_clusters=3, distinct_domains=12, temporal_spread_days=400, score=0.6)
    stances = [StanceResult(claim_index=0, result_index=0, label="support", quote="X does cause Y")]
    report = ClaimReport(claim=claim, origin=origin, independence=independence, stances=stances, locale_asymmetry={})
    assert report.claim.text == "X causes Y"
    assert report.origin.confidence == "medium"
    assert report.independence.score == 0.6
    assert report.stances[0].label == "support"
```

- [ ] **Step 2b: Create empty conftest.py**

```python
# tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero'`

- [ ] **Step 4: Write models.py**

```python
# src/patientzero/models.py
"""Shared data structures for the Patient Zero pipeline.

No stage constructs its own ad-hoc dicts for cross-stage data — everything
that crosses a stage boundary is one of these frozen dataclasses.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchResult:
    title: str
    link: str
    snippet: str
    domain: str
    date: str | None  # ISO date string if known, else None


@dataclass(frozen=True)
class Claim:
    text: str
    index: int


@dataclass(frozen=True)
class OriginCandidate:
    date: str | None          # ISO date of earliest corroborated appearance, or None if unresolved
    confidence: str           # "high" | "medium" | "low" | "unresolved"
    evidence_urls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EchoCluster:
    result_indices: tuple[int, ...]
    domain_count: int


@dataclass(frozen=True)
class IndependenceScore:
    distinct_clusters: int
    distinct_domains: int
    temporal_spread_days: int
    score: float               # 0.0-1.0, higher = more independent corroboration


@dataclass(frozen=True)
class StanceResult:
    claim_index: int
    result_index: int
    label: str                 # "support" | "refute" | "unrelated" | "unclear"
    quote: str


@dataclass(frozen=True)
class ClaimReport:
    claim: Claim
    origin: OriginCandidate
    independence: IndependenceScore
    stances: list[StanceResult]
    locale_asymmetry: dict[str, list[StanceResult]]  # locale code -> stances for that locale
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/patientzero/__init__.py src/patientzero/models.py tests/test_models.py tests/conftest.py
git commit -m "feat: scaffold patientzero-core package with shared data models

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Content-addressed SerpApi cache

**Files:**
- Create: `src/patientzero/cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (only stdlib `sqlite3`, `hashlib`, `json`).
- Produces: `Cache(db_path: str)` with methods `get(params: dict) -> dict | None`,
  `put(params: dict, response: dict) -> None`, and `cache_key(params: dict) -> str`.
  Task 3 (`serp_client.py`) wraps every call through `Cache.get`/`Cache.put`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cache.py
import os
import tempfile

from patientzero.cache import Cache


def test_cache_key_is_stable_regardless_of_param_order():
    c = Cache(db_path=":memory:")
    key_a = c.cache_key({"q": "hello", "hl": "en"})
    key_b = c.cache_key({"hl": "en", "q": "hello"})
    assert key_a == key_b


def test_cache_miss_returns_none():
    c = Cache(db_path=":memory:")
    assert c.get({"q": "never stored"}) is None


def test_cache_put_then_get_roundtrips():
    c = Cache(db_path=":memory:")
    params = {"q": "roundtrip test", "hl": "en"}
    response = {"organic_results": [{"title": "A"}]}
    c.put(params, response)
    assert c.get(params) == response


def test_cache_persists_to_file(tmp_path):
    db_path = str(tmp_path / "cache.sqlite3")
    c1 = Cache(db_path=db_path)
    c1.put({"q": "persisted"}, {"result": True})
    del c1

    c2 = Cache(db_path=db_path)
    assert c2.get({"q": "persisted"}) == {"result": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.cache'`

- [ ] **Step 3: Write cache.py**

```python
# src/patientzero/cache.py
"""Content-addressed cache for SerpApi responses.

Every SerpApi call in this codebase MUST go through this cache. Identical
normalized params never hit the network twice, which keeps the free-tier
credit budget (spec sec 5) usable during development and lets tests run
fully offline against recorded fixtures.
"""
import hashlib
import json
import sqlite3


class Cache:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, body TEXT NOT NULL)"
        )
        self._conn.commit()

    @staticmethod
    def cache_key(params: dict) -> str:
        normalized = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, params: dict) -> dict | None:
        key = self.cache_key(params)
        row = self._conn.execute(
            "SELECT body FROM responses WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def put(self, params: dict, response: dict) -> None:
        key = self.cache_key(params)
        body = json.dumps(response)
        self._conn.execute(
            "INSERT OR REPLACE INTO responses (key, body) VALUES (?, ?)", (key, body)
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cache.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero/cache.py tests/test_cache.py
git commit -m "feat: add content-addressed SQLite cache for SerpApi responses

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: SerpApi search gateway with SERPAPI_MOCK support

**Files:**
- Create: `src/patientzero/serp_client.py`
- Create: `tests/fixtures/serpapi/example_search.json`
- Test: `tests/test_serp_client.py`

**Interfaces:**
- Consumes: `Cache` from Task 2 (`cache.get`, `cache.put`).
- Produces: `SerpClient(api_key: str | None, cache: Cache, mock_dir: str | None = None)`
  with method `search(params: dict) -> dict` (returns raw SerpApi JSON dict) and
  `search_results(params: dict) -> list[SearchResult]` (parses `organic_results` into
  `SearchResult` objects). Task 5 (`bisection.py`) and others consume `search_results`.
  Raises `SerpApiError(message: str)` on unrecoverable failure after retries.

- [ ] **Step 1: Write the fixture file**

```json
{
  "search_metadata": {"status": "Success"},
  "organic_results": [
    {
      "title": "Example claim first reported",
      "link": "https://example-news.com/story-a",
      "snippet": "Officials say the example claim occurred on January 10th.",
      "displayed_link": "example-news.com",
      "date": "Jan 10, 2019"
    },
    {
      "title": "Another outlet covers the same claim",
      "link": "https://another-outlet.com/story-b",
      "snippet": "The claim reported by example-news.com was confirmed today.",
      "displayed_link": "another-outlet.com",
      "date": "Jan 11, 2019"
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_serp_client.py
import json
import os
from pathlib import Path

import pytest

from patientzero.cache import Cache
from patientzero.serp_client import SerpClient, SerpApiError

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "serpapi"


def test_mock_mode_returns_fixture_without_network(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    result = client.search({"q": "example claim", "fixture": "example_search"})
    assert result["organic_results"][0]["title"] == "Example claim first reported"


def test_mock_mode_raises_clear_error_when_fixture_missing(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    with pytest.raises(SerpApiError, match="fixture"):
        client.search({"q": "no such fixture", "fixture": "does_not_exist"})


def test_search_results_parses_organic_results_into_dataclasses(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    results = client.search_results({"q": "example claim", "fixture": "example_search"})
    assert len(results) == 2
    assert results[0].domain == "example-news.com"
    assert results[0].title == "Example claim first reported"


def test_second_identical_call_hits_cache_not_fixture_lookup(monkeypatch, tmp_path):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=str(tmp_path / "cache.sqlite3"))
    client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR))
    params = {"q": "example claim", "fixture": "example_search"}
    first = client.search(params)
    # Move the fixture dir away to prove the second call can't be re-reading it
    client.mock_dir = "/nonexistent/path"
    second = client.search(params)
    assert first == second
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_serp_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.serp_client'`

- [ ] **Step 4: Write serp_client.py**

```python
# src/patientzero/serp_client.py
"""Gateway to SerpApi. Every network call goes through the Cache (spec sec 3, 5).

When SERPAPI_MOCK=1, no network call is made at all: responses are read from
recorded fixture files, keyed by the "fixture" param, and then written into
the cache so subsequent identical calls don't even touch the filesystem.
"""
import json
import os
import time
from pathlib import Path

import requests

from patientzero.cache import Cache
from patientzero.models import SearchResult

SERPAPI_ENDPOINT = "https://serpapi.com/search"
MAX_RETRIES = 3


class SerpApiError(Exception):
    pass


class SerpClient:
    def __init__(self, api_key: str | None, cache: Cache, mock_dir: str | None = None):
        self.api_key = api_key
        self.cache = cache
        self.mock_dir = mock_dir

    def _is_mock(self) -> bool:
        return os.environ.get("SERPAPI_MOCK") == "1"

    def search(self, params: dict) -> dict:
        cached = self.cache.get(params)
        if cached is not None:
            return cached

        if self._is_mock():
            response = self._load_fixture(params)
        else:
            response = self._call_live(params)

        self.cache.put(params, response)
        return response

    def _load_fixture(self, params: dict) -> dict:
        fixture_name = params.get("fixture")
        if not fixture_name:
            raise SerpApiError(
                "SERPAPI_MOCK=1 but no 'fixture' key given in params; "
                "cannot select a fixture file"
            )
        fixture_path = Path(self.mock_dir) / f"{fixture_name}.json"
        if not fixture_path.exists():
            raise SerpApiError(f"fixture file not found: {fixture_path}")
        return json.loads(fixture_path.read_text())

    def _call_live(self, params: dict) -> dict:
        request_params = dict(params)
        request_params.pop("fixture", None)
        request_params["api_key"] = self.api_key

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(SERPAPI_ENDPOINT, params=request_params, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2 ** attempt)
        raise SerpApiError(f"SerpApi call failed after {MAX_RETRIES} retries: {last_error}")

    def search_results(self, params: dict) -> list[SearchResult]:
        raw = self.search(params)
        results = []
        for item in raw.get("organic_results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    link=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    domain=item.get("displayed_link", "").split("/")[0],
                    date=item.get("date"),
                )
            )
        return results
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_serp_client.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add src/patientzero/serp_client.py tests/test_serp_client.py tests/fixtures/serpapi/example_search.json
git commit -m "feat: add SerpApi gateway with SERPAPI_MOCK fixture replay

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Query planner (locale + date-restriction)

**Files:**
- Create: `src/patientzero/query_planner.py`
- Test: `tests/test_query_planner.py`

**Interfaces:**
- Consumes: `Claim` from Task 1.
- Produces: `build_date_restricted_query(claim: Claim, min_date: date | None, max_date: date | None) -> dict`,
  `build_locale_query(claim: Claim, hl: str, gl: str = "in") -> dict`. Both return
  plain `dict` param sets consumable by `SerpClient.search`/`search_results`.
  Task 5 (bisection) uses `build_date_restricted_query`; Task 9 (pipeline) uses
  `build_locale_query` for cross-lingual asymmetry.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query_planner.py
from datetime import date

from patientzero.models import Claim
from patientzero.query_planner import build_date_restricted_query, build_locale_query


def test_date_restricted_query_includes_tbs_range():
    claim = Claim(text="Water causes floods", index=0)
    params = build_date_restricted_query(
        claim, min_date=date(2018, 1, 1), max_date=date(2019, 1, 1)
    )
    assert params["q"] == "Water causes floods"
    assert params["tbs"] == "cdr:1,cd_min:01/01/2018,cd_max:01/01/2019"
    assert params["engine"] == "google"


def test_date_restricted_query_omits_tbs_when_no_bounds_given():
    claim = Claim(text="Unrestricted claim", index=0)
    params = build_date_restricted_query(claim, min_date=None, max_date=None)
    assert "tbs" not in params


def test_locale_query_sets_hl_and_gl():
    claim = Claim(text="Local claim", index=0)
    params = build_locale_query(claim, hl="hi", gl="in")
    assert params["hl"] == "hi"
    assert params["gl"] == "in"
    assert params["q"] == "Local claim"


def test_locale_query_defaults_gl_to_india():
    claim = Claim(text="Default gl claim", index=0)
    params = build_locale_query(claim, hl="en")
    assert params["gl"] == "in"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_query_planner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.query_planner'`

- [ ] **Step 3: Write query_planner.py**

```python
# src/patientzero/query_planner.py
"""Builds SerpApi query param dicts for the two query shapes the pipeline needs:
date-restricted (for bisection) and locale-targeted (for cross-lingual asymmetry).
"""
from datetime import date

from patientzero.models import Claim


def build_date_restricted_query(
    claim: Claim, min_date: date | None, max_date: date | None
) -> dict:
    params = {"engine": "google", "q": claim.text}
    if min_date is not None and max_date is not None:
        params["tbs"] = (
            f"cdr:1,cd_min:{min_date.strftime('%m/%d/%Y')},"
            f"cd_max:{max_date.strftime('%m/%d/%Y')}"
        )
    return params


def build_locale_query(claim: Claim, hl: str, gl: str = "in") -> dict:
    return {"engine": "google", "q": claim.text, "hl": hl, "gl": gl}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_query_planner.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero/query_planner.py tests/test_query_planner.py
git commit -m "feat: add query planner for date-restricted and locale queries

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Temporal bisection origin-finding

**Files:**
- Create: `src/patientzero/bisection.py`
- Test: `tests/test_bisection.py`

**Interfaces:**
- Consumes: `Claim`, `SearchResult`, `OriginCandidate` from Task 1; `SerpClient.search_results`
  from Task 3; `build_date_restricted_query` from Task 4.
- Produces: `find_origin(claim: Claim, serp_client: SerpClient, today: date,
  relevance_check: Callable[[Claim, list[SearchResult]], bool]) -> OriginCandidate`.
  The `relevance_check` callback is injected so tests can control it deterministically
  without needing a real LLM (spec sec 4.1's per-probe verification requirement).
  Task 9 (pipeline) supplies a real LLM-backed relevance check at call time.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bisection.py
from datetime import date

from patientzero.models import Claim, SearchResult
from patientzero.bisection import find_origin


def _result(link="https://a.com/x"):
    return SearchResult(title="t", link=link, snippet="s", domain="a.com", date=None)


def test_find_origin_returns_unresolved_when_no_window_has_relevant_results():
    claim = Claim(text="claim with no origin", index=0)

    class FakeClient:
        def search_results(self, params):
            return []  # nothing ever found

    def relevance_check(claim, results):
        return False

    origin = find_origin(
        claim, FakeClient(), today=date(2026, 9, 17), relevance_check=relevance_check
    )
    assert origin.confidence == "unresolved"
    assert origin.date is None


def test_find_origin_converges_on_bracket_containing_two_corroborating_results():
    claim = Claim(text="claim with known origin", index=0)

    # Simulate: any window whose max_date >= 2019-06-01 has 2 corroborating results,
    # any window entirely before that has none.
    def fake_search_results(params):
        tbs = params.get("tbs", "")
        if not tbs:
            return [_result(), _result("https://b.com/y")]
        max_date_str = tbs.split("cd_max:")[1]
        month, day, year = max_date_str.split("/")
        cutoff = date(int(year), int(month), int(day))
        if cutoff >= date(2019, 6, 1):
            return [_result(), _result("https://b.com/y")]
        return []

    class FakeClient:
        def search_results(self, params):
            return fake_search_results(params)

    def relevance_check(claim, results):
        return len(results) >= 2

    origin = find_origin(
        claim, FakeClient(), today=date(2026, 9, 17), relevance_check=relevance_check
    )
    assert origin.confidence in ("high", "medium")
    assert origin.date is not None
    resolved = date.fromisoformat(origin.date)
    # Bisection should land within ~1 month of the true cutoff
    assert abs((resolved - date(2019, 6, 1)).days) <= 35


def test_find_origin_requires_corroboration_not_just_one_result():
    claim = Claim(text="single uncorroborated result", index=0)

    class FakeClient:
        def search_results(self, params):
            return [_result()]  # always exactly one result, never two

    def relevance_check(claim, results):
        return len(results) >= 1

    origin = find_origin(
        claim, FakeClient(), today=date(2026, 9, 17), relevance_check=relevance_check
    )
    assert origin.confidence == "unresolved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bisection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.bisection'`

- [ ] **Step 3: Write bisection.py**

```python
# src/patientzero/bisection.py
"""Temporal bisection: find the earliest indexed-date window in which a claim's
corroborated evidence first appears (spec sec 4.1).

Algorithm:
  1. Exponential bracket probe at today-1y, today-3y, today-8y to find a window
     that already contains corroborated evidence (the "positive" bracket) and one
     that doesn't (the "negative" bracket).
  2. Bisect between the negative and positive bracket dates until the window is
     within ~1 month.
  3. Every probe's results must pass BOTH a relevance check (are these results
     actually about this claim?) AND a corroboration requirement (>=2 results)
     before the window counts as "positive". A window returning results is not
     the same as a window returning evidence for this claim.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from patientzero.models import Claim, OriginCandidate, SearchResult
from patientzero.query_planner import build_date_restricted_query

BRACKET_OFFSETS_YEARS = (1, 3, 8)
MIN_CORROBORATION = 2
BISECTION_TOLERANCE_DAYS = 31
MAX_BISECTION_STEPS = 6


def _is_positive_window(
    claim: Claim,
    serp_client,
    min_date: date,
    max_date: date,
    relevance_check: Callable[[Claim, list[SearchResult]], bool],
) -> bool:
    params = build_date_restricted_query(claim, min_date=min_date, max_date=max_date)
    results = serp_client.search_results(params)
    if len(results) < MIN_CORROBORATION:
        return False
    return relevance_check(claim, results)


def find_origin(
    claim: Claim,
    serp_client,
    today: date,
    relevance_check: Callable[[Claim, list[SearchResult]], bool],
) -> OriginCandidate:
    epoch = date(2000, 1, 1)

    # Step 1: bracket probe
    positive_max_date = None
    for years in BRACKET_OFFSETS_YEARS:
        candidate_max = today - timedelta(days=365 * years)
        if _is_positive_window(claim, serp_client, epoch, candidate_max, relevance_check):
            positive_max_date = candidate_max
            break

    if positive_max_date is None:
        # Even the widest bracket (8y) found no corroborated evidence at all.
        # Try the full range up to today as a last resort before giving up.
        if _is_positive_window(claim, serp_client, epoch, today, relevance_check):
            positive_max_date = today
        else:
            return OriginCandidate(date=None, confidence="unresolved", evidence_urls=[])

    # Step 2: bisect between epoch (negative, nothing before start of time) and
    # positive_max_date to narrow down the earliest positive window.
    low = epoch
    high = positive_max_date
    steps = 0
    while (high - low).days > BISECTION_TOLERANCE_DAYS and steps < MAX_BISECTION_STEPS:
        mid = low + (high - low) / 2
        if _is_positive_window(claim, serp_client, epoch, mid, relevance_check):
            high = mid
        else:
            low = mid
        steps += 1

    # Final evidence collection at the converged window for evidence_urls + confidence
    params = build_date_restricted_query(claim, min_date=epoch, max_date=high)
    results = serp_client.search_results(params)
    confidence = "high" if len(results) >= 3 else "medium"

    return OriginCandidate(
        date=high.isoformat(),
        confidence=confidence,
        evidence_urls=[r.link for r in results[:5]],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bisection.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero/bisection.py tests/test_bisection.py
git commit -m "feat: add temporal bisection algorithm for origin-finding

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Echo detection (simhash clustering)

**Files:**
- Create: `src/patientzero/echo.py`
- Test: `tests/test_echo.py`

**Interfaces:**
- Consumes: `SearchResult` from Task 1.
- Produces: `simhash(text: str, num_bits: int = 64) -> int`, `hamming_distance(a: int, b: int) -> int`,
  `cluster_results(results: list[SearchResult], distance_threshold: int = 3) -> list[EchoCluster]`.
  Task 7 (independence) consumes `cluster_results` output directly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_echo.py
from patientzero.models import SearchResult
from patientzero.echo import simhash, hamming_distance, cluster_results


def _result(title, snippet, domain):
    return SearchResult(title=title, link=f"https://{domain}/x", snippet=snippet, domain=domain, date=None)


def test_simhash_identical_text_is_identical_hash():
    a = simhash("the quick brown fox jumps over the lazy dog")
    b = simhash("the quick brown fox jumps over the lazy dog")
    assert a == b


def test_simhash_similar_text_has_small_hamming_distance():
    a = simhash("the quick brown fox jumps over the lazy dog")
    b = simhash("the quick brown fox jumped over the lazy dog")
    assert hamming_distance(a, b) <= 4


def test_simhash_unrelated_text_has_large_hamming_distance():
    a = simhash("the quick brown fox jumps over the lazy dog")
    b = simhash("stock markets rallied today on strong earnings reports")
    assert hamming_distance(a, b) > 10


def test_cluster_results_groups_near_duplicate_syndicated_copies():
    results = [
        _result("Floods hit the region hard", "Officials confirm floods hit the region hard today", "wire-a.com"),
        _result("Floods hit the region hard", "Officials confirm floods hit the region hard today", "copycat-b.com"),
        _result("Local team wins championship", "The local team won the championship after a close match", "sports-c.com"),
    ]
    clusters = cluster_results(results)
    sizes = sorted(len(c.result_indices) for c in clusters)
    assert sizes == [1, 2]


def test_cluster_with_multiple_domains_reports_domain_count():
    results = [
        _result("Same story", "identical wording used everywhere in this test", "a.com"),
        _result("Same story", "identical wording used everywhere in this test", "b.com"),
        _result("Same story", "identical wording used everywhere in this test", "c.com"),
    ]
    clusters = cluster_results(results)
    assert len(clusters) == 1
    assert clusters[0].domain_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_echo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.echo'`

- [ ] **Step 3: Write echo.py**

```python
# src/patientzero/echo.py
"""Simhash-based echo detection: clusters near-duplicate title+snippet text so
syndicated/copy-paste coverage doesn't get counted as independent corroboration
(spec sec 4.2).
"""
import hashlib
import re

from patientzero.models import EchoCluster, SearchResult

DEFAULT_NUM_BITS = 64
SHINGLE_SIZE = 4


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _shingles(tokens: list[str], size: int = SHINGLE_SIZE) -> list[str]:
    if len(tokens) < size:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)]


def simhash(text: str, num_bits: int = DEFAULT_NUM_BITS) -> int:
    tokens = _tokenize(text)
    shingles = _shingles(tokens)
    if not shingles:
        return 0

    bit_votes = [0] * num_bits
    for shingle in shingles:
        digest = hashlib.sha256(shingle.encode("utf-8")).digest()
        hash_int = int.from_bytes(digest, "big")
        for bit in range(num_bits):
            if (hash_int >> bit) & 1:
                bit_votes[bit] += 1
            else:
                bit_votes[bit] -= 1

    result = 0
    for bit in range(num_bits):
        if bit_votes[bit] > 0:
            result |= 1 << bit
    return result


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def cluster_results(
    results: list[SearchResult], distance_threshold: int = 3
) -> list[EchoCluster]:
    hashes = [simhash(f"{r.title} {r.snippet}") for r in results]
    n = len(results)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            if hamming_distance(hashes[i], hashes[j]) <= distance_threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    clusters = []
    for indices in groups.values():
        domains = {results[i].domain for i in indices}
        clusters.append(EchoCluster(result_indices=tuple(indices), domain_count=len(domains)))
    return clusters
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_echo.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero/echo.py tests/test_echo.py
git commit -m "feat: add simhash-based echo detection for syndicated content

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Independence scoring

**Files:**
- Create: `src/patientzero/independence.py`
- Test: `tests/test_independence.py`

**Interfaces:**
- Consumes: `EchoCluster`, `SearchResult`, `IndependenceScore` from Task 1/6;
  `cluster_results` from Task 6.
- Produces: `score_independence(results: list[SearchResult], clusters: list[EchoCluster]) -> IndependenceScore`.
  Task 9 (pipeline) calls this directly after `cluster_results`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_independence.py
from patientzero.models import SearchResult, EchoCluster
from patientzero.independence import score_independence


def _result(domain, date=None):
    return SearchResult(title="t", link=f"https://{domain}/x", snippet="s", domain=domain, date=date)


def test_many_syndicated_copies_score_low_independence():
    results = [_result(f"copy{i}.com", date="2020-01-01") for i in range(10)]
    clusters = [EchoCluster(result_indices=tuple(range(10)), domain_count=10)]
    score = score_independence(results, clusters)
    assert score.distinct_clusters == 1
    assert score.score < 0.3


def test_multiple_independent_clusters_score_higher():
    results = [
        _result("a.com", date="2018-01-01"),
        _result("b.com", date="2020-06-01"),
        _result("c.com", date="2022-12-01"),
    ]
    clusters = [
        EchoCluster(result_indices=(0,), domain_count=1),
        EchoCluster(result_indices=(1,), domain_count=1),
        EchoCluster(result_indices=(2,), domain_count=1),
    ]
    score = score_independence(results, clusters)
    assert score.distinct_clusters == 3
    assert score.distinct_domains == 3
    assert score.temporal_spread_days > 1000
    assert score.score > 0.6


def test_score_is_clamped_between_zero_and_one():
    results = [_result(f"d{i}.com", date="2021-01-01") for i in range(50)]
    clusters = [EchoCluster(result_indices=(i,), domain_count=1) for i in range(50)]
    score = score_independence(results, clusters)
    assert 0.0 <= score.score <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_independence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.independence'`

- [ ] **Step 3: Write independence.py**

```python
# src/patientzero/independence.py
"""Combines echo-cluster output into a single independence score: how much of
the "142 sources agree" is actually independent corroboration vs syndicated
copies of the same 2-3 origins (spec sec 4.2).
"""
from datetime import date

from patientzero.models import EchoCluster, IndependenceScore, SearchResult

# Empirically-chosen normalization caps: beyond these, additional clusters/
# domains/days no longer meaningfully increase confidence.
CLUSTER_NORM_CAP = 5
DOMAIN_NORM_CAP = 10
TEMPORAL_NORM_CAP_DAYS = 1500


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def score_independence(
    results: list[SearchResult], clusters: list[EchoCluster]
) -> IndependenceScore:
    distinct_clusters = len(clusters)
    distinct_domains = len({r.domain for r in results})

    dates = [d for d in (_parse_date(r.date) for r in results) if d is not None]
    temporal_spread_days = (max(dates) - min(dates)).days if len(dates) >= 2 else 0

    cluster_component = min(distinct_clusters / CLUSTER_NORM_CAP, 1.0)
    domain_component = min(distinct_domains / DOMAIN_NORM_CAP, 1.0)
    temporal_component = min(temporal_spread_days / TEMPORAL_NORM_CAP_DAYS, 1.0)

    score = round(
        0.5 * cluster_component + 0.3 * domain_component + 0.2 * temporal_component, 4
    )
    score = max(0.0, min(1.0, score))

    return IndependenceScore(
        distinct_clusters=distinct_clusters,
        distinct_domains=distinct_domains,
        temporal_spread_days=temporal_spread_days,
        score=score,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_independence.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero/independence.py tests/test_independence.py
git commit -m "feat: add independence scoring combining cluster/domain/temporal signals

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: LLM client abstraction (fake + Anthropic-backed)

**Files:**
- Create: `src/patientzero/llm_client.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `LLMClient` protocol with `complete(prompt: str) -> str`; `FakeLLMClient(responses: list[str])`
  for tests (returns queued responses in order, raises `StopIteration`-derived `LLMClientError`
  if exhausted); `AnthropicLLMClient(api_key: str, model: str = "claude-sonnet-5")` as the
  real implementation. Tasks 9 and 10 (stance, atomizer) both take an `LLMClient` in their
  constructor/function signature and call only `.complete(prompt)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.llm_client'`

- [ ] **Step 3: Write llm_client.py**

```python
# src/patientzero/llm_client.py
"""LLM client abstraction. Stance classification (Task 9) and atomization
(Task 10) depend only on the `complete(prompt) -> str` method, never on a
specific provider SDK, so tests can inject FakeLLMClient with zero network
or API-key requirements.
"""
from typing import Protocol


class LLMClientError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class FakeLLMClient:
    """Test double: returns pre-scripted responses in order."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.received_prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.received_prompts.append(prompt)
        if not self._responses:
            raise LLMClientError("FakeLLMClient exhausted: no more queued responses")
        return self._responses.pop(0)


class AnthropicLLMClient:
    """Real implementation backed by the Anthropic API. Requires the
    `anthropic` package (install with `pip install patientzero-core[anthropic]`).
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        import anthropic  # deferred import: only required when actually used

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero/llm_client.py tests/test_llm_client.py
git commit -m "feat: add LLM client abstraction with fake and Anthropic-backed impls

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Batched stance classification

**Files:**
- Create: `src/patientzero/stance.py`
- Test: `tests/test_stance.py`

**Interfaces:**
- Consumes: `Claim`, `SearchResult`, `StanceResult` from Task 1; `LLMClient` protocol
  from Task 8.
- Produces: `classify_stances(claim: Claim, results: list[SearchResult], llm: LLMClient,
  batch_size: int = 5) -> list[StanceResult]`. Task 11 (pipeline) calls this per claim
  per locale.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stance.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.stance'`

- [ ] **Step 3: Write stance.py**

```python
# src/patientzero/stance.py
"""Batched LLM stance classification. Never returns a raw TRUE/FALSE verdict —
labels are support/refute/unrelated/unclear, each with the justifying quote
(spec sec 1, 4.4). Malformed LLM output degrades to "unclear" for every result
in that batch rather than raising (spec sec 6).
"""
import json

from patientzero.llm_client import LLMClient
from patientzero.models import Claim, SearchResult, StanceResult

VALID_LABELS = {"support", "refute", "unrelated", "unclear"}


def _build_prompt(claim: Claim, batch: list[tuple[int, SearchResult]]) -> str:
    items = "\n".join(
        f'{{"result_index": {idx}, "title": {json.dumps(r.title)}, "snippet": {json.dumps(r.snippet)}}}'
        for idx, r in batch
    )
    return (
        f"Claim: {claim.text}\n\n"
        f"For each search result below, decide whether it supports, refutes, is "
        f"unrelated to, or is unclear about the claim. Respond ONLY with a JSON "
        f"array of objects: "
        f'[{{"result_index": <int>, "label": "support"|"refute"|"unrelated"|"unclear", '
        f'"quote": "<short justifying quote from the snippet>"}}]\n\n'
        f"Results:\n{items}"
    )


def classify_stances(
    claim: Claim, results: list[SearchResult], llm: LLMClient, batch_size: int = 5
) -> list[StanceResult]:
    indexed = list(enumerate(results))
    all_stances: list[StanceResult] = []

    for start in range(0, len(indexed), batch_size):
        batch = indexed[start : start + batch_size]
        prompt = _build_prompt(claim, batch)
        raw_response = llm.complete(prompt)

        try:
            parsed = json.loads(raw_response)
            by_index = {item["result_index"]: item for item in parsed}
        except (json.JSONDecodeError, TypeError, KeyError):
            by_index = {}

        for idx, _result in batch:
            item = by_index.get(idx)
            if item is None or item.get("label") not in VALID_LABELS:
                all_stances.append(
                    StanceResult(claim_index=claim.index, result_index=idx, label="unclear", quote="")
                )
            else:
                all_stances.append(
                    StanceResult(
                        claim_index=claim.index,
                        result_index=idx,
                        label=item["label"],
                        quote=item.get("quote", ""),
                    )
                )

    return all_stances
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stance.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero/stance.py tests/test_stance.py
git commit -m "feat: add batched LLM stance classification with graceful degradation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Claim atomization

**Files:**
- Create: `src/patientzero/atomizer.py`
- Test: `tests/test_atomizer.py`

**Interfaces:**
- Consumes: `Claim` from Task 1; `LLMClient` protocol from Task 8.
- Produces: `atomize(text: str, llm: LLMClient) -> list[Claim]`. Returns `[]` (not an
  error) when no checkable claims are found (spec sec 6). Task 11 (pipeline) calls
  this first, on raw user input.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atomizer.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_atomizer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.atomizer'`

- [ ] **Step 3: Write atomizer.py**

```python
# src/patientzero/atomizer.py
"""Splits raw user input (a forward, a headline, a URL's text) into individually
checkable factual assertions. Returns an empty list — not an error — when the
input contains no verifiable claims (spec sec 6), e.g. pure opinion.
"""
import json

from patientzero.llm_client import LLMClient
from patientzero.models import Claim


def _build_prompt(text: str) -> str:
    return (
        "Extract every individually fact-checkable factual assertion from the "
        "text below. Ignore opinions, greetings, and non-factual statements. "
        "Respond ONLY with a JSON array of strings, one per claim. If there are "
        "no checkable factual claims, respond with an empty array: []\n\n"
        f"Text:\n{text}"
    )


def atomize(text: str, llm: LLMClient) -> list[Claim]:
    prompt = _build_prompt(text)
    raw_response = llm.complete(prompt)

    try:
        parsed = json.loads(raw_response)
        if not isinstance(parsed, list):
            return []
    except json.JSONDecodeError:
        return []

    return [Claim(text=str(item), index=i) for i, item in enumerate(parsed) if str(item).strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_atomizer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/patientzero/atomizer.py tests/test_atomizer.py
git commit -m "feat: add LLM-based claim atomizer with graceful empty-result handling

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: Pipeline orchestration

**Files:**
- Create: `src/patientzero/pipeline.py`
- Create: `tests/fixtures/serpapi/origin_positive.json`
- Create: `tests/fixtures/serpapi/origin_negative.json`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 1–10: `atomize`, `find_origin`, `cluster_results`,
  `score_independence`, `classify_stances`, `build_locale_query`, `SerpClient`, `LLMClient`.
- Produces: `run_pipeline(text: str, serp_client: SerpClient, llm: LLMClient, today: date,
  locales: list[str] = ["en", "hi"]) -> list[ClaimReport]`. This is the top-level function
  the FastAPI wrapper (future plan) calls.

- [ ] **Step 1: Write the fixture files**

```json
// tests/fixtures/serpapi/origin_positive.json
{
  "search_metadata": {"status": "Success"},
  "organic_results": [
    {"title": "Report on the claim", "link": "https://wire-a.com/x", "snippet": "detailed evidence about the pipeline test claim", "displayed_link": "wire-a.com", "date": "Jun 1, 2019"},
    {"title": "Second outlet on the claim", "link": "https://wire-b.com/y", "snippet": "detailed evidence about the pipeline test claim", "displayed_link": "wire-b.com", "date": "Jun 2, 2019"}
  ]
}
```

```json
// tests/fixtures/serpapi/origin_negative.json
{
  "search_metadata": {"status": "Success"},
  "organic_results": []
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_pipeline.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'patientzero.pipeline'`

- [ ] **Step 4: Write pipeline.py**

```python
# src/patientzero/pipeline.py
"""Top-level orchestration: raw text in, a ClaimReport per atomized claim out.
This is the single entry point the FastAPI wrapper (separate plan) calls.
"""
from datetime import date

from patientzero.atomizer import atomize
from patientzero.bisection import find_origin
from patientzero.echo import cluster_results
from patientzero.independence import score_independence
from patientzero.llm_client import LLMClient
from patientzero.models import ClaimReport
from patientzero.query_planner import build_locale_query
from patientzero.serp_client import SerpClient
from patientzero.stance import classify_stances

DEFAULT_LOCALES = ["en", "hi"]


def _relevance_check(llm: LLMClient):
    def check(claim, results) -> bool:
        if not results:
            return False
        stances = classify_stances(claim, results, llm)
        return any(s.label in ("support", "refute") for s in stances)

    return check


def run_pipeline(
    text: str,
    serp_client: SerpClient,
    llm: LLMClient,
    today: date,
    locales: list[str] = None,
) -> list[ClaimReport]:
    if locales is None:
        locales = DEFAULT_LOCALES

    claims = atomize(text, llm)
    reports = []

    for claim in claims:
        origin = find_origin(claim, serp_client, today, relevance_check=_relevance_check(llm))

        locale_asymmetry = {}
        all_results_for_independence = []
        for locale in locales:
            params = build_locale_query(claim, hl=locale)
            results = serp_client.search_results(params)
            all_results_for_independence.extend(results)
            stances = classify_stances(claim, results, llm)
            locale_asymmetry[locale] = stances

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

    return reports
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Run the full test suite to confirm nothing regressed**

Run: `pytest tests/ -v`
Expected: all tests across all 11 tasks PASS

- [ ] **Step 7: Commit**

```bash
git add src/patientzero/pipeline.py tests/test_pipeline.py tests/fixtures/serpapi/origin_positive.json tests/fixtures/serpapi/origin_negative.json
git commit -m "feat: add pipeline orchestration tying atomizer, bisection, echo, independence, and stance together

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 12: Golden-claim regression fixtures

**Files:**
- Create: `tests/fixtures/golden_claims.json`
- Test: `tests/test_golden_claims.py`

**Interfaces:**
- Consumes: `run_pipeline` from Task 11; fixture JSON files (this task documents the
  *shape* golden claims must have — recording real fixture data from actual SerpApi
  calls happens later, outside this plan, per spec sec 7's manual-smoke-test step).
- Produces: a regression test that will be extended with real recorded fixtures once
  a SerpApi key is available; for this plan, establishes the harness and one synthetic
  golden case so the pattern exists and CI has something to run.

- [ ] **Step 1: Write the golden claims manifest**

```json
// tests/fixtures/golden_claims.json
[
  {
    "name": "no_clear_origin_case",
    "input_text": "A claim that appears in no indexed source anywhere.",
    "expected_origin_confidence": "unresolved"
  }
]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_golden_claims.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_golden_claims.py -v`
Expected: FAIL — `origin_negative.json` fixture already exists from Task 11 but the
manifest/test files don't exist yet, so this fails with `FileNotFoundError` for
`golden_claims.json` until Step 1 is done; after Step 1, it should fail only if
`run_pipeline` behavior doesn't yet match (it should actually pass immediately given
Task 11's implementation — if so, this step's "expected fail" is superseded by
confirming it passes for the right reason, which the next step verifies).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_golden_claims.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/golden_claims.json tests/test_golden_claims.py
git commit -m "test: add golden-claim regression harness with no-origin case

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## After This Plan

This plan produces a fully tested, importable `patientzero-core` package that runs
end-to-end with zero network access via `SERPAPI_MOCK=1`. It does **not** cover:

- FastAPI HTTP wrapper + SSE streaming (spec §3)
- Next.js frontend / 5-panel report UI (spec §3)
- Recording real fixtures from a live SerpApi key against real golden claims (spec §7)
- PyPI publish (spec §8, day 10)
- Demo video, README, submission text (spec §8, days 14–18)

Each of these is substantial enough to warrant its own plan once this one is executed
and reviewed.
