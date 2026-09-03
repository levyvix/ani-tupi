"""Filter menus for anime selection (status, year, season)."""

from datetime import datetime

from models.models import Status
from ui.components import menu_navigate


def status_select_menu(navigate=None) -> Status | None:
    """Show status submenu mapping readable labels to Status enum.

    Returns:
        Selected Status, or None on ESC
    """
    status_options = [
        "📺 Watching (Assistindo)",
        "📋 Planning (Planejo assistir)",
        "✅ Completed (Completo)",
        "⏸️  Paused (Pausado)",
        "❌ Dropped (Dropado)",
        "🔁 Repeating (Reassistindo)",
    ]

    status_map = {
        "📺 Watching (Assistindo)": Status.CURRENT,
        "📋 Planning (Planejo assistir)": Status.PLANNING,
        "✅ Completed (Completo)": Status.COMPLETED,
        "⏸️  Paused (Pausado)": Status.PAUSED,
        "❌ Dropped (Dropado)": Status.DROPPED,
        "🔁 Repeating (Reassistindo)": Status.REPEATING,
    }

    selection = (navigate or menu_navigate)(status_options, "Escolha o novo status")

    if selection is None:
        return None

    return status_map.get(selection)


def choose_year() -> int | None:
    """Let user choose year filter for trending.

    Returns:
        Year (int) or 0 for "all years", or None if cancelled

    """
    current_year = datetime.now().year

    # Generate year options (current year + 10 years back)
    year_options = ["🌐 Todos os anos"]
    year_options.extend([str(year) for year in range(current_year, current_year - 11, -1)])

    selection = menu_navigate(year_options, "Escolha o ano")

    if selection is None:
        return None

    if selection == "🌐 Todos os anos":
        return 0  # 0 means "all years"

    return int(selection)


def choose_season() -> str | None:
    """Let user choose season filter for trending.

    Returns:
        Season string (WINTER, SPRING, SUMMER, FALL) or "ALL", or None if cancelled

    """
    season_options = [
        "🌐 Todas as temporadas",
        "Q1 - 🌸 Primavera (Spring)",
        "Q2 - ☀️  Verão (Summer)",
        "Q3 - 🍂 Outono (Fall)",
        "Q4 - ❄️  Inverno (Winter)",
    ]

    season_map = {
        "🌐 Todas as temporadas": "ALL",
        "Q1 - 🌸 Primavera (Spring)": "SPRING",
        "Q2 - ☀️  Verão (Summer)": "SUMMER",
        "Q3 - 🍂 Outono (Fall)": "FALL",
        "Q4 - ❄️  Inverno (Winter)": "WINTER",
    }

    selection = menu_navigate(season_options, "Escolha a temporada")

    if selection is None:
        return None

    return season_map.get(selection)


def choose_status() -> str | None:
    """Let user choose list status.

    Returns:
        Status string (CURRENT, PLANNING, etc) or None if cancelled

    """
    status_options = [
        "📺 Watching (Assistindo)",
        "📋 Planning (Planejo assistir)",
        "✅ Completed (Completo)",
        "⏸️  Paused (Pausado)",
        "❌ Dropped (Dropado)",
        "🔁 Rewatching (Reassistindo)",
    ]

    status_map = {
        "📺 Watching (Assistindo)": "CURRENT",
        "📋 Planning (Planejo assistir)": "PLANNING",
        "✅ Completed (Completo)": "COMPLETED",
        "⏸️  Paused (Pausado)": "PAUSED",
        "❌ Dropped (Dropado)": "DROPPED",
        "🔁 Rewatching (Reassistindo)": "REPEATING",
    }

    selection = menu_navigate(status_options, "Escolha o status")

    if selection is None:
        return None

    return status_map.get(selection)
