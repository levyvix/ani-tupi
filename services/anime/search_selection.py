"""User-facing selection helpers for anime search results."""

from services.anime.search_result_models import (
    ContextualSearchResults,
    DualSearchResults,
    ManualSearchSelection,
)


def select_manual_search_results(
    search_results: ContextualSearchResults,
    query: str,
    args,
    *,
    repository,
    ui,
    log,
) -> ManualSearchSelection:
    """Run the manual incremental search UI for one query."""
    search_state = search_results.state
    current_titles = search_results.titles_with_sources
    while True:
        current_result = search_state.get_current()
        used_query = current_result.used_query if current_result else query
        titles_with_sources = current_titles

        if not titles_with_sources:
            return ManualSearchSelection(
                selected_anime=None,
                source=None,
                was_cancelled=False,
                search_query_used=query,
            )

        filtered_titles = titles_with_sources
        if hasattr(args, "season") and args.season is not None:
            requested_season = args.season

            if requested_season > 1:
                filtered_titles = []
                for title in titles_with_sources:
                    base_title = title.split(" [")[0] if " [" in title else title
                    inferred_season = repository._infer_season_from_title(base_title)
                    inferred_season = inferred_season or 1

                    if inferred_season == requested_season:
                        filtered_titles.append(title)

                if not filtered_titles:
                    log.warning(
                        f"⚠️  Nenhum resultado encontrado especificamente para a estação {requested_season}. "
                        f"Mostrando todos os resultados."
                    )
                    filtered_titles = titles_with_sources
                else:
                    log.info(f"🎬 Filtrando resultados para estação {requested_season}")

        continue_button = "🔍 Continuar buscando (menos palavras)"
        if search_state.has_previous():
            titles_with_button = [continue_button] + filtered_titles
            word_count = current_result.word_count if current_result else len(used_query.split())
            show_continue_msg = f" (usando {word_count} palavras)"
        else:
            titles_with_button = filtered_titles
            show_continue_msg = ""

        selected_anime_with_source = ui.menu_navigate(
            titles_with_button,
            msg=f"Escolha o Anime.{show_continue_msg}",
            enable_search=False,
        )

        if not selected_anime_with_source:
            return ManualSearchSelection(
                selected_anime=None,
                source=None,
                was_cancelled=True,
                search_query_used=used_query,
            )

        if selected_anime_with_source == continue_button:
            previous = search_state.go_back()
            current_titles = previous.results if previous else current_titles
            continue

        selected_anime = selected_anime_with_source.split(" [")[0]
        source = None
        if " [" in selected_anime_with_source and selected_anime_with_source.endswith("]"):
            source = selected_anime_with_source.split(" [")[1].rstrip("]")

        return ManualSearchSelection(
            selected_anime=selected_anime,
            source=source,
            was_cancelled=False,
            search_query_used=used_query,
        )


def select_dual_search_results(
    dual_results: DualSearchResults,
    *,
    ui,
) -> ManualSearchSelection:
    """Show both user-query and official-title results in one menu."""
    options: list[str] = []
    seen_titles: set[str] = set()

    def add_group(label: str, results: ContextualSearchResults) -> None:
        if not results.titles_with_sources:
            return
        options.append(f"─ {label}")
        for title in results.titles_with_sources:
            if title in seen_titles:
                continue
            seen_titles.add(title)
            options.append(title)

    add_group(f"Sua busca: {dual_results.user_query}", dual_results.user_results)
    add_group(f"Nome oficial/romaji: {dual_results.official_query}", dual_results.official_results)

    if not seen_titles:
        return ManualSearchSelection(selected_anime=None, source=None, was_cancelled=False)

    selected_anime_with_source = ui.menu_navigate(
        options,
        msg="Escolha o Anime.",
        enable_search=False,
    )
    if not selected_anime_with_source:
        return ManualSearchSelection(selected_anime=None, source=None, was_cancelled=True)

    selected_anime = selected_anime_with_source.split(" [")[0]
    source = None
    if " [" in selected_anime_with_source and selected_anime_with_source.endswith("]"):
        source = selected_anime_with_source.split(" [")[1].rstrip("]")

    return ManualSearchSelection(
        selected_anime=selected_anime,
        source=source,
        was_cancelled=False,
        search_query_used=dual_results.official_results.used_query
        or dual_results.user_results.used_query,
    )


__all__ = ["select_dual_search_results", "select_manual_search_results"]
