"""AniList and Jikan/MyAnimeList API data models."""

from pydantic import BaseModel, ConfigDict, Field


class AniListSearchResult(BaseModel):
    """AniList search result with score."""

    anilist_id: int
    score: int
    title: str


# AniList API Models
class AniListTitle(BaseModel):
    """AniList title object with multiple language variants."""

    romaji: str | None = Field(None, description="Romaji title")
    english: str | None = Field(None, description="English title")
    native: str | None = Field(None, description="Native title")


class AniListAnimeStatistics(BaseModel):
    """AniList anime statistics."""

    count: int = Field(ge=0, description="Total anime count")
    episodesWatched: int = Field(ge=0, description="Total episodes watched")
    minutesWatched: int = Field(ge=0, description="Total minutes watched")


class AniListStatistics(BaseModel):
    """AniList user statistics."""

    anime: AniListAnimeStatistics | None = Field(None, description="Anime statistics")


class AniListViewerInfo(BaseModel):
    """AniList viewer/user information.

    Attributes:
        id: User ID
        name: Username
        statistics: User statistics
    """

    id: int = Field(..., description="User ID")
    name: str = Field(..., min_length=1, description="Username")
    statistics: AniListStatistics | None = Field(None, description="User statistics")


class AiringAnimeEntry(BaseModel):
    """Anime from watching list with airing episode info.

    Represents an anime that is in the user's watching list and has
    new episodes airing. Used for the "Novos Episódios" (New Episodes) tab.

    Attributes:
        anilist_id: AniList anime ID for routing to playback
        title: Formatted anime title for display
        progress: User's current episode progress
        next_episode_number: Episode number that aired/is airing
        episodes_behind: Gap between next episode and user progress (for sorting)
        airing_at: Unix timestamp of next episode air time (optional)
        average_score: AniList score for context (0-100, optional)
    """

    anilist_id: int = Field(..., description="AniList anime ID")
    title: str = Field(..., min_length=1, description="Formatted anime title")
    progress: int = Field(..., ge=0, description="User's current episode progress")
    next_episode_number: int = Field(..., ge=1, description="Episode number that aired")
    episodes_behind: int = Field(..., ge=0, description="Episodes behind (next_episode - progress)")
    airing_at: int | None = Field(None, description="Unix timestamp of next episode air time")
    average_score: int | None = Field(None, ge=0, le=100, description="AniList average score")


class AniListAnime(BaseModel):
    """AniList anime media object.

    Attributes:
        id: AniList anime ID
        title: Title object with multiple languages
        episodes: Total episodes (None if unknown)
        averageScore: Average score (0-100)
        seasonYear: Year of release
        season: Season (WINTER, SPRING, SUMMER, FALL)
        type: Media type (ANIME, MANGA)
        status: Media status (FINISHED, RELEASING, NOT_YET_RELEASED, CANCELLED, HIATUS)
        startDate: Start date object with year, month, day
    """

    model_config = {"populate_by_name": True}

    id: int = Field(..., description="AniList anime ID")
    title: AniListTitle = Field(..., description="Title object")
    episodes: int | None = Field(None, description="Total episodes")
    averageScore: int | None = Field(None, ge=0, le=100, description="Average score")
    seasonYear: int | None = Field(None, ge=1900, le=2100, description="Release year")
    season: str | None = Field(None, description="Season (WINTER, SPRING, SUMMER, FALL)")
    type: str | None = Field(None, description="Media type")
    status: str | None = Field(
        None,
        description="Media status (FINISHED, RELEASING, NOT_YET_RELEASED, CANCELLED, HIATUS)",
    )
    startDate: dict[str, int | None] | None = Field(
        None, description="Start date with year, month, day"
    )
    nextAiringEpisode: dict[str, int | None] | None = Field(
        None,
        description="Next airing episode info (episode, airingAt); null if not currently airing",
    )


class AnimeMetadataEntry(BaseModel):
    """External anime metadata search result (MyAnimeList-shaped)."""

    model_config = ConfigDict(populate_by_name=True)

    mal_id: int = Field(..., description="MyAnimeList anime ID")
    title: str = Field(..., min_length=1, description="Primary MAL title")
    title_english: str | None = Field(None, alias="title_english", description="English title")
    title_japanese: str | None = Field(None, alias="title_japanese", description="Japanese title")
    titles: list[dict[str, str | None]] = Field(
        default_factory=list,
        description="Additional title variants returned by Jikan",
    )
    synonyms: list[str] = Field(default_factory=list, description="Title synonyms")


class AniListManga(BaseModel):
    """AniList manga media object.

    Attributes:
        id: AniList manga ID
        title: Title object with multiple languages
        chapters: Total chapters (None if unknown)
        volumes: Total volumes (None if unknown)
        averageScore: Average score (0-100)
        startDate: Start date (year, month, day - values can be None)
        endDate: End date (year, month, day - values can be None for ongoing)
        type: Media type (ANIME, MANGA)
    """

    id: int = Field(..., description="AniList manga ID")
    title: AniListTitle = Field(..., description="Title object")
    chapters: int | None = Field(None, description="Total chapters")
    volumes: int | None = Field(None, description="Total volumes")
    averageScore: int | None = Field(None, ge=0, le=100, description="Average score")
    startDate: dict[str, int | None] | None = Field(
        None, description="Start date (year, month, day - values can be None)"
    )
    endDate: dict[str, int | None] | None = Field(
        None, description="End date (year, month, day - values can be None for ongoing)"
    )
    type: str | None = Field(None, description="Media type")


class AniListMediaListEntry(BaseModel):
    """AniList media list entry.

    Attributes:
        id: List entry ID
        status: List status (CURRENT, PLANNING, COMPLETED, etc.)
        progress: Episode progress
        score: User score
        startedAt: Start date
        completedAt: Completion date
        media: Anime media object
    """

    id: int = Field(..., description="List entry ID")
    status: str | None = Field(None, description="List status")
    progress: int | None = Field(None, ge=0, description="Episode progress")
    score: int | None = Field(None, ge=0, le=100, description="User score")
    # AniList devolve FuzzyDate com year/month/day nulos quando a data não foi
    # preenchida, então os valores internos são opcionais.
    startedAt: dict[str, int | None] | None = Field(
        None, description="Start date (year, month, day)"
    )
    completedAt: dict[str, int | None] | None = Field(
        None, description="Completion date (year, month, day)"
    )
    media: AniListAnime | None = Field(None, description="Anime media object")
    createdAt: int | None = Field(None, description="Creation timestamp")


class AniListActivity(BaseModel):
    """AniList activity (list update).

    Attributes:
        id: Activity ID
        status: List status
        progress: Episode progress
        createdAt: Creation timestamp
        media: Anime media object
    """

    id: int = Field(..., description="Activity ID")
    status: str | None = Field(None, description="List status")
    progress: str | int | None = Field(None, description="Episode progress")
    createdAt: int = Field(..., description="Creation timestamp")
    media: AniListAnime | None = Field(None, description="Anime media object")


class AniListRelationNode(BaseModel):
    """AniList relation node (sequel, prequel, etc.).

    Attributes:
        id: AniList ID
        type: Media type (ANIME, MANGA)
        title: Title object
        episodes: Total episodes
        status: Media status (FINISHED, RELEASING, NOT_YET_RELEASED, CANCELLED, HIATUS)
        startDate: Start date object with year, month, day
    """

    id: int = Field(..., description="AniList ID")
    type: str = Field(..., description="Media type")
    title: AniListTitle = Field(..., description="Title object")
    episodes: int | None = Field(None, description="Total episodes")
    status: str | None = Field(
        None,
        description="Media status (FINISHED, RELEASING, NOT_YET_RELEASED, CANCELLED, HIATUS)",
    )
    startDate: dict[str, int | None] | None = Field(
        None, description="Start date with year, month, day"
    )


class AniListRelationEdge(BaseModel):
    """AniList relation edge.

    Attributes:
        relationType: Type of relation (SEQUEL, PREQUEL, etc.)
        node: Related anime node
    """

    relationType: str = Field(..., description="Relation type")
    node: AniListRelationNode = Field(..., description="Related anime")
