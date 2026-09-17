from patientzero.models import SearchResult
from patientzero.echo import simhash, hamming_distance, cluster_results


def _result(title, snippet, domain):
    return SearchResult(title=title, link=f"https://{domain}/x", snippet=snippet, domain=domain, date=None)


def test_simhash_identical_text_is_identical_hash():
    a = simhash("the quick brown fox jumps over the lazy dog")
    b = simhash("the quick brown fox jumps over the lazy dog")
    assert a == b


def test_simhash_similar_text_has_small_hamming_distance():
    a = simhash("the quick brown fox jumps over the lazy dog")
    b = simhash("the quick brown fox jumped over the lazy dog")
    assert hamming_distance(a, b) <= 4


def test_simhash_unrelated_text_has_large_hamming_distance():
    a = simhash("the quick brown fox jumps over the lazy dog")
    b = simhash("stock markets rallied today on strong earnings reports")
    assert hamming_distance(a, b) > 10


def test_cluster_results_groups_near_duplicate_syndicated_copies():
    results = [
        _result("Floods hit the region hard", "Officials confirm floods hit the region hard today", "wire-a.com"),
        _result("Floods hit the region hard", "Officials confirm floods hit the region hard today", "copycat-b.com"),
        _result("Local team wins championship", "The local team won the championship after a close match", "sports-c.com"),
    ]
    clusters = cluster_results(results)
    sizes = sorted(len(c.result_indices) for c in clusters)
    assert sizes == [1, 2]


def test_cluster_with_multiple_domains_reports_domain_count():
    results = [
        _result("Same story", "identical wording used everywhere in this test", "a.com"),
        _result("Same story", "identical wording used everywhere in this test", "b.com"),
        _result("Same story", "identical wording used everywhere in this test", "c.com"),
    ]
    clusters = cluster_results(results)
    assert len(clusters) == 1
    assert clusters[0].domain_count == 3


def test_simhash_nonlatin_text_does_not_collapse_to_zero():
    a = simhash("यह एक असंबंधित समाचार कहानी है जो बहुत अलग विषय पर है")
    assert a != 0


def test_cluster_results_does_not_falsely_merge_unrelated_nonlatin_text():
    results = [
        _result("पहली खबर", "यह एक पूरी तरह से अलग विषय के बारे में खबर है", "site-a.com"),
        _result("दूसरी खबर", "बाजार में शेयरों की कीमतों में आज भारी गिरावट दर्ज की गई", "site-b.com"),
    ]
    clusters = cluster_results(results)
    assert len(clusters) == 2
