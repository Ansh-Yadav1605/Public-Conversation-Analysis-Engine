"""
api/main.py
Public Conversation Analysis Engine — FastAPI Application Entry Point

Exposes the pipeline as an HTTP API so the Vercel frontend (or any HTTP
client) can trigger runs and read results without touching the CLI.

Endpoints registered here:
    GET  /health          → liveness check for Railway uptime monitoring
    POST /api/run         → trigger a full pipeline run (background task)
    GET  /api/status/{id} → poll job state: pending → running → done/failed
    GET  /api/results     → ranked OpportunityArea list from last run
    GET  /api/signals     → all Signal records (evidence view)
    GET  /api/config      → current taxonomy + question set (read-only)

Run locally:
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.pipeline import router as pipeline_router
from api.routes.results import router as results_router

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Public Conversation Analysis Engine",
    description=(
        "HTTP API wrapper around the three-stage Python pipeline "
        "(scrape → extract → analyze → export)."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow Vercel frontend + local dev
# ---------------------------------------------------------------------------

_VERCEL_ORIGIN = os.environ.get(
    "VERCEL_URL",
    "https://your-project.vercel.app",  # replace after first Vercel deploy
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        _VERCEL_ORIGIN,
        "http://localhost:3000",  # Next.js local dev
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(pipeline_router, prefix="/api")
app.include_router(results_router, prefix="/api")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"], summary="Liveness check")
async def health() -> dict:
    """Returns 200 OK when the service is up. Used by Railway uptime monitoring."""
    return {"status": "ok", "version": "0.1.0"}
