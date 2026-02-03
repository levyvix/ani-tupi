"""Anime search, selection, and playback command handler.

This module handles:
- Interactive anime search or continue watching
- Episode selection and playback loop
- History management and AniList progress sync
- Source switching and quality selection

This is a thin coordinator that delegates all business logic to services.
"""

from services import anime_service
from services.history_service import save_history
from services.anime.playback_service import (
    prepare_playback_from_search,
    prepare_playback_from_history,
    get_episode_url_and_source,
    sync_progress_to_anilist,
    navigate_episodes,
    PlaybackContext,
)
from services.anime.download_service import AnimeDownloadService
from ui.components import loading, menu_navigate
from utils.video_player import VideoPlayer
from utils.episode_range_parser import parse_episode_range, RangeParseError


def handle_anime_download(ctx: "PlaybackContext", args) -> None:
    """Handle anime download workflow.

    Prompts user for episode range and downloads episodes for offline viewing.

    Args:
        ctx: Current playback context
        args: Command-line arguments
    """
    print("\n📥 Baixar episódios para assistir depois")
    print(f"   Anime: {ctx.anime_title}")
    print(f"   Total de episódios: {ctx.num_episodes}")

    # Calculate default range (next unwatched to end)
    # ctx.episode_idx is 0-indexed, so next episode is episode_idx + 2
    next_episode = ctx.episode_idx + 2
    if next_episode > ctx.num_episodes:
        next_episode = ctx.num_episodes

    default_range = f"{next_episode}-"
    print(f"   Padrão: {default_range} (do episódio {next_episode} até o fim)\n")

    # Prompt for range
    try:
        range_input = input("Qual intervalo? (pressione Enter para padrão): ").strip()

        # If empty, use default (next unwatched to end)
        if not range_input:
            range_input = default_range
            print(f"   Usando: {range_input}")

        # Parse range
        episodes = parse_episode_range(range_input, ctx.num_episodes)
    except RangeParseError as e:
        print(f"❌ {e}")
        return

    # Initialize download service
    service = AnimeDownloadService()

    # Create a function to get episode URL from context
    def get_episode_url_for_download(episode_num: int):
        """Get episode URL for download."""
        from services.anime.playback_service import get_episode_url_and_source

        result = get_episode_url_and_source(ctx.anime_title, episode_num)
        if result.success and result.player_url:
            return (result.player_url, result.source or "unknown")
        return None

    # Download episodes
    print(f"\n⏳ Baixando {len(episodes)} episódio(s)...")
    try:
        with loading(f"Baixando {len(episodes)} episódio(s)..."):
            result = service.download_episodes(
                anime_title=ctx.anime_title,
                range_input=range_input,
                total_episodes=ctx.num_episodes,
                get_episode_url=get_episode_url_for_download,
            )

        # Show result
        print(f"\n{result.summary}")

        if result.successful > 0:
            print(f"✅ {result.successful} episódio(s) baixado(s) com sucesso!")
            print(f"   Localização: {service.download_dir / ctx.anime_title}")
    except Exception as e:
        print(f"❌ Erro ao baixar: {e}")


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
    source = None

    # If command-line args provided, use them; otherwise handled by main menu
    if args.query or args.continue_watching:
        if args.continue_watching:
            # Prepare playback context from history
            ctx = prepare_playback_from_history()
            if ctx is None:
                raise Exception("Problema ao conseguir informacoes do anime.")
        else:
            # Search for anime
            result = anime_service.search_anime_flow(args)
            selected_anime, episode_idx, source = result
            if not selected_anime or episode_idx is None:
                return

            # Prepare playback context from search results
            ctx = prepare_playback_from_search(selected_anime, episode_idx, source)
            if ctx is None:
                return
    else:
        # This path is used when called from main menu
        result = anime_service.search_anime_flow(args)
        selected_anime, episode_idx, source = result
        if not selected_anime or episode_idx is None:
            return

        # Prepare playback context from search results
        ctx = prepare_playback_from_search(selected_anime, episode_idx, source)
        if ctx is None:
            return

    # Display AniList discovery info if found
    if ctx.anilist_title:
        print(f"✅ Encontrado: {ctx.anilist_title}")
    else:
        print("⚠️  Não foi possível encontrar no AniList (continuando sem sincronização)")

    # Initialize video player for this session
    player = VideoPlayer()

    # Main playback loop
    while True:
        episode = ctx.episode_idx + 1  # Convert to 1-indexed

        # Get episode video URL
        with loading("Buscando vídeo..."):
            playback_result = get_episode_url_and_source(ctx.anime_title, episode)

        if not playback_result.success:
            print(f"\n❌ {playback_result.error_message}")
            print("   💡 O episódio pode estar indisponível em todas as fontes.")
            print("   💡 Tente outro episódio ou espere e tente novamente mais tarde.\n")
            continue

        # Play video
        player_url = playback_result.player_url
        source = playback_result.source

        if player_url is None:
            print("\n❌ Nenhum vídeo encontrado")
            continue

        # Format progress string
        from services.anime.progress_service import get_episode_progress_info
        from services.anime.anilist_discovery_service import AniListDiscoveryResult

        anilist_result = None
        if ctx.anilist_id:
            anilist_result = AniListDiscoveryResult(
                anilist_id=ctx.anilist_id,
                anilist_title=ctx.anilist_title,
                total_episodes=ctx.total_episodes_anilist,
                found=True,
                authenticated=True,
            )

        progress_info = get_episode_progress_info(episode, ctx.num_episodes, anilist_result)

        print(f"\n▶️  Iniciando reprodução do episódio {progress_info.progress_str}...")
        print(f"   Fonte: {source or 'unknown'}")
        print(f"   URL: {player_url[:80]}{'...' if len(player_url) > 80 else ''}\n")

        playback_result = player.play_episode(
            url=player_url,
            anime_title=ctx.anime_title,
            episode_number=episode,
            total_episodes=ctx.num_episodes,
            source=source,
            use_ipc=True,
            debug=args.debug,
            anilist_id=ctx.anilist_id,
            anilist_episodes=ctx.total_episodes_anilist,
        )

        exit_code = playback_result.exit_code
        final_episode = (
            playback_result.data.get("episode", episode) if playback_result.data else episode
        )

        print("\n📊 Reprodução encerrada:")
        print(f"   Exit code: {exit_code}")
        print(f"   Ação: {playback_result.action}")

        # Log MPV exit code if it's not a normal exit
        if exit_code not in [0, 3]:  # 0=normal, 3=user quit with 'q'
            print(f"\n⚠️  MPV exit code: {exit_code}")
            if exit_code == 2:
                print("    (Possível erro ao reproduzir ou janela fechada)")

        # Only clear terminal if playback was successful
        # If there was an error, keep messages visible for user to read
        if exit_code != 0:
            # Error occurred - give user time to see error messages
            print("\n⏳ Pressione Enter para continuar...")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass

        # Update context with actual episode watched (accounts for Shift+N navigation)
        # PlaybackContext is immutable, so create a new one with updated episode_idx
        # Context tracks playback position (what was played), not watch status (what was confirmed)
        ctx = PlaybackContext(
            anime_title=ctx.anime_title,
            episode_idx=final_episode - 1,  # Convert 1-indexed to 0-indexed
            source=ctx.source,
            anilist_id=ctx.anilist_id,
            anilist_title=ctx.anilist_title,
            total_episodes_anilist=ctx.total_episodes_anilist,
            num_episodes=ctx.num_episodes,
            episode_list=ctx.episode_list,
        )

        # Ask if watched until the end
        confirm_options = ["✅ Sim, assisti até o final", "❌ Não, parei antes."]
        confirm = menu_navigate(
            confirm_options, msg=f"Você assistiu o episódio {final_episode} até o final?"
        )

        # Only save history and sync if user watched until the end
        if confirm == "✅ Sim, assisti até o final":
            save_history(ctx.anime_title, ctx.episode_idx, ctx.anilist_id, source)

            # AniList sync
            if ctx.anilist_id:
                success = sync_progress_to_anilist(ctx.anilist_id, final_episode, ctx.num_episodes)
                if success:
                    print("✅ Progresso salvo no AniList!")
                else:
                    print("⚠️  Não foi possível salvar no AniList (continuando...)")

                # Check for sequels when last episode is watched
                if final_episode == ctx.num_episodes:
                    if anime_service.offer_sequel_and_continue(ctx.anilist_id, args):
                        return  # Sequel started, exit this flow
        # If user didn't finish, context is still updated but history is NOT saved
        # Navigation menu will show for both confirmation outcomes

        # Episode navigation menu
        opts = []
        if ctx.episode_idx < ctx.num_episodes - 1:
            opts.append("▶️  Próximo")
        if ctx.episode_idx > 0:
            opts.append("◀️  Anterior")
        opts.append("🔁 Replay")
        opts.append("📋 Escolher outro episódio")
        opts.append("📥 Baixar para assistir depois")
        opts.append("🔄 Trocar fonte")

        selected_opt = menu_navigate(list(opts), msg="O que quer fazer agora?")

        if not selected_opt or selected_opt == "🔙 Voltar":
            return  # Exit to main menu
        elif selected_opt == "▶️  Próximo":
            ctx = navigate_episodes(ctx, "next")
        elif selected_opt == "◀️  Anterior":
            ctx = navigate_episodes(ctx, "previous")
        elif selected_opt == "🔁 Replay":
            ctx = navigate_episodes(ctx, "replay")
        elif selected_opt == "📋 Escolher outro episódio":
            # User selects episode from menu
            selected_episode = menu_navigate(list(ctx.episode_list), msg="Escolha o episódio.")
            if not selected_episode:
                return  # User cancelled, exit function
            episode_idx = ctx.episode_list.index(selected_episode)
            ctx = navigate_episodes(ctx, "choose", episode_idx)
        elif selected_opt == "📥 Baixar para assistir depois":
            # Download episodes for offline viewing
            handle_anime_download(ctx, args)
        elif selected_opt == "🔄 Trocar fonte":
            # Source switching
            result = anime_service.switch_anime_source(ctx.anime_title, args, ctx.anilist_id)
            new_anime, new_episode_idx = result
            if new_anime and new_episode_idx is not None:
                # Prepare new context with switched source
                new_ctx = prepare_playback_from_search(new_anime, new_episode_idx, source)
                if new_ctx:
                    ctx = new_ctx
                    # Update episode count and list
                    ctx = navigate_episodes(ctx, "choose", new_episode_idx)
