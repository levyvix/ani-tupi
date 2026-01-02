"""AniList integration command handler.

This module handles:
- Authentication with AniList
- Browsing trending anime and user lists
- Watching anime via AniList with progress sync
"""

from services import anime_service
from ui.anilist_menus import anilist_main_menu, authenticate_flow


def anilist_auth(args) -> None:
    """Handle AniList authentication flow."""
    authenticate_flow()


def anilist_menu(args) -> None:
    """Handle AniList menu and watching loop.

    Allows users to browse and watch anime from AniList,
    with automatic progress synchronization.
    """
    # Loop to allow watching multiple anime without restarting
    while True:
        result = anilist_main_menu()
        if not result:
            break  # User cancelled/exited

        anime_title, anilist_id = result
        # Start normal flow with selected anime
        anime_service.anilist_anime_flow(anime_title, anilist_id, args)
        # After watching, loop back to AniList menu
