"""AniSkip API integration for fetching anime intro/outro skip timestamps.

Provides skip times from the community-maintained AniSkip API (api.aniskip.com).
Skip times are identified by MyAnimeList (MAL) ID and episode number.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import httpx

from models.models import SkipTimes
from services.jikan_client import jikan_client

logger = logging.getLogger(__name__)


class AniSkipService:
    """Client for AniSkip API with in-memory session caching.

    Fetches skip timestamps for anime intros (OP) and outros (ED) from api.aniskip.com.
    Results are cached in-memory per session to avoid repeated API calls.
    """

    def __init__(self, base_url: str = "https://api.aniskip.com"):
        """Initialize AniSkip service.

        Args:
            base_url: AniSkip API base URL (default: https://api.aniskip.com)
        """
        self.base_url = base_url.rstrip("/")
        self._cache: dict[str, SkipTimes] = {}
        self._mal_id_cache: dict[str, int | None] = {}  # Cache for title -> MAL ID lookups
        self._timeout = 10.0  # seconds

    def get_skip_times(self, mal_id: int, episode: int) -> Optional[SkipTimes]:
        """Fetch skip timestamps for anime episode.

        Args:
            mal_id: MyAnimeList anime ID
            episode: Episode number (1-indexed)

        Returns:
            SkipTimes object with op/ed timestamps, or None if:
            - No skip data available for this anime/episode
            - API request fails
            - Network error occurs

        API Response Format:
            {
                "found": true,
                "results": [
                    {
                        "interval": {"startTime": 90.0, "endTime": 180.0},
                        "skipType": "op",
                        "episodeLength": 1420.0
                    },
                    {
                        "interval": {"startTime": 1320.0, "endTime": 1420.0},
                        "skipType": "ed",
                        "episodeLength": 1420.0
                    }
                ],
                "statusCode": 200
            }
        """
        cache_key = f"{mal_id}:{episode}"

        # Check cache first
        if cache_key in self._cache:
            logger.debug(f"AniSkip cache hit: {cache_key}")
            return self._cache[cache_key]

        # Fetch from API
        url = f"{self.base_url}/v2/skip-times/{mal_id}/{episode}"
        params = {"types[]": ["op", "ed"], "episodeLength": 0}

        try:
            logger.debug(f"Fetching skip times: MAL ID {mal_id}, Episode {episode}")
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            # Parse response
            if not data.get("found") or not data.get("results"):
                logger.debug(f"No skip times found for MAL ID {mal_id}, Episode {episode}")
                return None

            # Extract skip times from results
            skip_times = self._parse_skip_times(data["results"])
            if skip_times:
                self._cache[cache_key] = skip_times
                logger.info(
                    f"AniSkip: Fetched skip times for MAL ID {mal_id}, Episode {episode} "
                    f"(OP: {skip_times.op_start}-{skip_times.op_end}, "
                    f"ED: {skip_times.ed_start}-{skip_times.ed_end})"
                )
            return skip_times

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"No skip times found for MAL ID {mal_id}, Episode {episode}")
            else:
                logger.warning(
                    f"AniSkip API error: {e.response.status_code} for MAL ID {mal_id}, "
                    f"Episode {episode}"
                )
            return None
        except httpx.TimeoutException:
            logger.warning(f"AniSkip API timeout for MAL ID {mal_id}, Episode {episode}")
            return None
        except Exception as e:
            logger.warning(
                f"AniSkip API request failed for MAL ID {mal_id}, Episode {episode}: {e}"
            )
            return None

    def get_skip_available_batch(
        self, mal_id: int, max_episode: int, episodes_to_check: list[int] | None = None
    ) -> dict[int, bool]:
        """Check which episodes have skip times available.

        Performs parallel requests to AniSkip API for specified episodes.
        Results are cached, so subsequent calls are fast.

        Args:
            mal_id: MyAnimeList anime ID
            max_episode: Maximum episode number (for validation, not used if episodes_to_check provided)
            episodes_to_check: List of specific episode numbers to check (1-indexed).
                              If None, checks all episodes from 1 to max_episode.
                              Use this to limit checks to just next/current/previous for performance.

        Returns:
            Dict mapping episode number -> True (has skip) or False (no skip)
            Example: {1: True, 2: False, 3: True, ...}

        Note:
            - Uses ThreadPoolExecutor for parallel requests (faster)
            - Gracefully handles API failures (treats as "no skip times")
            - Results are cached in memory (subsequent calls use cache)
            - Max workers: 4 (respectful to API)
            - Passing episodes_to_check=[] returns empty dict instantly (no API calls)
        """
        results = {}

        # Determine which episodes to check
        if episodes_to_check is not None:
            episodes = episodes_to_check
        else:
            episodes = list(range(1, max_episode + 1))

        # If no episodes to check, return empty dict
        if not episodes:
            return results

        # Use ThreadPoolExecutor for parallel requests
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all requests
            futures = {executor.submit(self.get_skip_times, mal_id, ep): ep for ep in episodes}

            # Collect results as they complete
            for future in as_completed(futures):
                ep = futures[future]
                try:
                    skip_times = future.result()
                    results[ep] = skip_times is not None
                except Exception as e:
                    logger.warning(f"Error checking skip times for episode {ep}: {e}")
                    results[ep] = False

        return results

    def _parse_skip_times(self, results: list[dict]) -> Optional[SkipTimes]:
        """Parse skip times from API results.

        Args:
            results: List of skip time entries from API

        Returns:
            SkipTimes object with extracted timestamps, or None if no valid data
        """
        op_start, op_end = None, None
        ed_start, ed_end = None, None

        for result in results:
            skip_type = result.get("skipType")
            interval = result.get("interval", {})
            start_time = interval.get("startTime")
            end_time = interval.get("endTime")

            if skip_type == "op" and start_time is not None and end_time is not None:
                op_start = float(start_time)
                op_end = float(end_time)
            elif skip_type == "ed" and start_time is not None and end_time is not None:
                ed_start = float(start_time)
                ed_end = float(end_time)

        # Return SkipTimes only if at least one skip time found
        if op_start is not None or ed_start is not None:
            return SkipTimes(
                op_start=op_start,
                op_end=op_end,
                ed_start=ed_start,
                ed_end=ed_end,
            )

        return None

    def search_mal_id(self, anime_title: str) -> Optional[int]:
        """Search for MAL ID by anime title using Jikan API.

        Args:
            anime_title: Anime title to search for

        Returns:
            MAL ID if found, None otherwise

        Uses Jikan API (unofficial MAL API) to search for anime by title.
        Results are cached to avoid repeated API calls.
        """
        # Check cache first
        cache_key = anime_title.lower().strip()
        if cache_key in self._mal_id_cache:
            logger.debug(f"MAL ID cache hit: {cache_key}")
            return self._mal_id_cache[cache_key]

        try:
            logger.debug(f"Searching MAL ID for: {anime_title}")
            results = jikan_client.search_anime(anime_title, limit=1)
            if results:
                mal_id = results[0].mal_id
                if mal_id:
                    self._mal_id_cache[cache_key] = mal_id
                    logger.info(f"MAL ID found for '{anime_title}': {mal_id}")
                    return mal_id

            # No results found
            logger.debug(f"No MAL ID found for '{anime_title}'")
            self._mal_id_cache[cache_key] = None
            return None

        except Exception as e:
            logger.warning(f"Jikan API request failed for '{anime_title}': {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the in-memory skip times and MAL ID caches."""
        self._cache.clear()
        self._mal_id_cache.clear()
        logger.debug("AniSkip caches cleared")
