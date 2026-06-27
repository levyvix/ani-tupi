"""Playback service - orchestrates the full playback flow.

This service coordinates:
- Preparing playback context from search or history
- Getting episode URLs
- Syncing progress to AniList
- Episode navigation

All results are returned as immutable dataclasses.
All errors are handled gracefully - functions never raise exceptions.
"""

from dataclasses import dataclass
import logging

from models.models import Status
from services.anime.anilist_discovery_service import (
    discover_anilist_info,
)
from services.anilist_service import anilist_client
from services.history_service import load_history
from services.repository import rep
from utils.logging import get_logger

logger = get_logger(__name__)


logger = logging.getLogger(__name__)


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
    except Exception as e:
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
    except Exception as e:
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
            except Exception as e:
                logger.debug("Episode URL pattern error for %s ep %d: %s", anime_title, episode, e)

        # Check if this is an awaiting episode with a direct URL from incremental search
        from services.anime import anilist_integration
        from scrapers.plugins.animesdigital import AnimesDigital
        from threading import Event

        if hasattr(anilist_integration.anilist_anime_flow, "_awaiting_episode_urls"):
            awaiting_urls = anilist_integration.anilist_anime_flow._awaiting_episode_urls
            if anime_title in awaiting_urls and episode in awaiting_urls[anime_title]:
                # Use the direct episode URL from AnimesDigital homepage search
                episode_url = awaiting_urls[anime_title][episode]

                # Extract player URL from the AnimesDigital episode page
                try:
                    scraper = AnimesDigital()
                    container = []
                    event = Event()

                    # Call search_player_src to extract the video URL
                    scraper.search_player_src(episode_url, container, event)

                    if container:
                        player_url = container[0]
                        return EpisodePlaybackResult(
                            player_url=player_url,
                            source="animesdigital",
                            success=True,
                            error_message=None,
                        )
                    else:
                        # If we couldn't extract player from the direct URL, fall back to regular search
                        logger.debug(
                            f"Could not extract player from direct AnimesDigital URL for {anime_title} ep {episode}, trying regular search"
                        )
                except Exception as e:
                    logger.debug(
                        f"Error extracting player from AnimesDigital awaiting episode: {e}"
                    )
                    # Fall back to regular search
                    pass

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
    except Exception as e:
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
                from utils.anilist_discovery import clear_discovery_cache

                try:
                    clear_discovery_cache(anime_title)
                    logger.info(
                        "Cleared invalid cache mapping for '%s' (was ID %d)",
                        anime_title,
                        anilist_id,
                    )
                except Exception:
                    pass
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
    except Exception as e:
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

    except Exception as e:
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
            video_url = rep.search_player_from_page(page_url, source_name)
            if video_url:
                logger.debug("Got video URL from %s: %s...", source_name, video_url[:80])
                sources.append((video_url, source_name, page_url))
                seen_sources.add(source_name)
            else:
                logger.debug("search_player_from_page returned None for %s", source_name)
        except Exception as e:
            logger.debug("Exception extracting from %s: %s", source_name, e)
            continue

    return [(url, source, referrer) for url, source, referrer in sources if url and source]
