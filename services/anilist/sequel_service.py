"""Sequel detection and continuation service.

Detects and offers sequels when anime finishes.
"""

from services.core import ui_bridge
from services.anilist import anilist_client
from models.models import Status
from utils.logging import get_logger

logger = get_logger(__name__)


def _is_anime_released(anime_node) -> bool:
    """Check if an anime has started airing or is finished.

    Args:
        anime_node: AniListRelationNode with status and startDate

    Returns:
        True if anime has started airing (RELEASING or FINISHED), False if not yet released
    """
    if not anime_node:
        return True  # Assume released if no data

    # Check status field
    if hasattr(anime_node, "status"):
        status = anime_node.status
        if status == "NOT_YET_RELEASED":
            return False
        if status in ("RELEASING", "FINISHED"):
            return True

    return True  # Default to released if status is unknown


def offer_sequel_and_continue(
    anilist_id: int,
    args,
    current_episode: int | None = None,
    anilist_episodes: int | None = None,
) -> bool:
    """Check for sequels when last episode is watched and offer to continue.

    Args:
        anilist_id: AniList ID of the anime just watched
        args: Command line arguments
        current_episode: Current episode number (for checking if series is truly complete)
        anilist_episodes: Total episodes on AniList (if known)

    Returns:
        True if user accepted sequel and it started playback, False otherwise
    """
    # Import here to avoid circular dependency
    from services.anime.anilist_integration import anilist_anime_flow

    # Only offer sequels if authenticated
    if not anilist_client.is_authenticated():
        return False

    # If we know the AniList episode count, check if series is actually complete
    # This prevents offering sequels when the current source has fewer episodes
    if anilist_episodes and current_episode:
        if current_episode < anilist_episodes:
            # User has more episodes to watch - don't offer sequel
            remaining = anilist_episodes - current_episode
            logger.info(
                f"\n💡 Existem mais {remaining} episódio(s) disponível(is) em outras fontes."
            )
            return False

    # Get sequels from AniList
    sequels = anilist_client.get_sequels(anilist_id)

    if not sequels:
        return False  # No sequels found

    # Format sequel options
    if len(sequels) == 1:
        sequel = sequels[0]
        sequel_title = anilist_client.format_title(sequel.title)
        is_released = _is_anime_released(sequel)

        # Single sequel: offer multiple options (but suggest Planning if not yet released)
        if is_released:
            menu_options = [
                "▶️ Procurar episódios",
                "📋 Adicionar à 'Planejo Assistir'",
                "❌ Não, parar aqui",
            ]
        else:
            menu_options = ["📋 Adicionar à 'Planejo Assistir'", "❌ Não, parar aqui"]
            sequel_title += " ⏳ (ainda não lançado)"

        choice = ui_bridge.menu_navigate(
            menu_options,
            msg=f"Deseja continuar com a sequência?\n\n→ {sequel_title}",
        )

        if choice == "▶️ Procurar episódios":
            # Get sequel info and start playback
            anilist_anime_flow(
                sequel_title,
                sequel.id,
                args,
                anilist_progress=0,
                display_title=sequel_title,
                total_episodes=sequel.episodes,
            )
            return True
        elif choice == "📋 Adicionar à 'Planejo Assistir'":
            # Add to Planning list without searching for episodes
            success = anilist_client.add_to_list(sequel.id, Status.PLANNING)
            if success:
                logger.info(f"✅ {sequel_title} adicionado à sua lista de 'Planejo Assistir'!")
            else:
                logger.info(f"❌ Erro ao adicionar {sequel_title} à sua lista.")
            return False
    else:
        # Multiple sequels: let user choose and then ask what to do
        sequel_options = []
        for s in sequels:
            title = anilist_client.format_title(s.title)
            is_released = _is_anime_released(s)
            if not is_released:
                title += " ⏳"
            sequel_options.append(title)

        choice = ui_bridge.menu_navigate(
            sequel_options + ["❌ Não, parar aqui"],
            msg="Qual sequência deseja assistir?",
        )

        if choice and choice != "❌ Não, parar aqui":
            # Find selected sequel (removing the ⏳ indicator if present)
            choice_clean = choice.replace(" ⏳", "")
            selected_sequel = next(
                (s for s in sequels if anilist_client.format_title(s.title) == choice_clean),
                None,
            )
            if selected_sequel:
                sequel_title = anilist_client.format_title(selected_sequel.title)
                is_released = _is_anime_released(selected_sequel)

                # Ask what user wants to do (but suggest Planning if not yet released)
                if is_released:
                    action_options = [
                        "▶️ Procurar episódios",
                        "📋 Adicionar à 'Planejo Assistir'",
                        "❌ Cancelar",
                    ]
                else:
                    action_options = [
                        "📋 Adicionar à 'Planejo Assistir'",
                        "❌ Cancelar",
                    ]
                    sequel_title += " ⏳ (ainda não lançado)"

                action_choice = ui_bridge.menu_navigate(
                    action_options,
                    msg=f"O que deseja fazer com {sequel_title}?",
                )

                if action_choice == "▶️ Procurar episódios":
                    anilist_anime_flow(
                        sequel_title,
                        selected_sequel.id,
                        args,
                        anilist_progress=0,
                        display_title=sequel_title,
                        total_episodes=selected_sequel.episodes,
                    )
                    return True
                elif action_choice == "📋 Adicionar à 'Planejo Assistir'":
                    # Add to Planning list without searching for episodes
                    success = anilist_client.add_to_list(selected_sequel.id, Status.PLANNING)
                    if success:
                        logger.info(
                            f"\n✅ {sequel_title} adicionado à sua lista de 'Planejo Assistir'!"
                        )
                    else:
                        logger.info(f"❌ Erro ao adicionar {sequel_title} à sua lista.")
                    return False

    return False
