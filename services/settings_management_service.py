"""Interactive settings management service for CLI configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import ValidationError

from models.config import (
    AppSettings,
    load_user_settings_overrides,
    save_user_settings_overrides,
    settings,
)


class SettingsManagementService:
    """Manage runtime-editable settings with validation and persistence."""

    def __init__(self) -> None:
        self._category_types = {
            name: field.annotation
            for name, field in AppSettings.model_fields.items()
            if hasattr(field.annotation, "model_fields")
        }

    def categories(self) -> list[tuple[str, str]]:
        """Return tuples of (settings_key, category_label)."""
        return [(key, model.__name__) for key, model in self._category_types.items()]

    def fields_for_category(self, category_key: str) -> list[str]:
        model = self._category_types[category_key]
        return list(model.model_fields.keys())

    def field_description(self, category_key: str, field_key: str) -> str:
        model = self._category_types[category_key]
        field = model.model_fields[field_key]
        if isinstance(field.description, str) and field.description.strip():
            return field.description.strip()
        return "Sem descrição disponível."

    def get_effective_value(self, category_key: str, field_key: str) -> Any:
        category = getattr(settings, category_key)
        return getattr(category, field_key)

    def env_var_name(self, category_key: str, field_key: str) -> str:
        return f"ANI_TUPI__{category_key.upper()}__{field_key.upper()}"

    def is_env_override_active(self, category_key: str, field_key: str) -> bool:
        return self.env_var_name(category_key, field_key) in os.environ

    def parse_input_value(
        self,
        category_key: str,
        field_key: str,
        raw_value: str,
        current_value: Any | None = None,
    ) -> Any:
        model = self._category_types[category_key]
        field = model.model_fields[field_key]
        if (
            category_key == "plugins"
            and field_key == "priority_order"
            and isinstance(current_value, list)
        ):
            return _parse_priority_order(raw_value, current_value)
        return _parse_raw_value(raw_value, field.annotation)

    def validate_staged(self, staged_changes: dict[str, dict[str, Any]]) -> AppSettings:
        existing = load_user_settings_overrides()
        merged = _deep_merge(existing, staged_changes)
        return AppSettings.model_validate(merged)

    def save_staged(self, staged_changes: dict[str, dict[str, Any]]) -> None:
        existing = load_user_settings_overrides()
        merged = _deep_merge(existing, staged_changes)
        save_user_settings_overrides(merged)


def _parse_raw_value(raw_value: str, annotation: Any) -> Any:
    text = raw_value.strip()
    origin = get_origin(annotation)

    if origin is list:
        args = get_args(annotation)
        elem_type = args[0] if args else str
        if not text:
            return []
        if text.startswith("["):
            loaded = json.loads(text)
            if not isinstance(loaded, list):
                raise ValueError("Expected a JSON list")
            return [_parse_scalar(str(item), elem_type) for item in loaded]
        return [_parse_scalar(item.strip(), elem_type) for item in text.split(",") if item.strip()]

    return _parse_scalar(text, annotation)


def _parse_scalar(text: str, annotation: Any) -> Any:
    if annotation is bool:
        normalized = text.lower()
        if normalized in {"1", "true", "t", "yes", "y", "on", "sim", "s"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off", "nao", "não"}:
            return False
        raise ValueError("Expected boolean value (true/false)")

    if annotation is int:
        return int(text)

    if annotation is float:
        return float(text)

    if annotation is Path:
        return Path(text).expanduser()

    origin = get_origin(annotation)
    if origin is None and annotation is str:
        return text

    args = get_args(annotation)
    if origin is not None and type(None) in args:
        if text.lower() in {"none", "null", ""}:
            return None
        inner = next(arg for arg in args if arg is not type(None))
        return _parse_scalar(text, inner)

    return text


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = dict(base)
    for key, value in updates.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = _deep_merge(current, value)
        else:
            result[key] = value
    return result


def _get_available_plugin_names() -> set[str]:
    plugins_dir = Path(__file__).parent.parent / "scrapers" / "plugins"
    skip = {"__init__.py", "utils.py"}
    return {f.stem for f in plugins_dir.glob("*.py") if f.name not in skip}


def _parse_priority_order(raw_value: str, current_order: list[Any]) -> list[Any]:
    text = raw_value.strip()
    if not text:
        return current_order

    if text.startswith("["):
        loaded = json.loads(text)
        if not isinstance(loaded, list):
            raise ValueError("Expected a JSON list")
        desired = [str(item).strip() for item in loaded if str(item).strip()]
    else:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) == 1 and " " in parts[0]:
            parts = [part.strip() for part in parts[0].split() if part.strip()]
        desired = parts

    available = _get_available_plugin_names()
    unknown = [name for name in desired if name not in available]
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}")

    deduped_desired: list[Any] = []
    for name in desired:
        if name not in deduped_desired:
            deduped_desired.append(name)

    tail = [name for name in current_order if name not in deduped_desired]
    return [*deduped_desired, *tail]


__all__ = ["SettingsManagementService", "ValidationError"]
