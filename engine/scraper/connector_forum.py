"""
engine/scraper/connector_forum.py
Public Conversation Analysis Engine — Fashion Forums / Communities Connector

Scrapes public forum and community pages using requests + BeautifulSoup.
Designed primarily for Quora topic pages and similar Q&A style communities.

Credentials required: None (public pages with polite crawl delays).
Install: pip install requests beautifulsoup4 lxml

Config keys (from source_list.yaml → config):
    base_url              : str  — base URL of the forum/site
    topic_urls            : list — specific topic/thread page URLs to scrape
    selector_config       : dict — CSS selectors for post container, text, date
    scrape_comments       : bool — whether to follow links to answer/comment threads
    request_delay_seconds : float — politeness delay between HTTP requests
"""

from __future__ import annotations

import hashlib
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from engine.scraper.base_connector import BaseConnector
from engine.config_loader import SourceConfig
from engine.logger import get_logger

log = get_logger(__name__)


class ForumConnector(BaseConnector):
    source_type = "forum"

    # Default CSS selectors — overridden by source-specific selector_config
    _DEFAULT_SELECTORS = {
        "post_container": "div.q-box",
        "text_field": "span.q-text",
        "date_field": "span[class*='time']",
    }

    # User-Agent header to identify the crawler politely
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ConversationAnalysisEngine/0.1; "
            "+https://github.com/graduation-project-pm)"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def fetch(self) -> list[dict[str, Any]]:
        cfg = self.config.config
        topic_urls: list[str] = cfg.get("topic_urls", [])
        selector_config: dict = cfg.get("selector_config", {})
        delay: float = float(cfg.get("request_delay_seconds", 2.0))

        selectors = {**self._DEFAULT_SELECTORS, **selector_config}

        self.log.info(
            "Fetching forum pages: %d URL(s) with delay=%.1fs",
            len(topic_urls), delay,
        )

        if not topic_urls:
            self.log.warning("No topic_urls configured for '%s' — skipping.", self.config.source_name)
            return []

        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            self.log.error("requests or beautifulsoup4 not installed.")
            return []

        results: list[dict[str, Any]] = []

        for url in topic_urls:
            if len(results) >= self.config.volume_cap:
                break
            try:
                resp = requests.get(url, headers=self._HEADERS, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                posts = soup.select(selectors["post_container"])
                if not posts:
                    # Fallback: extract all paragraph text if selectors don't match
                    posts = soup.find_all("p")
                    for p in posts:
                        text = p.get_text(separator=" ", strip=True)
                        if len(text) < 50:
                            continue
                        results.append(self._build_raw(url, text, None, None))
                else:
                    for post in posts:
                        text_el = post.select_one(selectors["text_field"]) or post
                        text = text_el.get_text(separator=" ", strip=True)
                        if len(text) < 30:
                            continue

                        date_el = post.select_one(selectors.get("date_field", ""))
                        date_str = date_el.get_text(strip=True) if date_el else None

                        results.append(self._build_raw(url, text, None, date_str))

                self.log.debug("Forum '%s': scraped %d entries from %s", self.config.source_name, len(results), url)

            except Exception as exc:
                self.log.warning("Forum scrape failed for '%s': %s", url, exc)

            time.sleep(delay)

        self.log.info(
            "Forum '%s': fetched %d records.", self.config.source_name, len(results)
        )
        return self._cap(results)

    @staticmethod
    def _build_raw(
        url: str,
        text: str,
        author: str | None,
        date_published: str | None,
    ) -> dict[str, Any]:
        content_id = hashlib.sha256((url + text[:100]).encode()).hexdigest()[:16]
        return {
            "content_id": content_id,
            "url": url,
            "text": text,
            "author": author,
            "date_published": date_published,
            "upvotes": None,
            "reply_count": None,
        }
