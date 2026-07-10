"""Manga source-selection service (business logic).

Extracted from manga_tupi.py. Handles the logic of choosing/switching the
source a manga is read from:

- re-searching a manga in a newly selected source to get its correct id,
- falling back to the manga's other known sources when a chapter is missing.

These functions may need a loading spinner, so they accept an injected
``progress`` context manager (defaulting to a lazy ui_bridge proxy) following
the same dependency-injection pattern used in ``services/history_service.py``.
They never build menus; the command layer owns prompts.
"""

from services import ui_bridge
from services.manga.reading_flow import (
    build_manga_url,
    find_chapter_by_number,
    sort_chapters_ascending,
)
from utils.logging import get_logger

logger = get_logger(__name__)


def research_manga_in_new_source(
    service,
    selected_manga,
    new_source: str,
    progress=ui_bridge.loading,
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
            logger.debug(f"Fonte indisponível: {e}")
        except Exception as e:
            logger.warning(f"Erro inesperado ao carregar capítulos: {e}")

        with progress(f"Buscando '{selected_manga.title}' em {new_source}..."):
            results = service.search_manga(selected_manga.title, source=new_source)

        if not results:
            logger.info(f"⚠️  Manga não encontrado em {new_source}")
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

        logger.info(f"✓ Encontrado em {new_source}: {best_match.title}")
        return selected_manga.model_copy(
            update={
                "id": best_match.id,
                "title": best_match.title,
                "description": best_match.description,
                "status": best_match.status,
            }
        )
    except Exception as e:
        logger.info(f"⚠️  Erro ao buscar em {new_source}: {e}")
        return selected_manga


def resume_from_other_source(
    service,
    selected_manga,
    chapter_num: int,
    current_source: str,
    progress=ui_bridge.loading,
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
        except Exception:
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
