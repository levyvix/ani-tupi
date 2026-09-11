from tests.fixtures.anilist import anilist_errors, graphql_response


def _entry(media_id: int, status: str = "RELEASING") -> dict:
    return {
        "status": "CURRENT",
        "progress": 3,
        "media": {
            "id": media_id,
            "title": {"romaji": "Test", "english": "Test", "native": "T"},
            "status": status,
            "episodes": 12,
            "nextAiringEpisode": None,
        },
    }


def test_empty_watching_response_is_successful_empty(anilist_client, anilist_http):
    anilist_http.enqueue(graphql_response({"MediaListCollection": {"lists": [{"entries": []}]}}))

    result = anilist_client.get_watching_releasing_entries()

    assert result.ok is True
    assert result.entries == []


def test_filters_releasing_and_deduplicates_media_ids(anilist_client, anilist_http):
    anilist_http.enqueue(
        graphql_response(
            {
                "MediaListCollection": {
                    "lists": [{"entries": [_entry(10), _entry(10), _entry(11, "FINISHED")]}]
                }
            }
        )
    )

    result = anilist_client.get_watching_releasing_entries()

    assert [entry["media"]["id"] for entry in result.entries] == [10]
    request = anilist_http.calls[0]
    assert "status: CURRENT" in request["json"]["query"]


def test_api_failure_is_not_returned_as_stale_or_empty_success(anilist_client, anilist_http):
    anilist_http.enqueue(anilist_errors("server unavailable"))

    result = anilist_client.get_watching_releasing_entries()

    assert result.ok is False
    assert result.error_kind == "api"
    assert result.entries == []


def test_forbidden_response_is_classified_as_authentication_failure(anilist_client, anilist_http):
    anilist_http.enqueue(anilist_errors("forbidden"))

    result = anilist_client.get_watching_releasing_entries()

    assert result.ok is False
    assert result.error_kind == "authentication"


def test_missing_authentication_is_distinct_without_api_call(anilist_client, anilist_http):
    anilist_client.token = None

    result = anilist_client.get_watching_releasing_entries()

    assert result.ok is False
    assert result.error_kind == "authentication"
    assert anilist_http.call_count == 0
