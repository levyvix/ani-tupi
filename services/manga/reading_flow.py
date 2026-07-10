"""Manga reading-flow service (UI-free business logic).

Extracted from manga_tupi.py. Holds the pure logic that decides *what* to read:

- building per-source manga URLs,
- sorting chapters ascending,
- locating a chapter by its integer number,
- computing the recommended "resume" chapter from AniList / local history,
- moving the resume chapter to the top of a display list.

Everything here is side-effect free and returns immutable data so it can be
unit-tested without a terminal. Menus and prompts stay in the command layer.
"""

from dataclasses import dataclass

from models.models import ChapterData
from utils.logging import get_logger

logger = get_logger(__name__)

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


def _chapter_sort_value(chapter: ChapterData) -> float:
    """Numeric sort key for a chapter, tolerant of commas and junk."""
    normalized = str(chapter.number).replace(",", ".")
    stripped = normalized.replace("-", "").replace(".", "")
    return float(normalized) if stripped.isdigit() else 0.0


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
        try:
            if int(float(chapter.number)) == number:
                return chapter
        except (ValueError, TypeError):
            continue
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
        try:
            return ResumePoint(chapter_number=int(float(last_local_chapter)) + 1, source="local")
        except (ValueError, TypeError):
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
        try:
            if int(float(chapter.number)) == resume_point.chapter_number:
                recommended_index = i
                break
        except (ValueError, TypeError):
            continue

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
    current_value = float(current_number)
    for i, chapter in enumerate(chapters):
        if float(chapter.number) > current_value:
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
