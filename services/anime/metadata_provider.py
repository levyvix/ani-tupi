"""External anime metadata access, named by role rather than by vendor.

Exposes the ``AnimeMetadataProvider`` protocol and the concrete implementation
currently in use. Consumers depend on the protocol via ``get_metadata_provider``
so swapping the vendor only replaces the implementation class.
"""

from typing import Protocol, runtime_checkable
from urllib.parse import urlencode

import httpx

from scrapers.plugins.utils import http_get_with_retry
from models.config import settings
from models.models import AnimeMetadataEntry
from utils.logging import get_logger

__all__ = [
    "AnimeMetadataProvider",
    "JikanMetadataProvider",
    "TenraiMetadataProvider",
    "get_metadata_provider",
]

logger = get_logger(__name__)


@runtime_checkable
class AnimeMetadataProvider(Protocol):
    """Contract for searching external anime metadata by title."""

    def search_anime(self, query: str, limit: int = 5) -> list[AnimeMetadataEntry]:
        """Search anime by title and return validated domain entries.

        Never raises on provider failure — an unavailable provider returns an
        empty list so callers can fall back to other resolvers.
        """
        ...


# === Implementação concreta: Tenrai ===


class TenraiMetadataProvider:
    """``AnimeMetadataProvider`` backed by Tenrai's public catalogue API."""

    def __init__(
        self,
        base_url: str = "https://api.tenrai.org/v1",
        timeout: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or settings.search.title_resolution_timeout_seconds

    def search_anime(self, query: str, limit: int = 5) -> list[AnimeMetadataEntry]:
        """Search anime titles on the provider and return parsed entries."""
        url = f"{self.base_url}/anime"
        params = {"q": query, "limit": limit}
        full_url = f"{url}?{urlencode(params)}"

        try:
            response = http_get_with_retry(
                full_url,
                timeout=self.timeout,
                max_retries=1,
                backoff_base=0.25,
            )
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.warning(f"Tenrai API error: {e.response.status_code} for '{query}'")
            return []
        except httpx.TimeoutException:
            logger.warning(f"Tenrai API timeout for '{query}'")
            return []
        except Exception as e:
            logger.warning(f"Tenrai API request failed for '{query}': {e}")
            return []

        raw_items = data.get("data")
        if raw_items is None:
            logger.warning(f"Tenrai API resposta inesperada. Keys: {list(data.keys())}")
            return []
        results: list[AnimeMetadataEntry] = []
        for item in raw_items:
            try:
                results.append(AnimeMetadataEntry.model_validate(item))
            except Exception:
                continue
        return results


_provider: AnimeMetadataProvider = TenraiMetadataProvider()


def get_metadata_provider() -> AnimeMetadataProvider:
    """Return the configured anime metadata provider."""
    return _provider


# Backward-compatible import for callers that used the former provider name.
# The implementation now targets Tenrai; it never calls the retired Jikan API.
JikanMetadataProvider = TenraiMetadataProvider
