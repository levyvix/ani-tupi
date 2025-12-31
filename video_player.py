import subprocess


def play_video(url: str, debug=False) -> None:
    try:
        if not debug:
            process = subprocess.run(
                [
                    "mpv",
                    url,
                    "--fullscreen",
                    "--cursor-autohide-fs-only",
                ],
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )
    except FileNotFoundError:
        # Handle the case where mpv is not installed or not in PATH
        raise EnvironmentError(
            "Error: 'mpv' is not installed or not found in the system PATH."
        )
    except Exception as e:
        raise e
