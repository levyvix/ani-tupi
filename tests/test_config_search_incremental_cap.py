"""Tests for the user-tunable incremental-search result cap setting."""

from models.config import AppSettings


def _fresh_settings() -> AppSettings:
    """Instantiate settings with the configured defaults."""
    return AppSettings()


def test_incremental_max_results_default_is_20():
    assert _fresh_settings().search.incremental_max_results == 20
