"""AniList-aware scraper cache adapters.

These adapters wrap the pure disk-cache primitives in ``utils.cache`` with
AniList discovery: when an AniList ID can be resolved for a title, episode
data is keyed by that stable ID instead of the raw (source-specific) title.

They live in the service layer (not ``utils``) because they depend on AniList
discovery, which is itself a service-layer concern.
"""

from models.config import settings
from models.models import ScraperCacheData
from utils.cache import get_cache

from services.anilist.discovery import get_anilist_id_from_title


def get_scraper_cache(anime_title: str):
    """Get cached scraper data for an anime.

    Args:
        anime_title: Normalized anime title

    Returns:
        ScraperCacheData with episode_urls and episode_count or None if not found
    """
    # Check if episodes cache is enabled
    if not settings.cache.episodes_cache_enabled:
        return None

    try:
        # Try to discover AniList ID for better cache lookup
        anilist_id = get_anilist_id_from_title(anime_title)

        if anilist_id:
            cache_key = f"episodes:{anilist_id}"
        else:
            cache_key = f"episodes:{anime_title}"

        # Get from unified cache system
        cache_obj = get_cache()
        cached_urls = cache_obj.get(cache_key)

        if cached_urls and isinstance(cached_urls, list):
            return ScraperCacheData(
                episode_urls=cached_urls,  # type: ignore[arg-type]  # unified cache returns Any
                episode_count=len(cached_urls),
                timestamp=0,  # Not used in new system
            )

        return None

    except Exception:
        return None


def set_scraper_cache(anime_title: str, episode_count: int, episode_urls: list[str]) -> None:
    """Save scraper results to cache.

    Args:
        anime_title: Normalized anime title
        episode_count: Number of episodes found
        episode_urls: List of episode URLs
    """
    # Check if episodes cache is enabled
    if not settings.cache.episodes_cache_enabled:
        return

    try:
        cache_obj = get_cache()

        # Try to discover AniList ID for better cache key
        anilist_id = get_anilist_id_from_title(anime_title)

        if anilist_id:
            cache_key = f"episodes:{anilist_id}"
        else:
            cache_key = f"episodes:{anime_title}"

        # Save to unified cache system
        cache_obj.set(cache_key, episode_urls, ttl=settings.performance.default_ttl_hours * 3600)

    except Exception:
        pass  # Silent fail - cache is optional
