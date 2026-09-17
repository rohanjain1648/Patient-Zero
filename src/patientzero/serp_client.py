"""Gateway to SerpApi. Every network call goes through the Cache (spec sec 3, 5).

When SERPAPI_MOCK=1, no network call is made at all: responses are read from
recorded fixture files, keyed by the "fixture" param, and then written into
the cache so subsequent identical calls don't even touch the filesystem.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from patientzero.cache import Cache
from patientzero.models import SearchResult

SERPAPI_ENDPOINT = "https://serpapi.com/search"
MAX_RETRIES = 3


class SerpApiError(Exception):
    pass


def _normalize_date(raw: str | None) -> str | None:
    """Normalize a SerpApi date string (e.g. "Jan 10, 2019") to ISO 8601.

    Returns None if `raw` is falsy or doesn't match the expected format,
    rather than raising: date normalization must never abort a search.
    """
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


class SerpClient:
    def __init__(
        self,
        api_key: str | None,
        cache: Cache,
        mock_dir: str | None = None,
        max_calls: int | None = None,
    ):
        self.api_key = api_key
        self.cache = cache
        self.mock_dir = mock_dir
        self.max_calls = max_calls
        self._call_count = 0

    def _is_mock(self) -> bool:
        return os.environ.get("SERPAPI_MOCK") == "1"

    def search(self, params: dict) -> dict:
        cached = self.cache.get(params)
        if cached is not None:
            return cached

        if self.max_calls is not None and self._call_count >= self.max_calls:
            raise SerpApiError("SerpApi call cap exceeded")
        self._call_count += 1

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
        # Sanitize against path traversal: only the bare file name (no
        # directory separators, no "..") is allowed to select a fixture.
        safe_name = Path(fixture_name).name
        if safe_name != fixture_name or safe_name in ("", ".", ".."):
            raise SerpApiError(f"invalid fixture name: {fixture_name!r}")
        fixture_path = Path(self.mock_dir) / f"{safe_name}.json"
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
            except (requests.RequestException, ValueError) as exc:
                # ValueError covers json.JSONDecodeError: a 200 response with
                # a malformed/non-JSON body should be retried just like a
                # network error, not propagate uncaught.
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
        raise SerpApiError(f"SerpApi call failed after {MAX_RETRIES} retries: {last_error}")

    def search_results(self, params: dict) -> list[SearchResult]:
        raw = self.search(params)
        results = []
        for item in raw.get("organic_results", []):
            link = item.get("link", "")
            netloc = urlparse(link).netloc
            if netloc.startswith("www."):
                netloc = netloc[len("www.") :]
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    link=link,
                    snippet=item.get("snippet", ""),
                    domain=netloc,
                    date=_normalize_date(item.get("date")),
                )
            )
        return results
