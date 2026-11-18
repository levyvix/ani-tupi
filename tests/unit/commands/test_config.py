"""Unit tests for interactive config command."""

from __future__ import annotations

import importlib


class _FakeService:
    def __init__(self):
        self.saved = None

    def categories(self):
        return [("cache", "Cache e desempenho")]

    def fields_in_category(self, category_key: str):
        return [("cache", "episodes_cache_enabled")]

    def category_description(self, category_key: str):
        return "Validade dos dados guardados e limites de desempenho."

    def fields_for_category(self, category_key: str):
        return ["episodes_cache_enabled"]

    def get_effective_value(self, category_key: str, field_key: str):
        return False

    def field_description(self, category_key: str, field_key: str):
        return "Guardar listas de episódios em cache"

    def env_var_name(self, category_key: str, field_key: str):
        return "ANI_TUPI__CACHE__EPISODES_CACHE_ENABLED"

    def is_env_override_active(self, category_key: str, field_key: str):
        return False

    def parse_input_value(self, category_key: str, field_key: str, raw: str, current_value=None):
        if raw == "invalid":
            raise ValueError("Expected boolean value")
        return raw.lower() == "true"

    def validate_staged(self, staged):
        return None

    def save_staged(self, staged):
        self.saved = staged


def test_config_save_flow(monkeypatch):
    """Config command should stage and save edits."""
    config_module = importlib.import_module("commands.config")
    fake = _FakeService()

    choices = iter(
        [
            "Cache e desempenho",  # top menu
            "Guardar listas de episódios em cache · atual: False",  # category field
            None,  # back from category
            config_module.SAVE_OPTION,  # save
            config_module.CONFIRM_SAVE,  # confirm save
        ]
    )

    monkeypatch.setattr(config_module, "SettingsManagementService", lambda: fake)
    monkeypatch.setattr(config_module, "menu_navigate", lambda *args, **kwargs: next(choices))
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: "true")

    result = config_module.config(None)

    assert result == 0
    assert fake.saved == {"cache": {"episodes_cache_enabled": True}}


def test_config_discard_flow(monkeypatch):
    """Discard option should exit without saving."""
    config_module = importlib.import_module("commands.config")
    fake = _FakeService()

    monkeypatch.setattr(config_module, "SettingsManagementService", lambda: fake)
    monkeypatch.setattr(
        config_module, "menu_navigate", lambda *args, **kwargs: config_module.DISCARD_OPTION
    )

    result = config_module.config(None)

    assert result == 0
    assert fake.saved is None


def test_config_invalid_input_shows_error_and_keeps_running(monkeypatch):
    """Invalid input should not crash and should not save."""
    config_module = importlib.import_module("commands.config")
    fake = _FakeService()

    choices = iter(
        [
            "Cache e desempenho",
            "Guardar listas de episódios em cache · atual: False",
            None,
            config_module.DISCARD_OPTION,
        ]
    )

    monkeypatch.setattr(config_module, "SettingsManagementService", lambda: fake)
    monkeypatch.setattr(config_module, "menu_navigate", lambda *args, **kwargs: next(choices))
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: "invalid")

    result = config_module.config(None)

    assert result == 0
    assert fake.saved is None
