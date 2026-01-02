"""MangaDex API client and manga service layer.

Provides:
- MangaDexClient: API client with error handling and caching
- MangaCache: Simple in-memory cache with TTL
- MangaHistory: Reading progress persistence
- Custom exceptions: MangaError, MangaNotFoundError, etc.
"""

import json
import time
from typing import Any

import requests

from models.config import MangaSettings, get_data_path
from models.models import ChapterData, MangaHistoryEntry, MangaMetadata, MangaStatus


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


class ChapterNotAvailableError(MangaError):
    """Chapter not available in selected languages."""

    user_message = "Capítulo não disponível no idioma selecionado."


class MangaCache:
    """Simple in-memory cache with TTL."""

    def __init__(self, ttl_hours: int):
        """Initialize cache with TTL.

        Args:
            ttl_hours: Time to live for cached items in hours
        """
        self.ttl_seconds = ttl_hours * 3600
        self.cache: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        if key not in self.cache:
            return None

        value, expire_time = self.cache[key]
        if time.time() > expire_time:
            del self.cache[key]
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        """Set cached value with TTL.

        Args:
            key: Cache key
            value: Value to cache
        """
        expire_time = time.time() + self.ttl_seconds
        self.cache[key] = (value, expire_time)

    def clear(self) -> None:
        """Clear all cache."""
        self.cache.clear()


class MangaHistory:
    """Reading progress tracker with JSON persistence."""

    _history_file = get_data_path() / "manga_history.json"

    @classmethod
    def _ensure_dir(cls) -> None:
        """Ensure history directory exists."""
        cls._history_file.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls) -> dict[str, MangaHistoryEntry]:
        """Load history from file.

        Returns:
            Dictionary mapping manga titles to history entries
        """
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
        """Save history to file.

        Args:
            history: Dictionary mapping titles to history entries
        """
        cls._ensure_dir()

        data = {title: entry.model_dump() for title, entry in history.items()}

        try:
            with cls._history_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except IOError as e:
            raise MangaError(f"Failed to save history: {e}")

    @classmethod
    def get_last_chapter(cls, manga_title: str) -> str | None:
        """Get last read chapter for manga.

        Args:
            manga_title: Manga title to look up

        Returns:
            Chapter number string or None if not found
        """
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
    ) -> None:
        """Update reading progress.

        Args:
            manga_title: Manga title
            chapter_number: Chapter number read
            chapter_id: Optional MangaDex chapter ID
            manga_id: Optional MangaDex manga ID
        """
        history = cls.load()
        history[manga_title] = MangaHistoryEntry(
            last_chapter=chapter_number,
            last_chapter_id=chapter_id,
            manga_id=manga_id,
        )
        cls.save(history)


class MangaDexClient:
    """MangaDex API client with caching and error handling."""

    def __init__(self, config: MangaSettings):
        """Initialize MangaDex client.

        Args:
            config: Manga configuration settings
        """
        self.base_url = config.api_url
        self.languages = config.languages
        self.cache = MangaCache(config.cache_duration_hours)

    def search_manga(self, query: str) -> list[MangaMetadata]:
        """Search for manga by title.

        Uses cache to avoid repeated API calls.

        Args:
            query: Search query (manga title)

        Returns:
            List of MangaMetadata objects

        Raises:
            MangaNotFoundError: If no results found
            MangaDexError: If API call fails
        """
        cache_key = f"search:{query.lower()}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            resp = requests.get(
                f"{self.base_url}/manga",
                params={"title": query, "limit": 100},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise MangaDexError(f"Search failed: {e}")

        if not data.get("data"):
            raise MangaNotFoundError()

        results = []
        for item in data["data"]:
            try:
                attrs = item["attributes"]
                manga = MangaMetadata(
                    id=item["id"],
                    title=self._get_title(attrs),
                    description=attrs.get("description", {}).get("en"),
                    status=MangaStatus(attrs.get("status", "ongoing")),
                    year=attrs.get("year"),
                    tags=[tag["attributes"]["name"]["en"] for tag in attrs.get("tags", [])],
                )
                results.append(manga)
            except (KeyError, ValueError):
                continue

        if not results:
            raise MangaNotFoundError()

        self.cache.set(cache_key, results)
        return results

    def get_chapters(self, manga_id: str) -> list[ChapterData]:
        """Fetch chapters for a manga.

        Filters by configured languages and paginates.

        Args:
            manga_id: MangaDex manga ID

        Returns:
            List of ChapterData objects sorted by chapter number

        Raises:
            MangaDexError: If API call fails
        """
        cache_key = f"chapters:{manga_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            chapters = []
            offset = 0

            while True:
                resp = requests.get(
                    f"{self.base_url}/manga/{manga_id}/feed",
                    params={
                        "limit": 500,
                        "offset": offset,
                        "translatedLanguage[]": self.languages,
                        "order[chapter]": "asc",
                        "includeEmptyPages": 0,
                        "includeFuturePublishAt": 0,
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

                if not data.get("data"):
                    break

                for item in data["data"]:
                    try:
                        attrs = item["attributes"]
                        if attrs.get("chapter") is None:
                            continue

                        chapter = ChapterData(
                            id=item["id"],
                            number=str(attrs["chapter"]),
                            title=attrs.get("title"),
                            language=attrs.get("translatedLanguage", "unknown"),
                            published_at=attrs.get("publishAt"),
                            scanlation_group=self._get_group_name(item),
                        )
                        chapters.append(chapter)
                    except (KeyError, ValueError):
                        continue

                offset += 500
                if len(data["data"]) < 500:
                    break

            # Sort by chapter number
            chapters.sort(
                key=lambda c: float(c.number),
                reverse=True,
            )

            self.cache.set(cache_key, chapters)
            return chapters

        except requests.RequestException as e:
            raise MangaDexError(f"Failed to fetch chapters: {e}")

    def get_chapter_pages(self, chapter_id: str) -> list[str]:
        """Fetch image URLs for a chapter.

        Does not cache (changes frequently).

        Args:
            chapter_id: MangaDex chapter ID

        Returns:
            List of image URLs

        Raises:
            MangaDexError: If API call fails
        """
        try:
            resp = requests.get(
                f"{self.base_url}/at-home/server/{chapter_id}",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            base_url = data["baseUrl"]
            hash_code = data["chapter"]["hash"]
            files = data["chapter"]["data"]

            return [f"{base_url}/data/{hash_code}/{filename}" for filename in files]

        except requests.RequestException as e:
            raise MangaDexError(f"Failed to fetch chapter pages: {e}")

    @staticmethod
    def _get_title(attrs: dict[str, Any]) -> str:
        """Extract manga title from attributes.

        Tries preferred language first, then fallbacks.

        Args:
            attrs: Manga attributes from API

        Returns:
            Manga title in preferred language
        """
        # Try Portuguese first
        if "pt-br" in attrs.get("altTitles", []):
            return attrs["altTitles"]["pt-br"]

        # Try English
        if "en" in attrs.get("title", {}):
            return attrs["title"]["en"]

        # Try Japanese
        if "ja" in attrs.get("title", {}):
            return attrs["title"]["ja"]

        # Fallback to first available
        if isinstance(attrs.get("title"), dict):
            return next(iter(attrs["title"].values()))

        return "Unknown"

    @staticmethod
    def _get_group_name(chapter_item: dict[str, Any]) -> str | None:
        """Extract scanlation group name from chapter.

        Args:
            chapter_item: Chapter item from API

        Returns:
            Group name or None if not available
        """
        relationships = chapter_item.get("relationships", [])
        for rel in relationships:
            if rel.get("type") == "scanlation_group":
                try:
                    return rel["attributes"]["name"]
                except KeyError:
                    pass
        return None
