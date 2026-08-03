"""AniList package - GraphQL transport plus the service layer built on it.

- ``client``: GraphQL transport, auth and anime/manga operations
- ``anilist_service``: discovery, scraper cache, progress sync and sequels
"""

from services.anilist.anilist_service import (
    AniListDiscoveryResult,
    auto_discover_anilist_id,
    clear_discovery_cache,
    discover_anilist_info,
    get_anilist_id_from_title,
    get_anilist_id_with_interactive_fallback,
    get_anilist_metadata,
    get_scraper_cache,
    offer_sequel_and_continue,
    set_scraper_cache,
    sync_anilist_progress,
)
from services.anilist.client import AniListClient, get_anilist_client

__all__ = [
    "AniListClient",
    "AniListDiscoveryResult",
    "auto_discover_anilist_id",
    "clear_discovery_cache",
    "discover_anilist_info",
    "get_anilist_client",
    "get_anilist_id_from_title",
    "get_anilist_id_with_interactive_fallback",
    "get_anilist_metadata",
    "get_scraper_cache",
    "offer_sequel_and_continue",
    "set_scraper_cache",
    "sync_anilist_progress",
]
