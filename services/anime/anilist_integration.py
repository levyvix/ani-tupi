"""AniList integration flows for anime playback.

Handles AniList-specific anime flows including search, selection, progress tracking,
sequel detection, and synchronization with AniList API.
"""

import json
from typing import Optional

from models.config import get_data_path
from services.anilist_service import anilist_client
from services.repository import rep
from ui.components import loading, menu_navigate
from utils.scraper_cache import get_cache, set_cache
from scrapers import loader
from models.models import Status
from services.history_service import save_history, reset_history
from utils.video_player import VideoPlayer
from services.anime.source_management import switch_anime_source
from utils.logging import get_logger
from services.anime.mappings import (
    load_anilist_mapping,
    load_anilist_urls,
    save_anilist_mapping,
    load_language_preference,
    save_language_preference,
)
from services.anime.search import incremental_search_anime
from services.anime.search import _rank_anime_results_by_reference
from services.anime.title_normalization import normalize_title_for_dedup
from services.anime.playback_fallback import play_episode_with_fallback
from utils.video_player import _format_episode_progress

# Use centralized path function from config
HISTORY_PATH = get_data_path()

logger = get_logger(__name__)


def build_anilist_post_playback_options(current_episode_idx: int, num_episodes: int) -> list[str]:
    """Build post-playback options for AniList playback flow."""
    opts = []
    has_next_episode = current_episode_idx < num_episodes - 1

    if has_next_episode:
        opts.append("▶️  Próximo")
    else:
        opts.append("↩️  Voltar ao menu anterior")

    if current_episode_idx > 0:
        opts.append("◀️  Anterior")

    opts.append("🔁 Replay")
    opts.append("📋 Escolher outro episódio")
    opts.append("🔄 Trocar fonte")
    return opts


def _is_anime_released(anime_node) -> bool:
    """Check if an anime has started airing or is finished.

    Args:
        anime_node: AniListRelationNode with status and startDate

    Returns:
        True if anime has started airing (RELEASING or FINISHED), False if not yet released
    """
    if not anime_node:
        return True  # Assume released if no data

    # Check status field
    if hasattr(anime_node, "status"):
        status = anime_node.status
        if status == "NOT_YET_RELEASED":
            return False
        if status in ("RELEASING", "FINISHED"):
            return True

    return True  # Default to released if status is unknown


def offer_sequel_and_continue(
    anilist_id: int,
    args,
    current_episode: Optional[int] = None,
    anilist_episodes: Optional[int] = None,
) -> bool:
    """Check for sequels when last episode is watched and offer to continue.

    Args:
        anilist_id: AniList ID of the anime just watched
        args: Command line arguments
        current_episode: Current episode number (for checking if series is truly complete)
        anilist_episodes: Total episodes on AniList (if known)

    Returns:
        True if user accepted sequel and it started playback, False otherwise
    """
    # Only offer sequels if authenticated
    if not anilist_client.is_authenticated():
        return False

    # If we know the AniList episode count, check if series is actually complete
    # This prevents offering sequels when the current source has fewer episodes
    if anilist_episodes and current_episode:
        if current_episode < anilist_episodes:
            # User has more episodes to watch - don't offer sequel
            logger.info(
                f"\n💡 Existem mais {anilist_episodes - current_episode} episódio(s) disponível(is) em outras fontes."
            )
            return False

    # Get sequels from AniList
    sequels = anilist_client.get_sequels(anilist_id)

    if not sequels:
        return False  # No sequels found

    # Format sequel options
    if len(sequels) == 1:
        sequel = sequels[0]
        sequel_title = anilist_client.format_title(sequel.title)
        is_released = _is_anime_released(sequel)

        # Single sequel: offer multiple options (but suggest Planning if not yet released)
        if is_released:
            menu_options = [
                "▶️ Procurar episódios",
                "📋 Adicionar à 'Planejo Assistir'",
                "❌ Não, parar aqui",
            ]
        else:
            menu_options = ["📋 Adicionar à 'Planejo Assistir'", "❌ Não, parar aqui"]
            sequel_title += " ⏳ (ainda não lançado)"

        choice = menu_navigate(
            menu_options,
            msg=f"Deseja continuar com a sequência?\n\n→ {sequel_title}",
        )

        if choice == "▶️ Procurar episódios":
            # Get sequel info and start playback
            anilist_anime_flow(
                sequel_title,
                sequel.id,
                args,
                anilist_progress=0,
                display_title=sequel_title,
                total_episodes=sequel.episodes,
            )
            return True
        elif choice == "📋 Adicionar à 'Planejo Assistir'":
            # Add to Planning list without searching for episodes
            success = anilist_client.add_to_list(sequel.id, Status.PLANNING)
            if success:
                logger.info(f"✅ {sequel_title} adicionado à sua lista de 'Planejo Assistir'!")
            else:
                logger.info(f"❌ Erro ao adicionar {sequel_title} à sua lista.")
            return False
    else:
        # Multiple sequels: let user choose and then ask what to do
        sequel_options = []
        for s in sequels:
            title = anilist_client.format_title(s.title)
            is_released = _is_anime_released(s)
            if not is_released:
                title += " ⏳"
            sequel_options.append(title)

        choice = menu_navigate(
            sequel_options + ["❌ Não, parar aqui"],
            msg="Qual sequência deseja assistir?",
        )

        if choice and choice != "❌ Não, parar aqui":
            # Find selected sequel (removing the ⏳ indicator if present)
            choice_clean = choice.replace(" ⏳", "")
            selected_sequel = next(
                (s for s in sequels if anilist_client.format_title(s.title) == choice_clean),
                None,
            )
            if selected_sequel:
                sequel_title = anilist_client.format_title(selected_sequel.title)
                is_released = _is_anime_released(selected_sequel)

                # Ask what user wants to do (but suggest Planning if not yet released)
                if is_released:
                    action_options = [
                        "▶️ Procurar episódios",
                        "📋 Adicionar à 'Planejo Assistir'",
                        "❌ Cancelar",
                    ]
                else:
                    action_options = [
                        "📋 Adicionar à 'Planejo Assistir'",
                        "❌ Cancelar",
                    ]
                    sequel_title += " ⏳ (ainda não lançado)"

                action_choice = menu_navigate(
                    action_options,
                    msg=f"O que deseja fazer com {sequel_title}?",
                )

                if action_choice == "▶️ Procurar episódios":
                    anilist_anime_flow(
                        sequel_title,
                        selected_sequel.id,
                        args,
                        anilist_progress=0,
                        display_title=sequel_title,
                        total_episodes=selected_sequel.episodes,
                    )
                    return True
                elif action_choice == "📋 Adicionar à 'Planejo Assistir'":
                    # Add to Planning list without searching for episodes
                    success = anilist_client.add_to_list(selected_sequel.id, Status.PLANNING)
                    if success:
                        logger.info(
                            f"\n✅ {sequel_title} adicionado à sua lista de 'Planejo Assistir'!"
                        )
                    else:
                        logger.info(f"❌ Erro ao adicionar {sequel_title} à sua lista.")
                    return False

    return False


def anilist_anime_flow(
    anime_title: str,
    anilist_id: int,
    args,
    anilist_progress: int = 0,
    display_title: str | None = None,
    total_episodes: int | None = None,
) -> None:
    """Flow for anime selected from AniList
    Searches scrapers for the anime and starts normal playback flow.

    Args:
        anime_title: Title to search for (romaji or english)
        anilist_id: AniList ID for syncing
        args: Command line arguments
        anilist_progress: Current episode progress from AniList (0 if not watching)
        display_title: Full bilingual title for display (romaji / english)
        total_episodes: Total number of episodes from AniList (None if unknown)

    """
    # Use display_title if provided, otherwise fall back to anime_title
    if not display_title:
        display_title = anime_title

    # Get full anime info from AniList to access both English and Romaji titles
    anime_info = anilist_client.get_anime_by_id(anilist_id)
    english_title = None
    romaji_title = None
    if anime_info:
        english_title = anime_info.title.english
        romaji_title = anime_info.title.romaji

    loader.load_plugins()

    # Clear previous search results to avoid accumulating data from previous calls
    # (Repository is singleton, so it keeps data between calls)
    rep.clear_search_results()

    # Store anilist_id in repository for caching (cache key)
    if anilist_id:
        rep.anime_to_anilist_id[anime_title] = anilist_id

    # Show active sources
    active_sources = rep.get_active_sources()
    if active_sources:
        logger.info(f"ℹ️  Fontes ativas: {', '.join(active_sources)}")

    # Check if we have a saved title choice from before (ASK BEFORE SEARCHING)
    saved_title, saved_source, saved_url = (
        load_anilist_mapping(anilist_id) if anilist_id else (None, None, None)
    )
    selected_anime = None
    source = None
    episode_list = None
    scraper_episode_count = None
    episodes_already_loaded = False

    if saved_title:
        # Format title with source for display
        display_title_with_source = saved_title
        if saved_source:
            display_title_with_source = f"{saved_title} [{saved_source}]"

        # Ask user if they want to continue with saved choice BEFORE searching
        choice = menu_navigate(
            ["✅ Continuar com este", "🔄 Escolher outro"],
            msg=f"Você usou '{display_title_with_source}' antes.\nQuer continuar?",
        )

        if not choice:
            return  # User cancelled

        if choice == "✅ Continuar com este":
            selected_anime = saved_title
            source = saved_source
            logger.info(f"✅ Usando: {selected_anime}")
            # Fluxo normal vai procurar episódios (não salva/usa URL)

    # Only ask for language preference if no saved title or user wants to choose another
    if selected_anime is None and english_title and romaji_title:
        # Compare normalized titles - if they're the same, skip the menu
        normalized_english = normalize_title_for_dedup(english_title)
        normalized_romaji = normalize_title_for_dedup(romaji_title)

        if normalized_english == normalized_romaji:
            # Titles are the same when normalized - use Romaji by default
            anime_title = romaji_title
        else:
            # Titles are different - ask user for language preference
            # Check if language preference is cached
            cached_language = load_language_preference(anilist_id) if anilist_id else None

            if cached_language:
                # Use cached language preference
                anime_title = english_title if cached_language == "english" else romaji_title
            else:
                # Ask user for language preference
                language_options = [
                    f"🇯🇵 Romanji: {romaji_title}",
                    f"🇬🇧 Inglês: {english_title}",
                ]
                language_choice = menu_navigate(
                    language_options, msg="Escolha o idioma para buscar:"
                )

                if not language_choice:
                    return  # User cancelled

                # Set anime_title based on choice and cache the preference
                if language_choice.startswith("🇬🇧"):
                    anime_title = english_title
                    if anilist_id:
                        save_language_preference(anilist_id, "english")
                else:
                    anime_title = romaji_title
                    if anilist_id:
                        save_language_preference(anilist_id, "romaji")

    # Only search if no saved title or user wants to choose another
    search_state = None
    titles_with_sources = None
    used_query = None
    # Note: Don't reset 'source' here - it's set in "Continuar com este" block above
    # Only reset if selected_anime is None
    if selected_anime is None:
        source = None

    if selected_anime is None:
        # Cache-first: Check if anime_title is in cache before searching
        cache_data = get_cache(anime_title)

        if cache_data:
            # Found in cache! Use it directly
            logger.info(f"ℹ️  Usando cache ({cache_data.episode_count} eps disponíveis)")
            rep.load_from_cache(anime_title, cache_data)

            # Discover available sources for this anime (background search)
            rep.search_anime(anime_title, verbose=False)

            used_query = anime_title
            # Don't filter - repo.search_anime already loaded cache data
            # If we filter by anime_title, we might exclude alternate title versions in cache
            titles_with_sources = rep.get_anime_titles_with_sources()
            if not titles_with_sources:
                titles_with_sources = [anime_title]
        else:
            # Not in cache: use incremental search (start with min(3,len(words)) and filter)
            search_state, titles_with_sources = incremental_search_anime(
                anime_title,
                english_title=english_title,
                romaji_title=romaji_title,
            )

            if titles_with_sources and romaji_title:
                titles_with_sources = _rank_anime_results_by_reference(
                    titles_with_sources, romaji_title
                )

            # Extract the query that was actually used for the final results
            if search_state:
                current_result_set = search_state.get_current()
                if current_result_set:
                    used_query = current_result_set.query

    if selected_anime is None and not titles_with_sources:
        # Offer manual search (only if we haven't found anything)
        choice = menu_navigate(
            ["🔍 Buscar manualmente", "🔙 Voltar ao AniList"], msg="O que deseja fazer?"
        )

        if not choice:
            return  # User cancelled

        if choice == "🔍 Buscar manualmente":
            manual_query = input("\n🔍 Digite o nome para buscar: ")

            # Cache-first: Check if manual query is in cache
            cache_data = get_cache(manual_query)
            if cache_data:
                logger.info(f"ℹ️  Usando cache ({cache_data.episode_count} eps disponíveis)")
                rep.load_from_cache(manual_query, cache_data)

                # Discover available sources for this anime (background search)
                rep.search_anime(manual_query, verbose=False)

                # Get formatted title with sources from scrapers
                titles_with_sources = rep.get_anime_titles_with_sources(
                    filter_by_query=manual_query, original_query=manual_query
                )
                if not titles_with_sources:
                    titles_with_sources = [manual_query]

                used_query = manual_query
                search_state = None  # No navigation state for manual cached search
            else:
                # Not in cache: use incremental search for manual query
                search_state, titles_with_sources = incremental_search_anime(
                    manual_query,
                    english_title=english_title,
                    romaji_title=romaji_title,
                )

                if titles_with_sources and romaji_title:
                    titles_with_sources = _rank_anime_results_by_reference(
                        titles_with_sources, romaji_title
                    )

                # Extract the query that was actually used for the final results
                if search_state:
                    current_result_set = search_state.get_current()
                    if current_result_set:
                        used_query = current_result_set.query

            if not titles_with_sources:
                return
        else:
            return  # Back to AniList menu

    # Loop to allow navigation between result sets and selection
    while selected_anime is None:
        # Show menu with optional navigation if search_state exists
        menu_title = f"📺 Anime do AniList: '{display_title}'\n"

        # Show search result set info if using incremental search
        if search_state:
            current_result_set = search_state.get_current()
            if current_result_set:
                # Use the normalized used_query from the result set
                display_query = current_result_set.used_query or current_result_set.query
                menu_title += f"🔍 Busca usada: '{display_query}'\n"
                menu_title += f"   ({current_result_set.word_count} palavras: {len(current_result_set.results)} resultados)\n"
        else:
            # For cache hits, use the query that was already used
            display_query = used_query or anime_title
            menu_title += f"🔍 Busca usada: '{display_query}'\n"

        menu_title += f"\nEncontrados {len(titles_with_sources)} resultados. Escolha:"

        # Show all results (no pagination)
        titles_to_show = titles_with_sources

        # Normalize anime titles for display (lowercase, letters and numbers only)
        # Keep sources as is, only normalize the anime name part
        # Create mapping from normalized title → original title for lookup after selection
        normalized_to_original = {}
        normalized_titles_to_show = []
        for title_with_sources in titles_to_show:
            # Split into title and sources
            if " [" in title_with_sources:
                anime_name, sources_part = title_with_sources.split(" [", 1)
                sources_part = "[" + sources_part
            else:
                anime_name = title_with_sources
                sources_part = ""

            # Normalize only the anime name
            normalized_name = normalize_title_for_dedup(anime_name)
            normalized_full = f"{normalized_name} {sources_part}".rstrip()

            normalized_to_original[normalized_name] = anime_name
            normalized_titles_to_show.append(normalized_full)

        normalized_titles_all = []
        for title_with_sources in titles_with_sources:
            # Split into title and sources
            if " [" in title_with_sources:
                anime_name, sources_part = title_with_sources.split(" [", 1)
                sources_part = "[" + sources_part
            else:
                anime_name = title_with_sources
                sources_part = ""

            # Normalize only the anime name
            normalized_name = normalize_title_for_dedup(anime_name)
            normalized_full = f"{normalized_name} {sources_part}".rstrip()

            normalized_to_original[normalized_name] = anime_name
            normalized_titles_all.append(normalized_full)

        # Build menu options (all normalized titles)
        titles_with_button = normalized_titles_to_show

        # Calculate language toggle button parameters
        can_toggle_language = (
            search_state
            and search_state.can_toggle_language()
            and english_title
            and romaji_title
            and english_title != romaji_title
        )
        alt_lang = search_state.get_alternative_language() if search_state else None
        alt_label = (
            f"🔄 Re-buscar em {'Inglês' if alt_lang == 'english' else 'Romanji'}"
            if can_toggle_language
            else None
        )

        # Show menu with navigation support
        selected_anime_with_source = menu_navigate(
            titles_with_button,
            msg=menu_title,
            search_state=search_state,
            alternative_language_available=can_toggle_language,
            alternative_language_label=alt_label,
        )

        if not selected_anime_with_source:
            return  # User cancelled

        # Handle language toggle
        if selected_anime_with_source == "__research_language__":
            # Toggle to alternative language and re-search
            assert search_state is not None
            new_lang = search_state.toggle_language()
            new_title = english_title if new_lang == "english" else romaji_title

            # Clear repository to remove old search results
            rep.clear_search_results()

            # Store anilist_id in repository for caching with new title
            if anilist_id:
                rep.anime_to_anilist_id[new_title] = anilist_id

            # Re-search with alternative language
            search_state, titles_with_sources = incremental_search_anime(
                new_title,
                english_title=english_title,
                romaji_title=romaji_title,
            )

            # Extract the query that was actually used
            if search_state:
                current_result_set = search_state.get_current()
                if current_result_set:
                    used_query = current_result_set.query

            continue  # Loop back to show menu with new results

        # Handle incremental search navigation
        if selected_anime_with_source == "__nav_previous__":
            # Navigate to previous result set
            assert search_state is not None
            search_state.go_back()
            new_result_set = search_state.get_current()
            assert new_result_set is not None
            titles_with_sources = new_result_set.results
            continue  # Loop back to show menu with new results

        elif selected_anime_with_source == "__nav_next__":
            # Navigate to next result set
            assert search_state is not None
            search_state.go_forward()
            new_result_set = search_state.get_current()
            assert new_result_set is not None
            titles_with_sources = new_result_set.results
            continue  # Loop back to show menu with new results

        else:
            # selected_anime_with_source is from normalized_titles_to_show (already normalized)
            # We need to get the actual title from titles_with_sources at the same index
            # Find the index in normalized_titles_to_show
            idx = normalized_titles_to_show.index(selected_anime_with_source)
            # Get corresponding title from original titles_with_sources
            full_selected_title = titles_with_sources[idx]
            # Extract anime name (without sources)
            selected_anime = full_selected_title.split(" [")[0]

            # Extract source (if present)
            source = None
            if " [" in full_selected_title and full_selected_title.endswith("]"):
                source = full_selected_title.split(" [")[1].rstrip("]")

            break  # Exit while loop

    # Save the choice for next time (with original search title for "Trocar fonte")
    if anilist_id:
        # Get anime URLs from repository IMMEDIATELY after user selects
        anime_url = None
        anime_urls = {}  # source -> URL mapping for all available sources

        # Try exact match first
        repo_title = selected_anime
        if selected_anime not in rep.anime_to_urls:
            # If no exact match, find best fuzzy match
            from fuzzywuzzy import fuzz

            repo_titles = list(rep.anime_to_urls.keys())
            if repo_titles:
                best_match = max(
                    repo_titles,
                    key=lambda t: fuzz.token_sort_ratio(selected_anime.lower(), t.lower()),
                )
                if fuzz.token_sort_ratio(selected_anime.lower(), best_match.lower()) >= 50:
                    repo_title = best_match

        # Get URLs from repository - collect ALL available sources
        if repo_title in rep.anime_to_urls:
            for url, src, _params in rep.anime_to_urls[repo_title]:
                # Store URL for this source
                anime_urls[src] = url
                # Keep first URL as primary (for backwards compatibility)
                if anime_url is None and (source is None or src in source.split(",")):
                    anime_url = url

        save_anilist_mapping(
            anilist_id,
            selected_anime,
            search_title=anime_title,
            source=source,
            anime_url=anime_url,
            anime_urls=anime_urls,
        )

    # Get episodes (skip if already loaded from "Continuar com este")
    if not episodes_already_loaded:
        cache_data = get_cache(selected_anime)
    else:
        cache_data = None

    if cache_data:
        # Use cached data for episode list
        episode_list = cache_data.episode_urls
        scraper_episode_count = cache_data.episode_count
        logger.info(f"ℹ️  Usando cache ({scraper_episode_count} eps disponíveis)")

        # Still need to populate repository for video URL search
        # (cache only stores episode titles, not the URLs needed for playback)
        rep.search_episodes(selected_anime)
    else:
        # If we have saved URLs from "Continuar com este", add them to repository first
        if selected_anime == saved_title:
            # Load all saved URLs (source -> URL mapping)
            saved_urls = load_anilist_urls(anilist_id) if anilist_id else {}

            if saved_urls:
                # Add all saved URLs to repository
                sources_list = ", ".join(sorted(saved_urls.keys()))
                logger.info(f"📺 Carregando '{selected_anime}' da fonte {sources_list}...")
                for src, url in saved_urls.items():
                    rep.add_anime(selected_anime, url, src)
            elif saved_url and saved_source:
                # Fallback for old format with single URL
                logger.info(f"📺 Carregando '{selected_anime}' da fonte {saved_source}...")
                rep.add_anime(selected_anime, saved_url, saved_source)

        # Fetch from scrapers
        with loading("Carregando episódios..."):
            rep.search_episodes(selected_anime)
        episode_list = rep.get_episode_list(selected_anime)
        scraper_episode_count = len(episode_list)

        if not episode_list:
            logger.info(
                "\n❌ Nenhum episódio carregado — todos os scrapers falharam (timeout ou erro de rede)."
            )
            logger.info("   Tente novamente em alguns instantes.")
            input("\nPressione Enter para voltar...")
            return

        # Save to cache
        set_cache(selected_anime, scraper_episode_count, episode_list)

    # Check local history for this anime (use max of AniList and local)
    local_progress = 0
    try:
        history_file = HISTORY_PATH / "history.json"
        with history_file.open() as f:
            history_data = json.load(f)
            if selected_anime in history_data:
                # history stores episode_idx (0-based), progress is 1-based
                local_progress = history_data[selected_anime][1] + 1
    except (FileNotFoundError, KeyError, IndexError):
        pass  # No local history

    # Use maximum of AniList and local progress (never go backwards)
    max_progress = max(anilist_progress, local_progress)

    # If user has progress (from AniList or local), offer to continue from there
    if max_progress > 0 and max_progress <= len(episode_list):
        # Offer -1/0/+1 options (previous, current, next)
        # Using max_progress to never go backwards
        options = []
        option_to_idx = {}

        # Show source of progress
        progress_source = ""
        if max_progress == anilist_progress and max_progress == local_progress:
            progress_source = "AniList + Local"
        elif max_progress == anilist_progress:
            progress_source = "AniList"
        elif max_progress == local_progress:
            progress_source = "Local"

        # Next episode (+1) - SHOW FIRST
        next_ep = None
        if max_progress < len(episode_list):
            # Next episode exists in the list (available in scrapers)
            next_ep = f"⏭️  Episódio {max_progress + 1} (próximo)"
            options.append(next_ep)
            option_to_idx[next_ep] = max_progress
        elif total_episodes and max_progress < total_episodes:
            # Next episode exists according to AniList but not in scrapers yet
            next_ep = f"⏭️  Episódio {max_progress + 1} (aguardando)"
            options.append(next_ep)
            option_to_idx[next_ep] = None  # Mark as unavailable

        # Current episode (max progress)
        current_ep = f"▶️  Episódio {max_progress} ({progress_source})"
        options.append(current_ep)
        option_to_idx[current_ep] = max_progress - 1

        # Previous episode (-1)
        if max_progress > 1:
            prev_ep = f"◀️  Episódio {max_progress - 1} (anterior)"
            options.append(prev_ep)
            option_to_idx[prev_ep] = max_progress - 2
        # If neither condition is true, anime is complete (don't show next episode)

        # Add option to choose any episode
        options.append("📋 Escolher outro episódio")
        options.append("🔄 Começar do zero")

        # Build menu message with episode availability info
        menu_msg = f"{selected_anime} - De onde quer continuar?"
        if total_episodes and scraper_episode_count:
            menu_msg += f"\n📊 {scraper_episode_count} eps disponíveis / {total_episodes} total"
        elif scraper_episode_count:
            menu_msg += f"\n📊 {scraper_episode_count} eps disponíveis"

        choice = menu_navigate(options, msg=menu_msg)

        if not choice:
            return  # User cancelled

        if choice == "📋 Escolher outro episódio":
            # Don't fetch skip times upfront - load them on-demand when playing
            # This avoids loading skip times for all episodes when user only plays 1-2

            formatted_episode_list = list(episode_list)

            # Let user choose from full episode list
            selected_episode = menu_navigate(formatted_episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                return
            episode_idx = formatted_episode_list.index(selected_episode)
        elif choice == "🔄 Começar do zero":
            # Confirm before resetting
            confirm_reset = menu_navigate(
                ["✅ Sim, resetar", "❌ Cancelar"],
                msg="Tem certeza que quer começar do zero? Seu progresso será perdido.",
            )
            if confirm_reset == "✅ Sim, resetar":
                reset_history(selected_anime)
                episode_idx = 0
                logger.info("✅ Histórico resetado! Começando do episódio 1...")
            else:
                return  # User cancelled
        else:
            episode_idx = option_to_idx[choice]
            # Check if episode is unavailable (marked as None)
            if episode_idx is None:
                # Try incremental search on AnimesDigital homepage for awaiting episodes
                logger.info(f"🔍 Buscando episódio {max_progress + 1} no AnimesDigital...")

                from scrapers.plugins.animesdigital import AnimesDigital

                scraper = AnimesDigital()

                try:
                    with loading("Procurando novo episódio..."):
                        # Try incremental search on homepage
                        results = scraper.search_homepage_incremental(selected_anime)

                    if results:
                        # Filter to the episode we want (max_progress + 1)
                        target_ep_num = max_progress + 1
                        matching_episodes = [
                            ep for ep in results if ep["episode_number"] == target_ep_num
                        ]

                        if matching_episodes:
                            # Found the episode! Use it
                            episode = matching_episodes[0]
                            logger.info(f"✅ Episódio {target_ep_num} encontrado no AnimesDigital!")
                            logger.info(f"   URL: {episode['episode_url'][:80]}...")

                            # Set episode_idx to the target episode (use a special marker to indicate it's from homepage)
                            # We'll handle this in the playback flow
                            episode_idx = target_ep_num - 1  # Convert to 0-indexed

                            # Store the direct episode URL for use in playback
                            # We'll pass this through the playback context
                            if not hasattr(anilist_anime_flow, "_awaiting_episode_urls"):
                                anilist_anime_flow._awaiting_episode_urls = {}
                            anilist_anime_flow._awaiting_episode_urls[selected_anime] = {
                                target_ep_num: episode["episode_url"]
                            }
                        else:
                            # Episode not found in homepage results
                            logger.info(
                                f"\n❌ Episódio {target_ep_num} não encontrado no AnimesDigital."
                            )
                            input("\nPressione Enter para voltar...")
                            return
                    else:
                        # No results from incremental search
                        logger.info(
                            f"\n❌ Episódio {max_progress + 1} ainda não disponível nos scrapers ou no AnimesDigital."
                        )
                        input("\nPressione Enter para voltar...")
                        return

                except Exception as e:
                    # Fallback if search fails
                    logger.info(f"⚠️  Erro ao buscar no AnimesDigital: {e}")
                    logger.info(f"Episódio {max_progress + 1} ainda não disponível nos scrapers.")
                    input("\nPressione Enter para voltar...")
                    return
    else:
        # No progress or progress out of bounds - show full episode list
        selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")

        if not selected_episode:
            return  # User cancelled, go back

        episode_idx = episode_list.index(selected_episode)

    # At this point, episode_idx is guaranteed to be int, not None
    if not isinstance(episode_idx, int):
        raise ValueError(f"episode_idx should be int, got {type(episode_idx)}")

    current_episode_idx: int = episode_idx
    num_episodes = len(episode_list)

    # Loop to allow going back to episode selection
    while True:
        # Ask what user wants to do with the episode
        episode_number = current_episode_idx + 1
        action_options = [
            "▶️ Assistir agora",
            "📥 Baixar para assistir depois",
            "🔙 Voltar",
        ]
        action = menu_navigate(
            action_options, msg=f"O que deseja fazer com o episódio {episode_number}?"
        )

        if action == "🔙 Voltar":
            # Go back to episode selection menu
            # Fetch skip times for ALL episodes if not already fetched
            # Don't fetch skip times upfront - load them on-demand when playing
            # This avoids loading skip times for all episodes when user only plays 1-2

            formatted_episode_list = list(episode_list)

            # Let user choose from full episode list
            selected_episode = menu_navigate(formatted_episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                return  # User cancelled, exit completely
            current_episode_idx = formatted_episode_list.index(selected_episode)
            continue  # Loop back to action menu with new episode

        if action == "📥 Baixar para assistir depois":
            # Download episodes starting from current
            from services.anime.download_service import AnimeDownloadService
            from utils.episode_range_parser import parse_episode_range, RangeParseError

            logger.info(f"📥 Baixar episódios: {selected_anime}")
            logger.info(f"   Total de episódios: {num_episodes}")

            # Calculate default range (from current episode to end)
            default_range = f"{episode_number}-"
            logger.info(f"   Padrão: {default_range} (do episódio {episode_number} até o fim)\n")

            # Prompt for range
            try:
                range_input = input("Qual intervalo? (pressione Enter para padrão): ").strip()

                if not range_input:
                    range_input = default_range
                    logger.info(f"   Usando: {range_input}")

                # Parse range
                episodes = parse_episode_range(range_input, num_episodes)
            except RangeParseError as e:
                logger.info(f"❌ {e}")
                return

            # Download episodes
            service = AnimeDownloadService()

            def get_episode_url_for_download(episode_num: int):
                """Get episode URL for download."""
                player_url = rep.search_player(selected_anime, episode_num)
                if player_url:
                    return (player_url, source or "unknown")
                return None

            logger.info(f"⏳ Baixando {len(episodes)} episódio(s)...")
            try:
                with loading(f"Baixando {len(episodes)} episódio(s)..."):
                    result = service.download_episodes(
                        anime_title=selected_anime,
                        range_input=range_input,
                        total_episodes=num_episodes,
                        get_episode_url=get_episode_url_for_download,
                    )

                # Show result
                logger.info(f"{result.summary}")

                if result.successful > 0:
                    logger.info(f"✅ {result.successful} episódio(s) baixado(s) com sucesso!")
                    logger.info(f"   Localização: {service.download_dir / selected_anime}")
            except Exception as e:
                logger.info(f"❌ Erro ao baixar: {e}")
            return
        elif action == "▶️ Assistir agora":
            # Break out of loop and proceed to playback
            break
        else:
            # User cancelled
            return

    # Playback loop (with AniList sync)
    while True:
        episode = current_episode_idx + 1

        # Get all available sources for this episode (sorted by priority)
        all_sources = rep.get_all_episode_sources(selected_anime, episode)

        # Check if video sources are available
        if not all_sources:
            logger.info("❌ Nenhuma fonte conseguiu extrair o vídeo.")
            logger.info("   💡 O episódio está indisponível em todas as fontes.")
            continue

        # Show episode progress
        progress_str = _format_episode_progress(episode, num_episodes, total_episodes)
        logger.info(f"▶️  Iniciando reprodução do episódio {progress_str}...")

        # Show which sources will be tried (in priority order)
        source_names = [s for _, s in all_sources]
        if len(source_names) > 1:
            logger.info(f"   🔄 Tentando fontes: {', '.join(source_names)}")
        else:
            logger.info(f"   Fonte: {source_names[0]}")

        # Extract actual video URLs from episode pages before playback
        # all_sources contains (page_url, source_name) pairs
        video_sources = []
        for page_url, source_name in all_sources:
            try:
                # Call search_player_src to extract the real video URL
                video_url = rep.search_player_from_page(page_url, source_name)
                if video_url:
                    video_sources.append((video_url, source_name, page_url))
                else:
                    logger.info(
                        f"   ⚠️  [{source_name}] Não retornou URL de vídeo (page_url={page_url[:80]})"
                    )
            except Exception as e:
                # If extraction fails, skip this source
                logger.info(f"   ❌ [{source_name}] Erro ao extrair vídeo: {e}")
                continue

        # Use extracted video URLs for playback (fallback to page URLs if no videos found)
        sources_for_playback = video_sources if video_sources else all_sources

        # Use fallback-aware playback
        player = VideoPlayer()
        fallback_result = play_episode_with_fallback(
            player=player,
            sources=sources_for_playback,
            anime_title=selected_anime,
            episode_number=episode,
            total_episodes=num_episodes,
            use_ipc=True,
            debug=args.debug,
            anilist_id=anilist_id,
            anilist_episodes=total_episodes,
        )

        result = fallback_result.playback_result
        source_used = fallback_result.source_used or "unknown"

        logger.info("📊 Reprodução encerrada:")
        logger.info(f"   Exit code: {result.exit_code}")
        logger.info(f"   Ação: {result.action}")
        if fallback_result.sources_tried:
            logger.info(f"   Fonte usada: {source_used}")

        error_hint = result.data.get("error_hint") if isinstance(result.data, dict) else None
        if result.exit_code not in [0, 3] and error_hint:
            logger.info(f"   ❌ {error_hint}")

        # Handle IPC navigation actions
        if result.action == "next":
            # User pressed Shift+N - already saved history and synced AniList in IPC handler
            # Move to next episode automatically
            if result.data and "episode" in result.data:
                next_episode = result.data["episode"]
                if next_episode <= num_episodes:
                    episode_idx = next_episode - 1
                    current_episode_idx = next_episode - 1  # CRITICAL: sync both variables
                    # Check for sequels when last episode is watched
                    if next_episode == num_episodes:
                        # Get AniList episode count to check if series is truly complete
                        anilist_episodes = None
                        if anilist_id:
                            anime_info = anilist_client.get_anime_by_id(anilist_id)
                            if anime_info:
                                anilist_episodes = anime_info.episodes

                        if offer_sequel_and_continue(
                            anilist_id,
                            args,
                            current_episode=next_episode,
                            anilist_episodes=anilist_episodes,
                        ):
                            return  # Sequel started, exit this flow
                    continue  # Loop to play next episode
            # Fall through to menu if no next episode data
        elif result.action == "quit":
            # User quit (may have used Shift+N/P to load different episode before quitting)
            # Sync episode_idx with the final episode number from IPC context
            if result.data and "episode" in result.data:
                final_episode = result.data["episode"]
                if final_episode >= 1 and final_episode <= num_episodes:
                    episode_idx = final_episode - 1
                    current_episode_idx = final_episode - 1  # CRITICAL: sync both variables
                    episode = final_episode
        elif result.action == "auto-next":
            # Auto-play active and user pressed 'q' - already marked as watched in IPC handler
            # Sync with AniList and move to next episode
            current_episode = result.data.get("episode", episode) if result.data else episode

            # Update AniList if authenticated
            if anilist_client.is_authenticated() and anilist_id:
                # Check if anime is in any list
                if not anilist_client.is_in_any_list(anilist_id):
                    logger.info("📝 Adicionando à sua lista do AniList...")
                    anilist_client.add_to_list(anilist_id, Status.CURRENT)
                else:
                    # Auto-promote from PLANNING to CURRENT, or CURRENT to COMPLETED
                    entry = anilist_client.get_media_list_entry(anilist_id)
                    if entry:
                        if entry.status == "PLANNING":
                            logger.info("📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                            anilist_client.add_to_list(anilist_id, Status.CURRENT)
                        elif entry.status == "CURRENT":
                            # If finishing last episode of a watched anime, mark as completed
                            if current_episode == num_episodes:
                                logger.info("✅ Marcando como 'Completo'...")
                                anilist_client.change_status(anilist_id, Status.COMPLETED)
                        # If already COMPLETED, leave it as is (don't change to REPEATING)
                        # User can manually change status to REPEATING if they want to track rewatches

                logger.info(f"🔄 Sincronizando progresso com AniList (Ep {current_episode})...")
                success = anilist_client.update_progress(anilist_id, current_episode)
                if success:
                    logger.info("✅ Progresso salvo no AniList!")
                else:
                    # Verify token is still valid if sync failed
                    viewer = anilist_client.get_viewer_info()
                    if not viewer:
                        logger.info("⚠️  Token do AniList expirou")
                        logger.info("   Execute: ani-tupi anilist auth")
                    else:
                        logger.info("⚠️  Não foi possível salvar no AniList (continuando...)")

            # Check if there's a next episode
            # Use current_episode (from IPC context) instead of episode_idx
            # because episode_idx may be stale if Shift+N/P was used to load episodes
            # current_episode is 1-indexed, so convert to 0-indexed for episode_idx
            episode_idx = current_episode - 1  # Convert 1-indexed to 0-indexed
            current_episode_idx = current_episode - 1  # CRITICAL: sync both variables
            next_episode_idx = episode_idx + 1
            if next_episode_idx < num_episodes:
                # Move to next episode
                episode_idx = next_episode_idx
                current_episode_idx = next_episode_idx  # CRITICAL: sync both variables
                logger.info(f"▶️  Carregando próximo episódio: {episode_idx + 1}")
                continue  # Loop to play next episode
            else:
                # Last episode - check for sequels
                logger.info("✅ Último episódio assistido!")
                # Get AniList episode count to check if series is truly complete
                anilist_episodes = None
                if anilist_id:
                    anime_info = anilist_client.get_anime_by_id(anilist_id)
                    if anime_info:
                        anilist_episodes = anime_info.episodes

                if anilist_id and offer_sequel_and_continue(
                    anilist_id,
                    args,
                    current_episode=current_episode,
                    anilist_episodes=anilist_episodes,
                ):
                    return  # Sequel started, exit this flow
                # No sequel or user declined - return to menu
                return
        elif result.action == "previous":
            # User pressed Shift+P - go to previous episode
            if result.data and "episode" in result.data:
                prev_episode = result.data["episode"]
                if prev_episode >= 1:
                    episode_idx = prev_episode - 1
                    current_episode_idx = prev_episode - 1  # CRITICAL: sync both variables
                    continue  # Loop to play previous episode
            # Fall through to menu if no previous episode data
        elif result.action == "reload":
            # User pressed Shift+R - reload current episode
            continue  # Loop to replay same episode
        elif result.action == "mark-menu":
            # User pressed Shift+M - mark watched and show menu
            # History already saved in IPC handler, just show menu
            pass
        elif result.exit_code not in [0, 3]:  # Error cases
            logger.info(f"⚠️  MPV exit code: {result.exit_code}")
            if result.exit_code == 2:
                logger.info(" (Possível erro ao reproduzir ou janela fechada)")

        # For normal quit or other actions, show confirmation menu
        # (History/AniList sync already handled by IPC if action was "next")
        if result.action != "next":
            # Only clear terminal if playback was successful (exit_code == 0)
            # If there was an error, keep messages visible for 2 seconds

            if result.exit_code != 0:
                # Error occurred - give user time to see error messages
                logger.info("⏳ Pressione Enter para continuar...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass

                # Never ask "watched until end" on playback errors.
                # This avoids accidental history/AniList corruption by misclick.
                pass

            # Ask if watched until the end before saving/updating anything
            confirm_options = ["✅ Sim, assisti até o final", "❌ Não, parei antes."]
            confirm = menu_navigate(
                confirm_options,
                msg=f"Você assistiu o episódio {episode} de '{selected_anime}' até o final?",
            )

            # Only save history and update AniList if user confirmed
            if confirm == "✅ Sim, assisti até o final":
                save_history(selected_anime, episode_idx, anilist_id, source)

                # Update AniList if authenticated
                if anilist_client.is_authenticated() and anilist_id:
                    # Check if anime is in any list
                    if not anilist_client.is_in_any_list(anilist_id):
                        logger.info("📝 Adicionando à sua lista do AniList...")
                        anilist_client.add_to_list(anilist_id, "CURRENT")
                    else:
                        # Auto-promote from PLANNING to CURRENT, or CURRENT to COMPLETED
                        entry = anilist_client.get_media_list_entry(anilist_id)
                        if entry:
                            if entry.status == "PLANNING":
                                logger.info(
                                    "\n📝 Movendo de 'Planejo Assistir' para 'Assistindo'..."
                                )
                                anilist_client.add_to_list(anilist_id, "CURRENT")
                            elif entry.status == "CURRENT":
                                # If finishing last episode of a watched anime, mark as completed
                                if episode == num_episodes:
                                    logger.info("✅ Marcando como 'Completo'...")
                                    anilist_client.change_status(anilist_id, Status.COMPLETED)
                            # If already COMPLETED, leave it as is (don't change to REPEATING)
                            # User can manually change status to REPEATING if they want to track rewatches

                    logger.info(f"🔄 Sincronizando progresso com AniList (Ep {episode})...")
                    success = anilist_client.update_progress(anilist_id, episode)
                    if success:
                        logger.info("✅ Progresso salvo no AniList!")
                    else:
                        # Verify token is still valid if sync failed
                        viewer = anilist_client.get_viewer_info()
                        if not viewer:
                            logger.info("⚠️  Token do AniList expirou")
                            logger.info("   Execute: ani-tupi anilist auth")
                        else:
                            logger.info("⚠️  Não foi possível salvar no AniList (continuando...)")

                    # Check for sequels when last episode is watched
                    if episode == num_episodes:
                        # Get AniList episode count to check if series is truly complete
                        anilist_episodes = None
                        if anilist_id:
                            anime_info = anilist_client.get_anime_by_id(anilist_id)
                            if anime_info:
                                anilist_episodes = anime_info.episodes

                        if offer_sequel_and_continue(
                            anilist_id,
                            args,
                            current_episode=episode,
                            anilist_episodes=anilist_episodes,
                        ):
                            return  # Sequel started, exit this flow
            else:
                # User didn't finish - don't save anything, just continue to menu
                pass

        selected_opt = menu_navigate(
            build_anilist_post_playback_options(current_episode_idx, num_episodes),
            msg="O que quer fazer agora?",
        )

        if not selected_opt or selected_opt in {"🔙 Voltar", "↩️  Voltar ao menu anterior"}:
            return  # Exit to previous menu
        if selected_opt == "▶️  Próximo":
            current_episode_idx += 1
            episode_idx = current_episode_idx  # CRITICAL: sync both variables
        elif selected_opt == "◀️  Anterior":
            current_episode_idx -= 1
            episode_idx = current_episode_idx  # CRITICAL: sync both variables
        elif selected_opt == "🔁 Replay":
            # Keep same episode_idx, loop continues to replay
            pass
        elif selected_opt == "📋 Escolher outro episódio":
            episode_list = rep.get_episode_list(selected_anime)
            selected_episode = menu_navigate(episode_list, msg="Escolha o episódio.")
            if not selected_episode:
                return  # User cancelled, go back
            episode_idx = episode_list.index(selected_episode)  # CRITICAL: sync both variables
            current_episode_idx = episode_list.index(selected_episode)
        elif selected_opt == "🔄 Trocar fonte":
            new_anime, new_episode_idx = switch_anime_source(
                selected_anime, args, anilist_id, display_title
            )
            if new_anime:
                selected_anime = new_anime
                episode_idx = new_episode_idx
                current_episode_idx = new_episode_idx  # CRITICAL: sync both variables
                num_episodes = len(rep.get_episode_list(selected_anime))
                # Continue loop with new anime/episode
