# Specification: Testing Infrastructure

**Status:** ADDED

**Version:** 1.0

**Change ID:** `add-comprehensive-testing`

## Overview

ani-tupi includes automated test infrastructure for unit, integration, and end-to-end testing of core functionality. Tests validate business logic, plugin behavior, API integration, and complete user workflows without manual testing.

## ADDED Requirements

### Requirement: Test Execution Environment

The application MUST provide a test execution environment using pytest with configuration and dependency management.

#### Scenario: Run unit tests locally
```bash
pytest tests/ -v --cov
```
- Command execution MUST return exit code 0 if all tests pass
- Coverage report MUST be generated showing line coverage
- Execution time MUST be less than 5 seconds

#### Scenario: Run specific test module
```bash
pytest tests/test_repository.py -v
```
- Command execution MUST only run tests in specified module
- Results MUST show pass/fail status for each test function
- Filtering MUST work: `pytest tests/test_repository.py::test_title_normalization -v`

#### Scenario: Run with coverage by module
```bash
pytest --cov=repository --cov-report=term-missing tests/test_repository.py
```
- Coverage output MUST show line-by-line coverage
- Missing lines MUST be highlighted
- Coverage percentage MUST be displayed for module

#### Technical Details

- **Framework:** pytest 7.0+ (MUST be installed)
- **Async support:** pytest-asyncio 0.24+ (MUST support async tests)
- **Coverage:** pytest-cov 4.1+ (MUST generate coverage reports)
- **Configuration:** `pytest.ini` MUST define defaults (testpaths, addopts)
- **Dependencies:** All test dependencies MUST be in `pyproject.toml` dev group

### Requirement: Unit Test Coverage for Core Modules

The application MUST provide unit tests for core business logic modules with minimum coverage targets.

#### Scenario: Test title normalization
```python
test_repository.py::test_title_normalization
```
- Input: "Dandadan 2nd Season; Episode 3" MUST normalize to "dan da dan S02E03"
- Implementation MUST remove accents, punctuation, and normalize season notation
- Tests MUST validate exact match and edge cases

#### Scenario: Test fuzzy matching threshold
```python
test_repository.py::test_fuzzy_matching_95_percent
```
- Query "Dan Da Dan" MUST match database entry "Dandadan" when >95% similar
- Exact matches MUST be found
- Partial matches MUST respect 95% threshold boundary
- Tests MUST validate all match scenarios

#### Scenario: Test Repository state isolation
```python
test_repository.py::test_clear_search_results_resets_all
```
- Action: Add anime then clear search results
- Data structures MUST be completely emptied
- Tests MUST validate proper cleanup between test runs

#### Scenario: Test Pydantic model validation
```python
test_models.py::test_anime_metadata_validation
```
- Valid AnimeMetadata(title="...", url="...", source="...") MUST be accepted
- Missing required fields MUST raise ValidationError
- Invalid data MUST be rejected immediately

#### Scenario: Test history save/load
```python
test_history_service.py::test_save_load_preserves_state
```
- Save operation with anime="Dandadan", episode=5 MUST persist data
- Load operation MUST return exact state without data loss
- File I/O MUST handle serialization correctly

#### Technical Details

- **Module coverage requirements:**
  - `repository.py`: MUST have ≥80% coverage
  - `models.py`: MUST have ≥75% coverage
  - `config.py`: MUST have ≥70% coverage
  - `history_service.py`: MUST have ≥80% coverage

- **Test characteristics:**
  - MUST use only in-memory data (no file I/O)
  - MUST NOT require external dependencies
  - MUST be parametrized for multiple test cases
  - MUST execute in less than 1 second total

### Requirement: Integration Test Coverage for Plugin System

The application MUST provide integration tests validating plugin discovery, registration, and multi-plugin orchestration.

#### Scenario: Load plugins from directory
```python
test_plugin_loader.py::test_discover_plugins
```
- Plugins in `plugins/` directory MUST be auto-discovered
- All valid plugins MUST be loaded
- Plugin interface validation MUST be enforced
- Language filtering MUST work correctly

#### Scenario: Register plugin in Repository
```python
test_plugin_loader.py::test_register_plugin
```
- Plugin registration with `rep.register(MockPlugin)` MUST succeed
- Plugin MUST be accessible via `rep.get_active_sources()`
- Duplicate plugin names MUST be handled properly

#### Scenario: Multi-plugin search orchestration
```python
test_repository_integration.py::test_search_anime_parallel_plugins
```
- Multiple mock plugins MUST execute in parallel
- Results from all plugins MUST be merged in Repository
- ThreadPool execution MUST not block on slow plugins
- Deduplication MUST work across sources

#### Scenario: Plugin error handling
```python
test_repository_integration.py::test_search_fails_gracefully_if_plugin_throws
```
- When one plugin throws exception, others MUST continue
- Errors MUST be logged without stopping search
- Application MUST remain stable after plugin failure
- User MUST still see results from working plugins

#### Scenario: AniList API client with mocked HTTP
```python
test_anilist_service.py::test_get_trending_anime
```
- HTTP calls MUST be mocked (not real network requests)
- Sample response MUST be correctly parsed
- GraphQL query formatting MUST be validated
- Error handling MUST work for invalid responses

#### Technical Details

- **Modules tested:**
  - `loader.py`: Plugin discovery and validation MUST work
  - `repository.py`: Search orchestration MUST merge results
  - `core/anilist_service.py`: API client MUST handle responses

- **Mocking approach:**
  - Mock plugins: MUST replace real Selenium with fake implementations
  - Mock HTTP: MUST use `unittest.mock.patch('requests.post')`
  - Mock file I/O: MUST use pytest's `tmp_path` fixture

- **Test characteristics:**
  - Components MUST interact as in production
  - External services MUST be mocked (no real HTTP calls)
  - MUST execute in less than 2 seconds total

### Requirement: End-to-End Test Coverage for User Workflows

The application MUST provide E2E tests validating complete user workflows from start to finish.

#### Scenario: Search → Select → Load Episodes → Select Episode workflow
```python
test_e2e_search.py::test_complete_search_workflow
```
1. User search with `rep.search_anime("dandadan")` MUST succeed
2. Anime list MUST contain "Dandadan" entry
3. Anime selection MUST set current selection in Repository
4. Episodes MUST be loaded and accessible
5. Episode selection MUST return correct episode data
6. Full workflow MUST complete without errors

#### Scenario: Video URL extraction with fallback
```python
test_e2e_video_extraction.py::test_fallback_to_second_plugin
```
1. First mock plugin failure MUST not stop search
2. Second mock plugin MUST be attempted
3. Video URL from successful plugin MUST be returned
4. Async race pattern MUST execute correctly
5. Error recovery MUST be transparent to user

#### Scenario: Watch episode → Update history → Resume watching
```python
test_e2e_anilist.py::test_watch_and_save_workflow
```
1. Episode 5 watch action MUST be saved to history
2. History MUST persist to disk correctly
3. Resume watching MUST restore exact state
4. Episode index MUST match saved value
5. Anime title MUST match saved title

#### Technical Details

- **Workflows covered:**
  - Search and episode selection MUST work end-to-end
  - Video URL discovery MUST support multi-source fallback
  - History persistence MUST survive app restart
  - AniList integration MUST sync progress (with mocking)

- **Test characteristics:**
  - MUST use realistic mock data (anime names, episode counts)
  - MUST validate full data flow from start to finish
  - MUST mock only external services (HTTP, file paths)
  - MUST execute in less than 2 seconds total

### Requirement: CI/CD Test Automation

The application MUST run tests automatically on every push and PR with GitHub Actions.

#### Scenario: Tests run on push to main branch
```yaml
on: [push, pull_request]
```
- GitHub Actions workflow MUST be triggered automatically
- All tests MUST execute in CI environment
- Coverage report MUST be generated
- Results MUST be posted to commit

#### Scenario: Tests required to pass for PR merge
```yaml
check-required: true
```
- PR MUST NOT be mergeable without passing tests
- Failed tests MUST block merge
- Developer MUST see failures in PR checks
- Test status MUST be visible in GitHub UI

#### Scenario: Coverage reports accessible
```bash
codecov upload
```
- Coverage report MUST be uploaded to Codecov
- Historical coverage trends MUST be visible
- Coverage badge MUST be available for README
- Coverage regression MUST be detected

#### Technical Details

- **Workflow file:** `.github/workflows/test.yml` (MUST exist)
- **Trigger:** MUST run on [push, pull_request]
- **Steps MUST include:**
  1. Checkout code
  2. Setup Python 3.12
  3. Install dependencies (uv sync)
  4. Run pytest with coverage
  5. Upload coverage report
- **Execution time:** MUST complete in < 5 minutes

### Requirement: Test Data and Fixtures

The application MUST provide reusable test data and fixtures supporting multiple tests.

#### Scenario: Mock anime fixture
```python
@pytest.fixture
def sample_anime():
    return AnimeMetadata(...)
```
- Fixture MUST provide valid AnimeMetadata instance
- Data MUST be reusable by multiple tests
- Fixture setup MUST be isolated (no test pollution)

#### Scenario: Mock episode fixture
```python
@pytest.fixture
def sample_episodes():
    return EpisodeData(...)
```
- Fixture MUST provide valid EpisodeData instance
- Episode titles and URLs MUST match in length
- Fixture MUST be reusable without state persistence

#### Scenario: Clean Repository fixture
```python
@pytest.fixture
def repo_clean():
    repo = Repository()
    repo.clear_search_results()
    yield repo
```
- Fixture MUST provide fresh Repository instance
- All search results MUST be cleared before test
- Original state MUST be restored after test

#### Scenario: Test data from JSON files
```
fixtures/
├── anime_data.json      # Realistic anime metadata
├── episode_data.json    # Realistic episode lists
└── anilist_responses.json # Sample API responses
```
- Test data files MUST contain realistic sample data
- Data MUST match structure of actual API responses
- Files MUST be easy to update when sites change

#### Technical Details

- **Fixture location:** `tests/conftest.py` (MUST be present)
- **Test data location:** `tests/fixtures/` (MUST exist)
- **Characteristics:**
  - Fixtures MUST be reusable across multiple tests
  - Test data MUST be realistic (matches real sites)
  - Fixtures MUST be centralized (easy to update)
  - Data MUST be parametrizable for multiple scenarios

### Requirement: Test Documentation and Conventions

The application MUST provide test documentation and enforce consistent naming conventions.

#### Scenario: Test function naming
```
test_[module]_[scenario]_[expected_outcome]
test_repository_fuzzy_matching_returns_match_above_threshold
test_plugin_loader_discovers_plugins_in_directory
```
- Test names MUST follow pattern: `test_[module]_[scenario]_[outcome]`
- Names MUST be descriptive and self-documenting
- Test discovery MUST find all tests starting with `test_`

#### Scenario: Test module documentation
```python
"""
Tests for repository.py

Coverage:
- Title normalization
- Fuzzy matching (95% threshold)
- Plugin registration
- State isolation
"""
```
- Module docstrings MUST document coverage areas
- Docstrings MUST list tested functionality
- Documentation MUST help future developers add tests

#### Scenario: How to run tests (tests/README.md)
```
# Run all tests
pytest

# Run specific test
pytest tests/test_repository.py::test_title_normalization

# Run with coverage
pytest --cov

# Run in parallel
pytest -n auto
```
- README MUST provide clear running instructions
- Commands MUST work on all platforms
- Examples MUST show common test scenarios

#### Scenario: How to add new tests
Template provided in `tests/README.md`:
```python
class TestNewFeature:
    def test_basic_scenario(self, fixture):
        # Arrange
        # Act
        # Assert
```
- Template MUST be provided for new test creation
- Guidelines MUST explain structure (Arrange-Act-Assert)
- Examples MUST show fixture usage

#### Technical Details

- **Documentation file:** `tests/README.md` (MUST exist)
- **Naming conventions:** MUST be consistent across all tests
- **Template:** MUST be available for new test creation
- **Style:** MUST follow project linting rules (ruff)
- **Format:** MUST use Arrange-Act-Assert pattern

## Coverage Targets

| Module | Target | Rationale |
|--------|--------|-----------|
| `repository.py` | 80% | Core business logic, critical for reliability |
| `models.py` | 75% | Data validation, prevents bad data |
| `config.py` | 70% | Configuration loading, less critical |
| `history_service.py` | 80% | Persistence, data integrity essential |
| `core/anilist_service.py` | 70% | API client, integration validated |
| `loader.py` | 65% | Plugin system, less critical for users |
| **Overall** | **60%** | Reasonable baseline for CLI tool |

## Test Execution Performance

- **Unit tests:** <1 second
- **Integration tests:** ~2 seconds
- **E2E tests:** ~2 seconds
- **Total suite:** <5 seconds

## Out of Scope

- Live scraper testing (websites may change)
- Real video playback validation
- Full TUI layer testing (manual testing preferred)
- Performance benchmarking (can be added later)
- Selenium-based plugin tests (use mocks instead)

## Related Specifications

- None yet (testing is new capability)

## Implementation Notes

- Tests use pytest as standard framework
- Tests are independent (no order dependencies)
- Tests don't require system dependencies (FFmpeg, MPV, Selenium)
- Tests run in parallel for speed
- Tests use pytest fixtures for setup/teardown
