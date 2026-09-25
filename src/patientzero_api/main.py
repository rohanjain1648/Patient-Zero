"""Uvicorn entrypoint: `uvicorn patientzero_api.main:app`. Reads config from
the environment (optionally a .env file) and wires the real clients."""
import os

from dotenv import load_dotenv

from patientzero_api.app import create_app
from patientzero_api.clients import build_llm_client, build_serp_client
from patientzero_api.store import ReportStore

load_dotenv()

_data_dir = os.environ.get("PATIENTZERO_DATA_DIR", "data")
os.makedirs(_data_dir, exist_ok=True)

_cors = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
_store = ReportStore(os.path.join(_data_dir, "reports.db"))

# A missing key is not a crash: without credentials the API still starts and
# serves the recorded demo session, so `git clone && uvicorn ...` works for
# someone evaluating the repo who has no keys of their own.
try:
    _serp_client = build_serp_client(
        cache_db_path=os.path.join(_data_dir, "cache.db"),
        mock_dir=os.environ.get("SERPAPI_MOCK_DIR"),
    )
    _llm_client = build_llm_client()
    _demo_only = False
except RuntimeError as exc:
    print(f"[patientzero] starting in DEMO MODE (no live analysis): {exc}")
    _serp_client, _llm_client, _demo_only = None, None, True

app = create_app(
    serp_client=_serp_client,
    llm_client=_llm_client,
    store=_store,
    cors_origins=_cors,
    demo_only=_demo_only,
)
