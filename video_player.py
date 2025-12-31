import subprocess


def play_video(url: str, debug=False) -> None:
    try:
        if not debug:
            subprocess.run(
                [
                    "mpv",
                    url,
                    "--fullscreen",
                    "--cursor-autohide-fs-only",
                ],
                check=False, stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )
    except FileNotFoundError:
        # Handle the case where mpv is not installed or not in PATH
        msg = "Error: 'mpv' is not installed or not found in the system PATH."
        raise OSError(
            msg
        )
    except Exception:
        raise
