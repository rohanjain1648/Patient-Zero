"""Thin FastAPI wrapper over patientzero.pipeline.run_pipeline. This module
contains no forensics logic of its own — it only wires HTTP <-> the pipeline,
per spec sec 3.
"""
import queue
import threading
import uuid
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from patientzero.llm_client import LLMClient
from patientzero.pipeline import run_pipeline
from patientzero.serp_client import SerpClient
from patientzero_api.serialization import serialize_claim_report
from patientzero_api.sse import format_sse_event
from patientzero_api.store import ReportStore

_DONE = object()


def create_app(serp_client: SerpClient, llm_client: LLMClient, store: ReportStore) -> FastAPI:
    app = FastAPI(title="Patient Zero API")

    @app.get("/api/analyze")
    def analyze(text: str = Query(..., min_length=1)):
        report_id = str(uuid.uuid4())
        events: "queue.Queue" = queue.Queue()

        def on_progress(stage: str, detail: dict) -> None:
            events.put(("progress", {"stage": stage, **detail}))

        def worker() -> None:
            try:
                reports = run_pipeline(
                    text, serp_client, llm_client, today=date.today(), on_progress=on_progress
                )
                store.save(report_id, reports)
                events.put(
                    (
                        "report",
                        {
                            "report_id": report_id,
                            "claims": [serialize_claim_report(r) for r in reports],
                        },
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # run_pipeline already degrades known failure modes (spec sec
                # 6) internally, so reaching here means something unexpected
                # broke. The stream must still terminate rather than hang the
                # HTTP connection open forever with no final event.
                events.put(("error", {"message": str(exc)}))
            finally:
                events.put(_DONE)

        threading.Thread(target=worker, daemon=True).start()

        def stream():
            while True:
                item = events.get()
                if item is _DONE:
                    break
                event, data = item
                yield format_sse_event(event, data)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/reports/{report_id}")
    def get_report(report_id: str):
        reports = store.load(report_id)
        if reports is None:
            raise HTTPException(status_code=404, detail="report not found")
        return {"report_id": report_id, "claims": [serialize_claim_report(r) for r in reports]}

    return app
