"""Tests for AnimeOperationsMixin (services/anilist/anime_operations.py).

Uses real AniListClient + mixin; only the external httpx.post boundary is mocked.
"""

import pytest

from tests.fixtures.anilist import (
    anilist_errors,
    graphql_response,
    media_entry,
    media_list_collection,
    save_media_list_entry,
    viewer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _media_list_entry_payload(
    entry_id: int = 1,
    status: str = "CURRENT",
    progress: int = 3,
    created_at: int = 1_000_000,
    media_id: int = 10,
) -> dict:
    """Build a raw media-list entry dict suitable for MediaListCollection."""
    return {
        "id": entry_id,
        "status": status,
        "progress": progress,
        "createdAt": created_at,
        "media": media_entry(media_id),
    }


def _relation_edge(
    relation_type: str = "SEQUEL",
    node_id: int = 20,
    node_type: str = "ANIME",
) -> dict:
    return {
        "relationType": relation_type,
        "node": {
            "id": node_id,
            "idMal": node_id + 1000,
            "type": node_type,
            "title": {"romaji": "Sequel Anime", "english": "Sequel Anime", "native": "SA"},
            "episodes": 12,
            "status": "FINISHED",
            "startDate": {"year": 2025, "month": 1, "day": 1},
        },
    }


def _activity_payload(activity_id: int = 5) -> dict:
    return {
        "id": activity_id,
        "status": "watched",
        "progress": "3",
        "createdAt": 1_700_000,
        "media": media_entry(10),
    }


# ===========================================================================
# get_trending
# ===========================================================================


class TestGetTrending:
    def test_returns_list_of_anime(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response({"Page": {"media": [media_entry(1), media_entry(2)]}})
        )
        results = anilist_client.get_trending()
        assert len(results) == 2
        assert results[0].id == 1
        assert results[1].id == 2

    def test_empty_media_list(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Page": {"media": []}}))
        results = anilist_client.get_trending()
        assert results == []

    def test_none_result_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))
        results = anilist_client.get_trending()
        assert results == []

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("Server error"))
        with pytest.raises(Exception):
            anilist_client.get_trending()

    def test_passes_year_and_season(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Page": {"media": []}}))
        anilist_client.get_trending(year=2024, season="WINTER")
        call = anilist_http.calls[0]
        variables = call["json"]["variables"]
        assert variables["seasonYear"] == 2024
        assert variables["season"] == "WINTER"

    def test_passes_page_and_per_page(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Page": {"media": []}}))
        anilist_client.get_trending(page=2, per_page=5)
        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["page"] == 2
        assert variables["perPage"] == 5

    def test_network_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("network down"))
        with pytest.raises(Exception):
            anilist_client.get_trending()


# ===========================================================================
# get_user_list
# ===========================================================================


class TestGetUserList:
    def test_unauthenticated_returns_empty(self, anilist_client, anilist_http):
        anilist_client.token = None
        results = anilist_client.get_user_list("CURRENT")
        assert results == []
        assert anilist_http.call_count == 0

    def test_returns_entries(self, anilist_client, anilist_http):
        entry = _media_list_entry_payload()
        anilist_http.enqueue(graphql_response(media_list_collection([entry])))
        results = anilist_client.get_user_list("CURRENT")
        assert len(results) == 1
        assert results[0].id == 1
        assert results[0].status == "CURRENT"

    def test_sorted_by_created_at_desc(self, anilist_client, anilist_http):
        e1 = _media_list_entry_payload(entry_id=1, created_at=100)
        e2 = _media_list_entry_payload(entry_id=2, created_at=200)
        anilist_http.enqueue(graphql_response(media_list_collection([e1, e2])))
        results = anilist_client.get_user_list("CURRENT")
        assert results[0].id == 2  # most recent first

    def test_empty_collection_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(media_list_collection([])))
        results = anilist_client.get_user_list("CURRENT")
        assert results == []

    def test_no_media_list_collection_key(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        results = anilist_client.get_user_list("CURRENT")
        assert results == []

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("Forbidden"))
        with pytest.raises(Exception):
            anilist_client.get_user_list("CURRENT")

    def test_fetches_viewer_when_user_id_is_none(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        # First call: viewer info; second call: user list
        anilist_http.enqueue(graphql_response({"Viewer": viewer(user_id=42)})).enqueue(
            graphql_response(media_list_collection([]))
        )
        results = anilist_client.get_user_list("CURRENT")
        assert results == []
        assert anilist_client.user_id == 42
        assert anilist_http.call_count == 2

    def test_returns_empty_when_viewer_fetch_fails(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response({}))  # no Viewer key → get_viewer_info returns None
        results = anilist_client.get_user_list("CURRENT")
        assert results == []


# ===========================================================================
# change_status
# ===========================================================================


class TestChangeStatus:
    def test_unauthenticated_returns_false(self, anilist_client, anilist_http):
        anilist_client.token = None
        result = anilist_client.change_status(1, "CURRENT")
        assert result is False
        assert anilist_http.call_count == 0

    def test_success_returns_true(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(save_media_list_entry(99, status="CURRENT")))
        result = anilist_client.change_status(1, "CURRENT")
        assert result is True

    def test_missing_key_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        result = anilist_client.change_status(1, "CURRENT")
        assert result is False

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("not found"))
        with pytest.raises(Exception):
            anilist_client.change_status(1, "CURRENT")

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("timeout"))
        with pytest.raises(Exception):
            anilist_client.change_status(1, "CURRENT")


# ===========================================================================
# update_progress
# ===========================================================================


class TestUpdateProgress:
    def test_unauthenticated_returns_false(self, anilist_client, anilist_http):
        anilist_client.token = None
        result = anilist_client.update_progress(1, 5)
        assert result is False
        assert anilist_http.call_count == 0

    def test_success_returns_true(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(save_media_list_entry(99, progress=5)))
        result = anilist_client.update_progress(1, 5)
        assert result is True

    def test_missing_save_key_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        result = anilist_client.update_progress(1, 5)
        assert result is False

    def test_none_result_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))
        result = anilist_client.update_progress(1, 5)
        assert result is False

    def test_completed_error_returns_true(self, anilist_client, anilist_http):
        """Anime already completed → treated as success (return True)."""
        anilist_http.enqueue(anilist_errors("already completed"))
        result = anilist_client.update_progress(1, 5)
        assert result is True

    def test_finished_error_returns_true(self, anilist_client, anilist_http):
        """'finished' keyword in error → also treated as success."""
        anilist_http.enqueue(anilist_errors("series is already finished"))
        result = anilist_client.update_progress(1, 5)
        assert result is True

    def test_exceed_error_returns_false(self, anilist_client, anilist_http):
        """Progress would exceed total episodes → returns False."""
        anilist_http.enqueue(anilist_errors("progress would exceed total"))
        result = anilist_client.update_progress(1, 9999)
        assert result is False

    def test_generic_exception_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("random error"))
        result = anilist_client.update_progress(1, 5)
        assert result is False


# ===========================================================================
# search_anime
# ===========================================================================


class TestSearchAnime:
    def test_returns_results(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response({"Page": {"media": [media_entry(1), media_entry(2)]}})
        )
        results = anilist_client.search_anime("attack on titan")
        assert len(results) == 2

    def test_empty_results(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Page": {"media": []}}))
        results = anilist_client.search_anime("no match")
        assert results == []

    def test_none_result_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))
        results = anilist_client.search_anime("test")
        assert results == []

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("rate limited"))
        with pytest.raises(Exception):
            anilist_client.search_anime("test")

    def test_passes_search_variable(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Page": {"media": []}}))
        anilist_client.search_anime("naruto")
        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["search"] == "naruto"


# ===========================================================================
# get_anime_by_id
# ===========================================================================


class TestGetAnimeById:
    def test_returns_anime(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Media": media_entry(42)}))
        result = anilist_client.get_anime_by_id(42)
        assert result is not None
        assert result.id == 42

    def test_none_result_returns_none(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))
        result = anilist_client.get_anime_by_id(99)
        assert result is None

    def test_missing_media_key_returns_none(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        result = anilist_client.get_anime_by_id(99)
        assert result is None

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("not found"))
        with pytest.raises(Exception):
            anilist_client.get_anime_by_id(99)

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("network"))
        with pytest.raises(Exception):
            anilist_client.get_anime_by_id(1)


# ===========================================================================
# get_recent_activities
# ===========================================================================


class TestGetRecentActivities:
    def test_unauthenticated_returns_empty(self, anilist_client, anilist_http):
        anilist_client.token = None
        results = anilist_client.get_recent_activities()
        assert results == []
        assert anilist_http.call_count == 0

    def test_returns_activities(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response({"Page": {"activities": [_activity_payload(1), _activity_payload(2)]}})
        )
        results = anilist_client.get_recent_activities()
        assert len(results) == 2
        assert results[0].id == 1

    def test_empty_activities(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Page": {"activities": []}}))
        results = anilist_client.get_recent_activities()
        assert results == []

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("error"))
        with pytest.raises(Exception):
            anilist_client.get_recent_activities()

    def test_fetches_viewer_when_user_id_is_none(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response({"Viewer": viewer(user_id=42)})).enqueue(
            graphql_response({"Page": {"activities": []}})
        )
        results = anilist_client.get_recent_activities()
        assert results == []
        assert anilist_client.user_id == 42

    def test_returns_empty_when_viewer_fetch_fails(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response({}))
        results = anilist_client.get_recent_activities()
        assert results == []

    def test_none_result_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))
        results = anilist_client.get_recent_activities()
        assert results == []


# ===========================================================================
# is_in_any_list
# ===========================================================================


class TestIsInAnyList:
    def test_unauthenticated_returns_false(self, anilist_client, anilist_http):
        anilist_client.token = None
        result = anilist_client.is_in_any_list(1)
        assert result is False
        assert anilist_http.call_count == 0

    def test_in_list_returns_true(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"MediaList": {"id": 1, "status": "CURRENT"}}))
        result = anilist_client.is_in_any_list(10)
        assert result is True

    def test_not_in_list_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        result = anilist_client.is_in_any_list(10)
        assert result is False

    def test_null_media_list_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"MediaList": None}))
        result = anilist_client.is_in_any_list(10)
        assert result is False

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("not in list"))
        with pytest.raises(Exception):
            anilist_client.is_in_any_list(10)

    def test_fetches_viewer_when_user_id_is_none(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response({"Viewer": viewer(user_id=42)})).enqueue(
            graphql_response({"MediaList": {"id": 1, "status": "CURRENT"}})
        )
        result = anilist_client.is_in_any_list(10)
        assert result is True
        assert anilist_client.user_id == 42

    def test_returns_false_when_viewer_fetch_fails(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response({}))
        result = anilist_client.is_in_any_list(10)
        assert result is False


# ===========================================================================
# add_to_list
# ===========================================================================


class TestAddToList:
    def test_success_returns_true(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response(
                save_media_list_entry(
                    5,
                    status="PLANNING",
                    media={"id": 10, "idMal": 1010, "title": {"romaji": "X"}},
                )
            )
        )
        result = anilist_client.add_to_list(10, status="PLANNING")
        assert result is True

    def test_missing_key_returns_false(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        result = anilist_client.add_to_list(10)
        assert result is False

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("mutation failed"))
        with pytest.raises(Exception):
            anilist_client.add_to_list(10)

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("crash"))
        with pytest.raises(Exception):
            anilist_client.add_to_list(10)

    def test_default_status_is_current(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(save_media_list_entry(1, status="CURRENT")))
        anilist_client.add_to_list(10)
        variables = anilist_http.calls[0]["json"]["variables"]
        assert variables["status"] == "CURRENT"


# ===========================================================================
# get_anime_relations
# ===========================================================================


class TestGetAnimeRelations:
    def test_returns_edges(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response(
                {
                    "Media": {
                        "relations": {
                            "edges": [
                                _relation_edge("SEQUEL"),
                                _relation_edge("PREQUEL", node_id=30),
                            ]
                        }
                    }
                }
            )
        )
        results = anilist_client.get_anime_relations(1)
        assert len(results) == 2
        assert results[0].relationType == "SEQUEL"

    def test_no_relations_key_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Media": {}}))
        results = anilist_client.get_anime_relations(1)
        assert results == []

    def test_none_result_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response(None))
        results = anilist_client.get_anime_relations(1)
        assert results == []

    def test_missing_media_key_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        results = anilist_client.get_anime_relations(1)
        assert results == []

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("error"))
        with pytest.raises(Exception):
            anilist_client.get_anime_relations(1)


# ===========================================================================
# get_sequels
# ===========================================================================


class TestGetSequels:
    def test_returns_only_anime_sequels(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response(
                {
                    "Media": {
                        "relations": {
                            "edges": [
                                _relation_edge("SEQUEL", node_id=20, node_type="ANIME"),
                                _relation_edge("SEQUEL", node_id=21, node_type="MANGA"),
                                _relation_edge("PREQUEL", node_id=19, node_type="ANIME"),
                            ]
                        }
                    }
                }
            )
        )
        sequels = anilist_client.get_sequels(1)
        assert len(sequels) == 1
        assert sequels[0].id == 20
        assert sequels[0].type == "ANIME"

    def test_no_sequels_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response({"Media": {"relations": {"edges": [_relation_edge("PREQUEL")]}}})
        )
        sequels = anilist_client.get_sequels(1)
        assert sequels == []

    def test_empty_relations(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"Media": {"relations": {"edges": []}}}))
        sequels = anilist_client.get_sequels(1)
        assert sequels == []


# ===========================================================================
# get_media_list_entry
# ===========================================================================


class TestGetMediaListEntry:
    def test_unauthenticated_returns_none(self, anilist_client, anilist_http):
        anilist_client.token = None
        result = anilist_client.get_media_list_entry(1)
        assert result is None
        assert anilist_http.call_count == 0

    def test_returns_entry(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response(
                {"MediaList": {"id": 5, "status": "CURRENT", "progress": 3, "score": 0}}
            )
        )
        result = anilist_client.get_media_list_entry(10)
        assert result is not None
        assert result.id == 5
        assert result.status == "CURRENT"

    def test_null_media_list_returns_none(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({"MediaList": None}))
        result = anilist_client.get_media_list_entry(10)
        assert result is None

    def test_missing_key_returns_none(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        result = anilist_client.get_media_list_entry(10)
        assert result is None

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("not found"))
        with pytest.raises(Exception):
            anilist_client.get_media_list_entry(10)

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("crash"))
        with pytest.raises(Exception):
            anilist_client.get_media_list_entry(10)

    def test_fetches_viewer_when_user_id_is_none(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response({"Viewer": viewer(user_id=42)})).enqueue(
            graphql_response(
                {"MediaList": {"id": 5, "status": "CURRENT", "progress": 1, "score": 0}}
            )
        )
        result = anilist_client.get_media_list_entry(10)
        assert result is not None
        assert anilist_client.user_id == 42

    def test_returns_none_when_viewer_fetch_fails(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response({}))
        result = anilist_client.get_media_list_entry(10)
        assert result is None


# ===========================================================================
# get_airing_episodes_for_watching
# ===========================================================================


class TestGetAiringEpisodesForWatching:
    def _airing_entry(self, media_id: int = 10) -> dict:
        return {
            "progress": 3,
            "media": {
                "id": media_id,
                "idMal": media_id + 1000,
                "title": {"romaji": "Test", "english": "Test", "native": "T"},
                "averageScore": 80,
                "status": "RELEASING",
                "episodes": 24,
                "endDate": {"year": None, "month": None, "day": None},
                "nextAiringEpisode": {"episode": 4, "airingAt": 1_800_000},
            },
        }

    def test_unauthenticated_returns_empty(self, anilist_client, anilist_http):
        anilist_client.token = None
        results = anilist_client.get_airing_episodes_for_watching()
        assert results == []
        assert anilist_http.call_count == 0

    def test_returns_raw_entries(self, anilist_client, anilist_http):
        entry = self._airing_entry()
        anilist_http.enqueue(
            graphql_response({"MediaListCollection": {"lists": [{"entries": [entry]}]}})
        )
        results = anilist_client.get_airing_episodes_for_watching()
        assert len(results) == 1
        assert results[0]["progress"] == 3

    def test_empty_list_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(
            graphql_response({"MediaListCollection": {"lists": [{"entries": []}]}})
        )
        results = anilist_client.get_airing_episodes_for_watching()
        assert results == []

    def test_missing_collection_key_returns_empty(self, anilist_client, anilist_http):
        anilist_http.enqueue(graphql_response({}))
        results = anilist_client.get_airing_episodes_for_watching()
        assert results == []

    def test_error_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(anilist_errors("forbidden"))
        with pytest.raises(Exception):
            anilist_client.get_airing_episodes_for_watching()

    def test_exception_propagates(self, anilist_client, anilist_http):
        anilist_http.enqueue(Exception("crash"))
        with pytest.raises(Exception):
            anilist_client.get_airing_episodes_for_watching()

    def test_fetches_viewer_when_user_id_is_none(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        entry = self._airing_entry()
        anilist_http.enqueue(graphql_response({"Viewer": viewer(user_id=42)})).enqueue(
            graphql_response({"MediaListCollection": {"lists": [{"entries": [entry]}]}})
        )
        results = anilist_client.get_airing_episodes_for_watching()
        assert len(results) == 1
        assert anilist_client.user_id == 42

    def test_returns_empty_when_viewer_fetch_fails(self, anilist_client, anilist_http):
        anilist_client.user_id = None
        anilist_http.enqueue(graphql_response({}))
        results = anilist_client.get_airing_episodes_for_watching()
        assert results == []

    def test_flattens_multiple_list_groups(self, anilist_client, anilist_http):
        e1 = self._airing_entry(10)
        e2 = self._airing_entry(11)
        anilist_http.enqueue(
            graphql_response(
                {"MediaListCollection": {"lists": [{"entries": [e1]}, {"entries": [e2]}]}}
            )
        )
        results = anilist_client.get_airing_episodes_for_watching()
        assert len(results) == 2
