"""Airing Episodes Service - fetches and filters anime with airing episodes.

This service supports the "Novos Episódios" (New Episodes) tab feature by:
- Fetching the user's watching list from AniList
- Filtering for anime with airing episode data (nextAiringEpisode not null)
- Filtering for only "awaiting" episodes (scheduled within 90 days, not yet aired)
- Calculating episode gaps (how many episodes behind)
- Sorting by urgency (most episodes behind first)
- Returning structured AiringAnimeEntry objects for display
"""

import logging
import time
from datetime import datetime, timezone

from models.config import settings
from models.models import AiringAnimeEntry, AniListTitle
from services.anilist_service import anilist_client


logger = logging.getLogger(__name__)

# Time windows for episode status determination
NINETY_DAYS_SECONDS = 90 * 24 * 60 * 60  # 90 days in seconds


class AiringEpisodesService:
    """Service for fetching and managing airing episodes from user's watching list."""

    def __init__(self):
        """Initialize service with AniList client."""
        self.client = anilist_client

    @staticmethod
    def _parse_end_date(end_date: dict | None) -> datetime | None:
        """Parse AniList endDate object to datetime using conservative fallback.

        Args:
            end_date: Dict with year, month, day keys (any may be None)

        Returns:
            datetime in UTC or None if end_date is None or year is missing
        """
        if not end_date:
            return None

        year = end_date.get("year")
        if not year:
            return None

        month = end_date.get("month") or 1
        day = end_date.get("day") or 1

        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _is_within_grace_period(end_date_obj: dict | None) -> bool:
        """Check if an anime's end date is within the 60-day grace period.

        Args:
            end_date_obj: AniList endDate dict with year, month, day

        Returns:
            True if the anime ended less than GRACE_PERIOD_DAYS days ago
        """
        end_dt = AiringEpisodesService._parse_end_date(end_date_obj)
        if end_dt is None:
            return False

        now = datetime.now(tz=timezone.utc)
        delta = now - end_dt
        return delta.days < settings.airing.grace_period_days

    @staticmethod
    def _is_awaiting_episode(airing_at: int | None) -> bool:
        """Check if an episode is awaiting (scheduled within 90 days, not yet aired).

        Args:
            airing_at: Unix timestamp of episode air time (or None if unknown)

        Returns:
            True if episode is awaiting (not yet aired, within 90 days),
            False if already aired or too far in future
        """
        if airing_at is None:
            return False

        now = int(time.time())

        # Episode must be in the future (not yet aired)
        if airing_at <= now:
            return False

        # Episode must be within 90 days (strictly less than)
        if airing_at >= now + NINETY_DAYS_SECONDS:
            return False

        return True

    def get_watching_with_airing_episodes(self) -> list[AiringAnimeEntry]:
        """Get user's watching anime with new AWAITING episodes, sorted by urgency.

        "Awaiting" means the next episode is scheduled to air within 90 days
        and hasn't aired yet. Excludes:
        - Anime already aired/completed (nextAiringEpisode.airingAt in past)
        - Anime on hiatus (nextAiringEpisode.airingAt more than 90 days away)
        - Anime without scheduled next episodes

        This method:
        1. Fetches user's CURRENT watching list from AniList
        2. Filters anime to only those with nextAiringEpisode data (actively airing)
        3. Filters anime to only those with awaiting episodes (within 90 days, not aired)
        4. Calculates episodes_behind (nextEpisode - userProgress)
        5. Sorts by episodes_behind descending (most urgent first)
        6. Returns structured AiringAnimeEntry objects

        Returns:
            List of AiringAnimeEntry objects sorted by urgency (most behind first),
            or empty list if not authenticated, no airing anime, or no awaiting episodes found
        """
        # Fetch raw API entries
        entries = self.client.get_airing_episodes_for_watching()

        if not entries:
            return []

        # Filter and transform entries
        airing_anime: list[AiringAnimeEntry] = []

        for entry in entries:
            try:
                # Extract fields from API response
                progress = entry.get("progress", 0)
                media = entry.get("media")

                if not media:
                    continue

                # Extract title (shared by both airing and grace period paths)
                title_obj = media.get("title", {})
                if isinstance(title_obj, dict):
                    title = (
                        title_obj.get("english")
                        or title_obj.get("romaji")
                        or title_obj.get("native")
                        or "Unknown"
                    )
                elif isinstance(title_obj, AniListTitle):
                    title = title_obj.english or title_obj.romaji or title_obj.native or "Unknown"
                else:
                    title = str(title_obj)

                anilist_id = media.get("id", 0)
                average_score = media.get("averageScore")

                next_airing = media.get("nextAiringEpisode")

                if next_airing:
                    # Active airing: filter for only "awaiting" episodes
                    airing_at = next_airing.get("airingAt")
                    if not self._is_awaiting_episode(airing_at):
                        logger.debug(
                            f"Skipping anime {media.get('id')}: episode not awaiting "
                            f"(airing_at={airing_at})"
                        )
                        continue

                    next_episode_number = next_airing.get("episode", 0)
                    if next_episode_number <= 0:
                        continue

                    # episodes behind = (last aired episode) - (user progress)
                    episodes_behind = max(0, (next_episode_number - 1) - progress)

                    entry_obj = AiringAnimeEntry(
                        anilist_id=anilist_id,
                        title=title,
                        progress=progress,
                        next_episode_number=next_episode_number,
                        episodes_behind=episodes_behind,
                        airing_at=airing_at,
                        average_score=average_score,
                    )
                else:
                    # No next airing episode — check grace period for recently finished anime
                    media_status = media.get("status")
                    total_episodes = media.get("episodes")
                    end_date_obj = media.get("endDate")

                    if media_status != "FINISHED":
                        continue
                    if not total_episodes:
                        continue
                    if not self._is_within_grace_period(end_date_obj):
                        logger.debug(
                            f"Skipping finished anime {media.get('id')}: outside grace period"
                        )
                        continue
                    if progress >= total_episodes:
                        continue

                    episodes_behind = total_episodes - progress

                    entry_obj = AiringAnimeEntry(
                        anilist_id=anilist_id,
                        title=title,
                        progress=progress,
                        next_episode_number=total_episodes,
                        episodes_behind=episodes_behind,
                        airing_at=None,
                        average_score=average_score,
                    )

                airing_anime.append(entry_obj)

            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Error processing airing episode entry: {e}")
                continue

        # Sort by episodes_behind descending (most urgent first)
        airing_anime.sort(key=lambda x: x.episodes_behind, reverse=True)

        return airing_anime
