"""AniList API client - complete GraphQL client with anime and manga operations.

Handles OAuth flow, token management, base GraphQL communication,
and all anime/manga operations via mixins.
"""

import json
import time

import requests

from models.config import settings
from models.models import AniListViewerInfo, AniListTitle
from services.anilist.formatters import (
    format_title as _format_title,
    get_search_title as _get_search_title,
)
from services.anilist.anime_operations import AnimeOperationsMixin
from services.anilist.manga_operations import MangaOperationsMixin
from utils.headless_detector import get_token_from_user
from utils.logging import get_logger
from typing import Optional

logger = get_logger(__name__)


class AniListClient(AnimeOperationsMixin, MangaOperationsMixin):
    """Core AniList API client with authentication and query execution."""

    def __init__(self) -> None:
        """Initialize the AniList client."""
        self.user_id = None  # Will be set after authentication or loaded from file
        self.token = self._load_token()
        self.api_url = settings.anilist.api_url  # Expose API URL for testing

    def _load_token(self) -> str | None:
        """Load access token and user_id from file."""
        token_file = settings.anilist.token_file
        if not token_file.exists():
            return None
        try:
            with token_file.open() as f:
                data = json.load(f)
                raw_user_id = data.get("user_id")
                self.user_id = int(raw_user_id) if raw_user_id else None  # Load user_id if exists
                return data.get("access_token")
        except Exception:
            return None

    def _save_token(self, token: str, user_id: Optional[int] = None) -> None:
        """Save access token and user_id to file."""
        token_file = settings.anilist.token_file
        token_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"access_token": token}
        if user_id:
            data["user_id"] = str(user_id)
        with token_file.open("w") as f:
            json.dump(data, f)

    def is_authenticated(self) -> bool:
        """Check if user has valid token."""
        return self.token is not None

    def authenticate(self, max_retries: int = 3) -> bool:
        """OAuth authentication flow (headless mode).

        Displays authorization URL and waits for token input via stdin.
        Supports token pasted from URL fragment or raw token string.

        Args:
            max_retries: Maximum number of token input attempts

        Returns:
            True if authentication successful, False otherwise
        """
        # Build OAuth URL
        auth_url = f"{settings.anilist.auth_url}?client_id={settings.anilist.client_id}&response_type=token"

        # Try to get token from user (up to max_retries times)
        for attempt in range(max_retries):
            token_input = get_token_from_user(auth_url)

            if not token_input:
                # User cancelled
                return False

            # Parse token from URL if needed
            token = self._parse_token(token_input)

            if not token:
                remaining = max_retries - attempt - 1
                if remaining > 0:
                    logger.info(
                        f"\n❌ Invalid token format. Please try again ({remaining} attempts left).\n"
                    )
                continue

            # Validate token
            try:
                valid = self._validate_token(token)
            except Exception as e:
                logger.info(f"\n❌ Token validation failed: {e}\n")
                return False

            if valid:
                self.token = token

                # Get and display user info
                user_info = self.get_viewer_info()
                if user_info:
                    self.user_id = user_info.id  # Save user ID for queries
                    self._save_token(token, self.user_id)  # Save both token and user_id
                    logger.info(f"\n✅ Authentication successful! Welcome, {user_info.name}!")
                return True

            # Token validation failed
            remaining = max_retries - attempt - 1
            if remaining > 0:
                logger.info(
                    f"\n❌ Token validation failed. Please check the token and try again ({remaining} attempts left).\n"
                )

        logger.info("\n❌ Authentication failed after maximum retry attempts.")
        return False

    def _parse_token(self, token_input: str) -> str:
        """Parse token from user input.

        Handles: raw token, URL with fragment, or access_token= prefix.
        """
        token = token_input.strip()

        # If user pasted full URL with fragment
        if "#access_token=" in token:
            token = token.split("#access_token=")[1].split("&")[0]
        # If user pasted just the fragment part
        elif "access_token=" in token:
            token = token.split("access_token=")[1].split("&")[0]
        # If user pasted URL-encoded version
        elif "%23access_token=" in token:
            token = token.split("%23access_token=")[1].split("&")[0]

        return token.strip()

    def _validate_token(self, token: str) -> bool:
        """Validate token by fetching viewer info."""
        query = """
        query {
            Viewer {
                id
                name
            }
        }
        """
        try:
            result = self._query(query, token=token)
            return result is not None and "Viewer" in result
        except Exception as e:
            logger.debug(f"Token validation error: {e}")
            return False

    def _query(
        self, query: str, variables: Optional[dict] = None, token: Optional[str] = None
    ) -> dict:
        """Execute GraphQL query with retry on rate limit (429).

        Args:
            query: GraphQL query string
            variables: Query variables
            token: Optional token override (for validation)

        Returns:
            Query result data

        """
        headers = {}
        use_token = token if token else self.token

        if use_token:
            headers["Authorization"] = f"Bearer {use_token}"

        max_retries = 3
        base_wait = 1

        for attempt in range(max_retries):
            response = requests.post(
                settings.anilist.api_url,
                json={"query": query, "variables": variables or {}},
                headers=headers,
            )

            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = base_wait * (2**attempt)
                    time.sleep(wait_time)
                    continue
                msg = f"Query failed with status {response.status_code} (rate limited)"
                raise Exception(msg)

            if response.status_code != 200:
                try:
                    error_data = response.json()
                    errors = error_data.get("errors", [])
                    if errors:
                        error_msg = errors[0].get("message", "Unknown error")
                        msg = f"Query failed with status {response.status_code}: {error_msg}"
                    else:
                        msg = f"Query failed with status {response.status_code}"
                except Exception:
                    msg = f"Query failed with status {response.status_code}"
                raise Exception(msg)

            result = response.json()

            if "errors" in result:
                msg = f"GraphQL error: {result['errors']}"
                raise Exception(msg)

            return result.get("data")

        # Should not reach here, but included for safety
        raise Exception("Query failed after all retries")

    def get_viewer_info(self) -> AniListViewerInfo | None:
        """Get authenticated user info with statistics."""
        if not self.is_authenticated():
            return None

        query = """
        query {
            Viewer {
                id
                name
                avatar {
                    medium
                    large
                }
                statistics {
                    anime {
                        count
                        episodesWatched
                        minutesWatched
                    }
                }
            }
        }
        """

        try:
            result = self._query(query)
            viewer_data = result.get("Viewer") if result else None
            if viewer_data:
                return AniListViewerInfo.model_validate(viewer_data)
            return None
        except Exception:
            return None

    def format_title(self, title_obj: AniListTitle | dict) -> str:
        """Format title object to single string. Delegates to formatters module."""
        return _format_title(title_obj)

    def get_search_title(self, title_obj: AniListTitle | dict) -> str:
        """Extract title for scraper search (English only). Delegates to formatters module."""
        return _get_search_title(title_obj)
