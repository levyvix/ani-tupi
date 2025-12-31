# Proposal: Add Pydantic Validation for Function Arguments, Returns, and Configuration

**Change ID:** `add-pydantic-validation`

**Status:** Proposal (awaiting approval)

**Proposed By:** User

**Date:** 2025-12-31

## Why

The current codebase has scattered magic numbers, hardcoded configuration values, and inconsistent function signatures that make the code harder to maintain and prone to errors:

1. **Magic Numbers**: Hardcoded values like `98` (fuzzy matching threshold), `6 * 60 * 60` (cache duration), `70` (minimum score), and `CLIENT_ID = 20148` are scattered throughout the code without type safety or validation
2. **Configuration Scattered Across Files**: API URLs, file paths, and thresholds are defined as module-level constants in different files with no central configuration
3. **Inconsistent Type Hints**: Some functions use type hints (`-> str | None`) while others don't, and there's no runtime validation of inputs
4. **Path Handling Complexity**: Multiple files duplicate the logic for determining OS-specific paths (`~/.local/state/ani-tupi` vs `C:\Program Files\ani-tupi`)
5. **No Input Validation**: Functions accept arbitrary values without validation (e.g., fuzzy thresholds could be -1 or 500)

Using Pydantic provides:
- **Type Safety**: Runtime validation of function arguments and return values
- **Centralized Configuration**: Single source of truth for all configurable values
- **Self-Documenting Code**: Pydantic models serve as living documentation
- **Better Error Messages**: Clear validation errors instead of silent failures or cryptic exceptions

## Summary

Introduce **Pydantic v2** for runtime type validation and centralized configuration management. Create typed models for:

1. **Configuration Settings** (`config.py`): Application-wide settings (API URLs, file paths, timeouts, thresholds)
2. **Function Arguments/Returns**: Plugin interface methods, repository methods, AniList client methods
3. **Data Transfer Objects**: Structured data passed between layers (anime metadata, episode data, search results)

This change maintains backward compatibility while adding validation and improving code clarity.

## Problem Statement

### Current Issues

1. **Magic Numbers Everywhere**:
   ```python
   # repository.py:102
   threshold = 98  # What is this? Why 98?

   # scraper_cache.py:15
   CACHE_DURATION = 6 * 60 * 60  # 6 hours - hardcoded

   # repository.py:109
   def get_anime_titles(self, filter_by_query: str = None, min_score: int = 70):
       # 70 - magic number, no validation
   ```

2. **Duplicated OS Path Logic**:
   ```python
   # main.py:15
   HISTORY_PATH = (
       Path.home() / ".local/state/ani-tupi"
       if name != "nt"
       else Path("C:\\Program Files\\ani-tupi")
   )

   # anilist_menu.py:16 - DUPLICATE
   HISTORY_PATH = (...)

   # scraper_cache.py:8 - DUPLICATE
   CACHE_FILE = (...)
   ```

3. **No Runtime Validation**:
   ```python
   def get_anime_titles(self, filter_by_query: str = None, min_score: int = 70):
       # min_score could be -1, 500, "hello" - no checks
   ```

4. **API Configuration Scattered**:
   ```python
   # anilist.py:13-15
   ANILIST_API_URL = "https://graphql.anilist.co"
   ANILIST_AUTH_URL = "https://anilist.co/api/v2/oauth/authorize"
   CLIENT_ID = 20148

   # Hard to override, test, or configure per environment
   ```

### Impact on Development

- **Testing**: Difficult to mock configurations or inject test values
- **Maintenance**: Changes to thresholds require searching the entire codebase
- **Debugging**: Magic numbers make it unclear what's being compared or why
- **Portability**: OS-specific logic duplicated instead of centralized

## Solution Overview

### Tech Stack (New)

- **Pydantic v2**: Schema validation and settings management
- **pydantic-settings**: Environment-based configuration loading

### Key Changes

1. **New Configuration Module** (`config.py`)
   - Centralized settings using `BaseSettings`
   - Environment variable support (`.env` file)
   - OS-aware path resolution (auto-detects Windows vs Linux/macOS)
   - Validation for all configurable values

2. **Pydantic Models for Data**
   - `AnimeMetadata`: Structured anime information (title, URL, source, params)
   - `EpisodeData`: Episode list data (titles, URLs, source)
   - `SearchResult`: Repository search results
   - `VideoUrl`: Video playback URL with headers

3. **Validated Function Signatures**
   - Repository methods use Pydantic models for arguments
   - AniList client returns validated models
   - Plugin interface updated with typed contracts

4. **Settings Structure**
   ```python
   class AniListSettings(BaseModel):
       api_url: HttpUrl = "https://graphql.anilist.co"
       client_id: int = Field(20148, gt=0)
       token_file: Path = Field(default_factory=lambda: get_data_path() / "anilist_token.json")

   class CacheSettings(BaseModel):
       duration_hours: int = Field(6, ge=1, le=72)
       cache_file: Path = Field(default_factory=lambda: get_data_path() / "scraper_cache.json")

   class SearchSettings(BaseModel):
       fuzzy_threshold: int = Field(98, ge=0, le=100)
       min_score: int = Field(70, ge=0, le=100)
       progressive_search_min_words: int = Field(2, ge=1, le=10)

   class AppSettings(BaseSettings):
       anilist: AniListSettings = Field(default_factory=AniListSettings)
       cache: CacheSettings = Field(default_factory=CacheSettings)
       search: SearchSettings = Field(default_factory=SearchSettings)

       model_config = SettingsConfigDict(
           env_nested_delimiter='__',  # ANI_TUPI__ANILIST__CLIENT_ID
           env_prefix='ANI_TUPI__',
           case_sensitive=False
       )
   ```

## Impact Analysis

### Benefits

- ✅ **Centralized Configuration**: Single source of truth in `config.py`
- ✅ **Runtime Validation**: Catch invalid values early with clear error messages
- ✅ **Type Safety**: IDE autocomplete and static analysis support
- ✅ **Environment Flexibility**: Override via `.env` file or environment variables
- ✅ **Self-Documenting**: Pydantic models serve as API documentation
- ✅ **Testability**: Easy to inject mock configurations for testing
- ✅ **Reduced Duplication**: OS path logic centralized in one place

### Trade-offs

- ❌ **Dependency Addition**: Adds `pydantic` and `pydantic-settings` dependencies
  - Mitigation: Pydantic is widely used, well-maintained, and adds ~1MB to package size
- ❌ **Migration Effort**: Need to update existing code to use new models
  - Mitigation: Can be done incrementally; old code continues to work during migration
- ❌ **Learning Curve**: Developers need to understand Pydantic syntax
  - Mitigation: Pydantic v2 has excellent docs; similar to dataclasses

### Affected Code

**New Files:**
- `config.py` - Centralized settings and configuration

**Modified Files:**
- `repository.py` - Use Pydantic models for method arguments/returns
- `anilist.py` - Load settings from config, validate GraphQL responses
- `scraper_cache.py` - Use config for cache settings
- `main.py` - Load app config on startup, remove duplicate path logic
- `anilist_menu.py` - Remove duplicate path constants
- `loader.py` - Plugin interface with validated signatures
- `pyproject.toml` - Add pydantic dependencies

**No Changes Needed:**
- `menu.py` - UI layer remains unchanged
- `video_player.py` - Simple subprocess wrapper, no validation needed
- Plugin files - Interface update only (implementation stays same)

### Dependencies

**Add:**
- `pydantic>=2.10.0`
- `pydantic-settings>=2.7.0`

**Rationale:**
- Pydantic v2 is 5-50x faster than v1 (Rust core)
- `pydantic-settings` handles `.env` loading and nested config
- Both libraries are industry-standard (100M+ downloads/month)

## Success Criteria

1. ✅ All magic numbers moved to centralized config
2. ✅ No duplicate OS path logic (single `get_data_path()` helper)
3. ✅ Repository methods validate input arguments at runtime
4. ✅ AniList client settings loaded from config
5. ✅ Configuration can be overridden via environment variables
6. ✅ Invalid config values raise clear `ValidationError` messages
7. ✅ All existing tests pass (after updating to use config)
8. ✅ Type hints on all public functions
9. ✅ Zero breaking changes to CLI interface

## Scope

### In Scope

- Create `config.py` with `AppSettings`, `AniListSettings`, `CacheSettings`, `SearchSettings`
- Define Pydantic models for: `AnimeMetadata`, `EpisodeData`, `SearchResult`, `VideoUrl`
- Update `repository.py` to validate fuzzy thresholds, min_score
- Update `anilist.py` to load API config from settings
- Update `scraper_cache.py` to use cache duration from config
- Remove duplicate `HISTORY_PATH` definitions
- Add type validation to `PluginInterface` methods
- Add environment variable documentation to README

### Out of Scope

- Validating HTML scraping responses (too brittle, sites change frequently)
- Database/ORM integration (no DB in current architecture)
- API response caching with Pydantic (separate concern)
- Migration of curses UI code (no validation needed)
- Backwards compatibility with Python <3.10 (Pydantic v2 requires 3.8+; we're on 3.12)

## Questions for Approval

1. **Environment Variables**: Should we support `.env` file for local dev, or only environment variables?
   - Recommendation: Support both (`.env` for dev, env vars for production)

2. **Validation Strictness**: Should invalid config values crash on startup or log warnings?
   - Recommendation: Crash on startup with clear error (fail-fast principle)

3. **Incremental Migration**: Should we validate all functions at once, or incrementally?
   - Recommendation: Incremental - start with config and repository, then expand

4. **Config File Location**: Should config also support TOML/YAML, or only env vars?
   - Recommendation: Start with env vars only; add file support if requested

## Next Steps

1. **Approval**: Review and approve this proposal
2. **Design Review**: Review `design.md` for architecture decisions
3. **Implementation**: Execute `tasks.md` sequentially
4. **Validation**: Run `openspec validate add-pydantic-validation --strict`
5. **Testing**: Manual testing + validation error scenarios
6. **Documentation**: Update README with environment variable examples
7. **Deployment**: Merge to `master` branch

---

**Estimated Scope**: Medium refactor (8-12 hours implementation + testing)

**Risk Level**: Low-Medium (no business logic changes, but touches multiple files)

**Rollback Plan**: If issues arise, revert to commit before merge; magic numbers still work without Pydantic
