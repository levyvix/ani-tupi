# Proposal: Add Comprehensive Testing Framework

**Change ID:** `add-comprehensive-testing`

**Date:** 2026-01-02

**Scope:** Add automated testing infrastructure with unit tests, integration tests, and end-to-end test workflows to replace manual testing requirements.

## Problem Statement

Currently, every change requires manual testing of the entire application workflow:
1. Search for anime
2. Select anime from results
3. Load episodes
4. Select episode
5. Extract and play video
6. Update history/AniList

This is time-consuming and error-prone. There is no automated test suite to:
- Catch regressions when refactoring code
- Validate plugin behavior independently
- Test edge cases (fuzzy matching, title normalization, cache behavior)
- Verify API integrations (AniList, scrapers)
- Ensure cross-platform compatibility

### Current State
- **No test suite:** Only manual testing via CLI with `--debug` flag
- **No test dependencies:** pytest not in dev dependencies
- **No test infrastructure:** No conftest.py, test fixtures, mocks, or CI test workflow
- **Manual regression testing:** Each change requires re-testing entire workflow

## Proposed Solution

Create a **three-layer testing framework**:

1. **Unit Tests** - Fast, isolated tests for core logic (Repository, models, config)
2. **Integration Tests** - Test plugin loading, plugin interactions, and data pipelines
3. **End-to-End Tests** - Test complete user workflows with mock data

### Layer 1: Unit Tests

**Target modules:**
- `repository.py` - Title normalization, fuzzy matching, data storage
- `models.py` - Pydantic validation and model serialization
- `config.py` - Configuration loading and path resolution
- `core/history_service.py` - History save/load logic
- `cache_manager.py` - Cache operations

**Benefits:**
- Fast execution (~1 second for all unit tests)
- Can run on CI without external dependencies
- Tests core business logic in isolation

### Layer 2: Integration Tests

**Target modules:**
- `loader.py` - Plugin discovery and loading
- `repository.py` + plugins - Search orchestration and plugin registration
- `core/anilist_service.py` - AniList API client (with mocked HTTP)

**Benefits:**
- Tests component interactions (plugins, repository)
- Validates data flow between modules
- Uses mocked external services (no real API calls)

### Layer 3: End-to-End Tests

**Target workflows:**
- Complete anime search and episode selection
- Video URL extraction (with mock sources)
- History persistence and resume-watching
- AniList integration flow

**Benefits:**
- Tests actual user workflows
- Validates full data pipelines
- Detects integration issues

## Key Requirements

### Testing Infrastructure

1. **Test Framework:** pytest with fixtures and parametrization
2. **Test Organization:** Tests colocated with source modules in `tests/` directory
3. **Test Data:** Mock anime/episode data for reproducible testing
4. **Mocking:** unittest.mock for external services (HTTP, file I/O)
5. **CI Integration:** GitHub Actions workflow to run tests on push/PR
6. **Coverage Reports:** Pytest coverage output (target: 60% for core logic)

### Mock Strategy

- **HTTP requests:** Mock responses using unittest.mock
- **Plugin execution:** Use mock plugin classes instead of real Selenium
- **File I/O:** Use temporary directories (pytest's `tmp_path`)
- **External APIs:** Mock AniList and scraper responses

### Test Data

Create fixture files with realistic test data:
- Sample anime search results
- Sample episode lists
- Sample video URL responses
- Sample AniList API responses

## Success Criteria

1. ✅ At least 50 test cases covering unit, integration, and E2E layers
2. ✅ All core modules (repository, models, config, history) have >70% coverage
3. ✅ CI/CD workflow runs tests on every push/PR
4. ✅ Tests run in <5 seconds (excluding external API calls)
5. ✅ Clear documentation on how to run and add tests
6. ✅ Manual testing time reduced by 80% for normal changes

## Out of Scope

- Live scraper testing (external sites may change)
- Real video playback testing
- Full coverage of UI layer (TUI is tested manually)
- Performance benchmarking (can be added later)

## Implementation Notes

- Tests use **pytest** (standard Python testing framework)
- Tests are **independent** (no test order dependencies)
- Tests **don't require system dependencies** (FFmpeg, MPV, Selenium) except for plugin tests
- Tests **run in parallel** for speed
- Tests use **pytest fixtures** for setup/teardown and data sharing
