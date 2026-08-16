"""
engine/scraper/connector_reddit.py
Public Conversation Analysis Engine — Reddit Connector

Uses PRAW (Python Reddit API Wrapper) to search subreddits for relevant
posts and their top comments.

Credentials required (set via environment variables or .env file):
    REDDIT_CLIENT_ID     — from https://www.reddit.com/prefs/apps
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT    — e.g. "engine:v0.1 (by /u/yourusername)"

Install: pip install praw

Config keys (from source_list.yaml → config):
    subreddit            : str       — subreddit name without r/
    search_keywords      : list[str] — search query strings
    sort                 : str       — "top" | "hot" | "new" | "relevance"
    post_type            : str       — "link+self" | "self" | "link"
    include_comments     : bool      — whether to fetch top comments per post
    max_comments_per_post: int       — max comment depth per post
"""

from __future__ import annotations

import os
import time
from typing import Any

from engine.scraper.base_connector import BaseConnector
from engine.config_loader import SourceConfig


class RedditConnector(BaseConnector):
    source_type = "reddit"

    def _build_reddit(self):
        """Initialize PRAW Reddit instance from environment variables."""
        try:
            import praw  # type: ignore[import]
        except ImportError:
            raise ImportError("praw not installed. Run: pip install praw")

        client_id = os.environ.get("REDDIT_CLIENT_ID", "")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
        user_agent = os.environ.get(
            "REDDIT_USER_AGENT",
            "engine:v0.1 (graduation-project-pm)"
        )

        if not client_id or not client_secret:
            raise ValueError(
                "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables "
                "must be set. Get credentials at https://www.reddit.com/prefs/apps"
            )

        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            read_only=True,
        )

    def fetch(self) -> list[dict[str, Any]]:
        cfg = self.config.config
        subreddit_name = cfg.get("subreddit", "")
        keywords = cfg.get("search_keywords", [])
        sort = cfg.get("sort", "top")
        include_comments = cfg.get("include_comments", True)
        max_comments = cfg.get("max_comments_per_post", 30)

        self.log.info(
            "Fetching Reddit: r/%s | %d keyword queries | sort=%s",
            subreddit_name, len(keywords), sort,
        )

        try:
            reddit = self._build_reddit()
        except (ImportError, ValueError) as exc:
            self.log.error("Reddit connector setup failed: %s", exc)
            return []

        results: list[dict[str, Any]] = []
        seen_post_ids: set[str] = set()

        for keyword in keywords:
            if len(results) >= self.config.volume_cap:
                break
            try:
                subreddit = reddit.subreddit(subreddit_name)
                posts = subreddit.search(
                    keyword,
                    sort=sort,
                    time_filter="year",
                    limit=min(50, self.config.volume_cap),
                )

                for post in posts:
                    if len(results) >= self.config.volume_cap:
                        break
                    if post.id in seen_post_ids:
                        continue
                    seen_post_ids.add(post.id)

                    # Apply lookback filter
                    from datetime import datetime, timezone
                    pub_str = datetime.utcfromtimestamp(
                        post.created_utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if not self._is_within_lookback(pub_str):
                        continue

                    # Add the post itself
                    results.append({
                        "id": post.id,
                        "record_kind": "post",
                        "title": post.title,
                        "selftext": post.selftext,
                        "url": post.url,
                        "permalink": post.permalink,
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_utc": post.created_utc,
                        "author": str(post.author) if post.author else None,
                        "subreddit": subreddit_name,
                    })

                    # Optionally add top comments
                    if include_comments and post.selftext != "[removed]":
                        try:
                            post.comments.replace_more(limit=0)
                            for comment in post.comments.list()[:max_comments]:
                                if not comment.body or comment.body in ("[deleted]", "[removed]"):
                                    continue
                                results.append({
                                    "id": f"{post.id}_{comment.id}",
                                    "record_kind": "comment",
                                    "body": comment.body,
                                    "url": f"https://www.reddit.com{post.permalink}",
                                    "permalink": post.permalink,
                                    "score": comment.score,
                                    "num_comments": None,
                                    "created_utc": comment.created_utc,
                                    "author": str(comment.author) if comment.author else None,
                                    "subreddit": subreddit_name,
                                })
                        except Exception:
                            pass  # comment fetch is best-effort

                time.sleep(1.0)  # respect Reddit API rate limits

            except Exception as exc:
                self.log.warning(
                    "Reddit search failed for keyword '%s' in r/%s: %s",
                    keyword, subreddit_name, exc,
                )
                continue

        self.log.info(
            "Reddit r/%s: fetched %d records (posts + comments).",
            subreddit_name, len(results),
        )
        return self._cap(results)
