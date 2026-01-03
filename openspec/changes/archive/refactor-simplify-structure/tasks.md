# Implementation Tasks

**Change ID:** `refactor-simplify-structure`

## Prerequisites
- [ ] Review proposal.md for full context
- [ ] Ensure all tests pass: `uv run pytest`

---

## Phase 1: Create New Directory Structure

### Create Directories
- [ ] Create `commands/` directory with `__init__.py`
- [ ] Create `services/` directory with `__init__.py`
- [ ] Create `utils/` directory with `__init__.py`
- [ ] Create `scrapers/` directory with `__init__.py`
- [ ] Create `models/` directory with `__init__.py`

### Move Files (No Code Changes)
- [ ] Move `core/anime_service.py` → `services/anime_service.py`
- [ ] Move `core/anilist_service.py` → `services/anilist_service.py`
- [ ] Move `core/history_service.py` → `services/history_service.py`
- [ ] Move `repository.py` → `services/repository.py`
- [ ] Move `manga_service.py` → `services/manga_service.py`
- [ ] Move `models.py` → `models/models.py`
- [ ] Move `config.py` → `models/config.py`
- [ ] Move `scraper_cache.py` → `utils/scraper_cache.py`
- [ ] Move `cache_manager.py` → `utils/cache_manager.py`
- [ ] Move `anilist_discovery.py` → `utils/anilist_discovery.py`
- [ ] Move `video_player.py` → `utils/video_player.py`
- [ ] Move `plugins/` directory → `scrapers/plugins/`
- [ ] Move `loader.py` → `scrapers/loader.py`

---

## Phase 2: Update All Imports

### Core Imports
- [ ] Update imports in `services/anime_service.py` (was `core/anime_service.py`)
- [ ] Update imports in `services/anilist_service.py` (was `core/anilist_service.py`)
- [ ] Update imports in `services/history_service.py` (was `core/history_service.py`)
- [ ] Update imports in `services/repository.py` (was `repository.py`)
- [ ] Update imports in `services/manga_service.py` (was `manga_service.py`)

### Utilities Imports
- [ ] Update imports in `utils/plugins.py` (consolidated from `loader.py` + `plugin_manager.py`)
- [ ] Update imports in `utils/scraper_cache.py`
- [ ] Update imports in `utils/cache_manager.py`
- [ ] Update imports in `utils/anilist_discovery.py`
- [ ] Update imports in `utils/video_player.py`

### UI Imports
- [ ] Update imports in `ui/components.py`
- [ ] Update imports in `ui/anilist_menus.py`

### Model Imports
- [ ] Update imports in `models/models.py` (was `models.py`)
- [ ] Update imports in `models/config.py` (was `config.py`)

### Test Imports
- [ ] Update all imports in `tests/` directory to use new module paths

---

## Phase 3: Create New Commands Module

### Create Command Handlers
- [ ] Create `commands/anime.py` - anime search & playback (extract from `main.py::search_anime_flow()`)
- [ ] Create `commands/anilist.py` - anilist menu & sync (extract from `main.py::anilist_main_menu()`)
- [ ] Create `commands/manga.py` - manga mode (consolidate `manga_tupi.py` logic)
- [ ] Create `commands/sources.py` - plugin management (from `plugin_manager.py`)

### Command Handler Implementation
- [ ] Implement `commands/anime.py::anime_command(args)` - takes parsed args, returns control
- [ ] Implement `commands/anilist.py::anilist_command(args)` - anilist browsing & watching loop
- [ ] Implement `commands/manga.py::manga_command(args)` - manga reader flow
- [ ] Implement `commands/sources.py::manage_sources_command()` - plugin enable/disable UI

---

## Phase 4: Consolidate Entry Points

### Create Single Main Entry Point
- [ ] Rewrite `main.py` to:
  - [ ] Parse CLI arguments (anime search, anilist, manga, sources, continue-watching)
  - [ ] Load plugins once at startup
  - [ ] Route to appropriate command handler in `commands/*.py`
  - [ ] Handle error handling and graceful exit
- [ ] Remove `cli.py` (obsolete wrapper)
- [ ] Update `pyproject.toml` entry point to point to `main.py:cli` (not `cli.py:cli`)

### Menu Routing in Main
- [ ] Show main menu if no args provided
- [ ] Menu options: Buscar Anime, Continuar Assistindo, AniList, Mangá, Gerenciar Fontes
- [ ] Route each option to appropriate command handler

---

## Phase 5: Consolidate Utilities

### Merge Loader + Plugin Manager
- [ ] Create `utils/plugins.py` consolidating:
  - [ ] `loader.py::PluginInterface` (ABC)
  - [ ] `loader.py::load_plugins()` function
  - [ ] `plugin_manager.py::plugin_management_menu()`
  - [ ] `plugin_manager.py::enable/disable plugin functions`

### Create Utility Init
- [ ] Create `utils/__init__.py` exporting key functions:
  - [ ] `from .plugins import load_plugins, PluginInterface, plugin_management_menu`
  - [ ] `from .video_player import play_video, select_quality_animefire`
  - [ ] `from .scraper_cache import load_cache, save_cache`

---

## Phase 6: Create Services Init

- [ ] Create `services/__init__.py` exporting:
  - [ ] `from .repository import rep`
  - [ ] `from .history_service import load_history, save_history, reset_history`
  - [ ] `from .anime_service import search_anime_flow, anilist_anime_flow`
  - [ ] `from .anilist_service import AniListClient`
  - [ ] `from .manga_service import MangaDexClient, MangaHistory`

---

## Phase 7: Test & Validation

### Run Test Suite
- [ ] Run `uv run pytest` - all tests pass ✅
- [ ] Run `uv run pytest -v` - check import paths are correct
- [ ] Check for import errors: `python -c "import ani_tupi.main"`

### Manual Testing
- [ ] Test anime search: `uv run main.py -q "Dandadan"`
- [ ] Test continue watching: `uv run main.py --continue-watching`
- [ ] Test AniList: `uv run main.py` → select AniList
- [ ] Test manga: `uv run main.py` → select Mangá
- [ ] Test manage sources: `uv run main.py` → select Gerenciar Fontes
- [ ] Test CLI install: `uv tool install --reinstall .`
- [ ] Test CLI global: `ani-tupi -q "test"`

---

## Phase 8: Cleanup & Documentation

### Remove Old Files
- [ ] Delete `cli.py` (now consolidated into `main.py`)
- [ ] Delete `loader.py` from root (now `scrapers/loader.py`)
- [ ] Delete `plugin_manager.py` (now consolidated in `utils/plugins.py`)
- [ ] Delete `core/__init__.py` (core directory no longer exists)
- [ ] Delete `core/` directory

### Update Documentation
- [ ] Update `CLAUDE.md` with new module structure
- [ ] Update any module docstrings with new paths
- [ ] Create `ARCHITECTURE.md` explaining new structure

### Update pyproject.toml
- [ ] Ensure entry point points to correct location: `ani-tupi = "main:cli"`
- [ ] Verify all package includes are correct

---

## Phase 9: Final Verification

### Before Merge
- [ ] All tests pass: `uv run pytest --cov`
- [ ] No import errors: `python -m py_compile main.py commands/*.py services/*.py utils/*.py ui/*.py`
- [ ] CLI works: `uv run ani-tupi --help`
- [ ] Git status clean: `git status`
- [ ] Ready for PR review

---

## Rollback Plan

If issues arise:
1. `git reset --hard HEAD` - revert all changes
2. `uv sync` - reinstall original dependencies
3. `uv tool install --reinstall .` - reinstall CLI tool

## Notes

- **Parallel Work:** Phases 1-2 can be done in parallel with careful testing
- **No Breaking Changes:** All user-facing commands remain identical
- **Plugin Interface:** No changes to `PluginInterface` ABC
- **Import Order:** Test imports frequently to catch circular dependencies early
