from typing import NamedTuple

import subprocess
from pathlib import Path

from models.config import settings
from utils.logging import get_logger
from utils.mpv import IPCHandler, MPVLauncher, MPVLogManager

logger = get_logger(__name__)


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


class VideoPlayer:
    """Manager for video playback using MPV with IPC support.

    Thin orchestrator composing focused collaborators:
    - MPVLogManager: log rotation and MPV error classification.
    - MPVLauncher: MPV process launch and input.conf generation.
    - IPCHandler: IPC socket lifecycle and keybinding-driven navigation.
    """

    def __init__(self, autoplay: bool = False):
        """Initialize VideoPlayer with session state.

        Args:
            autoplay: Whether to automatically play the next episode when current finishes
        """
        self.autoplay = autoplay
        self._log_manager = MPVLogManager()
        self._launcher = MPVLauncher(self._log_manager)
        self._ipc = IPCHandler(self, self._launcher)

    @property
    def _last_mpv_log_file(self) -> str | None:
        """Path of the most recent MPV log file (managed by the launcher)."""
        return self._launcher.last_mpv_log_file

    def get_autoplay_state(self) -> bool:
        """Get current auto-play state."""
        return self.autoplay

    def set_autoplay_state(self, enabled: bool) -> None:
        """Set auto-play state."""
        self.autoplay = enabled

    def play_episode(
        self,
        url: str,
        anime_title: str,
        episode_number: int,
        total_episodes: int,
        source: str,
        use_ipc: bool = True,
        debug: bool = False,
        anilist_id: int | None = None,
        anilist_episodes: int | None = None,
        referrer: str | None = None,
    ) -> VideoPlaybackResult:
        """Play a single episode with optional IPC support for episode navigation.

        Args:
            url: Video URL to play
            anime_title: Name of anime being watched
            episode_number: Current episode number (1-indexed)
            total_episodes: Total episodes available in scraper
            source: Name of scraper source (e.g., "animefire")
            use_ipc: Enable IPC socket for keybinding events (default True)
            debug: Skip playback and return simulated result
            anilist_id: AniList ID for syncing progress (optional)
            anilist_episodes: Total episodes from AniList (optional, for display)

        Returns:
            VideoPlaybackResult with exit code, action, and optional data
        """
        # Check if IPC should be disabled globally
        if settings.disable_ipc:
            use_ipc = False

        if debug:
            logger.info("DEBUG MODE: Skipping video playback")
            return VideoPlaybackResult(exit_code=0, action="quit", data=None)

        if not use_ipc:
            return self._play_video_without_ipc(url, debug=False, referrer=referrer)

        # Try IPC-based playback, then fall back to a plain MPV subprocess.
        input_conf_path = None
        socket_path = None
        mpv_process = None

        # Episode context passed to IPC handlers
        episode_context = {
            "anime_title": anime_title,
            "episode_number": episode_number,
            "total_episodes": total_episodes,
            "anilist_episodes": anilist_episodes,
            "source": source,
            "url": url,
            "referrer": referrer,
            "anilist_id": anilist_id,
        }

        try:
            logger.debug(f"Source={source} IPC={use_ipc}")
            logger.debug(f"Full URL: {url}")
            # Generate socket path and input.conf
            socket_path = self._create_ipc_socket_path()
            input_conf_path, _ = self._generate_input_conf()

            # Launch MPV with IPC
            mpv_process = self._launch_mpv_with_ipc(
                url,
                socket_path,
                input_conf_path,
                anime_title=anime_title,
                episode_number=episode_number,
                referrer=referrer,
            )

            # Start monitoring events
            result = self._ipc_event_loop(mpv_process, socket_path, episode_context)

            # Wait for process to finish if still running
            if mpv_process.poll() is None:
                try:
                    mpv_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    mpv_process.terminate()

            return result

        except Exception as e:
            logger.info(f"⚠️  IPC playback unavailable: {e}. Using MPV without IPC.")

            # Clean up any dangling process
            if mpv_process and mpv_process.poll() is None:
                try:
                    mpv_process.terminate()
                    mpv_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    mpv_process.kill()

            return self._play_video_without_ipc(url, debug=False, referrer=referrer)

        finally:
            # Clean up temporary files
            if input_conf_path:
                try:
                    Path(input_conf_path).unlink()
                except OSError:
                    pass

            if socket_path:
                self._cleanup_ipc_socket(socket_path)

    def _play_video_without_ipc(
        self, url: str, debug: bool = False, referrer: str | None = None
    ) -> VideoPlaybackResult:
        """Play video through the system MPV process without IPC."""
        try:
            exit_code = self.play_video_raw(url, debug=debug, referrer=referrer)
            return VideoPlaybackResult(exit_code=exit_code, action="quit", data=None)
        except Exception as e:
            logger.info(f"⚠️  Playback error: {e}")
            return VideoPlaybackResult(exit_code=2, action="quit", data=None)

    def play_video_raw(
        self,
        url: str,
        debug: bool = False,
        ytdl_format: str | None = None,
        referrer: str | None = None,
    ) -> int:
        """Play video through the system MPV process and return its exit code."""
        logger.debug(f"Playing through system MPV: {url}")
        if debug:
            logger.info("DEBUG MODE: Skipping video playback")
            return 0

        process = None
        try:
            process = self._launcher.launch_mpv_without_ipc(
                url,
                ytdl_format=ytdl_format,
                referrer=referrer,
            )
            _, stderr_output = process.communicate()
            exit_code = process.returncode or 0

            log_output = ""
            if self._last_mpv_log_file:
                try:
                    log_output = Path(self._last_mpv_log_file).read_text(
                        encoding="utf-8", errors="ignore"
                    )
                except OSError:
                    pass

            if exit_code == 0 and self._has_mpv_load_error(stderr_output or "", log_output):
                return 2
            return exit_code
        except KeyboardInterrupt:
            if process and process.poll() is None:
                process.terminate()
            return 3
        except FileNotFoundError as e:
            raise OSError("Error: 'mpv' is not installed or not found in PATH.") from e
        except Exception as e:
            logger.info(f"⚠️  MPV error: {e}")
            return 2

    # ------------------------------------------------------------------
    # Delegation to collaborators (kept as methods for API/test stability)
    # ------------------------------------------------------------------

    def _create_ipc_socket_path(self) -> str:
        """Generate platform-specific IPC socket path for MPV communication."""
        return self._ipc.create_ipc_socket_path()

    def _cleanup_ipc_socket(self, path: str) -> None:
        """Clean up IPC socket file/pipe without errors."""
        self._ipc.cleanup_ipc_socket(path)

    def _generate_input_conf(self) -> tuple[str, str]:
        """Generate temporary MPV input.conf with custom IPC keybindings."""
        return self._launcher.generate_input_conf()

    def _handle_keybinding_action(
        self,
        action: str,
        context: dict,
    ) -> VideoPlaybackResult | None:
        """Handle keybinding action from MPV and return navigation result."""
        return self._ipc.handle_keybinding_action(action, context)

    def _launch_mpv_with_ipc(
        self,
        url: str,
        socket_path: str,
        input_conf: str,
        anime_title: str | None = None,
        episode_number: int | None = None,
        referrer: str | None = None,
    ) -> subprocess.Popen:
        """Launch MPV process with IPC socket support."""
        return self._launcher.launch_mpv_with_ipc(
            url,
            socket_path,
            input_conf,
            anime_title=anime_title,
            episode_number=episode_number,
            referrer=referrer,
        )

    def _ipc_event_loop(
        self,
        mpv_process: subprocess.Popen,
        socket_path: str,
        episode_context: dict,
        timeout: float = 1.0,
    ) -> VideoPlaybackResult:
        """Monitor IPC socket for keybinding events from MPV."""
        return self._ipc.ipc_event_loop(mpv_process, socket_path, episode_context, timeout=timeout)

    @staticmethod
    def _has_mpv_load_error(stderr_output: str, log_output: str) -> bool:
        """Detect file-loading failures that may still return MPV exit code 0."""
        return MPVLogManager.has_mpv_load_error(stderr_output, log_output)

    @staticmethod
    def _classify_mpv_error(stderr_output: str, log_output: str) -> str | None:
        """Return a user-facing error hint based on MPV logs."""
        return MPVLogManager.classify_mpv_error(stderr_output, log_output)

    def _send_mpv_command(self, sock, command: str, args: list) -> None:
        """Send JSON-RPC command to MPV via IPC socket."""
        self._ipc.send_mpv_command(sock, command, args)


def _format_episode_progress(
    episode_num: int,
    scraper_total: int | None | str = None,
    anilist_total: int | None = None,
) -> str:
    """Format episode progress with scraper and AniList episode counts."""
    if scraper_total is None:
        scraper_total = "?"
    result = f"{episode_num} / {scraper_total}"
    if anilist_total and anilist_total != scraper_total:
        result += f" (total: {anilist_total})"
    return result


# Global functions for backward compatibility (will use a default instance)
_default_player = VideoPlayer()


def get_autoplay_state() -> bool:
    """Get current auto-play state."""
    return _default_player.get_autoplay_state()


def set_autoplay_state(enabled: bool) -> None:
    """Set auto-play state."""
    _default_player.set_autoplay_state(enabled)


def play_video(url: str, debug=False, ytdl_format: str | None = None) -> int:
    """Play video through the system MPV process and return its exit code."""
    return _default_player.play_video_raw(url, debug=debug, ytdl_format=ytdl_format)


def play_episode(
    url: str,
    anime_title: str,
    episode_number: int,
    total_episodes: int,
    source: str,
    use_ipc: bool = True,
    debug: bool = False,
    anilist_id: int | None = None,
    anilist_episodes: int | None = None,
    referrer: str | None = None,
) -> VideoPlaybackResult:
    """Play a single episode with optional IPC support."""
    return _default_player.play_episode(
        url=url,
        anime_title=anime_title,
        episode_number=episode_number,
        total_episodes=total_episodes,
        source=source,
        use_ipc=use_ipc,
        debug=debug,
        anilist_id=anilist_id,
        anilist_episodes=anilist_episodes,
        referrer=referrer,
    )
