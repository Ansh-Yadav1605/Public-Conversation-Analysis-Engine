"""
engine/analyzer/ranker.py
Public Conversation Analysis Engine — Opportunity Ranker

Ranks OpportunityArea records by their composite priority scores.

Strategy:
- Primary sort: `scores.composite` descending
- Secondary sort (tie-breaker): `scores.severity` descending
- Tertiary sort: `signal_count` descending
- Assign sequential 1-based rank (`rank = 1` is top priority)
"""

from __future__ import annotations

from engine.analyzer.models import OpportunityArea
from engine.logger import get_logger

log = get_logger(__name__)


class OpportunityRanker:
    """
    Sorts and assigns priority ranks to OpportunityArea instances.
    """

    @staticmethod
    def rank(opportunities: list[OpportunityArea]) -> list[OpportunityArea]:
        """
        Sort and rank OpportunityArea records in descending order of priority.

        Args:
            opportunities: List of scored OpportunityArea instances.

        Returns:
            Sorted list with 1-based rank assigned to each opportunity.
        """
        if not opportunities:
            return []

        # Sort descending by composite score, then severity, then signal count
        sorted_ops = sorted(
            opportunities,
            key=lambda op: (
                op.scores.composite,
                op.scores.severity,
                op.signal_count,
            ),
            reverse=True,
        )

        # Assign 1-based rank
        for idx, op in enumerate(sorted_ops, start=1):
            op.rank = idx

        log.info(
            "OpportunityRanker: ranked %d opportunities (top score: %.4f, rank 1: '%s').",
            len(sorted_ops),
            sorted_ops[0].scores.composite if sorted_ops else 0.0,
            sorted_ops[0].title if sorted_ops else "None",
        )
        return sorted_ops
