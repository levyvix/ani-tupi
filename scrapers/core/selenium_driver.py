"""Selenium WebDriver wrapper for dynamic web scraping.

Provides unified interface for dynamic JavaScript-rendered content scraping
with stealth mode, user-agent rotation, and BeautifulSoup parsing.
"""

import random
import time
from typing import Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


USER_AGENTS = [
    # Desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Mobile
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
]

COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class SeleniumWebDriver:
    """Selenium WebDriver wrapper with stealth and parsing capabilities.

    Handles browser lifecycle, page rendering, user-agent rotation,
    and BeautifulSoup integration for CSS selector-based parsing.
    """

    def __init__(self, headless: bool = True, timeout: int = 20):
        """Initialize Selenium WebDriver with Chrome options.

        Args:
            headless: Run browser in headless mode (default: True)
            timeout: Page load timeout in seconds (default: 20)
        """
        self.timeout = timeout
        self.driver = None
        self._init_driver(headless)

    def _init_driver(self, headless: bool) -> None:
        """Initialize Chrome WebDriver with stealth options."""
        options = Options()

        # Headless mode
        if headless:
            options.add_argument("--headless=new")

        # Stealth options to evade detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")

        # Performance
        options.add_argument("--disable-images")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-java")
        options.add_argument("--disable-popup-blocking")

        # User agent rotation
        user_agent = random.choice(USER_AGENTS)
        options.add_argument(f"user-agent={user_agent}")

        # Initialize driver (Selenium Manager auto-downloads chromedriver)
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(self.timeout)

        # Add request headers via CDP (Chrome DevTools Protocol)
        self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": user_agent})

    def fetch(
        self, url: str, wait_selector: Optional[str] = None, max_retries: int = 2
    ) -> BeautifulSoup:
        """Fetch URL and return parsed HTML with retry on timeout.

        Args:
            url: Target URL to fetch
            wait_selector: Optional CSS selector to wait for before returning
            max_retries: Number of retry attempts on timeout (default: 2)

        Returns:
            BeautifulSoup: Parsed HTML document

        Raises:
            Exception: If page load fails after all retries or element wait fails
        """
        from selenium.common.exceptions import TimeoutException

        for attempt in range(max_retries + 1):
            try:
                self.driver.get(url)

                # Add small random delay to mimic human browsing
                time.sleep(random.uniform(0.5, 1.5))

                # Wait for specific element if provided
                if wait_selector:
                    try:
                        WebDriverWait(self.driver, self.timeout).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                        )
                    except Exception as e:
                        raise Exception(f"Failed to find element '{wait_selector}': {e}")

                # Get rendered HTML and parse
                html = self.driver.page_source
                return BeautifulSoup(html, "html.parser")

            except TimeoutException as e:
                if attempt < max_retries:
                    wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(
                        f"Timeout after {max_retries + 1} attempts on {url}: {e}"
                    ) from e

    def fetch_json(self, url: str) -> dict:
        """Fetch URL and parse as JSON.

        Args:
            url: Target URL returning JSON

        Returns:
            dict: Parsed JSON response

        Raises:
            Exception: If page load or JSON parsing fails
        """
        import json

        try:
            self.driver.get(url)
        except Exception as e:
            raise Exception(f"Failed to load URL '{url}': {e}") from e
        time.sleep(random.uniform(0.5, 1.5))

        try:
            # Get page text and parse as JSON
            text = self.driver.find_element(By.TAG_NAME, "body").text
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse JSON response: {e}")

    def close(self) -> None:
        """Close browser and cleanup resources."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

    def __del__(self):
        """Ensure cleanup on object destruction."""
        self.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.close()
