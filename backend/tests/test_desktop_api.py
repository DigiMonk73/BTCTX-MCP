"""
What the Mac app's window can ask of the app (desktop/desktop_api.py,
pywebview's js_api), tested without pywebview.

The setup code: while the account still has the default login, the window's
login page reads it here to set the owner's own login (#151). A browser or
another program on the Mac has no window.pywebview, so it can't.
"""

import sys
from pathlib import Path

import pytest

from backend.services import first_run

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
from desktop_api import DesktopAPI  # noqa: E402

APP_URL = "http://127.0.0.1:8765"


class Window:
    """pywebview's window, as far as the API uses it."""

    def __init__(self, url: str | None):
        self.url = url

    def get_current_url(self) -> str | None:
        return self.url


def window_api(url: str | None = APP_URL + "/login") -> DesktopAPI:
    api = DesktopAPI(APP_URL)
    api._set_window(Window(url))
    return api


@pytest.fixture
def code():
    """A setup code file, as the backend makes while the login is the default."""
    yield first_run.ensure_code()
    first_run.clear_code()


def test_the_window_reads_the_setup_code(code):
    assert window_api().setup_code() == code
    assert window_api(APP_URL + "/").setup_code() == code


def test_no_code_without_the_file():
    """The login was set: the backend deleted the file."""
    first_run.clear_code()
    assert window_api().setup_code() is None


@pytest.mark.parametrize("url", [
    "https://example.com/login", "http://127.0.0.1:9999/login", "http://127.0.0.1:8765.example.com/",
    "file:///tmp/page.html", None,
])
def test_only_the_apps_own_pages_get_it(code, url):
    """pywebview gives the API to whatever page its window shows."""
    assert window_api(url).setup_code() is None


def test_no_code_before_the_window_exists(code):
    assert DesktopAPI(APP_URL).setup_code() is None
