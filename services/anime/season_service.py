"""Season selection and filtering service.

Handles organizing episodes by season, filtering by season number,
and validating season data for multi-season anime.
"""

from models.models import EpisodeData

__all__ = [
    "count_episodes_in_season",
    "filter_episodes_by_season",
    "get_available_seasons",
    "organize_episodes_by_season",
    "validate_season_exists",
]


def organize_episodes_by_season(episodes: list[EpisodeData]) -> dict[int, list[EpisodeData]]:
    """Organize episodes into a dictionary keyed by season number.

    Args:
        episodes: List of episodes from scraper(s)

    Returns:
        Dictionary mapping season number to list of episodes in that season
    """
    organized: dict[int, list[EpisodeData]] = {}
    for episode in episodes:
        season = episode.season
        if season not in organized:
            organized[season] = []
        organized[season].append(episode)
    return organized


def get_available_seasons(episodes: list[EpisodeData]) -> list[int]:
    """Extract unique season numbers from episode list, sorted.

    Args:
        episodes: List of episodes from scraper(s)

    Returns:
        Sorted list of available season numbers
    """
    seasons = set(episode.season for episode in episodes)
    return sorted(seasons)


def filter_episodes_by_season(episodes: list[EpisodeData], season_number: int) -> list[EpisodeData]:
    """Filter episodes to return only those from a specific season.

    Args:
        episodes: List of episodes from scraper(s)
        season_number: Season number to filter by

    Returns:
        List of episodes from the specified season

    Raises:
        ValueError: If season_number is invalid or not found
    """
    if season_number < 1:
        raise ValueError(f"Season number must be positive, got: {season_number}")

    filtered = [ep for ep in episodes if ep.season == season_number]
    if not filtered:
        available = get_available_seasons(episodes)
        raise ValueError(f"Season {season_number} not found. Available seasons: {available}")
    return filtered


def validate_season_exists(episodes: list[EpisodeData], season_number: int) -> bool:
    """Check if a season number exists in the episode list.

    Args:
        episodes: List of episodes from scraper(s)
        season_number: Season number to validate

    Returns:
        True if season exists, False otherwise
    """
    return any(episode.season == season_number for episode in episodes)


def count_episodes_in_season(episodes: list[EpisodeData], season_number: int) -> int:
    """Count episodes in a specific season.

    Args:
        episodes: List of episodes from scraper(s)
        season_number: Season number

    Returns:
        Number of episodes in the season
    """
    return sum(1 for ep in episodes if ep.season == season_number)
