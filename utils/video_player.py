from typing import NamedTuple

import os
import platform
import socket
import subprocess
import tempfile
import uuid
import json
import time
from pathlib import Path
from datetime import datetime

from models.config import get_data_path
from utils.logging import get_logger
from utils.playback_hints import resolve_mpv_stream_options

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
    """Manager for video playback using MPV with IPC support."""

    def __init__(self, autoplay: bool = False):
        """Initialize VideoPlayer with session state.

        Args:
            autoplay: Whether to automatically play the next episode when current finishes
        """
        self.autoplay = autoplay
        self._last_mpv_log_file: str | None = None

    def _get_mpv_logs_dir(self) -> Path:
        """Return directory for persistent MPV logs."""
        logs_dir = get_data_path() / "mpv-logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def _rotate_mpv_logs(self, max_files: int = 7, max_total_bytes: int = 20 * 1024 * 1024) -> None:
        """Rotate MPV logs by file count and total size.

        Keeps newest files and removes older ones first.
        """
        try:
            logs_dir = self._get_mpv_logs_dir()
            files = sorted(
                logs_dir.glob("mpv-*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            # File-count based cleanup
            for old_file in files[max_files:]:
                try:
                    old_file.unlink()
                except OSError:
                    pass

            # Re-list after count cleanup for size-based cleanup
            files = sorted(
                logs_dir.glob("mpv-*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            total_size = sum(p.stat().st_size for p in files)
            if total_size <= max_total_bytes:
                return

            # Remove oldest until under limit
            for old_file in reversed(files):
                if total_size <= max_total_bytes:
                    break
                try:
                    size = old_file.stat().st_size
                    old_file.unlink()
                    total_size -= size
                except OSError:
                    continue
        except OSError:
            # Never block playback if log rotation fails
            return

    def _prepare_mpv_log_file(self) -> str:
        """Create a new MPV log file path and rotate old logs."""
        configured_log = os.environ.get("ANI_TUPI_MPV_LOG_FILE", "").strip()
        if configured_log:
            return configured_log

        self._rotate_mpv_logs()
        logs_dir = self._get_mpv_logs_dir()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        return str(logs_dir / f"mpv-{ts}-{str(uuid.uuid4())[:8]}.log")

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
        if os.environ.get("ANI_TUPI_DISABLE_IPC") == "1":
            use_ipc = False

        if debug:
            logger.info("DEBUG MODE: Skipping video playback")
            return VideoPlaybackResult(exit_code=0, action="quit", data=None)

        if not use_ipc:
            # Use legacy blocking playback
            return self._play_video_legacy(url, debug=False, referrer=referrer)

        # Try IPC-based playback with fallback
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

        except (FileNotFoundError, OSError, Exception) as e:
            # IPC launch failed, fallback to legacy
            logger.info(f"⚠️  IPC playback unavailable: {e}. Using legacy mode.")

            # Clean up any dangling process
            if mpv_process and mpv_process.poll() is None:
                try:
                    mpv_process.terminate()
                    mpv_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    mpv_process.kill()

            return self._play_video_legacy(url, debug=False, referrer=referrer)

        finally:
            # Clean up temporary files
            if input_conf_path:
                try:
                    Path(input_conf_path).unlink()
                except OSError:
                    pass

            if socket_path:
                self._cleanup_ipc_socket(socket_path)

    def _play_video_legacy(
        self, url: str, debug: bool = False, referrer: str | None = None
    ) -> VideoPlaybackResult:
        """Play video using legacy python-mpv blocking mode (fallback)."""
        logger.debug("_play_video_legacy called")
        logger.debug(f"Full URL: {url}")
        if debug:
            logger.info("Skipping video playback")
            return VideoPlaybackResult(exit_code=0, action="quit", data=None)

        try:
            logger.debug("Calling play_video_raw...")
            exit_code = self.play_video_raw(url, debug=False, referrer=referrer)
            logger.debug(f"play_video_raw returned exit_code={exit_code}")
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
        """Play video using python-mpv and return exit code."""
        logger.debug("play_video_raw: Starting")
        logger.debug(f"Full URL: {url}")
        if debug:
            logger.info("DEBUG MODE: Skipping video playback")
            return 0

        import mpv

        # Generate custom ani-tupi keybindings
        input_conf_path, _ = self._generate_input_conf()

        referrer, demuxer_lavf_o = resolve_mpv_stream_options(url, referrer)

        player = None
        try:
            # Create MPV instance with current settings
            logger.debug("play_video_raw: Creating MPV instance...")
            mpv_kwargs = dict(
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
                speed=1.8,
                input_default_bindings=True,
                input_vo_keyboard=True,
                input_conf=input_conf_path,
                osc=True,
                referrer=referrer,
                user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
            )
            if demuxer_lavf_o:
                mpv_kwargs["demuxer_lavf_o"] = demuxer_lavf_o
            player = mpv.MPV(**mpv_kwargs)

            # Start playback (blocking)
            logger.debug(" play_video_raw: Calling player.play()...")
            player.play(url)
            logger.debug(" play_video_raw: Calling player.wait_for_playback()...")
            player.wait_for_playback()
            logger.debug(" play_video_raw: Playback finished normally (exit code 0)")

            return 0  # Normal playback completion

        except mpv.ShutdownError:
            # User aborted (Ctrl+C or window close)
            logger.debug(" play_video_raw: ShutdownError (user abort)")
            return 3
        except FileNotFoundError as e:
            logger.debug(" play_video_raw: MPV not found in PATH")
            msg = "Error: 'mpv' is not installed or not found in the system PATH."
            raise OSError(msg) from e
        except Exception as e:
            # Playback error
            logger.debug(f" play_video_raw: Exception: {type(e).__name__}: {e}")
            logger.info(f"⚠️  MPV error: {e}")
            return 2
        finally:
            # Clean up player instance
            try:
                if player is not None:
                    player.terminate()
            except OSError:
                pass

            # Clean up temporary input.conf file
            if input_conf_path:
                try:
                    Path(input_conf_path).unlink()
                except OSError:
                    pass

    def _create_ipc_socket_path(self) -> str:
        """Generate platform-specific IPC socket path for MPV communication."""
        unique_id = str(uuid.uuid4())[:8]
        system = platform.system()

        if system == "Windows":
            return f"\\\\.\\pipe\\ani-tupi-mpv-{unique_id}"
        else:
            temp_dir = tempfile.gettempdir()
            return str(Path(temp_dir) / f"ani-tupi-mpv-{unique_id}.sock")

    def _cleanup_ipc_socket(self, path: str) -> None:
        """Clean up IPC socket file/pipe without errors."""
        if not path:
            return

        try:
            socket_path = Path(path)
            if socket_path.exists():
                socket_path.unlink()
        except (OSError, FileNotFoundError):
            pass

    def _generate_input_conf(self) -> tuple[str, str]:
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

    def _handle_keybinding_action(
        self,
        action: str,
        context: dict,
    ) -> VideoPlaybackResult | None:
        """Handle keybinding action from MPV and return navigation result."""
        match action:
            case "mark-next":
                return VideoPlaybackResult(
                    exit_code=0,
                    action="next",
                    data={"episode": context.get("episode_number", 0) + 1},
                )
            case "previous":
                return VideoPlaybackResult(
                    exit_code=0,
                    action="previous",
                    data={"episode": max(1, context.get("episode_number", 1) - 1)},
                )
            case "mark-menu":
                return VideoPlaybackResult(
                    exit_code=0,
                    action="mark-menu",
                    data={"episode": context.get("episode_number", 0)},
                )
            case "reload-episode":
                return VideoPlaybackResult(
                    exit_code=0,
                    action="reload",
                    data={"episode": context.get("episode_number", 0)},
                )
            case "toggle-autoplay":
                self.autoplay = not self.autoplay
                return VideoPlaybackResult(
                    exit_code=0,
                    action="toggle-autoplay",
                    data={"enabled": self.autoplay},
                )
            case "toggle-sub-dub":
                return VideoPlaybackResult(
                    exit_code=0,
                    action="toggle-sub-dub",
                    data={"message": "Sub/Dub toggle (if available)"},
                )
            case _:
                return None

    def _launch_mpv_with_ipc(
        self,
        url: str,
        socket_path: str,
        input_conf: str,
        anime_title: str | None = None,
        episode_number: int | None = None,
        referrer: str | None = None,
    ) -> subprocess.Popen:
        """Launch MPV process with IPC socket support.

        Args:
            url: Video URL to play
            socket_path: Path to IPC socket
            input_conf: Path to input.conf file
            anime_title: Anime title for window title
            episode_number: Episode number for window title
            source: Source name for window title

        Returns:
            MPV subprocess handle
        """
        debug_mode = os.environ.get("ANI_TUPI_DEBUG_MPV") == "1"
        self._last_mpv_log_file = None

        referrer, demuxer_lavf_o = resolve_mpv_stream_options(url, referrer)

        mpv_args = [
            "mpv",
            f"--input-ipc-server={socket_path}",
            f"--input-conf={input_conf}",
            "--fullscreen=yes",
            "--osc=yes",
            "--cache=yes",
            "--demuxer-max-bytes=400M",
            "--demuxer-max-back-bytes=100M",
            "--demuxer-readahead-secs=40",
            "--stream-buffer-size=2M",
            "--speed=1.8",
            "--ytdl=yes",
            "--ytdl-format=bestvideo[height<=1080]+bestaudio/best",
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
        ]

        # Keep MPV log enabled by default for debugging playback failures.
        log_file = self._prepare_mpv_log_file()
        self._last_mpv_log_file = log_file
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

    def _ipc_event_loop(
        self,
        mpv_process: subprocess.Popen,
        socket_path: str,
        episode_context: dict,
        timeout: float = 1.0,
    ) -> VideoPlaybackResult:
        """Monitor IPC socket for keybinding events from MPV."""
        # Wait for socket to be ready
        max_wait = 5.0
        start_time = time.time()
        sock = None

        while time.time() - start_time < max_wait:
            try:
                if platform.system() == "Windows":
                    # Fallback to legacy on Windows for now
                    url = episode_context.get("url", "")
                    return self._play_video_legacy(url, debug=False)

                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect(socket_path)
                break
            except (FileNotFoundError, ConnectionRefusedError, OSError):
                time.sleep(0.1)
                continue

        if not sock:
            url = episode_context.get("url", "")
            logger.debug("[PLAYBACK DEBUG] IPC socket failed, falling back to legacy.")
            logger.debug(f"[PLAYBACK DEBUG] Full URL for legacy fallback: {url}")
            return self._play_video_legacy(url, debug=False)

        try:
            buffer = ""
            while mpv_process.poll() is None:
                try:
                    chunk = sock.recv(1024).decode("utf-8", errors="ignore")
                    if not chunk:
                        break
                    buffer += chunk

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
                                    if action == "mark-next":
                                        from services.history_service import (
                                            save_history_from_event,
                                        )
                                        from services.repository import rep

                                        anime_title = episode_context.get("anime_title")
                                        episode_number = episode_context.get("episode_number", 1)
                                        source = episode_context.get("source")
                                        anilist_id = episode_context.get("anilist_id")

                                        if not anime_title:
                                            continue

                                        episode_idx = episode_number - 1
                                        save_history_from_event(
                                            anime_title=anime_title,
                                            episode_idx=episode_idx,
                                            action="watched",
                                            source=source,
                                            anilist_id=anilist_id,
                                        )

                                        next_episode_number = episode_number + 1
                                        scraper_total = episode_context.get("total_episodes")
                                        anilist_total = episode_context.get("anilist_episodes")
                                        progress_str = _format_episode_progress(
                                            next_episode_number,
                                            scraper_total,
                                            anilist_total,
                                        )
                                        self._send_mpv_command(
                                            sock,
                                            "show-text",
                                            [f"Buscando Episódio {progress_str}..."],
                                        )
                                        next_url = rep.search_player(
                                            anime_title, next_episode_number
                                        )

                                        if next_url:
                                            self._send_mpv_command(
                                                sock, "loadfile", [next_url, "replace"]
                                            )
                                            self._send_mpv_command(
                                                sock,
                                                "show-text",
                                                [f"▶️ Reproduzindo Episódio {progress_str}"],
                                            )
                                            # Update MPV title to show new episode number
                                            new_title = (
                                                f"{anime_title} Episode {next_episode_number}"
                                            )
                                            self._send_mpv_command(
                                                sock,
                                                "set_property",
                                                ["force-media-title", new_title],
                                            )
                                            episode_context["episode_number"] = next_episode_number
                                            episode_context["url"] = next_url
                                            logger.info(f"▶️  Reproduzindo Episódio {progress_str}")

                                            continue
                                        else:
                                            self._send_mpv_command(
                                                sock,
                                                "show-text",
                                                [
                                                    "Não há mais episódios disponíveis ou erro ao buscar"
                                                ],
                                            )
                                            logger.info(
                                                f"❌ Falha ao carregar Episódio {next_episode_number}"
                                            )

                                    elif action == "previous":
                                        from services.repository import rep

                                        anime_title = episode_context.get("anime_title")
                                        episode_number = episode_context.get("episode_number", 1)

                                        if not anime_title:
                                            continue

                                        prev_episode_number = max(1, episode_number - 1)
                                        if prev_episode_number < episode_number:
                                            scraper_total = episode_context.get("total_episodes")
                                            anilist_total = episode_context.get("anilist_episodes")
                                            progress_str = _format_episode_progress(
                                                prev_episode_number,
                                                scraper_total,
                                                anilist_total,
                                            )
                                            self._send_mpv_command(
                                                sock,
                                                "show-text",
                                                [f"Buscando Episódio {progress_str}..."],
                                            )
                                            prev_url = rep.search_player(
                                                anime_title, prev_episode_number
                                            )

                                            if prev_url:
                                                self._send_mpv_command(
                                                    sock,
                                                    "loadfile",
                                                    [prev_url, "replace"],
                                                )
                                                self._send_mpv_command(
                                                    sock,
                                                    "show-text",
                                                    [f"⏪ Voltando para Episódio {progress_str}"],
                                                )
                                                # Update MPV title to show new episode number
                                                new_title = (
                                                    f"{anime_title} Episode {prev_episode_number}"
                                                )
                                                self._send_mpv_command(
                                                    sock,
                                                    "set_property",
                                                    ["force-media-title", new_title],
                                                )
                                                episode_context["episode_number"] = (
                                                    prev_episode_number
                                                )
                                                episode_context["url"] = prev_url
                                                logger.info(
                                                    f"⏪ Voltando para Episódio {progress_str}"
                                                )

                                                continue
                                            else:
                                                self._send_mpv_command(
                                                    sock,
                                                    "show-text",
                                                    [
                                                        "Episódio anterior não disponível ou erro ao buscar"
                                                    ],
                                                )
                                                logger.info(
                                                    f"❌ Falha ao carregar Episódio {prev_episode_number}"
                                                )
                                        else:
                                            self._send_mpv_command(
                                                sock,
                                                "show-text",
                                                ["Não há episódios anteriores"],
                                            )

                                    elif action == "reload-episode":
                                        current_url = episode_context.get("url")
                                        if current_url:
                                            self._send_mpv_command(
                                                sock,
                                                "loadfile",
                                                [current_url, "replace"],
                                            )
                                            self._send_mpv_command(
                                                sock,
                                                "show-text",
                                                ["Reloading episode..."],
                                            )
                                            continue

                                    elif action == "toggle-autoplay":
                                        self.autoplay = not self.autoplay
                                        status = "ATIVADO" if self.autoplay else "DESATIVADO"
                                        message = f"Auto-play {status} (válido para toda a sessão)"
                                        self._send_mpv_command(sock, "show-text", [message, "3000"])
                                        logger.info(f"{message}")
                                        continue

                                    result = self._handle_keybinding_action(action, episode_context)
                                    if result:
                                        return result
                        except json.JSONDecodeError:
                            continue
                except TimeoutError:
                    continue
                except Exception as e:
                    logger.info(f"IPC error: {e}")
                    break

            exit_code = mpv_process.returncode or 0
            stderr_output = ""
            debug_mode = os.environ.get("ANI_TUPI_DEBUG_MPV") == "1"
            if hasattr(mpv_process, "stderr") and mpv_process.stderr:
                try:
                    stderr_output = mpv_process.stderr.read()
                except (OSError, ValueError):
                    pass

            log_output = ""
            if self._last_mpv_log_file:
                try:
                    with open(self._last_mpv_log_file, encoding="utf-8", errors="ignore") as f:
                        log_output = f.read()
                except OSError:
                    log_output = ""

            # MPV can sometimes exit with code 0 even when file loading failed.
            # Detect this signature and treat it as playback failure.
            if exit_code == 0 and self._has_mpv_load_error(stderr_output, log_output):
                exit_code = 2

            error_hint = self._classify_mpv_error(stderr_output, log_output)

            if debug_mode:
                logger.info(f"   🧪 MPV debug mode ativo | exit_code={exit_code}")
                if stderr_output.strip():
                    stderr_lines = [
                        line.strip() for line in stderr_output.split("\n") if line.strip()
                    ]
                    logger.info("   🧪 MPV stderr (últimas linhas):")
                    for line in stderr_lines[-10:]:
                        logger.info(f"      {line[:160]}")

                if self._last_mpv_log_file:
                    logger.info(f"   🧪 MPV log file salvo em: {self._last_mpv_log_file}")
                    try:
                        log_lines = [
                            line.strip() for line in log_output.split("\n") if line.strip()
                        ]
                        if log_lines:
                            logger.info("   🧪 MPV log (últimas linhas):")
                            for line in log_lines[-15:]:
                                logger.info(f"      {line[:160]}")
                    except OSError as e:
                        logger.info(f"   ⚠️  Falha ao ler MPV log file: {e}")

            if exit_code != 0 or "error" in stderr_output.lower():
                logger.info(f"⚠️  MPV exited with code {exit_code}")
                if self._last_mpv_log_file:
                    logger.info(f"   📝 MPV log: {self._last_mpv_log_file}")
                if "error" in stderr_output.lower():
                    error_lines = [
                        line for line in stderr_output.split("\n") if "error" in line.lower()
                    ]
                    for error_line in error_lines[:3]:
                        if error_line.strip():
                            logger.info(f"   ❌ {error_line.strip()[:100]}")
                    if "400" in stderr_output:
                        logger.info("\n   ℹ️  AnimesonlineCC: Token expirado (URLs temporárias)")
                logger.info("   Tente ativar debug: ANI_TUPI_DEBUG_MPV=1 uv run ani-tupi")

            if self.autoplay and exit_code == 0:
                from services.history_service import save_history_from_event

                anime_title = episode_context.get("anime_title")
                episode_number = episode_context.get("episode_number", 1)
                source = episode_context.get("source")
                anilist_id = episode_context.get("anilist_id")

                if anime_title:
                    episode_idx = episode_number - 1
                    save_history_from_event(
                        anime_title=anime_title,
                        episode_idx=episode_idx,
                        action="watched",
                        source=source,
                        anilist_id=anilist_id,
                    )
                logger.info(
                    f"▶️  Auto-play ativo: marcando Episódio {episode_number} como assistido"
                )
                return VideoPlaybackResult(
                    exit_code=exit_code,
                    action="auto-next",
                    data={"episode": episode_number},
                )

            final_episode = episode_context.get("episode_number", 1)
            return VideoPlaybackResult(
                exit_code=exit_code,
                action="quit",
                data={"episode": final_episode, "error_hint": error_hint},
            )
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

    @staticmethod
    def _has_mpv_load_error(stderr_output: str, log_output: str) -> bool:
        """Detect file-loading failures that may still return MPV exit code 0."""
        haystack = f"{stderr_output}\n{log_output}".lower()
        error_signatures = [
            "exiting... (errors when loading file)",
            "failed to open",
            "file not found",
            "403 forbidden",
            "http error 403",
            "http error 404",
            "unable to open url",
        ]
        return any(signature in haystack for signature in error_signatures)

    @staticmethod
    def _classify_mpv_error(stderr_output: str, log_output: str) -> str | None:
        """Return a user-facing error hint based on MPV logs."""
        haystack = f"{stderr_output}\n{log_output}".lower()

        if "404" in haystack or "not found" in haystack:
            return "Episódio indisponível nesta fonte (HTTP 404)."
        if "403" in haystack or "forbidden" in haystack:
            return "A fonte bloqueou o acesso ao vídeo (HTTP 403)."
        if "timed out" in haystack or "timeout" in haystack:
            return "Timeout ao carregar o vídeo desta fonte."
        if "errors when loading file" in haystack or "failed to open" in haystack:
            return "Falha ao carregar vídeo nesta fonte."
        return None

    def _send_mpv_command(self, sock: socket.socket, command: str, args: list) -> None:
        """Send JSON-RPC command to MPV via IPC socket."""
        request = {"command": [command] + args}
        try:
            message = json.dumps(request) + "\n"
            sock.sendall(message.encode("utf-8"))
        except Exception as e:
            logger.info(f"Failed to send MPV command: {e}")


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
    """Play video using python-mpv and return exit code."""
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
