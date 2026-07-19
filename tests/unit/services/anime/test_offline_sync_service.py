"""Tests for services/anime/offline_sync_service.py.

Strategy: NO mocking of internal logic. Use monkeypatch to redirect the module-level
_get_queue_path() to a path under a temp directory so disk I/O is real but isolated.
sync_progress_to_anilist is monkeypatched because it talks to the live AniList API.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redirect_queue_to(tmp: Path, monkeypatch):
    """Point _get_queue_path() at tmp / offline_sync_queue.json."""
    queue_file = tmp / "offline_sync_queue.json"
    monkeypatch.setattr(
        "services.anime.offline_sync_service._get_queue_path",
        lambda: queue_file,
    )
    return queue_file


# ---------------------------------------------------------------------------
# _classify_error
# ---------------------------------------------------------------------------


class TestClassifyError:
    def test_none_is_retryable(self):
        from services.anime.offline_sync_service import _classify_error

        assert _classify_error(None) is True

    @pytest.mark.parametrize(
        "msg", ["401 unauthorized", "403 forbidden", "unauthorized", "forbidden"]
    )
    def test_auth_errors_not_retryable(self, msg):
        from services.anime.offline_sync_service import _classify_error

        assert _classify_error(Exception(msg)) is False

    @pytest.mark.parametrize("msg", ["token expired", "invalid token"])
    def test_token_errors_not_retryable(self, msg):
        from services.anime.offline_sync_service import _classify_error

        assert _classify_error(Exception(msg)) is False

    def test_invalid_anilist_not_retryable(self):
        from services.anime.offline_sync_service import _classify_error

        assert _classify_error(Exception("invalid anilist id")) is False

    def test_not_found_not_retryable(self):
        from services.anime.offline_sync_service import _classify_error

        assert _classify_error(Exception("resource not found")) is False

    @pytest.mark.parametrize(
        "msg",
        [
            "connection refused",
            "timeout occurred",
            "network error",
            "errno 111",
            "socket closed",
            "reset by peer",
            "500 server error",
            "502 bad gateway",
            "503 service unavailable",
            "504 gateway timeout",
            "429 rate limit",
        ],
    )
    def test_network_errors_are_retryable(self, msg):
        from services.anime.offline_sync_service import _classify_error

        assert _classify_error(Exception(msg)) is True

    def test_unknown_error_defaults_to_retryable(self):
        from services.anime.offline_sync_service import _classify_error

        assert _classify_error(Exception("something weird happened")) is True


# ---------------------------------------------------------------------------
# _load_queue / _save_queue (round-trip)
# ---------------------------------------------------------------------------


class TestQueuePersistence:
    def test_load_returns_empty_when_file_missing(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import _load_queue

        q = _load_queue()
        assert q.entries == []

    def test_save_then_load_round_trip(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import _load_queue, _save_queue
        from models.models import OfflineSyncQueue, OfflineSyncQueueEntry

        queue = OfflineSyncQueue()
        queue.entries.append(
            OfflineSyncQueueEntry(anime_title="Naruto", episode_number=1, anilist_id=20)
        )
        _save_queue(queue)
        loaded = _load_queue()
        assert len(loaded.entries) == 1
        assert loaded.entries[0].anime_title == "Naruto"
        assert loaded.entries[0].anilist_id == 20

    def test_load_returns_empty_on_corrupt_file(self, tmp_path, monkeypatch):
        queue_file = _redirect_queue_to(tmp_path, monkeypatch)
        queue_file.write_text("not json at all{{{")
        from services.anime.offline_sync_service import _load_queue

        q = _load_queue()
        assert q.entries == []


# ---------------------------------------------------------------------------
# add_to_queue
# ---------------------------------------------------------------------------


class TestAddToQueue:
    def test_add_retryable_error_enqueues_entry(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import add_to_queue, _load_queue

        add_to_queue(
            anime_title="One Piece",
            episode_number=5,
            anilist_id=21,
            error=Exception("connection refused"),
        )
        q = _load_queue()
        assert len(q.entries) == 1
        assert q.entries[0].anime_title == "One Piece"
        assert q.entries[0].episode_number == 5

    def test_non_retryable_error_not_queued(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import add_to_queue, _load_queue

        add_to_queue(
            anime_title="Bleach",
            episode_number=1,
            anilist_id=22,
            error=Exception("401 unauthorized"),
        )
        q = _load_queue()
        assert q.entries == []

    def test_add_offline_with_none_error(self, tmp_path, monkeypatch):
        """None error = went offline; still queues because _classify_error(None) is True."""
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import add_to_queue, _load_queue

        add_to_queue(
            anime_title="Bleach",
            episode_number=3,
            anilist_id=22,
            error=None,
        )
        q = _load_queue()
        assert len(q.entries) == 1

    def test_duplicate_entry_is_updated_not_appended(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import add_to_queue, _load_queue

        add_to_queue("AttackOnTitan", 7, 30, error=Exception("timeout"))
        add_to_queue("AttackOnTitan", 7, 30, error=Exception("timeout again"))
        q = _load_queue()
        assert len(q.entries) == 1
        assert "again" in (q.entries[0].last_error or "")

    def test_multiple_different_entries_accumulated(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import add_to_queue, _load_queue

        add_to_queue("Anime A", 1, 100, error=Exception("timeout"))
        add_to_queue("Anime B", 2, 200, error=Exception("connection"))
        q = _load_queue()
        assert len(q.entries) == 2

    def test_stores_file_path_when_local(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import add_to_queue, _load_queue

        ep_file = tmp_path / "ep01.mkv"
        add_to_queue("Local Show", 1, 50, error=None, is_local=True, file_path=ep_file)
        q = _load_queue()
        assert q.entries[0].is_local is True
        assert q.entries[0].file_path == str(ep_file)


# ---------------------------------------------------------------------------
# retry_offline_syncs — empty queue
# ---------------------------------------------------------------------------


class TestRetryOfflineSyncs:
    def test_empty_queue_returns_zeros(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import retry_offline_syncs

        result = retry_offline_syncs()
        assert result == {"successful": 0, "failed": 0}

    def test_successful_sync_removes_entry_and_deletes_file(self, tmp_path, monkeypatch):
        queue_file = _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import add_to_queue, retry_offline_syncs

        add_to_queue("Naruto", 1, 20, error=Exception("timeout"))
        assert queue_file.exists()

        with patch(
            "services.anime.offline_sync_service.sync_progress_to_anilist", return_value=True
        ):
            result = retry_offline_syncs()

        assert result["successful"] == 1
        assert result["failed"] == 0
        # File should be deleted when queue is empty after success
        assert not queue_file.exists()

    def test_failed_sync_increments_retry_count(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import (
            add_to_queue,
            retry_offline_syncs,
            _load_queue,
        )

        add_to_queue("Boruto", 2, 101, error=Exception("timeout"))

        with patch(
            "services.anime.offline_sync_service.sync_progress_to_anilist", return_value=False
        ):
            result = retry_offline_syncs()

        assert result["failed"] == 1
        assert result["successful"] == 0
        q = _load_queue()
        assert len(q.entries) == 1
        assert q.entries[0].retry_count == 1

    def test_entry_exceeding_max_retries_is_dropped(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import retry_offline_syncs, _load_queue
        from models.models import OfflineSyncQueueEntry, OfflineSyncQueue
        from services.anime.offline_sync_service import _save_queue

        # Pre-populate queue with retry_count at limit
        entry = OfflineSyncQueueEntry(
            anime_title="OldAnime",
            episode_number=99,
            anilist_id=999,
            retry_count=3,  # default max is 3
        )
        q = OfflineSyncQueue(entries=[entry])
        _save_queue(q)

        with patch(
            "services.anime.offline_sync_service.sync_progress_to_anilist", return_value=False
        ):
            result = retry_offline_syncs()

        # Entry is dropped because retry_count >= max_retry_count
        assert result["failed"] == 1
        loaded = _load_queue()
        assert loaded.entries == []

    def test_exception_during_sync_increments_retry_count(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import (
            add_to_queue,
            retry_offline_syncs,
            _load_queue,
        )

        add_to_queue("HunterHunter", 50, 11061, error=Exception("timeout"))

        with patch(
            "services.anime.offline_sync_service.sync_progress_to_anilist",
            side_effect=RuntimeError("unexpected"),
        ):
            result = retry_offline_syncs()

        assert result["failed"] == 1
        q = _load_queue()
        assert q.entries[0].retry_count == 1
        assert "unexpected" in (q.entries[0].last_error or "")

    def test_mixed_success_and_failure(self, tmp_path, monkeypatch):
        _redirect_queue_to(tmp_path, monkeypatch)
        from services.anime.offline_sync_service import (
            add_to_queue,
            retry_offline_syncs,
            _load_queue,
        )

        add_to_queue("AnimeSuccess", 1, 1, error=Exception("timeout"))
        add_to_queue("AnimeFail", 2, 2, error=Exception("timeout"))

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count == 1  # first call succeeds, second fails

        with patch(
            "services.anime.offline_sync_service.sync_progress_to_anilist", side_effect=side_effect
        ):
            result = retry_offline_syncs()

        assert result["successful"] == 1
        assert result["failed"] == 1
        q = _load_queue()
        assert len(q.entries) == 1  # Only failed entry remains
