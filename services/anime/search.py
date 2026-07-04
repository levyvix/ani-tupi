"""Anime search flow with progressive search support.

Handles manual anime search with progressive word reduction,
cache integration, and scraper discovery.
"""

import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

from models.config import settings
from models.models import AnimeTitleResolution
from services.anime.title_resolution import AnimeTitleResolver
from services.repository import rep
from ui.components import loading, menu_navigate, menu_navigate_episodes
from utils.scraper_cache import get_cache
from services.anime.title_normalization import normalize_anime_title
from utils.logging import get_logger


logger = get_logger(__name__)
INCREMENTAL_SEARCH_MAX_RESULTS = 20


def _debug_incremental_search(message: str) -> None:
    """Emit opt-in debug logs for incremental search investigations."""
    if os.getenv("ANI_TUPI_DEBUG_INCREMENTAL_SEARCH") == "1":
        logger.info(f"🔎 [incremental] {message}")


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


@dataclass(frozen=True)
class ContextualSearchResults:
    """Results for contextual scraper-first search with similarity ranking."""

    state: "IncrementalSearchState"
    titles_with_sources: list[str]
    used_query: str | None


@dataclass(frozen=True)
class DualSearchResults:
    """Paired search results for user query and resolved official title."""

    user_query: str
    user_results: ContextualSearchResults
    official_query: str
    official_results: ContextualSearchResults


def _filter_anime_results(titles: list[str], query: str) -> list[str]:
    """Filter anime titles using normalized and compact matching.

    This function filters a list of "Title [sources]" formatted strings
    using the repository's normalization rules plus a whitespace-insensitive
    compact form. The compact comparison is important for titles that appear
    concatenated in scraper sources, such as "himekishi", while the query
    may arrive as "hime kishi".

    Uses the same normalization logic as the repository to ensure
    consistent filtering behavior.

    Args:
        titles: List of anime titles in "Title [source1, source2]" format
        query: Query to filter by (e.g., "tate no yuusha no nariagari 2")

    Returns:
        Filtered list of titles where the normalized query appears in the
        normalized title, or the compact normalized query appears in the
        compact normalized title
    """
    from services.search_repository import SearchRepository as _SearchRepository
    from services.anime.title_normalization import get_compact_normalized_title_key

    normalize_fn = _SearchRepository._normalize_for_filter

    query_normalized = normalize_fn(query)
    query_compact = get_compact_normalized_title_key(query_normalized)
    filtered = []

    for title in titles:
        # Extract base title (remove source indicators like "[source1, source2]")
        base_title = title.split(" [")[0] if " [" in title else title

        # Normalize title for comparison
        title_normalized = normalize_fn(base_title)
        title_compact = get_compact_normalized_title_key(title_normalized)
        title_words = title_normalized.split()
        query_words = query_normalized.split()

        if (
            query_normalized in title_normalized
            or query_compact in title_compact
            or all(word in title_words for word in query_words)
        ):
            filtered.append(title)

    return filtered


def _rank_anime_results_by_reference(titles: list[str], reference_title: str) -> list[str]:
    """Rank title strings using the canonical AniList reference title."""
    from thefuzz import fuzz
    from services.search_repository import SearchRepository

    reference_title = reference_title.split(" / ")[0]
    reference_normalized = SearchRepository._normalize_for_filter(reference_title)
    reference_compact = SearchRepository._normalize_for_similarity(reference_title)
    reference_words = SearchRepository._normalize_words_for_similarity(reference_title)

    def contains_word_sequence(haystack: list[str], needle: list[str]) -> bool:
        if not needle:
            return True
        it = iter(haystack)
        return all(any(word == candidate for candidate in it) for word in needle)

    scored_titles = []
    for title in titles:
        base_title = title.split(" [")[0] if " [" in title else title
        normalized_title = SearchRepository._normalize_for_filter(base_title)
        compact_title = SearchRepository._normalize_for_similarity(base_title)
        title_words = SearchRepository._normalize_words_for_similarity(base_title)

        score = max(
            fuzz.ratio(reference_normalized, normalized_title),
            fuzz.partial_ratio(reference_normalized, normalized_title),
            fuzz.token_sort_ratio(reference_normalized, normalized_title),
            fuzz.ratio(reference_compact, compact_title),
        )

        if reference_words and title_words[: len(reference_words)] == reference_words:
            score = min(100, score + 40)
        elif reference_normalized in normalized_title:
            score = min(100, score + 20)
        elif reference_compact in compact_title:
            score = min(100, score + 10)

        if contains_word_sequence(title_words, reference_words):
            score = min(100, score + 25)
        else:
            score = max(0, score - 25)

        # Prefer more specific titles over short prefix-only matches.
        if len(title_words) < len(reference_words):
            if title_words == reference_words[: len(title_words)]:
                score = 0
            else:
                score = max(0, score - 50)
        elif len(title_words) > len(reference_words):
            score = min(100, score + min(30, (len(title_words) - len(reference_words)) * 5))

        scored_titles.append((title, score, len(title_words), base_title))

    scored_titles.sort(key=lambda item: (-item[1], item[2], item[3]))
    return [item[0] for item in scored_titles]


def _best_similarity_score_for_reference(titles: list[str], reference_title: str) -> int:
    """Return the best similarity score between results and a reference title."""
    from thefuzz import fuzz
    from services.search_repository import SearchRepository

    if not titles or not reference_title:
        return 0

    reference_normalized = SearchRepository._normalize_for_filter(reference_title)
    reference_compact = SearchRepository._normalize_for_similarity(reference_title)
    best_score = 0

    for title in titles:
        base_title = title.split(" [")[0] if " [" in title else title
        normalized_title = SearchRepository._normalize_for_filter(base_title)
        compact_title = SearchRepository._normalize_for_similarity(base_title)

        score = max(
            fuzz.ratio(reference_normalized, normalized_title),
            fuzz.partial_ratio(reference_normalized, normalized_title),
            fuzz.token_sort_ratio(reference_normalized, normalized_title),
            fuzz.ratio(reference_compact, compact_title),
        )
        best_score = max(best_score, score)

    return best_score


def _get_ranked_titles_with_sources(
    *, filter_by_query: str | None, original_query: str | None, anilist_results
) -> list[str]:
    return rep.get_anime_titles_with_sources(
        filter_by_query=filter_by_query,
        original_query=original_query,
        anilist_results=anilist_results,
    )


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
    5. Stop when results ≤ 20
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
    _debug_incremental_search(f"query='{query}' normalized='{normalized_query}' words={words}")

    # Determine starting word count.
    # Very short first tokens like "no", "to", "re" are too ambiguous on their own,
    # so start with the first two words when possible.
    start_word_count = 1
    if len(words) >= 2 and len(words[0]) < 4:
        start_word_count = 2
    current_word_count = start_word_count
    current_results: list[str] = []
    base_results: list[str] = []  # Store base search results for filtering
    anilist_reference_title: str | None = None
    anilist_results = None

    # Progressive filtering: add words until results ≤ 20
    # After the initial base search, we filter results instead of re-searching scrapers
    while current_word_count <= len(words):
        # Build search query for this iteration
        partial_query = " ".join(words[:current_word_count])
        _debug_incremental_search(f"iteration={current_word_count} partial_query='{partial_query}'")

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
                        anilist_reference_title = ranking_query
                except Exception as e:
                    logger.debug(f"AniList indisponível para '{used_query}': {e}")

                # Get anime titles with sources, ranked by AniList if available
                titles_with_sources = _get_ranked_titles_with_sources(
                    filter_by_query=used_query,
                    original_query=ranking_query,
                    anilist_results=anilist_results,
                )

                if anilist_reference_title:
                    titles_with_sources = _rank_anime_results_by_reference(
                        titles_with_sources, anilist_reference_title
                    )

                # Store base results for filtering in subsequent iterations
                # These results are from the base N-word search and will be filtered, not re-searched
                base_results = titles_with_sources.copy()
                current_results = titles_with_sources
                _debug_incremental_search(
                    f"base_search results={len(current_results)} used_query='{used_query}'"
                )

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
                if len(current_results) <= INCREMENTAL_SEARCH_MAX_RESULTS:
                    # Good result set size - stop here
                    _debug_incremental_search(
                        f"stop: base results <= {INCREMENTAL_SEARCH_MAX_RESULTS}"
                    )
                    break

            except (OSError, ConnectionError, TimeoutError, ValueError) as e:
                logger.warning(f"Error during incremental search at word {current_word_count}: {e}")
                # Fall back to previous results if available
                if state.has_previous():
                    state.go_back()
                    current_results = state.get_current().results
                    break
                raise
            except Exception:
                raise

        else:
            # Subsequent iterations: filter base results instead of re-searching
            # This avoids unnecessary scraper calls and is much faster
            try:
                with loading(f"Filtrando '{partial_query}'..."):
                    # Filter the base results by the expanded query
                    # Uses substring matching on normalized titles (same as repository does)
                    filtered = _filter_anime_results(base_results, partial_query)
                _debug_incremental_search(
                    f"filtered_count={len(filtered)} from_base={len(base_results)} "
                    f"for='{partial_query}'"
                )

                # If filtered results are very few (<= 3), or zero, do a fresh search instead
                # This handles cases where API returns different results for different queries
                # (e.g., AnimesDigital returns more results for "re zero" than filtering "re" results)
                #
                # Re-search strategy:
                # - If query has 2+ words AND filtered results <= 3: ALWAYS re-search
                #   (2+ words = specific enough query to be worth re-searching all scrapers)
                # - This ensures we don't miss results from APIs that only match multi-word queries
                #   (e.g., AnimesDigital finds Re:Zero for "re zero" but not for "re")
                if len(filtered) <= 3 and current_word_count >= 2:
                    logger.debug(
                        f"Only {len(filtered)} filtered results for '{partial_query}', "
                        "performing fresh search instead"
                    )
                    _debug_incremental_search(
                        f"fresh_search triggered for='{partial_query}' because filtered_count={len(filtered)}"
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
                            anilist_reference_title = ranking_query
                    except Exception as e:
                        logger.debug(f"AniList indisponível para '{used_query}': {e}")

                    # Get anime titles with sources, ranked by AniList if available
                    titles_with_sources = _get_ranked_titles_with_sources(
                        filter_by_query=used_query,
                        original_query=ranking_query,
                        anilist_results=anilist_results,
                    )

                    if anilist_reference_title:
                        titles_with_sources = _rank_anime_results_by_reference(
                            titles_with_sources, anilist_reference_title
                        )

                    if not titles_with_sources:
                        _debug_incremental_search(
                            f"fresh_search returned 0 results for='{partial_query}', keeping previous state"
                        )
                        current_state = state.get_current()
                        if current_state:
                            current_results = current_state.results
                        _debug_incremental_search(
                            f"continuing after empty fresh_search for='{partial_query}'"
                        )
                        current_word_count += 1
                        continue

                    # Update base_results to include new search results for future filtering
                    base_results = titles_with_sources.copy()
                    current_results = titles_with_sources
                    _debug_incremental_search(
                        f"fresh_search results={len(current_results)} used_query='{used_query}'"
                    )

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
                    if anilist_reference_title:
                        filtered = _rank_anime_results_by_reference(
                            filtered, anilist_reference_title
                        )
                    current_results = filtered
                    _debug_incremental_search(
                        f"using_filtered_results count={len(current_results)} for='{partial_query}'"
                    )

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
                    # Filtering reached 0 results, so keep the last valid state but continue
                    # trying later words. Some sources only return the target once the query
                    # becomes specific enough.
                    _debug_incremental_search(
                        f"filter returned 0 for='{partial_query}', keeping previous valid state and continuing"
                    )
                    current_state = state.get_current()
                    if current_state:
                        current_results = current_state.results
                    current_word_count += 1
                    continue

            except (OSError, ConnectionError, TimeoutError, ValueError) as e:
                logger.warning(f"Error during filtering at word {current_word_count}: {e}")
                # Fall back to previous results if available
                if state.has_previous():
                    state.go_back()
                    current_results = state.get_current().results
                    break
                raise
            except Exception:
                raise

            # Check stopping condition
            if len(current_results) <= INCREMENTAL_SEARCH_MAX_RESULTS:
                # Good result set size - stop here
                _debug_incremental_search(
                    f"stop: current results={len(current_results)} <= {INCREMENTAL_SEARCH_MAX_RESULTS}"
                )
                break

        # Continue adding words
        current_word_count += 1

    # Handle zero results: revert to previous iteration if available
    if not current_results and state.has_previous():
        state.go_back()
        current_results = state.get_current().results
        _debug_incremental_search(
            "final fallback to previous state because current_results was empty"
        )

    current_state = state.get_current()
    if current_state:
        _debug_incremental_search(
            f"final_state word_count={current_state.word_count} query='{current_state.query}' "
            f"results={len(current_state.results)}"
        )

    return state, current_results


def contextual_incremental_search(
    query: str,
    reference_title: str | None = None,
    english_title: str | None = None,
    romaji_title: str | None = None,
) -> ContextualSearchResults:
    """Run incremental scraper search and rank the final results by similarity.

    This is the scraper-first search path used by AniList-aware flows:
    start with the first normalized word, gather base results from scrapers once,
    then narrow locally and rank the final list against a reference title.
    """
    search_state, titles_with_sources = incremental_search_anime(
        query,
        english_title=english_title,
        romaji_title=romaji_title,
    )

    ranking_title = reference_title or romaji_title or english_title or query
    if titles_with_sources and ranking_title:
        titles_with_sources = _rank_anime_results_by_reference(titles_with_sources, ranking_title)

    used_query = None
    current_result_set = search_state.get_current()
    if current_result_set:
        used_query = current_result_set.query

    return ContextualSearchResults(
        state=search_state,
        titles_with_sources=titles_with_sources,
        used_query=used_query,
    )


def _parallel_contextual_search_worker(query: str, reference_title: str) -> dict:
    """Run a contextual search in an isolated process and return serializable data."""
    from scrapers import loader

    loader.load_plugins()
    result = contextual_incremental_search(query, reference_title=reference_title)
    return {
        "used_query": result.used_query,
        "titles_with_sources": result.titles_with_sources,
    }


def _search_results_from_serialized(query: str, payload: dict) -> ContextualSearchResults:
    """Rebuild minimal contextual results from a serialized worker payload."""
    used_query = payload.get("used_query") or query
    state = IncrementalSearchState()
    if payload.get("titles_with_sources"):
        word_count = max(1, len(used_query.split()))
        state.add_result(
            word_count=word_count,
            query=used_query,
            results=list(payload["titles_with_sources"]),
            used_query=used_query,
        )
    return ContextualSearchResults(
        state=state,
        titles_with_sources=list(payload.get("titles_with_sources", [])),
        used_query=used_query,
    )


def _ensure_anime_sources_in_repo(selected_anime: str, *fallback_queries: str) -> bool:
    """Populate ``anime_to_urls`` after searches that ran outside the main process.

    Dual contextual search uses worker processes, so their repository state is not
    visible here. Re-run lightweight scraper searches in-process until the chosen
    anime title is registered.
    """
    if rep.anime_to_urls.get(selected_anime):
        return True

    candidates: list[str] = []
    seen: set[str] = set()
    for query in (selected_anime, *fallback_queries):
        cleaned = (query or "").strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(cleaned)

    for candidate in candidates:
        rep.search_anime(candidate, verbose=False)
        if rep.anime_to_urls.get(selected_anime):
            return True

    return bool(rep.anime_to_urls.get(selected_anime))


def run_dual_contextual_search(user_query: str, official_query: str) -> DualSearchResults:
    """Run user query and official-title query in parallel and return both result sets."""
    with ProcessPoolExecutor(max_workers=2) as executor:
        user_future = executor.submit(
            _parallel_contextual_search_worker,
            user_query,
            user_query,
        )
        official_future = executor.submit(
            _parallel_contextual_search_worker,
            official_query,
            official_query,
        )
        user_payload = user_future.result()
        official_payload = official_future.result()

    return DualSearchResults(
        user_query=user_query,
        user_results=_search_results_from_serialized(user_query, user_payload),
        official_query=official_query,
        official_results=_search_results_from_serialized(official_query, official_payload),
    )


def _select_from_manual_search_results(
    search_results: ContextualSearchResults,
    query: str,
    args,
) -> ManualSearchSelection:
    """Run the manual incremental search UI for one query."""
    search_state = search_results.state
    current_titles = search_results.titles_with_sources
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
            enable_search=False,
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


def _select_from_dual_search_results(
    dual_results: DualSearchResults,
) -> ManualSearchSelection:
    """Show both user-query and official-title results in one menu."""
    options: list[str] = []
    seen_titles: set[str] = set()

    def add_group(label: str, results: ContextualSearchResults) -> None:
        if not results.titles_with_sources:
            return
        options.append(f"─ {label}")
        for title in results.titles_with_sources:
            if title in seen_titles:
                continue
            seen_titles.add(title)
            options.append(title)

    add_group(f"Sua busca: {dual_results.user_query}", dual_results.user_results)
    add_group(f"Nome oficial/romaji: {dual_results.official_query}", dual_results.official_results)

    if not seen_titles:
        return ManualSearchSelection(selected_anime=None, source=None, was_cancelled=False)

    selected_anime_with_source = menu_navigate(
        options,
        msg="Escolha o Anime.",
        enable_search=False,
    )
    if not selected_anime_with_source:
        return ManualSearchSelection(selected_anime=None, source=None, was_cancelled=True)

    selected_anime = selected_anime_with_source.split(" [")[0]
    source = None
    if " [" in selected_anime_with_source and selected_anime_with_source.endswith("]"):
        source = selected_anime_with_source.split(" [")[1].rstrip("]")

    return ManualSearchSelection(
        selected_anime=selected_anime,
        source=source,
        was_cancelled=False,
        search_query_used=dual_results.official_results.used_query
        or dual_results.user_results.used_query,
    )


def _resolve_search_query(query: str) -> AnimeTitleResolution | None:
    """Resolve a failed manual query into a more canonical title."""
    if not settings.search.enable_title_resolution:
        return None

    resolver = AnimeTitleResolver()
    resolution = resolver.resolve(query)
    if resolution and resolution.resolved_title.casefold() != query.strip().casefold():
        return resolution
    return None


def _build_search_query_candidates(
    original_query: str,
    resolution: AnimeTitleResolution | None,
) -> list[str]:
    """Build fallback search queries from the resolved title and its aliases.

    The resolver already picks the highest-scoring Jikan candidate. If that
    canonical title does not yield scraper results, try the provider aliases
    before falling back to the user's original query.
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str | None) -> None:
        if not value:
            return
        cleaned = value.strip()
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        candidates.append(cleaned)

    if resolution:
        add_candidate(resolution.resolved_title)
        for alias in resolution.aliases:
            add_candidate(alias)

    add_candidate(original_query)
    return candidates


def search_anime_flow(args):
    """Flow for searching and selecting an anime with progressive search support.

    Supports decreasing word count if user wants to see more results.
    Example: "Spy Family Season 2" (4 words) → Try 4 → 3 → 2 words progressively.

    Jikan-first: resolves the canonical title before cache and scraper search.
    """
    # Clear previous search results to avoid accumulating data from previous calls
    # (Repository is singleton, so it keeps data between calls)
    rep.clear_search_results()

    query = input("\n🔍 Pesquise anime: ") if not args.query else args.query

    source = None
    resolution = _resolve_search_query(query)
    if resolution:
        official_title = resolution.resolved_title.strip()
        if official_title and official_title.casefold() != query.strip().casefold():
            logger.info(f"💡 Nome oficial/romaji encontrado: {official_title}")

    selected_anime = None
    source = None
    search_query_used = query
    fallback_resolution = resolution

    if resolution:
        official_title = resolution.resolved_title.strip()
        dual_results = run_dual_contextual_search(query, official_title)
        selection = _select_from_dual_search_results(dual_results)
        if selection.was_cancelled:
            return None, None, None
        if selection.found:
            selected_anime = selection.selected_anime
            source = selection.source
            if selection.search_query_used:
                search_query_used = selection.search_query_used

    for candidate_query in [] if selected_anime else [query]:
        # Cache-first: Check if query is in cache before searching scrapers
        cache_data = get_cache(candidate_query)

        if cache_data:
            logger.info(f"Usando cache ({cache_data.episode_count} eps disponíveis)")
            # Populate repository from cache
            rep.load_from_cache(candidate_query, cache_data)

            # Discover available sources for this anime (background search)
            rep.search_anime(candidate_query, verbose=False)

            selected_anime = candidate_query
            break

        search_result = _select_from_manual_search_results(
            contextual_incremental_search(
                candidate_query,
                reference_title=resolution.resolved_title if resolution else candidate_query,
            ),
            candidate_query,
            args,
        )
        if search_result.was_cancelled:
            return None, None, None

        if search_result.found:
            selected_anime = search_result.selected_anime
            source = search_result.source
            break

    if not selected_anime:
        search_candidates = _build_search_query_candidates(query, fallback_resolution)

        # Skip only the original query because it was already tried above.
        fallback_candidates = [
            candidate_query
            for candidate_query in search_candidates
            if candidate_query.strip().casefold() != query.strip().casefold()
        ]

        for candidate_query in fallback_candidates:
            if fallback_resolution:
                logger.info(
                    f"🔎 Tentando novamente com título resolvido via {fallback_resolution.provider}: "
                    f"{candidate_query}"
                )

            cache_data = get_cache(candidate_query)

            if cache_data:
                logger.info(f"Usando cache ({cache_data.episode_count} eps disponíveis)")
                rep.load_from_cache(candidate_query, cache_data)
                rep.search_anime(candidate_query, verbose=False)
                selected_anime = candidate_query
                break

            contextual_results = contextual_incremental_search(
                candidate_query,
                reference_title=fallback_resolution.resolved_title
                if fallback_resolution
                else candidate_query,
            )
            search_result = _select_from_manual_search_results(
                contextual_results,
                candidate_query,
                args,
            )
            if search_result.was_cancelled:
                return None, None, None

            if search_result.found:
                selected_anime = search_result.selected_anime
                source = search_result.source
                break

    if not selected_anime:
        logger.error(
            "❌ Nenhum resultado encontrado nem pela busca direta nem pela resolução externa."
        )
        return None, None, None

    # At this point, selected_anime is set from either cache or scrapers
    fallback_queries = [query, search_query_used]
    if fallback_resolution:
        fallback_queries.append(fallback_resolution.resolved_title)

    with loading("Carregando episódios..."):
        if not _ensure_anime_sources_in_repo(selected_anime, *fallback_queries):
            logger.warning(
                "Não foi possível localizar fontes para '%s' após a seleção.",
                selected_anime,
            )
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
    else:
        # No -e flag: show menu for user to select
        episode_idx = menu_navigate_episodes(episode_list)

        if episode_idx is None:
            return None, None, None  # User cancelled

    return selected_anime, episode_idx, source
