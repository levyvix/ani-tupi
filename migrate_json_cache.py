"""One-time migration from JSON cache to DiskCache (SQLite).

Automatically runs on first startup with diskcache.
Preserves existing cache data and creates backup of old file.
"""

import json

from config import settings


def migrate_old_json_cache() -> None:
    """Migrate scraper_cache.json to DiskCache SQLite backend.

    Safe to run multiple times - only migrates if old cache exists and new doesn't.
    """
    old_cache_file = settings.cache.cache_file
    cache_dir = settings.cache.cache_dir

    # Check if migration is needed
    if not old_cache_file.exists():
        return  # No old cache to migrate

    if cache_dir.exists() and list(cache_dir.glob("*")):
        return  # New cache already exists, skip migration

    print("🔄 Migrando cache JSON antigo para SQLite...")

    try:
        # Read old JSON cache
        with old_cache_file.open() as f:
            old_data = json.load(f)

        # Migrate to new cache system
        from cache_manager import get_cache
        from anilist_discovery import auto_discover_anilist_id

        cache = get_cache()
        migrated = 0

        for anime_title, data in old_data.items():
            episode_urls = data.get("episode_urls", [])
            if not episode_urls:
                continue

            # Try to discover AniList ID for better caching
            anilist_id = auto_discover_anilist_id(anime_title)

            if anilist_id:
                # Store with AniList ID as cache key
                cache_key = f"episodes:{anilist_id}"
            else:
                # Fallback to title if AniList ID not found
                cache_key = f"episodes:{anime_title}"

            # Store in new cache system
            cache.set(cache_key, episode_urls, expire=settings.cache.duration_hours * 3600)
            migrated += 1

        # Backup old cache file (don't delete)
        backup_file = old_cache_file.with_suffix(".json.backup")
        old_cache_file.rename(backup_file)

        if migrated > 0:
            print(f"✅ {migrated} animes migrados! Backup: {backup_file}")
        else:
            print("ℹ️  Cache antigo estava vazio, nada para migrar")

    except Exception as e:
        print(f"⚠️  Erro ao migrar cache: {e}")
        print("   Cache continuará funcionando sem dados antigos")
