# Proposal: Comprehensive App Workflow and Integration Tests

**Status:** Draft
**Change ID:** expand-comprehensive-testing
**Date:** 2026-01-02

## Problem Statement

Current test coverage (208 passing, 35 skipped) focuses on individual components (Repository, Models, Config) but lacks end-to-end integration tests for critical user workflows:

1. **App Workflow Tests** - No tests verify the complete anime search → episode selection → playback loop or AniList integration workflows
2. **Scraper Search Tests** - No tests verify scraper plugin execution, title normalization, fuzzy matching, or multi-source deduplication in realistic scenarios
3. **MPV Playback Tests** - No tests verify exit code handling, error recovery, or fallback behavior when video URLs fail
4. **AniList Integration Tests** - Limited tests for authentication, progress sync, list updates, or error handling
5. **Real Plugin Interaction** - Tests use mocks; no verification that real scrapers (animefire, animesonlinecc) work correctly

## Proposed Solution

Expand test suite with four complementary test modules targeting realistic user scenarios:

### 1. **App Workflow Tests** (`test_e2e_app_workflow.py`)
- Main menu navigation and state transitions
- Search → Episode selection → Playback flow
- Continue watching with history loading
- Error recovery (no results, API failures)
- Plugin source management
- AniList authentication and browsing

### 2. **Scraper Search Tests** (`test_scraper_search.py`)
- Title normalization edge cases (accents, special chars, unicode)
- Fuzzy matching and deduplication across sources
- Plugin execution order and timeout behavior
- Search with 0, 1, or multiple results
- Episode list consistency across sources
- Handling malformed scraper responses

### 3. **MPV Playback Tests** (`test_mpv_playback.py`)
- Exit code interpretation (0, 1, 2, 3, 4)
- Fallback to VLC when MPV fails
- yt-dlp integration and URL format handling
- Timeout and interrupt handling
- Debug mode (skip playback)
- User quit vs playback errors

### 4. **AniList Integration Tests** (`test_anilist_integration.py`)
- OAuth token refresh and expiration
- Trending anime fetching with pagination
- User list updates (watching, planning, completed)
- Progress sync after episode playback
- Anime search and ID resolution
- Network error handling and retry logic

## Expected Outcomes

**Before:**
- 208 unit/component tests
- Limited E2E coverage
- No verification of real plugin behavior
- No MPV error code validation

**After:**
- 300+ total tests
- Comprehensive E2E workflow validation
- Real plugin integration tests (with mocks)
- MPV exit code and fallback handling
- AniList OAuth and API interaction tests
- ~90%+ code coverage for critical paths

## Success Criteria

1. ✅ All new tests pass with realistic data and mocks
2. ✅ App workflow tests verify state transitions and error recovery
3. ✅ Scraper tests validate title normalization, deduplication, and multi-source behavior
4. ✅ MPV tests verify all exit codes and fallback scenarios
5. ✅ AniList tests verify authentication, list updates, and progress sync
6. ✅ Test suite runs under 10 seconds (pytest optimization)

## Dependencies & Sequencing

1. **Phase 1** (Independent, can be parallel):
   - Scraper search tests (mock-based, no external dependencies)
   - MPV playback tests (mock-based, configurable subprocess behavior)

2. **Phase 2** (Dependent on Phase 1):
   - App workflow tests (uses scraper + playback infrastructure)

3. **Phase 3** (External dependency):
   - AniList integration tests (requires test API key or mock responses)

## Decisions Made

1. ✅ **Real Scrapers:** Will test against actual sites (animefire.plus, animesonlinecc.to)
   - Benefit: Catches real breaking changes immediately
   - Risk: Tests may fail if sites change; use retry logic for flaky tests

2. ✅ **AniList API:** Will use mocked responses (not test account)
   - Benefit: Fast, reliable, complete control over scenarios
   - Trade-off: Won't catch real API schema changes (but accept that risk)

3. ✅ **MPV Fallback:** Remove VLC fallback (tested, doesn't work reliably)
   - Change: MPV failures show error message instead of attempting VLC
   - Impact: User must retry or select different episode
   - Tests: Focus on exit code interpretation, not fallback

4. **Async Race Pattern:** Will mock asyncio events in tests
   - Tests will simulate plugin race with controllable timing
   - Won't test real asyncio behavior (too complex; unit tests cover that)

## Implementation Status

✅ Proposal complete, ready for implementation phase after approval.
