"""Manga CLI - read manga from MangaDex.

Thin command/orchestration layer for searching and reading manga. Menus and
spinners live here; all reading/search/download business logic lives in
``services/manga/*`` (notably ``read_orchestrator`` for the online flow).
"""

from InquirerPy import inquirer

from models.config import settings
from models.models import LocalChapter
from services.anilist import anilist_client
from services.local_manga_service import LocalMangaService
from services.manga_service import (
    MangaDexError,
    MangaHistory,
    MangaNotFoundError,
    UnifiedMangaService,
)
from services.manga.anilist_lists import handle_anilist_list
from services.manga.read_orchestrator import continue_manga_flow, start_manga_search
from ui.components import loading, menu_navigate, pause, show_error, show_info, show_warning
from utils.logging import get_logger
from utils.manga_reader import open_pdf_reader

logger = get_logger(__name__)


def _show_manga_main_menu() -> str | None:
    """Show main manga menu with options."""
    menu_options = [
        "📖 Reading",
        "✅ Completed",
        "📋 Planning",
        "📅 Recent",
        "📈 Trending",
        "🔍 Search",
        "📂 Local Library",
    ]
    return menu_navigate(menu_options, "Manga Tupi - Menu Principal")


def _handle_reading_list(service: UnifiedMangaService) -> None:
    handle_anilist_list(service, "reading", start_manga_search)


def _handle_completed_list(service: UnifiedMangaService) -> None:
    handle_anilist_list(service, "completed", start_manga_search)


def _handle_planning_list(service: UnifiedMangaService) -> None:
    handle_anilist_list(service, "planning", start_manga_search)


def _handle_recent_history(service: UnifiedMangaService) -> None:
    """Handle recent manga reading history using the MangaHistory service."""
    history = MangaHistory.load()
    if not history:
        show_info("Nenhum histórico recente", title="Histórico")
        pause()
        return

    recent_manga = list(history.items())[:10]

    options = []
    for i, (title, entry) in enumerate(recent_manga, 1):
        try:
            chapter = int(float(entry.last_chapter)) + 1
        except (TypeError, ValueError) as e:
            logger.debug(f"Parse error capítulo: {e}")
            chapter = "Desconhecido"
        options.append(f"{i:2d}. {title} - Cap. {chapter}")

    selection = menu_navigate(options, "Recent - Manga")
    if selection and selection != "← Voltar":
        try:
            idx = int(selection.split(".")[0]) - 1
            if 0 <= idx < len(recent_manga):
                title, _ = recent_manga[idx]
                start_manga_search(service, title)
        except (ValueError, IndexError):
            pass


def _handle_trending(service: UnifiedMangaService) -> None:
    """Handle trending manga from AniList."""
    with loading("Carregando trending manga..."):
        manga_list = anilist_client.get_trending_manga()

    if not manga_list:
        show_info("Nenhum mangá trending encontrado", title="Trending")
        pause()
        return

    options = []
    manga_map = {}
    for i, manga in enumerate(manga_list, 1):
        title = anilist_client.format_title(manga.title)
        chapters = getattr(manga, "chapters", None) or "?"
        score = getattr(manga, "averageScore", None) or "N/A"
        display = f"{i:2d}. {title} ({chapters} caps) ⭐{score}%"
        options.append(display)
        manga_map[display] = title

    selection = menu_navigate(options, "Trending - Manga")
    if selection and selection != "← Voltar":
        try:
            idx = int(selection.split(".")[0]) - 1
            if 0 <= idx < len(manga_list):
                start_manga_search(service, manga_map[selection])
        except (ValueError, IndexError):
            pass


def _handle_local_library() -> None:
    """Handle local library browsing (offline mode)."""
    config = settings.manga
    local_service = LocalMangaService(config.output_directory)

    with loading("Escaneando biblioteca local..."):
        manga_list = local_service.get_manga_list()

    if not manga_list:
        show_info(
            f"Nenhum mangá baixado encontrado\nDiretório: {config.output_directory}",
            title="Biblioteca local",
        )
        pause()
        return

    selection = menu_navigate(manga_list, "Local Library - Selecione Mangá")
    if selection is None:
        return

    manga_title = selection.split(" (")[0]
    _show_local_chapters(local_service, manga_title)


def _show_local_chapters(local_service: "LocalMangaService", manga_title: str) -> None:
    """Show chapters for selected manga from local library."""
    with loading("Carregando capítulos..."):
        chapters = local_service.get_chapters_for_manga(manga_title)

    if not chapters:
        show_warning(f"Nenhum capítulo encontrado para: {manga_title}", title="Capítulos")
        pause()
        return

    history = MangaHistory()
    last_chapter = history.get_last_chapter(manga_title)

    chapter_labels = [ch.display_name() for ch in chapters]
    if last_chapter:
        for i, ch in enumerate(chapters):
            if ch.chapter_number == last_chapter:
                chapter_labels[i] = f"⮕ Retomar: {chapter_labels[i]}"
                break

    while True:
        selected_label = menu_navigate(chapter_labels, f"{manga_title} - Selecione capítulo")
        if not selected_label:
            return

        clean_label = selected_label.replace("⮕ Retomar: ", "")
        chapter_names = [ch.display_name() for ch in chapters]
        if clean_label not in chapter_names:
            logger.error(f"Capítulo '{clean_label}' não encontrado.")
            return
        chapter_index = chapter_names.index(clean_label)

        _process_local_chapter(
            local_service, manga_title, chapters[chapter_index], chapters, chapter_index, history
        )


def _open_local_chapter(local_service, manga_title, chapter):
    """Ensure a local chapter has a PDF and open it. Returns (pdf_path, reader_process)."""
    pdf_path = chapter.pdf_path
    if not chapter.has_pdf and chapter.has_images:
        logger.info("📄 Criando PDF a partir das imagens...")
        pdf_path = local_service.auto_create_pdf_if_needed(manga_title, chapter.chapter_number)
        if not pdf_path:
            show_error("Erro ao criar PDF")
            pause()
            return None, None
    elif not chapter.has_pdf:
        show_error("Capítulo não disponível (sem PDF ou imagens)")
        pause()
        return None, None

    if pdf_path is None:
        show_error("Caminho do PDF não disponível")
        pause()
        return None, None

    return pdf_path, open_pdf_reader(pdf_path)


def _process_local_chapter(
    local_service: "LocalMangaService",
    manga_title: str,
    chapter: "LocalChapter",
    all_chapters: list["LocalChapter"],
    current_index: int,
    history: MangaHistory,
) -> None:
    """Process and open local chapters, looping through navigation with AniList sync."""
    while True:
        pdf_path, reader_process = _open_local_chapter(local_service, manga_title, chapter)
        if pdf_path is None:
            return

        history.update(manga_title, chapter.chapter_number, chapter_id=None, manga_id=None)

        anilist_synced = False
        try:
            if anilist_client.is_authenticated():
                if local_service.sync_to_anilist_if_ahead(
                    manga_title, chapter.chapter_number, anilist_client
                ):
                    logger.info("✅ Progresso sincronizado com AniList")
                    anilist_synced = True
        except Exception as exc:
            logger.debug("AniList sync check failed for '%s': %s", manga_title, exc)
            pass

        if anilist_synced and settings.manga.auto_delete_read_chapters:
            try:
                chapter_folder = chapter.pdf_path.parent if chapter.pdf_path else None
                if chapter_folder and chapter_folder.exists():
                    import shutil

                    shutil.rmtree(chapter_folder)
                    logger.info("✓ Capítulo deletado automaticamente: economizando espaço em disco")
            except Exception as e:
                logger.info(f"⚠️  Não foi possível deletar capítulo automaticamente: {e}")

        if reader_process:
            logger.info("\n📖 Feche o leitor de PDF para continuar.")
            reader_process.wait()

        action = menu_navigate(
            [
                "Próximo capítulo",
                "Capítulo anterior",
                "Ler novamente",
                "Selecionar outro capítulo",
            ],
            "O que deseja fazer?",
        )

        if action == "Selecionar outro capítulo":
            return

        if action == "Próximo capítulo":
            if current_index + 1 < len(all_chapters):
                current_index += 1
                chapter = all_chapters[current_index]
            else:
                show_info("Você chegou ao último capítulo disponível!", title="Navegação")
                pause()
                return
        elif action == "Capítulo anterior":
            if current_index > 0:
                current_index -= 1
                chapter = all_chapters[current_index]
            else:
                show_info("Este é o primeiro capítulo!", title="Navegação")
                pause()
                return
        elif action == "Ler novamente":
            continue
        else:
            return


def _handle_search_flow(service: UnifiedMangaService) -> None:
    """Handle the free-text search flow."""
    query = inquirer.text(message="Pesquise mangá").execute()  # type: ignore[attr-defined]
    if not query.strip():
        show_warning("Pesquisa vazia", title="Busca")
        return

    selected_source = service.current_source
    search_term = query.split(" / ")[-1].strip() if " / " in query else query

    try:
        with loading(f"Buscando mangás em {selected_source}..."):
            results = service.search_manga(search_term)
    except MangaNotFoundError:
        show_error("Mangá não encontrado. Tente outra pesquisa.")
        return
    except MangaDexError as e:
        show_warning(e.user_message)
        return
    except Exception as e:
        show_error(f"Erro inesperado: {e}")
        return

    if not results:
        show_error("Nenhum mangá encontrado. Tente outra pesquisa.")
        return

    manga_titles = [m.title for m in results]
    try:
        selected_title = menu_navigate(manga_titles, "Selecione mangá")
    except KeyboardInterrupt:
        return

    if selected_title is None:
        return

    selected_manga = next((m for m in results if m.title == selected_title), None)
    if selected_manga is None:
        logger.error(f"Manga '{selected_title}' não encontrado nos resultados.")
        return

    continue_manga_flow(service, selected_manga, allow_source_change=True)


def main() -> None:
    """Main manga CLI entry point."""
    config = settings.manga
    try:
        service = UnifiedMangaService(config)
    except RuntimeError as e:
        logger.info(f"❌ {e}")
        return

    handlers = {
        "📖 Reading": _handle_reading_list,
        "✅ Completed": _handle_completed_list,
        "📋 Planning": _handle_planning_list,
        "📅 Recent": _handle_recent_history,
        "📈 Trending": _handle_trending,
        "🔍 Search": _handle_search_flow,
    }

    while True:
        choice = _show_manga_main_menu()
        if choice is None:
            return

        if choice == "📂 Local Library":
            _handle_local_library()
        elif choice in handlers:
            handlers[choice](service)
        else:
            return


if __name__ == "__main__":
    main()
