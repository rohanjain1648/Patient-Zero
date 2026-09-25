"""Records a real analysis run to src/patientzero_api/demo_session.json.

The recorded file is what zero-key demo mode replays, so it must always come
from a genuine run against live SerpApi + LLM providers — never hand-written.
Run it with your keys in .env:

    python scripts/record_demo.py "Some claim to analyse"

Every call still goes through the cache, so re-recording the same claim costs
no additional SerpApi credits.
"""
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from patientzero.pipeline import run_pipeline  # noqa: E402
from patientzero_api.clients import build_llm_client, build_serp_client  # noqa: E402
from patientzero_api.serialization import serialize_claim_report  # noqa: E402

OUTPUT_PATH = ROOT / "src" / "patientzero_api" / "demo_session.json"

DEFAULT_CLAIM = "The Great Wall of China is visible from space with the naked eye."


def main() -> int:
    claim_text = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CLAIM

    os.makedirs(ROOT / "data", exist_ok=True)
    serp_client = build_serp_client(cache_db_path=str(ROOT / "data" / "cache.db"))
    llm_client = build_llm_client()

    started = time.monotonic()
    events = []

    def on_progress(stage: str, detail: dict) -> None:
        events.append(
            {
                "event": "progress",
                "offset": round(time.monotonic() - started, 3),
                "data": {"stage": stage, **detail},
            }
        )
        print(f"  {time.monotonic() - started:6.1f}s  {stage} {detail}")

    print(f"Recording: {claim_text!r}")
    reports = run_pipeline(
        claim_text, serp_client, llm_client, today=date.today(), on_progress=on_progress
    )

    events.append(
        {
            "event": "report",
            "offset": round(time.monotonic() - started, 3),
            "data": {
                "report_id": "demo",
                "claims": [serialize_claim_report(r) for r in reports],
            },
        }
    )

    session = {
        "claim": claim_text,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_seconds": round(time.monotonic() - started, 1),
        "serpapi_usage": getattr(serp_client, "usage", {}),
        "events": events,
    }
    OUTPUT_PATH.write_text(json.dumps(session, indent=2), encoding="utf-8")

    print(f"\nWrote {OUTPUT_PATH.relative_to(ROOT)}")
    print(f"  {len(reports)} claim report(s), {len(events)} events, "
          f"{session['duration_seconds']}s, SerpApi {session['serpapi_usage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
