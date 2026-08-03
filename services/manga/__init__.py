"""Manga package - one module per service.

- ``manga_service``: multi-source manga service, history, AniList lists
- ``reading_service``: reading flow, preferences, source choice, orchestration
- ``download_service``: chapter download and batching
- ``local_manga_service``: locally stored manga
"""

from services.manga.download_service import (
    BatchDownloadResult,
    download_chapter,
    download_chapters_batch,
    prompt_download_range,
    resolve_parallelism,
    split_new_and_downloaded,
)
from services.manga.manga_service import handle_anilist_list
from services.manga.reading_service import (
    ResumePoint,
    build_manga_url,
    chapter_number_value,
    compute_resume_point,
    find_chapter_by_number,
    find_next_chapter_index,
    match_anilist_progress,
    promote_resume_chapter,
    research_manga_in_new_source,
    resume_from_other_source,
    sort_chapters_ascending,
)

__all__ = [
    "BatchDownloadResult",
    "ResumePoint",
    "build_manga_url",
    "chapter_number_value",
    "compute_resume_point",
    "download_chapter",
    "download_chapters_batch",
    "find_chapter_by_number",
    "find_next_chapter_index",
    "handle_anilist_list",
    "match_anilist_progress",
    "promote_resume_chapter",
    "prompt_download_range",
    "research_manga_in_new_source",
    "resolve_parallelism",
    "resume_from_other_source",
    "sort_chapters_ascending",
    "split_new_and_downloaded",
]
