"""AniList integration flows for anime playback.

Handles AniList-specific anime flows including search, selection, progress tracking,
sequel detection, and synchronization with AniList API.
"""

import json
from typing import Optional

from models.config import get_data_path, settings
from services.anilist_service import anilist_client
from services.repository import rep
from ui.components import loading, menu_navigate
from utils.scraper_cache import get_cache, set_cache
from scrapers import loader
from models.models import Status
from services.history_service import save_history, reset_history
from utils.video_player import VideoPlayer
from services.anime.source_management import switch_anime_source
from services.anime.mappings import (
    load_anilist_mapping,
    save_anilist_mapping,
)
from services.anime.search import incremental_search_anime

# Use centralized path function from config
HISTORY_PATH = get_data_path()


def offer_sequel_and_continue(
    anilist_id: int,
    args,
    current_episode: Optional[int] = None,
    anilist_episodes: Optional[int] = None,
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
    # Only offer sequels if authenticated
    if not anilist_client.is_authenticated():
        return False

    # If we know the AniList episode count, check if series is actually complete
    # This prevents offering sequels when the current source has fewer episodes
    if anilist_episodes and current_episode:
        if current_episode < anilist_episodes:
            # User has more episodes to watch - don't offer sequel
            print(
                f"\n💡 Existem mais {anilist_episodes - current_episode} episódio(s) disponível(is) em outras fontes."
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

        # Single sequel: offer simple confirmation
        choice = menu_navigate(
            ["✅ Sim, continuar", "❌ Não, parar aqui"],
            msg=f"Deseja continuar com a sequência?\n\n→ {sequel_title}",
        )

        if choice == "✅ Sim, continuar":
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
    else:
        # Multiple sequels: let user choose
        sequel_options = [anilist_client.format_title(s.title) for s in sequels]

        choice = menu_navigate(
            sequel_options + ["❌ Não, parar aqui"],
            msg="Qual sequência deseja assistir?",
        )

        if choice and choice != "❌ Não, parar aqui":
            # Find selected sequel
            selected_sequel = next(
                (s for s in sequels if anilist_client.format_title(s.title) == choice), None
            )
            if selected_sequel:
                sequel_title = anilist_client.format_title(selected_sequel.title)
                anilist_anime_flow(
                    sequel_title,
                    selected_sequel.id,
                    args,
                    anilist_progress=0,
                    display_title=sequel_title,
                    total_episodes=selected_sequel.episodes,
                )
                return True

    return False


def anilist_anime_flow(
    anime_title: str,
    anilist_id: int,
    args,
    anilist_progress: int = 0,
    display_title: str | None = None,
    total_episodes: int | None = None,
) -> None:
    """Flow for anime selected from AniList
    Searches scrapers for the anime and starts normal playback flow.

    Args:
        anime_title: Title to search for (romaji or english)
        anilist_id: AniList ID for syncing
        args: Command line arguments
        anilist_progress: Current episode progress from AniList (0 if not watching)
        display_title: Full bilingual title for display (romaji / english)
        total_episodes: Total number of episodes from AniList (None if unknown)

    """
    # Use display_title if provided, otherwise fall back to anime_title
    if not display_title:
        display_title = anime_title

    # Get full anime info from AniList to access both English and Romaji titles
    anime_info = anilist_client.get_anime_by_id(anilist_id)
    if anime_info:
        english_title = anime_info.title.english
        romaji_title = anime_info.title.romaji

        # Build language selection menu (only if both titles exist and are different)
        if english_title and romaji_title and english_title != romaji_title:
            language_options = [
                f"🇬🇧 Inglês: {english_title}",
                f"🇯🇵 Romanji: {romaji_title}",
            ]
            language_choice = menu_navigate(language_options, msg="Escolha o idioma para buscar:")

            if not language_choice:
                return  # User cancelled

            # Set anime_title based on choice
            if language_choice.startswith("🇬🇧"):
                anime_title = english_title
            else:
                anime_title = romaji_title

    loader.load_plugins({"pt-br"})  # type: ignore

    # Clear previous search results to avoid accumulating data from previous calls
    # (Repository is singleton, so it keeps data between calls)
    rep.clear_search_results()

    # Store anilist_id in repository for caching (cache key)
    if anilist_id:
        rep.anime_to_anilist_id[anime_title] = anilist_id

    # Show active sources
    active_sources = rep.get_active_sources()
    if active_sources:
        print(f"ℹ️  Fontes ativas: {', '.join(active_sources)}")

    # Cache-first: Check if anime_title is in cache before searching
    cache_data = get_cache(anime_title)
    search_state = None
    titles_with_sources = None
    used_query = None
    source = None

    if cache_data:
        # Found in cache! Use it directly
        print(f"ℹ️  Usando cache ({cache_data.episode_count} eps disponíveis)")
        rep.load_from_cache(anime_title, cache_data)

        # Discover available sources for this anime (background search)
        rep.search_anime(anime_title, verbose=False)

        used_query = anime_title
        titles_with_sources = rep.get_anime_titles_with_sources(
            filter_by_query=anime_title, original_query=anime_title
        )
        if not titles_with_sources:
            titles_with_sources = [anime_title]
    else:
        # Not in cache: use incremental search
        search_state, titles_with_sources = incremental_search_anime(anime_title)

        # Extract the query that was actually used for the final results
        if search_state:
            current_result_set = search_state.get_current()
            if current_result_set:
                used_query = current_result_set.query

    if not titles_with_sources:
        # Offer manual search
        choice = menu_navigate(
            ["🔍 Buscar manualmente", "🔙 Voltar ao AniList"], msg="O que deseja fazer?"
        )

        if not choice:
            return  # User cancelled

        if choice == "🔍 Buscar manualmente":
            manual_query = input("\n🔍 Digite o nome para buscar: ")

            # Cache-first: Check if manual query is in cache
            cache_data = get_cache(manual_query)
            if cache_data:
                print(f"ℹ️  Usando cache ({cache_data.episode_count} eps disponíveis)")
                rep.load_from_cache(manual_query, cache_data)

                # Discover available sources for this anime (background search)
                rep.search_anime(manual_query, verbose=False)

                # Get formatted title with sources from scrapers
                titles_with_sources = rep.get_anime_titles_with_sources(
                    filter_by_query=manual_query, original_query=manual_query
                )
                if not titles_with_sources:
                    titles_with_sources = [manual_query]

                used_query = manual_query
                search_state = None  # No navigation state for manual cached search
            else:
                # Not in cache: use incremental search for manual query
                search_state, titles_with_sources = incremental_search_anime(manual_query)

                # Extract the query that was actually used for the final results
                if search_state:
                    current_result_set = search_state.get_current()
                    if current_result_set:
                        used_query = current_result_set.query

            if not titles_with_sources:
                return
        else:
            return  # Back to AniList menu

    # Check if we have a saved title choice from before
    saved_title = load_anilist_mapping(anilist_id) if anilist_id else None

    # Convert titles with sources to plain titles for saved title check
    titles = [t.split(" [")[0] for t in titles_with_sources]

    # Loop to allow navigation between result sets and selection
    selected_anime = None
    while selected_anime is None:
        # If we have a saved title and it's in the current results, ask user if they want to keep it
        if saved_title and saved_title in titles:
            # Ask user if they want to continue with saved choice
            choice = menu_navigate(
                ["✅ Continuar com este", "🔄 Escolher outro"],
                msg=f"Você usou '{saved_title}' antes.\nQuer continuar?",
            )

            if not choice:
                return  # User cancelled

            if choice == "✅ Continuar com este":
                selected_anime = saved_title
                break  # Exit while loop

        # Show menu with optional navigation if search_state exists
        menu_title = f"📺 Anime do AniList: '{display_title}'\n"

        # Show search result set info if using incremental search
        if search_state:
            current_result_set = search_state.get_current()
            if current_result_set:
                # Use the normalized used_query from the result set
                display_query = current_result_set.used_query or current_result_set.query
                menu_title += f"🔍 Busca usada: '{display_query}'\n"
                menu_title += f"   ({current_result_set.word_count} palavras: {len(current_result_set.results)} resultados)\n"
        else:
            # For cache hits, use the query that was already used
            display_query = used_query or anime_title
            menu_title += f"🔍 Busca usada: '{display_query}'\n"

        menu_title += f"\nEncontrados {len(titles_with_sources)} resultados. Escolha:"

        # Show pagination if too many results
        SHOW_MORE_BUTTON = "📋 Ver todos os resultados"
        top_limit = settings.search.top_results_limit
        titles_to_show = titles_with_sources[:top_limit]
        has_more = len(titles_with_sources) > top_limit

        # Build menu options
        titles_with_button = []
        if has_more:
            titles_with_button.append(SHOW_MORE_BUTTON)
        titles_with_button.extend(titles_to_show)

        # Show menu with navigation support
        selected_anime_with_source = menu_navigate(
            titles_with_button, msg=menu_title, search_state=search_state
        )

        # Handle "Show all" button
        if selected_anime_with_source == SHOW_MORE_BUTTON:
            # Show all results in next menu
            titles_with_button = titles_with_sources.copy()
            selected_anime_with_source = menu_navigate(
                titles_with_button, msg=menu_title, search_state=search_state
            )

        if not selected_anime_with_source:
            return  # User cancelled

        # Handle incremental search navigation
        if selected_anime_with_source == "__nav_previous__":
            # Navigate to previous result set
            assert search_state is not None
            search_state.go_back()
            new_result_set = search_state.get_current()
            assert new_result_set is not None
            titles_with_sources = new_result_set.results
            titles = [t.split(" [")[0] for t in titles_with_sources]
            continue  # Loop back to show menu with new results

        elif selected_anime_with_source == "__nav_next__":
            # Navigate to next result set
            assert search_state is not None
            search_state.go_forward()
            new_result_set = search_state.get_current()
            assert new_result_set is not None
            titles_with_sources = new_result_set.results
            titles = [t.split(" [")[0] for t in titles_with_sources]
            continue  # Loop back to show menu with new results

        else:
            # Remove source tag from selected anime
            selected_anime = selected_anime_with_source.split(" [")[0]
            # Extract source (if present)
            source = None
            if " [" in selected_anime_with_source and selected_anime_with_source.endswith("]"):
                source = selected_anime_with_source.split(" [")[1].rstrip("]")
            break  # Exit while loop

    # Save the choice for next time (with original search title for "Trocar fonte")
    if anilist_id:
        save_anilist_mapping(anilist_id, selected_anime, search_title=anime_title)

    # Get episodes (check cache first)
    cache_data = get_cache(selected_anime)
    scraper_episode_count = None

    if cache_data:
        # Use cached data for episode list
        episode_list = cache_data.episode_urls
        scraper_episode_count = cache_data.episode_count
        print(f"ℹ️  Usando cache ({scraper_episode_count} eps disponíveis)")

        # Still need to populate repository for video URL search
        # (cache only stores episode titles, not the URLs needed for playback)
        rep.search_episodes(selected_anime)
    else:
        # Fetch from scrapers
        with loading("Carregando episódios..."):
            rep.search_episodes(selected_anime)
        episode_list = rep.get_episode_list(selected_anime)
        scraper_episode_count = len(episode_list)

        # Save to cache
        set_cache(selected_anime, scraper_episode_count, episode_list)

    # Check local history for this anime (use max of AniList and local)
    local_progress = 0
    try:
        history_file = HISTORY_PATH / "history.json"
        with history_file.open() as f:
            history_data = json.load(f)
            if selected_anime in history_data:
                # history stores episode_idx (0-based), progress is 1-based
                local_progress = history_data[selected_anime][1] + 1
    except (FileNotFoundError, KeyError, IndexError):
        pass  # No local history

    # Use maximum of AniList and local progress (never go backwards)
    max_progress = max(anilist_progress, local_progress)

    # If user has progress (from AniList or local), offer to continue from there
    if max_progress > 0 and max_progress <= len(episode_list):
        # Offer -1/0/+1 options (previous, current, next)
        # Using max_progress to never go backwards
        options = []
        option_to_idx = {}

        # Show source of progress
        progress_source = ""
        if max_progress == anilist_progress and max_progress == local_progress:
            progress_source = "AniList + Local"
        elif max_progress == anilist_progress:
            progress_source = "AniList"
        elif max_progress == local_progress:
            progress_source = "Local"

        # Previous episode (-1)
        if max_progress > 1:
            prev_ep = f"◀️  Episódio {max_progress - 1} (anterior)"
            options.append(prev_ep)
            option_to_idx[prev_ep] = max_progress - 2

        # Current episode (max progress)
        current_ep = f"▶️  Episódio {max_progress} ({progress_source})"
        options.append(current_ep)
        option_to_idx[current_ep] = max_progress - 1

        # Next episode (+1)
        if max_progress < len(episode_list):
            # Next episode exists in the list (available in scrapers)
            next_ep = f"⏭️  Episódio {max_progress + 1} (próximo)"
            options.append(next_ep)
            option_to_idx[next_ep] = max_progress
        elif total_episodes and max_progress < total_episodes:
            # Next episode exists according to AniList but not in scrapers yet
            next_ep = f"⏭️  Episódio {max_progress + 1} (aguardando)"
            options.append(next_ep)
            option_to_idx[next_ep] = None  # Mark as unavailable
        # If neither condition is true, anime is complete (don't show next episode)

        # Add option to choose any episode
        options.append("📋 Escolher outro episódio")
        options.append("🔄 Começar do zero")

        # Build menu message with episode availability info
        menu_msg = f"{selected_anime} - De onde quer continuar?"
        if total_episodes and scraper_episode_count:
            menu_msg += f"\n📊 {scraper_episode_count} eps disponíveis / {total_episodes} total"
        elif scraper_episode_count:
            menu_msg += f"\n📊 {scraper_episode_count} eps disponíveis"

        choice = menu_navigate(options, msg=menu_msg)

        if not choice:
            return  # User cancelled

        if choice == "📋 Escolher outro episódio":
            # Let user choose from full episode list
            selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                return
            episode_idx = episode_list.index(selected_episode)
        elif choice == "🔄 Começar do zero":
            # Confirm before resetting
            confirm_reset = menu_navigate(
                ["✅ Sim, resetar", "❌ Cancelar"],
                msg="Tem certeza que quer começar do zero? Seu progresso será perdido.",
            )
            if confirm_reset == "✅ Sim, resetar":
                reset_history(selected_anime)
                episode_idx = 0
                print("✅ Histórico resetado! Começando do episódio 1...")
            else:
                return  # User cancelled
        else:
            episode_idx = option_to_idx[choice]
            # Check if episode is unavailable (marked as None)
            if episode_idx is None:
                print(f"\n⏳ Episódio {max_progress + 1} ainda não disponível nos scrapers.")
                input("\nPressione Enter para voltar...")
                return
    else:
        # No progress or progress out of bounds - show full episode list
        selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")

        if not selected_episode:
            return  # User cancelled, go back

        episode_idx = episode_list.index(selected_episode)

    # At this point, episode_idx is guaranteed to be int, not None
    if not isinstance(episode_idx, int):
        raise ValueError(f"episode_idx should be int, got {type(episode_idx)}")

    current_episode_idx: int = episode_idx
    num_episodes = len(episode_list)

    # Ask what user wants to do with the first episode
    initial_episode = current_episode_idx + 1
    action_options = ["▶️ Assistir agora", "📥 Baixar para assistir depois", "🔙 Voltar"]
    initial_action = menu_navigate(
        action_options, msg=f"O que deseja fazer com o episódio {initial_episode}?"
    )

    if initial_action == "📥 Baixar para assistir depois":
        # Download episodes starting from current
        from services.anime.download_service import AnimeDownloadService
        from utils.episode_range_parser import parse_episode_range, RangeParseError

        print(f"\n📥 Baixar episódios: {selected_anime}")
        print(f"   Total de episódios: {num_episodes}")

        # Calculate default range (from current episode to end)
        default_range = f"{initial_episode}-"
        print(f"   Padrão: {default_range} (do episódio {initial_episode} até o fim)\n")

        # Prompt for range
        try:
            range_input = input("Qual intervalo? (pressione Enter para padrão): ").strip()

            if not range_input:
                range_input = default_range
                print(f"   Usando: {range_input}")

            # Parse range
            episodes = parse_episode_range(range_input, num_episodes)
        except RangeParseError as e:
            print(f"❌ {e}")
            return

        # Download episodes
        service = AnimeDownloadService()

        def get_episode_url_for_download(episode_num: int):
            """Get episode URL for download."""
            player_url = rep.search_player(selected_anime, episode_num)
            if player_url:
                return (player_url, source or "unknown")
            return None

        print(f"\n⏳ Baixando {len(episodes)} episódio(s)...")
        try:
            with loading(f"Baixando {len(episodes)} episódio(s)..."):
                result = service.download_episodes(
                    anime_title=selected_anime,
                    range_input=range_input,
                    total_episodes=num_episodes,
                    get_episode_url=get_episode_url_for_download,
                )

            # Show result
            print(f"\n{result.summary}")

            if result.successful > 0:
                print(f"✅ {result.successful} episódio(s) baixado(s) com sucesso!")
                print(f"   Localização: {service.download_dir / selected_anime}")
        except Exception as e:
            print(f"❌ Erro ao baixar: {e}")
        return
    elif initial_action != "▶️ Assistir agora":
        # User cancelled
        return

    # Initialize video player for this session
    player = VideoPlayer()

    # Playback loop (with AniList sync)
    while True:
        episode = current_episode_idx + 1

        # Get video URL from scraper plugins
        with loading("Buscando vídeo..."):
            player_url = rep.search_player(selected_anime, episode)

        # Check if video URL was found
        if not player_url:
            print("❌ Nenhuma fonte conseguiu extrair o vídeo.")
            print("   💡 O episódio está indisponível em todas as fontes.")
            continue

        # Play episode with IPC support
        from utils.video_player import _format_episode_progress

        progress_str = _format_episode_progress(episode, num_episodes, total_episodes)
        print(f"\n▶️  Iniciando reprodução do episódio {progress_str}...")
        print(f"   Fonte: {source or 'unknown'}")
        print(f"   URL: {player_url[:80]}{'...' if len(player_url) > 80 else ''}\n")

        result = player.play_episode(
            url=player_url,
            anime_title=selected_anime,
            episode_number=episode,
            total_episodes=num_episodes,
            source=source or "unknown",
            use_ipc=True,
            debug=args.debug,
            anilist_id=anilist_id,
            anilist_episodes=total_episodes,
        )

        print("\n📊 Reprodução encerrada:")
        print(f"   Exit code: {result.exit_code}")
        print(f"   Ação: {result.action}")

        # Handle IPC navigation actions
        if result.action == "next":
            # User pressed Shift+N - already saved history and synced AniList in IPC handler
            # Move to next episode automatically
            if result.data and "episode" in result.data:
                next_episode = result.data["episode"]
                if next_episode <= num_episodes:
                    episode_idx = next_episode - 1
                    current_episode_idx = next_episode - 1  # CRITICAL: sync both variables
                    # Check for sequels when last episode is watched
                    if next_episode == num_episodes:
                        # Get AniList episode count to check if series is truly complete
                        anilist_episodes = None
                        if anilist_id:
                            anime_info = anilist_client.get_anime_by_id(anilist_id)
                            if anime_info:
                                anilist_episodes = anime_info.episodes

                        if offer_sequel_and_continue(
                            anilist_id,
                            args,
                            current_episode=next_episode,
                            anilist_episodes=anilist_episodes,
                        ):
                            return  # Sequel started, exit this flow
                    continue  # Loop to play next episode
            # Fall through to menu if no next episode data
        elif result.action == "quit":
            # User quit (may have used Shift+N/P to load different episode before quitting)
            # Sync episode_idx with the final episode number from IPC context
            if result.data and "episode" in result.data:
                final_episode = result.data["episode"]
                if final_episode >= 1 and final_episode <= num_episodes:
                    episode_idx = final_episode - 1
                    current_episode_idx = final_episode - 1  # CRITICAL: sync both variables
                    episode = final_episode
        elif result.action == "auto-next":
            # Auto-play active and user pressed 'q' - already marked as watched in IPC handler
            # Sync with AniList and move to next episode
            current_episode = result.data.get("episode", episode) if result.data else episode

            # Update AniList if authenticated
            if anilist_client.is_authenticated() and anilist_id:
                # Check if anime is in any list
                if not anilist_client.is_in_any_list(anilist_id):
                    print("📝 Adicionando à sua lista do AniList...")
                    anilist_client.add_to_list(anilist_id, Status.CURRENT)
                else:
                    # Auto-promote from PLANNING to CURRENT, or CURRENT to COMPLETED
                    entry = anilist_client.get_media_list_entry(anilist_id)
                    if entry:
                        if entry.status == "PLANNING":
                            print("📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                            anilist_client.add_to_list(anilist_id, Status.CURRENT)
                        elif entry.status == "CURRENT":
                            # If finishing last episode of a watched anime, mark as completed
                            if current_episode == num_episodes:
                                print("✅ Marcando como 'Completo'...")
                                anilist_client.change_status(anilist_id, Status.COMPLETED)
                        # If already COMPLETED, leave it as is (don't change to REPEATING)
                        # User can manually change status to REPEATING if they want to track rewatches

                print(f"🔄 Sincronizando progresso com AniList (Ep {current_episode})...")
                success = anilist_client.update_progress(anilist_id, current_episode)
                if success:
                    print("✅ Progresso salvo no AniList!")
                else:
                    # Verify token is still valid if sync failed
                    viewer = anilist_client.get_viewer_info()
                    if not viewer:
                        print("⚠️  Token do AniList expirou")
                        print("   Execute: ani-tupi anilist auth")
                    else:
                        print("⚠️  Não foi possível salvar no AniList (continuando...)")

            # Check if there's a next episode
            # Use current_episode (from IPC context) instead of episode_idx
            # because episode_idx may be stale if Shift+N/P was used to load episodes
            # current_episode is 1-indexed, so convert to 0-indexed for episode_idx
            episode_idx = current_episode - 1  # Convert 1-indexed to 0-indexed
            current_episode_idx = current_episode - 1  # CRITICAL: sync both variables
            next_episode_idx = episode_idx + 1
            if next_episode_idx < num_episodes:
                # Move to next episode
                episode_idx = next_episode_idx
                current_episode_idx = next_episode_idx  # CRITICAL: sync both variables
                print(f"▶️  Carregando próximo episódio: {episode_idx + 1}")
                continue  # Loop to play next episode
            else:
                # Last episode - check for sequels
                print("✅ Último episódio assistido!")
                # Get AniList episode count to check if series is truly complete
                anilist_episodes = None
                if anilist_id:
                    anime_info = anilist_client.get_anime_by_id(anilist_id)
                    if anime_info:
                        anilist_episodes = anime_info.episodes

                if anilist_id and offer_sequel_and_continue(
                    anilist_id,
                    args,
                    current_episode=current_episode,
                    anilist_episodes=anilist_episodes,
                ):
                    return  # Sequel started, exit this flow
                # No sequel or user declined - return to menu
                return
        elif result.action == "previous":
            # User pressed Shift+P - go to previous episode
            if result.data and "episode" in result.data:
                prev_episode = result.data["episode"]
                if prev_episode >= 1:
                    episode_idx = prev_episode - 1
                    current_episode_idx = prev_episode - 1  # CRITICAL: sync both variables
                    continue  # Loop to play previous episode
            # Fall through to menu if no previous episode data
        elif result.action == "reload":
            # User pressed Shift+R - reload current episode
            continue  # Loop to replay same episode
        elif result.action == "mark-menu":
            # User pressed Shift+M - mark watched and show menu
            # History already saved in IPC handler, just show menu
            pass
        elif result.exit_code not in [0, 3]:  # Error cases
            print(f"⚠️  MPV exit code: {result.exit_code}")
            if result.exit_code == 2:
                print(" (Possível erro ao reproduzir ou janela fechada)")
                continue

        # For normal quit or other actions, show confirmation menu
        # (History/AniList sync already handled by IPC if action was "next")
        if result.action != "next":
            # Only clear terminal if playback was successful (exit_code == 0)
            # If there was an error, keep messages visible for 2 seconds

            if result.exit_code != 0:
                # Error occurred - give user time to see error messages
                print("\n⏳ Pressione Enter para continuar...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass

            # Ask if watched until the end before saving/updating anything
            confirm_options = ["✅ Sim, assisti até o final", "❌ Não, parei antes."]
            confirm = menu_navigate(
                confirm_options,
                msg=f"Você assistiu o episódio {episode} de '{selected_anime}' até o final?",
            )

            # Only save history and update AniList if user confirmed
            if confirm == "✅ Sim, assisti até o final":
                save_history(selected_anime, episode_idx, anilist_id, source)

                # Update AniList if authenticated
                if anilist_client.is_authenticated() and anilist_id:
                    # Check if anime is in any list
                    if not anilist_client.is_in_any_list(anilist_id):
                        print("\n📝 Adicionando à sua lista do AniList...")
                        anilist_client.add_to_list(anilist_id, "CURRENT")
                    else:
                        # Auto-promote from PLANNING to CURRENT, or CURRENT to COMPLETED
                        entry = anilist_client.get_media_list_entry(anilist_id)
                        if entry:
                            if entry.status == "PLANNING":
                                print("\n📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                                anilist_client.add_to_list(anilist_id, "CURRENT")
                            elif entry.status == "CURRENT":
                                # If finishing last episode of a watched anime, mark as completed
                                if episode == num_episodes:
                                    print("\n✅ Marcando como 'Completo'...")
                                    anilist_client.change_status(anilist_id, Status.COMPLETED)
                            # If already COMPLETED, leave it as is (don't change to REPEATING)
                            # User can manually change status to REPEATING if they want to track rewatches

                    print(f"\n🔄 Sincronizando progresso com AniList (Ep {episode})...")
                    success = anilist_client.update_progress(anilist_id, episode)
                    if success:
                        print("✅ Progresso salvo no AniList!")
                    else:
                        # Verify token is still valid if sync failed
                        viewer = anilist_client.get_viewer_info()
                        if not viewer:
                            print("⚠️  Token do AniList expirou")
                            print("   Execute: ani-tupi anilist auth")
                        else:
                            print("⚠️  Não foi possível salvar no AniList (continuando...)")

                    # Check for sequels when last episode is watched
                    if episode == num_episodes:
                        # Get AniList episode count to check if series is truly complete
                        anilist_episodes = None
                        if anilist_id:
                            anime_info = anilist_client.get_anime_by_id(anilist_id)
                            if anime_info:
                                anilist_episodes = anime_info.episodes

                        if offer_sequel_and_continue(
                            anilist_id,
                            args,
                            current_episode=episode,
                            anilist_episodes=anilist_episodes,
                        ):
                            return  # Sequel started, exit this flow
            else:
                # User didn't finish - don't save anything, just continue to menu
                pass

        opts = []
        if current_episode_idx < num_episodes - 1:
            opts.append("▶️  Próximo")
        if current_episode_idx > 0:
            opts.append("◀️  Anterior")
        opts.append("🔁 Replay")
        opts.append("📋 Escolher outro episódio")
        opts.append("🔄 Trocar fonte")

        selected_opt = menu_navigate(opts, msg="O que quer fazer agora?")

        if not selected_opt or selected_opt == "🔙 Voltar":
            return  # Exit to previous menu
        if selected_opt == "▶️  Próximo":
            current_episode_idx += 1
            episode_idx = current_episode_idx  # CRITICAL: sync both variables
        elif selected_opt == "◀️  Anterior":
            current_episode_idx -= 1
            episode_idx = current_episode_idx  # CRITICAL: sync both variables
        elif selected_opt == "🔁 Replay":
            # Keep same episode_idx, loop continues to replay
            pass
        elif selected_opt == "📋 Escolher outro episódio":
            episode_list = rep.get_episode_list(selected_anime)
            selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                return  # User cancelled, go back
            episode_idx = episode_list.index(selected_episode)  # CRITICAL: sync both variables
            current_episode_idx = episode_list.index(selected_episode)
        elif selected_opt == "🔄 Trocar fonte":
            new_anime, new_episode_idx = switch_anime_source(
                selected_anime, args, anilist_id, display_title
            )
            if new_anime:
                selected_anime = new_anime
                episode_idx = new_episode_idx
                current_episode_idx = new_episode_idx  # CRITICAL: sync both variables
                num_episodes = len(rep.get_episode_list(selected_anime))
                # Continue loop with new anime/episode
