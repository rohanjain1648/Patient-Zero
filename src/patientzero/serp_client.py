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
