"""
tests/test_phase1.py
Phase 1 — Foundation & Configuration
Unit tests for config loader, taxonomy coverage, and data store.

Run: pytest tests/test_phase1.py -v
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest
import yaml

# ── Fixtures and helpers ───────────────────────────────────────────────────


def _load_yaml(rel_path: str) -> dict:
    # Resolve relative to the engine/ package directory (where config/ lives)
    engine_dir = Path(__file__).parent.parent  # engine/tests/ -> engine/
    path = engine_dir / rel_path
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# =============================================================================
# Tests — source_list.yaml
# =============================================================================

class TestSourceList:
    def setup_method(self):
        self.data = _load_yaml("config/source_list.yaml")

    def test_yaml_parseable(self):
        """source_list.yaml must be valid YAML and non-empty."""
        assert self.data is not None
        assert "sources" in self.data
        assert len(self.data["sources"]) > 0

    def test_required_source_types_present(self):
        """All 7 source types must be configured (enabled or disabled)."""
        required = {"app_store", "play_store", "reddit", "forum", "social", "youtube", "review_qa"}
        configured = {s["source_type"] for s in self.data["sources"]}
        missing = required - configured
        assert not missing, f"Missing source types: {sorted(missing)}"

    def test_schema_fields_present(self):
        """Every source entry must have all required schema fields."""
        required_fields = {"source_type", "source_name", "enabled", "lookback_days", "volume_cap"}
        for source in self.data["sources"]:
            missing = required_fields - set(source.keys())
            assert not missing, (
                f"Source '{source.get('source_name', '?')}' missing fields: {missing}"
            )

    def test_lookback_days_positive(self):
        """lookback_days must be a positive integer for all sources."""
        for s in self.data["sources"]:
            assert isinstance(s["lookback_days"], int) and s["lookback_days"] > 0, (
                f"Source '{s['source_name']}' has invalid lookback_days: {s['lookback_days']}"
            )

    def test_volume_cap_positive(self):
        """volume_cap must be a positive integer for all sources."""
        for s in self.data["sources"]:
            assert isinstance(s["volume_cap"], int) and s["volume_cap"] > 0, (
                f"Source '{s['source_name']}' has invalid volume_cap: {s['volume_cap']}"
            )

    def test_at_least_one_source_enabled(self):
        """At least one source must be enabled."""
        enabled = [s for s in self.data["sources"] if s.get("enabled", False)]
        assert len(enabled) > 0, "No sources are enabled in source_list.yaml"


# =============================================================================
# Tests — taxonomy.yaml
# =============================================================================

class TestTaxonomy:
    def setup_method(self):
        self.data = _load_yaml("config/taxonomy.yaml")

    def test_yaml_parseable(self):
        assert self.data is not None
        assert "taxonomy" in self.data

    def test_minimum_node_count(self):
        """Must have ≥ 29 taxonomy nodes."""
        nodes = self.data["taxonomy"]
        assert len(nodes) >= 29, f"Only {len(nodes)} nodes found; minimum is 29."

    def test_minimum_dimension_count(self):
        """Must cover ≥ 10 distinct dimensions."""
        dims = {n["dimension"] for n in self.data["taxonomy"]}
        assert len(dims) >= 10, f"Only {len(dims)} dimensions found; minimum is 10."

    def test_node_ids_unique(self):
        """node_id values must be unique across the entire taxonomy."""
        ids = [n["node_id"] for n in self.data["taxonomy"]]
        assert len(ids) == len(set(ids)), "Duplicate node_id values found in taxonomy.yaml"

    def test_required_node_schema_fields(self):
        """Every node must have all required schema fields."""
        required = {"node_id", "label", "dimension", "sub_category", "question_refs", "detection_rules"}
        for node in self.data["taxonomy"]:
            missing = required - set(node.keys())
            assert not missing, f"Node '{node.get('node_id', '?')}' missing fields: {missing}"

    def test_question_refs_are_valid_ints(self):
        """question_refs must be lists of integers in range 1-10."""
        for node in self.data["taxonomy"]:
            refs = node.get("question_refs", [])
            assert isinstance(refs, list), f"Node '{node['node_id']}': question_refs must be a list."
            for ref in refs:
                assert isinstance(ref, int) and 1 <= ref <= 10, (
                    f"Node '{node['node_id']}': invalid question_ref {ref!r}"
                )

    def test_at_least_5_keywords_per_node(self):
        """Every node must have ≥ 5 seed keywords."""
        sparse = []
        for node in self.data["taxonomy"]:
            kws = node.get("detection_rules", {}).get("keywords", [])
            if len(kws) < 5:
                sparse.append((node["node_id"], len(kws)))
        assert not sparse, (
            f"The following nodes have < 5 keywords: {sparse}"
        )

    def test_embedding_hint_present(self):
        """Every node must have a non-empty embedding_hint."""
        missing_hint = []
        for node in self.data["taxonomy"]:
            hint = str(node.get("detection_rules", {}).get("embedding_hint", "")).strip()
            if not hint:
                missing_hint.append(node["node_id"])
        assert not missing_hint, f"Nodes missing embedding_hint: {missing_hint}"

    def test_all_questions_coverable(self):
        """Every question 1-10 must be reachable via at least one taxonomy node."""
        all_refs: set[int] = set()
        for node in self.data["taxonomy"]:
            all_refs.update(node.get("question_refs", []))
        missing_questions = set(range(1, 11)) - all_refs
        assert not missing_questions, (
            f"The following questions have no taxonomy coverage: {sorted(missing_questions)}"
        )

    def test_required_10_dimensions(self):
        """Verify the exact 10 expected behavioral dimensions are present."""
        expected_dims = {
            "Fit & Sizing",
            "Styling & Occasion",
            "Price & Value",
            "Trust & Reviews",
            "Return & Risk",
            "Social Validation",
            "Product Information",
            "Comparison Behavior",
            "Intent Signal",
            "Segment Markers",
        }
        actual_dims = {n["dimension"] for n in self.data["taxonomy"]}
        missing = expected_dims - actual_dims
        assert not missing, f"Missing expected dimensions: {missing}"


# =============================================================================
# Tests — question_set.yaml
# =============================================================================

class TestQuestionSet:
    def setup_method(self):
        self.data = _load_yaml("config/question_set.yaml")

    def test_yaml_parseable(self):
        assert self.data is not None
        assert "questions" in self.data

    def test_exactly_10_questions(self):
        assert len(self.data["questions"]) == 10, (
            f"Expected 10 questions, found {len(self.data['questions'])}"
        )

    def test_question_ids_1_to_10(self):
        """question_id must be integers 1 through 10 with no gaps or duplicates."""
        ids = sorted(q["question_id"] for q in self.data["questions"])
        assert ids == list(range(1, 11)), f"question_ids are not 1-10: {ids}"

    def test_required_question_schema_fields(self):
        required = {"question_id", "question_text", "related_dimensions"}
        for q in self.data["questions"]:
            missing = required - set(q.keys())
            assert not missing, f"Question {q.get('question_id', '?')} missing fields: {missing}"

    def test_all_dimensions_referenced(self):
        """Every question must reference at least one related dimension."""
        empty = [q["question_id"] for q in self.data["questions"]
                 if not q.get("related_dimensions")]
        assert not empty, f"Questions with no related_dimensions: {empty}"


# =============================================================================
# Tests — scoring_weights.yaml
# =============================================================================

class TestScoringWeights:
    def setup_method(self):
        self.data = _load_yaml("config/scoring_weights.yaml")

    def test_yaml_parseable(self):
        assert self.data is not None
        assert "scoring_weights" in self.data

    def test_weights_sum_to_one(self):
        """w_frequency + w_severity + w_evidence_strength must == 1.0."""
        sw = self.data["scoring_weights"]
        total = sw["w_frequency"] + sw["w_severity"] + sw["w_evidence_strength"]
        assert math.isclose(total, 1.0, abs_tol=0.001), (
            f"Scoring weights sum to {total:.4f}, not 1.0"
        )

    def test_all_weights_positive(self):
        sw = self.data["scoring_weights"]
        for key in ("w_frequency", "w_severity", "w_evidence_strength"):
            assert sw[key] > 0, f"{key} must be positive, got {sw[key]}"

    def test_confidence_thresholds_valid(self):
        """Confidence thresholds must be in (0, 1) and low_flag > minimum."""
        ct = self.data.get("confidence_thresholds", {})
        low = ct.get("low_confidence_flag", 0.5)
        minimum = ct.get("minimum_confidence", 0.3)
        assert 0 < minimum < low < 1.0, (
            f"Invalid confidence thresholds: minimum={minimum}, low_flag={low}"
        )

    def test_severity_intensity_has_three_levels(self):
        si = self.data.get("severity_intensity", {})
        assert "high" in si and "medium" in si and "low" in si, (
            "severity_intensity must define 'high', 'medium', and 'low' levels."
        )


# =============================================================================
# Tests — Config Loader (integration)
# =============================================================================

class TestConfigLoader:
    def test_load_all_config_no_exception(self):
        """load_all_config() must complete without raising."""
        from engine.config_loader import load_all_config
        cfg = load_all_config()
        assert cfg is not None

    def test_taxonomy_get_node(self):
        from engine.config_loader import load_taxonomy
        taxonomy = load_taxonomy()
        node = taxonomy.get_node("fit_sizing.size_uncertainty")
        assert node is not None
        assert node.label is not None

    def test_taxonomy_get_by_dimension(self):
        from engine.config_loader import load_taxonomy
        taxonomy = load_taxonomy()
        nodes = taxonomy.get_by_dimension("Fit & Sizing")
        assert len(nodes) >= 4, f"Expected ≥4 Fit & Sizing nodes, got {len(nodes)}"

    def test_question_set_get(self):
        from engine.config_loader import load_question_set
        qs = load_question_set()
        q = qs.get(1)
        assert q is not None
        assert "wishlist" in q.question_text.lower()


# =============================================================================
# Tests — Data Store
# =============================================================================

class TestDataStore:
    def test_init_data_store(self):
        """init_data_store() must create directories without error."""
        from engine.data_store import init_data_store, RAW_RECORDS_DIR, SIGNALS_DIR, OPPORTUNITIES_DIR
        init_data_store()
        assert RAW_RECORDS_DIR.exists()
        assert SIGNALS_DIR.exists()
        assert OPPORTUNITIES_DIR.exists()

    def test_write_and_read_raw_record(self, tmp_path, monkeypatch):
        """Write a mock RawRecord and read it back."""
        import engine.data_store as ds_module
        monkeypatch.setattr(ds_module, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_module, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_module, "OPPORTUNITIES_DIR", tmp_path / "opps")

        from engine.data_store import DataStore
        store = DataStore(run_id="test_run")

        record = {
            "record_id": "uuid-001",
            "source_type": "reddit",
            "source_name": "r/IndianFashionAddicts",
            "text": "The size chart on Myntra is completely useless.",
        }
        store.write_raw_record(record)
        all_records = store.read_all_raw_records()
        assert len(all_records) == 1
        assert all_records[0]["record_id"] == "uuid-001"

    def test_record_id_dedup_set(self, tmp_path, monkeypatch):
        """raw_record_ids() returns correct set for deduplication."""
        import engine.data_store as ds_module
        monkeypatch.setattr(ds_module, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_module, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_module, "OPPORTUNITIES_DIR", tmp_path / "opps")

        from engine.data_store import DataStore
        store = DataStore(run_id="test_dedup")
        store.write_raw_record({"record_id": "a", "text": "some text"})
        store.write_raw_record({"record_id": "b", "text": "other text"})
        ids = store.raw_record_ids()
        assert ids == {"a", "b"}
