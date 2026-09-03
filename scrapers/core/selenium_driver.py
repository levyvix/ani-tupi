"""Selenium WebDriver wrapper for dynamic web scraping.

Provides unified interface for dynamic JavaScript-rendered content scraping
with stealth mode, user-agent rotation, and BeautifulSoup parsing.
"""

import random
import time
import weakref

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
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


def _quit_driver(driver) -> None:
    """Quit a WebDriver handle, swallowing any teardown errors.

    Kept at module level so ``weakref.finalize`` can hold a reference to the
    driver handle without keeping the owning ``SeleniumWebDriver`` alive.
    """
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


class SeleniumWebDriver:
    """Selenium WebDriver wrapper with stealth and parsing capabilities.

    Handles browser lifecycle, page rendering, user-agent rotation,
    and BeautifulSoup integration for CSS selector-based parsing.
    """

    def __init__(self, headless: bool = True, timeout: int = 20, user_agent: str | None = None):
        """Initialize Selenium WebDriver with Chrome options.

        Args:
            headless: Run browser in headless mode (default: True)
            timeout: Page load timeout in seconds (default: 20)
            user_agent: Fixed user-agent to use instead of random rotation.
                Required when the extracted media URL is bound to the UA that
                will later play it (e.g. anroll/anidrive googlevideo links).
        """
        self.timeout = timeout
        self.driver = None
        self._finalizer = None
        self._init_driver(headless, user_agent)
        # Deterministic cleanup: runs on GC and at interpreter exit, and is
        # idempotent. Does not hold a strong reference to ``self``.
        self._finalizer = weakref.finalize(self, _quit_driver, self.driver)

    def _init_driver(self, headless: bool, user_agent: str | None = None) -> None:
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
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Performance
        options.add_argument("--disable-images")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-java")
        options.add_argument("--disable-popup-blocking")

        # User agent: fixed when provided, otherwise rotate
        user_agent = user_agent or random.choice(USER_AGENTS)
        options.add_argument(f"user-agent={user_agent}")

        # Initialize driver (Selenium Manager auto-downloads chromedriver)
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(self.timeout)

        # Stealth: hide webdriver flag and set user agent via CDP
        self.driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": user_agent})
        try:
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
            )
        except Exception:
            pass

    def fetch(
        self, url: str, wait_selector: str | None = None, max_retries: int = 2
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

                # Wait for Cloudflare challenge to clear if present (up to 15s)
                self._wait_for_cloudflare_challenge()

                # Wait for specific element if provided
                if wait_selector:
                    try:
                        WebDriverWait(self.driver, self.timeout).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                        )
                    except WebDriverException as e:
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

    def _wait_for_cloudflare_challenge(self, max_wait: float = 15.0) -> None:
        """Wait for Cloudflare challenge to clear, if present.

        Cloudflare renders a 'Just a moment...' page with Turnstile widget.
        This polls the page title and DOM for challenge indicators.
        """
        end = time.time() + max_wait
        while time.time() < end:
            try:
                title = (self.driver.title or "").lower()
                html = (self.driver.page_source or "").lower()
                # Detect challenge page
                if "just a moment" in title or "cf-challenge" in html or "cf-turnstile" in html:
                    time.sleep(1.0)
                    continue
                # Also detect cf-mitigated overlay - wait for it to disappear
                if "checking if the site connection is secure" in html:
                    time.sleep(1.0)
                    continue
                break
            except Exception:
                break

    def fetch_json(self, url: str, referer: str | None = None) -> dict | None:
        """Fetch JSON via browser fetch API (uses Cloudflare clearance cookies).

        Useful for API endpoints protected by Cloudflare (e.g. dooplayer).
        Returns parsed JSON dict or None on failure.
        """
        import json as _json

        if referer:
            try:
                self.driver.get(referer)
                time.sleep(random.uniform(0.5, 1.0))
                self._wait_for_cloudflare_challenge()
            except Exception:
                pass

        # Use browser's fetch with credentials to reuse cf_clearance cookies
        script = """
            var url = arguments[0];
            var callback = arguments[arguments.length - 1];
            fetch(url, {credentials: 'include', headers: {'Accept': 'application/json'}})
                .then(function(r){ return r.text().then(function(t){ return {status: r.status, text: t}; }); })
                .then(function(o){ callback(o); })
                .catch(function(e){ callback({status: 0, text: '', error: e.toString()}); });
        """
        try:
            self.driver.set_script_timeout(self.timeout)
            result = self.driver.execute_async_script(script, url)
            if not result or result.get("status") != 200:
                return None
            return _json.loads(result.get("text", ""))
        except Exception:
            return None

    def close(self) -> None:
        """Close browser and cleanup resources.

        Idempotent: running the finalizer also detaches it, so a later GC or
        interpreter-exit pass will not attempt a second ``quit()``.
        """
        if self._finalizer is not None:
            # Runs _quit_driver(self.driver) exactly once and detaches itself.
            self._finalizer()
        self.driver = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        """Context manager exit with cleanup."""
        self.close()
