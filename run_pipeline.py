"""
run_pipeline.py
Public Conversation Analysis Engine — Unified Pipeline Runner

Executes the entire analysis pipeline from end to end:
  Phase 2: Source Scraping & Normalization  (run.py)
  Phase 3: Taxonomy-Based Extraction        (run.py)
  Phase 4: Opportunity Clustering & Scoring (run.py)
  Phase 5: Output Report Assembly & Export  (export.py)

Usage:
    python run_pipeline.py
    python run_pipeline.py --dry-run
    python run_pipeline.py --skip-scrape
    python run_pipeline.py --layer a
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from engine.analyzer.opportunity_store import OpportunityStore
from engine.analyzer.run import run_analysis
from engine.config_loader import load_all_config
from engine.extractor.run import run_extraction
from engine.extractor.signal_store import SignalStore
from engine.logger import get_logger
from engine.output.export import export_all
from engine.output.report_builder import ReportBuilder
from engine.scraper.run import run_scraping

log = get_logger("engine.pipeline")

_ENGINE_DATA_DIR = Path(
    os.environ.get("ENGINE_DATA_DIR", Path(__file__).parent / "engine" / "data")
)
DEFAULT_REPORTS_DIR = _ENGINE_DATA_DIR / "reports"


def run_full_pipeline(
    dry_run: bool = False,
    skip_scrape: bool = False,
    layer: str = "ab",
    min_sources: int = 2,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Execute all pipeline phases in sequence and generate final deliverables.

    Returns:
        Summary dictionary with timing and metrics for each phase.
    """
    pipeline_start = time.time()
    out_dir = output_dir or DEFAULT_REPORTS_DIR

    log.info("=" * 80)
    log.info("PUBLIC CONVERSATION ANALYSIS ENGINE — FULL PIPELINE EXECUTION")
    log.info("  dry_run     : %s", dry_run)
    log.info("  skip_scrape : %s", skip_scrape)
    log.info("  match_layer : %s", layer.upper())
    log.info("  min_sources : %d", min_sources)
    log.info("  output_dir  : %s", out_dir)
    log.info("=" * 80)

    cfg = load_all_config()
    pipeline_summary: dict[str, Any] = {
        "phase2_scrape": {},
        "phase3_extract": {},
        "phase4_analyze": {},
        "phase5_export": {},
        "total_elapsed_seconds": 0.0,
    }

    # -------------------------------------------------------------------------
    # Phase 2: Scraping & Normalization
    # -------------------------------------------------------------------------
    p2_start = time.time()
    if not skip_scrape:
        log.info("\n>>> STARTING PHASE 2: SOURCE SCRAPING & NORMALIZATION <<<")
        p2_summary = run_scraping(dry_run=dry_run)
        pipeline_summary["phase2_scrape"] = p2_summary
        log.info("Phase 2 complete in %.2fs.", time.time() - p2_start)
    else:
        log.info("\n>>> SKIPPING PHASE 2: Using existing raw records <<<")
        pipeline_summary["phase2_scrape"] = {"skipped": True}

    # -------------------------------------------------------------------------
    # Phase 3: Taxonomy-Based Extraction
    # -------------------------------------------------------------------------
    p3_start = time.time()
    log.info("\n>>> STARTING PHASE 3: TAXONOMY-BASED EXTRACTION <<<")
    p3_summary = run_extraction(dry_run=dry_run, layer=layer)
    pipeline_summary["phase3_extract"] = p3_summary
    log.info("Phase 3 complete in %.2fs.", time.time() - p3_start)

    # -------------------------------------------------------------------------
    # Phase 4: Opportunity Clustering & Scoring
    # -------------------------------------------------------------------------
    p4_start = time.time()
    log.info("\n>>> STARTING PHASE 4: OPPORTUNITY CLUSTERING & SCORING <<<")
    p4_summary = run_analysis(min_sources=min_sources, dry_run=False)
    pipeline_summary["phase4_analyze"] = p4_summary
    log.info("Phase 4 complete in %.2fs.", time.time() - p4_start)

    # -------------------------------------------------------------------------
    # Phase 5: Output Report Building & Export
    # -------------------------------------------------------------------------
    p5_start = time.time()
    log.info("\n>>> STARTING PHASE 5: REPORT ASSEMBLY & EXPORT <<<")

    op_store = OpportunityStore()
    opportunities = op_store.read_all()

    sig_store = SignalStore()
    signals = sig_store.read_all()

    builder = ReportBuilder(config=cfg)
    final_report = builder.build_report(opportunities=opportunities, signals=signals)

    export_paths = export_all(report=final_report, output_dir=out_dir)
    pipeline_summary["phase5_export"] = {
        "opportunities_exported": len(opportunities),
        "export_paths": {k: str(v) for k, v in export_paths.items()},
    }
    log.info("Phase 5 complete in %.2fs.", time.time() - p5_start)

    # -------------------------------------------------------------------------
    # Final Summary
    # -------------------------------------------------------------------------
    total_elapsed = time.time() - pipeline_start
    pipeline_summary["total_elapsed_seconds"] = round(total_elapsed, 2)

    log.info("\n" + "=" * 80)
    log.info("PIPELINE EXECUTION COMPLETE — TOTAL TIME: %.2fs", total_elapsed)
    log.info("  Signals in Store       : %d", len(signals))
    log.info("  Opportunities Surfaced : %d", len(opportunities))
    log.info("  Export Deliverables    :")
    for fmt, path in export_paths.items():
        log.info("    [%s] %s", fmt.upper(), path)
    log.info("=" * 80 + "\n")

    return pipeline_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Public Conversation Analysis Engine — Unified Pipeline Runner"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run fast extraction on a 10% sample",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip scraping phase and use existing raw records",
    )
    parser.add_argument(
        "--layer",
        choices=["a", "ab"],
        default="ab",
        help="Extraction layers: 'a'=keyword only, 'ab'=keyword+embedding (default: ab)",
    )
    parser.add_argument(
        "--min-sources",
        type=int,
        default=2,
        help="Minimum independent source types per opportunity (default: 2)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom destination directory for exported reports",
    )
    args = parser.parse_args()

    out_path = Path(args.output_dir) if args.output_dir else None
    run_full_pipeline(
        dry_run=args.dry_run,
        skip_scrape=args.skip_scrape,
        layer=args.layer,
        min_sources=args.min_sources,
        output_dir=out_path,
    )


if __name__ == "__main__":
    main()
