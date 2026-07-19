"""Tests for PlayerRepository class."""

import pytest
from services.repository.player_repository import PlayerRepository


class MockPlugin:
    """Mock plugin for testing video URL resolution."""

    def __init__(self, name: str, video_url: str | None = None):
        self.name = name
        self.video_url = video_url

    def search_player_src(self, url: str, container: list, event):
        """Mock plugin method for video resolution."""
        if self.video_url:
            container.append(self.video_url)
        event.set()


@pytest.fixture
def player_repo():
    """Create a fresh player repository for each test."""
    PlayerRepository.reset_singleton()
    return PlayerRepository()


class TestPlayerRepository:
    """Test PlayerRepository class."""

    def test_singleton_pattern(self):
        """PlayerRepository should be a singleton."""
        repo1 = PlayerRepository()
        repo2 = PlayerRepository()
        assert repo1 is repo2

    def test_set_anime_to_anilist_id(self, player_repo):
        """Should map anime title to AniList ID."""
        player_repo.set_anime_to_anilist_id("Naruto", 20)

        assert player_repo.get_anime_anilist_id("Naruto") == 20

    def test_get_anime_anilist_id_not_found(self, player_repo):
        """Should return None for unmapped anime."""
        result = player_repo.get_anime_anilist_id("NonExistent")
        assert result is None

    def test_set_multiple_anime_ids(self, player_repo):
        """Should map multiple anime to IDs."""
        player_repo.set_anime_to_anilist_id("Naruto", 20)
        player_repo.set_anime_to_anilist_id("One Piece", 21)
        player_repo.set_anime_to_anilist_id("Bleach", 269)

        assert player_repo.get_anime_anilist_id("Naruto") == 20
        assert player_repo.get_anime_anilist_id("One Piece") == 21
        assert player_repo.get_anime_anilist_id("Bleach") == 269

    def test_get_all_anime_ids(self, player_repo):
        """Should return dict of all anime-to-ID mappings."""
        player_repo.set_anime_to_anilist_id("Naruto", 20)
        player_repo.set_anime_to_anilist_id("One Piece", 21)

        all_ids = player_repo.get_all_anime_ids()

        assert all_ids == {
            "Naruto": 20,
            "One Piece": 21,
        }

    def test_get_all_anime_ids_empty(self, player_repo):
        """Should return empty dict when no mappings exist."""
        all_ids = player_repo.get_all_anime_ids()
        assert all_ids == {}

    def test_register_plugin(self, player_repo):
        """Should register a plugin for video resolution."""
        plugin = MockPlugin("animefire", "http://video.mp4")
        player_repo.register_plugin(plugin)

        assert player_repo.get_plugin("animefire") is plugin

    def test_get_plugin_not_found(self, player_repo):
        """Should return None for unregistered plugin."""
        result = player_repo.get_plugin("nonexistent")
        assert result is None

    def test_get_active_sources(self, player_repo):
        """Should return sorted list of registered plugin names."""
        player_repo.register_plugin(MockPlugin("zulu"))
        player_repo.register_plugin(MockPlugin("alpha"))
        player_repo.register_plugin(MockPlugin("mike"))

        sources = player_repo.get_active_sources()

        # get_active_sources already returns sorted list
        assert sources == ["alpha", "mike", "zulu"]

    def test_get_active_sources_empty(self, player_repo):
        """Should return empty list when no plugins registered."""
        sources = player_repo.get_active_sources()
        assert sources == []

    def test_clear_selected_urls(self, player_repo):
        """Should clear selected URLs for an anime."""
        player_repo.set_selected_urls("Naruto", 1, [("http://vid.mp4", "animefire")])

        assert len(player_repo.get_selected_urls("Naruto", 1)) > 0

        player_repo.clear_selected_urls("Naruto", 1)

        assert player_repo.get_selected_urls("Naruto", 1) == []

    def test_set_selected_urls(self, player_repo):
        """Should set selected URLs for episode."""
        urls = [("http://vid1.mp4", "animefire"), ("http://vid2.mp4", "animesonline")]
        player_repo.set_selected_urls("Naruto", 1, urls)

        result = player_repo.get_selected_urls("Naruto", 1)
        assert result == urls

    def test_get_selected_urls_empty(self, player_repo):
        """Should return empty list for episode with no URLs."""
        result = player_repo.get_selected_urls("Naruto", 99)
        assert result == []

    def test_reset_singleton(self):
        """Should clear singleton instance on reset."""
        repo1 = PlayerRepository()
        repo1.set_anime_to_anilist_id("Naruto", 20)
        repo1.register_plugin(MockPlugin("animefire"))

        PlayerRepository.reset_singleton()

        repo2 = PlayerRepository()
        assert repo2.get_anime_anilist_id("Naruto") is None
        assert repo2.get_plugin("animefire") is None
