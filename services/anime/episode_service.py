"""Episode service - loading, selection, context, URL patterns and awaiting.

Seções:
- Padrão de URL de episódio
- Registro de episódios aguardados
- Contexto de navegação
- Seleção de episódio
- Carregamento da lista de episódios
"""

import json
import re

from models import EpisodeContext
from models.config import get_data_path
from scrapers.plugins.utils import http_head_with_fallback
from services.anilist.anilist_service import get_scraper_cache, set_scraper_cache
from services.anime.mappings import load_anilist_urls
from services.core import ui_bridge
from services.core.history_service import reset_history
from services.repository import rep
from utils.logging import get_logger

__all__ = [
    # Padrão de URL de episódio
    "derive_episode_url",
    "detect_episode_pattern",
    "validate_episode_url",
    # Registro de episódios aguardados
    "AwaitingEpisodeRegistry",
    "registry",
    # Contexto de navegação
    "get_next_episode_context",
    # Seleção de episódio
    "SWITCH_SOURCE",
    # Carregamento da lista de episódios
    "HISTORY_PATH",
]

logger = get_logger(__name__)


# === Padrão de URL de episódio ===


_EPISODE_PATTERN = re.compile(r"/(\d{1,3})\.mp4/")


def detect_episode_pattern(url: str) -> dict | None:
    """Detect if URL contains a substitutable episode number.

    Args:
        url: Video URL to inspect.

    Returns:
        Dict with ``episode`` (int), ``padded`` (bool), ``width`` (int),
        ``match_start`` and ``match_end`` (indices of the digit group), or
        ``None`` if the pattern is not found.
    """
    match = _EPISODE_PATTERN.search(url)
    if not match:
        return None
    raw = match.group(1)
    padded = raw.startswith("0") and len(raw) > 1
    return {
        "episode": int(raw),
        "padded": padded,
        "width": len(raw) if padded else 0,
        "match_start": match.start(1),
        "match_end": match.end(1),
    }


def derive_episode_url(url: str, target_episode: int) -> str | None:
    """Derive URL for *target_episode* by substituting the episode number.

    Zero-padding is preserved: if the original number was ``08`` the derived
    number will be ``09``; if it was ``11`` (no padding) it becomes ``12``.

    Args:
        url: Current video URL containing the episode number.
        target_episode: Episode number to derive the URL for.

    Returns:
        New URL with the episode number replaced, or ``None`` if the pattern
        is not found in *url*.
    """
    info = detect_episode_pattern(url)
    if info is None:
        return None
    if info["padded"]:
        new_ep = str(target_episode).zfill(info["width"])
    else:
        new_ep = str(target_episode)
    return url[: info["match_start"]] + new_ep + url[info["match_end"] :]


def validate_episode_url(url: str, timeout: float = 5.0) -> bool:
    """Check whether *url* resolves to a valid episode via a HEAD request.

    Args:
        url: URL to validate.
        timeout: Request timeout in seconds.

    Returns:
        ``True`` if the server returns a 2xx status code, ``False`` otherwise.
    """
    logger.info(f"[URL-PATTERN] HEAD {url[:80]}{'...' if len(url) > 80 else ''}")
    try:
        response = http_head_with_fallback(
            url,
            timeout=timeout,
            follow_redirects=True,
        )
        logger.info(
            f"[URL-PATTERN] → {response.status_code} {'✅ HIT' if response.is_success else '❌ MISS'}"
        )
        return response.is_success
    except Exception as exc:
        logger.info(f"[URL-PATTERN] → ERROR: {exc}")
        logger.debug("validate_episode_url failed for %s: %s", url, exc)
        return False


# === Registro de episódios aguardados ===


class AwaitingEpisodeRegistry:
    """Maps ``anime_title -> {episode_number: episode_page_url}``.

    Instances are cheap; a shared module-level instance (``registry``) is used
    by the running application, while tests can create isolated instances.
    """

    def __init__(self) -> None:
        self._urls: dict[str, dict[int, str]] = {}

    def set(self, anime_title: str, episode_number: int, episode_url: str) -> None:
        """Record a direct episode-page URL for an awaiting episode."""
        self._urls.setdefault(anime_title, {})[episode_number] = episode_url

    def get(self, anime_title: str, episode_number: int) -> str | None:
        """Return the recorded episode-page URL, or ``None`` if not awaiting."""
        return self._urls.get(anime_title, {}).get(episode_number)

    def clear(self, anime_title: str) -> None:
        """Drop any awaiting URLs recorded for ``anime_title``."""
        self._urls.pop(anime_title, None)


# Shared instance used by the application flows.
registry = AwaitingEpisodeRegistry()


# === Contexto de navegação ===


def get_next_episode_context(
    anime_title: str,
    current_episode: int,
) -> EpisodeContext | None:
    """Get episode context for next episode (used by IPC handlers).

    Args:
        anime_title: Name of anime
        current_episode: Current episode number (1-indexed)

    Returns:
        EpisodeContext with url, title, episode info, or None if no next episode
    """

    episode_list = rep.get_episode_list(anime_title)
    if not episode_list:
        return None

    # Convert to 0-based index
    next_idx = current_episode  # Already incremented from IPC
    if next_idx >= len(episode_list):
        # No next episode available
        return None

    try:
        next_episode_title = episode_list[next_idx]
        # Get URL from repository if available
        url_and_source = rep.get_episode_url_and_source(anime_title, next_idx + 1)
        next_url = url_and_source[0] if url_and_source else None
        if not next_url:
            logger.info("Nao foi possivel encontrar a url do proximo episodio")
            return None

        return EpisodeContext(
            url=next_url,
            title=next_episode_title,
            episode=next_idx + 1,  # Convert back to 1-indexed
            total=len(episode_list),
        )
    except (IndexError, KeyError):
        return None


# === Seleção de episódio ===


# Sentinel returned by ``_resolve_start_episode_idx`` when the user asks to
# switch sources. The caller owns the switch flow (it has args/anilist_id/etc.).
SWITCH_SOURCE = object()


def _build_continue_menu(
    selected_anime: str,
    max_progress: int,
    anilist_progress: int,
    local_progress: int,
    episode_list: list,
    total_episodes: int | None,
    scraper_episode_count: int | None,
) -> tuple[list[str], dict[str, int | None], str]:
    """Build the "de onde continuar" menu options and message."""
    options: list[str] = []
    option_to_idx: dict[str, int | None] = {}

    progress_source = ""
    if max_progress == anilist_progress and max_progress == local_progress:
        progress_source = "AniList + Local"
    elif max_progress == anilist_progress:
        progress_source = "AniList"
    elif max_progress == local_progress:
        progress_source = "Local"

    if max_progress < len(episode_list):
        next_ep = f"⏭️  Episódio {max_progress + 1} (próximo)"
        options.append(next_ep)
        option_to_idx[next_ep] = max_progress
    elif total_episodes and max_progress < total_episodes:
        next_ep = f"⏭️  Episódio {max_progress + 1} (aguardando)"
        options.append(next_ep)
        option_to_idx[next_ep] = None

    current_ep = f"▶️  Episódio {max_progress} ({progress_source})"
    options.append(current_ep)
    option_to_idx[current_ep] = max_progress - 1

    if max_progress > 1:
        prev_ep = f"◀️  Episódio {max_progress - 1} (anterior)"
        options.append(prev_ep)
        option_to_idx[prev_ep] = max_progress - 2

    options.append("📋 Escolher outro episódio")
    options.append("🔄 Começar do zero")
    options.append("🔀 Trocar fonte")

    menu_msg = f"{selected_anime} - De onde quer continuar?"
    if total_episodes and scraper_episode_count:
        menu_msg += f"\n📊 {scraper_episode_count} eps disponíveis / {total_episodes} total"
    elif scraper_episode_count:
        menu_msg += f"\n📊 {scraper_episode_count} eps disponíveis"

    return options, option_to_idx, menu_msg


def _find_awaiting_episode_idx(
    selected_anime: str,
    target_ep_num: int,
) -> int | None:
    """Search AnimesDigital's homepage for a freshly-released episode.

    Records the direct episode URL in the awaiting-episode registry so the
    playback layer can extract it. Returns the 0-indexed episode index, or
    ``None`` when the episode could not be found.
    """
    from services.repository import rep
    from services.anime.episode_service import registry as awaiting_registry

    logger.info(f"🔍 Buscando episódio {target_ep_num} no AnimesDigital...")

    try:
        with ui_bridge.loading("Procurando novo episódio..."):
            results = rep.search_homepage_incremental("animesdigital", selected_anime)

        if not results:
            logger.info(
                f"\n❌ Episódio {target_ep_num} ainda não disponível nos scrapers ou "
                "no AnimesDigital."
            )
            ui_bridge.prompt("\nPressione Enter para voltar...")
            return None

        matching_episodes = [ep for ep in results if ep["episode_number"] == target_ep_num]
        if not matching_episodes:
            logger.info(f"\n❌ Episódio {target_ep_num} não encontrado no AnimesDigital.")
            ui_bridge.prompt("\nPressione Enter para voltar...")
            return None

        episode = matching_episodes[0]
        logger.info(f"✅ Episódio {target_ep_num} encontrado no AnimesDigital!")
        logger.info(f"   URL: {episode['episode_url'][:80]}...")

        awaiting_registry.set(selected_anime, target_ep_num, episode["episode_url"])
        return target_ep_num - 1

    except (OSError, ConnectionError, TimeoutError) as e:
        logger.warning(f"⚠️  Erro de rede ao buscar no AnimesDigital: {e!r}")
        logger.info(f"Episódio {target_ep_num} ainda não disponível nos scrapers.")
        ui_bridge.prompt("\nPressione Enter para voltar...")
        return None
    except Exception as e:
        logger.warning(
            f"⚠️  Erro inesperado ao buscar no AnimesDigital: {e!r}",
            exc_info=True,
        )
        logger.info(f"Episódio {target_ep_num} ainda não disponível nos scrapers.")
        ui_bridge.prompt("\nPressione Enter para voltar...")
        return None


def _resolve_start_episode_idx(
    selected_anime: str,
    episode_list: list,
    anilist_progress: int,
    local_progress: int,
    total_episodes: int | None,
    scraper_episode_count: int | None,
) -> int | object | None:
    """Ask the user where to start and return the 0-indexed episode.

    Returns ``None`` when the user cancels or the episode is unavailable, or
    the ``SWITCH_SOURCE`` sentinel when the user wants to switch sources.
    """
    max_progress = max(anilist_progress, local_progress)

    if not (0 < max_progress <= len(episode_list)):
        return ui_bridge.menu_navigate_episodes(episode_list)

    options, option_to_idx, menu_msg = _build_continue_menu(
        selected_anime,
        max_progress,
        anilist_progress,
        local_progress,
        episode_list,
        total_episodes,
        scraper_episode_count,
    )

    choice = ui_bridge.menu_navigate(options, msg=menu_msg)

    if not choice:
        return None

    if choice == "🔀 Trocar fonte":
        return SWITCH_SOURCE

    if choice == "📋 Escolher outro episódio":
        return ui_bridge.menu_navigate_episodes(episode_list)

    if choice == "🔄 Começar do zero":
        confirm_reset = ui_bridge.menu_navigate(
            ["✅ Sim, resetar", "❌ Cancelar"],
            msg="Tem certeza que quer começar do zero? Seu progresso será perdido.",
        )
        if confirm_reset == "✅ Sim, resetar":
            reset_history(selected_anime)
            logger.info("✅ Histórico resetado! Começando do episódio 1...")
            return 0
        return None

    episode_idx = option_to_idx[choice]
    if episode_idx is None:
        return _find_awaiting_episode_idx(selected_anime, max_progress + 1)
    return episode_idx


# === Carregamento da lista de episódios ===


# Use centralized path function from config
HISTORY_PATH = get_data_path()


def _read_local_progress(selected_anime: str) -> int:
    """Return the next episode to watch based on local history (0 if none)."""
    try:
        history_file = HISTORY_PATH / "history.json"
        with history_file.open() as f:
            history_data = json.load(f)
            if selected_anime in history_data:
                return history_data[selected_anime][1] + 1
    except (OSError, KeyError, IndexError):
        pass  # No local history
    return 0


def _load_episode_list(
    selected_anime: str,
    saved_title: str | None,
    saved_source: str | None,
    saved_url: str | None,
    anilist_id: int,
) -> tuple[list | None, int]:
    """Load the episode list from cache or by scraping.

    Returns ``(episode_list, scraper_episode_count)``. ``episode_list`` is
    ``None`` when loading failed (no episodes could be scraped).
    """
    cache_data = get_scraper_cache(selected_anime)

    if cache_data:
        logger.info(f"ℹ️  Usando cache ({cache_data.episode_count} eps disponíveis)")
        rep.search_episodes(selected_anime)
        return cache_data.episode_urls, cache_data.episode_count

    if selected_anime == saved_title:
        saved_urls = load_anilist_urls(anilist_id) if anilist_id else {}
        if saved_urls:
            sources_list = ", ".join(sorted(saved_urls.keys()))
            logger.info(f"📺 Carregando '{selected_anime}' da fonte {sources_list}...")
            for src, url in saved_urls.items():
                rep.add_anime(selected_anime, url, src)
        elif saved_url and saved_source:
            logger.info(f"📺 Carregando '{selected_anime}' da fonte {saved_source}...")
            rep.add_anime(selected_anime, saved_url, saved_source)

    with ui_bridge.loading("Carregando episódios..."):
        rep.search_episodes(selected_anime)
    episode_list = rep.get_episode_list(selected_anime)
    scraper_episode_count = len(episode_list)

    if not episode_list:
        logger.info(
            "\n❌ Nenhum episódio carregado — todos os scrapers falharam (timeout ou erro de rede)."
        )
        logger.info("   Tente novamente em alguns instantes.")
        ui_bridge.prompt("\nPressione Enter para voltar...")
        return None, 0

    set_scraper_cache(selected_anime, scraper_episode_count, episode_list)
    return episode_list, scraper_episode_count
