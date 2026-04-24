"""Anime search flow with progressive search support.

Handles manual anime search with progressive word reduction,
cache integration, and scraper discovery.
"""

import time
from dataclasses import dataclass, field

from models.config import settings
from models.models import AnimeTitleResolution
from services.anime.title_resolution import AnimeTitleResolver
from services.repository import rep
from ui.components import loading, menu_navigate
from utils.scraper_cache import get_cache
from services.anime.title_normalization import normalize_anime_title
from utils.logging import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class ManualSearchSelection:
    """Result of manual anime search selection before episode loading."""

    selected_anime: str | None
    source: str | None
    was_cancelled: bool = False
    search_query_used: str | None = None

    @property
    def found(self) -> bool:
        return self.selected_anime is not None


def _filter_anime_results(titles: list[str], query: str) -> list[str]:
    """Filter anime titles by checking if all query words appear in title.

    This function filters a list of "Title [sources]" formatted strings
    by checking that all words in the query appear in the title (in any order).
    This allows finding "Season 2" when searching for "2" because "2" is
    contained in the title.

    Uses the same normalization logic as the repository to ensure
    consistent filtering behavior.

    Args:
        titles: List of anime titles in "Title [source1, source2]" format
        query: Query to filter by (e.g., "tate no yuusha no nariagari 2")

    Returns:
        Filtered list of titles where all normalized query words
        appear in the normalized title
    """
    from services.repository import Repository

    normalize_fn = Repository._normalize_for_filter

    query_normalized = normalize_fn(query)
    query_words = query_normalized.split()
    filtered = []

    for title in titles:
        # Extract base title (remove source indicators like "[source1, source2]")
        base_title = title.split(" [")[0] if " [" in title else title

        # Normalize title for comparison
        title_normalized = normalize_fn(base_title)
        title_words = title_normalized.split()

        # Check if ALL query words appear in title words
        # This is conjunctive (AND logic): all words must be present
        if all(word in title_words for word in query_words):
            filtered.append(title)

    return filtered


@dataclass
class SearchResultSet:
    """Represents a single search result set from an incremental search iteration.

    Tracks metadata about search results including word count, query used,
    and source distribution for UI display and navigation.
    """

    word_count: int
    query: str
    results: list[str]
    is_filtered: bool = False  # True if results were filtered from base search, not searched
    used_query: str | None = None  # Normalized query that was actually used for search
    timestamp: float = field(default_factory=time.time)
    source_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.word_count <= 0:
            raise ValueError(f"word_count must be positive, got {self.word_count}")
        # Default used_query to query if not provided
        if not self.used_query:
            self.used_query = self.query


class IncrementalSearchState:
    """Manages search history and navigation for incremental anime search.

    Tracks multiple search result sets as words are progressively added,
    allowing users to navigate backward/forward between result sets.

    Attributes:
        search_history: List of SearchResultSet objects in chronological order
        current_index: Current position in navigation history
        current_language: Language of the current search results ("romaji" or "english")
        current_title: The title used for current search (in current_language)
        alternative_title: Title in the alternative language (if available)
        alternative_language: The alternative language ("romaji" or "english")
    """

    def __init__(self):
        self.search_history: list[SearchResultSet] = []
        self.current_index: int = -1
        self.current_language: str = "romaji"
        self.current_title: str | None = None
        self.alternative_title: str | None = None
        self.alternative_language: str | None = None

    def add_result(
        self,
        word_count: int,
        query: str,
        results: list[str],
        source_counts: dict[str, int] | None = None,
        used_query: str | None = None,
        is_filtered: bool = False,
    ) -> None:
        """Add a new search result set to the history.

        Args:
            word_count: Number of words used in this search
            query: The actual query string used (e.g., "boku no hero")
            results: List of anime titles with sources
            source_counts: Optional dict of source names to result counts
            used_query: The normalized query that was actually used for search (lowercase, no punctuation)
            is_filtered: If True, results were filtered from base search, not searched from scrapers
        """
        result_set = SearchResultSet(
            word_count=word_count,
            query=query,
            results=results,
            is_filtered=is_filtered,
            used_query=used_query or query,
            source_counts=source_counts or {},
        )
        # If we've navigated backward, discard forward history
        if self.current_index < len(self.search_history) - 1:
            self.search_history = self.search_history[: self.current_index + 1]

        self.search_history.append(result_set)
        self.current_index = len(self.search_history) - 1

    def go_back(self) -> SearchResultSet | None:
        """Navigate to the previous search result set.

        Returns:
            The previous SearchResultSet, or None if already at the beginning
        """
        if self.current_index > 0:
            self.current_index -= 1
            return self.search_history[self.current_index]
        return None

    def go_forward(self) -> SearchResultSet | None:
        """Navigate to the next search result set.

        Returns:
            The next SearchResultSet, or None if already at the end
        """
        if self.current_index < len(self.search_history) - 1:
            self.current_index += 1
            return self.search_history[self.current_index]
        return None

    def get_current(self) -> SearchResultSet | None:
        """Get the current search result set.

        Returns:
            The current SearchResultSet, or None if no results
        """
        if 0 <= self.current_index < len(self.search_history):
            return self.search_history[self.current_index]
        return None

    def has_previous(self) -> bool:
        """Check if there is a previous result set to navigate to."""
        return self.current_index > 0

    def has_next(self) -> bool:
        """Check if there is a next result set to navigate to."""
        return self.current_index < len(self.search_history) - 1

    def clear(self) -> None:
        """Clear all search history."""
        self.search_history = []
        self.current_index = -1

    def can_toggle_language(self) -> bool:
        """Check if language toggle is available.

        Returns:
            True if alternative title exists and alternative language is different
        """
        return self.alternative_title is not None and self.alternative_language is not None

    def get_alternative_language(self) -> str | None:
        """Get the language we can switch to.

        Returns:
            The alternative language ("romaji" or "english"), or None if toggle not available
        """
        return self.alternative_language if self.can_toggle_language() else None

    def toggle_language(self) -> str:
        """Switch to the alternative language and update state.

        Returns:
            The new current language after toggle

        Raises:
            ValueError: If toggle is not available (alternative_title is None)
        """
        if not self.can_toggle_language():
            raise ValueError("Language toggle not available")

        # Swap languages, titles, and current_title
        old_language = self.current_language
        old_title = self.current_title

        self.current_language = self.alternative_language
        self.current_title = self.alternative_title
        self.alternative_language = old_language
        self.alternative_title = old_title

        return self.current_language

    def __repr__(self) -> str:
        current = self.get_current()
        current_str = (
            f"{current.word_count} words, {len(current.results)} results" if current else "none"
        )
        return f"IncrementalSearchState(current={current_str}, history_size={len(self.search_history)})"


def incremental_search_anime(
    query: str,
    english_title: str | None = None,
    romaji_title: str | None = None,
) -> tuple[IncrementalSearchState, list[str]]:
    """Perform incremental anime search starting with 1 word and adding progressively.

    Implements the filtering-based word addition strategy:
    1. Normalize query first (lowercase, remove season patterns, punctuation, etc)
    2. Start with first word of normalized query
    3. Execute initial search to get base results
    4. For each additional word: filter base results instead of re-searching
    5. Stop when results ≤ 5
    6. Fallback if zero results to previous iteration without re-searching

    Args:
        query: The user's search query (e.g., "Boku no Hero Academia Season 5")
        english_title: English title (for language toggle feature), optional
        romaji_title: Romaji title (for language toggle feature), optional

    Returns:
        Tuple of (IncrementalSearchState, final_results_list)
        - State tracks all search iterations for navigation
        - Results are the final anime titles with sources to display
    """
    state = IncrementalSearchState()

    # Initialize language tracking if both titles are provided
    if english_title and romaji_title and english_title != romaji_title:
        # Determine current language based on query
        query_lower = query.lower()
        english_lower = english_title.lower()

        # Check which title is closer to the query
        if english_lower in query_lower or query_lower == english_lower:
            # Query matches English title
            state.current_language = "english"
            state.current_title = english_title
            state.alternative_title = romaji_title
            state.alternative_language = "romaji"
        else:
            # Default to Romaji or if query matches Romaji
            state.current_language = "romaji"
            state.current_title = romaji_title
            state.alternative_title = english_title
            state.alternative_language = "english"

    # Normalize query first (remove season patterns, punctuation, convert to lowercase, etc)
    # normalize_anime_title() returns a list of variations from most specific to least
    # The first variation is the fully normalized query (most specific)
    variations = normalize_anime_title(query, is_english=False)
    if not variations:
        variations = [query.lower()]

    # Use the first (most specific) normalized variation for incremental search
    normalized_query = variations[0]
    words = normalized_query.split()

    # Determine starting word count (start with 1 word, add more if results > 5)
    start_word_count = 1
    current_word_count = start_word_count
    current_results: list[str] = []
    base_results: list[str] = []  # Store base search results for filtering

    # Progressive filtering: add words until results ≤ 5
    # After the initial base search, we filter results instead of re-searching scrapers
    while current_word_count <= len(words):
        # Build search query for this iteration
        partial_query = " ".join(words[:current_word_count])

        if current_word_count == start_word_count:
            # Initial search: execute scraper search (only happens once)
            # All subsequent iterations will filter this base result set
            rep.clear_search_results()
            try:
                with loading(f"Buscando '{partial_query}'..."):
                    rep.search_anime(partial_query, verbose=True)

                # Get results from this iteration
                search_metadata = rep.get_search_metadata()
                used_query = search_metadata.used_query or partial_query

                # Try to get AniList match for ranking
                ranking_query = used_query
                try:
                    from utils.anilist_discovery import auto_discover_anilist_id

                    anilist_results = auto_discover_anilist_id(used_query)
                    if anilist_results:
                        ranking_query = anilist_results[0].title
                except Exception:
                    pass

                # Get anime titles with sources, ranked by AniList if available
                titles_with_sources = rep.get_anime_titles_with_sources(
                    filter_by_query=used_query, original_query=ranking_query
                )

                # Store base results for filtering in subsequent iterations
                # These results are from the base N-word search and will be filtered, not re-searched
                base_results = titles_with_sources.copy()
                current_results = titles_with_sources

                # Count results from each source for metadata
                source_counts: dict[str, int] = {}
                for title_entry in titles_with_sources:
                    # Parse "Title [source]" format
                    if " [" in title_entry:
                        _, source = title_entry.rsplit(" [", 1)
                        source = source.rstrip("]")
                        source_counts[source] = source_counts.get(source, 0) + 1

                # Store results in state (with normalized used_query)
                state.add_result(
                    current_word_count,
                    partial_query,
                    titles_with_sources,
                    source_counts,
                    used_query=used_query,
                    is_filtered=False,
                )

                # Check stopping condition
                if len(current_results) <= 5:
                    # Good result set size - stop here
                    break

            except Exception as e:
                logger.warning(f"Error during incremental search at word {current_word_count}: {e}")
                # Fall back to previous results if available
                if state.has_previous():
                    state.go_back()
                    current_results = state.get_current().results
                    break
                raise

        else:
            # Subsequent iterations: filter base results instead of re-searching
            # This avoids unnecessary scraper calls and is much faster
            try:
                with loading(f"Filtrando '{partial_query}'..."):
                    # Filter the base results by the expanded query
                    # Uses substring matching on normalized titles (same as repository does)
                    filtered = _filter_anime_results(base_results, partial_query)

                # If filtered results are very few (<= 3), do a fresh search instead
                # This handles cases where API returns different results for different queries
                # (e.g., AnimesDigital returns more results for "re zero" than filtering "re" results)
                #
                # Re-search strategy:
                # - If query has 2+ words AND filtered results <= 3: ALWAYS re-search
                #   (2+ words = specific enough query to be worth re-searching all scrapers)
                # - This ensures we don't miss results from APIs that only match multi-word queries
                #   (e.g., AnimesDigital finds Re:Zero for "re zero" but not for "re")
                if filtered and len(filtered) <= 3 and current_word_count >= 2:
                    logger.debug(
                        f"Only {len(filtered)} filtered results for '{partial_query}', "
                        "performing fresh search instead"
                    )
                    # Clear and re-search with the full query
                    rep.clear_search_results()
                    with loading(f"Buscando '{partial_query}'..."):
                        rep.search_anime(partial_query, verbose=True)

                    # Get results from fresh search
                    search_metadata = rep.get_search_metadata()
                    used_query = search_metadata.used_query or partial_query

                    # Try to get AniList match for ranking
                    ranking_query = used_query
                    try:
                        from utils.anilist_discovery import auto_discover_anilist_id

                        anilist_results = auto_discover_anilist_id(used_query)
                        if anilist_results:
                            ranking_query = anilist_results[0].title
                    except Exception:
                        pass

                    # Get anime titles with sources, ranked by AniList if available
                    titles_with_sources = rep.get_anime_titles_with_sources(
                        filter_by_query=used_query, original_query=ranking_query
                    )

                    # Update base_results to include new search results for future filtering
                    base_results = titles_with_sources.copy()
                    current_results = titles_with_sources

                    # Count results from each source for metadata
                    source_counts: dict[str, int] = {}
                    for title_entry in titles_with_sources:
                        if " [" in title_entry:
                            _, source = title_entry.rsplit(" [", 1)
                            source = source.rstrip("]")
                            source_counts[source] = source_counts.get(source, 0) + 1

                    state.add_result(
                        current_word_count,
                        partial_query,
                        titles_with_sources,
                        source_counts,
                        used_query=used_query,
                        is_filtered=False,  # This was a fresh search, not a filter
                    )

                elif filtered:
                    # Filtered results found and enough (> 3) - use them
                    current_results = filtered

                    # Count results from each source for metadata
                    source_counts: dict[str, int] = {}
                    for title_entry in filtered:
                        # Parse "Title [source]" format
                        if " [" in title_entry:
                            _, source = title_entry.rsplit(" [", 1)
                            source = source.rstrip("]")
                            source_counts[source] = source_counts.get(source, 0) + 1

                    state.add_result(
                        current_word_count,
                        partial_query,
                        filtered,
                        source_counts,
                        used_query=partial_query,
                        is_filtered=True,
                    )
                else:
                    # Filtered to 0 results - fallback to previous iteration
                    # Important: we do NOT re-search when filtering fails
                    # Instead, we keep the previous result set
                    state.go_back()
                    current_results = state.get_current().results
                    current_word_count += 1
                    continue

            except Exception as e:
                logger.warning(f"Error during filtering at word {current_word_count}: {e}")
                # Fall back to previous results if available
                if state.has_previous():
                    state.go_back()
                    current_results = state.get_current().results
                    break
                raise

            # Check stopping condition
            if len(current_results) <= 5:
                # Good result set size - stop here
                break

        # Continue adding words
        current_word_count += 1

    # Handle zero results: revert to previous iteration if available
    if not current_results and state.has_previous():
        state.go_back()
        current_results = state.get_current().results

    return state, current_results


def _select_from_manual_search_results(query: str, args) -> ManualSearchSelection:
    """Run the manual incremental search UI for one query."""
    search_state, current_titles = incremental_search_anime(query)
    while True:
        current_result = search_state.get_current()
        used_query = current_result.used_query if current_result else query
        titles_with_sources = current_titles

        if not titles_with_sources:
            return ManualSearchSelection(
                selected_anime=None,
                source=None,
                was_cancelled=False,
                search_query_used=query,
            )

        filtered_titles = titles_with_sources
        if hasattr(args, "season") and args.season is not None:
            requested_season = args.season

            if requested_season > 1:
                filtered_titles = []
                for title in titles_with_sources:
                    base_title = title.split(" [")[0] if " [" in title else title
                    inferred_season = rep._infer_season_from_title(base_title)
                    inferred_season = inferred_season or 1

                    if inferred_season == requested_season:
                        filtered_titles.append(title)

                if not filtered_titles:
                    logger.warning(
                        f"⚠️  Nenhum resultado encontrado especificamente para a estação {requested_season}. "
                        f"Mostrando todos os resultados."
                    )
                    filtered_titles = titles_with_sources
                else:
                    logger.info(f"🎬 Filtrando resultados para estação {requested_season}")

        continue_button = "🔍 Continuar buscando (menos palavras)"
        if search_state.has_previous():
            titles_with_button = [continue_button] + filtered_titles
            word_count = current_result.word_count if current_result else len(used_query.split())
            show_continue_msg = f" (usando {word_count} palavras)"
        else:
            titles_with_button = filtered_titles
            show_continue_msg = ""

        selected_anime_with_source = menu_navigate(
            titles_with_button,
            msg=f"Escolha o Anime.{show_continue_msg}",
        )

        if not selected_anime_with_source:
            return ManualSearchSelection(
                selected_anime=None,
                source=None,
                was_cancelled=True,
                search_query_used=used_query,
            )

        if selected_anime_with_source == continue_button:
            previous = search_state.go_back()
            current_titles = previous.results if previous else current_titles
            continue

        selected_anime = selected_anime_with_source.split(" [")[0]
        source = None
        if " [" in selected_anime_with_source and selected_anime_with_source.endswith("]"):
            source = selected_anime_with_source.split(" [")[1].rstrip("]")

        return ManualSearchSelection(
            selected_anime=selected_anime,
            source=source,
            was_cancelled=False,
            search_query_used=used_query,
        )


def _resolve_search_query(query: str) -> AnimeTitleResolution | None:
    """Resolve a failed manual query into a more canonical title."""
    if not settings.search.enable_title_resolution:
        return None

    resolver = AnimeTitleResolver()
    resolution = resolver.resolve(query)
    if resolution and resolution.resolved_title.casefold() != query.strip().casefold():
        logger.info(
            "🔎 Tentando novamente com título resolvido via %s: %s",
            resolution.provider,
            resolution.resolved_title,
        )
        return resolution
    return None


def search_anime_flow(args):
    """Flow for searching and selecting an anime with progressive search support.

    Supports decreasing word count if user wants to see more results.
    Example: "Spy Family Season 2" (4 words) → Try 4 → 3 → 2 words progressively.

    Cache-first: Checks cache before searching scrapers to avoid unnecessary requests.
    """
    # Clear previous search results to avoid accumulating data from previous calls
    # (Repository is singleton, so it keeps data between calls)
    rep.clear_search_results()

    query = input("\n🔍 Pesquise anime: ") if not args.query else args.query

    source = None

    # Cache-first: Check if query is in cache before searching scrapers
    cache_data = get_cache(query)
    selected_anime = None
    if cache_data:
        logger.info(f"Usando cache ({cache_data.episode_count} eps disponíveis)")
        # Populate repository from cache
        rep.load_from_cache(query, cache_data)

        # Discover available sources for this anime (background search)
        rep.search_anime(query, verbose=False)

        selected_anime = query
    else:
        search_result = _select_from_manual_search_results(query, args)
        if search_result.was_cancelled:
            return None, None, None

        if not search_result.found:
            resolution = _resolve_search_query(query)
            if resolution:
                search_result = _select_from_manual_search_results(resolution.resolved_title, args)
                if search_result.was_cancelled:
                    return None, None, None

        if not search_result.found:
            logger.error(
                "❌ Nenhum resultado encontrado nem pela busca direta nem pela resolução externa."
            )
            return None, None, None

        selected_anime = search_result.selected_anime
        source = search_result.source

    # At this point, selected_anime is set from either cache or scrapers
    with loading("Carregando episódios..."):
        rep.search_episodes(selected_anime)

    # Handle season selection
    requested_season = None
    if hasattr(args, "season") and args.season is not None:
        # User specified season via -S flag
        requested_season = args.season
        available_seasons = rep.get_available_seasons(selected_anime)
        if requested_season not in available_seasons:
            logger.error(
                f"❌ Estação {requested_season} não encontrada. "
                f"Estações disponíveis: {available_seasons}"
            )
            return None, None, None
        logger.info(f"🎬 Filtrando: Estação {requested_season}")
    else:
        # Show season menu if applicable
        available_seasons = rep.get_available_seasons(selected_anime)
        if len(available_seasons) > 1:
            # Multiple seasons: show menu
            season_options = []
            for season in available_seasons:
                try:
                    season_episodes = rep.get_episode_list(selected_anime, season=season)
                    ep_count = len(season_episodes)
                    season_options.append((season, f"🎬 Estação {season} ({ep_count} episódios)"))
                except Exception:
                    season_options.append((season, f"🎬 Estação {season}"))

            season_options_display = [opt[1] for opt in season_options]
            selected_option = menu_navigate(season_options_display, msg="Escolha a estação.")

            if selected_option is None:
                return None, None, None  # User cancelled

            # Extract season from selected option
            for season_num, display in season_options:
                if display == selected_option:
                    requested_season = season_num
                    break

    # Now get episodes filtered by season (if specified)
    episode_list = rep.get_episode_list(selected_anime, season=requested_season)

    # Handle -e flag: skip menu if episode number provided
    if hasattr(args, "episode") and args.episode is not None:
        total_episodes = len(episode_list)

        # Validate episode number is within bounds
        if args.episode < 1 or args.episode > total_episodes:
            logger.error(
                f"❌ Episódio {args.episode} não existe ou ainda não foi ao ar. "
                f"Episódios disponíveis: 1-{total_episodes}"
            )
            return None, None, None

        # Use episode directly (0-indexed for episode_idx)
        episode_idx = args.episode - 1
        selected_episode = episode_list[episode_idx]
    else:
        # No -e flag: show menu for user to select
        selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")

        if not selected_episode:
            return None, None, None  # User cancelled

        episode_idx = episode_list.index(selected_episode)

    return selected_anime, episode_idx, source
