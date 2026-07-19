"""Incremental search state management for anime search navigation."""

from services.anime.search.result_set import SearchResultSet


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

        NOTE: this intentionally mutates ``self`` in place. Unlike the
        source-selection helpers, ``IncrementalSearchState`` is loop-owned
        internal search state (never a caller-passed input to transform), and
        the interactive search loop that owns it relies on this in-place
        semantics. Making it return a new copy would be invasive here (and the
        toggle-language tests assert in-place mutation), so it is not an
        immutable-data-flow violation.

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
