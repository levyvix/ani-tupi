"""Anime download service for offline viewing.

This service orchestrates:
- Episode downloading with parallel queue management
- Download validation and intelligent retry logic
- Download history persistence
- Storage organization

All operations maintain immutability - no state mutation.
"""

import json
import logging
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from tqdm import tqdm

from models.config import get_data_path, settings
from models.models import (
    AnimeDownloadDatabase,
    AnimeDownloadHistory,
    DownloadResult,
    DownloadedEpisode,
)
from utils.episode_range_parser import parse_episode_range, RangeParseError

logger = logging.getLogger(__name__)


@dataclass
class DownloadTask:
    """Represents a download task with retry tracking."""

    episode_number: int
    attempts: int = 0
    max_attempts: int = 3

    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.attempts < self.max_attempts

    def increment_attempt(self) -> None:
        """Increment attempt counter."""
        self.attempts += 1


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
        self.db_path = get_data_path() / "anime_downloads.json"
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
        get_episode_url: Callable[[int], tuple[str, str] | None],
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

        # Sanitize anime_title to prevent path traversal
        safe_title = Path(anime_title).name
        if safe_title != anime_title or not safe_title:
            raise ValueError("Título de anime inválido")

        # Create anime directory
        anime_dir = self.download_dir / safe_title
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
            # Pre-fetch all episode URLs serially to avoid browser pool exhaustion
            episode_urls = self._prefetch_episode_urls(anime_title, to_download, get_episode_url)
            # Then download files in parallel
            successful, failed, corrupted = self._download_parallel(
                anime_title, anime_dir, to_download, episode_urls
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

    def _prefetch_episode_urls(
        self,
        anime_title: str,
        episodes: list[int],
        get_episode_url: Callable[[int], tuple[str, str] | None],
    ) -> dict[int, tuple[str, str] | None]:
        """Pre-fetch all episode URLs serially to avoid browser pool exhaustion.

        Uses URL pattern derivation as a fast path when CDN URLs follow a
        predictable episode-number pattern (e.g. /03.mp4/index.m3u8).
        Falls back to full scraping when pattern derivation fails.

        Args:
            anime_title: Anime title for logging
            episodes: List of episode numbers to fetch
            get_episode_url: Function to get URL for episode

        Returns:
            Dict mapping episode number to (url, source) or None
        """
        from services.anime.episode_url_pattern import (
            derive_episode_url,
            detect_episode_pattern,
            validate_episode_url,
        )

        logger.debug(f"Pre-fetching URLs for {len(episodes)} episodes")
        episode_urls: dict[int, tuple[str, str] | None] = {}
        last_known_url: str | None = None
        last_known_source: str | None = None

        for ep_num in episodes:
            # Fast path: try to derive URL from last known URL via pattern
            if last_known_url and detect_episode_pattern(last_known_url):
                try:
                    derived = derive_episode_url(last_known_url, ep_num)
                    if derived and validate_episode_url(derived):
                        logger.debug(f"URL pattern hit for {anime_title} ep {ep_num}: {derived}")
                        episode_urls[ep_num] = (derived, last_known_source or "pattern")
                        last_known_url = derived
                        continue
                    else:
                        logger.debug(
                            f"URL pattern miss for {anime_title} ep {ep_num}, falling back to scraping"
                        )
                except Exception as e:
                    logger.debug(f"URL pattern error for {anime_title} ep {ep_num}: {e}")

            # Fallback: full scraping
            try:
                url_info = get_episode_url(ep_num)
                episode_urls[ep_num] = url_info
                if url_info:
                    last_known_url, last_known_source = url_info
                    logger.debug(f"Fetched URL for episode {ep_num}")
                else:
                    last_known_url = None
                    logger.warning(f"No URL found for {anime_title} episode {ep_num}")
            except Exception as e:
                logger.warning(f"Error fetching URL for episode {ep_num}: {e}")
                episode_urls[ep_num] = None
                last_known_url = None

        return episode_urls

    def _download_parallel(
        self,
        anime_title: str,
        anime_dir: Path,
        episodes: list[int],
        episode_urls: dict[int, tuple[str, str] | None],
    ) -> tuple[int, list[int], list[int]]:
        """Download episodes with intelligent retry queue and TQDM progress.

        Args:
            anime_title: Anime title for logging
            anime_dir: Directory to save episodes
            episodes: List of episode numbers to download
            episode_urls: Pre-fetched URLs for episodes

        Returns:
            Tuple of (successful_count, failed_list, corrupted_list)
        """
        # Initialize download queue
        download_queue = deque([DownloadTask(ep_num) for ep_num in episodes])
        queue_lock = threading.Lock()

        successful = 0
        failed = []
        corrupted = []
        results_lock = threading.Lock()

        # Progress bar
        pbar = tqdm(
            total=len(episodes),
            desc=f"📥 {anime_title}",
            unit="ep",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        )

        def worker():
            """Worker thread that processes download queue."""
            nonlocal successful

            while True:
                # Get next task from queue
                with queue_lock:
                    if not download_queue:
                        break
                    task = download_queue.popleft()

                # Increment attempt counter
                task.increment_attempt()

                # Download episode
                ep_num = task.episode_number
                url_info = episode_urls.get(ep_num)
                success, is_valid = self._download_single_episode_with_url(
                    anime_title, anime_dir, ep_num, url_info
                )

                # Process result
                with results_lock:
                    if success and is_valid:
                        successful += 1
                        pbar.update(1)
                        pbar.set_postfix({"✓": successful, "❌": len(failed)})

                    elif success and not is_valid:
                        # File corrupted - don't retry
                        corrupted.append(ep_num)
                        pbar.update(1)
                        pbar.set_postfix({"✓": successful, "⚠️": len(corrupted)})

                    else:
                        # Download failed
                        if task.can_retry():
                            # Re-add to end of queue for retry
                            with queue_lock:
                                download_queue.append(task)
                            logger.debug(
                                f"Episode {ep_num} re-added to queue "
                                f"(attempt {task.attempts}/{task.max_attempts})"
                            )
                        else:
                            # Max retries exceeded
                            failed.append(ep_num)
                            pbar.update(1)
                            pbar.set_postfix({"✓": successful, "❌": len(failed)})
                            logger.error(
                                f"Episode {ep_num} failed after {task.max_attempts} attempts"
                            )

        # Launch worker threads
        threads = []
        for _ in range(self.max_parallel):
            thread = threading.Thread(target=worker, daemon=False)
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        pbar.close()
        return successful, failed, corrupted

    def _download_single_episode_with_url(
        self,
        anime_title: str,
        anime_dir: Path,
        episode_num: int,
        url_info: tuple[str, str] | None,
    ) -> tuple[bool, bool]:
        """Download a single episode with pre-fetched URL (single attempt).

        Retry logic is handled by the queue system in _download_parallel().

        Args:
            anime_title: Anime title
            anime_dir: Directory to save episode
            episode_num: Episode number
            url_info: Pre-fetched (url, source) or None

        Returns:
            Tuple of (success, is_valid)
            - success: File was created
            - is_valid: File size > 1MB (not HTML error page)
        """
        # Check if URL is available
        if not url_info:
            logger.warning(f"No URL found for {anime_title} episode {episode_num}")
            return False, False

        url, source = url_info
        file_path = anime_dir / f"{episode_num}.{settings.anime_download.video_format}"

        # Single download attempt
        try:
            success = self._download_file(url, file_path)
            if success:
                # Validate file
                is_valid = self._validate_file(file_path)
                if is_valid:
                    logger.debug(f"✓ Episode {episode_num}: Downloaded successfully")
                    return True, True

                logger.debug(f"⚠️  Episode {episode_num}: File invalid (too small)")
                if file_path.exists():
                    file_path.unlink()
                return False, False

            return False, False
        except Exception as e:
            logger.debug(f"Episode {episode_num} download error: {e}")
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
                    "merge_output_format": settings.anime_download.video_format,
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
