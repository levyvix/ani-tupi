# CLAUDE.md

Guidance for developing ani-tupi: a Brazilian Portuguese CLI for anime and manga with multi-source support, AniList integration, and external player support.

---

## Workflow Orchestration

**Everything starts with execution discipline.** These principles prevent mistakes, reduce rework, and ensure high-quality contributions.

### Git Worktrees
- Use worktrees for parallel development on independent features
- Each worktree has its own branch, isolated from main working directory
- Clean up worktrees when done to keep repository tidy
- Create worktree on feature branch: isolates changes from main working directory
- Test and iterate before pushing to avoid conflicts
- Useful for testing CI/CD or working on multiple features simultaneously

### 1. Plan Mode Default

- **Enter plan mode for ANY non-trivial task** (3+ steps or architectural decisions)
- Plan mode ensures alignment before implementation starts
- Use plan mode for exploration and design verification
- If something goes sideways, **STOP and re-plan immediately** — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop

- After ANY correction from the user, update `<spec-path>/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing what I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

### 7. Specification Discipline

Ask these four clarifying questions before ANY implementation:

1. **"What happens when it fails?"** — Define edge cases, error modes, and failure paths
2. **"How do we know it's working?"** — Establish concrete acceptance criteria and verification methods
3. **"What does 'done' look like?"** — Define exact completion criteria, not fuzzy statements
4. **"Can you show me an example?"** — Ground discussions in concrete instances, not abstractions

**Apply these principles:**
- Use precise terminology over vague language (NOT "priority: high", YES "priority_level: 1"; NOT "timeout: short", YES "timeout_seconds: 30")
- Require exact numbers/enums in specs, not relative language
- Document edge cases explicitly (what breaks? what's unsupported?)
- Design error paths before happy paths—assume failures will occur
- For mission-critical specs affecting multiple components: state requirements at least twice using formal language, include concrete examples

**Why?** Most failures happen because someone was afraid to ask an obvious question. Clarifying questions prevent half-understood requirements that waste effort later.

### Core Execution Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards. Design defensive architecture: error paths before happy paths, explicit edge case handling.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

---

## Core Values

**Simplicity First**: Every feature should feel effortless to the user. Complex logic (incremental search, fuzzy matching, automatic syncing) runs invisibly.

**DRY Architecture**: Code is organized by *what it does*, not *where it lives*. If multiple scrapers implement `search()` → they're one pattern (plugin protocol). If multiple services fetch from APIs → they share a base class. If code repeats → extract it.

**Immutable Data Flow**: Data flows forward only. Services don't modify input; they return transformed copies. This makes debugging trivial: follow the data, not the mutations.

**Plugin Everything**: Scrapers, PDF readers, storage backends—all pluggable. New source? Create one file. Done.

**User Configuration Over Code**: Settings live in environment variables (via Pydantic config), not config files that break. Users can tune everything without touching code.

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

## Configuration

All settings are environment variables. Use Pydantic as the source of truth:

```bash
ANI_TUPI__CACHE__DURATION_HOURS=48
ANI_TUPI__MANGA__PDF_READER=zathura
ANI_TUPI__LOG_LEVEL=debug
```

### Source Priority Configuration

**Standard Priority** (used for all anime):
```bash
export ANI_TUPI__PLUGINS__PRIORITY_ORDER='["animesdigital", "goyabu", "animefire", "animesonlinecc"]'
```

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

### Modify AniList Integration

AniList touches three places (because AniList is stateful—token, rate limits, cached queries):

1. **API client**: `services/anilist_service.py`
   - All GraphQL queries/mutations live here
   - Handles rate limiting, token refresh

2. **Discovery** (title mapping): `utils/anilist_discovery.py`
   - Fuzzy-matches scraper titles to AniList IDs
   - Caches winning matches in JSON

3. **Commands**: `commands/anilist.py`
   - User-facing flow: auth, list browsing, sync triggers

To add a feature: modify 1 (add the API method), then 2–3 if title mapping is needed.

---

## Features

### Anime Download

Download episodes for offline viewing. Episodes stored in `~/.local/share/ani-tupi/anime/` organized by title.

**How to Download**:
1. While watching, select "📥 Baixar para assistir depois"
2. Enter episode range: `5`, `1-12`, `5-`, `-12`, or `5-15`
3. Episodes download in parallel (respects `max_parallel_downloads` config, default: 2)
4. Already-downloaded episodes are skipped automatically

**Configuration**:
```bash
export ANI_TUPI__ANIME__MAX_PARALLEL_DOWNLOADS=4
export ANI_TUPI__ANIME__DOWNLOAD_DIRECTORY="~/Videos/Anime"
export ANI_TUPI__ANIME__VIDEO_FORMAT="mp4"
```

**Architecture**:
- `AnimeDownloadService`: Orchestrates downloads with parallel queue and retry logic
- `LocalAnimeService`: Scans and manages local library
- Episodes stored in: `~/.local/share/ani-tupi/anime/{anime_title}/{episode_number}.mkv`
- Metadata stored in: `~/.local/state/ani-tupi/anime_downloads.json`

### Airing Episodes

The "🎬 Novos Episódios" tab displays anime from your AniList watching list that have new episodes currently airing.

**How to Access**:
1. Open the AniList menu: `uv run ani-tupi`
2. Select "🎬 Novos Episódios" (appears at top of authenticated menu)
3. Browse anime sorted by urgency (most episodes behind first)
4. Select an anime to start playback

**Display Format**:
```
Jujutsu Kaisen - Ep 25 aired, você viu 22 (3 atrasado) ⭐82%
Dandadan - Ep 18 aired, você viu 15 (3 atrasado) ⭐79%
Blue Lock - Ep 11 aired, você viu 11 (0 atrasado) ⭐75%
```

**Architecture**:
- `services/anime/airing_episodes_service.py`: Business logic (filtering, sorting, gap calculation)
- `services/anilist/anime_operations.py`: GraphQL query `get_airing_episodes_for_watching()`
- `models/models.py`: `AiringAnimeEntry` Pydantic model for display data

**Testing**:
```bash
uv run pytest tests/test_airing_episodes_service.py tests/test_anilist_airing_query.py -v
```

### AniList Authentication (Headless Mode)

Authentication works in all environments—local terminal, SSH session, container, or CI/CD pipeline. No browser required.

**How It Works**:
1. User runs `uv run ani-tupi` and selects AniList menu
2. System displays authorization URL and prompts for token
3. User visits URL in any browser (on same device or different machine)
4. User authorizes the application
5. User copies token from redirect URL and pastes into terminal
6. Token is validated and stored locally

**Authentication Flow**:
```
$ uv run ani-tupi
[Select "Autenticar com AniList"]

================================================
🔐 AniList Authentication Required
================================================

1. Visit this URL in your browser:

   https://anilist.co/api/v2/oauth/authorize?client_id=...&response_type=token

2. Authorize the application
3. Copy the access token from the URL (or from the page)
4. Paste it below when prompted

Paste token here: ••••••••••••••••••••
✅ Authentication successful! Welcome, YourName!
```

**Token Input**:
- Token input is masked with `●●●●` characters for security (uses Python's `getpass`)
- Supports raw tokens or full URLs with token fragment
- Validates token by making test GraphQL query to AniList
- Auto-retries up to 3 times on invalid token

**Troubleshooting Auth Failures**:
- **"Token validation failed"**: Token is expired, revoked, or malformed. Get a fresh token from the auth URL.
- **"Invalid token format"**: User may have copied partial token. Try copying the full URL from browser address bar.
- **Network error during validation**: Check internet connection and retry. Auth succeeds only if token validates with AniList API.
- **Token in SSH session**: Works the same—open auth URL on local computer, copy token, paste in SSH terminal.

**Architecture**:
- `services/anilist/client.py`: `authenticate()` method handles headless flow
- `utils/headless_detector.py`: `get_token_from_user()` displays URL and prompts for input
- Token stored in: `~/.local/state/ani-tupi/anilist_token.json`
- Token includes: `access_token` and `user_id` (for faster queries)

**Testing**:
```bash
uv run pytest tests/test_anilist_authentication.py -v
```

---

## Development Workflow

**Setup**:
```bash
uv sync
```

**Run**:
```bash
uv run ani-tupi                          # Anime CLI
uv run manga_tupi                        # Manga CLI
uv run main.py --debug                   # Enable debug logging
```

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

**Release and Versioning**:

Versions are automatically bumped based on conventional commit messages using semantic versioning (MAJOR.MINOR.PATCH). The release workflow runs automatically when commits are pushed to main after CI passes.

```bash
# Commits that trigger version bumps:
feat: ...          # Bumps MINOR (0.1.0 → 0.2.0)
fix: ...           # Bumps PATCH (0.1.0 → 0.1.1)
BREAKING CHANGE:   # Bumps MAJOR (0.1.0 → 1.0.0)
```

**How to Use**:

Just write conventional commits and push to main/master:

```bash
# Feature release (bumps minor: 0.2.2 → 0.3.0)
git commit -m "feat: add new capability"

# Patch release (bumps patch: 0.2.2 → 0.2.3)
git commit -m "fix: resolve issue"

# Major release (bumps major: 0.2.2 → 1.0.0)
git commit -m "feat: breaking change

BREAKING CHANGE: description of breaking change"

git push origin master
# → CI runs → Release workflow triggers → v0.3.0 published!
```

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

## Known Issues & Solutions

### Scraper Results Not Cached

**Root Cause**: Service not calling `cache.set()` after fetch.

**Solution**: Check `services/anime_service.py` where results are returned. If cache miss, add:
```python
self.cache.set(cache_key, results, ttl=settings.cache_duration_hours)
```

### New PDF Reader Not Detected

**Root Cause**: `utils/manga_reader.py` detection loop doesn't check for your reader.

**Solution**: Add executable name to priority list:
```python
PRIORITY = ["zathura", "evince", "your-reader-name", "xdg-open"]
```

### AniList Authentication Fails

**Root Causes**:
1. Invalid token—expired, revoked, or malformed
2. Network error during token validation
3. Wrong authorization step—user didn't authorize application

**Solution**:
- Delete stored token: `rm ~/.local/state/ani-tupi/anilist_token.json`
- Re-run `uv run ani-tupi` and select AniList menu
- Follow auth flow again: visit URL, authorize, copy token, paste
- If still failing, check network connection: `curl https://graphql.anilist.co`

### AniList Sync Fails

**Root Causes**:
1. Token expired (valid ~6 months)
2. Network error (retry on next episode)
3. Title mismatch (create mapping manually)

**Debugging**:
```bash
export ANI_TUPI__LOG_LEVEL=debug
uv run ani-tupi --query "anime name"
```

Logs show GraphQL requests/responses.

### AnimesonlineCC Videos Fail

**Root Cause**: Videos use temporary Blogger URLs with short expiry.

**Solution**: Use AnimesDigital or AnimeFire as primary sources:
```bash
export ANI_TUPI__PLUGINS__PRIORITY_ORDER='["animesdigital", "animefire"]'
```

### Incremental Search Gives Wrong Results

**Root Cause**: Words not split correctly or thresholds miscalibrated.

**Solution**: Check `services/anime_service.py` incremental search algorithm:
- Split query by space
- Start with first 3 words
- Add one word per iteration
- Stop when results ≤ 5 or all words used

---

## Design Trade-Offs

**Protocol over Inheritance**: Less boilerplate, but requires discipline (protocols aren't enforced at runtime—duck typing catches mistakes late).

**Centralized Config**: Simpler, but environment variables are less discoverable than a config file.

**External Tools as Adapters**: Maximum flexibility, but means testing requires mocks (no integration tests with real MPV).

**DRY Documentation**: This guide repeats no code flows. But it's denser to read. Always refer to actual services for truth.

---

## Testing Strategy

**Principle: NO MOCKING BY DEFAULT. Use real implementations. Only mock external tools, APIs, and destructive operations.**

### The Rule
- **Start with real code**: Every test should exercise actual functions and services
- **Only mock externals**: HTTP calls, database connections, external APIs (AniList, AniSkip)
- **Use temp directories instead of mocking**: Never mock file operations—use `temp_dir` fixture
- **Never mock internal services**: If you're mocking a service layer or plugin, you're not testing integration

### Test Approach
- **Integration tests** with real services, plugins, and storage (NEVER mock these)
- **Mock external APIs only**: AniList GraphQL, AniSkip, external video providers, HTTP requests
- **Mock destructive operations**: Never delete real files—use temporary directories with auto-cleanup
- **Real plugin loading**: Load actual scrapers from `scrapers/plugins/` directory
- **Real storage**: Use temporary directories for cache/downloads (auto-cleanup via pytest fixtures)

### Available Fixtures (in `tests/conftest.py`)
```python
@pytest.fixture
def repository:
    """Real Repository with plugins loaded from scrapers/plugins/"""
    pass

@pytest.fixture
def temp_dir:
    """Temporary directory auto-cleaned up after test"""
    pass

@pytest.fixture
def test_settings:
    """Real AppSettings using temp directories"""
    pass
```

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

---

## When to Refactor

**Red flag**: Code is repeated in two places → extract a function.

**Red flag**: A function has more than 3 parameters → create a type (dataclass, Pydantic model, or class) to hold them.

**Red flag**: Two functions have identical parameters and both modify state → make them methods of a class.

**Red flag**: A service has 3+ dependencies → consider dependency injection pattern.

**Red flag**: A plugin doesn't implement the protocol → it's probably a command or service, not a plugin.
