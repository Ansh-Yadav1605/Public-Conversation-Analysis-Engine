"""
engine/scraper/run.py
Public Conversation Analysis Engine — Scraping Orchestrator (Phase 2)

Entry point for the source scraping layer.

Pipeline:
    1. Load source_list.yaml via config_loader
    2. For each enabled source, instantiate the correct connector
    3. Call connector.fetch() → list of source-native raw dicts
    4. Normalize each raw dict → RawRecord
    5. Dedup check: skip if already seen (cross-run fingerprint)
    6. Write new records to the JSONL data store
    7. Save deduplicator fingerprints
    8. Log a summary

Usage:
    python -m engine.scraper.run
    python -m engine.scraper.run --dry-run    (10% sample mode)
    python -m engine.scraper.run --source reddit  (single source type only)
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from engine.config_loader import load_all_config, SourceConfig
from engine.data_store import DataStore
from engine.scraper.deduplicator import Deduplicator
from engine.scraper.models import RawRecord
from engine.scraper.normalizer import normalize
from engine.logger import get_logger

log = get_logger(__name__)

# ── Connector registry ─────────────────────────────────────────────────────
# Maps source_type → connector class. Import lazily inside the function to
# avoid hard-import failures when optional dependencies aren't installed.

CONNECTOR_REGISTRY: dict[str, str] = {
    "app_store":  "engine.scraper.connector_app_store.AppStoreConnector",
    "play_store": "engine.scraper.connector_play_store.PlayStoreConnector",
    "reddit":     "engine.scraper.connector_reddit.RedditConnector",
    "forum":      "engine.scraper.connector_forum.ForumConnector",
    "social":     "engine.scraper.connector_social.SocialConnector",
    "youtube":    "engine.scraper.connector_youtube.YouTubeConnector",
    "review_qa":  "engine.scraper.connector_review_qa.ReviewQAConnector",
}


def _import_connector(dotted_path: str):
    """Dynamically import a connector class by its dotted module path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def run_scraping(
    source_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Execute the full scraping pipeline.

    Args:
        source_filter: If set, only scrape sources matching this source_type.
        dry_run:       If True, cap each source at 10% of its volume_cap.

    Returns:
        Summary dict: {
            "sources_run": int,
            "records_fetched": int,
            "records_written": int,
            "duplicates_skipped": int,
            "errors": int,
        }
    """
    run_start = time.time()
    log.info("=" * 70)
    log.info("PHASE 2 — SCRAPING PIPELINE STARTED")
    if dry_run:
        log.info("  [DRY RUN MODE] Volume capped at 10%% per source")
    if source_filter:
        log.info("  [FILTER] Only running source_type='%s'", source_filter)
    log.info("=" * 70)

    cfg = load_all_config()
    store = DataStore()
    dedup = Deduplicator()

    summary = {
        "sources_run": 0,
        "records_fetched": 0,
        "records_written": 0,
        "duplicates_skipped": 0,
        "errors": 0,
    }

    enabled_sources = cfg.source_list.enabled_sources
    if source_filter:
        enabled_sources = [s for s in enabled_sources if s.source_type == source_filter]

    if not enabled_sources:
        log.warning("No enabled sources matched the filter. Exiting.")
        return summary

    for source_cfg in enabled_sources:
        log.info(
            "-- Running connector: '%s' (type=%s)",
            source_cfg.source_name, source_cfg.source_type,
        )

        # Resolve connector class
        connector_path = CONNECTOR_REGISTRY.get(source_cfg.source_type)
        if not connector_path:
            log.error("No connector registered for source_type='%s'", source_cfg.source_type)
            summary["errors"] += 1
            continue

        # Apply dry-run cap override
        if dry_run:
            from dataclasses import replace
            source_cfg = SourceConfig(
                source_type=source_cfg.source_type,
                source_name=source_cfg.source_name,
                enabled=source_cfg.enabled,
                lookback_days=source_cfg.lookback_days,
                volume_cap=max(1, source_cfg.volume_cap // 10),
                config=source_cfg.config,
            )

        try:
            ConnectorClass = _import_connector(connector_path)
            connector = ConnectorClass(source_cfg)
            raw_records: list[dict[str, Any]] = connector.fetch()
        except Exception as exc:
            log.error(
                "Connector '%s' raised an unhandled exception: %s",
                source_cfg.source_name, exc,
            )
            summary["errors"] += 1
            continue

        source_fetched = len(raw_records)
        source_written = 0
        source_dupes = 0

        for raw in raw_records:
            record: RawRecord | None = normalize(
                source_cfg.source_type,
                source_cfg.source_name,
                raw,
            )
            if record is None:
                continue

            if dedup.is_duplicate(record):
                log.debug("Duplicate skipped: record_id=%s", record.record_id)
                source_dupes += 1
                continue

            store.write_raw_record(record.to_dict())
            dedup.mark_seen(record)
            source_written += 1

        summary["sources_run"] += 1
        summary["records_fetched"] += source_fetched
        summary["records_written"] += source_written
        summary["duplicates_skipped"] += source_dupes

        log.info(
            "  '%s' done: fetched=%d | written=%d | dupes_skipped=%d",
            source_cfg.source_name, source_fetched, source_written, source_dupes,
        )

    # Persist fingerprints for cross-run deduplication
    dedup.save()

    elapsed = time.time() - run_start

    log.info("=" * 70)
    log.info("SCRAPING PIPELINE COMPLETE — elapsed=%.1fs", elapsed)
    log.info("  Sources run       : %d", summary["sources_run"])
    log.info("  Records fetched   : %d", summary["records_fetched"])
    log.info("  Records written   : %d", summary["records_written"])
    log.info("  Duplicates skipped: %d", summary["duplicates_skipped"])
    log.info("  Errors            : %d", summary["errors"])
    log.info("=" * 70)

    return summary


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Public Conversation Analysis Engine — Phase 2 Scraper"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run with 10%% of volume_cap for fast testing",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        metavar="SOURCE_TYPE",
        help="Run only sources matching this source_type (e.g. reddit, youtube)",
    )
    args = parser.parse_args()

    summary = run_scraping(source_filter=args.source, dry_run=args.dry_run)
    sys.exit(0 if summary["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
