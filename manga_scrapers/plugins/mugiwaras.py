"""MugiwarasOficial.com manga scraper.

Scrapes manga from https://mugiwarasoficial.com/ (Brazilian Portuguese site).
Uses Selenium for dynamic content rendering and chapter extraction.
"""

import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from scrapers.core.selenium_driver import SeleniumWebDriver
from utils.logging import get_logger

logger = get_logger(__name__)


class MugiwarasOficial:
    """MugiwarasOficial.com scraper plugin."""

    name = "mugiwaras"
    base_url = "https://mugiwarasoficial.com"

    def __init__(self):
        self._driver: SeleniumWebDriver | None = None

    def _fetch(self, url: str, **kwargs):
        if self._driver is None:
            self._driver = SeleniumWebDriver()
        try:
            return self._driver.fetch(url, **kwargs)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def search_manga(self, query: str) -> list[dict[str, Any]]:
        """Search for manga by title.

        Args:
            query: Search query string

        Returns:
            List of manga results
        """
        try:
            # Use WordPress search endpoint
            search_url = f"{self.base_url}/?s={query.replace(' ', '+')}&post_type=wp-manga"

            # Fetch with Selenium for robustness
            tree = self._fetch(search_url)

            results = []

            # Parse manga results from Madara theme
            # Each manga is in a div with class "row c-tabs-item__content"
            manga_items = tree.select("div.row.c-tabs-item__content")

            for item in manga_items:
                try:
                    # Extract title and URL from the link
                    link = item.select_one("div.post-title a")
                    if not link:
                        continue

                    title = str(link.text).strip()
                    url = link.get("href", "")

                    if not title or not url:
                        continue

                    # Extract latest chapter info (optional)
                    latest_chapter = item.select_one("span.chapter a")
                    latest_chapter_text = (
                        str(latest_chapter.text).strip() if latest_chapter else None
                    )

                    # Extract manga ID from URL (slug)
                    manga_id = url.rstrip("/").split("/")[-1]

                    results.append(
                        {
                            "id": manga_id,
                            "title": title,
                            "url": url,
                            "description": None,  # Not available in search results
                            "status": "ongoing",  # Default, can be updated from detail page
                            "year": None,  # Not available in search results
                            "latest_chapter": latest_chapter_text,
                        }
                    )
                except Exception:
                    # Skip malformed entries
                    continue

            return results

        except Exception as e:
            logger.info(f"⚠️  Erro ao buscar mangá: {e}")
            return []

    def get_chapters(self, manga_id: str, manga_url: str) -> list[dict[str, Any]]:
        """Fetch chapter list for a manga.

        Extracts chapter URLs directly from HTML href attributes in the chapter list.
        Each chapter's "url" field is populated with the link extracted from the website.

        Args:
            manga_id: Manga ID (slug)
            manga_url: Manga URL

        Returns:
            List of chapters with "url" field extracted from HTML href attributes
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Use Selenium to render the page and wait for AJAX-loaded chapters
                # Increase timeout on retry attempts and add small delay between retries
                if retry_count > 0:
                    time.sleep(2)  # Wait before retrying

                with SeleniumWebDriver() as driver:
                    tree = driver.fetch(manga_url)

                chapters = []

                # Extract chapter list
                chapter_items = tree.select("li.wp-manga-chapter")

                # If no chapters found and we can retry, do so
                if not chapter_items and retry_count < max_retries - 1:
                    retry_count += 1
                    logger.info(f"⚠️  Nenhum capítulo encontrado, tentativa {retry_count + 1}...")
                    continue

                for item in chapter_items:
                    try:
                        links = item.select("a")
                        if not links:
                            continue

                        link = links[0]
                        chapter_url = link.get("href", "")
                        chapter_title = str(link.text).strip()

                        if not chapter_url:
                            continue

                        # Extract chapter number from title or URL
                        # Typical format: "Capítulo 222 PT-BR" or "capitulo-222-pt-br"
                        number_match = re.search(r"(\d+(?:\.\d+)?)", chapter_title)
                        if number_match:
                            chapter_number = number_match.group(1)
                        else:
                            # Try extracting from URL
                            url_match = re.search(r"capitulo-(\d+(?:\.\d+)?)", chapter_url)
                            if url_match:
                                chapter_number = url_match.group(1)
                            else:
                                continue  # Skip if no number found

                        # Generate chapter ID from URL
                        chapter_id = chapter_url.rstrip("/").split("/")[-1]

                        # Clean chapter title (remove "Capítulo X PT-BR")
                        clean_title = re.sub(
                            r"capítulo\s+\d+(\.\d+)?\s*-?\s*pt-br",
                            "",
                            chapter_title,
                            flags=re.IGNORECASE,
                        ).strip()
                        if clean_title and clean_title != chapter_title:
                            final_title = clean_title
                        else:
                            final_title = None

                        chapters.append(
                            {
                                "id": chapter_id,
                                "number": chapter_number,
                                "title": final_title,
                                "url": chapter_url,
                            }
                        )
                    except Exception:
                        continue

                # Sort chapters by number (descending - latest first)
                chapters.sort(key=lambda c: float(c["number"]), reverse=True)

                return chapters

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.info(f"⚠️  Erro ao buscar capítulos (após {max_retries} tentativas): {e}")
                    return []
                logger.info(f"⚠️  Erro ao buscar capítulos (tentativa {retry_count}): {e}")

        return []

    # CDN page filename pattern: ".../<dir>/01.webp"
    _PAGE_RE = re.compile(r"^(.*/)(\d+)\.([a-zA-Z]+)$")
    _MAX_PAGES = 300

    def get_chapter_pages(self, chapter_id: str, chapter_url: str) -> list[str]:
        """Fetch image URLs for a chapter.

        MugiwarasOficial embeds only the first page in the DOM, wrapped in an
        ad-redirect ``<a href="https://.../jump/...?a=<real_cdn_url>">``. The
        remaining pages live in the same CDN directory with sequential,
        zero-padded filenames (``01.webp``, ``02.webp``, ...). We extract the
        first page's real URL, then enumerate the directory until a gap (404).

        Args:
            chapter_id: Chapter ID
            chapter_url: Chapter URL

        Returns:
            List of image URLs
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                if retry_count > 0:
                    time.sleep(2)  # Wait before retrying

                with SeleniumWebDriver() as driver:
                    tree = driver.fetch(chapter_url)

                first_url = self._extract_first_page_url(tree)

                if not first_url and retry_count < max_retries - 1:
                    retry_count += 1
                    logger.info(f"⚠️  Nenhuma página encontrada, tentativa {retry_count + 1}...")
                    continue

                if not first_url:
                    return []

                return self._enumerate_pages(first_url)

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.info(
                        f"⚠️  Erro ao buscar páginas do capítulo (após {max_retries} tentativas): {e}"
                    )
                    return []
                logger.info(f"⚠️  Erro ao buscar páginas do capítulo (tentativa {retry_count}): {e}")

        return []

    def _extract_first_page_url(self, tree) -> str | None:
        """Find the first chapter page URL embedded in the chapter HTML.

        Looks for the CDN page path (``/manga_.../<hash>/NN.ext``) inside the
        ad-redirect anchor's ``a`` query param, falling back to a direct match
        on any attribute that already points at the CDN page directory.
        """
        for tag in tree.find_all("a"):
            href = tag.get("href", "")
            if "/manga_" not in href:
                continue
            real = parse_qs(urlparse(href).query).get("a", [None])[0]
            if real and "/manga_" in real and self._PAGE_RE.match(real):
                return real.strip()

        # Fallback: a tag attribute may already hold the bare CDN page URL
        for tag in tree.find_all(True):
            for value in tag.attrs.values():
                if (
                    isinstance(value, str)
                    and "/manga_" in value
                    and value.strip().startswith("http")
                    and self._PAGE_RE.match(value.strip())
                ):
                    return value.strip()
        return None

    def _enumerate_pages(self, first_url: str) -> list[str]:
        """Enumerate sequential CDN page URLs starting from the first page.

        Derives the directory, numeric width and extension from ``first_url``,
        then probes incrementing page numbers until the first missing page.
        """
        match = self._PAGE_RE.match(first_url)
        if not match:
            return [first_url]

        prefix, num, ext = match.groups()
        width = len(num)
        start = int(num)

        pages: list[str] = []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": f"{self.base_url}/",
        }
        with httpx.Client(headers=headers, timeout=15, follow_redirects=True) as client:
            for n in range(start, start + self._MAX_PAGES):
                url = f"{prefix}{n:0{width}d}.{ext}"
                try:
                    resp = client.head(url)
                except httpx.HTTPError:
                    break
                if resp.status_code != 200:
                    break
                pages.append(url)
        return pages


def load():
    """Load MugiwarasOficial plugin.

    Returns:
        Plugin instance
    """
    return MugiwarasOficial()
