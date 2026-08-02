"""Tests for the anime metadata provider (spec: anime-metadata-provider)."""

from unittest.mock import Mock, patch

import httpx
import pytest

from models.models import AnimeMetadataEntry
from services.anime.metadata_provider import (
    AnimeMetadataProvider,
    JikanMetadataProvider,
    get_metadata_provider,
)

PATCH_TARGET = "services.anime.metadata_provider.http_get_with_retry"


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    return response


class TestProtocolConformance:
    def test_concrete_implementation_satisfies_protocol(self):
        provider: AnimeMetadataProvider = JikanMetadataProvider()
        assert isinstance(provider, AnimeMetadataProvider)

    def test_access_function_returns_a_provider(self):
        assert isinstance(get_metadata_provider(), AnimeMetadataProvider)

    def test_returns_validated_domain_entries_not_raw_payloads(self):
        payload = {
            "data": [
                {
                    "mal_id": 20,
                    "title": "Naruto",
                    "title_english": "Naruto",
                    "title_japanese": "ナルト",
                    "titles": [{"type": "Default", "title": "Naruto"}],
                    "synonyms": [],
                }
            ]
        }
        with patch(PATCH_TARGET, return_value=_response(payload)):
            results = JikanMetadataProvider().search_anime("naruto")

        assert [type(entry) for entry in results] == [AnimeMetadataEntry]
        assert results[0].title == "Naruto"

    def test_skips_entries_that_fail_validation(self):
        payload = {"data": [{"mal_id": "not-an-int"}, {"mal_id": 1, "title": "Bleach"}]}
        with patch(PATCH_TARGET, return_value=_response(payload)):
            results = JikanMetadataProvider().search_anime("bleach")

        assert [entry.title for entry in results] == ["Bleach"]


class TestGracefulDegradation:
    """Spec scenario: 'Provedor fora do ar' — no exception escapes."""

    @pytest.mark.parametrize(
        "failure",
        [
            httpx.HTTPStatusError(
                "server error",
                request=httpx.Request("GET", "https://api.jikan.moe/v4/anime"),
                response=httpx.Response(503),
            ),
            httpx.TimeoutException("timed out"),
            ConnectionError("no network"),
        ],
        ids=["http_error", "timeout", "connection_error"],
    )
    def test_provider_failure_returns_empty_list(self, failure):
        with patch(PATCH_TARGET, side_effect=failure):
            assert JikanMetadataProvider().search_anime("naruto") == []

    def test_unexpected_payload_shape_returns_empty_list(self):
        with patch(PATCH_TARGET, return_value=_response({"error": "rate limited"})):
            assert JikanMetadataProvider().search_anime("naruto") == []
