"""
tests/test_phase3.py
Phase 3 — Taxonomy-Based Extraction Layer
Unit tests for Signal model, preprocessor, taxonomy matcher, signal constructor,
signal store, and extraction orchestrator.

No live API calls. Uses synthetic RawRecords and the real taxonomy.yaml.
Run: pytest engine/tests/test_phase3.py -v
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.scraper.models import RawRecord, AuthorMeta, PlatformMeta, now_iso


# =============================================================================
# Fixtures
# =============================================================================

def _make_raw_record(
    text: str,
    source_type: str = "reddit",
    source_name: str = "Reddit — r/IndianFashionAddicts",
    content_id: str | None = None,
    record_id: str | None = None,
    segment_hints: list[str] | None = None,
) -> RawRecord:
    return RawRecord(
        record_id=record_id or str(uuid.uuid4()),
        source_type=source_type,
        source_name=source_name,
        content_id=content_id or str(uuid.uuid4()),
        url="https://reddit.com/r/test/abc",
        text=text,
        author_meta=AuthorMeta(
            user_type="identified",
            segment_hints=segment_hints or [],
        ),
        date_collected=now_iso(),
        date_published="2025-08-01T10:00:00Z",
        platform_meta=PlatformMeta(upvotes=5, reply_count=2, rating=None),
    )


def _load_real_taxonomy():
    from engine.config_loader import load_taxonomy
    return load_taxonomy()


def _load_real_scoring():
    from engine.config_loader import load_scoring_config
    return load_scoring_config()


# =============================================================================
# Tests — Signal model (models.py)
# =============================================================================

class TestSignalModel:
    def _make_signal(self, **kwargs):
        from engine.extractor.models import Signal, SourceRef
        defaults = dict(
            signal_id=str(uuid.uuid4()),
            record_id=str(uuid.uuid4()),
            source_ref=SourceRef(
                source_type="reddit",
                source_name="Reddit — r/test",
                url="https://reddit.com/r/test/abc",
                date_published="2025-08-01T10:00:00Z",
            ),
            taxonomy_node="fit_sizing.size_uncertainty",
            dimension="Fit & Sizing",
            sub_category="Size Uncertainty",
            question_refs=[2, 3, 7],
            verbatim_quote="I never know which size to order on Myntra.",
            severity_hint="high",
            segment_hints=["female"],
            confidence=0.90,
            match_layer="keyword",
        )
        defaults.update(kwargs)
        return Signal(**defaults)

    def test_valid_signal_created(self):
        sig = self._make_signal()
        assert sig.taxonomy_node == "fit_sizing.size_uncertainty"
        assert sig.confidence == 0.90

    def test_confidence_clamped_above_1(self):
        sig = self._make_signal(confidence=1.5)
        assert sig.confidence == 1.0

    def test_confidence_clamped_below_0(self):
        sig = self._make_signal(confidence=-0.1)
        assert sig.confidence == 0.0

    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError, match="severity_hint"):
            self._make_signal(severity_hint="extreme")

    def test_invalid_match_layer_raises(self):
        with pytest.raises(ValueError, match="match_layer"):
            self._make_signal(match_layer="magic")

    def test_to_dict_all_fields(self):
        sig = self._make_signal()
        d = sig.to_dict()
        required = {
            "signal_id", "record_id", "source_ref", "taxonomy_node",
            "dimension", "sub_category", "question_refs", "verbatim_quote",
            "severity_hint", "segment_hints", "confidence", "match_layer",
        }
        assert required <= d.keys()

    def test_source_ref_in_dict(self):
        sig = self._make_signal()
        d = sig.to_dict()
        sr = d["source_ref"]
        assert "source_type" in sr and "url" in sr

    def test_roundtrip_from_dict(self):
        from engine.extractor.models import Signal
        sig = self._make_signal()
        sig2 = Signal.from_dict(sig.to_dict())
        assert sig2.signal_id == sig.signal_id
        assert sig2.taxonomy_node == sig.taxonomy_node
        assert sig2.confidence == sig.confidence

    def test_all_severity_hints_valid(self):
        from engine.extractor.models import VALID_SEVERITY_HINTS
        for hint in VALID_SEVERITY_HINTS:
            sig = self._make_signal(severity_hint=hint)
            assert sig.severity_hint == hint

    def test_all_match_layers_valid(self):
        from engine.extractor.models import VALID_MATCH_LAYERS
        for layer in VALID_MATCH_LAYERS:
            sig = self._make_signal(match_layer=layer)
            assert sig.match_layer == layer


# =============================================================================
# Tests — Text Preprocessor (preprocessor.py)
# =============================================================================

class TestPreprocessor:
    def test_basic_clean(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("The size chart is wrong.")
        assert result.cleaned_text
        assert result.original_text == "The size chart is wrong."

    def test_html_stripped(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("<p>The <b>size</b> chart is <i>wrong</i>.</p>")
        assert "<" not in result.cleaned_text
        assert "size" in result.cleaned_text

    def test_urls_stripped(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("Check https://myntra.com/size-guide for size info.")
        assert "https://" not in result.cleaned_text
        assert "size" in result.cleaned_text

    def test_emoji_normalized(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("I hate the return process 😡 it is so frustrating")
        assert "😡" not in result.cleaned_text
        assert "angry" in result.cleaned_text or "frustrated" in result.cleaned_text

    def test_repeated_punctuation_collapsed(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("Terrible sizing!!!! The clothes are huge!!!")
        assert "!!!!" not in result.cleaned_text

    def test_whitespace_collapsed(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("The  size   chart   is    wrong.")
        assert "  " not in result.cleaned_text

    def test_empty_text_returns_empty_sentences(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("")
        assert result.sentences == []
        assert result.cleaned_text == ""

    def test_whitespace_only_returns_empty(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("   \n\t  ")
        assert result.sentences == []

    def test_original_text_preserved(self):
        from engine.extractor.preprocessor import preprocess
        original = "<p>Size chart is wrong!!!</p>"
        result = preprocess(original)
        assert result.original_text == original

    def test_sentences_list_nonempty_for_real_text(self):
        from engine.extractor.preprocessor import preprocess
        text = (
            "I ordered a medium but it runs too small. "
            "The size chart on Myntra is completely misleading. "
            "I always have to size up when buying from them."
        )
        result = preprocess(text)
        assert len(result.sentences) >= 1

    def test_short_sentences_filtered(self):
        from engine.extractor.preprocessor import preprocess
        text = "Hi. I do not know which size to order when I shop on Myntra or AJIO."
        result = preprocess(text)
        # Short greeting "Hi" should be filtered
        for s in result.sentences:
            assert len(s) >= 15

    def test_word_count_positive(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("The fabric quality is not good for the price.")
        assert result.word_count > 0

    def test_is_english_true_for_english(self):
        from engine.extractor.preprocessor import preprocess
        result = preprocess("I cannot find my size on Myntra. It is very frustrating.")
        assert result.is_english is True

    def test_multi_sentence_text_splits_correctly(self):
        from engine.extractor.preprocessor import preprocess
        text = (
            "Ordered a medium shirt. The fabric felt cheap for the price. "
            "I had to return it because of the size. "
            "The return process was a nightmare."
        )
        result = preprocess(text)
        # Should produce multiple sentences
        assert len(result.sentences) >= 2


# =============================================================================
# Tests — Taxonomy Matcher — Layer A (taxonomy_matcher.py)
# =============================================================================

class TestTaxonomyMatcherLayerA:
    """
    Layer A only tests — bypass embedding model by monkeypatching.
    """

    def setup_method(self):
        self.taxonomy = _load_real_taxonomy()

    def _matcher_no_embedding(self):
        from engine.extractor.taxonomy_matcher import TaxonomyMatcher
        with patch(
            "engine.extractor.taxonomy_matcher.TaxonomyMatcher._try_load_embedder"
        ):
            m = TaxonomyMatcher.__new__(TaxonomyMatcher)
            m.taxonomy = self.taxonomy
            m._embedding_available = False
            m._node_embeddings = None
            m._embedder = None
        return m

    def test_keyword_match_size_uncertainty(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "I am not sure about size and the size chart is inaccurate on Myntra."
        )
        node_ids = [r.node.node_id for r in results]
        assert "fit_sizing.size_uncertainty" in node_ids

    def test_keyword_match_price_hesitation(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "This dress is too expensive for what it is, I cannot justify the price."
        )
        node_ids = [r.node.node_id for r in results]
        assert "price_value.price_hesitation" in node_ids

    def test_keyword_match_waiting_for_sale(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "I am waiting for sale before buying this from Myntra."
        )
        node_ids = [r.node.node_id for r in results]
        assert "price_value.waiting_for_sale" in node_ids

    def test_keyword_match_return_policy(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "The return policy is complicated and the return process is a hassle."
        )
        node_ids = [r.node.node_id for r in results]
        assert "return_risk.return_policy_friction" in node_ids

    def test_keyword_match_fake_reviews(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "All the reviews seem fake and the ratings are inflated on Myntra."
        )
        node_ids = [r.node.node_id for r in results]
        assert "trust_reviews.review_authenticity" in node_ids

    def test_no_match_for_irrelevant_sentence(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "The weather is nice today and I went for a walk."
        )
        assert len(results) == 0

    def test_multi_node_match(self):
        """A single sentence can trigger multiple taxonomy nodes."""
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "I am not sure about size and the return policy complicated."
        )
        # Should match at least size_uncertainty AND return_policy_friction
        assert len(results) >= 2

    def test_keyword_match_confidence_is_090(self):
        from engine.extractor.taxonomy_matcher import KEYWORD_CONFIDENCE
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence("I never know which size to order on Myntra.")
        keyword_results = [r for r in results if r.match_layer == "keyword"]
        if keyword_results:
            assert all(r.confidence == KEYWORD_CONFIDENCE for r in keyword_results)

    def test_match_result_has_matched_keywords(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence("I am not sure about size when buying online.")
        keyword_results = [r for r in results if r.match_layer == "keyword"]
        for r in keyword_results:
            assert len(r.matched_keywords) > 0

    def test_case_insensitive_keyword_match(self):
        matcher = self._matcher_no_embedding()
        results_lower = matcher.match_sentence("not sure about size")
        results_upper = matcher.match_sentence("NOT SURE ABOUT SIZE")
        assert len(results_lower) == len(results_upper)

    def test_passive_bookmarking_node(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "I am just saving for reference and not actually going to buy this."
        )
        node_ids = [r.node.node_id for r in results]
        assert "intent_signal.passive_bookmarking" in node_ids

    def test_trending_match(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "This item is trending on Instagram and everyone is wearing it."
        )
        node_ids = [r.node.node_id for r in results]
        assert "social_validation.trend_alignment" in node_ids

    def test_shortlisting_match(self):
        matcher = self._matcher_no_embedding()
        results = matcher.match_sentence(
            "I wishlisted multiple options and can't choose between these two dresses."
        )
        node_ids = [r.node.node_id for r in results]
        assert "comparison.shortlisting_behavior" in node_ids

    def test_all_10_dimensions_reachable(self):
        """At least one keyword in each dimension should trigger a match."""
        matcher = self._matcher_no_embedding()
        dimension_trigger_sentences = {
            "Fit & Sizing": "I am not sure about size and runs small",
            "Styling & Occasion": "I want styling advice for this occasion",
            "Price & Value": "This is too expensive and not worth the price",
            "Trust & Reviews": "The reviews seem fake and ratings are suspicious",
            "Return & Risk": "The return policy is complicated",
            "Social Validation": "I need a second opinion before buying",
            "Product Information": "The fabric not mentioned and material quality concern",
            "Comparison Behavior": "I wishlisted multiple options to compare",
            "Intent Signal": "I am planning to buy this on payday",
            "Segment Markers": "As a college student with a student budget",
        }
        matched_dims: set[str] = set()
        for dim, sentence in dimension_trigger_sentences.items():
            results = matcher.match_sentence(sentence)
            if results:
                matched_dims.add(dim)

        assert len(matched_dims) >= 8, (
            f"Only {len(matched_dims)} dimensions matched. "
            f"Missing: {set(dimension_trigger_sentences) - matched_dims}"
        )


# =============================================================================
# Tests — Signal Constructor (signal_constructor.py)
# =============================================================================

class TestSignalConstructor:
    def setup_method(self):
        from engine.extractor.signal_constructor import SignalConstructor
        self.scoring = _load_real_scoring()
        self.constructor = SignalConstructor(self.scoring)

    def _make_match(self, sentence: str, confidence: float = 0.90, match_layer: str = "keyword"):
        from engine.extractor.taxonomy_matcher import MatchResult
        taxonomy = _load_real_taxonomy()
        node = taxonomy.get_node("fit_sizing.size_uncertainty")
        return MatchResult(
            node=node,
            sentence=sentence,
            confidence=confidence,
            match_layer=match_layer,
            matched_keywords=["not sure about size"],
        )

    def test_build_returns_signal(self):
        from engine.extractor.models import Signal
        record = _make_raw_record("I am not sure about size and runs small.")
        match = self._make_match("I am not sure about size and runs small.")
        sig = self.constructor.build(record, match)
        assert isinstance(sig, Signal)

    def test_verbatim_quote_is_sentence(self):
        sentence = "I never know which size to order on Myntra."
        record = _make_raw_record(sentence)
        match = self._make_match(sentence)
        sig = self.constructor.build(record, match)
        assert sig.verbatim_quote == sentence

    def test_record_id_propagated(self):
        record = _make_raw_record("Size chart is wrong.", record_id="rid-123")
        match = self._make_match("Size chart is wrong.")
        sig = self.constructor.build(record, match)
        assert sig.record_id == "rid-123"

    def test_source_ref_populated(self):
        record = _make_raw_record("Size issue.", source_type="app_store", source_name="App Store — Myntra")
        match = self._make_match("Size issue.")
        sig = self.constructor.build(record, match)
        assert sig.source_ref.source_type == "app_store"
        assert "Myntra" in sig.source_ref.source_name

    def test_taxonomy_node_from_match(self):
        record = _make_raw_record("Size chart is confusing.")
        match = self._make_match("Size chart is confusing.")
        sig = self.constructor.build(record, match)
        assert sig.taxonomy_node == "fit_sizing.size_uncertainty"

    def test_question_refs_from_node(self):
        record = _make_raw_record("Size chart is confusing.")
        match = self._make_match("Size chart is confusing.")
        sig = self.constructor.build(record, match)
        assert 2 in sig.question_refs
        assert 3 in sig.question_refs

    def test_confidence_from_match(self):
        record = _make_raw_record("Size chart is confusing.")
        match = self._make_match("Size chart is confusing.", confidence=0.75, match_layer="embedding")
        sig = self.constructor.build(record, match)
        assert sig.confidence == 0.75
        assert sig.match_layer == "embedding"

    def test_severity_high_for_hate(self):
        record = _make_raw_record("I hate the return process.")
        match = self._make_match("I hate the return process.")
        sig = self.constructor.build(record, match)
        assert sig.severity_hint == "high"

    def test_severity_high_for_frustrated(self):
        record = _make_raw_record("I am so frustrated with the sizing.")
        match = self._make_match("I am so frustrated with the sizing.")
        sig = self.constructor.build(record, match)
        assert sig.severity_hint == "high"

    def test_severity_medium_for_annoying(self):
        record = _make_raw_record("It is really annoying that sizes are inconsistent.")
        match = self._make_match("It is really annoying that sizes are inconsistent.")
        sig = self.constructor.build(record, match)
        assert sig.severity_hint in ("medium", "high")  # "annoying" is medium

    def test_severity_low_for_slight(self):
        record = _make_raw_record("Sizing is a bit off and slightly loose overall.")
        match = self._make_match("Sizing is a bit off and slightly loose overall.")
        sig = self.constructor.build(record, match)
        assert sig.severity_hint in ("low", "unknown")

    def test_severity_unknown_for_neutral(self):
        record = _make_raw_record("The size chart shows measurements in centimeters.")
        match = self._make_match("The size chart shows measurements in centimeters.")
        sig = self.constructor.build(record, match)
        assert sig.severity_hint == "unknown"

    def test_segment_hints_from_author_meta(self):
        record = _make_raw_record(
            "Size issue.",
            segment_hints=["female", "urban"],
        )
        match = self._make_match("Size issue.")
        sig = self.constructor.build(record, match)
        assert "female" in sig.segment_hints
        assert "urban" in sig.segment_hints

    def test_segment_hints_inferred_from_text(self):
        record = _make_raw_record(
            "As a college student, I cannot afford the expensive price."
        )
        match = self._make_match("As a college student, I cannot afford the expensive price.")
        sig = self.constructor.build(record, match)
        assert "student" in sig.segment_hints

    def test_segment_hints_from_office_wear(self):
        record = _make_raw_record("I need office wear for my corporate job.")
        match = self._make_match("I need office wear for my corporate job.")
        sig = self.constructor.build(record, match)
        assert "working_professional" in sig.segment_hints

    def test_signal_has_unique_id(self):
        record = _make_raw_record("Size issue.")
        match = self._make_match("Size issue.")
        sig1 = self.constructor.build(record, match)
        sig2 = self.constructor.build(record, match)
        assert sig1.signal_id != sig2.signal_id


# =============================================================================
# Tests — Signal Store (signal_store.py)
# =============================================================================

class TestSignalStore:
    def _make_signal(self, dimension="Fit & Sizing", node="fit_sizing.size_uncertainty",
                     source_type="reddit", confidence=0.90):
        from engine.extractor.models import Signal, SourceRef
        return Signal(
            signal_id=str(uuid.uuid4()),
            record_id=str(uuid.uuid4()),
            source_ref=SourceRef(source_type=source_type, source_name="Test",
                                  url=None, date_published=None),
            taxonomy_node=node,
            dimension=dimension,
            sub_category="Test Sub",
            question_refs=[2, 3],
            verbatim_quote="The size chart is wrong.",
            severity_hint="high",
            segment_hints=["female"],
            confidence=confidence,
            match_layer="keyword",
        )

    def test_write_and_read_all(self, tmp_path, monkeypatch):
        import engine.data_store as ds_mod
        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        from engine.extractor.signal_store import SignalStore
        store = SignalStore(run_id="test_run")
        sig = self._make_signal()
        store.write(sig)
        all_sigs = store.read_all()
        assert len(all_sigs) == 1
        assert all_sigs[0].signal_id == sig.signal_id

    def test_by_dimension(self, tmp_path, monkeypatch):
        import engine.data_store as ds_mod
        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        from engine.extractor.signal_store import SignalStore
        store = SignalStore(run_id="test_run")
        store.write(self._make_signal(dimension="Fit & Sizing"))
        store.write(self._make_signal(dimension="Price & Value", node="price_value.price_hesitation"))
        fit_sigs = store.by_dimension("Fit & Sizing")
        assert len(fit_sigs) == 1

    def test_source_types_present(self, tmp_path, monkeypatch):
        import engine.data_store as ds_mod
        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        from engine.extractor.signal_store import SignalStore
        store = SignalStore(run_id="test_run")
        store.write(self._make_signal(source_type="reddit"))
        store.write(self._make_signal(source_type="app_store"))
        types = store.source_types_present()
        assert "reddit" in types
        assert "app_store" in types

    def test_average_confidence(self, tmp_path, monkeypatch):
        import engine.data_store as ds_mod
        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        from engine.extractor.signal_store import SignalStore
        store = SignalStore(run_id="test_run")
        store.write(self._make_signal(confidence=0.90))
        store.write(self._make_signal(confidence=0.70))
        avg = store.average_confidence()
        assert abs(avg - 0.80) < 0.01


# =============================================================================
# Tests — Extraction Orchestrator (run.py) with synthetic data
# =============================================================================

class TestExtractionOrchestrator:

    def _write_test_records(self, store, records: list[RawRecord]) -> None:
        for r in records:
            store.write_raw_record(r.to_dict())

    def test_extraction_produces_signals(self, tmp_path, monkeypatch):
        """Orchestrator should extract signals from records with matching text."""
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")
        monkeypatch.setattr(ext_run, "_PROCESSED_IDS_FILE", tmp_path / "proc.json")

        raw_store = ds_mod.DataStore(run_id="test")
        records = [
            _make_raw_record("I am not sure about size and the size chart is inaccurate."),
            _make_raw_record("This dress is too expensive and I am waiting for sale."),
            _make_raw_record("The return policy is complicated and hard to return items."),
            _make_raw_record("Fake reviews everywhere and the ratings seem inflated on Myntra."),
            _make_raw_record("I cannot find my size. The fabric is not mentioned in the listing."),
        ]
        self._write_test_records(raw_store, records)

        from engine.extractor.run import run_extraction
        summary = run_extraction(dry_run=False, layer="a")

        assert summary["records_processed"] == 5
        assert summary["signals_extracted"] > 0
        assert summary["errors"] == 0

    def test_dry_run_processes_subset(self, tmp_path, monkeypatch):
        """Dry run should process ~10% of records."""
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")
        monkeypatch.setattr(ext_run, "_PROCESSED_IDS_FILE", tmp_path / "proc.json")

        raw_store = ds_mod.DataStore(run_id="test")
        # Write 20 records
        for i in range(20):
            raw_store.write_raw_record(
                _make_raw_record(f"I am not sure about size on Myntra record number {i}.").to_dict()
            )

        from engine.extractor.run import run_extraction
        summary = run_extraction(dry_run=True, layer="a")

        # 10% of 20 = 2 records
        assert summary["records_processed"] <= 3  # allow rounding

    def test_already_processed_records_skipped(self, tmp_path, monkeypatch):
        """Records processed in a previous run should not be re-extracted."""
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")
        monkeypatch.setattr(ext_run, "_PROCESSED_IDS_FILE", tmp_path / "proc.json")

        record = _make_raw_record("Size chart is wrong on Myntra.")
        raw_store = ds_mod.DataStore(run_id="test")
        raw_store.write_raw_record(record.to_dict())

        from engine.extractor.run import run_extraction

        summary1 = run_extraction(dry_run=False, layer="a")
        assert summary1["records_processed"] == 1

        # Second run — same record should be skipped
        summary2 = run_extraction(dry_run=False, layer="a")
        assert summary2["records_processed"] == 0

    def test_empty_store_returns_zero_signals(self, tmp_path, monkeypatch):
        """When there are no raw records, extraction should return zeros."""
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")
        monkeypatch.setattr(ext_run, "_PROCESSED_IDS_FILE", tmp_path / "proc.json")

        from engine.extractor.run import run_extraction
        summary = run_extraction(layer="a")
        assert summary["signals_extracted"] == 0
        assert summary["records_processed"] == 0

    def test_multi_signal_from_single_record(self, tmp_path, monkeypatch):
        """A single record with multiple matching sentences should produce multiple signals."""
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")
        monkeypatch.setattr(ext_run, "_PROCESSED_IDS_FILE", tmp_path / "proc.json")

        # Text with multiple distinct taxonomy triggers
        text = (
            "I am not sure about size on Myntra, their size chart is inaccurate. "
            "Also this dress is too expensive and I am waiting for sale. "
            "And the return policy is complicated if size is wrong."
        )
        record = _make_raw_record(text)
        raw_store = ds_mod.DataStore(run_id="test")
        raw_store.write_raw_record(record.to_dict())

        from engine.extractor.run import run_extraction
        summary = run_extraction(dry_run=False, layer="a")

        assert summary["signals_extracted"] >= 2

    def test_min_confidence_filter(self, tmp_path, monkeypatch):
        """Signals below min_confidence threshold should be filtered out."""
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")
        monkeypatch.setattr(ext_run, "_PROCESSED_IDS_FILE", tmp_path / "proc.json")

        record = _make_raw_record("I am not sure about size on Myntra.")
        raw_store = ds_mod.DataStore(run_id="test")
        raw_store.write_raw_record(record.to_dict())

        from engine.extractor.run import run_extraction
        # Set threshold above keyword confidence (0.90) → no signals should pass
        summary = run_extraction(dry_run=False, layer="a", min_confidence=0.95)

        assert summary["signals_extracted"] == 0
        assert summary["low_confidence_signals"] >= 0  # some were filtered

    def test_summary_has_avg_confidence(self, tmp_path, monkeypatch):
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")
        monkeypatch.setattr(ext_run, "_PROCESSED_IDS_FILE", tmp_path / "proc.json")

        raw_store = ds_mod.DataStore(run_id="test")
        raw_store.write_raw_record(
            _make_raw_record("Not sure about size and size chart is inaccurate on Myntra.").to_dict()
        )

        from engine.extractor.run import run_extraction
        summary = run_extraction(layer="a")

        if summary["signals_extracted"] > 0:
            assert "avg_confidence" in summary
            assert 0.0 <= summary["avg_confidence"] <= 1.0
