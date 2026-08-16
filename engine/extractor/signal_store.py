"""
engine/extractor/signal_store.py
Public Conversation Analysis Engine — Signal Store

Thin wrapper around DataStore for Signal-specific operations.
Provides convenience methods for reading, writing, and querying signals
without coupling the rest of the extractor to DataStore internals.

Usage:
    from engine.extractor.signal_store import SignalStore
    store = SignalStore(run_id="20260816_180000")
    store.write(signal)
    all_signals = store.read_all()
    by_dim = store.by_dimension("Fit & Sizing")
"""

from __future__ import annotations

from engine.data_store import DataStore
from engine.extractor.models import Signal
from engine.logger import get_logger

log = get_logger(__name__)


class SignalStore:
    """
    Signal-specific access layer over DataStore.

    The underlying storage is the JSONL signal files in engine/data/signals/.
    """

    def __init__(self, run_id: str | None = None) -> None:
        self._store = DataStore(run_id=run_id)

    def write(self, signal: Signal) -> None:
        """Persist one Signal record."""
        self._store.write_signal(signal.to_dict())

    def read_all(self) -> list[Signal]:
        """Read all Signal records across all runs."""
        results = []
        for d in self._store.read_all_signals():
            try:
                results.append(Signal.from_dict(d))
            except Exception as exc:
                log.warning("Skipping malformed Signal record: %s", exc)
        return results

    def count(self) -> int:
        return len(self.read_all())

    def by_dimension(self, dimension: str) -> list[Signal]:
        return [s for s in self.read_all() if s.dimension == dimension]

    def by_taxonomy_node(self, node_id: str) -> list[Signal]:
        return [s for s in self.read_all() if s.taxonomy_node == node_id]

    def by_record_id(self, record_id: str) -> list[Signal]:
        return [s for s in self.read_all() if s.record_id == record_id]

    def dimensions_present(self) -> list[str]:
        """Return the unique dimensions that have at least one signal."""
        seen: set[str] = set()
        return [
            s.dimension for s in self.read_all()
            if s.dimension not in seen and not seen.add(s.dimension)  # type: ignore
        ]

    def source_types_present(self) -> list[str]:
        """Return the unique source types that have at least one signal."""
        seen: set[str] = set()
        return [
            s.source_ref.source_type for s in self.read_all()
            if s.source_ref.source_type not in seen and not seen.add(s.source_ref.source_type)  # type: ignore
        ]

    def average_confidence(self) -> float:
        """Compute average confidence across all signals."""
        signals = self.read_all()
        if not signals:
            return 0.0
        return sum(s.confidence for s in signals) / len(signals)
