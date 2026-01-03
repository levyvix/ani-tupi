# Design: Modular Architecture Refactoring

## Architectural Patterns

### 1. Service Layer Pattern

**Philosophy**: Separate business logic from UI and data access.

**Implementation**:
```
core/
├── anime_service.py      # Orchestrates anime search → episode selection → playback
├── history_service.py    # History CRUD operations
└── anilist_service.py    # AniList API interactions (renamed from anilist.py)
```

**Service Characteristics**:
- Pure functions where possible (no hidden state)
- Clear input/output contracts
- Use repository singleton for data (keep existing pattern)
- Use config for settings (keep existing pattern)
- No circular dependencies

**Example - anime_service.py**:
```python
# core/anime_service.py
from repository import rep
from models import VideoUrl
from ui.components import menu, loading

def search_anime(query: str) -> list[str]:
    """Search for anime across all plugins.

    Returns: List of anime titles
    """
    with loading(f"Buscando '{query}'..."):
        rep.search_anime(query)
    return rep.get_anime()

def get_episodes(anime: str) -> list[str]:
    """Get episode list for anime.

    Returns: List of episode titles
    """
    with loading("Carregando episódios..."):
        rep.search_episodes(anime)
    return rep.get_episode_titles(anime)

def get_video_url(anime: str, episode_idx: int) -> VideoUrl | None:
    """Extract playback URL for episode.

    Returns: VideoUrl model or None if failed
    """
    with loading("Buscando vídeo..."):
        return rep.search_player(anime, episode_idx)
```

### 2. Menu Registry Pattern

**Philosophy**: Decouple menu options from menu rendering. Make adding new options trivial.

**Implementation**:
```python
# ui/menu_system.py
from collections.abc import Callable

class MenuRegistry:
    def __init__(self):
        self._items: dict[str, Callable] = {}

    def register(self, label: str, handler: Callable):
        """Register a menu option.

        Args:
            label: Display text in menu
            handler: Function to call when selected
        """
        self._items[label] = handler

    def get_labels(self) -> list[str]:
        return list(self._items.keys())

    def handle(self, label: str):
        """Execute handler for selected option."""
        return self._items[label]()

# Global registry
menu_registry = MenuRegistry()
```

**Usage**:
```python
# ui/anime_menus.py
from ui.menu_system import menu_registry
from core.anime_service import search_anime, get_episodes

def anime_search_flow():
    query = input("Buscar: ")
    anime_list = search_anime(query)
    # ... rest of flow

menu_registry.register("Buscar Anime", anime_search_flow)
menu_registry.register("Continuar Assistindo", continue_watching_flow)
```

**Main Menu**:
```python
# cli.py
from ui.menu_system import menu_registry
from ui.components import menu

def main_menu():
    while True:
        choice = menu(menu_registry.get_labels(), "ani-tupi")
        if choice == "Sair":
            break
        menu_registry.handle(choice)
```

### 3. Module Organization

**Directory Structure Rationale**:

```
core/          # Business logic - no UI dependencies
├── anime_service.py
├── history_service.py
└── anilist_service.py

ui/            # User interface - depends on core
├── components.py        # menu(), loading() - low-level widgets
├── menu_system.py       # MenuRegistry - menu orchestration
├── anime_menus.py       # Anime flow handlers
└── anilist_menus.py     # AniList flow handlers

plugins/       # Scrapers - no changes
models.py      # Pydantic models - no changes
config.py      # Settings - no changes
repository.py  # Singleton data store - no changes
loader.py      # Plugin discovery - no changes
cli.py         # Entry point - thin wrapper
```

**Dependency Rules**:
1. `core/` can import: `models`, `config`, `repository`, `loader`
2. `ui/` can import: `core/`, `models`, `config`, `repository`
3. `plugins/` can import: `loader`, `repository`, `models`
4. `cli.py` imports: `ui/`, `core/`, `config`, `loader`

**No circular imports because**:
- Core never imports UI
- Plugins never import Core or UI
- Data layer (repository/models/config) imported by everyone

### 4. Migration Strategy

**Phase 1: Create Structure (No Breaking Changes)**
- Create `core/` and `ui/` directories
- Copy (don't move) code to new locations
- Update imports in new files
- Old files still work

**Phase 2: Update Entry Points**
- Create new `cli.py`
- Update `pyproject.toml` to use `cli.py`
- Test CLI works with new structure
- Old `main.py` still exists but unused

**Phase 3: Remove Old Code**
- Delete `main.py`
- Delete `anilist_menu.py`, `menu.py`, `loading.py` (moved to ui/)
- Delete `anilist.py` (moved to core/)
- Run tests

**Rollback Plan**:
- If phase 3 breaks something, revert to phase 2 (both structures coexist)
- If phase 2 breaks, only new files affected - delete them
- Git history preserves old working state

## Alternative Approaches Considered

### Alternative 1: Keep main.py, Add Modules

**Pros**: Less disruptive, smaller change
**Cons**: Doesn't solve "main.py too large" problem, still coupled

**Decision**: Rejected - doesn't achieve modularization goals

### Alternative 2: Full MVC with Classes

**Pros**: Very formal separation of concerns
**Cons**: Adds complexity (controllers, views, models all as classes)

**Decision**: Rejected - over-engineering for this project size

### Alternative 3: Plugin Everything (including menus)

**Pros**: Ultimate flexibility
**Cons**: Too complex for beginners, unnecessary abstraction

**Decision**: Rejected - plugins for scrapers only (current approach works well)

## Trade-offs

### Chosen: Service Layer + Menu Registry

**Pros**:
- Clear boundaries between concerns
- Easy to understand (services are just modules with functions)
- Easy to extend (register new menu options)
- No framework magic (plain Python)
- Testable (services have clear contracts)

**Cons**:
- More files (18 files → 22 files)
- Need to update imports
- Learning new structure (one-time cost)

**Why it's the right choice**: Balances maintainability with simplicity. Beginners can follow the flow from `cli.py → ui/ → core/` easily.

## Edge Cases and Error Handling

### Import Errors During Migration

**Problem**: Moving files breaks imports
**Solution**: Use relative imports within packages, absolute imports across packages

**Example**:
```python
# ui/anime_menus.py
from ui.components import menu  # Absolute (clear)
from core.anime_service import search_anime  # Absolute (clear)
```

### Menu Registry Key Conflicts

**Problem**: Two menus register same label
**Solution**: Registry checks for duplicates, raises clear error

```python
def register(self, label: str, handler: Callable):
    if label in self._items:
        raise ValueError(f"Menu option '{label}' already registered")
    self._items[label] = handler
```

### Service Initialization Order

**Problem**: Services might depend on plugins being loaded
**Solution**: Services use lazy initialization, plugins loaded in cli.py before menu

```python
# cli.py
def cli():
    loader.load_plugins({"pt-br": True})  # Load first
    main_menu()  # Then show menus
```

## Performance Considerations

### Import Cost

**Impact**: More modules = slightly slower startup
**Mitigation**: Lazy imports where possible, Python caches imports
**Measurement**: Expect <10ms increase (negligible for TUI app)

### Menu Registry Overhead

**Impact**: Dictionary lookup instead of if/elif chain
**Mitigation**: O(1) dict lookup is faster than O(n) if/elif for large menus
**Measurement**: Negligible (microseconds)

## Security Considerations

No security changes - this is pure refactoring. Same input validation, same subprocess calls.

## Testing Strategy

### Manual Testing Checklist

After refactoring:
- [ ] `ani-tupi --help` works
- [ ] Search anime works
- [ ] Select episode works
- [ ] Video playback works
- [ ] Continue watching works
- [ ] AniList auth works
- [ ] AniList sync works
- [ ] History persists
- [ ] Cache works

### Future Unit Tests (when test suite exists)

```python
# test_anime_service.py
def test_search_anime():
    results = search_anime("dandadan")
    assert len(results) > 0
    assert any("dan da dan" in r.lower() for r in results)

# test_menu_registry.py
def test_register_menu():
    registry = MenuRegistry()
    registry.register("Test", lambda: "result")
    assert "Test" in registry.get_labels()
    assert registry.handle("Test") == "result"
```

## Documentation Updates

### Files to Update

1. `CLAUDE.md` - Update architecture section with new structure
2. `README.md` - No changes (user-facing unchanged)
3. Docstrings - Add to all service functions

### Code Comments

Add module-level docstrings explaining purpose:

```python
# core/anime_service.py
"""Anime search and playback orchestration.

This module provides high-level functions for:
- Searching anime across all plugins
- Fetching episode lists
- Extracting video URLs
- Managing playback loop

Used by: ui/anime_menus.py
"""
```

## Rollout Plan

### Pre-Deployment

1. Create feature branch: `refactor/modular-architecture`
2. Implement changes following tasks.md
3. Manual testing via `uv run ani-tupi`
4. Code review (check for missed imports)

### Deployment

1. Merge to master
2. Users run `uv tool install --reinstall .`
3. CLI behavior unchanged (transparent refactor)

### Monitoring

Watch for:
- Import errors (check Python version compatibility)
- Performance regression (unlikely but measure startup time)
- User reports of broken functionality

### Rollback

If critical bug found:
1. Revert merge commit
2. Users reinstall previous version
3. Fix issue in feature branch
4. Re-deploy when stable
