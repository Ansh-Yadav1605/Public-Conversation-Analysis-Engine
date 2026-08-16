"""
engine/analyzer/run.py
Public Conversation Analysis Engine — Opportunity Clustering & Scoring Orchestrator (Phase 4)

Pipeline:
1. Reads all extracted Signal records from the SignalStore.
2. SignalGrouper: Groups signals by taxonomy node / dimension.
3. CrossSourceValidator: Enforces >= min_sources independent platforms per cluster.
4. OpportunitySynthesizer: Creates structured statements, titles, and representative quotes.
5. OpportunityScorer: Computes Frequency, Severity, Evidence Strength, and Composite scores.
6. OpportunityRanker: Ranks opportunities (rank 1 = top priority).
7. OpportunityStore: Persists ranked OpportunityArea records to JSONL store.
8. Displays a comprehensive summary log.

Usage:
    python -m engine.analyzer.run
    python -m engine.analyzer.run --min-sources 2
    python -m engine.analyzer.run --top-k 10
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from engine.analyzer.grouper import SignalGrouper
from engine.analyzer.models import OpportunityArea
from engine.analyzer.opportunity_store import OpportunityStore
from engine.analyzer.ranker import OpportunityRanker
from engine.analyzer.scorer import OpportunityScorer
from engine.analyzer.synthesizer import OpportunitySynthesizer
from engine.analyzer.validator import CrossSourceValidator
from engine.config_loader import load_all_config
from engine.extractor.signal_store import SignalStore
from engine.logger import get_logger

log = get_logger(__name__)


def run_analysis(
    min_sources: int = 2,
    top_k: int = 10,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Execute the Stage 3 Opportunity Clustering & Scoring Pipeline.

    Args:
        min_sources: Minimum independent source types required for a cluster.
        top_k: Number of top opportunities to display in the summary.
        dry_run: If True, operates in memory without persisting to OpportunityStore.

    Returns:
        Summary dict containing execution metrics and top opportunities.
    """
    run_start = time.time()
    log.info("=" * 70)
    log.info("PHASE 4 — OPPORTUNITY CLUSTERING & SCORING PIPELINE STARTED")
    log.info("  min_sources threshold : %d", min_sources)
    if dry_run:
        log.info("  [DRY RUN MODE] Results will not be saved to disk.")
    log.info("=" * 70)

    # 1. Load configs & signal store
    cfg = load_all_config()
    sig_store = SignalStore()
    signals = sig_store.read_all()

    summary: dict[str, Any] = {
        "signals_read": len(signals),
        "candidate_clusters": 0,
        "passed_clusters": 0,
        "rejected_clusters": 0,
        "opportunities_surfaced": 0,
        "top_opportunities": [],
    }

    if not signals:
        log.warning("Opportunity Analyzer: 0 signals found in SignalStore. Run Phase 3 first.")
        return summary

    log.info("Loaded %d signals from SignalStore.", len(signals))

    # 2. Group signals
    grouper = SignalGrouper(taxonomy=cfg.taxonomy)
    candidate_clusters = grouper.group(signals)
    summary["candidate_clusters"] = len(candidate_clusters)

    # 3. Cross-Source Validation
    validator = CrossSourceValidator(min_sources=min_sources)
    val_result = validator.validate(candidate_clusters)
    summary["passed_clusters"] = len(val_result.passed_clusters)
    summary["rejected_clusters"] = len(val_result.rejected_clusters)

    if not val_result.passed_clusters:
        log.warning(
            "No candidate clusters passed the cross-source validation threshold (min_sources=%d).",
            min_sources,
        )
        return summary

    # 4. Synthesize Opportunity Areas
    synthesizer = OpportunitySynthesizer(taxonomy=cfg.taxonomy)
    synthesized_ops = [
        synthesizer.synthesize(cluster) for cluster in val_result.passed_clusters
    ]

    # 5. Score Opportunities
    scorer = OpportunityScorer(scoring_config=cfg.scoring)
    scored_ops = scorer.score_all(synthesized_ops, val_result.passed_clusters)

    # 6. Rank Opportunities
    ranked_ops = OpportunityRanker.rank(scored_ops)
    summary["opportunities_surfaced"] = len(ranked_ops)

    # 7. Persist to OpportunityStore
    if not dry_run:
        op_store = OpportunityStore()
        op_store.write_batch(ranked_ops)

    # 8. Extract top K summary
    top_ops = ranked_ops[:top_k]
    summary["top_opportunities"] = [
        {
            "rank": op.rank,
            "title": op.title,
            "dimension": op.dimension,
            "signal_count": op.signal_count,
            "composite_score": op.scores.composite,
            "sources": list(op.source_spread.keys()),
        }
        for op in top_ops
    ]

    elapsed = time.time() - run_start

    # Log summary table
    log.info("=" * 70)
    log.info("OPPORTUNITY CLUSTERING & SCORING COMPLETE — elapsed=%.2fs", elapsed)
    log.info("  Signals processed        : %d", summary["signals_read"])
    log.info("  Candidate clusters       : %d", summary["candidate_clusters"])
    log.info("  Clusters passed (>=%d src): %d", min_sources, summary["passed_clusters"])
    log.info("  Clusters rejected        : %d", summary["rejected_clusters"])
    log.info("  Opportunities surfaced   : %d", summary["opportunities_surfaced"])
    log.info("-" * 70)
    log.info("TOP %d OPPORTUNITY AREAS:", min(top_k, len(ranked_ops)))
    for op in top_ops:
        log.info(
            "  #%d [%.3f] (%s | %d sigs) %s",
            op.rank,
            op.scores.composite,
            op.dimension,
            op.signal_count,
            op.title,
        )
    log.info("=" * 70)

    return summary


# ── CLI Entry Point ────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Public Conversation Analysis Engine — Phase 4 Opportunity Analyzer"
    )
    parser.add_argument(
        "--min-sources",
        type=int,
        default=2,
        help="Minimum independent source types required per opportunity cluster (default: 2)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top opportunities to display in summary (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run analysis without saving to disk",
    )
    args = parser.parse_args()

    summary = run_analysis(
        min_sources=args.min_sources,
        top_k=args.top_k,
        dry_run=args.dry_run,
    )
    sys.exit(0 if summary.get("opportunities_surfaced", 0) > 0 or summary.get("signals_read", 0) == 0 else 1)


if __name__ == "__main__":
    main()
