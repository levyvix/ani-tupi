from typing import NamedTuple
import os
import platform
import socket
import subprocess
import tempfile
import uuid
from pathlib import Path

# Global auto-play state for the entire session
# When enabled, closing the player (q) automatically advances to next episode
_AUTOPLAY_ENABLED = False


class VideoPlaybackResult(NamedTuple):
    """Result of video playback with optional navigation data.

    Attributes:
        exit_code: MPV exit code (0=normal, 2=error, 3=abort)
        action: Action triggered by keybinding ("quit", "next", "previous", "mark-menu", "reload", "toggle-autoplay", "toggle-sub-dub")
        data: Optional metadata about the action (e.g., next episode URL, episode number)
    """

    exit_code: int
    action: str = "quit"
    data: dict | None = None


def play_video(url: str, debug=False, ytdl_format: str | None = None) -> int:
    """Play video using python-mpv and return exit code.

    Args:
        url: Video URL to play
        debug: Skip playback and return simulated values
        ytdl_format: yt-dlp format selector string

    Returns:
        Exit code from MPV:
        - 0: Normal exit (video finished or user quit with 'q')
        - 2: File couldn't be played OR window closed by user
        - 3: User aborted with quit command
    """

    if debug:
        print("DEBUG MODE: Skipping video playback")
        return 0

    import mpv

    try:
        # Create MPV instance with current settings
        player = mpv.MPV(
            fullscreen=True,
            cursor_autohide_fs_only=True,
            log_handler=print,
            ytdl=True,
            ytdl_format=ytdl_format or "bestvideo[height<=1080]+bestaudio/best",
            ytdl_raw_options="concurrent-fragments=5",
            cache=True,
            demuxer_max_bytes="400M",
            demuxer_max_back_bytes="100M",
            demuxer_readahead_secs=40,
            stream_buffer_size="2M",
            speed=1.8,  # Default playback speed
            input_default_bindings=True,  # Enable default key bindings
            input_vo_keyboard=True,  # Handle keyboard input on video output
            osc=True,  # On-screen controller for mouse interaction
        )

        # Start playback (blocking)
        player.play(url)
        player.wait_for_playback()

        return 0  # Normal playback completion

    except mpv.ShutdownError:
        # User aborted (Ctrl+C or window close)
        return 3

    except FileNotFoundError as e:
        # Handle the case where mpv is not installed or not in PATH
        msg = "Error: 'mpv' is not installed or not found in the system PATH."
        raise OSError(msg) from e

    except Exception as e:
        # Playback error
        print(f"⚠️  MPV error: {e}")
        return 2

    finally:
        # Clean up player instance
        try:
            player.terminate()
        except:  # noqa: E722
            pass


# ============================================================================
# Phase 2: IPC Socket Infrastructure
# ============================================================================


def _create_ipc_socket_path() -> str:
    r"""Generate platform-specific IPC socket path for MPV communication.

    Returns:
        Socket path appropriate for the current OS.
        - Linux/macOS: /tmp/ani-tupi-mpv-{uuid}.sock
        - Windows: \\.\pipe\ani-tupi-mpv-{uuid}
    """
    unique_id = str(uuid.uuid4())[:8]
    system = platform.system()

    if system == "Windows":
        return f"\\\\.\\pipe\\ani-tupi-mpv-{unique_id}"
    else:
        # Linux and macOS
        temp_dir = tempfile.gettempdir()
        return str(Path(temp_dir) / f"ani-tupi-mpv-{unique_id}.sock")


def _cleanup_ipc_socket(path: str) -> None:
    """Clean up IPC socket file/pipe without errors.

    Args:
        path: Socket path to remove
    """
    if not path:
        return

    try:
        socket_path = Path(path)
        if socket_path.exists():
            socket_path.unlink()
    except (OSError, FileNotFoundError):
        # Socket already removed or on Windows (pipes cleanup differently)
        pass


def _generate_input_conf() -> tuple[str, str]:
    """Generate temporary MPV input.conf with custom IPC keybindings.

    Returns:
        Tuple of (input_conf_path, content) with the temporary config file path
        and its content for verification.
    """
    input_conf_content = """# ani-tupi IPC Keybindings Configuration
# Auto-generated for episode navigation

# Next Episode (mark watched, move to next)
Shift+N script-message mark-next

# Previous Episode (go to previous, resume from saved position)
Shift+P script-message previous

# Mark & Menu (mark watched, show menu: next/continue/quit)
Shift+M script-message mark-menu

# Reload Current Episode (retry same episode)
Shift+R script-message reload-episode

# Toggle Auto-play (skip episode selection for next episode)
Shift+A script-message toggle-autoplay

# Toggle Subtitle/Dub (switch if available)
Shift+T script-message toggle-sub-dub
"""

    # Create temp file with cleanup on exit
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".conf", prefix="ani-tupi-input-", delete=False, encoding="utf-8"
    ) as f:
        f.write(input_conf_content)
        temp_path = f.name

    return temp_path, input_conf_content


def _handle_keybinding_action(
    action: str,
    context: dict,
) -> VideoPlaybackResult | None:
    """Handle keybinding action from MPV and return navigation result.

    Args:
        action: Action name from MPV input.conf (mark-next, previous, etc.)
        context: Episode context with url, anime_title, episode_number, etc.

    Returns:
        VideoPlaybackResult with action and data, or None if action not handled
    """
    match action:
        case "mark-next":
            # Mark current episode as watched, move to next
            return VideoPlaybackResult(
                exit_code=0, action="next", data={"episode": context.get("episode_number", 0) + 1}
            )

        case "previous":
            # Go to previous episode
            return VideoPlaybackResult(
                exit_code=0,
                action="previous",
                data={"episode": max(1, context.get("episode_number", 1) - 1)},
            )

        case "mark-menu":
            # Mark current as watched, show menu
            return VideoPlaybackResult(
                exit_code=0, action="mark-menu", data={"episode": context.get("episode_number", 0)}
            )

        case "reload-episode":
            # Retry current episode
            return VideoPlaybackResult(
                exit_code=0, action="reload", data={"episode": context.get("episode_number", 0)}
            )

        case "toggle-autoplay":
            # Toggle auto-play preference
            return VideoPlaybackResult(
                exit_code=0,
                action="toggle-autoplay",
                data={"autoplay": True},  # Would be toggled at service layer
            )

        case "toggle-sub-dub":
            # Toggle subtitle/dub (no state change, just OSD message)
            return VideoPlaybackResult(
                exit_code=0,
                action="toggle-sub-dub",
                data={"message": "Sub/Dub toggle (if available)"},
            )

        case _:
            return None


def _launch_mpv_with_ipc(
    url: str,
    socket_path: str,
    input_conf: str,
) -> subprocess.Popen:
    """Launch MPV process with IPC socket support.

    Args:
        url: Video URL to play
        socket_path: IPC socket path for communication
        input_conf: Path to input.conf file with keybindings

    Returns:
        Popen subprocess object for the MPV process

    Raises:
        FileNotFoundError: If mpv binary not found
        OSError: If process launch fails
    """
    mpv_args = [
        "mpv",
        f"--input-ipc-server={socket_path}",
        f"--input-conf={input_conf}",
        "--fullscreen=yes",
        "--osc=yes",  # Enable on-screen controller for mouse interaction and video bar
        "--cache=yes",
        "--demuxer-max-bytes=400M",
        "--demuxer-max-back-bytes=100M",
        "--demuxer-readahead-secs=40",
        "--stream-buffer-size=2M",
        "--speed=1.8",
        "--ytdl=yes",
        "--ytdl-format=bestvideo[height<=1080]+bestaudio/best",
        url,
    ]

    try:
        return subprocess.Popen(
            mpv_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        msg = "MPV not found in PATH. Please install mpv."
        raise FileNotFoundError(msg) from e
    except Exception as e:
        msg = f"Failed to launch MPV: {e}"
        raise OSError(msg) from e


def _play_video_legacy(url: str, debug: bool = False) -> VideoPlaybackResult:
    """Play video using legacy python-mpv blocking mode (fallback).

    Args:
        url: Video URL to play
        debug: Skip playback if True

    Returns:
        VideoPlaybackResult with exit code and quit action
    """
    if debug:
        print("DEBUG MODE: Skipping video playback")
        return VideoPlaybackResult(exit_code=0, action="quit", data=None)

    try:
        exit_code = play_video(url, debug=False)
        return VideoPlaybackResult(exit_code=exit_code, action="quit", data=None)
    except Exception as e:
        print(f"⚠️  Playback error: {e}")
        return VideoPlaybackResult(exit_code=2, action="quit", data=None)


def _send_mpv_command(sock: socket.socket, command: str, args: list) -> None:
    """Send JSON-RPC command to MPV via IPC socket.

    Args:
        sock: Connected IPC socket
        command: MPV command name (e.g., "loadfile", "show-text")
        args: Command arguments
    """
    import json

    request = {"command": [command] + args}
    try:
        message = json.dumps(request) + "\n"
        sock.sendall(message.encode("utf-8"))
    except Exception as e:
        print(f"Failed to send MPV command: {e}")


def _ipc_event_loop(
    mpv_process: subprocess.Popen,
    socket_path: str,
    episode_context: dict,
    timeout: float = 1.0,
) -> VideoPlaybackResult:
    """Monitor IPC socket for keybinding events from MPV.

    Args:
        mpv_process: Running MPV subprocess
        socket_path: Path to IPC socket
        episode_context: Dict with anime_title, episode_number, total_episodes, source
        timeout: Socket read timeout in seconds

    Returns:
        VideoPlaybackResult when MPV closes or action is triggered
    """
    import json
    import time

    # Declare global auto-play state early to avoid SyntaxError
    global _AUTOPLAY_ENABLED

    # Use global auto-play state (persists across all episodes in the session)
    autoplay_enabled = _AUTOPLAY_ENABLED

    # Wait for socket to be ready
    max_wait = 5.0
    start_time = time.time()
    sock = None

    while time.time() - start_time < max_wait:
        try:
            if platform.system() == "Windows":
                # Windows named pipes - handled differently
                # For now, skip IPC on Windows and use legacy
                return _play_video_legacy("", debug=False)

            # Unix socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(socket_path)
            break
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            time.sleep(0.1)
            continue

    if not sock:
        # Fallback to legacy if socket connection fails
        return _play_video_legacy("", debug=False)

    try:
        buffer = ""
        last_action = "quit"  # Track last action taken (for return value)
        last_action_episode = None  # Track episode number for last action
        while mpv_process.poll() is None:  # While process is running
            try:
                chunk = sock.recv(1024).decode("utf-8", errors="ignore")
                if not chunk:
                    break
                buffer += chunk

                # Parse JSON-RPC messages (one per line)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.strip():
                        continue

                    try:
                        msg = json.loads(line)
                        if msg.get("event") == "client-message":
                            args = msg.get("args", [])
                            if args:
                                action = args[0]

                                # Handle navigation actions that load new episodes
                                if action == "mark-next":
                                    from services.history_service import save_history_from_event
                                    from services.repository import rep

                                    anime_title = episode_context.get("anime_title")
                                    episode_number = episode_context.get("episode_number", 1)
                                    source = episode_context.get("source")
                                    anilist_id = episode_context.get("anilist_id")

                                    # Save current episode as watched (0-indexed)
                                    episode_idx = episode_number - 1
                                    sync_info = save_history_from_event(
                                        anime_title=anime_title,
                                        episode_idx=episode_idx,
                                        action="watched",
                                        source=source,
                                        anilist_id=anilist_id,
                                    )

                                    # Show terminal feedback about AniList sync
                                    if sync_info.get("anilist_message"):
                                        print(f"   {sync_info['anilist_message']}")

                                    # Show confirmation that episode was marked as watched
                                    from services.anilist_service import anilist_client

                                    sync_status = ""
                                    if anilist_id and anilist_client.is_authenticated():
                                        sync_status = " ✓ AniList"
                                    # MPV show-text format: show-text "message" [duration_ms]
                                    # Duration is optional, default is usually 3000ms
                                    _send_mpv_command(
                                        sock,
                                        "show-text",
                                        [
                                            f"✓ Ep {episode_number} marcado como assistido{sync_status}",
                                            3000,
                                        ],
                                    )

                                    # Get episode list to check if next episode exists
                                    episode_list = rep.get_episode_list(anime_title)
                                    total_episodes = len(episode_list) if episode_list else 0

                                    # Get next episode URL
                                    next_episode_number = episode_number + 1
                                    if episode_list and next_episode_number <= len(episode_list):
                                        next_episode_idx = next_episode_number - 1
                                        next_url = rep.get_episode_url(
                                            anime_title, next_episode_idx
                                        )

                                        if next_url:
                                            # Show terminal feedback about playing next episode
                                            print(f"▶️  Reproduzindo Episódio {next_episode_number}")

                                            # Send MPV command to load next episode
                                            _send_mpv_command(
                                                sock, "loadfile", [next_url, "replace"]
                                            )

                                            # Show OSD message
                                            _send_mpv_command(
                                                sock,
                                                "show-text",
                                                [f"Carregando Episódio {next_episode_number}..."],
                                            )

                                            # Update episode context for next iteration
                                            episode_context["episode_number"] = next_episode_number
                                            episode_context["url"] = next_url
                                            episode_context["total_episodes"] = total_episodes
                                            # Preserve anilist_id for next episode

                                            # Track that "next" action was taken
                                            last_action = "next"
                                            last_action_episode = next_episode_number  # Track which episode to play next

                                            # Continue loop to listen for more keybindings
                                            continue
                                        else:
                                            # Next episode URL not found
                                            _send_mpv_command(
                                                sock, "show-text", ["No next episode available"]
                                            )
                                    else:
                                        # No more episodes
                                        _send_mpv_command(sock, "show-text", ["No more episodes"])

                                elif action == "previous":
                                    from services.repository import rep

                                    anime_title = episode_context.get("anime_title")
                                    episode_number = episode_context.get("episode_number", 1)

                                    # Get previous episode URL
                                    prev_episode_number = max(1, episode_number - 1)
                                    if prev_episode_number < episode_number:
                                        prev_episode_idx = prev_episode_number - 1
                                        prev_url = rep.get_episode_url(
                                            anime_title, prev_episode_idx
                                        )

                                        if prev_url:
                                            # Show terminal feedback about playing previous episode
                                            print(f"⏪ Voltando para Episódio {prev_episode_number}")

                                            # Send MPV command to load previous episode
                                            _send_mpv_command(
                                                sock, "loadfile", [prev_url, "replace"]
                                            )

                                            # Show OSD message
                                            _send_mpv_command(
                                                sock,
                                                "show-text",
                                                [f"Carregando Episódio {prev_episode_number}..."],
                                            )

                                            # Update episode context
                                            episode_context["episode_number"] = prev_episode_number
                                            episode_context["url"] = prev_url

                                            # Track that "previous" action was taken
                                            last_action = "previous"
                                            last_action_episode = (
                                                prev_episode_number  # Track which episode to play
                                            )

                                            # Continue loop
                                            continue
                                        else:
                                            print("⚠️  Episódio anterior não disponível")
                                            _send_mpv_command(
                                                sock,
                                                "show-text",
                                                ["Episódio anterior não disponível"],
                                            )
                                    else:
                                        print("⚠️  Nenhum episódio anterior")
                                        _send_mpv_command(
                                            sock, "show-text", ["Nenhum episódio anterior"]
                                        )

                                elif action == "reload-episode":
                                    # Reload current episode
                                    current_url = episode_context.get("url")
                                    current_episode = episode_context.get("episode_number", 1)
                                    if current_url:
                                        # Show terminal feedback about reloading episode
                                        print(f"🔄 Recarregando Episódio {current_episode}")

                                        _send_mpv_command(
                                            sock, "loadfile", [current_url, "replace"]
                                        )
                                        _send_mpv_command(
                                            sock, "show-text", [f"Recarregando Episódio {current_episode}..."]
                                        )
                                        # Track reload action
                                        last_action = "reload"
                                        # Continue loop
                                        continue

                                # Handle other actions (mark-menu, toggle-autoplay, toggle-sub-dub)
                                # Add terminal feedback for these actions
                                if action == "mark-menu":
                                    from services.history_service import save_history_from_event

                                    anime_title = episode_context.get("anime_title")
                                    episode_number = episode_context.get("episode_number", 1)
                                    source = episode_context.get("source")
                                    anilist_id = episode_context.get("anilist_id")

                                    # Save current episode as watched
                                    episode_idx = episode_number - 1
                                    sync_info = save_history_from_event(
                                        anime_title=anime_title,
                                        episode_idx=episode_idx,
                                        action="watched",
                                        source=source,
                                        anilist_id=anilist_id,
                                    )

                                    # Show terminal feedback
                                    print(f"📋 Episódio {episode_number} marcado - Retornando ao menu")
                                    if sync_info.get("anilist_message"):
                                        print(f"   {sync_info['anilist_message']}")

                                    # Show OSD message
                                    from services.anilist_service import anilist_client

                                    sync_status = ""
                                    if anilist_id and anilist_client.is_authenticated():
                                        sync_status = " ✓ AniList"
                                    _send_mpv_command(
                                        sock,
                                        "show-text",
                                        [f"✓ Marcado como assistido{sync_status}", 2000],
                                    )

                                elif action == "toggle-autoplay":
                                    # Toggle global auto-play state (persists for entire session)
                                    _AUTOPLAY_ENABLED = not _AUTOPLAY_ENABLED
                                    autoplay_enabled = _AUTOPLAY_ENABLED
                                    status = "ATIVADO" if autoplay_enabled else "DESATIVADO"
                                    print(f"🔄 Auto-play {status} (válido para toda a sessão)")
                                    _send_mpv_command(
                                        sock,
                                        "show-text",
                                        [f"Auto-play {status} - Ao sair (q) {'vai para próximo episódio' if autoplay_enabled else 'volta ao menu'}", 3000],
                                    )
                                    # Continue playing - don't close the player
                                    continue

                                elif action == "toggle-sub-dub":
                                    # TODO: Implement subtitle/dub switching logic
                                    print("🔄 Alternando legendado/dublado (se disponível)")
                                    _send_mpv_command(
                                        sock, "show-text", ["Sub/Dub alternado (se disponível)", 2000]
                                    )
                                    # Continue playing - don't close the player
                                    continue

                                # Handle other actions that require closing the player
                                result = _handle_keybinding_action(action, episode_context)
                                if result:
                                    # For actions that require returning to caller (mark-menu)
                                    return result

                    except json.JSONDecodeError:
                        # Skip malformed JSON
                        continue

            except socket.timeout:
                # Timeout is normal, continue polling
                continue
            except Exception as e:
                print(f"IPC error: {e}")
                break

        # MPV process exited normally - return last action taken (or "quit" if none)
        # If last_action was "next", include episode data
        if last_action == "next" and last_action_episode:
            return VideoPlaybackResult(
                exit_code=mpv_process.returncode or 0,
                action="next",
                data={"episode": last_action_episode},
            )
        elif last_action == "previous" and last_action_episode:
            return VideoPlaybackResult(
                exit_code=mpv_process.returncode or 0,
                action="previous",
                data={"episode": last_action_episode},
            )
        elif last_action == "reload":
            current_episode = episode_context.get("episode_number", 1)
            return VideoPlaybackResult(
                exit_code=mpv_process.returncode or 0,
                action="reload",
                data={"episode": current_episode},
            )
        else:
            # Check if auto-play is enabled
            if autoplay_enabled:
                # Mark current episode as watched and advance to next
                from services.history_service import save_history_from_event

                anime_title = episode_context.get("anime_title")
                episode_number = episode_context.get("episode_number", 1)
                source = episode_context.get("source")
                anilist_id = episode_context.get("anilist_id")

                # Save current episode as watched
                episode_idx = episode_number - 1
                sync_info = save_history_from_event(
                    anime_title=anime_title,
                    episode_idx=episode_idx,
                    action="watched",
                    source=source,
                    anilist_id=anilist_id,
                )

                # Show terminal feedback
                print(f"✓ Episódio {episode_number} marcado como assistido")
                if sync_info.get("anilist_message"):
                    print(f"   {sync_info['anilist_message']}")

                # Return "next" action to load next episode
                next_episode = episode_number + 1
                print(f"▶️  Auto-play: Carregando Episódio {next_episode}")
                return VideoPlaybackResult(
                    exit_code=mpv_process.returncode or 0,
                    action="next",
                    data={"episode": next_episode},
                )
            else:
                # Auto-play disabled - return to menu
                return VideoPlaybackResult(
                    exit_code=mpv_process.returncode or 0, action="quit", data=None
                )

    finally:
        try:
            sock.close()
        except:  # noqa: E722
            pass


# ============================================================================
# Phase 3: New Play Interface (play_episode)
# ============================================================================


def play_episode(
    url: str,
    anime_title: str,
    episode_number: int,
    total_episodes: int,
    source: str,
    use_ipc: bool = True,
    debug: bool = False,
    anilist_id: int | None = None,
) -> VideoPlaybackResult:
    """Play a single episode with optional IPC support for episode navigation.

    Args:
        url: Video URL to play
        anime_title: Name of anime being watched
        episode_number: Current episode number (1-indexed)
        total_episodes: Total episodes in series
        source: Name of scraper source (e.g., "animefire")
        use_ipc: Enable IPC socket for keybinding events (default True)
        debug: Skip playback and return simulated result
        anilist_id: AniList ID for syncing progress (optional)

    Returns:
        VideoPlaybackResult with exit code, action, and optional data

    Environment Variables:
        ANI_TUPI_DISABLE_IPC: Set to "1" to force legacy playback

    Note:
        Auto-play state is global (_AUTOPLAY_ENABLED) and persists across all
        episodes in the session. Use Shift+A during playback to toggle.
    """
    # Check if IPC should be disabled globally
    if os.environ.get("ANI_TUPI_DISABLE_IPC") == "1":
        use_ipc = False

    if debug:
        print("DEBUG MODE: Skipping video playback")
        return VideoPlaybackResult(exit_code=0, action="quit", data=None)

    # Episode context passed to IPC handlers
    episode_context = {
        "anime_title": anime_title,
        "episode_number": episode_number,
        "total_episodes": total_episodes,
        "source": source,
        "url": url,
        "anilist_id": anilist_id,
    }

    if not use_ipc:
        # Use legacy blocking playback
        return _play_video_legacy(url, debug=False)

    # Try IPC-based playback with fallback
    input_conf_path = None
    socket_path = None
    mpv_process = None

    try:
        # Generate socket path and input.conf
        socket_path = _create_ipc_socket_path()
        input_conf_path, _ = _generate_input_conf()

        # Launch MPV with IPC
        mpv_process = _launch_mpv_with_ipc(url, socket_path, input_conf_path)

        # Start monitoring events
        result = _ipc_event_loop(mpv_process, socket_path, episode_context)

        # Wait for process to finish if still running
        if mpv_process.poll() is None:
            try:
                mpv_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                mpv_process.terminate()

        return result

    except (FileNotFoundError, OSError, Exception) as e:
        # IPC launch failed, fallback to legacy
        print(f"⚠️  IPC playback unavailable: {e}. Using legacy mode.")

        # Clean up any dangling process
        if mpv_process and mpv_process.poll() is None:
            try:
                mpv_process.terminate()
                mpv_process.wait(timeout=1)
            except:  # noqa: E722
                mpv_process.kill()

        return _play_video_legacy(url, debug=False)

    finally:
        # Clean up temporary files
        if input_conf_path:
            try:
                Path(input_conf_path).unlink()
            except:  # noqa: E722
                pass

        if socket_path:
            _cleanup_ipc_socket(socket_path)
