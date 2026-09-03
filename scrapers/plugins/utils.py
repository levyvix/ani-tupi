import re
import time

import httpx
from utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def http_request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    json: dict | None = None,
    data: bytes | str | None = None,
    params: dict | None = None,
    timeout: float = 30,
    follow_redirects: bool = True,
    max_retries: int = 3,
    backoff_base: float = 0.5,
    client: httpx.Client | None = None,
) -> httpx.Response:
    """Perform an HTTP request with retry/backoff for transient failures.

    Retries on rate limiting (HTTP 429), server errors (>= 500), timeouts,
    and transport/connection errors. For a 429 response the ``Retry-After``
    header is honored when present; otherwise exponential backoff is used.
    Other 4xx errors (except 429) raise immediately without retrying.

    Args:
        method: HTTP method (GET, POST, HEAD, PUT, DELETE, PATCH).
        url: The URL to request.
        headers: Optional request headers.
        json: Optional JSON payload (for POST, PUT, PATCH).
        data: Optional request body (bytes or str).
        params: Optional query parameters.
        timeout: Per-request timeout in seconds.
        follow_redirects: Whether to follow redirects.
        max_retries: Maximum number of retry attempts after the first request.
        backoff_base: Base seconds for exponential backoff.
        client: Optional ``httpx.Client`` to use.

    Returns:
        The successful ``httpx.Response`` (status verified via raise_for_status).
    """

    def _do_request() -> httpx.Response:
        if client is not None:
            return client.request(
                method,
                url,
                headers=headers,
                json=json,
                data=data,
                params=params,
                timeout=timeout,
                follow_redirects=follow_redirects,
            )
        return httpx.request(
            method,
            url,
            headers=headers,
            json=json,
            data=data,
            params=params,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = _do_request()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            delay = backoff_base * 2**attempt
            logger.debug(
                f"http_request_with_retry retry {attempt + 1}/{max_retries} for {method} {url} "
                f"(reason: {type(exc).__name__}), sleeping {delay:.2f}s"
            )
            time.sleep(delay)
            continue

        status = getattr(response, "status_code", None)
        if isinstance(status, int) and (status == 429 or status >= 500):
            last_exc = None
            if attempt >= max_retries:
                response.raise_for_status()
                return response
            if status == 429 and (retry_after := response.headers.get("Retry-After")):
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = backoff_base * 2**attempt
            else:
                delay = backoff_base * 2**attempt
            logger.debug(
                f"http_request_with_retry retry {attempt + 1}/{max_retries} for {method} {url} "
                f"(reason: HTTP {status}), sleeping {delay:.2f}s"
            )
            time.sleep(delay)
            continue

        response.raise_for_status()
        return response

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"http_request_with_retry exhausted retries for {method} {url}")


def http_get_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 30,
    follow_redirects: bool = True,
    max_retries: int = 3,
    backoff_base: float = 0.5,
    client: httpx.Client | None = None,
) -> httpx.Response:
    """Perform an HTTP GET with retry/backoff for transient failures.

    This is a convenience wrapper around http_request_with_retry for GET requests.
    See http_request_with_retry for details on retry behavior.

    Args:
        url: The URL to fetch.
        headers: Optional request headers.
        timeout: Per-request timeout in seconds.
        follow_redirects: Whether to follow redirects.
        max_retries: Maximum number of retry attempts after the first request.
        backoff_base: Base seconds for exponential backoff.
        client: Optional ``httpx.Client`` to use (mainly for testability).

    Returns:
        The successful ``httpx.Response`` (status verified via raise_for_status).
    """
    return http_request_with_retry(
        "GET",
        url,
        headers=headers,
        timeout=timeout,
        follow_redirects=follow_redirects,
        max_retries=max_retries,
        backoff_base=backoff_base,
        client=client,
    )


def http_head_with_fallback(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 5,
    fallback_to_get: bool = True,
    follow_redirects: bool = True,
    max_retries: int = 3,
    backoff_base: float = 0.5,
    client: httpx.Client | None = None,
) -> httpx.Response:
    """Perform an HTTP HEAD with fallback to GET for CDN rejections.

    Useful for checking URL validity/headers when some CDNs reject HEAD requests.
    First attempts HEAD; if that fails with 403/405, falls back to GET with
    Range header to minimize bandwidth.

    Args:
        url: The URL to check.
        headers: Optional request headers.
        timeout: Per-request timeout in seconds.
        fallback_to_get: If True and HEAD fails with 403/405, try GET.
        follow_redirects: Whether to follow redirects.
        max_retries: Maximum number of retry attempts.
        backoff_base: Base seconds for exponential backoff.
        client: Optional ``httpx.Client`` to use.

    Returns:
        The ``httpx.Response`` from HEAD or fallback GET (status verified).
    """
    try:
        return http_request_with_retry(
            "HEAD",
            url,
            headers=headers,
            timeout=timeout,
            follow_redirects=follow_redirects,
            max_retries=max_retries,
            backoff_base=backoff_base,
            client=client,
        )
    except httpx.HTTPStatusError as exc:
        if fallback_to_get and exc.response.status_code in (403, 405):
            logger.debug(f"HEAD failed with {exc.response.status_code} for {url}, trying GET...")
            fallback_headers = dict(headers) if headers else {}
            fallback_headers["Range"] = "bytes=0-1"
            return http_get_with_retry(
                url,
                headers=fallback_headers,
                timeout=timeout,
                follow_redirects=follow_redirects,
                max_retries=max_retries,
                backoff_base=backoff_base,
                client=client,
            )
        raise


def append_player_source(container: list, source: str) -> bool:
    """Append a candidate playback URL, skipping duplicates."""
    if source in container:
        return False
    container.append(source)
    return True


def store_player_source(container: list, event, source: str) -> bool:
    """Append a candidate playback URL.

    ``event`` is kept for plugin API compatibility; extraction no longer
    stops after the first URL so playback can try every candidate in order.
    """
    _ = event
    return append_player_source(container, source)


def extract_anivideo_hls(html: str) -> str | None:
    """Extract the direct HLS URL from an anivideo videohls.php `d=` parameter."""
    from urllib.parse import unquote

    match = re.search(r"https://api\.anivideo\.net/videohls\.php\?d=([^\"'<>&\s]+)", html)
    if not match:
        return None
    base = unquote(match.group(1).split("&")[0])
    if base.endswith(".m3u8"):
        return base
    if base.endswith(".mp4"):
        return f"{base}/index.m3u8"
    return base


def load_plugin(plugin_cls, register) -> None:
    """Register an anime plugin with the caller-supplied registration callback."""
    register(plugin_cls())
