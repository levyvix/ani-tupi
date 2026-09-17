from types import SimpleNamespace

from models.download import AiringSourceBinding, AiringSourceCandidate
from models.anime import ScrapedEpisodes
from services.anilist.client import AiringWatchQueryResult
from services.anime.airing_downloads import (
    AiringDownloadsService,
    AiringMonitorQueryError,
    select_published_episodes,
)


def _binding() -> AiringSourceBinding:
    return AiringSourceBinding(
        title="Example Anime",
        source="source-a",
        anime_url="https://example.test/anime",
        params={"slug": "example"},
        season=1,
    )


def _entry(*, progress=4, status="RELEASING", next_airing=None, media_id=7):
    return {
        "status": "CURRENT",
        "progress": progress,
        "media": {
            "id": media_id,
            "status": status,
            "nextAiringEpisode": next_airing,
        },
    }


def _batch(*titles):
    return ScrapedEpisodes(
        titles=list(titles),
        urls=[f"https://example.test/{index}" for index, _ in enumerate(titles, 1)],
        source="source-a",
        season=1,
    )


def test_selects_backlog_in_number_order_without_using_position():
    result = select_published_episodes(
        _entry(),
        _binding(),
        [_batch("Episode 7", "Episode 5", "Episode 6")],
    )

    assert [episode.episode_number for episode in result] == [5, 6, 7]


def test_preserves_real_gaps_and_ignores_specials():
    result = select_published_episodes(
        _entry(),
        _binding(),
        [_batch("Episode 5", "Episode 7", "Special 6", "Episode without number")],
    )

    assert [episode.episode_number for episode in result] == [5, 7]


def test_future_next_airing_episode_is_not_treated_as_published():
    result = select_published_episodes(
        _entry(next_airing={"episode": 5, "airingAt": 2_000}),
        _binding(),
        [_batch("Episode 5", "Episode 6")],
        now=1_000,
    )

    assert result == []


def test_finished_media_has_no_candidates():
    assert (
        select_published_episodes(_entry(status="FINISHED"), _binding(), [_batch("Episode 5")])
        == []
    )


def test_conflicting_urls_for_same_episode_are_ignored():
    first = _batch("Episode 5")
    second = ScrapedEpisodes(
        titles=["Episode 5"],
        urls=["https://other.test/5"],
        source="source-a",
        season=1,
    )

    assert select_published_episodes(_entry(), _binding(), [first, second]) == []


def test_query_keeps_api_failure_distinct_from_empty_list():
    client = SimpleNamespace(
        get_watching_releasing_entries=lambda: AiringWatchQueryResult([], "api", "api down")
    )
    service = AiringDownloadsService(client=client)

    result = service.query_watching()
    assert result.ok is False
    assert result.error_kind == "api"
    try:
        service.get_watching_releasing()
    except AiringMonitorQueryError as error:
        assert error.kind == "api"
    else:
        raise AssertionError("API failure must not be presented as an empty list")


def test_source_fetch_uses_only_saved_source_and_context():
    calls = []

    class Plugin:
        def search_episodes(self, title, url, params):
            calls.append((title, url, params))
            return [_batch("Episode 5")]

    repository = SimpleNamespace(sources={"source-a": Plugin(), "source-b": Plugin()})
    store = SimpleNamespace(effective=lambda _id: SimpleNamespace(binding=_binding()))
    service = AiringDownloadsService(repository=repository, source_store=store)

    selection = service.select_for_entry(_entry())

    assert [episode.episode_number for episode in selection.episodes] == [5]
    assert calls == [("Example Anime", "https://example.test/anime", {"slug": "example"})]


def test_aggregated_binding_merges_episodes_from_ordered_source_alternatives():
    calls = []

    class Plugin:
        def __init__(self, source, title):
            self.source = source
            self.title = title

        def search_episodes(self, title, url, params):
            calls.append((self.source, title, url, params))
            titles = ["Episode 5"] if self.source == "source-a" else ["Episode 5", "Episode 6"]
            return [
                ScrapedEpisodes(
                    titles=titles,
                    urls=[f"https://{self.source}.test/{number}" for number in (5, 6)][
                        : len(titles)
                    ],
                    source=self.source,
                    season=1,
                )
            ]

    binding = _binding().model_copy(
        update={
            "alternatives": [
                AiringSourceCandidate(
                    title="Example Anime (source B)",
                    source="source-b",
                    anime_url="https://source-b.example/anime",
                    params={"slug": "alternative"},
                    season=1,
                )
            ]
        }
    )
    repository = SimpleNamespace(
        sources={
            "source-a": Plugin("source-a", "Example Anime"),
            "source-b": Plugin("source-b", "Example Anime (source B)"),
        }
    )
    store = SimpleNamespace(effective=lambda _id: SimpleNamespace(binding=binding))
    service = AiringDownloadsService(repository=repository, source_store=store)

    selection = service.select_for_entry(_entry(progress=4))

    assert [episode.episode_number for episode in selection.episodes] == [5, 6]
    assert [candidate.source for candidate in selection.candidates_by_episode[5]] == [
        "source-a",
        "source-b",
    ]
    assert calls == [
        ("source-a", "Example Anime", "https://example.test/anime", {"slug": "example"}),
        (
            "source-b",
            "Example Anime (source B)",
            "https://source-b.example/anime",
            {"slug": "alternative"},
        ),
    ]


def test_refreshes_saved_title_search_before_fetching_source_episodes():
    calls = []

    class Plugin:
        def __init__(self, source):
            self.source = source

        def search_episodes(self, title, url, params):
            calls.append(self.source)
            return [
                ScrapedEpisodes(
                    titles=["Episode 5"],
                    urls=[f"https://{self.source}.test/episode-5"],
                    source=self.source,
                    season=1,
                )
            ]

    class Repository:
        def __init__(self):
            self.sources = {"source-a": Plugin("source-a"), "source-b": Plugin("source-b")}
            self.anime_to_urls = {}

        def clear_search_results(self):
            self.anime_to_urls = {}

        def search_anime(self, title, verbose=False):
            self.anime_to_urls[title] = [
                ("https://source-a.test/anime", "source-a", {"source": "a"}),
                ("https://source-b.test/anime", "source-b", {"source": "b"}),
            ]

    binding = _binding()
    repository = Repository()
    saved = []
    store = SimpleNamespace(
        effective=lambda _id: SimpleNamespace(binding=binding),
        save_binding=lambda anilist_id, refreshed: saved.append((anilist_id, refreshed)),
    )
    service = AiringDownloadsService(repository=repository, source_store=store)

    selection = service.select_for_entry(_entry(progress=4))

    assert [episode.source for episode in selection.episodes] == ["source-a"]
    assert calls == ["source-a", "source-b"]
    assert saved[0][0] == 7
    assert [item.source for item in saved[0][1].alternatives] == ["source-b"]
