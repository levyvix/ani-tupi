"""User crontab and private launcher support for airing downloads."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from models.config import get_data_path, get_user_config_path, settings

from .airing_download_scheduler import AiringDownloadSettings

__all__ = [
    "AiringDownloadConfigStore",
    "AiringDownloadCron",
    "AiringDownloadLauncher",
    "CronError",
    "CronStatus",
]


START_MARKER = "# >>> ani-tupi airing-downloads >>>"
END_MARKER = "# <<< ani-tupi airing-downloads <<<"


class CronError(RuntimeError):
    """Actionable error while preparing or updating the user crontab."""


@dataclass(frozen=True)
class CronStatus:
    installed: bool
    daemon: str
    crontab_available: bool
    launcher_path: str
    state_path: str
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "daemon": self.daemon,
            "crontab_available": self.crontab_available,
            "launcher_path": self.launcher_path,
            "state_path": self.state_path,
            "message": self.message,
        }


class AiringDownloadConfigStore:
    """Persist only monitor settings, separately from application settings."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_user_config_path() / "airing_downloads.json"

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, values: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(values, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.chmod(raw_path, 0o600)
            os.replace(raw_path, self.path)
        finally:
            if os.path.exists(raw_path):
                os.unlink(raw_path)


class AiringDownloadLauncher:
    """Generate a private, session-independent launcher script."""

    def __init__(
        self,
        *,
        path: Path,
        project_root: Path | None = None,
        executable: str | None = None,
        uv_executable: str | None = None,
        environment: dict[str, str] | None = None,
        state_path: Path | None = None,
    ) -> None:
        self.path = path.expanduser().absolute()
        self.project_root = (project_root or _project_root()).absolute()
        self.executable = executable
        self.uv_executable = uv_executable
        self.environment = environment if environment is not None else dict(os.environ)
        self.state_path = (state_path or self.path.parent / "airing_download_state.json").absolute()

    def command(self) -> list[str]:
        if (self.project_root / "pyproject.toml").is_file():
            uv = self.uv_executable or shutil.which("uv")
            if not uv:
                raise CronError("uv não encontrado para executar o checkout local.")
            return [
                str(Path(uv).absolute()),
                "run",
                "--no-sync",
                "--project",
                str(self.project_root),
                "ani-tupi",
                "airing",
                "run",
            ]
        executable = self.executable or shutil.which("ani-tupi")
        if not executable:
            raise CronError("Executável instalado ani-tupi não encontrado.")
        return [str(Path(executable).absolute()), "airing", "run"]

    def render(self) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        command = " ".join(shlex.quote(part) for part in self.command())
        lines = ["#!/bin/sh", "umask 077", "set -eu"]
        xdg = self._xdg_environment()
        for key, value in xdg.items():
            lines.append(f"export {key}={shlex.quote(value)}")
        for key, value in sorted(self._safe_overrides().items()):
            lines.append(f"export {key}={shlex.quote(value)}")
        lines.append(f"exec {command}")
        content = "\n".join(lines) + "\n"
        self.path.write_text(content, encoding="utf-8")
        os.chmod(self.path, 0o700)
        return content

    def _xdg_environment(self) -> dict[str, str]:
        config_path = get_user_config_path().absolute()
        state_root = get_data_path().parent.absolute()
        data_root = Path(
            self.environment.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        ).absolute()
        return {
            "XDG_CONFIG_HOME": str(config_path.parent),
            "XDG_STATE_HOME": str(state_root),
            "XDG_DATA_HOME": str(data_root),
        }

    def _safe_overrides(self) -> dict[str, str]:
        allowed = {
            "ANI_TUPI__AIRING_DOWNLOADS__POLL_INTERVAL_MINUTES",
            "ANI_TUPI__SEARCH__PREFERRED_AUDIO",
        }
        return {
            key: value
            for key, value in self.environment.items()
            if key in allowed and isinstance(value, str)
        }


class AiringDownloadCron:
    """Own exactly one marked block in the user's crontab."""

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        config_store: AiringDownloadConfigStore | None = None,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        environment: dict[str, str] | None = None,
        project_root: Path | None = None,
        executable: str | None = None,
        uv_executable: str | None = None,
    ) -> None:
        self.state_dir = (state_dir or get_data_path() / "airing-downloads").absolute()
        self.config_store = config_store or AiringDownloadConfigStore()
        self.runner = runner or subprocess.run
        self.which = which
        self.environment = environment if environment is not None else dict(os.environ)
        self.project_root = project_root
        self.executable = executable
        self.uv_executable = uv_executable
        self.launcher_path = self.state_dir / "airing-download-launcher"
        self.state_path = self.state_dir / "airing_download_state.json"

    @property
    def crontab_executable(self) -> str:
        executable = self.which("crontab")
        if not executable:
            raise CronError("crontab não está instalado ou não está no PATH.")
        return str(Path(executable).absolute())

    def read_crontab(self) -> str:
        executable = self.crontab_executable
        result = self.runner([executable, "-l"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return _decode_output(result.stdout)
        stderr = _decode_output(result.stderr).lower()
        if "no crontab" in stderr or "nenhum crontab" in stderr:
            return ""
        raise CronError(f"Não foi possível ler o crontab: {_decode_output(result.stderr).strip()}")

    def write_crontab(self, content: str) -> None:
        executable = self.crontab_executable
        result = self.runner(
            [executable, "-"], input=content, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise CronError(
                f"Não foi possível escrever o crontab: {_decode_output(result.stderr).strip()}"
            )

    def install(self, settings_obj: AiringDownloadSettings | None = None) -> CronStatus:
        settings_obj = settings_obj or AiringDownloadSettings.from_application(
            self.config_store.load()
        )
        # Validate crontab and launcher prerequisites before changing the crontab.
        current = self.read_crontab()
        token_path = getattr(getattr(settings, "anilist", None), "token_file", None)
        if token_path is not None and not Path(token_path).expanduser().is_file():
            raise CronError(
                "Credencial AniList local não encontrada; execute anilist auth primeiro."
            )
        launcher = AiringDownloadLauncher(
            path=self.launcher_path,
            project_root=self.project_root,
            executable=self.executable,
            uv_executable=self.uv_executable,
            environment=self.environment,
            state_path=self.state_path,
        )
        launcher.render()
        updated = _replace_managed_block(current, self._managed_block(settings_obj, launcher.path))
        if updated != current:
            self.write_crontab(updated)
        reread = self.read_crontab()
        if _managed_block_count(reread) != 1:
            raise CronError("A instalação foi escrita, mas o bloco gerenciado não foi confirmado.")
        self.config_store.save(settings_obj.model_dump(mode="json"))
        return self.status(crontab=reread)

    def remove(self) -> CronStatus:
        current = self.read_crontab()
        updated = _remove_managed_block(current)
        if updated != current:
            self.write_crontab(updated)
        reread = self.read_crontab()
        if _managed_block_count(reread) != 0:
            raise CronError("O bloco do monitor ainda está presente após remove.")
        return self.status(crontab=reread)

    def status(self, *, crontab: str | None = None) -> CronStatus:
        try:
            content = crontab if crontab is not None else self.read_crontab()
            available = True
        except CronError as exc:
            content = ""
            available = False
            message = str(exc)
        else:
            message = None
        installed = _managed_block_count(content) == 1
        daemon = self._daemon_status() if available else "unknown"
        return CronStatus(
            installed, daemon, available, str(self.launcher_path), str(self.state_path), message
        )

    def _daemon_status(self) -> str:
        if not self.which("crond") and not self.which("cron"):
            return "unknown"
        # Presence of a daemon binary does not prove that it is running.
        return "unknown"

    def _managed_block(self, settings_obj: AiringDownloadSettings, launcher_path: Path) -> str:
        schedule = (
            "0 * * * *"
            if settings_obj.poll_interval_minutes == 60
            else f"*/{settings_obj.poll_interval_minutes} * * * *"
        )
        command = _escape_cron_percent(shlex.quote(str(launcher_path.absolute())))
        return f"{START_MARKER}\n{schedule} {command}\n{END_MARKER}\n"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _decode_output(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _escape_cron_percent(value: str) -> str:
    return value.replace("%", r"\%")


def _managed_block_count(content: str) -> int:
    return content.count(START_MARKER)


def _remove_managed_block(content: str) -> str:
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    in_block = False
    found_end = False
    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped == START_MARKER:
            if in_block:
                raise CronError("Crontab contém blocos gerenciados duplicados ou aninhados.")
            in_block = True
            continue
        if stripped == END_MARKER:
            if not in_block:
                raise CronError("Crontab contém marcador de fim sem início.")
            in_block = False
            found_end = True
            continue
        if not in_block:
            output.append(line)
    if in_block or (_managed_block_count(content) and not found_end):
        raise CronError("Crontab contém um bloco gerenciado incompleto.")
    return "".join(output)


def _replace_managed_block(content: str, block: str) -> str:
    without = _remove_managed_block(content) if _managed_block_count(content) else content
    if without and not without.endswith(("\n", "\r")):
        without += "\n"
    return without + block
