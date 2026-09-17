"""One-shot, non-interactive monitor for downloads of airing anime.

The monitor deliberately owns orchestration only.  Source selection and the
download implementation are injected (or discovered through the small set of
legacy interfaces used by this repository), which keeps a systemd invocation
independent from the interactive playback flow.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, field_validator

from models.config import get_data_path, settings
from services.anilist.client import anilist_client
from services.repository import rep

__all__ = [
    "AiringDownloadScheduler",
    "AiringDownloadSettings",
    "CycleResult",
]


class AiringDownloadSettings(BaseModel):
    """Runtime limits used by a single monitor cycle.

    ``models.config`` owns the application-wide setting when that model is
    available.  Keeping this small validated adapter here also lets the systemd
    path run against older installations during an upgrade.
    """

    poll_interval_minutes: int = Field(default=30)
    max_attempts: int = Field(default=3, ge=1, le=5)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    log_max_bytes: int = Field(default=512 * 1024, ge=4096)
    log_backup_count: int = Field(default=3, ge=1, le=10)

    @field_validator("poll_interval_minutes")
    @classmethod
    def validate_poll_interval(cls, value: int) -> int:
        valid = {1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}
        if value not in valid:
            raise ValueError(f"poll_interval_minutes must be one of {sorted(valid)}")
        return value

    @classmethod
    def from_application(cls, persisted: dict[str, Any] | None = None) -> "AiringDownloadSettings":
        """Read the new settings model, environment overrides, and persisted values.

        Environment variables intentionally win over persisted values, matching
        the application's settings precedence.  Secret-looking environment
        values are never copied into scheduler state or launcher files.
        """
        values: dict[str, Any] = {}
        app_value = getattr(settings, "airing_downloads", None)
        if app_value is not None:
            for name in cls.model_fields:
                if hasattr(app_value, name):
                    values[name] = getattr(app_value, name)
        values.update(persisted or {})

        env_name = "ANI_TUPI__AIRING_DOWNLOADS__POLL_INTERVAL_MINUTES"
        if os.environ.get(env_name):
            values["poll_interval_minutes"] = int(os.environ[env_name])
        return cls.model_validate(values)


@dataclass
class CycleResult:
    """Observable result of one scheduler invocation."""

    exit_code: int
    status: str
    started_at: str
    finished_at: str | None = None
    active: bool = False
    animes: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def successful(self) -> int:
        return sum(int(item.get("successful", 0)) for item in self.animes)

    @property
    def failed(self) -> int:
        return sum(int(item.get("failed", 0)) for item in self.animes)

    @property
    def skipped(self) -> int:
        return sum(int(item.get("skipped", 0)) for item in self.animes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "active": self.active,
            "successful": self.successful,
            "failed": self.failed,
            "skipped": self.skipped,
            "animes": self.animes,
            "error": self.error,
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]


class _CycleLock:
    """Small advisory process lock with a readable owner marker."""

    def __init__(self, path: Path):
        self.path = path
        self._file = None

    def acquire(self) -> bool:
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._file.close()
            self._file = None
            return False
        self._file.seek(0)
        self._file.truncate()
        self._file.write(json.dumps({"pid": os.getpid(), "started_at": _now()}))
        self._file.flush()
        return True

    def release(self) -> None:
        if self._file is None:
            return
        import fcntl

        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _binding_headers(binding: Any) -> dict[str, str] | None:
    params = _value(binding, "params", {})
    headers = _value(params, "headers", {}) if isinstance(params, dict) else {}
    if not isinstance(headers, dict):
        return None
    return {str(key): str(value) for key, value in headers.items()}


def _binding_referrer(binding: Any) -> str | None:
    params = _value(binding, "params", {})
    if isinstance(params, dict):
        referrer = params.get("referrer") or params.get("referer")
        if isinstance(referrer, str):
            return referrer
    anime_url = _value(binding, "anime_url")
    return anime_url if isinstance(anime_url, str) else None


def _binding_for_source(binding: Any, source: str) -> Any:
    """Return the saved context that belongs to one candidate source."""
    if _value(binding, "source") == source:
        return binding
    for alternative in _value(binding, "alternatives", []) or []:
        if _value(alternative, "source") == source:
            return alternative
    return binding


class AiringDownloadScheduler:
    """Run one bounded monitor cycle and persist its result."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        repository: Any | None = None,
        download_service: Any | None = None,
        binding_resolver: Callable[[int], Any] | Any | None = None,
        processor: Callable[[Any, Any], dict[str, Any]] | None = None,
        settings_obj: AiringDownloadSettings | None = None,
        state_path: Path | None = None,
        lock_path: Path | None = None,
        log_path: Path | None = None,
    ) -> None:
        self.client = client or anilist_client
        self.repository = repository or rep
        self.download_service = download_service
        if binding_resolver is None:
            try:
                from services.anime.airing_sources import AiringSourceStore

                binding_resolver = AiringSourceStore()
            except ImportError:
                pass
        self.binding_resolver = binding_resolver
        self.processor = processor
        self.settings = settings_obj or AiringDownloadSettings.from_application()
        data_path = get_data_path()
        self.state_path = state_path or data_path / "airing_download_state.json"
        self.lock_path = lock_path or data_path / "airing_download.lock"
        self.log_path = log_path or data_path / "airing_download.log"

    def run_once(self) -> CycleResult:
        started_at = _now()
        lock = _CycleLock(self.lock_path)
        if not lock.acquire():
            result = CycleResult(
                exit_code=0,
                status="active",
                started_at=started_at,
                finished_at=_now(),
                active=True,
                error="Outra execução do monitor já está ativa.",
            )
            self._append_log("cycle skipped: another run is active")
            return result

        try:
            result = self._run_locked(started_at)
            self._write_state(result)
            return result
        finally:
            lock.release()

    def status(self) -> dict[str, Any]:
        """Return the last persisted result without contacting AniList."""
        lock = _CycleLock(self.lock_path)
        if not lock.acquire():
            return {
                "status": "active",
                "active": True,
                "state_path": str(self.state_path),
            }
        lock.release()
        if not self.state_path.exists():
            return {"status": "unknown", "state_path": str(self.state_path)}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            data["state_path"] = str(self.state_path)
            return data
        except (OSError, json.JSONDecodeError):
            return {"status": "invalid", "state_path": str(self.state_path)}

    def _run_locked(self, started_at: str) -> CycleResult:
        animes: list[dict[str, Any]] = []
        try:
            if hasattr(self.client, "is_authenticated") and not self.client.is_authenticated():
                raise RuntimeError("Autenticação AniList não encontrada ou inválida.")
            entries = self._fetch_entries()
        except Exception as exc:  # one cycle must terminate cleanly and observably
            error = _safe_error(exc)
            self._append_log(f"cycle failed before anime processing: {error}")
            return CycleResult(1, "failed", started_at, _now(), error=error)

        seen_ids: set[int] = set()
        for entry in entries:
            anilist_id = _value(_value(entry, "media", entry), "id")
            if not isinstance(anilist_id, int) or anilist_id <= 0 or anilist_id in seen_ids:
                continue
            seen_ids.add(anilist_id)
            media = _value(entry, "media", entry)
            title = (
                _value(_value(media, "title", {}), "english")
                or _value(_value(media, "title", {}), "romaji")
                or _value(media, "title", "Desconhecido")
            )
            record = {"anilist_id": anilist_id, "title": str(title)}
            try:
                if not self._is_releasing(media):
                    record.update(status="skipped", reason="not_releasing", skipped=1)
                else:
                    resolved = self._resolve_binding(anilist_id)
                    binding = _value(resolved, "binding", resolved)
                    origin = _value(resolved, "origin", "configured")
                    if binding is None:
                        record.update(status="skipped", reason="source_not_configured", skipped=1)
                    else:
                        record.update(
                            source=_value(binding, "source"),
                            source_origin=origin,
                        )
                        processed = self._process_anime(entry, binding, str(title))
                        record.update(processed)
            except Exception as exc:
                error = _safe_error(exc)
                record.update(status="failed", reason="processing_error", error=error, failed=1)
                self._append_log(f"anime {anilist_id} failed: {error}")
            animes.append(record)

        failed = any(item.get("status") == "failed" for item in animes)
        result = CycleResult(
            1 if failed else 0,
            "failed" if failed else "completed",
            started_at,
            _now(),
            animes=animes,
        )
        self._append_log(
            f"cycle completed: anime={len(animes)} successful={result.successful} "
            f"failed={result.failed} skipped={result.skipped}"
        )
        return result

    def _fetch_entries(self) -> list[Any]:
        result_method = getattr(self.client, "get_watching_releasing_entries", None)
        if result_method is not None:
            result = result_method()
            if hasattr(result, "ok"):
                if not result.ok:
                    raise RuntimeError(
                        getattr(result, "error", None) or "Falha ao consultar AniList."
                    )
                return list(getattr(result, "entries", []) or [])
            if isinstance(result, list):
                return result
        method = getattr(self.client, "get_airing_episodes_for_watching", None)
        if method is None:
            method = getattr(self.client, "get_watching_airing_for_monitor", None)
        if method is None:
            raise RuntimeError("Cliente AniList não oferece consulta de airing para o monitor.")
        entries = method()
        return list(entries or [])

    @staticmethod
    def _is_releasing(media: Any) -> bool:
        status = _value(media, "status")
        return str(status or "").upper() == "RELEASING"

    def _resolve_binding(self, anilist_id: int) -> Any | None:
        resolver = self.binding_resolver
        if resolver is None:
            return None
        if callable(resolver):
            return resolver(anilist_id)
        for method_name in ("effective", "effective_for", "get_effective", "get_binding"):
            method = getattr(resolver, method_name, None)
            if method:
                return method(anilist_id)
        if isinstance(resolver, dict):
            value = resolver.get(anilist_id)
            if isinstance(value, dict) and "configured" in value:
                if value.get("configured") is not None:
                    return {"binding": value["configured"], "origin": "configured"}
                if value.get("last_played") is not None:
                    return {"binding": value["last_played"], "origin": "last_played"}
                return None
            if value is not None and hasattr(value, "configured"):
                configured = getattr(value, "configured", None)
                if configured is not None:
                    return {"binding": configured, "origin": "configured"}
                last_played = getattr(value, "last_played", None)
                if last_played is not None:
                    return {"binding": last_played, "origin": "last_played"}
            return value
        if hasattr(resolver, "configured"):
            configured = getattr(resolver, "configured", None)
            if configured is not None:
                return {"binding": configured, "origin": "configured"}
            last_played = getattr(resolver, "last_played", None)
            if last_played is not None:
                return {"binding": last_played, "origin": "last_played"}
        return None

    def _process_anime(self, entry: Any, binding: Any, title: str) -> dict[str, Any]:
        if self.processor is not None:
            return dict(self.processor(entry, binding))
        if self.download_service is None:
            from services.anime.download_service import AnimeDownloadService

            self.download_service = AnimeDownloadService()

        if hasattr(self.binding_resolver, "effective"):
            from services.anime.airing_downloads import AiringDownloadsService

            selection = AiringDownloadsService(
                client=self.client,
                repository=self.repository,
                source_store=self.binding_resolver,
            ).select_for_entry(entry)
            selected_binding = selection.source.binding
            if selected_binding is None:
                return {
                    "status": "skipped",
                    "reason": selection.source.reason or "source_not_configured",
                    "skipped": 1,
                }
            if not selection.episodes:
                return {
                    "status": "skipped",
                    "reason": "no_available_episodes",
                    "skipped": 1,
                }
            successful = failed = skipped = 0
            anilist_id = _value(_value(entry, "media", entry), "id")
            for candidate in selection.episodes:
                candidates = getattr(selection, "candidates_by_episode", {}).get(
                    candidate.episode_number, (candidate,)
                )
                episode_done = False
                for source_candidate in candidates:
                    candidate_binding = _binding_for_source(
                        selected_binding, source_candidate.source
                    )
                    player_url = self._resolve_player_url(
                        source_candidate.url, source_candidate.source
                    )
                    if not player_url:
                        continue
                    ep_url, src = player_url, source_candidate.source
                    result = self.download_service.download_episodes(
                        anime_title=_value(candidate_binding, "title", selected_binding.title),
                        range_input=str(source_candidate.source_episode_number),
                        total_episodes=source_candidate.source_episode_number,
                        get_episode_url=lambda _n, u=ep_url, s=src: (u, s),
                        anilist_id=anilist_id,
                        season=source_candidate.season,
                        catalog_episode_number=source_candidate.episode_number,
                        source=source_candidate.source,
                        variant=_value(candidate_binding, "variant", selected_binding.variant),
                        silent=True,
                        strict=True,
                        headers=_binding_headers(candidate_binding),
                        referrer=_binding_referrer(candidate_binding),
                        max_attempts=self.settings.max_attempts,
                        request_timeout_seconds=self.settings.request_timeout_seconds,
                    )
                    attempt_successful = int(_value(result, "successful", 0) or 0)
                    attempt_skipped = len(_value(result, "skipped", []) or [])
                    if attempt_successful or attempt_skipped:
                        successful += attempt_successful
                        skipped += attempt_skipped
                        episode_done = True
                        break
                if not episode_done:
                    failed += 1
            return {
                "status": "failed" if failed else "completed",
                "successful": successful,
                "failed": failed,
                "skipped": skipped,
                "reason": "download_failed" if failed else "downloaded_or_current",
            }

        # This is a conservative adapter for the current repository contract.
        # Newer download services can replace it by accepting ``processor``.
        source = _value(binding, "source")
        if not source or "," in str(source) or str(source).lower() == "mixed":
            return {"status": "skipped", "reason": "ambiguous_source"}
        if (
            hasattr(self.repository, "get_active_sources")
            and source not in self.repository.get_active_sources()
        ):
            return {"status": "failed", "reason": "source_unavailable", "failed": 1}

        self.repository.clear_search_results()
        self.repository.add_anime(
            _value(binding, "title", title),
            _value(binding, "anime_url", ""),
            source,
            _value(binding, "params", {}) or {},
        )
        self.repository.search_episodes(_value(binding, "title", title), source_filter=source)
        params = _value(binding, "params", {}) or {}
        season = params.get("season", 1) if isinstance(params, dict) else 1
        episode_numbers = self.repository.get_episode_list(_value(binding, "title", title), season)
        progress = int(_value(entry, "progress", 0) or 0)
        next_airing = _value(_value(entry, "media", entry), "nextAiringEpisode")
        next_episode = _value(next_airing, "episode") if next_airing else None
        candidates = [number for number in episode_numbers if number > progress]
        if next_episode:
            candidates = [number for number in candidates if number < int(next_episode)]
        if not candidates:
            return {"status": "skipped", "reason": "no_available_episodes", "skipped": 1}

        results: list[Any] = []
        for episode_number in sorted(set(candidates)):
            page = self.repository.get_episode_url_and_source(
                _value(binding, "title", title), episode_number
            )
            if not page or page[1] != source:
                continue
            player_url = self._resolve_player_url(page[0], source)
            if not player_url:
                continue
            result = self.download_service.download_episodes(
                anime_title=_value(binding, "title", title),
                range_input=str(episode_number),
                total_episodes=max(episode_number, 1),
                get_episode_url=lambda _number, url=player_url: (url, source),
            )
            results.append(result)
        successful = sum(int(_value(item, "successful", 0) or 0) for item in results)
        failed = sum(len(_value(item, "failed", []) or []) for item in results)
        skipped = sum(len(_value(item, "skipped", []) or []) for item in results)
        return {
            "status": "failed" if failed else "completed",
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "reason": "download_failed" if failed else "downloaded_or_current",
        }

    def _resolve_player_url(self, page_url: str, source: str) -> str | None:
        method = getattr(self.repository, "search_player_from_page", None)
        if method is None:
            return None
        candidates = method(page_url, source) or []
        return candidates[0] if candidates else None

    def _write_state(self, result: CycleResult) -> None:
        payload = result.as_dict()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.", dir=self.state_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.chmod(raw_path, 0o600)
            os.replace(raw_path, self.state_path)
        finally:
            if os.path.exists(raw_path):
                os.unlink(raw_path)

    def _append_log(self, message: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = f"{_now()} {message}\n"
        if (
            self.log_path.exists()
            and self.log_path.stat().st_size + len(line.encode()) > self.settings.log_max_bytes
        ):
            for index in range(self.settings.log_backup_count, 0, -1):
                old = self.log_path.with_name(f"{self.log_path.name}.{index}")
                newer = self.log_path.with_name(f"{self.log_path.name}.{index + 1}")
                if old.exists():
                    if index == self.settings.log_backup_count:
                        old.unlink()
                    else:
                        old.replace(newer)
            self.log_path.replace(self.log_path.with_name(f"{self.log_path.name}.1"))
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        os.chmod(self.log_path, 0o600)


def _safe_error(exc: Exception) -> str:
    """Keep state/logs useful without allowing accidental token disclosure."""
    message = str(exc)
    for marker in ("Bearer ", "access_token=", "token="):
        if marker in message:
            message = message.split(marker, 1)[0] + marker + "[redacted]"
    return message[:500]
