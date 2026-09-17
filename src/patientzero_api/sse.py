"""Formats (event, data) pairs into the Server-Sent Events wire format:
"event: <name>\\ndata: <json>\\n\\n" — the blank line after the data line is
what tells the browser's EventSource one event has ended.
"""
import json


def format_sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
