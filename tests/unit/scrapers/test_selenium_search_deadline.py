"""Selenium operations cooperate with the active source-search deadline."""

from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import TimeoutException

from scrapers.core import search_deadline, selenium_driver
from scrapers.core.search_deadline import SearchDeadlineExceeded, use_search_deadline
from scrapers.core.selenium_driver import SeleniumWebDriver


def test_fetch_bounds_page_load_and_element_waits(monkeypatch):
    with patch("scrapers.core.selenium_driver.webdriver.Chrome") as chrome_cls:
        handle = MagicMock()
        handle.page_source = "<html><body>ready</body></html>"
        chrome_cls.return_value = handle
        driver = SeleniumWebDriver(timeout=20)

    monkeypatch.setattr(search_deadline, "monotonic", lambda: 10.0)
    monkeypatch.setattr(search_deadline, "sleep", lambda _delay: None)
    monkeypatch.setattr(selenium_driver.random, "uniform", lambda *_args: 0.1)
    wait = MagicMock()
    wait.until.return_value = True
    wait_factory = MagicMock(return_value=wait)
    monkeypatch.setattr(selenium_driver, "WebDriverWait", wait_factory)

    with use_search_deadline(12.0):
        page = driver.fetch("https://example.test", wait_selector="body")

    assert page.body is not None
    assert handle.set_page_load_timeout.call_args_list[-1].args == (2.0,)
    wait_factory.assert_called_once_with(handle, 2.0, poll_frequency=0.1)
    wait.until.assert_called_once()


def test_fetch_json_bounds_script_timeout(monkeypatch):
    with patch("scrapers.core.selenium_driver.webdriver.Chrome") as chrome_cls:
        handle = MagicMock()
        handle.execute_async_script.return_value = {"status": 200, "text": '{"ok":true}'}
        chrome_cls.return_value = handle
        driver = SeleniumWebDriver(timeout=20)

    monkeypatch.setattr(search_deadline, "monotonic", lambda: 10.0)
    monkeypatch.setattr(search_deadline, "sleep", lambda _delay: None)

    with use_search_deadline(13.0):
        result = driver.fetch_json("https://example.test/api")

    assert result == {"ok": True}
    handle.set_script_timeout.assert_called_once_with(3.0)


def test_expired_page_load_deadline_still_closes_driver(monkeypatch):
    with patch("scrapers.core.selenium_driver.webdriver.Chrome") as chrome_cls:
        handle = MagicMock()
        handle.get.side_effect = TimeoutException("page load timed out")
        chrome_cls.return_value = handle

        deadline_times = iter([10.0, 10.2])
        monkeypatch.setattr(search_deadline, "monotonic", lambda: next(deadline_times))

        with SeleniumWebDriver(timeout=20) as driver:
            with use_search_deadline(10.1), pytest.raises(SearchDeadlineExceeded):
                driver.fetch("https://example.test")

    handle.quit.assert_called_once()


def test_cloudflare_wait_stops_at_search_deadline_and_closes_driver(monkeypatch):
    with patch("scrapers.core.selenium_driver.webdriver.Chrome") as chrome_cls:
        handle = MagicMock()
        handle.title = "Just a moment..."
        handle.page_source = "cf-turnstile"
        chrome_cls.return_value = handle

        deadline_times = iter([10.0, 10.2])
        monkeypatch.setattr(search_deadline, "monotonic", lambda: next(deadline_times))
        monkeypatch.setattr(search_deadline, "sleep", lambda _delay: None)
        with SeleniumWebDriver() as driver:
            with use_search_deadline(10.1), pytest.raises(SearchDeadlineExceeded):
                driver._wait_for_cloudflare_challenge()

    handle.quit.assert_called_once()
