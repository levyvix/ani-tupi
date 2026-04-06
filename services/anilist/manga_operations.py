"""Manga-specific operations for AniList API.

Mixin class providing manga trending, lists, search, and sync.
"""

from typing import Protocol

from models.models import (
    AniListManga,
    AniListMediaListEntry,
    AniListViewerInfo,
    Status,
)


class _MangaOperationsRequired(Protocol):
    """Protocol defining methods required by MangaOperationsMixin."""

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


class MangaOperationsMixin(_MangaOperationsRequired):  # type: ignore[misc]
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
            # Log error for debugging (might be COMPLETED status issue)
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
        except Exception:
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
        except Exception:
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
        except Exception:
            return []
