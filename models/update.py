"""Update-check and video playback data models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VideoUrl(BaseModel):
    """Video playback URL with optional headers.

    Attributes:
        url: Video URL (m3u8 HLS or direct video file)
        headers: Optional HTTP headers for playback (User-Agent, Referer, etc.)
    """

    url: str = Field(..., min_length=1, description="Video URL (m3u8 or mp4/mkv/etc)")
    headers: dict[str, str] | None = Field(None, description="HTTP headers for playback")

    @field_validator("url")
    @classmethod
    def validate_video_url(cls, v: str) -> str:
        """Validate video URL format.

        Accepts:
        - m3u8 (HLS streaming)
        - Direct video files (mp4, mkv, avi, webm)
        - Dynamic URLs (logged as warning but allowed)
        """
        import warnings

        valid_extensions = (".m3u8", ".mp4", ".mkv", ".avi", ".webm")
        if not any(v.endswith(ext) for ext in valid_extensions):
            # Some sites have dynamic URLs without file extensions
            warnings.warn(f"Video URL may be invalid: {v}", stacklevel=2)
        return v


class UpdateCheckState(BaseModel):
    """Persisted update-check state for cooldown behavior."""

    last_checked_at: datetime | None = Field(
        default=None,
        description="Timestamp of the last successful remote version check",
    )
    last_latest_version: str | None = Field(
        default=None,
        description="Latest known upstream version from the last successful check",
    )
    last_update_available: bool = Field(
        default=False,
        description="Whether the last successful check reported an available update",
    )


class UpdateCheckResult(BaseModel):
    """Immutable startup update-check result."""

    model_config = ConfigDict(frozen=True)

    local_version: str = Field(..., min_length=1, description="Installed local version")
    latest_version: str | None = Field(default=None, description="Latest upstream version")
    update_available: bool = Field(
        default=False,
        description="True when a newer upstream version is available",
    )
    message: str | None = Field(
        default=None,
        description="User-facing update message when an update is available",
    )
