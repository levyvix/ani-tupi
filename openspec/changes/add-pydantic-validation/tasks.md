# Tasks: Add Pydantic Validation

**Change ID:** `add-pydantic-validation`

**Status:** Completed

## Task Checklist

### Phase 1: Setup & Configuration Module (Foundation)

- [x] **T1.1**: Add Pydantic dependencies to `pyproject.toml`
  - Add `pydantic>=2.10.0`
  - Add `pydantic-settings>=2.7.0`
  - Run `uv sync` to install
  - **Validation**: `python -c "import pydantic; print(pydantic.VERSION)"` shows v2.x ✓ Verified Pydantic 2.12.5

- [x] **T1.2**: Create `config.py` with base settings structure
  - Create `config.py` at project root
  - Define `get_data_path()` helper (replaces duplicate HISTORY_PATH logic)
  - Implement OS detection (Windows vs Linux/macOS)
  - **Validation**: `python -c "from config import get_data_path; print(get_data_path())"` returns correct path ✓ Verified

- [x] **T1.3**: Define `AniListSettings` model in `config.py`
  - Fields: `api_url`, `auth_url`, `token_url`, `client_id`, `token_file`
  - Add `HttpUrl` validation for URLs
  - Add `Field` constraints (e.g., `client_id > 0`)
  - **Validation**: Instantiate `AniListSettings()` without errors ✓ Verified

- [x] **T1.4**: Define `CacheSettings` model in `config.py`
  - Fields: `duration_hours`, `cache_file`
  - Add constraints: `duration_hours` between 1-72
  - **Validation**: `CacheSettings(duration_hours=100)` raises ValidationError ✓ Verified

- [x] **T1.5**: Define `SearchSettings` model in `config.py`
  - Fields: `fuzzy_threshold`, `min_score`, `progressive_search_min_words`
  - Add constraints: all values 0-100 where applicable
  - **Validation**: Invalid threshold raises clear error ✓ Verified

- [x] **T1.6**: Create `AppSettings` root model with nested settings
  - Combine `AniListSettings`, `CacheSettings`, `SearchSettings`
  - Configure `SettingsConfigDict` with env prefix `ANI_TUPI__`
  - Support nested env vars: `ANI_TUPI__ANILIST__CLIENT_ID`
  - **Validation**: Set env var and confirm it overrides default ✓ Verified

- [x] **T1.7**: Add singleton `settings` instance in `config.py`
  - Create global `settings = AppSettings()`
  - Export for import: `from config import settings`
  - **Validation**: Import in REPL and access `settings.anilist.api_url` ✓ Verified

### Phase 2: Data Models (Type Safety)

- [x] **T2.1**: Define `AnimeMetadata` Pydantic model
  - Fields: `title: str`, `url: str`, `source: str`, `params: dict | None`
  - Add field validators (e.g., `url` must be non-empty)
  - **Validation**: Create instance with invalid URL, confirm error ✓ Verified

- [x] **T2.2**: Define `EpisodeData` Pydantic model
  - Fields: `anime_title: str`, `episode_titles: list[str]`, `episode_urls: list[str]`, `source: str`
  - Add validator: `len(episode_titles) == len(episode_urls)`
  - **Validation**: Mismatched lengths raise error ✓ Verified

- [x] **T2.3**: Define `SearchResult` model for repository results
  - Fields: `anime_titles: list[str]`, `total_sources: int`
  - **Validation**: Instantiate with sample data ✓ Verified

- [x] **T2.4**: Define `VideoUrl` model for playback URLs
  - Fields: `url: str`, `headers: dict[str, str] | None`
  - Add URL format validation
  - **Validation**: Create instance with m3u8 URL ✓ Verified

### Phase 3: Repository Migration (Core Logic)

- [x] **T3.1**: Update `repository.py` imports
  - Import `settings` from `config`
  - Import Pydantic models (`AnimeMetadata`, etc.)
  - **Validation**: No import errors ✓ Verified

- [x] **T3.2**: Replace magic numbers in `repository.py` with config values
  - Line 102: `threshold = 98` → `threshold = settings.search.fuzzy_threshold`
  - Line 109: `min_score: int = 70` → `min_score: int = settings.search.min_score`
  - Line 53: `min_words = 2` → `settings.search.progressive_search_min_words`
  - **Validation**: Search still works with same behavior ✓ Verified (already integrated)

- [x] **T3.3**: Update `add_anime()` to use `AnimeMetadata` model
  - Change signature: `add_anime(self, anime: AnimeMetadata) -> None`
  - Update callers to pass model instead of individual args
  - **Validation**: Plugins can still add anime without errors ✓ Verified

- [x] **T3.4**: Add input validation to `get_anime_titles()`
  - Validate `min_score` is 0-100
  - Raise `ValueError` with clear message if invalid
  - **Validation**: Call with `min_score=150` raises error ✓ Verified

- [x] **T3.5**: Update `add_episode_list()` to use `EpisodeData` model
  - Change signature to accept `EpisodeData` object
  - Validate episode count matches URL count
  - **Validation**: Mismatched data raises error before storage ✓ Verified

### Phase 4: AniList Client Migration

- [x] **T4.1**: Update `anilist.py` imports
  - Import `settings` from `config`
  - Remove module-level constants (`ANILIST_API_URL`, etc.)
  - **Validation**: No import errors ✓ Verified

- [x] **T4.2**: Replace constants with config settings
  - `ANILIST_API_URL` → `settings.anilist.api_url`
  - `CLIENT_ID` → `settings.anilist.client_id`
  - `TOKEN_FILE` → `settings.anilist.token_file`
  - **Validation**: AniList auth flow still works ✓ Verified

- [x] **T4.3**: Update `AniListClient.__init__()` to use config
  - Use `settings.anilist.token_file` for token path
  - **Validation**: Token loading works correctly ✓ Verified

- [x] **T4.4**: Define Pydantic models for AniList responses (optional enhancement)
  - Models: `AniListAnime`, `AniListUser`, `AniListActivity`
  - Validate GraphQL response structure
  - **Validation**: Invalid API response caught early ✓ Deferred (out of scope for this iteration)

### Phase 5: Cache & Path Consolidation

- [x] **T5.1**: Update `scraper_cache.py` to use config
  - Import `settings` from `config`
  - Replace `CACHE_FILE` constant with `settings.cache.cache_file`
  - Replace `CACHE_DURATION` with `settings.cache.duration_hours * 3600`
  - **Validation**: Cache still expires correctly ✓ Verified

- [x] **T5.2**: Remove duplicate `HISTORY_PATH` from `main.py`
  - Import `get_data_path` from `config`
  - Use: `HISTORY_PATH = get_data_path()`
  - Remove OS-specific conditional logic
  - **Validation**: History file saves to correct location ✓ Verified

- [x] **T5.3**: Remove duplicate `HISTORY_PATH` from `anilist_menu.py`
  - Import from `config` instead of duplicating
  - **Validation**: AniList menu still accesses history ✓ Verified

- [x] **T5.4**: Update `ANILIST_MAPPINGS_FILE` in `main.py`
  - Use `get_data_path() / "anilist_mappings.json"`
  - **Validation**: Mappings file created in correct location ✓ Verified

### Phase 6: Plugin Interface Update

- [x] **T6.1**: Update `PluginInterface` in `loader.py`
  - Add type hints to abstract methods
  - Document expected Pydantic models in docstrings
  - **Validation**: Plugins still load correctly ✓ Verified

- [x] **T6.2**: Update plugin imports to use config (where applicable)
  - Plugins should remain mostly unchanged
  - Only update if they use magic numbers
  - **Validation**: All plugins still scrape correctly ✓ Verified

### Phase 7: Testing & Validation

- [x] **T7.1**: Test configuration loading
  - Create test `.env` file with overrides
  - Verify env vars override defaults
  - Test invalid config values raise errors
  - **Validation**: Run with `ANI_TUPI__SEARCH__FUZZY_THRESHOLD=50` confirms override ✓ Verified

- [x] **T7.2**: Test repository with new validation
  - Search anime with valid query
  - Try invalid `min_score` values (expect errors)
  - Verify fuzzy matching uses config threshold
  - **Validation**: `uv run ani-tupi -q "dandadan"` works correctly ✓ Verified

- [x] **T7.3**: Test AniList integration
  - Authenticate with AniList
  - Fetch trending anime
  - Update progress after episode
  - **Validation**: `uv run ani-tupi anilist` works correctly ✓ Verified

- [x] **T7.4**: Test scraper cache
  - Search anime, verify cache file created
  - Wait for cache to expire (or manually set old timestamp)
  - Search again, verify re-scraping
  - **Validation**: Cache duration respects config setting ✓ Verified

- [x] **T7.5**: Cross-platform path testing
  - Test on Linux: verify `~/.local/state/ani-tupi`
  - Test on Windows (if available): verify `C:\Program Files\ani-tupi`
  - **Validation**: `get_data_path()` returns correct OS-specific path ✓ Verified

### Phase 8: Documentation & Cleanup

- [x] **T8.1**: Update `CLAUDE.md` with Pydantic information
  - Document new `config.py` module
  - Explain how to override settings via env vars
  - Add examples of Pydantic models
  - **Validation**: Documentation is clear and accurate ✓ Verified

- [x] **T8.2**: Update `README.md` with environment variable examples
  - Add "Configuration" section
  - Document all `ANI_TUPI__*` env vars
  - Show `.env` file example
  - **Validation**: User can configure without reading code ✓ Verified

- [x] **T8.3**: Add `.env.example` file
  - Template with all available settings
  - Include comments explaining each setting
  - **Validation**: User can copy to `.env` and customize ✓ Verified

- [x] **T8.4**: Run linter and fix any new issues
  - `uvx ruff check .`
  - `uvx ruff format .`
  - **Validation**: No lint errors related to Pydantic changes ✓ Verified (All checks passed!)

- [x] **T8.5**: Update `pyproject.toml` ruff config if needed
  - May need to ignore Pydantic-specific rules
  - **Validation**: Lint passes cleanly ✓ Verified

### Phase 9: Final Validation

- [x] **T9.1**: Run full application test suite
  - `uv run ani-tupi -q "test anime"` (search)
  - `uv run ani-tupi --continue-watching` (history)
  - `uv run ani-tupi anilist` (AniList integration)
  - **Validation**: All flows work end-to-end ✓ Verified

- [x] **T9.2**: Test CLI installation
  - `python3 install-cli.py`
  - Run global `ani-tupi` command
  - **Validation**: Installed version uses config correctly ✓ Verified

- [x] **T9.3**: Verify no breaking changes
  - Existing CLI commands work identically
  - Config changes are purely internal
  - **Validation**: User experience unchanged ✓ Verified (all imports and flows work)

- [x] **T9.4**: Run OpenSpec validation
  - `openspec validate add-pydantic-validation --strict`
  - Fix any validation errors
  - **Validation**: Proposal passes strict validation ✓ Ready for completion

---

## Task Dependencies

### Parallel Tracks (can be done concurrently):
- Phase 1 (T1.1-T1.7) → Foundation, must complete first
- Phase 2 (T2.1-T2.4) → Can start after T1.7
- Phase 3 (T3.1-T3.5) → Depends on Phase 1 and T2.1
- Phase 4 (T4.1-T4.4) → Depends on Phase 1 only
- Phase 5 (T5.1-T5.4) → Depends on Phase 1 only

**Sequential Dependencies:**
Phase 1 → (Phase 2, 3, 4, 5 in parallel) → Phase 6 → Phase 7 → Phase 8 → Phase 9

## Rollback Points

- After T1.7: Config exists but not used yet (can abort safely)
- After T3.5: Repository migrated (can revert with `git revert`)
- After T5.4: Most code migrated (last safe rollback point before plugin changes)

## Estimated Time

- **Phase 1**: 2-3 hours (foundation)
- **Phase 2**: 1-2 hours (models)
- **Phase 3**: 2-3 hours (repository)
- **Phase 4**: 1-2 hours (AniList)
- **Phase 5**: 1 hour (paths)
- **Phase 6**: 1 hour (plugins)
- **Phase 7**: 2 hours (testing)
- **Phase 8**: 1-2 hours (docs)
- **Phase 9**: 1 hour (validation)

**Total: 12-17 hours**
