"""MangaLivre.blog manga scraper.

Scrapes manga from https://mangalivre.blog/ (Brazilian Portuguese site).
Uses Selenium WebDriver for search and dynamic AJAX-loaded chapters.
Adaptive CSS selectors survive website design changes.
"""

import re
import time
from typing import Any

from scrapers.core.selenium_driver import SeleniumWebDriver
from utils.logging import get_logger

logger = get_logger(__name__)


class MangaLivre:
    """MangaLivre.blog scraper plugin."""

    name = "mangalivre"
    languages = ["pt-br"]
    base_url = "https://mangalivre.blog"

    def __init__(self):
        """Initialize scraper with SeleniumWebDriver."""
        pass  # Use SeleniumWebDriver.fetch() directly, no instance needed

    def search_manga(self, query: str) -> list[dict[str, Any]]:
        """Search for manga by title.

        Args:
            query: Search query string

        Returns:
            List of manga results with structure:
            [
                {
                    "id": "unique-id",
                    "title": "Manga Title",
                    "url": "https://...",
                    "description": "Description or None",
                    "status": "ongoing",
                    "year": None,
                }
            ]
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Use WordPress search endpoint
                search_url = f"{self.base_url}/?s={query.replace(' ', '+')}&post_type=wp-manga"

                # Add delay before retry to avoid rate limiting
                if retry_count > 0:
                    time.sleep(2)

                # Fetch search results with Selenium
                tree = SeleniumWebDriver().fetch(search_url)

                results = []

                # Parse manga results from WordPress theme
                # Search results use div.manga-card structure
                manga_cards = tree.select("div.manga-card")

                for card in manga_cards:
                    try:
                        # Extract link and title
                        links = card.select("a")
                        if not links:
                            continue

                        link = links[0]
                        if not link:
                            continue
                        url_val = link.attrib.get("href", "")  # type: ignore
                        url = (
                            url_val if isinstance(url_val, str) else str(url_val) if url_val else ""
                        )
                        if not url:
                            continue

                        # Extract title - try multiple selectors
                        # MangaLivre uses h2, h3, h4 or spans for titles
                        h2s = card.select("h2")
                        h3s = card.select("h3")
                        h4s = card.select("h4")
                        span_titles = card.select("span[class*='title']")
                        title_spans = card.select(".title")

                        title_elem = (
                            h2s[0]
                            if h2s
                            else (
                                h3s[0]
                                if h3s
                                else (
                                    h4s[0]
                                    if h4s
                                    else (
                                        span_titles[0]
                                        if span_titles
                                        else (title_spans[0] if title_spans else None)
                                    )
                                )
                            )
                        )
                        title = str(title_elem.text) if title_elem else str(link.text)
                        title = title.strip()

                        if not title or title.isspace():
                            continue

                        # Extract description if available
                        desc_elems = card.select("p")
                        description = str(desc_elems[0].text).strip() if desc_elems else None

                        # Extract status if available
                        status_elems = card.select("span")
                        status = (
                            str(status_elems[0].text).strip().lower() if status_elems else "ongoing"
                        )

                        # Extract manga ID from URL (slug)
                        if isinstance(url, str):
                            manga_id = url.rstrip("/").split("/")[-1]
                        else:
                            manga_id = str(url).rstrip("/").split("/")[-1] if url else "unknown"

                        results.append(
                            {
                                "id": manga_id,
                                "title": title,
                                "url": url,
                                "description": description,
                                "status": status,
                                "year": None,  # Not available in search results
                            }
                        )
                    except Exception:
                        # Skip malformed entries
                        continue

                return results

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.info(f"⚠️  Erro ao buscar mangá (após {max_retries} tentativas): {e}")
                    return []
                logger.info(f"⚠️  Erro ao buscar mangá (tentativa {retry_count}): {e}")

        return []

    def get_chapters(self, manga_id: str, manga_url: str) -> list[dict[str, Any]]:
        """Fetch chapter list for a manga.

        Extracts chapter URLs directly from HTML href attributes in the chapter list.
        Each chapter's "url" field is populated with the link extracted from the website.

        Args:
            manga_id: Manga ID (slug)
            manga_url: Manga URL

        Returns:
            List of chapters with "url" field extracted from HTML href attributes:
            [
                {
                    "id": "chapter-id",
                    "number": "1",
                    "title": "Chapter Title or None",
                    "url": "https://...",
                }
            ]
        """
        try:
            # Use Selenium to render page and wait for AJAX-loaded chapters
            tree = SeleniumWebDriver().fetch(manga_url)

            chapters = []

            # Extract chapter list - MangaLivre uses li.chapter-item
            chapter_items = tree.select("li.chapter-item")

            for item in chapter_items:
                try:
                    links = item.select("a")
                    if not links:
                        continue

                    link = links[0]
                    if not link:
                        continue
                    url_val = link.attrib.get("href", "")  # type: ignore[union-attr]
                    chapter_url = (
                        url_val if isinstance(url_val, str) else str(url_val) if url_val else ""
                    )
                    chapter_title = str(link.text).strip() if hasattr(link, "text") else ""

                    if not chapter_url:
                        continue

                    # Extract chapter number from title or URL
                    # Typical format: "Capítulo 222 - Título" or "capitulo-222"
                    number_match = re.search(
                        r"capítulo\s+(\d+(?:\.\d+)?)", chapter_title, re.IGNORECASE
                    )
                    if number_match:
                        chapter_number = number_match.group(1)
                    else:
                        # Try extracting from URL
                        chapter_url_str = (
                            chapter_url if isinstance(chapter_url, str) else str(chapter_url)
                        )
                        url_match = re.search(r"capitulo-(\d+(?:\.\d+)?)", chapter_url_str)
                        if url_match:
                            chapter_number = url_match.group(1)
                        else:
                            continue  # Skip if no number found

                    # Generate chapter ID from URL
                    chapter_url_str = (
                        chapter_url if isinstance(chapter_url, str) else str(chapter_url)
                    )
                    chapter_id = chapter_url_str.rstrip("/").split("/")[-1]

                    # Clean chapter title (remove "Capítulo X" and similar)
                    clean_title = re.sub(
                        r"capítulo\s+\d+(\.\d+)?\s*-?\s*",
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
            logger.info(f"⚠️  Erro ao buscar capítulos: {e}")
            return []

    def get_chapter_pages(self, chapter_id: str, chapter_url: str) -> list[str]:
        """Fetch image URLs for a chapter.

        Args:
            chapter_id: Chapter ID
            chapter_url: Chapter URL

        Returns:
            List of image URLs (absolute URLs)
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Use Selenium to render the page with JavaScript

                if retry_count > 0:
                    time.sleep(2)  # Wait before retrying

                tree = SeleniumWebDriver().fetch(chapter_url)

                page_urls = []

                # Extract all images from the page
                all_images = tree.select("img")

                for img in all_images:
                    if not img:
                        continue
                    # Try multiple attributes where image URL might be
                    # WordPress lazy-loading uses data-src or data-lazy-src
                    img_url = (
                        img.attrib.get("data-src")  # type: ignore
                        or img.attrib.get("data-lazy-src")  # type: ignore
                        or img.attrib.get("src")  # type: ignore
                        or img.attrib.get("data-original")  # type: ignore
                    )

                    # Skip if no URL
                    if not img_url:
                        continue

                    # Strip whitespace
                    img_url_str = img_url if isinstance(img_url, str) else str(img_url)
                    img_url = img_url_str.strip()

                    # Normalize URL - handle relative URLs
                    if not img_url.startswith("http"):
                        if img_url.startswith("//"):
                            img_url = "https:" + img_url
                        elif img_url.startswith("/"):
                            img_url = self.base_url + img_url
                        else:
                            continue

                    # Filter for manga page images
                    # MangaLivre stores images in /wp-content/uploads/
                    is_manga_page = "/wp-content/uploads/" in img_url.lower()

                    # Skip logos, banners, ads, and other non-manga content
                    is_noise = any(
                        skip in img_url.lower()
                        for skip in [
                            "logo",
                            "banner",
                            "/ad/",
                            "/ads/",
                            "sidebar",
                            "amazon",
                            "cropped-",
                            ".gif",
                        ]
                    )

                    # Ensure it's an actual image file
                    is_image = any(
                        img_url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]
                    )

                    if is_manga_page and not is_noise and is_image and img_url not in page_urls:
                        page_urls.append(img_url)

                # If no pages found and we can retry, do so
                if not page_urls and retry_count < max_retries - 1:
                    retry_count += 1
                    logger.info(f"⚠️  Nenhuma página encontrada, tentativa {retry_count + 1}...")
                    continue

                return page_urls

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.info(
                        f"⚠️  Erro ao buscar páginas do capítulo (após {max_retries} tentativas): {e}"
                    )
                    return []
                logger.info(f"⚠️  Erro ao buscar páginas do capítulo (tentativa {retry_count}): {e}")

        return []


def load(languages: set[str]):
    """Load MangaLivre plugin if pt-br is in languages.

    Args:
        languages: Set of supported languages

    Returns:
        Plugin instance or None
    """
    if "pt-br" in languages:
        return MangaLivre()
    return None
