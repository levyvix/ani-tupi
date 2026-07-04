"""Unit tests for anime command menu layering helpers."""

import importlib
from unittest.mock import patch
from types import SimpleNamespace


def _make_ctx(episode_idx: int = 1, total: int = 3):
    """Create PlaybackContext test fixture."""
    mod = importlib.import_module("services.anime.playback_service")
    return mod.PlaybackContext(
        anime_title="Test Anime",
        episode_idx=episode_idx,
        source="animefire",
        anilist_id=None,
        anilist_title=None,
        total_episodes_anilist=None,
        num_episodes=total,
        episode_list=tuple(f"Episódio {i}" for i in range(1, total + 1)),
    )


def test_build_post_playback_options_middle_episode():
    """Should include previous and next options when not at boundaries."""
    anime_cmd = importlib.import_module("commands.anime")
    ctx = _make_ctx(episode_idx=1, total=3)

    opts = anime_cmd.build_post_playback_options(ctx)

    assert any("▶️  Próximo" in opt for opt in opts)
    assert any("◀️  Anterior" in opt for opt in opts)
    assert "📋 Escolher outro episódio" in opts
    assert "📥 Baixar para assistir depois" in opts
    assert "🔄 Trocar fonte" in opts


def test_build_post_playback_options_last_episode_prioritizes_back_option():
    """Last episode should offer a safe back option before previous episode."""
    anime_cmd = importlib.import_module("commands.anime")
    ctx = _make_ctx(episode_idx=2, total=3)

    opts = anime_cmd.build_post_playback_options(ctx)

    assert opts[0] == "↩️  Voltar ao menu anterior"
    assert not any("▶️  Próximo" in opt for opt in opts)
    assert any("◀️  Anterior" in opt for opt in opts)


def test_select_episode_from_menu_returns_none_on_back():
    """Back from episode selection should return None, not raise/exit."""
    anime_cmd = importlib.import_module("commands.anime")
    ctx = _make_ctx()

    with patch.object(anime_cmd, "menu_navigate_episodes", return_value=None):
        selected_ctx = anime_cmd.select_episode_from_menu(ctx)

    assert selected_ctx is None


def test_select_episode_from_menu_returns_updated_context():
    """Selecting an episode should navigate to chosen index."""
    anime_cmd = importlib.import_module("commands.anime")
    ctx = _make_ctx(episode_idx=0, total=3)

    with patch.object(anime_cmd, "menu_navigate_episodes", return_value=2):
        with patch.object(anime_cmd, "navigate_episodes", return_value="new_ctx") as mock_nav:
            selected_ctx = anime_cmd.select_episode_from_menu(ctx)

    assert selected_ctx == "new_ctx"
    mock_nav.assert_called_once_with(ctx, "choose", 2)


def test_build_episode_sources_keeps_fast_path_and_fallback_sources():
    """Fast-path URL should not suppress repository fallback sources."""
    anime_cmd = importlib.import_module("commands.anime")
    url_result = SimpleNamespace(
        success=True,
        player_url="https://cdn.example.com/ep8.m3u8",
        source="animefire",
    )

    with patch.object(
        anime_cmd.rep,
        "get_all_episode_sources",
        return_value=[
            ("https://animefire.example/ep8", "animefire"),
            ("https://animesdigital.example/ep8", "animesdigital"),
            ("https://anitube.example/ep8", "anitube"),
        ],
    ):
        with patch.object(
            anime_cmd.rep,
            "search_player_from_page",
            side_effect=[
                ["https://animesdigital.cdn/ep8.m3u8", "https://animesdigital.cdn/ep8-blogger.mp4"],
                ["https://anitube.cdn/ep8.m3u8"],
            ],
        ) as mock_extract:
            sources = anime_cmd.build_episode_sources("Kami no Shizuku", 8, url_result)

    assert sources == [
        ("https://cdn.example.com/ep8.m3u8", "animefire", None),
        (
            "https://animesdigital.cdn/ep8.m3u8",
            "animesdigital",
            "https://animesdigital.example/ep8",
        ),
        (
            "https://animesdigital.cdn/ep8-blogger.mp4",
            "animesdigital",
            "https://animesdigital.example/ep8",
        ),
        ("https://anitube.cdn/ep8.m3u8", "anitube", "https://anitube.example/ep8"),
    ]
    assert mock_extract.call_count == 2
