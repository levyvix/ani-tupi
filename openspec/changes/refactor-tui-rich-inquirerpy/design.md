# Design: Rich + InquirerPy TUI Stack

**Change ID:** `refactor-tui-rich-inquirerpy`

**Date:** 2025-12-31

## Architectural Overview

### Old Architecture (Textual)

```
MenuApp (app instance)
  → on_mount()
    → push_screen(MenuScreen)
      → compose() creates widgets (OptionList, Input, etc)
      → event handlers (on_option_list_option_selected, etc)
      → CSS styling
  → app.run() blocks until user selection
  → Result returned, app destroyed
```

**Problem**: App instance created per menu, lifecycle overhead on every transition.

### New Architecture (Rich + InquirerPy)

```
menu() function (pure)
  → format options for InquirerPy
  → inquirer.select() - single prompt
  → Spinner context manager wraps API calls
  → Result returned, function exits
  → Caller loops if needed
```

**Benefit**: Stateless, functional approach; faster transitions.

## Implementation Strategy

### 1. Menu System Refactor

**File: `menu.py`**

Replace 400+ lines of Textual code with ~150 lines of Rich + InquirerPy:

```python
from rich.console import Console
from rich.style import Style
from inquirerpy import inquire
from inquirerpy.validator import EmptyInputValidator
import sys

# Catppuccin Mocha theme
CATPPUCCIN_MOCHA = {
    "background": "#1e1e2e",
    "text": "#cdd6f4",
    "highlight": "#cba6f7",
    "muted": "#6c7086",
}

def menu(opts: list[str], msg: str = "") -> str:
    """Display interactive menu using InquirerPy"""
    opts_copy = opts.copy()
    opts_copy.append("Sair")

    answer = inquire.select(
        message=msg or "Menu",
        choices=opts_copy,
        instruction="(Use arrow keys to navigate)",
        keybindings={
            "interrupt": [{"key": "q"}],  # Q to quit
        },
    ).execute()

    if answer == "Sair":
        sys.exit(0)

    return answer

def menu_navigate(opts: list[str], msg: str = "") -> Optional[str]:
    """Display menu without forcing exit (for navigation flows)"""
    try:
        answer = inquire.select(
            message=msg or "Menu",
            choices=opts,
            instruction="(Use arrow keys, ESC to go back)",
        ).execute()
        return answer
    except KeyboardInterrupt:  # ESC or Ctrl+C
        return None
```

**Key Design Decisions:**

1. **Stateless**: Functions return immediately, no app instance
2. **InquirerPy Handling**:
   - `inquire.select()` provides arrow key navigation natively
   - ESC/Ctrl+C raises `KeyboardInterrupt` (caught as back action)
   - Q key triggers interrupt (configurable)
3. **Catppuccin Colors**:
   - Pass `Style` objects to Rich for text rendering
   - InquirerPy inherits terminal theme (can't customize directly without hacks)
   - Fallback: Use rich console with theme set at program start

### 2. Loading Indicators

**File: `loading.py` (new)**

Context manager for API calls:

```python
from contextlib import contextmanager
from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live

@contextmanager
def loading(msg: str = "Carregando..."):
    """Context manager for loading indicators"""
    console = Console()

    with Live(Spinner("dots", text=msg), console=console, refresh_per_second=12.5):
        yield
```

**Usage:**

```python
# In repository.py or main.py
from loading import loading

with loading("Buscando animes..."):
    rep.search_anime(query)
```

**Integration Points:**

- `repository.py::search_anime()` - Show spinner during ThreadPool execution
- `repository.py::search_episodes()` - Show spinner during episode fetch
- `repository.py::search_player()` - Show spinner during async race
- `anilist_menu.py::_show_anime_list()` - Show spinner while fetching trending/lists
- `anilist.py::get_trending()` - Show spinner for GraphQL call

### 3. Navigation Flow

**Current (Textual):**
```
User selects menu option
  → on_option_list_option_selected() event handler
  → app.exit(selection) or callback
  → Screen destroyed
  → New app instance created
```

**New (Rich + InquirerPy):**
```
User selects menu option (arrow keys + Enter)
  → inquire.select() returns selection
  → Function returns, caller loops if needed
  → No app lifecycle
```

**Example Flow (AniList browsing):**

```python
def anilist_main_menu():
    options = ["Trending", "Watching", "Search", ...]
    selection = menu_navigate(options, "AniList")

    if selection == "Trending":
        # Fetch trending anime
        with loading("Carregando trending..."):
            anime_list = anilist_client.get_trending()

        # Show anime selection
        anime_options = [f"{title} ({eps} eps)" for title, eps in anime_list]
        choice = menu_navigate(anime_options, "Trending Anime")

        if choice:
            return (title, anime_id)

    # Loop back to main menu
    return anilist_main_menu()
```

**Keyboard Handling:**

| Key       | Action                    | Implementation      |
|-----------|---------------------------|---------------------|
| ↑/↓       | Navigate menu             | InquirerPy native   |
| Enter     | Select option             | InquirerPy native   |
| ESC       | Go back (return None)     | Catch KeyboardInterrupt |
| Q         | Quit to terminal          | KeyError handler → sys.exit() |

### 4. Color Scheme Implementation

**Strategy 1 (Preferred): Terminal Theme**

Set Rich console theme at startup:

```python
from rich.console import Console
from rich.theme import Theme

CATPPUCCIN_THEME = Theme({
    "menu.title": "bold #cba6f7",          # Purple header
    "menu.text": "#cdd6f4",                # Light text
    "menu.highlight": "reverse #cba6f7",  # Inverted purple
    "menu.muted": "#6c7086",               # Muted gray
})

console = Console(theme=CATPPUCCIN_THEME)
```

**Strategy 2 (Fallback): Direct Style Objects**

Use Rich `Style` in message formatting:

```python
from rich.style import Style

style_highlight = Style(color="#cba6f7", bold=True)
console.print("Selected", style=style_highlight)
```

**Challenge**: InquirerPy doesn't expose color customization directly. Will use Rich console theme + custom prompt rendering if needed.

### 5. Preview Panels Removal

**Old Textual Feature:**
```
┌─────────────────┐  ┌────────────────┐
│  Menu Options   │  │    Preview     │
│  - Option 1     │  │                │
│  - Option 2     │  │ Synopsis info  │
│  - Option 3     │  │ Rating, etc    │
└─────────────────┘  └────────────────┘
```

**New Rich Approach:**

Show info sequentially instead:

```python
# After selection
choice = menu_navigate(options, "Anime List")

if choice:
    # Get and display info
    anime_info = rep.get_anime_info(choice)
    console.print(f"[bold]{choice}[/bold]")
    console.print(f"Synopsis: {anime_info['synopsis']}")
    console.print(f"Rating: {anime_info['rating']}")

    # Ask to proceed
    confirm = menu_navigate(["▶️ Watch", "🔙 Back"], "")
```

**Rationale**: Simpler UX, avoids 2-column layout complexity.

### 6. Dependency Graph

```
menu.py (main public API)
  ├─ Rich (rendering)
  ├─ InquirerPy (prompts)
  └─ loading.py (spinners)

loading.py
  ├─ Rich (spinner, live console)
  └─ contextlib (manager)

anilist_menu.py
  ├─ menu.py (menu_navigate)
  └─ loading.py (API spinners) [NEW]

repository.py
  └─ loading.py (search spinners) [NEW]

main.py
  ├─ menu.py (menu, menu_navigate)
  └─ loading.py (video player spinners) [NEW]
```

## Technical Decisions

### Decision 1: InquirerPy over other libraries

**Options Considered:**

1. **InquirerPy** (chosen)
   - ✅ Arrow key navigation native
   - ✅ Active maintenance
   - ✅ Can customize colors
   - ❌ Less flexible layout than Textual

2. **Click / Prompt**
   - Simple but limited interactivity
   - No rich styling

3. **Urwid** (like Omarchy)
   - Heavyweight, similar to Textual
   - More control but more complexity

**Decision**: InquirerPy balances simplicity + interactivity.

### Decision 2: Spinner context manager vs manual control

**Options:**

1. **Context Manager** (chosen)
   ```python
   with loading("Searching..."):
       result = repo.search_anime(query)
   ```
   - ✅ Clean, reusable
   - ✅ Auto-cleanup on exception
   - ✅ Minimal code changes

2. **Manual spinner state**
   ```python
   spinner = start_loading("Searching...")
   result = repo.search_anime(query)
   stop_loading(spinner)
   ```
   - ❌ Easy to forget stop call
   - ❌ Exception safety issues

**Decision**: Context manager enforces cleanup.

### Decision 3: Catppuccin in Terminal vs Code

InquirerPy uses terminal's existing color palette, which won't perfectly match Catppuccin unless terminal is configured with Catppuccin theme.

**Strategy:**
1. Document requirement: "Use Catppuccin terminal theme for best colors"
2. Provide fallback styling via Rich console theme
3. InquirerPy inherits whatever colors are in use

**Alternative**: Inject ANSI escape codes directly (complex, fragile).

**Decision**: Accept terminal theme dependency; document in README.

## Testing Strategy

### Unit Tests

Not applicable (stateless functions, integration with external libraries).

### Integration Tests

Manual testing checklist:
- [ ] Menu navigation (arrows, Enter, ESC)
- [ ] Q key quits to terminal
- [ ] Catppuccin colors visible (if terminal configured)
- [ ] Loading spinners appear and disappear
- [ ] API calls properly wrapped with spinners
- [ ] No console output overlaps

### Manual Test Scenarios

1. **Basic Menu**
   ```bash
   uv run main.py -q "test"
   ```
   Navigate with arrows, press ESC, then run again.

2. **AniList Flow**
   ```bash
   uv run main.py anilist
   ```
   Select "Trending", watch spinner, select anime, spinners during search.

3. **Search & Play**
   ```bash
   uv run main.py -q "dandadan"
   ```
   Spinners during scraper search, episode selection, video URL fetch.

## Rollback Plan

If critical issues arise:

1. Revert commit: `git revert <commit-hash>`
2. Restore dependencies: `uv sync` (will re-install textual)
3. Menu.py restores to Textual version from git history
4. No data loss (repository, history, settings unaffected)

## Performance Expectations

### Metrics

| Metric | Textual | Rich + InquirerPy | Improvement |
|--------|---------|-------------------|-------------|
| Menu show time | ~500ms | ~50ms | 10x |
| Transition flicker | Yes (visible) | No | ✅ |
| Code size (menu.py) | ~500 lines | ~150 lines | 70% reduction |
| Startup time | ~1s | ~200ms | 5x |

### Why the improvement?

- **Textual**: App initialization, CSS parsing, widget tree creation
- **Rich + InquirerPy**: Direct prompt, no lifecycle overhead

## Future Enhancements (Out of Scope)

1. **Search Feature**: Implement via InquirerPy's filter/search extension
2. **Themes**: Add dynamic theme switching (RichTheme files)
3. **Progress Bars**: Use Rich progress for multi-step operations
4. **Tables**: Use Rich tables for episode listings (instead of simple menus)

---

**Arch Review Status**: Ready for implementation after approval.
