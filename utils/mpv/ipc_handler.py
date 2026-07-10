"""IPC socket lifecycle, event loop, command sending, and keybinding actions."""

from __future__ import annotations

import json
import platform
import socket
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from models.config import settings
from utils.logging import get_logger

if TYPE_CHECKING:
    import subprocess

    from utils.mpv.launcher import MPVLauncher
    from utils.video_player import VideoPlaybackResult, VideoPlayer

logger = get_logger(__name__)


class IPCHandler:
    """Handle MPV IPC socket communication and keybinding-driven navigation."""

    def __init__(self, player: VideoPlayer, launcher: MPVLauncher):
        self._player = player
        self._launcher = launcher

    def create_ipc_socket_path(self) -> str:
        """Generate platform-specific IPC socket path for MPV communication."""
        unique_id = str(uuid.uuid4())[:8]
        system = platform.system()

        if system == "Windows":
            return f"\\\\.\\pipe\\ani-tupi-mpv-{unique_id}"
        else:
            temp_dir = tempfile.gettempdir()
            return str(Path(temp_dir) / f"ani-tupi-mpv-{unique_id}.sock")

    def cleanup_ipc_socket(self, path: str) -> None:
        """Clean up IPC socket file/pipe without errors."""
        if not path:
            return

        try:
            socket_path = Path(path)
            if socket_path.exists():
                socket_path.unlink()
        except (OSError, FileNotFoundError):
            pass

    def handle_keybinding_action(
        self,
        action: str,
        context: dict,
    ) -> VideoPlaybackResult | None:
        """Handle keybinding action from MPV and return navigation result."""
        from utils.video_player import VideoPlaybackResult

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
                self._player.autoplay = not self._player.autoplay
                return VideoPlaybackResult(
                    exit_code=0,
                    action="toggle-autoplay",
                    data={"enabled": self._player.autoplay},
                )
            case "toggle-sub-dub":
                return VideoPlaybackResult(
                    exit_code=0,
                    action="toggle-sub-dub",
                    data={"message": "Sub/Dub toggle (if available)"},
                )
            case _:
                return None

    def ipc_event_loop(
        self,
        mpv_process: subprocess.Popen,
        socket_path: str,
        episode_context: dict,
        timeout: float = 1.0,
    ) -> VideoPlaybackResult:
        """Monitor IPC socket for keybinding events from MPV."""
        from utils.video_player import VideoPlaybackResult, _format_episode_progress

        # Wait for socket to be ready
        max_wait = 5.0
        start_time = time.time()
        sock = None

        while time.time() - start_time < max_wait:
            try:
                if platform.system() == "Windows":
                    # Fallback to legacy on Windows for now
                    url = episode_context.get("url", "")
                    return self._player._play_video_legacy(url, debug=False)

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
            return self._player._play_video_legacy(url, debug=False)

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
                                        self.send_mpv_command(
                                            sock,
                                            "show-text",
                                            [f"Buscando Episódio {progress_str}..."],
                                        )
                                        next_url = rep.search_player(
                                            anime_title, next_episode_number
                                        )

                                        if next_url:
                                            self.send_mpv_command(
                                                sock, "loadfile", [next_url, "replace"]
                                            )
                                            self.send_mpv_command(
                                                sock,
                                                "show-text",
                                                [f"▶️ Reproduzindo Episódio {progress_str}"],
                                            )
                                            # Update MPV title to show new episode number
                                            new_title = (
                                                f"{anime_title} Episode {next_episode_number}"
                                            )
                                            self.send_mpv_command(
                                                sock,
                                                "set_property",
                                                ["force-media-title", new_title],
                                            )
                                            episode_context["episode_number"] = next_episode_number
                                            episode_context["url"] = next_url
                                            logger.info(f"▶️  Reproduzindo Episódio {progress_str}")

                                            continue
                                        else:
                                            self.send_mpv_command(
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
                                            self.send_mpv_command(
                                                sock,
                                                "show-text",
                                                [f"Buscando Episódio {progress_str}..."],
                                            )
                                            prev_url = rep.search_player(
                                                anime_title, prev_episode_number
                                            )

                                            if prev_url:
                                                self.send_mpv_command(
                                                    sock,
                                                    "loadfile",
                                                    [prev_url, "replace"],
                                                )
                                                self.send_mpv_command(
                                                    sock,
                                                    "show-text",
                                                    [f"⏪ Voltando para Episódio {progress_str}"],
                                                )
                                                # Update MPV title to show new episode number
                                                new_title = (
                                                    f"{anime_title} Episode {prev_episode_number}"
                                                )
                                                self.send_mpv_command(
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
                                                self.send_mpv_command(
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
                                            self.send_mpv_command(
                                                sock,
                                                "show-text",
                                                ["Não há episódios anteriores"],
                                            )

                                    elif action == "reload-episode":
                                        current_url = episode_context.get("url")
                                        if current_url:
                                            self.send_mpv_command(
                                                sock,
                                                "loadfile",
                                                [current_url, "replace"],
                                            )
                                            self.send_mpv_command(
                                                sock,
                                                "show-text",
                                                ["Reloading episode..."],
                                            )
                                            continue

                                    elif action == "toggle-autoplay":
                                        self._player.autoplay = not self._player.autoplay
                                        status = (
                                            "ATIVADO" if self._player.autoplay else "DESATIVADO"
                                        )
                                        message = f"Auto-play {status} (válido para toda a sessão)"
                                        self.send_mpv_command(sock, "show-text", [message, "3000"])
                                        logger.info(f"{message}")
                                        continue

                                    result = self.handle_keybinding_action(action, episode_context)
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
            debug_mode = settings.debug_mpv
            if hasattr(mpv_process, "stderr") and mpv_process.stderr:
                try:
                    stderr_output = mpv_process.stderr.read()
                except (OSError, ValueError):
                    pass

            log_output = ""
            last_log_file = self._launcher.last_mpv_log_file
            if last_log_file:
                try:
                    with open(last_log_file, encoding="utf-8", errors="ignore") as f:
                        log_output = f.read()
                except OSError:
                    log_output = ""

            # MPV can sometimes exit with code 0 even when file loading failed.
            # Detect this signature and treat it as playback failure.
            if exit_code == 0 and self._launcher._log_manager.has_mpv_load_error(
                stderr_output, log_output
            ):
                exit_code = 2

            error_hint = self._launcher._log_manager.classify_mpv_error(stderr_output, log_output)

            if debug_mode:
                logger.info(f"   🧪 MPV debug mode ativo | exit_code={exit_code}")
                if stderr_output.strip():
                    stderr_lines = [
                        line.strip() for line in stderr_output.split("\n") if line.strip()
                    ]
                    logger.info("   🧪 MPV stderr (últimas linhas):")
                    for line in stderr_lines[-10:]:
                        logger.info(f"      {line[:160]}")

                if last_log_file:
                    logger.info(f"   🧪 MPV log file salvo em: {last_log_file}")
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
                if last_log_file:
                    logger.info(f"   📝 MPV log: {last_log_file}")
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

            if self._player.autoplay and exit_code == 0:
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

    def send_mpv_command(self, sock: socket.socket, command: str, args: list) -> None:
        """Send JSON-RPC command to MPV via IPC socket."""
        request = {"command": [command] + args}
        try:
            message = json.dumps(request) + "\n"
            sock.sendall(message.encode("utf-8"))
        except Exception as e:
            logger.info(f"Failed to send MPV command: {e}")
