import argparse
import sys

from scrapers import loader
from services.repository import rep
from ui.components import menu
from commands import (
    anime as anime_cmd,
    anilist_auth as anilist_auth_cmd,
    anilist_menu as anilist_menu_cmd,
    config as config_cmd,
    manage_sources as manage_sources_cmd,
    manga as manga_cmd,
    update as update_cmd,
)
from commands.cache import handle_clear_cache
from commands.update import run_startup_update_check, show_version_info
from utils.logging import get_logger

logger = get_logger(__name__)


def handle_local_library(args) -> None:
    """Handle local anime library browsing and playback.

    Shows downloaded anime and allows playback of offline episodes.
    """
    from commands.local_anime import handle_local_library_playback

    handle_local_library_playback(args)


def show_main_menu() -> str | None:
    """Display main menu with options."""
    options = [
        "🔍 Buscar Anime",
        "▶️  Continuar Assistindo",
        "📂 Biblioteca Local",
        "📺 AniList",
        "📚 Mangá",
        "⚙️  Gerenciar Fontes",
    ]
    return menu(options, msg="Ani-Tupi - Menu Principal")


def main_menu_flow(args) -> None:
    """Show main menu and route to appropriate command handler."""
    while True:
        choice = show_main_menu()

        if choice == "🔍 Buscar Anime":
            anime_cmd(args)
        elif choice == "▶️  Continuar Assistindo":
            # Keep the menu's shared namespace immutable between handlers.
            continue_values = vars(args).copy()
            continue_values["continue_watching"] = True
            anime_cmd(argparse.Namespace(**continue_values))
        elif choice == "📂 Biblioteca Local":
            handle_local_library(args)
        elif choice == "📺 AniList":
            anilist_menu_cmd(args)
        elif choice == "📚 Mangá":
            manga_cmd(args)
        elif choice == "⚙️  Gerenciar Fontes":
            manage_sources_cmd(args)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without executing application startup."""
    parser = argparse.ArgumentParser(
        prog="ani-tupi",
        description="Veja anime sem sair do terminal.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    anilist_parser = subparsers.add_parser("anilist", help="Integração com AniList")
    anilist_parser.add_argument(
        "action",
        nargs="?",
        default="menu",
        choices=["auth", "menu"],
        help="auth: fazer login | menu: navegar listas (padrão)",
    )
    subparsers.add_parser("update", help="Verificar e atualizar ani-tupi")
    subparsers.add_parser("config", help="Configurar o ani-tupi interativamente")

    parser.add_argument("--query", "-q")
    parser.add_argument(
        "-e", "--episode", type=int, help="Número do episódio para assistir (ex: 5)"
    )
    parser.add_argument(
        "-S", "--season", type=int, help="Número da estação para anime com múltiplas estações"
    )
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument(
        "--version",
        action="store_true",
        help="Mostrar versão local e comparar com a release remota",
    )
    parser.add_argument("--continue-watching", "-c", action="store_true", dest="continue_watching")
    parser.add_argument("--manga", "-m", action="store_true")
    parser.add_argument(
        "--list-sources", action="store_true", help="Listar todas as fontes de anime disponíveis"
    )
    parser.add_argument(
        "--random",
        "-r",
        action="store_true",
        help="Sortear um anime aleatório da lista do AniList e reproduzir",
    )
    parser.add_argument(
        "--clear-cache", nargs="?", const=True, metavar="[anime_name]", help="Limpar cache"
    )
    return parser


def cli() -> None:
    """Entry point for CLI."""
    args = build_parser().parse_args()

    # Configure logging early, before any other imports or operations
    from utils.logging import configure_logging

    configure_logging(debug=args.debug)

    if args.command == "update":
        sys.exit(update_cmd(args))
    if args.command == "config":
        sys.exit(config_cmd(args))

    if args.version:
        show_version_info()
        sys.exit(0)

    run_startup_update_check()

    # Load plugins once at startup
    loader.load_plugins(rep.register)

    # Retry offline AniList syncs on startup
    from models.config import settings

    if settings.offline_sync.enable_auto_retry:
        from services.anime.offline_sync_service import retry_offline_syncs

        result = retry_offline_syncs()
        if result["successful"] > 0 or result["failed"] > 0:
            logger.info(
                f"📡 Sincronização offline: {result['successful']} ok, "
                f"{result['failed']} falha(s) pendente(s)"
            )

    # Show active sources
    active_sources = rep.get_active_sources()
    if active_sources:
        logger.debug(f"ℹ️  Fontes ativas: {', '.join(active_sources)}")

    # Handle --list-sources before other commands
    if args.list_sources:
        sources = rep.get_active_sources()
        if sources:
            logger.info("\n🔌 Fontes de anime disponíveis:")
            for i, source in enumerate(sources, 1):
                logger.info(f"   {i}. {source}")
        else:
            logger.info("\n❌ Nenhuma fonte de anime encontrada!")
        sys.exit(0)

    # Handle --clear-cache before other commands
    if args.clear_cache:
        handle_clear_cache(args.clear_cache)
        sys.exit(0)

    # Handle commands
    if args.command == "anilist":
        if args.action == "auth":
            anilist_auth_cmd(args)
            sys.exit(0)
        else:  # menu
            anilist_menu_cmd(args)
    elif args.query or args.continue_watching or args.manga or args.random:
        # Command-line arguments provided, route to appropriate handler
        if args.manga:
            manga_cmd(args)
        elif args.random:
            from commands.anime import handle_random_anime

            handle_random_anime(args)
        else:
            # Query or continue_watching - use anime command
            anime_cmd(args)
    else:
        # No arguments - show main menu and route
        main_menu_flow(args)


if __name__ == "__main__":
    cli()
