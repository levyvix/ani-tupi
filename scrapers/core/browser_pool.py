"""Browser pool for Firefox instances.

Single-instance pool optimized for CLI usage:
- Maintains 1 Firefox instance for all operations
- Reused across all scrapers to minimize memory usage
- Automatic health checking and recovery if browser crashes
- Thread-safe access with timeout queuing
- Automatic cleanup of old/unhealthy instances
"""

import queue
import threading
import time
from contextlib import contextmanager
from typing import Any

from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver

from scrapers.plugins.utils import is_firefox_installed_as_snap

# Semaphore to prevent creating too many browsers at once
_creation_lock = threading.Semaphore(1)


class BrowserContext:
    """Context manager for browser instances.

    Ensures proper cleanup and return of browsers to the pool.
    """

    def __init__(self, browser_pool, browser, browser_id):
        self.browser_pool = browser_pool
        self.browser = browser
        self.browser_id = browser_id
        self._checked_out = True

    def __enter__(self) -> WebDriver:
        return self  # Type hint that this behaves like WebDriver

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to underlying browser."""
        return getattr(self.browser, name)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._checked_out = False

        # If there was an exception, mark browser as unhealthy
        if exc_type is not None:
            self.browser_pool._mark_unhealthy(self.browser_id)

        # Return browser to pool
        self.browser_pool._return_browser(self.browser_id, self.browser)


class BrowserPool:
    """Single Firefox instance pool for all operations.

    Maintains 1 reusable Firefox instance across the entire application.
    This minimizes memory usage and startup overhead. Browser is only
    recreated if it becomes unhealthy or crashes.

    For CLI usage patterns where operations are sequential, this single-instance
    approach is optimal: no browser spawn spam, minimal memory footprint.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, max_size: int = 1):
        """Singleton pattern with configurable pool size."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_size: int = 1):
        """Initialize browser pool with specified size.

        Args:
            max_size: Maximum number of browser instances in pool
        """
        if hasattr(self, "_initialized"):
            return

        self._max_size = max_size
        self._pool = queue.Queue(maxsize=max_size)
        self._browsers = {}  # browser_id -> (browser, last_used, healthy)
        self._next_id = 0
        self._lock = threading.Lock()
        self._initialized = True

        # Pre-populate pool with a few instances
        self._populate_pool()

    def _create_browser(self):
        """Create a new optimized Firefox instance.

        Returns:
            tuple: (webdriver.Firefox, browser_id)
        """
        # Prevent creating browsers beyond max_size
        with self._lock:
            if len(self._browsers) >= self._max_size:
                raise RuntimeError(f"Browser pool at max capacity ({self._max_size})")

        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")

        try:
            if is_firefox_installed_as_snap():
                service = webdriver.FirefoxService(executable_path="/snap/bin/geckodriver")
                driver = webdriver.Firefox(options=options, service=service)
            else:
                driver = webdriver.Firefox(options=options)
        except Exception as e:
            raise RuntimeError(f"Failed to create Firefox instance: {e}")

        # Set implicit wait
        driver.implicitly_wait(2)

        with self._lock:
            browser_id = self._next_id
            self._next_id += 1
            self._browsers[browser_id] = (driver, time.time(), True)

        return driver, browser_id

    def _populate_pool(self):
        """Pre-populate pool with browser instances."""
        # Start with 1 instance (or up to max_size)
        initial_count = min(1, self._max_size)

        for _ in range(initial_count):
            try:
                browser, browser_id = self._create_browser()
                self._pool.put((browser_id, browser))
            except Exception:
                # If we can't create initial instance, that's ok
                # We'll create it on-demand
                pass

    def _mark_unhealthy(self, browser_id: int):
        """Mark a browser instance as unhealthy for cleanup.

        Args:
            browser_id: ID of browser to mark as unhealthy
        """
        with self._lock:
            if browser_id in self._browsers:
                browser, last_used, _ = self._browsers[browser_id]
                self._browsers[browser_id] = (browser, last_used, False)

    def _return_browser(self, browser_id: int, browser):
        """Return browser to pool after use.

        Args:
            browser_id: ID of browser being returned
            browser: The browser instance
        """
        with self._lock:
            if browser_id in self._browsers:
                _, _, healthy = self._browsers[browser_id]
                self._browsers[browser_id] = (browser, time.time(), healthy)

        try:
            self._pool.put((browser_id, browser), timeout=5)
        except queue.Full:
            # Pool is full, close this browser
            try:
                browser.quit()
            except Exception:
                pass
            with self._lock:
                self._browsers.pop(browser_id, None)

    def _cleanup_old_browsers(self):
        """Clean up old or unhealthy browser instances."""
        current_time = time.time()
        max_age = 300  # 5 minutes

        with self._lock:
            to_remove = []
            for browser_id, (browser, last_used, healthy) in self._browsers.items():
                if not healthy or (current_time - last_used) > max_age:
                    to_remove.append((browser_id, browser))

            for browser_id, browser in to_remove:
                try:
                    browser.quit()
                except Exception:
                    pass
                self._browsers.pop(browser_id, None)

    @contextmanager
    def get_browser(self):
        """Get a browser instance from the pool.

        Returns:
            Context manager that yields a Firefox webdriver instance

        Example:
            with browser_pool.get_browser() as driver:
                driver.get(url)
                # ... use driver
            # Browser automatically returned to pool
        """
        # Cleanup old/unhealthy browsers periodically
        self._cleanup_old_browsers()

        browser = None
        browser_id = None

        # Try to get existing browser from pool (with timeout)
        try:
            browser_id, browser = self._pool.get(timeout=3)
        except queue.Empty:
            # No browser available, create one
            with _creation_lock:
                # Double-check within lock
                try:
                    browser_id, browser = self._pool.get_nowait()
                except queue.Empty:
                    browser, browser_id = self._create_browser()

        # Health check on retrieved browser
        try:
            browser.current_url  # Quick check if browser is responsive
        except Exception:
            # Browser is unhealthy, kill it and create a new one
            try:
                browser.quit()
            except Exception:
                pass
            with self._lock:
                self._browsers.pop(browser_id, None)

            with _creation_lock:
                browser, browser_id = self._create_browser()

        yield BrowserContext(self, browser, browser_id)

    def close_all(self):
        """Close all browser instances and cleanup pool."""
        with self._lock:
            for browser_id, (browser, _, _) in list(self._browsers.items()):
                try:
                    browser.quit()
                except Exception:
                    pass

            self._browsers.clear()

        # Clear the queue
        while not self._pool.empty():
            try:
                self._pool.get_nowait()
            except queue.Empty:
                break

    def __del__(self):
        """Cleanup on object destruction."""
        self.close_all()


# Global instance for easy import - lazy initialization to avoid startup delay
browser_pool = None


def get_browser_pool():
    """Get the global browser pool instance, creating it lazily."""
    global browser_pool
    if browser_pool is None:
        browser_pool = BrowserPool()
    return browser_pool
