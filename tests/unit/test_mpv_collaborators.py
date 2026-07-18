"""Tests for the MPV playback collaborators extracted from VideoPlayer.

These exercise the now-isolated pure/near-pure pieces directly:
- MPVLogManager: log rotation and MPV error classification.
- MPVLauncher: input.conf generation.
"""

import time
from unittest.mock import patch

import pytest

from utils.mpv import MPVLauncher, MPVLogManager


class TestMPVLogManagerRotation:
    """Log rotation by file count and by total size."""

    def _make_log(self, logs_dir, name, size_bytes, mtime):
        path = logs_dir / name
        path.write_bytes(b"x" * size_bytes)
        import os

        os.utime(path, (mtime, mtime))
        return path

    def test_rotation_keeps_newest_by_count(self, tmp_path, monkeypatch):
        """Should keep only the newest `max_files` logs."""
        logs_dir = tmp_path / "mpv-logs"
        logs_dir.mkdir()

        manager = MPVLogManager()
        monkeypatch.setattr(manager, "get_mpv_logs_dir", lambda: logs_dir)

        base = time.time()
        for i in range(10):
            self._make_log(logs_dir, f"mpv-{i:02d}.log", 10, base + i)

        manager.rotate_mpv_logs(max_files=3, max_total_bytes=10 * 1024 * 1024)

        remaining = sorted(p.name for p in logs_dir.glob("mpv-*.log"))
        assert remaining == ["mpv-07.log", "mpv-08.log", "mpv-09.log"]

    def test_rotation_trims_by_total_size(self, tmp_path, monkeypatch):
        """Should remove oldest logs until under the byte budget."""
        logs_dir = tmp_path / "mpv-logs"
        logs_dir.mkdir()

        manager = MPVLogManager()
        monkeypatch.setattr(manager, "get_mpv_logs_dir", lambda: logs_dir)

        base = time.time()
        # 5 files of 100 bytes each = 500 bytes total
        for i in range(5):
            self._make_log(logs_dir, f"mpv-{i:02d}.log", 100, base + i)

        # Budget 250 bytes -> only 2 newest (200 bytes) should survive
        manager.rotate_mpv_logs(max_files=100, max_total_bytes=250)

        remaining = sorted(p.name for p in logs_dir.glob("mpv-*.log"))
        assert remaining == ["mpv-03.log", "mpv-04.log"]

    def test_rotation_no_op_when_within_limits(self, tmp_path, monkeypatch):
        """Should keep all files when within both limits."""
        logs_dir = tmp_path / "mpv-logs"
        logs_dir.mkdir()

        manager = MPVLogManager()
        monkeypatch.setattr(manager, "get_mpv_logs_dir", lambda: logs_dir)

        base = time.time()
        for i in range(3):
            self._make_log(logs_dir, f"mpv-{i:02d}.log", 10, base + i)

        manager.rotate_mpv_logs(max_files=7, max_total_bytes=10 * 1024 * 1024)

        remaining = list(logs_dir.glob("mpv-*.log"))
        assert len(remaining) == 3


class TestMPVLogManagerErrorClassification:
    """Error detection and user-facing classification from MPV output."""

    def test_has_load_error_detects_exit_zero_failure(self):
        stderr = ""
        log = "[7.189][i][cplayer] Exiting... (Errors when loading file)"
        assert MPVLogManager.has_mpv_load_error(stderr, log) is True

    def test_has_load_error_detects_403(self):
        assert MPVLogManager.has_mpv_load_error("HTTP error 403", "") is True

    def test_has_load_error_false_for_normal_log(self):
        log = "[1.234][i][cplayer] playback restart complete"
        assert MPVLogManager.has_mpv_load_error("", log) is False

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("HTTP 404 not found", "Episódio indisponível nesta fonte (HTTP 404)."),
            ("403 forbidden", "A fonte bloqueou o acesso ao vídeo (HTTP 403)."),
            ("connection timed out", "Timeout ao carregar o vídeo desta fonte."),
            ("failed to open stream", "Falha ao carregar vídeo nesta fonte."),
        ],
    )
    def test_classify_returns_expected_hint(self, text, expected):
        assert MPVLogManager.classify_mpv_error(text, "") == expected

    def test_classify_returns_none_for_clean_output(self):
        assert MPVLogManager.classify_mpv_error("all good", "playing") is None


class TestMPVLauncherProcess:
    """MPV command construction for IPC and plain playback."""

    @patch("utils.mpv.launcher.subprocess.Popen")
    def test_plain_launch_omits_ipc_and_keeps_requested_format(self, mock_popen):
        launcher = MPVLauncher(MPVLogManager())

        launcher.launch_mpv_without_ipc(
            "https://example.com/video.m3u8",
            ytdl_format="best",
        )

        args = mock_popen.call_args.args[0]
        assert "--ytdl-format=best" in args
        assert not any(arg.startswith("--input-ipc-server=") for arg in args)
        assert not any(arg.startswith("--input-conf=") for arg in args)


class TestMPVLauncherInputConf:
    """input.conf generation contains the expected keybindings."""

    def test_generate_input_conf_contains_keybindings(self):
        launcher = MPVLauncher(MPVLogManager())
        path, content = launcher.generate_input_conf()

        try:
            assert "shift+n script-message mark-next" in content
            assert "shift+p script-message previous" in content
            assert "shift+m script-message mark-menu" in content
            assert "shift+r script-message reload-episode" in content
            assert "shift+a script-message toggle-autoplay" in content
            assert "shift+t script-message toggle-sub-dub" in content

            # File is written to disk with the same content
            from pathlib import Path

            assert Path(path).read_text(encoding="utf-8") == content
        finally:
            from pathlib import Path

            Path(path).unlink(missing_ok=True)
