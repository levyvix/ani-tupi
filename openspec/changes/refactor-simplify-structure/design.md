# Architectural Design

**Change ID:** `refactor-simplify-structure`

## Overview

This design document explains the architectural decisions for simplifying ani-tupi's repository structure through reorganization into clear, modular folders with a unified entry point.

## Current Architecture Problems

### 1. Scattered Entry Points
- `cli.py`: 15 LOC thin wrapper (indirection without value)
- `main.py`: 315 LOC monolithic controller with all flows mixed together
- `manga_tupi.py`: 252 LOC separate CLI for manga mode
- **Result:** Unclear which file to modify for new features; logic duplication

### 2. Root Directory Clutter
15+ Python files at root level make it hard to understand module organization:
```
ani-tupi/
├── repository.py         # Data layer
├── loader.py             # Plugin loading
├── plugin_manager.py     # Plugin UI
├── anilist_discovery.py  # AniList utilities
├── cache_manager.py      # Caching utilities
├── scraper_cache.py      # More caching
├── video_player.py       # Video playback
├── models.py             # Data models
├── config.py             # Configuration
├── main.py               # Main controller
├── cli.py                # CLI wrapper
├── manga_tupi.py         # Manga mode
└── manga_service.py      # Manga service
```

**Problem:** No clear responsibility hierarchy. Is `repository.py` part of services? Where should new utilities go?

### 3. Inconsistent Module Organization
- `core/anime_service.py` - Business logic
- `ui/components.py` - UI layer
- `plugins/animefire.py` - Scrapers
- BUT: `repository.py`, `video_player.py`, `config.py` - At root (no clear home)

**Problem:** Mixed concerns. New developers don't know where to add code.

### 4. Utilities Scattered Across Codebase
- Plugin loading: `loader.py` (107 LOC)
- Plugin UI: `plugin_manager.py` (146 LOC)
- Caching: `cache_manager.py` + `scraper_cache.py` (311 LOC combined)
- AniList discovery: `anilist_discovery.py` (126 LOC)
- Video playback: `video_player.py` (59 LOC)

**Problem:** Finding all plugin-related code requires searching 2+ files; caching logic split across modules.

## Proposed Architecture

### 1. Clear Folder Hierarchy

```
ani-tupi/
├── main.py                   # ← SINGLE entry point (consolidates cli.py + main.py + manga_tupi.py)
│
├── commands/                 # ← Command handlers (new routing layer)
│   ├── anime.py             # Anime search & playback flow
│   ├── anilist.py           # AniList menu & watch loop
│   ├── manga.py             # Manga reader
│   └── sources.py           # Plugin management
│
├── services/                 # ← Business logic (organized, not scattered)
│   ├── anime_service.py      # [moved from core/]
│   ├── anilist_service.py    # [moved from core/]
│   ├── history_service.py    # [moved from core/]
│   ├── manga_service.py      # [moved from root]
│   └── repository.py         # [moved from root] - central data store
│
├── utils/                    # ← Utilities (consolidated from root scatter)
│   ├── plugins.py            # [merged from loader.py + plugin_manager.py]
│   ├── video_player.py       # [moved from root]
│   ├── scraper_cache.py      # [moved from root]
│   ├── cache_manager.py      # [moved from root]
│   └── anilist_discovery.py  # [moved from root]
│
├── scrapers/                 # ← Plugin system (organized, not scattered)
│   ├── loader.py             # PluginInterface ABC + load_plugins()
│   └── plugins/              # Plugin implementations
│       ├── animefire.py
│       └── animesonlinecc.py
│
├── models/                   # ← Data models (organized)
│   ├── config.py             # [moved from root]
│   └── models.py             # [moved from root]
│
├── ui/                       # ← UI layer (unchanged)
│   ├── components.py
│   └── anilist_menus.py
│
└── tests/                    # ← Testing (unchanged)
```

### 2. Entry Point Consolidation

#### Before: Three Entry Points
```python
# cli.py (15 LOC) - pointless wrapper
from main import cli as main_cli
def cli():
    main_cli()

# main.py (315 LOC) - monolithic controller
def cli():
    # Parse args
    # Show menu
    # Anime flow / AniList flow / Manga flow / Sources flow / Continue-watching flow
    # Playback loop

# manga_tupi.py (252 LOC) - separate CLI
def main():
    # Manga-specific flow
```

**Problem:** Logic for routing to different flows is scattered and duplicated.

#### After: Single Entry Point
```python
# main.py (unified)
def cli():
    # Parse all CLI args once
    parser = argparse.ArgumentParser()
    parser.add_argument('-q', '--query')
    parser.add_argument('--continue-watching', action='store_true')
    parser.add_argument('--manga', action='store_true')
    # ... etc
    args = parser.parse_args()

    # Load plugins once
    loader.load_plugins({"pt-br"})

    # Route to handler or show menu
    if args.query or args.continue_watching:
        commands.anime(args)
    elif args.manga:
        commands.manga(args)
    else:
        # Show main menu
        choice = ui.show_main_menu()
        if choice == "🔍 Buscar":
            commands.anime(args)
        elif choice == "📺 AniList":
            commands.anilist(args)
        elif choice == "📚 Mangá":
            commands.manga(args)
        # ... etc
```

**Benefit:** Single source of truth for all command routing; no duplication.

### 3. Command Handler Pattern

Each command handler is a separate module in `commands/`:

#### `commands/anime.py`
```python
def anime(args):
    """Handle anime search, selection, and playback."""
    # Search anime (uses anime_service)
    # Select episode
    # Get video URL
    # Play video
    # Save history
```

#### `commands/anilist.py`
```python
def anilist(args):
    """Handle AniList browsing and watching loop."""
    # Show AniList menu
    # Loop: Select anime → Watch → Update progress
```

#### `commands/manga.py`
```python
def manga(args):
    """Handle manga reading."""
    # Search manga (uses manga_service)
    # Select chapter
    # Display pages
```

#### `commands/sources.py`
```python
def manage_sources(args):
    """Handle plugin management UI."""
    # Show active sources
    # Enable/disable plugins
```

**Benefit:** Each file handles one user interaction flow; easy to understand and extend.

### 4. Utilities Consolidation

#### Before: Scattered
- Plugin loading + UI: 253 LOC split across `loader.py` + `plugin_manager.py`
- Caching logic: 311 LOC split across `cache_manager.py` + `scraper_cache.py`
- Video playback: `video_player.py` (59 LOC)
- Discovery: `anilist_discovery.py` (126 LOC)

#### After: Organized in `utils/`
```python
# utils/plugins.py (consolidated)
class PluginInterface: ...          # From loader.py
def load_plugins(...): ...          # From loader.py
def plugin_management_menu(): ...   # From plugin_manager.py
def enable_plugin(name): ...        # From plugin_manager.py
def disable_plugin(name): ...       # From plugin_manager.py

# utils/video_player.py
def play_video(url, ...): ...
def select_quality_animefire(...): ...

# utils/scraper_cache.py
def load_cache(): ...
def save_cache(...): ...

# utils/anilist_discovery.py
def auto_discover_anilist_id(...): ...
def get_anilist_metadata(...): ...
```

**Benefit:** All plugin code in one place; all caching logic in one place; single import path.

### 5. Services Layer (Reorganized, Not Changed)

Move services into organized folder:
```python
# Before (scattered across core/ and root)
from core import anime_service
from repository import rep
from manga_service import MangaDexClient

# After (organized under services/)
from services import anime_service, repository
from services.manga_service import MangaDexClient
```

**Benefit:** Clear that these are application services; easy to find all business logic.

## Import Pattern Changes

### Global Imports (main.py)
```python
# Before
import loader
from core import anime_service
from core.history_service import load_history, save_history
from manga_tupi import main as manga_tupi
from repository import rep
from ui.components import loading, menu
from video_player import play_video

# After
from services import repository, anime_service
from services.history_service import load_history, save_history
from utils import plugins, video_player
from ui.components import loading, menu
from commands import anime, anilist, manga, sources
```

**Benefit:** Clearer module relationships; no circular imports between root-level files.

### Service-Level Imports (services/anime_service.py)
```python
# Before
from repository import rep
from video_player import play_video
from ui.components import loading, menu

# After
from services import repository
from utils import video_player
from ui.components import loading, menu
```

**Benefit:** Services know they're part of a `services` package; clear dependencies.

## Plugin System (Unchanged Logic, Better Location)

The plugin system moves to `scrapers/` for better organization:

```python
# Before
import loader  # From root

loader.load_plugins({"pt-br"})

# After
from scrapers import loader

loader.load_plugins({"pt-br"})
```

**Key:** The `PluginInterface` ABC and `load_plugins()` function logic remain identical—only the location changes for organization.

## Configuration & Models (Organized)

```python
# Before
from models import AnimeMetadata
from config import settings

# After
from models.models import AnimeMetadata
from models.config import settings
```

**Note:** Can shorten to `from models import AnimeMetadata` if `models/__init__.py` re-exports.

## Backward Compatibility

### CLI (100% Compatible)
```bash
# All of these work identically before and after
ani-tupi
ani-tupi -q "Dandadan"
ani-tupi --continue-watching
ani-tupi anilist
ani-tupi manga  # Handled by commands/
```

### Plugin System (100% Compatible)
```python
# Plugin interface unchanged
class MyPlugin(PluginInterface):
    name = "myplugin"
    languages = ["pt-br"]

    @staticmethod
    def search_anime(query: str) -> None: ...

    @staticmethod
    def search_episodes(anime: str, url: str, params) -> None: ...

    @staticmethod
    def search_player_src(url_episode: str, container: list, event) -> None: ...

def load(languages_dict):
    if "pt-br" in languages_dict:
        rep.register(MyPlugin)
```

**Only change:** Import path changes from `loader.PluginInterface` to `scrapers.loader.PluginInterface`.

### Configuration & History (100% Compatible)
- No schema changes to history.json or anilist_token.json
- Config path resolution remains identical
- All environment variables work the same

## Testing Strategy

### Import Testing
- Verify all imports resolve: `python -m py_compile main.py commands/*.py services/*.py utils/*.py`
- Check for circular imports: run `python -c "import main"`

### Functional Testing
- Unit tests unchanged (only import paths updated)
- Integration tests unchanged
- E2E tests: run full flows manually

### CLI Testing
- `uv run ani-tupi -q "test"` - Anime search
- `uv run ani-tupi --continue-watching` - Continue watching
- `uv tool install --reinstall .` then `ani-tupi` - Global CLI works

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Circular imports | Use relative imports carefully; test frequently |
| Plugin discovery breaks | `scrapers/loader.py` logic unchanged, just moved |
| Tests fail on import paths | Update test `sys.path` or use new module structure |
| CLI entry point wrong | Test `uv run main.py:cli` and `uv tool install` explicitly |

## Future Benefits

Once this structure is in place:

1. **Easier to add features:** New command? Add `commands/newfeature.py`. New utility? Add `utils/newutility.py`
2. **Cleaner imports:** Related modules grouped together; clear boundaries
3. **Better testing:** Commands can be tested independently by mocking services
4. **Scalability:** If features grow, can easily split `services/` into subfolders (e.g., `services/anime/`, `services/manga/`)
5. **Onboarding:** New developers see clear structure immediately

## Implementation Notes

### File Move Strategy
1. Create all directories first
2. Move files one category at a time (commands, then services, then utils)
3. Update imports after each category
4. Test after each category to catch issues early

### Import Update Order
1. Update service-to-service imports first
2. Update commands imports
3. Update main.py imports
4. Update tests imports
5. Validate no circular imports

### Git Workflow
- Single commit per category move + import updates
- Keep commits small for easier review
- Final cleanup commit removes old files
