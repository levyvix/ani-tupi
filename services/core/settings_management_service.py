"""Interactive settings management service for CLI configuration."""

from __future__ import annotations

import json
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

    _sections = (
        ("account", "Conta e AniList", ("anilist", "offline_sync")),
        ("search", "Busca de animes", ("search",)),
        ("sources", "Fontes de anime", ("plugins",)),
        ("anime_download", "Downloads de anime", ("anime_download", "airing_downloads")),
        ("manga", "Leitura e downloads de mangá", ("manga",)),
        ("cache", "Cache e desempenho", ("cache", "performance")),
        ("airing", "Novos episódios", ("airing",)),
        ("updates", "Atualizações", ("updates",)),
        ("player", "Player e diagnóstico", ("runtime",)),
    )

    def __init__(self) -> None:
        self._category_types = {
            name: field.annotation
            for name, field in AppSettings.model_fields.items()
            if hasattr(field.annotation, "model_fields")
        }

    def categories(self) -> list[tuple[str, str]]:
        """Return user-facing sections of related settings."""
        return [(key, label) for key, label, _ in self._sections]

    def fields_in_category(self, category_key: str) -> list[tuple[str, str]]:
        """Return (settings group, field name) pairs for a user-facing section."""
        groups = next(groups for key, _, groups in self._sections if key == category_key)
        return [
            (group, field_name)
            for group in groups
            for field_name in self.fields_for_category(group)
        ]

    def category_description(self, category_key: str) -> str:
        """Return a short explanation for a settings section."""
        descriptions = {
            "account": "Preferências do AniList e sincronização quando estiver offline.",
            "search": "Como os resultados de anime são encontrados e exibidos.",
            "sources": "Ative fontes e defina a ordem de preferência.",
            "anime_download": "Pastas, formato e comportamento dos downloads de anime.",
            "manga": "Fontes, leitor de PDF e comportamento dos downloads de mangá.",
            "cache": "Validade dos dados guardados e limites de desempenho.",
            "airing": "Exibição de animes com episódios recentes.",
            "updates": "Verificação de novas versões do ani-tupi.",
            "player": "Opções do player e registros para diagnóstico.",
        }
        return descriptions[category_key]

    def fields_for_category(self, category_key: str) -> list[str]:
        model = self._category_types[category_key]
        return [
            field_name
            for field_name, field in model.model_fields.items()
            if not (
                isinstance(field.json_schema_extra, dict)
                and field.json_schema_extra.get("editable") is False
            )
        ]

    def field_description(self, category_key: str, field_key: str) -> str:
        model = self._category_types[category_key]
        field = model.model_fields[field_key]
        if isinstance(field.description, str) and field.description.strip():
            return field.description.strip()
        return "Sem descrição disponível."

    def get_effective_value(self, category_key: str, field_key: str) -> Any:
        category = getattr(settings, category_key)
        return getattr(category, field_key)

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
    from scrapers.loader import discover_plugin_names

    return set(discover_plugin_names())


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
