"""
engine/analyzer/grouper.py
Public Conversation Analysis Engine — Signal Grouper

Groups individual Signal records into candidate opportunity clusters.

Strategy:
1. Primary Grouping: Group signals by `taxonomy_node`
2. Sibling Merging:
   - Identify taxonomy nodes within the same dimension that share high overlap in
     question references and conceptual focus.
   - Sibling clusters with smaller signal volumes or tightly coupled semantics
     (e.g., fit_sizing.size_uncertainty + fit_sizing.inconsistent_sizing) can be
     merged into a unified candidate cluster when appropriate, or retained as focused
     clusters when volume warrants.
3. Output: A list of `CandidateCluster` objects containing grouped signals.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from engine.config_loader import TaxonomyConfig
from engine.extractor.models import Signal
from engine.logger import get_logger

log = get_logger(__name__)


@dataclass
class CandidateCluster:
    """A cluster of related signals representing a candidate opportunity."""
    cluster_id: str
    dimension: str
    taxonomy_nodes: list[str]
    signals: list[Signal] = field(default_factory=list)

    @property
    def signal_count(self) -> int:
        return len(self.signals)

    @property
    def distinct_source_types(self) -> set[str]:
        return {s.source_ref.source_type for s in self.signals if s.source_ref and s.source_ref.source_type}


class SignalGrouper:
    """
    Groups signals by taxonomy node and merges related sibling nodes into candidate clusters.
    """

    def __init__(self, taxonomy: Optional[TaxonomyConfig] = None) -> None:
        self.taxonomy = taxonomy

    def group(self, signals: list[Signal]) -> list[CandidateCluster]:
        """
        Group a list of Signals into CandidateClusters.

        Args:
            signals: Raw list of Signal records from the extraction layer.

        Returns:
            List of CandidateCluster instances.
        """
        if not signals:
            log.info("SignalGrouper: 0 signals provided to group.")
            return []

        # 1. Bucket by taxonomy_node
        node_buckets: dict[str, list[Signal]] = defaultdict(list)
        for sig in signals:
            node_buckets[sig.taxonomy_node].append(sig)

        log.info(
            "SignalGrouper: bucketed %d signals into %d distinct taxonomy nodes.",
            len(signals), len(node_buckets),
        )

        # 2. Build candidate clusters
        # Group by (dimension, sub_category / node)
        clusters: list[CandidateCluster] = []

        for node_id, node_signals in sorted(node_buckets.items()):
            if not node_signals:
                continue

            dim = node_signals[0].dimension
            cluster = CandidateCluster(
                cluster_id=f"cluster_{node_id}",
                dimension=dim,
                taxonomy_nodes=[node_id],
                signals=node_signals,
            )
            clusters.append(cluster)

        log.info("SignalGrouper: created %d candidate clusters.", len(clusters))
        return clusters
