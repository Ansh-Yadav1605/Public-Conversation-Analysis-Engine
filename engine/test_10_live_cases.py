"""
engine/test_10_live_cases.py
Public Conversation Analysis Engine — 10 Live Environment Verification Test Cases

Runs 10 comprehensive operational test cases validating the entire pipeline in the live environment:
  Case 1:  Configuration Loading & Cross-File Integrity (All 4 YAMLs, 10 Dimensions, 10 Questions)
  Case 2:  Scraper Normalization Robustness (Handles dirty/noisy text, Unicode, missing fields)
  Case 3:  Cross-Run Deduplication & Store Fingerprinting (Prevents double ingestion)
  Case 4:  Live Connector Interface & Fallback Gracefulness (Public connectors, error handling)
  Case 5:  Text Preprocessor Pipeline (HTML stripping, emoji mapping, sentence tokenization)
  Case 6:  10-Dimension Taxonomy Matching Coverage (All 10 behavioral dimensions trigger signals)
  Case 7:  Signal Construction & Context Extraction (Severity hint & segment inference)
  Case 8:  Cross-Source Evidence Filtering (Enforces >= 2 platform diversity threshold)
  Case 9:  Priority Scoring Formula & Ranker Determinism (Composite weights sum, tie-breaking)
  Case 10: End-to-End Pipeline Execution & Multi-Format Export (.md, .json, .csv with Q1-Q10 answered)

Usage:
    python engine/test_10_live_cases.py
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.analyzer.grouper import CandidateCluster, SignalGrouper
from engine.analyzer.models import OpportunityArea, OpportunityScores, RepresentativeQuote
from engine.analyzer.opportunity_store import OpportunityStore
from engine.analyzer.ranker import OpportunityRanker
from engine.analyzer.scorer import OpportunityScorer
from engine.analyzer.synthesizer import OpportunitySynthesizer
from engine.analyzer.validator import CrossSourceValidator
from engine.config_loader import load_all_config
from engine.data_store import DataStore
from engine.extractor.models import Signal, SourceRef
from engine.extractor.preprocessor import preprocess
from engine.extractor.signal_constructor import SignalConstructor
from engine.extractor.signal_store import SignalStore
from engine.extractor.taxonomy_matcher import TaxonomyMatcher
from engine.logger import get_logger
from engine.output.export import export_all, to_csv, to_json, to_markdown
from engine.output.report_builder import ReportBuilder
from engine.scraper.deduplicator import Deduplicator
from engine.scraper.models import AuthorMeta, PlatformMeta, RawRecord, now_iso
from engine.scraper.normalizer import normalize
from run_pipeline import run_full_pipeline

log = get_logger("engine.live_test")


def _make_signal(
    source_type: str = "reddit",
    severity_hint: str = "high",
    confidence: float = 0.90,
) -> Signal:
    return Signal(
        signal_id=str(uuid.uuid4()),
        record_id=str(uuid.uuid4()),
        source_ref=SourceRef(
            source_type=source_type,
            source_name=f"Source {source_type}",
            url=f"https://{source_type}.com/test",
            date_published="2025-08-01T10:00:00Z",
        ),
        taxonomy_node="fit_sizing.size_uncertainty",
        dimension="Fit & Sizing",
        sub_category="Size Uncertainty",
        question_refs=[2, 3, 7],
        verbatim_quote="The size chart is inaccurate and confusing.",
        severity_hint=severity_hint,
        segment_hints=["female"],
        confidence=confidence,
        match_layer="keyword",
    )


def print_case_header(num: int, title: str) -> None:
    print(f"\n{'='*75}")
    print(f"  CASE {num:02d}: {title}")
    print(f"{'='*75}")


def test_case_1() -> bool:
    """Case 1: Configuration Loading & Cross-File Integrity."""
    print_case_header(1, "Configuration Loading & Cross-File Integrity")
    cfg = load_all_config()
    
    # Assertions
    assert len(cfg.source_list.sources) >= 7, "Must have >= 7 sources configured"
    assert len(cfg.taxonomy.nodes) >= 29, "Must have >= 29 taxonomy nodes"
    assert len(cfg.taxonomy.dimensions) >= 10, "Must have >= 10 dimensions"
    assert len(cfg.question_set.questions) == 10, "Must have exactly 10 questions"
    total_weights = (
        cfg.scoring.weights.w_frequency
        + cfg.scoring.weights.w_severity
        + cfg.scoring.weights.w_evidence_strength
    )
    assert abs(total_weights - 1.0) < 0.001, "Scoring weights must sum to 1.0"
    
    print(f"  [PASS] 4 YAML configs loaded successfully.")
    print(f"         - Sources configured: {len(cfg.source_list.sources)} (Enabled: {len(cfg.source_list.enabled_sources)})")
    print(f"         - Taxonomy Nodes: {len(cfg.taxonomy.nodes)} across {len(cfg.taxonomy.dimensions)} dimensions")
    print(f"         - Behavioral Questions: {len(cfg.question_set.questions)}")
    print(f"         - Scoring Weights: freq={cfg.scoring.weights.w_frequency}, sev={cfg.scoring.weights.w_severity}, ev={cfg.scoring.weights.w_evidence_strength} (Sum: {total_weights:.2f})")
    return True


def test_case_2() -> bool:
    """Case 2: Scraper Normalization Robustness."""
    print_case_header(2, "Scraper Normalization Robustness (Dirty Text, Unicode & Varied Formats)")
    test_raw_samples = [
        ("app_store", "AppStore", {"id": "101", "title": "Good app!", "content": "  Sizing is completely off   on myntra  ", "rating": 3, "userName": "Riya"}),
        ("play_store", "PlayStore", {"reviewId": "202", "content": "Size chart not accurate 🔥👕", "score": 2, "thumbsUpCount": 10, "userName": "Aman"}),
        ("reddit", "Reddit", {"id": "303", "record_kind": "post", "title": "Price too high", "selftext": "Waiting for big sale before buying", "score": 45, "author": "user_a"}),
        ("forum", "Quora", {"content_id": "404", "url": "https://quora.com/q1", "text": "Are Myntra clothes true to size?", "author": "Sneha"}),
        ("social", "Twitter", {"id": "505", "text": "Return process is a complete hassle @Myntra #fail", "public_metrics": {"like_count": 5}}),
        ("youtube", "YouTube", {"comment_id": "606", "video_id": "v1", "text": "Fabric quality does not match pictures.", "author_name": "Pooja"}),
        ("review_qa", "Myntra QA", {"content_id": "707", "url": "https://myntra.com/p1", "text": "Q: Is this pure cotton? A: Poly-cotton blend."}),
    ]
    
    for src_type, src_name, payload in test_raw_samples:
        rec = normalize(src_type, src_name, payload)
        assert rec is not None, f"Failed to normalize {src_type}"
        assert rec.record_id, f"Record ID missing for {src_type}"
        assert rec.text and not rec.text.startswith(" "), f"Text improperly cleaned for {src_type}"
        assert rec.source_type == src_type

    print(f"  [PASS] Successfully normalized dirty sample records across all 7 source types.")
    return True


def test_case_3() -> bool:
    """Case 3: Cross-Run Deduplication & Store Fingerprinting."""
    print_case_header(3, "Cross-Run Deduplication & Store Fingerprinting")
    with tempfile.TemporaryDirectory() as tmpdir:
        fp_file = Path(tmpdir) / "dedup_fps.json"
        
        # Monkeypatch deduplicator path
        import engine.scraper.deduplicator as dedup_mod
        orig_fp = dedup_mod.FINGERPRINT_FILE
        dedup_mod.FINGERPRINT_FILE = fp_file
        
        try:
            dedup = Deduplicator()
            rec = RawRecord(
                record_id="r-001",
                source_type="reddit",
                source_name="r/test",
                content_id="post_999",
                url=None,
                text="The fabric is cheap and size chart is misleading.",
                author_meta=AuthorMeta(),
                date_collected=now_iso(),
                date_published=None,
                platform_meta=PlatformMeta(),
            )
            
            assert not dedup.is_duplicate(rec), "First check should not be duplicate"
            dedup.mark_seen(rec)
            assert dedup.is_duplicate(rec), "Second check must be marked duplicate"
            dedup.save()
            
            # Re-instantiate deduplicator (simulating a new pipeline run)
            dedup2 = Deduplicator()
            assert dedup2.is_duplicate(rec), "Persisted fingerprint must detect duplicate in new instance"
            print(f"  [PASS] Fingerprint hash persisted and detected across independent runs.")
        finally:
            dedup_mod.FINGERPRINT_FILE = orig_fp
    return True


def test_case_4() -> bool:
    """Case 4: Live Connector Interface & Fallback Gracefulness."""
    print_case_header(4, "Live Connector Interface & Fallback Gracefulness")
    from engine.config_loader import SourceConfig
    from engine.scraper.connector_app_store import AppStoreConnector
    from engine.scraper.connector_forum import ForumConnector
    from engine.scraper.connector_reddit import RedditConnector
    from engine.scraper.connector_social import SocialConnector
    from engine.scraper.connector_youtube import YouTubeConnector
    
    # Check that missing keys or connection issues degrade gracefully to [] without crashing
    c_reddit = RedditConnector(SourceConfig("reddit", "Reddit Test", True, 30, 5, {"subreddit": "test", "search_keywords": ["test"]}))
    assert isinstance(c_reddit.fetch(), list), "Reddit connector must return list even without keys"
    
    c_social = SocialConnector(SourceConfig("social", "Twitter Test", True, 30, 5, {"platform": "twitter", "search_queries": ["test"]}))
    assert isinstance(c_social.fetch(), list), "Social connector must return list even without keys"

    c_youtube = YouTubeConnector(SourceConfig("youtube", "YT Test", True, 30, 5, {"search_queries": ["test"]}))
    assert isinstance(c_youtube.fetch(), list), "YouTube connector must return list even without keys"

    print(f"  [PASS] All connectors handle unauthenticated / fallback states gracefully (return []).")
    return True


def test_case_5() -> bool:
    """Case 5: Text Preprocessor Pipeline."""
    print_case_header(5, "Text Preprocessor Pipeline (HTML, URLs, Emojis, Sentence Splits)")
    dirty_text = (
        "<html><body>I hate the size chart! 😡 It is completely wrong. "
        "Check this link https://example.com/product for details. "
        "Also the return process took 2 weeks!!!! 📦💔</body></html>"
    )
    result = preprocess(dirty_text)
    
    assert "<" not in result.cleaned_text, "HTML tags must be stripped"
    assert "https://" not in result.cleaned_text, "URLs must be stripped"
    assert "😡" not in result.cleaned_text and "📦" not in result.cleaned_text, "Emojis must be normalized"
    assert len(result.sentences) >= 2, f"Expected multiple sentences, got {len(result.sentences)}"
    assert result.is_english is True, "English text should be identified"
    
    print(f"  [PASS] Preprocessor correctly cleaned text and split into {len(result.sentences)} valid sentences.")
    for i, s in enumerate(result.sentences, 1):
        print(f"         Sentence {i}: \"{s}\"")
    return True


def test_case_6() -> bool:
    """Case 6: 10-Dimension Taxonomy Matching Coverage."""
    print_case_header(6, "10-Dimension Taxonomy Matching Coverage")
    cfg = load_all_config()
    matcher = TaxonomyMatcher(cfg.taxonomy)
    # Disable embedding model for purely deterministic keyword verification
    matcher._embedding_available = False
    
    sample_utterances = {
        "Fit & Sizing": "I am not sure about size and the size chart is inaccurate on Myntra.",
        "Styling & Occasion": "I need styling advice and don't know how to style this dress.",
        "Price & Value": "This shirt is too expensive and I am waiting for sale.",
        "Trust & Reviews": "The reviews seem fake and the ratings are inflated.",
        "Return & Risk": "The return policy is complicated and hard to return.",
        "Social Validation": "I need a second opinion and want to know if this is trending.",
        "Product Information": "The fabric not mentioned and no material details in the description.",
        "Comparison Behavior": "I wishlisted multiple options to compare prices across apps.",
        "Intent Signal": "I am planning to buy this on payday when I get salary.",
        "Segment Markers": "As a college student with a tight student budget.",
    }
    
    matched_dims = set()
    for expected_dim, text in sample_utterances.items():
        matches = matcher.match_sentence(text)
        assert len(matches) > 0, f"No matches found for dimension '{expected_dim}'"
        dims = {m.node.dimension for m in matches}
        assert expected_dim in dims, f"Expected {expected_dim}, got {dims}"
        matched_dims.add(expected_dim)
        print(f"  [PASS] Matched '{expected_dim}' -> Node: {matches[0].node.node_id} (conf: {matches[0].confidence:.2f})")
    
    assert len(matched_dims) == 10, "All 10 dimensions must match"
    return True


def test_case_7() -> bool:
    """Case 7: Signal Construction & Context Extraction."""
    print_case_header(7, "Signal Construction & Context Extraction (Severity & Segment Hints)")
    cfg = load_all_config()
    constructor = SignalConstructor(cfg.scoring)
    matcher = TaxonomyMatcher(cfg.taxonomy)
    matcher._embedding_available = False
    
    rec = RawRecord(
        record_id="rec-100",
        source_type="reddit",
        source_name="r/IndianFashionAddicts",
        content_id="post-100",
        url="https://reddit.com/test",
        text="As a college student, I hate the sizing on Myntra! It is a complete disaster.",
        author_meta=AuthorMeta(user_type="identified", segment_hints=["female"]),
        date_collected=now_iso(),
        date_published="2025-08-01T10:00:00Z",
        platform_meta=PlatformMeta(upvotes=15),
    )
    
    matches = matcher.match_sentence(rec.text)
    assert len(matches) > 0
    signal = constructor.build(rec, matches[0])
    
    assert signal.severity_hint == "high", f"Expected 'high' severity for 'hate/disaster', got '{signal.severity_hint}'"
    assert "student" in signal.segment_hints or "female" in signal.segment_hints, "Segment hints not properly inferred"
    assert signal.record_id == "rec-100"
    assert signal.source_ref.source_type == "reddit"
    assert len(signal.question_refs) > 0
    
    print(f"  [PASS] Signal constructed:")
    print(f"         - Node: {signal.taxonomy_node} ({signal.dimension})")
    print(f"         - Severity Hint: {signal.severity_hint}")
    print(f"         - Segment Hints: {signal.segment_hints}")
    print(f"         - Question References: {signal.question_refs}")
    return True


def test_case_8() -> bool:
    """Case 8: Cross-Source Evidence Filtering."""
    print_case_header(8, "Cross-Source Evidence Filtering (>= 2 Platform Diversity)")
    validator = CrossSourceValidator(min_sources=2)
    
    # Candidate 1: Signals from 2 different platforms (Reddit + Play Store) -> MUST PASS
    c1 = CandidateCluster(
        cluster_id="cluster_valid",
        dimension="Fit & Sizing",
        taxonomy_nodes=["fit_sizing.size_uncertainty"],
        signals=[
            _make_signal(source_type="reddit"),
            _make_signal(source_type="play_store"),
        ],
    )
    
    # Candidate 2: Signals from ONLY 1 platform (Reddit only) -> MUST BE REJECTED
    c2 = CandidateCluster(
        cluster_id="cluster_single_source",
        dimension="Price & Value",
        taxonomy_nodes=["price_value.price_hesitation"],
        signals=[
            _make_signal(source_type="reddit"),
            _make_signal(source_type="reddit"),
        ],
    )
    
    result = validator.validate([c1, c2])
    assert len(result.passed_clusters) == 1, "Only 1 cluster should pass"
    assert result.passed_clusters[0].cluster_id == "cluster_valid"
    assert len(result.rejected_clusters) == 1, "1 cluster should be rejected"
    assert result.rejected_clusters[0].cluster_id == "cluster_single_source"
    
    print(f"  [PASS] Multi-platform cluster passed; single-platform cluster filtered out.")
    return True


def test_case_9() -> bool:
    """Case 9: Priority Scoring Formula & Ranker Determinism."""
    print_case_header(9, "Priority Scoring Formula & Ranker Determinism")
    cfg = load_all_config()
    scorer = OpportunityScorer(cfg.scoring)
    
    cluster_high = CandidateCluster(
        cluster_id="c_high",
        dimension="Fit & Sizing",
        taxonomy_nodes=["fit_sizing.size_uncertainty"],
        signals=[
            _make_signal(source_type="reddit", severity_hint="high", confidence=0.90),
            _make_signal(source_type="app_store", severity_hint="high", confidence=0.95),
            _make_signal(source_type="play_store", severity_hint="high", confidence=0.90),
        ],
    )
    
    cluster_low = CandidateCluster(
        cluster_id="c_low",
        dimension="Fit & Sizing",
        taxonomy_nodes=["fit_sizing.size_uncertainty"],
        signals=[
            _make_signal(source_type="reddit", severity_hint="low", confidence=0.70),
            _make_signal(source_type="youtube", severity_hint="low", confidence=0.70),
        ],
    )
    
    scores_high = scorer.compute_scores(cluster_high, max_signal_count=3)
    scores_low = scorer.compute_scores(cluster_low, max_signal_count=3)
    
    assert scores_high.composite > scores_low.composite, "High pain/volume cluster must score higher"
    assert 0.0 <= scores_high.composite <= 1.0
    assert 0.0 <= scores_low.composite <= 1.0
    
    # Test Ranker
    op_high = OpportunityArea(
        opportunity_id="c_high", title="High Op", dimension="Fit", taxonomy_nodes=[], question_answers=[],
        signal_count=3, source_spread={}, scores=scores_high, segment_concentration="",
        opportunity_statement="", representative_quotes=[]
    )
    op_low = OpportunityArea(
        opportunity_id="c_low", title="Low Op", dimension="Fit", taxonomy_nodes=[], question_answers=[],
        signal_count=2, source_spread={}, scores=scores_low, segment_concentration="",
        opportunity_statement="", representative_quotes=[]
    )
    
    ranked = OpportunityRanker.rank([op_low, op_high])
    assert ranked[0].opportunity_id == "c_high" and ranked[0].rank == 1
    assert ranked[1].opportunity_id == "c_low" and ranked[1].rank == 2
    
    print(f"  [PASS] Score calculations verified:")
    print(f"         - High Priority: composite={scores_high.composite:.4f} (Freq: {scores_high.frequency:.2f}, Sev: {scores_high.severity:.2f}, Ev: {scores_high.evidence_strength:.2f}) -> Rank #1")
    print(f"         - Low Priority : composite={scores_low.composite:.4f} (Freq: {scores_low.frequency:.2f}, Sev: {scores_low.severity:.2f}, Ev: {scores_low.evidence_strength:.2f}) -> Rank #2")
    return True


def test_case_10() -> bool:
    """Case 10: End-to-End Pipeline Execution & Multi-Format Export."""
    print_case_header(10, "End-to-End Pipeline Execution & Multi-Format Export (.md, .json, .csv)")
    with tempfile.TemporaryDirectory() as tmpdir:
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run
        
        tmp_path = Path(tmpdir)
        orig_raw = ds_mod.RAW_RECORDS_DIR
        orig_sig = ds_mod.SIGNALS_DIR
        orig_opp = ds_mod.OPPORTUNITIES_DIR
        orig_proc = ext_run._PROCESSED_IDS_FILE
        
        ds_mod.RAW_RECORDS_DIR = tmp_path / "raw"
        ds_mod.SIGNALS_DIR = tmp_path / "signals"
        ds_mod.OPPORTUNITIES_DIR = tmp_path / "opps"
        ext_run._PROCESSED_IDS_FILE = tmp_path / "proc_ids.json"
        
        try:
            # Seed raw records covering multi-platform conversations
            raw_store = DataStore(run_id="live_seed")
            seeded_records = [
                {"record_id": "r1", "source_type": "reddit", "source_name": "Reddit IFA", "content_id": "c1", "url": "https://reddit.com/1", "text": "I am not sure about size on Myntra, the size chart is inaccurate.", "author_meta": {"user_type": "identified", "segment_hints": ["female"]}, "date_collected": now_iso(), "date_published": "2025-08-01T10:00:00Z", "platform_meta": {"upvotes": 12, "reply_count": 4, "rating": None}},
                {"record_id": "r2", "source_type": "play_store", "source_name": "Google Play", "content_id": "c2", "url": "https://play.google.com/1", "text": "Not sure about size at all, should I size up or down?", "author_meta": {"user_type": "identified", "segment_hints": ["urban"]}, "date_collected": now_iso(), "date_published": "2025-08-01T10:00:00Z", "platform_meta": {"upvotes": 5, "reply_count": 1, "rating": 2.0}},
                {"record_id": "r3", "source_type": "youtube", "source_name": "YouTube Reviews", "content_id": "c3", "url": "https://youtube.com/1", "text": "This dress is too expensive, I am waiting for sale and discount.", "author_meta": {"user_type": "identified", "segment_hints": ["student"]}, "date_collected": now_iso(), "date_published": "2025-08-01T10:00:00Z", "platform_meta": {"upvotes": 20, "reply_count": 2, "rating": None}},
                {"record_id": "r4", "source_type": "forum", "source_name": "Quora Topics", "content_id": "c4", "url": "https://quora.com/1", "text": "I never buy full price on Myntra, always waiting for sale.", "author_meta": {"user_type": "identified", "segment_hints": ["budget_buyer"]}, "date_collected": now_iso(), "date_published": "2025-08-01T10:00:00Z", "platform_meta": {"upvotes": 4, "reply_count": 0, "rating": None}},
            ]
            for r in seeded_records:
                raw_store.write_raw_record(r)
            
            reports_dir = tmp_path / "reports"
            summary = run_full_pipeline(
                dry_run=False,
                skip_scrape=True,
                layer="a",
                min_sources=2,
                output_dir=reports_dir,
            )
            
            # Verify outputs
            md_path = reports_dir / "final_analysis_report.md"
            json_path = reports_dir / "final_analysis_report.json"
            csv_path = reports_dir / "opportunities_matrix.csv"
            
            assert md_path.exists() and md_path.stat().st_size > 500, "Markdown report missing or empty"
            assert json_path.exists() and json_path.stat().st_size > 500, "JSON report missing or empty"
            assert csv_path.exists() and csv_path.stat().st_size > 100, "CSV report missing or empty"
            
            # Check JSON contents
            with json_path.open("r", encoding="utf-8") as fh:
                report_data = json.load(fh)
            assert len(report_data["question_answers"]) == 10, "Report must answer all 10 questions"
            assert len(report_data["opportunity_cards"]) >= 2, "Opportunities should be surfaced"
            
            print(f"  [PASS] Pipeline completed in {summary['total_elapsed_seconds']:.2f}s:")
            print(f"         - Signals extracted: {summary['phase3_extract']['signals_extracted']}")
            print(f"         - Opportunities surfaced: {summary['phase4_analyze']['opportunities_surfaced']}")
            print(f"         - Deliverables generated:")
            print(f"           * Markdown: {md_path} ({md_path.stat().st_size} bytes)")
            print(f"           * JSON    : {json_path} ({json_path.stat().st_size} bytes)")
            print(f"           * CSV     : {csv_path} ({csv_path.stat().st_size} bytes)")
            return True
        finally:
            ds_mod.RAW_RECORDS_DIR = orig_raw
            ds_mod.SIGNALS_DIR = orig_sig
            ds_mod.OPPORTUNITIES_DIR = orig_opp
            ext_run._PROCESSED_IDS_FILE = orig_proc


def run_all_10_cases() -> bool:
    print(f"\n{'#'*75}")
    print(f"  PUBLIC CONVERSATION ANALYSIS ENGINE -- 10 LIVE ENVIRONMENT TEST CASES")
    print(f"{'#'*75}")
    
    test_cases = [
        test_case_1,
        test_case_2,
        test_case_3,
        test_case_4,
        test_case_5,
        test_case_6,
        test_case_7,
        test_case_8,
        test_case_9,
        test_case_10,
    ]
    
    results = []
    start_time = time.time()
    
    for tc in test_cases:
        try:
            ok = tc()
            results.append((tc.__doc__.split(":")[0].strip() if tc.__doc__ else tc.__name__, ok, None))
        except Exception as exc:
            results.append((tc.__doc__.split(":")[0].strip() if tc.__doc__ else tc.__name__, False, exc))
            log.error("Test Case failed with error: %s", exc, exc_info=True)
            
    total_time = time.time() - start_time
    
    print(f"\n{'='*75}")
    print(f"  10-CASE LIVE TEST RESULTS SUMMARY (Total Time: {total_time:.2f}s)")
    print(f"{'='*75}")
    
    passed_count = sum(1 for _, ok, _ in results if ok)
    for name, ok, err in results:
        status_str = "[PASS]" if ok else "[FAIL]"
        err_str = f" -- Error: {err}" if err else ""
        print(f"  {status_str} {name}{err_str}")
        
    print(f"{'='*75}")
    print(f"  OVERALL RESULT: {passed_count}/10 CASES PASSED")
    print(f"{'='*75}\n")
    
    return passed_count == 10


if __name__ == "__main__":
    success = run_all_10_cases()
    sys.exit(0 if success else 1)
