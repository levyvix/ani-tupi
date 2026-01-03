# Design: Sequel Detection & Auto Status Promotion

## Context

ani-tupi integrates with AniList.co to track anime watch progress and manage watch lists. Currently, when users finish an anime season, they must manually search for and select the sequel, then manually change the status if the anime was in "Planning" status. This creates friction and reduces user engagement.

**Stakeholders:**
- Users who watch anime in seasonal order and want seamless continuation
- Users who maintain carefully curated "Planning" lists and want automatic status tracking
- AniList data integrity (progress should match user's actual viewing)

**Constraints:**
- Must not interrupt playback (non-blocking API calls)
- Must handle AniList API failures gracefully (don't interrupt viewing)
- Must work in both `anilist_anime_flow()` (AniList-sourced) and normal playback loop
- No new external dependencies

## Goals / Non-Goals

### Goals
- Enable seamless sequel continuation when last episode is watched
- Automatically promote anime from PLANNING to CURRENT when viewing starts
- Gracefully handle multiple sequels and missing sequels
- Maintain existing behavior when features don't apply

### Non-Goals
- Implement prequel detection (separate feature)
- Auto-skip opening/ending credits
- Implement rating/review system
- Change playback behavior or episode ordering

## Decisions

### Decision 1: Sequential API Calls vs Parallel

**Decision:** Sequential calls after episode confirmation

**Rationale:**
- Sequel query only happens when user confirms end of episode (rare event, ~1 per hour per user)
- Latency (~200ms) is acceptable in this context (user is already waiting for menu)
- Keep code simple and reduce error surface
- Avoid complex async error handling

**Alternative Considered:** Parallel with asyncio
- Pro: Faster (100ms saved)
- Con: Complex error handling, overkill for user-driven interactions

### Decision 2: Where to Hook - After update_progress() vs Before

**Decision:** Check status change BEFORE `update_progress()`, execute status change at same time as progress if needed

**Rationale:**
- User confirmation only happens once
- Grouping related operations (status + progress) reduces API calls
- Clear sequencing: is_in_list → check_planning → change_status → update_progress

**Alternative Considered:** Separate calls
- Pro: Decoupled logic
- Con: Extra API call, confusing message ordering

### Decision 3: GraphQL Method Design

**Decision:** Three separate methods with clear responsibilities

```
get_anime_relations() → All relations (ANIME type only)
get_sequels() → Filtered for SEQUEL type
get_media_list_entry() → User's current entry with status
```

**Rationale:**
- Single responsibility principle
- Reusable (get_anime_relations could support prequel detection)
- Testable in isolation
- Clear naming matches requirement hierarchy

**Alternative Considered:** Single method returning everything
- Pro: One API call
- Con: Less reusable, harder to test

### Decision 4: Silent Failures for API Errors

**Decision:** All new API methods return empty list/None on failure, no exceptions raised

**Rationale:**
- Matches existing AniList client pattern (e.g., `add_to_list()` returns bool)
- Never interrupts playback (non-blocking requirement)
- Users see feature gracefully skip rather than application crash
- Reduces support burden for flaky networks

**Alternative Considered:** Raise exceptions, handle in caller
- Pro: Explicit error handling
- Con: Risk of unhandled exceptions, interrupt playback

### Decision 5: Sequel Offer UX - Menu vs Automatic

**Decision:** Always show menu, never auto-continue

**Rationale:**
- Users may want to break and do something else
- Manual confirmation prevents accidental playback
- Respects user agency
- Matches existing "Did you watch until end?" pattern

**Alternative Considered:** Auto-play sequel without menu
- Pro: Maximum flow
- Con: Surprising behavior, no escape without killing app

### Decision 6: Multiple Sequels Handling

**Decision:** Show choice menu when multiple sequels exist

**Rationale:**
- Rare but possible (e.g., OVA + TV sequel)
- Consistent with existing anime selection UI
- Better UX than declining offer or picking arbitrarily

### Decision 7: Status Change Notification

**Decision:** Show notification only when status actually changes (PLANNING → CURRENT)

**Rationale:**
- Users expect silent behavior when anime already CURRENT
- Reduces message spam
- Makes important status change visible

**Alternative Considered:** Always show status update message
- Pro: Explicit feedback
- Con: Noisy, confuses users who already had anime in CURRENT

### Decision 8: Sequel Progress Initialization

**Decision:** Query existing progress via `get_media_list_entry()` when sequel is selected

**Rationale:**
- If user already watched Season 2 partially, resume from there
- Prevents re-watching already-seen episodes
- Respects user's existing progress in AniList

**Alternative Considered:** Always start from episode 1
- Pro: Simpler implementation
- Con: Forces re-watching, loses progress tracking

## Risks / Trade-offs

### Risk 1: Sequel Title Mismatch in Scrapers

**Risk:** Sequel exists in AniList but not found in scraper under exact title
- Example: "Attack on Titan: The Final Season" in AniList, "Shingeki no Kyojin 4" in scraper

**Mitigation:**
- Use fuzzy matching in scraper search (already exists in Repository)
- Show error message, let user search manually
- Monitor for common mismatches, add aliases if needed

**Trade-off:** Automated matching won't be 100% reliable; user fallback provided

### Risk 2: Multiple Episodes Released Between Sessions

**Risk:** Episode 1 of sequel has episode 2-5 released; user expects to resume from 1
- Example: User finished Season 1 on Monday, Season 2 dropped 5 episodes on Tuesday

**Mitigation:**
- Use scraper's episode count, not AniList's total
- Default to episode 1 if episode count differs significantly
- Current progress query still respects user's watched progress

**Trade-off:** Slight confusion if episode counts mismatch; acceptable (rare case)

### Risk 3: API Rate Limiting

**Risk:** Frequent calls to AniList could trigger rate limiting
- Expected frequency: ~1 sequel query per hour per user (low risk)

**Mitigation:**
- Queries are user-driven, not automatic
- AniList rate limit is per-user and generous for normal usage
- Add monitoring if this becomes issue

### Risk 4: Duplication in anilist_anime_flow and main()

**Risk:** Same logic in two places; maintenance burden if changes needed

**Mitigation:**
- Document in comments
- Create helper function for common logic (offer_sequel_and_continue)
- Refactor to single flow in future if needed

**Trade-off:** Code duplication accepted for now; trade-off for simplicity

## Migration Plan

### Deployment

1. **Backward Compatibility:** All changes are additive
   - Existing playback flow unchanged if not applicable
   - Features only trigger when specific conditions met (last episode, PLANNING status)

2. **Rollback:** Simple
   - Remove helper function call from playback loops
   - Optionally remove new methods from AniList client (unused after removal)

3. **User Visibility:**
   - Features are opt-in (require user confirmation)
   - No breaking changes to existing functionality
   - Safe to deploy without user communication needed

### Testing on Deployment

1. Manual testing checklist in tasks.md
2. No automated tests needed (existing pattern in project)
3. Monitor logs for new error conditions

## Open Questions

- Should we cache sequel information to avoid repeated queries if user restarts same anime?
  - *Decision defer to Phase 2*: Monitor usage patterns first
- Should "Prequel" detection be added at same time?
  - *Decision defer*: Separate feature, lower priority
- Should we support "Continue Franchise" (watch full saga)?
  - *Decision defer to Phase 2*: Feature expansion after v1 ships
