"""Tests for startup update-check service behavior."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

from models.config import UpdateCheckSettings
from services.core.update_check_service import UpdateCheckService


def _service(settings: UpdateCheckSettings, state_path, local_version: str = "0.8.0"):
    return UpdateCheckService(
        update_settings=settings,
        state_path=state_path,
        local_version=local_version,
    )


def test_update_available_builds_notice(temp_dir):
    """Returns update notice when remote version is newer."""
    settings = UpdateCheckSettings(
        enabled=True,
        interval_hours=24,
        request_timeout_seconds=1.5,
        release_source_url="https://pypi.org/pypi/ani-tupi/json",
        update_command="uv tool upgrade ani-tupi",
    )
    service = _service(settings, temp_dir / "update_check_state.json", local_version="0.8.0")

    payload = {"info": {"version": "0.9.0"}}

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.return_value = Mock(json=lambda: payload)

        result = service.check_for_updates()

    assert result.local_version == "0.8.0"
    assert result.latest_version == "0.9.0"
    assert result.update_available is True
    assert result.message == (
        "⬆️  Nova versão disponível: 0.8.0 -> 0.9.0. Atualize com: uv tool upgrade ani-tupi"
    )


def test_current_version_returns_no_notice(temp_dir):
    """No message is shown when local version is current."""
    settings = UpdateCheckSettings(enabled=True, interval_hours=24)
    service = _service(settings, temp_dir / "update_check_state.json", local_version="0.8.0")

    payload = {"info": {"version": "0.8.0"}}

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.return_value = Mock(json=lambda: payload)

        result = service.check_for_updates()

    assert result.latest_version == "0.8.0"
    assert result.update_available is False
    assert result.message is None


def test_invalid_payload_returns_fail_safe_result(temp_dir):
    """Invalid payload should not crash and should not show notice."""
    settings = UpdateCheckSettings(enabled=True, interval_hours=24)
    service = _service(settings, temp_dir / "update_check_state.json")

    payload = {"unexpected": "shape"}

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.return_value = Mock(json=lambda: payload)

        result = service.check_for_updates()

    assert result.update_available is False
    assert result.latest_version is None
    assert result.message is None


def test_timeout_and_network_failures_are_silent(temp_dir):
    """Fetch errors (e.g. bad JSON from a network failure) return no-notice result."""
    settings = UpdateCheckSettings(enabled=True, interval_hours=24)
    service = _service(settings, temp_dir / "update_check_state.json")

    # _fetch_latest_version catches (ValueError, TypeError); simulate a fetch
    # that produces unparseable content (as happens after a timeout/retry cycle).
    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.side_effect = ValueError("network failure")
        timeout_result = service.check_for_updates()

    assert timeout_result.update_available is False
    assert timeout_result.latest_version is None
    assert timeout_result.message is None

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.side_effect = TypeError("bad response type")
        network_result = service.check_for_updates()

    assert network_result.update_available is False
    assert network_result.latest_version is None
    assert network_result.message is None


def test_uses_cached_result_before_interval_elapses(temp_dir):
    """Service reuses persisted latest version before interval expires."""
    settings = UpdateCheckSettings(enabled=True, interval_hours=24)
    state_path = temp_dir / "update_check_state.json"
    service = _service(settings, state_path, local_version="0.8.0")

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.return_value = Mock(json=lambda: {"info": {"version": "1.0.0"}})

        first = service.check_for_updates()

    assert first.update_available is True

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.return_value = Mock(json=lambda: {"info": {"version": "9.9.9"}})

        second = service.check_for_updates()

    assert mock_get.call_count == 0
    assert second.latest_version == "1.0.0"
    assert second.update_available is True


def test_cache_expires_after_interval(temp_dir):
    """Service performs a new request after interval expires."""
    settings = UpdateCheckSettings(enabled=True, interval_hours=1)
    state_path = temp_dir / "update_check_state.json"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        """
{
  "last_checked_at": "2000-01-01T00:00:00+00:00",
  "last_latest_version": "0.8.1",
  "last_update_available": true
}
""".strip()
    )

    service = _service(settings, state_path, local_version="0.8.0")

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.return_value = Mock(json=lambda: {"info": {"version": "0.9.0"}})

        result = service.check_for_updates()

    assert mock_get.call_count == 1
    assert result.latest_version == "0.9.0"
    assert result.update_available is True


def test_disabled_update_check_skips_network(temp_dir):
    """Disabled setting must avoid remote call entirely."""
    settings = UpdateCheckSettings(enabled=False)
    service = _service(settings, temp_dir / "update_check_state.json")

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        result = service.check_for_updates()

    assert mock_get.call_count == 0
    assert result.update_available is False
    assert result.latest_version is None


def test_state_saved_with_successful_check(temp_dir):
    """Successful checks persist timestamp and latest version for cooldown."""
    settings = UpdateCheckSettings(enabled=True, interval_hours=24)
    state_path = temp_dir / "update_check_state.json"
    service = _service(settings, state_path, local_version="0.8.0")

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        mock_get.return_value = Mock(json=lambda: {"info": {"version": "0.9.0"}})
        service.check_for_updates()

    raw_state = state_path.read_text()
    assert "0.9.0" in raw_state


def test_cached_state_with_naive_timestamp_is_supported(temp_dir):
    """Naive datetimes in cache should be treated as UTC and remain valid."""
    settings = UpdateCheckSettings(enabled=True, interval_hours=24)
    state_path = temp_dir / "update_check_state.json"
    service = _service(settings, state_path, local_version="0.8.0")

    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "")
    state_path.write_text(
        (
            "{"
            f'"last_checked_at":"{now}",'
            '"last_latest_version":"0.8.1",'
            '"last_update_available":true'
            "}"
        )
    )

    with patch("services.core.update_check_service.http_get_with_retry") as mock_get:
        result = service.check_for_updates()

    assert mock_get.call_count == 0
    assert result.latest_version == "0.8.1"
    assert result.update_available is True
