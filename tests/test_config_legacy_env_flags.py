"""Tests for legacy single-underscore debug/runtime env flags on AppSettings.

These flags were previously read ad-hoc via os.getenv/os.environ across the
codebase. They are now centralized in models.config and must remain settable
via their exact historical env var names with the same "== '1'" truthiness.
"""

from models.config import AppSettings


def _fresh_settings() -> AppSettings:
    """Instantiate a fresh settings object so monkeypatched env is picked up."""
    return AppSettings()


def test_airing_download_poll_interval_defaults_to_30(monkeypatch):
    monkeypatch.delenv("ANI_TUPI__AIRING_DOWNLOADS__POLL_INTERVAL_MINUTES", raising=False)
    assert _fresh_settings().airing_downloads.poll_interval_minutes == 30


def test_airing_download_poll_interval_accepts_environment_override(monkeypatch):
    monkeypatch.setenv("ANI_TUPI__AIRING_DOWNLOADS__POLL_INTERVAL_MINUTES", "20")
    assert _fresh_settings().airing_downloads.poll_interval_minutes == 20


def test_airing_download_poll_interval_rejects_non_divisors(monkeypatch):
    monkeypatch.setenv("ANI_TUPI__AIRING_DOWNLOADS__POLL_INTERVAL_MINUTES", "7")
    import pytest

    with pytest.raises(ValueError):
        _fresh_settings()


def test_debug_incremental_search_enabled_when_one(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_DEBUG_INCREMENTAL_SEARCH", "1")
    assert _fresh_settings().debug_incremental_search is True


def test_debug_incremental_search_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("ANI_TUPI_DEBUG_INCREMENTAL_SEARCH", raising=False)
    assert _fresh_settings().debug_incremental_search is False


def test_debug_incremental_search_disabled_for_non_one(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_DEBUG_INCREMENTAL_SEARCH", "true")
    assert _fresh_settings().debug_incremental_search is False


def test_debug_mpv_enabled_when_one(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_DEBUG_MPV", "1")
    assert _fresh_settings().debug_mpv is True


def test_debug_mpv_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("ANI_TUPI_DEBUG_MPV", raising=False)
    assert _fresh_settings().debug_mpv is False


def test_disable_ipc_enabled_when_one(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_DISABLE_IPC", "1")
    assert _fresh_settings().disable_ipc is True


def test_disable_ipc_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("ANI_TUPI_DISABLE_IPC", raising=False)
    assert _fresh_settings().disable_ipc is False


def test_mpv_log_file_returns_stripped_path(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_MPV_LOG_FILE", "  /tmp/mpv-test.log  ")
    assert _fresh_settings().mpv_log_file == "/tmp/mpv-test.log"


def test_mpv_log_file_none_when_unset(monkeypatch):
    monkeypatch.delenv("ANI_TUPI_MPV_LOG_FILE", raising=False)
    assert _fresh_settings().mpv_log_file is None


def test_mpv_log_file_none_when_blank(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_MPV_LOG_FILE", "   ")
    assert _fresh_settings().mpv_log_file is None
