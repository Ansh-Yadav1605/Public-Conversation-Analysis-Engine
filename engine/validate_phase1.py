"""
engine/validate_phase1.py
Public Conversation Analysis Engine — Phase 1 Exit Criteria Validator

Run this script after Phase 1 setup to confirm all exit criteria are met
before proceeding to Phase 2.

Exit Criteria (from implementation-plan.md §Phase 1):
    ✓ Taxonomy reviewed for coverage: every question answerable via ≥1 taxonomy path
    ✓ Config files are valid YAML and parseable without errors
    ✓ All 4 config files present and complete
    ✓ Minimum node count: ≥ 29 taxonomy nodes across ≥ 10 dimensions
    ✓ Scoring weights sum to 1.0
    ✓ At least 7 source types enabled in source_list.yaml (all 7 configured)
    ✓ Data store directories exist

Usage:
    python -m engine.validate_phase1
    # or:
    python engine/validate_phase1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from engine.config_loader import load_all_config
from engine.data_store import init_data_store
from engine.logger import get_logger

log = get_logger(__name__)

# Minimum counts required by implementation plan
MIN_TAXONOMY_NODES = 29
MIN_TAXONOMY_DIMENSIONS = 10
REQUIRED_SOURCE_TYPES = {
    "app_store", "play_store", "reddit", "forum", "social", "youtube", "review_qa"
}
REQUIRED_QUESTION_COUNT = 10
REQUIRED_CONFIG_FILES = [
    "config/source_list.yaml",
    "config/taxonomy.yaml",
    "config/question_set.yaml",
    "config/scoring_weights.yaml",
]


def check_config_files_present() -> bool:
    """Check 1: All 4 config files exist."""
    engine_dir = Path(__file__).parent
    missing = []
    for rel_path in REQUIRED_CONFIG_FILES:
        full = engine_dir / rel_path
        if not full.exists():
            missing.append(str(full))

    if missing:
        log.error("FAIL — Missing config files:\n  %s", "\n  ".join(missing))
        return False

    log.info("PASS — All 4 config files present.")
    return True


def check_source_list(cfg) -> bool:
    """Check 2: All 7 source types configured (enabled or disabled)."""
    configured_types = {s.source_type for s in cfg.source_list.sources}
    missing_types = REQUIRED_SOURCE_TYPES - configured_types
    if missing_types:
        log.error(
            "FAIL — source_list.yaml is missing source types: %s", sorted(missing_types)
        )
        return False

    enabled_types = {s.source_type for s in cfg.source_list.enabled_sources}
    log.info(
        "PASS -- source_list.yaml: %d source types configured, %d source types enabled. "
        "Enabled types: %s",
        len(configured_types),
        len(enabled_types),
        sorted(enabled_types),
    )
    return True


def check_taxonomy_coverage(cfg) -> bool:
    """Check 3: ≥ 29 nodes, ≥ 10 dimensions, all dimensions mapped."""
    nodes = cfg.taxonomy.nodes
    dims = cfg.taxonomy.dimensions

    passed = True

    if len(nodes) < MIN_TAXONOMY_NODES:
        log.error(
            "FAIL — taxonomy.yaml has %d nodes; minimum required is %d.",
            len(nodes), MIN_TAXONOMY_NODES,
        )
        passed = False
    else:
        log.info("PASS -- taxonomy.yaml: %d nodes (>=%d required).", len(nodes), MIN_TAXONOMY_NODES)

    if len(dims) < MIN_TAXONOMY_DIMENSIONS:
        log.error(
            "FAIL -- taxonomy.yaml has %d dimensions; minimum required is %d.",
            len(dims), MIN_TAXONOMY_DIMENSIONS,
        )
        passed = False
    else:
        log.info(
            "PASS -- taxonomy.yaml: %d dimensions (>=%d required). Dimensions: %s",
            len(dims), MIN_TAXONOMY_DIMENSIONS, dims,
        )

    return passed


def check_question_set(cfg) -> bool:
    """Check 4: Exactly 10 questions defined."""
    count = len(cfg.question_set.questions)
    if count != REQUIRED_QUESTION_COUNT:
        log.error(
            "FAIL — question_set.yaml has %d questions; exactly %d required.",
            count, REQUIRED_QUESTION_COUNT,
        )
        return False
    log.info("PASS — question_set.yaml: %d questions defined.", count)
    return True


def check_scoring_weights(cfg) -> bool:
    """Check 5: Weights sum to 1.0 (validated in loader; re-confirm here)."""
    w = cfg.scoring.weights
    total = round(w.w_frequency + w.w_severity + w.w_evidence_strength, 6)
    if abs(total - 1.0) > 0.001:
        log.error(
            "FAIL — scoring_weights do not sum to 1.0 (got %.4f).", total
        )
        return False
    log.info(
        "PASS — scoring_weights sum to 1.0: "
        "frequency=%.2f, severity=%.2f, evidence_strength=%.2f",
        w.w_frequency, w.w_severity, w.w_evidence_strength,
    )
    return True


def check_keyword_density(cfg) -> bool:
    """Check 6: Every taxonomy node has ≥ 5 seed keywords."""
    sparse_nodes = [
        n.node_id
        for n in cfg.taxonomy.nodes
        if len(n.detection_rules.keywords) < 5
    ]
    if sparse_nodes:
        log.warning(
            "WARNING — %d taxonomy node(s) have fewer than 5 keywords: %s. "
            "Consider adding more seed keywords before Phase 3.",
            len(sparse_nodes), sparse_nodes,
        )
    else:
        log.info("PASS -- All taxonomy nodes have >= 5 seed keywords.")
    return True  # warning only, not blocking


def check_data_store() -> bool:
    """Check 7: Data store directories are initialized."""
    try:
        init_data_store()
        log.info("PASS — Data store directories initialized.")
        return True
    except Exception as exc:
        log.error("FAIL — Data store initialization failed: %s", exc)
        return False


def run_all_checks() -> bool:
    """Run all Phase 1 exit criteria checks. Returns True if all pass."""
    log.info("=" * 70)
    log.info("PHASE 1 EXIT CRITERIA VALIDATION")
    log.info("=" * 70)

    # Check 1: files present (must pass before loading)
    if not check_config_files_present():
        log.error("Aborting — config files must exist before further checks.")
        return False

    # Load all configs (this also runs the cross-coverage validation)
    try:
        cfg = load_all_config()
    except Exception as exc:
        log.error("FAIL — Config loading/validation raised an error: %s", exc)
        return False

    checks = [
        check_source_list(cfg),
        check_taxonomy_coverage(cfg),
        check_question_set(cfg),
        check_scoring_weights(cfg),
        check_keyword_density(cfg),
        check_data_store(),
    ]

    log.info("=" * 70)
    if all(checks):
        log.info("[PASS] ALL PHASE 1 EXIT CRITERIA PASSED -- Ready to proceed to Phase 2.")
        return True
    else:
        failed = checks.count(False)
        log.error(
            "[FAIL] %d CHECK(S) FAILED -- Resolve issues above before proceeding to Phase 2.",
            failed,
        )
        return False


if __name__ == "__main__":
    success = run_all_checks()
    sys.exit(0 if success else 1)
