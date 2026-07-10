"""Tests for services/history_service.py.

Covers:
- save_history() – writes correct format to JSON store
- reset_history() – removes an entry from the store
- save_history_from_event() – derives total_episodes and anilist_id from repo state
- load_history() depth guard (BUG-07) – returns None after depth > 5

Strategy:
- Patch the module-level _history_store with a real JSONStore backed by a tmp dir
- Patch menu_navigate / loading / UI calls so no interactive prompts fire
- Mock only external AniList HTTP calls when present
- No mocking of internal services (repository, JSONStore)
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from utils.persistence import JSONStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_store(tmp_path: Path) -> JSONStore:
    """Return a real JSONStore writing to a temp file."""
    return JSONStore(tmp_path / "history.json")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def history_store(tmp_path):
    """Real JSONStore backed by a temporary directory."""
    return make_store(tmp_path)


@pytest.fixture(autouse=True)
def patch_history_store(history_store):
    """Redirect the module-level _history_store to the temp store for every test."""
    with patch("services.history_service._history_store", history_store):
        yield history_store


# ---------------------------------------------------------------------------
# save_history
# ---------------------------------------------------------------------------


class TestSaveHistory:
    """Tests for save_history()."""

    def test_saves_basic_entry(self, history_store):
        """save_history writes [timestamp, episode, None, None, None, {}] to store."""
        from services.history_service import save_history

        before = int(time.time())
        save_history("Demon Slayer", 3)
        after = int(time.time())

        data = history_store.load({})
        assert "Demon Slayer" in data

        entry = data["Demon Slayer"]
        ts, ep_idx, anilist_id, source, total_eps, anime_urls = entry

        assert before <= ts <= after
        assert ep_idx == 3
        assert anilist_id is None
        assert source is None
        # total_episodes may be None when repo has no episode list
        assert anime_urls == {}

    def test_saves_optional_fields(self, history_store):
        """save_history persists anilist_id, source and total_episodes."""
        from services.history_service import save_history

        save_history(
            "Attack on Titan",
            7,
            anilist_id=16498,
            source="animefire",
            total_episodes=25,
            anime_urls={"animefire": "https://animefire.net/anime/aot"},
        )

        data = history_store.load({})
        entry = data["Attack on Titan"]
        _, ep_idx, anilist_id, source, total_eps, anime_urls = entry

        assert ep_idx == 7
        assert anilist_id == 16498
        assert source == "animefire"
        assert total_eps == 25
        assert anime_urls == {"animefire": "https://animefire.net/anime/aot"}

    def test_overwrites_existing_entry(self, history_store):
        """Calling save_history twice for the same anime updates the entry."""
        from services.history_service import save_history

        save_history("Naruto", 0)
        save_history("Naruto", 10)

        data = history_store.load({})
        assert data["Naruto"][1] == 10

    def test_multiple_anime_coexist(self, history_store):
        """Multiple anime entries live side-by-side in the store."""
        from services.history_service import save_history

        save_history("One Piece", 100)
        save_history("Bleach", 50)

        data = history_store.load({})
        assert "One Piece" in data
        assert "Bleach" in data


# ---------------------------------------------------------------------------
# reset_history
# ---------------------------------------------------------------------------


class TestResetHistory:
    """Tests for reset_history()."""

    def test_removes_existing_entry(self, history_store):
        """reset_history deletes the anime key from the store."""
        from services.history_service import reset_history, save_history

        save_history("Vinland Saga", 5)
        assert "Vinland Saga" in history_store.load({})

        reset_history("Vinland Saga")
        assert "Vinland Saga" not in history_store.load({})

    def test_reset_nonexistent_entry_is_noop(self, history_store):
        """reset_history on a missing entry does not raise."""
        from services.history_service import reset_history

        # Should complete silently
        reset_history("Ghost in the Shell")
        assert history_store.load({}) == {}

    def test_reset_leaves_other_entries_intact(self, history_store):
        """reset_history only removes the targeted anime."""
        from services.history_service import reset_history, save_history

        save_history("HxH", 1)
        save_history("FMA", 2)

        reset_history("HxH")

        data = history_store.load({})
        assert "HxH" not in data
        assert "FMA" in data


# ---------------------------------------------------------------------------
# save_history_from_event
# ---------------------------------------------------------------------------


class TestSaveHistoryFromEvent:
    """Tests for save_history_from_event()."""

    def test_saves_episode_with_explicit_anilist_id(self, history_store):
        """save_history_from_event stores the provided anilist_id."""
        from services.history_service import save_history_from_event

        # Patch anilist_client so no HTTP calls fire
        mock_anilist = MagicMock()
        mock_anilist.is_authenticated.return_value = False

        with patch("services.history_service.rep") as mock_rep:
            mock_rep.get_episode_list.return_value = []
            mock_rep.anime_to_urls = {}

            with patch("services.anilist.anilist_client", mock_anilist):
                save_history_from_event(
                    "Jujutsu Kaisen",
                    episode_idx=4,
                    action="watched",
                    source="sushianimes",
                    anilist_id=113415,
                )

        data = history_store.load({})
        assert "Jujutsu Kaisen" in data
        entry = data["Jujutsu Kaisen"]
        assert entry[1] == 4
        assert entry[2] == 113415
        assert entry[3] == "sushianimes"

    def test_saves_episode_without_anilist_id_no_crash(self, history_store):
        """save_history_from_event works when no anilist_id is provided."""
        from services.history_service import save_history_from_event

        with patch("services.history_service.rep") as mock_rep:
            mock_rep.get_episode_list.return_value = []
            mock_rep.anime_to_urls = {}
            mock_rep.anime_to_anilist_id = {}

            save_history_from_event("Black Clover", episode_idx=0, action="started")

        data = history_store.load({})
        assert "Black Clover" in data

    def test_derives_total_episodes_from_repo(self, history_store):
        """save_history_from_event uses episode list length as total_episodes."""
        from services.history_service import save_history_from_event

        episode_list = [f"Ep {i}" for i in range(1, 13)]

        with patch("services.history_service.rep") as mock_rep:
            mock_rep.get_episode_list.return_value = episode_list
            mock_rep.anime_to_urls = {}
            mock_rep.anime_to_anilist_id = {}

            save_history_from_event("Spy x Family", episode_idx=2, action="watched")

        data = history_store.load({})
        entry = data["Spy x Family"]
        total_eps = entry[4]
        assert total_eps == 12

    def test_falls_back_to_history_for_anilist_id(self, history_store):
        """If anilist_id not in repo, it is read from an existing history entry."""
        from services.history_service import save_history, save_history_from_event

        # Pre-populate history with an anilist_id for this anime
        save_history("Mob Psycho 100", 1, anilist_id=97988, source="animefire")

        with patch("services.history_service.rep") as mock_rep:
            mock_rep.get_episode_list.return_value = []
            mock_rep.anime_to_urls = {}
            mock_rep.anime_to_anilist_id = {}  # Not in repo

            mock_anilist = MagicMock()
            mock_anilist.is_authenticated.return_value = False

            with patch("services.anilist.anilist_client", mock_anilist):
                save_history_from_event(
                    "Mob Psycho 100",
                    episode_idx=5,
                    action="watched",
                )

        data = history_store.load({})
        entry = data["Mob Psycho 100"]
        # The anilist_id should have been recovered from existing history
        assert entry[2] == 97988


# ---------------------------------------------------------------------------
# load_history – depth guard (BUG-07)
# ---------------------------------------------------------------------------


class TestLoadHistoryDepthGuard:
    """Tests for the retry loop guard in load_history() (BUG-07 fix).

    Recursion was replaced by a for-loop with range(6). Tests validate that the
    loop terminates and emits the expected warning after exhausting retries.
    """

    def test_returns_none_on_cancelled_menu(self, history_store):
        """Cancelled history menu returns None gracefully (no warning)."""
        from services.history_service import load_history

        with patch("ui.components.menu_navigate", return_value=None):
            result = load_history()

        assert result is None

    def test_no_warning_when_menu_cancelled(self, history_store):
        """No 'Muitas tentativas' warning when user simply cancels the menu."""
        import services.history_service as hs_module
        from services.history_service import load_history

        with patch("ui.components.menu_navigate", return_value=None):
            with patch.object(hs_module.logger, "warning") as mock_warn:
                load_history()

        mock_warn.assert_not_called()

    def test_guard_logs_warning_after_max_retries(self, history_store):
        """Warning fires after 6 retry-inducing iterations."""
        import services.history_service as hs_module
        from services.history_service import save_history

        save_history("Goblin Slayer", 1, source="animefire")

        # _find_episodes returning (anime, None, ...) triggers continue each iteration
        with patch.object(
            hs_module,
            "_find_episodes",
            return_value=("Goblin Slayer", None, True, True),
        ):
            with patch("ui.components.menu_navigate", return_value="Goblin Slayer (Ep 2)"):
                with patch.object(hs_module.logger, "warning") as mock_warn:
                    result = hs_module.load_history()

        assert result is None
        mock_warn.assert_called_once()
        assert "Muitas tentativas" in mock_warn.call_args[0][0]

    def test_returns_none_immediately_with_empty_history(self, history_store):
        """Empty history → menu has no items → returns None without looping."""
        from services.history_service import load_history

        with patch("ui.components.menu_navigate", return_value=None):
            result = load_history()

        assert result is None


# ---------------------------------------------------------------------------
# load_history – empty history
# ---------------------------------------------------------------------------


class TestLoadHistoryEmptyHistory:
    """load_history behaviour when no history exists yet."""

    def test_returns_none_when_history_empty(self, history_store):
        """Returns None (not an exception) when history file is missing."""
        from services.history_service import load_history

        with patch("ui.components.menu_navigate", return_value=None):
            result = load_history()

        assert result is None

    def test_returns_none_when_user_cancels_menu(self, history_store):
        """Returns None when user presses Esc / cancels history menu."""
        from services.history_service import save_history, load_history

        save_history("One Punch Man", 0)

        with patch("ui.components.menu_navigate", return_value=None):
            result = load_history()

        assert result is None
