"""Tests for anime download models."""

from pathlib import Path

import pytest

from models.models import (
    AnimeDownloadDatabase,
    AnimeDownloadHistory,
    DownloadResult,
    DownloadedEpisode,
)


class TestDownloadedEpisode:
    """Test DownloadedEpisode model."""

    def test_create_downloaded_episode(self):
        """Create a downloaded episode."""
        ep = DownloadedEpisode(
            episode_number=1,
            file_path=Path("/home/user/.local/share/ani-tupi/anime/Dandadan/1.mkv"),
            file_size_mb=512.5,
            source="animefire",
        )
        assert ep.episode_number == 1
        assert ep.file_size_mb == 512.5
        assert ep.source == "animefire"
        assert ep.status == "success"

    def test_episode_validation_negative_number(self):
        """Negative episode number fails."""
        with pytest.raises(ValueError):
            DownloadedEpisode(
                episode_number=-1,
                file_path=Path("/home/user/.local/share/ani-tupi/anime/Test/1.mkv"),
                file_size_mb=100.0,
                source="test",
            )

    def test_episode_validation_zero_number(self):
        """Zero episode number fails."""
        with pytest.raises(ValueError):
            DownloadedEpisode(
                episode_number=0,
                file_path=Path("/home/user/.local/share/ani-tupi/anime/Test/1.mkv"),
                file_size_mb=100.0,
                source="test",
            )

    def test_episode_negative_size_fails(self):
        """Negative file size fails."""
        with pytest.raises(ValueError):
            DownloadedEpisode(
                episode_number=1,
                file_path=Path("/home/user/.local/share/ani-tupi/anime/Test/1.mkv"),
                file_size_mb=-100.0,
                source="test",
            )

    def test_episode_custom_status(self):
        """Custom download status."""
        ep = DownloadedEpisode(
            episode_number=5,
            file_path=Path("/home/user/.local/share/ani-tupi/anime/Test/5.mkv"),
            file_size_mb=256.0,
            source="animesdigital",
            status="corrupted",
        )
        assert ep.status == "corrupted"


class TestDownloadResult:
    """Test DownloadResult model."""

    def test_download_result_success(self):
        """Successful download result."""
        result = DownloadResult(
            successful=12,
            summary="✓ 12/12 episódios baixados com sucesso",
        )
        assert result.successful == 12
        assert len(result.failed) == 0
        assert len(result.skipped) == 0

    def test_download_result_partial_success(self):
        """Partial download result."""
        result = DownloadResult(
            successful=10,
            failed=[3, 7],
            skipped=[1, 2],
            summary="✓ 10/12 episódios baixados (2 falharam, 2 já existiam)",
        )
        assert result.successful == 10
        assert result.failed == [3, 7]
        assert result.skipped == [1, 2]

    def test_download_result_all_failed(self):
        """All downloads failed."""
        result = DownloadResult(
            successful=0,
            failed=[1, 2, 3, 4, 5],
            summary="❌ Todos os downloads falharam",
        )
        assert result.successful == 0
        assert len(result.failed) == 5

    def test_download_result_with_corrupted(self):
        """Result with corrupted downloads."""
        result = DownloadResult(
            successful=8,
            corrupted=[5, 9],
            summary="⚠️ 8 episódios salvos, 2 corrompidos",
        )
        assert result.successful == 8
        assert result.corrupted == [5, 9]


class TestAnimeDownloadHistory:
    """Test AnimeDownloadHistory model."""

    def test_create_empty_history(self):
        """Create empty anime download history."""
        history = AnimeDownloadHistory(anime_title="Dandadan")
        assert history.anime_title == "Dandadan"
        assert len(history.episodes) == 0
        assert history.total_size_mb == 0.0

    def test_add_episode_to_history(self):
        """Add episode to history."""
        history = AnimeDownloadHistory(anime_title="Dandadan")
        ep = DownloadedEpisode(
            episode_number=1,
            file_path=Path("/home/user/.local/share/ani-tupi/anime/Dandadan/1.mkv"),
            file_size_mb=512.0,
            source="animefire",
        )
        # Manually add episode (service layer would do this)
        history.episodes[1] = ep
        assert history.has_episode(1)

    def test_get_episode_numbers(self):
        """Get sorted episode numbers."""
        history = AnimeDownloadHistory(anime_title="Dandadan")
        for num in [5, 1, 3, 2, 4]:
            history.episodes[num] = DownloadedEpisode(
                episode_number=num,
                file_path=Path(f"/home/user/.local/share/ani-tupi/anime/Dandadan/{num}.mkv"),
                file_size_mb=512.0,
                source="animefire",
            )
        assert history.get_episode_numbers() == [1, 2, 3, 4, 5]

    def test_has_episode_success(self):
        """Check if episode exists with success status."""
        history = AnimeDownloadHistory(anime_title="Dandadan")
        history.episodes[1] = DownloadedEpisode(
            episode_number=1,
            file_path=Path("/home/user/.local/share/ani-tupi/anime/Dandadan/1.mkv"),
            file_size_mb=512.0,
            source="animefire",
            status="success",
        )
        assert history.has_episode(1)

    def test_has_episode_failed(self):
        """Episode with failed status doesn't count as 'has'."""
        history = AnimeDownloadHistory(anime_title="Dandadan")
        history.episodes[2] = DownloadedEpisode(
            episode_number=2,
            file_path=Path("/home/user/.local/share/ani-tupi/anime/Dandadan/2.mkv"),
            file_size_mb=0.0,
            source="animefire",
            status="failed",
        )
        assert not history.has_episode(2)

    def test_has_episode_corrupted(self):
        """Episode with corrupted status doesn't count as 'has'."""
        history = AnimeDownloadHistory(anime_title="Dandadan")
        history.episodes[3] = DownloadedEpisode(
            episode_number=3,
            file_path=Path("/home/user/.local/share/ani-tupi/anime/Dandadan/3.mkv"),
            file_size_mb=256.0,
            source="animefire",
            status="corrupted",
        )
        assert not history.has_episode(3)

    def test_validation_empty_title(self):
        """Empty anime title fails."""
        with pytest.raises(ValueError):
            AnimeDownloadHistory(anime_title="")


class TestAnimeDownloadDatabase:
    """Test AnimeDownloadDatabase model."""

    def test_create_empty_database(self):
        """Create empty download database."""
        db = AnimeDownloadDatabase()
        assert db.version == 1
        assert len(db.anime) == 0

    def test_add_anime_to_database(self):
        """Add anime to database."""
        db = AnimeDownloadDatabase()
        history = AnimeDownloadHistory(anime_title="Dandadan")
        history.episodes[1] = DownloadedEpisode(
            episode_number=1,
            file_path=Path("/home/user/.local/share/ani-tupi/anime/Dandadan/1.mkv"),
            file_size_mb=512.0,
            source="animefire",
        )
        db.anime["Dandadan"] = history
        assert "Dandadan" in db.anime
        assert db.anime["Dandadan"].has_episode(1)

    def test_database_serialization(self):
        """Database can be serialized to JSON."""
        db = AnimeDownloadDatabase()
        history = AnimeDownloadHistory(anime_title="Dandadan")
        history.episodes[1] = DownloadedEpisode(
            episode_number=1,
            file_path=Path("/home/user/.local/share/ani-tupi/anime/Dandadan/1.mkv"),
            file_size_mb=512.0,
            source="animefire",
        )
        db.anime["Dandadan"] = history

        # Serialize
        json_str = db.model_dump_json()
        assert "Dandadan" in json_str
        assert "512.0" in json_str

        # Deserialize
        db2 = AnimeDownloadDatabase.model_validate_json(json_str)
        assert "Dandadan" in db2.anime
        assert db2.anime["Dandadan"].has_episode(1)

    def test_database_multiple_anime(self):
        """Database with multiple anime."""
        db = AnimeDownloadDatabase()

        for title in ["Dandadan", "Jujutsu Kaisen", "Chainsaw Man"]:
            history = AnimeDownloadHistory(anime_title=title)
            for ep_num in range(1, 6):
                history.episodes[ep_num] = DownloadedEpisode(
                    episode_number=ep_num,
                    file_path=Path(f"/home/user/.local/share/ani-tupi/anime/{title}/{ep_num}.mkv"),
                    file_size_mb=512.0,
                    source="animefire",
                )
            db.anime[title] = history

        assert len(db.anime) == 3
        assert all(db.anime[title].has_episode(1) for title in db.anime)
