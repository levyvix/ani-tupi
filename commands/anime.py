"""Anime search, selection, and playback command handler.

This module handles:
- Interactive anime search or continue watching
- Episode selection and playback loop
- History management and AniList progress sync
- Source switching and quality selection
"""

from services import anime_service
from services.history_service import load_history, save_history
from services.repository import rep
from ui.components import loading, menu_navigate
from utils.video_player import play_video


def anime(args) -> None:
    """Handle anime search, selection, and playback flow.

    Supports:
    - Direct search with -q flag
    - Continue watching from history
    - Episode selection and playback loop
    - AniList progress sync
    - Source switching
    """
    # Variables for AniList integration and source tracking
    anilist_id = None
    anilist_title = None
    source = None

    # If command-line args provided, use them; otherwise handled by main menu
    if args.query or args.continue_watching:
        if args.continue_watching:
            selected_anime, episode_idx, anilist_id, anilist_title = load_history()
            if any([selected_anime, episode_idx, anilist_id, anilist_title]) is None:
                raise Exception("Problema ao conseguir informacoes do anime.")
            # Episodes already loaded by load_history()
        else:
            selected_anime, episode_idx, source = anime_service.search_anime_flow(args)
            if not selected_anime:
                return

            # Try to auto-discover AniList ID if authenticated
            from services.anilist_service import anilist_client
            if anilist_client.is_authenticated():
                from utils.anilist_discovery import get_anilist_id_from_title

                print(f"\n🔍 Procurando '{selected_anime}' no AniList...")
                anilist_id = get_anilist_id_from_title(selected_anime)

                if anilist_id:
                    # Get anime metadata for display
                    from utils.anilist_discovery import get_anilist_metadata
                    metadata = get_anilist_metadata(anilist_id)
                    if metadata:
                        anilist_title = anilist_client.format_title(metadata.title)
                        print(f"✅ Encontrado: {anilist_title}")
                else:
                    print("⚠️  Não foi possível encontrar no AniList (continuando sem sincronização)")
    else:
        # This path is used when called from main menu
        selected_anime, episode_idx, source = anime_service.search_anime_flow(args)
        if not selected_anime:
            return

        # Try to auto-discover AniList ID if authenticated
        from services.anilist_service import anilist_client
        if anilist_client.is_authenticated():
            from utils.anilist_discovery import get_anilist_id_from_title

            print(f"\n🔍 Procurando '{selected_anime}' no AniList...")
            anilist_id = get_anilist_id_from_title(selected_anime)

            if anilist_id:
                # Get anime metadata for display
                from utils.anilist_discovery import get_anilist_metadata
                metadata = get_anilist_metadata(anilist_id)
                if metadata:
                    anilist_title = anilist_client.format_title(metadata.title)
                    print(f"✅ Encontrado: {anilist_title}")
            else:
                print("⚠️  Não foi possível encontrar no AniList (continuando sem sincronização)")

    # Get episode list for playback
    episode_list = rep.get_episode_list(selected_anime)
    num_episodes = len(episode_list)

    while True:
        episode = episode_idx + 1

        # Get episode URL and source to determine quality extraction method
        episode_info = rep.get_episode_url_and_source(selected_anime, episode)

        if not episode_info:
            print(f"❌ Episódio {episode} não encontrado")
            continue

        episode_url, source = episode_info

        # Get video URL from scraper plugins
        with loading("Buscando vídeo..."):
            player_url = rep.search_player(selected_anime, episode)

        # Check if video URL was found
        if not player_url:
            print("\n❌ Nenhuma fonte conseguiu extrair o vídeo.")
            print("   💡 O episódio pode estar indisponível em todas as fontes.")
            print("   💡 Tente outro episódio ou espere e tente novamente mais tarde.\n")
            continue

        # Play video
        exit_code = play_video(player_url, args.debug)

        # Log MPV exit code if it's not a normal exit
        if exit_code not in [0, 3]:  # 0=normal, 3=user quit with 'q'
            print(f"\n⚠️  MPV exit code: {exit_code}")
            if exit_code == 2:
                print("    (Possível erro ao reproduzir ou janela fechada)")

        # Clear terminal before asking confirmation
        import os

        os.system("clear")

        # Ask if watched until the end
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
            from services.anilist_service import anilist_client

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
                            if entry.status == "PLANNING":
                                print("\n📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                                anilist_client.add_to_list(anilist_id, "CURRENT")
                            elif entry.status == "COMPLETED":
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
                        if anime_service.offer_sequel_and_continue(anilist_id, args):
                            return  # Sequel started, exit this flow

        # Episode navigation menu
        opts = []
        if episode_idx < num_episodes - 1:
            opts.append("▶️  Próximo")
        if episode_idx > 0:
            opts.append("◀️  Anterior")
        opts.append("🔁 Replay")
        opts.append("📋 Escolher outro episódio")
        opts.append("🔄 Trocar fonte")

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
            new_anime, new_episode_idx = anime_service.switch_anime_source(
                selected_anime, args, anilist_id
            )
            if new_anime:
                selected_anime = new_anime
                episode_idx = new_episode_idx
                num_episodes = len(rep.get_episode_list(selected_anime))
                # Continue loop with new anime/episode
