"""Unit tests for AniList integration playback menus."""

import importlib
from types import SimpleNamespace

from services.anime.playback_service import PlaybackFallbackResult
from utils.video_player import VideoPlaybackResult


def test_build_anilist_post_playback_options_middle_episode():
    """Middle episode should include next and previous navigation."""
    mod = importlib.import_module("services.anime.anilist_integration")

    opts = mod.build_anilist_post_playback_options(current_episode_idx=4, num_episodes=12)

    assert any("▶️  Próximo" == opt for opt in opts)
    assert any("◀️  Anterior" == opt for opt in opts)
    assert "🔁 Replay" in opts


def test_playback_loop_preserves_autoplay_between_episodes(monkeypatch):
    """The player carrying session state must be reused for auto-next episodes."""
    mod = importlib.import_module("services.anime.anilist_integration")
    players = []
    autoplay_states = []

    class Repository:
        @staticmethod
        def get_all_episode_sources(_anime, episode):
            return [(f"https://example.test/{episode}", "test-source")]

        @staticmethod
        def search_player_from_page(url, _source):
            return url

    def play_with_fallback(*, player, episode_number, **_kwargs):
        players.append(player)
        autoplay_states.append(player.get_autoplay_state())
        if episode_number == 1:
            player.set_autoplay_state(True)
        return PlaybackFallbackResult(
            playback_result=VideoPlaybackResult(
                exit_code=0,
                action="auto-next",
                data={"episode": episode_number},
            ),
            source_used="test-source",
            sources_tried=[("test-source", 0)],
            all_failed=False,
        )

    monkeypatch.setattr(mod, "rep", Repository())
    monkeypatch.setattr(mod, "play_episode_with_fallback", play_with_fallback)
    monkeypatch.setattr(mod, "sync_anilist_progress", lambda *_args: None)
    monkeypatch.setattr(mod, "_maybe_offer_sequel_on_finish", lambda *_args: False)

    mod._run_playback_loop(
        selected_anime="Test Anime",
        source="test-source",
        display_title="Test Anime",
        start_episode_idx=0,
        episode_list=[object(), object()],
        anilist_id=1,
        total_episodes=2,
        args=SimpleNamespace(debug=False),
    )

    assert len(players) == 2
    assert players[0] is players[1]
    assert autoplay_states == [False, True]


def test_build_anilist_post_playback_options_last_episode_prioritizes_back_option():
    """Last episode should offer a safe back option as the first choice."""
    mod = importlib.import_module("services.anime.anilist_integration")

    opts = mod.build_anilist_post_playback_options(current_episode_idx=6, num_episodes=7)

    assert opts[0] == "↩️  Voltar ao menu anterior"
    assert not any("▶️  Próximo" == opt for opt in opts)
    assert any("◀️  Anterior" == opt for opt in opts)
    assert "🔁 Replay" in opts
