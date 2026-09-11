"""Persistence and precedence rules for airing download source bindings."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Literal

from models.config import get_data_path
from models.download import AiringSourceBinding, AiringSourceRecord
from services.anime.download_catalog import catalog_lock
from utils.logging import get_logger

__all__ = [
    "AIRING_SOURCES_FILE",
    "AiringSourceStore",
    "EffectiveAiringSource",
    "AmbiguousAiringSourceError",
    "clear_configured_source",
    "get_effective_source",
    "invalidate_last_played_source",
    "load_airing_source",
    "save_configured_source",
    "save_last_played_source",
]


logger = get_logger(__name__)
AIRING_SOURCES_FILE = get_data_path() / "airing_download_sources.json"


class AmbiguousAiringSourceError(ValueError):
    """Raised when a source context cannot identify one safe season/source."""


@dataclass(frozen=True)
class EffectiveAiringSource:
    """Resolved source plus the reason it was or was not selected."""

    binding: AiringSourceBinding | None
    origin: Literal["configured", "last_played", "missing", "configured_invalid"]
    reason: str | None = None


def _is_usable(binding: AiringSourceBinding | None) -> bool:
    return binding is not None and binding.season is not None


class AiringSourceStore:
    """Atomically persist independent configured and last-played bindings."""

    _lock = RLock()

    def __init__(self, file_path: Path | None = None) -> None:
        self.file_path = Path(file_path or AIRING_SOURCES_FILE)

    def _load_raw(self) -> dict:
        if not self.file_path.exists():
            return {}
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}

        # Accept an early envelope shape if one was created during development,
        # while writing the stable and simple ID-keyed shape below.
        entries = data.get("sources")
        return entries if isinstance(entries, dict) else data

    def _load_records(self) -> dict[str, AiringSourceRecord]:
        records: dict[str, AiringSourceRecord] = {}
        for anilist_id, value in self._load_raw().items():
            if not str(anilist_id).isdigit() or not isinstance(value, dict):
                continue
            try:
                records[str(anilist_id)] = AiringSourceRecord.model_validate(value)
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring invalid airing source record for AniList ID %s", anilist_id
                )
        return records

    def load(self, anilist_id: int) -> AiringSourceRecord | None:
        """Return one record, preserving ``None`` for an unknown ID."""
        with self._lock:
            return self._load_records().get(str(anilist_id))

    def _write_records(self, records: dict[str, AiringSourceRecord]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            anilist_id: record.model_dump(mode="json", exclude_none=True)
            for anilist_id, record in records.items()
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.file_path.parent,
                prefix=f".{self.file_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(payload, temporary, indent=2, ensure_ascii=False)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.file_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _require_safe_context(binding: AiringSourceBinding) -> None:
        if binding.season is None:
            raise AmbiguousAiringSourceError(
                "airing source context must identify exactly one season"
            )
        if not binding.source or "," in binding.source or binding.source.lower() == "mixed":
            raise AmbiguousAiringSourceError(
                "airing source context must identify exactly one source"
            )

    def _update(
        self,
        anilist_id: int,
        field: Literal["configured", "last_played"],
        binding: AiringSourceBinding,
    ) -> None:
        if anilist_id <= 0:
            raise ValueError("anilist_id must be positive")
        self._require_safe_context(binding)
        with self._lock, catalog_lock(self.file_path):
            records = self._load_records()
            record = records.get(str(anilist_id), AiringSourceRecord())
            records[str(anilist_id)] = record.model_copy(update={field: binding})
            self._write_records(records)

    def save_configured(self, anilist_id: int, binding: AiringSourceBinding) -> None:
        """Save explicit configuration without touching playback evidence."""
        self._update(anilist_id, "configured", binding)

    def save_last_played(self, anilist_id: int, binding: AiringSourceBinding) -> None:
        """Save confirmed remote playback without touching configuration."""
        self._update(anilist_id, "last_played", binding)

    def clear_configured(self, anilist_id: int) -> None:
        """Remove only the explicit preference, retaining last playback."""
        with self._lock, catalog_lock(self.file_path):
            records = self._load_records()
            record = records.get(str(anilist_id))
            if record is None:
                return
            updated = record.model_copy(update={"configured": None})
            if updated.last_played is None:
                records.pop(str(anilist_id), None)
            else:
                records[str(anilist_id)] = updated
            self._write_records(records)

    def invalidate_last_played(self, anilist_id: int) -> None:
        """Discard incomplete playback evidence while preserving configuration."""
        with self._lock, catalog_lock(self.file_path):
            records = self._load_records()
            record = records.get(str(anilist_id))
            if record is None:
                return
            updated = record.model_copy(update={"last_played": None})
            if updated.configured is None:
                records.pop(str(anilist_id), None)
            else:
                records[str(anilist_id)] = updated
            self._write_records(records)

    def effective(self, anilist_id: int) -> EffectiveAiringSource:
        """Resolve configured first, with no fallback when it is unusable."""
        record = self.load(anilist_id)
        if record is None:
            return EffectiveAiringSource(None, "missing", "no source binding")
        if record.configured is not None:
            if _is_usable(record.configured):
                return EffectiveAiringSource(record.configured, "configured")
            return EffectiveAiringSource(
                None,
                "configured_invalid",
                "configured source has ambiguous context",
            )
        if _is_usable(record.last_played):
            return EffectiveAiringSource(record.last_played, "last_played")
        return EffectiveAiringSource(None, "missing", "no valid source binding")


def load_airing_source(anilist_id: int, file_path: Path | None = None) -> AiringSourceRecord | None:
    return AiringSourceStore(file_path).load(anilist_id)


def save_configured_source(
    anilist_id: int,
    binding: AiringSourceBinding,
    file_path: Path | None = None,
) -> None:
    AiringSourceStore(file_path).save_configured(anilist_id, binding)


def save_last_played_source(
    anilist_id: int,
    binding: AiringSourceBinding,
    file_path: Path | None = None,
) -> None:
    AiringSourceStore(file_path).save_last_played(anilist_id, binding)


def clear_configured_source(anilist_id: int, file_path: Path | None = None) -> None:
    AiringSourceStore(file_path).clear_configured(anilist_id)


def invalidate_last_played_source(anilist_id: int, file_path: Path | None = None) -> None:
    AiringSourceStore(file_path).invalidate_last_played(anilist_id)


def get_effective_source(anilist_id: int, file_path: Path | None = None) -> EffectiveAiringSource:
    return AiringSourceStore(file_path).effective(anilist_id)
