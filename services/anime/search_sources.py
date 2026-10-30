"""Scraper-backed source search and AniList-assisted result ranking."""

from dataclasses import dataclass

from models.models import SearchResults


@dataclass
class ScraperSearchOutcome:
    """Result of a single scraper search + ranking pass."""

    titles_with_sources: list[str]
    used_query: str
    anilist_reference_title: str | None
    search_results: SearchResults


def perform_scraper_search(
    partial_query: str, *, repository, discover_anilist, get_ranked_titles, ranker, log
) -> ScraperSearchOutcome:
    """Run a scraper search for ``partial_query`` and rank the results.

    Clears prior results, searches all scrapers, attempts an AniList match for
    ranking, and returns the ranked titles-with-sources plus the query actually
    used and any AniList reference title discovered.
    """
    search_results = repository.search_anime(partial_query, verbose=True)

    search_metadata = repository.get_search_metadata(search_results=search_results)
    used_query = search_metadata.used_query or partial_query

    ranking_query = used_query
    anilist_reference_title: str | None = None
    anilist_results = None
    try:
        anilist_results = discover_anilist(used_query)
        if anilist_results:
            ranking_query = anilist_results[0].title
            anilist_reference_title = ranking_query
    except Exception as e:
        log.debug(f"AniList indisponível para '{used_query}': {e}")

    titles_with_sources = get_ranked_titles(
        filter_by_query=used_query,
        original_query=ranking_query,
        anilist_results=anilist_results,
        search_results=search_results,
    )

    if anilist_reference_title:
        titles_with_sources = ranker(titles_with_sources, anilist_reference_title)

    return ScraperSearchOutcome(
        titles_with_sources, used_query, anilist_reference_title, search_results
    )


__all__ = ["ScraperSearchOutcome", "perform_scraper_search"]
