"""Cache system for scraper results (wrapper for backward compatibility).

DEPRECATED: This module is kept for backward compatibility only.
New code should use cache_manager.py instead.

Cache settings (location, duration) are configured in config.py
"""

from utils.cache_manager import (
    get_cache as _get_diskcache,
    clear_cache_all,
    clear_cache_by_prefix,
)
from utils.anilist_discovery import auto_discover_anilist_id


def get_cache(anime_title: str) -> dict | None:
    """Get cached scraper data for an anime (backward compatibility wrapper).

    Args:
        anime_title: Normalized anime title

    Returns:
        Dict with 'episode_urls' and 'episode_count' or None if not found

    """
    try:
        # Try to discover AniList ID for better cache lookup
        anilist_id = auto_discover_anilist_id(anime_title)

        if anilist_id:
            cache_key = f"episodes:{anilist_id}"
        else:
            cache_key = f"episodes:{anime_title}"

        # Get from new cache system
        cached_urls = _get_diskcache(cache_key)

        if cached_urls:
            return {
                "episode_urls": cached_urls,
                "episode_count": len(cached_urls),
                "timestamp": 0,  # Not used in new system
            }

        return None

    except Exception:
        return None


def set_cache(anime_title: str, episode_count: int, episode_urls: list[str]) -> None:
    """Save scraper results to cache (backward compatibility wrapper).

    Args:
        anime_title: Normalized anime title
        episode_count: Number of episodes found
        episode_urls: List of episode URLs

    """
    try:
        from utils.cache_manager import get_cache as dc
        from models.config import settings

        # Try to discover AniList ID for better cache key
        anilist_id = auto_discover_anilist_id(anime_title)

        if anilist_id:
            cache_key = f"episodes:{anilist_id}"
        else:
            cache_key = f"episodes:{anime_title}"

        # Save to new cache system
        dc().set(cache_key, episode_urls, expire=settings.cache.duration_hours * 3600)

    except Exception:
        pass  # Silent fail - cache is optional


def clear_cache(anime_title: str | None = None) -> None:
    """Clear cache for specific anime or all cache (backward compatibility wrapper).

    Args:
        anime_title: Anime to clear, or None to clear all

    """
    try:
        if anime_title is None:
            # Clear all cache
            clear_cache_all()
        else:
            # Try to discover AniList ID for precise clearing
            anilist_id = auto_discover_anilist_id(anime_title)

            if anilist_id:
                clear_cache_by_prefix(f":{anilist_id}:")
            else:
                clear_cache_by_prefix(f":{anime_title}:")

    except Exception:
        pass  # Silent fail
