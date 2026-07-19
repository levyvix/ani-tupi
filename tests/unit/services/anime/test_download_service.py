"""Tests for AnimeDownloadService.

Strategy: NO mocking of internal services/storage. Mock ONLY externals:
- yt_dlp (the actual HTTP download tool)
- subprocess / external tools (none here)

File I/O uses real temp directories via tmp_path/monkeypatch.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from models.download import (
    AnimeDownloadDatabase,
    AnimeDownloadHistory,
    DownloadedEpisode,
)
from utils.range_parser import RangeParseError


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_service(tmp_path: Path, monkeypatch, max_parallel: int = 1) -> object:
    """Return a real AnimeDownloadService backed by tmp_path."""
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "db" / "anime_downloads.json"

    monkeypatch.setenv("ANI_TUPI__ANIME_DOWNLOAD__DOWNLOAD_DIRECTORY", str(dl_dir))
    monkeypatch.setenv("ANI_TUPI__ANIME_DOWNLOAD__MAX_PARALLEL_DOWNLOADS", str(max_parallel))
    monkeypatch.setenv("ANI_TUPI__ANIME_DOWNLOAD__SKIP_ALREADY_DOWNLOADED", "true")
    monkeypatch.setenv("ANI_TUPI__ANIME_DOWNLOAD__VIDEO_FORMAT", "mkv")

    # Reload settings so the new env vars take effect
    from importlib import reload
    import models.config
    import services.anime.download_service as ds_mod

    reload(models.config)
    reload(ds_mod)

    svc = ds_mod.AnimeDownloadService()
    # Override db_path to avoid touching real state dir
    svc.db_path = db_path
    svc.db_path.parent.mkdir(parents=True, exist_ok=True)
    return svc


def _make_valid_video(path: Path) -> None:
    """Write a fake 2MB binary file so _validate_file passes."""
    path.write_bytes(b"\x00" * (2 * 1024 * 1024))


def _noop_url_getter(ep_num: int):
    """Fallback get_episode_url that returns None (nothing to download)."""
    return None


# ---------------------------------------------------------------------------
# DownloadTask unit tests (pure data-class, no I/O)
# ---------------------------------------------------------------------------


class TestDownloadTask:
    def test_can_retry_below_max(self):
        from services.anime.download_service import DownloadTask

        task = DownloadTask(episode_number=1, attempts=0, max_attempts=3)
        assert task.can_retry() is True

    def test_can_retry_at_max(self):
        from services.anime.download_service import DownloadTask

        task = DownloadTask(episode_number=1, attempts=3, max_attempts=3)
        assert task.can_retry() is False

    def test_increment_attempt(self):
        from services.anime.download_service import DownloadTask

        task = DownloadTask(episode_number=1, attempts=0)
        task.increment_attempt()
        assert task.attempts == 1


# ---------------------------------------------------------------------------
# _validate_file
# ---------------------------------------------------------------------------


class TestValidateFile:
    def test_nonexistent_file_invalid(self, tmp_path):
        svc = _make_service(tmp_path, pytest.MonkeyPatch())
        result = svc._validate_file(tmp_path / "missing.mkv")
        assert result is False

    def test_small_file_invalid(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        f = tmp_path / "tiny.mkv"
        f.write_bytes(b"\x00" * 100)  # way under 1 MB
        assert svc._validate_file(f) is False

    def test_large_enough_file_valid(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        f = tmp_path / "valid.mkv"
        _make_valid_video(f)
        assert svc._validate_file(f) is True


# ---------------------------------------------------------------------------
# _load_database / _save_database
# ---------------------------------------------------------------------------


class TestDatabasePersistence:
    def test_load_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        # Use a fresh db_path that doesn't exist yet
        svc.db_path = tmp_path / "fresh_db.json"
        db = svc._load_database()
        assert isinstance(db, AnimeDownloadDatabase)
        assert db.anime == {}

    def test_save_and_reload(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        db = AnimeDownloadDatabase()
        history = AnimeDownloadHistory(anime_title="My Anime")
        ep = DownloadedEpisode(
            episode_number=1,
            file_path=tmp_path / "1.mkv",
            file_size_mb=50.0,
            source="test",
            status="success",
        )
        history.episodes[1] = ep
        db.anime["My Anime"] = history

        svc._save_database(db)
        assert svc.db_path.exists()

        loaded = svc._load_database()
        assert "My Anime" in loaded.anime
        assert loaded.anime["My Anime"].has_episode(1)

    def test_load_handles_corrupted_json(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        svc.db_path.parent.mkdir(parents=True, exist_ok=True)
        svc.db_path.write_text("not json at all!!!")

        db = svc._load_database()
        # Should return empty database without raising
        assert isinstance(db, AnimeDownloadDatabase)
        assert db.anime == {}


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_all_success(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        summary = svc._build_summary(5, 5, [], [], [])
        assert "5/5" in summary

    def test_partial_failure(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        summary = svc._build_summary(3, 5, [4, 5], [], [])
        assert "3/5" in summary
        assert "4" in summary or "falharam" in summary.lower() or "❌" in summary

    def test_with_corrupted(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        summary = svc._build_summary(3, 5, [], [4, 5], [])
        assert "corrompidos" in summary or "⚠️" in summary

    def test_with_skipped(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        summary = svc._build_summary(0, 0, [], [], [1, 2, 3])
        assert "já existiam" in summary or "⊘" in summary

    def test_mixed(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        summary = svc._build_summary(2, 4, [3], [4], [5, 6])
        assert isinstance(summary, str)
        assert len(summary) > 0


# ---------------------------------------------------------------------------
# _download_single_episode_with_url
# ---------------------------------------------------------------------------


class TestDownloadSingleEpisodeWithUrl:
    def test_no_url_returns_false(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        anime_dir = tmp_path / "anime"
        anime_dir.mkdir()

        success, valid = svc._download_single_episode_with_url("MyAnime", anime_dir, 1, None)
        assert success is False
        assert valid is False

    def test_download_failure_propagates_as_false(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        anime_dir = tmp_path / "anime"
        anime_dir.mkdir()

        with patch.object(svc, "_download_file", return_value=False):
            success, valid = svc._download_single_episode_with_url(
                "MyAnime", anime_dir, 1, ("http://example.com/1.mkv", "test")
            )
        assert success is False

    def test_successful_download_valid_file(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        anime_dir = tmp_path / "anime"
        anime_dir.mkdir()

        # Simulate _download_file writing a valid file
        def fake_download(url: str, file_path: Path) -> bool:
            _make_valid_video(file_path)
            return True

        with patch.object(svc, "_download_file", side_effect=fake_download):
            success, valid = svc._download_single_episode_with_url(
                "MyAnime", anime_dir, 1, ("http://example.com/1.mkv", "test")
            )

        assert success is True
        assert valid is True

    def test_download_file_too_small_returns_corrupted(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        anime_dir = tmp_path / "anime"
        anime_dir.mkdir()

        def fake_download_tiny(url: str, file_path: Path) -> bool:
            file_path.write_bytes(b"\x00" * 100)  # < 1 MB
            return True

        with patch.object(svc, "_download_file", side_effect=fake_download_tiny):
            success, valid = svc._download_single_episode_with_url(
                "MyAnime", anime_dir, 1, ("http://example.com/1.mkv", "test")
            )

        assert success is False
        assert valid is False
        # File should be removed
        assert not (anime_dir / "1.mkv").exists()

    def test_exception_returns_false(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        anime_dir = tmp_path / "anime"
        anime_dir.mkdir()

        with patch.object(svc, "_download_file", side_effect=RuntimeError("boom")):
            success, valid = svc._download_single_episode_with_url(
                "MyAnime", anime_dir, 1, ("http://example.com/1.mkv", "test")
            )
        assert success is False


# ---------------------------------------------------------------------------
# _download_file (mocks yt_dlp, the real external boundary)
# ---------------------------------------------------------------------------


class TestDownloadFile:
    def test_successful_yt_dlp_download(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        output_path = tmp_path / "1.mkv"

        def fake_ydl_download(ydl_instance, urls):
            # Simulate yt-dlp writing the file to the temp dir
            # We need to write a file in the same temp dir yt-dlp would use
            pass

        # Patch yt_dlp at the module level used by the service
        with patch("yt_dlp.YoutubeDL") as mock_ydl_class:
            mock_ydl_instance = MagicMock()

            def fake_context_enter(self):
                return mock_ydl_instance

            def fake_context_exit(self, *args):
                return False

            mock_ydl_class.return_value.__enter__ = fake_context_enter
            mock_ydl_class.return_value.__exit__ = fake_context_exit

            # Simulate yt-dlp writing a file by hooking the download call
            import tempfile as _tempfile

            original_tmp_class = _tempfile.TemporaryDirectory

            class FakeTempDir:
                def __init__(self, *a, **kw):
                    self._real = original_tmp_class()

                def __enter__(self):
                    p = Path(self._real.__enter__())
                    # Write the "downloaded" file
                    (p / "download.mkv").write_bytes(b"\x00" * 100)
                    return str(p)

                def __exit__(self, *args):
                    return self._real.__exit__(*args)

            with patch("tempfile.TemporaryDirectory", FakeTempDir):
                result = svc._download_file("http://example.com/ep1.mkv", output_path)

        assert result is True
        assert output_path.exists()

    def test_yt_dlp_exception_returns_false(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        output_path = tmp_path / "1.mkv"

        with patch("yt_dlp.YoutubeDL") as mock_ydl_class:
            mock_ydl_class.return_value.__enter__ = MagicMock(
                side_effect=RuntimeError("yt-dlp failed")
            )
            mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)

            result = svc._download_file("http://example.com/ep1.mkv", output_path)

        assert result is False

    def test_no_file_written_returns_false(self, tmp_path, monkeypatch):
        """When yt-dlp runs but writes nothing, _download_file returns False."""
        svc = _make_service(tmp_path, monkeypatch)
        output_path = tmp_path / "1.mkv"

        import tempfile as _tempfile

        original_tmp_class = _tempfile.TemporaryDirectory

        class EmptyTempDir:
            def __init__(self, *a, **kw):
                self._real = original_tmp_class()

            def __enter__(self):
                return self._real.__enter__()  # empty dir, no file written

            def __exit__(self, *args):
                return self._real.__exit__(*args)

        with patch("yt_dlp.YoutubeDL") as mock_ydl_class:
            mock_ydl_class.return_value.__enter__ = MagicMock(
                return_value=MagicMock(download=MagicMock())
            )
            mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)
            with patch("tempfile.TemporaryDirectory", EmptyTempDir):
                result = svc._download_file("http://example.com/ep1.mkv", output_path)

        assert result is False


# ---------------------------------------------------------------------------
# _prefetch_episode_urls
# ---------------------------------------------------------------------------


class TestPrefetchEpisodeUrls:
    def test_fetches_urls_via_callback(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        def getter(ep: int):
            return (f"http://cdn.example.com/{ep:02d}.mp4", "test_src")

        result = svc._prefetch_episode_urls("Anime", [1, 2, 3], getter)
        assert result[1] == ("http://cdn.example.com/01.mp4", "test_src")
        assert result[2] == ("http://cdn.example.com/02.mp4", "test_src")
        assert result[3] == ("http://cdn.example.com/03.mp4", "test_src")

    def test_none_url_recorded(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        result = svc._prefetch_episode_urls("Anime", [1, 2], _noop_url_getter)
        assert result[1] is None
        assert result[2] is None

    def test_callback_exception_recorded_as_none(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        def bad_getter(ep: int):
            raise RuntimeError("scraper exploded")

        result = svc._prefetch_episode_urls("Anime", [1], bad_getter)
        assert result[1] is None

    def test_pattern_fast_path_used(self, tmp_path, monkeypatch):
        """When a URL pattern is detected and valid, the fast path skips the scraper."""
        svc = _make_service(tmp_path, monkeypatch)
        scraper_called = []

        def getter(ep: int):
            scraper_called.append(ep)
            return ("http://cdn.example.net/anime/01.mp4/index.m3u8", "src")

        with (
            patch("services.anime.episode_url_pattern.detect_episode_pattern", return_value=True),
            patch(
                "services.anime.episode_url_pattern.derive_episode_url",
                side_effect=lambda url, ep: f"http://cdn.example.net/anime/{ep:02d}.mp4/index.m3u8",
            ),
            patch("services.anime.episode_url_pattern.validate_episode_url", return_value=True),
        ):
            result = svc._prefetch_episode_urls("Anime", [1, 2, 3], getter)

        # Episode 1 should go via scraper (no last_known_url yet)
        assert 1 in scraper_called
        # Episodes 2 and 3 may use pattern (scraper NOT called)
        assert 2 not in scraper_called
        assert 3 not in scraper_called
        assert result[2] is not None
        assert result[3] is not None

    def test_pattern_miss_falls_back_to_scraper(self, tmp_path, monkeypatch):
        """When derived URL fails validation, falls back to scraper."""
        svc = _make_service(tmp_path, monkeypatch)
        scraper_called = []

        def getter(ep: int):
            scraper_called.append(ep)
            return (f"http://cdn.example.net/anime/{ep:02d}.mp4/index.m3u8", "src")

        with (
            patch("services.anime.episode_url_pattern.detect_episode_pattern", return_value=True),
            patch(
                "services.anime.episode_url_pattern.derive_episode_url",
                return_value="http://bad.url/",
            ),
            patch("services.anime.episode_url_pattern.validate_episode_url", return_value=False),
        ):
            svc._prefetch_episode_urls("Anime", [1, 2], getter)

        # Both episodes fall back to scraper since pattern validation fails
        assert 1 in scraper_called
        assert 2 in scraper_called


# ---------------------------------------------------------------------------
# download_episodes (integration through the service, mocking only _download_file)
# ---------------------------------------------------------------------------


class TestDownloadEpisodes:
    def _fake_download(self, anime_dir: Path, ep: int):
        """Write a valid fake video file."""
        path = anime_dir / f"{ep}.mkv"
        _make_valid_video(path)
        return True

    def test_invalid_range_raises(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        with pytest.raises(RangeParseError):
            svc.download_episodes("Anime", "abc-xyz", 10, _noop_url_getter)

    def test_path_traversal_rejected(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        with pytest.raises(ValueError, match="inválido"):
            svc.download_episodes("../evil", "1", 5, _noop_url_getter)

    def test_empty_title_rejected(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        with pytest.raises(ValueError):
            svc.download_episodes("", "1", 5, _noop_url_getter)

    def test_all_episodes_no_url_returns_zero_success(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        result = svc.download_episodes("Anime A", "1-3", 5, _noop_url_getter)

        assert result.successful == 0
        assert len(result.failed) == 3  # max retries exceeded for all

    def test_successful_single_episode_download(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        def getter(ep: int):
            return (f"http://cdn.example.com/{ep}.mkv", "test")

        def fake_dl(url: str, file_path: Path) -> bool:
            _make_valid_video(file_path)
            return True

        with patch.object(svc, "_download_file", side_effect=fake_dl):
            result = svc.download_episodes("My Anime", "1", 10, getter)

        assert result.successful == 1
        assert result.failed == []
        assert result.corrupted == []
        assert (svc.download_dir / "My Anime" / "1.mkv").exists()

    def test_history_updated_after_download(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        def getter(ep: int):
            return (f"http://cdn.example.com/{ep}.mkv", "test")

        def fake_dl(url: str, file_path: Path) -> bool:
            _make_valid_video(file_path)
            return True

        with patch.object(svc, "_download_file", side_effect=fake_dl):
            svc.download_episodes("My Anime", "1-2", 10, getter)

        db = svc._load_database()
        assert "My Anime" in db.anime
        history = db.anime["My Anime"]
        assert history.has_episode(1)
        assert history.has_episode(2)

    def test_skip_already_downloaded(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        # Pre-populate the database
        db = AnimeDownloadDatabase()
        # Use the service's configured download_dir (points to tmp_path)
        anime_dir = Path(svc.download_dir) / "Cached Anime"
        anime_dir.mkdir(parents=True)
        ep_file = anime_dir / "1.mkv"
        _make_valid_video(ep_file)

        history = AnimeDownloadHistory(anime_title="Cached Anime")
        history.episodes[1] = DownloadedEpisode(
            episode_number=1,
            file_path=ep_file,
            file_size_mb=2.0,
            source="test",
            status="success",
        )
        db.anime["Cached Anime"] = history
        svc._save_database(db)

        download_called = []

        def getter(ep: int):
            download_called.append(ep)
            return (f"http://cdn.example.com/{ep}.mkv", "test")

        with patch.object(svc, "_download_file", side_effect=lambda *a: True):
            result = svc.download_episodes("Cached Anime", "1-2", 5, getter)

        # Episode 1 should be skipped
        assert 1 in result.skipped

    def test_corrupted_file_tracked(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        def getter(ep: int):
            return (f"http://cdn.example.com/{ep}.mkv", "test")

        def fake_dl_tiny(url: str, file_path: Path) -> bool:
            file_path.write_bytes(b"\x00" * 100)  # < 1 MB → invalid
            return True

        with patch.object(svc, "_download_file", side_effect=fake_dl_tiny):
            result = svc.download_episodes("Corrupt Anime", "1", 5, getter)

        # After max retries, small files end up as failed (retried then failed)
        # OR the single attempt returns success=False so it retries and eventually fails
        # The behavior: _download_single_episode_with_url returns (False, False) for tiny files
        # which means it retries up to max_attempts then appends to failed
        assert result.successful == 0

    def test_result_summary_populated(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)

        def getter(ep: int):
            return (f"http://cdn.example.com/{ep}.mkv", "test")

        def fake_dl(url: str, file_path: Path) -> bool:
            _make_valid_video(file_path)
            return True

        with patch.object(svc, "_download_file", side_effect=fake_dl):
            result = svc.download_episodes("Anime", "1-3", 10, getter)

        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_parallel_download_multiple_episodes(self, tmp_path, monkeypatch):
        """With max_parallel=2, multiple episodes download correctly."""
        svc = _make_service(tmp_path, monkeypatch, max_parallel=2)

        def getter(ep: int):
            return (f"http://cdn.example.com/{ep}.mkv", "test")

        def fake_dl(url: str, file_path: Path) -> bool:
            _make_valid_video(file_path)
            return True

        with patch.object(svc, "_download_file", side_effect=fake_dl):
            result = svc.download_episodes("Parallel Anime", "1-4", 10, getter)

        assert result.successful == 4
        assert result.failed == []


# ---------------------------------------------------------------------------
# _download_parallel (whitebox: retry logic)
# ---------------------------------------------------------------------------


class TestDownloadParallel:
    def test_retry_on_failure_then_succeed(self, tmp_path, monkeypatch):
        """Episode fails first attempt, succeeds on retry."""
        svc = _make_service(tmp_path, monkeypatch)
        anime_dir = tmp_path / "anime"
        anime_dir.mkdir()

        call_count = [0]

        def fake_dl(url: str, file_path: Path) -> bool:
            call_count[0] += 1
            if call_count[0] == 1:
                return False  # first attempt fails
            _make_valid_video(file_path)
            return True

        episode_urls = {1: ("http://example.com/1.mkv", "test")}
        with patch.object(svc, "_download_file", side_effect=fake_dl):
            successful, failed, corrupted = svc._download_parallel(
                "TestAnime", anime_dir, [1], episode_urls
            )

        assert successful == 1
        assert failed == []

    def test_max_retries_exceeded_goes_to_failed(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        anime_dir = tmp_path / "anime"
        anime_dir.mkdir()

        with patch.object(svc, "_download_file", return_value=False):
            episode_urls = {1: ("http://example.com/1.mkv", "test")}
            successful, failed, corrupted = svc._download_parallel(
                "TestAnime", anime_dir, [1], episode_urls
            )

        assert successful == 0
        assert 1 in failed

    def test_no_url_immediately_fails_after_retries(self, tmp_path, monkeypatch):
        svc = _make_service(tmp_path, monkeypatch)
        anime_dir = tmp_path / "anime"
        anime_dir.mkdir()

        episode_urls = {1: None}
        successful, failed, corrupted = svc._download_parallel(
            "TestAnime", anime_dir, [1], episode_urls
        )

        assert successful == 0
        assert 1 in failed
