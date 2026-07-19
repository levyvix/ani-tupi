"""Player repository for managing video playback and plugin state."""

from collections import defaultdict
from typing import Any
from utils.cache import get_cache
from models.config import settings


class PlayerRepository:
    """Manages video player state and AniList ID mappings.

    Single responsibility: track plugin state for video resolution,
    maintain anime-to-AniList-ID mappings, and cache selected URLs.
    """

    _instance: "PlayerRepository | None" = None

    def __new__(cls):
        """Enforce singleton pattern."""
        if not cls._instance:
            cls._instance = super().__new__(cls)
            # Initialize attributes on the new instance
            cls._instance._plugins = {}
            cls._instance._anime_to_anilist_id = {}
            cls._instance._selected_urls = defaultdict(lambda: defaultdict(list))
        return cls._instance

    def register_plugin(self, plugin: Any) -> None:
        """Register a plugin for video playback.

        Args:
            plugin: Plugin instance with 'name' attribute and search_player_src method
        """
        self._plugins[plugin.name] = plugin

    def get_plugin(self, name: str) -> Any | None:
        """Get plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        return self._plugins.get(name)

    def get_active_sources(self) -> list[str]:
        """Get sorted list of registered plugin names.

        Returns:
            Sorted list of plugin names
        """
        return sorted(list(self._plugins.keys()))

    def set_anime_to_anilist_id(self, anime: str, anilist_id: int) -> None:
        """Map anime title to AniList ID.

        Args:
            anime: Anime title
            anilist_id: AniList numeric ID
        """
        self._anime_to_anilist_id[anime] = anilist_id

    def get_anime_anilist_id(self, anime: str) -> int | None:
        """Get AniList ID for anime title.

        Args:
            anime: Anime title

        Returns:
            AniList ID or None if not mapped
        """
        return self._anime_to_anilist_id.get(anime)

    def get_all_anime_ids(self) -> dict[str, int]:
        """Get all anime-to-AniList-ID mappings.

        Returns:
            Dictionary mapping anime titles to AniList IDs
        """
        return dict(self._anime_to_anilist_id)

    def set_selected_urls(self, anime: str, episode_num: int, urls: list[tuple[str, str]]) -> None:
        """Store selected URLs for an episode.

        Args:
            anime: Anime title
            episode_num: Episode number (1-indexed)
            urls: List of (url, source) tuples
        """
        self._selected_urls[anime][episode_num] = urls

    def get_selected_urls(self, anime: str, episode_num: int) -> list[tuple[str, str]]:
        """Get selected URLs for an episode.

        Args:
            anime: Anime title
            episode_num: Episode number (1-indexed)

        Returns:
            List of (url, source) tuples
        """
        return self._selected_urls[anime].get(episode_num, [])

    def clear_selected_urls(self, anime: str, episode_num: int) -> None:
        """Clear selected URLs for an episode.

        Args:
            anime: Anime title
            episode_num: Episode number (1-indexed)
        """
        if anime in self._selected_urls and episode_num in self._selected_urls[anime]:
            del self._selected_urls[anime][episode_num]

    def get_video_url(self, anime: str, episode_num: int) -> str | None:
        """Get cached video URL for an episode.

        Args:
            anime: Anime title
            episode_num: Episode number (1-indexed)

        Returns:
            Cached video URL or None if not found/expired
        """
        cache = get_cache()
        anilist_id = self.get_anime_anilist_id(anime)
        # Use AniList ID as cache key if available for better stability
        key_base = str(anilist_id) if anilist_id else anime.lower()
        cache_key = f"video:{key_base}:ep:{episode_num}"
        return cache.get(cache_key)

    def set_video_url(self, anime: str, episode_num: int, video_url: str) -> None:
        """Cache video URL for an episode with TTL.

        Args:
            anime: Anime title
            episode_num: Episode number (1-indexed)
            video_url: Video player URL to cache
        """
        cache = get_cache()
        anilist_id = self.get_anime_anilist_id(anime)
        key_base = str(anilist_id) if anilist_id else anime.lower()
        cache_key = f"video:{key_base}:ep:{episode_num}"

        ttl = settings.performance.video_url_cache_ttl_seconds
        cache.set(cache_key, video_url, ttl=ttl)

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset singleton instance for testing.

        Use only in test fixtures.
        """
        cls._instance = None
