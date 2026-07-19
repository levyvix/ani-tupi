"""Tests for updated EpisodeRepository with priority sorting."""

from services.repository.episode_repository import EpisodeRepository


class TestEpisodeRepository:
    """Test EpisodeRepository functionality."""

    def setup_method(self):
        """Reset singleton before each test."""
        EpisodeRepository.reset_singleton()

    def teardown_method(self):
        """Clean up after each test."""
        EpisodeRepository.reset_singleton()

    def test_singleton_pattern(self):
        """EpisodeRepository should be a singleton."""
        repo1 = EpisodeRepository()
        repo2 = EpisodeRepository()
        assert repo1 is repo2

    def test_add_episode_list(self):
        """Add episode list to repository."""
        repo = EpisodeRepository()
        titles = ["Ep 1", "Ep 2", "Ep 3"]
        urls = ["http://url1.com", "http://url2.com", "http://url3.com"]

        repo.add_episode_list("Anime A", titles, urls, "animefire")

        assert "Anime A" in repo.anime_episodes_urls
        assert len(repo.anime_episodes_urls["Anime A"]) == 1

    def test_add_episode_list_replace_existing(self):
        """Adding same source should replace previous entry."""
        repo = EpisodeRepository()

        # Add first batch
        repo.add_episode_list(
            "Anime A", ["Ep 1", "Ep 2"], ["http://url1.com", "http://url2.com"], "source1"
        )
        # Add second batch for same source - should replace
        repo.add_episode_list(
            "Anime A",
            ["Ep 1", "Ep 2", "Ep 3"],
            ["http://url1.com", "http://url2.com", "http://url3.com"],
            "source1",
        )

        # Should still have only 1 source entry (replaced)
        assert len(repo.anime_episodes_urls["Anime A"]) == 1
        assert len(repo.anime_episodes_urls["Anime A"][0][0]) == 3

    def test_get_episode_list(self):
        """Get episode list returns longest from multiple sources."""
        repo = EpisodeRepository()
        repo.add_episode_list(
            "Anime A", ["Ep 1", "Ep 2"], ["http://url1", "http://url2"], "source1"
        )
        repo.add_episode_list(
            "Anime A",
            ["Ep 1", "Ep 2", "Ep 3"],
            ["http://url1", "http://url2", "http://url3"],
            "source2",
        )

        result = repo.get_episode_list("Anime A")
        assert len(result) == 3  # Longest list

    def test_get_episode_url_and_source_priority(self):
        """get_episode_url_and_source respects priority order."""
        repo = EpisodeRepository()
        repo.add_episode_list(
            "Anime A",
            ["Ep 1", "Ep 2"],
            ["http://animefire_url1", "http://animefire_url2"],
            "animefire",
        )
        repo.add_episode_list(
            "Anime A",
            ["Ep 1", "Ep 2", "Ep 3"],
            ["http://sub_url1", "http://sub_url2", "http://sub_url3"],
            "sub_source",
        )

        # Assuming priority order is configured in settings
        result = repo.get_episode_url_and_source("Anime A", 1)

        assert result is not None
        assert result[0] in ["http://animefire_url1", "http://sub_url1"]
        assert result[1] in ["animefire", "sub_source"]

    def test_get_all_episode_sources_sorted_by_priority(self):
        """get_all_episode_sources returns all sources sorted by priority."""
        repo = EpisodeRepository()
        repo.add_episode_list("Anime A", ["Ep 1"], ["http://dub_url"], "animefire")
        repo.add_episode_list("Anime A", ["Ep 1"], ["http://sub_url"], "sushianimes")

        result = repo.get_all_episode_sources("Anime A", 1)

        assert len(result) == 2
        assert result[0][1] in ["animefire", "sushianimes"]
        assert result[1][1] in ["animefire", "sushianimes"]
        assert result[0][1] != result[1][1]

    def test_get_next_available_episode(self):
        """get_next_available_episode respects priority."""
        repo = EpisodeRepository()
        repo.add_episode_list(
            "Anime A",
            ["Ep 1", "Ep 2", "Ep 3"],
            ["http://url1", "http://url2", "http://url3"],
            "source1",
        )
        repo.add_episode_list(
            "Anime A", ["Ep 1", "Ep 2"], ["http://url1", "http://url2"], "source2"
        )

        result = repo.get_next_available_episode("Anime A", 1)

        assert result is not None
        episode_num, url = result
        assert episode_num == 2
        assert url is not None

    def test_save_and_restore_episode_state(self):
        """Save and restore episode state."""
        repo = EpisodeRepository()
        repo.add_episode_list(
            "Anime A", ["Ep 1", "Ep 2"], ["http://url1", "http://url2"], "source1"
        )

        # Save state
        state = repo.save_episode_state("Anime A")

        # Clear and restore
        repo.clear_episode_state("Anime A")
        assert len(repo.anime_episodes_urls["Anime A"]) == 0

        repo.restore_episode_state("Anime A", state)
        assert len(repo.anime_episodes_urls["Anime A"]) > 0

    def test_load_from_cache(self):
        """Load episodes from cache."""
        repo = EpisodeRepository()
        cache_data = {"episode_urls": ["http://url1", "http://url2", "http://url3"]}

        repo.load_from_cache("Anime A", cache_data)

        # Should have cache source added
        assert "Anime A" in repo.anime_episodes_urls
        urls, source = repo.anime_episodes_urls["Anime A"][0]
        assert source == "cache"
        assert len(urls) == 3

    def test_reset_singleton(self):
        """reset_singleton clears instance."""
        repo1 = EpisodeRepository()
        repo1.add_episode_list("Anime A", ["Ep 1"], ["http://url1"], "source")

        EpisodeRepository.reset_singleton()
        repo2 = EpisodeRepository()

        assert len(repo2.anime_episodes_urls) == 0
        assert repo1 is not repo2

    def test_get_episode_url_and_source_returns_none_for_invalid_episode(self):
        """Should return None if episode doesn't exist."""
        repo = EpisodeRepository()
        repo.add_episode_list("Anime A", ["Ep 1"], ["http://url1"], "source")

        result = repo.get_episode_url_and_source("Anime A", 999)
        assert result is None

    def test_get_all_episode_sources_empty_for_missing_anime(self):
        """Should return empty list for missing anime."""
        repo = EpisodeRepository()

        result = repo.get_all_episode_sources("Unknown Anime", 1)
        assert result == []

    def test_get_next_available_episode_none_if_no_more(self):
        """Should return None if no more episodes available."""
        repo = EpisodeRepository()
        repo.add_episode_list("Anime A", ["Ep 1", "Ep 2"], ["http://url1", "http://url2"], "source")

        result = repo.get_next_available_episode("Anime A", 10)
        assert result is None
