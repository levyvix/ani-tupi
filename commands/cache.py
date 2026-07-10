"""Cache command handler for ani-tupi CLI."""

from __future__ import annotations

from utils.logging import get_logger

logger = get_logger(__name__)


def handle_clear_cache(target) -> None:
    """Clear scraper cache, optionally scoped to a single anime title.

    Args:
        target: ``True`` clears everything; a string clears only that title's
            cache (resolving its AniList id when possible for a precise prefix).
    """
    from services.anilist.discovery import auto_discover_anilist_id
    from services.anime.mappings import clear_anilist_mapping
    from utils.cache import clear_cache_all_with_mappings, clear_cache_by_prefix

    if target is True:
        clear_cache_all_with_mappings()
        logger.info("✅ Cache completamente limpo!")
        return

    # Try to discover AniList ID for more precise clearing
    anilist_id = auto_discover_anilist_id(target)
    if anilist_id:
        clear_cache_by_prefix(f":{anilist_id}:")
        clear_anilist_mapping(anilist_id)
        logger.info(f"✅ Cache de '{target}' (AniList ID {anilist_id}) foi limpo!")
    else:
        # Fallback: clear by title prefix
        clear_cache_by_prefix(f":{target}:")
        logger.info(f"✅ Cache de '{target}' foi limpo!")
