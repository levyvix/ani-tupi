"""Offline sync queue management for AniList progress updates.

Handles queuing failed syncs for retry when network is unavailable.
Persists queue to JSON and retries on app startup.

Architecture:
- add_to_queue(): Classifies errors and queues only retryable ones
- retry_offline_syncs(): Retries queued entries, removes successful ones
- _classify_error(): Determines if error is retryable (network) or not (auth)
"""

import logging
from pathlib import Path

from models.config import settings
from models.models import OfflineSyncQueue, OfflineSyncQueueEntry
from services.anime.playback_service import sync_progress_to_anilist

logger = logging.getLogger(__name__)


def _get_queue_path() -> Path:
    """Get path to offline sync queue JSON file."""
    queue_dir = Path.home() / ".local" / "state" / "ani-tupi"
    queue_dir.mkdir(parents=True, exist_ok=True)
    return queue_dir / "offline_sync_queue.json"


def _load_queue() -> OfflineSyncQueue:
    """Load offline sync queue from disk.

    Returns:
        OfflineSyncQueue (empty if file not found)
    """
    queue_path = _get_queue_path()
    if not queue_path.exists():
        return OfflineSyncQueue()

    try:
        import json

        with open(queue_path, "r") as f:
            data = json.load(f)
            return OfflineSyncQueue.model_validate(data)
    except Exception as e:
        logger.error(f"Failed to load offline sync queue: {e}")
        return OfflineSyncQueue()


def _save_queue(queue: OfflineSyncQueue) -> None:
    """Save offline sync queue to disk.

    Args:
        queue: Queue to save
    """
    queue_path = _get_queue_path()
    try:
        import json

        queue_path.parent.mkdir(parents=True, exist_ok=True)
        with open(queue_path, "w") as f:
            json.dump(queue.model_dump(mode="json"), f, indent=2, default=str)
        logger.debug(f"Saved offline sync queue: {queue_path}")
    except Exception as e:
        logger.error(f"Failed to save offline sync queue: {e}")


def _classify_error(exception: Exception | None) -> bool:
    """Classify whether an error is retryable.

    Retryable errors (network-related):
    - ConnectionError, TimeoutError, socket.timeout
    - RequestException (requests library)
    - 5xx HTTP status codes
    - Rate limit errors (429)

    Not retryable (auth/client errors):
    - 401 Unauthorized, 403 Forbidden
    - Token expired
    - Invalid AniList ID

    Args:
        exception: Exception to classify (None if no exception)

    Returns:
        True if retryable (network error), False if not retryable
    """
    if exception is None:
        return True  # None error = successful, not queued

    error_msg = str(exception).lower()

    # Not retryable: auth errors
    if any(x in error_msg for x in ["401", "403", "unauthorized", "forbidden"]):
        return False

    if any(x in error_msg for x in ["expired", "invalid token", "token"]):
        return False

    if "invalid anilist" in error_msg or "not found" in error_msg:
        return False

    # Retryable: network errors
    if any(
        x in error_msg
        for x in [
            "connection",
            "timeout",
            "network",
            "errno",
            "socket",
            "refused",
            "reset",
            "500",
            "502",
            "503",
            "504",
            "429",
        ]
    ):
        return True

    # Default to retryable if unsure (network is more likely than auth)
    return True


def add_to_queue(
    anime_title: str,
    episode_number: int,
    anilist_id: int,
    error: Exception | None = None,
    is_local: bool = False,
    file_path: Path | None = None,
) -> None:
    """Add a failed sync to offline queue for retry.

    Only queues retryable errors (network-related). Non-retryable errors
    (auth, invalid ID) are logged but not queued.

    Args:
        anime_title: Anime title (for reference)
        episode_number: Episode watched (1-indexed)
        anilist_id: AniList media ID
        error: Exception that caused the failure (None if offline)
        is_local: Whether episode came from local library
        file_path: Path to local episode file (for cleanup after sync)
    """
    # Check if error is retryable
    if not _classify_error(error):
        logger.warning(
            f"Not queuing non-retryable error for {anime_title} ep {episode_number}: {error}"
        )
        return

    # Load current queue
    queue = _load_queue()

    # Check if entry already exists
    existing_idx = None
    for i, entry in enumerate(queue.entries):
        if entry.anilist_id == anilist_id and entry.episode_number == episode_number:
            existing_idx = i
            break

    # Create new entry or update existing
    entry = OfflineSyncQueueEntry(
        anime_title=anime_title,
        episode_number=episode_number,
        anilist_id=anilist_id,
        last_error=str(error) if error else None,
        is_local=is_local,
        file_path=str(file_path) if file_path else None,
    )

    if existing_idx is not None:
        queue.entries[existing_idx] = entry
        logger.debug(f"Updated queue entry for {anime_title} ep {episode_number}")
    else:
        queue.entries.append(entry)
        logger.info(
            f"Queued sync for {anime_title} ep {episode_number} ({len(queue.entries)} total)"
        )

    # Save updated queue
    _save_queue(queue)


def retry_offline_syncs() -> dict[str, int]:
    """Retry all queued offline syncs.

    Retries each entry:
    - If successful: removes from queue, deletes local file if configured
    - If failed: increments retry_count, updates last_error
    - If max_retry_count exceeded: removes from queue

    Returns:
        Dictionary with {"successful": N, "failed": M} counts
    """
    queue = _load_queue()
    if not queue.entries:
        return {"successful": 0, "failed": 0}

    successful_count = 0
    failed_count = 0

    # Process each entry
    entries_to_keep = []

    for entry in queue.entries:
        # Check if max retries exceeded
        if entry.retry_count >= settings.offline_sync.max_retry_count:
            logger.warning(
                f"Giving up on {entry.anime_title} ep {entry.episode_number} "
                f"after {entry.retry_count} retries"
            )
            failed_count += 1
            continue

        # Try to sync
        logger.debug(f"Retrying sync for {entry.anime_title} ep {entry.episode_number}")
        try:
            success = sync_progress_to_anilist(
                entry.anilist_id,
                entry.episode_number,
                0,  # num_episodes: 0 prevents false completion triggers
                entry.anime_title,
            )

            if success:
                logger.info(
                    f"✅ Offline sync successful for {entry.anime_title} ep {entry.episode_number}"
                )
                successful_count += 1

                # Delete local file if sync successful and file cleanup enabled
                if entry.is_local and settings.offline_sync.enable_file_cleanup:
                    try:
                        from services.local_anime_service import LocalAnimeService

                        service = LocalAnimeService()
                        deleted = service.delete_episode(entry.anime_title, entry.episode_number)
                        if deleted:
                            logger.info(
                                f"🗑️  Deleted {entry.anime_title} ep {entry.episode_number} after sync"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to delete {entry.anime_title} ep {entry.episode_number}: {e}"
                        )

                # Don't keep this entry (sync successful)
                continue

            else:
                # Sync failed, increment retry counter and keep entry
                entry.retry_count += 1
                entry.last_error = (
                    "Sync failed (check logs for details). "
                    "Common issues: wrong AniList ID, anime already COMPLETED, "
                    "episode number exceeds total"
                )
                failed_count += 1
                entries_to_keep.append(entry)
                logger.warning(
                    f"❌ Offline sync failed for {entry.anime_title} ep {entry.episode_number} "
                    f"anime_id={entry.anilist_id} "
                    f"(retry {entry.retry_count}/{settings.offline_sync.max_retry_count}). "
                    f"Check logs above for error details."
                )

        except Exception as e:
            # Exception during sync, increment retry counter
            entry.retry_count += 1
            entry.last_error = str(e)
            failed_count += 1
            entries_to_keep.append(entry)
            logger.error(
                f"❌ Exception during offline sync for {entry.anime_title} ep {entry.episode_number}: {e}"
            )

    # Update queue with remaining entries
    queue.entries = entries_to_keep

    if entries_to_keep:
        _save_queue(queue)
        logger.info(f"Offline sync queue has {len(entries_to_keep)} remaining entries")
    else:
        # Queue is empty, delete file
        try:
            _get_queue_path().unlink()
            logger.debug("Offline sync queue is empty, deleted file")
        except Exception:
            pass

    return {"successful": successful_count, "failed": failed_count}
