"""Cache manager using diskcache with FanoutCache (SQLite backend).

Provides decorators for caching:
- Video URLs (biggest performance win: 7-15s → 100ms)
- Episode URLs
- Search results
- AniList metadata
"""

from typing import Optional

from diskcache import FanoutCache

from models.config import settings

# Cache global (FanoutCache = 4 shards SQLite for concurrency)
_cache = None


def get_cache() -> FanoutCache:
    """Lazy init of global cache."""
    global _cache
    if _cache is None:
        cache_dir = settings.cache.cache_dir
        _cache = FanoutCache(
            directory=str(cache_dir),
            shards=4,  # 4 SQLite files = less contention
            timeout=1.0,
        )
    return _cache


def default_ttl() -> int:
    """Default TTL in seconds."""
    return settings.cache.duration_hours * 3600


def cache_video_url(func):
    """Decorator to cache video URLs (m3u8/mp4 streaming).

    This is the BIGGEST performance win: 7-15 seconds → <100ms!
    """

    def wrapper(cache_key, episode: int, source: Optional[str] = None):
        """Wrapper that checks cache before calling expensive Selenium.

        Args:
            cache_key: anilist_id (int) or anime_title (str) fallback
            episode: Episode number
            source: Scraper source (animefire, animesonlinecc, etc)

        Returns:
            Video URL (m3u8 or mp4)
        """
        cache = get_cache()
        key = f"video:{cache_key}:{episode}:{source or 'any'}"

        # Check cache first
        cached = cache.get(key)
        if cached is not None:
            return cached

        # Cache miss - run expensive Selenium operation
        result = func(cache_key, episode, source)

        if result:
            # Save to cache
            cache.set(key, result, expire=default_ttl())

        return result

    return wrapper


def cache_episodes(func):
    """Decorator to cache episode URL lists."""

    def wrapper(cache_key):
        """Wrapper for episode list caching.

        Args:
            cache_key: anilist_id (int) or anime_title (str)

        Returns:
            Tuple of (episode_titles, episode_urls)
        """
        cache = get_cache()
        key = f"episodes:{cache_key}"

        cached = cache.get(key)
        if cached is not None:
            return cached

        # Cache miss - fetch from scrapers
        result = func(cache_key)

        if result:
            cache.set(key, result, expire=default_ttl())

        return result

    return wrapper


def cache_search_results(func):
    """Decorator to cache anime search results."""

    def wrapper(query: str):
        """Wrapper for search result caching.

        Args:
            query: Search query string

        Returns:
            Dict of {anime_title: [(url, source, params)]}
        """
        cache = get_cache()
        key = f"search:{query.lower()}"

        cached = cache.get(key)
        if cached is not None:
            return cached

        # Cache miss - search scrapers
        result = func(query)

        if result:
            cache.set(key, result, expire=default_ttl())

        return result

    return wrapper


def cache_anilist_metadata(func):
    """Decorator to cache AniList metadata (avoiding API calls)."""

    def wrapper(anilist_id: int):
        """Wrapper for AniList metadata caching.

        Args:
            anilist_id: AniList ID

        Returns:
            Dict with title, cover, description, score, etc
        """
        cache = get_cache()
        key = f"anilist_meta:{anilist_id}"

        cached = cache.get(key)
        if cached is not None:
            return cached

        # Cache miss - fetch from AniList API
        result = func(anilist_id)

        if result:
            cache.set(key, result, expire=2592000)  # 30 days for metadata

        return result

    return wrapper


def get_cached_video_url(cache_key, episode: int, source: Optional[str] = None) -> str | None:
    """Direct cache lookup for video URLs (without calling scraper)."""
    cache = get_cache()
    key = f"video:{cache_key}:{episode}:{source or 'any'}"
    return cache.get(key)


def save_video_url(cache_key, episode: int, source: str, url: str) -> None:
    """Manually save video URL to cache."""
    cache = get_cache()
    key = f"video:{cache_key}:{episode}:{source}"
    cache.set(key, url, expire=default_ttl())


def clear_cache_all() -> None:
    """Clear entire cache."""
    cache = get_cache()
    cache.clear()


def clear_cache_by_prefix(prefix: str) -> None:
    """Clear cache entries by prefix.

    Examples:
        clear_cache_by_prefix("video:123456:")  # Clear all videos for anilist_id
        clear_cache_by_prefix("episodes:123456:")  # Clear episodes
        clear_cache_by_prefix("search:")  # Clear all search results
    """
    cache = get_cache()
    keys_to_delete = []

    for key in cache.iterkeys():
        if key.startswith(prefix):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        cache.delete(key)


def get_cache_stats() -> dict:
    """Get cache statistics."""
    cache = get_cache()
    return {
        "size": len(cache),
        "total_items": sum(1 for _ in cache.iterkeys()),
    }
