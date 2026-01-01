"""CLI entry point for ani-tupi.

Thin wrapper that delegates to existing main.py functionality.
Future refactoring will extract business logic to core/anime_service.py.
"""

from main import cli as main_cli

def cli() -> None:
    """Entry point for CLI - delegates to main.py for now."""
    main_cli()


if __name__ == "__main__":
    cli()
