"""Integration-style tests for history service behavior."""

from contextlib import nullcontext

from utils.persistence import JSONStore


class EpisodePlugin:
    def __init__(self, name: str, episode_count: int, repository):
        self.name = name
        self.episode_count = episode_count
        self.repository = repository

    def search_episodes(self, anime: str, url: str, params):
        titles = [f"Episode {i + 1}" for i in range(self.episode_count)]
        urls = [f"{url}/ep{i + 1}" for i in range(self.episode_count)]
        self.repository.add_episode_list(anime, titles, urls, self.name)


def _make_menu_responder(choices: list[str], calls: list[tuple[list[str], str]]):
    iterator = iter(choices)

    def _menu(options, msg="", **kwargs):
        calls.append((list(options), msg))
        return next(iterator)

    return _menu


class TestHistoryService:
    def test_load_history_returns_none_when_user_goes_back(self, temp_dir, repository, monkeypatch):
        import ui.components
        from services.core import history_service

        history_store = JSONStore(temp_dir / "history.json")
        monkeypatch.setattr(history_service, "_history_store", history_store)
        monkeypatch.setattr(history_service, "rep", repository)
        monkeypatch.setattr(ui.components, "menu_navigate", _make_menu_responder([None], []))

        history_store.set(
            "Goblin Slayer",
            [1234567890, 1, None, "animefire", 13, {"animefire": "https://example.com/animefire"}],
        )

        assert history_service.load_history() is None

    def test_save_history_persists_all_source_urls(self, temp_dir, repository, monkeypatch):
        from services.core import history_service

        history_store = JSONStore(temp_dir / "history.json")
        monkeypatch.setattr(history_service, "_history_store", history_store)
        monkeypatch.setattr(history_service, "rep", repository)

        repository.add_anime("Goblin Slayer", "https://example.com/animefire", "animefire", {})
        repository.add_anime(
            "Goblin Slayer", "https://example.com/animesdigital", "animesdigital", {}
        )

        history_service.save_history("Goblin Slayer", 1, source="animefire")

        stored = history_store.load({})
        assert stored["Goblin Slayer"][5] == {
            "animefire": "https://example.com/animefire",
            "animesdigital": "https://example.com/animesdigital",
        }

    def test_load_history_uses_saved_urls_and_skips_anime_search(
        self, temp_dir, repository, monkeypatch
    ):
        from services.core import history_service

        history_store = JSONStore(temp_dir / "history.json")
        monkeypatch.setattr(history_service, "_history_store", history_store)
        monkeypatch.setattr(history_service, "rep", repository)
        import ui.components

        monkeypatch.setattr(ui.components, "loading", lambda *args, **kwargs: nullcontext())

        repository.register(EpisodePlugin("animefire", 3, repository))

        history_store.set(
            "Goblin Slayer",
            [
                1234567890,
                1,
                None,
                "animefire",
                13,
                {"animefire": "https://example.com/animefire"},
            ],
        )

        menu_calls: list[tuple[list[str], str]] = []
        monkeypatch.setattr(
            ui.components,
            "menu_navigate",
            _make_menu_responder(
                ["Goblin Slayer (2/13)", "▶️  Episódio 2 (Local)"],
                menu_calls,
            ),
        )

        def fail_search_anime(*args, **kwargs):
            raise AssertionError("load_history should not call search_anime when URLs are saved")

        monkeypatch.setattr(repository, "search_anime", fail_search_anime)

        result = history_service.load_history()

        assert result == ("Goblin Slayer", 1, None, None)
        assert any("Episódio 3 (próximo)" in option for option in menu_calls[1][0])
        assert all("aguardando" not in option for option in menu_calls[1][0])
