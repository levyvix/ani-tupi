"""Unified manga service with multi-source support and utilities.

Provides:
- UnifiedMangaService: Multi-source manga service with plugin support
- MangaHistory: Reading progress persistence
- DownloadedChaptersTracker: Download tracking and metadata
- MangaDexClient: Backward compatibility alias
- Custom exceptions: MangaError, MangaNotFoundError, etc.

This module consolidates both the legacy MangaDex-specific service
and the new multi-source unified service into a single source of truth.
"""

import itertools
import json
import threading
from datetime import datetime
from typing import Any
from collections import OrderedDict


from manga_scrapers.loader import load_manga_plugins
from models.config import MangaSettings, get_data_path
from services.anime.title_normalization import normalize_title_for_dedup
from models.models import ChapterData, MangaHistoryEntry, MangaMetadata, MangaStatus
from utils.logging import get_logger

logger = get_logger(__name__)

_STATUS_MAP = {
    "ongoing": MangaStatus.ONGOING,
    "completed": MangaStatus.COMPLETED,
    "hiatus": MangaStatus.HIATUS,
    "cancelled": MangaStatus.CANCELLED,
}

_MANGA_URL_TEMPLATES = {
    "mangadex": "https://mangadex.org/title/{}",
    "mugiwaras": "https://mugiwarasoficial.com/manga/{}/",
    "mangalivre": "https://mangalivre.blog/manga/{}/",
}


class MangaError(Exception):
    """Base manga error with user-friendly message."""

    user_message = "Ocorreu um erro com o mangá"

    def __init__(self, message: str = "", user_message: str | None = None):
        super().__init__(message)
        if user_message:
            self.user_message = user_message


class MangaNotFoundError(MangaError):
    """Manga not found in search results."""

    user_message = "Mangá não encontrado. Tente outra pesquisa."


class MangaDexError(MangaError):
    """MangaDex API error (network, rate limit, etc)."""

    user_message = "Erro ao conectar com MangaDex. Verifique sua conexão."


class MangaHistory:
    """Reading progress tracker with JSON persistence."""

    _history_file = get_data_path() / "manga_history.json"
    _lock = threading.Lock()

    @classmethod
    def _ensure_dir(cls) -> None:
        """Ensure history directory exists."""
        cls._history_file.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls) -> dict[str, MangaHistoryEntry]:
        """Load history from file."""
        cls._ensure_dir()

        if not cls._history_file.exists():
            return {}

        try:
            with cls._history_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return {title: MangaHistoryEntry(**entry) for title, entry in data.items()}
        except (json.JSONDecodeError, ValueError):
            return {}

    @classmethod
    def save(cls, history: dict[str, MangaHistoryEntry]) -> None:
        """Save history to file."""
        cls._ensure_dir()

        data = {title: entry.model_dump() for title, entry in history.items()}

        try:
            with cls._history_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as e:
            raise MangaError(f"Failed to save history: {e}")

    @classmethod
    def get_last_chapter(cls, manga_title: str) -> str | None:
        """Get last read chapter for manga."""
        history = cls.load()
        entry = history.get(manga_title)
        return entry.last_chapter if entry else None

    @classmethod
    def update(
        cls,
        manga_title: str,
        chapter_number: str,
        chapter_id: str | None = None,
        manga_id: str | None = None,
        anilist_id: int | None = None,
    ) -> None:
        """Update reading progress."""
        with cls._lock:
            history = cls.load()
            entry = history.get(manga_title)

            # Preserve existing AniList data if not provided
            if entry and not anilist_id:
                anilist_id = entry.anilist_id

            history[manga_title] = MangaHistoryEntry(
                last_chapter=chapter_number,
                last_chapter_id=chapter_id,
                manga_id=manga_id,
                anilist_id=anilist_id,
            )
            cls.save(history)


class DownloadedChaptersTracker:
    """Tracks and persists downloaded chapters across the application.

    Maintains a JSON file mapping manga IDs to their downloaded chapters
    with metadata like file size and download timestamp.
    """

    _downloads_file = get_data_path() / "manga_downloads.json"
    _lock = threading.Lock()

    @classmethod
    def _ensure_dir(cls) -> None:
        """Ensure downloads directory exists."""
        cls._downloads_file.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _load_raw(cls) -> dict[str, Any]:
        """Load raw download state from JSON file."""
        cls._ensure_dir()

        if not cls._downloads_file.exists():
            return {}

        try:
            with cls._downloads_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    @classmethod
    def _save_raw(cls, data: dict[str, Any]) -> None:
        """Save raw download state to JSON file."""
        cls._ensure_dir()

        try:
            with cls._downloads_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as e:
            raise MangaError(f"Failed to save downloads: {e}")

    @classmethod
    def is_downloaded(cls, manga_id: str, chapter_number: str) -> bool:
        """Check if a chapter is already downloaded."""
        data = cls._load_raw()
        manga_state = data.get(manga_id, {})
        downloaded = manga_state.get("downloaded_chapters", {})
        return chapter_number in downloaded

    @classmethod
    def mark_downloaded(
        cls,
        manga_id: str,
        manga_title: str,
        chapter_number: str,
        file_path: str,
        file_size_mb: float,
        source: str = "mangadex",
    ) -> None:
        """Mark a chapter as downloaded and persist metadata."""
        with cls._lock:
            data = cls._load_raw()

            if manga_id not in data:
                data[manga_id] = {
                    "manga_title": manga_title,
                    "source": source,
                    "downloaded_chapters": {},
                    "last_download_at": None,
                }

            data[manga_id]["downloaded_chapters"][chapter_number] = {
                "file_path": file_path,
                "file_size_mb": file_size_mb,
                "downloaded_at": str(datetime.now()),
            }
            data[manga_id]["last_download_at"] = str(datetime.now())

            cls._save_raw(data)

    @classmethod
    def get_downloaded_chapters(cls, manga_id: str) -> dict[str, Any]:
        """Get all downloaded chapters for a manga."""
        data = cls._load_raw()
        manga_state = data.get(manga_id, {})
        return manga_state.get("downloaded_chapters", {})

    @classmethod
    def get_download_path(cls, manga_id: str, chapter_number: str) -> str | None:
        """Get file path for a downloaded chapter."""
        data = cls._load_raw()
        manga_state = data.get(manga_id, {})
        downloaded = manga_state.get("downloaded_chapters", {})
        chapter_data = downloaded.get(chapter_number)
        return chapter_data.get("file_path") if chapter_data else None

    @classmethod
    def cleanup_download(cls, manga_id: str, chapter_number: str) -> None:
        """Remove a chapter from the download tracker."""
        data = cls._load_raw()

        if manga_id in data:
            downloaded = data[manga_id].get("downloaded_chapters", {})
            if chapter_number in downloaded:
                del downloaded[chapter_number]
                cls._save_raw(data)


class UnifiedMangaService:
    """Unified manga service supporting multiple sources.

    Orchestrates multiple manga scraper plugins and provides a clean interface
    for the manga CLI.
    """

    def __init__(self, config: MangaSettings):
        """Initialize service with config and load plugins."""
        self.config = config

        # Load all available manga scraper plugins
        self.plugins = load_manga_plugins()

        if not self.plugins:
            raise RuntimeError("Nenhum plugin de mangá disponível")

        # Default source (prioritize MugiwarasOficial for Brazilian Portuguese, MangaDex as fallback)
        self.current_source = self._determine_default_source()

        # Path to manga plugin metadata
        self.metadata_file = get_data_path() / "manga_plugin_metadata.json"
        self._load_metadata()

        # Track the last source where a manga was found (for search results)
        self.last_found_source: str | None = None

    def _load_metadata(self) -> None:
        """Load manga plugin metadata from file.

        Metadata maps manga_id to which plugin has it (e.g., {"manga-id": "mugiwaras"})
        This allows us to remember which plugin a manga was found in.
        Uses OrderedDict to implement LRU behavior.
        """
        self.manga_plugin_map: OrderedDict[str, str] = OrderedDict()
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file) as f:
                    data = json.load(f)
                    # Load into OrderedDict, limiting to 1000 most recent
                    # Assuming the file stores them in some order, or just take first 1000
                    # For LRU, we want the most recent ones.
                    for k, v in itertools.islice(data.items(), 1000):
                        self.manga_plugin_map[k] = v
            except Exception:
                self.manga_plugin_map = OrderedDict()

    def _save_metadata(self) -> None:
        """Save manga plugin metadata to file."""
        try:
            self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_file, "w") as f:
                # Save all entries from current in-memory map
                json.dump(dict(self.manga_plugin_map), f, indent=2)
        except Exception:
            pass  # Silently ignore save errors

    def _record_manga_in_plugin(self, manga_id: str, plugin_name: str) -> None:
        """Record which plugin a manga was found in with LRU eviction."""
        if manga_id in self.manga_plugin_map:
            # Move to end (most recent)
            self.manga_plugin_map.move_to_end(manga_id)

        self.manga_plugin_map[manga_id] = plugin_name

        # Evict oldest if limit exceeded (1000 entries)
        if len(self.manga_plugin_map) > 1000:
            self.manga_plugin_map.popitem(last=False)

        self._save_metadata()

    def _get_known_plugin_for_manga(self, manga_id: str) -> str | None:
        """Get the plugin where a manga was previously found, updating LRU."""
        if manga_id in self.manga_plugin_map:
            # Move to end (most recent)
            self.manga_plugin_map.move_to_end(manga_id)
            return self.manga_plugin_map[manga_id]
        return None

    def _determine_default_source(self) -> str:
        """Determine default source: preferred order, then any available."""
        # Use configured preferred sources
        source_priority = self.config.preferred_sources

        # Try sources in priority order
        for source in source_priority:
            if source in self.plugins:
                return source

        # Fallback to any available source
        available_sources = list(self.plugins.keys())
        if available_sources:
            return available_sources[0]

        # This should not happen due to the check in __init__
        raise RuntimeError("Nenhum plugin de mangá disponível")

    def _get_fallback_source(self, failed_source: str) -> str | None:
        """Get a fallback source when the current source fails."""
        # Use configured preferred sources for fallback logic
        preferred_sources = self.config.preferred_sources

        # Try other preferred sources first
        for source in preferred_sources:
            if source != failed_source and source in self.plugins:
                return source

        # Try any other available source
        for source in self.plugins:
            if source != failed_source:
                return source

        return None

    def get_available_sources(self) -> list[str]:
        """Get list of available manga sources."""
        return list(self.plugins.keys())

    def set_source(self, source: str) -> bool:
        """Set the current manga source. Returns False if not found."""
        if source in self.plugins:
            self.current_source = source
            return True
        return False

    def _record_and_return(
        self, results: list[MangaMetadata], source_name: str
    ) -> list[MangaMetadata]:
        for result in results:
            self._record_manga_in_plugin(result.id, source_name)
        self.last_found_source = source_name
        return results

    def search_manga(self, query: str, source: str | None = None) -> list[MangaMetadata]:
        """Search for manga by title.

        When a specific ``source`` is requested, only that source is queried.
        Otherwise every available source is searched and results are merged by
        normalized title — each merged manga keeps a ``sources`` map of
        source -> id, so the UI can show "Title [source1, source2]".
        """
        source_name = source or self.current_source

        if source_name not in self.plugins:
            raise ValueError(f"Fonte '{source_name}' não disponível")

        # Specific source requested: query only that one (no merging).
        if source is not None:
            try:
                results = self._search_manga_from_source(query, source_name)
            except Exception as e:
                raise ValueError(f"Falha ao buscar em {source_name}: {e}")
            return self._record_and_return(results, source_name) if results else []

        return self._search_all_sources(query, primary=source_name)

    def _search_all_sources(self, query: str, primary: str) -> list[MangaMetadata]:
        """Search every source and merge results by normalized title."""
        # Search primary source first so its id/source wins ties.
        search_order = [primary] + [s for s in self.plugins if s != primary]

        merged: dict[str, MangaMetadata] = {}
        for src in search_order:
            try:
                results = self._search_manga_from_source(query, src)
            except Exception as e:
                logger.info(f"⚠️  Falha na fonte {src}: {e}")
                continue
            if not results:
                continue
            logger.info(f"✓ Encontrados {len(results)} resultado(s) em {src}")
            for manga in results:
                self._record_manga_in_plugin(manga.id, src)
                norm = normalize_title_for_dedup(manga.title) or manga.title.lower()
                existing = merged.get(norm)
                if existing is not None:
                    existing.sources.setdefault(src, manga.id)
                else:
                    manga.sources = {src: manga.id}
                    merged[norm] = manga

        results = list(merged.values())
        self.last_found_source = primary if results else None
        return results

    def _search_manga_from_source(self, query: str, source_name: str) -> list[MangaMetadata]:
        """Search for manga from a specific source."""
        plugin = self.plugins[source_name]
        raw_results = plugin.search_manga(query)

        # Convert plugin results to MangaMetadata objects
        results = []
        for item in raw_results:
            try:
                # Normalize status
                status_str = item.get("status", "ongoing").lower()
                status = _STATUS_MAP.get(status_str, MangaStatus.ONGOING)

                manga = MangaMetadata(
                    id=item["id"],
                    title=item["title"],
                    description=item.get("description"),
                    status=status,
                    year=item.get("year"),
                    tags=item.get("tags", []),
                )
                results.append(manga)
            except (KeyError, ValueError):
                continue

        return results

    def get_chapters(
        self, manga_id: str, manga_url: str | None = None, source: str | None = None
    ) -> list[ChapterData]:
        """Fetch chapters, trying known source from metadata then fallbacks."""
        source_name = source or self.current_source

        if source_name not in self.plugins:
            raise ValueError(f"Fonte '{source_name}' não disponível")

        # Try primary source
        try:
            return self._get_chapters_from_source(manga_id, manga_url, source_name)
        except Exception as e:
            # If specific source requested, don't try others
            if source is not None:
                raise ValueError(f"Falha ao buscar capítulos em {source_name}: {e}")

            # Try known plugin for this manga from metadata
            known_source = self._get_known_plugin_for_manga(manga_id)
            if known_source and known_source != source_name:
                try:
                    logger.info(
                        f"⚠️  Falha em {source_name}, tentando fonte conhecida {known_source}..."
                    )
                    return self._get_chapters_from_source(manga_id, manga_url, known_source)
                except Exception:
                    pass

            # Try other fallback sources
            fallback_source = self._get_fallback_source(source_name)
            if fallback_source:
                logger.info(f"⚠️  Tentando fallback {fallback_source}...")
                try:
                    return self._get_chapters_from_source(manga_id, None, fallback_source)
                except Exception as fallback_error:
                    logger.info(f"⚠️  Falha no fallback {fallback_source}: {fallback_error}")

            # Re-raise the original error
            raise e

    def _get_chapters_from_source(
        self, manga_id: str, manga_url: str | None, source_name: str
    ) -> list[ChapterData]:
        """Get chapters from a specific source. URLs must be populated by plugin."""
        plugin = self.plugins[source_name]

        # Some plugins need the URL, others just the ID
        if manga_url is None:
            template = _MANGA_URL_TEMPLATES.get(source_name, "")
            manga_url = template.format(manga_id) if template else ""

        raw_chapters = plugin.get_chapters(manga_id, manga_url)

        # Convert plugin results to ChapterData objects
        chapters = []
        for item in raw_chapters:
            try:
                # Validate URL is populated by plugin
                url = item.get("url")
                if not url:
                    logger.info(f"⚠️  Capítulo {item['id']} de {source_name} sem URL extraída")

                chapter = ChapterData(
                    id=item["id"],
                    number=item["number"],
                    title=item.get("title"),
                    url=url,  # Store chapter URL from plugin if available
                    language=source_name,  # Use source as language for now
                    published_at=None,  # Not all sources provide this
                    scanlation_group=None,  # Not all sources provide this
                )
                chapters.append(chapter)
            except (KeyError, ValueError):
                continue

        return chapters

    def get_chapter_pages(
        self, chapter_id: str, chapter_url: str | None = None, source: str | None = None
    ) -> list[str]:
        """Fetch image URLs for a chapter."""
        source_name = source or self.current_source

        if source_name not in self.plugins:
            raise ValueError(f"Fonte '{source_name}' não disponível")

        plugin = self.plugins[source_name]

        # Some plugins need the URL, others just the ID
        if chapter_url is None or chapter_url == "":
            if source_name == "mangadex":
                chapter_url = f"https://mangadex.org/chapter/{chapter_id}"
            # For other sources like mangalivre, mugiwaras that need URL,
            # pass empty string only if URL construction isn't available
            # Let plugin handle empty URL gracefully

        return plugin.get_chapter_pages(chapter_id, chapter_url or "")

    def check_manga_available(self, manga_title: str, source: str | None = None) -> bool:
        """Quick check if a manga is available in a source."""
        source_name = source or self.current_source

        if source_name not in self.plugins:
            return False

        try:
            results = self._search_manga_from_source(manga_title, source_name)
            return len(results) > 0
        except Exception:
            return False

    def get_available_sources_for_manga(self, manga_title: str) -> list[str]:
        """Get list of sources that have a specific manga."""
        available = []
        for source in self.plugins:
            if self.check_manga_available(manga_title, source):
                available.append(source)
        return available


class MangaDexClient(UnifiedMangaService):
    """Legacy MangaDex client for backward compatibility.

    Use UnifiedMangaService instead for new code.
    """

    def __init__(self, config: MangaSettings):
        """Initialize with MangaDex as default source."""
        super().__init__(config)
        # Force MangaDex as default for backward compatibility
        if "mangadex" in self.plugins:
            self.current_source = "mangadex"
