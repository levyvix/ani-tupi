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
    from services.anilist_service import anilist_client

    # Loop to allow watching multiple anime without restarting
    while True:
        result = anilist_main_menu()
        if not result:
            break  # User cancelled/exited

        anime_title, anilist_id = result

        # Fetch anime info to get display title and total episodes
        anime_info = anilist_client.get_anime_by_id(anilist_id)
        display_title = None
        total_episodes = None
        anilist_progress = 0

        if anime_info:
            display_title = anilist_client.format_title(anime_info.title)
            total_episodes = anime_info.episodes

            # Get user progress if logged in
            entry = anilist_client.get_media_list_entry(anilist_id)
            if entry and entry.progress:
                anilist_progress = entry.progress
        # Start normal flow with selected anime (with all parameters)
        anime_service.anilist_anime_flow(
            anime_title,
            anilist_id,
            args,
            anilist_progress=anilist_progress,
            display_title=display_title,
            total_episodes=total_episodes,
        )
        # After watching, loop back to AniList menu
