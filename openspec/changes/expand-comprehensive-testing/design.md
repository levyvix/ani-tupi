# Design: Comprehensive App Workflow and Integration Tests

## Architectural Overview

```
┌─────────────────────────────────────────────────────────────┐
│ TEST LAYERS (Bottom-up execution)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 4: App Workflow Tests                               │
│  ├─ Main menu navigation                                   │
│  ├─ Search → Episode → Playback flow                       │
│  └─ Error recovery (uses layers 1-3)                       │
│                                                             │
│  Layer 3: Playback & AniList Tests                         │
│  ├─ MPV exit code handling (mocked subprocess)             │
│  ├─ AniList authentication & progress sync (mocked API)    │
│  └─ Fallback and error scenarios                           │
│                                                             │
│  Layer 2: Scraper Search Tests                             │
│  ├─ Title normalization & fuzzy matching                   │
│  ├─ Plugin execution & multi-source deduplication          │
│  └─ Episode list handling across sources                   │
│                                                             │
│  Layer 1: Component Tests (existing)                       │
│  ├─ Repository (title normalization logic)                 │
│  ├─ Models (data validation)                               │
│  └─ Config (settings validation)                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Test Implementation Strategy

### 1. Scraper Search Tests (`test_scraper_search.py`)

**Why start here:**
- Foundation for other E2E tests
- Tests core Repository logic indirectly
- **Uses real scrapers** (animefire.plus, animesonlinecc.to) to catch breaking changes

**Real Scraper Integration Strategy:**
- Tests make actual HTTP requests to real sites
- Use retry logic to handle transient failures
- Mark flaky tests with `@pytest.mark.flaky(reruns=3)` if needed
- Benefit: Catches real breaking changes immediately
- Risk: Tests may fail if sites change; document known issues

**Key Test Patterns:**

```python
# Pattern 1: Title Normalization Edge Cases
def test_normalize_titles_with_accents():
    # "Dãndadãn" → normalize → match "Dandadan"

# Pattern 2: Fuzzy Matching Deduplication
def test_deduplicate_similar_titles_across_sources():
    # Add "Dan Da Dan" (animefire) + "Dandadan" (animesonlinecc)
    # Should recognize as same anime, combine sources

# Pattern 3: Plugin Execution Order
def test_parallel_plugin_search_execution():
    # Multiple plugins execute in parallel
    # Verify all results are collected (not just first)

# Pattern 4: Multi-Source Episode Selection
def test_episode_list_from_multiple_sources():
    # Episodes from animefire + animesonlinecc
    # Should provide both sources, let user choose
```

### 2. MPV Playback Tests (`test_mpv_playback.py`)

**Mocking Strategy:**
- Mock `subprocess.run()` to return specific exit codes
- Mock `play_video()` function with parametrized exit codes
- No actual MPV/video playback required
- **Note:** VLC fallback removed (tested, doesn't work reliably)

**Exit Code Scenarios:**

```python
# Exit Code 0: Normal completion (user watched or quit gracefully)
def test_mpv_exit_code_0_success():
    # Video played, user quit with 'q'
    # Should return to episode menu or continue watching

# Exit Code 2: File couldn't be played
def test_mpv_exit_code_2_error():
    # yt-dlp couldn't extract video
    # Show error: "⚠️  MPV falhou ao reproduzir este vídeo"
    # User offered to retry or select different episode

# Exit Code 1, 3, 4: Various errors
def test_mpv_exit_code_errors_recovery():
    # Handle gracefully, don't crash
    # Return to menu with error message
```

### 3. App Workflow Tests (`test_e2e_app_workflow.py`)

**Dependency Graph:**

```
Main Menu
├─ Search Anime Flow
│  ├─ Scraper search (layer 2)
│  ├─ Episode selection
│  ├─ Episode playback (layer 3)
│  └─ History save
│
├─ Continue Watching
│  ├─ History load
│  └─ Playback flow (layer 3)
│
├─ AniList Flow
│  ├─ Authentication
│  ├─ List browsing
│  └─ Progress sync
│
└─ Plugin Management
   └─ Enable/disable sources
```

**Test Structure:**

```python
class TestSearchToPlaybackFlow:
    """Search → Episode selection → Playback → History save"""

    def test_complete_workflow_dandadan():
        # 1. Search for "Dandadan"
        # 2. Select from results
        # 3. Choose episode 1
        # 4. Play video (mocked MPV)
        # 5. Verify history saved

    def test_workflow_with_no_results():
        # 1. Search for non-existent anime
        # 2. Show error message
        # 3. Return to menu

    def test_workflow_multi_source_fallback():
        # 1. Search finds anime on 2 sources
        # 2. User selects source
        # 3. Episode list loads from that source
        # 4. Playback works
```

### 4. AniList Integration Tests (`test_anilist_integration.py`)

**Mock Layers:**

```python
# Mock AniList GraphQL API responses
mock_anilist_response_trending = {
    "data": {
        "Page": {
            "media": [
                {"id": 1, "title": {"romaji": "Dandadan"}, "episodes": 12},
                ...
            ]
        }
    }
}

# Mock OAuth token exchange
mock_oauth_response = {
    "access_token": "test_token_xyz",
    "token_type": "Bearer"
}

# Test patterns
def test_anilist_trending_with_pagination():
    # Fetch page 1 (50 items)
    # Should have next page available

def test_anilist_update_progress():
    # Watch episode 5 of anime ID 123
    # Call update_progress(123, 5)
    # Verify GraphQL mutation sent correctly

def test_anilist_network_error_recovery():
    # Timeout on first request
    # Should retry (with backoff)
```

## Test Data & Fixtures

### New Fixtures (in `conftest.py`):

```python
# Realistic mock anime data
@pytest.fixture
def mock_scraper_results_dandadan():
    """Realistic results from animefire + animesonlinecc"""
    return {
        "animefire": {
            "title": "Dandadan",
            "episodes": 12,
            "urls": ["url1", "url2", ...]
        },
        "animesonlinecc": {
            "title": "Dan Da Dan",  # Note: different name!
            "episodes": 12,
            "urls": ["url_a", "url_b", ...]
        }
    }

# Mock MPV exit codes
@pytest.fixture(params=[0, 1, 2, 3, 4])
def mpv_exit_code(request):
    """Parametrized exit codes for testing"""
    return request.param

# Mock AniList API
@pytest.fixture
def mock_anilist_client(monkeypatch):
    """Mock httpx client for AniList requests"""
    ...
```

## Test Execution Order & Dependencies

**Execution Flow:**

1. **Unit tests** (existing) - 5ms per test
2. **Scraper search tests** (new) - 50ms per test
3. **MPV playback tests** (new) - 20ms per test
4. **App workflow tests** (new) - 100ms per test (integration)
5. **AniList integration tests** (new) - 80ms per test (API mocks)

**Parallelization:**
- All test modules can run in parallel (pytest-xdist)
- No shared state between modules
- Mock fixtures are isolated per test

**Expected Total Runtime:** 5-10 seconds (pytest -n auto)

## Risk Mitigation

**Risk:** Tests become brittle due to tight coupling to implementation
**Mitigation:**
- Test behavior/contracts, not implementation details
- Use pytest fixtures for common setup
- Mock external dependencies (scrapers, APIs)

**Risk:** Tests timeout during scraper execution
**Mitigation:**
- All scraper tests use mocks (not real Selenium)
- Async race pattern tested with mock asyncio events
- Configurable timeouts per test

**Risk:** AniList API changes break tests
**Mitigation:**
- Use mock responses, not real API calls
- Version fixtures to match tested API schema
- Document breaking changes in CHANGELOG

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Total Tests | 208 | 320+ |
| App Workflow Coverage | ~40% | 90%+ |
| Scraper Integration | 0% | 100% |
| MPV Error Handling | 0% | 100% |
| AniList Integration | ~20% | 80%+ |
| Test Execution Time | 3s | <10s |
| Code Coverage | ~60% | 80%+ |
