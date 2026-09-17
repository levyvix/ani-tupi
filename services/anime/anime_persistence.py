"""Anime persistence - AniList mappings and the user's source/language choice.

Seções:
- Mapeamentos AniList
- Escolha de fonte do usuário
"""

from models.config import get_data_path
from models.download import AiringSourceBinding, AiringSourceCandidate
from services.anime.airing_sources import AiringSourceStore
from services.anime.source_contexts import (
    binding_from_source_candidates,
    source_candidates_for,
    source_names_for,
)
from services.repository import rep
from utils.exceptions import PersistenceError
from utils.logging import get_logger
from utils.persistence import JSONStore

__all__ = [
    "clear_anilist_mapping",
    "load_anilist_mapping",
    "load_anilist_search_title",
    "load_anilist_source_bindings",
    "load_anilist_urls",
    "load_language_preference",
    "persist_anime_choice",
    "save_anilist_mapping",
    "save_language_preference",
]

logger = get_logger(__name__)


# === Mapeamentos AniList ===


HISTORY_PATH = get_data_path()

# AniList to scraper title mappings cache
_anilist_mappings_store = JSONStore(HISTORY_PATH / "anilist_mappings.json")


def load_anilist_mapping(
    anilist_id: int,
) -> tuple[str | None, str | None, str | None]:
    """Load saved scraper title, source, and URL for an AniList ID.

    Args:
        anilist_id: The AniList anime ID

    Returns:
        Tuple of (scraper_title, source, anime_url) or (None, None, None) if not found
    """
    shared = AiringSourceStore().effective(anilist_id).binding
    mapping = _anilist_mappings_store.get(str(anilist_id))
    if shared is not None:
        return shared.title, source_names_for(shared), shared.anime_url
    # Handle both old format (string) and new format (dict)
    if isinstance(mapping, dict):
        return (
            mapping.get("scraper_title"),
            mapping.get("source"),
            mapping.get("anime_url"),
        )
    # Old format only has title, no source or URL
    return mapping, None, None


def load_anilist_urls(anilist_id: int) -> dict[str, str]:
    """Load all saved anime URLs (source -> URL mapping) for an AniList ID.

    Args:
        anilist_id: The AniList anime ID

    Returns:
        Dict mapping sources to URLs (e.g., {"animefire": "https://...", "animesdigital": "https://..."})
    """
    shared = AiringSourceStore().effective(anilist_id).binding
    if shared is not None:
        return {
            candidate.source: candidate.anime_url
            for candidate in [
                AiringSourceCandidate(
                    title=shared.title,
                    source=shared.source,
                    anime_url=shared.anime_url,
                    params=shared.params,
                    variant=shared.variant,
                ),
                *shared.alternatives,
            ]
        }

    mapping = _anilist_mappings_store.get(str(anilist_id))
    if isinstance(mapping, dict):
        return mapping.get("anime_urls", {})
    return {}


def load_anilist_source_bindings(anilist_id: int) -> list[AiringSourceBinding]:
    """Load all shared source contexts in playback fallback order."""
    shared = AiringSourceStore().effective(anilist_id).binding
    if shared is None:
        return []
    return [
        shared,
        *[
            AiringSourceBinding(
                title=candidate.title,
                source=candidate.source,
                anime_url=candidate.anime_url,
                params=candidate.params,
                variant=candidate.variant,
            )
            for candidate in shared.alternatives
        ],
    ]


def load_anilist_search_title(anilist_id: int) -> str | None:
    """Load the original search/display title used for an AniList ID.

    Args:
        anilist_id: The AniList anime ID

    Returns:
        Original search title or None if not found
    """
    mapping = _anilist_mappings_store.get(str(anilist_id))
    # Only new format (dict) has search_title
    if isinstance(mapping, dict):
        return mapping.get("search_title")
    return None


def save_anilist_mapping(
    anilist_id: int,
    scraper_title: str,
    search_title: str | None = None,
    source: str | None = None,
    anime_url: str | None = None,
    language_choice: str | None = None,
    anime_urls: dict[str, str] | None = None,
    params: dict | None = None,
    source_candidates: list[AiringSourceCandidate] | None = None,
) -> None:
    """Save scraper title choice, search title, source, URL(s), and language preference for an AniList ID.

    Args:
        anilist_id: The AniList ID
        scraper_title: The selected anime title from scraper
        search_title: The original search/display title used to find it
        source: The scraper source (e.g., "animefire", "animesdigital")
        anime_url: The anime page URL from the scraper (e.g., https://animefire.io/animes/...)
        language_choice: The language chosen ("romaji" or "english")
        anime_urls: Dict mapping sources to URLs (e.g., {"animefire": "https://...", "animesdigital": "https://..."})
    """
    try:
        mapping_id = str(anilist_id)
        # Preserve existing values if not provided
        existing = _anilist_mappings_store.get(mapping_id, {})
        if isinstance(existing, str):
            # Migrate old format to new format
            existing = {"scraper_title": existing}

        # Merge anime_urls with existing ones if not provided
        merged_urls = existing.get("anime_urls", {})
        if anime_urls:
            merged_urls.update(anime_urls)
        elif anime_url and source:
            # If single URL provided, add to urls dict
            merged_urls[source] = anime_url

        _anilist_mappings_store.set(
            mapping_id,
            {
                "scraper_title": scraper_title,
                "search_title": search_title or existing.get("search_title"),
                "source": source or existing.get("source"),
                "anime_url": anime_url or existing.get("anime_url"),
                "anime_urls": merged_urls,
                "language_choice": language_choice or existing.get("language_choice"),
            },
        )
        if anilist_id > 0 and source and source.lower() not in {"local", "unknown", "mixed"}:
            candidates = source_candidates or []
            if not candidates and "," not in source and anime_url:
                candidates = [
                    AiringSourceCandidate(
                        title=scraper_title,
                        source=source,
                        anime_url=anime_url,
                        params=params or {},
                    )
                ]
            if not candidates:
                return
            binding = binding_from_source_candidates(scraper_title, candidates)
            if binding is None:
                return
            AiringSourceStore().save_binding(
                anilist_id,
                binding,
            )
    except PersistenceError as e:
        logger.error(f"Failed to save AniList mapping: {e}")


def load_language_preference(anilist_id: int) -> str | None:
    """Load the language preference (romaji or english) for an AniList ID.

    Args:
        anilist_id: The AniList anime ID

    Returns:
        "romaji", "english", or None if not found
    """
    mapping = _anilist_mappings_store.get(str(anilist_id))
    if isinstance(mapping, dict):
        return mapping.get("language_choice")
    return None


def save_language_preference(anilist_id: int, language_choice: str) -> None:
    """Save the language preference for an AniList ID.

    Args:
        anilist_id: The AniList anime ID
        language_choice: "romaji" or "english"
    """
    try:
        mapping_id = str(anilist_id)
        existing = _anilist_mappings_store.get(mapping_id, {})
        if isinstance(existing, str):
            existing = {"scraper_title": existing}

        existing["language_choice"] = language_choice
        _anilist_mappings_store.set(mapping_id, existing)
    except PersistenceError as e:
        logger.error(f"Failed to save language preference: {e}")


def clear_anilist_mapping(anilist_id: int | None = None) -> None:
    """Clear AniList mappings and their shared source bindings."""
    try:
        from models.config import get_data_path

        store = JSONStore(get_data_path() / "anilist_mappings.json")
        if anilist_id is None:
            store.clear()
            AiringSourceStore().clear_all()
        else:
            store.delete(str(anilist_id))
            AiringSourceStore().clear_configured(anilist_id)
    except PersistenceError as e:
        logger.error(f"Failed to clear AniList mappings: {e}")


# === Escolha de fonte do usuário ===


def persist_anime_choice(
    anilist_id: int,
    selected_anime: str,
    search_title: str,
    source: str | None,
) -> None:
    """Save the resolved anime choice (title, source, URLs) for next time."""
    anime_url = None
    anime_urls: dict[str, str] = {}
    selected_params: dict | None = None
    source_candidates: list[AiringSourceCandidate] = []

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
        all_candidates = source_candidates_for(rep, repo_title)
        source_candidates = source_candidates_for(rep, repo_title, source)
        anime_urls = {candidate.source: candidate.anime_url for candidate in all_candidates}
        if source_candidates:
            primary = source_candidates[0]
            anime_url = primary.anime_url
            selected_params = primary.params

    save_anilist_mapping(
        anilist_id,
        selected_anime,
        search_title=search_title,
        source=source,
        anime_url=anime_url,
        anime_urls=anime_urls,
        params=selected_params,
        source_candidates=source_candidates,
    )
