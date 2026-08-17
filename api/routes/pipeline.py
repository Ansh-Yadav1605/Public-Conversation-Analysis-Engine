"""
api/routes/pipeline.py
Public Conversation Analysis Engine — Pipeline Trigger Routes

Provides two endpoints:
    POST /api/run              → enqueue a full pipeline run as a background task
    GET  /api/status/{job_id} → poll job state

Job state machine:
    pending → running → done
                      → failed (with error message)

Job store is in-memory (dict). This is intentional for the graduation-project
scale (single Railway instance, infrequent runs). For production, swap the
dict for a Redis-backed Celery queue and the Railway Redis add-on.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from engine.logger import get_logger

log = get_logger("api.pipeline")

router = APIRouter(tags=["pipeline"])

# ---------------------------------------------------------------------------
# In-memory job store  (key: job_id, value: job state dict)
# ---------------------------------------------------------------------------

jobs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_pipeline_task(job_id: str) -> None:
    """Run the full pipeline in the background and update the job store."""
    jobs[job_id] = {"status": "running"}
    log.info("Pipeline job %s started.", job_id)
    try:
        # Import here so the API server starts fast even if engine deps are
        # slow to import (e.g. heavy ML packages).
        from run_pipeline import run_full_pipeline  # type: ignore[import]

        summary = run_full_pipeline()
        jobs[job_id] = {"status": "done", "summary": summary}
        log.info("Pipeline job %s completed successfully.", job_id)
    except Exception as exc:  # noqa: BLE001
        jobs[job_id] = {"status": "failed", "error": str(exc)}
        log.error("Pipeline job %s failed: %s", job_id, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/run",
    summary="Trigger a full pipeline run",
    response_description="Job ID for polling status",
)
async def trigger_run(background_tasks: BackgroundTasks) -> dict[str, str]:
    """
    Enqueue a full end-to-end pipeline run (scrape → extract → analyze → export).

    Returns a `job_id` immediately. Poll `GET /api/status/{job_id}` to track
    progress.

    **Note:** Running two jobs concurrently against the same data directory is
    not recommended on a single Railway instance.
    """
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending"}
    background_tasks.add_task(_run_pipeline_task, job_id)
    log.info("Pipeline job %s enqueued.", job_id)
    return {"job_id": job_id}


@router.get(
    "/status/{job_id}",
    summary="Poll pipeline job status",
    response_description="Job state: pending | running | done | failed | not_found",
)
async def get_status(job_id: str) -> dict[str, Any]:
    """
    Return the current state of a pipeline job.

    Possible `status` values:
    - `pending`   — queued, not yet started
    - `running`   — currently executing
    - `done`      — completed; `summary` field contains phase metrics
    - `failed`    — errored; `error` field contains the exception message
    - `not_found` — unknown job_id
    """
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"status": "not_found", "job_id": job_id})
    return {"job_id": job_id, **job}


@router.get(
    "/jobs",
    summary="List all known pipeline jobs",
    response_description="Dict of job_id → job state",
)
async def list_jobs() -> dict[str, Any]:
    """Return all jobs currently in the in-memory store (for debugging)."""
    return jobs
