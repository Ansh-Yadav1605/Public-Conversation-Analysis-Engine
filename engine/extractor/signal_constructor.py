"""
engine/extractor/signal_constructor.py
Public Conversation Analysis Engine — Signal Constructor

For each (RawRecord, MatchResult) pair, assembles a fully populated Signal record.

Responsibilities:
    - verbatim_quote   : the exact sentence that triggered the match
    - severity_hint    : inferred from intensity keywords in the sentence
                         (using scoring_weights.yaml severity_intensity lists)
    - segment_hints    : propagated from RawRecord.author_meta.segment_hints
                         + inferred from text using segment marker keywords
    - question_refs    : from the matched taxonomy node's question_refs field
    - confidence       : from the MatchResult (Layer A = 0.90, Layer B = cosine sim)
    - match_layer      : "keyword" | "embedding"

Usage:
    from engine.extractor.signal_constructor import SignalConstructor
    constructor = SignalConstructor(scoring_config)
    signal = constructor.build(raw_record, match_result)
"""

from __future__ import annotations

import uuid
from typing import Any

from engine.config_loader import ScoringConfig
from engine.extractor.models import Signal, SourceRef
from engine.extractor.taxonomy_matcher import MatchResult
from engine.scraper.models import RawRecord
from engine.logger import get_logger

log = get_logger(__name__)

# Segment inference keywords — used to extract segment hints from sentence text
_SEGMENT_KEYWORDS: dict[str, list[str]] = {
    "female": [
        "as a woman", "as a girl", "she", "her", "women's", "female", "ladies",
        "saree", "kurta", "ethnic wear", "kurti",
    ],
    "male": [
        "as a man", "as a guy", "he", "him", "men's", "male", "guys",
        "shirt", "trousers", "formal wear",
    ],
    "student": ["college student", "student", "pocket money", "hostel", "campus"],
    "working_professional": [
        "office wear", "working professional", "job", "salary", "first job",
        "corporate", "9 to 5",
    ],
    "budget_buyer": [
        "budget", "affordable", "can't afford", "out of budget", "cheap",
        "price sensitive", "value for money",
    ],
    "premium_buyer": [
        "premium", "luxury", "high-end", "designer", "branded", "expensive taste",
    ],
    "frequent_buyer": [
        "I shop every month", "frequent buyer", "loyal customer", "buy a lot",
        "regular customer",
    ],
    "occasional_buyer": [
        "rarely buy", "once in a while", "occasional", "not a frequent buyer",
    ],
    "urban": ["metro city", "bangalore", "mumbai", "delhi", "hyderabad", "pune", "tier 1"],
    "tier2_city": ["tier 2", "tier 3", "small town", "non-metro"],
}


class SignalConstructor:
    """
    Builds Signal records from (RawRecord, MatchResult) pairs.

    Instantiate once per pipeline run with the loaded ScoringConfig
    (needed for severity_intensity keyword lists).
    """

    def __init__(self, scoring_config: ScoringConfig) -> None:
        self._high_kws = [kw.lower() for kw in scoring_config.severity_intensity.get("high", [])]
        self._medium_kws = [kw.lower() for kw in scoring_config.severity_intensity.get("medium", [])]
        self._low_kws = [kw.lower() for kw in scoring_config.severity_intensity.get("low", [])]

    def build(self, record: RawRecord, match: MatchResult) -> Signal:
        """
        Assemble one Signal record from a RawRecord and a MatchResult.

        Args:
            record : The source RawRecord containing the matched sentence.
            match  : The MatchResult from the taxonomy matcher.

        Returns:
            A fully populated Signal ready to be written to the signal store.
        """
        sentence = match.sentence
        node = match.node

        return Signal(
            signal_id=str(uuid.uuid4()),
            record_id=record.record_id,
            source_ref=SourceRef(
                source_type=record.source_type,
                source_name=record.source_name,
                url=record.url,
                date_published=record.date_published,
            ),
            taxonomy_node=node.node_id,
            dimension=node.dimension,
            sub_category=node.sub_category,
            question_refs=list(node.question_refs),
            verbatim_quote=sentence,
            severity_hint=self._infer_severity(sentence),
            segment_hints=self._infer_segments(record, sentence),
            confidence=match.confidence,
            match_layer=match.match_layer,
        )

    def _infer_severity(self, sentence: str) -> str:
        """
        Classify the intensity of pain/frustration expressed in the sentence.
        Checks high > medium > low intensity keyword lists; defaults to "unknown".
        """
        lower = sentence.lower()

        for kw in self._high_kws:
            if kw in lower:
                return "high"

        for kw in self._medium_kws:
            if kw in lower:
                return "medium"

        for kw in self._low_kws:
            if kw in lower:
                return "low"

        return "unknown"

    @staticmethod
    def _infer_segments(record: RawRecord, sentence: str) -> list[str]:
        """
        Combine segment hints from:
        1. RawRecord.author_meta.segment_hints (set by connectors where available)
        2. Text inference from sentence content using _SEGMENT_KEYWORDS
        Returns a deduplicated, sorted list.
        """
        hints: set[str] = set(record.author_meta.segment_hints)
        sentence_lower = sentence.lower()

        for segment, keywords in _SEGMENT_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in sentence_lower:
                    hints.add(segment)
                    break  # one keyword match per segment is enough

        return sorted(hints)
