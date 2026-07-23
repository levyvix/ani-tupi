"""Tests for the Otakulogia GraphQL scraper.

Only the external boundary (the GraphQL POST) is mocked; the plugin's request
building, JSON-scalar unwrapping, season selection and quality ordering all run
for real.
"""

import pytest
from unittest.mock import MagicMock, patch

from scrapers.plugins.otakulogia import Otakulogia


def _wrapped(records: list[dict]) -> dict:
    """Mimic the API's random-keyed wrapper around the record array."""
    return {"RANDOM_key_9f": records}


def _response(data: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"data": data}
    return response


def _router(routes: dict[str, dict]):
    """Build an ``http_request_with_retry`` side effect keyed by operation name."""

    def side_effect(method, url, **kwargs):
        query = kwargs["json"]["query"]
        for op, data in routes.items():
            if op in query:
                return _response(data)
        raise AssertionError(f"unexpected query: {query}")

    return side_effect


SEARCH_RECORDS = [
    {"cid": "8160", "category_name": "Naruto SD"},
    {"cid": "1216", "category_name": "Naruto: Blood Prison"},
]

FLAT_EPISODES = [
    {"id": "3", "video_ep": "EP 2 | LEG"},
    {"id": "1", "video_ep": "EP 1 | LEG"},
]

TEMPORADAS = {
    "has_temporada": True,
    "temporadas": [
        {"tid": 4710, "name": "Temporada 01 | Legendado"},
        {"tid": 7035, "name": "Temporada 03 | Legendado"},
    ],
}


def _event() -> MagicMock:
    event = MagicMock()
    event.is_set.return_value = False
    return event


class TestOtakulogiaScraper:
    def setup_method(self):
        self.scraper = Otakulogia()

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_anime_returns_results(self, mock_req):
        mock_req.side_effect = _router(
            {
                "SearchVideo": {"SearchVideo": _wrapped(SEARCH_RECORDS)},
                "CheckTemporada": {"CheckTemporada": {"has_temporada": False}},
            }
        )

        results = self.scraper.search_anime("naruto")

        assert len(results) == 2
        titles = {r.title for r in results}
        assert titles == {"Naruto SD", "Naruto: Blood Prison"}
        sd = next(r for r in results if r.title == "Naruto SD")
        assert sd.url == "https://otakulogia.com/anime/8160"
        assert sd.params == {"cid": "8160"}
        assert sd.source == "otakulogia"

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_anime_expands_seasons(self, mock_req):
        seasons = {
            "has_temporada": True,
            "temporadas": [
                {"tid": 100, "name": "Temporada 01 | Dublado"},
                {"tid": 200, "name": "Temporada 03 | Legendado"},
            ],
        }

        def side_effect(method, url, **kwargs):
            query = kwargs["json"]["query"]
            if "SearchVideo" in query:
                return _response(
                    {"SearchVideo": _wrapped([{"cid": "33205", "category_name": "Jujutsu Kaisen"}])}
                )
            if "CheckTemporada" in query:
                return _response({"CheckTemporada": seasons})
            raise AssertionError(query)

        mock_req.side_effect = side_effect

        results = self.scraper.search_anime("jujutsu")

        by_title = {r.title: r for r in results}
        assert set(by_title) == {
            "Jujutsu Kaisen Temporada 1 Dublado",
            "Jujutsu Kaisen Temporada 3 Legendado",
        }
        assert by_title["Jujutsu Kaisen Temporada 3 Legendado"].params == {
            "cid": "33205",
            "tid": 200,
            "season": 3,
        }
        assert by_title["Jujutsu Kaisen Temporada 1 Dublado"].params == {
            "cid": "33205",
            "tid": 100,
            "season": 1,
        }

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_anime_movie_entry(self, mock_req):
        seasons = {
            "has_temporada": True,
            "temporadas": [
                {"tid": 300, "name": "Jujutsu Kaisen 0 Movie | Dublado"},
            ],
        }

        def side_effect(method, url, **kwargs):
            query = kwargs["json"]["query"]
            if "SearchVideo" in query:
                return _response(
                    {"SearchVideo": _wrapped([{"cid": "33205", "category_name": "Jujutsu Kaisen"}])}
                )
            if "CheckTemporada" in query:
                return _response({"CheckTemporada": seasons})
            raise AssertionError(query)

        mock_req.side_effect = side_effect

        results = self.scraper.search_anime("jujutsu")

        assert len(results) == 1
        assert results[0].title == "Jujutsu Kaisen 0 Movie | Dublado"
        assert results[0].params == {"cid": "33205", "tid": 300}

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_anime_isolates_failing_temporada(self, mock_req):
        seasons = {
            "has_temporada": True,
            "temporadas": [
                {"tid": 100, "name": "Temporada 01 | Dublado"},
            ],
        }

        def side_effect(method, url, **kwargs):
            query = kwargs["json"]["query"]
            if "SearchVideo" in query:
                return _response(
                    {
                        "SearchVideo": _wrapped(
                            [
                                {"cid": "1", "category_name": "Good Anime"},
                                {"cid": "2", "category_name": "Bad Anime"},
                            ]
                        )
                    }
                )
            if "CheckTemporada" in query:
                cid = kwargs["json"]["variables"]["catId"]
                if cid == "2":
                    raise RuntimeError("unexpected API shape for cid 2")
                return _response({"CheckTemporada": seasons})
            raise AssertionError(query)

        mock_req.side_effect = side_effect

        results = self.scraper.search_anime("anime")

        by_title = {r.title: r for r in results}
        # Good catalog expands into its season entry; the failing catalog
        # degrades to a flat single entry instead of aborting the whole search.
        assert by_title["Good Anime Temporada 1 Dublado"].params == {
            "cid": "1",
            "tid": 100,
            "season": 1,
        }
        assert by_title["Bad Anime"].params == {"cid": "2"}

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_episodes_uses_tid_param(self, mock_req):
        captured_tids = []

        def side_effect(method, url, **kwargs):
            query = kwargs["json"]["query"]
            if "CheckTemporada" in query:
                raise AssertionError("CheckTemporada should not be called when tid is provided")
            if "VideoByCatId" in query:
                variables = kwargs["json"]["variables"]
                captured_tids.append(variables["input"].get("tid"))
                if variables["input"]["page"] == 1:
                    return _response({"VideoByCatId": _wrapped(FLAT_EPISODES)})
                return _response({"VideoByCatId": _wrapped([])})
            raise AssertionError(query)

        mock_req.side_effect = side_effect

        result = self.scraper.search_episodes(
            "Jujutsu",
            "https://otakulogia.com/anime/33205",
            {"cid": "33205", "tid": 200, "season": 3},
        )

        assert result[0].season == 3
        assert captured_tids[0] == 200

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_anime_empty_returns_empty_list(self, mock_req):
        mock_req.side_effect = _router({"SearchVideo": {"SearchVideo": _wrapped([])}})

        assert self.scraper.search_anime("nothing") == []

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_episodes_flat_catalog(self, mock_req):
        # First VideoByCatId page returns episodes, the second is empty (end).
        pages = [_wrapped(FLAT_EPISODES), _wrapped([])]
        calls = {"n": 0}

        def side_effect(method, url, **kwargs):
            query = kwargs["json"]["query"]
            if "CheckTemporada" in query:
                return _response({"CheckTemporada": {"has_temporada": False}})
            if "VideoByCatId" in query:
                data = pages[min(calls["n"], len(pages) - 1)]
                calls["n"] += 1
                return _response({"VideoByCatId": data})
            raise AssertionError(query)

        mock_req.side_effect = side_effect

        result = self.scraper.search_episodes(
            "Naruto SD", "https://otakulogia.com/anime/8160", {"cid": "8160"}
        )

        assert len(result) == 1
        batch = result[0]
        assert batch.season == 1
        assert batch.source == "otakulogia"
        # Sorted ascending by episode number parsed from ``video_ep``.
        assert batch.titles == ["Episódio 1", "Episódio 2"]
        assert batch.urls == [
            "https://otakulogia.com/watch/1",
            "https://otakulogia.com/watch/3",
        ]

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_episodes_selects_requested_season(self, mock_req):
        captured_tids = []

        def side_effect(method, url, **kwargs):
            variables = kwargs["json"]["variables"]
            query = kwargs["json"]["query"]
            if "CheckTemporada" in query:
                return _response({"CheckTemporada": TEMPORADAS})
            if "VideoByCatId" in query:
                captured_tids.append(variables["input"].get("tid"))
                if variables["input"]["page"] == 1:
                    return _response({"VideoByCatId": _wrapped(FLAT_EPISODES)})
                return _response({"VideoByCatId": _wrapped([])})
            raise AssertionError(query)

        mock_req.side_effect = side_effect

        result = self.scraper.search_episodes(
            "Jujutsu", "https://otakulogia.com/anime/33205", {"cid": "33205", "season": 3}
        )

        assert result[0].season == 3
        # Season 3 maps to tid 7035, sent as an int (the API rejects strings).
        assert captured_tids[0] == 7035
        assert isinstance(captured_tids[0], int)

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_episodes_missing_cid_returns_empty(self, mock_req):
        result = self.scraper.search_episodes("x", "https://otakulogia.com/", None)
        assert result == []
        mock_req.assert_not_called()

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_player_src_prefers_fhd(self, mock_req):
        record = {
            "id": "1",
            "video_url_fhd": "https://cdn.example/fhd.mp4",
            "video_url": "https://cdn.example/hd.mp4",
            "video_url_sd": "",
        }
        mock_req.side_effect = _router({"SingleVideo": {"SingleVideo": _wrapped([record])}})
        container: list = []

        self.scraper.search_player_src("https://otakulogia.com/watch/1", container, _event())

        # FHD first, then the standard URL; empty SD skipped.
        assert container == ["https://cdn.example/fhd.mp4", "https://cdn.example/hd.mp4"]

    @patch("scrapers.plugins.otakulogia.http_request_with_retry")
    def test_search_player_src_no_source_raises(self, mock_req):
        mock_req.side_effect = _router({"SingleVideo": {"SingleVideo": _wrapped([])}})

        with pytest.raises(Exception):
            self.scraper.search_player_src("https://otakulogia.com/watch/1", [], _event())

    def test_search_player_src_invalid_url_raises(self):
        with pytest.raises(Exception):
            self.scraper.search_player_src("https://otakulogia.com/bad", [], _event())
