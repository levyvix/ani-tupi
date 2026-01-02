# Spec Delta: AniList Integration Tests

**Capability:** Comprehensive AniList API interaction testing
**Module:** `tests/test_anilist_integration.py`
**Status:** Proposed

## ADDED Requirements

### Requirement: User can authenticate with AniList via OAuth

**Scenario: User logs in to sync watch progress**
1. User selects "📺 AniList" from main menu
2. App checks for existing token in `~/.local/state/ani-tupi/anilist_token.json`
3. No token found → show OAuth login instructions
4. Browser opens: `https://anilist.co/api/v2/oauth/authorize?client_id=21576&response_type=token`
5. User authorizes ani-tupi
6. Browser redirects with token in URL: `https://anilist.co/api/v2/oauth/pin?access_token=...`
7. User copies token, pastes into terminal
8. Token validated with GraphQL query (get current user)
9. Token saved to disk
10. Trending anime loaded and displayed

**Validation Tests:**
- `test_oauth_flow_success()` - Token obtained and saved
- `test_oauth_invalid_credentials()` - Error handling
- `test_token_persists_between_sessions()` - Saved to disk

**Related:**
- `core/anilist_service.py::authenticate()`

---

### Requirement: App fetches and displays trending anime

**Scenario: User wants to see what's trending on AniList**
1. User selects "📺 AniList" from main menu
2. App queries AniList trending endpoint (if authenticated) or anonymous trending
3. Query returns: media list with 50 anime sorted by popularity
4. Each anime shows: Title, Score (0-100), Episode count
5. User can scroll through list or search by title
6. User selects anime to watch
7. App searches local scrapers for that anime

**Validation Tests:**
- `test_fetch_trending_anime()` - Get top 50 anime
- `test_trending_pagination()` - Next page available
- `test_trending_with_scores()` - Rating/popularity included
- `test_trending_network_timeout()` - Retry with backoff

**Related:**
- `core/anilist_service.py::get_trending()`
- `ui/anilist_menus.py`

---

### Requirement: Authenticated users can view personalized lists

**Scenario: User views their watch lists**
1. User authenticated with token
2. User selects "📺 AniList" → "Minha Lista"
3. App queries user's MediaListCollection
4. Shows: "Assistindo", "Planejamento", "Completado", etc.
5. User can filter by status:
   - **Assistindo (CURRENT):** Currently watching
   - **Planejamento (PLANNING):** Plan to watch
   - **Completado (COMPLETED):** Already watched
   - **Em Pausa (PAUSED):** Stopped/on hold
   - **Dropado (DROPPED):** Dropped

6. Each list shows anime with progress: "Dandadan (5/12)"
7. User can select anime to continue watching

**Validation Tests:**
- `test_get_watching_list()` - User's current list
- `test_get_planning_list()` - Plan to watch list
- `test_get_completed_list()` - Finished anime
- `test_list_progress_shown()` - Episode/episode total displayed

**Related:**
- `core/anilist_service.py::get_user_list()`

---

### Requirement: Progress syncs to AniList after episode playback

**Scenario: Watching episode updates AniList**
1. User selects anime from AniList list
2. Watches episodes 1-5
3. After each episode, app sends mutation to AniList
4. Mutation: `UpdateMediaListEntry(media_id, progress)`
5. AniList updates: "Dandadan (5/12)"
6. If episode count reaches total, status changes to "COMPLETED"
7. Local history also saved

**Validation Tests:**
- `test_sync_after_episode_watch()` - Auto-update after playback
- `test_sync_respects_max_episodes()` - Won't exceed total (12)
- `test_sync_updates_status_on_completion()` - COMPLETED when done
- `test_sync_network_error_silent_fail()` - Don't interrupt playback

**Related:**
- `core/anilist_service.py::update_progress()`
- `core/history_service.py::save_history()`

---

### Requirement: Conflict resolution between local and AniList progress

**Scenario: User's local history and AniList differ**
1. Local: Watched episode 5
2. AniList: Watched episode 8 (synced on different device)
3. User continues watching from last menu
4. App loads history → shows "Continuar Assistindo: Episódio 5"
5. User sees: "⚠️  AniList has you at episode 8"
6. User can:
   - ▶️ Continue from 5 (local)
   - ⏭️ Jump to 8 (AniList)
7. Choice saved to both systems

**Validation Tests:**
- `test_sync_conflict_detection()` - Different progress detected
- `test_sync_conflict_user_choice()` - User can choose source
- `test_sync_conflict_resolution_updates_both()` - Both systems updated

**Related:**
- `core/history_service.py::load_history()`

---

### Requirement: Error handling for AniList API failures

**Scenario: Network issues or API errors**
1. AniList API unreachable (timeout)
2. App shows: "⚠️  Não foi possível conectar ao AniList"
3. Offers options:
   - 🔄 Tentar Novamente (retry with backoff)
   - ← Voltar (use offline mode / fall back to local scrapers)
4. If retry, waits with exponential backoff (1s, 2s, 4s, 8s)
5. Max 3 retries before giving up

**Validation Tests:**
- `test_anilist_network_timeout()` - Timeout handling
- `test_anilist_api_error_response()` - Server error (5xx)
- `test_anilist_retry_backoff()` - Exponential backoff
- `test_anilist_offline_fallback()` - Graceful degradation

**Related:**
- `core/anilist_service.py` (error handling)

---

## MODIFIED Requirements

**Existing Requirement:** AniList support
- **Was:** "App may integrate with AniList for progress tracking"
- **Now:** "App shall integrate with AniList for authentication, list browsing, and progress syncing with conflict resolution and error recovery"
- **Impact:** AniList becomes core feature, not optional

---

## REMOVED Requirements

None.

---

## Cross-References

- **Foundation for:** Complete app feature (AniList browsing)
- **Uses:** httpx for API calls (mocked in tests)
- **Related:** History management, app workflow, progress sync
