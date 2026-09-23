"""Content-addressed cache for SerpApi responses.

Every SerpApi call in this codebase MUST go through this cache. Identical
normalized params never hit the network twice, which keeps the free-tier
credit budget (spec sec 5) usable during development and lets tests run
fully offline against recorded fixtures.
"""
import hashlib
import json
import sqlite3
import threading


class Cache:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        # The API runs each analysis on its own thread over one shared
        # connection; sqlite3 connections are not safe for concurrent use.
        self._lock = threading.Lock()
        with self._lock:
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
        with self._lock:
            row = self._conn.execute(
                "SELECT body FROM responses WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    def put(self, params: dict, response: dict) -> None:
        key = self.cache_key(params)
        body = json.dumps(response)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO responses (key, body) VALUES (?, ?)", (key, body)
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
