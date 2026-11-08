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
the app, with the catalog, AzurKit's version and the commit it was built
from (``azurkit.commit``, About's), the image to start from (the
one the last build read, remembered in platformdirs' config folder, else a
release's own image), whether there are file dialogs (the window's), the
site's address, which its share links name (:data:`SITE`, D884), and the
theme the player last picked (dark until they pick light, D897; ``POST
api/theme`` ``{"theme"}`` remembers it there too: the page's address, and
so its storage, is new each launch), whether the page's Remember settings
is ticked (``remember``, off by default, D1156) and, only while it is, the
page's setup as it was last left (D915: the packs ticked, the settings
changed and a loaded recipe's config.xbr cells, never the image or anything
read from it; ``POST api/setup`` ``{"remember", "setup"}`` keeps the choice
and, remembering, the setup, ``null`` or ``remember`` false forgetting it;
a setup kept with no choice, AzurKit 1.0's, is forgotten at the launch,
never restored; and ``POST api/restore`` ``{"setup"}`` gives back what
still applies, ``sdk.restore``). The page's ``theme.js``, which sets
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
dialog chose (it asked first), with ``POST api/cancel``. ``GET
api/progress`` gives the progress of the calls in flight, each a
``core.progress`` record (``{"stage", "label", "done", "total",
"percent"}``): the newest's at its top, and each kind's in ``calls``
(``build``, ``save``: their named stages, the swap's items counted;
``preview``, ``match``: the call's own line, the swap's items counted;
``plan``: its logic read, fill and placements; ``tracker``: a plan's
first view's seed logic and world map, the maps' exits counted on it
outside Live's view; ``randomizer``, ``restore``,
``vanilla``, ``spoiler``: the call's own line, no count), which the page
shows as its bar.
Both run in the engine (:mod:`.engine`): ``serve``'s on a thread of the
server, the app's (:func:`main`) in a process of its own, with the seed's
plan and the Characters tab's pictures and G4 match, so the server's own
answers never wait on a build, and Cancel answers at once.
Work ahead (:mod:`.ahead`, D1007): ``POST api/prefetch`` ``{"gen", "recipe",
"view"}`` plans the page's typed seed (``{seed, share}``, as Track asks it)
and reads that plan's first tracker view, and ``POST api/speculate`` ``{"gen",
"iso", "packs", "xbr", "randomizer", "character"}`` builds the page's settled
setup, each at the page's change number; Track, the tracker's first ask and
Build take them. ``api/install`` carries ``gen`` too.
``POST api/spoiler`` ``{}`` gives the last randomized build's spoiler
(``{"text"}``), which the build leaves out (``sdk.image``'s ``spoiler``
false) and the engine makes from the plan it kept the first time it is
asked (``sdk.spoiler(plan, built=True)``), and ``{"out"}`` writes it there,
on the same terms. ``POST api/randomizer`` ``{"given"}`` gives what
the Randomizer tab shows (``sdk.randomizer_settings``).
``POST api/settings_file`` ``{"out", "settings"}`` writes the Randomizer
tab's settings as a settings file (D144; ``out`` null: ``settings.toml``
in the Downloads folder), never over an existing file but one the save
dialog chose.
``POST api/tracker`` ``{"given"}`` gives what the item tracker shows
(``sdk.tracker``; a shaped plan's Spoiler's openers are the engine's, as
its work ahead keeps them; with no plan the vanilla game's spots, never in
the slot a typed seed's first view is read ahead in); with Live on for its plan, it first merges what Live
read since the last ask (:mod:`.live`: the spots the game shows taken, the
element levels it holds) and gives Live's status and where it saw the
player (``live``). ``POST api/live`` ``{"on", "plan", "marks",
"endpoints"}`` turns Live on for a plan (reading the first of the
endpoints that answers as xemu: the fork's shared RAM, or QMP; Modkit's
grammar, empty for the defaults; the private ones of the xemu Play started and of the admin attach's helper
first) or off. ``POST api/play`` ``{"iso", "xemu"}`` launches the player's xemu with the saved build
``iso`` in its tray and private endpoints Live reads (Modkit's Play, :mod:`.play`: ``xemu`` the one the
player picked; the one it launched is remembered, the config's ``xemu``), or says what it needs first;
``api/attach`` ``{"pid"}`` reads a running xemu of the player's through the macOS admin attach (one
password prompt, a read-only root helper, :mod:`.live_helper`); ``api/tray`` ``{}`` gives the randomized
AzurKit build in a running xemu's tray (``iso``; another disc is passed over) and its recipe (``preset``),
whose seed the tracker then tracks (D261). Each Build writes a log in the log folder (:mod:`.logs`), and ``api/logs``
``{"open"}`` names that folder and the last log, and opens either (``"folder"``, ``"last"``) in this
computer's own viewer. ``POST api/plan`` ``{"recipe"}`` plans a seed to track
(``sdk.plan``), and ``POST api/tracked`` ``{"tracker"}`` remembers the
plan last tracked and the marks of the last plans (``host.json``'s
``tracker``: the randomizer's names and numbers, never the image's).
``POST api/art`` gives the tracker's pictures that ship with the page
(:mod:`.art`: its maps' index and its icons' names, Step 4.3f);
``GET art/<version>/<name>`` serves one.
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
(``sdk.content_install``, into the content folder); ``api/community``
``{}`` the community packs that folder holds (``sdk.community``); ``api/replace``
``{"path", "file"}`` picks a computer file to replace one of the image's (``sdk.file_entry``, held for this session);
``api/saves`` ``{"given"}`` the Tools tab's Saves (``sdk.saves``); ``api/content_source``
``{"source"}`` remembers the tab's Content from (``null``: the default),
which ``host.json``'s ``content_source`` gives the next page, and
``api/show_objects`` ``{"show"}`` its Show objects (D1034: ``false``, the
default, hides the objects), ``host.json``'s ``show_objects``.
The Data tab's calls (Step 4.7a): ``POST api/data`` ``{"given"}`` gives a
view of config.xbr's cells (``sdk.data``: the vanilla file AzurKit ships,
no image) and ``api/data_edit`` ``{"given"}`` checks a cell's edit into the
recipe's ``xbr`` operations (``sdk.data_edit``); the page keeps them.
The Variants view's calls (Step 4.6c): ``POST api/variants``,
``api/variant_open``, ``api/variant_read``, ``api/variant_save`` and
``api/variant_delete`` ``{"given"}`` (``sdk.variants`` ...: the list, and
your variants in ``variants`` in the user data folder, where Modkit keeps
them), ``api/variant_import`` ``{"path"}`` (an Export's zip or a
recipe.json, read by path) and ``api/variant_export`` ``{"name", "out"}``
(the zip written to ``out``, else the Downloads folder);
``api/variant_check`` and Step 4.6b's calls on the dress it keeps run in
the engine (:data:`EDITED`), its bar in ``api/progress``.
The Tools tab's calls (Step 4.7c): ``POST api/info`` ``{"iso"}`` says what
the image is (``sdk.image_info``), ``api/verify_all`` ``{"iso"}`` checks
every file of it (``sdk.verify_all``: only what its kept check hasn't
hashed, its bar in ``api/progress``), ``api/files`` ``{"iso"}`` lists its
files (``sdk.files``) and ``api/extract`` ``{"iso", "path", "out"}``
writes one (``sdk.extract``); ``api/open`` ``{"iso"}`` reads an AzurKit
build's recipe (``sdk.open_build`` of the files it changed);
``api/mods_file`` ``{"text"}`` reads a mods file and ``{"recipe" |
"preset", "out"}`` writes one (``sdk.mods_file``), ``api/plan_spoiler``
``{"plan"}`` gives a plan file's spoiler (the engine's ``sdk.spoiler``) and
``api/report`` ``{"text", "out", "name"}`` writes a text the tab shows (the
last build's report); each save goes to ``out``, else the Downloads folder,
never over an existing file but the one the save dialog chose, nor a
vanilla image or the image it reads (D36). ``api/storage`` ``{"clear"}``
lists what the app keeps on this computer, by name (:func:`kept`), and
clears those entries alone: never an image or the folder that may hold one
(SEC-10); asked as the tab opens, it has the engine build the randomizer's
logic meanwhile, for a plan file's spoiler.
``POST api/choose`` ``{"kind": "iso" | "build" | "out" | ..., "path"}`` opens the window's
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
import hashlib
import hmac
import http.server
import json
import math
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from collections.abc import Callable
from pathlib import Path

from azurkit import __version__, commit, sdk
from azurkit.core import gate
from azurkit.core.progress import record
from azurkit.edits import files as replaced
from azurkit.edits import xbr
from azurkit.tools import randomizer
from azurkit.tools.mods import community as communal
from azurkit.tools.randomizer import dbcache, tracking
from azurkit.tools.randomizer.live import link

from . import ahead, live, logs, play, swapcache, warm, xemu
from . import art as pictures
from . import engine as engines
from .engine import Cancelled

SITE = "https://azurik-modding-hub.github.io/AzurKit/"   # the site (D884), which the app's share links open

PAGE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "web"   # the frozen app's, else the checkout's
NO_WINDOW = "AZURKIT_NO_WINDOW"   # set: main() opens nothing (the tests' mode)
MAX_BODY = 1 << 20
KEEP = 1.0
"""s a call may run before its answer's headers go, and between the spaces that follow them until the answer (JSON
reads past them): Firefox aborts every connection that carried no byte in the 5 s after the computer's network
changes (``network.http.network-changed.timeout``), and a call that sent nothing until its answer lost it, a plan's or
a spoiler's of seconds, tens on a slow runner ("NetworkError"; a Mac's IPv6 changed every 1-8 min here, Step 4.4ci36)."""
IMAGES = ("Disc images (*.iso;*.xiso)",)   # the open dialog's filter (another name can be typed in)
VARIANT_FILES = ("Variants (*.zip;*.json)",)   # the Variants view's Import (an Export's zip, or a recipe.json alone)
SAVES = ("out", "spoiler", "settings", "extract", "mods", "report", "saves", "variant")   # the kinds of save the save dialog chooses for
UNFILTERED = ("replacement", "folder", "xemu")   # the open dialog's kinds that take any file (xemu: its .app or program)
MODS = "AzurKit mods.json"   # the Tools tab's mods file, by default (web/tools.mjs's)
NEVER_CLEARED = (".iso", ".xiso")   # an image AzurKit's Clear never removes, wherever it is (SEC-10)
# text_select: pywebview otherwise injects a <style> to stop selection, which the page's CSP refuses
WINDOW = {"title": "AzurKit", "width": 1100, "height": 820, "text_select": True}
# The page's themes (D897: dark until the player picks light, which the app remembers) and each one's ground
# (web/app.css's --bg), which the window shows until the page draws
GROUNDS = {"dark": "#0d1117", "light": "#e8ecf1"}
THEMES = tuple(GROUNDS)
QUIT_WAIT = 1.5   # seconds a close waits, in all, for a cancelled save to remove its part file (AZ-823)
QUITTING = "AzurKit is quitting: nothing was written"
CONTENT_TYPES = {".css": "text/css", ".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".html": "text/html",
                 ".ico": "image/x-icon", ".js": "text/javascript", ".json": "application/json", ".md": "text/markdown",
                 ".mjs": "text/javascript", ".png": "image/png", ".wasm": "application/wasm", ".wav": "audio/x-wav",
                 ".zip": "application/zip"}
"""What a browser is told of each kind of file the page, Pyodide's core and the content folder hold: this table, never
``mimetypes``, whose guess on Windows is the registry's (``text/plain`` for a ``.mjs`` on many a machine, which a browser
refuses to run as a module, so the page never starts)."""
IDLE = {"stage": None, "label": "", "done": 0, "total": 0, "percent": None}   # api/progress with nothing in flight


def content_type(name: str) -> str:
    """The ``Content-Type`` of a file called ``name``: :data:`CONTENT_TYPES`'s, else plain bytes."""
    return CONTENT_TYPES.get(Path(name).suffix.lower(), "application/octet-stream")


def _config() -> Path:
    from platformdirs import user_config_path
    return user_config_path("AzurKit", appauthor=False) / "app.json"


_REMEMBERING = threading.RLock()
"""Held to read the config and to write it: a build's thread and the page's calls each remember a part of it, and
Windows refuses to replace a file another thread has open."""
WAITS = (0.05, 0.1, 0.2, 0.4, 0.8, 0)
"""s between the tries of the config's read or replace that Windows refuses while another process (a virus scanner)
holds the file open for a moment; refused at the last, it fails."""


def _tried(attempt: Callable[[], object]) -> object:
    """``attempt()``, tried again after each of :data:`WAITS` it raises PermissionError."""
    for wait in WAITS:
        try:
            return attempt()
        except PermissionError:
            if not wait:
                raise
            time.sleep(wait)


def _read() -> dict:
    """What the config holds, read past a moment it is held open (:func:`_tried`): ``{}`` when there is none;
    ValueError for a file that holds no settings object, OSError for one it still can't read."""
    with _REMEMBERING:
        try:
            kept = json.loads(_tried(lambda: _config().read_text(encoding="utf-8")))
        except FileNotFoundError:
            return {}
    if not isinstance(kept, dict):
        raise ValueError(f"a JSON {type(kept).__name__}, not an object")
    return kept


def _logic_ahead() -> None:
    """The randomizer's logic, read ahead from the server's start on D1008's
    intent (Randomize on in the remembered setup, a tracked plan
    remembered), off the launch's path, which checks the setup against the
    shipped skip table alone: the Randomizer tab's first ask or the tracker's
    view that follows finds it read, or waits for this read (Step 4.4bd).
    Only the wheel's or the frozen app's shipped one, never a checkout's
    check (about 4 s)."""
    with contextlib.suppress(Exception):   # a refusal: the page's own call names it
        if dbcache.shipped_skips(randomizer.DATA_DIR) is not None:
            randomizer.kept_logic()


def _kept() -> dict:
    """What the app remembers (``{"iso", "theme", "remember", "setup"}``), else nothing. Read past a moment it is held
    open too: a page handed no setup for one would remember the next change over it."""
    try:
        return _read()
    except (OSError, ValueError):
        return {}


def _start_image(kept: dict | None = None) -> str:
    """The image the last build read (in ``kept``, else the config), else a release's own image, else ``""``."""
    last = (_kept() if kept is None else kept).get("iso")
    if isinstance(last, str) and Path(last).is_file():
        return last
    return str(next(filter(None, map(gate.find, gate.RELEASES)), ""))


def _theme(kept: dict | None = None) -> str:
    """The theme the player last picked (in ``kept``, else the config), else dark (D897)."""
    return theme if (theme := (_kept() if kept is None else kept).get("theme")) in THEMES else THEMES[0]


def _theme_js() -> bytes:
    """The app's ``theme.js`` (the site's reads the browser's storage): it
    sets the remembered theme before the page's first paint."""
    return f'document.documentElement.dataset.theme = "{_theme()}";\n'.encode()


def _remember(**kept: object) -> None:
    """Remember ``kept`` beside what the config holds (``None`` forgets a
    key), written whole or not at all, past a moment another process (a
    virus scanner, on Windows) holds the file open, to read it or to
    replace it (:func:`_read`): a read refused past that writes nothing,
    as what it couldn't read would be lost, and a file that holds no
    settings is written over. Each says why on stderr, and no more: a build
    doesn't fail for it."""
    def say(text: str) -> None:
        with contextlib.suppress(OSError, ValueError):   # a stderr gone with its reader
            print(f"azurkit: {text}", file=sys.stderr)

    try:
        with _REMEMBERING:
            try:
                was = _read()
            except ValueError as exc:
                say(f"the config held no settings ({exc}): remembering {', '.join(kept)} writes it over")
                was = {}
            _config().parent.mkdir(parents=True, exist_ok=True)
            part = _config().with_suffix(".json.part")
            part.write_text(json.dumps({k: v for k, v in (was | kept).items() if v is not None}) + "\n",
                            encoding="utf-8")
            _tried(lambda: part.replace(_config()))
    except OSError as exc:
        say(f"can't remember {', '.join(kept)}: {exc}")


def _set_theme(body: dict) -> dict:
    """``api/theme``: remember the theme the page's toggle picked."""
    if (theme := body.get("theme")) not in THEMES:
        raise ValueError(f"theme: {theme!r} is none of {', '.join(THEMES)}")
    _remember(theme=theme)
    return {}


def _setup(kept: dict) -> object:
    """The page's setup the config holds (D915), only while the page's
    Remember settings is ticked (``remember`` true, D1156), else ``None``."""
    return kept.get("setup") if kept.get("remember") is True else None


def _set_setup(body: dict) -> dict:
    """``api/setup``: whether the page remembers its setup (``remember``,
    Remember settings: false unless true, D1156) and, remembering, the
    setup itself (D915), else none (unticked, the kept one is forgotten at
    once; ``null`` forgets it too): pack and setting names (identifiers, so
    never a path), their numbers and config.xbr ``set`` operations only, so never a
    ``replace_bytes``' bytes. A ``set``'s table, entity, prop and text
    value are free strings (config.xbr's names hold spaces; text cells hold
    text), checked by :func:`xbr.normalize` alone: the page fills them from
    the catalog and never puts the image's path in one. The Randomizer
    tab's (``randomizer``: on, the seed the player typed, the settings and
    the obsidian cost) is checked as a build checks it
    (``tools.randomizer.remembered``), and the Characters tab's
    (``character``) as a share link carries one: names and numbers. A
    refused setup leaves the kept one as it was, the tick kept still (the
    site keeps it whatever its setup)."""
    if not isinstance(remember := body.get("remember", False), bool):
        raise ValueError(f"remember: {remember!r} is neither true nor false")
    if (setup := body.get("setup") if remember else None) is not None:
        try:
            _check_setup(setup)
        except ValueError:
            _remember(remember=True)
            raise
    _remember(remember=remember or None, setup=setup)
    return {}


def _check_setup(setup: object) -> None:
    """Refuse, by name, a setup :func:`_set_setup` can't keep."""
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
    if "community" in setup:
        communal.normalize(setup["community"])   # ids and pins only, else refused by name


TRACKED = 20   # the plans whose marks the app keeps (the page's KEEP)


def _set_tracked(body: dict) -> dict:
    """``api/tracked``: remember the tracker's plan last tracked (a plan
    file's object: the randomizer's names and numbers) and the marks of
    the last :data:`TRACKED` plans (``{sha256: marks}``), Live's endpoints,
    Gems and Show collected, or forget them (``null``); marks the tracker
    can't read are refused by name."""
    if (kept := body.get("tracker")) is not None:
        if not (isinstance(kept, dict) and set(kept) <= {"plan", "marks", "endpoints", "gems", "collected"}
                and all(kept.get(k, False) in (True, False) for k in ("gems", "collected"))):
            raise ValueError("tracker: an object of plan, marks, endpoints, gems and collected only, or null")
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


def _set_objects(body: dict) -> dict:
    """``api/show_objects``: remember the Characters tab's Show objects
    (``true``; ``false`` forgets it: the objects hidden, the default)."""
    if not isinstance(show := body.get("show"), bool):
        raise ValueError("show_objects: show is true or false")
    _remember(show_objects=show or None)
    return {}


def _downloads() -> Path:
    """The Downloads folder (made where it isn't): where a save without a path goes."""
    from platformdirs import user_downloads_path
    folder = user_downloads_path()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _written(out: Path, data: bytes) -> dict:
    """``data`` at ``out``, whole or not at all (a part file renamed into place)."""
    part = out.with_name(f"{out.name}.part")
    try:
        part.write_bytes(data)
        part.replace(out)
    finally:
        part.unlink(missing_ok=True)
    return {"out": str(out), "size": len(data)}


def kept() -> list[tuple[str, str, Path]]:
    """What the app keeps on this computer (``api/storage``), each a named
    entry of its own (SEC-10): ``(name, what, path)``."""
    from platformdirs import user_data_path
    return [("settings", "Your setup, theme, tracker marks, Content from and the last image's path", _config()),
            ("stamps", "The images AzurKit checked (each one's path, size and times)", swapcache.root() / "stamps.json"),
            ("swap", "The characters' dressed bodies, a Check's parts, pictures and G4 matches",
             swapcache.root() / "swap"),
            ("content", "Installed community content", user_data_path("AzurKit", appauthor=False) / "content"),
            ("logs", "Each build's log (its recipe and report, or why it failed)", logs.folder())]


def _size(path: Path) -> int:
    if not path.is_dir() or path.is_symlink():
        return path.lstat().st_size
    return sum((Path(root) / name).lstat().st_size for root, _, names in os.walk(path) for name in names)


def _clear(path: Path) -> bool:
    """Remove ``path``, a :func:`kept` entry: a file, or a folder's files
    and then the folders they leave empty; never an image
    (:data:`NEVER_CLEARED`), nor a folder still holding one (SEC-10).
    Whether it held anything."""
    if not (path.exists() or path.is_symlink()):
        return False
    if path.is_symlink() or not path.is_dir():
        if path.suffix.lower() in NEVER_CLEARED:
            return False
        path.unlink()
        return True
    for root, folders, names in os.walk(path, topdown=False):
        for name in [*names, *(f for f in folders if (Path(root) / f).is_symlink())]:
            if Path(name).suffix.lower() not in NEVER_CLEARED:
                (Path(root) / name).unlink()
        with contextlib.suppress(OSError):   # it still holds an image
            Path(root).rmdir()
    return True


def _storage(body: dict) -> dict:
    """``api/storage``: each :func:`kept` entry there is, its size in bytes;
    with ``clear``, each removed first (:func:`_clear`) and named in
    ``cleared``."""
    cleared = [name for name, _, path in kept() if body.get("clear") and _clear(path)]
    return {"entries": [{"name": name, "what": what, "size": _size(path)} for name, what, path in kept()
                        if path.exists() or path.is_symlink()]} | ({"cleared": cleared} if body.get("clear") else {})


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
    """The page's server and engine, on its own thread. :attr:`url` opens it. Its listen queue is the system's longest
    (``socket.SOMAXCONN``), not socketserver's 5: a page's load asks for its files at once, and Windows refuses a
    connect past a full queue where macOS and Linux drop it and the browser tries again (the site's test server's 29
    ECONNREFUSED on GitHub's Windows runner, ``tests/_static.py``)."""

    daemon_threads = True
    request_queue_size = socket.SOMAXCONN

    def __init__(self, page: Path, engine: engines.Here | engines.Spawned | None = None):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.closed = False                 # set by close(): a connection the page kept is answered no more
        self.engine = engine or engines.Here()   # where builds, saves, plans and pictures run
        self.page, self.token = page.resolve(), secrets.token_urlsafe(32)
        self.host, self.cookie = f"127.0.0.1:{self.server_port}", f"azurkit-token-{self.server_port}"
        self.url = f"http://{self.host}/?token={self.token}"
        self.window = None                  # the pywebview window, once there is one: its file dialogs
        self.started = time.monotonic()     # host.json's age: how long this launch has run (the page's bar, D980)
        self.busy = threading.Lock()        # one build or save at a time
        self.writing = threading.Lock()     # held by a save, which quit() waits on (never a build)
        self.out: Path | None = None        # where the save in flight writes
        self.calls: dict[object, tuple[str, dict]] = {}   # the calls in flight: their kind and last record
        self.following = threading.Lock()   # self.calls
        self.cancelled = threading.Event()
        self.quitting = False               # set by quit(), before it cancels: no build or save starts after it
        self.deadline: float | None = None  # quit()'s first call's, plus QUIT_WAIT
        self.chosen: tuple[str, Path] | None = None   # the save dialog's last answer and its kind (it asked first)
        self.seeded: dict | None = None     # the last randomized build's plan, whose spoiler api/spoiler gives
        self.spoiler: str | None = None     # and that spoiler, once the engine made it
        self.source: Path | None = None     # and the image it was built from, which it never replaces (D36)
        self.tracking = threading.Lock()    # the tracker the page's asks and Live's feed share
        self.feed: live.Feed | None = None  # Live, while it is on
        self.player = play.Player()         # Play's xemu and the admin attach's helper, their private folders
        self.log: Path | None = None        # the last build's log, which its save is added to
        self.drawing = pictures.Drawing()   # the tracker's maps and icons, shipped with the page
        self.picks: dict[str, Path] = {}    # the files picked this session to replace the image's, by its path
        self.slots = ahead.Ahead(kill=self._quiet)   # the work ahead, each click's way to it (D1007)
        if "setup" in (kept := _kept()) and _setup(kept) is None:   # AzurKit 1.0's, kept unasked: never restored
            _remember(setup=None)
        if warm.intent(_setup(kept), kept.get("tracker")):
            threading.Thread(target=_logic_ahead, name="azurkit-logic", daemon=True).start()
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
        self.slots.close()   # every job ahead stops, and a click on one is let go (D1012)
        if (feed := self.feed) is not None:
            feed.stop()
        self.player.close()   # Play's and the helper's private folders: the helper sees its socket gone and exits
        self.deadline = self.deadline or time.monotonic() + QUIT_WAIT
        if saved := self.writing.acquire(timeout=max(0.0, self.deadline - time.monotonic())):
            self.writing.release()
        self.engine.close()   # the app's engine process ends here, before a stalled save's part file goes
        if not saved and (out := self.out) is not None:
            _unpart(out)

    def close(self) -> None:
        self.quit()
        self.closed = True
        self.shutdown()
        self.server_close()

    def handle_error(self, request, client_address) -> None:
        """A browser that dropped a kept connection (a closed context or window resets it) or left mid-answer is no
        fault of the app's: only another error prints its traceback."""
        if not isinstance(sys.exception(), ConnectionError):
            super().handle_error(request, client_address)

    def cancel(self) -> dict:
        """``api/cancel``: a save stops at its next chunk; a build answers
        Cancelled at once, and its work runs on as work ahead through a
        seed's fill, for the next Build of these settings (:mod:`.ahead`),
        then stops at its next record."""
        self.cancelled.set()
        self.slots.cancel("build")
        return {}

    def _quiet(self, job: ahead.Job) -> None:
        """``job``, stopped or cancelled, reached no record within
        ``ahead.GRACE``: the engine's process ends and another takes its
        place, but for a view (the server's own) and beside a save, which
        that would write again from nothing: that job ends at its next
        record."""
        with self.following:
            saving = any(kind == "save" for kind, _ in self.calls.values())
        if job.kind != "view" and not saving:
            self.engine.cancel()

    @contextlib.contextmanager
    def follow(self, kind: str, first: dict = IDLE):
        """A call of ``kind`` in flight for ``api/progress``, from its record
        ``first``: ``report(record)`` gives its next, until it ends."""
        ident = object()
        with self.following:
            self.calls[ident] = (kind, first)

        def report(step: dict) -> None:
            with self.following:
                if ident in self.calls:
                    self.calls[ident] = (kind, step)
        try:
            yield report
        finally:
            with self.following:
                self.calls.pop(ident, None)

    def progress(self) -> dict:
        """``api/progress``: the newest call's record, and each kind's (``calls``)."""
        with self.following:
            calls = list(self.calls.values())
        return {**(calls[-1][1] if calls else IDLE), "calls": dict(calls)}

    def host_info(self) -> dict:
        kept = _kept()
        return {"engine": "app", "version": __version__, "commit": commit(), "catalog": sdk.catalog(), "iso": _start_image(kept),
                "dialogs": self.window is not None, "site": SITE, "theme": _theme(kept),
                "remember": kept.get("remember") is True, "setup": _setup(kept), "tracker": kept.get("tracker"),
                "content_source": kept.get("content_source"), "show_objects": kept.get("show_objects") is True,
                "attach": xemu.can_attach(), "age": round(time.monotonic() - self.started, 3)}

    def _recipe(self, body: dict) -> dict:
        recipe = {"iso": str(_path(body.get("iso"), "image")), "packs": body.get("packs", {})}
        return self._held(recipe | {key: body[key] for key in ("xbr", "randomizer", "character", "community", "files")
                                    if body.get(key)})

    def _held(self, recipe: object) -> object:
        """``recipe`` with the files its ``files`` names that the player
        picked this session (``api/replace``), by the server's own record,
        and never a ``picked`` of its own, with ``files`` or without: no
        recipe, and no page, names a computer path it reads (SEC-11)."""
        if not isinstance(recipe, dict):
            return recipe
        held = {k: v for k, v in recipe.items() if k != "picked"}
        if not isinstance(recipe.get("files"), list):
            return held
        named = [e["path"] for e in recipe["files"] if isinstance(e, dict) and isinstance(e.get("path"), str)]
        return held | {"picked": {path: str(self.picks[path]) for path in named if path in self.picks}}

    def saves(self, body: dict) -> dict:
        """``api/saves`` (``sdk.saves``): the computer paths it reads through
        ``edits.files.source`` (SEC-11), the BIOS files read for this ask
        alone and refused by size before they are read; a slot saved to
        ``out``, a new folder (:meth:`writable`), else under its id in the
        Downloads folder; no zip: the site's."""
        from azurkit.tools.saves import session

        given = dict(body.get("given") or {})
        if given.get("do") == "zip" or not {"flash", "mcpx"}.isdisjoint(given):
            raise ValueError("saves: the app reads your files by path, and saves a folder")
        for key in ("folder", "image"):
            if key in given:
                given[key] = str(_path(replaced.source(str(given[key])), "save"))
        if given.get("do") == "sign":
            given["iso"] = str(_path(given.get("iso"), "image"))
            for key in ("flash", "mcpx"):
                if not (where := given.pop(f"{key}_file", None)):
                    continue
                file = _path(replaced.source(str(where)), key)
                if file.stat().st_size > session.MAX_BIOS:
                    raise ValueError(f"saves: {file.name} is no BIOS file: past the {session.MAX_BIOS:,} B AzurKit reads as one")
                given[key] = file.read_bytes()
        if given.get("do") == "save":
            name = str(given.get("id"))
            given["out"] = str(self.writable(_path(given["out"], "slot's folder") if given.get("out")
                                             else _downloads() / name, "saves"))
        return sdk.saves(given)

    def replace(self, body: dict) -> dict:
        """``api/replace``: ``{"path", "file"}``, a computer file the player
        picked to stand in for the image's ``path``: its entry
        (``sdk.file_entry``), and the file held for this session's builds. A
        network share or device path is refused before anything is opened
        (``edits.files.source``)."""
        path, file = body.get("path"), replaced.source(str(body.get("file") or ""))
        given = _path(file, "replacement")
        sdk.file_entry({"path": path, "sha256": "0" * 64, "size": given.stat().st_size})   # refused before it is read
        with self.follow("replace", record("check", f"Reading {given.name}")), open(given, "rb") as f:
            sha = hashlib.file_digest(f, "sha256").hexdigest()
            entry = sdk.file_entry({"path": path, "sha256": sha, "size": f.tell()})
        self.picks[path] = given
        return entry

    def _image(self, recipe: dict) -> Callable[[ahead.Job], dict]:
        """A build of ``recipe`` in the engine, as a slot's job, its peak told to the slots (``ahead.room``)."""
        def run(job: ahead.Job) -> dict:
            built = self.engine.call("image", recipe, progress=job.progress, fore=job.fore)
            self.slots.peaked(job.key, built["peak"])
            return built
        return run

    def _planned(self, recipe: object) -> Callable[[ahead.Job], dict]:
        """A seed's plan (``{seed, share}``, as Track asks it) in the engine, as a slot's job; meanwhile, here, what
        its first tracker view compiles (:meth:`_view_ahead`)."""
        def run(job: ahead.Job) -> dict:
            threading.Thread(target=self._view_ahead, args=(recipe, job), name="azurkit-view-ahead",
                             daemon=True).start()
            return self.engine.call("plan", recipe, progress=job.progress, fore=job.fore)
        return run

    def _view_ahead(self, recipe: object, job: ahead.Job) -> None:
        """``randomizer.tracker_ahead`` of the plan ``job`` works out in the engine, on a thread of this process
        (whose Logic the view reads) as low as the job runs (D1007), each compile waiting while a call other than
        that plan's is in flight here or a build runs ahead (its answers pass this process's GIL, which a low thread
        holds while the busy computer runs others: a Build then waits on it), until the job ends or stops (the view,
        once the plan is in, compiles what is left)."""
        low, over = ahead.Low(), lambda: job.done.is_set() or job.state == "stopped"

        def stop() -> bool:
            while not over() and (self._others("plan") or (built := self.slots.job("build")) is not None
                                  and not built.done.is_set()):
                time.sleep(0.05)
            low(job.state != "taken")
            return over()
        low(job.state != "taken")
        with contextlib.suppress(Exception):   # a head start only: the view works it out
            randomizer.tracker_ahead(recipe, stop)

    def _others(self, kind: str) -> bool:
        """Whether a call of another kind than ``kind`` is in flight (:meth:`follow`)."""
        with self.following:
            return any(other != kind for other, _ in self.calls.values())

    def speculate(self, body: dict) -> dict:
        """``api/speculate``: build the page's settled recipe ahead at its
        change ``gen`` (D1007), so its Build takes that build; a seed's fill
        is the plan's ahead, which the build waits on. No image yet, a save
        or a dress in flight (the page offers again once it ends): nothing
        ahead, and what was stops."""
        gen = body.get("gen")
        if not isinstance(gen, int) or self.quitting:
            return {"ahead": False}
        try:
            recipe = self._recipe(body)
        except ValueError:
            recipe = None
        with self.following:
            dressing = any(kind in ("save", "preview", "match") for kind, _ in self.calls.values())
        key = None if recipe is None or dressing else ahead.key(recipe)
        return {"ahead": self.slots.offer("build", gen, key, self._image(recipe))}

    def prefetch(self, body: dict) -> dict:
        """``api/prefetch``: plan the page's typed seed ahead at its change
        ``gen`` (``recipe``: ``{seed, share}``, as Track asks it; null:
        nothing ahead), then that plan's first tracker view (``view``: the
        tracker's ``spoiler`` and ``gems``, as its first ask sends them; none
        while Live reads the tracker), so Track and its first view take them."""
        gen, recipe, view = body.get("gen"), body.get("recipe"), body.get("view")
        if not isinstance(gen, int) or self.quitting:
            return {"ahead": False}
        view = {k: view[k] for k in ("spoiler", "gems") if k in view} if isinstance(view, dict) else {}

        def then(job: ahead.Job) -> None:
            given = {"plan": job.value, "marks": {}, **view}
            # a shaped plan's Spoiler's openers are the engine's work ahead already, which only a click may ask for
            if self.feed is None and not (view.get("spoiler") and job.value["settings"].get("seed_difficulty")):
                self.slots.offer("view", job.gen, ahead.key(given), lambda j: sdk.tracker(given, progress=j.progress))
        key = ahead.key(recipe) if isinstance(recipe, dict) and recipe.get("seed") else None
        return {"ahead": self.slots.offer("plan", gen, key, self._planned(recipe), then=then)}

    def build(self, body: dict) -> dict:
        recipe = self._recipe(body)
        self.log = log = logs.start({k: v for k, v in recipe.items() if k != "picked"})   # Modkit's build log
        try:
            with self.busy, self.follow("build") as report:
                if self.quitting:
                    raise ValueError(QUITTING)
                try:   # the job of this recipe, if there is one (its records from its last)
                    built = self.slots.take("build", ahead.key(recipe), self._image(recipe), report=report)
                except Cancelled:
                    raise ValueError(QUITTING if self.quitting else "Cancelled: nothing was built") from None
                except engines.Gone as exc:
                    raise ValueError(QUITTING if self.quitting else str(exc)) from None
            if self.quitting:   # closed while it built (AZ-823)
                raise ValueError(QUITTING)
        except (OSError, ValueError) as exc:
            logs.failed(log, str(exc))
            raise
        logs.built(log, built["report"], built["size"])
        report = built["report"]
        self.seeded, self.spoiler, self.source = report.get("plan"), None, Path(recipe["iso"])
        _remember(iso=recipe["iso"])
        from platformdirs import user_downloads_path
        iso = Path(recipe["iso"])
        stem = iso.stem if iso.suffix.lower() in (".iso", ".xiso") else iso.name   # the site's download's name
        recipe = {k: v for k, v in recipe.items() if k != "picked"}   # the server holds it (_held)
        return {"report": report, "size": built["size"], "recipe": recipe, "build": built["build"],
                "out": str(user_downloads_path() / f"{stem} (AzurKit).iso")}

    def writable(self, out: Path, kind: str) -> Path:
        """``out``, where a save of ``kind`` (one of :data:`SAVES`: ``out``,
        the image) may write (SEC-16): never over an existing file but the
        one the save dialog chose for that kind (it asked first), nor the
        image the last build read or a vanilla image (D36)."""
        if out.exists() and self.chosen != (kind, out):
            raise ValueError(f"{out} exists: choose another name, or delete it first")
        if out.exists() and any(image and image.exists() and out.samefile(image)
                                for image in (self.source, *map(gate.find, gate.RELEASES))):
            raise ValueError(f"{out}: it is a vanilla image, which AzurKit never writes over")
        return out

    def save(self, body: dict) -> dict:
        recipe, out = self._held(body.get("recipe")), self.writable(_path(body.get("out"), "saved image"), "out")

        with self.busy, self.writing, self.follow("save", record("write")) as report:
            def progress(step: dict) -> None:
                report(step)
                if self.cancelled.is_set():
                    raise Cancelled
            self.cancelled.clear()   # before the check: a quit after it still cancels this save
            if self.quitting:
                raise ValueError(QUITTING)
            self.out = out
            try:
                saved = self.engine.call("save", recipe, str(out), body.get("build"), progress=progress)
                logs.add(self.log, f"saved {saved['out']} · {saved['size']} bytes · sha256 {saved['sha256']}")
                return {"saved": saved}
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
        with self.follow("randomizer", record("plan", "Reading the randomizer's logic")) as report:
            return sdk.randomizer_settings(body.get("given"), progress=report)

    def restore(self, body: dict) -> dict:
        """``api/restore``: what of the setup still applies; with Randomize
        on, the engine builds the randomizer's logic meanwhile."""
        setup = body.get("setup")
        if isinstance(setup, dict) and isinstance(setup.get("randomizer"), dict) and setup["randomizer"].get("on"):
            self.engine.warm("randomizer")
        with self.follow("restore", record("read", "Restoring your setup")):
            return sdk.restore(setup)

    def vanilla(self, body: dict) -> dict:
        """``api/vanilla``: the image's own slider values, or an AzurKit
        build's recipe; the engine reads a vanilla image meanwhile, for its
        pictures."""
        with self.follow("vanilla", record("check")):
            read = _vanilla(body)
        if "opened" not in read:
            self.engine.warm("image", str(_path(body.get("iso"), "image")))
        return read

    def _openers(self, report: Callable[[dict], object]) -> Callable[[dict], list]:
        """A click's tracker's ``openers``: a shaped plan's Spoiler's, from the engine, where its work ahead keeps
        them, and never again in this process (5 s, with no record to end them at); ``report`` hears its count."""
        return lambda plan: self.engine.call("openers", plan, progress=report)

    def track(self, body: dict) -> dict:
        """``api/tracker``: what the tracker shows (``sdk.tracker``), one ask
        at a time; with Live on for its plan, Live's events since the last
        ask merged into its marks, the reach holding the element levels the
        game holds, and Live's status (``live``). As Modkit's: the marks keep
        the saved slot the game last showed, the next session opens on their
        journal (a lost link, Live off and on), and Reset reads the game
        again."""
        given = body.get("given")
        with self.tracking, self.follow("tracker", record("plan", "Reading the seed's logic")) as report:
            feed = self.feed
            plan = given.get("plan") if isinstance(given, dict) else None
            if isinstance(given, dict) and plan is None:   # the maps browsed with no plan (Step 4.4u3): the work
                return sdk.tracker(given, progress=report)   # ahead's view of a typed seed goes on
            if feed is None or not isinstance(plan, dict) or plan.get("sha256") != feed.sha256:
                try:   # a plan's first view, read ahead (api/prefetch) if it was
                    return self.slots.take("view", ahead.key(given), lambda job: sdk.tracker(
                        given, progress=job.progress, openers=self._openers(job.progress)), report=report)
                except Cancelled:
                    raise ValueError(QUITTING) from None
            if (ahead_view := self.slots.job("view")) is not None:   # both read the plan's one tracker
                ahead_view.done.wait()
            events, seen = feed.take()
            slot = seen.pop("slot")
            out = tracking.view({**given, "kit": seen.pop("kit"), "held": seen.pop("held")}, events, report,
                                self._openers(report))
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
                self.feed = live.Feed(body.get("plan"), body.get("marks"), endpoints, bool(body.get("gems")),
                                      launch=self.player.endpoints()).start()
        return {}

    def play(self, body: dict) -> dict:
        """``api/play``: Play the saved build ``iso`` (:meth:`.play.Player.play`), the xemu it launched
        remembered for the next Play (never a Flatpak id)."""
        if self.quitting:
            raise ValueError(QUITTING)
        chosen = body.get("xemu") if isinstance(body.get("xemu"), str) and body["xemu"] else None
        remembered = _kept().get("xemu")
        with self.follow("play"):
            reply = self.player.play(_path(body.get("iso"), "saved build"), chosen,
                                     remembered if isinstance(remembered, str) else None)
        if remember := reply.pop("remember", None):
            _remember(xemu=remember)
        return reply

    def attach(self, body: dict) -> dict:
        """``api/attach``: a running xemu read through the macOS admin attach (:meth:`.play.Player.attach`)."""
        pid = body.get("pid")
        if pid is not None and (isinstance(pid, bool) or not isinstance(pid, int)):
            raise ValueError("attach: pid is the process of the xemu picked")
        with self.follow("attach"):
            return self.player.attach(pid)

    def tray(self, body: dict) -> dict:
        """``api/tray``: the randomized AzurKit build in a running xemu's tray (the player's own, D248) and its
        recipe (``preset``: ``sdk.open_build`` of the files it changed), whose seed the tracker tracks (D261); a
        disc that isn't one is passed over for the next running xemu's (Modkit's ``tray_seed``); ``{}`` when no
        xemu holds one."""
        presets: dict[Path, dict] = {}

        def randomized(disc: Path) -> bool:
            try:
                presets[disc] = sdk.open_build(str(disc), whole=False)
            except (OSError, ValueError):   # not an AzurKit build
                return False
            return any(layer.get("tool") == "randomizer" for layer in presets[disc].get("layers", []))

        with self.follow("tray"):
            if (disc := xemu.tray_disc(accept=randomized)) is None:
                return {}
            return {"iso": str(disc), "name": disc.name, "preset": presets[disc]}

    def build_logs(self, body: dict) -> dict:
        """``api/logs``: the log folder and the last log; ``open`` ``"folder"`` or ``"last"`` opens it in this
        computer's own viewer (:func:`.logs.reveal`)."""
        newest = logs.last()
        if (which := body.get("open")) is not None:
            if which not in ("folder", "last"):
                raise ValueError("logs: open is folder or last")
            if which == "last" and newest is None:
                raise ValueError("No build log yet: build first")
            if which == "folder":
                logs.folder().mkdir(parents=True, exist_ok=True)
            logs.reveal(logs.folder() if which == "folder" else newest)
        return {"folder": str(logs.folder()), "last": str(newest) if newest else None}

    def dressed(self, job: str, body: dict) -> dict:
        """``api/preview`` and ``api/match``: the engine's, followed by its line (a variant's dress takes minutes); the
        build ahead stops at its next record, as no dress runs beside it, and the page offers it again once this ends."""
        recipe = body.get("recipe")
        character = recipe.get("character") if isinstance(recipe, dict) else None
        species = character.get("species") if isinstance(character, dict) else None
        what = "draw it" if job == "preview" else "match garret4"
        first = record("dress", f"Dressing {species} to {what}" if isinstance(species, str) else None)
        with self.follow(job, first) as report, self.slots.turn():   # the swap's items counted on its line
            self.slots.offer("build", self.slots.gen, None, None)   # a dress beside its GiBs passes 6 (D1017): it stops
            return self.engine.call(job, recipe, progress=lambda step: report(step | {"label": first["label"]}))

    def plan(self, body: dict) -> dict:
        """``api/plan``: a seed's plan to track (the engine's; planned
        ahead, ``api/prefetch``, if its seed was)."""
        recipe = body.get("recipe")
        with self.follow("plan", record("plan")) as report:
            try:
                return {"plan": self.slots.take("plan", ahead.key(recipe), self._planned(recipe), report=report)}
            except Cancelled:
                raise ValueError(QUITTING) from None

    def install(self, body: dict) -> dict:
        """``api/install``: ``sdk.content_install``; then work ahead of an
        older change than the page's ``gen`` stops (it read the content
        before)."""
        try:
            return sdk.content_install({"id": body.get("id"), "source": body.get("source")})
        finally:
            if isinstance(gen := body.get("gen"), int):
                self.slots.change(gen)

    def edited(self, job: str, body: dict) -> dict:
        """``api/variant_check`` and the Variants editor's calls that stand on
        the dress it keeps (Step 4.6b's ``variant_colours``,
        ``variant_preview``, ``variant_rows``, ``export_pngs``): the engine's,
        followed by its line; a build ahead stops at its next record, as no
        dress runs beside it."""
        given = body.get("given")
        name = given.get("name") if isinstance(given, dict) else None
        first = record("dress", f"Checking {name} with game data" if isinstance(name, str) else None)
        with self.follow(job, first) as report, self.slots.turn():
            self.slots.offer("build", self.slots.gen, None, None)
            return self.engine.call(job, given, progress=lambda step: report(step | {"label": first["label"]}))

    def variant_import(self, body: dict) -> dict:
        """``api/variant_import``: ``{"path"}``, an Export's zip or a
        recipe.json the player picked, read (a share or device path refused
        before it is opened, ``edits.files.source``; past ``library.MOST``
        bytes refused unread) and made a variant of theirs (``sdk.variant_import``)."""
        from azurkit.tools.characters import library

        file = _path(replaced.source(str(body.get("path") or "")), "variant's file")
        if file.stat().st_size > library.MOST:
            raise ValueError(f"import: {file.name} is past the {library.MOST:,} B a variant's file holds")
        return sdk.variant_import({"data": file.read_bytes()})

    def variant_export(self, body: dict) -> dict:
        """``api/variant_export``: ``{"name", "out"}``, the variant's zip
        (``sdk.variant_export``) written to ``out``, else under its name in
        the Downloads folder (:meth:`writable`): ``{"out", "size",
        "unshareable"}``."""
        made = sdk.variant_export({"name": body.get("name")})
        out = self.writable(_path(body["out"], "zip") if body.get("out") else _downloads() / made["name"], "variant")
        return _written(out, made["zip"]) | {"unshareable": made["unshareable"]}

    def art(self, body: dict) -> dict:
        """``api/art``: the tracker's shipped pictures
        (:meth:`.art.Drawing.status`)."""
        return self.drawing.status()

    def spoiled(self, body: dict) -> dict:
        """``api/spoiler``: the last randomized build's spoiler (``{"text"}``,
        made by the engine from the plan it kept, once), or with ``out`` that
        spoiler written there, never over an existing file but the one the
        save dialog chose, nor a vanilla image or the image it was built from
        (D36); whole or not at all."""
        if (plan := self.seeded) is None:
            raise ValueError("No spoiler: build with Randomize ticked first")
        out = self.writable(_path(body["out"], "spoiler"), "spoiler") if body.get("out") else None
        if (text := self.spoiler) is None:
            with self.follow("spoiler", record("spoiler")) as report:
                text = self.engine.call("spoiler", plan, progress=report)["text"]
            if self.seeded is plan:   # no build since
                self.spoiler = text
        if out is None:
            return {"text": text}
        data = text.encode("utf-8")
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
        out = self.writable(_path(body["out"], "settings file") if body.get("out")
                            else user_downloads_path() / "settings.toml", "settings")
        data = randomizer.settings_file(body.get("settings")).encode("utf-8")
        part = out.with_name(f"{out.name}.part")
        part.write_bytes(data)
        part.replace(out)
        return {"saved": {"out": str(out), "size": len(data)}}

    def info(self, body: dict) -> dict:
        """``api/info``: what the image is (``sdk.image_info``)."""
        with self.follow("info", record("check", "Reading your image")):
            return sdk.image_info(str(_path(body.get("iso"), "image")))

    def verify_all(self, body: dict) -> dict:
        """``api/verify_all``: every file of the image checked, its bytes counted (``sdk.verify_all``)."""
        with self.follow("verify_all", record("check", sdk.CHECK_ALL)) as report:
            return sdk.verify_all(str(_path(body.get("iso"), "image")), progress=report)

    def extract(self, body: dict) -> dict:
        """``api/extract``: the image's file ``path`` written to ``out``,
        else under its name in the Downloads folder (``sdk.extract``)."""
        iso, member = _path(body.get("iso"), "image"), body.get("path")
        if not (isinstance(member, str) and member.strip("/")):
            raise ValueError("extract: name the image's file")
        out = self.writable(_path(body["out"], "extracted file") if body.get("out")
                            else _downloads() / member.rstrip("/").rpartition("/")[2], "extract")
        with self.follow("extract", record("write", f"Extracting {member}")) as report:
            return sdk.extract(str(iso), member, str(out), progress=report)

    def mods_file(self, body: dict) -> dict:
        """``api/mods_file``: ``{"text"}`` read (``sdk.mods_file``'s preset);
        with ``out``, its ``recipe`` or ``preset`` written there as a mods
        file, else in the Downloads folder (:data:`MODS`)."""
        given = {key: body[key] for key in ("text", "recipe", "preset") if key in body}
        if "out" not in body:
            return sdk.mods_file(given)
        text = sdk.mods_file(given)["text"]
        out = self.writable(_path(body["out"], "mods file") if body["out"] else _downloads() / MODS, "mods")
        return _written(out, text.encode("utf-8"))

    def report(self, body: dict) -> dict:
        """``api/report``: a text the Tools tab shows (the last build's
        report, a plan's spoiler) written to ``out``, else under ``name`` in
        the Downloads folder; whole or not at all."""
        text, name = body.get("text"), body.get("name") or "AzurKit build report.txt"
        if not isinstance(text, str) or len(text) > MAX_BODY:
            raise ValueError("report: text is the report's text")
        if not (isinstance(name, str) and name not in (".", "..") and "/" not in name and "\\" not in name):
            raise ValueError("report: name is a file's name")
        out = self.writable(_path(body["out"], "report") if body.get("out") else _downloads() / name, "report")
        return _written(out, text.encode("utf-8"))

    def storage(self, body: dict) -> dict:
        """``api/storage`` (:func:`_storage`), which the Tools tab asks as it
        opens: the engine builds the randomizer's logic meanwhile, for a plan
        file's spoiler."""
        if not body.get("clear"):
            self.engine.warm("randomizer")
        return _storage(body)

    def plan_spoiler(self, body: dict) -> dict:
        """``api/plan_spoiler``: a plan file's spoiler (the engine's), its
        bar counting the randomizer's logic's checks while the engine still
        reads it (the tab's opening started it), then the spoiler's stage."""
        with self.follow("plan_spoiler", record("plan", "Reading the randomizer's logic")) as report:
            return self.engine.call("plan_spoiler", body.get("plan"), progress=report)

    def choose(self, body: dict) -> dict:
        """The window's file dialog: an image to read (``iso``, an AzurKit
        ``build``), or where to save one (``out``) or another of
        :data:`SAVES` (the spoiler, the settings, an extracted file, a mods
        file, a report)."""
        import webview
        self.chosen = None   # each dialog's answer is its own: a cancelled one vouches for nothing
        given = Path(body["path"]).expanduser() if isinstance(body.get("path"), str) and body["path"] else None
        folder = str(given.parent) if given else ""
        if body.get("kind") in SAVES:
            picked = self.window.create_file_dialog(webview.FileDialog.SAVE, directory=folder,
                                                    save_filename=given.name if given else "")
        else:
            picked = self.window.create_file_dialog(
                webview.FileDialog.FOLDER if body.get("kind") == "folder" else webview.FileDialog.OPEN, directory=folder,
                **({} if body.get("kind") in UNFILTERED else
                   {"file_types": VARIANT_FILES if body.get("kind") == "variant_file" else IMAGES}))
        if isinstance(picked, (list, tuple)):
            picked = picked[0] if picked else None
        if picked and body.get("kind") in SAVES:
            self.chosen = (body["kind"], Path(str(picked)))
        return {"path": str(picked) if picked else None}


class _Handler(http.server.BaseHTTPRequestHandler):
    """Each connection kept for the page's next request (HTTP/1.1), its answers sent without Nagle's delay, as the
    site's test server's (``tests/_static.py``): a page's load of its files and pictures takes a few connections, never
    one a file. Every answer has its length, but a long call's (:meth:`_kept`), which closes its connection to end; a
    refusal (``send_error``) closes its connection too, as its body may be unread."""
    server: Server
    protocol_version = "HTTP/1.1"
    disable_nagle_algorithm = True   # TCP_NODELAY: an answer's body never waits on the browser's ACK of its headers

    def _url(self) -> urllib.parse.SplitResult | None:
        """The request's URL when it carries this launch's token and names
        this server as its host, and the app hasn't closed, else ``None``."""
        url = urllib.parse.urlsplit(self.path)
        given = urllib.parse.parse_qs(url.query).get("token", [""])[0]
        cookie = next((v for k, _, v in (c.strip().partition("=") for c in self.headers.get("Cookie", "").split(";"))
                       if k == self.server.cookie), "")
        token = self.server.token.encode()
        if self.server.closed or self.headers.get("Host") != self.server.host or not (
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
            return self._json(self.server.progress())
        if url.path.startswith("/art/") and url.path != "/art/icons.css":   # the tracker's pictures (that's a page file)
            version, _, rel = urllib.parse.unquote(url.path).removeprefix("/art/").partition("/")
            root = self.server.drawing.where
            file = (root / rel).resolve()
            ok = version == tracking.ART_VERSION and file.suffix in (".png", ".json") and file.is_relative_to(
                root.resolve()) and file.is_file()
            return self._send(file.read_bytes(), content_type(file.name)) if ok else self.send_error(404)
        try:
            file = (self.server.page / (urllib.parse.unquote(url.path).lstrip("/") or "index.html")).resolve()
            data = file.read_bytes() if file.is_relative_to(self.server.page) and file.is_file() else None
        except (OSError, ValueError):   # a NUL in the path, say
            data = None
        if data is None:
            return self.send_error(404)
        self._send(data, content_type(file.name),
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
                "/api/plan": self.server.plan,
                "/api/tracked": _set_tracked, "/api/live": self.server.live, "/api/art": self.server.art,
                "/api/play": self.server.play, "/api/attach": self.server.attach, "/api/tray": self.server.tray,
                "/api/logs": self.server.build_logs,
                "/api/settings_file": self.server.settings_file,
                "/api/pickers": lambda body: sdk.pickers(body.get("given")),
                "/api/preview": lambda body: self.server.dressed("preview", body),
                "/api/match": lambda body: self.server.dressed("match", body),
                "/api/content": lambda body: sdk.content({"source": body.get("source")}),
                "/api/community": lambda body: sdk.community(), "/api/replace": self.server.replace, "/api/saves": self.server.saves,
                "/api/install": self.server.install,
                "/api/speculate": self.server.speculate, "/api/prefetch": self.server.prefetch,
                "/api/content_source": _set_source, "/api/show_objects": _set_objects,
                "/api/spoiler": self.server.spoiled,
                "/api/data": lambda body: sdk.data(body.get("given")),
                "/api/data_edit": lambda body: sdk.data_edit(body.get("given")),
                "/api/info": self.server.info, "/api/verify_all": self.server.verify_all,
                "/api/files": lambda body: sdk.files(str(_path(body.get("iso"), "image"))),
                "/api/extract": self.server.extract,
                "/api/open": lambda body: {"preset": sdk.open_build(str(_path(body.get("iso"), "build")), whole=False)},
                "/api/mods_file": self.server.mods_file, "/api/report": self.server.report,
                "/api/plan_spoiler": self.server.plan_spoiler, "/api/storage": self.server.storage,
                **{f"/api/{name}": (lambda name: lambda body: getattr(sdk, name)(body.get("given")))(name)
                   for name in VARIANT_CALLS},
                **{f"/api/{job}": (lambda job: lambda body: self.server.edited(job, body))(job) for job in EDITED},
                "/api/variant_import": self.server.variant_import, "/api/variant_export": self.server.variant_export,
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
        with self._kept() as sent:
            try:
                reply = call(body)
            except (OSError, ValueError, engines.Gone) as exc:   # the sdk's refusals name what and why, never game bytes
                reply = {"refused": str(exc)}
        if sent:
            self.wfile.write(json.dumps(reply).encode())
        else:
            self._json(reply)

    @contextlib.contextmanager
    def _kept(self):
        """While a call runs, its connection never quiet (:data:`KEEP`): past ``KEEP`` s its answer's headers go (200,
        JSON, no length: the answer ends at the connection's close, which they say) and a space each ``KEEP`` s after
        them. Yields a list that holds ``True`` once they went."""
        sent, done, lock = [], threading.Event(), threading.Lock()

        def keep() -> None:
            while not done.wait(KEEP):
                with lock:
                    if done.is_set():
                        return
                    try:
                        if not sent:
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.send_header("Cache-Control", "no-store")
                            self.send_header("Connection", "close")   # and close_connection
                            self.end_headers()
                            sent.append(True)
                        self.wfile.write(b" ")
                    except OSError:   # the page went: the answer's own write says so
                        return
        keeper = threading.Thread(target=keep, name="azurkit-keep", daemon=True)
        keeper.start()
        try:
            yield sent
        finally:
            with lock:
                done.set()
            keeper.join()

    def log_message(self, *args) -> None:   # the token is in the first request's line
        pass


VARIANT_CALLS = ("variants", "variant_open", "variant_read", "variant_save", "variant_delete", "base_bones",
                 "own_sounds", "kit_throw", "move_sources")
"""The Variants view's calls the server answers itself (``api/<name>`` ``{"given"}``: ``sdk.<name>``)."""
EDITED = ("variant_check", "variant_colours", "variant_preview", "variant_rows", "export_pngs")
"""Those the engine answers, the dress a Check keeps there serving the ones after it (:meth:`Server.edited`)."""


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
        with contextlib.suppress(OSError):   # a disk that won't: nothing more to do here
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


def _input_kept_from_children() -> None:
    """On Windows, keep this process's input from the processes it starts: each takes its parent's standard handles,
    and a read blocked on a pipe holds that pipe's lock, so a child's Python stops at its first look at its own stdin
    until the read ends. ``serve``'s read would hold the engine there for good: it never answers, and it dies at its
    start when the app is killed. Its standard input becomes NUL; ``sys.stdin`` still reads the pipe."""
    if os.name == "nt":
        import ctypes
        import msvcrt
        set_std_handle = ctypes.WinDLL("kernel32").SetStdHandle
        set_std_handle.argtypes = (ctypes.c_ulong, ctypes.c_void_p)
        set_std_handle(-10 & 0xFFFFFFFF, msvcrt.get_osfhandle(os.open(os.devnull, os.O_RDONLY)))   # STD_INPUT_HANDLE


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
    if argv:
        _input_kept_from_children()   # before the engine's spawn
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
