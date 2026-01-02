"""History management service.

This module provides functions for managing watch history:
- Loading history with migration support
- Saving history with timestamps and AniList IDs
- Resetting history for specific anime

Used by: ui/anime_menus.py, core/anime_service.py
"""

import time
from json import dump, load
from sys import exit

import re

from models.config import get_data_path
from services.repository import rep
from ui.components import loading, menu_navigate

# Use centralized path function from config
HISTORY_PATH = get_data_path()


def clean_anime_title_for_search(title: str) -> str:
    """Remove common suffixes from anime title for better search results.

    Removes patterns like (Dublado), (Legendado), (Completo), etc.
    This helps when searching for anime that may have changed naming in scrapers.

    Args:
        title: Original anime title (may contain suffixes)

    Returns:
        Cleaned title without common suffixes

    Examples:
        "Tougen Anki (Dublado)" -> "Tougen Anki"
        "Dandadan 2ª Temporada Dublado" -> "Dandadan 2ª Temporada"
    """
    # Remove common suffixes in parentheses
    title = re.sub(r'\s*\((Dublado|Legendado|Completo|Dual Audio|PT-BR)\)\s*', '', title, flags=re.IGNORECASE)
    # Remove standalone "Dublado" or "Legendado" at the end
    title = re.sub(r'\s+(Dublado|Legendado|Completo|Dual Audio|PT-BR)\s*$', '', title, flags=re.IGNORECASE)
    return title.strip()


def load_history():
    """Load watch history and let user choose episode (-1/0/+1 from last watched).

    Old formats:
    - v1: {"anime_name": [episodes_urls, episode_idx], ...}
    - v2: {"anime_name": [timestamp, episode_idx], ...}
    - v3: {"anime_name": [timestamp, episode_idx, anilist_id], ...}
    - v4: {"anime_name": [timestamp, episode_idx, anilist_id, source], ...}
    New format:
    - v5: {"anime_name": [timestamp, episode_idx, anilist_id, source, total_episodes], ...}

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
                    # Migrate: [episodes_urls, episode_idx] → [timestamp, episode_idx, None, None, None]
                    data[anime_name] = [int(time.time()), info[1], None, None, None]
                # Check if missing anilist_id (v2 format)
                elif len(info) == 2:
                    needs_migration = True
                    # Migrate: [timestamp, episode_idx] → [timestamp, episode_idx, None, None, None]
                    data[anime_name] = [info[0], info[1], None, None, None]
                # Check if missing source (v3 format)
                elif len(info) == 3:
                    needs_migration = True
                    # Migrate: [timestamp, episode_idx, anilist_id] → [timestamp, episode_idx, anilist_id, None, None]
                    data[anime_name] = [info[0], info[1], info[2], None, None]
                # Check if missing total_episodes (v4 format)
                elif len(info) == 4:
                    needs_migration = True
                    # Migrate: [timestamp, episode_idx, anilist_id, source] → [timestamp, episode_idx, anilist_id, source, None]
                    data[anime_name] = [info[0], info[1], info[2], info[3], None]

            # Save migrated data
            if needs_migration:
                with file_path.open("w") as f_write:
                    dump(data, f_write)

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
                    anilist_title = anime_info.get("title", {}).get("romaji")

                # Get progress from AniList (source of truth)
                entry = anilist_client.get_media_list_entry(anilist_id)
                if entry and entry.get("progress"):
                    anilist_episode_idx = entry["progress"] - 1  # Convert to 0-based index

            # Use maximum progress from both sources, never go backwards
            if anilist_episode_idx > local_episode_idx:
                last_episode_idx = anilist_episode_idx
                progress_source = "AniList"
            else:
                last_episode_idx = local_episode_idx
                # Keep "Local" as default if both are equal or local is higher

            # Search for episodes to offer -1/0/+1 options
            # Clean title to improve search (remove Dublado, Legendado, etc)
            search_title = clean_anime_title_for_search(anime)
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
                retry_choice = menu_navigate(
                    retry_options, msg="O que deseja fazer?"
                )

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
                selected_episode = menu_navigate(
                    episode_list, msg="Escolha o episódio."
                )
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


def save_history(anime, episode, anilist_id=None, source=None, total_episodes=None) -> None:
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

    file_path = HISTORY_PATH / "history.json"
    try:
        with file_path.open("r+") as f:
            data = load(f)
            # Save with timestamp, anilist_id, source, and total_episodes (v5 format)
            data[anime] = [int(time.time()), episode, anilist_id, source, total_episodes]

        with file_path.open("w") as f:
            dump(data, f)

    except FileNotFoundError:
        HISTORY_PATH.mkdir(parents=True, exist_ok=True)

        with file_path.open("w") as f:
            data = {}
            # Save with timestamp, anilist_id, source, and total_episodes (v5 format)
            data[anime] = [int(time.time()), episode, anilist_id, source, total_episodes]
            dump(data, f)

    except PermissionError:
        return


def reset_history(anime) -> None:
    """Remove anime from watch history (reset to episode 0).

    Args:
        anime: Anime title to reset
    """
    file_path = HISTORY_PATH / "history.json"
    try:
        with file_path.open("r") as f:
            data = load(f)

        # Remove the anime from history if it exists
        if anime in data:
            del data[anime]

        with file_path.open("w") as f:
            dump(data, f)

    except FileNotFoundError:
        # File doesn't exist, nothing to reset
        pass
    except PermissionError:
        # Can't write to file, silently fail
        pass
