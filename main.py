import argparse

import loader
from core import anime_service
from core.history_service import load_history, save_history
from manga_tupi import main as manga_tupi
from repository import rep
from ui.components import loading, menu
from video_player import play_video

# Use centralized path function from config
def show_main_menu():
    """Display main menu with options."""
    options = [
        "🔍 Buscar Anime",
        "▶️  Continuar Assistindo",
        "📺 AniList",
        "📚 Mangá",
        "⚙️  Gerenciar Fontes",
    ]
    return menu(options, msg="Ani-Tupi - Menu Principal")



def main(args) -> None:
    loader.load_plugins({"pt-br"}, None if not args.debug else ["animesonlinecc"])

    # Show active sources
    active_sources = rep.get_active_sources()
    if active_sources:
        print(f"ℹ️  Fontes ativas: {', '.join(active_sources)}")

    # Variables for AniList integration and source tracking
    anilist_id = None
    anilist_title = None
    source = None

    # If command-line args provided, skip main menu
    if args.query or args.continue_watching or args.manga:
        if args.continue_watching:
            selected_anime, episode_idx, anilist_id, anilist_title = load_history()
            # Episodes already loaded by load_history()
            # Note: source is extracted from history inside load_history()
        else:
            selected_anime, episode_idx, source = anime_service.search_anime_flow(args)
            if not selected_anime:
                return
    else:
        # Show main menu (no loop here - user can restart if needed)
        choice = show_main_menu()

        if choice == "🔍 Buscar Anime":
            selected_anime, episode_idx, source = anime_service.search_anime_flow(args)
            if not selected_anime:
                return
        elif choice == "▶️  Continuar Assistindo":
            selected_anime, episode_idx, anilist_id, _anilist_title = load_history()
            # Episodes already loaded by load_history()
        elif choice == "📺 AniList":
            from ui.anilist_menus import anilist_main_menu

            # Loop to allow watching multiple anime
            while True:
                result = anilist_main_menu()
                if not result:
                    return  # User cancelled, exit to main menu

                anime_title, anilist_id = result
                anime_service.anilist_anime_flow(anime_title, anilist_id, args)
                # After watching, loop back to AniList menu
        elif choice == "📚 Mangá":
            manga_tupi()
            return
        elif choice == "⚙️  Gerenciar Fontes":
            from plugin_manager import plugin_management_menu

            plugin_management_menu()
            return  # Return to exit after managing plugins

    # Get episode list for playback (needed after any selection flow)
    episode_list = rep.get_episode_list(selected_anime)
    num_episodes = len(episode_list)
    while True:
        episode = episode_idx + 1
        with loading("Buscando vídeo..."):
            player_url = rep.search_player(selected_anime, episode)
        if args.debug:
            pass
        play_video(player_url, args.debug)

        # Ask if watched until the end (always ask, not just for AniList)
        from ui.components import menu_navigate

        confirm_options = ["✅ Sim, assisti até o final", "❌ Não, parei antes."]
        confirm = menu_navigate(
            confirm_options, msg=f"Você assistiu o episódio {episode} até o final?"
        )

        # Only save history if user watched until the end
        if confirm == "✅ Sim, assisti até o final":
            save_history(selected_anime, episode_idx, anilist_id, source)
        else:
            # User didn't finish - go back to episode menu without saving
            continue

        # AniList sync (if coming from continue watching with anilist_id)
        if anilist_id:
            from core.anilist_service import anilist_client

            if anilist_client.is_authenticated():
                if confirm == "✅ Sim, assisti até o final":
                    # Check if anime is in any list
                    if not anilist_client.is_in_any_list(anilist_id):
                        print("\n📝 Adicionando à sua lista do AniList...")
                        anilist_client.add_to_list(anilist_id, "CURRENT")
                    else:
                        # Auto-promote from PLANNING to CURRENT, or COMPLETED to REPEATING
                        entry = anilist_client.get_media_list_entry(anilist_id)
                        if entry:
                            if entry.get("status") == "PLANNING":
                                print("\n📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                                anilist_client.add_to_list(anilist_id, "CURRENT")
                            elif entry.get("status") == "COMPLETED":
                                print("\n🔄 Mudando para 'Recomassistindo'...")
                                anilist_client.change_status(anilist_id, "REPEATING")

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
                        if anime_service.offer_sequel_and_continue(anilist_id, selected_anime, args):
                            return  # Sequel started, exit this flow

        opts = []
        if episode_idx < num_episodes - 1:
            opts.append("▶️  Próximo")
        if episode_idx > 0:
            opts.append("◀️  Anterior")
        opts.append("🔁 Replay")
        opts.append("📋 Escolher outro episódio")
        opts.append("🔄 Trocar fonte")

        from ui.components import menu_navigate

        selected_opt = menu_navigate(opts, msg="O que quer fazer agora?")

        if not selected_opt or selected_opt == "🔙 Voltar":
            return  # Exit to main menu
        if selected_opt == "▶️  Próximo":
            episode_idx += 1
        elif selected_opt == "◀️  Anterior":
            episode_idx -= 1
        elif selected_opt == "🔁 Replay":
            # Keep same episode_idx, loop continues to replay
            pass
        elif selected_opt == "📋 Escolher outro episódio":
            episode_list = rep.get_episode_list(selected_anime)
            selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                continue  # Stay in current episode menu
            episode_idx = episode_list.index(selected_episode)
        elif selected_opt == "🔄 Trocar fonte":
            new_anime, new_episode_idx = anime_service.switch_anime_source(selected_anime, args, anilist_id)
            if new_anime:
                selected_anime = new_anime
                episode_idx = new_episode_idx
                num_episodes = len(rep.get_episode_list(selected_anime))
                # Continue loop with new anime/episode

def cli() -> None:
    """Entry point para CLI."""
    # Migrate old JSON cache to new SQLite-based cache system on first run
    # Note: Migration module removed - cache system already migrated
    # from migrate_json_cache import migrate_old_json_cache
    # migrate_old_json_cache()

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
        "--list-sources",
        action="store_true",
        help="Listar todas as fontes de anime disponíveis",
    )
    parser.add_argument(
        "--clear-cache",
        nargs="?",
        const=True,
        metavar="[anime_name]",
        help="Limpar cache (sem argumentos limpa tudo, ou especifique anime para limpar apenas um)",
    )

    args = parser.parse_args()

    # Handle --list-sources before other commands
    if args.list_sources:
        loader.load_plugins({"pt-br"})
        sources = rep.get_active_sources()
        if sources:
            print("\n🔌 Fontes de anime disponíveis:")
            for i, source in enumerate(sources, 1):
                print(f"   {i}. {source}")
        else:
            print("\n❌ Nenhuma fonte de anime encontrada!")
        return

    # Handle --clear-cache before other commands
    if args.clear_cache is not None:
        from cache_manager import clear_cache_all, clear_cache_by_prefix
        from anilist_discovery import auto_discover_anilist_id

        if args.clear_cache is True:
            # Clear all cache
            clear_cache_all()
            print("✅ Cache completamente limpo!")
        else:
            # Try to discover AniList ID for more precise clearing
            anilist_id = auto_discover_anilist_id(args.clear_cache)
            if anilist_id:
                clear_cache_by_prefix(f":{anilist_id}:")
                print(f"✅ Cache de '{args.clear_cache}' (AniList ID {anilist_id}) foi limpo!")
            else:
                # Fallback: clear by title prefix
                clear_cache_by_prefix(f":{args.clear_cache}:")
                print(f"✅ Cache de '{args.clear_cache}' foi limpo!")
        return

    # Handle commands
    if args.command == "anilist":
        from ui.anilist_menus import anilist_main_menu, authenticate_flow

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
                anime_service.anilist_anime_flow(anime_title, anilist_id, args)
                # After watching, loop back to AniList menu
    elif args.manga:
        manga_tupi()
    else:
        main(args)


if __name__ == "__main__":
    cli()
