"""CLI handlers for the airing-download monitor."""

from __future__ import annotations

from typing import Any

from services.anime.airing_download_systemd import AiringDownloadSystemd, SystemdError
from services.anime.airing_download_scheduler import AiringDownloadScheduler


def airing_downloads(args: Any) -> int:
    """Dispatch one monitor action and return its process exit code."""
    action = getattr(args, "airing_downloads", None)
    handlers = {
        "configure": configure,
        "install": install,
        "run": run,
        "status": status,
        "remove": remove,
    }
    handler = handlers.get(action)
    if handler is None:
        return 2
    return int(handler(args) or 0)


def configure(_args: Any) -> int:
    from scrapers import loader
    from services.repository import rep
    from services.anime.airing_download_configuration import configure_airing_downloads

    loader.load_plugins(rep.register)
    return int(configure_airing_downloads() or 0)


def install(_args: Any) -> int:
    try:
        monitor = AiringDownloadSystemd()
        result = monitor.install()
    except (SystemdError, ValueError, OSError) as exc:
        print(f"Erro ao instalar o monitor: {exc}")
        return 1
    print(
        "Monitor instalado: "
        f"intervalo configurado, launcher em {result.launcher_path}. "
        "A validade remota da credencial será verificada no ciclo."
    )
    return 0


def run(_args: Any) -> int:
    from scrapers import loader
    from services.repository import rep

    loader.load_plugins(rep.register)
    monitor = AiringDownloadSystemd()
    result = AiringDownloadScheduler(
        state_path=monitor.state_path,
        lock_path=monitor.state_dir / "airing_download.lock",
        log_path=monitor.state_dir / "airing_download.log",
    ).run_once()
    if result.error:
        print(result.error)
    return result.exit_code


def status(_args: Any) -> int:
    monitor = AiringDownloadSystemd()
    systemd_status = monitor.status()
    last = AiringDownloadScheduler(
        state_path=monitor.state_path,
        lock_path=monitor.state_dir / "airing_download.lock",
        log_path=monitor.state_dir / "airing_download.log",
    ).status()
    print(f"Agendamento systemd: {'instalado' if systemd_status.installed else 'não instalado'}")
    print(f"Daemon systemd user: {systemd_status.daemon}")
    print(f"Execução ativa/último estado: {last.get('status', 'unknown')}")
    print(f"Estado: {last.get('state_path', monitor.state_path)}")
    for anime in last.get("animes", []):
        source = anime.get("source")
        origin = anime.get("source_origin")
        source_info = f" fonte={source} origem={origin}" if source else ""
        print(
            f"- {anime.get('title', anime.get('anilist_id', 'anime'))}: "
            f"{anime.get('status', 'unknown')} {anime.get('reason', '')}{source_info}"
        )
    return 0


def remove(_args: Any) -> int:
    try:
        result = AiringDownloadSystemd().remove()
    except (SystemdError, OSError) as exc:
        print(f"Erro ao remover o monitor: {exc}")
        return 1
    print(f"Monitor removido; launcher preservado em {result.launcher_path}.")
    return 0


__all__ = ["airing_downloads", "configure", "install", "run", "status", "remove"]
