"""Manga domain data models (MangaDex/scraper metadata, chapters, history)."""

from datetime import datetime
from pathlib import Path
from enum import Enum

from pydantic import BaseModel, Field

from models.anilist import AniListManga


class MangaStatus(str, Enum):
    """Manga publication status."""

    ONGOING = "ongoing"
    COMPLETED = "completed"
    HIATUS = "hiatus"
    CANCELLED = "cancelled"


class MangaMetadata(BaseModel):
    """Manga metadata from MangaDex.

    Attributes:
        id: MangaDex UUID
        title: Manga title
        description: Optional description
        status: Publication status (ongoing, completed, etc.)
        year: Publication year
        tags: List of tags/genres
        anilist_id: Optional AniList manga ID for integration
        anilist_data: Optional AniList manga data
    """

    id: str = Field(..., min_length=1, description="MangaDex UUID")
    title: str = Field(..., min_length=1, description="Manga title")
    description: str | None = Field(None, description="Manga description")
    status: MangaStatus = Field(..., description="Publication status")
    year: int | None = Field(None, ge=1900, le=2100, description="Publication year")
    tags: list[str] = Field(default_factory=list, description="Tags/genres")
    anilist_id: int | None = Field(None, description="AniList manga ID")
    # String annotation defers Pydantic resolution; model_rebuild() is called in
    # models.models after all submodules are imported. Import MangaMetadata via
    # models.models (not models.manga directly) or call model_rebuild() yourself.
    anilist_data: "AniListManga | None" = Field(None, description="AniList manga data")
    sources: dict[str, str] = Field(
        default_factory=dict,
        description="Map of source name -> manga id in that source (multi-source results)",
    )


class ChapterData(BaseModel):
    """Chapter data from MangaDex or other manga sources.

    Attributes:
        id: Chapter UUID or identifier
        number: Chapter number (supports decimals like "42.5")
        title: Optional chapter title
        url: Chapter URL extracted by the plugin during scraping.
            Must be populated by the plugin's get_chapters() method.
            For web scrapers: the href attribute from chapter links.
            For API sources: constructed from response data (e.g., MangaDex).
        language: Language code (pt-br, en, ja, etc.)
        published_at: Optional publication date
        scanlation_group: Optional scanlation group name
    """

    id: str = Field(..., min_length=1, description="Chapter UUID")
    number: str = Field(..., min_length=1, description="Chapter number (e.g., '42', '42.5')")
    title: str | None = Field(None, description="Chapter title")
    url: str | None = Field(
        None, description="Chapter URL extracted by plugin (required for reading)"
    )
    language: str = Field(..., min_length=1, description="Language code (pt-br, en, ja)")
    published_at: datetime | None = Field(None, description="Publication date")
    scanlation_group: str | None = Field(None, description="Scanlation group name")

    def display_name(self) -> str:
        """Format chapter for display.

        Returns:
            Formatted string like "Cap. 42 - Título" or "Cap. 42" if no title.
        """
        if self.title:
            return f"Cap. {self.number} - {self.title}"
        return f"Cap. {self.number}"


class LocalChapter(BaseModel):
    """Local chapter metadata for offline reading.

    Attributes:
        chapter_number: Chapter number (e.g., "01", "42", "42.5")
        pdf_path: Path to PDF file (None if doesn't exist)
        has_pdf: Whether PDF file exists
        has_images: Whether chapter has any image files
        image_count: Number of image files in chapter directory
        file_size_mb: Total size of chapter directory in MB
    """

    chapter_number: str = Field(..., min_length=1, description="Chapter number")
    pdf_path: Path | None = Field(None, description="Path to PDF file")
    has_pdf: bool = Field(..., description="Whether PDF file exists")
    has_images: bool = Field(..., description="Whether chapter has image files")
    image_count: int = Field(default=0, ge=0, description="Number of image files")
    file_size_mb: float = Field(default=0.0, ge=0.0, description="Total size in MB")

    def display_name(self) -> str:
        """Format chapter for display.

        Returns:
            Formatted string like "Cap. 01 (PDF, 20.7 MB)" or "Cap. 01 (Images: 42)"
        """
        if self.has_pdf and self.file_size_mb > 0:
            return f"Cap. {self.chapter_number} (PDF, {self.file_size_mb:.1f} MB)"
        elif self.has_images and self.image_count > 0:
            return f"Cap. {self.chapter_number} (Imagens: {self.image_count})"
        else:
            return f"Cap. {self.chapter_number}"


class MangaHistoryEntry(BaseModel):
    """Single entry in reading history.

    Attributes:
        last_chapter: Chapter number (e.g., "42.5")
        last_chapter_id: Optional MangaDex chapter ID
        timestamp: When the chapter was read
        manga_id: Optional MangaDex manga ID
        anilist_id: Optional AniList manga ID for integration
        manga_status: Optional AniList status for this manga
        downloaded_chapters: List of chapter numbers downloaded for later reading
    """

    last_chapter: str = Field(..., min_length=1, description="Chapter number")
    last_chapter_id: str | None = Field(None, description="MangaDex chapter ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="Read timestamp")
    manga_id: str | None = Field(None, description="MangaDex manga ID")
    anilist_id: int | None = Field(None, description="AniList manga ID")
    manga_status: str | None = Field(None, description="AniList status for this manga")
    downloaded_chapters: list[str] = Field(
        default_factory=list, description="Chapter numbers downloaded for later"
    )
