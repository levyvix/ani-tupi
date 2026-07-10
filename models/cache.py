"""Cache-related data models."""

from pydantic import BaseModel, Field


class ScraperCacheData(BaseModel):
    """Scraper cache data structure.

    Attributes:
        episode_urls: List of episode URLs
        episode_count: Number of episodes
        timestamp: Cache timestamp (legacy, not used in new system)
    """

    episode_urls: list[str] = Field(..., description="Episode URLs")
    episode_count: int = Field(..., ge=0, description="Number of episodes")
    timestamp: int = Field(default=0, description="Cache timestamp (legacy)")


class CacheStats(BaseModel):
    """Cache statistics.

    Attributes:
        size: Cache size
        total_items: Total number of items in cache
    """

    size: int = Field(..., ge=0, description="Cache size")
    total_items: int = Field(..., ge=0, description="Total items")
