# Design: Manga CLI Refactoring

**Change ID:** `fix-manga-cli`

**Document Type:** Architecture & Design Document

## Overview

This document outlines the architectural design for refactoring `manga_tupi.py` to follow ani-tupi MVCP (Model-View-Controller-Plugin) principles and improve user experience with proper menus, loading indicators, and state management.

## Current Architecture Issues

```
Current (Problematic):
┌──────────────────────────────────────────┐
│ manga_tupi.py (ALL LOGIC)                │
│                                          │
│ ├── input() calls (blocks UI)           │
│ ├── Hardcoded config (base_url)         │
│ ├── Direct API calls (requests.get)     │
│ ├── File I/O (image saving)             │
│ ├── UI rendering (menu() calls)         │
│ ├── Image viewer (threading)            │
│ └── History (None - not implemented)    │
│                                          │
└──────────────────────────────────────────┘
                    ↓
        Hard to maintain, test, extend
```

## Proposed Architecture

### MVCP Pattern for Manga Mode

```
┌──────────────────────────────┐
│ CLI Entry (manga_tupi.py)    │
│ ├── Parse arguments          │
│ ├── Orchestrate flow         │
│ └── Call service & menu      │
└────────────────┬─────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌──────────────────┐  ┌──────────────────┐
│ MODEL LAYER      │  │ VIEW LAYER       │
│                  │  │                  │
│ manga_service.py │  │ menu.py          │
│ ├── Search       │  │ (Rich + InquirerPy)
│ ├── Chapters     │  │                  │
│ ├── Pages        │  │ loading.py       │
│ ├── Cache        │  │ (Spinners)       │
│ ├── History      │  │                  │
│ └── Error handle │  │ config.py        │
│                  │  │ (Settings)       │
└──────────────────┘  └──────────────────┘
        ↑                      ▲
        └──────────┬───────────┘
                   │
         Separation of Concerns
         (API logic ≠ UI rendering)
```

### File Structure

**New Service Layer:**

```python
# manga_service.py - NEW FILE

class MangaDexClient:
    """MangaDex API client with proper error handling and caching."""

    def __init__(self, config: MangaSettings):
        self.base_url = config.api_url
        self.cache = MangaCache(config.cache_duration_hours)
        self.languages = config.languages

    def search_manga(self, query: str) -> list[MangaMetadata]:
        """Search for manga by title.

        Uses cache to avoid repeated API calls for same query.
        Raises MangaNotFoundError if no results.
        """

    def get_chapters(self, manga_id: str) -> list[ChapterData]:
        """Fetch chapters for a manga.

        Filters by configured languages.
        Caches chapter list by manga_id.
        """

    def get_chapter_pages(self, chapter_id: str) -> list[str]:
        """Fetch image URLs for a chapter.

        No caching (changes frequently).
        """

class MangaCache:
    """Simple in-memory cache for search results and chapters."""

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""

    def set(self, key: str, value: Any) -> None:
        """Set cached value with TTL."""

class MangaHistory:
    """Reading progress tracker."""

    @staticmethod
    def load() -> dict:
        """Load history from manga_history.json"""

    @staticmethod
    def save(history: dict) -> None:
        """Save history to manga_history.json"""

    @staticmethod
    def get_last_chapter(manga_title: str) -> str | None:
        """Get last read chapter for manga."""

    @staticmethod
    def update(manga_title: str, chapter_number: str) -> None:
        """Update reading progress."""
```

**Refactored CLI:**

```python
# manga_tupi.py - REFACTORED

def main():
    """Main manga CLI entry point."""
    # 1. Initialize service with config
    config = settings.manga
    service = MangaDexClient(config)

    # 2. Search for manga (with spinner)
    query = inquirer.text(message="Pesquise mangá")

    with loading("Buscando mangás..."):
        results = service.search_manga(query)

    # 3. Select manga (Rich menu)
    manga = menu_navigate([r.title for r in results], "Selecione mangá")

    # 4. Load chapters (with spinner and caching)
    with loading("Carregando capítulos..."):
        chapters = service.get_chapters(manga.id)

    # 5. Remember last read chapter
    history = MangaHistory()
    last_chapter = history.get_last_chapter(manga.title)

    # 6. Display chapters with resume hint
    chapter_labels = [
        f"{ch.number} - {ch.title or 'Sem título'}"
        for ch in chapters
    ]

    if last_chapter:
        chapter_labels[0] = f"⮕ Retomar - {chapter_labels[0]}"

    # 7. Chapter selection loop (like anime mode)
    selected_chapter = menu_navigate(chapter_labels, "Selecione capítulo")

    while selected_chapter:
        # 8. Download/display pages (with tqdm progress)
        with loading("Carregando páginas..."):
            pages = service.get_chapter_pages(selected_chapter.id)

        # 9. Save pages to disk
        output_path = config.output_directory / manga.title / selected_chapter.number
        output_path.mkdir(parents=True, exist_ok=True)

        for i, url in enumerate(tqdm(pages)):
            img_data = requests.get(url).content
            (output_path / f"{i:03d}.png").write_bytes(img_data)

        # 10. Open image viewer
        open_viewer(str(output_path))

        # 11. Save reading progress
        history.update(manga.title, selected_chapter.number)

        # 12. Ask for next chapter
        action = menu_navigate(["Próximo", "Sair"], "O que deseja fazer?")
        selected_chapter = next_chapter if action == "Próximo" else None
```

### Configuration Structure

**In `config.py`:**

```python
from pydantic import BaseModel, Field, HttpUrl

class MangaSettings(BaseModel):
    """MangaDex manga reader settings."""

    api_url: HttpUrl = Field(
        default="https://api.mangadex.org",
        description="MangaDex API base URL"
    )

    cache_duration_hours: int = Field(
        default=24,
        ge=1,
        le=72,
        description="How long to cache chapter lists (hours)"
    )

    output_directory: Path = Field(
        default_factory=lambda: Path.home() / "Downloads",
        description="Where to save downloaded manga chapters"
    )

    languages: list[str] = Field(
        default=["pt-br", "en"],
        description="Preferred languages in order (pt-br, en, ja, etc)"
    )

    model_config = ConfigDict(validate_default=True)


class AppSettings(BaseSettings):
    """Application configuration."""

    anilist: AniListSettings = Field(default_factory=AniListSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    manga: MangaSettings = Field(default_factory=MangaSettings)  # NEW
```

**Environment Variables:**

```bash
# Override defaults
export ANI_TUPI__MANGA__API_URL=https://custom-mangadex-mirror.com
export ANI_TUPI__MANGA__CACHE_DURATION_HOURS=48
export ANI_TUPI__MANGA__OUTPUT_DIRECTORY=~/Mangas
export ANI_TUPI__MANGA__LANGUAGES=pt-br,en,ja
```

### Data Models

**In `models.py`:**

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class MangaStatus(str, Enum):
    """Manga publication status."""
    ONGOING = "ongoing"
    COMPLETED = "completed"
    HIATUS = "hiatus"
    CANCELLED = "cancelled"


class MangaMetadata(BaseModel):
    """Manga metadata from MangaDex."""

    id: str  # MangaDex UUID
    title: str
    description: str | None = None
    status: MangaStatus
    year: int | None = None
    cover_url: str | None = None  # Cover image URL
    tags: list[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "uuid",
                "title": "Dandadan",
                "status": "ongoing",
                "cover_url": "https://..."
            }
        }


class ChapterData(BaseModel):
    """Chapter data from MangaDex."""

    id: str  # Chapter UUID
    number: str  # e.g., "42", "42.5" (supports decimals)
    title: str | None = None
    language: str  # e.g., "pt-br", "en"
    published_at: datetime | None = None
    scanlation_group: str | None = None

    def display_name(self) -> str:
        """Format chapter for display.

        Returns:
            "42 - Título" or "42" if no title
        """
        if self.title:
            return f"Cap. {self.number} - {self.title}"
        return f"Cap. {self.number}"


class MangaHistoryEntry(BaseModel):
    """Single entry in reading history."""

    last_chapter: str  # Chapter number (e.g., "42.5")
    last_chapter_id: str | None = None  # MangaDex chapter ID
    timestamp: datetime
    manga_id: str | None = None  # MangaDex manga ID
```

### Error Handling Strategy

**Custom Exceptions:**

```python
class MangaError(Exception):
    """Base manga error."""
    user_message: str  # User-friendly message


class MangaNotFoundError(MangaError):
    """Manga not found in search results."""
    user_message = "Mangá não encontrado. Tente outra pesquisa."


class MangaDexError(MangaError):
    """MangaDex API error (network, rate limit, etc)."""
    user_message = "Erro ao conectar com MangaDex. Verifique sua conexão."


class ChapterNotAvailable(MangaError):
    """Chapter not available in selected languages."""
    user_message = "Capítulo não disponível no idioma selecionado."
```

**Error Handling in CLI:**

```python
try:
    results = service.search_manga(query)
except MangaNotFoundError as e:
    print(f"❌ {e.user_message}")
    return
except MangaDexError as e:
    print(f"⚠️  {e.user_message}")
    print(f"   Detalhes técnicos: {e}")
    return
```

### Caching Strategy

**In-Memory Cache with TTL:**

```python
class MangaCache:
    """Simple in-memory cache for search and chapter data."""

    def __init__(self, ttl_hours: int):
        self.ttl_seconds = ttl_hours * 3600
        self.cache: dict[str, tuple[Any, float]] = {}  # {key: (value, expire_time)}

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        if key not in self.cache:
            return None

        value, expire_time = self.cache[key]
        if time.time() > expire_time:
            del self.cache[key]
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        """Set cached value with TTL."""
        expire_time = time.time() + self.ttl_seconds
        self.cache[key] = (value, expire_time)

    def clear(self) -> None:
        """Clear all cache."""
        self.cache.clear()
```

**Cache Keys:**

```python
# Search results cache
cache_key = f"search:{query.lower()}"

# Chapter list cache
cache_key = f"chapters:{manga_id}"

# Chapter pages (NO CACHE - changes frequently)
# Directly download each time
```

### Flow Diagram

```
User runs: manga-tupi
    │
    ▼
┌─────────────────────────────────────┐
│ 1. Load Configuration               │
│    (from env vars or defaults)      │
│    • API URL, output dir, languages │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 2. Initialize Service               │
│    MangaDexClient(config)           │
│    + Cache + History                │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 3. Get Search Query                 │
│    inquirer.text("Pesquise mangá")  │
│                                     │
│    (Instead of: input())            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 4. Search with Spinner              │
│    with loading("Buscando..."):      │
│        results = search_manga()     │
│                                     │
│    (Check cache first)              │
└─────────────────────────────────────┘
    │
    ├─ Not Found ──┐
    │              ▼ Show error, go back to step 3
    │
    ├─ Found ──────┐
    │              ▼
    ▼
┌─────────────────────────────────────┐
│ 5. Show Manga Options               │
│    menu_navigate(titles)            │
│                                     │
│    (With fuzzy search support)      │
└─────────────────────────────────────┘
    │
    ▼ User selects manga
┌─────────────────────────────────────┐
│ 6. Load Chapters with Spinner       │
│    with loading("Carregando..."):    │
│        chapters = get_chapters()    │
│                                     │
│    (Check cache by manga_id)        │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 7. Display Chapters                 │
│    menu_navigate(chapter_labels)    │
│                                     │
│    (Show "⮕ Retomar" hint if       │
│     reading history exists)         │
└─────────────────────────────────────┘
    │
    ▼ User selects chapter
┌─────────────────────────────────────┐
│ 8. Download Pages                   │
│    with loading("Carregando..."):    │
│        pages = get_chapter_pages()  │
│                                     │
│    for each page:                   │
│        download + save to disk      │
│        show progress with tqdm      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 9. Open Image Viewer                │
│    subprocess.run([viewer, path])   │
│                                     │
│    (Background, doesn't block)      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 10. Save Reading Progress           │
│     history.update(manga, chapter)  │
│     → manga_history.json            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 11. Ask Next Action                 │
│     menu_navigate(["Próximo", ...]) │
│                                     │
│     Yes ─┐ Go to step 8             │
│     No  ──► Exit                    │
└─────────────────────────────────────┘
```

### Key Design Decisions

**1. Why Service Layer?**
- Separates API logic from UI concerns
- Easier to test (mock service)
- Can be reused by future manga plugins
- Follows MVCP pattern

**2. Why In-Memory Cache Instead of File?**
- Simpler implementation
- Fast lookups
- No disk I/O overhead
- Cache cleared on app restart (acceptable)

**3. Why History in JSON?**
- Matches anime mode (consistency)
- Simple key-value structure
- Easy to read/debug
- Can be extended later with more fields

**4. Why Rich + InquirerPy Instead of Curses?**
- Matches anime mode exactly
- Better fuzzy search
- Non-blocking UI
- Cleaner code

**5. Why Not Plugin Architecture for Manga?**
- MangaDex is sufficient for now
- Manga plugins would require different interface
- Can be added later if needed

### Backward Compatibility

- CLI interface unchanged: `manga-tupi` still works
- No breaking changes to existing scripts
- Old manga downloads still accessible

### Testing Strategy

**Unit Tests:**

```python
def test_search_returns_results():
    """Test service.search_manga() with mock API."""

def test_cache_expires():
    """Test cache TTL expiration."""

def test_history_load_save():
    """Test reading progress persistence."""

def test_chapter_display_name():
    """Test chapter formatting for display."""
```

**Integration Tests:**

```python
def test_full_manga_workflow():
    """Test from search to download."""
```

**Manual Tests:**

```bash
# Test search
uv run manga-tupi
# Input: "Dandadan"
# Verify: Shows menu with anime results

# Test download
# Select: Dandadan
# Select: Chapter 1
# Verify: Downloads pages to ~/Downloads/Dandadan/1/

# Test resume
# Run again, select Dandadan
# Verify: Shows "⮕ Retomar - Cap. 1"
```

## Appendix: Migration Checklist

- [ ] Create `manga_service.py` with MangaDexClient
- [ ] Add MangaSettings to `config.py`
- [ ] Add data models to `models.py`
- [ ] Refactor `manga_tupi.py` to use service layer
- [ ] Implement reading history
- [ ] Add loading spinners for API calls
- [ ] Update error handling
- [ ] Test full workflow
- [ ] Update README with manga examples
- [ ] Run linter and type checks
