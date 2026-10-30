"""Result models shared by anime search flow and selection."""

from dataclasses import dataclass

from services.anime.search_state import IncrementalSearchState


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


__all__ = ["ContextualSearchResults", "DualSearchResults", "ManualSearchSelection"]
