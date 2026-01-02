import subprocess


def play_video(url: str, debug=False, ytdl_format: str | None = None) -> int:
    """Play video using MPV and return exit code.

    Returns:
        Exit code from MPV:
        - 0: Normal exit (video finished or user quit with 'q')
        - 1: Generic error
        - 2: File couldn't be played OR window closed by user
        - 3: User aborted with quit command
        - 4: Command line parsing error
    """
    try:
        # Build base MPV command
        cmd = [
            "mpv",
            url,
            "--speed=1.8",
            "--fullscreen",
            "--cursor-autohide-fs-only",
            "--log-file=mpv.log",  # Keep detailed logs for debugging
            # === Principais opções para começar mais rápido e reduzir travamentos ===
            "--cache=yes",  # ativa cache (geralmente já é default)
            "--demuxer-max-bytes=400MiB",  # ou até 800MiB / 1GiB se tiver RAM sobrando
            "--demuxer-max-back-bytes=100MiB",  # ajuda em seeks para trás
            "--demuxer-readahead-secs=40",  # tenta pré-carregar mais segundos
            "--stream-buffer-size=2MiB",  # buffer de rede maior (padrão é pequeno)
            # yt-dlp integration
            "--ytdl-raw-options=concurrent-fragments=5",  # baixa pedaços em paralelo
        ]

        # Add format selection if specified, otherwise use default best quality
        if ytdl_format:
            cmd.append(f"--ytdl-format={ytdl_format}")
        else:
            cmd.append("--ytdl-format=bestvideo[height<=1080]+bestaudio/best")

        result = subprocess.run(
            cmd,
            check=False,  # Don't raise on non-zero exit
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )

        # Show error details if playback failed
        if result.returncode == 2:
            print("⚠️  MPV falhou ao reproduzir este vídeo")
            return 2

        return result.returncode
    except FileNotFoundError:
        # Handle the case where mpv is not installed or not in PATH
        msg = "Error: 'mpv' is not installed or not found in the system PATH."
        raise OSError(msg)
    except Exception as e:
        raise e
