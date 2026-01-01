"""AniList menu interface
Textual-based menu for browsing AniList trending and user lists.
"""

import json
import os
import webbrowser

from core.anilist_service import anilist_client
from config import get_data_path
from ui.components import loading, menu_navigate

# History file path (centralized from config)
HISTORY_PATH = get_data_path()


def anilist_main_menu() -> tuple[str, int] | None:
    """Main AniList menu.

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
    if selection == "📅 Recentes (Local)":
        _show_recent_history()  # Now loops internally
        return anilist_main_menu()
    if selection == "🔍 Buscar Anime":
        return _search_and_add_anime(is_logged_in)
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
        _show_account_menu()
        return anilist_main_menu()
    if selection.startswith("─"):
        # Separator - show menu again
        return anilist_main_menu()
    return anilist_main_menu()


def _show_account_menu() -> None:
    """Show account management menu with user stats and logout option."""
    # Load all data once at the beginning
    with loading("Carregando informações da conta..."):
        user_info = anilist_client.get_viewer_info()

        if not user_info:
            print("\n❌ Erro ao carregar informações do usuário")
            input("Pressione Enter para continuar...")
            return

        username = user_info["name"]
        user_id = user_info["id"]

        # Get user stats - calculate manually from lists since API statistics might be 0
        stats = user_info.get("statistics", {}).get("anime", {})
        api_count = stats.get("count", 0)
        api_episodes = stats.get("episodesWatched", 0)
        api_minutes = stats.get("minutesWatched", 0)

        # If API stats are 0, calculate from user lists
        if api_count == 0:
            all_entries = []
            for status in ["CURRENT", "COMPLETED", "PLANNING", "PAUSED", "DROPPED", "REPEATING"]:
                entries = anilist_client.get_user_list(status)
                all_entries.extend(entries)

            total_count = len(all_entries)
            episodes_watched = sum(entry.get("progress", 0) for entry in all_entries)
            minutes_watched = episodes_watched * 24
        else:
            total_count = api_count
            episodes_watched = api_episodes
            minutes_watched = api_minutes

        days_watched = minutes_watched / (60 * 24) if minutes_watched > 0 else 0

        # Get recent activities
        activities = anilist_client.get_recent_activities(limit=5)

    # Build account info display (once)
    account_info = [
        f"👤 Usuário: {username}",
        f"🎬 Animes nas listas: {total_count}",
        f"📺 Episódios assistidos: {episodes_watched}",
        f"⏱️  Tempo estimado: {days_watched:.1f} dias",
        "",
        "📅 Atividades Recentes:",
    ]

    # Format recent activities
    if activities:
        status_emoji = {
            "watched episode": "▶️",
            "plans to watch": "📋",
            "completed": "✅",
            "dropped": "❌",
            "paused watching": "⏸️",
            "rewatched": "🔁",
        }

        for activity in activities:
            status = activity.get("status", "").lower()
            progress = activity.get("progress")
            media = activity.get("media", {})
            title = media.get("title", {}).get("romaji") or media.get("title", {}).get(
                "english", "Unknown"
            )
            episodes = media.get("episodes")
            emoji = status_emoji.get(status, "•")

            if "watched episode" in status and progress:
                if episodes:
                    activity_msg = f"  {emoji} {title} ({progress}/{episodes})"
                else:
                    activity_msg = f"  {emoji} {title} (Ep {progress})"
            elif "completed" in status:
                activity_msg = f"  {emoji} Completou {title}"
            elif "plans to watch" in status:
                activity_msg = f"  {emoji} Planeja assistir {title}"
            elif "dropped" in status:
                activity_msg = f"  {emoji} Dropou {title}"
            elif "paused" in status:
                activity_msg = f"  {emoji} Pausou {title}"
            elif "rewatched" in status:
                activity_msg = f"  {emoji} Reassistiu {title}"
            else:
                activity_msg = f"  {emoji} {status}: {title}"

            account_info.append(activity_msg)
    else:
        account_info.append("  Nenhuma atividade recente")

    account_info.extend(["", "─" * 40])

    # Print account info once
    print("\n" + "\n".join(account_info))

    # Menu options loop
    while True:
        menu_options = [
            "🌐 Abrir perfil no navegador",
            "🚪 Logout",
        ]

        selection = menu_navigate(menu_options, f"Conta: {username}")

        if selection is None:
            # ESC pressed - clear screen and return to main menu
            os.system("clear" if os.name != "nt" else "cls")
            return

        if selection == "🌐 Abrir perfil no navegador":
            profile_url = f"https://anilist.co/user/{user_id}"
            print(f"\n🌐 Abrindo: {profile_url}")
            webbrowser.open(profile_url)
            input("\nPressione Enter para continuar...")
            continue

        if selection == "🚪 Logout":
            confirm_options = ["✅ Sim, fazer logout", "❌ Cancelar"]
            confirm = menu_navigate(confirm_options, "Tem certeza?")

            if confirm == "✅ Sim, fazer logout":
                token_path = HISTORY_PATH / "anilist_token.json"
                if token_path.exists():
                    token_path.unlink()
                    print("\n✅ Logout realizado com sucesso!")
                    input("\nPressione Enter para continuar...")
                    os.system("clear" if os.name != "nt" else "cls")
                    return
                print("\n❌ Token não encontrado")
                input("\nPressione Enter para continuar...")
            continue


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
        year = _choose_year()
        if year is None:  # User cancelled year selection
            return anilist_main_menu()

        season = _choose_season()
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
            print("\n❌ Nenhum anime encontrado")
            print("   Possíveis causas:")
            print("   - Conexão com internet")
            print("   - API do AniList indisponível")
            print("   - Nenhum anime nesse filtro")
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
                media["title"].get("romaji") or media["title"].get("english") or display_title
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
        import argparse

        from core.anime_service import anilist_anime_flow

        # Create args object for anilist_anime_flow
        args = argparse.Namespace(debug=False)

        # Convert episodes to int if available (might be "?" for unknown)
        total_episodes = episodes if isinstance(episodes, int) else None

        # Watch the anime (pass both display and search titles)
        anilist_anime_flow(
            search_title,
            anime_id,
            args,
            anilist_progress=progress,
            display_title=display_title,
            total_episodes=total_episodes,
        )

        # After watching, loop back to show list again
        # This allows user to select another anime from the same list


def _show_recent_history() -> None:
    """Show recently watched anime from local history and allow resuming playback."""
    history_file = HISTORY_PATH / "history.json"

    while True:  # Loop to allow watching multiple anime from recent history
        try:
            with history_file.open() as f:
                history = json.load(f)
        except FileNotFoundError:
            print("\n📂 Nenhum histórico encontrado")
            input("\nPressione Enter para voltar...")
            return
        except Exception:
            print("\n❌ Erro ao carregar histórico")
            input("\nPressione Enter para voltar...")
            return

        if not history:
            print("\n📂 Histórico vazio")
            input("\nPressione Enter para voltar...")
            return

        # Sort by timestamp (most recent first)
        sorted_history = sorted(
            history.items(),
            key=lambda x: x[1][0],  # timestamp is first element
            reverse=True,
        )

        # Build menu options with AniList names (deduplicated by anilist_id)
        with loading("Carregando nomes do AniList..."):
            options = []
            anime_map = {}
            seen_anilist_ids = {}  # Track animes by AniList ID to avoid duplicates

            for anime_name, data in sorted_history[:20]:  # Show last 20
                # Handle both old and new format
                # data format: [timestamp, episode_idx, anilist_id (optional)]
                episode_idx = data[1]
                anilist_id = data[2] if len(data) > 2 else None

                # If we have anilist_id, get the official name and check for duplicates
                display_name = anime_name
                if anilist_id:
                    # Check if we already added this anime (by anilist_id)
                    if anilist_id in seen_anilist_ids:
                        # Skip duplicate - keep the most recent one (already added)
                        continue

                    # Get official AniList name
                    anime_info = anilist_client.get_anime_by_id(anilist_id)
                    if anime_info:
                        display_name = anilist_client.format_title(anime_info["title"])

                    # Mark this anilist_id as seen
                    seen_anilist_ids[anilist_id] = True

                episode_num = episode_idx + 1
                display = f"{display_name} (Ep {episode_num})"
                options.append(display)
                # Store anime_name, anilist_id, and episode_idx
                anime_map[display] = (anime_name, anilist_id, episode_idx)

        # Show menu
        selection = menu_navigate(options, "Animes Recentes (Local)")

        if selection is None:
            return  # User cancelled, go back to main menu

        anime_name, saved_anilist_id, episode_idx = anime_map[selection]

        # If we don't have anilist_id, search for it
        if not saved_anilist_id:
            with loading(f"Buscando '{anime_name}' no AniList..."):
                search_results = anilist_client.search_anime(anime_name)

            if search_results:
                best_match = search_results[0]
                saved_anilist_id = best_match["id"]

        # Get anime info for display and total episodes
        total_episodes = None
        anilist_progress = 0
        if saved_anilist_id:
            anime_info = anilist_client.get_anime_by_id(saved_anilist_id)
            if anime_info:
                display_title = anilist_client.format_title(anime_info["title"])
                search_title = (
                    anime_info["title"].get("romaji")
                    or anime_info["title"].get("english")
                    or display_title
                )
                # Get total episodes from AniList
                total_episodes = anime_info.get("episodes")

                # Get progress from AniList (source of truth)
                entry = anilist_client.get_media_list_entry(saved_anilist_id)
                if entry and entry.get("progress"):
                    anilist_progress = entry["progress"]
            else:
                display_title = anime_name
                search_title = anime_name
        else:
            display_title = anime_name
            search_title = anime_name

        # Use AniList progress as primary source, fall back to local history
        # This ensures we always have the most up-to-date progress
        starting_progress = max(anilist_progress, episode_idx)

        # Import here to avoid circular import
        import argparse

        from core.anime_service import anilist_anime_flow

        # Create args object
        args = argparse.Namespace(debug=False)

        # Watch the anime starting from AniList progress (source of truth)
        # Use max of AniList and local history to never go backwards
        anilist_anime_flow(
            search_title,
            saved_anilist_id,
            args,
            anilist_progress=starting_progress,  # Use AniList as source of truth
            display_title=display_title,
            total_episodes=total_episodes,  # Pass total episodes from AniList
        )

        # After watching, loop back to show recent history again


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
            anime["title"].get("romaji") or anime["title"].get("english") or display_title
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
                    return anilist_main_menu()
                # Status selection cancelled, show actions again
                continue
            if action == "▶️  Assistir agora":
                return (search_title, anime_id)
            return anilist_main_menu()
    else:
        # Not logged in - just watch
        return (search_title, anime_id)


def _choose_status() -> str | None:
    """Let user choose list status.

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


def _choose_year() -> int | None:
    """Let user choose year filter for trending.

    Returns:
        Year (int) or 0 for "all years", or None if cancelled

    """
    from datetime import datetime

    current_year = datetime.now().year

    # Generate year options (current year + 10 years back)
    year_options = ["🌐 Todos os anos"]
    year_options.extend([str(year) for year in range(current_year, current_year - 11, -1)])

    selection = menu_navigate(year_options, "Escolha o ano")

    if selection is None:
        return None

    if selection == "🌐 Todos os anos":
        return 0  # 0 means "all years"

    return int(selection)


def _choose_season() -> str | None:
    """Let user choose season filter for trending.

    Returns:
        Season string (WINTER, SPRING, SUMMER, FALL) or "ALL", or None if cancelled

    """
    season_options = [
        "🌐 Todas as temporadas",
        "Q1 - 🌸 Primavera (Spring)",
        "Q2 - ☀️  Verão (Summer)",
        "Q3 - 🍂 Outono (Fall)",
        "Q4 - ❄️  Inverno (Winter)",
    ]

    season_map = {
        "🌐 Todas as temporadas": "ALL",
        "Q1 - 🌸 Primavera (Spring)": "SPRING",
        "Q2 - ☀️  Verão (Summer)": "SUMMER",
        "Q3 - 🍂 Outono (Fall)": "FALL",
        "Q4 - ❄️  Inverno (Winter)": "WINTER",
    }

    selection = menu_navigate(season_options, "Escolha a temporada")

    if selection is None:
        return None

    return season_map.get(selection)


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
        if user_info:
            pass
    else:
        pass


if __name__ == "__main__":
    # Test menu
    result = anilist_main_menu()
    if result:
        title, anime_id = result
