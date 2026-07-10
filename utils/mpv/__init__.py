"""MPV playback collaborators for VideoPlayer.

Focused components extracted from the former VideoPlayer god-class:
- MPVLogManager: log directory, rotation, log-file preparation, error classification.
- IPCHandler: IPC socket lifecycle, event loop, command sending, keybinding actions.
- MPVLauncher: MPV process launch and input.conf generation.

VideoPlayer composes these and delegates to them, keeping its public API unchanged.
"""

from utils.mpv.ipc_handler import IPCHandler
from utils.mpv.launcher import MPVLauncher
from utils.mpv.log_manager import MPVLogManager

__all__ = ["MPVLogManager", "IPCHandler", "MPVLauncher"]
