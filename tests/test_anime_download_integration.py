"""Integration tests for anime download feature.

Tests the complete workflow:
1. Download episodes
2. Access local library
3. Play downloaded episodes
4. Delete downloaded content
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from services.anime.download_service import AnimeDownloadService
from services.local_anime_service import LocalAnimeService
from utils.episode_range_parser import parse_episode_range


@pytest.fixture
def temp_download_dir():
    """Create temporary directory for downloads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_state_dir():
    """Create temporary directory for state files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def services(temp_download_dir, temp_state_dir, monkeypatch):
    """Create download and local services with temporary directories."""
    monkeypatch.setattr(
        "services.anime.download_service.settings.anime_download.download_directory",
        temp_download_dir,
    )
    monkeypatch.setattr(
        "services.local_anime_service.settings.anime_download.download_directory",
        temp_download_dir,
    )
    monkeypatch.setattr(
        "services.anime.download_service.settings.anime_download.max_parallel_downloads",
        2,
    )
    monkeypatch.setenv("HOME", str(temp_state_dir))

    download_service = AnimeDownloadService()
    download_service.db_path = temp_state_dir / "anime_downloads.json"

    local_service = LocalAnimeService()
    local_service.db_path = temp_state_dir / "anime_downloads.json"

    return {
        "download": download_service,
        "local": local_service,
        "download_dir": temp_download_dir,
        "state_dir": temp_state_dir,
    }


class TestDownloadToLocalLibraryWorkflow:
    """Test complete workflow from download to playback."""

    def test_complete_download_and_library_flow(self, services):
        """Complete workflow: download → list → access episodes."""
        anime_title = "Dandadan"
        total_eps = 12

        # 1. Download episodes (with actual file creation)
        def mock_download_file(url, file_path):
            """Mock download that creates actual files."""
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB file
            return True

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "animefire")

        with patch.object(services["download"], "_download_file", side_effect=mock_download_file):
            with patch.object(services["download"], "_validate_file", return_value=True):
                result = services["download"].download_episodes(
                    anime_title,
                    "1-5",
                    total_eps,
                    mock_url_getter,
                )

        assert result.successful == 5
        print(f"\n✓ Downloaded: {result.summary}")

        # 2. Check local library lists the anime
        anime_list = services["local"].get_downloaded_anime_list()
        assert anime_title in anime_list
        print(f"✓ Local library has: {anime_list}")

        # 3. Get anime info
        info = services["local"].get_anime_info(anime_title)
        assert info["total_episodes"] == 5
        assert set(info["episode_numbers"]) == {1, 2, 3, 4, 5}
        print(f"✓ Anime info: {info['total_episodes']} episodes")

        # 4. Get episode list
        episodes = services["local"].get_downloaded_episodes(anime_title)
        assert len(episodes) == 5
        print(f"✓ Episode list: {[ep[0] for ep in episodes]}")

        # 5. Get metadata for specific episode
        metadata = services["local"].get_episode_metadata(anime_title, 1)
        assert metadata is not None
        assert metadata["episode_number"] == 1
        print(f"✓ Episode 1 metadata: {metadata['file_size_mb']}MB")

    def test_multi_anime_library(self, services):
        """Test library with multiple anime."""

        # Download multiple anime
        def mock_download_file(url, file_path):
            """Mock download that creates actual files."""
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"x" * (2 * 1024 * 1024))
            return True

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "test")

        titles = ["Dandadan", "Jujutsu Kaisen", "Chainsaw Man"]
        for title in titles:
            with patch.object(
                services["download"], "_download_file", side_effect=mock_download_file
            ):
                with patch.object(services["download"], "_validate_file", return_value=True):
                    services["download"].download_episodes(
                        title,
                        "1-3",
                        12,
                        mock_url_getter,
                    )

        # List all anime
        anime_list = services["local"].get_downloaded_anime_list()
        assert len(anime_list) == 3
        assert set(anime_list) == set(titles)
        print(f"✓ Library has {len(anime_list)} anime: {sorted(anime_list)}")

        # Check each anime
        for title in titles:
            info = services["local"].get_anime_info(title)
            assert info["total_episodes"] == 3
            print(f"✓ {title}: {info['total_episodes']} episodes")

    def test_episode_deletion_updates_library(self, services):
        """Deleting episode updates local library."""
        anime_title = "Dandadan"

        # Download episodes
        def mock_download_file(url, file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"x" * (2 * 1024 * 1024))
            return True

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "test")

        with patch.object(services["download"], "_download_file", side_effect=mock_download_file):
            with patch.object(services["download"], "_validate_file", return_value=True):
                services["download"].download_episodes(
                    anime_title,
                    "1-5",
                    12,
                    mock_url_getter,
                )

        # Verify initial state
        episodes = services["local"].get_downloaded_episodes(anime_title)
        assert len(episodes) == 5
        print(f"✓ Initial: {len(episodes)} episodes")

        # Delete episode 3
        deleted = services["local"].delete_episode(anime_title, 3)
        assert deleted is True

        # Verify updated state
        episodes = services["local"].get_downloaded_episodes(anime_title)
        assert len(episodes) == 4
        assert 3 not in [ep[0] for ep in episodes]
        print(f"✓ After deletion: {len(episodes)} episodes")

    def test_anime_deletion_removes_from_library(self, services):
        """Deleting all anime episodes removes from library."""
        anime_title = "Dandadan"

        # Download episodes
        def mock_download_file(url, file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"x" * (2 * 1024 * 1024))
            return True

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "test")

        with patch.object(services["download"], "_download_file", side_effect=mock_download_file):
            with patch.object(services["download"], "_validate_file", return_value=True):
                services["download"].download_episodes(
                    anime_title,
                    "1-5",
                    12,
                    mock_url_getter,
                )

        # Verify in library
        anime_list = services["local"].get_downloaded_anime_list()
        assert anime_title in anime_list

        # Delete entire anime
        deleted = services["local"].delete_anime(anime_title)
        assert deleted is True

        # Verify removed from library
        anime_list = services["local"].get_downloaded_anime_list()
        assert anime_title not in anime_list
        print("✓ Anime removed from library")


class TestRangeParsingIntegration:
    """Test episode range parsing with downloads."""

    def test_single_episode_download(self, services):
        """Download single episode using parsed range."""
        anime_title = "Dandadan"
        range_str = "5"
        total_eps = 12

        # Parse range
        episodes = parse_episode_range(range_str, total_eps)
        assert episodes == [5]

        # Download
        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "test")

        with patch.object(services["download"], "_download_file", return_value=True):
            with patch.object(services["download"], "_validate_file", return_value=True):
                result = services["download"].download_episodes(
                    anime_title,
                    range_str,
                    total_eps,
                    mock_url_getter,
                )

        assert result.successful == 1
        print("✓ Single episode download")

    def test_range_with_dash_download(self, services):
        """Download range like 5-12."""
        anime_title = "Dandadan"
        range_str = "5-12"
        total_eps = 24

        episodes = parse_episode_range(range_str, total_eps)
        assert len(episodes) == 8
        assert episodes[0] == 5
        assert episodes[-1] == 12

        # Download
        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "test")

        with patch.object(services["download"], "_download_file", return_value=True):
            with patch.object(services["download"], "_validate_file", return_value=True):
                result = services["download"].download_episodes(
                    anime_title,
                    range_str,
                    total_eps,
                    mock_url_getter,
                )

        assert result.successful == 8
        print("✓ Range download (5-12)")

    def test_open_ended_range_download(self, services):
        """Download open-ended range like 5-."""
        anime_title = "Dandadan"
        range_str = "5-"
        total_eps = 10

        episodes = parse_episode_range(range_str, total_eps)
        assert episodes == [5, 6, 7, 8, 9, 10]

        # Download
        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "test")

        with patch.object(services["download"], "_download_file", return_value=True):
            with patch.object(services["download"], "_validate_file", return_value=True):
                result = services["download"].download_episodes(
                    anime_title,
                    range_str,
                    total_eps,
                    mock_url_getter,
                )

        assert result.successful == 6
        print("✓ Open-ended range download (5-)")


class TestDatabasePersistence:
    """Test database persistence across service instances."""

    def test_database_survives_service_reload(self, services):
        """Downloaded episodes persist across service instances."""
        anime_title = "Dandadan"

        # Download with first service instance
        def mock_download_file(url, file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"x" * (2 * 1024 * 1024))
            return True

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "test")

        with patch.object(services["download"], "_download_file", side_effect=mock_download_file):
            with patch.object(services["download"], "_validate_file", return_value=True):
                services["download"].download_episodes(
                    anime_title,
                    "1-5",
                    12,
                    mock_url_getter,
                )

        # Create new service instance
        new_service = LocalAnimeService()
        new_service.db_path = services["state_dir"] / "anime_downloads.json"

        # Verify episodes are accessible
        anime_list = new_service.get_downloaded_anime_list()
        assert anime_title in anime_list

        episodes = new_service.get_downloaded_episodes(anime_title)
        assert len(episodes) == 5
        print("✓ Database persistence verified")

    def test_skip_already_downloaded_across_sessions(self, services):
        """Skip logic works across service instances."""
        anime_title = "Dandadan"

        def mock_download_file(url, file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"x" * (2 * 1024 * 1024))
            return True

        # First download: episodes 1-5
        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "test")

        with patch.object(services["download"], "_download_file", side_effect=mock_download_file):
            with patch.object(services["download"], "_validate_file", return_value=True):
                result1 = services["download"].download_episodes(
                    anime_title,
                    "1-5",
                    12,
                    mock_url_getter,
                )

        assert result1.successful == 5

        # Second download: episodes 1-8 (1-5 should be skipped)
        with patch.object(services["download"], "_download_file", side_effect=mock_download_file):
            with patch.object(services["download"], "_validate_file", return_value=True):
                result2 = services["download"].download_episodes(
                    anime_title,
                    "1-8",
                    12,
                    mock_url_getter,
                )

        assert result2.successful == 3  # Only 6, 7, 8
        assert set(result2.skipped) == {1, 2, 3, 4, 5}
        print("✓ Skip logic across sessions working")
