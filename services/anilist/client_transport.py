"""AniList GraphQL transport and viewer query helpers."""

from models.models import AniListViewerInfo


def execute_query(
    client,
    query: str,
    variables: dict | None = None,
    token: str | None = None,
    *,
    settings_obj,
    httpx_module,
    json_module,
    log,
) -> dict:
    """Execute GraphQL query with retry on rate limit (429).

    Args:
        query: GraphQL query string
        variables: Query variables
        token: Optional token override (for validation)

    Returns:
        Query result data

    """
    from scrapers.plugins.utils import http_request_with_retry

    headers = {}
    use_token = token if token else client.token

    if use_token:
        headers["Authorization"] = f"Bearer {use_token}"

    not_found_exc = None
    try:
        response = http_request_with_retry(
            "POST",
            settings_obj.anilist.api_url,
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=settings_obj.anilist.request_timeout_seconds,
            follow_redirects=True,
        )
    except httpx_module.HTTPStatusError as exc:
        # AniList sinaliza "entrada inexistente" (ex.: MediaList de um anime
        # fora da lista do usuário) com 404, mas devolve um corpo GraphQL
        # válido cujo data traz nulls. Tratamos como resposta normal.
        if exc.response.status_code != 404:
            raise
        log.debug(f"AniList 404 tratado como resposta GraphQL: {exc.response.text}")
        response = exc.response
        not_found_exc = exc

    try:
        result = response.json()
    except json_module.JSONDecodeError:
        # 404 sem corpo GraphQL não veio do AniList (proxy, portal cativo):
        # o erro HTTP original é mais informativo que o de parsing.
        if not_found_exc is not None:
            raise not_found_exc from None
        raise

    # Num 404 os "errors" apenas descrevem o recurso ausente; o data com
    # nulls é a resposta legítima e quem chamou sabe interpretá-la.
    if "errors" in result and not (not_found_exc is not None and "data" in result):
        msg = f"GraphQL error: {result['errors']}"
        raise Exception(msg)

    return result.get("data")


def get_viewer_info(client) -> AniListViewerInfo | None:
    """Get authenticated user info with statistics."""
    if not client.is_authenticated():
        return None

    query = """
        query {
            Viewer {
                id
                name
                avatar {
                    medium
                    large
                }
                statistics {
                    anime {
                        count
                        episodesWatched
                        minutesWatched
                    }
                }
            }
        }
        """

    try:
        result = client._query(query)
        viewer_data = result.get("Viewer") if result else None
        if viewer_data:
            return AniListViewerInfo.model_validate(viewer_data)
        return None
    except Exception:
        return None


__all__ = ["execute_query", "get_viewer_info"]
