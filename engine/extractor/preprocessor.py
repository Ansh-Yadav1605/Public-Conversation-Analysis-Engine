"""
engine/extractor/preprocessor.py
Public Conversation Analysis Engine — Text Preprocessor

Cleans raw text and splits it into sentences for per-sentence taxonomy matching.
Sentence-level granularity is critical: a single review may contain multiple
distinct signals, each needing its own Signal record.

Pipeline per RawRecord.text:
    1. Strip HTML tags
    2. Strip/normalize URLs
    3. Normalize emojis → descriptive text tokens
    4. Language detection — flag non-English text
    5. Clean whitespace, collapse repeated punctuation
    6. Sentence-split
    7. Return PreprocessedText with both original and cleaned text + sentence list

Usage:
    from engine.extractor.preprocessor import preprocess
    result = preprocess(raw_record.text)
    for sent in result.sentences:
        ...  # run taxonomy matcher on each sentence
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from engine.logger import get_logger

log = get_logger(__name__)

# Minimum character length for a sentence to be worth processing
MIN_SENTENCE_LENGTH = 15

# Emoji → text token map for the most common fashion-context emojis
_EMOJI_MAP = {
    "😊": " happy ", "😃": " happy ", "😢": " sad ", "😞": " disappointed ",
    "😡": " angry ", "😤": " frustrated ", "❤️": " love ", "💔": " disappointed ",
    "👍": " good ", "👎": " bad ", "⭐": " star ", "🌟": " great ",
    "🔥": " trending ", "💯": " great ", "😍": " love ", "🙄": " annoyed ",
    "😩": " frustrated ", "💸": " expensive ", "🏷️": " price ",
    "📦": " delivery ", "🛍️": " shopping ", "👗": " dress ",
    "👕": " shirt ", "👖": " pants ", "👠": " shoes ",
    "✅": " ok ", "❌": " no ", "⚠️": " warning ",
}

# HTML tag pattern
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# URL pattern
_URL_RE = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$\-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)
# Repeated punctuation (e.g. "!!!!" → "!")
_REPEAT_PUNCT_RE = re.compile(r"([!?.,;:])\1{2,}")
# Repeated whitespace
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class PreprocessedText:
    """Result of text preprocessing for one RawRecord."""
    original_text: str                    # unchanged raw text
    cleaned_text: str                     # fully cleaned text
    sentences: list[str]                  # sentence-split cleaned text
    is_english: bool = True               # False if detected as non-English
    language: Optional[str] = None        # detected language code (e.g. "en")
    word_count: int = 0


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub(" ", text)


def _strip_urls(text: str) -> str:
    return _URL_RE.sub(" ", text)


def _normalize_emojis(text: str) -> str:
    for emoji, replacement in _EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    # Remove any remaining emoji-like characters (unicode ranges)
    text = re.sub(
        r"[\U00010000-\U0010ffff]",  # supplementary unicode (most emojis)
        " ",
        text,
        flags=re.UNICODE,
    )
    return text


def _clean_whitespace(text: str) -> str:
    text = _REPEAT_PUNCT_RE.sub(r"\1", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _detect_language(text: str) -> tuple[str, bool]:
    """
    Detect the language of the text.
    Returns (language_code, is_english).
    Falls back to ("en", True) if langdetect is not installed or text is too short.
    """
    if len(text) < 20:
        return "en", True
    try:
        from langdetect import detect, LangDetectException  # type: ignore[import]
        lang = detect(text)
        return lang, lang == "en"
    except ImportError:
        return "en", True   # langdetect not installed — include all text
    except Exception:
        return "en", True   # detection failed — default to include


def _sentence_split(text: str) -> list[str]:
    """
    Split text into sentences using NLTK's Punkt tokenizer when available,
    falling back to a simple regex split.
    """
    # Try NLTK punkt
    try:
        import nltk  # type: ignore[import]
        try:
            sentences = nltk.sent_tokenize(text)
        except LookupError:
            # Download punkt data on first use
            nltk.download("punkt", quiet=True)
            nltk.download("punkt_tab", quiet=True)
            sentences = nltk.sent_tokenize(text)
        return [s.strip() for s in sentences if s.strip()]
    except ImportError:
        pass

    # Fallback: split on sentence-ending punctuation
    raw_sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in raw_sentences if s.strip()]


def preprocess(text: str) -> PreprocessedText:
    """
    Full preprocessing pipeline for a single RawRecord.text.

    Args:
        text: Raw text from a RawRecord.

    Returns:
        PreprocessedText with cleaned text, sentences, and language info.
        If text is empty, returns a PreprocessedText with empty sentences.
    """
    original = text

    if not text or not text.strip():
        return PreprocessedText(
            original_text=original,
            cleaned_text="",
            sentences=[],
            is_english=True,
            language="en",
            word_count=0,
        )

    # Step 1–3: Clean text
    cleaned = _strip_html(text)
    cleaned = _strip_urls(cleaned)
    cleaned = _normalize_emojis(cleaned)
    cleaned = _clean_whitespace(cleaned)

    # Step 4: Language detection
    language, is_english = _detect_language(cleaned)
    if not is_english:
        log.debug(
            "Non-English text detected (lang=%s). Text will be flagged but still processed.",
            language,
        )

    # Step 5: Sentence split
    raw_sentences = _sentence_split(cleaned)
    sentences = [s for s in raw_sentences if len(s) >= MIN_SENTENCE_LENGTH]

    word_count = len(cleaned.split())

    return PreprocessedText(
        original_text=original,
        cleaned_text=cleaned,
        sentences=sentences,
        is_english=is_english,
        language=language,
        word_count=word_count,
    )
