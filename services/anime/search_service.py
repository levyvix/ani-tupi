# ruff: noqa: F822
# pyright: reportUnsupportedDunderAll=false

"""Compatibility facade for anime search service imports."""

import sys

from services.anime import search_flow as implementation

__all__ = [
    "ContextualSearchResults",
    "DualSearchResults",
    "INCREMENTAL_SEARCH_MAX_RESULTS",
    "IncrementalSearchState",
    "ManualSearchSelection",
    "SearchResultSet",
    "_best_similarity_score_for_reference",
    "contextual_incremental_search",
    "incremental_search_anime",
    "rank_anime_results_by_reference",
    "run_dual_contextual_search",
    "search_anime_flow",
]
sys.modules[__name__] = implementation
