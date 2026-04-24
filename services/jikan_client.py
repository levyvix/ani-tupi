"""Shared Jikan/MAL client for anime title lookups."""

import logging

import httpx

from models.config import settings
from models.models import JikanAnimeEntry

logger = logging.getLogger(__name__)


class JikanClient:
    """Small Jikan client focused on anime title search."""

    def __init__(
        self,
        base_url: str = "https://api.jikan.moe/v4",
        timeout: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or settings.search.title_resolution_timeout_seconds

    def search_anime(self, query: str, limit: int = 5) -> list[JikanAnimeEntry]:
        """Search anime titles on Jikan and return parsed entries."""
        url = f"{self.base_url}/anime"
        params = {"q": query, "limit": limit}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.warning(f"Jikan API error: {e.response.status_code} for '{query}'")
            return []
        except httpx.TimeoutException:
            logger.warning(f"Jikan API timeout for '{query}'")
            return []
        except Exception as e:
            logger.warning(f"Jikan API request failed for '{query}': {e}")
            return []

        raw_items = data.get("data") or []
        results: list[JikanAnimeEntry] = []
        for item in raw_items:
            try:
                results.append(JikanAnimeEntry.model_validate(item))
            except Exception:
                continue
        return results


jikan_client = JikanClient()
