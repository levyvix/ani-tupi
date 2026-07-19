"""Anime search flow with progressive search support.

Handles manual anime search with progressive word reduction,
cache integration, and scraper discovery.
"""

# Re-export public components from main module for backward compatibility
from services.anime.search.core import (
    incremental_search_anime,
    contextual_incremental_search,
    search_anime_flow,
    run_dual_contextual_search,
    ManualSearchSelection,
    ContextualSearchResults,
    DualSearchResults,
)
from services.anime.search.incremental_search_state import IncrementalSearchState
from services.anime.search.result_set import SearchResultSet
from services.anime.search.filtering import _filter_anime_results
from services.anime.search.ranking import (
    _rank_anime_results_by_reference,
    _best_similarity_score_for_reference,
)
from services.anime.search.scraper_search import (
    _ScraperSearchOutcome,
    _perform_scraper_search,
    _get_ranked_titles_with_sources,
)

__all__ = [
    "incremental_search_anime",
    "contextual_incremental_search",
    "search_anime_flow",
    "run_dual_contextual_search",
    "ManualSearchSelection",
    "ContextualSearchResults",
    "DualSearchResults",
    "IncrementalSearchState",
    "SearchResultSet",
    "_filter_anime_results",
    "_rank_anime_results_by_reference",
    "_best_similarity_score_for_reference",
    "_perform_scraper_search",
    "_get_ranked_titles_with_sources",
    "_ScraperSearchOutcome",
]
