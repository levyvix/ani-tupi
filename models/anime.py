"""Anime, episode, search, and watch-history data models."""

from enum import Enum
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
        episode_numbers: List of episode numbers (normalized to int)
        episode_urls: List of episode URLs (must be http/https)
        source: Plugin source name
        season: Season number (1-indexed). Optional: defaults to 1.

    Validation:
        - episode_numbers and episode_urls must have same length
        - All episode URLs must be valid http(s) URLs
        - season must be positive integer
    """

    anime_title: str = Field(..., min_length=1, description="Anime title")
    episode_numbers: list[int] = Field(..., description="Episode numbers (normalized)")
    episode_urls: list[str] = Field(..., description="Episode URLs (must be http/https)")
    source: str = Field(..., min_length=1, description="Plugin source name")
    season: int = Field(default=1, ge=1, description="Season number (1-indexed)")

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
        if len(self.episode_numbers) != len(self.episode_urls):
            raise ValueError(
                f"Mismatched episodes: {len(self.episode_numbers)} numbers "
                f"vs {len(self.episode_urls)} URLs"
            )
        return self


class ScrapedEpisodes(BaseModel):
    """Raw episode batch returned by a scraper plugin.

    Plugins are pure adapters: ``search_episodes`` returns these batches instead
    of mutating the repository. The episode repository normalizes raw ``titles``
    to episode numbers and registers the data.

    Attributes:
        titles: Raw episode labels from the scraper (e.g. "Episódio 1")
        urls: Episode URLs, aligned 1:1 with ``titles``
        source: Plugin source name
        season: Season number (1-indexed); 1 lets the repository infer it
    """

    titles: list[str]
    urls: list[str]
    source: str
    season: int = 1


class AnimeTitleResolution(BaseModel, frozen=True):
    """Resolved title used to retry manual anime searches conservatively."""

    original_query: str = Field(..., min_length=1, description="Original user query")
    resolved_title: str = Field(..., min_length=1, description="Canonical title for re-search")
    provider: str = Field(..., min_length=1, description="Provider name used for resolution")
    confidence: int = Field(..., ge=0, le=100, description="Confidence score for the match")
    aliases: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Useful aliases returned by the provider",
    )


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
        source: Source of the search (cache, scraper, or mixed)
        cache_hit: Whether results came from cache
        cache_age_seconds: Age of cached result in seconds (None if not from cache)
        scraper_sources: List of scraper names that provided results
        cache_check_time_ms: Time taken to check cache (milliseconds)
        scraper_execution_time_ms: Time taken to execute scrapers (milliseconds)
        total_execution_time_ms: Total time for the search (milliseconds)
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
    cache_hit: bool | None = None
    cache_age_seconds: int | None = None
    scraper_sources: list[str] = Field(
        default_factory=list, description="List of scrapers that provided results"
    )
    cache_check_time_ms: int = Field(
        default=0, ge=0, description="Cache check time in milliseconds"
    )
    scraper_execution_time_ms: int = Field(
        default=0, ge=0, description="Scraper execution time in milliseconds"
    )
    total_execution_time_ms: int = Field(
        default=0, ge=0, description="Total execution time in milliseconds"
    )


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
        default_factory=tuple,
        description="Immutable tuple of AnimeSearchResult objects",
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


class HistoryEntry(BaseModel):
    """Watch history entry. Serializes as list for JSON backward compat.

    JSON list format: [timestamp, episode_idx, anilist_id, source, total_episodes, urls]
    """

    timestamp: int
    episode_idx: int
    anilist_id: int | None = None
    source: str | None = None
    total_episodes: int | None = None
    urls: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_list(cls, data: list) -> "HistoryEntry":
        return cls(
            timestamp=data[0],
            episode_idx=data[1],
            anilist_id=data[2] if len(data) > 2 else None,
            source=data[3] if len(data) > 3 else None,
            total_episodes=data[4] if len(data) > 4 and data[4] else None,
            urls=data[5] if len(data) > 5 and isinstance(data[5], dict) else {},
        )

    def to_list(self) -> list:
        return [
            self.timestamp,
            self.episode_idx,
            self.anilist_id,
            self.source,
            self.total_episodes,
            self.urls,
        ]
