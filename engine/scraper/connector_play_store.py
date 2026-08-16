"""
engine/scraper/connector_play_store.py
Public Conversation Analysis Engine — Google Play Store Connector

Uses the `google-play-scraper` library to fetch reviews for a given
Android app (Myntra, AJIO) from the Google Play Store.

Credentials required: None (public data).
Install: pip install google-play-scraper

Config keys (from source_list.yaml → config):
    app_id       : str  — Android package name (e.g. "com.myntra.android")
    country      : str  — ISO country code (default: "in")
    language     : str  — language code (default: "en")
    rating_filter: list[int] | null — star ratings to include, null = all
"""

from __future__ import annotations

import time
from typing import Any

from engine.scraper.base_connector import BaseConnector
from engine.config_loader import SourceConfig


class PlayStoreConnector(BaseConnector):
    source_type = "play_store"

    def fetch(self) -> list[dict[str, Any]]:
        cfg = self.config.config
        app_id = cfg.get("app_id", "")
        country = cfg.get("country", "in")
        language = cfg.get("language", "en")
        rating_filter = cfg.get("rating_filter")

        self.log.info(
            "Fetching Play Store reviews: app_id='%s' country=%s lang=%s",
            app_id, country, language,
        )

        try:
            from google_play_scraper import reviews, Sort  # type: ignore[import]
        except ImportError:
            self.log.error(
                "google-play-scraper not installed. Run: pip install google-play-scraper"
            )
            return []

        all_reviews: list[dict[str, Any]] = []
        continuation_token = None
        batch_size = min(200, self.config.volume_cap)

        try:
            while len(all_reviews) < self.config.volume_cap:
                result, continuation_token = reviews(
                    app_id,
                    lang=language,
                    country=country,
                    sort=Sort.NEWEST,
                    count=batch_size,
                    continuation_token=continuation_token,
                )
                if not result:
                    break
                all_reviews.extend(result)
                if continuation_token is None:
                    break
                time.sleep(0.5)   # polite delay between pagination calls
        except Exception as exc:
            self.log.error("Play Store fetch failed for '%s': %s", app_id, exc)
            return []

        results: list[dict[str, Any]] = []
        for rev in all_reviews:
            rev = dict(rev)
            rev["appId"] = app_id

            if rating_filter is not None:
                if rev.get("score") not in rating_filter:
                    continue

            pub = rev.get("at")
            if hasattr(pub, "isoformat"):
                pub_str = pub.isoformat()
            else:
                pub_str = str(pub) if pub else None
            if not self._is_within_lookback(pub_str):
                continue

            results.append(rev)

        self.log.info("Play Store '%s': fetched %d reviews.", app_id, len(results))
        return self._cap(results)
