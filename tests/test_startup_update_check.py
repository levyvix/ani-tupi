"""Startup integration tests for update-check notice behavior."""

from unittest.mock import patch

import pytest

import importlib

import main
from models.models import UpdateCheckResult

# commands/__init__ rebinds the name `update` to the function, shadowing the
# submodule attribute; fetch the real module object from sys.modules.
_update_cmd = importlib.import_module("commands.update")


def test_startup_notice_is_shown_when_update_available():
    """Startup prints notice only when update is available."""
    result = UpdateCheckResult(
        local_version="0.8.0",
        latest_version="0.9.0",
        update_available=True,
        message="⬆️  Nova versão disponível: 0.8.0 -> 0.9.0. Atualize com: uv tool upgrade ani-tupi",
    )

    with patch(
        "services.core.update_check_service.UpdateCheckService.check_for_updates"
    ) as mock_check:
        with patch.object(_update_cmd.logger, "info") as mock_info:
            mock_check.return_value = result
            main.run_startup_update_check()

    mock_info.assert_called_once_with(result.message)


def test_startup_notice_is_hidden_when_no_update():
    """Startup does not print notice when no update exists."""
    result = UpdateCheckResult(
        local_version="0.8.0",
        latest_version="0.8.0",
        update_available=False,
        message=None,
    )

    with patch(
        "services.core.update_check_service.UpdateCheckService.check_for_updates"
    ) as mock_check:
        with patch.object(_update_cmd.logger, "info") as mock_info:
            mock_check.return_value = result
            main.run_startup_update_check()

    assert mock_info.call_count == 0


def test_startup_continues_when_update_check_raises():
    """Unexpected update-check errors never break startup flow."""
    with patch(
        "services.core.update_check_service.UpdateCheckService.check_for_updates"
    ) as mock_check:
        mock_check.side_effect = RuntimeError("boom")
        main.run_startup_update_check()


@pytest.mark.parametrize(
    "message",
    [
        None,
        "",
    ],
)
def test_notice_not_shown_without_message_payload(message: str | None):
    """Guard against malformed available results missing message payload."""
    result = UpdateCheckResult(
        local_version="0.8.0",
        latest_version="0.9.0",
        update_available=True,
        message=message,
    )

    with patch(
        "services.core.update_check_service.UpdateCheckService.check_for_updates"
    ) as mock_check:
        with patch.object(_update_cmd.logger, "info") as mock_info:
            mock_check.return_value = result
            main.run_startup_update_check()

    assert mock_info.call_count == 0
