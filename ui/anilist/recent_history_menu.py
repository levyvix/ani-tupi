"""Recent history menu for local anime playback history."""

import argparse
import json

from models.config import get_data_path
from ui.components import loading, menu_navigate
from utils.logging import get_logger

logger = get_logger(__name__)

# History file path (centralized from config)
HISTORY_PATH = get_data_path()

# Dependency injection holders
anilist_client = None
run_anime_actions = None


def set_anilist_client(client):
    """Set the AniList client dependency."""
    global anilist_client
    anilist_client = client


def set_run_anime_actions(callback):
    """Set the run_anime_actions callback."""
    global run_anime_actions
    run_anime_actions = callback


def get_search_title(title, display_title: str = "") -> str:
    """Get preferred title for search based on config.

    Args:
        title: AniListTitle object with romaji/english/native
        display_title: Fallback display title

    Returns:
        Title to use for searching (english or romaji based on config)
    """
    from models.config import settings

    if settings.anilist.prefer_english_title:
        return title.english or title.romaji or display_title
    return title.romaji or title.english or display_title


def show_recent_history() -> None:
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

        # Create args object
        args = argparse.Namespace(debug=False)

        # Show per-anime actions menu starting from AniList progress (source of truth)
        # Use max of AniList and local history to never go backwards
        run_anime_actions(
            search_title,
            saved_anilist_id,
            args,
            anilist_progress=starting_progress,  # Use AniList as source of truth
            display_title=display_title,
            total_episodes=total_episodes,  # Pass total episodes from AniList
        )

        # After the actions menu, loop back to show recent history again
