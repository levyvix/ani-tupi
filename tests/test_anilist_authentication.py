"""Tests for AniList authentication (headless mode)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from services.anilist.client import AniListClient


@pytest.fixture
def temp_token_file():
    """Create temporary token file location."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "anilist_token.json"


@pytest.fixture
def anilist_client(temp_token_file, monkeypatch):
    """Create AniListClient with temporary token file."""
    monkeypatch.setattr(
        "services.anilist.client.settings.anilist.token_file",
        temp_token_file,
    )
    monkeypatch.setattr(
        "services.anilist.client.settings.anilist.api_url",
        "https://graphql.anilist.co",
    )
    monkeypatch.setattr(
        "services.anilist.client.settings.anilist.auth_url",
        "https://anilist.co/api/v2/oauth/authorize",
    )
    monkeypatch.setattr(
        "services.anilist.client.settings.anilist.client_id",
        "test_client_id",
    )
    return AniListClient()


class TestTokenParsing:
    """Test token parsing from various input formats."""

    def test_parse_raw_token(self, anilist_client):
        """Parse raw token string."""
        token = "raw_token_abc123"
        parsed = anilist_client._parse_token(token)
        assert parsed == "raw_token_abc123"

    def test_parse_token_with_fragment(self, anilist_client):
        """Parse token from URL with fragment."""
        url = "https://anilist.co/api/v2/oauth/pin#access_token=abc123xyz&token_type=Bearer"
        parsed = anilist_client._parse_token(url)
        assert parsed == "abc123xyz"

    def test_parse_token_with_access_token_prefix(self, anilist_client):
        """Parse token with access_token= prefix."""
        token_input = "access_token=abc123xyz&token_type=Bearer"
        parsed = anilist_client._parse_token(token_input)
        assert parsed == "abc123xyz"

    def test_parse_token_url_encoded(self, anilist_client):
        """Parse URL-encoded token."""
        token_input = "%23access_token=abc123xyz&token_type=Bearer"
        parsed = anilist_client._parse_token(token_input)
        assert parsed == "abc123xyz"

    def test_parse_token_with_whitespace(self, anilist_client):
        """Parse token with surrounding whitespace."""
        token = "  raw_token_abc123  "
        parsed = anilist_client._parse_token(token)
        assert parsed == "raw_token_abc123"

    def test_parse_empty_token(self, anilist_client):
        """Parse empty token returns empty string."""
        parsed = anilist_client._parse_token("")
        assert parsed == ""


class TestTokenValidation:
    """Test token validation."""

    def test_validate_token_success(self, anilist_client):
        """Validate token successfully."""
        with patch.object(anilist_client, "_query") as mock_query:
            mock_query.return_value = {"Viewer": {"id": 12345, "name": "TestUser"}}
            result = anilist_client._validate_token("valid_token")
            assert result is True
            mock_query.assert_called_once()

    def test_validate_token_failure_no_viewer(self, anilist_client):
        """Validation fails when Viewer not in response."""
        with patch.object(anilist_client, "_query") as mock_query:
            mock_query.return_value = {"data": {}}
            result = anilist_client._validate_token("invalid_token")
            assert result is False

    def test_validate_token_failure_exception(self, anilist_client):
        """Validation fails on exception."""
        with patch.object(anilist_client, "_query") as mock_query:
            mock_query.side_effect = Exception("Network error")
            result = anilist_client._validate_token("bad_token")
            assert result is False

    def test_validate_token_failure_none_response(self, anilist_client):
        """Validation fails when response is None."""
        with patch.object(anilist_client, "_query") as mock_query:
            mock_query.return_value = None
            result = anilist_client._validate_token("bad_token")
            assert result is False


class TestHeadlessAuthentication:
    """Test headless authentication flow."""

    def test_authenticate_success(self, anilist_client, temp_token_file):
        """Successful authentication saves token."""
        with patch("utils.headless_detector.getpass.getpass") as mock_getpass:
            with patch.object(anilist_client, "_validate_token") as mock_validate:
                with patch.object(anilist_client, "get_viewer_info") as mock_viewer:
                    mock_getpass.return_value = "access_token=valid_token&other=data"
                    mock_validate.return_value = True
                    mock_viewer.return_value = Mock(id=12345, name="TestUser")

                    result = anilist_client.authenticate()

                    assert result is True
                    assert anilist_client.token == "valid_token"
                    assert temp_token_file.exists()

    def test_authenticate_saves_token_to_file(self, anilist_client, temp_token_file):
        """Token is saved to file after authentication."""
        with patch("utils.headless_detector.getpass.getpass") as mock_getpass:
            with patch.object(anilist_client, "_validate_token") as mock_validate:
                with patch.object(anilist_client, "get_viewer_info") as mock_viewer:
                    mock_getpass.return_value = "valid_token"
                    mock_validate.return_value = True
                    mock_viewer.return_value = Mock(id=12345, name="TestUser")

                    anilist_client.authenticate()

                    # Verify token file was created
                    assert temp_token_file.exists()
                    with temp_token_file.open() as f:
                        data = json.load(f)
                        assert data["access_token"] == "valid_token"
                        assert data["user_id"] == "12345"

    def test_authenticate_malformed_token_retry(self, anilist_client):
        """Authentication retries on malformed token (fails parsing but not empty)."""
        with patch("utils.headless_detector.getpass.getpass") as mock_getpass:
            # First call: malformed token, second call: valid token
            mock_getpass.side_effect = ["xyz", "valid_token"]
            with patch.object(anilist_client, "_validate_token") as mock_validate:
                with patch.object(anilist_client, "get_viewer_info") as mock_viewer:
                    # xyz is empty after parsing, so it should retry
                    with patch.object(anilist_client, "_parse_token") as mock_parse:
                        mock_parse.side_effect = ["", "valid_token"]
                        mock_validate.return_value = True
                        mock_viewer.return_value = Mock(id=12345, name="TestUser")

                        result = anilist_client.authenticate()

                        assert result is True
                        assert mock_getpass.call_count == 2

    def test_authenticate_validation_failure_retry(self, anilist_client):
        """Authentication retries on validation failure."""
        with patch("utils.headless_detector.getpass.getpass") as mock_getpass:
            # First call: invalid token, second call: valid token
            mock_getpass.side_effect = ["invalid_token", "valid_token"]
            with patch.object(anilist_client, "_validate_token") as mock_validate:
                with patch.object(anilist_client, "get_viewer_info") as mock_viewer:
                    # First call fails, second succeeds
                    mock_validate.side_effect = [False, True]
                    mock_viewer.return_value = Mock(id=12345, name="TestUser")

                    result = anilist_client.authenticate()

                    assert result is True
                    assert mock_getpass.call_count == 2

    def test_authenticate_max_retries_exceeded(self, anilist_client):
        """Authentication fails after max retries."""
        with patch("utils.headless_detector.getpass.getpass") as mock_getpass:
            mock_getpass.return_value = "invalid_token"
            with patch.object(anilist_client, "_validate_token") as mock_validate:
                mock_validate.return_value = False

                result = anilist_client.authenticate(max_retries=3)

                assert result is False
                # Called 3 times (max_retries)
                assert mock_getpass.call_count == 3

    def test_authenticate_user_cancels(self, anilist_client):
        """Authentication fails when user cancels."""
        with patch("utils.headless_detector.getpass.getpass") as mock_getpass:
            mock_getpass.return_value = ""

            result = anilist_client.authenticate()

            assert result is False

    def test_authenticate_custom_max_retries(self, anilist_client):
        """Authenticate respects custom max_retries parameter."""
        with patch("utils.headless_detector.getpass.getpass") as mock_getpass:
            mock_getpass.return_value = "invalid"
            with patch.object(anilist_client, "_validate_token") as mock_validate:
                mock_validate.return_value = False

                result = anilist_client.authenticate(max_retries=5)

                assert result is False
                assert mock_getpass.call_count == 5

    def test_authenticate_no_viewer_info(self, anilist_client):
        """Authentication succeeds even if viewer info fetch fails."""
        with patch("utils.headless_detector.getpass.getpass") as mock_getpass:
            with patch.object(anilist_client, "_validate_token") as mock_validate:
                with patch.object(anilist_client, "get_viewer_info") as mock_viewer:
                    mock_getpass.return_value = "valid_token"
                    mock_validate.return_value = True
                    mock_viewer.return_value = None

                    result = anilist_client.authenticate()

                    # Should succeed but not save user_id
                    assert result is True
                    assert anilist_client.token == "valid_token"


class TestTokenStorage:
    """Test token storage and loading."""

    def test_load_token_from_file(self, anilist_client, temp_token_file):
        """Load token from existing file."""
        # Create token file
        temp_token_file.parent.mkdir(parents=True, exist_ok=True)
        with temp_token_file.open("w") as f:
            json.dump({"access_token": "saved_token", "user_id": "12345"}, f)

        # Create new client to load token
        client = AniListClient()
        assert client.token == "saved_token"
        assert client.user_id == 12345

    def test_load_token_file_missing(self, anilist_client, temp_token_file):
        """Load token returns None when file doesn't exist."""
        assert temp_token_file.exists() is False
        loaded = anilist_client._load_token()
        assert loaded is None

    def test_load_token_invalid_json(self, anilist_client, temp_token_file):
        """Load token handles invalid JSON gracefully."""
        temp_token_file.parent.mkdir(parents=True, exist_ok=True)
        with temp_token_file.open("w") as f:
            f.write("invalid json")

        loaded = anilist_client._load_token()
        assert loaded is None

    def test_save_token_with_user_id(self, anilist_client, temp_token_file):
        """Save token stores both token and user_id."""
        anilist_client._save_token("test_token", user_id=123)
        assert temp_token_file.exists()

        with temp_token_file.open() as f:
            data = json.load(f)
            assert data["access_token"] == "test_token"
            assert data["user_id"] == "123"

    def test_is_authenticated_with_token(self, anilist_client):
        """is_authenticated returns True when token exists."""
        anilist_client.token = "valid_token"
        assert anilist_client.is_authenticated() is True

    def test_is_authenticated_without_token(self, anilist_client):
        """is_authenticated returns False when no token."""
        anilist_client.token = None
        assert anilist_client.is_authenticated() is False
