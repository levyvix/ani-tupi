"""Tests for AniListDiscoveryService - TDD approach.

Tests are written BEFORE implementation following the TDD cycle:
1. RED - Write failing tests
2. GREEN - Implement minimal code to pass
3. REFACTOR - Improve code quality
"""

from unittest.mock import patch
import pytest

from models.models import AniListAnime, AniListSearchResult, AniListTitle


class TestAniListDiscoveryResult:
    """Tests for the immutable AniListDiscoveryResult dataclass."""

    def test_result_is_frozen_dataclass(self):
        """AniListDiscoveryResult should be immutable (frozen)."""
        from services.anilist.discovery import AniListDiscoveryResult

        result = AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=False,
        )

        # Should raise error when trying to modify
        with pytest.raises(AttributeError):
            result.found = True

    def test_result_with_all_fields_populated(self):
        """Should create result with all fields populated."""
        from services.anilist.discovery import AniListDiscoveryResult

        result = AniListDiscoveryResult(
            anilist_id=12345,
            anilist_title="Dandadan",
            total_episodes=12,
            found=True,
            authenticated=True,
        )

        assert result.anilist_id == 12345
        assert result.anilist_title == "Dandadan"
        assert result.total_episodes == 12
        assert result.found is True
        assert result.authenticated is True

    def test_result_not_found_case(self):
        """Should create result for not found case."""
        from services.anilist.discovery import AniListDiscoveryResult

        result = AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=True,
        )

        assert result.anilist_id is None
        assert result.anilist_title is None
        assert result.total_episodes is None
        assert result.found is False
        assert result.authenticated is True


class TestDiscoverAnilistInfo:
    """Tests for discover_anilist_info function."""

    @patch("services.anilist.discovery.anilist_client")
    def test_not_authenticated_returns_empty_result(self, mock_anilist):
        """When not authenticated, should return result with authenticated=False."""
        from services.anilist.discovery import discover_anilist_info

        # Setup: AniList not authenticated
        mock_anilist.is_authenticated.return_value = False

        # Execute
        result = discover_anilist_info("Dandadan")

        # Verify
        assert result.authenticated is False
        assert result.found is False
        assert result.anilist_id is None
        assert result.anilist_title is None
        assert result.total_episodes is None

    @patch("services.anilist.discovery.normalize_title_for_search")
    @patch("services.anilist.discovery.auto_discover_anilist_id")
    @patch("services.anilist.discovery.anilist_client")
    def test_authenticated_no_match_found(self, mock_anilist, mock_auto_discover, mock_normalize):
        """When authenticated but no match found, return found=False."""
        from services.anilist.discovery import discover_anilist_info

        # Setup
        mock_anilist.is_authenticated.return_value = True
        mock_normalize.return_value = "nonexistent anime"
        mock_auto_discover.return_value = []  # Empty results

        # Execute
        result = discover_anilist_info("Nonexistent Anime (Dublado)")

        # Verify
        assert result.authenticated is True
        assert result.found is False
        assert result.anilist_id is None
        assert result.anilist_title is None
        mock_normalize.assert_called_once_with("Nonexistent Anime (Dublado)")

    @patch("services.anilist.discovery.get_anilist_metadata")
    @patch("services.anilist.discovery.normalize_title_for_search")
    @patch("services.anilist.discovery.auto_discover_anilist_id")
    @patch("services.anilist.discovery.anilist_client")
    def test_authenticated_successful_discovery(
        self, mock_anilist, mock_auto_discover, mock_normalize, mock_get_metadata
    ):
        """Successful discovery returns complete result with title normalization."""
        from services.anilist.discovery import discover_anilist_info

        # Setup: Authenticated, title normalization, and metadata retrieval
        mock_anilist.is_authenticated.return_value = True
        mock_normalize.return_value = "dandadan"
        mock_auto_discover.return_value = [
            AniListSearchResult(anilist_id=12345, score=95, title="Dandadan")
        ]
        mock_get_metadata.return_value = AniListAnime(
            id=12345,
            title=AniListTitle(romaji="Dandadan", english="Dandadan", native=None),
            episodes=12,
            averageScore=85,
            seasonYear=2024,
            season="FALL",
            type="ANIME",
        )
        mock_anilist.format_title.return_value = "Dandadan"

        # Execute with title containing suffix (tests normalization)
        result = discover_anilist_info("dandadan (Dublado)")

        # Verify
        assert result.authenticated is True
        assert result.found is True
        assert result.anilist_id == 12345
        assert result.anilist_title == "Dandadan"
        assert result.total_episodes == 12
        # Verify normalization was called with original title
        mock_normalize.assert_called_once_with("dandadan (Dublado)")
        # Verify auto_discover was called with normalized title
        mock_auto_discover.assert_called_once_with("dandadan")

    @patch("services.anilist.discovery.get_anilist_metadata")
    @patch("services.anilist.discovery.normalize_title_for_search")
    @patch("services.anilist.discovery.auto_discover_anilist_id")
    @patch("services.anilist.discovery.anilist_client")
    def test_error_handling_graceful_degradation(
        self, mock_anilist, mock_auto_discover, mock_normalize, mock_get_metadata
    ):
        """Test graceful error handling in various failure scenarios."""
        from services.anilist.discovery import discover_anilist_info

        # Scenario 1: API discovery fails - return no match
        mock_anilist.is_authenticated.return_value = True
        mock_normalize.return_value = "dandadan"
        mock_auto_discover.side_effect = TypeError("Network error")
        result = discover_anilist_info("Dandadan")
        assert result.authenticated is True
        assert result.found is False
        assert result.anilist_id is None

        # Scenario 2: Discovery succeeds but metadata fetch fails - return partial result
        mock_auto_discover.side_effect = None
        mock_auto_discover.return_value = [
            AniListSearchResult(anilist_id=12345, score=95, title="Dandadan")
        ]
        mock_get_metadata.side_effect = TypeError("Metadata fetch failed")
        result = discover_anilist_info("Dandadan")
        assert result.authenticated is True
        assert result.found is True
        assert result.anilist_id == 12345
        assert result.anilist_title is None
        assert result.total_episodes is None

        # Scenario 3: Discovery succeeds but metadata returns None - return partial result
        mock_get_metadata.side_effect = None
        mock_get_metadata.return_value = None
        result = discover_anilist_info("Dandadan")
        assert result.authenticated is True
        assert result.found is True
        assert result.anilist_id == 12345
        assert result.anilist_title is None
        assert result.total_episodes is None

    @patch("services.anilist.discovery.get_anilist_metadata")
    @patch("services.anilist.discovery.normalize_title_for_search")
    @patch("services.anilist.discovery.auto_discover_anilist_id")
    @patch("services.anilist.discovery.anilist_client")
    def test_anime_with_unknown_episode_count(
        self, mock_anilist, mock_auto_discover, mock_normalize, mock_get_metadata
    ):
        """When anime episodes count is unknown (None), result should have None."""
        from services.anilist.discovery import discover_anilist_info

        # Setup: Ongoing anime with unknown episode count
        mock_anilist.is_authenticated.return_value = True
        mock_normalize.return_value = "one piece"
        mock_auto_discover.return_value = [
            AniListSearchResult(anilist_id=21, score=95, title="One Piece")
        ]
        mock_get_metadata.return_value = AniListAnime(
            id=21,
            title=AniListTitle(romaji="One Piece", english="One Piece", native=None),
            episodes=None,  # Unknown for ongoing series
            averageScore=87,
            seasonYear=1999,
            season="FALL",
            type="ANIME",
        )
        mock_anilist.format_title.return_value = "One Piece"

        # Execute
        result = discover_anilist_info("One Piece")

        # Verify
        assert result.found is True
        assert result.anilist_id == 21
        assert result.anilist_title == "One Piece"
        assert result.total_episodes is None

    @patch("services.anilist.discovery.normalize_title_for_search")
    @patch("services.anilist.discovery.anilist_client")
    def test_empty_title_returns_not_found(self, mock_anilist, mock_normalize):
        """When title is empty after normalization, should return not found."""
        from services.anilist.discovery import discover_anilist_info

        # Setup: Title normalizes to empty string
        mock_anilist.is_authenticated.return_value = True
        mock_normalize.return_value = ""

        # Execute
        result = discover_anilist_info("(Dublado)")

        # Verify - should not attempt search with empty title
        assert result.authenticated is True
        assert result.found is False
        assert result.anilist_id is None
