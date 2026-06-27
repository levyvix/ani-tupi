"""Unit tests for source switching with incremental search.

Tests that source switching performs a new incremental search,
allowing user to discover different sources and versions of the anime.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from services.anime.source_management import switch_anime_source


@pytest.fixture
def setup_mocks():
    """Setup all necessary mocks for source switching tests."""
    patches = []

    # Patch repository
    mock_rep_patch = patch("services.anime.source_management.rep")
    mock_rep = mock_rep_patch.start()
    patches.append(mock_rep_patch)

    # Setup repository mock
    mock_rep.anime_episodes_urls = {}
    mock_rep.save_episode_state.return_value = {"urls": [], "titles": []}
    mock_rep.clear_search_results = Mock()
    mock_rep.search_episodes = Mock()
    mock_rep.get_episode_list.return_value = [1]

    # Patch title normalization
    mock_norm_patch = patch("services.anime.source_management.normalize_anime_title")
    mock_normalize = mock_norm_patch.start()
    mock_normalize.return_value = ["test anime"]  # Single variant for simplicity
    patches.append(mock_norm_patch)

    # Patch AniList search title loader
    mock_anilist_patch = patch("services.anime.source_management.load_anilist_search_title")
    mock_load_anilist = mock_anilist_patch.start()
    mock_load_anilist.return_value = None  # Use current_anime instead
    patches.append(mock_anilist_patch)

    # Patch loading context manager
    mock_loading_patch = patch("services.anime.source_management.loading")
    mock_loading = mock_loading_patch.start()
    mock_loading.return_value.__enter__ = Mock()
    mock_loading.return_value.__exit__ = Mock(return_value=None)
    patches.append(mock_loading_patch)

    # Patch menu_navigate (anime selection)
    mock_menu_patch = patch("services.anime.source_management.menu_navigate")
    mock_menu = mock_menu_patch.start()
    mock_menu.side_effect = ["Test Anime [animefire]"]
    patches.append(mock_menu_patch)

    # Patch menu_navigate_episodes (episode selection returns 0-based index)
    mock_menu_eps_patch = patch("services.anime.source_management.menu_navigate_episodes")
    mock_menu_eps = mock_menu_eps_patch.start()
    mock_menu_eps.return_value = 0
    patches.append(mock_menu_eps_patch)

    # Patch incremental_search_anime
    mock_incremental_patch = patch("services.anime.source_management.incremental_search_anime")
    mock_incremental = mock_incremental_patch.start()
    # Create mock state with navigation support
    mock_state = MagicMock()
    mock_state.get_current.return_value = MagicMock(
        query="test anime", results=["Test Anime [animefire]"]
    )
    mock_state.has_previous.return_value = False
    mock_state.has_next.return_value = False
    mock_incremental.return_value = (mock_state, ["Test Anime [animefire]"])
    patches.append(mock_incremental_patch)

    # Patch history file access to avoid progress detection
    mock_open_patch = patch("builtins.open", side_effect=FileNotFoundError)
    mock_open_patch.start()
    patches.append(mock_open_patch)

    # Patch anilist client (it's imported inside the function)
    mock_anilist_client_patch = patch("services.anilist_service.anilist_client")
    mock_anilist_client = mock_anilist_client_patch.start()
    mock_anilist_client.is_authenticated.return_value = False
    patches.append(mock_anilist_client_patch)

    yield {
        "rep": mock_rep,
        "normalize": mock_normalize,
        "load_anilist": mock_load_anilist,
        "loading": mock_loading,
        "menu": mock_menu,
        "incremental": mock_incremental,
    }

    # Cleanup
    for p in patches:
        p.stop()


class TestSourceSwitchingCache:
    """Test source switching behavior (now using incremental search)."""

    def test_performs_incremental_search(self, setup_mocks):
        """When switching source, should perform a NEW incremental search."""
        mocks = setup_mocks

        # Call switch_anime_source
        switch_anime_source("Current Anime", Mock())

        # Verify incremental_search_anime was called
        mocks["incremental"].assert_called()

        # Verify it was called with the normalized title
        call_args = mocks["incremental"].call_args[0]
        assert call_args[0] == "test anime"  # Should be normalized

    def test_normalizes_anilist_title_before_search(self, setup_mocks):
        """Should normalize AniList title before passing to incremental search."""
        mocks = setup_mocks
        # Setup: AniList provides a search title
        mocks["load_anilist"].return_value = "Boku no Hero Academia Season 5"

        # Call switch_anime_source with anilist_id
        switch_anime_source("Current Anime", Mock(), anilist_id=12345)

        # Verify normalize_anime_title was called with the AniList title
        mocks["normalize"].assert_called()
        call_args = mocks["normalize"].call_args[0]
        assert "Boku no Hero Academia Season 5" in call_args

        # Verify incremental_search_anime was called with normalized version
        mocks["incremental"].assert_called()

    def test_clears_search_results_before_new_search(self, setup_mocks):
        """Should clear previous search results before starting new search."""
        mocks = setup_mocks

        # Call switch_anime_source
        switch_anime_source("Current Anime", Mock())

        # Verify clear_search_results was called
        mocks["rep"].clear_search_results.assert_called()

    def test_returns_selected_anime_and_episode_idx(self, setup_mocks):
        """Should return the selected anime title and episode index."""
        # Call switch_anime_source
        result = switch_anime_source("Current Anime", Mock())

        # Verify result is a tuple of (anime_title, episode_idx)
        assert result is not None
        assert len(result) == 2
        assert result[0] is not None  # Anime title
        assert isinstance(result[1], int)  # Episode index
        assert result[1] >= 0

    def test_loads_episodes_from_new_source(self, setup_mocks):
        """Should load episodes from the newly selected source."""
        mocks = setup_mocks

        # Call switch_anime_source
        switch_anime_source("Current Anime", Mock())

        # Verify search_episodes was called with selected anime
        mocks["rep"].search_episodes.assert_called()

    def test_returns_none_when_no_results(self, setup_mocks):
        """Should return (None, None) when search returns no results."""
        mocks = setup_mocks
        # Setup: Incremental search returns empty results
        mock_state = MagicMock()
        mock_state.get_current.return_value = None
        mocks["incremental"].return_value = (mock_state, [])

        # Call switch_anime_source
        result = switch_anime_source("Current Anime", Mock())

        # Verify it returns (None, None)
        assert result == (None, None)
