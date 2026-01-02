"""Plugin/scraper system for anime sources.

Plugin architecture for multi-source anime scraping:
- loader: Plugin discovery and loading system
- plugins: Actual scraper implementations
"""

from scrapers import loader

__all__ = ["loader"]
