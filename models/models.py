"""Pydantic data models for structured data transfer.

Defines DTOs (Data Transfer Objects) for:
- AnimeMetadata: Anime information from scrapers
- EpisodeData: Episode lists from scrapers
- SearchResult: Repository search results
- VideoUrl: Playback URLs with optional headers
- MangaMetadata: Manga information from MangaDex
- ChapterData: Chapter information from MangaDex
- MangaHistoryEntry: Reading progress tracking
"""

from datetime import datetime
from enum import Enum
from typing import Any, TypeAlias

from pydantic import BaseModel, Field, field_validator, model_validator

# Type aliases for common patterns
AnimeTitle: TypeAlias = str
EpisodeNumber: TypeAlias = int
AnimeURL: TypeAlias = str
PluginName: TypeAlias = str
AnimeTuple: TypeAlias = tuple[str, str, dict[str, Any] | None]  # (url, source, params)
EpisodeList: TypeAlias = list[str]
EpisodeURLList: TypeAlias = list[str]
AniListID: TypeAlias = int | None
TimestampSeconds: TypeAlias = int


class AnimeMetadata(BaseModel):
    """Anime metadata from scraper.

    Attributes:
        title: Anime title (non-empty)
        url: Anime URL from scraper (must be http/https)
        source: Plugin source name (non-empty)
        params: Optional extra parameters for scraper
    """

    title: str = Field(..., min_length=1, description="Anime title")
    url: str = Field(..., min_length=1, description="Anime URL from scraper")
    source: str = Field(..., min_length=1, description="Plugin source name")
    params: dict[str, Any] | None = Field(None, description="Extra params for scraper")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"URL must be http(s), got: {v}")
        return v


class EpisodeData(BaseModel):
    """Episode list from scraper.

    Attributes:
        anime_title: Title of the anime
        episode_titles: List of episode titles
        episode_urls: List of episode URLs (must be http/https)
        source: Plugin source name

    Validation:
        - episode_titles and episode_urls must have same length
        - All episode URLs must be valid http(s) URLs
    """

    anime_title: str = Field(..., min_length=1, description="Anime title")
    episode_titles: list[str] = Field(..., description="Episode titles")
    episode_urls: list[str] = Field(..., description="Episode URLs (must be http/https)")
    source: str = Field(..., min_length=1, description="Plugin source name")

    @field_validator("episode_urls", mode="before")
    @classmethod
    def validate_episode_urls(cls, v: list[str]) -> list[str]:
        """Validate all episode URLs are properly formatted."""
        for url in v:
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"Episode URL must be http(s), got: {url}")
        return v

    @model_validator(mode="after")
    def validate_lengths(self) -> "EpisodeData":
        """Validate episode lists have matching lengths."""
        if len(self.episode_titles) != len(self.episode_urls):
            raise ValueError(
                f"Mismatched episodes: {len(self.episode_titles)} titles "
                f"vs {len(self.episode_urls)} URLs"
            )
        return self


class SearchResult(BaseModel):
    """Repository search result.

    Attributes:
        anime_titles: List of found anime titles
        total_sources: Number of sources that returned results
    """

    anime_titles: list[str] = Field(..., description="Found anime titles")
    total_sources: int = Field(ge=0, description="Number of sources with results")


class VideoUrl(BaseModel):
    """Video playback URL with optional headers.

    Attributes:
        url: Video URL (m3u8 HLS or direct video file)
        headers: Optional HTTP headers for playback (User-Agent, Referer, etc.)
    """

    url: str = Field(..., min_length=1, description="Video URL (m3u8 or mp4/mkv/etc)")
    headers: dict[str, str] | None = Field(None, description="HTTP headers for playback")

    @field_validator("url")
    @classmethod
    def validate_video_url(cls, v: str) -> str:
        """Validate video URL format.

        Accepts:
        - m3u8 (HLS streaming)
        - Direct video files (mp4, mkv, avi, webm)
        - Dynamic URLs (logged as warning but allowed)
        """
        import warnings

        valid_extensions = (".m3u8", ".mp4", ".mkv", ".avi", ".webm")
        if not any(v.endswith(ext) for ext in valid_extensions):
            # Some sites have dynamic URLs without file extensions
            warnings.warn(f"Video URL may be invalid: {v}", stacklevel=2)
        return v


class MangaStatus(str, Enum):
    """Manga publication status."""

    ONGOING = "ongoing"
    COMPLETED = "completed"
    HIATUS = "hiatus"
    CANCELLED = "cancelled"


class MangaMetadata(BaseModel):
    """Manga metadata from MangaDex.

    Attributes:
        id: MangaDex UUID
        title: Manga title
        description: Optional description
        status: Publication status (ongoing, completed, etc.)
        year: Publication year
        cover_url: Optional cover image URL
        tags: List of tags/genres
    """

    id: str = Field(..., min_length=1, description="MangaDex UUID")
    title: str = Field(..., min_length=1, description="Manga title")
    description: str | None = Field(None, description="Manga description")
    status: MangaStatus = Field(..., description="Publication status")
    year: int | None = Field(None, ge=1900, le=2100, description="Publication year")
    cover_url: str | None = Field(None, description="Cover image URL")
    tags: list[str] = Field(default_factory=list, description="Tags/genres")


class ChapterData(BaseModel):
    """Chapter data from MangaDex.

    Attributes:
        id: Chapter UUID
        number: Chapter number (supports decimals like "42.5")
        title: Optional chapter title
        language: Language code (pt-br, en, ja, etc.)
        published_at: Optional publication date
        scanlation_group: Optional scanlation group name
    """

    id: str = Field(..., min_length=1, description="Chapter UUID")
    number: str = Field(..., min_length=1, description="Chapter number (e.g., '42', '42.5')")
    title: str | None = Field(None, description="Chapter title")
    language: str = Field(..., min_length=1, description="Language code (pt-br, en, ja)")
    published_at: datetime | None = Field(None, description="Publication date")
    scanlation_group: str | None = Field(None, description="Scanlation group name")

    def display_name(self) -> str:
        """Format chapter for display.

        Returns:
            Formatted string like "Cap. 42 - Título" or "Cap. 42" if no title.
        """
        if self.title:
            return f"Cap. {self.number} - {self.title}"
        return f"Cap. {self.number}"


class MangaHistoryEntry(BaseModel):
    """Single entry in reading history.

    Attributes:
        last_chapter: Chapter number (e.g., "42.5")
        last_chapter_id: Optional MangaDex chapter ID
        timestamp: When the chapter was read
        manga_id: Optional MangaDex manga ID
    """

    last_chapter: str = Field(..., min_length=1, description="Chapter number")
    last_chapter_id: str | None = Field(None, description="MangaDex chapter ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="Read timestamp")
    manga_id: str | None = Field(None, description="MangaDex manga ID")
