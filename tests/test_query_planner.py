from datetime import date

from patientzero.models import Claim
from patientzero.query_planner import build_date_restricted_query, build_locale_query


def test_date_restricted_query_includes_tbs_range():
    claim = Claim(text="Water causes floods", index=0)
    params = build_date_restricted_query(
        claim, min_date=date(2018, 1, 1), max_date=date(2019, 1, 1)
    )
    assert params["q"] == "Water causes floods"
    assert params["tbs"] == "cdr:1,cd_min:01/01/2018,cd_max:01/01/2019"
    assert params["engine"] == "google"


def test_date_restricted_query_omits_tbs_when_no_bounds_given():
    claim = Claim(text="Unrestricted claim", index=0)
    params = build_date_restricted_query(claim, min_date=None, max_date=None)
    assert "tbs" not in params


def test_locale_query_sets_hl_and_gl():
    claim = Claim(text="Local claim", index=0)
    params = build_locale_query(claim, hl="hi", gl="in")
    assert params["hl"] == "hi"
    assert params["gl"] == "in"
    assert params["q"] == "Local claim"


def test_locale_query_defaults_gl_to_india():
    claim = Claim(text="Default gl claim", index=0)
    params = build_locale_query(claim, hl="en")
    assert params["gl"] == "in"
