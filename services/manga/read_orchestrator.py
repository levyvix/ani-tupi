"""Online manga reading orchestration (UI-injected).

Extracted from the ``manga_tupi.py`` monolith. These functions drive the
interactive online-reading flow (search -> pick manga -> pick source ->
resume/select chapter -> read/download), but they never import the
presentation layer. UI callables (``menu``, ``progress``, ``prompt``,
``show_*``) are injected, defaulting to lazy ``ui_bridge`` proxies — the same
dependency-injection pattern used by ``services/history_service.py``.

Business decisions (resume point, chapter sorting/lookup, source switching,
batch download) live in the sibling service modules; this module wires them
together and interleaves the menus.
"""

from models.models import Status
from services import ui_bridge
from services.anilist_service import anilist_client
from services.manga_service import (
    DownloadedChaptersTracker,
    MangaDexError,
    MangaHistory,
    MangaNotFoundError,
    UnifiedMangaService,
)
from services.manga.download import (
    _download_images,
    download_chapters_batch,
    prompt_download_range,
    resolve_parallelism,
    split_new_and_downloaded,
)
from services.manga.reading_flow import (
    build_manga_url,
    compute_resume_point,
    find_chapter_by_number,
    find_next_chapter_index,
    match_anilist_progress,
    promote_resume_chapter,
    sort_chapters_ascending,
)
from services.manga.source_selection import (
    research_manga_in_new_source,
    resume_from_other_source,
)
from utils.logging import get_logger
from utils.manga_reader import is_zathura_running, open_pdf_reader
from utils.manga_selection_preferences import manga_selection_preferences
from utils.manga_source_preferences import manga_source_preferences
from utils.pdf_converter import create_pdf_from_images

logger = get_logger(__name__)


def start_manga_search(
    service: UnifiedMangaService,
    title: str,
    menu=ui_bridge.menu_navigate,
    progress=ui_bridge.loading,
) -> None:
    """Search for a manga by title, pick one, then continue into the read flow."""
    search_term = title.split(" / ")[-1].strip() if " / " in title else title

    try:
        with progress(f"Buscando '{search_term}'..."):
            results = service.search_manga(search_term)
    except MangaNotFoundError:
        logger.info("❌ Mangá não encontrado. Tente outra pesquisa.")
        return
    except MangaDexError as e:
        logger.info(f"⚠️  {e.user_message}")
        return
    except Exception as e:
        logger.info(f"❌ Erro inesperado: {e}")
        return

    if not results:
        logger.info("❌ Nenhum mangá encontrado. Tente outra pesquisa.")
        return

    preferred_manga_id = manga_selection_preferences.get_preferred_manga_id(title)
    selected_manga = None
    if preferred_manga_id:
        selected_manga = next((m for m in results if m.id == preferred_manga_id), None)

    if selected_manga:
        suffix = _sources_suffix(selected_manga.sources)
        try:
            choice = menu(
                [
                    f"⭐ Continuar com: {selected_manga.title}{suffix} (salvo)",
                    "🔄 Trocar de mangá",
                ],
                "Qual mangá deseja ler?",
            )
        except KeyboardInterrupt:
            return
        if choice is None:
            return
        if choice.startswith("🔄"):
            selected_manga = None

    if not selected_manga:
        if len(results) > 1:
            label_to_manga = {}
            for manga in results:
                suffix = _sources_suffix(manga.sources)
                if manga.id == preferred_manga_id:
                    label = f"⭐ {manga.title}{suffix} (salvo)"
                else:
                    label = f"{manga.title}{suffix}"
                label_to_manga[label] = manga
            try:
                selected_title = menu(list(label_to_manga), "Selecione mangá")
            except KeyboardInterrupt:
                return
            if selected_title is None:
                return
            selected_manga = label_to_manga.get(selected_title)
            if selected_manga is None:
                logger.error(f"Manga '{selected_title}' não encontrado nos resultados.")
                return
        else:
            selected_manga = results[0]

    manga_selection_preferences.set_preferred_manga_id(title, selected_manga.id)
    logger.info(f"✓ Preferência salva: {selected_manga.title}")

    continue_manga_flow(
        service, selected_manga, allow_source_change=True, menu=menu, progress=progress
    )


def _sources_suffix(sources) -> str:
    sources_str = ", ".join(sorted(sources)) if sources else ""
    return f" [{sources_str}]" if sources_str else ""


def _select_source(
    service: UnifiedMangaService, selected_manga, current_source: str, menu, progress
) -> str | None:
    """Interactive source-change menu. Returns chosen source, or None to abort."""
    if len(service.get_available_sources()) <= 1:
        return current_source

    manga_sources = list(getattr(selected_manga, "sources", {}) or {})
    saved_source = manga_source_preferences.get_preferred_source(selected_manga.title)
    sources_with_manga = manga_sources or service.get_available_sources_for_manga(
        selected_manga.title
    )

    menu_options = [f"📖 Ler com {current_source}"]
    if saved_source and saved_source != current_source:
        if saved_source in sources_with_manga:
            menu_options.append(f"⭐ Usar fonte salva: {saved_source}")
        else:
            manga_source_preferences.remove_preference(selected_manga.title)
            saved_source = None
    for source in sources_with_manga:
        if source != current_source:
            menu_options.append(f"🔄 Trocar para: {source}")

    sources_str = ", ".join(sorted(sources_with_manga)) if sources_with_manga else ""
    menu_title = selected_manga.title
    if sources_str:
        menu_title += f" [{sources_str}]"
    menu_title += f" - Fonte: {current_source}"

    try:
        action = menu(menu_options, menu_title)
    except KeyboardInterrupt:
        return None

    if action is None:
        return None
    if action.startswith("⭐ Usar fonte salva:"):
        new_source = action.split(": ")[1]
        if service.set_source(new_source):
            research_manga_in_new_source(service, selected_manga, new_source, progress=progress)
            logger.info(f"✓ Fonte alterada para: {new_source}")
            return new_source
    elif action.startswith("🔄 Trocar para:"):
        new_source = action.split(": ")[1]
        if service.set_source(new_source):
            research_manga_in_new_source(service, selected_manga, new_source, progress=progress)
            manga_source_preferences.set_preferred_source(selected_manga.title, new_source)
            logger.info(f"✓ Fonte alterada e salva: {new_source}")
            return new_source
        logger.info(f"❌ Falha ao alterar fonte para: {new_source}")
        return None
    return current_source


def _get_anilist_progress(selected_manga) -> int | None:
    if not anilist_client.is_authenticated():
        return None
    try:
        manga_list = anilist_client.get_user_manga_list("CURRENT")
        return match_anilist_progress(manga_list, selected_manga.title, anilist_client.format_title)
    except Exception:
        return None


def _load_chapters_with_fallback(
    service, selected_manga, selected_source, allow_source_change, progress
):
    """Load chapters, trying other sources on failure. Returns (chapters, source, url)."""
    manga_url = build_manga_url(selected_source, selected_manga.id)
    try:
        with progress(f"Carregando capítulos de {selected_source}..."):
            chapters = service.get_chapters(
                selected_manga.id, manga_url=manga_url, source=selected_source
            )
        return chapters, selected_source, manga_url
    except MangaDexError as e:
        logger.info(f"⚠️  {e.user_message}")
        if not allow_source_change:
            return None, selected_source, manga_url
        logger.info("🔄 Tentando outras fontes...")
        for fallback_source in service.get_available_sources():
            if fallback_source == selected_source:
                continue
            logger.info(f"  Tentando {fallback_source}...")
            try:
                if service.set_source(fallback_source):
                    fb_id = (selected_manga.sources or {}).get(fallback_source, selected_manga.id)
                    manga_url = build_manga_url(fallback_source, fb_id)
                    chapters = service.get_chapters(
                        fb_id, manga_url=manga_url, source=fallback_source
                    )
                    if chapters:
                        selected_manga.id = fb_id
                        manga_source_preferences.set_preferred_source(
                            selected_manga.title, fallback_source
                        )
                        logger.info(f"✓ Usando fonte alternativa: {fallback_source}")
                        return chapters, fallback_source, manga_url
            except Exception:
                continue
        return None, selected_source, manga_url
    except Exception as e:
        logger.info(f"❌ Erro ao carregar capítulos: {e}")
        return None, selected_source, manga_url


def continue_manga_flow(
    service: UnifiedMangaService,
    selected_manga,
    allow_source_change: bool = True,
    menu=ui_bridge.menu_navigate,
    progress=ui_bridge.loading,
) -> None:
    """Continue with chapter selection and reading for a selected manga."""
    manga_sources = list(getattr(selected_manga, "sources", {}) or {})
    selected_source = (
        manga_sources[0] if manga_sources else (service.last_found_source or service.current_source)
    )

    if allow_source_change:
        chosen = _select_source(service, selected_manga, selected_source, menu, progress)
        if chosen is None:
            return
        selected_source = chosen

    if manga_source_preferences.get_preferred_source(selected_manga.title) != selected_source:
        manga_source_preferences.set_preferred_source(selected_manga.title, selected_source)

    history = MangaHistory()
    resume_point = compute_resume_point(
        _get_anilist_progress(selected_manga),
        history.get_last_chapter(selected_manga.title),
    )

    resume_immediately = False
    if resume_point is not None:
        try:
            resume_choice = menu(
                [
                    f"⮕ Sim, retomar capítulo {resume_point.chapter_number} "
                    f"({resume_point.source})",
                    "📋 Não, ver lista completa de capítulos",
                ],
                f"{selected_manga.title} - Retomar leitura?",
            )
        except KeyboardInterrupt:
            return
        if resume_choice and resume_choice.startswith("⮕ Sim, retomar"):
            resume_immediately = True
            logger.info(f"✓ Retomando capítulo {resume_point.chapter_number}...")

    chapters, selected_source, manga_url = _load_chapters_with_fallback(
        service, selected_manga, selected_source, allow_source_change, progress
    )
    if not chapters:
        logger.info("❌ Nenhum capítulo disponível")
        return

    sort_chapters_ascending(chapters)

    if resume_immediately and resume_point is not None:
        recommended = find_chapter_by_number(chapters, resume_point.chapter_number)
        if not recommended or not recommended.url:
            logger.info(
                f"⚠️  Capítulo {resume_point.chapter_number} não disponível em "
                f"{selected_source}. Tentando outras fontes..."
            )
            fallback = resume_from_other_source(
                service,
                selected_manga,
                resume_point.chapter_number,
                selected_source,
                progress=progress,
            )
            if fallback:
                selected_source, manga_url, chapters, recommended = fallback
                manga_source_preferences.set_preferred_source(selected_manga.title, selected_source)

        if recommended and recommended.url:
            logger.info(
                f"✓ Capítulo {resume_point.chapter_number} encontrado em {selected_source}. "
                "Iniciando leitura..."
            )
            _process_chapter(
                service,
                selected_manga,
                recommended,
                manga_url,
                selected_source,
                history,
                chapters,
                [ch.display_name() for ch in chapters],
                chapters.index(recommended),
                menu,
                progress,
            )
            return
        logger.info(
            f"⚠️  Capítulo {resume_point.chapter_number} não encontrado em nenhuma fonte. "
            "Mostrando lista completa..."
        )

    chapter_labels = [ch.display_name() for ch in chapters]
    if resume_point is not None and not resume_immediately:
        promote_resume_chapter(chapters, chapter_labels, resume_point)

    current_index = 0
    auto_load_next = False
    while True:
        if not auto_load_next:
            try:
                selected_label = menu(chapter_labels, "Selecione capítulo")
            except KeyboardInterrupt:
                return
            if not selected_label:
                return
            display_label = selected_label.replace("⮕ Retomar - ", "")
            current_index = next(
                (
                    i
                    for i, label in enumerate(chapter_labels)
                    if label.replace("⮕ Retomar - ", "") == display_label
                ),
                0,
            )

        auto_load_next = False
        selected_chapter = chapters[current_index]
        action = _show_chapter_action_menu(menu)
        if action is None:
            continue
        if action == "read":
            _process_chapter(
                service,
                selected_manga,
                selected_chapter,
                manga_url,
                selected_source,
                history,
                chapters,
                chapter_labels,
                current_index,
                menu,
                progress,
            )
        elif action == "download":
            handle_download_for_later(
                service,
                selected_manga,
                selected_chapter,
                manga_url,
                selected_source,
                history,
                chapters,
                menu=menu,
                progress=progress,
            )


def _show_chapter_action_menu(menu) -> str | None:
    selection = menu(
        [
            "📖 Ler Agora (Read Now)",
            "⬇️  Baixar para Depois (Download for Later)",
            "↩️  Voltar (Back)",
        ],
        "O que deseja fazer?",
    )
    if selection is None or selection == "↩️  Voltar (Back)":
        return None
    if "📖" in selection:
        return "read"
    if "⬇️" in selection:
        return "download"
    return None


def handle_download_for_later(
    service,
    selected_manga,
    selected_chapter,
    manga_url,
    selected_source,
    history,
    chapters: list | None = None,
    menu=ui_bridge.menu_navigate,
    progress=ui_bridge.loading,
    prompt=ui_bridge.prompt,
) -> None:
    """Download-for-later flow: menus here, batching in the download service."""
    from models.config import settings

    config = settings.manga

    if chapters is None:
        try:
            with progress(f"Carregando capítulos de {selected_source}..."):
                all_chapters = service.get_chapters(
                    selected_manga.id, manga_url=manga_url, source=selected_source
                )
        except Exception as e:
            logger.info(f"❌ Erro ao carregar capítulos: {e}")
            return
        all_chapters.reverse()  # scraper returns descending
    else:
        all_chapters = chapters

    if not all_chapters:
        logger.info("❌ Nenhum capítulo disponível")
        return

    chapters_to_download = prompt_download_range(
        history.get_last_chapter(selected_manga.title),
        all_chapters,
        default_count=config.default_download_range,
    )
    if not chapters_to_download:
        return

    tracker = DownloadedChaptersTracker()
    new_chapters, already_downloaded = split_new_and_downloaded(
        chapters_to_download, selected_manga.id, tracker
    )

    if already_downloaded and config.skip_already_downloaded:
        confirm = menu(
            ["✅ Sim, continuar", "❌ Cancelar", "🔄 Re-baixar todos"],
            f"{len(already_downloaded)} capítulo(s) já baixado(s). Continuar apenas com novos?",
        )
        if confirm == "❌ Cancelar":
            return
        if confirm == "🔄 Re-baixar todos":
            new_chapters = chapters_to_download

    if not new_chapters:
        logger.info(f"✓ Todos os {len(already_downloaded)} capítulo(s) já estão baixados")
        return

    logger.info(f"\n📥 Baixando {len(new_chapters)} capítulo(s)...")
    max_parallel = resolve_parallelism(config.max_parallel_downloads)

    if max_parallel == 1 or len(new_chapters) == 1:

        def _on_failure(_error_msg: str) -> bool:
            try:
                return (
                    menu(["✅ Continuar", "❌ Cancelar"], "Continuar com próximo capítulo?")
                    == "✅ Continuar"
                )
            except Exception:
                return False

        result = download_chapters_batch(
            new_chapters,
            service,
            selected_manga,
            manga_url,
            selected_source,
            config,
            tracker,
            max_parallel=1,
            on_failure=_on_failure,
        )
    else:
        logger.info(f"🚀 Usando {max_parallel} downloads paralelos...")
        from tqdm import tqdm

        with tqdm(total=len(new_chapters), desc="📥 Baixando capítulos", unit="cap") as pbar:

            def _on_progress(successful: int, failed: list[str]) -> None:
                pbar.set_postfix({"✅": successful, "❌": len(failed)}, refresh=False)
                pbar.update(1)

            result = download_chapters_batch(
                new_chapters,
                service,
                selected_manga,
                manga_url,
                selected_source,
                config,
                tracker,
                max_parallel=max_parallel,
                on_progress=_on_progress,
            )

    logger.info(f"\n✓ Download concluído: {result.successful} capítulo(s) baixados")
    if result.failed_chapters:
        logger.info(
            f"⚠️  {len(result.failed_chapters)} capítulo(s) falharam: "
            f"{', '.join(result.failed_chapters)}"
        )
    prompt("Pressione Enter para voltar ao menu...")


def _prepare_chapter_pdf(selected_manga, selected_chapter, selected_source, service, progress):
    """Download images and build the chapter PDF. Returns pdf_path or None."""
    from models.config import settings

    config = settings.manga
    output_path = config.output_directory / selected_manga.title / selected_chapter.number
    output_path.mkdir(parents=True, exist_ok=True)
    pdf_path = output_path / f"{selected_chapter.number}.pdf"

    if pdf_path.exists():
        logger.info("📖 Abrindo capítulo existente...")
        return pdf_path

    try:
        with progress("Carregando páginas..."):
            pages = service.get_chapter_pages(
                selected_chapter.id, chapter_url=selected_chapter.url or "", source=selected_source
            )
    except MangaDexError as e:
        logger.info(f"⚠️  {e.user_message}")
        return None
    except Exception as e:
        logger.info(f"❌ Erro ao carregar páginas: {e}")
        return None

    if not pages:
        logger.info("❌ Nenhuma página disponível para este capítulo")
        return None

    logger.info(f"Baixando {len(pages)} páginas...")
    try:
        _download_images(pages, output_path, config)
        if not config.auto_create_pdf:
            logger.info(f"✓ Capítulo salvo em: {output_path}")
            return None
        logger.info("📄 Criando PDF...")
        create_pdf_from_images(output_path, pdf_path, quality=config.pdf_quality)
        if config.delete_images_after_pdf:
            for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                for img in output_path.glob(ext):
                    img.unlink()
            logger.info("🗑️  Imagens removidas (mantendo apenas PDF)")
        logger.info(f"✓ PDF criado: {pdf_path}")
        return pdf_path
    except Exception as e:
        logger.info(f"❌ Erro ao processar capítulo: {e}")
        if output_path.exists():
            for f in output_path.glob("*"):
                f.unlink(missing_ok=True)
        return None


def _sync_read_to_anilist(selected_manga, selected_chapter, pdf_path, menu) -> None:
    """Confirm chapter completion and sync progress to AniList (interactive)."""
    from models.config import settings

    if not anilist_client.is_authenticated():
        return
    try:
        confirm = menu(
            ["✅ Sim, li até o final", "❌ Não, parei antes"],
            f"Você leu o capítulo {selected_chapter.number} até o final?",
        )
        if confirm != "✅ Sim, li até o final":
            logger.info("✓ Progresso não atualizado no AniList (capítulo não concluído)")
            return

        search_results = anilist_client.search_manga(selected_manga.title)
        if not search_results:
            logger.info(f"⚠️  Mangá não encontrado no AniList: {selected_manga.title}")
            return

        best_match = search_results[0]
        list_entry = anilist_client.get_manga_list_entry(best_match.id)
        chapter_num = int(float(selected_chapter.number))
        if anilist_client.update_manga_progress(best_match.id, chapter_num):
            logger.info(
                f"✓ Progresso atualizado no AniList: {selected_manga.title} "
                f"- Cap. {selected_chapter.number}"
            )
            if not list_entry or list_entry.status == "PLANNING":
                anilist_client.change_manga_status(best_match.id, Status.CURRENT)
                logger.info("✓ Status alterado para: Lendo")
        else:
            logger.info("⚠️  Falha ao atualizar progresso no AniList")

        if settings.manga.auto_delete_read_chapters and pdf_path and pdf_path.exists():
            try:
                import shutil

                shutil.rmtree(pdf_path.parent)
                logger.info("✓ Capítulo deletado automaticamente: economizando espaço em disco")
            except Exception as e:
                logger.info(f"⚠️  Não foi possível deletar capítulo automaticamente: {e}")
    except Exception as e:
        logger.info(f"⚠️  Erro ao sincronizar com AniList: {e}")


def _process_chapter(
    service,
    selected_manga,
    selected_chapter,
    manga_url,
    selected_source,
    history,
    chapters,
    chapter_labels,
    current_index,
    menu,
    progress,
) -> None:
    """Process chapter reading, looping through next/previous/re-read navigation."""
    while True:
        pdf_path = _prepare_chapter_pdf(
            selected_manga, selected_chapter, selected_source, service, progress
        )
        if pdf_path is None:
            return

        open_pdf_reader(pdf_path)
        history.update(
            selected_manga.title,
            selected_chapter.number,
            chapter_id=selected_chapter.id,
            manga_id=selected_manga.id,
        )

        if is_zathura_running():
            logger.info("📖 Feche o Zathura para continuar.")
            while is_zathura_running():
                import time

                time.sleep(1)
            logger.info("✓ Zathura fechado. Continuando...")

        _sync_read_to_anilist(selected_manga, selected_chapter, pdf_path, menu)

        try:
            action = menu(
                ["Próximo", "Anterior", "Ler novamente", "Selecionar outro capítulo"],
                "O que deseja fazer?",
            )
        except KeyboardInterrupt:
            return

        if action is None or action in ("Sair", "Selecionar outro capítulo"):
            return

        if action == "Próximo":
            next_index = find_next_chapter_index(chapters, selected_chapter.number)
            if next_index is None:
                logger.info("Você chegou ao final dos capítulos disponíveis")
                return
            current_index = next_index
            chapter_labels[current_index] = chapter_labels[current_index].replace(
                "⮕ Retomar - ", ""
            )
        elif action == "Anterior":
            if current_index - 1 >= 0:
                current_index -= 1
                chapter_labels[current_index] = chapter_labels[current_index].replace(
                    "⮕ Retomar - ", ""
                )
            else:
                logger.info("Você está no primeiro capítulo")
        # "Ler novamente" re-reads the current chapter (no index change).

        selected_chapter = chapters[current_index]
