"""AniList service package - transport, discovery, and progress sync.

This package consolidates the AniList domain into clear roles:
- client: GraphQL transport (auth + operations) via ``AniListClient``
- discovery: fuzzy matching of scraped titles to AniList IDs
- scraper_cache: AniList-aware episode cache adapters
"""

from .client import AniListClient

# Global singleton instance used across the codebase.
anilist_client = AniListClient()

# Discovery + scraper cache import ``anilist_client`` from this package, so
# they are imported after the singleton is defined to avoid a circular import
# at package init time. They are re-exported for the package surface.
from .discovery import (  # noqa: E402
    AniListDiscoveryResult,
    auto_discover_anilist_id,
    clear_discovery_cache,
    discover_anilist_info,
    get_anilist_id_from_title,
    get_anilist_id_with_interactive_fallback,
    get_anilist_metadata,
)
from .scraper_cache import get_scraper_cache, set_scraper_cache  # noqa: E402

__all__ = [
    "AniListClient",
    "anilist_client",
    "AniListDiscoveryResult",
    "auto_discover_anilist_id",
    "clear_discovery_cache",
    "discover_anilist_info",
    "get_anilist_id_from_title",
    "get_anilist_id_with_interactive_fallback",
    "get_anilist_metadata",
    "get_scraper_cache",
    "set_scraper_cache",
]
