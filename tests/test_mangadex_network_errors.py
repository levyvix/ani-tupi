"""Tests that the MangaDex plugin distinguishes network errors from empty results.

A network/HTTP failure must be logged at WARNING level (so it is visible in
logs) while still returning ``[]`` to preserve the existing return contract.
Only the external HTTP client (``httpx``) is mocked.

The project uses loguru (not stdlib logging), so a temporary loguru sink is
installed to capture emitted records instead of pytest's ``caplog``.
"""

import httpx
import pytest

from manga_scrapers.plugins.mangadex import MangaDex
from utils.logging import _base_logger


@pytest.fixture
def scraper():
    return MangaDex()


@pytest.fixture
def warnings():
    """Capture loguru WARNING+ records emitted during the test."""
    captured: list[str] = []
    sink_id = _base_logger.add(
        lambda message: captured.append(message.record["message"]),
        level="WARNING",
    )
    yield captured
    _base_logger.remove(sink_id)


def test_search_manga_logs_warning_on_timeout(scraper, monkeypatch, warnings):
    def _raise(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", _raise)

    result = scraper.search_manga("naruto")

    assert result == []
    assert any("naruto" in msg for msg in warnings)


def test_search_manga_logs_warning_on_connect_error(scraper, monkeypatch, warnings):
    def _raise(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", _raise)

    result = scraper.search_manga("bleach")

    assert result == []
    assert len(warnings) == 1


def test_get_chapters_logs_warning_on_timeout(scraper, monkeypatch, warnings):
    def _raise(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", _raise)

    result = scraper.get_chapters("manga-id", "https://mangadex.org/title/manga-id")

    assert result == []
    assert len(warnings) == 1


def test_get_chapter_pages_logs_warning_on_timeout(scraper, monkeypatch, warnings):
    def _raise(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", _raise)

    result = scraper.get_chapter_pages("chapter-id", "https://mangadex.org/chapter/chapter-id")

    assert result == []
    assert len(warnings) == 1
