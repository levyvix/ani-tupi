"""Playback coordinator for video extraction and player search."""

import asyncio
from threading import Event
from collections import defaultdict

from models.config import settings
from utils.logging import get_logger

logger = get_logger(__name__)


def safe_plugin_call(plugin_func, url, container: list, event: Event) -> bool:
    """Safely call a plugin function and return success/failure status.

    Args:
        plugin_func: The plugin's search_player_src method
        url: The episode/page URL
        container: List to store the video URL (modified by plugin)
        event: Event for synchronization

    Returns:
        True if extraction succeeded, False otherwise
    """
    try:
        plugin_func(url, container, event)
        return bool(container)
    except Exception:
        return False


class PlaybackCoordinator:
    """Coordinator for playback-related operations.

    Handles:
    - Extracting video URLs from scraper plugins
    - Detecting source from URL
    - Managing playback caching
    """

    def __init__(self, sources: dict):
        """Initialize coordinator with available scraper sources.

        Args:
            sources: Dict of {source_name: plugin} pairs
        """
        self.sources = sources
        self.anime_to_anilist_id = {}  # For cache key optimization

    def _detect_source_from_url(self, url: str) -> str | None:
        """Detect which scraper source a URL belongs to based on domain.

        Args:
            url: The anime page URL

        Returns:
            Source name (e.g., "animefire") or None if not detected
        """
        url_lower = url.lower()

        # Map domain patterns to scraper sources
        domain_mappings = {
            "animefire": "animefire",
            "animesdigital": "animesdigital",
            "animesonline": "sushianimes",
            "goyabu": "goyabu",
        }

        # Check each domain pattern
        for domain_pattern, source_name in domain_mappings.items():
            if domain_pattern in url_lower:
                return source_name

        # If not detected by domain, return None
        return None

    def search_player(
        self, sources_with_urls: list[tuple], anime: str, episode_num: int
    ) -> str | None:
        """Search for video URLs with caching across multiple sources.

        Cache video URLs to speed up rewatching (7-15s → 100ms!)
        Respects configured priority order for source selection.

        Args:
            sources_with_urls: List of (url, source) tuples for the episode
            anime: Anime title
            episode_num: Episode number (1-indexed)

        Returns:
            Video URL or None if not found
        """
        # Defensive check: No sources have this episode available
        if not sources_with_urls:
            logger.info(f"   ❌ Episódio {episode_num} não disponível nas fontes ativas.")
            return None

        # Get anilist_id for cache key (if already discovered)
        anilist_id = self.anime_to_anilist_id.get(anime)

        # Use anilist_id if available, fallback to anime title
        cache_key = anilist_id if anilist_id else anime

        # CACHE CHECK: Try to get video URL from cache first
        try:
            from utils.cache_manager import get_cache as get_dc

            dc = get_dc()
            cache_key_full = f"video:{cache_key}:ep:{episode_num}"
            cached_url = dc.get(cache_key_full)
            if cached_url:
                logger.info(
                    f"   ℹ️  Usando vídeo em cache (válido por {settings.performance.video_url_cache_ttl_seconds // 60} min)"
                )
                return cached_url
        except Exception:
            dc = None
            cache_key_full = None

        # Cache miss - search all sources in parallel
        async def search_all_sources():
            nonlocal sources_with_urls, cache_key, dc, cache_key_full
            container = []

            # Show which sources are being tried
            sources_list = [source for _, source in sources_with_urls]
            if len(sources_list) > 1:
                logger.info(f"   🔄 Tentando fontes: {', '.join(sources_list)}")

            # Organize URLs by source following priority order
            priority_order = settings.plugins.priority_order
            priority_map = {name: idx for idx, name in enumerate(priority_order)}

            # Group URLs by source
            sources_urls = defaultdict(list)
            for url, source in sources_with_urls:
                sources_urls[source].append((url, source))

            # Sort sources by priority
            sorted_sources = sorted(
                sources_urls.keys(),
                key=lambda s: priority_map.get(s, len(priority_order)),
            )

            # Try sources in configured priority order (SEQUENTIALLY to respect priority)
            for source_name in sorted_sources:
                if container:
                    # Already found a video, stop searching
                    break

                source_urls = sources_urls[source_name]
                is_priority = priority_map.get(source_name, len(priority_order)) < len(
                    priority_order
                )

                # For each source, try each URL in sequence
                for url, source in source_urls:
                    if container:
                        # Already found a video, stop searching
                        break

                    try:
                        # Run each attempt in its own thread so a stalled source
                        # does not block later fallback attempts.
                        event = Event()
                        result_container = []

                        def run_plugin():
                            success = safe_plugin_call(
                                self.sources[source].search_player_src,
                                url,
                                result_container,
                                event,
                            )
                            if success:
                                video_url = result_container[0]
                                # Truncate very long URLs in display
                                display_url = (
                                    video_url[:80] + "..." if len(video_url) > 80 else video_url
                                )
                                logger.info(f"   ✅ Vídeo encontrado em: {source}")
                                logger.info(f"      URL: {display_url}")
                                container.extend(result_container)
                            else:
                                logger.info(f"   ❌ {source} falhou ao extrair vídeo")
                            return success

                        # Wait with timeout (longer for priority sources)
                        timeout = 15 if is_priority else 10
                        task = asyncio.to_thread(run_plugin)
                        await asyncio.wait_for(task, timeout=timeout)

                        # If we got here and container has content, we found a video
                        if container:
                            break

                    except asyncio.TimeoutError:
                        # This source timed out, try next
                        logger.info(f"   ⏱️  {source} timeout (> {timeout}s)")
                        continue
                    except Exception:
                        # This source failed, try next
                        continue

            # Get video URL if found, otherwise return None
            video_url = container[0] if container else None

            # CACHE SAVE: Save video URL to cache with TTL
            if video_url and dc and cache_key_full:
                try:
                    dc.set(
                        cache_key_full,
                        video_url,
                        ttl=settings.performance.video_url_cache_ttl_seconds,
                    )
                except Exception:
                    pass

            return video_url

        return asyncio.run(search_all_sources())

    def search_player_from_page(self, page_url: str, source_name: str) -> str | None:
        """Extract video URL from an episode page for a specific source.

        Args:
            page_url: URL of the episode page (e.g., https://animesdigital.org/video/a/134940/)
            source_name: Name of the source (e.g., "animesdigital")

        Returns:
            Video URL or None if extraction fails
        """
        if source_name not in self.sources:
            logger.warning(f"Source '{source_name}' not registered, cannot extract video")
            return None

        try:
            container = []
            event = Event()

            # Call the source's search_player_src to extract video URL from the page
            success = safe_plugin_call(
                self.sources[source_name].search_player_src,
                page_url,
                container,
                event,
            )

            if success and container:
                return container[0]
            if not success:
                logger.warning(f"No video URL extracted for {source_name}")
            return None
        except Exception as e:
            logger.warning(f"Exception extracting video from {source_name}: {e}")
            return None
