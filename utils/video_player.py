import mpv


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
