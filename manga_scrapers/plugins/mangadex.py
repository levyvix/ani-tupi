"""MangaDex API scraper plugin.

Refactored from the original manga_service.py to fit the plugin architecture.
Uses requests for API communication.
"""

from typing import Any

import httpx


class MangaDex:
    """MangaDex API scraper plugin."""

    name = "mangadex"
    base_url = "https://api.mangadex.org"

    def __init__(self):
        """Initialize MangaDex scraper."""
        pass

    def search_manga(self, query: str) -> list[dict[str, Any]]:
        """Search for manga by title.

        Args:
            query: Search query string

        Returns:
            List of manga results
        """
        try:
            resp = httpx.get(
                f"{self.base_url}/manga",
                params={"title": query, "limit": 100},
                timeout=10,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        if not data.get("data"):
            return []

        results = []
        for item in data["data"]:
            try:
                attrs = item["attributes"]
                manga_id = item["id"]
                title = self._get_title(attrs)
                description = attrs.get("description", {}).get("en")
                status = attrs.get("status", "ongoing")
                year = attrs.get("year")
                tags = [tag["attributes"]["name"]["en"] for tag in attrs.get("tags", [])]

                results.append(
                    {
                        "id": manga_id,
                        "title": title,
                        "url": f"https://mangadex.org/title/{manga_id}",
                        "description": description,
                        "status": status,
                        "year": year,
                        "tags": tags,
                    }
                )
            except (KeyError, ValueError):
                continue

        return results

    def get_chapters(self, manga_id: str, manga_url: str) -> list[dict[str, Any]]:
        """Fetch chapter list for a manga.

        Extracts chapter URLs by constructing them from chapter IDs:
        https://mangadex.org/chapter/{chapter_id}

        Args:
            manga_id: MangaDex manga ID
            manga_url: Manga URL (not used for API)

        Returns:
            List of chapters with "url" field populated by plugin
        """
        try:
            chapters = []
            offset = 0
            limit = 96

            while True:
                # Build params with pt-br language filter
                params: dict = {
                    "limit": limit,
                    "offset": offset,
                    "order[chapter]": "asc",
                    "includeEmptyPages": "0",
                    "includeFuturePublishAt": "0",
                    "translatedLanguage[]": ["pt-br"],
                }

                resp = httpx.get(
                    f"{self.base_url}/manga/{manga_id}/feed",
                    params=params,
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

                        chapter_id = item["id"]
                        number = str(attrs["chapter"])
                        title = attrs.get("title")

                        chapters.append(
                            {
                                "id": chapter_id,
                                "number": number,
                                "title": title,
                                "url": f"https://mangadex.org/chapter/{chapter_id}",
                            }
                        )
                    except (KeyError, ValueError):
                        continue

                total = data.get("total", 0)
                offset += limit
                if offset >= total or len(data["data"]) < limit:
                    break

            # Sort by chapter number (descending - latest first)
            chapters.sort(
                key=lambda c: float(c["number"]),
                reverse=True,
            )

            return chapters

        except Exception:
            return []

    def get_chapter_pages(self, chapter_id: str, chapter_url: str) -> list[str]:
        """Fetch image URLs for a chapter.

        Args:
            chapter_id: MangaDex chapter ID
            chapter_url: Chapter URL (not used for API)

        Returns:
            List of image URLs
        """
        try:
            resp = httpx.get(
                f"{self.base_url}/at-home/server/{chapter_id}",
                timeout=10,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()

            base_url = data["baseUrl"]
            hash_code = data["chapter"]["hash"]
            files = data["chapter"]["data"]

            return [f"{base_url}/data/{hash_code}/{filename}" for filename in files]

        except Exception:
            return []

    @staticmethod
    def _get_title(attrs: dict[str, Any]) -> str:
        """Extract manga title from attributes.

        Tries preferred languages first, then fallbacks.

        Args:
            attrs: Manga attributes from API

        Returns:
            Manga title in preferred language
        """
        # Try Portuguese first (altTitles is a list of dicts)
        alt_titles = attrs.get("altTitles", [])
        if isinstance(alt_titles, list):
            for alt_title in alt_titles:
                if isinstance(alt_title, dict):
                    if "pt-br" in alt_title:
                        return alt_title["pt-br"]

        # Try English in title
        title = attrs.get("title", {})
        if isinstance(title, dict):
            if "en" in title:
                return title["en"]

        # Try Japanese in title
        if isinstance(title, dict):
            if "ja" in title:
                return title["ja"]

        # Try Romanized Japanese (ja-ro)
        if isinstance(title, dict):
            if "ja-ro" in title:
                return title["ja-ro"]

        # Fallback to first available language in title
        if isinstance(title, dict):
            value = next(iter(title.values()))
            if isinstance(value, str):
                return value

        return "Unknown"


def load():
    """Load MangaDex plugin.

    Returns:
        Plugin instance
    """
    return MangaDex()
