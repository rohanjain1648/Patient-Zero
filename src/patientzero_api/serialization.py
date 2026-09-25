"""Converts patientzero.models.ClaimReport (and its nested frozen dataclasses)
to and from plain JSON-safe dicts. Every HTTP response body and every row the
ReportStore (Task 3) writes to SQLite goes through these two functions — no
other module builds its own shape for a ClaimReport.
"""
from dataclasses import asdict

from patientzero.models import (
    Claim,
    ClaimReport,
    IndependenceScore,
    MediaMention,
    OriginCandidate,
    Propagation,
    StanceResult,
    TrendPoint,
)


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
        propagation=_propagation_from_dict(data.get("propagation")),
    )


def _propagation_from_dict(data: dict | None) -> Propagation:
    # Reports stored before propagation existed have no such key; they must
    # still load rather than 500 the saved-report endpoint.
    if not data:
        return Propagation()
    return Propagation(
        trend=[TrendPoint(**p) for p in data.get("trend", [])],
        mentions=[MediaMention(**m) for m in data.get("mentions", [])],
        peak_date=data.get("peak_date"),
    )
