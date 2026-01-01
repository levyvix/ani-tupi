# Tasks: Modular Architecture Refactoring

## Phase 1: Create Directory Structure (No Breaking Changes)

- [ ] **Create core/ directory**
  - Create `core/__init__.py` (empty)
  - Validation: Directory exists

- [ ] **Create ui/ directory**
  - Create `ui/__init__.py` (empty)
  - Validation: Directory exists

## Phase 2: Migrate History Management

- [ ] **Create core/history_service.py**
  - Move `load_history()` from main.py (line 1078)
  - Move `save_history()` from main.py (line 1241)
  - Move `reset_history()` from main.py (line 1270)
  - Add module docstring explaining purpose
  - Update imports: use `from config import get_data_path`
  - Validation: `uv run python -c "from core.history_service import load_history; print('OK')"`

- [ ] **Test history service works**
  - Import in Python REPL
  - Call `load_history()`
  - Verify returns dict
  - Validation: No import errors, function returns expected type

## Phase 3: Migrate AniList Service

- [ ] **Move anilist.py to core/anilist_service.py**
  - Copy `anilist.py` → `core/anilist_service.py`
  - Update imports in new file (no external changes yet)
  - Validation: File exists in new location

- [ ] **Update AniList imports throughout codebase**
  - Find all `from anilist import` or `import anilist`
  - Change to `from core.anilist_service import`
  - Files to update: main.py, anilist_menu.py, anilist_discovery.py
  - Validation: `rg "from anilist import|import anilist" --type py` returns no results

- [ ] **Delete old anilist.py**
  - Remove `anilist.py` from project root
  - Validation: File no longer exists

## Phase 4: Migrate AniList Menus

- [ ] **Move anilist_menu.py to ui/anilist_menus.py**
  - Copy `anilist_menu.py` → `ui/anilist_menus.py`
  - Update imports: `from core.anilist_service import`
  - Update imports: `from ui.components import menu, loading`
  - Validation: No import errors when importing new module

- [ ] **Update anilist_menu imports in main.py**
  - Change `from anilist_menu import` → `from ui.anilist_menus import`
  - Validation: `rg "from anilist_menu import|import anilist_menu" --type py` returns empty

- [ ] **Delete old anilist_menu.py**
  - Remove `anilist_menu.py` from project root
  - Validation: File no longer exists

## Phase 5: Consolidate UI Components

- [ ] **Create ui/components.py**
  - Copy `menu.py` content to `ui/components.py`
  - Copy `loading.py` content to `ui/components.py`
  - Add module docstring: "Reusable UI components: menu(), loading()"
  - Keep both functions in same file (they're small)
  - Validation: Both functions present in new file

- [ ] **Update menu imports throughout codebase**
  - Find all `from menu import` or `import menu`
  - Change to `from ui.components import menu`
  - Find all `from loading import` or `import loading`
  - Change to `from ui.components import loading`
  - Files to update: main.py, repository.py, manga_service.py, etc
  - Validation: `rg "^from menu import|^import menu|^from loading import|^import loading" --type py` returns no matches

- [ ] **Delete old menu.py and loading.py**
  - Remove `menu.py` from project root
  - Remove `loading.py` from project root
  - Validation: Files no longer exist

## Phase 6: Create Anime Service

- [ ] **Create core/anime_service.py with search functions**
  - Create file with module docstring
  - Move `normalize_anime_title()` from main.py (line 52)
  - Move `load_anilist_mapping()` from main.py (line 21)
  - Move `save_anilist_mapping()` from main.py (line 31)
  - Update imports in new file
  - Validation: `uv run python -c "from core.anime_service import normalize_anime_title; print('OK')"`

- [ ] **Add playback flow functions to anime_service**
  - Move `offer_sequel_and_continue()` from main.py (line 132)
  - Move `switch_anime_source()` from main.py (line 694)
  - Update imports to use `from ui.components import menu`
  - Update imports to use `from core.history_service import`
  - Validation: No import errors

- [ ] **Add anime flow orchestration functions**
  - Move `anilist_anime_flow()` from main.py (line 211)
  - Move `search_anime_flow()` from main.py (line 840)
  - Rename to remove `_flow` suffix (keep as `anilist_anime()`, `search_anime()`)
  - Update all internal function calls to use new service imports
  - Validation: Functions work when called directly

## Phase 7: Create Menu System

- [ ] **Create ui/menu_system.py with MenuRegistry**
  - Create `MenuRegistry` class with `__init__`, `register()`, `get_labels()`, `handle()` methods
  - Add docstrings to all methods
  - Add duplicate detection in `register()` method
  - Create global instance: `menu_registry = MenuRegistry()`
  - Validation: Can import and use registry

- [ ] **Create ui/anime_menus.py**
  - Create file with module docstring
  - Move `show_main_menu()` logic from main.py (line 829)
  - Convert to menu registry pattern
  - Register options: "Buscar Anime", "Continuar Assistindo", "AniList", "Gerenciar Cache", "Sair"
  - Import flow functions from `core.anime_service`
  - Validation: Can import module without errors

## Phase 8: Create Thin CLI Entry Point

- [ ] **Create cli.py**
  - Create new file with module docstring
  - Move `cli()` function from main.py (line 1296)
  - Move `main()` function from main.py (line 927)
  - Update imports to use new structure:
    - `from core.anime_service import`
    - `from ui.menu_system import menu_registry`
    - `from ui.anime_menus import show_main_menu`
  - Keep argparse logic
  - Load plugins before showing menu
  - Validation: `uv run python cli.py --help` works

- [ ] **Update pyproject.toml entry points**
  - Change `ani-tupi = "main:cli"` → `ani-tupi = "cli:cli"`
  - Keep `manga-tupi = "manga_tupi:main"` unchanged
  - Validation: `uv run ani-tupi --help` works

## Phase 9: Integration Testing

- [ ] **Test anime search flow**
  - Run: `uv run ani-tupi`
  - Select "Buscar Anime"
  - Search for "dandadan"
  - Select anime
  - Select episode
  - Verify video player launches
  - Validation: End-to-end flow works

- [ ] **Test continue watching**
  - Run: `uv run ani-tupi`
  - Select "Continuar Assistindo"
  - Verify history shows
  - Select anime
  - Verify jumps to correct episode
  - Validation: History persistence works

- [ ] **Test AniList integration**
  - Run: `uv run ani-tupi`
  - Select "AniList"
  - Browse trending
  - Select anime
  - Watch episode
  - Verify AniList progress syncs
  - Validation: AniList sync works

- [ ] **Test cache management**
  - Run: `uv run ani-tupi`
  - Select "Gerenciar Cache"
  - Clear cache for specific anime
  - Search again
  - Verify new results cached
  - Validation: Cache system works

- [ ] **Test CLI arguments**
  - Test: `uv run ani-tupi --help`
  - Test: `uv run ani-tupi -q "dandadan"`
  - Test: `uv run ani-tupi --continue-watching`
  - Test: `uv run ani-tupi --clear-cache`
  - Test: `uv run ani-tupi anilist`
  - Validation: All CLI modes work

## Phase 10: Cleanup Old Code

- [ ] **Verify main.py is unused**
  - Check `pyproject.toml` uses `cli:cli`
  - Check no imports of `main` module exist
  - Validation: `rg "from main import|import main" --type py` returns no results (except cli.py's own content)

- [ ] **Delete old main.py**
  - Remove `main.py` from project root
  - Validation: File no longer exists, `uv run ani-tupi` still works

- [ ] **Update CLAUDE.md documentation**
  - Update "Architecture Deep Dive" section
  - Document new directory structure
  - Update "Key Files Reference" section
  - Add new sections for core/ and ui/
  - Validation: Documentation matches new structure

## Phase 11: Final Validation

- [ ] **Run linter**
  - Execute: `uvx ruff check .`
  - Fix any import-related warnings
  - Validation: No critical errors

- [ ] **Test CLI installation**
  - Run: `uv tool install --reinstall .`
  - Test: `ani-tupi --help`
  - Test: `ani-tupi -q "test"`
  - Validation: Installed CLI works

- [ ] **Verify no breaking changes**
  - All original CLI commands work
  - All original functionality preserved
  - No new dependencies added
  - Validation: Behavior identical to pre-refactor

- [ ] **Update tasks.md**
  - Mark all tasks as completed: `- [x]`
  - Validation: All checkboxes checked

## Dependencies Between Tasks

**Sequential dependencies:**
- Phase 1 must complete before all other phases (need directories)
- Phase 2-6 can run in parallel (independent modules)
- Phase 7 depends on Phase 6 (needs anime_service functions)
- Phase 8 depends on Phase 7 (needs menu_registry)
- Phase 9 depends on Phase 8 (needs working CLI)
- Phase 10 depends on Phase 9 (verify old code unused)
- Phase 11 depends on Phase 10 (final validation)

**Parallelizable:**
- Phases 2, 3, 4, 5 are independent (different files)
- Can work on history + AniList + UI components simultaneously

## Estimated Effort

**Total tasks**: 38 tasks
**Estimated time**: 3-4 hours for experienced developer
**Complexity**: Medium (mostly moving code, updating imports)
**Risk level**: Low (pure refactoring, no logic changes)

## Rollback Procedure

If any phase fails:

1. **Before Phase 10**: Old code still exists, just revert new files
2. **After Phase 10**: Use git to restore main.py
3. **Nuclear option**: `git revert <commit-hash>` on entire change

## Success Metrics

- [ ] All 38 tasks completed
- [ ] Zero functionality regressions
- [ ] main.py deleted (or reduced to <100 lines)
- [ ] `uv run ani-tupi` works identically to before
- [ ] Code organized in clear directory structure
- [ ] Adding new menu option requires <10 lines of code
