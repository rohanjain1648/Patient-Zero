"""Propagation tracing: how a claim spread beyond plain web search.

Web search alone tells us a claim exists and roughly when it was first indexed.
It does not tell us when people actually *noticed*, or whether the claim jumped
media types. This module adds two more SerpApi engines for that:

  - google_news   -> dated, source-attributed articles (the propagation trail)
  - google_trends -> public search interest over time (the attention curve)

Overlaying the bisected origin date on the attention curve is the point: a claim
that originated years before its interest peak propagated slowly; one whose peak
sits on the origin date arrived fully formed, which is the signature of a
coordinated push rather than organic spread.

Per spec sec 6 every engine here is optional: a failure degrades to an empty
field and the claim's report still ships.
"""
from datetime import datetime, timezone

from patientzero.models import Claim, MediaMention, Propagation, TrendPoint
from patientzero.serp_client import SerpApiError

# Enough to show a trail without spending the credit budget on breadth.
MAX_NEWS_MENTIONS = 8


def build_news_query(claim: Claim, hl: str = "en", gl: str = "in") -> dict:
    return {"engine": "google_news", "q": claim.text, "hl": hl, "gl": gl}


def build_trends_query(claim: Claim) -> dict:
    # date="all" reaches back to 2004. A narrower window would hide the very
    # interest spike we are trying to line up against the origin date.
    return {
        "engine": "google_trends",
        "q": claim.text,
        "data_type": "TIMESERIES",
        "date": "all",
    }


def _parse_news_date(item: dict) -> str | None:
    """google_news gives either an ISO `iso_date` or a US-formatted `date`
    string like "07/04/2026, 07:00 AM, +0000 UTC". Neither is guaranteed.
    """
    iso = item.get("iso_date")
    if iso:
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass

    raw = item.get("date")
    if raw:
        head = raw.split(",")[0].strip()
        try:
            return datetime.strptime(head, "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass

    return None


def parse_news_results(raw: dict) -> list[MediaMention]:
    mentions = []
    for item in raw.get("news_results", [])[:MAX_NEWS_MENTIONS]:
        source = item.get("source") or {}
        mentions.append(
            MediaMention(
                medium="news",
                title=item.get("title", ""),
                link=item.get("link", ""),
                source=source.get("name", "") if isinstance(source, dict) else str(source),
                date=_parse_news_date(item),
            )
        )
    return mentions


def parse_trend_timeline(raw: dict) -> list[TrendPoint]:
    points = []
    for item in raw.get("interest_over_time", {}).get("timeline_data", []):
        values = item.get("values") or []
        timestamp = item.get("timestamp")
        if not values or timestamp is None:
            # A point without a value or an x-coordinate cannot be plotted.
            continue
        try:
            points.append(
                TrendPoint(
                    date=item.get("date", ""),
                    timestamp=int(timestamp),
                    value=int(values[0].get("extracted_value", 0)),
                )
            )
        except (TypeError, ValueError):
            continue
    return points


def _peak_date(points: list[TrendPoint]) -> str | None:
    if not points:
        return None
    peak = max(points, key=lambda p: p.value)
    if peak.value <= 0:
        # A flat-zero curve has no meaningful peak to report.
        return None
    return datetime.fromtimestamp(peak.timestamp, tz=timezone.utc).date().isoformat()


def trace_propagation(claim: Claim, serp_client, on_progress=None) -> Propagation:
    if on_progress is None:
        on_progress = lambda stage, detail: None  # noqa: E731

    def _run(engine: str, params: dict, parse):
        """Each engine is independently optional: one going down must not cost
        us the other's data, so failures are swallowed per engine, not in one
        try block around both.
        """
        try:
            parsed = parse(serp_client.search(params))
            on_progress("propagation_engine_complete", {"engine": engine, "ok": True})
            return parsed
        except (SerpApiError, KeyError, TypeError, ValueError):
            on_progress("propagation_engine_complete", {"engine": engine, "ok": False})
            return []

    mentions = _run("google_news", build_news_query(claim), parse_news_results)
    trend = _run("google_trends", build_trends_query(claim), parse_trend_timeline)

    return Propagation(trend=trend, mentions=mentions, peak_date=_peak_date(trend))
