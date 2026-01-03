# Proposal: Refactor to Modular Architecture

## Problem Statement

The current codebase has maintainability and extensibility challenges:

1. **main.py is too large (1400 lines)** - Contains business logic, flow control, history management, AniList integration, and CLI parsing mixed together
2. **Tight coupling** - Functions in main.py directly access global repository instance and call various services
3. **Difficult to add menu options** - Menu logic is embedded within flow functions making it hard to extend
4. **Hard to add new features** - No clear separation between different concerns (anime playback, manga, AniList, history)
5. **Testing challenges** - No clear boundaries make unit testing difficult

## Goal

Refactor the codebase to be:
- **Modular** - Clear separation of concerns with dedicated modules for each domain
- **Easy to maintain** - Beginners can understand the structure quickly
- **Easy to extend** - Adding new sources is already easy; make adding menu options equally simple
- **No unnecessary complexity** - Keep it straightforward, avoid over-engineering

## Proposed Solution

### Architecture Overview

Transform from monolithic main.py to a layered architecture:

```
ani-tupi/
├── core/                    # Core business logic
│   ├── __init__.py
│   ├── anime_service.py     # Anime search/playback orchestration
│   ├── history_service.py   # History load/save/reset
│   └── anilist_service.py   # AniList operations (existing anilist.py moves here)
├── plugins/                 # Already good - no changes needed
│   ├── animefire.py
│   └── ...
├── ui/                      # User interface layer
│   ├── __init__.py
│   ├── menu_system.py       # Menu registry + dispatcher
│   ├── anime_menus.py       # Anime-specific menus
│   ├── anilist_menus.py     # AniList menus (existing anilist_menu.py moves here)
│   └── components.py        # Reusable menu components (existing menu.py + loading.py)
├── models.py                # Already good - Pydantic models
├── config.py                # Already good - Pydantic settings
├── repository.py            # Already good - singleton data store
├── loader.py                # Already good - plugin discovery
├── cli.py                   # NEW: Thin CLI entry point
└── main.py                  # REMOVED: Logic moved to services + cli.py
```

### Key Design Decisions

1. **Service Layer Pattern**
   - `anime_service.py` - Encapsulates anime search, episode selection, playback loop
   - `history_service.py` - All history operations (load/save/reset/continue watching)
   - `anilist_service.py` - Rename existing `anilist.py` for consistency
   - Each service has clear input/output, easy to test

2. **Menu System Registry**
   - `menu_system.py` exports a `MenuRegistry` class
   - New menu options registered via decorators or simple dict
   - Example: `registry.add("Continuar Assistindo", handler=continue_watching_flow)`
   - Main menu auto-generated from registry

3. **No Over-Engineering**
   - No dependency injection frameworks
   - No complex metaclasses or decorators
   - Simple imports and function calls
   - Keep repository as singleton (already works well)

4. **Backward Compatibility**
   - `manga_tupi.py` already separate - no changes needed
   - Plugin interface unchanged
   - Config/models unchanged
   - Only internal refactoring

### What Changes for Users

**Nothing**. This is pure refactoring - same CLI interface, same behavior.

### What Changes for Developers

**Adding new menu options becomes trivial:**

Before (modify main.py line 829):
```python
def show_main_menu():
    options = [
        "Buscar Anime",
        "Continuar Assistindo",
        # ... lots of scattered logic ...
    ]
    # Handler logic embedded in huge match/if statements
```

After (add to ui/anime_menus.py):
```python
from ui.menu_system import menu_registry

@menu_registry.register("Buscar Novo Anime")
def search_new_anime_flow():
    from core.anime_service import AnimeService
    service = AnimeService()
    # ... clean, isolated logic ...
```

**Adding new sources (plugins):**
Already easy - this refactor doesn't change plugin system.

## Benefits

1. **Easier to understand** - New developers see clear folder structure
2. **Easier to test** - Services have clear boundaries
3. **Easier to extend** - Add menu options without touching main flow
4. **Better organization** - Related code grouped together
5. **No added complexity** - Simple Python modules and functions

## Migration Path

1. Create new directory structure
2. Move history functions to `core/history_service.py`
3. Move anime flow functions to `core/anime_service.py`
4. Move `anilist.py` to `core/anilist_service.py`
5. Move menu functions to `ui/anime_menus.py`
6. Move `anilist_menu.py` to `ui/anilist_menus.py`
7. Rename `menu.py` + `loading.py` to `ui/components.py`
8. Create `ui/menu_system.py` with registry
9. Create `cli.py` as thin entry point
10. Update imports throughout codebase
11. Delete old `main.py`
12. Update `pyproject.toml` entry points

## Risks and Mitigations

**Risk**: Breaking working code during refactor
**Mitigation**: Move code incrementally, test after each move

**Risk**: Import cycles
**Mitigation**: Services only import from models/config/repository, never from each other

**Risk**: Too much abstraction
**Mitigation**: Keep services as simple modules with functions, no classes unless needed

## Success Criteria

- [ ] All existing functionality works unchanged
- [ ] main.py reduced from 1400 lines to <100 lines (cli.py)
- [ ] Clear separation: core/, ui/, plugins/
- [ ] Adding new menu option takes <10 lines of code
- [ ] A beginner can navigate the codebase structure
- [ ] No test failures (when tests exist)
