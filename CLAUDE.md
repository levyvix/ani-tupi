# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start Commands

All commands use **UV** for Python package management (never pip):

```bash
# Install dependencies
uv sync

# Run ani-tupi
uv run ani-tupi              # Interactive menu
uv run ani-tupi -q "search"  # Search directly

# Run tests
uv run pytest                # All tests
uv run pytest tests/test_repository.py::TestClass::test_method  # Specific test

# Add dependencies (use instead of modifying pyproject.toml)
uv add package-name          # Add runtime dependency
uv add --dev pytest-plugin   # Add dev dependency

# Lint code
uvx ruff check .
uvx ruff format .
```

**Important:** Always use UV, never pip or direct Python commands. For standalone scripts: `uv run --with package1 --with package2 script.py`

---

## Architecture Overview

ani-tupi uses **MVCP (Model-View-Controller-Plugin)** architecture:

### Core Layers

1. **Models Layer** (`models/`)
   - `config.py` - Pydantic v2 settings management (OS-specific paths, AniList, cache)
   - `models.py` - Data classes: `AnimeMetadata`, `EpisodeData`, `MangaMetadata`
   - Central source of truth for data structures

2. **Services Layer** (`services/`)
   - `repository.py` - Singleton containing scraped data, title mappings, and search results
   - `anilist_service.py` - GraphQL API client for AniList OAuth + list operations
   - `history_service.py` - Persistence: anime/manga watch history (JSON files in `~/.local/state/ani-tupi/`)
   - `anime_service.py` - Business logic: search, episode caching, player control
   - `manga_service.py` - MangaDex API client for manga reading

3. **Scrapers** (`scrapers/`)
   - `loader.py` - Plugin system: discovers and loads scraper plugins from `plugins/` directory
   - `plugins/` - Individual scrapers (animefire, animesonlinecc) implementing `PluginInterface`
   - Plugins inherit `PluginInterface` and register with Repository on load
   - Selenium + geckodriver for dynamic site rendering

4. **UI Layer** (`ui/`)
   - `components.py` - Reusable Rich + InquirerPy components (menus, input, progress)
   - `anilist_menus.py` - AniList-specific UI (list navigation, account info)
   - Rich for styling, InquirerPy for interactive selection

5. **Commands** (`commands/`)
   - `anime.py` - Main anime search/watch flow
   - `anilist.py` - AniList menu navigation and auth
   - `manga.py` - Manga search/read flow
   - `sources.py` - Manage active scraper sources

### Data Flow

```
User Input (menu/CLI)
    ↓
Command Handler (commands/anime.py, etc)
    ↓
Service Layer (anime_service.py)
    ↓
Repository (singleton, holds search state)
    ↓
Plugin System (scrapers/loader.py loads plugins)
    ↓
Individual Scrapers (plugins/) → websites
    ↓
Models (AnimeMetadata, EpisodeData)
    ↓
Persistence (history_service.py) → ~/.local/state/ani-tupi/
```

### Key Design Patterns

- **Singleton Repository** - Single source of truth for anime data (in `services/repository.py:13-28`)
- **Plugin Interface** - All scrapers must implement `PluginInterface` with `search()`, `get_episodes()`, `get_stream_url()`
- **Pydantic Models** - Centralized validation via `models.py`
- **Config via Settings** - `models/config.py` handles all environment variables with defaults
- **DiskCache** - `diskcache` library for SQLite-backed scraper cache (better than old JSON approach)

---

## Development Commands

### Running the Application

```bash
# Development mode - run without global installation
uv run ani-tupi

# With debug output
uv run main.py --debug

# Direct query search
uv run main.py -q "dandadan"

# Continue last watched
uv run main.py -c
```

### Testing

```bash
# Run all tests
uv run pytest -v

# Run unit tests only
uv run pytest -m unit

# Run integration tests
uv run pytest -m integration

# Run E2E tests (slower, realistic)
uv run pytest -m e2e

# Run single test file
uv run pytest tests/test_repository.py -v

# Run single test method
uv run pytest tests/test_repository.py::TestClass::test_method -v

# With coverage report
uv run pytest --cov=. --cov-report=term-missing

# Show output + verbose
uv run pytest -v -s

# Run parallel (faster)
uv run pytest -n auto
```

### Code Quality

```bash
# Check style with Ruff
uvx ruff check .

# Auto-fix style issues
uvx ruff format .

# Check specific file
uvx ruff check services/repository.py

# View full diagnostic
uvx ruff check . --show-files
```

### Building & Installation

```bash
# Install as global CLI (development)
uv tool install --force .

# Uninstall global CLI
uv tool uninstall ani-tupi

# Build standalone executable
uv run build.py

# The executable appears in dist/ folder
```

---

## Project Structure Reference

```
ani-tupi/
├── main.py                 # CLI entry point, routes commands
├── models/
│   ├── config.py          # Pydantic settings (environment variables, paths)
│   └── models.py          # Data classes: AnimeMetadata, EpisodeData, etc
├── services/
│   ├── repository.py      # CORE: Singleton holding all search data
│   ├── anilist_service.py # GraphQL client for AniList API
│   ├── history_service.py # Save/load watch history JSON
│   ├── anime_service.py   # Business logic: search, caching, playback
│   └── manga_service.py   # MangaDex API client
├── scrapers/
│   ├── loader.py          # Plugin loader system
│   └── plugins/
│       ├── animefire.py
│       └── animesonlinecc.py
├── commands/              # Command handlers (CLI routes)
│   ├── anime.py
│   ├── anilist.py
│   └── manga.py
├── ui/
│   ├── components.py      # Rich + InquirerPy components
│   └── anilist_menus.py   # AniList UI
├── utils/
│   ├── cache_manager.py   # Cache operations
│   └── anilist_discovery.py  # Fuzzy matching anime titles
├── tests/
│   ├── conftest.py        # Pytest fixtures
│   ├── test_repository.py
│   ├── test_anilist_service.py
│   └── ... (other test files)
├── pyproject.toml         # Dependencies (use 'uv add' to modify)
└── .github/workflows/     # CI/CD automation

Data Storage (persistent):
~/.local/state/ani-tupi/
├── anime_history.json     # Watch history
├── manga_history.json     # Manga read history
├── cache/                 # DiskCache SQLite cache
└── anilist_token.json     # AniList OAuth token
```

---

## Important Architecture Details

### Repository (Singleton)

Located in `services/repository.py` lines 13-28:

- **Only one instance exists per session** - manages all search state
- Stores:
  - `sources` - registered plugin names
  - `anime_to_urls` - anime title → list of source URLs
  - `anime_episodes_titles` - cached episode names per anime
  - `anime_episodes_urls` - cached video URLs per episode
  - `norm_titles` - normalized title → original title mapping
  - `anime_to_anilist_id` - anime title → AniList ID (for caching)

- Called by: `anime_service.py` for search operations
- Must be cleared between searches: `repo.clear_search_results()`

### Plugin System

Located in `scrapers/loader.py`:

- Discovers all `.py` files in `scrapers/plugins/` directory
- Each plugin must implement:
  ```python
  class MyPlugin(PluginInterface):
      name: str  # unique identifier
      def search(self, query: str) -> list[AnimeMetadata]
      def get_episodes(self, anime: AnimeMetadata) -> list[EpisodeData]
      def get_stream_url(self, episode: EpisodeData) -> str
  ```
- On startup: `loader.load_plugins()` registers all plugins with Repository
- Usage: `anime_service.py` searches all registered plugins in parallel using ThreadPoolExecutor

### Configuration System

Located in `models/config.py`:

- **Pydantic v2 BaseSettings** - automatically reads environment variables
- Env var format: `ANI_TUPI__SECTION__KEY` (double underscore)
- Examples:
  ```bash
  ANI_TUPI__ANILIST__CLIENT_ID=12345
  ANI_TUPI__CACHE__DURATION_HOURS=48
  ANI_TUPI__MANGA__OUTPUT_DIRECTORY=~/Mangas
  ```
- OS-specific data paths:
  - Linux/macOS: `~/.local/state/ani-tupi/`
  - Windows: `C:\\Program Files\\ani-tupi`
- Import in code: `from models.config import settings`

### AniList Integration

Located in `services/anilist_service.py`:

- OAuth flow: opens browser for user to authorize, stores token
- GraphQL queries for trending, user lists (Watching, Planning, Completed), status updates
- Token stored at: `~/.local/state/ani-tupi/anilist_token.json`
- Fuzzy matching to find AniList entries when searching via scraper

### Cache System

Located in `services/anime_service.py`:

- **Episode Cache** - stores list of episodes for each anime per source
- **Scraper Cache** - stores anime search results
- **Backed by DiskCache** - SQLite-based, more reliable than JSON
- Cache location: `~/.local/state/ani-tupi/cache/`
- Duration: configurable via `ANI_TUPI__CACHE__DURATION_HOURS`

---

## Testing Guidelines

### Test Organization

All tests in `tests/` folder. Three categories marked with pytest marks:

- **Unit** (`@pytest.mark.unit`) - fast, no external calls
- **Integration** (`@pytest.mark.integration`) - component interactions, mocked APIs
- **E2E** (`@pytest.mark.e2e`) - full workflows, minimal mocking

### Test Files Overview

| File | Type | Coverage |
|------|------|----------|
| `test_repository.py` | Unit | Singleton behavior, anime storage, title normalization |
| `test_models.py` | Unit | Pydantic models validation |
| `test_config.py` | Unit | Configuration loading and defaults |
| `test_history_service.py` | Unit | History JSON persistence |
| `test_plugin_loader.py` | Integration | Plugin discovery and registration |
| `test_anilist_service.py` | Integration | GraphQL queries (mocked API) |
| `test_repository_integration.py` | Integration | Repository + plugins together |
| `test_e2e_search.py` | E2E | Full search → select → cache flow |
| `test_e2e_anilist.py` | E2E | AniList menu + playback flow |

### Common Test Fixtures (in `conftest.py`)

```python
repo_fresh           # Fresh Repository instance
sample_anime_dandadan  # Test anime metadata
sample_episodes_dandadan  # Test episode list
mock_anilist_response_trending  # Mock API response
temp_history_file    # Temporary JSON file for tests
```

### When Adding New Code

1. Add corresponding test file: `tests/test_new_module.py`
2. Add docstring explaining coverage
3. Aim for >70% coverage on new module
4. Use existing fixtures when possible
5. Run locally: `uv run pytest -v` before pushing

---

## Common Tasks

### Adding a New Scraper Plugin

1. Create file: `scrapers/plugins/my_scraper.py`
2. Implement `PluginInterface`:
   ```python
   from scrapers.loader import PluginInterface
   from models.models import AnimeMetadata, EpisodeData

   class MyPlugin(PluginInterface):
       name = "my_scraper"

       def search(self, query: str) -> list[AnimeMetadata]:
           # Return list of AnimeMetadata with url, title, etc
           pass

       def get_episodes(self, anime: AnimeMetadata) -> list[EpisodeData]:
           # Return list of EpisodeData with urls, numbers, titles
           pass

       def get_stream_url(self, episode: EpisodeData) -> str:
           # Return video URL (mpv will play it)
           pass
   ```
3. Plugin auto-loads on startup via `loader.load_plugins()`
4. Add tests: `tests/test_my_scraper.py`

### Adding Configuration Option

1. Edit `models/config.py` - add new field to appropriate Settings class
2. Use Pydantic Field with defaults and validators
3. Access in code: `from models.config import settings; settings.your_new_field`
4. Can override via env var: `ANI_TUPI__SECTION__FIELD_NAME=value`
5. Add test in `tests/test_config.py`

### Modifying Data Models

1. Edit `models/models.py`
2. Update Pydantic model with new fields
3. Add validation if needed
4. Update any code that constructs these models
5. Add/update tests in `tests/test_models.py`

### Adding New Command

1. Create handler in `commands/new_command.py`
2. Import and route in `main.py:cli()` function
3. Call `repo = Repository()` if you need search data
4. Use components from `ui/components.py` for menus
5. Add tests in `tests/test_e2e_new_command.py`

---

## Debugging Tips

### Enable Debug Output

```bash
uv run main.py --debug  # Sets logging level to DEBUG
```

### Inspect Repository State

During development, add:
```python
from services.repository import rep
print(f"Anime found: {rep.get_anime_list()}")
print(f"Active sources: {rep.get_active_sources()}")
```

### Test a Single Component

```bash
# Test just plugin loader
uv run pytest tests/test_plugin_loader.py -v -s

# Test repository with debug output
uv run pytest tests/test_repository.py::TestClass -v -s --tb=short
```

### Check Cache Contents

```python
from models.config import settings
import diskcache
cache = diskcache.Cache(str(settings.cache.cache_dir))
print(list(cache.keys())[:10])  # First 10 cache keys
```

---

## Known Patterns & Conventions

### Naming Conventions

- **Plugin names** - lowercase with underscores: `animefire`, `animesonlinecc`
- **Models** - PascalCase: `AnimeMetadata`, `EpisodeData`
- **Service classes** - PascalCase: `AniListService`, `HistoryService`
- **Functions** - snake_case: `normalize_title()`, `get_anime_list()`

### Import Organization

Grouped in order:
1. Standard library (`os`, `pathlib`, `typing`)
2. External packages (`pydantic`, `requests`, `rich`)
3. Local modules (`models.config`, `services.repository`)

### Error Handling

- Validation errors use Pydantic's `ValidationError`
- File operations catch `FileNotFoundError` and create directories
- Network failures caught and logged (don't crash app)
- Ruff linter configured to allow bare `except` for scraping failures

### Configuration Precedence

1. Environment variable (highest priority): `ANI_TUPI__CACHE__DURATION_HOURS=12`
2. `.env` file in project root
3. Hardcoded defaults in `models/config.py` (lowest priority)

---

## CI/CD & Deployment

### GitHub Actions

- **On push/PR:** Runs `uv sync` → `pytest --cov`
- **Build test:** Validates PyInstaller executable creation
- **Workflow file:** `.github/workflows/ci.yml`

### Manual Testing Before PR

```bash
# Full local CI simulation
uv sync
uv run pytest -v --cov --cov-report=html
uv run build.py  # Test executable creation
```

---

## File Modification Gotchas

### Never Edit These Directly

- `.github/workflows/` - controlled by project
- `pyproject.toml` - use `uv add package_name` instead
- `uv.lock` - generated automatically

### Always Use UV

- Adding dependency? Use `uv add`, not pip
- Running script? Use `uv run`, not `python`
- Never `pip install` - breaks UV's lock file

### Preserve Test Fixtures

- `tests/conftest.py` - shared across all tests, verify changes don't break other tests
- `tests/fixtures/` - JSON mock data, keep format consistent
- Use `repo_fresh` fixture to avoid state pollution

---

## Related Documentation

- **Tests guide:** `tests/README.md`
- **Main README:** `README.md` (installation, usage, legal basis)
- **OpenSpec changes:** `openspec/` (design docs for major refactors)

