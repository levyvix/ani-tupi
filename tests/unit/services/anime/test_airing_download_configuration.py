from contextlib import contextmanager
from types import SimpleNamespace

from services.anime import airing_download_configuration as configuration_module
from services.anilist.client import AiringWatchQueryResult
from services.anime.airing_download_configuration import AiringDownloadConfigurationService, _title
from services.anime.airing_sources import AiringSourceStore


@contextmanager
def _progress(_message):
    yield


def test_configure_defaults_to_romaji_title():
    assert _title({"title": {"romaji": "Shingeki no Kyojin", "english": "Attack on Titan"}}) == (
        "Shingeki no Kyojin"
    )


class _Plugin:
    def __init__(self, source):
        self.source = source

    def search_episodes(self, _title, _url, _params):
        return [SimpleNamespace(season=2)]


class _Repository:
    sources = {"source-a": _Plugin("source-a"), "source-b": _Plugin("source-b")}

    def clear_search_results(self):
        pass

    def search_anime(self, _title, verbose=False):
        return SimpleNamespace(
            results=(
                SimpleNamespace(
                    title="Example Anime",
                    sources=(
                        ("https://source-a.example/anime", "source-a", {"dub": True}),
                        ("https://source-b.example/anime", "source-b", {}),
                    ),
                ),
            )
        )


class _SeparateResultsRepository(_Repository):
    def search_anime(self, _title, verbose=False):
        return SimpleNamespace(
            results=(
                SimpleNamespace(
                    title="Liar Game",
                    sources=(("https://source-a.example/anime", "source-a", {}),),
                ),
                SimpleNamespace(
                    title="Liar Game - TV",
                    sources=(("https://source-b.example/anime", "source-b", {}),),
                ),
            )
        )


class _ExplicitSeasonRepository(_Repository):
    def search_anime(self, _title, verbose=False):
        return SimpleNamespace(
            results=(
                SimpleNamespace(
                    title="Liar Game 3rd Season",
                    sources=(("https://source-a.example/anime", "source-a", {}),),
                ),
                SimpleNamespace(
                    title="Liar Game - 3rd Season",
                    sources=(("https://source-b.example/anime", "source-b", {}),),
                ),
            )
        )


class _Client:
    def get_watching_releasing_entries(self):
        return AiringWatchQueryResult(
            [
                {
                    "progress": 3,
                    "media": {
                        "id": 100,
                        "status": "RELEASING",
                        "title": {"romaji": "Example Anime"},
                    },
                }
            ]
        )


def test_configure_persists_selected_source_context(tmp_path):
    store = AiringSourceStore(tmp_path / "airing_download_sources.json")
    service = AiringDownloadConfigurationService(
        client=_Client(),
        repository=_Repository(),
        source_store=store,
        menu=lambda options, **_kwargs: next(option for option in options if "source-b" in option),
        progress=_progress,
    )

    assert service.configure() == 0
    saved = store.load(100)
    assert saved is not None
    assert saved.binding is not None
    assert saved.binding.source == "source-a"
    assert [source.source for source in saved.binding.alternatives] == ["source-b"]
    assert not hasattr(saved.binding, "season")
    assert saved.binding.params == {"dub": True}
    assert saved.binding.alternatives[0].params == {}


def test_configure_cancel_preserves_existing_preference(tmp_path):
    store = AiringSourceStore(tmp_path / "airing_download_sources.json")
    existing = store.load(100)
    assert existing is None

    choices = iter(["📺 Example Anime [source-a, source-b] / temporada 2", None])
    service = AiringDownloadConfigurationService(
        client=_Client(),
        repository=_Repository(),
        source_store=store,
        menu=lambda _options, **_kwargs: next(choices),
        progress=_progress,
    )
    assert service.configure() == 0

    saved = store.load(100)
    assert saved is not None
    assert saved.binding is not None
    assert saved.binding.source == "source-a"


def test_similar_titles_from_separate_results_share_one_choice():
    service = AiringDownloadConfigurationService(
        repository=_SeparateResultsRepository(),
        progress=_progress,
    )

    choices = service._search_choices("Liar Game")

    assert len(choices) == 1
    assert choices[0].label == "📺 Liar Game [source-a, source-b] / temporada 2"
    assert choices[0].binding.alternatives[0].source == "source-b"


def test_same_title_with_different_source_seasons_stays_one_choice(monkeypatch):
    monkeypatch.setattr(
        configuration_module,
        "_episode_seasons",
        lambda _repository, _title, source, _url, _params: [1 if source == "source-a" else 3],
    )
    service = AiringDownloadConfigurationService(
        repository=_ExplicitSeasonRepository(),
        progress=_progress,
    )

    choices = service._search_choices("Liar Game")

    assert len(choices) == 1
    assert choices[0].label == "📺 Liar Game 3rd Season [source-a, source-b] / temporada 3"
    assert not hasattr(choices[0].binding, "season")
    assert choices[0].binding.alternatives[0].season == 3


def test_default_repository_uses_hierarchical_search(monkeypatch):
    repository = SimpleNamespace(
        sources={"source-a": _Plugin("source-a")},
        anime_to_urls={
            "Liar Game": (("https://source-a.example/anime", "source-a", {}),),
        },
        clear_search_results=lambda: None,
        search_anime=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("configure should use hierarchical search")
        ),
    )
    called = []

    def hierarchical_search(query, reference_title):
        called.append((query, reference_title))
        return SimpleNamespace(titles_with_sources=["Liar Game [source-a]"])

    monkeypatch.setattr(configuration_module, "rep", repository)
    monkeypatch.setattr(
        "services.anime.search_service.contextual_incremental_search", hierarchical_search
    )

    choices = AiringDownloadConfigurationService(
        repository=repository,
        progress=_progress,
    )._search_choices("Liar Game")

    assert called == [("Liar Game", "Liar Game")]
    assert len(choices) == 1


def test_configure_can_remove_explicit_preference(tmp_path):
    store = AiringSourceStore(tmp_path / "airing_download_sources.json")
    service = AiringDownloadConfigurationService(
        client=_Client(),
        repository=_Repository(),
        source_store=store,
        menu=lambda options, **_kwargs: next(option for option in options if "source-a" in option),
        progress=_progress,
    )
    service.configure()

    service = AiringDownloadConfigurationService(
        client=_Client(),
        repository=_Repository(),
        source_store=store,
        menu=lambda options, **_kwargs: "🗑️ Remover preferência explícita",
        progress=_progress,
    )
    assert service.configure() == 0
    assert store.load(100) is None
