# Spec: OS-Aware Path Resolution

**Change ID:** `add-pydantic-validation`

**Capability:** `path-resolution`

**Status:** Proposed Delta

## ADDED Requirements

### Requirement: MUST provide centralized OS-aware path resolution

The system MUST provide a single `get_data_path()` helper function that returns the correct data directory path for the current operating system.

**Details:**
- Function: `get_data_path() -> Path`
- Returns:
  - Linux/macOS: `~/.local/state/ani-tupi`
  - Windows: `C:\Program Files\ani-tupi`
- Location: `config.py` module
- Used by: All file path configurations (token files, cache files, history files)
- Testable: Can mock `os.name` in unit tests

#### Scenario: Application starts on Linux

1. Application imports: `from config import get_data_path`
2. Calls: `data_path = get_data_path()`
3. Function checks: `os.name == "nt"` → False (Linux)
4. Returns: `Path.home() / ".local" / "state" / "ani-tupi"`
5. Expands to: `/home/username/.local/state/ani-tupi`
6. All files (token, cache, history) stored in this directory
7. Directory created automatically if it doesn't exist

---

### Requirement: MUST support automatic directory creation

The system MUST automatically create the data directory and parent directories if they don't exist when writing files.

**Details:**
- Method: `Path.mkdir(parents=True, exist_ok=True)`
- Timing: Before writing token file, cache file, or history file
- Permissions: Default user permissions (0755 directories, 0644 files)
- Error handling: If directory creation fails (permissions), raise clear error

#### Scenario: First run on fresh system

1. User runs: `uv run ani-tupi anilist auth`
2. AniList client needs to save token to: `get_data_path() / "anilist_token.json"`
3. Checks if parent directory exists: `~/.local/state/ani-tupi`
4. Directory doesn't exist (fresh system)
5. Calls: `settings.anilist.token_file.parent.mkdir(parents=True, exist_ok=True)`
6. Creates directory chain: `~/.local` → `~/.local/state` → `~/.local/state/ani-tupi`
7. Writes token file successfully
8. Subsequent runs use existing directory

---

## MODIFIED Requirements

### Requirement: Path configuration MUST be OS-aware by default

All file path settings MUST use `get_data_path()` to automatically resolve the correct path for the current OS.

**Previously:** Duplicated OS detection logic in multiple files:
- `main.py:15`:
  ```python
  HISTORY_PATH = (
      Path.home() / ".local/state/ani-tupi"
      if name != "nt"
      else Path("C:\\Program Files\\ani-tupi")
  )
  ```
- `anilist_menu.py:16` - DUPLICATE of above
- `scraper_cache.py:8` - DUPLICATE of above
- `anilist.py:21` - DUPLICATE for token file

**Details:**
- Single implementation in `get_data_path()`
- All configs use: `Field(default_factory=lambda: get_data_path() / "filename.json")`
- No duplicated OS checks
- Easy to test (mock `os.name`)
- Easy to extend (add macOS-specific logic, BSD support, etc.)

#### Scenario: Token file path on Windows

1. Previously in `anilist.py`:
   ```python
   TOKEN_FILE = Path.home() / ".local/state/ani-tupi/anilist_token.json"
   # This creates Linux/macOS path on Windows! Wrong!
   ```
2. Now in `config.py`:
   ```python
   class AniListSettings(BaseModel):
       token_file: Path = Field(
           default_factory=lambda: get_data_path() / "anilist_token.json"
       )

   # get_data_path() returns correct Windows path automatically
   ```
3. On Windows: `get_data_path()` returns `C:\Program Files\ani-tupi`
4. Token file: `C:\Program Files\ani-tupi\anilist_token.json`
5. Works correctly on both Windows and Linux
6. No platform-specific code in anilist.py

---

### Requirement: Duplicate path constants MUST be removed

The system MUST eliminate all duplicate `HISTORY_PATH`, `CACHE_FILE`, and `TOKEN_FILE` constants by using centralized config.

**Previously:** Same logic duplicated in 4+ files:
- `main.py:15` - `HISTORY_PATH`
- `anilist_menu.py:16` - `HISTORY_PATH` (duplicate)
- `scraper_cache.py:8` - `CACHE_FILE` (duplicate logic)
- `anilist.py:21` - `TOKEN_FILE` (duplicate logic)

**Details:**
- Remove all module-level path constants
- Import from config: `from config import settings`
- Access via: `settings.anilist.token_file`, `settings.cache.cache_file`
- History path: `get_data_path() / "history.json"` (used directly, no setting needed)
- Single source of truth in `config.py`

#### Scenario: Cache file path used in scraper

1. Previously in `scraper_cache.py:8`:
   ```python
   CACHE_FILE = (
       Path.home() / ".local/state/ani-tupi/scraper_cache.json"
       if __import__("os").name != "nt"
       else Path("C:\\Program Files\\ani-tupi\\scraper_cache.json")
   )
   ```
2. Now in `scraper_cache.py`:
   ```python
   from config import settings

   # Use throughout module
   cache_file = settings.cache.cache_file
   ```
3. Path automatically correct for current OS
4. Can be overridden via environment variable:
   ```bash
   export ANI_TUPI__CACHE__CACHE_FILE=/tmp/ani-tupi-cache.json
   ```
5. No code changes needed for custom paths

---

## REMOVED Requirements

### Requirement: REMOVE inline OS detection from file path definitions

The system MUST remove all inline OS detection (e.g., `if name != "nt"`) from file path definitions.

**Previously:** Inline ternary operators scattered across files:
```python
HISTORY_PATH = (
    Path.home() / ".local/state/ani-tupi"
    if name != "nt"
    else Path("C:\\Program Files\\ani-tupi")
)
```

**Details:**
- Delete all inline OS checks for paths
- Replace with imports from config module
- OS detection happens once in `get_data_path()`
- Cleaner, more testable code

#### Scenario: Removing duplicate history path logic

1. Before in `main.py:15`:
   ```python
   from os import name
   from pathlib import Path

   HISTORY_PATH = (
       Path.home() / ".local/state/ani-tupi"
       if name != "nt"
       else Path("C:\\Program Files\\ani-tupi")
   )
   ```
2. After in `main.py`:
   ```python
   from pathlib import Path
   from config import get_data_path

   HISTORY_PATH = get_data_path()
   ```
3. OS detection logic removed from `main.py`
4. Same functionality, cleaner code
5. Testable: Can mock `get_data_path()` in tests

---

## Cross-References

**Related Capabilities:**
- `configuration-management` - Path settings use `get_data_path()` in field defaults
- `data-validation` - Path fields validated as `pathlib.Path` type

**Dependencies:**
- Requires: Python 3.8+ (pathlib standard library)
- No external dependencies for path resolution

**Migration Path:**
1. Create `get_data_path()` in `config.py`
2. Update config settings to use `get_data_path()` in field defaults
3. Replace `HISTORY_PATH` in `main.py` with `get_data_path()`
4. Remove duplicate `HISTORY_PATH` from `anilist_menu.py`
5. Replace `CACHE_FILE` in `scraper_cache.py` with `settings.cache.cache_file`
6. Replace `TOKEN_FILE` in `anilist.py` with `settings.anilist.token_file`
7. Remove all `if name != "nt"` checks for paths
8. Test on both Linux and Windows to verify correct paths

---

## Platform Support

**Supported Platforms:**
- Linux (any distribution)
- macOS (all versions)
- Windows 10/11

**Path Conventions:**
- **XDG Base Directory Specification** (Linux): `~/.local/state/` for app state
- **macOS**: Uses `~/.local/state/` (same as Linux for consistency)
- **Windows**: `C:\Program Files\ani-tupi\` (standard application data location)

**Future Enhancement:**
Could support `APPDATA` environment variable on Windows for per-user installations:
```python
if os.name == "nt":
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "ani-tupi"
    return Path("C:\\Program Files\\ani-tupi")
```

---

## Testing Strategy

**Unit Tests:**
```python
import pytest
from unittest.mock import patch
from config import get_data_path

def test_data_path_linux(monkeypatch):
    """Test Linux/macOS path resolution."""
    monkeypatch.setattr('os.name', 'posix')
    assert get_data_path() == Path.home() / ".local" / "state" / "ani-tupi"

def test_data_path_windows(monkeypatch):
    """Test Windows path resolution."""
    monkeypatch.setattr('os.name', 'nt')
    assert get_data_path() == Path("C:\\Program Files\\ani-tupi")

def test_token_file_uses_data_path():
    """Test token file path is OS-aware."""
    from config import settings
    expected = get_data_path() / "anilist_token.json"
    assert settings.anilist.token_file == expected
```

**Integration Tests:**
- Run on Linux: Verify files created in `~/.local/state/ani-tupi/`
- Run on Windows (if available): Verify files in `C:\Program Files\ani-tupi\`
- Manual testing: Check file locations after running app
