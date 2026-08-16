"""
engine/scraper/connector_review_qa.py
Public Conversation Analysis Engine — Myntra / AJIO Product Reviews & Q&A Connector

Scrapes on-platform product reviews and Q&A sections from Myntra and AJIO
using requests + BeautifulSoup. Both sites are heavily JavaScript-rendered,
so this connector uses their internal (semi-public) JSON API endpoints where
available, with HTML scraping as fallback.

Credentials required: None (public pages; requests imitate a browser).
Install: pip install requests beautifulsoup4 lxml

Config keys (from source_list.yaml → config):
    platform              : str       — "myntra" | "ajio"
    base_url              : str       — platform base URL
    category_urls         : list[str] — category page URLs to discover products
    products_per_category : int       — max products to sample per category
    reviews_per_product   : int       — max reviews to fetch per product
    include_qa            : bool      — whether to also fetch Q&A entries
    request_delay_seconds : float     — polite delay between HTTP requests

Notes:
    - Myntra exposes a JSON review API at:
        https://www.myntra.com/gateway/v2/reviews/{product_id}?pageNo=1&pageSize=50
    - AJIO product IDs are embedded in the product page URL path.
    - Both sites use dynamic JS rendering for product listing pages;
      this connector targets known API endpoints rather than scraping HTML listings.
    - If these APIs change, the connector degrades gracefully (logs warning, returns []).
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any

from engine.scraper.base_connector import BaseConnector
from engine.config_loader import SourceConfig


class ReviewQAConnector(BaseConnector):
    source_type = "review_qa"

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.myntra.com/",
    }

    def fetch(self) -> list[dict[str, Any]]:
        cfg = self.config.config
        platform = cfg.get("platform", "myntra").lower()
        category_urls: list[str] = cfg.get("category_urls", [])
        products_per_cat = int(cfg.get("products_per_category", 10))
        reviews_per_product = int(cfg.get("reviews_per_product", 50))
        include_qa = bool(cfg.get("include_qa", True))
        delay = float(cfg.get("request_delay_seconds", 3.0))

        self.log.info(
            "Fetching %s reviews: %d categories | %d products/cat | %d reviews/product",
            platform.upper(), len(category_urls), products_per_cat, reviews_per_product,
        )

        try:
            import requests
        except ImportError:
            self.log.error("requests not installed. Run: pip install requests")
            return []

        results: list[dict[str, Any]] = []
        session = requests.Session()
        session.headers.update(self._HEADERS)

        for cat_url in category_urls:
            if len(results) >= self.config.volume_cap:
                break

            product_ids = self._discover_product_ids(session, platform, cat_url, products_per_cat)
            self.log.debug(
                "%s: discovered %d product IDs from %s",
                platform, len(product_ids), cat_url,
            )

            for pid in product_ids:
                if len(results) >= self.config.volume_cap:
                    break

                reviews = self._fetch_reviews(session, platform, pid, reviews_per_product, delay)
                results.extend(reviews)

                if include_qa:
                    qa_items = self._fetch_qa(session, platform, pid, delay)
                    results.extend(qa_items)

                time.sleep(delay)

        self.log.info("%s: fetched %d review/QA records.", platform.upper(), len(results))
        return self._cap(results)

    # -------------------------------------------------------------------------
    # Product ID discovery
    # -------------------------------------------------------------------------

    def _discover_product_ids(
        self,
        session: Any,
        platform: str,
        category_url: str,
        limit: int,
    ) -> list[str]:
        """
        Extract product IDs from a category URL.
        Myntra: numeric IDs embedded in product URLs (e.g. /brand/t-shirt/1234567)
        AJIO:   product codes in URL path (e.g. /p/RF1234)
        """
        try:
            resp = session.get(category_url, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            self.log.warning("Product discovery failed for %s: %s", category_url, exc)
            return []

        if platform == "myntra":
            # Myntra product IDs are 7-8 digit numbers in href paths
            ids = re.findall(r'/buy/[^"]*?/(\d{7,8})', resp.text)
            if not ids:
                ids = re.findall(r'"productId"[:\s]+"?(\d+)"?', resp.text)
        elif platform == "ajio":
            # AJIO product codes start with RF, RI, etc. in URL paths
            ids = re.findall(r'["\'/]p/([A-Z]{2}\d{6,})', resp.text)
            if not ids:
                ids = re.findall(r'"code":"([A-Z]{2}\d{6,})"', resp.text)
        else:
            ids = []

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_ids: list[str] = []
        for pid in ids:
            if pid not in seen:
                seen.add(pid)
                unique_ids.append(pid)

        return unique_ids[:limit]

    # -------------------------------------------------------------------------
    # Review fetching
    # -------------------------------------------------------------------------

    def _fetch_reviews(
        self,
        session: Any,
        platform: str,
        product_id: str,
        limit: int,
        delay: float,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        if platform == "myntra":
            api_url = (
                f"https://www.myntra.com/gateway/v2/reviews/{product_id}"
                f"?pageNo=1&pageSize={min(limit, 50)}"
            )
            try:
                resp = session.get(api_url, timeout=10)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                review_list = (
                    data.get("response", {}).get("reviews", [])
                    or data.get("reviews", [])
                    or []
                )
                for rev in review_list[:limit]:
                    title = rev.get("title", "")
                    body = rev.get("reviewText", rev.get("body", ""))
                    text = f"{title}. {body}".strip(". ")
                    if not text:
                        continue
                    results.append({
                        "content_id": f"myntra_rev_{product_id}_{rev.get('reviewId', hashlib.sha256(text[:50].encode()).hexdigest()[:8])}",
                        "platform": "myntra",
                        "url": f"https://www.myntra.com/{product_id}",
                        "text": text,
                        "title": title,
                        "author": rev.get("userNickname", rev.get("nickname")),
                        "date_published": rev.get("submissionTime", rev.get("date")),
                        "rating": rev.get("rating"),
                        "helpful_count": rev.get("positiveFeedbackCount"),
                        "record_kind": "review",
                    })
            except Exception as exc:
                self.log.warning("Myntra review fetch failed for product %s: %s", product_id, exc)

        elif platform == "ajio":
            api_url = (
                f"https://www.ajio.com/api/p/{product_id}/reviews"
                f"?currentPage=0&pageSize={min(limit, 50)}"
            )
            try:
                resp = session.get(api_url, timeout=10)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                review_list = data.get("reviews", data.get("results", []))
                for rev in review_list[:limit]:
                    text = rev.get("comment", rev.get("reviewText", ""))
                    if not text:
                        continue
                    results.append({
                        "content_id": f"ajio_rev_{product_id}_{rev.get('id', hashlib.sha256(text[:50].encode()).hexdigest()[:8])}",
                        "platform": "ajio",
                        "url": f"https://www.ajio.com/p/{product_id}",
                        "text": text,
                        "author": rev.get("principal", {}).get("name") if isinstance(rev.get("principal"), dict) else rev.get("reviewer"),
                        "date_published": rev.get("date"),
                        "rating": rev.get("rating"),
                        "helpful_count": None,
                        "record_kind": "review",
                    })
            except Exception as exc:
                self.log.warning("AJIO review fetch failed for product %s: %s", product_id, exc)

        time.sleep(delay * 0.5)
        return results

    # -------------------------------------------------------------------------
    # Q&A fetching
    # -------------------------------------------------------------------------

    def _fetch_qa(
        self,
        session: Any,
        platform: str,
        product_id: str,
        delay: float,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        if platform == "myntra":
            api_url = f"https://www.myntra.com/gateway/v2/reviews/qa/{product_id}?pageNo=1&pageSize=20"
            try:
                resp = session.get(api_url, timeout=10)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                qa_list = data.get("response", {}).get("QAlist", data.get("QAlist", []))
                for qa in qa_list:
                    question = qa.get("question", "")
                    answers = qa.get("answers", [])
                    combined = question
                    if answers:
                        answer_texts = " | ".join(
                            a.get("text", a.get("answer", "")) for a in answers if a
                        )
                        combined = f"Q: {question} A: {answer_texts}"
                    if not combined.strip():
                        continue
                    results.append({
                        "content_id": f"myntra_qa_{product_id}_{hashlib.sha256(combined[:50].encode()).hexdigest()[:8]}",
                        "platform": "myntra",
                        "url": f"https://www.myntra.com/{product_id}",
                        "text": combined.strip(),
                        "author": None,
                        "date_published": None,
                        "rating": None,
                        "helpful_count": None,
                        "record_kind": "qa",
                    })
            except Exception as exc:
                self.log.warning("Myntra Q&A fetch failed for product %s: %s", product_id, exc)

        time.sleep(delay * 0.3)
        return results
