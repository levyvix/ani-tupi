"""Exercise repository search through the shared HTTP and Selenium deadlines."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from bs4 import BeautifulSoup

from models.models import AnimeMetadata
from scrapers.core import search_deadline
from scrapers.core.selenium_driver import SeleniumWebDriver
from scrapers.plugins.utils import http_get_with_retry
from services.repository import search_repository
from services.repository.search_repository import SearchRepository


class _HttpSearchSource:
    name = "http-source"

    def search_anime(self, query):
        response = http_get_with_retry("https://http.example/search", timeout=5)
        title = BeautifulSoup(response.text, "html.parser").select_one("h1").get_text(strip=True)
        return [
            AnimeMetadata(
                title=f"{title} {query}", url="https://http.example/anime", source=self.name
            )
        ]


class _SeleniumSearchSource:
    name = "selenium-source"

    def search_anime(self, query):
        with SeleniumWebDriver() as driver:
            page = driver.fetch("https://selenium.example/search")
        title = page.select_one("h1").get_text(strip=True)
        return [
            AnimeMetadata(
                title=f"{title} {query}",
                url="https://selenium.example/anime",
                source=self.name,
            )
        ]


def test_search_repository_uses_deadline_aware_http_and_selenium(monkeypatch):
    SearchRepository.reset_singleton()
    repo = SearchRepository()
    repo.register(_HttpSearchSource())
    repo.register(_SeleniumSearchSource())

    monkeypatch.setattr(
        search_repository,
        "settings",
        SimpleNamespace(
            performance=SimpleNamespace(http_timeout=1),
            plugins=SimpleNamespace(priority_order=["selenium-source", "http-source"]),
            search=SimpleNamespace(progressive_search_min_words=1),
            cache=SimpleNamespace(search_cache_ttl_seconds=60),
        ),
    )
    monkeypatch.setattr(repo, "_try_cache", lambda _query, _verbose: (None, 0))
    monkeypatch.setattr(repo, "_save_cache", lambda _query, _verbose, _state=None: None)
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "https://http.example/search"),
        text="<h1>HTTP show</h1>",
    )
    monkeypatch.setattr("scrapers.plugins.utils.httpx.request", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(search_deadline, "sleep", lambda _delay: None)
    monkeypatch.setattr(search_deadline, "monotonic", lambda: 10.0)

    with patch("scrapers.core.selenium_driver.webdriver.Chrome") as chrome_cls:
        browser = MagicMock()
        browser.page_source = "<h1>Selenium show</h1>"
        chrome_cls.return_value = browser

        try:
            results = repo.search_anime("deadline integration", verbose=False)

            assert {item.title for item in results.results} == {
                "HTTP show deadline integration",
                "Selenium show deadline integration",
            }
            assert repo.get_search_metadata().timed_out_sources == []
            assert browser.quit.call_count == 1
        finally:
            SearchRepository.reset_singleton()
