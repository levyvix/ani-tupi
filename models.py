"""Pydantic data models for structured data transfer.

Defines DTOs (Data Transfer Objects) for:
- AnimeMetadata: Anime information from scrapers
- EpisodeData: Episode lists from scrapers
- SearchResult: Repository search results
- VideoUrl: Playback URLs with optional headers
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


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
        episode_urls: List of episode URLs
        source: Plugin source name

    Validation:
        - episode_titles and episode_urls must have same length
    """

    anime_title: str = Field(..., min_length=1, description="Anime title")
    episode_titles: list[str] = Field(..., description="Episode titles")
    episode_urls: list[str] = Field(..., description="Episode URLs")
    source: str = Field(..., min_length=1, description="Plugin source name")

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
