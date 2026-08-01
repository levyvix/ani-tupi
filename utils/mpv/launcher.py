"""MPV process launcher and input.conf generation."""

import subprocess
import tempfile

from models.config import settings
from utils.logging import get_logger
from utils.mpv.log_manager import MPVLogManager
from utils.playback_hints import resolve_mpv_stream_options

logger = get_logger(__name__)


class MPVLauncher:
    """Generate MPV keybinding config and launch MPV subprocesses."""

    def __init__(self, log_manager: MPVLogManager):
        self._log_manager = log_manager
        self.last_mpv_log_file: str | None = None

    def generate_input_conf(self) -> tuple[str, str]:
        """Generate temporary MPV input.conf with custom IPC keybindings."""
        input_conf_content = """# ani-tupi IPC Keybindings Configuration
# Auto-generated for episode navigation

# Next Episode (mark watched, move to next)
shift+n script-message mark-next

# Previous Episode (go to previous, resume from saved position)
shift+p script-message previous

# Mark & Menu (mark watched, show menu: next/continue/quit)
shift+m script-message mark-menu

# Reload Current Episode (retry same episode)
shift+r script-message reload-episode

# Toggle Auto-play (skip episode selection for next episode)
shift+a script-message toggle-autoplay

# Toggle Subtitle/Dub (switch if available)
shift+t script-message toggle-sub-dub

# Next Source (switch current episode to the next available source)
shift+f script-message next-source
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".conf",
            prefix="ani-tupi-input-",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(input_conf_content)
            temp_path = f.name

        return temp_path, input_conf_content

    def launch_mpv_with_ipc(
        self,
        url: str,
        socket_path: str,
        input_conf: str,
        anime_title: str | None = None,
        episode_number: int | None = None,
        referrer: str | None = None,
    ) -> subprocess.Popen:
        """Launch MPV with an IPC socket for episode navigation."""
        return self._launch_mpv(
            url,
            socket_path=socket_path,
            input_conf=input_conf,
            anime_title=anime_title,
            episode_number=episode_number,
            referrer=referrer,
        )

    def launch_mpv_without_ipc(
        self,
        url: str,
        *,
        ytdl_format: str | None = None,
        referrer: str | None = None,
    ) -> subprocess.Popen:
        """Launch the system MPV process without episode-navigation IPC."""
        return self._launch_mpv(url, ytdl_format=ytdl_format, referrer=referrer)

    def _launch_mpv(
        self,
        url: str,
        *,
        socket_path: str | None = None,
        input_conf: str | None = None,
        anime_title: str | None = None,
        episode_number: int | None = None,
        ytdl_format: str | None = None,
        referrer: str | None = None,
    ) -> subprocess.Popen:
        """Build and start an MPV subprocess."""
        debug_mode = settings.debug_mpv
        self.last_mpv_log_file = None

        referrer, demuxer_lavf_o = resolve_mpv_stream_options(url, referrer)

        mpv_args = ["mpv"]
        if socket_path:
            mpv_args.append(f"--input-ipc-server={socket_path}")
        if input_conf:
            mpv_args.append(f"--input-conf={input_conf}")

        mpv_args.extend(
            [
                "--fullscreen=yes",
                "--osc=yes",
                "--cache=yes",
                "--demuxer-max-bytes=400M",
                "--demuxer-max-back-bytes=100M",
                "--demuxer-readahead-secs=40",
                "--stream-buffer-size=2M",
                "--hwdec=no",
                "--ytdl=yes",
                f"--ytdl-format={ytdl_format or 'bestvideo[height<=1080]+bestaudio/best'}",
                "--user-agent=Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
            ]
        )

        # Keep MPV log enabled by default for debugging playback failures.
        log_file = self._log_manager.prepare_mpv_log_file()
        self.last_mpv_log_file = log_file
        mpv_args.append(f"--log-file={log_file}")

        if debug_mode:
            mpv_args.append("--msg-level=all=v")
            logger.info(f"   🧪 MPV debug log: {log_file}")

        if anime_title and episode_number:
            media_title = f"{anime_title} Episode {episode_number}"
            mpv_args.append(f"--force-media-title={media_title}")

        if referrer:
            mpv_args.append(f"--referrer={referrer}")

        if demuxer_lavf_o:
            mpv_args.append(f"--demuxer-lavf-o={demuxer_lavf_o}")

        mpv_args.append(url)

        logger.debug("[PLAYBACK DEBUG] MPV command line:")
        logger.debug(f"[PLAYBACK DEBUG] {' '.join(mpv_args)}")

        try:
            if debug_mode:
                return subprocess.Popen(
                    mpv_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
            else:
                return subprocess.Popen(
                    mpv_args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
        except FileNotFoundError as e:
            raise FileNotFoundError("MPV not found in PATH. Please install mpv.") from e
        except Exception as e:
            raise OSError(f"Failed to launch MPV: {e}") from e
