# Module Organization Specification

**Capability:** Module Structure & Code Organization
**Change ID:** refactor-simplify-structure

## MODIFIED Requirements

### Requirement: Clear Module Hierarchy

#### Before State
```
ani-tupi/
├── repository.py         # Root level - unclear home
├── loader.py             # Root level - plugin loading
├── plugin_manager.py     # Root level - plugin UI
├── anilist_discovery.py  # Root level - AniList utilities
├── cache_manager.py      # Root level - caching
├── scraper_cache.py      # Root level - more caching
├── video_player.py       # Root level - video playback
├── models.py             # Root level - data models
├── config.py             # Root level - configuration
├── main.py               # Root level - main controller
├── cli.py                # Root level - CLI wrapper
├── manga_tupi.py         # Root level - manga mode
├── manga_service.py      # Root level - manga service
├── core/                 # Business logic (inconsistent with root)
├── plugins/              # Scrapers (scattered)
└── ui/                   # UI layer (good organization)
```

#### After State
```
ani-tupi/
├── main.py               # Single entry point
├── commands/             # Command handlers
│   ├── anime.py
│   ├── anilist.py
│   ├── manga.py
│   └── sources.py
├── services/             # Business logic (organized)
│   ├── anime_service.py
│   ├── anilist_service.py
│   ├── history_service.py
│   ├── manga_service.py
│   └── repository.py
├── utils/                # Utilities (consolidated)
│   ├── plugins.py
│   ├── video_player.py
│   ├── scraper_cache.py
│   ├── cache_manager.py
│   └── anilist_discovery.py
├── scrapers/             # Plugin system (organized)
│   ├── loader.py
│   └── plugins/
├── models/               # Data models (organized)
│   ├── models.py
│   └── config.py
├── ui/                   # UI layer (unchanged)
│   ├── components.py
│   └── anilist_menus.py
└── tests/                # Testing (unchanged)
```

#### Scenario: Verify commands directory exists
```bash
$ ls -d ani-tupi/commands
ani-tupi/commands/ exists with anime.py, anilist.py, manga.py, sources.py
```

#### Scenario: Verify services directory
```bash
$ ls ani-tupi/services/
anime_service.py  anilist_service.py  history_service.py  manga_service.py  repository.py
```

#### Scenario: Verify utils directory
```bash
$ ls ani-tupi/utils/
plugins.py  video_player.py  scraper_cache.py  cache_manager.py  anilist_discovery.py
```

#### Scenario: Verify old files removed
```bash
$ test ! -f ani-tupi/loader.py
$ test ! -f ani-tupi/plugin_manager.py
$ test ! -f ani-tupi/cli.py
(All pass - files removed)
```

### Requirement: Consolidated Utilities

#### Before State
- Plugin loading: `loader.py` (107 LOC) + `plugin_manager.py` (146 LOC)
- Caching: `cache_manager.py` (210 LOC) + `scraper_cache.py` (101 LOC)
- Video: `video_player.py` (59 LOC)
- Discovery: `anilist_discovery.py` (126 LOC)
- All scattered at root level

#### After State
- All utilities in `utils/` directory
- Related utilities co-located
- Single import path for each utility module

#### Scenario: Import utilities
```python
# Before (scattered)
from loader import load_plugins
from plugin_manager import plugin_management_menu
from cache_manager import get_cache
from scraper_cache import load_cache
from video_player import play_video
from anilist_discovery import auto_discover_anilist_id

# After (organized)
from utils.plugins import load_plugins, plugin_management_menu
from utils.cache_manager import get_cache
from utils.scraper_cache import load_cache
from utils.video_player import play_video
from utils.anilist_discovery import auto_discover_anilist_id
```

#### Scenario: Plugin utilities consolidated
```bash
$ grep -l "PluginInterface\|load_plugins\|plugin_management_menu" ani-tupi/utils/plugins.py
# Single file consolidates all plugin-related code
```

### Requirement: Services Layer Organization

#### Before State
- `core/` directory (some services)
- Root level files (repository.py, manga_service.py)
- Inconsistent organization

#### After State
- All services in `services/` directory
- Clear location for business logic
- Single import path for all services

#### Scenario: Import services
```python
# Before (inconsistent)
from core.anime_service import search_anime_flow
from core.anilist_service import AniListClient
from core.history_service import load_history
from repository import rep
from manga_service import MangaDexClient

# After (organized)
from services.anime_service import search_anime_flow
from services.anilist_service import AniListClient
from services.history_service import load_history
from services.repository import rep
from services.manga_service import MangaDexClient

# Or via __init__.py
from services import repository, anime_service
```

### Requirement: Models & Configuration Organization

#### Before State
- `models.py` at root
- `config.py` at root
- Mixed with other modules

#### After State
- `models/models.py` - Data models
- `models/config.py` - Configuration
- Grouped in dedicated folder

#### Scenario: Import models
```python
# Before
from models import AnimeMetadata, EpisodeData, VideoUrl
from config import settings

# After
from models.models import AnimeMetadata, EpisodeData, VideoUrl
from models.config import settings

# Or via __init__.py re-export
from models import AnimeMetadata, EpisodeData, VideoUrl, settings
```

### Requirement: Scrapers Directory Organization

#### Before State
- `loader.py` at root
- `plugins/` directory scattered

#### After State
- `scrapers/loader.py` - Plugin loader
- `scrapers/plugins/` - Plugin implementations
- Grouped for clarity

#### Scenario: Import plugin loader
```python
# Before
from loader import load_plugins, PluginInterface

# After
from scrapers.loader import load_plugins, PluginInterface
```

## Backward Compatibility Notes

✅ Plugin interface unchanged - `PluginInterface` ABC has same methods
✅ No changes to plugin discovery logic
✅ No changes to data storage
✅ Configuration files and history files unchanged
✅ All imports can use relative or absolute paths

## Implementation Notes

### Import Strategy
1. Create all `__init__.py` files
2. Move files to new locations
3. Update imports in each module
4. Test imports after each category
5. Re-export common items in `__init__.py` for convenience

### Example __init__.py files
```python
# services/__init__.py
from .repository import rep, Repository
from .anime_service import search_anime_flow, anilist_anime_flow
from .anilist_service import AniListClient
from .history_service import load_history, save_history, reset_history
from .manga_service import MangaDexClient, MangaHistory

__all__ = [
    'rep', 'Repository',
    'search_anime_flow', 'anilist_anime_flow',
    'AniListClient',
    'load_history', 'save_history', 'reset_history',
    'MangaDexClient', 'MangaHistory',
]
```
