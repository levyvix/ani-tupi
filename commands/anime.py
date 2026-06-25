"""Anime search, selection, and playback command handler.

This module handles:
- Interactive anime search or continue watching
- Episode selection and playback loop
- History management and AniList progress sync
- Source switching and quality selection

This is a thin coordinator that delegates all business logic to services.
"""

from pathlib import Path

from services import anime_service
from services.history_service import save_history
from services.repository import rep
from services.anime.playback_service import (
    prepare_playback_from_search,
    prepare_playback_from_history,
    get_episode_url_and_source,
    sync_progress_to_anilist,
    navigate_episodes,
    PlaybackContext,
)
from utils.logging import get_logger
from services.anime.download_service import AnimeDownloadService
from services.anime.playback_fallback import play_episode_with_fallback
from ui.components import loading, menu_navigate
from utils.video_player import VideoPlayer
from utils.episode_range_parser import parse_episode_range, RangeParseError

logger = get_logger(__name__)


def build_episode_sources(
    anime_title: str,
    episode: int,
    url_result,
) -> list[tuple[str, str, str | None]]:
    """Build ordered playback sources for an episode.

    Keeps any direct/fast-path URL as the first candidate, but still collects
    all remaining repository-backed sources so playback fallback can continue
    when the first source fails.
    """
    sources: list[tuple[str, str, str | None]] = []
    seen_sources: set[str] = set()

    if url_result.success and url_result.player_url:
        direct_source = url_result.source or "unknown"
        sources.append((url_result.player_url, direct_source, None))
        seen_sources.add(direct_source)
        logger.info(
            f"[DEBUG] Using direct URL from get_episode_url_and_source: {url_result.player_url[:80]}..."
        )
    else:
        logger.info(
            f"[DEBUG] get_episode_url_and_source failed (success={url_result.success}), using fallback"
        )

    page_sources = rep.get_all_episode_sources(anime_title, episode)
    logger.info(f"[DEBUG] Found {len(page_sources)} page sources")

    for page_url, source_name in page_sources:
        if source_name in seen_sources:
            logger.info(f"[DEBUG] Skipping duplicate source already queued: {source_name}")
            continue

        logger.info(f"[DEBUG] Extracting video URL from {source_name} page: {page_url[:80]}...")
        try:
            video_url = rep.search_player_from_page(page_url, source_name)
            if video_url:
                logger.info(
                    f"[DEBUG] SUCCESS: Got video URL from {source_name}: {video_url[:80]}..."
                )
                sources.append((video_url, source_name, page_url))
                seen_sources.add(source_name)
            else:
                logger.info(
                    f"[DEBUG] FAILED: search_player_from_page returned None for {source_name}"
                )
        except Exception as e:
            logger.info(f"[DEBUG] EXCEPTION extracting from {source_name}: {e}")
            continue

    return [(url, source, referrer) for url, source, referrer in sources if url and source]


def build_post_playback_options(ctx: "PlaybackContext") -> list[str]:
    """Build post-playback action options for current context."""
    opts = []
    has_next_episode = ctx.episode_idx < ctx.num_episodes - 1

    if has_next_episode:
        opts.append("▶️  Próximo")
    else:
        opts.append("↩️  Voltar ao menu anterior")

    if ctx.episode_idx > 0:
        opts.append("◀️  Anterior")

    opts.append("🔁 Replay")
    opts.append("📋 Escolher outro episódio")
    opts.append("📥 Baixar para assistir depois")
    opts.append("🔄 Trocar fonte")
    return opts


def select_episode_from_menu(ctx: "PlaybackContext") -> "PlaybackContext | None":
    """Select an episode from menu and return updated context.

    Returns:
        Updated PlaybackContext when episode is selected.
        None when user chooses to go back from episode selection.
    """
    episode_options = list(ctx.episode_list)
    selected_episode = menu_navigate(episode_options, msg="Escolha o episódio.")
    if not selected_episode:
        return None

    episode_idx = episode_options.index(selected_episode)
    return navigate_episodes(ctx, "choose", episode_idx)


def handle_anime_download(ctx: "PlaybackContext", args) -> None:
    """Handle anime download workflow.

    Prompts user for episode range and downloads episodes for offline viewing.

    Args:
        ctx: Current playback context
        args: Command-line arguments
    """
    logger.info("📥 Baixar episódios para assistir depois")
    logger.info(f"   Anime: {ctx.anime_title}")
    logger.info(f"   Total de episódios: {ctx.num_episodes}")

    # Calculate default range (next unwatched to end)
    # ctx.episode_idx is 0-indexed, so next episode is episode_idx + 2
    next_episode = ctx.episode_idx + 2
    if next_episode > ctx.num_episodes:
        next_episode = ctx.num_episodes

    default_range = f"{next_episode}-"
    logger.info(f"   Padrão: {default_range} (do episódio {next_episode} até o fim)\n")

    # Prompt for range
    try:
        range_input = input("Qual intervalo? (pressione Enter para padrão): ").strip()

        # If empty, use default (next unwatched to end)
        if not range_input:
            range_input = default_range
            logger.info(f"   Usando: {range_input}")

        # Parse range
        episodes = parse_episode_range(range_input, ctx.num_episodes)
    except RangeParseError as e:
        logger.info(f"❌ {e}")
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
    logger.info(f"⏳ Baixando {len(episodes)} episódio(s)...")
    try:
        with loading(f"Baixando {len(episodes)} episódio(s)..."):
            result = service.download_episodes(
                anime_title=ctx.anime_title,
                range_input=range_input,
                total_episodes=ctx.num_episodes,
                get_episode_url=get_episode_url_for_download,
            )

        # Show result
        logger.info(f"{result.summary}")

        if result.successful > 0:
            logger.info(f"✅ {result.successful} episódio(s) baixado(s) com sucesso!")
            logger.info(f"   Localização: {service.download_dir / ctx.anime_title}")
    except Exception as e:
        logger.info(f"❌ Erro ao baixar: {e}")


def handle_post_playback_confirmation(
    anime_title: str,
    episode_number: int,
    num_episodes: int,
    anilist_id: int | None,
    source: str | None,
    is_local: bool = False,
    file_path: "Path | None" = None,
) -> bool:
    """Handle post-playback confirmation and syncing.

    After episode playback, ask if user watched until the end.
    If confirmed, save history and sync to AniList.
    If AniList sync fails and configured, queue for offline retry.

    Args:
        anime_title: Title of anime just watched
        episode_number: Episode number (1-indexed)
        num_episodes: Total episodes in series
        anilist_id: AniList ID if discovered (None = no sync)
        source: Video source name
        is_local: Whether episode came from local library
        file_path: Path to local episode file (for cleanup after sync)

    Returns:
        True if user confirmed watching until end, False otherwise
    """
    # Ask if watched until the end
    confirm_options = ["✅ Sim, assisti até o final", "❌ Não, parei antes."]
    confirm = menu_navigate(
        confirm_options, msg=f"Você assistiu o episódio {episode_number} até o final?"
    )

    confirmed = confirm == "✅ Sim, assisti até o final"

    if confirmed:
        # Save history for both remote and local episodes
        save_history(
            anime_title,
            episode_number - 1,
            anilist_id,
            source or "local",
            total_episodes=num_episodes,
        )

        # AniList sync
        if anilist_id:
            success = sync_progress_to_anilist(
                anilist_id, episode_number, num_episodes, anime_title
            )
            if success:
                logger.info("✅ Progresso salvo no AniList!")

                # Delete local file after successful sync (if configured)
                if is_local and file_path:
                    from models.config import settings
                    from services.local_anime_service import LocalAnimeService

                    if settings.offline_sync.enable_file_cleanup:
                        try:
                            service = LocalAnimeService()
                            deleted = service.delete_episode(anime_title, episode_number)
                            if deleted:
                                logger.info(
                                    f"🗑️  Arquivo local deletado (episódio {episode_number})"
                                )
                        except Exception as e:
                            logger.info(f"⚠️  Erro ao deletar arquivo: {e}")
            else:
                logger.info("⚠️  Não foi possível salvar no AniList")
                logger.info("   Será sincronizado quando estiver online.")

                # Queue for offline sync
                from services.anime.offline_sync_service import add_to_queue

                add_to_queue(
                    anime_title=anime_title,
                    episode_number=episode_number,
                    anilist_id=anilist_id,
                    error=None,
                    is_local=is_local,
                    file_path=file_path,
                )
        else:
            # No AniList ID found - still handle local file deletion if configured
            if is_local and file_path:
                from models.config import settings
                from services.local_anime_service import LocalAnimeService

                if settings.offline_sync.delete_after_watch:
                    try:
                        service = LocalAnimeService()
                        deleted = service.delete_episode(anime_title, episode_number)
                        if deleted:
                            logger.info(f"🗑️  Arquivo local deletado (episódio {episode_number})")
                    except Exception as e:
                        logger.info(f"⚠️  Erro ao deletar arquivo: {e}")

    return confirmed


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
                return

            # Handle -e flag override for continue watching
            if hasattr(args, "episode") and args.episode is not None:
                episode_list = rep.get_episode_list(ctx.anime_title)
                total_episodes = len(episode_list)

                if total_episodes == 0:
                    logger.error("❌ Nao foi possivel carregar episodios para este anime.")
                    return

                # Validate episode number is within bounds
                if args.episode < 1 or args.episode > total_episodes:
                    logger.error(
                        f"❌ Episódio {args.episode} não existe ou ainda não foi ao ar. "
                        f"Episódios disponíveis: 1-{total_episodes}"
                    )
                    return

                # Replace context with new episode (convert to 0-indexed)
                ctx = prepare_playback_from_search(
                    ctx.anime_title,
                    args.episode - 1,
                    ctx.source,
                )
                if ctx is None:
                    return
        else:
            # Search for anime (handles -e flag internally)
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

        # Handle -e flag for episode specification
        if hasattr(args, "episode") and args.episode is not None:
            episode_list = rep.get_episode_list(selected_anime)
            total_episodes = len(episode_list)

            if total_episodes == 0:
                logger.error("❌ Nao foi possivel carregar episodios para este anime.")
                return

            # Validate episode number is within bounds
            if args.episode < 1 or args.episode > total_episodes:
                logger.error(
                    f"❌ Episódio {args.episode} não existe ou ainda não foi ao ar. "
                    f"Episódios disponíveis: 1-{total_episodes}"
                )
                return

            # Convert to 0-indexed
            episode_idx = args.episode - 1

        # Prepare playback context from search results
        ctx = prepare_playback_from_search(selected_anime, episode_idx, source)
        if ctx is None:
            return

    # Display AniList discovery info if found
    if ctx.anilist_title:
        logger.info(f"✅ Encontrado: {ctx.anilist_title}")
    else:
        logger.info("⚠️  Não foi possível encontrar no AniList (continuando sem sincronização)")

    # Initialize video player for this session
    player = VideoPlayer()

    # Main playback loop
    current_player_url: str | None = None  # tracks URL from previous episode for pattern opt.
    while True:
        episode = ctx.episode_idx + 1  # Convert to 1-indexed

        # Get all episode sources with fallback support
        with loading("Buscando vídeo..."):
            url_result = get_episode_url_and_source(
                ctx.anime_title, episode, current_player_url=current_player_url
            )
            sources = build_episode_sources(ctx.anime_title, episode, url_result)
            logger.info(f"[DEBUG] Final sources count: {len(sources)}")

        if not sources:
            logger.info("❌ Nenhuma fonte conseguiu extrair o video.")
            logger.info("   💡 O episódio pode estar indisponível em todas as fontes.")
            logger.info("   💡 Tente outro episódio ou espere e tente novamente mais tarde.\n")
            break

        # Use first source for initial display
        initial_source = sources[0][1]

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

        logger.info(f"▶️  Iniciando reprodução do episódio {progress_info.progress_str}...")
        if len(sources) > 1:
            logger.info(f"   Fontes disponíveis: {', '.join(s[1] for s in sources)}")
        else:
            logger.info(f"   Fonte: {initial_source}")
        logger.info(f"   URL: {sources[0][0][:80]}{'...' if len(sources[0][0]) > 80 else ''}\n")

        # Use fallback logic to try each source in priority order
        fallback_result = play_episode_with_fallback(
            player=player,
            sources=sources,
            anime_title=ctx.anime_title,
            episode_number=episode,
            total_episodes=ctx.num_episodes,
            use_ipc=True,
            debug=args.debug,
            anilist_id=ctx.anilist_id,
            anilist_episodes=ctx.total_episodes_anilist,
        )

        playback_result = fallback_result.playback_result
        source_used = fallback_result.source_used
        all_failed = fallback_result.all_failed

        exit_code = playback_result.exit_code
        error_hint = (
            playback_result.data.get("error_hint")
            if isinstance(playback_result.data, dict)
            else None
        )
        final_episode = (
            playback_result.data.get("episode", episode) if playback_result.data else episode
        )

        # Show appropriate message based on playback outcome
        if exit_code == 0:
            logger.info(f"✅ Reprodução concluída (Fonte: {source_used})")
        elif exit_code == 3:
            logger.info("⏸️  Reprodução interrompida pelo usuário")
        elif all_failed:
            logger.info("❌ Nenhuma fonte conseguiu reproduzir o episódio")
            sources_tried = ", ".join(f"{source}" for source, _ in fallback_result.sources_tried)
            logger.info(f"   Fontes tentadas: {sources_tried}")
            logger.info("   💡 Tente trocar de fonte manualmente ou verifique sua conexão.")
        else:
            logger.info(f"⚠️  Erro ao reproduzir (código: {exit_code})")
            if error_hint:
                logger.info(f"   ❌ {error_hint}")

        logger.info("📊 Reprodução encerrada:")
        logger.info(f"   Exit code: {exit_code}")
        logger.info(f"   Ação: {playback_result.action}")

        # Log MPV exit code if it's not a normal exit
        if exit_code not in [0, 3]:  # 0=normal, 3=user quit with 'q'
            logger.info(f"⚠️  MPV exit code: {exit_code}")
            if exit_code == 2:
                logger.info("    (Possível erro ao reproduzir ou janela fechada)")

        # Only clear terminal if playback was successful
        # If there was an error, keep messages visible for user to read
        if exit_code != 0:
            # Error occurred - give user time to see error messages
            logger.info("⏳ Pressione Enter para continuar...")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass

        # Save the URL that was played so next iteration can try pattern derivation
        if exit_code in (0, 3) and sources:
            current_player_url = sources[0][0]
        else:
            current_player_url = None

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

        # Handle post-playback confirmation only on successful playback.
        # On errors, skip confirmation to avoid accidental history corruption.
        if exit_code == 0:
            confirmed = handle_post_playback_confirmation(
                anime_title=ctx.anime_title,
                episode_number=final_episode,
                num_episodes=ctx.num_episodes,
                anilist_id=ctx.anilist_id,
                source=source_used,
                is_local=False,
            )
        else:
            confirmed = False

        # Check for sequels when last episode is watched and confirmed
        if confirmed and ctx.anilist_id and final_episode == ctx.num_episodes:
            if anime_service.offer_sequel_and_continue(ctx.anilist_id, args):
                return  # Sequel started, exit this flow

        # Post-playback action layer
        while True:
            selected_opt = menu_navigate(
                build_post_playback_options(ctx), msg="O que quer fazer agora?"
            )

            if not selected_opt:
                return  # Exit to main menu

            if selected_opt == "↩️  Voltar ao menu anterior":
                return

            if "▶️  Próximo" in selected_opt:  # May have ⏭️ indicator
                ctx = navigate_episodes(ctx, "next")
                break

            if "◀️  Anterior" in selected_opt:  # May have ⏭️ indicator
                ctx = navigate_episodes(ctx, "previous")
                break

            if "🔁 Replay" in selected_opt:  # May have ⏭️ indicator
                ctx = navigate_episodes(ctx, "replay")
                break

            if selected_opt == "📋 Escolher outro episódio":
                selected_ctx = select_episode_from_menu(ctx)
                if selected_ctx is None:
                    continue  # Back to action layer
                ctx = selected_ctx
                break

            if selected_opt == "📥 Baixar para assistir depois":
                handle_anime_download(ctx, args)
                continue  # Stay in action layer

            if selected_opt == "🔄 Trocar fonte":
                result = anime_service.switch_anime_source(ctx.anime_title, args, ctx.anilist_id)
                new_anime, new_episode_idx = result
                if new_anime and new_episode_idx is not None:
                    new_ctx = prepare_playback_from_search(new_anime, new_episode_idx, source)
                    if new_ctx:
                        ctx = navigate_episodes(new_ctx, "choose", new_episode_idx)
                        break
                else:
                    logger.info("⚠️  Troca de fonte cancelada ou não foi possível trocar de fonte.")


def handle_random_anime(args) -> None:
    """Handle --random flag to pick and play a random anime.

    Args:
        args: Command line arguments
    """
    from services.anime.random_anime_service import handle_random_anime as service_handler

    service_handler(args)
