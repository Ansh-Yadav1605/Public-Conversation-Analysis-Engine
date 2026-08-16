"""
engine/analyzer/validator.py
Public Conversation Analysis Engine — Cross-Source Validator

Filters candidate clusters by requiring evidence across independent source types.

Rule:
    A candidate cluster must contain signals from >= `min_sources` (default: 2)
    distinct source types (e.g. reddit + app_store) to be validated.

Rationale:
    Signals appearing on only a single platform risk being artifacts of platform-specific
    culture, UI bugs, or review bombing rather than fundamental user behavioral friction.
"""

from __future__ import annotations

from dataclasses import dataclass
from engine.analyzer.grouper import CandidateCluster
from engine.logger import get_logger

log = get_logger(__name__)

DEFAULT_MIN_SOURCES = 2


@dataclass
class ValidationResult:
    """Validation summary for a clustering run."""
    passed_clusters: list[CandidateCluster]
    rejected_clusters: list[CandidateCluster]
    min_sources: int

    @property
    def total_candidates(self) -> int:
        return len(self.passed_clusters) + len(self.rejected_clusters)


class CrossSourceValidator:
    """
    Enforces cross-source evidence thresholds on candidate opportunity clusters.
    """

    def __init__(self, min_sources: int = DEFAULT_MIN_SOURCES) -> None:
        self.min_sources = max(1, min_sources)

    def validate(self, clusters: list[CandidateCluster]) -> ValidationResult:
        """
        Filter candidate clusters based on source diversity.

        Args:
            clusters: List of candidate clusters from SignalGrouper.

        Returns:
            ValidationResult containing passed and rejected clusters.
        """
        passed: list[CandidateCluster] = []
        rejected: list[CandidateCluster] = []

        for cluster in clusters:
            sources = cluster.distinct_source_types
            source_count = len(sources)

            if source_count >= self.min_sources:
                log.debug(
                    "Cluster '%s' PASSED validation (%d source types: %s).",
                    cluster.cluster_id, source_count, sorted(sources),
                )
                passed.append(cluster)
            else:
                log.info(
                    "Cluster '%s' REJECTED (insufficient cross-source evidence: %d < %d source types: %s).",
                    cluster.cluster_id, source_count, self.min_sources, sorted(sources),
                )
                rejected.append(cluster)

        log.info(
            "CrossSourceValidator: %d/%d clusters passed (min_sources=%d).",
            len(passed), len(clusters), self.min_sources,
        )
        return ValidationResult(
            passed_clusters=passed,
            rejected_clusters=rejected,
            min_sources=self.min_sources,
        )
