"""Anime download and offline-sync data models."""

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator


class DownloadedEpisode(BaseModel):
    """Metadata for a downloaded episode.

    Attributes:
        episode_number: Episode number (1-indexed)
        file_path: Path to downloaded video file
        file_size_mb: File size in MB
        source: Source scraper name
        downloaded_at: ISO timestamp when downloaded
        status: Download status (success, failed, corrupted)
    """

    episode_number: int = Field(..., ge=1, description="Episode number (1-indexed)")
    file_path: Path = Field(..., description="Path to downloaded video file")
    file_size_mb: float = Field(..., ge=0.0, description="File size in MB")
    source: str = Field(..., min_length=1, description="Source scraper name")
    downloaded_at: datetime = Field(default_factory=datetime.now, description="Download timestamp")
    status: Literal["success", "failed", "corrupted"] = Field(
        "success", description="Download status (success, failed, corrupted)"
    )
    # Optional fields make new records addressable by AniList while keeping
    # legacy title-indexed records valid.
    anilist_id: int | None = Field(None, gt=0, description="AniList media ID")
    season: int | None = Field(None, ge=1, description="Anime season")
    variant: str | None = Field(None, description="Dub/sub or other variant")
    episode_url: str | None = Field(None, description="Episode page used for download")


class AiringSourceCandidate(BaseModel):
    """One source page belonging to an aggregated airing result."""

    title: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    anime_url: str = Field(..., min_length=1, validation_alias=AliasChoices("anime_url", "url"))
    params: dict[str, Any] = Field(default_factory=dict)
    variant: str | None = None
    season: int = Field(1, ge=1)

    @field_validator("anime_url")
    @classmethod
    def validate_anime_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("anime_url must be an absolute HTTP(S) URL")
        return value

    @field_validator("source")
    @classmethod
    def validate_single_source(cls, value: str) -> str:
        value = value.strip()
        if not value or "," in value or value.lower() == "mixed":
            raise ValueError("source must identify exactly one scraper")
        return value


class AiringSourceBinding(BaseModel):
    """Source context that can be used safely by the airing monitor.

    ``season=None`` deliberately represents an unresolved context. It is
    accepted while reading old or partially written data, but the airing
    source store refuses to make it effective.
    """

    model_config = {"populate_by_name": True}

    title: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    anime_url: str = Field(..., min_length=1, validation_alias=AliasChoices("anime_url", "url"))
    params: dict[str, Any] = Field(default_factory=dict)
    variant: str | None = None
    alternatives: list["AiringSourceCandidate"] = Field(
        default_factory=list,
        description="Additional equivalent source pages searched in order",
    )
    episode_number: int | None = Field(
        None,
        ge=1,
        description="Episode number that established the playback evidence",
    )
    season: int | None = Field(1, ge=1)
    episode_number_offset: int = 0
    episode_mapping: dict[int, int] = Field(default_factory=dict)
    recorded_at: datetime | None = Field(
        None,
        validation_alias=AliasChoices("recorded_at", "played_at", "last_played_at"),
    )

    @field_validator("anime_url")
    @classmethod
    def validate_anime_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("anime_url must be an absolute HTTP(S) URL")
        return value

    @field_validator("source")
    @classmethod
    def validate_single_source(cls, value: str) -> str:
        value = value.strip()
        if not value or "," in value or value.lower() == "mixed":
            raise ValueError("source must identify exactly one scraper")
        return value

    def anilist_episode_number(self, source_episode: int) -> int:
        """Translate a source episode number using the saved context."""
        return self.episode_mapping.get(source_episode, source_episode + self.episode_number_offset)

    @property
    def url(self) -> str:
        """Compatibility spelling for the saved anime page URL."""
        return self.anime_url

    @property
    def source_name(self) -> str:
        """Compatibility spelling for callers that use source_name."""
        return self.source

    @property
    def played_at(self) -> datetime | None:
        return self.recorded_at


class AiringSourceRecord(BaseModel):
    """The two independent origins associated with one AniList media ID."""

    configured: AiringSourceBinding | None = None
    last_played: AiringSourceBinding | None = None


class AiringDownloadState(BaseModel):
    """Small persisted summary for a monitor execution."""

    version: int = Field(1, ge=1)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    downloaded: int = Field(0, ge=0)
    skipped: int = Field(0, ge=0)
    failures: dict[str, str] = Field(default_factory=dict)
    exclusions: dict[str, str] = Field(default_factory=dict)


# Descriptive aliases for integrations that call the record a preference or
# the execution summary a monitor state.
AiringSourcePreferences = AiringSourceRecord
AiringMonitorState = AiringDownloadState


class AiringEpisodeCandidate(BaseModel):
    """A published, numbered episode returned by the linked source."""

    episode_number: int = Field(..., ge=1)
    source_episode_number: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    season: int = Field(..., ge=1)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("episode URL must be an absolute HTTP(S) URL")
        return value


class DownloadResult(BaseModel):
    """Result of a download operation.

    Attributes:
        successful: Number of successful downloads
        failed: List of failed episode numbers
        corrupted: List of corrupted episode numbers
        skipped: List of already-downloaded episode numbers
        summary: Human-readable summary
    """

    successful: int = Field(..., ge=0, description="Number of successful downloads")
    failed: list[int] = Field(default_factory=list, description="List of failed episode numbers")
    corrupted: list[int] = Field(
        default_factory=list, description="List of corrupted episode numbers"
    )
    skipped: list[int] = Field(
        default_factory=list, description="List of already-downloaded episodes"
    )
    summary: str = Field(..., min_length=1, description="Human-readable summary")


class AnimeDownloadHistory(BaseModel):
    """History of downloaded anime per title.

    Attributes:
        anime_title: Title of the anime
        episodes: Dictionary of episode_number -> DownloadedEpisode
        last_downloaded: ISO timestamp of last download
        total_size_mb: Total size of all downloaded episodes
    """

    anime_title: str = Field(..., min_length=1, description="Anime title")
    episodes: dict[int, DownloadedEpisode] = Field(
        default_factory=dict, description="Downloaded episodes by number"
    )
    last_downloaded: datetime = Field(
        default_factory=datetime.now, description="Last download timestamp"
    )
    total_size_mb: float = Field(default=0.0, ge=0.0, description="Total size of all episodes")
    anilist_id: int | None = Field(None, gt=0, description="AniList media ID")
    season: int | None = Field(None, ge=1, description="Anime season")
    variant: str | None = Field(None, description="Dub/sub or other variant")

    def get_episode_numbers(self) -> list[int]:
        """Get sorted list of downloaded episode numbers.

        Returns:
            Sorted list of episode numbers
        """
        return sorted(self.episodes.keys())

    def has_episode(self, episode_number: int) -> bool:
        """Check if episode is downloaded.

        Args:
            episode_number: Episode number to check

        Returns:
            True if episode exists and status is 'success'
        """
        ep = self.episodes.get(episode_number)
        return ep is not None and ep.status == "success"


class AnimeDownloadDatabase(BaseModel):
    """Root model for anime download history database.

    Stores downloaded anime across the library, serialized to JSON.

    Attributes:
        version: Schema version for migrations
        anime: Dictionary of anime_title -> AnimeDownloadHistory
        last_updated: ISO timestamp of last update
    """

    version: int = Field(default=1, description="Schema version for migrations")
    anime: dict[str, AnimeDownloadHistory] = Field(
        default_factory=dict, description="Downloaded anime by title"
    )
    last_updated: datetime = Field(
        default_factory=datetime.now, description="Last update timestamp"
    )


class OfflineSyncQueueEntry(BaseModel):
    """Pending AniList progress update for retry.

    Stores failed sync attempts to retry when network becomes available.

    Attributes:
        anime_title: Anime title for reference
        episode_number: Episode watched (1-indexed)
        anilist_id: AniList media ID for sync
        timestamp: When sync was attempted
        retry_count: Number of retry attempts
        last_error: Most recent error message
        is_local: Whether episode came from local library (enables file cleanup)
        file_path: Path to local episode file (for cleanup after successful sync)
    """

    anime_title: str = Field(..., min_length=1, description="Anime title")
    episode_number: int = Field(..., ge=1, description="Episode number watched")
    anilist_id: int = Field(..., gt=0, description="AniList media ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="When sync was attempted")
    retry_count: int = Field(default=0, ge=0, description="Number of retry attempts")
    last_error: str | None = Field(None, description="Most recent error message")
    is_local: bool = Field(default=False, description="From local library (enables file cleanup)")
    file_path: str | None = Field(None, description="Path to local episode file")


class OfflineSyncQueue(BaseModel):
    """Database of pending offline sync operations.

    Persisted to JSON for retry on app startup.

    Attributes:
        version: Schema version for migrations
        entries: List of pending sync operations
        last_updated: When queue was last updated
    """

    version: int = Field(default=1, description="Schema version for migrations")
    entries: list[OfflineSyncQueueEntry] = Field(
        default_factory=list, description="Pending sync operations"
    )
    last_updated: datetime = Field(
        default_factory=datetime.now, description="Last update timestamp"
    )
