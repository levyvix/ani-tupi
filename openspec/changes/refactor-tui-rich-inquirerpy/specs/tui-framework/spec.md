# Spec: TUI Framework (Rich + InquirerPy)

**Change ID:** `refactor-tui-rich-inquirerpy`

**Capability:** `tui-framework`

**Status:** Proposed Delta

## MODIFIED Requirements

### Requirement: MUST display interactive terminal menu using InquirerPy

The system MUST display an interactive menu using InquirerPy's `select()` prompt with keyboard navigation (arrow keys, Enter to select).

**Previously:** Textual app with MenuScreen, OptionList widgets, CSS styling

**Details:**
- Display: Single-column list of options
- Interaction: Arrow keys (↑/↓) navigate; Enter selects
- Styling: Inherit terminal colors; Rich theme provides Catppuccin palette
- Function: `menu(opts: list[str], msg: str = "") -> str`
- Behavior: Auto-appends "Sair" option; selection exits or loops

#### Scenario: User searches and selects anime

1. User runs: `uv run ani-tupi -q "dandadan"`
2. System displays menu:
   ```
   Search: dandadan
   ─────────────────
   1) Dandadan
   2) Dandadan (Alternative Title)
   (Use arrow keys to navigate)
   ```
3. User presses ↓ to move to option 2
4. User presses Enter to select
5. System returns selection; menu exits immediately
6. Control returns to caller for next action

---

### Requirement: MUST support navigation menu with ESC back action

The system MUST display a navigation menu that allows users to go back (ESC) without exiting the application.

**Previously:** MenuScreen with mode parameter

**Details:**
- Function: `menu_navigate(opts: list[str], msg: str = "") -> Optional[str]`
- Behavior: ESC key returns `None` (indicates "go back")
- Keyboard: Arrows for navigation; ESC for back; Q for quit
- No auto-appended "Sair" (caller controls flow)

#### Scenario: AniList browsing with back navigation

1. System calls: `menu_navigate(["Trending", "Watching", "Login"], "AniList")`
2. User presses ↓ to navigate to "Watching"
3. User presses ESC to go back
4. Function returns `None`
5. Caller's `anilist_main_menu()` handles None → shows previous menu

---

### Requirement: MUST exit on Q key from any menu

The system MUST exit immediately to terminal when user presses Q key from any menu.

**Previously:** Q key handled via Textual bindings

**Details:**
- Key: Q
- Behavior: Calls `sys.exit(0)` immediately
- Location: Handled in `inquire.select()` keybindings
- Fallback: Can also use Ctrl+C (standard interrupt)

#### Scenario: User wants to quit from deep menu

1. User in any menu: `menu_navigate(options, "Select Episode")`
2. User presses Q
3. System calls interrupt handler → `sys.exit(0)`
4. Process terminates, user returns to shell

---

### Requirement: MUST apply Catppuccin colors via Rich Theme

Menus MUST be styled with Catppuccin Mocha color scheme using Rich `Theme` and `Style` objects.

**Previously:** Textual CSS with Catppuccin palette

**Details:**
- Palette:
  - Background: `#1e1e2e`
  - Foreground: `#cdd6f4`
  - Highlight (selected): `#cba6f7` (purple)
  - Muted: `#6c7086`
- Implementation: Rich `Theme` configured at Console creation
- Fallback: If terminal doesn't support colors, use plain text
- Note: Best results with Catppuccin terminal theme installed

#### Scenario: User sees styled menu

1. System creates Rich Console with Catppuccin theme
2. Displays menu with styled title (bold purple)
3. Selected option highlighted (inverted color)
4. Colors match Catppuccin Mocha palette
5. Fallback gracefully if terminal doesn't support ANSI colors

---

## REMOVED Requirements

### Requirement: Textual Screen Lifecycle

**Removal Justification:** Replaced by stateless InquirerPy prompts; no more screen stacking or widget composition.

---

### Requirement: CSS Styling System

**Removal Justification:** Rich uses inline `Style` objects instead of CSS files; simpler and more direct.

---

### Requirement: Preview Panels

**Removal Justification:** Rich doesn't support 2-column layouts easily; preview info shown sequentially instead (out of scope for this capability).

---

## Design Rationale

### Why InquirerPy?

- ✅ Native arrow key support (vs custom key handling)
- ✅ Simpler API (vs Textual's widget composition)
- ✅ Color customization (vs limited Textual theming)
- ✅ Active maintenance and documentation

### Why Rich?

- ✅ Render styled text, spinners, tables, panels
- ✅ Theme support for consistent colors
- ✅ Works with InquirerPy without conflicts

### Performance Impact

| Metric | Textual | Rich + InquirerPy |
|--------|---------|-------------------|
| Menu display | ~500ms | ~50ms |
| Code lines | ~500 | ~150 |
| Dependencies | Heavy | Lightweight |

---

## Cross-References

- **Capability: `loading-indicators`** — Loading spinners wrap menu/search operations
- **File: `menu.py`** — Contains `menu()` and `menu_navigate()` implementations
- **File: `loading.py`** — New file with spinner context manager

---

**Status**: Ready for approval and implementation.
