"""AniList GraphQL response builders and a fake httpx.post transport.

The AniList client funnels every operation through ``AniListClient._query`` which
calls ``httpx.post``. Tests mock that single external boundary and let the real
client + operation mixins run, matching the "mock only externals" rule.

Usage::

    def test_something(anilist_http):  # fixture from tests/conftest.py
        anilist_http.enqueue(graphql_response({"Viewer": viewer()}))
        ...  # call client methods; they hit the fake transport
        assert anilist_http.calls[0]["json"]["query"]  # inspect the request
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock


def graphql_response(
    data: dict[str, Any] | None = None,
    *,
    errors: list[dict[str, Any]] | None = None,
    status_code: int = 200,
) -> Mock:
    """Build a fake ``httpx.Response`` for a GraphQL call.

    Args:
        data: The ``data`` payload (wrapped as ``{"data": ...}``).
        errors: Optional GraphQL ``errors`` array (present even on 200 responses).
        status_code: HTTP status code to report.
    """
    body: dict[str, Any] = {}
    if data is not None:
        body["data"] = data
    if errors is not None:
        body["errors"] = errors

    response = Mock()
    response.status_code = status_code
    response.json = Mock(return_value=body)
    response.text = str(body)
    return response


def anilist_data(data: dict[str, Any]) -> Mock:
    """Shorthand for a successful 200 response carrying ``data``."""
    return graphql_response(data)


def anilist_errors(message: str = "Boom", *, status_code: int = 200) -> Mock:
    """Build a response carrying a GraphQL error message."""
    return graphql_response(errors=[{"message": message}], status_code=status_code)


def viewer(user_id: int = 42, name: str = "Tester") -> dict[str, Any]:
    """Minimal ``Viewer`` payload with statistics."""
    return {
        "id": user_id,
        "name": name,
        "avatar": {"medium": "m.png", "large": "l.png"},
        "statistics": {"anime": {"count": 3, "episodesWatched": 30, "minutesWatched": 720}},
    }


def media_entry(
    media_id: int = 1,
    *,
    romaji: str = "Test Anime",
    english: str | None = "Test Anime",
    episodes: int | None = 12,
    status: str = "FINISHED",
) -> dict[str, Any]:
    """Minimal ``Media`` payload."""
    return {
        "id": media_id,
        "idMal": media_id + 1000,
        "title": {"romaji": romaji, "english": english, "native": romaji},
        "episodes": episodes,
        "averageScore": 80,
        "seasonYear": 2024,
        "status": status,
    }


def media_list_collection(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap entries into a ``MediaListCollection`` shape (single list group)."""
    return {"MediaListCollection": {"lists": [{"entries": entries}]}}


def save_media_list_entry(entry_id: int = 99, **fields: Any) -> dict[str, Any]:
    """``SaveMediaListEntry`` mutation success payload."""
    payload = {"id": entry_id}
    payload.update(fields)
    return {"SaveMediaListEntry": payload}


class FakeAniListTransport:
    """Callable stand-in for the AniList HTTP boundary.

    The client funnels every GraphQL call through
    ``scrapers.plugins.utils.http_request_with_retry("POST", url, json=..., ...)``
    (retry/status handling lives in that helper). This transport replaces it and
    also tolerates the legacy ``httpx.post(url, ...)`` calling convention.

    Enqueue responses (or exceptions) in the order they will be consumed. Each
    call pops the next queued item; if the queue is empty the ``default``
    response is returned. Every call is recorded in ``self.calls`` with the
    ``method`` and ``url`` plus keyword args (``json``/``headers``/...).
    """

    def __init__(self, default: Mock | None = None) -> None:
        self._queue: list[Any] = []
        self.default = default if default is not None else graphql_response({})
        self.calls: list[dict[str, Any]] = []

    def enqueue(self, *responses: Any) -> "FakeAniListTransport":
        """Queue one or more responses/exceptions for upcoming calls."""
        self._queue.extend(responses)
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Mock:
        # http_request_with_retry(method, url, ...) -> two positionals;
        # legacy httpx.post(url, ...) -> one positional.
        if len(args) >= 2:
            method, url = args[0], args[1]
        elif len(args) == 1:
            method, url = None, args[0]
        else:
            method, url = None, None
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self._queue.pop(0) if self._queue else self.default
        if isinstance(item, BaseException) or (
            isinstance(item, type) and issubclass(item, BaseException)
        ):
            raise item
        return item

    @property
    def call_count(self) -> int:
        return len(self.calls)
