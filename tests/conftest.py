"""Pytest configuration and fixtures for ani-tupi tests.

This module provides real service instances for integration testing,
avoiding excessive mocks in favor of testing actual behavior.
"""

import tempfile
from pathlib import Path

import pytest

from services.repository import Repository


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for test storage.

    Automatically cleaned up after test completes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings(temp_dir, monkeypatch):
    """Provide real AppSettings configured for testing.

    Uses environment variables with test-specific paths.
    """
    # Use temporary directory for cache and storage
    monkeypatch.setenv("ANI_TUPI__CACHE__DIRECTORY", str(temp_dir / "cache"))
    monkeypatch.setenv("ANI_TUPI__ANIME__DOWNLOAD_DIRECTORY", str(temp_dir / "downloads"))
    monkeypatch.setenv("ANI_TUPI__LOG_LEVEL", "debug")

    # Return fresh settings instance
    from importlib import reload
    import models.config

    reload(models.config)
    return models.config.settings


@pytest.fixture
def repository(test_settings):
    """Provide a real Repository instance with real plugins loaded.

    This loads actual scraper plugins from scrapers/plugins/ directory.
    Cache is reset before each test to ensure isolation.
    """
    Repository.reset_singleton()
    repo = Repository()

    yield repo

    # Cleanup
    Repository.reset_singleton()


@pytest.fixture(autouse=True)
def reset_repository():
    """Auto-reset repository singleton before each test."""
    Repository.reset_singleton()
    yield
    Repository.reset_singleton()


@pytest.fixture
def anilist_http(monkeypatch):
    """Patch the AniList HTTP boundary with a fake transport.

    The client executes GraphQL via
    ``scrapers.plugins.utils.http_request_with_retry("POST", url, json=..., ...)``,
    so we patch that single external boundary; the real ``AniListClient`` and its
    operation mixins run against the enqueued responses. Enqueue payloads with
    the builders in ``tests.fixtures.anilist``::

        anilist_http.enqueue(graphql_response({"Viewer": viewer()}))
    """
    from tests.fixtures.anilist import FakeAniListTransport

    transport = FakeAniListTransport()
    monkeypatch.setattr("scrapers.plugins.utils.http_request_with_retry", transport)
    return transport


@pytest.fixture
def anilist_client(temp_dir, monkeypatch):
    """Provide an authenticated ``AniListClient`` backed by a temp token file.

    The token file lives under ``temp_dir`` so persistence uses ``tmp_path``
    semantics. Combine with ``anilist_http`` to drive GraphQL responses.
    """
    from services.anilist.client import AniListClient

    token_file = temp_dir / "anilist_token.json"
    monkeypatch.setattr("services.anilist.client.settings.anilist.token_file", token_file)
    monkeypatch.setattr(
        "services.anilist.client.settings.anilist.api_url",
        "https://graphql.anilist.co",
    )
    client = AniListClient()
    client.token = "test-token"
    client.user_id = 42
    return client


@pytest.fixture
def state_dir(temp_dir):
    """Provide a temp directory standing in for the app state dir.

    Services persist JSON under a module-global :class:`JSONStore`; tests can
    repoint those stores at this directory to exercise real persistence without
    touching the user's real state. Returns the path (auto-cleaned)."""
    state = temp_dir / "state"
    state.mkdir(parents=True, exist_ok=True)
    return state
