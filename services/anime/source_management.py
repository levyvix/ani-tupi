"""Source switching logic for anime playback.

Allows users to switch between different scraper sources mid-playback
while maintaining episode progress and AniList synchronization.
"""

import json

from models.config import get_data_path
from services.repository import rep
from ui.components import loading, menu_navigate, menu_navigate_episodes
from services.anime.title_normalization import (
    normalize_anime_title,
    normalize_title_for_dedup,
)
from utils.logging import get_logger
from services.anime.mappings import (
    load_anilist_search_title,
)
from services.anime.search import incremental_search_anime

logger = get_logger(__name__)

HISTORY_PATH = get_data_path()


def switch_anime_source(
    current_anime: str,
    args,
    anilist_id: int | None = None,
    display_title: str | None = None,
) -> tuple[str, int] | tuple[None, None]:
    """Allow user to switch to a different anime source/title.

    Performs a NEW complete search (incremental) for the anime title,
    allowing user to discover different sources and versions.
    Maintains progress from local history and AniList (as fallback).

    Args:
        current_anime: Current anime title being watched
        args: CLI arguments
        anilist_id: Optional AniList ID for progress fallback
        display_title: Optional original display title from AniList (for search)

    Returns: (new_anime_title, episode_idx) or (None, None) if cancelled
    """
    # SAVE: Preserve current anime's episode data (search_anime will destroy it)
    saved_episode_data = None
    if current_anime in rep.anime_episodes_urls:
        # Store shallow copies of the data structures for restoration
        saved_episode_data = rep.save_episode_state(current_anime)

    # 1. Determine search query (use saved AniList search title if available)
    if anilist_id:
        search_query = load_anilist_search_title(anilist_id)
    else:
        search_query = None
    search_query = search_query or display_title or current_anime

    # Normalize the AniList title to get best search query
    normalized_variations = normalize_anime_title(search_query)
    if normalized_variations:
        search_query = normalized_variations[0]

    # 2. Perform INCREMENTAL search (same as search_anime_flow)
    rep.clear_search_results()
    state, search_results = incremental_search_anime(search_query)

    # If no results at all
    if not search_results:
        if saved_episode_data:
            rep.restore_episode_state(current_anime, saved_episode_data)
            logger.info("⚠️  Nenhuma fonte encontrada para trocar")
            logger.info("   💡 Mantendo fonte atual...")
        else:
            logger.info("⚠️  Nenhuma fonte encontrada")
        return None, None

    # 3. Show menu with navigation support (same as search_anime_flow)
    current_result_set = state.get_current()
    menu_title = "🔄 Trocar fonte\n"
    if current_result_set:
        menu_title += f"🔍 Busca: '{current_result_set.query}'\n"
        menu_title += f"Encontrados {len(current_result_set.results)} resultados. Escolha:"

    # Build menu options with navigation buttons
    menu_options = []

    # Add navigation buttons if available
    if state.has_previous():
        menu_options.append("⬅️  Resultados anteriores (mais palavras)")
    if state.has_next():
        menu_options.append("➡️  Resultados próximos (menos palavras)")

    # Normalize titles for display (same as anilist_integration.py)
    # Create mapping: normalized → original for lookup after selection
    normalized_to_original = {}
    normalized_search_results = []
    for title_with_sources in search_results:
        # Split into anime name and sources
        if " [" in title_with_sources:
            anime_name, sources_part = title_with_sources.split(" [", 1)
            sources_part = "[" + sources_part
        else:
            anime_name = title_with_sources
            sources_part = ""

        # Normalize anime name: lowercase, letters/numbers/apostrophes only
        normalized_name = normalize_title_for_dedup(anime_name)
        normalized_full = f"{normalized_name} {sources_part}".rstrip()
        normalized_to_original[normalized_name] = anime_name
        normalized_search_results.append(normalized_full)

    menu_options.extend(normalized_search_results)

    selected_anime_with_source = menu_navigate(menu_options, msg=menu_title)

    if not selected_anime_with_source:
        # User cancelled
        if saved_episode_data:
            rep.restore_episode_state(current_anime, saved_episode_data)
        return None, None

    # Handle navigation buttons
    if selected_anime_with_source == "⬅️  Resultados anteriores (mais palavras)":
        prev_set = state.go_back()
        if prev_set:
            # Recursively call with preserved state (simplified: just show previous results)
            # For now, restart the flow to keep it simple
            if saved_episode_data:
                rep.restore_episode_state(current_anime, saved_episode_data)
            return switch_anime_source(current_anime, args, anilist_id, display_title)
        return None, None

    if selected_anime_with_source == "➡️  Resultados próximos (menos palavras)":
        next_set = state.go_forward()
        if next_set:
            # Recursively call with preserved state
            if saved_episode_data:
                rep.restore_episode_state(current_anime, saved_episode_data)
            return switch_anime_source(current_anime, args, anilist_id, display_title)
        return None, None

    # User selected an anime - map normalized back to original
    normalized_selected = selected_anime_with_source.split(" [")[0]
    selected_anime = normalized_to_original.get(normalized_selected, normalized_selected)

    # 5. Load episodes from new source
    with loading("Carregando episódios..."):
        rep.search_episodes(selected_anime)

    # 6. Get episode list from new source
    episode_list = rep.get_episode_list(selected_anime)

    # 7. Check progress from both sources (AniList as primary source of truth)
    local_progress = 0
    anilist_progress = 0
    progress_source = ""

    # First check local history
    try:
        history_file = HISTORY_PATH / "history.json"
        with history_file.open() as f:
            history_data = json.load(f)
            if selected_anime in history_data:
                # history stores episode_idx (0-based), progress is 1-based
                local_progress = history_data[selected_anime][1] + 1
    except (OSError, KeyError, IndexError):
        pass  # No local history

    # 8. If have anilist_id, always check AniList (source of truth)
    # Use AniList as primary when available (you might have watched via web/mobile)
    if anilist_id:
        from services.anilist_service import anilist_client

        if anilist_client.is_authenticated():
            # Get media list entry for this anime
            entry = anilist_client.get_media_list_entry(anilist_id)
            if entry and entry.progress:
                anilist_progress = entry.progress

    # Use maximum progress available, preferring AniList when it's ahead
    max_progress = max(local_progress, anilist_progress)
    if max_progress > 0:
        if anilist_progress > local_progress:
            # AniList is ahead - user probably watched on web/mobile
            progress_source = "AniList"
        elif anilist_progress == local_progress and anilist_progress > 0:
            # Both equal and from AniList source
            progress_source = "AniList"
        else:
            # Local is ahead or AniList not available
            progress_source = "Local"

    # 9. If user has progress, offer -1/0/+1 options
    if max_progress > 0 and max_progress <= len(episode_list):
        options = []
        option_to_idx = {}

        # Next episode (+1) - SHOW FIRST
        if max_progress < len(episode_list):
            next_ep = f"⏭️  Episódio {max_progress + 1} (próximo)"
            options.append(next_ep)
            option_to_idx[next_ep] = max_progress

        # Current episode
        current_ep = f"▶️  Episódio {max_progress} ({progress_source})"
        options.append(current_ep)
        option_to_idx[current_ep] = max_progress - 1

        # Previous episode (-1)
        if max_progress > 1:
            prev_ep = f"◀️  Episódio {max_progress - 1} (anterior)"
            options.append(prev_ep)
            option_to_idx[prev_ep] = max_progress - 2

        # Add option to choose any episode
        options.append("📋 Escolher outro episódio")

        choice = menu_navigate(options, msg=f"{selected_anime} - De onde quer continuar?")

        if not choice:
            return None, None  # User cancelled

        if choice == "📋 Escolher outro episódio":
            # Let user choose from full episode list
            episode_idx = menu_navigate_episodes(episode_list)
            if episode_idx is None:
                return None, None
        else:
            episode_idx = option_to_idx[choice]
    else:
        # No progress - show full episode list
        episode_idx = menu_navigate_episodes(episode_list)

        if episode_idx is None:
            return None, None  # User cancelled

    return selected_anime, episode_idx


# get_next_episode_context is now imported from services.anime.episode_context
