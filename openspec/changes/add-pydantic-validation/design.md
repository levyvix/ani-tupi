# Design: Pydantic Validation Architecture

**Change ID:** `add-pydantic-validation`

**Status:** Proposed Design

**Last Updated:** 2025-12-31

## Overview

This design introduces Pydantic v2 for runtime type validation and centralized configuration management across the ani-tupi codebase. The goal is to eliminate magic numbers, consolidate scattered configuration, and add type safety without breaking existing functionality.

## Architecture Decisions

### 1. Configuration Hierarchy

**Decision**: Use nested Pydantic `BaseSettings` models with environment variable support

**Rationale**:
- Separates concerns (AniList, cache, search settings are independent)
- Supports environment-based overrides (dev vs production)
- Maintains type safety across all config access
- Self-documenting through Pydantic field descriptions

**Structure**:
```
AppSettings (root)
├── AniListSettings (anilist.*)
│   ├── api_url
│   ├── client_id
│   └── token_file
├── CacheSettings (cache.*)
│   ├── duration_hours
│   └── cache_file
└── SearchSettings (search.*)
    ├── fuzzy_threshold
    ├── min_score
    └── progressive_search_min_words
```

**Environment Variable Mapping**:
```bash
ANI_TUPI__ANILIST__API_URL="https://graphql.anilist.co"
ANI_TUPI__CACHE__DURATION_HOURS=12
ANI_TUPI__SEARCH__FUZZY_THRESHOLD=95
```

**Trade-offs**:
- ✅ Clear organization by domain
- ✅ Easy to extend (add new setting sections)
- ❌ Nested access requires more typing (`settings.anilist.api_url`)
- Mitigation: Autocomplete makes this trivial

### 2. Path Resolution Strategy

**Decision**: Centralize OS-specific path logic in `get_data_path()` helper

**Current State** (duplicated across 3 files):
```python
# main.py, anilist_menu.py, scraper_cache.py
HISTORY_PATH = (
    Path.home() / ".local/state/ani-tupi"
    if name != "nt"
    else Path("C:\\Program Files\\ani-tupi")
)
```

**New Design**:
```python
# config.py
def get_data_path() -> Path:
    """Get OS-specific data directory for ani-tupi.

    Returns:
        ~/.local/state/ani-tupi (Linux/macOS)
        C:\\Program Files\\ani-tupi (Windows)
    """
    if os.name == "nt":
        return Path("C:\\Program Files\\ani-tupi")
    return Path.home() / ".local" / "state" / "ani-tupi"
```

**Usage**:
```python
# anilist.py
from config import settings

# Token file path now comes from config
token_file = settings.anilist.token_file  # auto-resolved to correct OS path

# scraper_cache.py
cache_file = settings.cache.cache_file
```

**Rationale**:
- Single source of truth for path resolution
- Easy to test (mock `os.name` in unit tests)
- Portable across platforms
- Future-proof for additional platforms (BSD, etc.)

**Trade-offs**:
- ✅ DRY principle (no duplication)
- ✅ Testable
- ❌ Adds indirection (import required)
- Mitigation: Config module is lightweight, always safe to import

### 3. Validation Strategy

**Decision**: Fail-fast on startup with clear error messages

**Approach**:
```python
# config.py
class SearchSettings(BaseModel):
    fuzzy_threshold: int = Field(98, ge=0, le=100, description="Fuzzy matching threshold (0-100)")
    min_score: int = Field(70, ge=0, le=100, description="Minimum relevance score")

    @field_validator('fuzzy_threshold')
    @classmethod
    def validate_threshold(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError(f"fuzzy_threshold must be 0-100, got {v}")
        return v
```

**Error Example**:
```python
# Invalid config
ANI_TUPI__SEARCH__FUZZY_THRESHOLD=150

# Result on startup:
ValidationError: 1 validation error for AppSettings
search.fuzzy_threshold
  Input should be less than or equal to 100 [type=less_than_equal, input_value=150, input_type=int]
```

**Rationale**:
- Errors caught immediately on application start (not during runtime)
- Clear, actionable error messages guide users to fix config
- No silent failures or cryptic exceptions later
- Aligns with "fail-fast" principle

**Trade-offs**:
- ✅ Clear error messages
- ✅ Prevents invalid state
- ❌ Crashes on startup if config invalid
- Mitigation: This is desirable behavior (invalid config should not run)

### 4. Data Transfer Objects (DTOs)

**Decision**: Define Pydantic models for structured data passed between layers

**Models**:

```python
# AnimeMetadata - replaces tuple (title, url, source, params)
class AnimeMetadata(BaseModel):
    title: str = Field(..., min_length=1, description="Anime title")
    url: str = Field(..., min_length=1, description="Anime URL from scraper")
    source: str = Field(..., min_length=1, description="Plugin source name")
    params: dict[str, Any] | None = Field(None, description="Extra params for scraper")

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(('http://', 'https://')):
            raise ValueError(f"URL must start with http:// or https://, got {v}")
        return v

# EpisodeData - replaces separate lists
class EpisodeData(BaseModel):
    anime_title: str
    episode_titles: list[str]
    episode_urls: list[str]
    source: str

    @model_validator(mode='after')
    def validate_lengths_match(self) -> 'EpisodeData':
        if len(self.episode_titles) != len(self.episode_urls):
            raise ValueError(
                f"Episode title count ({len(self.episode_titles)}) "
                f"must match URL count ({len(self.episode_urls)})"
            )
        return self

# SearchResult - structured repository response
class SearchResult(BaseModel):
    anime_titles: list[str]
    total_sources: int = Field(ge=0)

# VideoUrl - playback URL with optional headers
class VideoUrl(BaseModel):
    url: str
    headers: dict[str, str] | None = None

    @field_validator('url')
    @classmethod
    def validate_video_url(cls, v: str) -> str:
        # Accept m3u8 (HLS) or direct video URLs
        valid_extensions = ('.m3u8', '.mp4', '.mkv', '.avi', '.webm')
        if not any(v.endswith(ext) for ext in valid_extensions):
            # Log warning but don't fail (some sites have dynamic URLs)
            import warnings
            warnings.warn(f"Video URL may be invalid: {v}")
        return v
```

**Usage Example**:
```python
# OLD (repository.py)
def add_anime(self, title: str, url: str, source: str, params=None) -> None:
    # 4 separate arguments, no validation

# NEW
def add_anime(self, anime: AnimeMetadata) -> None:
    # Single validated object, type-safe
    # Can't pass invalid URL or empty title

# Plugin usage (OLD)
rep.add_anime(title, url, ExamplePlugin.name)

# Plugin usage (NEW)
rep.add_anime(AnimeMetadata(
    title=title,
    url=url,
    source=ExamplePlugin.name
))
```

**Rationale**:
- Type safety at layer boundaries (repository ↔ plugins, client ↔ API)
- Self-documenting (models show expected structure)
- Easier refactoring (IDE can track model changes)
- Prevents "tuple hell" (what's the 3rd argument again?)

**Trade-offs**:
- ✅ Explicit, self-documenting code
- ✅ IDE autocomplete for fields
- ❌ More verbose (object creation vs args)
- Mitigation: Verbosity aids clarity; worth the trade-off

### 5. Incremental Migration Strategy

**Decision**: Migrate in phases to minimize risk

**Phase Prioritization**:
1. **Config module** (foundation, no existing code broken)
2. **Repository layer** (most benefit, centralized validation)
3. **AniList client** (API boundary, structured responses)
4. **Cache & paths** (low-risk cleanup)
5. **Plugin interface** (last, touches multiple files)

**Migration Pattern**:
```python
# Step 1: Old code continues to work
def add_anime(self, title: str, url: str, source: str, params=None) -> None:
    anime = AnimeMetadata(title=title, url=url, source=source, params=params)
    # ... use anime object internally

# Step 2: Add new signature, keep old as wrapper
def add_anime(self, anime: AnimeMetadata | None = None,
              title: str | None = None, url: str | None = None,
              source: str | None = None, params=None) -> None:
    if anime is None:
        # Old-style call
        anime = AnimeMetadata(title=title, url=url, source=source, params=params)
    # ... use anime object

# Step 3: Deprecate old signature (future)
@deprecated("Use add_anime(AnimeMetadata(...)) instead")
def add_anime(self, title: str, url: str, source: str, params=None) -> None:
    ...

# Step 4: Remove old signature (after all callers updated)
def add_anime(self, anime: AnimeMetadata) -> None:
    ...
```

**Rationale**:
- Avoids "big bang" refactor
- Each phase can be tested independently
- Old code continues working during migration
- Can pause migration at any stable point

**Trade-offs**:
- ✅ Low risk of breaking changes
- ✅ Each phase delivers value
- ❌ Temporary dual signatures (complexity)
- Mitigation: Clear TODO comments mark temporary code

### 6. Testing Strategy

**Decision**: Focus on validation testing, not full integration tests

**Test Priorities**:
1. **Config validation**: Invalid values raise errors
2. **Path resolution**: Correct OS-specific paths
3. **Model validation**: DTOs reject invalid data
4. **Environment overrides**: Env vars work correctly

**Test Examples**:
```python
# Test config validation
def test_invalid_fuzzy_threshold():
    with pytest.raises(ValidationError):
        SearchSettings(fuzzy_threshold=150)

# Test path resolution
def test_data_path_windows(monkeypatch):
    monkeypatch.setattr('os.name', 'nt')
    assert get_data_path() == Path("C:\\Program Files\\ani-tupi")

def test_data_path_linux(monkeypatch):
    monkeypatch.setattr('os.name', 'posix')
    assert get_data_path() == Path.home() / ".local" / "state" / "ani-tupi"

# Test DTO validation
def test_anime_metadata_invalid_url():
    with pytest.raises(ValidationError):
        AnimeMetadata(title="Test", url="not-a-url", source="test")

def test_episode_data_length_mismatch():
    with pytest.raises(ValidationError):
        EpisodeData(
            anime_title="Test",
            episode_titles=["Ep1", "Ep2"],
            episode_urls=["url1"],  # Length mismatch!
            source="test"
        )
```

**Rationale**:
- Validation logic is core value of Pydantic
- Unit tests are fast and reliable
- Integration tests covered by manual testing (CLI flows)

**Trade-offs**:
- ✅ Fast, focused tests
- ✅ High coverage of validation logic
- ❌ Doesn't test end-to-end flows
- Mitigation: Manual testing covers E2E (existing practice)

## Implementation Details

### Config Module Structure

```python
# config.py
from pathlib import Path
from typing import Any
import os

from pydantic import BaseModel, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_data_path() -> Path:
    """Get OS-specific data directory."""
    if os.name == "nt":
        return Path("C:\\Program Files\\ani-tupi")
    return Path.home() / ".local" / "state" / "ani-tupi"


class AniListSettings(BaseModel):
    """AniList API configuration."""

    api_url: str = Field(
        "https://graphql.anilist.co",
        description="AniList GraphQL API endpoint"
    )
    auth_url: str = Field(
        "https://anilist.co/api/v2/oauth/authorize",
        description="OAuth authorization URL"
    )
    client_id: int = Field(
        20148,
        gt=0,
        description="OAuth client ID (public)"
    )
    token_file: Path = Field(
        default_factory=lambda: get_data_path() / "anilist_token.json",
        description="Path to stored access token"
    )


class CacheSettings(BaseModel):
    """Scraper cache configuration."""

    duration_hours: int = Field(
        6,
        ge=1,
        le=72,
        description="Cache validity duration in hours"
    )
    cache_file: Path = Field(
        default_factory=lambda: get_data_path() / "scraper_cache.json",
        description="Path to cache storage file"
    )


class SearchSettings(BaseModel):
    """Anime search and fuzzy matching configuration."""

    fuzzy_threshold: int = Field(
        98,
        ge=0,
        le=100,
        description="Fuzzy matching threshold for deduplication (0-100)"
    )
    min_score: int = Field(
        70,
        ge=0,
        le=100,
        description="Minimum relevance score for search results (0-100)"
    )
    progressive_search_min_words: int = Field(
        2,
        ge=1,
        le=10,
        description="Minimum words to use in progressive search"
    )


class AppSettings(BaseSettings):
    """Root application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_nested_delimiter='__',  # ANI_TUPI__ANILIST__CLIENT_ID
        env_prefix='ANI_TUPI__',
        case_sensitive=False,
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'  # Ignore unknown env vars
    )

    anilist: AniListSettings = Field(default_factory=AniListSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)


# Singleton instance
settings = AppSettings()
```

### Data Models Module

```python
# models.py (optional - could also live in config.py)
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator


class AnimeMetadata(BaseModel):
    """Anime metadata from scraper."""

    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    params: dict[str, Any] | None = None

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(('http://', 'https://')):
            raise ValueError(f"URL must be http(s), got: {v}")
        return v


class EpisodeData(BaseModel):
    """Episode list from scraper."""

    anime_title: str
    episode_titles: list[str]
    episode_urls: list[str]
    source: str

    @model_validator(mode='after')
    def validate_lengths(self) -> 'EpisodeData':
        if len(self.episode_titles) != len(self.episode_urls):
            raise ValueError(
                f"Mismatched episodes: {len(self.episode_titles)} titles "
                f"vs {len(self.episode_urls)} URLs"
            )
        return self


class SearchResult(BaseModel):
    """Repository search result."""

    anime_titles: list[str]
    total_sources: int = Field(ge=0)


class VideoUrl(BaseModel):
    """Video playback URL with headers."""

    url: str
    headers: dict[str, str] | None = None
```

## Migration Checklist (Reference for Implementation)

- [ ] Create `config.py` with all settings models
- [ ] Replace `ANILIST_API_URL` etc. in `anilist.py`
- [ ] Replace `CACHE_DURATION` in `scraper_cache.py`
- [ ] Replace duplicate `HISTORY_PATH` in `main.py`, `anilist_menu.py`
- [ ] Replace `threshold = 98` in `repository.py`
- [ ] Add `AnimeMetadata` model and update `add_anime()`
- [ ] Add `EpisodeData` model and update `add_episode_list()`
- [ ] Update plugin interface docstrings (no code changes needed)
- [ ] Add `.env.example` file
- [ ] Update documentation (README, CLAUDE.md)

## Alternative Designs Considered

### Alternative 1: TOML Configuration File

**Approach**: Use `config.toml` instead of environment variables

**Pros**:
- More user-friendly for non-technical users
- Easier to see all settings in one place
- Comments can explain each setting

**Cons**:
- Requires file parsing (add dependency)
- Harder to override in containers/CI
- Not as portable as env vars

**Decision**: Rejected. Environment variables are more flexible and align with 12-factor app principles. Can add TOML support later if requested.

### Alternative 2: Dataclasses Instead of Pydantic

**Approach**: Use Python 3.10+ `dataclasses` with manual validation

**Pros**:
- No external dependency
- Simpler mental model
- Faster (no Pydantic overhead)

**Cons**:
- No runtime validation
- No environment variable support
- Have to write all validation manually
- No nested model support

**Decision**: Rejected. Pydantic provides too much value (validation, env vars, nested models) to skip.

### Alternative 3: Global Constants Module

**Approach**: Create `constants.py` with all magic numbers, no Pydantic

**Pros**:
- Very simple
- No new dependencies
- Easy to understand

**Cons**:
- No validation
- No type safety
- No environment overrides
- Just moves problem, doesn't solve it

**Decision**: Rejected. This is a minimal improvement over current state.

## Risk Assessment

### High Risk Areas
- **Plugin interface changes**: Touches multiple files, could break scrapers
  - Mitigation: Make plugin changes last, test thoroughly

### Medium Risk Areas
- **Repository refactor**: Core logic, used everywhere
  - Mitigation: Keep old signatures during transition

### Low Risk Areas
- **Config module creation**: New code, no existing dependencies
- **Path consolidation**: Simple cleanup, easy to test
- **AniList client**: Self-contained, clear boundaries

## Performance Considerations

**Pydantic v2 Performance**:
- Validation is very fast (Rust core)
- ~5-50x faster than Pydantic v1
- Negligible overhead for our use case (CLI app, not high-throughput server)

**Config Loading**:
- Happens once on app startup
- Settings singleton cached for entire runtime
- No performance impact on hot paths

**Model Validation**:
- Only happens at layer boundaries (scraper → repository)
- Minimal overhead compared to network I/O (scraping)

**Conclusion**: Performance impact is negligible for this application.

## Open Questions

1. **Should we validate HTML scraping responses with Pydantic?**
   - Probably not - scrapers are brittle by nature
   - Focus validation on our own data structures

2. **Should config support JSON/YAML in addition to env vars?**
   - Start with env vars only
   - Add file support if users request it

3. **Should we add Pydantic models for curses UI data?**
   - No - UI layer doesn't need validation
   - Focus on business logic and data boundaries

## Future Enhancements

- Add `pydantic-ai` for AI-powered anime recommendations (if implemented)
- Use Pydantic's JSON Schema export for API documentation
- Add OpenAPI spec generation (if web API added)
- Validate MangaDex API responses with Pydantic models

---

**Design Status**: Ready for implementation

**Approver**: Awaiting user approval

**Next Step**: Review proposal.md and approve to begin implementation
