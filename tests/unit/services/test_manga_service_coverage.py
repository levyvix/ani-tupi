"""Coverage tests for services/manga_service.py.

Targets: MangaHistory, DownloadedChaptersTracker, UnifiedMangaService.
Strategy: real implementations; mock only load_manga_plugins (the external
plugin boundary) and never mock internal services.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plugin(name: str, search_results=None, chapter_results=None, page_results=None):
    """Create a fake manga plugin."""
    plugin = MagicMock()
    plugin.name = name
    plugin.search_manga.return_value = search_results or []
    plugin.get_chapters.return_value = chapter_results or []
    plugin.get_chapter_pages.return_value = page_results or []
    return plugin


def _manga_search_result(id_="m1", title="Test Manga", status="ongoing"):
    return {"id": id_, "title": title, "status": status}


def _chapter_result(id_="c1", number="1", url="http://x/ch/1"):
    return {"id": id_, "number": number, "url": url}


# ---------------------------------------------------------------------------
# MangaHistory
# ---------------------------------------------------------------------------


class TestMangaHistory:
    @pytest.fixture(autouse=True)
    def _redirect_history_file(self, tmp_path, monkeypatch):
        from services.manga.manga_service import MangaHistory

        monkeypatch.setattr(MangaHistory, "_history_file", tmp_path / "manga_history.json")

    def test_load_returns_empty_when_file_missing(self):
        from services.manga.manga_service import MangaHistory

        result = MangaHistory.load()
        assert result == {}

    def test_save_and_load_roundtrip(self):
        from services.manga.manga_service import MangaHistory
        from models.models import MangaHistoryEntry

        entry = MangaHistoryEntry(last_chapter="5")
        MangaHistory.save({"One Piece": entry})
        loaded = MangaHistory.load()
        assert "One Piece" in loaded
        assert loaded["One Piece"].last_chapter == "5"

    def test_load_returns_empty_on_corrupt_json(self, tmp_path, monkeypatch):
        from services.manga.manga_service import MangaHistory

        f = tmp_path / "manga_history.json"
        f.write_text("not valid json")
        monkeypatch.setattr(MangaHistory, "_history_file", f)
        assert MangaHistory.load() == {}

    def test_get_last_chapter_returns_none_when_missing(self):
        from services.manga.manga_service import MangaHistory

        assert MangaHistory.get_last_chapter("Naruto") is None

    def test_get_last_chapter_returns_chapter(self):
        from services.manga.manga_service import MangaHistory
        from models.models import MangaHistoryEntry

        MangaHistory.save({"Naruto": MangaHistoryEntry(last_chapter="42")})
        assert MangaHistory.get_last_chapter("Naruto") == "42"

    def test_update_creates_new_entry(self):
        from services.manga.manga_service import MangaHistory

        MangaHistory.update("Bleach", "100", chapter_id="cid", manga_id="mid", anilist_id=99)
        history = MangaHistory.load()
        assert history["Bleach"].last_chapter == "100"
        assert history["Bleach"].anilist_id == 99

    def test_update_preserves_anilist_id(self):
        from services.manga.manga_service import MangaHistory

        MangaHistory.update("Bleach", "1", anilist_id=55)
        MangaHistory.update("Bleach", "2")  # no anilist_id — should preserve
        history = MangaHistory.load()
        assert history["Bleach"].anilist_id == 55
        assert history["Bleach"].last_chapter == "2"

    def test_update_is_thread_safe(self):
        from services.manga.manga_service import MangaHistory

        errors = []

        def update_chapter(ch):
            try:
                MangaHistory.update("Manga", str(ch))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_chapter, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        history = MangaHistory.load()
        assert "Manga" in history


# ---------------------------------------------------------------------------
# DownloadedChaptersTracker
# ---------------------------------------------------------------------------


class TestDownloadedChaptersTracker:
    @pytest.fixture(autouse=True)
    def _redirect_downloads_file(self, tmp_path, monkeypatch):
        from services.manga.manga_service import DownloadedChaptersTracker

        monkeypatch.setattr(
            DownloadedChaptersTracker, "_downloads_file", tmp_path / "manga_downloads.json"
        )

    def test_is_downloaded_returns_false_initially(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        assert DownloadedChaptersTracker.is_downloaded("m1", "1") is False

    def test_mark_downloaded_persists(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        DownloadedChaptersTracker.mark_downloaded("m1", "Manga", "5", "/path/5.pdf", 1.2)
        assert DownloadedChaptersTracker.is_downloaded("m1", "5") is True

    def test_get_downloaded_chapters_empty(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        assert DownloadedChaptersTracker.get_downloaded_chapters("m1") == {}

    def test_get_downloaded_chapters_after_mark(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        DownloadedChaptersTracker.mark_downloaded("m1", "Manga", "3", "/x.pdf", 0.5)
        chapters = DownloadedChaptersTracker.get_downloaded_chapters("m1")
        assert "3" in chapters
        assert chapters["3"]["file_path"] == "/x.pdf"

    def test_get_download_path_returns_none_when_missing(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        assert DownloadedChaptersTracker.get_download_path("m1", "99") is None

    def test_get_download_path_returns_path_after_mark(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        DownloadedChaptersTracker.mark_downloaded("m1", "Manga", "7", "/ch7.pdf", 1.0)
        assert DownloadedChaptersTracker.get_download_path("m1", "7") == "/ch7.pdf"

    def test_cleanup_download_removes_entry(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        DownloadedChaptersTracker.mark_downloaded("m1", "Manga", "2", "/x.pdf", 0.3)
        DownloadedChaptersTracker.cleanup_download("m1", "2")
        assert DownloadedChaptersTracker.is_downloaded("m1", "2") is False

    def test_cleanup_download_noop_when_missing(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        # Should not raise
        DownloadedChaptersTracker.cleanup_download("m1", "999")

    def test_load_raw_returns_empty_on_corrupt(self, tmp_path, monkeypatch):
        from services.manga.manga_service import DownloadedChaptersTracker

        f = tmp_path / "bad.json"
        f.write_text("{invalid}")
        monkeypatch.setattr(DownloadedChaptersTracker, "_downloads_file", f)
        assert DownloadedChaptersTracker._load_raw() == {}

    def test_mark_downloaded_with_custom_source(self):
        from services.manga.manga_service import DownloadedChaptersTracker

        DownloadedChaptersTracker.mark_downloaded(
            "m1", "Manga", "1", "/f.pdf", 0.1, source="mugiwaras"
        )
        assert DownloadedChaptersTracker.is_downloaded("m1", "1") is True


# ---------------------------------------------------------------------------
# UnifiedMangaService
# ---------------------------------------------------------------------------


@pytest.fixture
def manga_config(tmp_path):
    from models.config import MangaSettings

    return MangaSettings(
        output_directory=tmp_path / "manga",
        preferred_sources=["src_a", "src_b"],
    )


@pytest.fixture
def plugin_a():
    return _make_plugin(
        "src_a",
        search_results=[_manga_search_result("m1", "Attack on Titan")],
        chapter_results=[_chapter_result("c1", "1")],
        page_results=["http://img1.png", "http://img2.png"],
    )


@pytest.fixture
def plugin_b():
    return _make_plugin(
        "src_b",
        search_results=[_manga_search_result("m2", "Attack on Titan")],
        chapter_results=[_chapter_result("c2", "1")],
    )


@pytest.fixture
def service_ab(manga_config, plugin_a, plugin_b, tmp_path, monkeypatch):
    monkeypatch.setattr("services.manga.manga_service.get_data_path", lambda: tmp_path / "state")
    with patch(
        "services.manga.manga_service.load_manga_plugins",
        return_value={"src_a": plugin_a, "src_b": plugin_b},
    ):
        from services.manga.manga_service import UnifiedMangaService

        svc = UnifiedMangaService(manga_config)
    return svc


class TestUnifiedMangaServiceInit:
    def test_raises_when_no_plugins(self, manga_config):
        with patch("services.manga.manga_service.load_manga_plugins", return_value={}):
            from services.manga.manga_service import UnifiedMangaService

            with pytest.raises(RuntimeError, match="Nenhum plugin"):
                UnifiedMangaService(manga_config)

    def test_default_source_uses_preferred_order(self, manga_config, plugin_a, plugin_b, tmp_path):
        with patch(
            "services.manga.manga_service.load_manga_plugins",
            return_value={"src_a": plugin_a, "src_b": plugin_b},
        ):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(manga_config)
        assert svc.current_source == "src_a"

    def test_fallback_source_if_preferred_not_available(self, tmp_path):
        from models.config import MangaSettings

        config = MangaSettings(preferred_sources=["nonexistent"], output_directory=tmp_path)
        plugin = _make_plugin("other")
        with patch(
            "services.manga.manga_service.load_manga_plugins", return_value={"other": plugin}
        ):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(config)
        assert svc.current_source == "other"


class TestUnifiedMangaServiceSearch:
    def test_search_specific_source(self, service_ab, plugin_a):
        results = service_ab.search_manga("Attack", source="src_a")
        assert len(results) == 1
        assert results[0].title == "Attack on Titan"
        plugin_a.search_manga.assert_called_once()

    def test_search_invalid_source_raises(self, service_ab):
        with pytest.raises(ValueError, match="não disponível"):
            service_ab.search_manga("x", source="nonexistent")

    def test_search_all_sources_merges_by_title(self, service_ab):
        results = service_ab.search_manga("Attack")
        # Both plugins return "Attack on Titan" → merged into 1 result
        assert len(results) == 1

    def test_search_all_sources_multiple_distinct_results(self, manga_config, tmp_path):
        p1 = _make_plugin("src_a", search_results=[_manga_search_result("m1", "Naruto")])
        p2 = _make_plugin("src_b", search_results=[_manga_search_result("m2", "Bleach")])
        with patch(
            "services.manga.manga_service.load_manga_plugins",
            return_value={"src_a": p1, "src_b": p2},
        ):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(manga_config)
        results = svc.search_manga("manga")
        assert len(results) == 2

    def test_search_source_failure_raises_for_specific_source(self, manga_config, tmp_path):
        p = _make_plugin("src_a")
        p.search_manga.side_effect = RuntimeError("network error")
        with patch("services.manga.manga_service.load_manga_plugins", return_value={"src_a": p}):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(manga_config)
        with pytest.raises(ValueError, match="Falha ao buscar"):
            svc.search_manga("x", source="src_a")

    def test_search_source_failure_continues_in_all_sources(self, manga_config, tmp_path):
        p1 = _make_plugin("src_a")
        p1.search_manga.side_effect = RuntimeError("boom")
        p2 = _make_plugin("src_b", search_results=[_manga_search_result("m2", "Bleach")])
        with patch(
            "services.manga.manga_service.load_manga_plugins",
            return_value={"src_a": p1, "src_b": p2},
        ):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(manga_config)
        results = svc.search_manga("Bleach")
        assert len(results) == 1

    def test_search_returns_empty_for_specific_source_no_results(self, manga_config, tmp_path):
        p = _make_plugin("src_a", search_results=[])
        with patch("services.manga.manga_service.load_manga_plugins", return_value={"src_a": p}):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(manga_config)
        assert svc.search_manga("x", source="src_a") == []


class TestUnifiedMangaServiceSources:
    def test_get_available_sources(self, service_ab):
        sources = service_ab.get_available_sources()
        assert "src_a" in sources
        assert "src_b" in sources

    def test_set_source_valid(self, service_ab):
        assert service_ab.set_source("src_b") is True
        assert service_ab.current_source == "src_b"

    def test_set_source_invalid(self, service_ab):
        assert service_ab.set_source("nonexistent") is False

    def test_check_manga_available_true(self, service_ab):
        assert service_ab.check_manga_available("Attack on Titan", source="src_a") is True

    def test_check_manga_available_false(self, service_ab):
        assert service_ab.check_manga_available("Attack on Titan", source="nonexistent") is False

    def test_check_manga_available_exception_returns_false(self, service_ab, plugin_a):
        plugin_a.search_manga.side_effect = Exception("network")
        assert service_ab.check_manga_available("x", source="src_a") is False

    def test_get_available_sources_for_manga(self, service_ab):
        sources = service_ab.get_available_sources_for_manga("Attack on Titan")
        assert "src_a" in sources


class TestUnifiedMangaServiceChapters:
    def test_get_chapters_from_current_source(self, service_ab):
        with patch("services.manga.reading_service.build_manga_url", return_value="http://manga/"):
            chapters = service_ab.get_chapters("m1")
        assert len(chapters) == 1
        assert chapters[0].number == "1"

    def test_get_chapters_invalid_source_raises(self, service_ab):
        with pytest.raises(ValueError, match="não disponível"):
            service_ab.get_chapters("m1", source="missing")

    def test_get_chapters_specific_source_failure_raises(self, service_ab, plugin_a):
        plugin_a.get_chapters.side_effect = RuntimeError("error")
        with pytest.raises(ValueError, match="Falha ao buscar capítulos"):
            service_ab.get_chapters("m1", source="src_a")

    def test_get_chapters_falls_back_on_error(self, manga_config, tmp_path):
        """When primary fails without explicit source, tries fallback."""
        p1 = _make_plugin("src_a")
        p1.get_chapters.side_effect = RuntimeError("timeout")
        p2 = _make_plugin("src_b", chapter_results=[_chapter_result("c1", "5")])
        with patch(
            "services.manga.manga_service.load_manga_plugins",
            return_value={"src_a": p1, "src_b": p2},
        ):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(manga_config)
        with patch("services.manga.reading_service.build_manga_url", return_value="http://x/"):
            chapters = svc.get_chapters("m1")
        assert len(chapters) == 1

    def test_get_chapter_pages(self, service_ab):
        pages = service_ab.get_chapter_pages("c1", chapter_url="http://x", source="src_a")
        assert pages == ["http://img1.png", "http://img2.png"]

    def test_get_chapter_pages_invalid_source_raises(self, service_ab):
        with pytest.raises(ValueError, match="não disponível"):
            service_ab.get_chapter_pages("c1", source="nonexistent")

    def test_get_chapter_pages_constructs_mangadex_url(self, manga_config, tmp_path):
        p = _make_plugin("mangadex", page_results=["http://img.png"])
        with patch("services.manga.manga_service.load_manga_plugins", return_value={"mangadex": p}):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(manga_config)
        pages = svc.get_chapter_pages("chapter-uuid", chapter_url=None, source="mangadex")
        assert pages == ["http://img.png"]


class TestLRUMetadata:
    def test_record_and_get_known_plugin(self, service_ab, tmp_path, monkeypatch):
        service_ab._record_manga_in_plugin("m1", "src_a")
        assert service_ab._get_known_plugin_for_manga("m1") == "src_a"

    def test_lru_eviction_at_1001(self, service_ab):
        for i in range(1001):
            service_ab._record_manga_in_plugin(f"manga-{i}", "src_a")
        assert len(service_ab.manga_plugin_map) == 1000

    def test_get_known_plugin_returns_none_for_unknown(self, service_ab):
        assert service_ab._get_known_plugin_for_manga("unknown-id") is None

    def test_metadata_persisted_and_loaded(self, manga_config, tmp_path, monkeypatch):
        state = tmp_path / "state"
        monkeypatch.setattr("services.manga.manga_service.get_data_path", lambda: state)
        with patch(
            "services.manga.manga_service.load_manga_plugins",
            return_value={"src_a": _make_plugin("src_a")},
        ):
            from services.manga.manga_service import UnifiedMangaService

            svc = UnifiedMangaService(manga_config)
        svc._record_manga_in_plugin("m99", "src_a")

        # Re-create service to load from file
        with patch(
            "services.manga.manga_service.load_manga_plugins",
            return_value={"src_a": _make_plugin("src_a")},
        ):
            from services.manga.manga_service import UnifiedMangaService

            svc2 = UnifiedMangaService(manga_config)
        assert svc2._get_known_plugin_for_manga("m99") == "src_a"
