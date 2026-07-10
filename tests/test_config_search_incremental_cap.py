"""Tests for the user-tunable incremental-search result cap setting."""

from models.config import AppSettings


def _fresh_settings() -> AppSettings:
    """Instantiate a fresh settings object so monkeypatched env is picked up."""
    return AppSettings()


def test_incremental_max_results_default_is_20(monkeypatch):
    monkeypatch.delenv("ANI_TUPI__SEARCH__INCREMENTAL_MAX_RESULTS", raising=False)
    assert _fresh_settings().search.incremental_max_results == 20


def test_incremental_max_results_env_override(monkeypatch):
    monkeypatch.setenv("ANI_TUPI__SEARCH__INCREMENTAL_MAX_RESULTS", "35")
    assert _fresh_settings().search.incremental_max_results == 35
