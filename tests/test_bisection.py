# tests/test_bisection.py
from datetime import date

from patientzero.models import Claim, SearchResult
from patientzero.bisection import find_origin


def _result(link="https://a.com/x"):
    return SearchResult(title="t", link=link, snippet="s", domain="a.com", date=None)


def test_find_origin_returns_unresolved_when_no_window_has_relevant_results():
    claim = Claim(text="claim with no origin", index=0)

    class FakeClient:
        def search_results(self, params):
            return []  # nothing ever found

    def relevance_check(claim, results):
        return False

    origin = find_origin(
        claim, FakeClient(), today=date(2026, 9, 17), relevance_check=relevance_check
    )
    assert origin.confidence == "unresolved"
    assert origin.date is None


def test_find_origin_converges_on_bracket_containing_two_corroborating_results():
    claim = Claim(text="claim with known origin", index=0)

    # Simulate: any window whose max_date >= 2019-06-01 has 2 corroborating results,
    # any window entirely before that has none.
    def fake_search_results(params):
        tbs = params.get("tbs", "")
        if not tbs:
            return [_result(), _result("https://b.com/y")]
        max_date_str = tbs.split("cd_max:")[1]
        month, day, year = max_date_str.split("/")
        cutoff = date(int(year), int(month), int(day))
        if cutoff >= date(2019, 6, 1):
            return [_result(), _result("https://b.com/y")]
        return []

    class FakeClient:
        def search_results(self, params):
            return fake_search_results(params)

    def relevance_check(claim, results):
        return len(results) >= 2

    origin = find_origin(
        claim, FakeClient(), today=date(2026, 9, 17), relevance_check=relevance_check
    )
    assert origin.confidence in ("high", "medium")
    assert origin.date is not None
    resolved = date.fromisoformat(origin.date)
    # Bisection should land within ~1 month of the true cutoff
    assert abs((resolved - date(2019, 6, 1)).days) <= 35


def test_find_origin_requires_corroboration_not_just_one_result():
    claim = Claim(text="single uncorroborated result", index=0)

    class FakeClient:
        def search_results(self, params):
            return [_result()]  # always exactly one result, never two

    def relevance_check(claim, results):
        return len(results) >= 1

    origin = find_origin(
        claim, FakeClient(), today=date(2026, 9, 17), relevance_check=relevance_check
    )
    assert origin.confidence == "unresolved"
