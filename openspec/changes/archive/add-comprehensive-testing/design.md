# Design: Comprehensive Testing Framework

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Test Suite Structure              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  tests/                                             │
│  ├── conftest.py          ← Shared fixtures        │
│  ├── fixtures/            ← Mock data              │
│  │   ├── anime_data.json                           │
│  │   ├── episode_data.json                         │
│  │   └── anilist_responses.json                    │
│  ├── test_models.py       ← Unit tests             │
│  ├── test_config.py                                │
│  ├── test_repository.py                            │
│  ├── test_history_service.py                       │
│  ├── test_plugin_loader.py ← Integration tests     │
│  ├── test_repository_integration.py                │
│  ├── test_anilist_service.py                       │
│  ├── test_e2e_search.py    ← E2E tests             │
│  ├── test_e2e_video_extraction.py                  │
│  ├── test_e2e_anilist.py                           │
│  └── README.md            ← Testing guide          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Test Categories & Rationale

### Layer 1: Unit Tests (Fast, Isolated)

**Goal:** Test individual modules in isolation with mocked dependencies.

**Modules Tested:**
- `repository.py` - Core business logic (title matching, deduplication)
- `models.py` - Data validation
- `config.py` - Configuration loading
- `history_service.py` - Persistence logic

**Key Design Decisions:**
1. **No external dependencies** - All tests use in-memory data structures
2. **Parametrized tests** - Multiple scenarios in single test function using `@pytest.mark.parametrize`
3. **Fixtures for common data** - Reusable test anime, episodes, configs
4. **Fast execution** - All unit tests complete in <1 second

**Example:**
```python
@pytest.mark.parametrize("title,expected", [
    ("Dandadan 2nd Season; Episode 3", "dan da dan S02E03"),
    ("Attack on Titan (Part 1)", "attack on titan"),
])
def test_title_normalization(title, expected):
    assert normalize_title(title) == expected
```

### Layer 2: Integration Tests (Component Interactions)

**Goal:** Test how modules interact with each other and external systems (mocked).

**Modules Tested:**
- `loader.py` + plugins - Plugin discovery and registration
- `repository.py` + mock plugins - Search orchestration
- `anilist_service.py` - API client with mocked HTTP

**Key Design Decisions:**
1. **Mock plugins** - Create fake plugin classes for testing without real Selenium/scraping
2. **Mocked HTTP** - Use `unittest.mock.patch` to mock requests/httpx responses
3. **Fixture-based test data** - Shared mock data that multiple tests use
4. **State isolation** - Each test gets a fresh Repository instance

**Example:**
```python
def test_search_anime_parallel_execution(mock_plugins_fixture):
    # Multiple plugins execute in parallel
    # First to find result wins
    # Others are cancelled
    rep.search_anime("dandadan")
    assert len(rep.anime_to_urls["Dandadan"]) > 0
```

### Layer 3: End-to-End Tests (Complete Workflows)

**Goal:** Test full user workflows from start to finish with realistic data.

**Workflows Tested:**
1. Search → Select Anime → Load Episodes → Select Episode
2. Extract Video URL (with fallback handling)
3. Search → Watch Episode → Update AniList Progress

**Key Design Decisions:**
1. **Minimal mocking** - Only mock external services (HTTP, file I/O)
2. **Realistic data flow** - Use actual functions, not mocked versions
3. **Test data that mimics reality** - Anime names, episode counts match real sites
4. **Clear assertions** - Validate final state matches expected user outcome

**Example:**
```python
def test_search_watch_save_workflow():
    # 1. User searches for "Dandadan"
    rep.search_anime("dandadan")
    anime_list = rep.get_anime_list()

    # 2. Selects "Dandadan" from results
    rep.set_selected_anime("Dandadan")

    # 3. Loads episodes
    rep.search_episodes("Dandadan", "https://...", None)
    episodes = rep.get_episodes("Dandadan")

    # 4. Selects episode 1
    # 5. Saves to history
    save_history("Dandadan", 0)

    # 6. Resume watching works
    last_anime, last_ep = load_history()
    assert last_anime == "Dandadan"
    assert last_ep == 0
```

## Fixture Strategy

### Shared Fixtures (conftest.py)

Create reusable fixtures that multiple tests use:

```python
@pytest.fixture
def sample_anime():
    """Realistic anime data for testing."""
    return AnimeMetadata(
        title="Dandadan",
        url="https://animefire.plus/animes/dandadan",
        source="animefire"
    )

@pytest.fixture
def sample_episodes():
    """Realistic episode list."""
    return EpisodeData(
        anime_title="Dandadan",
        episode_titles=["Ep. 1", "Ep. 2", ...],
        episode_urls=["url1", "url2", ...],
        source="animefire"
    )

@pytest.fixture
def repo_clean(monkeypatch):
    """Fresh Repository instance for each test."""
    # Create new instance
    repo = Repository()
    repo.clear_search_results()
    yield repo
    # Cleanup
    repo.clear_search_results()
```

### Test Data Files (fixtures/ directory)

Store realistic test data in JSON files:

**fixtures/anime_data.json:**
```json
{
  "animes": [
    {
      "title": "Dandadan",
      "url": "https://animefire.plus/animes/dandadan",
      "source": "animefire"
    },
    ...
  ]
}
```

**Rationale:**
- Separate test data from test logic
- Reusable across multiple tests
- Easy to update if sites change
- Realistic data reduces false negatives

## Mocking Strategy

### HTTP Mocking (for AniList, scrapers)

Use `unittest.mock.patch` to mock HTTP responses:

```python
@patch('requests.post')
def test_anilist_update_progress(mock_post):
    # Mock successful response
    mock_post.return_value.json.return_value = {"data": {...}}

    # Test code calls requests.post
    client.update_progress(anime_id=1, episode=5)

    # Verify it was called correctly
    mock_post.assert_called_once()
```

### Plugin Mocking (for integration tests)

Create mock plugin classes that don't require Selenium:

```python
class MockAnimeFirePlugin(PluginInterface):
    name = "mock_animefire"

    @staticmethod
    def search_anime(query: str) -> None:
        # Return hardcoded test data instead of scraping
        rep.add_anime("Dandadan", "https://test.url", "mock_animefire")

    # ... other methods
```

**Benefits:**
- No Selenium required for plugin tests
- Deterministic results (no site changes)
- Fast execution
- Isolated plugin logic testing

### File I/O Mocking

Use pytest's `tmp_path` fixture for temporary files:

```python
def test_history_save_load(tmp_path):
    history_file = tmp_path / "history.json"

    # Test save
    save_history("Dandadan", 5, str(history_file))

    # Test load
    title, episode = load_history(str(history_file))
    assert title == "Dandadan"
    assert episode == 5
```

**Benefits:**
- No cleanup needed (temporary dirs auto-deleted)
- Isolated tests (one test's file doesn't affect another)
- Works on all platforms

## Coverage Strategy

### Target Coverage by Module

| Module | Target | Rationale |
|--------|--------|-----------|
| `repository.py` | 80% | Core business logic, must be reliable |
| `models.py` | 75% | Data validation critical |
| `config.py` | 70% | Configuration loading, path handling |
| `history_service.py` | 80% | Persistence, data integrity |
| `core/anilist_service.py` | 70% | API client, integration point |
| `loader.py` | 65% | Plugin loading, less critical |
| `main.py` | 40% | UI/controller, harder to test |
| **Overall** | **60%** | Reasonable baseline for CLI project |

### Coverage Measurement

Use pytest-cov to generate reports:

```bash
# Generate terminal report
pytest --cov=. --cov-report=term-missing

# Generate HTML report
pytest --cov=. --cov-report=html

# Check specific module
pytest --cov=repository --cov-report=term-missing
```

## CI/CD Integration

### GitHub Actions Workflow (test.yml)

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: "3.12"
      - run: pip install uv
      - run: uv sync
      - run: pytest -v --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
```

### Test Execution Strategy

- **Unit tests:** Always run (no external dependencies)
- **Integration tests:** Always run (mocked external services)
- **E2E tests:** Always run (mocked plugins and APIs)
- **Coverage:** Required to pass CI
- **Parallel execution:** Use `-n auto` flag for speed

## Test Isolation & State Management

### Repository Singleton Management

Problem: `Repository` is a singleton; tests must not interfere with each other.

**Solution:**

```python
@pytest.fixture(autouse=True)
def reset_repository():
    """Auto-reset Repository before each test."""
    repo = Repository()
    repo.clear_search_results()
    yield
    repo.clear_search_results()
```

### Plugin Registration Management

Problem: Plugins register globally; tests share state.

**Solution:**

```python
@pytest.fixture
def clean_plugin_registry():
    """Provide clean plugin registry for test."""
    repo = Repository()
    # Save original sources
    original_sources = repo.sources.copy()
    yield repo
    # Restore original
    repo.sources = original_sources
```

## Test Naming Conventions

### Test Function Names

```
test_[module]_[scenario]_[expected_outcome]
test_repository_search_anime_returns_matches
test_plugin_loader_discovers_plugins_in_directory
test_anilist_service_update_progress_sends_correct_mutation
```

### Test Class Names (for organization)

```python
class TestRepositoryTitleNormalization:
    def test_removes_accents(self): ...
    def test_handles_special_characters(self): ...

class TestAnimeDeduplication:
    def test_merges_duplicate_sources(self): ...
    def test_preserves_all_sources(self): ...
```

## Test Documentation

Each test module should include:

```python
"""
Tests for module_name.py

Coverage:
- Title normalization (empty string, special chars, unicode)
- Fuzzy matching (95% threshold validation)
- Plugin registration (duplicate names, missing interface)

See tests/README.md for running and adding tests.
"""
```

## Debugging Failed Tests

### Local Debugging

```bash
# Run single test with output
pytest tests/test_repository.py::test_fuzzy_matching -v -s

# Run with pdb debugger
pytest tests/test_repository.py -v --pdb

# Run with print statements visible
pytest tests/test_repository.py -v -s
```

### CI Debugging

GitHub Actions will:
1. Show pytest output in PR checks
2. Fail the test step if any tests fail
3. Prevent merge until all tests pass

## Performance Considerations

### Test Execution Time

Target: <5 seconds for full suite

**Breakdown:**
- Unit tests: ~1 second
- Integration tests: ~2 seconds
- E2E tests: ~2 seconds

**Optimization:**
- Use `pytest -n auto` for parallel execution
- Avoid sleep() calls in tests
- Mock slow operations (file I/O, HTTP)

### Caching During Tests

- History file writes use `tmp_path` (no persistent cache)
- Plugin cache disabled during tests (use fresh instances)
- No real HTTP calls (all mocked)

## Future Enhancements (Out of Scope)

1. **Performance benchmarks** - Track execution time of critical paths
2. **Selenium-based plugin tests** - Real browser testing (slow, brittle)
3. **Visual regression tests** - TUI layout validation
4. **Load testing** - Handle 1000+ anime in cache
5. **Property-based testing** - Generative testing with hypothesis

These can be added in future changes once testing foundation is solid.
