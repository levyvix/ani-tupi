"""Manga search and reading command handler.

This module handles:
- Manga search and selection
- Chapter reading flow
- Reading history management
"""


def manga(args) -> None:
    """Handle manga search and reading flow.

    Delegates to the separate manga_tupi module which contains
    all manga-specific functionality.
    """
    from manga_tupi import main as manga_tupi

    manga_tupi()
