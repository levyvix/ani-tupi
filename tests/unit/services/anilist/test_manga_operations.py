"""Tests for MangaOperationsMixin in services/anilist/manga_operations.py."""

import pytest

from tests.fixtures.anilist import (
    anilist_data,
    graphql_response,
    save_media_list_entry,
    viewer,
)


# ---------------------------------------------------------------------------
# Helpers / minimal manga fixtures
# ---------------------------------------------------------------------------


def _manga_item(
    manga_id: int = 10,
    *,
    romaji: str = "Test Manga",
    chapters: int | None = 50,
    volumes: int | None = 5,
) -> dict:
    return {
        "id": manga_id,
        "title": {"romaji": romaji, "english": romaji, "native": romaji},
        "chapters": chapters,
        "volumes": volumes,
        "averageScore": 75,
        "startDate": {"year": 2020, "month": 1, "day": 1},
        "endDate": None,
    }


def _media_list_entry(
    entry_id: int = 1,
    *,
    manga_id: int = 10,
    romaji: str = "Test Manga",
    chapters: int | None = 50,
    progress: int = 3,
) -> dict:
    return {
        "id": entry_id,
        "progress": progress,
        "createdAt": 1700000000,
        "media": {
            "id": manga_id,
            "title": {"romaji": romaji, "english": romaji, "native": romaji},
            "chapters": chapters,
            "volumes": None,
            "averageScore": 75,
            "startDate": {"year": 2020, "month": 1, "day": 1},
        },
    }


def _media_list_response(entry_id: int = 1, manga_id: int = 10) -> dict:
    """Shape returned by get_manga_list_entry query (MediaList)."""
    return {
        "MediaList": {
            "id": entry_id,
            "status": "CURRENT",
            "progress": 5,
            "score": 80,
            "startedAt": {"year": 2021, "month": 3, "day": 1},
            "completedAt": None,
        }
    }


# ---------------------------------------------------------------------------
# get_trending_manga
# ---------------------------------------------------------------------------


class TestGetTrendingManga:
    def test_returns_manga_list(self, anilist_client, anilist_http):
        items = [_manga_item(i) for i in range(1, 4)]
        anilist_http.enqueue(anilist_data({"Page": {"media": items}}))

        result = anilist_client.get_trending_manga()

        assert len(result) == 3
        assert result[0].id == 1
        assert result[0].title.romaji == "Test Manga"

    def test_empty_media_returns_empty_list(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"Page": {"media": []}}))

        result = anilist_client.get_trending_manga()

        assert result == []

    def test_null_result_returns_empty_list(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))

        result = anilist_client.get_trending_manga()

        assert result == []

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("network error"))

        with pytest.raises(Exception):
            anilist_client.get_trending_manga()

    def test_passes_page_and_per_page(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"Page": {"media": [_manga_item()]}}))

        anilist_client.get_trending_manga(page=2, per_page=5)

        call = anilist_http.calls[0]
        variables = call["json"]["variables"]
        assert variables["page"] == 2
        assert variables["perPage"] == 5


# ---------------------------------------------------------------------------
# get_user_manga_list
# ---------------------------------------------------------------------------


class TestGetUserMangaList:
    def test_returns_entries_when_authenticated(self, anilist_client, anilist_http):
        entries = [_media_list_entry(i) for i in range(1, 3)]
        anilist_http.enqueue(
            anilist_data({"MediaListCollection": {"lists": [{"entries": entries}]}})
        )

        result = anilist_client.get_user_manga_list("CURRENT")

        assert len(result) == 2

    def test_not_authenticated_returns_empty(self, anilist_client, anilist_http):
        anilist_client.token = None  # unauthenticated

        result = anilist_client.get_user_manga_list("CURRENT")

        assert result == []
        assert anilist_http.call_count == 0

    def test_lazy_user_id_fetch(self, anilist_client, anilist_http):
        """When user_id is None, should call get_viewer_info first."""
        anilist_client.user_id = None
        entries = [_media_list_entry()]
        anilist_http.enqueue(anilist_data({"Viewer": viewer(user_id=42)}))
        anilist_http.enqueue(
            anilist_data({"MediaListCollection": {"lists": [{"entries": entries}]}})
        )

        result = anilist_client.get_user_manga_list("PLANNING")

        assert len(result) == 1
        assert anilist_client.user_id == 42

    def test_lazy_user_id_fetch_viewer_fails_returns_empty(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response(None))

        result = anilist_client.get_user_manga_list("CURRENT")

        assert result == []

    def test_sorted_by_created_at_desc(self, anilist_client, anilist_http):
        entries = [
            {**_media_list_entry(1), "createdAt": 100},
            {**_media_list_entry(2), "createdAt": 300},
            {**_media_list_entry(3), "createdAt": 200},
        ]
        anilist_http.enqueue(
            anilist_data({"MediaListCollection": {"lists": [{"entries": entries}]}})
        )

        result = anilist_client.get_user_manga_list("CURRENT")

        assert result[0].id == 2  # highest createdAt first

    def test_flattens_multiple_list_groups(self, anilist_client, anilist_http):
        group1 = [_media_list_entry(1)]
        group2 = [_media_list_entry(2), _media_list_entry(3)]
        anilist_http.enqueue(
            anilist_data(
                {"MediaListCollection": {"lists": [{"entries": group1}, {"entries": group2}]}}
            )
        )

        result = anilist_client.get_user_manga_list("COMPLETED")

        assert len(result) == 3

    def test_empty_collection_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"MediaListCollection": {"lists": []}}))

        result = anilist_client.get_user_manga_list("DROPPED")

        assert result == []

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("timeout"))

        with pytest.raises(Exception):
            anilist_client.get_user_manga_list("CURRENT")

    def test_none_result_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))

        result = anilist_client.get_user_manga_list("CURRENT")

        assert result == []


# ---------------------------------------------------------------------------
# get_manga_by_id
# ---------------------------------------------------------------------------


class TestGetMangaById:
    def test_returns_manga(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"Media": _manga_item(10)}))

        result = anilist_client.get_manga_by_id(10)

        assert result is not None
        assert result.id == 10

    def test_missing_media_returns_none(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"Media": None}))

        result = anilist_client.get_manga_by_id(999)

        assert result is None

    def test_null_result_returns_none(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))

        result = anilist_client.get_manga_by_id(1)

        assert result is None

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("error"))

        with pytest.raises(Exception):
            anilist_client.get_manga_by_id(1)

    def test_passes_manga_id(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"Media": _manga_item(42)}))

        anilist_client.get_manga_by_id(42)

        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["id"] == 42


# ---------------------------------------------------------------------------
# get_manga_list_entry
# ---------------------------------------------------------------------------


class TestGetMangaListEntry:
    def test_returns_entry_when_authenticated(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data(_media_list_response()))

        result = anilist_client.get_manga_list_entry(10)

        assert result is not None
        assert result.id == 1
        assert result.status == "CURRENT"

    def test_not_authenticated_returns_none(self, anilist_client, anilist_http):
        anilist_client.token = None

        result = anilist_client.get_manga_list_entry(10)

        assert result is None
        assert anilist_http.call_count == 0

    def test_lazy_user_id_fetch(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(anilist_data({"Viewer": viewer(user_id=42)}))
        anilist_http.enqueue(anilist_data(_media_list_response()))

        result = anilist_client.get_manga_list_entry(10)

        assert result is not None
        assert anilist_client.user_id == 42

    def test_lazy_user_id_viewer_fails_returns_none(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response(None))

        result = anilist_client.get_manga_list_entry(10)

        assert result is None

    def test_media_list_not_in_result_returns_none(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({}))

        result = anilist_client.get_manga_list_entry(10)

        assert result is None

    def test_null_media_list_returns_none(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"MediaList": None}))

        result = anilist_client.get_manga_list_entry(10)

        assert result is None

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("boom"))

        with pytest.raises(Exception):
            anilist_client.get_manga_list_entry(10)


# ---------------------------------------------------------------------------
# update_manga_progress
# ---------------------------------------------------------------------------


class TestUpdateMangaProgress:
    def test_returns_true_on_success(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data(save_media_list_entry(99, progress=5)))

        result = anilist_client.update_manga_progress(10, 5)

        assert result is True

    def test_not_authenticated_returns_false(self, anilist_client, anilist_http):
        anilist_client.token = None

        result = anilist_client.update_manga_progress(10, 5)

        assert result is False
        assert anilist_http.call_count == 0

    def test_missing_mutation_result_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({}))

        result = anilist_client.update_manga_progress(10, 5)

        assert result is False

    def test_null_result_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))

        result = anilist_client.update_manga_progress(10, 5)

        assert result is False

    def test_exception_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("network error"))

        result = anilist_client.update_manga_progress(10, 5)

        assert result is False

    def test_passes_correct_variables(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data(save_media_list_entry(99, progress=7)))

        anilist_client.update_manga_progress(manga_id=15, chapter=7)

        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["mediaId"] == 15
        assert variables["progress"] == 7


# ---------------------------------------------------------------------------
# add_manga_to_list
# ---------------------------------------------------------------------------


class TestAddMangaToList:
    def test_returns_true_on_success(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data(save_media_list_entry(1, status="CURRENT")))

        result = anilist_client.add_manga_to_list(10)

        assert result is True

    def test_default_status_is_current(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data(save_media_list_entry(1, status="CURRENT")))

        anilist_client.add_manga_to_list(10)

        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["status"] == "CURRENT"

    def test_custom_status(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data(save_media_list_entry(1, status="PLANNING")))

        result = anilist_client.add_manga_to_list(10, status="PLANNING")

        assert result is True
        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["status"] == "PLANNING"

    def test_missing_mutation_key_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({}))

        result = anilist_client.add_manga_to_list(10)

        assert result is False

    def test_null_result_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))

        result = anilist_client.add_manga_to_list(10)

        assert result is False

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("error"))

        with pytest.raises(Exception):
            anilist_client.add_manga_to_list(10)


# ---------------------------------------------------------------------------
# change_manga_status
# ---------------------------------------------------------------------------


class TestChangeMangaStatus:
    def test_returns_true_on_success(self, anilist_client, anilist_http):
        from models.anime import Status

        anilist_http.enqueue(anilist_data(save_media_list_entry(1, status="COMPLETED")))

        result = anilist_client.change_manga_status(10, Status.COMPLETED)

        assert result is True

    def test_not_authenticated_returns_false(self, anilist_client, anilist_http):
        from models.anime import Status

        anilist_client.token = None

        result = anilist_client.change_manga_status(10, Status.CURRENT)

        assert result is False
        assert anilist_http.call_count == 0

    def test_missing_mutation_key_returns_false(self, anilist_client, anilist_http):
        from models.anime import Status

        anilist_http.enqueue(anilist_data({}))

        result = anilist_client.change_manga_status(10, Status.PAUSED)

        assert result is False

    def test_exception_propagates(self, anilist_client, anilist_http):
        from models.anime import Status

        anilist_http.enqueue(Exception("network"))

        with pytest.raises(Exception):
            anilist_client.change_manga_status(10, Status.DROPPED)

    def test_passes_status_value(self, anilist_client, anilist_http):
        from models.anime import Status

        anilist_http.enqueue(anilist_data(save_media_list_entry(1)))

        anilist_client.change_manga_status(10, Status.PLANNING)

        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["status"] == Status.PLANNING.value


# ---------------------------------------------------------------------------
# search_manga
# ---------------------------------------------------------------------------


class TestSearchManga:
    def test_returns_manga_list(self, anilist_client, anilist_http):
        items = [_manga_item(i) for i in range(1, 3)]
        anilist_http.enqueue(anilist_data({"Page": {"media": items}}))

        result = anilist_client.search_manga("one piece")

        assert len(result) == 2

    def test_empty_results(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"Page": {"media": []}}))

        result = anilist_client.search_manga("nonexistent")

        assert result == []

    def test_null_result_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))

        result = anilist_client.search_manga("anything")

        assert result == []

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("timeout"))

        with pytest.raises(Exception):
            anilist_client.search_manga("query")

    def test_passes_search_variable(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_data({"Page": {"media": [_manga_item()]}}))

        anilist_client.search_manga("naruto")

        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["search"] == "naruto"
