"""
api/routes/results.py
Public Conversation Analysis Engine — Results & Config Routes

Provides read-only access to pipeline outputs:
    GET /api/results  → ranked OpportunityArea list (JSON-serialisable dicts)
    GET /api/signals  → all Signal records
    GET /api/config   → current taxonomy + question set (from YAML configs)

These endpoints read from the same JSONL stores that the pipeline writes to,
so they always reflect the most recent completed run.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from engine.analyzer.opportunity_store import OpportunityStore
from engine.config_loader import load_all_config
from engine.extractor.signal_store import SignalStore
from engine.logger import get_logger

log = get_logger("api.results")

router = APIRouter(tags=["results"])


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------


@router.get(
    "/results",
    summary="Get ranked opportunity areas",
    response_description="List of OpportunityArea objects sorted by rank",
)
async def get_results() -> list[dict[str, Any]]:
    """
    Return all `OpportunityArea` records from the most recent completed
    pipeline run, sorted by rank (ascending; rank 1 = best opportunity).

    Returns an empty list if no pipeline run has been completed yet.
    """
    try:
        store = OpportunityStore()
        opportunities = store.read_all()
        # Sort by rank ascending; fall back to composite score descending
        sorted_opps = sorted(
            opportunities,
            key=lambda op: (
                op.rank if op.rank is not None else 999_999,
                -(op.scores.composite if op.scores else 0.0),
            ),
        )
        return [op.to_dict() for op in sorted_opps]
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to read results: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read results: {exc}") from exc


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


@router.get(
    "/signals",
    summary="Get all signal records",
    response_description="List of Signal objects",
)
async def get_signals() -> list[dict[str, Any]]:
    """
    Return all `Signal` records across all pipeline runs.

    Signals are the atomic evidence units extracted from public conversation
    data. Each signal maps to one verbatim quote + source reference.
    """
    try:
        store = SignalStore()
        signals = store.read_all()
        return [s.to_dict() for s in signals]
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to read signals: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read signals: {exc}") from exc


# ---------------------------------------------------------------------------
# Config (read-only taxonomy + question set)
# ---------------------------------------------------------------------------


@router.get(
    "/config",
    summary="Get current taxonomy and question set",
    response_description="Parsed config from engine/config/*.yaml",
)
async def get_config() -> dict[str, Any]:
    """
    Return the current taxonomy and behavioural question set loaded from
    `engine/config/source_list.yaml` and `engine/config/question_set.yaml`.

    This is read-only; changing the YAML files requires a redeploy.
    """
    try:
        cfg = load_all_config()
        # load_all_config returns a dataclass/namespace — convert to plain dict
        if hasattr(cfg, "__dict__"):
            return cfg.__dict__
        return dict(cfg)  # type: ignore[call-overload]
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to load config: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load config: {exc}") from exc
