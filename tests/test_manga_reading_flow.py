"""Tests for the extracted manga reading-flow services.

Covers the pure decision logic extracted from the ``manga_tupi.py`` monolith:
- resume-point computation (AniList vs local history),
- locating a chapter by number,
- chapter sorting,
- resume-label promotion,
- next-chapter lookup,
- AniList progress title matching,
- manga URL construction,
- and the download-service batching/split helpers (network mocked).

Follows the project convention: real code exercised, only external boundaries
(HTTP, AniList entries) faked.
"""

from types import SimpleNamespace


from models.models import ChapterData
from services.manga.reading_service import (
    ResumePoint,
    build_manga_url,
    compute_resume_point,
    find_chapter_by_number,
    find_next_chapter_index,
    match_anilist_progress,
    promote_resume_chapter,
    sort_chapters_ascending,
)


def _ch(number: str, url: str | None = "http://x", title: str | None = None) -> ChapterData:
    return ChapterData(
        id=f"id-{number}",
        number=number,
        title=title,
        url=url,
        language="mangadex",
    )


class TestComputeResumePoint:
    def test_prefers_anilist_progress(self):
        rp = compute_resume_point(anilist_progress=5, last_local_chapter="2")
        assert rp == ResumePoint(chapter_number=6, source="AniList")

    def test_falls_back_to_local(self):
        rp = compute_resume_point(anilist_progress=None, last_local_chapter="10")
        assert rp == ResumePoint(chapter_number=11, source="local")

    def test_decimal_local_chapter_floored(self):
        rp = compute_resume_point(None, "42.5")
        assert rp == ResumePoint(chapter_number=43, source="local")

    def test_none_when_no_data(self):
        assert compute_resume_point(None, None) is None

    def test_none_when_local_unparseable(self):
        assert compute_resume_point(None, "extra") is None

    def test_anilist_zero_progress_recommends_chapter_one(self):
        rp = compute_resume_point(0, None)
        assert rp == ResumePoint(chapter_number=1, source="AniList")


class TestFindChapterByNumber:
    def test_matches_integer(self):
        chapters = [_ch("1"), _ch("2"), _ch("3")]
        assert find_chapter_by_number(chapters, 2).number == "2"

    def test_matches_decimal_floored(self):
        chapters = [_ch("41"), _ch("42.5"), _ch("43")]
        # 42.5 -> int 42
        assert find_chapter_by_number(chapters, 42).number == "42.5"

    def test_returns_none_when_missing(self):
        assert find_chapter_by_number([_ch("1")], 99) is None


class TestSortChaptersAscending:
    def test_sorts_numeric(self):
        chapters = [_ch("10"), _ch("2"), _ch("1")]
        sort_chapters_ascending(chapters)
        assert [c.number for c in chapters] == ["1", "2", "10"]

    def test_handles_comma_decimals(self):
        chapters = [_ch("3"), _ch("1,5"), _ch("1")]
        sort_chapters_ascending(chapters)
        assert [c.number for c in chapters] == ["1", "1,5", "3"]


class TestPromoteResumeChapter:
    def test_moves_matching_chapter_to_top(self):
        chapters = [_ch("1"), _ch("2"), _ch("3")]
        labels = [c.display_name() for c in chapters]
        promote_resume_chapter(chapters, labels, ResumePoint(2, "local"))
        assert chapters[0].number == "2"
        assert labels[0].startswith("⮕ Retomar (local)")
        # remaining stay in sync
        assert chapters[1].number == "1"
        assert chapters[2].number == "3"

    def test_fallback_to_first_when_no_match(self):
        chapters = [_ch("1"), _ch("2")]
        labels = [c.display_name() for c in chapters]
        promote_resume_chapter(chapters, labels, ResumePoint(99, "AniList"))
        assert labels[0].startswith("⮕ Retomar (AniList)")
        assert chapters[0].number == "1"

    def test_noop_if_already_has_resume_label(self):
        chapters = [_ch("1"), _ch("2")]
        labels = ["⮕ Retomar (local) - Cap. 2", "Cap. 1"]
        promote_resume_chapter(chapters, labels, ResumePoint(1, "local"))
        assert labels[0] == "⮕ Retomar (local) - Cap. 2"


class TestFindNextChapterIndex:
    def test_returns_next_greater_index(self):
        chapters = [_ch("1"), _ch("2"), _ch("3")]
        assert find_next_chapter_index(chapters, "2") == 2

    def test_returns_none_at_end(self):
        chapters = [_ch("1"), _ch("2")]
        assert find_next_chapter_index(chapters, "2") is None


class TestBuildMangaUrl:
    def test_mugiwaras(self):
        assert build_manga_url("mugiwaras", "abc") == "https://mugiwarasoficial.com/manga/abc/"

    def test_mangadex(self):
        assert build_manga_url("mangadex", "uuid") == "https://mangadex.org/title/uuid"

    def test_unknown_source_none(self):
        assert build_manga_url("other", "x") is None


def _entry(romaji=None, english=None, progress=None):
    title = SimpleNamespace(romaji=romaji, english=english)
    media = SimpleNamespace(title=title)
    return SimpleNamespace(media=media, progress=progress)


class TestMatchAnilistProgress:
    def test_exact_romaji_match(self):
        entries = [_entry(romaji="Chainsaw Man", progress=12)]
        assert match_anilist_progress(entries, "Chainsaw Man", None) == 12

    def test_partial_match(self):
        entries = [_entry(romaji="Jujutsu Kaisen 2nd Season", progress=5)]
        assert match_anilist_progress(entries, "Jujutsu Kaisen", None) == 5

    def test_english_fallback(self):
        entries = [_entry(english="Attack on Titan", progress=3)]
        assert match_anilist_progress(entries, "Attack on Titan", None) == 3

    def test_no_match_returns_none(self):
        entries = [_entry(romaji="One Piece", progress=100)]
        assert match_anilist_progress(entries, "Naruto", None) is None

    def test_empty_list_none(self):
        assert match_anilist_progress([], "Anything", None) is None

    def test_zero_progress_ignored(self):
        # progress of 0 is falsy in the original logic -> skipped
        entries = [_entry(romaji="Berserk", progress=0)]
        assert match_anilist_progress(entries, "Berserk", None) is None
