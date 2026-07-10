"""Tests for legacy single-underscore debug/runtime env flags on AppSettings.

These flags were previously read ad-hoc via os.getenv/os.environ across the
codebase. They are now centralized in models.config and must remain settable
via their exact historical env var names with the same "== '1'" truthiness.
"""

from models.config import AppSettings


def _fresh_settings() -> AppSettings:
    """Instantiate a fresh settings object so monkeypatched env is picked up."""
    return AppSettings()


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


def test_debug_mpv_disabled_for_non_one(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_DEBUG_MPV", "true")
    assert _fresh_settings().debug_mpv is False


def test_disable_ipc_enabled_when_one(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_DISABLE_IPC", "1")
    assert _fresh_settings().disable_ipc is True


def test_disable_ipc_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("ANI_TUPI_DISABLE_IPC", raising=False)
    assert _fresh_settings().disable_ipc is False


def test_disable_ipc_disabled_for_non_one(monkeypatch):
    monkeypatch.setenv("ANI_TUPI_DISABLE_IPC", "yes")
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
