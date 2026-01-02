"""Custom exception hierarchy for ani-tupi application.

Provides specific exception types for different failure scenarios,
making error handling more precise and testable.
"""


class AniTupiError(Exception):
    """Base exception for all ani-tupi errors."""

    pass


class ScraperError(AniTupiError):
    """Raised when a scraper plugin fails to execute."""

    pass


class ScraperNotFoundError(ScraperError):
    """Raised when a requested scraper/plugin is not available."""

    pass


class CacheError(AniTupiError):
    """Raised when cache operations fail."""

    pass


class PersistenceError(AniTupiError):
    """Raised when JSON file I/O operations fail."""

    pass


class VideoPlaybackError(AniTupiError):
    """Raised when video playback fails."""

    pass


class AniListError(AniTupiError):
    """Raised when AniList API operations fail."""

    pass


class ConfigError(AniTupiError):
    """Raised when configuration is invalid or missing."""

    pass
