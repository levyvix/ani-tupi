"""MPV log management: directory, rotation, preparation, and error classification."""

import uuid
from datetime import datetime
from pathlib import Path

from models.config import get_data_path, settings


class MPVLogManager:
    """Manage persistent MPV logs and classify MPV error output."""

    def get_mpv_logs_dir(self) -> Path:
        """Return directory for persistent MPV logs."""
        logs_dir = get_data_path() / "mpv-logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def rotate_mpv_logs(self, max_files: int = 7, max_total_bytes: int = 20 * 1024 * 1024) -> None:
        """Rotate MPV logs by file count and total size.

        Keeps newest files and removes older ones first.
        """
        try:
            logs_dir = self.get_mpv_logs_dir()
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

    def prepare_mpv_log_file(self) -> str:
        """Create a new MPV log file path and rotate old logs."""
        configured_log = settings.mpv_log_file
        if configured_log:
            return configured_log

        self.rotate_mpv_logs()
        logs_dir = self.get_mpv_logs_dir()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        return str(logs_dir / f"mpv-{ts}-{str(uuid.uuid4())[:8]}.log")

    @staticmethod
    def has_mpv_load_error(stderr_output: str, log_output: str) -> bool:
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
    def classify_mpv_error(stderr_output: str, log_output: str) -> str | None:
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
