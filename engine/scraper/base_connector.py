"""
engine/scraper/base_connector.py
Public Conversation Analysis Engine — Base Connector Interface

All source connectors inherit from BaseConnector and implement fetch().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from engine.config_loader import SourceConfig
from engine.logger import get_logger


class BaseConnector(ABC):
    """
    Abstract base class for all source connectors.

    Subclasses must implement fetch() which returns a list of source-native
    raw dicts. The normalizer converts these to RawRecord objects.

    The connector is responsible for:
    - Reading config from the SourceConfig object
    - Respecting lookback_days and volume_cap
    - Handling rate limits and API errors gracefully (log and continue)
    - Returning an empty list on complete failure (never raising)
    """

    source_type: str = ""   # overridden by each subclass

    def __init__(self, source_config: SourceConfig) -> None:
        self.config = source_config
        self.log = get_logger(f"engine.scraper.{self.__class__.__name__}")

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """
        Fetch raw records from the source.

        Returns:
            list of source-native dicts (pre-normalization).
            Empty list if the source is unreachable or returns no data.
        """

    def _cap(self, items: list[Any]) -> list[Any]:
        """Trim to volume_cap."""
        cap = self.config.volume_cap
        if len(items) > cap:
            self.log.debug("Capping %d records to volume_cap=%d", len(items), cap)
            return items[:cap]
        return items

    def _is_within_lookback(self, date_str: str | None) -> bool:
        """
        Check whether a publish date falls within the configured lookback window.
        Returns True if date is None (no date available — include by default).
        """
        if not date_str:
            return True
        from datetime import datetime, timezone, timedelta
        try:
            # Try ISO-8601 UTC
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            pub = datetime.fromisoformat(date_str)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.lookback_days)
            return pub >= cutoff
        except Exception:
            return True   # unparseable date → include
