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
