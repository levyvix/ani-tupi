"""Manga source matching, switching, and chapter fallback selection."""

from services.core import ui_bridge
from services.manga.reading_logic import (
    build_manga_url,
    find_chapter_by_number,
    sort_chapters_ascending,
)
from services.manga.manga_service import MangaDexError, UnifiedMangaService
from utils.logging import get_logger

logger = get_logger(__name__)


def research_manga_in_new_source(
    service,
    selected_manga,
    new_source: str,
    progress=ui_bridge.loading,
    *,
    log=logger,
):
    """Re-search a manga in a new source and return an updated copy.

    When switching sources, the manga id may differ. This verifies the manga
    exists in ``new_source`` and returns a copy of ``selected_manga`` with the
    corrected id/metadata so subsequent chapter fetches target the right
    source. The input ``selected_manga`` is never mutated; if no update is
    needed (or the manga is not found), the original object is returned
    unchanged.
    """
    try:
        # If the merged search already knows this manga's id in the new source,
        # use it directly — no re-search needed.
        known_id = (getattr(selected_manga, "sources", {}) or {}).get(new_source)
        if known_id:
            return selected_manga.model_copy(update={"id": known_id})

        # First try with the current id (ids may be shared across sources).
        try:
            chapters = service.get_chapters(selected_manga.id, source=new_source)
            if chapters:
                return selected_manga
        except (ConnectionError, TimeoutError) as e:
            log.debug(f"Fonte indisponível: {e}")
        except Exception as e:
            log.warning(f"Erro inesperado ao carregar capítulos: {e}")

        with progress(f"Buscando '{selected_manga.title}' em {new_source}..."):
            results = service.search_manga(selected_manga.title, source=new_source)

        if not results:
            log.info(f"⚠️  Manga não encontrado em {new_source}")
            return selected_manga

        best_match = None

        # Exact title match first.
        for result in results:
            if result.title.lower() == selected_manga.title.lower():
                best_match = result
                break

        # Match by id (ids can be shared).
        if not best_match:
            for result in results:
                if result.id == selected_manga.id:
                    best_match = result
                    break

        # Otherwise prefer the shortest title (likely the main series).
        if not best_match:
            best_match = min(results, key=lambda x: len(x.title))

        log.info(f"✓ Encontrado em {new_source}: {best_match.title}")
        return selected_manga.model_copy(
            update={
                "id": best_match.id,
                "title": best_match.title,
                "description": best_match.description,
                "status": best_match.status,
            }
        )
    except Exception as e:
        log.info(f"⚠️  Erro ao buscar em {new_source}: {e}")
        return selected_manga


def resume_from_other_source(
    service,
    selected_manga,
    chapter_num: int,
    current_source: str,
    progress=ui_bridge.loading,
    *,
    log=logger,
):
    """Find a chapter in the manga's other known sources.

    Returns ``(source, manga_url, sorted_chapters, chapter, updated_manga)``
    for the first source that has ``chapter_num`` with a usable URL, or None.
    On success sets the service source and returns ``updated_manga``, a copy of
    ``selected_manga`` with its id set to that source's id. The input
    ``selected_manga`` is never mutated.
    """
    other_sources = [s for s in (selected_manga.sources or {}) if s != current_source]
    for src in other_sources:
        src_id = selected_manga.sources[src]
        manga_url = build_manga_url(src, src_id)
        try:
            with progress(f"Procurando capítulo {chapter_num} em {src}..."):
                chapters = service.get_chapters(src_id, manga_url=manga_url, source=src)
        except Exception as exc:
            log.debug("Failed to get chapters from source '%s': %s", src, exc)
            continue
        if not chapters:
            continue
        sort_chapters_ascending(chapters)
        chapter = find_chapter_by_number(chapters, chapter_num)
        if chapter and chapter.url:
            service.set_source(src)
            updated_manga = selected_manga.model_copy(update={"id": src_id})
            return src, manga_url, chapters, chapter, updated_manga
    return None


def sources_suffix(sources) -> str:
    sources_str = ", ".join(sorted(sources)) if sources else ""
    return f" [{sources_str}]" if sources_str else ""


def select_source(
    service: UnifiedMangaService,
    selected_manga,
    current_source: str,
    menu,
    progress,
    *,
    preferences,
    research_source,
    ui,
    log,
):
    """Interactive source-change menu.

    Returns ``(chosen_source, updated_manga)`` where ``updated_manga`` is a
    (possibly re-searched) copy of ``selected_manga`` for the chosen source, or
    ``(None, selected_manga)`` to abort. The input ``selected_manga`` is never
    mutated.
    """
    if len(service.get_available_sources()) <= 1:
        return current_source, selected_manga

    manga_sources = list(getattr(selected_manga, "sources", {}) or {})
    saved_source = preferences.get_preferred_source(selected_manga.title)
    sources_with_manga = manga_sources or service.get_available_sources_for_manga(
        selected_manga.title
    )

    menu_options = [f"📖 Ler com {current_source}"]
    if saved_source and saved_source != current_source:
        if saved_source in sources_with_manga:
            menu_options.append(f"⭐ Usar fonte salva: {saved_source}")
        else:
            preferences.remove_preference(selected_manga.title)
            saved_source = None
    for source in sources_with_manga:
        if source != current_source:
            menu_options.append(f"🔄 Trocar para: {source}")

    sources_str = ", ".join(sorted(sources_with_manga)) if sources_with_manga else ""
    menu_title = selected_manga.title
    if sources_str:
        menu_title += f" [{sources_str}]"
    menu_title += f" - Fonte: {current_source}"

    try:
        action = menu(menu_options, menu_title)
    except KeyboardInterrupt:
        return None, selected_manga

    if action is None:
        return None, selected_manga
    if action.startswith("⭐ Usar fonte salva:"):
        new_source = action.split(": ")[1]
        if service.set_source(new_source):
            updated = research_source(service, selected_manga, new_source, progress=progress)
            ui.show_info(f"✓ Fonte alterada para: {new_source}")
            return new_source, updated
    elif action.startswith("🔄 Trocar para:"):
        new_source = action.split(": ")[1]
        if service.set_source(new_source):
            updated = research_source(service, selected_manga, new_source, progress=progress)
            preferences.set_preferred_source(updated.title, new_source)
            ui.show_info(f"✓ Fonte alterada e salva: {new_source}")
            return new_source, updated
        ui.show_warning(f"❌ Falha ao alterar fonte para: {new_source}")
        return None, selected_manga
    return current_source, selected_manga


def get_anilist_progress(selected_manga, *, client, match_progress, log) -> int | None:
    if not client.is_authenticated():
        return None
    try:
        manga_list = client.get_user_manga_list("CURRENT")
        return match_progress(manga_list, selected_manga.title, client.format_title)
    except Exception as exc:
        log.debug("Failed to get AniList progress for '%s': %s", selected_manga.title, exc)
        return None


def load_chapters_with_fallback(
    service, selected_manga, selected_source, allow_source_change, progress, *, preferences, ui, log
):
    """Load chapters, trying other sources on failure.

    Returns ``(chapters, source, url, manga)`` where ``manga`` is a
    (possibly re-sourced) copy of ``selected_manga``. The input
    ``selected_manga`` is never mutated.
    """
    manga_url = build_manga_url(selected_source, selected_manga.id)
    try:
        with progress(f"Carregando capítulos de {selected_source}..."):
            chapters = service.get_chapters(
                selected_manga.id, manga_url=manga_url, source=selected_source
            )
        return chapters, selected_source, manga_url, selected_manga
    except MangaDexError as e:
        ui.show_warning(f"⚠️  {e.user_message}")
        if not allow_source_change:
            return None, selected_source, manga_url, selected_manga
        log.info("🔄 Tentando outras fontes...")
        for fallback_source in service.get_available_sources():
            if fallback_source == selected_source:
                continue
            log.info(f"  Tentando {fallback_source}...")
            try:
                if service.set_source(fallback_source):
                    fb_id = (selected_manga.sources or {}).get(fallback_source, selected_manga.id)
                    manga_url = build_manga_url(fallback_source, fb_id)
                    chapters = service.get_chapters(
                        fb_id, manga_url=manga_url, source=fallback_source
                    )
                    if chapters:
                        updated_manga = selected_manga.model_copy(update={"id": fb_id})
                        preferences.set_preferred_source(updated_manga.title, fallback_source)
                        ui.show_info(f"✓ Usando fonte alternativa: {fallback_source}")
                        return chapters, fallback_source, manga_url, updated_manga
            except Exception as exc:
                log.debug("Fallback source '%s' failed: %s", fallback_source, exc)
                continue
        return None, selected_source, manga_url, selected_manga
    except Exception as e:
        ui.show_warning(f"❌ Erro ao carregar capítulos: {e}")
        return None, selected_source, manga_url, selected_manga


__all__ = [
    "get_anilist_progress",
    "load_chapters_with_fallback",
    "research_manga_in_new_source",
    "resume_from_other_source",
    "select_source",
    "sources_suffix",
]
