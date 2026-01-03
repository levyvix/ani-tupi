# Design: MPV IPC Keybindings Integration

**Change ID:** `add-mpv-ipc-keybindings`
**Phase:** Detailed Design
**Author:** Claude Code
**Date:** 2026-01-03

---

## System Architecture

### 1. IPC Communication Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ anime_service.py                                                │
│ - Search anime                                                  │
│ - Select episode                                                │
│ - Prepare episode metadata (title, url, number, total)          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ VideoPlayerIPC.play_episode()                                   │
│ - Create MPV input.conf with custom bindings                    │
│ - Launch MPV with --input-ipc-server=<socket>                   │
│ - Pass episode metadata to MPV (via user properties)            │
│ - Initialize IPC client, connect to socket                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Event Loop (blocking)                                           │
│ - Listen on IPC socket for MPV events                           │
│ - Receive JSON: {"command": "shift+n", ...}                     │
│ - Parse event → call handler (next_episode, previous_etc)       │
│ - Handler calls anime_service for next ep or history_service    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Handler (on_next_episode, etc)                                  │
│ - Fetch next episode URL from repository                        │
│ - Call save_history() with new episode index                    │
│ - Send response to MPV (next URL, episode title, etc)           │
│ - MPV loads new URL via JSON command:                           │
│   {"command": "loadfile", "args": [url]}                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ MPV continues with next video                                   │
│ - User can press Shift+N again for next episode                 │
│ - Or press Shift+P to go back                                   │
│ - Or close window to exit                                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2. IPC Socket Setup

**Socket Location:**
- Linux/macOS: `/tmp/ani-tupi-mpv-{pid}.sock`
- Windows: `\\.\pipe\ani-tupi-mpv-{pid}`

**MPV Launch Parameters:**
```python
mpv_instance = subprocess.Popen([
    "mpv",
    video_url,
    f"--input-ipc-server={socket_path}",
    "--fullscreen=yes",
    "--osc=no",  # Disable on-screen controller, use custom OSD
    "--force-window=immediate",
    # ... other options
])
```

**Python IPC Client:**
```python
from python_mpv_jsonipc import MPVClient

client = MPVClient(socket_path="/tmp/ani-tupi-mpv-{pid}.sock")
# Send command:
client.call("loadfile", video_url)
# Listen for events:
for event in client.listen():
    if event["event"] == "client-message":
        handle_custom_command(event["args"])
```

---

## Implementation Details

### 3. Modified Functions

#### `utils/video_player.py`

**Current Implementation:**
```python
def play_video(url: str, debug=False, ytdl_format: str | None = None) -> int:
    """Play using python-mpv (blocking)."""
    player = mpv.MPV(fullscreen=True, input_default_bindings=True)
    player.play(url)
    player.wait_for_playback()
    return 0
```

**New Implementation:**
```python
def play_episode(
    url: str,
    anime_title: str,
    episode_number: int,
    total_episodes: int,
    source: str,
    use_ipc: bool = True,
    debug=False,
) -> VideoPlaybackResult:
    """
    Play episode with optional IPC keybindings.

    Returns:
        VideoPlaybackResult(exit_code, action, next_episode_index)
        - exit_code: 0=normal, 2=error, 3=user quit
        - action: "next", "previous", "retry", "quit", "auto-play"
        - next_episode_index: if action="next" or "auto-play", the index to load
    """
    if not use_ipc:
        return _play_video_legacy(url, debug)

    # Create temporary socket path
    socket_path = _create_ipc_socket_path()

    # Prepare episode metadata
    episode_context = {
        "anime_title": anime_title,
        "episode_number": episode_number,
        "total_episodes": total_episodes,
        "source": source,
        "current_url": url,
    }

    # Create custom input.conf
    input_conf = _generate_input_conf()

    try:
        # Launch MPV with IPC
        mpv_process = subprocess.Popen([
            "mpv",
            url,
            f"--input-ipc-server={socket_path}",
            f"--input-conf={input_conf}",
            "--fullscreen=yes",
            # ... other settings
        ])

        # Connect IPC client and start event loop
        return _ipc_event_loop(
            mpv_process,
            socket_path,
            episode_context
        )
    finally:
        if mpv_process.poll() is None:
            mpv_process.terminate()
        _cleanup_ipc_socket(socket_path)


def _ipc_event_loop(
    mpv_process,
    socket_path: str,
    episode_context: dict
) -> VideoPlaybackResult:
    """
    Listen for IPC events from MPV.

    Handles:
    - shift+n: Mark watched, next episode
    - shift+p: Previous episode (resume)
    - shift+m: Mark watched, show menu
    - shift+r: Reload episode
    - shift+a: Toggle auto-play
    - shift+t: Toggle sub/dub
    """
    client = MPVClient(socket_path=socket_path)

    while mpv_process.poll() is None:
        try:
            # Wait for events with timeout
            for event in client.listen(timeout=1.0):
                if event["event"] == "client-message":
                    action = event["args"][0]
                    result = _handle_keybinding_action(
                        action,
                        episode_context
                    )
                    if result:  # Action triggered navigation
                        return result
        except Exception as e:
            logger.warning(f"IPC error: {e}")
            break

    # MPV closed normally
    return VideoPlaybackResult(exit_code=0, action="quit", data=None)


def _handle_keybinding_action(action: str, context: dict) -> VideoPlaybackResult | None:
    """
    Process keybinding action from MPV.

    Returns None if action is handled but no navigation,
    or VideoPlaybackResult if should load new episode.
    """
    anime_title = context["anime_title"]
    ep_num = context["episode_number"]
    total_eps = context["total_episodes"]

    if action == "mark-next":
        # Mark current as watched, load next
        save_history(anime_title, ep_num, ...)
        if ep_num < total_eps:
            next_url = _get_episode_url(anime_title, ep_num + 1)
            return VideoPlaybackResult(
                exit_code=0,
                action="next",
                data={"url": next_url, "episode": ep_num + 1}
            )
        else:
            # Show OSD: no more episodes
            return VideoPlaybackResult(exit_code=0, action="quit", data=None)

    elif action == "previous":
        # Load previous episode from history
        prev_ep = ep_num - 1
        if prev_ep >= 1:
            prev_url = _get_episode_url(anime_title, prev_ep)
            return VideoPlaybackResult(
                exit_code=0,
                action="previous",
                data={"url": prev_url, "episode": prev_ep}
            )

    # Handle other actions...
    return None
```

**Return Type Change:**
```python
from typing import NamedTuple

class VideoPlaybackResult(NamedTuple):
    exit_code: int           # 0=normal, 2=error, 3=abort
    action: str              # "quit", "next", "previous", "retry"
    data: dict | None        # {"url": "...", "episode": 3, ...}
```

#### `services/anime_service.py`

**Current Code** (around line 300):
```python
# Play video
exit_code = play_video(player_url, args.debug)

# Check exit code...
if exit_code == 0:
    # Ask user: did you watch?
```

**New Code:**
```python
# Play episode with IPC support
result = play_episode(
    url=player_url,
    anime_title=anime_title,
    episode_number=episode_idx + 1,
    total_episodes=len(episodes),
    source=source_name,
    use_ipc=True,
)

# Handle result based on action
if result.action == "next":
    # Automatically jump to next episode
    episode_idx = result.data["episode"]
    player_url = result.data["url"]
    # Loop continues, plays next

elif result.action == "previous":
    # Jump to previous episode
    episode_idx = result.data["episode"]
    # ...

elif result.action == "quit":
    # Exit playback
    break
```

#### `services/history_service.py`

**New Function:**
```python
def save_history_from_event(
    anime_title: str,
    episode_idx: int,
    action: str = "watched",  # "watched", "started", "skipped"
    source: str | None = None,
) -> None:
    """
    Save history triggered by keybinding event.

    Called by IPC handler when user presses Shift+N/M/etc.
    Includes additional metadata about how episode was marked.
    """
    timestamp = int(time.time())
    anilist_id = get_anilist_id_for_anime(anime_title)

    # Update history with extended metadata
    history = _history_store.load({})
    if anime_title not in history:
        history[anime_title] = {}

    history[anime_title]["timestamp"] = timestamp
    history[anime_title]["episode_idx"] = episode_idx
    history[anime_title]["action"] = action  # NEW
    history[anime_title]["source"] = source  # NEW

    _history_store.save(history)
```

---

## Trade-offs & Design Decisions

### Decision 1: IPC Library Choice

**Options:**
1. **python-mpv-jsonipc** (chosen)
   - Pros: Pure Python, no C dependencies, JSON protocol well-documented
   - Cons: Less mature than python-mpv C API
   - Impact: Requires `uv add python-mpv-jsonipc`

2. **python-mpv** (current) with async subprocess
   - Pros: Already in dependencies
   - Cons: Not designed for background event monitoring while video plays
   - Impact: Would need hacky workaround with threading

3. **Custom JSON-RPC over raw socket**
   - Pros: No new dependencies
   - Cons: Reinvent wheel, error-prone
   - Impact: More development burden

**Decision:** Use python-mpv-jsonipc (good balance of simplicity and maturity)

---

### Decision 2: Fallback Strategy

**Options:**
1. **Graceful fallback** to legacy behavior if IPC unavailable
   - Pros: No user impact if IPC fails
   - Cons: Silent feature degradation
   - Implementation: Set `use_ipc=False` if socket creation fails

2. **Hard error** if IPC fails
   - Pros: Obvious to user if something is wrong
   - Cons: Annoying if MPV version doesn't support IPC

3. **Manual flag** to disable IPC
   - Pros: User has control
   - Cons: Requires configuration knowledge

**Decision:** Implement all three:
- Try IPC by default with automatic fallback
- Log warning if fallback triggered
- Allow `ANI_TUPI_DISABLE_IPC=1` env var to force legacy behavior

---

### Decision 3: Socket File Location

**Options:**
1. `/tmp/ani-tupi-mpv-*.sock` (Linux/macOS)
   - Pros: Standard location, auto-cleaned by OS
   - Cons: May not exist on some systems, permission issues

2. `~/.cache/ani-tupi/sockets/`
   - Pros: Guaranteed writable, persistent across reboots
   - Cons: Manual cleanup needed

3. Temp directory from `tempfile` module
   - Pros: Portable, OS handles cleanup
   - Cons: Different paths per platform (less readable in debug)

**Decision:** Use `tempfile.NamedTemporaryFile()` for portability, plus fallback to `~/.cache` if needed

---

### Decision 4: OSD Message Format

**Options:**
1. Use MPV's built-in OSD system
   - Command: `show-text "Marked watched, loading Ep 42..."`
   - Pros: Native, simple
   - Cons: Limited formatting

2. Custom overlay via lua script
   - Pros: Full control over appearance
   - Cons: Complex, requires Lua knowledge

3. Silent operation (no OSD)
   - Pros: Less intrusive
   - Cons: User doesn't know action took effect

**Decision:** Use MPV's `show-text` for simplicity, can extend later

---

## Data Schema Changes

### history.json Format Evolution

**Current v5 Format:**
```json
{
  "Dandadan": [1704192000, 3, 12345, "animefire", 50]
}
```

**Extended v6 Format** (if needed):
```json
{
  "Dandadan": {
    "timestamp": 1704192000,
    "episode_idx": 3,
    "anilist_id": 12345,
    "source": "animefire",
    "total_episodes": 50,
    "action": "watched",
    "auto_play": true,
    "last_position": 0.75
  }
}
```

**Backward Compatibility:** Maintain v5 array format as primary, migrate on first access

---

## Error Handling

### Scenarios & Recovery

| Scenario | Current Behavior | New Behavior |
|----------|------------------|--------------|
| IPC socket fails to create | N/A | Fall back to legacy play_video() |
| MPV doesn't support IPC | N/A | Graceful fallback (log warning) |
| Next episode URL fetch fails | N/A | Show OSD "Failed to load next" + pause |
| User presses Shift+N on last ep | N/A | Show OSD "No more episodes" + quit |
| History save fails during Shift+N | N/A | Show warning, continue to next anyway |
| MPV crashes during playback | Return exit code 2 | Still return exit code 2 (unchanged) |

---

## Testing Approach

### Unit Tests
- Mock `MPVClient` to simulate IPC events
- Test `_handle_keybinding_action()` with various inputs
- Test history serialization with new metadata
- Test fallback path when IPC disabled

### Integration Tests
- Real MPV process with test socket
- Verify IPC communication works end-to-end
- Test episode navigation (next → previous → history)
- Test concurrent access (multiple episodes in queue)

### E2E Tests
- Full workflow: search → select → play → Shift+N → next plays automatically
- Verify history.json contains correct metadata
- Test on different platforms (Linux/macOS/Windows if possible)

---

## Rollout Plan

### Phase 1: Compatibility Check
- Add `use_ipc=False` parameter (default False) to `play_episode()`
- Keep legacy `play_video()` function working
- No user-facing changes yet

### Phase 2: Beta Testing
- Set `use_ipc=True` by default
- Log all IPC events for debugging
- Collect user feedback

### Phase 3: Production
- Stabilize IPC code based on feedback
- Remove legacy `play_video()` function
- Update documentation

---

## Appendix: MPV input.conf Template

```
# Generated by ani-tupi for episode navigation
# Do not edit directly

# Episode Navigation
shift+n script-message mark-next
shift+p script-message previous
shift+m script-message mark-menu
shift+r script-message reload-episode
shift+a script-message toggle-autoplay
shift+t script-message toggle-sub-dub

# Close without marking
shift+q script-message quit-no-mark

# Debug (remove in production)
shift+d script-message debug-info
```

---

## Appendix: IPC Event Types

All events sent FROM MPV TO ani-tupi:

```json
{
  "type": "keybinding",
  "action": "mark-next",
  "episode": 3,
  "anime_title": "Dandadan"
}
```

All commands sent FROM ani-tupi TO MPV:

```json
{
  "command": "loadfile",
  "args": ["https://stream.url/video.m3u8"]
}
```

---

## References

- MPV JSON IPC Protocol: https://github.com/mpv-player/mpv/blob/master/DOCS/man/ipc.rst
- python-mpv-jsonipc Docs: https://github.com/iwalton3/python-mpv-jsonipc
- Viu Implementation Reference: https://github.com/viu-media/viu
