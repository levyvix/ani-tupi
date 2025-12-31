# Spec: Loading Indicators for API Operations

**Change ID:** `refactor-tui-rich-inquirerpy`

**Capability:** `loading-indicators`

**Status:** Proposed Delta (New)

## ADDED Requirements

### Requirement: MUST display animated loading spinner

The system MUST display an animated spinner while performing long-running operations (API calls, scraper searches) to provide user feedback.

**Details:**
- Widget: Rich `Spinner` with animation (dots, line, or similar)
- Message: Descriptive text (e.g., "Buscando animes...", "Carregando episódios...")
- Duration: Show for entire operation; dismiss when complete
- Responsive: Non-blocking; user can still interrupt (Ctrl+C)

**Implementation:**
```python
from loading import loading

# Usage
with loading("Buscando animes..."):
    result = repository.search_anime(query)
```

#### Scenario: User searches for anime while spinner shows progress

1. User types anime name and presses Enter: `"Dandadan"`
2. System calls: `with loading("Buscando animes..."): rep.search_anime("Dandadan")`
3. Spinner appears: ⠋ Buscando animes... (animated)
4. Scraper plugins execute in parallel (ThreadPool)
5. First result found after ~2 seconds
6. Spinner disappears, menu shows results
7. User selects anime from results menu

---

### Requirement: MUST wrap API calls with loading spinners

The system MUST wrap all major API calls (AniList GraphQL, scraper searches, video URL discovery) with loading spinners to indicate progress.

**Details:**
- Operations: `search_anime()`, `search_episodes()`, `search_player_src()`, AniList fetches
- Messages: Localized PT-BR ("Buscando...", "Carregando...", "Procurando vídeo...")
- Timing: Show for async operations only (>500ms expected)
- Cancellation: Spinner respects Ctrl+C (raises KeyboardInterrupt)

#### Scenario: AniList trending anime list loads with spinner

1. User selects: `anilist_menu.py → Trending`
2. System shows spinner: ⠙ Carregando trending...
3. AniList GraphQL query executes (~1-2 seconds)
4. API response returns
5. Spinner dismissed
6. Menu displays anime list with scores and episode counts

---

### Requirement: MUST handle exceptions in loading context

If an operation raises an exception while loading spinner is active, the system MUST dismiss the spinner and propagate the exception to the caller.

**Details:**
- Cleanup: Spinner always cleaned up (even on error)
- Exception: Propagated to caller for handling
- Message: Error message displayed after spinner disappears
- Recovery: Caller can show error menu or retry

#### Scenario: API timeout while loading spinner active

1. User selects AniList list (e.g., "Watching")
2. Spinner appears: ⠋ Carregando lista...
3. After 30 seconds: API times out → `httpx.TimeoutException`
4. Spinner disappears immediately
5. Error message: `❌ Timeout ao buscar lista. Tente novamente.`
6. System returns to previous menu

---

### Requirement: MUST support stacked loading spinners

If multiple nested operations have spinners, the system MUST display the innermost spinner message.

**Details:**
- Nesting: Allowed (context managers can nest)
- Display: Show only the most recent spinner message
- Use Case: Example - fetching anime → fetching episodes → fetching video
- Optional: Not required for initial implementation

#### Scenario: Cascading spinners during full watch flow

1. User selects episode
2. Level 1: Spinner "Procurando vídeo..." (outermost)
   - Level 2: Spinner "Conectando ao provider..." (nested)
   - (Video URL found or timeout)
3. Level 2 spinner cleared, returns to Level 1
4. Level 1 spinner cleared, returns to menu

---

## MODIFIED Requirements

### Requirement: MUST display spinner during search operations

The system MUST display a spinner during entire search operation.

**Previously:** No feedback during search (user sees frozen menu)

**Details:**
- `repository.search_anime()`: Wrap ThreadPool with `loading("Buscando animes...")`
- `repository.search_episodes()`: Wrap thread with `loading("Carregando episódios...")`
- `repository.search_player_src()`: Wrap asyncio race with `loading("Procurando vídeo...")`

#### Scenario: User sees immediate feedback for search

1. User enters search query: "Attack on Titan"
2. System executes: `with loading("Buscando animes..."): rep.search_anime("Attack on Titan")`
3. Spinner animates (⠋ → ⠙ → ⠹ → ...)
4. All plugins execute in parallel
5. First result found (~1-2 sec)
6. Spinner exits context, menu shown with results

---

## Design Details

### Implementation: `loading.py`

```python
from contextlib import contextmanager
from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live

@contextmanager
def loading(msg: str = "Carregando..."):
    """
    Context manager for loading indicators.

    Usage:
        with loading("Searching..."):
            result = expensive_operation()
    """
    console = Console()
    spinner = Spinner("dots", text=msg)

    with Live(spinner, console=console, refresh_per_second=12.5):
        yield  # Operation runs here
    # Spinner auto-cleaned up on exit (success or exception)
```

### Integration Points

**File: `repository.py`**
```python
def search_anime(self, query: str):
    from loading import loading
    with loading("Buscando animes..."):
        # ThreadPool.map() here
        # Plugins execute and add results
```

**File: `anilist_menu.py`**
```python
def _show_anime_list(list_type: str):
    from loading import loading
    with loading(f"Carregando {list_type}..."):
        if list_type == "trending":
            anime_list = anilist_client.get_trending(per_page=50)
        else:
            anime_list = anilist_client.get_user_list(list_type, per_page=50)
```

### Color Coordination

- Spinner text: White/light (inherits terminal color)
- Spinner animation: Catppuccin purple (`#cba6f7`) if possible via Rich
- Background: Transparent (terminal background)

---

## Cross-References

- **Capability: `tui-framework`** — Menus that call operations with spinners
- **File: `repository.py`** — Wraps search methods with loading context
- **File: `anilist_menu.py`** — Wraps AniList API calls with loading
- **File: `loading.py`** — New file containing spinner implementation

---

## Success Criteria

1. ✅ Spinner appears and animates during API calls
2. ✅ Spinner disappears when operation completes
3. ✅ Exceptions during operation don't crash spinner
4. ✅ No console output overlaps with spinner
5. ✅ Messages in Portuguese (PT-BR)
6. ✅ User can interrupt with Ctrl+C
7. ✅ Performance overhead <10ms per call

---

**Status**: Ready for approval and implementation.
