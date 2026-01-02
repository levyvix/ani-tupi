# Spec Delta: Scraper Search Tests

**Capability:** Comprehensive scraper search and title normalization
**Module:** `tests/test_scraper_search.py`
**Status:** Proposed

## ADDED Requirements

### Requirement: Title normalization handles diverse character sets

**Scenario: Anime with accents, special chars, unicode titles**
1. Input: "Dãndadãn" (with accents)
2. Normalization removes accents: "Dandadan"
3. Fuzzy match with "Dandadan" from other source: 100% match ✓

4. Input: "Attack on Titan (Part 1)" (with parentheses)
5. Normalization removes special chars: "Attack on Titan Part 1"
6. Fuzzy match with "Attack on Titan" from other source: 95%+ match ✓

7. Input: "進撃の巨人" (Japanese kanji)
8. Normalization preserves for search but standardizes format
9. Uniquely tracked (doesn't match English "Attack on Titan")

**Validation Tests:**
- `test_normalize_removes_accents()` - Diacritics handled
- `test_normalize_removes_special_characters()` - Brackets, dashes removed
- `test_normalize_handles_unicode_japanese()` - Kanji preserved

**Related:**
- `test_repository.py::TestTitleNormalization` (existing unit tests)

---

### Requirement: Multi-source anime deduplication with fuzzy matching

**Scenario: Same anime available from 2 sources with different titles**
1. animefire returns: title="Dan Da Dan", episodes=12
2. animesonlinecc returns: title="Dandadan", episodes=12
3. Repository detects 95%+ fuzzy match
4. Consolidates into single anime entry with 2 sources
5. User sees "Dandadan [animefire, animesonlinecc]" once, not twice

**Validation Tests:**
- `test_deduplicate_same_title_different_sources()` - Same anime merged
- `test_deduplicate_with_fuzzy_threshold()` - 95% threshold applied
- `test_deduplicate_across_four_sources()` - Scales to many sources

**Related:**
- `test_repository.py::TestAnimeDeduplication` (existing)

---

### Requirement: Parallel plugin search execution with result collection

**Scenario: Multiple plugins execute simultaneously for faster results**
1. User initiates search for "Dandadan"
2. ThreadPool launches all 3+ plugins in parallel (not sequentially)
3. animefire finishes first (0.5s)
4. Results accumulated in repository
5. animesonlinecc finishes second (1.2s)
6. Results accumulated (doesn't replace first)
7. All sources present in final results

**Validation Tests:**
- `test_parallel_plugin_execution()` - ThreadPool active
- `test_search_results_from_all_plugins()` - All contribute

**Related:**
- `repository.py::_search_with_incremental_results()` (ThreadPool implementation)

---

### Requirement: Consistent episode lists across multiple sources

**Scenario: Episode counts and lists match across sources**
1. animefire: 12 episodes with titles ["Ep 1 - Title", ...]
2. animesonlinecc: 12 episodes with same titles
3. Repository merges but preserves both source URLs per episode
4. User can play episode 5 from either source

**Validation Tests:**
- `test_episode_list_consistency()` - Same episodes, different sources
- `test_episodes_episode_count_matches()` - All sources have 12 episodes
- `test_episodes_from_multiple_sources()` - Both sources available

---

### Requirement: Search handles edge cases gracefully

**Scenario: Zero results, single result, many results**
1. Search "nonexistent": 0 results → show error
2. Search "Very Specific Anime Title": 1 result → auto-select
3. Search "Anime": 50+ results → show top 10 with "Show All" button

**Validation Tests:**
- `test_search_with_zero_results()` - Error message shown
- `test_search_with_one_result()` - Auto-select
- `test_search_with_many_results()` - Top 10 shown, pagination available

---

## MODIFIED Requirements

None - new capability.

---

## REMOVED Requirements

None.

---

## Cross-References

- **Foundation for:** App Workflow Tests
- **Uses:** Repository fuzzy matching, title normalization
- **Used by:** All scraper-dependent workflows
