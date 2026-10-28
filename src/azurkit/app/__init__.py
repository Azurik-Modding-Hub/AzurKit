"""The app host (D732): the web page (``web/``) in a pywebview window, or,
where there is no webview (Linux without pywebview's GTK or Qt extras, say),
in the default browser.

Either way the page comes from a server on 127.0.0.1 (:func:`serve`) that
answers only a request that names it as the host (no DNS rebinding) and
carries this launch's token: in its URL the first time, then in the cookie
that answer sets. The cookie is named for the launch's port: browsers keep
cookies by host, not port, so a second launch's never replaces the first's.
The engine below never starts a thread; this host does, for the server.

The tests run with :data:`NO_WINDOW` set (``tests/conftest.py``): the owner
works on this screen (D839), so there :func:`main` refuses at once, before it
serves anything or opens a window or a browser tab.
"""

from __future__ import annotations

import hmac
import http.server
import mimetypes
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

PAGE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "web"   # the frozen app's, else the checkout's
NO_WINDOW = "AZURKIT_NO_WINDOW"   # set: main() opens nothing (the tests' mode)


class Server(http.server.ThreadingHTTPServer):
    """The page's server, on its own thread. :attr:`url` opens it."""

    daemon_threads = True

    def __init__(self, page: Path):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.page, self.token = page.resolve(), secrets.token_urlsafe(32)
        self.host, self.cookie = f"127.0.0.1:{self.server_port}", f"azurkit-token-{self.server_port}"
        self.url = f"http://{self.host}/?token={self.token}"
        threading.Thread(target=self.serve_forever, name="azurkit-page", daemon=True).start()

    def close(self) -> None:
        self.shutdown()
        self.server_close()


class _Handler(http.server.BaseHTTPRequestHandler):
    server: Server

    def do_GET(self) -> None:
        url = urllib.parse.urlsplit(self.path)
        given = urllib.parse.parse_qs(url.query).get("token", [""])[0]
        cookie = next((v for k, _, v in (c.strip().partition("=") for c in self.headers.get("Cookie", "").split(";"))
                       if k == self.server.cookie), "")
        token = self.server.token.encode()
        if self.headers.get("Host") != self.server.host or not (
                hmac.compare_digest(given.encode(), token) or hmac.compare_digest(cookie.encode(), token)):
            return self.send_error(403)
        try:
            file = (self.server.page / (urllib.parse.unquote(url.path).lstrip("/") or "index.html")).resolve()
            data = file.read_bytes() if file.is_relative_to(self.server.page) and file.is_file() else None
        except (OSError, ValueError):   # a NUL in the path, say
            data = None
        if data is None:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if given:
            self.send_header("Set-Cookie",
                             f"{self.server.cookie}={self.server.token}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:   # the token is in the first request's line
        pass


def serve(page: Path = PAGE) -> Server:
    """Serve ``page`` (a folder holding ``index.html``) on 127.0.0.1 with a
    fresh token, on a thread; :meth:`Server.close` stops it."""
    if not (page / "index.html").is_file():
        raise FileNotFoundError(f"{page}: no index.html (the page)")
    return Server(page)


def _window(url: str) -> bool:
    """Show ``url`` in a pywebview window until it closes; ``False`` when
    there is no webview here."""
    try:
        import webview
        from webview.errors import WebViewException
    except ImportError:
        return False
    try:
        webview.create_window("AzurKit", url, width=1100, height=760)
        webview.start(private_mode=True)
    except WebViewException:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    """Open the page: in a window, else in the default browser (served until
    Ctrl-C); exit 1 at once when :data:`NO_WINDOW` is set."""
    if os.environ.get(NO_WINDOW):
        print(f"azurkit: no window while {NO_WINDOW} is set (the tests' mode)", file=sys.stderr)
        return 1
    try:
        server = serve()
    except FileNotFoundError as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    try:
        if not _window(server.url):
            print(f"AzurKit: the page is at {server.url} (Ctrl-C quits)")
            webbrowser.open(server.url)
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0
