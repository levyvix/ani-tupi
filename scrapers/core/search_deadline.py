"""Cooperative monotonic deadlines for anime source search operations.

``SearchRepository`` activates a deadline around each plugin's search call.
Plugins must use the shared HTTP retry helpers or ``bounded_timeout`` and
``sleep_with_search_deadline`` for external operations. If a search starts
nested worker threads, it must copy the current ``contextvars`` context so
those helpers can see the same deadline.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic, sleep
from typing import Iterator


class SearchDeadlineExceeded(TimeoutError):
    """Raised when a cooperative operation reaches the active search deadline."""


_active_search_deadline: ContextVar[float | None] = ContextVar(
    "active_search_deadline", default=None
)


@contextmanager
def use_search_deadline(deadline: float | None) -> Iterator[None]:
    """Make a source-search deadline available to helpers in the current thread."""
    token = _active_search_deadline.set(deadline)
    try:
        yield
    finally:
        _active_search_deadline.reset(token)


def current_search_deadline() -> float | None:
    """Return the active deadline, if this operation belongs to a source search."""
    return _active_search_deadline.get()


def remaining_search_time() -> float | None:
    """Return seconds remaining or ``None`` when no search deadline is active."""
    deadline = current_search_deadline()
    if deadline is None:
        return None

    remaining = deadline - monotonic()
    if remaining <= 0:
        raise SearchDeadlineExceeded("Anime source search deadline exceeded")
    return remaining


def bounded_timeout(max_timeout: float) -> float:
    """Bound an operation timeout by the active search's remaining budget."""
    remaining = remaining_search_time()
    return max_timeout if remaining is None else min(max_timeout, remaining)


def sleep_with_search_deadline(delay: float) -> None:
    """Sleep for a retry or poll interval without crossing the active deadline."""
    remaining = remaining_search_time()
    if remaining is None:
        sleep(delay)
        return

    if delay >= remaining:
        sleep(remaining)
        raise SearchDeadlineExceeded("Anime source search deadline exceeded")
    sleep(delay)
