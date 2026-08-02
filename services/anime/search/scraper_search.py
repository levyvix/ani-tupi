"""Scraper search execution and result ranking."""

from dataclasses import dataclass

from services.repository import rep
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _ScraperSearchOutcome:
    """Result of a single scraper search + ranking pass."""

    titles_with_sources: list[str]
    used_query: str
    anilist_reference_title: str | None


def _get_ranked_titles_with_sources(
    *, filter_by_query: str | None, original_query: str | None, anilist_results
) -> list[str]:
    return rep.get_anime_titles_with_sources(
        filter_by_query=filter_by_query,
        original_query=original_query,
        anilist_results=anilist_results,
    )


def _perform_scraper_search(partial_query: str) -> _ScraperSearchOutcome:
    """Run a scraper search for ``partial_query`` and rank the results.

    Clears prior results, searches all scrapers, attempts an AniList match for
    ranking, and returns the ranked titles-with-sources plus the query actually
    used and any AniList reference title discovered.
    """
    from services.anime.search.ranking import _rank_anime_results_by_reference

    rep.clear_search_results()
    rep.search_anime(partial_query, verbose=True)

    search_metadata = rep.get_search_metadata()
    used_query = search_metadata.used_query or partial_query

    ranking_query = used_query
    anilist_reference_title: str | None = None
    anilist_results = None
    try:
        from services.anilist.anilist_service import auto_discover_anilist_id

        anilist_results = auto_discover_anilist_id(used_query)
        if anilist_results:
            ranking_query = anilist_results[0].title
            anilist_reference_title = ranking_query
    except Exception as e:
        logger.debug(f"AniList indisponível para '{used_query}': {e}")

    titles_with_sources = _get_ranked_titles_with_sources(
        filter_by_query=used_query,
        original_query=ranking_query,
        anilist_results=anilist_results,
    )

    if anilist_reference_title:
        titles_with_sources = _rank_anime_results_by_reference(
            titles_with_sources, anilist_reference_title
        )

    return _ScraperSearchOutcome(titles_with_sources, used_query, anilist_reference_title)
