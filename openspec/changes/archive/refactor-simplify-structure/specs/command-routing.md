# Command Routing System Specification

**Capability:** Command Routing & Separation of Concerns
**Change ID:** refactor-simplify-structure

## ADDED Requirements

### Requirement: Commands Module

#### Overview
Create `commands/` package to separate user-facing command flows from main entry point logic.

#### Scenario: Import command handlers
```python
from commands import anime, anilist, manga, sources
```

#### Scenario: Route to anime command
```python
# main.py
if args.query or args.continue_watching:
    anime.handle(args)
```

#### Scenario: Route to anilist command
```python
# main.py
elif choice == "📺 AniList":
    anilist.handle(args)
```

### Requirement: Anime Command Handler

#### Overview
`commands/anime.py` handles anime search, episode selection, and playback.

#### Scenario: Search and play anime
```python
# commands/anime.py
def handle(args):
    """Search anime and manage playback loop."""
    # Search anime by query or continue from history
    # Show episode list
    # Loop: select episode → get video URL → play → save history
    # Return when user exits
```

#### Scenario: Continue watching flow
```python
# From history
selected_anime, episode_idx = load_history()
# Jump to episode selection (not search)
```

### Requirement: AniList Command Handler

#### Overview
`commands/anilist.py` handles AniList menu browsing and watch synchronization.

#### Scenario: Browse AniList trending
```python
# commands/anilist.py
def handle(args):
    """Show AniList menu and manage watch loops."""
    # Show menu: Trending, Watching, Planning, etc.
    # Loop: select anime → search scrapers → play → update progress
    # Return when user exits menu
```

### Requirement: Manga Command Handler

#### Overview
`commands/manga.py` consolidates manga reading flow from `manga_tupi.py`.

#### Scenario: Read manga
```python
# commands/manga.py
def handle(args):
    """Search manga and manage reading loop."""
    # Search manga by query
    # Select manga
    # Show chapter list
    # Loop: select chapter → display pages → save history
    # Return when user exits
```

### Requirement: Sources Command Handler

#### Overview
`commands/sources.py` handles plugin management UI.

#### Scenario: Manage plugins
```python
# commands/sources.py
def handle(args):
    """Show plugin management menu."""
    # Show active/inactive plugins
    # Toggle enable/disable
    # Return when user exits
```

## MODIFIED Requirements

### Requirement: Main Entry Point Routing Logic

#### Before State
- main.py contains all flows mixed together
- Logic for routing to different commands in same function
- 315 LOC monolithic controller

#### After State
- main.py is thin entry point
- Routes to command handlers in `commands/`
- Command handlers own their flows

#### Scenario: Main routing
```python
# main.py (simplified)
def cli():
    loader.load_plugins({"pt-br"})

    args = parse_args()

    # Short path for direct commands
    if args.query or args.continue_watching:
        return anime.handle(args)
    elif args.manga:
        return manga.handle(args)

    # Interactive menu
    while True:
        choice = show_main_menu()
        if choice == "🔍 Buscar Anime":
            anime.handle(args)
        elif choice == "📺 AniList":
            anilist.handle(args)
        elif choice == "📚 Mangá":
            manga.handle(args)
        elif choice == "⚙️ Gerenciar Fontes":
            sources.handle(args)
        elif choice == "Sair":
            break
```

#### Scenario: Error handling
```python
# Each command handler catches its own errors
# Returns cleanly to main menu or exits
```

## Backward Compatibility Notes

✅ No changes to user-facing behavior
✅ All CLI options work identically:
- `ani-tupi` - Shows menu
- `ani-tupi -q "query"` - Direct search
- `ani-tupi --continue-watching` - Resume
- `ani-tupi anilist` - AniList mode
- `ani-tupi manga` - Manga mode

✅ No changes to:
- Configuration
- History file format
- Plugin interface
- Service APIs

## Implementation Notes

### Command Handler Pattern
Each handler should:
1. Accept minimal arguments (parsed CLI args or None)
2. Use services for business logic
3. Use UI components for user interaction
4. Save history/state as appropriate
5. Return cleanly (no exceptions raised)

### Error Handling
- Handlers catch exceptions internally
- Display user-friendly error messages
- Return to main menu or exit gracefully
- Log exceptions for debugging

### Testing Strategy
- Mock services to test command routing
- Test error handling paths
- Verify return behavior (menu loop vs exit)
