"""Repository aggregator for anime search, episodes, and playback.

Coordinates between specialized repositories:
- SearchRepository: anime search and deduplication
- EpisodeRepository: episode management and source selection
- PlaybackCoordinator: video extraction from sources
"""

from services.search_repository import SearchRepository
from services.episode_repository import EpisodeRepository
from services.playback_coordinator import PlaybackCoordinator
from utils.logging import get_logger

logger = get_logger(__name__)


class Repository:
    """Central repository aggregating specialized data storage.

    Coordinates between SearchRepository, EpisodeRepository, and PlaybackCoordinator
    to provide unified interface for anime search, episode management, and playback.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if not Repository._instance:
            Repository._instance = super().__new__(cls)
            Repository._initialized = False
        return Repository._instance

    def __init__(self) -> None:
        # Only initialize once
        if Repository._initialized:
            return

        self._search_repo = SearchRepository()
        self._episode_repo = EpisodeRepository()
        self._playback_coordinator = None

        Repository._initialized = True

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset singleton instance for testing."""
        cls._instance = None
        cls._initialized = False
        SearchRepository.reset_singleton()
        EpisodeRepository.reset_singleton()

    # Registration & Sources
    def register(self, plugin) -> None:
        """Register a scraper plugin."""
        self._search_repo.register(plugin)
        self._episode_repo.set_sources(self._search_repo.sources)
        self.sources = self._search_repo.sources
        if self._playback_coordinator is None:
            self._playback_coordinator = PlaybackCoordinator(self.sources)

    def get_active_sources(self) -> list[str]:
        """Get list of currently registered plugin names."""
        return self._search_repo.get_active_sources()

    # Search Methods
    def clear_search_results(self) -> None:
        """Clear all search results."""
        self._search_repo.clear_search_results()

    def search_anime(self, query: str, verbose: bool = True):
        """Search for anime across all registered sources."""
        return self._search_repo.search_anime(query, verbose)

    def search_anime_with_word_limit(self, query: str, word_limit: int, verbose: bool = True):
        """Search anime with a word limit."""
        return self._search_repo.search_anime_with_word_limit(query, word_limit, verbose)

    def get_search_metadata(self):
        """Get metadata about the last search."""
        return self._search_repo.get_search_metadata()

    def add_anime(self, title: str, url: str, source: str, params=None) -> None:
        """Add anime with deduplication."""
        self._search_repo.add_anime(title, url, source, params)

    def get_anime_titles(
        self, filter_by_query: str | None = None, min_score: int | None = None
    ) -> list[str]:
        """Get anime titles."""
        return self._search_repo.get_anime_titles(filter_by_query, min_score)

    def get_anime_titles_with_sources(
        self,
        filter_by_query: str | None = None,
        original_query: str | None = None,
        anilist_results: list | None = None,
    ) -> list[str]:
        """Get anime titles with sources."""
        return self._search_repo.get_anime_titles_with_sources(
            filter_by_query, original_query, anilist_results
        )

    # Episode Methods
    def add_episode_list(
        self,
        anime: str,
        title_list: list[str],
        url_list: list[str],
        source: str,
        season: int = 1,
    ) -> None:
        """Add episode list.

        Args:
            anime: Anime title
            title_list: List of episode titles
            url_list: List of episode URLs
            source: Plugin source name
            season: Season number (default: 1, inferred from title if not specified)
        """
        # Infer season from anime title if not explicitly provided
        if season == 1:  # Only infer if default
            inferred_season = self._infer_season_from_title(anime)
            if inferred_season:
                season = inferred_season
        self._episode_repo.add_episode_list(anime, title_list, url_list, source, season)

    @staticmethod
    def _infer_season_from_title(title: str) -> int | None:
        """Infer season number from anime title.

        Detects patterns like:
        - "Season 2", "season 7", "temporada 12"
        - "2nd Season", "7º", "7ª"
        - Works for any season number 2-99

        Args:
            title: Anime title

        Returns:
            Inferred season number (2+) or None if season 1 (default)
        """
        import re

        title_lower = title.lower()

        # Patterns to detect season numbers
        # Ordered by specificity (most specific first)
        patterns = [
            # English patterns: "Season N", "season N", "Nth season"
            r"season\s+(\d+)",  # "Season 2", "season 7"
            r"(\d+)(?:st|nd|rd|th)\s+season",  # "2nd season", "7th season"
            r"season\s+(\d+)(?:st|nd|rd|th)",  # "season 2nd"
            # Portuguese patterns
            r"temporada\s+(\d+)",  # "temporada 2", "temporada 7"
            r"(\d+)º\s+temporada",  # "2º temporada", "7º temporada"
            r"(\d+)ª\s+temporada",  # "2ª temporada", "7ª temporada"
            r"temp\s+(\d+)",  # "temp 2"
            # Standalone number patterns (be careful not to match episode numbers)
            r"\s-\s(\d+)(?:\s|$|[^0-9])",  # " - 2 ", " - 7 "
            r"\|\s(\d+)(?:\s|$|[^0-9])",  # "| 2 ", "| 7 "
            # Number at the end of title (most lenient, checked last)
            # "Anime 2", "Anime 12", but NOT "Episode 100"
            # Accept 1-2 digits to cover seasons 2-99 but not huge episode numbers
            r"\s([2-9]|[1-9]\d)(?:\s|$)",  # 2-99 at end: "Anime 2 " or "Anime 12"
        ]

        # Try each pattern
        for pattern in patterns:
            match = re.search(pattern, title_lower)
            if match:
                season_num = int(match.group(1))
                # Return if season number is 2 or higher (skip if season 1)
                if season_num >= 2:
                    return season_num

        return None  # Default to season 1

    def get_episode_list(self, anime: str, season: int | None = None) -> list[int]:
        """Get episode list for anime, optionally filtered by season.

        Args:
            anime: Anime title
            season: Optional season number to filter by

        Returns:
            List of episode numbers
        """
        return self._episode_repo.get_episode_list(anime, season)

    def get_available_seasons(self, anime: str) -> list[int]:
        """Get available seasons for an anime.

        Args:
            anime: Anime title

        Returns:
            List of available season numbers
        """
        return self._episode_repo.get_available_seasons(anime)

    def get_episode_list_for_season(self, anime: str, season: int) -> list[int]:
        """Get episode list for a specific season.

        Args:
            anime: Anime title
            season: Season number

        Returns:
            List of episode numbers for that season
        """
        return self._episode_repo.get_episode_list_for_season(anime, season)

    def save_episode_state(self, anime: str) -> dict:
        """Save episode state."""
        return self._episode_repo.save_episode_state(anime)

    def restore_episode_state(self, anime: str, state: dict) -> None:
        """Restore episode state."""
        self._episode_repo.restore_episode_state(anime, state)

    def load_from_cache(self, anime: str, cache_data) -> None:
        """Load episodes from cache."""
        self._episode_repo.load_from_cache(anime, cache_data)

    def get_episode_url_and_source(self, anime: str, episode_num: int) -> tuple[str, str] | None:
        """Get episode URL and source."""
        return self._episode_repo.get_episode_url_and_source(anime, episode_num)

    def get_all_episode_sources(self, anime: str, episode_num: int) -> list[tuple[str, str]]:
        """Get all episode sources sorted by priority."""
        return self._episode_repo.get_all_episode_sources(anime, episode_num)

    def get_next_available_episode(self, anime: str, from_episode: int) -> tuple[int, str] | None:
        """Get next available episode."""
        return self._episode_repo.get_next_available_episode(anime, from_episode)

    def search_episodes(self, anime: str, source_filter: str | None = None) -> None:
        """Search for episodes."""
        self._episode_repo.search_episodes(anime, self._search_repo.anime_to_urls, source_filter)

    # Playback Methods
    def _detect_source_from_url(self, url: str) -> str | None:
        """Detect source from URL."""
        if self._playback_coordinator is None:
            self._playback_coordinator = PlaybackCoordinator(self._search_repo.sources)
        return self._playback_coordinator._detect_source_from_url(url)

    def search_player(self, anime: str, episode_num: int) -> str | None:
        """Search for video URL."""
        if self._playback_coordinator is None:
            self._playback_coordinator = PlaybackCoordinator(self._search_repo.sources)

        selected_urls = []
        for urls, source in self._episode_repo.anime_episodes_urls[anime]:
            if len(urls) >= episode_num and source != "cache":
                selected_urls.append((urls[episode_num - 1], source))

        return self._playback_coordinator.search_player(selected_urls, anime, episode_num)

    def search_player_from_page(self, page_url: str, source_name: str) -> list[str]:
        """Extract candidate video URLs from an episode page."""
        if self._playback_coordinator is None:
            self._playback_coordinator = PlaybackCoordinator(self._search_repo.sources)
        return self._playback_coordinator.search_player_from_page(page_url, source_name)

    # Data access (for backward compatibility)
    @property
    def anime_to_urls(self):
        """Search repo anime_to_urls."""
        return self._search_repo.anime_to_urls

    @property
    def anime_episodes_numbers(self):
        """Episode repo anime_episodes_numbers."""
        return self._episode_repo.anime_episodes_numbers

    @property
    def anime_episodes_urls(self):
        """Episode repo anime_episodes_urls."""
        return self._episode_repo.anime_episodes_urls

    @property
    def sources(self):
        """Registered sources."""
        return self._search_repo.sources

    @sources.setter
    def sources(self, value):
        """Set sources."""
        self._search_repo.sources = value
        self._episode_repo.sources = value

    @property
    def norm_titles(self):
        """Normalized titles."""
        return self._search_repo.norm_titles

    @property
    def anime_to_anilist_id(self):
        """Anime to AniList ID mapping."""
        if self._playback_coordinator is None and self._search_repo.sources:
            self._playback_coordinator = PlaybackCoordinator(self._search_repo.sources)
        if self._playback_coordinator:
            return self._playback_coordinator.anime_to_anilist_id
        return {}

    @anime_to_anilist_id.setter
    def anime_to_anilist_id(self, value):
        """Set anime to AniList ID mapping."""
        if self._playback_coordinator is None and self._search_repo.sources:
            self._playback_coordinator = PlaybackCoordinator(self._search_repo.sources)
        if self._playback_coordinator:
            self._playback_coordinator.anime_to_anilist_id = value

    # Legacy internal methods (kept for compatibility)
    def _build_search_results(self, query: str):
        """Build search results."""
        return self._search_repo._build_search_results(query)

    def _search_with_incremental_results(self, query: str, verbose: bool = True) -> None:
        """Search with incremental results."""
        self._search_repo._search_with_incremental_results(query, verbose)


# Global singleton instance
rep = Repository()
