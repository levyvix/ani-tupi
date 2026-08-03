"""Integration tests for the UI-decoupled service layer (review item C2).

These services no longer import from ``ui.*`` nor call the global ``input()``.
Instead they accept injected UI callables. The tests here exercise the real
business logic with plain fake callables (no ``ui.components`` patching),
proving the services are usable without a terminal.

Only genuine external boundaries (AniList client, filesystem) are stubbed.
"""

from contextlib import nullcontext

from models.models import ScrapedEpisodes
from utils.persistence import JSONStore


class EpisodePlugin:
    """Real-ish scraper plugin that yields a fixed number of episodes."""

    def __init__(self, name: str, episode_count: int):
        self.name = name
        self.episode_count = episode_count

    def search_episodes(self, anime: str, url: str, params):
        titles = [f"Episode {i + 1}" for i in range(self.episode_count)]
        urls = [f"{url}/ep{i + 1}" for i in range(self.episode_count)]
        return [ScrapedEpisodes(titles=titles, urls=urls, source=self.name)]


def _progress(_msg="Carregando..."):
    """Fake cosmetic spinner - a no-op context manager."""
    return nullcontext()


class ScriptedMenu:
    """Fake ``menu_navigate`` that returns queued answers and records calls."""

    def __init__(self, answers):
        self._answers = iter(answers)
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, opts, msg="", **kwargs):
        self.calls.append((list(opts), msg))
        return next(self._answers)


# ---------------------------------------------------------------------------
# history_service.load_history - injected UI, no ui.components involvement
# ---------------------------------------------------------------------------


class TestLoadHistoryInjectedUI:
    def test_saved_urls_path_returns_contract_tuple(self, temp_dir, repository, monkeypatch):
        """load_history resolves via injected callables and honours the
        (anime, episode_idx, anilist_id, anilist_title) contract."""
        from services.core import history_service

        store = JSONStore(temp_dir / "history.json")
        monkeypatch.setattr(history_service, "_history_store", store)
        monkeypatch.setattr(history_service, "rep", repository)

        repository.register(EpisodePlugin("animefire", 3))
        store.set(
            "Goblin Slayer",
            [1234567890, 1, None, "animefire", 13, {"animefire": "https://example.com/animefire"}],
        )

        menu = ScriptedMenu(["Goblin Slayer (2/13)", "▶️  Episódio 2 (Local)"])

        def _no_search(*a, **k):
            raise AssertionError("saved-URL path must not hit search_anime")

        monkeypatch.setattr(repository, "search_anime", _no_search)

        result = history_service.load_history(
            menu=menu,
            progress=_progress,
            prompt=lambda _m: "",
        )

        assert result == ("Goblin Slayer", 1, None, None)
        # menu was actually consulted twice (history list + episode picker)
        assert len(menu.calls) == 2

    def test_cancel_history_menu_returns_none(self, temp_dir, repository, monkeypatch):
        from services.core import history_service

        store = JSONStore(temp_dir / "history.json")
        monkeypatch.setattr(history_service, "_history_store", store)
        monkeypatch.setattr(history_service, "rep", repository)
        store.set("Whatever", [1, 0, None, "animefire", 1, {"animefire": "u"}])

        result = history_service.load_history(
            menu=ScriptedMenu([None]),
            progress=_progress,
            prompt=lambda _m: "",
        )
        assert result is None


class TestPickEpisodeInjectedUI:
    def test_next_episode_choice(self):
        from services.core.history_service import _pick_episode

        menu = ScriptedMenu(["⏭️  Episódio 3 (próximo)"])
        idx = _pick_episode(
            "Anime",
            [1, 2, 3, 4, 5],
            last_ep_idx=1,
            progress_source="Local",
            menu=menu,
            menu_episodes=lambda eps: None,
            prompt=lambda _m: "",
        )
        assert idx == 2

    def test_choose_other_episode_delegates_to_menu_episodes(self):
        from services.core.history_service import _pick_episode

        menu = ScriptedMenu(["📋 Escolher outro episódio"])
        idx = _pick_episode(
            "Anime",
            [1, 2, 3],
            last_ep_idx=0,
            progress_source="Local",
            menu=menu,
            menu_episodes=lambda eps: 2,
            prompt=lambda _m: "",
        )
        assert idx == 2

    def test_unavailable_episode_prompts_and_returns_none(self):
        from services.core.history_service import _pick_episode

        prompts: list[str] = []
        menu = ScriptedMenu(["⏭️  Episódio 4 (aguardando)"])
        idx = _pick_episode(
            "Anime",
            [1, 2, 3],  # last_ep_idx points at final episode -> "aguardando"
            last_ep_idx=2,
            progress_source="Local",
            menu=menu,
            menu_episodes=lambda eps: None,
            prompt=lambda m: prompts.append(m),
        )
        assert idx is None
        assert prompts, "prompt (injected input) should have been used"


# ---------------------------------------------------------------------------
# random_anime_service - injected menu, no ui import
# ---------------------------------------------------------------------------


class TestRandomAnimeInjectedUI:
    def test_handle_post_playback_uses_injected_menu(self, monkeypatch):
        from services.anime import random_anime_service as ras
        from services.anime.playback_service import PlaybackContext

        ctx = PlaybackContext(
            anime_title="Test",
            episode_idx=0,
            source="animefire",
            anilist_id=None,
            anilist_title=None,
            total_episodes_anilist=None,
            num_episodes=3,
            episode_list=("Ep 1", "Ep 2", "Ep 3"),
        )

        saved: list[tuple] = []
        monkeypatch.setattr(ras, "save_history", lambda *a, **k: saved.append(a))

        service = ras.RandomAnimeService()
        # Confirm "watched", then choose "Sair" (no further playback).
        menu = ScriptedMenu(["✅ Sim, assisti até o final", "🔙 Sair"])

        service.handle_post_playback(
            ctx, episode=1, source="animefire", menu=menu, progress=_progress
        )

        assert saved, "confirmed watch should persist history"
        # First menu is the confirmation, second is post-playback options.
        assert len(menu.calls) == 2


# ---------------------------------------------------------------------------
# manga_service AniList lists - injected pause/show_* and menu
# ---------------------------------------------------------------------------


class TestHandleAnilistListInjectedUI:
    def test_not_authenticated_shows_warning_and_pauses(self, monkeypatch):
        from services.manga import manga_service as anilist_lists

        monkeypatch.setattr(anilist_lists.anilist_client, "is_authenticated", lambda: False)

        warnings: list[str] = []
        pauses: list[bool] = []
        selected: list[str] = []

        anilist_lists.handle_anilist_list(
            service=object(),
            list_type="reading",
            on_manga_selected=lambda s, t: selected.append(t),
            menu=ScriptedMenu([None]),
            progress=_progress,
            pause=lambda *a, **k: pauses.append(True),
            show_info=lambda *a, **k: None,
            show_warning=lambda msg, **k: warnings.append(msg),
        )

        assert warnings, "unauthenticated should warn"
        assert pauses, "unauthenticated should pause"
        assert not selected, "callback must not fire when unauthenticated"

    def test_empty_list_shows_info_and_pauses(self, monkeypatch):
        from services.manga import manga_service as anilist_lists

        monkeypatch.setattr(anilist_lists.anilist_client, "is_authenticated", lambda: True)
        monkeypatch.setattr(anilist_lists.anilist_client, "get_user_manga_list", lambda status: [])

        infos: list[str] = []
        pauses: list[bool] = []

        anilist_lists.handle_anilist_list(
            service=object(),
            list_type="planning",
            on_manga_selected=lambda s, t: None,
            menu=ScriptedMenu([None]),
            progress=_progress,
            pause=lambda *a, **k: pauses.append(True),
            show_info=lambda msg, **k: infos.append(msg),
            show_warning=lambda *a, **k: None,
        )

        assert infos == ["Nenhum mangá planejado"]
        assert pauses
