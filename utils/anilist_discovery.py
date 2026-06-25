"""Auto-discover AniList IDs for scraped anime using fuzzy matching.

When user does manual search without AniList, automatically match results
against AniList API to get anilist_id. This enables better caching and
metadata enrichment.
"""

from thefuzz import fuzz

from models.models import AniListAnime, AniListSearchResult
from models.config import settings
from utils.cache_manager import get_cache, clear_cache_by_prefix
from utils.logging import get_logger

logger = get_logger(__name__)


def auto_discover_anilist_id(scraper_title: str) -> list[AniListSearchResult]:
    """Auto-discover AniList ID via API using fuzzy matching.

    Tries to find best match in AniList for the scraper title.
    Only accepts strong matches (score >= threshold from config).
    Results are cached to avoid repeated API calls.

    Args:
        scraper_title: Anime title from scraper (possibly normalized)

    Returns:
        A list of AniListSearchResult, sorted by score descending.
    """

    try:
        # Check cache first
        cache = get_cache()
        cache_key = f"anilist_id:{scraper_title.lower()}"

        cached = cache.get(cache_key)
        if cached is not None:
            # Handle backward compatibility with old cache format (int)
            if isinstance(cached, list):
                try:
                    return [AniListSearchResult(**item) for item in cached]
                except TypeError:
                    # In case of malformed list, treat as a cache miss
                    pass
            # Old format or malformed, fall through to re-fetch

        # Query AniList API
        from services.anilist_service import anilist_client

        results = anilist_client.search_anime(scraper_title)

        if not results:
            # Cache "not found" result for 1 day to avoid repeated API calls
            cache.set(cache_key, [], ttl=86400)
            return []

        # Fuzzy match against scraper title
        matches = []
        for anime in results:
            title_romaji = anime.title.romaji or ""
            title_english = anime.title.english or ""

            # Skip if no titles available
            if not title_romaji and not title_english:
                continue

            # Check both titles using token_sort_ratio for better word order tolerance
            score_romaji = (
                fuzz.token_sort_ratio(scraper_title.lower(), title_romaji.lower())
                if title_romaji
                else 0
            )
            score_english = (
                fuzz.token_sort_ratio(scraper_title.lower(), title_english.lower())
                if title_english
                else 0
            )
            score = max(score_romaji, score_english)

            threshold = settings.cache.anilist_fuzzy_threshold
            if score >= threshold:
                matches.append(
                    AniListSearchResult(
                        anilist_id=anime.id,
                        score=score,
                        title=title_romaji or title_english,
                    )
                )

        # Sort by score descending
        sorted_matches = sorted(matches, key=lambda x: x.score, reverse=True)

        # Cache for 30 days
        cache.set(cache_key, [match.model_dump() for match in sorted_matches], ttl=2592000)
        return sorted_matches

    except Exception as e:
        logger.info(f"⚠️  Erro ao buscar AniList ID para '{scraper_title}': {e}")
        return []


def get_anilist_id_from_title(anime_title: str) -> int | None:
    """Wrapper around auto_discover_anilist_id for single best match."""
    results = auto_discover_anilist_id(anime_title)
    if results:
        return results[0].anilist_id
    return None


def get_anilist_id_with_interactive_fallback(
    anime_title: str,
    strict_threshold: int = 95,
) -> int | None:
    """Try strict discovery (95%), show list if below threshold.

    For local library titles that don't match perfectly, show user a list of
    candidates to choose the correct match. Caches the user's choice for
    future episodes of the same anime.

    Args:
        anime_title: Title to discover (e.g., "Chainsaw Man Dublado")
        strict_threshold: Fuzzy match score threshold for automatic match (0-100)

    Returns:
        AniList ID if found/selected, None otherwise
    """
    # Get all discovery results (sorted by score)
    results = auto_discover_anilist_id(anime_title)

    if not results:
        logger.info(f"❌ Não foi possível encontrar '{anime_title}' no AniList")
        return None

    # If best match >= threshold, use it automatically
    best_match = results[0]
    if best_match.score >= strict_threshold:
        return best_match.anilist_id

    # Below threshold: show list for user to choose
    logger.info(f"\n🔍 Match parcial encontrado: {best_match.title} ({best_match.score}%)")
    logger.info("   Escolha a correspondência correta:\n")

    from ui.components import menu_navigate

    # Create display options with scores
    match_options = [f"{r.title} ({r.score}%)" for r in results[:5]]
    match_options.append("⏭️  Nenhuma das opções (pular sync)")

    selected = menu_navigate(match_options, msg="Qual é o anime correto?")

    if not selected or "Nenhuma" in selected:
        return None

    # Extract selected result by index
    selected_idx = match_options.index(selected)
    chosen = results[selected_idx]

    logger.info(f"✅ Mapeado: {chosen.title}")
    logger.info(f"   🆔 ID AniList: {chosen.anilist_id}")

    # Validate anime exists before caching
    from services.anilist_service import anilist_client

    try:
        anime_info = anilist_client.get_anime_by_id(chosen.anilist_id)
        if not anime_info:
            logger.info(f"⚠️  Aviso: Anime ID {chosen.anilist_id} não encontrado no AniList")
            logger.info("   Sincronização pode falhar. Tente novamente com outro título.")
            return chosen.anilist_id  # Still return it, but warn user

        # Valid anime, cache for future episodes
        cache = get_cache()
        cache_key = f"anilist_id:{anime_title.lower()}"
        cache.set(cache_key, [chosen.model_dump()], ttl=2592000)  # 30 days
        logger.info("   ✅ Cache salvo por 30 dias")

    except Exception as e:
        logger.info(f"⚠️  Não foi possível validar anime ID: {e}")
        # Still cache it anyway, but user is warned

    return chosen.anilist_id


def clear_discovery_cache(anime_title: str | None = None) -> int:
    """Clear cached AniList ID mappings.

    Args:
        anime_title: Specific title to clear, or None to clear all

    Returns:
        Number of entries cleared
    """
    cache = get_cache()

    if anime_title:
        # Clear specific title
        cache_key = f"anilist_id:{anime_title.lower()}"
        try:
            cache.delete(cache_key)
            return 1
        except Exception:
            return 0

    # Clear all anilist_id entries using prefix-based clearing
    clear_cache_by_prefix("anilist_id:")
    # Return a non-zero sentinel since we can't count keys cleared
    return 1


def get_anilist_metadata(anilist_id: int) -> AniListAnime | None:
    """Fetch and cache complete AniList metadata (title, cover, etc).

    Args:
        anilist_id: AniList ID

    Returns:
        AniListAnime with metadata or None if fetch fails
    """

    cache = get_cache()
    cache_key = f"anilist_meta:{anilist_id}"

    # Check cache first
    cached = cache.get(cache_key)
    if cached is not None:
        # Handle both dict (cached) and AniListAnime (new format)
        if isinstance(cached, dict):
            return AniListAnime.model_validate(cached)
        if isinstance(cached, AniListAnime):
            return cached
        # Invalid cache entry - fall through to re-fetch

    try:
        from services.anilist_service import anilist_client

        # Fetch from AniList API
        metadata = anilist_client.get_anime_by_id(anilist_id)

        if metadata:
            # Cache as dict for compatibility
            cache.set(cache_key, metadata.model_dump(), ttl=2592000)
            return metadata

        return None

    except Exception as e:
        logger.info(f"⚠️  Erro ao buscar metadata do AniList ID {anilist_id}: {e}")
        return None
