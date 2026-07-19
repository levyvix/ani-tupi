"""Account management menu for AniList user accounts."""

import os
import webbrowser

from models.config import get_data_path
from ui.components import loading, menu_navigate, pause, render_section, show_error, show_info
from utils.logging import get_logger

logger = get_logger(__name__)

# History file path (centralized from config)
HISTORY_PATH = get_data_path()

# Dependency injection holders
anilist_client = None


def set_anilist_client(client):
    """Set the AniList client dependency."""
    global anilist_client
    anilist_client = client


def get_search_title(title, display_title: str = "") -> str:
    """Get preferred title for search based on config.

    Args:
        title: AniListTitle object with romaji/english/native
        display_title: Fallback display title

    Returns:
        Title to use for searching (english or romaji based on config)
    """
    from models.config import settings

    if settings.anilist.prefer_english_title:
        return title.english or title.romaji or display_title
    return title.romaji or title.english or display_title


def show_account_menu() -> None:
    """Show account management menu with user stats and logout option."""
    # Load all data once at the beginning
    with loading("Carregando informações da conta..."):
        user_info = anilist_client.get_viewer_info()

        if not user_info:
            show_error("Não foi possível carregar as informações da conta.")
            pause()
            return

        username = user_info.name
        user_id = user_info.id

        # Get user stats - use API statistics directly
        stats = user_info.statistics
        api_count = stats.anime.count if stats and stats.anime else 0
        api_episodes = stats.anime.episodesWatched if stats and stats.anime else 0
        api_minutes = stats.anime.minutesWatched if stats and stats.anime else 0

        # Use API stats as primary source. Only calculate from lists if API returns 0
        # and API call succeeds (to avoid multiple requests on rate limiting)
        total_count = api_count
        episodes_watched = api_episodes
        minutes_watched = api_minutes

        days_watched = minutes_watched / (60 * 24) if minutes_watched > 0 else 0

        # Get recent activities
        activities = anilist_client.get_recent_activities(limit=5)

    # Build account info display (once)
    account_info = [
        f"👤 Usuário: {username}",
        f"🎬 Animes nas listas: {total_count}",
        f"📺 Episódios assistidos: {episodes_watched}",
        f"⏱️  Tempo estimado: {days_watched:.1f} dias",
        "",
        "📅 Atividades Recentes:",
    ]

    # Format recent activities
    if activities:
        status_emoji = {
            "watched episode": "▶️",
            "plans to watch": "📋",
            "completed": "✅",
            "dropped": "❌",
            "paused watching": "⏸️",
            "rewatched": "🔁",
        }

        for activity in activities:
            status = (activity.status or "").lower()
            progress = activity.progress
            media = activity.media
            if media:
                title = get_search_title(media.title, "Unknown")
                episodes = media.episodes
            else:
                title = "Unknown"
                episodes = None
            emoji = status_emoji.get(status, "•")

            if "watched episode" in status and progress:
                progress_str = str(progress)
                if episodes:
                    activity_msg = f"  {emoji} {title} ({progress_str}/{episodes})"
                else:
                    activity_msg = f"  {emoji} {title} (Ep {progress_str})"
            elif "completed" in status:
                activity_msg = f"  {emoji} Completou {title}"
            elif "plans to watch" in status:
                activity_msg = f"  {emoji} Planeja assistir {title}"
            elif "dropped" in status:
                activity_msg = f"  {emoji} Dropou {title}"
            elif "paused" in status:
                activity_msg = f"  {emoji} Pausou {title}"
            elif "rewatched" in status:
                activity_msg = f"  {emoji} Reassistiu {title}"
            else:
                activity_msg = f"  {emoji} {status}: {title}"

            account_info.append(activity_msg)
    else:
        account_info.append("  Nenhuma atividade recente")

    account_info.extend(["", "─" * 40])

    # Print account info once
    render_section(f"Conta: {username}", account_info)

    # Menu options loop
    while True:
        menu_options = [
            "🌐 Abrir perfil no navegador",
            "🚪 Logout",
        ]

        selection = menu_navigate(menu_options, f"Conta: {username}")

        if selection is None:
            # ESC pressed - clear screen and return to main menu
            os.system("clear" if os.name != "nt" else "cls")
            return

        if selection == "🌐 Abrir perfil no navegador":
            profile_url = f"https://anilist.co/user/{user_id}"
            show_info(f"Abrindo perfil no navegador: {profile_url}")
            webbrowser.open(profile_url)
            pause()
            continue

        if selection == "🚪 Logout":
            confirm_options = ["✅ Sim, fazer logout", "❌ Cancelar"]
            confirm = menu_navigate(confirm_options, "Tem certeza?")

            if confirm == "✅ Sim, fazer logout":
                token_path = HISTORY_PATH / "anilist_token.json"
                if token_path.exists():
                    token_path.unlink()
                    logger.info("\n✅ Logout realizado com sucesso!")
                    input("\nPressione Enter para continuar...")
                    os.system("clear" if os.name != "nt" else "cls")
                    return
                logger.info("\n❌ Token não encontrado")
                input("\nPressione Enter para continuar...")
            continue
