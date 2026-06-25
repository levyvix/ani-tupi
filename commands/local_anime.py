"""Local anime library browsing and playback.

Handles offline viewing of downloaded anime episodes with:
- Episode selection and playback
- Post-playback navigation (Next, Previous, Replay, Back)
- AniList sync with offline queue for failures
- Automatic file cleanup after successful sync
"""

from pathlib import Path

from models.config import get_data_path
from services.local_anime_service import LocalAnimeService
from utils.anilist_discovery import (
    get_anilist_id_from_title,
    get_anilist_id_with_interactive_fallback,
)
from utils.logging import get_logger
from ui.components import menu_navigate
from utils.video_player import VideoPlayer
from utils.persistence import JSONStore

logger = get_logger(__name__)


def _sanitize_title(raw_title: str) -> str:
    """Sanitize anime title to prevent path traversal."""
    safe_title = Path(raw_title).name
    if not safe_title or safe_title != raw_title:
        raise ValueError("Título de anime inválido")
    return safe_title


def _extract_selected_title(selection: str) -> str:
    """Extract anime title from formatted selection string."""
    return _sanitize_title(selection.split(" (")[0])


def _discover_anilist_id(selected_title: str) -> int | None:
    """Discover AniList ID for local anime title."""
    anilist_id = None
    try:
        # Check if this is first watched episode (non-interactive load of history)
        try:
            history_path = get_data_path()
            history_store = JSONStore(history_path / "history.json")
            history_data = history_store.load({})
            is_first_watched = selected_title not in history_data
        except Exception:
            is_first_watched = True

        if is_first_watched:
            # Interactive discovery for first watched episode
            anilist_id = get_anilist_id_with_interactive_fallback(
                selected_title,
                strict_threshold=95,
            )
        else:
            # Standard discovery (use cached result if available)
            anilist_id = get_anilist_id_from_title(selected_title)
    except Exception:
        pass  # Discovery failure is silent - proceed without AniList ID

    return anilist_id


def _format_anime_list(service: LocalAnimeService, anime_titles: list[str]) -> list[str]:
    """Format anime list with downloaded episode counts."""
    anime_list_with_counts = []
    for title in anime_titles:
        info = service.get_anime_info(title)
        count = info["total_episodes"]
        anime_list_with_counts.append(f"{title} ({count} eps)")
    return anime_list_with_counts


def _select_episode_action(selected_title: str, selected_ep_num: int) -> str | None:
    """Show episode action menu before playback."""
    opts = ["▶️  Assistir agora", "🗑️  Apagar episódio"]
    return menu_navigate(
        opts,
        msg=f"📺 {selected_title} - Episódio {selected_ep_num}",
        enable_search=False,
    )


def _show_post_playback_menu(
    episodes: list[tuple[int, Path]],
    final_episode: int,
) -> str | None:
    """Show post-playback action menu."""
    opts = []
    current_idx = next(
        (i for i, (ep_num, _) in enumerate(episodes) if ep_num == final_episode), None
    )

    if current_idx is not None:
        if current_idx < len(episodes) - 1:
            opts.append("▶️  Próximo")
        if current_idx > 0:
            opts.append("◀️  Anterior")

    opts.extend(
        [
            "🔁 Replay",
            "📚 Voltar à biblioteca do anime",
            "🗑️  Apagar episódio atual",
            "📂 Voltar à biblioteca local",
        ]
    )

    return menu_navigate(opts, msg="O que quer fazer agora?", enable_search=False)


def handle_local_library_playback(args) -> None:
    """Handle local anime library browsing and playback.

    Allows users to:
    1. Select downloaded anime from library
    2. Select episode to play
    3. Play episode offline
    4. Navigate to next/previous episodes or replay
    5. Sync progress to AniList with offline queue fallback
    """
    while True:
        service = LocalAnimeService()
        anime_list = service.get_downloaded_anime_list()

        if not anime_list:
            logger.info("\n📂 Biblioteca Local")
            logger.info("❌ Nenhum anime baixado ainda")
            logger.info("   💡 Use '📥 Baixar para assistir depois' no menu de reprodução")
            return

        anime_list_with_counts = _format_anime_list(service, anime_list)
        selected = menu_navigate(
            anime_list_with_counts,
            msg="📂 Biblioteca Local - Selecione um anime",
        )
        if not selected:
            return

        selected_title = _extract_selected_title(selected)
        selected_ep_num: int | None = None
        anilist_id: int | None = None

        # Episode loop for selected anime
        while True:
            try:
                episodes = service.get_downloaded_episodes(selected_title)
            except FileNotFoundError:
                logger.info(f"❌ Anime não encontrado: {selected_title}")
                break

            if not episodes:
                logger.info(f"❌ Nenhum episódio encontrado para {selected_title}")
                break

            episode_numbers = [ep_num for ep_num, _ in episodes]
            if selected_ep_num not in episode_numbers:
                selected_ep_num = None

            # Episode selection + per-episode menu
            if selected_ep_num is None:
                episode_options = [f"Episódio {ep_num}" for ep_num in episode_numbers]
                selected_ep_str = menu_navigate(
                    episode_options,
                    msg=f"📂 {selected_title} - Selecione um episódio",
                )
                if not selected_ep_str:
                    break  # Back to local library anime list

                selected_ep_num = int(selected_ep_str.split()[1])
                episode_action = _select_episode_action(selected_title, selected_ep_num)

                if not episode_action:
                    selected_ep_num = None
                    continue

                if episode_action == "🗑️  Apagar episódio":
                    deleted = service.delete_episode(selected_title, selected_ep_num)
                    if deleted:
                        logger.info(f"🗑️  Episódio {selected_ep_num} apagado")
                    else:
                        logger.info("❌ Episódio não encontrado para apagar")
                    selected_ep_num = None
                    continue

            ep_path = next(
                (file_path for ep_num, file_path in episodes if ep_num == selected_ep_num), None
            )
            if not ep_path:
                logger.info("❌ Episódio não encontrado")
                selected_ep_num = None
                continue

            player = VideoPlayer()
            file_url = f"file://{ep_path.resolve()}"

            logger.info(f"\n▶️  Reproduzindo: {selected_title} - Episódio {selected_ep_num}")
            logger.info(f"   Arquivo: {ep_path}")

            playback_result = player.play_episode(
                url=file_url,
                anime_title=selected_title,
                episode_number=selected_ep_num,
                total_episodes=None,
                source="local",
                use_ipc=True,
            )

            final_episode = selected_ep_num
            if (
                playback_result
                and isinstance(playback_result.data, dict)
                and isinstance(playback_result.data.get("episode"), int)
            ):
                final_episode = playback_result.data["episode"]

            final_ep_path = next(
                (file_path for ep_num, file_path in episodes if ep_num == final_episode),
                ep_path,
            )

            if anilist_id is None:
                anilist_id = _discover_anilist_id(selected_title)

            from commands.anime import handle_post_playback_confirmation

            handle_post_playback_confirmation(
                anime_title=selected_title,
                episode_number=final_episode,
                num_episodes=None,
                anilist_id=anilist_id,
                source="local",
                is_local=True,
                file_path=final_ep_path,
            )

            post_playback_action = _show_post_playback_menu(episodes, final_episode)
            current_idx = next(
                (i for i, (ep_num, _) in enumerate(episodes) if ep_num == final_episode),
                None,
            )

            if not post_playback_action:
                selected_ep_num = None
                continue

            if post_playback_action == "📂 Voltar à biblioteca local":
                break

            if post_playback_action == "▶️  Próximo" and current_idx is not None:
                if current_idx < len(episodes) - 1:
                    selected_ep_num = episodes[current_idx + 1][0]
                else:
                    selected_ep_num = None
                continue

            if post_playback_action == "◀️  Anterior" and current_idx is not None:
                if current_idx > 0:
                    selected_ep_num = episodes[current_idx - 1][0]
                else:
                    selected_ep_num = None
                continue

            if post_playback_action == "🔁 Replay":
                selected_ep_num = final_episode
                continue

            if post_playback_action == "📚 Voltar à biblioteca do anime":
                selected_ep_num = None
                continue

            if post_playback_action == "🗑️  Apagar episódio atual":
                deleted = service.delete_episode(selected_title, final_episode)
                if deleted:
                    logger.info(f"🗑️  Episódio {final_episode} apagado")
                else:
                    logger.info("❌ Episódio não encontrado para apagar")
                selected_ep_num = None
