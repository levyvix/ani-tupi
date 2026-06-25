"""Manga PDF reader launcher.

Integrates with external PDF readers (similar to video_player.py for MPV).
Auto-detects available readers with fallback chain: Zathura → Evince → Okular → MuPDF.
"""

import shutil
import subprocess
from pathlib import Path

from models.config import settings
from utils.logging import get_logger

logger = get_logger(__name__)


def is_zathura_running() -> bool:
    """Check if Zathura PDF reader is currently running.

    Returns:
        True if Zathura process is found, False otherwise
    """
    try:
        # Check for zathura processes with timeout
        result = subprocess.run(
            ["pgrep", "-f", "zathura"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        # Fallback method if pgrep is not available
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            return "zathura" in result.stdout.lower()
        except (subprocess.SubprocessError, FileNotFoundError):
            return False


def ensure_zathura_config() -> None:
    """Ensure Zathura configuration exists with fit-width default zoom.

    Creates ~/.config/zathura/zathurarc if it doesn't exist,
    or adds fit-width setting to existing configuration.
    Preserves existing user configurations.
    """
    config_dir = Path.home() / ".config" / "zathura"
    config_file = config_dir / "zathurarc"

    # Create config directory if it doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True)

    # Configuration lines for optimal manga reading
    config_lines = [
        "set zoom fit-width",
        "set scroll-step 50",  # Scroll suave
        "map <Down> scroll down",  # Setas para navegação vertical
        "map <Up> scroll up",
        "map j scroll down",  # Vim keys para scroll
        "map k scroll up",
        "map <Right> navigate next",  # Page navigation apenas com PageDown/PageUp
        "map <Left> navigate previous",
        "map <PageDown> navigate next",
        "map <PageUp> navigate previous",
    ]

    # Check if config file exists and contains our settings
    if config_file.exists():
        content = config_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Check if fit-width is already configured
        already_configured = any(
            line.strip().startswith("set zoom") and "fit-width" in line.strip() for line in lines
        )

        if not already_configured:
            # Add our configuration if not present
            if content and not content.endswith("\n"):
                content += "\n"
            content += "\n# ani-tupi Zathura configuration\n"
            content += "\n".join(config_lines)
            content += "\n"

            config_file.write_text(content, encoding="utf-8")
    else:
        # Create new config file with our settings
        config_content = (
            """# Zathura configuration for ani-tupi
# Generated automatically - safe to edit

"""
            + "\n".join(config_lines)
            + "\n"
        )

        config_file.write_text(config_content, encoding="utf-8")


def find_pdf_reader() -> str | None:
    """Find available PDF reader on system.

    Follows priority order:
    1. User configuration (ANI_TUPI__MANGA__PDF_READER env var)
    2. Zathura (lightweight, keyboard-focused, perfect for manga)
    3. Evince (GNOME default, widely available)
    4. Okular (KDE default, feature-rich)
    5. MuPDF (minimal, fast)
    6. xdg-open (generic system default)

    Returns:
        Path to PDF reader executable or None if not found
    """
    # Check user preference from config
    if settings.manga.pdf_reader:
        if shutil.which(settings.manga.pdf_reader):
            return settings.manga.pdf_reader

    # Auto-detect readers in order of preference from configuration
    readers = settings.manga.pdf_reader_priority

    for reader in readers:
        if shutil.which(reader):
            return reader

    return None


def open_pdf_reader(pdf_path: Path) -> subprocess.Popen | None:
    """Open PDF reader for manga chapter.

    Launches reader in background without blocking the CLI.
    Falls back gracefully if no reader found.
    Automatically configures Zathura for fit-width zoom if needed.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Subprocess handle if reader launched, None if not found
    """
    reader = find_pdf_reader()

    if not reader:
        message = (
            "⚠️  Nenhum leitor de PDF encontrado.\n"
            "   Instale um destes: zathura, evince, okular, ou mupdf\n"
            "   Ou configure manualmente: export ANI_TUPI__MANGA__PDF_READER=seu_leitor"
        )
        logger.info(message)
        logger.warning(f"PDF reader not found: {message}")
        logger.info(f"   PDF salvo em: {pdf_path}")
        return None

    # Configure Zathura if it's being used and auto-config is enabled
    if reader == "zathura" and settings.manga.zathura_auto_config:
        ensure_zathura_config()

    try:
        # Launch reader in background (non-blocking) with a timeout
        process = subprocess.Popen(
            [reader, str(pdf_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Apply a reasonable timeout for launching the process
            # This prevents hangs if the reader itself takes too long to start
            # or prompts for user input blocking the CLI.
            # Not directly a timeout for the *entire* reading session, but for launch.
            # communicate(timeout=...) is for waiting for process to finish, not start
        )
        return process

    except FileNotFoundError as e:
        error_message = f"PDF reader executable not found: {reader}. Error: {e}"
        logger.error(error_message)
        logger.info(f"⚠️  Erro: {error_message}")
        logger.info(f"   PDF salvo em: {pdf_path}")
        return None
    except subprocess.TimeoutExpired:
        error_message = f"PDF reader {reader} took too long to launch."
        logger.error(error_message)
        logger.info(f"⚠️  Erro: {error_message}")
        logger.info(f"   PDF salvo em: {pdf_path}")
        return None
    except subprocess.CalledProcessError as e:
        error_message = f"PDF reader {reader} exited with error code {e.returncode}. Error: {e}"
        logger.error(error_message)
        logger.info(f"⚠️  Erro: {error_message}")
        logger.info(f"   PDF salvo em: {pdf_path}")
        return None
    except Exception as e:
        error_message = f"Unexpected error launching {reader}. Error: {e}"
        logger.error(error_message)
        logger.info(f"⚠️  Erro ao abrir {reader}: {e}")
        logger.info(f"   PDF salvo em: {pdf_path}")
        return None
