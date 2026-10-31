"""The app host (D732): the web page (``web/``) with the native engine
behind it (D866), in a pywebview window, or, where there is no webview
(Linux without pywebview's GTK or Qt extras, say), in the default browser.

Either way the page comes from a server on 127.0.0.1 (:func:`serve`) that
answers only a request that names it as the host (no DNS rebinding) and
carries this launch's token: in its URL the first time, then in the cookie
that answer sets. The cookie is named for the launch's port: browsers keep
cookies by host, not port, so a second launch's never replaces the first's.
The engine below never starts a thread; this host does, for the server,
and the app's engine process (:mod:`.engine`).

The server is the page's engine too. ``host.json`` tells the page it is in
the app, with the catalog, AzurKit's version, the image to start from (the
one the last build read, remembered in platformdirs' config folder, else a
release's own image), whether there are file dialogs (the window's), the
site's address, which its share links name (:data:`SITE`, D884), and the
theme the player last picked (dark until they pick light, D897; ``POST
api/theme`` ``{"theme"}`` remembers it there too: the page's address, and
so its storage, is new each launch) and the page's setup as it was last
left (D915: the packs ticked, the settings changed and a loaded recipe's
config.xbr cells, never the image or anything read from it; ``POST
api/setup`` ``{"setup"}`` remembers it, ``null`` forgets it, and ``POST
api/restore`` ``{"setup"}`` gives back what still applies,
``sdk.restore``). The page's ``theme.js``, which sets
the theme before its first paint, is the server's own (:func:`_theme_js`),
and the window opens on that theme's ground (:data:`GROUNDS`), so a player
who picked light never sees a dark first frame.
``POST api/build`` ``{"iso", "packs", "xbr", "randomizer"}`` plans the build (``sdk.image``: the
report, the size, the build's id, and where to save it: the Downloads
folder, under the site's download's name), and ``POST api/save``
``{"recipe", "out", "build"}`` writes it: the image that build made, kept
and hashed in the engine from the moment it was made (``sdk.save``), else,
when the engine keeps it no more or its input changed, the recipe built
again (``sdk.build``); never over an existing file but the one the save
dialog chose (it asked first), with ``GET api/progress`` (the save's
``core.progress`` record) and ``POST api/cancel``.
Both run in the engine (:mod:`.engine`): ``serve``'s on the request's own
thread, the app's (:func:`main`) in a process of its own, with the seed's
plan and the Characters tab's pictures and G4 match, so the server's own
answers never wait on a build, and Cancel stops a build at once.
``POST api/spoiler`` ``{"out"}`` writes the last randomized build's spoiler
there, on the same terms. ``POST api/randomizer`` ``{"given"}`` gives what
the Randomizer tab shows (``sdk.randomizer_settings``).
``POST api/settings_file`` ``{"out", "settings"}`` writes the Randomizer
tab's settings as a settings file (D144; ``out`` null: ``settings.toml``
in the Downloads folder), never over an existing file but one the save
dialog chose.
``POST api/tracker`` ``{"given"}`` gives what the item tracker shows
(``sdk.tracker``); with Live on for its plan, it first merges what Live
read since the last ask (:mod:`.live`: the spots the game shows taken, the
element levels it holds) and gives Live's status and where it saw the
player (``live``). ``POST api/live`` ``{"on", "plan", "marks",
"endpoints"}`` turns Live on for a plan (reading the first of the
endpoints that answers as xemu: the fork's shared RAM, or QMP; Modkit's
grammar, empty for the defaults) or off. ``POST api/plan`` ``{"recipe"}`` plans a seed to track
(``sdk.plan``), and ``POST api/tracked`` ``{"tracker"}`` remembers the
plan last tracked and the marks of the last plans (``host.json``'s
``tracker``: the randomizer's names and numbers, never the image's).
``POST api/art`` ``{"iso", "draw"}`` says which of the tracker's pictures
are drawn (:mod:`.art`: its maps and icons, drawn from the player's image
into the user cache folder, Step 4.2c3), and with ``draw`` draws the
rest from ``iso`` on a thread; ``GET art/<version>/<name>`` serves one.
Live (``api/live``'s ``gems``) reads the gem spots too while the tracker
shows them (R1.43).
``POST api/vanilla`` ``{"iso"}`` reads the image's own values of the
sliders at its XBE's sites (``sdk.vanilla``), or, when the image is an
AzurKit build, ``{"opened": its recipe}`` (``sdk.open_build`` of the files
it changed).
``POST api/preset`` ``{"recipe", "report"}`` makes a share link's fragment
(``sdk.preset_encode``) and ``POST api/decode`` ``{"text"}`` reads one
(``sdk.preset_decode``).
The Characters tab's calls (Step 4.3d): ``POST api/pickers`` ``{"given"}``
(``sdk.pickers``), ``api/preview`` and ``api/match`` ``{"recipe"}`` (the
pictures as base64 PNG), and Azurik-Custom-Content's ``api/content``
``{"source"}`` (``sdk.content``) and ``api/install`` ``{"id", "source"}``
(``sdk.content_install``, into the content folder); ``api/content_source``
``{"source"}`` remembers the tab's Content from (``null``: the default),
which ``host.json``'s ``content_source`` gives the next page.
``POST api/choose`` ``{"kind": "iso" | "out", "path"}`` opens the window's
file dialog. A POST is JSON from the page's own origin. A refusal (the
sdk's) comes back as ``{"refused": message}``; one build or save runs at a
time. Closing the app cancels either (:meth:`Server.quit`, AZ-823) and
never waits on a build (the app's engine process: it ends it).

The app (:func:`main`) keeps the images it checked and the swap's answers
across launches in platformdirs' cache folder (:mod:`.swapcache`), so an
image picked again isn't hashed again and a body dressed once isn't
dressed again; ``serve`` alone (the tests') keeps nothing past its process.

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
import math
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
from azurkit.edits import xbr
from azurkit.tools import randomizer
from azurkit.tools.randomizer import tracking
from azurkit.tools.randomizer.live import link

from . import art as pictures
from . import engine as engines
from . import live, swapcache
from .engine import Cancelled

SITE = "https://azurik-modding-hub.github.io/AzurKit/"   # the site (D884), which the app's share links open

PAGE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "web"   # the frozen app's, else the checkout's
NO_WINDOW = "AZURKIT_NO_WINDOW"   # set: main() opens nothing (the tests' mode)
MAX_BODY = 1 << 20
IMAGES = ("Disc images (*.iso;*.xiso)",)   # the open dialog's filter (another name can be typed in)
# text_select: pywebview otherwise injects a <style> to stop selection, which the page's CSP refuses
WINDOW = {"title": "AzurKit", "width": 1100, "height": 820, "text_select": True}
# The page's themes (D897: dark until the player picks light, which the app remembers) and each one's ground
# (web/app.css's --bg), which the window shows until the page draws
GROUNDS = {"dark": "#0d1117", "light": "#e8ecf1"}
THEMES = tuple(GROUNDS)
QUIT_WAIT = 1.5   # seconds a close waits, in all, for a cancelled save to remove its part file (AZ-823)
QUITTING = "AzurKit is quitting: nothing was written"
IDLE = {"stage": None, "label": "", "done": 0, "total": 0, "percent": None}   # api/progress with nothing in flight


def _config() -> Path:
    from platformdirs import user_config_path
    return user_config_path("AzurKit", appauthor=False) / "app.json"


def _kept() -> dict:
    """What the app remembers (``{"iso", "theme", "setup"}``), else nothing."""
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


def _theme_js() -> bytes:
    """The app's ``theme.js`` (the site's reads the browser's storage): it
    sets the remembered theme before the page's first paint."""
    return f'document.documentElement.dataset.theme = "{_theme()}";\n'.encode()


_REMEMBERING = threading.Lock()   # a build's thread and the page's calls each remember a part of the config


def _remember(**kept: object) -> None:
    """Remember ``kept`` beside what the config holds (``None`` forgets a
    key), written whole or not at all."""
    try:
        with _REMEMBERING:
            _config().parent.mkdir(parents=True, exist_ok=True)
            part = _config().with_suffix(".json.part")
            part.write_text(json.dumps({k: v for k, v in (_kept() | kept).items() if v is not None}) + "\n",
                            encoding="utf-8")
            part.replace(_config())
    except OSError:   # remembering is a convenience: a build doesn't fail for it
        pass


def _set_theme(body: dict) -> dict:
    """``api/theme``: remember the theme the page's toggle picked."""
    if (theme := body.get("theme")) not in THEMES:
        raise ValueError(f"theme: {theme!r} is none of {', '.join(THEMES)}")
    _remember(theme=theme)
    return {}


def _set_setup(body: dict) -> dict:
    """``api/setup``: remember the page's setup (D915), or forget it
    (``null``): pack and setting names (identifiers, so never a path), their
    numbers and config.xbr ``set`` operations only, so never a
    ``replace_bytes``' bytes. A ``set``'s table, entity, prop and text
    value are free strings (config.xbr's names hold spaces; text cells hold
    text), checked by :func:`xbr.normalize` alone: the page fills them from
    the catalog and never puts the image's path in one. The Randomizer
    tab's (``randomizer``: on, the seed the player typed, the settings and
    the obsidian cost) is checked as a build checks it
    (``tools.randomizer.remembered``), and the Characters tab's
    (``character``) as a share link carries one: names and numbers."""
    if (setup := body.get("setup")) is not None:
        if not (isinstance(setup, dict) and set(setup) <= set(sdk.SETUP)):
            raise ValueError(f"setup: an object of {', '.join(sdk.SETUP)} only, or null")
        ticked, values, ops = setup.get("ticked", []), setup.get("values", {}), setup.get("xbr", [])
        if not (isinstance(ticked, list) and all(map(_named, ticked))):
            raise ValueError("setup: ticked holds pack names only")
        if not (isinstance(values, dict) and all(_named(pack) and _numbers(settings) for pack, settings in values.items())):
            raise ValueError("setup: values holds {pack: {setting: number}} only")
        if not (isinstance(ops, list) and all(isinstance(op, dict) and op.get("op") == "set" for op in ops)):
            raise ValueError("setup: xbr holds config.xbr set operations only (Q174)")
        xbr.normalize(ops)   # each set with exactly its keys, else refused by name
        if "randomizer" in setup:
            try:
                randomizer.remembered(setup["randomizer"])
            except ValueError as exc:
                raise ValueError(f"setup: randomizer: {exc}") from None
        if "character" in setup and (lost := sdk.restore({"character": setup["character"]})["dropped"]):
            raise ValueError(f"setup: {lost[0]}")   # by name and numbers, never a recipe file's path
    _remember(setup=setup)
    return {}


TRACKED = 20   # the plans whose marks the app keeps (the page's KEEP)


def _set_tracked(body: dict) -> dict:
    """``api/tracked``: remember the tracker's plan last tracked (a plan
    file's object: the randomizer's names and numbers) and the marks of
    the last :data:`TRACKED` plans (``{sha256: marks}``), or forget them
    (``null``); marks the tracker can't read are refused by name."""
    if (kept := body.get("tracker")) is not None:
        if not (isinstance(kept, dict) and set(kept) <= {"plan", "marks", "endpoints", "gems"}
                and kept.get("gems", False) in (True, False)):
            raise ValueError("tracker: an object of plan, marks, endpoints and gems only, or null")
        if not isinstance(endpoints := kept.get("endpoints", ""), str):
            raise ValueError("tracker: endpoints is a list's text")
        try:
            link.parse(endpoints)
        except ValueError as exc:
            raise ValueError(f"tracker: endpoints: {exc}") from None
        plan, marks = kept.get("plan"), kept.get("marks", {})
        if not (plan is None or (isinstance(plan, dict) and isinstance(plan.get("sha256"), str))):
            raise ValueError("tracker: plan is a plan file's object")
        if not (isinstance(marks, dict) and len(marks) <= TRACKED and all(isinstance(k, str) for k in marks)):
            raise ValueError(f"tracker: marks is {{plan sha256: marks}} of at most {TRACKED} plans")
        for each in marks.values():
            tracking.marks_of(each)
    _remember(tracker=kept)
    return {}


def _set_source(body: dict) -> dict:
    """``api/content_source``: remember the Characters tab's Content from
    (an http(s) URL or a folder's path, as ``sdk.content`` reads it), or
    forget it (``null``: the default)."""
    if (source := body.get("source")) is not None:
        if not (isinstance(source, str) and len(source) <= 2048 and (
                urllib.parse.urlsplit(source.strip()).scheme in ("http", "https")
                or Path(source.strip()).expanduser().is_absolute())):
            raise ValueError("content_source: an http(s) URL or a folder's full path")
    _remember(content_source=source)
    return {}


def _named(name: object) -> bool:
    """``name`` is a pack's or a setting's name (an identifier: never a path)."""
    return isinstance(name, str) and name.isidentifier()


def _numbers(settings: object) -> bool:
    """``settings`` is ``{setting: a finite number}``."""
    return isinstance(settings, dict) and all(_named(name) and type(value) in (int, float) and math.isfinite(value)
                                              for name, value in settings.items())


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

    def __init__(self, page: Path, engine: engines.Here | engines.Spawned | None = None):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.engine = engine or engines.Here()   # where builds, saves, plans and pictures run
        self.page, self.token = page.resolve(), secrets.token_urlsafe(32)
        self.host, self.cookie = f"127.0.0.1:{self.server_port}", f"azurkit-token-{self.server_port}"
        self.url = f"http://{self.host}/?token={self.token}"
        self.window = None                  # the pywebview window, once there is one: its file dialogs
        self.busy = threading.Lock()        # one build or save at a time
        self.writing = threading.Lock()     # held by a save, which quit() waits on (never a build)
        self.out: Path | None = None        # where the save in flight writes
        self.progress = IDLE                # the save's last core.progress record
        self.cancelled = threading.Event()
        self.quitting = False               # set by quit(), before it cancels: no build or save starts after it
        self.deadline: float | None = None  # quit()'s first call's, plus QUIT_WAIT
        self.chosen: Path | None = None     # the save dialog's last answer, which it asked before replacing
        self.spoiler: str | None = None     # the last randomized build's spoiler (api/spoiler)
        self.source: Path | None = None     # and the image it was built from, which it never replaces (D36)
        self.tracking = threading.Lock()    # the tracker the page's asks and Live's feed share
        self.feed: live.Feed | None = None  # Live, while it is on
        self.drawing = pictures.Drawing()   # the tracker's maps and icons, in the user cache folder
        threading.Thread(target=self.serve_forever, name="azurkit-page", daemon=True).start()

    def quit(self) -> None:
        """Cancel a build or a save in flight, within :data:`QUIT_WAIT`
        (AZ-823): the window's closing hook (its close button, and Cmd-Q,
        after which no ``finally`` runs) and :meth:`close`. A build writes
        nothing, so this never waits on one: its answer is refused (the
        app's engine process, which ends here, ends it). A save
        is waited on until it has removed its part file (D35), as its thread
        is a daemon, which the interpreter's exit would kill mid-write; if
        it hasn't by then (a stalled disk), its part file is removed here.
        A build or save that takes ``busy`` after ``quitting`` is set
        refuses; a save that took it before sees ``cancelled``, set after
        ``quitting``, before its part file is made and after each chunk."""
        self.quitting = True
        self.cancelled.set()
        self.drawing.stop()
        if (feed := self.feed) is not None:
            feed.stop()
        self.deadline = self.deadline or time.monotonic() + QUIT_WAIT
        if saved := self.writing.acquire(timeout=max(0.0, self.deadline - time.monotonic())):
            self.writing.release()
        self.engine.close()   # the app's engine process ends here, before a stalled save's part file goes
        if not saved and (out := self.out) is not None:
            _unpart(out)

    def close(self) -> None:
        self.quit()
        self.shutdown()
        self.server_close()

    def cancel(self) -> dict:
        """``api/cancel``: a save stops at its next chunk; a build in the
        app's engine process at once (it ends, and another starts)."""
        self.cancelled.set()
        self.engine.cancel()
        return {}

    def host_info(self) -> dict:
        return {"engine": "app", "version": __version__, "catalog": sdk.catalog(), "iso": _start_image(),
                "dialogs": self.window is not None, "site": SITE, "theme": _theme(),
                "setup": _kept().get("setup"), "tracker": _kept().get("tracker"),
                "content_source": _kept().get("content_source")}

    def build(self, body: dict) -> dict:
        recipe = {"iso": str(_path(body.get("iso"), "image")), "packs": body.get("packs", {})}
        recipe |= {key: body[key] for key in ("xbr", "randomizer", "character") if body.get(key)}
        with self.busy:
            if self.quitting:
                raise ValueError(QUITTING)
            try:
                built = self.engine.call("image", recipe)
            except Cancelled:
                raise ValueError("Cancelled: nothing was built") from None
            except engines.Gone as exc:
                raise ValueError(QUITTING if self.quitting else str(exc)) from None
        if self.quitting:   # closed while it built (AZ-823)
            raise ValueError(QUITTING)
        report = built["report"]
        self.spoiler, self.source = report.get("spoiler"), Path(recipe["iso"])
        _remember(iso=recipe["iso"])
        from platformdirs import user_downloads_path
        iso = Path(recipe["iso"])
        stem = iso.stem if iso.suffix.lower() in (".iso", ".xiso") else iso.name   # the site's download's name
        return {"report": report, "size": built["size"], "recipe": recipe, "build": built["build"],
                "out": str(user_downloads_path() / f"{stem} (AzurKit).iso")}

    def save(self, body: dict) -> dict:
        recipe, out = body.get("recipe"), _path(body.get("out"), "saved image")
        if out.exists() and out != self.chosen:
            raise ValueError(f"{out} exists: choose another name, or delete it first")

        def progress(step: dict) -> None:
            self.progress = step
            if self.cancelled.is_set():
                raise Cancelled
        with self.busy, self.writing:
            self.cancelled.clear()   # before the check: a quit after it still cancels this save
            if self.quitting:
                raise ValueError(QUITTING)
            self.progress, self.out = IDLE, out
            try:
                return {"saved": self.engine.call("save", recipe, str(out), body.get("build"), progress=progress)}
            except Cancelled:
                raise ValueError("Cancelled: nothing was written") from None
            except engines.Gone as exc:   # its process ended mid-write: its part file goes here
                _unpart(out)
                raise ValueError("Cancelled: nothing was written" if self.cancelled.is_set()
                                 else f"{exc}: nothing was written") from None

    def randomizer(self, body: dict) -> dict:
        """``api/randomizer``: what the Randomizer tab shows; the engine
        builds the randomizer's logic meanwhile, for a seed's build."""
        self.engine.warm("randomizer")
        return sdk.randomizer_settings(body.get("given"))

    def restore(self, body: dict) -> dict:
        """``api/restore``: what of the setup still applies; with Randomize
        on, the engine builds the randomizer's logic meanwhile."""
        setup = body.get("setup")
        if isinstance(setup, dict) and isinstance(setup.get("randomizer"), dict) and setup["randomizer"].get("on"):
            self.engine.warm("randomizer")
        return sdk.restore(setup)

    def vanilla(self, body: dict) -> dict:
        """``api/vanilla``: the image's own slider values, or an AzurKit
        build's recipe; the engine reads a vanilla image meanwhile, for its
        pictures."""
        read = _vanilla(body)
        if "opened" not in read:
            self.engine.warm("image", str(_path(body.get("iso"), "image")))
        return read

    def track(self, body: dict) -> dict:
        """``api/tracker``: what the tracker shows (``sdk.tracker``), one ask
        at a time; with Live on for its plan, Live's events since the last
        ask merged into its marks, the reach holding the element levels the
        game holds, and Live's status (``live``). As Modkit's: the marks keep
        the saved slot the game last showed, the next session opens on their
        journal (a lost link, Live off and on), and Reset reads the game
        again."""
        given = body.get("given")
        with self.tracking:
            feed = self.feed
            plan = given.get("plan") if isinstance(given, dict) else None
            if feed is None or not isinstance(plan, dict) or plan.get("sha256") != feed.sha256:
                return sdk.tracker(given)
            events, seen = feed.take()
            slot = seen.pop("slot")
            out = tracking.view({**given, "kit": seen.pop("kit"), "held": seen.pop("held")}, events)
            t = tracking.tracker_of(plan)
            if slot is not None and slot != t.slot:
                t.slot = slot
                out["marks"] = t.state()
            if given.get("reset"):
                feed.resync()
            feed.keep(t.journal())
            return out | {"live": seen}

    def live(self, body: dict) -> dict:
        """``api/live``: Live on for ``plan`` (its marks the journal a
        first settle checks the game against), reading the first of
        ``endpoints`` that answers (empty: the defaults), or off."""
        with self.tracking:
            if self.feed is not None:
                self.feed.stop()
                self.feed = None
            if body.get("on"):
                if self.quitting:
                    raise ValueError(QUITTING)
                endpoints = body.get("endpoints") or ""
                if not isinstance(endpoints, str):
                    raise ValueError("live: endpoints is a list's text, as Endpoints… takes it")
                try:
                    link.parse(endpoints)
                except ValueError as exc:
                    raise ValueError(f"Endpoints: {exc}") from None
                self.feed = live.Feed(body.get("plan"), body.get("marks"), endpoints, bool(body.get("gems"))).start()
        return {}

    def art(self, body: dict) -> dict:
        """``api/art``: which of the tracker's pictures are drawn
        (:meth:`.art.Drawing.status`), and with ``draw`` the rest drawn from
        the image at ``iso`` on a thread, one part at a time, once ``iso``
        names a file (a path half typed draws nothing, and says nothing)."""
        if body.get("draw"):
            if self.quitting:
                raise ValueError(QUITTING)
            iso = body.get("iso")
            path = Path(iso.strip()).expanduser() if isinstance(iso, str) else None
            if path is not None and path.is_absolute() and path.is_file():
                self.drawing.start(str(path))
        return self.drawing.status()

    def save_spoiler(self, body: dict) -> dict:
        """``api/spoiler``: write the last randomized build's spoiler to
        ``out``, never over an existing file but the one the save dialog
        chose, nor a vanilla image or the image it was built from (D36);
        whole or not at all."""
        out = _path(body.get("out"), "spoiler")
        if self.spoiler is None:
            raise ValueError("No spoiler: build with Randomize ticked first")
        if out.exists() and out != self.chosen:
            raise ValueError(f"{out} exists: choose another name, or delete it first")
        if out.exists() and any(image and image.exists() and out.samefile(image)
                                for image in (self.source, *map(gate.find, gate.RELEASES))):
            raise ValueError(f"{out}: it is a vanilla image, which AzurKit never writes over")
        data = self.spoiler.encode("utf-8")
        part = out.with_name(f"{out.name}.part")
        part.write_bytes(data)
        part.replace(out)
        return {"spoiler": {"out": str(out), "size": len(data)}}

    def settings_file(self, body: dict) -> dict:
        """``api/settings_file``: the Randomizer tab's ``settings`` (a
        settings table, checked as a build checks it) written as a settings
        file (Modkit's ``--save-settings`` file) to ``out``, never over an
        existing file but the one the save dialog chose; whole or not at all."""
        from platformdirs import user_downloads_path
        out = _path(body["out"], "settings file") if body.get("out") else user_downloads_path() / "settings.toml"
        if out.exists() and out != self.chosen:
            raise ValueError(f"{out} exists: choose another name, or delete it first")
        data = randomizer.settings_file(body.get("settings")).encode("utf-8")
        part = out.with_name(f"{out.name}.part")
        part.write_bytes(data)
        part.replace(out)
        return {"saved": {"out": str(out), "size": len(data)}}

    def choose(self, body: dict) -> dict:
        """The window's file dialog: an image to read, or where to save one
        (``out``), the spoiler (``spoiler``) or the settings (``settings``)."""
        import webview
        given = Path(body["path"]).expanduser() if isinstance(body.get("path"), str) and body["path"] else None
        folder = str(given.parent) if given else ""
        if body.get("kind") in ("out", "spoiler", "settings"):
            picked = self.window.create_file_dialog(webview.FileDialog.SAVE, directory=folder,
                                                    save_filename=given.name if given else "")
        else:
            picked = self.window.create_file_dialog(webview.FileDialog.OPEN, directory=folder, file_types=IMAGES)
        if isinstance(picked, (list, tuple)):
            picked = picked[0] if picked else None
        if picked and body.get("kind") in ("out", "spoiler", "settings"):
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
        if url.path == "/theme.js":
            return self._send(_theme_js(), "text/javascript")
        if url.path == "/api/progress":
            return self._json(self.server.progress)
        if url.path.startswith("/art/"):   # the tracker's pictures, from the user cache folder (never the bundle)
            version, _, rel = urllib.parse.unquote(url.path).removeprefix("/art/").partition("/")
            root = self.server.drawing.where
            file = (root / rel).resolve()
            ok = version == tracking.ART_VERSION and file.suffix in (".png", ".json") and file.is_relative_to(
                root.resolve()) and file.is_file()
            return self._send(file.read_bytes(), mimetypes.guess_type(file.name)[0]) if ok else self.send_error(404)
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
        call = {"/api/build": self.server.build, "/api/save": self.server.save, "/api/vanilla": self.server.vanilla,
                "/api/preset": lambda body: {"fragment": sdk.preset_encode(body.get("recipe"), body.get("report"))},
                "/api/decode": lambda body: {"preset": sdk.preset_decode(body.get("text"))},
                "/api/theme": _set_theme, "/api/setup": _set_setup,
                "/api/restore": self.server.restore,
                "/api/randomizer": self.server.randomizer,
                "/api/tracker": self.server.track,
                "/api/plan": lambda body: {"plan": self.server.engine.call("plan", body.get("recipe"))},
                "/api/tracked": _set_tracked, "/api/live": self.server.live, "/api/art": self.server.art,
                "/api/settings_file": self.server.settings_file,
                "/api/pickers": lambda body: sdk.pickers(body.get("given")),
                "/api/preview": lambda body: self.server.engine.call("preview", body.get("recipe")),
                "/api/match": lambda body: self.server.engine.call("match", body.get("recipe")),
                "/api/content": lambda body: sdk.content({"source": body.get("source")}),
                "/api/install": lambda body: sdk.content_install({"id": body.get("id"), "source": body.get("source")}),
                "/api/content_source": _set_source,
                "/api/spoiler": self.server.save_spoiler,
                "/api/cancel": lambda body: self.server.cancel()}.get(url.path)
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
        except (OSError, ValueError, engines.Gone) as exc:   # the sdk's refusals name what and why, never game bytes
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


def _unpart(out: Path) -> None:
    """Remove a save's part files beside ``out`` (``iso.pack``'s), its writer ended (D35)."""
    for part in out.parent.glob(f"{glob.escape(out.name)}.*.part"):
        with contextlib.suppress(OSError):   # still open on Windows: nothing more to do here
            part.unlink(missing_ok=True)


def serve(page: Path = PAGE, engine: engines.Here | engines.Spawned | None = None) -> Server:
    """Serve ``page`` (a folder holding ``index.html``) on 127.0.0.1 with a
    fresh token, on a thread, its calls run by ``engine`` (on the request's
    thread: :class:`.engine.Here`); :meth:`Server.close` stops both."""
    if not (page / "index.html").is_file():
        raise FileNotFoundError(f"{page}: no index.html (the page)")
    return Server(page, engine)


def _window(server: Server) -> bool:
    """Show the page in a pywebview window until it closes; ``False`` when
    there is no webview here."""
    try:
        import webview
        from webview.errors import WebViewException
    except ImportError:
        return False
    try:
        server.window = webview.create_window(url=server.url, **WINDOW, background_color=GROUNDS[_theme()])
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
    if not (PAGE / "index.html").is_file():
        print(f"azurkit: {PAGE}: no index.html (the page)", file=sys.stderr)
        return 1
    swapcache.install()   # the images checked and the swap's answers, kept across launches (the engine's too)
    server = serve(engine=engines.Spawned(stores=True))
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
