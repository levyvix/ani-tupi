"""Additional coverage tests for services/anilist/formatters.py.

Targets previously uncovered lines:
- format_title: only-english path (line ~42-43), only-native fallback (line ~44-45)
- get_search_title: all branches via both AniListTitle model and dict inputs

Do NOT overwrite tests/unit/services/anilist/test_formatters.py — this file adds more cases.
"""

from models.models import AniListTitle
from services.anilist.formatters import format_title, get_search_title


# ---------------------------------------------------------------------------
# format_title – uncovered branches
# ---------------------------------------------------------------------------


class TestFormatTitleUncoveredBranches:
    def test_only_english_returns_english(self):
        """When only english is set (no romaji), returns english."""
        title = AniListTitle(romaji=None, english="My Hero Academia", native=None)
        assert format_title(title) == "My Hero Academia"

    def test_only_native_returns_native(self):
        """When only native is set, returns native."""
        title = AniListTitle(romaji=None, english=None, native="僕のヒーローアカデミア")
        assert format_title(title) == "僕のヒーローアカデミア"

    def test_all_none_returns_unknown(self):
        """When all title fields are None, returns 'Unknown'."""
        title = AniListTitle(romaji=None, english=None, native=None)
        assert format_title(title) == "Unknown"

    def test_dict_only_english(self):
        """Dict input with only english returns english."""
        assert format_title({"english": "Attack on Titan"}) == "Attack on Titan"

    def test_dict_only_native(self):
        """Dict input with only native returns native."""
        assert format_title({"native": "進撃の巨人"}) == "進撃の巨人"

    def test_dict_all_none_returns_unknown(self):
        """Dict input with all None returns 'Unknown'."""
        assert format_title({}) == "Unknown"


# ---------------------------------------------------------------------------
# get_search_title – all branches
# ---------------------------------------------------------------------------


class TestGetSearchTitle:
    def test_english_preferred_when_present(self):
        """Returns english title when available."""
        title = AniListTitle(romaji="Shingeki no Kyojin", english="Attack on Titan")
        assert get_search_title(title) == "Attack on Titan"

    def test_falls_back_to_romaji_when_no_english(self):
        """Returns romaji when english is absent."""
        title = AniListTitle(romaji="Shingeki no Kyojin", english=None)
        assert get_search_title(title) == "Shingeki no Kyojin"

    def test_falls_back_to_native_when_no_english_or_romaji(self):
        """Returns native when both english and romaji are absent."""
        title = AniListTitle(romaji=None, english=None, native="進撃の巨人")
        assert get_search_title(title) == "進撃の巨人"

    def test_returns_unknown_when_all_none(self):
        """Returns 'Unknown' when all fields are None."""
        title = AniListTitle(romaji=None, english=None, native=None)
        assert get_search_title(title) == "Unknown"

    def test_dict_english_preferred(self):
        """Dict input: english is preferred."""
        assert get_search_title({"english": "One Piece", "romaji": "One Piece"}) == "One Piece"

    def test_dict_falls_back_to_romaji(self):
        """Dict input: romaji when english absent."""
        assert get_search_title({"romaji": "One Piece", "english": None}) == "One Piece"

    def test_dict_falls_back_to_native(self):
        """Dict input: native when both english and romaji absent."""
        assert get_search_title({"native": "ワンピース"}) == "ワンピース"

    def test_dict_all_missing_returns_unknown(self):
        """Dict input: all absent returns 'Unknown'."""
        assert get_search_title({}) == "Unknown"
