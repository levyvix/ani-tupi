"""Unified AniList manga list handler.

Consolidates _handle_reading_list, _handle_completed_list, _handle_planning_list
into a single parameterized function to eliminate code duplication.
"""

from collections.abc import Callable

from services.anilist_service import anilist_client
from services.manga_service import UnifiedMangaService
from ui.components import loading, menu_navigate, pause, show_info, show_warning
from utils.logging import get_logger

logger = get_logger(__name__)


# Status configuration: (anilist_status, loading_message, empty_message, menu_title)
LIST_CONFIG = {
    "reading": (
        "CURRENT",
        "lista de leitura",
        "Nenhum mangá na lista de leitura",
        "Reading - Manga",
    ),
    "completed": (
        "COMPLETED",
        "lista completos",
        "Nenhum mangá completado",
        "Completed - Manga",
    ),
    "planning": (
        "PLANNING",
        "lista planejados",
        "Nenhum mangá planejado",
        "Planning - Manga",
    ),
}


def handle_anilist_list(
    service: UnifiedMangaService,
    list_type: str,
    on_manga_selected: Callable[[UnifiedMangaService, str], None],
) -> None:
    """Handle any AniList manga list (reading, completed, planning).

    Replaces three nearly-identical functions (_handle_reading_list,
    _handle_completed_list, _handle_planning_list) with a single
    parameterized implementation.

    Args:
        service: UnifiedMangaService instance
        list_type: One of "reading", "completed", "planning"
        on_manga_selected: Callback when user selects a manga
                          (receives service and title)

    Raises:
        ValueError: If list_type is not recognized
    """
    if list_type not in LIST_CONFIG:
        raise ValueError(
            f"Unknown list type: {list_type}. Must be one of {list(LIST_CONFIG.keys())}"
        )

    anilist_status, loading_msg, empty_msg, menu_title = LIST_CONFIG[list_type]

    # Check authentication
    if not anilist_client.is_authenticated():
        show_warning("Faça login primeiro: uv run python main.py anilist auth", title="AniList")
        pause()
        return

    # Load list
    with loading(f"Carregando {loading_msg}..."):
        manga_list = anilist_client.get_user_manga_list(anilist_status)

    if not manga_list:
        show_info(empty_msg, title=menu_title)
        pause()
        return

    # Format options
    options = []
    manga_map = {}

    for i, manga in enumerate(manga_list, 1):
        if manga.media:
            title = anilist_client.format_title(manga.media.title)

            # Different display format for reading vs completed/planning
            if list_type == "reading":
                progress = manga.progress or 0
                total_chapters = getattr(manga.media, "chapters", None) or "?"
                display = f"{i:2d}. {title} - Cap. {progress}/{total_chapters}"
            else:
                chapters = getattr(manga.media, "chapters", None) or "?"
                score = getattr(manga.media, "averageScore", None) or "N/A"
                display = f"{i:2d}. {title} ({chapters} caps) ⭐{score}%"

            options.append(display)
            manga_map[display] = title

    # Show menu
    selection = menu_navigate(options, menu_title)

    if selection and selection != "← Voltar":
        try:
            idx = int(selection.split(".")[0]) - 1
            if 0 <= idx < len(manga_list):
                manga_title = manga_map[selection]
                on_manga_selected(service, manga_title)
        except (ValueError, IndexError):
            pass
