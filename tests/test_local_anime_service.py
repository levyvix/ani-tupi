"""Tests for LocalAnimeService.

Uses real file I/O via tmp_path — no mocking of internal code.
Only external tools (video players, HTTP) would be mocked, but this
service has none, so everything runs against real temp directories.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from models.models import (
    AnimeDownloadDatabase,
    AnimeDownloadHistory,
    DownloadedEpisode,
)
from services.anime.local_anime_service import LocalAnimeService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(tmp_path: Path, monkeypatch) -> LocalAnimeService:
    """Return a LocalAnimeService wired to tmp_path directories."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    db_path = tmp_path / "state" / "ani-tupi" / "anime_downloads.json"

    monkeypatch.setattr("models.config.settings.anime_download.download_directory", download_dir)

    svc = LocalAnimeService.__new__(LocalAnimeService)
    svc.download_dir = download_dir
    svc.db_path = db_path
    return svc


def _add_episode_file(
    anime_dir: Path, episode_num: int, ext: str = ".mkv", size_bytes: int = 1024 * 1024
) -> Path:
    """Create a dummy video file for an episode (default 1 MB)."""
    anime_dir.mkdir(parents=True, exist_ok=True)
    ep_file = anime_dir / f"{episode_num}{ext}"
    ep_file.write_bytes(b"x" * size_bytes)
    return ep_file


def _write_db(db_path: Path, db: AnimeDownloadDatabase) -> None:
    """Persist a database to disk."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with open(db_path, "w") as f:
        json.dump(db.model_dump(mode="json"), f, default=str)


def _make_episode_record(
    episode_number: int,
    file_path: Path,
    file_size_mb: float = 100.0,
    source: str = "test_source",
    status: str = "success",
) -> DownloadedEpisode:
    return DownloadedEpisode(
        episode_number=episode_number,
        file_path=file_path,
        file_size_mb=file_size_mb,
        source=source,
        downloaded_at=datetime.now(),
        status=status,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def svc(tmp_path, monkeypatch):
    return _make_service(tmp_path, monkeypatch)


# ---------------------------------------------------------------------------
# get_downloaded_anime_list
# ---------------------------------------------------------------------------


class TestGetDownloadedAnimeList:
    def test_empty_download_dir_returns_empty_list(self, svc):
        result = svc.get_downloaded_anime_list()
        assert result == []

    def test_download_dir_does_not_exist_returns_empty_list(self, svc):
        svc.download_dir = svc.download_dir / "nonexistent"
        result = svc.get_downloaded_anime_list()
        assert result == []

    def test_returns_anime_with_video_files(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        _add_episode_file(anime_dir, 1)

        result = svc.get_downloaded_anime_list()
        assert result == ["Naruto"]

    def test_ignores_dirs_without_video_files(self, svc):
        empty_dir = svc.download_dir / "EmptyAnime"
        empty_dir.mkdir()
        (empty_dir / "notes.txt").write_text("not a video")

        result = svc.get_downloaded_anime_list()
        assert result == []

    def test_returns_sorted_list(self, svc):
        for name in ["Zoro", "Attack on Titan", "Bleach"]:
            _add_episode_file(svc.download_dir / name, 1)

        result = svc.get_downloaded_anime_list()
        assert result == ["Attack on Titan", "Bleach", "Zoro"]

    def test_all_video_extensions_recognised(self, svc):
        for ext in [".mkv", ".mp4", ".avi", ".webm"]:
            anime_name = f"Anime_{ext[1:]}"
            anime_dir = svc.download_dir / anime_name
            _add_episode_file(anime_dir, 1, ext=ext)

        result = svc.get_downloaded_anime_list()
        assert len(result) == 4


# ---------------------------------------------------------------------------
# get_downloaded_episodes
# ---------------------------------------------------------------------------


class TestGetDownloadedEpisodes:
    def test_raises_when_anime_dir_missing(self, svc):
        with pytest.raises(FileNotFoundError):
            svc.get_downloaded_episodes("NoSuchAnime")

    def test_returns_episodes_sorted(self, svc):
        anime_dir = svc.download_dir / "Bleach"
        for ep in [3, 1, 2]:
            _add_episode_file(anime_dir, ep)

        result = svc.get_downloaded_episodes("Bleach")
        assert [n for n, _ in result] == [1, 2, 3]

    def test_skips_files_with_non_numeric_names(self, svc):
        anime_dir = svc.download_dir / "Bleach"
        anime_dir.mkdir()
        _add_episode_file(anime_dir, 1)
        (anime_dir / "extra-stuff.mkv").write_bytes(b"data")

        result = svc.get_downloaded_episodes("Bleach")
        assert len(result) == 1
        assert result[0][0] == 1

    def test_non_video_files_ignored(self, svc):
        anime_dir = svc.download_dir / "Bleach"
        anime_dir.mkdir()
        _add_episode_file(anime_dir, 1)
        (anime_dir / "1.srt").write_text("subtitle")

        result = svc.get_downloaded_episodes("Bleach")
        assert len(result) == 1

    def test_empty_anime_dir_returns_empty_list(self, svc):
        anime_dir = svc.download_dir / "EmptyAnime"
        anime_dir.mkdir()

        result = svc.get_downloaded_episodes("EmptyAnime")
        assert result == []

    def test_invalid_title_raises_value_error(self, svc):
        with pytest.raises(ValueError):
            svc.get_downloaded_episodes("../etc/passwd")

    def test_returns_correct_paths(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        ep_file = _add_episode_file(anime_dir, 5)

        result = svc.get_downloaded_episodes("Naruto")
        assert result[0] == (5, ep_file)


# ---------------------------------------------------------------------------
# get_episode_metadata
# ---------------------------------------------------------------------------


class TestGetEpisodeMetadata:
    def test_returns_none_when_db_empty(self, svc):
        result = svc.get_episode_metadata("Naruto", 1)
        assert result is None

    def test_returns_none_when_anime_not_in_db(self, svc, tmp_path):
        db = AnimeDownloadDatabase()
        _write_db(svc.db_path, db)

        result = svc.get_episode_metadata("Naruto", 1)
        assert result is None

    def test_returns_none_when_episode_not_in_db(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        anime_dir.mkdir()
        ep_file = _add_episode_file(anime_dir, 1)

        db = AnimeDownloadDatabase()
        db.anime["Naruto"] = AnimeDownloadHistory(
            anime_title="Naruto",
            episodes={1: _make_episode_record(1, ep_file)},
        )
        _write_db(svc.db_path, db)

        result = svc.get_episode_metadata("Naruto", 99)
        assert result is None

    def test_returns_metadata_dict(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        anime_dir.mkdir()
        ep_file = _add_episode_file(anime_dir, 1)

        db = AnimeDownloadDatabase()
        db.anime["Naruto"] = AnimeDownloadHistory(
            anime_title="Naruto",
            episodes={1: _make_episode_record(1, ep_file, file_size_mb=250.5, source="animefire")},
        )
        _write_db(svc.db_path, db)

        result = svc.get_episode_metadata("Naruto", 1)

        assert result is not None
        assert result["episode_number"] == 1
        assert result["file_size_mb"] == 250.5
        assert result["source"] == "animefire"
        assert result["status"] == "success"
        assert "downloaded_at" in result
        assert "file_path" in result


# ---------------------------------------------------------------------------
# get_anime_info
# ---------------------------------------------------------------------------


class TestGetAnimeInfo:
    def test_returns_zeros_when_anime_not_found(self, svc):
        result = svc.get_anime_info("NonExistent")
        assert result == {
            "title": "NonExistent",
            "total_episodes": 0,
            "total_size_mb": 0.0,
            "episode_numbers": [],
        }

    def test_returns_correct_episode_count(self, svc):
        anime_dir = svc.download_dir / "Bleach"
        for ep in [1, 2, 3]:
            _add_episode_file(anime_dir, ep)

        result = svc.get_anime_info("Bleach")
        assert result["total_episodes"] == 3
        assert result["episode_numbers"] == [1, 2, 3]
        assert result["title"] == "Bleach"

    def test_total_size_mb_is_nonzero_for_real_files(self, svc):
        anime_dir = svc.download_dir / "Bleach"
        _add_episode_file(anime_dir, 1)

        result = svc.get_anime_info("Bleach")
        assert result["total_size_mb"] > 0


# ---------------------------------------------------------------------------
# delete_episode
# ---------------------------------------------------------------------------


class TestDeleteEpisode:
    def test_returns_false_when_anime_dir_missing(self, svc):
        result = svc.delete_episode("NoSuchAnime", 1)
        assert result is False

    def test_deletes_episode_file(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        ep_file = _add_episode_file(anime_dir, 1)

        assert ep_file.exists()
        result = svc.delete_episode("Naruto", 1)

        assert result is True
        assert not ep_file.exists()

    def test_removes_empty_directory_after_last_episode(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        _add_episode_file(anime_dir, 1)

        svc.delete_episode("Naruto", 1)

        assert not anime_dir.exists()

    def test_keeps_directory_when_other_episodes_remain(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        _add_episode_file(anime_dir, 1)
        _add_episode_file(anime_dir, 2)

        svc.delete_episode("Naruto", 1)

        assert anime_dir.exists()
        remaining = list(anime_dir.iterdir())
        assert len(remaining) == 1
        assert remaining[0].stem == "2"

    def test_returns_false_when_episode_file_not_found(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        _add_episode_file(anime_dir, 2)

        result = svc.delete_episode("Naruto", 99)
        assert result is False

    def test_updates_database_after_deletion(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        ep_file = _add_episode_file(anime_dir, 1)

        db = AnimeDownloadDatabase()
        db.anime["Naruto"] = AnimeDownloadHistory(
            anime_title="Naruto",
            episodes={1: _make_episode_record(1, ep_file, file_size_mb=100.0)},
            total_size_mb=100.0,
        )
        _write_db(svc.db_path, db)

        svc.delete_episode("Naruto", 1)

        loaded = svc._load_database()
        history = loaded.anime.get("Naruto")
        # Episode should be removed from db
        assert history is None or 1 not in history.episodes

    def test_invalid_title_raises_value_error(self, svc):
        with pytest.raises(ValueError):
            svc.delete_episode("../secret", 1)


# ---------------------------------------------------------------------------
# delete_anime
# ---------------------------------------------------------------------------


class TestDeleteAnime:
    def test_returns_false_when_anime_dir_missing(self, svc):
        result = svc.delete_anime("NoSuchAnime")
        assert result is False

    def test_deletes_all_episode_files(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        files = [_add_episode_file(anime_dir, ep) for ep in [1, 2, 3]]

        svc.delete_anime("Naruto")

        for f in files:
            assert not f.exists()
        assert not anime_dir.exists()

    def test_returns_true_on_success(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        _add_episode_file(anime_dir, 1)

        result = svc.delete_anime("Naruto")
        assert result is True

    def test_removes_from_database(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        ep_file = _add_episode_file(anime_dir, 1)

        db = AnimeDownloadDatabase()
        db.anime["Naruto"] = AnimeDownloadHistory(
            anime_title="Naruto",
            episodes={1: _make_episode_record(1, ep_file)},
        )
        _write_db(svc.db_path, db)

        svc.delete_anime("Naruto")

        loaded = svc._load_database()
        assert "Naruto" not in loaded.anime

    def test_invalid_title_raises_value_error(self, svc):
        with pytest.raises(ValueError):
            svc.delete_anime("../../etc/passwd")


# ---------------------------------------------------------------------------
# clear_corrupted_episodes
# ---------------------------------------------------------------------------


class TestClearCorruptedEpisodes:
    def test_returns_empty_when_anime_not_in_db(self, svc):
        result = svc.clear_corrupted_episodes("Naruto")
        assert result == []

    def test_returns_empty_when_no_corrupted_episodes(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        anime_dir.mkdir()
        ep_file = _add_episode_file(anime_dir, 1)

        db = AnimeDownloadDatabase()
        db.anime["Naruto"] = AnimeDownloadHistory(
            anime_title="Naruto",
            episodes={1: _make_episode_record(1, ep_file, status="success")},
        )
        _write_db(svc.db_path, db)

        result = svc.clear_corrupted_episodes("Naruto")
        assert result == []

    def test_clears_corrupted_episodes_from_db(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        anime_dir.mkdir()
        ep1_file = anime_dir / "1.mkv"
        ep2_file = anime_dir / "2.mkv"
        ep1_file.write_bytes(b"data")
        ep2_file.write_bytes(b"data")

        db = AnimeDownloadDatabase()
        db.anime["Naruto"] = AnimeDownloadHistory(
            anime_title="Naruto",
            episodes={
                1: _make_episode_record(1, ep1_file, status="success"),
                2: _make_episode_record(2, ep2_file, status="corrupted"),
            },
        )
        _write_db(svc.db_path, db)

        result = svc.clear_corrupted_episodes("Naruto")
        assert result == [2]

        loaded = svc._load_database()
        assert 2 not in loaded.anime["Naruto"].episodes
        assert 1 in loaded.anime["Naruto"].episodes

    def test_clears_multiple_corrupted_episodes(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        anime_dir.mkdir()

        episodes = {}
        for ep in [1, 2, 3]:
            ep_file = anime_dir / f"{ep}.mkv"
            ep_file.write_bytes(b"data")
            episodes[ep] = _make_episode_record(ep, ep_file, status="corrupted")

        db = AnimeDownloadDatabase()
        db.anime["Naruto"] = AnimeDownloadHistory(anime_title="Naruto", episodes=episodes)
        _write_db(svc.db_path, db)

        result = svc.clear_corrupted_episodes("Naruto")
        assert sorted(result) == [1, 2, 3]

        loaded = svc._load_database()
        assert loaded.anime["Naruto"].episodes == {}

    def test_recalculates_total_size_after_clearing(self, svc):
        anime_dir = svc.download_dir / "Naruto"
        anime_dir.mkdir()
        ep1_file = anime_dir / "1.mkv"
        ep2_file = anime_dir / "2.mkv"
        ep1_file.write_bytes(b"data")
        ep2_file.write_bytes(b"data")

        db = AnimeDownloadDatabase()
        db.anime["Naruto"] = AnimeDownloadHistory(
            anime_title="Naruto",
            total_size_mb=300.0,
            episodes={
                1: _make_episode_record(1, ep1_file, file_size_mb=200.0, status="success"),
                2: _make_episode_record(2, ep2_file, file_size_mb=100.0, status="corrupted"),
            },
        )
        _write_db(svc.db_path, db)

        svc.clear_corrupted_episodes("Naruto")

        loaded = svc._load_database()
        assert loaded.anime["Naruto"].total_size_mb == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# _load_database / _save_database
# ---------------------------------------------------------------------------


class TestDatabasePersistence:
    def test_load_returns_empty_db_when_file_missing(self, svc):
        result = svc._load_database()
        assert isinstance(result, AnimeDownloadDatabase)
        assert result.anime == {}

    def test_save_then_load_roundtrip(self, svc):
        db = AnimeDownloadDatabase()
        anime_dir = svc.download_dir / "Naruto"
        anime_dir.mkdir()
        ep_file = _add_episode_file(anime_dir, 1)

        db.anime["Naruto"] = AnimeDownloadHistory(
            anime_title="Naruto",
            episodes={1: _make_episode_record(1, ep_file, file_size_mb=500.0)},
            total_size_mb=500.0,
        )

        svc._save_database(db)
        loaded = svc._load_database()

        assert "Naruto" in loaded.anime
        assert 1 in loaded.anime["Naruto"].episodes
        assert loaded.anime["Naruto"].episodes[1].file_size_mb == 500.0

    def test_load_returns_empty_db_on_corrupted_json(self, svc):
        svc.db_path.parent.mkdir(parents=True, exist_ok=True)
        svc.db_path.write_text("not valid json {{{")

        result = svc._load_database()
        assert isinstance(result, AnimeDownloadDatabase)
        assert result.anime == {}

    def test_save_creates_parent_directories(self, svc, tmp_path):
        deep_db_path = tmp_path / "a" / "b" / "c" / "db.json"
        svc.db_path = deep_db_path

        db = AnimeDownloadDatabase()
        svc._save_database(db)

        assert deep_db_path.exists()
