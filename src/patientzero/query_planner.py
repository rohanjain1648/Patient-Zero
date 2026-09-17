"""Builds SerpApi query param dicts for the two query shapes the pipeline needs:
date-restricted (for bisection) and locale-targeted (for cross-lingual asymmetry).
"""
from datetime import date

from patientzero.models import Claim


def build_date_restricted_query(
    claim: Claim, min_date: date | None, max_date: date | None
) -> dict:
    params = {"engine": "google", "q": claim.text}
    if min_date is not None and max_date is not None:
        params["tbs"] = (
            f"cdr:1,cd_min:{min_date.strftime('%m/%d/%Y')},"
            f"cd_max:{max_date.strftime('%m/%d/%Y')}"
        )
    return params


def build_locale_query(claim: Claim, hl: str, gl: str = "in") -> dict:
    return {"engine": "google", "q": claim.text, "hl": hl, "gl": gl}
