# Project Context

## Purpose

ani-tupi is a terminal-based anime and manga streaming application in Brazilian Portuguese. It provides a unified interface to search, browse, and play anime and manga from multiple sources (animes sites), with integration to AniList.co for progress tracking and watch list management.

**Key Goals:**
- Lightweight, keyboard-driven TUI alternative to web browsers
- Multi-source scraping for anime content (animefire.plus, animesonlinecc.to, etc)
- AniList synchronization for watch progress and personalized recommendations
- Plugin-based extensibility for adding new anime/manga sources
- Cross-platform support (Linux, macOS, Windows)

## Tech Stack

**Core:**
- Python 3.8+
- UV (package manager and dependency resolver)
- Curses (terminal UI rendering)

**Scraping & HTTP:**
- Selenium + BeautifulSoup (web scraping)
- httpx (async HTTP client)
- Firefox/Geckodriver (browser automation)

**External APIs:**
- AniList GraphQL API (anime metadata, watch lists, progress sync)
- MangaDex API (manga content via `manga_tupi.py`)

**Video Playback:**
- MPV (media player)

**Utilities:**
- fuzzywuzzy (fuzzy string matching for anime title normalization)
- asyncio (async race patterns for plugin execution)
- pathlib (cross-platform path handling)

**Dev Tools:**
- pytest (testing - implicit, no current test suite)

## Project Conventions

### Code Style

- **Language:** Python 3 with type hints where reasonable (not strict)
- **Naming:** snake_case for functions/variables, CamelCase for classes
- **Line Length:** No strict limit but keep readable
- **Formatting:** Black-compatible (implicit, no formatter configured)
- **Docstrings:** Brief docstrings for public methods; inline comments for non-obvious logic
- **Async:** asyncio for I/O-heavy operations (plugin execution, API calls)
- **No magic numbers:** Use constants with descriptive names

### Architecture Patterns

**MVCP (Model-View-Controller-Plugin) Architecture:**

1. **Model** (`repository.py`)
   - Singleton pattern managing anime/episode/video URL mappings
   - Central data store shared across application
   - Manages fuzzy matching and title normalization
   - Orchestrates parallel plugin execution (ThreadPool for search, asyncio for video URL discovery)

2. **View** (`menu.py`)
   - Curses-based terminal UI with yellow-on-black color scheme
   - Stateless rendering function (pure function pattern)
   - Handles user input (arrow keys, selection)
   - Auto-appends "Sair" (Exit) option to all menus

3. **Controller** (`main.py`, `anilist_anime_flow()`, `manga_tupi.py`)
   - Application flow orchestration
   - User interaction routing
   - Error handling and recovery

4. **Plugin System** (`loader.py`, `plugins/*`)
   - Abstract base class `PluginInterface` defines three methods: `search_anime()`, `search_episodes()`, `search_player_src()`
   - Plugins auto-discovered from `plugins/` directory (excludes `__init__.py` and `utils.py`)
   - Language-filtered loading (default: `["pt-br"]`)
   - Race pattern for video URL discovery: first plugin to find URL wins, others cancelled

**Key Design Decisions:**
- **Singleton Repository:** Single source of truth, prevents data inconsistency
- **Parallel Search:** Multiple scrapers execute simultaneously (ThreadPool) for speed
- **Async Race for Video URLs:** Multiple plugins race to find first working URL (first-completed pattern)
- **Fuzzy Title Matching:** Deduplicates anime across sources with 95% similarity threshold
- **Plugin Isolation:** Each plugin owns its own scraping logic and authentication

### Testing Strategy

**Current State:** No formal test suite implemented

**Testing Approach (implicit):**
- Manual testing via CLI with `--debug` flag (skips video playback)
- GitHub Actions CI validates:
  - Syntax and imports (fast checks)
  - `install-cli.py` cross-platform installation
  - Dependency resolution via `uv sync`

**Recommended Testing (not yet implemented):**
- Unit tests for Repository class (title normalization, fuzzy matching)
- Integration tests for plugin discovery
- Mock-based tests for AniList client (external API)
- E2E test on sample anime searches

**Debug Mode:**
```bash
uv run main.py --debug -q "anime name"  # Skip video playback, test search flow
```

### Git Workflow

**Branching:**
- `master` - production-ready code
- Feature branches - merged via GitHub PRs with conventional commits

**Commit Convention:**
- `feat:` - New features (new plugins, new modes)
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `refactor:` - Code restructuring
- `chore:` - Dependency updates, CI changes

**Example:**
```
feat: adiciona automaticamente animes à lista Watching do AniList
fix: corrige FileNotFoundError ao executar CLI de fora da pasta do projeto
```

**Pull Requests:**
- Link to issues where applicable
- Include testing notes (manual test steps if no automated tests)
- Before merging, ensure `uv sync` and basic functionality work

## Domain Context

### Anime/Manga Streaming Context

**Brazilian Portuguese Market:**
- Heavy reliance on Portuguese-dubbed/subtitled content
- Common anime sites: animefire.plus, animesonlinecc.to (live scraping targets)
- Title normalization critical: "Dandadan 2nd Season; Episode 3" → "Dan Da Dan S02E03"
- Episode numbering: Most sites use `SXXYY` format (Season XX, Episode YY)

**AniList Integration:**
- AniList.co provides official anime database, user tracking, ratings
- OAuth implicit grant flow (Client ID: 21576, public)
- Supports multiple list types: CURRENT (watching), PLANNING, COMPLETED, PAUSED, DROPPED, REPEATING
- Progress sync happens after each watched episode

### Video Playback Context

- MPV is assumed installed on system (`mpv` in PATH)
- URLs extracted as m3u8 (HLS streams) or direct mp4 links
- Some streams require specific headers (User-Agent, Referer)
- Selenium-based scrapers may need Firefox snap detection on Linux

### Plugin System Context

**Scraper Challenges:**
- Websites change HTML structure frequently (brittle CSS selectors)
- JavaScript-heavy sites require Selenium (BeautifulSoup alone insufficient)
- Rate limiting and blocking (may need delays, rotating User-Agents)
- Geo-blocking or IP restrictions on some sources

**Plugin Pattern:**
```python
class ExamplePlugin(PluginInterface):
    name = "exampleplugin"
    languages = ["pt-br"]

    @staticmethod
    def search_anime(query: str) -> None:
        # Scrape, call rep.add_anime(title, url, ExamplePlugin.name)

    @staticmethod
    def search_episodes(anime: str, url: str, params) -> None:
        # Scrape, call rep.add_episode_list(anime, titles, urls, ExamplePlugin.name)

    @staticmethod
    def search_player_src(url_episode: str, container: list, event: asyncio.Event) -> None:
        # Extract video URL, container.append(url) then event.set()

def load(languages_dict):
    if "pt-br" in languages_dict:
        rep.register(ExamplePlugin)
```

## Important Constraints

**System Requirements:**
- Python 3.8+ (type hints, asyncio)
- MPV media player must be installed and in PATH
- Firefox browser (for Selenium-based plugins) - supports snap installations
- Terminal emulator supporting curses (Linux/macOS native; Windows via `windows-curses`)

**Technical Constraints:**
- **Single-threaded UI:** Curses is not thread-safe; long-running operations must preserve UI responsiveness
- **Plugin Discovery:** Only loads plugins matching requested language codes
- **Resource Paths:** Must use `get_resource_path()` for cross-platform and installed contexts
- **History Storage:** Different paths on Windows vs Linux/macOS
- **Cross-platform UTF-8:** Windows requires `io.setlocale()` reconfiguration

**External Service Constraints:**
- **Scraper Fragility:** Depends on website HTML stability (brittle CSS selectors)
- **AniList Rate Limits:** GraphQL API throttles high-frequency requests (not problematic for user-driven lookups)
- **Source Availability:** Some anime sources may require VPN, have region restrictions, or be blocked by ISPs

**Dependency Constraints:**
- Uses UV exclusively for package management (do not edit `pyproject.toml` directly)
- Installation via `install-cli.py` uses `uv tool install` (requires UV installed)
- Selenium/BeautifulSoup pattern requires specific element selectors (high maintenance burden)

## External Dependencies

### Third-party APIs

**AniList GraphQL API** (`anilist.py`)
- Endpoint: `https://graphql.anilist.co`
- Authentication: OAuth 2.0 implicit grant (no client secret)
- Uses: Trending anime, user watch lists, progress updates, anime search
- Rate Limits: Reasonable for human-driven usage

### Web Scraping Targets (Plugins)

**Active Sources:**
- `animefire.plus` - animefire plugin
- `animesonlinecc.to` - animesonlinecc plugin
- Additional sources in `plugins/` directory

**Scraping Method:** Selenium WebDriver + BeautifulSoup or httpx + BeautifulSoup depending on site JavaScript requirements

### External Tools

**MPV** (media player)
- Required system dependency
- Called via `subprocess.run(["mpv", url, "--fullscreen", ...])`
- Handles m3u8 streams and direct mp4 links natively

**Firefox** (browser automation)
- Required for Selenium-based plugins
- Linux: Snap detection via `snap list firefox`
- Geckodriver: Located in `/snap/bin/geckodriver` on snap installations

### Data Storage

**Local History** (`~/.local/state/ani-tupi/history.json` on Linux/macOS)
```json
{
    "Anime Title": [timestamp, episode_index]
}
```

**AniList Token** (`~/.local/state/ani-tupi/anilist_token.json`)
- OAuth access token (persisted indefinitely until user revokes)
- Used for all authenticated AniList requests

### CI/CD Infrastructure

**GitHub Actions Workflows** (`.github/workflows/`)
- `ci.yml` - Fast syntax/import validation on push/PR
- `build-test.yml` - Cross-platform installation testing
