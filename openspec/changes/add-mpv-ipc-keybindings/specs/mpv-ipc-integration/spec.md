# Spec Delta: MPV IPC Integration for Episode Navigation

**Capability:** Real-time episode navigation during video playback via MPV keybindings
**Module:** `utils/video_player.py`, `services/anime_service.py`, `services/history_service.py`
**Status:** Proposed

---

## ADDED Requirements

### Requirement: App SHALL establish JSON IPC connection with MPV before playback

The app SHALL create a JSON-RPC IPC socket and establish bidirectional communication with MPV to enable keybinding event handling.

#### Scenario: User launches episode playback with IPC enabled

1. User selects an episode to watch
2. `play_episode()` function is called with episode metadata
3. App generates platform-specific socket path (`/tmp/ani-tupi-mpv-*.sock` on Linux, `\\.\pipe\ani-tupi-mpv-*` on Windows)
4. App creates temporary MPV input.conf with custom keybindings
5. MPV process launches with `--input-ipc-server={socket_path}` flag
6. MPVClient connects to socket within 2 seconds
7. IPC event loop begins listening for messages from MPV
8. Video playback starts with custom keybindings available

**Validation Tests:**
- `test_ipc_socket_created_on_linux()` - Socket file exists and is writable
- `test_ipc_socket_created_on_windows()` - Named pipe created correctly
- `test_mpv_process_launches_with_ipc_flag()` - Process started with correct arguments
- `test_ipc_connection_timeout_fallback()` - Falls back to legacy if socket unavailable
- `test_socket_cleanup_on_exit()` - Temporary socket removed after playback

**Related:**
- `utils/video_player.py::_create_ipc_socket_path()`
- `utils/video_player.py::_generate_input_conf()`
- `utils/video_player.py::_launch_mpv_with_ipc()`
- `utils/video_player.py::play_episode()`

---

### Requirement: App SHALL receive and parse keybinding events from MPV

The app SHALL listen for JSON IPC messages from MPV and parse keybinding events to trigger appropriate handlers.

#### Scenario: User presses custom keybinding and app detects it

1. MPV is playing video with IPC connection active
2. User presses Shift+N (or other registered keybinding)
3. MPV's input.conf has binding: `shift+n script-message mark-next`
4. MPV sends JSON message via IPC socket: `{"event": "client-message", "args": ["mark-next"]}`
5. App listens on socket with timeout (1 second)
6. App receives message, parses JSON
7. App extracts action name from `args[0]`
8. App calls handler for that action (e.g., `_on_mark_next()`)

**Validation Tests:**
- `test_receive_keybinding_shift_n()` - Message received and parsed as "mark-next"
- `test_receive_keybinding_all_six()` - All keybindings (N/P/M/R/A/T) work
- `test_parse_json_ipc_message_format()` - JSON parsed correctly
- `test_malformed_message_logged_ignored()` - Invalid JSON doesn't crash
- `test_socket_timeout_handled()` - Timeout doesn't block forever

**Related:**
- `utils/video_player.py::_ipc_event_loop()`
- `utils/video_player.py::_handle_keybinding_action()`

---

### Requirement: App handle Shift+N to mark episode watched and jump to next


The app SHALL handle Shift+N keybinding to save current episode as watched and automatically load the next episode.

#### Scenario: User presses Shift+N to mark current as watched and load next episode

1. User is watching "Dandadan" Episode 3 (of 50)
2. Episode 4 URL is available in repository
3. User presses Shift+N during playback
4. MPV sends `client-message mark-next` via IPC
5. App calls handler `_on_mark_next()`
6. Handler calls `save_history_from_event("Dandadan", episode_idx=3, action="watched", source="animefire")`
7. History is saved with timestamp
8. Handler calls `get_episode_url("Dandadan", 4)` to get next episode URL
9. App sends MPV command: `{"command": "loadfile", "args": ["https://stream.url/ep4.m3u8"]}`
10. MPV loads and plays episode 4
11. App continues listening for more keybindings
12. When video ends or user quits, app returns `VideoPlaybackResult(exit_code=0, action="next", data={"episode": 4})`

**Error Cases:**
- No next episode exists (episode 50 is last):
  - Show OSD: "No more episodes"
  - Return `VideoPlaybackResult(exit_code=0, action="quit", data=None)`
- Episode URL fetch fails:
  - Show OSD: "Error loading episode 4"
  - Pause video, wait for Shift+R (reload) or user closes

**Validation Tests:**
- `test_shift_n_saves_history_with_episode_3()` - History persisted correctly
- `test_shift_n_loads_episode_4()` - Next episode URL fetched and loaded
- `test_shift_n_on_last_episode_50()` - Shows "no more episodes", exits cleanly
- `test_shift_n_url_fetch_fails_shows_error()` - Error OSD shown, doesn't crash
- `test_shift_n_returns_correct_result()` - VideoPlaybackResult has action="next"

**Related:**
- `utils/video_player.py::_on_mark_next()`
- `services/history_service.py::save_history_from_event()`
- `services/repository.py::get_episode_url()`

---

### Requirement: App handle Shift+P to resume previous episode


The app SHALL handle Shift+P keybinding to load and resume playback of the previous episode.

#### Scenario: User presses Shift+P to go back to previous episode

1. User is watching episode 4
2. Episode 3 was previously watched (in history)
3. User presses Shift+P during playback
4. MPV sends `client-message previous` via IPC
5. App calls handler `_on_previous()`
6. Handler checks: `episode_number - 1 >= 1` (not less than 1)
7. Handler calls `get_episode_url("Dandadan", 3)`
8. Episode 3 URL retrieved from repository
9. App sends MPV command: `{"command": "loadfile", "args": [ep3_url]}`
10. MPV loads episode 3
11. Episode context updates to episode 3
12. User can press Shift+N to go forward to episode 4 again

**Error Cases:**
- User is on episode 1:
  - Show OSD: "No previous episode"
  - Continue current playback
- Episode URL fetch fails:
  - Show OSD: "Error loading episode 3"
  - No action, continue current

**Validation Tests:**
- `test_shift_p_on_episode_4_goes_to_3()` - Episode 3 loads
- `test_shift_p_on_episode_1_shows_error()` - "No previous" message shown
- `test_shift_p_multiple_times_episode_4_2_3()` - Can navigate back multiple times
- `test_shift_p_url_matches_previous()` - Correct episode URL loaded

**Related:**
- `utils/video_player.py::_on_previous()`
- `services/repository.py::get_episode_url()`

---

### Requirement: App handle Shift+M for explicit mark with menu


The app SHALL handle Shift+M keybinding to mark current episode as watched and show a menu for user selection.

#### Scenario: User presses Shift+M to mark episode as watched with menu confirmation

1. User is watching episode 3
2. User presses Shift+M
3. MPV sends `client-message mark-menu` via IPC
4. App calls handler `_on_mark_menu()`
5. Handler calls `save_history("Dandadan", episode_idx=3, ...)`
6. Episode 3 saved to history
7. Handler returns `VideoPlaybackResult(action="mark-menu", ...)`
8. App detects action="mark-menu" and shows menu with options:
   - ⏭️  Next Episode (→ load ep 4)
   - ▶️  Continue Watching (→ resume ep 3)
   - ← Go Back (→ return to main menu)
   - ⏹️  Quit (→ exit)
9. User selects option
10. App takes action (navigate or quit)

**Validation Tests:**
- `test_shift_m_saves_episode_to_history()` - History persisted
- `test_shift_m_returns_menu_action()` - Result indicates menu
- `test_shift_m_next_option_loads_ep4()` - Next selection works
- `test_shift_m_continue_option_resumes()` - Continue option works

**Related:**
- `utils/video_player.py::_on_mark_menu()`
- `services/history_service.py::save_history_from_event()`

---

### Requirement: App handle Shift+A to toggle auto-play preference


The app SHALL handle Shift+A keybinding to toggle the auto-play setting, which determines whether to automatically load the next episode after completion.

#### Scenario: User presses Shift+A to enable auto-play for next episodes

1. User starts watching episode 1
2. Auto-play is currently OFF
3. User presses Shift+A
4. MPV sends `client-message toggle-autoplay` via IPC
5. App calls handler `_on_toggle_autoplay()`
6. Handler reads current preference (OFF)
7. Handler toggles to ON
8. Handler saves new preference: `save_history_from_event(..., auto_play=True)`
9. App shows OSD: "Auto-play: ON"
10. When episode 1 finishes (normal exit, no user quit), instead of asking confirmation:
    - App automatically loads episode 2
    - No menu shown
    - Playback continues
11. User can press Shift+A again to turn off auto-play

**Validation Tests:**
- `test_shift_a_toggles_off_to_on()` - Preference changes to ON
- `test_shift_a_toggles_on_to_off()` - Preference changes to OFF
- `test_shift_a_preference_persisted_in_history()` - Setting saved
- `test_autoplay_enabled_skips_confirmation_menu()` - Next episode loads automatically
- `test_autoplay_disabled_shows_confirmation()` - Menu appears when OFF

**Related:**
- `utils/video_player.py::_on_toggle_autoplay()`
- `services/history_service.py::save_history_from_event()`
- `services/anime_service.py` (auto-play handler)

---

### Requirement: App handle Shift+R to reload/retry current episode


The app SHALL handle Shift+R keybinding to reload the current episode from the beginning.

#### Scenario: User presses Shift+R to replay current episode from start

1. User is watching episode 3
2. Buffering issue occurs or user wants to restart
3. User presses Shift+R
4. MPV sends `client-message reload-episode` via IPC
5. App calls handler `_on_reload()`
6. Handler gets current episode URL from context
7. Handler sends MPV command: `{"command": "loadfile", "args": [current_url, "replace"]}`
8. MPV reloads same video URL from start (position resets to 0)
9. Episode context remains unchanged (still episode 3)
10. History is NOT updated (no new watch progress made)

**Validation Tests:**
- `test_shift_r_reloads_same_url()` - Same URL loaded
- `test_shift_r_seeks_to_start()` - Video starts from 0
- `test_shift_r_no_history_change()` - History metadata unchanged
- `test_shift_r_clears_cache()` - Buffering issues cleared by reload

**Related:**
- `utils/video_player.py::_on_reload()`

---

### Requirement: App handle Shift+T for subtitle/dub toggle


The app SHALL handle Shift+T keybinding to cycle audio tracks or switch between dubbed and subtitled versions when available.

#### Scenario: User presses Shift+T to switch audio track

1. User is watching episode 3 (with audio track available)
2. User presses Shift+T
3. MPV sends `client-message toggle-sub-dub` via IPC
4. App calls handler `_on_toggle_sub_dub()`
5. Handler attempts to cycle audio track using MPV command: `{"command": "cycle", "args": ["audio"]}`
6. If source provides multiple URL variants (dub/sub), handler can optionally fetch new URL
7. MPV cycles to next available audio track
8. App shows OSD: "Audio track switched"
9. Playback continues with new audio

**Notes:**
- Basic implementation: Just cycle audio with MPV `cycle audio` command
- Advanced implementation (future): Support multiple URL variants per source
- Some sources may only have single audio track (graceful degradation)

**Validation Tests:**
- `test_shift_t_cycles_audio_track()` - Audio stream changed
- `test_shift_t_shows_osd_feedback()` - User sees confirmation
- `test_shift_t_single_track_source_no_op()` - Graceful fallback
- `test_shift_t_multiple_tracks_work()` - Can cycle between 2+ tracks

**Related:**
- `utils/video_player.py::_on_toggle_sub_dub()`

---

## MODIFIED Requirements

### Requirement: Playback function returns navigation data


The app SHALL return navigation metadata from the playback function to allow callers to respond to user keybinding actions.

#### Scenario: Caller receives navigation actions from playback function

**Was:**
- Function `play_video()` returns only `int` (exit code 0/2/3)
- Caller knows if playback succeeded but not what user did during playback
- No way to respond to user keybinding actions

**Now:**
- Function `play_episode()` returns `VideoPlaybackResult` NamedTuple:
  ```python
  VideoPlaybackResult(
      exit_code: int,       # 0=normal, 2=error, 3=user abort
      action: str,          # "quit", "next", "previous", "reload", "mark-menu"
      data: dict | None     # {"url": "...", "episode": 4, "title": "Ep 4: ..."}
  )
  ```
- Caller can respond to `action` field to navigate episodes or show menus
- Example in anime_service.py:
  ```python
  result = play_episode(...)
  if result.action == "next":
      episode_idx = result.data["episode"]  # Jump to episode 4
  ```

**Impact:**
- `anime_service.py` must handle new `VideoPlaybackResult` type
- Backward compat: Old `play_video()` wrapper keeps returning `int`
- No breaking changes to callers not using IPC features

**Validation Tests:**
- `test_play_episode_returns_video_playback_result()` - Type is correct
- `test_play_episode_action_is_quit()` - Normal exit has action="quit"
- `test_play_episode_action_is_next()` - Shift+N press has action="next"
- `test_play_episode_data_contains_next_url()` - Navigation data available
- `test_play_video_backward_compat_returns_int()` - Old function still works

**Related:**
- `utils/video_player.py::play_episode()`
- `utils/video_player.py::play_video()` (backward compat)
- `services/anime_service.py` (caller)

---

### Requirement: History service saves event-triggered progress


The app SHALL save watch history when triggered by keybinding events during playback, with extended metadata about action type and source.

#### Scenario: IPC event handlers save watch progress during keybinding actions

**Was:**
- Function `save_history(anime_title, episode_idx)` saves only basic data
- Only called after playback completes (from playback menu)
- No metadata about how/why episode was marked
- Single call per episode

**Now:**
- New function `save_history_from_event()` with extended parameters:
  ```python
  save_history_from_event(
      anime_title: str,
      episode_idx: int,
      action: str = "watched",    # "watched" | "started" | "skipped"
      source: str | None = None,  # "animefire", "animesonlinecc", etc
      auto_play: bool | None = None
  )
  ```
- Called directly from IPC event handlers (Shift+N, Shift+M, etc.)
- Can be called multiple times per session (different episodes)
- History can track action type and source per episode
- Optional v6 format extends JSON schema (backward compatible)

**Optional v6 History Format:**
```json
{
  "Dandadan": {
    "timestamp": 1704192000,
    "episode_idx": 5,
    "anilist_id": 12345,
    "source": "animefire",
    "action": "watched",
    "auto_play": true,
    "total_episodes": 50
  }
}
```

**Backward Compatibility:**
- Old v5 array format still supported for reading
- New function creates new format on first save
- Migration happens transparently on load

**Validation Tests:**
- `test_save_history_from_event_stores_action()` - Action type saved
- `test_save_history_from_event_stores_source()` - Scraper name saved
- `test_save_history_from_event_backward_compatible()` - Old v5 loads correctly
- `test_history_migration_v5_to_v6()` - Format upgrades transparently
- `test_multiple_history_events_per_session()` - Multiple saves work

**Related:**
- `services/history_service.py::save_history_from_event()`
- `services/history_service.py::save_history()` (existing)

---

## REMOVED Requirements

None. All existing requirements remain in effect.

---

## Notes for Implementers

1. **IPC Stability:** Test graceful fallback if socket unavailable
2. **Platform Differences:** Unix socket (Linux/macOS) vs named pipe (Windows)
3. **Timeout Handling:** Use 1-2 second timeout on socket reads, don't block forever
4. **Process Management:** Ensure MPV subprocess terminated properly on app exit
5. **Resource Cleanup:** Always remove temporary socket files/pipes
6. **Testing:** Mock MPV/socket in unit tests, use real process in integration tests
7. **Logging:** Log IPC events at DEBUG level for troubleshooting
