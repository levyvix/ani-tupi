"""Manga service modules.

Split from manga_tupi.py monolith for better maintainability.
"""

from services.manga.anilist_lists import handle_anilist_list
from services.manga.download import (
    BatchDownloadResult,
    download_chapter,
    download_chapters_batch,
    prompt_download_range,
    resolve_parallelism,
    split_new_and_downloaded,
)
from services.manga.reading_flow import (
    ResumePoint,
    build_manga_url,
    chapter_number_value,
    compute_resume_point,
    find_chapter_by_number,
    find_next_chapter_index,
    match_anilist_progress,
    promote_resume_chapter,
    sort_chapters_ascending,
)
from services.manga.source_selection import (
    research_manga_in_new_source,
    resume_from_other_source,
)

__all__ = [
    "handle_anilist_list",
    "download_chapter",
    "download_chapters_batch",
    "prompt_download_range",
    "BatchDownloadResult",
    "resolve_parallelism",
    "split_new_and_downloaded",
    "ResumePoint",
    "build_manga_url",
    "compute_resume_point",
    "chapter_number_value",
    "find_chapter_by_number",
    "find_next_chapter_index",
    "match_anilist_progress",
    "promote_resume_chapter",
    "sort_chapters_ascending",
    "research_manga_in_new_source",
    "resume_from_other_source",
]
