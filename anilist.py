"""AniList API integration for ani-tupi.

GraphQL client for tracking anime progress and fetching lists.
"""

import json
import webbrowser
from pathlib import Path

import requests

# AniList API endpoints
ANILIST_API_URL = "https://graphql.anilist.co"
ANILIST_AUTH_URL = "https://anilist.co/api/v2/oauth/authorize"
ANILIST_TOKEN_URL = "https://anilist.co/api/v2/oauth/token"

# OAuth Config (using implicit grant - no client secret needed)
CLIENT_ID = 20148  # Public client ID (same as viu-media/viu)

# Token storage
TOKEN_FILE = Path.home() / ".local/state/ani-tupi/anilist_token.json"


class AniListClient:
    """GraphQL client for AniList API."""

    def __init__(self) -> None:
        """Initialize the AniList client."""
        self.token = self._load_token()
        self.user_id = None  # Will be set after authentication

    def _load_token(self) -> str | None:
        """Load access token and user_id from file."""
        if not TOKEN_FILE.exists():
            return None
        try:
            with TOKEN_FILE.open() as f:
                data = json.load(f)
                self.user_id = data.get("user_id")  # Load user_id if exists
                return data.get("access_token")
        except Exception:
            return None

    def _save_token(self, token: str, user_id: int | None = None) -> None:
        """Save access token and user_id to file."""
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"access_token": token}
        if user_id:
            data["user_id"] = user_id
        with TOKEN_FILE.open("w") as f:
            json.dump(data, f)

    def is_authenticated(self) -> bool:
        """Check if user has valid token."""
        return self.token is not None

    def authenticate(self) -> bool:
        """OAuth authentication flow (same method as viu-media/viu).

        Opens browser for authorization, user copies token from URL.
        """
        # Build OAuth URL
        auth_url = f"{ANILIST_AUTH_URL}?client_id={CLIENT_ID}&response_type=token"


        # Open browser
        webbrowser.open(auth_url, new=2)


        # Get token from user
        token_input = input("\nCole o token aqui: ").strip()

        # Parse token from URL if needed (same as viu does)
        token = self._parse_token(token_input)

        if not token:
            return False

        # Validate token
        if self._validate_token(token):
            self.token = token

            # Get and display user info
            user_info = self.get_viewer_info()
            if user_info:
                self.user_id = user_info["id"]  # Save user ID for queries
                self._save_token(token, self.user_id)  # Save both token and user_id
            return True
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
        except Exception:
            return False

    def _query(self, query: str, variables: dict | None = None, token: str | None = None) -> dict:
        """Execute GraphQL query.

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

        response = requests.post(
            ANILIST_API_URL,
            json={"query": query, "variables": variables or {}},
            headers=headers,
        )

        if response.status_code != 200:
            msg = f"Query failed with status {response.status_code}"
            raise Exception(msg)

        result = response.json()

        if "errors" in result:
            msg = f"GraphQL error: {result['errors']}"
            raise Exception(msg)

        return result.get("data")

    def get_viewer_info(self) -> dict | None:
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
            return result.get("Viewer") if result else None
        except Exception:
            return None

    def get_trending(
        self,
        page: int = 1,
        per_page: int = 20,
        year: int | None = None,
        season: str | None = None,
    ) -> list[dict]:
        """Get trending anime with optional filters.

        Args:
            page: Page number
            per_page: Items per page
            year: Filter by year (None = all years)
            season: Filter by season (WINTER, SPRING, SUMMER, FALL, or None = all seasons)

        Returns list of anime with: id, title, episodes, coverImage
        """
        query = """
        query ($page: Int, $perPage: Int, $seasonYear: Int, $season: MediaSeason) {
            Page(page: $page, perPage: $perPage) {
                media(type: ANIME, sort: TRENDING_DESC, seasonYear: $seasonYear, season: $season) {
                    id
                    title {
                        romaji
                        english
                        native
                    }
                    episodes
                    coverImage {
                        medium
                    }
                    averageScore
                    seasonYear
                    season
                }
            }
        }
        """

        variables = {"page": page, "perPage": per_page}
        if year:
            variables["seasonYear"] = year
        if season:
            variables["season"] = season

        try:
            result = self._query(query, variables)
            return result["Page"]["media"] if result else []
        except Exception:
            return []

    def get_user_list(self, status: str, page: int = 1, per_page: int = 50) -> list[dict]:
        """Get authenticated user's anime list by status.

        Args:
            status: CURRENT, PLANNING, COMPLETED, DROPPED, PAUSED, REPEATING
            page: Page number
            per_page: Items per page

        Returns list with: anime data + progress

        """
        if not self.is_authenticated():
            return []

        # Ensure we have user_id
        if not self.user_id:
            user_info = self.get_viewer_info()
            if user_info:
                self.user_id = user_info["id"]
            else:
                return []

        # Use MediaListCollection with explicit userId
        query = """
        query ($userId: Int, $status: MediaListStatus) {
            MediaListCollection(userId: $userId, type: ANIME, status: $status) {
                lists {
                    entries {
                        id
                        progress
                        createdAt
                        media {
                            id
                            title {
                                romaji
                                english
                                native
                            }
                            episodes
                            coverImage {
                                medium
                            }
                            averageScore
                            seasonYear
                        }
                    }
                }
            }
        }
        """

        variables = {"userId": self.user_id, "status": status}

        try:
            result = self._query(query, variables)
            if result and "MediaListCollection" in result:
                # Flatten the lists structure
                entries = []
                for list_group in result["MediaListCollection"]["lists"]:
                    entries.extend(list_group["entries"])

                # Sort by createdAt descending (most recent first)
                entries.sort(key=lambda x: x.get("createdAt", 0), reverse=True)

                return entries
            return []
        except Exception:
            return []

    def update_progress(self, anime_id: int, episode: int) -> bool:
        """Update anime progress.

        Args:
            anime_id: AniList anime ID
            episode: Episode number (1-indexed)

        Returns:
            True if successful

        """
        if not self.is_authenticated():
            return False

        query = """
        mutation ($mediaId: Int, $progress: Int) {
            SaveMediaListEntry(mediaId: $mediaId, progress: $progress) {
                id
                progress
            }
        }
        """

        variables = {"mediaId": anime_id, "progress": episode}

        try:
            self._query(query, variables)
            return True
        except Exception:
            return False

    def search_anime(self, query_text: str) -> list[dict]:
        """Search anime by title.

        Returns list of anime matching query
        """
        query = """
        query ($search: String) {
            Page(perPage: 10) {
                media(type: ANIME, search: $search) {
                    id
                    title {
                        romaji
                        english
                        native
                    }
                    episodes
                    coverImage {
                        medium
                    }
                    averageScore
                    seasonYear
                }
            }
        }
        """

        variables = {"search": query_text}

        try:
            result = self._query(query, variables)
            return result["Page"]["media"] if result else []
        except Exception:
            return []

    def get_anime_by_id(self, anime_id: int) -> dict | None:
        """Get anime info by AniList ID.

        Args:
            anime_id: AniList anime ID

        Returns:
            Anime data with id, title, episodes, etc. or None if not found

        """
        query = """
        query ($id: Int) {
            Media(id: $id, type: ANIME) {
                id
                title {
                    romaji
                    english
                    native
                }
                episodes
                coverImage {
                    medium
                }
                averageScore
                seasonYear
            }
        }
        """

        variables = {"id": anime_id}

        try:
            result = self._query(query, variables)
            return result.get("Media") if result else None
        except Exception:
            return None

    def get_recent_activities(self, limit: int = 5) -> list[dict]:
        """Get user's recent anime list activities.

        Args:
            limit: Number of recent activities to fetch (default 5)

        Returns:
            List of activity dicts with: type, status, progress, media info, createdAt

        """
        if not self.is_authenticated():
            return []

        # Ensure we have user_id
        if not self.user_id:
            user_info = self.get_viewer_info()
            if user_info:
                self.user_id = user_info["id"]
            else:
                return []

        query = """
        query ($userId: Int, $page: Int, $perPage: Int) {
            Page(page: $page, perPage: $perPage) {
                activities(userId: $userId, type: ANIME_LIST, sort: ID_DESC) {
                    ... on ListActivity {
                        id
                        status
                        progress
                        createdAt
                        media {
                            id
                            title {
                                romaji
                                english
                            }
                            episodes
                        }
                    }
                }
            }
        }
        """

        variables = {"userId": self.user_id, "page": 1, "perPage": limit}

        try:
            result = self._query(query, variables)
            return result["Page"]["activities"] if result else []
        except Exception:
            return []

    def is_in_any_list(self, anime_id: int) -> bool:
        """Check if anime is in any of the user's lists.

        Args:
            anime_id: AniList anime ID

        Returns:
            True if anime is in any list, False otherwise

        """
        if not self.is_authenticated():
            return False

        # Ensure we have user_id
        if not self.user_id:
            user_info = self.get_viewer_info()
            if user_info:
                self.user_id = user_info["id"]
            else:
                return False

        query = """
        query ($userId: Int, $mediaId: Int) {
            MediaList(userId: $userId, mediaId: $mediaId) {
                id
                status
            }
        }
        """

        variables = {"userId": self.user_id, "mediaId": anime_id}

        try:
            result = self._query(query, variables)
            return result is not None and "MediaList" in result and result["MediaList"] is not None
        except Exception:
            return False

    def add_to_list(self, anime_id: int, status: str = "CURRENT") -> bool:
        """Add anime to user's list.

        Args:
            anime_id: AniList anime ID
            status: List status (CURRENT, PLANNING, COMPLETED, PAUSED, DROPPED, REPEATING)

        Returns:
            True if successful

        """
        mutation = """
        mutation ($mediaId: Int, $status: MediaListStatus) {
            SaveMediaListEntry(mediaId: $mediaId, status: $status) {
                id
                status
                media {
                    title {
                        romaji
                    }
                }
            }
        }
        """

        variables = {
            "mediaId": anime_id,
            "status": status
        }

        try:
            result = self._query(mutation, variables)
            if result and "SaveMediaListEntry" in result:
                result["SaveMediaListEntry"]["media"]["title"]["romaji"]
                return True
            return False
        except Exception:
            return False

    def format_title(self, title_obj: dict) -> str:
        """Format title object to single string
        Shows romaji + english when both available.
        """
        romaji = title_obj.get("romaji")
        english = title_obj.get("english")
        native = title_obj.get("native")

        # If both romaji and english exist and are different
        if romaji and english and romaji != english:
            return f"{romaji} / {english}"
        # If only romaji
        if romaji:
            return romaji
        # If only english
        if english:
            return english
        # Fallback to native
        return native or "Unknown"


# Global client instance
anilist_client = AniListClient()
