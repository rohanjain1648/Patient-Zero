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

app = create_app(
    serp_client=build_serp_client(
        cache_db_path=os.path.join(_data_dir, "cache.db"),
        mock_dir=os.environ.get("SERPAPI_MOCK_DIR"),
    ),
    llm_client=build_llm_client(),
    store=ReportStore(os.path.join(_data_dir, "reports.db")),
    cors_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
)
