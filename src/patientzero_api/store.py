"""SQLite-backed store for completed analysis reports, separate from
patientzero-core's content-addressed SerpApi response cache (spec sec 3's
"SQLite: response cache + saved reports" line names these as two distinct
concerns). A corrupted stored row degrades to a miss rather than crashing
the request, matching the same lesson already applied to Cache.get in
patientzero-core.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from patientzero.models import ClaimReport
from patientzero_api.serialization import claim_report_from_dict, serialize_claim_report


class ReportStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        # Shared across request/worker threads; sqlite3 connections are not
        # safe for concurrent use.
        self._lock = threading.Lock()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS reports ("
            "report_id TEXT PRIMARY KEY, claims_json TEXT NOT NULL, created_at TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    def save(self, report_id: str, claims: list[ClaimReport]) -> None:
        body = json.dumps([serialize_claim_report(c) for c in claims])
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO reports (report_id, claims_json, created_at) VALUES (?, ?, ?)",
                (report_id, body, created_at),
            )
            self._conn.commit()

    def load(self, report_id: str) -> list[ClaimReport] | None:
        with self._lock:
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
        with self._lock:
            self._conn.close()
