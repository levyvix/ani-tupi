"""AniList token persistence and OAuth helpers."""


def load_token(client, *, settings_obj, json_module):
    """Load access token and user_id from file."""
    token_file = settings_obj.anilist.token_file
    if not token_file.exists():
        return None
    try:
        with token_file.open() as f:
            data = json_module.load(f)
            raw_user_id = data.get("user_id")
            client.user_id = int(raw_user_id) if raw_user_id else None  # Load user_id if exists
            return data.get("access_token")
    except Exception:
        return None


def save_token(
    client, token: str, user_id: int | None = None, *, settings_obj, json_module
) -> None:
    """Save access token and user_id to file."""
    token_file = settings_obj.anilist.token_file
    token_file.parent.mkdir(parents=True, exist_ok=True)
    data = {"access_token": token}
    if user_id:
        data["user_id"] = str(user_id)
    with token_file.open("w") as f:
        json_module.dump(data, f)


def parse_token(token_input: str) -> str:
    """Parse token from user input.

    Handles: raw token, URL with fragment, or access_token= prefix.
    """
    token = token_input.strip()

    # If user pasted full URL with fragment
    if "#access_token=" in token:
        token = token.split("#access_token=")[1].split("&")[0]
    # If user pasted just the fragment part
    elif "access_token=" in token:
        token = token.split("access_token=")[1].split("&")[0]
    # If user pasted URL-encoded version
    elif "%23access_token=" in token:
        token = token.split("%23access_token=")[1].split("&")[0]

    return token.strip()


def validate_token(client, token: str, *, httpx_module, log) -> bool:
    """Validate token by fetching viewer info."""
    query = """
        query {
            Viewer {
                id
                name
            }
        }
        """
    try:
        result = client._query(query, token=token)
        return result is not None and "Viewer" in result
    except httpx_module.ConnectError:
        log.warning(
            "⚠️  Não foi possível conectar ao AniList. Verifique sua conexão ou tente mais tarde."
        )
        raise
    except httpx_module.TimeoutException:
        log.warning("⚠️  AniList não respondeu a tempo. O serviço pode estar fora do ar.")
        raise
    except Exception as e:
        msg = str(e)
        server_error = any(f"status {code}" in msg for code in (500, 502, 503, 504))
        if server_error:
            log.warning("⚠️  AniList retornou erro de servidor. O serviço pode estar fora do ar.")
            raise
        log.debug(f"Token validation error: {e}")
        return False


def authenticate(
    client, max_retries: int = 3, *, settings_obj, token_provider, httpx_module, log
) -> bool:
    """OAuth authentication flow (headless mode).

    Displays authorization URL and waits for token input via stdin.
    Supports token pasted from URL fragment or raw token string.

    Args:
        max_retries: Maximum number of token input attempts

    Returns:
        True if authentication successful, False otherwise
    """
    # Build OAuth URL
    auth_url = f"{settings_obj.anilist.auth_url}?client_id={settings_obj.anilist.client_id}&response_type=token"

    # Try to get token from user (up to max_retries times)
    for attempt in range(max_retries):
        token_input = token_provider(auth_url)

        if not token_input:
            # User cancelled
            return False

        # Parse token from URL if needed
        token = client._parse_token(token_input)

        if not token:
            remaining = max_retries - attempt - 1
            if remaining > 0:
                log.info(
                    f"\n❌ Invalid token format. Please try again ({remaining} attempts left).\n"
                )
            continue

        # Validate token
        try:
            valid = client._validate_token(token)
        except (httpx_module.ConnectError, httpx_module.TimeoutException):
            return False
        except Exception:
            log.info(
                "\n❌ Não foi possível validar o token. AniList pode estar fora do ar. Tente novamente mais tarde.\n"
            )
            return False

        if valid:
            client.token = token

            # Get and display user info
            user_info = client.get_viewer_info()
            if user_info:
                client.user_id = user_info.id  # Save user ID for queries
                client._save_token(token, client.user_id)  # Save both token and user_id
                log.info(f"\n✅ Authentication successful! Welcome, {user_info.name}!")
            return True

        # Token validation failed
        remaining = max_retries - attempt - 1
        if remaining > 0:
            log.info(
                f"\n❌ Token validation failed. Please check the token and try again ({remaining} attempts left).\n"
            )

    log.info("\n❌ Authentication failed after maximum retry attempts.")
    return False


__all__ = ["authenticate", "load_token", "parse_token", "save_token", "validate_token"]
