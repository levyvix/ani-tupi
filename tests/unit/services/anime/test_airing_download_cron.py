"""Tests for the isolated user-crontab adapter and launcher."""

from __future__ import annotations

import subprocess
from pathlib import Path

from services.anime.airing_download_cron import (
    END_MARKER,
    START_MARKER,
    AiringDownloadConfigStore,
    AiringDownloadCron,
)
from services.anime.airing_download_scheduler import AiringDownloadSettings


class FakeCrontab:
    def __init__(self, content: str):
        self.content = content
        self.writes = 0

    def __call__(self, command, **kwargs):
        if command[-1] == "-l":
            return subprocess.CompletedProcess(command, 0, self.content, "")
        self.content = kwargs["input"]
        self.writes += 1
        return subprocess.CompletedProcess(command, 0, "", "")


def test_install_is_idempotent_and_preserves_external_jobs(tmp_path: Path, monkeypatch):
    external = "MAILTO=user@example.test\n17 4 * * * /path with spaces/task\n"
    runner = FakeCrontab(external)
    token = tmp_path / "token.json"
    token.write_text('{"access_token":"secret-token"}')
    monkeypatch.setattr("services.anime.airing_download_cron.settings.anilist.token_file", token)
    config = AiringDownloadConfigStore(tmp_path / "config.json")
    cron = AiringDownloadCron(
        state_dir=tmp_path / "state with % sign",
        config_store=config,
        runner=runner,
        which=lambda name: "/usr/bin/" + name,
        project_root=tmp_path / "published",
        executable="/opt/ani tupi/bin/ani-tupi",
    )

    first = cron.install(AiringDownloadSettings(poll_interval_minutes=15))
    first_content = runner.content
    second = cron.install(AiringDownloadSettings(poll_interval_minutes=15))

    assert first.installed and second.installed
    assert runner.content == first_content
    assert runner.writes == 1
    assert runner.content.startswith(external)
    assert runner.content.count(START_MARKER) == 1
    assert runner.content.count(END_MARKER) == 1
    assert r"\%" in runner.content
    assert config.load()["poll_interval_minutes"] == 15


def test_remove_only_removes_managed_block(tmp_path: Path):
    external = "0 1 * * * external\n"
    block = f"{START_MARKER}\n*/30 * * * * /private/launcher\n{END_MARKER}\n"
    runner = FakeCrontab(external + block)
    cron = AiringDownloadCron(
        state_dir=tmp_path / "state",
        runner=runner,
        which=lambda name: "/usr/bin/" + name,
    )

    result = cron.remove()

    assert not result.installed
    assert runner.content == external
