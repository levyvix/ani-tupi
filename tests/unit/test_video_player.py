"""Tests for VideoPlayer class and autoplay state."""

from unittest.mock import patch
from utils.video_player import VideoPlayer, VideoPlaybackResult


class TestVideoPlayer:
    """Test VideoPlayer class functionality."""

    def test_autoplay_initialization(self):
        """Should initialize with correct autoplay state."""
        player1 = VideoPlayer(autoplay=True)
        assert player1.autoplay is True

        player2 = VideoPlayer(autoplay=False)
        assert player2.autoplay is False

    def test_set_autoplay_state(self):
        """Should update autoplay state."""
        player = VideoPlayer(autoplay=False)
        player.set_autoplay_state(True)
        assert player.autoplay is True
        assert player.get_autoplay_state() is True

    def test_autoplay_toggle_via_keybinding(self):
        """Should toggle autoplay state when handling keybinding action."""
        player = VideoPlayer(autoplay=False)

        # Simulate Shift+A keybinding
        result = player._handle_keybinding_action("toggle-autoplay", {})

        assert player.autoplay is True
        assert result.action == "toggle-autoplay"
        assert result.data["enabled"] is True

        # Toggle again
        player._handle_keybinding_action("toggle-autoplay", {})
        assert player.autoplay is False

    def test_instance_isolation(self):
        """Autoplay state should be isolated between instances."""
        player1 = VideoPlayer(autoplay=True)
        player2 = VideoPlayer(autoplay=False)

        assert player1.autoplay is True
        assert player2.autoplay is False

        player1.set_autoplay_state(False)
        assert player1.autoplay is False
        assert player2.autoplay is False  # Still False

    @patch("utils.video_player.VideoPlayer._launch_mpv_with_ipc")
    @patch("utils.video_player.VideoPlayer._ipc_event_loop")
    def test_play_episode_uses_instance_state(self, mock_loop, mock_launch):
        """Should use instance state during playback."""
        player = VideoPlayer(autoplay=True)
        mock_loop.return_value = VideoPlaybackResult(exit_code=0, action="quit")

        player.play_episode(
            url="http://test.mp4",
            anime_title="Test",
            episode_number=1,
            total_episodes=12,
            source="test",
            use_ipc=True,
        )

        # Verify that the loop was called (the state is used inside it)
        assert mock_loop.called

    def test_play_video_raw_uses_mpv_subprocess(self, monkeypatch):
        """Should use the system MPV process instead of a Python binding."""

        class FakeProcess:
            returncode = 0

            @staticmethod
            def communicate():
                return "", ""

        player = VideoPlayer()
        calls = []

        def launch(url, *, ytdl_format=None, referrer=None):
            calls.append((url, ytdl_format, referrer))
            return FakeProcess()

        monkeypatch.setattr(player._launcher, "launch_mpv_without_ipc", launch)

        exit_code = player.play_video_raw(
            "https://example.com/video.m3u8",
            ytdl_format="best",
            referrer="https://example.com/",
        )

        assert exit_code == 0
        assert calls == [
            ("https://example.com/video.m3u8", "best", "https://example.com/"),
        ]

    def test_play_video_raw_detects_load_error(self, monkeypatch, tmp_path):
        """Should map an MPV load failure with exit code zero to code two."""

        class FakeProcess:
            returncode = 0

            @staticmethod
            def communicate():
                return "", ""

        log_file = tmp_path / "mpv.log"
        log_file.write_text("Exiting... (Errors when loading file)", encoding="utf-8")

        player = VideoPlayer()
        player._launcher.last_mpv_log_file = str(log_file)
        monkeypatch.setattr(
            player._launcher,
            "launch_mpv_without_ipc",
            lambda *args, **kwargs: FakeProcess(),
        )

        assert player.play_video_raw("https://example.com/missing.m3u8") == 2

    def test_detects_mpv_load_error_signature(self):
        """Should detect load failures even when MPV exits with code 0."""
        stderr = ""
        log = "[7.189][i][cplayer] Exiting... (Errors when loading file)"
        assert VideoPlayer._has_mpv_load_error(stderr, log) is True

    def test_ignores_non_error_log_content(self):
        """Should not flag normal playback logs as load error."""
        stderr = ""
        log = "[1.234][i][cplayer] playback restart complete"
        assert VideoPlayer._has_mpv_load_error(stderr, log) is False
