"""Anime-specific operations for AniList API.

Mixin class providing anime trending, lists, search, sync, and relations.
"""

import logging
from typing import Protocol

from models.models import (
    AniListAnime,
    AniListMediaListEntry,
    AniListActivity,
    AniListRelationEdge,
    AniListRelationNode,
    AniListViewerInfo,
    Status,
)

logger = logging.getLogger(__name__)


class _AnimeOperationsRequired(Protocol):
    """Protocol defining methods required by AnimeOperationsMixin."""

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


class AnimeOperationsMixin(_AnimeOperationsRequired):  # type: ignore[misc]
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
            # Log error for debugging
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
        except Exception:
            return []
