"""SearchRepository deadlines preserve fast results and discard late sources."""

from threading import Event
from types import SimpleNamespace
from time import monotonic

from models.models import AnimeMetadata
from services.repository import search_repository
from services.repository.search_repository import SearchRepository


class _Source:
    def __init__(self, name, search):
        self.name = name
        self._search = search

    def search_anime(self, query):
        return self._search(query)


def test_search_returns_partial_results_and_discards_late_source(monkeypatch):
    SearchRepository.reset_singleton()
    repo = SearchRepository()
    started = Event()
    release = Event()
    finished = Event()
    cached_snapshots = []

    def slow_search(_query):
        started.set()
        try:
            release.wait(timeout=2)
            return [
                AnimeMetadata(title="Late anime", url="https://late.example/anime", source="slow")
            ]
        finally:
            finished.set()

    def fast_search(_query):
        return [AnimeMetadata(title="Fast anime", url="https://fast.example/anime", source="fast")]

    repo.register(_Source("slow", slow_search))
    repo.register(_Source("fast", fast_search))
    monkeypatch.setattr(
        search_repository,
        "settings",
        SimpleNamespace(
            performance=SimpleNamespace(http_timeout=0.02),
            plugins=SimpleNamespace(priority_order=["fast", "slow"]),
            search=SimpleNamespace(progressive_search_min_words=1),
            cache=SimpleNamespace(search_cache_ttl_seconds=60),
        ),
    )
    monkeypatch.setattr(repo, "_try_cache", lambda _query, _verbose: (None, 0))
    monkeypatch.setattr(
        repo,
        "_save_cache",
        lambda _query, _verbose, state: cached_snapshots.append(dict(state.anime_to_urls)),
    )

    try:
        start = monotonic()
        results = repo.search_anime("deadline-check", verbose=False)
        duration = monotonic() - start

        assert started.is_set()
        assert duration < 0.5
        assert [result.title for result in results.results] == ["Fast anime"]
        assert repo.get_search_metadata().timed_out_sources == ["slow"]
        assert len(cached_snapshots) == 1
        assert "Late anime" not in cached_snapshots[0]

        release.set()
        assert finished.wait(timeout=1)

        assert repo.get_anime_titles() == ["Fast anime"]
        assert "Late anime" not in repo.anime_to_urls
    finally:
        release.set()
        SearchRepository.reset_singleton()


def test_completed_source_results_keep_configured_priority_order(monkeypatch):
    SearchRepository.reset_singleton()
    repo = SearchRepository()
    repo.register(
        _Source(
            "lower-priority",
            lambda _query: [
                AnimeMetadata(
                    title="Same anime",
                    url="https://lower.example/anime",
                    source="lower-priority",
                )
            ],
        )
    )
    repo.register(
        _Source(
            "higher-priority",
            lambda _query: [
                AnimeMetadata(
                    title="Same anime",
                    url="https://higher.example/anime",
                    source="higher-priority",
                )
            ],
        )
    )
    monkeypatch.setattr(
        search_repository,
        "settings",
        SimpleNamespace(
            performance=SimpleNamespace(http_timeout=1),
            plugins=SimpleNamespace(priority_order=["higher-priority", "lower-priority"]),
            search=SimpleNamespace(progressive_search_min_words=1),
            cache=SimpleNamespace(search_cache_ttl_seconds=60),
        ),
    )
    monkeypatch.setattr(repo, "_try_cache", lambda _query, _verbose: (None, 0))
    monkeypatch.setattr(repo, "_save_cache", lambda _query, _verbose, _state=None: None)

    try:
        repo.search_anime("priority-check", verbose=False)

        title = next(iter(repo.anime_to_urls))
        source_order = [source for _url, source, _params in repo.anime_to_urls[title]]
        assert source_order == ["higher-priority", "lower-priority"]
        assert repo.get_search_metadata().timed_out_sources == []
    finally:
        SearchRepository.reset_singleton()
