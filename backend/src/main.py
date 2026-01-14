from . import compat  # noqa: F401  # ensures runtime patches run before FastAPI import

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .planner.router import router as planner_router
from .planner.services import metrics as metrics_service
from .security.ip_allowlist import IPAllowlistMiddleware

app = FastAPI(title="AI Costing Planner API", version="0.1.0")

app.add_middleware(
    IPAllowlistMiddleware,
    allowlist_raw=settings.planner_ip_allowlist,
    trust_proxy_headers=settings.planner_trust_proxy_headers,
    # Keep health open for basic monitoring; everything else can be restricted.
    exclude_paths=["/api/health"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(planner_router, prefix=settings.planner_api_prefix)
if settings.metrics_enabled:
    app.include_router(metrics_service.router)


@app.get("/api/health", tags=["Health"])
def api_health():
    return {"status": "ok"}
