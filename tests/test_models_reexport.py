"""Verify models.models re-export hub preserves backward-compatible imports.

The model definitions were split into cohesive domain submodules. models.models
must re-export every previously-importable name, and each name must be the SAME
class object as in its new submodule (no duplication).
"""

import models.anilist as anilist
import models.anime as anime
import models.cache as cache
import models.download as download
import models.manga as manga
import models.models as hub
import models.update as update


def test_representative_names_import_from_hub():
    from models.models import (  # noqa: F401
        AniListAnime,
        AnimeMetadata,
        DownloadResult,
        EpisodeData,
        MangaMetadata,
        ScraperCacheData,
        SearchResults,
        VideoUrl,
    )


def test_hub_classes_are_same_objects_as_submodules():
    assert hub.AnimeMetadata is anime.AnimeMetadata
    assert hub.EpisodeData is anime.EpisodeData
    assert hub.SearchResults is anime.SearchResults
    assert hub.MangaMetadata is manga.MangaMetadata
    assert hub.ChapterData is manga.ChapterData
    assert hub.AniListAnime is anilist.AniListAnime
    assert hub.AniListManga is anilist.AniListManga
    assert hub.ScraperCacheData is cache.ScraperCacheData
    assert hub.DownloadResult is download.DownloadResult
    assert hub.VideoUrl is update.VideoUrl


def test_all_exports_are_resolvable():
    for name in hub.__all__:
        assert hasattr(hub, name), f"{name} listed in __all__ but not present"
