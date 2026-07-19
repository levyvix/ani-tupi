"""Unit tests for settings management service."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from services.core.settings_management_service import SettingsManagementService


def test_parse_input_value_supports_common_types():
    """Parser should handle bool/int/list/path values."""
    svc = SettingsManagementService()

    assert svc.parse_input_value("cache", "episodes_cache_enabled", "true") is True
    assert svc.parse_input_value("cache", "search_cache_ttl_seconds", "7200") == 7200
    assert svc.parse_input_value("plugins", "disabled_plugins", "a, b ,c") == ["a", "b", "c"]
    assert (
        svc.parse_input_value("anilist", "token_file", "~/token.json")
        == Path("~/token.json").expanduser()
    )


def test_validate_staged_raises_for_invalid_values(monkeypatch):
    """Validation should reject staged overrides that violate constraints."""
    svc = SettingsManagementService()
    monkeypatch.setattr(
        "services.core.settings_management_service.load_user_settings_overrides", lambda: {}
    )

    with pytest.raises(ValidationError):
        svc.validate_staged({"cache": {"anilist_fuzzy_threshold": 10}})


def test_field_description_exposes_pydantic_field_docs():
    """Field descriptions should come from settings metadata."""
    svc = SettingsManagementService()

    description = svc.field_description("cache", "search_cache_ttl_seconds")

    assert "Time-to-live for search results cache" in description


def test_priority_order_partial_reorder_keeps_unspecified_tail():
    """Specified sources should move to top; unspecified keep relative order."""
    svc = SettingsManagementService()
    current = ["sushianimes", "animesdigital", "animefire", "anitube"]

    updated = svc.parse_input_value(
        "plugins",
        "priority_order",
        "animefire,anitube",
        current_value=current,
    )

    assert updated == ["animefire", "anitube", "sushianimes", "animesdigital"]


def test_priority_order_single_top1_keeps_rest_order():
    """Single top source should only be moved to front."""
    svc = SettingsManagementService()
    current = ["sushianimes", "animesdigital", "animefire", "anitube"]

    updated = svc.parse_input_value(
        "plugins",
        "priority_order",
        "anitube",
        current_value=current,
    )

    assert updated == ["anitube", "sushianimes", "animesdigital", "animefire"]


def test_priority_order_rejects_unknown_source():
    """Unknown source names should be rejected with clear error."""
    svc = SettingsManagementService()
    current = ["sushianimes", "anitube"]

    with pytest.raises(ValueError, match="Unknown source"):
        svc.parse_input_value(
            "plugins",
            "priority_order",
            "foo",
            current_value=current,
        )


def test_save_staged_merges_existing_overrides(monkeypatch):
    """Persisted overrides should be merged instead of replaced."""
    svc = SettingsManagementService()
    saved: dict = {}

    monkeypatch.setattr(
        "services.core.settings_management_service.load_user_settings_overrides",
        lambda: {"cache": {"search_cache_ttl_seconds": 3600}},
    )
    monkeypatch.setattr(
        "services.core.settings_management_service.save_user_settings_overrides",
        lambda payload: saved.update(payload),
    )

    svc.save_staged({"cache": {"episodes_cache_enabled": True}})

    assert saved["cache"]["search_cache_ttl_seconds"] == 3600
    assert saved["cache"]["episodes_cache_enabled"] is True
