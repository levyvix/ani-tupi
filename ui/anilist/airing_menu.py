"""Airing episodes menu for upcoming/new anime episodes."""

import argparse

from ui.components import loading, menu_navigate
from utils.logging import get_logger

logger = get_logger(__name__)

# Dependency injection holders
anilist_client = None
airing_service_factory = None
run_anime_actions = None


def set_anilist_client(client):
    """Set the AniList client dependency."""
    global anilist_client
    anilist_client = client


def set_airing_service_factory(factory):
    """Set the airing service factory dependency."""
    global airing_service_factory
    airing_service_factory = factory


def set_run_anime_actions(callback):
    """Set the run_anime_actions callback."""
    global run_anime_actions
    run_anime_actions = callback


def get_search_title(title, display_title: str = "") -> str:
    """Get preferred title for search based on config.

    Args:
        title: AniListTitle object with romaji/english/native
        display_title: Fallback display title

    Returns:
        Title to use for searching (english or romaji based on config)
    """
    from models.config import settings

    if settings.anilist.prefer_english_title:
        return title.english or title.romaji or display_title
    return title.romaji or title.english or display_title


def format_time_until_airing(airing_at: int | None) -> str:
    """Format time until episode airs.

    Args:
        airing_at: Unix timestamp of episode air time

    Returns:
        Formatted string like "em 2h 30m" or "em 1d 5h"
    """
    if not airing_at:
        return "data desconhecida"

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).timestamp()
    seconds_until = int(airing_at - now)

    if seconds_until <= 0:
        return "agora"

    # Convert to human-readable format
    days = seconds_until // 86400
    hours = (seconds_until % 86400) // 3600
    minutes = (seconds_until % 3600) // 60

    if days > 0:
        return f"em {days}d {hours}h"
    elif hours > 0:
        return f"em {hours}h {minutes}m"
    else:
        return f"em {minutes}m"


def show_airing_episodes() -> None:
    """Show airing episodes from watching list with playback flow.

    Displays anime from user's watching list that have new episodes airing,
    sorted by urgency (most episodes behind first). User can select an anime
    to watch starting from their current progress.
    """
    while True:
        # Fetch airing episodes
        with loading("Carregando episódios em transmissão..."):
            service = airing_service_factory()
            airing_anime = service.get_watching_with_airing_episodes()

        if not airing_anime:
            logger.info("\n❌ Nenhum anime em transmissão na sua lista 'Assistindo'")
            input("\nPressione Enter para voltar...")
            return

        # Build menu options
        options = []
        anime_map = {}

        for entry in airing_anime:
            # Format: "(Z atrasado) Title - Próximo Ep X sai em Xh Ym, você viu Y ⭐Score%"
            if entry.airing_at is None and entry.episodes_behind > 0:
                status_str = (
                    f"Anime finalizado, você viu {entry.progress}/{entry.next_episode_number}"
                )
            else:
                time_until = format_time_until_airing(entry.airing_at)
                status_str = f"Próximo Ep {entry.next_episode_number} sai {time_until}, você viu {entry.progress}"

            prefix = f"({entry.episodes_behind} atrasado) " if entry.episodes_behind > 0 else ""

            display = f"{prefix}{entry.title} - {status_str}"

            if entry.average_score:
                display += f" ⭐{entry.average_score}%"

            options.append(display)
            anime_map[display] = entry

        # Show menu
        selection = menu_navigate(options, "🎬 Novos Episódios - Assistindo")

        if selection is None:
            return  # User cancelled, go back to main menu

        # Get selected anime
        entry = anime_map[selection]

        # Get anime info for search
        anime_info = anilist_client.get_anime_by_id(entry.anilist_id)
        if not anime_info:
            logger.info(f"\n❌ Erro ao buscar informações de '{entry.title}'")
            input("\nPressione Enter para tentar novamente...")
            continue

        # Format titles
        display_title = anilist_client.format_title(anime_info.title)
        search_title = get_search_title(anime_info.title, display_title)

        # Create args object for anilist_anime_flow
        args = argparse.Namespace(debug=False)

        # Show per-anime actions menu
        run_anime_actions(
            search_title,
            entry.anilist_id,
            args,
            anilist_progress=entry.progress,
            display_title=display_title,
            total_episodes=anime_info.episodes,
        )

        # After the actions menu, loop back to show airing episodes list again
