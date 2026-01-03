"""History management service.

This module provides functions for managing watch history:
- Loading history with timestamps and AniList IDs
- Saving history with timestamps and AniList IDs
- Resetting history for specific anime

Used by: ui/anime_menus.py, core/anime_service.py
"""

import time
from sys import exit

from models.config import get_data_path
from services.repository import rep
from ui.components import loading, menu_navigate
from utils.persistence import JSONStore
from utils.title_utils import clean_title_for_display
from utils.exceptions import PersistenceError
from utils.logging import get_logger

logger = get_logger(__name__)

# Use centralized path function from config
HISTORY_PATH = get_data_path()
_history_store = JSONStore(HISTORY_PATH / "history.json")


def load_history():
    """Load watch history and let user choose episode (-1/0/+1 from last watched).

    Format:
    - v5: {"anime_name": [timestamp, episode_idx, anilist_id, source, total_episodes], ...}

    Returns: (anime_name, episode_idx, anilist_id, anilist_title)
    """
    try:
        data = _history_store.load({})

        # Build menu with episode info (sorted by most recent)
        titles = {}
        # Sort by timestamp (descending - most recent first)
        sorted_data = sorted(data.items(), key=lambda x: x[1][0], reverse=True)

        for entry, info in sorted_data:
            episode_idx = info[1]
            total_episodes = info[4] if len(info) > 4 and info[4] else None

            if total_episodes:
                ep_info = f" ({episode_idx + 1}/{total_episodes})"
            else:
                ep_info = f" (Ep {episode_idx + 1})"
            titles[entry + ep_info] = len(ep_info)

        selected = menu_navigate(list(titles.keys()), msg="Continue assistindo.")

        if not selected:
            exit()  # User cancelled continue watching

        anime = selected[: -titles[selected]]
        local_episode_idx = data[anime][1]
        anilist_id = data[anime][2] if len(data[anime]) > 2 else None
        saved_source = data[anime][3] if len(data[anime]) > 3 else None

        # If we have anilist_id, check AniList for progress (source of truth)
        anilist_title = None
        anilist_episode_idx = -1
        progress_source = "Local"

        if anilist_id:
            from services.anilist_service import anilist_client

            anime_info = anilist_client.get_anime_by_id(anilist_id)
            if anime_info:
                # Use romaji title as primary
                anilist_title = anime_info.title.romaji

            # Get progress from AniList (source of truth)
            entry = anilist_client.get_media_list_entry(anilist_id)
            if entry and entry.progress:
                anilist_episode_idx = entry.progress - 1  # Convert to 0-based index

        # Use maximum progress from both sources, never go backwards
        if anilist_episode_idx > local_episode_idx:
            last_episode_idx = anilist_episode_idx
            progress_source = "AniList"
        else:
            last_episode_idx = local_episode_idx
            # Keep "Local" as default if both are equal or local is higher

        # Search for episodes to offer -1/0/+1 options
        # Clean title to improve search (remove Dublado, Legendado, etc)
        search_title = clean_title_for_display(anime)
        rep.clear_search_results()

        if search_title != anime:
            with loading(f"Buscando '{search_title}' (título simplificado)..."):
                rep.search_anime(search_title)
        else:
            with loading(f"Buscando '{anime}'..."):
                rep.search_anime(anime)

        # Check if multiple anime results (different sources/versions)
        anime_titles = rep.get_anime_titles()
        selected_anime_title = None

        if len(anime_titles) > 1:
            # Multiple results - let user choose
            anime_with_sources = rep.get_anime_titles_with_sources()
            selected = menu_navigate(
                anime_with_sources,
                msg=f"Múltiplas fontes encontradas para '{anime}'. Escolha uma:",
            )
            if not selected:
                exit()  # User cancelled

            # Extract anime title (remove source info)
            # Format is "Title [source1, source2]"
            selected_anime_title = selected.rsplit(" [", 1)[0]
        elif len(anime_titles) == 1:
            # Single result - use it directly
            selected_anime_title = anime_titles[0]
        else:
            # No results - will be handled below
            selected_anime_title = search_title

        # Load episodes for selected anime
        # Use saved source if available (faster and more accurate)
        if saved_source:
            with loading(f"Carregando episódios de {saved_source}..."):
                rep.search_episodes(selected_anime_title, source_filter=saved_source)
        else:
            with loading("Carregando episódios..."):
                rep.search_episodes(selected_anime_title)
        episode_list = rep.get_episode_list(selected_anime_title)

        # Update anime reference to selected one
        anime = selected_anime_title

        if not episode_list:
            # Anime not found in scrapers - offer options
            print(f"\n⚠️  '{anime}' não foi encontrado nos scrapers disponíveis.")
            print("Possíveis motivos:")
            print("  • O anime foi removido do scraper")
            print("  • O nome mudou no site")
            print("  • O scraper está temporariamente offline")

            retry_options = [
                "🔄 Tentar novamente",
                "🗑️  Remover do histórico",
                "← Voltar ao menu de histórico",
            ]
            retry_choice = menu_navigate(retry_options, msg="O que deseja fazer?")

            if retry_choice == "🔄 Tentar novamente":
                # Retry: recursively call load_history() again
                return load_history()
            elif retry_choice == "🗑️  Remover do histórico":
                reset_history(anime)
                print(f"✅ '{anime}' removido do histórico.")
                input("\nPressione Enter para continuar...")
                return load_history()  # Show history menu again
            else:
                # Go back to history menu
                return load_history()

        # Offer -1/0/+1 options (previous, current, next)
        last_ep_num = last_episode_idx + 1
        options = []
        option_to_idx = {}

        # Previous episode (-1)
        if last_episode_idx > 0:
            prev_ep = f"◀️  Episódio {last_ep_num - 1} (anterior)"
            options.append(prev_ep)
            option_to_idx[prev_ep] = last_episode_idx - 1

        # Current episode (0) - show source of progress
        current_ep = f"▶️  Episódio {last_ep_num} ({progress_source})"
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
        options.append("🔄 Começar do zero")

        choice = menu_navigate(options, msg=f"{anime} - De onde quer continuar?")

        if not choice:
            exit()  # User cancelled

        if choice == "📋 Escolher outro episódio":
            # Let user choose from full episode list
            selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                exit()
            episode_idx = episode_list.index(selected_episode)
        elif choice == "🔄 Começar do zero":
            # Confirm before resetting
            confirm_reset = menu_navigate(
                ["✅ Sim, resetar", "❌ Cancelar"],
                msg="Tem certeza que quer começar do zero? Seu progresso será perdido.",
            )
            if confirm_reset == "✅ Sim, resetar":
                reset_history(anime)
                episode_idx = 0
                print("✅ Histórico resetado! Começando do episódio 1...")
            else:
                exit()  # User cancelled
        else:
            episode_idx = option_to_idx[choice]
            # Check if episode is unavailable (marked as None)
            if episode_idx is None:
                print(f"\n⏳ Episódio {last_ep_num + 1} ainda não disponível nos scrapers.")
                input("\nPressione Enter para voltar...")
                exit()

        return anime, episode_idx, anilist_id, anilist_title
    except FileNotFoundError:
        logger.error("History file not found, exiting")
        exit()
    except PersistenceError as e:
        logger.error(f"Permission error accessing history: {e}")
        return None


def save_history(anime: str, episode: int, anilist_id: int | None = None, source: str | None = None, total_episodes: int | None = None) -> None:
    """Save watch history with timestamp, optional AniList ID, source, and total episodes.

    Format: {"anime_name": [timestamp, episode_idx, anilist_id, source, total_episodes], ...}
    - anilist_id can be None for anime not from AniList
    - source is the scraper name (e.g., "animefire", "animesonlinecc")
    - total_episodes is the known total count of episodes (auto-detected if not provided)
    """
    # Auto-detect total_episodes if not provided
    if total_episodes is None:
        episode_list = rep.get_episode_list(anime)
        if episode_list:
            total_episodes = len(episode_list)

    try:
        _history_store.set(anime, [int(time.time()), episode, anilist_id, source, total_episodes])
    except PersistenceError as e:
        logger.error(f"Failed to save history: {e}")


def save_history_from_event(
    anime_title: str,
    episode_idx: int,
    action: str = "watched",
    source: str | None = None,
    anilist_id: int | None = None,
) -> dict[str, str | bool]:
    """Save watch history from IPC keybinding event and sync with AniList.

    This function is called when the user triggers episode navigation via
    keybindings (Shift+N, Shift+M, etc.) during MPV playback.

    Args:
        anime_title: Anime name
        episode_idx: 0-based episode index
        action: Action type - "watched" (marked as watched), "started" (began watching),
                "skipped" (skipped episode)
        source: Scraper source name (e.g., "animefire")
        anilist_id: AniList ID for syncing (optional, will try to get from repository if not provided)

    Returns:
        Dict with sync information:
        - "anilist_added": True if added to AniList list, False otherwise
        - "anilist_status_change": Status change message (e.g., "PLANNING → CURRENT") or None
        - "anilist_progress_synced": True if progress was synced, False otherwise
        - "anilist_message": Human-readable message about AniList operations
    """
    # Get total episodes from repository if available
    total_episodes = None
    episode_list = rep.get_episode_list(anime_title)
    if episode_list:
        total_episodes = len(episode_list)

    # Get AniList ID from parameter or repository
    if anilist_id is None:
        anilist_id = rep.anime_to_anilist_id.get(anime_title)
        # If still None, try to get from history
        if anilist_id is None:
            try:
                history_data = _history_store.load({})
                if anime_title in history_data:
                    history_entry = history_data[anime_title]
                    if len(history_entry) > 2:
                        anilist_id = history_entry[2]
            except Exception:
                pass

    # Initialize return values
    sync_info = {
        "anilist_added": False,
        "anilist_status_change": None,
        "anilist_progress_synced": False,
        "anilist_message": None,
    }

    try:
        # Save with action metadata in a separate tracking object
        # Keep the original history format intact for backward compatibility
        _history_store.set(
            anime_title,
            [int(time.time()), episode_idx, anilist_id, source, total_episodes]
        )
        logger.info(
            f"Saved history for '{anime_title}' Ep {episode_idx + 1} (action: {action})"
        )
    except PersistenceError as e:
        logger.error(f"Failed to save history event for '{anime_title}': {e}")

    # Sync with AniList if authenticated and anilist_id is available
    if anilist_id and action == "watched":
        from services.anilist_service import anilist_client
        
        if anilist_client.is_authenticated():
            try:
                # Check if anime is in any list
                if not anilist_client.is_in_any_list(anilist_id):
                    logger.info(f"Adding '{anime_title}' to AniList CURRENT list")
                    anilist_client.add_to_list(anilist_id, "CURRENT")
                    sync_info["anilist_added"] = True
                    sync_info["anilist_message"] = "✅ Adicionado ao AniList"
                else:
                    # Auto-promote from PLANNING to CURRENT, or COMPLETED to REPEATING
                    entry = anilist_client.get_media_list_entry(anilist_id)
                    if entry:
                        old_status = entry.status
                        if entry.status == "PLANNING":
                            logger.info(f"Moving '{anime_title}' from PLANNING to CURRENT")
                            anilist_client.add_to_list(anilist_id, "CURRENT")
                            sync_info["anilist_status_change"] = "PLANNING → CURRENT"
                            sync_info["anilist_message"] = "✅ Movido para CURRENT no AniList"
                        elif entry.status == "COMPLETED":
                            logger.info(f"Changing '{anime_title}' to REPEATING")
                            anilist_client.change_status(anilist_id, "REPEATING")
                            sync_info["anilist_status_change"] = "COMPLETED → REPEATING"
                            sync_info["anilist_message"] = "✅ Status alterado para REPEATING no AniList"

                # Update progress (episode_idx is 0-based, convert to 1-based)
                episode_number = episode_idx + 1
                success = anilist_client.update_progress(anilist_id, episode_number)
                if success:
                    logger.info(f"Synced progress to AniList: Ep {episode_number}")
                    sync_info["anilist_progress_synced"] = True
                    if not sync_info["anilist_message"]:
                        sync_info["anilist_message"] = "✅ Progresso atualizado no AniList"
                else:
                    # Verify token is still valid if sync failed
                    viewer = anilist_client.get_viewer_info()
                    if not viewer:
                        logger.warning("AniList token expired - sync failed")
                    else:
                        logger.warning(f"Failed to sync progress to AniList for Ep {episode_number}")
            except Exception as e:
                logger.error(f"Error syncing with AniList: {e}")

    return sync_info


def reset_history(anime: str) -> None:
    """Remove anime from watch history (reset to episode 0).

    Args:
        anime: Anime title to reset
    """
    try:
        _history_store.delete(anime)
        logger.info(f"Reset history for '{anime}'")
    except PersistenceError as e:
        logger.error(f"Failed to reset history for '{anime}': {e}")
