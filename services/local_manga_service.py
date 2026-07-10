"""Service for offline manga reading from local filesystem.

Scans ~/.manga_tupi/ directory to discover downloaded manga and chapters.
Provides functionality for PDF auto-creation and AniList sync (forward-only).
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from loguru import logger

from models.models import LocalChapter
from models.config import settings
from utils.pdf_converter import create_pdf_from_images

if TYPE_CHECKING:
    from services.anilist.client import AniListClient as AniListService


class LocalMangaService:
    """Service for offline manga reading from local filesystem."""

    def __init__(self, manga_output_dir: Path | str):
        """Initialize with manga output directory.

        Args:
            manga_output_dir: Path to ~/.manga_tupi directory
        """
        self.output_dir = Path(manga_output_dir)
        logger.debug(f"LocalMangaService initialized with: {self.output_dir}")

    def scan_local_library(self) -> dict[str, list[str]]:
        """Scan filesystem and build manga -> chapters mapping.

        Returns:
            Dictionary mapping manga title to list of chapter numbers.
            Example: {"Chainsaw Man": ["01", "02", "03"], "Dandadan": ["1", "2"]}

        Error Handling:
            - If output directory doesn't exist, returns empty dict
            - Skips invalid chapter directories (no PDF or images)
        """
        if not self.output_dir.exists():
            logger.warning(f"Manga directory not found: {self.output_dir}")
            return {}

        library = {}

        try:
            # List all manga directories
            for manga_dir in sorted(self.output_dir.iterdir()):
                if not manga_dir.is_dir():
                    continue

                manga_title = manga_dir.name
                chapters = []

                # List chapters for this manga
                for chapter_dir in sorted(
                    manga_dir.iterdir(),
                    key=lambda x: self._chapter_sort_key(x.name),
                ):
                    if not chapter_dir.is_dir():
                        continue

                    chapter_num = chapter_dir.name

                    # Validate chapter has content
                    if self._validate_chapter_directory(chapter_dir):
                        chapters.append(chapter_num)
                    else:
                        logger.debug(f"Skipping invalid chapter: {manga_title}/{chapter_num}")

                # Only add manga if it has valid chapters
                if chapters:
                    library[manga_title] = chapters
                    logger.debug(f"Found manga: {manga_title} with {len(chapters)} chapters")

            return library

        except Exception as e:
            logger.error(f"Error scanning local library: {e}")
            return {}

    def get_manga_list(self) -> list[str]:
        """Get sorted list of manga titles with chapter counts.

        Returns:
            List of formatted strings like:
            ["Chainsaw Man (15 caps)", "Dandadan (8 caps)", ...]
        """
        library = self.scan_local_library()

        formatted_list = [
            f"{title} ({len(chapters)} caps)" for title, chapters in sorted(library.items())
        ]

        return formatted_list

    def get_chapters_for_manga(self, manga_title: str) -> list[LocalChapter]:
        """Get available chapters for a manga.

        Args:
            manga_title: Manga title (directory name)

        Returns:
            List of LocalChapter objects sorted by chapter number.

        Error Handling:
            - Returns empty list if manga not found
            - Skips chapters without content (PDF or images)
        """
        manga_dir = self.output_dir / manga_title

        if not manga_dir.exists():
            logger.warning(f"Manga directory not found: {manga_dir}")
            return []

        chapters = []

        try:
            # Scan all chapter directories
            for chapter_dir in sorted(
                manga_dir.iterdir(),
                key=lambda x: self._chapter_sort_key(x.name),
            ):
                if not chapter_dir.is_dir():
                    continue

                chapter_num = chapter_dir.name

                # Validate chapter
                if not self._validate_chapter_directory(chapter_dir):
                    logger.debug(f"Skipping invalid chapter: {manga_title}/{chapter_num}")
                    continue

                # Build LocalChapter object
                local_chapter = self._build_local_chapter(chapter_dir, chapter_num)
                if local_chapter:
                    chapters.append(local_chapter)

            return chapters

        except Exception as e:
            logger.error(f"Error getting chapters for {manga_title}: {e}")
            return []

    def auto_create_pdf_if_needed(self, manga_title: str, chapter_num: str) -> Path | None:
        """Auto-create PDF from images if PDF doesn't exist.

        Args:
            manga_title: Manga title (directory name)
            chapter_num: Chapter number (directory name)

        Returns:
            Path to PDF (existing or newly created), or None if failed/no content

        Logic:
            1. Check if PDF exists → return path
            2. Check if images exist → create PDF → return path
            3. Return None if no content available

        Error Handling:
            - Catches PDF creation failures
            - Logs warnings for incomplete chapters
        """
        chapter_dir = self.output_dir / manga_title / chapter_num
        pdf_path = chapter_dir / f"{chapter_num}.pdf"

        # PDF already exists
        if pdf_path.exists():
            logger.debug(f"PDF already exists: {pdf_path}")
            return pdf_path

        # Check if images exist
        images = self._get_image_files(chapter_dir)
        if not images:
            logger.warning(f"No images found for {manga_title}/{chapter_num}")
            return None

        # Create PDF from images
        try:
            logger.info(f"Creating PDF from {len(images)} images...")
            create_pdf_from_images(
                chapter_dir,
                pdf_path,
                quality=settings.manga.pdf_quality,
            )

            logger.info(f"PDF created successfully: {pdf_path}")

            # Delete images if configured
            if settings.manga.delete_images_after_pdf:
                logger.info("Deleting source images...")
                for img in images:
                    img.unlink()
                logger.info(f"Deleted {len(images)} images")

            return pdf_path

        except Exception as e:
            logger.error(f"Failed to create PDF: {e}")
            return None

    def sync_to_anilist_if_ahead(
        self,
        manga_title: str,
        local_chapter_num: str,
        anilist_service: Optional["AniListService"] = None,
    ) -> bool:
        """Sync local progress to AniList if local is ahead (forward-only).

        Args:
            manga_title: Manga title from local library
            local_chapter_num: Chapter number from local history (e.g., "05", "42.5")
            anilist_service: AniList service instance (None if offline)

        Returns:
            True if synced, False if not synced (offline, behind, or error)

        Logic:
            1. If anilist_service is None → return False (offline mode)
            2. Try to find AniList ID for this manga
            3. Get current AniList progress for this manga
            4. Compare: local_chapter > anilist_chapter?
            5. If yes → update AniList and return True
            6. If no → return False (don't regress)

        Error Handling:
            - Network errors → return False (silent fail)
            - AniList not found → return False (no match)
            - Authentication required → return False (user not logged in)
            - Invalid chapter numbers → return False
        """
        if anilist_service is None:
            logger.debug("AniList service not available (offline mode)")
            return False

        try:
            # Parse local chapter number to integer
            try:
                local_chapter = int(float(local_chapter_num))
            except (ValueError, TypeError):
                logger.warning(f"Invalid chapter number: {local_chapter_num}")
                return False

            logger.debug(f"Syncing to AniList: {manga_title} - Cap. {local_chapter}")

            # Import here to avoid circular imports
            from services.manga_service import MangaHistory

            # Try to find AniList ID from history
            history = MangaHistory.load()
            entry = history.get(manga_title)
            anilist_id = entry.anilist_id if entry else None

            if not anilist_id:
                # Try fuzzy search using AniList discovery
                logger.debug(f"Searching AniList for: {manga_title}")
                try:
                    from services.anilist.discovery import get_anilist_id_from_title

                    anilist_id = get_anilist_id_from_title(manga_title)
                except Exception as search_error:
                    logger.debug(f"AniList search failed: {search_error}")
                    anilist_id = None

                if not anilist_id:
                    logger.debug(f"No AniList match found for: {manga_title}")
                    return False

            # Get current AniList progress
            try:
                anilist_entry = anilist_service.get_manga_list_entry(anilist_id)
                if not anilist_entry or anilist_entry.progress is None:
                    logger.warning(f"Could not get AniList progress for ID: {anilist_id}")
                    return False

                anilist_chapter = anilist_entry.progress
            except Exception as e:
                logger.warning(f"Failed to get AniList entry: {e}")
                return False

            logger.debug(f"AniList progress: {anilist_chapter}, Local: {local_chapter}")

            # Only update if local is ahead (forward-only)
            if local_chapter > anilist_chapter:
                logger.info(f"Updating AniList: {manga_title} → Cap. {local_chapter}")
                anilist_service.update_manga_progress(anilist_id, local_chapter)
                return True
            else:
                logger.debug(
                    f"Local not ahead (local={local_chapter}, "
                    f"anilist={anilist_chapter}) - not syncing"
                )
                return False

        except Exception as e:
            logger.error(f"AniList sync failed: {e}")
            return False

    # =========== Private Helper Methods ==========

    def _validate_chapter_directory(self, chapter_path: Path) -> bool:
        """Validate chapter directory has PDF or images.

        Args:
            chapter_path: Path to chapter directory

        Returns:
            True if chapter has PDF or images, False otherwise
        """
        # Check for PDF
        pdf_name = f"{chapter_path.name}.pdf"
        has_pdf = (chapter_path / pdf_name).exists()

        # Check for images
        has_images = bool(self._get_image_files(chapter_path))

        return has_pdf or has_images

    def _get_image_files(self, directory: Path) -> list[Path]:
        """Get all image files in directory.

        Args:
            directory: Directory to scan

        Returns:
            List of image file paths (PNG, JPG, JPEG, WEBP)
        """
        if not directory.exists():
            return []

        image_extensions = ("*.png", "*.jpg", "*.jpeg", "*.webp")
        images = []

        for ext in image_extensions:
            images.extend(sorted(directory.glob(ext)))

        return images

    def _build_local_chapter(self, chapter_dir: Path, chapter_num: str) -> LocalChapter | None:
        """Build LocalChapter object from directory.

        Args:
            chapter_dir: Path to chapter directory
            chapter_num: Chapter number (directory name)

        Returns:
            LocalChapter object or None if invalid
        """
        try:
            # Check for PDF
            pdf_name = f"{chapter_num}.pdf"
            pdf_path = chapter_dir / pdf_name
            has_pdf = pdf_path.exists()

            # Get images
            images = self._get_image_files(chapter_dir)
            has_images = bool(images)
            image_count = len(images)

            # Calculate directory size in MB
            total_size = 0
            for file in chapter_dir.rglob("*"):
                if file.is_file():
                    total_size += file.stat().st_size
            file_size_mb = total_size / (1024 * 1024)

            return LocalChapter(
                chapter_number=chapter_num,
                pdf_path=pdf_path if has_pdf else None,
                has_pdf=has_pdf,
                has_images=has_images,
                image_count=image_count,
                file_size_mb=round(file_size_mb, 1),
            )

        except Exception as e:
            logger.error(f"Error building LocalChapter for {chapter_dir}: {e}")
            return None

    @staticmethod
    def _chapter_sort_key(chapter_name: str) -> tuple:
        """Generate sort key for chapter directory names.

        Handles numeric and decimal chapter numbers (e.g., "01", "42", "42.5").

        Args:
            chapter_name: Chapter directory name

        Returns:
            Tuple for sorting (handles both integers and decimals)
        """
        try:
            # Try parsing as float to handle decimals like "42.5"
            return (0, float(chapter_name))
        except ValueError:
            # Fallback to string sorting for non-numeric names
            return (1, chapter_name)
