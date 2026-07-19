"""Shared test fixtures package for ani-tupi.

Exposes reusable AniList GraphQL / HTTP response builders so service tests
mock only the external boundary (never internal services), per the project
Testing Strategy.
"""

from tests.fixtures.anilist import (
    FakeAniListTransport,
    anilist_data,
    anilist_errors,
    graphql_response,
    media_entry,
    media_list_collection,
    save_media_list_entry,
    viewer,
)

__all__ = [
    "FakeAniListTransport",
    "anilist_data",
    "anilist_errors",
    "graphql_response",
    "media_entry",
    "media_list_collection",
    "save_media_list_entry",
    "viewer",
]
