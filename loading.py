"""Loading indicators for API calls using Rich spinners."""

from contextlib import contextmanager
from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live


@contextmanager
def loading(msg: str = "Carregando..."):
    """
    Context manager for displaying loading indicators during operations.

    Args:
        msg: The message to display alongside the spinner

    Usage:
        with loading("Buscando animes..."):
            results = fetch_anime()
    """
    console = Console()

    with Live(
        Spinner("dots", text=msg),
        console=console,
        refresh_per_second=12.5,
        transient=True,  # Spinner disappears after completion
    ):
        yield
