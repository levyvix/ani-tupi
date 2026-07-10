"""AniList integration command handler.

This module handles:
- Authentication with AniList
- Browsing trending anime and user lists
- Watching anime via AniList with progress sync
"""

import webbrowser

from rich.console import Console
from rich.prompt import Confirm

from services import anime_service
from ui import anilist_menus
from ui.anilist_menus import (
    anilist_main_menu,
    anime_actions_menu,
    authenticate_flow,
    status_select_menu,
)
from ui.components import loading, pause, show_error, show_info, show_success, show_warning

_console = Console()


def _wire_anilist_menus() -> None:
    """Inject runtime dependencies into the pure ``ui.anilist_menus`` layer.

    Keeps ``ui`` free of ``services``/``commands`` imports (breaks the
    dependency cycle) while preserving production behaviour.
    """
    from services.anilist import anilist_client
    from services.anime.airing_episodes_service import AiringEpisodesService
    from commands.local_anime import handle_local_library_playback

    anilist_menus.configure(
        client=anilist_client,
        anime_flow=anime_service.anilist_anime_flow,
        anime_actions=run_anime_actions,
        airing_service=AiringEpisodesService,
        local_library_playback=handle_local_library_playback,
    )


def _handle_anilist_download(anime_title: str, total_episodes: int | None) -> None:
    """Handle download action from the anime actions menu.

    Prompts for an episode range and downloads via AnimeDownloadService,
    without requiring a PlaybackContext.

    Args:
        anime_title: Title used to search scrapers
        total_episodes: Total episodes available (None/<=0 aborts)
    """
    from services.anime.download_service import AnimeDownloadService
    from services.anime.playback_service import get_episode_url_and_source
    from utils.range_parser import RangeParseError

    if not total_episodes or total_episodes <= 0:
        show_warning("Número total de episódios desconhecido. Não é possível baixar.")
        pause()
        return

    range_input = input(f"\nQual intervalo? (1-{total_episodes}, ex.: 1-12, 5, 5-, -12): ").strip()
    if not range_input:
        show_warning("Nenhum intervalo informado.")
        pause()
        return

    def get_episode_url(episode_num: int):
        result = get_episode_url_and_source(anime_title, episode_num)
        if result.success and result.player_url:
            return (result.player_url, result.source or "unknown")
        return None

    service = AnimeDownloadService()
    try:
        with loading("Baixando episódios..."):
            result = service.download_episodes(
                anime_title=anime_title,
                range_input=range_input,
                total_episodes=total_episodes,
                get_episode_url=get_episode_url,
            )
    except RangeParseError as e:
        show_error(f"Intervalo inválido: {e}")
        pause()
        return

    show_info(result.summary, title="Resultado do download")
    pause()


def _handle_status_change(anilist_id: int) -> None:
    """Handle status change action from the anime actions menu.

    Args:
        anilist_id: AniList anime ID to update
    """
    from services.anilist import anilist_client

    if not anilist_client.is_authenticated():
        show_warning("Você precisa estar autenticado no AniList para mudar o status.")
        pause()
        return

    status = status_select_menu()
    if status is None:
        return  # ESC → back to actions menu

    with loading("Atualizando status no AniList..."):
        ok = anilist_client.change_status(anilist_id, status)

    if ok:
        show_success(f"Status atualizado para {status.value}.")
    else:
        show_error("Não foi possível atualizar o status no AniList.")
    pause()


def run_anime_actions(
    anime_title: str,
    anilist_id: int,
    args,
    *,
    anilist_progress: int = 0,
    display_title: str | None = None,
    total_episodes: int | None = None,
) -> None:
    """Show the per-anime actions menu loop for a selected anime.

    Shared entry point used by every AniList list flow. Non-terminal actions
    (download, status, open) return to the menu; "watch" is terminal.

    Args:
        anime_title: Title used to search scrapers
        anilist_id: AniList anime ID
        args: Command-line args passed to the playback flow
        anilist_progress: User progress from AniList
        display_title: Full display title (falls back to anime_title)
        total_episodes: Total episodes available (may be None)
    """
    menu_title = display_title or anime_title
    while True:
        action = anime_actions_menu(menu_title)
        if action is None:
            return  # ESC → back to anime list

        if action == "watch":
            anime_service.anilist_anime_flow(
                anime_title,
                anilist_id,
                args,
                anilist_progress=anilist_progress,
                display_title=display_title,
                total_episodes=total_episodes,
            )
            return  # terminal action
        if action == "download":
            _handle_anilist_download(anime_title, total_episodes)
        elif action == "status":
            _handle_status_change(anilist_id)
        elif action == "open":
            show_info(f"Abrindo https://anilist.co/anime/{anilist_id}")
            webbrowser.open_new_tab(f"https://anilist.co/anime/{anilist_id}")


def anilist_auth(args) -> None:
    """Handle AniList authentication flow."""
    _wire_anilist_menus()
    authenticate_flow()


def anilist_menu(args) -> None:
    """Handle AniList menu and watching loop.

    Allows users to browse and watch anime from AniList,
    with automatic progress synchronization.
    """
    from services.anilist import anilist_client

    _wire_anilist_menus()

    if not anilist_client.is_authenticated():
        want_to_connect = Confirm.ask(
            "You are not signed in to AniList. Would you like to connect?",
            default=True,
        )
        if not want_to_connect:
            _console.print("You can authenticate later with: [bold]ani-tupi anilist auth[/bold]")
            return
        authenticate_flow()
        if not anilist_client.is_authenticated():
            _console.print(
                "[red]Authentication failed. Please try again with: ani-tupi anilist auth[/red]"
            )
            return

    # Loop to allow watching multiple anime without restarting
    while True:
        result = anilist_main_menu()
        if not result:
            break  # User cancelled/exited

        anime_title, anilist_id = result

        # Fetch anime info to get display title and total episodes
        anime_info = anilist_client.get_anime_by_id(anilist_id)
        display_title = None
        total_episodes = None
        anilist_progress = 0

        if anime_info:
            display_title = anilist_client.format_title(anime_info.title)
            total_episodes = anime_info.episodes

            # Get user progress if logged in
            entry = anilist_client.get_media_list_entry(anilist_id)
            if entry and entry.progress:
                anilist_progress = entry.progress
        # Show per-anime actions menu before any playback
        run_anime_actions(
            anime_title,
            anilist_id,
            args,
            anilist_progress=anilist_progress,
            display_title=display_title,
            total_episodes=total_episodes,
        )
        # After the action loop, loop back to AniList menu
