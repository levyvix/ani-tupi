import argparse
import sys

from scrapers import loader
from services.repository import rep
from ui.components import menu
from commands import anime as anime_cmd
from commands import anilist_menu as anilist_menu_cmd
from commands import anilist_auth as anilist_auth_cmd
from commands import manga as manga_cmd
from commands import manage_sources as manage_sources_cmd


def show_main_menu():
    """Display main menu with options."""
    options = [
        "🔍 Buscar Anime",
        "▶️  Continuar Assistindo",
        "📺 AniList",
        "📚 Mangá",
        "⚙️  Gerenciar Fontes",
    ]
    return menu(options, msg="Ani-Tupi - Menu Principal")


def main_menu_flow(args) -> None:
    """Show main menu and route to appropriate command handler."""
    choice = show_main_menu()

    if choice == "🔍 Buscar Anime":
        anime_cmd(args)
    elif choice == "▶️  Continuar Assistindo":
        # Set continue_watching flag and let anime handler take it
        args.continue_watching = True
        anime_cmd(args)
    elif choice == "📺 AniList":
        anilist_menu_cmd(args)
    elif choice == "📚 Mangá":
        manga_cmd(args)
    elif choice == "⚙️  Gerenciar Fontes":
        manage_sources_cmd(args)


def cli() -> None:
    """Entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="ani-tupi",
        description="Veja anime sem sair do terminal.",
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    # AniList command
    anilist_parser = subparsers.add_parser("anilist", help="Integração com AniList")
    anilist_parser.add_argument(
        "action",
        nargs="?",
        default="menu",
        choices=["auth", "menu"],
        help="auth: fazer login | menu: navegar listas (padrão)",
    )

    # Main anime command arguments (default)
    parser.add_argument(
        "--query",
        "-q",
    )
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--continue-watching", "-c", action="store_true", dest="continue_watching")
    parser.add_argument("--manga", "-m", action="store_true")
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="Listar todas as fontes de anime disponíveis",
    )
    parser.add_argument(
        "--clear-cache",
        nargs="?",
        const=True,
        metavar="[anime_name]",
        help="Limpar cache (sem argumentos limpa tudo, ou especifique anime para limpar apenas um)",
    )

    args = parser.parse_args()

    # Load plugins once at startup
    loader.load_plugins({"pt-br"})  # type: ignore

    # Show active sources
    active_sources = rep.get_active_sources()
    if active_sources:
        print(f"ℹ️  Fontes ativas: {', '.join(active_sources)}")

    # Handle --list-sources before other commands
    if args.list_sources:
        sources = rep.get_active_sources()
        if sources:
            print("\n🔌 Fontes de anime disponíveis:")
            for i, source in enumerate(sources, 1):
                print(f"   {i}. {source}")
        else:
            print("\n❌ Nenhuma fonte de anime encontrada!")
        sys.exit(0)

    # Handle --clear-cache before other commands
    if args.clear_cache:
        from utils.cache_manager import clear_cache_all, clear_cache_by_prefix
        from utils.anilist_discovery import auto_discover_anilist_id

        if args.clear_cache is True:
            # Clear all cache
            clear_cache_all()
            print("✅ Cache completamente limpo!")
        else:
            # Try to discover AniList ID for more precise clearing
            anilist_id = auto_discover_anilist_id(args.clear_cache)
            if anilist_id:
                clear_cache_by_prefix(f":{anilist_id}:")
                print(f"✅ Cache de '{args.clear_cache}' (AniList ID {anilist_id}) foi limpo!")
            else:
                # Fallback: clear by title prefix
                clear_cache_by_prefix(f":{args.clear_cache}:")
                print(f"✅ Cache de '{args.clear_cache}' foi limpo!")
        sys.exit(0)

    # Handle commands
    if args.command == "anilist":
        if args.action == "auth":
            anilist_auth_cmd(args)
            sys.exit(0)
        else:  # menu
            anilist_menu_cmd(args)
    elif args.query or args.continue_watching or args.manga:
        # Command-line arguments provided, route to appropriate handler
        if args.manga:
            manga_cmd(args)
        else:
            # Query or continue_watching - use anime command
            anime_cmd(args)
    else:
        # No arguments - show main menu and route
        main_menu_flow(args)


if __name__ == "__main__":
    cli()
