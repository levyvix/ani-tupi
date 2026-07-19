"""Interactive CLI settings command."""

from __future__ import annotations

from pydantic import ValidationError

from services.core.settings_management_service import SettingsManagementService
from ui.components import menu_navigate
from utils.logging import get_logger

logger = get_logger(__name__)


SAVE_OPTION = "💾 Salvar alterações"
DISCARD_OPTION = "🗑️ Descartar alterações"


def config(args) -> int:
    """Interactive settings editor grouped by category."""
    service = SettingsManagementService()
    staged: dict[str, dict[str, object]] = {}

    while True:
        top_options = [
            *[label for _, label in service.categories()],
            SAVE_OPTION,
            DISCARD_OPTION,
        ]
        top_choice = menu_navigate(top_options, msg="ani-tupi config", enable_search=False)

        if top_choice is None or top_choice == DISCARD_OPTION:
            logger.info("⚠️ Nenhuma alteração foi salva.")
            return 0

        if top_choice == SAVE_OPTION:
            if not staged:
                logger.info("ℹ️ Nenhuma alteração pendente para salvar.")
                return 0
            try:
                service.validate_staged(staged)
            except ValidationError as exc:
                logger.error("❌ Falha de validação. Revise os valores antes de salvar.")
                logger.error(str(exc))
                continue
            service.save_staged(staged)
            logger.info("✅ Configurações salvas com sucesso.")
            return 0

        category_key = _find_category_key(service, top_choice)
        if not category_key:
            logger.error("❌ Categoria inválida.")
            continue

        _edit_category(service, category_key, top_choice, staged)


def _edit_category(
    service: SettingsManagementService,
    category_key: str,
    category_label: str,
    staged: dict[str, dict[str, object]],
) -> None:
    while True:
        field_options = []
        for field_name in service.fields_for_category(category_key):
            staged_value = staged.get(category_key, {}).get(field_name)
            value = (
                staged_value
                if staged_value is not None
                else service.get_effective_value(category_key, field_name)
            )
            description = service.field_description(category_key, field_name)
            field_options.append(f"{field_name} = {value} :: {description}")

        choice = menu_navigate(
            field_options, msg=f"Configuração: {category_label}", enable_search=True
        )
        if choice is None:
            return

        field_name = choice.split(" = ", 1)[0]
        env_var = service.env_var_name(category_key, field_name)
        if service.is_env_override_active(category_key, field_name):
            logger.warning(
                f"⚠️ Esta chave está sobreposta por variável de ambiente ({env_var}). "
                "Em runtime, a env var continuará com prioridade."
            )

        current_value = staged.get(category_key, {}).get(
            field_name,
            service.get_effective_value(category_key, field_name),
        )
        description = service.field_description(category_key, field_name)
        logger.info(f"ℹ️ {category_label}.{field_name}: {description}")
        if category_key == "plugins" and field_name == "priority_order":
            logger.info(
                "ℹ️ Dica: informe só os itens que quer no topo (ex: animefire,anitube). "
                "Os não citados mantêm a ordem atual."
            )
        raw = input(
            f"Novo valor para {category_label}.{field_name} (atual: {current_value}): "
        ).strip()
        if raw == "":
            logger.info("ℹ️ Alteração cancelada para este campo.")
            continue

        try:
            parsed = service.parse_input_value(
                category_key, field_name, raw, current_value=current_value
            )
        except (ValueError, TypeError) as exc:
            logger.error(f"❌ Valor inválido: {exc}")
            continue

        staged.setdefault(category_key, {})[field_name] = parsed
        logger.info(f"✅ Alteração pendente: {category_label}.{field_name} = {parsed}")


def _find_category_key(service: SettingsManagementService, label: str) -> str | None:
    for key, category_label in service.categories():
        if category_label == label:
            return key
    return None
