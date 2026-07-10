"""Integration tests for manga multi-source search/dedup and source selection.

- Search+dedup uses a real ``UnifiedMangaService`` with fake in-memory plugins
  (plugins are the external boundary — the scrapers).
- Source-selection logic (``research_manga_in_new_source``,
  ``resume_from_other_source``) uses a fake service standing in for the
  external network.
"""

from types import SimpleNamespace


from models.config import MangaSettings
from models.models import MangaMetadata, MangaStatus
from services.manga_service import UnifiedMangaService
from services.manga.reading_flow import find_chapter_by_number
from services.manga.source_selection import (
    research_manga_in_new_source,
    resume_from_other_source,
)


class _FakePlugin:
    """Minimal manga scraper plugin: returns preconfigured search results."""

    def __init__(self, results):
        self._results = results

    def search_manga(self, query):
        return self._results

    def get_chapters(self, manga_id, manga_url):
        return []

    def get_chapter_pages(self, chapter_id, chapter_url):
        return []


def _make_service(plugins: dict, tmp_path, monkeypatch) -> UnifiedMangaService:
    """Build a UnifiedMangaService with injected fake plugins."""
    monkeypatch.setattr("services.manga_service.load_manga_plugins", lambda: plugins)
    # Redirect metadata persistence into tmp.
    svc = UnifiedMangaService(MangaSettings(output_directory=tmp_path))
    svc.metadata_file = tmp_path / "meta.json"
    svc.manga_plugin_map.clear()
    return svc


class TestSearchDedup:
    def test_same_title_different_separators_merged(self, tmp_path, monkeypatch):
        plugins = {
            "srcA": _FakePlugin(
                [{"id": "a1", "title": "Anime A: Revolucao Dublado", "status": "ongoing"}]
            ),
            "srcB": _FakePlugin(
                [{"id": "b1", "title": "Anime A - Revolucao Dublado", "status": "ongoing"}]
            ),
        }
        svc = _make_service(plugins, tmp_path, monkeypatch)
        results = svc.search_manga("anime a")
        # Both variants collapse into a single entry with both sources.
        assert len(results) == 1
        assert set(results[0].sources) == {"srcA", "srcB"}

    def test_distinct_titles_not_merged(self, tmp_path, monkeypatch):
        plugins = {
            "srcA": _FakePlugin([{"id": "a1", "title": "Naruto", "status": "ongoing"}]),
            "srcB": _FakePlugin([{"id": "b1", "title": "Bleach", "status": "ongoing"}]),
        }
        svc = _make_service(plugins, tmp_path, monkeypatch)
        results = svc.search_manga("x")
        titles = sorted(r.title for r in results)
        assert titles == ["Bleach", "Naruto"]

    def test_primary_source_wins_for_id(self, tmp_path, monkeypatch):
        # Primary (current_source) is searched first, so its id becomes the base.
        plugins = {
            "mangadex": _FakePlugin(
                [{"id": "primary-id", "title": "Chainsaw Man", "status": "ongoing"}]
            ),
            "srcB": _FakePlugin([{"id": "other-id", "title": "Chainsaw Man", "status": "ongoing"}]),
        }
        svc = _make_service(plugins, tmp_path, monkeypatch)
        svc.current_source = "mangadex"
        results = svc.search_manga("chainsaw")
        assert len(results) == 1
        assert results[0].id == "primary-id"
        assert results[0].sources["mangadex"] == "primary-id"
        assert results[0].sources["srcB"] == "other-id"


def _manga(title="Test", mid="m1", sources=None):
    return MangaMetadata(id=mid, title=title, status=MangaStatus.ONGOING, sources=sources or {})


class _FakeService:
    """Stands in for UnifiedMangaService for source-switch logic tests."""

    def __init__(self, chapters_by_source=None, search_by_source=None):
        self._chapters = chapters_by_source or {}
        self._search = search_by_source or {}
        self.current_source = "mangadex"
        self.set_source_calls = []

    def get_chapters(self, manga_id, manga_url=None, source=None):
        return self._chapters.get(source, [])

    def search_manga(self, title, source=None):
        return self._search.get(source, [])

    def set_source(self, source):
        self.set_source_calls.append(source)
        self.current_source = source
        return True


def _noop_progress(msg=""):
    from contextlib import contextmanager

    @contextmanager
    def cm():
        yield

    return cm()


class TestResearchMangaInNewSource:
    def test_uses_known_source_id_without_research(self):
        manga = _manga(sources={"mugiwaras": "mug-id"})
        svc = _FakeService()
        updated = research_manga_in_new_source(svc, manga, "mugiwaras", progress=_noop_progress)
        assert updated.id == "mug-id"

    def test_researches_and_updates_on_exact_title(self):
        manga = _manga(title="Chainsaw Man", mid="old")
        found = _manga(title="Chainsaw Man", mid="new-id")
        svc = _FakeService(search_by_source={"srcB": [found]})
        updated = research_manga_in_new_source(svc, manga, "srcB", progress=_noop_progress)
        assert updated.id == "new-id"

    def test_does_not_mutate_input_manga(self):
        # Immutable data flow: the passed-in manga must be left untouched; the
        # updated copy is returned instead.
        manga = _manga(title="Chainsaw Man", mid="old", sources={})
        found = _manga(title="Chainsaw Man Renewed", mid="new-id")
        svc = _FakeService(search_by_source={"srcB": [found]})

        updated = research_manga_in_new_source(svc, manga, "srcB", progress=_noop_progress)

        # Original unchanged.
        assert manga.id == "old"
        assert manga.title == "Chainsaw Man"
        # Returned copy carries the new source's metadata.
        assert updated is not manga
        assert updated.id == "new-id"
        assert updated.title == "Chainsaw Man Renewed"


class TestResumeFromOtherSource:
    def test_finds_chapter_in_other_source(self):
        ch = SimpleNamespace(number="5", url="http://x", id="c5")
        manga = _manga(sources={"mangadex": "md", "mugiwaras": "mug"})
        svc = _FakeService(chapters_by_source={"mugiwaras": [ch]})
        result = resume_from_other_source(
            svc, manga, chapter_num=5, current_source="mangadex", progress=_noop_progress
        )
        assert result is not None
        src, _url, chapters, chapter, updated = result
        assert src == "mugiwaras"
        assert chapter.number == "5"
        # Input untouched; new id conveyed via the returned copy.
        assert manga.id == "m1"
        assert updated is not manga
        assert updated.id == "mug"
        assert "mugiwaras" in svc.set_source_calls

    def test_does_not_mutate_input_manga(self):
        ch = SimpleNamespace(number="5", url="http://x", id="c5")
        manga = _manga(mid="orig", sources={"mangadex": "md", "mugiwaras": "mug"})
        svc = _FakeService(chapters_by_source={"mugiwaras": [ch]})

        result = resume_from_other_source(
            svc, manga, chapter_num=5, current_source="mangadex", progress=_noop_progress
        )

        assert result is not None
        *_rest, updated = result
        assert manga.id == "orig"
        assert updated is not manga
        assert updated.id == "mug"

    def test_returns_none_when_no_other_source_has_it(self):
        manga = _manga(sources={"mangadex": "md", "mugiwaras": "mug"})
        svc = _FakeService(chapters_by_source={"mugiwaras": []})
        result = resume_from_other_source(
            svc, manga, chapter_num=5, current_source="mangadex", progress=_noop_progress
        )
        assert result is None

    def test_skips_chapter_without_url(self):
        ch = SimpleNamespace(number="5", url=None, id="c5")
        manga = _manga(sources={"mangadex": "md", "mugiwaras": "mug"})
        svc = _FakeService(chapters_by_source={"mugiwaras": [ch]})
        result = resume_from_other_source(
            svc, manga, chapter_num=5, current_source="mangadex", progress=_noop_progress
        )
        assert result is None


def test_find_chapter_by_number_with_namespace_chapters():
    chapters = [SimpleNamespace(number="1"), SimpleNamespace(number="2")]
    assert find_chapter_by_number(chapters, 2).number == "2"
