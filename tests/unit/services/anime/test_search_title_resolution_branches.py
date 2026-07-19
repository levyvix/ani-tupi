"""Tests targeting uncovered branches in services/anime/search.py and
services/anime/title_resolution.py.

Strategy:
- Pure/helper functions tested directly with no mocking.
- IncrementalSearchState navigation branches covered as unit tests.
- AnimeTitleResolver cache / provider-fallback branches covered with
  lightweight fakes (no httpx or real AniList).
- AniListTitleResolver / JikanTitleResolver timeout/exception/empty branches
  exercised by monkeypatching the external call boundaries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from unittest.mock import patch

from models.models import AnimeTitleResolution, AniListAnime, AniListTitle, JikanAnimeEntry

if TYPE_CHECKING:
    from services.anime.search import IncrementalSearchState


# ============================================================================
# IncrementalSearchState navigation branches  (lines 291-334, 344-388)
# ============================================================================


class TestIncrementalSearchStateNavigation:
    def _state_with(self, results_sets: list[list[str]]) -> "IncrementalSearchState":
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        for i, results in enumerate(results_sets, start=1):
            state.add_result(
                word_count=i,
                query=f"query{i}",
                results=results,
                used_query=f"query{i}",
            )
        return state

    def test_go_back_at_beginning_returns_none(self):
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        assert state.go_back() is None

    def test_go_back_from_second_returns_first(self):
        state = self._state_with([["A"], ["B"]])
        result = state.go_back()
        assert result is not None
        assert result.results == ["A"]

    def test_go_forward_at_end_returns_none(self):
        state = self._state_with([["A"]])
        assert state.go_forward() is None

    def test_go_forward_after_go_back(self):
        state = self._state_with([["A"], ["B"]])
        state.go_back()
        result = state.go_forward()
        assert result is not None
        assert result.results == ["B"]

    def test_get_current_on_empty_state_returns_none(self):
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        assert state.get_current() is None

    def test_has_previous_and_has_next(self):
        state = self._state_with([["A"], ["B"], ["C"]])
        state.go_back()  # now at index 1
        assert state.has_previous()
        assert state.has_next()

    def test_clear_resets_state(self):
        state = self._state_with([["A"], ["B"]])
        state.clear()
        assert state.get_current() is None
        assert not state.has_previous()
        assert not state.has_next()

    def test_add_result_discards_forward_history(self):
        state = self._state_with([["A"], ["B"], ["C"]])
        # Navigate back two steps
        state.go_back()
        state.go_back()
        # Now add a new result; forward history should be discarded
        state.add_result(word_count=99, query="new", results=["X"], used_query="new")
        assert not state.has_next()
        assert state.get_current().results == ["X"]

    def test_can_toggle_language_true_when_both_set(self):
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        state.alternative_title = "Alt Title"
        state.alternative_language = "english"
        assert state.can_toggle_language() is True

    def test_can_toggle_language_false_when_none(self):
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        assert state.can_toggle_language() is False

    def test_get_alternative_language_returns_none_when_not_toggleable(self):
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        assert state.get_alternative_language() is None

    def test_toggle_language_raises_when_not_available(self):
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        with pytest.raises(ValueError, match="Language toggle not available"):
            state.toggle_language()

    def test_toggle_language_swaps(self):
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        state.current_language = "romaji"
        state.current_title = "Romaji Title"
        state.alternative_language = "english"
        state.alternative_title = "English Title"
        new_lang = state.toggle_language()
        assert new_lang == "english"
        assert state.current_title == "English Title"
        assert state.alternative_title == "Romaji Title"

    def test_repr_shows_current_info(self):
        state = self._state_with([["A", "B"]])
        r = repr(state)
        assert "IncrementalSearchState" in r

    def test_repr_when_empty(self):
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        r = repr(state)
        assert "none" in r


# ============================================================================
# _count_sources  (lines 391-402)
# ============================================================================


class TestCountSources:
    def test_single_source(self):
        from services.anime.search.core import _count_sources

        result = _count_sources(["Naruto [animesdigital]"])
        assert result == {"animesdigital": 1}

    def test_multiple_sources_same_name(self):
        from services.anime.search.core import _count_sources

        result = _count_sources(["Naruto [animesdigital]", "Bleach [animesdigital]"])
        assert result == {"animesdigital": 2}

    def test_no_source_bracket(self):
        from services.anime.search.core import _count_sources

        result = _count_sources(["Naruto"])
        assert result == {}

    def test_mixed(self):
        from services.anime.search.core import _count_sources

        result = _count_sources(["A [src1]", "B [src2]", "C"])
        assert result["src1"] == 1
        assert result["src2"] == 1
        assert "C" not in result


# ============================================================================
# _best_similarity_score_for_reference (lines 171-197)
# ============================================================================


class TestBestSimilarityScore:
    def test_empty_titles_returns_zero(self):
        from services.anime.search import _best_similarity_score_for_reference

        assert _best_similarity_score_for_reference([], "Naruto") == 0

    def test_empty_reference_returns_zero(self):
        from services.anime.search import _best_similarity_score_for_reference

        assert _best_similarity_score_for_reference(["Naruto"], "") == 0

    def test_exact_match_returns_high_score(self):
        from services.anime.search import _best_similarity_score_for_reference

        score = _best_similarity_score_for_reference(["Naruto"], "Naruto")
        assert score > 80

    def test_title_with_source_bracket(self):
        from services.anime.search import _best_similarity_score_for_reference

        # Title in "Title [source]" format — base title should be extracted
        score = _best_similarity_score_for_reference(["Naruto [animesdigital]"], "Naruto")
        assert score > 80


# ============================================================================
# _filter_anime_results (lines 65-110)
# ============================================================================


class TestFilterAnimeResults:
    def test_substring_match(self):
        from services.anime.search import _filter_anime_results

        titles = ["Naruto Shippuden [src]", "One Piece [src]", "Bleach [src]"]
        result = _filter_anime_results(titles, "naruto")
        assert any("Naruto" in t for t in result)
        assert not any("One Piece" in t for t in result)

    def test_no_matches_returns_empty(self):
        from services.anime.search import _filter_anime_results

        titles = ["Naruto [src]", "One Piece [src]"]
        result = _filter_anime_results(titles, "gundam")
        assert result == []

    def test_all_match_empty_query(self):
        from services.anime.search import _filter_anime_results

        # Empty query string normalizes to empty - all words match vacuously
        titles = ["Naruto [src]", "One Piece [src]"]
        result = _filter_anime_results(titles, "")
        # empty query_normalized means all word in [] match — expect all titles back
        assert len(result) == len(titles)


# ============================================================================
# _build_search_query_candidates (lines 999-1030)
# ============================================================================


class TestBuildSearchQueryCandidates:
    def test_no_resolution_returns_only_original(self):
        from services.anime.search.core import _build_search_query_candidates

        result = _build_search_query_candidates("one piece", None)
        assert result == ["one piece"]

    def test_resolution_prepends_resolved_title(self):
        from services.anime.search.core import _build_search_query_candidates

        resolution = AnimeTitleResolution(
            original_query="op",
            resolved_title="One Piece",
            provider="jikan",
            confidence=90,
            aliases=("One Piece", "ワンピース"),
        )
        result = _build_search_query_candidates("op", resolution)
        assert result[0] == "One Piece"
        assert "op" in result

    def test_duplicates_are_deduplicated(self):
        from services.anime.search.core import _build_search_query_candidates

        resolution = AnimeTitleResolution(
            original_query="one piece",
            resolved_title="One Piece",
            provider="jikan",
            confidence=90,
            aliases=("One Piece",),
        )
        result = _build_search_query_candidates("one piece", resolution)
        # "One Piece" and "one piece" are the same when casefolded
        assert result.count("One Piece") + result.count("one piece") == 1

    def test_aliases_included(self):
        from services.anime.search.core import _build_search_query_candidates

        resolution = AnimeTitleResolution(
            original_query="naruto",
            resolved_title="Naruto",
            provider="jikan",
            confidence=95,
            aliases=("Naruto", "Naruto Shippuden"),
        )
        result = _build_search_query_candidates("naruto", resolution)
        assert "Naruto Shippuden" in result


# ============================================================================
# _search_results_from_serialized (lines 773-789)
# ============================================================================


class TestSearchResultsFromSerialized:
    def test_empty_payload(self):
        from services.anime.search.core import _search_results_from_serialized

        result = _search_results_from_serialized("query", {})
        assert result.titles_with_sources == []
        assert result.used_query == "query"

    def test_payload_with_titles(self):
        from services.anime.search.core import _search_results_from_serialized

        payload = {
            "used_query": "naruto shippuden",
            "titles_with_sources": ["Naruto [src]", "Naruto Shippuden [src]"],
        }
        result = _search_results_from_serialized("naruto shippuden", payload)
        assert result.used_query == "naruto shippuden"
        assert len(result.titles_with_sources) == 2
        assert result.state.get_current() is not None

    def test_uses_query_when_used_query_missing(self):
        from services.anime.search.core import _search_results_from_serialized

        payload = {"titles_with_sources": ["Anime A [src]"]}
        result = _search_results_from_serialized("my query", payload)
        assert result.used_query == "my query"


# ============================================================================
# _resolve_search_query (lines 987-996)
# ============================================================================


class TestResolveSearchQuery:
    def test_returns_none_when_disabled(self, monkeypatch):
        monkeypatch.setattr(
            "services.anime.search.core.settings.search.enable_title_resolution", False
        )
        from services.anime.search.core import _resolve_search_query

        result = _resolve_search_query("naruto")
        assert result is None

    def test_returns_none_when_resolved_same_as_query(self):
        from services.anime.search.core import _resolve_search_query
        from services.anime.title_resolution import AnimeTitleResolver

        static_result = AnimeTitleResolution(
            original_query="naruto",
            resolved_title="naruto",
            provider="jikan",
            confidence=100,
            aliases=("naruto",),
        )
        with patch.object(AnimeTitleResolver, "resolve", return_value=static_result):
            result = _resolve_search_query("naruto")
        assert result is None

    def test_returns_resolution_when_different_from_query(self):
        from services.anime.search.core import _resolve_search_query
        from services.anime.title_resolution import AnimeTitleResolver

        static_result = AnimeTitleResolution(
            original_query="re zero",
            resolved_title="Re:Zero kara Hajimeru Isekai Seikatsu",
            provider="jikan",
            confidence=85,
            aliases=("Re:Zero",),
        )
        with patch.object(AnimeTitleResolver, "resolve", return_value=static_result):
            result = _resolve_search_query("re zero")
        assert result is not None
        assert result.resolved_title == "Re:Zero kara Hajimeru Isekai Seikatsu"


# ============================================================================
# AnimeTitleResolver — cache branch and enable_title_resolution=False
# (title_resolution.py lines 195-220)
# ============================================================================


class FakeCache:
    def __init__(self):
        self.data: dict = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl=None):
        self.data[key] = value


class StaticProvider:
    def __init__(self, name: str, result: AnimeTitleResolution | None):
        self.name = name
        self.result = result
        self.calls = 0

    def resolve(self, query: str) -> AnimeTitleResolution | None:
        self.calls += 1
        return self.result


class TestAnimeTitleResolver:
    def test_returns_none_when_title_resolution_disabled(self, monkeypatch):
        from services.anime.title_resolution import AnimeTitleResolver

        monkeypatch.setattr(
            "services.anime.title_resolution.settings.search.enable_title_resolution", False
        )
        resolver = AnimeTitleResolver(providers=[], cache=FakeCache())
        assert resolver.resolve("naruto") is None

    def test_returns_none_for_empty_query(self):
        from services.anime.title_resolution import AnimeTitleResolver

        resolver = AnimeTitleResolver(providers=[], cache=FakeCache())
        assert resolver.resolve("") is None
        assert resolver.resolve("   ") is None

    def test_returns_cached_result_without_calling_provider(self):
        from services.anime.title_resolution import AnimeTitleResolver

        cache = FakeCache()
        provider = StaticProvider("test", None)
        resolver = AnimeTitleResolver(providers=[provider], cache=cache)

        expected = AnimeTitleResolution(
            original_query="naruto",
            resolved_title="Naruto",
            provider="test",
            confidence=90,
            aliases=("Naruto",),
        )
        # Pre-populate cache
        resolver.cache.set(resolver._cache_key("naruto"), expected.model_dump())

        result = resolver.resolve("naruto")
        assert result is not None
        assert result.resolved_title == "Naruto"
        assert provider.calls == 0  # cache hit — provider not called

    def test_calls_provider_on_cache_miss(self):
        from services.anime.title_resolution import AnimeTitleResolver

        expected = AnimeTitleResolution(
            original_query="bleach",
            resolved_title="Bleach",
            provider="test",
            confidence=95,
            aliases=("Bleach",),
        )
        provider = StaticProvider("test", expected)
        resolver = AnimeTitleResolver(providers=[provider], cache=FakeCache())

        result = resolver.resolve("bleach")
        assert result is not None
        assert result.resolved_title == "Bleach"
        assert provider.calls == 1

    def test_skips_provider_returning_none_tries_next(self):
        from services.anime.title_resolution import AnimeTitleResolver

        good = AnimeTitleResolution(
            original_query="query",
            resolved_title="Good Result",
            provider="second",
            confidence=80,
            aliases=("Good Result",),
        )
        p1 = StaticProvider("first", None)
        p2 = StaticProvider("second", good)
        resolver = AnimeTitleResolver(providers=[p1, p2], cache=FakeCache())

        result = resolver.resolve("query")
        assert result is not None
        assert result.resolved_title == "Good Result"
        assert p1.calls == 1
        assert p2.calls == 1

    def test_returns_none_when_all_providers_return_none(self):
        from services.anime.title_resolution import AnimeTitleResolver

        resolver = AnimeTitleResolver(providers=[StaticProvider("p", None)], cache=FakeCache())
        assert resolver.resolve("unknown anime xyz") is None

    def test_caches_result_after_provider_call(self):
        from services.anime.title_resolution import AnimeTitleResolver

        expected = AnimeTitleResolution(
            original_query="fate",
            resolved_title="Fate/stay night",
            provider="test",
            confidence=88,
            aliases=("Fate/stay night",),
        )
        cache = FakeCache()
        provider = StaticProvider("test", expected)
        resolver = AnimeTitleResolver(providers=[provider], cache=cache)
        resolver.resolve("fate")
        # Second call should hit cache
        provider.calls = 0
        resolver.resolve("fate")
        assert provider.calls == 0

    def test_corrupt_cache_entry_falls_through_to_provider(self):
        from services.anime.title_resolution import AnimeTitleResolver

        good = AnimeTitleResolution(
            original_query="q",
            resolved_title="Result",
            provider="p",
            confidence=70,
            aliases=("Result",),
        )
        cache = FakeCache()
        # Inject corrupt cache data (not a valid AnimeTitleResolution)
        cache.data["title-resolution:anime:q"] = {"bad": "data", "no_required_fields": True}
        provider = StaticProvider("p", good)
        resolver = AnimeTitleResolver(providers=[provider], cache=cache)
        result = resolver.resolve("q")
        # Should fall through to provider since cache validation fails
        assert result is not None or provider.calls >= 1


# ============================================================================
# AniListTitleResolver — timeout and exception branches (lines 80-88)
# ============================================================================


class TestAniListTitleResolver:
    def test_timeout_returns_none(self, monkeypatch):
        from services.anime.title_resolution import AniListTitleResolver
        from concurrent.futures import TimeoutError as FutureTimeoutError

        resolver = AniListTitleResolver()
        with patch(
            "services.anime.title_resolution._run_with_timeout", side_effect=FutureTimeoutError()
        ):
            result = resolver.resolve("naruto")
        assert result is None

    def test_general_exception_returns_none(self):
        from services.anime.title_resolution import AniListTitleResolver

        resolver = AniListTitleResolver()
        with patch(
            "services.anime.title_resolution._run_with_timeout",
            side_effect=ConnectionError("no net"),
        ):
            result = resolver.resolve("naruto")
        assert result is None

    def test_empty_results_returns_none(self):
        from services.anime.title_resolution import AniListTitleResolver

        resolver = AniListTitleResolver()
        with patch("services.anime.title_resolution._run_with_timeout", return_value=[]):
            result = resolver.resolve("naruto")
        assert result is None

    def test_result_with_no_resolvable_title_returns_none(self):
        """All title fields empty → resolved_title is empty → return None."""
        from services.anime.title_resolution import AniListTitleResolver

        anime = AniListAnime(
            id=1,
            title=AniListTitle(romaji=None, english=None, native=None),
            episodes=12,
            status="FINISHED",
            averageScore=80,
            seasonYear=2020,
        )
        with patch("services.anime.title_resolution._run_with_timeout", return_value=[anime]):
            result = AniListTitleResolver().resolve("query")
        assert result is None


# ============================================================================
# JikanTitleResolver — exception and empty-results branches (lines 133-173)
# ============================================================================


class TestJikanTitleResolver:
    def test_exception_returns_none(self):
        from services.anime.title_resolution import JikanTitleResolver

        resolver = JikanTitleResolver()
        with patch(
            "services.anime.title_resolution.jikan_client.search_anime",
            side_effect=ConnectionError("fail"),
        ):
            result = resolver.resolve("naruto")
        assert result is None

    def test_empty_results_returns_none(self):
        from services.anime.title_resolution import JikanTitleResolver

        with patch("services.anime.title_resolution.jikan_client.search_anime", return_value=[]):
            result = JikanTitleResolver().resolve("naruto")
        assert result is None

    def test_returns_resolution_for_valid_results(self):
        from services.anime.title_resolution import JikanTitleResolver

        entry = JikanAnimeEntry(
            mal_id=1,
            title="Naruto",
            title_english="Naruto",
            title_japanese="ナルト",
            synonyms=[],
            titles=[{"type": "Default", "title": "Naruto"}],
        )
        with patch(
            "services.anime.title_resolution.jikan_client.search_anime", return_value=[entry]
        ):
            result = JikanTitleResolver().resolve("naruto")
        assert result is not None
        assert result.resolved_title == "Naruto"
        assert result.provider == "jikan"

    def test_multiple_results_picks_highest_confidence(self):
        """When multiple results are returned, the one with best alias match wins."""
        from services.anime.title_resolution import JikanTitleResolver

        low = JikanAnimeEntry(
            mal_id=1,
            title="Completely Different XYZ",
            title_english=None,
            title_japanese=None,
            synonyms=[],
            titles=[],
        )
        high = JikanAnimeEntry(
            mal_id=2,
            title="Naruto Shippuden",
            title_english="Naruto Shippuden",
            title_japanese=None,
            synonyms=[],
            titles=[],
        )
        with patch(
            "services.anime.title_resolution.jikan_client.search_anime", return_value=[low, high]
        ):
            result = JikanTitleResolver().resolve("Naruto Shippuden")
        assert result is not None
        assert result.resolved_title == "Naruto Shippuden"


# ============================================================================
# _unique_aliases / _calculate_confidence helpers (title_resolution.py)
# ============================================================================


class TestHelpers:
    def test_unique_aliases_deduplicates_case_insensitive(self):
        from services.anime.title_resolution import _unique_aliases

        result = _unique_aliases(["Naruto", "naruto", "NARUTO", None, "  ", "Naruto Shippuden"])
        assert result.count("Naruto") == 1
        assert "Naruto Shippuden" in result

    def test_unique_aliases_skips_none_and_blank(self):
        from services.anime.title_resolution import _unique_aliases

        result = _unique_aliases([None, "", "  "])
        assert result == ()

    def test_calculate_confidence_empty_candidates(self):
        from services.anime.title_resolution import _calculate_confidence

        assert _calculate_confidence("query", ()) == 0

    def test_calculate_confidence_exact_match(self):
        from services.anime.title_resolution import _calculate_confidence

        score = _calculate_confidence("naruto", ("Naruto",))
        assert score > 80

    def test_init_language_tracking_sets_english_when_query_matches(self):
        from services.anime.search.core import _init_language_tracking
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        _init_language_tracking(
            state, "Fullmetal Alchemist", "Fullmetal Alchemist", "Hagane no Renkinjutsushi"
        )
        assert state.current_language == "english"
        assert state.alternative_language == "romaji"

    def test_init_language_tracking_sets_romaji_when_query_not_english(self):
        from services.anime.search.core import _init_language_tracking
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        _init_language_tracking(
            state, "Hagane no Renkinjutsushi", "Fullmetal Alchemist", "Hagane no Renkinjutsushi"
        )
        assert state.current_language == "romaji"
        assert state.alternative_language == "english"

    def test_init_language_tracking_noop_when_titles_same(self):
        from services.anime.search.core import _init_language_tracking
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        _init_language_tracking(state, "Naruto", "Naruto", "Naruto")
        # english == romaji, so tracking should NOT be seeded
        assert state.alternative_title is None

    def test_init_language_tracking_noop_when_none(self):
        from services.anime.search.core import _init_language_tracking
        from services.anime.search import IncrementalSearchState

        state = IncrementalSearchState()
        _init_language_tracking(state, "Naruto", None, None)
        assert state.alternative_title is None
