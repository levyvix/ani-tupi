"""Identity-aware persistence for downloaded anime and source bindings.

The download database remains the single catalog of completed files.  This
module adds the small amount of coordination needed by manual downloads,
scheduled downloads, and local playback without changing the legacy title
layout or JSON shape required by older callers.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from models.config import get_data_path, settings
from models.download import (
    AiringSourceBinding,
    AiringSourceRecord,
    AnimeDownloadDatabase,
    AnimeDownloadHistory,
    DownloadedEpisode,
)
from utils.logging import get_logger

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses the process lock fallback.
    fcntl = None

logger = get_logger(__name__)

DOWNLOAD_DATABASE_NAME = "anime_downloads.json"
AIRING_SOURCES_NAME = "airing_download_sources.json"
VIDEO_EXTENSIONS = frozenset({".mkv", ".mp4", ".avi", ".webm"})
MIN_VALID_FILE_BYTES = 1024 * 1024
_thread_locks: dict[Path, threading.RLock] = {}
_thread_locks_guard = threading.Lock()
_lock_depths = threading.local()


def _thread_lock_depths() -> dict[Path, int]:
    """Per-thread reentrancy counters keyed by normalized lock path."""
    depths = getattr(_lock_depths, "depths", None)
    if depths is None:
        depths = {}
        _lock_depths.depths = depths
    return depths


@contextmanager
def catalog_lock(path: Path) -> Iterator[None]:
    """Lock a catalog and its destination for the duration of a mutation.

    The lock is reentrant within a thread.  A nested acquisition (for example
    ``download_episodes`` calling ``reconcile_episode`` -> ``register_episode``)
    reuses the ``flock`` already held by the outermost acquisition.  Opening a
    second file description for the same lock always deadlocks, because
    ``flock`` locks are per open file description.
    """
    normalized_path = path.resolve()
    with _thread_locks_guard:
        thread_lock = _thread_locks.setdefault(normalized_path, threading.RLock())
    thread_lock.acquire()
    depths = _thread_lock_depths()
    depth = depths.get(normalized_path, 0)
    lock_file = None
    try:
        if depth == 0:
            lock_path = path.with_name(f".{path.name}.lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = lock_path.open("a+")
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        depths[normalized_path] = depth + 1
        try:
            yield
        finally:
            if depth == 0:
                depths.pop(normalized_path, None)
            else:
                depths[normalized_path] = depth
    finally:
        if depth == 0 and lock_file is not None:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
        thread_lock.release()


def atomic_write_json(path: Path, value: object) -> None:
    """Write JSON durably and replace the destination in one filesystem step."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise


def is_valid_media_file(path: Path, min_size: int = MIN_VALID_FILE_BYTES) -> bool:
    """Return whether *path* is a complete-looking local video file."""
    try:
        return (
            path.is_file()
            and path.suffix.lower() in VIDEO_EXTENSIONS
            and path.stat().st_size >= min_size
        )
    except OSError:
        return False


def stable_anime_directory(
    download_dir: Path, anime_title: str, anilist_id: int | None = None
) -> Path:
    """Return a collision-resistant directory for a new download."""
    if anilist_id is not None:
        return download_dir / f"anilist-{anilist_id}"
    safe_title = Path(anime_title).name
    if not safe_title or safe_title != anime_title:
        raise ValueError("Título de anime inválido")
    return download_dir / safe_title


def history_key(database: AnimeDownloadDatabase, anime_title: str, anilist_id: int | None) -> str:
    """Choose a title key without merging distinct AniList identities."""
    if anilist_id is None or anime_title not in database.anime:
        return anime_title
    existing = database.anime[anime_title]
    if existing.anilist_id == anilist_id:
        return anime_title
    return f"{anime_title} [anilist-{anilist_id}]"


class DownloadCatalog:
    """Read and mutate the existing title-indexed download database safely."""

    def __init__(self, db_path: Path | None = None, download_dir: Path | None = None):
        self.db_path = db_path or (get_data_path() / DOWNLOAD_DATABASE_NAME)
        self.download_dir = download_dir or settings.anime_download.download_directory

    def load_database(self) -> AnimeDownloadDatabase:
        if not self.db_path.exists():
            return AnimeDownloadDatabase()
        try:
            return AnimeDownloadDatabase.model_validate(
                json.loads(self.db_path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Could not load anime download catalog: %s", exc)
            return AnimeDownloadDatabase()

    def save_database(self, database: AnimeDownloadDatabase) -> None:
        """Persist the catalog atomically under the shared lock."""
        with catalog_lock(self.db_path):
            self.save_database_unlocked(database)

    def save_database_unlocked(self, database: AnimeDownloadDatabase) -> None:
        database.last_updated = datetime.now()
        atomic_write_json(self.db_path, database.model_dump(mode="json"))

    def episode_path(self, episode: DownloadedEpisode) -> Path:
        path = episode.file_path
        return path if path.is_absolute() else self.download_dir / path

    def find_episode(
        self,
        anilist_id: int | None,
        episode_number: int,
        *,
        season: int | None = 1,
        variant: str | None = None,
        anime_title: str | None = None,
    ) -> DownloadedEpisode | None:
        """Find one valid episode by identity, never by fuzzy title matching."""
        database = self.load_database()
        matches: list[DownloadedEpisode] = []
        for title, history in database.anime.items():
            if anilist_id is None and anime_title is not None and title != anime_title:
                continue
            for number, episode in history.episodes.items():
                if number != episode_number or episode.status != "success":
                    continue
                record_id = episode.anilist_id or history.anilist_id
                if record_id != anilist_id:
                    continue
                record_season = episode.season or history.season
                if season is not None and record_season != season:
                    continue
                if variant is not None and episode.variant != variant:
                    continue
                if is_valid_media_file(self.episode_path(episode)):
                    matches.append(episode)

        unique_paths = {str(self.episode_path(item).resolve()) for item in matches}
        if len(unique_paths) > 1:
            logger.warning(
                "Ambiguous local episode for AniList ID %s episode %s",
                anilist_id,
                episode_number,
            )
            return None
        return matches[0] if matches else None

    def reconcile_episode(
        self,
        anime_title: str,
        episode_number: int,
        *,
        anilist_id: int | None = None,
        season: int | None = 1,
        variant: str | None = None,
        source: str = "unknown",
        storage_episode_number: int | None = None,
    ) -> DownloadedEpisode | None:
        """Register a valid already-published file left by an interrupted run."""
        existing = self.find_episode(
            anilist_id,
            episode_number,
            season=season,
            variant=variant,
            anime_title=anime_title,
        )
        if existing:
            return existing

        directory = stable_anime_directory(self.download_dir, anime_title, anilist_id)
        storage_episode_number = storage_episode_number or episode_number
        candidates = sorted(
            path
            for path in directory.glob(f"{storage_episode_number}.*")
            if is_valid_media_file(path)
        )
        if len(candidates) != 1:
            return None
        return self.register_episode(
            anime_title,
            episode_number,
            candidates[0],
            source=source,
            anilist_id=anilist_id,
            season=season,
            variant=variant,
        )

    def register_episode(
        self,
        anime_title: str,
        episode_number: int,
        file_path: Path,
        *,
        source: str,
        anilist_id: int | None = None,
        season: int | None = 1,
        variant: str | None = None,
        episode_url: str | None = None,
    ) -> DownloadedEpisode:
        """Merge one completed episode into the existing catalog atomically."""
        if not is_valid_media_file(file_path):
            raise ValueError(f"Arquivo de mídia inválido: {file_path}")
        episode = DownloadedEpisode(
            episode_number=episode_number,
            file_path=file_path,
            file_size_mb=file_path.stat().st_size / (1024 * 1024),
            source=source,
            status="success",
            anilist_id=anilist_id,
            season=season,
            variant=variant,
            episode_url=episode_url,
        )
        with catalog_lock(self.db_path):
            database = self.load_database()
            key = history_key(database, anime_title, anilist_id)
            history = database.anime.get(key)
            if history is None:
                history = AnimeDownloadHistory(
                    anime_title=anime_title,
                    anilist_id=anilist_id,
                    season=season,
                    variant=variant,
                )
            previous_history_id = history.anilist_id
            existing = history.episodes.get(episode_number)
            if existing is not None:
                existing_id = (
                    existing.anilist_id if existing.anilist_id is not None else previous_history_id
                )
                existing_season = existing.season or history.season
                existing_variant = existing.variant
                if (
                    existing.status == "success"
                    and existing_id == anilist_id
                    and existing_season == season
                    and existing_variant == variant
                    and is_valid_media_file(self.episode_path(existing))
                ):
                    return existing
            if anilist_id is not None:
                history.anilist_id = anilist_id
                history.season = season
                history.variant = variant
            history.episodes[episode_number] = episode
            history.total_size_mb = sum(item.file_size_mb for item in history.episodes.values())
            history.last_downloaded = datetime.now()
            database.anime[key] = history
            self.save_database_unlocked(database)
        return episode


def source_bindings_path(path: Path | None = None) -> Path:
    return path or (get_data_path() / AIRING_SOURCES_NAME)


def load_source_records(path: Path | None = None) -> dict[int, AiringSourceRecord]:
    source_path = source_bindings_path(path)
    if not source_path.exists():
        return {}
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        return {int(key): AiringSourceRecord.model_validate(value) for key, value in raw.items()}
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("Could not load airing source bindings: %s", exc)
        return {}


def save_source_records(records: dict[int, AiringSourceRecord], path: Path | None = None) -> None:
    source_path = source_bindings_path(path)
    with catalog_lock(source_path):
        atomic_write_json(
            source_path,
            {str(key): value.model_dump(mode="json") for key, value in records.items()},
        )


def get_source_record(anilist_id: int, path: Path | None = None) -> AiringSourceRecord:
    return load_source_records(path).get(anilist_id, AiringSourceRecord())


def set_configured_source(
    anilist_id: int, binding: AiringSourceBinding, path: Path | None = None
) -> None:
    source_path = source_bindings_path(path)
    with catalog_lock(source_path):
        records = load_source_records(source_path)
        record = records.setdefault(anilist_id, AiringSourceRecord())
        record.binding = binding
        atomic_write_json(
            source_path,
            {str(key): value.model_dump(mode="json") for key, value in records.items()},
        )


def remove_configured_source(anilist_id: int, path: Path | None = None) -> None:
    source_path = source_bindings_path(path)
    with catalog_lock(source_path):
        records = load_source_records(source_path)
        record = records.get(anilist_id)
        if record is None:
            return
        records.pop(anilist_id, None)
        atomic_write_json(
            source_path,
            {str(key): value.model_dump(mode="json") for key, value in records.items()},
        )


def set_last_played_source(
    anilist_id: int, binding: AiringSourceBinding, path: Path | None = None
) -> None:
    source_path = source_bindings_path(path)
    with catalog_lock(source_path):
        records = load_source_records(source_path)
        record = records.setdefault(anilist_id, AiringSourceRecord())
        record.binding = binding
        atomic_write_json(
            source_path,
            {str(key): value.model_dump(mode="json") for key, value in records.items()},
        )


def _merge_confirmed_playback_binding(
    existing: AiringSourceBinding | None,
    confirmed: AiringSourceBinding,
) -> AiringSourceBinding:
    """Keep every saved source context when recording playback evidence."""
    if existing is None:
        return confirmed

    contexts = [existing, *existing.alternatives]
    confirmed_key = (confirmed.source, confirmed.anime_url)
    has_confirmed_context = any(
        (context.source, context.anime_url) == confirmed_key for context in contexts
    )
    alternatives = list(existing.alternatives)
    if not has_confirmed_context:
        alternatives.append(
            {
                "title": confirmed.title,
                "source": confirmed.source,
                "anime_url": confirmed.anime_url,
                "params": confirmed.params,
                "variant": confirmed.variant,
            }
        )
    return existing.model_copy(
        update={
            "title": confirmed.title,
            "episode_number": confirmed.episode_number,
            "recorded_at": confirmed.recorded_at,
            "variant": existing.variant or confirmed.variant,
            "alternatives": alternatives,
        }
    )


def record_confirmed_remote_playback(
    anilist_id: int,
    anime_title: str,
    source: str | None,
    anime_url: str | None,
    *,
    season: int | None = 1,
    variant: str | None = None,
    episode_number: int | None = None,
    params: dict | None = None,
    path: Path | None = None,
) -> bool:
    """Persist a remote source only after playback was confirmed."""
    if not source or source in {"local", "unknown", "pattern", "mixed"} or not anime_url:
        invalidate_last_played_source(anilist_id, path)
        return False
    try:
        binding = AiringSourceBinding(
            title=anime_title,
            source=source,
            anime_url=anime_url,
            params=params or {},
            variant=variant,
            episode_number=episode_number,
            recorded_at=datetime.now(),
        )
    except ValueError:
        invalidate_last_played_source(anilist_id, path)
        return False
    existing = get_source_record(anilist_id, path).binding
    set_last_played_source(
        anilist_id,
        _merge_confirmed_playback_binding(existing, binding),
        path,
    )
    return True


def invalidate_last_played_source(anilist_id: int, path: Path | None = None) -> None:
    source_path = source_bindings_path(path)
    with catalog_lock(source_path):
        records = load_source_records(source_path)
        record = records.get(anilist_id)
        if record is None:
            return
        records.pop(anilist_id, None)
        atomic_write_json(
            source_path,
            {str(key): value.model_dump(mode="json") for key, value in records.items()},
        )


def effective_source(
    anilist_id: int, path: Path | None = None
) -> tuple[AiringSourceBinding | None, str | None]:
    """Return the shared source binding."""
    record = get_source_record(anilist_id, path)
    if record.binding is not None:
        return record.binding, "binding"
    return None, None


# Short aliases are kept for callers that describe this file as a store.
load_airing_source_records = load_source_records
save_airing_source_records = save_source_records


__all__ = [
    "AIRING_SOURCES_NAME",
    "DownloadCatalog",
    "MIN_VALID_FILE_BYTES",
    "VIDEO_EXTENSIONS",
    "atomic_write_json",
    "catalog_lock",
    "effective_source",
    "get_source_record",
    "invalidate_last_played_source",
    "is_valid_media_file",
    "load_airing_source_records",
    "load_source_records",
    "remove_configured_source",
    "save_airing_source_records",
    "save_source_records",
    "record_confirmed_remote_playback",
    "set_configured_source",
    "set_last_played_source",
    "source_bindings_path",
    "stable_anime_directory",
]
