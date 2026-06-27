"""AniList integration flows for anime playback.

Handles AniList-specific anime flows including search, selection, progress tracking,
sequel detection, and synchronization with AniList API.
"""

import json
from collections.abc import Callable
from typing import Any

from models.config import get_data_path
from services.anilist_service import anilist_client
from services.repository import rep
from ui.components import loading, menu_navigate, menu_navigate_episodes
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


def resolve_preferred_title(
    anilist_id: int | None,
    english_title: str | None,
    romaji_title: str | None,
    current_title: str,
) -> str | None:
    """Resolve which title to use for searching based on user preference.

    Checks cached language preference, or prompts user to choose.
    If titles are the same when normalized, uses romaji by default.

    Args:
        anilist_id: AniList ID for preference caching
        english_title: English title from AniList
        romaji_title: Romaji title from AniList
        current_title: Current title (fallback if no preference resolution needed)

    Returns:
        Resolved title string, or None if user cancelled.
    """
    if not english_title or not romaji_title:
        return current_title

    normalized_english = normalize_title_for_dedup(english_title)
    normalized_romaji = normalize_title_for_dedup(romaji_title)

    if normalized_english == normalized_romaji:
        return romaji_title

    # Titles are different - check cache or ask user
    cached_language = load_language_preference(anilist_id) if anilist_id else None

    if cached_language:
        return english_title if cached_language == "english" else romaji_title

    language_options = [
        f"🇯🇵 Romanji: {romaji_title}",
        f"🇬🇧 Inglês: {english_title}",
    ]
    language_choice = menu_navigate(language_options, msg="Escolha o idioma para buscar:")

    if not language_choice:
        return None  # User cancelled

    if language_choice.startswith("🇬🇧"):
        if anilist_id:
            save_language_preference(anilist_id, "english")
        return english_title
    else:
        if anilist_id:
            save_language_preference(anilist_id, "romaji")
        return romaji_title


def load_episodes_from_cache_or_search(
    query: str,
    anilist_id: int | None,
    english_title: str | None,
    romaji_title: str | None,
) -> tuple[Any, list[str]]:
    """Cache-first search: try cache first, fall back to incremental search.

    Args:
        query: Search query (the anime title to search for)
        anilist_id: AniList ID for repository caching
        english_title: English title for search ranking
        romaji_title: Romaji title for search ranking

    Returns:
        Tuple of (search_state, titles_with_sources).
        search_state is None on cache hit.
    """
    cache_data = get_cache(query)

    if cache_data:
        logger.info(f"ℹ️  Usando cache ({cache_data.episode_count} eps disponíveis)")
        rep.load_from_cache(query, cache_data)
        rep.search_anime(query, verbose=False)
        titles_with_sources = rep.get_anime_titles_with_sources()
        if not titles_with_sources:
            titles_with_sources = [query]
        return None, titles_with_sources

    # Not in cache: use incremental search
    search_state, titles_with_sources = incremental_search_anime(
        query,
        english_title=english_title,
        romaji_title=romaji_title,
    )

    if titles_with_sources and romaji_title:
        titles_with_sources = _rank_anime_results_by_reference(titles_with_sources, romaji_title)

    return search_state, titles_with_sources


def select_anime_from_results(
    titles_with_sources: list[str],
    search_state: Any,
    query: str,
    display_title: str,
    english_title: str | None,
    romaji_title: str | None,
    anilist_id: int | None,
) -> tuple[str | None, str | None, str | None]:
    """Show anime selection menu and return user's choice.

    Handles navigation between result sets (incremental search), language toggle,
    and anime selection. Loops until the user picks an anime or cancels.

    Args:
        titles_with_sources: List of titles with source annotations
        search_state: Incremental search state (None for cache hits)
        query: Search query used
        display_title: Display title for menu header
        english_title: English title for language toggle
        romaji_title: Romaji title for language toggle
        anilist_id: AniList ID for repository updates on language toggle

    Returns:
        Tuple of (selected_anime, source, used_query).
        All None if user cancelled.
    """
    used_query = None
    if search_state:
        current_result_set = search_state.get_current()
        if current_result_set:
            used_query = current_result_set.query

    selected_anime = None
    source = None

    while selected_anime is None:
        menu_title = f"📺 Anime do AniList: '{display_title}'\n"

        if search_state:
            current_result_set = search_state.get_current()
            if current_result_set:
                display_query = current_result_set.used_query or current_result_set.query
                menu_title += f"🔍 Busca usada: '{display_query}'\n"
                menu_title += f"   ({current_result_set.word_count} palavras: {len(current_result_set.results)} resultados)\n"
        else:
            display_query = used_query or query
            menu_title += f"🔍 Busca usada: '{display_query}'\n"

        menu_title += f"\nEncontrados {len(titles_with_sources)} resultados. Escolha:"

        # Build normalized title mapping
        normalized_to_original = {}
        normalized_titles_to_show = []
        for title_with_sources in titles_with_sources:
            if " [" in title_with_sources:
                anime_name, sources_part = title_with_sources.split(" [", 1)
                sources_part = "[" + sources_part
            else:
                anime_name = title_with_sources
                sources_part = ""

            normalized_name = normalize_title_for_dedup(anime_name)
            normalized_full = f"{normalized_name} {sources_part}".rstrip()

            normalized_to_original[normalized_name] = anime_name
            normalized_titles_to_show.append(normalized_full)

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

        selected_anime_with_source = menu_navigate(
            normalized_titles_to_show,
            msg=menu_title,
            search_state=search_state,
            alternative_language_available=can_toggle_language,
            alternative_language_label=alt_label,
        )

        if not selected_anime_with_source:
            return None, None, None  # User cancelled

        if selected_anime_with_source == "__research_language__":
            assert search_state is not None
            new_lang = search_state.toggle_language()
            new_title = english_title if new_lang == "english" else romaji_title

            rep.clear_search_results()
            if anilist_id:
                rep.anime_to_anilist_id[new_title] = anilist_id

            search_state, titles_with_sources = incremental_search_anime(
                new_title,
                english_title=english_title,
                romaji_title=romaji_title,
            )

            if search_state:
                current_result_set = search_state.get_current()
                if current_result_set:
                    used_query = current_result_set.query

            continue

        if selected_anime_with_source == "__nav_previous__":
            assert search_state is not None
            search_state.go_back()
            new_result_set = search_state.get_current()
            assert new_result_set is not None
            titles_with_sources = new_result_set.results
            continue

        elif selected_anime_with_source == "__nav_next__":
            assert search_state is not None
            search_state.go_forward()
            new_result_set = search_state.get_current()
            assert new_result_set is not None
            titles_with_sources = new_result_set.results
            continue

        else:
            idx = normalized_titles_to_show.index(selected_anime_with_source)
            full_selected_title = titles_with_sources[idx]
            selected_anime = full_selected_title.split(" [")[0]

            source = None
            if " [" in full_selected_title and full_selected_title.endswith("]"):
                source = full_selected_title.split(" [")[1].rstrip("]")

            break

    return selected_anime, source, used_query


def _sync_anilist_progress(
    anilist_id: int,
    episode: int,
    num_episodes: int,
    status_obj: Status | None = None,
) -> None:
    """Sync watched episode progress to AniList and update status if needed.

    Handles PLANNING → CURRENT promotion, CURRENT → COMPLETED on last episode.
    Logs warnings on failure without raising.

    Args:
        anilist_id: AniList media ID
        episode: Episode number just watched (1-indexed)
        num_episodes: Total episodes available (from scrapers)
        status_obj: Pre-fetched Status value to pass when already known (unused internally)
    """
    if not anilist_client.is_authenticated() or not anilist_id:
        return

    if not anilist_client.is_in_any_list(anilist_id):
        logger.info("📝 Adicionando à sua lista do AniList...")
        anilist_client.add_to_list(anilist_id, Status.CURRENT)
    else:
        entry = anilist_client.get_media_list_entry(anilist_id)
        if entry:
            if entry.status == "PLANNING":
                logger.info("📝 Movendo de 'Planejo Assistir' para 'Assistindo'...")
                anilist_client.add_to_list(anilist_id, Status.CURRENT)
            elif entry.status == "CURRENT" and episode == num_episodes:
                logger.info("✅ Marcando como 'Completo'...")
                anilist_client.change_status(anilist_id, Status.COMPLETED)

    logger.info(f"🔄 Sincronizando progresso com AniList (Ep {episode})...")
    success = anilist_client.update_progress(anilist_id, episode)
    if success:
        logger.info("✅ Progresso salvo no AniList!")
    else:
        viewer = anilist_client.get_viewer_info()
        if not viewer:
            logger.info("⚠️  Token do AniList expirou")
            logger.info("   Execute: ani-tupi anilist auth")
        else:
            logger.info("⚠️  Não foi possível salvar no AniList (continuando...)")


def offer_sequel_and_continue(
    anilist_id: int,
    args,
    current_episode: int | None = None,
    anilist_episodes: int | None = None,
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
    query_getter: Callable[[], str] = input,
) -> None:
    """Flow for anime selected from AniList.

    Searches scrapers for the anime and starts normal playback flow.

    Args:
        anime_title: Title to search for (romaji or english)
        anilist_id: AniList ID for syncing
        args: Command line arguments
        anilist_progress: Current episode progress from AniList (0 if not watching)
        display_title: Full bilingual title for display (romaji / english)
        total_episodes: Total number of episodes from AniList (None if unknown)
        query_getter: Callable to get manual search query from user (default: input)
    """
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
    rep.clear_search_results()

    if anilist_id:
        rep.anime_to_anilist_id[anime_title] = anilist_id

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
        display_title_with_source = saved_title
        if saved_source:
            display_title_with_source = f"{saved_title} [{saved_source}]"

        choice = menu_navigate(
            ["✅ Continuar com este", "🔄 Escolher outro"],
            msg=f"Você usou '{display_title_with_source}' antes.\nQuer continuar?",
        )

        if not choice:
            return

        if choice == "✅ Continuar com este":
            selected_anime = saved_title
            source = saved_source
            logger.info(f"✅ Usando: {selected_anime}")

    # Resolve title language preference (only if user didn't pick saved title)
    if selected_anime is None and english_title and romaji_title:
        resolved = resolve_preferred_title(anilist_id, english_title, romaji_title, anime_title)
        if resolved is None:
            return  # User cancelled
        anime_title = resolved

    # Prepare search state variables
    search_state = None
    titles_with_sources = None
    used_query = None
    if selected_anime is None:
        source = None

    if selected_anime is None:
        search_state, titles_with_sources = load_episodes_from_cache_or_search(
            anime_title, anilist_id, english_title, romaji_title
        )
        if search_state:
            current_result_set = search_state.get_current()
            if current_result_set:
                used_query = current_result_set.query
        else:
            used_query = anime_title

    if selected_anime is None and not titles_with_sources:
        # Offer manual search (only if we haven't found anything)
        choice = menu_navigate(
            ["🔍 Buscar manualmente", "🔙 Voltar ao AniList"], msg="O que deseja fazer?"
        )

        if not choice:
            return

        if choice == "🔍 Buscar manualmente":
            manual_query = query_getter("\n🔍 Digite o nome para buscar: ")

            search_state, titles_with_sources = load_episodes_from_cache_or_search(
                manual_query, anilist_id, english_title, romaji_title
            )
            if search_state:
                current_result_set = search_state.get_current()
                if current_result_set:
                    used_query = current_result_set.query
            else:
                used_query = manual_query

            if not titles_with_sources:
                return
        else:
            return  # Back to AniList menu

    if selected_anime is None:
        selected_anime, source, used_query = select_anime_from_results(
            titles_with_sources,
            search_state,
            used_query or anime_title,
            display_title,
            english_title,
            romaji_title,
            anilist_id,
        )
        if selected_anime is None:
            return  # User cancelled

    # Clear any stale awaiting episode URLs from previous sessions for this anime
    if hasattr(anilist_anime_flow, "_awaiting_episode_urls"):
        anilist_anime_flow._awaiting_episode_urls.pop(selected_anime, None)

    # Save the choice for next time (with original search title for "Trocar fonte")
    if anilist_id:
        anime_url = None
        anime_urls = {}

        repo_title = selected_anime
        if selected_anime not in rep.anime_to_urls:
            from thefuzz import fuzz

            repo_titles = list(rep.anime_to_urls.keys())
            if repo_titles:
                best_match = max(
                    repo_titles,
                    key=lambda t: fuzz.token_sort_ratio(selected_anime.lower(), t.lower()),
                )
                if fuzz.token_sort_ratio(selected_anime.lower(), best_match.lower()) >= 50:
                    repo_title = best_match

        if repo_title in rep.anime_to_urls:
            for url, src, _params in rep.anime_to_urls[repo_title]:
                anime_urls[src] = url
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
        episode_list = cache_data.episode_urls
        scraper_episode_count = cache_data.episode_count
        logger.info(f"ℹ️  Usando cache ({scraper_episode_count} eps disponíveis)")
        rep.search_episodes(selected_anime)
    else:
        if selected_anime == saved_title:
            saved_urls = load_anilist_urls(anilist_id) if anilist_id else {}

            if saved_urls:
                sources_list = ", ".join(sorted(saved_urls.keys()))
                logger.info(f"📺 Carregando '{selected_anime}' da fonte {sources_list}...")
                for src, url in saved_urls.items():
                    rep.add_anime(selected_anime, url, src)
            elif saved_url and saved_source:
                logger.info(f"📺 Carregando '{selected_anime}' da fonte {saved_source}...")
                rep.add_anime(selected_anime, saved_url, saved_source)

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

        set_cache(selected_anime, scraper_episode_count, episode_list)

    # Check local history for this anime (use max of AniList and local)
    local_progress = 0
    try:
        history_file = HISTORY_PATH / "history.json"
        with history_file.open() as f:
            history_data = json.load(f)
            if selected_anime in history_data:
                local_progress = history_data[selected_anime][1] + 1
    except (OSError, KeyError, IndexError):
        pass  # No local history

    max_progress = max(anilist_progress, local_progress)

    if max_progress > 0 and max_progress <= len(episode_list):
        options = []
        option_to_idx = {}

        progress_source = ""
        if max_progress == anilist_progress and max_progress == local_progress:
            progress_source = "AniList + Local"
        elif max_progress == anilist_progress:
            progress_source = "AniList"
        elif max_progress == local_progress:
            progress_source = "Local"

        next_ep = None
        if max_progress < len(episode_list):
            next_ep = f"⏭️  Episódio {max_progress + 1} (próximo)"
            options.append(next_ep)
            option_to_idx[next_ep] = max_progress
        elif total_episodes and max_progress < total_episodes:
            next_ep = f"⏭️  Episódio {max_progress + 1} (aguardando)"
            options.append(next_ep)
            option_to_idx[next_ep] = None

        current_ep = f"▶️  Episódio {max_progress} ({progress_source})"
        options.append(current_ep)
        option_to_idx[current_ep] = max_progress - 1

        if max_progress > 1:
            prev_ep = f"◀️  Episódio {max_progress - 1} (anterior)"
            options.append(prev_ep)
            option_to_idx[prev_ep] = max_progress - 2

        options.append("📋 Escolher outro episódio")
        options.append("🔄 Começar do zero")

        menu_msg = f"{selected_anime} - De onde quer continuar?"
        if total_episodes and scraper_episode_count:
            menu_msg += f"\n📊 {scraper_episode_count} eps disponíveis / {total_episodes} total"
        elif scraper_episode_count:
            menu_msg += f"\n📊 {scraper_episode_count} eps disponíveis"

        choice = menu_navigate(options, msg=menu_msg)

        if not choice:
            return

        if choice == "📋 Escolher outro episódio":
            episode_idx = menu_navigate_episodes(episode_list)
            if episode_idx is None:
                return
        elif choice == "🔄 Começar do zero":
            confirm_reset = menu_navigate(
                ["✅ Sim, resetar", "❌ Cancelar"],
                msg="Tem certeza que quer começar do zero? Seu progresso será perdido.",
            )
            if confirm_reset == "✅ Sim, resetar":
                reset_history(selected_anime)
                episode_idx = 0
                logger.info("✅ Histórico resetado! Começando do episódio 1...")
            else:
                return
        else:
            episode_idx = option_to_idx[choice]
            if episode_idx is None:
                logger.info(f"🔍 Buscando episódio {max_progress + 1} no AnimesDigital...")

                from scrapers.plugins.animesdigital import AnimesDigital

                scraper = AnimesDigital()

                try:
                    with loading("Procurando novo episódio..."):
                        results = scraper.search_homepage_incremental(selected_anime)

                    if results:
                        target_ep_num = max_progress + 1
                        matching_episodes = [
                            ep for ep in results if ep["episode_number"] == target_ep_num
                        ]

                        if matching_episodes:
                            episode = matching_episodes[0]
                            logger.info(f"✅ Episódio {target_ep_num} encontrado no AnimesDigital!")
                            logger.info(f"   URL: {episode['episode_url'][:80]}...")

                            episode_idx = target_ep_num - 1

                            if not hasattr(anilist_anime_flow, "_awaiting_episode_urls"):
                                anilist_anime_flow._awaiting_episode_urls = {}
                            anilist_anime_flow._awaiting_episode_urls[selected_anime] = {
                                target_ep_num: episode["episode_url"]
                            }
                        else:
                            logger.info(
                                f"\n❌ Episódio {target_ep_num} não encontrado no AnimesDigital."
                            )
                            input("\nPressione Enter para voltar...")
                            return
                    else:
                        logger.info(
                            f"\n❌ Episódio {max_progress + 1} ainda não disponível nos scrapers ou no AnimesDigital."
                        )
                        input("\nPressione Enter para voltar...")
                        return

                except (OSError, ConnectionError, TimeoutError) as e:
                    logger.warning(f"⚠️  Erro de rede ao buscar no AnimesDigital: {e!r}")
                    logger.info(f"Episódio {max_progress + 1} ainda não disponível nos scrapers.")
                    input("\nPressione Enter para voltar...")
                    return
                except Exception as e:
                    logger.warning(
                        f"⚠️  Erro inesperado ao buscar no AnimesDigital: {e!r}", exc_info=True
                    )
                    logger.info(f"Episódio {max_progress + 1} ainda não disponível nos scrapers.")
                    input("\nPressione Enter para voltar...")
                    return
    else:
        episode_idx = menu_navigate_episodes(episode_list)

        if episode_idx is None:
            return

    if not isinstance(episode_idx, int):
        raise ValueError(f"episode_idx should be int, got {type(episode_idx)}")

    current_episode_idx: int = episode_idx
    num_episodes = len(episode_list)

    # Loop to allow going back to episode selection
    while True:
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
            new_idx = menu_navigate_episodes(episode_list)
            if new_idx is None:
                return
            current_episode_idx = new_idx
            continue

        if action == "📥 Baixar para assistir depois":
            from services.anime.download_service import AnimeDownloadService
            from utils.episode_range_parser import parse_episode_range, RangeParseError

            logger.info(f"📥 Baixar episódios: {selected_anime}")
            logger.info(f"   Total de episódios: {num_episodes}")

            default_range = f"{episode_number}-"
            logger.info(f"   Padrão: {default_range} (do episódio {episode_number} até o fim)\n")

            try:
                range_input = input("Qual intervalo? (pressione Enter para padrão): ").strip()

                if not range_input:
                    range_input = default_range
                    logger.info(f"   Usando: {range_input}")

                episodes = parse_episode_range(range_input, num_episodes)
            except RangeParseError as e:
                logger.info(f"❌ {e}")
                return

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

                logger.info(f"{result.summary}")

                if result.successful > 0:
                    logger.info(f"✅ {result.successful} episódio(s) baixado(s) com sucesso!")
                    logger.info(f"   Localização: {service.download_dir / selected_anime}")
            except Exception as e:
                logger.warning(f"❌ Erro ao baixar: {e!r}", exc_info=True)
            return
        elif action == "▶️ Assistir agora":
            break
        else:
            return

    # Playback loop (with AniList sync)
    while True:
        episode = current_episode_idx + 1

        all_sources = rep.get_all_episode_sources(selected_anime, episode)

        if not all_sources:
            logger.info("❌ Nenhuma fonte conseguiu extrair o vídeo.")
            logger.info("   💡 O episódio está indisponível em todas as fontes.")
            break

        progress_str = _format_episode_progress(episode, num_episodes, total_episodes)
        logger.info(f"▶️  Iniciando reprodução do episódio {progress_str}...")

        source_names = [s for _, s in all_sources]
        if len(source_names) > 1:
            logger.info(f"   🔄 Tentando fontes: {', '.join(source_names)}")
        else:
            logger.info(f"   Fonte: {source_names[0]}")

        video_sources = []
        for page_url, source_name in all_sources:
            try:
                video_url = rep.search_player_from_page(page_url, source_name)
                if video_url:
                    video_sources.append((video_url, source_name, page_url))
                else:
                    logger.info(
                        f"   ⚠️  [{source_name}] Não retornou URL de vídeo (page_url={page_url[:80]})"
                    )
            except (OSError, ConnectionError, TimeoutError) as e:
                logger.warning(f"   ❌ [{source_name}] Erro de rede ao extrair vídeo: {e!r}")
                continue
            except Exception as e:
                logger.warning(
                    f"   ❌ [{source_name}] Erro inesperado ao extrair vídeo: {e!r}", exc_info=True
                )
                continue

        sources_for_playback = video_sources if video_sources else all_sources

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

        if result.action == "next":
            if result.data and "episode" in result.data:
                next_episode = result.data["episode"]
                if next_episode <= num_episodes:
                    episode_idx = next_episode - 1
                    current_episode_idx = next_episode - 1
                    if next_episode == num_episodes:
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
                            return
                    continue
        elif result.action == "quit":
            if result.data and "episode" in result.data:
                final_episode = result.data["episode"]
                if final_episode >= 1 and final_episode <= num_episodes:
                    episode_idx = final_episode - 1
                    current_episode_idx = final_episode - 1
                    episode = final_episode
        elif result.action == "auto-next":
            current_episode = result.data.get("episode", episode) if result.data else episode

            _sync_anilist_progress(anilist_id, current_episode, num_episodes)

            episode_idx = current_episode - 1
            current_episode_idx = current_episode - 1
            next_episode_idx = episode_idx + 1
            if next_episode_idx < num_episodes:
                episode_idx = next_episode_idx
                current_episode_idx = next_episode_idx
                logger.info(f"▶️  Carregando próximo episódio: {episode_idx + 1}")
                continue
            else:
                logger.info("✅ Último episódio assistido!")
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
                    return
                return
        elif result.action == "previous":
            if result.data and "episode" in result.data:
                prev_episode = result.data["episode"]
                if prev_episode >= 1:
                    episode_idx = prev_episode - 1
                    current_episode_idx = prev_episode - 1
                    continue
        elif result.action == "reload":
            continue
        elif result.action == "mark-menu":
            pass
        elif result.exit_code not in [0, 3]:
            logger.info(f"⚠️  MPV exit code: {result.exit_code}")
            if result.exit_code == 2:
                logger.info(" (Possível erro ao reproduzir ou janela fechada)")

        if result.action != "next":
            if result.exit_code != 0:
                logger.info("⏳ Pressione Enter para continuar...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    pass

                pass

            confirm_options = ["✅ Sim, assisti até o final", "❌ Não, parei antes."]
            confirm = menu_navigate(
                confirm_options,
                msg=f"Você assistiu o episódio {episode} de '{selected_anime}' até o final?",
            )

            if confirm == "✅ Sim, assisti até o final":
                episode = current_episode_idx + 1
                save_history(selected_anime, episode_idx, anilist_id, source)

                _sync_anilist_progress(anilist_id, episode, num_episodes)

                if episode == num_episodes:
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
                        return

        selected_opt = menu_navigate(
            build_anilist_post_playback_options(current_episode_idx, num_episodes),
            msg="O que quer fazer agora?",
        )

        if not selected_opt or selected_opt in {"🔙 Voltar", "↩️  Voltar ao menu anterior"}:
            return
        if selected_opt == "▶️  Próximo":
            current_episode_idx += 1
            episode_idx = current_episode_idx
        elif selected_opt == "◀️  Anterior":
            current_episode_idx -= 1
            episode_idx = current_episode_idx
        elif selected_opt == "🔁 Replay":
            pass
        elif selected_opt == "📋 Escolher outro episódio":
            episode_list = rep.get_episode_list(selected_anime)
            new_idx = menu_navigate_episodes(episode_list)
            if new_idx is None:
                return
            episode_idx = new_idx
            current_episode_idx = new_idx
        elif selected_opt == "🔄 Trocar fonte":
            new_anime, new_episode_idx = switch_anime_source(
                selected_anime, args, anilist_id, display_title
            )
            if new_anime:
                selected_anime = new_anime
                episode_idx = new_episode_idx
                current_episode_idx = new_episode_idx
                num_episodes = len(rep.get_episode_list(selected_anime))
