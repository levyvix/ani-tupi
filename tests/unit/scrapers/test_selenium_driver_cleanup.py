"""Tests for SeleniumWebDriver deterministic resource cleanup (H8).

Verifies the weakref.finalize-based teardown: no real Chrome is launched
(webdriver.Chrome is patched to a MagicMock), and cleanup runs exactly once
regardless of how many times close() is called or whether the finalizer also
fires.
"""

from unittest.mock import MagicMock, patch

from scrapers.core.selenium_driver import SeleniumWebDriver


def _make_driver():
    """Build a SeleniumWebDriver whose underlying handle is a MagicMock."""
    with patch("scrapers.core.selenium_driver.webdriver.Chrome") as chrome_cls:
        instance = MagicMock()
        chrome_cls.return_value = instance
        driver = SeleniumWebDriver()
    return driver, instance


def test_close_is_idempotent():
    """Calling close() twice does not error and only quits once."""
    driver, handle = _make_driver()

    driver.close()
    driver.close()

    handle.quit.assert_called_once()
    assert driver.driver is None


def test_finalizer_does_not_double_quit_after_close():
    """After close(), the finalizer is detached so it won't quit again."""
    driver, handle = _make_driver()

    driver.close()
    assert handle.quit.call_count == 1

    # Explicitly running the finalizer (as GC / interpreter exit would) must
    # be a no-op because close() already ran and detached it.
    driver._finalizer()

    handle.quit.assert_called_once()


def test_finalizer_quits_when_close_not_called():
    """If close() is never called, the finalizer still quits exactly once."""
    driver, handle = _make_driver()

    # Simulate GC / interpreter exit invoking the finalizer.
    driver._finalizer()

    handle.quit.assert_called_once()


def test_context_manager_quits_on_exit():
    """Using the driver as a context manager quits the handle on exit."""
    with patch("scrapers.core.selenium_driver.webdriver.Chrome") as chrome_cls:
        handle = MagicMock()
        chrome_cls.return_value = handle
        with SeleniumWebDriver() as driver:
            assert driver.driver is handle

    handle.quit.assert_called_once()
