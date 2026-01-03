# Implementation Tasks

## 1. AniList GraphQL Client Extensions (`anilist.py`)

- [ ] 1.1 Add `get_anime_relations(anime_id)` method
  - GraphQL query for Media.relations with relationType filtering
  - Return list of relation edges with node metadata
  - Handle API failures silently (return empty list)

- [ ] 1.2 Add `get_sequels(anime_id)` method
  - Call `get_anime_relations()` and filter for SEQUEL type
  - Return filtered list of sequel nodes

- [ ] 1.3 Add `get_media_list_entry(anime_id)` method
  - Query MediaList entry with: id, status, progress, score, dates
  - Return None if not in list or not authenticated
  - Handle API failures silently (return None)

- [ ] 1.4 Validate new methods with `openspec validate add-anilist-sequel-detection --strict`

## 2. Sequel Detection Helper Function (`main.py`)

- [ ] 2.1 Add `offer_sequel_and_continue()` function after line 106
  - Accepts: anilist_id, current_anime, args
  - Call `anilist_client.get_sequels(anilist_id)`
  - If no sequels: return False
  - If one sequel: show confirmation menu "Continuar com [Title]?"
  - If multiple sequels: show choice menu
  - If user accepts:
    - Get sequel's current progress via `get_media_list_entry()`
    - Call `anilist_anime_flow()` with sequel ID
    - Return True

- [ ] 2.2 Test helper function in debug mode
  - `uv run main.py --debug` with anime that has sequel

## 3. Integrate Sequel Detection into AniList Flow (`main.py`)

- [ ] 3.1 Modify `anilist_anime_flow()` completion block (lines 365-376)
  - After `update_progress()` call
  - Check if `episode == num_episodes` (last episode)
  - Call `offer_sequel_and_continue(anilist_id, selected_anime, args)`
  - If returns True: exit loop (sequel started)

- [ ] 3.2 Test integration
  - Watch last episode of anime with known sequel
  - Verify sequel offer appears
  - Accept and verify scraper search works

## 4. Integrate Status Change into AniList Flow (`main.py`)

- [ ] 4.1 Modify `anilist_anime_flow()` completion block (same lines 365-376)
  - Before `update_progress()` call
  - Call `anilist_client.get_media_list_entry(anilist_id)`
  - Check if status is "PLANNING"
  - If yes: call `anilist_client.add_to_list(anilist_id, "CURRENT")`
  - Show message: "📝 Movendo de 'Planejo Assistir' para 'Assistindo'..."

- [ ] 4.2 Test status change
  - Add anime to PLANNING on AniList website
  - Watch episode 1 in ani-tupi
  - Confirm completion
  - Verify status changed on AniList website

## 5. Integrate Sequel Detection into Normal Flow (`main.py`)

- [ ] 5.1 Modify normal playback loop completion block (lines 517-528)
  - Same changes as steps 3 and 4
  - Integrate both sequel detection and status change

- [ ] 5.2 Test in normal flow context
  - Search anime directly (not from AniList menu)
  - Watch last episode
  - Verify sequel offer works

## 6. Integration Testing

- [ ] 6.1 Test Sequel Detection with multiple sources
  - [ ] Anime with single sequel
  - [ ] Anime with multiple sequels (choice menu)
  - [ ] Anime with no sequel (silent skip)
  - [ ] Sequel not found in scrapers (error handling)

- [ ] 6.2 Test Status Promotion
  - [ ] Anime in PLANNING → CURRENT
  - [ ] Anime already CURRENT (no change)
  - [ ] Anime not in list (auto-add)

- [ ] 6.3 Test Combined Flow
  - [ ] Add Season 2 to PLANNING
  - [ ] Watch Season 1 last episode
  - [ ] Accept sequel offer
  - [ ] Watch Season 2 episode 1
  - [ ] Verify Season 2 status changed to CURRENT

- [ ] 6.4 Test Error Handling
  - [ ] AniList API failures (non-blocking)
  - [ ] Network disconnected (graceful failure)
  - [ ] Invalid anime ID (silent skip)

- [ ] 6.5 Edge Cases
  - [ ] User already watching sequel (resume from current progress)
  - [ ] Sequel selection with multiple options
  - [ ] User declines sequel (returns to normal menu)

## 7. Code Review & Cleanup

- [ ] 7.1 Verify code style follows conventions
- [ ] 7.2 Check for proper error handling (no unhandled exceptions)
- [ ] 7.3 Verify messages are in Portuguese
- [ ] 7.4 Check imports are properly added
- [ ] 7.5 Ensure no breaking changes to existing functions

## 8. Documentation

- [ ] 8.1 Update CLAUDE.md if needed with any workarounds discovered
- [ ] 8.2 Add comment explaining sequel detection flow in main.py
