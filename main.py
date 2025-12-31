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


HISTORY_PATH = Path.home().as_posix() + "/.local/state/ani-tupi/" if name != 'nt' else "C:\\Program Files\\ani-tupi\\"

def anilist_anime_flow(anime_title: str, anilist_id: int, args):
    """
    Flow for anime selected from AniList
    Searches scrapers for the anime and starts normal playback flow
    """
    from anilist import anilist_client

    loader.load_plugins({"pt-br"}, None if not args.debug else ["animesonlinecc"])

    print(f"\n🔍 Buscando '{anime_title}' nos scrapers...")

    # Search anime in scrapers
    rep.search_anime(anime_title)
    titles = rep.get_anime_titles()

    if not titles:
        print(f"❌ Anime '{anime_title}' não encontrado nos scrapers.")
        print("Tente outro anime ou busque manualmente.")
        return

    # If multiple results, let user choose
    if len(titles) > 1:
        selected_anime = menu(titles, msg=f"Encontrados {len(titles)} resultados. Escolha:")
    else:
        selected_anime = titles[0]
        print(f"✅ Encontrado: {selected_anime}")

    # Get episodes
    rep.search_episodes(selected_anime)
    episode_list = rep.get_episode_list(selected_anime)
    selected_episode = menu(episode_list, msg="Escolha o episódio.")

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
            opts.append("Próximo")
        if episode_idx > 0:
            opts.append("Anterior")

        selected_opt = menu(opts, msg="O que quer fazer agora?")

        if selected_opt == "Próximo":
            episode_idx += 1
        elif selected_opt == "Anterior":
            episode_idx -= 1

def main(args):
    loader.load_plugins({"pt-br"}, None if not args.debug else ["animesonlinecc"])

    if not args.continue_watching:
        query = (input("Pesquise anime: ") if not args.query else args.query) if not args.debug else "eva"
        rep.search_anime(query)
        titles = rep.get_anime_titles()
        selected_anime = menu(titles, msg="Escolha o Anime.")

        rep.search_episodes(selected_anime)
        episode_list = rep.get_episode_list(selected_anime)
        selected_episode = menu(episode_list, msg="Escolha o episódio.")

        episode_idx = episode_list.index(selected_episode) 
    else:
        selected_anime, episode_idx = load_history()
    
    num_episodes = len(rep.anime_episodes_urls[selected_anime][0][0])
    while True:
        episode = episode_idx + 1
        player_url = rep.search_player(selected_anime, episode)
        if args.debug: print(player_url)
        play_video(player_url, args.debug)
        save_history(selected_anime, episode_idx)

        opts = []
        if episode_idx < num_episodes - 1:
            opts.append("Próximo")
        if episode_idx > 0:
            opts.append("Anterior")

        selected_opt = menu(opts, msg="O que quer fazer agora?")

        if selected_opt == "Próximo":
            episode_idx += 1 
        elif selected_opt == "Anterior":
            episode_idx -= 1

def load_history():
    file_path = HISTORY_PATH + "history.json"
    try:
        with open(file_path, "r") as f:
            data = load(f)
            titles = dict()
            for entry, info in data.items():
                ep_info = f" (Ultimo episódio assistido {info[1] + 1})"
                titles[entry + ep_info] = len(ep_info)
            selected = menu(list(titles.keys()), msg="Continue assistindo.")
            anime = selected[:-titles[selected]]
            episode_idx = data[anime][1]
            rep.anime_episodes_urls[anime] = data[anime][0]
        return anime, episode_idx
    except FileNotFoundError:
        print("Sem histórico de animes")
        exit()
    except PermissionError:
        print("Sem permissão para ler arquivos.")
        return

def save_history(anime, episode):
    file_path = HISTORY_PATH + "history.json"
    try:
        with open(file_path, "r+") as f:
            data = load(f)
            data[anime] = [rep.anime_episodes_urls[anime],
                           episode]
        with open(file_path , "w") as f:
            dump(data, f)

    except FileNotFoundError:
        Path(HISTORY_PATH).mkdir(parents=True, exist_ok=True)

        with open(file_path, "w") as f:
            data = dict()
            data[anime] = [rep.anime_episodes_urls[anime],
                            episode]
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
            result = anilist_main_menu()
            if result:
                anime_title, anilist_id = result
                # Start normal flow with selected anime
                anilist_anime_flow(anime_title, anilist_id, args)
    elif args.manga:
        manga_tupi()
    else:
        main(args)


if __name__=="__main__":
    cli()

