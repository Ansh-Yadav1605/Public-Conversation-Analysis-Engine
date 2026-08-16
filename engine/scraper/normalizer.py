"""
engine/scraper/normalizer.py
Public Conversation Analysis Engine — Normalization Layer

Converts source-native raw dicts (as returned by each connector) into
validated RawRecord objects.

Each source type has its own _normalize_<source_type>() function.
The public entry point is normalize(source_type, source_name, raw) -> RawRecord.

Contract:
    - Every field in RawRecord is always populated (or explicitly None).
    - Input text is lightly cleaned (strip, collapse whitespace) but not altered.
    - The original source data is never mutated.
    - Raises ValueError for unrecognizable source_type or empty text.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from engine.scraper.models import AuthorMeta, PlatformMeta, RawRecord, now_iso
from engine.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Collapse whitespace and strip leading/trailing space."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _make_record_id(source_type: str, content_id: str) -> str:
    """Deterministic UUID derived from source_type + content_id for idempotency."""
    key = f"{source_type}::{content_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Source-specific normalizers
# ---------------------------------------------------------------------------

def _normalize_app_store(source_name: str, raw: dict[str, Any]) -> RawRecord:
    """
    Normalize Apple App Store review.

    Expected raw keys (from app-store-scraper or iTunes RSS):
        id, userName, title, content (or review), rating, date, appId
    """
    content_id = str(raw.get("id", raw.get("reviewId", "")))
    title = raw.get("title", "")
    body = raw.get("content", raw.get("review", ""))
    text = _clean_text(f"{title}. {body}".strip(". "))

    app_id = raw.get("appId", raw.get("app_id", ""))
    url = raw.get("url", f"https://apps.apple.com/in/app/id{app_id}") if app_id else None

    return RawRecord(
        record_id=_make_record_id("app_store", content_id),
        source_type="app_store",
        source_name=source_name,
        content_id=content_id,
        url=url,
        text=text,
        author_meta=AuthorMeta(
            user_type="identified" if raw.get("userName") else "anonymous",
            segment_hints=[],
        ),
        date_collected=now_iso(),
        date_published=str(raw.get("date", raw.get("updated", ""))) or None,
        platform_meta=PlatformMeta(
            upvotes=None,
            reply_count=None,
            rating=_safe_float(raw.get("rating", raw.get("score"))),
        ),
    )


def _normalize_play_store(source_name: str, raw: dict[str, Any]) -> RawRecord:
    """
    Normalize Google Play Store review.

    Expected raw keys (from google-play-scraper):
        reviewId, userName, content, score, thumbsUpCount, at, appId
    """
    content_id = str(raw.get("reviewId", ""))
    text = _clean_text(raw.get("content", ""))

    app_id = raw.get("appId", "")
    url = (
        f"https://play.google.com/store/apps/details?id={app_id}"
        if app_id else None
    )

    published = raw.get("at")
    if hasattr(published, "isoformat"):
        published = published.isoformat()
    elif published is not None:
        published = str(published)

    return RawRecord(
        record_id=_make_record_id("play_store", content_id),
        source_type="play_store",
        source_name=source_name,
        content_id=content_id,
        url=url,
        text=text,
        author_meta=AuthorMeta(
            user_type="identified" if raw.get("userName") else "anonymous",
            segment_hints=[],
        ),
        date_collected=now_iso(),
        date_published=published,
        platform_meta=PlatformMeta(
            upvotes=_safe_int(raw.get("thumbsUpCount")),
            reply_count=None,
            rating=_safe_float(raw.get("score")),
        ),
    )


def _normalize_reddit(source_name: str, raw: dict[str, Any]) -> RawRecord:
    """
    Normalize a Reddit post or comment.

    Expected raw keys:
        id, url, selftext (or body), title, score, num_comments, created_utc,
        author, subreddit, permalink, record_kind ("post" | "comment")
    """
    kind = raw.get("record_kind", "post")
    content_id = str(raw.get("id", ""))

    if kind == "comment":
        text = _clean_text(raw.get("body", ""))
    else:
        title = raw.get("title", "")
        body = raw.get("selftext", "")
        text = _clean_text(f"{title}\n{body}".strip())

    permalink = raw.get("permalink", "")
    url = raw.get("url") or (
        f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
    )

    created = raw.get("created_utc")
    if created:
        from datetime import datetime, timezone
        try:
            published = datetime.fromtimestamp(float(created), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            published = str(created)
    else:
        published = None

    author = str(raw.get("author", "")) or None

    return RawRecord(
        record_id=_make_record_id("reddit", content_id),
        source_type="reddit",
        source_name=source_name,
        content_id=content_id,
        url=url,
        text=text,
        author_meta=AuthorMeta(
            user_type="identified" if author and author != "[deleted]" else "anonymous",
            segment_hints=[],
        ),
        date_collected=now_iso(),
        date_published=published,
        platform_meta=PlatformMeta(
            upvotes=_safe_int(raw.get("score")),
            reply_count=_safe_int(raw.get("num_comments")),
            rating=None,
        ),
    )


def _normalize_forum(source_name: str, raw: dict[str, Any]) -> RawRecord:
    """
    Normalize a scraped forum/community post.

    Expected raw keys:
        content_id (or url hash), url, text, author, date_published,
        upvotes, reply_count
    """
    url = raw.get("url", "")
    content_id = str(
        raw.get("content_id")
        or hashlib.sha256(url.encode()).hexdigest()[:16]
    )
    text = _clean_text(raw.get("text", raw.get("body", "")))

    return RawRecord(
        record_id=_make_record_id("forum", content_id),
        source_type="forum",
        source_name=source_name,
        content_id=content_id,
        url=url or None,
        text=text,
        author_meta=AuthorMeta(
            user_type="identified" if raw.get("author") else "anonymous",
            segment_hints=[],
        ),
        date_collected=now_iso(),
        date_published=raw.get("date_published"),
        platform_meta=PlatformMeta(
            upvotes=_safe_int(raw.get("upvotes")),
            reply_count=_safe_int(raw.get("reply_count")),
            rating=None,
        ),
    )


def _normalize_social(source_name: str, raw: dict[str, Any]) -> RawRecord:
    """
    Normalize a social media post (Twitter/X).

    Expected raw keys (from Tweepy v2 or similar):
        id (or tweet_id), text, author_id, created_at, url,
        public_metrics (dict with like_count, reply_count)
    """
    content_id = str(raw.get("id", raw.get("tweet_id", "")))
    text = _clean_text(raw.get("text", ""))
    url = raw.get("url") or (
        f"https://twitter.com/i/web/status/{content_id}" if content_id else None
    )

    metrics = raw.get("public_metrics", {}) or {}

    return RawRecord(
        record_id=_make_record_id("social", content_id),
        source_type="social",
        source_name=source_name,
        content_id=content_id,
        url=url,
        text=text,
        author_meta=AuthorMeta(
            user_type="identified" if raw.get("author_id") else "anonymous",
            segment_hints=[],
        ),
        date_collected=now_iso(),
        date_published=raw.get("created_at"),
        platform_meta=PlatformMeta(
            upvotes=_safe_int(metrics.get("like_count")),
            reply_count=_safe_int(metrics.get("reply_count")),
            rating=None,
        ),
    )


def _normalize_youtube(source_name: str, raw: dict[str, Any]) -> RawRecord:
    """
    Normalize a YouTube video comment.

    Expected raw keys (from YouTube Data API v3 CommentThread):
        comment_id, video_id, text, author_name, published_at,
        like_count, total_reply_count
    """
    content_id = str(raw.get("comment_id", raw.get("id", "")))
    text = _clean_text(raw.get("text", raw.get("textDisplay", raw.get("textOriginal", ""))))
    video_id = raw.get("video_id", "")
    url = f"https://www.youtube.com/watch?v={video_id}" if video_id else raw.get("url")

    return RawRecord(
        record_id=_make_record_id("youtube", content_id),
        source_type="youtube",
        source_name=source_name,
        content_id=content_id,
        url=url,
        text=text,
        author_meta=AuthorMeta(
            user_type="identified" if raw.get("author_name") else "anonymous",
            segment_hints=[],
        ),
        date_collected=now_iso(),
        date_published=raw.get("published_at"),
        platform_meta=PlatformMeta(
            upvotes=_safe_int(raw.get("like_count")),
            reply_count=_safe_int(raw.get("total_reply_count")),
            rating=None,
        ),
    )


def _normalize_review_qa(source_name: str, raw: dict[str, Any]) -> RawRecord:
    """
    Normalize a Myntra / AJIO product review or Q&A entry.

    Expected raw keys:
        content_id, product_id, product_name, platform, url,
        text (review body or Q&A combined), author, date_published,
        rating, helpful_count, record_kind ("review" | "qa")
    """
    content_id = str(raw.get("content_id", raw.get("review_id", raw.get("qa_id", ""))))
    title = raw.get("title", "")
    body = raw.get("text", raw.get("body", ""))
    text = _clean_text(f"{title}. {body}".strip(". "))

    return RawRecord(
        record_id=_make_record_id("review_qa", content_id),
        source_type="review_qa",
        source_name=source_name,
        content_id=content_id,
        url=raw.get("url"),
        text=text,
        author_meta=AuthorMeta(
            user_type="identified" if raw.get("author") else "anonymous",
            segment_hints=[],
        ),
        date_collected=now_iso(),
        date_published=raw.get("date_published"),
        platform_meta=PlatformMeta(
            upvotes=_safe_int(raw.get("helpful_count")),
            reply_count=None,
            rating=_safe_float(raw.get("rating")),
        ),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_NORMALIZER_MAP = {
    "app_store":  _normalize_app_store,
    "play_store": _normalize_play_store,
    "reddit":     _normalize_reddit,
    "forum":      _normalize_forum,
    "social":     _normalize_social,
    "youtube":    _normalize_youtube,
    "review_qa":  _normalize_review_qa,
}


def normalize(source_type: str, source_name: str, raw: dict[str, Any]) -> RawRecord | None:
    """
    Normalize a source-native raw dict into a validated RawRecord.

    Args:
        source_type: One of the 7 valid source type strings.
        source_name: Human-readable source label (from source_list.yaml).
        raw:         Source-native dict as returned by the connector.

    Returns:
        RawRecord if normalization succeeds.
        None if the record is invalid (empty text, unknown type) — caller should skip.
    """
    normalizer_fn = _NORMALIZER_MAP.get(source_type)
    if normalizer_fn is None:
        log.warning("normalize(): unknown source_type '%s' — skipping record.", source_type)
        return None

    try:
        record = normalizer_fn(source_name, raw)
        if not record.text:
            log.debug("Skipping record with empty text from '%s'.", source_name)
            return None
        return record
    except Exception as exc:
        log.warning(
            "normalize(): failed for source_type='%s' source='%s': %s",
            source_type, source_name, exc,
        )
        return None
