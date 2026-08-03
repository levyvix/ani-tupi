"""Progress service - episode progress calculation logic.

This service extracts progress calculation logic from commands/anime.py
and provides immutable data types for episode progress information.

Key responsibilities:
- Calculate episode progress (current/total)
- Handle discrepancies between scraper and AniList episode counts
- Format progress strings for display
- Gracefully degrade when data is unavailable
"""

from dataclasses import dataclass

from services.anilist.anilist_service import AniListDiscoveryResult

__all__ = [
    "EpisodeProgressInfo",
    "ProgressContext",
    "calculate_watch_context",
    "get_episode_progress_info",
]


@dataclass(frozen=True)
class EpisodeProgressInfo:
    """Immutable episode progress information.

    Attributes:
        current_episode: The episode number being watched (1-indexed)
        scraper_total: Total episodes from scraper
        anilist_total: Total episodes from AniList (if available)
        progress_str: Pre-formatted progress string for display
    """

    current_episode: int
    scraper_total: int
    anilist_total: int | None
    progress_str: str


@dataclass(frozen=True)
class ProgressContext:
    """Immutable context for anime watching session.

    Attributes:
        anime_title: The anime title
        episode_number: Current episode number
        source: Scraper source name (if available)
        anilist_id: AniList ID (if discovered)
        num_episodes: Episode count from scraper
    """

    anime_title: str
    episode_number: int
    source: str | None
    anilist_id: int | None
    num_episodes: int


def get_episode_progress_info(
    episode_number: int,
    scraper_total: int,
    anilist_discovery: AniListDiscoveryResult | None,
) -> EpisodeProgressInfo:
    """Calculate episode progress information.

    This function determines the episode progress string by:
    1. Using scraper total as primary source
    2. Using AniList total as fallback when scraper total is unknown
    3. Showing both when there's a discrepancy
    4. Showing "?" when total is unknown from all sources

    Args:
        episode_number: Current episode number (1-indexed)
        scraper_total: Total episodes from scraper (0 = unknown)
        anilist_discovery: AniList discovery result (optional)

    Returns:
        EpisodeProgressInfo with calculated progress string
    """
    # Extract AniList total episodes if available
    anilist_total: int | None = None
    if anilist_discovery is not None and anilist_discovery.found:
        anilist_total = anilist_discovery.total_episodes

    # Calculate progress string
    progress_str = _format_progress_string(
        episode_number=episode_number,
        scraper_total=scraper_total,
        anilist_total=anilist_total,
    )

    return EpisodeProgressInfo(
        current_episode=episode_number,
        scraper_total=scraper_total,
        anilist_total=anilist_total,
        progress_str=progress_str,
    )


def _format_progress_string(
    episode_number: int,
    scraper_total: int,
    anilist_total: int | None,
) -> str:
    """Format progress string based on available episode counts.

    Rules:
    1. If scraper_total > 0 and matches anilist_total (or anilist_total is None):
       Use format "X/Y"
    2. If scraper_total > 0 and anilist_total differs:
       Use format "X/Y (AniList: Z)"
    3. If scraper_total == 0 (unknown) and anilist_total is available:
       Use anilist_total as fallback "X/Y"
    4. If both are unknown:
       Use format "X/?"

    Args:
        episode_number: Current episode number
        scraper_total: Total from scraper (0 = unknown)
        anilist_total: Total from AniList (None = unknown)

    Returns:
        Formatted progress string
    """
    # Case 1: Scraper total is known
    if scraper_total > 0:
        # Check for discrepancy with AniList
        if anilist_total is not None and anilist_total != scraper_total:
            return f"{episode_number}/{scraper_total} (AniList: {anilist_total})"
        return f"{episode_number}/{scraper_total}"

    # Case 2: Scraper total unknown, use AniList fallback
    if anilist_total is not None:
        return f"{episode_number}/{anilist_total}"

    # Case 3: Both unknown
    return f"{episode_number}/?"


def calculate_watch_context(
    anime_title: str,
    episode_number: int,
    source: str | None,
    anilist_id: int | None,
    num_episodes: int,
) -> ProgressContext:
    """Build a complete progress context for anime watching.

    This helper creates an immutable context object with all
    playback-related information for a watching session.

    Args:
        anime_title: The anime title
        episode_number: Current episode number
        source: Scraper source name (optional)
        anilist_id: AniList ID (optional)
        num_episodes: Episode count from scraper

    Returns:
        ProgressContext with all fields populated
    """
    return ProgressContext(
        anime_title=anime_title,
        episode_number=episode_number,
        source=source,
        anilist_id=anilist_id,
        num_episodes=num_episodes,
    )
