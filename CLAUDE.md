<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## Clean Error Messages - IMPROVED ✓

### Change (2026-01-01)
Removed verbose error messages and Selenium stacktraces that cluttered user output during fallback attempts.

### What Changed

**Before:**
```
⚠️  Erro ao extrair source do vídeo: Message: Unable to locate element:
[id="my-video_html5_api"]; For documentation on this error, please visit:
https://www.selenium.dev/documentation/webdriver/troubleshooting/errors#no-such-element-exception
Stacktrace:
RemoteError@chrome://remote/content/shared/RemoteError.sys.mjs:8:8
WebDriverError@chrome://remote/content/shared/webdriver/Errors.sys.mjs:202:5
NoSuchElementError@chrome://remote/content/shared/webdriver/Errors.sys.mjs:555:5
dom.find/</<@chrome://remote/content/shared/DOM.sys.mjs:136:16
```

**After:**
```
🔄 Tentando fontes: animefire, animesonlinecc
❌ animefire falhou: Unable to locate element: [id="my-video_html5_api"]
✅ Vídeo encontrado em: animesonlinecc
```

### Implementation

**Changes in `plugins/animefire.py`:**
- Removed all intermediate error prints from functions:
  - `extract_quality_options()` - Removed error prints at lines 85, 131, 146
  - `extract_blogger_video_url()` - Removed error prints at lines 193, 209, 216, 220, 236, 253
  - Removed `traceback.print_exc()` call
- Functions now either return None silently or raise exceptions for repository to handle

**Existing Clean Handling in `repository.py`:**
- `safe_plugin_call()` already implemented (lines 546-555)
- Catches exceptions and shows only first line (max 80 chars)
- Format: `❌ {source} falhou: {error[:80]}`

**User Experience:**
- Multi-source fallback still works perfectly
- Errors are now concise and actionable
- No overwhelming stacktraces in terminal
- Success/failure clearly indicated with emojis

### Files Modified
- `plugins/animefire.py` (removed error prints from multiple functions)

---

## Multi-Source Fallback System - IMPLEMENTED ✓

### Feature (2026-01-01)
Automatic fallback between multiple anime sources when one fails.

### How It Works

**Source Registration:**
- Multiple plugins can be active simultaneously (animefire, animesonlinecc)
- Each plugin registers itself in the repository
- Sources are tried in parallel when extracting video URLs

**Fallback Flow:**
```
Episode selected → Extract video URL from all sources in parallel →
→ First successful source wins → If all fail, show clear error message
```

**Example Output:**
```
🔄 Tentando fontes: animefire, animesonlinecc
❌ animefire falhou: Unable to locate element: [id="my-video_html5_api"]
✅ Vídeo encontrado em: animesonlinecc
```

### Implementation Details

**Error Handling** (`repository.py::search_player`):
- `safe_plugin_call()` wrapper catches exceptions from plugins
- Errors are logged but don't stop execution
- Other sources continue attempting extraction
- Returns None only if ALL sources fail

**User Feedback:**
- Shows which sources are being tried
- Shows which source succeeded/failed
- Shows first line of error (avoids huge stack traces)
- Clear error message if no sources succeed

**None Protection** (`main.py`, `core/anime_service.py`):
- Checks if video URL is None before calling `play_video()`
- Shows helpful error message suggesting retry or different episode
- Returns to episode menu instead of crashing

### Files Modified
- `repository.py` (lines 540-555) - Added exception handling wrapper
- `main.py` (lines 122-127) - Added None check and error message
- `core/anime_service.py` (lines 641-646) - Added None check and error message
- `plugins/animesonlinecc.py` - Restored from commit 40fae3e, updated to selectolax

### Troubleshooting

**One source always fails:**
- Normal behavior if site structure changed
- Other sources will automatically be tried
- Error message shows which source failed and why

**All sources fail:**
- Episode may be unavailable on all sites
- Try another episode or different anime
- Check if sites are accessible via browser

**Plugin not loading:**
- Check `plugin_manager.py` for disabled plugins
- Ensure plugin is in `plugins/` directory
- Verify plugin has `load()` function

---

## Video Quality Selection - IMPLEMENTED ✓

### Feature (2026-01-01)
Users can now select video quality before playback (720p, 480p, 360p, etc) for AnimeFire videos.

### How It Works

**AnimeFire Quality Detection** (primary method):
1. **Page Inspection**: Uses Selenium to inspect episode page on AnimeFire
2. **Quality Extraction**: Extracts available qualities from page controls (`<div class="video-ql">`)
3. **Direct URLs**: Builds direct MP4 URLs from pattern: `https://lightspeedst.net/s5/mp4_temp/{anime}/{ep}/{quality}.mp4`
4. **Quality Menu**: Shows available qualities with current quality marked
5. **Direct Playback**: Passes MP4 URL directly to MPV (no yt-dlp needed)

**Example Flow:**
```
Episode page URL → Selenium extracts qualities → User selects → Direct MP4 playback
https://animefire.io/animes/shokuba/1 → [720p, 480p, 360p] → 720p → lightspeedst.net/.../720p.mp4
```

### Implementation Details

**New Files:**
- `plugins/animefire.py::extract_quality_options(url_episode)` - Extracts qualities from page
- `video_player.py::select_quality_animefire(url, qualities)` - Quality selection menu
- `repository.py::get_episode_url_and_source(anime, ep)` - Get episode URL and source name

**Integration Points:**
- `main.py` (line ~98): Detects AnimeFire source, extracts qualities, shows menu
- `core/anime_service.py` (line ~617): Same integration for AniList flow

**Quality Detection Process:**
1. Selenium loads episode page (headless Firefox)
2. Closes banner/popup if present
3. Extracts current video source to get base URL
4. Finds quality control elements (`id-720p`, `id-360p`, etc)
5. Filters disabled qualities (have `text-gray` class)
6. Returns list of available qualities with URLs

**Testing:**
```bash
# Test quality extraction from page
uv run --with selenium test_extract_qualities.py

# Test full integration
uv run test_quality_integration.py

# Real usage
uv run ani-tupi
# → Select anime
# → Select episode
# → Quality menu appears automatically for AnimeFire
```

**Menu Behavior:**
- Shows only available qualities (disabled ones filtered out)
- Current quality marked with ▶️ marker
- ESC/Voltar cancels and skips episode
- Arrow keys to navigate, Enter to select

**Fallback:**
- If quality detection fails, falls back to `search_player()` async flow
- Other sources (non-AnimeFire) still use original Blogger extraction

### Troubleshooting

**No qualities detected:**
- Check Selenium/geckodriver installed: `sudo pacman -S firefox geckodriver`
- AnimeFire may have changed page structure
- Check console output for extraction errors

**Quality menu slow:**
- First load takes ~3-5s (Selenium page load + extraction)
- Loading spinner shows "Detectando qualidades disponíveis..."
- Browser runs headless (invisible)

**Wrong quality plays:**
- URL pattern may have changed on AnimeFire
- Check browser Network tab for actual video URLs
- Verify URL pattern in `extract_quality_options()`

**Banner blocks extraction:**
- Function tries common close selectors automatically
- If banner persists, may need to update close selectors in code

---

## Blogger Video URLs & yt-dlp Integration - SOLVED ✓

### Issue (2026-01-01)
MPV was failing to play videos from AnimeFire with exit code 2. URLs were from Blogger with temporary tokens.

### Root Cause
1. **Video URL caching** - URLs with temporary tokens were being cached and reused after expiration
2. **yt-dlp missing** - MPV requires yt-dlp to process Blogger video pages
3. **Manual extraction attempted** - Tried extracting VIDEO_CONFIG from Blogger pages, but tokens expired during processing

### Solution Implemented (2026-01-01)

**1. Installed yt-dlp:**
```bash
sudo pacman -S yt-dlp
```

**2. Disabled video URL caching** (`repository.py` lines 513-515, 551-553):
- Removed cache lookup for video URLs (tokens expire too quickly)
- Only episode lists are cached, not video stream URLs
- This prevents playback failures from expired cached URLs

**3. Removed manual Blogger extraction** (`plugins/animefire.py` lines 195-200):
- Pass Blogger URLs directly to MPV
- yt-dlp processes URLs in real-time (no delay = no expiration)
- Much more reliable than manual extraction

**4. Added VLC fallback** (`video_player.py` lines 45-73):
- If MPV fails (exit code 2), automatically tries VLC
- Removed `check=True` to prevent exceptions on non-zero exit codes
- Always asks user if they watched until the end (regardless of exit code)

### How It Works Now
```
Selenium extracts iframe URL (2-3s)
  → Passes Blogger URL directly to MPV
  → MPV calls yt-dlp automatically
  → yt-dlp extracts stream in real-time
  → Video plays ✅
```

### Test Results
- ✅ **Dan Da Dan Ep 1**: Works perfectly (yt-dlp processes successfully)
- ❌ **Wotaku Ep 1**: "Video is unavailable" on Blogger (not our fault - video removed from source)

**UPDATE (2026-01-01 - Evening):**
Fixed critical bug preventing yt-dlp integration:
- **Bug**: `--ytdl-raw-options=concurrent-fragments=3-5` was invalid (yt-dlp expects integer, not range)
- **Error**: `yt-dlp: error: option --concurrent-fragments: invalid integer value: '3-5'`
- **Fix**: Changed to `concurrent-fragments=5` in `video_player.py` line 252
- **Impact**: MPV can now properly invoke yt-dlp to process Blogger URLs

### Verification
Test with fresh URLs:
```bash
uv run test_real_flow.py  # Simulates complete flow with yt-dlp
```

### Important Notes
- **Some videos will be unavailable** - this is expected (content removed from AnimeFire/Blogger)
- **Always test with different anime/episodes** if one fails
- **Cache cleared**: `rm ~/.local/state/ani-tupi/scraper_cache.json` if needed
- **yt-dlp handles tokens automatically** - no manual extraction needed

### Files Modified
- `repository.py` - Disabled video URL caching
- `plugins/animefire.py` - Removed manual Blogger extraction
- `video_player.py` - Added VLC fallback, better error handling
- `test_real_flow.py`, `test_ytdlp.py` - Debug/test scripts

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ani-tupi is a terminal-based anime/manga streaming application in Brazilian Portuguese that follows a **modular architecture**:

- **Core Services** (`core/`): Business logic and external API integrations
  - `core/anilist_service.py` - AniList GraphQL client
  - `core/history_service.py` - Watch history management
- **UI Layer** (`ui/`): User interface components and menus
  - `ui/components.py` - Reusable menu widgets (Rich + InquirerPy)
  - `ui/anilist_menus.py` - AniList browsing interface
- **Data Layer**: Singleton data store and models
  - `repository.py` - Central data store managing anime/episode/video URL mappings
  - `models.py` - Pydantic models for type-safe data
  - `config.py` - Centralized configuration
- **Plugin System** (`loader.py` + `plugins/*`): Extensible scraper system for anime sources
- **Entry Points**:
  - `cli.py` - Main CLI entry point for ani-tupi
  - `manga_tupi.py` - Manga mode entry point
  - `main.py` - Legacy controller (to be refactored)

## Development Commands

### Running the Application

```bash
# Development mode (no installation)
uv run ani-tupi                      # Run anime mode
uv run manga-tupi                    # Run manga mode
uv run main.py --debug               # Debug mode (skips video playback)
uv run main.py -q "dandadan"         # Direct search query
uv run main.py --continue-watching   # Resume last watched

# Cache management
uv run ani-tupi --clear-cache        # Clear all cache
uv run ani-tupi --clear-cache "Dandadan"  # Clear cache for specific anime

# AniList integration
uv run ani-tupi anilist auth         # Authenticate with AniList
uv run ani-tupi anilist              # Browse AniList lists (trending, watching, etc)

# Install as global CLI tool (recommended for testing)
python3 install-cli.py               # Installs to ~/.local/bin/
ani-tupi                             # Use globally after install

# Uninstall global CLI
uv tool uninstall ani-tupi
```

### Dependency Management

```bash
# Install/sync dependencies
uv sync                              # Install all dependencies

# Add new dependency
uv add package-name                  # NEVER edit pyproject.toml directly

# Add dev dependency
uv add --dev package-name
```

### Code Linting

```bash
# Run ruff linter
uvx ruff check .

# Auto-fix issues
uvx ruff check --fix .

# Format code
uvx ruff format .
```

**Ruff Configuration:**
The project uses a custom ruff configuration in `pyproject.toml` that ignores less critical rules while maintaining code quality. The configuration is tailored for this codebase's pragmatic approach to linting:

- **Ignored rules include**: Overly strict docstring requirements (D107, D205, D401), complexity metrics (C901, PLR*), type annotation requirements (ANN*), and security checks that don't apply to this use case (S603, S607 for mpv subprocess calls).
- **Line length**: Set to 100 characters (more flexible than the default 88).
- **Key fixes applied**: Changed `open()` to `Path.open()` where practical, removed commented-out code, improved docstring formatting.

If you encounter new lint errors, consider whether they represent real issues or if the rule should be added to the ignore list in `pyproject.toml`.

### Installing as CLI Tool

```bash
# Recommended: Install globally using install-cli.py
python3 install-cli.py               # Installs to ~/.local/bin/ via uv tool install
ani-tupi                             # Use globally after install

# Uninstall
uv tool uninstall ani-tupi

# Force reinstall (after code changes)
uv tool install --reinstall .        # Required to pick up source code changes
```

### Common Issues

**FileNotFoundError when running from outside project directory:**
- **Problem**: `loader.py` uses `get_resource_path()` to locate plugins
- **Root cause**: Using `abspath(".")` returns current working directory, not installation path
- **Solution**: Changed to `dirname(abspath(__file__))` which returns the module's install location
- **After fixing**: Must use `uv tool install --reinstall .` to rebuild the package (UV caches builds)

**Video player won't open when selecting an episode:**
- **Problem**: App shows "Buscando vídeo..." but player never launches; goes straight to "Did you watch to the end?" prompt
- **Root cause**: `geckodriver` is missing. The animefire plugin uses Selenium + Firefox to extract video URLs, and Selenium requires geckodriver
- **Solution**: Install geckodriver via `sudo pacman -S geckodriver` (or via Omarchy GUI: `Super + Alt + Space → Install > Package`)
- **Verification**: Run `which geckodriver && geckodriver --version` to confirm installation
- **Also fixed**: Added error handling in `repository.py::search_player()` to prevent IndexError when video URL extraction fails

## Configuration Management

### Pydantic Configuration (`config.py`)

As of 2025-12-31, ani-tupi uses **Pydantic v2** for runtime type validation and centralized configuration.

**Key Features:**
- **Type Safety**: Runtime validation of all configuration values
- **Centralized Settings**: Single source of truth in `config.py` instead of scattered magic numbers
- **Environment Variable Support**: Override settings via `ANI_TUPI__*` env vars
- **OS-Aware Paths**: Single `get_data_path()` replaces duplicated platform-specific logic
- **Validation**: Invalid config values raise clear errors on startup

**Available Settings:**

```python
from config import settings

# AniList API
settings.anilist.api_url         # GraphQL endpoint (default: graphql.anilist.co)
settings.anilist.auth_url        # OAuth authorization URL
settings.anilist.client_id       # Public OAuth client ID
settings.anilist.token_file      # Path to access token (auto-resolved OS path)

# Cache
settings.cache.duration_hours    # Cache validity (1-72 hours, default 6)
settings.cache.cache_file        # Path to cache JSON (auto-resolved OS path)

# Search
settings.search.progressive_search_min_words  # Min words for progressive search (1-10, default 2)
```

**Environment Variable Override:**

```bash
# Override any setting with ANI_TUPI__SECTION__SETTING=value
export ANI_TUPI__SEARCH__FUZZY_THRESHOLD=85
export ANI_TUPI__CACHE__DURATION_HOURS=12
export ANI_TUPI__ANILIST__CLIENT_ID=12345

uv run ani-tupi  # Uses custom config
```

**Local Development (.env file):**

```bash
# Copy .env.example to .env and customize
cp .env.example .env
# Edit .env with your settings
uv run ani-tupi  # Automatically loads .env
```

**Path Resolution:**

```python
from config import get_data_path

path = get_data_path()  # ~/.local/state/ani-tupi (Linux/macOS)
                        # C:\Program Files\ani-tupi (Windows)
```

All config-aware modules import `settings` from `config.py`:
- `repository.py` - Uses progressive_search_min_words
- `core/anilist_service.py` - Uses API URLs, client_id, token_file
- `scraper_cache.py` - Uses cache_file and duration_hours
- `main.py`, `ui/anilist_menus.py`, `core/history_service.py` - Use get_data_path() for history/mappings

### Data Models (`models.py`)

Pydantic models for structured data validation:

```python
from models import AnimeMetadata, EpisodeData, VideoUrl

# AnimeMetadata: Anime from scraper
anime = AnimeMetadata(
    title="Dandadan",
    url="https://example.com/dandadan",
    source="animefire",
    params=None  # Optional scraper params
)

# EpisodeData: Episode list (validates title/URL length match)
episodes = EpisodeData(
    anime_title="Dandadan",
    episode_titles=["Ep1", "Ep2"],
    episode_urls=["url1", "url2"],
    source="animefire"
)

# VideoUrl: Playback URL with optional headers
video = VideoUrl(
    url="https://example.com/stream.m3u8",
    headers={"User-Agent": "Mozilla/5.0"}
)
```

## Architecture Deep Dive

### Module Organization (as of 2026-01-01)

The codebase is organized into clear layers:

```
ani-tupi/
├── core/                    # Business logic layer
│   ├── __init__.py
│   ├── anilist_service.py   # AniList GraphQL API client
│   └── history_service.py   # Watch history management
├── ui/                      # User interface layer
│   ├── __init__.py
│   ├── components.py        # Reusable menu widgets (menu, loading)
│   └── anilist_menus.py     # AniList browsing interface
├── plugins/                 # Scraper plugins (no changes)
│   ├── animefire.py
│   └── animesonlinecc.py
├── cli.py                   # NEW: CLI entry point
├── main.py                  # Legacy controller (contains most business logic)
├── manga_tupi.py            # Manga mode entry point
├── repository.py            # Singleton data store
├── models.py                # Pydantic data models
├── config.py                # Centralized configuration
└── loader.py                # Plugin discovery system
```

**Dependency Rules:**
- `core/` can import: `models`, `config`, `repository`, `loader`
- `ui/` can import: `core/`, `models`, `config`, `repository`
- `plugins/` can import: `loader`, `repository`, `models`
- `cli.py` imports: `main` (for now - will evolve to use `ui/` and `core/` directly)

### TUI System (Rich + InquirerPy)

**Architecture:** As of 2025-12-31, the TUI has been refactored from Textual to Rich + InquirerPy for better performance and simplicity.

**Core Components:**
- `ui/components.py` - Interactive menus using InquirerPy (arrow keys, ESC, Q) + loading spinners using Rich
- `ui/anilist_menus.py` - AniList browsing interface

**Key Features:**
- **Stateless Functions**: No app instances, functions return immediately
- **Loading Indicators**: Spinners show during API calls (search, episode fetch, video URL discovery)
- **Catppuccin Mocha Theme**: Purple (#cba6f7) highlights, dark background (#1e1e2e)
- **Keyboard Navigation**: Arrows to navigate, Enter to select, ESC to go back, Q to quit
- **Fuzzy Search**: Always enabled - type to filter options instantly in any menu

**Performance:**
- Menu transitions: ~50ms (was ~500ms with Textual)
- No flickering or app recreation
- Code reduced by 65% (527 lines → 175 lines in menu.py)

**Adding Loading Spinners to New Code:**
```python
from ui.components import loading

# Wrap slow operations with spinner
with loading("Buscando animes..."):
    rep.search_anime(query)

# Spinner automatically disappears when done
```

**Using Menus with Search:**
```python
from ui.components import menu, menu_navigate

# Basic menu (fuzzy search enabled by default)
selected = menu(["Option 1", "Option 2"], "Choose")

# Navigation menu (fuzzy search enabled by default)
selected = menu_navigate(["Item 1", "Item 2"], "Select")

# Disable search if needed (use arrow keys only)
selected = menu(options, "Choose", enable_search=False)

# Fuzzy search is ALWAYS enabled by default:
# - Type to filter options (fuzzy matching)
# - Arrow keys to navigate filtered results
# - ESC to go back, Q to quit
```

### Application Flow (Anime Mode)

```
CLI → Plugin Loading → Search Anime → Select Anime → Get Episodes →
→ Select Episode → [Video Playback Loop: Get URL → Play → Save History → Next/Previous/Exit]
```

**Critical: Video URL Discovery** uses async race pattern (`repository.py::search_player`):
- Runs all plugins in parallel using `asyncio.wait(return_when=FIRST_COMPLETED)`
- Returns first successful video URL
- Uses container/event pattern to prevent race conditions

### Plugin System

**Creating a New Plugin:**

1. Create `plugins/yourplugin.py`
2. Implement `PluginInterface` (ABC from `loader.py`):
   ```python
   class YourPlugin(PluginInterface):
       name = "yourplugin"
       languages = ["pt-br"]

       @staticmethod
       def search_anime(query: str) -> None:
           # Scrape search results
           # Call: rep.add_anime(title, url, YourPlugin.name)

       @staticmethod
       def search_episodes(anime: str, url: str, params) -> None:
           # Scrape episode list
           # Call: rep.add_episode_list(anime, titles, urls, YourPlugin.name)

       @staticmethod
       def search_player_src(url_episode: str, container: list, event: asyncio.Event) -> None:
           # Extract video URL (m3u8/mp4)
           # If found: container.append(url) and event.set()

   def load(languages_dict):
       if "pt-br" in languages_dict:
           rep.register(YourPlugin)
   ```

3. Plugin auto-discovered on next run (no registration needed)

**Plugin Discovery:**
- `loader.py::load_plugins()` scans `plugins/` directory
- Excludes `__init__.py` and `utils.py`
- Only loads plugins matching requested languages (default: `["pt-br"]`)

### Repository Pattern (Singleton)

`repository.py` maintains central data structures:

```python
self.sources = dict()                           # {plugin_name: PluginClass}
self.anime_to_urls = defaultdict(list)          # {title: [(url, source, params)]}
self.anime_episodes_titles = defaultdict(list)  # {anime: [[title_list]]}
self.anime_episodes_urls = defaultdict(list)    # {anime: [(url_list, source)]}
self.norm_titles = dict()                       # {title: normalized_title}
```

**Fuzzy Matching Logic:**
- Normalizes titles (removes accents, punctuation, "temporada" → "season")
- Uses `fuzzywuzzy.fuzz.ratio()` with 95% threshold
- Deduplicates similar anime across sources (e.g., "Dan Da Dan" vs "DanDaDan")

**Parallel Execution:**
- `search_anime()`: ThreadPool across all plugins (workers = min(num_plugins, cpu_count))
- `search_episodes()`: One thread per source
- `search_player()`: Asyncio race pattern (returns first result)

### Video Playback

`video_player.py` is minimal:
```python
subprocess.run(["mpv", url, "--fullscreen", "--cursor-autohide-fs-only", "--log-file=log.txt"])
```

**Dependencies:**
- Requires `mpv` on system PATH
- Requires `firefox` for Selenium scrapers
- Supports snap Firefox via `/snap/bin/geckodriver`

### History System

**Location:** `~/.local/state/ani-tupi/history.json` (Linux/macOS) or `C:\Program Files\ani-tupi\` (Windows)

**Format:**
```json
{
    "Anime Title": [timestamp, episode_index]
}
```

**Continue Watching Flow:**
1. Read history.json
2. Display menu with last watched episode: "Anime (Ultimo episódio assistido N)"
3. Strip suffix before lookup, jump to saved episode

### Curses TUI (`menu.py`)

**Color Scheme:**
- Pair 1: Black on Yellow (selected)
- Pair 2: Yellow on Black (title/normal)

**Features:**
- Arrow key navigation with viewport scrolling
- Auto-appends "Sair" (Exit) option
- Wraps around (first ↔ last)
- Handles terminal resize via `screen_height - 2`

## Build System Details

### Two Distribution Methods

1. **CLI Tool (Recommended):** `python3 install-cli.py` → Installs to `~/.local/bin/` via `uv tool install`
2. **Development Mode:** `uv run ani-tupi` → No installation required

### Plugin Loading

All plugin loading uses `get_resource_path()` helper in `loader.py` to handle different execution contexts (development vs installed).

### Cross-Platform Considerations

**Windows-specific:**
- `windows-curses` dependency (conditional in pyproject.toml)
- UTF-8 encoding reconfiguration in main.py
- Different history path: `C:\Program Files\ani-tupi\`

**Snap Firefox Detection:**
```python
def is_firefox_installed_as_snap() -> bool:
    result = subprocess.run(["snap", "list", "firefox"], capture_output=True)
    return result.returncode == 0
```

## Common Modification Scenarios

### Adding a New Anime Source

1. Create `plugins/newsource.py` implementing `PluginInterface`
2. Set `name` and `languages = ["pt-br"]`
3. Implement three static methods (search_anime, search_episodes, search_player_src)
4. Add `load()` function calling `rep.register(YourClass)`
5. Test: `uv run main.py --debug -q "test anime"`

**Note:** Use Selenium + BeautifulSoup pattern from existing plugins (animefire.py, animesonlinecc.py)

### Changing UI Colors

Edit `menu.py::menu()` function:
```python
curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # Selected
curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Normal
```

### Modifying Video Player Behavior

Edit `video_player.py::play_video()`:
- Add MPV flags to subprocess.run() command
- Example: Add `"--sub-auto=fuzzy"` for auto-subtitle loading

### Adding New Data Fields

1. Add to Repository class in `repository.py` (likely a new `defaultdict`)
2. Create getter/setter methods
3. Update plugins to populate the data via repository methods

## Debug Mode

**Flag:** `--debug` or environment variable check in main.py

**Effects:**
- Skips actual video playback (`video_player.py` returns immediately)
- Useful for testing search/episode extraction without MPV
- Logs still written to `log.txt`

**Usage:**
```bash
uv run main.py --debug -q "anime name"
```

## AniList Integration

### Overview

AniList.co integration allows users to:
- Browse trending anime
- Access their watch lists (Watching, Planning, Completed, etc)
- Automatically sync progress after watching episodes
- Get personalized recommendations

### Architecture

**Files:**
- `anilist.py` - GraphQL client for AniList API
- `anilist_menu.py` - Curses menu for browsing AniList data
- `main.py::anilist_anime_flow()` - Integration with normal playback flow

**Flow:**
```
ani-tupi anilist → Menu (Trending/Lists) → Select Anime →
→ Search in scrapers → Select Episode → Watch → Update AniList progress
```

### GraphQL Client (`anilist.py`)

**Authentication:**
- Uses OAuth implicit grant flow (no client secret needed)
- Client ID: 21576 (public)
- Token stored at `~/.local/state/ani-tupi/anilist_token.json`
- Browser-based auth: Opens AniList.co, user copies token

**Key Methods:**
```python
anilist_client.authenticate()                  # OAuth flow
anilist_client.get_trending(per_page=50)       # Trending anime
anilist_client.get_user_list("CURRENT")        # User's watching list
anilist_client.update_progress(anime_id, ep)   # Sync progress
anilist_client.search_anime(query)             # Search by title
```

**Available List Types:**
- `CURRENT` - Currently watching
- `PLANNING` - Plan to watch
- `COMPLETED` - Finished
- `PAUSED` - On hold
- `DROPPED` - Dropped
- `REPEATING` - Rewatching

### Menu System (`anilist_menu.py`)

**Main Menu:**
- Shows "Trending" always (no login required)
- If logged in: Shows username + all list types
- Uses same curses styling as main menu (yellow/black)

**Anime List View:**
- Displays anime with progress: `Title (3/12) ⭐85%`
- Handles both trending (no progress) and user lists (with progress)
- Returns `(anime_title, anilist_id)` tuple on selection

### Integration with Scrapers

**Title Matching:**
1. User selects anime from AniList (e.g., "Dan Da Dan")
2. `anilist_anime_flow()` searches scrapers using that title
3. If multiple results, user picks correct match
4. Normal episode selection flow continues
5. After watching: Updates both local history AND AniList

**Progress Sync:**
- Happens automatically after each episode
- Uses AniList ID to ensure correct anime
- Silent on success, shows warning on failure
- Non-blocking (doesn't interrupt playback if fails)

### OAuth Setup

**First-time auth:**
```bash
ani-tupi anilist auth
# 1. Browser opens to AniList.co
# 2. User authorizes ani-tupi
# 3. Redirected to: https://anilist.co/api/v2/oauth/pin?access_token=...
# 4. User copies token and pastes into terminal
# 5. Token validated and saved
```

**Token persistence:**
- Saved to `~/.local/state/ani-tupi/anilist_token.json`
- Valid indefinitely (until user revokes)
- No refresh needed (implicit grant)

### Adding AniList Features

**To add new GraphQL query:**
1. Add method to `AniListClient` in `anilist.py`
2. Define GraphQL query string
3. Call `self._query(query, variables)`
4. Handle response

**To add menu option:**
1. Add to `anilist_menu.py::anilist_main_menu()`
2. Create handler function (similar to `_show_anime_list()`)
3. Return result or call `anilist_main_menu()` to loop

## Key Files Reference

**Entry Points:**
- `cli.py` - NEW: Main CLI entry point (thin wrapper for now)
- `manga_tupi.py` - Manga mode entry point (MangaDex API)

**Core Services:**
- `core/anilist_service.py` - AniList GraphQL API client
- `core/history_service.py` - Watch history management (load/save/reset)

**UI Layer:**
- `ui/components.py` - Reusable menu widgets (menu, menu_navigate, loading)
- `ui/anilist_menus.py` - AniList browsing interface

**Data & Business Logic:**
- `main.py` - Legacy controller (contains most business logic - to be refactored)
- `repository.py` - Singleton data store, search orchestration
- `models.py` - Pydantic data models (AnimeMetadata, EpisodeData, VideoUrl)
- `config.py` - Centralized configuration (Pydantic Settings)

**Plugin System:**
- `loader.py` - Plugin discovery and loading system
- `plugins/animefire.py` - Example scraper plugin (animefire.plus)
- `plugins/animesonlinecc.py` - Example scraper plugin (animesonlinecc.to)

**Utilities:**
- `video_player.py` - MPV subprocess wrapper
- `install-cli.py` - Global CLI installer
- `pyproject.toml` - Project configuration (dependencies, entry points)

## CI/CD (GitHub Actions)

Located in `.github/workflows/`:
- `ci.yml` - Fast validation on push/PR (syntax checks, dependency validation)
- `build-test.yml` - Tests install-cli.py on multiple platforms

## Future Enhancement Ideas (from todo.txt)

- Watch lists implementation
- Switch to pytermgui for richer TUI (better than curses)
- Use python-mpv for programmatic video control
- AI recommendation system (Gemini/LLaMA)
- Cython optimization for repository/model layer
