"""
tests/test_phase5.py
Phase 5 — Output, Delivery & Validation
Unit and integration tests for ReportBuilder, Export module (Markdown, JSON, CSV),
and Full Pipeline execution.

No live network calls. Uses synthetic data and real config files.
Run: pytest engine/tests/test_phase5.py -v
"""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.analyzer.models import (
    OpportunityArea,
    OpportunityScores,
    RepresentativeQuote,
)
from engine.config_loader import load_all_config
from engine.extractor.models import Signal, SourceRef
from engine.output.export import export_all, to_csv, to_json, to_markdown
from engine.output.report_builder import FinalReport, ReportBuilder
from run_pipeline import run_full_pipeline


# =============================================================================
# Helper Fixtures
# =============================================================================

def _make_test_opportunity(
    opp_id: str = "opp-1",
    title: str = "Size uncertainty creates pre-purchase friction",
    dimension: str = "Fit & Sizing",
    questions: list[int] | None = None,
    rank: int = 1,
    composite: float = 0.85,
) -> OpportunityArea:
    return OpportunityArea(
        opportunity_id=opp_id,
        title=title,
        dimension=dimension,
        taxonomy_nodes=["fit_sizing.size_uncertainty"],
        question_answers=questions or [1, 2, 3, 7],
        signal_count=25,
        source_spread={"reddit": 12, "app_store": 8, "play_store": 5},
        scores=OpportunityScores(
            frequency=0.80,
            severity=0.88,
            evidence_strength=0.75,
            composite=composite,
        ),
        segment_concentration="Female, Urban, Repeat buyers",
        opportunity_statement="Users frequently abandon purchase due to inconsistent sizing.",
        representative_quotes=[
            RepresentativeQuote(
                verbatim="The size chart on Myntra is completely wrong.",
                source_type="reddit",
                source_name="r/IndianFashionAddicts",
                url="https://reddit.com/r/test/1",
            ),
            RepresentativeQuote(
                verbatim="Always have to size up on this app.",
                source_type="app_store",
                source_name="Apple App Store",
                url="https://apple.com/app/1",
            ),
            RepresentativeQuote(
                verbatim="Sizes vary wildly across brands.",
                source_type="play_store",
                source_name="Google Play Store",
                url="https://play.google.com/1",
            ),
        ],
        rank=rank,
    )


def _make_test_signal(
    qid_refs: list[int] | None = None,
    dimension: str = "Fit & Sizing",
) -> Signal:
    return Signal(
        signal_id=str(uuid.uuid4()),
        record_id=str(uuid.uuid4()),
        source_ref=SourceRef(
            source_type="reddit",
            source_name="r/IndianFashionAddicts",
            url="https://reddit.com/r/test",
            date_published="2025-08-01T10:00:00Z",
        ),
        taxonomy_node="fit_sizing.size_uncertainty",
        dimension=dimension,
        sub_category="Size Uncertainty",
        question_refs=qid_refs or [1, 2, 3, 7],
        verbatim_quote="I never know which size to order when shopping online.",
        severity_hint="high",
        segment_hints=["female"],
        confidence=0.90,
        match_layer="keyword",
    )


# =============================================================================
# 1. Tests — ReportBuilder
# =============================================================================

class TestReportBuilder:
    def setup_method(self):
        self.config = load_all_config()
        self.builder = ReportBuilder(self.config)

    def test_build_report_structure(self):
        op1 = _make_test_opportunity(opp_id="op1", rank=1, composite=0.90)
        op2 = _make_test_opportunity(
            opp_id="op2",
            title="Price skepticism limits conversion",
            dimension="Price & Value",
            questions=[1, 4, 5, 8, 9, 10],
            rank=2,
            composite=0.75,
        )
        signals = [_make_test_signal() for _ in range(5)]

        report = self.builder.build_report([op1, op2], signals)
        assert isinstance(report, FinalReport)
        assert report.generated_at is not None
        assert report.metadata["total_opportunities"] == 2
        assert report.metadata["total_signals"] == 5
        assert len(report.executive_summary_table) == 2
        assert len(report.opportunity_cards) == 2

    def test_all_10_questions_covered_in_report(self):
        op = _make_test_opportunity(questions=list(range(1, 11)))
        signals = [_make_test_signal(qid_refs=list(range(1, 11)))]

        report = self.builder.build_report([op], signals)
        assert len(report.question_answers) == 10

        question_ids = [qa.question_id for qa in report.question_answers]
        assert question_ids == list(range(1, 11))
        for qa in report.question_answers:
            assert len(qa.question_text) > 0
            assert len(qa.evidence_summary) > 0
            assert len(qa.top_opportunities) > 0

    def test_report_dict_serialization(self):
        op = _make_test_opportunity()
        signals = [_make_test_signal()]
        report = self.builder.build_report([op], signals)

        d = report.to_dict()
        assert "generated_at" in d
        assert "executive_summary_table" in d
        assert "question_answers" in d
        assert "opportunity_cards" in d


# =============================================================================
# 2. Tests — Export Module
# =============================================================================

class TestExportModule:
    def setup_method(self):
        self.config = load_all_config()
        self.builder = ReportBuilder(self.config)
        self.op1 = _make_test_opportunity(opp_id="op1", rank=1, composite=0.90)
        self.op2 = _make_test_opportunity(
            opp_id="op2",
            title="Price skepticism limits conversion",
            dimension="Price & Value",
            questions=[4, 5, 8, 9, 10],
            rank=2,
            composite=0.75,
        )
        self.signals = [_make_test_signal() for _ in range(3)]
        self.report = self.builder.build_report([self.op1, self.op2], self.signals)

    def test_to_markdown_contains_all_sections(self):
        md = to_markdown(self.report)
        assert "# Public Conversation Analysis Report" in md
        assert "## Section 1: Executive Summary" in md
        assert "## Section 2: Behavioral Question Answers" in md
        assert "## Section 3: Opportunity Detail Cards" in md
        assert "## Section 4: Signal Audit Appendix" in md
        assert "### Q1:" in md
        assert "### Q10:" in md
        assert "### Rank #1:" in md
        assert "### Rank #2:" in md
        assert "The size chart on Myntra is completely wrong." in md

    def test_to_json_valid_and_parseable(self):
        json_str = to_json(self.report)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert parsed["metadata"]["total_opportunities"] == 2
        assert len(parsed["executive_summary_table"]) == 2
        assert len(parsed["question_answers"]) == 10

    def test_to_csv_valid_and_parseable(self):
        csv_str = to_csv(self.report.opportunity_cards)
        reader = list(csv.DictReader(csv_str.splitlines()))
        assert len(reader) == 2
        assert reader[0]["rank"] == "1"
        assert reader[0]["opportunity_id"] == "op1"
        assert float(reader[0]["composite_score"]) == 0.90
        assert reader[1]["rank"] == "2"

    def test_export_all_saves_files(self, tmp_path):
        out_dir = tmp_path / "reports"
        paths = export_all(self.report, out_dir)

        assert "markdown" in paths
        assert "json" in paths
        assert "csv" in paths

        assert paths["markdown"].exists()
        assert paths["json"].exists()
        assert paths["csv"].exists()

        assert len(paths["markdown"].read_text(encoding="utf-8")) > 100
        assert len(paths["json"].read_text(encoding="utf-8")) > 100
        assert len(paths["csv"].read_text(encoding="utf-8")) > 50


# =============================================================================
# 3. Tests — Full Pipeline Runner & Success Criteria
# =============================================================================

class TestFullPipelineRunner:
    def test_pipeline_dry_run(self, tmp_path, monkeypatch):
        import engine.data_store as ds_mod
        import engine.extractor.run as ext_run
        from engine.data_store import DataStore
        from engine.scraper.models import RawRecord, AuthorMeta, PlatformMeta, now_iso

        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")
        monkeypatch.setattr(ext_run, "_PROCESSED_IDS_FILE", tmp_path / "proc_ids.json")

        # 1. Seed store with raw records that match multiple dimensions across sources
        raw_store = DataStore(run_id="seed")
        raw_records = [
            {
                "record_id": "r1",
                "source_type": "reddit",
                "source_name": "r/IndianFashionAddicts",
                "content_id": "c1",
                "url": "https://reddit.com/1",
                "text": "The size chart is inaccurate and confusing. I am not sure about size.",
                "author_meta": {"user_type": "identified", "segment_hints": ["female"]},
                "date_collected": now_iso(),
                "date_published": "2025-08-01T10:00:00Z",
                "platform_meta": {"upvotes": 5, "reply_count": 2, "rating": None},
            },
            {
                "record_id": "r2",
                "source_type": "play_store",
                "source_name": "Play Store",
                "content_id": "c2",
                "url": "https://play.google.com/1",
                "text": "Size chart not helpful at all. Should I size up or down?",
                "author_meta": {"user_type": "identified", "segment_hints": ["urban"]},
                "date_collected": now_iso(),
                "date_published": "2025-08-01T10:00:00Z",
                "platform_meta": {"upvotes": 1, "reply_count": 0, "rating": 2.0},
            },
            {
                "record_id": "r3",
                "source_type": "youtube",
                "source_name": "YouTube Hauls",
                "content_id": "c3",
                "url": "https://youtube.com/1",
                "text": "This dress is too expensive and I am waiting for sale. Not worth the price.",
                "author_meta": {"user_type": "identified", "segment_hints": ["budget_buyer"]},
                "date_collected": now_iso(),
                "date_published": "2025-08-01T10:00:00Z",
                "platform_meta": {"upvotes": 10, "reply_count": 1, "rating": None},
            },
            {
                "record_id": "r4",
                "source_type": "forum",
                "source_name": "Quora Fashion",
                "content_id": "c4",
                "url": "https://quora.com/1",
                "text": "I am waiting for sale and discount because price is too high.",
                "author_meta": {"user_type": "identified", "segment_hints": ["student"]},
                "date_collected": now_iso(),
                "date_published": "2025-08-01T10:00:00Z",
                "platform_meta": {"upvotes": 3, "reply_count": 0, "rating": None},
            },
        ]
        for r in raw_records:
            raw_store.write_raw_record(r)

        # 2. Run full pipeline with skip_scrape=True to use seeded records
        out_reports_dir = tmp_path / "final_reports"
        summary = run_full_pipeline(
            dry_run=False,
            skip_scrape=True,
            layer="a",
            min_sources=2,
            output_dir=out_reports_dir,
        )

        assert summary["total_elapsed_seconds"] >= 0.0
        assert summary["phase3_extract"]["signals_extracted"] >= 2
        assert summary["phase4_analyze"]["opportunities_surfaced"] >= 1
        assert summary["phase5_export"]["opportunities_exported"] >= 1

        # Check files created
        assert (out_reports_dir / "final_analysis_report.md").exists()
        assert (out_reports_dir / "final_analysis_report.json").exists()
        assert (out_reports_dir / "opportunities_matrix.csv").exists()
