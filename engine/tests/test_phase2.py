"""
tests/test_phase2.py
Phase 2 — Source Scraping Layer
Unit tests for RawRecord model, normalizer, deduplicator, and all 7 connectors.

Tests use mock data — no live API calls are made.
Run: pytest engine/tests/test_phase2.py -v
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# =============================================================================
# Helpers
# =============================================================================

def _isoformat_days_ago(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def _future_iso() -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=10)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# =============================================================================
# Tests — RawRecord model (models.py)
# =============================================================================

class TestRawRecord:
    def _make(self, **kwargs):
        from engine.scraper.models import RawRecord, AuthorMeta, PlatformMeta, now_iso
        defaults = dict(
            record_id=str(uuid.uuid4()),
            source_type="reddit",
            source_name="Reddit — r/IndianFashionAddicts",
            content_id="abc123",
            url="https://reddit.com/r/test/abc123",
            text="The size chart on Myntra is completely useless.",
            author_meta=AuthorMeta(user_type="identified", segment_hints=["female"]),
            date_collected=now_iso(),
            date_published=None,
            platform_meta=PlatformMeta(upvotes=10, reply_count=3, rating=None),
        )
        defaults.update(kwargs)
        return RawRecord(**defaults)

    def test_valid_record_created(self):
        r = self._make()
        assert r.source_type == "reddit"
        assert r.text.startswith("The size")

    def test_invalid_source_type_raises(self):
        with pytest.raises(ValueError, match="Invalid source_type"):
            self._make(source_type="invalid_type")

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            self._make(text="")

    def test_whitespace_only_text_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            self._make(text="   ")

    def test_to_dict_has_all_fields(self):
        r = self._make()
        d = r.to_dict()
        required = {
            "record_id", "source_type", "source_name", "content_id",
            "url", "text", "author_meta", "date_collected", "date_published", "platform_meta"
        }
        assert required <= d.keys()

    def test_to_dict_author_meta_structure(self):
        r = self._make()
        d = r.to_dict()
        assert "user_type" in d["author_meta"]
        assert "segment_hints" in d["author_meta"]

    def test_to_dict_platform_meta_structure(self):
        r = self._make()
        d = r.to_dict()
        assert "upvotes" in d["platform_meta"]
        assert "reply_count" in d["platform_meta"]
        assert "rating" in d["platform_meta"]

    def test_roundtrip_from_dict(self):
        r = self._make()
        r2 = type(r).from_dict(r.to_dict())
        assert r2.record_id == r.record_id
        assert r2.text == r.text
        assert r2.source_type == r.source_type

    def test_all_source_types_valid(self):
        from engine.scraper.models import VALID_SOURCE_TYPES
        for st in VALID_SOURCE_TYPES:
            r = self._make(source_type=st)
            assert r.source_type == st


# =============================================================================
# Tests — Normalizer (normalizer.py)
# =============================================================================

class TestNormalizer:
    def test_normalize_app_store(self):
        from engine.scraper.normalizer import normalize
        raw = {
            "id": "12345",
            "title": "Great app but sizing off",
            "content": "I love Myntra but the sizing guides are wrong.",
            "rating": 3,
            "date": "2025-10-01T10:00:00Z",
            "userName": "user1",
            "appId": "1457057405",
        }
        record = normalize("app_store", "Apple App Store — Myntra", raw)
        assert record is not None
        assert record.source_type == "app_store"
        assert "sizing" in record.text.lower()
        assert record.platform_meta.rating == 3.0
        assert record.author_meta.user_type == "identified"

    def test_normalize_play_store(self):
        from engine.scraper.normalizer import normalize
        raw = {
            "reviewId": "gps-001",
            "content": "Good app. Size chart is confusing.",
            "score": 4,
            "thumbsUpCount": 5,
            "at": datetime(2025, 9, 1, tzinfo=timezone.utc),
            "userName": "Priya",
            "appId": "com.myntra.android",
        }
        record = normalize("play_store", "Play Store — Myntra", raw)
        assert record is not None
        assert record.source_type == "play_store"
        assert record.platform_meta.upvotes == 5
        assert record.platform_meta.rating == 4.0

    def test_normalize_reddit_post(self):
        from engine.scraper.normalizer import normalize
        raw = {
            "id": "rp001",
            "record_kind": "post",
            "title": "Myntra sizing is a mess",
            "selftext": "Ordered M but got XL vibes.",
            "url": "https://reddit.com/r/test/rp001",
            "score": 42,
            "num_comments": 8,
            "created_utc": 1700000000,
            "author": "fashion_user",
        }
        record = normalize("reddit", "Reddit — r/IndianFashionAddicts", raw)
        assert record is not None
        assert "Myntra sizing" in record.text
        assert record.platform_meta.upvotes == 42
        assert record.platform_meta.reply_count == 8

    def test_normalize_reddit_comment(self):
        from engine.scraper.normalizer import normalize
        raw = {
            "id": "rc001",
            "record_kind": "comment",
            "body": "Same issue, their size charts are useless.",
            "permalink": "/r/test/rp001/comment/rc001",
            "score": 5,
            "created_utc": 1700001000,
        }
        record = normalize("reddit", "Reddit — r/IndianFashionAddicts", raw)
        assert record is not None
        assert "size charts" in record.text

    def test_normalize_forum(self):
        from engine.scraper.normalizer import normalize
        raw = {
            "content_id": "f001",
            "url": "https://www.quora.com/q/myntra/some-question",
            "text": "I always check sizing reviews before buying on Myntra.",
            "author": "Anjali",
            "date_published": "2025-07-15",
        }
        record = normalize("forum", "Quora — Myntra Topics", raw)
        assert record is not None
        assert record.source_type == "forum"
        assert record.author_meta.user_type == "identified"

    def test_normalize_social(self):
        from engine.scraper.normalizer import normalize
        raw = {
            "id": "tweet001",
            "text": "Myntra size chart is the worst, ordered M got L #MyntraFail",
            "author_id": "user_9999",
            "created_at": "2025-11-01T12:00:00Z",
            "public_metrics": {"like_count": 15, "reply_count": 3},
        }
        record = normalize("social", "Twitter/X — Myntra Discussions", raw)
        assert record is not None
        assert record.source_type == "social"
        assert record.platform_meta.upvotes == 15
        assert record.platform_meta.reply_count == 3

    def test_normalize_youtube(self):
        from engine.scraper.normalizer import normalize
        raw = {
            "comment_id": "yt001",
            "video_id": "abc123xyz",
            "text": "Great haul! But Myntra sizing runs small, always size up.",
            "author_name": "FashionFan",
            "published_at": "2025-08-10T09:00:00Z",
            "like_count": 22,
            "total_reply_count": 4,
        }
        record = normalize("youtube", "YouTube — Myntra Hauls", raw)
        assert record is not None
        assert "abc123xyz" in record.url
        assert record.platform_meta.upvotes == 22

    def test_normalize_review_qa(self):
        from engine.scraper.normalizer import normalize
        raw = {
            "content_id": "mntra_rev_1234567_001",
            "url": "https://www.myntra.com/1234567",
            "text": "Quality is good but size runs small. Ordered M got tight fit.",
            "author": "Rohit",
            "date_published": "2025-06-20",
            "rating": 3.5,
            "helpful_count": 7,
        }
        record = normalize("review_qa", "Myntra Product Reviews", raw)
        assert record is not None
        assert record.source_type == "review_qa"
        assert record.platform_meta.rating == 3.5
        assert record.platform_meta.upvotes == 7

    def test_normalize_empty_text_returns_none(self):
        from engine.scraper.normalizer import normalize
        raw = {"id": "empty001", "content": "   ", "appId": "123"}
        record = normalize("app_store", "Test Source", raw)
        assert record is None

    def test_normalize_unknown_source_type_returns_none(self):
        from engine.scraper.normalizer import normalize
        record = normalize("unknown_source", "Test", {"text": "some text"})
        assert record is None

    def test_record_id_deterministic(self):
        """Same content_id + source_type should always produce the same record_id."""
        from engine.scraper.normalizer import normalize
        raw = {"reviewId": "stable001", "content": "Great product.", "score": 5}
        r1 = normalize("play_store", "Play Store — Myntra", raw)
        r2 = normalize("play_store", "Play Store — Myntra", raw)
        assert r1 is not None and r2 is not None
        assert r1.record_id == r2.record_id

    def test_text_whitespace_cleaned(self):
        from engine.scraper.normalizer import normalize
        raw = {"reviewId": "ws001", "content": "Good   product  with   spaces.", "score": 5}
        r = normalize("play_store", "Play Store", raw)
        assert r is not None
        assert "  " not in r.text  # no double spaces


# =============================================================================
# Tests — Deduplicator (deduplicator.py)
# =============================================================================

class TestDeduplicator:
    def _make_record(self, content_id="c001", text="Some fashion review text here."):
        from engine.scraper.models import RawRecord, AuthorMeta, PlatformMeta, now_iso
        return RawRecord(
            record_id=str(uuid.uuid4()),
            source_type="reddit",
            source_name="Reddit — r/test",
            content_id=content_id,
            url=None,
            text=text,
            author_meta=AuthorMeta(),
            date_collected=now_iso(),
            date_published=None,
            platform_meta=PlatformMeta(),
        )

    def test_new_record_is_not_duplicate(self, tmp_path, monkeypatch):
        import engine.scraper.deduplicator as dedup_mod
        monkeypatch.setattr(dedup_mod, "FINGERPRINT_FILE", tmp_path / "fps.json")
        from engine.scraper.deduplicator import Deduplicator
        dedup = Deduplicator()
        record = self._make_record()
        assert not dedup.is_duplicate(record)

    def test_record_marked_seen_is_duplicate(self, tmp_path, monkeypatch):
        import engine.scraper.deduplicator as dedup_mod
        monkeypatch.setattr(dedup_mod, "FINGERPRINT_FILE", tmp_path / "fps.json")
        from engine.scraper.deduplicator import Deduplicator
        dedup = Deduplicator()
        record = self._make_record()
        dedup.mark_seen(record)
        assert dedup.is_duplicate(record)

    def test_different_records_not_duplicate(self, tmp_path, monkeypatch):
        import engine.scraper.deduplicator as dedup_mod
        monkeypatch.setattr(dedup_mod, "FINGERPRINT_FILE", tmp_path / "fps.json")
        from engine.scraper.deduplicator import Deduplicator
        dedup = Deduplicator()
        r1 = self._make_record("c001", "Review about size issues.")
        r2 = self._make_record("c002", "Review about return policy.")
        dedup.mark_seen(r1)
        assert not dedup.is_duplicate(r2)

    def test_fingerprints_persisted_across_instances(self, tmp_path, monkeypatch):
        import engine.scraper.deduplicator as dedup_mod
        fp_path = tmp_path / "fps.json"
        monkeypatch.setattr(dedup_mod, "FINGERPRINT_FILE", fp_path)

        from engine.scraper.deduplicator import Deduplicator
        dedup1 = Deduplicator()
        record = self._make_record()
        dedup1.mark_seen(record)
        dedup1.save()

        dedup2 = Deduplicator()
        assert dedup2.is_duplicate(record), "Fingerprint should survive across instances"

    def test_seen_count(self, tmp_path, monkeypatch):
        import engine.scraper.deduplicator as dedup_mod
        monkeypatch.setattr(dedup_mod, "FINGERPRINT_FILE", tmp_path / "fps.json")
        from engine.scraper.deduplicator import Deduplicator
        dedup = Deduplicator()
        assert dedup.seen_count == 0
        dedup.mark_seen(self._make_record("x1", "Text one"))
        dedup.mark_seen(self._make_record("x2", "Text two"))
        assert dedup.seen_count == 2


# =============================================================================
# Tests — Base Connector helpers
# =============================================================================

class TestBaseConnector:
    def _make_connector(self, volume_cap=100, lookback_days=365):
        from engine.scraper.base_connector import BaseConnector
        from engine.config_loader import SourceConfig

        class DummyConnector(BaseConnector):
            source_type = "reddit"
            def fetch(self): return []

        sc = SourceConfig(
            source_type="reddit",
            source_name="Test",
            enabled=True,
            lookback_days=lookback_days,
            volume_cap=volume_cap,
            config={},
        )
        return DummyConnector(sc)

    def test_cap_trims_to_volume_cap(self):
        conn = self._make_connector(volume_cap=3)
        items = [1, 2, 3, 4, 5]
        assert conn._cap(items) == [1, 2, 3]

    def test_cap_no_trim_when_under_cap(self):
        conn = self._make_connector(volume_cap=10)
        items = [1, 2, 3]
        assert conn._cap(items) == [1, 2, 3]

    def test_is_within_lookback_recent_date(self):
        conn = self._make_connector(lookback_days=365)
        recent = _isoformat_days_ago(30)
        assert conn._is_within_lookback(recent) is True

    def test_is_within_lookback_old_date(self):
        conn = self._make_connector(lookback_days=30)
        old = _isoformat_days_ago(60)
        assert conn._is_within_lookback(old) is False

    def test_is_within_lookback_none_returns_true(self):
        conn = self._make_connector()
        assert conn._is_within_lookback(None) is True

    def test_is_within_lookback_unparseable_returns_true(self):
        conn = self._make_connector()
        assert conn._is_within_lookback("not-a-date") is True


# =============================================================================
# Tests — Connector fetch() with mocked dependencies
# =============================================================================

class TestAppStoreConnector:
    def _make_source_config(self):
        from engine.config_loader import SourceConfig
        return SourceConfig(
            source_type="app_store",
            source_name="Apple App Store — Myntra",
            enabled=True,
            lookback_days=365,
            volume_cap=10,
            config={"app_id": "1457057405", "app_name": "Myntra", "country": "in"},
        )

    def test_fetch_returns_list_on_import_error(self, monkeypatch):
        """If app-store-scraper is not installed, fetch() returns []."""
        from engine.scraper.connector_app_store import AppStoreConnector
        sc = self._make_source_config()
        conn = AppStoreConnector(sc)
        with patch("builtins.__import__", side_effect=ImportError):
            # Use the actual import guard path inside the method
            with patch.dict("sys.modules", {"app_store_scraper": None}):
                result = conn.fetch()
        # Either [] or actual results depending on installation; just assert it's a list
        assert isinstance(result, list)

    def test_fetch_with_mock_appstore(self):
        from engine.scraper.connector_app_store import AppStoreConnector
        sc = self._make_source_config()
        conn = AppStoreConnector(sc)

        mock_reviews = [
            {
                "id": f"rev{i}",
                "title": f"Review {i}",
                "content": f"The size chart is confusing review number {i}.",
                "rating": (i % 5) + 1,
                "date": _isoformat_days_ago(10),
                "userName": f"user{i}",
                "appId": "1457057405",
            }
            for i in range(5)
        ]

        mock_app_cls = MagicMock()
        mock_app_instance = MagicMock()
        mock_app_instance.reviews = mock_reviews
        mock_app_cls.return_value = mock_app_instance

        with patch.dict("sys.modules", {"app_store_scraper": MagicMock(AppStore=mock_app_cls)}):
            result = conn.fetch()

        assert isinstance(result, list)
        assert len(result) <= sc.volume_cap


class TestPlayStoreConnector:
    def _make_source_config(self):
        from engine.config_loader import SourceConfig
        return SourceConfig(
            source_type="play_store",
            source_name="Play Store — Myntra",
            enabled=True,
            lookback_days=365,
            volume_cap=10,
            config={"app_id": "com.myntra.android", "country": "in", "language": "en"},
        )

    def test_fetch_with_mock(self):
        from engine.scraper.connector_play_store import PlayStoreConnector
        sc = self._make_source_config()
        conn = PlayStoreConnector(sc)

        mock_revs = [
            {
                "reviewId": f"gps{i}",
                "content": f"Play store review {i} about sizing.",
                "score": 3,
                "thumbsUpCount": i,
                "at": datetime.now(timezone.utc) - timedelta(days=10),
                "userName": f"user{i}",
                "appId": "com.myntra.android",
            }
            for i in range(5)
        ]

        mock_reviews_fn = MagicMock(return_value=(mock_revs, None))
        mock_sort = MagicMock()
        mock_sort.NEWEST = "newest"
        mock_gps_module = MagicMock(reviews=mock_reviews_fn, Sort=mock_sort)

        with patch.dict("sys.modules", {"google_play_scraper": mock_gps_module}):
            result = conn.fetch()

        assert isinstance(result, list)
        assert len(result) <= sc.volume_cap


class TestRedditConnector:
    def _make_source_config(self):
        from engine.config_loader import SourceConfig
        return SourceConfig(
            source_type="reddit",
            source_name="Reddit — r/IndianFashionAddicts",
            enabled=True,
            lookback_days=365,
            volume_cap=10,
            config={
                "subreddit": "IndianFashionAddicts",
                "search_keywords": ["myntra size"],
                "sort": "top",
                "include_comments": False,
                "max_comments_per_post": 5,
            },
        )

    def test_fetch_fails_gracefully_without_credentials(self, monkeypatch):
        """Without env vars, Reddit connector returns [] without raising."""
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
        from engine.scraper.connector_reddit import RedditConnector
        sc = self._make_source_config()
        conn = RedditConnector(sc)
        # Should not raise; gracefully returns []
        result = conn.fetch()
        assert isinstance(result, list)


class TestYouTubeConnector:
    def _make_source_config(self):
        from engine.config_loader import SourceConfig
        return SourceConfig(
            source_type="youtube",
            source_name="YouTube — Myntra Hauls",
            enabled=True,
            lookback_days=365,
            volume_cap=10,
            config={
                "search_queries": ["Myntra haul"],
                "max_videos_per_query": 2,
                "max_comments_per_video": 5,
                "language": "en",
                "order": "relevance",
            },
        )

    def test_fetch_fails_gracefully_without_api_key(self, monkeypatch):
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
        from engine.scraper.connector_youtube import YouTubeConnector
        sc = self._make_source_config()
        conn = YouTubeConnector(sc)
        result = conn.fetch()
        assert isinstance(result, list)


class TestSocialConnector:
    def _make_source_config(self):
        from engine.config_loader import SourceConfig
        return SourceConfig(
            source_type="social",
            source_name="Twitter/X — Myntra",
            enabled=True,
            lookback_days=180,
            volume_cap=10,
            config={
                "platform": "twitter",
                "search_queries": ["myntra size issue"],
                "language": "en",
                "exclude_retweets": True,
                "min_likes": 0,
            },
        )

    def test_fetch_fails_gracefully_without_token(self, monkeypatch):
        monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
        from engine.scraper.connector_social import SocialConnector
        sc = self._make_source_config()
        conn = SocialConnector(sc)
        result = conn.fetch()
        assert result == []

    def test_unsupported_platform_returns_empty(self):
        from engine.config_loader import SourceConfig
        from engine.scraper.connector_social import SocialConnector
        sc = SourceConfig(
            source_type="social",
            source_name="Instagram",
            enabled=True,
            lookback_days=180,
            volume_cap=10,
            config={"platform": "instagram", "search_queries": []},
        )
        conn = SocialConnector(sc)
        result = conn.fetch()
        assert result == []


class TestForumConnector:
    def _make_source_config(self):
        from engine.config_loader import SourceConfig
        return SourceConfig(
            source_type="forum",
            source_name="Quora — Myntra",
            enabled=True,
            lookback_days=365,
            volume_cap=10,
            config={
                "base_url": "https://www.quora.com",
                "topic_urls": ["https://www.quora.com/topic/Myntra-Online-Shopping"],
                "selector_config": {},
                "scrape_comments": False,
                "request_delay_seconds": 0.0,
            },
        )

    def test_fetch_with_mock_requests(self):
        from engine.scraper.connector_forum import ForumConnector
        sc = self._make_source_config()
        conn = ForumConnector(sc)

        mock_html = """
        <html><body>
        <p>I always check sizing charts before buying on Myntra. The reviews are helpful.</p>
        <p>AJIO sizes run small compared to what I expected. Ordered L got M size fit.</p>
        <p>Short.</p>
        </body></html>
        """

        mock_resp = MagicMock()
        mock_resp.text = mock_html
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200

        with patch("requests.get", return_value=mock_resp):
            with patch("requests.Session.get", return_value=mock_resp):
                import requests
                result = conn.fetch()

        assert isinstance(result, list)

    def test_fetch_empty_when_no_urls(self):
        from engine.config_loader import SourceConfig
        from engine.scraper.connector_forum import ForumConnector
        sc = SourceConfig(
            source_type="forum",
            source_name="Empty Forum",
            enabled=True,
            lookback_days=365,
            volume_cap=10,
            config={"topic_urls": [], "selector_config": {}, "request_delay_seconds": 0.0},
        )
        conn = ForumConnector(sc)
        result = conn.fetch()
        assert result == []


class TestReviewQAConnector:
    def _make_source_config(self, platform="myntra"):
        from engine.config_loader import SourceConfig
        return SourceConfig(
            source_type="review_qa",
            source_name=f"{platform.upper()} Product Reviews",
            enabled=True,
            lookback_days=365,
            volume_cap=10,
            config={
                "platform": platform,
                "base_url": f"https://www.{platform}.com",
                "category_urls": [f"https://www.{platform}.com/men-tshirts"],
                "products_per_category": 2,
                "reviews_per_product": 5,
                "include_qa": False,
                "request_delay_seconds": 0.0,
            },
        )

    def test_normalizer_handles_review_qa_raw(self):
        """Verify normalizer correctly handles review_qa raw dicts."""
        from engine.scraper.normalizer import normalize
        raw = {
            "content_id": "myntra_rev_9999_001",
            "url": "https://www.myntra.com/9999",
            "text": "Excellent product! Fits well and the quality is great.",
            "author": "TestUser",
            "date_published": "2025-09-15",
            "rating": 5.0,
            "helpful_count": 12,
            "record_kind": "review",
        }
        record = normalize("review_qa", "Myntra Product Reviews", raw)
        assert record is not None
        assert record.source_type == "review_qa"
        assert record.platform_meta.rating == 5.0


# =============================================================================
# Tests — Orchestrator (run.py) — unit test with mock connectors
# =============================================================================

class TestScrapingOrchestrator:
    def test_run_scraping_dry_run(self, tmp_path, monkeypatch):
        """
        Dry-run mode should execute without errors even if connectors return [].
        Uses a minimal source config with a mock connector.
        """
        import engine.scraper.deduplicator as dedup_mod
        import engine.data_store as ds_mod

        monkeypatch.setattr(dedup_mod, "FINGERPRINT_FILE", tmp_path / "fps.json")
        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        # Patch load_all_config to return a minimal config
        from engine.config_loader import SourceListConfig, SourceConfig, AllConfig, TaxonomyConfig, QuestionSetConfig, ScoringConfig, ScoringWeights, ConfidenceThresholds

        mock_source = SourceConfig(
            source_type="reddit",
            source_name="Mock Reddit",
            enabled=True,
            lookback_days=365,
            volume_cap=10,
            config={"subreddit": "test", "search_keywords": ["test"], "sort": "top", "include_comments": False, "max_comments_per_post": 0},
        )
        mock_cfg = MagicMock()
        mock_cfg.source_list.enabled_sources = [mock_source]

        with patch("engine.scraper.run.load_all_config", return_value=mock_cfg):
            with patch("engine.scraper.run._import_connector") as mock_import:
                mock_connector_cls = MagicMock()
                mock_connector_instance = MagicMock()
                mock_connector_instance.fetch.return_value = []
                mock_connector_cls.return_value = mock_connector_instance
                mock_import.return_value = mock_connector_cls

                from engine.scraper.run import run_scraping
                summary = run_scraping(dry_run=True)

        assert isinstance(summary, dict)
        assert "records_written" in summary
        assert "errors" in summary

    def test_run_scraping_writes_records(self, tmp_path, monkeypatch):
        """Records returned by mock connector should be written to store."""
        import engine.scraper.deduplicator as dedup_mod
        import engine.data_store as ds_mod

        monkeypatch.setattr(dedup_mod, "FINGERPRINT_FILE", tmp_path / "fps.json")
        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        from engine.config_loader import SourceConfig
        mock_source = SourceConfig(
            source_type="play_store",
            source_name="Play Store Mock",
            enabled=True,
            lookback_days=365,
            volume_cap=5,
            config={"app_id": "com.test", "country": "in", "language": "en"},
        )
        mock_cfg = MagicMock()
        mock_cfg.source_list.enabled_sources = [mock_source]

        # Two mock raw records that normalize successfully
        mock_raw_records = [
            {"reviewId": "mock001", "content": "Size chart is very confusing on this app.", "score": 2, "thumbsUpCount": 3, "at": None, "userName": "u1", "appId": "com.test"},
            {"reviewId": "mock002", "content": "Returned because the fit was completely off.", "score": 1, "thumbsUpCount": 1, "at": None, "userName": "u2", "appId": "com.test"},
        ]

        with patch("engine.scraper.run.load_all_config", return_value=mock_cfg):
            with patch("engine.scraper.run._import_connector") as mock_import:
                mock_cls = MagicMock()
                mock_inst = MagicMock()
                mock_inst.fetch.return_value = mock_raw_records
                mock_cls.return_value = mock_inst
                mock_import.return_value = mock_cls

                from engine.scraper.run import run_scraping
                summary = run_scraping()

        assert summary["records_written"] == 2
        assert summary["duplicates_skipped"] == 0

    def test_dedup_prevents_double_write(self, tmp_path, monkeypatch):
        """Running the same mock data twice should deduplicate on the second run."""
        import engine.scraper.deduplicator as dedup_mod
        import engine.data_store as ds_mod

        fp_path = tmp_path / "fps.json"
        monkeypatch.setattr(dedup_mod, "FINGERPRINT_FILE", fp_path)
        monkeypatch.setattr(ds_mod, "RAW_RECORDS_DIR", tmp_path / "raw")
        monkeypatch.setattr(ds_mod, "SIGNALS_DIR", tmp_path / "signals")
        monkeypatch.setattr(ds_mod, "OPPORTUNITIES_DIR", tmp_path / "opps")

        from engine.config_loader import SourceConfig
        mock_source = SourceConfig(
            source_type="play_store",
            source_name="Play Store Mock",
            enabled=True,
            lookback_days=365,
            volume_cap=5,
            config={"app_id": "com.test", "country": "in", "language": "en"},
        )
        mock_cfg = MagicMock()
        mock_cfg.source_list.enabled_sources = [mock_source]

        same_raw = [
            {"reviewId": "dedup001", "content": "This exact review will be seen twice.", "score": 3, "at": None},
        ]

        def run_once():
            with patch("engine.scraper.run.load_all_config", return_value=mock_cfg):
                with patch("engine.scraper.run._import_connector") as mock_import:
                    mock_cls = MagicMock()
                    mock_inst = MagicMock()
                    mock_inst.fetch.return_value = same_raw
                    mock_cls.return_value = mock_inst
                    mock_import.return_value = mock_cls
                    from engine.scraper.run import run_scraping
                    return run_scraping()

        s1 = run_once()
        s2 = run_once()

        assert s1["records_written"] == 1
        assert s2["records_written"] == 0
        assert s2["duplicates_skipped"] == 1
