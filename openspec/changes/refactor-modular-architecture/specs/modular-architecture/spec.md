# Specification: Modular Architecture

## Overview

The ani-tupi application SHALL be organized using a layered modular architecture that separates concerns into distinct, well-defined modules. This architecture enables maintainability, testability, and extensibility while avoiding unnecessary complexity.

## ADDED Requirements

### Requirement: Service Layer Organization

The application SHALL organize business logic into a service layer located in the `core/` directory.

**Rationale**: Separates business logic from UI and data access, making code easier to understand, test, and maintain.

**Acceptance Criteria**:
- A `core/` directory exists at project root
- All business logic services are located in `core/`
- Services have clear, documented interfaces
- Services import only from: models, config, repository, loader (no UI imports)

#### Scenario: Developer locates anime search logic

**Given** a developer wants to understand how anime searching works
**When** they navigate to the `core/` directory
**Then** they find `anime_service.py` with clearly documented search functions
**And** the service has no dependencies on UI code

#### Scenario: Service function is tested in isolation

**Given** a service function like `search_anime(query: str)`
**When** a developer writes a unit test
**Then** the function can be imported and tested without initializing the UI
**And** the function has clear input/output contracts

### Requirement: UI Layer Organization

The application SHALL organize user interface code into a UI layer located in the `ui/` directory.

**Rationale**: Separates presentation logic from business logic, making UI changes independent of core functionality.

**Acceptance Criteria**:
- A `ui/` directory exists at project root
- All menu and interaction code is located in `ui/`
- UI modules can import from `core/` but not vice versa
- Reusable UI components are in `ui/components.py`

#### Scenario: Developer adds new menu option

**Given** a developer wants to add "Baixar Episódio" menu option
**When** they navigate to `ui/anime_menus.py`
**Then** they can add the option by registering it with the menu registry
**And** the change requires fewer than 10 lines of code

#### Scenario: Menu component is reused

**Given** multiple menu flows need to display selection lists
**When** developers import from `ui/components`
**Then** they can use the same `menu()` function consistently
**And** the menu behavior is standardized across the app

### Requirement: Menu Registry System

The application SHALL provide a menu registry system that allows declarative registration of menu options.

**Rationale**: Decouples menu options from menu rendering, making it trivial to add new options without modifying core menu logic.

**Acceptance Criteria**:
- `ui/menu_system.py` exports a `MenuRegistry` class
- Menu options are registered via `menu_registry.register(label, handler)`
- The registry prevents duplicate labels with clear error messages
- Main menu is auto-generated from registry contents

#### Scenario: New menu option is added

**Given** a developer wants to add a new menu option "Estatísticas"
**When** they call `menu_registry.register("Estatísticas", stats_handler)`
**Then** the option appears in the main menu automatically
**And** selecting it calls the `stats_handler` function

#### Scenario: Duplicate menu option is prevented

**Given** a menu option "Buscar Anime" is already registered
**When** another module tries to register "Buscar Anime"
**Then** the registry raises a `ValueError` with a clear error message
**And** the duplicate registration is prevented

### Requirement: History Service Module

The application SHALL provide a dedicated history service for all history-related operations.

**Rationale**: Centralizes history management logic, making it easier to maintain and extend history features.

**Acceptance Criteria**:
- `core/history_service.py` exists with documented functions
- Functions: `load_history()`, `save_history()`, `reset_history()`
- All history file operations are encapsulated in this module
- Other modules import history functions from this service

#### Scenario: History is loaded at startup

**Given** the application starts
**When** `load_history()` is called from `core/history_service`
**Then** the function returns a dict of anime to [timestamp, episode_idx]
**And** the function handles missing files gracefully

#### Scenario: History is saved after watching

**Given** a user finishes watching an episode
**When** `save_history(anime, episode, anilist_id)` is called
**Then** the function persists the data to the history file
**And** the function creates the directory if it doesn't exist

### Requirement: AniList Service Module

The application SHALL provide a dedicated AniList service for all AniList API operations.

**Rationale**: Consolidates AniList integration logic, making API changes easier to manage.

**Acceptance Criteria**:
- `core/anilist_service.py` exists (renamed from `anilist.py`)
- All AniList GraphQL operations are in this module
- OAuth token management is in this module
- Other modules import AniList functions from this service

#### Scenario: AniList client is imported

**Given** a module needs to interact with AniList
**When** it imports `from core.anilist_service import AniListClient`
**Then** the import succeeds without errors
**And** the client provides documented methods for API operations

### Requirement: Anime Service Module

The application SHALL provide a dedicated anime service for anime search, selection, and playback orchestration.

**Rationale**: Encapsulates anime-related business logic in one place, making the main flow easier to understand.

**Acceptance Criteria**:
- `core/anime_service.py` exists with documented functions
- Functions include: `normalize_anime_title()`, `search_anime_flow()`, `anilist_anime_flow()`
- AniList mapping functions are in this module
- Sequel detection and source switching logic is in this module

#### Scenario: Anime search flow is executed

**Given** a user wants to search for an anime
**When** `search_anime_flow(args)` is called from `core/anime_service`
**Then** the function orchestrates: search → selection → episodes → playback
**And** the function uses repository for data and UI components for interaction

### Requirement: Thin CLI Entry Point

The application SHALL provide a thin CLI entry point that delegates to services and UI modules.

**Rationale**: Keeps the CLI layer simple and focused on argument parsing and flow dispatch.

**Acceptance Criteria**:
- `cli.py` exists at project root with less than 150 lines
- `cli.py` contains only: argparse setup, plugin loading, menu dispatch
- All business logic delegated to `core/` services
- All UI logic delegated to `ui/` modules

#### Scenario: CLI is invoked with search query

**Given** a user runs `ani-tupi -q "dandadan"`
**When** `cli.py` parses the arguments
**Then** it loads plugins via `loader.load_plugins()`
**And** it calls `anime_service.search_anime_flow(args)`
**And** it does not contain embedded business logic

### Requirement: Backward Compatible CLI

The application SHALL maintain full backward compatibility with existing CLI interface.

**Rationale**: Users should not notice any behavior changes; this is an internal refactor.

**Acceptance Criteria**:
- All existing CLI flags work identically (`--help`, `-q`, `--continue-watching`, etc.)
- `pyproject.toml` entry point updated to `cli:cli`
- No new dependencies added
- No changes to user-facing behavior

#### Scenario: Existing CLI commands work

**Given** a user has installed ani-tupi previously
**When** they run `ani-tupi --help` after the refactor
**Then** the help text is identical or improved
**And** all documented commands work as before

#### Scenario: Plugin system unchanged

**Given** a custom plugin exists in `plugins/` directory
**When** the application starts
**Then** the plugin is discovered and loaded correctly
**And** the plugin interface is unchanged

### Requirement: Clear Module Dependencies

The application SHALL enforce clear dependency rules to prevent circular imports.

**Rationale**: Prevents import cycles and makes the codebase easier to navigate and reason about.

**Acceptance Criteria**:
- `core/` modules never import from `ui/`
- `plugins/` never import from `core/` or `ui/`
- Data layer (repository, models, config) can be imported by all layers
- Violations cause import errors (fail-fast)

#### Scenario: Core module tries to import UI

**Given** a developer mistakenly adds `from ui.components import menu` in `core/history_service.py`
**When** the module is imported
**Then** the code reviewer catches this during review
**And** the import is moved to a UI module instead

#### Scenario: Dependencies are documented

**Given** a new developer joins the project
**When** they read `design.md`
**Then** they find clear dependency rules documented
**And** they understand which modules can import from which layers

## MODIFIED Requirements

None. This change is purely additive (new structure) and removes old code (main.py).

## REMOVED Requirements

### Requirement: Monolithic main.py Entry Point

The application SHALL NO LONGER use a single large `main.py` file containing all business logic.

**Rationale**: The 1400-line main.py violates separation of concerns and makes maintenance difficult.

**Migration**: Logic moved to appropriate service modules in `core/` and `ui/`.

#### Scenario: Developer searches for history logic

**Given** a developer wants to modify history saving behavior
**When** they search for history-related code
**Then** they find it in `core/history_service.py` (not main.py)
**And** the old `main.py` no longer exists

## Related Specifications

None (this is the first spec in the project).

## Migration Notes

**Breaking Changes**: None for end users. Internal code organization changes only.

**Deprecation Timeline**:
- Immediately after merge: `main.py` deleted
- No deprecation period needed (internal refactor)

**Migration Steps**:
1. Install refactored version: `uv tool install --reinstall .`
2. Run tests to verify behavior unchanged
3. Report any issues to GitHub

## Appendix: File Structure

**Before**:
```
ani-tupi/
├── main.py (1400 lines - everything)
├── anilist.py
├── anilist_menu.py
├── menu.py
├── loading.py
├── repository.py
├── models.py
├── config.py
└── plugins/
```

**After**:
```
ani-tupi/
├── cli.py (<150 lines)
├── core/
│   ├── anime_service.py
│   ├── history_service.py
│   └── anilist_service.py
├── ui/
│   ├── components.py (menu + loading)
│   ├── menu_system.py
│   ├── anime_menus.py
│   └── anilist_menus.py
├── repository.py (unchanged)
├── models.py (unchanged)
├── config.py (unchanged)
└── plugins/ (unchanged)
```
