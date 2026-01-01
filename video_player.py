import subprocess


def play_video(url: str, debug=False) -> None:
    try:
        if not debug:
            subprocess.run(
                [
                    "mpv",
                    url,
                    "--speed=1.8",
                    "--fullscreen",
                    "--cursor-autohide-fs-only",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )
        else:
            print("Playing video: ", url)
    except FileNotFoundError:
        # Handle the case where mpv is not installed or not in PATH
        msg = "Error: 'mpv' is not installed or not found in the system PATH."
        raise OSError(msg)
    except Exception:
        raise
