"""
engine/scraper/models.py
Public Conversation Analysis Engine — RawRecord Data Model

Defines the canonical RawRecord schema as specified in architecture.md §4.1.3.
Every source connector produces source-native dicts; the normalizer converts
them into validated RawRecord objects before they reach the data store.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# AuthorMeta & PlatformMeta — nested schema components
# ---------------------------------------------------------------------------

@dataclass
class AuthorMeta:
    user_type: str = "anonymous"   # "anonymous" | "identified"
    segment_hints: list[str] = field(default_factory=list)


@dataclass
class PlatformMeta:
    upvotes: Optional[int] = None
    reply_count: Optional[int] = None
    rating: Optional[float] = None    # star rating 1–5 where applicable


# ---------------------------------------------------------------------------
# RawRecord — canonical unified schema
# ---------------------------------------------------------------------------

VALID_SOURCE_TYPES = frozenset({
    "app_store", "play_store", "reddit", "forum", "social", "youtube", "review_qa"
})


@dataclass
class RawRecord:
    """
    Unified raw conversation record produced by the normalization layer.

    One RawRecord = one atomic piece of public conversation text
    (a review, comment, post, or reply) from any source type.

    Fields match architecture.md §4.1.3 exactly. All fields are always
    present; optional fields default to None rather than being absent.
    """

    record_id: str                    # UUID v4 — generated if not supplied
    source_type: str                  # one of VALID_SOURCE_TYPES
    source_name: str                  # human-readable e.g. "Reddit — r/IndianFashionAddicts"
    content_id: str                   # platform-native ID (used for dedup)
    url: Optional[str]                # direct link to original content
    text: str                         # full cleaned text of the record
    author_meta: AuthorMeta           # user type + segment hints
    date_collected: str               # ISO-8601 — when the engine fetched it
    date_published: Optional[str]     # ISO-8601 — original publish date, or None
    platform_meta: PlatformMeta       # upvotes, reply_count, rating

    def __post_init__(self) -> None:
        if self.source_type not in VALID_SOURCE_TYPES:
            raise ValueError(
                f"Invalid source_type '{self.source_type}'. "
                f"Must be one of: {sorted(VALID_SOURCE_TYPES)}"
            )
        if not self.text or not self.text.strip():
            raise ValueError("RawRecord.text must be non-empty.")
        if not self.record_id:
            self.record_id = str(uuid.uuid4())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for JSONL storage."""
        return {
            "record_id": self.record_id,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "content_id": self.content_id,
            "url": self.url,
            "text": self.text,
            "author_meta": {
                "user_type": self.author_meta.user_type,
                "segment_hints": self.author_meta.segment_hints,
            },
            "date_collected": self.date_collected,
            "date_published": self.date_published,
            "platform_meta": {
                "upvotes": self.platform_meta.upvotes,
                "reply_count": self.platform_meta.reply_count,
                "rating": self.platform_meta.rating,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RawRecord":
        """Deserialize from a stored JSONL dict."""
        am = data.get("author_meta", {})
        pm = data.get("platform_meta", {})
        return cls(
            record_id=data["record_id"],
            source_type=data["source_type"],
            source_name=data["source_name"],
            content_id=data["content_id"],
            url=data.get("url"),
            text=data["text"],
            author_meta=AuthorMeta(
                user_type=am.get("user_type", "anonymous"),
                segment_hints=am.get("segment_hints", []),
            ),
            date_collected=data["date_collected"],
            date_published=data.get("date_published"),
            platform_meta=PlatformMeta(
                upvotes=pm.get("upvotes"),
                reply_count=pm.get("reply_count"),
                rating=pm.get("rating"),
            ),
        )


def now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
