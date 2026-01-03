# Refactor: Simplify Repository Structure

**Change ID:** `refactor-simplify-structure`
**Status:** Proposal
**Version:** 1.0

## Summary

Consolidate ani-tupi's scattered entry points and utility modules into a clean, modular folder-based structure with a single `main.py` entry point. This reduces code duplication (multiple `loader.py`, `plugin_manager.py`, `anilist_discovery.py` utilities), simplifies navigation, and improves maintainability.

**Goals:**
- Single unified `main.py` entry point for both CLI and script execution
- Clear folder hierarchy: `commands/`, `services/`, `utils/`, `scrapers/`, `ui/`
- Consolidate utility functions into reusable modules
- Remove duplication across entry points (`cli.py`, `manga_tupi.py`, `main.py`)
- Maintain 100% backward compatibility with existing functionality

## Motivation

**Current State:**
- Multiple entry points: `cli.py` (15 LOC, thin wrapper), `main.py` (315 LOC), `manga_tupi.py` (252 LOC)
- Scattered utilities: `loader.py`, `plugin_manager.py`, `anilist_discovery.py`, `cache_manager.py` (separate from core)
- Inconsistent module organization: core services in `core/`, UI in `ui/`, utilities at root
- Code duplication: Menu handling, error messages, plugin loading logic spread across files
- Unclear module responsibilities: What owns anime search? Video playback routing?

**Problems:**
1. **Navigation Friction:** 15+ Python files in root directory (repository.py, loader.py, video_player.py, config.py, models.py, plugin_manager.py, anilist_discovery.py, cache_manager.py, scraper_cache.py, etc.) make it hard to find what to edit
2. **Duplicated Logic:** Plugin loading, menu rendering, and error handling scattered across entry points
3. **Unclear Boundaries:** Where should new features go? No consistent pattern
4. **Import Chaos:** Circular imports between `core/anime_service.py`, `main.py`, and `repository.py`

## Proposal

### New Structure

```
ani-tupi/
├── main.py                          # Single entry point (consolidated)
├── commands/                        # Command handlers (search, watch, anilist, manga, sources)
│   ├── __init__.py
│   ├── anime.py                     # anime search & playback flow
│   ├── anilist.py                   # anilist menu & sync
│   ├── manga.py                     # manga search & reading
│   └── sources.py                   # plugin management UI
├── services/                        # Business logic (unchanged, just organized)
│   ├── __init__.py
│   ├── anime_service.py             # [moved from core/]
│   ├── anilist_service.py           # [moved from core/]
│   ├── history_service.py           # [moved from core/]
│   ├── manga_service.py             # [moved from root]
│   └── repository.py                # [moved from root]
├── utils/                           # Utilities (consolidated from root scatter)
│   ├── __init__.py
│   ├── plugins.py                   # [consolidated from loader.py + plugin_manager.py]
│   ├── scraper_cache.py             # [moved from root]
│   ├── cache_manager.py             # [moved from root]
│   ├── anilist_discovery.py         # [moved from root]
│   └── video_player.py              # [moved from root]
├── scrapers/                        # Plugin system (unchanged logic, better location)
│   ├── __init__.py
│   ├── loader.py                    # PluginInterface ABC + load_plugins()
│   └── plugins/                     # Same as current plugins/
│       ├── animefire.py
│       └── animesonlinecc.py
├── ui/                              # UI layer (unchanged)
│   ├── __init__.py
│   ├── components.py                # menus, loading spinners
│   └── anilist_menus.py             # anilist-specific UI
├── models/                          # Data models (new organization)
│   ├── __init__.py
│   ├── models.py                    # [moved from root]
│   └── config.py                    # [moved from root]
└── tests/                           # Testing (unchanged)
```

### Entry Point Consolidation

**Before:**
- `cli.py`: 15 LOC thin wrapper → `from main import cli as main_cli` (pointless indirection)
- `main.py`: 315 LOC main loop with all flows mixed
- `manga_tupi.py`: 252 LOC separate CLI for manga

**After:**
- `main.py`: Single unified entry point (consolidates `cli.py`, `main.py`, and manga handling)
  - Parses CLI args once
  - Routes to appropriate command handler (`commands/*.py`)
  - All menus, flows, and modes in one place

### Module Consolidation

**Loader + Plugin Manager → `utils/plugins.py`**
- Current: `loader.py` (107 LOC) + `plugin_manager.py` (146 LOC) = 253 LOC
- New: `utils/plugins.py` (single source of truth for all plugin operations)
- Functions: `load_plugins()`, `get_active_sources()`, `plugin_management_menu()`

**Utilities → `utils/`**
- `scraper_cache.py` (101 LOC) → `utils/scraper_cache.py`
- `cache_manager.py` (210 LOC) → `utils/cache_manager.py`
- `anilist_discovery.py` (126 LOC) → `utils/anilist_discovery.py`
- `video_player.py` (59 LOC) → `utils/video_player.py`

**Services → `services/` (organized, single location)**
- `core/anime_service.py` → `services/anime_service.py`
- `core/anilist_service.py` → `services/anilist_service.py`
- `core/history_service.py` → `services/history_service.py`
- `manga_service.py` → `services/manga_service.py`
- `repository.py` → `services/repository.py`

**Commands → `commands/` (new)**
- Extract flows from `main.py` into handlers
- Each command is a separate file (manga, anime, anilist, sources)
- Single responsibility: each file handles one user interaction flow

### Import Simplification

**Before:**
```python
from core import anime_service
from core.history_service import load_history
from repository import rep
from ui.components import loading, menu
from video_player import play_video
```

**After:**
```python
from services import anime_service, repository
from services.history_service import load_history
from utils import video_player
from ui.components import loading, menu
```

## Implementation Approach

### Phase 1: Create New Structure (No Code Changes Yet)
1. Create new directories: `commands/`, `services/`, `utils/`, `scrapers/`, `models/`
2. Move files to new locations (no edits, just mv)
3. Update all imports across codebase

### Phase 2: Consolidate Entry Point
1. Consolidate `cli.py` + `main.py` + `manga_tupi.py` into new single `main.py`
2. Extract flows into `commands/*.py` handlers
3. Update `pyproject.toml` entry points

### Phase 3: Consolidate Utilities
1. Merge `loader.py` + `plugin_manager.py` → `utils/plugins.py`
2. Verify all imports work

### Phase 4: Testing & Cleanup
1. Run full test suite
2. Remove old/duplicate files
3. Update documentation

## Affected Capabilities

- **Core Application Flow** - Entry point and command routing
- **Plugin System** - Loader organization
- **Anime/Manga Playback** - Services organization
- **AniList Integration** - Services organization

## Backward Compatibility

✅ **100% compatible**
- CLI behavior unchanged: `ani-tupi`, `ani-tupi -q "query"`, `ani-tupi anilist`, etc.
- All user-facing commands work identically
- Plugin interface unchanged (`PluginInterface` ABC unchanged)
- No database schema changes
- Configuration files unchanged

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Circular imports during refactoring | Use relative imports carefully; test imports before merging |
| Breaking existing test imports | Update test file imports; tests still pass |
| CLI entry point misconfiguration | Test `uv run ani-tupi` and `uv tool install` after changes |
| Plugin discovery breaks | `scrapers/loader.py` unchanged, just relocated |

## Questions for Approval

1. **Folder naming:** Is `utils/` a good name, or prefer `tooling/`, `helpers/`, `lib/`?
2. **Services organization:** Should `repository.py` stay in services, or move to a separate `data/` folder?
3. **Commands scope:** Should commands handle all routing, or keep some logic in `main.py`?

## Related Changes

- None currently blocking
- No conflicts with existing OpenSpec changes
