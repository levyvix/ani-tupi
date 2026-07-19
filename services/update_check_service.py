"""Startup update-check service.

Fetches latest upstream version with cooldown caching, compares versions,
and returns an immutable result for CLI/TUI rendering.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scrapers.plugins.utils import http_get_with_retry

from models.config import UpdateCheckSettings, get_data_path, settings
from models.models import UpdateCheckResult, UpdateCheckState
from utils.logging import get_logger

logger = get_logger(__name__)


class UpdateCheckService:
    """Checks for newer ani-tupi versions with persisted cooldown state."""

    def __init__(
        self,
        update_settings: UpdateCheckSettings | None = None,
        state_path: Path | None = None,
        package_name: str = "ani-tupi",
        local_version: str | None = None,
    ) -> None:
        self.settings = update_settings or settings.updates
        self.state_path = state_path or (get_data_path() / "update_check_state.json")
        self.package_name = package_name
        self._local_version_override = local_version

    def get_version_info(self) -> tuple[str, str | None]:
        """Return (local_version, latest_version) without cooldown caching.

        latest_version is None when the remote release source is unreachable.
        Use this for explicit version display (--version / update command).
        """
        local_version = self._get_local_version()
        latest_version = self._fetch_latest_version()
        return local_version, latest_version

    def is_remote_newer(self, local_version: str, remote_version: str) -> bool:
        """Public wrapper for version comparison.

        Returns True when remote_version is strictly greater than local_version.
        """
        return self._is_remote_newer(local_version, remote_version)

    def check_for_updates(self) -> UpdateCheckResult:
        """Run update check and return a fail-safe result for startup rendering."""
        local_version = self._get_local_version()

        if not self.settings.enabled:
            return UpdateCheckResult(local_version=local_version)

        cached = self._get_cached_result(local_version)
        if cached is not None:
            return cached

        latest_version = self._fetch_latest_version()
        if latest_version is None:
            return UpdateCheckResult(local_version=local_version)

        update_available = self._is_remote_newer(local_version, latest_version)
        result = self._build_result(local_version, latest_version, update_available)
        self._save_state(
            UpdateCheckState(
                last_checked_at=datetime.now(UTC),
                last_latest_version=latest_version,
                last_update_available=update_available,
            )
        )

        return result

    def _build_result(
        self,
        local_version: str,
        latest_version: str,
        update_available: bool,
    ) -> UpdateCheckResult:
        message = None
        if update_available:
            message = (
                "⬆️  Nova versão disponível: "
                f"{local_version} -> {latest_version}. "
                f"Atualize com: {self.settings.update_command}"
            )

        return UpdateCheckResult(
            local_version=local_version,
            latest_version=latest_version,
            update_available=update_available,
            message=message,
        )

    def _get_cached_result(self, local_version: str) -> UpdateCheckResult | None:
        state = self._load_state()
        if state is None:
            return None

        if state.last_checked_at is None or not state.last_latest_version:
            return None

        last_checked_at = state.last_checked_at
        if last_checked_at.tzinfo is None:
            last_checked_at = last_checked_at.replace(tzinfo=UTC)

        now = datetime.now(UTC)
        interval = timedelta(hours=self.settings.interval_hours)
        if now - last_checked_at > interval:
            return None

        latest_version = state.last_latest_version
        update_available = self._is_remote_newer(local_version, latest_version)
        return self._build_result(local_version, latest_version, update_available)

    def _load_state(self) -> UpdateCheckState | None:
        if not self.state_path.exists():
            return None

        try:
            with self.state_path.open() as f:
                data = json.load(f)
            return UpdateCheckState.model_validate(data)
        except Exception as exc:
            logger.debug(f"Update-check cache load failed: {exc}")
            return None

    def _save_state(self, state: UpdateCheckState) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with self.state_path.open("w") as f:
                json.dump(state.model_dump(mode="json"), f, indent=2)
        except Exception as exc:
            logger.debug(f"Update-check cache save failed: {exc}")

    def _fetch_latest_version(self) -> str | None:
        try:
            response = http_get_with_retry(
                self.settings.release_source_url,
                timeout=self.settings.request_timeout_seconds,
            )
            payload = response.json()
        except (ValueError, TypeError) as exc:
            logger.debug(f"Update-check request failed: {exc}")
            return None

        latest_version = self._extract_latest_version(payload)
        if latest_version is None:
            logger.debug("Update-check payload did not include a valid version field")

        return latest_version

    def _extract_latest_version(self, payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None

        info = payload.get("info")
        if isinstance(info, dict) and isinstance(info.get("version"), str):
            return self._normalize_version(info["version"])

        for key in ("tag_name", "version"):
            raw_version = payload.get(key)
            if isinstance(raw_version, str):
                return self._normalize_version(raw_version)

        return None

    def _get_local_version(self) -> str:
        if self._local_version_override:
            normalized = self._normalize_version(self._local_version_override)
            if normalized:
                return normalized

        try:
            raw_version = importlib.metadata.version(self.package_name)
            normalized = self._normalize_version(raw_version)
            if normalized:
                return normalized
        except importlib.metadata.PackageNotFoundError:
            pass
        except Exception as exc:
            logger.debug(f"Unable to read installed package version: {exc}")

        pyproject_version = self._read_version_from_pyproject()
        if pyproject_version:
            return pyproject_version

        return "0.0.0"

    def _read_version_from_pyproject(self) -> str | None:
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if not pyproject_path.exists():
            return None

        try:
            with pyproject_path.open("rb") as f:
                pyproject_data = tomllib.load(f)
            project_data = pyproject_data.get("project", {})
            raw_version = project_data.get("version")
            if isinstance(raw_version, str):
                return self._normalize_version(raw_version)
        except Exception as exc:
            logger.debug(f"Unable to read version from pyproject.toml: {exc}")

        return None

    def _normalize_version(self, version: str) -> str | None:
        normalized = version.strip()
        if not normalized:
            return None

        if normalized.startswith(("v", "V")):
            normalized = normalized[1:]

        return normalized or None

    def _is_remote_newer(self, local_version: str, remote_version: str) -> bool:
        local_key = self._version_key(local_version)
        remote_key = self._version_key(remote_version)
        if local_key is None or remote_key is None:
            return False

        max_len = max(len(local_key), len(remote_key))
        padded_local = local_key + (0,) * (max_len - len(local_key))
        padded_remote = remote_key + (0,) * (max_len - len(remote_key))
        return padded_remote > padded_local

    def _version_key(self, version: str) -> tuple[int, ...] | None:
        normalized = self._normalize_version(version)
        if not normalized:
            return None

        core = normalized.split("+", maxsplit=1)[0]
        numeric_parts = re.findall(r"\d+", core)
        if not numeric_parts:
            return None

        return tuple(int(part) for part in numeric_parts)
