# Spec: Configuration Management with Pydantic

**Change ID:** `add-pydantic-validation`

**Capability:** `configuration-management`

**Status:** Proposed Delta

## ADDED Requirements

### Requirement: MUST centralize all application settings in config module

The system MUST provide a single `config.py` module that defines all configurable application settings using Pydantic `BaseSettings`.

**Details:**
- Module: `config.py` at project root
- Settings: Nested Pydantic models organized by domain (AniList, Cache, Search)
- Access: Singleton instance `settings` imported from config module
- Validation: All settings validated on application startup
- Environment Support: Override via `ANI_TUPI__*` environment variables

#### Scenario: Developer wants to change fuzzy matching threshold

1. Developer opens `config.py`
2. Locates `SearchSettings.fuzzy_threshold` field
3. Sees current default: `Field(98, ge=0, le=100, description="...")`
4. Can override via environment variable: `ANI_TUPI__SEARCH__FUZZY_THRESHOLD=95`
5. Or create `.env` file with override
6. Application loads new value on next startup
7. Invalid values (e.g., 150) raise clear `ValidationError` with message

---

### Requirement: MUST support environment variable configuration

The system MUST allow all settings to be overridden via environment variables with a consistent naming convention.

**Details:**
- Prefix: `ANI_TUPI__` (double underscore separator)
- Nesting: `ANI_TUPI__SECTION__FIELD` (e.g., `ANI_TUPI__ANILIST__CLIENT_ID`)
- Case: Insensitive (e.g., `ani_tupi__anilist__client_id` also works)
- File Support: Load from `.env` file if present
- Priority: Environment variables override `.env` file override defaults

#### Scenario: CI pipeline needs custom AniList client ID

1. CI script sets: `export ANI_TUPI__ANILIST__CLIENT_ID=12345`
2. Application starts with `uv run ani-tupi`
3. Config loads default settings from `config.py`
4. Detects `ANI_TUPI__ANILIST__CLIENT_ID` environment variable
5. Overrides default client ID with `12345`
6. Application uses custom client ID for AniList API calls
7. No code changes or `.env` file needed

---

### Requirement: MUST validate configuration values on startup

The system MUST validate all configuration values when the application starts and raise clear errors for invalid settings.

**Details:**
- Timing: Validation occurs on first import of `settings` singleton
- Validation: Pydantic validators check constraints (e.g., `ge=0`, `le=100`)
- Errors: `ValidationError` with field name and constraint violation
- Behavior: Application exits immediately on invalid config (fail-fast)
- Message: Human-readable error explaining what's wrong and how to fix

#### Scenario: User sets invalid cache duration

1. User creates `.env` file with: `ANI_TUPI__CACHE__DURATION_HOURS=200`
2. Runs: `uv run ani-tupi -q "anime"`
3. Application imports `from config import settings`
4. Pydantic validation runs on `AppSettings` creation
5. Detects `duration_hours=200` violates constraint `le=72` (max 72 hours)
6. Raises `ValidationError`:
   ```
   1 validation error for AppSettings
   cache.duration_hours
     Input should be less than or equal to 72 [type=less_than_equal, input_value=200, input_type=int]
   ```
7. Application exits with exit code 1
8. User fixes `.env` to `ANI_TUPI__CACHE__DURATION_HOURS=24`
9. Application starts successfully

---

### Requirement: MUST organize settings by functional domain

Configuration MUST be grouped into logical sections reflecting different areas of functionality.

**Details:**
- `AniListSettings`: API URLs, client ID, token storage path
- `CacheSettings`: Cache duration, cache file path
- `SearchSettings`: Fuzzy matching thresholds, search behavior
- Extensible: New sections can be added (e.g., `PluginSettings`, `UISettings`)
- Access: `settings.anilist.api_url`, `settings.cache.duration_hours`, etc.

#### Scenario: Developer adds new UI configuration section

1. Developer creates `UISettings` class in `config.py`:
   ```python
   class UISettings(BaseModel):
       theme: str = Field("catppuccin-mocha", description="UI color theme")
       menu_height: int = Field(20, ge=5, le=50, description="Menu height in lines")
   ```
2. Adds to `AppSettings`:
   ```python
   class AppSettings(BaseSettings):
       ...
       ui: UISettings = Field(default_factory=UISettings)
   ```
3. UI code imports: `from config import settings`
4. Accesses theme: `theme = settings.ui.theme`
5. Users can override: `ANI_TUPI__UI__THEME=gruvbox`
6. Validation ensures `menu_height` is 5-50

---

## MODIFIED Requirements

### Requirement: Magic numbers MUST be replaced with named configuration settings

The system MUST eliminate all hardcoded magic numbers and replace them with named settings from the config module.

**Previously:** Magic numbers scattered across multiple files:
- `threshold = 98` in `repository.py:102`
- `CACHE_DURATION = 6 * 60 * 60` in `scraper_cache.py:15`
- `min_score: int = 70` in `repository.py:109`
- `CLIENT_ID = 20148` in `anilist.py:18`

**Details:**
- All numeric constants moved to `config.py` with descriptive names
- Field descriptions explain purpose and valid ranges
- Code references settings instead of literals
- Configuration values documented in single location

#### Scenario: Fuzzy matching threshold used in repository

1. Previously in `repository.py:102`:
   ```python
   threshold = 98  # What is this? Why 98?
   if fuzz.ratio(title_, self.norm_titles[key]) >= threshold:
   ```
2. Now imports config:
   ```python
   from config import settings

   threshold = settings.search.fuzzy_threshold
   if fuzz.ratio(title_, self.norm_titles[key]) >= threshold:
   ```
3. Threshold definition in `config.py`:
   ```python
   class SearchSettings(BaseModel):
       fuzzy_threshold: int = Field(
           98,
           ge=0,
           le=100,
           description="Fuzzy matching threshold for anime deduplication (0-100)"
       )
   ```
4. Clear what the value is, why it's 98, and what range is valid
5. Can be overridden without touching code: `ANI_TUPI__SEARCH__FUZZY_THRESHOLD=95`

---

### Requirement: API configuration MUST be centralized and environment-aware

The system MUST move all API-related configuration (URLs, client IDs, tokens) to the config module with environment variable support.

**Previously:** Constants defined in `anilist.py`:
- `ANILIST_API_URL = "https://graphql.anilist.co"`
- `ANILIST_AUTH_URL = "..."`
- `CLIENT_ID = 20148`
- `TOKEN_FILE = Path.home() / ".local/state/ani-tupi/anilist_token.json"`

**Details:**
- All API config in `AniListSettings` model
- Token file path uses `get_data_path()` helper (OS-aware)
- Can override API URL for testing (e.g., mock server)
- Client ID configurable per deployment

#### Scenario: Testing with mock AniList API

1. Developer sets up local mock GraphQL server on `http://localhost:4000`
2. Creates `.env.test` file:
   ```
   ANI_TUPI__ANILIST__API_URL=http://localhost:4000
   ANI_TUPI__ANILIST__CLIENT_ID=99999
   ```
3. Runs tests: `env $(cat .env.test | xargs) uv run pytest`
4. Application loads config with test overrides
5. All AniList API calls go to mock server
6. No code changes needed
7. Production `.env` uses real AniList URL

---

## REMOVED Requirements

None. This is a purely additive change.

---

## Cross-References

**Related Capabilities:**
- `data-validation` - Pydantic models for DTOs (anime metadata, episodes)
- `path-resolution` - OS-aware path resolution used in config

**Dependencies:**
- Requires: `pydantic>=2.10.0`, `pydantic-settings>=2.7.0`
- Impacts: `repository.py`, `anilist.py`, `scraper_cache.py`, `main.py`, `anilist_menu.py`

**Migration Path:**
1. Create `config.py` with all settings models
2. Import `settings` in affected files
3. Replace module-level constants with `settings.*` references
4. Remove old constants
5. Test with environment variable overrides
