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
    assert results[0].date == "2019-01-10"


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


def test_max_calls_cap_raises_after_limit_exceeded(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR), max_calls=1)
    client.search({"q": "first call", "fixture": "example_search"})
    with pytest.raises(SerpApiError, match="cap"):
        client.search({"q": "second call, different params", "fixture": "example_search"})


def test_max_calls_cap_does_not_count_cache_hits(monkeypatch):
    monkeypatch.setenv("SERPAPI_MOCK", "1")
    cache = Cache(db_path=":memory:")
    client = SerpClient(api_key=None, cache=cache, mock_dir=str(FIXTURE_DIR), max_calls=1)
    params = {"q": "same params", "fixture": "example_search"}
    client.search(params)  # 1st real call, uses up the cap
    client.search(params)  # identical params -> cache hit, should NOT raise
