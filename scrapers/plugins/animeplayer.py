"""AnimePlyer scraper for animeplayer.com.br

Scrapes anime metadata, episodes, and video URLs from animeplayer.com.br.
Uses StealthyFetcher to bypass Cloudflare protection.

Note: AnimePlyer uses proxy URLs with ?link= parameter containing the real video URL.
Example: https://traffic.thatwebsite.com.br/jax/?link=<real_video_url>
"""

import re
from urllib.parse import urlparse, parse_qs
from selectolax.parser import HTMLParser
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

try:
    from scrapling.fetchers import StealthySession  # type: ignore[import-not-found]

    HAS_SCRAPLING = True
except ImportError:
    HAS_SCRAPLING = False

from scrapers.core.browser_pool import get_browser_pool
from scrapers.plugins.utils import get_with_retry, head_with_retry
from services.repository import rep


def extract_real_video_url(proxy_url: str) -> str:
    """Extract real video URL from AnimePlyer proxy URL.

    AnimePlyer uses proxy URLs with the real video URL in the ?link= parameter.

    Args:
        proxy_url: URL like https://traffic.thatwebsite.com.br/jax/?link=<video_url>

    Returns:
        Real video URL, or original URL if extraction fails
    """
    try:
        # Parse the URL
        parsed = urlparse(proxy_url)

        # Extract query parameters
        query_params = parse_qs(parsed.query)

        # Get the 'link' parameter (it's a list, so take first item)
        if "link" in query_params and query_params["link"]:
            real_url = query_params["link"][0]
            return real_url
    except Exception:
        pass

    # If extraction fails, return original URL
    return proxy_url


class AnimePlyer:
    """AnimePlyer scraper for animeplayer.com.br."""

    languages = ["pt-br"]
    name = "animeplayer"

    def search_anime(self, query: str) -> None:
        """Search for anime on AnimePlyer.

        Uses StealthyFetcher to bypass Cloudflare protection.
        Extracts anime titles and links from search results.
        """
        import sys
        import os

        search_url = f"https://animeplayer.com.br/?s={'+'.join(query.split())}"
        debug = os.getenv("ANI_TUPI_DEBUG_ANIMEPLAYER", "").lower() == "true"

        try:
            # Use StealthyFetcher to bypass Cloudflare
            if HAS_SCRAPLING:
                if debug:
                    print(f"[AnimePlyer] Using StealthyFetcher for: {search_url}", file=sys.stderr)
                with StealthySession() as session:
                    response = session.fetch(search_url)
                    content = response.content
            else:
                # Fallback to regular requests if scrapling not available
                if debug:
                    print(f"[AnimePlyer] Using get_with_retry for: {search_url}", file=sys.stderr)
                response = get_with_retry(search_url, timeout=15)
                content = response.text

            if debug:
                print(f"[AnimePlyer] Got content, length: {len(content)}", file=sys.stderr)

            tree = HTMLParser(content)

            # Look for anime result containers
            # AnimePlyer typically uses article tags or divs with specific classes
            anime_containers = tree.css(
                "article, div[class*='anime'], div[class*='item'], div[class*='post']"
            )

            if debug:
                print(f"[AnimePlyer] Found {len(anime_containers)} containers", file=sys.stderr)

            titles = []
            urls = []

            for container in anime_containers:
                # Find the link and title
                link = container.css_first("a[href*='episodios']") or container.css_first("a")

                if link:
                    href = link.attributes.get("href", "")
                    title = link.text().strip()

                    # Clean title
                    title = " ".join(title.split())

                    if href and title and href.startswith("http"):
                        titles.append(title)
                        urls.append(href)
                        if debug:
                            print(f"[AnimePlyer] Found: {title[:50]}", file=sys.stderr)

            if debug:
                print(f"[AnimePlyer] Total results: {len(titles)}", file=sys.stderr)

            # Add to repository
            for title, url in zip(titles, urls):
                rep.add_anime(title, url, self.name)

        except Exception as e:
            # Print error for debugging
            import traceback

            if debug:
                print(f"[AnimePlyer] Error: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
            pass

    def search_episodes(self, anime: str, url: str, params: dict | None) -> None:
        """Fetch episode list from anime page.

        Uses StealthyFetcher to bypass Cloudflare.
        Extracts episode links from the anime detail page.
        Episodes are typically in a list or carousel format.
        """
        try:
            # Try StealthyFetcher first for Cloudflare bypass
            if HAS_SCRAPLING:
                with StealthySession() as session:
                    response = session.fetch(url)
                    content = response.content
            else:
                # Fallback to browser automation
                with get_browser_pool().get_browser() as driver:
                    driver.get(url)

                    # Wait for page to load
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_all_elements_located((By.TAG_NAME, "body"))
                        )
                    except:
                        pass

                    content = driver.page_source

            tree = HTMLParser(content)

            # Look for episode links
            # Common patterns: a[href*='episodios'], a[href*='ep-'], li a
            episode_links = tree.css("a[href*='episodios']")

            if not episode_links:
                # Try alternative patterns
                episode_links = tree.css("a[href*='ep-']")

            if not episode_links:
                # Try finding in lists
                episode_links = tree.css("li a, div[class*='episode'] a")

            episode_titles = []
            episode_urls = []

            for link in episode_links:
                href = link.attributes.get("href", "")
                title = link.text().strip()

                # Clean title
                title = " ".join(title.split())

                if href and title and href.startswith("http"):
                    episode_urls.append(href)
                    episode_titles.append(title)

            # Add episodes to repository
            if episode_titles and episode_urls:
                rep.add_episode_list(anime, episode_titles, episode_urls, self.name)

        except Exception:
            # Fail silently
            pass

    def search_player_src(self, url: str, container: list, event) -> None:
        """Extract video URL from episode player.

        Uses browser automation to load JavaScript-rendered content.
        AnimePlyer has multiple player options (#option-1, #option-2, etc.)
        with video URLs stored in data-src attributes.
        """
        try:
            with get_browser_pool().get_browser() as driver:
                driver.get(url)

                # Wait for player to load
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div.player-placeholder[data-src]")
                        )
                    )
                except:
                    raise Exception("Could not find player element on page")

                # Method 1: Extract from data-src attribute of player-placeholder divs
                # AnimePlyer stores proxy URLs in data-src, with real video URL in ?link= parameter
                try:
                    player_divs = driver.find_elements(
                        By.CSS_SELECTOR, "div.player-placeholder[data-src]"
                    )

                    if player_divs:
                        # Get the active player (usually first or marked with .active class)
                        active_div = None
                        for div in player_divs:
                            if "active" in div.get_attribute("class"):
                                active_div = div
                                break

                        # If no active div, use the first one
                        if not active_div:
                            active_div = player_divs[0]

                        proxy_url = active_div.get_attribute("data-src")
                        if proxy_url:
                            # Extract real video URL from ?link= parameter
                            video_url = extract_real_video_url(proxy_url)

                            if not event.is_set():
                                container.append(video_url)
                                event.set()
                            return

                except:
                    pass

                # Method 2: Look for video element inside player divs
                try:
                    video = driver.find_element(By.CSS_SELECTOR, "div.player-placeholder video")
                    src = video.get_attribute("src")

                    if src:
                        if not event.is_set():
                            container.append(src)
                            event.set()
                        return

                    # Try source tag inside video
                    source = video.find_element(By.TAG_NAME, "source")
                    src = source.get_attribute("src")
                    if src:
                        if not event.is_set():
                            container.append(src)
                            event.set()
                        return

                except:
                    pass

                # Method 3: Look for any video element on page
                try:
                    video = driver.find_element(By.TAG_NAME, "video")
                    src = video.get_attribute("src")

                    if src:
                        if not event.is_set():
                            container.append(src)
                            event.set()
                        return

                    # Try source tag
                    source = video.find_element(By.TAG_NAME, "source")
                    src = source.get_attribute("src")
                    if src:
                        if not event.is_set():
                            container.append(src)
                            event.set()
                        return

                except:
                    pass

                # Method 4: Look for iframes (video might be embedded)
                try:
                    iframes = driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        src = iframe.get_attribute("src")
                        if src and ("video" in src or "embed" in src):
                            if not event.is_set():
                                container.append(src)
                                event.set()
                            return
                except:
                    pass

                # Method 5: Extract from page source using regex patterns
                page_source = driver.page_source

                # Look for data-src attributes (proxy URLs with ?link= parameter)
                data_src_urls = re.findall(r'data-src="([^"]*)"', page_source)
                if data_src_urls:
                    # Extract real video URL from proxy URL
                    real_url = extract_real_video_url(data_src_urls[0])
                    if not event.is_set():
                        container.append(real_url)
                        event.set()
                    return

                # Look for video URLs in the HTML
                urls = re.findall(r"https?://[^\s\"'<>]+\.(?:mp4|m3u8|webm)", page_source)

                if urls:
                    # Try to verify the URL exists with HEAD request
                    for url_candidate in urls:
                        try:
                            response = head_with_retry(url_candidate, timeout=5)
                            if response.status_code == 200:
                                if not event.is_set():
                                    container.append(url_candidate)
                                    event.set()
                                return
                        except:
                            pass

                    # If HEAD request fails, use the first URL anyway
                    if not event.is_set():
                        container.append(urls[0])
                        event.set()
                        return

                # If nothing worked, raise an error
                raise Exception("Could not extract video URL from AnimePlyer")

        except Exception as e:
            if "Firefox" in str(e):
                raise Exception("Firefox not installed or browser pool failed.")
            else:
                raise


def load(languages_dict) -> None:
    """Load AnimePlyer scraper if language is supported."""
    can_load = False
    for language in AnimePlyer.languages:
        if language in languages_dict:
            can_load = True
            break

    if can_load:
        rep.register(AnimePlyer())
