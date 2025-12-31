"""Cache system for scraper results to avoid unnecessary requests."""

import json
import time
from pathlib import Path

# Cache location
CACHE_FILE = (
    Path.home() / ".local/state/ani-tupi/scraper_cache.json"
    if __import__("os").name != "nt"
    else Path("C:\\Program Files\\ani-tupi\\scraper_cache.json")
)

# Cache duration: 6 hours
CACHE_DURATION = 6 * 60 * 60


def get_cache(anime_title: str) -> dict | None:
    """Get cached scraper data for an anime.

    Args:
        anime_title: Normalized anime title

    Returns:
        Cached data dict or None if not found/expired

    """
    try:
        if not CACHE_FILE.exists():
            return None

        with CACHE_FILE.open() as f:
            cache = json.load(f)

        if anime_title not in cache:
            return None

        data = cache[anime_title]
        timestamp = data.get("timestamp", 0)

        # Check if cache is still valid
        if time.time() - timestamp > CACHE_DURATION:
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
        # Load existing cache
        cache = {}
        if CACHE_FILE.exists():
            with CACHE_FILE.open() as f:
                cache = json.load(f)

        # Update with new data
        cache[anime_title] = {
            "episode_count": episode_count,
            "episode_urls": episode_urls,
            "timestamp": time.time(),
        }

        # Save
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open("w") as f:
            json.dump(cache, f, indent=2)

    except Exception:
        pass  # Silent fail - cache is optional


def clear_cache(anime_title: str | None = None) -> None:
    """Clear cache for specific anime or all cache.

    Args:
        anime_title: Anime to clear, or None to clear all

    """
    try:
        if anime_title is None:
            # Clear all cache
            if CACHE_FILE.exists():
                CACHE_FILE.unlink()
        else:
            # Clear specific anime
            if not CACHE_FILE.exists():
                return

            with CACHE_FILE.open() as f:
                cache = json.load(f)

            if anime_title in cache:
                del cache[anime_title]

                with CACHE_FILE.open("w") as f:
                    json.dump(cache, f, indent=2)

    except Exception:
        pass
