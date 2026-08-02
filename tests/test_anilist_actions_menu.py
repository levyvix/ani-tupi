"""Tests for the AniList per-anime actions menu and its helpers."""

import builtins
from argparse import Namespace
from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

import commands.anilist as cmd
import services.anilist.client as svc_anilist
import services.anime.download_service as dl_service
import ui.anilist_menus as menus
from models.models import Status
from utils.range_parser import RangeParseError


class TestWireAnilistMenus:
    """The command layer injects real deps into the pure ui layer."""

    def test_wiring_populates_menu_holders(self):
        cmd._wire_anilist_menus()

        # ui must never import services/commands; deps arrive via configure().
        assert menus.anilist_client is not None
        assert menus.run_anime_actions is cmd.run_anime_actions
        assert callable(menus.airing_service_factory)
        assert callable(menus.handle_local_library_playback)
        assert callable(menus.anilist_anime_flow)


@pytest.fixture
def anime_info():
    """Fake AniList anime info object."""
    info = Mock()
    info.title = Mock()
    info.episodes = 12
    return info


def _make_client(authenticated=True):
    client = Mock()
    client.is_authenticated.return_value = authenticated
    client.format_title.return_value = "Cool Anime"
    entry = Mock()
    entry.progress = 3
    client.get_media_list_entry.return_value = entry
    client.change_status.return_value = True
    return client


def _make_download_service():
    """Fake external AnimeDownloadService (network/filesystem boundary)."""
    service = Mock()
    result = Mock()
    result.summary = "2 baixados"
    service.download_episodes.return_value = result
    return service


# Menu labels exposed by the real ``ui.anilist_menus`` action menu. Selecting
# these via the (mocked) input boundary drives the real ``action_map`` routing
# instead of substituting the module's own routing helper.
_ACTION_LABELS = {
    "watch": "▶️  Assistir agora",
    "download": "📥 Baixar",
    "status": "🔄 Mudar status",
    "open": "🌐 Abrir página no AniList",
}


class TestActionLoop:
    """Task 5.1: action loop routes each option; None returns to list.

    Real integration: the true ``run_anime_actions`` loop, the real
    ``anime_actions_menu`` (via the mocked ``menu_navigate`` input boundary),
    and the real internal handlers (``_handle_anilist_download`` /
    ``_handle_status_change``) all execute. Only genuine external boundaries
    are faked: the AniList HTTP client, the playback service, the download
    service, ``webbrowser``, and terminal input/menu selection.
    """

    @contextmanager
    def _run(self, actions, client, anime_info):
        """Drive the real ``anilist_menu`` action loop for one selected anime.

        Yields ``(watch_mock, browser_mock)``. The real ``run_anime_actions``
        loop, the real ``anime_actions_menu`` (via the mocked ``menu_navigate``
        input boundary) and the real internal handlers all execute. The context
        manager form lets individual tests layer additional external-boundary
        fakes (download service, ``status_select_menu``) around the run.

        Args:
            actions: sequence of action keys ("watch"/"download"/"status"/
                "open") or ``None`` (ESC); mapped to real menu labels and fed
                to ``menu_navigate``.
            client: fake AniList client (external boundary).
            anime_info: fake AniList anime info returned by the client.
        """
        client.get_anime_by_id.return_value = anime_info

        # Translate action keys into the real menu labels; None stays None (ESC).
        action_selections = [_ACTION_LABELS[a] if a is not None else None for a in actions]
        # anilist_main_menu is a pure UI selector (defined in ui.anilist_menus,
        # not the module under test); keep it patched to select one anime, then
        # let the real action loop run against the real menus/handlers.
        with (
            patch.object(svc_anilist, "anilist_client", client),
            patch.object(cmd, "anilist_main_menu", side_effect=[("cool anime", 42), None]),
            patch.object(menus, "menu_navigate", side_effect=action_selections),
            patch.object(cmd, "anilist_anime_flow") as watch,
            patch.object(cmd, "pause"),
            patch.object(cmd, "webbrowser") as browser,
        ):
            cmd.anilist_menu(Namespace(debug=False))
            yield watch, browser

    def test_watch_is_terminal(self, anime_info):
        client = _make_client()
        with self._run(["watch"], client, anime_info) as (watch, _browser):
            pass
        watch.assert_called_once()

    def test_download_then_back(self, anime_info):
        client = _make_client()
        service = _make_download_service()
        with (
            patch.object(dl_service, "AnimeDownloadService", return_value=service),
            patch.object(builtins, "input", return_value="1-2"),
            self._run(["download", None], client, anime_info) as (watch, _browser),
        ):
            pass
        # Real _handle_anilist_download ran and invoked the download service
        # with the anime title and total episodes taken from the AniList client.
        service.download_episodes.assert_called_once()
        kwargs = service.download_episodes.call_args.kwargs
        assert kwargs["anime_title"] == "cool anime"
        assert kwargs["total_episodes"] == 12
        watch.assert_not_called()

    def test_status_then_back(self, anime_info):
        client = _make_client()
        client.change_status.return_value = True
        with (
            patch.object(cmd, "status_select_menu", return_value=Status.PAUSED),
            self._run(["status", None], client, anime_info),
        ):
            pass
        # Real _handle_status_change ran and called the external client.
        client.change_status.assert_called_once_with(42, Status.PAUSED)

    def test_open_then_back(self, anime_info):
        client = _make_client()
        with self._run(["open", None], client, anime_info) as (_watch, browser):
            pass
        browser.open_new_tab.assert_called_once_with("https://anilist.co/anime/42")

    def test_none_returns_to_list(self, anime_info):
        client = _make_client()
        with self._run([None], client, anime_info) as (watch, _browser):
            pass
        watch.assert_not_called()
        client.change_status.assert_not_called()


class TestHandleStatusChange:
    """Task 5.2: status change helper (mock external client only)."""

    def test_success(self):
        client = Mock()
        client.is_authenticated.return_value = True
        client.change_status.return_value = True
        with (
            patch("services.anilist.client.anilist_client", client),
            patch.object(cmd, "status_select_menu", return_value=Status.PAUSED),
            patch.object(cmd, "pause"),
            patch.object(cmd, "show_success") as ok,
        ):
            cmd._handle_status_change(42)
        client.change_status.assert_called_once_with(42, Status.PAUSED)
        ok.assert_called_once()

    def test_api_failure(self):
        client = Mock()
        client.is_authenticated.return_value = True
        client.change_status.return_value = False
        with (
            patch("services.anilist.client.anilist_client", client),
            patch.object(cmd, "status_select_menu", return_value=Status.DROPPED),
            patch.object(cmd, "pause"),
            patch.object(cmd, "show_error") as err,
        ):
            cmd._handle_status_change(42)
        err.assert_called_once()

    def test_not_authenticated(self):
        client = Mock()
        client.is_authenticated.return_value = False
        with (
            patch("services.anilist.client.anilist_client", client),
            patch.object(cmd, "pause"),
            patch.object(cmd, "show_warning") as warn,
        ):
            cmd._handle_status_change(42)
        warn.assert_called_once()
        client.change_status.assert_not_called()

    def test_esc_submenu(self):
        client = Mock()
        client.is_authenticated.return_value = True
        with (
            patch("services.anilist.client.anilist_client", client),
            patch.object(cmd, "status_select_menu", return_value=None),
        ):
            cmd._handle_status_change(42)
        client.change_status.assert_not_called()


class TestHandleDownload:
    """Task 5.3: download helper (mock external download service only)."""

    def test_valid_range(self):
        service = Mock()
        result = Mock()
        result.summary = "2 baixados"
        service.download_episodes.return_value = result
        with (
            patch("services.anime.download_service.AnimeDownloadService", return_value=service),
            patch("builtins.input", return_value="1-2"),
            patch.object(cmd, "pause"),
            patch.object(cmd, "show_info") as info,
        ):
            cmd._handle_anilist_download("cool anime", 12)
        service.download_episodes.assert_called_once()
        info.assert_called_once()

    def test_range_parse_error(self):
        service = Mock()
        service.download_episodes.side_effect = RangeParseError("bad")
        with (
            patch("services.anime.download_service.AnimeDownloadService", return_value=service),
            patch("builtins.input", return_value="99-1"),
            patch.object(cmd, "pause"),
            patch.object(cmd, "show_error") as err,
        ):
            cmd._handle_anilist_download("cool anime", 12)
        err.assert_called_once()

    def test_total_episodes_none(self):
        with (
            patch("builtins.input") as inp,
            patch.object(cmd, "pause"),
            patch.object(cmd, "show_warning") as warn,
        ):
            cmd._handle_anilist_download("cool anime", None)
        warn.assert_called_once()
        inp.assert_not_called()
