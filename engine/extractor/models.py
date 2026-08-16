"""
engine/extractor/models.py
Public Conversation Analysis Engine — Signal Data Model

Defines the canonical Signal schema as specified in architecture.md §4.2.4.
One Signal = one atomic behavioral observation extracted from a RawRecord.
A single RawRecord can produce multiple Signals (one per matched taxonomy node).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

VALID_SEVERITY_HINTS = frozenset({"high", "medium", "low", "unknown"})
VALID_MATCH_LAYERS = frozenset({"keyword", "embedding", "llm"})


@dataclass
class SourceRef:
    """Preserved source pointer — allows full traceability from Signal back to origin."""
    source_type: str
    source_name: str
    url: Optional[str]
    date_published: Optional[str]


@dataclass
class Signal:
    """
    Atomic behavioral observation extracted from one RawRecord sentence.

    Fields match architecture.md §4.2.4 exactly.
    """

    signal_id: str                  # UUID v4
    record_id: str                  # FK → RawRecord.record_id
    source_ref: SourceRef           # preserved source metadata from the RawRecord
    taxonomy_node: str              # dot-notation node_id (e.g. "fit_sizing.size_uncertainty")
    dimension: str                  # parent dimension label (e.g. "Fit & Sizing")
    sub_category: str               # sub-category label
    question_refs: list[int]        # questions this signal helps answer
    verbatim_quote: str             # the exact sentence(s) that triggered the match
    severity_hint: str              # "high" | "medium" | "low" | "unknown"
    segment_hints: list[str]        # demographic / behavioral cues
    confidence: float               # 0.0–1.0 (keyword=0.90, embedding=cosine_sim, llm=explicit)
    match_layer: str                # "keyword" | "embedding" | "llm"

    def __post_init__(self) -> None:
        if not self.signal_id:
            self.signal_id = str(uuid.uuid4())
        if self.severity_hint not in VALID_SEVERITY_HINTS:
            raise ValueError(
                f"Invalid severity_hint '{self.severity_hint}'. "
                f"Must be one of: {sorted(VALID_SEVERITY_HINTS)}"
            )
        if self.match_layer not in VALID_MATCH_LAYERS:
            raise ValueError(
                f"Invalid match_layer '{self.match_layer}'. "
                f"Must be one of: {sorted(VALID_MATCH_LAYERS)}"
            )
        self.confidence = round(max(0.0, min(1.0, float(self.confidence))), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "record_id": self.record_id,
            "source_ref": {
                "source_type": self.source_ref.source_type,
                "source_name": self.source_ref.source_name,
                "url": self.source_ref.url,
                "date_published": self.source_ref.date_published,
            },
            "taxonomy_node": self.taxonomy_node,
            "dimension": self.dimension,
            "sub_category": self.sub_category,
            "question_refs": self.question_refs,
            "verbatim_quote": self.verbatim_quote,
            "severity_hint": self.severity_hint,
            "segment_hints": self.segment_hints,
            "confidence": self.confidence,
            "match_layer": self.match_layer,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Signal":
        sr = data.get("source_ref", {})
        return cls(
            signal_id=data["signal_id"],
            record_id=data["record_id"],
            source_ref=SourceRef(
                source_type=sr.get("source_type", ""),
                source_name=sr.get("source_name", ""),
                url=sr.get("url"),
                date_published=sr.get("date_published"),
            ),
            taxonomy_node=data["taxonomy_node"],
            dimension=data["dimension"],
            sub_category=data["sub_category"],
            question_refs=data.get("question_refs", []),
            verbatim_quote=data["verbatim_quote"],
            severity_hint=data.get("severity_hint", "unknown"),
            segment_hints=data.get("segment_hints", []),
            confidence=float(data.get("confidence", 0.5)),
            match_layer=data.get("match_layer", "keyword"),
        )
