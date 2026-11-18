"""Interactive CLI settings command."""

from __future__ import annotations

from pydantic import ValidationError

from services.core.settings_management_service import SettingsManagementService
from ui.components import menu_navigate
from utils.logging import get_logger

logger = get_logger(__name__)


SAVE_OPTION = "💾 Salvar alterações"
DISCARD_OPTION = "🗑️ Descartar alterações"
CONFIRM_SAVE = "✅ Sim, salvar agora"
CONFIRM_DISCARD = "🗑️ Sim, descartar alterações"
KEEP_EDITING = "↩️ Voltar às configurações"


def config(args) -> int:
    """Interactive settings editor grouped by category."""
    service = SettingsManagementService()
    staged: dict[str, dict[str, object]] = {}

    while True:
        pending_count = _pending_count(staged)
        top_options = [
            *[label for _, label in service.categories()],
            SAVE_OPTION,
            DISCARD_OPTION,
        ]
        status = f" · {pending_count} alterações pendentes" if pending_count else ""
        top_choice = menu_navigate(top_options, msg=f"ani-tupi config{status}", enable_search=False)

        if top_choice is None or top_choice == DISCARD_OPTION:
            if not staged:
                logger.info("ℹ️ Nenhuma alteração pendente para salvar.")
                return 0
            action = _confirm_pending_changes()
            if action == "continue":
                continue
            if action == "save":
                if _save_staged(service, staged):
                    return 0
                continue
            logger.info("⚠️ Alterações descartadas.")
            return 0

        if top_choice == SAVE_OPTION:
            if not staged:
                logger.info("ℹ️ Nenhuma alteração pendente para salvar.")
                return 0
            if (
                menu_navigate(
                    [CONFIRM_SAVE, KEEP_EDITING],
                    msg=f"Salvar {_pending_count(staged)} alterações?",
                    enable_search=False,
                )
                != CONFIRM_SAVE
            ):
                continue
            if _save_staged(service, staged):
                return 0
            continue

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
        field_options: list[str] = []
        field_by_option: dict[str, tuple[str, str]] = {}
        for settings_group, field_name in service.fields_in_category(category_key):
            group_changes = staged.get(settings_group, {})
            value = group_changes.get(
                field_name, service.get_effective_value(settings_group, field_name)
            )
            description = service.field_description(settings_group, field_name)
            option = f"{description} · atual: {value}"
            field_options.append(option)
            field_by_option[option] = (settings_group, field_name)

        choice = menu_navigate(
            field_options,
            msg=(
                f"{category_label} — {service.category_description(category_key)}\n"
                f"{_pending_count(staged)} alterações pendentes"
            ),
            enable_search=True,
        )
        if choice is None:
            return

        settings_group, field_name = field_by_option[choice]
        current_value = staged.get(settings_group, {}).get(
            field_name,
            service.get_effective_value(settings_group, field_name),
        )
        description = service.field_description(settings_group, field_name)
        logger.info(f"ℹ️ {category_label}: {description}")
        if settings_group == "plugins" and field_name == "priority_order":
            logger.info(
                "ℹ️ Dica: informe só os itens que quer no topo (ex: animefire,anitube). "
                "Os não citados mantêm a ordem atual."
            )
        raw = input(f"Novo valor para '{description}' (atual: {current_value}): ").strip()
        if raw == "":
            logger.info("ℹ️ Alteração cancelada para este campo.")
            continue

        try:
            parsed = service.parse_input_value(
                settings_group, field_name, raw, current_value=current_value
            )
        except (ValueError, TypeError) as exc:
            logger.error(f"❌ Valor inválido: {exc}")
            continue

        original_value = service.get_effective_value(settings_group, field_name)
        if parsed == original_value:
            staged.get(settings_group, {}).pop(field_name, None)
            if not staged.get(settings_group):
                staged.pop(settings_group, None)
            logger.info("ℹ️ Valor igual ao atual; alteração pendente removida.")
            continue

        staged.setdefault(settings_group, {})[field_name] = parsed
        logger.info(f"✅ Alteração pendente: {description} = {parsed}")


def _pending_count(staged: dict[str, dict[str, object]]) -> int:
    return sum(len(fields) for fields in staged.values())


def _confirm_pending_changes() -> str:
    choice = menu_navigate(
        [CONFIRM_SAVE, CONFIRM_DISCARD, KEEP_EDITING],
        msg="Há alterações nesta sessão. O que deseja fazer?",
        enable_search=False,
    )
    if choice == CONFIRM_SAVE:
        return "save"
    if choice == CONFIRM_DISCARD:
        return "discard"
    return "continue"


def _save_staged(service: SettingsManagementService, staged: dict[str, dict[str, object]]) -> bool:
    try:
        service.validate_staged(staged)
    except ValidationError as exc:
        logger.error("❌ Falha de validação. Revise os valores antes de salvar.")
        logger.error(str(exc))
        return False
    service.save_staged(staged)
    logger.info("✅ Configurações salvas com sucesso.")
    return True


def _find_category_key(service: SettingsManagementService, label: str) -> str | None:
    for key, category_label in service.categories():
        if category_label == label:
            return key
    return None
