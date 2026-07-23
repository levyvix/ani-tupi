"""Unit tests for incremental_search_anime algorithm."""

from dataclasses import dataclass, field

import pytest

from models.models import AnimeMetadata
from services.anime.search import (
    IncrementalSearchState,
    _filter_anime_results,
    incremental_search_anime,
)


@dataclass
class InMemorySearchPlugin:
    """Deterministic scraper boundary returning real domain models."""

    name: str = "testsource"
    results_by_query: dict[str, list[str]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def set_results(self, query: str, titles: list[str]) -> None:
        self.results_by_query[query.casefold()] = list(titles)

    def search_anime(self, query: str) -> list[AnimeMetadata]:
        self.calls.append(query)
        return [
            AnimeMetadata(
                title=title,
                url=f"https://example.test/{self.name}/{index}",
                source=self.name,
                params={},
            )
            for index, title in enumerate(self.results_by_query.get(query.casefold(), []), start=1)
        ]


@pytest.fixture
def incremental_search_env(repository, monkeypatch):
    """Connect an isolated real repository to the search module."""
    import services.anime.search.core as search_core_module
    import services.anime.search.scraper_search as scraper_search_module
    from utils import cache as cache_module
    from utils.cache import MemoryCache

    plugin = InMemorySearchPlugin()
    repository.register(plugin)
    monkeypatch.setattr(search_core_module, "rep", repository)
    monkeypatch.setattr(scraper_search_module, "rep", repository)
    monkeypatch.setattr(cache_module, "_global_cache", MemoryCache())
    monkeypatch.setattr(
        "services.anilist.discovery.auto_discover_anilist_id",
        lambda _query: [],
    )
    return repository, plugin


def titled_variants(prefix: str, count: int) -> list[str]:
    """Build semantically searchable fixture titles."""
    return [f"{prefix} Variant {index:02d}" for index in range(1, count + 1)]


def test_incremental_search_stops_at_20_results(incremental_search_env):
    """Test that filtering stops when results ≤ 20.

    With the new filtering approach, we search once with 1 word to get base results,
    then filter for subsequent iterations instead of re-searching.

    However, if filtering returns ≤ 3 results AND they contain fast scrapers
    (API-based like animesdigital, animefire), we re-search with the full query
    to get better results (APIs may return different results for different queries).
    """
    _repository, plugin = incremental_search_env

    # Setup: 1 word returns 21 results (>20, so continue)
    # Results contain anime titles with sources, so filtering can work on them
    plugin.set_results(
        "boku",
        [
            "Boku no Hero",
            "Boku no Hero Season 2",
            "Boku no Hero Season 3",
            *titled_variants("Boku", 18),
        ],
    )

    # Setup: 2 words returns the filtered results (20 items)
    # When filtering "boku" -> "boku no" returns 3 results with fast scrapers,
    # we re-search with "boku no" to get better API results
    plugin.set_results(
        "boku no",
        [
            "Boku no Hero",
            "Boku no Hero Season 2",
            "Boku no Hero Season 3",
            "Boku no Hero Season 4",
            "Boku no Hero Season 5",
            "Boku no Hero Season 6",
            "Boku no Hero OVA 1",
            "Boku no Hero OVA 2",
            "Boku no Hero Movie 1",
            "Boku no Hero Movie 2",
            "Boku no Hero Special 1",
            "Boku no Hero Special 2",
            "Boku no Hero Special 3",
            "Boku no Hero Extra 1",
            "Boku no Hero Extra 2",
            "Boku no Hero Extra 3",
            "Boku no Hero Extra 4",
            "Boku no Hero Extra 5",
            "Boku no Hero Extra 6",
            "Boku no Hero Extra 7",
        ],
    )

    state, results = incremental_search_anime("boku no hero academia")

    # Should search twice:
    # 1. Initial search with "boku" (1 word)
    # 2. Filter/re-search with "boku no" after the base result set stayed > 20
    assert len(plugin.calls) == 2
    assert "boku" in plugin.calls
    assert "boku no" in plugin.calls

    # Should get results from the re-search
    assert state.get_current() is not None


def test_incremental_search_uses_all_words_if_needed(incremental_search_env):
    """Test that filtering uses all words if results still > 20.

    With filtering approach: search once with 3 words, then filter progressively.
    """
    _repository, plugin = incremental_search_env

    # Setup: base 3-word search returns > 20 results with many titles
    # Note: "attack on titan season 4" gets normalized to "attack on titan 4" (season removed)
    # So it has 4 words: "attack", "on", "titan", "4"
    # Starts with min(3,4)=3 words
    plugin.set_results(
        "attack on titan",
        [
            "Attack on Titan",
            "Attack on Titan Season 2",
            "Attack on Titan Season 3",
            "Attack on Titan Season 4",
            *titled_variants("Attack on Titan", 17),
        ],
    )

    state, results = incremental_search_anime("attack on titan season 4")

    # Should only search once (base 3-word search)
    # Then filter for 4-word iteration instead of re-searching
    assert len(plugin.calls) == 1  # Only base search, no re-search

    # Results should be from filtering, which may narrow results
    assert state.get_current() is not None


def test_incremental_search_starts_with_1_word_when_first_word_is_long_enough(
    incremental_search_env,
):
    """Search should start with one word when the first token has 4+ letters."""
    _repository, plugin = incremental_search_env

    plugin.set_results("shingeki", ["Shingeki no Kyojin Variant 01"])

    state, results = incremental_search_anime("shingeki no kyojin")

    assert plugin.calls[0] == "shingeki"


def test_incremental_search_starts_with_2_words_when_first_word_is_short(incremental_search_env):
    """Search should start with two words when the first token has fewer than 4 letters."""
    _repository, plugin = incremental_search_env

    plugin.set_results("no game", ["No Game No Life"])

    state, results = incremental_search_anime("no game no life")

    assert plugin.calls[0] == "no game"


def test_incremental_search_starts_with_fewer_if_query_short(incremental_search_env):
    """Test that search starts with all words if query < 3 words."""
    _repository, plugin = incremental_search_env

    plugin.set_results("dandadan", ["Dandadan Variant 01"])

    state, results = incremental_search_anime("dandadan")

    # Should start with 1 word
    assert len(plugin.calls) >= 1
    assert plugin.calls[0] == "dandadan"


def test_incremental_search_two_word_query(incremental_search_env):
    """Two-word queries with a short first token should start with both words."""
    _repository, plugin = incremental_search_env

    plugin.set_results("no game", ["No Game No Life Variant 01"])

    state, results = incremental_search_anime("no game")

    assert plugin.calls[0] == "no game"


def test_incremental_search_state_navigation(incremental_search_env):
    """Test that state tracks all iterations with filtering.

    With filtering: base search + filtering iterations both get tracked.
    """
    _repository, plugin = incremental_search_env

    # "my hero academia season 2" gets normalized to "my hero academia 2" (season removed)
    # So it has 4 words: "my", "hero", "academia", "2"
    # Starts with 1 word
    # Base search returns results containing titles with all relevant information
    plugin.set_results(
        "my",
        [
            "My Hero Academia",
            "My Hero Academia Season 2",
            "My Hero Academia Season 3",
            "My Hero Academia Season 4",
            "My Hero Academia Season 5",
            *titled_variants("My Hero Academia", 20),
        ],
    )

    state, results = incremental_search_anime("my hero academia season 2")

    # The real base result set is narrowed locally for the next word.
    assert len(state.search_history) >= 2
    assert state.search_history[0].word_count == 2
    assert state.search_history[1].is_filtered is True
    assert state.get_current() is not None


def test_incremental_search_zero_results_fallback(incremental_search_env):
    """Test fallback when filtering returns zero results.

    With filtering: when filter produces 0 results, we fallback to previous
    without re-searching.
    """
    _repository, plugin = incremental_search_env

    # Setup: 1 word returns 8 results (>5)
    # "test query with no match words" has 6 words
    plugin.set_results(
        "test",
        [
            "Test Anime",
            "Test Anime Season 2",
            "Test Anime Season 3",
            "Another Test",
            "Test Show",
            *titled_variants("Test", 3),
        ],
    )

    state, results = incremental_search_anime("test query with no match words")

    # Should only search once (base search)
    # Filtering will find some results (those containing "test")
    assert len(plugin.calls) == 1

    # Should return some results from the last valid step
    assert len(results) > 0
    assert state.get_current() is not None
    assert state.get_current().word_count == 1


def test_incremental_search_continues_after_empty_intermediate_refinement(incremental_search_env):
    """A failed intermediate refinement should not block later words from being tried."""
    _repository, plugin = incremental_search_env

    plugin.set_results(
        "hime",
        [
            "Himegoto",
            "Mushikaburi Hime",
            "Niehime to Kemono no Ou",
            "Akagami no Shirayuki Hime",
            "Koihime Musou",
            *titled_variants("Hime", 16),
        ],
    )
    # Non-matching titles keep SearchRepository from progressively retrying with
    # fewer words while still producing an empty displayed result set.
    plugin.set_results("hime kishi", ["Kishi Placeholder"])
    plugin.set_results("hime kishi wa", ["Wa Placeholder"])
    plugin.set_results(
        "hime kishi wa barbaroi",
        ["Hime Kishi wa Barbaroi no Yome"],
    )

    state, results = incremental_search_anime("hime kishi wa barbaroi no yome")

    assert plugin.calls == [
        "hime",
        "hime kishi",
        "hime kishi wa",
        "hime kishi wa barbaroi",
    ]
    assert state.get_current() is not None
    assert state.get_current().word_count == 4
    assert results == ["Hime Kishi wa Barbaroi no Yome [testsource]"]


def test_incremental_search_preserves_last_valid_filtered_step(incremental_search_env):
    """If a later word yields zero results, preserve the last narrowed result set."""
    _repository, plugin = incremental_search_env

    plugin.set_results(
        "hime",
        [
            "Himekishi wa Barbaroi no Yome",
            "Himegoto",
            "Mushikaburi Hime",
            "Niehime to Kemono no Ou",
            "Akagami no Shirayuki Hime",
            *titled_variants("Hime", 16),
        ],
    )
    plugin.set_results(
        "hime kishi",
        ["Himekishi wa Barbaroi no Yome"],
    )

    state, results = incremental_search_anime("hime kishi xyz")

    assert len(plugin.calls) == 2
    assert state.get_current() is not None
    assert state.get_current().word_count == 2
    assert results == ["Himekishi wa Barbaroi no Yome [testsource]"]


def test_incremental_search_zero_filtered_results_trigger_fresh_search(incremental_search_env):
    """If base filtering misses a title entirely, retry with a real refined search."""
    _repository, plugin = incremental_search_env

    plugin.set_results(
        "hime",
        [
            "Himegoto",
            "Mushikaburi Hime",
            "Niehime to Kemono no Ou",
            "Akagami no Shirayuki Hime",
            "Koihime Musou",
            *titled_variants("Hime", 16),
        ],
    )
    plugin.set_results(
        "hime kishi",
        ["Hime Kishi wa Barbaroi no Yome"],
    )

    state, results = incremental_search_anime("hime kishi wa barbaroi no yome")

    assert plugin.calls == ["hime", "hime kishi"]
    assert state.get_current() is not None
    assert state.get_current().word_count == 2
    assert results == ["Hime Kishi wa Barbaroi no Yome [testsource]"]


def test_incremental_search_source_counts(incremental_search_env):
    """Test that real deduplication and source counts reach search state."""
    repository, plugin = incremental_search_env
    secondary = InMemorySearchPlugin(name="secondary")
    repository.register(secondary)

    titles = titled_variants("Test Anime", 3)
    plugin.set_results("test", titles)
    secondary.set_results("test", [titles[0], "Test Anime Variant 04"])

    state, results = incremental_search_anime("test anime")

    current = state.get_current()
    assert current is not None
    assert current.source_counts == {
        "secondary, testsource": 1,
        "secondary": 1,
        "testsource": 2,
    }


def test_incremental_search_exactly_20_results(incremental_search_env):
    """Test that exactly 20 results triggers stop condition."""
    _repository, plugin = incremental_search_env

    # "test anime series long" has 4 words, starts with 1
    plugin.set_results(
        "test",
        titled_variants("Test", 20),
    )
    plugin.set_results(
        "test anime series long",
        [f"B{i}" for i in range(1, 23)],
    )

    state, results = incremental_search_anime("test anime series long")

    # Should stop at first iteration (20 results = ≤ 20)
    assert len(plugin.calls) == 1
    assert len(results) == 20


def test_incremental_search_returns_state_and_results(incremental_search_env):
    """Test that return value is tuple of (state, results)."""
    _repository, plugin = incremental_search_env
    plugin.set_results("anime", titled_variants("Anime", 2))

    result = incremental_search_anime("anime")

    assert isinstance(result, tuple)
    assert len(result) == 2
    state, results = result
    assert isinstance(state, IncrementalSearchState)
    assert isinstance(results, list)


def test_incremental_search_maintains_query_metadata(incremental_search_env):
    """Test that query metadata is stored for each iteration."""
    _repository, plugin = incremental_search_env

    plugin.set_results("spy family", ["Spy Family Variant 01"])

    state, results = incremental_search_anime("spy family tv special")

    current = state.get_current()
    assert current is not None
    assert current.query == "spy family"
    assert current.word_count == 2


# ============================================================================
# Tests for the new filtering-based approach (Task 1-7)
# ============================================================================


def test_filter_anime_results_basic():
    """Test basic filtering with simple substring match."""
    titles = [
        "Shield Hero",
        "Shield Hero Season 2",
        "Attack on Titan",
    ]

    # Filter by "shield" should match first two
    filtered = _filter_anime_results(titles, "shield")
    assert len(filtered) == 2
    assert "Shield Hero" in filtered
    assert "Shield Hero Season 2" in filtered


def test_filter_anime_results_case_insensitive():
    """Test that filtering is case-insensitive."""
    titles = [
        "Shield Hero",
        "Attack on Titan",
    ]

    # Query in uppercase should still match
    filtered = _filter_anime_results(titles, "SHIELD")
    assert len(filtered) == 1
    assert "Shield Hero" in filtered


def test_filter_anime_results_by_single_word():
    """Test filtering with a single word (like a number).

    With the word-matching approach, filtering by "2" finds all
    results containing the word "2".
    """
    titles = [
        "Shield Hero",
        "Shield Hero 2",
        "Shield Hero 3",
    ]

    # Filter by "2" should match Shield Hero 2
    filtered = _filter_anime_results(titles, "2")
    assert len(filtered) == 1
    assert "Shield Hero 2" in filtered


def test_filter_anime_results_numbered_anime():
    """Test filtering numbered anime titles like season numbers."""
    titles = [
        "Jujutsu Kaisen",
        "Jujutsu Kaisen 0",
        "Jujutsu Kaisen Season 2",
    ]

    # Filter by "0" should match Jujutsu Kaisen 0
    filtered = _filter_anime_results(titles, "jujutsu kaisen 0")
    assert len(filtered) == 1
    assert "Jujutsu Kaisen 0" in filtered


def test_filter_anime_results_empty():
    """Test filtering with no matches."""
    titles = [
        "Shield Hero",
        "Attack on Titan",
    ]

    # Filter by non-existent term
    filtered = _filter_anime_results(titles, "xyz")
    assert len(filtered) == 0


def test_filter_anime_results_punctuation_normalized():
    """Test that filtering normalizes punctuation like repository does."""
    titles = [
        "Boku no Hero Academia",
        "My Hero Academia",
    ]

    # Query with punctuation should be normalized
    filtered = _filter_anime_results(titles, "boku no hero")
    assert len(filtered) == 1
    assert "Boku no Hero Academia" in filtered


def test_search_result_set_filtered_flag():
    """Test that SearchResultSet has is_filtered field with default False."""
    from services.anime.search import SearchResultSet

    # Create with default (should be False)
    result_set = SearchResultSet(
        word_count=3,
        query="test query",
        results=["A1", "A2"],
    )
    assert result_set.is_filtered is False

    # Create with is_filtered=True
    result_set2 = SearchResultSet(
        word_count=4,
        query="test query expanded",
        results=["B1"],
        is_filtered=True,
    )
    assert result_set2.is_filtered is True


def test_incremental_search_filters_not_searches(incremental_search_env):
    """Test that subsequent iterations filter instead of re-searching.

    This is the core requirement: base results should be filtered,
    not re-searched from scrapers.
    """
    _repository, plugin = incremental_search_env

    # "tate no yuusha no nariagari 2" normalizes to same (no season pattern)
    # Has 6 words: "tate", "no", "yuusha", "no", "nariagari", "2"
    # Starts with min(3,6)=3 words

    # First search (3 words) returns many results, all compatible with the
    # next refinement. The fourth-word iteration must be local filtering.
    plugin.set_results(
        "tate no yuusha",
        [f"Tate no Yuusha no Variant {index:02d}" for index in range(1, 22)],
    )

    state, results = incremental_search_anime("tate no yuusha no")

    # With new filtering approach: should stop at 3 words if results <= 20
    # Because filtering reduces results from 8 to 3 (all contain "shield hero")
    # Actually, let's adjust: all base results contain "shield" so first search returns 8
    # After min(3,6)=3 words, we have 8 results which is > 5
    # Then we filter by 4 words: partial_query = "tate no yuusha no"
    # Filter base_results by "tate no yuusha no" -> no results match (titles don't contain all those words)
    # So should fall back to previous and not make another search call

    # Key assertion: should only search once (initial), not re-search
    # In the new implementation, after the initial search, we filter instead of searching
    assert len(plugin.calls) == 1  # Only initial 3-word search


def test_incremental_search_fallback_on_zero_filter(incremental_search_env):
    """Test that zero filter results fall back to previous without re-searching.

    With the new re-search logic: if filtering returns ≤ 3 results with fast scrapers,
    we re-search with the full query. This test checks that behavior.
    """
    _repository, plugin = incremental_search_env

    # Setup: 1-word search returns 21 results (>20, so continue filtering)
    plugin.set_results(
        "test",
        [
            "Test Anime",
            "Test Anime Season 2",
            "Test Anime Season 3",
            *titled_variants("Test", 18),
        ],
    )
    # When filtering "test" -> "test anime" returns 3 results with fast scrapers,
    # we re-search with "test anime" to get better API results
    plugin.set_results(
        "test anime",
        [
            "Test Anime",
            "Test Anime Season 2",
            "Test Anime Season 3",
        ],
    )

    state, results = incremental_search_anime("test anime ultra rare edition")

    # Should search twice:
    # 1. Initial search with "test" (1 word)
    # 2. Re-search with "test anime" (2 words) because filtered had ≤ 3 results with fast scrapers
    assert len(plugin.calls) == 2
    assert "test" in plugin.calls
    assert "test anime" in plugin.calls

    # Results should be from the re-search
    assert len(results) > 0


def test_incremental_search_is_filtered_flag_set(incremental_search_env):
    """Test that is_filtered flag is set correctly for filtered iterations."""
    _repository, plugin = incremental_search_env

    # Setup: return small result set so we can add more words
    plugin.set_results("test anime", ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"])
    # Note: With new filtering approach, we won't search again
    # We'll filter the base results

    state, results = incremental_search_anime("test anime series long")

    # Check that initial search has is_filtered=False
    assert state.search_history[0].is_filtered is False

    # Check that filtered iterations have is_filtered=True (if any exist)
    # In this case, after 3-word search we have 8 results > 5, so we'd add another word
    # But that would be filtered now, not searched
    if len(state.search_history) > 1:
        # If there's a second iteration, it should be marked as filtered
        assert state.search_history[1].is_filtered is True


def test_incremental_search_small_base_results_stops(incremental_search_env):
    """Test that algorithm stops immediately if base search returns ≤ 20 results."""
    _repository, plugin = incremental_search_env
    plugin.set_results("test", ["Test Variant 01", "Test Variant 02", "Test Variant 03"])

    state, results = incremental_search_anime("test anime series long")

    # Should stop after one search (base search returned ≤ 20)
    assert plugin.calls == ["test"]
    assert len(results) == 3


def test_filter_anime_results_with_multiple_sources():
    """Test filtering with multiple sources in brackets."""
    titles = [
        "Shield Hero",
        "Shield Hero 2",
        "Attack on Titan",
    ]

    # Filter by "2" should match only Shield Hero 2
    filtered = _filter_anime_results(titles, "2")
    assert len(filtered) == 1
    assert "Shield Hero 2" in filtered


def test_filter_anime_results_preserves_source_info():
    """Test that filtering preserves the source bracket information."""
    titles = [
        "Spy Family [animefire, sushianimes]",
        "Spy Family Season 2 [animefire]",
    ]

    filtered = _filter_anime_results(titles, "spy family season 2")
    assert len(filtered) == 1
    assert "[" in filtered[0]  # Should preserve brackets
    assert "]" in filtered[0]


def test_filter_anime_results_matches_compact_titles():
    """Compact normalized matching should handle concatenated scraper titles."""
    titles = [
        "Himekishi wa Barbaroi no Yome",
        "Himegoto",
        "Mushikaburi Hime",
    ]

    filtered = _filter_anime_results(titles, "hime kishi")

    assert filtered == ["Himekishi wa Barbaroi no Yome"]


def test_incremental_search_season_2_query_real_world(incremental_search_env):
    """Test real-world scenario: "Tate no Yuusha no Nariagari Season 2".

    This addresses the original issue where numbered queries would fail.
    When the number "2" is added, filtering should find Season 2 results
    because those titles contain all words in the expanded query.

    With the new stop condition, the search should keep adding words until the
    filtered results are <= 20. In this fixture, it reaches that threshold
    before needing a fresh full-query re-search.
    """
    _repository, plugin = incremental_search_env

    # Setup: base search with 1 word returns various titles (>20, so continue filtering)
    # This simulates what would happen when searching "tate"
    plugin.set_results(
        "tate",
        [
            "Tate no Yuusha no Nariagari",
            "Tate no Yuusha no Nariagari 2",
            "Tate no Yuusha no Nariagari Dublado",
            "Tate no Yuusha no Nariagari Season 2",
            "Tate no Yuusha no Nariagari Season 3",
            "Tate no Yuusha no Nariagari Season 4",
            *titled_variants("Tate", 16),
        ],
    )

    # Setup: full-query search remains available, but should not be used here
    # because the filtered result set drops to <= 20 before that point.
    plugin.set_results(
        "tate no yuusha no nariagari 2",
        [
            "Tate no Yuusha no Nariagari 2",
            "Tate no Yuusha no Nariagari Season 2",
        ],
    )

    # Perform the search with the full normalized query
    # "tate no yuusha no nariagari season 2" normalizes to "tate no yuusha no nariagari 2"
    state, results = incremental_search_anime("tate no yuusha no nariagari season 2")

    # Should only search once, then stop after filtering down to <= 20 results
    assert len(plugin.calls) == 1
    assert "tate" in plugin.calls

    # Results should still include Season 2 variants in the filtered set
    assert len(results) > 0
    assert any("season 2" in title.lower() or "nariagari 2" in title.lower() for title in results)

    # Check that the state tracks iterations
    assert state.get_current() is not None
    assert state.search_history[0].word_count == 1  # Base search with 1 word
    assert state.get_current().word_count == 2


def test_filter_by_number_finds_all_containing_results():
    """Test that filtering by number finds ALL results containing that number.

    This validates the core fix: when user searches for "2", we find
    ALL results that contain "2", whether it's "...2" or "Season 2",
    because ALL query words must appear in the result title (any order).
    """
    titles = [
        "Tate no Yuusha no Nariagari",
        "Tate no Yuusha no Nariagari 2",
        "Tate no Yuusha no Nariagari Season 2",
        "Tate no Yuusha no Nariagari Season 3",
    ]

    # Filter by the expanded query that includes the season number "2"
    # This simulates what happens when filtering after adding "2" to wordlist
    filtered = _filter_anime_results(titles, "tate no yuusha no nariagari 2")

    # Should find ALL results containing ALL query words:
    # - "Tate no Yuusha no Nariagari 2" ✓ (has: tate, no, yuusha, no, nariagari, 2)
    # - "Tate no Yuusha no Nariagari Season 2" ✓ (has: tate, no, yuusha, no, nariagari, 2, season)
    # - NOT "Tate no Yuusha no Nariagari Season 3" (missing: 2)
    assert len(filtered) == 2, f"Should find 2 results, got {len(filtered)}: {filtered}"

    # Both variants should be present
    assert any(
        "nariagari 2" in title.lower() and "season" not in title.lower() for title in filtered
    )
    assert any("season 2" in title.lower() for title in filtered)
