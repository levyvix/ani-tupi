"""Application configuration using Pydantic v2.

Centralized settings for ani-tupi including:
- API endpoints and credentials
- Cache settings
- Search configuration
- OS-specific data paths

Configuration can be overridden via environment variables:
    ANI_TUPI__ANILIST__CLIENT_ID=12345
    ANI_TUPI__CACHE__DURATION_HOURS=12
    ANI_TUPI__SEARCH__PROGRESSIVE_SEARCH_MIN_WORDS=2
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
        38122,
        gt=0,
        description="OAuth client ID (public)",
    )
    token_file: Path = Field(
        default_factory=lambda: get_data_path() / "anilist_token.json",
        description="Path to stored access token",
    )
    prefer_english_title: bool = Field(
        False,
        description="Use English title for searches (True) or Romaji (False)",
    )
    manga_prefer_english_title: bool = Field(
        False,
        description="Use English title for manga searches (True) or Romaji (False)",
    )
    manga_auto_sync: bool = Field(
        True,
        description="Automatically sync manga progress with AniList when confirmed",
    )
    manga_progress_confirmation: bool = Field(
        True,
        description="Ask for chapter completion confirmation after reading",
    )


class CacheSettings(BaseModel):
    """Unified cache configuration with TTL and refresh options."""

    cache_dir: Path = Field(
        default_factory=lambda: get_data_path() / "cache",
        description="Path to cache directory (unified backends)",
    )
    anilist_auto_discover: bool = Field(
        True,
        description="Auto-discover AniList ID for manual searches via fuzzy matching",
    )
    anilist_fuzzy_threshold: int = Field(
        90,
        ge=70,
        le=100,
        description="Minimum fuzzy match score (0-100) for AniList ID auto-discovery",
    )
    episodes_cache_enabled: bool = Field(
        False,
        description="Enable episodes cache (disabled by default due to new episode needed to be fetched)",
    )
    # TTL Configuration
    search_cache_ttl_seconds: int = Field(
        3600,
        ge=60,
        description="Time-to-live for search results cache in seconds (default: 1 hour)",
    )
    episodes_cache_ttl_seconds: int = Field(
        1800,
        ge=60,
        description="Time-to-live for episode lists cache in seconds (default: 30 minutes)",
    )
    video_url_cache_ttl_seconds: int = Field(
        7200,
        ge=60,
        description="Time-to-live for video URLs cache in seconds (default: 2 hours)",
    )
    cache_max_size_bytes: int = Field(
        50 * 1024 * 1024,  # 50 MB
        ge=1_000_000,
        description="Maximum cache size in bytes before LRU eviction (default: 50 MB)",
    )
    # Background refresh configuration
    background_refresh_enabled: bool = Field(
        False,
        description="Enable background refresh of stale cache entries (default: disabled for conservative behavior)",
    )
    background_refresh_threshold_seconds: int = Field(
        2700,  # 45 minutes
        ge=60,
        description="Threshold for background refresh: refresh cache older than this (seconds)",
    )
    background_refresh_max_workers: int = Field(
        2,
        ge=1,
        le=16,
        description="Maximum parallel background refresh workers",
    )


class SearchSettings(BaseModel):
    """Anime search configuration."""

    progressive_search_min_words: int = Field(
        1,  # Changed from 2 to support single-word anime like "Dandadan"
        ge=1,
        description="Minimum words to use in progressive search",
    )
    top_results_limit: int = Field(
        10,
        ge=5,
        le=50,
        description="Maximum results to show initially (before 'Show all' button)",
    )
    preferred_audio: str = Field(
        "dublado",
        pattern="^(dublado|legendado)$",
        description="Preferred audio type for AnimesDigital: 'dublado' or 'legendado'",
    )


class PluginSettings(BaseModel):
    """Plugin/scraper management settings."""

    disabled_plugins: list[str] = Field(
        default_factory=list,
        description="List of disabled plugin names (e.g., ['animesonlinecc'])",
    )
    priority_order: list[str] = Field(
        default_factory=lambda: [
            "dattebayo",
            "animesdigital",
            "animefire",
            "anitube",
            "animesonlinecc",
        ],
        description="Priority order for scraper sources (first = highest priority)",
    )


class PerformanceSettings(BaseModel):
    """Performance optimization settings for scrapers."""

    # HTTP Client Settings
    http_timeout: int = Field(
        15,
        ge=5,
        le=60,
        description="Default timeout for HTTP requests (seconds)",
    )
    http_pool_connections: int = Field(
        10,
        ge=5,
        le=50,
        description="Number of connection pools to cache",
    )
    http_pool_maxsize: int = Field(
        20,
        ge=10,
        le=100,
        description="Maximum connections per pool",
    )
    http_retry_attempts: int = Field(
        3,
        ge=1,
        le=5,
        description="Number of retry attempts for failed HTTP requests",
    )

    # Cache Settings (additional to existing cache settings)
    search_cache_ttl: int = Field(
        300,
        ge=60,
        le=1800,
        description="TTL for search results cache (seconds, 5 minutes default)",
    )
    episodes_cache_ttl: int = Field(
        1800,
        ge=300,
        le=3600,
        description="TTL for episode list cache (seconds, 30 minutes default)",
    )
    video_url_cache_ttl_seconds: int = Field(
        3600,
        ge=300,
        le=86400,
        description="TTL for video URL cache (seconds, 1 hour default)",
    )
    smart_cache_max_size_mb: int = Field(
        100,
        ge=50,
        le=500,
        description="Maximum size of smart cache (MB)",
    )

    # Unified Cache Settings
    cache_type: str = Field(
        "disk",
        description="Cache backend: memory, disk, or hybrid",
    )

    # Consolidated Cache TTL Settings (replaces duplicate duration_hours fields)
    default_ttl_hours: int = Field(
        168,
        ge=1,
        le=720,
        description="Default cache TTL in hours (7 days, max 30 days)",
    )
    source_ttls: dict[str, int] = Field(
        default_factory=lambda: {
            "search": 5,  # 5 minutes for search results
            "episodes": 30,  # 30 minutes for episode lists
            "video": 15,  # 15 minutes for video URLs (expire quickly)
            "manga": 24,  # 24 hours for manga chapters
            "anilist_meta": 720,  # 30 days for AniList metadata
        },
        description="Source-specific TTL in hours",
    )


class AnimeDownloadSettings(BaseModel):
    """Anime download and local library settings."""

    download_directory: Path = Field(
        default_factory=lambda: Path.home() / ".local" / "share" / "ani-tupi" / "anime",
        description="Where to save downloaded anime episodes",
    )
    max_parallel_downloads: int = Field(
        3,
        ge=1,
        le=16,
        description="Maximum parallel episode downloads (1 = sequential, 16 = max)",
    )
    video_format: str = Field(
        "mkv",
        description="Default video format for downloads (mkv, mp4, etc)",
    )
    skip_already_downloaded: bool = Field(
        True,
        description="Skip already-downloaded episodes in batch operations",
    )
    skip_intros: bool = Field(
        True,
        description="Enable automatic skipping of anime intros (OP) and outros (ED) via AniSkip API",
    )


class OfflineSyncConfig(BaseModel):
    """Configuration for offline AniList sync queue."""

    max_retry_count: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retries before giving up on failed sync",
    )
    enable_auto_retry: bool = Field(
        default=True,
        description="Automatically retry offline syncs on app startup",
    )
    enable_file_cleanup: bool = Field(
        default=True,
        description="Automatically delete local episode files after successful sync",
    )
    delete_after_watch: bool = Field(
        default=True,
        description="Delete local files after watching (regardless of AniList sync)",
    )


class MangaSettings(BaseModel):
    """Manga reader settings with multi-source support."""

    api_url: str = Field(
        "https://api.mangadex.org",
        description="MangaDex API base URL",
    )

    output_directory: Path = Field(
        default_factory=lambda: Path.home() / ".manga_tupi",
        description="Where to save downloaded manga chapters",
    )
    languages: list[str] = Field(
        default_factory=lambda: ["pt-br", "en"],
        description="Preferred languages in order (pt-br, en, ja, etc)",
    )
    preferred_sources: list[str] = Field(
        default_factory=lambda: ["mangalivre", "mugiwaras", "mangadex"],
        description="Preferred manga sources in priority order",
    )
    pdf_reader: str | None = Field(
        None,
        description="PDF reader to use (zathura, evince, okular, mupdf). None = auto-detect",
    )
    pdf_reader_priority: list[str] = Field(
        default_factory=lambda: ["zathura", "evince", "okular", "mupdf", "xdg-open"],
        description="Priority list for PDF reader auto-detection",
    )
    delete_images_after_pdf: bool = Field(
        True,
        description="Delete PNG images after PDF creation (keeps only PDF)",
    )
    pdf_quality: int = Field(
        85,
        ge=1,
        le=100,
        description="JPEG quality for images inside PDF (0-100, lower = smaller file)",
    )
    auto_create_pdf: bool = Field(
        True,
        description="Automatically create PDF after downloading images",
    )
    zathura_auto_config: bool = Field(
        True,
        description="Automatically configure Zathura for fit-width zoom",
    )
    # Download for later settings
    default_download_range: int = Field(
        5,
        ge=1,
        le=100,
        description="Default chapters to download when user selects 'download'",
    )
    auto_open_after_download: bool = Field(
        False,
        description="Auto-open PDF reader after downloading (False = stay in menu)",
    )
    skip_already_downloaded: bool = Field(
        True,
        description="Skip already-downloaded chapters in batch operations",
    )
    download_storage_dir: str | None = Field(
        None,
        description="Custom directory for downloaded PDFs (None = use output_directory)",
    )
    auto_delete_read_chapters: bool = Field(
        True,
        description="Automatically delete chapter files after marking as read (saves disk space)",
    )
    debug_download_failures: bool = Field(
        False,
        description="Enable detailed logging for download failures (helps debug issues)",
    )
    max_parallel_downloads: int = Field(
        0,
        ge=0,
        le=16,
        description="Maximum parallel chapter downloads (0 = use CPU count, 1 = sequential)",
    )


class AiringSettings(BaseModel):
    """Settings for airing episodes feature."""

    grace_period_days: int = Field(
        60,
        ge=1,
        le=365,
        description="Days after a show finishes airing to keep it visible in the New Episodes tab (default: 60)",
    )


class AppSettings(BaseSettings):
    """Root application settings with environment variable support.

    Environment variables use the prefix ANI_TUPI__ with nested delimiters:
    - ANI_TUPI__ANILIST__CLIENT_ID=12345
    - ANI_TUPI__CACHE__DURATION_HOURS=12
    - ANI_TUPI__SEARCH__PROGRESSIVE_SEARCH_MIN_WORDS=2

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

    anilist: AniListSettings = AniListSettings()  # type: ignore[call-arg]
    cache: CacheSettings = CacheSettings()  # type: ignore[call-arg]
    search: SearchSettings = SearchSettings()  # type: ignore[call-arg]
    plugins: PluginSettings = PluginSettings()  # type: ignore[call-arg]
    anime_download: AnimeDownloadSettings = AnimeDownloadSettings()  # type: ignore[call-arg]
    offline_sync: OfflineSyncConfig = OfflineSyncConfig()  # type: ignore[call-arg]
    manga: MangaSettings = MangaSettings()  # type: ignore[call-arg]
    performance: PerformanceSettings = PerformanceSettings()  # type: ignore[call-arg]
    airing: AiringSettings = AiringSettings()  # type: ignore[call-arg]


# Singleton instance - import and use throughout the app
settings = AppSettings()
