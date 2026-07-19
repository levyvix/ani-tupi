"""Update command handler for ani-tupi CLI."""

from __future__ import annotations

import subprocess

from models.config import settings
from services.core.update_check_service import UpdateCheckService
from utils.logging import get_logger

logger = get_logger(__name__)


def run_startup_update_check() -> None:
    """Check for updates and render a startup notice when one is available."""
    try:
        result = UpdateCheckService().check_for_updates()
        if result.update_available and result.message:
            logger.info(result.message)
    except Exception as exc:
        logger.debug(f"Startup update check skipped due to unexpected error: {exc}")


def show_version_info() -> None:
    """Show local version and compare with the latest remote release."""
    service = UpdateCheckService()
    local_version, latest_version = service.get_version_info()

    logger.info(f"ani-tupi local: {local_version}")
    if not latest_version:
        logger.info("ani-tupi remoto: indisponível (falha ao consultar release)")
        return

    logger.info(f"ani-tupi remoto: {latest_version}")
    if service.is_remote_newer(local_version, latest_version):
        logger.info(f"⬆️  Atualização disponível. Execute: {settings.updates.update_command}")
    else:
        logger.info("✅ Você já está na versão mais recente.")


def update(args) -> int:
    """Check for a newer release and run the configured update command."""
    service = UpdateCheckService()
    local_version, latest_version = service.get_version_info()

    logger.info(f"ani-tupi local: {local_version}")
    if not latest_version:
        logger.info("ani-tupi remoto: indisponível (falha ao consultar release)")
        return 0

    logger.info(f"ani-tupi remoto: {latest_version}")
    if not service.is_remote_newer(local_version, latest_version):
        logger.info("✅ Você já está na versão mais recente.")
        return 0

    logger.info(f"⬆️  Atualização disponível. Execute: {settings.updates.update_command}")
    logger.info("⏳ Executando comando de atualização...")

    completed = None
    try:
        completed = subprocess.run(settings.updates.update_command, shell=True)
    except OSError as exc:
        logger.error(f"❌ Falha ao iniciar atualização: {exc}")
        return 1

    if completed is None or completed.returncode != 0:
        code = completed.returncode if completed is not None else 1
        logger.error(f"❌ Comando de atualização falhou com código {code}")
        return code

    logger.info("✅ Atualização concluída com sucesso.")
    return 0
