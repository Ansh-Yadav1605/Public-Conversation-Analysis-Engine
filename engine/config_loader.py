"""
engine/config_loader.py
Public Conversation Analysis Engine — Configuration Loader & Validator

Loads and validates all four config files:
    - config/source_list.yaml
    - config/taxonomy.yaml
    - config/question_set.yaml
    - config/scoring_weights.yaml

Exposes typed dataclasses and a single load_all_config() entry point.

Usage:
    from engine.config_loader import load_all_config
    cfg = load_all_config()
    print(cfg.taxonomy.nodes[0].node_id)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from engine.logger import get_logger

log = get_logger(__name__)

# ── Config directory ───────────────────────────────────────────────────────
CONFIG_DIR = Path(__file__).parent / "config"


# =============================================================================
# Dataclasses — typed representations of each config file
# =============================================================================

@dataclass
class DetectionRules:
    keywords: list[str]
    embedding_hint: str


@dataclass
class TaxonomyNode:
    node_id: str
    label: str
    dimension: str
    sub_category: str
    question_refs: list[int]
    detection_rules: DetectionRules


@dataclass
class TaxonomyConfig:
    nodes: list[TaxonomyNode]

    def get_node(self, node_id: str) -> Optional[TaxonomyNode]:
        """Return a node by its dot-notation ID, or None if not found."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_by_dimension(self, dimension: str) -> list[TaxonomyNode]:
        """Return all nodes in a given dimension."""
        return [n for n in self.nodes if n.dimension == dimension]

    @property
    def dimensions(self) -> list[str]:
        """Return the unique list of dimension names."""
        seen: list[str] = []
        for n in self.nodes:
            if n.dimension not in seen:
                seen.append(n.dimension)
        return seen


@dataclass
class Question:
    question_id: int
    question_text: str
    related_dimensions: list[str]
    notes: str = ""


@dataclass
class QuestionSetConfig:
    questions: list[Question]

    def get(self, question_id: int) -> Optional[Question]:
        for q in self.questions:
            if q.question_id == question_id:
                return q
        return None


@dataclass
class ScoringWeights:
    w_frequency: float
    w_severity: float
    w_evidence_strength: float

    def validate(self) -> None:
        total = self.w_frequency + self.w_severity + self.w_evidence_strength
        if not math.isclose(total, 1.0, abs_tol=0.001):
            raise ValueError(
                f"scoring_weights must sum to 1.0, got {total:.4f}. "
                f"Check config/scoring_weights.yaml."
            )


@dataclass
class ConfidenceThresholds:
    low_confidence_flag: float = 0.50
    minimum_confidence: float = 0.30


@dataclass
class ScoringConfig:
    weights: ScoringWeights
    confidence_thresholds: ConfidenceThresholds
    severity_intensity: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SourceConfig:
    source_type: str
    source_name: str
    enabled: bool
    lookback_days: int
    volume_cap: int
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceListConfig:
    sources: list[SourceConfig]

    @property
    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]

    def get_by_type(self, source_type: str) -> list[SourceConfig]:
        return [s for s in self.sources if s.source_type == source_type]


@dataclass
class AllConfig:
    """Container for all four loaded and validated config objects."""
    source_list: SourceListConfig
    taxonomy: TaxonomyConfig
    question_set: QuestionSetConfig
    scoring: ScoringConfig


# =============================================================================
# Loaders
# =============================================================================

def _load_yaml(filename: str) -> dict[str, Any]:
    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. "
            f"Run Phase 1 setup to create config files."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    log.debug("Loaded config file: %s", path)
    return data


def load_source_list() -> SourceListConfig:
    """Load and parse config/source_list.yaml."""
    raw = _load_yaml("source_list.yaml")
    sources = [
        SourceConfig(
            source_type=s["source_type"],
            source_name=s["source_name"],
            enabled=bool(s.get("enabled", True)),
            lookback_days=int(s["lookback_days"]),
            volume_cap=int(s["volume_cap"]),
            config=s.get("config", {}),
        )
        for s in raw["sources"]
    ]
    log.info(
        "Loaded source list: %d sources total, %d enabled",
        len(sources),
        sum(1 for s in sources if s.enabled),
    )
    return SourceListConfig(sources=sources)


def load_taxonomy() -> TaxonomyConfig:
    """Load and parse config/taxonomy.yaml."""
    raw = _load_yaml("taxonomy.yaml")
    nodes: list[TaxonomyNode] = []
    for n in raw["taxonomy"]:
        dr_raw = n.get("detection_rules", {})
        nodes.append(
            TaxonomyNode(
                node_id=n["node_id"],
                label=n["label"],
                dimension=n["dimension"],
                sub_category=n["sub_category"],
                question_refs=[int(q) for q in n.get("question_refs", [])],
                detection_rules=DetectionRules(
                    keywords=dr_raw.get("keywords", []),
                    embedding_hint=str(dr_raw.get("embedding_hint", "")).strip(),
                ),
            )
        )
    log.info(
        "Loaded taxonomy: %d nodes across %d dimensions",
        len(nodes),
        len({n.dimension for n in nodes}),
    )
    return TaxonomyConfig(nodes=nodes)


def load_question_set() -> QuestionSetConfig:
    """Load and parse config/question_set.yaml."""
    raw = _load_yaml("question_set.yaml")
    questions = [
        Question(
            question_id=int(q["question_id"]),
            question_text=str(q["question_text"]).strip(),
            related_dimensions=q.get("related_dimensions", []),
            notes=str(q.get("notes", "")).strip(),
        )
        for q in raw["questions"]
    ]
    log.info("Loaded question set: %d questions", len(questions))
    return QuestionSetConfig(questions=questions)


def load_scoring_config() -> ScoringConfig:
    """Load and parse config/scoring_weights.yaml."""
    raw = _load_yaml("scoring_weights.yaml")
    sw = raw["scoring_weights"]
    weights = ScoringWeights(
        w_frequency=float(sw["w_frequency"]),
        w_severity=float(sw["w_severity"]),
        w_evidence_strength=float(sw["w_evidence_strength"]),
    )
    weights.validate()

    ct_raw = raw.get("confidence_thresholds", {})
    thresholds = ConfidenceThresholds(
        low_confidence_flag=float(ct_raw.get("low_confidence_flag", 0.50)),
        minimum_confidence=float(ct_raw.get("minimum_confidence", 0.30)),
    )

    severity_intensity = raw.get("severity_intensity", {})

    log.info(
        "Loaded scoring weights: frequency=%.2f, severity=%.2f, evidence=%.2f",
        weights.w_frequency,
        weights.w_severity,
        weights.w_evidence_strength,
    )
    return ScoringConfig(
        weights=weights,
        confidence_thresholds=thresholds,
        severity_intensity=severity_intensity,
    )


# =============================================================================
# Master loader + cross-file validation
# =============================================================================

def load_all_config() -> AllConfig:
    """
    Load all four config files and run cross-file coverage checks.

    Raises:
        FileNotFoundError: If any config file is missing.
        ValueError: If cross-coverage checks fail (orphan dimensions, unanswerable questions).

    Returns:
        AllConfig with all four validated config objects.
    """
    log.info("Loading all configuration files ...")
    source_list = load_source_list()
    taxonomy = load_taxonomy()
    question_set = load_question_set()
    scoring = load_scoring_config()

    _validate_coverage(taxonomy, question_set)

    log.info("All configuration files loaded and validated successfully.")
    return AllConfig(
        source_list=source_list,
        taxonomy=taxonomy,
        question_set=question_set,
        scoring=scoring,
    )


def _validate_coverage(taxonomy: TaxonomyConfig, question_set: QuestionSetConfig) -> None:
    """
    Cross-file coverage validation:
    1. Every taxonomy dimension must map to at least one question.
    2. Every question must be covered by at least one taxonomy node.
    """
    log.info("Running taxonomy <-> question coverage validation ...")

    all_question_ids = {q.question_id for q in question_set.questions}
    all_node_question_refs: set[int] = set()
    for node in taxonomy.nodes:
        all_node_question_refs.update(node.question_refs)

    # Check 1: every question is answerable via at least one taxonomy node
    unanswerable = all_question_ids - all_node_question_refs
    if unanswerable:
        raise ValueError(
            f"Coverage gap: the following questions have NO taxonomy nodes mapped to them: "
            f"{sorted(unanswerable)}. Update taxonomy.yaml to add question_refs."
        )

    # Check 2: every taxonomy dimension maps to at least one question
    for dim in taxonomy.dimensions:
        dim_nodes = taxonomy.get_by_dimension(dim)
        dim_question_refs: set[int] = set()
        for node in dim_nodes:
            dim_question_refs.update(node.question_refs)
        if not dim_question_refs:
            raise ValueError(
                f"Orphan dimension: '{dim}' has no question_refs across any of its nodes. "
                f"Add at least one question_ref to a node in this dimension."
            )

    log.info(
        "Coverage check passed: all %d questions answerable, all %d dimensions mapped.",
        len(all_question_ids),
        len(taxonomy.dimensions),
    )
