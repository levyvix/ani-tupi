"""Playback service - extraction, source fallback and the full playback flow.

This service coordinates:
- Extracting video URLs from the registered scrapers (``PlaybackCoordinator``)
- Falling back to the next source when MPV fails to play an episode
- Preparing playback context from search or history
- Getting episode URLs
- Syncing progress to AniList
- Episode navigation

All results are returned as immutable dataclasses.
All errors are handled gracefully - functions never raise exceptions.

Seções:
- Coordenação de extração
- Fallback de fonte
- Fluxo de reprodução
"""

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from threading import Event
from typing import Callable, NamedTuple

import httpx

from models.config import settings
from models.models import Status
from services.anilist.anilist_service import discover_anilist_info
from services.anilist.client import anilist_client
from services.core.history_service import load_history
from services.repository import rep
from utils.logging import get_logger
from utils.video_player import VideoPlayer, VideoPlaybackResult

__all__ = [
    # Coordenação de extração
    "PlaybackCoordinator",
    "safe_plugin_call",
    # Fallback de fonte
    "MPV_USER_ABORT_CODE",
    "PlaybackFallbackResult",
    "play_episode_with_fallback",
    "probe_url_playable",
    # Fluxo de reprodução
    "PlaybackContext",
    "EpisodePlaybackResult",
    "build_episode_sources",
    "get_episode_url_and_source",
    "navigate_episodes",
    "prepare_playback_from_history",
    "prepare_playback_from_search",
    "sync_progress_to_anilist",
]

logger = get_logger(__name__)


# === Coordenação de extração ===


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
            from utils.cache import get_cache as get_dc

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

                    except TimeoutError:
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

    def search_player_from_page(self, page_url: str, source_name: str) -> list[str]:
        """Extract candidate video URLs from an episode page for a specific source.

        Args:
            page_url: URL of the episode page (e.g., https://animesdigital.org/video/a/134940/)
            source_name: Name of the source (e.g., "animesdigital")

        Returns:
            Ordered list of candidate video URLs, or an empty list if extraction fails
        """
        if source_name not in self.sources:
            logger.warning(f"Source '{source_name}' not registered, cannot extract video")
            return []

        try:
            container = []
            event = Event()

            success = safe_plugin_call(
                self.sources[source_name].search_player_src,
                page_url,
                container,
                event,
            )

            if success and container:
                return list(container)
            if not success:
                logger.debug(f"No video URL extracted for {source_name}")
            return []
        except Exception as e:
            logger.warning(f"Exception extracting video from {source_name}: {e}")
            return []


# === Fallback de fonte ===


# Exit code 3 indicates user abort (Ctrl+C) - stop immediately, don't fallback
MPV_USER_ABORT_CODE = 3

# Statuses that mean the CDN definitively does not host this stream. Kept
# deliberately narrow: 403/405 are excluded because they usually signal a
# referrer/HEAD quirk on a stream MPV can still play.
_MISSING_STATUSES = frozenset({404, 410})


def probe_url_playable(url: str, referrer: str | None = None, timeout: float = 5.0) -> bool:
    """Check whether *url* is worth handing to MPV.

    Scrapers occasionally return a stale CDN path that answers 404, which costs a
    full MPV spawn to discover. A cheap HEAD skips those upfront.

    Fails open: anything other than an explicit 404/410 returns ``True``, so a
    transient network error or a HEAD-hostile CDN never skips a working source.

    Args:
        url: Candidate video URL.
        referrer: Referer header the player would send, if any.
        timeout: Per-request timeout in seconds.

    Returns:
        ``False`` only when the server explicitly reports the stream as missing.
    """
    from scrapers.plugins.utils import DEFAULT_HEADERS, http_head_with_fallback

    headers = dict(DEFAULT_HEADERS)
    if referrer:
        headers["Referer"] = referrer
    try:
        http_head_with_fallback(url, headers=headers, timeout=timeout, max_retries=1)
        return True
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in _MISSING_STATUSES:
            return False
        logger.debug(f"probe_url_playable: status {exc.response.status_code} for {url}")
        return True
    except Exception as exc:
        logger.debug(f"probe_url_playable: {exc!r} for {url}")
        return True


class PlaybackFallbackResult(NamedTuple):
    """Result from fallback-aware episode playback.

    Attributes:
        playback_result: The VideoPlaybackResult from the successful (or last) play attempt
        source_used: Name of the source that succeeded, or None if all failed
        sources_tried: List of (source_name, exit_code) for all attempted sources
        all_failed: True if every source returned a failure exit code
    """

    playback_result: VideoPlaybackResult
    source_used: str | None
    sources_tried: list[tuple[str, int]]
    all_failed: bool


def _normalize_candidate_urls(urls: str | list[str] | None) -> list[str]:
    """Normalize extractor output to a deduplicated URL list."""
    if not urls:
        return []
    if isinstance(urls, str):
        return [urls]
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def play_episode_with_fallback(
    player: VideoPlayer,
    sources: list[tuple[str, str] | tuple[str, str, str | None]],
    anime_title: str,
    episode_number: int,
    total_episodes: int,
    use_ipc: bool = True,
    debug: bool = False,
    anilist_id: int | None = None,
    anilist_episodes: int | None = None,
    extractor: Callable[[str, str], str | list[str] | None] | None = None,
    url_probe: Callable[[str, str | None], bool] | None = None,
) -> PlaybackFallbackResult:
    """Play episode using rank-major fallback until one attempt succeeds.

    Candidates are tried by quality rank across all sources: the best-quality
    URL (rank 0) of every source is attempted first, then the next-best (rank 1)
    of every source, and so on. This prefers high quality everywhere before
    falling back to lower-quality streams.

    An attempt fails when MPV returns a non-zero exit code that is NOT exit
    code 3 (user abort). Exit code 3 means the user intentionally cancelled —
    in that case we stop immediately.

    Args:
        player: VideoPlayer instance with session state (autoplay, etc.)
        sources: List of (url, source_name) or (url, source_name, referrer) tuples sorted by priority.
            When ``extractor`` is provided, the first tuple element is treated as a
            page URL and resolved to one or more playable video URLs lazily, on demand.
        anime_title: Anime title for display and IPC context
        episode_number: Current episode number (1-indexed)
        total_episodes: Total episodes in scraper
        use_ipc: Enable IPC socket for keybinding events
        debug: Skip actual playback (testing mode)
        anilist_id: AniList ID for progress sync
        anilist_episodes: Total episodes from AniList
        extractor: Optional ``(page_url, source_name) -> urls | None`` callback.
            May return a single URL or an ordered list of candidates to try with MPV
            before moving to the next source. When None, tuple elements are already
            extracted video URLs.
        url_probe: Optional ``(url, referrer) -> bool`` check run before spawning MPV.
            Returning False skips the candidate without counting it as an attempt.
            When None, every candidate goes straight to MPV.

    Returns:
        PlaybackFallbackResult with outcome details
    """
    if not sources:
        error_result = VideoPlaybackResult(exit_code=2, action="quit", data=None)
        return PlaybackFallbackResult(
            playback_result=error_result,
            source_used=None,
            sources_tried=[],
            all_failed=True,
        )

    sources_tried: list[tuple[str, int]] = []
    last_result = VideoPlaybackResult(exit_code=2, action="quit", data=None)

    # Lazily extract each source's candidate URLs the first time we reach it,
    # then cache so the rank-major loop below can revisit every source per rank.
    candidate_cache: dict[int, list[str]] = {}
    referrer_cache: dict[int, str | None] = {}

    def get_candidates(idx: int) -> list[str]:
        if idx in candidate_cache:
            return candidate_cache[idx]
        entry = sources[idx]
        first, source = entry[0], entry[1]
        if extractor is not None:
            try:
                candidates = _normalize_candidate_urls(extractor(first, source))
            except Exception as e:
                logger.debug(f"[{source}] erro ao extrair vídeo: {e!r}")
                candidates = []
            referrer_cache[idx] = entry[2] if len(entry) > 2 else first
        else:
            candidates = [first]
            referrer_cache[idx] = entry[2] if len(entry) > 2 else None
        if not candidates:
            logger.debug(f"[{source}] não retornou URL de vídeo, pulando")
        candidate_cache[idx] = candidates
        return candidates

    # Rank-major playback: try candidate #rank of every source before moving to
    # the next (lower-quality) rank. rank 0 = best quality across all sources.
    rank = 0
    while True:
        played_at_rank = False
        for idx in range(len(sources)):
            source = sources[idx][1]
            candidates = get_candidates(idx)
            if rank >= len(candidates):
                continue
            played_at_rank = True
            url = candidates[rank]

            if url_probe is not None and not url_probe(url, referrer_cache[idx]):
                logger.info(
                    f"   ⏭️  '{source}' (qualidade {rank + 1}) indisponível no servidor, pulando"
                )
                continue

            attempt_num = len(sources_tried) + 1
            if len(sources) > 1:
                logger.info(
                    f"   🎬 Tentativa {attempt_num}: {source} "
                    f"(qualidade {rank + 1}/{len(candidates)})"
                )

            logger.debug(f"[{source}] reproduzindo URL (rank {rank}): {url}")

            result = player.play_episode(
                url=url,
                anime_title=anime_title,
                episode_number=episode_number,
                total_episodes=total_episodes,
                source=source,
                use_ipc=use_ipc,
                debug=debug,
                anilist_id=anilist_id,
                anilist_episodes=anilist_episodes,
                referrer=referrer_cache[idx],
                candidates=[
                    (entry[0], entry[1], entry[2] if len(entry) > 2 else None) for entry in sources
                ],
                candidates_extractor=extractor,
            )
            last_result = result
            sources_tried.append((source, result.exit_code))

            if result.exit_code in (MPV_USER_ABORT_CODE, 0):
                return PlaybackFallbackResult(
                    playback_result=result,
                    source_used=source,
                    sources_tried=sources_tried,
                    all_failed=False,
                )

            logger.info(
                f"   ❌ '{source}' (qualidade {rank + 1}) falhou (código: {result.exit_code})"
            )

        if not played_at_rank:
            break
        rank += 1

    tried_names = list(dict.fromkeys(s for s, _ in sources_tried))
    logger.info(f"\n❌ Nenhuma fonte funcionou para o episódio {episode_number}.")
    if tried_names:
        logger.info(f"   Fontes tentadas: {', '.join(tried_names)}")
    else:
        logger.info("   Nenhuma fonte tinha um vídeo disponível.")
    logger.info("   💡 Tente trocar de fonte manualmente ou verifique sua conexão.")

    return PlaybackFallbackResult(
        playback_result=last_result,
        source_used=None,
        sources_tried=sources_tried,
        all_failed=True,
    )


# === Fluxo de reprodução ===


# =============================================================================
# Immutable Data Types
# =============================================================================


@dataclass(frozen=True)
class PlaybackContext:
    """Immutable context for anime playback session.

    Attributes:
        anime_title: Selected anime title
        episode_idx: Current episode index (0-indexed)
        source: Video source/scraper name
        anilist_id: AniList ID if discovered
        anilist_title: Formatted AniList title if found
        total_episodes_anilist: Total episodes from AniList
        num_episodes: Total episodes from scraper
        episode_list: List of episode strings for menu display
    """

    anime_title: str
    episode_idx: int
    source: str | None
    anilist_id: int | None
    anilist_title: str | None
    total_episodes_anilist: int | None
    num_episodes: int
    episode_list: tuple[str, ...]


@dataclass(frozen=True)
class EpisodePlaybackResult:
    """Immutable result from episode video URL extraction.

    Attributes:
        player_url: Video URL for playback
        source: Source that provided the video
        success: Whether video URL was found
        error_message: Error message if failed
    """

    player_url: str | None
    source: str | None
    success: bool
    error_message: str | None


# =============================================================================
# Playback Preparation Functions
# =============================================================================


def prepare_playback_from_search(
    selected_anime: str,
    episode_idx: int,
    source: str | None,
) -> PlaybackContext | None:
    """Prepare playback context after anime search.

    This function:
    1. Discovers AniList information for the anime
    2. Gets episode list from repository
    3. Builds immutable PlaybackContext

    All errors are handled gracefully - the function never raises exceptions.

    Args:
        selected_anime: The anime title selected from search results
        episode_idx: The episode index to start from (0-indexed)
        source: The scraper source name

    Returns:
        PlaybackContext with all fields populated, or None on critical failure
    """
    # Try to discover AniList info
    anilist_id: int | None = None
    anilist_title: str | None = None
    total_episodes_anilist: int | None = None
    try:
        anilist_result = discover_anilist_info(selected_anime)
        if anilist_result.found:
            anilist_id = anilist_result.anilist_id
            anilist_title = anilist_result.anilist_title
            total_episodes_anilist = anilist_result.total_episodes
    except (httpx.TimeoutException, httpx.ConnectError, json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to discover AniList info for '%s': %s", selected_anime, e)
        # Continue without AniList info

    # Get episode list from repository
    episode_list_raw = rep.get_episode_list(selected_anime)
    episode_list = tuple(episode_list_raw) if episode_list_raw else ()
    num_episodes = len(episode_list)

    return PlaybackContext(
        anime_title=selected_anime,
        episode_idx=episode_idx,
        source=source,
        anilist_id=anilist_id,
        anilist_title=anilist_title,
        total_episodes_anilist=total_episodes_anilist,
        num_episodes=num_episodes,
        episode_list=episode_list,
    )


def prepare_playback_from_history() -> PlaybackContext | None:
    """Prepare playback context from continue watching history.

    This function:
    1. Loads history using history_service
    2. Discovers/enriches AniList information
    3. Gets episode list from repository
    4. Builds immutable PlaybackContext

    All errors are handled gracefully.

    Returns:
        PlaybackContext with all fields populated, or None if history load fails
    """
    # Load history
    history_result = load_history()
    if history_result is None:
        return None

    anime_title, episode_idx, anilist_id_from_history, anilist_title_from_history = history_result

    # Try to discover/enrich AniList info
    anilist_id: int | None = anilist_id_from_history
    anilist_title: str | None = anilist_title_from_history
    total_episodes_anilist: int | None = None
    try:
        anilist_result = discover_anilist_info(anime_title)
        if anilist_result.found:
            anilist_id = anilist_result.anilist_id
            anilist_title = anilist_result.anilist_title
            total_episodes_anilist = anilist_result.total_episodes
    except (httpx.TimeoutException, httpx.ConnectError, json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to discover AniList info for '%s': %s", anime_title, e)
        # Continue with info from history

    # Get episode list from repository
    episode_list_raw = rep.get_episode_list(anime_title)
    episode_list = tuple(episode_list_raw) if episode_list_raw else ()
    num_episodes = len(episode_list)

    return PlaybackContext(
        anime_title=anime_title,
        episode_idx=episode_idx,
        source=None,  # Source not stored in history
        anilist_id=anilist_id,
        anilist_title=anilist_title,
        total_episodes_anilist=total_episodes_anilist,
        num_episodes=num_episodes,
        episode_list=episode_list,
    )


# =============================================================================
# Episode URL Retrieval
# =============================================================================


def get_episode_url_and_source(
    anime_title: str,
    episode: int,
    current_player_url: str | None = None,
) -> EpisodePlaybackResult:
    """Get video URL for an episode.

    This function:
    1. If current_player_url is provided, tries to derive the episode URL via
       pattern substitution (fast HEAD request) before falling back to scraping
    2. Checks if this is an awaiting episode with direct URL from homepage search
    3. Uses repository to search for video URL (regular path)
    4. Handles errors gracefully
    5. Returns immutable result

    Args:
        anime_title: The anime title
        episode: The episode number (1-indexed)
        current_player_url: Currently playing URL; used to attempt URL pattern
            derivation before scraping (optional)

    Returns:
        EpisodePlaybackResult with video URL or error message
    """
    try:
        # Fast path: try URL pattern derivation when we have an existing player URL
        if current_player_url:
            try:
                from services.anime.episode_url_pattern import (
                    derive_episode_url,
                    detect_episode_pattern,
                    validate_episode_url,
                )

                if detect_episode_pattern(current_player_url):
                    logger.info(
                        f"[URL-PATTERN] Tentando derivar ep {episode} de: {current_player_url[:80]}"
                    )
                    derived_url = derive_episode_url(current_player_url, episode)
                    if derived_url and validate_episode_url(derived_url):
                        logger.debug(
                            "Episode URL pattern hit for %s ep %d: %s",
                            anime_title,
                            episode,
                            derived_url,
                        )
                        return EpisodePlaybackResult(
                            player_url=derived_url,
                            source="pattern",
                            success=True,
                            error_message=None,
                        )
                    else:
                        logger.debug(
                            "Episode URL pattern miss for %s ep %d, falling back to scraping",
                            anime_title,
                            episode,
                        )
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                json.JSONDecodeError,
                ValueError,
            ) as e:
                logger.debug("Episode URL pattern error for %s ep %d: %s", anime_title, episode, e)

        # Check if this is an awaiting episode with a direct URL from homepage search
        from services.anime.awaiting_episodes import registry as awaiting_registry

        episode_url = awaiting_registry.get(anime_title, episode)
        if episode_url:
            # Extract player URL from the AnimesDigital episode page via the
            # repository (no direct plugin import).
            try:
                candidates = rep.search_player_from_page(episode_url, "animesdigital")
                if candidates:
                    return EpisodePlaybackResult(
                        player_url=candidates[0],
                        source="animesdigital",
                        success=True,
                        error_message=None,
                    )
                # If we couldn't extract player from the direct URL, fall back to regular search
                logger.debug(
                    f"Could not extract player from direct AnimesDigital URL for {anime_title} ep {episode}, trying regular search"
                )
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                json.JSONDecodeError,
                ValueError,
            ) as e:
                logger.debug(f"Error extracting player from AnimesDigital awaiting episode: {e}")
                # Fall back to regular search

        # Regular path: Get episode URL and source info
        episode_info = rep.get_episode_url_and_source(anime_title, episode)
        source = episode_info[1] if episode_info else None

        # Search for video player URL
        player_url = rep.search_player(anime_title, episode)

        if player_url:
            return EpisodePlaybackResult(
                player_url=player_url,
                source=source,
                success=True,
                error_message=None,
            )
        else:
            return EpisodePlaybackResult(
                player_url=None,
                source=source,
                success=False,
                error_message="Nenhuma fonte conseguiu extrair o video.",
            )
    except (httpx.TimeoutException, httpx.ConnectError, json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to get episode URL for '%s' ep %d: %s", anime_title, episode, e)
        return EpisodePlaybackResult(
            player_url=None,
            source=None,
            success=False,
            error_message=f"Erro ao buscar video: {str(e)}",
        )


# =============================================================================
# AniList Progress Sync
# =============================================================================


def _validate_anilist_id(
    anilist_id: int,
    episode: int,
    anime_title: str | None = None,
) -> bool:
    """Validate AniList ID by checking anime exists.

    Args:
        anilist_id: The AniList media ID to validate
        episode: The episode number being synced
        anime_title: Original anime title (for cache cleanup if invalid)

    Returns:
        True if anime exists and is valid, False otherwise
    """
    try:
        anime_info = anilist_client.get_anime_by_id(anilist_id)
        if not anime_info:
            logger.warning(
                "AniList ID %d not found. Anime may not exist or ID is incorrect.",
                anilist_id,
            )
            # Clear the invalid cached mapping if provided
            if anime_title:
                from services.anilist.anilist_service import clear_discovery_cache

                try:
                    clear_discovery_cache(anime_title)
                    logger.info(
                        "Cleared invalid cache mapping for '%s' (was ID %d)",
                        anime_title,
                        anilist_id,
                    )
                except (OSError, IOError, ValueError) as exc:
                    logger.debug("Failed to clear discovery cache for '%s': %s", anime_title, exc)
            return False

        # Check if episode number is reasonable
        if anime_info.episodes and episode > anime_info.episodes:
            logger.warning(
                "Episode %d exceeds total episodes (%d) for anime_id=%d (%s). "
                "AniList ID may be incorrect.",
                episode,
                anime_info.episodes,
                anilist_id,
                anime_info.title.romaji,
            )
            return False

        return True
    except (httpx.TimeoutException, httpx.ConnectError, json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to validate anime_id=%d: %s", anilist_id, e)
        return False


def sync_progress_to_anilist(
    anilist_id: int | None,
    episode: int,
    num_episodes: int,
    anime_title: str | None = None,
) -> bool:
    """Sync episode progress to AniList.

    This function:
    1. Checks if AniList is authenticated and has valid ID
    2. Validates the AniList ID exists and episode number is valid
    3. Adds anime to list if not present
    4. Promotes status if needed (PLANNING -> CURRENT)
    5. Updates episode progress
    6. Marks as COMPLETED if last episode

    All errors are handled gracefully - function never raises exceptions.

    Args:
        anilist_id: The AniList media ID (None = no sync)
        episode: The episode number watched (1-indexed)
        num_episodes: Total number of episodes
        anime_title: Original anime title (for cache cleanup if ID is invalid)

    Returns:
        True if sync was successful, False otherwise
    """
    # Check if we have an AniList ID
    if anilist_id is None:
        logger.debug("No AniList ID provided, skipping sync")
        return False

    # Check if client is authenticated
    if not anilist_client.is_authenticated():
        logger.debug("AniList not authenticated, skipping sync")
        return False

    try:
        # Validate anilist_id is positive
        if not isinstance(anilist_id, int) or anilist_id <= 0:
            logger.error(
                "Invalid AniList ID: %r (must be positive integer)",
                anilist_id,
            )
            return False

        # Validate AniList ID exists and episode is valid
        if not _validate_anilist_id(anilist_id, episode, anime_title):
            logger.warning(
                "AniList ID validation failed for anime_id=%d ep=%d. "
                "Skipping sync - check that ID is correct.",
                anilist_id,
                episode,
            )
            return False

        logger.debug(
            "Syncing to AniList: anime_id=%d, episode=%d/%d",
            anilist_id,
            episode,
            num_episodes,
        )

        # Check if anime is in any list
        if not anilist_client.is_in_any_list(anilist_id):
            logger.info("Adding anime %d to AniList CURRENT list", anilist_id)
            anilist_client.add_to_list(anilist_id, Status.CURRENT.value)
        else:
            # Check current status and promote if needed
            entry = anilist_client.get_media_list_entry(anilist_id)
            if entry:
                if entry.status == "PLANNING":
                    logger.info("Promoting anime %d from PLANNING to CURRENT", anilist_id)
                    anilist_client.add_to_list(anilist_id, Status.CURRENT.value)

        # Update progress
        success = anilist_client.update_progress(anilist_id, episode)
        if not success:
            logger.warning(
                "Failed to update progress for anime_id=%d ep=%d. "
                "Check logs above for specific error.",
                anilist_id,
                episode,
            )
            return False

        # Fetch entry once for log and completion check
        entry = anilist_client.get_media_list_entry(anilist_id)
        if entry and entry.status == "COMPLETED":
            logger.info(
                "Anime anime_id=%d is already COMPLETED on AniList",
                anilist_id,
            )
            logger.info(f"✅ Anime já está marcado como COMPLETO no AniList (ID: {anilist_id})")
        else:
            logger.info(
                "✅ Successfully synced anime_id=%d progress to episode %d",
                anilist_id,
                episode,
            )
            logger.info(f"✅ Progresso sincronizado com AniList (ID: {anilist_id})")

        # Check if last episode - mark as completed
        if episode == num_episodes and num_episodes > 0:
            if entry and entry.status == "CURRENT":
                logger.info("Marking anime %d as COMPLETED", anilist_id)
                logger.info("✅ Anime marcado como COMPLETO no AniList")
                anilist_client.change_status(anilist_id, Status.COMPLETED)

        return True

    except (httpx.TimeoutException, httpx.ConnectError, json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to sync progress to AniList for anime %d: %s", anilist_id, e)
        return False


# =============================================================================
# Episode Navigation
# =============================================================================


def navigate_episodes(
    ctx: PlaybackContext,
    action: str,
    target_idx: int | None = None,
) -> PlaybackContext:
    """Navigate to a different episode.

    This function creates a new PlaybackContext with updated episode_idx.
    The original context is never modified (immutability).

    Args:
        ctx: Current playback context
        action: Navigation action - "next", "previous", "replay", "choose"
        target_idx: Target episode index for "choose" action (0-indexed)

    Returns:
        New PlaybackContext with updated episode_idx
    """
    new_idx = ctx.episode_idx

    if action == "next":
        # Go to next episode if not at the end
        if ctx.episode_idx < ctx.num_episodes - 1:
            new_idx = ctx.episode_idx + 1
    elif action == "previous":
        # Go to previous episode if not at the beginning
        if ctx.episode_idx > 0:
            new_idx = ctx.episode_idx - 1
    elif action == "replay":
        # Keep same episode
        new_idx = ctx.episode_idx
    elif action == "choose":
        # Jump to specific episode
        if target_idx is not None:
            # Clamp to valid range
            if target_idx < 0:
                new_idx = 0
            elif target_idx >= ctx.num_episodes:
                new_idx = max(0, ctx.num_episodes - 1)
            else:
                new_idx = target_idx
    # For unknown actions, keep current episode

    # Return new context with updated episode_idx
    return PlaybackContext(
        anime_title=ctx.anime_title,
        episode_idx=new_idx,
        source=ctx.source,
        anilist_id=ctx.anilist_id,
        anilist_title=ctx.anilist_title,
        total_episodes_anilist=ctx.total_episodes_anilist,
        num_episodes=ctx.num_episodes,
        episode_list=ctx.episode_list,
    )


def build_episode_sources(
    anime_title: str,
    episode: int,
    url_result: "EpisodePlaybackResult",
) -> list[tuple[str, str, str | None]]:
    """Build ordered playback sources for an episode.

    Keeps any direct/fast-path URL as the first candidate, but still collects
    all remaining repository-backed sources so playback fallback can continue
    when the first source fails.
    """
    sources: list[tuple[str, str, str | None]] = []
    seen_sources: set[str] = set()

    if url_result.success and url_result.player_url:
        direct_source = url_result.source or "unknown"
        sources.append((url_result.player_url, direct_source, None))
        seen_sources.add(direct_source)
        logger.debug(
            "Using direct URL from get_episode_url_and_source: %s...", url_result.player_url[:80]
        )
    else:
        logger.debug(
            "get_episode_url_and_source failed (success=%s), using fallback", url_result.success
        )

    page_sources = rep.get_all_episode_sources(anime_title, episode)
    logger.debug("Found %d page sources", len(page_sources))

    for page_url, source_name in page_sources:
        if source_name in seen_sources:
            logger.debug("Skipping duplicate source already queued: %s", source_name)
            continue

        logger.debug("Extracting video URL from %s page: %s...", source_name, page_url[:80])
        try:
            video_urls = rep.search_player_from_page(page_url, source_name)
            if video_urls:
                logger.debug(
                    "Got %d candidate URL(s) from %s (first: %s...)",
                    len(video_urls),
                    source_name,
                    video_urls[0][:80],
                )
                for video_url in video_urls:
                    sources.append((video_url, source_name, page_url))
                seen_sources.add(source_name)
            else:
                logger.debug("search_player_from_page returned no URLs for %s", source_name)
        except (httpx.TimeoutException, httpx.ConnectError, json.JSONDecodeError, ValueError) as e:
            logger.debug("Exception extracting from %s: %s", source_name, e)
            continue

    return [(url, source, referrer) for url, source, referrer in sources if url and source]
