"""Tests for scraper cache round-trip via the unified cache system.

Verifies get_scraper_cache/set_scraper_cache preserve the ScraperCacheData
episode-caching behavior, using a real disk cache in a temporary directory
and mocking only the external AniList lookup.
"""

from utils import cache as cache_module
from utils.cache import DiskCache
from services.anilist.anilist_service import get_scraper_cache, set_scraper_cache


def test_scraper_cache_round_trip(temp_dir, monkeypatch):
    """set_scraper_cache then get_scraper_cache returns matching ScraperCacheData."""
    # Use a real disk cache in a temp directory as the global cache.
    disk_cache = DiskCache(cache_dir=temp_dir / "cache")
    monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

    # No AniList ID available -> key falls back to the anime title.
    monkeypatch.setattr(
        "services.anilist.anilist_service.get_anilist_id_from_title", lambda _title: None
    )
    monkeypatch.setattr(cache_module.settings.cache, "episodes_cache_enabled", True)

    episode_urls = ["http://example.com/ep1", "http://example.com/ep2"]
    set_scraper_cache("Some Anime", len(episode_urls), episode_urls)

    result = get_scraper_cache("Some Anime")

    assert result is not None
    assert result.episode_count == 2
    assert result.episode_urls == episode_urls


def test_scraper_cache_miss_returns_none(temp_dir, monkeypatch):
    """get_scraper_cache returns None when nothing is cached."""
    disk_cache = DiskCache(cache_dir=temp_dir / "cache")
    monkeypatch.setattr(cache_module, "_global_cache", disk_cache)
    monkeypatch.setattr(
        "services.anilist.anilist_service.get_anilist_id_from_title", lambda _title: None
    )
    monkeypatch.setattr(cache_module.settings.cache, "episodes_cache_enabled", True)

    assert get_scraper_cache("Unknown Anime") is None
