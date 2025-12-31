# Proposal: Refactor TUI from Textual to Rich + InquirerPy

**Change ID:** `refactor-tui-rich-inquirerpy`

**Status:** Proposal (awaiting approval)

**Proposed By:** User

**Date:** 2025-12-31

## Why

The current Textual-based TUI causes performance issues and adds unnecessary complexity:

1. **App Recreation on Every Menu**: Textual destroys and recreates the entire app for each menu transition, causing 500ms+ delays and visible flickering
2. **Lack of API Feedback**: Users see frozen UI during anime searches and AniList fetches with no indication of progress
3. **Excessive Complexity**: Textual's widget lifecycle, CSS theming, and screen stacking are overkill for simple terminal menus
4. **Maintenance Burden**: 500+ lines of Textual code vs. ~150 with Rich + InquirerPy

Switching to Rich + InquirerPy provides immediate responsiveness, cleaner code, and loading spinners that give users feedback during slow operations.

## Summary

Replace Textual TUI framework with simpler, more responsive stack using **Rich** for rendering and **InquirerPy** for interactive menus. Maintain Catppuccin color scheme, keyboard navigation (arrows, ESC to back, Q to quit), and add loading placeholders for API calls.

## Problem Statement

### Current Issues with Textual

1. **Performance & Responsiveness**: Textual destroys and recreates the entire app for each menu transition, causing lag and visible flickering
2. **Complexity**: Heavyweight framework for simple terminal menus (CSS, screens, widgets, event system)
3. **Maintenance Burden**: Screen composition, widget lifecycle, CSS theming adds cognitive overhead
4. **Feature Bloat**: Not needed for anime/menu TUI use case

### Identified Bottlenecks

- **API Calls**: AniList GraphQL and scraper searches block UI with no feedback
- **Missing Feedback**: No loading indicators while fetching anime lists or episode data
- **Menu Transitions**: Visible app recreation between screens (~500ms+ per transition)

## Solution Overview

### Tech Stack (New)

- **Rich**: For styled output, spinners, tables, and layout
- **InquirerPy**: Interactive CLI menu prompts (arrow keys, selection)
- **Spinner/Progress**: Rich spinners for API call feedback

### Key Changes

1. **Menu System** (`menu.py`)
   - Replace Textual app/screen architecture with `InquirerPy` prompts
   - Keep single-instance menu loop (no app recreation)
   - Support Catppuccin colors via Rich console theme

2. **Loading Indicators** (new `loading.py`)
   - Add spinner context manager for API calls
   - Display "Carregando..." with animated spinner while fetching
   - Apply to: AniList searches, scraper anime searches, episode fetches

3. **Navigation**
   - Maintain arrow key navigation (InquirerPy native)
   - ESC to go back (InquirerPy native)
   - Q to quit (custom handler)

4. **Color Scheme**
   - Migrate from Textual CSS to Rich `Style` objects
   - Keep Catppuccin Mocha palette:
     - Background: `#1e1e2e`
     - Text: `#cdd6f4`
     - Highlight: `#cba6f7` (purple)
     - Muted: `#6c7086`

## Impact Analysis

### Benefits

- ✅ **Faster Menu Transitions**: No app recreation, pure function rendering
- ✅ **Simpler Codebase**: ~40% less code (no widget lifecycle, CSS, screens)
- ✅ **Better Feedback**: Spinners show API progress immediately
- ✅ **Easier Maintenance**: Rich + InquirerPy are well-documented, widely used
- ✅ **Cleaner UX**: Consistent, responsive menu experience

### Trade-offs

- ❌ **Less Fancy Layouts**: Rich has no 2-column layout like Textual (preview panels removed)
  - Mitigation: Preview data can be shown sequentially or after selection
- ❌ **Different Architecture**: Move away from Screen/Widget pattern
  - Mitigation: New pattern is simpler (functions instead of classes)

### Affected Code

- `menu.py` - Complete refactor (replace MenuApp/MenuScreen)
- `anilist_menu.py` - No changes needed (still calls `menu_navigate()`)
- `main.py` - No changes needed (still calls `menu()`)
- `simple_menu.py` - May be removed (legacy curses, replaced by Rich)
- `pyproject.toml` - Remove `textual`, add `inquirerpy`, upgrade `rich`

### Dependencies

**Remove:**
- `textual>=0.50.0`

**Add:**
- `inquirerpy>=0.3.4`

**Upgrade:**
- `rich` (likely already installed; ensure ≥13.0.0 for Catppuccin theme)

## Success Criteria

1. ✅ All existing menu flows work identically
2. ✅ Navigation: arrows, ESC back, Q quit all functional
3. ✅ Catppuccin colors maintained (no visible degradation)
4. ✅ Loading spinners appear during API calls (AniList, scrapers)
5. ✅ No flickering or app recreation on menu transitions
6. ✅ Code size reduced by ≥30% in menu.py
7. ✅ Response time for menu display <100ms (was ~500ms with Textual)

## Scope

### In Scope

- Replace `MenuApp` / `MenuScreen` with InquirerPy prompts
- Migrate styling to Rich `Style` + Catppuccin palette
- Add loading spinners to async operations (search_anime, search_episodes, search_player_src)
- Update `menu()` and `menu_navigate()` function signatures to work with new system

### Out of Scope

- Preview panels (Textual feature, not critical)
- Theming UI (manual theme switching removed for now)
- Search feature (was limited in Textual; can be added later as InquirerPy plugin)
- Windows-specific testing (curses already works there, Rich should too)

## Questions for Approval

1. **Preview Panels**: Remove silently, or show info sequentially after menu selection?
2. **Search Feature**: Drop the `/` search toggle, or implement differently with InquirerPy?
3. **Testing**: Should we add unit tests for the new menu system, or manual test only?

## Next Steps

1. **Approval**: Review and approve this proposal
2. **Design Review**: Review `design.md` for architectural decisions
3. **Implementation**: Execute `tasks.md` sequentially
4. **Validation**: Run `openspec validate refactor-tui-rich-inquirerpy --strict`
5. **Testing**: Manual testing of all menu flows
6. **Deployment**: Merge to `master` branch

---

**Estimated Scope**: Small-to-medium refactor (6-8 hours implementation + testing)

**Risk Level**: Low (contained to UI layer, no data/business logic changes)

**Rollback Plan**: If issues arise, revert to commit before merge; Textual still available in git history.
