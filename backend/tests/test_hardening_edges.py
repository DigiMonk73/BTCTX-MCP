"""
Edges kept closed around the request, the reports and the Mac window:
- A Content-Length is read only from ASCII digits (backend/body_limit.py):
  str.isdigit() also takes '²', which int() refuses, and int() reads no
  more than 4,300 digits.
- ReportLab opens no file and fetches nothing, even for markup that reached
  a Paragraph unescaped (backend/services/reports/safe_text.py): the
  escaping is the first line, this the second.
- The Mac window's Save dialog answers only the app's own pages
  (desktop/desktop_api.py), as its setup code does.
- The Docker image's server, which StartOS runs too, takes a client's
  address from its connection, never from an X-Forwarded-For header
  (Dockerfile: --no-proxy-headers).
"""

import asyncio
import base64
import io
import json
import sys
import types
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

import backend.services.reports.safe_text  # noqa: F401  (ReportLab's settings)
from backend.body_limit import MAX_BODY_BYTES, too_large
from backend.main import app
from backend.tests import test_desktop_api
from backend.tests.test_desktop_api import APP_URL
from desktop_api import NOT_THE_APP, DesktopAPI  # on the path test_desktop_api gives it

REPO = Path(__file__).resolve().parents[2]


def post_login(content_length: bytes, body: bytes) -> tuple[int, dict]:
    """POST /api/login straight over ASGI with this Content-Length header."""
    headers = [(b"host", b"testserver"), (b"content-type", b"application/json"),
               (b"content-length", content_length)]
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": "/api/login", "raw_path": b"/api/login", "query_string": b"",
        "root_path": "", "headers": headers, "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
    }
    sent, given = [], [False]

    async def receive():
        if given[0]:
            return {"type": "http.disconnect"}
        given[0] = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def collect(message):
        sent.append(message)

    asyncio.run(app(scope, receive, collect))
    start = next(m for m in sent if m["type"] == "http.response.start")
    answer = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], json.loads(answer or b"{}")


@pytest.mark.parametrize("length", ["²", "³", "¹²", "1²"])
def test_a_content_length_of_other_digits_is_none(fresh_app, length):
    """The body is then counted as it comes, as one sent in chunks."""
    body = json.dumps({"username": "nobody", "password": "x"}).encode()
    status, answer = post_login(length.encode("latin-1"), body)
    assert (status, answer) == (401, {"detail": "Invalid username or password."})


@pytest.mark.parametrize("length", ["9" * 19, "9" * 4301, "1" + "0" * 5000],
                         ids=["19 digits", "4301 digits", "5001 digits"])
def test_a_content_length_longer_than_any_body_is_over_the_limit(fresh_app, length):
    status, answer = post_login(length.encode(), b"{}")
    assert (status, answer) == (413, {"detail": too_large(MAX_BODY_BYTES)})


def test_leading_zeros_are_still_a_length(fresh_app):
    body = json.dumps({"username": "nobody", "password": "x"}).encode()
    status, _answer = post_login(("0" * 30 + str(len(body))).encode(), body)
    assert status == 401


@pytest.fixture
def local_image(tmp_path) -> Path:
    path = tmp_path / "local.png"
    Image.new("RGB", (4, 4), "red").save(path)
    return path


def build(markup: str) -> None:
    SimpleDocTemplate(io.BytesIO()).build([Paragraph(markup, getSampleStyleSheet()["Normal"])])


@pytest.mark.parametrize("src", ["{path}", "file://{path}"])
def test_reportlab_opens_no_local_file_even_for_unescaped_markup(local_image, src):
    with pytest.raises(OSError, match="Cannot open resource"):
        build(f'<img src="{src.format(path=local_image)}" width="4" height="4"/>')


def test_reportlab_still_builds_the_reports_text():
    """The standard fonts are built in: nothing to open for them."""
    out = io.BytesIO()
    SimpleDocTemplate(out).build([Paragraph("<b>Bold</b> <i>and</i> <font face='Courier'>plain</font>",
                                            getSampleStyleSheet()["Normal"])])
    assert out.getvalue().startswith(b"%PDF")


class Window(test_desktop_api.Window):
    """The window, with the Save dialog: it answers with save_to."""

    def __init__(self, url: str | None):
        super().__init__(url)
        self.dialogs = []
        self.save_to = None

    def create_file_dialog(self, *args, **kwargs):
        self.dialogs.append(kwargs)
        return (str(self.save_to),)


@pytest.fixture
def window(monkeypatch):
    """pywebview's window, the one the Save dialog is asked of."""
    shown = Window(APP_URL + "/reports")
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(windows=[shown], SAVE_DIALOG=30))
    return shown


def api_showing(window: Window) -> DesktopAPI:
    api = DesktopAPI(APP_URL)
    api._set_window(window)
    return api


@pytest.mark.parametrize("url", [
    "https://example.com/report", "http://127.0.0.1:9999/", "file:///tmp/page.html", None,
])
def test_the_save_dialog_answers_only_the_apps_own_pages(window, tmp_path, url):
    window.url, window.save_to = url, tmp_path / "report.pdf"
    result = api_showing(window).save_file("report.pdf", base64.b64encode(b"%PDF").decode())
    assert result == {"success": False, "error": NOT_THE_APP}
    assert window.dialogs == [] and not window.save_to.exists()


def test_the_apps_own_page_saves_its_file(window, tmp_path):
    window.save_to = tmp_path / "report.pdf"
    result = api_showing(window).save_file("report.pdf", base64.b64encode(b"%PDF").decode())
    assert result == {"success": True, "path": str(window.save_to)}
    assert window.save_to.read_bytes() == b"%PDF" and len(window.dialogs) == 1


def test_no_save_dialog_before_the_window_exists(window):
    assert DesktopAPI(APP_URL).save_file("report.pdf", "") == {"success": False, "error": NOT_THE_APP}
    assert window.dialogs == []


def test_the_docker_image_takes_no_client_address_from_headers():
    from uvicorn.main import main as uvicorn_cli

    cmd = next(line for line in (REPO / "Dockerfile").read_text().splitlines() if line.startswith("CMD "))
    args = json.loads(cmd[len("CMD "):])
    assert args[0] == "uvicorn"
    params = uvicorn_cli.make_context("uvicorn", args[1:]).params
    assert params["proxy_headers"] is False
    # StartOS runs this command; its README, which Start9's support agent
    # reads, quotes it
    assert f"`{' '.join(args)}`" in (REPO / "startos" / "README.md").read_text()
