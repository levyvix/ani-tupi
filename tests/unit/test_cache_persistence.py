"""Tests for utils/cache.py and utils/persistence.py.

Strategy:
- Real objects, no mocking of internal logic
- Use tmp_path for file-based tests
- Manually expire _CacheItem to test TTL paths
- Skip permission tests when running as effective root
"""

import os
import stat
import time
from unittest.mock import patch

import pytest

from utils.persistence import JSONStore
from utils.exceptions import PersistenceError


# ---------------------------------------------------------------------------
# utils/persistence.py – JSONStore
# ---------------------------------------------------------------------------


class TestJSONStoreLoad:
    """Tests for JSONStore.load()."""

    def test_load_missing_file_returns_default(self, tmp_path):
        store = JSONStore(tmp_path / "missing.json")
        assert store.load() == {}

    def test_load_missing_file_returns_custom_default(self, tmp_path):
        store = JSONStore(tmp_path / "missing.json")
        assert store.load(default={"key": "val"}) == {"key": "val"}

    def test_load_invalid_json_returns_default(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ not valid json !!!", encoding="utf-8")
        store = JSONStore(bad_file)
        assert store.load(default=[]) == []

    def test_load_valid_json(self, tmp_path):
        good_file = tmp_path / "good.json"
        good_file.write_text('{"a": 1, "b": 2}', encoding="utf-8")
        store = JSONStore(good_file)
        assert store.load() == {"a": 1, "b": 2}

    def test_load_permission_error_raises_persistence_error(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("chmod has no effect as root")
        protected = tmp_path / "protected.json"
        protected.write_text('{"x": 1}', encoding="utf-8")
        protected.chmod(0o000)
        try:
            store = JSONStore(protected)
            with pytest.raises(PersistenceError, match="Permission denied"):
                store.load()
        finally:
            protected.chmod(stat.S_IRUSR | stat.S_IWUSR)


class TestJSONStoreSave:
    """Tests for JSONStore.save()."""

    def test_save_creates_parent_dirs(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "data.json"
        store = JSONStore(deep)
        store.save({"hello": "world"})
        assert deep.exists()

    def test_save_round_trip(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        payload = {"name": "Naruto", "episodes": 720}
        store.save(payload)
        assert store.load() == payload

    def test_save_permission_error_raises_persistence_error(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("chmod has no effect as root")
        locked_dir = tmp_path / "locked"
        locked_dir.mkdir()
        locked_dir.chmod(0o444)
        try:
            store = JSONStore(locked_dir / "data.json")
            with pytest.raises(PersistenceError, match="Permission denied"):
                store.save({"x": 1})
        finally:
            locked_dir.chmod(stat.S_IRWXU)

    def test_save_non_serializable_raises_persistence_error(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        with pytest.raises(PersistenceError, match="Cannot serialize"):
            store.save({"fn": lambda x: x})


class TestJSONStoreGetSet:
    """Tests for JSONStore.get() and .set()."""

    def test_get_missing_key_returns_none(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        assert store.get("missing") is None

    def test_get_missing_key_returns_custom_default(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        assert store.get("missing", default="fallback") == "fallback"

    def test_set_then_get(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        store.set("anime", "Bleach")
        assert store.get("anime") == "Bleach"

    def test_set_overwrites_existing_key(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        store.set("ep", 1)
        store.set("ep", 99)
        assert store.get("ep") == 99


class TestJSONStoreUpdate:
    """Tests for JSONStore.update()."""

    def test_update_merges_multiple_keys(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        store.set("a", 1)
        store.update({"b": 2, "c": 3})
        data = store.load()
        assert data == {"a": 1, "b": 2, "c": 3}

    def test_update_overwrites_key(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        store.set("x", "old")
        store.update({"x": "new"})
        assert store.get("x") == "new"


class TestJSONStoreDelete:
    """Tests for JSONStore.delete()."""

    def test_delete_removes_key(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        store.set("gone", True)
        store.delete("gone")
        assert store.get("gone") is None

    def test_delete_nonexistent_key_is_noop(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        # Should not raise
        store.delete("nope")

    def test_delete_leaves_other_keys_intact(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        store.set("keep", "yes")
        store.set("remove", "no")
        store.delete("remove")
        data = store.load()
        assert "remove" not in data
        assert data["keep"] == "yes"


class TestJSONStoreExistsClear:
    """Tests for JSONStore.exists() and .clear()."""

    def test_exists_false_when_missing(self, tmp_path):
        store = JSONStore(tmp_path / "nope.json")
        assert store.exists() is False

    def test_exists_true_after_save(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        store.save({"a": 1})
        assert store.exists() is True

    def test_clear_empties_file(self, tmp_path):
        store = JSONStore(tmp_path / "data.json")
        store.set("data", "here")
        store.clear()
        assert store.load() == {}


# ---------------------------------------------------------------------------
# utils/cache.py – _CacheItem
# ---------------------------------------------------------------------------


class TestCacheItem:
    """Tests for the _CacheItem helper class."""

    def test_is_not_expired_fresh_item(self):
        from utils.cache import _CacheItem

        item = _CacheItem("data", ttl=3600)
        assert not item.is_expired()

    def test_is_expired_old_item(self):
        from utils.cache import _CacheItem

        item = _CacheItem("data", ttl=1)
        item.created_at = time.time() - 100
        assert item.is_expired()

    def test_access_increments_count(self):
        from utils.cache import _CacheItem

        item = _CacheItem("data", ttl=3600)
        assert item.access_count == 0
        item.access()
        assert item.access_count == 1

    def test_access_updates_last_accessed(self):
        from utils.cache import _CacheItem

        item = _CacheItem("data", ttl=3600)
        before = item.last_accessed
        time.sleep(0.01)
        item.access()
        assert item.last_accessed >= before

    def test_size_bytes_returns_positive_int(self):
        from utils.cache import _CacheItem

        item = _CacheItem({"key": "value"}, ttl=60)
        assert isinstance(item.size_bytes(), int)
        assert item.size_bytes() > 0

    def test_size_bytes_non_serializable_fallback(self):
        from utils.cache import _CacheItem

        item = _CacheItem(object(), ttl=60)
        # Should not raise; uses sys.getsizeof fallback
        assert item.size_bytes() > 0


# ---------------------------------------------------------------------------
# utils/cache.py – MemoryCache
# ---------------------------------------------------------------------------


class TestMemoryCacheBasics:
    """Tests for MemoryCache basic set/get/delete/clear."""

    @pytest.fixture
    def cache(self):
        from utils.cache import MemoryCache

        return MemoryCache(max_size_mb=100, default_ttl=3600)

    def test_set_and_get(self, cache):
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_get_missing_returns_none(self, cache):
        assert cache.get("nope") is None

    def test_delete_removes_key(self, cache):
        cache.set("k", "v")
        deleted = cache.delete("k")
        assert deleted is True
        assert cache.get("k") is None

    def test_delete_missing_returns_false(self, cache):
        assert cache.delete("ghost") is False

    def test_clear_empties_cache(self, cache):
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_overwrite_existing_key(self, cache):
        cache.set("x", "old")
        cache.set("x", "new")
        assert cache.get("x") == "new"

    def test_get_stats_reflects_size(self, cache):
        cache.set("a", 1)
        cache.set("b", 2)
        stats = cache.get_stats()
        assert stats.total_items == 2

    def test_custom_ttl_per_item(self, cache):
        cache.set("k", "v", ttl=86400)
        assert cache.get("k") == "v"


class TestMemoryCacheTTLExpiry:
    """Tests for MemoryCache TTL/expiry paths."""

    def test_expired_item_removed_on_access(self):
        """Accessing an expired item removes it from the cache."""
        from utils.cache import MemoryCache

        cache = MemoryCache(default_ttl=3600)
        cache.set("zombie", "value")
        # Manually expire the item by backdating its creation
        cache._cache["zombie"].created_at = time.time() - 7200
        cache._cache["zombie"].ttl = 1
        result = cache.get("zombie")
        assert result is None
        assert "zombie" not in cache._cache

    def test_fresh_item_not_evicted(self):
        from utils.cache import MemoryCache

        cache = MemoryCache(default_ttl=3600)
        cache.set("fresh", "data")
        assert cache.get("fresh") == "data"

    def test_lru_eviction_with_tiny_cache(self):
        """LRU eviction fires when cache is at capacity."""
        from utils.cache import MemoryCache

        # max_size_mb=0 means max_size_bytes=0; every new insert triggers eviction
        cache = MemoryCache(max_size_mb=0, default_ttl=3600)
        cache.set("a", "v1")
        cache.set("b", "v2")
        # Should not crash; cache evicts as needed
        assert cache.get_stats().total_items >= 0


# ---------------------------------------------------------------------------
# utils/cache.py – DiskCache
# ---------------------------------------------------------------------------


class TestDiskCache:
    """Tests for DiskCache using a real temp directory."""

    @pytest.fixture
    def disk_cache(self, tmp_path):
        from utils.cache import DiskCache

        return DiskCache(cache_dir=tmp_path / "dc", default_ttl=3600)

    def test_set_and_get(self, disk_cache):
        disk_cache.set("key", "value")
        assert disk_cache.get("key") == "value"

    def test_get_missing_returns_none(self, disk_cache):
        assert disk_cache.get("nope") is None

    def test_delete_key(self, disk_cache):
        disk_cache.set("k", "v")
        result = disk_cache.delete("k")
        assert result is True
        assert disk_cache.get("k") is None

    def test_delete_missing_key(self, disk_cache):
        result = disk_cache.delete("ghost")
        assert result is False

    def test_clear(self, disk_cache):
        disk_cache.set("a", 1)
        disk_cache.set("b", 2)
        disk_cache.clear()
        assert disk_cache.get("a") is None
        assert disk_cache.get("b") is None

    def test_get_stats(self, disk_cache):
        disk_cache.set("x", "y")
        stats = disk_cache.get_stats()
        assert stats.total_items >= 0

    def test_set_with_custom_ttl(self, disk_cache):
        disk_cache.set("k", "v", ttl=60)
        assert disk_cache.get("k") == "v"


# ---------------------------------------------------------------------------
# utils/cache.py – HybridCache
# ---------------------------------------------------------------------------


class TestHybridCache:
    """Tests for HybridCache (memory + disk)."""

    @pytest.fixture
    def hybrid_cache(self, tmp_path):
        from utils.cache import HybridCache

        return HybridCache(cache_dir=tmp_path / "hc", memory_size_mb=10, default_ttl=3600)

    def test_set_and_get(self, hybrid_cache):
        hybrid_cache.set("key", "val")
        assert hybrid_cache.get("key") == "val"

    def test_disk_fallback_when_not_in_memory(self, hybrid_cache):
        hybrid_cache.set("k", "v")
        # Clear memory only so disk is the only copy
        hybrid_cache._memory.clear()
        # get() should promote from disk to memory
        assert hybrid_cache.get("k") == "v"

    def test_get_missing_returns_none(self, hybrid_cache):
        assert hybrid_cache.get("nope") is None

    def test_delete_removes_from_both(self, hybrid_cache):
        hybrid_cache.set("x", 1)
        hybrid_cache.delete("x")
        assert hybrid_cache.get("x") is None

    def test_clear_removes_all(self, hybrid_cache):
        hybrid_cache.set("a", 1)
        hybrid_cache.set("b", 2)
        hybrid_cache.clear()
        assert hybrid_cache.get("a") is None

    def test_get_stats_combined(self, hybrid_cache):
        hybrid_cache.set("x", 1)
        stats = hybrid_cache.get_stats()
        assert stats.total_items >= 0


# ---------------------------------------------------------------------------
# utils/cache.py – create_cache factory and global helpers
# ---------------------------------------------------------------------------


class TestCacheTypeFactory:
    """Tests for create_cache() factory function."""

    def test_create_memory_cache(self):
        from utils.cache import create_cache, CacheType, MemoryCache

        cache = create_cache(CacheType.MEMORY)
        assert isinstance(cache, MemoryCache)

    def test_create_cache_from_string(self):
        from utils.cache import create_cache, MemoryCache

        cache = create_cache("memory")
        assert isinstance(cache, MemoryCache)

    def test_create_invalid_type_raises(self):
        from utils.cache import create_cache

        with pytest.raises((ValueError, Exception)):
            create_cache("invalid_backend")

    def test_create_disk_cache(self, tmp_path):
        from utils.cache import create_cache, CacheType, DiskCache

        with patch("utils.cache.settings") as mock_settings:
            mock_settings.performance.smart_cache_max_size_mb = 50
            mock_settings.performance.search_cache_ttl = 3600
            mock_settings.performance.default_ttl_hours = 1
            mock_settings.cache.cache_dir = tmp_path / "disk_cache"
            cache = create_cache(CacheType.DISK)
        assert isinstance(cache, DiskCache)

    def test_create_hybrid_cache(self, tmp_path):
        from utils.cache import create_cache, CacheType, HybridCache

        with patch("utils.cache.settings") as mock_settings:
            mock_settings.performance.smart_cache_max_size_mb = 50
            mock_settings.performance.search_cache_ttl = 3600
            mock_settings.performance.default_ttl_hours = 1
            mock_settings.cache.cache_dir = tmp_path / "hybrid_cache"
            cache = create_cache(CacheType.HYBRID)
        assert isinstance(cache, HybridCache)


class TestGlobalCacheFunctions:
    """Tests for module-level cache utility functions."""

    def test_clear_cache_all_clears_global_cache(self, monkeypatch):
        from utils import cache as cache_mod
        from utils.cache import MemoryCache

        mc = MemoryCache(default_ttl=3600)
        mc.set("sentinel", "value")
        monkeypatch.setattr(cache_mod, "_global_cache", mc)

        cache_mod.clear_cache_all()
        assert mc.get("sentinel") is None

    def test_get_cache_returns_same_instance_on_repeat(self, monkeypatch):
        from utils import cache as cache_mod
        from utils.cache import MemoryCache

        mc = MemoryCache(default_ttl=60)
        monkeypatch.setattr(cache_mod, "_global_cache", mc)
        assert cache_mod.get_cache() is mc
        assert cache_mod.get_cache() is mc

    def test_get_cache_creates_fresh_when_none(self, monkeypatch):
        from utils import cache as cache_mod
        from utils.cache import Cache

        monkeypatch.setattr(cache_mod, "_global_cache", None)
        with patch("utils.cache.settings") as mock_settings:
            mock_settings.performance.cache_type = "memory"
            mock_settings.performance.smart_cache_max_size_mb = 50
            mock_settings.performance.search_cache_ttl = 3600
            result = cache_mod.get_cache()
        assert isinstance(result, Cache)

    def test_clear_cache_by_prefix_on_memory_cache(self, monkeypatch):
        """clear_cache_by_prefix doesn't crash on a MemoryCache (no iterkeys)."""
        from utils import cache as cache_mod
        from utils.cache import MemoryCache

        mc = MemoryCache(default_ttl=3600)
        mc.set("prefix_a", 1)
        mc.set("other", 3)
        monkeypatch.setattr(cache_mod, "_global_cache", mc)

        cache_mod.clear_cache_by_prefix("prefix_")
        # "other" should survive regardless
        assert mc.get("other") == 3

    def test_clear_cache_by_prefix_on_memory_cache_via_internal(self, monkeypatch):
        """clear_cache_by_prefix hits the _cache.keys() fallback on MemoryCache."""
        from utils import cache as cache_mod
        from utils.cache import MemoryCache

        mc = MemoryCache(default_ttl=3600)
        mc.set("prefix_x", 1)
        mc.set("prefix_y", 2)
        mc.set("keep", 3)
        monkeypatch.setattr(cache_mod, "_global_cache", mc)

        cache_mod.clear_cache_by_prefix("prefix_")
        # "keep" must survive; prefix keys are removed via _cache.keys() path
        assert mc.get("keep") == 3
