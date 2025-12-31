"""Cache system for scraper results to avoid unnecessary requests.

Cache settings (location, duration) are configured in config.py
"""

import json
import time

from config import settings


def get_cache(anime_title: str) -> dict | None:
    """Get cached scraper data for an anime.

    Args:
        anime_title: Normalized anime title

    Returns:
        Cached data dict or None if not found/expired

    """
    try:
        cache_file = settings.cache.cache_file
        if not cache_file.exists():
            return None

        with cache_file.open() as f:
            cache = json.load(f)

        if anime_title not in cache:
            return None

        data = cache[anime_title]
        timestamp = data.get("timestamp", 0)

        # Check if cache is still valid (duration in hours from config)
        cache_duration_seconds = settings.cache.duration_hours * 3600
        if time.time() - timestamp > cache_duration_seconds:
            return None  # Expired

        return data

    except Exception:
        return None


def set_cache(anime_title: str, episode_count: int, episode_urls: list[str]) -> None:
    """Save scraper results to cache.

    Args:
        anime_title: Normalized anime title
        episode_count: Number of episodes found
        episode_urls: List of episode URLs

    """
    try:
        cache_file = settings.cache.cache_file
        # Load existing cache
        cache = {}
        if cache_file.exists():
            with cache_file.open() as f:
                cache = json.load(f)

        # Update with new data
        cache[anime_title] = {
            "episode_count": episode_count,
            "episode_urls": episode_urls,
            "timestamp": time.time(),
        }

        # Save
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with cache_file.open("w") as f:
            json.dump(cache, f, indent=2)

    except Exception:
        pass  # Silent fail - cache is optional


def clear_cache(anime_title: str | None = None) -> None:
    """Clear cache for specific anime or all cache.

    Args:
        anime_title: Anime to clear, or None to clear all

    """
    try:
        cache_file = settings.cache.cache_file
        if anime_title is None:
            # Clear all cache
            if cache_file.exists():
                cache_file.unlink()
        else:
            # Clear specific anime
            if not cache_file.exists():
                return

            with cache_file.open() as f:
                cache = json.load(f)

            if anime_title in cache:
                del cache[anime_title]

                with cache_file.open("w") as f:
                    json.dump(cache, f, indent=2)

    except Exception:
        pass
