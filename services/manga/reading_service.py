"""Manga reading service - flow logic, preferences, source choice and orchestration.

Holds the pure logic that decides *what* to read (resume point, chapter
sorting/lookup, per-source URLs), the persisted user preferences, the
source-switching helpers, and the interactive orchestration that wires them
together. UI callables (``menu``, ``progress``, ``prompt``, ``show_*``) are
injected, defaulting to lazy ``ui_bridge`` proxies.

Seções:
- Lógica de leitura
- Preferências persistidas
- Seleção de fonte
- Orquestração da leitura
"""

import json
from dataclasses import dataclass

from models.config import get_data_path
from models.models import ChapterData, Status
from services.anilist.client import anilist_client
from services.core import ui_bridge
from services.manga.download_service import (
    download_chapters_batch,
    download_images,
    prompt_download_range,
    resolve_parallelism,
    split_new_and_downloaded,
)
from services.manga.manga_service import (
    DownloadedChaptersTracker,
    MangaDexError,
    MangaHistory,
    MangaNotFoundError,
    UnifiedMangaService,
)
from utils.logging import get_logger
from utils.manga_reader import is_zathura_running, open_pdf_reader
from utils.pdf_converter import create_pdf_from_images

__all__ = [
    # Lógica de leitura
    "ResumePoint",
    "build_manga_url",
    "chapter_number_value",
    "compute_resume_point",
    "find_chapter_by_number",
    "find_next_chapter_index",
    "match_anilist_progress",
    "promote_resume_chapter",
    "sort_chapters_ascending",
    # Preferências persistidas
    "MangaSelectionPreferences",
    "MangaSourcePreferences",
    "manga_selection_preferences",
    "manga_source_preferences",
    # Seleção de fonte
    "research_manga_in_new_source",
    "resume_from_other_source",
    # Orquestração da leitura
    "continue_manga_flow",
    "handle_download_for_later",
    "start_manga_search",
]

logger = get_logger(__name__)


# === Lógica de leitura ===


# Canonical source of manga URL templates. Any module needing to build a
# base manga URL (reading flow, unified service, source selection) reads from
# this single dict via ``build_manga_url``.
_MANGA_URL_TEMPLATES = {
    "mugiwaras": "https://mugiwarasoficial.com/manga/{}/",
    "mangadex": "https://mangadex.org/title/{}",
    "mangalivre": "https://mangalivre.blog/manga/{}/",
}


def build_manga_url(source: str, manga_id: str) -> str | None:
    """Construct the base manga URL for sources that need it."""
    template = _MANGA_URL_TEMPLATES.get(source)
    return template.format(manga_id) if template else None


def chapter_number_value(value) -> float | None:
    """Parse a chapter number (str/int/float) to float, tolerant of commas and junk.

    Single source of truth for chapter-number parsing (previously scattered as
    ``float(...)`` / ``int(float(...))`` across the manga flow). Returns None when
    the value is not a usable number so callers can distinguish junk from 0.
    """
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _chapter_sort_value(chapter: ChapterData) -> float:
    """Numeric sort key for a chapter, tolerant of commas and junk."""
    value = chapter_number_value(chapter.number)
    return value if value is not None else 0.0


def sort_chapters_ascending(chapters: list[ChapterData]) -> list[ChapterData]:
    """Return chapters sorted ascending by number (1 -> 2 -> 3 -> ...).

    Sorts in place (matching prior behavior) and also returns the list for
    convenience/chaining.
    """
    chapters.sort(key=_chapter_sort_value)
    return chapters


def find_chapter_by_number(chapters: list[ChapterData], number: int) -> ChapterData | None:
    """Return the chapter whose integer number matches, or None."""
    for chapter in chapters:
        value = chapter_number_value(chapter.number)
        if value is not None and int(value) == number:
            return chapter
    return None


@dataclass(frozen=True)
class ResumePoint:
    """Recommended chapter to resume reading, computed before scraping."""

    chapter_number: int
    source: str  # "AniList" or "local"


def compute_resume_point(
    anilist_progress: int | None,
    last_local_chapter: str | None,
) -> ResumePoint | None:
    """Decide which chapter to recommend resuming, preferring AniList progress.

    Args:
        anilist_progress: AniList chapter progress (chapters read) or None.
        last_local_chapter: Last read chapter from local history (e.g. "42") or None.

    Returns:
        A ResumePoint for the *next* chapter to read, or None if unknown.
    """
    if anilist_progress is not None:
        return ResumePoint(chapter_number=anilist_progress + 1, source="AniList")

    if last_local_chapter:
        value = chapter_number_value(last_local_chapter)
        if value is not None:
            return ResumePoint(chapter_number=int(value) + 1, source="local")
        return None

    return None


def promote_resume_chapter(
    chapters: list[ChapterData],
    chapter_labels: list[str],
    resume_point: ResumePoint,
) -> None:
    """Move the recommended chapter to the top of the display list with a hint.

    Mutates ``chapters`` and ``chapter_labels`` in place (kept in sync), matching
    the prior monolith behavior. If no exact match is found, the first chapter is
    labeled as the resume target as a fallback.
    """
    if any("Retomar" in label for label in chapter_labels):
        return

    recommended_index = None
    for i, chapter in enumerate(chapters):
        value = chapter_number_value(chapter.number)
        if value is not None and int(value) == resume_point.chapter_number:
            recommended_index = i
            break

    index = recommended_index if recommended_index is not None else 0
    if index >= len(chapters):
        return

    resume_label = f"⮕ Retomar ({resume_point.source}) - {chapter_labels[index]}"
    chapter = chapters.pop(index)
    chapter_labels.pop(index)
    chapters.insert(0, chapter)
    chapter_labels.insert(0, resume_label)


def find_next_chapter_index(chapters: list[ChapterData], current_number: str) -> int | None:
    """Return the index of the first chapter numbered greater than current_number."""
    current_value = chapter_number_value(current_number)
    if current_value is None:
        return None
    for i, chapter in enumerate(chapters):
        value = chapter_number_value(chapter.number)
        if value is not None and value > current_value:
            return i
    return None


def match_anilist_progress(manga_list, manga_title: str, format_title) -> int | None:
    """Find AniList reading progress for a manga by fuzzy title match.

    Args:
        manga_list: List of AniList media list entries (may be None/empty).
        manga_title: Local manga title to match against.
        format_title: Unused placeholder kept for signature stability.

    Returns:
        Progress (chapters read) for the first matching entry, or None.
    """
    if not manga_list:
        return None

    target = manga_title.lower()
    for entry in manga_list:
        if not entry.media:
            continue
        entry_title = ""
        if entry.media.title.romaji:
            entry_title = entry.media.title.romaji.lower()
        elif entry.media.title.english:
            entry_title = entry.media.title.english.lower()

        if not entry_title:
            continue

        if target == entry_title or target in entry_title or entry_title in target:
            if entry.progress:
                return entry.progress

    return None


# === Preferências persistidas ===


class MangaSelectionPreferences:
    """Manages manga selection preferences with JSON persistence."""

    def __init__(self):
        """Initialize preferences manager."""
        self.preferences_file = get_data_path() / "manga_selection_preferences.json"
        self._preferences: dict[str, str] = {}  # search_query -> manga_id
        self._load_preferences()

    def _load_preferences(self) -> None:
        """Load preferences from JSON file."""
        try:
            if self.preferences_file.exists():
                with self.preferences_file.open("r", encoding="utf-8") as f:
                    self._preferences = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._preferences = {}

    def _save_preferences(self) -> None:
        """Save preferences to JSON file."""
        try:
            # Ensure directory exists
            self.preferences_file.parent.mkdir(parents=True, exist_ok=True)

            with self.preferences_file.open("w", encoding="utf-8") as f:
                json.dump(self._preferences, f, indent=2, ensure_ascii=False)
        except OSError:
            # Silently fail if unable to save (graceful degradation)
            pass

    def get_preferred_manga_id(self, search_query: str) -> str | None:
        """Get preferred manga ID for a search query.

        Args:
            search_query: The original search query

        Returns:
            Preferred manga ID or None if not set
        """
        # Normalize query for consistent matching
        normalized_query = search_query.strip().lower()
        return self._preferences.get(normalized_query)

    def set_preferred_manga_id(self, search_query: str, manga_id: str) -> None:
        """Set preferred manga ID for a search query.

        Args:
            search_query: The original search query
            manga_id: The manga ID to prefer
        """
        # Normalize query for consistent matching
        normalized_query = search_query.strip().lower()
        self._preferences[normalized_query] = manga_id
        self._save_preferences()

    def remove_preference(self, search_query: str) -> bool:
        """Remove preference for a search query.

        Args:
            search_query: The search query

        Returns:
            True if preference was removed, False if not found
        """
        normalized_query = search_query.strip().lower()
        if normalized_query in self._preferences:
            del self._preferences[normalized_query]
            self._save_preferences()
            return True
        return False

    def get_all_preferences(self) -> dict[str, str]:
        """Get all manga selection preferences.

        Returns:
            Dictionary mapping search queries to manga IDs
        """
        return self._preferences.copy()


# Global instance for use throughout the app
manga_selection_preferences = MangaSelectionPreferences()


class MangaSourcePreferences:
    """Manages manga source preferences with JSON persistence."""

    def __init__(self):
        """Initialize preferences manager."""
        self.preferences_file = get_data_path() / "manga_source_preferences.json"
        self._preferences: dict[str, str] = {}
        self._load_preferences()

    def _load_preferences(self) -> None:
        """Load preferences from JSON file."""
        try:
            if self.preferences_file.exists():
                with self.preferences_file.open("r", encoding="utf-8") as f:
                    self._preferences = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._preferences = {}

    def _save_preferences(self) -> None:
        """Save preferences to JSON file."""
        try:
            # Ensure directory exists
            self.preferences_file.parent.mkdir(parents=True, exist_ok=True)

            with self.preferences_file.open("w", encoding="utf-8") as f:
                json.dump(self._preferences, f, indent=2, ensure_ascii=False)
        except OSError:
            # Silently fail if unable to save (graceful degradation)
            pass

    def get_preferred_source(self, manga_title: str) -> str | None:
        """Get preferred source for a manga.

        Args:
            manga_title: The manga title

        Returns:
            Preferred source name or None if not set
        """
        # Normalize title for consistent matching
        normalized_title = manga_title.strip().lower()
        return self._preferences.get(normalized_title)

    def set_preferred_source(self, manga_title: str, source: str) -> None:
        """Set preferred source for a manga.

        Args:
            manga_title: The manga title
            source: The source name (e.g., "mugiwaras", "mangadex")
        """
        # Normalize title for consistent matching
        normalized_title = manga_title.strip().lower()
        self._preferences[normalized_title] = source
        self._save_preferences()

    def remove_preference(self, manga_title: str) -> bool:
        """Remove preference for a manga.

        Args:
            manga_title: The manga title

        Returns:
            True if preference was removed, False if not found
        """
        normalized_title = manga_title.strip().lower()
        if normalized_title in self._preferences:
            del self._preferences[normalized_title]
            self._save_preferences()
            return True
        return False

    def get_all_preferences(self) -> dict[str, str]:
        """Get all manga source preferences.

        Returns:
            Dictionary mapping manga titles to source names
        """
        return self._preferences.copy()


# Global instance for use throughout the app
manga_source_preferences = MangaSourcePreferences()


# === Seleção de fonte ===


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
        except Exception as exc:
            logger.debug("Failed to get chapters from source '%s': %s", src, exc)
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


# === Orquestração da leitura ===


def start_manga_search(
    service: UnifiedMangaService,
    title: str,
    menu=ui_bridge.menu_navigate,
    progress=ui_bridge.loading,
) -> None:
    """Search for a manga by title, pick one, then continue into the read flow."""
    search_term = title.split(" / ")[-1].strip() if " / " in title else title

    try:
        with progress(f"Buscando '{search_term}'..."):
            results = service.search_manga(search_term)
    except MangaNotFoundError:
        ui_bridge.show_warning("❌ Mangá não encontrado. Tente outra pesquisa.")
        return
    except MangaDexError as e:
        ui_bridge.show_warning(f"⚠️  {e.user_message}")
        return
    except Exception as e:
        ui_bridge.show_warning(f"❌ Erro inesperado: {e}")
        return

    if not results:
        ui_bridge.show_warning("❌ Nenhum mangá encontrado. Tente outra pesquisa.")
        return

    preferred_manga_id = manga_selection_preferences.get_preferred_manga_id(title)
    selected_manga = None
    if preferred_manga_id:
        selected_manga = next((m for m in results if m.id == preferred_manga_id), None)

    if selected_manga:
        suffix = _sources_suffix(selected_manga.sources)
        try:
            choice = menu(
                [
                    f"⭐ Continuar com: {selected_manga.title}{suffix} (salvo)",
                    "🔄 Trocar de mangá",
                ],
                "Qual mangá deseja ler?",
            )
        except KeyboardInterrupt:
            return
        if choice is None:
            return
        if choice.startswith("🔄"):
            selected_manga = None

    if not selected_manga:
        if len(results) > 1:
            label_to_manga = {}
            for manga in results:
                suffix = _sources_suffix(manga.sources)
                if manga.id == preferred_manga_id:
                    label = f"⭐ {manga.title}{suffix} (salvo)"
                else:
                    label = f"{manga.title}{suffix}"
                label_to_manga[label] = manga
            try:
                selected_title = menu(list(label_to_manga), "Selecione mangá")
            except KeyboardInterrupt:
                return
            if selected_title is None:
                return
            selected_manga = label_to_manga.get(selected_title)
            if selected_manga is None:
                logger.error(f"Manga '{selected_title}' não encontrado nos resultados.")
                return
        else:
            selected_manga = results[0]

    manga_selection_preferences.set_preferred_manga_id(title, selected_manga.id)
    ui_bridge.show_info(f"✓ Preferência salva: {selected_manga.title}")

    continue_manga_flow(
        service, selected_manga, allow_source_change=True, menu=menu, progress=progress
    )


def _sources_suffix(sources) -> str:
    sources_str = ", ".join(sorted(sources)) if sources else ""
    return f" [{sources_str}]" if sources_str else ""


def _select_source(
    service: UnifiedMangaService, selected_manga, current_source: str, menu, progress
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
    saved_source = manga_source_preferences.get_preferred_source(selected_manga.title)
    sources_with_manga = manga_sources or service.get_available_sources_for_manga(
        selected_manga.title
    )

    menu_options = [f"📖 Ler com {current_source}"]
    if saved_source and saved_source != current_source:
        if saved_source in sources_with_manga:
            menu_options.append(f"⭐ Usar fonte salva: {saved_source}")
        else:
            manga_source_preferences.remove_preference(selected_manga.title)
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
            updated = research_manga_in_new_source(
                service, selected_manga, new_source, progress=progress
            )
            ui_bridge.show_info(f"✓ Fonte alterada para: {new_source}")
            return new_source, updated
    elif action.startswith("🔄 Trocar para:"):
        new_source = action.split(": ")[1]
        if service.set_source(new_source):
            updated = research_manga_in_new_source(
                service, selected_manga, new_source, progress=progress
            )
            manga_source_preferences.set_preferred_source(updated.title, new_source)
            ui_bridge.show_info(f"✓ Fonte alterada e salva: {new_source}")
            return new_source, updated
        ui_bridge.show_warning(f"❌ Falha ao alterar fonte para: {new_source}")
        return None, selected_manga
    return current_source, selected_manga


def _get_anilist_progress(selected_manga) -> int | None:
    if not anilist_client.is_authenticated():
        return None
    try:
        manga_list = anilist_client.get_user_manga_list("CURRENT")
        return match_anilist_progress(manga_list, selected_manga.title, anilist_client.format_title)
    except Exception as exc:
        logger.debug("Failed to get AniList progress for '%s': %s", selected_manga.title, exc)
        return None


def _load_chapters_with_fallback(
    service, selected_manga, selected_source, allow_source_change, progress
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
        ui_bridge.show_warning(f"⚠️  {e.user_message}")
        if not allow_source_change:
            return None, selected_source, manga_url, selected_manga
        logger.info("🔄 Tentando outras fontes...")
        for fallback_source in service.get_available_sources():
            if fallback_source == selected_source:
                continue
            logger.info(f"  Tentando {fallback_source}...")
            try:
                if service.set_source(fallback_source):
                    fb_id = (selected_manga.sources or {}).get(fallback_source, selected_manga.id)
                    manga_url = build_manga_url(fallback_source, fb_id)
                    chapters = service.get_chapters(
                        fb_id, manga_url=manga_url, source=fallback_source
                    )
                    if chapters:
                        updated_manga = selected_manga.model_copy(update={"id": fb_id})
                        manga_source_preferences.set_preferred_source(
                            updated_manga.title, fallback_source
                        )
                        ui_bridge.show_info(f"✓ Usando fonte alternativa: {fallback_source}")
                        return chapters, fallback_source, manga_url, updated_manga
            except Exception as exc:
                logger.debug("Fallback source '%s' failed: %s", fallback_source, exc)
                continue
        return None, selected_source, manga_url, selected_manga
    except Exception as e:
        ui_bridge.show_warning(f"❌ Erro ao carregar capítulos: {e}")
        return None, selected_source, manga_url, selected_manga


def continue_manga_flow(
    service: UnifiedMangaService,
    selected_manga,
    allow_source_change: bool = True,
    menu=ui_bridge.menu_navigate,
    progress=ui_bridge.loading,
) -> None:
    """Continue with chapter selection and reading for a selected manga."""
    manga_sources = list(getattr(selected_manga, "sources", {}) or {})
    selected_source = (
        manga_sources[0] if manga_sources else (service.last_found_source or service.current_source)
    )

    if allow_source_change:
        chosen, selected_manga = _select_source(
            service, selected_manga, selected_source, menu, progress
        )
        if chosen is None:
            return
        selected_source = chosen

    if manga_source_preferences.get_preferred_source(selected_manga.title) != selected_source:
        manga_source_preferences.set_preferred_source(selected_manga.title, selected_source)

    history = MangaHistory()
    resume_point = compute_resume_point(
        _get_anilist_progress(selected_manga),
        history.get_last_chapter(selected_manga.title),
    )

    resume_immediately = False
    if resume_point is not None:
        try:
            resume_choice = menu(
                [
                    f"⮕ Sim, retomar capítulo {resume_point.chapter_number} "
                    f"({resume_point.source})",
                    "📋 Não, ver lista completa de capítulos",
                ],
                f"{selected_manga.title} - Retomar leitura?",
            )
        except KeyboardInterrupt:
            return
        if resume_choice and resume_choice.startswith("⮕ Sim, retomar"):
            resume_immediately = True
            ui_bridge.show_info(f"✓ Retomando capítulo {resume_point.chapter_number}...")

    chapters, selected_source, manga_url, selected_manga = _load_chapters_with_fallback(
        service, selected_manga, selected_source, allow_source_change, progress
    )
    if not chapters:
        ui_bridge.show_warning("❌ Nenhum capítulo disponível")
        return

    sort_chapters_ascending(chapters)

    if resume_immediately and resume_point is not None:
        recommended = find_chapter_by_number(chapters, resume_point.chapter_number)
        if not recommended or not recommended.url:
            ui_bridge.show_warning(
                f"⚠️  Capítulo {resume_point.chapter_number} não disponível em "
                f"{selected_source}. Tentando outras fontes..."
            )
            fallback = resume_from_other_source(
                service,
                selected_manga,
                resume_point.chapter_number,
                selected_source,
                progress=progress,
            )
            if fallback:
                selected_source, manga_url, chapters, recommended, selected_manga = fallback
                manga_source_preferences.set_preferred_source(selected_manga.title, selected_source)

        if recommended and recommended.url:
            ui_bridge.show_info(
                f"✓ Capítulo {resume_point.chapter_number} encontrado em {selected_source}. "
                "Iniciando leitura..."
            )
            _process_chapter(
                service,
                selected_manga,
                recommended,
                manga_url,
                selected_source,
                history,
                chapters,
                [ch.display_name() for ch in chapters],
                chapters.index(recommended),
                menu,
                progress,
            )
            return
        ui_bridge.show_warning(
            f"⚠️  Capítulo {resume_point.chapter_number} não encontrado em nenhuma fonte. "
            "Mostrando lista completa..."
        )

    chapter_labels = [ch.display_name() for ch in chapters]
    if resume_point is not None and not resume_immediately:
        promote_resume_chapter(chapters, chapter_labels, resume_point)

    current_index = 0
    auto_load_next = False
    while True:
        if not auto_load_next:
            try:
                selected_label = menu(chapter_labels, "Selecione capítulo")
            except KeyboardInterrupt:
                return
            if not selected_label:
                return
            display_label = selected_label.replace("⮕ Retomar - ", "")
            current_index = next(
                (
                    i
                    for i, label in enumerate(chapter_labels)
                    if label.replace("⮕ Retomar - ", "") == display_label
                ),
                0,
            )

        auto_load_next = False
        selected_chapter = chapters[current_index]
        action = _show_chapter_action_menu(menu)
        if action is None:
            continue
        if action == "read":
            _process_chapter(
                service,
                selected_manga,
                selected_chapter,
                manga_url,
                selected_source,
                history,
                chapters,
                chapter_labels,
                current_index,
                menu,
                progress,
            )
        elif action == "download":
            handle_download_for_later(
                service,
                selected_manga,
                selected_chapter,
                manga_url,
                selected_source,
                history,
                chapters,
                menu=menu,
                progress=progress,
            )


def _show_chapter_action_menu(menu) -> str | None:
    selection = menu(
        [
            "📖 Ler Agora (Read Now)",
            "⬇️  Baixar para Depois (Download for Later)",
            "↩️  Voltar (Back)",
        ],
        "O que deseja fazer?",
    )
    if selection is None or selection == "↩️  Voltar (Back)":
        return None
    if "📖" in selection:
        return "read"
    if "⬇️" in selection:
        return "download"
    return None


def handle_download_for_later(
    service,
    selected_manga,
    selected_chapter,
    manga_url,
    selected_source,
    history,
    chapters: list | None = None,
    menu=ui_bridge.menu_navigate,
    progress=ui_bridge.loading,
    prompt=ui_bridge.prompt,
) -> None:
    """Download-for-later flow: menus here, batching in the download service."""
    from models.config import settings

    config = settings.manga

    if chapters is None:
        try:
            with progress(f"Carregando capítulos de {selected_source}..."):
                all_chapters = service.get_chapters(
                    selected_manga.id, manga_url=manga_url, source=selected_source
                )
        except Exception as e:
            ui_bridge.show_warning(f"❌ Erro ao carregar capítulos: {e}")
            return
        all_chapters.reverse()  # scraper returns descending
    else:
        all_chapters = chapters

    if not all_chapters:
        ui_bridge.show_warning("❌ Nenhum capítulo disponível")
        return

    chapters_to_download = prompt_download_range(
        history.get_last_chapter(selected_manga.title),
        all_chapters,
        default_count=config.default_download_range,
    )
    if not chapters_to_download:
        return

    tracker = DownloadedChaptersTracker()
    new_chapters, already_downloaded = split_new_and_downloaded(
        chapters_to_download, selected_manga.id, tracker
    )

    if already_downloaded and config.skip_already_downloaded:
        confirm = menu(
            ["✅ Sim, continuar", "❌ Cancelar", "🔄 Re-baixar todos"],
            f"{len(already_downloaded)} capítulo(s) já baixado(s). Continuar apenas com novos?",
        )
        if confirm == "❌ Cancelar":
            return
        if confirm == "🔄 Re-baixar todos":
            new_chapters = chapters_to_download

    if not new_chapters:
        ui_bridge.show_info(f"✓ Todos os {len(already_downloaded)} capítulo(s) já estão baixados")
        return

    logger.info(f"\n📥 Baixando {len(new_chapters)} capítulo(s)...")
    max_parallel = resolve_parallelism(config.max_parallel_downloads)

    if max_parallel == 1 or len(new_chapters) == 1:

        def _on_failure(_error_msg: str) -> bool:
            try:
                return (
                    menu(["✅ Continuar", "❌ Cancelar"], "Continuar com próximo capítulo?")
                    == "✅ Continuar"
                )
            except Exception:
                return False

        result = download_chapters_batch(
            new_chapters,
            service,
            selected_manga,
            manga_url,
            selected_source,
            config,
            tracker,
            max_parallel=1,
            on_failure=_on_failure,
        )
    else:
        logger.info(f"🚀 Usando {max_parallel} downloads paralelos...")
        from tqdm import tqdm

        with tqdm(total=len(new_chapters), desc="📥 Baixando capítulos", unit="cap") as pbar:

            def _on_progress(successful: int, failed: list[str]) -> None:
                pbar.set_postfix({"✅": successful, "❌": len(failed)}, refresh=False)
                pbar.update(1)

            result = download_chapters_batch(
                new_chapters,
                service,
                selected_manga,
                manga_url,
                selected_source,
                config,
                tracker,
                max_parallel=max_parallel,
                on_progress=_on_progress,
            )

    ui_bridge.show_info(f"✓ Download concluído: {result.successful} capítulo(s) baixados")
    if result.failed_chapters:
        ui_bridge.show_warning(
            f"⚠️  {len(result.failed_chapters)} capítulo(s) falharam: "
            f"{', '.join(result.failed_chapters)}"
        )
    prompt("Pressione Enter para voltar ao menu...")


def _prepare_chapter_pdf(selected_manga, selected_chapter, selected_source, service, progress):
    """Download images and build the chapter PDF. Returns pdf_path or None."""
    from models.config import settings

    config = settings.manga
    output_path = config.output_directory / selected_manga.title / selected_chapter.number
    output_path.mkdir(parents=True, exist_ok=True)
    pdf_path = output_path / f"{selected_chapter.number}.pdf"

    if pdf_path.exists():
        logger.info("📖 Abrindo capítulo existente...")
        return pdf_path

    try:
        with progress("Carregando páginas..."):
            pages = service.get_chapter_pages(
                selected_chapter.id, chapter_url=selected_chapter.url or "", source=selected_source
            )
    except MangaDexError as e:
        ui_bridge.show_warning(f"⚠️  {e.user_message}")
        return None
    except Exception as e:
        ui_bridge.show_warning(f"❌ Erro ao carregar páginas: {e}")
        return None

    if not pages:
        ui_bridge.show_warning("❌ Nenhuma página disponível para este capítulo")
        return None

    logger.info(f"Baixando {len(pages)} páginas...")
    try:
        download_images(pages, output_path, config)
        if not config.auto_create_pdf:
            ui_bridge.show_info(f"✓ Capítulo salvo em: {output_path}")
            return None
        logger.info("📄 Criando PDF...")
        create_pdf_from_images(output_path, pdf_path, quality=config.pdf_quality)
        if config.delete_images_after_pdf:
            for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                for img in output_path.glob(ext):
                    img.unlink()
            logger.info("🗑️  Imagens removidas (mantendo apenas PDF)")
        logger.info(f"✓ PDF criado: {pdf_path}")
        return pdf_path
    except Exception as e:
        ui_bridge.show_warning(f"❌ Erro ao processar capítulo: {e}")
        if output_path.exists():
            for f in output_path.glob("*"):
                f.unlink(missing_ok=True)
        return None


def _sync_read_to_anilist(selected_manga, selected_chapter, pdf_path, menu) -> None:
    """Confirm chapter completion and sync progress to AniList (interactive)."""
    from models.config import settings

    if not anilist_client.is_authenticated():
        return
    try:
        confirm = menu(
            ["✅ Sim, li até o final", "❌ Não, parei antes"],
            f"Você leu o capítulo {selected_chapter.number} até o final?",
        )
        if confirm != "✅ Sim, li até o final":
            ui_bridge.show_info("✓ Progresso não atualizado no AniList (capítulo não concluído)")
            return

        search_results = anilist_client.search_manga(selected_manga.title)
        if not search_results:
            ui_bridge.show_warning(f"⚠️  Mangá não encontrado no AniList: {selected_manga.title}")
            return

        best_match = search_results[0]
        list_entry = anilist_client.get_manga_list_entry(best_match.id)
        chapter_value = chapter_number_value(selected_chapter.number)
        chapter_num = int(chapter_value) if chapter_value is not None else 0
        if anilist_client.update_manga_progress(best_match.id, chapter_num):
            ui_bridge.show_info(
                f"✓ Progresso atualizado no AniList: {selected_manga.title} "
                f"- Cap. {selected_chapter.number}"
            )
            if not list_entry or list_entry.status == "PLANNING":
                anilist_client.change_manga_status(best_match.id, Status.CURRENT)
                ui_bridge.show_info("✓ Status alterado para: Lendo")
        else:
            ui_bridge.show_warning("⚠️  Falha ao atualizar progresso no AniList")

        if settings.manga.auto_delete_read_chapters and pdf_path and pdf_path.exists():
            try:
                import shutil

                shutil.rmtree(pdf_path.parent)
                ui_bridge.show_info(
                    "✓ Capítulo deletado automaticamente: economizando espaço em disco"
                )
            except Exception as e:
                ui_bridge.show_warning(f"⚠️  Não foi possível deletar capítulo automaticamente: {e}")
    except Exception as e:
        ui_bridge.show_warning(f"⚠️  Erro ao sincronizar com AniList: {e}")


def _process_chapter(
    service,
    selected_manga,
    selected_chapter,
    manga_url,
    selected_source,
    history,
    chapters,
    chapter_labels,
    current_index,
    menu,
    progress,
) -> None:
    """Process chapter reading, looping through next/previous/re-read navigation."""
    while True:
        pdf_path = _prepare_chapter_pdf(
            selected_manga, selected_chapter, selected_source, service, progress
        )
        if pdf_path is None:
            return

        open_pdf_reader(pdf_path)
        history.update(
            selected_manga.title,
            selected_chapter.number,
            chapter_id=selected_chapter.id,
            manga_id=selected_manga.id,
        )

        if is_zathura_running():
            ui_bridge.show_info("📖 Feche o Zathura para continuar.")
            while is_zathura_running():
                import time

                time.sleep(1)
            ui_bridge.show_info("✓ Zathura fechado. Continuando...")

        _sync_read_to_anilist(selected_manga, selected_chapter, pdf_path, menu)

        try:
            action = menu(
                ["Próximo", "Anterior", "Ler novamente", "Selecionar outro capítulo"],
                "O que deseja fazer?",
            )
        except KeyboardInterrupt:
            return

        if action is None or action in ("Sair", "Selecionar outro capítulo"):
            return

        if action == "Próximo":
            next_index = find_next_chapter_index(chapters, selected_chapter.number)
            if next_index is None:
                ui_bridge.show_info("Você chegou ao final dos capítulos disponíveis")
                return
            current_index = next_index
            chapter_labels[current_index] = chapter_labels[current_index].replace(
                "⮕ Retomar - ", ""
            )
        elif action == "Anterior":
            if current_index - 1 >= 0:
                current_index -= 1
                chapter_labels[current_index] = chapter_labels[current_index].replace(
                    "⮕ Retomar - ", ""
                )
            else:
                ui_bridge.show_info("Você está no primeiro capítulo")
        # "Ler novamente" re-reads the current chapter (no index change).

        selected_chapter = chapters[current_index]
