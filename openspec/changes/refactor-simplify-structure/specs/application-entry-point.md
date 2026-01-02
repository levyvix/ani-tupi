# Application Entry Point Specification

**Capability:** Application Entry Point & Command Routing
**Change ID:** refactor-simplify-structure

## MODIFIED Requirements

### Requirement: Single Unified Entry Point

#### Before State
- Multiple entry points: `cli.py`, `main.py`, `manga_tupi.py`
- Logic duplication across files
- Unclear routing to different flows

#### After State
- Single `main.py` entry point for all modes
- Clear command routing to `commands/*.py` handlers
- Consolidates anime, anilist, manga, and source management into one flow

#### Scenario: User runs basic anime search
```bash
$ uv run main.py -q "Dandadan"
→ main.py parses args
→ Routes to commands.anime(args)
→ Anime search flow begins
```

#### Scenario: User runs AniList mode
```bash
$ uv run main.py anilist
→ main.py parses args
→ Routes to commands.anilist(args)
→ AniList menu displays
```

#### Scenario: User runs with no args (interactive menu)
```bash
$ uv run main.py
→ main.py shows main menu
→ User selects option
→ Routes to appropriate command handler
```

### Requirement: Consolidated Entry Points

#### Before State
- `cli.py`: 15 LOC thin wrapper (pointless indirection)
- `main.py`: 315 LOC with all flows mixed
- `manga_tupi.py`: 252 LOC separate CLI

#### After State
- `cli.py`: Removed (consolidated into main.py)
- `main.py`: Single unified entry point with command routing
- `manga_tupi.py`: Removed (logic moved to commands/manga.py)

#### Scenario: Verify no cli.py wrapper remains
```bash
$ ls ani-tupi/cli.py
cli.py does not exist (removed)
```

#### Scenario: Verify pyproject.toml entry point
```
[project.scripts]
ani-tupi = "main:cli"  # Points to main.py:cli function
```

### Requirement: Command Routing

#### Before State
- Mixed logic in main.py for anime, anilist, manga, and sources
- No clear separation of concerns

#### After State
- Each command in separate `commands/*.py` file
- main.py routes to appropriate handler
- Each handler returns cleanly to main menu or exits

#### Scenario: Route anime command
```python
if args.query or args.continue_watching:
    from commands import anime
    anime.handle(args)
```

#### Scenario: Route AniList command
```python
elif choice == "📺 AniList":
    from commands import anilist
    anilist.handle(args)
```

#### Scenario: Route manga command
```python
elif choice == "📚 Mangá":
    from commands import manga
    manga.handle(args)
```

## MODIFIED Requirements: Plugin System Integration

### Requirement: Load plugins once at startup

#### Before State
- `loader.load_plugins()` called multiple times

#### After State
- main.py loads plugins once at startup
- Commands use already-loaded plugins

#### Scenario: Plugin loading in main.py
```python
# main.py startup
from scrapers import loader
loader.load_plugins({"pt-br"})

# Commands access pre-loaded plugins via services.repository
```

## Backward Compatibility Notes

✅ All CLI commands work identically:
```bash
ani-tupi                     # Works
ani-tupi -q "query"          # Works
ani-tupi --continue-watching # Works
ani-tupi anilist             # Works
ani-tupi manga               # Works
```

✅ No changes to:
- CLI argument parsing
- User-facing behavior
- Plugin interface (`PluginInterface` ABC)
- Configuration loading
