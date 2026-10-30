"""AniList GraphQL transport - client, auth and anime/manga operations.

Handles OAuth flow, token management, GraphQL communication and every
anime/manga operation exposed by ``AniListClient``.

Seções:
- Contrato exigido pelos mixins
- Operações de anime
- Operações de manga
- Cliente GraphQL
"""

import json
from typing import TYPE_CHECKING

import httpx

from models.config import settings
from models.models import (
    AniListTitle,
    AniListViewerInfo,
)
from utils.anilist_titles import (
    format_title as _format_title,
    get_search_title as _get_search_title,
)
from utils.headless_detector import get_token_from_user
from services.anilist import client_auth, client_transport
from utils.logging import get_logger
from services.anilist.client_protocol import AiringWatchQueryResult
from services.anilist.anime_operations import AnimeOperationsMixin
from services.anilist.manga_operations import MangaOperationsMixin

__all__ = [
    "AniListClient",
    "AiringWatchQueryResult",
    "AnimeOperationsMixin",
    "MangaOperationsMixin",
    "anilist_client",
    "get_anilist_client",
]

if TYPE_CHECKING:
    # ``anilist_client`` is served lazily by ``__getattr__`` at the bottom of
    # this module; declaring it here keeps the public surface statically visible.
    anilist_client: "AniListClient"

logger = get_logger(__name__)


# === Cliente GraphQL ===


class AniListClient(AnimeOperationsMixin, MangaOperationsMixin):
    """Core AniList API client with authentication and query execution."""

    def __init__(self) -> None:
        """Initialize the AniList client."""
        self.user_id = None  # Will be set after authentication or loaded from file
        self.token = self._load_token()
        self.api_url = settings.anilist.api_url  # Expose API URL for testing

    def _load_token(self) -> str | None:
        return client_auth.load_token(self, settings_obj=settings, json_module=json)

    def _save_token(self, token: str, user_id: int | None = None) -> None:
        client_auth.save_token(self, token, user_id, settings_obj=settings, json_module=json)

    def is_authenticated(self) -> bool:
        """Check if user has valid token."""
        return self.token is not None

    def authenticate(self, max_retries: int = 3) -> bool:
        return client_auth.authenticate(
            self,
            max_retries,
            settings_obj=settings,
            token_provider=get_token_from_user,
            httpx_module=httpx,
            log=logger,
        )

    def _parse_token(self, token_input: str) -> str:
        return client_auth.parse_token(token_input)

    def _validate_token(self, token: str) -> bool:
        return client_auth.validate_token(self, token, httpx_module=httpx, log=logger)

    def _query(self, query: str, variables: dict | None = None, token: str | None = None) -> dict:
        return client_transport.execute_query(
            self,
            query,
            variables,
            token,
            settings_obj=settings,
            httpx_module=httpx,
            json_module=json,
            log=logger,
        )

    def get_viewer_info(self) -> AniListViewerInfo | None:
        return client_transport.get_viewer_info(self)

    def format_title(self, title_obj: AniListTitle | dict) -> str:
        """Format title object to single string. Delegates to formatters module."""
        return _format_title(title_obj)

    def get_search_title(self, title_obj: AniListTitle | dict) -> str:
        """Extract title for scraper search (English only). Delegates to formatters module."""
        return _get_search_title(title_obj)


# === Instância compartilhada ===

_client: AniListClient | None = None


def get_anilist_client() -> AniListClient:
    """Return the shared AniList client, constructing it on first use."""
    global _client
    if _client is None:
        _client = AniListClient()
    return _client


def __getattr__(name: str):
    """Expose ``anilist_client`` lazily (PEP 562).

    Importing this module no longer reads the token file as a side effect; the
    client is only built when something actually touches ``anilist_client``.
    """
    if name == "anilist_client":
        return get_anilist_client()
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
