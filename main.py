import loader
import argparse
from menu import menu
from repository import rep
from loader import PluginInterface
from sys import exit
from video_player import play_video
from json import load, dump
from manga_tupi import main as manga_tupi
from os import name
from pathlib import Path
import time


HISTORY_PATH = Path.home().as_posix() + "/.local/state/ani-tupi/" if name != 'nt' else "C:\\Program Files\\ani-tupi\\"

def normalize_anime_title(title: str) -> list[str]:
    """
    Generate title variations for better scraper matching
    Returns list of possible titles to try
    """
    import re

    variations = [title]  # Original title always first

    # Remove "Season N" / "2nd Season" etc
    season_patterns = [
        r'\s+Season\s+\d+',
        r'\s+\d+(?:st|nd|rd|th)\s+Season',
        r'\s+S\d+',
        r'\s+Part\s+\d+',
    ]

    base_variations = [title]  # Start with original

    for pattern in season_patterns:
        cleaned = re.sub(pattern, '', title, flags=re.IGNORECASE).strip()
        if cleaned and cleaned not in base_variations:
            base_variations.append(cleaned)

    # For each base variation, create case variations
    all_variations = []
    for variant in base_variations:
        # Original
        if variant not in all_variations:
            all_variations.append(variant)

        # Lowercase
        lower = variant.lower()
        if lower != variant and lower not in all_variations:
            all_variations.append(lower)

        # Title Case (Each Word Capitalized)
        title_case = variant.title()
        if title_case != variant and title_case not in all_variations:
            all_variations.append(title_case)

    return all_variations

def anilist_anime_flow(anime_title: str, anilist_id: int, args):
    """
    Flow for anime selected from AniList
    Searches scrapers for the anime and starts normal playback flow
    """
    from anilist import anilist_client

    loader.load_plugins({"pt-br"}, None if not args.debug else ["animesonlinecc"])

    # Try different title variations
    title_variations = normalize_anime_title(anime_title)
    titles = []

    for variant in title_variations:
        print(f"\n🔍 Buscando '{variant}' nos scrapers...")
        rep.clear_search_results()  # Clear previous search results
        rep.search_anime(variant)
        titles = rep.get_anime_titles()
        if titles:
            break  # Found results, stop trying

    if not titles:
        print(f"\n❌ Anime '{anime_title}' não encontrado automaticamente.")
        print("💡 Tentou variações:", ", ".join(f"'{v}'" for v in title_variations))

        # Offer manual search
        from menu import menu_navigate
        choice = menu_navigate(
            ["🔍 Buscar manualmente", "🔙 Voltar ao AniList"],
            msg="O que deseja fazer?"
        )

        if not choice:
            return  # User cancelled

        if choice == "🔍 Buscar manualmente":
            manual_query = input("\n🔍 Digite o nome para buscar: ")
            rep.clear_search_results()  # Clear previous search results
            rep.search_anime(manual_query)
            titles = rep.get_anime_titles()

            if not titles:
                print(f"❌ Nenhum resultado para '{manual_query}'")
                return
        else:
            return  # Back to AniList menu

    # If multiple results, let user choose
    if len(titles) > 1:
        from menu import menu_navigate
        selected_anime = menu_navigate(titles, msg=f"Encontrados {len(titles)} resultados. Escolha:")
        if not selected_anime:
            return  # User cancelled
    else:
        selected_anime = titles[0]
        print(f"✅ Encontrado: {selected_anime}")

    # Get episodes
    rep.search_episodes(selected_anime)
    episode_list = rep.get_episode_list(selected_anime)
    from menu import menu_navigate
    selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")

    if not selected_episode:
        return  # User cancelled, go back

    episode_idx = episode_list.index(selected_episode)
    num_episodes = len(rep.anime_episodes_urls[selected_anime][0][0])

    # Playback loop (with AniList sync)
    while True:
        episode = episode_idx + 1
        player_url = rep.search_player(selected_anime, episode)
        if args.debug: print(player_url)
        play_video(player_url, args.debug)
        save_history(selected_anime, episode_idx)

        # Update AniList progress (only if we have anilist_id)
        if anilist_client.is_authenticated() and anilist_id:
            success = anilist_client.update_progress(anilist_id, episode)
            if success:
                print(f"✅ AniList atualizado: episódio {episode}")
            else:
                print(f"⚠️  Não foi possível atualizar AniList")

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
        elif selected_opt == "▶️  Próximo":
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
    """Display main menu with options"""
    options = [
        "🔍 Buscar Anime",
        "▶️  Continuar Assistindo",
        "📺 AniList",
        "📚 Mangá",
    ]
    return menu(options, msg="Ani-Tupi - Menu Principal")

def search_anime_flow(args):
    """Flow for searching and selecting an anime"""
    query = (input("\n🔍 Pesquise anime: ") if not args.query else args.query) if not args.debug else "eva"
    rep.clear_search_results()  # Clear previous search results
    rep.search_anime(query)
    titles = rep.get_anime_titles()

    if not titles:
        print(f"❌ Nenhum anime encontrado para '{query}'")
        return None, None

    from menu import menu_navigate
    selected_anime = menu_navigate(titles, msg="Escolha o Anime.")

    if not selected_anime:
        return None, None  # User cancelled

    rep.search_episodes(selected_anime)
    episode_list = rep.get_episode_list(selected_anime)
    selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")

    if not selected_episode:
        return None, None  # User cancelled

    episode_idx = episode_list.index(selected_episode)
    return selected_anime, episode_idx

def main(args):
    loader.load_plugins({"pt-br"}, None if not args.debug else ["animesonlinecc"])

    # If command-line args provided, skip main menu
    if args.query or args.continue_watching or args.manga:
        if args.continue_watching:
            selected_anime, episode_idx = load_history()
            # Need to search episodes again (history no longer stores URLs)
            print(f"\n🔍 Buscando episódios de '{selected_anime}'...")
            rep.clear_search_results()  # Clear previous search results
            rep.search_anime(selected_anime)
            rep.search_episodes(selected_anime)
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
            selected_anime, episode_idx = load_history()
            # Need to search episodes again (history no longer stores URLs)
            print(f"\n🔍 Buscando episódios de '{selected_anime}'...")
            rep.clear_search_results()  # Clear previous search results
            rep.search_anime(selected_anime)
            rep.search_episodes(selected_anime)
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

    num_episodes = len(rep.anime_episodes_urls[selected_anime][0][0])
    while True:
        episode = episode_idx + 1
        player_url = rep.search_player(selected_anime, episode)
        if args.debug: print(player_url)
        play_video(player_url, args.debug)
        save_history(selected_anime, episode_idx)

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
        elif selected_opt == "▶️  Próximo":
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
    """
    Load watch history and migrate old format if needed

    Old format: {"anime_name": [episodes_urls, episode_idx], ...}
    New format: {"anime_name": [timestamp, episode_idx], ...}
    """
    file_path = HISTORY_PATH + "history.json"
    try:
        with open(file_path, "r") as f:
            data = load(f)

            # Migrate old format to new format if needed
            needs_migration = False
            for anime_name, info in data.items():
                # Check if first element is a list (old format)
                if isinstance(info[0], list):
                    needs_migration = True
                    # Migrate: [episodes_urls, episode_idx] → [timestamp, episode_idx]
                    data[anime_name] = [int(time.time()), info[1]]

            # Save migrated data
            if needs_migration:
                print("⚙️  Migrando histórico para novo formato...")
                with open(file_path, "w") as f_write:
                    dump(data, f_write)

            # Build menu with episode info
            titles = dict()
            for entry, info in data.items():
                ep_info = f" (Ultimo episódio assistido {info[1] + 1})"
                titles[entry + ep_info] = len(ep_info)

            from menu import menu_navigate
            selected = menu_navigate(list(titles.keys()), msg="Continue assistindo.")

            if not selected:
                exit()  # User cancelled continue watching

            anime = selected[:-titles[selected]]
            episode_idx = data[anime][1]

            # Note: We no longer restore episodes_urls from history
            # User will need to search for the anime again to get fresh URLs

        return anime, episode_idx
    except FileNotFoundError:
        print("Sem histórico de animes")
        exit()
    except PermissionError:
        print("Sem permissão para ler arquivos.")
        return

def save_history(anime, episode):
    """
    Save watch history with timestamp

    Format: {"anime_name": [timestamp, episode_idx], ...}
    """
    file_path = HISTORY_PATH + "history.json"
    try:
        with open(file_path, "r+") as f:
            data = load(f)
            # Save with timestamp (new format)
            data[anime] = [int(time.time()), episode]

        with open(file_path, "w") as f:
            dump(data, f)

    except FileNotFoundError:
        Path(HISTORY_PATH).mkdir(parents=True, exist_ok=True)

        with open(file_path, "w") as f:
            data = dict()
            # Save with timestamp (new format)
            data[anime] = [int(time.time()), episode]
            dump(data, f)

    except PermissionError:
        print("Não há permissão para criar arquivos.")
        return

def cli():
    """Entry point para CLI"""
    parser = argparse.ArgumentParser(
                prog = "ani-tupi",
                description="Veja anime sem sair do terminal.",
            )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    # AniList command
    anilist_parser = subparsers.add_parser("anilist", help="Integração com AniList")
    anilist_parser.add_argument("action", nargs="?", default="menu", choices=["auth", "menu"],
                                help="auth: fazer login | menu: navegar listas (padrão)")

    # Main anime command arguments (default)
    parser.add_argument("--query", "-q",)
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--continue_watching", "-c", action="store_true")
    parser.add_argument("--manga", "-m", action="store_true")

    args = parser.parse_args()

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


if __name__=="__main__":
    cli()

