"""Tests for the update command handler."""

from unittest.mock import Mock, patch

import httpx

from commands.update import update
from models.config import settings


def test_update_command_reports_current_version_without_running_update(monkeypatch):
    """No update command should run when remote version matches local."""
    monkeypatch.setattr(
        settings.updates,
        "update_command",
        "echo upgrade",
    )

    with patch("services.update_check_service.importlib.metadata.version", return_value="0.8.0"):
        with patch.object(httpx.Client, "get") as mock_get:
            mock_get.return_value = Mock(
                status_code=200,
                json=lambda: {"info": {"version": "0.8.0"}},
                raise_for_status=lambda: None,
            )

            with patch("commands.update.subprocess.run") as mock_run:
                result = update(None)

    assert result == 0
    assert mock_run.call_count == 0


def test_update_command_runs_configured_update_when_new_version_exists(monkeypatch):
    """A newer remote version should trigger the configured update command."""
    monkeypatch.setattr(
        settings.updates,
        "update_command",
        "echo upgrade",
    )

    with patch("services.update_check_service.importlib.metadata.version", return_value="0.8.0"):
        with patch.object(httpx.Client, "get") as mock_get:
            mock_get.return_value = Mock(
                status_code=200,
                json=lambda: {"info": {"version": "0.9.0"}},
                raise_for_status=lambda: None,
            )

            with patch("commands.update.subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0)
                result = update(None)

    assert result == 0
    mock_run.assert_called_once_with("echo upgrade", shell=True)


def test_update_command_handles_release_lookup_failure(monkeypatch):
    """Remote release failures should not crash the command."""
    monkeypatch.setattr(
        settings.updates,
        "update_command",
        "echo upgrade",
    )

    with patch("services.update_check_service.importlib.metadata.version", return_value="0.8.0"):
        with patch.object(httpx.Client, "get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timeout")

            with patch("commands.update.subprocess.run") as mock_run:
                result = update(None)

    assert result == 0
    assert mock_run.call_count == 0
