# ani-tupi Test Suite Documentation

Complete guide to running and writing tests for ani-tupi.

## Quick Start

### Run All Tests

```bash
# Simple
uv run pytest

# Verbose output
uv run pytest -v

# With coverage report
uv run pytest --cov=. --cov-report=term-missing

# Run in parallel (faster)
uv run pytest -n auto
```

### Run Specific Tests

```bash
# Run single test file
uv run pytest tests/test_repository.py

# Run single test class
uv run pytest tests/test_repository.py::TestTitleNormalization

# Run single test function
uv run pytest tests/test_repository.py::TestTitleNormalization::test_normalize_removes_accents

# Run tests matching pattern
uv run pytest -k "normalization"
```

### Run by Test Type

```bash
# Unit tests only
uv run pytest -m unit

# Integration tests only
uv run pytest -m integration

# E2E tests only
uv run pytest -m e2e

# Skip slow tests
uv run pytest -m "not slow"
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── fixtures/                # Mock data (JSON)
│   ├── anime_data.json
│   ├── episode_data.json
│   └── anilist_responses.json
├── test_repository.py       # Unit: Repository (15+ tests)
├── test_models.py           # Unit: Data models (10+ tests)
├── test_config.py           # Unit: Configuration (10+ tests)
├── test_history_service.py  # Unit: History (8+ tests)
├── test_plugin_loader.py    # Integration: Plugin loading (10+ tests)
├── test_repository_integration.py  # Integration: Repository + plugins (12+ tests)
├── test_anilist_service.py  # Integration: AniList API (12+ tests)
├── test_e2e_search.py       # E2E: Search workflow (5+ tests)
├── test_e2e_video_extraction.py    # E2E: Video extraction (5+ tests)
├── test_e2e_anilist.py      # E2E: AniList workflow (4+ tests)
└── README.md                # This file
```

## Test Categories

### Unit Tests (Fast, Isolated)

**Files:** `test_repository.py`, `test_models.py`, `test_config.py`, `test_history_service.py`

- Test individual modules in isolation
- No external dependencies
- Fast execution (<1 second total)
- Run before every commit

**Example:**
```bash
uv run pytest tests/test_repository.py -v
```

### Integration Tests (Component Interactions)

**Files:** `test_plugin_loader.py`, `test_repository_integration.py`, `test_anilist_service.py`

- Test how modules interact
- Use mocked external services
- Realistic data flow
- Run before PR

**Example:**
```bash
uv run pytest tests/test_repository_integration.py -v
```

### End-to-End Tests (Complete Workflows)

**Files:** `test_e2e_*.py`

- Test full user workflows
- Minimal mocking
- Realistic scenarios
- Run before release

**Example:**
```bash
uv run pytest tests/test_e2e_search.py -v
```

## Writing New Tests

### Test Template

```python
"""
Tests for module_name.py

Coverage:
- What this test file covers
"""

import pytest


class TestFeatureName:
    """Test specific feature."""

    def test_basic_behavior(self):
        """Should do something expected."""
        # Arrange
        data = setup_test_data()

        # Act
        result = do_something(data)

        # Assert
        assert result is not None
```

### Using Fixtures

```python
def test_with_repo(self, repo_fresh):
    """Use fresh Repository fixture."""
    repo_fresh.add_anime("Test", "url", "source")
    assert len(repo_fresh.get_anime_list()) > 0


def test_with_sample_anime(self, sample_anime_dandadan):
    """Use sample anime fixture."""
    assert sample_anime_dandadan.title == "Dandadan"


def test_with_temp_file(self, temp_history_file):
    """Use temporary file fixture."""
    # Use temp_history_file path
    Path(temp_history_file).write_text("test")
```

### Available Fixtures

**Repository:**
- `repo_fresh` - Fresh Repository instance, auto-cleared before/after
- `mock_plugins_fixture` - Repo with mock plugins pre-registered

**Sample Data:**
- `sample_anime_dandadan` - Dandadan metadata
- `sample_anime_attack_on_titan` - Attack on Titan metadata
- `sample_episodes_dandadan` - 12-episode list
- `sample_episodes_short` - 3-episode list
- `sample_video_url` - Video URL with headers

**Mock Data:**
- `mock_anilist_response_trending` - AniList trending response
- `mock_anilist_response_user_list` - AniList user list response

**File I/O:**
- `temp_history_file` - Temporary history JSON file
- `temp_cache_dir` - Temporary cache directory

**Configuration:**
- `mock_settings` - Mocked settings object
- `monkeypatch_settings` - Function to set config values

### Common Test Patterns

**Testing exceptions:**
```python
def test_invalid_input_raises_error(self):
    """Should raise ValidationError for invalid input."""
    with pytest.raises(ValidationError):
        AnimeMetadata(title="", url="url", source="source")
```

**Parametrized tests:**
```python
@pytest.mark.parametrize("input,expected", [
    ("dandadan", "Dandadan"),
    ("ATTACK on TITAN", "Attack on Titan"),
])
def test_normalize_titles(self, input, expected):
    """Should normalize various titles."""
    assert normalize(input) == expected
```

**Mocking external calls:**
```python
from unittest.mock import patch

@patch("requests.post")
def test_api_call(self, mock_post):
    """Should make API call."""
    mock_post.return_value.json.return_value = {"data": {}}
    result = client.search()
    assert result is not None
```

## Coverage Goals

Target coverage by module:

| Module | Target | Status |
|--------|--------|--------|
| `repository.py` | 80% | In progress |
| `models.py` | 75% | In progress |
| `config.py` | 70% | In progress |
| `history_service.py` | 80% | In progress |
| `core/anilist_service.py` | 70% | In progress |
| `loader.py` | 65% | In progress |
| **Overall** | **60%** | Aim for this minimum |

### Check Coverage

```bash
# Terminal report
uv run pytest --cov=. --cov-report=term-missing

# HTML report (opens in browser)
uv run pytest --cov=. --cov-report=html
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Debugging Tests

### Run with Output

```bash
# Show print statements
uv run pytest tests/test_repository.py -v -s

# Show one test in detail
uv run pytest tests/test_repository.py::test_name -v -s
```

### Debug with Debugger

```bash
# Stop at first failure and drop to pdb
uv run pytest --pdb tests/test_repository.py

# Stop at failure with full traceback
uv run pytest --pdb --tb=long tests/test_repository.py
```

### Run Single Test

```bash
# Easiest way to debug one test
uv run pytest tests/test_repository.py::TestAnimeRegistration::test_add_anime_single -v -s
```

## Performance Tips

### Speed Up Tests

```bash
# Run in parallel
uv run pytest -n auto

# Run only changed tests (requires pytest-git)
uv run pytest --git-only

# Skip slow tests
uv run pytest -m "not slow"
```

### Profile Test Execution

```bash
# Show slowest 10 tests
uv run pytest --durations=10
```

## Continuous Integration

Tests run automatically on:
- **Push to master:** All tests must pass
- **Pull request:** All tests must pass before merge
- **Workflow:** `.github/workflows/test.yml`

### View CI Results

On GitHub:
1. Go to Pull Request
2. Click "Checks" tab
3. Click "Tests" to see results
4. Click "Details" for full output

### Local CI Check

Before pushing:
```bash
# Run all tests locally first
uv run pytest -v --cov

# Check ruff style
uvx ruff check tests/
uvx ruff format tests/
```

## Test Maintenance

### Update Tests When Code Changes

If you modify:
- **A function signature** → Update corresponding tests
- **Business logic** → Update assertions
- **Error handling** → Add error test cases
- **Configuration** → Update config tests

### Keep Tests Independent

```python
# ✅ GOOD: Each test is independent
def test_add_anime(self, repo_fresh):
    repo_fresh.add_anime("A", "url", "source")
    assert "A" in repo_fresh.get_anime_list()

def test_search_anime(self, repo_fresh):
    repo_fresh.search_anime("test")
    # fresh repo used, no dependence on previous test
```

```python
# ❌ BAD: Tests depend on execution order
def test_1_add_anime(self, repo):  # Shares state
    repo.add_anime("A", "url", "source")

def test_2_search(self, repo):  # Depends on test_1
    assert "A" in repo.get_anime_list()
```

## Troubleshooting

### "ModuleNotFoundError: No module named..."

```bash
# Resync dependencies
uv sync

# Or run with full path
cd /home/levi/ani-tupi && uv run pytest
```

### "Fixture not found"

- Fixture must be in `conftest.py` at same level or parent
- Check fixture name spelling
- Run from project root: `uv run pytest tests/`

### "Test hangs or times out"

```bash
# Add timeout (requires pytest-timeout)
uv add --dev pytest-timeout

# Then use in tests:
@pytest.mark.timeout(5)
def test_something(self):
    # Must complete in 5 seconds
    pass
```

### Tests pass locally but fail in CI

- Check Python version (should be 3.12)
- Check OS (tests run on both Ubuntu and macOS)
- Run `uv sync` to match lock file
- Look at CI logs in `.github/workflows/test.yml`

## Adding New Modules

When adding a new module `new_feature.py`:

1. Create `tests/test_new_feature.py`
2. Follow naming pattern: `test_[module_name].py`
3. Create test classes for each feature
4. Aim for >70% coverage
5. Add docstring explaining what's tested
6. Use existing fixtures where possible

Example:
```python
"""
Tests for new_feature.py

Coverage:
- Main function behavior
- Error handling
- Edge cases
"""

import pytest

class TestMainFunction:
    def test_basic_behavior(self):
        from new_feature import main_function
        result = main_function("test")
        assert result is not None
```

## CI/CD Integration

### GitHub Actions Workflow

Located at `.github/workflows/test.yml`

**Runs on:**
- Push to `master`, `main`, `develop`
- All pull requests
- Both Ubuntu and macOS

**Steps:**
1. Checkout code
2. Set up Python 3.12
3. Install uv
4. Sync dependencies (`uv sync`)
5. Run tests with coverage (`pytest --cov`)
6. Upload coverage to Codecov

**Required for PR merge:**
- All tests pass
- Coverage doesn't decrease significantly

### Manual CI Run

To simulate CI locally:
```bash
# Full CI simulation
uv sync
uv run pytest -v --cov --cov-report=xml
```

## Resources

- **pytest documentation:** https://docs.pytest.org/
- **Project CLAUDE.md:** See Development Commands section
- **conftest.py:** Available fixtures and setup
- **Test files:** Examples of working tests

## Contributing Tests

When submitting PRs:
1. Add tests for new features
2. Update tests for changed behavior
3. Ensure coverage >70% for modified modules
4. Tests must pass locally first: `uv run pytest -v`
5. Run `uvx ruff check tests/` to check style
6. Add docstring explaining test coverage

Thanks for testing! 🧪
