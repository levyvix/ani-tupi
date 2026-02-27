"""Tests for Manga PDF reader launcher functionality."""

import pytest
import subprocess
from unittest.mock import patch, MagicMock

from utils.manga_reader import (
    is_zathura_running,
    find_pdf_reader,
    open_pdf_reader,
)


@pytest.fixture
def temp_pdf_file(tmp_path):
    """Create a temporary dummy PDF file."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_text("dummy pdf content")
    return pdf_file


class TestMangaReader:
    """Test manga reader utilities."""

    @patch("subprocess.run")
    def test_is_zathura_running_true(self, mock_run):
        """Should return True if Zathura is running."""
        mock_run.return_value = MagicMock(returncode=0)
        assert is_zathura_running() is True
        mock_run.assert_called_with(
            ["pgrep", "-f", "zathura"], capture_output=True, text=True, timeout=2.0
        )

    @patch("subprocess.run")
    def test_is_zathura_running_false(self, mock_run):
        """Should return False if Zathura is not running."""
        mock_run.return_value = MagicMock(returncode=1)
        assert is_zathura_running() is False

    @patch("subprocess.run")
    def test_is_zathura_running_fallback(self, mock_run):
        """Should use `ps aux` fallback if `pgrep` is not found."""
        # Configure pgrep call to raise FileNotFoundError, and ps aux to return success
        mock_run.side_effect = [
            FileNotFoundError,
            MagicMock(stdout="...zathura...", returncode=0),
        ]

        assert is_zathura_running() is True

        # Verify pgrep was called first
        assert mock_run.call_args_list[0].args == (["pgrep", "-f", "zathura"],)
        assert mock_run.call_args_list[0].kwargs == {
            "capture_output": True,
            "text": True,
            "timeout": 2.0,
        }

        # Verify ps aux was called second
        assert mock_run.call_args_list[1].args == (["ps", "aux"],)
        assert mock_run.call_args_list[1].kwargs == {
            "capture_output": True,
            "text": True,
            "timeout": 5.0,
        }

        # Verify ps aux was called second
        mock_run.call_args_list[1].assert_called_with(
            ["ps", "aux"], capture_output=True, text=True, timeout=5.0
        )

        mock_run.assert_called_with(["ps", "aux"], capture_output=True, text=True, timeout=5.0)

    @patch("shutil.which")
    def test_find_pdf_reader_user_preference(self, mock_which):
        """Should prioritize user-configured reader."""
        # Patch the global settings object directly
        with patch("models.config.settings.manga.pdf_reader", "myreader"):  # noqa
            mock_which.side_effect = lambda x: "/usr/bin/myreader" if x == "myreader" else None
            reader = find_pdf_reader()
            assert reader == "myreader"
            mock_which.assert_called_with("myreader")

    @patch("shutil.which")
    def test_find_pdf_reader_priority_list(self, mock_which):
        """Should follow configured priority list for auto-detection."""
        # Patch the global settings object directly
        with patch("models.config.settings.manga.pdf_reader", None):  # No user preference # noqa
            with patch(
                "models.config.settings.manga.pdf_reader_priority",  # noqa
                ["nonexistent", "evince", "zathura"],
            ):
                mock_which.side_effect = lambda x: f"/usr/bin/{x}" if x == "evince" else None
                reader = find_pdf_reader()
                assert reader == "evince"
                # Verify the order of calls
                mock_which.assert_any_call("nonexistent")
                mock_which.assert_any_call("evince")

    @patch("shutil.which", return_value=None)
    def test_find_pdf_reader_not_found(self, mock_which):
        """Should return None if no reader is found."""
        with patch("models.config.settings.manga.pdf_reader", None):  # noqa
            with patch("models.config.settings.manga.pdf_reader_priority", ["nonexistent"]):  # noqa
                reader = find_pdf_reader()
                assert reader is None
                mock_which.assert_called_with("nonexistent")

    @patch("subprocess.Popen", return_value=MagicMock())
    @patch("utils.manga_reader.find_pdf_reader", return_value="zathura")
    @patch("utils.manga_reader.ensure_zathura_config")
    @patch("builtins.print")
    @patch("utils.manga_reader.logger")
    def test_open_pdf_reader_success_zathura(
        self,
        mock_logger,
        mock_print,
        mock_ensure_config,
        mock_find_reader,
        mock_popen,
        temp_pdf_file,
    ):
        """Should open Zathura and configure it if enabled."""
        with patch("models.config.settings.manga.zathura_auto_config", True):  # noqa
            process = open_pdf_reader(temp_pdf_file)
            assert process is not None
            mock_find_reader.assert_called_once()
            mock_ensure_config.assert_called_once()
            mock_popen.assert_called_once_with(
                ["zathura", str(temp_pdf_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            mock_logger.warning.assert_not_called()
            mock_logger.error.assert_not_called()

    @patch("subprocess.Popen", return_value=MagicMock())
    @patch("utils.manga_reader.find_pdf_reader", return_value="evince")
    @patch("utils.manga_reader.ensure_zathura_config")  # Should not be called for evince
    @patch("builtins.print")
    @patch("utils.manga_reader.logger")
    def test_open_pdf_reader_success_generic(
        self,
        mock_logger,
        mock_print,
        mock_ensure_config,
        mock_find_reader,
        mock_popen,
        temp_pdf_file,
    ):
        """Should open generic reader without Zathura config calls."""
        with patch(
            "models.config.settings.manga.zathura_auto_config", True
        ):  # Still shouldn't call ensure_config # noqa
            process = open_pdf_reader(temp_pdf_file)
            assert process is not None
            mock_find_reader.assert_called_once()
            mock_ensure_config.assert_not_called()
            mock_popen.assert_called_once_with(
                ["evince", str(temp_pdf_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            mock_logger.warning.assert_not_called()
            mock_logger.error.assert_not_called()

    @patch("utils.manga_reader.find_pdf_reader", return_value=None)
    @patch("builtins.print")
    @patch("utils.manga_reader.logger")
    def test_open_pdf_reader_no_reader_found(
        self, mock_logger, mock_print, mock_find_reader, temp_pdf_file
    ):
        """Should print error and return None if no reader found."""
        process = open_pdf_reader(temp_pdf_file)
        assert process is None
        mock_find_reader.assert_called_once()
        mock_print.assert_any_call(
            "⚠️  Nenhum leitor de PDF encontrado.\n"
            "   Instale um destes: zathura, evince, okular, ou mupdf\n"
            "   Ou configure manualmente: export ANI_TUPI__MANGA__PDF_READER=seu_leitor"
        )
        mock_print.assert_any_call(f"   PDF salvo em: {temp_pdf_file}")
        mock_logger.warning.assert_called_once()
        mock_logger.error.assert_not_called()

    @patch("subprocess.Popen", side_effect=FileNotFoundError("reader not found"))
    @patch("utils.manga_reader.find_pdf_reader", return_value="zathura")
    @patch("builtins.print")
    @patch("utils.manga_reader.logger")
    def test_open_pdf_reader_popen_filenotfound(
        self, mock_logger, mock_print, mock_find_reader, mock_popen, temp_pdf_file
    ):
        """Should handle FileNotFoundError from Popen."""
        process = open_pdf_reader(temp_pdf_file)
        assert process is None
        mock_print.assert_any_call(
            "⚠️  Erro: PDF reader executable not found: zathura. Error: reader not found"
        )
        mock_print.assert_any_call(f"   PDF salvo em: {temp_pdf_file}")
        mock_logger.error.assert_called_once()

    @patch("subprocess.Popen", side_effect=subprocess.CalledProcessError(1, "cmd"))
    @patch("utils.manga_reader.find_pdf_reader", return_value="zathura")
    @patch("builtins.print")
    @patch("utils.manga_reader.logger")
    def test_open_pdf_reader_popen_calledprocesserror(
        self,
        mock_logger,
        mock_print,
        mock_find_reader,
        mock_popen,
        temp_pdf_file,
    ):
        """Should handle CalledProcessError from Popen."""
        process = open_pdf_reader(temp_pdf_file)
        assert process is None
        mock_print.assert_any_call(
            "⚠️  Erro: PDF reader zathura exited with error code 1. Error: Command 'cmd' returned non-zero exit status 1."
        )
        mock_print.assert_any_call(f"   PDF salvo em: {temp_pdf_file}")
        mock_logger.error.assert_called_once()

    @patch("subprocess.Popen", side_effect=subprocess.TimeoutExpired("cmd", 1))
    @patch("utils.manga_reader.find_pdf_reader", return_value="zathura")
    @patch("builtins.print")
    @patch("utils.manga_reader.logger")
    def test_open_pdf_reader_popen_timeoutexpired(
        self,
        mock_logger,
        mock_print,
        mock_find_reader,
        mock_popen,
        temp_pdf_file,
    ):
        """Should handle TimeoutExpired from Popen."""
        process = open_pdf_reader(temp_pdf_file)
        assert process is None
        mock_print.assert_any_call("⚠️  Erro: PDF reader zathura took too long to launch.")
        mock_print.assert_any_call(f"   PDF salvo em: {temp_pdf_file}")
        mock_logger.error.assert_called_once()
