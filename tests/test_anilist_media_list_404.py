"""Tests for AniList returning HTTP 404 with a valid GraphQL body.

AniList answers MediaList queries for an anime that is not in the user's list
with status 404 while still returning ``{"errors": [...], "data": {...null}}``.
That must be read as "no entry", not as a fatal HTTP failure.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from services.anilist.client import AniListClient

API_URL = "https://graphql.anilist.co"


def _response(status: int, *, json_body=None, text: str | None = None) -> httpx.Response:
    """Build a real httpx.Response so raise_for_status behaves genuinely."""
    request = httpx.Request("POST", API_URL)
    if text is not None:
        return httpx.Response(status, text=text, request=request)
    return httpx.Response(status, json=json_body, request=request)


@pytest.fixture
def anilist_client(monkeypatch):
    """Authenticated client pointed at a temporary token file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(
            "services.anilist.client.settings.anilist.token_file",
            Path(tmpdir) / "anilist_token.json",
        )
        monkeypatch.setattr("services.anilist.client.settings.anilist.api_url", API_URL)
        client = AniListClient()
        client.token = "test_token"
        client.user_id = 5555
        yield client


class TestMediaListNotFound:
    """The reported crash: watching an anime absent from the user's list."""

    def test_get_media_list_entry_returns_none_when_not_in_list(self, anilist_client):
        """404 + 'Not Found' body means no entry, not a crash."""
        body = {
            "errors": [{"message": "Not Found", "status": 404}],
            "data": {"MediaList": None},
        }
        with patch("httpx.request", return_value=_response(404, json_body=body)) as mock_request:
            assert anilist_client.get_media_list_entry(98478) is None

        # Guards against a vacuous pass: None must come from the 404 handling,
        # not from an early return before any HTTP call.
        assert mock_request.called

    def test_get_media_list_entry_returns_none_for_private_user(self, anilist_client):
        """AniList uses the same 404 shape for a private profile."""
        body = {
            "errors": [{"message": "Private User", "status": 404}],
            "data": {"MediaList": None},
        }
        with patch("httpx.request", return_value=_response(404, json_body=body)):
            assert anilist_client.get_media_list_entry(98478) is None

    def test_get_media_list_entry_still_parses_existing_entry(self, anilist_client):
        """Regression: a normal 200 response is unaffected."""
        body = {
            "data": {
                "MediaList": {
                    "id": 1,
                    "status": "CURRENT",
                    "progress": 7,
                    "score": 85,
                    "startedAt": {"year": 2024, "month": 1, "day": 5},
                    "completedAt": None,
                }
            }
        }
        with patch("httpx.request", return_value=_response(200, json_body=body)):
            entry = anilist_client.get_media_list_entry(98478)

        assert entry is not None
        assert entry.progress == 7

    def test_progress_survives_entry_without_dates(self, anilist_client):
        """AniList sends FuzzyDate with null year/month/day when unset.

        Those nulls must not fail validation, otherwise the entry is silently
        dropped and the user restarts the anime from episode 0.
        """
        body = {
            "data": {
                "MediaList": {
                    "id": 1,
                    "status": "CURRENT",
                    "progress": 7,
                    "score": 85,
                    "startedAt": {"year": None, "month": None, "day": None},
                    "completedAt": {"year": None, "month": None, "day": None},
                }
            }
        }
        with patch("httpx.request", return_value=_response(200, json_body=body)):
            entry = anilist_client.get_media_list_entry(98478)

        assert entry is not None
        assert entry.progress == 7


class TestQuery404Handling:
    """_query treats a 404 GraphQL body as data, but nothing else."""

    def test_returns_data_on_404_with_graphql_body(self, anilist_client):
        body = {"errors": [{"message": "Not Found"}], "data": {"MediaList": None}}
        with patch("httpx.request", return_value=_response(404, json_body=body)):
            assert anilist_client._query("query {}") == {"MediaList": None}

    def test_raises_on_404_without_data_key(self, anilist_client):
        """A 404 carrying only errors is a real failure."""
        body = {"errors": [{"message": "Not Found"}]}
        with patch("httpx.request", return_value=_response(404, json_body=body)):
            with pytest.raises(Exception, match="GraphQL error"):
                anilist_client._query("query {}")

    def test_propagates_http_error_on_404_with_non_json_body(self, anilist_client):
        """A proxy/captive-portal 404 keeps the informative HTTP error."""
        with patch("httpx.request", return_value=_response(404, text="<html>nope</html>")):
            with pytest.raises(httpx.HTTPStatusError):
                anilist_client._query("query {}")

    def test_other_client_errors_still_raise(self, anilist_client):
        """400 is not swallowed by the 404 handling."""
        with patch("httpx.request", return_value=_response(400, json_body={"errors": []})):
            with pytest.raises(httpx.HTTPStatusError):
                anilist_client._query("query {}")

    def test_graphql_errors_on_200_still_raise(self, anilist_client):
        """Regression: errors on a successful status remain fatal."""
        body = {"errors": [{"message": "Invalid token"}]}
        with patch("httpx.request", return_value=_response(200, json_body=body)):
            with pytest.raises(Exception, match="GraphQL error"):
                anilist_client._query("query {}")
