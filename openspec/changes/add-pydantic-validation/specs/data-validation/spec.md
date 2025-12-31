# Spec: Data Validation with Pydantic Models

**Change ID:** `add-pydantic-validation`

**Capability:** `data-validation`

**Status:** Proposed Delta

## ADDED Requirements

### Requirement: MUST define Pydantic models for structured data transfer

The system MUST provide Pydantic `BaseModel` classes for all structured data passed between application layers.

**Details:**
- Models: `AnimeMetadata`, `EpisodeData`, `SearchResult`, `VideoUrl`
- Location: `config.py` or separate `models.py` module
- Purpose: Type-safe data transfer between plugins, repository, and controllers
- Validation: Runtime validation of all fields
- Benefits: IDE autocomplete, clear contracts, self-documenting code

#### Scenario: Plugin adds anime to repository

1. Plugin scrapes anime data from website
2. Creates `AnimeMetadata` instance:
   ```python
   anime = AnimeMetadata(
       title="Dan Da Dan",
       url="https://animefire.plus/dan-da-dan",
       source="animefire",
       params={"season": 1}
   )
   ```
3. Calls: `rep.add_anime(anime)`
4. Pydantic validates:
   - `title` is non-empty string
   - `url` starts with `http://` or `https://`
   - `source` is non-empty string
5. If validation passes, anime stored in repository
6. If validation fails (e.g., `url="not-a-url"`), raises `ValidationError`:
   ```
   1 validation error for AnimeMetadata
   url
     URL must be http(s), got: not-a-url [type=value_error, input_value='not-a-url', input_type=str]
   ```

---

### Requirement: MUST validate anime metadata structure

The system MUST validate anime metadata fields (title, URL, source) using `AnimeMetadata` Pydantic model.

**Details:**
- Model: `AnimeMetadata(title: str, url: str, source: str, params: dict | None)`
- Validation:
  - `title`: Non-empty string, min 1 character
  - `url`: Non-empty string, must start with `http://` or `https://`
  - `source`: Non-empty string (plugin name)
  - `params`: Optional dict of extra scraper parameters
- Used by: `Repository.add_anime()`, plugins

#### Scenario: Invalid URL rejected by validation

1. Plugin attempts to add anime with malformed URL:
   ```python
   anime = AnimeMetadata(
       title="Test Anime",
       url="ftp://invalid",  # Invalid protocol
       source="test-plugin"
   )
   ```
2. Pydantic validation runs on model creation
3. `url` field validator checks for `http://` or `https://` prefix
4. Validation fails, raises `ValidationError`:
   ```
   URL must be http(s), got: ftp://invalid
   ```
5. Plugin developer sees clear error message
6. Fixes URL to use `https://`
7. Validation passes

---

### Requirement: MUST validate episode data structure and consistency

The system MUST validate episode data using `EpisodeData` Pydantic model and ensure title/URL list lengths match.

**Details:**
- Model: `EpisodeData(anime_title: str, episode_titles: list[str], episode_urls: list[str], source: str)`
- Validation:
  - All fields required (no None values)
  - `episode_titles` and `episode_urls` must have same length
  - `source` is non-empty string
- Cross-field validation: `@model_validator` ensures list lengths match
- Used by: `Repository.add_episode_list()`, plugins

#### Scenario: Mismatched episode list rejected

1. Plugin scrapes episode list but makes mistake:
   ```python
   episode_data = EpisodeData(
       anime_title="Test Anime",
       episode_titles=["Ep 1", "Ep 2", "Ep 3"],  # 3 titles
       episode_urls=["url1", "url2"],  # 2 URLs - MISMATCH!
       source="test-plugin"
   )
   ```
2. Pydantic `@model_validator` runs after field validation
3. Checks: `len(episode_titles) == len(episode_urls)`
4. Detects mismatch: 3 != 2
5. Raises `ValidationError`:
   ```
   Mismatched episodes: 3 titles vs 2 URLs
   ```
6. Plugin developer immediately sees the bug
7. Fixes scraping logic to ensure matching lengths
8. Validation passes

---

### Requirement: MUST validate function input arguments at runtime

The system MUST validate function arguments using Pydantic field validators and raise clear errors for invalid inputs.

**Details:**
- Target functions: `Repository.get_anime_titles()`, `search_anime()`, cache functions
- Validation: Check ranges, types, constraints
- Example: `min_score` must be 0-100
- Errors: `ValueError` with descriptive message (or `ValidationError` if using model)
- Timing: Validate immediately on function entry (fail-fast)

#### Scenario: Invalid min_score rejected

1. User code calls: `rep.get_anime_titles(filter_by_query="anime", min_score=150)`
2. Function signature: `def get_anime_titles(self, filter_by_query: str = None, min_score: int = 70)`
3. Function validates `min_score`:
   ```python
   if not 0 <= min_score <= 100:
       raise ValueError(f"min_score must be 0-100, got {min_score}")
   ```
4. Validation fails, raises `ValueError: min_score must be 0-100, got 150`
5. Caller sees clear error message
6. Fixes to `min_score=85`
7. Validation passes

**Alternative Implementation** (using Pydantic model):
```python
class SearchParams(BaseModel):
    filter_by_query: str | None = None
    min_score: int = Field(70, ge=0, le=100)

def get_anime_titles(self, params: SearchParams) -> list[str]:
    # Validation automatic via Pydantic
```

---

### Requirement: MUST define VideoUrl model for playback URLs

The system MUST validate video playback URLs using `VideoUrl` Pydantic model with optional headers.

**Details:**
- Model: `VideoUrl(url: str, headers: dict[str, str] | None = None)`
- Validation:
  - `url`: Non-empty string
  - Optional: Warn if URL doesn't end with common video extensions (`.m3u8`, `.mp4`, etc.)
  - `headers`: Optional dict for HTTP headers (User-Agent, Referer, etc.)
- Used by: Plugin `search_player_src()` methods
- Purpose: Standardize video URL structure across plugins

#### Scenario: Plugin returns video URL with headers

1. Plugin finds video URL that requires specific headers:
   ```python
   video = VideoUrl(
       url="https://example.com/video.m3u8",
       headers={
           "User-Agent": "Mozilla/5.0 ...",
           "Referer": "https://animefire.plus"
       }
   )
   ```
2. Pydantic validates structure
3. Repository stores validated video URL
4. Video player receives standardized `VideoUrl` object
5. Can extract headers for MPV: `--http-header-fields="Referer: ..."`
6. Playback works correctly with required headers

---

## MODIFIED Requirements

### Requirement: Repository MUST use validated data models instead of tuples

The system MUST replace tuple-based data storage with Pydantic models for type safety and validation.

**Previously:** Repository used tuples and separate lists:
- `anime_to_urls: defaultdict(list)` stored `(url, source, params)` tuples
- `add_anime(title: str, url: str, source: str, params=None)` used 4 separate arguments
- No validation of argument values
- Tuple unpacking error-prone: `url, source, params = anime_data` (what order?)

**Details:**
- Replace: `(url, source, params)` tuples → `AnimeMetadata` objects
- Method signature: `add_anime(self, anime: AnimeMetadata) -> None`
- Storage: `anime_to_urls: defaultdict[str, list[AnimeMetadata]]`
- Benefits: Named fields, autocomplete, validation

#### Scenario: Repository stores anime with metadata

1. Previously (tuple-based):
   ```python
   # repository.py
   self.anime_to_urls[title].append((url, source, params))

   # Later retrieval - what order?
   for url, source, params in self.anime_to_urls[title]:
       ...
   ```
2. Now (model-based):
   ```python
   # repository.py
   self.anime_to_urls[title].append(anime)  # anime is AnimeMetadata

   # Later retrieval - clear fields
   for anime in self.anime_to_urls[title]:
       print(anime.url, anime.source, anime.params)
   ```
3. IDE provides autocomplete for `anime.url`, `anime.source`
4. Type checker ensures correct usage
5. No confusion about tuple order

---

### Requirement: Plugin interface MUST specify validated data contracts

The system MUST update `PluginInterface` abstract class to document expected Pydantic models for method arguments and returns.

**Previously:** Plugin methods used loose signatures:
- `search_anime(query: str) -> None` - no return value, side effects only
- `search_episodes(anime: str, url: str, params) -> None` - untyped `params`
- `search_player_src(url_episode: str, container: list, event: asyncio.Event) -> None` - container type unclear

**Details:**
- Add type hints: `params: dict[str, Any] | None`
- Add docstrings specifying Pydantic models used
- Document: "Plugins should create `AnimeMetadata` objects and call `rep.add_anime()`"
- No breaking changes: Interface update only (implementations unchanged)

#### Scenario: Plugin developer reads interface documentation

1. Developer opens `loader.py` to implement new plugin
2. Sees updated `PluginInterface.search_anime()` docstring:
   ```python
   @staticmethod
   @abstractmethod
   def search_anime(query: str) -> None:
       """Search for anime matching query.

       Implementations should:
       1. Scrape anime search results from source
       2. Create AnimeMetadata objects for each result
       3. Call rep.add_anime(metadata) to store results

       Args:
           query: Search query string (e.g., "dandadan")
       """
   ```
3. Understands expected workflow
4. Creates `AnimeMetadata` objects as documented
5. Plugin works correctly with repository

---

## REMOVED Requirements

None. This is a purely additive change to improve data validation.

---

## Cross-References

**Related Capabilities:**
- `configuration-management` - Settings models use same Pydantic patterns
- `path-resolution` - Used in token_file, cache_file paths

**Dependencies:**
- Requires: `pydantic>=2.10.0`
- Impacts: `repository.py`, `loader.py`, plugins (interface only)

**Migration Path:**
1. Define Pydantic models: `AnimeMetadata`, `EpisodeData`, `SearchResult`, `VideoUrl`
2. Update `Repository.add_anime()` to accept `AnimeMetadata`
3. Keep backward compatibility: accept both model and individual args (transition period)
4. Update plugins to create models (can be gradual)
5. Remove backward compatibility after all plugins updated
6. Add validation to `get_anime_titles()` and other methods
