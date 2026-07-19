"""Extended coverage tests for services/history_service.py.

Covers the paths not exercised by tests/test_history_service.py:
- _load_persisted_history: menu selection parsing, ep_info formatting
- _resolve_anilist_progress: anilist_id branch, local-source fallback
- _validate_anime_sources: single valid source, multi-source, no valid sources
- _find_episodes: saved_urls path, anilist cache path, local-source path,
  single-result search path, multi-result path
- _pick_episode: next/current/previous/chooser/reset options
- load_history: full happy path, not-found path, manual-search path,
  remove-from-history path
- save_history: auto-derives total_episodes from repo
- save_history_from_event: with AniList sync

Strategy (matches project CLAUDE.md):
- Monkeypatch services.history_service._history_store to a real JSONStore in tmp
- Patch ui_bridge callables (menu_navigate, loading, prompt, menu_navigate_episodes)
- Mock only external AniList HTTP boundary
- Real Repository and real JSONStore
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from utils.persistence import JSONStore


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def history_store(tmp_path):
    """Real JSONStore in a temp directory."""
    return JSONStore(tmp_path / "history.json")


@pytest.fixture(autouse=True)
def patch_history_store(history_store):
    """Redirect module-level _history_store to temp store for every test."""
    with patch("services.history_service._history_store", history_store):
        yield history_store


@pytest.fixture()
def history_repository(repository, monkeypatch):
    """Bind history_service.rep to the real isolated Repository fixture."""
    import services.history_service as hs

    monkeypatch.setattr(hs, "rep", repository)
    return repository


def noop_loading(msg=""):
    """Synchronous fake for ui_bridge.loading context manager."""

    @contextmanager
    def _cm(msg=msg):
        yield

    return _cm(msg)


def make_loading():
    """Return a callable that acts as ui_bridge.loading(msg) -> context manager."""

    @contextmanager
    def loading(msg=""):
        yield

    return loading


class UnauthAniList:
    @staticmethod
    def is_authenticated():
        return False


# ---------------------------------------------------------------------------
# _load_persisted_history
# ---------------------------------------------------------------------------


class TestLoadPersistedHistory:
    """Tests for the internal _load_persisted_history helper."""

    def test_returns_none_when_menu_cancelled(self, history_store):
        from services.history_service import _load_persisted_history, save_history

        save_history("Naruto", 0)
        result = _load_persisted_history(menu=lambda items, msg="": None)
        assert result is None

    def test_returns_entry_on_selection(self, history_store):
        from services.history_service import _load_persisted_history, save_history

        save_history("Bleach", 5, total_episodes=10)

        captured_items = []

        def fake_menu(items, msg=""):
            captured_items.extend(items)
            return items[0]  # pick first item

        result = _load_persisted_history(menu=fake_menu)
        assert result is not None
        _, anime, ep_idx, _, _, _ = result
        assert anime == "Bleach"
        assert ep_idx == 5

    def test_ep_info_with_total_episodes(self, history_store):
        """Format includes X/total when total_episodes is set."""
        from services.history_service import _load_persisted_history, save_history

        save_history("One Piece", 3, total_episodes=20)

        menu_items = []

        def fake_menu(items, msg=""):
            menu_items.extend(items)
            return items[0]

        _load_persisted_history(menu=fake_menu)
        # The menu item should contain "4/20"
        assert any("4/20" in item for item in menu_items)

    def test_ep_info_without_total_episodes(self, history_store):
        """Format uses 'Ep N' when total_episodes is None."""
        from services.history_service import _load_persisted_history, save_history

        save_history("HxH", 10)

        menu_items = []

        def fake_menu(items, msg=""):
            menu_items.extend(items)
            return items[0]

        _load_persisted_history(menu=fake_menu)
        assert any("Ep 11" in item for item in menu_items)


# ---------------------------------------------------------------------------
# _resolve_anilist_progress
# ---------------------------------------------------------------------------


class TestResolveAnilistProgress:
    """Tests for _resolve_anilist_progress."""

    def test_returns_minus_one_when_no_anilist_id(self):
        from services.history_service import _resolve_anilist_progress

        aid, title, ep_idx = _resolve_anilist_progress(
            None, "scraper", "My Anime", progress=make_loading()
        )
        assert aid is None
        assert title is None
        assert ep_idx == -1

    def test_fetches_progress_when_anilist_id_provided(self, monkeypatch):
        from services.history_service import _resolve_anilist_progress

        fake_info = MagicMock()
        fake_info.title.romaji = "Test Anime"
        fake_entry = MagicMock()
        fake_entry.progress = 5

        fake_client = MagicMock()
        fake_client.get_anime_by_id.return_value = fake_info
        fake_client.get_media_list_entry.return_value = fake_entry

        import services.anilist as anilist_mod

        monkeypatch.setattr(anilist_mod, "anilist_client", fake_client)

        aid, title, ep_idx = _resolve_anilist_progress(
            123, "animefire", "Test Anime", progress=make_loading()
        )

        assert aid == 123
        assert title == "Test Anime"
        assert ep_idx == 4  # progress - 1

    def test_no_progress_returns_minus_one(self, monkeypatch):
        from services.history_service import _resolve_anilist_progress

        fake_client = MagicMock()
        fake_client.get_anime_by_id.return_value = None
        fake_client.get_media_list_entry.return_value = None

        import services.anilist as anilist_mod

        monkeypatch.setattr(anilist_mod, "anilist_client", fake_client)

        aid, title, ep_idx = _resolve_anilist_progress(
            456, "animefire", "Test Anime", progress=make_loading()
        )

        assert ep_idx == -1


# ---------------------------------------------------------------------------
# _validate_anime_sources
# ---------------------------------------------------------------------------


class TestValidateAnimeSources:
    """Tests for _validate_anime_sources."""

    def test_no_valid_sources_returns_none_empty(self, history_repository):
        from services.history_service import _validate_anime_sources

        # SearchResults with no sources that return episodes
        search_results = MagicMock()
        search_results.get_anime_titles_with_sources.return_value = []

        title, eps = _validate_anime_sources(
            search_results,
            menu=lambda items, msg="": None,
            progress=make_loading(),
        )
        assert title is None
        assert eps == []

    def test_single_valid_source_returns_without_menu(self, history_repository):
        from services.history_service import _validate_anime_sources

        # Mock rep.search_episodes and rep.get_episode_list
        import services.history_service as hs

        episode_mock = [MagicMock(number=1), MagicMock(number=2)]
        hs.rep.get_episode_list = MagicMock(return_value=episode_mock)
        hs.rep.search_episodes = MagicMock()

        search_results = MagicMock()
        search_results.get_anime_titles_with_sources.return_value = ["Dragon Ball [src]"]

        menu_called = []

        def fail_menu(items, msg=""):
            menu_called.append(items)
            return None

        title, eps = _validate_anime_sources(
            search_results,
            menu=fail_menu,
            progress=make_loading(),
        )
        # Single source: menu should NOT be called
        assert not menu_called
        assert title == "Dragon Ball"
        assert eps is episode_mock

    def test_multiple_sources_shows_menu(self, history_repository):
        from services.history_service import _validate_anime_sources, _RETRY
        import services.history_service as hs

        episode_mock = [MagicMock(number=1)]
        hs.rep.get_episode_list = MagicMock(return_value=episode_mock)
        hs.rep.search_episodes = MagicMock()

        search_results = MagicMock()
        search_results.get_anime_titles_with_sources.return_value = [
            "SAO [src1]",
            "SAO [src2]",
        ]

        # Cancel the menu → _RETRY
        title, eps = _validate_anime_sources(
            search_results,
            menu=lambda items, msg="": None,
            progress=make_loading(),
        )
        assert title is _RETRY
        assert eps is None


# ---------------------------------------------------------------------------
# _pick_episode
# ---------------------------------------------------------------------------


class TestPickEpisode:
    """Tests for _pick_episode helper."""

    def _episodes(self, n=5):
        return [MagicMock(number=i + 1) for i in range(n)]

    def test_pick_next_episode(self):
        from services.history_service import _pick_episode

        episodes = self._episodes(5)

        def fake_menu(items, msg=""):
            # Pick the "next" option (first in list)
            return items[0]

        result = _pick_episode(
            "Naruto",
            episodes,
            last_ep_idx=1,
            progress_source="Local",
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            prompt=lambda msg: "",
        )
        assert result == 2  # next episode index

    def test_pick_current_episode(self):
        from services.history_service import _pick_episode

        episodes = self._episodes(5)

        def fake_menu(items, msg=""):
            # Second item is current episode
            return items[1]

        result = _pick_episode(
            "Naruto",
            episodes,
            last_ep_idx=2,
            progress_source="Local",
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            prompt=lambda msg: "",
        )
        assert result == 2

    def test_pick_previous_episode(self):
        from services.history_service import _pick_episode

        episodes = self._episodes(5)

        def fake_menu(items, msg=""):
            # Third item is previous episode (when last_ep_idx > 0)
            return items[2]

        result = _pick_episode(
            "Naruto",
            episodes,
            last_ep_idx=2,
            progress_source="Local",
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            prompt=lambda msg: "",
        )
        assert result == 1

    def test_pick_choose_another_episode(self):
        from services.history_service import _pick_episode

        episodes = self._episodes(5)

        def fake_menu(items, msg=""):
            return "📋 Escolher outro episódio"

        result = _pick_episode(
            "Naruto",
            episodes,
            last_ep_idx=2,
            progress_source="Local",
            menu=fake_menu,
            menu_episodes=lambda eps: 3,
            prompt=lambda msg: "",
        )
        assert result == 3

    def test_reset_history_confirmed(self, history_store):
        from services.history_service import _pick_episode, save_history

        save_history("FMA", 5)
        episodes = self._episodes(10)
        call_count = [0]

        def fake_menu(items, msg=""):
            call_count[0] += 1
            if call_count[0] == 1:
                return "🔄 Começar do zero"
            return "✅ Sim, resetar"

        result = _pick_episode(
            "FMA",
            episodes,
            last_ep_idx=5,
            progress_source="Local",
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            prompt=lambda msg: "",
        )
        assert result == 0

    def test_reset_history_cancelled(self, history_store):
        from services.history_service import _pick_episode, save_history

        save_history("FMA", 5)
        episodes = self._episodes(10)
        call_count = [0]

        def fake_menu(items, msg=""):
            call_count[0] += 1
            if call_count[0] == 1:
                return "🔄 Começar do zero"
            return "❌ Cancelar"

        result = _pick_episode(
            "FMA",
            episodes,
            last_ep_idx=5,
            progress_source="Local",
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            prompt=lambda msg: "",
        )
        assert result is None

    def test_cancelled_menu_returns_none(self):
        from services.history_service import _pick_episode

        episodes = self._episodes(5)
        result = _pick_episode(
            "Naruto",
            episodes,
            last_ep_idx=2,
            progress_source="Local",
            menu=lambda items, msg="": None,
            menu_episodes=lambda eps: 0,
            prompt=lambda msg: "",
        )
        assert result is None

    def test_awaiting_episode_prompts_and_returns_none(self):
        """Selecting 'next' when at last episode prompts user and returns None."""
        from services.history_service import _pick_episode

        episodes = self._episodes(3)

        def fake_menu(items, msg=""):
            # At last episode, first option is "aguardando"
            return items[0]

        prompted = []
        result = _pick_episode(
            "Naruto",
            episodes,
            last_ep_idx=2,
            progress_source="Local",
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            prompt=lambda msg: prompted.append(msg) or "",
        )
        assert result is None
        assert prompted  # prompt was called


# ---------------------------------------------------------------------------
# load_history – happy path with episodes
# ---------------------------------------------------------------------------


class TestLoadHistoryHappyPath:
    """load_history returns correct tuple when everything succeeds."""

    def test_happy_path_local_episodes(self, history_store, history_repository, monkeypatch):
        """load_history returns (anime, ep_idx, anilist_id, anilist_title) on success."""
        from services.history_service import load_history, save_history
        import services.history_service as hs

        save_history("Cowboy Bebop", 2, source="testscr", total_episodes=26)

        # Provide episode list via repository
        history_repository.add_episode_list(
            "Cowboy Bebop",
            [f"Ep {i}" for i in range(1, 27)],
            [f"https://example.test/cowboy-bebop/{i}" for i in range(1, 27)],
            "testscr",
        )
        history_repository.add_anime("Cowboy Bebop", "https://example.test/cowboy-bebop", "testscr")

        # Patch _find_episodes to return episode list directly (skip scraper search)
        ep_list = history_repository.get_episode_list("Cowboy Bebop")
        monkeypatch.setattr(
            hs,
            "_find_episodes",
            lambda *a, **kw: ("Cowboy Bebop", ep_list, False, True),
        )

        call_count = [0]

        def fake_menu(items, msg=""):
            call_count[0] += 1
            if call_count[0] == 1:
                # History menu — pick the first item
                return items[0] if items else None
            # Episode picker — pick "current"
            for item in items:
                if "▶️" in item:
                    return item
            return items[0]

        result = load_history(
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            progress=make_loading(),
            prompt=lambda msg: "",
        )

        assert result is not None
        anime, ep_idx, anilist_id, anilist_title = result
        assert anime == "Cowboy Bebop"
        assert isinstance(ep_idx, int)


# ---------------------------------------------------------------------------
# load_history – not-found flow
# ---------------------------------------------------------------------------


class TestLoadHistoryNotFound:
    """load_history handles anime not found in scrapers."""

    def test_remove_from_history(self, history_store, history_repository, monkeypatch):
        """Choosing 'remove from history' deletes the entry."""
        from services.history_service import load_history, save_history
        import services.history_service as hs

        save_history("Ghost In The Shell", 3, source="scraper")

        monkeypatch.setattr(
            hs,
            "_find_episodes",
            lambda *a, **kw: ("Ghost In The Shell", [], True, False),
        )

        call_count = [0]
        prompted = []

        def fake_menu(items, msg=""):
            call_count[0] += 1
            if call_count[0] == 1:
                # History selection
                return items[0] if items else None
            # Not-found options menu: pick "remove"
            for item in items:
                if "Remover" in item:
                    return item
            return None

        result = load_history(
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            progress=make_loading(),
            prompt=lambda msg: prompted.append(msg) or "",
        )

        # After removing, loop continues but empty history → None
        assert result is None
        # Entry should be gone from store
        assert "Ghost In The Shell" not in history_store.load({})

    def test_back_to_menu_continues_loop(self, history_store, history_repository, monkeypatch):
        """Choosing 'back' in not-found flow continues the loop, eventually returns None."""
        from services.history_service import load_history, save_history
        import services.history_service as hs

        save_history("Trigun", 1, source="scraper")

        monkeypatch.setattr(
            hs,
            "_find_episodes",
            lambda *a, **kw: ("Trigun", [], True, False),
        )

        history_call = [0]

        def fake_menu(items, msg=""):
            history_call[0] += 1
            if history_call[0] == 1:
                return items[0] if items else None
            # Not-found: always pick "back"
            for item in items:
                if "Voltar" in item:
                    return item
            return None

        result = load_history(
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            progress=make_loading(),
            prompt=lambda msg: "",
        )
        assert result is None


# ---------------------------------------------------------------------------
# load_history – manual search flow
# ---------------------------------------------------------------------------


class TestLoadHistoryManualSearch:
    """load_history manual search fallback."""

    def test_manual_search_empty_query_continues(
        self, history_store, history_repository, monkeypatch
    ):
        """Empty manual query continues the loop without crashing."""
        from services.history_service import load_history, save_history
        import services.history_service as hs

        save_history("Unknown Anime", 0, source="scraper")

        monkeypatch.setattr(
            hs,
            "_find_episodes",
            lambda *a, **kw: ("Unknown Anime", [], True, False),
        )

        history_call = [0]
        prompt_call = [0]

        def fake_menu(items, msg=""):
            history_call[0] += 1
            if history_call[0] == 1:
                return items[0] if items else None
            for item in items:
                if "Buscar manualmente" in item:
                    return item
            return None

        def fake_prompt(msg):
            prompt_call[0] += 1
            return "  "  # blank query

        result = load_history(
            menu=fake_menu,
            menu_episodes=lambda eps: 0,
            progress=make_loading(),
            prompt=fake_prompt,
        )
        assert result is None


# ---------------------------------------------------------------------------
# save_history – auto-derives total_episodes
# ---------------------------------------------------------------------------


class TestSaveHistoryAutoTotal:
    """save_history derives total_episodes from repository when not given."""

    def test_derives_total_from_repo(self, history_store, history_repository):
        from services.history_service import save_history

        history_repository.add_episode_list(
            "Shingeki",
            [f"Ep {i}" for i in range(1, 26)],
            [f"https://example.test/aot/{i}" for i in range(1, 26)],
            "testscr",
        )

        save_history("Shingeki", 10)

        data = history_store.load({})
        assert data["Shingeki"][4] == 25


# ---------------------------------------------------------------------------
# save_history_from_event – AniList sync when authenticated
# ---------------------------------------------------------------------------


class TestSaveHistoryFromEventAniList:
    """save_history_from_event syncs progress when AniList is authenticated."""

    def test_authenticated_adds_to_list(self, history_store, history_repository, monkeypatch):
        import services.anilist as anilist_service
        from services.history_service import save_history_from_event

        fake_client = MagicMock()
        fake_client.is_authenticated.return_value = True
        fake_client.get_media_list_entry.return_value = None
        fake_client.add_to_list.return_value = True
        fake_client.update_progress.return_value = True

        monkeypatch.setattr(anilist_service, "anilist_client", fake_client)

        save_history_from_event(
            "Steins;Gate",
            episode_idx=3,
            action="watched",
            source="animefiredub",
            anilist_id=9253,
        )

        fake_client.add_to_list.assert_called_once_with(9253, "CURRENT")
        fake_client.update_progress.assert_called_once_with(9253, 4)

    def test_planning_status_moves_to_current(self, history_store, history_repository, monkeypatch):
        import services.anilist as anilist_service
        from services.history_service import save_history_from_event

        fake_entry = MagicMock()
        fake_entry.status = "PLANNING"
        fake_entry.progress = 0

        fake_client = MagicMock()
        fake_client.is_authenticated.return_value = True
        fake_client.get_media_list_entry.return_value = fake_entry
        fake_client.add_to_list.return_value = True
        fake_client.update_progress.return_value = True

        monkeypatch.setattr(anilist_service, "anilist_client", fake_client)

        save_history_from_event("Code Geass", episode_idx=0, action="watched", anilist_id=1575)

        fake_client.add_to_list.assert_called_once_with(1575, "CURRENT")

    def test_completed_status_changes_to_repeating(
        self, history_store, history_repository, monkeypatch
    ):
        import services.anilist as anilist_service
        from services.history_service import save_history_from_event
        from models.models import Status

        fake_entry = MagicMock()
        fake_entry.status = "COMPLETED"

        fake_client = MagicMock()
        fake_client.is_authenticated.return_value = True
        fake_client.get_media_list_entry.return_value = fake_entry
        fake_client.change_status.return_value = True
        fake_client.update_progress.return_value = True

        monkeypatch.setattr(anilist_service, "anilist_client", fake_client)

        save_history_from_event("FMAB", episode_idx=60, action="watched", anilist_id=5114)

        fake_client.change_status.assert_called_once_with(5114, Status.REPEATING)
        fake_client.update_progress.assert_called_once_with(5114, 61)

    def test_completed_status_change_fails_skips_progress(
        self, history_store, history_repository, monkeypatch
    ):
        """If change_status returns False, progress update is skipped."""
        import services.anilist as anilist_service
        from services.history_service import save_history_from_event

        fake_entry = MagicMock()
        fake_entry.status = "COMPLETED"

        fake_client = MagicMock()
        fake_client.is_authenticated.return_value = True
        fake_client.get_media_list_entry.return_value = fake_entry
        fake_client.change_status.return_value = False

        monkeypatch.setattr(anilist_service, "anilist_client", fake_client)

        save_history_from_event("FMAB", episode_idx=60, action="watched", anilist_id=5114)

        fake_client.update_progress.assert_not_called()

    def test_action_not_watched_skips_anilist_sync(
        self, history_store, history_repository, monkeypatch
    ):
        """action='started' does not trigger AniList sync."""
        import services.anilist as anilist_service
        from services.history_service import save_history_from_event

        fake_client = MagicMock()
        fake_client.is_authenticated.return_value = True

        monkeypatch.setattr(anilist_service, "anilist_client", fake_client)

        save_history_from_event("Evangelion", episode_idx=0, action="started", anilist_id=30)

        fake_client.get_media_list_entry.assert_not_called()
        fake_client.update_progress.assert_not_called()


# ---------------------------------------------------------------------------
# _find_episodes – saved URLs, AniList cache, local, search branches
# ---------------------------------------------------------------------------


class TestFindEpisodes:
    """Drive the _find_episodes helper across its branches.

    ``rep`` is the module-level Repository; its methods are patched to steer
    each code path deterministically without hitting real scrapers.
    """

    @pytest.fixture()
    def fake_rep(self, monkeypatch):
        import services.history_service as hs

        rep = MagicMock()
        monkeypatch.setattr(hs, "rep", rep)
        return rep

    def test_saved_urls_dict_loads_episodes(self, fake_rep):
        from services.history_service import _find_episodes

        eps = [MagicMock(number=1), MagicMock(number=2)]
        fake_rep.get_episode_list.return_value = eps

        anime, ep_list, searched, found = _find_episodes(
            "Berserk",
            None,
            None,
            "animefire",
            {"animefire": "https://x/berserk"},
            progress=make_loading(),
        )

        assert ep_list is eps
        assert searched is False
        assert found is True
        fake_rep.add_anime.assert_called_once_with("Berserk", "https://x/berserk", "animefire")

    def test_saved_urls_string_loads_episodes(self, fake_rep):
        """Non-dict saved_urls hits the else branch (line 128)."""
        from services.history_service import _find_episodes

        eps = [MagicMock(number=1)]
        fake_rep.get_episode_list.return_value = eps

        anime, ep_list, searched, found = _find_episodes(
            "Lain",
            None,
            None,
            "animefire",
            "https://x/lain",
            progress=make_loading(),
        )

        assert ep_list is eps
        fake_rep.add_anime.assert_called_once_with("Lain", "https://x/lain", "animefire")

    def test_anilist_cache_loads_episodes(self, fake_rep, monkeypatch):
        """anilist_id with cached urls hits lines 135-145."""
        import services.history_service as hs

        eps = [MagicMock(number=1), MagicMock(number=2), MagicMock(number=3)]
        fake_rep.get_episode_list.return_value = eps

        monkeypatch.setattr(hs, "load_anilist_urls", lambda aid: {"animefire": "https://x/gurren"})

        anime, ep_list, searched, found = hs._find_episodes(
            "Gurren Lagann",
            111,
            None,
            None,
            None,
            progress=make_loading(),
        )

        assert ep_list is eps
        assert searched is False
        assert found is True

    def test_local_source_returns_empty(self, fake_rep, monkeypatch):
        """saved_source == 'local' returns anilist_title and empty list (147-148)."""
        import services.history_service as hs

        monkeypatch.setattr(hs, "load_anilist_urls", lambda aid: {})

        anime, ep_list, searched, found = hs._find_episodes(
            "Local Anime",
            None,
            "Resolved Title",
            "local",
            None,
            progress=make_loading(),
        )

        assert anime == "Resolved Title"
        assert ep_list == []
        assert searched is False
        assert found is False

    def test_search_no_results(self, fake_rep):
        """Scraper search returning nothing hits lines 155-157."""
        from services.history_service import _find_episodes

        search_results = MagicMock()
        search_results.get_anime_titles.return_value = []
        fake_rep.search_anime.return_value = search_results

        anime, ep_list, searched, found = _find_episodes(
            "Nonexistent",
            None,
            None,
            None,
            None,
            progress=make_loading(),
        )

        assert ep_list == []
        assert searched is True
        assert found is False

    def test_search_single_result_with_source(self, fake_rep):
        """Single search result with saved_source hits lines 159-167."""
        from services.history_service import _find_episodes

        eps = [MagicMock(number=1), MagicMock(number=2)]
        search_results = MagicMock()
        search_results.get_anime_titles.return_value = ["Trigun"]
        fake_rep.search_anime.return_value = search_results
        fake_rep.get_episode_list.return_value = eps

        anime, ep_list, searched, found = _find_episodes(
            "Trigun",
            None,
            None,
            "animefire",
            None,
            progress=make_loading(),
        )

        assert anime == "Trigun"
        assert ep_list is eps
        assert searched is True
        assert found is True

    def test_search_single_result_without_source(self, fake_rep):
        """Single search result without saved_source hits the else at 164-166."""
        from services.history_service import _find_episodes

        eps = [MagicMock(number=1)]
        search_results = MagicMock()
        search_results.get_anime_titles.return_value = ["Trigun"]
        fake_rep.search_anime.return_value = search_results
        fake_rep.get_episode_list.return_value = eps

        anime, ep_list, searched, found = _find_episodes(
            "Trigun",
            None,
            None,
            None,
            None,
            progress=make_loading(),
        )

        assert anime == "Trigun"
        assert ep_list is eps
        assert found is True

    def test_search_multiple_results_retry(self, fake_rep):
        """Multiple results where _validate returns _RETRY hits 169-171."""
        from services.history_service import _find_episodes

        search_results = MagicMock()
        search_results.get_anime_titles.return_value = ["A", "B"]
        search_results.get_anime_titles_with_sources.return_value = [
            "A [src1]",
            "B [src2]",
        ]
        fake_rep.search_anime.return_value = search_results
        fake_rep.get_episode_list.return_value = [MagicMock(number=1)]

        # Cancel the source-selection menu -> _RETRY -> (anime, None, ...)
        anime, ep_list, searched, found = _find_episodes(
            "Ambiguous",
            None,
            None,
            None,
            None,
            menu=lambda items, msg="": None,
            progress=make_loading(),
        )

        assert ep_list is None
        assert searched is True


# ---------------------------------------------------------------------------
# load_history – manual search success flow (lines 307-346)
# ---------------------------------------------------------------------------


class TestLoadHistoryManualSearchSuccess:
    """Full manual-search-and-replace path through load_history."""

    def test_manual_search_replaces_history(self, history_store, monkeypatch):
        from services.history_service import load_history, save_history
        import services.history_service as hs

        save_history("Old Name", 4, source="animefire", total_episodes=12)

        # First _find_episodes call: not found -> triggers not-found retry menu
        monkeypatch.setattr(
            hs,
            "_find_episodes",
            lambda *a, **kw: ("Old Name", [], True, False),
        )

        # Fake repository for the manual-search branch
        eps = [MagicMock(number=i + 1) for i in range(12)]
        search_results = MagicMock()
        search_results.get_anime_titles.return_value = ["New Name"]
        search_results.get_anime_titles_with_sources.return_value = ["New Name [animefire]"]

        rep = MagicMock()
        rep.search_anime.return_value = search_results
        rep.get_episode_list.return_value = eps
        monkeypatch.setattr(hs, "rep", rep)

        state = {"n": 0}

        def fake_menu(items, msg=""):
            state["n"] += 1
            n = state["n"]
            if n == 1:
                # History selection menu
                return items[0] if items else None
            if n == 2:
                # Not-found options: pick manual search
                for it in items:
                    if "Buscar manualmente" in it:
                        return it
                return None
            if n == 3:
                # Replace confirmation
                return "✅ Sim, substituir"
            # Episode picker: pick "current"
            for it in items:
                if "▶️" in it:
                    return it
            return items[0]

        result = load_history(
            menu=fake_menu,
            menu_episodes=lambda e: 0,
            progress=make_loading(),
            prompt=lambda msg: "New Name",
        )

        assert result is not None
        anime, ep_idx, _, _ = result
        assert anime == "New Name"
        # Old entry replaced, new entry saved
        data = history_store.load({})
        assert "Old Name" not in data
        assert "New Name" in data

    def test_manual_search_no_results_continues(self, history_store, monkeypatch):
        """Manual query returning no results logs and continues (312-315)."""
        from services.history_service import load_history, save_history
        import services.history_service as hs

        save_history("Vanished", 0, source="animefire")

        monkeypatch.setattr(
            hs,
            "_find_episodes",
            lambda *a, **kw: ("Vanished", [], True, False),
        )

        search_results = MagicMock()
        search_results.get_anime_titles.return_value = []
        rep = MagicMock()
        rep.search_anime.return_value = search_results
        monkeypatch.setattr(hs, "rep", rep)

        state = {"n": 0}

        def fake_menu(items, msg=""):
            state["n"] += 1
            if state["n"] == 1:
                return items[0] if items else None
            for it in items:
                if "Buscar manualmente" in it:
                    return it
            return None

        prompted = []
        result = load_history(
            menu=fake_menu,
            menu_episodes=lambda e: 0,
            progress=make_loading(),
            prompt=lambda msg: prompted.append(msg) or "SomeQuery",
        )

        assert result is None
        # "Pressione Enter para continuar" was prompted after no results
        assert any("continuar" in p for p in prompted)

    def test_manual_search_selected_no_episodes_continues(self, history_store, monkeypatch):
        """Selected title without episodes logs and continues (333-336)."""
        from services.history_service import load_history, save_history
        import services.history_service as hs

        save_history("Empty Source", 0, source="animefire")

        monkeypatch.setattr(
            hs,
            "_find_episodes",
            lambda *a, **kw: ("Empty Source", [], True, False),
        )

        search_results = MagicMock()
        search_results.get_anime_titles.return_value = ["Found But Empty"]
        search_results.get_anime_titles_with_sources.return_value = ["Found But Empty [src]"]

        rep = MagicMock()
        rep.search_anime.return_value = search_results
        rep.get_episode_list.return_value = []  # no episodes
        monkeypatch.setattr(hs, "rep", rep)

        state = {"n": 0}

        def fake_menu(items, msg=""):
            state["n"] += 1
            if state["n"] == 1:
                return items[0] if items else None
            for it in items:
                if "Buscar manualmente" in it:
                    return it
            return None

        result = load_history(
            menu=fake_menu,
            menu_episodes=lambda e: 0,
            progress=make_loading(),
            prompt=lambda msg: "AnyQuery",
        )

        assert result is None
