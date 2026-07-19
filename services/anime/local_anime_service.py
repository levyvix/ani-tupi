"""Local anime library service for offline viewing.

Scans and manages locally downloaded anime episodes.
Provides episode discovery, file listing, and metadata tracking.
"""

import json
from utils.logging import get_logger
from pathlib import Path

from models.config import get_data_path, settings
from models.models import (
    AnimeDownloadDatabase,
)

logger = get_logger(__name__)


class LocalAnimeService:
    """Manages the local anime library.

    Scans the download directory for downloaded episodes and provides
    interfaces to browse, list, and play them.
    """

    def __init__(self):
        """Initialize local anime service."""
        self.download_dir = settings.anime_download.download_directory
        self.db_path = get_data_path() / "anime_downloads.json"

    def get_downloaded_anime_list(self) -> list[str]:
        """Get list of all downloaded anime titles.

        Returns:
            Sorted list of anime titles that have downloaded episodes
        """
        if not self.download_dir.exists():
            return []

        anime_list = []
        for anime_dir in self.download_dir.iterdir():
            if anime_dir.is_dir() and self._has_video_files(anime_dir):
                anime_list.append(anime_dir.name)

        return sorted(anime_list)

    def get_downloaded_episodes(self, anime_title: str) -> list[tuple[int, Path]]:
        """Get list of downloaded episodes for an anime.

        Args:
            anime_title: Title of the anime

        Returns:
            List of (episode_number, file_path) tuples, sorted by episode number

        Raises:
            FileNotFoundError: If anime directory doesn't exist
        """
        safe_title = Path(anime_title).name
        if not safe_title or safe_title != anime_title:
            raise ValueError("Título de anime inválido")
        anime_dir = self.download_dir / safe_title
        if not anime_dir.exists():
            raise FileNotFoundError(f"Anime directory not found: {anime_title}")

        episodes = []
        video_extensions = (".mkv", ".mp4", ".avi", ".webm")

        for file_path in anime_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                try:
                    # Try to parse episode number from filename
                    ep_num = int(file_path.stem)
                    episodes.append((ep_num, file_path))
                except ValueError:
                    logger.warning(f"Skipping file with invalid name: {file_path.name}")
                    continue

        # Sort by episode number
        return sorted(episodes, key=lambda x: x[0])

    def get_episode_metadata(self, anime_title: str, episode_num: int) -> dict | None:
        """Get metadata for a downloaded episode.

        Args:
            anime_title: Title of the anime
            episode_num: Episode number (1-indexed)

        Returns:
            Dictionary with episode metadata (file_size_mb, downloaded_at, source)
            or None if episode not found in database
        """
        db = self._load_database()
        history = db.anime.get(anime_title)

        if not history:
            return None

        episode = history.episodes.get(episode_num)
        if not episode:
            return None

        return {
            "episode_number": episode.episode_number,
            "file_path": str(episode.file_path),
            "file_size_mb": episode.file_size_mb,
            "source": episode.source,
            "downloaded_at": episode.downloaded_at.isoformat(),
            "status": episode.status,
        }

    def get_anime_info(self, anime_title: str) -> dict:
        """Get information about downloaded anime.

        Args:
            anime_title: Title of the anime

        Returns:
            Dictionary with anime info: total_episodes, total_size_mb, episodes_list
        """
        try:
            episodes = self.get_downloaded_episodes(anime_title)
            total_size_mb = sum(ep_path.stat().st_size / (1024 * 1024) for _, ep_path in episodes)

            return {
                "title": anime_title,
                "total_episodes": len(episodes),
                "total_size_mb": round(total_size_mb, 2),
                "episode_numbers": [ep_num for ep_num, _ in episodes],
            }
        except FileNotFoundError:
            return {
                "title": anime_title,
                "total_episodes": 0,
                "total_size_mb": 0.0,
                "episode_numbers": [],
            }

    def delete_episode(self, anime_title: str, episode_num: int) -> bool:
        """Delete a downloaded episode.

        Args:
            anime_title: Title of the anime
            episode_num: Episode number to delete

        Returns:
            True if deleted successfully, False if not found

        This function:
        - Deletes the video file
        - Updates the download database
        - Cleans up empty anime directories
        """
        safe_title = Path(anime_title).name
        if not safe_title or safe_title != anime_title:
            raise ValueError("Título de anime inválido")
        anime_dir = self.download_dir / safe_title
        if not anime_dir.exists():
            return False

        # Find and delete episode file
        video_extensions = (".mkv", ".mp4", ".avi", ".webm")
        deleted = False

        for file_path in anime_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                try:
                    ep_num = int(file_path.stem)
                    if ep_num == episode_num:
                        file_path.unlink()
                        deleted = True
                        logger.info(f"Deleted episode {episode_num}: {file_path}")
                        break
                except ValueError:
                    continue

        if deleted:
            # Update database
            db = self._load_database()
            history = db.anime.get(anime_title)
            if history and episode_num in history.episodes:
                del history.episodes[episode_num]
                history.total_size_mb = sum(ep.file_size_mb for ep in history.episodes.values())
                db.anime[anime_title] = history
                self._save_database(db)

            # Clean up empty directories
            if not any(anime_dir.iterdir()):
                anime_dir.rmdir()
                logger.info(f"Removed empty directory: {anime_dir}")

        return deleted

    def delete_anime(self, anime_title: str) -> bool:
        """Delete all episodes of an anime.

        Args:
            anime_title: Title of the anime to delete

        Returns:
            True if deleted successfully
        """
        safe_title = Path(anime_title).name
        if not safe_title or safe_title != anime_title:
            raise ValueError("Título de anime inválido")
        anime_dir = self.download_dir / safe_title
        if not anime_dir.exists():
            return False

        # Delete all files in directory
        try:
            for file_path in anime_dir.iterdir():
                if file_path.is_file():
                    file_path.unlink()
            anime_dir.rmdir()
            logger.info(f"Deleted anime directory: {anime_dir}")

            # Update database
            db = self._load_database()
            if anime_title in db.anime:
                del db.anime[anime_title]
                self._save_database(db)

            return True
        except Exception as e:
            logger.error(f"Failed to delete anime {anime_title}: {e}")
            return False

    def clear_corrupted_episodes(self, anime_title: str) -> list[int]:
        """Clear episodes marked as corrupted in database.

        Args:
            anime_title: Title of the anime

        Returns:
            List of cleared episode numbers
        """
        db = self._load_database()
        history = db.anime.get(anime_title)

        if not history:
            return []

        corrupted = [ep_num for ep_num, ep in history.episodes.items() if ep.status == "corrupted"]

        for ep_num in corrupted:
            del history.episodes[ep_num]

        if corrupted:
            history.total_size_mb = sum(ep.file_size_mb for ep in history.episodes.values())
            db.anime[anime_title] = history
            self._save_database(db)
            logger.info(f"Cleared {len(corrupted)} corrupted episodes from {anime_title}")

        return corrupted

    def _has_video_files(self, directory: Path) -> bool:
        """Check if directory contains any video files.

        Args:
            directory: Directory to check

        Returns:
            True if directory contains video files
        """
        video_extensions = (".mkv", ".mp4", ".avi", ".webm")
        try:
            for file_path in directory.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                    return True
        except (OSError, PermissionError):
            pass
        return False

    def _load_database(self) -> AnimeDownloadDatabase:
        """Load download history from disk.

        Returns:
            AnimeDownloadDatabase (empty if not found)
        """
        if not self.db_path.exists():
            return AnimeDownloadDatabase()

        try:
            with open(self.db_path) as f:
                data = json.load(f)
                return AnimeDownloadDatabase.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load download database: {e}")
            return AnimeDownloadDatabase()

    def _save_database(self, db: AnimeDownloadDatabase) -> None:
        """Save download history to disk.

        Args:
            db: Database to save
        """
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, "w") as f:
                json.dump(db.model_dump(mode="json"), f, indent=2, default=str)
            logger.debug(f"Saved download database: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to save download database: {e}")
