"""Tests for LocalAnimeService."""

import json
import tempfile
from pathlib import Path

import pytest

from models.models import (
    AnimeDownloadDatabase,
    AnimeDownloadHistory,
    DownloadedEpisode,
)
from services.local_anime_service import LocalAnimeService


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
def local_service(temp_download_dir, temp_state_dir, monkeypatch):
    """Create local anime service with temporary directories."""
    monkeypatch.setattr(
        "services.local_anime_service.settings.anime_download.download_directory",
        temp_download_dir,
    )
    monkeypatch.setenv("HOME", str(temp_state_dir))

    service = LocalAnimeService()
    service.db_path = temp_state_dir / "anime_downloads.json"
    return service


class TestLocalAnimeServiceBasic:
    """Test basic local anime service operations."""

    def test_service_initialization(self, local_service):
        """Service initializes correctly."""
        assert local_service.download_dir is not None

    def test_empty_library(self, local_service):
        """Empty library returns empty list."""
        anime_list = local_service.get_downloaded_anime_list()
        assert anime_list == []

    def test_get_anime_list_single(self, local_service, temp_download_dir):
        """Get list with single anime."""
        anime_dir = temp_download_dir / "Dandadan"
        anime_dir.mkdir()
        (anime_dir / "1.mkv").write_bytes(b"x" * 1000)

        anime_list = local_service.get_downloaded_anime_list()
        assert "Dandadan" in anime_list

    def test_get_anime_list_multiple(self, local_service, temp_download_dir):
        """Get list with multiple anime (sorted)."""
        titles = ["Dandadan", "Jujutsu Kaisen", "Chainsaw Man"]
        for title in titles:
            anime_dir = temp_download_dir / title
            anime_dir.mkdir()
            (anime_dir / "1.mkv").write_bytes(b"x" * 1000)

        anime_list = local_service.get_downloaded_anime_list()
        assert len(anime_list) == 3
        assert anime_list == sorted(titles)


class TestLocalAnimeServiceEpisodes:
    """Test episode discovery and listing."""

    def test_get_episodes_single(self, local_service, temp_download_dir):
        """Get single episode."""
        anime_dir = temp_download_dir / "Dandadan"
        anime_dir.mkdir()
        (anime_dir / "1.mkv").write_bytes(b"x" * 1000)

        episodes = local_service.get_downloaded_episodes("Dandadan")
        assert len(episodes) == 1
        assert episodes[0][0] == 1

    def test_get_episodes_range(self, local_service, temp_download_dir):
        """Get range of episodes."""
        anime_dir = temp_download_dir / "Dandadan"
        anime_dir.mkdir()
        for i in range(1, 6):
            (anime_dir / f"{i}.mkv").write_bytes(b"x" * 1000)

        episodes = local_service.get_downloaded_episodes("Dandadan")
        assert len(episodes) == 5
        # Check sorted
        assert [ep[0] for ep in episodes] == [1, 2, 3, 4, 5]

    def test_get_episodes_mixed_formats(self, local_service, temp_download_dir):
        """Get episodes in different formats."""
        anime_dir = temp_download_dir / "Dandadan"
        anime_dir.mkdir()
        (anime_dir / "1.mkv").write_bytes(b"x" * 1000)
        (anime_dir / "2.mp4").write_bytes(b"x" * 1000)
        (anime_dir / "3.webm").write_bytes(b"x" * 1000)

        episodes = local_service.get_downloaded_episodes("Dandadan")
        assert len(episodes) == 3

    def test_get_episodes_ignores_non_video(self, local_service, temp_download_dir):
        """Non-video files are ignored."""
        anime_dir = temp_download_dir / "Dandadan"
        anime_dir.mkdir()
        (anime_dir / "1.mkv").write_bytes(b"x" * 1000)
        (anime_dir / "README.txt").write_bytes(b"text")
        (anime_dir / ".metadata").write_bytes(b"meta")

        episodes = local_service.get_downloaded_episodes("Dandadan")
        assert len(episodes) == 1

    def test_get_episodes_nonexistent_anime(self, local_service):
        """Getting episodes of nonexistent anime raises error."""
        with pytest.raises(FileNotFoundError):
            local_service.get_downloaded_episodes("Nonexistent")


class TestLocalAnimeServiceMetadata:
    """Test episode metadata retrieval."""

    def test_get_episode_metadata(self, local_service, temp_download_dir, temp_state_dir):
        """Get metadata for downloaded episode."""
        anime_title = "Dandadan"
        anime_dir = temp_download_dir / anime_title
        anime_dir.mkdir()

        ep_path = anime_dir / "1.mkv"
        ep_path.write_bytes(b"x" * (2 * 1024 * 1024))

        # Create database entry
        db = AnimeDownloadDatabase()
        history = AnimeDownloadHistory(anime_title=anime_title)
        history.episodes[1] = DownloadedEpisode(
            episode_number=1,
            file_path=ep_path,
            file_size_mb=2.0,
            source="animefire",
            status="success",
        )
        db.anime[anime_title] = history

        db_path = temp_state_dir / "anime_downloads.json"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(db_path, "w") as f:
            json.dump(db.model_dump(mode="json"), f, default=str)

        local_service.db_path = db_path

        # Get metadata
        metadata = local_service.get_episode_metadata(anime_title, 1)
        assert metadata is not None
        assert metadata["episode_number"] == 1
        assert metadata["file_size_mb"] == 2.0
        assert metadata["source"] == "animefire"

    def test_get_episode_metadata_not_found(self, local_service):
        """Getting metadata of nonexistent episode returns None."""
        metadata = local_service.get_episode_metadata("Nonexistent", 1)
        assert metadata is None


class TestLocalAnimeServiceInfo:
    """Test anime info retrieval."""

    def test_get_anime_info(self, local_service, temp_download_dir):
        """Get anime info."""
        anime_title = "Dandadan"
        anime_dir = temp_download_dir / anime_title
        anime_dir.mkdir()

        for i in range(1, 6):
            (anime_dir / f"{i}.mkv").write_bytes(b"x" * (1 * 1024 * 1024))

        info = local_service.get_anime_info(anime_title)
        assert info["title"] == anime_title
        assert info["total_episodes"] == 5
        assert info["total_size_mb"] > 0
        assert info["episode_numbers"] == [1, 2, 3, 4, 5]

    def test_get_anime_info_nonexistent(self, local_service):
        """Getting info of nonexistent anime returns empty info."""
        info = local_service.get_anime_info("Nonexistent")
        assert info["title"] == "Nonexistent"
        assert info["total_episodes"] == 0
        assert info["total_size_mb"] == 0.0


class TestLocalAnimeServiceDeletion:
    """Test episode and anime deletion."""

    def test_delete_episode(self, local_service, temp_download_dir):
        """Delete a single episode."""
        anime_title = "Dandadan"
        anime_dir = temp_download_dir / anime_title
        anime_dir.mkdir()
        (anime_dir / "1.mkv").write_bytes(b"x" * 1000)
        (anime_dir / "2.mkv").write_bytes(b"x" * 1000)

        # Delete episode 1
        result = local_service.delete_episode(anime_title, 1)
        assert result is True
        assert not (anime_dir / "1.mkv").exists()
        assert (anime_dir / "2.mkv").exists()

    def test_delete_episode_not_found(self, local_service):
        """Deleting nonexistent episode returns False."""
        result = local_service.delete_episode("Nonexistent", 1)
        assert result is False

    def test_delete_anime(self, local_service, temp_download_dir):
        """Delete entire anime."""
        anime_title = "Dandadan"
        anime_dir = temp_download_dir / anime_title
        anime_dir.mkdir()
        for i in range(1, 6):
            (anime_dir / f"{i}.mkv").write_bytes(b"x" * 1000)

        result = local_service.delete_anime(anime_title)
        assert result is True
        assert not anime_dir.exists()

    def test_delete_anime_not_found(self, local_service):
        """Deleting nonexistent anime returns False."""
        result = local_service.delete_anime("Nonexistent")
        assert result is False


class TestLocalAnimeServiceCorruptedCleanup:
    """Test corrupted episode handling."""

    def test_clear_corrupted_episodes(self, local_service, temp_state_dir):
        """Clear corrupted episodes from database."""
        anime_title = "Dandadan"

        # Create database with corrupted episode
        db = AnimeDownloadDatabase()
        history = AnimeDownloadHistory(anime_title=anime_title)
        history.episodes[1] = DownloadedEpisode(
            episode_number=1,
            file_path=Path("/fake/1.mkv"),
            file_size_mb=1.0,
            source="test",
            status="success",
        )
        history.episodes[2] = DownloadedEpisode(
            episode_number=2,
            file_path=Path("/fake/2.mkv"),
            file_size_mb=1.0,
            source="test",
            status="corrupted",
        )
        history.episodes[3] = DownloadedEpisode(
            episode_number=3,
            file_path=Path("/fake/3.mkv"),
            file_size_mb=1.0,
            source="test",
            status="corrupted",
        )
        db.anime[anime_title] = history

        db_path = temp_state_dir / "anime_downloads.json"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(db_path, "w") as f:
            json.dump(db.model_dump(mode="json"), f, default=str)

        local_service.db_path = db_path

        # Clear corrupted
        cleared = local_service.clear_corrupted_episodes(anime_title)
        assert cleared == [2, 3]

        # Verify database updated
        db2 = local_service._load_database()
        assert 1 in db2.anime[anime_title].episodes
        assert 2 not in db2.anime[anime_title].episodes
        assert 3 not in db2.anime[anime_title].episodes
