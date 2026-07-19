"""Persistence of anime selection choices.

Saves the user's anime/source selection so they can be reused in future sessions.
"""

from services.repository import rep
from services.anime.mappings import save_anilist_mapping
from utils.logging import get_logger

logger = get_logger(__name__)


def _persist_anime_choice(
    anilist_id: int,
    selected_anime: str,
    search_title: str,
    source: str | None,
) -> None:
    """Save the resolved anime choice (title, source, URLs) for next time."""
    anime_url = None
    anime_urls: dict[str, str] = {}

    repo_title = selected_anime
    if selected_anime not in rep.anime_to_urls:
        from thefuzz import fuzz

        repo_titles = list(rep.anime_to_urls.keys())
        if repo_titles:
            best_match = max(
                repo_titles,
                key=lambda t: fuzz.token_sort_ratio(selected_anime.lower(), t.lower()),
            )
            if fuzz.token_sort_ratio(selected_anime.lower(), best_match.lower()) >= 50:
                repo_title = best_match

    if repo_title in rep.anime_to_urls:
        for url, src, _params in rep.anime_to_urls[repo_title]:
            anime_urls[src] = url
            if anime_url is None and (source is None or src in source.split(",")):
                anime_url = url

    save_anilist_mapping(
        anilist_id,
        selected_anime,
        search_title=search_title,
        source=source,
        anime_url=anime_url,
        anime_urls=anime_urls,
    )
