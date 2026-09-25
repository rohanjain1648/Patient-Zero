"""Propagation uses two SerpApi engines beyond plain web search (google_news,
google_trends). Every failure mode must degrade to an empty Propagation rather
than abort the claim (spec sec 6), so most of these tests are failure tests.
"""
from datetime import date

import pytest

from patientzero.models import Claim
from patientzero.propagation import (
    build_news_query,
    build_trends_query,
    parse_news_results,
    parse_trend_timeline,
    trace_propagation,
)
from patientzero.serp_client import SerpApiError


class StubSerpClient:
    """Returns a scripted response per engine, and records what it was asked."""

    def __init__(self, by_engine: dict, raises: set | None = None):
        self.by_engine = by_engine
        self.raises = raises or set()
        self.calls = []

    def search(self, params):
        engine = params["engine"]
        self.calls.append(params)
        if engine in self.raises:
            raise SerpApiError(f"{engine} exploded")
        return self.by_engine.get(engine, {})


CLAIM = Claim(text="The Great Wall is visible from space", index=0)

NEWS_RESPONSE = {
    "news_results": [
        {
            "title": "Astronauts say otherwise",
            "link": "https://example.com/a",
            "source": {"name": "Example News"},
            "iso_date": "2016-07-04T07:00:00Z",
        },
        {
            "title": "A second story",
            "link": "https://other.org/b",
            "source": {"name": "Other Org"},
            "date": "07/04/2020, 07:00 AM, +0000 UTC",
        },
    ]
}

TRENDS_RESPONSE = {
    "interest_over_time": {
        "timeline_data": [
            {"date": "Jan 2004", "timestamp": "1072915200", "values": [{"extracted_value": 0}]},
            {"date": "Jun 2016", "timestamp": "1464739200", "values": [{"extracted_value": 91}]},
            {"date": "Jul 2016", "timestamp": "1467331200", "values": [{"extracted_value": 40}]},
        ]
    }
}


def test_build_news_query_targets_the_news_engine():
    params = build_news_query(CLAIM)
    assert params["engine"] == "google_news"
    assert params["q"] == CLAIM.text


def test_build_trends_query_asks_for_a_full_history_timeseries():
    params = build_trends_query(CLAIM)
    assert params["engine"] == "google_trends"
    assert params["data_type"] == "TIMESERIES"
    # Without the full window we cannot show interest predating the origin.
    assert params["date"] == "all"


def test_parse_news_results_reads_both_date_shapes():
    mentions = parse_news_results(NEWS_RESPONSE)
    assert [m.date for m in mentions] == ["2016-07-04", "2020-07-04"]
    assert [m.source for m in mentions] == ["Example News", "Other Org"]
    assert {m.medium for m in mentions} == {"news"}


def test_parse_news_results_keeps_an_undated_item_rather_than_dropping_it():
    mentions = parse_news_results({"news_results": [{"title": "t", "link": "l"}]})
    assert len(mentions) == 1
    assert mentions[0].date is None
    assert mentions[0].source == ""


def test_parse_trend_timeline_extracts_points_in_order():
    points = parse_trend_timeline(TRENDS_RESPONSE)
    assert [p.value for p in points] == [0, 91, 40]
    assert points[1].timestamp == 1464739200
    assert points[1].date == "Jun 2016"


def test_parse_trend_timeline_survives_a_malformed_payload():
    assert parse_trend_timeline({}) == []
    assert parse_trend_timeline({"interest_over_time": {"timeline_data": [{}]}}) == []


def test_trace_propagation_combines_both_engines_and_finds_the_peak():
    client = StubSerpClient({"google_news": NEWS_RESPONSE, "google_trends": TRENDS_RESPONSE})
    prop = trace_propagation(CLAIM, client)

    assert len(prop.mentions) == 2
    assert len(prop.trend) == 3
    # Jun 2016 is the 91 — the maximum.
    assert prop.peak_date == "2016-06-01"
    assert {c["engine"] for c in client.calls} == {"google_news", "google_trends"}


def test_trace_propagation_degrades_to_empty_when_every_engine_fails():
    client = StubSerpClient({}, raises={"google_news", "google_trends"})
    prop = trace_propagation(CLAIM, client)

    assert prop.mentions == []
    assert prop.trend == []
    assert prop.peak_date is None


def test_trace_propagation_keeps_the_engine_that_worked_when_the_other_fails():
    """A Trends outage must not cost us the News timeline, and vice versa."""
    client = StubSerpClient({"google_news": NEWS_RESPONSE}, raises={"google_trends"})
    prop = trace_propagation(CLAIM, client)

    assert len(prop.mentions) == 2
    assert prop.trend == []


def test_trace_propagation_reports_progress_per_engine():
    client = StubSerpClient({"google_news": NEWS_RESPONSE, "google_trends": TRENDS_RESPONSE})
    events = []
    trace_propagation(CLAIM, client, on_progress=lambda s, d: events.append((s, d)))

    stages = [s for s, _ in events]
    assert "propagation_engine_complete" in stages
    assert {d["engine"] for _, d in events} == {"google_news", "google_trends"}


def test_trace_propagation_marks_a_failed_engine_in_progress():
    client = StubSerpClient({}, raises={"google_trends", "google_news"})
    events = []
    trace_propagation(CLAIM, client, on_progress=lambda s, d: events.append((s, d)))

    assert all(d["ok"] is False for _, d in events)
