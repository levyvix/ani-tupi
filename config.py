"""Application configuration using Pydantic v2.

Centralized settings for ani-tupi including:
- API endpoints and credentials
- Cache settings
- Search and fuzzy matching thresholds
- OS-specific data paths

Configuration can be overridden via environment variables:
    ANI_TUPI__ANILIST__CLIENT_ID=12345
    ANI_TUPI__CACHE__DURATION_HOURS=12
    ANI_TUPI__SEARCH__FUZZY_THRESHOLD=95
"""

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_data_path() -> Path:
    """Get OS-specific data directory for ani-tupi.

    Returns:
        Path: ~/.local/state/ani-tupi (Linux/macOS) or C:\\Program Files\\ani-tupi (Windows)
    """
    if os.name == "nt":
        return Path("C:\\Program Files\\ani-tupi")
    return Path.home() / ".local" / "state" / "ani-tupi"


class AniListSettings(BaseModel):
    """AniList API configuration."""

    api_url: str = Field(
        "https://graphql.anilist.co",
        description="AniList GraphQL API endpoint",
    )
    auth_url: str = Field(
        "https://anilist.co/api/v2/oauth/authorize",
        description="OAuth authorization URL",
    )
    client_id: int = Field(
        20148,
        gt=0,
        description="OAuth client ID (public)",
    )
    token_file: Path = Field(
        default_factory=lambda: get_data_path() / "anilist_token.json",
        description="Path to stored access token",
    )


class CacheSettings(BaseModel):
    """Scraper cache configuration."""

    duration_hours: int = Field(
        6,
        ge=1,
        le=72,
        description="Cache validity duration in hours",
    )
    cache_file: Path = Field(
        default_factory=lambda: get_data_path() / "scraper_cache.json",
        description="Path to cache storage file",
    )


class SearchSettings(BaseModel):
    """Anime search and fuzzy matching configuration."""

    fuzzy_threshold: int = Field(
        90,
        ge=0,
        le=100,
        description="Fuzzy matching threshold for deduplication (0-100)",
    )
    min_score: int = Field(
        70,
        ge=0,
        le=100,
        description="Minimum relevance score for search results (0-100)",
    )
    progressive_search_min_words: int = Field(
        2,
        ge=1,
        le=10,
        description="Minimum words to use in progressive search",
    )


class AppSettings(BaseSettings):
    """Root application settings with environment variable support.

    Environment variables use the prefix ANI_TUPI__ with nested delimiters:
    - ANI_TUPI__ANILIST__CLIENT_ID=12345
    - ANI_TUPI__CACHE__DURATION_HOURS=12
    - ANI_TUPI__SEARCH__FUZZY_THRESHOLD=95

    Can also be configured via .env file in project root.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",  # ANI_TUPI__ANILIST__CLIENT_ID
        env_prefix="ANI_TUPI__",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars
    )

    anilist: AniListSettings = Field(default_factory=AniListSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)


# Singleton instance - import and use throughout the app
settings = AppSettings()
