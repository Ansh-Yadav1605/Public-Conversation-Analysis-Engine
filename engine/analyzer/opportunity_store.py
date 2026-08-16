"""
engine/analyzer/opportunity_store.py
Public Conversation Analysis Engine — Opportunity Store

High-level interface over DataStore for storing and querying OpportunityArea records.

Usage:
    from engine.analyzer.opportunity_store import OpportunityStore
    store = OpportunityStore()
    store.write_batch(opportunities)
    top_5 = store.top_k(5)
    by_dim = store.by_dimension("Fit & Sizing")
"""

from __future__ import annotations

from typing import Optional

from engine.analyzer.models import OpportunityArea
from engine.data_store import DataStore
from engine.logger import get_logger

log = get_logger(__name__)


class OpportunityStore:
    """
    Persistence and query layer for OpportunityArea records.
    """

    def __init__(self, run_id: Optional[str] = None) -> None:
        self._store = DataStore(run_id=run_id)

    def write(self, opportunity: OpportunityArea) -> None:
        """Persist a single OpportunityArea."""
        self._store.write_opportunity(opportunity.to_dict())

    def write_batch(self, opportunities: list[OpportunityArea]) -> None:
        """Persist a list of OpportunityArea instances."""
        for op in opportunities:
            self._store.write_opportunity(op.to_dict())
        log.info("OpportunityStore: wrote %d opportunities to store.", len(opportunities))

    def read_all(self) -> list[OpportunityArea]:
        """Read all OpportunityArea records across all pipeline runs."""
        raw_list = self._store.read_all_opportunities()
        opportunities: list[OpportunityArea] = []
        for item in raw_list:
            try:
                opportunities.append(OpportunityArea.from_dict(item))
            except Exception as exc:
                log.warning("OpportunityStore: skipping malformed record: %s", exc)
        return opportunities

    def count(self) -> int:
        """Total opportunity count."""
        return len(self.read_all())

    def by_dimension(self, dimension: str) -> list[OpportunityArea]:
        """Filter opportunities by dimension."""
        return [op for op in self.read_all() if op.dimension.lower() == dimension.lower()]

    def by_question(self, question_id: int) -> list[OpportunityArea]:
        """Filter opportunities that help answer a specific behavioral question ID (1-10)."""
        return [op for op in self.read_all() if question_id in op.question_answers]

    def top_k(self, k: int = 5) -> list[OpportunityArea]:
        """Return the top K ranked opportunities."""
        all_ops = self.read_all()
        # Sort by rank ascending (1 is top), or composite score descending
        sorted_ops = sorted(
            all_ops,
            key=lambda op: (op.rank if op.rank is not None else 999999, -op.scores.composite),
        )
        return sorted_ops[:k]
