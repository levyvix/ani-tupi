"""Tests for AnimeDownloadService."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from models.models import AnimeDownloadDatabase, DownloadedEpisode
from services.anime.download_service import AnimeDownloadService
from utils.episode_range_parser import RangeParseError


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
def download_service(temp_download_dir, temp_state_dir, monkeypatch):
    """Create download service with temporary directories."""
    # Patch config
    monkeypatch.setattr(
        "services.anime.download_service.settings.anime_download.download_directory",
        temp_download_dir,
    )
    monkeypatch.setattr(
        "services.anime.download_service.settings.anime_download.max_parallel_downloads",
        2,
    )
    monkeypatch.setattr(
        "services.anime.download_service.settings.anime_download.skip_already_downloaded",
        True,
    )
    monkeypatch.setattr(
        "services.anime.download_service.settings.anime_download.video_format",
        "mkv",
    )
    monkeypatch.setenv("HOME", str(temp_state_dir))

    service = AnimeDownloadService()
    service.db_path = temp_state_dir / "anime_downloads.json"
    return service


class TestAnimeDownloadServiceBasic:
    """Test basic download service operations."""

    def test_service_initialization(self, download_service):
        """Service initializes correctly."""
        assert download_service.download_dir.exists()
        assert download_service.db_path.parent.exists()
        assert download_service.max_parallel == 2

    def test_load_empty_database(self, download_service):
        """Load non-existent database returns empty."""
        db = download_service._load_database()
        assert len(db.anime) == 0
        assert db.version == 1

    def test_save_and_load_database(self, download_service):
        """Save and load database preserves data."""
        from models.models import AnimeDownloadHistory

        # Create and save
        db = AnimeDownloadDatabase()
        history = AnimeDownloadHistory(anime_title="Dandadan")
        db.anime["Dandadan"] = history
        download_service._save_database(db)

        # Load and verify
        db2 = download_service._load_database()
        assert "Dandadan" in db2.anime
        assert db2.anime["Dandadan"].anime_title == "Dandadan"


class TestAnimeDownloadServiceRangeValidation:
    """Test range validation."""

    def test_invalid_range_raises_error(self, download_service):
        """Invalid range raises RangeParseError."""

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}", "test")

        with pytest.raises(RangeParseError):
            download_service.download_episodes(
                "Test",
                "invalid",
                12,
                mock_url_getter,
            )

    def test_out_of_bounds_range_gets_clamped(self, download_service):
        """Out of bounds range gets clamped to valid range."""

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}", "test")

        # "1-50" with total 12 gets clamped to "1-12"
        with patch.object(download_service, "_download_file", return_value=False):
            result = download_service.download_episodes(
                "Test",
                "1-50",
                12,
                mock_url_getter,
            )

        # Should not raise, but handle gracefully
        assert result.successful >= 0


class TestAnimeDownloadServiceSkipExisting:
    """Test skipping already-downloaded episodes."""

    def test_skip_already_downloaded(self, download_service):
        """Already-downloaded episodes are skipped."""
        from models.models import AnimeDownloadHistory

        anime_title = "Dandadan"
        total_episodes = 12

        # Create episode 1 already downloaded
        anime_dir = download_service.download_dir / anime_title
        anime_dir.mkdir(parents=True, exist_ok=True)
        ep1_path = anime_dir / "1.mkv"
        ep1_path.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB file

        # Update database
        db = download_service._load_database()
        history = AnimeDownloadHistory(anime_title=anime_title)
        history.episodes[1] = DownloadedEpisode(
            episode_number=1,
            file_path=ep1_path,
            file_size_mb=2.0,
            source="test",
            status="success",
        )
        db.anime[anime_title] = history
        download_service._save_database(db)

        # Mock URL getter
        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}", "test")

        # Mock file download
        with patch.object(download_service, "_download_file", return_value=True):
            with patch.object(download_service, "_validate_file", return_value=True):
                result = download_service.download_episodes(
                    anime_title,
                    "1-3",
                    total_episodes,
                    mock_url_getter,
                )

        # Episode 1 should be skipped
        assert 1 in result.skipped
        # Episodes 2-3 should be downloaded
        assert result.successful == 2


class TestAnimeDownloadServiceDirectoryCreation:
    """Test directory structure creation."""

    def test_anime_directory_created(self, download_service):
        """Anime directory is created on download."""
        anime_title = "Test Anime"

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}", "test")

        with patch.object(download_service, "_download_file", return_value=False):
            download_service.download_episodes(
                anime_title,
                "1",
                12,
                mock_url_getter,
            )

        anime_dir = download_service.download_dir / anime_title
        assert anime_dir.exists()


class TestAnimeDownloadServiceFileValidation:
    """Test file validation."""

    def test_validate_file_too_small(self, download_service, temp_download_dir):
        """File smaller than 1MB is invalid."""
        test_file = temp_download_dir / "small.mkv"
        test_file.write_bytes(b"x" * 100)  # 100 bytes

        assert not download_service._validate_file(test_file)

    def test_validate_file_valid(self, download_service, temp_download_dir):
        """File larger than 1MB is valid."""
        test_file = temp_download_dir / "large.mkv"
        test_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB

        assert download_service._validate_file(test_file)

    def test_validate_nonexistent_file(self, download_service):
        """Nonexistent file is invalid."""
        assert not download_service._validate_file(Path("/nonexistent/file.mkv"))


class TestAnimeDownloadServiceSummary:
    """Test summary generation."""

    def test_summary_all_successful(self, download_service):
        """Summary for all successful downloads."""
        summary = download_service._build_summary(5, 5, [], [], [])
        assert "✓ 5/5" in summary
        assert "❌" not in summary

    def test_summary_partial_failure(self, download_service):
        """Summary for partial failure."""
        summary = download_service._build_summary(3, 5, [1, 2], [], [])
        assert "✓ 3/5" in summary
        assert "❌ 2 falharam" in summary

    def test_summary_with_corrupted(self, download_service):
        """Summary with corrupted files."""
        summary = download_service._build_summary(2, 5, [], [3, 4], [])
        assert "⚠️" in summary
        assert "2 corrompidos" in summary

    def test_summary_with_skipped(self, download_service):
        """Summary with skipped episodes."""
        summary = download_service._build_summary(3, 5, [], [], [1, 2])
        assert "⊘ 2 já existiam" in summary


class TestAnimeDownloadServiceIntegration:
    """Integration tests for complete download flow."""

    def test_download_single_episode(self, download_service):
        """Download single episode successfully."""
        anime_title = "Dandadan"

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "animefire")

        with patch.object(download_service, "_download_file", return_value=True):
            with patch.object(download_service, "_validate_file", return_value=True):
                result = download_service.download_episodes(
                    anime_title,
                    "1",
                    12,
                    mock_url_getter,
                )

        assert result.successful == 1
        assert len(result.failed) == 0

    def test_download_range(self, download_service):
        """Download range of episodes."""
        anime_title = "Dandadan"

        def mock_url_getter(ep_num):
            return (f"https://example.com/ep{ep_num}.mkv", "animefire")

        with patch.object(download_service, "_download_file", return_value=True):
            with patch.object(download_service, "_validate_file", return_value=True):
                result = download_service.download_episodes(
                    anime_title,
                    "1-3",
                    12,
                    mock_url_getter,
                )

        assert result.successful == 3
        assert len(result.failed) == 0

    def test_download_handles_no_url(self, download_service):
        """Handle case where episode URL is not found."""
        anime_title = "Dandadan"

        def mock_url_getter(ep_num):
            # Return None for some episodes
            if ep_num == 2:
                return None
            return (f"https://example.com/ep{ep_num}.mkv", "animefire")

        with patch.object(download_service, "_download_file", return_value=True):
            with patch.object(download_service, "_validate_file", return_value=True):
                result = download_service.download_episodes(
                    anime_title,
                    "1-3",
                    12,
                    mock_url_getter,
                )

        assert result.successful == 2
        assert 2 in result.failed
