"""Tests for the dependency-inverted ``ui.anilist_menus`` layer.

These tests verify that the now-pure UI render/navigation functions invoke the
INJECTED callbacks (``run_anime_actions``, ``airing_service_factory``,
``handle_local_library_playback``) with the right selection, given fixed data
and fake callbacks. External boundaries (AniList client, cache) are the only
things faked; the render/navigation logic runs for real.
"""

from unittest.mock import Mock, patch

import pytest

import ui.anilist.airing_menu as airing_menu
import ui.anilist_menus as menus
from models.models import AiringAnimeEntry, AniListAnime, AniListTitle


@pytest.fixture
def restore_menus_state():
    """Snapshot and restore module-level DI holders around each test."""
    saved_menus = (
        menus.anilist_client,
        menus.anilist_anime_flow,
        menus.run_anime_actions,
        menus.airing_service_factory,
        menus.handle_local_library_playback,
    )
    saved_airing = (
        airing_menu.anilist_client,
        airing_menu.airing_service_factory,
        airing_menu.run_anime_actions,
    )
    yield
    (
        menus.anilist_client,
        menus.anilist_anime_flow,
        menus.run_anime_actions,
        menus.airing_service_factory,
        menus.handle_local_library_playback,
    ) = saved_menus
    (
        airing_menu.anilist_client,
        airing_menu.airing_service_factory,
        airing_menu.run_anime_actions,
    ) = saved_airing


class TestConfigure:
    """configure() wires every runtime dependency onto the module."""

    def test_configure_sets_all_holders(self, restore_menus_state):
        client = Mock()
        flow = Mock()
        actions = Mock()
        factory = Mock()
        local = Mock()

        menus.configure(
            client=client,
            anime_flow=flow,
            anime_actions=actions,
            airing_service=factory,
            local_library_playback=local,
        )

        assert menus.anilist_client is client
        assert menus.anilist_anime_flow is flow
        assert menus.run_anime_actions is actions
        assert menus.airing_service_factory is factory
        assert menus.handle_local_library_playback is local


class TestShowAnimeListInvokesCallback:
    """_show_anime_list renders a user list and delegates to run_anime_actions."""

    def test_selection_calls_run_anime_actions(self, restore_menus_state):
        client = Mock()
        client.get_user_list.return_value = [
            AniListAnime(
                id=42,
                title=AniListTitle(romaji="Cool Anime", english="Cool Anime"),
                episodes=12,
                averageScore=90,
            )
        ]
        client.format_title.return_value = "Cool Anime"

        actions = Mock()
        menus.anilist_client = client
        menus.run_anime_actions = actions

        # First menu_navigate returns the anime; then None ends the list loop.
        # anilist_main_menu is stubbed so the recursive return does nothing.
        with (
            patch.object(
                menus,
                "menu_navigate",
                side_effect=[
                    "Cool Anime (12 eps) ⭐90%",
                    None,
                ],
            ),
            patch.object(menus, "anilist_main_menu", return_value=None),
            patch.object(menus, "loading"),
        ):
            menus._show_anime_list("CURRENT")

        actions.assert_called_once()
        call = actions.call_args
        assert call[0][0] == "Cool Anime"  # search_title
        assert call[0][1] == 42  # anilist_id
        assert call[1]["display_title"] == "Cool Anime"
        assert call[1]["total_episodes"] == 12


class TestAiringEpisodesInvokesFactoryAndCallback:
    """_show_airing_episodes uses the injected factory + run_anime_actions."""

    def test_selection_calls_run_anime_actions(self, restore_menus_state):
        entry = AiringAnimeEntry(
            anilist_id=7,
            title="Airing Anime",
            progress=3,
            next_episode_number=5,
            episodes_behind=1,
            airing_at=None,
            average_score=80,
        )
        service = Mock()
        service.get_watching_with_airing_episodes.return_value = [entry]
        factory = Mock(return_value=service)

        client = Mock()
        anime_info = AniListAnime(
            id=7,
            title=AniListTitle(romaji="Airing Anime", english="Airing Anime"),
            episodes=5,
        )
        client.get_anime_by_id.return_value = anime_info
        client.format_title.return_value = "Airing Anime"

        actions = Mock()
        # show_airing_episodes lives in ui.anilist.airing_menu; set DI there
        airing_menu.anilist_client = client
        airing_menu.airing_service_factory = factory
        airing_menu.run_anime_actions = actions

        # display string built for a finished-anime entry (airing_at is None)
        display = "(1 atrasado) Airing Anime - Anime finalizado, você viu 3/5 ⭐80%"
        with (
            patch.object(airing_menu, "menu_navigate", side_effect=[display, None]),
            patch.object(airing_menu, "loading"),
        ):
            menus.show_airing_episodes()

        factory.assert_called()
        actions.assert_called_once()
        call = actions.call_args
        assert call[0][0] == "Airing Anime"  # search_title
        assert call[0][1] == 7  # anilist_id
        assert call[1]["anilist_progress"] == 3
        assert call[1]["total_episodes"] == 5


class TestLocalLibraryDelegates:
    """_show_local_library delegates to the injected local playback callback."""

    def test_calls_injected_handler(self, restore_menus_state):
        handler = Mock()
        menus.handle_local_library_playback = handler

        menus._show_local_library()

        handler.assert_called_once()
        # It receives an args namespace with debug=False.
        (args,) = handler.call_args[0]
        assert args.debug is False
