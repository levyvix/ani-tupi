## General Rules and Guidelines

**Best Practices for writing Python code:**

### Design Principles
- Apply the DRY principle - Don't Repeat Yourself
- Prefer composition over inheritance for more maintainable code
- Write pure functions when possible (no side effects, same output for same input)
- Follow SOLID principles for maintainable object-oriented design
- Write tests first (TDD) or alongside code development
- Use dataclasses for data containers

### Handling Complexity
- Hide implementation details behind clean interfaces
- Create abstractions that eliminate complexity for users
- Encapsulate related data and behavior in cohesive classes
- Use interfaces or abstract base classes to define contracts
- Apply dependency injection for more flexible and testable code
- Favor simple solutions over complex or clever ones
- Design for the most common use case first
- Keep component coupling loose through well-defined interfaces

---

## Core Values

**Simplicity First**: Every feature should feel effortless to the user. Complex logic (incremental search, fuzzy matching, automatic syncing) runs invisibly.

**DRY Architecture**: Code is organized by *what it does*, not *where it lives*. If multiple scrapers implement `search()` → they're one pattern (plugin protocol). If multiple services fetch from APIs → they share a base class. If code repeats → extract it.

**Immutable Data Flow**: Data flows forward only. Services don't modify input; they return transformed copies. This makes debugging trivial: follow the data, not the mutations.

**Plugin Everything**: Scrapers, PDF readers, storage backends—all pluggable. New source? Create one file. Done.

**User Configuration Over Code**: Settings live in environment variables (via Pydantic config), not config files that break. Users can tune everything without touching code.

---

## CLI Usage Guide

### Basic Anime Playback

```bash
# Search and select anime interactively
ani-tupi -q "anime name"

# Search and jump to specific episode
ani-tupi -q "anime name" -e 5
```

### Advanced Options

```bash
# Select specific season (for anime with multiple seasons)
ani-tupi -q "anime name" -S 2

# Select specific season and episode
ani-tupi -q "anime name" -S 2 -e 5

# Continue from where you left off
ani-tupi -c

# Continue from specific episode (overrides history)
ani-tupi -c -e 5

# Continue from history but override to different season
ani-tupi -c -S 2

# List available sources
ani-tupi --list-sources

# Clear cache (all or specific anime)
ani-tupi --clear-cache
ani-tupi --clear-cache "anime name"
```

### Season and Episode Usage

- `-S 2` → Seleciona estação 2 (para anime com múltiplas estações)
- `-S 2 -e 5` → Estação 2, episódio 5 (pula menus)
- `-e 5` → Episódio 5 (navegação via menu para próximo/anterior disponível)
- `-e 1` → Início (episódio 1)
- `-e 100` → Erro se > total de episódios disponíveis

**Nota sobre estações**: Se um anime tem apenas uma estação, o menu de seleção é automaticamente pulado.

---

## Architecture Principles

### The Three-Tier System

1. **Commands** (CLI entry points) - Parse user intent
2. **Services** (business logic) - Coordinate plugins, cache, APIs, and persistence
3. **Plugins** (implementations) - Scrapers, readers, storage backends

Services orchestrate. They decide: "Should I search cache first?" "Should I sync to AniList?" "Which plugin should I use?"

Commands ask services questions. Services ask plugins for data. Plugins never ask anything—they're pure adapters.

**To extend**: Add a new feature? Build a service. Add a new data source? Build a plugin. Add a new command? Wire up a service call.

### Pattern: Centralized Configuration

All settings flow through `models/config.py` (Pydantic v2):

```python
from models.config import settings
cache_ttl = settings.cache_duration_hours
reader = settings.manga.pdf_reader
```

Why? Environment variables override defaults (`ANI_TUPI__CACHE__DURATION_HOURS=48`), no scattered `.env` files, type validation on boot, configuration is self-documenting.

### Pattern: Plugin Protocol (Not Inheritance)

Each plugin implements a structural type:

```python
class Scraper(Protocol):
    def search(self, query: str) -> list[AnimeMetadata]: ...
    def get_episodes(self, url: str) -> list[EpisodeData]: ...
```

Why protocol, not ABC?
- Scrapers auto-discover with duck typing
- No base class boilerplate
- Plugin loading is one loop: find `.py` files in `scrapers/plugins/`, import them, extract classes matching the protocol

### Pattern: Repository for Plugin Access

Don't import plugins directly. Use the repository:

```python
from services.repository import get_scrapers

for scraper in get_scrapers():
    results.extend(scraper.search(query))
```

Why? Scrapers are loaded dynamically. The repository tracks which ones exist, which ones are enabled.

### Pattern: Multi-Source Title Normalization

The repository automatically deduplicates anime results from multiple sources using intelligent title normalization. This means:

**Same anime, different title formats are merged:**
```
AnimesDigital: "Anime A: Revolucao Dublado"
AnimeOnlineCC: "Anime A - Revolucao Dublado"
AnimeFireTV:   "Anime A | Revolucao Dublado"

Result: Single entry "anime a revolucao dublado [animesdigital, animesonlinecc, animefiretv]"
```

**How it works:**
- `normalize_title_for_dedup()` strips away separators (`:`, `-`, `|`, `/`), language markers (`Dublado`, `Legendado`), and season indicators
- When `add_anime()` is called, new titles are matched against existing normalized titles
- If normalized forms match, the source is appended to the existing entry
- If no match, a new entry is created

**Examples of merged titles:**
```
"Jujutsu Kaisen Season 2 Dublado" + "Jujutsu Kaisen 2nd Season"
→ "jujutsu kaisen 2 [both sources]"

"Hell's Paradise: Jigokuraku" + "Hell's Paradise - Jigokuraku"
→ "hell s paradise jigokuraku [both sources]"
```

Why? Reduces cognitive load during search. Users see one entry per anime with all available sources, not 3-4 duplicate entries with slight title variations.

### Pattern: Caching as a Wrapper

Services decide *when* to cache, not the scraper:

```python
if cache_hit := self.cache.get(key):
    return cache_hit

results = scraper.search(query)
self.cache.set(key, results, ttl=settings.cache_duration_hours)
```

Scrapers stay simple. Services control cache strategy. Cache invalidation is centralized.

### Pattern: External Tools via Adapters

MPV, PDF readers, MangaDex API—all external. Wrap them:

```python
class VideoPlayer:
    def play(self, url: str, episode_number: int) -> None:
        # IPC to MPV

class MangaReader:
    def open(self, pdf_path: str) -> None:
        # Detect installed readers, execute in priority order
```

Why? Replacing MPV = swap one class. Testing doesn't require external tools (mock them).

---

## Data Structures

All data validated with Pydantic (`models/models.py`):

```python
class AnimeMetadata(BaseModel):
    title: str
    url: str
    cover: str | None = None

class EpisodeData(BaseModel):
    number: int
    title: str
    video_url: str
    aired: date | None = None
```

Why Pydantic? Validation on entry (fail fast if scraper returns garbage), type hints everywhere, serialization to JSON for cache/history.

---

## How to Extend

### Add a New Scraper

1. Create `scrapers/plugins/newsource.py`:
```python
class NewSourceScraper:
    def search(self, query: str) -> list[AnimeMetadata]:
        # Call API, parse HTML, return metadata
        pass

    def get_episodes(self, url: str) -> list[EpisodeData]:
        # Parse page, extract video URLs
        pass
```

2. Auto-discovered by `scrapers/loader.py` on boot. No registration needed.

3. Test: `uv run pytest tests/` includes plugin discovery checks.

### Add a New Service

Most feature work belongs here. Example: adding "trending anime" feature:

1. Create `services/trending_service.py`:
```python
class TrendingService:
    def __init__(self, scrapers: list[Scraper], cache: Cache, api_client: APIClient):
        self.scrapers = scrapers
        self.cache = cache
        self.api = api_client

    def get_trending(self, language: str) -> list[AnimeMetadata]:
        # Hit API or scrape, cache result, return
        pass
```

2. In the command layer (`commands/anime.py`), instantiate and use:
```python
service = TrendingService(get_scrapers(), cache, api_client)
trending = service.get_trending("pt-br")
```

Services own the business logic. Commands own the CLI flow.

### Add a New Command

1. Create `commands/newcommand.py`:
```python
def handle_new_command(args):
    service = SomeService()
    result = service.do_something()
    render_menu(result)
```

2. Wire it in `main.py` argument parser, route to the function.
---

**Testing**:
```bash
uv run pytest tests/test_anilist_authentication.py -v
```

---

## Development Workflow


**Quality**:
```bash
uv run ruff check .                      # Lint
uv run ruff format .                     # Format
uv run pytest                            # Test
uv run pytest -v --cov=. --cov-report=html  # Coverage
```

**Manage**:
```bash
uv add package-name                      # Add dependency
uv remove package-name                   # Remove dependency
uv sync --upgrade                        # Update all
```

**How to Use**:

Just write conventional commits and push to branch:

```bash
# Feature release (bumps minor: 0.2.2 → 0.3.0)
git commit -m "feat: add new capability"

# Patch release (bumps patch: 0.2.2 → 0.2.3)
git commit -m "fix: resolve issue"

# Major release (bumps major: 0.2.2 → 1.0.0)
git commit -m "feat: breaking change

BREAKING CHANGE: description of breaking change"

git push
# → CI runs → Release workflow triggers → v0.3.0 published!
```

**Never use `git commit --no-verify`.**
- Commits must pass local hooks before they are created
- If a hook fails, fix the root cause and rerun the commit
- If hooks conflict with unrelated local changes, isolate the relevant changes properly instead of bypassing verification

**Release Workflow**:
- Triggers automatically after CI passes on main branch
- Calculates next version from commit history since last release
- Creates git tag (e.g., `v0.2.0`) and GitHub Release
- Generates release notes from commit messages
- Updates CHANGELOG.md

**⚠️ Always `git pull --rebase` before pushing after a `feat:` or `fix:` commit.**
The release bot commits the version bump and CHANGELOG directly to remote, so the local branch will be behind. This is expected — just rebase and push.

**Configuration**:
- Release rules: `[tool.semantic_release]` in `pyproject.toml` (what triggers bumps)
- Workflow: `.github/workflows/release.yml` (GitHub Actions)
- Tool: `python-semantic-release` (not Node.js `semantic-release`)
- Always use conventional commits to get the correct version bump

**Troubleshooting Release Failures**:
- **Release workflow didn't trigger**: Check that CI workflow name is exactly "CI" (matches `workflow_run` trigger)
- **Version not bumped**: Ensure commits use correct conventional format (`feat:`, `fix:`, etc.)
- **Push permission error**: Ensure `GITHUB_TOKEN` has `contents: write` permission in workflow
- **"no release will be made"**: Normal for feature branches; release only happens on `master`/`main`
- **Version mismatch**: If `pyproject.toml` version diverges from latest git tag, manually update to match (`git tag -l | sort -V | tail -1`)

---


## Testing Strategy

**Principle: NO MOCKING BY DEFAULT. Use real implementations. Only mock external tools, APIs, and destructive operations.**

### The Rule
- **Start with real code**: Every test should exercise actual functions and services
- **Only mock externals**: HTTP calls, database connections, external APIs (AniList)
- **Use temp directories instead of mocking**: Never mock file operations—use `temp_dir` fixture
- **Never mock internal services**: If you're mocking a service layer or plugin, you're not testing integration

### Test Approach
- **Integration tests** with real services, plugins, and storage (NEVER mock these)
- **Mock external APIs only**: AniList GraphQL, external video providers, HTTP requests
- **Mock destructive operations**: Never delete real files—use temporary directories with auto-cleanup
- **Real plugin loading**: Load actual scrapers from `scrapers/plugins/` directory
- **Real storage**: Use temporary directories for cache/downloads (auto-cleanup via pytest fixtures)


### Refactoring Pattern
Old (excessive mocks):
```python
# Mock both scraper AND repository = no real integration testing
with patch.object(scraper, 'search') as mock_search:
    mock_search.return_value = [...]
    result = repository.search_anime("query")
```

New (real integration):
```python
# Use real repository with real scrapers, mock only external API
with patch.object(httpx.Client, "get") as mock_http:  # External API mock only
    mock_http.return_value = Mock(status_code=200, json=lambda: {...})
    result = repository.search_anime("query")  # Real scrapers, real business logic
```

Goal: 80%+ coverage on service layer (business logic). CLI layer and utilities need less coverage (tested manually).

### Running Tests with Subagents

When running the full test suite (`uv run pytest`), use a **test-runner** subagent to avoid filling the main context window with large output:

```bash
# Instead of: uv run pytest -v
# Use the subagent system to run tests and report failures
```

The subagent will:
1. Execute `uv run pytest -v` in isolation
2. Parse test results and identify failures
3. Report failures with:
   - File paths and line numbers
   - Error messages and stack traces
   - Suggested fixes or patterns
4. Return a concise summary (not the raw 88KB output)

This keeps the conversation focused and prevents context bloat while maintaining full access to test diagnostics.

---

## Notes for Contributors

1. **Always use `uv`**.
2. **Config in `models/config.py`**—not scattered imports.
3. **Business logic in services**—not commands or UI.
4. **Don't import plugins directly**—use the repository.
5. **Immutable data**—return new objects, never mutate input.
6. **Avoid circular imports**: commands → services → models/utils.
7. **Persist data** in `~/.local/state/ani-tupi/` (XDG standard).
8. **No hardcoded values**—use config or Pydantic models.

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```


### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```


### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk diff                # Ultra-compact diffs
```


### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

<!-- /rtk-instructions -->
