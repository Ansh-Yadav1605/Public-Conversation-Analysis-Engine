"""
engine/scraper/connector_youtube.py
Public Conversation Analysis Engine — YouTube Comments Connector

Uses the YouTube Data API v3 to:
1. Search for relevant fashion haul/review/try-on videos
2. Fetch top-level comments on each found video

Credentials required:
    YOUTUBE_API_KEY — from https://console.cloud.google.com/apis/credentials
                      Enable "YouTube Data API v3" on the project.

Install: pip install google-api-python-client

Config keys (from source_list.yaml → config):
    search_queries        : list[str] — YouTube search queries
    max_videos_per_query  : int       — number of videos to pull per query
    max_comments_per_video: int       — max comments to fetch per video
    language              : str       — video language relevance hint (default: "en")
    order                 : str       — "relevance" | "date" | "viewCount"
"""

from __future__ import annotations

import os
import time
from typing import Any

from engine.scraper.base_connector import BaseConnector
from engine.config_loader import SourceConfig


class YouTubeConnector(BaseConnector):
    source_type = "youtube"

    def _build_client(self):
        api_key = os.environ.get("YOUTUBE_API_KEY", "")
        if not api_key:
            raise ValueError(
                "YOUTUBE_API_KEY environment variable not set. "
                "Create one at https://console.cloud.google.com/apis/credentials"
            )
        try:
            from googleapiclient.discovery import build  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "google-api-python-client not installed. "
                "Run: pip install google-api-python-client"
            )
        return build("youtube", "v3", developerKey=api_key)

    def fetch(self) -> list[dict[str, Any]]:
        cfg = self.config.config
        queries: list[str] = cfg.get("search_queries", [])
        max_videos = int(cfg.get("max_videos_per_query", 5))
        max_comments = int(cfg.get("max_comments_per_video", 100))
        language = cfg.get("language", "en")
        order = cfg.get("order", "relevance")

        self.log.info(
            "Fetching YouTube comments: %d queries | max_videos=%d | max_comments=%d",
            len(queries), max_videos, max_comments,
        )

        try:
            youtube = self._build_client()
        except (ValueError, ImportError) as exc:
            self.log.error("YouTube connector setup failed: %s", exc)
            return []

        results: list[dict[str, Any]] = []
        seen_video_ids: set[str] = set()

        for query in queries:
            if len(results) >= self.config.volume_cap:
                break
            try:
                # Step 1: search for videos
                search_response = youtube.search().list(
                    q=query,
                    part="id,snippet",
                    type="video",
                    maxResults=max_videos,
                    relevanceLanguage=language,
                    order=order,
                ).execute()

                video_ids = [
                    item["id"]["videoId"]
                    for item in search_response.get("items", [])
                    if item["id"]["videoId"] not in seen_video_ids
                ]
                seen_video_ids.update(video_ids)
                self.log.debug("YouTube query '%s': found %d videos", query, len(video_ids))

                # Step 2: fetch comments for each video
                for video_id in video_ids:
                    if len(results) >= self.config.volume_cap:
                        break
                    try:
                        comments_response = youtube.commentThreads().list(
                            part="snippet",
                            videoId=video_id,
                            maxResults=min(max_comments, 100),
                            textFormat="plainText",
                            order="relevance",
                        ).execute()

                        for item in comments_response.get("items", []):
                            top = item["snippet"]["topLevelComment"]["snippet"]
                            results.append({
                                "comment_id": item["id"],
                                "video_id": video_id,
                                "text": top.get("textDisplay", ""),
                                "author_name": top.get("authorDisplayName"),
                                "published_at": top.get("publishedAt"),
                                "like_count": top.get("likeCount", 0),
                                "total_reply_count": item["snippet"].get("totalReplyCount", 0),
                            })

                        time.sleep(0.2)  # YouTube API: 10,000 units/day quota

                    except Exception as exc:
                        self.log.warning(
                            "YouTube comment fetch failed for video '%s': %s", video_id, exc
                        )

            except Exception as exc:
                self.log.warning("YouTube search failed for query '%s': %s", query, exc)

            time.sleep(0.5)

        # Apply lookback filter
        filtered = [
            r for r in results
            if self._is_within_lookback(r.get("published_at"))
        ]

        self.log.info("YouTube: fetched %d comments.", len(filtered))
        return self._cap(filtered)
