from types import SimpleNamespace

from models.config import settings
from services.anilist.client import AiringWatchQueryResult
from services.anime.airing_download_configuration import AiringDownloadConfigurationService
from services.anime.airing_download_scheduler import AiringDownloadScheduler
from services.anime.airing_sources import AiringSourceStore
from services.anime.download_catalog import record_confirmed_remote_playback
from services.anime.download_service import AnimeDownloadService
from services.anime.local_anime_service import LocalAnimeService


class _Plugin:
    name = "demo"

    def search_anime(self, _query):
        return [
            SimpleNamespace(
                title="Example Anime",
                url="https://demo.example/anime/example",
                source=self.name,
                params={"variant": "sub"},
            )
        ]

    def search_episodes(self, _title, _url, _params):
        return [
            SimpleNamespace(
                titles=["Episode 1", "Episode 2"],
                urls=[
                    "https://demo.example/anime/example/1",
                    "https://demo.example/anime/example/2",
                ],
                source=self.name,
                season=1,
            )
        ]


class _Repository:
    def __init__(self):
        self.sources = {"demo": _Plugin()}

    def clear_search_results(self):
        pass

    def search_anime(self, _query, verbose=False):
        result = self.sources["demo"].search_anime(_query)[0]
        return SimpleNamespace(
            results=(
                SimpleNamespace(
                    title=result.title,
                    sources=((result.url, result.source, result.params),),
                ),
            )
        )

    def get_active_sources(self):
        return ["demo"]

    def search_player_from_page(self, page_url, source):
        assert source == "demo"
        return [f"https://video.example/{page_url.rsplit('/', 1)[-1]}.mkv"]

    def get_episode_url_and_source(self, _title, episode):
        return (f"https://demo.example/anime/example/{episode}", "demo")

    def search_player(self, _title, _episode):
        return "https://video.example/2.mkv"


class _Client:
    def __init__(self):
        self.mutations = 0

    def is_authenticated(self):
        return True

    def get_watching_releasing_entries(self):
        return AiringWatchQueryResult(
            [
                {
                    "progress": 1,
                    "media": {
                        "id": 42,
                        "status": "RELEASING",
                        "title": {"romaji": "Example Anime"},
                    },
                }
            ]
        )


def test_configure_predownload_play_local_then_refresh_online(tmp_path, monkeypatch):
    download_dir = tmp_path / "downloads"
    state_dir = tmp_path / "state"
    monkeypatch.setattr(settings.anime_download, "download_directory", download_dir)
    monkeypatch.setattr("services.anime.local_anime_service.get_data_path", lambda: state_dir)

    repository = _Repository()
    client = _Client()
    source_store = AiringSourceStore(state_dir / "airing_download_sources.json")
    configure = AiringDownloadConfigurationService(
        client=client,
        repository=repository,
        source_store=source_store,
        menu=lambda options, **_kwargs: next(option for option in options if "[demo]" in option),
        progress=lambda _message: _null_context(),
    )

    assert configure.configure() == 0

    service = AnimeDownloadService()
    service.download_dir = download_dir
    service.db_path = state_dir / "anime_downloads.json"
    downloader_calls = []

    def fake_download(_url, file_path, **_kwargs):
        downloader_calls.append(file_path)
        file_path.write_bytes(b"x" * (2 * 1024 * 1024))
        return True

    monkeypatch.setattr(service, "_download_file", fake_download)
    scheduler_kwargs = {
        "client": client,
        "repository": repository,
        "download_service": service,
        "binding_resolver": source_store,
        "state_path": state_dir / "state.json",
        "lock_path": state_dir / "lock",
        "log_path": state_dir / "monitor.log",
    }

    first = AiringDownloadScheduler(**scheduler_kwargs).run_once()
    second = AiringDownloadScheduler(**scheduler_kwargs).run_once()
    assert first.successful == 1
    assert second.skipped == 1
    assert len(downloader_calls) == 1
    assert client.mutations == 0

    assert source_store.effective(42).origin == "binding"
    assert record_confirmed_remote_playback(
        42,
        "Example Anime",
        "demo",
        "https://demo.example/anime/example",
        season=1,
        variant="sub",
        episode_number=2,
        params={"variant": "sub"},
        path=source_store.file_path,
    )
    source_store.clear_configured(42)
    effective = source_store.effective(42)
    assert effective.origin == "missing"
    assert effective.binding is None

    local = LocalAnimeService()
    record = local.find_episode(42, 2, season=1)
    assert record is not None
    local_path = local.path_for_record(record)
    assert local_path.exists()

    import services.anime.playback_service as playback

    monkeypatch.setattr(playback, "rep", repository)
    local_result = playback.get_episode_url_and_source("Example Anime", 2, anilist_id=42, season=1)
    assert local_result.is_local is True
    assert local_result.file_path == local_path

    local_path.unlink()
    online_result = playback.get_episode_url_and_source("Example Anime", 2, anilist_id=42, season=1)
    assert online_result.is_local is False
    assert online_result.player_url == "https://video.example/2.mkv"


class _null_context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False
