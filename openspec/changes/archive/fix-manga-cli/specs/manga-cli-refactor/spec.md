# Spec: Manga CLI Refactoring to Follow ani-tupi Architecture

**Change ID:** `fix-manga-cli`

**Capability:** `manga-cli-refactor`

**Status:** Proposed Delta

## ADDED Requirements

### Requirement: MUST replace input() with Rich + InquirerPy menus

The manga CLI MUST replace all `input()` function calls with Rich + InquirerPy interactive menus for consistency with anime mode and improved user experience.

**Details:**
- All user prompts use InquirerPy's `inquirer.text()` or `inquirer.select()`
- Search results displayed using `menu_navigate()` from `menu.py`
- Chapter selection displayed using `menu_navigate()` with fuzzy search support
- No blocking `input()` calls that prevent seeing typed characters

#### Scenario: User searches for manga

1. User runs: `uv run manga-tupi`
2. CLI displays: `"Pesquise mangá"` using `inquirer.text()`
3. User can type incrementally and see input
4. User presses Enter to search
5. CLI shows loading spinner: `"Buscando mangás..."`
6. Results displayed in Rich + InquirerPy menu
7. User navigates with arrow keys
8. User types to filter (fuzzy search)
9. User presses Enter to select

```python
from inquirerpy import inquirer
from menu import menu_navigate
from loading import loading

query = inquirer.text(message="Pesquise mangá")

with loading("Buscando mangás..."):
    results = service.search_manga(query)

titles = [r.title for r in results]
selected = menu_navigate(titles, "Selecione mangá")
```

---

### Requirement: MUST show loading spinners for all API calls

The manga CLI MUST display a loading spinner using the existing `loading.py` context manager for all long-running API operations.

**Details:**
- Spinner shown during: search, fetch chapters, download pages
- Uses existing `loading()` context manager
- Spinner disappears automatically when operation completes
- Message is user-friendly and describes what's happening

#### Scenario: Loading chapters from MangaDex API

1. User selects a manga
2. CLI displays: `"Carregando capítulos..."`
3. Spinner animates while API call runs
4. Upon completion, spinner disappears
5. Chapter list displayed immediately

```python
from loading import loading

with loading("Carregando capítulos..."):
    chapters = service.get_chapters(manga_id)

# Spinner automatically removed when block exits
menu_navigate(chapters, "Selecione capítulo")
```

---

### Requirement: MUST implement reading history and resume feature

The manga CLI MUST track reading progress in `~/.local/state/ani-tupi/manga_history.json` and display a resume hint when user opens previously-read manga.

**Details:**
- History file: `~/.local/state/ani-tupi/manga_history.json` (cross-platform path)
- Format: JSON with manga title as key, last chapter and timestamp as values
- Resume hint: First chapter menu option shows "⮕ Retomar" when applicable
- Progress automatically saved after reading chapter

#### Scenario: User resumes reading manga

1. User previously read Dandadan Chapter 5
2. User runs: `uv run manga-tupi`
3. User searches for: "Dandadan"
4. Chapter list displays:
   - `"⮕ Retomar - Cap. 5 - Título"` (first option with hint)
   - `"Cap. 1 - ..."`
   - `"Cap. 2 - ..."`
   - ... (more chapters)
5. User can select resume option or scroll for different chapter
6. After reading, progress automatically saved

**History File Format:**
```json
{
  "Dandadan": {
    "last_chapter": "5.0",
    "last_chapter_id": "uuid-here",
    "timestamp": "2025-12-31T15:30:00Z"
  }
}
```

---

### Requirement: MUST create service layer for API interactions

The manga CLI MUST use a dedicated `MangaDexClient` service class for all API interactions with proper error handling and user-friendly error messages.

**Details:**
- Service class: `MangaDexClient` in `manga_service.py`
- Methods: `search_manga()`, `get_chapters()`, `get_chapter_pages()`
- Error handling: Raises custom MangaError subclasses
- Separation: All API logic isolated from UI/CLI code
- Error messages: User-friendly, not technical

#### Scenario: Network error during manga search

1. User searches for manga
2. Network connection fails
3. MangaDexClient raises `MangaDexError`
4. CLI catches error and shows:
   - `"❌ Erro ao conectar com MangaDex. Verifique sua conexão."`
5. User can retry or return to main menu

```python
try:
    results = service.search_manga(query)
except MangaDexError as e:
    print(f"⚠️  {e.user_message}")
    return
```

---

### Requirement: MUST cache search results and chapters

The manga CLI MUST cache search results and chapter lists for configured duration (default 24 hours) to reduce API calls and improve responsiveness.

**Details:**
- Cache type: In-memory with TTL (time-to-live)
- Default TTL: 24 hours (configurable)
- Keys:
  - `search:{query.lower()}` for search results
  - `chapters:{manga_id}` for chapter lists
- Chapter pages: NOT cached (always fetch fresh)
- Cache cleared on application restart

#### Scenario: User searches same manga twice

1. User runs: `uv run manga-tupi`
2. User searches: "Dandadan" (slow, with spinner, ~2 seconds)
3. Results retrieved from MangaDex, cached
4. User searches: "Dandadan" again (fast, instant from cache)
5. Same results displayed without network delay

```python
cache_key = f"search:{query.lower()}"
cached = cache.get(cache_key)
if cached:
    return cached  # Instant response

results = requests.get(f"{base_url}/manga", ...).json()
cache.set(cache_key, results)
return results
```

---

### Requirement: MUST use Pydantic models for data validation

All manga metadata and chapter data MUST use Pydantic models for runtime type validation and self-documenting code.

**Details:**
- Models defined in `models.py`
- Models used: `MangaMetadata`, `ChapterData`, `MangaHistoryEntry`
- Runtime validation: Invalid data raises `ValidationError`
- Type hints: All fields have explicit types

#### Scenario: Creating manga metadata from API response

1. Service receives JSON from MangaDex API
2. Service validates against `MangaMetadata` model:
   ```python
   manga = MangaMetadata(
       id=response["id"],
       title=response["attributes"]["title"],
       status=response["attributes"]["status"]
   )
   ```
3. If validation fails, raises clear `ValidationError`
4. If valid, returns typed object with IDE support

---

### Requirement: MUST support configuration via environment variables

Manga mode settings MUST be configurable via environment variables following `ANI_TUPI__MANGA__*` pattern.

**Details:**
- Prefix: `ANI_TUPI__MANGA__` (double underscore)
- Variables:
  - `ANI_TUPI__MANGA__API_URL` - MangaDex API endpoint
  - `ANI_TUPI__MANGA__CACHE_DURATION_HOURS` - Cache TTL
  - `ANI_TUPI__MANGA__OUTPUT_DIRECTORY` - Download location
  - `ANI_TUPI__MANGA__LANGUAGES` - Preferred languages (comma-separated)

#### Scenario: User customizes manga output directory

1. User sets: `export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=/mnt/manga-library`
2. User runs: `uv run manga-tupi`
3. Config loads from environment variable
4. Chapters downloaded to: `/mnt/manga-library/MangaTitle/ChapterNo/`
5. No code changes or config files needed

```bash
export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=/custom/path
export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48
uv run manga-tupi
```

---

## MODIFIED Requirements

### Requirement: MUST maintain backward-compatible CLI interface

The CLI entry point and user workflow MUST remain unchanged to ensure backward compatibility.

**Old Behavior (Current):**
- Entry point: `manga-tupi`
- Prompts user for manga title
- Shows results
- Allows chapter selection
- Downloads and displays images

**New Behavior (After Refactor):**
- Entry point: `manga-tupi` (unchanged)
- Same user workflow
- Improved UX: Better menus, loading spinners, history
- Same command-line interface (no new arguments)

#### Scenario: User runs manga-tupi as before

1. User runs: `manga-tupi` (or `uv run manga-tupi`)
2. CLI prompts for search (now using Rich, not input())
3. User selects manga from menu (fuzzy search available)
4. User selects chapter (shows resume hint if applicable)
5. Chapters download and display (progress shown)
6. Progress saved automatically
7. Workflow identical to before, UX improved

```bash
$ manga-tupi
Pesquise mangá: Dandadan
(Loading spinner shows)
(Menu with results)
(User selects)
(Chapter list with resume hint)
(Download with progress)
```

---

## REMOVED Requirements

- ~~Use bare `input()` for user prompts~~ → Replaced with InquirerPy
- ~~No loading indicators during API calls~~ → Added spinners
- ~~Manual threading for image viewer~~ → Simplified to subprocess
- ~~Hardcoded API configuration~~ → Moved to config.py

---

## Dependencies

### Existing Dependencies (Already in pyproject.toml)
- `requests` - HTTP calls
- `rich` - Terminal UI
- `inquirerpy` - Interactive menus
- `tqdm` - Progress bars
- `pydantic` - Data validation

### New Dependencies
None. All libraries already in `pyproject.toml`.

---

## Validation Criteria

- [ ] All `input()` calls replaced with InquirerPy
- [ ] Loading spinners shown for search, chapters, pages
- [ ] Reading history saved and restored correctly
- [ ] Service layer abstracts all API calls
- [ ] Pydantic models used for data validation
- [ ] Configuration via environment variables works
- [ ] Error messages are user-friendly
- [ ] Backward compatibility maintained (same CLI interface)
- [ ] Linter passes with no warnings
- [ ] Type hints on all public functions

---

## Test Cases

- [ ] **Happy Path**: Search → Select manga → Select chapter → Download → View
- [ ] **Cache Hit**: Search same manga twice, second time is instant
- [ ] **Not Found**: Search returns no results, error shown
- [ ] **Resume**: Previously read manga shows resume hint
- [ ] **Config Override**: Environment variable changes output directory
- [ ] **Network Error**: Connection failure shows user-friendly error
- [ ] **History File**: Reading history persisted across sessions

---

## Performance Requirements

- Search with cache hit: < 100ms
- Search API call: < 3 seconds
- Chapter list load: < 2 seconds
- Chapter pages download: ~1 second per page
- Menu response time: < 100ms

---

## Security Considerations

- ✅ No credential storage (MangaDex is public)
- ✅ URLs from official API only
- ✅ Downloaded files in user directory
- ✅ No code injection risks (no eval/exec)
- ✅ No sensitive data in configuration
