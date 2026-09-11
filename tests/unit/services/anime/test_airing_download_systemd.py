"""Tests for the systemd user timer adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services.anime.airing_download_cron import AiringDownloadConfigStore
from services.anime.airing_download_scheduler import AiringDownloadSettings
from services.anime.airing_download_systemd import (
    TIMER_NAME,
    AiringDownloadSystemd,
)


class FakeSystemd:
    def __init__(self) -> None:
        self.enabled = False
        self.active = False
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        self.commands.append(command)
        action = command[2:]
        if action == ["enable", "--now", TIMER_NAME]:
            self.enabled = True
            self.active = True
            return subprocess.CompletedProcess(command, 0, "", "")
        if action == ["disable", "--now", TIMER_NAME]:
            self.enabled = False
            self.active = False
            return subprocess.CompletedProcess(command, 0, "", "")
        if action == ["is-enabled", TIMER_NAME]:
            return subprocess.CompletedProcess(command, int(not self.enabled), "", "")
        if action == ["is-active", TIMER_NAME]:
            return subprocess.CompletedProcess(command, int(not self.active), "", "")
        return subprocess.CompletedProcess(command, 0, "", "")


def _monitor(tmp_path: Path, runner: FakeSystemd) -> AiringDownloadSystemd:
    token = tmp_path / "token.json"
    token.write_text('{"access_token":"secret"}', encoding="utf-8")
    config = AiringDownloadConfigStore(tmp_path / "config.json")
    return AiringDownloadSystemd(
        state_dir=tmp_path / "state",
        config_store=config,
        runner=runner,
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
        environment={},
        project_root=tmp_path / "published",
        executable="/opt/ani-tupi/bin/ani-tupi",
        user_unit_dir=tmp_path / "user-units",
    )


def test_install_is_idempotent_and_preserves_external_units(tmp_path: Path, monkeypatch):
    runner = FakeSystemd()
    token = tmp_path / "token.json"
    token.write_text('{"access_token":"secret"}', encoding="utf-8")
    monkeypatch.setattr("services.anime.airing_download_systemd.settings.anilist.token_file", token)
    monitor = _monitor(tmp_path, runner)
    external = monitor.user_unit_dir / "other.timer"
    external.parent.mkdir(parents=True)
    external.write_text("[Timer]\nOnCalendar=daily\n", encoding="utf-8")

    first = monitor.install(AiringDownloadSettings(poll_interval_minutes=15))
    first_service = monitor.service_path.read_text(encoding="utf-8")
    first_timer = monitor.timer_path.read_text(encoding="utf-8")
    second = monitor.install(AiringDownloadSettings(poll_interval_minutes=15))

    assert first.installed and second.installed
    assert first.daemon == second.daemon == "ativo"
    assert monitor.service_path.read_text(encoding="utf-8") == first_service
    assert monitor.timer_path.read_text(encoding="utf-8") == first_timer
    assert 'ExecStart="/tmp' in first_service
    assert "Persistent=true" in first_timer
    assert "OnCalendar=*-*-* *:00/15" in first_timer
    assert "secret" not in first_service + first_timer
    assert external.read_text(encoding="utf-8") == "[Timer]\nOnCalendar=daily\n"


def test_remove_only_removes_managed_units(tmp_path: Path, monkeypatch):
    runner = FakeSystemd()
    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("services.anime.airing_download_systemd.settings.anilist.token_file", token)
    monitor = _monitor(tmp_path, runner)
    external = monitor.user_unit_dir / "other.service"
    external.parent.mkdir(parents=True)
    external.write_text("[Service]\nType=oneshot\n", encoding="utf-8")
    monitor.install(AiringDownloadSettings())

    result = monitor.remove()

    assert not result.installed
    assert not monitor.service_path.exists()
    assert not monitor.timer_path.exists()
    assert external.exists()
    assert not runner.enabled
    assert not runner.active


def test_status_reports_missing_systemd_without_touching_units(tmp_path: Path):
    monitor = AiringDownloadSystemd(
        state_dir=tmp_path / "state",
        user_unit_dir=tmp_path / "user-units",
        which=lambda _name: None,
    )

    result = monitor.status()

    assert not result.installed
    assert result.daemon == "indisponível"
    assert not result.systemd_available
    assert result.message == "systemctl não encontrado"


def test_default_unit_directory_is_the_systemd_user_directory(tmp_path: Path, monkeypatch):
    app_config = tmp_path / ".config" / "ani-tupi"
    monkeypatch.setattr(
        "services.anime.airing_download_systemd.get_user_config_path",
        lambda: app_config,
    )

    monitor = AiringDownloadSystemd(
        state_dir=tmp_path / "state",
        which=lambda _name: None,
    )

    assert monitor.user_unit_dir == app_config.parent / "systemd" / "user"


def test_install_restores_managed_files_when_activation_fails(tmp_path: Path, monkeypatch):
    class FailingSystemd(FakeSystemd):
        def __call__(self, command, **kwargs):
            if command[2:] == ["enable", "--now", TIMER_NAME]:
                self.commands.append(command)
                return subprocess.CompletedProcess(command, 1, "", "activation failed")
            return super().__call__(command, **kwargs)

    runner = FailingSystemd()
    monitor = _monitor(tmp_path, runner)
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "services.anime.airing_download_systemd.settings.anilist.token_file", token_path
    )
    monitor.state_dir.mkdir(parents=True)
    monitor.user_unit_dir.mkdir(parents=True)
    monitor.launcher_path.write_text("old launcher", encoding="utf-8")
    monitor.service_path.write_text("old service", encoding="utf-8")
    monitor.timer_path.write_text("old timer", encoding="utf-8")

    with pytest.raises(Exception, match="activation failed"):
        monitor.install(AiringDownloadSettings())

    assert monitor.launcher_path.read_text(encoding="utf-8") == "old launcher"
    assert monitor.service_path.read_text(encoding="utf-8") == "old service"
    assert monitor.timer_path.read_text(encoding="utf-8") == "old timer"


def test_remove_succeeds_without_systemd_when_units_are_absent(tmp_path: Path):
    monitor = AiringDownloadSystemd(
        state_dir=tmp_path / "state",
        user_unit_dir=tmp_path / "user-units",
        which=lambda _name: None,
    )

    result = monitor.remove()

    assert result.installed is False
    assert result.daemon == "indisponível"
