"""Tests for local anime library navigation flow."""

import importlib
from pathlib import Path

from utils.video_player import VideoPlaybackResult


class _FakeLocalAnimeService:
    """In-memory local anime service for flow tests."""

    def __init__(self, base: Path):
        self._episodes: dict[str, list[tuple[int, Path]]] = {
            "Naruto": [(1, base / "1.mp4"), (2, base / "2.mp4")],
            "Bleach": [(1, base / "10.mp4")],
        }

    def get_downloaded_anime_list(self) -> list[str]:
        return sorted([title for title, episodes in self._episodes.items() if episodes])

    def get_anime_info(self, anime_title: str) -> dict:
        return {"total_episodes": len(self._episodes.get(anime_title, []))}

    def get_downloaded_episodes(self, anime_title: str) -> list[tuple[int, Path]]:
        if anime_title not in self._episodes:
            raise FileNotFoundError(anime_title)
        return list(self._episodes[anime_title])

    def delete_episode(self, anime_title: str, episode_num: int) -> bool:
        if anime_title not in self._episodes:
            return False
        original = self._episodes[anime_title]
        kept = [entry for entry in original if entry[0] != episode_num]
        self._episodes[anime_title] = kept
        return len(kept) != len(original)


def _patch_common(monkeypatch, tmp_path, menu_returns):
    """Patch local anime command dependencies for deterministic tests."""
    anime_cmd = importlib.import_module("commands.anime")
    local_anime = importlib.import_module("commands.local_anime")

    service = _FakeLocalAnimeService(tmp_path)
    calls = []
    menu_iter = iter(menu_returns)

    def fake_menu(opts, msg="", **kwargs):
        calls.append((msg, list(opts)))
        return next(menu_iter)

    class FakePlayer:
        call_count = 0

        def play_episode(self, **kwargs):
            FakePlayer.call_count += 1
            return VideoPlaybackResult(exit_code=0, action="quit", data=None)

    monkeypatch.setattr(local_anime, "LocalAnimeService", lambda: service)
    monkeypatch.setattr(local_anime, "menu_navigate", fake_menu)
    monkeypatch.setattr(local_anime, "VideoPlayer", FakePlayer)
    monkeypatch.setattr(local_anime, "_discover_anilist_id", lambda _title: None)
    monkeypatch.setattr(anime_cmd, "handle_post_playback_confirmation", lambda **kwargs: True)

    return local_anime, calls, FakePlayer


def test_back_inside_anime_returns_to_local_library_list(monkeypatch, tmp_path):
    """Back from episode list should return to anime list, not exit local library."""
    local_anime, calls, fake_player = _patch_common(
        monkeypatch,
        tmp_path,
        [
            "Naruto (2 eps)",  # Select anime
            None,  # Back from episode list
            None,  # Exit from local library anime list
        ],
    )

    local_anime.handle_local_library_playback(args=None)

    local_menu_calls = [msg for msg, _ in calls if "Biblioteca Local - Selecione um anime" in msg]
    assert len(local_menu_calls) == 2
    assert fake_player.call_count == 0


def test_post_playback_back_to_anime_library_returns_to_episode_list(monkeypatch, tmp_path):
    """Back to anime library after playback should land on episode list of same anime."""
    local_anime, calls, fake_player = _patch_common(
        monkeypatch,
        tmp_path,
        [
            "Naruto (2 eps)",  # Select anime
            "Episódio 1",  # Select episode
            "▶️  Assistir agora",  # Episode actions
            "📚 Voltar à biblioteca do anime",  # Post playback
            None,  # Back from episode list to anime list
            None,  # Exit local library list
        ],
    )

    local_anime.handle_local_library_playback(args=None)

    episode_list_calls = [msg for msg, _ in calls if "Selecione um episódio" in msg]
    assert len(episode_list_calls) == 2
    assert fake_player.call_count == 1


def test_post_playback_back_to_local_library_returns_to_anime_list(monkeypatch, tmp_path):
    """Back to local library after playback should jump to anime list directly."""
    local_anime, calls, _ = _patch_common(
        monkeypatch,
        tmp_path,
        [
            "Naruto (2 eps)",  # Select anime
            "Episódio 1",  # Select episode
            "▶️  Assistir agora",  # Episode actions
            "📂 Voltar à biblioteca local",  # Post playback
            None,  # Exit local library list
        ],
    )

    local_anime.handle_local_library_playback(args=None)

    local_menu_calls = [msg for msg, _ in calls if "Biblioteca Local - Selecione um anime" in msg]
    episode_list_calls = [msg for msg, _ in calls if "Selecione um episódio" in msg]
    assert len(local_menu_calls) == 2
    assert len(episode_list_calls) == 1
