"""Tests for the AniList per-anime actions menu and its helpers."""

from argparse import Namespace
from unittest.mock import Mock, patch

import pytest

import commands.anilist as cmd
from models.models import Status
from utils.episode_range_parser import RangeParseError


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
    return client


class TestActionLoop:
    """Task 5.1: action loop routes each option; None returns to list."""

    def _run(self, actions, client, anime_info):
        """Run anilist_menu with a mocked main menu and action sequence.

        The main menu yields one anime then exits; anime_actions_menu yields
        the provided actions in order.
        """
        client.get_anime_by_id.return_value = anime_info
        with (
            patch("services.anilist_service.anilist_client", client),
            patch.object(cmd, "anilist_main_menu", side_effect=[("cool anime", 42), None]),
            patch.object(cmd, "anime_actions_menu", side_effect=actions),
            patch.object(cmd.anime_service, "anilist_anime_flow") as watch,
            patch.object(cmd, "_handle_anilist_download") as download,
            patch.object(cmd, "_handle_status_change") as status,
            patch.object(cmd, "webbrowser") as browser,
        ):
            cmd.anilist_menu(Namespace(debug=False))
        return watch, download, status, browser

    def test_watch_is_terminal(self, anime_info):
        client = _make_client()
        watch, download, status, browser = self._run(["watch"], client, anime_info)
        watch.assert_called_once()
        download.assert_not_called()

    def test_download_then_back(self, anime_info):
        client = _make_client()
        watch, download, status, browser = self._run(["download", None], client, anime_info)
        download.assert_called_once_with("cool anime", 12)
        watch.assert_not_called()

    def test_status_then_back(self, anime_info):
        client = _make_client()
        watch, download, status, browser = self._run(["status", None], client, anime_info)
        status.assert_called_once_with(42)

    def test_open_then_back(self, anime_info):
        client = _make_client()
        watch, download, status, browser = self._run(["open", None], client, anime_info)
        browser.open_new_tab.assert_called_once_with("https://anilist.co/anime/42")

    def test_none_returns_to_list(self, anime_info):
        client = _make_client()
        watch, download, status, browser = self._run([None], client, anime_info)
        watch.assert_not_called()
        download.assert_not_called()
        status.assert_not_called()


class TestHandleStatusChange:
    """Task 5.2: status change helper (mock external client only)."""

    def test_success(self):
        client = Mock()
        client.is_authenticated.return_value = True
        client.change_status.return_value = True
        with (
            patch("services.anilist_service.anilist_client", client),
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
            patch("services.anilist_service.anilist_client", client),
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
            patch("services.anilist_service.anilist_client", client),
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
            patch("services.anilist_service.anilist_client", client),
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
            patch(
                "services.anime.download_service.AnimeDownloadService",
                return_value=service,
            ),
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
            patch(
                "services.anime.download_service.AnimeDownloadService",
                return_value=service,
            ),
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
