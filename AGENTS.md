
# AGENTS.md - Development Guide for AI Assistants

This file provides essential guidance for AI agents working in the ani-tupi codebase.

## Build & Development Commands

### Setup & Installation
```bash
# Install dependencies (ALWAYS use UV, never pip)
uv sync

# Install as global CLI for testing
python3 install-cli.py

# Or use UV tool install
uv tool install --force .

# Uninstall global CLI
uv tool uninstall ani-tupi
```

### Running the Application
```bash
# Main anime CLI
uv run ani-tupi
uv run ani-tupi --query "dandadan"
uv run ani-tupi --continue-watching
uv run ani-tupi anilist

# Manga CLI
uv run manga_tupi

# Debug mode
uv run main.py --debug
```

### Testing Commands
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_range_parser.py

# Run single test function
uv run pytest tests/test_range_parser.py::TestRangeParserEmpty::test_empty_input_no_history -v

# Run with coverage
uv run pytest --cov=. --cov-report=html

# Run by marker
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m slow
```

### Linting & Formatting
```bash
# Check code (check only, no auto-fix)
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# Type checking (optional, mypy is lenient)
uv run mypy .
```

### Building & Distribution
```bash
# Build standalone executable
python3 install-cli.py  # Creates dist/ani-tupi

# Just commands (preferred)
just build
just install
just test
just lint
just format
```

### Dependency Management
```bash
# Add dependencies (NEVER edit pyproject.toml directly)
uv add package-name
uv add --dev dev-package-name

# Update all dependencies
uv sync --upgrade

# Remove dependency
uv remove package-name

# Run script with additional packages
uv run --with extra-package script.py
```

## Code Style Guidelines

### Python Version & Target
- **Python**: 3.12+ (specified in pyproject.toml)
- **Line length**: 100 characters (Ruff configuration)
- **Target**: Modern Python patterns with type hints where practical

### Import Organization
```python
# Standard library imports first
import os
import sys
from pathlib import Path
from typing import Optional, List

# Third-party imports next
import requests
from pydantic import BaseModel
from rich.progress import track

# Local imports last
from models.config import settings
from services.anime_service import AnimeService
from utils.exceptions import AniTupiError
```

### Type Annotations
- **Use type hints** for function signatures and class attributes
- **Optional types**: Use `Optional[str]` instead of `str | None` for older Python compatibility
- **Collections**: Prefer `list[str]`, `dict[str, int]` over `List[str]`, `Dict[str, int]`
- **Return types**: Always annotate function returns, especially for public APIs
- **Complex types**: Use Pydantic models for data transfer objects

### Naming Conventions
- **Files**: snake_case (e.g., `anime_service.py`, `range_parser.py`)
- **Classes**: PascalCase (e.g., `AnimeService`, `MangaDexClient`)
- **Functions/variables**: snake_case (e.g., `get_episodes()`, `last_chapter`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DEFAULT_CACHE_TTL`)
- **Private**: Prefix with underscore (e.g., `_internal_method()`)
- **Exceptions**: End with "Error" (e.g., `ScraperError`, `CacheError`)

### Error Handling Patterns
```python
# Use custom exceptions from utils.exceptions
from utils.exceptions import ScraperError, AniTupiError

try:
    result = risky_operation()
except NetworkError as e:
    logger.error(f"Network failure: {e}")
    raise ScraperError(f"Failed to fetch data: {e}") from e

# Blind exceptions are acceptable in this codebase (per ruff config)
except Exception:
    logger.error("Unexpected error occurred")
    raise AniTupiError("Operation failed")
```

### Pydantic Models
- **All data structures** should inherit from `BaseModel`
- **Validation**: Use Pydantic validators for complex rules
- **Fields**: Use `Field()` for descriptions and constraints
- **Strict mode**: Not enforced, but validate URLs and required fields

### Service Layer Pattern
```python
# Services handle business logic, commands handle UI flow
class AnimeService:
    def search_anime(self, query: str) -> List[AnimeMetadata]:
        """Search for anime across all enabled scrapers."""

    def get_episodes(self, anime: AnimeMetadata) -> List[EpisodeData]:
        """Fetch episode list for specific anime."""
```

### Configuration Management
- **Centralized settings**: `from models.config import settings`
- **Environment variables**: Use `ANI_TUPI__*` pattern (Pydantic Settings)
- **No hardcoded values**: Use settings for all configurable behavior
- **Plugin preferences**: Stored in JSON files, managed via loader

### File I/O & Persistence
- **JSON storage**: Use `~/.local/state/ani-tupi/` (XDG standard)
- **Atomic operations**: Write to temp file first, then rename
- **Error handling**: Use `PersistenceError` from `utils.exceptions`
- **Pathlib**: Prefer `Path` over `os.path` when practical

### Plugin System
- **Auto-discovery**: Plugins in `scrapers/plugins/` are loaded automatically
- **Protocols**: Use structural typing, no inheritance required
- **Languages**: Each plugin specifies supported languages
- **Preferences**: Store user preferences in JSON files

### Testing Guidelines
- **Fixtures**: Use `pytest.fixture` for setup/teardown
- **Markers**: Use `@pytest.mark.unit`, `@pytest.mark.integration`, etc.
- **Mocking**: Use `unittest.mock` for external dependencies
- **Temp files**: Use `tempfile` for file operations in tests
- **Coverage**: Focus on critical paths, not 100% coverage

### Logging & Debugging
- **Loguru**: Centralized logging configuration in `utils/logging.py`
- **Debug mode**: Use `--debug` flag for verbose output
- **Structured logging**: Include context and error details
- **Performance**: Log slow operations, cache hits/misses

### Import Dependencies by Layer
```
Commands → Services → Models/Utils → External libs
```
- **Commands**: Handle user flow, no business logic
- **Services**: Business logic, orchestration
- **Models**: Data structures, validation
- **Utils**: Helpers, utilities, low-level operations

### Common Patterns
```python
# Menu interaction (InquirerPy)
from ui.components import menu, loading
with loading("Searching..."):
    results = service.search(query)
choice = menu(results, msg="Select anime:")

# Cache operations
from utils.cache_manager import get_cached, set_cached
cached = get_cached(key)
if not cached:
    data = fetch_fresh_data()
    set_cached(key, data, ttl=3600)

# Progress tracking
from rich.progress import track
for item in track(items, description="Processing..."):
    process_item(item)
```

## Project Architecture

### Directory Structure
```
ani-tupi/
├── main.py                 # CLI entry point
├── manga_tupi.py          # Manga CLI entry point
├── models/                # Pydantic data models
├── commands/              # CLI command handlers
├── services/              # Business logic layer
├── scrapers/              # Plugin system for sources
├── ui/                    # Menu and UI components
├── utils/                 # Utilities and helpers
├── tests/                 # pytest test files
├── manga_scrapers/        # Manga plugin system
└── pyproject.toml         # Project configuration
```

### Key Components
- **Main entry**: `main.py` → CLI parsing → command routing
- **Plugin loader**: `scrapers/loader.py` auto-discovers scraper plugins
- **Service layer**: Business logic separated from UI/CLI
- **Configuration**: Centralized Pydantic settings with env var support
- **Cache**: SQLite via diskcache for scraper results
- **Persistence**: JSON files in XDG state directory
- **UI**: Rich + InquirerPy for terminal interfaces

### External Dependencies
- **Video**: MPV player with IPC support
- **Web**: Playwright/Selenium for scraping
- **HTTP**: requests/httpx for API calls
- **Images**: Pillow for PDF conversion
- **Validation**: Pydantic v2 for data models
- **UI**: Rich for formatting, InquirerPy for menus
- **Testing**: pytest with asyncio and coverage support

### Important Notes
- **UV required**: Always use `uv run` for Python commands
- **No pip editing**: Use `uv add/remove` for dependency changes
- **Ruff config**: Custom rules ignore less critical issues
- **Type checking**: MyPy is lenient, focus on critical paths
- **Plugin system**: Auto-discovery, no manual registration needed
- **AniList integration**: GraphQL API with OAuth flow
- **Manga support**: PDF generation, reader detection
- **Cache strategy**: 7-day TTL for scraper results
- **Error handling**: Custom exception hierarchy

Remember: This is a Brazilian Portuguese application, but code comments should be in English.
