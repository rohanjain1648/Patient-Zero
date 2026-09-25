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


def test_round_trip_preserves_propagation():
    from patientzero.models import MediaMention, Propagation, TrendPoint

    report = ClaimReport(
        claim=Claim(text="c", index=0),
        origin=OriginCandidate(date="2016-06-05", confidence="high", evidence_urls=["u"]),
        independence=IndependenceScore(
            distinct_clusters=1, distinct_domains=1, temporal_spread_days=0, score=0.5
        ),
        stances=[],
        locale_asymmetry={},
        propagation=Propagation(
            trend=[TrendPoint(date="Jun 2016", timestamp=1464739200, value=91)],
            mentions=[
                MediaMention(
                    medium="news", title="t", link="l", source="s", date="2016-07-04"
                )
            ],
            peak_date="2016-06-01",
        ),
    )

    restored = claim_report_from_dict(serialize_claim_report(report))
    assert restored == report


def test_a_report_stored_before_propagation_existed_still_loads():
    """Rows written by the pre-propagation schema have no such key."""
    legacy = {
        "claim": {"text": "c", "index": 0},
        "origin": {"date": None, "confidence": "unresolved", "evidence_urls": []},
        "independence": {
            "distinct_clusters": 0,
            "distinct_domains": 0,
            "temporal_spread_days": 0,
            "score": 0.0,
        },
        "stances": [],
        "locale_asymmetry": {},
    }
    restored = claim_report_from_dict(legacy)
    assert restored.propagation.trend == []
    assert restored.propagation.peak_date is None
