# Implementation Tasks: Manga CLI Refactoring

**Change ID:** `fix-manga-cli`

**Estimated Duration:** 6-8 hours

## Phase 1: Preparation & Configuration (2 hours)

### Task 1.1: Add MangaSettings to config.py
**Status:** Pending
**Dependencies:** `add-pydantic-validation` must be complete

**Subtasks:**
- [ ] Add `MangaSettings` Pydantic model with fields:
  - `api_url: HttpUrl = "https://api.mangadex.org"`
  - `cache_duration_hours: int = Field(default=24, ge=1, le=72)`
  - `output_directory: Path = Field(default_factory=lambda: Path.home() / "Downloads")`
  - `languages: list[str] = Field(default=["pt-br", "en"])`
- [ ] Add `manga: MangaSettings` field to `AppSettings`
- [ ] Test: `from config import settings; print(settings.manga)`
- [ ] Verify environment variable override works:
  ```bash
  export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48
  uv run -c "from config import settings; print(settings.manga.cache_duration_hours)"
  ```

**Validation:**
```bash
uv run -c "from config import settings; assert settings.manga.api_url == 'https://api.mangadex.org'"
uv run -c "from config import settings; assert settings.manga.cache_duration_hours == 24"
```

---

### Task 1.2: Add Manga Data Models to models.py
**Status:** Pending
**Dependencies:** Task 1.1

**Subtasks:**
- [ ] Add `MangaStatus` enum:
  - `ONGOING = "ongoing"`
  - `COMPLETED = "completed"`
  - `HIATUS = "hiatus"`
  - `CANCELLED = "cancelled"`
- [ ] Add `MangaMetadata` Pydantic model with fields:
  - `id: str` (MangaDex UUID)
  - `title: str`
  - `description: str | None = None`
  - `status: MangaStatus`
  - `year: int | None = None`
  - `cover_url: str | None = None`
  - `tags: list[str] = []`
- [ ] Add `ChapterData` Pydantic model with fields:
  - `id: str` (Chapter UUID)
  - `number: str` (supports decimals like "42.5")
  - `title: str | None = None`
  - `language: str`
  - `published_at: datetime | None = None`
  - `scanlation_group: str | None = None`
  - `display_name()` method
- [ ] Add `MangaHistoryEntry` Pydantic model with fields:
  - `last_chapter: str`
  - `last_chapter_id: str | None = None`
  - `timestamp: datetime`
  - `manga_id: str | None = None`

**Validation:**
```bash
uv run -c "from models import MangaMetadata, ChapterData, MangaHistoryEntry, MangaStatus"
uv run -c "from models import MangaMetadata; m = MangaMetadata(id='1', title='Test', status='ongoing'); print(m.title)"
```

---

### Task 1.3: Create manga_service.py Service Layer
**Status:** Pending
**Dependencies:** Task 1.2

**Subtasks:**
- [ ] Create `manga_service.py` with following classes:

#### MangaCache class
```python
class MangaCache:
    """Simple in-memory cache with TTL."""

    def __init__(self, ttl_hours: int):
        self.ttl_seconds = ttl_hours * 3600
        self.cache = {}

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any) -> None: ...
    def clear(self) -> None: ...
```

- [ ] Create `MangaDexClient` class with methods:
  - `__init__(config: MangaSettings)` - Initialize with config
  - `search_manga(query: str) -> list[MangaMetadata]` - Search by title
  - `get_chapters(manga_id: str) -> list[ChapterData]` - Get chapter list
  - `get_chapter_pages(chapter_id: str) -> list[str]` - Get page URLs
  - Each method:
    - Uses cache where appropriate
    - Raises appropriate MangaError subclass on failure
    - Includes proper error messages

- [ ] Create error classes:
  ```python
  class MangaError(Exception):
      user_message: str

  class MangaNotFoundError(MangaError): ...
  class MangaDexError(MangaError): ...
  class ChapterNotAvailable(MangaError): ...
  ```

**Validation:**
```bash
uv run -c "from manga_service import MangaDexClient, MangaCache"
```

---

## Phase 2: State Management (1.5 hours)

### Task 2.1: Implement Reading History
**Status:** Pending
**Dependencies:** Task 1.2

**Subtasks:**
- [ ] Create `MangaHistory` class in `manga_service.py` with static methods:
  - `load() -> dict[str, MangaHistoryEntry]` - Load from JSON
  - `save(history: dict) -> None` - Save to JSON
  - `get_last_chapter(manga_title: str) -> str | None` - Get resume chapter
  - `update(manga_title: str, chapter_number: str, chapter_id: str = None) -> None`
  - File location: `~/.local/state/ani-tupi/manga_history.json`

- [ ] Ensure path uses `get_data_path()` for cross-platform compatibility

- [ ] Error handling for:
  - Missing file (create new history)
  - Invalid JSON (recreate file)
  - Permission errors (log and continue)

**Validation:**
```bash
# Create test manga history entry
uv run -c "
from manga_service import MangaHistory
hist = MangaHistory()
hist.update('Test Manga', '5.0')
assert hist.get_last_chapter('Test Manga') == '5.0'
"
```

---

## Phase 3: CLI Refactoring (3 hours)

### Task 3.1: Replace input() with InquirerPy
**Status:** Pending
**Dependencies:** Task 1.1, Phase 2 complete

**Subtasks:**
- [ ] Replace `input("Pesquise mangá: ")` with:
  ```python
  from inquirerpy import inquirer

  query = inquirer.text(
      message="Pesquise mangá",
      default="",
      validate=lambda x: len(x) > 0
  )
  ```

- [ ] Replace `menu(titles)` calls with:
  ```python
  from menu import menu_navigate

  selected = menu_navigate(titles, "Selecione mangá")
  ```

- [ ] Replace chapter selection with `menu_navigate`

- [ ] Add "⮕ Retomar" hint if reading history exists:
  ```python
  if last_chapter:
      # Prepend resume option
      chapter_labels.insert(0, f"⮕ Retomar - Cap. {last_chapter}")
  ```

**Validation:**
```bash
# Manual test - verify menus appear, not input()
uv run manga-tupi
# (Type search, see menu with fuzzy search, select)
```

---

### Task 3.2: Add Loading Spinners
**Status:** Pending
**Dependencies:** Task 3.1

**Subtasks:**
- [ ] Wrap API calls with `loading()` context manager:
  ```python
  from loading import loading

  with loading("Buscando mangás..."):
      results = service.search_manga(query)

  with loading("Carregando capítulos..."):
      chapters = service.get_chapters(manga_id)

  with loading("Carregando páginas..."):
      pages = service.get_chapter_pages(chapter_id)
  ```

- [ ] Keep existing `tqdm` for image download progress

**Validation:**
```bash
# Manual test - verify spinners show during API calls
uv run manga-tupi
# (Observe spinners during search, chapter load, etc)
```

---

### Task 3.3: Refactor Main Flow to Use Service Layer
**Status:** Pending
**Dependencies:** All previous tasks

**Subtasks:**
- [ ] Refactor `main()` function to orchestrate:
  1. Load config
  2. Create service instance
  3. Search with loading spinner
  4. Show manga menu
  5. Load chapters with loading spinner
  6. Show resume hint if applicable
  7. Chapter selection loop:
     - Load pages with spinner
     - Download with tqdm
     - Open viewer
     - Save progress
     - Ask next action
  8. Exit

- [ ] Error handling for each step:
  ```python
  try:
      results = service.search_manga(query)
  except MangaDexError as e:
      print(f"⚠️  {e.user_message}")
      return
  except Exception as e:
      print(f"❌ Erro inesperado: {e}")
      return
  ```

- [ ] Maintain backward compatibility with CLI:
  - Same entry point: `manga-tupi`
  - No new command-line arguments
  - Same user workflow

**Validation:**
```bash
uv run manga-tupi  # Full workflow test
# 1. Search for manga
# 2. Select manga
# 3. Select chapter
# 4. Download completes
# 5. Verify history saved
```

---

### Task 3.4: Code Quality & Style
**Status:** Pending
**Dependencies:** Task 3.3

**Subtasks:**
- [ ] Run linter and fix issues:
  ```bash
  uvx ruff check manga_service.py manga_tupi.py --fix
  ```

- [ ] Format code:
  ```bash
  uvx ruff format manga_service.py manga_tupi.py
  ```

- [ ] Add docstrings to all public methods

- [ ] Add type hints to all functions

- [ ] Verify no magic numbers (all in config)

**Validation:**
```bash
uvx ruff check .
# Should have no errors in manga-related files
```

---

## Phase 4: Testing & Documentation (1.5-2 hours)

### Task 4.1: Manual Testing
**Status:** Pending
**Dependencies:** Phase 3 complete

**Test Scenarios:**

- [ ] **Test: Search Happy Path**
  ```bash
  uv run manga-tupi
  # Input: "Dandadan"
  # Verify: Shows results, user can select
  ```

- [ ] **Test: Cache Hit**
  ```bash
  uv run manga-tupi
  # Search "Dandadan" first time (slow, with spinner)
  # Search "Dandadan" again (instant, from cache)
  ```

- [ ] **Test: No Results**
  ```bash
  uv run manga-tupi
  # Input: "xyzabc123gibberish"
  # Verify: Error message shown
  ```

- [ ] **Test: Reading History**
  ```bash
  uv run manga-tupi
  # Search, select manga, select chapter 1
  # Verify: manga_history.json created
  # Run again, select same manga
  # Verify: "⮕ Retomar - Cap. 1" appears
  ```

- [ ] **Test: Configuration**
  ```bash
  export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=/tmp/test-manga
  uv run manga-tupi
  # Download chapter
  # Verify: Files saved to /tmp/test-manga
  ```

- [ ] **Test: Error Handling (Network Down)**
  ```bash
  # Simulate network error
  uv run manga-tupi
  # Verify: Clear error message
  ```

**Documentation:**
- [ ] Record any issues/edge cases found
- [ ] Document workarounds if needed

---

### Task 4.2: Update README
**Status:** Pending
**Dependencies:** Task 4.1

**Subtasks:**
- [ ] Add manga usage section to README:
  ```markdown
  ## Ler Mangá

  ```bash
  manga-tupi
  ```

  - Pesquise mangá (busca em tempo real)
  - Selecione título
  - Selecione capítulo (com resumo de último lido)
  - Visualize em seu viewer padrão
  - Progresso salvo automaticamente

  ### Configuração

  ```bash
  export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=~/Mangas
  export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48
  export ANI_TUPI__MANGA__LANGUAGES=pt-br,en
  ```
  ```

- [ ] Add environment variables documentation:
  - `ANI_TUPI__MANGA__OUTPUT_DIRECTORY`
  - `ANI_TUPI__MANGA__CACHE_DURATION_HOURS`
  - `ANI_TUPI__MANGA__LANGUAGES`
  - `ANI_TUPI__MANGA__API_URL`

- [ ] Add troubleshooting section:
  - "Mangá não encontrado"
  - "Erro ao conectar"
  - "Histórico não salva"

---

### Task 4.3: Validate Specs
**Status:** Pending
**Dependencies:** All tasks

**Subtasks:**
- [ ] Run spec validation:
  ```bash
  openspec validate fix-manga-cli --strict
  ```

- [ ] Fix any validation errors

- [ ] Ensure all requirements from specs are implemented

**Success Criteria:**
```bash
openspec validate fix-manga-cli --strict
# Should pass with no errors
```

---

## Phase 5: Integration & Deployment (optional, 1 hour)

### Task 5.1: Integration Testing
**Status:** Pending
**Dependencies:** Phase 4 complete

**Subtasks:**
- [ ] Verify anime mode still works:
  ```bash
  uv run ani-tupi --debug -q "Dandadan"
  ```

- [ ] Verify both modes can be installed globally:
  ```bash
  python3 install-cli.py
  which ani-tupi manga-tupi
  ```

- [ ] Test both commands work from different directories:
  ```bash
  cd /
  ani-tupi --help
  manga-tupi
  ```

---

### Task 5.2: Create Test Suite (Optional, Future)
**Status:** Pending
**Dependencies:** Phase 4

**Subtasks:**
- [ ] Create `tests/test_manga_service.py` with:
  - Mock MangaDex API responses
  - Test cache functionality
  - Test error handling
  - Test history operations

- [ ] Create `tests/test_manga_config.py` with:
  - Test MangaSettings validation
  - Test environment variable override
  - Test invalid values

Note: This can be deferred to future enhancement

---

## Acceptance Criteria

### Must Have (Required for completion)

- [x] `manga_tupi.py` refactored to use service layer
- [x] All `input()` calls replaced with InquirerPy
- [x] Loading spinners on all API calls
- [x] Reading history implemented and working
- [x] Configuration via environment variables
- [x] Error messages user-friendly
- [x] No breaking changes to CLI
- [x] Linter passes
- [x] Type hints added
- [x] Documentation updated

### Should Have (Strongly recommended)

- [ ] Manual testing completed successfully
- [ ] README updated with examples
- [ ] Edge cases handled (network, API errors)
- [ ] Cache TTL working correctly

### Nice to Have (Can be future enhancement)

- [ ] Automated test suite
- [ ] Performance benchmarks
- [ ] Manga plugins architecture
- [ ] Sync to AniList

---

## Risk & Mitigation

### Risk: Breaking existing manga downloads
**Mitigation:** Doesn't affect already downloaded files; only changes how new downloads work

### Risk: MangaDex API changes
**Mitigation:** Proper error handling; migration path clear if needed

### Risk: Configuration loading fails
**Mitigation:** Falls back to defaults; clear validation errors at startup

---

## Rollback Plan

If issues discovered after merging:

```bash
# Revert change
git revert <commit-hash>

# Old manga_tupi.py still available in history
git show HEAD~1:manga_tupi.py > manga_tupi.py.old
```

Old code continues to work even with refactored anime mode.

---

## Notes

- Depends on `add-pydantic-validation` change being complete
- No new external dependencies needed
- All libraries already in `pyproject.toml`
- Follows established patterns from anime mode
- Safe to implement in parallel with other features
