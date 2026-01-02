"""
Shared test fixtures and configuration for ani-tupi test suite.

This module provides:
- Repository fixtures for isolated testing
- Sample data fixtures (anime, episodes, AniList responses)
- Cleanup fixtures for state management
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from config import settings, get_data_path
from models import AnimeMetadata, EpisodeData, VideoUrl
from repository import Repository


# ========== Repository Fixtures ==========


@pytest.fixture
def repo_fresh():
    """Fresh Repository instance with cleared state."""
    repo = Repository()
    repo.clear_search_results()
    yield repo
    # Cleanup
    repo.clear_search_results()


@pytest.fixture(autouse=True)
def reset_repository():
    """Auto-reset Repository before each test to prevent cross-test pollution."""
    repo = Repository()
    repo.clear_search_results()
    yield
    repo.clear_search_results()


# ========== Sample Data Fixtures ==========


@pytest.fixture
def sample_anime_dandadan():
    """Realistic anime metadata for Dandadan."""
    return AnimeMetadata(
        title="Dandadan",
        url="https://animefire.plus/animes/dandadan",
        source="animefire",
        params=None,
    )


@pytest.fixture
def sample_anime_attack_on_titan():
    """Realistic anime metadata for Attack on Titan."""
    return AnimeMetadata(
        title="Attack on Titan",
        url="https://animefire.plus/animes/shingeki-no-kyojin",
        source="animefire",
        params=None,
    )


@pytest.fixture
def sample_episodes_dandadan():
    """Realistic episode list for Dandadan."""
    return EpisodeData(
        anime_title="Dandadan",
        episode_titles=[f"Episódio {i}" for i in range(1, 13)],
        episode_urls=[f"https://animefire.plus/animes/dandadan/{i}" for i in range(1, 13)],
        source="animefire",
    )


@pytest.fixture
def sample_episodes_short():
    """Realistic short episode list for testing."""
    return EpisodeData(
        anime_title="Short Anime",
        episode_titles=["Ep. 1", "Ep. 2", "Ep. 3"],
        episode_urls=["url1", "url2", "url3"],
        source="test_source",
    )


@pytest.fixture
def sample_video_url():
    """Realistic video URL for testing."""
    return VideoUrl(
        url="https://example.com/video.m3u8",
        headers={"User-Agent": "Mozilla/5.0"},
    )


# ========== Mock Plugin Fixtures ==========


class MockPluginAnimefire:
    """Mock plugin for animefire without Selenium."""

    name = "mock_animefire"
    languages = ["pt-br"]

    @staticmethod
    def search_anime(query: str) -> None:
        """Mock anime search - returns hardcoded test data."""
        if query.lower() == "dandadan":
            repo = Repository()
            repo.add_anime(
                "Dandadan",
                "https://animefire.plus/animes/dandadan",
                "mock_animefire",
            )

    @staticmethod
    def search_episodes(anime: str, url: str, params) -> None:
        """Mock episode search - returns hardcoded test data."""
        if anime == "Dandadan":
            repo = Repository()
            episode_titles = [f"Episódio {i}" for i in range(1, 13)]
            episode_urls = [f"{url}/{i}" for i in range(1, 13)]
            repo.add_episode_list(anime, episode_titles, episode_urls, "mock_animefire")

    @staticmethod
    def search_player_src(url_episode: str, container: list, event) -> None:
        """Mock video extraction - returns hardcoded URL."""
        container.append(VideoUrl(url="https://example.com/video.m3u8"))
        event.set()

    @staticmethod
    def load(languages_dict):
        """Plugin load method."""
        pass


class MockPluginAnimesonlinecc:
    """Mock plugin for animesonlinecc without Selenium."""

    name = "mock_animesonlinecc"
    languages = ["pt-br"]

    @staticmethod
    def search_anime(query: str) -> None:
        """Mock anime search - returns hardcoded test data."""
        if query.lower() == "dandadan":
            repo = Repository()
            repo.add_anime(
                "Dandadan",
                "https://animesonlinecc.to/anime/dandadan",
                "mock_animesonlinecc",
            )

    @staticmethod
    def search_episodes(anime: str, url: str, params) -> None:
        """Mock episode search - returns hardcoded test data."""
        if anime == "Dandadan":
            repo = Repository()
            episode_titles = [f"Ep {i}" for i in range(1, 13)]
            episode_urls = [f"{url}/{i}" for i in range(1, 13)]
            repo.add_episode_list(
                anime, episode_titles, episode_urls, "mock_animesonlinecc"
            )

    @staticmethod
    def search_player_src(url_episode: str, container: list, event) -> None:
        """Mock video extraction - returns different URL."""
        container.append(VideoUrl(url="https://example2.com/video.m3u8"))
        event.set()

    @staticmethod
    def load(languages_dict):
        """Plugin load method."""
        pass


@pytest.fixture
def mock_plugins_fixture(repo_fresh):
    """Register mock plugins in Repository for testing."""
    # Clear any existing sources and reset
    repo_fresh.sources.clear()
    # Register only mock plugins for testing
    repo_fresh.register(MockPluginAnimefire)
    repo_fresh.register(MockPluginAnimesonlinecc)
    return repo_fresh


# ========== Mock Data Fixtures (JSON) ==========


@pytest.fixture
def mock_anilist_response_trending():
    """Mock AniList API response for trending anime."""
    return {
        "data": {
            "Page": {
                "media": [
                    {
                        "id": 1,
                        "title": {"userPreferred": "Dandadan"},
                        "averageScore": 85,
                        "popularity": 100000,
                    },
                    {
                        "id": 2,
                        "title": {"userPreferred": "Solo Leveling"},
                        "averageScore": 88,
                        "popularity": 95000,
                    },
                ]
            }
        }
    }


@pytest.fixture
def mock_anilist_response_user_list():
    """Mock AniList API response for user's watching list."""
    return {
        "data": {
            "MediaListCollection": {
                "lists": [
                    {
                        "name": "Watching",
                        "entries": [
                            {
                                "media": {
                                    "id": 1,
                                    "title": {"userPreferred": "Dandadan"},
                                },
                                "progress": 3,
                                "media": {"episodes": 12},
                            }
                        ],
                    }
                ]
            }
        }
    }


# ========== File I/O Fixtures ==========


@pytest.fixture
def temp_history_file():
    """Temporary history file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def temp_cache_dir():
    """Temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


# ========== Configuration Fixtures ==========


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("config.settings") as mock:
        mock.cache.duration_hours = 6
        mock.cache.cache_file = "/tmp/test_cache.json"
        mock.search.progressive_search_min_words = 2
        mock.anilist.api_url = "https://graphql.anilist.co"
        mock.anilist.client_id = "21576"
        mock.anilist.token_file = "/tmp/test_token.json"
        yield mock


# ========== Monkeypatch Helpers ==========


@pytest.fixture
def monkeypatch_settings(monkeypatch):
    """Monkeypatch settings for tests."""
    def set_setting(path: str, value):
        """Set a setting value using dot notation (e.g., 'cache.duration_hours')."""
        parts = path.split(".")
        obj = settings
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)

    return set_setting
