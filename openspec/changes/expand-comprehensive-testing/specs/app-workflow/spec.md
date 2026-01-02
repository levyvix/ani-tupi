# Spec Delta: App Workflow Tests

**Capability:** End-to-end app workflow testing
**Module:** `tests/test_e2e_app_workflow.py`
**Status:** Proposed

## ADDED Requirements

### Requirement: User can complete full search-to-playback workflow

**Scenario: User searches, selects episode, and watches video**
1. User selects "🔍 Buscar Anime" from main menu
2. User enters search query "Dandadan"
3. Scraper results show anime from 2+ sources
4. User selects first result "Dandadan"
5. Episode menu shows 12 episodes
6. User selects "Episódio 1"
7. Video URL is extracted (mocked)
8. MPV launches and plays (mocked, returns exit code 0)
9. Playback prompt: "Did you watch until the end?"
10. User confirms with "Sim"
11. History is saved with timestamp, episode, and source
12. User returns to main menu

**Validation Tests:**
- `test_search_dandadan_watch_episode_1()` - Complete workflow success
- `test_search_saves_to_history()` - History entry created correctly
- `test_episode_selection_shows_all()` - All episodes visible

**Related:**
- `test_scraper_search.py::TestMultiSourceSearchExecution`
- `test_mpv_playback.py::TestPlaybackFallback`

---

### Requirement: User can continue watching from history

**Scenario: User resumes watching from saved progress**
1. User selects "▶️  Continuar Assistindo" from main menu
2. History loads, shows: "Dandadan (Episódio 5)"
3. User can select:
   - ◀️  Episódio 4 (previous)
   - ▶️  Episódio 5 (current)
   - ⏭️  Episódio 6 (next)
4. User selects episode 5
5. Scraper loads that anime's episodes
6. Playback continues from that episode
7. Progress saved after watching

**Validation Tests:**
- `test_continue_watching_loads_history()` - History deserializes correctly
- `test_continue_watching_episode_offset_options()` - -1/0/+1 menu shown
- `test_continue_watching_updates_history()` - New episode saved

**Related:**
- `test_history_service.py` (existing)
- `core/history_service.py::load_history()`

---

### Requirement: App handles search with no results gracefully

**Scenario: User searches for anime that doesn't exist**
1. User searches for "xyzabc123nonexistent"
2. All scrapers execute in parallel
3. No results found (all return empty)
4. Error message: "❌ 'xyzabc123nonexistent' não foi encontrado..."
5. User can:
   - 🔄 Tentar Novamente (retry with different search)
   - 🗑️  Remover (remove from history if applicable)
   - ← Voltar (go back to menu)

**Validation Tests:**
- `test_search_nonexistent_anime_error()` - Error shown
- `test_search_retry_option()` - Can retry with different query
- `test_search_returns_to_menu()` - Menu restored

**Related:**
- `test_e2e_search.py::TestE2EErrorRecovery` (existing)

---

### Requirement: User can handle multi-source anime with source selection

**Scenario: Anime available from multiple sources with different episode counts**
1. User searches "Dandadan"
2. Results show:
   - animefire: 12 episodes
   - animesonlinecc: 12 episodes (with Portuguese dubs)
3. Menu prompt: "Múltiplas fontes encontradas. Escolha uma:"
4. User selects "Dandadan [animefire, animesonlinecc]"
5. Episodes load from selected source
6. Selected source is remembered for next time

**Validation Tests:**
- `test_search_with_multiple_sources_user_chooses()` - Source menu shown
- `test_source_selection_sticky()` - Remembered for next watch

**Related:**
- `test_scraper_search.py::TestFuzzyDeduplication`
- `test_scraper_search.py::TestMultiSourceSearchExecution`

---

### Requirement: App handles network/API errors with retry

**Scenario: Scraper site is temporarily unavailable**
1. User initiates search
2. animefire scraper times out (network error)
3. animesonlinecc scraper succeeds
4. Error message: "⚠️  animefire times out (but animesonlinecc found results)"
5. Results displayed from available sources
6. User can proceed or retry failed source

**Validation Tests:**
- `test_scraper_timeout_fallback_to_others()` - Other sources used
- `test_network_error_message_shown()` - Error visible to user

**Related:**
- `test_scraper_search.py::TestMultiSourceSearchExecution::test_search_with_one_source_timeout`

---

## MODIFIED Requirements

None - this is a new capability with no existing requirements to modify.

---

## REMOVED Requirements

None - this is additive functionality.

---

## Cross-References

- **Depends on:** Scraper Search Tests, MPV Playback Tests (foundation)
- **Used by:** Manual testing workflows, user acceptance testing
- **Related specs:** Repository behavior, History management, AniList workflows
