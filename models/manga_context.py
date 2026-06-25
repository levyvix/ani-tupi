"""Context data classes for manga operations.

Replaces functions with 9-10 parameters with structured context objects.
Enables cleaner function signatures and better type safety.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from models.models import ChapterData


class ChapterContext(BaseModel):
    """Context for chapter processing operations.

    Consolidates parameters for _handle_read_now, _process_chapter, etc.
    """

    manga_id: str = Field(..., description="Manga ID (MangaDex UUID or scraper ID)")
    manga_title: str = Field(..., description="Manga title for display and history")
    chapter_id: str = Field(..., description="Chapter ID")
    chapter_number: str = Field(..., description="Chapter number (e.g., '42', '42.5')")
    source: str = Field(..., description="Source name (mangadex, mugiwaras, etc.)")
    manga_url: Optional[str] = Field(None, description="Base manga URL for scrapers")

    # Navigation context (optional, for chapter navigation)
    all_chapters: Optional[list[ChapterData]] = Field(
        None, description="All chapters for navigation"
    )
    chapter_labels: Optional[list[str]] = Field(None, description="Formatted chapter labels")
    current_index: int = Field(0, ge=0, description="Current chapter index in list")

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class DownloadRequest(BaseModel):
    """Request parameters for chapter download operations.

    Consolidates parameters for _download_single_chapter.
    """

    chapter_id: str = Field(..., description="Chapter ID to download")
    chapter_number: str = Field(..., description="Chapter number")
    manga_id: str = Field(..., description="Manga ID")
    manga_title: str = Field(..., description="Manga title")
    source: str = Field(..., description="Source name")
    manga_url: Optional[str] = Field(None, description="Base manga URL")

    # Download options
    output_directory: Path = Field(..., description="Base output directory")
    pdf_quality: int = Field(85, ge=1, le=100, description="PDF JPEG quality")
    delete_images_after_pdf: bool = Field(False, description="Delete images after PDF creation")

    # Progress tracking (for batch downloads)
    chapter_idx: int = Field(1, ge=1, description="Chapter index for progress (1-based)")
    total_chapters: int = Field(1, ge=1, description="Total chapters being downloaded")

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class ReadingSession(BaseModel):
    """Context for a manga reading session.

    Tracks state across chapter reads within a session.
    """

    manga_id: str
    manga_title: str
    source: str
    manga_url: Optional[str] = None

    # Progress
    current_chapter: Optional[str] = None
    chapters: list[ChapterData] = Field(default_factory=list)
    chapter_index: int = 0

    # History/sync
    last_synced_chapter: Optional[str] = None
    anilist_progress: Optional[int] = None

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


@dataclass
class DownloadResult:
    """Result of a single chapter download."""

    success: bool
    chapter_number: str
    error_message: str = ""
    pdf_path: Optional[Path] = None
    file_size_mb: float = 0.0
