# Proposal: MPV IPC Keybindings Integration

**Change ID:** `add-mpv-ipc-keybindings`
**Status:** Proposed
**Priority:** Medium
**Date:** 2026-01-03

---

## Why

**Problem:** Users cannot navigate episodes without restarting the menu after playback ends. Every video requires going through the search/episode menu again, creating friction in binge-watching scenarios.

**Impact:** Poor user experience for sequential episode watching. Users of similar apps (viu-media/viu) have come to expect in-player navigation.

**Opportunity:** Implement keybindings during MPV playback to enable seamless episode navigation, automatic watch history tracking, and user preference persistence (auto-play).

---

## Executive Summary

Enable custom keybindings during video playback in MPV to allow users to:
- Navigate episodes without closing the player (Shift+N/P for next/previous)
- Mark episodes as watched and jump to next (Shift+M)
- Toggle auto-play for next episode (Shift+A)
- Reload/retry current episode (Shift+R)
- Toggle subtitle/dub (Shift+T)

This integrates with ani-tupi's history service to automatically save watch progress based on keybinding actions, rather than only on normal playback completion.

---

## Problem Statement

**Current Behavior:**
- User watches an episode via `play_video()` which uses python-mpv blocking playback
- When user quits (via MPV's default 'q' key), the app only asks "Did you watch?" for confirmation
- No way to navigate to next/previous episode without restarting the menu
- Watch history only saved on normal completion, not on user actions within MPV

**Desired Behavior:**
- User can press Shift+N during playback to mark current episode as watched and jump to next
- User can press Shift+P to go to previous episode (resumes from where they were)
- User can press Shift+A to toggle auto-play (saves preference)
- All actions trigger ani-tupi's history service to persist progress
- Visual feedback in MPV console/OSD about actions taken

---

## Proposed Solution

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    ani-tupi Application                         │
│  (commands/anime.py → anime_service.py → utils/video_player.py)│
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│          VideoPlayerIPC (Enhanced video_player.py)              │
│  - Manages MPV process with IPC socket                          │
│  - Monitors keybinding events from MPV                          │
│  - Communicates episode data to MPV                             │
│  - Translates MPV events to ani-tupi actions                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    IPC Socket (Unix/Windows)
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MPV Media Player                           │
│  - Loads input.conf with custom keybindings                     │
│  - Reports events via JSON-RPC protocol                         │
│  - Displays OSD messages from ani-tupi                          │
│  - Renders video playback                                       │
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

1. **VideoPlayerIPC** (`utils/video_player.py` refactored)
   - Replace `play_video()` with IPC-aware version
   - Establish MPV IPC socket before playback
   - Monitor socket for events (Shift+N, Shift+M, etc.)
   - Return episode navigation data along with exit code

2. **MPV Configuration** (auto-generated)
   - Create temporary MPV input.conf with custom bindings
   - Register commands like `mark-watched-next`, `previous-episode`, etc.
   - Send events back to ani-tupi via IPC

3. **Episode Context Passing**
   - Pass episode metadata to MPV (current ep #, total eps, anime title)
   - Store in MPV user properties accessible to input.conf
   - Used by OSD messages: "Marked watched, next: Ep 42 of 50"

4. **History Integration**
   - Episode navigation actions trigger `save_history()` calls
   - Auto-save on Shift+M (mark watched and next)
   - Resume from saved position on Shift+P (previous)
   - Persist auto-play preference in history.json metadata

---

## Scope & Deliverables

### Capability 1: MPV IPC Socket Integration
- Establish secure IPC communication with MPV process
- Support both Unix socket (Linux/macOS) and named pipes (Windows)
- Graceful fallback if IPC unavailable (use old play_video behavior)

### Capability 2: Custom Keybindings
- Implement Shift+N (next episode) - marks watched, moves to next
- Implement Shift+P (previous episode) - resumes from saved position
- Implement Shift+M (mark watched, ask next/continue/quit) - explicit control
- Implement Shift+R (reload current) - retry same episode
- Implement Shift+A (toggle auto-play) - skip episode selection for next
- Implement Shift+T (toggle sub/dub) - if source supports switching

### Capability 3: Visual Feedback
- Display OSD messages during keybinding actions
- Show confirmation: "Marked as watched. Loading Ep 42..."
- Show error if navigation fails: "No next episode available"
- Brief status display: "Auto-play: ON/OFF"

### Capability 4: History Persistence
- Save watch progress when user triggers Shift+M or Shift+N
- Preserve auto-play preference in settings
- Track source per episode (which scraper it came from)
- Support for resuming from middle of previous episode

---

## Technical Details

### Keybinding Map

| Binding | Action | Effect | History |
|---------|--------|--------|---------|
| Shift+N | Next | Mark watched, load next ep | Save to history |
| Shift+P | Previous | Resume from saved position | Load from history |
| Shift+M | Mark & Menu | Mark watched, show menu (next/continue/quit) | Save to history |
| Shift+R | Reload | Retry current ep URL | No history change |
| Shift+A | Auto-play | Toggle auto next ep on completion | Save preference |
| Shift+T | Toggle | Switch sub/dub if available | No history change |

### IPC Command Format

Commands sent from MPV to ani-tupi:
```json
{
  "command": "episode-navigation",
  "action": "next",
  "anime_title": "Dandadan",
  "current_episode": 3,
  "total_episodes": 50,
  "source": "animefire"
}
```

Responses from ani-tupi to MPV (via OSD):
```json
{
  "osd_message": "Marked watched. Loading Ep 4 of 50...",
  "next_episode_url": "https://...",
  "next_episode_title": "Ep 4: Title"
}
```

### Configuration Files

**MPV input.conf template** (`~/.config/mpv/input.conf` or runtime override):
```
shift+n show-text "Next Episode" ; script-message mark-next
shift+p show-text "Previous Episode" ; script-message previous
shift+m show-text "Mark Watched" ; script-message mark-menu
shift+r show-text "Reload" ; script-message reload-episode
shift+a show-text "Toggle Auto-play" ; script-message toggle-autoplay
shift+t show-text "Toggle Sub/Dub" ; script-message toggle-sub-dub
```

---

## Dependencies

- **python-mpv-jsonipc** (new dependency)
  - Provides JSON-RPC IPC client for external MPV control
  - Alternative to python-mpv's C API for better stability

- **pyzmq** (optional, for advanced IPC scenarios)
  - Would allow ZMQ socket communication if needed later

---

## Breaking Changes

- `play_video()` return type remains `int` (exit code) but behavior changes
  - Exit codes now include navigation events (future enum expansion)
  - Callers must handle new metadata in `VideoPlaybackResult` named tuple

- Configuration: May require user to update `~/.config/mpv/input.conf` if they have custom bindings

---

## Testing Strategy

### Unit Tests
- Mock IPC socket communication
- Test keybinding-to-action mapping
- Test history save/load with navigation events
- Test OSD message formatting

### Integration Tests
- Real MPV process with test socket
- Full episode navigation flow: next → previous → history
- Auto-play preference persistence
- Error handling (no next episode, network failure on URL retrieval)

### E2E Tests
- Full user workflow: search → select anime → play → Shift+N → next episode → play
- Verify history.json contains navigation metadata
- Test fallback to old behavior if IPC unavailable

---

## Rollback Plan

If IPC implementation causes issues:
1. Set environment variable `ANI_TUPI_DISABLE_IPC=1`
2. Falls back to original `play_video()` blocking behavior
3. No history structure changes (backward compatible)

---

## Success Criteria

- [x] User can press Shift+N and next episode loads without restarting menu
- [x] Watch history correctly saves Shift+N actions
- [x] Auto-play preference persists across sessions
- [x] OSD messages provide visual feedback
- [x] Works on Linux (Unix socket), macOS, and Windows (named pipes)
- [x] Graceful fallback if MPV doesn't support IPC
- [x] Tests pass with >80% coverage for new code

---

## References

- **Related Proposals:** None (new feature)
- **Related Code:**
  - `utils/video_player.py` (current implementation)
  - `services/anime_service.py` (playback orchestration)
  - `services/history_service.py` (history persistence)
- **External References:**
  - [python-mpv-jsonipc](https://github.com/iwalton3/python-mpv-jsonipc)
  - [MPV JSON IPC Docs](https://github.com/mpv-player/mpv/blob/master/DOCS/man/ipc.rst)
  - [viu-media/viu Implementation](https://github.com/viu-media/viu) - Reference implementation with similar feature
