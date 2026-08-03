"""Coverage tests for services/anilist/discovery.py.

Targets the previously uncovered paths in:
- auto_discover_anilist_id: cache hits (list + old format), no-title skip, exception path
- get_anilist_id_from_title: simple pass-through
- clear_discovery_cache: per-title and full clear
- get_anilist_metadata: cache hits (dict + AniListAnime), fetch success/miss/exception
- discover_anilist_info: unauthenticated, empty title, no results, metadata exception,
  metadata None, full success path
"""

from unittest.mock import patch


from utils import cache as cache_module
from utils.cache import DiskCache
from models.models import AniListAnime, AniListTitle, AniListSearchResult
from services.anilist import anilist_service as discovery


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _anime(anime_id: int, romaji: str, english: str | None = None) -> AniListAnime:
    return AniListAnime(id=anime_id, title=AniListTitle(romaji=romaji, english=english))


def _search_result(
    anime_id: int = 1, score: int = 90, title: str = "Naruto"
) -> AniListSearchResult:
    return AniListSearchResult(anilist_id=anime_id, score=score, title=title)


# ---------------------------------------------------------------------------
# auto_discover_anilist_id – cache and edge-case branches
# ---------------------------------------------------------------------------


class TestAutoDiscoverCache:
    def test_returns_cached_list_on_second_call(self, temp_dir, monkeypatch):
        """Second call returns cached results without hitting the API again."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        results = [_anime(20, "Naruto")]
        with patch.object(discovery.anilist_client, "search_anime", return_value=results) as mock:
            first = discovery.auto_discover_anilist_id("naruto")
            second = discovery.auto_discover_anilist_id("naruto")

        assert len(first) == len(second)
        mock.assert_called_once()  # second call hits cache

    def test_old_int_cache_format_causes_refetch(self, temp_dir, monkeypatch):
        """Old cache format (int, not list) is ignored and API is called again."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        # Seed cache with old-format int value
        cache_key = "anilist_id:naruto"
        disk_cache.set(cache_key, 20, ttl=1000)

        results = [_anime(20, "Naruto")]
        with patch.object(discovery.anilist_client, "search_anime", return_value=results) as mock:
            discovery.auto_discover_anilist_id("naruto")

        mock.assert_called_once()  # cache miss because int format is ignored

    def test_malformed_list_cache_causes_refetch(self, temp_dir, monkeypatch):
        """A cached list with bad items (TypeError on unpack) falls through to re-fetch."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        # Seed cache with a list of non-dict items (causes TypeError in AniListSearchResult(**item))
        cache_key = "anilist_id:naruto"
        disk_cache.set(cache_key, ["not-a-dict", "also-not-a-dict"], ttl=1000)

        results = [_anime(20, "Naruto")]
        with patch.object(discovery.anilist_client, "search_anime", return_value=results) as mock:
            discovery.auto_discover_anilist_id("naruto")

        mock.assert_called_once()  # malformed cache was ignored, API was called

    def test_skips_anime_with_no_titles(self, temp_dir, monkeypatch):
        """Anime with empty romaji and english are skipped during matching."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        titleless = AniListAnime(id=99, title=AniListTitle(romaji=None, english=None))
        with patch.object(discovery.anilist_client, "search_anime", return_value=[titleless]):
            results = discovery.auto_discover_anilist_id("naruto")

        # No titles → no match possible
        assert results == []

    def test_exception_returns_empty_list(self, temp_dir, monkeypatch):
        """Any exception during discovery is caught and empty list returned."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        with patch.object(
            discovery.anilist_client, "search_anime", side_effect=RuntimeError("boom")
        ):
            results = discovery.auto_discover_anilist_id("some anime")

        assert results == []

    def test_empty_api_results_cached_as_empty(self, temp_dir, monkeypatch):
        """Empty API result is cached so second call skips API."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        with patch.object(discovery.anilist_client, "search_anime", return_value=[]) as mock:
            first = discovery.auto_discover_anilist_id("Unknown Anime XYZ")
            second = discovery.auto_discover_anilist_id("Unknown Anime XYZ")

        assert first == []
        assert second == []
        mock.assert_called_once()

    def test_below_threshold_not_included(self, temp_dir, monkeypatch):
        """Anime with score below threshold are excluded from results."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        # threshold is typically 70; "Z" vs "Naruto" will score very low
        results = [_anime(1, "Totally Unrelated Title ZZZZ")]
        with patch.object(discovery.anilist_client, "search_anime", return_value=results):
            matches = discovery.auto_discover_anilist_id("naruto")

        assert matches == []


# ---------------------------------------------------------------------------
# clear_discovery_cache
# ---------------------------------------------------------------------------


class TestClearDiscoveryCache:
    def test_clear_specific_title(self, temp_dir, monkeypatch):
        """Clearing a specific title returns 1."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        disk_cache.set(
            "anilist_id:naruto", [{"anilist_id": 20, "score": 90, "title": "Naruto"}], ttl=1000
        )

        n = discovery.clear_discovery_cache("naruto")
        assert n == 1

    def test_clear_specific_title_exception_returns_zero(self, temp_dir, monkeypatch):
        """When cache.delete raises, the except branch returns 0."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)
        # Patch cache.delete to raise to trigger the except branch (lines 207-208)
        monkeypatch.setattr(
            disk_cache, "delete", lambda key: (_ for _ in ()).throw(RuntimeError("fail"))
        )

        result = discovery.clear_discovery_cache("some title")
        assert result == 0

    def test_clear_all_returns_nonzero(self, temp_dir, monkeypatch):
        """Clearing all (no title arg) returns a non-zero sentinel."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)
        # clear_cache_by_prefix uses get_cache() internally which bypasses our monkeypatch;
        # patch the utility function directly so it doesn't touch real disk cache internals.
        monkeypatch.setattr(
            "services.anilist.anilist_service.clear_cache_by_prefix", lambda prefix: None
        )

        n = discovery.clear_discovery_cache()
        assert n == 1  # sentinel value defined in implementation


# ---------------------------------------------------------------------------
# get_anilist_metadata
# ---------------------------------------------------------------------------


class TestGetAniListMetadata:
    def test_returns_anime_on_success(self, temp_dir, monkeypatch):
        """Fetches and caches anime from API on first call."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        anime = _anime(1, "Naruto")
        with patch.object(discovery.anilist_client, "get_anime_by_id", return_value=anime):
            result = discovery.get_anilist_metadata(1)

        assert result is not None
        assert result.id == 1

    def test_returns_cached_dict(self, temp_dir, monkeypatch):
        """Cached dict is deserialized to AniListAnime."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        anime = _anime(1, "Naruto")
        disk_cache.set("anilist_meta:1", anime.model_dump(), ttl=1000)

        result = discovery.get_anilist_metadata(1)
        assert result is not None
        assert result.id == 1

    def test_returns_cached_anilistanime_object(self, temp_dir, monkeypatch):
        """Cached AniListAnime object is returned directly."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        anime = _anime(1, "Naruto")
        disk_cache.set("anilist_meta:1", anime, ttl=1000)

        result = discovery.get_anilist_metadata(1)
        assert result is not None
        assert result.id == 1

    def test_returns_none_when_api_returns_none(self, temp_dir, monkeypatch):
        """Returns None when API returns no result."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        with patch.object(discovery.anilist_client, "get_anime_by_id", return_value=None):
            result = discovery.get_anilist_metadata(999)

        assert result is None

    def test_returns_none_on_exception(self, temp_dir, monkeypatch):
        """Returns None when API raises a caught exception type."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        with patch.object(
            discovery.anilist_client, "get_anime_by_id", side_effect=TypeError("boom")
        ):
            result = discovery.get_anilist_metadata(1)

        assert result is None

    def test_second_call_uses_cache(self, temp_dir, monkeypatch):
        """Second call reads from cache without hitting API again."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        anime = _anime(1, "Naruto")
        with patch.object(discovery.anilist_client, "get_anime_by_id", return_value=anime) as mock:
            discovery.get_anilist_metadata(1)
            discovery.get_anilist_metadata(1)

        mock.assert_called_once()


# ---------------------------------------------------------------------------
# discover_anilist_info
# ---------------------------------------------------------------------------


class TestDiscoverAnilistInfo:
    def test_returns_unauthenticated_result_when_no_token(self, temp_dir, monkeypatch):
        """When client is not authenticated, result has authenticated=False."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        with patch.object(discovery.anilist_client, "is_authenticated", return_value=False):
            result = discovery.discover_anilist_info("Naruto")

        assert result.authenticated is False
        assert result.found is False
        assert result.anilist_id is None

    def test_returns_not_found_on_empty_normalized_title(self, temp_dir, monkeypatch):
        """If title normalizes to empty string, returns found=False, authenticated=True."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        with patch.object(discovery.anilist_client, "is_authenticated", return_value=True):
            with patch(
                "services.anilist.anilist_service.normalize_title_for_search", return_value=""
            ):
                result = discovery.discover_anilist_info("   ")

        assert result.authenticated is True
        assert result.found is False

    def test_returns_not_found_when_no_anilist_match(self, temp_dir, monkeypatch):
        """Empty discovery results → found=False, authenticated=True."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        with patch.object(discovery.anilist_client, "is_authenticated", return_value=True):
            with patch.object(discovery.anilist_client, "search_anime", return_value=[]):
                result = discovery.discover_anilist_info("Nonexistent Anime")

        assert result.authenticated is True
        assert result.found is False
        assert result.anilist_id is None

    def test_returns_partial_result_when_metadata_exception(self, temp_dir, monkeypatch):
        """Metadata fetch raises a caught exception → found=True but anilist_title=None."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        anime = _anime(1735, "Naruto Shippuuden", english="Naruto: Shippuden")
        with patch.object(discovery.anilist_client, "is_authenticated", return_value=True):
            with patch.object(discovery.anilist_client, "search_anime", return_value=[anime]):
                # Patch get_anilist_metadata directly so the exception propagates up
                # to discover_anilist_info's except block (lines 345-354)
                with patch(
                    "services.anilist.anilist_service.get_anilist_metadata",
                    side_effect=TypeError("err"),
                ):
                    result = discovery.discover_anilist_info("Naruto Shippuden")

        assert result.authenticated is True
        assert result.found is True
        assert result.anilist_id == 1735
        assert result.anilist_title is None

    def test_returns_partial_result_when_metadata_none(self, temp_dir, monkeypatch):
        """Metadata returns None → found=True but anilist_title=None."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        anime = _anime(1735, "Naruto Shippuuden", english="Naruto: Shippuden")
        with patch.object(discovery.anilist_client, "is_authenticated", return_value=True):
            with patch.object(discovery.anilist_client, "search_anime", return_value=[anime]):
                with patch.object(discovery.anilist_client, "get_anime_by_id", return_value=None):
                    result = discovery.discover_anilist_info("Naruto Shippuden")

        assert result.authenticated is True
        assert result.found is True
        assert result.anilist_id == 1735
        assert result.anilist_title is None

    def test_returns_full_result_on_success(self, temp_dir, monkeypatch):
        """Full happy path returns all fields populated."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        anime = _anime(1735, "Naruto Shippuuden", english="Naruto: Shippuden")
        anime_meta = AniListAnime(
            id=1735,
            title=AniListTitle(romaji="Naruto Shippuuden", english="Naruto: Shippuden"),
            episodes=500,
        )
        with patch.object(discovery.anilist_client, "is_authenticated", return_value=True):
            with patch.object(discovery.anilist_client, "search_anime", return_value=[anime]):
                with patch.object(
                    discovery.anilist_client, "get_anime_by_id", return_value=anime_meta
                ):
                    result = discovery.discover_anilist_info("Naruto Shippuden")

        assert result.authenticated is True
        assert result.found is True
        assert result.anilist_id == 1735
        assert result.anilist_title is not None
        assert result.total_episodes == 500

    def test_handles_search_exception_gracefully(self, temp_dir, monkeypatch):
        """Exception from auto_discover_anilist_id is caught, returns found=False."""
        disk_cache = DiskCache(cache_dir=temp_dir / "cache")
        monkeypatch.setattr(cache_module, "_global_cache", disk_cache)

        with patch.object(discovery.anilist_client, "is_authenticated", return_value=True):
            with patch(
                "services.anilist.anilist_service.auto_discover_anilist_id",
                side_effect=TypeError("network error"),
            ):
                result = discovery.discover_anilist_info("Naruto")

        assert result.authenticated is True
        assert result.found is False
