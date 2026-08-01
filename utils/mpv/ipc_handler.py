"""IPC socket lifecycle, event loop, command sending, and keybinding actions."""

from __future__ import annotations

import json
import platform
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Callable, NamedTuple

from models.config import settings
from utils.logging import get_logger

if TYPE_CHECKING:
    from utils.mpv.launcher import MPVLauncher
    from utils.video_player import VideoPlaybackResult, VideoPlayer

logger = get_logger(__name__)


class NextSource(NamedTuple):
    """Next source picked from the episode's candidate cycle.

    Attributes:
        url: Playable URL, or the page URL when it still needs extraction.
        source: Source name.
        referrer: Referer associated with the candidate, if any.
        position: 1-indexed position of this source in the cycle.
        total: Number of distinct sources in the cycle.
    """

    url: str
    source: str
    referrer: str | None
    position: int
    total: int


def select_next_source(
    candidates: list[tuple[str, str, str | None]] | None,
    current_source: str | None,
) -> NextSource | None:
    """Pick the source that follows *current_source* in the candidate cycle.

    Candidates may repeat a source with several quality ranks; the cycle keeps one
    entry per source name (the first, best-quality one) in the original priority
    order and wraps around at the end. A ``current_source`` absent from the cycle
    starts from the first entry.

    Returns:
        The next source, or ``None`` when there is no cycle or it holds a single
        source (nothing to switch to).
    """
    if not candidates:
        return None

    cycle: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    for url, source, referrer in candidates:
        if source in seen:
            continue
        seen.add(source)
        cycle.append((url, source, referrer))

    if len(cycle) < 2:
        return None

    current_idx = next((i for i, entry in enumerate(cycle) if entry[1] == current_source), -1)
    next_idx = (current_idx + 1) % len(cycle)
    url, source, referrer = cycle[next_idx]
    return NextSource(url, source, referrer, next_idx + 1, len(cycle))


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
            case "next-source":
                # Handled in-place by ipc_event_loop; nothing to hand back to the caller.
                return None
            case "toggle-sub-dub":
                return VideoPlaybackResult(
                    exit_code=0,
                    action="toggle-sub-dub",
                    data={"message": "Sub/Dub toggle (if available)"},
                )
            case _:
                return None

    @staticmethod
    def _resolve_candidate_url(
        candidate: NextSource,
        extractor: Callable[[str, str], str | list[str] | None] | None,
    ) -> tuple[str | None, str | None]:
        """Resolve a candidate to a playable URL plus the referrer to use.

        Without an extractor the candidate already holds a video URL. With one, the
        candidate's URL is an episode page resolved on demand (the page then doubles
        as referrer when the candidate has none).
        """
        if extractor is None:
            return candidate.url, candidate.referrer

        try:
            resolved = extractor(candidate.url, candidate.source)
        except Exception as e:
            logger.debug(f"[{candidate.source}] erro ao extrair vídeo na troca de fonte: {e!r}")
            return None, None

        urls = [resolved] if isinstance(resolved, str) else list(resolved or [])
        if not urls:
            return None, None
        return urls[0], candidate.referrer or candidate.url

    def _restart_without_ipc(
        self,
        mpv_process: subprocess.Popen,
        episode_context: dict,
    ) -> VideoPlaybackResult:
        """Stop the IPC process and restart MPV without IPC."""
        if mpv_process.poll() is None:
            mpv_process.terminate()
            try:
                mpv_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                mpv_process.kill()

        return self._player._play_video_without_ipc(
            episode_context.get("url", ""),
            debug=False,
            referrer=episode_context.get("referrer"),
        )

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
                    return self._restart_without_ipc(mpv_process, episode_context)

                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect(socket_path)
                break
            except (FileNotFoundError, ConnectionRefusedError, OSError):
                time.sleep(0.1)
                continue

        if not sock:
            logger.debug("[PLAYBACK DEBUG] IPC socket failed; restarting without IPC.")
            return self._restart_without_ipc(mpv_process, episode_context)

        # Observe playback position so a source switch can resume where it stopped.
        # Purely reactive: the loop never blocks on a get_property round-trip.
        self.send_mpv_command(sock, "observe_property", [1, "time-pos"])
        last_time_pos: float | None = None

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
                            if msg.get("event") == "property-change":
                                if msg.get("name") == "time-pos":
                                    pos = msg.get("data")
                                    if isinstance(pos, (int, float)):
                                        last_time_pos = float(pos)
                                continue
                            if msg.get("event") == "client-message":
                                args = msg.get("args", [])
                                if args:
                                    action = args[0]
                                    if action == "mark-next":
                                        from services.core.history_service import (
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

                                    elif action == "next-source":
                                        candidates = episode_context.get("candidates")
                                        next_source = select_next_source(
                                            candidates, episode_context.get("source")
                                        )

                                        if not candidates:
                                            self.send_mpv_command(
                                                sock,
                                                "show-text",
                                                ["Troca de fonte não disponível"],
                                            )
                                            continue

                                        if next_source is None:
                                            self.send_mpv_command(
                                                sock,
                                                "show-text",
                                                ["Não há outra fonte disponível"],
                                            )
                                            continue

                                        self.send_mpv_command(
                                            sock,
                                            "show-text",
                                            [
                                                f"Trocando para {next_source.source} "
                                                f"({next_source.position}/{next_source.total})..."
                                            ],
                                        )

                                        new_url, new_referrer = self._resolve_candidate_url(
                                            next_source,
                                            episode_context.get("candidates_extractor"),
                                        )
                                        if not new_url:
                                            self.send_mpv_command(
                                                sock,
                                                "show-text",
                                                [f"Falha ao carregar a fonte {next_source.source}"],
                                            )
                                            logger.info(
                                                f"❌ Falha ao trocar para a fonte "
                                                f"{next_source.source}"
                                            )
                                            continue

                                        if last_time_pos:
                                            self.send_mpv_command(
                                                sock,
                                                "set_property",
                                                ["start", f"{last_time_pos:.3f}"],
                                            )
                                        if new_referrer != episode_context.get("referrer"):
                                            self.send_mpv_command(
                                                sock,
                                                "set_property",
                                                ["referrer", new_referrer or ""],
                                            )

                                        self.send_mpv_command(
                                            sock, "loadfile", [new_url, "replace"]
                                        )
                                        self.send_mpv_command(
                                            sock, "set_property", ["start", "none"]
                                        )

                                        episode_context["url"] = new_url
                                        episode_context["source"] = next_source.source
                                        episode_context["referrer"] = new_referrer
                                        logger.info(
                                            f"🔄 Trocando para a fonte {next_source.source} "
                                            f"({next_source.position}/{next_source.total})"
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
                from services.core.history_service import save_history_from_event

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
                    data={"episode": episode_number, "source": source},
                )

            final_episode = episode_context.get("episode_number", 1)
            return VideoPlaybackResult(
                exit_code=exit_code,
                action="quit",
                data={
                    "episode": final_episode,
                    "error_hint": error_hint,
                    "source": episode_context.get("source"),
                },
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
