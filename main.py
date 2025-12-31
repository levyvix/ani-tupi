import argparse
import time
from json import dump, load
from sys import exit

import loader
from config import get_data_path
from loading import loading
from manga_tupi import main as manga_tupi
from menu import menu
from repository import rep
from video_player import play_video

# Use centralized path function from config
HISTORY_PATH = get_data_path()

# AniList to scraper title mappings cache
ANILIST_MAPPINGS_FILE = HISTORY_PATH / "anilist_mappings.json"


def load_anilist_mapping(anilist_id: int) -> str | None:
    """Load saved scraper title for an AniList ID."""
    try:
        with ANILIST_MAPPINGS_FILE.open() as f:
            mappings = load(f)
            return mappings.get(str(anilist_id))
    except (FileNotFoundError, ValueError):
        return None


def save_anilist_mapping(anilist_id: int, scraper_title: str) -> None:
    """Save scraper title choice for an AniList ID."""
    try:
        # Load existing mappings
        try:
            with ANILIST_MAPPINGS_FILE.open() as f:
                mappings = load(f)
        except (FileNotFoundError, ValueError):
            mappings = {}

        # Update mapping
        mappings[str(anilist_id)] = scraper_title

        # Save
        HISTORY_PATH.mkdir(parents=True, exist_ok=True)
        with ANILIST_MAPPINGS_FILE.open("w") as f:
            dump(mappings, f, indent=2)
    except Exception:
        pass


def normalize_anime_title(title: str):
    """Gera variações progressivas do título em lowercase, removendo palavras do final.
    Exemplo: "Attack on Titan Season 2" → ["attack on titan", "attack on", "attack"]
    Todas as saídas são sempre minúsculas.
    """
    import re

    # 1. Remove partes de temporada / cour / part / etc
    season_patterns = [
        r"\s+Season\s+\d+",
        r"\s+\d+(?:st|nd|rd|th)\s+Season",
        r"\s+S\d+",
        r"\s+Part\s+\d+",
        r"\s+Cour\s+\d+",
        r"\s+Arc\s+[^:]+",
        r"\s+Final\s+Season",
        r"\s+2nd\s+Season",
        r"[:−-]\s*Season\s+\d+",
    ]

    cleaned = title
    for pattern in season_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # 2. Mantém apenas letras, números e espaços — remove tudo o mais
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", cleaned)
    # Remove espaços múltiplos e trim
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return [title.strip().lower()]  # fallback em minúsculas

    # 3. Converte tudo para lowercase desde o início
    cleaned = cleaned.lower()

    # 4. Divide em palavras
    words = cleaned.split()

    # 5. Gera as variações (da mais longa para a mais curta)
    variations = []
    for i in range(len(words), 0, -1):
        variant = " ".join(words[:i])
        if variant and variant not in variations:
            variations.append(variant)

    # Remove duplicatas (embora improvável com essa lógica) e mantém ordem
    seen = set()
    result = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            result.append(v)

    return result


def offer_sequel_and_continue(anilist_id: int, current_anime: str, args) -> bool:
    """Check for sequels when last episode is watched and offer to continue.

    Args:
        anilist_id: AniList ID of the anime just watched
        current_anime: Title of the anime being watched
        args: Command line arguments

    Returns:
        True if user accepted sequel and it started playback, False otherwise
    """
    from anilist import anilist_client
    from menu import menu_navigate

    # Only offer sequels if authenticated
    if not anilist_client.is_authenticated():
        return False

    # Get sequels from AniList
    sequels = anilist_client.get_sequels(anilist_id)

    if not sequels:
        return False  # No sequels found

    # Format sequel options
    if len(sequels) == 1:
        sequel = sequels[0]
        sequel_title = anilist_client.format_title(sequel["title"])

        # Single sequel: offer simple confirmation
        choice = menu_navigate(
            ["✅ Sim, continuar", "❌ Não, parar aqui"],
            msg=f"Deseja continuar com a sequência?\n\n→ {sequel_title}",
        )

        if choice == "✅ Sim, continuar":
            # Get sequel info and start playback
            anilist_anime_flow(
                sequel_title,
                sequel["id"],
                args,
                anilist_progress=0,
                display_title=sequel_title,
                total_episodes=sequel.get("episodes"),
            )
            return True
    else:
        # Multiple sequels: let user choose
        sequel_options = [anilist_client.format_title(s["title"]) for s in sequels]

        choice = menu_navigate(
            sequel_options + ["❌ Não, parar aqui"],
            msg="Qual sequência deseja assistir?",
        )

        if choice and choice != "❌ Não, parar aqui":
            # Find selected sequel
            selected_sequel = next((s for s in sequels
                                   if anilist_client.format_title(s["title"]) == choice), None)
            if selected_sequel:
                sequel_title = anilist_client.format_title(selected_sequel["title"])
                anilist_anime_flow(
                    sequel_title,
                    selected_sequel["id"],
                    args,
                    anilist_progress=0,
                    display_title=sequel_title,
                    total_episodes=selected_sequel.get("episodes"),
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
    from anilist import anilist_client
    from scraper_cache import get_cache, set_cache

    loader.load_plugins({"pt-br"}, None if not args.debug else ["animesonlinecc"])

    # Try different title variations
    title_variations = normalize_anime_title(anime_title)
    titles = []
    used_query = None  # Track which query was actually used

    for variant in title_variations:
        rep.clear_search_results()  # Clear previous search results
        with loading(f"Buscando '{variant}'..."):
            rep.search_anime(variant, verbose=False)
        titles = rep.get_anime_titles(filter_by_query=variant, min_score=85)
        if titles:
            used_query = variant
            break  # Found results, stop trying

    manual_search = False
    if not titles:

        # Offer manual search
        from menu import menu_navigate

        choice = menu_navigate(
            ["🔍 Buscar manualmente", "🔙 Voltar ao AniList"], msg="O que deseja fazer?"
        )

        if not choice:
            return  # User cancelled

        if choice == "🔍 Buscar manualmente":
            manual_query = input("\n🔍 Digite o nome para buscar: ")
            rep.clear_search_results()  # Clear previous search results
            with loading(f"Buscando '{manual_query}'..."):
                rep.search_anime(manual_query)
            titles = rep.get_anime_titles(filter_by_query=manual_query, min_score=85)
            used_query = manual_query
            manual_search = True

            if not titles:
                return
        else:
            return  # Back to AniList menu

    # Check if we have a saved title choice from before
    from menu import menu_navigate

    saved_title = load_anilist_mapping(anilist_id) if anilist_id else None

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
        else:
            # User wants to choose a different title - show full menu
            menu_title = f"📺 Anime do AniList: '{display_title}'\n"
            if manual_search:
                menu_title += f"🔍 Busca manual: '{used_query}'\n"
            else:
                menu_title += f"🔍 Busca usada: '{used_query}'\n"
            menu_title += f"\nEncontrados {len(titles)} resultados. Escolha:"

            selected_anime = menu_navigate(titles, msg=menu_title)
            if not selected_anime:
                return  # User cancelled
    else:
        # No saved title or not in results - show full menu
        menu_title = f"📺 Anime do AniList: '{display_title}'\n"
        if manual_search:
            menu_title += f"🔍 Busca manual: '{used_query}'\n"
        else:
            menu_title += f"🔍 Busca usada: '{used_query}'\n"
        menu_title += f"\nEncontrados {len(titles)} resultados. Escolha:"

        selected_anime = menu_navigate(titles, msg=menu_title)
        if not selected_anime:
            return  # User cancelled

    # Save the choice for next time
    if anilist_id:
        save_anilist_mapping(anilist_id, selected_anime)

    # Get episodes (check cache first)
    cache_data = get_cache(selected_anime)
    scraper_episode_count = None

    if cache_data:
        # Use cached data for episode list
        episode_list = cache_data.get("episode_urls", [])
        scraper_episode_count = cache_data.get("episode_count", len(episode_list))
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

    from menu import menu_navigate

    # Check local history for this anime (use max of AniList and local)
    local_progress = 0
    try:
        history_file = HISTORY_PATH / "history.json"
        with history_file.open() as f:
            history_data = load(f)
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
        else:
            episode_idx = option_to_idx[choice]
            # Check if episode is unavailable (marked as None)
            if episode_idx is None:
                print(
                    f"\n⏳ Episódio {max_progress + 1} ainda não disponível nos scrapers."
                )
                input("\nPressione Enter para voltar...")
                return
    else:
        # No progress or progress out of bounds - show full episode list
        selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")

        if not selected_episode:
            return  # User cancelled, go back

        episode_idx = episode_list.index(selected_episode)
    num_episodes = len(episode_list)

    # Playback loop (with AniList sync)
    while True:
        episode = episode_idx + 1
        with loading("Buscando vídeo..."):
            player_url = rep.search_player(selected_anime, episode)
        if args.debug:
            pass
        if not player_url:
            return
        play_video(player_url, args.debug)
        save_history(selected_anime, episode_idx, anilist_id)

        # Ask if watched until the end before updating AniList
        if anilist_client.is_authenticated() and anilist_id:
            from menu import menu_navigate

            confirm_options = ["✅ Sim, assisti até o final", "❌ Não, parei antes."]
            confirm = menu_navigate(
                confirm_options, msg=f"Você assistiu o episódio {episode} até o final?"
            )

            if confirm == "✅ Sim, assisti até o final":
                # Check if anime is in any list
                if not anilist_client.is_in_any_list(anilist_id):
                    print("\n📝 Adicionando à sua lista do AniList...")
                    anilist_client.add_to_list(anilist_id, "CURRENT")
                else:
                    # Auto-promote from PLANNING to CURRENT if needed
                    entry = anilist_client.get_media_list_entry(anilist_id)
                    if entry and entry.get("status") == "PLANNING":
                        print("\n📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                        anilist_client.add_to_list(anilist_id, "CURRENT")

                print(f"\n🔄 Sincronizando progresso com AniList (Ep {episode})...")
                success = anilist_client.update_progress(anilist_id, episode)
                if success:
                    print("✅ Progresso salvo no AniList!")
                else:
                    print("⚠️  Não foi possível salvar no AniList (continuando...)")

                # Check for sequels when last episode is watched
                if episode == num_episodes:
                    if offer_sequel_and_continue(anilist_id, selected_anime, args):
                        return  # Sequel started, exit this flow

        opts = []
        if episode_idx < num_episodes - 1:
            opts.append("▶️  Próximo")
        if episode_idx > 0:
            opts.append("◀️  Anterior")
        opts.append("📋 Escolher outro episódio")
        opts.append("🔙 Voltar")

        from menu import menu_navigate

        selected_opt = menu_navigate(opts, msg="O que quer fazer agora?")

        if not selected_opt or selected_opt == "🔙 Voltar":
            return  # Exit to previous menu
        if selected_opt == "▶️  Próximo":
            episode_idx += 1
        elif selected_opt == "◀️  Anterior":
            episode_idx -= 1
        elif selected_opt == "📋 Escolher outro episódio":
            episode_list = rep.get_episode_list(selected_anime)
            selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                continue  # Stay in current episode menu
            episode_idx = episode_list.index(selected_episode)


def show_main_menu():
    """Display main menu with options."""
    options = [
        "🔍 Buscar Anime",
        "▶️  Continuar Assistindo",
        "📺 AniList",
        "📚 Mangá",
    ]
    return menu(options, msg="Ani-Tupi - Menu Principal")


def search_anime_flow(args):
    """Flow for searching and selecting an anime."""
    query = (
        (input("\n🔍 Pesquise anime: ") if not args.query else args.query)
        if not args.debug
        else "eva"
    )
    rep.clear_search_results()  # Clear previous search results
    with loading(f"Buscando '{query}'..."):
        rep.search_anime(query)
    titles = rep.get_anime_titles(filter_by_query=query, min_score=85)

    if not titles:
        return None, None

    from menu import menu_navigate

    selected_anime = menu_navigate(titles, msg="Escolha o Anime.")

    if not selected_anime:
        return None, None  # User cancelled

    with loading("Carregando episódios..."):
        rep.search_episodes(selected_anime)
    episode_list = rep.get_episode_list(selected_anime)
    selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")

    if not selected_episode:
        return None, None  # User cancelled

    episode_idx = episode_list.index(selected_episode)
    return selected_anime, episode_idx


def main(args) -> None:
    loader.load_plugins({"pt-br"}, None if not args.debug else ["animesonlinecc"])

    # Variables for AniList integration
    anilist_id = None
    anilist_title = None

    # If command-line args provided, skip main menu
    if args.query or args.continue_watching or args.manga:
        if args.continue_watching:
            selected_anime, episode_idx, anilist_id, anilist_title = load_history()
            # Episodes already loaded by load_history()
        else:
            selected_anime, episode_idx = search_anime_flow(args)
            if not selected_anime:
                return
    else:
        # Show main menu (no loop here - user can restart if needed)
        choice = show_main_menu()

        if choice == "🔍 Buscar Anime":
            selected_anime, episode_idx = search_anime_flow(args)
            if not selected_anime:
                return
        elif choice == "▶️  Continuar Assistindo":
            selected_anime, episode_idx, anilist_id, _anilist_title = load_history()
            # Episodes already loaded by load_history()
        elif choice == "📺 AniList":
            from anilist_menu import anilist_main_menu

            # Loop to allow watching multiple anime
            while True:
                result = anilist_main_menu()
                if not result:
                    return  # User cancelled, exit to main menu

                anime_title, anilist_id = result
                anilist_anime_flow(anime_title, anilist_id, args)
                # After watching, loop back to AniList menu
        elif choice == "📚 Mangá":
            manga_tupi()
            return

    num_episodes = len(episode_list)
    while True:
        episode = episode_idx + 1
        with loading("Buscando vídeo..."):
            player_url = rep.search_player(selected_anime, episode)
        if args.debug:
            pass
        play_video(player_url, args.debug)
        save_history(selected_anime, episode_idx, anilist_id)

        # AniList sync (if coming from continue watching with anilist_id)
        if anilist_id:
            from anilist import anilist_client
            from menu import menu_navigate

            if anilist_client.is_authenticated():
                confirm_options = [
                    "✅ Sim, assisti até o final",
                    "❌ Não, parei antes.",
                ]
                confirm = menu_navigate(
                    confirm_options,
                    msg=f"Você assistiu o episódio {episode} até o final?",
                )

                if confirm == "✅ Sim, assisti até o final":
                    # Check if anime is in any list
                    if not anilist_client.is_in_any_list(anilist_id):
                        print("\n📝 Adicionando à sua lista do AniList...")
                        anilist_client.add_to_list(anilist_id, "CURRENT")
                    else:
                        # Auto-promote from PLANNING to CURRENT if needed
                        entry = anilist_client.get_media_list_entry(anilist_id)
                        if entry and entry.get("status") == "PLANNING":
                            print("\n📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                            anilist_client.add_to_list(anilist_id, "CURRENT")

                    print(f"\n🔄 Sincronizando progresso com AniList (Ep {episode})...")
                    success = anilist_client.update_progress(anilist_id, episode)
                    if success:
                        print("✅ Progresso salvo no AniList!")
                    else:
                        print("⚠️  Não foi possível salvar no AniList (continuando...)")

                    # Check for sequels when last episode is watched
                    if episode == num_episodes:
                        if offer_sequel_and_continue(anilist_id, selected_anime, args):
                            return  # Sequel started, exit this flow

        opts = []
        if episode_idx < num_episodes - 1:
            opts.append("▶️  Próximo")
        if episode_idx > 0:
            opts.append("◀️  Anterior")
        opts.append("📋 Escolher outro episódio")
        opts.append("🔙 Voltar")

        from menu import menu_navigate

        selected_opt = menu_navigate(opts, msg="O que quer fazer agora?")

        if not selected_opt or selected_opt == "🔙 Voltar":
            return  # Exit to main menu
        if selected_opt == "▶️  Próximo":
            episode_idx += 1
        elif selected_opt == "◀️  Anterior":
            episode_idx -= 1
        elif selected_opt == "📋 Escolher outro episódio":
            episode_list = rep.get_episode_list(selected_anime)
            selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                continue  # Stay in current episode menu
            episode_idx = episode_list.index(selected_episode)


def load_history():
    """Load watch history and let user choose episode (-1/0/+1 from last watched).

    Old formats:
    - v1: {"anime_name": [episodes_urls, episode_idx], ...}
    - v2: {"anime_name": [timestamp, episode_idx], ...}
    New format:
    - v3: {"anime_name": [timestamp, episode_idx, anilist_id], ...}

    Returns: (anime_name, episode_idx, anilist_id, anilist_title)
    """
    file_path = HISTORY_PATH / "history.json"
    try:
        with file_path.open() as f:
            data = load(f)

            # Migrate old formats to new format if needed
            needs_migration = False
            for anime_name, info in data.items():
                # Check if first element is a list (v1 format)
                if isinstance(info[0], list):
                    needs_migration = True
                    # Migrate: [episodes_urls, episode_idx] → [timestamp, episode_idx, None]
                    data[anime_name] = [int(time.time()), info[1], None]
                # Check if missing anilist_id (v2 format)
                elif len(info) == 2:
                    needs_migration = True
                    # Migrate: [timestamp, episode_idx] → [timestamp, episode_idx, None]
                    data[anime_name] = [info[0], info[1], None]

            # Save migrated data
            if needs_migration:
                with file_path.open("w") as f_write:
                    dump(data, f_write)

            # Build menu with episode info
            titles = {}
            for entry, info in data.items():
                ep_info = f" (Ultimo episódio assistido {info[1] + 1})"
                titles[entry + ep_info] = len(ep_info)

            from menu import menu_navigate

            selected = menu_navigate(list(titles.keys()), msg="Continue assistindo.")

            if not selected:
                exit()  # User cancelled continue watching

            anime = selected[: -titles[selected]]
            last_episode_idx = data[anime][1]
            anilist_id = data[anime][2] if len(data[anime]) > 2 else None

            # If we have anilist_id, get the original AniList title
            anilist_title = None
            if anilist_id:
                from anilist import anilist_client

                anime_info = anilist_client.get_anime_by_id(anilist_id)
                if anime_info:
                    # Use romaji title as primary
                    anilist_title = anime_info.get("title", {}).get("romaji")
                else:
                    pass

            # Search for episodes to offer -1/0/+1 options
            rep.clear_search_results()
            with loading(f"Buscando '{anime}'..."):
                rep.search_anime(anime)
            with loading("Carregando episódios..."):
                rep.search_episodes(anime)
            episode_list = rep.get_episode_list(anime)

            if not episode_list:
                exit()

            # Offer -1/0/+1 options (previous, current, next)
            last_ep_num = last_episode_idx + 1
            options = []
            option_to_idx = {}

            # Previous episode (-1)
            if last_episode_idx > 0:
                prev_ep = f"◀️  Episódio {last_ep_num - 1} (anterior)"
                options.append(prev_ep)
                option_to_idx[prev_ep] = last_episode_idx - 1

            # Current episode (0)
            current_ep = f"▶️  Episódio {last_ep_num} (último assistido)"
            options.append(current_ep)
            option_to_idx[current_ep] = last_episode_idx

            # Next episode (+1)
            if last_episode_idx < len(episode_list) - 1:
                # Next episode exists in the list
                next_ep = f"⏭️  Episódio {last_ep_num + 1} (próximo)"
                options.append(next_ep)
                option_to_idx[next_ep] = last_episode_idx + 1
            else:
                # Next episode doesn't exist yet, but show as unavailable
                next_ep = f"⏭️  Episódio {last_ep_num + 1} (aguardando)"
                options.append(next_ep)
                option_to_idx[next_ep] = None  # Mark as unavailable

            # Add option to choose any episode
            options.append("📋 Escolher outro episódio")

            choice = menu_navigate(options, msg=f"{anime} - De onde quer continuar?")

            if not choice:
                exit()  # User cancelled

            if choice == "📋 Escolher outro episódio":
                # Let user choose from full episode list
                selected_episode = menu_navigate(
                    episode_list, msg="Escolha o episódio."
                )
                if not selected_episode:
                    exit()
                episode_idx = episode_list.index(selected_episode)
            else:
                episode_idx = option_to_idx[choice]
                # Check if episode is unavailable (marked as None)
                if episode_idx is None:
                    print(
                        f"\n⏳ Episódio {last_ep_num + 1} ainda não disponível nos scrapers."
                    )
                    input("\nPressione Enter para voltar...")
                    exit()

        return anime, episode_idx, anilist_id, anilist_title
    except FileNotFoundError:
        exit()
    except PermissionError:
        return None


def save_history(anime, episode, anilist_id=None) -> None:
    """Save watch history with timestamp and optional AniList ID.

    Format: {"anime_name": [timestamp, episode_idx, anilist_id], ...}
    anilist_id can be None for anime not from AniList
    """
    file_path = HISTORY_PATH / "history.json"
    try:
        with file_path.open("r+") as f:
            data = load(f)
            # Save with timestamp and anilist_id (new format)
            data[anime] = [int(time.time()), episode, anilist_id]

        with file_path.open("w") as f:
            dump(data, f)

    except FileNotFoundError:
        HISTORY_PATH.mkdir(parents=True, exist_ok=True)

        with file_path.open("w") as f:
            data = {}
            # Save with timestamp and anilist_id (new format)
            data[anime] = [int(time.time()), episode, anilist_id]
            dump(data, f)

    except PermissionError:
        return


def cli() -> None:
    """Entry point para CLI."""
    parser = argparse.ArgumentParser(
        prog="ani-tupi",
        description="Veja anime sem sair do terminal.",
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    # AniList command
    anilist_parser = subparsers.add_parser("anilist", help="Integração com AniList")
    anilist_parser.add_argument(
        "action",
        nargs="?",
        default="menu",
        choices=["auth", "menu"],
        help="auth: fazer login | menu: navegar listas (padrão)",
    )

    # Main anime command arguments (default)
    parser.add_argument(
        "--query",
        "-q",
    )
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--continue_watching", "-c", action="store_true")
    parser.add_argument("--manga", "-m", action="store_true")
    parser.add_argument(
        "--clear-cache",
        nargs="?",
        const=True,
        metavar="[anime_name]",
        help="Limpar cache (sem argumentos limpa tudo, ou especifique anime para limpar apenas um)",
    )

    args = parser.parse_args()

    # Handle --clear-cache before other commands
    if args.clear_cache is not None:
        from scraper_cache import clear_cache

        if args.clear_cache is True:
            # Clear all cache
            clear_cache()
            print("✅ Cache completamente limpo!")
        else:
            # Clear specific anime
            clear_cache(args.clear_cache)
            print(f"✅ Cache de '{args.clear_cache}' foi limpo!")
        return

    # Handle commands
    if args.command == "anilist":
        from anilist_menu import anilist_main_menu, authenticate_flow

        if args.action == "auth":
            authenticate_flow()
        else:  # menu
            # Loop to allow watching multiple anime without restarting
            while True:
                result = anilist_main_menu()
                if not result:
                    break  # User cancelled/exited

                anime_title, anilist_id = result
                # Start normal flow with selected anime
                anilist_anime_flow(anime_title, anilist_id, args)
                # After watching, loop back to AniList menu
    elif args.manga:
        manga_tupi()
    else:
        main(args)


if __name__ == "__main__":
    cli()
