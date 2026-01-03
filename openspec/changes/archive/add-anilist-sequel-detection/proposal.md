# Change: Add AniList Sequel Detection & Auto Status Promotion

## Why

Users frequently watch entire seasons of anime and want to seamlessly continue with sequels when they finish. Additionally, when an anime is marked as "Planning" (plan to watch), users expect it to automatically move to "Watching" when they actually start watching it. These features improve the streaming experience by eliminating friction and keeping AniList synchronized with actual viewing behavior.

## What Changes

- **Sequel Detection:** When user finishes the last episode of an anime, system queries AniList for sequels and offers automatic continuation
- **Auto Status Promotion:** When user confirms watching an episode while anime is in "Planning" status, automatically promote to "CURRENT" (Watching)
- **New AniList Methods:** Add `get_anime_relations()`, `get_sequels()`, and `get_media_list_entry()` to GraphQL client
- **Enhanced Playback Flow:** Integration points in both `anilist_anime_flow()` and normal playback loop

## Impact

- **Affected specs:** anilist-integration (new capability)
- **Affected code:**
  - `/home/levi/ani-tupi/anilist.py` - Add 3 new GraphQL methods (~100 lines)
  - `/home/levi/ani-tupi/main.py` - Add sequel offer helper function + modify 2 playback loops (~80 lines)
- **Breaking changes:** None
- **Dependencies:** No new external dependencies (uses existing AniList GraphQL API)
- **Testing:** Manual testing checklist provided in tasks.md
