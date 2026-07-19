"""Coverage tests for services/anime/anilist_integration.py.

Strategy: mock only external boundaries (anilist_client, ui_bridge, rep,
get_scraper_cache/set_scraper_cache, incremental_search_anime, etc.).
Never mock internal pure logic.
"""

from __future__ import annotations

import importlib
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mod():
    return importlib.import_module("services.anime.anilist_integration")


def _make_args(**kwargs):
    return SimpleNamespace(debug=False, **kwargs)


def _make_ui_bridge_mock(menu_returns=None, prompt_returns="", pause_returns=None):
    """Return a mock ui_bridge with sensible defaults."""
    m = MagicMock()
    if menu_returns is not None:
        if isinstance(menu_returns, list):
            m.menu_navigate.side_effect = menu_returns
        else:
            m.menu_navigate.return_value = menu_returns
    else:
        m.menu_navigate.return_value = None

    m.prompt.return_value = prompt_returns
    m.pause.return_value = None
    m.menu_navigate_episodes.return_value = None

    @contextmanager
    def _loading(msg=""):
        yield

    m.loading.side_effect = _loading
    return m


# ---------------------------------------------------------------------------
# build_anilist_post_playback_options
# ---------------------------------------------------------------------------


class TestBuildAnilistPostPlaybackOptions:
    def test_first_episode_no_previous(self):
        mod = _mod()
        opts = mod.build_anilist_post_playback_options(0, 5)
        assert "▶️  Próximo" in opts
        assert "◀️  Anterior" not in opts

    def test_last_episode_no_next(self):
        mod = _mod()
        opts = mod.build_anilist_post_playback_options(4, 5)
        assert "↩️  Voltar ao menu anterior" in opts
        assert "▶️  Próximo" not in opts
        assert "◀️  Anterior" in opts

    def test_replay_always_present(self):
        mod = _mod()
        for idx in range(3):
            opts = mod.build_anilist_post_playback_options(idx, 5)
            assert "🔁 Replay" in opts

    def test_choose_episode_always_present(self):
        mod = _mod()
        opts = mod.build_anilist_post_playback_options(2, 5)
        assert "📋 Escolher outro episódio" in opts
        assert "🔄 Trocar fonte" in opts


# ---------------------------------------------------------------------------
# _is_anime_released
# ---------------------------------------------------------------------------


class TestIsAnimeReleased:
    def test_none_returns_true(self):
        mod = _mod()
        assert mod._is_anime_released(None) is True

    def test_not_yet_released(self):
        mod = _mod()
        node = SimpleNamespace(status="NOT_YET_RELEASED")
        assert mod._is_anime_released(node) is False

    def test_releasing(self):
        mod = _mod()
        node = SimpleNamespace(status="RELEASING")
        assert mod._is_anime_released(node) is True

    def test_finished(self):
        mod = _mod()
        node = SimpleNamespace(status="FINISHED")
        assert mod._is_anime_released(node) is True

    def test_unknown_status_returns_true(self):
        mod = _mod()
        node = SimpleNamespace(status="CANCELLED")
        assert mod._is_anime_released(node) is True

    def test_no_status_attr(self):
        mod = _mod()
        node = object()
        assert mod._is_anime_released(node) is True


# ---------------------------------------------------------------------------
# resolve_preferred_title
# ---------------------------------------------------------------------------


class TestResolvePreferredTitle:
    def test_no_english_title_returns_current(self, monkeypatch):
        mod = _mod()
        result = mod.resolve_preferred_title(1, None, "Romaji", "fallback")
        assert result == "fallback"

    def test_no_romaji_title_returns_current(self, monkeypatch):
        mod = _mod()
        result = mod.resolve_preferred_title(1, "English", None, "fallback")
        assert result == "fallback"

    def test_same_normalized_titles_returns_romaji(self, monkeypatch):
        mod = _mod()
        # Same after normalization
        result = mod.resolve_preferred_title(1, "Jujutsu Kaisen", "jujutsu kaisen", "fallback")
        assert result == "jujutsu kaisen"

    def test_cached_english_preference(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "load_language_preference", lambda aid: "english")
        result = mod.resolve_preferred_title(1, "Attack on Titan", "Shingeki no Kyojin", "x")
        assert result == "Attack on Titan"

    def test_cached_romaji_preference(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "load_language_preference", lambda aid: "romaji")
        result = mod.resolve_preferred_title(1, "Attack on Titan", "Shingeki no Kyojin", "x")
        assert result == "Shingeki no Kyojin"

    def test_user_picks_english(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "load_language_preference", lambda aid: None)
        monkeypatch.setattr(mod, "save_language_preference", lambda aid, lang: None)
        ui = _make_ui_bridge_mock(menu_returns="🇬🇧 Inglês: Attack on Titan")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.resolve_preferred_title(1, "Attack on Titan", "Shingeki no Kyojin", "x")
        assert result == "Attack on Titan"

    def test_user_picks_romaji(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "load_language_preference", lambda aid: None)
        monkeypatch.setattr(mod, "save_language_preference", lambda aid, lang: None)
        ui = _make_ui_bridge_mock(menu_returns="🇯🇵 Romaji: Shingeki no Kyojin")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.resolve_preferred_title(1, "Attack on Titan", "Shingeki no Kyojin", "x")
        assert result == "Shingeki no Kyojin"

    def test_user_cancels_returns_none(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "load_language_preference", lambda aid: None)
        ui = _make_ui_bridge_mock(menu_returns=None)
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.resolve_preferred_title(1, "Attack on Titan", "Shingeki no Kyojin", "x")
        assert result is None

    def test_no_anilist_id_skips_cache(self, monkeypatch):
        mod = _mod()
        load_pref_called = []
        monkeypatch.setattr(
            mod, "load_language_preference", lambda aid: load_pref_called.append(aid) or None
        )
        monkeypatch.setattr(mod, "save_language_preference", lambda aid, lang: None)
        ui = _make_ui_bridge_mock(menu_returns="🇯🇵 Romaji: Shingeki no Kyojin")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        mod.resolve_preferred_title(None, "Attack on Titan", "Shingeki no Kyojin", "x")
        assert not load_pref_called


# ---------------------------------------------------------------------------
# _current_used_query
# ---------------------------------------------------------------------------


class TestCurrentUsedQuery:
    def test_no_search_state_returns_fallback(self):
        mod = _mod()
        assert mod._current_used_query(None, "fallback") == "fallback"

    def test_no_current_result_set_returns_fallback(self):
        mod = _mod()
        state = MagicMock()
        state.get_current.return_value = None
        assert mod._current_used_query(state, "fallback") == "fallback"

    def test_returns_query_from_result_set(self):
        mod = _mod()
        state = MagicMock()
        state.get_current.return_value = SimpleNamespace(query="found query")
        assert mod._current_used_query(state, "fallback") == "found query"


# ---------------------------------------------------------------------------
# _read_local_progress
# ---------------------------------------------------------------------------


class TestReadLocalProgress:
    def test_no_history_file_returns_zero(self, tmp_path, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "HISTORY_PATH", tmp_path)
        result = mod._read_local_progress("Some Anime")
        assert result == 0

    def test_anime_in_history_returns_next_ep(self, tmp_path, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "HISTORY_PATH", tmp_path)
        history = {"Some Anime": [0, 4, 42]}  # index 1 = episode idx
        (tmp_path / "history.json").write_text(json.dumps(history))
        result = mod._read_local_progress("Some Anime")
        assert result == 5  # 4 + 1

    def test_anime_not_in_history_returns_zero(self, tmp_path, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "HISTORY_PATH", tmp_path)
        history = {"Other Anime": [0, 3, 42]}
        (tmp_path / "history.json").write_text(json.dumps(history))
        result = mod._read_local_progress("Some Anime")
        assert result == 0

    def test_invalid_json_returns_zero(self, tmp_path, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "HISTORY_PATH", tmp_path)
        # history.json exists but is missing the key -> KeyError branch
        (tmp_path / "history.json").write_text('{"Other": [0, 1, 2]}')
        result = mod._read_local_progress("Missing Anime")
        assert result == 0


# ---------------------------------------------------------------------------
# _build_continue_menu
# ---------------------------------------------------------------------------


class TestBuildContinueMenu:
    def _call(self, **kwargs):
        mod = _mod()
        defaults = dict(
            selected_anime="Test Anime",
            max_progress=3,
            anilist_progress=3,
            local_progress=3,
            episode_list=[object()] * 10,
            total_episodes=12,
            scraper_episode_count=10,
        )
        defaults.update(kwargs)
        return mod._build_continue_menu(**defaults)

    def test_has_next_episode_in_options(self):
        options, option_to_idx, _ = self._call()
        assert any("Episódio 4" in o for o in options)

    def test_current_and_prev_in_options(self):
        options, _, _ = self._call(max_progress=5)
        assert any("Episódio 5" in o for o in options)
        assert any("Episódio 4" in o for o in options)

    def test_no_previous_when_progress_is_1(self):
        options, _, _ = self._call(max_progress=1, anilist_progress=1, local_progress=1)
        assert not any("Episódio 0" in o for o in options)

    def test_source_label_both(self):
        # progress_source is embedded in the episode option label, not the menu_msg
        options, _, _ = self._call(anilist_progress=5, local_progress=5, max_progress=5)
        ep_labels = " ".join(options)
        assert "AniList + Local" in ep_labels

    def test_waiting_episode_when_progress_at_scraper_end(self):
        episode_list = [object()] * 3
        options, option_to_idx, _ = self._call(
            max_progress=3,
            anilist_progress=3,
            local_progress=3,
            episode_list=episode_list,
            total_episodes=12,
            scraper_episode_count=3,
        )
        # next episode exists but not scraped yet
        awaiting_opts = [o for o in options if "aguardando" in o]
        assert awaiting_opts
        assert option_to_idx[awaiting_opts[0]] is None

    def test_menu_msg_includes_episode_counts(self):
        _, _, msg = self._call()
        assert "eps disponíveis" in msg


# ---------------------------------------------------------------------------
# _resolve_start_episode_idx - simple branches
# ---------------------------------------------------------------------------


class TestResolveStartEpisodeIdx:
    def _call(self, mod, episode_list, anilist_progress, local_progress, ui, **kwargs):
        mod_ref = mod if not isinstance(mod, str) else importlib.import_module(mod)
        return mod_ref._resolve_start_episode_idx(
            selected_anime="Anime",
            episode_list=episode_list,
            anilist_progress=anilist_progress,
            local_progress=local_progress,
            total_episodes=kwargs.get("total_episodes", None),
            scraper_episode_count=kwargs.get("scraper_episode_count", None),
        )

    def test_no_progress_shows_episode_list(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        ui.menu_navigate_episodes.return_value = 0
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = self._call(mod, [object()] * 5, 0, 0, ui)
        assert result == 0
        ui.menu_navigate_episodes.assert_called_once()

    def test_user_chooses_next_episode(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        ep_list = [object()] * 5
        # max_progress = 2
        ui.menu_navigate.return_value = "⏭️  Episódio 3 (próximo)"
        result = mod._resolve_start_episode_idx("Anime", ep_list, 2, 2, None, None)
        assert result == 2

    def test_user_chooses_choose_episode(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        ui.menu_navigate.return_value = "📋 Escolher outro episódio"
        ui.menu_navigate_episodes.return_value = 3
        monkeypatch.setattr(mod, "ui_bridge", ui)
        ep_list = [object()] * 5
        result = mod._resolve_start_episode_idx("Anime", ep_list, 2, 2, None, None)
        assert result == 3

    def test_user_cancels(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        ui.menu_navigate.return_value = None
        monkeypatch.setattr(mod, "ui_bridge", ui)
        ep_list = [object()] * 5
        result = mod._resolve_start_episode_idx("Anime", ep_list, 2, 2, None, None)
        assert result is None

    def test_user_resets_history(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        reset_called = []
        monkeypatch.setattr(mod, "reset_history", lambda a: reset_called.append(a))
        # First call: choose "Começar do zero"
        # Second: confirm reset
        ui.menu_navigate.side_effect = ["🔄 Começar do zero", "✅ Sim, resetar"]
        ep_list = [object()] * 5
        result = mod._resolve_start_episode_idx("Anime", ep_list, 2, 2, None, None)
        assert result == 0
        assert reset_called == ["Anime"]

    def test_user_cancels_reset(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        monkeypatch.setattr(mod, "reset_history", lambda a: None)
        ui.menu_navigate.side_effect = ["🔄 Começar do zero", "❌ Cancelar"]
        ep_list = [object()] * 5
        result = mod._resolve_start_episode_idx("Anime", ep_list, 2, 2, None, None)
        assert result is None


# ---------------------------------------------------------------------------
# _prompt_saved_title_choice
# ---------------------------------------------------------------------------


class TestPromptSavedTitleChoice:
    def test_no_saved_title_returns_not_cancelled(self, monkeypatch):
        mod = _mod()
        selected, source, cancelled = mod._prompt_saved_title_choice(None, None)
        assert selected is None
        assert source is None
        assert cancelled is False

    def test_user_continues_with_saved(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock(menu_returns="✅ Continuar com este")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        selected, source, cancelled = mod._prompt_saved_title_choice("Saved Anime", "src1")
        assert selected == "Saved Anime"
        assert source == "src1"
        assert cancelled is False

    def test_user_chooses_other(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock(menu_returns="🔄 Escolher outro")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        selected, source, cancelled = mod._prompt_saved_title_choice("Saved Anime", "src1")
        assert selected is None
        assert cancelled is False

    def test_user_cancels_menu(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock(menu_returns=None)
        monkeypatch.setattr(mod, "ui_bridge", ui)
        selected, source, cancelled = mod._prompt_saved_title_choice("Saved Anime", None)
        assert selected is None
        assert cancelled is True


# ---------------------------------------------------------------------------
# _sync_anilist_progress
# ---------------------------------------------------------------------------


class TestSyncAnilistProgress:
    def _make_client(
        self, authenticated=True, in_list=False, entry=None, update_success=True, viewer=None
    ):
        client = MagicMock()
        client.is_authenticated.return_value = authenticated
        client.is_in_any_list.return_value = in_list
        client.get_media_list_entry.return_value = entry
        client.update_progress.return_value = update_success
        client.get_viewer_info.return_value = viewer
        return client

    def test_not_authenticated_returns_early(self, monkeypatch):
        mod = _mod()
        client = self._make_client(authenticated=False)
        monkeypatch.setattr(mod, "anilist_client", client)
        mod._sync_anilist_progress(1, 5, 12)
        client.update_progress.assert_not_called()

    def test_not_in_list_adds_current(self, monkeypatch):
        mod = _mod()
        client = self._make_client(authenticated=True, in_list=False, update_success=True)
        monkeypatch.setattr(mod, "anilist_client", client)
        mod._sync_anilist_progress(1, 5, 12)
        client.add_to_list.assert_called()
        client.update_progress.assert_called_with(1, 5)

    def test_planning_status_promoted(self, monkeypatch):
        mod = _mod()
        entry = SimpleNamespace(status="PLANNING")
        client = self._make_client(
            authenticated=True, in_list=True, entry=entry, update_success=True
        )
        monkeypatch.setattr(mod, "anilist_client", client)
        from models.models import Status

        mod._sync_anilist_progress(1, 5, 12)
        client.add_to_list.assert_called_with(1, Status.CURRENT)

    def test_current_status_last_ep_completes(self, monkeypatch):
        mod = _mod()
        entry = SimpleNamespace(status="CURRENT")
        client = self._make_client(
            authenticated=True, in_list=True, entry=entry, update_success=True
        )
        monkeypatch.setattr(mod, "anilist_client", client)
        from models.models import Status

        mod._sync_anilist_progress(1, 12, 12)
        client.change_status.assert_called_with(1, Status.COMPLETED)

    def test_current_status_not_last_ep_no_complete(self, monkeypatch):
        mod = _mod()
        entry = SimpleNamespace(status="CURRENT")
        client = self._make_client(
            authenticated=True, in_list=True, entry=entry, update_success=True
        )
        monkeypatch.setattr(mod, "anilist_client", client)
        mod._sync_anilist_progress(1, 5, 12)
        client.change_status.assert_not_called()

    def test_update_fails_gets_viewer(self, monkeypatch):
        mod = _mod()
        client = self._make_client(
            authenticated=True, in_list=True, entry=None, update_success=False, viewer=None
        )
        monkeypatch.setattr(mod, "anilist_client", client)
        mod._sync_anilist_progress(1, 5, 12)
        client.get_viewer_info.assert_called()

    def test_update_fails_viewer_exists_logs_warning(self, monkeypatch):
        mod = _mod()
        viewer = SimpleNamespace(id=42)
        client = self._make_client(
            authenticated=True, in_list=True, entry=None, update_success=False, viewer=viewer
        )
        monkeypatch.setattr(mod, "anilist_client", client)
        # Should not raise
        mod._sync_anilist_progress(1, 5, 12)


# ---------------------------------------------------------------------------
# _get_anilist_titles
# ---------------------------------------------------------------------------


class TestGetAnilistTitles:
    def test_no_anime_info_returns_none_none(self, monkeypatch):
        mod = _mod()
        client = MagicMock()
        client.get_anime_by_id.return_value = None
        monkeypatch.setattr(mod, "anilist_client", client)
        eng, rom = mod._get_anilist_titles(42)
        assert eng is None
        assert rom is None

    def test_returns_titles_from_client(self, monkeypatch):
        mod = _mod()
        anime_info = SimpleNamespace(
            title=SimpleNamespace(english="English Title", romaji="Romaji Title")
        )
        client = MagicMock()
        client.get_anime_by_id.return_value = anime_info
        monkeypatch.setattr(mod, "anilist_client", client)
        eng, rom = mod._get_anilist_titles(42)
        assert eng == "English Title"
        assert rom == "Romaji Title"


# ---------------------------------------------------------------------------
# offer_sequel_and_continue
# ---------------------------------------------------------------------------


class TestOfferSequelAndContinue:
    def _base_client(self):
        client = MagicMock()
        client.is_authenticated.return_value = True
        return client

    def test_not_authenticated_returns_false(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        client.is_authenticated.return_value = False
        monkeypatch.setattr(mod, "anilist_client", client)
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is False

    def test_more_episodes_available_returns_false(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        monkeypatch.setattr(mod, "anilist_client", client)
        # current_episode=5, anilist_episodes=12 => still more to watch
        result = mod.offer_sequel_and_continue(
            1, _make_args(), current_episode=5, anilist_episodes=12
        )
        assert result is False

    def test_no_sequels_returns_false(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        client.get_sequels.return_value = []
        monkeypatch.setattr(mod, "anilist_client", client)
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is False

    def test_single_sequel_released_user_plays(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        sequel = SimpleNamespace(id=99, title=MagicMock(), episodes=12, status="FINISHED")
        client.get_sequels.return_value = [sequel]
        client.format_title.return_value = "Sequel Title"
        monkeypatch.setattr(mod, "anilist_client", client)
        ui = _make_ui_bridge_mock(menu_returns="▶️ Procurar episódios")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        flow_calls = []
        monkeypatch.setattr(mod, "anilist_anime_flow", lambda *a, **kw: flow_calls.append((a, kw)))
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is True
        assert flow_calls

    def test_single_sequel_released_user_adds_planning(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        sequel = SimpleNamespace(id=99, title=MagicMock(), episodes=12, status="FINISHED")
        client.get_sequels.return_value = [sequel]
        client.format_title.return_value = "Sequel Title"
        client.add_to_list.return_value = True
        monkeypatch.setattr(mod, "anilist_client", client)
        ui = _make_ui_bridge_mock(menu_returns="📋 Adicionar à 'Planejo Assistir'")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is False
        client.add_to_list.assert_called()

    def test_single_sequel_not_released_shows_planning_option(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        sequel = SimpleNamespace(id=99, title=MagicMock(), episodes=None, status="NOT_YET_RELEASED")
        client.get_sequels.return_value = [sequel]
        client.format_title.return_value = "Sequel Title"
        client.add_to_list.return_value = True
        monkeypatch.setattr(mod, "anilist_client", client)
        ui = _make_ui_bridge_mock(menu_returns="📋 Adicionar à 'Planejo Assistir'")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is False

    def test_single_sequel_user_declines(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        sequel = SimpleNamespace(id=99, title=MagicMock(), episodes=12, status="FINISHED")
        client.get_sequels.return_value = [sequel]
        client.format_title.return_value = "Sequel Title"
        monkeypatch.setattr(mod, "anilist_client", client)
        ui = _make_ui_bridge_mock(menu_returns="❌ Não, parar aqui")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is False

    def test_multiple_sequels_user_picks_and_plays(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        s1 = SimpleNamespace(id=10, title=MagicMock(), episodes=12, status="FINISHED")
        s2 = SimpleNamespace(id=11, title=MagicMock(), episodes=6, status="FINISHED")
        client.get_sequels.return_value = [s1, s2]
        client.format_title.side_effect = lambda t: "Sequel One" if t is s1.title else "Sequel Two"
        monkeypatch.setattr(mod, "anilist_client", client)
        # First navigate: pick "Sequel One", then action: play episodes
        ui = _make_ui_bridge_mock()
        ui.menu_navigate.side_effect = ["Sequel One", "▶️ Procurar episódios"]
        monkeypatch.setattr(mod, "ui_bridge", ui)
        flow_calls = []
        monkeypatch.setattr(mod, "anilist_anime_flow", lambda *a, **kw: flow_calls.append((a, kw)))
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is True

    def test_multiple_sequels_user_cancels(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        s1 = SimpleNamespace(id=10, title=MagicMock(), episodes=12, status="FINISHED")
        client.get_sequels.return_value = [s1]
        # Need 2 sequels to hit "multiple" branch
        s2 = SimpleNamespace(id=11, title=MagicMock(), episodes=12, status="FINISHED")
        client.get_sequels.return_value = [s1, s2]
        client.format_title.side_effect = lambda t: "S1" if t is s1.title else "S2"
        monkeypatch.setattr(mod, "anilist_client", client)
        ui = _make_ui_bridge_mock(menu_returns="❌ Não, parar aqui")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is False

    def test_multiple_sequels_adds_planning(self, monkeypatch):
        mod = _mod()
        client = self._base_client()
        s1 = SimpleNamespace(id=10, title=MagicMock(), episodes=12, status="FINISHED")
        s2 = SimpleNamespace(id=11, title=MagicMock(), episodes=6, status="FINISHED")
        client.get_sequels.return_value = [s1, s2]
        client.format_title.side_effect = lambda t: "Sequel One" if t is s1.title else "Sequel Two"
        client.add_to_list.return_value = True
        monkeypatch.setattr(mod, "anilist_client", client)
        ui = _make_ui_bridge_mock()
        ui.menu_navigate.side_effect = ["Sequel One", "📋 Adicionar à 'Planejo Assistir'"]
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.offer_sequel_and_continue(1, _make_args())
        assert result is False
        client.add_to_list.assert_called()


# ---------------------------------------------------------------------------
# load_episodes_from_cache_or_search
# ---------------------------------------------------------------------------


class TestLoadEpisodesFromCacheOrSearch:
    def test_cache_hit_loads_from_cache(self, monkeypatch):
        mod = _mod()
        cache_data = SimpleNamespace(episode_count=12, episode_urls=list(range(12)))
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: cache_data)
        rep = MagicMock()
        rep.get_anime_titles_with_sources.return_value = ["Anime [src]"]
        monkeypatch.setattr(mod, "rep", rep)
        state, titles = mod.load_episodes_from_cache_or_search("Test", 1, "English", "Romaji")
        assert state is None
        assert titles == ["Anime [src]"]
        rep.load_from_cache.assert_called()

    def test_cache_hit_empty_titles_uses_query(self, monkeypatch):
        mod = _mod()
        cache_data = SimpleNamespace(episode_count=0, episode_urls=[])
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: cache_data)
        rep = MagicMock()
        rep.get_anime_titles_with_sources.return_value = []
        monkeypatch.setattr(mod, "rep", rep)
        state, titles = mod.load_episodes_from_cache_or_search("Test Query", 1, "English", "Romaji")
        assert state is None
        assert titles == ["Test Query"]

    def test_no_cache_uses_incremental_search(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: None)
        fake_state = MagicMock()
        monkeypatch.setattr(
            mod, "incremental_search_anime", lambda q, **kw: (fake_state, ["Result [src]"])
        )
        monkeypatch.setattr(mod, "_rank_anime_results_by_reference", lambda t, r: t)
        state, titles = mod.load_episodes_from_cache_or_search("Test", 1, "English", "Romaji")
        assert state is fake_state
        assert "Result [src]" in titles

    def test_no_cache_no_romaji_skips_ranking(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: None)
        fake_state = MagicMock()
        rank_called = []
        monkeypatch.setattr(mod, "incremental_search_anime", lambda q, **kw: (fake_state, ["R"]))
        monkeypatch.setattr(
            mod, "_rank_anime_results_by_reference", lambda t, r: rank_called.append(True) or t
        )
        state, titles = mod.load_episodes_from_cache_or_search("Test", 1, None, None)
        assert not rank_called


# ---------------------------------------------------------------------------
# _confirm_watch_or_download
# ---------------------------------------------------------------------------


class TestConfirmWatchOrDownload:
    def test_user_watches(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock(menu_returns="▶️ Assistir agora")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        ep_list = [object()] * 5
        result = mod._confirm_watch_or_download("Anime", ep_list, 2, 5, None)
        assert result == 2

    def test_user_downloads(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock(menu_returns="📥 Baixar para assistir depois")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        download_called = []
        monkeypatch.setattr(mod, "_download_episodes", lambda *a, **kw: download_called.append(a))
        ep_list = [object()] * 5
        result = mod._confirm_watch_or_download("Anime", ep_list, 2, 5, None)
        assert result is None
        assert download_called

    def test_user_goes_back_then_watches(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        ui.menu_navigate.side_effect = ["🔙 Voltar", "▶️ Assistir agora"]
        ui.menu_navigate_episodes.return_value = 1
        monkeypatch.setattr(mod, "ui_bridge", ui)
        ep_list = [object()] * 5
        result = mod._confirm_watch_or_download("Anime", ep_list, 2, 5, None)
        assert result == 1

    def test_user_goes_back_and_cancels_episode_select(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        ui.menu_navigate.return_value = "🔙 Voltar"
        ui.menu_navigate_episodes.return_value = None
        monkeypatch.setattr(mod, "ui_bridge", ui)
        ep_list = [object()] * 5
        result = mod._confirm_watch_or_download("Anime", ep_list, 2, 5, None)
        assert result is None

    def test_none_action_returns_none(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock(menu_returns=None)
        monkeypatch.setattr(mod, "ui_bridge", ui)
        ep_list = [object()] * 5
        result = mod._confirm_watch_or_download("Anime", ep_list, 2, 5, None)
        assert result is None


# ---------------------------------------------------------------------------
# _load_episode_list
# ---------------------------------------------------------------------------


class TestLoadEpisodeList:
    def test_cache_hit_returns_cached_list(self, monkeypatch):
        mod = _mod()
        eps = list(range(5))
        cache_data = SimpleNamespace(episode_count=5, episode_urls=eps)
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: cache_data)
        rep = MagicMock()
        monkeypatch.setattr(mod, "rep", rep)
        episode_list, count = mod._load_episode_list("Anime", None, None, None, 1)
        assert episode_list == eps
        assert count == 5

    def test_no_cache_scraped_list_returned(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: None)
        eps = ["ep1", "ep2"]
        rep = MagicMock()
        rep.get_episode_list.return_value = eps
        monkeypatch.setattr(mod, "rep", rep)
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        monkeypatch.setattr(mod, "set_scraper_cache", lambda *a: None)
        episode_list, count = mod._load_episode_list("Anime", None, None, None, 0)
        assert episode_list == eps
        assert count == 2

    def test_no_episodes_returns_none(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: None)
        rep = MagicMock()
        rep.get_episode_list.return_value = []
        monkeypatch.setattr(mod, "rep", rep)
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        episode_list, count = mod._load_episode_list("Anime", None, None, None, 0)
        assert episode_list is None
        assert count == 0

    def test_saved_title_with_urls_adds_anime(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: None)
        rep = MagicMock()
        eps = ["ep1"]
        rep.get_episode_list.return_value = eps
        monkeypatch.setattr(mod, "rep", rep)
        monkeypatch.setattr(mod, "load_anilist_urls", lambda aid: {"src1": "http://url1"})
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        monkeypatch.setattr(mod, "set_scraper_cache", lambda *a: None)
        episode_list, count = mod._load_episode_list("Anime", "Anime", "src1", "http://url1", 1)
        rep.add_anime.assert_called()

    def test_saved_title_with_fallback_url(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: None)
        rep = MagicMock()
        eps = ["ep1"]
        rep.get_episode_list.return_value = eps
        monkeypatch.setattr(mod, "rep", rep)
        monkeypatch.setattr(mod, "load_anilist_urls", lambda aid: {})
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        monkeypatch.setattr(mod, "set_scraper_cache", lambda *a: None)
        episode_list, count = mod._load_episode_list("Anime", "Anime", "src1", "http://url1", 1)
        rep.add_anime.assert_called_with("Anime", "http://url1", "src1")


# ---------------------------------------------------------------------------
# _find_awaiting_episode_idx
# ---------------------------------------------------------------------------


class TestFindAwaitingEpisodeIdx:
    def test_no_results_returns_none(self, monkeypatch):
        mod = _mod()
        rep = MagicMock()
        rep.search_homepage_incremental.return_value = []
        monkeypatch.setattr(mod, "rep", rep)
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod._find_awaiting_episode_idx("Anime", 5)
        assert result is None

    def test_episode_found_registers_and_returns_idx(self, monkeypatch):
        mod = _mod()
        rep = MagicMock()
        rep.search_homepage_incremental.return_value = [
            {"episode_number": 5, "episode_url": "http://ep5"}
        ]
        monkeypatch.setattr(mod, "rep", rep)
        registry = MagicMock()
        monkeypatch.setattr(mod, "awaiting_registry", registry)
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod._find_awaiting_episode_idx("Anime", 5)
        assert result == 4  # 5 - 1
        registry.set.assert_called_with("Anime", 5, "http://ep5")

    def test_episode_not_in_results_returns_none(self, monkeypatch):
        mod = _mod()
        rep = MagicMock()
        rep.search_homepage_incremental.return_value = [
            {"episode_number": 3, "episode_url": "http://ep3"}
        ]
        monkeypatch.setattr(mod, "rep", rep)
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod._find_awaiting_episode_idx("Anime", 5)
        assert result is None

    def test_network_error_returns_none(self, monkeypatch):
        mod = _mod()
        rep = MagicMock()
        rep.search_homepage_incremental.side_effect = ConnectionError("timeout")
        monkeypatch.setattr(mod, "rep", rep)
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod._find_awaiting_episode_idx("Anime", 5)
        assert result is None

    def test_unexpected_exception_returns_none(self, monkeypatch):
        mod = _mod()
        rep = MagicMock()
        rep.search_homepage_incremental.side_effect = RuntimeError("unexpected")
        monkeypatch.setattr(mod, "rep", rep)
        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod._find_awaiting_episode_idx("Anime", 5)
        assert result is None


# ---------------------------------------------------------------------------
# _maybe_offer_sequel_on_finish
# ---------------------------------------------------------------------------


class TestMaybeOfferSequelOnFinish:
    def test_no_anilist_id_offers_sequel_anyway(self, monkeypatch):
        mod = _mod()
        client = MagicMock()
        client.get_anime_by_id.return_value = None
        monkeypatch.setattr(mod, "anilist_client", client)
        monkeypatch.setattr(mod, "offer_sequel_and_continue", lambda *a, **kw: False)
        result = mod._maybe_offer_sequel_on_finish(0, _make_args(), 5)
        assert result is False

    def test_with_anime_info_passes_episodes(self, monkeypatch):
        mod = _mod()
        client = MagicMock()
        anime = SimpleNamespace(episodes=12)
        client.get_anime_by_id.return_value = anime
        monkeypatch.setattr(mod, "anilist_client", client)
        calls = []
        monkeypatch.setattr(
            mod, "offer_sequel_and_continue", lambda *a, **kw: calls.append(kw) or True
        )
        result = mod._maybe_offer_sequel_on_finish(1, _make_args(), 12)
        assert result is True
        assert calls[0]["anilist_episodes"] == 12


# ---------------------------------------------------------------------------
# select_anime_from_results - simple path
# ---------------------------------------------------------------------------


class TestSelectAnimeFromResults:
    def _make_simple_search_state(self, query="test"):
        state = MagicMock()
        state.get_current.return_value = SimpleNamespace(
            query=query,
            used_query=query,
            word_count=2,
            results=["Result A [src]"],
        )
        state.can_toggle_language.return_value = False
        state.get_alternative_language.return_value = None
        return state

    def test_user_cancels_returns_none_triple(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock(menu_returns=None)
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.select_anime_from_results(
            ["Anime A [src]"], None, "test", "Test", None, None, 1
        )
        assert result == (None, None, None)

    def test_user_selects_anime_without_source(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        # Normalize: "anime a" is what would be shown (without bracket)
        ui.menu_navigate.return_value = "anime a"
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.select_anime_from_results(["Anime A"], None, "test", "Test", None, None, 1)
        selected, source, _ = result
        assert selected == "Anime A"
        assert source is None

    def test_user_selects_anime_with_source(self, monkeypatch):
        mod = _mod()
        ui = _make_ui_bridge_mock()
        ui.menu_navigate.return_value = "anime a [mysrc]"
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod.select_anime_from_results(
            ["Anime A [mysrc]"], None, "test", "Test", None, None, 1
        )
        selected, source, _ = result
        assert selected == "Anime A"
        assert source == "mysrc"


# ---------------------------------------------------------------------------
# _search_and_select_anime
# ---------------------------------------------------------------------------


class TestSearchAndSelectAnime:
    def test_no_results_user_searches_manually(self, monkeypatch):
        mod = _mod()
        call_count = [0]

        def fake_load(*a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return None, []  # first call: no results
            return None, ["Manual Anime [src]"]  # second call: found

        monkeypatch.setattr(mod, "load_episodes_from_cache_or_search", fake_load)
        ui = _make_ui_bridge_mock(menu_returns="🔍 Buscar manualmente")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        monkeypatch.setattr(
            mod, "select_anime_from_results", lambda *a, **kw: ("Manual Anime", "src", "manual")
        )
        result = mod._search_and_select_anime(
            "Anime",
            1,
            "Eng",
            "Rom",
            "Display",
            lambda prompt: "manual query",
        )
        selected, source, _ = result
        assert selected == "Manual Anime"

    def test_no_results_user_cancels_back(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(mod, "load_episodes_from_cache_or_search", lambda *a, **kw: (None, []))
        ui = _make_ui_bridge_mock(menu_returns="🔙 Voltar ao AniList")
        monkeypatch.setattr(mod, "ui_bridge", ui)
        result = mod._search_and_select_anime(
            "Anime",
            1,
            "Eng",
            "Rom",
            "Display",
            lambda prompt: "unused",
        )
        assert result[0] is None

    def test_has_results_selects(self, monkeypatch):
        mod = _mod()
        monkeypatch.setattr(
            mod, "load_episodes_from_cache_or_search", lambda *a, **kw: (None, ["Result [src]"])
        )
        monkeypatch.setattr(
            mod, "select_anime_from_results", lambda *a, **kw: ("Result", "src", "Result")
        )
        result = mod._search_and_select_anime(
            "Anime",
            1,
            None,
            None,
            "Display",
            lambda prompt: "unused",
        )
        assert result[0] == "Result"


# ---------------------------------------------------------------------------
# _persist_anime_choice
# ---------------------------------------------------------------------------


class TestPersistAnimeChoice:
    def test_direct_url_lookup(self, monkeypatch):
        mod = _mod()
        rep = MagicMock()
        rep.anime_to_urls = {"Selected Anime": [("http://url", "src", {})]}
        monkeypatch.setattr(mod, "rep", rep)
        save_calls = []
        monkeypatch.setattr(mod, "save_anilist_mapping", lambda *a, **kw: save_calls.append(kw))
        mod._persist_anime_choice(1, "Selected Anime", "Selected Anime", "src")
        assert save_calls
        assert save_calls[0]["anime_url"] == "http://url"

    def test_fuzzy_fallback(self, monkeypatch):
        mod = _mod()
        rep = MagicMock()
        rep.anime_to_urls = {"Selected Anime Extended": [("http://url2", "src", {})]}
        monkeypatch.setattr(mod, "rep", rep)
        save_calls = []
        monkeypatch.setattr(mod, "save_anilist_mapping", lambda *a, **kw: save_calls.append(kw))
        mod._persist_anime_choice(1, "Selected Anime", "Selected Anime", "src")
        # Should fall through to fuzzy and find the close match
        assert save_calls

    def test_no_urls_saves_empty(self, monkeypatch):
        mod = _mod()
        rep_mock = MagicMock()
        rep_mock.anime_to_urls = {}
        monkeypatch.setattr(mod, "rep", rep_mock)
        save_calls = []
        monkeypatch.setattr(mod, "save_anilist_mapping", lambda *a, **kw: save_calls.append(kw))
        mod._persist_anime_choice(1, "Unknown Anime", "Unknown Anime", None)
        assert save_calls
        assert save_calls[0]["anime_url"] is None


# ---------------------------------------------------------------------------
# anilist_anime_flow - main flow tests
# ---------------------------------------------------------------------------


class TestAnilistAnimeFlow:
    def _patch_everything(self, monkeypatch, mod, *, menu_side_effect=None, episode_list=None):
        """Set up all common mocks for the main flow."""
        client = MagicMock()
        client.get_anime_by_id.return_value = SimpleNamespace(
            title=SimpleNamespace(english="English", romaji="Romaji")
        )
        monkeypatch.setattr(mod, "anilist_client", client)

        loader_mock = MagicMock()
        monkeypatch.setattr(mod, "loader", loader_mock)

        rep_mock = MagicMock()
        rep_mock.anime_to_anilist_id = {}
        rep_mock.get_active_sources.return_value = ["src1"]
        ep_list = episode_list or ["ep1", "ep2", "ep3"]
        rep_mock.get_episode_list.return_value = ep_list
        rep_mock.anime_to_urls = {}
        monkeypatch.setattr(mod, "rep", rep_mock)

        monkeypatch.setattr(mod, "load_anilist_mapping", lambda aid: (None, None, None))
        monkeypatch.setattr(mod, "save_anilist_mapping", lambda *a, **kw: None)
        monkeypatch.setattr(mod, "load_language_preference", lambda aid: None)
        monkeypatch.setattr(mod, "save_language_preference", lambda aid, lang: None)
        monkeypatch.setattr(mod, "get_scraper_cache", lambda q: None)
        monkeypatch.setattr(mod, "set_scraper_cache", lambda *a: None)
        monkeypatch.setattr(
            mod, "incremental_search_anime", lambda q, **kw: (None, ["Test Anime [src]"])
        )
        monkeypatch.setattr(mod, "_rank_anime_results_by_reference", lambda t, r: t)

        ui = _make_ui_bridge_mock()
        if menu_side_effect is not None:
            ui.menu_navigate.side_effect = menu_side_effect
        monkeypatch.setattr(mod, "ui_bridge", ui)

        registry_mock = MagicMock()
        monkeypatch.setattr(mod, "awaiting_registry", registry_mock)

        monkeypatch.setattr(mod, "_read_local_progress", lambda a: 0)
        monkeypatch.setattr(mod, "_run_playback_loop", lambda *a, **kw: None)
        monkeypatch.setattr(mod, "reset_history", lambda a: None)

        return client, rep_mock, ui

    def test_user_cancelled_at_title_choice_returns(self, monkeypatch):
        mod = _mod()
        client, rep_mock, ui = self._patch_everything(monkeypatch, mod)
        # _prompt_saved_title_choice gets cancelled=True (user presses esc)
        monkeypatch.setattr(mod, "_prompt_saved_title_choice", lambda a, b: (None, None, True))
        mod.anilist_anime_flow("Anime", 1, _make_args())
        # Should return without calling _run_playback_loop (already mocked as no-op)

    def test_no_saved_title_searches_and_plays(self, monkeypatch):
        mod = _mod()
        client, rep_mock, ui = self._patch_everything(monkeypatch, mod)
        monkeypatch.setattr(mod, "_prompt_saved_title_choice", lambda a, b: (None, None, False))
        # select_anime_from_results returns an anime
        ui.menu_navigate.return_value = "test anime [src]"
        # _resolve_start_episode_idx returns 0 (no progress)
        monkeypatch.setattr(mod, "_resolve_start_episode_idx", lambda *a, **kw: 0)
        # _confirm_watch_or_download returns 0
        monkeypatch.setattr(mod, "_confirm_watch_or_download", lambda *a, **kw: 0)
        play_calls = []
        monkeypatch.setattr(mod, "_run_playback_loop", lambda *a, **kw: play_calls.append(True))
        mod.anilist_anime_flow("Test Anime", 1, _make_args())
        assert play_calls

    def test_saved_title_skips_search(self, monkeypatch):
        mod = _mod()
        client, rep_mock, ui = self._patch_everything(monkeypatch, mod)
        monkeypatch.setattr(
            mod, "_prompt_saved_title_choice", lambda a, b: ("Saved Anime", "src1", False)
        )
        # No search should happen
        search_called = []
        monkeypatch.setattr(
            mod,
            "_search_and_select_anime",
            lambda *a, **kw: search_called.append(True) or (None, None, None),
        )
        monkeypatch.setattr(mod, "_load_episode_list", lambda *a: (["ep1"], 1))
        monkeypatch.setattr(mod, "_resolve_start_episode_idx", lambda *a, **kw: 0)
        monkeypatch.setattr(mod, "_confirm_watch_or_download", lambda *a, **kw: 0)
        monkeypatch.setattr(mod, "_run_playback_loop", lambda *a, **kw: None)
        mod.anilist_anime_flow("Test Anime", 1, _make_args())
        assert not search_called

    def test_no_episode_list_returns_early(self, monkeypatch):
        mod = _mod()
        client, rep_mock, ui = self._patch_everything(monkeypatch, mod)
        monkeypatch.setattr(
            mod, "_prompt_saved_title_choice", lambda a, b: ("Saved Anime", "src1", False)
        )
        monkeypatch.setattr(mod, "_load_episode_list", lambda *a: (None, 0))
        play_calls = []
        monkeypatch.setattr(mod, "_run_playback_loop", lambda *a, **kw: play_calls.append(True))
        mod.anilist_anime_flow("Test Anime", 1, _make_args())
        assert not play_calls

    def test_user_cancels_episode_selection_returns(self, monkeypatch):
        mod = _mod()
        client, rep_mock, ui = self._patch_everything(monkeypatch, mod)
        monkeypatch.setattr(
            mod, "_prompt_saved_title_choice", lambda a, b: ("Saved Anime", "src1", False)
        )
        monkeypatch.setattr(mod, "_load_episode_list", lambda *a: (["ep1", "ep2"], 2))
        monkeypatch.setattr(mod, "_resolve_start_episode_idx", lambda *a, **kw: None)
        play_calls = []
        monkeypatch.setattr(mod, "_run_playback_loop", lambda *a, **kw: play_calls.append(True))
        mod.anilist_anime_flow("Test Anime", 1, _make_args())
        assert not play_calls

    def test_user_cancels_watch_or_download_returns(self, monkeypatch):
        mod = _mod()
        client, rep_mock, ui = self._patch_everything(monkeypatch, mod)
        monkeypatch.setattr(
            mod, "_prompt_saved_title_choice", lambda a, b: ("Saved Anime", "src1", False)
        )
        monkeypatch.setattr(mod, "_load_episode_list", lambda *a: (["ep1"], 1))
        monkeypatch.setattr(mod, "_resolve_start_episode_idx", lambda *a, **kw: 0)
        monkeypatch.setattr(mod, "_confirm_watch_or_download", lambda *a, **kw: None)
        play_calls = []
        monkeypatch.setattr(mod, "_run_playback_loop", lambda *a, **kw: play_calls.append(True))
        mod.anilist_anime_flow("Test Anime", 1, _make_args())
        assert not play_calls

    def test_display_title_defaults_to_anime_title(self, monkeypatch):
        mod = _mod()
        client, rep_mock, ui = self._patch_everything(monkeypatch, mod)
        monkeypatch.setattr(mod, "_prompt_saved_title_choice", lambda a, b: (None, None, True))
        # Just verify no crash
        mod.anilist_anime_flow("Anime Title Without Display", 1, _make_args())


# ---------------------------------------------------------------------------
# _run_playback_loop - additional branches
# ---------------------------------------------------------------------------


class TestRunPlaybackLoopBranches:
    from services.anime.playback_fallback import PlaybackFallbackResult
    from utils.video_player import VideoPlaybackResult

    def _make_fallback(self, action, episode, exit_code=0):
        from services.anime.playback_fallback import PlaybackFallbackResult
        from utils.video_player import VideoPlaybackResult

        return PlaybackFallbackResult(
            playback_result=VideoPlaybackResult(
                exit_code=exit_code,
                action=action,
                data={"episode": episode},
            ),
            source_used="test-src",
            sources_tried=[("test-src", 0)],
            all_failed=False,
        )

    def _setup(self, monkeypatch, sources_per_ep=1):
        mod = _mod()
        ep_list = [object(), object(), object()]

        rep = MagicMock()
        rep.get_all_episode_sources.side_effect = lambda anime, ep: (
            [(f"http://ep{ep}", "test-src")] * sources_per_ep
        )
        rep.search_player_from_page.side_effect = lambda url, src: url
        rep.get_episode_list.return_value = ep_list
        monkeypatch.setattr(mod, "rep", rep)

        monkeypatch.setattr(mod, "_sync_anilist_progress", lambda *a, **kw: None)
        monkeypatch.setattr(mod, "_maybe_offer_sequel_on_finish", lambda *a, **kw: False)
        monkeypatch.setattr(mod, "save_history", lambda *a, **kw: None)

        ui = _make_ui_bridge_mock()
        monkeypatch.setattr(mod, "ui_bridge", ui)

        player = MagicMock()
        player.get_autoplay_state.return_value = False
        monkeypatch.setattr(mod, "VideoPlayer", lambda: player)

        return mod, ep_list, rep, ui

    def test_no_sources_breaks_loop(self, monkeypatch):
        mod = _mod()
        rep = MagicMock()
        rep.get_all_episode_sources.return_value = []
        monkeypatch.setattr(mod, "rep", rep)
        monkeypatch.setattr(mod, "_sync_anilist_progress", lambda *a: None)
        monkeypatch.setattr(mod, "_maybe_offer_sequel_on_finish", lambda *a, **kw: False)
        monkeypatch.setattr(mod, "save_history", lambda *a, **kw: None)
        monkeypatch.setattr(mod, "ui_bridge", _make_ui_bridge_mock())

        mod._run_playback_loop("Anime", "src", "Display", 0, [object()], 1, None, _make_args())

    def test_quit_action_updates_episode(self, monkeypatch):
        mod, ep_list, rep, ui = self._setup(monkeypatch)
        fallback = self._make_fallback("quit", 2, exit_code=0)

        monkeypatch.setattr(mod, "play_episode_with_fallback", lambda **kw: fallback)

        # After quit: confirm watching (marks watched), then exit via menu
        ui.menu_navigate.side_effect = [
            "✅ Sim, assisti até o final",  # confirm watched
            "↩️  Voltar ao menu anterior",  # exit
        ]
        mod._run_playback_loop("Anime", None, "Display", 0, ep_list, 1, None, _make_args())

    def test_previous_action_goes_back(self, monkeypatch):
        mod, ep_list, rep, ui = self._setup(monkeypatch)
        call_count = [0]

        def play_fallback(**kw):
            call_count[0] += 1
            from services.anime.playback_fallback import PlaybackFallbackResult
            from utils.video_player import VideoPlaybackResult

            if call_count[0] == 1:
                return PlaybackFallbackResult(
                    playback_result=VideoPlaybackResult(
                        exit_code=0, action="previous", data={"episode": 1}
                    ),
                    source_used="src",
                    sources_tried=[("src", 0)],
                    all_failed=False,
                )
            else:
                return PlaybackFallbackResult(
                    playback_result=VideoPlaybackResult(
                        exit_code=0, action="quit", data={"episode": 1}
                    ),
                    source_used="src",
                    sources_tried=[("src", 0)],
                    all_failed=False,
                )

        monkeypatch.setattr(mod, "play_episode_with_fallback", play_fallback)
        ui.menu_navigate.side_effect = [
            "✅ Sim, assisti até o final",  # after quit confirm
            "↩️  Voltar ao menu anterior",  # exit
        ]
        mod._run_playback_loop("Anime", None, "Display", 1, ep_list, 1, None, _make_args())
        assert call_count[0] == 2

    def test_reload_action_continues(self, monkeypatch):
        mod, ep_list, rep, ui = self._setup(monkeypatch)
        call_count = [0]

        def play_fallback(**kw):
            call_count[0] += 1
            from services.anime.playback_fallback import PlaybackFallbackResult
            from utils.video_player import VideoPlaybackResult

            if call_count[0] == 1:
                return PlaybackFallbackResult(
                    playback_result=VideoPlaybackResult(exit_code=0, action="reload", data={}),
                    source_used="src",
                    sources_tried=[("src", 0)],
                    all_failed=False,
                )
            else:
                return PlaybackFallbackResult(
                    playback_result=VideoPlaybackResult(
                        exit_code=0, action="quit", data={"episode": 1}
                    ),
                    source_used="src",
                    sources_tried=[("src", 0)],
                    all_failed=False,
                )

        monkeypatch.setattr(mod, "play_episode_with_fallback", play_fallback)
        ui.menu_navigate.side_effect = [
            "✅ Sim, assisti até o final",
            "↩️  Voltar ao menu anterior",
        ]
        mod._run_playback_loop("Anime", None, "Display", 0, ep_list, 1, None, _make_args())
        assert call_count[0] == 2

    def test_mark_menu_action_does_not_crash(self, monkeypatch):
        mod, ep_list, rep, ui = self._setup(monkeypatch)

        def play_fallback(**kw):
            from services.anime.playback_fallback import PlaybackFallbackResult
            from utils.video_player import VideoPlaybackResult

            return PlaybackFallbackResult(
                playback_result=VideoPlaybackResult(exit_code=0, action="mark-menu", data={}),
                source_used="src",
                sources_tried=[("src", 0)],
                all_failed=False,
            )

        monkeypatch.setattr(mod, "play_episode_with_fallback", play_fallback)
        ui.menu_navigate.side_effect = [
            "✅ Sim, assisti até o final",
            "↩️  Voltar ao menu anterior",
        ]
        mod._run_playback_loop("Anime", None, "Display", 0, ep_list, 1, None, _make_args())

    def test_next_action_advances_episode(self, monkeypatch):
        mod, ep_list, rep, ui = self._setup(monkeypatch)
        call_count = [0]

        def play_fallback(**kw):
            call_count[0] += 1
            from services.anime.playback_fallback import PlaybackFallbackResult
            from utils.video_player import VideoPlaybackResult

            if call_count[0] == 1:
                return PlaybackFallbackResult(
                    playback_result=VideoPlaybackResult(
                        exit_code=0, action="next", data={"episode": 2}
                    ),
                    source_used="src",
                    sources_tried=[("src", 0)],
                    all_failed=False,
                )
            else:
                # Quit from episode 2
                return PlaybackFallbackResult(
                    playback_result=VideoPlaybackResult(
                        exit_code=0, action="quit", data={"episode": 2}
                    ),
                    source_used="src",
                    sources_tried=[("src", 0)],
                    all_failed=False,
                )

        monkeypatch.setattr(mod, "play_episode_with_fallback", play_fallback)
        ui.menu_navigate.side_effect = [
            "✅ Sim, assisti até o final",
            "↩️  Voltar ao menu anterior",
        ]
        mod._run_playback_loop("Anime", None, "Display", 0, ep_list, 1, None, _make_args())
        assert call_count[0] == 2

    def test_post_playback_choose_episode(self, monkeypatch):
        mod, ep_list, rep, ui = self._setup(monkeypatch)

        def play_fallback(**kw):
            from services.anime.playback_fallback import PlaybackFallbackResult
            from utils.video_player import VideoPlaybackResult

            return PlaybackFallbackResult(
                playback_result=VideoPlaybackResult(
                    exit_code=0, action="quit", data={"episode": 1}
                ),
                source_used="src",
                sources_tried=[("src", 0)],
                all_failed=False,
            )

        monkeypatch.setattr(mod, "play_episode_with_fallback", play_fallback)
        call_count = [0]

        def menu_nav(options, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return "✅ Sim, assisti até o final"
            elif call_count[0] == 2:
                return "📋 Escolher outro episódio"
            else:
                return None  # cancel from episode selector

        ui.menu_navigate.side_effect = menu_nav
        ui.menu_navigate_episodes.return_value = None
        mod._run_playback_loop("Anime", None, "Display", 0, ep_list, 1, None, _make_args())
