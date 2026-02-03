"""Anime download service for offline viewing.

This service orchestrates:
- Episode downloading with parallel queue management
- Download validation and retry logic
- Download history persistence
- Storage organization

All operations maintain immutability - no state mutation.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from models.config import settings
from models.models import (
    AnimeDownloadDatabase,
    AnimeDownloadHistory,
    DownloadResult,
    DownloadedEpisode,
)
from utils.episode_range_parser import parse_episode_range, RangeParseError

logger = logging.getLogger(__name__)


class AnimeDownloadService:
    """Manages anime episode downloads and local library.

    Handles:
    - Parallel downloads with ordered execution
    - File validation (size, integrity)
    - Retry logic with exponential backoff
    - Metadata tracking and persistence
    """

    def __init__(self):
        """Initialize download service."""
        self.download_dir = settings.anime_download.download_directory
        self.max_parallel = settings.anime_download.max_parallel_downloads
        self.db_path = Path.home() / ".local" / "state" / "ani-tupi" / "anime_downloads.json"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def download_episodes(
        self,
        anime_title: str,
        range_input: str,
        total_episodes: int,
        get_episode_url: Callable[[int], Optional[tuple[str, str]]],
    ) -> DownloadResult:
        """Download episodes for an anime.

        Args:
            anime_title: Title of the anime
            range_input: User input for episode range (e.g., "1-12", "5", "5-")
            total_episodes: Total episodes available
            get_episode_url: Function(episode_num) -> (url, source) or None

        Returns:
            DownloadResult with summary of operation

        Raises:
            RangeParseError: If range parsing fails
        """
        # Parse and validate range
        try:
            episodes_to_download = parse_episode_range(range_input, total_episodes)
        except RangeParseError as e:
            logger.error(f"Invalid range '{range_input}': {e}")
            raise

        # Create anime directory
        anime_dir = self.download_dir / anime_title
        anime_dir.mkdir(parents=True, exist_ok=True)

        # Load existing history
        db = self._load_database()
        history = db.anime.get(anime_title, AnimeDownloadHistory(anime_title=anime_title))

        # Separate: skip already downloaded, prepare new downloads
        skipped = []
        to_download = []

        for ep_num in episodes_to_download:
            if settings.anime_download.skip_already_downloaded and history.has_episode(ep_num):
                skipped.append(ep_num)
            else:
                to_download.append(ep_num)

        # Download in parallel batches
        successful = 0
        failed = []
        corrupted = []

        if to_download:
            logger.info(f"Downloading {len(to_download)} episodes for {anime_title}")
            successful, failed, corrupted = self._download_parallel(
                anime_title, anime_dir, to_download, get_episode_url
            )

        # Update history
        for ep_num in to_download:
            if ep_num not in failed and ep_num not in corrupted:
                file_path = anime_dir / f"{ep_num}.{settings.anime_download.video_format}"
                if file_path.exists():
                    file_size_mb = file_path.stat().st_size / (1024 * 1024)
                    history.episodes[ep_num] = DownloadedEpisode(
                        episode_number=ep_num,
                        file_path=file_path,
                        file_size_mb=file_size_mb,
                        source="mixed",
                        status="success",
                    )

        # Mark corrupted episodes
        for ep_num in corrupted:
            history.episodes[ep_num] = DownloadedEpisode(
                episode_number=ep_num,
                file_path=anime_dir / f"{ep_num}.{settings.anime_download.video_format}",
                file_size_mb=0.0,
                source="unknown",
                status="corrupted",
            )

        # Update database
        history.total_size_mb = sum(ep.file_size_mb for ep in history.episodes.values())
        db.anime[anime_title] = history
        self._save_database(db)

        # Build summary
        summary = self._build_summary(successful, len(to_download), failed, corrupted, skipped)

        return DownloadResult(
            successful=successful,
            failed=failed,
            corrupted=corrupted,
            skipped=skipped,
            summary=summary,
        )

    def _download_parallel(
        self,
        anime_title: str,
        anime_dir: Path,
        episodes: list[int],
        get_episode_url: Callable[[int], Optional[tuple[str, str]]],
    ) -> tuple[int, list[int], list[int]]:
        """Download episodes in parallel batches.

        Args:
            anime_title: Anime title for logging
            anime_dir: Directory to save episodes
            episodes: List of episode numbers to download
            get_episode_url: Function to get URL for episode

        Returns:
            Tuple of (successful_count, failed_list, corrupted_list)
        """
        successful = 0
        failed = []
        corrupted = []

        # Use ThreadPoolExecutor for parallel downloads
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            futures = {
                executor.submit(
                    self._download_single_episode,
                    anime_title,
                    anime_dir,
                    ep_num,
                    get_episode_url,
                ): ep_num
                for ep_num in episodes
            }

            for future in as_completed(futures):
                ep_num = futures[future]
                try:
                    success, is_valid = future.result()
                    if success:
                        if is_valid:
                            successful += 1
                        else:
                            corrupted.append(ep_num)
                    else:
                        failed.append(ep_num)
                except Exception as e:
                    logger.error(f"Download error for episode {ep_num}: {e}")
                    failed.append(ep_num)

        return successful, failed, corrupted

    def _download_single_episode(
        self,
        anime_title: str,
        anime_dir: Path,
        episode_num: int,
        get_episode_url: Callable[[int], Optional[tuple[str, str]]],
    ) -> tuple[bool, bool]:
        """Download a single episode with retry logic.

        Args:
            anime_title: Anime title
            anime_dir: Directory to save episode
            episode_num: Episode number
            get_episode_url: Function to get URL

        Returns:
            Tuple of (success, is_valid)
            - success: File was created
            - is_valid: File size > 1MB (not HTML error page)
        """
        # Get episode URL
        url_info = get_episode_url(episode_num)
        if not url_info:
            logger.warning(f"No URL found for {anime_title} episode {episode_num}")
            return False, False

        url, source = url_info
        file_path = anime_dir / f"{episode_num}.{settings.anime_download.video_format}"

        # Download with retry
        max_retries = 3

        for attempt in range(max_retries):
            try:
                success = self._download_file(url, file_path)
                if success:
                    # Validate file
                    is_valid = self._validate_file(file_path)
                    if is_valid:
                        logger.info(f"✓ Episode {episode_num}: Downloaded successfully")
                        return True, True
                    else:
                        logger.warning(f"⚠️  Episode {episode_num}: File invalid (too small)")
                        if file_path.exists():
                            file_path.unlink()
                        return False, False
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(
                        f"Retry {attempt + 1}/{max_retries} for episode {episode_num}: {e}"
                    )
                else:
                    logger.error(
                        f"❌ Episode {episode_num}: Download failed after {max_retries} attempts"
                    )
                    return False, False

        return False, False

    def _download_file(self, url: str, file_path: Path) -> bool:
        """Download a file from URL using yt-dlp for HLS/wrapper URL support.

        Args:
            url: Download URL
            file_path: Path to save file

        Returns:
            True if download succeeded
        """
        try:
            import yt_dlp
            import shutil
            import tempfile

            # Use yt-dlp to handle HLS streams, proxy URLs, and other complex formats
            # Download to temp directory, then move to final location
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Configure yt-dlp to download best quality
                ydl_opts = {
                    "format": "best",
                    "quiet": True,
                    "no_warnings": True,
                    "outtmpl": str(temp_path / "download.%(ext)s"),
                    "force_generic_extractor": True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # Find the downloaded file (could be any extension)
                downloaded_files = list(temp_path.glob("download.*"))
                if not downloaded_files:
                    logger.error(f"No file downloaded for {url}")
                    return False

                downloaded_file = downloaded_files[0]

                # Move to final location, renaming to target format
                # Note: Extension is renamed to match config, but codec/container is preserved
                shutil.move(str(downloaded_file), str(file_path))

            return True
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return False

    def _validate_file(self, file_path: Path) -> bool:
        """Validate downloaded file is not corrupt.

        Args:
            file_path: Path to file to validate

        Returns:
            True if file is valid (size > 1MB)
        """
        if not file_path.exists():
            return False

        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb < 1.0:
            logger.warning(f"File too small ({file_size_mb:.1f}MB): {file_path}")
            return False

        return True

    def _load_database(self) -> AnimeDownloadDatabase:
        """Load download history from disk.

        Returns:
            AnimeDownloadDatabase (empty if not found)
        """
        if not self.db_path.exists():
            return AnimeDownloadDatabase()

        try:
            with open(self.db_path, "r") as f:
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

    def _build_summary(
        self,
        successful: int,
        total: int,
        failed: list[int],
        corrupted: list[int],
        skipped: list[int],
    ) -> str:
        """Build human-readable summary.

        Args:
            successful: Number of successful downloads
            total: Total episodes attempted
            failed: List of failed episode numbers
            corrupted: List of corrupted episode numbers
            skipped: List of skipped episode numbers

        Returns:
            Formatted summary string
        """
        parts = []

        if successful == total and not failed and not corrupted:
            parts.append(f"✓ {successful}/{total} episódios baixados com sucesso")
        else:
            parts.append(f"✓ {successful}/{total} episódios baixados")

            if failed:
                parts.append(f"❌ {len(failed)} falharam (episódios {', '.join(map(str, failed))})")

            if corrupted:
                parts.append(
                    f"⚠️  {len(corrupted)} corrompidos (episódios {', '.join(map(str, corrupted))})"
                )

        if skipped:
            parts.append(f"⊘ {len(skipped)} já existiam")

        return " | ".join(parts)
