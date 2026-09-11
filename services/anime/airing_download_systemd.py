"""Systemd user timer and private launcher support for airing downloads."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from models.config import get_data_path, get_user_config_path, settings

from .airing_download_cron import AiringDownloadConfigStore, AiringDownloadLauncher, CronError
from .airing_download_scheduler import AiringDownloadSettings

__all__ = ["AiringDownloadSystemd", "SystemdError", "SystemdStatus"]


SERVICE_NAME = "ani-tupi-airing-download.service"
TIMER_NAME = "ani-tupi-airing-download.timer"


class SystemdError(RuntimeError):
    """Actionable error while preparing or updating the user timer."""


@dataclass(frozen=True)
class SystemdStatus:
    installed: bool
    daemon: str
    systemd_available: bool
    service_path: str
    timer_path: str
    launcher_path: str
    state_path: str
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "daemon": self.daemon,
            "systemd_available": self.systemd_available,
            "service_path": self.service_path,
            "timer_path": self.timer_path,
            "launcher_path": self.launcher_path,
            "state_path": self.state_path,
            "message": self.message,
        }


class AiringDownloadSystemd:
    """Own the two user units used by the airing download monitor."""

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
        user_unit_dir: Path | None = None,
    ) -> None:
        self.state_dir = (state_dir or get_data_path() / "airing-downloads").absolute()
        self.config_store = config_store or AiringDownloadConfigStore()
        self.runner = runner or subprocess.run
        self.which = which
        self.environment = environment if environment is not None else dict(os.environ)
        self.project_root = project_root
        self.executable = executable
        self.uv_executable = uv_executable
        self.user_unit_dir = (
            user_unit_dir or get_user_config_path().parent / "systemd" / "user"
        ).absolute()
        self.service_path = self.user_unit_dir / SERVICE_NAME
        self.timer_path = self.user_unit_dir / TIMER_NAME
        self.launcher_path = self.state_dir / "airing-download-launcher"
        self.state_path = self.state_dir / "airing_download_state.json"

    @property
    def systemctl_executable(self) -> str:
        executable = self.which("systemctl")
        if not executable:
            raise SystemdError("systemctl não está instalado ou não está no PATH.")
        return str(Path(executable).absolute())

    def install(self, settings_obj: AiringDownloadSettings | None = None) -> SystemdStatus:
        settings_obj = settings_obj or AiringDownloadSettings.from_application(
            self.config_store.load()
        )
        systemctl = self.systemctl_executable
        token_path = getattr(getattr(settings, "anilist", None), "token_file", None)
        if token_path is not None and not Path(token_path).expanduser().is_file():
            raise SystemdError(
                "Credencial AniList local não encontrada; execute anilist auth primeiro."
            )

        managed_paths = (self.launcher_path, self.service_path, self.timer_path)
        previous_files = {
            path: path.read_bytes() if path.is_file() else None for path in managed_paths
        }
        launcher = AiringDownloadLauncher(
            path=self.launcher_path,
            project_root=self.project_root,
            executable=self.executable,
            uv_executable=self.uv_executable,
            environment=self.environment,
            state_path=self.state_path,
        )
        try:
            launcher.render()
            self._write_unit(self.service_path, self._service_content(launcher.path))
            self._write_unit(self.timer_path, self._timer_content(settings_obj))
            self._systemctl(systemctl, "daemon-reload")
            self._systemctl(systemctl, "enable", "--now", TIMER_NAME)
            self.config_store.save(settings_obj.model_dump(mode="json"))
            result = self.status()
            if not result.installed:
                raise SystemdError(
                    result.message or "O timer foi escrito, mas não foi confirmado como ativo."
                )
            return result
        except CronError as exc:
            self._restore_managed_files(previous_files)
            raise SystemdError(str(exc)) from exc
        except Exception:
            self._restore_managed_files(previous_files)
            try:
                self._systemctl(systemctl, "daemon-reload")
            except (OSError, SystemdError):
                pass
            raise

    def remove(self) -> SystemdStatus:
        if not self.service_path.exists() and not self.timer_path.exists():
            return self.status()
        systemctl = self.systemctl_executable
        if self.timer_path.exists() or self.service_path.exists():
            self._systemctl(systemctl, "disable", "--now", TIMER_NAME)
        for path in (self.timer_path, self.service_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self._systemctl(systemctl, "daemon-reload")
        result = self.status()
        if result.installed:
            raise SystemdError("As unidades do monitor ainda estão instaladas após remove.")
        return result

    def _restore_managed_files(self, previous_files: dict[Path, bytes | None]) -> None:
        """Restore the launcher and units if activation did not complete."""
        for path, content in previous_files.items():
            if content is None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def status(self) -> SystemdStatus:
        systemctl = self.which("systemctl")
        if not systemctl:
            return self._status(False, "indisponível", False, "systemctl não encontrado")
        executable = str(Path(systemctl).absolute())
        enabled = self._systemctl_status(executable, "is-enabled", TIMER_NAME)
        active = self._systemctl_status(executable, "is-active", TIMER_NAME)
        installed = (
            self.service_path.is_file() and self.timer_path.is_file() and enabled.returncode == 0
        )
        if active.returncode == 0:
            daemon = "ativo"
        elif enabled.returncode == 0:
            daemon = "parado"
        else:
            daemon = "desconhecido"
        message = None
        if enabled.returncode != 0 and (self.service_path.exists() or self.timer_path.exists()):
            message = _decode_output(enabled.stderr).strip() or "timer não habilitado"
        return self._status(installed, daemon, True, message)

    def _status(
        self, installed: bool, daemon: str, available: bool, message: str | None
    ) -> SystemdStatus:
        return SystemdStatus(
            installed=installed,
            daemon=daemon,
            systemd_available=available,
            service_path=str(self.service_path),
            timer_path=str(self.timer_path),
            launcher_path=str(self.launcher_path),
            state_path=str(self.state_path),
            message=message,
        )

    def _systemctl(self, executable: str, *arguments: str) -> None:
        result = self._systemctl_status(executable, *arguments)
        if result.returncode != 0:
            detail = _decode_output(result.stderr).strip() or _decode_output(result.stdout).strip()
            raise SystemdError(f"systemctl --user {' '.join(arguments)} falhou: {detail}")

    def _systemctl_status(self, executable: str, *arguments: str) -> subprocess.CompletedProcess:
        return self.runner(
            [executable, "--user", *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def _write_unit(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def _service_content(self, launcher_path: Path) -> str:
        return "\n".join(
            [
                "[Unit]",
                "Description=ani-tupi airing download monitor",
                "",
                "[Service]",
                "Type=oneshot",
                f"ExecStart={_systemd_quote(str(launcher_path.absolute()))}",
                "",
            ]
        )

    def _timer_content(self, settings_obj: AiringDownloadSettings) -> str:
        interval = settings_obj.poll_interval_minutes
        calendar = "*-*-* *:00:00" if interval == 60 else f"*-*-* *:00/{interval}"
        return "\n".join(
            [
                "[Unit]",
                "Description=ani-tupi airing download schedule",
                "",
                "[Timer]",
                f"OnCalendar={calendar}",
                "Persistent=true",
                "Unit=" + SERVICE_NAME,
                "AccuracySec=1min",
                "",
                "[Install]",
                "WantedBy=timers.target",
                "",
            ]
        )


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _decode_output(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""
