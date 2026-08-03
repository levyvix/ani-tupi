"""Repository package for anime search, episodes, and playback.

Public surface:
- ``Repository``: aggregator coordinating the specialized repositories
- ``rep``: shared singleton instance used across the codebase
"""

from services.repository.repository import Repository, rep

__all__ = ["Repository", "rep"]
