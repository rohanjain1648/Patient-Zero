"""Zero-key demo mode.

A judge should be able to clone the repo, install, start the server and see a
full analysis without owning a SerpApi key, a Groq key or an OpenAI key — and
without spending anyone's credits. This module replays a session recorded from
a real run (scripts/record_demo.py) at its original pacing, so the SSE stream a
judge watches is the same shape as a live one.

This is a presentation path, never a substitute for analysis: it only ever
replays bytes captured from a real run, and the UI labels the stream as a
replay.
"""
import json
import time
from pathlib import Path

DEFAULT_SESSION_PATH = Path(__file__).parent / "demo_session.json"

# Recorded runs take tens of seconds, most of it network wait. Replaying that
# verbatim would make the demo video mostly dead air, so gaps are scaled down
# and clamped — fast enough to hold attention, slow enough that a viewer can
# read each stage as it lands.
REPLAY_SPEED = 4.0
MAX_GAP_SECONDS = 1.2
MIN_GAP_SECONDS = 0.08


class DemoSessionUnavailable(Exception):
    pass


def load_session(path: Path | str = DEFAULT_SESSION_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        raise DemoSessionUnavailable(f"no recorded demo session at {path}")
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DemoSessionUnavailable(f"demo session at {path} is unreadable: {exc}") from exc

    if not isinstance(session.get("events"), list) or not session["events"]:
        raise DemoSessionUnavailable(f"demo session at {path} has no events")
    return session


def replay_events(session: dict, sleep=time.sleep):
    """Yields (event_name, data) pairs in recorded order, pausing between them
    in proportion to the original run's timing.
    """
    previous_offset = 0.0
    for entry in session["events"]:
        offset = float(entry.get("offset", previous_offset))
        gap = (offset - previous_offset) / REPLAY_SPEED
        previous_offset = offset
        if gap > 0:
            sleep(max(MIN_GAP_SECONDS, min(gap, MAX_GAP_SECONDS)))
        yield entry["event"], entry["data"]
