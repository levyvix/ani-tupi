"""AniList menu interface
Textual-based menu for browsing AniList trending and user lists.
"""

import argparse
import json
import os
import webbrowser

from concurrent.futures import ThreadPoolExecutor, as_completed
from services.anilist_service import anilist_client
from services.anime_service import anilist_anime_flow
from services.anime.airing_episodes_service import AiringEpisodesService
from services.anime.aniskip_service import AniSkipService
from models.config import get_data_path, settings
from ui.components import loading, menu_navigate
from models.models import AniListTitle
from utils.cache import get_cache
from utils.logging import get_logger

logger = get_logger(__name__)

# History file path (centralized from config)
HISTORY_PATH = get_data_path()


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


def _fetch_skip_icon_for_mal_id(aniskip: AniSkipService, cache, title: str, mal_id: int) -> str:
    """Fetch skip icon for a MAL ID without additional lookups.

    Used internally by batch fetching to avoid redundant MAL ID searches.

    Args:
        aniskip: AniSkipService instance
        cache: Cache instance
        title: Display title for caching
        mal_id: MyAnimeList ID (already resolved)

    Returns:
        Icon string "⏭️ " if skip data available, empty string otherwise
    """
    cache_key = f"aniskip:{mal_id}"

    # Check cache first (7 day TTL)
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return "⏭️ " if cached_result else ""

    try:
        skip_times = aniskip.get_skip_times(mal_id, 1)
        has_skip = bool(skip_times)
        cache.set(cache_key, has_skip, ttl=604800)
        return "⏭️ " if has_skip else ""
    except Exception:
        cache.set(cache_key, False, ttl=604800)
        return ""


def _get_aniskip_icon(display_title: str, mal_id: int | None = None, timeout: float = 1.5) -> str:
    """Get skip icon if anime has auto-skip data available.

    Uses persistent cache (7 day TTL) and quick timeout to avoid blocking UI.

    Args:
        display_title: Display title of the anime
        mal_id: Optional MyAnimeList ID (speeds up lookup if provided)
        timeout: Max time to wait for API response in seconds

    Returns:
        Icon string "⏭️ " if skip data available, empty string otherwise
    """
    cache = get_cache()

    try:
        # Check cache first (7 day TTL = 604800 seconds)
        cache_key = f"aniskip:{mal_id or display_title.lower()}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return "⏭️ " if cached_result else ""

        aniskip = AniSkipService()
        found_mal_id = mal_id

        # Search for mal_id if not provided (with timeout)
        if not found_mal_id:
            try:
                found_mal_id = aniskip.search_mal_id(display_title)
            except Exception:
                # Timeout or error - cache as "no skip data" and return
                cache.set(cache_key, False, ttl=604800)
                return ""

        if found_mal_id:
            try:
                skip_times = aniskip.get_skip_times(found_mal_id, 1)
                has_skip = bool(skip_times)
                # Cache result for 7 days
                cache.set(cache_key, has_skip, ttl=604800)
                return "⏭️ " if has_skip else ""
            except Exception:
                # Timeout or error - cache as "no skip data"
                cache.set(cache_key, False, ttl=604800)
                return ""

        # MAL ID not found - cache as "no skip data"
        cache.set(cache_key, False, ttl=604800)
        return ""

    except Exception:
        # Any other error - silently fail without blocking UI
        pass
    return ""


def _get_aniskip_icons_batch(
    anime_list: list[tuple[str, int | None]],
    max_workers: int | None = None,
    timeout_per_task: float = 2.0,
    use_progress_bar: bool = True,
) -> dict[str, str]:
    """Get skip icons for multiple anime in parallel with optimized MAL ID lookups.

    Two-phase approach:
    1. Batch resolve missing MAL IDs in parallel
    2. Fetch skip times in parallel

    Uses ThreadPoolExecutor to parallelize API calls with no global timeout.
    Each individual task has a timeout to avoid hanging.

    Args:
        anime_list: List of (display_title, mal_id) tuples
        max_workers: Max parallel threads. If None, scales based on list size (4-8)
        timeout_per_task: Max time per individual task in seconds
        use_progress_bar: Whether to show tqdm progress bar (default True)

    Returns:
        Dictionary mapping display_title -> icon string (may be incomplete)
    """
    result = {}

    if not anime_list:
        return result

    from tqdm import tqdm

    # Dynamically scale workers based on list size (4-8 workers)
    if max_workers is None:
        max_workers = min(8, max(4, len(anime_list) // 3))

    aniskip = AniSkipService()

    # Phase 1: Resolve missing MAL IDs in parallel
    cache = get_cache()
    mal_ids_to_search = []
    mal_id_map = {}  # title -> mal_id

    for title, mal_id in anime_list:
        if mal_id:
            mal_id_map[title] = mal_id
        else:
            mal_ids_to_search.append(title)

    # Batch search MAL IDs if needed
    if mal_ids_to_search:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(aniskip.search_mal_id, title): title for title in mal_ids_to_search
            }

            for future in as_completed(futures):
                title = futures[future]
                try:
                    mal_id = future.result(timeout=timeout_per_task)
                    if mal_id:
                        mal_id_map[title] = mal_id
                except Exception:
                    pass  # Skip if MAL ID lookup fails

    # Phase 2: Fetch skip times in parallel for all anime with MAL IDs
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all skip time checks
        future_to_title = {}
        for title, mal_id in anime_list:
            mal_id = mal_id_map.get(title)  # Use resolved MAL ID if available
            if mal_id:
                # Submit skip check task
                future = executor.submit(_fetch_skip_icon_for_mal_id, aniskip, cache, title, mal_id)
                future_to_title[future] = title
            else:
                # No MAL ID available - skip this anime
                result[title] = ""

        # Collect results as they complete with progress bar
        futures_iter = as_completed(future_to_title)

        # Wrap with tqdm for progress bar
        if use_progress_bar:
            futures_iter = tqdm(
                futures_iter,
                total=len(future_to_title),
                desc=f"Carregando skip times ({len(anime_list)} animes)",
                unit="anime",
                bar_format="{desc}: {bar}| {n_fmt}/{total_fmt}",
                leave=False,  # Remove bar after completion
            )

        for future in futures_iter:
            title = future_to_title[future]
            try:
                icon = future.result(timeout=timeout_per_task)
                result[title] = icon
            except Exception:
                result[title] = ""

    # Fill in any missing anime that couldn't be looked up
    for title, _ in anime_list:
        if title not in result:
            result[title] = ""

    return result


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
        _show_recent_history()  # Now loops internally
        return anilist_main_menu()
    if selection == "📂 Biblioteca Local":
        _show_local_library()  # Now loops internally
        return anilist_main_menu()
    if selection == "🔍 Buscar Anime":
        return _search_and_add_anime(is_logged_in)
    if selection == "🎬 Novos Episódios":
        _show_airing_episodes()  # Now loops internally
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
            logger.info("\n❌ Erro ao carregar informações do usuário")
            input("Pressione Enter para continuar...")
            return

        username = user_info.name
        user_id = user_info.id

        # Get user stats - use API statistics directly
        stats = user_info.statistics
        api_count = stats.anime.count if stats and stats.anime else 0
        api_episodes = stats.anime.episodesWatched if stats and stats.anime else 0
        api_minutes = stats.anime.minutesWatched if stats and stats.anime else 0

        # Use API stats as primary source. Only calculate from lists if API returns 0
        # and API call succeeds (to avoid multiple requests on rate limiting)
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
            status = (activity.status or "").lower()
            progress = activity.progress
            media = activity.media
            if media:
                title = get_search_title(media.title, "Unknown")
                episodes = media.episodes
            else:
                title = "Unknown"
                episodes = None
            emoji = status_emoji.get(status, "•")

            if "watched episode" in status and progress:
                progress_str = str(progress)
                if episodes:
                    activity_msg = f"  {emoji} {title} ({progress_str}/{episodes})"
                else:
                    activity_msg = f"  {emoji} {title} (Ep {progress_str})"
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
    logger.info("\n" + "\n".join(account_info))

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
            logger.info(f"\n🌐 Abrindo: {profile_url}")
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
                    logger.info("\n✅ Logout realizado com sucesso!")
                    input("\nPressione Enter para continuar...")
                    os.system("clear" if os.name != "nt" else "cls")
                    return
                logger.info("\n❌ Token não encontrado")
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
            episodes = _get_episode_count(anime_id, media.episodes) or "?"

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

        # Import here to avoid circular import
        import argparse

        from services.anime_service import anilist_anime_flow

        # Create args object for anilist_anime_flow
        args = argparse.Namespace(debug=False)

        # Convert episodes to int if available (might be "?" for unknown)
        total_episodes = episodes if isinstance(episodes, int) else None

        # Watch the anime (pass both display and search titles)
        # This will go through the normal playback flow where user can choose
        # to download or watch after selecting an episode
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
            logger.info("\n📂 Nenhum histórico encontrado")
            input("\nPressione Enter para voltar...")
            return
        except Exception:
            logger.info("\n❌ Erro ao carregar histórico")
            input("\nPressione Enter para voltar...")
            return

        if not history:
            logger.info("\n📂 Histórico vazio")
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
                        display_name = anilist_client.format_title(anime_info.title)

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
                saved_anilist_id = best_match.id

        # Get anime info for display and total episodes
        total_episodes = None
        anilist_progress = 0
        if saved_anilist_id:
            anime_info = anilist_client.get_anime_by_id(saved_anilist_id)
            if anime_info:
                display_title = anilist_client.format_title(anime_info.title)
                search_title = get_search_title(anime_info.title, display_title)
                # Get total episodes from AniList
                total_episodes = anime_info.episodes

                # Get progress from AniList (source of truth)
                entry = anilist_client.get_media_list_entry(saved_anilist_id)
                if entry and entry.progress:
                    anilist_progress = entry.progress
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

        from services.anime_service import anilist_anime_flow

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
                status = _choose_status()
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


def _format_time_until_airing(airing_at: int | None) -> str:
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


def _show_airing_episodes() -> None:
    """Show airing episodes from watching list with playback flow.

    Displays anime from user's watching list that have new episodes airing,
    sorted by urgency (most episodes behind first). User can select an anime
    to watch starting from their current progress.
    """
    while True:
        # Fetch airing episodes
        with loading("Carregando episódios em transmissão..."):
            service = AiringEpisodesService()
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
                time_until = _format_time_until_airing(entry.airing_at)
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

        # Watch the anime
        anilist_anime_flow(
            search_title,
            entry.anilist_id,
            args,
            anilist_progress=entry.progress,
            display_title=display_title,
            total_episodes=anime_info.episodes,
        )

        # After watching, loop back to show airing episodes list again


def _show_local_library() -> None:
    """Show local anime library menu with full playback flow.

    Delegates to handle_local_library_playback() to ensure consistency
    with the main menu flow, including:
    - Post-playback confirmation ("Você assistiu até o final?")
    - AniList sync with offline queue fallback
    - Navigation menu (Next/Previous/Replay/Back)
    - Playback loop for multiple episodes
    """
    from commands.local_anime import handle_local_library_playback

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
        if user_info:
            pass
    else:
        pass


if __name__ == "__main__":
    # Test menu
    result = anilist_main_menu()
    if result:
        title, anime_id = result
