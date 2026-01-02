"""Auto-discover AniList IDs for scraped anime using fuzzy matching.

When user does manual search without AniList, automatically match results
against AniList API to get anilist_id. This enables better caching and
metadata enrichment.
"""

from fuzzywuzzy import fuzz

from utils.cache_manager import get_cache


def auto_discover_anilist_id(scraper_title: str) -> int | None:
    """Auto-discover AniList ID via API using fuzzy matching.

    Tries to find best match in AniList for the scraper title.
    Only accepts strong matches (score >= threshold from config).
    Results are cached to avoid repeated API calls.

    Args:
        scraper_title: Anime title from scraper (possibly normalized)

    Returns:
        anilist_id if strong match found, None otherwise
    """
    from models.config import settings

    try:
        # Check cache first
        cache = get_cache()
        cache_key = f"anilist_id:{scraper_title.lower()}"

        cached = cache.get(cache_key)
        if cached is not None:
            return cached  # None is valid (means "not found")

        # Query AniList API
        from services.anilist_service import anilist_client

        results = anilist_client.search_anime(scraper_title)

        if not results:
            # Cache "not found" result for 1 day to avoid repeated API calls
            cache.set(cache_key, None, expire=86400)
            return None

        # Fuzzy match against scraper title
        best_match = None
        best_score = 0

        for anime in results:
            title_romaji = anime.get("title", {}).get("romaji", "") or ""
            title_english = anime.get("title", {}).get("english", "") or ""

            # Skip if no titles available
            if not title_romaji and not title_english:
                continue

            # Check both titles
            score_romaji = fuzz.ratio(
                scraper_title.lower(), title_romaji.lower()
            ) if title_romaji else 0
            score_english = fuzz.ratio(
                scraper_title.lower(), title_english.lower()
            ) if title_english else 0
            score = max(score_romaji, score_english)

            if score > best_score:
                best_score = score
                best_match = anime

        # Only accept if score >= threshold (default 90)
        threshold = settings.cache.anilist_fuzzy_threshold
        if best_score >= threshold and best_match:
            anilist_id = best_match.get("id")
            # Cache for 30 days
            cache.set(cache_key, anilist_id, expire=2592000)
            return anilist_id

        # Below threshold - cache as not found
        cache.set(cache_key, None, expire=86400)
        return None

    except Exception as e:
        print(f"⚠️  Erro ao buscar AniList ID para '{scraper_title}': {e}")
        return None


def get_anilist_id_from_title(anime_title: str) -> int | None:
    """Wrapper around auto_discover_anilist_id with simpler interface."""
    return auto_discover_anilist_id(anime_title)


def get_anilist_metadata(anilist_id: int) -> dict | None:
    """Fetch and cache complete AniList metadata (title, cover, etc).

    Args:
        anilist_id: AniList ID

    Returns:
        Dict with AniList data or None if fetch fails
    """
    cache = get_cache()
    cache_key = f"anilist_meta:{anilist_id}"

    # Check cache first
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from services.anilist_service import anilist_client

        # Fetch from AniList API
        metadata = anilist_client.get_anime_details(anilist_id)

        if metadata:
            # Cache for 30 days
            cache.set(cache_key, metadata, expire=2592000)
            return metadata

        return None

    except Exception as e:
        print(f"⚠️  Erro ao buscar metadata do AniList ID {anilist_id}: {e}")
        return None
