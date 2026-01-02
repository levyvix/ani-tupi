"""Tests for video_player module with python-mpv integration."""

import pytest
from unittest.mock import MagicMock, patch
from utils.video_player import play_video


class TestPlayVideoDebugMode:
    """Test debug mode behavior."""

    def test_debug_mode_returns_zero(self):
        """Debug mode should return 0 without launching MPV."""
        exit_code = play_video("http://example.com/video.mp4", debug=True)
        assert exit_code == 0
        assert isinstance(exit_code, int)

    def test_debug_mode_ignores_url(self):
        """Debug mode should work with any URL."""
        exit_code = play_video("invalid://url", debug=True)
        assert exit_code == 0


class TestPlayVideoWithMPV:
    """Test playback with python-mpv."""

    @patch("utils.video_player.mpv.MPV")
    def test_normal_playback(self, mock_mpv_class):
        """Should return exit code 0 for normal playback."""
        mock_player = MagicMock()
        mock_mpv_class.return_value = mock_player
        mock_player.wait_for_playback.return_value = None

        exit_code = play_video("http://example.com/video.mp4")

        assert exit_code == 0
        assert isinstance(exit_code, int)
        mock_player.play.assert_called_once_with("http://example.com/video.mp4")
        mock_player.wait_for_playback.assert_called_once()

    @patch("utils.video_player.mpv.MPV")
    def test_playback_error(self, mock_mpv_class):
        """Should return exit code 2 on playback error."""
        mock_player = MagicMock()
        mock_player.play.side_effect = Exception("Network error")
        mock_mpv_class.return_value = mock_player

        exit_code = play_video("http://example.com/video.mp4")

        assert exit_code == 2  # Error code

    @patch("utils.video_player.mpv.MPV")
    def test_shutdown_error_returns_abort(self, mock_mpv_class):
        """Should return exit code 3 on shutdown (user abort)."""
        # Create a custom exception class for ShutdownError
        class FakeShutdownError(Exception):
            pass

        mock_player = MagicMock()
        mock_player.wait_for_playback.side_effect = FakeShutdownError("User aborted")
        mock_mpv_class.return_value = mock_player

        # Patch mpv.ShutdownError to our fake class
        with patch("utils.video_player.mpv.ShutdownError", FakeShutdownError):
            exit_code = play_video("http://example.com/video.mp4")

        # Should return abort code
        assert exit_code == 3

    @patch("utils.video_player.mpv.MPV")
    def test_file_not_found(self, mock_mpv_class):
        """Should raise OSError if mpv is not installed."""
        mock_player = MagicMock()
        mock_player.play.side_effect = FileNotFoundError("mpv not found")
        mock_mpv_class.return_value = mock_player

        with pytest.raises(OSError):
            play_video("http://example.com/video.mp4")


class TestPlayVideoConfiguration:
    """Test MPV configuration."""

    @patch("utils.video_player.mpv.MPV")
    def test_default_configuration(self, mock_mpv_class):
        """Should apply correct default MPV configuration."""
        mock_player = MagicMock()
        mock_mpv_class.return_value = mock_player
        mock_player.wait_for_playback.return_value = None

        play_video("http://example.com/video.mp4")

        # Verify MPV was initialized with correct parameters
        mock_mpv_class.assert_called_once()
        call_kwargs = mock_mpv_class.call_args[1]

        assert call_kwargs["fullscreen"] is True
        assert call_kwargs["cursor_autohide_fs_only"] is True
        assert call_kwargs["ytdl"] is True
        assert call_kwargs["cache"] is True
        assert call_kwargs["speed"] == 1.8
        assert call_kwargs["input_default_bindings"] is True
        assert call_kwargs["input_vo_keyboard"] is True
        assert call_kwargs["osc"] is True
        assert "bestvideo" in call_kwargs["ytdl_format"]

    @patch("utils.video_player.mpv.MPV")
    def test_custom_ytdl_format(self, mock_mpv_class):
        """Should use custom yt-dlp format when provided."""
        mock_player = MagicMock()
        mock_mpv_class.return_value = mock_player
        mock_player.wait_for_playback.return_value = None

        custom_format = "best[height<=480]"
        play_video("http://example.com/video.mp4", ytdl_format=custom_format)

        call_kwargs = mock_mpv_class.call_args[1]
        assert call_kwargs["ytdl_format"] == custom_format


class TestPlayVideoReturnValue:
    """Test return value format."""

    @patch("utils.video_player.mpv.MPV")
    def test_returns_integer(self, mock_mpv_class):
        """Should return an integer exit code."""
        mock_player = MagicMock()
        mock_mpv_class.return_value = mock_player
        mock_player.wait_for_playback.return_value = None

        result = play_video("http://example.com/video.mp4")

        assert isinstance(result, int)
        assert result >= 0

    @patch("utils.video_player.mpv.MPV")
    def test_exit_codes_are_valid(self, mock_mpv_class):
        """Exit codes should be 0, 2, or 3."""
        mock_player = MagicMock()
        mock_mpv_class.return_value = mock_player

        # Test normal exit (0)
        mock_player.wait_for_playback.return_value = None
        exit_code = play_video("http://example.com/video.mp4")
        assert exit_code in [0, 2, 3]

        # Test error (2)
        mock_player.play.side_effect = Exception("Error")
        exit_code = play_video("http://example.com/video.mp4")
        assert exit_code == 2


class TestPlayVideoCleanup:
    """Test player cleanup."""

    @patch("utils.video_player.mpv.MPV")
    def test_player_terminate_called(self, mock_mpv_class):
        """Should call player.terminate() in finally block."""
        mock_player = MagicMock()
        mock_mpv_class.return_value = mock_player
        mock_player.wait_for_playback.return_value = None

        play_video("http://example.com/video.mp4")

        # Verify terminate was called
        mock_player.terminate.assert_called_once()

    @patch("utils.video_player.mpv.MPV")
    def test_player_terminate_called_on_error(self, mock_mpv_class):
        """Should call player.terminate() even if error occurs."""
        mock_player = MagicMock()
        mock_mpv_class.return_value = mock_player
        mock_player.play.side_effect = Exception("Error")

        play_video("http://example.com/video.mp4")

        # Verify terminate was called despite error
        mock_player.terminate.assert_called_once()
