"""
tests/test_phase4.py
Phase 4 — Opportunity Clustering & Scoring
Unit and integration tests for OpportunityArea schema, SignalGrouper, CrossSourceValidator,
OpportunitySynthesizer, OpportunityScorer, OpportunityRanker, OpportunityStore, and Analyzer Orchestrator.

No live API calls required. Uses synthetic signals and real taxonomy & scoring configs.
Run: pytest engine/tests/test_phase4.py -v
"""

from __future__ import annotations

import math
import tempfile
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from engine.analyzer.grouper import CandidateCluster, SignalGrouper
from engine.analyzer.models import (
    OpportunityArea,
    OpportunityScores,
    RepresentativeQuote,
)
from engine.analyzer.opportunity_store import OpportunityStore
from engine.analyzer.ranker import OpportunityRanker
from engine.analyzer.scorer import OpportunityScorer
from engine.analyzer.synthesizer import OpportunitySynthesizer
from engine.analyzer.validator import CrossSourceValidator, ValidationResult
from engine.config_loader import load_scoring_config, load_taxonomy
from engine.extractor.models import Signal, SourceRef


# =============================================================================
# Helper Fixtures & Signal Factories
# =============================================================================

def _make_signal(
    taxonomy_node: str = "fit_sizing.size_uncertainty",
    dimension: str = "Fit & Sizing",
    source_type: str = "reddit",
    source_name: str = "r/IndianFashionAddicts",
    verbatim: str = "The size chart is inaccurate and confusing.",
    severity_hint: str = "high",
    confidence: float = 0.90,
    segment_hints: list[str] | None = None,
    question_refs: list[int] | None = None,
) -> Signal:
    return Signal(
        signal_id=str(uuid.uuid4()),
        record_id=str(uuid.uuid4()),
        source_ref=SourceRef(
            source_type=source_type,
            source_name=source_name,
            url=f"https://{source_type}.com/post/123",
            date_published="2025-08-01T10:00:00Z",
        ),
        taxonomy_node=taxonomy_node,
        dimension=dimension,
        sub_category="Size Uncertainty",
        question_refs=question_refs or [2, 3, 7],
        verbatim_quote=verbatim,
        severity_hint=severity_hint,
        segment_hints=segment_hints or ["female", "urban"],
        confidence=confidence,
        match_layer="keyword",
    )


# =============================================================================
# 1. Tests — OpportunityArea Data Models
# =============================================================================

class TestOpportunityModels:
    def _make_op(self) -> OpportunityArea:
        return OpportunityArea(
            opportunity_id="opp-001",
            title="Size uncertainty creates pre-purchase friction",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            question_answers=[2, 3, 7],
            signal_count=10,
            source_spread={"reddit": 6, "app_store": 4},
            scores=OpportunityScores(
                frequency=0.8,
                severity=0.9,
                evidence_strength=0.7,
                composite=0.81,
            ),
            segment_concentration="Female, Urban",
            opportunity_statement="Users hesitate to buy due to confusing size charts.",
            representative_quotes=[
                RepresentativeQuote(
                    verbatim="Size chart is wrong",
                    source_type="reddit",
                    source_name="r/IndianFashionAddicts",
                    url="https://reddit.com/1",
                )
            ],
            rank=1,
        )

    def test_valid_creation(self):
        op = self._make_op()
        assert op.opportunity_id == "opp-001"
        assert op.rank == 1
        assert op.scores.composite == 0.81

    def test_empty_title_raises(self):
        op = self._make_op()
        with pytest.raises(ValueError, match="title"):
            OpportunityArea(
                opportunity_id="1",
                title="",
                dimension="Fit & Sizing",
                taxonomy_nodes=[],
                question_answers=[],
                signal_count=1,
                source_spread={},
                scores=op.scores,
                segment_concentration="",
                opportunity_statement="",
                representative_quotes=[],
            )

    def test_empty_dimension_raises(self):
        op = self._make_op()
        with pytest.raises(ValueError, match="dimension"):
            OpportunityArea(
                opportunity_id="1",
                title="Some Title",
                dimension="",
                taxonomy_nodes=[],
                question_answers=[],
                signal_count=1,
                source_spread={},
                scores=op.scores,
                segment_concentration="",
                opportunity_statement="",
                representative_quotes=[],
            )

    def test_to_dict_and_roundtrip(self):
        op = self._make_op()
        d = op.to_dict()
        assert d["opportunity_id"] == "opp-001"
        assert d["scores"]["composite"] == 0.81
        assert len(d["representative_quotes"]) == 1

        op2 = OpportunityArea.from_dict(d)
        assert op2.opportunity_id == op.opportunity_id
        assert op2.scores.frequency == op.scores.frequency
        assert len(op2.representative_quotes) == len(op.representative_quotes)
        assert op2.representative_quotes[0].verbatim == op.representative_quotes[0].verbatim


# =============================================================================
# 2. Tests — SignalGrouper
# =============================================================================

class TestSignalGrouper:
    def test_group_empty_signals(self):
        grouper = SignalGrouper()
        clusters = grouper.group([])
        assert clusters == []

    def test_group_by_taxonomy_nodes(self):
        taxonomy = load_taxonomy()
        grouper = SignalGrouper(taxonomy=taxonomy)

        signals = [
            _make_signal(taxonomy_node="fit_sizing.size_uncertainty", source_type="reddit"),
            _make_signal(taxonomy_node="fit_sizing.size_uncertainty", source_type="app_store"),
            _make_signal(taxonomy_node="price_value.price_hesitation", dimension="Price & Value", source_type="youtube"),
        ]

        clusters = grouper.group(signals)
        assert len(clusters) == 2

        cluster_map = {c.taxonomy_nodes[0]: c for c in clusters}
        assert "fit_sizing.size_uncertainty" in cluster_map
        assert "price_value.price_hesitation" in cluster_map
        assert cluster_map["fit_sizing.size_uncertainty"].signal_count == 2
        assert cluster_map["price_value.price_hesitation"].signal_count == 1

    def test_distinct_source_types_on_candidate_cluster(self):
        signals = [
            _make_signal(source_type="reddit"),
            _make_signal(source_type="reddit"),
            _make_signal(source_type="app_store"),
            _make_signal(source_type="youtube"),
        ]
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=signals,
        )
        assert cluster.distinct_source_types == {"reddit", "app_store", "youtube"}


# =============================================================================
# 3. Tests — CrossSourceValidator
# =============================================================================

class TestCrossSourceValidator:
    def test_validator_passes_multi_source_cluster(self):
        validator = CrossSourceValidator(min_sources=2)
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=[
                _make_signal(source_type="reddit"),
                _make_signal(source_type="app_store"),
            ],
        )

        result = validator.validate([cluster])
        assert len(result.passed_clusters) == 1
        assert len(result.rejected_clusters) == 0

    def test_validator_rejects_single_source_cluster(self):
        validator = CrossSourceValidator(min_sources=2)
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=[
                _make_signal(source_type="reddit"),
                _make_signal(source_type="reddit"),
            ],
        )

        result = validator.validate([cluster])
        assert len(result.passed_clusters) == 0
        assert len(result.rejected_clusters) == 1

    def test_custom_min_sources_threshold(self):
        validator = CrossSourceValidator(min_sources=3)
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=[
                _make_signal(source_type="reddit"),
                _make_signal(source_type="app_store"),
            ],
        )

        result = validator.validate([cluster])
        assert len(result.passed_clusters) == 0
        assert len(result.rejected_clusters) == 1


# =============================================================================
# 4. Tests — OpportunitySynthesizer
# =============================================================================

class TestOpportunitySynthesizer:
    def test_synthesize_statement_and_quotes(self):
        taxonomy = load_taxonomy()
        synthesizer = OpportunitySynthesizer(taxonomy=taxonomy)

        signals = [
            _make_signal(source_type="reddit", verbatim="Myntra size chart is terrible.", severity_hint="high", confidence=0.95),
            _make_signal(source_type="app_store", verbatim="Always have to size up on this app.", severity_hint="medium", confidence=0.85),
            _make_signal(source_type="play_store", verbatim="Inconsistent sizing across brands.", severity_hint="high", confidence=0.90),
        ]

        cluster = CandidateCluster(
            cluster_id="cluster_fit_sizing.size_uncertainty",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=signals,
        )

        op = synthesizer.synthesize(cluster)
        assert op.opportunity_id == cluster.cluster_id
        assert op.dimension == "Fit & Sizing"
        assert len(op.representative_quotes) == 3
        assert "Female" in op.segment_concentration or "Urban" in op.segment_concentration
        assert "Fit & Sizing" in op.title or "Size" in op.title
        assert len(op.opportunity_statement) > 20
        assert 2 in op.question_answers
        assert 3 in op.question_answers

    def test_quote_source_diversity(self):
        synthesizer = OpportunitySynthesizer()
        signals = [
            _make_signal(source_type="reddit", verbatim="Quote 1 from Reddit"),
            _make_signal(source_type="reddit", verbatim="Quote 2 from Reddit"),
            _make_signal(source_type="youtube", verbatim="Quote 3 from YouTube"),
            _make_signal(source_type="forum", verbatim="Quote 4 from Forum"),
        ]
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=signals,
        )

        op = synthesizer.synthesize(cluster)
        quote_sources = {q.source_type for q in op.representative_quotes}
        assert "reddit" in quote_sources
        assert "youtube" in quote_sources
        assert "forum" in quote_sources


# =============================================================================
# 5. Tests — OpportunityScorer
# =============================================================================

class TestOpportunityScorer:
    def setup_method(self):
        self.scoring_config = load_scoring_config()
        self.scorer = OpportunityScorer(self.scoring_config)

    def test_frequency_score_calculation(self):
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=[_make_signal() for _ in range(5)],
        )
        scores = self.scorer.compute_scores(cluster, max_signal_count=10)
        assert math.isclose(scores.frequency, 0.5, abs_tol=0.001)

    def test_severity_score_calculation(self):
        # 1 high (1.0), 1 medium (0.6), 1 low (0.3) -> avg = (1.0 + 0.6 + 0.3) / 3 = 1.9 / 3 = 0.6333
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=[
                _make_signal(severity_hint="high"),
                _make_signal(severity_hint="medium"),
                _make_signal(severity_hint="low"),
            ],
        )
        scores = self.scorer.compute_scores(cluster, max_signal_count=3)
        expected_sev = (1.0 + 0.6 + 0.3) / 3.0
        assert math.isclose(scores.severity, expected_sev, abs_tol=0.001)

    def test_evidence_strength_calculation(self):
        # 2 distinct source types out of 7, avg confidence = 0.90
        # formula = (2 / 7.0) * 0.90 = 0.2571
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=[
                _make_signal(source_type="reddit", confidence=0.90),
                _make_signal(source_type="app_store", confidence=0.90),
            ],
        )
        scores = self.scorer.compute_scores(cluster, max_signal_count=2)
        expected_evidence = (2.0 / 7.0) * 0.90
        assert math.isclose(scores.evidence_strength, expected_evidence, abs_tol=0.001)

    def test_composite_score_formula(self):
        # composite = w_freq * freq + w_sev * sev + w_ev * ev
        cluster = CandidateCluster(
            cluster_id="c1",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            signals=[
                _make_signal(source_type="reddit", severity_hint="high", confidence=1.0),
            ],
        )
        scores = self.scorer.compute_scores(cluster, max_signal_count=1)
        w = self.scoring_config.weights
        expected_comp = (
            w.w_frequency * scores.frequency
            + w.w_severity * scores.severity
            + w.w_evidence_strength * scores.evidence_strength
        )
        assert math.isclose(scores.composite, expected_comp, abs_tol=0.001)


# =============================================================================
# 6. Tests — OpportunityRanker
# =============================================================================

class TestOpportunityRanker:
    def test_rank_opportunities_descending(self):
        def _make_scored_op(op_id: str, comp: float, sev: float, count: int) -> OpportunityArea:
            return OpportunityArea(
                opportunity_id=op_id,
                title=f"Opportunity {op_id}",
                dimension="Fit & Sizing",
                taxonomy_nodes=[],
                question_answers=[],
                signal_count=count,
                source_spread={},
                scores=OpportunityScores(frequency=0.5, severity=sev, evidence_strength=0.5, composite=comp),
                segment_concentration="",
                opportunity_statement="",
                representative_quotes=[],
            )

        ops = [
            _make_scored_op("op_low", 0.40, 0.5, 5),
            _make_scored_op("op_high", 0.85, 0.9, 20),
            _make_scored_op("op_mid", 0.65, 0.7, 10),
        ]

        ranked = OpportunityRanker.rank(ops)
        assert [op.opportunity_id for op in ranked] == ["op_high", "op_mid", "op_low"]
        assert [op.rank for op in ranked] == [1, 2, 3]


# =============================================================================
# 7. Tests — OpportunityStore
# =============================================================================

class TestOpportunityStore:
    def test_write_read_and_queries(self, tmp_path, monkeypatch):
        import engine.data_store as ds_mod
        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        store = OpportunityStore(run_id="test_run")
        op1 = OpportunityArea(
            opportunity_id="op1",
            title="Size Friction",
            dimension="Fit & Sizing",
            taxonomy_nodes=["fit_sizing.size_uncertainty"],
            question_answers=[2, 3],
            signal_count=15,
            source_spread={"reddit": 10, "app_store": 5},
            scores=OpportunityScores(0.8, 0.9, 0.7, 0.85),
            segment_concentration="Female",
            opportunity_statement="Size issues.",
            representative_quotes=[],
            rank=1,
        )
        op2 = OpportunityArea(
            opportunity_id="op2",
            title="Price Skepticism",
            dimension="Price & Value",
            taxonomy_nodes=["price_value.price_hesitation"],
            question_answers=[1, 5],
            signal_count=8,
            source_spread={"reddit": 5, "youtube": 3},
            scores=OpportunityScores(0.5, 0.6, 0.5, 0.55),
            segment_concentration="Students",
            opportunity_statement="Price issues.",
            representative_quotes=[],
            rank=2,
        )

        store.write_batch([op1, op2])
        all_ops = store.read_all()
        assert len(all_ops) == 2

        fit_ops = store.by_dimension("Fit & Sizing")
        assert len(fit_ops) == 1
        assert fit_ops[0].opportunity_id == "op1"

        q3_ops = store.by_question(3)
        assert len(q3_ops) == 1
        assert q3_ops[0].opportunity_id == "op1"

        top_1 = store.top_k(1)
        assert len(top_1) == 1
        assert top_1[0].rank == 1


# =============================================================================
# 8. Tests — Analyzer Orchestrator (run.py)
# =============================================================================

class TestAnalyzerOrchestrator:
    def test_run_analysis_end_to_end(self, tmp_path, monkeypatch):
        import engine.data_store as ds_mod
        from engine.analyzer.run import run_analysis
        from engine.extractor.signal_store import SignalStore

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        sig_store = SignalStore(run_id="test_run")
        # Populate signals for 2 dimensions, each with >= 2 source types
        test_signals = [
            _make_signal(taxonomy_node="fit_sizing.size_uncertainty", dimension="Fit & Sizing", source_type="reddit"),
            _make_signal(taxonomy_node="fit_sizing.size_uncertainty", dimension="Fit & Sizing", source_type="app_store"),
            _make_signal(taxonomy_node="price_value.price_hesitation", dimension="Price & Value", source_type="youtube"),
            _make_signal(taxonomy_node="price_value.price_hesitation", dimension="Price & Value", source_type="forum"),
            # Single source cluster -> will be filtered out by validator
            _make_signal(taxonomy_node="return_risk.return_policy_friction", dimension="Return & Risk", source_type="social"),
        ]
        for s in test_signals:
            sig_store.write(s)

        summary = run_analysis(min_sources=2, top_k=5, dry_run=False)

        assert summary["signals_read"] == 5
        assert summary["candidate_clusters"] == 3
        assert summary["passed_clusters"] == 2
        assert summary["rejected_clusters"] == 1
        assert summary["opportunities_surfaced"] == 2
        assert len(summary["top_opportunities"]) == 2
        assert summary["top_opportunities"][0]["rank"] == 1
