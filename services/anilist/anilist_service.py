"""AniList service layer - discovery, sequels, progress sync and scraper cache.

Transport lives in ``services.anilist.client``; this module holds the business
logic built on top of it.

Seções:
- Descoberta de IDs do AniList
- Cache de scraper indexado por AniList
- Sincronização de progresso
- Sequências
"""

from dataclasses import dataclass

from pydantic import ValidationError
from thefuzz import fuzz

from models.config import settings
from models.models import AniListAnime, AniListSearchResult, Status
from services.anilist.client import anilist_client
from services.core import ui_bridge
from utils.cache import get_cache, clear_cache_by_prefix
from utils.logging import get_logger
from utils.title_utils import normalize_title_for_search

__all__ = [
    "AniListDiscoveryResult",
    "auto_discover_anilist_id",
    "clear_discovery_cache",
    "discover_anilist_info",
    "get_anilist_id_from_title",
    "get_anilist_id_with_interactive_fallback",
    "get_anilist_metadata",
    "get_scraper_cache",
    "set_scraper_cache",
    "sync_anilist_progress",
    "offer_sequel_and_continue",
]

logger = get_logger(__name__)


# === Descoberta de IDs do AniList ===


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
                except (ValidationError, TypeError):
                    # In case of malformed list, treat as a cache miss
                    pass
            # Old format or malformed, fall through to re-fetch

        # Query AniList API
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

    except (ValidationError, TypeError, KeyError) as e:
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
        # Fetch from AniList API
        metadata = anilist_client.get_anime_by_id(anilist_id)

        if metadata:
            # Cache as dict for compatibility
            cache.set(cache_key, metadata.model_dump(), ttl=2592000)
            return metadata

        return None

    except (ValidationError, TypeError, KeyError) as e:
        logger.info(f"⚠️  Erro ao buscar metadata do AniList ID {anilist_id}: {e}")
        return None


@dataclass(frozen=True)
class AniListDiscoveryResult:
    """Immutable result from AniList discovery.

    Attributes:
        anilist_id: The AniList ID if found, None otherwise
        anilist_title: The formatted AniList title if found, None otherwise
        total_episodes: Total episodes from AniList if found, None otherwise
        found: Whether a match was found
        authenticated: Whether AniList was authenticated
    """

    anilist_id: int | None
    anilist_title: str | None
    total_episodes: int | None
    found: bool
    authenticated: bool


def discover_anilist_info(anime_title: str) -> AniListDiscoveryResult:
    """Discover AniList information for an anime title.

    This function:
    1. Checks if AniList is authenticated
    2. Normalizes the title (removes Portuguese suffixes like Dublado, Legendado)
    3. Searches AniList for matches
    4. Fetches metadata if found
    5. Returns an immutable result

    All errors are handled gracefully - the function never raises exceptions.

    Args:
        anime_title: The anime title to search for (may include suffixes)

    Returns:
        AniListDiscoveryResult with discovery results
    """
    # Check authentication first
    if not anilist_client.is_authenticated():
        return AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=False,
        )

    # Normalize title
    normalized_title = normalize_title_for_search(anime_title)

    # Handle empty title after normalization
    if not normalized_title:
        return AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=True,
        )

    # Search AniList
    try:
        anilist_results = auto_discover_anilist_id(normalized_title)
    except (ValidationError, TypeError, KeyError) as e:
        logger.warning("AniList search failed for '%s': %s", anime_title, e)
        return AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=True,
        )

    # No match found
    if not anilist_results:
        return AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=True,
        )

    # Get the best match (first result, sorted by score)
    best_match = anilist_results[0]
    anilist_id = best_match.anilist_id

    # Fetch metadata
    try:
        metadata = get_anilist_metadata(anilist_id)
    except (ValidationError, TypeError, KeyError) as e:
        logger.warning("AniList metadata fetch failed for ID %d: %s", anilist_id, e)
        # Return partial result with ID but no title/episodes
        return AniListDiscoveryResult(
            anilist_id=anilist_id,
            anilist_title=None,
            total_episodes=None,
            found=True,
            authenticated=True,
        )

    # Metadata not found
    if metadata is None:
        return AniListDiscoveryResult(
            anilist_id=anilist_id,
            anilist_title=None,
            total_episodes=None,
            found=True,
            authenticated=True,
        )

    # Format title and return complete result
    formatted_title = anilist_client.format_title(metadata.title)

    return AniListDiscoveryResult(
        anilist_id=anilist_id,
        anilist_title=formatted_title,
        total_episodes=metadata.episodes,
        found=True,
        authenticated=True,
    )


# === Cache de scraper indexado por AniList ===


def get_scraper_cache(anime_title: str):
    """Get cached scraper data for an anime.

    Args:
        anime_title: Normalized anime title

    Returns:
        ScraperCacheData with episode_urls and episode_count or None if not found
    """
    from models.models import ScraperCacheData

    # Check if episodes cache is enabled
    if not settings.cache.episodes_cache_enabled:
        return None

    try:
        # Try to discover AniList ID for better cache lookup
        anilist_id = get_anilist_id_from_title(anime_title)

        if anilist_id:
            cache_key = f"episodes:{anilist_id}"
        else:
            cache_key = f"episodes:{anime_title}"

        # Get from unified cache system
        cache_obj = get_cache()
        cached_urls = cache_obj.get(cache_key)

        if cached_urls and isinstance(cached_urls, list):
            return ScraperCacheData(
                episode_urls=cached_urls,  # type: ignore[arg-type]  # unified cache returns Any
                episode_count=len(cached_urls),
                timestamp=0,  # Not used in new system
            )

        return None

    except Exception:
        return None


def set_scraper_cache(anime_title: str, episode_count: int, episode_urls: list[str]) -> None:
    """Save scraper results to cache.

    Args:
        anime_title: Normalized anime title
        episode_count: Number of episodes found
        episode_urls: List of episode URLs
    """
    # Check if episodes cache is enabled
    if not settings.cache.episodes_cache_enabled:
        return

    try:
        cache_obj = get_cache()

        # Try to discover AniList ID for better cache key
        anilist_id = get_anilist_id_from_title(anime_title)

        if anilist_id:
            cache_key = f"episodes:{anilist_id}"
        else:
            cache_key = f"episodes:{anime_title}"

        # Save to unified cache system
        cache_obj.set(cache_key, episode_urls, ttl=settings.performance.default_ttl_hours * 3600)

    except Exception:
        pass  # Silent fail - cache is optional


# === Sincronização de progresso ===


def sync_anilist_progress(
    anilist_id: int,
    episode: int,
    num_episodes: int,
) -> None:
    """Sync watched episode progress to AniList and update status if needed.

    Handles PLANNING → CURRENT promotion, CURRENT → COMPLETED on last episode.
    Logs warnings on failure without raising.

    Args:
        anilist_id: AniList media ID
        episode: Episode number just watched (1-indexed)
        num_episodes: Total episodes available (from scrapers)
    """
    if not anilist_client.is_authenticated() or not anilist_id:
        return

    if not anilist_client.is_in_any_list(anilist_id):
        logger.info("📝 Adicionando à sua lista do AniList...")
        anilist_client.add_to_list(anilist_id, Status.CURRENT)
    else:
        entry = anilist_client.get_media_list_entry(anilist_id)
        if entry:
            if entry.status == "PLANNING":
                logger.info("📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                anilist_client.add_to_list(anilist_id, Status.CURRENT)
            elif entry.status == "CURRENT" and episode == num_episodes:
                logger.info("✅ Marcando como 'Completo'...")
                anilist_client.change_status(anilist_id, Status.COMPLETED)

    logger.info(f"🔄 Sincronizando progresso com AniList (Ep {episode})...")
    success = anilist_client.update_progress(anilist_id, episode)
    if success:
        logger.info("✅ Progresso salvo no AniList!")
    else:
        viewer = anilist_client.get_viewer_info()
        if not viewer:
            logger.info("⚠️  Token do AniList expirou")
            logger.info("   Execute: ani-tupi anilist auth")
        else:
            logger.info("⚠️  Não foi possível salvar no AniList (continuando...)")


# === Sequências ===


def _is_anime_released(anime_node) -> bool:
    """Check if an anime has started airing or is finished.

    Args:
        anime_node: AniListRelationNode with status and startDate

    Returns:
        True if anime has started airing (RELEASING or FINISHED), False if not yet released
    """
    if not anime_node:
        return True  # Assume released if no data

    # Check status field
    if hasattr(anime_node, "status"):
        status = anime_node.status
        if status == "NOT_YET_RELEASED":
            return False
        if status in ("RELEASING", "FINISHED"):
            return True

    return True  # Default to released if status is unknown


def offer_sequel_and_continue(
    anilist_id: int,
    args,
    current_episode: int | None = None,
    anilist_episodes: int | None = None,
) -> bool:
    """Check for sequels when last episode is watched and offer to continue.

    Args:
        anilist_id: AniList ID of the anime just watched
        args: Command line arguments
        current_episode: Current episode number (for checking if series is truly complete)
        anilist_episodes: Total episodes on AniList (if known)

    Returns:
        True if user accepted sequel and it started playback, False otherwise
    """
    # Import here to avoid circular dependency
    from services.anime.anilist_integration import anilist_anime_flow

    # Only offer sequels if authenticated
    if not anilist_client.is_authenticated():
        return False

    # `anilist_episodes` here is the count of episodes that have ACTUALLY aired
    # (see _available_episode_count). If the current source stopped before the
    # last aired episode, the gap already exists somewhere — hint at other
    # sources. We never claim certainty (the episode "should" be there) and we
    # stay silent when the aired count is unknown ("na dúvida, nem mostra nada").
    if anilist_episodes and current_episode:
        if current_episode < anilist_episodes:
            next_ep = current_episode + 1
            if anilist_episodes - current_episode == 1:
                logger.info(
                    f"\n💡 Sua fonte vai até o episódio {current_episode}, mas o episódio "
                    f"{next_ep} já foi lançado — deve estar disponível em outra fonte."
                )
            else:
                logger.info(
                    f"\n💡 Sua fonte vai até o episódio {current_episode}, mas os episódios "
                    f"{next_ep} a {anilist_episodes} já foram lançados — devem estar "
                    f"disponíveis em outras fontes."
                )
            return False

    # Get sequels from AniList
    sequels = anilist_client.get_sequels(anilist_id)

    if not sequels:
        return False  # No sequels found

    # Format sequel options
    if len(sequels) == 1:
        sequel = sequels[0]
        sequel_title = anilist_client.format_title(sequel.title)
        is_released = _is_anime_released(sequel)

        # Single sequel: offer multiple options (but suggest Planning if not yet released)
        if is_released:
            menu_options = [
                "▶️ Procurar episódios",
                "📋 Adicionar à 'Planejo Assistir'",
                "❌ Não, parar aqui",
            ]
        else:
            menu_options = ["📋 Adicionar à 'Planejo Assistir'", "❌ Não, parar aqui"]
            sequel_title += " ⏳ (ainda não lançado)"

        choice = ui_bridge.menu_navigate(
            menu_options,
            msg=f"Deseja continuar com a sequência?\n\n→ {sequel_title}",
        )

        if choice == "▶️ Procurar episódios":
            # Get sequel info and start playback
            anilist_anime_flow(
                sequel_title,
                sequel.id,
                args,
                anilist_progress=0,
                display_title=sequel_title,
                total_episodes=sequel.episodes,
            )
            return True
        elif choice == "📋 Adicionar à 'Planejo Assistir'":
            # Add to Planning list without searching for episodes
            success = anilist_client.add_to_list(sequel.id, Status.PLANNING)
            if success:
                logger.info(f"✅ {sequel_title} adicionado à sua lista de 'Planejo Assistir'!")
            else:
                logger.info(f"❌ Erro ao adicionar {sequel_title} à sua lista.")
            return False
    else:
        # Multiple sequels: let user choose and then ask what to do
        sequel_options = []
        for s in sequels:
            title = anilist_client.format_title(s.title)
            is_released = _is_anime_released(s)
            if not is_released:
                title += " ⏳"
            sequel_options.append(title)

        choice = ui_bridge.menu_navigate(
            sequel_options + ["❌ Não, parar aqui"],
            msg="Qual sequência deseja assistir?",
        )

        if choice and choice != "❌ Não, parar aqui":
            # Find selected sequel (removing the ⏳ indicator if present)
            choice_clean = choice.replace(" ⏳", "")
            selected_sequel = next(
                (s for s in sequels if anilist_client.format_title(s.title) == choice_clean),
                None,
            )
            if selected_sequel:
                sequel_title = anilist_client.format_title(selected_sequel.title)
                is_released = _is_anime_released(selected_sequel)

                # Ask what user wants to do (but suggest Planning if not yet released)
                if is_released:
                    action_options = [
                        "▶️ Procurar episódios",
                        "📋 Adicionar à 'Planejo Assistir'",
                        "❌ Cancelar",
                    ]
                else:
                    action_options = [
                        "📋 Adicionar à 'Planejo Assistir'",
                        "❌ Cancelar",
                    ]
                    sequel_title += " ⏳ (ainda não lançado)"

                action_choice = ui_bridge.menu_navigate(
                    action_options,
                    msg=f"O que deseja fazer com {sequel_title}?",
                )

                if action_choice == "▶️ Procurar episódios":
                    anilist_anime_flow(
                        sequel_title,
                        selected_sequel.id,
                        args,
                        anilist_progress=0,
                        display_title=sequel_title,
                        total_episodes=selected_sequel.episodes,
                    )
                    return True
                elif action_choice == "📋 Adicionar à 'Planejo Assistir'":
                    # Add to Planning list without searching for episodes
                    success = anilist_client.add_to_list(selected_sequel.id, Status.PLANNING)
                    if success:
                        logger.info(
                            f"\n✅ {sequel_title} adicionado à sua lista de 'Planejo Assistir'!"
                        )
                    else:
                        logger.info(f"❌ Erro ao adicionar {sequel_title} à sua lista.")
                    return False

    return False
