"""
engine/data_store.py
Public Conversation Analysis Engine — Local Data Store Initializer

Manages three flat JSONL stores:
    engine/data/raw_records/   → RawRecord objects (Phase 2 output)
    engine/data/signals/       → Signal objects (Phase 3 output)
    engine/data/opportunities/ → OpportunityArea objects (Phase 4 output)

Each store uses one JSONL file per pipeline run for isolation.
The active store files are referenced via a central manifest (store_manifest.json).

Why JSONL?
    Simple, human-inspectable, append-friendly, and Git-diffable.
    No database daemon required. SQLite can be added in Phase 4-5 if needed.

Usage:
    from engine.data_store import DataStore
    store = DataStore()
    store.write_raw_record(record_dict)
    records = store.read_all_raw_records()
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from engine.logger import get_logger

log = get_logger(__name__)

# ── Store paths ────────────────────────────────────────────────────────────
# ENGINE_DATA_DIR is set by Railway Volume mount (/app/engine/data).
# Falls back to the local path for CLI usage.
DATA_DIR = Path(
    os.environ.get("ENGINE_DATA_DIR", Path(__file__).parent / "data")
)
RAW_RECORDS_DIR = DATA_DIR / "raw_records"
SIGNALS_DIR = DATA_DIR / "signals"
OPPORTUNITIES_DIR = DATA_DIR / "opportunities"

_RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")


class DataStore:
    """
    Simple JSONL-based data store for the three pipeline entity types.

    Each instance scopes all writes to a single timestamped run file.
    Reads always span ALL existing files in the store directory, enabling
    cross-run deduplication and full corpus analysis.
    """

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or _RUN_TS
        self._ensure_dirs()
        self._raw_file = RAW_RECORDS_DIR / f"raw_{self.run_id}.jsonl"
        self._signal_file = SIGNALS_DIR / f"signals_{self.run_id}.jsonl"
        self._opportunity_file = OPPORTUNITIES_DIR / f"opportunities_{self.run_id}.jsonl"
        log.info("DataStore initialized for run_id=%s", self.run_id)

    def _ensure_dirs(self) -> None:
        for d in (RAW_RECORDS_DIR, SIGNALS_DIR, OPPORTUNITIES_DIR):
            d.mkdir(parents=True, exist_ok=True)

    # ── Raw Records ────────────────────────────────────────────────────────

    def write_raw_record(self, record: dict[str, Any]) -> None:
        """Append one RawRecord dict to the current run's JSONL file."""
        self._append(self._raw_file, record)

    def read_all_raw_records(self) -> list[dict[str, Any]]:
        """Read all RawRecords across all run files."""
        return list(self._iter_all(RAW_RECORDS_DIR))

    def raw_record_ids(self) -> set[str]:
        """Return the set of all record_ids for deduplication checks."""
        return {r["record_id"] for r in self.read_all_raw_records() if "record_id" in r}

    # ── Signals ────────────────────────────────────────────────────────────

    def write_signal(self, signal: dict[str, Any]) -> None:
        """Append one Signal dict to the current run's JSONL file."""
        self._append(self._signal_file, signal)

    def read_all_signals(self) -> list[dict[str, Any]]:
        """Read all Signals across all run files."""
        return list(self._iter_all(SIGNALS_DIR))

    # ── Opportunities ──────────────────────────────────────────────────────

    def write_opportunity(self, opportunity: dict[str, Any]) -> None:
        """Append one OpportunityArea dict to the current run's JSONL file."""
        self._append(self._opportunity_file, opportunity)

    def read_all_opportunities(self) -> list[dict[str, Any]]:
        """Read all OpportunityAreas across all run files."""
        return list(self._iter_all(OPPORTUNITIES_DIR))

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _append(path: Path, obj: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    @staticmethod
    def _iter_all(directory: Path) -> Iterator[dict[str, Any]]:
        for jsonl_file in sorted(directory.glob("*.jsonl")):
            with jsonl_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError as exc:
                            log.warning(
                                "Skipping malformed JSONL line in %s: %s", jsonl_file.name, exc
                            )

    def summary(self) -> dict[str, int]:
        """Return record counts across all stores."""
        return {
            "raw_records": sum(1 for _ in self._iter_all(RAW_RECORDS_DIR)),
            "signals": sum(1 for _ in self._iter_all(SIGNALS_DIR)),
            "opportunities": sum(1 for _ in self._iter_all(OPPORTUNITIES_DIR)),
        }


def init_data_store() -> None:
    """
    Create the data directory structure.
    Called once during Phase 1 setup. Safe to call multiple times (idempotent).
    """
    for d in (RAW_RECORDS_DIR, SIGNALS_DIR, OPPORTUNITIES_DIR):
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
    log.info("Data store directories initialized at: %s", DATA_DIR)
