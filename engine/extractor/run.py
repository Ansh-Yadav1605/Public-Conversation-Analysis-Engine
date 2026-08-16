"""
engine/extractor/run.py
Public Conversation Analysis Engine — Extraction Orchestrator (Phase 3)

Entry point for the taxonomy-based extraction layer.

Pipeline per RawRecord:
    1. Load all RawRecords from the data store
    2. Skip records already processed in a previous run (via processed_ids tracking)
    3. Preprocess text → PreprocessedText (clean, split into sentences)
    4. Skip non-English records (flag in log, do not discard silently)
    5. For each sentence: run TaxonomyMatcher (Layer A + B)
    6. For each (sentence, matched node): build a Signal via SignalConstructor
    7. Write Signal to the signal store
    8. Log extraction summary

Usage:
    python -m engine.extractor.run
    python -m engine.extractor.run --dry-run   (first 10% of records only)
    python -m engine.extractor.run --layer a   (keyword only, skip embeddings)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from engine.config_loader import load_all_config
from engine.data_store import DataStore
from engine.extractor.models import Signal
from engine.extractor.preprocessor import preprocess
from engine.extractor.signal_constructor import SignalConstructor
from engine.extractor.signal_store import SignalStore
from engine.extractor.taxonomy_matcher import TaxonomyMatcher
from engine.scraper.models import RawRecord
from engine.logger import get_logger

log = get_logger(__name__)

# File that tracks which record_ids have already been extracted
_PROCESSED_IDS_FILE = (
    Path(__file__).parent.parent / "data" / "extraction_processed_ids.json"
)


def _load_processed_ids() -> set[str]:
    if _PROCESSED_IDS_FILE.exists():
        try:
            with _PROCESSED_IDS_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return set(data.get("processed_ids", []))
        except Exception:
            return set()
    return set()


def _save_processed_ids(processed_ids: set[str]) -> None:
    _PROCESSED_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _PROCESSED_IDS_FILE.open("w", encoding="utf-8") as fh:
        json.dump({"processed_ids": sorted(processed_ids)}, fh)


def run_extraction(
    dry_run: bool = False,
    layer: str = "ab",
    min_confidence: float | None = None,
) -> dict[str, int | float]:
    """
    Execute the full extraction pipeline.

    Args:
        dry_run:        If True, process only the first 10% of available RawRecords.
        layer:          "a" = keyword only; "ab" = keyword + embedding (default).
        min_confidence: Override minimum confidence threshold (from scoring_weights.yaml).

    Returns:
        Summary dict with extraction statistics.
    """
    run_start = time.time()

    log.info("=" * 70)
    log.info("PHASE 3 — EXTRACTION PIPELINE STARTED")
    if dry_run:
        log.info("  [DRY RUN] Processing first 10%% of records only.")
    log.info("  Match layers: %s", layer.upper())
    log.info("=" * 70)

    cfg = load_all_config()
    min_conf = min_confidence if min_confidence is not None else cfg.scoring.confidence_thresholds.minimum_confidence

    # ── Setup ──────────────────────────────────────────────────────────────
    raw_store = DataStore()
    signal_store = SignalStore()
    processed_ids = _load_processed_ids()

    # ── Load raw records ───────────────────────────────────────────────────
    all_raw_dicts = raw_store.read_all_raw_records()
    if not all_raw_dicts:
        log.warning("No RawRecords found in the data store. Run Phase 2 first.")
        return {"records_found": 0, "records_processed": 0, "signals_extracted": 0,
                "non_english_skipped": 0, "low_confidence_signals": 0, "errors": 0,
                "avg_confidence": 0.0, "avg_signals_per_record": 0.0}

    # Filter already-processed records
    unprocessed = [d for d in all_raw_dicts if d.get("record_id") not in processed_ids]

    if dry_run:
        cutoff = max(1, len(unprocessed) // 10)
        unprocessed = unprocessed[:cutoff]
        log.info("Dry-run: processing %d of %d unprocessed records.", len(unprocessed), len(all_raw_dicts))
    else:
        log.info(
            "Records: total=%d | already processed=%d | to process=%d",
            len(all_raw_dicts), len(all_raw_dicts) - len(unprocessed), len(unprocessed),
        )

    if not unprocessed:
        log.info("All records already processed. Nothing to do.")
        return {"records_found": len(all_raw_dicts), "records_processed": 0,
                "signals_extracted": 0, "non_english_skipped": 0,
                "low_confidence_signals": 0, "errors": 0,
                "avg_confidence": 0.0, "avg_signals_per_record": 0.0}

    # ── Initialise components ──────────────────────────────────────────────
    matcher = TaxonomyMatcher(cfg.taxonomy)
    if layer == "ab" and matcher._embedding_available:
        matcher.precompute_node_embeddings()
    elif layer == "a":
        matcher._embedding_available = False
        log.info("Embedding layer (B) disabled by --layer a flag.")

    constructor = SignalConstructor(cfg.scoring)

    # ── Main extraction loop ───────────────────────────────────────────────
    summary = {
        "records_found": len(all_raw_dicts),
        "records_processed": 0,
        "signals_extracted": 0,
        "non_english_skipped": 0,
        "low_confidence_signals": 0,
        "errors": 0,
    }
    total_confidence: float = 0.0
    multi_signal_records: int = 0
    new_processed: set[str] = set()

    for raw_dict in unprocessed:
        record_id = raw_dict.get("record_id", "")
        try:
            record = RawRecord.from_dict(raw_dict)
        except Exception as exc:
            log.warning("Skipping malformed RawRecord '%s': %s", record_id, exc)
            summary["errors"] += 1
            continue

        # ── Preprocess ────────────────────────────────────────────────────
        try:
            processed = preprocess(record.text)
        except Exception as exc:
            log.warning("Preprocessing failed for record '%s': %s", record_id, exc)
            summary["errors"] += 1
            continue

        if not processed.is_english:
            log.debug("Non-English record skipped: id=%s lang=%s", record_id, processed.language)
            summary["non_english_skipped"] += 1
            new_processed.add(record_id)
            continue

        if not processed.sentences:
            new_processed.add(record_id)
            continue

        # ── Match and construct signals ────────────────────────────────────
        record_signal_count = 0
        for sentence in processed.sentences:
            try:
                matches = matcher.match_sentence(sentence)
            except Exception as exc:
                log.warning("Matcher error for record '%s' sentence: %s", record_id, exc)
                continue

            for match in matches:
                if match.confidence < min_conf:
                    summary["low_confidence_signals"] += 1
                    continue

                try:
                    signal = constructor.build(record, match)
                    signal_store.write(signal)
                    record_signal_count += 1
                    total_confidence += signal.confidence
                    summary["signals_extracted"] += 1
                except Exception as exc:
                    log.warning("Signal construction failed: %s", exc)

        if record_signal_count >= 2:
            multi_signal_records += 1

        new_processed.add(record_id)
        summary["records_processed"] += 1

        # Progress log every 100 records
        if summary["records_processed"] % 100 == 0:
            log.info(
                "  Progress: %d records processed | %d signals extracted",
                summary["records_processed"], summary["signals_extracted"],
            )

    # ── Persist processed IDs ──────────────────────────────────────────────
    all_processed = processed_ids | new_processed
    if not dry_run:
        _save_processed_ids(all_processed)

    # ── Summary ───────────────────────────────────────────────────────────
    total_sig = summary["signals_extracted"]
    total_proc = summary["records_processed"]
    avg_conf = round(total_confidence / total_sig, 4) if total_sig > 0 else 0.0
    avg_per_rec = round(total_sig / total_proc, 2) if total_proc > 0 else 0.0
    multi_pct = round(100 * multi_signal_records / total_proc, 1) if total_proc > 0 else 0.0

    summary["avg_confidence"] = avg_conf
    summary["avg_signals_per_record"] = avg_per_rec

    elapsed = time.time() - run_start

    log.info("=" * 70)
    log.info("EXTRACTION PIPELINE COMPLETE -- elapsed=%.1fs", elapsed)
    log.info("  Records found       : %d", summary["records_found"])
    log.info("  Records processed   : %d", summary["records_processed"])
    log.info("  Non-English skipped : %d", summary["non_english_skipped"])
    log.info("  Signals extracted   : %d", summary["signals_extracted"])
    log.info("  Avg confidence      : %.4f", avg_conf)
    log.info("  Avg signals/record  : %.2f", avg_per_rec)
    log.info("  Multi-signal records: %d (%.1f%%)", multi_signal_records, multi_pct)
    log.info("  Low-conf filtered   : %d", summary["low_confidence_signals"])
    log.info("  Errors              : %d", summary["errors"])
    log.info("=" * 70)

    return summary


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Public Conversation Analysis Engine — Phase 3 Extractor"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process only the first 10%% of unprocessed records",
    )
    parser.add_argument(
        "--layer",
        choices=["a", "ab"],
        default="ab",
        help="Match layers: 'a'=keyword only, 'ab'=keyword+embedding (default: ab)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        metavar="THRESHOLD",
        help="Override minimum signal confidence threshold (0.0–1.0)",
    )
    args = parser.parse_args()

    summary = run_extraction(
        dry_run=args.dry_run,
        layer=args.layer,
        min_confidence=args.min_confidence,
    )
    sys.exit(0 if summary.get("errors", 0) == 0 else 1)


if __name__ == "__main__":
    main()
