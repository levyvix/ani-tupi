"""AniList menu interface
Textual-based menu for browsing AniList trending and user lists.
"""

import argparse

from models.config import get_data_path, settings
from ui.components import loading, menu_navigate
from models.models import AniListTitle, Status
from utils.cache import get_cache
from utils.logging import get_logger
from ui.anilist.account_menu import show_account_menu, set_anilist_client as set_account_menu_client
from ui.anilist.recent_history_menu import (
    show_recent_history,
    set_anilist_client as set_recent_history_client,
    set_run_anime_actions as set_recent_history_actions,
)
from ui.anilist.airing_menu import (
    show_airing_episodes,
    set_anilist_client as set_airing_menu_client,
    set_airing_service_factory,
    set_run_anime_actions as set_airing_menu_actions,
)
from ui.anilist.filters import choose_year, choose_season, choose_status

logger = get_logger(__name__)

# History file path (centralized from config)
HISTORY_PATH = get_data_path()

# ---------------------------------------------------------------------------
# Dependency injection holders
#
# ``ui`` must remain a pure rendering layer: it may not import from
# ``services.*`` or ``commands.*``. The command layer wires the real
# implementations at runtime via :func:`configure`. Tests may patch these
# module attributes directly.
# ---------------------------------------------------------------------------


def _not_configured(*_, **__):
    raise RuntimeError(
        "ui.anilist_menus não foi configurado — chame configure() antes de usar os menus"
    )


anilist_client = _not_configured
anilist_anime_flow = _not_configured
run_anime_actions = _not_configured
airing_service_factory = _not_configured
handle_local_library_playback = _not_configured


def configure(
    *,
    client,
    anime_flow,
    anime_actions,
    airing_service,
    local_library_playback,
) -> None:
    """Wire the runtime dependencies used by the AniList menus.

    Called by the command layer so ``ui`` never imports ``services``/``commands``.

    Args:
        client: AniList client instance (``services.anilist.anilist_client``)
        anime_flow: Playback flow callable (``anilist_anime_flow``)
        anime_actions: Per-anime actions callback (``run_anime_actions``)
        airing_service: Zero-arg factory returning an airing-episodes service
        local_library_playback: Local library playback callback
    """
    global anilist_client, anilist_anime_flow, run_anime_actions
    global airing_service_factory, handle_local_library_playback

    anilist_client = client
    anilist_anime_flow = anime_flow
    run_anime_actions = anime_actions
    airing_service_factory = airing_service
    handle_local_library_playback = local_library_playback

    # Wire dependencies in submodules
    set_account_menu_client(client)
    set_recent_history_client(client)
    set_recent_history_actions(anime_actions)
    set_airing_menu_client(client)
    set_airing_service_factory(airing_service)
    set_airing_menu_actions(anime_actions)


def get_search_title(title: AniListTitle, display_title: str = "") -> str:
    """Get preferred title for search based on config.

    Args:
        title: AniListTitle object with romaji/english/native
        display_title: Fallback display title

    Returns:
        Title to use for searching (english or romaji based on config)
    """
    if settings.anilist.prefer_english_title:
        return title.english or title.romaji or display_title
    return title.romaji or title.english or display_title


def _get_episode_count(anime_id: int, media_episodes: int | None) -> int | None:
    """Get episode count for an anime with caching fallback.

    Args:
        anime_id: AniList anime ID
        media_episodes: Episode count from media list response (can be None)

    Returns:
        Episode count as int, or None if truly unknown
    """
    # If we already have episode count, return it
    if media_episodes is not None:
        return media_episodes

    # Check cache first
    cache = get_cache()
    cache_key = f"anilist_episodes:{anime_id}"
    cached_episodes = cache.get(cache_key)
    if cached_episodes is not None:
        return cached_episodes

    # Cache miss - fetch full anime details
    try:
        anime_details = anilist_client.get_anime_by_id(anime_id)
        if anime_details and anime_details.episodes is not None:
            # Cache the result (7 days TTL = 604800 seconds)
            cache.set(cache_key, anime_details.episodes, ttl=604800)
            return anime_details.episodes
    except Exception:
        # If API call fails, we'll return None and keep "?" fallback
        pass

    # Truly unknown episode count
    return None


def _start_watching_anime(search_title: str, anime_id: int, display_title: str) -> None:
    """Start watching anime with proper progress tracking.

    Args:
        search_title: Title to use for searching scrapers
        anime_id: AniList anime ID
        display_title: Full display title for the user

    Returns:
        None (loads playback flow, then returns to main menu)
    """
    args = argparse.Namespace(debug=False)
    entry = anilist_client.get_media_list_entry(anime_id)
    anilist_progress = entry.progress if entry and entry.progress else 0

    anilist_anime_flow(
        search_title,
        anime_id,
        args,
        anilist_progress=anilist_progress,
        display_title=display_title,
    )


def anime_actions_menu(display_title: str) -> str | None:
    """Show per-anime actions menu.

    Args:
        display_title: Title shown in the menu header

    Returns:
        One of "watch", "download", "status", "open", or None on ESC
    """
    action_options = [
        "▶️  Assistir agora",
        "📥 Baixar",
        "🔄 Mudar status",
        "🌐 Abrir página no AniList",
    ]

    action_map = {
        "▶️  Assistir agora": "watch",
        "📥 Baixar": "download",
        "🔄 Mudar status": "status",
        "🌐 Abrir página no AniList": "open",
    }

    selection = menu_navigate(action_options, display_title)

    if selection is None:
        return None

    return action_map.get(selection)


def status_select_menu() -> Status | None:
    """Show status submenu mapping readable labels to Status enum.

    Returns:
        Selected Status, or None on ESC
    """
    status_options = [
        "📺 Watching (Assistindo)",
        "📋 Planning (Planejo assistir)",
        "✅ Completed (Completo)",
        "⏸️  Paused (Pausado)",
        "❌ Dropped (Dropado)",
        "🔁 Repeating (Reassistindo)",
    ]

    status_map = {
        "📺 Watching (Assistindo)": Status.CURRENT,
        "📋 Planning (Planejo assistir)": Status.PLANNING,
        "✅ Completed (Completo)": Status.COMPLETED,
        "⏸️  Paused (Pausado)": Status.PAUSED,
        "❌ Dropped (Dropado)": Status.DROPPED,
        "🔁 Repeating (Reassistindo)": Status.REPEATING,
    }

    selection = menu_navigate(status_options, "Escolha o novo status")

    if selection is None:
        return None

    return status_map.get(selection)


def anilist_main_menu() -> tuple[str, int] | None:
    """Main AniList menu.

    Returns:
        Tuple of (anime_title, anilist_id) if anime selected
        None if user exits

    """
    # Check authentication status
    is_logged_in = anilist_client.is_authenticated()

    # Build menu options
    menu_options = [
        "📈 Trending",
        "📅 Recentes (Local)",
        "📂 Biblioteca Local",
        "🔍 Buscar Anime",
    ]

    if is_logged_in:
        # Get user info
        user_info = anilist_client.get_viewer_info()
        username = user_info.name if user_info else "User"

        menu_options.extend(
            [
                f"👤 {username}",
                "─" * 30,
                "🎬 Novos Episódios",
                "📺 Watching",
                "📋 Planning",
                "✅ Completed",
                "⏸️  Paused",
                "❌ Dropped",
                "🔁 Rewatching",
            ]
        )
    else:
        menu_options.append("🔐 Login (use: ani-tupi anilist auth)")

    # Display menu
    selection = menu_navigate(menu_options, "AniList Menu")

    if selection is None:
        return None

    # Handle selection
    if selection == "📈 Trending":
        _show_anime_list("trending")  # Now loops internally
        return anilist_main_menu()
    if selection == "📅 Recentes (Local)":
        show_recent_history()  # Now loops internally
        return anilist_main_menu()
    if selection == "📂 Biblioteca Local":
        _show_local_library()  # Now loops internally
        return anilist_main_menu()
    if selection == "🔍 Buscar Anime":
        return _search_and_add_anime(is_logged_in)
    if selection == "🎬 Novos Episódios":
        show_airing_episodes()  # Now loops internally
        return anilist_main_menu()
    if selection == "📺 Watching":
        _show_anime_list("CURRENT")  # Now loops internally
        return anilist_main_menu()
    if selection == "📋 Planning":
        _show_anime_list("PLANNING")  # Now loops internally
        return anilist_main_menu()
    if selection == "✅ Completed":
        _show_anime_list("COMPLETED")  # Now loops internally
        return anilist_main_menu()
    if selection == "⏸️  Paused":
        _show_anime_list("PAUSED")  # Now loops internally
        return anilist_main_menu()
    if selection == "❌ Dropped":
        _show_anime_list("DROPPED")  # Now loops internally
        return anilist_main_menu()
    if selection == "🔁 Rewatching":
        _show_anime_list("REPEATING")  # Now loops internally
        return anilist_main_menu()
    if selection.startswith("👤"):
        # Show account management menu
        show_account_menu()
        return anilist_main_menu()
    if selection.startswith("─"):
        # Separator - show menu again
        return anilist_main_menu()
    return anilist_main_menu()


def _show_anime_list(list_type: str) -> tuple[str, int] | None:
    """Show anime list (trending or user list) with loop to stay in list.

    Args:
        list_type: 'trending' or AniList status (CURRENT, PLANNING, etc)

    Returns:
        None (loops back to main menu when done)

    """
    # If trending, ask for year and season filters first
    year = None
    season = None
    if list_type == "trending":
        year = choose_year()
        if year is None:  # User cancelled year selection
            return anilist_main_menu()

        season = choose_season()
        if season is None:  # User cancelled season selection
            return anilist_main_menu()

    while True:  # Loop to allow watching multiple anime from same list
        # Fetch anime list
        if list_type == "trending":
            # Build title based on filters
            title_parts = ["Trending"]
            if year != 0:  # 0 means "all years"
                title_parts.append(str(year))
            if season != "ALL":  # "ALL" means "all seasons"
                season_names = {
                    "WINTER": "Inverno",
                    "SPRING": "Primavera",
                    "SUMMER": "Verão",
                    "FALL": "Outono",
                }
                title_parts.append(season_names.get(season, season))
            title = " - ".join(title_parts)

            with loading("Carregando trending..."):
                anime_list = anilist_client.get_trending(
                    per_page=50,
                    year=year if year != 0 else None,
                    season=season if season != "ALL" else None,
                )
        else:
            with loading(f"Carregando lista {list_type}..."):
                anime_list = anilist_client.get_user_list(list_type, per_page=50)
            title = f"Your {list_type.title()} List"

        if not anime_list:
            logger.info("\n❌ Nenhum anime encontrado")
            logger.info("   Possíveis causas:")
            logger.info("   - Conexão com internet")
            logger.info("   - API do AniList indisponível")
            logger.info("   - Nenhum anime nesse filtro")
            input("\nPressione Enter para voltar...")
            return anilist_main_menu()

        # Format options
        options = []
        anime_map = {}  # option -> (display_title, search_title, id, progress, episodes)

        # Build menu
        for item in anime_list:
            # Handle different response formats
            if hasattr(item, "media"):  # User list format (AniListMediaListEntry)
                media = item.media
                progress = item.progress or 0
            else:  # Trending format (AniListAnime)
                media = item
                progress = 0

            if not media:
                continue

            # Format title for display (bilingual)
            display_title = anilist_client.format_title(media.title)

            # Get preferred search title based on config
            search_title = get_search_title(media.title, display_title)

            anime_id = media.id
            # Avoid blocking list rendering with one extra AniList request per anime
            # when AniList does not expose the episode count for ongoing shows.
            episodes = media.episodes if media.episodes is not None else "?"

            # Build display string
            if progress > 0:
                display = f"{display_title} ({progress}/{episodes})"
            else:
                display = f"{display_title} ({episodes} eps)"

            # Add score if available
            score = media.averageScore
            if score:
                display += f" ⭐{score}%"

            options.append(display)
            anime_map[display] = (
                display_title,
                search_title,
                anime_id,
                progress,
                episodes,
            )

        # Show menu
        selection = menu_navigate(options, title)

        if selection is None:
            return anilist_main_menu()  # User cancelled, go back to main menu

        # Get selected anime info
        display_title, search_title, anime_id, progress, episodes = anime_map[selection]

        # Create args object for anilist_anime_flow
        args = argparse.Namespace(debug=False)

        # Convert episodes to int if available (might be "?" for unknown)
        total_episodes = episodes if isinstance(episodes, int) else None

        # Show per-anime actions menu (watch/download/status/open)
        run_anime_actions(
            search_title,
            anime_id,
            args,
            anilist_progress=progress,
            display_title=display_title,
            total_episodes=total_episodes,
        )

        # After the actions menu, loop back to show list again
        # This allows user to select another anime from the same list


def _search_and_add_anime(is_logged_in: bool) -> tuple[str, int] | None:
    """Search for anime and optionally add to user's list.

    Args:
        is_logged_in: Whether user is authenticated

    Returns:
        Tuple of (anime_title, anilist_id) if selected to watch
        None if going back

    """
    # Get search query
    query = input("\n🔍 Digite o nome do anime: ").strip()

    if not query:
        return anilist_main_menu()

    with loading(f"Buscando '{query}' no AniList..."):
        results = anilist_client.search_anime(query)

    if not results:
        input("\nPressione Enter para voltar...")
        return anilist_main_menu()

    # Format results for menu
    options = []
    anime_map = {}

    for anime in results:
        display_title = anilist_client.format_title(anime.title)
        anime_id = anime.id
        episodes = anime.episodes
        year = anime.seasonYear or "?"
        score = anime.averageScore

        display = f"{display_title} ({year}, {episodes} eps)"
        if score:
            display += f" ⭐{score}%"

        options.append(display)
        search_title = get_search_title(anime.title, display_title)
        anime_map[display] = (display_title, search_title, anime_id)

    # Show results
    selection = menu_navigate(options, f"Resultados para '{query}'")

    if selection is None:
        return anilist_main_menu()

    display_title, search_title, anime_id = anime_map[selection]

    # If logged in, offer to add to list
    if is_logged_in:
        while True:  # Loop to allow adding then watching
            action_options = ["▶️  Assistir agora", "➕ Adicionar à lista", "🔙 Voltar"]
            action = menu_navigate(action_options, f"{display_title}")

            if action == "➕ Adicionar à lista":
                # Choose status
                status = choose_status()
                if status:
                    anilist_client.add_to_list(anime_id, status)

                    # Ask if want to watch now
                    watch_now_options = ["▶️  Assistir agora", "🔙 Voltar ao menu"]
                    watch_choice = menu_navigate(watch_now_options, "Anime adicionado!")

                    if watch_choice == "▶️  Assistir agora":
                        _start_watching_anime(search_title, anime_id, display_title)
                        return anilist_main_menu()
                    return anilist_main_menu()
                # Status selection cancelled, show actions again
                continue
            if action == "▶️  Assistir agora":
                _start_watching_anime(search_title, anime_id, display_title)
                return anilist_main_menu()
            return anilist_main_menu()
    else:
        # Not logged in - just watch
        _start_watching_anime(search_title, anime_id, display_title)
        return anilist_main_menu()


def _show_local_library() -> None:
    """Show local anime library menu with full playback flow.

    Delegates to handle_local_library_playback() to ensure consistency
    with the main menu flow, including:
    - Post-playback confirmation ("Você assistiu até o final?")
    - AniList sync with offline queue fallback
    - Navigation menu (Next/Previous/Replay/Back)
    - Playback loop for multiple episodes
    """
    args = argparse.Namespace(debug=False)
    handle_local_library_playback(args)


def authenticate_flow() -> None:
    """Run OAuth authentication flow."""
    if anilist_client.is_authenticated():
        user_info = anilist_client.get_viewer_info()
        if user_info:
            choice = input("\nDeseja fazer login com outra conta? (s/N): ").strip().lower()
            if choice != "s":
                return

    # Run authentication
    success = anilist_client.authenticate()

    if success:
        user_info = anilist_client.get_viewer_info()
        username = user_info.get("name", "usuário") if user_info else "usuário"
        logger.info(f"Autenticado como {username}")
    else:
        logger.error("Falha na autenticação. Verifique o token.")


if __name__ == "__main__":
    # Test menu
    result = anilist_main_menu()
    if result:
        title, anime_id = result
