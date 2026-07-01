"""Episode repository for managing episode data and caching."""

import re
from collections import defaultdict
from threading import Lock, Thread

from models.config import settings
from models.models import EpisodeData
from services.priority_utils import sort_by_priority
from utils.logging import get_logger

logger = get_logger(__name__)


def parse_episode_number(title: str, fallback: int) -> int:
    """Normalize a scraper episode title to its episode number.

    Scrapers expose inconsistent labels ("Episódio 1", "Episodio - Legendado - 1",
    "Ep 1"). The episode number is the last integer in the label; if none is
    present, fall back to the positional index.

    Args:
        title: Raw episode label from a scraper
        fallback: Positional number to use when no digit is found (1-indexed)

    Returns:
        Episode number as int
    """
    numbers = re.findall(r"\d+", title)
    return int(numbers[-1]) if numbers else fallback


class EpisodeRepository:
    """Manages episode lists and episode state for anime.

    Single responsibility: track episode metadata, cache, and state management
    for all registered anime.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """Enforce singleton pattern."""
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize episode repository (only once)."""
        if EpisodeRepository._initialized:
            return

        self.sources = {}  # Will be injected when needed
        self.anime_episodes_numbers = defaultdict(list)
        self.anime_episodes_urls = defaultdict(list)
        self.anime_episodes_seasons = defaultdict(list)  # Season info for each episode
        self.last_search_failures = defaultdict(list)
        self._failure_lock = Lock()

        EpisodeRepository._initialized = True

    def set_sources(self, sources: dict) -> None:
        """Set available sources (scrapers). Called during initialization."""
        self.sources = sources

    def add_episode_list(
        self, anime: str, title_list: list[str], url_list: list[str], source: str, season: int = 1
    ) -> None:
        """Add episode list with validation.

        Episode labels are normalized to plain episode numbers (int) so that all
        sources expose a consistent list regardless of their labelling style.

        Args:
            anime: Anime title
            title_list: List of raw episode labels from the scraper
            url_list: List of episode URLs
            source: Plugin source name
            season: Season number (default: 1)

        Raises:
            ValueError: If title_list and url_list have different lengths.
        """
        # Normalize raw labels ("Episódio 1", "Episodio - Legendado - 1") to ints
        episode_numbers = [
            parse_episode_number(title, fallback=i + 1) for i, title in enumerate(title_list)
        ]

        # Validate using EpisodeData model
        episode_data = EpisodeData(
            anime_title=anime,
            episode_numbers=episode_numbers,
            episode_urls=url_list,
            source=source,
            season=season,
        )

        # Check if entry for (anime, source) already exists
        existing_index = None
        for i, (_, existing_source) in enumerate(self.anime_episodes_urls[anime]):
            if existing_source == source:
                existing_index = i
                break

        if existing_index is not None:
            # Replace existing entry
            self.anime_episodes_numbers[anime][existing_index] = episode_data.episode_numbers
            self.anime_episodes_urls[anime][existing_index] = (
                episode_data.episode_urls,
                source,
            )
            self.anime_episodes_seasons[anime][existing_index] = season
        else:
            # Add new entry
            self.anime_episodes_numbers[anime].append(episode_data.episode_numbers)
            self.anime_episodes_urls[anime].append((episode_data.episode_urls, source))
            self.anime_episodes_seasons[anime].append(season)

    def get_episode_list(self, anime: str, season: int | None = None) -> list[int]:
        """Get episode list for anime (returns longest list if multiple sources).

        Args:
            anime: Anime title
            season: Optional season number to filter by (default: None = all seasons)

        Returns:
            List of episode numbers from source with most episodes (optionally filtered by season)
        """
        episodes = self.anime_episodes_numbers[anime]
        if not episodes:
            return []

        # If season filter requested, find episodes matching that season
        if season is not None:
            seasons = self.anime_episodes_seasons[anime]
            # Find all sources with matching season and pick the longest
            matching_episodes = []
            for i, episode_list in enumerate(episodes):
                source_season = seasons[i] if i < len(seasons) else 1
                if source_season == season:
                    matching_episodes.append(episode_list)

            if not matching_episodes:
                return []  # No episodes for this season
            episode_list = sorted(matching_episodes, key=len)[-1]
            return episode_list
        else:
            # No season filter: return longest list, but drop obvious outliers
            # (e.g. mistaking global post IDs for sequential episode numbers).
            if len(episodes) == 1:
                return episodes[0]
            lengths = sorted(len(episode_list) for episode_list in episodes)
            second_largest = lengths[-2]
            largest = lengths[-1]
            outlier_threshold = max(second_largest * 3, second_largest + 50)
            pool = (
                [episode_list for episode_list in episodes if len(episode_list) < largest]
                if largest > outlier_threshold
                else episodes
            )
            episode_list = sorted(pool, key=lambda number_list: len(number_list))[-1]
            return episode_list

    def get_episode_url_and_source(self, anime: str, episode_num: int) -> tuple[str, str] | None:
        """Get episode URL and source name for a specific episode.

        Respects the priority order configured in settings.

        Args:
            anime: Anime title
            episode_num: Episode number (1-indexed)

        Returns:
            Tuple of (episode_url, source_name) or None if not found
        """
        # Validate episode_num
        if episode_num < 1:
            return None

        # Get available sources for this episode with their priorities
        available_sources = []
        for urls, source in self.anime_episodes_urls[anime]:
            if len(urls) >= episode_num:
                available_sources.append((urls[episode_num - 1], source))

        if not available_sources:
            return None

        # Get appropriate priority order based on anime type
        priority_order = settings.plugins.priority_order
        sorted_sources = sort_by_priority(available_sources, priority_order, source_index=1)

        # Return the highest priority source
        return sorted_sources[0] if sorted_sources else None

    def get_all_episode_sources(self, anime: str, episode_num: int) -> list[tuple[str, str]]:
        """Get all available sources for an episode, sorted by priority.

        Returns all (url, source) pairs for an episode, ordered by configured
        priority. Used for source fallback when playback fails.

        Args:
            anime: Anime title
            episode_num: Episode number (1-indexed)

        Returns:
            List of (url, source) tuples sorted by priority, or empty list if episode not found
        """
        if episode_num < 1:
            return []

        available_sources = []
        for urls, source in self.anime_episodes_urls[anime]:
            if len(urls) >= episode_num:
                available_sources.append((urls[episode_num - 1], source))

        if not available_sources:
            return []

        # Sort by priority order
        priority_order = settings.plugins.priority_order
        sorted_sources = sort_by_priority(available_sources, priority_order, source_index=1)

        return sorted_sources

    def save_episode_state(self, anime: str) -> dict:
        """Save the current episode state for an anime.

        Used by source switching to preserve episode data across searches.

        Args:
            anime: Anime title

        Returns:
            Dict with keys 'urls' and 'numbers' containing episode data
        """
        return {
            "urls": list(self.anime_episodes_urls[anime]),
            "numbers": list(self.anime_episodes_numbers[anime]),
        }

    def restore_episode_state(self, anime: str, state: dict) -> None:
        """Restore previously saved episode state for an anime.

        Used by source switching to restore episode data after search.

        Args:
            anime: Anime title
            state: Dict with 'urls' and 'numbers' keys
        """
        self.anime_episodes_urls[anime] = state["urls"]
        self.anime_episodes_numbers[anime] = state["numbers"]

    def load_from_cache(self, anime: str, cache_data) -> None:
        """Populate repository from cached data.

        Cache-first approach: When anime is found in cache, load its data
        directly into the repository without searching scrapers.

        Args:
            anime: Anime title
            cache_data: ScraperCacheData model or dict with keys 'episode_urls' and 'episode_count'
        """
        if not cache_data:
            return

        # Handle both Pydantic models and dicts
        if hasattr(cache_data, "episode_urls"):
            # It's a Pydantic model
            episode_urls = cache_data.episode_urls
        else:
            # It's a dict
            episode_urls = cache_data.get("episode_urls", [])

        if not episode_urls:
            return

        # Generate sequential episode numbers from URL count (1-indexed)
        episode_numbers = list(range(1, len(episode_urls) + 1))

        # Add to repository as if it came from a "cache" source
        self.anime_episodes_numbers[anime].append(episode_numbers)
        self.anime_episodes_urls[anime].append((episode_urls, "cache"))

        # Note: We don't add a "dummy" entry to anime_to_urls here because:
        # 1. It's not a real scraper source - just cached episode data
        # 2. It would appear as "[cached]" in user-facing source lists
        # 3. search_anime() is called later to discover real sources for display

    def get_next_available_episode(self, anime: str, from_episode: int) -> tuple[int, str] | None:
        """Get next available episode from a given episode number.

        Searches all sources for the next available episode after the given one,
        respecting the priority order configured in settings.

        Args:
            anime: Anime title
            from_episode: Episode number to search from (1-indexed)

        Returns:
            Tuple of (episode_number, url) or None if no more episodes
        """
        if from_episode < 1:
            from_episode = 1

        # Find available episodes after from_episode
        available_sources = []
        for urls, source in self.anime_episodes_urls.get(anime, []):
            # from_episode is 1-based (e.g., episode 5 → from_episode=5).
            # urls is 0-based, so the *next* episode lives at urls[from_episode]:
            #   episode 1 → urls[0], episode 2 → urls[1], …, next → urls[from_episode]
            # The boundary check (len(urls) > from_episode) confirms that index exists.
            if len(urls) > from_episode:
                available_sources.append((urls[from_episode], source))

        if not available_sources:
            return None

        # Get appropriate priority order based on anime type
        priority_order = settings.plugins.priority_order
        sorted_sources = sort_by_priority(available_sources, priority_order, source_index=1)

        # Return the highest priority source's next episode
        if sorted_sources:
            best_url = sorted_sources[0][0]
            return (from_episode + 1, best_url)

        return None

    def clear_episode_state(self, anime: str) -> None:
        """Clear episode state for a specific anime.

        Args:
            anime: Anime title
        """
        self.anime_episodes_numbers[anime] = []
        self.anime_episodes_urls[anime] = []
        self.anime_episodes_seasons[anime] = []
        self.last_search_failures[anime] = []

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset singleton instance for testing.

        Use only in test fixtures.
        """
        cls._instance = None

    def search_episodes(
        self, anime: str, anime_to_urls: dict, source_filter: str | None = None
    ) -> None:
        """Search for episodes from all sources or a specific source.

        Args:
            anime: Anime title to search episodes for
            anime_to_urls: Dict mapping anime titles to (url, source, params) tuples
            source_filter: Optional source name to search only that source (e.g., "animefire")
        """
        urls_and_scrapers = anime_to_urls.get(anime, [])
        self.last_search_failures[anime] = []

        # Filter by source if specified
        if source_filter:
            urls_and_scrapers = [
                (url, source, params)
                for url, source, params in urls_and_scrapers
                if source == source_filter
            ]

        # Build threads safely, avoiding potential race conditions
        threads = []
        for url, source, params in urls_and_scrapers:
            # Handle invalid source names (e.g., "animefire, animesdigital")
            actual_source = source

            # If source is not valid, try to detect from URL
            if actual_source not in self.sources:
                # Try comma-separated sources
                if "," in actual_source:
                    # Split and try the first valid one
                    for candidate_source in actual_source.split(","):
                        candidate_source = candidate_source.strip()
                        if candidate_source in self.sources:
                            actual_source = candidate_source
                            break

            # Only create thread if we have a valid source
            if actual_source in self.sources:

                def worker(
                    source_name: str = actual_source,
                    episode_url: str = url,
                    episode_params: dict | None = params,
                ) -> None:
                    try:
                        self.sources[source_name].search_episodes(
                            anime, episode_url, episode_params
                        )
                    except Exception as exc:
                        with self._failure_lock:
                            self.last_search_failures[anime].append((source_name, str(exc)))
                        logger.warning(
                            "Failed to load episodes for '%s' from source '%s': %s",
                            anime,
                            source_name,
                            exc,
                        )

                th = Thread(
                    target=worker,
                    name=f"search_episodes:{actual_source}:{anime}",
                    daemon=True,
                )
                threads.append(th)

        for th in threads:
            th.start()

        if not threads:
            return

        for th in threads:
            th.join()

    def get_last_search_failures(self, anime: str) -> list[tuple[str, str]]:
        """Return scraper failures from the most recent episode search for an anime."""
        return list(self.last_search_failures.get(anime, []))

    def get_available_seasons(self, anime: str) -> list[int]:
        """Get available season numbers for an anime (from longest episode list).

        Args:
            anime: Anime title

        Returns:
            Sorted list of available season numbers
        """
        # Get seasons from the longest episode list (most complete source)
        episodes_by_source = self.anime_episodes_seasons[anime]
        if not episodes_by_source:
            return [1]  # Default to season 1 if no info

        # Get the season from the source with most episodes
        episodes_numbers = self.anime_episodes_numbers[anime]
        longest_idx = max(range(len(episodes_numbers)), key=lambda i: len(episodes_numbers[i]))
        season = episodes_by_source[longest_idx] if longest_idx < len(episodes_by_source) else 1

        return [season]  # For now, return single season per source

    def get_episode_list_for_season(self, anime: str, season: int) -> list[int]:
        """Get episode list for a specific season.

        For now, since episodes are organized by source and each source
        returns one season, this returns the full episode list if season matches.

        Args:
            anime: Anime title
            season: Season number

        Returns:
            List of episode numbers for that season, or empty list if not found
        """
        # Get the longest episode list
        episodes = self.anime_episodes_numbers[anime]
        if not episodes:
            return []
        longest_idx = max(range(len(episodes)), key=lambda i: len(episodes[i]))
        longest_episodes = episodes[longest_idx]

        # Check if the season matches
        seasons = self.anime_episodes_seasons[anime]
        source_season = seasons[longest_idx] if longest_idx < len(seasons) else 1

        if source_season == season:
            return longest_episodes
        return []
