"""Update command handler for ani-tupi CLI."""

from __future__ import annotations

import shlex
import subprocess

from models.config import settings
from services.update_check_service import UpdateCheckService
from utils.logging import get_logger

logger = get_logger(__name__)


def update(args) -> int:
    """Check for a newer release and run the configured update command."""
    service = UpdateCheckService()
    local_version = service._get_local_version()
    latest_version = service._fetch_latest_version()

    logger.info(f"ani-tupi local: {local_version}")
    if not latest_version:
        logger.info("ani-tupi remoto: indisponível (falha ao consultar release)")
        return 0

    logger.info(f"ani-tupi remoto: {latest_version}")
    if not service._is_remote_newer(local_version, latest_version):
        logger.info("✅ Você já está na versão mais recente.")
        return 0

    logger.info(f"⬆️  Atualização disponível. Execute: {settings.updates.update_command}")
    logger.info("⏳ Executando comando de atualização...")

    try:
        cmd = shlex.split(settings.updates.update_command)
        completed = subprocess.run(cmd)
    except OSError as exc:
        logger.error(f"❌ Falha ao iniciar atualização: {exc}")
        return 1

    if completed.returncode != 0:
        logger.error(f"❌ Comando de atualização falhou com código {completed.returncode}")
        return completed.returncode

    logger.info("✅ Atualização concluída com sucesso.")
    return 0
