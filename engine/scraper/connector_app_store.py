"""
engine/scraper/connector_app_store.py
Public Conversation Analysis Engine — Apple App Store Connector

Uses the `app-store-scraper` library to fetch reviews for a given app
(Myntra, AJIO) from the Apple App Store India store.

Credentials required: None (public data).
Install: pip install app-store-scraper

Config keys (from source_list.yaml → config):
    app_id       : str  — Apple App Store numeric ID
    app_name     : str  — display name used in scraper
    country      : str  — ISO country code (default: "in")
    rating_filter: list[int] | null — star ratings to include, null = all
"""

from __future__ import annotations

import time
from typing import Any

from engine.scraper.base_connector import BaseConnector
from engine.config_loader import SourceConfig


class AppStoreConnector(BaseConnector):
    source_type = "app_store"

    def fetch(self) -> list[dict[str, Any]]:
        cfg = self.config.config
        app_id = cfg.get("app_id", "")
        app_name = cfg.get("app_name", "app")
        country = cfg.get("country", "in")
        rating_filter = cfg.get("rating_filter")   # None or list of ints

        self.log.info(
            "Fetching App Store reviews: app='%s' (id=%s) country=%s",
            app_name, app_id, country,
        )

        try:
            from app_store_scraper import AppStore  # type: ignore[import]
        except ImportError:
            self.log.error(
                "app-store-scraper not installed. Run: pip install app-store-scraper"
            )
            return []

        try:
            app = AppStore(country=country, app_name=app_name, app_id=app_id)
            app.review(how_many=self.config.volume_cap)
            raw_reviews: list[dict] = app.reviews or []
        except Exception as exc:
            self.log.error("App Store fetch failed for '%s': %s", app_name, exc)
            return []

        results: list[dict[str, Any]] = []
        for rev in raw_reviews:
            # Attach app_id for URL construction in normalizer
            rev = dict(rev)
            rev["appId"] = app_id

            # Apply rating filter if configured
            if rating_filter is not None:
                score = rev.get("rating", rev.get("score"))
                if score not in rating_filter:
                    continue

            # Apply lookback filter
            pub_date = str(rev.get("date", "")) or None
            if not self._is_within_lookback(pub_date):
                continue

            results.append(rev)

        self.log.info("App Store '%s': fetched %d reviews.", app_name, len(results))
        return self._cap(results)
