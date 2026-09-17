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
