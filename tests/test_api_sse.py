import json

from patientzero_api.sse import format_sse_event


def test_format_sse_event_produces_valid_sse_wire_format():
    formatted = format_sse_event("progress", {"stage": "atomizing"})
    lines = formatted.split("\n")
    assert lines[0] == "event: progress"
    assert lines[1].startswith("data: ")
    assert json.loads(lines[1][len("data: "):]) == {"stage": "atomizing"}
    assert formatted.endswith("\n\n")


def test_format_sse_event_handles_nested_and_unicode_data():
    formatted = format_sse_event("report", {"claims": [{"text": "दावा"}]})
    data_line = formatted.split("\n")[1]
    payload = json.loads(data_line[len("data: "):])
    assert payload["claims"][0]["text"] == "दावा"
