# CLAUDE.md

Guidance for developing ani-tupi: a Brazilian Portuguese CLI for anime and manga with multi-source support, AniList integration, and external player support.

## Core Values

**Simplicity First**: Every feature should feel effortless to the user. Complex logic (incremental search, fuzzy matching, automatic syncing) runs invisibly.

**DRY Architecture**: Code is organized by *what it does*, not *where it lives*. If multiple scrapers implement `search()` → they're one pattern (plugin protocol). If multiple services fetch from APIs → they share a base class. If code repeats → extract it.

**Immutable Data Flow**: Data flows forward only. Services don't modify input; they return transformed copies. This makes debugging trivial: follow the data, not the mutations.

**Plugin Everything**: Scrapers, PDF readers, storage backends—all pluggable. New source? Create one file. Done.

**User Configuration Over Code**: Settings live in environment variables (via Pydantic config), not config files that break. Users can tune everything without touching code.

## Architecture Principles

### Pattern: Service Layer as Coordinator

The system has three tiers:

1. **Commands** (CLI entry points) - Parse user intent
2. **Services** (business logic) - Coordinate plugins, cache, APIs, and persistence
3. **Plugins** (implementations) - Scrapers, readers, storage backends

Services orchestrate. They decide: "Should I search cache first?" "Should I sync to AniList?" "Which plugin should I use?"

Commands ask services questions. Services ask plugins for data. Plugins never ask anything—they're pure adapters.

**Extension**: Add a new feature? Build a service. Add a new data source? Build a plugin. Add a new command? Wire up a service call.

### Pattern: Centralized Configuration

All settings flow through one place: `models/config.py` (Pydantic v2).

```python
# In any file:
from models.config import settings
cache_ttl = settings.cache_duration_hours
reader = settings.manga.pdf_reader
```

Why? Centralization means:
- Environment variables override defaults (`ANI_TUPI__CACHE__DURATION_HOURS=48`)
- No scattered `.env` files or hardcoded values
- Type validation on boot (fail fast)
- Configuration is self-documenting

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

This is why adding a scraper requires only: create one file, implement two methods, done.

### Pattern: Repository for Plugin Access

Need to call scrapers? Don't import them directly. Use the repository:

```python
# services/anime_service.py
from services.repository import get_scrapers

for scraper in get_scrapers():
    results.extend(scraper.search(query))
```

Why? Because scrapers are loaded dynamically. The repository tracks which ones exist, which ones are enabled. You don't hardcode plugin names anywhere.

### Pattern: Caching as a Wrapper

Scraper results are cached consistently across the system, but the service layer decides *when* to cache, not the scraper.

```python
# services/anime_service.py
if cache_hit := self.cache.get(key):
    return cache_hit

results = scraper.search(query)
self.cache.set(key, results, ttl=settings.cache_duration_hours)
```

Why? Because:
- Scrapers stay simple (no caching logic)
- Services control cache strategy (e.g., "don't cache on retry")
- Cache invalidation is centralized

### Pattern: External Tools via Adapters

MPV, PDF readers, MangaDex API—all external. Wrap them:

```python
# utils/video_player.py
class VideoPlayer:
    def play(self, url: str, episode_number: int) -> None:
        # IPC to MPV, or import subprocess

# utils/manga_reader.py
class MangaReader:
    def open(self, pdf_path: str) -> None:
        # Detect installed readers, execute in priority order
```

Why? Because:
- Replacing MPV with another player = swap one class
- Testing doesn't require external tools (mock them)
- You can detect/configure readers per-system

### Pattern: Shared Arguments → Shared Class

Multiple functions with identical parameters? Make them methods:

```python
# Bad:
def search_animefire(query): ...
def search_animesonline(query): ...

# Good:
class AnimeFireScraper:
    def search(self, query): ...
class AnimesonlineScraper:
    def search(self, query): ...
```

The system uses this everywhere:
- `AniListService` → all AniList methods share `token`, `rate_limit`, `client`
- `MangaService` → all manga methods share `cache`, `downloader`, `pdf_converter`
- Scrapers → search and episode extraction both need the scraper session

## How Data Flows

### Anime Watching
1. **CLI** → user types `uv run ani-tupi --query "dandadan"`
2. **Command** → parses args, calls `AnimeService.search(query)`
3. **Service** → checks cache; if miss, loops through enabled scrapers
4. **Scraper** → calls MangaDex/AnimeFire/etc API, returns `AnimeMetadata`
5. **Service** → performs *incremental search* (local algorithm: add words until ≤5 results)
6. **UI** → shows menu; user picks anime
7. **Service** → fetches episodes from chosen scraper, checks history, caches episodes
8. **UI** → shows episode menu; user picks episode
9. **Service** → launches `VideoPlayer.play(url)`, which execs MPV with IPC socket
10. **After playback** → service updates history, asks "Sync to AniList?", sends GraphQL mutation if yes

### Manga Reading
Same steps, but:
- Step 3: Call `MangaService.search()` instead, which hits MangaDex API
- Step 7: Instead of episodes, fetch chapters
- Step 9: `MangaReader.open(pdf)` instead of VideoPlayer; reader auto-detects (Zathura → Evince → xdg-open)
- Step 10: `MangaService.convert_to_pdf()` if needed (downloads images, Pillow conversion), saves progress

The pattern is identical. Services handle orchestration. Plugins handle source-specific work.

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

## Configuration

All settings are environment variables. Use Pydantic as the source of truth:

```bash
# All equivalent:
ANI_TUPI__CACHE__DURATION_HOURS=48
ANI_TUPI__MANGA__PDF_READER=zathura
ANI_TUPI__LOG_LEVEL=debug
```

No config files. Centralized in `models/config.py`. Type-safe on boot.

## Development Workflow

**Setup**
```bash
uv sync
```

**Run**
```bash
uv run ani-tupi                          # Anime CLI
uv run manga_tupi                        # Manga CLI
uv run main.py --debug                   # Enable debug logging
```

**Quality**
```bash
uv run ruff check .                      # Lint
uv run ruff format .                     # Format
uv run pytest                            # Test
```

**Manage**
```bash
uv add package-name                      # Add dependency
uv remove package-name                   # Remove dependency
uv sync --upgrade                        # Update all
```

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

Most work belongs here. Example: adding "trending anime" feature:

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

## Anime Download Feature

### Overview

Download episodes for offline viewing. Episodes are stored locally in `~/.local/share/ani-tupi/anime/` and organized by anime title.

### How to Download Episodes

1. **In Playback**: While watching an episode, press the menu and select "📥 Baixar para assistir depois"
2. **Range Selection**: Enter an episode range:
   - `5`: Download episode 5
   - `1-12`: Download episodes 1 through 12
   - `5-`: Download from episode 5 to the end
   - `-12`: Download episodes 1 through 12
   - `5-15`: Download episodes 5 through 15

3. Episodes download in parallel (respects `max_parallel_downloads` config, default: 2)
4. Already-downloaded episodes are skipped automatically

### How to Access Local Library

1. From main menu, select "📂 Biblioteca Local"
2. Choose an anime from the list
3. Select an episode to play
4. Playback uses the same VideoPlayer as streaming

### How to Configure Downloads

Set environment variables to customize behavior:

```bash
# Maximum parallel downloads (1-16)
export ANI_TUPI__ANIME__MAX_PARALLEL_DOWNLOADS=4

# Download directory (default: ~/.local/share/ani-tupi/anime)
export ANI_TUPI__ANIME__DOWNLOAD_DIRECTORY="~/Videos/Anime"

# Video format (mkv, mp4, etc)
export ANI_TUPI__ANIME__VIDEO_FORMAT="mp4"
```

### Architecture

**Services**:
- `AnimeDownloadService`: Orchestrates downloads with parallel queue and retry logic
- `LocalAnimeService`: Scans and manages local library, discovers episodes

**Data**:
- Episodes stored in: `~/.local/share/ani-tupi/anime/{anime_title}/{episode_number}.mkv`
- Metadata stored in: `~/.local/state/ani-tupi/anime_downloads.json`
- Format: Pydantic models (serialized to JSON for persistence)

**Commands**:
- Download prompt in playback menu (`commands/anime.py`)
- Local library browser in main menu (`main.py`)

### Implementation Details

- **Episode Range Parser**: Flexible input parsing with validation (`utils/episode_range_parser.py`)
- **Download Models**: Pydantic models for type-safe download operations (`models/models.py`)
- **Parallel Downloads**: ThreadPoolExecutor with ordered execution (ep 1 before ep 2)
- **File Validation**: Skip files < 1MB (indicates HTML error pages)
- **Retry Logic**: Exponential backoff (2s, 4s, 8s) for failed downloads
- **Skip Logic**: If episode exists in database and skip_already_downloaded=True, download is skipped

## Known Issues & Solutions

### Issue: Scraper Results Not Cached

**Root Cause**: Service not calling `cache.set()` after fetch.

**Solution**: Check `services/anime_service.py` line where results are returned. If cache miss, add:
```python
self.cache.set(cache_key, results, ttl=settings.cache_duration_hours)
```

### Issue: New PDF Reader Not Detected

**Root Cause**: `utils/manga_reader.py` detection loop doesn't check for your reader.

**Solution**: Add executable name to priority list:
```python
PRIORITY = ["zathura", "evince", "your-reader-name", "xdg-open"]
```

### Issue: AniList Sync Fails

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

### Issue: AnimesonlineCC Videos Fail

**Root Cause**: Videos use temporary Blogger URLs with short expiry.

**Solution**: Use AnimesDigital or AnimeFire as primary sources:
```bash
export ANI_TUPI__PLUGINS__PRIORITY_ORDER='["animesdigital", "animefire"]'
```

### Issue: Incremental Search Gives Wrong Results

**Root Cause**: Two separate search iterations are being treated as one (words not split correctly).

**Solution**: Check `services/anime_service.py` incremental search algorithm:
- Split query by space
- Start with first 3 words
- Add one word per iteration
- Stop when results ≤ 5 or all words used

## Design Trade-Offs

**Protocol over Inheritance**: Less boilerplate, but requires discipline (protocols aren't enforced at runtime—duck typing catches mistakes late).

**Centralized Config**: Simpler, but environment variables are less discoverable than a config file.

**External Tools as Adapters**: Maximum flexibility, but means testing requires mocks (no integration tests with real MPV).

**DRY Documentation**: This guide repeats no code flows. But it's denser to read. Always refer to actual services for truth.

## Testing Strategy

- **Unit tests** for services (mock scrapers, cache, API clients)
- **Integration tests** for plugin loading (verify scrapers are discoverable)
- **E2E tests** for critical flows (search → select → play/read)

Run: `uv run pytest -v --cov=. --cov-report=html`

Goal: 80%+ coverage on service layer (business logic). CLI layer and utilities need less coverage (tested manually).

## Notes for Contributors

1. **Always use `uv`.
2. **Config in `models/config.py`**—not scattered imports.
3. **Business logic in services**—not commands or UI.
4. **Don't import plugins directly**—use the repository.
5. **Immutable data**—return new objects, never mutate input.
6. **Avoid circular imports**: commands → services → models/utils.
7. **Persist data** in `~/.local/state/ani-tupi/` (XDG standard).
8. **No hardcoded values**—use config or Pydantic models.

## When to Refactor

**Red flag**: Code is repeated in two places → extract a function.

**Red flag**: A function has more than 3 parameters → create a type (dataclass, Pydantic model, or class) to hold them.

**Red flag**: Two functions have identical parameters and both modify state → make them methods of a class.

**Red flag**: A service has 3+ dependencies → consider dependency injection pattern.

**Red flag**: A plugin doesn't implement the protocol → it's probably a command or service, not a plugin.
