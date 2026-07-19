"""Integration tests for the complete anime search to watch flow.

This tests the real integration between:
1. AniList search
2. Menu navigation
3. Playback start
4. Progress tracking
"""

import argparse
from unittest.mock import Mock, patch
import pytest

from models.models import (
    AniListTitle,
    AniListAnime,
    AniListMediaListEntry,
)


@pytest.fixture
def mock_anilist_client():
    """Mock AniList client."""
    with patch("ui.anilist_menus.anilist_client") as mock_client:
        yield mock_client


@pytest.fixture
def mock_anilist_anime_flow():
    """Mock the anime flow function."""
    with patch("ui.anilist_menus.anilist_anime_flow") as mock_flow:
        yield mock_flow


@pytest.fixture
def mock_menu_navigate():
    """Mock menu navigation."""
    with patch("ui.anilist_menus.menu_navigate") as mock_menu:
        yield mock_menu


@pytest.fixture
def mock_loading():
    """Mock loading context manager."""
    with patch("ui.anilist_menus.loading") as mock_load:
        mock_load.return_value.__enter__ = Mock(return_value=None)
        mock_load.return_value.__exit__ = Mock(return_value=None)
        yield mock_load


@pytest.fixture
def mock_anilist_main_menu():
    """Mock main menu."""
    with patch("ui.anilist_menus.anilist_main_menu") as mock_menu:
        yield mock_menu


@pytest.fixture
def sample_search_results():
    """Sample AniList search results."""
    return [
        AniListAnime(
            id=1,
            title=AniListTitle(romaji="Dandadan", english="Dandadan"),
            episodes=12,
            averageScore=87,
            seasonYear=2024,
        ),
        AniListAnime(
            id=2,
            title=AniListTitle(romaji="Jujutsu Kaisen", english="Jujutsu Kaisen"),
            episodes=24,
            averageScore=85,
            seasonYear=2021,
        ),
    ]


class TestCompleteSearchToWatchIntegration:
    """Integration tests for the complete search to watch flow."""

    def test_search_watch_with_progress_starts_playback(
        self,
        mock_anilist_client,
        mock_anilist_anime_flow,
        mock_menu_navigate,
        mock_loading,
        mock_anilist_main_menu,
        sample_search_results,
    ):
        """User searches, has progress on anime, watches from that progress."""
        from ui.anilist_menus import _search_and_add_anime

        # Setup: User has watched 5 episodes
        entry = AniListMediaListEntry(
            id=1,
            status="CURRENT",
            progress=5,
        )
        mock_menu_navigate.side_effect = [
            "Dandadan (2024, 12 eps) ⭐87%",  # Select first result
            "▶️  Assistir agora",  # Watch now
        ]
        mock_anilist_client.search_anime.return_value = sample_search_results
        mock_anilist_client.format_title.return_value = "Dandadan"
        mock_anilist_client.get_media_list_entry.return_value = entry
        mock_anilist_main_menu.return_value = None

        with patch("builtins.input", return_value="Dandadan"):
            _search_and_add_anime(is_logged_in=True)

        # Verify: anilist_anime_flow called with progress
        mock_anilist_anime_flow.assert_called_once()
        call_args = mock_anilist_anime_flow.call_args

        # Verify playback starts with correct progress
        assert call_args[0][0] == "Dandadan"  # search_title
        assert call_args[0][1] == 1  # anime_id
        assert call_args[1]["anilist_progress"] == 5

    def test_search_multiple_results_user_selects_second(
        self,
        mock_anilist_client,
        mock_anilist_anime_flow,
        mock_menu_navigate,
        mock_loading,
        mock_anilist_main_menu,
        sample_search_results,
    ):
        """User searches, gets multiple results, selects the second one."""
        from ui.anilist_menus import _search_and_add_anime

        mock_menu_navigate.side_effect = [
            "Jujutsu Kaisen (2021, 24 eps) ⭐85%",  # Select second result
            "▶️  Assistir agora",
        ]
        mock_anilist_client.search_anime.return_value = sample_search_results
        mock_anilist_client.format_title.side_effect = ["Dandadan", "Jujutsu Kaisen"]
        mock_anilist_client.get_media_list_entry.return_value = None
        mock_anilist_main_menu.return_value = None

        with patch("builtins.input", return_value="Jujutsu"):
            _search_and_add_anime(is_logged_in=True)

        # Verify: correct anime ID was used
        call_args = mock_anilist_anime_flow.call_args
        assert call_args[0][1] == 2  # Jujutsu Kaisen ID

    def test_add_new_anime_then_watch(
        self,
        mock_anilist_client,
        mock_anilist_anime_flow,
        mock_menu_navigate,
        mock_loading,
        mock_anilist_main_menu,
        sample_search_results,
    ):
        """User adds new anime to list (with CURRENT status) then starts watching."""
        from ui.anilist_menus import _search_and_add_anime

        # User adds anime that's not on their list.
        # choose_status() is imported from ui.anilist.filters and calls its own
        # menu_navigate; patch it directly so we don't need to thread a side-effect
        # through the ui.anilist_menus.menu_navigate mock.
        mock_menu_navigate.side_effect = [
            "Dandadan (2024, 12 eps) ⭐87%",  # Select result
            "➕ Adicionar à lista",  # Add to list
            "▶️  Assistir agora",  # Watch now after adding
        ]
        mock_anilist_client.search_anime.return_value = sample_search_results
        mock_anilist_client.format_title.return_value = "Dandadan"
        mock_anilist_client.get_media_list_entry.return_value = None
        mock_anilist_main_menu.return_value = None

        with (
            patch("ui.anilist_menus.choose_status", return_value="CURRENT"),
            patch("builtins.input", return_value="Dandadan"),
        ):
            _search_and_add_anime(is_logged_in=True)

        # Verify: anime was added BEFORE playback
        mock_anilist_client.add_to_list.assert_called_once_with(1, "CURRENT")

        # Verify: playback started AFTER adding
        assert mock_anilist_anime_flow.called
        assert mock_anilist_client.add_to_list.call_count == 1

    def test_playback_starts_immediately_no_menu_recursion(
        self,
        mock_anilist_client,
        mock_anilist_anime_flow,
        mock_menu_navigate,
        mock_loading,
        mock_anilist_main_menu,
        sample_search_results,
    ):
        """Bug fix verification: playback starts immediately, no menu recursion."""
        from ui.anilist_menus import _search_and_add_anime

        # This is the core bug: after "▶️ Assistir agora", playback should start
        # WITHOUT returning to menu first
        mock_menu_navigate.side_effect = [
            "Dandadan (2024, 12 eps) ⭐87%",
            "▶️  Assistir agora",  # This should trigger playback immediately
        ]
        mock_anilist_client.search_anime.return_value = sample_search_results
        mock_anilist_client.format_title.return_value = "Dandadan"
        mock_anilist_client.get_media_list_entry.return_value = None
        mock_anilist_main_menu.return_value = None

        with patch("builtins.input", return_value="Dandadan"):
            _search_and_add_anime(is_logged_in=True)

        # Verify: anilist_anime_flow was called (playback started)
        assert mock_anilist_anime_flow.called

        # Verify: anilist_main_menu was called exactly once (at the end)
        # not multiple times in a loop
        assert mock_anilist_main_menu.call_count == 1

    def test_correct_parameters_passed_to_playback(
        self,
        mock_anilist_client,
        mock_anilist_anime_flow,
        mock_menu_navigate,
        mock_loading,
        mock_anilist_main_menu,
        sample_search_results,
    ):
        """Verify all correct parameters are passed to anilist_anime_flow."""
        from ui.anilist_menus import _search_and_add_anime

        # User with progress watches anime
        entry = AniListMediaListEntry(id=1, status="CURRENT", progress=7)
        mock_menu_navigate.side_effect = [
            "Dandadan (2024, 12 eps) ⭐87%",
            "▶️  Assistir agora",
        ]
        mock_anilist_client.search_anime.return_value = sample_search_results
        mock_anilist_client.format_title.return_value = "Dandadan"
        mock_anilist_client.get_media_list_entry.return_value = entry
        mock_anilist_main_menu.return_value = None

        with patch("builtins.input", return_value="Dandadan"):
            _search_and_add_anime(is_logged_in=True)

        # Verify all parameters
        call_args = mock_anilist_anime_flow.call_args
        assert call_args[0][0] == "Dandadan"  # search_title
        assert call_args[0][1] == 1  # anime_id
        assert isinstance(call_args[0][2], argparse.Namespace)
        assert call_args[0][2].debug is False
        assert call_args[1]["anilist_progress"] == 7
        assert call_args[1]["display_title"] == "Dandadan"

    def test_unauthenticated_user_skips_add_option(
        self,
        mock_anilist_client,
        mock_anilist_anime_flow,
        mock_menu_navigate,
        mock_loading,
        mock_anilist_main_menu,
        sample_search_results,
    ):
        """Unauthenticated user has no "add to list" option, goes straight to watch."""
        from ui.anilist_menus import _search_and_add_anime

        # Unauthenticated user searches and watches
        mock_menu_navigate.side_effect = [
            "Dandadan (2024, 12 eps) ⭐87%",  # Select result
            # No "add to list" menu - straight to playback
        ]
        mock_anilist_client.search_anime.return_value = sample_search_results
        mock_anilist_client.format_title.return_value = "Dandadan"
        mock_anilist_client.get_media_list_entry.return_value = None
        mock_anilist_main_menu.return_value = None

        with patch("builtins.input", return_value="Dandadan"):
            _search_and_add_anime(is_logged_in=False)

        # Verify: playback started without showing action menu
        mock_anilist_anime_flow.assert_called_once()
        # Verify: menu_navigate called only once (for search results)
        assert mock_menu_navigate.call_count == 1


# ============================================================================
# INTEGRATION TESTS: Episode Fetching Enhancement
# ============================================================================


class TestEpisodeFetchingIntegration:
    """Integration tests for enhanced episode fetching in anime lists."""

    @pytest.fixture
    def mock_cache(self):
        """Mock cache system."""
        with patch("ui.anilist_menus.get_cache") as mock_cache_func:
            cache_mock = Mock()
            mock_cache_func.return_value = cache_mock
            yield cache_mock

    def test_get_episode_count_integration_with_cache_and_api(
        self, mock_anilist_client, mock_cache
    ):
        """Test _get_episode_count function with real cache and API integration."""
        from ui.anilist_menus import _get_episode_count

        # Test 1: Direct return when episodes not null
        result = _get_episode_count(123, 12)
        assert result == 12
        mock_cache.get.assert_not_called()
        mock_anilist_client.get_anime_by_id.assert_not_called()

        # Test 2: Cache hit
        mock_cache.get.return_value = 24
        result = _get_episode_count(456, None)
        assert result == 24
        mock_cache.get.assert_called_with("anilist_episodes:456")
        mock_anilist_client.get_anime_by_id.assert_not_called()

        # Test 3: Cache miss, API success
        mock_cache.reset_mock()
        mock_cache.get.return_value = None
        anime_with_episodes = AniListAnime(
            id=789,
            title=AniListTitle(romaji="Test Anime"),
            episodes=36,
        )
        mock_anilist_client.get_anime_by_id.return_value = anime_with_episodes

        result = _get_episode_count(789, None)
        assert result == 36
        mock_cache.get.assert_called_with("anilist_episodes:789")
        mock_anilist_client.get_anime_by_id.assert_called_with(789)
        mock_cache.set.assert_called_with("anilist_episodes:789", 36, ttl=604800)

    def test_get_episode_count_integration_edge_cases(self, mock_anilist_client, mock_cache):
        """Test _get_episode_count edge cases."""
        from ui.anilist_menus import _get_episode_count

        # Test 1: API returns None
        mock_cache.get.return_value = None
        mock_anilist_client.get_anime_by_id.return_value = None

        result = _get_episode_count(123, None)
        assert result is None
        mock_cache.set.assert_not_called()

        # Test 2: API returns anime with null episodes
        mock_cache.reset_mock()
        mock_cache.get.return_value = None
        anime_with_null_episodes = AniListAnime(
            id=456,
            title=AniListTitle(romaji="Null Anime"),
            episodes=None,
        )
        mock_anilist_client.get_anime_by_id.return_value = anime_with_null_episodes

        result = _get_episode_count(456, None)
        assert result is None
        mock_cache.set.assert_not_called()

        # Test 3: API exception
        mock_cache.reset_mock()
        mock_cache.get.return_value = None
        mock_anilist_client.get_anime_by_id.side_effect = Exception("API Error")

        result = _get_episode_count(789, None)
        assert result is None
        mock_cache.set.assert_not_called()

    def test_cache_performance_benefit_simulation(self, mock_anilist_client, mock_cache):
        """Simulate performance benefit of caching across multiple calls."""
        from ui.anilist_menus import _get_episode_count

        anime_ids = [100, 101, 102, 103, 104]

        # First round: all cache misses, API calls
        mock_cache.get.side_effect = [None] * 5
        mock_anilist_client.get_anime_by_id.side_effect = [
            AniListAnime(id=id, title=AniListTitle(romaji=f"Anime {i}"), episodes=12 + i)
            for i, id in enumerate(anime_ids)
        ]

        # First calls
        first_results = [_get_episode_count(id, None) for id in anime_ids]
        expected_first = [12, 13, 14, 15, 16]
        assert first_results == expected_first

        # Verify API was called 5 times and cache was set 5 times
        assert mock_anilist_client.get_anime_by_id.call_count == 5
        assert mock_cache.set.call_count == 5

        # Second round: all cache hits
        mock_cache.reset_mock()
        mock_anilist_client.reset_mock()
        mock_cache.get.side_effect = [12, 13, 14, 15, 16]  # Cached values

        # Second calls
        second_results = [_get_episode_count(id, None) for id in anime_ids]
        assert second_results == expected_first

        # Verify no API calls, only cache gets
        assert mock_anilist_client.get_anime_by_id.call_count == 0
        assert mock_cache.set.call_count == 0
        assert mock_cache.get.call_count == 5
