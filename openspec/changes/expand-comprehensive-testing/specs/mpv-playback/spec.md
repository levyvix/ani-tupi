# Spec Delta: MPV Playback Error Handling Tests

**Capability:** Robust MPV exit code handling and fallback playback
**Module:** `tests/test_mpv_playback.py`
**Status:** Proposed

## ADDED Requirements

### Requirement: App interprets all MPV exit codes correctly

**Scenario: MPV returns various exit codes with different meanings**

| Exit Code | Meaning | App Behavior |
|-----------|---------|--------------|
| 0 | Normal completion (user quit with 'q') | Return to menu, ask "Did you watch?" |
| 1 | Generic error (invalid input, etc) | Show error, offer retry |
| 2 | File couldn't be played (yt-dlp failed) | **Fallback to VLC**, or suggest retry |
| 3 | User abort (Ctrl+C during playback) | Return to menu, don't count as watched |
| 4 | Command line parsing error | Log error, return to menu |

**Validation Tests:**
- `test_mpv_exit_code_0_success()` - Normal completion
- `test_mpv_exit_code_1_generic_error()` - Handled
- `test_mpv_exit_code_2_file_not_playable()` - Triggers fallback
- `test_mpv_exit_code_3_user_abort()` - No history save
- `test_mpv_exit_code_4_cmd_line_error()` - No crash

**Related:**
- `video_player.py::play_video()` (implementation)

---

### Requirement: Graceful error handling when video cannot be played

**Scenario: yt-dlp cannot extract video from URL**
1. MPV called with Blogger URL
2. yt-dlp tries to extract (fails)
3. MPV returns exit code 2
4. App detects failure: "⚠️  MPV falhou ao reproduzir este vídeo"
5. User shown options:
   - 🔄 Tentar Novamente (retry with same URL)
   - ⏭️  Próximo Episódio (skip to next episode)
   - ← Voltar (return to episode menu)

**Note:** VLC fallback removed (tested and found unreliable). User must choose manual action instead.

**Validation Tests:**
- `test_mpv_exit_code_2_error_message()` - Error shown to user
- `test_mpv_error_retry_option()` - Can retry same URL
- `test_mpv_error_skip_episode()` - Can skip to next

**Related:**
- `video_player.py::play_video()` (error code handling)

---

### Requirement: yt-dlp integration correctly handles video formats

**Scenario: yt-dlp extracts video in specified format**
1. Blogger URL passed to MPV
2. MPV invokes yt-dlp with format: `bestvideo[height<=1080]+bestaudio/best`
3. yt-dlp downloads best video (≤1080p) + best audio
4. Merges into playable file
5. MPV plays merged file

**Validation Tests:**
- `test_ytdl_format_string_correct()` - Format string validated
- `test_ytdl_concurrent_fragments_option()` - Parallel download enabled (fragments=5)
- `test_ytdl_timeout_handling()` - Network timeout behavior

**Related:**
- `video_player.py` (yt-dlp command construction)

---

### Requirement: History is saved appropriately based on exit code

**Scenario: History saved only for successful/partial views, not aborts**
1. User watches episode, quits normally with 'q' (exit 0) → Save history ✓
2. User watches episode, stops with Ctrl+C (exit 3) → Don't save ✓
3. User video fails (exit 2) → Don't save ✓
4. User confirms "Did you watch?" → Save with timestamp ✓

**Validation Tests:**
- `test_history_saved_on_successful_exit()` - Exit 0 + confirm → saved
- `test_history_not_saved_on_abort()` - Exit 3 → not saved
- `test_history_not_saved_on_playback_error()` - Exit 2 → not saved

**Related:**
- `core/history_service.py::save_history()`

---

## MODIFIED Requirements

**Existing Requirement:** Video playback functionality
- **Was:** "App shall play videos using MPV"
- **Now:** "App shall play videos using MPV with robust error handling and fallback to VLC"
- **Impact:** Exit codes must be interpreted; fallback mechanism required

---

## REMOVED Requirements

None.

---

## Cross-References

- **Foundation for:** App Workflow Tests (playback part)
- **Uses:** Mocked subprocess for exit code simulation
- **Related:** History saving behavior, error messaging
