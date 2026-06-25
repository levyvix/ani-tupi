"""Unified cache system with pluggable backends.

Replaces 4 different cache implementations with a single interface:
- Memory cache: Fast in-memory with TTL and LRU
- Disk cache: Persistent storage using diskcache (SQLite)
- Hybrid: Memory first, disk fallback for persistence

Configuration in models/config.py determines cache type and behavior.
"""

import time
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union
from pathlib import Path
from enum import Enum

from diskcache import FanoutCache
from models.config import settings
from models.models import CacheStats


class CacheType(str, Enum):
    """Supported cache backend types."""

    MEMORY = "memory"
    DISK = "disk"
    HYBRID = "hybrid"


class Cache(ABC):
    """Abstract cache interface for all cache implementations."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (defaults to cache default)
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if not found
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached items."""
        pass

    @abstractmethod
    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats with current cache information
        """
        pass

    def cleanup_expired(self) -> None:
        """Remove expired items (optional for backends that handle automatically)."""
        pass


class MemoryCache(Cache):
    """In-memory cache with TTL and LRU eviction.

    Thread-safe implementation for fast access without persistence.
    """

    def __init__(self, max_size_mb: int = 100, default_ttl: int = 3600):
        """Initialize memory cache.

        Args:
            max_size_mb: Maximum cache size in MB
            default_ttl: Default TTL in seconds
        """
        self._cache: Dict[str, "_CacheItem"] = {}
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._current_size_bytes = 0
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None

            if item.is_expired():
                del self._cache[key]
                self._current_size_bytes -= item.size_bytes()
                return None

            item.access()
            return item.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        if ttl is None:
            ttl = self._default_ttl

        with self._lock:
            # Remove existing item
            if key in self._cache:
                old_item = self._cache[key]
                self._current_size_bytes -= old_item.size_bytes()

            # Create new item
            new_item = _CacheItem(value, ttl)
            item_size = new_item.size_bytes()

            # Evict if necessary
            while self._current_size_bytes + item_size > self._max_size_bytes and self._cache:
                self._evict_lru()

            # Add new item
            self._cache[key] = new_item
            self._current_size_bytes += item_size

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        with self._lock:
            item = self._cache.pop(key, None)
            if item:
                self._current_size_bytes -= item.size_bytes()
                return True
            return False

    def clear(self) -> None:
        """Clear all cached items."""
        with self._lock:
            self._cache.clear()
            self._current_size_bytes = 0

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        with self._lock:
            return CacheStats(
                size=len(self._cache),
                total_items=len(self._cache),
            )

    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if not self._cache:
            return

        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
        lru_item = self._cache[lru_key]
        del self._cache[lru_key]
        self._current_size_bytes -= lru_item.size_bytes()


class DiskCache(Cache):
    """Persistent disk cache using diskcache (SQLite backend).

    Provides durability and larger storage capacity.
    """

    def __init__(self, cache_dir: Optional[Path] = None, default_ttl: int = 3600):
        """Initialize disk cache.

        Args:
            cache_dir: Directory for cache files (defaults to config)
            default_ttl: Default TTL in seconds
        """
        if cache_dir is None:
            cache_dir = settings.cache.cache_dir

        cache_dir.mkdir(parents=True, exist_ok=True)

        self._cache = FanoutCache(
            directory=str(cache_dir),
            shards=4,  # 4 SQLite files for concurrency
            timeout=1.0,
        )
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get value from disk cache."""
        try:
            return self._cache.get(key)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in disk cache with TTL."""
        if ttl is None:
            ttl = self._default_ttl

        try:
            self._cache.set(key, value, expire=ttl)
        except Exception:
            pass  # Cache failures are non-critical

    def delete(self, key: str) -> bool:
        """Delete key from disk cache."""
        try:
            return self._cache.delete(key)
        except Exception:
            return False

    def clear(self) -> None:
        """Clear all cached items."""
        try:
            self._cache.clear()
        except Exception:
            pass

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        try:
            return CacheStats(
                size=len(self._cache),
                total_items=sum(1 for _ in self._cache.iterkeys()),
            )
        except Exception:
            return CacheStats(size=0, total_items=0)


class HybridCache(Cache):
    """Hybrid cache with memory first layer and disk persistence.

    Fast access from memory, durable storage on disk.
    Memory serves as LRU cache, disk as persistent backend.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        memory_size_mb: int = 50,
        default_ttl: int = 3600,
    ):
        """Initialize hybrid cache.

        Args:
            cache_dir: Directory for disk cache
            memory_size_mb: Size of memory cache layer
            default_ttl: Default TTL in seconds
        """
        self._memory = MemoryCache(memory_size_mb, default_ttl)
        self._disk = DiskCache(cache_dir, default_ttl)

    def get(self, key: str) -> Optional[Any]:
        """Get value from memory first, then disk."""
        # Try memory first
        value = self._memory.get(key)
        if value is not None:
            return value

        # Try disk
        value = self._disk.get(key)
        if value is not None:
            # Promote to memory
            self._memory.set(key, value)
            return value

        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in both memory and disk."""
        self._memory.set(key, value, ttl)
        self._disk.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        """Delete from both memory and disk."""
        memory_deleted = self._memory.delete(key)
        disk_deleted = self._disk.delete(key)
        return memory_deleted or disk_deleted

    def clear(self) -> None:
        """Clear both memory and disk."""
        self._memory.clear()
        self._disk.clear()

    def get_stats(self) -> CacheStats:
        """Get combined cache statistics."""
        memory_stats = self._memory.get_stats()
        disk_stats = self._disk.get_stats()
        return CacheStats(
            size=memory_stats.size + disk_stats.size,
            total_items=memory_stats.total_items + disk_stats.total_items,
        )


class _CacheItem:
    """Individual cached item with TTL and access tracking."""

    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl
        self.access_count = 0
        self.last_accessed = time.time()

    def is_expired(self) -> bool:
        """Check if item has expired."""
        return time.time() > (self.created_at + self.ttl)

    def access(self) -> Any:
        """Access the item (updates tracking)."""
        self.access_count += 1
        self.last_accessed = time.time()
        return self.value

    def size_bytes(self) -> int:
        """Estimate size of cached item."""
        try:
            import json

            return len(json.dumps(self.value, default=str).encode("utf-8"))
        except Exception:
            import sys

            return sys.getsizeof(self.value)


def create_cache(cache_type: Union[CacheType, str]) -> Cache:
    """Create cache instance based on configuration.

    Args:
        cache_type: Type of cache to create

    Returns:
        Cache instance of appropriate type
    """
    if isinstance(cache_type, str):
        cache_type = CacheType(cache_type.lower())

    if cache_type == CacheType.MEMORY:
        return MemoryCache(
            max_size_mb=settings.performance.smart_cache_max_size_mb,
            default_ttl=settings.performance.search_cache_ttl,
        )
    elif cache_type == CacheType.DISK:
        return DiskCache(default_ttl=settings.performance.default_ttl_hours * 3600)
    elif cache_type == CacheType.HYBRID:
        return HybridCache(
            memory_size_mb=settings.performance.smart_cache_max_size_mb // 2,
            default_ttl=settings.performance.default_ttl_hours * 3600,
        )
    else:
        raise ValueError(f"Unsupported cache type: {cache_type}")


# Global cache instance based on configuration
_global_cache: Optional[Cache] = None
_cache_lock = threading.Lock()


def get_cache() -> Cache:
    """Get configured global cache instance."""
    global _global_cache
    if _global_cache is None:
        with _cache_lock:
            if _global_cache is None:
                _global_cache = create_cache(settings.performance.cache_type)
    return _global_cache


def clear_cache_all() -> None:
    """Clear the global cache."""
    cache = get_cache()
    cache.clear()


def clear_cache_by_prefix(prefix: str) -> None:
    """Clear cache entries by prefix (limited implementation).

    Note: Full implementation depends on cache backend type.
    This is a basic implementation that works for most common cases.
    """
    cache = get_cache()

    # Basic approach - iterate through all keys if possible
    try:
        # Check if cache has iterkeys method (disk cache)
        if hasattr(cache, "iterkeys"):
            keys_to_delete = []
            for key in cache.iterkeys():
                if key.startswith(prefix):
                    keys_to_delete.append(key)
            for key in keys_to_delete:
                cache.delete(key)
        elif hasattr(cache, "keys"):
            # Memory cache or similar
            all_keys = list(cache.keys())
            keys_to_delete = [key for key in all_keys if key.startswith(prefix)]
            for key in keys_to_delete:
                cache.delete(key)
    except Exception:
        # Fallback: do nothing if cache operations fail
        pass

    try:
        # Hybrid cache - clear disk component
        if hasattr(cache, "_disk") and hasattr(cache._disk, "_cache"):
            keys_to_delete = []
            for key in cache._disk._cache.iterkeys():
                if key.startswith(prefix):
                    keys_to_delete.append(key)
            for key in keys_to_delete:
                cache._disk._cache.delete(key)
            # Also clear from memory component
            if hasattr(cache, "_memory") and hasattr(cache._memory, "_cache"):
                memory_keys_to_delete = [
                    key for key in cache._memory._cache.keys() if key.startswith(prefix)
                ]
                for key in memory_keys_to_delete:
                    cache._memory.delete(key)
            return
    except (AttributeError, TypeError):
        pass

    try:
        # Memory cache approach
        if hasattr(cache, "_cache"):
            keys_to_delete = [key for key in cache._cache.keys() if key.startswith(prefix)]
            for key in keys_to_delete:
                cache.delete(key)
    except (AttributeError, TypeError):
        pass
