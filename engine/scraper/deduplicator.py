"""
engine/scraper/deduplicator.py
Public Conversation Analysis Engine — Cross-Run Deduplication

Fingerprint = SHA-256(source_type + "::" + content_id + "::" + text[:200])

The fingerprint set is persisted to a flat file between runs so that records
already stored in previous runs are never re-processed.

Usage:
    from engine.scraper.deduplicator import Deduplicator
    dedup = Deduplicator()
    if dedup.is_duplicate(record):
        continue
    dedup.mark_seen(record)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from engine.scraper.models import RawRecord
from engine.logger import get_logger

log = get_logger(__name__)

# Fingerprint store persisted between pipeline runs
FINGERPRINT_FILE = Path(__file__).parent.parent / "data" / "dedup_fingerprints.json"


class Deduplicator:
    """
    SHA-256 fingerprint-based deduplication with cross-run persistence.

    Fingerprints are stored in memory during a run and flushed to disk on
    save(). On init, the fingerprints from all previous runs are loaded.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._load()
        log.info(
            "Deduplicator initialized: %d fingerprints loaded from previous runs.",
            len(self._seen),
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def is_duplicate(self, record: RawRecord) -> bool:
        """Return True if this record has been seen before (any run)."""
        fp = self._fingerprint(record)
        return fp in self._seen

    def mark_seen(self, record: RawRecord) -> None:
        """Register a record as seen. Call after writing to the data store."""
        self._seen.add(self._fingerprint(record))

    def record_exists(self, record_id: str) -> bool:
        """
        Lightweight check by record_id prefix.
        Used by the orchestrator for quick ID-based dedup during a run.
        The full fingerprint check (is_duplicate) is more thorough.
        """
        prefix = record_id.split("-")[0]
        return any(fp.startswith(prefix) for fp in self._seen)

    def save(self) -> None:
        """Persist fingerprint set to disk for use in future runs."""
        FINGERPRINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"fingerprints": sorted(self._seen)}
        with FINGERPRINT_FILE.open("w", encoding="utf-8") as fh:
            json.dump(data, fh)
        log.info("Deduplicator: saved %d fingerprints to %s", len(self._seen), FINGERPRINT_FILE)

    @property
    def seen_count(self) -> int:
        return len(self._seen)

    # ── Internal ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if FINGERPRINT_FILE.exists():
            try:
                with FINGERPRINT_FILE.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._seen = set(data.get("fingerprints", []))
            except Exception as exc:
                log.warning("Deduplicator: failed to load fingerprints (%s); starting fresh.", exc)
                self._seen = set()
        else:
            self._seen = set()

    @staticmethod
    def _fingerprint(record: RawRecord) -> str:
        """
        Compute fingerprint as per implementation-plan.md §2.4:
            hash(source_type + content_id + text[:200])
        """
        raw_key = (
            record.source_type
            + "::"
            + record.content_id
            + "::"
            + record.text[:200]
        )
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
