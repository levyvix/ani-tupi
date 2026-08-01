"""Integration tests for the Shift+F source switch in the MPV IPC event loop.

These drive the real ``IPCHandler.ipc_event_loop`` over a real UNIX socket: a tiny
fake "MPV" accepts the connection, pushes IPC events, and records every command the
handler sends back. Only the MPV process itself is faked.
"""

import json
import socket
import threading

import pytest

from utils.video_player import VideoPlayer


class FakeMPVProcess:
    """Stands in for the MPV subprocess: alive while the socket stays open."""

    stderr = None

    def __init__(self):
        self.returncode = 0

    def poll(self):
        return None


class FakeMPV:
    """UNIX-socket server that feeds IPC events and records received commands."""

    def __init__(self, socket_path: str, events: list[dict]):
        self.socket_path = socket_path
        self.events = events
        self.commands: list[list] = []
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(socket_path)
        self._server.listen(1)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._thread.join(timeout=5)
        self._server.close()

    def _run(self):
        conn, _ = self._server.accept()
        try:
            conn.settimeout(1.0)
            for event in self.events:
                conn.sendall((json.dumps(event) + "\n").encode("utf-8"))
            buffer = ""
            while True:
                try:
                    chunk = conn.recv(4096).decode("utf-8", errors="ignore")
                except TimeoutError:
                    break
                if not chunk:
                    break
                buffer += chunk
            for line in buffer.splitlines():
                if line.strip():
                    self.commands.append(json.loads(line)["command"])
        finally:
            conn.close()


@pytest.fixture
def socket_path(tmp_path):
    return str(tmp_path / "mpv.sock")


def run_loop(socket_path: str, events: list[dict], episode_context: dict):
    """Run the real IPC loop against a fake MPV and return (result, commands)."""
    player = VideoPlayer()
    with FakeMPV(socket_path, events) as fake_mpv:
        result = player._ipc_event_loop(FakeMPVProcess(), socket_path, episode_context)
    return result, fake_mpv.commands


def commands_of(commands: list[list], name: str) -> list[list]:
    return [c for c in commands if c and c[0] == name]


class TestNextSourceSwitch:
    """Shift+F swaps the stream in place and updates the episode context."""

    def test_switch_sends_expected_command_sequence(self, socket_path):
        context = {
            "anime_title": "Test Anime",
            "episode_number": 3,
            "source": "anitube",
            "url": "https://video-anitube.mp4",
            "referrer": None,
            "candidates": [
                ("https://video-anitube.mp4", "anitube", None),
                ("https://video-animefire.mp4", "animefire", "https://page-animefire"),
            ],
            "candidates_extractor": None,
        }

        _, commands = run_loop(
            socket_path,
            [{"event": "client-message", "args": ["next-source"]}],
            context,
        )

        assert ["loadfile", "https://video-animefire.mp4", "replace"] in commands
        assert ["set_property", "referrer", "https://page-animefire"] in commands
        assert ["set_property", "start", "none"] in commands
        texts = [c[1] for c in commands_of(commands, "show-text")]
        assert "Trocando para animefire (2/2)..." in texts

        # Context now points at the new source; episode is untouched.
        assert context["source"] == "animefire"
        assert context["url"] == "https://video-animefire.mp4"
        assert context["referrer"] == "https://page-animefire"
        assert context["episode_number"] == 3

    def test_observed_time_pos_is_applied_as_start(self, socket_path):
        context = {
            "anime_title": "Test Anime",
            "episode_number": 1,
            "source": "anitube",
            "url": "https://video-anitube.mp4",
            "referrer": None,
            "candidates": [
                ("https://video-anitube.mp4", "anitube", None),
                ("https://video-animefire.mp4", "animefire", None),
            ],
            "candidates_extractor": None,
        }

        _, commands = run_loop(
            socket_path,
            [
                {"event": "property-change", "name": "time-pos", "data": 128.25},
                {"event": "client-message", "args": ["next-source"]},
            ],
            context,
        )

        start_cmds = [c for c in commands_of(commands, "set_property") if c[1] == "start"]
        assert start_cmds[0] == ["set_property", "start", "128.250"]
        # start is restored right after the swap so later loads are not offset.
        assert start_cmds[-1] == ["set_property", "start", "none"]
        assert commands.index(start_cmds[0]) < commands.index(
            ["loadfile", "https://video-animefire.mp4", "replace"]
        )

    def test_single_source_reports_no_alternative(self, socket_path):
        context = {
            "anime_title": "Test Anime",
            "episode_number": 1,
            "source": "anitube",
            "url": "https://hd.mp4",
            "referrer": None,
            "candidates": [
                ("https://hd.mp4", "anitube", None),
                ("https://sd.mp4", "anitube", None),
            ],
            "candidates_extractor": None,
        }

        _, commands = run_loop(
            socket_path,
            [{"event": "client-message", "args": ["next-source"]}],
            context,
        )

        texts = [c[1] for c in commands_of(commands, "show-text")]
        assert texts == ["Não há outra fonte disponível"]
        assert commands_of(commands, "loadfile") == []
        assert context["source"] == "anitube"

    def test_missing_candidates_reports_unavailable(self, socket_path):
        context = {
            "anime_title": "Test Anime",
            "episode_number": 1,
            "source": "anitube",
            "url": "https://hd.mp4",
            "referrer": None,
        }

        _, commands = run_loop(
            socket_path,
            [{"event": "client-message", "args": ["next-source"]}],
            context,
        )

        texts = [c[1] for c in commands_of(commands, "show-text")]
        assert texts == ["Troca de fonte não disponível"]
        assert commands_of(commands, "loadfile") == []

    def test_lazy_candidate_is_extracted_on_switch(self, socket_path):
        """With lazy sources the page URL is resolved only when the user switches."""
        extracted = []

        def extractor(page_url, source):
            extracted.append((page_url, source))
            return ["https://video-animefire.mp4"]

        context = {
            "anime_title": "Test Anime",
            "episode_number": 1,
            "source": "anitube",
            "url": "https://video-anitube.mp4",
            "referrer": "https://page-anitube",
            "candidates": [
                ("https://page-anitube", "anitube", None),
                ("https://page-animefire", "animefire", None),
            ],
            "candidates_extractor": extractor,
        }

        _, commands = run_loop(
            socket_path,
            [{"event": "client-message", "args": ["next-source"]}],
            context,
        )

        assert extracted == [("https://page-animefire", "animefire")]
        assert ["loadfile", "https://video-animefire.mp4", "replace"] in commands
        # The page doubles as referrer when the candidate has none.
        assert context["referrer"] == "https://page-animefire"

    def test_failed_extraction_keeps_current_source(self, socket_path):
        context = {
            "anime_title": "Test Anime",
            "episode_number": 1,
            "source": "anitube",
            "url": "https://video-anitube.mp4",
            "referrer": None,
            "candidates": [
                ("https://page-anitube", "anitube", None),
                ("https://page-animefire", "animefire", None),
            ],
            "candidates_extractor": lambda page_url, source: None,
        }

        _, commands = run_loop(
            socket_path,
            [{"event": "client-message", "args": ["next-source"]}],
            context,
        )

        texts = [c[1] for c in commands_of(commands, "show-text")]
        assert "Falha ao carregar a fonte animefire" in texts
        assert commands_of(commands, "loadfile") == []
        assert context["source"] == "anitube"


class TestHistoryAfterSwitch:
    """History must credit the source actually being watched."""

    def test_mark_next_after_switch_saves_new_source(self, socket_path, monkeypatch):
        saved = {}

        def fake_save_history_from_event(**kwargs):
            saved.update(kwargs)

        monkeypatch.setattr(
            "services.core.history_service.save_history_from_event",
            fake_save_history_from_event,
        )
        from services.repository import rep

        monkeypatch.setattr(rep, "search_player", lambda title, ep: "https://next-episode.mp4")

        context = {
            "anime_title": "Test Anime",
            "episode_number": 3,
            "total_episodes": 12,
            "source": "anitube",
            "url": "https://video-anitube.mp4",
            "referrer": None,
            "anilist_id": None,
            "candidates": [
                ("https://video-anitube.mp4", "anitube", None),
                ("https://video-animefire.mp4", "animefire", None),
            ],
            "candidates_extractor": None,
        }

        result, _ = run_loop(
            socket_path,
            [
                {"event": "client-message", "args": ["next-source"]},
                {"event": "client-message", "args": ["mark-next"]},
            ],
            context,
        )

        assert saved["source"] == "animefire"
        assert saved["episode_idx"] == 2
        assert result.data["source"] == "animefire"
