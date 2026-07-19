"""Tests for PlaybackService - TDD approach.

Tests are written BEFORE implementation following the TDD cycle:
1. RED - Write failing tests
2. GREEN - Implement minimal code to pass
3. REFACTOR - Improve code quality

This service orchestrates the full playback flow including:
- Preparing playback context from search or history
- Getting episode URLs
- Syncing progress to AniList
- Episode navigation
"""

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch
import pytest

from services.anilist.discovery import AniListDiscoveryResult


# =============================================================================
# Step 1: Test Immutable Data Types
# =============================================================================


class TestPlaybackContextDataclass:
    """Tests for the immutable PlaybackContext dataclass."""

    def test_dataclass_is_frozen(self):
        """PlaybackContext should be immutable (frozen)."""
        from services.anime.playback_service import PlaybackContext

        ctx = PlaybackContext(
            anime_title="Dandadan",
            episode_idx=0,
            source=None,
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=12,
            episode_list=("Episodio 1", "Episodio 2"),
        )

        # Should raise error when trying to modify
        with pytest.raises(FrozenInstanceError):
            ctx.episode_idx = 1

    def test_dataclass_with_all_fields_populated(self):
        """Should create context with all fields populated."""
        from services.anime.playback_service import PlaybackContext

        ctx = PlaybackContext(
            anime_title="Dandadan",
            episode_idx=5,
            source="animefire",
            anilist_id=12345,
            anilist_title="Dandadan",
            total_episodes_anilist=24,
            num_episodes=24,
            episode_list=tuple(f"Episodio {i}" for i in range(1, 25)),
        )

        assert ctx.anime_title == "Dandadan"
        assert ctx.episode_idx == 5
        assert ctx.source == "animefire"
        assert ctx.anilist_id == 12345
        assert ctx.anilist_title == "Dandadan"
        assert ctx.total_episodes_anilist == 24
        assert ctx.num_episodes == 24
        assert len(ctx.episode_list) == 24

    def test_dataclass_with_optional_fields_none(self):
        """Should create context with optional fields as None."""
        from services.anime.playback_service import PlaybackContext

        ctx = PlaybackContext(
            anime_title="Test Anime",
            episode_idx=0,
            source=None,
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=12,
            episode_list=(),
        )

        assert ctx.source is None
        assert ctx.anilist_id is None
        assert ctx.anilist_title is None
        assert ctx.total_episodes_anilist is None


class TestEpisodePlaybackResultDataclass:
    """Tests for the immutable EpisodePlaybackResult dataclass."""

    def test_dataclass_is_frozen(self):
        """EpisodePlaybackResult should be immutable (frozen)."""
        from services.anime.playback_service import EpisodePlaybackResult

        result = EpisodePlaybackResult(
            player_url="https://example.com/video.mp4",
            source="animefire",
            success=True,
            error_message=None,
        )

        # Should raise error when trying to modify
        with pytest.raises(FrozenInstanceError):
            result.success = False

    def test_successful_result(self):
        """Should create a successful result with URL and source."""
        from services.anime.playback_service import EpisodePlaybackResult

        result = EpisodePlaybackResult(
            player_url="https://example.com/video.mp4",
            source="animefire",
            success=True,
            error_message=None,
        )

        assert result.player_url == "https://example.com/video.mp4"
        assert result.source == "animefire"
        assert result.success is True
        assert result.error_message is None

    def test_failed_result(self):
        """Should create a failed result with error message."""
        from services.anime.playback_service import EpisodePlaybackResult

        result = EpisodePlaybackResult(
            player_url=None,
            source=None,
            success=False,
            error_message="No video source found",
        )

        assert result.player_url is None
        assert result.source is None
        assert result.success is False
        assert result.error_message == "No video source found"


# =============================================================================
# Step 2: Tests for prepare_playback_from_search()
# =============================================================================


class TestPreparePlaybackFromSearch:
    """Tests for prepare_playback_from_search function."""

    @patch("services.anime.playback_service.rep")
    @patch("services.anime.playback_service.discover_anilist_info")
    def test_basic_search_result(self, mock_discover, mock_rep):
        """Test 1: Basic Search Result.

        Input: args, selected_anime="Dandadan", episode_idx=0, source="animefire"
        Expected: Returns PlaybackContext with all fields populated
        Verify: discover_anilist_info() is called to populate anilist_id, anilist_title
        """
        from services.anime.playback_service import prepare_playback_from_search

        # Setup mocks
        mock_discover.return_value = AniListDiscoveryResult(
            anilist_id=12345,
            anilist_title="Dandadan",
            total_episodes=12,
            found=True,
            authenticated=True,
        )
        mock_rep.get_episode_list.return_value = [
            "Episodio 1",
            "Episodio 2",
            "Episodio 3",
        ]

        # Execute
        result = prepare_playback_from_search(
            selected_anime="Dandadan",
            episode_idx=0,
            source="animefire",
        )

        # Verify
        assert result is not None
        assert result.anime_title == "Dandadan"
        assert result.episode_idx == 0
        assert result.source == "animefire"
        assert result.anilist_id == 12345
        assert result.anilist_title == "Dandadan"
        assert result.total_episodes_anilist == 12
        assert result.num_episodes == 3
        assert result.episode_list == ("Episodio 1", "Episodio 2", "Episodio 3")

        # Verify discover was called
        mock_discover.assert_called_once_with("Dandadan")

    @patch("services.anime.playback_service.rep")
    @patch("services.anime.playback_service.discover_anilist_info")
    def test_search_without_anilist_authentication(self, mock_discover, mock_rep):
        """Test 2: Search Without AniList Authentication.

        Input: AniList not authenticated
        Expected: PlaybackContext with anilist_id=None, anilist_title=None
        """
        from services.anime.playback_service import prepare_playback_from_search

        # Setup: AniList not authenticated
        mock_discover.return_value = AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=False,
        )
        mock_rep.get_episode_list.return_value = ["Ep 1", "Ep 2"]

        # Execute
        result = prepare_playback_from_search(
            selected_anime="Dandadan",
            episode_idx=0,
            source="animefire",
        )

        # Verify
        assert result is not None
        assert result.anilist_id is None
        assert result.anilist_title is None
        assert result.total_episodes_anilist is None

    @patch("services.anime.playback_service.rep")
    @patch("services.anime.playback_service.discover_anilist_info")
    def test_search_with_episode_list_and_counts(self, mock_discover, mock_rep):
        """Test episode list retrieval and mixed episode count scenarios."""
        from services.anime.playback_service import prepare_playback_from_search

        # Scenario 1: Episode list from repository (24 episodes)
        mock_discover.return_value = AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=True,
        )
        mock_rep.get_episode_list.return_value = [f"Episodio {i}" for i in range(1, 25)]
        result = prepare_playback_from_search(
            selected_anime="Test Anime",
            episode_idx=5,
            source="animesdigital",
        )
        assert result.num_episodes == 24
        assert len(result.episode_list) == 24
        assert result.episode_list[0] == "Episodio 1"

        # Scenario 2: Mixed counts - scraper has 24, AniList has 25
        mock_discover.return_value = AniListDiscoveryResult(
            anilist_id=12345,
            anilist_title="Some Anime",
            total_episodes=25,  # AniList says 25
            found=True,
            authenticated=True,
        )
        mock_rep.get_episode_list.return_value = [f"Ep {i}" for i in range(1, 25)]  # 24 episodes
        result = prepare_playback_from_search(
            selected_anime="Some Anime",
            episode_idx=0,
            source="animefire",
        )
        assert result.num_episodes == 24  # From scraper
        assert result.total_episodes_anilist == 25  # From AniList


# =============================================================================
# Step 3: Tests for prepare_playback_from_history()
# =============================================================================


class TestPreparePlaybackFromHistory:
    """Tests for prepare_playback_from_history function."""

    @patch("services.anime.playback_service.rep")
    @patch("services.anime.playback_service.discover_anilist_info")
    @patch("services.anime.playback_service.load_history")
    def test_load_from_history_success(self, mock_load_history, mock_discover, mock_rep):
        """Load history with and without AniList enrichment."""
        from services.anime.playback_service import prepare_playback_from_history

        # Scenario 1: Basic history load without AniList
        mock_load_history.return_value = ("Dandadan", 5, 12345, "Dandadan")
        mock_discover.return_value = AniListDiscoveryResult(
            anilist_id=12345,
            anilist_title="Dandadan",
            total_episodes=12,
            found=True,
            authenticated=True,
        )
        mock_rep.get_episode_list.return_value = [f"Ep {i}" for i in range(1, 13)]

        result = prepare_playback_from_history()
        assert result is not None
        assert result.anime_title == "Dandadan"
        assert result.episode_idx == 5
        assert result.anilist_id == 12345

        # Scenario 2: History with AniList enrichment
        mock_load_history.return_value = ("Test Anime", 3, 99999, "Test Anime (Romaji)")
        mock_discover.return_value = AniListDiscoveryResult(
            anilist_id=99999,
            anilist_title="Test Anime (Romaji)",
            total_episodes=24,
            found=True,
            authenticated=True,
        )
        mock_rep.get_episode_list.return_value = [f"Ep {i}" for i in range(1, 25)]

        result = prepare_playback_from_history()
        assert result.anilist_id == 99999
        assert result.anilist_title == "Test Anime (Romaji)"
        assert result.total_episodes_anilist == 24

    @patch("services.anime.playback_service.load_history")
    def test_history_load_failure(self, mock_load_history):
        """Test history load failure returns None."""
        from services.anime.playback_service import prepare_playback_from_history

        mock_load_history.return_value = None
        result = prepare_playback_from_history()
        assert result is None


# =============================================================================
# Step 4: Tests for get_episode_url_and_source()
# =============================================================================


class TestGetEpisodeUrlAndSource:
    """Tests for get_episode_url_and_source function."""

    @patch("services.anime.playback_service.rep")
    def test_successful_video_url_extraction(self, mock_rep):
        """Test 8: Successful Video URL Extraction.

        Input: anime_title="Dandadan", episode=5
        Expected: Returns EpisodePlaybackResult with player_url and source
        Verify: Uses rep.search_player() to get URL
        """
        from services.anime.playback_service import get_episode_url_and_source

        # Setup
        mock_rep.search_player.return_value = "https://video.example.com/ep5.mp4"
        mock_rep.get_episode_url_and_source.return_value = (
            "https://page.example.com/ep5",
            "animefire",
        )

        # Execute
        result = get_episode_url_and_source("Dandadan", 5)

        # Verify
        assert result.success is True
        assert result.player_url == "https://video.example.com/ep5.mp4"
        assert result.source == "animefire"
        assert result.error_message is None

        # Verify search_player was called
        mock_rep.search_player.assert_called_once_with("Dandadan", 5)

    @patch("services.anime.playback_service.rep")
    def test_video_lookup_failure_scenarios(self, mock_rep):
        """Test failure scenarios: no video found and API errors."""
        from services.anime.playback_service import get_episode_url_and_source

        # Scenario 1: No video found
        mock_rep.search_player.return_value = None
        mock_rep.get_episode_url_and_source.return_value = None
        result = get_episode_url_and_source("Dandadan", 5)
        assert result.success is False
        assert result.player_url is None
        assert result.error_message is not None

        # Scenario 2: API error during lookup
        mock_rep.search_player.side_effect = ValueError("Network error")
        result = get_episode_url_and_source("Dandadan", 5)
        assert result.success is False
        assert result.player_url is None
        assert result.error_message is not None


class TestEpisodeUrlPatternFallback:
    """Task 4.4 — when URL pattern validation fails, scraping runs normally."""

    @patch("services.anime.playback_service.rep")
    def test_falls_back_to_scraping_when_pattern_miss(self, mock_rep):
        """When derived URL returns 404, scraping is still called."""
        from unittest.mock import patch as _patch
        from services.anime.playback_service import get_episode_url_and_source

        mock_rep.search_player.return_value = "https://scraper.example.com/ep12.mp4"
        mock_rep.get_episode_url_and_source.return_value = (
            "https://page.example.com/ep12",
            "animefire",
        )

        current_url = "https://cdn.example.net/stream/y/anime/11.mp4/index.m3u8"

        with _patch("services.anime.episode_url_pattern.validate_episode_url", return_value=False):
            result = get_episode_url_and_source("My Anime", 12, current_player_url=current_url)

        assert result.success is True
        assert result.player_url == "https://scraper.example.com/ep12.mp4"
        mock_rep.search_player.assert_called_once_with("My Anime", 12)

    @patch("services.anime.playback_service.rep")
    def test_uses_pattern_url_when_valid(self, mock_rep):
        """When derived URL is valid, scraping is skipped."""
        from unittest.mock import patch as _patch
        from services.anime.playback_service import get_episode_url_and_source

        current_url = "https://cdn.example.net/stream/y/anime/11.mp4/index.m3u8"
        expected_derived = "https://cdn.example.net/stream/y/anime/12.mp4/index.m3u8"

        with _patch("services.anime.episode_url_pattern.validate_episode_url", return_value=True):
            result = get_episode_url_and_source("My Anime", 12, current_player_url=current_url)

        assert result.success is True
        assert result.player_url == expected_derived
        assert result.source == "pattern"
        mock_rep.search_player.assert_not_called()

    @patch("services.anime.playback_service.rep")
    def test_falls_back_when_no_pattern_in_url(self, mock_rep):
        """When current URL has no pattern, scraping runs normally."""
        from services.anime.playback_service import get_episode_url_and_source

        mock_rep.search_player.return_value = "https://scraper.example.com/ep5.mp4"
        mock_rep.get_episode_url_and_source.return_value = None

        result = get_episode_url_and_source(
            "My Anime", 5, current_player_url="https://player.example.com/embed/abc123"
        )

        assert result.success is True
        mock_rep.search_player.assert_called_once_with("My Anime", 5)


# =============================================================================
# Step 5: Tests for sync_progress_to_anilist()
# =============================================================================


class TestSyncProgressToAnilist:
    """Tests for sync_progress_to_anilist function."""

    def test_not_authenticated(self):
        """Test 11: Not Authenticated.

        Input: anilist_id=None, episode=5, watched=True
        Expected: Returns False (no sync attempted)
        """
        from services.anime.playback_service import sync_progress_to_anilist

        # Execute with no anilist_id
        result = sync_progress_to_anilist(
            anilist_id=None,
            episode=5,
            num_episodes=24,
        )

        # Verify no sync attempted
        assert result is False

    @patch("services.anime.playback_service.anilist_client")
    def test_sync_progress_success_scenarios(self, mock_anilist):
        """Test successful sync scenarios with different list states and status changes."""
        from services.anime.playback_service import sync_progress_to_anilist
        from models.models import Status

        # Scenario 1: Basic sync - anime already in list
        mock_anilist.is_authenticated.return_value = True
        mock_anilist.is_in_any_list.return_value = True
        mock_anilist.get_media_list_entry.return_value = MagicMock(status="CURRENT")
        mock_anilist.update_progress.return_value = True
        mock_anime = MagicMock(episodes=24)
        mock_anilist.get_anime_by_id.return_value = mock_anime

        result = sync_progress_to_anilist(anilist_id=12345, episode=5, num_episodes=24)
        assert result is True
        mock_anilist.update_progress.assert_called_with(12345, 5)

        # Scenario 2: Add anime to list (not in any list yet)
        mock_anilist.is_in_any_list.return_value = False
        mock_anilist.add_to_list.return_value = True
        mock_anilist.update_progress.reset_mock()

        result = sync_progress_to_anilist(anilist_id=12345, episode=5, num_episodes=24)
        assert result is True
        mock_anilist.add_to_list.assert_called_once()
        mock_anilist.update_progress.assert_called_with(12345, 5)

        # Scenario 3: Promote PLANNING to CURRENT
        mock_anilist.is_in_any_list.return_value = True
        mock_entry = MagicMock(status="PLANNING")
        mock_anilist.get_media_list_entry.return_value = mock_entry
        mock_anilist.add_to_list.reset_mock()
        mock_anilist.update_progress.reset_mock()

        result = sync_progress_to_anilist(anilist_id=12345, episode=1, num_episodes=24)
        assert result is True
        mock_anilist.add_to_list.assert_called_once_with(12345, Status.CURRENT)

        # Scenario 4: Complete anime (last episode)
        mock_entry.status = "CURRENT"
        mock_anilist.change_status.return_value = True
        mock_anilist.update_progress.reset_mock()

        result = sync_progress_to_anilist(anilist_id=12345, episode=24, num_episodes=24)
        assert result is True
        mock_anilist.change_status.assert_called_once_with(12345, Status.COMPLETED)

    @patch("services.anime.playback_service.anilist_client")
    def test_anilist_api_fails(self, mock_anilist):
        """Test 16: AniList API Fails.

        Input: anilist_client.update_progress() raises exception
        Expected: Returns False, error is logged but not raised
        """
        from services.anime.playback_service import sync_progress_to_anilist

        # Setup: API fails
        mock_anilist.is_authenticated.return_value = True
        mock_anilist.is_in_any_list.return_value = True
        mock_anilist.get_media_list_entry.return_value = MagicMock(status="CURRENT")
        mock_anilist.get_anime_by_id.return_value = MagicMock(episodes=24)
        mock_anilist.update_progress.side_effect = ValueError("API error")

        # Execute - should NOT raise exception
        result = sync_progress_to_anilist(
            anilist_id=12345,
            episode=5,
            num_episodes=24,
        )

        # Verify graceful failure
        assert result is False


# =============================================================================
# Step 6: Tests for navigate_episodes()
# =============================================================================


class TestNavigateEpisodes:
    """Tests for navigate_episodes function."""

    def test_navigate_direction_and_boundaries(self):
        """Test navigation in both directions with boundary enforcement."""
        from services.anime.playback_service import PlaybackContext, navigate_episodes

        ctx = PlaybackContext(
            anime_title="Dandadan",
            episode_idx=5,
            source="animefire",
            anilist_id=12345,
            anilist_title="Dandadan",
            total_episodes_anilist=12,
            num_episodes=12,
            episode_list=tuple(f"Ep {i}" for i in range(1, 13)),
        )

        # Navigate next (valid)
        new_ctx = navigate_episodes(ctx, action="next")
        assert new_ctx.episode_idx == 6
        assert ctx.episode_idx == 5  # Original unchanged

        # Navigate previous (valid)
        new_ctx = navigate_episodes(ctx, action="previous")
        assert new_ctx.episode_idx == 4

        # Cannot go past last episode
        ctx_last = PlaybackContext(
            anime_title="Dandadan",
            episode_idx=11,
            source="animefire",
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=12,
            episode_list=tuple(f"Ep {i}" for i in range(1, 13)),
        )
        new_ctx = navigate_episodes(ctx_last, action="next")
        assert new_ctx.episode_idx == 11

        # Cannot go before first episode
        ctx_first = PlaybackContext(
            anime_title="Dandadan",
            episode_idx=0,
            source="animefire",
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=12,
            episode_list=tuple(f"Ep {i}" for i in range(1, 13)),
        )
        new_ctx = navigate_episodes(ctx_first, action="previous")
        assert new_ctx.episode_idx == 0

    def test_choose_specific_episode(self):
        """Test 20: Choose Specific Episode.

        Input: episode_idx selected from menu
        Expected: Returns new PlaybackContext with selected episode_idx
        """
        from services.anime.playback_service import PlaybackContext, navigate_episodes

        # Setup
        ctx = PlaybackContext(
            anime_title="Dandadan",
            episode_idx=0,
            source="animefire",
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=24,
            episode_list=tuple(f"Ep {i}" for i in range(1, 25)),
        )

        # Execute: Jump to episode 15 (index 14)
        new_ctx = navigate_episodes(ctx, action="choose", target_idx=14)

        # Verify
        assert new_ctx.episode_idx == 14

    def test_replay_current_episode(self):
        """Test: Replay Current Episode.

        Input: action="replay"
        Expected: Returns same episode_idx (replay)
        """
        from services.anime.playback_service import PlaybackContext, navigate_episodes

        # Setup
        ctx = PlaybackContext(
            anime_title="Dandadan",
            episode_idx=5,
            source="animefire",
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=12,
            episode_list=tuple(f"Ep {i}" for i in range(1, 13)),
        )

        # Execute
        new_ctx = navigate_episodes(ctx, action="replay")

        # Verify same episode
        assert new_ctx.episode_idx == 5

    def test_navigate_preserves_all_context_fields(self):
        """Test: Navigation preserves all other context fields.

        Input: Navigate to next episode
        Expected: All fields except episode_idx are preserved
        """
        from services.anime.playback_service import PlaybackContext, navigate_episodes

        # Setup: Full context
        ctx = PlaybackContext(
            anime_title="Dandadan",
            episode_idx=5,
            source="animefire",
            anilist_id=12345,
            anilist_title="Dandadan (Romaji)",
            total_episodes_anilist=24,
            num_episodes=24,
            episode_list=tuple(f"Ep {i}" for i in range(1, 25)),
        )

        # Execute
        new_ctx = navigate_episodes(ctx, action="next")

        # Verify all other fields preserved
        assert new_ctx.anime_title == ctx.anime_title
        assert new_ctx.source == ctx.source
        assert new_ctx.anilist_id == ctx.anilist_id
        assert new_ctx.anilist_title == ctx.anilist_title
        assert new_ctx.total_episodes_anilist == ctx.total_episodes_anilist
        assert new_ctx.num_episodes == ctx.num_episodes
        assert new_ctx.episode_list == ctx.episode_list
        # Only episode_idx changed
        assert new_ctx.episode_idx == 6

    def test_navigate_preserves_episode_skip_available(self):
        """Test: Navigation preserves episode_skip_available dict.

        Input: Navigate to next episode with skip times dict
        Expected: New context contains same skip times dict
        """
        from services.anime.playback_service import PlaybackContext, navigate_episodes

        ctx = PlaybackContext(
            anime_title="Jujutsu Kaisen",
            episode_idx=2,
            source="animesdigital",
            anilist_id=54589,
            anilist_title="Jujutsu Kaisen",
            total_episodes_anilist=24,
            num_episodes=24,
            episode_list=tuple(f"Ep {i}" for i in range(1, 25)),
        )

        # Execute: Navigate to next episode
        new_ctx = navigate_episodes(ctx, action="next")

        # Verify: skip times dict preserved
        assert new_ctx.episode_idx == 3  # Navigation happened

        # Execute: Navigate to previous
        prev_ctx = navigate_episodes(new_ctx, action="previous")

        # Verify: skip times still preserved
        assert prev_ctx.episode_idx == 2

        # Execute: Choose specific episode
        chosen_ctx = navigate_episodes(ctx, action="choose", target_idx=10)

        # Verify: skip times preserved on choose action
        assert chosen_ctx.episode_idx == 10


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @patch("services.anime.playback_service.rep")
    @patch("services.anime.playback_service.discover_anilist_info")
    def test_empty_episode_list(self, mock_discover, mock_rep):
        """Test: Empty episode list from repository.

        Input: Repository returns empty list
        Expected: PlaybackContext with num_episodes=0, empty episode_list
        """
        from services.anime.playback_service import prepare_playback_from_search

        # Setup: Empty episode list
        mock_discover.return_value = AniListDiscoveryResult(
            anilist_id=None,
            anilist_title=None,
            total_episodes=None,
            found=False,
            authenticated=False,
        )
        mock_rep.get_episode_list.return_value = []

        # Execute
        result = prepare_playback_from_search(
            selected_anime="New Anime",
            episode_idx=0,
            source=None,
        )

        # Verify
        assert result is not None
        assert result.num_episodes == 0
        assert result.episode_list == ()

    @patch("services.anime.playback_service.rep")
    @patch("services.anime.playback_service.discover_anilist_info")
    def test_discover_anilist_info_exception(self, mock_discover, mock_rep):
        """Test: discover_anilist_info raises exception.

        Input: discover_anilist_info throws error
        Expected: Graceful handling, returns PlaybackContext without AniList info
        """
        from services.anime.playback_service import prepare_playback_from_search

        # Setup: Exception in discovery
        mock_discover.side_effect = ValueError("AniList API down")
        mock_rep.get_episode_list.return_value = ["Ep 1", "Ep 2"]

        # Execute - should NOT raise
        result = prepare_playback_from_search(
            selected_anime="Test Anime",
            episode_idx=0,
            source="animefire",
        )

        # Verify graceful handling
        assert result is not None
        assert result.anilist_id is None
        assert result.anilist_title is None

    @patch("services.anime.playback_service.anilist_client")
    def test_sync_with_unauthenticated_client(self, mock_anilist):
        """Test: Sync when anilist_client is not authenticated.

        Input: anilist_id provided but client not authenticated
        Expected: Returns False, no API calls made
        """
        from services.anime.playback_service import sync_progress_to_anilist

        # Setup: Not authenticated
        mock_anilist.is_authenticated.return_value = False

        # Execute
        result = sync_progress_to_anilist(
            anilist_id=12345,
            episode=5,
            num_episodes=24,
        )

        # Verify no sync
        assert result is False
        mock_anilist.update_progress.assert_not_called()

    def test_navigate_with_invalid_action(self):
        """Test: Navigate with unknown action.

        Input: action="invalid"
        Expected: Returns same context unchanged
        """
        from services.anime.playback_service import PlaybackContext, navigate_episodes

        ctx = PlaybackContext(
            anime_title="Test",
            episode_idx=5,
            source=None,
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=12,
            episode_list=(),
        )

        # Execute with invalid action
        new_ctx = navigate_episodes(ctx, action="invalid")

        # Verify no change
        assert new_ctx.episode_idx == 5

    def test_navigate_choose_out_of_bounds(self):
        """Test: Navigate choose with out-of-bounds target.

        Input: target_idx=100 but only 12 episodes
        Expected: Clamps to last valid episode
        """
        from services.anime.playback_service import PlaybackContext, navigate_episodes

        ctx = PlaybackContext(
            anime_title="Test",
            episode_idx=0,
            source=None,
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=12,
            episode_list=tuple(f"Ep {i}" for i in range(1, 13)),
        )

        # Execute with out-of-bounds target
        new_ctx = navigate_episodes(ctx, action="choose", target_idx=100)

        # Verify clamped to last episode
        assert new_ctx.episode_idx == 11  # Last valid index

    def test_navigate_choose_negative_target(self):
        """Test: Navigate choose with negative target.

        Input: target_idx=-5
        Expected: Clamps to first episode (0)
        """
        from services.anime.playback_service import PlaybackContext, navigate_episodes

        ctx = PlaybackContext(
            anime_title="Test",
            episode_idx=5,
            source=None,
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=12,
            episode_list=tuple(f"Ep {i}" for i in range(1, 13)),
        )

        # Execute with negative target
        new_ctx = navigate_episodes(ctx, action="choose", target_idx=-5)

        # Verify clamped to first episode
        assert new_ctx.episode_idx == 0
