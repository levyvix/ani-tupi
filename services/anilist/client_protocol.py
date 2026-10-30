"""Shared contract and result type for AniList operation mixins."""

from dataclasses import dataclass

from typing import Protocol

from models.models import AniListViewerInfo


@dataclass(frozen=True)
class AiringWatchQueryResult:
    """Result of the monitor's Watching query.

    An empty ``entries`` list with no error is a valid, current empty list.
    ``error_kind`` is set when authentication or the API prevented obtaining
    the current list, so callers never need to interpret an empty list as a
    successful query.
    """

    entries: list[dict]
    error_kind: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_kind is None


class ClientOperationsRequired(Protocol):
    """Protocol defining what the operation mixins need from the host client."""

    user_id: int | None

    def _query(self, query: str, variables: dict | None = None) -> dict | None:
        """Execute GraphQL query."""
        ...

    def is_authenticated(self) -> bool:
        """Check if authenticated."""
        ...

    def get_viewer_info(self) -> AniListViewerInfo | None:
        """Get authenticated user info."""
        ...


__all__ = ["AiringWatchQueryResult", "ClientOperationsRequired"]
