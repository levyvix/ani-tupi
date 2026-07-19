"""Tests for AniListClient._query, _validate_token, authenticate, get_viewer_info.

Covers the uncovered branches in services/anilist/client.py:
- _query: 429 retry/backoff, non-200 with errors, non-200 without errors, GraphQL errors
- _validate_token: ConnectError, TimeoutException, server errors (5xx), valid
- authenticate: ConnectError/Timeout propagation, generic Exception path
- get_viewer_info: success and exception path
"""

import httpx
import pytest

from tests.fixtures.anilist import (
    graphql_response,
    anilist_errors,
    viewer,
)


# ---------------------------------------------------------------------------
# _query – status code and retry branches
# ---------------------------------------------------------------------------


class TestQueryRetry:
    """Rate-limit (429) retry logic in _query."""

    def test_query_retries_on_429_then_succeeds(self, anilist_client, anilist_http, monkeypatch):
        """One 429 followed by a good 200 response succeeds after one retry."""
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda *_: None)

        anilist_http.enqueue(
            graphql_response(status_code=429),
            graphql_response({"Viewer": viewer()}),
        )

        result = anilist_client._query("query { Viewer { id } }")
        assert result == {"Viewer": viewer()}
        assert anilist_http.call_count == 2

    def test_query_raises_after_all_429_retries(self, anilist_client, anilist_http, monkeypatch):
        """Three consecutive 429 responses raises Exception."""
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda *_: None)

        anilist_http.enqueue(
            graphql_response(status_code=429),
            graphql_response(status_code=429),
            graphql_response(status_code=429),
        )

        with pytest.raises(Exception, match="rate limited"):
            anilist_client._query("query { Viewer { id } }")

        assert anilist_http.call_count == 3

    def test_query_sleep_called_with_exponential_backoff(
        self, anilist_client, anilist_http, monkeypatch
    ):
        """sleep is called with 1s then 2s before retries."""
        sleep_calls = []
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda n: sleep_calls.append(n))

        anilist_http.enqueue(
            graphql_response(status_code=429),
            graphql_response(status_code=429),
            graphql_response({"Viewer": viewer()}),
        )

        anilist_client._query("query { Viewer { id } }")

        assert sleep_calls == [1, 2]


class TestQueryNon200:
    """Non-200 (not 429) status code handling."""

    def test_query_raises_on_non_200_with_graphql_errors(
        self, anilist_client, anilist_http, monkeypatch
    ):
        """500 with errors array includes the error message in the exception."""
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda *_: None)
        anilist_http.enqueue(anilist_errors("Not found", status_code=404))

        with pytest.raises(Exception, match="status 404"):
            anilist_client._query("query { Viewer { id } }")

    def test_query_raises_on_non_200_no_errors(self, anilist_client, anilist_http, monkeypatch):
        """500 with no errors array raises generic status message."""
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda *_: None)
        anilist_http.enqueue(graphql_response(status_code=500))

        with pytest.raises(Exception, match="status 500"):
            anilist_client._query("query { Viewer { id } }")

    def test_query_raises_on_graphql_errors_in_200(self, anilist_client, anilist_http, monkeypatch):
        """200 response with GraphQL-level errors field raises Exception."""
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda *_: None)
        anilist_http.enqueue(anilist_errors("Unauthorized"))

        with pytest.raises(Exception, match="GraphQL error"):
            anilist_client._query("query { Viewer { id } }")

    def test_query_sends_authorization_header(self, anilist_client, anilist_http, monkeypatch):
        """When client has a token, Authorization header is attached."""
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda *_: None)
        anilist_http.enqueue(graphql_response({"Viewer": viewer()}))

        anilist_client._query("query { Viewer { id } }")

        call = anilist_http.calls[0]
        assert call["headers"]["Authorization"] == "Bearer test-token"

    def test_query_uses_token_override(self, anilist_client, anilist_http, monkeypatch):
        """Passing token= overrides the client token in the request."""
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda *_: None)
        anilist_http.enqueue(graphql_response({"Viewer": viewer()}))

        anilist_client._query("query { Viewer { id } }", token="override-token")

        call = anilist_http.calls[0]
        assert call["headers"]["Authorization"] == "Bearer override-token"

    def test_query_no_auth_header_when_no_token(self, anilist_client, anilist_http, monkeypatch):
        """When client has no token and no override, no Authorization header is sent."""
        monkeypatch.setattr("services.anilist.client.time.sleep", lambda *_: None)
        anilist_client.token = None
        anilist_http.enqueue(graphql_response({"Viewer": viewer()}))

        anilist_client._query("query { Viewer { id } }")

        call = anilist_http.calls[0]
        assert "Authorization" not in call.get("headers", {})


# ---------------------------------------------------------------------------
# _validate_token – connection / timeout / server errors
# ---------------------------------------------------------------------------


class TestValidateToken:
    def test_validate_raises_connect_error(self, anilist_client, anilist_http):
        """ConnectError is re-raised from _validate_token."""
        anilist_http.enqueue(httpx.ConnectError("refused"))

        with pytest.raises(httpx.ConnectError):
            anilist_client._validate_token("my-token")

    def test_validate_raises_timeout(self, anilist_client, anilist_http):
        """TimeoutException is re-raised from _validate_token."""
        anilist_http.enqueue(httpx.TimeoutException("timed out"))

        with pytest.raises(httpx.TimeoutException):
            anilist_client._validate_token("my-token")

    def test_validate_raises_server_error(self, anilist_client, anilist_http):
        """A 503 wrapped in an Exception message is re-raised."""
        anilist_http.enqueue(graphql_response(status_code=503))

        with pytest.raises(Exception, match="status 503"):
            anilist_client._validate_token("my-token")

    def test_validate_returns_true_on_success(self, anilist_client, anilist_http):
        """Valid viewer response returns True."""
        anilist_http.enqueue(graphql_response({"Viewer": viewer()}))

        result = anilist_client._validate_token("good-token")
        assert result is True

    def test_validate_returns_false_on_generic_exception(
        self, anilist_client, anilist_http, monkeypatch
    ):
        """A non-server, non-network exception returns False without raising."""
        # Enqueue a response that causes a non-5xx GraphQL error
        anilist_http.enqueue(anilist_errors("Invalid token"))

        result = anilist_client._validate_token("bad-token")
        assert result is False


# ---------------------------------------------------------------------------
# authenticate – exception propagation paths
# ---------------------------------------------------------------------------


class TestAuthenticateExceptions:
    def test_authenticate_returns_false_on_connect_error(
        self, anilist_client, anilist_http, monkeypatch
    ):
        """ConnectError during validation causes authenticate to return False."""
        monkeypatch.setattr(
            "services.anilist.client.get_token_from_user",
            lambda *_: "some-token",
        )
        monkeypatch.setattr(
            "services.anilist.client.AniListClient._parse_token",
            lambda self, t: t,
        )
        anilist_http.enqueue(httpx.ConnectError("refused"))

        result = anilist_client.authenticate()
        assert result is False

    def test_authenticate_returns_false_on_timeout(self, anilist_client, anilist_http, monkeypatch):
        """TimeoutException during validation causes authenticate to return False."""
        monkeypatch.setattr(
            "services.anilist.client.get_token_from_user",
            lambda *_: "some-token",
        )
        monkeypatch.setattr(
            "services.anilist.client.AniListClient._parse_token",
            lambda self, t: t,
        )
        anilist_http.enqueue(httpx.TimeoutException("timeout"))

        result = anilist_client.authenticate()
        assert result is False

    def test_authenticate_returns_false_on_generic_exception(
        self, anilist_client, anilist_http, monkeypatch
    ):
        """A server error during validation causes authenticate to return False."""
        monkeypatch.setattr(
            "services.anilist.client.get_token_from_user",
            lambda *_: "some-token",
        )
        monkeypatch.setattr(
            "services.anilist.client.AniListClient._parse_token",
            lambda self, t: t,
        )
        anilist_http.enqueue(graphql_response(status_code=503))

        result = anilist_client.authenticate()
        assert result is False


# ---------------------------------------------------------------------------
# get_viewer_info
# ---------------------------------------------------------------------------


class TestGetViewerInfo:
    def test_get_viewer_info_returns_model(self, anilist_client, anilist_http):
        """Successful query returns AniListViewerInfo model."""
        anilist_http.enqueue(graphql_response({"Viewer": viewer(user_id=42, name="Tester")}))

        info = anilist_client.get_viewer_info()

        assert info is not None
        assert info.id == 42
        assert info.name == "Tester"

    def test_get_viewer_info_returns_none_when_not_authenticated(self, anilist_client):
        """Returns None without hitting API when token is absent."""
        anilist_client.token = None

        info = anilist_client.get_viewer_info()

        assert info is None

    def test_get_viewer_info_returns_none_on_exception(self, anilist_client, anilist_http):
        """Returns None when _query raises."""
        anilist_http.enqueue(anilist_errors("Server error"))

        info = anilist_client.get_viewer_info()

        assert info is None

    def test_get_viewer_info_returns_none_when_viewer_missing(self, anilist_client, anilist_http):
        """Returns None when response has no Viewer key."""
        anilist_http.enqueue(graphql_response({}))

        info = anilist_client.get_viewer_info()

        assert info is None
