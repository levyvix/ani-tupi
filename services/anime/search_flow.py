"""Anime search service - incremental flow, filtering, ranking and state.

Handles manual anime search with progressive word reduction, cache
integration and scraper discovery.

Seções:
- Conjunto de resultados
- Estado da busca incremental
- Filtragem
- Ranqueamento
- Busca nos scrapers
- Fluxo de busca incremental
"""

from concurrent.futures import FIRST_EXCEPTION, ProcessPoolExecutor, wait

from models.config import settings
from services.anime.search_state import IncrementalSearchState, SearchResultSet
from services.anime.search_result_models import (
    ContextualSearchResults,
    DualSearchResults,
    ManualSearchSelection,
)
from services.anime.search_sources import ScraperSearchOutcome, perform_scraper_search
from services.anime.search_selection import (
    select_dual_search_results,
    select_manual_search_results,
)
from services.anime.search_ranking import (
    best_similarity_score_for_reference,
    filter_anime_results,
    rank_anime_results_by_reference,
)
from models.models import AnimeTitleResolution, SearchResults
from services.anilist.anilist_service import get_scraper_cache
from utils.title_normalization import normalize_anime_title
from services.anime.title_resolution import AnimeTitleResolver
from services.core import ui_bridge
from services.repository import rep
from utils.logging import get_logger

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

_best_similarity_score_for_reference = best_similarity_score_for_reference
_filter_anime_results = filter_anime_results


logger = get_logger(__name__)


# === Busca nos scrapers ===


def _get_ranked_titles_with_sources(
    *, filter_by_query: str | None, original_query: str | None, anilist_results, search_results
) -> list[str]:
    return rep.get_anime_titles_with_sources(
        filter_by_query=filter_by_query,
        original_query=original_query,
        anilist_results=anilist_results,
        search_results=search_results,
    )


def _perform_scraper_search(partial_query: str) -> ScraperSearchOutcome:
    """Use injected search dependencies while preserving the legacy patch point."""
    from services.anilist.anilist_service import auto_discover_anilist_id

    return perform_scraper_search(
        partial_query,
        repository=rep,
        discover_anilist=auto_discover_anilist_id,
        get_ranked_titles=_get_ranked_titles_with_sources,
        ranker=rank_anime_results_by_reference,
        log=logger,
    )


def _select_from_manual_search_results(
    search_results: ContextualSearchResults, query: str, args
) -> ManualSearchSelection:
    """Delegate menu selection while retaining the historical facade API."""
    return select_manual_search_results(
        search_results, query, args, repository=rep, ui=ui_bridge, log=logger
    )


def _select_from_dual_search_results(
    dual_results: DualSearchResults,
) -> ManualSearchSelection:
    """Delegate dual-result selection while retaining the historical facade API."""
    return select_dual_search_results(dual_results, ui=ui_bridge)


# === Fluxo de busca incremental ===


# Sourced from user-tunable settings (ANI_TUPI__SEARCH__INCREMENTAL_MAX_RESULTS).
INCREMENTAL_SEARCH_MAX_RESULTS = settings.search.incremental_max_results


def _debug_incremental_search(message: str) -> None:
    """Emit opt-in debug logs for incremental search investigations."""
    if settings.debug_incremental_search:
        logger.info(f"🔎 [incremental] {message}")


def _count_sources(titles_with_sources: list[str]) -> dict[str, int]:
    """Count how many results each source contributed.

    Parses the ``"Title [source]"`` display format and tallies each source.
    """
    source_counts: dict[str, int] = {}
    for title_entry in titles_with_sources:
        if " [" in title_entry:
            _, source = title_entry.rsplit(" [", 1)
            source = source.rstrip("]")
            source_counts[source] = source_counts.get(source, 0) + 1
    return source_counts


def _init_language_tracking(
    state: IncrementalSearchState,
    query: str,
    english_title: str | None,
    romaji_title: str | None,
) -> None:
    """Seed language-toggle tracking on ``state`` from the query's language."""
    if not (english_title and romaji_title and english_title != romaji_title):
        return

    query_lower = query.lower()
    english_lower = english_title.lower()

    if english_lower in query_lower or query_lower == english_lower:
        state.current_language = "english"
        state.current_title = english_title
        state.alternative_title = romaji_title
        state.alternative_language = "romaji"
    else:
        state.current_language = "romaji"
        state.current_title = romaji_title
        state.alternative_title = english_title
        state.alternative_language = "english"


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

    _init_language_tracking(state, query, english_title, romaji_title)

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

    # Progressive filtering: add words until results ≤ 20
    # After the initial base search, we filter results instead of re-searching scrapers
    while current_word_count <= len(words):
        # Build search query for this iteration
        partial_query = " ".join(words[:current_word_count])
        _debug_incremental_search(f"iteration={current_word_count} partial_query='{partial_query}'")

        if current_word_count == start_word_count:
            # Initial search: execute scraper search (only happens once)
            # All subsequent iterations will filter this base result set
            try:
                with ui_bridge.loading(f"Buscando '{partial_query}'..."):
                    outcome = _perform_scraper_search(partial_query)

                used_query = outcome.used_query
                if outcome.anilist_reference_title:
                    anilist_reference_title = outcome.anilist_reference_title
                titles_with_sources = outcome.titles_with_sources

                # Store base results for filtering in subsequent iterations
                # These results are from the base N-word search and will be filtered, not re-searched
                base_results = titles_with_sources.copy()
                current_results = titles_with_sources
                _debug_incremental_search(
                    f"base_search results={len(current_results)} used_query='{used_query}'"
                )

                # Store results in state (with normalized used_query)
                state.add_result(
                    current_word_count,
                    partial_query,
                    titles_with_sources,
                    _count_sources(titles_with_sources),
                    used_query=used_query,
                    is_filtered=False,
                    search_results=outcome.search_results,
                )

                if not current_results and current_word_count < len(words):
                    # Repository search already tries progressively shorter
                    # prefixes. Start that pass with the complete title so a
                    # slug-based catalog can resolve the exact AniList name.
                    full_query = " ".join(words)
                    _debug_incremental_search(
                        f"empty base results; retrying full title '{full_query}'"
                    )
                    with ui_bridge.loading(f"Buscando '{full_query}'..."):
                        fallback_outcome = _perform_scraper_search(full_query)

                    used_query = fallback_outcome.used_query
                    if fallback_outcome.anilist_reference_title:
                        anilist_reference_title = fallback_outcome.anilist_reference_title
                    current_results = fallback_outcome.titles_with_sources
                    current_word_count = len(words)
                    state.add_result(
                        len(words),
                        full_query,
                        current_results,
                        _count_sources(current_results),
                        used_query=used_query,
                        is_filtered=False,
                        search_results=fallback_outcome.search_results,
                    )
                    if current_results:
                        base_results = current_results.copy()
                    else:
                        break

                # Stop only after finding something. An empty first-word search
                # must continue to more specific prefixes because some sources
                # only return results for multi-word queries.
                if current_results and len(current_results) <= INCREMENTAL_SEARCH_MAX_RESULTS:
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
                with ui_bridge.loading(f"Filtrando '{partial_query}'..."):
                    # Filter the base results by the expanded query
                    # Uses substring matching on normalized titles (same as repository does)
                    filtered = filter_anime_results(base_results, partial_query)
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
                    with ui_bridge.loading(f"Buscando '{partial_query}'..."):
                        outcome = _perform_scraper_search(partial_query)

                    used_query = outcome.used_query
                    if outcome.anilist_reference_title:
                        anilist_reference_title = outcome.anilist_reference_title
                    titles_with_sources = outcome.titles_with_sources

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

                    state.add_result(
                        current_word_count,
                        partial_query,
                        titles_with_sources,
                        _count_sources(titles_with_sources),
                        used_query=used_query,
                        is_filtered=False,  # This was a fresh search, not a filter
                        search_results=outcome.search_results,
                    )

                elif filtered:
                    # Filtered results found and enough (> 3) - use them
                    if anilist_reference_title:
                        filtered = rank_anime_results_by_reference(
                            filtered, anilist_reference_title
                        )
                    current_results = filtered
                    _debug_incremental_search(
                        f"using_filtered_results count={len(current_results)} for='{partial_query}'"
                    )

                    previous_result_set = state.get_current()
                    state.add_result(
                        current_word_count,
                        partial_query,
                        filtered,
                        _count_sources(filtered),
                        used_query=partial_query,
                        is_filtered=True,
                        search_results=(
                            previous_result_set.search_results if previous_result_set else None
                        ),
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

            # Check stopping condition only when results exist. Empty prefixes
            # continue through the query so later words can match the title.
            if current_results and len(current_results) <= INCREMENTAL_SEARCH_MAX_RESULTS:
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
        titles_with_sources = rank_anime_results_by_reference(titles_with_sources, ranking_title)

    used_query = None
    current_result_set = search_state.get_current()
    if current_result_set:
        used_query = current_result_set.query

    return ContextualSearchResults(
        state=search_state,
        titles_with_sources=titles_with_sources,
        used_query=used_query,
        search_results=current_result_set.search_results if current_result_set else None,
    )


def _parallel_contextual_search_worker(query: str, reference_title: str) -> dict:
    """Run a contextual search in an isolated process and return serializable data."""
    from scrapers import loader

    loader.load_plugins(rep.register)
    result = contextual_incremental_search(query, reference_title=reference_title)
    return {
        "used_query": result.used_query,
        "titles_with_sources": result.titles_with_sources,
        "search_results": (
            result.search_results.model_dump(mode="python") if result.search_results else None
        ),
    }


def _search_results_from_serialized(query: str, payload: dict) -> ContextualSearchResults:
    """Rebuild minimal contextual results from a serialized worker payload."""
    used_query = payload.get("used_query") or query
    search_results_payload = payload.get("search_results")
    search_results = (
        SearchResults.model_validate(search_results_payload) if search_results_payload else None
    )
    state = IncrementalSearchState()
    if payload.get("titles_with_sources"):
        word_count = max(1, len(used_query.split()))
        state.add_result(
            word_count=word_count,
            query=used_query,
            results=list(payload["titles_with_sources"]),
            used_query=used_query,
            search_results=search_results,
        )
    return ContextualSearchResults(
        state=state,
        titles_with_sources=list(payload.get("titles_with_sources", [])),
        used_query=used_query,
        search_results=search_results,
    )


def _find_anime_search_results(selected_anime: str, *fallback_queries: str) -> SearchResults | None:
    """Resolve source URLs from an invocation snapshot for a selected title."""
    candidates: list[str] = []
    seen: set[str] = set()
    for query in (selected_anime, *fallback_queries):
        cleaned = (query or "").strip()
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            candidates.append(cleaned)

    for candidate in candidates:
        search_results = rep.search_anime(candidate, verbose=False)
        if search_results.get_sources_for_title(selected_anime):
            return search_results
    return None


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
        futures = (user_future, official_future)
        # Wait for both to settle (or for the first failure). This ensures a
        # failure in one future never leaves the other's result unretrieved.
        wait(futures, return_when=FIRST_EXCEPTION)
        try:
            user_payload = user_future.result()
            official_payload = official_future.result()
        except BaseException:
            # Cancel anything still pending, then let the ``with`` block's
            # shutdown(wait=True) reap the running worker, and re-raise.
            for future in futures:
                future.cancel()
            raise

    return DualSearchResults(
        user_query=user_query,
        user_results=_search_results_from_serialized(user_query, user_payload),
        official_query=official_query,
        official_results=_search_results_from_serialized(official_query, official_payload),
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

    The resolver already picks the highest-scoring provider candidate. If that
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


def _try_cache_hit(
    candidate_query: str, *, include_search_results: bool = False
) -> bool | SearchResults:
    """Populate the repository from cache for ``candidate_query`` if present.

    Returns ``True`` when a cache entry was found and loaded (so the caller can
    treat ``candidate_query`` as the selected anime), ``False`` otherwise.
    """
    cache_data = get_scraper_cache(candidate_query)
    if not cache_data:
        return False

    logger.info(f"Usando cache ({cache_data.episode_count} eps disponíveis)")
    # Populate repository from cache and discover available sources (background search).
    rep.load_from_cache(candidate_query, cache_data)
    search_results = rep.search_anime(candidate_query, verbose=False)
    return search_results if include_search_results else True


def search_anime_flow(args):
    """Flow for searching and selecting an anime with progressive search support.

    Supports decreasing word count if user wants to see more results.
    Example: "Spy Family Season 2" (4 words) → Try 4 → 3 → 2 words progressively.

    Resolution-first: resolves the canonical title before cache and scraper search.
    """
    if args.query:
        query = args.query
    else:
        try:
            query = ui_bridge.prompt("\n🔍 Pesquise anime (Enter para voltar): ").strip()
        except KeyboardInterrupt:
            # Treat Ctrl+C at the search prompt as navigation back to the main menu.
            return None, None, None

        if not query:
            return None, None, None

    source = None
    resolution = _resolve_search_query(query)
    if resolution:
        official_title = resolution.resolved_title.strip()
        if official_title and official_title.casefold() != query.strip().casefold():
            logger.info(f"💡 Nome oficial/romaji encontrado: {official_title}")

    selected_anime = None
    selected_search_results: SearchResults | None = None
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
            selected_search_results = selection.search_results
            if selection.search_query_used:
                search_query_used = selection.search_query_used

    for candidate_query in [] if selected_anime else [query]:
        # Cache-first: Check if query is in cache before searching scrapers
        cache_results = _try_cache_hit(candidate_query, include_search_results=True)
        if cache_results:
            selected_anime = candidate_query
            selected_search_results = cache_results
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
            selected_search_results = search_result.search_results
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

            cache_results = _try_cache_hit(candidate_query, include_search_results=True)
            if cache_results:
                selected_anime = candidate_query
                selected_search_results = cache_results
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
                selected_search_results = search_result.search_results
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

    if selected_search_results is None:
        selected_search_results = _find_anime_search_results(selected_anime, *fallback_queries)

    with ui_bridge.loading("Carregando episódios..."):
        if selected_search_results is None:
            logger.warning(
                "Não foi possível localizar fontes para '%s' após a seleção.",
                selected_anime,
            )
            rep.search_episodes(selected_anime)
        else:
            rep.search_episodes(selected_anime, search_results=selected_search_results)

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
            selected_option = ui_bridge.menu_navigate(
                season_options_display, msg="Escolha a estação."
            )

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
        episode_idx = ui_bridge.menu_navigate_episodes(episode_list)

        if episode_idx is None:
            return None, None, None  # User cancelled

    return selected_anime, episode_idx, source
