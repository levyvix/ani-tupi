"""Tests for services/manga/read_orchestrator.py.

Strategy:
- Real implementations for all internal services (MangaHistory, sorting, etc.)
- Mock ONLY external boundaries: httpx, open_pdf_reader, is_zathura_running,
  anilist_client, create_pdf_from_images, _download_images.
- Menus are injected callables — pass fakes (UI boundary).
- File operations use tmp_path.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models.manga import ChapterData, MangaMetadata, MangaStatus


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _manga(title="Test Manga", mid="manga-1", sources=None):
    return MangaMetadata(
        id=mid,
        title=title,
        status=MangaStatus.ONGOING,
        sources=sources or {},
    )


def _chapter(number: str, url: str | None = "http://x", cid: str | None = None):
    return ChapterData(
        id=cid or f"ch-{number}",
        number=number,
        title=None,
        url=url,
        language="pt-br",
    )


def _noop_progress(msg):
    """Context manager that does nothing — replaces ui_bridge.loading."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        yield

    return _ctx()


class _FakeService:
    """Minimal stand-in for UnifiedMangaService."""

    def __init__(
        self,
        search_results=None,
        chapters=None,
        pages=None,
        sources=None,
        raise_on_search=None,
        raise_on_chapters=None,
        raise_on_pages=None,
    ):
        self._search_results = search_results or []
        self._chapters = chapters or []
        self._pages = pages or []
        self._sources = sources or ["mangadex"]
        self._raise_on_search = raise_on_search
        self._raise_on_chapters = raise_on_chapters
        self._raise_on_pages = raise_on_pages
        self.current_source = "mangadex"
        self.last_found_source = None

    def search_manga(self, query):
        if self._raise_on_search:
            raise self._raise_on_search
        return self._search_results

    def get_chapters(self, manga_id, manga_url=None, source=None):
        if self._raise_on_chapters:
            raise self._raise_on_chapters
        return list(self._chapters)

    def get_chapter_pages(self, chapter_id, chapter_url=None, source=None):
        if self._raise_on_pages:
            raise self._raise_on_pages
        return list(self._pages)

    def get_available_sources(self):
        return list(self._sources)

    def get_available_sources_for_manga(self, title):
        return list(self._sources)

    def set_source(self, source):
        self.current_source = source
        return True


# ---------------------------------------------------------------------------
# _sources_suffix
# ---------------------------------------------------------------------------


class TestSourcesSuffix:
    def test_empty_sources_returns_empty_string(self):
        from services.manga.read_orchestrator import _sources_suffix

        assert _sources_suffix({}) == ""

    def test_none_sources_returns_empty_string(self):
        from services.manga.read_orchestrator import _sources_suffix

        assert _sources_suffix(None) == ""

    def test_single_source(self):
        from services.manga.read_orchestrator import _sources_suffix

        assert _sources_suffix({"mangadex": "id1"}) == " [mangadex]"

    def test_multiple_sources_sorted(self):
        from services.manga.read_orchestrator import _sources_suffix

        result = _sources_suffix({"srcB": "b", "srcA": "a"})
        assert result == " [srcA, srcB]"


# ---------------------------------------------------------------------------
# _show_chapter_action_menu
# ---------------------------------------------------------------------------


class TestShowChapterActionMenu:
    def test_returns_read_for_book_icon(self):
        from services.manga.read_orchestrator import _show_chapter_action_menu

        def menu(opts, title):
            return "📖 Ler Agora (Read Now)"

        assert _show_chapter_action_menu(menu) == "read"

    def test_returns_download_for_arrow_icon(self):
        from services.manga.read_orchestrator import _show_chapter_action_menu

        def menu(opts, title):
            return "⬇️  Baixar para Depois (Download for Later)"

        assert _show_chapter_action_menu(menu) == "download"

    def test_returns_none_for_back(self):
        from services.manga.read_orchestrator import _show_chapter_action_menu

        def menu(opts, title):
            return "↩️  Voltar (Back)"

        assert _show_chapter_action_menu(menu) is None

    def test_returns_none_for_none_selection(self):
        from services.manga.read_orchestrator import _show_chapter_action_menu

        def menu(opts, title):
            return None

        assert _show_chapter_action_menu(menu) is None


# ---------------------------------------------------------------------------
# start_manga_search — search paths
# ---------------------------------------------------------------------------


class TestStartMangaSearch:
    def test_no_results_shows_warning(self, monkeypatch):
        from services.manga.read_orchestrator import start_manga_search

        service = _FakeService(search_results=[])
        warnings = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.ui_bridge.show_warning", lambda m: warnings.append(m)
        )
        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.get_preferred_manga_id",
            lambda t: None,
        )

        start_manga_search(service, "Naruto", menu=lambda o, t: None, progress=_noop_progress)
        assert any("Nenhum" in w for w in warnings)

    def test_manga_not_found_error_shows_warning(self, monkeypatch):
        from services.manga.read_orchestrator import start_manga_search
        from services.manga.manga_service import MangaNotFoundError

        service = _FakeService(raise_on_search=MangaNotFoundError("not found"))
        warnings = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.ui_bridge.show_warning", lambda m: warnings.append(m)
        )

        start_manga_search(service, "X", menu=lambda o, t: None, progress=_noop_progress)
        assert len(warnings) == 1

    def test_manga_dex_error_shows_user_message(self, monkeypatch):
        from services.manga.read_orchestrator import start_manga_search
        from services.manga.manga_service import MangaDexError

        err = MangaDexError("internal", user_message="serviço indisponível")
        service = _FakeService(raise_on_search=err)
        warnings = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.ui_bridge.show_warning", lambda m: warnings.append(m)
        )

        start_manga_search(service, "X", menu=lambda o, t: None, progress=_noop_progress)
        assert any("serviço indisponível" in w for w in warnings)

    def test_unexpected_exception_shows_warning(self, monkeypatch):
        from services.manga.read_orchestrator import start_manga_search

        service = _FakeService(raise_on_search=RuntimeError("boom"))
        warnings = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.ui_bridge.show_warning", lambda m: warnings.append(m)
        )

        start_manga_search(service, "X", menu=lambda o, t: None, progress=_noop_progress)
        assert any("Erro inesperado" in w for w in warnings)

    def test_single_result_no_preferred_auto_selects(self, monkeypatch, tmp_path):
        """With one result and no preferred id the manga is auto-selected."""
        from services.manga.read_orchestrator import start_manga_search

        manga = _manga("One Piece")
        service = _FakeService(search_results=[manga], chapters=[_chapter("1")])

        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.get_preferred_manga_id",
            lambda t: None,
        )
        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.set_preferred_manga_id",
            lambda t, i: None,
        )

        # Patch continue_manga_flow to record call without deep execution
        called_with = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.continue_manga_flow",
            lambda svc, m, **kw: called_with.append(m),
        )

        infos = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.ui_bridge.show_info", lambda m: infos.append(m)
        )

        start_manga_search(service, "One Piece", menu=lambda o, t: o[0], progress=_noop_progress)
        assert called_with, "continue_manga_flow should have been called"
        assert called_with[0].title == "One Piece"

    def test_user_cancels_menu_returns_early(self, monkeypatch):
        """If menu raises KeyboardInterrupt the function returns silently."""
        from services.manga.read_orchestrator import start_manga_search

        manga = _manga("Bleach")
        service = _FakeService(search_results=[manga, _manga("Naruto")])

        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.get_preferred_manga_id",
            lambda t: None,
        )

        def _menu(opts, title):
            raise KeyboardInterrupt

        # Should not raise
        start_manga_search(service, "B", menu=_menu, progress=_noop_progress)

    def test_preferred_manga_shown_first_then_switch(self, monkeypatch):
        """When preferred id matches, user can opt to switch manga."""
        from services.manga.read_orchestrator import start_manga_search

        manga1 = _manga("One Piece", "m1")
        manga2 = _manga("Naruto", "m2")
        service = _FakeService(search_results=[manga1, manga2])

        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.get_preferred_manga_id",
            lambda t: "m1",
        )
        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.set_preferred_manga_id",
            lambda t, i: None,
        )

        called = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.continue_manga_flow",
            lambda svc, m, **kw: called.append(m),
        )
        monkeypatch.setattr("services.manga.read_orchestrator.ui_bridge.show_info", lambda m: None)

        # First menu returns "🔄 Trocar de mangá" → then second menu returns manga2
        call_count = [0]

        def _menu(opts, title):
            call_count[0] += 1
            if call_count[0] == 1:
                return "🔄 Trocar de mangá"
            # Return label that contains "Naruto"
            return next((o for o in opts if "Naruto" in o), opts[0])

        start_manga_search(service, "One Piece", menu=_menu, progress=_noop_progress)
        assert called and called[0].title == "Naruto"


# ---------------------------------------------------------------------------
# _prepare_chapter_pdf
# ---------------------------------------------------------------------------


def _fake_manga_settings(tmp_path, auto_create_pdf=True, delete_images=False, pdf_quality=80):
    return SimpleNamespace(
        manga=SimpleNamespace(
            output_directory=tmp_path,
            auto_create_pdf=auto_create_pdf,
            delete_images_after_pdf=delete_images,
            pdf_quality=pdf_quality,
            default_download_range=3,
            skip_already_downloaded=False,
            max_parallel_downloads=1,
            auto_delete_read_chapters=False,
        )
    )


class TestPrepareChapterPdf:
    def test_existing_pdf_returned_immediately(self, tmp_path):
        from services.manga.read_orchestrator import _prepare_chapter_pdf

        manga = _manga()
        chapter = _chapter("5")

        # Create the expected pdf path
        output_path = tmp_path / manga.title / chapter.number
        output_path.mkdir(parents=True)
        pdf_path = output_path / f"{chapter.number}.pdf"
        pdf_path.write_bytes(b"fake pdf")

        # settings is imported locally inside the function: patch models.config.settings
        with patch("models.config.settings", _fake_manga_settings(tmp_path)):
            service = _FakeService()
            result = _prepare_chapter_pdf(manga, chapter, "mangadex", service, _noop_progress)

        assert result == pdf_path

    def test_no_pages_returns_none(self, tmp_path):
        from services.manga.read_orchestrator import _prepare_chapter_pdf

        manga = _manga()
        chapter = _chapter("1")
        service = _FakeService(pages=[])

        warnings = []
        with (
            patch("models.config.settings", _fake_manga_settings(tmp_path)),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
        ):
            result = _prepare_chapter_pdf(manga, chapter, "mangadex", service, _noop_progress)

        assert result is None
        assert any("Nenhuma página" in w for w in warnings)

    def test_get_chapter_pages_mangadex_error_returns_none(self, tmp_path):
        from services.manga.read_orchestrator import _prepare_chapter_pdf
        from services.manga.manga_service import MangaDexError

        manga = _manga()
        chapter = _chapter("2")
        service = _FakeService(raise_on_pages=MangaDexError("err", user_message="falhou"))

        warnings = []
        with (
            patch("models.config.settings", _fake_manga_settings(tmp_path)),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
        ):
            result = _prepare_chapter_pdf(manga, chapter, "mangadex", service, _noop_progress)

        assert result is None
        assert any("falhou" in w for w in warnings)

    def test_get_chapter_pages_generic_error_returns_none(self, tmp_path):
        from services.manga.read_orchestrator import _prepare_chapter_pdf

        manga = _manga()
        chapter = _chapter("2")
        service = _FakeService(raise_on_pages=RuntimeError("network fail"))

        warnings = []
        with (
            patch("models.config.settings", _fake_manga_settings(tmp_path)),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
        ):
            result = _prepare_chapter_pdf(manga, chapter, "mangadex", service, _noop_progress)

        assert result is None
        assert any("Erro ao carregar" in w for w in warnings)

    def test_auto_create_pdf_false_returns_none(self, tmp_path):
        """When auto_create_pdf=False, images are saved but no PDF is returned."""
        from services.manga.read_orchestrator import _prepare_chapter_pdf

        manga = _manga()
        chapter = _chapter("3", url="http://img/1.jpg")
        service = _FakeService(pages=["http://img/1.jpg"])

        with (
            patch("models.config.settings", _fake_manga_settings(tmp_path, auto_create_pdf=False)),
            patch("services.manga.read_orchestrator._download_images"),
            patch("services.manga.read_orchestrator.ui_bridge.show_info"),
        ):
            result = _prepare_chapter_pdf(manga, chapter, "mangadex", service, _noop_progress)

        assert result is None

    def test_pdf_created_when_pages_available(self, tmp_path):
        """Happy path: pages available, pdf created and returned."""
        from services.manga.read_orchestrator import _prepare_chapter_pdf

        manga = _manga()
        chapter = _chapter("4", url="http://img/page.jpg")
        service = _FakeService(pages=["http://img/page.jpg"])

        expected_pdf = tmp_path / manga.title / chapter.number / f"{chapter.number}.pdf"

        def _create_fake_pdf(out_dir, pdf_path, quality):
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"pdf")

        with (
            patch("models.config.settings", _fake_manga_settings(tmp_path)),
            patch("services.manga.read_orchestrator._download_images"),
            patch(
                "services.manga.read_orchestrator.create_pdf_from_images",
                side_effect=_create_fake_pdf,
            ),
        ):
            result = _prepare_chapter_pdf(manga, chapter, "mangadex", service, _noop_progress)

        assert result == expected_pdf

    def test_download_error_cleans_up_output_dir(self, tmp_path):
        """When _download_images raises, output dir is cleaned and None returned."""
        from services.manga.read_orchestrator import _prepare_chapter_pdf

        manga = _manga()
        chapter = _chapter("6", url="http://img/1.jpg")
        service = _FakeService(pages=["http://img/1.jpg"])

        warnings = []
        with (
            patch("models.config.settings", _fake_manga_settings(tmp_path)),
            patch(
                "services.manga.read_orchestrator._download_images",
                side_effect=RuntimeError("disk full"),
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
        ):
            result = _prepare_chapter_pdf(manga, chapter, "mangadex", service, _noop_progress)

        assert result is None
        assert any("Erro ao processar" in w for w in warnings)


# ---------------------------------------------------------------------------
# _load_chapters_with_fallback
# ---------------------------------------------------------------------------


class TestLoadChaptersWithFallback:
    def test_success_returns_chapters(self, tmp_path):
        from services.manga.read_orchestrator import _load_chapters_with_fallback

        chapters = [_chapter("1"), _chapter("2")]
        service = _FakeService(chapters=chapters)
        manga = _manga()

        result_chapters, src, url, result_manga = _load_chapters_with_fallback(
            service, manga, "mangadex", True, _noop_progress
        )
        assert result_chapters == chapters
        assert src == "mangadex"

    def test_mangadex_error_with_no_fallback(self, monkeypatch):
        from services.manga.read_orchestrator import _load_chapters_with_fallback
        from services.manga.manga_service import MangaDexError

        err = MangaDexError("err", user_message="falhou")
        service = _FakeService(raise_on_chapters=err, sources=["mangadex"])
        manga = _manga()

        warnings = []
        with patch(
            "services.manga.read_orchestrator.ui_bridge.show_warning",
            side_effect=lambda m: warnings.append(m),
        ):
            result_chapters, src, url, result_manga = _load_chapters_with_fallback(
                service, manga, "mangadex", allow_source_change=False, progress=_noop_progress
            )

        assert result_chapters is None

    def test_generic_exception_returns_none(self, monkeypatch):
        from services.manga.read_orchestrator import _load_chapters_with_fallback

        service = _FakeService(raise_on_chapters=RuntimeError("network failure"))
        manga = _manga()

        warnings = []
        with patch(
            "services.manga.read_orchestrator.ui_bridge.show_warning",
            side_effect=lambda m: warnings.append(m),
        ):
            result_chapters, _, _, _ = _load_chapters_with_fallback(
                service, manga, "mangadex", True, _noop_progress
            )

        assert result_chapters is None

    def test_fallback_source_used_on_mangadex_error(self, monkeypatch):
        """When primary fails with MangaDexError and fallback succeeds, returns fallback chapters."""
        from services.manga.read_orchestrator import _load_chapters_with_fallback
        from services.manga.manga_service import MangaDexError

        fallback_chapters = [_chapter("1")]
        call_count = [0]

        class _MultiService(_FakeService):
            def get_chapters(self, manga_id, manga_url=None, source=None):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise MangaDexError("primary failed", user_message="falhou")
                return fallback_chapters

        service = _MultiService(sources=["mangadex", "mugiwaras"])
        manga = _manga(sources={"mangadex": "m1", "mugiwaras": "m2"})

        with (
            patch("services.manga.read_orchestrator.ui_bridge.show_warning"),
            patch("services.manga.read_orchestrator.ui_bridge.show_info"),
            patch("services.manga.read_orchestrator.manga_source_preferences.set_preferred_source"),
        ):
            result_chapters, src, url, result_manga = _load_chapters_with_fallback(
                service, manga, "mangadex", allow_source_change=True, progress=_noop_progress
            )

        assert result_chapters == fallback_chapters
        assert src == "mugiwaras"


# ---------------------------------------------------------------------------
# _sync_read_to_anilist
# ---------------------------------------------------------------------------


class TestSyncReadToAnilist:
    def test_skipped_when_not_authenticated(self, monkeypatch):
        from services.manga.read_orchestrator import _sync_read_to_anilist

        with patch(
            "services.manga.read_orchestrator.anilist_client.is_authenticated", return_value=False
        ):
            # Should return without calling menu
            menu_called = []
            _sync_read_to_anilist(
                _manga(), _chapter("1"), None, menu=lambda o, t: menu_called.append(1) or o[0]
            )
        assert not menu_called

    def test_user_says_not_finished_no_update(self, monkeypatch):
        from services.manga.read_orchestrator import _sync_read_to_anilist

        infos = []
        with (
            patch(
                "services.manga.read_orchestrator.anilist_client.is_authenticated",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
        ):
            _sync_read_to_anilist(
                _manga(),
                _chapter("5"),
                None,
                menu=lambda opts, title: "❌ Não, parei antes",
            )
        assert any("não atualizado" in i for i in infos)

    def test_anilist_not_found_shows_warning(self, monkeypatch):
        from services.manga.read_orchestrator import _sync_read_to_anilist

        warnings = []
        with (
            patch(
                "services.manga.read_orchestrator.anilist_client.is_authenticated",
                return_value=True,
            ),
            patch("services.manga.read_orchestrator.anilist_client.search_manga", return_value=[]),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
        ):
            _sync_read_to_anilist(
                _manga("Missing Title"),
                _chapter("1"),
                None,
                menu=lambda opts, title: "✅ Sim, li até o final",
            )
        assert any("não encontrado no AniList" in w for w in warnings)

    def test_successful_sync_updates_progress(self, monkeypatch):
        from services.manga.read_orchestrator import _sync_read_to_anilist

        anilist_manga = SimpleNamespace(id=42, status="CURRENT")
        infos = []
        with (
            patch(
                "services.manga.read_orchestrator.anilist_client.is_authenticated",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.search_manga",
                return_value=[anilist_manga],
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.get_manga_list_entry",
                return_value=anilist_manga,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.update_manga_progress",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
        ):
            _sync_read_to_anilist(
                _manga("One Piece"),
                _chapter("1050"),
                None,
                menu=lambda opts, title: "✅ Sim, li até o final",
            )
        assert any("AniList" in i for i in infos)

    def test_failed_update_shows_warning(self, monkeypatch):
        from services.manga.read_orchestrator import _sync_read_to_anilist

        anilist_manga = SimpleNamespace(id=42, status="CURRENT")
        warnings = []
        with (
            patch(
                "services.manga.read_orchestrator.anilist_client.is_authenticated",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.search_manga",
                return_value=[anilist_manga],
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.get_manga_list_entry",
                return_value=anilist_manga,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.update_manga_progress",
                return_value=False,
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
        ):
            _sync_read_to_anilist(
                _manga(),
                _chapter("1"),
                None,
                menu=lambda opts, title: "✅ Sim, li até o final",
            )
        assert any("Falha" in w for w in warnings)


# ---------------------------------------------------------------------------
# _select_source
# ---------------------------------------------------------------------------


class TestSelectSource:
    def test_single_source_returns_current(self, monkeypatch):
        from services.manga.read_orchestrator import _select_source

        service = _FakeService(sources=["mangadex"])
        manga = _manga()

        with patch(
            "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
            return_value=None,
        ):
            chosen, updated = _select_source(
                service, manga, "mangadex", menu=lambda o, t: o[0], progress=_noop_progress
            )
        assert chosen == "mangadex"
        assert updated is manga

    def test_user_cancels_returns_none(self, monkeypatch):
        from services.manga.read_orchestrator import _select_source

        service = _FakeService(sources=["mangadex", "mugiwaras"])
        manga = _manga()

        with patch(
            "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
            return_value=None,
        ):
            chosen, _ = _select_source(
                service, manga, "mangadex", menu=lambda o, t: None, progress=_noop_progress
            )
        assert chosen is None

    def test_keyboard_interrupt_returns_none(self, monkeypatch):
        from services.manga.read_orchestrator import _select_source

        service = _FakeService(sources=["mangadex", "mugiwaras"])
        manga = _manga()

        with patch(
            "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
            return_value=None,
        ):
            chosen, _ = _select_source(
                service,
                manga,
                "mangadex",
                menu=lambda o, t: (_ for _ in ()).throw(KeyboardInterrupt()),
                progress=_noop_progress,
            )
        assert chosen is None

    def test_switch_source_updates_and_saves(self, monkeypatch):
        from services.manga.read_orchestrator import _select_source

        service = _FakeService(
            sources=["mangadex", "mugiwaras"],
            search_results=[_manga("Test", sources={"mugiwaras": "m99"})],
        )
        manga = _manga("Test", sources={"mangadex": "m1", "mugiwaras": "m99"})

        infos = []
        prefs_set = []
        with (
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value=None,
            ),
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.set_preferred_source",
                side_effect=lambda t, s: prefs_set.append(s),
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
            patch(
                "services.manga.read_orchestrator.research_manga_in_new_source", return_value=manga
            ),
        ):
            chosen, _ = _select_source(
                service,
                manga,
                "mangadex",
                menu=lambda opts, title: "🔄 Trocar para: mugiwaras",
                progress=_noop_progress,
            )

        assert chosen == "mugiwaras"
        assert "mugiwaras" in prefs_set


# ---------------------------------------------------------------------------
# handle_download_for_later — basic paths
# ---------------------------------------------------------------------------


class TestHandleDownloadForLater:
    def _make_chapters(self):
        return [_chapter("1"), _chapter("2"), _chapter("3")]

    def test_empty_chapters_shows_warning(self, tmp_path, monkeypatch):
        from services.manga.read_orchestrator import handle_download_for_later

        service = _FakeService(chapters=[])
        manga = _manga()
        history = MagicMock()
        history.get_last_chapter.return_value = None

        warnings = []
        with patch(
            "services.manga.read_orchestrator.ui_bridge.show_warning",
            side_effect=lambda m: warnings.append(m),
        ):
            handle_download_for_later(
                service,
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=[],
                menu=lambda o, t: None,
                progress=_noop_progress,
            )
        assert any("Nenhum capítulo" in w for w in warnings)

    def test_no_chapters_arg_loads_from_service(self, tmp_path):
        """When chapters=None, service.get_chapters is called."""
        from services.manga.read_orchestrator import handle_download_for_later

        service = _FakeService(chapters=self._make_chapters())
        manga = _manga()
        history = MagicMock()
        history.get_last_chapter.return_value = None

        with (
            patch(
                "services.manga.read_orchestrator.prompt_download_range", return_value=[]
            ) as mock_range,
            patch("services.manga.read_orchestrator.ui_bridge.show_warning"),
            patch("models.config.settings", _fake_manga_settings(tmp_path)),
        ):
            handle_download_for_later(
                service,
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=None,
                menu=lambda o, t: None,
                progress=_noop_progress,
            )

        # prompt_download_range called with the loaded chapters
        mock_range.assert_called_once()

    def test_download_completes_successfully(self, tmp_path):
        from services.manga.read_orchestrator import handle_download_for_later
        from services.manga.download import BatchDownloadResult

        chapters = self._make_chapters()
        service = _FakeService(chapters=chapters)
        manga = _manga()
        history = MagicMock()
        history.get_last_chapter.return_value = None

        result = BatchDownloadResult(successful=3, failed_chapters=[])

        infos = []
        with (
            patch("services.manga.read_orchestrator.prompt_download_range", return_value=chapters),
            patch(
                "services.manga.read_orchestrator.split_new_and_downloaded",
                return_value=(chapters, []),
            ),
            patch("services.manga.read_orchestrator.download_chapters_batch", return_value=result),
            patch("services.manga.read_orchestrator.resolve_parallelism", return_value=1),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
            patch("models.config.settings", _fake_manga_settings(tmp_path)),
        ):
            handle_download_for_later(
                service,
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=chapters,
                menu=lambda o, t: None,
                progress=_noop_progress,
                prompt=lambda m: None,
            )

        assert any("3" in i for i in infos)

    def test_already_downloaded_cancel_aborts(self, tmp_path):
        from services.manga.read_orchestrator import handle_download_for_later

        chapters = self._make_chapters()
        manga = _manga()
        history = MagicMock()
        history.get_last_chapter.return_value = None

        fake_settings = _fake_manga_settings(tmp_path)
        fake_settings.manga.skip_already_downloaded = True

        with (
            patch("services.manga.read_orchestrator.prompt_download_range", return_value=chapters),
            patch(
                "services.manga.read_orchestrator.split_new_and_downloaded",
                return_value=([], chapters),
            ),
            patch("services.manga.read_orchestrator.download_chapters_batch") as mock_dl,
            patch("models.config.settings", fake_settings),
        ):
            handle_download_for_later(
                _FakeService(),
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=chapters,
                menu=lambda o, t: "❌ Cancelar",
                progress=_noop_progress,
            )

        mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# continue_manga_flow — happy path with no resume
# ---------------------------------------------------------------------------


class TestContinueMangaFlow:
    def test_no_chapters_shows_warning(self, monkeypatch):
        from services.manga.read_orchestrator import continue_manga_flow

        service = _FakeService(chapters=[])
        manga = _manga()

        warnings = []
        with (
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
            patch(
                "services.manga.read_orchestrator._select_source", return_value=("mangadex", manga)
            ),
            patch("services.manga.read_orchestrator._get_anilist_progress", return_value=None),
            patch("services.manga.read_orchestrator.MangaHistory") as mock_hist,
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value="mangadex",
            ),
            patch("services.manga.read_orchestrator.manga_source_preferences.set_preferred_source"),
        ):
            mock_hist.return_value.get_last_chapter.return_value = None
            continue_manga_flow(
                service,
                manga,
                allow_source_change=True,
                menu=lambda o, t: None,
                progress=_noop_progress,
            )

        assert any("Nenhum capítulo" in w for w in warnings)

    def test_user_cancels_source_selection_returns_early(self, monkeypatch):
        from services.manga.read_orchestrator import continue_manga_flow

        service = _FakeService(chapters=[_chapter("1")])
        manga = _manga()

        process_called = []
        with (
            patch("services.manga.read_orchestrator._select_source", return_value=(None, manga)),
            patch(
                "services.manga.read_orchestrator._process_chapter",
                side_effect=lambda *a, **kw: process_called.append(1),
            ),
        ):
            continue_manga_flow(
                service,
                manga,
                allow_source_change=True,
                menu=lambda o, t: None,
                progress=_noop_progress,
            )

        assert not process_called

    def test_chapter_list_shown_user_reads(self, monkeypatch, tmp_path):
        """Menu -> chapter -> 'read' action triggers _process_chapter."""
        from services.manga.read_orchestrator import continue_manga_flow

        chapters = [_chapter("1", url="http://x")]
        service = _FakeService(chapters=chapters)
        manga = _manga()

        process_calls = []

        with (
            patch(
                "services.manga.read_orchestrator._select_source", return_value=("mangadex", manga)
            ),
            patch("services.manga.read_orchestrator._get_anilist_progress", return_value=None),
            patch("services.manga.read_orchestrator.MangaHistory") as mock_hist,
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value="mangadex",
            ),
            patch("services.manga.read_orchestrator.manga_source_preferences.set_preferred_source"),
            patch(
                "services.manga.read_orchestrator._process_chapter",
                side_effect=lambda *a, **kw: process_calls.append(1),
            ),
        ):
            mock_hist.return_value.get_last_chapter.return_value = None

            menu_calls = [0]

            def _menu(opts, title):
                menu_calls[0] += 1
                if "Selecione capítulo" in title:
                    if menu_calls[0] > 2:
                        return None  # exit loop
                    return opts[0]
                if "O que deseja fazer" in title:
                    return "📖 Ler Agora (Read Now)"
                return None

            continue_manga_flow(
                service, manga, allow_source_change=True, menu=_menu, progress=_noop_progress
            )

        assert process_calls

    def test_resume_immediately_skips_chapter_list(self, monkeypatch, tmp_path):
        """When resume chosen and chapter found, goes straight to _process_chapter."""
        from services.manga.read_orchestrator import continue_manga_flow

        chapters = [_chapter("5"), _chapter("6")]
        service = _FakeService(chapters=chapters)
        manga = _manga()

        process_calls = []
        with (
            patch(
                "services.manga.read_orchestrator._select_source", return_value=("mangadex", manga)
            ),
            patch("services.manga.read_orchestrator._get_anilist_progress", return_value=4),
            patch("services.manga.read_orchestrator.MangaHistory") as mock_hist,
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value="mangadex",
            ),
            patch("services.manga.read_orchestrator.manga_source_preferences.set_preferred_source"),
            patch("services.manga.read_orchestrator.ui_bridge.show_info"),
            patch(
                "services.manga.read_orchestrator._process_chapter",
                side_effect=lambda *a, **kw: process_calls.append(1),
            ),
        ):
            mock_hist.return_value.get_last_chapter.return_value = None

            # resume menu: choose "⮕ Sim, retomar"
            def _menu(opts, title):
                if "Retomar" in title:
                    return next((o for o in opts if o.startswith("⮕ Sim")), None)
                return None

            continue_manga_flow(
                service, manga, allow_source_change=True, menu=_menu, progress=_noop_progress
            )

        assert process_calls


# ---------------------------------------------------------------------------
# _process_chapter — navigation loop
# ---------------------------------------------------------------------------


class TestProcessChapter:
    def _setup_pdf(self, tmp_path, manga, chapter):
        """Create a fake PDF so _prepare_chapter_pdf returns it."""
        output_path = tmp_path / manga.title / chapter.number
        output_path.mkdir(parents=True)
        pdf_path = output_path / f"{chapter.number}.pdf"
        pdf_path.write_bytes(b"fake")
        return pdf_path

    def test_returns_when_pdf_none(self, monkeypatch):
        from services.manga.read_orchestrator import _process_chapter

        manga = _manga()
        chapter = _chapter("1")
        history = MagicMock()

        with patch("services.manga.read_orchestrator._prepare_chapter_pdf", return_value=None):
            # Should return without calling open_pdf_reader
            open_calls = []
            with patch(
                "services.manga.read_orchestrator.open_pdf_reader",
                side_effect=lambda p: open_calls.append(p),
            ):
                _process_chapter(
                    _FakeService(),
                    manga,
                    chapter,
                    None,
                    "mangadex",
                    history,
                    [chapter],
                    ["Cap. 1"],
                    0,
                    menu=lambda o, t: None,
                    progress=_noop_progress,
                )
        assert not open_calls

    def test_selects_next_chapter(self, monkeypatch, tmp_path):
        from services.manga.read_orchestrator import _process_chapter

        manga = _manga()
        ch1 = _chapter("1")
        ch2 = _chapter("2")
        chapters = [ch1, ch2]
        history = MagicMock()

        call_count = [0]

        def _fake_prepare(manga, chapter, src, svc, progress):
            call_count[0] += 1
            if call_count[0] > 2:
                return None  # stop after 2 chapters
            pdf = tmp_path / f"{chapter.number}.pdf"
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(b"pdf")
            return pdf

        nav_calls = [0]

        def _menu(opts, title):
            nav_calls[0] += 1
            if nav_calls[0] == 1:
                return "Próximo"
            return "Selecionar outro capítulo"

        with (
            patch(
                "services.manga.read_orchestrator._prepare_chapter_pdf", side_effect=_fake_prepare
            ),
            patch("services.manga.read_orchestrator.open_pdf_reader"),
            patch("services.manga.read_orchestrator.is_zathura_running", return_value=False),
            patch("services.manga.read_orchestrator._sync_read_to_anilist"),
        ):
            _process_chapter(
                _FakeService(),
                manga,
                ch1,
                None,
                "mangadex",
                history,
                chapters,
                ["Cap. 1", "Cap. 2"],
                0,
                menu=_menu,
                progress=_noop_progress,
            )

        # history.update called twice (once per chapter read)
        assert history.update.call_count == 2

    def test_previous_chapter_navigation(self, monkeypatch, tmp_path):
        from services.manga.read_orchestrator import _process_chapter

        manga = _manga()
        ch1 = _chapter("1")
        ch2 = _chapter("2")
        chapters = [ch1, ch2]
        history = MagicMock()

        nav_calls = [0]

        def _menu(opts, title):
            nav_calls[0] += 1
            if nav_calls[0] == 1:
                return "Anterior"  # at ch2, go back -> first chapter
            return "Selecionar outro capítulo"

        def _fake_prepare(manga, chapter, src, svc, progress):
            pdf = tmp_path / f"{chapter.number}.pdf"
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(b"pdf")
            return pdf

        with (
            patch(
                "services.manga.read_orchestrator._prepare_chapter_pdf", side_effect=_fake_prepare
            ),
            patch("services.manga.read_orchestrator.open_pdf_reader"),
            patch("services.manga.read_orchestrator.is_zathura_running", return_value=False),
            patch("services.manga.read_orchestrator._sync_read_to_anilist"),
        ):
            _process_chapter(
                _FakeService(),
                manga,
                ch2,
                None,
                "mangadex",
                history,
                chapters,
                ["Cap. 1", "Cap. 2"],
                1,
                menu=_menu,
                progress=_noop_progress,
            )

        # Should have processed both ch2 and ch1 (after going back)
        assert history.update.call_count == 2

    def test_at_first_chapter_previous_shows_info(self, monkeypatch, tmp_path):
        from services.manga.read_orchestrator import _process_chapter

        manga = _manga()
        ch1 = _chapter("1")
        chapters = [ch1]
        history = MagicMock()

        infos = []
        nav_calls = [0]

        def _menu(opts, title):
            nav_calls[0] += 1
            if nav_calls[0] == 1:
                return "Anterior"
            return None  # exit

        with (
            patch(
                "services.manga.read_orchestrator._prepare_chapter_pdf",
                return_value=tmp_path / "1.pdf",
            ),
            patch("services.manga.read_orchestrator.open_pdf_reader"),
            patch("services.manga.read_orchestrator.is_zathura_running", return_value=False),
            patch("services.manga.read_orchestrator._sync_read_to_anilist"),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
        ):
            # Create the pdf file
            (tmp_path / "1.pdf").write_bytes(b"pdf")
            _process_chapter(
                _FakeService(),
                manga,
                ch1,
                None,
                "mangadex",
                history,
                chapters,
                ["Cap. 1"],
                0,
                menu=_menu,
                progress=_noop_progress,
            )

        assert any("primeiro capítulo" in i for i in infos)

    def test_next_chapter_at_end_shows_info(self, monkeypatch, tmp_path):
        from services.manga.read_orchestrator import _process_chapter

        manga = _manga()
        ch1 = _chapter("1")
        chapters = [ch1]
        history = MagicMock()

        infos = []
        nav_calls = [0]

        def _menu(opts, title):
            nav_calls[0] += 1
            if nav_calls[0] == 1:
                return "Próximo"
            return None

        with (
            patch(
                "services.manga.read_orchestrator._prepare_chapter_pdf",
                return_value=tmp_path / "1.pdf",
            ),
            patch("services.manga.read_orchestrator.open_pdf_reader"),
            patch("services.manga.read_orchestrator.is_zathura_running", return_value=False),
            patch("services.manga.read_orchestrator._sync_read_to_anilist"),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
        ):
            (tmp_path / "1.pdf").write_bytes(b"pdf")
            _process_chapter(
                _FakeService(),
                manga,
                ch1,
                None,
                "mangadex",
                history,
                chapters,
                ["Cap. 1"],
                0,
                menu=_menu,
                progress=_noop_progress,
            )

        assert any("final dos capítulos" in i for i in infos)

    def test_keyboard_interrupt_exits_loop(self, monkeypatch, tmp_path):
        from services.manga.read_orchestrator import _process_chapter

        manga = _manga()
        ch1 = _chapter("1")
        chapters = [ch1]
        history = MagicMock()

        with (
            patch(
                "services.manga.read_orchestrator._prepare_chapter_pdf",
                return_value=tmp_path / "1.pdf",
            ),
            patch("services.manga.read_orchestrator.open_pdf_reader"),
            patch("services.manga.read_orchestrator.is_zathura_running", return_value=False),
            patch("services.manga.read_orchestrator._sync_read_to_anilist"),
        ):
            (tmp_path / "1.pdf").write_bytes(b"pdf")
            _process_chapter(
                _FakeService(),
                manga,
                ch1,
                None,
                "mangadex",
                history,
                chapters,
                ["Cap. 1"],
                0,
                menu=lambda o, t: (_ for _ in ()).throw(KeyboardInterrupt()),
                progress=_noop_progress,
            )
        # Should return without raising


# ---------------------------------------------------------------------------
# Additional targeted tests for uncovered branches
# ---------------------------------------------------------------------------


class TestStartMangaSearchEdgeCases:
    """Cover lines 96-97, 99, 118, 121-122."""

    def test_preferred_manga_keyboard_interrupt_returns(self, monkeypatch):
        """KI on the preferred-manga confirmation menu returns silently (lines 96-97)."""
        from services.manga.read_orchestrator import start_manga_search

        manga = _manga("One Piece", "m1")
        service = _FakeService(search_results=[manga])
        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.get_preferred_manga_id",
            lambda t: "m1",
        )

        def _menu(opts, title):
            raise KeyboardInterrupt

        # Should not raise
        start_manga_search(service, "One Piece", menu=_menu, progress=_noop_progress)

    def test_preferred_manga_choice_none_returns(self, monkeypatch):
        """None choice on preferred-manga confirmation returns silently (line 99)."""
        from services.manga.read_orchestrator import start_manga_search

        manga = _manga("One Piece", "m1")
        service = _FakeService(search_results=[manga])
        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.get_preferred_manga_id",
            lambda t: "m1",
        )

        continue_called = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.continue_manga_flow",
            lambda *a, **kw: continue_called.append(1),
        )

        # menu returns None
        start_manga_search(
            service, "One Piece", menu=lambda opts, title: None, progress=_noop_progress
        )
        assert not continue_called

    def test_multi_result_menu_returns_none_exits(self, monkeypatch):
        """None selection from multi-result menu returns early (line 118)."""
        from services.manga.read_orchestrator import start_manga_search

        m1 = _manga("Bleach", "m1")
        m2 = _manga("Naruto", "m2")
        service = _FakeService(search_results=[m1, m2])
        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.get_preferred_manga_id",
            lambda t: None,
        )

        continue_called = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.continue_manga_flow",
            lambda *a, **kw: continue_called.append(1),
        )

        start_manga_search(service, "x", menu=lambda opts, title: None, progress=_noop_progress)
        assert not continue_called

    def test_multi_result_unknown_selection_logs_error(self, monkeypatch):
        """Menu returns unknown title -> logs error and returns (lines 121-122)."""
        from services.manga.read_orchestrator import start_manga_search

        m1 = _manga("Bleach", "m1")
        m2 = _manga("Naruto", "m2")
        service = _FakeService(search_results=[m1, m2])
        monkeypatch.setattr(
            "services.manga.read_orchestrator.manga_selection_preferences.get_preferred_manga_id",
            lambda t: None,
        )

        continue_called = []
        monkeypatch.setattr(
            "services.manga.read_orchestrator.continue_manga_flow",
            lambda *a, **kw: continue_called.append(1),
        )

        # Return a label that won't match any key
        start_manga_search(
            service,
            "x",
            menu=lambda opts, title: "Completely Unknown Manga Title XYZ",
            progress=_noop_progress,
        )
        assert not continue_called


class TestSelectSourceEdgeCases:
    """Cover lines 160-164, 183-189, 199-201."""

    def test_saved_source_not_in_available_removes_preference(self, monkeypatch):
        """Saved source not in sources_with_manga -> remove preference (lines 162-164)."""
        from services.manga.read_orchestrator import _select_source

        service = _FakeService(sources=["mangadex", "mugiwaras"])
        manga = _manga("Test", sources={"mangadex": "m1", "mugiwaras": "m2"})

        remove_calls = []
        with (
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value="old_source",
            ),
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.remove_preference",
                side_effect=lambda t: remove_calls.append(t),
            ),
        ):
            # Menu returns None to cancel
            chosen, _ = _select_source(
                service, manga, "mangadex", menu=lambda opts, title: None, progress=_noop_progress
            )

        assert remove_calls

    def test_use_saved_source_option(self, monkeypatch):
        """'⭐ Usar fonte salva:' path sets source and returns it (lines 183-189)."""
        from services.manga.read_orchestrator import _select_source

        service = _FakeService(sources=["mangadex", "mugiwaras"])
        manga = _manga("Test", sources={"mangadex": "m1", "mugiwaras": "m2"})
        updated_manga = _manga("Test", sources={"mangadex": "m1", "mugiwaras": "m2"})

        infos = []
        with (
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value="mugiwaras",
            ),
            patch(
                "services.manga.read_orchestrator.research_manga_in_new_source",
                return_value=updated_manga,
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
        ):
            chosen, result = _select_source(
                service,
                manga,
                "mangadex",
                menu=lambda opts, title: "⭐ Usar fonte salva: mugiwaras",
                progress=_noop_progress,
            )

        assert chosen == "mugiwaras"
        assert any("mugiwaras" in i for i in infos)

    def test_switch_source_set_source_fails_shows_warning(self, monkeypatch):
        """When set_source returns False, warning shown and None returned (lines 199-201)."""
        from services.manga.read_orchestrator import _select_source

        class _FailService(_FakeService):
            def set_source(self, source):
                return False

        service = _FailService(sources=["mangadex", "mugiwaras"])
        manga = _manga("Test", sources={"mangadex": "m1", "mugiwaras": "m2"})

        warnings = []
        with (
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value=None,
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
        ):
            chosen, _ = _select_source(
                service,
                manga,
                "mangadex",
                menu=lambda opts, title: "🔄 Trocar para: mugiwaras",
                progress=_noop_progress,
            )

        assert chosen is None
        assert any("Falha" in w for w in warnings)


class TestGetAnilistProgress:
    """Cover lines 205-212."""

    def test_authenticated_returns_matched_progress(self, monkeypatch):
        from services.manga.read_orchestrator import _get_anilist_progress

        manga = _manga("One Piece")
        fake_list = [SimpleNamespace(title="One Piece", progress=1050)]

        with (
            patch(
                "services.manga.read_orchestrator.anilist_client.is_authenticated",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.get_user_manga_list",
                return_value=fake_list,
            ),
            patch("services.manga.read_orchestrator.match_anilist_progress", return_value=1050),
        ):
            result = _get_anilist_progress(manga)

        assert result == 1050

    def test_authenticated_exception_returns_none(self, monkeypatch):
        from services.manga.read_orchestrator import _get_anilist_progress

        manga = _manga()
        with (
            patch(
                "services.manga.read_orchestrator.anilist_client.is_authenticated",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.get_user_manga_list",
                side_effect=RuntimeError("api down"),
            ),
        ):
            result = _get_anilist_progress(manga)

        assert result is None


class TestHandleDownloadEdgeCases:
    """Cover lines 490-491 (re-download all), 494-495 (all downloaded), 503-509 (on_failure)."""

    def _chapters(self):
        return [_chapter("1"), _chapter("2")]

    def test_redownload_all_option(self, tmp_path):
        """'🔄 Re-baixar todos' sets new_chapters = chapters_to_download (lines 490-491)."""
        from services.manga.read_orchestrator import handle_download_for_later
        from services.manga.download import BatchDownloadResult

        chapters = self._chapters()
        manga = _manga()
        history = MagicMock()
        history.get_last_chapter.return_value = None

        result = BatchDownloadResult(successful=2, failed_chapters=[])
        batch_calls = []
        fake_settings = _fake_manga_settings(tmp_path)
        fake_settings.manga.skip_already_downloaded = True

        with (
            patch("services.manga.read_orchestrator.prompt_download_range", return_value=chapters),
            patch(
                "services.manga.read_orchestrator.split_new_and_downloaded",
                return_value=([], chapters),
            ),
            patch(
                "services.manga.read_orchestrator.download_chapters_batch",
                side_effect=lambda ch, *a, **kw: batch_calls.append(ch) or result,
            ),
            patch("services.manga.read_orchestrator.resolve_parallelism", return_value=1),
            patch("services.manga.read_orchestrator.ui_bridge.show_info"),
            patch("models.config.settings", fake_settings),
        ):
            handle_download_for_later(
                _FakeService(),
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=chapters,
                menu=lambda o, t: "🔄 Re-baixar todos",
                progress=_noop_progress,
                prompt=lambda m: None,
            )

        # Should have downloaded all chapters (not empty)
        assert batch_calls
        assert batch_calls[0] == chapters

    def test_all_already_downloaded_shows_info(self, tmp_path):
        """All chapters downloaded and new_chapters empty shows info (lines 494-495)."""
        from services.manga.read_orchestrator import handle_download_for_later

        chapters = self._chapters()
        manga = _manga()
        history = MagicMock()
        history.get_last_chapter.return_value = None

        infos = []
        fake_settings = _fake_manga_settings(tmp_path)
        fake_settings.manga.skip_already_downloaded = False

        with (
            patch("services.manga.read_orchestrator.prompt_download_range", return_value=chapters),
            patch(
                "services.manga.read_orchestrator.split_new_and_downloaded",
                return_value=([], chapters),
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
            patch("models.config.settings", fake_settings),
        ):
            handle_download_for_later(
                _FakeService(),
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=chapters,
                menu=lambda o, t: None,
                progress=_noop_progress,
            )

        assert any("já estão baixados" in i for i in infos)


class TestSyncReadToAnilistEdgeCases:
    """Cover lines 635-636 (PLANNING status change) and 641-651 (auto delete)."""

    def test_planning_status_triggers_status_change(self, monkeypatch):
        """When list_entry status == 'PLANNING', change_manga_status is called (lines 635-636)."""
        from services.manga.read_orchestrator import _sync_read_to_anilist

        anilist_manga = SimpleNamespace(id=42)
        list_entry = SimpleNamespace(status="PLANNING")
        status_changes = []
        infos = []

        with (
            patch(
                "services.manga.read_orchestrator.anilist_client.is_authenticated",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.search_manga",
                return_value=[anilist_manga],
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.get_manga_list_entry",
                return_value=list_entry,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.update_manga_progress",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.change_manga_status",
                side_effect=lambda mid, s: status_changes.append(s),
            ),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
        ):
            _sync_read_to_anilist(
                _manga(),
                _chapter("5"),
                None,
                menu=lambda opts, title: "✅ Sim, li até o final",
            )

        assert status_changes, "change_manga_status should have been called"

    def test_auto_delete_chapter_on_completion(self, tmp_path):
        """When auto_delete_read_chapters=True and pdf exists, shutil.rmtree called (lines 641-648)."""
        from services.manga.read_orchestrator import _sync_read_to_anilist

        anilist_manga = SimpleNamespace(id=42)
        list_entry = SimpleNamespace(status="CURRENT")

        # Create a fake PDF dir
        pdf_path = tmp_path / "Test Manga" / "5" / "5.pdf"
        pdf_path.parent.mkdir(parents=True)
        pdf_path.write_bytes(b"pdf")

        infos = []
        fake_settings = _fake_manga_settings(tmp_path)
        fake_settings.manga.auto_delete_read_chapters = True

        with (
            patch(
                "services.manga.read_orchestrator.anilist_client.is_authenticated",
                return_value=True,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.search_manga",
                return_value=[anilist_manga],
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.get_manga_list_entry",
                return_value=list_entry,
            ),
            patch(
                "services.manga.read_orchestrator.anilist_client.update_manga_progress",
                return_value=True,
            ),
            patch("services.manga.read_orchestrator.anilist_client.change_manga_status"),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
            patch("models.config.settings", fake_settings),
        ):
            _sync_read_to_anilist(
                _manga(),
                _chapter("5"),
                pdf_path,
                menu=lambda opts, title: "✅ Sim, li até o final",
            )

        # The directory should have been deleted
        assert not pdf_path.parent.exists()
        assert any("deletado" in i for i in infos)


class TestProcessChapterZathura:
    """Cover lines 684-689 (Zathura wait loop)."""

    def test_waits_for_zathura_to_close(self, tmp_path):
        from services.manga.read_orchestrator import _process_chapter

        manga = _manga()
        ch1 = _chapter("1")
        chapters = [ch1]
        history = MagicMock()

        pdf = tmp_path / "1.pdf"
        pdf.write_bytes(b"pdf")

        zathura_calls = [0]

        def _fake_zathura():
            zathura_calls[0] += 1
            # First call True (running), then False (closed)
            return zathura_calls[0] <= 1

        infos = []

        with (
            patch("services.manga.read_orchestrator._prepare_chapter_pdf", return_value=pdf),
            patch("services.manga.read_orchestrator.open_pdf_reader"),
            patch("services.manga.read_orchestrator.is_zathura_running", side_effect=_fake_zathura),
            patch("services.manga.read_orchestrator._sync_read_to_anilist"),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_info",
                side_effect=lambda m: infos.append(m),
            ),
            patch("time.sleep"),
        ):  # don't actually sleep
            _process_chapter(
                _FakeService(),
                manga,
                ch1,
                None,
                "mangadex",
                history,
                chapters,
                ["Cap. 1"],
                0,
                menu=lambda o, t: None,
                progress=_noop_progress,
            )

        assert any("Zathura fechado" in i for i in infos)


class TestContinueMangaFlowEdgeCases:
    """Cover lines 285, 304-305, 322-335, 356, 363."""

    def test_resume_keyboard_interrupt_returns_early(self, monkeypatch):
        """KI on resume menu returns silently (lines 304-305)."""
        from services.manga.read_orchestrator import continue_manga_flow

        chapters = [_chapter("5")]
        service = _FakeService(chapters=chapters)
        manga = _manga()

        process_calls = []
        with (
            patch(
                "services.manga.read_orchestrator._select_source", return_value=("mangadex", manga)
            ),
            patch("services.manga.read_orchestrator._get_anilist_progress", return_value=4),
            patch("services.manga.read_orchestrator.MangaHistory") as mock_hist,
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value="mangadex",
            ),
            patch("services.manga.read_orchestrator.manga_source_preferences.set_preferred_source"),
            patch(
                "services.manga.read_orchestrator._process_chapter",
                side_effect=lambda *a, **kw: process_calls.append(1),
            ),
        ):
            mock_hist.return_value.get_last_chapter.return_value = None

            def _menu(opts, title):
                if "Retomar" in title:
                    raise KeyboardInterrupt
                return None

            continue_manga_flow(
                service, manga, allow_source_change=True, menu=_menu, progress=_noop_progress
            )

        assert not process_calls

    def test_resume_chapter_not_found_shows_fallback_warning(self, monkeypatch):
        """When resume chapter not found and fallback returns None, warning shown (line 356)."""
        from services.manga.read_orchestrator import continue_manga_flow

        # Chapter 5 in list but no url (so not found properly)
        chapters = [_chapter("5", url=None)]
        service = _FakeService(chapters=chapters)
        manga = _manga()

        warnings = []
        with (
            patch(
                "services.manga.read_orchestrator._select_source", return_value=("mangadex", manga)
            ),
            patch("services.manga.read_orchestrator._get_anilist_progress", return_value=4),
            patch("services.manga.read_orchestrator.MangaHistory") as mock_hist,
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value="mangadex",
            ),
            patch("services.manga.read_orchestrator.manga_source_preferences.set_preferred_source"),
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
            patch("services.manga.read_orchestrator.ui_bridge.show_info"),
            patch("services.manga.read_orchestrator.resume_from_other_source", return_value=None),
        ):
            mock_hist.return_value.get_last_chapter.return_value = None

            # Choose yes to resume
            def _menu(opts, title):
                if "Retomar" in title:
                    return next((o for o in opts if o.startswith("⮕ Sim")), None)
                return None

            continue_manga_flow(
                service, manga, allow_source_change=True, menu=_menu, progress=_noop_progress
            )

        assert any("não encontrado em nenhuma fonte" in w for w in warnings)

    def test_prefer_source_set_when_differs(self, monkeypatch):
        """If get_preferred_source != selected_source, set_preferred_source called (line 285)."""
        from services.manga.read_orchestrator import continue_manga_flow

        chapters = [_chapter("1")]
        service = _FakeService(chapters=chapters)
        manga = _manga()

        pref_set_calls = []
        with (
            patch(
                "services.manga.read_orchestrator._select_source", return_value=("mangadex", manga)
            ),
            patch("services.manga.read_orchestrator._get_anilist_progress", return_value=None),
            patch("services.manga.read_orchestrator.MangaHistory") as mock_hist,
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
                return_value="mugiwaras",
            ),
            patch(
                "services.manga.read_orchestrator.manga_source_preferences.set_preferred_source",
                side_effect=lambda t, s: pref_set_calls.append(s),
            ),
        ):
            mock_hist.return_value.get_last_chapter.return_value = None

            continue_manga_flow(
                service,
                manga,
                allow_source_change=True,
                menu=lambda o, t: None,
                progress=_noop_progress,
            )

        assert "mangadex" in pref_set_calls


class TestHandleDownloadErrorAndParallel:
    """Cover lines 459-461 (error loading chapters=None), 503-509 (_on_failure callback),
    523-532 (parallel path with tqdm), 591-594 (delete images after pdf)."""

    def test_error_loading_chapters_when_none_shows_warning(self, tmp_path):
        """When chapters=None and get_chapters raises, show warning (lines 459-461)."""
        from services.manga.read_orchestrator import handle_download_for_later

        service = _FakeService(raise_on_chapters=RuntimeError("network error"))
        manga = _manga()
        history = MagicMock()

        warnings = []
        fake_settings = _fake_manga_settings(tmp_path)

        with (
            patch(
                "services.manga.read_orchestrator.ui_bridge.show_warning",
                side_effect=lambda m: warnings.append(m),
            ),
            patch("models.config.settings", fake_settings),
        ):
            handle_download_for_later(
                service,
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=None,
                menu=lambda o, t: None,
                progress=_noop_progress,
            )

        assert any("Erro ao carregar" in w for w in warnings)

    def test_on_failure_callback_returns_true(self, tmp_path):
        """_on_failure callback when menu returns '✅ Continuar' returns True (lines 503-509)."""
        from services.manga.read_orchestrator import handle_download_for_later
        from services.manga.download import BatchDownloadResult

        chapters = [_chapter("1")]
        manga = _manga()
        history = MagicMock()
        history.get_last_chapter.return_value = None

        result = BatchDownloadResult(successful=1, failed_chapters=[])
        captured_on_failure = [None]

        def _capture_batch(
            chaps,
            svc,
            manga,
            url,
            src,
            cfg,
            tracker,
            max_parallel=1,
            on_failure=None,
            on_progress=None,
        ):
            captured_on_failure[0] = on_failure
            return result

        fake_settings = _fake_manga_settings(tmp_path)

        with (
            patch("services.manga.read_orchestrator.prompt_download_range", return_value=chapters),
            patch(
                "services.manga.read_orchestrator.split_new_and_downloaded",
                return_value=(chapters, []),
            ),
            patch(
                "services.manga.read_orchestrator.download_chapters_batch",
                side_effect=_capture_batch,
            ),
            patch("services.manga.read_orchestrator.resolve_parallelism", return_value=1),
            patch("services.manga.read_orchestrator.ui_bridge.show_info"),
            patch("models.config.settings", fake_settings),
        ):
            handle_download_for_later(
                _FakeService(),
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=chapters,
                menu=lambda o, t: "✅ Continuar",
                progress=_noop_progress,
                prompt=lambda m: None,
            )

        # Now invoke the captured callback to test it
        assert captured_on_failure[0] is not None
        assert captured_on_failure[0]("some error") is True

    def test_on_failure_callback_returns_false_on_exception(self, tmp_path):
        """_on_failure raises Exception in menu -> returns False (line 508-509)."""
        from services.manga.read_orchestrator import handle_download_for_later
        from services.manga.download import BatchDownloadResult

        chapters = [_chapter("1")]
        manga = _manga()
        history = MagicMock()
        history.get_last_chapter.return_value = None

        result = BatchDownloadResult(successful=1, failed_chapters=[])
        captured_on_failure = [None]

        def _capture_batch(
            chaps,
            svc,
            manga,
            url,
            src,
            cfg,
            tracker,
            max_parallel=1,
            on_failure=None,
            on_progress=None,
        ):
            captured_on_failure[0] = on_failure
            return result

        fake_settings = _fake_manga_settings(tmp_path)

        with (
            patch("services.manga.read_orchestrator.prompt_download_range", return_value=chapters),
            patch(
                "services.manga.read_orchestrator.split_new_and_downloaded",
                return_value=(chapters, []),
            ),
            patch(
                "services.manga.read_orchestrator.download_chapters_batch",
                side_effect=_capture_batch,
            ),
            patch("services.manga.read_orchestrator.resolve_parallelism", return_value=1),
            patch("services.manga.read_orchestrator.ui_bridge.show_info"),
            patch("models.config.settings", fake_settings),
        ):
            handle_download_for_later(
                _FakeService(),
                manga,
                _chapter("1"),
                None,
                "mangadex",
                history,
                chapters=chapters,
                menu=lambda o, t: (_ for _ in ()).throw(RuntimeError("boom")),
                progress=_noop_progress,
                prompt=lambda m: None,
            )

        assert captured_on_failure[0] is not None
        assert captured_on_failure[0]("err") is False

    def test_delete_images_after_pdf_created(self, tmp_path):
        """When delete_images_after_pdf=True, image files removed (lines 591-594)."""
        from services.manga.read_orchestrator import _prepare_chapter_pdf

        manga = _manga()
        chapter = _chapter("7", url="http://img/1.jpg")
        service = _FakeService(pages=["http://img/1.jpg"])

        # Create an image file that should be deleted
        output_path = tmp_path / manga.title / chapter.number
        output_path.mkdir(parents=True)
        img_file = output_path / "001.jpg"
        img_file.write_bytes(b"img")

        def _create_pdf(out_dir, pdf_path, quality):
            pdf_path.write_bytes(b"pdf")

        with (
            patch("models.config.settings", _fake_manga_settings(tmp_path, delete_images=True)),
            patch("services.manga.read_orchestrator._download_images"),
            patch(
                "services.manga.read_orchestrator.create_pdf_from_images", side_effect=_create_pdf
            ),
        ):
            result = _prepare_chapter_pdf(manga, chapter, "mangadex", service, _noop_progress)

        # PDF returned, image cleaned up
        assert result is not None
        assert not img_file.exists()

    def test_select_source_returns_current_when_read_selected(self, monkeypatch):
        """'📖 Ler com <source>' action returns current_source unchanged (line 201)."""
        from services.manga.read_orchestrator import _select_source

        service = _FakeService(sources=["mangadex", "mugiwaras"])
        manga = _manga("Test", sources={"mangadex": "m1", "mugiwaras": "m2"})

        with patch(
            "services.manga.read_orchestrator.manga_source_preferences.get_preferred_source",
            return_value=None,
        ):
            chosen, updated = _select_source(
                service,
                manga,
                "mangadex",
                menu=lambda opts, title: "📖 Ler com mangadex",
                progress=_noop_progress,
            )

        assert chosen == "mangadex"
        assert updated is manga
        # Should return without raising
