"""Search result set tracking for incremental search iterations."""

import time
from dataclasses import dataclass, field


@dataclass
class SearchResultSet:
    """Represents a single search result set from an incremental search iteration.

    Tracks metadata about search results including word count, query used,
    and source distribution for UI display and navigation.
    """

    word_count: int
    query: str
    results: list[str]
    is_filtered: bool = False  # True if results were filtered from base search, not searched
    used_query: str | None = None  # Normalized query that was actually used for search
    timestamp: float = field(default_factory=time.time)
    source_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.word_count <= 0:
            raise ValueError(f"word_count must be positive, got {self.word_count}")
        # Default used_query to query if not provided
        if not self.used_query:
            self.used_query = self.query
