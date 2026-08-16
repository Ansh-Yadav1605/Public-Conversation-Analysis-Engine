"""
engine/analyzer/scorer.py
Public Conversation Analysis Engine — Opportunity Scorer

Calculates the 4 priority scoring dimensions for OpportunityArea records
as specified in implementation-plan.md §4.5 and architecture.md §4.3.3.

Formulas:
1. Frequency Score:
   `min(signal_count / max_signals_in_run, 1.0)` (0.0 if max=0)

2. Severity Score:
   Weighted average of severity hints across all signals in the cluster:
   high = 1.0, medium = 0.6, low = 0.3, unknown = 0.5

3. Evidence Strength Score:
   `(distinct_source_types / 7.0) * avg_confidence_in_cluster`

4. Composite Priority Score:
   `w_frequency * frequency + w_severity * severity + w_evidence_strength * evidence_strength`
   Weights dynamically loaded from scoring_weights.yaml.
"""

from __future__ import annotations

from typing import Optional

from engine.analyzer.grouper import CandidateCluster
from engine.analyzer.models import OpportunityArea, OpportunityScores
from engine.config_loader import ScoringConfig, ScoringWeights
from engine.logger import get_logger

log = get_logger(__name__)

# Severity mapping values from scoring_weights.yaml / architecture.md
_SEVERITY_WEIGHTS = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.3,
    "unknown": 0.5,
}

TOTAL_POSSIBLE_SOURCE_TYPES = 7.0


class OpportunityScorer:
    """
    Computes Frequency, Severity, Evidence Strength, and Composite scores for OpportunityAreas.
    """

    def __init__(self, scoring_config: ScoringConfig) -> None:
        self.config = scoring_config
        self.weights: ScoringWeights = scoring_config.weights

    def score_all(
        self,
        opportunities: list[OpportunityArea],
        clusters: list[CandidateCluster],
    ) -> list[OpportunityArea]:
        """
        Score a list of OpportunityAreas using the corresponding CandidateCluster signal data.

        Args:
            opportunities: List of synthesized OpportunityArea instances.
            clusters: List of CandidateClusters containing the underlying signals.

        Returns:
            List of OpportunityArea instances with populated OpportunityScores.
        """
        if not opportunities or not clusters:
            return opportunities

        # Map cluster_id -> CandidateCluster for lookup
        cluster_map = {c.cluster_id: c for c in clusters}

        # 1. Determine maximum signal count across all opportunity areas in this run
        max_signal_count = max((op.signal_count for op in opportunities), default=1)
        if max_signal_count == 0:
            max_signal_count = 1

        log.info(
            "OpportunityScorer: scoring %d opportunities (max_signal_count=%d).",
            len(opportunities), max_signal_count,
        )

        scored_opportunities: list[OpportunityArea] = []

        for op in opportunities:
            cluster = cluster_map.get(op.opportunity_id)
            if not cluster or not cluster.signals:
                # Default zero scores if no signals
                op.scores = OpportunityScores(
                    frequency=0.0,
                    severity=0.0,
                    evidence_strength=0.0,
                    composite=0.0,
                )
                scored_opportunities.append(op)
                continue

            scores = self.compute_scores(cluster, max_signal_count)
            op.scores = scores
            scored_opportunities.append(op)

        return scored_opportunities

    def compute_scores(
        self, cluster: CandidateCluster, max_signal_count: int
    ) -> OpportunityScores:
        """Calculate the 4 scoring dimensions for a single cluster."""
        signals = cluster.signals
        count = len(signals)

        # 1. Frequency Score: min(count / max_count, 1.0)
        freq_score = min(count / float(max_signal_count), 1.0) if max_signal_count > 0 else 0.0

        # 2. Severity Score: weighted average
        if count > 0:
            total_sev = sum(_SEVERITY_WEIGHTS.get(s.severity_hint, 0.5) for s in signals)
            sev_score = total_sev / float(count)
        else:
            sev_score = 0.0

        # 3. Evidence Strength Score: (distinct_sources / 7.0) * avg_confidence
        distinct_sources = len(cluster.distinct_source_types)
        if count > 0:
            avg_conf = sum(s.confidence for s in signals) / float(count)
        else:
            avg_conf = 0.0

        evidence_score = (distinct_sources / TOTAL_POSSIBLE_SOURCE_TYPES) * avg_conf

        # 4. Composite Score
        composite_score = (
            self.weights.w_frequency * freq_score
            + self.weights.w_severity * sev_score
            + self.weights.w_evidence_strength * evidence_score
        )

        return OpportunityScores(
            frequency=round(freq_score, 4),
            severity=round(sev_score, 4),
            evidence_strength=round(evidence_score, 4),
            composite=round(composite_score, 4),
        )
