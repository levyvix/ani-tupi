"""Tests for EpisodeRepository class."""

import time

import pytest
from services.episode_repository import EpisodeRepository


@pytest.fixture
def episode_repo():
    """Create a fresh episode repository for each test."""
    EpisodeRepository.reset_singleton()
    return EpisodeRepository()


class TestEpisodeRepository:
    """Test EpisodeRepository class."""

    def test_singleton_pattern(self):
        """EpisodeRepository should be a singleton."""
        repo1 = EpisodeRepository()
        repo2 = EpisodeRepository()
        assert repo1 is repo2

    def test_add_episode_list_single(self, episode_repo):
        """Should add episode list for an anime."""
        titles = ["Episode 1", "Episode 2", "Episode 3"]
        urls = ["http://ep1.com", "http://ep2.com", "http://ep3.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "animefire")

        # Should store without raising error (normalized to episode numbers)
        assert episode_repo.get_episode_list("Naruto") == [1, 2, 3]

    def test_add_episode_list_validation(self, episode_repo):
        """Should validate that titles and urls have same length."""
        titles = ["Episode 1", "Episode 2"]
        urls = ["http://ep1.com"]  # Mismatch!

        with pytest.raises(ValueError):
            episode_repo.add_episode_list("Naruto", titles, urls, "animefire")

    def test_get_episode_list_empty(self, episode_repo):
        """Should return empty list for anime with no episodes."""
        result = episode_repo.get_episode_list("NonExistent")
        assert result == []

    def test_get_episode_list_multiple_sources(self, episode_repo):
        """Should return longest episode list when multiple sources exist."""
        titles1 = ["Ep1", "Ep2"]
        urls1 = ["http://1.com", "http://2.com"]
        titles2 = ["Ep1", "Ep2", "Ep3", "Ep4"]
        urls2 = ["http://1.com", "http://2.com", "http://3.com", "http://4.com"]

        episode_repo.add_episode_list("Naruto", titles1, urls1, "source1")
        episode_repo.add_episode_list("Naruto", titles2, urls2, "source2")

        result = episode_repo.get_episode_list("Naruto")
        assert result == [1, 2, 3, 4]  # Returns longest list

    def test_get_episode_url_by_index(self, episode_repo):
        """Should get episode URL by 0-indexed position."""
        titles = ["Episode 1", "Episode 2", "Episode 3"]
        urls = ["http://ep1.com", "http://ep2.com", "http://ep3.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "animefire")

        assert episode_repo.get_episode_url_and_source("Naruto", 1)[0] == "http://ep1.com"
        assert episode_repo.get_episode_url_and_source("Naruto", 2)[0] == "http://ep2.com"
        assert episode_repo.get_episode_url_and_source("Naruto", 3)[0] == "http://ep3.com"

    def test_get_episode_url_out_of_range(self, episode_repo):
        """Should return None for out-of-range episode index."""
        titles = ["Episode 1"]
        urls = ["http://ep1.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "animefire")

        assert episode_repo.get_episode_url_and_source("Naruto", 10) is None

    def test_get_episode_url_and_source(self, episode_repo):
        """Should return URL and source for 1-indexed episode number."""
        titles = ["Episode 1", "Episode 2"]
        urls = ["http://ep1.com", "http://ep2.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "animefire")

        result = episode_repo.get_episode_url_and_source("Naruto", 1)
        assert result == ("http://ep1.com", "animefire")

        result = episode_repo.get_episode_url_and_source("Naruto", 2)
        assert result == ("http://ep2.com", "animefire")

    def test_get_episode_url_and_source_invalid(self, episode_repo):
        """Should return None for invalid episode numbers."""
        titles = ["Episode 1"]
        urls = ["http://ep1.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "animefire")

        assert episode_repo.get_episode_url_and_source("Naruto", 0) is None
        assert episode_repo.get_episode_url_and_source("Naruto", 10) is None

    def test_save_episode_state(self, episode_repo):
        """Should save episode state for source switching."""
        titles = ["Episode 1", "Episode 2"]
        urls = ["http://ep1.com", "http://ep2.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "source1")

        state = episode_repo.save_episode_state("Naruto")

        assert "urls" in state
        assert "numbers" in state
        assert state["numbers"] == [[1, 2]]
        assert len(state["urls"]) == 1

    def test_restore_episode_state(self, episode_repo):
        """Should restore previously saved episode state."""
        titles = ["Episode 1", "Episode 2"]
        urls = ["http://ep1.com", "http://ep2.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "source1")
        state = episode_repo.save_episode_state("Naruto")

        # Clear and restore
        episode_repo.clear_episode_state("Naruto")
        assert episode_repo.get_episode_list("Naruto") == []

        episode_repo.restore_episode_state("Naruto", state)
        assert episode_repo.get_episode_list("Naruto") == [1, 2]

    def test_load_from_cache(self, episode_repo):
        """Should load episode data from cache."""
        cache_data = {
            "episode_urls": ["http://ep1.com", "http://ep2.com", "http://ep3.com"],
            "episode_count": 3,
        }

        episode_repo.load_from_cache("Naruto", cache_data)

        episode_list = episode_repo.get_episode_list("Naruto")
        # Should generate sequential episode numbers (1-indexed)
        assert len(episode_list) == 3
        assert episode_list[0] == 1

    def test_load_from_cache_pydantic_model(self, episode_repo):
        """Should handle Pydantic model cache data."""
        from collections import namedtuple

        CacheData = namedtuple("CacheData", ["episode_urls"])
        cache_data = CacheData(episode_urls=["http://ep1.com", "http://ep2.com"])

        episode_repo.load_from_cache("Naruto", cache_data)

        episode_list = episode_repo.get_episode_list("Naruto")
        assert len(episode_list) == 2

    def test_load_from_cache_empty(self, episode_repo):
        """Should handle empty cache data gracefully."""
        cache_data = {"episode_urls": []}

        episode_repo.load_from_cache("Naruto", cache_data)

        # Should not crash, return empty
        assert episode_repo.get_episode_list("Naruto") == []

    def test_get_next_available_episode(self, episode_repo):
        """Should find next available episode from given number."""
        titles = [f"Episode {i + 1}" for i in range(10)]
        urls = [f"http://ep{i + 1}.com" for i in range(10)]

        episode_repo.add_episode_list("Naruto", titles, urls, "animefire")

        result = episode_repo.get_next_available_episode("Naruto", 5)
        assert result == (6, "http://ep6.com")

    def test_get_next_available_episode_at_end(self, episode_repo):
        """Should return None when at end of episodes."""
        titles = ["Episode 1", "Episode 2"]
        urls = ["http://ep1.com", "http://ep2.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "animefire")

        result = episode_repo.get_next_available_episode("Naruto", 2)
        assert result is None

    def test_get_next_available_episode_multiple_sources(self, episode_repo):
        """Should find best next episode across multiple sources."""
        # Source 1: 5 episodes
        titles1 = [f"Episode {i + 1}" for i in range(5)]
        urls1 = [f"http://s1-ep{i + 1}.com" for i in range(5)]

        # Source 2: 10 episodes
        titles2 = [f"Episode {i + 1}" for i in range(10)]
        urls2 = [f"http://s2-ep{i + 1}.com" for i in range(10)]

        episode_repo.add_episode_list("Naruto", titles1, urls1, "source1")
        episode_repo.add_episode_list("Naruto", titles2, urls2, "source2")

        # Looking for next after 5 should find it in source2
        result = episode_repo.get_next_available_episode("Naruto", 5)
        assert result == (6, "http://s2-ep6.com")

    def test_clear_episode_state(self, episode_repo):
        """Should clear episode state for an anime."""
        titles = ["Episode 1", "Episode 2"]
        urls = ["http://ep1.com", "http://ep2.com"]

        episode_repo.add_episode_list("Naruto", titles, urls, "animefire")
        assert len(episode_repo.get_episode_list("Naruto")) > 0

        episode_repo.clear_episode_state("Naruto")
        assert episode_repo.get_episode_list("Naruto") == []

    def test_reset_singleton(self):
        """Should clear singleton instance on reset."""
        repo1 = EpisodeRepository()
        titles = ["Episode 1"]
        urls = ["http://ep1.com"]
        repo1.add_episode_list("Naruto", titles, urls, "animefire")

        EpisodeRepository.reset_singleton()

        repo2 = EpisodeRepository()
        assert repo2.get_episode_list("Naruto") == []

    def test_search_episodes_continues_when_one_source_fails(self, episode_repo):
        """Should swallow scraper exceptions and keep successful results."""

        class WorkingScraper:
            def search_episodes(self, anime: str, url: str, params):
                episode_repo.add_episode_list(anime, ["Episode 1"], ["http://ep1.com"], "working")

        class FailingScraper:
            def search_episodes(self, anime: str, url: str, params):
                raise RuntimeError("renderer timeout")

        episode_repo.set_sources({"working": WorkingScraper(), "failing": FailingScraper()})

        episode_repo.search_episodes(
            "Naruto",
            {
                "Naruto": [
                    ("http://working.example", "working", None),
                    ("http://failing.example", "failing", None),
                ]
            },
        )

        assert episode_repo.get_episode_list("Naruto") == [1]
        assert episode_repo.get_last_search_failures("Naruto") == [("failing", "renderer timeout")]

    def test_search_episodes_records_all_failures_without_raising(self, episode_repo):
        """Should record failures when every scraper errors."""

        class FailingScraper:
            def __init__(self, message: str):
                self.message = message

            def search_episodes(self, anime: str, url: str, params):
                raise RuntimeError(self.message)

        episode_repo.set_sources(
            {
                "source1": FailingScraper("timeout"),
                "source2": FailingScraper("network error"),
            }
        )

        episode_repo.search_episodes(
            "Bleach",
            {
                "Bleach": [
                    ("http://source1.example", "source1", None),
                    ("http://source2.example", "source2", None),
                ]
            },
        )

        assert episode_repo.get_episode_list("Bleach") == []
        assert sorted(episode_repo.get_last_search_failures("Bleach")) == [
            ("source1", "timeout"),
            ("source2", "network error"),
        ]

    def test_search_episodes_waits_for_all_sources_before_returning(self, episode_repo):
        """Should block until all sources complete so caller sees complete state."""

        slow_ran = []

        class FastScraper:
            def search_episodes(self, anime: str, url: str, params):
                episode_repo.add_episode_list(
                    anime, ["Ep1", "Ep2"], ["http://u1.com", "http://u2.com"], "fast"
                )

        class SlowScraper:
            def search_episodes(self, anime: str, url: str, params):
                time.sleep(0.1)
                slow_ran.append(True)
                episode_repo.add_episode_list(anime, ["Ep1"], ["http://slow-ep1.com"], "slow")

        episode_repo.set_sources({"fast": FastScraper(), "slow": SlowScraper()})

        episode_repo.search_episodes(
            "One Piece",
            {
                "One Piece": [
                    ("http://fast.example", "fast", None),
                    ("http://slow.example", "slow", None),
                ]
            },
        )

        assert slow_ran, "slow source must complete before search_episodes returns"
        assert episode_repo.get_episode_list("One Piece") == [1, 2]

    def test_get_episode_list_ignores_outlier_source(self, episode_repo):
        """Should drop absurdly long lists caused by scraper bugs."""
        normal_titles = [f"Ep {i}" for i in range(1, 13)]
        normal_urls = [f"http://example.com/{i}" for i in range(1, 13)]
        outlier_titles = [f"Ep {i}" for i in range(1, 6811)]
        outlier_urls = [f"http://bad.com/{i}" for i in range(1, 6811)]

        episode_repo.add_episode_list("Anime", normal_titles, normal_urls, "animefire")
        episode_repo.add_episode_list("Anime", outlier_titles, outlier_urls, "anroll")

        assert episode_repo.get_episode_list("Anime") == list(range(1, 13))
