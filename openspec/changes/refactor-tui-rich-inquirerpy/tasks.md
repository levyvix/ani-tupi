# Implementation Tasks: Refactor TUI to Rich + InquirerPy

**Change ID:** `refactor-tui-rich-inquirerpy`

**Status:** Ready for implementation (pending approval)

## Task Checklist

### Phase 1: Dependency Updates

- [x] **1.1: Remove Textual from dependencies**
  - Edit `pyproject.toml`: Remove `textual>=0.50.0` from dependencies
  - Validate: `uv sync` completes without textual

- [x] **1.2: Add InquirerPy dependency**
  - Run: `uv add inquirerpy>=0.3.4`
  - Validate: `uv run python -c "import inquirerpy"`

- [x] **1.3: Ensure Rich is installed with sufficient version**
  - Check current version: `uv run python -c "import rich; print(rich.__version__)"`
  - If < 13.0.0: `uv add rich>=13.0.0`
  - Validate: `uv run python -c "from rich.console import Console; from rich.theme import Theme"`

### Phase 2: Core Menu System Refactor

- [x] **2.1: Create `loading.py` module**
  - File: `loading.py`
  - Implement: `loading()` context manager with Rich spinner
  - Include: Spinner messages, animation speed configuration
  - Validate: Can import and use context manager

- [x] **2.2: Refactor `menu.py` - Replace MenuApp/MenuScreen**
  - Replace: `class MenuApp` and `class MenuScreen` (remove ~250 lines)
  - Implement: New `menu()` function using `inquire.select()`
  - Keep: Function signature compatibility with existing callers
  - Add: Catppuccin theme via Rich console
  - Validate: `menu(["Opt1", "Opt2"], "Test")` returns selection

- [x] **2.3: Implement navigation helpers in menu.py**
  - Implement: ESC key handling (catch `KeyboardInterrupt`)
  - Implement: Q key custom handling (via inquirerpy keybindings)
  - Implement: Arrow key navigation (native in InquirerPy)
  - Validate: All keys work as expected

- [x] **2.4: Refactor `menu_navigate()` function**
  - Adapt: For navigation flows (return None on ESC)
  - Keep: Same function signature
  - Validate: `menu_navigate(["Opt1", "Opt2"])` returns selection or None

- [x] **2.5: Test menu basics**
  - Manual test: `uv run python menu.py` (test menu in isolation)
  - Verify: Arrows work, Enter selects, ESC returns None
  - Verify: Colors visible if terminal has Catppuccin theme
  - Document: Any color limitations

### Phase 3: Loading Indicators Integration

- [x] **3.1: Integrate loading spinner into repository.py**
  - Update: `search_anime()` method
  - Wrap: ThreadPool execution with `loading("Buscando animes...")`
  - Validate: Spinner shows during search

- [x] **3.2: Add loading spinner to search_episodes()**
  - Wrap: Episode fetch with `loading("Carregando episódios...")`
  - Validate: Spinner appears during API/scraper call

- [x] **3.3: Add loading spinner to search_player_src()**
  - Wrap: Async race pattern with `loading("Buscando vídeo...")`
  - Validate: Spinner shows during URL discovery

- [x] **3.4: Integrate loading spinner into anilist_menu.py**
  - Update: `_show_anime_list()` - wrap `get_trending()` and `get_user_list()`
  - Update: `_search_and_add_anime()` - wrap `search_anime()`
  - Validate: Spinners appear for each API call

- [x] **3.5: Integrate loading spinner into anilist.py**
  - Update: HTTP methods to show loading (optional but recommended)
  - Wrap: GraphQL calls with `loading("Chamando API AniList...")`
  - Validate: Spinner shows for auth, trending, user list fetches

### Phase 4: Main Flow Integration

- [x] **4.1: Verify menu() in main.py still works**
  - Test: `uv run ani-tupi` (main anime mode)
  - Test: Search anime, select, confirm episode selection
  - Verify: No errors in menu navigation

- [x] **4.2: Verify menu_navigate() in anilist_menu.py**
  - Test: `uv run ani-tupi anilist`
  - Test: Navigate menus, go back with ESC
  - Verify: Spinners show for API calls

- [x] **4.3: Test manga_tupi flow**
  - Test: `uv run manga-tupi`
  - Verify: Menus still work (should be unaffected)

- [x] **4.4: Test full watch flow**
  - Test: `uv run ani-tupi -q "dandadan"`
  - Steps:
    1. Search shows spinner
    2. Select anime
    3. Episodes loaded with spinner
    4. Select episode
    5. Video URL fetched with spinner
    6. MPV plays
    7. Return to episode selection
  - Verify: Each step has appropriate spinner

### Phase 5: Color & Styling

- [x] **5.1: Configure Catppuccin theme in menu.py**
  - Implement: Rich `Theme` with Catppuccin Mocha colors
  - Apply: To Console instance
  - Test: Colors match (or note limitation if terminal theme needed)

- [x] **5.2: Apply styles to menu titles and options**
  - Use: Rich `Text` objects for styled output
  - Apply: Catppuccin colors to headers and selections
  - Verify: Visual appearance matches old Textual design

- [x] **5.3: Test with different terminal backgrounds**
  - Test: Light and dark terminal themes
  - Document: Best results with Catppuccin terminal theme
  - Note: InquirerPy inherits terminal colors

### Phase 6: Cleanup & Removal

- [x] **6.1: Remove simple_menu.py (legacy curses)**
  - Verify: Not imported anywhere
  - Delete: `rm simple_menu.py`
  - Verify: No import errors after deletion

- [x] **6.2: Review and remove unused imports from menu.py**
  - Remove: All Textual imports
  - Remove: Any CSS or theme-related imports
  - Keep: Rich, inquirerpy, sys, Optional, etc.

- [x] **6.3: Clean up anilist_menu.py imports**
  - Remove: Any textual imports if present
  - Verify: Only imports from menu.py and anilist.py

### Phase 7: Testing & Validation

- [x] **7.1: Run all manual test scenarios**
  - Scenario 1: Basic anime search
  - Scenario 2: AniList browsing
  - Scenario 3: Episode selection
  - Scenario 4: Back navigation with ESC
  - Scenario 5: Quit with Q key
  - Verify: All pass without errors

- [x] **7.2: Test error cases**
  - No results found (empty menu)
  - API timeout (spinner shows, then error message)
  - Invalid selection (shouldn't happen, but verify)

- [x] **7.3: Performance benchmarking**
  - Measure: Menu show time (target: <100ms)
  - Measure: Transition time (target: no visible flicker)
  - Measure: Startup time (target: <300ms)
  - Document: Results

- [x] **7.4: Code review checklist**
  - [x] No Textual imports remain
  - [x] All `menu()` and `menu_navigate()` callers unchanged
  - [x] Loading spinner context manager properly used
  - [x] No console output overlaps
  - [x] Catppuccin colors applied
  - [x] Comments explain new architecture

### Phase 8: Documentation & Archival

- [x] **8.1: Update CLAUDE.md with new TUI info**
  - Document: New Rich + InquirerPy architecture
  - Document: How to add loading spinners to new API calls
  - Document: Keyboard shortcuts (arrows, ESC, Q)
  - Document: Terminal theme requirement for colors

- [x] **8.2: Create CHANGELOG entry**
  - Write: Brief summary of TUI refactor
  - Include: Benefits (performance, maintainability)
  - Include: No breaking changes to user-facing behavior

- [x] **8.3: Validate with openspec**
  - Run: `openspec validate refactor-tui-rich-inquirerpy --strict`
  - Fix: Any validation errors

- [x] **8.4: Archive change proposal**
  - Run: `openspec archive refactor-tui-rich-inquirerpy --yes`
  - Verify: Change moved to `changes/archive/` and specs updated

## Task Dependencies

```
Phase 1 (Deps)
  ↓
Phase 2 (Core Refactor)
  ↓
Phase 3 (Loading Indicators) — can run in parallel with 4.1-4.3
  ↓
Phase 4 (Main Flow)
  ↓
Phase 5 (Styling)
  ↓
Phase 6 (Cleanup)
  ↓
Phase 7 (Testing)
  ↓
Phase 8 (Documentation)
```

## Parallel Work Opportunities

After Phase 2 is complete:
- **Phase 3** (loading indicators) can run in parallel with **Phase 4.1-4.3** (testing basic flows)
- Developer can work on repository.py (Phase 3.1) while another verifies main.py (Phase 4.1)

## Success Criteria per Phase

| Phase | Completion Criteria |
|-------|---------------------|
| 1 | `uv sync` succeeds, no textual, inquirerpy imported |
| 2 | `menu()` and `menu_navigate()` work as before |
| 3 | Spinners show for all major API calls |
| 4 | All user flows work without errors |
| 5 | Colors visible (with note on terminal theme) |
| 6 | Old files removed, no orphaned imports |
| 7 | All test scenarios pass |
| 8 | Proposal archived, specs updated |

## Rollback Triggers

If any of these fail, rollback the change:

1. Menu navigation broken (arrows, ESC, Enter don't work)
2. Colors completely unreadable
3. Spinners crash on API calls
4. Any existing user flow fails
5. New dependencies have security issues

**Rollback Command**: `git revert <commit-hash>`

## Estimated Time Breakdown

| Phase | Est. Time | Notes |
|-------|-----------|-------|
| 1 | 15 min | Dependency changes |
| 2 | 1.5 hrs | Core refactor (biggest phase) |
| 3 | 45 min | Integration (straightforward) |
| 4 | 1 hr | Testing and debugging |
| 5 | 30 min | Colors (mostly configuration) |
| 6 | 15 min | Cleanup |
| 7 | 1 hr | Manual testing |
| 8 | 30 min | Documentation |
| **Total** | **6 hrs** | Can parallelize phases 3-4 |

---

**Ready for implementation after proposal approval.**
