from unittest.mock import MagicMock


def html_response(html: str) -> MagicMock:
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    return response


def make_event(is_set: bool = False) -> MagicMock:
    event = MagicMock()
    event.is_set.return_value = is_set
    return event
