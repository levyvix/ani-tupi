"""AniList integration flows for anime playback.

Handles AniList-specific anime flows including search, selection, progress tracking,
sequel detection, and synchronization with AniList API.
"""

from collections.abc import Callable
from typing import Any

from services.anilist.client import anilist_client
from services.repository import rep
from services.core import ui_bridge
from services.anilist.anilist_service import get_scraper_cache
from scrapers import loader
from services.core.history_service import save_history
from utils.video_player import VideoPlayer
from services.anime.source_management import switch_anime_source
from utils.logging import get_logger
from services.anime.anime_persistence import (
    load_anilist_mapping,
    load_language_preference,
    save_language_preference,
)
from services.anime.search_service import incremental_search_anime
from services.anime.search_service import rank_anime_results_by_reference
from utils.title_normalization import normalize_title_for_dedup
from services.anime.playback_service import play_episode_with_fallback, probe_url_playable
from services.anime.episode_service import registry as awaiting_registry
from utils.video_player import _format_episode_progress

# Import extracted functions
from services.anime.episode_service import _resolve_start_episode_idx, SWITCH_SOURCE
from services.anime.episode_service import _load_episode_list, _read_local_progress
from services.anime.anime_persistence import persist_anime_choice
from services.anilist.anilist_service import sync_anilist_progress
from services.anilist.anilist_service import offer_sequel_and_continue

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
        f"🇯🇵 Romaji: {romaji_title}",
        f"🇬🇧 Inglês: {english_title}",
    ]
    language_choice = ui_bridge.menu_navigate(language_options, msg="Escolha o idioma para buscar:")

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
    cache_data = get_scraper_cache(query)

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
        titles_with_sources = rank_anime_results_by_reference(titles_with_sources, romaji_title)

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
                menu_title += (
                    f"   ({current_result_set.word_count} palavras: "
                    f"{len(current_result_set.results)} resultados)\n"
                )
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

        selected_anime_with_source = ui_bridge.menu_navigate(
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


def _get_anilist_titles(anilist_id: int) -> tuple[str | None, str | None]:
    """Fetch English and Romaji titles for an AniList ID.

    Returns ``(english_title, romaji_title)``; either may be ``None``.
    """
    anime_info = anilist_client.get_anime_by_id(anilist_id)
    if not anime_info:
        return None, None
    return anime_info.title.english, anime_info.title.romaji


def _prompt_saved_title_choice(
    saved_title: str | None,
    saved_source: str | None,
) -> tuple[str | None, str | None, bool]:
    """Offer to reuse a previously chosen title.

    Returns ``(selected_anime, source, cancelled)``. ``selected_anime`` is set
    only when the user chose to continue with the saved title. ``cancelled`` is
    ``True`` when the user aborted the menu entirely.
    """
    if not saved_title:
        return None, None, False

    display_title_with_source = saved_title
    if saved_source:
        display_title_with_source = f"{saved_title} [{saved_source}]"

    choice = ui_bridge.menu_navigate(
        ["✅ Continuar com este", "🔄 Escolher outro"],
        msg=f"Você usou '{display_title_with_source}' antes.\nQuer continuar?",
    )

    if not choice:
        return None, None, True

    if choice == "✅ Continuar com este":
        logger.info(f"✅ Usando: {saved_title}")
        return saved_title, saved_source, False

    return None, None, False


def _search_and_select_anime(
    anime_title: str,
    anilist_id: int,
    english_title: str | None,
    romaji_title: str | None,
    display_title: str,
    query_getter: Callable[[str], str],
) -> tuple[str | None, str | None, str]:
    """Run search (cache-first + incremental) and let the user pick an anime.

    Handles the manual-search fallback when nothing is found. Returns
    ``(selected_anime, source, used_query)``; ``selected_anime`` is ``None`` if
    the user cancelled or no result could be resolved.
    """
    search_state, titles_with_sources = load_episodes_from_cache_or_search(
        anime_title, anilist_id, english_title, romaji_title
    )
    used_query = _current_used_query(search_state, anime_title)

    if not titles_with_sources:
        choice = ui_bridge.menu_navigate(
            ["🔍 Buscar manualmente", "🔙 Voltar ao AniList"], msg="O que deseja fazer?"
        )
        if choice != "🔍 Buscar manualmente":
            return None, None, used_query

        manual_query = query_getter("\n🔍 Digite o nome para buscar: ")
        search_state, titles_with_sources = load_episodes_from_cache_or_search(
            manual_query, anilist_id, english_title, romaji_title
        )
        used_query = _current_used_query(search_state, manual_query)
        if not titles_with_sources:
            return None, None, used_query

    return select_anime_from_results(
        titles_with_sources,
        search_state,
        used_query or anime_title,
        display_title,
        english_title,
        romaji_title,
        anilist_id,
    )


def _current_used_query(search_state: Any, fallback: str) -> str:
    """Return the query recorded on the current result set, or ``fallback``."""
    if search_state:
        current_result_set = search_state.get_current()
        if current_result_set:
            return current_result_set.query
    return fallback


def _confirm_watch_or_download(
    selected_anime: str,
    episode_list: list,
    start_episode_idx: int,
    num_episodes: int,
    source: str | None,
) -> int | None:
    """Ask whether to watch now or download; run download loop if chosen.

    Returns the 0-indexed episode to watch, or ``None`` if the user chose
    download/back/cancel (nothing further to play).
    """
    current_episode_idx = start_episode_idx

    while True:
        episode_number = current_episode_idx + 1
        action = ui_bridge.menu_navigate(
            ["▶️ Assistir agora", "📥 Baixar para assistir depois", "🔙 Voltar"],
            msg=f"O que deseja fazer com o episódio {episode_number}?",
        )

        if action == "🔙 Voltar":
            new_idx = ui_bridge.menu_navigate_episodes(episode_list)
            if new_idx is None:
                return None
            current_episode_idx = new_idx
            continue

        if action == "📥 Baixar para assistir depois":
            _download_episodes(selected_anime, episode_number, num_episodes, source)
            return None

        if action == "▶️ Assistir agora":
            return current_episode_idx

        return None


def _download_episodes(
    selected_anime: str,
    episode_number: int,
    num_episodes: int,
    source: str | None,
) -> None:
    """Prompt for an episode range and download it."""
    from services.anime.download_service import AnimeDownloadService
    from utils.range_parser import parse_episode_range, RangeParseError

    logger.info(f"📥 Baixar episódios: {selected_anime}")
    logger.info(f"   Total de episódios: {num_episodes}")

    default_range = f"{episode_number}-"
    logger.info(f"   Padrão: {default_range} (do episódio {episode_number} até o fim)\n")

    try:
        range_input = ui_bridge.prompt("Qual intervalo? (pressione Enter para padrão): ").strip()
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
        with ui_bridge.loading(f"Baixando {len(episodes)} episódio(s)..."):
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


def _available_episode_count(anime_info) -> int | None:
    """Episodes that have actually aired, or None when it can't be determined.

    The "more episodes in other sources" hint only makes sense when we know how
    many episodes actually exist somewhere. For a currently-airing anime AniList
    exposes the next *unaired* episode via ``nextAiringEpisode.episode`` (aired ==
    episode - 1); the ``episodes`` field is the PLANNED total and counts unaired
    episodes too. For a FINISHED anime every planned episode has aired. When
    neither is known we return None so the caller stays silent — "na dúvida, nem
    mostra nada".
    """
    total = anime_info.episodes
    next_airing = getattr(anime_info, "nextAiringEpisode", None)
    if isinstance(next_airing, dict) and next_airing.get("episode"):
        aired = next_airing["episode"] - 1
        return min(aired, total) if total else aired
    if getattr(anime_info, "status", None) == "FINISHED":
        return total
    return None


def _maybe_offer_sequel_on_finish(
    anilist_id: int,
    args,
    current_episode: int,
) -> bool:
    """Offer a sequel when the final episode is reached. Returns True if handled."""
    anilist_episodes = None
    if anilist_id:
        anime_info = anilist_client.get_anime_by_id(anilist_id)
        if anime_info:
            anilist_episodes = _available_episode_count(anime_info)

    return offer_sequel_and_continue(
        anilist_id,
        args,
        current_episode=current_episode,
        anilist_episodes=anilist_episodes,
    )


def _run_playback_loop(
    selected_anime: str,
    source: str | None,
    display_title: str,
    start_episode_idx: int,
    episode_list: list,
    anilist_id: int,
    total_episodes: int | None,
    args,
) -> None:
    """Run the playback + AniList-sync loop until the user exits."""
    current_episode_idx = start_episode_idx
    episode_idx = start_episode_idx
    num_episodes = len(episode_list)
    # Reuse one player for the whole playback loop so session state (notably
    # autoplay toggled from MPV) survives when loading the next episode.
    player = VideoPlayer()

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

        fallback_result = play_episode_with_fallback(
            player=player,
            sources=all_sources,
            anime_title=selected_anime,
            episode_number=episode,
            total_episodes=num_episodes,
            use_ipc=True,
            debug=args.debug,
            anilist_id=anilist_id,
            anilist_episodes=total_episodes,
            extractor=rep.search_player_from_page,
            url_probe=probe_url_playable,
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
                    if next_episode == num_episodes and _maybe_offer_sequel_on_finish(
                        anilist_id, args, next_episode
                    ):
                        return
                    continue
        elif result.action == "quit":
            if result.data and "episode" in result.data:
                final_episode = result.data["episode"]
                if 1 <= final_episode <= num_episodes:
                    episode_idx = final_episode - 1
                    current_episode_idx = final_episode - 1
                    episode = final_episode
        elif result.action == "auto-next":
            current_episode = result.data.get("episode", episode) if result.data else episode

            sync_anilist_progress(anilist_id, current_episode, num_episodes)

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
                if anilist_id and _maybe_offer_sequel_on_finish(anilist_id, args, current_episode):
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
                ui_bridge.pause()

            confirm = ui_bridge.menu_navigate(
                ["✅ Sim, assisti até o final", "❌ Não, parei antes."],
                msg=f"Você assistiu o episódio {episode} de '{selected_anime}' até o final?",
            )

            if confirm == "✅ Sim, assisti até o final":
                episode = current_episode_idx + 1
                save_history(selected_anime, episode_idx, anilist_id, source)

                sync_anilist_progress(anilist_id, episode, num_episodes)

                if episode == num_episodes and _maybe_offer_sequel_on_finish(
                    anilist_id, args, episode
                ):
                    return

        selected_opt = ui_bridge.menu_navigate(
            build_anilist_post_playback_options(current_episode_idx, num_episodes),
            msg="O que quer fazer agora?",
        )

        if not selected_opt or selected_opt in {
            "🔙 Voltar",
            "↩️  Voltar ao menu anterior",
        }:
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
            new_idx = ui_bridge.menu_navigate_episodes(episode_list)
            if new_idx is None:
                return
            episode_idx = new_idx
            current_episode_idx = new_idx
        elif selected_opt == "🔄 Trocar fonte":
            new_anime, new_episode_idx = switch_anime_source(
                selected_anime, args, anilist_id, display_title
            )
            if new_anime and new_episode_idx is not None:
                selected_anime = new_anime
                episode_idx = new_episode_idx
                current_episode_idx = new_episode_idx
                num_episodes = len(rep.get_episode_list(selected_anime))


def anilist_anime_flow(
    anime_title: str,
    anilist_id: int,
    args,
    anilist_progress: int = 0,
    display_title: str | None = None,
    total_episodes: int | None = None,
    query_getter: Callable[[str], str] = ui_bridge.prompt,
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
        query_getter: Callable to get manual search query from user (default: ui_bridge.prompt)
    """
    if not display_title:
        display_title = anime_title

    english_title, romaji_title = _get_anilist_titles(anilist_id)

    loader.load_plugins(rep.register)
    rep.clear_search_results()

    if anilist_id:
        rep.anime_to_anilist_id[anime_title] = anilist_id

    active_sources = rep.get_active_sources()
    if active_sources:
        logger.debug(f"ℹ️  Fontes ativas: {', '.join(active_sources)}")

    # 1. Resolve which anime/source to play (saved choice, or search + select).
    saved_title, saved_source, saved_url = (
        load_anilist_mapping(anilist_id) if anilist_id else (None, None, None)
    )

    selected_anime, source, saved_cancelled = _prompt_saved_title_choice(saved_title, saved_source)
    if saved_cancelled:
        return

    if selected_anime is None:
        if english_title and romaji_title:
            resolved = resolve_preferred_title(anilist_id, english_title, romaji_title, anime_title)
            if resolved is None:
                return  # User cancelled
            anime_title = resolved

        selected_anime, source, _used_query = _search_and_select_anime(
            anime_title,
            anilist_id,
            english_title,
            romaji_title,
            display_title,
            query_getter,
        )
        if selected_anime is None:
            return  # User cancelled or nothing found

    # Clear any stale awaiting episode URLs from previous sessions for this anime.
    awaiting_registry.clear(selected_anime)

    # 2. Persist the resolved choice for next time.
    if anilist_id:
        persist_anime_choice(anilist_id, selected_anime, anime_title, source)

    # 3. Load the episode list (cache-first).
    episode_list, scraper_episode_count = _load_episode_list(
        selected_anime, saved_title, saved_source, saved_url, anilist_id
    )
    if episode_list is None:
        return

    # 4. Decide which episode to start from.
    local_progress = _read_local_progress(selected_anime)
    while True:
        start_episode_idx = _resolve_start_episode_idx(
            selected_anime,
            episode_list,
            anilist_progress,
            local_progress,
            total_episodes,
            scraper_episode_count,
        )
        if start_episode_idx is None:
            return

        if start_episode_idx is not SWITCH_SOURCE:
            break

        # User chose to switch sources: run a fresh search + selection. On
        # success, jump straight to playback with the new source; on cancel,
        # re-show the "de onde continuar" menu.
        new_anime, new_episode_idx = switch_anime_source(
            selected_anime, args, anilist_id, display_title
        )
        if new_anime and new_episode_idx is not None:
            selected_anime = new_anime
            episode_list = rep.get_episode_list(selected_anime)
            scraper_episode_count = len(episode_list)
            start_episode_idx = new_episode_idx
            break

    if not isinstance(start_episode_idx, int):
        raise ValueError(f"episode_idx should be int, got {type(start_episode_idx)}")

    # 5. Confirm watch vs download.
    watch_episode_idx = _confirm_watch_or_download(
        selected_anime, episode_list, start_episode_idx, len(episode_list), source
    )
    if watch_episode_idx is None:
        return

    # 6. Play (with AniList sync).
    _run_playback_loop(
        selected_anime,
        source,
        display_title,
        watch_episode_idx,
        episode_list,
        anilist_id,
        total_episodes,
        args,
    )
