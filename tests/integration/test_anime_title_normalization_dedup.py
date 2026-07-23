"""Integration tests for anime title normalization and display.

Tests the normalization function which converts anime titles to a clean display format:
- Lowercase
- Letters and numbers only
- Separators normalized to spaces
- Accents removed
- PRESERVING: language markers, season information, all meaningful content
"""

import pytest
from services.repository import Repository


@pytest.fixture
def clean_repository():
    """Create a fresh repository for each test."""
    repo = Repository.__new__(Repository)
    repo.__init__()
    # Reset the singleton state for clean tests
    Repository._instance = repo
    Repository._initialized = True
    yield repo
    # Cleanup after test
    Repository._instance = None
    Repository._initialized = False


class TestSeparatorMerging:
    """Test that titles with different separators but same content merge."""

    def test_colon_dash_merge(self, clean_repository):
        """Anime with : and - separators should merge."""
        clean_repository.add_anime("Anime A: Title Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A - Title Dublado", "url2", "source2")

        # Should have only 1 entry (separators don't matter)
        titles = clean_repository.get_anime_titles()
        assert len(titles) == 1

        # Both sources should be listed
        sources_str = str(clean_repository.anime_to_urls[titles[0]])
        assert "source1" in sources_str
        assert "source2" in sources_str

    def test_multiple_separator_types_merge(self, clean_repository):
        """Multiple separator types with same content merge."""
        clean_repository.add_anime("Anime A: Title Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A - Title Dublado", "url2", "source2")
        clean_repository.add_anime("Anime A | Title Dublado", "url3", "source3")
        clean_repository.add_anime("Anime A / Title Dublado", "url4", "source4")

        titles = clean_repository.get_anime_titles()
        assert len(titles) == 1  # All merge to one
        assert len(clean_repository.anime_to_urls[titles[0]]) == 4  # All 4 sources


class TestLanguageMarkerPreservation:
    """Test that different language versions stay separate."""

    def test_dublado_vs_legendado_separate(self, clean_repository):
        """Dublado and Legendado versions are DIFFERENT."""
        clean_repository.add_anime("Anime A Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A Legendado", "url2", "source2")

        # Should have 2 SEPARATE entries
        titles = clean_repository.get_anime_titles()
        assert len(titles) == 2

    def test_with_separators_and_language(self, clean_repository):
        """Dubbed and subtitled with different separators still separate."""
        clean_repository.add_anime("Anime A: Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A - Legendado", "url2", "source2")

        titles = clean_repository.get_anime_titles()
        assert len(titles) == 2


class TestSeasonFormatPreservation:
    """Different explicit season wordings for the same season MERGE now."""

    def test_season_and_temporada_merge(self, clean_repository):
        clean_repository.add_anime("Anime A Season 2", "url1", "source1")
        clean_repository.add_anime("Anime A Temporada 2", "url2", "source2")
        assert len(clean_repository.get_anime_titles()) == 1

    def test_season_and_ordinal_merge(self, clean_repository):
        clean_repository.add_anime("Anime A Season 2", "url1", "source1")
        clean_repository.add_anime("Anime A 2nd Season", "url2", "source2")
        assert len(clean_repository.get_anime_titles()) == 1

    def test_bare_number_merges_with_temporada(self, clean_repository):
        clean_repository.add_anime("Anime A 3 Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A Temporada 3 Dublado", "url2", "source2")
        assert len(clean_repository.get_anime_titles()) == 1

    def test_different_seasons_stay_separate(self, clean_repository):
        clean_repository.add_anime("Anime A Temporada 2", "url1", "source1")
        clean_repository.add_anime("Anime A Temporada 3", "url2", "source2")
        assert len(clean_repository.get_anime_titles()) == 2

    def test_dub_and_sub_stay_separate(self, clean_repository):
        clean_repository.add_anime("Anime A Temporada 3 Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A Temporada 3 Legendado", "url2", "source2")
        assert len(clean_repository.get_anime_titles()) == 2


class TestExactMatches:
    """Test that exact duplicates still merge."""

    def test_exact_same_title_merges(self, clean_repository):
        """Exactly identical titles merge (backward compatibility)."""
        clean_repository.add_anime("Anime A", "url1", "source1")
        clean_repository.add_anime("Anime A", "url2", "source2")

        titles = clean_repository.get_anime_titles()
        assert len(titles) == 1
        assert len(clean_repository.anime_to_urls[titles[0]]) == 2

    def test_exact_with_language_markers(self, clean_repository):
        """Exact duplicates with language markers merge."""
        clean_repository.add_anime("Anime A Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A Dublado", "url2", "source2")

        titles = clean_repository.get_anime_titles()
        assert len(titles) == 1
        assert len(clean_repository.anime_to_urls[titles[0]]) == 2


class TestUnicodeNormalization:
    """Test that unicode accents are normalized for display."""

    def test_accented_titles_normalized(self, clean_repository):
        """Accented characters are normalized in display."""
        clean_repository.add_anime("Café Terça", "url1", "source1")
        clean_repository.add_anime("Cafe Terca", "url2", "source2")

        # Should merge (accents are equivalent after normalization)
        titles = clean_repository.get_anime_titles()
        assert len(titles) == 1


class TestComplexScenarios:
    """Test realistic complex scenarios."""

    def test_death_note_versions(self, clean_repository):
        """Real-world Death Note example with dubbed/subtitled versions."""
        clean_repository.add_anime("Death Note Dublado", "url1", "animesdigital")
        clean_repository.add_anime("Death Note Legendado", "url2", "animefire")

        # Should be 2 separate entries
        titles = clean_repository.get_anime_titles()
        assert len(titles) == 2

    def test_multiple_anime_multiple_sources(self, clean_repository):
        """Multiple different anime from multiple sources."""
        # Naruto
        clean_repository.add_anime("Naruto: Classic", "url1", "source1")
        clean_repository.add_anime("Naruto - Classic", "url2", "source2")

        # One Piece
        clean_repository.add_anime("One Piece Season 1", "url3", "source3")
        clean_repository.add_anime("One Piece Temporada 1", "url4", "source4")

        # "One Piece Season 1" and "One Piece Temporada 1" both normalize to
        # season None and now merge; the two Naruto entries also merge.
        assert len(clean_repository.get_anime_titles()) == 2


class TestNormTitlesMapping:
    """Test that norm_titles dictionary is correctly maintained."""

    def test_norm_titles_tracks_originals(self, clean_repository):
        """norm_titles maps original titles to normalized forms."""
        clean_repository.add_anime("Anime A: Title Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A - Title Dublado", "url2", "source2")

        # Both originals should be tracked
        assert "Anime A: Title Dublado" in clean_repository.norm_titles
        assert "Anime A - Title Dublado" in clean_repository.norm_titles

        # Both should map to same normalized form
        norm1 = clean_repository.norm_titles["Anime A: Title Dublado"]
        norm2 = clean_repository.norm_titles["Anime A - Title Dublado"]
        assert norm1 == norm2
        assert norm1 == "anime a title dublado"

    def test_norm_titles_preserves_language(self, clean_repository):
        """norm_titles preserves language markers."""
        clean_repository.add_anime("Anime A Dublado", "url1", "source1")
        clean_repository.add_anime("Anime A Legendado", "url2", "source2")

        norm1 = clean_repository.norm_titles["Anime A Dublado"]
        norm2 = clean_repository.norm_titles["Anime A Legendado"]

        # Should be different (language markers preserved)
        assert norm1 != norm2
        assert "dublado" in norm1
        assert "legendado" in norm2


class TestBackwardCompatibility:
    """Ensure basic functionality still works."""

    def test_simple_exact_titles(self, clean_repository):
        """Simple exact titles work as before."""
        clean_repository.add_anime("Title 1", "url1", "source1")
        clean_repository.add_anime("Title 2", "url2", "source2")

        titles = clean_repository.get_anime_titles()
        assert len(titles) == 2

    def test_episodes_association(self, clean_repository):
        """Episodes can be associated with merged anime."""
        clean_repository.add_anime("Anime A: Title", "url1", "source1")
        clean_repository.add_anime("Anime A - Title", "url2", "source2")

        titles = clean_repository.get_anime_titles()
        assert len(titles) == 1

        # Associate episodes
        title = titles[0]
        clean_repository.anime_episodes_numbers[title] = [1, 2]
        clean_repository.anime_episodes_urls[title] = ["ep1_url", "ep2_url"]

        assert len(clean_repository.anime_episodes_numbers[title]) == 2
