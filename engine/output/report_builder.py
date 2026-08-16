"""
engine/output/report_builder.py
Public Conversation Analysis Engine — Report Builder (Phase 5)

Assembles the comprehensive Final Analysis Report with 4 core sections:
1. Executive Summary: High-level overview, ranked opportunity table, metrics summary.
2. Behavioral Question Answers: Direct evidence-backed answers for all 10 behavioral questions.
3. Opportunity Detail Cards: In-depth breakdown for every opportunity (scores, statement, source spread, verbatim quotes).
4. Raw Signal Appendix: Detailed audit log of underlying conversation signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from engine.analyzer.models import OpportunityArea
from engine.config_loader import AllConfig, QuestionSetConfig
from engine.extractor.models import Signal
from engine.logger import get_logger

log = get_logger(__name__)


@dataclass
class QuestionAnswerSection:
    """Answers a single behavioral question with linked opportunity evidence."""
    question_id: int
    question_text: str
    related_dimensions: list[str]
    notes: str
    top_opportunities: list[OpportunityArea]
    evidence_summary: str
    total_signals: int


@dataclass
class FinalReport:
    """Complete assembled report containing all 4 sections."""
    generated_at: str
    metadata: dict[str, Any]
    executive_summary_table: list[dict[str, Any]]
    question_answers: list[QuestionAnswerSection]
    opportunity_cards: list[OpportunityArea]
    signal_appendix: list[Signal]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "executive_summary_table": self.executive_summary_table,
            "question_answers": [
                {
                    "question_id": qa.question_id,
                    "question_text": qa.question_text,
                    "related_dimensions": qa.related_dimensions,
                    "notes": qa.notes,
                    "evidence_summary": qa.evidence_summary,
                    "total_signals": qa.total_signals,
                    "opportunity_ids": [op.opportunity_id for op in qa.top_opportunities],
                    "opportunity_titles": [op.title for op in qa.top_opportunities],
                }
                for qa in self.question_answers
            ],
            "opportunity_cards": [op.to_dict() for op in self.opportunity_cards],
            "signal_appendix_count": len(self.signal_appendix),
        }


class ReportBuilder:
    """
    Builds the FinalReport object by cross-referencing Opportunities, Questions, and Signals.
    """

    def __init__(self, config: AllConfig) -> None:
        self.config = config

    def build_report(
        self,
        opportunities: list[OpportunityArea],
        signals: list[Signal],
    ) -> FinalReport:
        """
        Assemble the complete 4-section analysis report.

        Args:
            opportunities: Ranked list of OpportunityArea records from Phase 4.
            signals: List of extracted Signal records from Phase 3.

        Returns:
            FinalReport instance ready for export.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1. Compute Metadata
        source_types_represented = sorted({
            s.source_ref.source_type for s in signals if s.source_ref and s.source_ref.source_type
        })
        dimensions_represented = sorted({op.dimension for op in opportunities})

        metadata = {
            "total_signals": len(signals),
            "total_opportunities": len(opportunities),
            "source_types_count": len(source_types_represented),
            "source_types": source_types_represented,
            "dimensions_count": len(dimensions_represented),
            "dimensions": dimensions_represented,
            "questions_total": len(self.config.question_set.questions),
        }

        # 2. Section 1: Executive Summary Table
        exec_table = [
            {
                "rank": op.rank,
                "title": op.title,
                "dimension": op.dimension,
                "composite_score": round(op.scores.composite, 4),
                "frequency_score": round(op.scores.frequency, 4),
                "severity_score": round(op.scores.severity, 4),
                "evidence_strength": round(op.scores.evidence_strength, 4),
                "signal_count": op.signal_count,
                "source_count": len(op.source_spread),
                "sources": list(op.source_spread.keys()),
            }
            for op in opportunities
        ]

        # 3. Section 2: Behavioral Question Answers (Q1 to Q10)
        question_answers = self._build_question_answers(opportunities, signals)

        # 4. Section 3: Opportunity Cards (Sorted by Rank)
        opportunity_cards = sorted(
            opportunities,
            key=lambda op: (op.rank if op.rank is not None else 999999, -op.scores.composite),
        )

        log.info(
            "ReportBuilder: assembled FinalReport (%d opportunities, %d questions, %d signals).",
            len(opportunities),
            len(question_answers),
            len(signals),
        )

        return FinalReport(
            generated_at=now,
            metadata=metadata,
            executive_summary_table=exec_table,
            question_answers=question_answers,
            opportunity_cards=opportunity_cards,
            signal_appendix=signals,
        )

    def _build_question_answers(
        self,
        opportunities: list[OpportunityArea],
        signals: list[Signal],
    ) -> list[QuestionAnswerSection]:
        """Maps opportunities and signals to each of the 10 behavioral questions."""
        sections: list[QuestionAnswerSection] = []

        for q in self.config.question_set.questions:
            # Find opportunities that explicitly list this question_id
            matching_ops = [
                op for op in opportunities if q.question_id in op.question_answers
            ]
            # Sort matching opportunities by rank
            matching_ops = sorted(
                matching_ops,
                key=lambda op: (op.rank if op.rank is not None else 999999, -op.scores.composite),
            )
            top_2_3 = matching_ops[:3]

            # Count total signals answering this question
            matching_signals = [
                s for s in signals if q.question_id in s.question_refs
            ]

            # Generate evidence summary
            evidence_summary = self._generate_question_evidence_summary(
                q.question_id, q.question_text, top_2_3, len(matching_signals)
            )

            sections.append(
                QuestionAnswerSection(
                    question_id=q.question_id,
                    question_text=q.question_text,
                    related_dimensions=list(q.related_dimensions),
                    notes=q.notes,
                    top_opportunities=top_2_3,
                    evidence_summary=evidence_summary,
                    total_signals=len(matching_signals),
                )
            )

        return sections

    @staticmethod
    def _generate_question_evidence_summary(
        qid: int,
        qtext: str,
        top_ops: list[OpportunityArea],
        signal_count: int,
    ) -> str:
        """Synthesize a direct, evidence-backed answer paragraph for a question."""
        if not top_ops:
            return (
                f"No opportunities directly mapped to Question {qid} under current validation thresholds "
                f"({signal_count} raw signals captured)."
            )

        top_titles = [f"'{op.title}' (#{op.rank})" for op in top_ops if op.rank is not None]
        titles_str = ", ".join(top_titles) if top_titles else "identified behavioral clusters"

        primary_op = top_ops[0]
        summary = (
            f"Observed {signal_count} customer signals addressing this question. "
            f"The primary driver is {titles_str}. "
            f"Specifically, {primary_op.opportunity_statement}"
        )
        return summary
