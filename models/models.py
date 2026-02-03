"""Pydantic data models for structured data transfer.

Defines DTOs (Data Transfer Objects) for:
- AnimeMetadata: Anime information from scrapers
- EpisodeData: Episode lists from scrapers
- SearchResult: Repository search results
- VideoUrl: Playback URLs with optional headers
- MangaMetadata: Manga information from MangaDex
- ChapterData: Chapter information from MangaDex
- MangaHistoryEntry: Reading progress tracking
- AnimeSearchResult: Immutable search result for one anime
- SearchResults: Immutable collection of search results
- EpisodeList: Immutable episode list
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

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


class AniListSearchResult(BaseModel):
    """AniList search result with score."""

    anilist_id: int
    score: int
    title: str


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
        tags: List of tags/genres
        anilist_id: Optional AniList manga ID for integration
        anilist_data: Optional AniList manga data
    """

    id: str = Field(..., min_length=1, description="MangaDex UUID")
    title: str = Field(..., min_length=1, description="Manga title")
    description: str | None = Field(None, description="Manga description")
    status: MangaStatus = Field(..., description="Publication status")
    year: int | None = Field(None, ge=1900, le=2100, description="Publication year")
    tags: list[str] = Field(default_factory=list, description="Tags/genres")
    anilist_id: int | None = Field(None, description="AniList manga ID")
    anilist_data: "Optional[AniListManga]" = Field(None, description="AniList manga data")


class ChapterData(BaseModel):
    """Chapter data from MangaDex or other manga sources.

    Attributes:
        id: Chapter UUID or identifier
        number: Chapter number (supports decimals like "42.5")
        title: Optional chapter title
        url: Chapter URL extracted by the plugin during scraping.
            Must be populated by the plugin's get_chapters() method.
            For web scrapers: the href attribute from chapter links.
            For API sources: constructed from response data (e.g., MangaDex).
        language: Language code (pt-br, en, ja, etc.)
        published_at: Optional publication date
        scanlation_group: Optional scanlation group name
    """

    id: str = Field(..., min_length=1, description="Chapter UUID")
    number: str = Field(..., min_length=1, description="Chapter number (e.g., '42', '42.5')")
    title: str | None = Field(None, description="Chapter title")
    url: str | None = Field(
        None, description="Chapter URL extracted by plugin (required for reading)"
    )
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


class LocalChapter(BaseModel):
    """Local chapter metadata for offline reading.

    Attributes:
        chapter_number: Chapter number (e.g., "01", "42", "42.5")
        pdf_path: Path to PDF file (None if doesn't exist)
        has_pdf: Whether PDF file exists
        has_images: Whether chapter has any image files
        image_count: Number of image files in chapter directory
        file_size_mb: Total size of chapter directory in MB
    """

    chapter_number: str = Field(..., min_length=1, description="Chapter number")
    pdf_path: Path | None = Field(None, description="Path to PDF file")
    has_pdf: bool = Field(..., description="Whether PDF file exists")
    has_images: bool = Field(..., description="Whether chapter has image files")
    image_count: int = Field(default=0, ge=0, description="Number of image files")
    file_size_mb: float = Field(default=0.0, ge=0.0, description="Total size in MB")

    def display_name(self) -> str:
        """Format chapter for display.

        Returns:
            Formatted string like "Cap. 01 (PDF, 20.7 MB)" or "Cap. 01 (Images: 42)"
        """
        if self.has_pdf and self.file_size_mb > 0:
            return f"Cap. {self.chapter_number} (PDF, {self.file_size_mb:.1f} MB)"
        elif self.has_images and self.image_count > 0:
            return f"Cap. {self.chapter_number} (Imagens: {self.image_count})"
        else:
            return f"Cap. {self.chapter_number}"


class MangaHistoryEntry(BaseModel):
    """Single entry in reading history.

    Attributes:
        last_chapter: Chapter number (e.g., "42.5")
        last_chapter_id: Optional MangaDex chapter ID
        timestamp: When the chapter was read
        manga_id: Optional MangaDex manga ID
        anilist_id: Optional AniList manga ID for integration
        manga_status: Optional AniList status for this manga
        downloaded_chapters: List of chapter numbers downloaded for later reading
    """

    last_chapter: str = Field(..., min_length=1, description="Chapter number")
    last_chapter_id: str | None = Field(None, description="MangaDex chapter ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="Read timestamp")
    manga_id: str | None = Field(None, description="MangaDex manga ID")
    anilist_id: int | None = Field(None, description="AniList manga ID")
    manga_status: str | None = Field(None, description="AniList status for this manga")
    downloaded_chapters: list[str] = Field(
        default_factory=list, description="Chapter numbers downloaded for later"
    )


# AniList API Models
class AniListTitle(BaseModel):
    """AniList title object with multiple language variants."""

    romaji: str | None = Field(None, description="Romaji title")
    english: str | None = Field(None, description="English title")
    native: str | None = Field(None, description="Native title")


class AniListAnimeStatistics(BaseModel):
    """AniList anime statistics."""

    count: int = Field(ge=0, description="Total anime count")
    episodesWatched: int = Field(ge=0, description="Total episodes watched")
    minutesWatched: int = Field(ge=0, description="Total minutes watched")


class AniListStatistics(BaseModel):
    """AniList user statistics."""

    anime: AniListAnimeStatistics | None = Field(None, description="Anime statistics")


class AniListViewerInfo(BaseModel):
    """AniList viewer/user information.

    Attributes:
        id: User ID
        name: Username
        statistics: User statistics
    """

    id: int = Field(..., description="User ID")
    name: str = Field(..., min_length=1, description="Username")
    statistics: AniListStatistics | None = Field(None, description="User statistics")


class AniListAnime(BaseModel):
    """AniList anime media object.

    Attributes:
        id: AniList anime ID
        title: Title object with multiple languages
        episodes: Total episodes (None if unknown)
        averageScore: Average score (0-100)
        seasonYear: Year of release
        season: Season (WINTER, SPRING, SUMMER, FALL)
        type: Media type (ANIME, MANGA)
    """

    id: int = Field(..., description="AniList anime ID")
    title: AniListTitle = Field(..., description="Title object")
    episodes: int | None = Field(None, description="Total episodes")
    averageScore: int | None = Field(None, ge=0, le=100, description="Average score")
    seasonYear: int | None = Field(None, ge=1900, le=2100, description="Release year")
    season: str | None = Field(None, description="Season (WINTER, SPRING, SUMMER, FALL)")
    type: str | None = Field(None, description="Media type")


class AniListManga(BaseModel):
    """AniList manga media object.

    Attributes:
        id: AniList manga ID
        title: Title object with multiple languages
        chapters: Total chapters (None if unknown)
        volumes: Total volumes (None if unknown)
        averageScore: Average score (0-100)
        startDate: Start date (year, month, day - values can be None)
        endDate: End date (year, month, day - values can be None for ongoing)
        type: Media type (ANIME, MANGA)
    """

    id: int = Field(..., description="AniList manga ID")
    title: AniListTitle = Field(..., description="Title object")
    chapters: int | None = Field(None, description="Total chapters")
    volumes: int | None = Field(None, description="Total volumes")
    averageScore: int | None = Field(None, ge=0, le=100, description="Average score")
    startDate: dict[str, int | None] | None = Field(
        None, description="Start date (year, month, day - values can be None)"
    )
    endDate: dict[str, int | None] | None = Field(
        None, description="End date (year, month, day - values can be None for ongoing)"
    )
    type: str | None = Field(None, description="Media type")


class AniListMediaListEntry(BaseModel):
    """AniList media list entry.

    Attributes:
        id: List entry ID
        status: List status (CURRENT, PLANNING, COMPLETED, etc.)
        progress: Episode progress
        score: User score
        startedAt: Start date
        completedAt: Completion date
        media: Anime media object
    """

    id: int = Field(..., description="List entry ID")
    status: str | None = Field(None, description="List status")
    progress: int | None = Field(None, ge=0, description="Episode progress")
    score: int | None = Field(None, ge=0, le=100, description="User score")
    startedAt: dict[str, int] | None = Field(None, description="Start date (year, month, day)")
    completedAt: dict[str, int] | None = Field(
        None, description="Completion date (year, month, day)"
    )
    media: AniListAnime | None = Field(None, description="Anime media object")
    createdAt: int | None = Field(None, description="Creation timestamp")


class AniListActivity(BaseModel):
    """AniList activity (list update).

    Attributes:
        id: Activity ID
        status: List status
        progress: Episode progress
        createdAt: Creation timestamp
        media: Anime media object
    """

    id: int = Field(..., description="Activity ID")
    status: str | None = Field(None, description="List status")
    progress: str | int | None = Field(None, description="Episode progress")
    createdAt: int = Field(..., description="Creation timestamp")
    media: AniListAnime | None = Field(None, description="Anime media object")


class AniListRelationNode(BaseModel):
    """AniList relation node (sequel, prequel, etc.).

    Attributes:
        id: AniList ID
        type: Media type (ANIME, MANGA)
        title: Title object
        episodes: Total episodes
    """

    id: int = Field(..., description="AniList ID")
    type: str = Field(..., description="Media type")
    title: AniListTitle = Field(..., description="Title object")
    episodes: int | None = Field(None, description="Total episodes")


class AniListRelationEdge(BaseModel):
    """AniList relation edge.

    Attributes:
        relationType: Type of relation (SEQUEL, PREQUEL, etc.)
        node: Related anime node
    """

    relationType: str = Field(..., description="Relation type")
    node: AniListRelationNode = Field(..., description="Related anime")


# Episode and Search Models
class EpisodeContext(BaseModel):
    """Episode context for next episode navigation.

    Attributes:
        url: Episode URL
        title: Episode title
        episode: Episode number (1-indexed)
        total: Total episodes
    """

    url: str = Field(..., min_length=1, description="Episode URL")
    title: str = Field(..., min_length=1, description="Episode title")
    episode: int = Field(..., ge=1, description="Episode number (1-indexed)")
    total: int = Field(..., ge=1, description="Total episodes")


class SearchMetadata(BaseModel):
    """Search metadata from repository.

    Attributes:
        original_query: The full query user typed
        used_query: The actual query used (after reduction)
        used_words: Number of words used in final search
        total_words: Total number of words in original query
        min_words: Minimum word limit (from config)
        variant_tested: Title variation that was tested
        variant_index: Index of the variation tested
        total_variants: Total number of variations available
        source: Source of the search (cache or scraper)
    """

    original_query: str | None = None
    used_query: str | None = None
    used_words: int | None = None
    total_words: int | None = None
    min_words: int | None = None
    variant_tested: str | None = None
    variant_index: int | None = None
    total_variants: int | None = None
    source: str | None = None


# Cache Models
class ScraperCacheData(BaseModel):
    """Scraper cache data structure.

    Attributes:
        episode_urls: List of episode URLs
        episode_count: Number of episodes
        timestamp: Cache timestamp (legacy, not used in new system)
    """

    episode_urls: list[str] = Field(..., description="Episode URLs")
    episode_count: int = Field(..., ge=0, description="Number of episodes")
    timestamp: int = Field(default=0, description="Cache timestamp (legacy)")


class CacheStats(BaseModel):
    """Cache statistics.

    Attributes:
        size: Cache size
        total_items: Total number of items in cache
    """

    size: int = Field(..., ge=0, description="Cache size")
    total_items: int = Field(..., ge=0, description="Total items")


# Plugin Models
class PluginPreferences(BaseModel):
    """Plugin preferences configuration.

    Attributes:
        disabled_plugins: List of disabled plugin names
    """

    disabled_plugins: list[str] = Field(default_factory=list, description="Disabled plugins")


class Status(str, Enum):
    CURRENT = "CURRENT"
    PLANNING = "PLANNING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    DROPPED = "DROPPED"
    REPEATING = "REPEATING"


# ============================================================================
# IMMUTABLE DATA STRUCTURES (Phase 2 - C3)
# ============================================================================
# These frozen Pydantic models enforce Immutable Data Flow principle from CLAUDE.md
# Services return new immutable values, never mutate state


class AnimeSearchResult(BaseModel, frozen=True):
    """Immutable anime search result.

    Represents one anime found across one or more sources.
    Cannot be modified after creation (frozen=True Pydantic model).

    Attributes:
        title: Human-readable anime title
        normalized_title: Normalized title for deduplication
        sources: Immutable tuple of (url, source_name, params) tuples
    """

    title: str = Field(..., min_length=1, description="Human-readable anime title")
    normalized_title: str = Field(
        ..., min_length=1, description="Normalized title for deduplication"
    )
    sources: tuple[tuple[str, str, dict], ...] = Field(
        ..., description="Tuple of (url, source_name, params) tuples"
    )

    @model_validator(mode="after")
    def validate_sources(self) -> "AnimeSearchResult":
        """Validate sources is not empty."""
        if not self.sources:
            raise ValueError("sources cannot be empty")
        return self


class SearchResults(BaseModel, frozen=True):
    """Immutable collection of anime search results.

    Returned by Repository.search_anime() instead of mutating repository state.
    Contains all search results + metadata.

    Attributes:
        query: Original search query
        results: Immutable tuple of AnimeSearchResult objects
        metadata: Search metadata (dict[str, Any])
    """

    query: str = Field(..., min_length=1, description="Original search query")
    results: tuple[AnimeSearchResult, ...] = Field(
        default_factory=tuple, description="Immutable tuple of AnimeSearchResult objects"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Search metadata")

    def get_anime_titles(self) -> list[str]:
        """Get list of anime titles from results.

        Returns:
            List of anime title strings
        """
        return [result.title for result in self.results]

    def get_anime_titles_with_sources(self) -> list[str]:
        """Get titles with source indicators.

        Returns:
            List of strings like "Anime Title [source1, source2]"
        """
        result_list = []
        for anime in self.results:
            sources = set(source for _url, source, _params in anime.sources)
            sources_str = ", ".join(sorted(sources))
            result_list.append(f"{anime.title} [{sources_str}]")
        return result_list

    def find_by_title(self, title: str) -> AnimeSearchResult | None:
        """Find anime by exact title match.

        Args:
            title: Anime title to search for

        Returns:
            AnimeSearchResult if found, None otherwise
        """
        for anime in self.results:
            if anime.title == title:
                return anime
        return None


class EpisodeList(BaseModel, frozen=True):
    """Immutable episode list for an anime.

    Stores episode metadata across multiple sources.

    Attributes:
        anime_title: Title of the anime
        episodes: Immutable tuple of (title, urls, source) tuples
    """

    anime_title: str = Field(..., min_length=1, description="Title of the anime")
    episodes: tuple[tuple[str, list[str], str], ...] = Field(
        default_factory=tuple, description="Immutable tuple of (title, urls, source) tuples"
    )

    def get_episode_titles(self) -> list[str]:
        """Get unified episode title list (from longest source).

        Returns:
            List of episode titles
        """
        if not self.episodes:
            return []
        # Return longest episode list (most complete source)
        longest_list = max([ep[1] for ep in self.episodes], key=len)
        return longest_list

    def get_episode_url(self, episode_num: int) -> tuple[str, str] | None:
        """Get episode URL and source name (1-indexed).

        Args:
            episode_num: Episode number (1-indexed, e.g., 1, 2, 3)

        Returns:
            Tuple of (url, source_name) or None if not found
        """
        for _title_list, url_list, source in self.episodes:
            if len(url_list) >= episode_num:
                return (url_list[episode_num - 1], source)
        return None


# ============================================================================
# ANIME DOWNLOAD MODELS (Phase 1 - Download Service)
# ============================================================================


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
    status: str = Field("success", description="Download status (success, failed, corrupted)")


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
