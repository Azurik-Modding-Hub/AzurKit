"""The app host (D732): the web page (``web/``) with the native engine
behind it (D866), in a pywebview window, or, where there is no webview
(Linux without pywebview's GTK or Qt extras, say), in the default browser.

Either way the page comes from a server on 127.0.0.1 (:func:`serve`) that
answers only a request that names it as the host (no DNS rebinding) and
carries this launch's token: in its URL the first time, then in the cookie
that answer sets. The cookie is named for the launch's port: browsers keep
cookies by host, not port, so a second launch's never replaces the first's.
The engine below never starts a thread; this host does, for the server.

The server is the page's engine too. ``host.json`` tells the page it is in
the app, with the catalog, AzurKit's version, the image to start from (the
one the last build read, remembered in platformdirs' config folder, else a
release's own image), whether there are file dialogs (the window's), the
site's address, which its share links name (:data:`SITE`, D884), and the
theme the player last picked (dark until they pick light, D897; ``POST
api/theme`` ``{"theme"}`` remembers it there too: the page's address, and
so its storage, is new each launch).
``POST api/build`` ``{"iso", "packs", "xbr"}`` plans the build (``sdk.image``: the
report, the size, and where to save it: the Downloads folder, under the
site's download's name), and ``POST api/save`` ``{"recipe", "out"}`` writes it
(``sdk.build``), never over an existing file but the one the save dialog
chose (it asked first), with ``GET api/progress`` and ``POST api/cancel``.
``POST api/vanilla`` ``{"iso"}`` reads the image's own values of the
sliders at its XBE's sites (``sdk.vanilla``), or, when the image is an
AzurKit build, ``{"opened": its recipe}`` (``sdk.open_build`` of the files
it changed).
``POST api/preset`` ``{"recipe", "report"}`` makes a share link's fragment
(``sdk.preset_encode``) and ``POST api/decode`` ``{"text"}`` reads one
(``sdk.preset_decode``).
``POST api/choose`` ``{"kind": "iso" | "out", "path"}`` opens the window's
file dialog. A POST is JSON from the page's own origin. A refusal (the
sdk's) comes back as ``{"refused": message}``; one build or save runs at a
time. Closing the app cancels either (:meth:`Server.quit`, AZ-823) and
never waits on a build.

The tests run with :data:`NO_WINDOW` set (``tests/conftest.py``): the owner
works on this screen (D839), so there :func:`main` refuses at once, before it
serves anything or opens a window or a browser tab. ``serve`` (``python -m
azurkit serve``, the frozen app's ``AzurKit serve``) opens neither in any
mode: it prints the page's address and serves until its input ends.
"""

from __future__ import annotations

import contextlib
import glob
import hmac
import http.server
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

from azurkit import __version__, sdk
from azurkit.core import gate

SITE = "https://azurik-modding-hub.github.io/AzurKit/"   # the site (D884), which the app's share links open

PAGE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "web"   # the frozen app's, else the checkout's
NO_WINDOW = "AZURKIT_NO_WINDOW"   # set: main() opens nothing (the tests' mode)
MAX_BODY = 1 << 20
IMAGES = ("Disc images (*.iso;*.xiso)",)   # the open dialog's filter (another name can be typed in)
# text_select: pywebview otherwise injects a <style> to stop selection, which the page's CSP refuses;
# background_color: the page's dark ground (D897), which the window shows until the page draws
WINDOW = {"title": "AzurKit", "width": 1100, "height": 820, "text_select": True, "background_color": "#0d1117"}
THEMES = ("dark", "light")   # the page's (D897): dark until the player picks light, which the app remembers
QUIT_WAIT = 1.5   # seconds a close waits, in all, for a cancelled save to remove its part file (AZ-823)
QUITTING = "AzurKit is quitting: nothing was written"


class Cancelled(Exception):
    """The page cancelled the save."""


def _config() -> Path:
    from platformdirs import user_config_path
    return user_config_path("AzurKit", appauthor=False) / "app.json"


def _kept() -> dict:
    """What the app remembers (``{"iso", "theme"}``), else nothing."""
    try:
        kept = json.loads(_config().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return kept if isinstance(kept, dict) else {}


def _start_image() -> str:
    """The image the last build read, else a release's own image, else ``""``."""
    last = _kept().get("iso")
    if isinstance(last, str) and Path(last).is_file():
        return last
    return str(next(filter(None, map(gate.find, gate.RELEASES)), ""))


def _theme() -> str:
    """The theme the player last picked, else dark (D897)."""
    return theme if (theme := _kept().get("theme")) in THEMES else THEMES[0]


def _remember(**kept: str) -> None:
    try:
        _config().parent.mkdir(parents=True, exist_ok=True)
        _config().write_text(json.dumps(_kept() | kept) + "\n", encoding="utf-8")
    except OSError:   # remembering is a convenience: a build doesn't fail for it
        pass


def _set_theme(body: dict) -> dict:
    """``api/theme``: remember the theme the page's toggle picked."""
    if (theme := body.get("theme")) not in THEMES:
        raise ValueError(f"theme: {theme!r} is none of {', '.join(THEMES)}")
    _remember(theme=theme)
    return {}


def _path(given: object, what: str) -> Path:
    """``given`` (``~`` expanded) as an absolute path; ``ValueError`` otherwise."""
    if not isinstance(given, str) or not given.strip():
        raise ValueError(f"name the {what}'s path")
    path = Path(given.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{given}: give the {what}'s full path")
    return path


class Server(http.server.ThreadingHTTPServer):
    """The page's server and engine, on its own thread. :attr:`url` opens it."""

    daemon_threads = True

    def __init__(self, page: Path):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.page, self.token = page.resolve(), secrets.token_urlsafe(32)
        self.host, self.cookie = f"127.0.0.1:{self.server_port}", f"azurkit-token-{self.server_port}"
        self.url = f"http://{self.host}/?token={self.token}"
        self.window = None                  # the pywebview window, once there is one: its file dialogs
        self.busy = threading.Lock()        # one build or save at a time
        self.writing = threading.Lock()     # held by a save, which quit() waits on (never a build)
        self.out: Path | None = None        # where the save in flight writes
        self.progress = (0, 0)
        self.cancelled = threading.Event()
        self.quitting = False               # set by quit(), before it cancels: no build or save starts after it
        self.deadline: float | None = None  # quit()'s first call's, plus QUIT_WAIT
        self.chosen: Path | None = None     # the save dialog's last answer, which it asked before replacing
        threading.Thread(target=self.serve_forever, name="azurkit-page", daemon=True).start()

    def quit(self) -> None:
        """Cancel a build or a save in flight, within :data:`QUIT_WAIT`
        (AZ-823): the window's closing hook (its close button, and Cmd-Q,
        after which no ``finally`` runs) and :meth:`close`. A build writes
        nothing, so this never waits on one: its answer is refused. A save
        is waited on until it has removed its part file (D35), as its thread
        is a daemon, which the interpreter's exit would kill mid-write; if
        it hasn't by then (a stalled disk), its part file is removed here.
        A build or save that takes ``busy`` after ``quitting`` is set
        refuses; a save that took it before sees ``cancelled``, set after
        ``quitting``, before its part file is made and after each chunk."""
        self.quitting = True
        self.cancelled.set()
        self.deadline = self.deadline or time.monotonic() + QUIT_WAIT
        if self.writing.acquire(timeout=max(0.0, self.deadline - time.monotonic())):
            self.writing.release()
        elif (out := self.out) is not None:
            for part in out.parent.glob(f"{glob.escape(out.name)}.*.part"):   # iso.pack's
                with contextlib.suppress(OSError):   # still open on Windows: nothing more to do here
                    part.unlink(missing_ok=True)

    def close(self) -> None:
        self.quit()
        self.shutdown()
        self.server_close()

    def host_info(self) -> dict:
        return {"engine": "app", "version": __version__, "catalog": sdk.catalog(), "iso": _start_image(),
                "dialogs": self.window is not None, "site": SITE, "theme": _theme()}

    def build(self, body: dict) -> dict:
        recipe = {"iso": str(_path(body.get("iso"), "image")), "packs": body.get("packs", {})}
        if body.get("xbr"):
            recipe["xbr"] = body["xbr"]
        with self.busy:
            if self.quitting:
                raise ValueError(QUITTING)
            made, report = sdk.image(recipe)
        if self.quitting:   # closed while it built (AZ-823)
            raise ValueError(QUITTING)
        _remember(iso=recipe["iso"])
        from platformdirs import user_downloads_path
        iso = Path(recipe["iso"])
        stem = iso.stem if iso.suffix.lower() in (".iso", ".xiso") else iso.name   # the site's download's name
        return {"report": report, "size": made.size, "recipe": recipe,
                "out": str(user_downloads_path() / f"{stem} (AzurKit).iso")}

    def save(self, body: dict) -> dict:
        recipe, out = body.get("recipe"), _path(body.get("out"), "saved image")
        if out.exists() and out != self.chosen:
            raise ValueError(f"{out} exists: choose another name, or delete it first")

        def progress(done: int, total: int) -> None:
            self.progress = (done, total)
            if self.cancelled.is_set():
                raise Cancelled
        with self.busy, self.writing:
            self.cancelled.clear()   # before the check: a quit after it still cancels this save
            if self.quitting:
                raise ValueError(QUITTING)
            self.progress, self.out = (0, 0), out
            try:
                return {"saved": sdk.build(recipe, str(out), progress=progress)}
            except Cancelled:
                raise ValueError("Cancelled: nothing was written") from None

    def choose(self, body: dict) -> dict:
        """The window's file dialog: an image to read, or where to save."""
        import webview
        given = Path(body["path"]).expanduser() if isinstance(body.get("path"), str) and body["path"] else None
        folder = str(given.parent) if given else ""
        if body.get("kind") == "out":
            picked = self.window.create_file_dialog(webview.FileDialog.SAVE, directory=folder,
                                                    save_filename=given.name if given else "")
        else:
            picked = self.window.create_file_dialog(webview.FileDialog.OPEN, directory=folder, file_types=IMAGES)
        if isinstance(picked, (list, tuple)):
            picked = picked[0] if picked else None
        if picked and body.get("kind") == "out":
            self.chosen = Path(str(picked))
        return {"path": str(picked) if picked else None}


class _Handler(http.server.BaseHTTPRequestHandler):
    server: Server

    def _url(self) -> urllib.parse.SplitResult | None:
        """The request's URL when it carries this launch's token and names
        this server as its host, else ``None``."""
        url = urllib.parse.urlsplit(self.path)
        given = urllib.parse.parse_qs(url.query).get("token", [""])[0]
        cookie = next((v for k, _, v in (c.strip().partition("=") for c in self.headers.get("Cookie", "").split(";"))
                       if k == self.server.cookie), "")
        token = self.server.token.encode()
        if self.headers.get("Host") != self.server.host or not (
                hmac.compare_digest(given.encode(), token) or hmac.compare_digest(cookie.encode(), token)):
            return None
        return url

    def _send(self, data: bytes, kind: str, cookie: bool = False) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie",
                             f"{self.server.cookie}={self.server.token}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, value: dict) -> None:
        self._send(json.dumps(value).encode(), "application/json")

    def do_GET(self) -> None:
        if (url := self._url()) is None:
            return self.send_error(403)
        if url.path == "/host.json":
            return self._json(self.server.host_info())
        if url.path == "/api/progress":
            done, total = self.server.progress
            return self._json({"done": done, "total": total})
        try:
            file = (self.server.page / (urllib.parse.unquote(url.path).lstrip("/") or "index.html")).resolve()
            data = file.read_bytes() if file.is_relative_to(self.server.page) and file.is_file() else None
        except (OSError, ValueError):   # a NUL in the path, say
            data = None
        if data is None:
            return self.send_error(404)
        self._send(data, mimetypes.guess_type(file.name)[0] or "application/octet-stream",
                   cookie="token" in urllib.parse.parse_qs(url.query))

    def do_POST(self) -> None:
        if (url := self._url()) is None or self.headers.get("Origin", f"http://{self.server.host}") != (
                f"http://{self.server.host}") or self.headers.get_content_type() != "application/json":
            return self.send_error(403)
        call = {"/api/build": self.server.build, "/api/save": self.server.save, "/api/vanilla": _vanilla,
                "/api/preset": lambda body: {"fragment": sdk.preset_encode(body.get("recipe"), body.get("report"))},
                "/api/decode": lambda body: {"preset": sdk.preset_decode(body.get("text"))},
                "/api/theme": _set_theme,
                "/api/cancel": lambda body: self.server.cancelled.set() or {}}.get(url.path)
        if url.path == "/api/choose" and self.server.window is not None:
            call = self.server.choose
        size = int(self.headers.get("Content-Length") or 0)
        if call is None or not 0 < size <= MAX_BODY:
            return self.send_error(404 if call is None else 413)
        try:
            body = json.loads(self.rfile.read(size))
        except ValueError:
            return self.send_error(400)
        if not isinstance(body, dict):
            return self.send_error(400)
        try:
            reply = call(body)
        except (OSError, ValueError) as exc:   # the sdk's refusals name what and why, never game bytes
            reply = {"refused": str(exc)}
        self._json(reply)

    def log_message(self, *args) -> None:   # the token is in the first request's line
        pass


def _vanilla(body: dict) -> dict:
    """``api/vanilla``: the image's own slider values, or an AzurKit build's recipe."""
    iso = str(_path(body.get("iso"), "image"))
    try:
        return sdk.vanilla(iso)
    except gate.NotVanillaError as exc:
        try:
            return {"opened": sdk.open_build(iso, whole=False)}
        except (OSError, ValueError):
            raise exc from None


def serve(page: Path = PAGE) -> Server:
    """Serve ``page`` (a folder holding ``index.html``) on 127.0.0.1 with a
    fresh token, on a thread; :meth:`Server.close` stops it."""
    if not (page / "index.html").is_file():
        raise FileNotFoundError(f"{page}: no index.html (the page)")
    return Server(page)


def _window(server: Server) -> bool:
    """Show the page in a pywebview window until it closes; ``False`` when
    there is no webview here."""
    try:
        import webview
        from webview.errors import WebViewException
    except ImportError:
        return False
    try:
        server.window = webview.create_window(url=server.url, **WINDOW)
        server.window.events.closing += server.quit
        webview.start(private_mode=True)
    except WebViewException:
        server.window = None
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    """Open the page: in a window, else in the default browser (served until
    Ctrl-C); exit 1 at once when :data:`NO_WINDOW` is set. ``["serve"]``
    opens neither: it prints the page's address and serves until its input
    ends (Ctrl-D) or Ctrl-C."""
    argv = list(argv or [])
    if argv not in ([], ["serve"]):
        print("usage: AzurKit [serve]", file=sys.stderr)
        return 2
    if not argv and os.environ.get(NO_WINDOW):
        print(f"azurkit: no window while {NO_WINDOW} is set (the tests' mode)", file=sys.stderr)
        return 1
    try:
        server = serve()
    except FileNotFoundError as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    try:
        if argv:
            print(server.url, flush=True)
            sys.stdin.read()
        elif not _window(server):
            print(f"AzurKit: the page is at {server.url} (Ctrl-C quits)", flush=True)
            webbrowser.open(server.url)
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0
