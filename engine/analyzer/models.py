"""
engine/analyzer/models.py
Public Conversation Analysis Engine — OpportunityArea Data Model

Defines the canonical OpportunityArea schema as specified in architecture.md §4.3.5.
An OpportunityArea groups related Signals across independent sources into a prioritized,
comparable product opportunity mapped to the 10 behavioral questions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RepresentativeQuote:
    """A verbatim quote from a real user conversation representing an opportunity."""
    verbatim: str
    source_type: str
    source_name: str
    url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verbatim": self.verbatim,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepresentativeQuote":
        return cls(
            verbatim=data["verbatim"],
            source_type=data["source_type"],
            source_name=data.get("source_name", ""),
            url=data.get("url"),
        )


@dataclass
class OpportunityScores:
    """The 4 scoring dimensions defined in architecture.md §4.3.3 & §4.3.4."""
    frequency: float          # 0.0–1.0 (signal volume relative to max)
    severity: float           # 0.0–1.0 (weighted pain intensity)
    evidence_strength: float  # 0.0–1.0 (source diversity * confidence)
    composite: float          # 0.0–1.0 (weighted sum using scoring_weights.yaml)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frequency": round(self.frequency, 4),
            "severity": round(self.severity, 4),
            "evidence_strength": round(self.evidence_strength, 4),
            "composite": round(self.composite, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpportunityScores":
        return cls(
            frequency=float(data.get("frequency", 0.0)),
            severity=float(data.get("severity", 0.0)),
            evidence_strength=float(data.get("evidence_strength", 0.0)),
            composite=float(data.get("composite", 0.0)),
        )


@dataclass
class OpportunityArea:
    """
    Unified Opportunity Area record produced by the analyzer stage.

    Represents an actionable, verified user pain point or behavioral pattern
    observed across independent platforms.
    """
    opportunity_id: str
    title: str
    dimension: str
    taxonomy_nodes: list[str]
    question_answers: list[int]
    signal_count: int
    source_spread: dict[str, int]
    scores: OpportunityScores
    segment_concentration: str
    opportunity_statement: str
    representative_quotes: list[RepresentativeQuote]
    rank: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.opportunity_id:
            self.opportunity_id = str(uuid.uuid4())
        if not self.title or not self.title.strip():
            raise ValueError("OpportunityArea.title must be non-empty.")
        if not self.dimension or not self.dimension.strip():
            raise ValueError("OpportunityArea.dimension must be non-empty.")
        if self.signal_count < 0:
            raise ValueError("OpportunityArea.signal_count cannot be negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "title": self.title,
            "dimension": self.dimension,
            "taxonomy_nodes": self.taxonomy_nodes,
            "question_answers": self.question_answers,
            "signal_count": self.signal_count,
            "source_spread": self.source_spread,
            "scores": self.scores.to_dict(),
            "segment_concentration": self.segment_concentration,
            "opportunity_statement": self.opportunity_statement,
            "representative_quotes": [q.to_dict() for q in self.representative_quotes],
            "rank": self.rank,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpportunityArea":
        quotes = [RepresentativeQuote.from_dict(q) for q in data.get("representative_quotes", [])]
        scores = OpportunityScores.from_dict(data.get("scores", {}))
        return cls(
            opportunity_id=data["opportunity_id"],
            title=data["title"],
            dimension=data["dimension"],
            taxonomy_nodes=data.get("taxonomy_nodes", []),
            question_answers=data.get("question_answers", []),
            signal_count=int(data.get("signal_count", 0)),
            source_spread=data.get("source_spread", {}),
            scores=scores,
            segment_concentration=data.get("segment_concentration", ""),
            opportunity_statement=data.get("opportunity_statement", ""),
            representative_quotes=quotes,
            rank=data.get("rank"),
        )
