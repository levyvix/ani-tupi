"""
AniList menu interface
Textual-based menu for browsing AniList trending and user lists
"""

import sys
import json
from typing import Optional
from pathlib import Path
from os import name as os_name
from anilist import anilist_client
from menu import menu_navigate
from loading import loading

# History file path (same as main.py)
HISTORY_PATH = (
    Path.home().as_posix() + "/.local/state/ani-tupi/"
    if os_name != "nt"
    else "C:\\Program Files\\ani-tupi\\"
)


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
    menu_options = ["📈 Trending", "📅 Recentes (Local)", "🔍 Buscar Anime"]

    if is_logged_in:
        # Get user info
        user_info = anilist_client.get_viewer_info()
        username = user_info["name"] if user_info else "User"

        menu_options.extend(
            [
                f"👤 {username}",
                "─" * 30,
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
    elif selection == "📅 Recentes (Local)":
        return _show_recent_history()
    elif selection == "🔍 Buscar Anime":
        return _search_and_add_anime(is_logged_in)
    elif selection == "📺 Watching":
        _show_anime_list("CURRENT")  # Now loops internally
        return anilist_main_menu()
    elif selection == "📋 Planning":
        _show_anime_list("PLANNING")  # Now loops internally
        return anilist_main_menu()
    elif selection == "✅ Completed":
        _show_anime_list("COMPLETED")  # Now loops internally
        return anilist_main_menu()
    elif selection == "⏸️  Paused":
        _show_anime_list("PAUSED")  # Now loops internally
        return anilist_main_menu()
    elif selection == "❌ Dropped":
        _show_anime_list("DROPPED")  # Now loops internally
        return anilist_main_menu()
    elif selection == "🔁 Rewatching":
        _show_anime_list("REPEATING")  # Now loops internally
        return anilist_main_menu()
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
    Show anime list (trending or user list) with loop to stay in list

    Args:
        list_type: 'trending' or AniList status (CURRENT, PLANNING, etc)

    Returns:
        None (loops back to main menu when done)
    """
    while True:  # Loop to allow watching multiple anime from same list
        # Fetch anime list
        if list_type == "trending":
            with loading("Carregando trending..."):
                anime_list = anilist_client.get_trending(per_page=50)
            title = "Trending Anime"
        else:
            with loading(f"Carregando lista {list_type}..."):
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

            # Get romaji first, then english
            search_title = (
                media["title"].get("romaji")
                or media["title"].get("english")
                or display_title
            )

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

        # Import here to avoid circular import
        from main import anilist_anime_flow
        import argparse

        # Create args object for anilist_anime_flow
        args = argparse.Namespace(debug=False)

        # Watch the anime (pass both display and search titles)
        anilist_anime_flow(search_title, anime_id, args, anilist_progress=progress, display_title=display_title)

        # After watching, loop back to show list again
        # This allows user to select another anime from the same list


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
        reverse=True,
    )

    # Build menu options
    options = []
    anime_map = {}

    for anime_name, data in sorted_history[:20]:  # Show last 20
        # Handle both old and new format
        timestamp = data[0]
        episode_idx = data[1]
        anilist_id = data[2] if len(data) > 2 else None

        episode_num = episode_idx + 1
        display = f"{anime_name} (Ep {episode_num})"
        options.append(display)
        anime_map[display] = (anime_name, anilist_id)

    # Show menu
    selection = menu_navigate(options, "Animes Recentes (Local)")

    if selection is None:
        return anilist_main_menu()

    anime_name, saved_anilist_id = anime_map[selection]

    # If we already have anilist_id saved, use it
    if saved_anilist_id:
        print(f"\n✅ Usando AniList ID salvo: {saved_anilist_id}")
        # Get anime info to show the correct title
        anime_info = anilist_client.get_anime_by_id(saved_anilist_id)
        if anime_info:
            anilist_title = anilist_client.format_title(anime_info["title"])
            print(f"📺 {anilist_title}")
        return (anime_name, saved_anilist_id)

    # No saved anilist_id - search for it
    print(f"\n🔍 Buscando '{anime_name}' no AniList...")
    with loading(f"Buscando '{anime_name}' no AniList..."):
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


def _search_and_add_anime(is_logged_in: bool) -> Optional[tuple[str, int]]:
    """
    Search for anime and optionally add to user's list

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

    print(f"\n🔍 Buscando '{query}' no AniList...")
    with loading(f"Buscando '{query}' no AniList..."):
        results = anilist_client.search_anime(query)

    if not results:
        print(f"\n❌ Nenhum anime encontrado para '{query}'")
        input("\nPressione Enter para voltar...")
        return anilist_main_menu()

    # Format results for menu
    options = []
    anime_map = {}

    for anime in results:
        display_title = anilist_client.format_title(anime["title"])
        anime_id = anime["id"]
        episodes = anime.get("episodes") or "?"
        year = anime.get("seasonYear") or "?"
        score = anime.get("averageScore")

        display = f"{display_title} ({year}, {episodes} eps)"
        if score:
            display += f" ⭐{score}%"

        options.append(display)
        search_title = (
            anime["title"].get("romaji")
            or anime["title"].get("english")
            or display_title
        )
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
                status = _choose_status()
                if status:
                    anilist_client.add_to_list(anime_id, status)

                    # Ask if want to watch now
                    watch_now_options = ["▶️  Assistir agora", "🔙 Voltar ao menu"]
                    watch_choice = menu_navigate(watch_now_options, "Anime adicionado!")

                    if watch_choice == "▶️  Assistir agora":
                        return (search_title, anime_id)
                    else:
                        return anilist_main_menu()
                else:
                    # Status selection cancelled, show actions again
                    continue
            elif action == "▶️  Assistir agora":
                return (search_title, anime_id)
            else:
                return anilist_main_menu()
    else:
        # Not logged in - just watch
        return (search_title, anime_id)


def _choose_status() -> Optional[str]:
    """
    Let user choose list status

    Returns:
        Status string (CURRENT, PLANNING, etc) or None if cancelled
    """
    status_options = [
        "📺 Watching (Assistindo)",
        "📋 Planning (Planejo assistir)",
        "✅ Completed (Completo)",
        "⏸️  Paused (Pausado)",
        "❌ Dropped (Dropado)",
        "🔁 Rewatching (Reassistindo)",
    ]

    status_map = {
        "📺 Watching (Assistindo)": "CURRENT",
        "📋 Planning (Planejo assistir)": "PLANNING",
        "✅ Completed (Completo)": "COMPLETED",
        "⏸️  Paused (Pausado)": "PAUSED",
        "❌ Dropped (Dropado)": "DROPPED",
        "🔁 Rewatching (Reassistindo)": "REPEATING",
    }

    selection = menu_navigate(status_options, "Escolha o status")

    if selection is None:
        return None

    return status_map.get(selection)


def authenticate_flow():
    """
    Run OAuth authentication flow
    """
    print("\n🔐 Autenticação AniList\n")

    if anilist_client.is_authenticated():
        user_info = anilist_client.get_viewer_info()
        if user_info:
            print(f"✅ Você já está logado como: {user_info['name']}")
            choice = (
                input("\nDeseja fazer login com outra conta? (s/N): ").strip().lower()
            )
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
