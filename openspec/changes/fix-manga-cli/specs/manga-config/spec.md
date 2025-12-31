# Spec: Manga Configuration Settings

**Change ID:** `fix-manga-cli`

**Capability:** `manga-config`

**Status:** Proposed Delta

## ADDED Requirements

### Requirement: MUST add MangaSettings to centralized configuration

The application MUST include a `MangaSettings` section in the configuration system with all manga-specific settings, configurable via environment variables.

**Details:**
- Module: `config.py`
- Class: `MangaSettings` using Pydantic `BaseModel`
- Fields: `api_url`, `cache_duration_hours`, `output_directory`, `languages`
- Access: Through `settings.manga` singleton instance
- Defaults: Sensible for typical users, customizable via env vars

#### Scenario: User customizes manga settings via environment variables

1. User wants manga saved to custom directory
2. User sets: `export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=/mnt/manga`
3. User sets: `export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48`
4. User runs: `uv run manga-tupi`
5. Config loads from environment variables
6. Chapters downloaded to: `/mnt/manga/MangaTitle/ChapterNo/`
7. Cache retains data for 48 hours instead of 24

```python
# In config.py
class MangaSettings(BaseModel):
    api_url: HttpUrl = "https://api.mangadex.org"
    cache_duration_hours: int = Field(default=24, ge=1, le=72)
    output_directory: Path = Field(default_factory=lambda: Path.home() / "Downloads")
    languages: list[str] = Field(default=["pt-br", "en"])

class AppSettings(BaseSettings):
    manga: MangaSettings = Field(default_factory=MangaSettings)

# Usage
from config import settings
settings.manga.output_directory  # User's custom value or default
```

---

### Requirement: MUST validate API endpoint URL

The MangaDex API URL MUST be validated as a proper URL with HttpUrl type and default to official endpoint.

**Details:**
- Type: Pydantic `HttpUrl`
- Default: `https://api.mangadex.org`
- Validation: Automatic by Pydantic
- Invalid URLs: Raise clear `ValidationError` on startup

#### Scenario: User provides invalid API URL

1. User sets: `export ANI_TUPI__MANGA__API_URL=not-a-url`
2. User runs: `uv run manga-tupi`
3. Pydantic validates configuration on startup
4. Raises: `ValidationError: Invalid URL provided`
5. Application exits with clear error message

```bash
$ export ANI_TUPI__MANGA__API_URL=invalid
$ uv run manga-tupi
ValidationError: 1 validation error for MangaSettings
api_url
  Input should be a valid URL, unable to parse URL string [type=url_parsing]
```

---

### Requirement: MUST provide configurable cache duration

The cache TTL MUST be configurable with validation constraints (min 1 hour, max 72 hours, default 24 hours).

**Details:**
- Type: Integer (hours)
- Constraints: 1 ≤ value ≤ 72
- Default: 24 hours
- Field validator: Rejects out-of-range values
- Flexibility: Users can adjust based on needs

#### Scenario: User wants longer cache duration

1. User has limited bandwidth
2. User wants to cache data for 3 days (72 hours)
3. User sets: `export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=72`
4. User runs: `uv run manga-tupi`
5. Cache retains data for 72 hours
6. Fewer API calls overall

```python
cache_duration_hours: int = Field(
    default=24,
    ge=1,  # minimum 1 hour
    le=72,  # maximum 72 hours
    description="How long to cache chapter lists before refreshing from API"
)
```

#### Scenario: User provides invalid cache duration

1. User sets: `export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=100`
2. User runs: `uv run manga-tupi`
3. Validation fails: `100 > 72 (max allowed)`
4. Clear error: `"Cache duration must be 1-72 hours, got 100"`
5. Application exits

---

### Requirement: MUST support configurable language preferences

The preferred languages for manga chapters MUST be configurable as an ordered list with default Portuguese and English.

**Details:**
- Type: List of language codes
- Default: `["pt-br", "en"]`
- Format: Comma-separated for env vars
- Priority: Languages tried in order
- Examples: "ja" (Japanese), "pt-br" (Portuguese), "en" (English)

#### Scenario: User prefers Japanese raw manga

1. User primarily reads Japanese manga
2. User sets: `export ANI_TUPI__MANGA__LANGUAGES=ja,en`
3. User runs: `uv run manga-tupi`
4. When searching manga with multiple language versions:
   - Service tries Japanese first
   - Falls back to English if not available
   - Portuguese chapters ignored (not in preference list)

```python
languages: list[str] = Field(
    default=["pt-br", "en"],
    description="Preferred languages in order (pt-br, en, ja, etc)"
)

# Environment variable usage
export ANI_TUPI__MANGA__LANGUAGES=ja,en,pt-br
```

---

### Requirement: MUST validate all settings with clear error messages

All manga configuration values MUST use Pydantic Field validators, providing runtime type checking and informative error messages for invalid values.

**Details:**
- Validation: Automatic on application startup
- Error Messages: Clear explanation of acceptable values
- Constraints: All fields have validation rules (ge, le, validators)
- Fail-Fast: Invalid config prevents application start

#### Scenario: User provides invalid configuration

1. User sets: `export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=not_a_number`
2. User runs: `uv run manga-tupi`
3. Pydantic validation fails on startup
4. Error shown:
   ```
   ValidationError: 1 validation error for MangaSettings
   cache_duration_hours
     Input should be a valid integer, unable to parse string as an integer
   ```
5. User corrects setting and retries

```python
from pydantic import BaseModel, Field

class MangaSettings(BaseModel):
    cache_duration_hours: int = Field(default=24, ge=1, le=72)
    # All fields have validators
```

---

### Requirement: MUST provide sensible defaults for zero-configuration usage

All manga settings MUST have sensible defaults that work correctly without any environment variable configuration.

**Details:**
- No required settings (all have defaults)
- Defaults suitable for typical users
- Official MangaDex endpoint by default
- Output directory: `~/Downloads` (cross-platform)
- Cache: 24 hours (balance between freshness and bandwidth)
- Languages: Portuguese + English (primary targets)

#### Scenario: New user runs without any configuration

1. User installs: `uv sync`
2. User runs: `uv run manga-tupi`
3. No environment variables set
4. Application starts successfully with defaults:
   - API: `https://api.mangadex.org` (official)
   - Output: `~/Downloads/`
   - Cache: 24 hours
   - Languages: Portuguese, English
5. User can search, download, and read manga immediately

```python
class MangaSettings(BaseModel):
    api_url: HttpUrl = "https://api.mangadex.org"
    cache_duration_hours: int = Field(default=24, ge=1, le=72)
    output_directory: Path = Field(default_factory=lambda: Path.home() / "Downloads")
    languages: list[str] = Field(default=["pt-br", "en"])
    # No required fields - all have defaults
```

---

### Requirement: MUST document all configuration options

All manga configuration options MUST be documented with descriptions, defaults, constraints, and usage examples in code and README.

**Details:**
- Inline: Field descriptions in `config.py`
- README: Table of all manga configuration options
- Examples: Common customization scenarios
- Constraints: Min/max values documented
- Use cases: Why user might customize each setting

#### Scenario: User wants to understand cache setting

1. User reads README "Configuration" section
2. Finds table:
   | Option | Default | Range | Description |
   |--------|---------|-------|-------------|
   | `ANI_TUPI__MANGA__CACHE_DURATION_HOURS` | 24 | 1-72 | How long to cache chapter lists |
3. Sees example: `export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48`
4. Understands impact: "48 hours means fewer API calls, but 2-day-old chapter lists"
5. Makes informed decision

---

## MODIFIED Requirements

### No Requirements Modified

Manga configuration is purely additive. No existing anime configuration is changed.

---

## Integration with Existing Systems

### Must integrate with shared configuration loading

Manga settings MUST load from same sources as anime settings (environment variables, `.env` file) using consistent `ANI_TUPI__` prefix pattern.

#### Scenario: User configures both anime and manga from .env file

1. User creates `.env` file:
   ```
   ANI_TUPI__CACHE__DURATION_HOURS=12
   ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48
   ANI_TUPI__MANGA__OUTPUT_DIRECTORY=/mnt/manga
   ```
2. User runs: `uv run ani-tupi` and `uv run manga-tupi`
3. Both applications load from same `.env` file
4. Anime uses 12-hour cache, manga uses 48-hour cache
5. Consistent configuration approach for both modes

---

### Must use cross-platform path resolution

Manga output directory and history file MUST use `get_data_path()` helper for correct behavior on Linux, macOS, and Windows.

#### Scenario: Reading history path varies by OS

1. History file location depends on OS:
   - Linux: `~/.local/state/ani-tupi/manga_history.json`
   - macOS: `~/Library/Application Support/ani-tupi/manga_history.json`
   - Windows: `C:\Program Files\ani-tupi\manga_history.json`
2. Service uses: `history_path = get_data_path() / "manga_history.json"`
3. Same code works on all platforms

---

## Dependencies

### Pydantic Dependency

**Requirement:** `add-pydantic-validation` change must be complete

**Reason:** `MangaSettings` inherits from Pydantic `BaseModel`

### Existing Libraries

All required libraries already in `pyproject.toml`:
- `pydantic>=2.10.0`
- `pydantic-settings>=2.7.0`

---

## Validation Criteria

- [ ] `MangaSettings` class created with all required fields
- [ ] All fields have appropriate types (`HttpUrl`, `int`, `Path`, etc)
- [ ] All fields have sensible defaults
- [ ] All fields have validation constraints (ge, le, etc)
- [ ] `settings.manga` accessible from any module
- [ ] Environment variable override works (`ANI_TUPI__MANGA__*`)
- [ ] Invalid config values raise clear `ValidationError`
- [ ] `.env` file loading works
- [ ] Documentation added to README
- [ ] No breaking changes to anime configuration
- [ ] Cross-platform path handling verified

---

## Examples

### Example 1: Default Configuration (No customization)

```python
from config import settings

print(settings.manga.api_url)  # https://api.mangadex.org
print(settings.manga.cache_duration_hours)  # 24
print(settings.manga.output_directory)  # ~/Downloads
print(settings.manga.languages)  # ['pt-br', 'en']
```

### Example 2: Environment Variables Override

```bash
# Shell session
export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=/custom/manga
export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=72
export ANI_TUPI__MANGA__LANGUAGES=ja,en,pt-br

uv run manga-tupi  # Uses custom settings
```

### Example 3: .env File Configuration

```bash
# .env file in project root
ANI_TUPI__MANGA__API_URL=https://mangadex-mirror.local
ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48
ANI_TUPI__MANGA__OUTPUT_DIRECTORY=/mnt/manga-library
ANI_TUPI__MANGA__LANGUAGES=pt-br,en

# User runs: uv run manga-tupi
# All settings loaded from .env file
```

---

## Performance Requirements

- Configuration loading: < 10ms
- Setting validation: < 10ms
- No impact on application startup time

---

## Security Considerations

- ✅ No secrets in manga settings (no API keys required)
- ✅ All URLs validated with `HttpUrl` type
- ✅ All file paths validated with `Path` type
- ✅ No hardcoded sensitive data
- ✅ User-controlled paths don't bypass sandbox (user's own directory)
