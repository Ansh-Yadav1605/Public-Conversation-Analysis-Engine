"""
engine/extractor/taxonomy_matcher.py
Public Conversation Analysis Engine — Taxonomy Matcher

Implements two-layer signal detection as specified in implementation-plan.md §3.3:

Layer A — Keyword/Rule Matching
    For each sentence, check against every taxonomy node's keyword list.
    Matching is case-insensitive. Multi-word phrases are matched as substrings.
    If any keyword matches: confidence = KEYWORD_CONFIDENCE (0.90).

Layer B — Embedding Similarity
    For sentences with NO keyword match, compute cosine similarity between
    the sentence embedding and each taxonomy node's embedding centroid.
    Model: all-MiniLM-L6-v2 (local, free, good accuracy for classification).
    If similarity >= EMBEDDING_THRESHOLD (0.65): confidence = similarity score.

The embeddings for all taxonomy nodes are pre-computed on first call and
cached in memory for the lifetime of the TaxonomyMatcher instance.

Usage:
    from engine.config_loader import load_taxonomy
    from engine.extractor.taxonomy_matcher import TaxonomyMatcher

    matcher = TaxonomyMatcher(load_taxonomy())
    matches = matcher.match_sentence("I never know which size to order on Myntra")
    # Returns list of MatchResult objects
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from engine.config_loader import TaxonomyConfig, TaxonomyNode
from engine.logger import get_logger

if TYPE_CHECKING:
    import numpy as np

log = get_logger(__name__)

# ── Tunable constants ──────────────────────────────────────────────────────
KEYWORD_CONFIDENCE: float = 0.90
EMBEDDING_THRESHOLD: float = 0.65
EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"


@dataclass
class MatchResult:
    """A single taxonomy node match for a sentence."""
    node: TaxonomyNode
    sentence: str
    confidence: float
    match_layer: str   # "keyword" | "embedding"
    matched_keywords: list[str] = field(default_factory=list)


class TaxonomyMatcher:
    """
    Two-layer taxonomy matcher (Layer A: keyword, Layer B: embedding).

    Initialise once per pipeline run; match_sentence() can be called
    repeatedly for each sentence from each RawRecord.
    """

    def __init__(self, taxonomy: TaxonomyConfig) -> None:
        self.taxonomy = taxonomy
        self._node_embeddings: Optional[dict[str, "np.ndarray"]] = None
        self._embedder = None
        self._embedding_available = False
        self._try_load_embedder()

    # ── Public API ─────────────────────────────────────────────────────────

    def match_sentence(self, sentence: str) -> list[MatchResult]:
        """
        Run both matching layers on a single sentence.

        Returns a list of MatchResult objects (0 = no match, N = multiple signals).
        Each result corresponds to one matched taxonomy node.
        """
        results: list[MatchResult] = []
        matched_node_ids: set[str] = set()

        # ── Layer A: Keyword matching ──────────────────────────────────────
        for node in self.taxonomy.nodes:
            matched_kws = self._keyword_match(sentence, node)
            if matched_kws:
                results.append(
                    MatchResult(
                        node=node,
                        sentence=sentence,
                        confidence=KEYWORD_CONFIDENCE,
                        match_layer="keyword",
                        matched_keywords=matched_kws,
                    )
                )
                matched_node_ids.add(node.node_id)

        # ── Layer B: Embedding similarity (only for unmatched nodes) ───────
        if self._embedding_available:
            unmatched_nodes = [
                n for n in self.taxonomy.nodes if n.node_id not in matched_node_ids
            ]
            if unmatched_nodes:
                embedding_matches = self._embedding_match(sentence, unmatched_nodes)
                results.extend(embedding_matches)

        return results

    def precompute_node_embeddings(self) -> None:
        """
        Pre-compute and cache embeddings for all taxonomy nodes.
        Called once before the extraction run starts.
        """
        if not self._embedding_available:
            log.info("Embedding model not available — Layer B will be skipped.")
            return

        log.info(
            "Pre-computing embeddings for %d taxonomy nodes (model: %s) ...",
            len(self.taxonomy.nodes), EMBEDDING_MODEL_NAME,
        )
        import numpy as np

        self._node_embeddings = {}
        for node in self.taxonomy.nodes:
            node_text = self._node_text_for_embedding(node)
            emb = self._embedder.encode(node_text, normalize_embeddings=True)
            self._node_embeddings[node.node_id] = emb

        log.info("Node embeddings pre-computed for %d nodes.", len(self._node_embeddings))

    # ── Layer A internals ──────────────────────────────────────────────────

    @staticmethod
    def _keyword_match(sentence: str, node: TaxonomyNode) -> list[str]:
        """Return the list of keywords from this node that appear in the sentence."""
        sentence_lower = sentence.lower()
        matched = []
        for kw in node.detection_rules.keywords:
            kw_lower = kw.lower()
            # Whole-phrase substring match (not restricted to word boundaries for
            # multi-word phrases, but must not be part of a longer word for single words)
            if " " in kw_lower:
                if kw_lower in sentence_lower:
                    matched.append(kw)
            else:
                # Single word: check for word-boundary match
                pattern = r"\b" + re.escape(kw_lower) + r"\b"
                if re.search(pattern, sentence_lower):
                    matched.append(kw)
        return matched

    # ── Layer B internals ──────────────────────────────────────────────────

    def _try_load_embedder(self) -> None:
        """Attempt to load the sentence-transformers model. Non-fatal if unavailable."""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
            self._embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
            self._embedding_available = True
            log.info("Embedding model loaded: %s", EMBEDDING_MODEL_NAME)
        except ImportError:
            log.warning(
                "sentence-transformers not installed. Layer B (embedding) will be skipped. "
                "Install with: pip install sentence-transformers"
            )
            self._embedding_available = False
        except Exception as exc:
            log.warning("Could not load embedding model '%s': %s — Layer B disabled.", EMBEDDING_MODEL_NAME, exc)
            self._embedding_available = False

    def _embedding_match(
        self, sentence: str, nodes: list[TaxonomyNode]
    ) -> list[MatchResult]:
        """Compute cosine similarity between sentence and each unmatched node."""
        import numpy as np

        # Compute sentence embedding
        sent_emb = self._embedder.encode(sentence, normalize_embeddings=True)

        results = []
        for node in nodes:
            if self._node_embeddings and node.node_id in self._node_embeddings:
                node_emb = self._node_embeddings[node.node_id]
            else:
                # Compute on-the-fly if precompute wasn't called
                node_text = self._node_text_for_embedding(node)
                node_emb = self._embedder.encode(node_text, normalize_embeddings=True)

            # Cosine similarity (both embeddings are L2-normalized → dot product = cosine)
            similarity = float(np.dot(sent_emb, node_emb))

            if similarity >= EMBEDDING_THRESHOLD:
                results.append(
                    MatchResult(
                        node=node,
                        sentence=sentence,
                        confidence=round(similarity, 4),
                        match_layer="embedding",
                        matched_keywords=[],
                    )
                )

        return results

    @staticmethod
    def _node_text_for_embedding(node: TaxonomyNode) -> str:
        """
        Build the text used to embed a taxonomy node.
        = node label + embedding_hint + top 10 keywords (space-separated).
        """
        kw_sample = " ".join(node.detection_rules.keywords[:10])
        return f"{node.label}. {node.detection_rules.embedding_hint} {kw_sample}"
