"""Tests for the H4 deduplication refactor.

Covers the three unifications:
1. Canonical title-filter normalization (public fn == SearchRepository delegate).
2. Manga URL templates unified into a single source.
3. (Range parser covered in tests/test_range_parser.py.)
"""

from utils.anilist_titles import format_title
from services.manga.reading_flow import _MANGA_URL_TEMPLATES, build_manga_url
from services.repository.search_repository import SearchRepository
from utils.title_utils import normalize_title_for_filter


class TestCanonicalFilterNormalization:
    """The public normalize_title_for_filter is the single implementation."""

    def test_private_delegate_matches_public(self):
        samples = [
            "Jujutsu--Kaisen: Season 2!",
            "Hell's Paradise: Jigokuraku",
            "Jujutsu Kaisen Season 2 Dublado",
            "Re:Zero (Dublado)",
            "  Multiple    Spaces  ",
            "Question? Mark. Dash-Here",
        ]
        for title in samples:
            assert SearchRepository._normalize_for_filter(title) == normalize_title_for_filter(
                title
            )

    def test_known_outputs_unchanged(self):
        """Golden outputs must remain identical to pre-refactor behavior."""
        assert normalize_title_for_filter("Jujutsu--Kaisen: Season 2!") == "jujutsu kaisen season 2"
        assert (
            normalize_title_for_filter("Jujutsu Kaisen Season 2 Dublado")
            == "jujutsu kaisen season 2 dublado"
        )
        assert (
            normalize_title_for_filter("Hell's Paradise: Jigokuraku")
            == "hell's paradise jigokuraku"
        )

    def test_formatter_still_uses_canonical_normalization(self):
        """format_title merges identical romaji/english after normalization."""
        # Romaji and english that normalize to the same string collapse to romaji only.
        result = format_title({"romaji": "Jujutsu Kaisen", "english": "Jujutsu-Kaisen"})
        assert result == "Jujutsu Kaisen"
        # Different titles are joined.
        result2 = format_title({"romaji": "Kimetsu no Yaiba", "english": "Demon Slayer"})
        assert result2 == "Kimetsu no Yaiba / Demon Slayer"


class TestUnifiedMangaUrlTemplates:
    """Both manga URL call paths must produce identical URLs per source."""

    def test_single_template_source(self):
        assert set(_MANGA_URL_TEMPLATES) == {"mugiwaras", "mangadex", "mangalivre"}

    def test_build_manga_url_matches_template_format(self):
        """build_manga_url (reading_flow) and the template dict produce the same URL."""
        for source, template in _MANGA_URL_TEMPLATES.items():
            expected = template.format("some-id")
            assert build_manga_url(source, "some-id") == expected

    def test_service_and_reading_flow_agree(self):
        """The unified service path builds URLs identical to build_manga_url."""
        # The service's _get_chapters_from_source uses build_manga_url internally.
        # Verify both known template sources produce the exact historical URLs.
        assert build_manga_url("mangadex", "uuid") == "https://mangadex.org/title/uuid"
        assert build_manga_url("mugiwaras", "abc") == "https://mugiwarasoficial.com/manga/abc/"
        assert build_manga_url("mangalivre", "xyz") == "https://mangalivre.blog/manga/xyz/"

    def test_unknown_source_returns_none(self):
        assert build_manga_url("nonexistent", "id") is None
