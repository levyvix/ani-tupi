## ADDED Requirements

### Requirement: Query Anime Relations via GraphQL

The system SHALL provide a method to retrieve related anime (sequels, prequels, spin-offs, etc.) from AniList GraphQL API for a given anime ID.

#### Scenario: Retrieve sequel relationships successfully
- **WHEN** user finishes watching an anime and system queries for relations
- **THEN** return list of related anime with `relationType` and metadata (id, title, episodes, score)

#### Scenario: Handle API failures gracefully
- **WHEN** AniList GraphQL API fails or returns no relations
- **THEN** return empty list without raising exception (silent failure)

#### Scenario: Filter to anime type only
- **WHEN** relations include both ANIME and MANGA type relations
- **THEN** return only ANIME-type relations (exclude manga adaptations)

### Requirement: Filter Relations for Sequel Type

The system SHALL provide a method to extract only sequel-type relations from the full relations list.

#### Scenario: Identify single sequel
- **WHEN** anime has one direct sequel (relationType = "SEQUEL")
- **THEN** return list containing only that sequel with full metadata

#### Scenario: Identify multiple sequels
- **WHEN** anime has multiple sequels (e.g., both TV sequel and OVA)
- **THEN** return list of all sequels for user selection

#### Scenario: Handle no sequels
- **WHEN** anime has no sequels
- **THEN** return empty list

### Requirement: Retrieve User's Anime List Entry

The system SHALL provide a method to retrieve a user's current list entry for a specific anime, including status and progress.

#### Scenario: Get entry for anime in user's list
- **WHEN** anime exists in user's AniList (any status: CURRENT, PLANNING, COMPLETED, etc.)
- **THEN** return entry with: id, status, progress, score, dates

#### Scenario: Handle anime not in user's list
- **WHEN** anime is not in any of user's lists
- **THEN** return None

#### Scenario: Require authentication
- **WHEN** user is not authenticated with AniList
- **THEN** return None without raising exception

### Requirement: Offer Sequel Continuation After Episode Completion

The system SHALL offer to continue watching a sequel when user confirms watching the last episode of an anime.

#### Scenario: Single sequel available and accepted
- **WHEN** user finishes last episode of anime with one sequel
- **WHEN** system queries for sequels and finds exactly one
- **WHEN** user confirms "Yes, continue with sequel"
- **THEN** search sequel in available scrapers
- **THEN** start playback of sequel from episode 1 (or current progress if already watching)

#### Scenario: Multiple sequels available
- **WHEN** anime has multiple sequels (rare but possible)
- **THEN** show menu to let user choose which sequel to continue with

#### Scenario: User declines sequel offer
- **WHEN** user selects "No, return to menu"
- **THEN** return to normal playback navigation menu

#### Scenario: No sequel available
- **WHEN** anime has no sequels
- **THEN** skip sequel offer, proceed to normal navigation menu

#### Scenario: Sequel not found in scrapers
- **WHEN** sequel exists in AniList but not available in any scraper
- **THEN** show message "Sequência não encontrada nos scrapers"
- **THEN** return to navigation menu

### Requirement: Automatically Promote Anime from Planning to Watching

The system SHALL automatically change an anime's AniList status from "PLANNING" to "CURRENT" when user confirms watching an episode.

#### Scenario: Anime in PLANNING status when watching first episode
- **WHEN** anime is in user's PLANNING list
- **WHEN** user confirms watching any episode until the end
- **THEN** automatically change status to CURRENT (Watching)
- **THEN** show notification: "📝 Movendo de 'Planejo Assistir' para 'Assistindo'..."

#### Scenario: Anime already in CURRENT status
- **WHEN** anime is already in CURRENT (Watching) status
- **THEN** skip status change, proceed with progress update only

#### Scenario: Anime not in any list yet
- **WHEN** anime is not in user's lists (existing behavior)
- **THEN** auto-add to CURRENT list (no status change needed)

#### Scenario: Sequel already in PLANNING, user accepts sequel
- **WHEN** user finishes Season 1
- **WHEN** user accepts sequel offer (Season 2 in PLANNING)
- **WHEN** user watches and confirms Season 2 episode 1
- **THEN** Season 2 automatically promoted from PLANNING to CURRENT

#### Scenario: Status change fails silently
- **WHEN** AniList status change fails (API error)
- **THEN** show warning but continue with progress update
- **THEN** don't interrupt playback loop

## MODIFIED Requirements

### Requirement: Episode Completion Confirmation (Updated)

The system SHALL ask user to confirm if they watched an episode until the end, then synchronize progress with AniList.

**Modified:** Now includes automatic status change check before progress update.

The system SHALL:
1. Ask user confirmation: "Did you watch to the end?"
2. If confirmed:
   - Check if anime is in any list
   - If not in list: auto-add to CURRENT
   - **NEW:** Check if anime is in PLANNING status
   - **NEW:** If PLANNING: auto-promote to CURRENT
   - Update progress to current episode
3. If not confirmed: keep history but don't update AniList progress

#### Scenario: Episode completion with status promotion
- **WHEN** user confirms watching episode
- **WHEN** anime is in PLANNING status
- **THEN** change status to CURRENT
- **THEN** update progress
- **THEN** show both operations' results

#### Scenario: Episode completion without status change
- **WHEN** user confirms watching episode
- **WHEN** anime is already in CURRENT or not in any list
- **THEN** skip status change
- **THEN** update progress only
- **THEN** show progress update only
