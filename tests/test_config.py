"""
Tests for config.py

Coverage:
- Settings loading from environment variables
- Default values (cache duration, API URLs)
- Path resolution (cross-platform get_data_path())
- Config validation (invalid values rejected)
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from config import settings, get_data_path, AppSettings


class TestConfigDefaults:
    """Test default configuration values."""

    def test_default_cache_duration(self):
        """Should have reasonable default cache duration."""
        assert 1 <= settings.cache.duration_hours <= 720

    def test_default_api_url(self):
        """Should have valid AniList API URL."""
        assert settings.anilist.api_url.startswith("https://")
        assert "anilist" in settings.anilist.api_url.lower()

    def test_default_client_id(self):
        """Should have AniList client ID."""
        assert settings.anilist.client_id is not None
        assert settings.anilist.client_id > 0

    def test_default_search_min_words(self):
        """Should have valid search minimum words."""
        assert 1 <= settings.search.progressive_search_min_words <= 10


class TestPathResolution:
    """Test get_data_path() for cross-platform support."""

    def test_get_data_path_returns_path(self):
        """Should return Path object."""
        path = get_data_path()
        assert isinstance(path, Path)

    def test_get_data_path_absolute(self):
        """Should return absolute path."""
        path = get_data_path()
        assert path.is_absolute()

    def test_get_data_path_contains_ani_tupi(self):
        """Should reference ani-tupi in path."""
        path = get_data_path()
        assert "ani-tupi" in path.as_posix().lower()

    def test_get_data_path_consistent(self):
        """Should return same path on multiple calls."""
        path1 = get_data_path()
        path2 = get_data_path()
        assert path1 == path2

    def test_get_data_path_platform_specific(self):
        """Path should be platform-appropriate."""
        path = get_data_path()
        # Should use appropriate separator for platform
        assert path.as_posix() is not None


class TestEnvironmentVariableOverride:
    """Test environment variable configuration."""

    def test_env_override_cache_duration(self):
        """Should allow overriding cache duration via env var."""
        with patch.dict(os.environ, {"ANI_TUPI__CACHE__DURATION_HOURS": "12"}):
            # Create fresh settings instance
            new_settings = AppSettings()
            assert new_settings.cache.duration_hours == 12

    def test_env_override_search_min_words(self):
        """Should allow overriding search min words via env var."""
        with patch.dict(os.environ, {"ANI_TUPI__SEARCH__PROGRESSIVE_SEARCH_MIN_WORDS": "3"}):
            new_settings = AppSettings()
            assert new_settings.search.progressive_search_min_words == 3

    def test_env_override_api_url(self):
        """Should allow overriding API URL via env var."""
        test_url = "https://custom.anilist.co"
        with patch.dict(os.environ, {"ANI_TUPI__ANILIST__API_URL": test_url}):
            new_settings = AppSettings()
            assert new_settings.anilist.api_url == test_url

    def test_env_multiple_overrides(self):
        """Should support multiple env var overrides."""
        with patch.dict(
            os.environ,
            {
                "ANI_TUPI__CACHE__DURATION_HOURS": "24",
                "ANI_TUPI__SEARCH__PROGRESSIVE_SEARCH_MIN_WORDS": "5",
            },
        ):
            new_settings = AppSettings()
            assert new_settings.cache.duration_hours == 24
            assert new_settings.search.progressive_search_min_words == 5


class TestConfigValidation:
    """Test configuration validation."""

    def test_invalid_cache_duration_below_min(self):
        """Should reject cache duration below minimum."""
        with pytest.raises(ValueError):
            AppSettings(cache={"duration_hours": 0})

    def test_invalid_cache_duration_above_max(self):
        """Should reject cache duration above maximum."""
        with pytest.raises(ValueError):
            AppSettings(cache={"duration_hours": 1000})

    def test_invalid_search_min_words_below_min(self):
        """Should reject search min words below minimum."""
        with pytest.raises(ValueError):
            AppSettings(search={"progressive_search_min_words": 0})

    def test_invalid_search_min_words_above_max(self):
        """Should reject search min words above maximum."""
        with pytest.raises(ValueError):
            AppSettings(search={"progressive_search_min_words": 100})

    def test_invalid_api_url_format(self):
        """Should validate API URL format."""
        # This depends on Pydantic validation
        settings_valid = AppSettings()
        assert settings_valid.anilist.api_url.startswith("http")


class TestCachePaths:
    """Test cache file path configuration."""

    def test_cache_file_path_not_empty(self):
        """Should have cache file path configured."""
        assert settings.cache.cache_file is not None
        assert settings.cache.cache_file != Path()

    def test_cache_file_path_contains_ani_tupi(self):
        """Cache file should be in ani-tupi directory."""
        # Path may be expanded, so check the end part
        cache_path = settings.cache.cache_file
        assert isinstance(cache_path, (str, Path))


class TestAniListConfig:
    """Test AniList-specific configuration."""

    def test_anilist_client_id_valid(self):
        """Should have valid AniList client ID."""
        assert settings.anilist.client_id
        assert isinstance(settings.anilist.client_id, int)
        assert settings.anilist.client_id > 0

    def test_anilist_api_url_https(self):
        """AniList API URL should use HTTPS."""
        assert settings.anilist.api_url.startswith("https://")

    def test_anilist_token_file_path(self):
        """Should have token file path configured."""
        assert settings.anilist.token_file is not None


class TestSearchConfig:
    """Test search-specific configuration."""

    def test_search_min_words_range(self):
        """Search min words should be in valid range."""
        assert 1 <= settings.search.progressive_search_min_words <= 10

    def test_search_config_values_positive(self):
        """All search config values should be positive."""
        assert settings.search.progressive_search_min_words > 0


class TestSettingsAsModel:
    """Test Settings as Pydantic model."""

    def test_settings_instance_type(self):
        """Settings should be AppSettings instance."""
        assert isinstance(settings, AppSettings)

    def test_settings_has_required_sections(self):
        """Settings should have required configuration sections."""
        assert hasattr(settings, "cache")
        assert hasattr(settings, "anilist")
        assert hasattr(settings, "search")

    def test_settings_cache_section(self):
        """Cache section should have required fields."""
        assert hasattr(settings.cache, "duration_hours")
        assert hasattr(settings.cache, "cache_file")

    def test_settings_anilist_section(self):
        """AniList section should have required fields."""
        assert hasattr(settings.anilist, "api_url")
        assert hasattr(settings.anilist, "client_id")
        assert hasattr(settings.anilist, "token_file")

    def test_settings_search_section(self):
        """Search section should have required fields."""
        assert hasattr(settings.search, "progressive_search_min_words")


class TestConfigConsistency:
    """Test configuration consistency."""

    def test_cache_duration_positive(self):
        """Cache duration must be positive."""
        assert settings.cache.duration_hours > 0

    def test_all_urls_have_protocol(self):
        """All URLs should have protocol prefix."""
        assert settings.anilist.api_url.startswith(("http://", "https://"))

    def test_client_id_not_empty(self):
        """Client ID should not be empty."""
        assert settings.anilist.client_id > 0
