"""Episode selection logic for anime playback.

Handles determining which episode the user should start watching.
"""

from services.core import ui_bridge
from services.core.history_service import reset_history
from utils.logging import get_logger

logger = get_logger(__name__)


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
    from services.anime.awaiting_episodes import registry as awaiting_registry

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
) -> int | None:
    """Ask the user where to start and return the 0-indexed episode.

    Returns ``None`` when the user cancels or the episode is unavailable.
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
