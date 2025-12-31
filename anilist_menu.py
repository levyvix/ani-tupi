"""
AniList menu interface
Curses-based menu for browsing AniList trending and user lists
"""

import curses
import sys
import json
from typing import Optional
from pathlib import Path
from os import name as os_name
from anilist import anilist_client

# History file path (same as main.py)
HISTORY_PATH = Path.home().as_posix() + "/.local/state/ani-tupi/" if os_name != 'nt' else "C:\\Program Files\\ani-tupi\\"


def anilist_main_menu() -> Optional[tuple[str, int]]:
    """
    Main AniList menu

    Returns:
        Tuple of (anime_title, anilist_id) if anime selected
        None if user exits
    """
    # Check authentication status
    is_logged_in = anilist_client.is_authenticated()

    # Build menu options
    menu_options = ["📈 Trending", "📅 Recentes (Local)"]

    if is_logged_in:
        # Get user info
        user_info = anilist_client.get_viewer_info()
        username = user_info["name"] if user_info else "User"

        menu_options.extend([
            f"👤 {username}",
            "─" * 30,
            "📺 Watching",
            "📋 Planning",
            "✅ Completed",
            "⏸️  Paused",
            "❌ Dropped",
            "🔁 Rewatching",
        ])
    else:
        menu_options.append("🔐 Login (use: ani-tupi anilist auth)")

    # Display menu
    selection = _display_menu(menu_options, "AniList Menu")

    if selection is None or selection == "Sair":
        return None

    # Handle selection
    if selection == "📈 Trending":
        return _show_anime_list("trending")
    elif selection == "📅 Recentes (Local)":
        return _show_recent_history()
    elif selection == "📺 Watching":
        return _show_anime_list("CURRENT")
    elif selection == "📋 Planning":
        return _show_anime_list("PLANNING")
    elif selection == "✅ Completed":
        return _show_anime_list("COMPLETED")
    elif selection == "⏸️  Paused":
        return _show_anime_list("PAUSED")
    elif selection == "❌ Dropped":
        return _show_anime_list("DROPPED")
    elif selection == "🔁 Rewatching":
        return _show_anime_list("REPEATING")
    elif selection.startswith("👤"):
        # User info - just show menu again
        return anilist_main_menu()
    elif selection.startswith("─"):
        # Separator - show menu again
        return anilist_main_menu()
    else:
        return anilist_main_menu()


def _show_anime_list(list_type: str) -> Optional[tuple[str, int]]:
    """
    Show anime list (trending or user list)

    Args:
        list_type: 'trending' or AniList status (CURRENT, PLANNING, etc)

    Returns:
        Tuple of (anime_title, anilist_id) if selected
    """
    # Fetch anime list
    if list_type == "trending":
        anime_list = anilist_client.get_trending(per_page=50)
        title = "Trending Anime"
    else:
        anime_list = anilist_client.get_user_list(list_type, per_page=50)
        title = f"Your {list_type.title()} List"

    if not anime_list:
        print(f"\n❌ Nenhum anime encontrado em {list_type}")
        input("\nPressione Enter para voltar...")
        return anilist_main_menu()

    # Format options
    options = []
    anime_map = {}  # option -> (display_title, search_title, id, progress, episodes)

    for item in anime_list:
        # Handle different response formats
        if "media" in item:  # User list format
            media = item["media"]
            progress = item.get("progress", 0)
        else:  # Trending format
            media = item
            progress = 0

        # Format title for display (bilingual)
        display_title = anilist_client.format_title(media["title"])

        # Get romaji for searching (scrapers use romaji/portuguese)
        search_title = media["title"].get("romaji") or media["title"].get("english") or display_title

        anime_id = media["id"]
        episodes = media.get("episodes") or "?"

        # Build display string
        if progress > 0:
            display = f"{display_title} ({progress}/{episodes})"
        else:
            display = f"{display_title} ({episodes} eps)"

        # Add score if available
        score = media.get("averageScore")
        if score:
            display += f" ⭐{score}%"

        options.append(display)
        anime_map[display] = (display_title, search_title, anime_id, progress, episodes)

    # Show menu
    selection = _display_menu(options, title)

    if selection is None or selection == "Sair":
        return anilist_main_menu()

    # Return selected anime info
    # Returns: (display_title, search_title, anilist_id)
    display_title, search_title, anime_id, progress, episodes = anime_map[selection]
    return (search_title, anime_id)  # Use search_title (romaji) for scraper search


def _display_menu(options: list[str], title: str = "") -> Optional[str]:
    """
    Display curses menu (reusing logic from menu.py)

    Args:
        options: List of menu options
        title: Menu title

    Returns:
        Selected option or None if exited
    """
    # Add exit option if not present
    if "Sair" not in options and "Voltar" not in options:
        options = options + ["Voltar"]

    def _menu_impl(stdscr):
        # Setup
        curses.curs_set(0)  # Hide cursor
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # Selected
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Normal

        current_option = 0
        start_index = 0  # Viewport start

        while True:
            stdscr.clear()
            screen_height, screen_width = stdscr.getmaxyx()

            # Display title
            if title:
                title_text = f" {title} "
                stdscr.addstr(0, (screen_width - len(title_text)) // 2, title_text, curses.color_pair(2) | curses.A_BOLD)

            # Display navigation hints at bottom
            hints = "↑↓: Navegar | Enter: Selecionar | ESC: Voltar"
            try:
                stdscr.addstr(screen_height - 1, (screen_width - len(hints)) // 2, hints, curses.color_pair(2) | curses.A_DIM)
            except:
                pass  # Ignore if terminal too small

            # Calculate viewport
            display_height = screen_height - 3  # Reserve space for hints
            end_index = min(start_index + display_height, len(options))
            visible_options = options[start_index:end_index]

            # Display options
            for idx, option in enumerate(visible_options):
                actual_idx = start_index + idx
                y_pos = idx + 1

                # Skip separator lines in selection
                if option.startswith("─"):
                    stdscr.addstr(y_pos, 2, option, curses.color_pair(2))
                elif actual_idx == current_option:
                    stdscr.addstr(y_pos, 2, f"> {option}", curses.color_pair(1))
                else:
                    stdscr.addstr(y_pos, 2, f"  {option}", curses.color_pair(2))

            stdscr.refresh()

            # Handle input
            key = stdscr.getch()

            if key == 27:  # ESC key
                return None

            if key == curses.KEY_UP:
                # Move up, skip separators
                current_option = (current_option - 1) % len(options)
                while options[current_option].startswith("─"):
                    current_option = (current_option - 1) % len(options)

                # Adjust viewport
                if current_option < start_index:
                    start_index = current_option

            elif key == curses.KEY_DOWN:
                # Move down, skip separators
                current_option = (current_option + 1) % len(options)
                while options[current_option].startswith("─"):
                    current_option = (current_option + 1) % len(options)

                # Adjust viewport
                if current_option >= end_index:
                    start_index = current_option - display_height + 1

            elif key in [curses.KEY_ENTER, 10, 13]:  # Enter
                selected = options[current_option]
                if selected in ["Sair", "Voltar"]:
                    return None
                return selected

        return None

    try:
        return curses.wrapper(_menu_impl)
    except KeyboardInterrupt:
        return None


def _show_recent_history() -> Optional[tuple[str, int]]:
    """
    Show recently watched anime from local history

    Returns:
        Tuple of (anime_title, anilist_id) if selected
        None if no history or user goes back
    """
    history_file = HISTORY_PATH + "history.json"

    try:
        with open(history_file, "r") as f:
            history = json.load(f)
    except FileNotFoundError:
        print("\n❌ Nenhum histórico encontrado.")
        print("Assista alguns animes primeiro!")
        input("\nPressione Enter para voltar...")
        return anilist_main_menu()
    except Exception as e:
        print(f"\n❌ Erro ao ler histórico: {e}")
        input("\nPressione Enter para voltar...")
        return anilist_main_menu()

    if not history:
        print("\n❌ Histórico vazio.")
        input("\nPressione Enter para voltar...")
        return anilist_main_menu()

    # Sort by timestamp (most recent first)
    sorted_history = sorted(
        history.items(),
        key=lambda x: x[1][0],  # timestamp is first element
        reverse=True
    )

    # Build menu options
    options = []
    anime_map = {}

    for anime_name, (timestamp, episode_idx) in sorted_history[:20]:  # Show last 20
        episode_num = episode_idx + 1
        display = f"{anime_name} (Ep {episode_num})"
        options.append(display)
        anime_map[display] = anime_name

    # Show menu
    selection = _display_menu(options, "Animes Recentes (Local)")

    if selection is None:
        return anilist_main_menu()

    anime_name = anime_map[selection]

    # Search this anime on AniList to get the ID
    print(f"\n🔍 Buscando '{anime_name}' no AniList...")
    search_results = anilist_client.search_anime(anime_name)

    if not search_results:
        print(f"\n❌ '{anime_name}' não encontrado no AniList.")
        print("Continuando sem sincronização...")
        input("\nPressione Enter para continuar...")
        # Return with None as anilist_id (will skip sync)
        return (anime_name, None)

    # If multiple results, use first match
    best_match = search_results[0]
    anime_id = best_match["id"]
    anilist_title = anilist_client.format_title(best_match["title"])

    print(f"✅ Encontrado: {anilist_title} (ID: {anime_id})")

    return (anime_name, anime_id)


def authenticate_flow():
    """
    Run OAuth authentication flow
    """
    print("\n🔐 Autenticação AniList\n")

    if anilist_client.is_authenticated():
        user_info = anilist_client.get_viewer_info()
        if user_info:
            print(f"✅ Você já está logado como: {user_info['name']}")
            choice = input("\nDeseja fazer login com outra conta? (s/N): ").strip().lower()
            if choice != "s":
                return

    # Run authentication
    success = anilist_client.authenticate()

    if success:
        user_info = anilist_client.get_viewer_info()
        if user_info:
            print(f"\n✅ Logado como: {user_info['name']}")
    else:
        print("\n❌ Falha na autenticação")


if __name__ == "__main__":
    # Test menu
    result = anilist_main_menu()
    if result:
        title, anime_id = result
        print(f"\nSelecionado: {title} (ID: {anime_id})")
