# Implementation Tasks: add-comprehensive-testing

## Setup Phase (Infrastructure)

- [ ] **Task 1:** Add pytest dependencies to `pyproject.toml`
  - [ ] Add `pytest>=7.0.0` to dev dependencies
  - [ ] Add `pytest-asyncio>=0.24.0` for async test support
  - [ ] Add `pytest-cov>=4.1.0` for coverage reports
  - [ ] Run `uv sync` to update lock file

- [ ] **Task 2:** Create test infrastructure
  - [ ] Create `tests/` directory structure
  - [ ] Create `tests/conftest.py` with shared fixtures
  - [ ] Create `tests/fixtures/` with test data (mock anime, episodes, responses)
  - [ ] Create `pytest.ini` configuration file

- [ ] **Task 3:** Add CI/CD test workflow
  - [ ] Create `.github/workflows/test.yml` GitHub Actions workflow
  - [ ] Workflow runs on: push to master, all PRs
  - [ ] Workflow steps: install deps, run pytest, upload coverage
  - [ ] Mark step as required for PR merges

## Unit Tests Phase (Core Logic)

- [ ] **Task 4:** Write Repository tests (`tests/test_repository.py`)
  - [ ] Test title normalization (accent removal, punctuation, spaces)
  - [ ] Test fuzzy matching logic (95% threshold)
  - [ ] Test anime deduplication (same title from different sources)
  - [ ] Test plugin registration and retrieval
  - [ ] Test `clear_search_results()` state management
  - [ ] Goal: ≥15 test cases, ≥70% coverage

- [ ] **Task 5:** Write models validation tests (`tests/test_models.py`)
  - [ ] Test AnimeMetadata creation and validation
  - [ ] Test EpisodeData with mismatched title/URL lists
  - [ ] Test VideoUrl with optional headers
  - [ ] Test invalid data raises validation errors
  - [ ] Goal: ≥10 test cases

- [ ] **Task 6:** Write config tests (`tests/test_config.py`)
  - [ ] Test settings loading from environment variables
  - [ ] Test default values (cache duration, API URLs)
  - [ ] Test path resolution (cross-platform `get_data_path()`)
  - [ ] Test config validation (invalid values rejected)
  - [ ] Goal: ≥10 test cases

- [ ] **Task 7:** Write history service tests (`tests/test_history_service.py`)
  - [ ] Test save/load history (JSON serialization)
  - [ ] Test history with multiple anime entries
  - [ ] Test resume-watching state extraction
  - [ ] Test temporary directory cleanup
  - [ ] Goal: ≥8 test cases

## Integration Tests Phase (Component Interactions)

- [ ] **Task 8:** Write plugin loader tests (`tests/test_plugin_loader.py`)
  - [ ] Test plugin discovery from `plugins/` directory
  - [ ] Test plugin registration in Repository
  - [ ] Test plugin interface validation (required methods exist)
  - [ ] Test language filtering (only load pt-br plugins)
  - [ ] Test mock plugin creation for testing
  - [ ] Goal: ≥10 test cases

- [ ] **Task 9:** Write Repository + plugin integration tests (`tests/test_repository_integration.py`)
  - [ ] Test `search_anime()` with mock plugins in parallel
  - [ ] Test `search_episodes()` with mock plugin results
  - [ ] Test fuzzy matching with duplicate anime names across sources
  - [ ] Test cache hit/miss behavior
  - [ ] Test error handling when plugin fails
  - [ ] Goal: ≥12 test cases

- [ ] **Task 10:** Write AniList service tests (`tests/test_anilist_service.py`)
  - [ ] Test GraphQL query formatting
  - [ ] Test authentication token handling (mocked)
  - [ ] Test trending anime endpoint (mocked HTTP response)
  - [ ] Test user list retrieval (mocked)
  - [ ] Test progress update (mocked POST)
  - [ ] Test error handling for invalid tokens
  - [ ] Goal: ≥12 test cases

## End-to-End Tests Phase (Complete Workflows)

- [ ] **Task 11:** Write complete search workflow test (`tests/test_e2e_search.py`)
  - [ ] Test: Search anime → Select anime → Load episodes → Select episode
  - [ ] Use mock plugins with realistic data
  - [ ] Test title normalization in real workflow
  - [ ] Test episode list caching
  - [ ] Goal: ≥5 test cases (workflow variations)

- [ ] **Task 12:** Write video extraction workflow test (`tests/test_e2e_video_extraction.py`)
  - [ ] Test: Get video URL from mock source (no actual playback)
  - [ ] Test: Multi-source fallback (one plugin fails, another succeeds)
  - [ ] Test: Timeout behavior if all plugins fail
  - [ ] Test: URL validation (must be valid m3u8 or mp4)
  - [ ] Goal: ≥5 test cases

- [ ] **Task 13:** Write AniList integration workflow test (`tests/test_e2e_anilist.py`)
  - [ ] Test: Search → Watch → Update AniList progress
  - [ ] Test: Logout and re-authenticate
  - [ ] Test: AniList offline (network error handling)
  - [ ] Goal: ≥4 test cases

## Documentation & Validation Phase

- [ ] **Task 14:** Create testing documentation
  - [ ] Write `tests/README.md` with:
    - [ ] How to run tests locally (`pytest`, `pytest -v`, `pytest --cov`)
    - [ ] How to run specific tests (`pytest tests/test_repository.py`)
    - [ ] How to add new tests (template and guidelines)
    - [ ] How to create mock data (fixtures)
    - [ ] Expected coverage targets by module

- [ ] **Task 15:** Validate test suite
  - [ ] Run `pytest -v` to ensure all tests pass
  - [ ] Run `pytest --cov` and verify ≥60% overall coverage
  - [ ] Run `pytest --cov` for each module and verify ≥70% for core modules
  - [ ] Run tests in parallel: `pytest -n auto` (requires pytest-xdist)
  - [ ] Ensure CI workflow passes on test.yml

- [ ] **Task 16:** Add test examples to project documentation
  - [ ] Update main `README.md` with test running instructions
  - [ ] Add testing section to `CLAUDE.md` project guide
  - [ ] Include example: "How to test my new plugin"

## Final Steps

- [ ] **Task 17:** Review and cleanup
  - [ ] Verify all 50+ test cases pass
  - [ ] Run `ruff check` on test files (follow project style)
  - [ ] Ensure test files have proper docstrings
  - [ ] Verify test fixtures are reusable and well-documented
  - [ ] Remove any temporary test files created during development

- [ ] **Task 18:** Create PR and update specs
  - [ ] Create PR with new test files and CI workflow
  - [ ] Update `openspec/specs/` if testing becomes a formal capability
  - [ ] Once merged, archive this change: `openspec archive add-comprehensive-testing --yes`

## Success Validation

After implementation, you should be able to:

1. ✅ Run `pytest` and see 50+ tests pass in <5 seconds
2. ✅ Run `pytest --cov` and see ≥60% coverage
3. ✅ Make a change to `repository.py` and immediately know if tests break
4. ✅ Add a new plugin and validate it with mock tests
5. ✅ Make a PR and see CI run tests automatically
6. ✅ Test the entire workflow without manual steps (except final video playback)

## Estimated Effort

- **Setup phase:** 1-2 hours
- **Unit tests:** 2-3 hours
- **Integration tests:** 2-3 hours
- **E2E tests:** 1-2 hours
- **Documentation:** 1 hour
- **Total:** 7-11 hours

Can be parallelized: Setup + some unit/integration tests can happen simultaneously.
