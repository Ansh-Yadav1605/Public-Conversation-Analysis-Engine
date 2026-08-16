"""
engine/analyzer/synthesizer.py
Public Conversation Analysis Engine — Opportunity Synthesizer

Synthesizes validated CandidateClusters into complete OpportunityArea records:
1. Writes structured, actionable opportunity statements.
2. Formulates concise, professional product titles.
3. Selects 3–5 diverse, high-confidence representative verbatim quotes.
4. Aggregates question answers (`question_refs` union).
5. Computes segment concentration from observed demographic & behavioral hints.
6. Computes platform source spread.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from engine.analyzer.grouper import CandidateCluster
from engine.analyzer.models import OpportunityArea, OpportunityScores, RepresentativeQuote
from engine.config_loader import TaxonomyConfig
from engine.extractor.models import Signal
from engine.logger import get_logger

log = get_logger(__name__)

# Dimension-specific behavioral templates for opportunity statements
_DIMENSION_ACTION_TEMPLATES = {
    "Fit & Sizing": {
        "action": "stalls or abandons purchase",
        "barrier": "uncertainty around clothing fit and cross-brand sizing inconsistency",
    },
    "Styling & Occasion": {
        "action": "hesitates to complete cart checkout",
        "barrier": "difficulty visualizing outfit coordination and occasion appropriateness",
    },
    "Price & Value": {
        "action": "postpones purchase or bookmarks passively",
        "barrier": "price-to-value skepticism and anticipation of impending discounts or sales",
    },
    "Trust & Reviews": {
        "action": "drops out during product evaluation",
        "barrier": "lack of credible, authentic reviews or unfamiliarity with marketplace seller quality",
    },
    "Return & Risk": {
        "action": "hesitates to finalize orders",
        "barrier": "friction in the return/exchange process and anxiety over irreversible purchases",
    },
    "Social Validation": {
        "action": "delays purchase decision",
        "barrier": "the need for peer reassurance, trend validation, or gifting confirmation",
    },
    "Product Information": {
        "action": "abandons product page",
        "barrier": "missing or ambiguous material/fabric specifications and misleading imagery",
    },
    "Comparison Behavior": {
        "action": "leaves platform to compare competitors",
        "barrier": "inability to easily compare shortlisted items or prices across platforms",
    },
    "Intent Signal": {
        "action": "uses wishlists for passive bookmarking without buying",
        "barrier": "lack of immediate purchasing urgency or specific trigger to convert intent into action",
    },
    "Segment Markers": {
        "action": "experiences friction in product discovery",
        "barrier": "catalog curation failing to cater to specific demographic and lifestyle requirements",
    },
}


class OpportunitySynthesizer:
    """
    Synthesizes raw signal clusters into structured, human-readable OpportunityArea objects.
    """

    def __init__(self, taxonomy: Optional[TaxonomyConfig] = None) -> None:
        self.taxonomy = taxonomy

    def synthesize(self, cluster: CandidateCluster) -> OpportunityArea:
        """
        Transform a CandidateCluster into an unranked OpportunityArea.
        (Scores will be computed in the scoring stage).
        """
        signals = cluster.signals
        dimension = cluster.dimension
        node_id = cluster.taxonomy_nodes[0] if cluster.taxonomy_nodes else "unknown"

        # 1. Source spread
        source_spread = Counter(s.source_ref.source_type for s in signals if s.source_ref)

        # 2. Question answers (sorted union)
        question_set: set[int] = set()
        for s in signals:
            question_set.update(s.question_refs)
        question_answers = sorted(question_set)

        # 3. Segment concentration
        segment_concentration = self._compute_segment_concentration(signals)

        # 4. Title & Opportunity Statement
        title = self._generate_title(cluster)
        statement = self._generate_statement(cluster, segment_concentration, source_spread)

        # 5. Representative quotes (3–5 diverse, high-confidence quotes)
        quotes = self._select_representative_quotes(signals, max_quotes=5)

        # 6. Initial empty scores (to be populated by Scorer)
        initial_scores = OpportunityScores(
            frequency=0.0,
            severity=0.0,
            evidence_strength=0.0,
            composite=0.0,
        )

        return OpportunityArea(
            opportunity_id=cluster.cluster_id,
            title=title,
            dimension=dimension,
            taxonomy_nodes=list(cluster.taxonomy_nodes),
            question_answers=question_answers,
            signal_count=len(signals),
            source_spread=dict(source_spread),
            scores=initial_scores,
            segment_concentration=segment_concentration,
            opportunity_statement=statement,
            representative_quotes=quotes,
            rank=None,
        )

    def _generate_title(self, cluster: CandidateCluster) -> str:
        """Derive a clean, impactful title for the opportunity."""
        # Use taxonomy node label if available
        if self.taxonomy and cluster.taxonomy_nodes:
            node = self.taxonomy.get_node(cluster.taxonomy_nodes[0])
            if node:
                # E.g. "Size Uncertainty — Unknown Which Size to Order" -> "Size uncertainty creates pre-purchase friction"
                sub = node.sub_category or node.label
                return f"{sub} creates pre-purchase friction"

        # Fallback based on dimension and node
        clean_node = cluster.taxonomy_nodes[0].split(".")[-1].replace("_", " ").title() if cluster.taxonomy_nodes else "User Friction"
        return f"{clean_node} undermines conversion in {cluster.dimension}"

    def _generate_statement(
        self,
        cluster: CandidateCluster,
        segment_concentration: str,
        source_spread: Counter,
    ) -> str:
        """
        Format: "[Segment] [stalls/hesitates/abandons] because [root cause], as evidenced by [signal pattern]"
        """
        dim = cluster.dimension
        template = _DIMENSION_ACTION_TEMPLATES.get(
            dim,
            {
                "action": "experiences hesitation at checkout",
                "barrier": f"unresolved friction within {dim}",
            },
        )

        seg_text = f"Users ({segment_concentration})" if segment_concentration != "General audience" else "Users"
        action = template["action"]
        barrier = template["barrier"]

        # Signal pattern summary
        top_sources = [src for src, _ in source_spread.most_common(2)]
        sources_str = " and ".join(top_sources) if top_sources else "public discussions"
        signal_pattern = f"recurring friction across {len(cluster.signals)} customer signals on {sources_str}"

        return (
            f"{seg_text} frequently {action} because of {barrier}, "
            f"as evidenced by {signal_pattern}."
        )

    def _compute_segment_concentration(self, signals: list[Signal]) -> str:
        """Find the most prevalent demographic/behavioral cues."""
        counter: Counter = Counter()
        for s in signals:
            for hint in s.segment_hints:
                counter[hint] += 1

        if not counter:
            return "General audience"

        # Top 1-3 segment hints
        top_hints = [f"{hint.replace('_', ' ')}" for hint, _ in counter.most_common(3)]
        return ", ".join(top_hints).capitalize()

    def _select_representative_quotes(
        self, signals: list[Signal], max_quotes: int = 5
    ) -> list[RepresentativeQuote]:
        """
        Select 3–5 representative quotes from distinct sources and highest confidence/severity.
        """
        if not signals:
            return []

        # Sort signals by: high severity first, then highest confidence, then length
        severity_rank = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
        sorted_signals = sorted(
            signals,
            key=lambda s: (
                severity_rank.get(s.severity_hint, 0),
                s.confidence,
                len(s.verbatim_quote),
            ),
            reverse=True,
        )

        selected: list[RepresentativeQuote] = []
        seen_quotes: set[str] = set()
        seen_sources: set[str] = set()

        # Pass 1: Select top quote from each distinct source type
        for sig in sorted_signals:
            quote_text = sig.verbatim_quote.strip()
            src_type = sig.source_ref.source_type if sig.source_ref else "unknown"

            if quote_text and quote_text not in seen_quotes and src_type not in seen_sources:
                selected.append(
                    RepresentativeQuote(
                        verbatim=quote_text,
                        source_type=src_type,
                        source_name=sig.source_ref.source_name if sig.source_ref else "",
                        url=sig.source_ref.url if sig.source_ref else None,
                    )
                )
                seen_quotes.add(quote_text)
                seen_sources.add(src_type)
                if len(selected) >= max_quotes:
                    break

        # Pass 2: Fill remaining quote slots up to max_quotes
        if len(selected) < max_quotes:
            for sig in sorted_signals:
                quote_text = sig.verbatim_quote.strip()
                if quote_text and quote_text not in seen_quotes:
                    src_type = sig.source_ref.source_type if sig.source_ref else "unknown"
                    selected.append(
                        RepresentativeQuote(
                            verbatim=quote_text,
                            source_type=src_type,
                            source_name=sig.source_ref.source_name if sig.source_ref else "",
                            url=sig.source_ref.url if sig.source_ref else None,
                        )
                    )
                    seen_quotes.add(quote_text)
                    if len(selected) >= max_quotes:
                        break

        # Ensure at least 1 quote if any available
        if not selected and signals:
            sig = signals[0]
            selected.append(
                RepresentativeQuote(
                    verbatim=sig.verbatim_quote,
                    source_type=sig.source_ref.source_type if sig.source_ref else "unknown",
                    source_name=sig.source_ref.source_name if sig.source_ref else "",
                    url=sig.source_ref.url if sig.source_ref else None,
                )
            )

        return selected
