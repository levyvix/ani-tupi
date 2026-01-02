"""Data models and configuration.

Pydantic models and configuration:
- models: Anime, episode, and video data models
- config: Centralized configuration (Pydantic Settings)
"""

from models.models import AnimeMetadata, EpisodeData, VideoUrl
from models.config import settings, get_data_path

__all__ = [
    "AnimeMetadata",
    "EpisodeData",
    "VideoUrl",
    "settings",
    "get_data_path",
]
