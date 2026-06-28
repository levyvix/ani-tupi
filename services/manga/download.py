"""Manga chapter download service.

Handles single chapter downloads, batch downloads, and download range prompting.
Extracted from manga_tupi.py to improve maintainability and enable unit testing.
"""

from pathlib import Path
import httpx

from services.manga_service import DownloadedChaptersTracker
from ui.components import menu_navigate
from utils.pdf_converter import create_pdf_from_images
from utils.logging import get_logger

logger = get_logger(__name__)


def download_chapter(
    chapter,
    service,
    selected_manga,
    manga_url: str | None,
    selected_source: str,
    config,
    tracker: DownloadedChaptersTracker,
    chapter_idx: int,
    total_chapters: int,
) -> tuple[bool, str]:
    """Download a single chapter and return (success, error_message).

    This function orchestrates the complete download process:
    1. Fetches chapter page URLs
    2. Downloads images with error handling
    3. Creates PDF from images
    4. Cleans up temporary files if configured
    5. Tracks download metadata

    Args:
        chapter: ChapterData object to download
        service: UnifiedMangaService instance
        selected_manga: Selected manga metadata
        manga_url: Base manga URL
        selected_source: Source name (mangadex, mugiwaras, etc.)
        config: Manga settings (output_directory, pdf_quality, etc.)
        tracker: DownloadedChaptersTracker instance for tracking
        chapter_idx: Chapter index for progress display (1-based)
        total_chapters: Total number of chapters being downloaded

    Returns:
        tuple: (success: bool, error_message: str)
               success=True if download completed, False otherwise
               error_message contains human-readable error if failed
    """
    try:
        logger.info(f"\n[{chapter_idx}/{total_chapters}] Capítulo {chapter.number}...")

        # Construct chapter URL based on source
        chapter_url = _construct_chapter_url(selected_source, manga_url, chapter, selected_manga)

        if config.debug_download_failures:
            logger.info(f"  🔍 Buscando páginas do capítulo {chapter.number}...")
            logger.info(f"     URL: {chapter_url}")
            logger.info(f"     ID: {chapter.id}")

        # Get chapter pages
        try:
            pages = service.get_chapter_pages(
                chapter.id, chapter_url=chapter_url, source=selected_source
            )
        except Exception as e:
            error_msg = f"Falha ao buscar páginas do capítulo {chapter.number}: {str(e)}"
            if config.debug_download_failures:
                logger.info(f"  ❌ {error_msg}")
            return False, error_msg

        if not pages:
            error_msg = f"Nenhuma página disponível para capítulo {chapter.number} (fonte: {selected_source})"
            if config.debug_download_failures:
                logger.info(f"  ❌ {error_msg}")
            return False, error_msg

        if config.debug_download_failures:
            logger.info(f"  ✓ Encontradas {len(pages)} páginas")

        # Create output directory
        output_path = config.output_directory / selected_manga.title / chapter.number
        output_path.mkdir(parents=True, exist_ok=True)

        # Download images
        _download_images(pages, output_path, config)

        # Check if download was successful (at least 50% of pages)
        image_files = _get_image_files(output_path)

        if len(image_files) == 0:
            return (
                False,
                f"Nenhuma imagem válida baixada para capítulo {chapter.number}",
            )

        if len(image_files) < len(pages) * 0.5:
            return (
                False,
                f"Apenas {len(image_files)}/{len(pages)} imagens válidas baixadas para capítulo {chapter.number}",
            )

        # Create PDF
        pdf_path = output_path / f"{chapter.number}.pdf"
        logger.info(f"📄 Criando PDF com {len(image_files)} imagens...")
        try:
            create_pdf_from_images(
                output_path,
                pdf_path,
                quality=config.pdf_quality,
            )
        except Exception as e:
            return False, f"Falha ao criar PDF para capítulo {chapter.number}: {str(e)}"

        # Delete images if configured
        if config.delete_images_after_pdf:
            for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                for img in output_path.glob(ext):
                    img.unlink()

        # Track download
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        tracker.mark_downloaded(
            selected_manga.id,
            selected_manga.title,
            chapter.number,
            str(pdf_path),
            file_size_mb,
            source=selected_source,
        )

        logger.info(f"✓ Capítulo {chapter.number} baixado ({file_size_mb:.1f} MB)")
        return True, ""

    except Exception as e:
        return False, f"Erro ao baixar capítulo {chapter.number}: {e}"


def download_chapters_batch(
    chapters: list,
    service,
    selected_manga,
    manga_url: str | None,
    selected_source: str,
    config,
    tracker: DownloadedChaptersTracker,
) -> tuple[int, list[str]]:
    """Download multiple chapters with progress tracking.

    Args:
        chapters: List of ChapterData objects to download
        service: UnifiedMangaService instance
        selected_manga: Selected manga metadata
        manga_url: Base manga URL
        selected_source: Source name
        config: Manga settings
        tracker: DownloadedChaptersTracker instance

    Returns:
        Tuple of (successful_count, failed_chapter_numbers)
    """
    successful = 0
    failed_chapters = []

    for i, chapter in enumerate(chapters, 1):
        success, error_msg = download_chapter(
            chapter,
            service,
            selected_manga,
            manga_url,
            selected_source,
            config,
            tracker,
            i,
            len(chapters),
        )

        if success:
            successful += 1
        else:
            failed_chapters.append(chapter.number)
            logger.info(f"❌ {error_msg}")

    return successful, failed_chapters


def prompt_download_range(
    last_chapter: str | None,
    available_chapters: list,
    default_count: int = 5,
) -> list | None:
    """Prompt user for chapter range to download.

    Asks user to select:
    1. Starting chapter (default: after last read)
    2. Number of chapters (default: 5)

    Args:
        last_chapter: Last read chapter number
        available_chapters: List of available ChapterData objects
        default_count: Default number of chapters to download

    Returns:
        List of ChapterData objects to download, or None if cancelled
    """
    if not available_chapters:
        return None

    # Find starting chapter index
    start_idx = 0
    if last_chapter:
        for i, ch in enumerate(available_chapters):
            if ch.number == last_chapter:
                start_idx = max(0, i - 1)  # Start one before last read
                break

    # Build menu options for number of chapters
    chapter_count_options = [
        "1 capítulo",
        "3 capítulos",
        "5 capítulos",
        "10 capítulos",
        "Todos (a partir de agora)",
    ]

    count_map = {
        "1 capítulo": 1,
        "3 capítulos": 3,
        "5 capítulos": 5,
        "10 capítulos": 10,
        "Todos (a partir de agora)": len(available_chapters) - start_idx,
    }

    choice = menu_navigate(chapter_count_options, "Quantos capítulos baixar?")
    if not choice:
        return None

    count = count_map.get(choice, default_count)
    return available_chapters[start_idx : start_idx + count]


# ========== Private Helpers ==========


def _construct_chapter_url(
    source: str, manga_url: str | None, chapter, manga_metadata
) -> str | None:
    """Construct chapter URL based on source.

    Args:
        source: Source name
        manga_url: Base manga URL
        chapter: ChapterData object
        manga_metadata: Selected manga metadata

    Returns:
        Chapter URL or None if source doesn't need URL
    """
    # First, try using the URL already stored in chapter data (from plugin)
    if chapter.url:
        return chapter.url

    # Fall back to source-specific construction
    if source == "mugiwaras":
        # Mugiwaras uses format: /manga/{manga-slug}/capitulo-{number}-{manga-slug}/
        manga_slug = (
            manga_metadata.title.lower().replace(" ", "-").replace(":", "").replace("?", "")
        )
        return f"{manga_url}capitulo-{chapter.number}-{manga_slug}/"
    elif source == "mangadex":
        return f"https://mangadex.org/chapter/{chapter.id}"
    elif source == "mangalivre":
        # MangaLivre format: /capitulo/{manga-slug}-capitulo-{number}-{subtitle}/
        # The URL should already be in chapter.url from the plugin - use it if available
        # Otherwise, try to construct it (though this may not work for all chapters)
        if chapter.url:
            return chapter.url
        # Fallback construction if URL is missing
        manga_slug = (
            manga_metadata.title.lower().replace(" ", "-").replace(":", "").replace("?", "")
        )
        return f"{manga_url}capitulo/{manga_slug}-capitulo-{chapter.number}/"

    return None


def _download_images(pages: list, output_path: Path, config) -> int:
    """Download chapter images and return count of valid downloads.

    Args:
        pages: List of image URLs to download
        output_path: Directory to save images
        config: Manga settings (for debug flags)

    Returns:
        Number of successfully downloaded images
    """
    valid_downloads = 0
    failed_pages = []

    for i, url in enumerate(pages):
        if config.debug_download_failures and (i % 10 == 0 or i < 3):
            logger.info(f"     Página {i + 1}/{len(pages)}: {url[:60]}...")

        ext = Path(url.split("?")[0]).suffix or ".png"
        img_path = output_path / f"{i:03d}{ext}"

        if not img_path.exists():
            response = None
            try:
                response = httpx.get(url, timeout=15, follow_redirects=True)
                response.raise_for_status()

                # Validate content is actually an image
                content_type = response.headers.get("content-type", "").lower()
                if not content_type.startswith("image/"):
                    failed_pages.append(f"Page {i}: Invalid content-type '{content_type}'")
                    continue

                img_data = response.content
                if len(img_data) < 1024:  # Skip very small files (likely errors)
                    failed_pages.append(f"Page {i}: Too small ({len(img_data)} bytes)")
                    continue

                img_path.write_bytes(img_data)
                valid_downloads += 1
            except httpx.TimeoutException:
                failed_pages.append(f"Page {i}: Timeout")
                continue
            except httpx.ConnectError:
                failed_pages.append(f"Page {i}: Connection error")
                continue
            except httpx.HTTPStatusError:
                status_code = getattr(response, "status_code", "unknown") if response else "unknown"
                failed_pages.append(f"Page {i}: HTTP {status_code}")
                continue
            except Exception as e:
                failed_pages.append(f"Page {i}: {str(e)}")
                continue
        else:
            valid_downloads += 1

    # Log failed pages if any
    if failed_pages:
        logger.info(f"  ⚠️  {len(failed_pages)} páginas falharam:")
        for failure in failed_pages[:5]:  # Show first 5 failures
            logger.info(f"    {failure}")
        if len(failed_pages) > 5:
            logger.info(f"    ... e mais {len(failed_pages) - 5} falhas")

    logger.info(f"✓ {valid_downloads} imagens válidas baixadas")
    return valid_downloads


def _get_image_files(output_path: Path) -> list[Path]:
    """Get all image files in output directory.

    Args:
        output_path: Directory to search

    Returns:
        List of image file paths
    """
    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.webp"]
    image_files = []
    for ext in image_extensions:
        image_files.extend(output_path.glob(ext))
    return image_files
