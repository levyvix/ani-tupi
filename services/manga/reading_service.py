# ruff: noqa: F822
# pyright: reportUnsupportedDunderAll=false

"""Compatibility facade for manga reading service imports."""

import sys

from services.manga import reading_flow as implementation

__all__ = [
    "MANGA_URL_TEMPLATES",
    "ResumePoint",
    "build_manga_url",
    "chapter_number_value",
    "compute_resume_point",
    "find_chapter_by_number",
    "find_next_chapter_index",
    "match_anilist_progress",
    "promote_resume_chapter",
    "sort_chapters_ascending",
    "MangaSelectionPreferences",
    "MangaSourcePreferences",
    "manga_selection_preferences",
    "manga_source_preferences",
    "research_manga_in_new_source",
    "resume_from_other_source",
    "continue_manga_flow",
    "handle_download_for_later",
    "start_manga_search",
]
sys.modules[__name__] = implementation
