# Proposal: Fix Manga CLI to Follow ani-tupi Architecture Principles

**Change ID:** `fix-manga-cli`

**Status:** Proposal (awaiting approval)

**Proposed By:** User

**Date:** 2025-12-31

## Why

The manga CLI (`manga_tupi.py`) is significantly different from the well-engineered anime CLI, violating the architectural principles established in ani-tupi:

1. **Architectural Inconsistency**: `manga_tupi.py` uses old interactive `input()` prompts instead of Rich/InquirerPy menus used throughout the app
2. **No Configuration Management**: Hardcoded API base URL, no Pydantic validation
3. **No Loading Indicators**: No spinner feedback during long API calls
4. **Poor UX**: Uses `input()` for search, blocking terminal; no fuzzy search
5. **Fragmented Code**: Directory handling and image downloading logic mixed with UI
6. **Threading Issues**: Uses bare threading for image viewer instead of proper async patterns
7. **No Cache/History**: Unlike anime mode, manga mode doesn't track reading progress
8. **No Error Handling**: No loading spinners, error messages, or recovery
9. **Inconsistent with MVCP**: Violates Model-View-Controller-Plugin separation

## Summary

Refactor `manga_tupi.py` to follow ani-tupi MVCP architecture:

1. **Add Manga Configuration** to `config.py`: MangaDex API settings, cache duration, output directory
2. **Refactor Menu System**: Replace `input()` and `menu()` calls with Rich + InquirerPy for consistency
3. **Add Loading Spinners**: Use `loading.py` context manager for API calls
4. **Implement Manga-Specific Data Models**: `MangaMetadata`, `ChapterData` using Pydantic
5. **Support Reading History**: Track chapter progress in `~/.local/state/ani-tupi/manga_history.json`
6. **Better Error Handling**: Catch API errors, show user-friendly messages
7. **Code Organization**: Separate concerns (API layer, menu layer, file I/O)

## Problem Statement

### Current Issues in `manga_tupi.py`

1. **Terminal Blocking Input**:
   ```python
   # Line 21: Blocks terminal with input()
   res = requests.get(f"{base_url}/manga", params={"title": input("Pesquise mangá: ")}).json()["data"]
   # ❌ User can't see what they're typing, no fuzzy search, blocks UI
   ```

2. **Hardcoded Configuration**:
   ```python
   # Line 13: API URL hardcoded, no env override
   base_url = "https://api.mangadex.org"
   # No way to change download directory, image format, etc
   ```

3. **Synchronous Threading**:
   ```python
   # Lines 82-95: Bare threading for image viewer
   thread = threading.Thread(target=run, args=(dir_path,))
   # ❌ Manual thread management, race conditions possible
   ```

4. **No User Feedback**:
   ```python
   # Line 85: tqdm shows progress but no spinner for API calls
   for i in tqdm(range(len(pages["chapter"]["data"]))):
       # Downloading but no "Loading..." spinner during requests.get()
   ```

5. **Fragmented Logic**:
   - Lines 71-97: Complex nested function `select_language()` with file I/O
   - Lines 40-52: Raw API calls mixed with business logic
   - No separation between fetching chapters and displaying menus

6. **No State Management**:
   - Unlike anime mode, doesn't save reading progress
   - No cache of chapter lists to avoid repeated API calls
   - No mappings between manga titles and MangaDex IDs

7. **Inconsistent UI**:
   ```python
   # Lines 37, 64, 75: Using menu() directly instead of Rich + InquirerPy
   selected_title = menu(titles)
   # Should use: menu_navigate(titles, "Selecione mangá")
   ```

### Impact on User Experience

- Searching feels slow with no feedback
- Terminal freezes during API calls
- Can't see what user is typing in `input()`
- Inconsistent styling vs anime mode
- No way to resume reading (progress not saved)
- Hard to debug when scraper breaks

## Solution Overview

### Architecture Changes

**Refactor to MVCP Pattern:**

```
API Layer (config.py + model)
    ↓
Service Layer (manga_service.py)
    ↓
Menu Layer (menu.py + anilist_menu.py pattern)
    ↓
CLI Entry (manga_tupi.py)
```

### Key Changes

1. **Add Manga Configuration** (`config.py`):
   ```python
   class MangaSettings(BaseModel):
       api_url: HttpUrl = "https://api.mangadex.org"
       cache_duration_hours: int = Field(24, ge=1, le=72)
       output_directory: Path = Field(default_factory=lambda: Path.home() / "Downloads")
       languages: list[str] = Field(default=["pt-br", "en"])

   class AppSettings(BaseSettings):
       manga: MangaSettings = Field(default_factory=MangaSettings)
       # ... existing anime settings ...
   ```

2. **Data Models** (`models.py`):
   ```python
   class MangaMetadata(BaseModel):
       id: str
       title: str
       description: str | None = None
       cover_url: str | None = None
       status: str  # "ongoing", "completed", "hiatus"

   class ChapterData(BaseModel):
       id: str
       number: str
       title: str | None = None
       language: str
       published_at: datetime
       pages: list[str]  # Image URLs
   ```

3. **Service Layer** (`manga_service.py` - new):
   - `MangaDexClient` class for API calls (replaces inline requests)
   - Methods: `search_manga()`, `get_chapters()`, `get_chapter_pages()`
   - Proper error handling and caching
   - Uses `loading.py` spinner for API calls

4. **Menu System** (`manga_tupi.py`):
   ```python
   # Replace input() with Rich + InquirerPy
   from inquirerpy import inquirer
   from loading import loading

   # Old: input("Pesquise mangá: ")
   # New: inquirer.text(message="Pesquise mangá")

   # Search with loading spinner
   with loading("Buscando mangás..."):
       results = service.search_manga(query)
   ```

5. **Reading History** (`~/.local/state/ani-tupi/manga_history.json`):
   ```json
   {
     "Manga Title": {
       "last_chapter": "42.5",
       "timestamp": "2025-12-31T12:30:00",
       "chapter_id": "uuid"
     }
   }
   ```

6. **Error Handling**:
   - Network errors: Show "Erro ao conectar com MangaDex"
   - Not found: "Mangá não encontrado"
   - Rate limiting: "Muitas requisições, tente novamente em 1 minuto"

### File Organization

**New/Modified Files:**

```
├── config.py                      (MODIFIED: Add MangaSettings)
├── models.py                      (MODIFIED: Add MangaMetadata, ChapterData)
├── manga_service.py               (NEW: MangaDex API client)
├── manga_tupi.py                  (MODIFIED: Refactored CLI)
└── pyproject.toml                 (MODIFIED: Update entry point if needed)
```

## Impact Analysis

### Benefits

- ✅ **Architectural Consistency**: Follows MVCP pattern like anime mode
- ✅ **Better UX**: Rich menus with fuzzy search, loading spinners
- ✅ **Type Safety**: Pydantic models for manga metadata
- ✅ **Reading Progress**: Saves and displays last read chapter
- ✅ **Configurability**: MangaDex API URL, languages, output directory via env
- ✅ **Maintainability**: Separated concerns (API, UI, file I/O)
- ✅ **Error Resilience**: Proper error handling with user-friendly messages
- ✅ **Code Reusability**: Service layer can be used by future plugins/APIs

### Trade-offs

- ❌ **More Files**: `manga_service.py` adds 1 new file
  - Mitigation: Clear separation of concerns, easier to test
- ❌ **API Refactoring**: MangaDex client extracted to service layer
  - Mitigation: Fully backwards compatible at CLI level
- ❌ **Dependency on Config**: Needs Pydantic for manga settings
  - Mitigation: Part of existing `add-pydantic-validation` change

### Affected Code

**New Files:**
- `manga_service.py` - MangaDex API client with proper error handling

**Modified Files:**
- `manga_tupi.py` - Refactored to use service layer + Rich menus
- `config.py` - Add MangaSettings (requires `add-pydantic-validation` to be complete)
- `models.py` - Add MangaMetadata, ChapterData

**No Changes:**
- `main.py`, `menu.py`, `loading.py` - Can be reused
- Plugins system - No manga plugins yet

## Success Criteria

1. ✅ `manga-tupi` command works from any directory
2. ✅ Search uses Rich + InquirerPy (not `input()`)
3. ✅ Loading spinners shown during API calls
4. ✅ Chapter list cached (no repeated API calls)
5. ✅ Reading progress saved to `manga_history.json`
6. ✅ Error messages shown for network/API errors
7. ✅ Configuration via env vars (`ANI_TUPI__MANGA__*`)
8. ✅ Image viewer command works (feh/open/etc)
9. ✅ Manga mode respects same styling as anime mode
10. ✅ No breaking changes to CLI interface

## Scope

### In Scope

- Refactor `manga_tupi.py` to use Rich + InquirerPy menus
- Create `manga_service.py` with MangaDex API client
- Add `MangaSettings` to `config.py`
- Add Pydantic models: `MangaMetadata`, `ChapterData`
- Implement reading history (`manga_history.json`)
- Add loading spinners for API calls
- Proper error handling with user-friendly messages
- Support chapter caching
- Document manga configuration in README

### Out of Scope

- Implementing manga plugins (future enhancement)
- Supporting other manga APIs besides MangaDex (future)
- Image editing/annotation features
- Manga recommendations (no recommendation system yet)
- Offline reading mode
- Custom image viewer selection (use system default)

## Questions for Approval

1. **Manga Plugins**: Should we design for future manga plugins (like anime), or just MangaDex?
   - Recommendation: Design for extensibility, but implement MangaDex first

2. **Image Viewer**: Use system default viewer (feh on Linux, Preview on macOS, Photos on Windows) or require specific tool?
   - Recommendation: Use feh on Linux (most common), fallback to system default on macOS/Windows

3. **Chapter Language**: Support multiple languages in one menu, or per-manga language preference?
   - Recommendation: Multiple languages per chapter (like current code does)

4. **History Sync**: Should reading progress sync to AniList (for manga with AniList entries)?
   - Recommendation: Future enhancement; implement local history first

5. **Cache Strategy**: How long to cache chapters? (Current: 24 hours proposed)
   - Recommendation: 24 hours for chapters, TTL configurable via env

## Relationship to Other Changes

**Depends On:**
- `add-pydantic-validation` - Needs `config.py` with Pydantic

**Enables:**
- Future manga plugins architecture (if needed)
- Manga/AniList sync (future)
- Reading statistics (future)

## Next Steps

1. **Approval**: Review and approve this proposal
2. **Design Review**: Review `design.md` for architectural details
3. **Implementation**: Execute `tasks.md` sequentially
4. **Validation**: Run `openspec validate fix-manga-cli --strict`
5. **Testing**: Manual testing with `uv run manga-tupi` and error scenarios
6. **Documentation**: Update README with manga usage examples
7. **Integration**: Ensure anime and manga modes work together

---

**Estimated Scope**: Medium refactor (6-8 hours implementation + testing)

**Risk Level**: Low (isolated to manga mode, doesn't affect anime)

**Rollback Plan**: Old `manga_tupi.py` can be restored if needed; anime mode unaffected
