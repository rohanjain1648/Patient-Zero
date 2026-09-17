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
