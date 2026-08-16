"""
engine/scraper/connector_social.py
Public Conversation Analysis Engine — Social Media (Twitter/X) Connector

Uses the Tweepy v2 client to search Twitter/X for fashion-related tweets
matching configured keyword queries and hashtags.

Credentials required (set via environment variables or .env):
    TWITTER_BEARER_TOKEN — OAuth 2.0 Bearer Token from
                           https://developer.twitter.com/en/portal/dashboard
                           (Free or Basic tier both work for search)

Install: pip install tweepy

Config keys (from source_list.yaml → config):
    platform          : str       — currently only "twitter" supported
    search_queries    : list[str] — Twitter search query strings
    language          : str       — BCP-47 language code (default: "en")
    exclude_retweets  : bool      — append -is:retweet if True
    min_likes         : int       — minimum like count filter (0 = all)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from engine.scraper.base_connector import BaseConnector
from engine.config_loader import SourceConfig


class SocialConnector(BaseConnector):
    source_type = "social"

    def fetch(self) -> list[dict[str, Any]]:
        cfg = self.config.config
        platform = cfg.get("platform", "twitter")
        queries: list[str] = cfg.get("search_queries", [])
        language = cfg.get("language", "en")
        exclude_retweets = cfg.get("exclude_retweets", True)
        min_likes = int(cfg.get("min_likes", 0))

        if platform != "twitter":
            self.log.warning(
                "SocialConnector: platform '%s' is not yet supported. Only 'twitter' is implemented.",
                platform,
            )
            return []

        bearer_token = os.environ.get("TWITTER_BEARER_TOKEN", "")
        if not bearer_token:
            self.log.error(
                "TWITTER_BEARER_TOKEN environment variable not set. "
                "Get a token at https://developer.twitter.com/en/portal/dashboard"
            )
            return []

        try:
            import tweepy  # type: ignore[import]
        except ImportError:
            self.log.error("tweepy not installed. Run: pip install tweepy")
            return []

        client = tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)

        # Compute lookback start time
        start_time = datetime.now(timezone.utc) - timedelta(days=self.config.lookback_days)

        results: list[dict[str, Any]] = []

        for query_str in queries:
            if len(results) >= self.config.volume_cap:
                break

            # Build full query
            full_query = query_str
            if f"lang:{language}" not in full_query:
                full_query += f" lang:{language}"
            if exclude_retweets and "-is:retweet" not in full_query:
                full_query += " -is:retweet"

            self.log.info("Twitter search: '%s'", full_query)

            try:
                response = client.search_recent_tweets(
                    query=full_query,
                    start_time=start_time,
                    max_results=min(100, self.config.volume_cap - len(results)),
                    tweet_fields=["created_at", "public_metrics", "author_id"],
                    expansions=["author_id"],
                )

                if not response.data:
                    continue

                for tweet in response.data:
                    metrics = tweet.public_metrics or {}
                    like_count = metrics.get("like_count", 0) or 0
                    if like_count < min_likes:
                        continue

                    results.append({
                        "id": str(tweet.id),
                        "text": tweet.text,
                        "author_id": str(tweet.author_id) if tweet.author_id else None,
                        "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                        "public_metrics": {
                            "like_count": metrics.get("like_count"),
                            "reply_count": metrics.get("reply_count"),
                            "retweet_count": metrics.get("retweet_count"),
                        },
                    })

            except Exception as exc:
                self.log.warning("Twitter search failed for query '%s': %s", query_str, exc)

            time.sleep(1.5)  # Twitter API rate limit: ~500k tweets/month on Basic

        self.log.info("Twitter: fetched %d tweets.", len(results))
        return self._cap(results)
