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
from typing import TYPE_CHECKING, Protocol

import httpx
from pydantic import ValidationError

from models.config import settings
from models.models import (
    AniListActivity,
    AniListAnime,
    AniListManga,
    AniListMediaListEntry,
    AniListRelationEdge,
    AniListRelationNode,
    AniListTitle,
    AniListViewerInfo,
    Status,
)
from utils.anilist_titles import (
    format_title as _format_title,
    get_search_title as _get_search_title,
)
from utils.headless_detector import get_token_from_user
from utils.logging import get_logger

__all__ = [
    "AniListClient",
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


# === Contrato exigido pelos mixins ===


class _ClientOperationsRequired(Protocol):
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


# === Operações de anime ===


class AnimeOperationsMixin(_ClientOperationsRequired):  # type: ignore[misc]
    """Mixin providing anime-specific AniList operations.

    Requires: self._query(), self.is_authenticated(), self.get_viewer_info(),
              self.user_id, self.token
    """

    def get_trending(
        self,
        page: int = 1,
        per_page: int = 20,
        year: int | None = None,
        season: str | None = None,
    ) -> list[AniListAnime]:
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
                    idMal
                    title {
                        romaji
                        english
                        native
                    }
                    episodes
                    averageScore
                    seasonYear
                    season
                }
            }
        }
        """

        variables: dict[str, int | str] = {"page": page, "perPage": per_page}
        if year:
            variables["seasonYear"] = year
        if season:
            variables["season"] = season

        try:
            result = self._query(query, variables)
            media_list = result["Page"]["media"] if result else []
            return [AniListAnime.model_validate(item) for item in media_list]
        except (KeyError, TypeError, ValidationError):
            return []

    def get_user_list(
        self, status: str, page: int = 1, per_page: int = 50
    ) -> list[AniListMediaListEntry]:
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
                self.user_id = user_info.id
            else:
                return []

        # Use MediaListCollection with explicit userId
        query = """
        query ($userId: Int, $status: MediaListStatus) {
            MediaListCollection(userId: $userId, type: ANIME, status: $status) {
                lists {
                    entries {
                        id
                        status
                        progress
                        createdAt
                        media {
                            id
                            idMal
                            title {
                                romaji
                                english
                                native
                            }
                            episodes
                            averageScore
                            seasonYear
                            status
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

                return [AniListMediaListEntry.model_validate(entry) for entry in entries]
            return []
        except (KeyError, TypeError, ValidationError):
            return []

    def change_status(self, anime_id: int, status: Status) -> bool:
        """Change anime list status.

        Args:
            anime_id: AniList anime ID
            status: New status (Status.CURRENT, Status.PLANNING, Status.COMPLETED, Status.PAUSED, Status.DROPPED, Status.REPEATING)

        Returns:
            True if successful
        """
        if not self.is_authenticated():
            return False

        mutation = """
        mutation ($mediaId: Int, $status: MediaListStatus) {
            SaveMediaListEntry(mediaId: $mediaId, status: $status) {
                id
                status
            }
        }
        """

        variables = {"mediaId": anime_id, "status": Status(status).value}

        try:
            result = self._query(mutation, variables)
            if result and "SaveMediaListEntry" in result:
                return True
            return False
        except (KeyError, TypeError, ValidationError):
            return False

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
            result = self._query(query, variables)
            # Check if mutation succeeded
            if result and "SaveMediaListEntry" in result:
                return True
            logger.warning(
                "SaveMediaListEntry mutation failed for anime_id=%d, episode=%d. Result: %s",
                anime_id,
                episode,
                result,
            )
            return False
        except Exception as e:
            # KEPT GENERIC: Exception message content is critical to determine retry/ignore behavior
            # "completed"/"finished" → silent recovery; "progress"/"exceed" → warn; others → error
            error_msg = str(e)
            error_lower = error_msg.lower()

            # Check for specific error conditions
            if "completed" in error_lower or "finished" in error_lower:
                logger.info(
                    "Anime anime_id=%d is already COMPLETED on AniList. Ignoring sync request.",
                    anime_id,
                )
                # Return True because this is not an error - anime is already complete
                return True
            elif "progress" in error_lower and "exceed" in error_lower:
                logger.warning(
                    "Cannot update anime_id=%d ep=%d: "
                    "Episode number exceeds total episodes. "
                    "Check if anilist_id is correct.",
                    anime_id,
                    episode,
                )
            else:
                logger.error(
                    "Failed to update progress for anime_id=%d ep=%d: %s",
                    anime_id,
                    episode,
                    error_msg,
                )
            return False

    def search_anime(self, query_text: str) -> list[AniListAnime]:
        """Search anime by title.

        Returns list of anime matching query
        """
        query = """
        query ($search: String) {
            Page(perPage: 10) {
                media(type: ANIME, search: $search) {
                    id
                    idMal
                    title {
                        romaji
                        english
                        native
                    }
                    episodes
                    averageScore
                    seasonYear
                }
            }
        }
        """

        variables = {"search": query_text}

        try:
            result = self._query(query, variables)
            media_list = result["Page"]["media"] if result else []
            return [AniListAnime.model_validate(item) for item in media_list]
        except (KeyError, TypeError, ValidationError):
            return []

    def get_anime_by_id(self, anime_id: int) -> AniListAnime | None:
        """Get anime info by AniList ID.

        Args:
            anime_id: AniList anime ID

        Returns:
            Anime data with id, title, episodes, status, startDate, etc. or None if not found

        """
        query = """
        query ($id: Int) {
            Media(id: $id, type: ANIME) {
                id
                idMal
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
                status
                startDate {
                    year
                    month
                    day
                }
                nextAiringEpisode {
                    episode
                }
            }
        }
        """

        variables = {"id": anime_id}

        try:
            result = self._query(query, variables)
            media_data = result.get("Media") if result else None
            if media_data:
                return AniListAnime.model_validate(media_data)
            return None
        except (KeyError, TypeError, ValidationError):
            return None

    def get_recent_activities(self, limit: int = 5) -> list[AniListActivity]:
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
                self.user_id = user_info.id
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
                            idMal
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
            activities = result["Page"]["activities"] if result else []
            return [AniListActivity.model_validate(activity) for activity in activities]
        except (KeyError, TypeError, ValidationError):
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
                self.user_id = user_info.id
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
        except (KeyError, TypeError, ValidationError):
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
                    id
                    idMal
                    title {
                        romaji
                    }
                }
            }
        }
        """

        variables = {"mediaId": anime_id, "status": status}

        try:
            result = self._query(mutation, variables)
            if result and "SaveMediaListEntry" in result:
                return True
            return False
        except (KeyError, TypeError, ValidationError):
            return False

    def get_anime_relations(self, anime_id: int) -> list[AniListRelationEdge]:
        """Get anime relations (sequels, prequels, related, etc).

        Args:
            anime_id: AniList anime ID

        Returns:
            List of relation edges with node metadata (id, title, type, status, startDate)
        """
        query = """
        query ($id: Int) {
            Media(id: $id, type: ANIME) {
                relations {
                    edges {
                        relationType
                        node {
                            id
                            idMal
                            type
                            title {
                                romaji
                                english
                                native
                            }
                            episodes
                            status
                            startDate {
                                year
                                month
                                day
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {"id": anime_id}

        try:
            result = self._query(query, variables)
            if result and "Media" in result and "relations" in result["Media"]:
                edges = result["Media"]["relations"]["edges"]
                return [AniListRelationEdge.model_validate(edge) for edge in edges]
            return []
        except (KeyError, TypeError, ValidationError):
            return []

    def get_sequels(self, anime_id: int) -> list[AniListRelationNode]:
        """Get direct sequels of an anime.

        Args:
            anime_id: AniList anime ID

        Returns:
            List of sequel anime nodes with: id, title, episodes
        """
        relations = self.get_anime_relations(anime_id)

        # Filter for SEQUEL type relations and ANIME type nodes
        sequels = [
            edge.node
            for edge in relations
            if edge.relationType == "SEQUEL" and edge.node.type == "ANIME"
        ]

        return sequels

    def get_media_list_entry(self, anime_id: int) -> AniListMediaListEntry | None:
        """Get user's media list entry for an anime.

        Args:
            anime_id: AniList anime ID

        Returns:
            MediaList entry with: id, status, progress, score, or None if not in list
        """
        if not self.is_authenticated():
            return None

        # Ensure we have user_id
        if not self.user_id:
            user_info = self.get_viewer_info()
            if user_info:
                self.user_id = user_info.id
            else:
                return None

        query = """
        query ($userId: Int, $mediaId: Int) {
            MediaList(userId: $userId, mediaId: $mediaId) {
                id
                status
                progress
                score
                startedAt {
                    year
                    month
                    day
                }
                completedAt {
                    year
                    month
                    day
                }
            }
        }
        """

        variables = {"userId": self.user_id, "mediaId": anime_id}

        try:
            result = self._query(query, variables)
            if result and "MediaList" in result and result["MediaList"]:
                return AniListMediaListEntry.model_validate(result["MediaList"])
            return None
        except (KeyError, TypeError, ValidationError):
            return None

    def get_airing_episodes_for_watching(self) -> list[dict]:
        """Get user's watching anime with next airing episode info.

        Fetches anime from CURRENT list with airing episode data to support
        the "Novos Episódios" (New Episodes) tab feature.

        Returns:
            List of raw API entries with: progress, media (id, title, nextAiringEpisode, averageScore)
            or empty list if not authenticated or no data available
        """
        if not self.is_authenticated():
            return []

        # Ensure we have user_id
        if not self.user_id:
            user_info = self.get_viewer_info()
            if user_info:
                self.user_id = user_info.id
            else:
                return []

        query = """
        query ($userId: Int) {
            MediaListCollection(userId: $userId, type: ANIME, status: CURRENT) {
                lists {
                    entries {
                        progress
                        media {
                            id
                            idMal
                            title {
                                romaji
                                english
                                native
                            }
                            averageScore
                            status
                            episodes
                            endDate {
                                year
                                month
                                day
                            }
                            nextAiringEpisode {
                                episode
                                airingAt
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {"userId": self.user_id}

        try:
            result = self._query(query, variables)
            if result and "MediaListCollection" in result:
                # Flatten the lists structure
                entries = []
                for list_group in result["MediaListCollection"]["lists"]:
                    entries.extend(list_group["entries"])
                return entries
            return []
        except (KeyError, TypeError, ValidationError):
            return []


# === Operações de manga ===


class MangaOperationsMixin(_ClientOperationsRequired):  # type: ignore[misc]
    """Mixin providing manga-specific AniList operations.

    Requires: self._query(), self.is_authenticated(), self.get_viewer_info(),
              self.user_id, self.token
    """

    def get_trending_manga(self, page: int = 1, per_page: int = 20) -> list[AniListManga]:
        """Get trending manga.

        Args:
            page: Page number
            per_page: Items per page

        Returns list of manga with: id, title, chapters, volumes, coverImage
        """
        query = """
        query ($page: Int, $perPage: Int) {
            Page(page: $page, perPage: $perPage) {
                media(type: MANGA, sort: TRENDING_DESC) {
                    id
                    title {
                        romaji
                        english
                        native
                    }
                    chapters
                    volumes
                    averageScore
                    startDate {
                        year
                        month
                        day
                    }
                    endDate {
                        year
                        month
                        day
                    }
                }
            }
        }
        """

        variables = {"page": page, "perPage": per_page}

        try:
            result = self._query(query, variables)
            media_list = result["Page"]["media"] if result else []
            return [AniListManga.model_validate(item) for item in media_list]
        except (KeyError, TypeError, ValidationError):
            return []

    def get_user_manga_list(
        self, status: str, page: int = 1, per_page: int = 50
    ) -> list[AniListMediaListEntry]:
        """Get authenticated user's manga list by status.

        Args:
            status: CURRENT, PLANNING, COMPLETED, DROPPED, PAUSED, REPEATING
            page: Page number
            per_page: Items per page

        Returns list with: manga data + progress
        """
        if not self.is_authenticated():
            return []

        # Ensure we have user_id
        if not self.user_id:
            user_info = self.get_viewer_info()
            if user_info:
                self.user_id = user_info.id
            else:
                return []

        # Use MediaListCollection with explicit userId for manga
        query = """
        query ($userId: Int, $status: MediaListStatus) {
            MediaListCollection(userId: $userId, type: MANGA, status: $status) {
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
                            chapters
                            volumes
                            averageScore
                            startDate {
                                year
                                month
                                day
                            }
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

                return [AniListMediaListEntry.model_validate(entry) for entry in entries]
            return []
        except (KeyError, TypeError, ValidationError):
            return []

    def get_manga_by_id(self, manga_id: int) -> AniListManga | None:
        """Get manga info by AniList ID.

        Args:
            manga_id: AniList manga ID

        Returns:
            Manga data with id, title, chapters, volumes, etc. or None if not found
        """
        query = """
        query ($id: Int) {
            Media(id: $id, type: MANGA) {
                id
                title {
                    romaji
                    english
                    native
                }
                chapters
                volumes
                coverImage {
                    medium
                }
                averageScore
                startDate {
                    year
                    month
                    day
                }
                endDate {
                    year
                    month
                    day
                }
            }
        }
        """

        variables = {"id": manga_id}

        try:
            result = self._query(query, variables)
            media_data = result.get("Media") if result else None
            if media_data:
                return AniListManga.model_validate(media_data)
            return None
        except (KeyError, TypeError, ValidationError):
            return None

    def get_manga_list_entry(self, manga_id: int) -> AniListMediaListEntry | None:
        """Get user's media list entry for a manga.

        Args:
            manga_id: AniList manga ID

        Returns:
            MediaList entry with: id, status, progress, score, or None if not in list
        """
        if not self.is_authenticated():
            return None

        # Ensure we have user_id
        if not self.user_id:
            user_info = self.get_viewer_info()
            if user_info:
                self.user_id = user_info.id
            else:
                return None

        query = """
        query ($userId: Int, $mediaId: Int) {
            MediaList(userId: $userId, mediaId: $mediaId) {
                id
                status
                progress
                score
                startedAt {
                    year
                    month
                    day
                }
                completedAt {
                    year
                    month
                    day
                }
            }
        }
        """

        variables = {"userId": self.user_id, "mediaId": manga_id}

        try:
            result = self._query(query, variables)
            if result and "MediaList" in result and result["MediaList"]:
                return AniListMediaListEntry.model_validate(result["MediaList"])
            return None
        except (KeyError, TypeError, ValidationError):
            return None

    def update_manga_progress(self, manga_id: int, chapter: int) -> bool:
        """Update manga progress.

        Args:
            manga_id: AniList manga ID
            chapter: Chapter number (1-indexed)

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

        variables = {"mediaId": manga_id, "progress": chapter}

        try:
            result = self._query(query, variables)
            # Check if mutation succeeded
            if result and "SaveMediaListEntry" in result:
                return True
            return False
        except Exception as e:
            # KEPT GENERIC: Exception message content determines error handling strategy
            # "completed"/"finished" → silent recovery; others → log and return False
            error_msg = str(e).lower()
            if "completed" in error_msg or "finished" in error_msg:
                # Silently handle COMPLETED status - user needs to change status manually
                return False
            return False

    def add_manga_to_list(self, manga_id: int, status: str = "CURRENT") -> bool:
        """Add manga to user's list.

        Args:
            manga_id: AniList manga ID
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

        variables = {"mediaId": manga_id, "status": status}

        try:
            result = self._query(mutation, variables)
            if result and "SaveMediaListEntry" in result:
                return True
            return False
        except (KeyError, TypeError, ValidationError):
            return False

    def change_manga_status(self, manga_id: int, status: Status) -> bool:
        """Change manga list status.

        Args:
            manga_id: AniList manga ID
            status: New status (Status.CURRENT, Status.PLANNING, Status.COMPLETED, Status.PAUSED, Status.DROPPED, Status.REPEATING)

        Returns:
            True if successful
        """
        if not self.is_authenticated():
            return False

        mutation = """
        mutation ($mediaId: Int, $status: MediaListStatus) {
            SaveMediaListEntry(mediaId: $mediaId, status: $status) {
                id
                status
            }
        }
        """

        variables = {"mediaId": manga_id, "status": Status(status).value}

        try:
            result = self._query(mutation, variables)
            if result and "SaveMediaListEntry" in result:
                return True
            return False
        except (KeyError, TypeError, ValidationError):
            return False

    def search_manga(self, query_text: str) -> list[AniListManga]:
        """Search manga by title.

        Returns list of manga matching query
        """
        query = """
        query ($search: String) {
            Page(perPage: 10) {
                media(type: MANGA, search: $search) {
                    id
                    title {
                        romaji
                        english
                        native
                    }
                    chapters
                    volumes
                    averageScore
                    startDate {
                        year
                        month
                        day
                    }
                }
            }
        }
        """

        variables = {"search": query_text}

        try:
            result = self._query(query, variables)
            media_list = result["Page"]["media"] if result else []
            return [AniListManga.model_validate(item) for item in media_list]
        except (KeyError, TypeError, ValidationError):
            return []


# === Cliente GraphQL ===


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

    def _save_token(self, token: str, user_id: int | None = None) -> None:
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
            except (httpx.ConnectError, httpx.TimeoutException):
                return False
            except Exception:
                logger.info(
                    "\n❌ Não foi possível validar o token. AniList pode estar fora do ar. Tente novamente mais tarde.\n"
                )
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
        except httpx.ConnectError:
            logger.warning(
                "⚠️  Não foi possível conectar ao AniList. Verifique sua conexão ou tente mais tarde."
            )
            raise
        except httpx.TimeoutException:
            logger.warning("⚠️  AniList não respondeu a tempo. O serviço pode estar fora do ar.")
            raise
        except Exception as e:
            msg = str(e)
            server_error = any(f"status {code}" in msg for code in (500, 502, 503, 504))
            if server_error:
                logger.warning(
                    "⚠️  AniList retornou erro de servidor. O serviço pode estar fora do ar."
                )
                raise
            logger.debug(f"Token validation error: {e}")
            return False

    def _query(self, query: str, variables: dict | None = None, token: str | None = None) -> dict:
        """Execute GraphQL query with retry on rate limit (429).

        Args:
            query: GraphQL query string
            variables: Query variables
            token: Optional token override (for validation)

        Returns:
            Query result data

        """
        from scrapers.plugins.utils import http_request_with_retry

        headers = {}
        use_token = token if token else self.token

        if use_token:
            headers["Authorization"] = f"Bearer {use_token}"

        not_found_exc: httpx.HTTPStatusError | None = None
        try:
            response = http_request_with_retry(
                "POST",
                settings.anilist.api_url,
                json={"query": query, "variables": variables or {}},
                headers=headers,
                timeout=settings.anilist.request_timeout_seconds,
                follow_redirects=True,
            )
        except httpx.HTTPStatusError as exc:
            # AniList sinaliza "entrada inexistente" (ex.: MediaList de um anime
            # fora da lista do usuário) com 404, mas devolve um corpo GraphQL
            # válido cujo data traz nulls. Tratamos como resposta normal.
            if exc.response.status_code != 404:
                raise
            logger.debug(f"AniList 404 tratado como resposta GraphQL: {exc.response.text}")
            response = exc.response
            not_found_exc = exc

        try:
            result = response.json()
        except json.JSONDecodeError:
            # 404 sem corpo GraphQL não veio do AniList (proxy, portal cativo):
            # o erro HTTP original é mais informativo que o de parsing.
            if not_found_exc is not None:
                raise not_found_exc from None
            raise

        # Num 404 os "errors" apenas descrevem o recurso ausente; o data com
        # nulls é a resposta legítima e quem chamou sabe interpretá-la.
        if "errors" in result and not (not_found_exc is not None and "data" in result):
            msg = f"GraphQL error: {result['errors']}"
            raise Exception(msg)

        return result.get("data")

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
