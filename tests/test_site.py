"""The site (Step 4.1d1, D866): the page in ``web/`` runs the wheel under
Pyodide 314 in a module worker, unpacked without its dependencies (WEB §3,
§6.3), here in headless Chromium, in WebKit (Safari's engine, Step
4.1d3) and in Firefox (D994), served from the site folder
``scripts/web_tools.py`` assembles. Each ported pack's G1 case builds its
golden on both releases, and the page's build is CPython's: the same report,
and the same segments, so the Blob it saves is the image ``sdk.image`` makes;
so is a build with a slider set on the page (Step 4.1e1), whose track holds
its vanilla value and widens, never clamps, and one of config.xbr's cells
(Step 4.1e2); the saved file of every pack is that image, byte for byte, and
opens back into its recipe. A share link carries the page's recipe and loads
it into a page it opens (Step 4.1g), and the site serves the favicon the page
links (Step 4.1g2). The page is design A with the owner's changes (Step 4.1h): dark
first, its areas' tabs, the packs in their categories' groups, Build always in
view, and an About tab; and with the owner's answers (Step 4.1i): a pack's
settings locked until it is ticked (D907), the L3 toggles in their settings'
rows (D909), light's faint text readable and a light first frame; and each
visit starts at the defaults unless Remember settings is ticked, which keeps
its setup between visits until Reset to defaults (Step 4.1j, D915; Step
4.19a, D1156), its faint text readable in dark too. Under the
page's CSP (no ``'unsafe-eval'``) nothing is refused, and every request is a GET of one of the site's own files or of the
community content it reads (any https address, D1135): the image never leaves the page. The page is driven as
``tests/_page.py`` says."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import errno
import functools
import hashlib
import http.client
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.parse
import warnings
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.tools import characters, data, mods, randomizer
from azurkit.tools.characters import pool
from azurkit.tools.randomizer import generator, tracking
from azurkit.tools.randomizer.art import icons
from scripts import record_goldens, web_tables, web_tools
from tests import _g1, _hosts, _page, _perf, _static, conftest
from tests.test_randomizer import BROWSED, TRACKER, TRACKER_MAP, _profile, shows_gems, tracker_states

RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]
# A piece at a time, in slices: WebKit answers a whole read of a Blob held in memory over about 100 MB with
# NotReadableError (one the page made itself too). The page never reads one: Save hands the browser the joined Blob.
SIGNATURE = """async () => {
  const out = [], step = 32 << 20;
  let place = 0;
  for (const s of azurkit.build.segments) {
    const start = place;
    place += s.size;
    if (s.kind !== "bytes") {
      out.push(s.kind === "copy" ? ["copy", s.offset, s.size] : ["zero", s.size]);
      continue;
    }
    const whole = new Uint8Array(s.size);
    for (let at = 0; at < s.size; at += step) {
      whole.set(new Uint8Array(await azurkit.build.blob.slice(start + at, start + Math.min(at + step, s.size)).arrayBuffer()), at);
    }
    out.push(["bytes", s.size, [...new Uint8Array(await crypto.subtle.digest("SHA-256", whole))]
                                 .map((b) => b.toString(16).padStart(2, "0")).join("")]);
  }
  return out;
}"""


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """The site, with this checkout's wheel."""
    return web_tools.site(tmp_path_factory.mktemp("site") / "site")


def test_the_site_built_with_its_own_wheel_holds_no_dotfile_but_nojekyll(site):
    """Pages' artifact leaves dotfiles out, and the service worker's release
    fetches each file it lists: a listed dotfile (``uv build``'s ``.gitignore``
    beside the wheel) would 404 and fail the worker's install on the real site."""
    assert [p.relative_to(site).as_posix() for p in site.rglob(".*")] == [".nojekyll"]


def test_the_pages_policy_lets_it_fetch_any_https_address_and_runs_only_its_own_code():
    """D1135 (the owner: "users should be able to load any community content repo they want"): the page's CSP lets
    it fetch any https address, a content repository on GitHub or anywhere else (``connect-src 'self' https:``), and
    no other directive widens: its scripts and workers are its own and nothing else loads from elsewhere, so what it
    fetches is data, never code it runs."""
    page = (web_tools.ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert [rule.split() for rule in web_tools.CSP.findall(page)[0].split("; ")] == [
        ["default-src", "'self'"], ["script-src", "'self'", "'wasm-unsafe-eval'"], ["worker-src", "'self'", "blob:"],
        ["connect-src", "'self'", "https:"], ["object-src", "'none'"], ["base-uri", "'none'"], ["form-action", "'none'"]]


def test_the_sites_files_are_as_new_as_the_site_so_macos_sweeping_its_temp_folder_leaves_them(site):
    """dirhelper deletes what looks 3 days old in macOS's temp folder at 03:35, and a Pyodide file copied with its
    release's times looks years old: a run crossing 03:35 lost them, and every page after it never got ready."""
    assert {p.relative_to(site).as_posix() for p in site.rglob("*")
            if p.is_file() and time.time() - p.stat().st_mtime > 86400} == set()


KINDS = (".azkp", ".bin", ".glb", ".gltf", ".json", ".md", ".png", ".wav")
"""The content kinds the site publishes, each served as data (mime-db's types: no page, script or rendered document;
a variant's shipped answer, ``.azkp``, no type's, so ``application/octet-stream``)."""
REFUSED = (".xsd", ".rng", ".html", ".zqx")
"""Two XML types a browser renders (an XHTML ``<script>`` in one ran on the site's origin), a page and a made-up suffix."""


@pytest.mark.parametrize("fault", ["a ../ path through a linked folder", "a linked folder", "a listed link",
                                   *(f"a listed {s} file" for s in REFUSED), "a page behind a trailing /",
                                   "a page behind a trailing /."])
def test_the_sites_content_is_its_checked_regular_files_and_a_fault_writes_nothing(tmp_path, monkeypatch, fault):
    """``web_tools.site(content=)`` publishes a content clone's manifest and
    each regular file it lists in ``content-source/``, checked as an Install
    checks them, a file of each kind of :data:`KINDS` (the allow-list,
    ``web_tools.CONTENT_KINDS``); a ``../`` path, a link anywhere on a listed
    file's path (a folder or the file: the deployer's own files), any other
    suffix (:data:`REFUSED`) and a path that isn't plain (a trailing ``/`` or
    ``/.``, which would publish the page under it) are refused naming the
    file, before the site's first file is written (the three cases SEC-3
    reproduced, a linked folder with no ``../``, and the trailing ``/``).
    The site's root holds an empty ``.nojekyll``: no Pages build turns a
    content file with front matter into a page."""
    from azurkit.tools.characters import content

    root, clone, outside = tmp_path / "root", tmp_path / "clone", tmp_path / "outside"
    for folder in (root / "web", tmp_path / "pyodide", clone / "packs/x", clone / "d1/d2/d3", outside):
        folder.mkdir(parents=True)
    page = """<meta http-equiv="Content-Security-Policy" content="default-src 'self'">the page\n"""
    (root / "web/index.html").write_text(page)
    (root / "web/sw.js").write_text(f"{web_tools.RELEASE_LINE}\n")   # the service worker's line for its release
    (clone / "index.html").write_text("planted\n")
    (clone / "packs/x/pack.json").write_text("{}\n")
    folder = {".md": "packs", ".wav": "sounds", ".azkp": "variants"}
    kinds = ["packs/x/pack.json", *(f"{folder.get(s, 'fx')}/x/x{s}" for s in KINDS if s != ".json")]   # each in a
    # folder that takes it (Step S1)
    for rel in kinds[1:]:
        (clone / rel).parent.mkdir(parents=True, exist_ok=True)
        (clone / rel).write_text(f"a {rel} file\n")
    (outside / "secret.json").write_text('"the deployer\'s"\n')
    for suffix in REFUSED:
        (clone / f"packs/x/x{suffix}").write_text("<script>1</script>\n")
    (clone / "packs/a").symlink_to(clone / "d1/d2/d3")
    (clone / "packs/y").symlink_to(outside)
    (clone / "packs/x/leak.json").symlink_to(outside / "secret.json")
    bad = {"a ../ path through a linked folder": "packs/a/../../../index.html",
           "a linked folder": "packs/y/secret.json", "a listed link": "packs/x/leak.json",
           **{f"a listed {s} file": f"packs/x/x{s}" for s in REFUSED}, "a page behind a trailing /": "packs/x/x.html/",
           "a page behind a trailing /.": "packs/x/x.html/."}[fault]
    monkeypatch.setattr(web_tools, "missing", lambda _root: [])
    monkeypatch.setattr(web_tools, "pyodide_dir", lambda _root: tmp_path / "pyodide")
    (built := tmp_path / "azurkit-0-py3-none-any.whl").write_bytes(b"a wheel")

    def site(out: Path, *paths: str) -> Path:
        listed = {p: (clone / p).read_bytes() if (clone / p).is_file() else b"its ../ folded by name (Windows)" for p in paths}
        files = [{"path": p, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for p, data in listed.items()]
        (clone / "manifest.json").write_text(json.dumps({"format": content.FORMAT, "schema_version": 1, "entries": [
            {"id": "x", "kind": "pack", "title": "X", "author": "A", "licence": "MIT", "version": 1, "files": files,
             "requires": []}]}))
        return web_tools.site(out, root, built, clone)

    good = site(tmp_path / "good", *kinds)
    assert sorted(p.relative_to(good / "content-source").as_posix() for p in (good / "content-source").rglob("*")
                  if p.is_file()) == sorted(["manifest.json", *kinds])
    assert all((good / "content-source" / rel).read_bytes() == (clone / rel).read_bytes() for rel in kinds)
    assert (good / "index.html").read_text() == page and (good / ".nojekyll").read_bytes() == b""
    with pytest.raises(SystemExit, match=re.escape(bad)):
        site(tmp_path / "bad", "packs/x/pack.json", bad)
    assert not (tmp_path / "bad").exists()


FOUR_CORES = "Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', { get: () => 4 });"
"""The site's pages say they have 4 cores, the computer AzurKit must run well on (D1017), so workers.mjs starts B on
any host: GitHub's Apple Silicon runner has 3, where Chromium and Firefox said 3 and the tests that wait on B's work
waited for a B that never started (run 41521288667). The pool's path with no B is pinned on stubs (``WORKERS_ROWS``'s
``cores``)."""


class Site:
    """The site served to a fresh browser context from its folder by a server
    of a process of its own (:class:`_page.Served`, at ``origin``, a secure
    context), every request logged (``requests``): its files never wait on
    this interpreter. They did when Playwright's routes fetched them through a
    server of this process's: a plan in a thread here or a full collection of
    the heap a randomizer test left here held its GIL, and on GitHub's 4-core
    Intel runner a reshape's picture waited 98 s (run 42071325305). Only a
    request elsewhere is routed here (a 404). Its service worker is blocked:
    routing never sees a service worker's own requests, so these pages run
    uncontrolled, as a browser without one does (``tests/test_service_worker.py``
    holds the site under ``sw.js``). A ``profile`` makes it persistent; in
    WebKit with a home of its own (``<profile>-home``), as Playwright's WebKit
    keeps OPFS, the build files, in the user's
    ``~/Library/WebKit/org.webkit.Playwright`` for every browser it launches
    while each browser's Web Locks are its own, so another test's page load
    swept this one's held build file (the gate on 3fd00b2: its Save's check
    failed reading it). CoreFoundation's ``CFFIXED_USER_HOME`` moves it
    (macOS)."""

    def __init__(self, browser, root: Path, profile: Path | None = None, **options):
        self.root, self.routed = root.resolve(), []   # routed: the requests answered here (elsewhere, a test's routes)
        self.files = _page.Served(self.root)
        self.origin = self.files.url
        options = {"service_workers": "block", **options}
        if profile and browser.browser_type.name == "webkit":
            home = profile.with_name(f"{profile.name}-home")
            home.mkdir(parents=True, exist_ok=True)
            options = {"env": {**os.environ, "CFFIXED_USER_HOME": str(home)}} | options
        try:
            self.context = (browser.browser_type.launch_persistent_context(str(profile), headless=True,
                                                                           accept_downloads=True, **options)
                            if profile else browser.new_context(accept_downloads=True, **options))
        except BaseException:
            self.files.close()
            raise
        self.context.add_init_script(FOUR_CORES)
        self.context.route(re.compile(rf"^(?!{re.escape(self.origin)}/)"), self._elsewhere)

    def _elsewhere(self, route, request) -> None:
        if request.url.startswith(f"blob:{self.origin}/"):   # the page's own blob: (WebKit routes them; Chromium doesn't)
            return route.continue_()
        self.routed.append((request.method, request.url, request.post_data_buffer))
        route.fulfill(status=404, body="")

    @property
    def requests(self) -> list[tuple]:
        """Each request: ``(method, url, body)``, those the site's server heard (a body as its size) and those
        answered here."""
        return [(method, f"{self.origin}{path}", size or None) for method, path, size in self.files.log()] + self.routed

    def open(self):
        """A new page, its engine loaded, each call bounded (``_page.within``; its load ``_page.load`` in
        ``_page.STALL``, as the new page has: the page's own files, about 0.4 MB, in 0.1-0.2 s here; the engine's 35 MB
        come after it)."""
        page = _page.within(self.context, self.context._impl_obj.new_page(), _page.STALL, "a new page")
        _page.load(page, f"{self.origin}/", seconds=_page.STALL)
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        return page

    def stray(self) -> list[str]:
        """Each request that isn't a GET of a site file, with no body, at ``origin``, or the page's read of the
        community list from GitHub (``sdk.SOURCE``'s manifest, D1135: a tab reads it when first opened with no Content
        from set; answered here as a 404, offline)."""
        files = {f"{self.origin}/{p.relative_to(self.root).as_posix()}" for p in self.root.rglob("*") if p.is_file()}
        files.add(f"{sdk.SOURCE}manifest.json")
        bare = ((method, url.partition("#")[0], body) for method, url, body in self.requests)   # a link's fragment
        return [f"{method} {url}" for method, url, body in bare
                if method != "GET" or body or (url if url != f"{self.origin}/" else f"{self.origin}/index.html") not in files]

    def close(self) -> None:
        try:
            _page.within(self.context, self.context._impl_obj.close(), _page.STALL, "the context's close")
        finally:
            self.files.close()


def test_a_site_pages_files_reach_it_from_a_server_of_their_own_while_this_process_holds_its_interpreter(
        browser, site, monkeypatch):
    """A site page's files come to its browser from a server of their own process (:class:`_page.Served`), never
    through this one: a page's load (35 MB: Pyodide's core, the wheel) sends Playwright's driver under 1 MiB from here,
    and ten of its files the page fetches are all answered while this interpreter is held (``_page.hold``: its GIL, as
    a full collection of a big heap or a plan here held it, on GitHub's Intel runner 98 s for a reshape's picture that
    a server of this process's served, run 42071325305)."""
    served = Site(browser, site)
    transport, sent = served.context._impl_obj._connection._transport, []
    real = transport.send
    monkeypatch.setattr(transport, "send", lambda message: (sent.append(len(transport.serialize_message(message))),
                                                            real(message))[1])
    names = ["characters/index.json", *(f"characters/{p.name}" for p in sorted((site / "characters").glob("*.png"))[:9])]
    try:
        page = served.open()
        files = {urllib.parse.urlsplit(url).path for _, url, _ in served.requests}
        assert {"/pyodide/pyodide.asm.wasm", f"/{next(site.glob('azurkit-*.whl')).name}"} <= files
        assert sum(sent) < 1 << 20, sum(sent)
        asked = page.evaluate("""(names) => {
            globalThis.fetched = [];
            for (const name of names) fetch(name, { cache: "no-store" }).then((r) => r.arrayBuffer())
                .then(() => fetched.push([name, performance.now()]));
            return performance.now();
        }""", names)
        _page.hold()
        fetched = page.evaluate("() => fetched")
        assert sorted(name for name, _ in fetched) == sorted(names) and all(
            at - asked < _page.HOLD * 1000 for _, at in fetched), (asked, fetched)
    finally:
        monkeypatch.undo()
        served.close()


def test_a_sites_file_server_holds_64_connections_made_at_once_and_answers_each(tmp_path):
    """:class:`_static.Files` (the site's file server) holds 64 connections made before it accepts any, and answers
    each: the driver fetches a page's files at once, and with socketserver's queue of 5 Windows refused the rest (29
    site tests failed on ECONNREFUSED, run 41666183947); here a connect past the queue waits for a retry instead."""
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

    (tmp_path / "a.txt").write_text("a")
    with _static.Files(("127.0.0.1", 0), functools.partial(Quiet, directory=str(tmp_path))) as server:
        held = [socket.create_connection(server.server_address, timeout=5) for _ in range(64)]   # none accepted yet
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for sock in held:
                sock.sendall(b"GET /a.txt HTTP/1.0\r\n\r\n")
            answers = [sock.makefile("rb").read() for sock in held]
        finally:
            server.shutdown()
            for sock in held:
                sock.close()
    assert [(answer.partition(b"\r\n")[0], answer.rpartition(b"\r\n\r\n")[2]) for answer in answers] == [
        (b"HTTP/1.0 200 OK", b"a")] * 64


def test_a_sites_file_server_answers_a_pages_files_over_one_kept_connection(tmp_path):
    """The site's file server (:class:`_page.Served`) keeps a connection for the next file (HTTP/1.1, no Nagle delay),
    as GitHub Pages serves a page's files over a few kept connections: with a connection a file, a first visit's
    install of its release's 551 files passed its 60 s on GitHub's Windows runner (run 42236789239), where its
    second engine's few big files loaded in 2.9 s. Two files and a missing one come over one connection, each whole; a
    refused method's answer closes it, as its body is never read."""
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("bb")
    served = _page.Served(tmp_path)
    connection = http.client.HTTPConnection(urllib.parse.urlsplit(served.url).netloc, timeout=10)
    got = []
    try:
        for method, path in (("GET", "/a.txt"), ("GET", "/b.txt"), ("GET", "/none.txt"), ("POST", "/a.txt")):
            connection.request(method, path, body=b"x" if method == "POST" else None)
            port = connection.sock.getsockname()[1]
            reply = connection.getresponse()
            got.append((reply.status, reply.read(), reply.will_close, port))
    finally:
        connection.close()
        served.close()
    assert [row[:3] for row in got] == [(200, b"a", False), (200, b"bb", False), (404, b"", False),
                                        (405, b"", True)] and len({port for *_, port in got}) == 1, got


def test_a_sites_file_server_sends_an_answer_whole_while_the_system_is_short_of_buffers():
    """The site's file server's writer (:class:`_static.Sender`) sends a piece the system refused for want of buffers
    (ENOBUFS, ENOMEM) again, so the answer comes whole and in order: on GitHub's arm64 runner macOS refused one with
    ENOBUFS, ``sendall`` ended it cut, and a first visit's install of the release in Firefox failed (run 42406769117).
    On macOS no piece is longer than the socket's low-water mark, so a refused piece sent none of its bytes."""
    data = os.urandom(1_000_003)
    listener = socket.create_server(("127.0.0.1", 0))
    peer = socket.create_connection(listener.getsockname(), timeout=10)
    sock, _ = listener.accept()
    pieces, refusals, got = [], {2: errno.ENOBUFS, 3: errno.ENOMEM, 6: errno.ENOBUFS}, bytearray()

    def send(piece) -> int:
        pieces.append(len(piece))
        if len(pieces) in refusals:
            raise OSError(refusals[len(pieces)], os.strerror(refusals[len(pieces)]))
        return sock.send(piece)

    def read() -> None:
        while len(got) < len(data) and (part := peer.recv(1 << 16)):
            got.extend(part)

    reader = threading.Thread(target=read)
    reader.start()
    try:
        short = types.SimpleNamespace(setsockopt=sock.setsockopt, getsockopt=sock.getsockopt, send=send)
        sender = _static.Sender(short)
        sent = sender.write(data)
        reader.join(10)
        darwin = sys.platform == "darwin"     # Windows refuses SO_SNDLOWAT (WSAEINVAL); only macOS's mark is pinned
        lowat = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDLOWAT) if darwin else None
    finally:
        for each in (sock, peer, listener):
            each.close()
        reader.join()
    assert (sent, len(got), bytes(got) == data) == (len(data), len(data), True)
    assert not darwin or sender.chunk == lowat == max(pieces) == _static.Sender.CHUNK, (sender.chunk, lowat, pieces)


def _built(page) -> dict:
    """The page's build once it is ready: its report and its segments
    (``["copy", offset, size]``, ``["bytes", size, sha256]``, ``["zero", size]``)."""
    return {"report": _page.built(page), "segments": _page.answer(page, SIGNATURE)}


def _signature(made: iso.Image) -> list[list]:
    return [["copy", p.offset, p.size] if isinstance(p, iso.Copy) else ["zero", p.size] if isinstance(p, iso.Zero)
            else ["bytes", p.size, hashlib.sha256(p.data).hexdigest()] for p in made.segments()]


def _as_cpython(built: dict, report: dict, made: iso.Image) -> dict:
    """What the page's dressed ``built`` is to equal: CPython's report and segments (:func:`_signature`). Off the host
    the goldens were recorded on (D1016: Pyodide's matrix products against this host's BLAS; the Intel Mac's differ for
    a hoe's lift, run 41328160086) each sha256 that holds a dress's float XBRs is the page's own (those files, the
    ``filelist.txt`` naming them, the segment that carries their changes and the build's manifest, which names their
    sha256s): every size, layout and other file stays exact, and ``test_characters.py`` holds the host's own bytes to
    their goldens close enough."""
    want = {"report": report, "segments": _signature(made)}
    if _hosts.recording() or len(built["segments"]) != len(want["segments"]):
        return want
    loose = (*record_goldens.FLOATS, "filelist.txt")
    with iso.Reader(made) as r:
        heads = [r.read(f)[:4096] for f in loose] + [report["result"][record_goldens.FLOATS[0]].encode()]
    held = [i for i, p in enumerate(made.segments()) if not isinstance(p, (iso.Copy, iso.Zero))
            and any(head in bytes(p.data) for head in heads)]
    for i in held:
        if built["segments"][i][:2] == want["segments"][i][:2]:
            want["segments"][i] = built["segments"][i]
    want["report"] = report | {"result": report["result"] | {f: built["report"]["result"].get(f) for f in loose
                                                             if f in report["result"]}}
    return want


SLID = "enemy_damage:enemy_damage_neutral=2,enemy_damage_weakness=0.5,enemy_damage_immune=-1"   # a G1 slider case
FPS = ("fps_unlock", {"target_fps": "120"}, None)
# player_physics' jump height and two of its L3 toggles (D909), the toggles from the page's checkboxes
FLIPPED = ("player_physics", {"jump_speed_scale": "1.5", "toggle_jump_speed_scale": "1", "toggle_gravity": "1"}, None)
UNIT = """(id) => document.getElementById(id).parentElement.querySelector(".unit").textContent"""
TRACK = """(id) => [document.getElementById(id).previousElementSibling.min,
                    document.getElementById(id).previousElementSibling.max]"""


PAGE_BUILDING = 5 << 28
"""Bytes of the machine's memory one page of the pack golden takes while it builds (1.25 GiB), rounded up from WebKit's,
the most of the three browsers': its page process at most 1045 MiB with 2 at once (Step 4.4ci17's results/g1-cpu3-free4,
the USA golden on this Mac read as the Apple Silicon runner: 3 cores, 4.0 GiB free), 874-936 MiB with 3 (Step 4.4ci14's
a-final-g1-pair-fp), and its share of WebKit's GPU and network processes (108 and 40 MiB)."""
KEPT_FREE = 3 << 29
"""Bytes the pack golden leaves free beside its pages (1.5 GiB): pytest's and its driver's growth for each page's image
(their 635 MiB grew to 1131 MiB in results/g1-cpu3-free4) and 1 GiB more as headroom. GitHub's 7 GB Apple Silicon
runner, whose vanilla tier runs one worker (nothing else beside the golden), lost a WebKit page of the golden's 3 at
once ("Target crashed": run 41744982709), and 3 take 3.3 GiB with the driver and pytest (Step 4.4ci14), which leaves
at most 1.2 GiB of its most free; 2 took 2.8 GiB here at their peak. That tier read 1.2-5.3 GiB free a minute, 3.0 the
median: its memory holds 2 pages at once with 4.0 GiB free, then 1 once pytest has grown (3.0-3.5 GiB)."""


def _at_once() -> int:
    """How many of the pack golden's pages build at once: each of a page's two engines a core of this worker's share of
    the machine's cores (its cores over xdist's workers, each running a test beside it), as a pick starts both (F checks
    the image, then B builds the page's recipe ahead, D1007), and no more than the machine's free memory holds
    (:data:`PAGE_BUILDING` each past :data:`KEPT_FREE`), at least 1. A page and its engine a core of all the cores (4
    on GitHub's 4-core Intel runner) let both releases' goldens, on its two workers at once, run 8 pages' 16 engines:
    a load of 42-54 there, its process listing unanswered 13 s, and a pick's round trips past :data:`_page.ACT` while
    the page itself had checked the image (run 42406769117)."""
    from scripts import ci_resources
    free = ci_resources.free_memory()[0]
    share = (os.cpu_count() or 2) // max(1, int(os.environ.get("PYTEST_XDIST_WORKER_COUNT", "1")))
    return max(1, min(share // 2, (free - KEPT_FREE) // PAGE_BUILDING))


@pytest.mark.parametrize("release", RELEASES)
def test_the_table_pages_the_site_ships_are_the_ones_the_recorder_finds_in_each_release(release, request):
    """web/tables.json's row of each release, which worker.mjs's ahead() reads in one round, is
    scripts/web_tables.py's output on that release's image, within the read cache's pages."""
    key, pages = web_tables.pages(request.getfixturevalue(f"{release.name}_iso"))
    assert json.loads(web_tables.OUT.read_text(encoding="utf-8"))[key] == pages and len(pages) <= web_tables.PAGES


@pytest.mark.parametrize("release", RELEASES)
def test_each_ported_pack_builds_its_g1_golden_in_each_browser(release, browser, site, request):
    """One page per pack, one with fps_unlock's slider typed to 120 FPS,
    one with enemy_damage's sliders at a G1 case's values (config.xbr's
    cells) and one with photo mode's fly speed past float32's range, built
    as many at once as its worker's share of the cores holds a page's two
    engines and its free memory holds (``_at_once``): each page's report and segments are CPython's for the
    values it sent, and the packs at their defaults and the slider case hold their
    G1 golden's files (and only ``filelist.txt`` besides); the fly speed
    is written as infinity with Q110's note, which the page shows, and one
    with player_physics' jump height at 1.5 and two of its L3 toggles on
    (D909). The slider's track holds its default and vanilla value, and a value typed
    past its hints widens it (D23, D42); once the image is picked, a slider
    at a site of the XBE shows the image's own vanilla value
    (``sdk.vanilla``), which its track holds too. No CSP violation, no
    request but GETs of the site's files. Ticking a pack that requires
    others ticks them too (``Pack.requires``), so its page builds it with
    them, and its G1 case (the pack alone) is test_packs'."""
    path = request.getfixturevalue(f"{release.name}_iso")
    golden = _g1.cases(release)
    cases = ([(name, {}, None if pack.requires else name) for name, pack in mods.PACKS.items()]
             + [FPS, ("enemy_damage", {k: str(v) for k, v in golden[SLID].params.items()}, SLID)]
             + [("qol_photo_mode", {"fly_speed": "1e39"}, None), FLIPPED])
    served = Site(browser, site)
    read = sdk.vanilla(str(path))
    assert {pack: set(sliders) for pack, sliders in read["packs"].items()} == {
        name: {s.name for s in pack.sliders() if s.catalog()["vanilla"] is None and release.name in pack.releases}
        for name, pack in mods.PACKS.items() if any(s.catalog()["vanilla"] is None for s in pack.sliders())}
    try:
        # A page's two engines a core of this worker's share (all 21 open on a 3-core runner, Firefox's next ran out of
        # its 120 s to start), as many as the free memory holds, read before each group
        at = 0
        while group := cases[at:at + _at_once()]:
            at += len(group)
            pages = [served.open() for _ in group]
            # Each page's image picked before any of them builds: a pick is Playwright's round trips to its page
            # (its locator, its input, the files), which the group's pages building beside it starved under
            # taskpolicy -b and nice 19 here (up to 8.6-14.0 s; a group's first pick at most 2.4 s; the page's own
            # change handler 1-6 ms) and past _page.ACT on GitHub's Intel Mac runner (run 41779807138); so picked,
            # at most 3.6 s here, slowed, with 8 busy loops beside it at a load of 31 (Step 4.4ci19)
            for (name, values, case), page in zip(group, pages):
                if (name, values, case) == FPS:
                    _page.tick(page, ["fps_unlock"])   # which unlocks its settings (D907)
                    assert _page.slide(page, "fps_unlock", "target_fps", "60") == ["30", "120", "60", "60"]
                    assert _page.slide(page, "fps_unlock", "target_fps", "1000") == ["30", "1000", "1000", "1000"]
                _page.pick(page, "#iso", path)
                if name in read["packs"]:
                    assert _page.until(page, "() => azurkit.vanilla") == read
                    for slider, value in read["packs"][name].items():
                        low, high = _page.answer(page, TRACK, f"{name}.{slider}")
                        assert float(low) <= value <= float(high)
                        assert _page.answer(page, UNIT, f"{name}.{slider}").endswith(f" · vanilla {value:g}")
            for (name, values, case), page in zip(group, pages):
                _page.build(page, [name], {name: values})
            for (name, values, case), page in zip(group, pages):
                built, sent = _built(page), _page.answer(page, "() => azurkit.sent")
                assert sent == {other: {s.name: float(values.get(s.name, s.default) if other == name else s.default)
                                        for s in mods.PACKS[other].sliders()}
                                for other in (name, *mods.PACKS[name].requires)}
                made, report = sdk.image({"iso": str(path), "packs": sent})
                if case:
                    _g1.check(built["report"]["result"], golden[case], case)
                if values.get("fly_speed") == "1e39":
                    note = "qol_photo_mode fly_speed: 1e+39 is past float32's range: written as inf (Q110)"
                    assert built["report"]["notes"] == [note]
                    assert f" · note: {note} · changed: " in _page.answer(page, STATUS)   # before the files, which run long
                assert (built["report"], built["segments"]) == (report, _signature(made)), (name, values)
                _page.check_csp(page)
                _page.close(page)
        assert served.stray() == []
    finally:
        served.close()


def test_the_pack_golden_builds_no_more_pages_at_once_than_its_workers_share_of_the_cores_and_the_free_memory_hold(
        monkeypatch):
    """A page's two engines a core of the worker's share of the cores (the cores over xdist's workers), and a page of
    :data:`PAGE_BUILDING` past :data:`KEPT_FREE` of the free memory, at least 1: GitHub's 4-core Intel runner, two
    workers, builds 1 page at a time in each (both releases' goldens at once ran 8 pages there, run 42406769117); its
    Apple Silicon runner (3 cores, one worker; its vanilla tier read 1.2-5.3 GiB free, 3.0 the median, and 3 at once
    cost a WebKit page, "Target crashed", run 41744982709), 1; this Mac (24 cores) 6 pages at -n 2, 12 alone, fewer
    as its free memory holds fewer."""
    from scripts import ci_resources
    for cores, workers, free, want in ((4, 2, 9.0, 1), (3, None, 4.5, 1), (4, 1, 9.0, 2), (24, 2, 64.0, 6),
                                       (24, None, 64.0, 12), (24, 1, 4.0, 2), (24, 1, 3.0, 1), (24, 8, 64.0, 1),
                                       (1, None, 64.0, 1)):
        monkeypatch.setattr(os, "cpu_count", lambda: cores)
        monkeypatch.setattr(ci_resources, "free_memory", lambda: (int(free * (1 << 30)), 7 << 30))
        if workers is None:
            monkeypatch.delenv("PYTEST_XDIST_WORKER_COUNT", raising=False)
        else:
            monkeypatch.setenv("PYTEST_XDIST_WORKER_COUNT", str(workers))
        assert _at_once() == want, (cores, workers, free)


def test_a_share_link_carries_the_recipe_and_a_page_opened_with_it_loads_it_marked(browser, site):
    """Copy link (no image needed) gives the page's address with
    ``sdk.preset_encode``'s fragment of its ticks and sliders, which the
    page's own address takes too. A page opened with that link loads it once
    its engine is ready: exactly those packs ticked, their sliders set, each
    tick and value it changed marked ● (an L3 toggle's left of its pill, so
    its row's columns line up with the others'), and no build. A link with config.xbr
    cells (``set``) loads them for the build and copies back the same link,
    and one that isn't a link is refused by name. No CSP violation, no
    request but GETs of the site's files."""
    from azurkit import __version__
    served = Site(browser, site)
    try:
        page = served.open()
        _page.tick(page, ["fps_unlock", "player_physics", "qol_memory_budget"],
                   {"fps_unlock": {"target_fps": "120"}, "player_physics": {"gravity": "4.9", "toggle_gravity": "1"}})
        _page.click(page, "share")
        link = _page.until(page, "() => azurkit.link")
        fragment = sdk.preset_encode({"packs": {"fps_unlock": {"target_fps": 120},
                                                "player_physics": {"gravity": 4.9, "toggle_gravity": 1},
                                                "qol_memory_budget": {}}})
        assert (link, page.evaluate("() => location.hash")) == (f"{served.origin}/{fragment}", fragment)
        assert page.evaluate("() => document.querySelector('#link').value") == link
        loaded = served.context.new_page()
        _page.load(loaded, link)
        _page.until(loaded, "() => globalThis.azurkit?.loaded")
        assert _page.ticked(loaded) == _page.ticked(page)
        assert list(_page.ticked(loaded)) == ["fps_unlock", "player_physics", "qol_memory_budget"]
        assert (_page.ticked(loaded)["fps_unlock"]["target_fps"], _page.ticked(loaded)["player_physics"]["gravity"],
                _page.ticked(loaded)["player_physics"]["toggle_gravity"]) == ("120", "4.9", "1")
        assert sorted(_page.marked(loaded)) == sorted([
            "fps_unlock", "fps_unlock.target_fps", "player_physics", "player_physics.gravity",
            "player_physics.toggle_gravity", "qol_memory_upper64", "qol_memory_upper64_gpu", "qol_alloc_race"])
        assert loaded.evaluate(COLUMNS, "player_physics") == [[1, 1, 1, 1], [True]]   # a marked L3's row lines up
        assert _locks(loaded)["fps_unlock"] == [True, "open"]   # the link's ticks unlock their settings (D907)
        assert loaded.evaluate("() => [azurkit.build, document.querySelector('#status').textContent]") == [
            None, f"Loaded the link's recipe (made with AzurKit {__version__}): 3 packs, marked ●. "
                  "Pick your vanilla image, then Build."]
        cell = {"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": "golem",
                "prop": "hitPoints", "value": 321}
        with_cell = f"{served.origin}/{sdk.preset_encode({'packs': {'qol_alloc_race': {}}, 'xbr': [cell]})}"
        again = served.context.new_page()
        _page.load(again, with_cell)
        _page.until(again, "() => globalThis.azurkit?.loaded")
        assert again.evaluate("() => [azurkit.xbr, document.querySelector('#xbr-note').textContent]") == [
            [cell], "The Data tab holds 1 config.xbr edit, which each build applies."]
        assert _locks(again)["fps_unlock"] == [False, "locked"]
        _page.click(again, "share")
        assert _page.until(again, "() => azurkit.link") == with_cell
        bad = served.context.new_page()
        _page.load(bad, f"{served.origin}/#p=@@")
        assert _page.until(bad, """() => document.querySelector("#status").classList.contains("error")
                                   && document.querySelector("#status").textContent""").startswith(
            "preset: no #p= and base64url")
        for each in (page, loaded, again, bad):
            _page.check_csp(each)
        assert served.stray() == []
    finally:
        served.close()


GROUND = "() => [azurkit.theme, getComputedStyle(document.body).backgroundColor]"   # app.css's ground, each theme
DARK, LIGHT = ["dark", "rgb(13, 17, 23)"], ["light", "rgb(232, 236, 241)"]
# Each pack with settings: [ticked, its settings' fields "locked" (all disabled), "open" (none) or "mixed"] (D907).
LOCKS = """() => Object.fromEntries([...document.querySelectorAll("#packs .pack:has(.slider)")].map((item) => {
    const off = [...item.querySelectorAll(".sliders input")].map((field) => field.disabled);
    return [item.dataset.pack, [item.querySelector("input[data-pack]").checked,
                                off.every(Boolean) ? "locked" : off.some(Boolean) ? "mixed" : "open"]];
}))"""
# A pack's setting rows (D909): each one's setting, label, and its row's last cell if that is an L3 toggle: the
# toggle's setting, text and tooltip, and whether it sits right of the row's unit.
ROWS = """(pack) => [...document.querySelectorAll(`#packs .pack[data-pack="${pack}"] .slider`)].map((row) => {
    const l3 = row.lastElementChild.matches(".l3") ? row.lastElementChild : null;
    return [row.querySelector("input[data-slider]").dataset.slider, row.querySelector("label").textContent,
            l3 && [l3.querySelector("input").dataset.slider, l3.textContent, l3.title,
                   l3.getBoundingClientRect().left >= row.querySelector(".unit").getBoundingClientRect().right]];
})"""
# A pack's settings, opened: how many places each column of its rows (each row a grid of its own) takes, and for each
# ● in an L3 toggle, whether it sits left of the pill, on the row's ground.
COLUMNS = """(pack) => {
    const item = document.querySelector(`#packs .pack[data-pack="${pack}"]`);
    if (!item.classList.contains("open")) item.querySelector(".toggle").click();
    const rows = [...item.querySelectorAll(".slider")];
    return [["input[type=range]", "input[type=text]", ".unit", ".l3"].map((part) => new Set(rows.map((row) => {
                const box = row.querySelector(part).getBoundingClientRect();
                return `${Math.round(box.left)} ${Math.round(box.right)}`;
            })).size),
            [...item.querySelectorAll(".l3 .mark:not(:empty)")].map((mark) =>
                mark.getBoundingClientRect().right <= mark.parentElement.getBoundingClientRect().left)];
}"""
# The Characters tab's layout at the page's width: [Content from and its Reset inside the list's column, on one line;
# no sideways scroll, every G4 button in view; the pictures inside their column].
# The Characters tab's columns (D1035: the community group under the species, Content from under it, all in the list's
# column): [Content from and Reset in the list's column, no sideways scroll with every G4 in view, the pictures in
# theirs, the species then the community entries (each with its button) then Content from].
CHARS_LAYOUT = """() => {
    const r = (el) => el.getBoundingClientRect(), tab = document.getElementById("characters");
    const [list, info] = [".chars-list", ".chars-info"].map((s) => r(document.querySelector(s)));
    const [source, reset, species, community] = ["char-source", "char-source-reset", "char-species", "char-community"]
        .map((id) => r(document.getElementById(id)));
    const g4 = [...tab.querySelectorAll(".g4")], entries = [...document.querySelectorAll("#char-community .entry")];
    return [source.right <= list.right && reset.right <= list.right && Math.abs(reset.top - source.top) < 2,
            tab.scrollWidth <= tab.clientWidth && g4.length > 0 && g4.every((b) => r(b).right <= innerWidth),
            r(document.getElementById("char-back")).right <= info.right,
            entries.length > 0 && entries.every((e) => e.querySelector("button, .note")) && species.bottom <= community.top
            && community.bottom <= source.top && community.left >= list.left && community.right <= list.right];
}"""
# Every visible text drawn in --faint (given true: in a grade's colour, on the Characters tab), and its contrast with
# the ground it sits on (WCAG's ratio): [what, ratio].
FAINT = """(graded = false) => {
    const rgb = (text) => text.match(/[\\d.]+/g).slice(0, 3).map(Number);
    const hex = getComputedStyle(document.documentElement).getPropertyValue("--faint").trim();
    const faint = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    const lum = (c) => c.map((v) => v / 255).map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
        .reduce((sum, v, i) => sum + [0.2126, 0.7152, 0.0722][i] * v, 0);
    const ground = (el) => {
        for (; el; el = el.parentElement) {
            const bg = getComputedStyle(el).backgroundColor;
            if (bg !== "transparent" && !/^rgba\\(.*, 0\\)$/.test(bg)) return rgb(bg);
        }
    };
    const color = (el) => rgb(getComputedStyle(el).color);
    return [...document.querySelectorAll(graded ? "#characters *" : "body *")].filter((el) => el.checkVisibility()
            && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
            && (graded ? el.style.color !== "" : color(el).join() === faint.join()))
        .map((el) => {
            const [hi, lo] = [lum(color(el)), lum(ground(el))].sort((a, b) => b - a);
            return [`${el.closest(".pack.open") ? "open " : ""}${el.dataset.model ?? (el.className || el.id)}`,
                    (hi + 0.05) / (lo + 0.05)];
        });
}"""

# Each grade's colour as drawn (its theme's --grade-*, else the engine's) and its contrast with each ground a models'
# row can have (the pane, the zebra rows', the chosen row's): [grade, ground, ratio].
GRADE_GROUNDS = """() => {
    const hex = (text) => [1, 3, 5].map((i) => parseInt(text.trim().slice(i, i + 2), 16));
    const lum = (c) => c.map((v) => v / 255).map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
        .reduce((sum, v, i) => sum + [0.2126, 0.7152, 0.0722][i] * v, 0);
    const css = (el, name) => getComputedStyle(el).getPropertyValue(name).trim();
    const tab = document.getElementById("characters");
    return Object.entries(azurkit.characters.state.view.colours).flatMap(([grade, colour]) =>
        ["--pane", "--zebra", "--sel"].map((ground) => {
            const [hi, lo] = [lum(hex(css(tab, `--grade-${grade}`) || colour)), lum(hex(css(tab, ground)))]
                .sort((a, b) => b - a);
            return [grade, ground, (hi + 0.05) / (lo + 0.05)];
        }));
}"""


def _locks(page) -> dict[str, list]:
    """:data:`LOCKS`, once it holds that every pack's settings are locked
    exactly when it is unticked (D907)."""
    locks = page.evaluate(LOCKS)
    assert {name: state for name, (on, state) in locks.items() if state != ("open" if on else "locked")} == {}
    return locks


def _rows(pack: mods.Pack) -> list[tuple]:
    """The rows the page shows ``pack``'s settings in, each slider with the
    L3 toggle that sits in its row (D909: a whole 0-or-1 setting named
    ``toggle_<other>`` pairs with ``<other>``), else ``None``."""
    names = {s.name for s in pack.sliders()}
    toggles = {s.name.removeprefix("toggle_"): s for s in pack.sliders()
               if s.name.startswith("toggle_") and s.name.removeprefix("toggle_") in names and s.whole == (0, 1)}
    return [(s, toggles.get(s.name)) for s in pack.sliders() if s not in toggles.values()]
SHOWN = """() => [...document.querySelectorAll("#packs .pack")].filter((item) => item.checkVisibility()
    && item.querySelector(".sliders").checkVisibility()).map((item) => {
        const settings = item.querySelector(".sliders").getBoundingClientRect(), row = item.getBoundingClientRect();
        const caption = document.querySelector("#patches > h2").getBoundingClientRect();
        return [item.dataset.pack, item.querySelector(".toggle").getAttribute("aria-expanded"), settings.left >= row.right,
                Math.abs(settings.top - row.top) < 1 && settings.top >= caption.bottom
                && settings.top < document.getElementById("patches").getBoundingClientRect().bottom];
    })"""
RELEASES = """() => new Set([...document.querySelectorAll("#packs .releases")].filter((r) => r.checkVisibility())
    .map((r) => Math.round(r.getBoundingClientRect().right))).size"""
# RELEASES with every opener in the platform's monospace, wider than 9em on each ("Settings · 13 ›"), then as it was.
WIDE_OPENERS = f"""() => {{ const openers = document.querySelectorAll("#packs .toggle");
    openers.forEach((t) => {{ t.style.fontFamily = "monospace"; }});
    const releases = ({RELEASES})();
    openers.forEach((t) => {{ t.style.fontFamily = ""; }});
    return releases; }}"""
LONG_READOUT = """() => {
    const readout = document.getElementById("status");
    readout.textContent = "a long refusal ".repeat(60);
    const scrolls = readout.scrollHeight > readout.clientHeight;
    const tall = document.querySelector("footer.build").getBoundingClientRect().height;
    readout.textContent = "";
    return [scrolls, tall < innerHeight / 5];
}"""
GROUPS = """(fold) => {
    [...document.querySelectorAll("#packs .group > summary")].find((s) => s.firstChild.textContent === fold)?.click();
    return [...document.querySelectorAll("#packs .group[data-category]")].map((group) => [group.open,
        group.querySelector(".tally").textContent, [...group.querySelectorAll(".pack")].filter((i) => i.checkVisibility()).length]);
}"""
BAR = """() => {
    const bar = document.querySelector("footer.build").getBoundingClientRect();
    const build = document.getElementById("build").getBoundingClientRect();
    return [Math.round(bar.bottom) === innerHeight, build.top >= bar.top && build.bottom <= innerHeight];
}"""


def test_the_page_opens_dark_with_its_areas_tabs_the_packs_in_groups_and_build_always_in_view(browser, site):
    """Design A with the owner's changes (Step 4.1h, D897-D903), on a
    system set to light: the page opens dark (D897), and its toggle picks
    light, which a page opened later in the same browser keeps from its
    first paint (theme.js sets it before the body, app.mjs held back here),
    until toggled back; faint text reads at least 4.5:1 on every ground it
    sits on, in light and in dark. The toolbar's tabs are the catalog's, in D901's order and
    only those whose area works (D902): Patches, Randomizer, About. The Patches tab
    groups the packs by Modkit's categories, in the catalog's order, each
    group folding and counting its packs ticked; a pack with settings has a
    Settings opener with the count of their rows (an L3 toggle sits in its
    setting's, D909), which shows them beside the list and
    closes the one open before (the first with settings opens first), and
    one without has none; the settings start beside their pack's row, in
    view however far the list is scrolled, the releases line up (in a
    wide font too), and a
    slider whose vanilla value is unread yet says nothing of it. Build and
    Save sit in a bar along the window's bottom, there however far the packs
    scroll, and at a narrow window's foot too; a long readout scrolls in it
    rather than growing it. The About tab says what AzurKit is, that it
    collects nothing and that the image never leaves the computer (and
    nothing anywhere in it about a host's logs, D883), its licence (the
    checkout's LICENSE), its credits (NOTICE.md's), its version and the
    commit its wheel was built from (this checkout's HEAD). No CSP
    violation, no request but GETs of the site's files."""
    from azurkit import __version__
    served = Site(browser, site, color_scheme="light", viewport={"width": 1280, "height": 600})
    try:
        page = served.open()
        assert page.evaluate(GROUND) == DARK
        _page.click(page, "theme")
        later = served.context.new_page()
        assert _page.first_paint(later, f"{served.origin}/") == LIGHT
        assert [page.evaluate(GROUND), later.evaluate(GROUND)] == [LIGHT, LIGHT]
        _page.click(later, "theme")
        assert [later.evaluate(GROUND), served.open().evaluate(GROUND)] == [DARK, DARK]

        catalog = sdk.catalog()
        assert [tab["title"] for tab in catalog["tabs"]] == ["Patches", "Randomizer", "Characters", "Data", "Tools",
                                                             "About"]
        assert page.evaluate("""() => [...document.querySelectorAll("#tabs [role=tab]")].map((tab) => [tab.textContent,
            tab.getAttribute("aria-selected"), document.getElementById(tab.getAttribute("aria-controls")).hidden])""") == [
            ["Patches", "true", False], ["Randomizer", "false", True], ["Characters", "false", True],
            ["Data", "false", True], ["Tools", "false", True], ["About", "false", True]]
        assert [c["title"] for c in catalog["categories"]] == ["Player", "Enemies", "Quality of Life"]
        grouped = [[p for p in mods.PACKS.values() if p.category == c["id"]] for c in catalog["categories"]]
        assert page.evaluate("""() => [...document.querySelectorAll("#packs .group[data-category]")].map((group) =>
            [group.querySelector("summary b").textContent, [...group.querySelectorAll(".pack")].map((item) =>
                [item.dataset.pack, item.querySelector(".toggle").hidden ? null : item.querySelector(".toggle").textContent])])
            """) == [[c["title"], [[p.name, f"Settings · {len(_rows(p))}" if p.sliders() else None] for p in packs]]
                     for c, packs in zip(catalog["categories"], grouped)]
        on = [[True, f"{sum(p.default_on for p in packs)} of {len(packs)} on", len(packs)] for packs in grouped]
        assert page.evaluate(GROUPS, "Quality of Life") == [*on[:2], [False, on[2][1], 0]]
        assert page.evaluate(GROUPS, "Quality of Life") == on
        _page.tick(page, ["fps_unlock"])
        assert [tally for _, tally, _ in page.evaluate(GROUPS, None)] == ["0 of 3 on", "0 of 2 on", "1 of 12 on"]
        assert page.evaluate(SHOWN) == [["player_physics", "true", True, True]]
        for theme in ("light", "dark"):   # the page is light here, then dark, then light again
            faint = page.evaluate(FAINT)
            assert {"line", "releases", "open releases", "version"} <= {what for what, _ in faint}, theme
            assert [(what, round(ratio, 2)) for what, ratio in faint if ratio < 4.5] == [], theme
            _page.click(page, "theme")
        assert page.evaluate(GROUND) == LIGHT
        page.evaluate("""() => document.querySelector('#packs .pack[data-pack="enemy_damage"] .toggle').click()""")
        assert page.evaluate(SHOWN) == [["enemy_damage", "true", True, True]]
        assert page.evaluate(RELEASES) == 1
        assert page.evaluate(WIDE_OPENERS) == 1   # in a font past 9em too (Linux's DejaVu was, Step 4.4ci2)
        assert "undefined" not in page.evaluate("() => document.getElementById('packs').textContent")

        assert page.evaluate(BAR) == [True, True]
        assert page.evaluate("() => { const tab = document.getElementById('patches'); tab.scrollTop = 1e6; "
                             "return tab.scrollTop; }") > 0
        assert page.evaluate(BAR) == [True, True]
        page.evaluate("""() => document.querySelector('#packs .pack[data-pack="qol_memory_budget"] .toggle').click()""")
        assert page.evaluate(SHOWN) == [["qol_memory_budget", "true", True, True]]
        assert page.evaluate(LONG_READOUT) == [True, True]
        page.set_viewport_size({"width": 700, "height": 600})
        assert page.evaluate("() => { scrollTo(0, 0); return document.documentElement.scrollHeight > innerHeight; }")
        assert page.evaluate(BAR) == [True, True]

        _page.click(page, "tab-about")
        shown = page.evaluate("""() => [document.getElementById("patches").hidden, document.getElementById("about").hidden,
            ...["privacy", "licence", "credits", "about-version", "about"].map((id) => document.getElementById(id).textContent)]""")
        assert shown[:2] == [True, False]
        assert not re.search(r"\bIP\b|visitor", shown.pop(), re.IGNORECASE)
        privacy, licence, credits, version = (" ".join(text.split()) for text in shown[2:])
        assert privacy == ("AzurKit collects nothing: it adds no logging, analytics or tracking. Your image never "
                           "leaves your computer: AzurKit reads it and builds right here.")
        assert licence == " ".join((_page.WEB.parent / "LICENSE").read_text(encoding="utf-8").split())
        notice = (_page.WEB.parent / "NOTICE.md").read_text(encoding="utf-8").splitlines()
        assert [line[3:] for line in notice if line.startswith("## ") and f"{line[3:]}." in credits] == [
            line[3:] for line in notice if line.startswith("## ")] != []
        head = subprocess.run(["git", "-C", str(_page.WEB.parent), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
        assert version == f"This is AzurKit {__version__}, built from commit {head[:12]}."
        for each in served.context.pages:
            _page.check_csp(each)
        assert served.stray() == []
    finally:
        served.close()


def test_a_phone_or_a_tablet_gets_one_plain_line_to_use_a_computer(browser, site):
    """D1000 (Step 4.3m): v1 is for computers. A phone (its touch screen
    emulated, ``(hover: none) and (pointer: coarse)``) shows one plain line
    saying to use a computer, atop the toolbar; a computer's page doesn't."""
    shown = """() => [getComputedStyle(document.getElementById("computers")).display !== "none",
        document.getElementById("computers").textContent]"""
    line = "AzurKit is for computers: open this page on a Mac or PC to use it."
    for options, seen in (({"is_mobile": True, "has_touch": True, "viewport": {"width": 390, "height": 844}}, True),
                          ({}, False)):
        served = Site(browser, site, **options)
        try:
            page = served.context.new_page()
            _page.load(page, f"{served.origin}/")
            assert page.evaluate(shown) == [seen, line], options
        finally:
            served.close()


def test_a_packs_settings_lock_until_it_is_ticked_and_its_l3_toggles_sit_in_their_rows(browser, site):
    """The owner's answers (Step 4.1i). D907: a pack's settings are locked
    (each field disabled, its value still shown) until its pack is ticked;
    ticking unlocks them with their values, unticking locks them again and
    keeps the values for later, and a build runs only with the ticked
    packs' (a link and a build's recipe set ticks and values together:
    test_a_share_link's). D909: each whole 0-or-1 setting named
    ``toggle_<other>`` shows as a small L3 toggle at the end of
    ``<other>``'s row, with a tooltip that says what it does, in place of
    a row of its own: player_physics shows its 13 sliders, each with its L3,
    and a toggle turned on is sent as 1. No CSP violation, no request but
    GETs of the site's files."""
    physics = mods.PACKS["player_physics"]
    rows = _rows(physics)
    assert (len(rows), sum(toggle is not None for _, toggle in rows), len(physics.sliders())) == (13, 13, 26)
    served = Site(browser, site)
    try:
        page = served.open()
        assert page.evaluate(ROWS, "player_physics") == [
            [s.name, s.label, toggle and [toggle.name, "L3", f"On: in game, a left-stick click (L3) flips {s.label} to "
                                                              "vanilla and back", True]] for s, toggle in rows]
        assert [rows for name, rows in ((p, page.evaluate(ROWS, p)) for p in mods.PACKS if p != "player_physics")
                if any(l3 for _, _, l3 in rows)] == []
        assert _locks(page)["player_physics"] == [False, "locked"]
        values = {"jump_speed_scale": "1.5", "toggle_jump_speed_scale": "1", "toggle_gravity": "1"}
        _page.tick(page, ["player_physics"], {"player_physics": values})
        assert _locks(page)["player_physics"] == [True, "open"]
        typed = _page.ticked(page)["player_physics"]
        assert {name: typed[name] for name in values} == values
        _page.click(page, "share")   # what the page would build: only the ticked packs, the toggles as 1
        assert _page.until(page, "() => azurkit.link").endswith(sdk.preset_encode(
            {"packs": {"player_physics": {"jump_speed_scale": 1.5, "toggle_jump_speed_scale": 1, "toggle_gravity": 1}}}))
        moved = """(pack) => {
            document.querySelector(`#packs input[data-pack="${pack}"]`).click();
            return document.querySelector("#packs .moved:not(:empty)")?.textContent ?? null;
        }"""
        up64, up256 = "qol_memory_upper64", "qol_memory_upper256"   # a tick says what it moved, in mods.settle's words
        on = list(_page.ticked(page))
        assert page.evaluate(moved, up256) == " ".join(mods.settle(on, [up256])[1])
        assert page.evaluate(moved, up64) == " ".join(mods.settle(on + [up64, "qol_memory_upper64_gpu", up256], (), [up64])[1])
        assert page.evaluate(moved, "fps_unlock") is None
        assert page.evaluate(f"""() => document.querySelector('#packs .pack[data-pack="{up256}"] .needs').textContent"""
                             ) == " Needs qol_memory_upper64, qol_memory_upper64_gpu."
        _page.tick(page, ["fps_unlock"])
        assert [_locks(page)[name] for name in ("player_physics", "fps_unlock")] == [[False, "locked"], [True, "open"]]
        assert page.evaluate("""() => [...document.querySelectorAll('#packs .pack[data-pack="player_physics"] input[data-slider]')]
            .map((field) => field.type === "checkbox" ? String(Number(field.checked)) : field.value)""") == [
            typed[x.name] for s, toggle in rows for x in (s, toggle) if x]
        _page.tick(page, ["player_physics"])
        assert _page.ticked(page)["player_physics"] == typed
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


STORED = "() => JSON.parse(localStorage.getItem('azurkit.setup'))"   # the site's remembered setup (D915)
STATUS = "() => document.querySelector('#status').textContent"
RESET = "() => document.getElementById('reset').disabled"
KEEP = "() => document.getElementById('remember').checked"   # Remember settings (D1156)
# A pack's settings as their fields read: {setting: its box's text, or an L3 toggle's "1" on, "0" off}.
FIELDS = """(pack) => Object.fromEntries([...document.querySelectorAll(`#packs .pack[data-pack="${pack}"] input[data-slider]`)]
    .map((field) => [field.dataset.slider, field.type === "checkbox" ? String(Number(field.checked)) : field.value]))"""


def _remembered(page, setup: dict | None) -> None:
    """Wait for the page's storage to hold ``setup`` (``None``: nothing)."""
    end = time.monotonic() + 10
    while (got := page.evaluate(STORED)) != setup:
        assert time.monotonic() < end, got
        time.sleep(0.1)


def _reload(page) -> None:
    _page.load(page)
    _page.until(page, "() => globalThis.azurkit?.ready", 120)


def test_a_revisit_starts_at_the_defaults_with_remember_settings_unticked(browser, site):
    """D1156: Remember settings, after Reset to defaults in the bottom bar,
    is off by default, and so a reload starts at the defaults with nothing
    kept and nothing said, a setup AzurKit 1.0 kept (no choice stored)
    removed unread. Ticked, the page keeps its setup at once; unticked, it
    forgets it at once, and the choice is kept for the next visit. Reset to
    defaults with nothing kept doesn't say a setup was forgotten."""
    defaults = [name for name, pack in mods.PACKS.items() if pack.default_on]
    plain = [defaults, "", None, False]
    served = Site(browser, site)
    try:
        page = served.open()
        page.evaluate("(text) => localStorage.setItem('azurkit.setup', text)",
                      json.dumps({"ticked": ["fps_unlock"], "values": {}, "xbr": []}))   # AzurKit 1.0's
        _reload(page)
        assert [list(_page.ticked(page)), page.evaluate(STATUS), page.evaluate(STORED), page.evaluate(KEEP)] == plain
        _page.tick(page, ["fps_unlock"], {"fps_unlock": {"target_fps": "120"}})
        _reload(page)   # its pagehide would keep the setup now
        assert [list(_page.ticked(page)), page.evaluate(STATUS), page.evaluate(STORED), page.evaluate(KEEP)] == plain
        _page.tick(page, ["fps_unlock"])
        _page.click(page, "remember")
        assert page.evaluate(STORED) == {"ticked": ["fps_unlock"], "values": {}, "xbr": []}
        _page.click(page, "remember")
        assert page.evaluate(STORED) is None
        _page.click(page, "reset")
        assert page.evaluate(STATUS) == ("Reset to the defaults: the packs on by default, every setting at its default, "
                                         "Randomize off.")
        _page.tick(page, ["fps_unlock"])
        _reload(page)
        assert [list(_page.ticked(page)), page.evaluate(STATUS), page.evaluate(STORED), page.evaluate(KEEP)] == plain
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


def test_a_revisit_restores_the_setup_with_remember_settings_ticked_until_reset_and_names_what_it_drops(browser, site):
    """D915 with Remember settings ticked (D1156): the page keeps its ticks
    and settings in the browser's storage
    (each setting changed from its default, an unticked pack's too, D907:
    names and numbers, nothing of the image), and a reload brings them back
    before an image is picked, unmarked and locked as they were, the box
    still ticked, and says
    so. Reset to defaults, in the bottom bar and off while the page is at
    them, ticks the packs on by default, sets every setting to its default
    and forgets the setup, the box left ticked, so a reload opens at the defaults. A remembered
    pack or setting the catalog no longer has is dropped and named in the
    status line, the rest restored. A share link wins over the remembered
    setup and becomes it; once the page changes, the address drops the link
    and a reload restores the change. No CSP violation, no request but GETs
    of the site's files."""
    defaults = [name for name, pack in mods.PACKS.items() if pack.default_on]
    served = Site(browser, site)
    try:
        page = served.open()
        assert [page.evaluate(STORED), page.evaluate(STATUS), page.evaluate(RESET)] == [None, "", True]
        _page.click(page, "remember")
        fresh = page.evaluate(FIELDS, "player_physics")
        values = {"jump_speed_scale": "1.5", "toggle_gravity": "1"}
        _page.tick(page, ["fps_unlock", "player_physics"],
                   {"fps_unlock": {"target_fps": "120"}, "player_physics": values})
        _page.tick(page, ["fps_unlock"])   # player_physics' settings lock, their values kept (D907)
        _remembered(page, {"ticked": ["fps_unlock"], "values": {
            "fps_unlock": {"target_fps": 120}, "player_physics": {"jump_speed_scale": 1.5, "toggle_gravity": 1}},
            "xbr": []})
        shown = [_page.ticked(page), page.evaluate(FIELDS, "player_physics")]
        assert fresh | values == shown[1] != fresh
        _reload(page)
        assert [_page.ticked(page), page.evaluate(FIELDS, "player_physics")] == shown
        assert [page.evaluate(STATUS), _page.marked(page), page.evaluate(RESET), page.evaluate(KEEP)] == [
            "Restored your last setup: 1 pack on. Reset to defaults clears it.", [], False, True]
        assert [_locks(page)[name] for name in ("fps_unlock", "player_physics")] == [[True, "open"], [False, "locked"]]

        _page.click(page, "reset")
        assert [list(_page.ticked(page)), page.evaluate(FIELDS, "player_physics"), page.evaluate(RESET),
                page.evaluate(KEEP)] == [defaults, fresh, True, True]
        _remembered(page, None)
        assert page.evaluate(STATUS) == ("Reset to the defaults: the packs on by default, every setting at its default, "
                                         "Randomize off; the remembered setup is forgotten.")   # a change is kept again
        _reload(page)
        assert [list(_page.ticked(page)), page.evaluate(STATUS)] == [defaults, ""]

        stale = {"ticked": ["qol_retired", "fps_unlock"],
                 "values": {"player_physics": {"gone_setting": 2, "jump_speed_scale": 1.25}}, "xbr": []}
        page.evaluate("(text) => localStorage.setItem('azurkit.setup', text)", json.dumps(stale))
        _reload(page)
        assert [page.evaluate(STATUS), list(_page.ticked(page)), page.evaluate(FIELDS, "player_physics") == fresh | {
            "jump_speed_scale": "1.25"}] == ["Restored your last setup, without qol_retired (no such pack); "
                                             "player_physics.gone_setting (no such setting)", ["fps_unlock"], True]
        _remembered(page, {"ticked": ["fps_unlock"], "values": {"player_physics": {"jump_speed_scale": 1.25}},
                           "xbr": []})

        linked = served.context.new_page()
        _page.load(linked, f"{served.origin}/{sdk.preset_encode({'packs': {'qol_alloc_race': {}}})}")
        _page.until(linked, "() => globalThis.azurkit?.loaded")
        assert list(_page.ticked(linked)) == ["qol_alloc_race"]
        _remembered(linked, {"ticked": ["qol_alloc_race"], "values": {}, "xbr": []})
        _page.tick(linked, ["fps_unlock", "qol_alloc_race"])
        _remembered(linked, {"ticked": ["fps_unlock", "qol_alloc_race"], "values": {}, "xbr": []})
        assert linked.evaluate("() => location.hash") == ""
        _reload(linked)
        assert list(_page.ticked(linked)) == ["fps_unlock", "qol_alloc_race"]
        for each in (page, linked):
            _page.check_csp(each)
        assert served.stray() == []
    finally:
        served.close()


COMMUNITY = """() => [...document.querySelectorAll("#char-community .entry")].map((e) => [e.dataset.entry,
    e.querySelector(".community").textContent.trim(), e.children[1].textContent,
    [...e.querySelectorAll(".model")].map((m) => m.dataset.model)])"""


def test_the_saves_section_round_trips_a_slot(browser, site, tmp_path):
    """Saves on the site (Step 4.7e): a slot's folder opens with no image, its text saves' lines editable; an edit is
    saved as a zip, the same bytes the engine's CPython gives (no bytes of the slot leave the page but the download);
    an xemu HDD image's two slots read, read-only; signing is greyed with its line until an image is picked. No CSP
    violation."""
    from azurkit.tools import saves as savekit

    from tests import test_saves as made

    folder = tmp_path / "slot" / made.ID
    for path, data in made._files().items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data)
    hdd = made._qcow2(tmp_path / "hdd.qcow2", made._Fatx({"UDATA": {"4d530007": {
        made.ID: made._slot_tree(1), "FEDCBA987654": made._slot_tree(2)}}}).chunks())
    slot, _ = savekit.edit(savekit.Slot.read(folder), [{"file": "magic.sav", "line": 0, "value": "2.000000"}])
    served = Site(browser, site)
    try:
        page = served.open()
        page.evaluate("() => document.getElementById('tab-tools').click()")
        assert page.evaluate("() => [document.getElementById('saves-sign').disabled, document.getElementById("
                             "'saves-sign-line').textContent.startsWith('Choose your image first')]") == [True, True]
        page.evaluate("""(given) => azurkit.saves.folder(Object.entries(given).map(([path, hex]) => {
            const file = new File([Uint8Array.from(hex.match(/../g) ?? [], (h) => parseInt(h, 16))], path.split('/').pop());
            Object.defineProperty(file, 'webkitRelativePath', { value: path });
            return file; }))""", {f"{made.ID}/{path}": data.hex() for path, data in {
            **made._files(), ".DS_Store": b"host"}.items()})
        _page.until(page, "() => azurkit.saves.state.slot?.id", 120)
        assert sorted(f["path"] for f in page.evaluate("() => azurkit.saves.state.slot.files")) == sorted(made._files())
        page.evaluate("""() => { const box = document.querySelector('#saves-rows input[data-file="magic.sav"]');
            box.value = '2.000000'; box.dispatchEvent(new Event('change', { bubbles: true })); }""")
        _page.until(page, "() => /changed: sign it again/.test(document.getElementById('status').textContent)", 60)
        with page.expect_download(timeout=120_000) as caught:
            page.evaluate("() => document.getElementById('saves-save').click()")
        assert caught.value.suggested_filename == f"{made.ID}.zip"
        with open(caught.value.path(), "rb") as f:
            assert f.read() == slot.zip()
        caught.value.delete()
        _page.pick(page, "#saves-hdd", hdd)
        _page.until(page, "() => azurkit.saves.state.slots.length === 2", 120)
        assert page.evaluate("() => azurkit.saves.state.slots.map((s) => s.id)") == sorted((made.ID, "FEDCBA987654"))
        _page.check_csp(page)
    finally:
        served.close()


def test_a_build_with_a_replaced_file_is_the_apps_image(browser, site, usa_iso, tmp_path):
    """Replace files on the site (Step 4.7d): greyed with its line until an image is picked; a file the build owns is
    refused by name; a pick's read moves the bottom bar from 0 to 100 % under its "Reading <file>" line (D980: a
    148 MB file's passes 1 s in Safari's read model, S54/lag); a picked File builds the image the engine builds on
    CPython for the same bytes, by the whole
    image's sha256; a share link refuses it by name; a mods file loaded in a fresh page asks for the file again and
    stops a Build by name, reading nothing."""
    from azurkit.edits import files

    name = "gamedata/fx.xbr"
    mine = tmp_path / "mine.bin"
    mine.write_bytes(b"a file of the player's own " * 30000)
    entry = files.entry(name, mine.read_bytes())
    defaults = {pack["name"]: {} for pack in sdk.catalog()["packs"] if pack["default_on"]}
    made, expected = sdk.image({"iso": str(usa_iso), "packs": defaults, "files": [entry]},
                               picked={name: mine.read_bytes()})
    out = tmp_path / "cpython.iso"
    sdk.save(made, str(out))
    with open(out, "rb") as f:
        want = hashlib.file_digest(f, "sha256").hexdigest()
    out.unlink()
    served = Site(browser, site)
    try:
        page = served.open()
        page.evaluate("() => document.getElementById('tab-tools').click()")
        assert page.evaluate("""() => [document.getElementById('replace-path').disabled,
            document.getElementById('replace-line').textContent]""") == [True, "Choose your image first (1.)"]
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa' && !document.getElementById('replace-path').disabled", 300)
        page.evaluate("() => { document.getElementById('replace-path').value = 'default.xbe'; }")
        _page.pick(page, "#replace-file", mine)
        _page.until(page, "() => /default.xbe isn't replaced: .*the packs' file/.test(document.getElementById('status').textContent)", 120)
        page.evaluate(f"""() => {{ document.getElementById('replace-path').value = {json.dumps(name)};
            const bar = document.getElementById('progress'), line = document.getElementById('progress-line');
            globalThis.readBar = [];
            new MutationObserver(() => bar.hasAttribute('value') && readBar.push(line.textContent))
              .observe(bar, {{ attributes: true, attributeFilter: ['value'] }}); }}""")
        _page.pick(page, "#replace-file", mine)
        _page.until(page, "() => azurkit.replace.entries().length === 1", 120)
        assert page.evaluate("() => azurkit.replace.entries()") == [entry]
        shown = page.evaluate("() => readBar")
        assert shown[0] == "Reading mine.bin… 0 %" and shown[-1] == "Reading mine.bin… 100 %", shown
        page.evaluate("() => document.getElementById('share').click()")
        _page.until(page, "() => /never carries a replaced file/.test(document.getElementById('status').textContent)", 60)
        page.evaluate("() => document.getElementById('tab-patches').click()")
        page.evaluate("() => document.getElementById('build').click()")
        assert _page.built(page)["result"] == expected["result"]   # Save open: Firefox greys it while its Blob is made
        with page.expect_download(timeout=600_000) as caught:
            page.evaluate("() => document.getElementById('save').click()")
        with open(caught.value.path(), "rb") as f:
            assert hashlib.file_digest(f, "sha256").hexdigest() == want
        caught.value.delete()
        _page.until(page, "() => azurkit.ready", 300)
        mods = tmp_path / "mods.json"
        mods.write_text(sdk.mods_file({"recipe": {"packs": defaults, "files": [entry]}})["text"], encoding="utf-8")
        fresh = served.open()
        _page.pick(fresh, "#iso", usa_iso)
        _page.until(fresh, "() => azurkit.vanilla?.release === 'usa'", 300)
        fresh.evaluate("() => document.getElementById('tab-tools').click()")
        _page.pick(fresh, "#tools-mods-file", mods)
        _page.until(fresh, "() => azurkit.replace.entries().length === 1", 120)
        assert "Not picked here" in fresh.evaluate("() => document.getElementById('replace-rows').textContent")
        fresh.evaluate("() => document.getElementById('build').click()")
        _page.until(fresh, "() => /isn't picked in this session/.test(document.getElementById('status').textContent)", 300)
        _page.check_csp(fresh)
    finally:
        served.close()


def test_the_sites_patches_tab_installs_a_community_pack_from_its_own_address_and_builds_it(
        browser, site, usa_iso, tmp_path, monkeypatch):
    """The site's community group (Step 4.3k): read from the site's own address when first opened, a pack's tick greyed
    until its Install, which refuses a pack.json no community pack may be by name and keeps nothing; ticked, it sets and
    locks the rows it names; a Build carries its layer and its game files are the app's engine's for the same recipe;
    a link carries it by its sha12 and opens with it ticked; a reopened page restores it, handed to its engine first,
    and its untick gives the rows back."""
    from azurkit import sdk

    from tests import test_community as made

    source, manifest = made._installed(tmp_path, monkeypatch, {
        "hard": made.HARD, "bad": made._pack({"qol_memory_upper64_gpu": {}})})
    sdk.content_install({"id": "hard", "source": str(source)})
    defaults = {pack["name"]: {} for pack in sdk.catalog()["packs"] if pack["default_on"]}   # the page's own ticks
    expected = sdk.image({"iso": str(usa_iso), "packs": defaults, "community": [{"id": "hard"}]})[1]["result"]
    served = Site(browser, site)

    def content(route, request) -> None:
        rel = urllib.parse.urlsplit(request.url).path.removeprefix("/content-test/")
        route.fulfill(path=str(source / rel)) if (source / rel).is_file() else route.fulfill(status=404, body="")
    served.context.route(f"{served.origin}/content-test/**", content)
    row = """document.querySelector('.cpack[data-community="hard"]')"""
    hp = """document.getElementById("player_max_hp.starting_hp")"""
    locked = f"() => {hp}.value === '150' && {hp}.disabled && {hp}.closest('.pack').classList.contains('owned')"
    try:
        page = served.open()
        page.evaluate("() => { localStorage.setItem('azurkit.content_source', './content-test/'); "
                      "localStorage.setItem('azurkit.remember', '1'); }")   # Remember settings ticked (D1156)
        page = served.open()
        _page.until(page, "() => azurkit.ready", 300)
        assert page.evaluate(f"() => {row}") is None   # nothing read until the group opens
        page.evaluate("() => { document.getElementById('community-group').open = true; }")
        _page.until(page, f"() => {row}?.querySelector('input').disabled && {row}.textContent.includes('Install it first')",
                    120)
        page.evaluate("""() => document.querySelector('.cpack[data-community="bad"] button').click()""")
        _page.until(page, "() => document.getElementById('status').textContent.startsWith('bad: nothing')", 120)
        assert "needs 'qol_memory_upper64'" in page.evaluate("() => document.getElementById('status').textContent")
        page.evaluate(f"() => {row}.querySelector('button').click()")
        _page.until(page, f"() => {row}?.querySelector('input') && !{row}.querySelector('input').disabled", 120)
        page.evaluate(f"() => {row}.querySelector('input').click()")
        _page.until(page, locked, 60)
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        page.evaluate("() => document.getElementById('build').click()")
        _page.until(page, "() => azurkit.build || document.getElementById('status').classList.contains('error')", 600)
        assert page.evaluate("() => azurkit.build.report.result") == expected
        assert " · community hard" in page.evaluate("() => document.getElementById('status').textContent")
        _page.until(page, "() => azurkit.ready", 300)
        page.evaluate("() => document.getElementById('share').click()")
        link = _page.until(page, "() => azurkit.link", 60)
        _page.until(page, "() => azurkit.kept?.includes('community')", 60)
        _page.check_csp(page)
        page = served.open()   # the remembered setup: the engine has the pack before the setup comes back
        _page.until(page, "() => azurkit.ready", 300)
        _page.until(page, locked, 60)
        page.evaluate("() => localStorage.removeItem('azurkit.setup')")
        page = served.context.new_page()
        _page.load(page, link)
        _page.until(page, "() => globalThis.azurkit?.ready", 300)
        _page.until(page, locked, 120)
        assert page.evaluate("() => azurkit.community.pins()")[0]["id"] == "hard"
        page.evaluate("() => { document.getElementById('community-group').open = true; }")
        _page.until(page, f"() => {row}?.querySelector('input')?.checked", 120)
        page.evaluate(f"() => {row}.querySelector('input').click()")
        _page.until(page, f"() => !{hp}.closest('.pack').classList.contains('owned') && !{hp}.disabled", 60)
        _page.check_csp(page)
    finally:
        served.close()


def test_the_characters_tab_lists_species_variants_and_weapons_and_installs_from_the_source(
        browser, site, usa_iso, tmp_path):
    """The Characters tab (Step 4.3d, D877, D913) on the site: with the image picked it lists the 178 species the
    player can wear, the 73 untested greyed, each row's grade read without colour too (its mark and its words as its
    title); Azurik-Custom-Content's entries (its source served from the site's own
    address) come under the species, beside Content from (D1035), each marked
    community; Install of an entry whose
    file isn't its manifest's sha256, or is past its listed size (read no further, Step 4.3m, SEC-9), is refused by
    name and keeps nothing, and Beamlord's installs, its variant
    then listed under it, installed v1, and a page opened again hands it to its engine before the tab is opened (a
    build from another tab reads it); a species picked shows its Weapon box and its two pictures (the site's own,
    Step 4.3f), and Content from and its Reset stay in the list's column, the pictures in theirs and every G4 button
    in view at any width, the tab never scrolling sideways; a field the engine refuses by name (a Scale that is no
    number), and a second refusal after it, leaves G4 and the Weapon box live, the image read (D979). No CSP
    violation, and no request but GETs of the site's files and the source's."""
    from azurkit.tools.characters import _player_variants, content, picker

    repo = tmp_path / "repo"
    files = {"variants/beamlord/variant.json": json.dumps({"beamlord": json.loads(
        _player_variants.BUILTIN.read_text(encoding="utf-8"))["beamlord"]}).encode(), "variants/tamper/variant.json": b"{}",
             "variants/big/variant.json": b"{}"}
    for path, data in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_bytes(data)
    entry = {"author": "Azurik-Modding-Hub", "licence": "MIT", "version": 1, "requires": []}
    manifest = content.filled({"format": content.FORMAT, "schema_version": 1, "entries": [
        entry | {"id": "beamlord", "kind": "variant", "title": "Beamlord", "files": [{"path": "variants/beamlord/variant.json"}]},
        entry | {"id": "tamper", "kind": "variant", "title": "Tampered", "files": [
            {"path": "variants/tamper/variant.json"}]},
        entry | {"id": "big", "kind": "variant", "title": "Too big", "files": [{"path": "variants/big/variant.json"}]}]},
        lambda path: (repo / path).read_bytes())
    (repo / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (repo / "variants/tamper/variant.json").write_bytes(b"[]")   # its bytes other than its manifest's
    (repo / "variants/big/variant.json").write_bytes(b"{}" + b" " * 64)   # past its manifest's size
    served = Site(browser, site)

    def source(route, request) -> None:
        served.routed.append((request.method, request.url, request.post_data_buffer))
        rel = urllib.parse.urlsplit(request.url).path.removeprefix("/content-test/")
        route.fulfill(path=str(repo / rel)) if (repo / rel).is_file() else route.fulfill(status=404, body="")
    served.context.route(f"{served.origin}/content-test/**", source)
    try:
        page = served.open()
        page.evaluate("() => localStorage.setItem('azurkit.content_source', './content-test/')")
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.click(page, "tab-characters")
        _page.until(page, "() => Boolean(azurkit.characters.state.view?.from) && azurkit.characters.state.view.community"
                          ".length === 3", 300)   # the engine's answer, the image read
        _page.click(page, "char-objects")   # every species, the objects too (D1034)
        assert page.evaluate("""() => [document.querySelectorAll("#char-species .model").length,
            document.querySelectorAll("#char-species .model.untested").length]""") == [178, 73]
        marks = page.evaluate("""() => [...document.querySelectorAll("#char-species .model")].map((m) =>
            [m.dataset.grade, getComputedStyle(m, "::after").content, m.title])""")
        assert {(grade, mark) for grade, mark, _ in marks} == {("green", '" ✓"'), ("yellow", '" ~"'), ("unseen", '" ?"')}
        assert [t for grade, _, t in marks if not t.startswith(picker.GRADE_WORDS[grade])] == []
        for theme in ("dark", "light"):   # each grade's colour at least 4.5:1 on its row's ground, the chosen row's too
            graded = page.evaluate(FAINT, True)
            assert len(graded) > 178 and [(what, round(r, 2)) for what, r in graded if r < 4.5] == [], theme
            assert [(g, on, round(r, 2)) for g, on, r in page.evaluate(GRADE_GROUNDS) if r < 4.5] == [], theme
            _page.click(page, "theme")
        assert page.evaluate(COMMUNITY) == [["beamlord", "community", "Install", []],
                                            ["tamper", "community", "Install", []], ["big", "community", "Install", []]]
        page.evaluate("""() => document.querySelector('#char-community .entry[data-entry="tamper"] button').click()""")
        _page.until(page, "() => document.getElementById('status').textContent.startsWith('Tampered: nothing')", 120)
        assert re.search(r"tamper: variants/tamper/variant\.json's sha256 [0-9a-f]{12} isn't the manifest's",
                         page.evaluate("() => document.getElementById('status').textContent"))
        _page.until(page, """() => !document.querySelector('#char-community .entry[data-entry="big"] button').disabled""")
        page.evaluate("""() => document.querySelector('#char-community .entry[data-entry="big"] button').click()""")
        _page.until(page, "() => document.getElementById('status').textContent.startsWith('Too big: nothing')", 120)
        assert page.evaluate("() => document.getElementById('status').textContent") == (
            "Too big: nothing was installed: variants/big/variant.json: past the 2 bytes its manifest lists")
        _page.until(page, """() => !document.querySelector('#char-community .entry[data-entry="beamlord"] button').disabled""")
        page.evaluate("""() => document.querySelector('#char-community .entry[data-entry="beamlord"] button').click()""")
        _page.until(page, """() => document.querySelector('#char-community .entry[data-entry="beamlord"] .model')""", 120)
        assert page.evaluate(COMMUNITY) == [["beamlord", "community", "installed v1", ["beamlord"]],
                                            ["tamper", "community", "Install", []], ["big", "community", "Install", []]]
        page.evaluate("() => document.querySelector('#char-species .model[data-model=\"keylord\"]').click()")
        _page.until(page, "() => azurkit.characters.state.view?.chosen.name === 'keylord'", 120)
        assert page.evaluate("() => document.querySelectorAll('#char-weapon option').length") > 1
        for width in (1280, 1024, 900, 700):   # the list gives way, then the options drop under it, then one column
            page.set_viewport_size({"width": width, "height": 800})
            assert page.evaluate(CHARS_LAYOUT) == [True] * 4, width
        _page.until(page, "() => document.getElementById('char-preview-note').textContent.startsWith('From the')", 300)
        assert page.evaluate("""() => ["char-front", "char-back"].map((id) => document.getElementById(id).getContext("2d")
            .getImageData(0, 0, 160, 160).data.some((v, i) => i % 4 === 3 && v > 0))""") == [True, True]
        scale = """(text) => { const box = document.getElementById("char-scale"); box.value = text;
            box.dispatchEvent(new Event("change")); }"""
        for bad in ("abc", "abcd"):   # refused fields, the image read: G4 and the weapons stay live each time (D979)
            page.evaluate(scale, bad)
            _page.until(page, f"""() => !document.getElementById('char-refused').hidden
                && document.getElementById('char-refused').textContent.includes("scale '{bad}'")""", 120)
            assert page.evaluate("""() => [[...document.querySelectorAll("#char-numbers .g4")].map((b) => b.disabled),
                document.getElementById("char-g4-note").textContent, document.getElementById("char-weapon").disabled]""") == [
                [False] * 4, "G4 sets a number so the body matches garret4.", False]
        page.evaluate(scale, "1")
        _page.until(page, "() => document.getElementById('char-refused').hidden && Boolean(azurkit.characters.state.view?.from)", 120)
        for act, left in (("document.getElementById('char-reset')", {"species": "keylord"}),   # a G4 still measuring: dropped
                          ("document.querySelector('#char-species .model[data-model=\"garret4\"]')", None)):
            assert page.evaluate(f"""() => {{ document.getElementById("char-g4-scale").click(); {act}.click();
                return azurkit.characters.state.matching; }}""") is True
            _page.until(page, """() => !azurkit.characters.state.matching && azurkit.characters.state.view?.asked
                === JSON.stringify(azurkit.characters.state.character)""", 300)
            assert page.evaluate("() => [azurkit.characters.character(), document.getElementById('char-scale').value]") == [left, "1"]
        assert page.evaluate("() => azurkit.violations") == []
        assert [r for r in served.stray() if not r.startswith(f"GET {served.origin}/content-test/")] == []
        again = served.open()   # this browser's storage, the Characters tab never opened
        assert _page.until(again, """async () => !azurkit.characters.state.opened && (await azurkit.engine.call(
            "pickers", {given: {iso: null}})).community.map((e) => `${e.id} ${e.state}`).join() === "beamlord installed"
            """, 120)
    finally:
        served.close()


MINE = "https://content.example.test/azurik"
"""A player's own content repository (D1135: any https address), typed with no trailing ``/``."""


def test_the_released_site_reads_community_content_from_github_or_any_https_repository_and_builds_booblord(
        browser, site, usa_iso):
    """D1135 (the owner: "users should be able to load any community content repo they want"): the site as
    ``release.yml`` builds it (``scripts/web_tools.py --site DIR``: no content of its own) reads Azurik-Custom-Content
    from GitHub at the visit, ``sdk.SOURCE`` on raw.githubusercontent.com, another origin, which its CSP's
    ``connect-src 'self' https:`` lets it fetch: here a route stands in for GitHub, answering as it does
    (``Access-Control-Allow-Origin: *``) with the files a second local server serves from a clone of the repository
    (CI's, else the one beside the main checkout). With nothing set Content from is that address, its list holds
    booblord and her Install checks each file. A player's own https repository (:data:`MINE`, another origin again)
    is read with no warning, an entry installs from it, and it is remembered for the next visit; booblord's Update
    from it is refused by name (SEC-8: an Update comes from where she was installed). A plain http source is refused
    by name before any fetch, and a read that fails (a 404, a host that lets only another site read it, no network)
    says what failed while the page works on, the last list read shown. Reset goes back to GitHub's, and booblord's
    Build at the page's defaults is G3's ``player-character=booblord`` golden, file for file. No CSP violation, and no
    request but GETs of the site's files and the sources'."""
    from tests.test_characters import _content_source

    clone = Path(_content_source())
    assert (clone / "manifest.json").is_file(), f"{clone}: a clone of Azurik-Custom-Content stands in for GitHub's"
    manifest = json.loads((clone / "manifest.json").read_text(encoding="utf-8"))
    titles = {e["id"]: e["title"] for e in manifest["entries"]}
    newer = next(e["version"] for e in manifest["entries"] if e["id"] == "booblord") + 1
    theirs = json.dumps(manifest | {"entries": [e | {"version": newer} if e["id"] == "booblord" else e
                                                for e in manifest["entries"]]})   # booblord one version up
    golden = record_goldens.recorded("pipelines.json")["randomize-full:player-character=booblord"]
    changed = {path: sha for path, sha in golden.items() if path in gate.USA.files and sha != gate.USA.files[path][1]}
    files, heard, asks = _page.Served(clone), [], set()   # asks: each request's method and body
    served = Site(browser, site)

    def repository(route, request) -> None:   # GitHub's, MINE's and three that fail, each from files' server
        heard.append(request.url)
        asks.add((request.method, request.post_data_buffer))
        host = urllib.parse.urlsplit(request.url).hostname
        if host == "offline.example.test":
            return route.abort("internetdisconnected")
        cors = {"Access-Control-Allow-Origin": "https://another.example.test" if host == "closed.example.test" else "*"}
        #   (a fulfil with none gets Playwright's own, the page's origin: closed's lets only another site read it)
        base = next((b for b in (sdk.SOURCE, f"{MINE}/", "https://closed.example.test/") if request.url.startswith(b)),
                    None)
        if base is None:
            return route.fulfill(status=404, body="", headers=cors)
        if base == f"{MINE}/" and request.url == f"{base}manifest.json":
            return route.fulfill(body=theirs, content_type="application/json", headers=cors)
        got = served.context.request.get(f"{files.url}/{request.url.removeprefix(base)}")   # the driver's fetch
        route.fulfill(response=got, headers=got.headers | cors)
    served.context.route(re.compile(r"^https://(raw\.githubusercontent\.com|[a-z]+\.example\.test)/"), repository)
    entry = """document.querySelector('#char-community .entry[data-entry="%s"]')"""
    note, box = "document.getElementById('char-content-note').textContent", "document.getElementById('char-source')"
    typed = f"(url) => {{ {box}.value = url; {box}.dispatchEvent(new Event('change')); }}"
    read = f"() => !{note}.startsWith('Reading') && !azurkit.characters.state.installing && [{box}.value, {note}]"
    state = lambda name: f"{entry % name}?.children[1].textContent"  # noqa: E731   its Install, Update or installed
    try:
        page = served.open()
        _page.click(page, "tab-characters")
        _page.until(page, f"() => {state('booblord')} === 'Install' && !{entry % 'booblord'}.querySelector('button')"
                          ".disabled", 300)
        assert _page.until(page, read, 60) == [sdk.SOURCE, ""]   # GitHub's, with no line
        _page.answer(page, f"() => {entry % 'booblord'}.querySelector('button').click()")
        _page.until(page, f"() => {state('booblord')} === 'installed v{newer - 1}'", 600)
        _page.answer(page, typed, MINE)
        assert _page.until(page, f"() => {state('booblord')} === 'Update to v{newer}' && ({read})()", 120) == [
            f"{MINE}/", ""]   # read with no warning
        _page.answer(page, f"() => {entry % 'beamlord'}.querySelector('button').click()")
        _page.until(page, f"() => {state('beamlord')} === 'installed v1' && {entry % 'beamlord'}.querySelector('.model')",
                    120)
        _page.answer(page, f"() => {entry % 'booblord'}.querySelector('button').click()")
        assert _page.until(page, "() => !azurkit.characters.state.installing && document.getElementById('status')"
                                 ".textContent.includes('nothing was installed') && document.getElementById('status')"
                                 ".textContent", 600) == (
            f"{titles['booblord']}: nothing was installed: booblord: it was installed from {sdk.SOURCE}, not {MINE}/: an "
            "Update comes from where it was installed (clear the installed content to take it from elsewhere)")
        _page.check_csp(page)
        _page.within(served.context, page._impl_obj.close(), _page.STALL, "the first page's close")
        asked = heard.count(f"{MINE}/manifest.json")
        page = served.open()   # the next visit: Content from remembered, and read from it
        assert _page.answer(page, f"() => {box}.value") == f"{MINE}/"
        _page.pick(page, "#iso", usa_iso)
        _page.click(page, "tab-characters")
        _page.until(page, f"() => {state('booblord')} === 'Update to v{newer}' && ({read})()", 300)
        assert heard.count(f"{MINE}/manifest.json") == asked + 1
        last = " Every built-in model below works. (the last list read is shown)"
        for bad, why in [
                ("http://content.example.test/azurik/", "http://content.example.test/azurik/ is plain http: the site "
                 "reads an https address (the desktop app reads http on this computer too)."),
                ("https://gone.example.test/", "Couldn't reach the community list at https://gone.example.test/ "
                 "(HTTP 404: no manifest.json there)."),
                *((f"https://{host}.example.test/", f"Couldn't reach the community list at https://{host}.example.test/ "
                   "(no answer: offline, or it doesn't let other sites read it).") for host in ("closed", "offline"))]:
            _page.answer(page, typed, bad)
            assert _page.until(page, read, 120) == [bad, why + last], bad
            assert _page.answer(page, f"""() => [document.querySelectorAll('#char-species .model').length > 100,
                {state('booblord')}]""") == [True, f"Update to v{newer}"], bad   # the page works on
        _page.click(page, "char-source-reset")
        assert _page.until(page, f"() => {state('booblord')} === 'installed v{newer - 1}' && ({read})()", 120) == [
            sdk.SOURCE, ""]
        assert _page.answer(page, "() => localStorage.getItem('azurkit.content_source')") is None
        _page.answer(page, _perf.model("booblord"))
        _page.until(page, _perf.chosen("booblord", pictures=False), 600)
        _page.click(page, "build")
        assert _page.built(page)["result"] == changed
        _page.check_csp(page)
        assert served.stray() == []
        assert asks == {("GET", None)}   # the sources' requests too: GETs, no body
    finally:
        served.close()
        files.close()


def test_an_install_lists_its_variants_while_the_images_check_runs(browser, site, usa_iso, tmp_path):
    """An Install while the image picked is still being checked (the worker's own wait on the kept stamp held here, so
    the check can't end) lists its variant at once, from the engine's answer that needs no image: the Weapon box lists
    its weapons (D1061), no line asks for an image and a build still waits for the image's answer, which then comes
    (Step 4.3r4m)."""
    from azurkit.tools.characters import _player_variants, content

    repo, path = tmp_path / "repo", "variants/beamlord/variant.json"
    (repo / path).parent.mkdir(parents=True)
    (repo / path).write_text(json.dumps({"beamlord": json.loads(
        _player_variants.BUILTIN.read_text(encoding="utf-8"))["beamlord"]}), encoding="utf-8")
    (repo / "manifest.json").write_text(json.dumps(content.filled({
        "format": content.FORMAT, "schema_version": 1, "entries": [
            {"author": "Azurik-Modding-Hub", "licence": "MIT", "version": 1, "requires": [], "id": "beamlord",
             "kind": "variant", "title": "Beamlord", "files": [{"path": path}]}]},
        lambda p: (repo / p).read_bytes())), encoding="utf-8")
    served = Site(browser, site)
    served.context.route(f"{served.origin}/content-test/**", lambda route, request: route.fulfill(
        path=str(repo / urllib.parse.urlsplit(request.url).path.removeprefix("/content-test/"))))
    entry = "document.querySelector('#char-community .entry[data-entry=\"beamlord\"]"
    try:
        page = served.open()
        page.evaluate("() => localStorage.setItem('azurkit.content_source', './content-test/')")
        page = served.open()
        _page.click(page, "tab-characters")
        _page.until(page, f"() => {entry} button')", 300)
        page.evaluate("""() => new Promise((held) => {   // a transaction kept alive: prime's read of the stamp waits on it
            const open = indexedDB.open("azurkit-stamp", 1);
            open.onupgradeneeded = () => open.result.createObjectStore("stamp");
            open.onsuccess = () => {
                const store = open.result.transaction("stamp", "readwrite").objectStore("stamp");
                const spin = () => { if (!window.released) store.get("last").onsuccess = spin; };
                spin();
                held();
            };
        })""")
        _page.pick(page, "#iso", usa_iso)
        page.evaluate(f"() => {entry} button').click()")
        _page.until(page, f"() => {entry} .model')", 120)
        assert page.evaluate("""() => [azurkit.characters.state.view.from, azurkit.characters.waiting(),
            document.getElementById("char-weapon").selectedOptions[0].textContent,
            document.getElementById("char-count").textContent.includes("Choose your image")]""") == [
            None, True, "Default (Axion staff)", False]
        page.evaluate("() => { window.released = true; }")
        _page.until(page, """() => Boolean(azurkit.characters.state.view?.from)
            && document.querySelectorAll('#char-weapon option').length > 1""", 300)
        assert page.evaluate(f"() => {entry} .model').dataset.model") == "beamlord"
    finally:
        served.close()


CHARS_SHOWN = """() => [document.querySelectorAll("#char-species .model").length,
    document.getElementById("char-count").textContent, ["char-front", "char-back"].map((id) => document.getElementById(id)
    .getContext("2d").getImageData(0, 0, 160, 160).data.some((v, i) => i % 4 === 3 && v > 0)),
    [...document.querySelectorAll("#char-numbers .g4")].map((b) => b.disabled), document.getElementById("char-g4-note")
    .textContent, document.getElementById("char-weapon").disabled, document.getElementById("char-weapon").options.length,
    asked.filter((t) => ["preview", "match"].includes(t))]"""


def test_chain_on_any_press_is_off_by_default_for_any_model_and_a_new_model_unticks_it(browser, site):
    """D1045: the Characters tab's Chain on any press starts off; ticked,
    the tab's character (which a build, a link and the remembered setup
    take) says so through the engine's answer, on Garret as on any model;
    unticked it says nothing; picking another model unticks it at once and
    the new model holds no chain."""
    tick = "() => document.getElementById('char-chain').click()"
    answered = "() => azurkit.characters.state.view?.asked === JSON.stringify(azurkit.characters.state.character)"
    state = "() => [document.getElementById('char-chain').checked, azurkit.characters.character()]"
    served = Site(browser, site)
    try:
        page = served.open()
        _page.click(page, "tab-characters")
        _page.until(page, answered, 120)
        assert page.evaluate(state) == [False, None]
        page.evaluate(tick)
        _page.until(page, answered, 60)
        assert page.evaluate(state) == [True, {"species": "garret4", "chain": "any"}]
        got = page.evaluate("""() => { document.querySelector('#char-species .model[data-model="keylord"]').click();
            return document.getElementById('char-chain').checked; }""")
        assert got is False
        _page.until(page, answered, 60)
        assert page.evaluate(state) == [False, {"species": "keylord"}]
        page.evaluate(tick)
        _page.until(page, answered, 60)
        assert page.evaluate(state) == [True, {"species": "keylord", "chain": "any"}]
        page.evaluate(tick)
        _page.until(page, answered, 60)
        assert page.evaluate(state) == [False, {"species": "keylord"}]
    finally:
        served.close()


def test_the_characters_tab_shows_every_species_and_its_pictures_before_an_image(browser, site, tmp_path, usa_iso):
    """Step 4.3f (D961, D979): before an image is picked the Characters tab
    lists the 178 species the player can wear but the 76 objects (D1034),
    with Garret's two pictures, and a click on another shows its own at
    once: the site's shipped answer and pictures (``tests/test_characters.py``
    holds them to the images and to the app's draw), no engine call drawing
    them. G4 stays greyed, saying the image is needed, and says so again once
    the engine refuses a file that is no image; the image picked after it, it
    says it is being read until its answer (Step 4.3m: never "Choose your image"
    meanwhile). The Weapon box lists every weapon all the while (D1061). No CSP
    violation, no request but GETs of the site's files."""
    served = Site(browser, site)
    served.context.add_init_script(script=ASKED)
    try:
        page = served.open()
        _page.click(page, "tab-characters")
        _page.until(page, "() => document.getElementById('char-preview-note').textContent.startsWith('From the')", 60)
        assert page.evaluate(CHARS_SHOWN) == [
            102, "102 species, 76 objects hidden · Choose your image to build, and to see how each weapon fits.",
            [True, True], [True] * 4, "Choose your image to match garret4 (G4).", False, 5, []]
        page.evaluate("() => document.querySelector('#char-species .model[data-model=\"keylord\"]').click()")
        _page.until(page, "() => azurkit.characters.state.view?.chosen.name === 'keylord'", 120)
        assert page.evaluate(CHARS_SHOWN)[2:] == [[True, True], [True] * 4, "Choose your image to match garret4 (G4).",
                                                  False, 6, []]
        (tmp_path / "not-an-image.iso").write_bytes(bytes(64 * 1024))
        _page.pick(page, "#iso", tmp_path / "not-an-image.iso")
        _page.until(page, "() => !document.getElementById('char-refused').hidden", 180)
        assert page.evaluate(CHARS_SHOWN)[3:7] == [[True] * 4, "Choose your image to match garret4 (G4).", False, 6]
        _page.pick(page, "#iso", usa_iso)
        assert page.evaluate(CHARS_SHOWN)[3:7] == [[True] * 4, "Reading your image…", False, 6]
        _page.until(page, "() => Boolean(azurkit.characters.state.view?.from)", 300)
        assert page.evaluate(CHARS_SHOWN)[4] == "G4 sets a number so the body matches garret4."
        index = json.loads((site / "characters" / "index.json").read_text(encoding="utf-8"))
        assert {f"characters/{index['species'][s]}.{v}.png" for s in ("garret4", "keylord") for v in ("front", "back")} <= {
            url.removeprefix(f"{served.origin}/") for _, url, _ in served.requests}
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


def weapon_previews(page) -> None:
    """Preview by the Weapon box, on either host, before an image: a small popup (no ``showModal``: the box stays live)
    follows the box through each weapon's shipped pictures and line, the model's own weapon for Default, and Close and
    Escape shut it; no engine call draws them."""
    shown = """() => { const [a, b] = ["front", "back"].map((v) => document.getElementById(`char-weapon-${v}`));
        return document.getElementById("char-weapon-popup").open && !a.hidden && a.complete && b.complete
            && a.naturalWidth === 160 && b.naturalWidth === 160 ? [a, b].map((i) => i.src.split("/").pop()) : null; }"""
    _page.click(page, "char-weapon-preview")
    index = json.loads((_page.WEB / "characters" / "index.json").read_text(encoding="utf-8"))
    pick = """(name) => { const box = document.getElementById("char-weapon"); box.value = name;
        box.dispatchEvent(new Event("change")); }"""
    assert page.evaluate("() => document.getElementById('char-weapon-popup').matches(':modal')") is False
    assert _page.until(page, shown, 60) == [f"{index['weapons']['axion_staff']['file']}.{v}.png" for v in ("front", "back")]
    for name, said in index["weapons"].items():
        if name != "axion_staff":
            page.evaluate(pick, name)
        assert _page.until(page, f"""() => {{ const got = ({shown})();
            return got?.[0] === "{said['file']}.front.png" ? got : null; }}""", 60)[1] == f"{said['file']}.back.png"
        assert page.evaluate("() => document.getElementById('char-weapon-line').textContent") == said["line"]
        assert said["title"] in page.evaluate("() => document.getElementById('char-weapon-title').textContent")
    page.evaluate(pick, "")
    _page.click(page, "char-weapon-close")
    assert page.evaluate("() => document.getElementById('char-weapon-popup').open") is False
    _page.click(page, "char-weapon-preview")
    page.keyboard.press("Escape")
    assert page.evaluate("() => document.getElementById('char-weapon-popup').open") is False


def test_the_weapon_preview_shows_each_weapons_shipped_pictures_in_a_popup_before_an_image(browser, site):
    """The owner's review (D1061) on the site: :func:`weapon_previews`, no engine call, no CSP violation, no request
    but GETs of the site's files."""
    served = Site(browser, site)
    served.context.add_init_script(script=ASKED)
    try:
        page = served.open()
        _page.click(page, "tab-characters")
        _page.until(page, "() => document.getElementById('char-preview-note').textContent.startsWith('From the')", 60)
        weapon_previews(page)
        assert page.evaluate("() => asked.filter((t) => ['preview', 'match'].includes(t))") == []
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


def test_reset_stays_on_the_chosen_model_and_picking_garret_clears_everything(browser, site):
    """D1062: Reset takes the sliders, options and weapon back to the chosen model's defaults and stays on it (plain
    Garret on Garret); another model keeps the size and the numbers, and picking Garret clears everything."""
    settled = """() => azurkit.characters.state.view?.asked === JSON.stringify(azurkit.characters.state.character)
        && azurkit.characters.state.view.chosen.name === azurkit.characters.state.character.species"""
    shown = """() => [azurkit.characters.character(), document.getElementById("char-scale").value,
        document.getElementById("char-weapon").value, document.getElementById("char-height").checked,
        document.querySelector("#char-species .model[aria-selected=true]")?.dataset.model]"""
    dressed = """() => { for (const [id, value] of [["char-scale", "2"], ["char-weapon", "farmers_hoe"]]) {
            const box = document.getElementById(id);
            box.value = value;
            box.dispatchEvent(new Event("change"));
        }
        document.getElementById("char-height").click(); }"""
    wear = """(name) => document.querySelector(`#char-species .model[data-model="${name}"]`).click()"""
    worn = {"scale": 2, "size": "garret4", "weapon": "farmers_hoe"}
    served = Site(browser, site)
    try:
        page = served.open()
        _page.click(page, "tab-characters")
        _page.until(page, settled, 60)
        page.evaluate(wear, "keylord")
        _page.until(page, settled, 300)
        page.evaluate(dressed)
        assert _page.until(page, f"() => ({settled})() && azurkit.characters.character()", 120) == {"species": "keylord", **worn}
        _page.click(page, "char-reset")
        _page.until(page, settled, 120)
        assert page.evaluate(shown) == [{"species": "keylord"}, "1", "", False, "keylord"]

        page.evaluate(dressed)
        _page.until(page, settled, 120)
        page.evaluate(wear, "garret4")
        _page.until(page, settled, 120)
        assert page.evaluate(shown) == [None, "1", "", False, "garret4"]

        page.evaluate(dressed)
        assert _page.until(page, f"() => ({settled})() && azurkit.characters.character()", 120) == {"species": "garret4", **worn}
        _page.click(page, "char-reset")
        _page.until(page, settled, 120)
        assert page.evaluate(shown) == [None, "1", "", False, "garret4"]

        page.evaluate(dressed)
        _page.until(page, settled, 120)
        page.evaluate(wear, "keylord")   # another model: the size and numbers come along, the weapon doesn't
        assert _page.until(page, f"() => ({settled})() && azurkit.characters.character()", 120) == {
            "species": "keylord", "scale": 2, "size": "garret4"}
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


# A pick of keylord made while F works: [F's job as it is made, B's job just after it]
PICKED_BUSY = """() => {
    const pool = azurkit.pool, busy = pool.state().f.job;
    document.querySelector('#char-species .model[data-model="keylord"]').click();
    return [busy, pool.state().b.job];
}"""
KEYLORD_AHEAD = "() => [azurkit.pool.state().b.job, ...azurkit.pool.state().kept].some((k) => k?.includes('keylord'))"


def test_a_pick_while_the_tab_reads_the_image_is_answered_by_the_free_worker_before_its_build_ahead(
        browser, site, usa_iso):
    """A model picked while F still works out the Characters tab's first answer on the picked image is answered at once
    without the image by B, the free worker, and its build ahead starts once B has answered: the build ahead took B
    first, and the pick's answer waited behind F's earlier asks (S12 in WebKit, 1.0-1.3 s with no change of its bar;
    Step 4.4ci21)."""
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.until(page, "() => { const s = azurkit.pool.state(); return s.b?.loaded && !s.b.job && s.kept.length; }",
                    600)   # the image's setup built ahead: B is free
        _page.click(page, "tab-characters")
        _page.until(page, "() => document.querySelector('#char-species .model[data-model=\"keylord\"]')", 300)
        # the shipped answer lists the models about 5 ms before the tab's own ask reaches F: picked once F has it
        _page.until(page, "() => azurkit.pool.state().f?.job === 'pickers'", 300)
        assert page.evaluate(PICKED_BUSY) == ["pickers", "pickers"]
        _page.until(page, "() => azurkit.characters.state.view?.chosen.name === 'keylord'", 300)
        _page.until(page, KEYLORD_AHEAD, 300)
        assert served.stray() == []
    finally:
        served.close()


SPECIES_SHOWN = """() => [document.getElementById("char-objects").checked, document.getElementById("char-count").textContent
    .split(" · ")[0], [...document.querySelectorAll("#char-species .model")].map((m) => m.dataset.model),
    document.querySelector("#char-species .model[aria-selected=true]")?.dataset.model ?? null]"""


def test_the_characters_tab_hides_the_objects_until_show_objects_and_keeps_a_worn_one_listed(browser, site):
    """D1034 on the site, before an image: the species list leaves out the 76 objects (the engine's: one or two rigid
    bones and no clip but an idle or a sit; the 73 pickups and keys, gargoylestone and the tesla trees, never the
    boulder), its count line saying how many; Show objects lists all 178 and this browser remembers it for the next
    page, and Clear on the Tools tab names it; a model worn when the objects are hidden (diamond, and a page opened
    again on the setup that remembered it) stays listed, chosen and worn, its count one more. No CSP violation."""
    from azurkit.tools.characters import picker

    objects = {name for name, _, thing in picker.species_list() if thing}
    untested = {s["name"] for s in sdk.pickers({"iso": None})["species"] if s["untested"]}
    assert len(objects) == 76 and untested < objects and objects - untested == {"gargoylestone", "tesla_tree",
                                                                                 "tesla_tree_x"}
    every = [name for name, _, _ in picker.species_list()]
    creatures = [name for name in every if name not in objects]
    assert "boulder" in creatures and len(creatures) == 102
    served = Site(browser, site)
    try:
        page = served.open()
        _page.click(page, "remember")   # the setup wearing a body is kept for the next visit (D1156)
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view", 60)
        assert page.evaluate(SPECIES_SHOWN) == [False, "102 species, 76 objects hidden", creatures, "garret4"]
        _page.click(page, "char-objects")
        assert page.evaluate(SPECIES_SHOWN) == [True, "178 species, 73 not yet tested", every, "garret4"]
        assert page.evaluate("() => localStorage.getItem('azurkit.show_objects')") == "1"
        page.evaluate("() => document.querySelector('#char-species .model[data-model=\"diamond\"]').click()")
        _page.until(page, "() => azurkit.characters.state.view?.chosen.name === 'diamond'", 120)
        _page.until(page, "() => JSON.parse(localStorage.getItem('azurkit.setup'))?.character?.species === 'diamond'")
        page = served.open()   # Show objects remembered
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view?.chosen.name === 'diamond'", 120)
        assert page.evaluate(SPECIES_SHOWN) == [True, "178 species, 73 not yet tested", every, "diamond"]
        _page.click(page, "char-objects")   # hidden again: the worn one stays, and stays worn
        shown = [name for name in every if name not in objects or name == "diamond"]
        assert page.evaluate(SPECIES_SHOWN) == [False, "103 species, 1 not yet tested, 75 objects hidden", shown,
                                                "diamond"]
        assert page.evaluate("() => [localStorage.getItem('azurkit.show_objects'), azurkit.characters.character()]") == [
            None, {"species": "diamond"}]
        page = served.open()   # the setup remembered wearing it, the objects hidden
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view?.chosen.name === 'diamond'", 120)
        assert page.evaluate(SPECIES_SHOWN) == [False, "103 species, 1 not yet tested, 75 objects hidden", shown,
                                                "diamond"]
        _page.click(page, "char-objects")
        _page.click(page, "tab-tools")
        assert _page.until(page, """() => [...document.querySelectorAll("#tools li, #tools tr")].map((e) =>
            e.textContent).find((t) => t.includes("Whether the Characters tab lists objects"))""")
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


def test_kept_content_reaches_the_engine_only_at_a_content_path_holding_its_installed_sha256(browser, site):
    """What this browser keeps installed (IndexedDB, which any script of the site's origin can write) is written into
    the engine's content folder file by file only where its path is one a manifest may list and installed.json holds
    its sha256: a planted ``../`` key never reaches Pyodide's file system (one once wrote over the engine's own
    packages), nor does a file whose bytes aren't the record's; each is left out with a line naming it, once in each
    of the site's two workers."""
    recipe = json.dumps({"beamlord": {}}).encode()   # lists beamlord under its entry wherever it is read
    planted = "../content/variants/planted/variant.json"   # variants/planted/variant.json, were it written
    escaped = "../../../lib/python3.14/site-packages/azurkit_planted/__init__.py"
    installed = {name: {"version": 1, "source": "", "files": {f"variants/{name}/variant.json": hashlib.sha256(recipe).hexdigest()}}
                 for name in ("kept", "planted", "swapped")}
    files = {"variants/kept/variant.json": recipe, planted: recipe, escaped: b"raise SystemExit",
             "variants/swapped/variant.json": b'{"beamlord": 1}'}
    served, lines = Site(browser, site), {}
    served.context.on("console", lambda m: lines.setdefault(m.worker and m.worker.url, []).append(m.text)
                      if m.text.startswith("AzurKit left out") else None)
    try:
        page = served.open()
        listed = page.evaluate("""async ([files, installed]) => {
            azurkit.engine.content(Object.fromEntries(Object.entries(files).map(([k, v]) => [k, new Uint8Array(v)])),
                                   installed);
            const reply = await azurkit.engine.call("pickers", {given: {iso: null}});
            return Object.fromEntries(reply.community.map((e) => [e.id, e.variants.map((v) => v.name)]));
        }""", [{k: list(v) for k, v in files.items()}, installed])
        assert listed == {"kept": ["beamlord"], "planted": [], "swapped": []}
        want = sorted([f"AzurKit left out kept content: path {path!r} isn't a file under variants/, clips/, sounds/, "
                       f"fx/, packs/" for path in (planted, escaped)]
                      + ["AzurKit left out kept content: variants/swapped/variant.json's sha256 # isn't installed.json's"])
        # each worker's lines, by the worker Playwright names: share() sends the content to F, and to B once it loads
        # (the 4 cores the page says start it), whose lines came beside F's before the check on Linux's WebKit (run
        # 41521288667)
        end = time.monotonic() + 120
        while (len(lines) < 2 or any(len(got) < len(want) for got in lines.values())) and time.monotonic() < end:
            page.wait_for_timeout(200)
        assert {worker: sorted(re.sub(r"[0-9a-f]{12}", "#", line) for line in got) for worker, got in lines.items()} \
            == dict.fromkeys(lines, want) and len(lines) == 2 and None not in lines, lines
    finally:
        served.close()


def test_the_site_serves_the_favicon_the_page_links(browser, site):
    """The page links the favicon (the mark, D892), and the site's folder,
    served as a static host serves it, gives each file the page asks for,
    byte for byte ``web/``'s. (A context with no route: Playwright aborts a
    request whose address ends in ``/favicon.ico`` once a context routes.)"""
    files = _page.Served(site)
    context = browser.new_context(service_workers="block")   # its icons, not sw.js's first visit (its own file's)
    try:
        page = context.new_page()
        _page.load(page, f"{files.url}/")
        _page.check_icons(page)
    finally:
        context.close()
        files.close()


def test_the_pick_and_the_characters_tab_check_the_image_once_and_a_page_opened_again_keeps_its_stamp(
        browser, site, usa_iso):
    """The site's worker checks the image's build files once a File (hashed in WebCrypto, ``sdk.prime``): picking it
    and then opening the Characters tab hash them once, and a page opened again, the same File picked, hashes them no
    more (the browser keeps the last image's stamp by its name, size, lastModified and a sample of its bytes)."""
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view?.species.length === 178", 300)
        assert _page.checks(page) == 1
        page.close()
        again = served.open()
        _page.pick(again, "#iso", usa_iso)
        _page.until(again, "() => azurkit.vanilla?.release === 'usa'", 300)
        assert _page.checks(again) == 0 and again.evaluate("() => azurkit.violations") == []
        assert served.stray() == []
    finally:
        served.close()


def test_two_files_with_the_same_name_size_and_time_but_other_bytes_get_other_stamps(browser, site, usa_iso):
    """The site keys an image by its name, size, lastModified and a sample of its bytes (its first and last MiB, the
    XBE's header among them): a look-alike File with the picked image's name, size and time and one byte of its XBE
    other is checked as itself and refused by that file's name, never vouched for by the image's stamp nor read from
    its blocks; the image asked for again is vouched for by the stamp it kept, hashed no more."""
    (at,) = [offset for path, offset, _ in gate.layout(usa_iso) if path == "default.xbe"]
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        answers = page.evaluate("""async (at) => {
            const real = azurkit.file, [byte] = new Uint8Array(await real.slice(at, at + 1).arrayBuffer());
            const like = new File([real.slice(0, at), new Uint8Array([byte ^ 0xff]), real.slice(at + 1)], real.name,
                                  { lastModified: real.lastModified });
            const ask = async (file) => {
                const reply = await azurkit.engine.call("pickers", { file, given: {} });
                return reply.refused ?? reply.species.length;
            };
            return [[like.name, like.size, like.lastModified].join() === [real.name, real.size, real.lastModified].join(),
                    await ask(like), await ask(real)];
        }""", at)
        assert answers[0] and answers[2] == 178, answers
        assert re.search(r"is not the vanilla .*: default\.xbe: its contents differ$", str(answers[1])), answers
        assert _page.checks(page) == 2   # the pick's, the look-alike's
    finally:
        served.close()


def test_the_image_checks_count_a_worker_that_ends_while_asked_as_none_and_fail_on_a_running_workers_error(
        browser, tmp_path, monkeypatch):
    """``_page.checks`` (the stamp tests' count) sums the image checks of the page's workers still running: a worker
    the page ends while its count is asked counts none in every engine (Chromium and WebKit fail that ask with
    TargetClosedError, Firefox with a plain Error: the race of run 41981438506's Linux tier), whether Playwright hears
    its close before that error or after it (Firefox's order on run 42156372553's Linux tier, 15 runs of 400 here:
    "Execution context was destroyed", the worker still listed; held here, its close heard 0.1 s late), and a
    running worker whose count fails fails it, by its error."""
    from playwright._impl._page import Worker
    from playwright.sync_api import Error
    for name, source in (("ends.js", "Object.defineProperty(self, 'azurkitChecks', { get() { postMessage('asked');"
                                     " return new Promise(() => {}); } });"),   # its count asked, the page ends it
                         ("counts.js", "self.azurkitChecks = 2;"),
                         ("fails.js", "Object.defineProperty(self, 'azurkitChecks', { get() { throw new Error("
                                      "'no count here'); } });"),
                         ("index.html", "<!doctype html><title>checks</title>")):
        (tmp_path / name).write_text(source)
    served = Site(browser, tmp_path)
    try:
        page = _page.within(served.context, served.context._impl_obj.new_page(), _page.STALL, "a new page")
        _page.load(page, f"{served.origin}/")

        def start(*names: str) -> None:
            listed = len(page.workers) + len(names)
            _page.answer(page, """(names) => { for (const name of names) {
                const worker = new Worker(`/${name}`);
                worker.onmessage = () => worker.terminate();
                (globalThis.started ??= []).push(worker);
            } }""", list(names))
            end = time.monotonic() + 30
            while len(page.workers) < listed:   # Playwright lists a worker once it hears it start
                assert time.monotonic() < end, (names, page.workers)
                page.wait_for_timeout(50)

        start("ends.js", "counts.js")
        assert _page.checks(page) == 2 and [w.url.rpartition("/")[2] for w in page.workers] == ["counts.js"]
        heard, late = Worker._on_close, 0.1   # s: past the ask's error, within ms of the close's message either side
        with monkeypatch.context() as held:
            held.setattr(Worker, "_on_close", lambda worker: asyncio.get_running_loop().call_later(late, heard, worker))
            start("ends.js")
            assert _page.checks(page) == 2 and [w.url.rpartition("/")[2] for w in page.workers] == ["counts.js"]
        start("fails.js")
        with pytest.raises(Error, match="no count here"):
            _page.checks(page)
    finally:
        served.close()


STALLED ="Blob.prototype.arrayBuffer = () => new Promise(() => {});   // this hash worker's reads never settle\n"
"""hashworker.mjs's first line in the next test: none of the hash worker's reads of the image settles."""
WAITS_ON = r"""() => azurkit.pool.state().f.at?.match(
    /^check: hash worker: run 1\/(\d+) read at \d+ MiB, run 2\/\1 read at \d+ MiB, run 3\/\1 read at \d+ MiB$/)?.[0]"""


def test_an_images_check_that_never_ends_names_the_reads_it_waits_on(browser, site, usa_iso):
    """Step 4.3r4t: the image's check says where it waits (worker.mjs's awaiting(), hasher.mjs's at()), and the pool
    keeps it for its state, which a page wait that times out prints (``_page.hang``): here its hash worker's three reads,
    each run's number of the runs and offset, none of which settles."""
    served = Site(browser, site)
    try:
        hasher = (site / "hashworker.mjs").read_text(encoding="utf-8")
        served.context.route("**/hashworker.mjs", lambda route: route.fulfill(body=STALLED + hasher,
                                                                          content_type="text/javascript"))
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        waits = _page.until(page, WAITS_ON, 120)
        time.sleep(2)
        assert page.evaluate("() => [azurkit.pool.state().f.at, azurkit.pool.state().f.last[0], azurkit.vanilla]") == [
            waits, "at", None]
        assert waits in _page.hang(page)
    finally:
        served.close()


BUSY = "() => { setTimeout(() => { const end = Date.now() + 8000; while (Date.now() < end); }); }"
"""The page's thread busy 8 s from its next task: it answers no call meanwhile, as a browser that stopped wouldn't."""


def test_a_call_a_page_leaves_unanswered_fails_by_name_with_its_state_within_its_bound(browser, site, monkeypatch,
                                                                                        tmp_path):
    """D1072: a page promise that never settles fails its call by name past its bound, with the page's state (its
    refusals of its security policy among it, ``azurkit.violations``, Step 4.5f), and a
    page that answers nothing fails a wait by name past the wait's timeout and ``_page.STALL``, saying its state went
    unread and that its browser still answers, each within that bound and its reads (``_page.HEAR`` each, the
    browser's probe ``_page.PROBE``) and the listing of its driver's processes: never a silent wait (Windows' Firefox once left an evaluate unanswered 2 h
    10 min, run 41610020282). The state's status line comes on lines of its own, its `` · `` parts whole up to
    ``_page.STATUS`` and the rest counted, no line past ``_page.WIDTH``, which CI's log cuts no more (run 42168608453
    cut a load failure's at "ValueError: can").
    A pick whose input never comes (``_page.pick``, every set_input_files of the site's tests)
    and a navigation whose document never comes (``_page.load``, every goto and reload of the site's tests, and the
    frozen app page's first load) fail so past ``_page.ACT``, Playwright's own bound for them, naming the file or the
    address, the load also the requests it waits on (Step 4.4ci30), and a browser's close its
    driver never answers (the ``browser`` fixture's, ``conftest.close_browser``) fails past its bound naming its
    browser and driver."""
    from playwright._impl._helper import DEFAULT_PLAYWRIGHT_TIMEOUT_IN_MILLISECONDS

    from scripts import ci_resources
    assert _page.ACT * 1000 == DEFAULT_PLAYWRIGHT_TIMEOUT_IN_MILLISECONDS   # no wider than the bound the calls had
    served = Site(browser, site)
    try:
        page = served.open()   # in the bound a page's opening has, not the test's
        status = " · ".join(["AzurKit didn't load: ValueError: " + " ".join(["can't read it"] * 30),
                             *(f"file{i:03}.xbr" for i in range(200))])   # one long part, then more than STATUS holds
        _page.answer(page, "(text) => { document.getElementById('status').textContent = text; }", status)
        _page.answer(page, "() => { azurkit.violations.push('page: style-src-elem inline, a stand-in refusal'); }")
        # each listing a failure below prints reads the processes' names, never their command lines: macOS's ps reads
        # those apart, 3-25 s under taskpolicy -b on a busy Mac, which took the close's failure past its 10 s (4.4ci36)
        read = []
        monkeypatch.setattr(ci_resources, "commands", lambda pids, timeout=0: read.append(len(pids)) or {})
        monkeypatch.setattr(_page, "STALL", 2)
        monkeypatch.setattr(_page, "ACT", 2)
        t0 = time.monotonic()   # its reads in the HEAR they have outside the test: in 1 s GitHub's Intel Mac runner
        with pytest.raises(AssertionError) as never:   # left the open WebKit page's state unread (run 41666183947)
            _page.answer(page, "() => new Promise(() => {})", seconds=1)
        settled = time.monotonic() - t0
        lines = str(never.value).splitlines()
        assert lines[0] == "no answer in 1 s: () => new Promise(() => {})" and lines[1].startswith("state: {'asks': [")
        assert "'violations': ['page: style-src-elem inline, a stand-in refusal']" in lines[1]   # the page's refusals
        assert lines[-2:-1] == ["its browser still answers"] and lines[-1].startswith("under its driver: ")
        said = [line for line in lines[2:] if line.startswith(("status: ", "  "))]   # whole, on lines CI doesn't cut
        shown, _, rest = " ".join(line.removeprefix("status: ").strip() for line in said).partition(" · …and ")
        assert said[0].startswith("status: AzurKit didn't load: ValueError: can't read it can't") and max(
            map(len, said)) <= _page.WIDTH and status.startswith(f"{shown} · ") and len(shown) <= _page.STATUS
        left = status.count(" · ") - shown.count(" · ")
        assert rest == f"{left} more of its parts ({len(status) - len(shown)} characters)"
        with monkeypatch.context() as cut:   # the busy page's state read ends unread inside its 8 s (PROBE whole)
            cut.setattr(_page, "HEAR", 1)
            page.evaluate(BUSY)
            t1 = time.monotonic()
            with pytest.raises(AssertionError) as busy:
                _page.until(page, "() => azurkit.build", 1)
            held = time.monotonic() - t1
        lines = str(busy.value).splitlines()
        assert re.fullmatch(r"no answer in [23] s: \(\) => azurkit\.build", lines[0])
        assert lines[1:2] + lines[-2:-1] == ["state: unread (no answer in 1 s)", "its browser still answers"]
        assert 1 <= settled < 20 and 3 <= held < 20, (settled, held)
        assert _page.until(page, "() => azurkit.ready", 30)   # the page answers again once its thread is free
        t3 = time.monotonic()   # a pick whose input never comes, its page's state read in its whole HEAR (Firefox's
        with pytest.raises(AssertionError) as unpicked:   # past the busy page's 1 s, slowed by taskpolicy -b: 4.4ci36)
            _page.pick(page, "#nowhere", site / "index.html")
        lines = str(unpicked.value).splitlines()
        assert lines[0] == "no answer in 2 s: the pick of index.html in #nowhere", lines
        assert lines[1].startswith("state: {'asks': [") and lines[-2:-1] == ["its browser still answers"], lines
        assert 2 <= time.monotonic() - t3 < 20
        monkeypatch.setattr(_page, "HEAR", 1)   # the held navigation's state read below may end unread in 1 s
        monkeypatch.setattr(browser._impl_obj, "close", lambda **_: asyncio.sleep(600))   # a close never answered
        # what the close may wait on, listed in 5 s (its 10 s outside the test), the close's 1 s with it inside the
        # test's 10 s; it reads the temporary folder's names last, every program's folder (29,742 names here, read in
        # up to 38 s at taskpolicy -b's background priority, 4.4ci36), so they may be what it leaves unread
        monkeypatch.setattr(ci_resources, "held", functools.partial(ci_resources.held, seconds=5))
        (downloads := tmp_path / "downloads").mkdir()
        (downloads / "a.txt").write_bytes(b"a")
        t4 = time.monotonic()
        with pytest.raises(AssertionError) as unclosed:
            conftest.close_browser(browser, 1, downloads=downloads)
        assert 1 <= (closed := time.monotonic() - t4) < 10 and not read, (closed, read)
        name, lines = browser.browser_type.name, str(unclosed.value).splitlines()
        driver = re.fullmatch(rf"no answer in 1 s: the {name} browser's close, its driver (\d+)", lines[0])[1]
        assert lines[1] == "its driver heard its browser's pipe close: no", lines
        assert re.match(rf"under its driver: \S+ \(id {driver}, parent \d+\): \d+ min, \d+ MiB; .+ \(id \d+, "
                        rf"parent \d+\): \d+ min, \d+ MiB", lines[2]), lines   # its browser under it
        assert [line.partition(": ")[0] for line in lines[3:7]] == [
            "left running since it began by a parent that ended", "crash handlers",
            "Playwright's temporary folders since it began", "its downloads"], lines
        assert re.fullmatch(rf"[^:]+: (.*\b{name}'s profile \(\d+ min\): (at least )?[\d.]+ MiB in \d+ files\b.*|"
                            r"(.+; )?the rest of the temporary folder unread)", lines[5]), lines
        assert lines[6] == "its downloads: 0.0 MiB in 1 files", lines
        routes = []   # a navigation whose document never comes
        page.route("**/held.html", lambda route: routes.append(route))
        t2 = time.monotonic()
        with pytest.raises(AssertionError) as unloaded:
            _page.load(page, f"{served.origin}/held.html")
        lines = str(unloaded.value).splitlines()
        assert lines[0] == f"no answer in 2 s: the page's load of {served.origin}/held.html" and len(routes) == 1, lines
        # its state read or not: Chromium's page left it unread in 1 s while its navigation was held
        assert lines[1].startswith("state: ") and lines[-3:-2] == ["its browser still answers"], lines
        assert re.fullmatch(rf"its requests unanswered: GET {re.escape(served.origin)}/held\.html \(\d+ s\)",
                            lines[-1]), lines
        assert 2 <= time.monotonic() - t2 < 20
        routes[0].abort()
    finally:
        monkeypatch.undo()   # the close has its own bound
        served.close()


def test_a_call_whose_page_webkit_ended_fails_at_once_naming_the_ending(monkeypatch):
    """Step 4.5f: WebKit may end a live page's process and tell Playwright nothing (its network process's request,
    run 42198913490's Intel tier: the read-back's evaluate waited out its 120 s, its state unread, naming nothing). A
    WebKit page's call left ``_page.LOOK`` s unanswered reads macOS's log from a second before the call began and fails
    at once naming a page of its own browser whose process ended, not another browser's (another worker's) nor the
    network process's refusal; a call answered sooner reads no log. A stand-in page that never answers, its log a
    stand-in's."""
    from concurrent.futures import ThreadPoolExecutor

    from scripts import ci_resources
    driver, ui, theirs = os.getpid(), 4242, 4343
    rows = (("10.1", f"Playwright[{theirs}:9a1]", "Process", "[pageProxyID=3, webPageID=4, PID=950] "   # another's
             "WebPageProxy::processDidTerminate: (pid 950), reason=Crash"),
            ("11.2", "com.apple.WebKit.Networking.Development[813:9b2]", "IPC", "Received an invalid message "
             "NetworkStorageManager_SetItem from WebContent process 38790, requesting for it to be terminated."),
            ("11.3", f"Playwright[{ui}:9a1]", "Process", "[pageProxyID=1529, webPageID=1530, PID=38790] "   # its own
             "WebPageProxy::processDidTerminate: (pid 38790), reason=RequestedByNetworkProcess"))
    log = "".join(f"2026-11-06 10:57:{at} E  {who} [com.apple.WebKit:{kind}] 0x1 - {what}\n"
                  for at, who, kind, what in rows)
    asked = []
    monkeypatch.setattr(ci_resources.subprocess, "run", lambda argv, **_: (
        asked.append(argv[argv.index("--start") + 1]), types.SimpleNamespace(stdout=log))[1])
    monkeypatch.setattr(ci_resources, "table", lambda timeout=0: [(driver, 1, 100, "node", "", 1 << 20),
                                                                  (ui, driver, 90, "Playwright", "", 1 << 20)])
    for name, value in (("LOG", True), ("LOOK", 1), ("HEAR", 1)):
        monkeypatch.setattr(_page, name, value)

    async def given(value):
        return value

    def apart(call):   # a Playwright's loop, in a thread of its own
        with ThreadPoolExecutor(1) as pool:
            return pool.submit(asyncio.run, call).result()
    connection = types.SimpleNamespace(_transport=types.SimpleNamespace(_proc=types.SimpleNamespace(pid=driver)))
    context = types.SimpleNamespace(browser=types.SimpleNamespace(browser_type=types.SimpleNamespace(name="webkit")),
                                    _sync=apart, _impl_obj=types.SimpleNamespace(cookies=lambda: given([]),
                                                                                 _connection=connection))
    page = types.SimpleNamespace(main_frame=None, context=context, _sync=apart, _impl_obj=types.SimpleNamespace(
        evaluate=lambda *_: given(7), page_errors=lambda: given([]), console_messages=lambda: given([])))
    assert _page.answer(page, "() => 7") == 7 and asked == []
    page._impl_obj.evaluate = lambda *_: asyncio.sleep(600)   # its process ended: never answered
    began = time.time()
    with pytest.raises(AssertionError) as ended:
        _page.answer(page, "() => azurkit.build")
    took = time.time() - began
    lines = str(ended.value).splitlines()
    assert re.fullmatch(r"no answer in [12] s: \(\) => azurkit\.build", lines[0]) and lines[1:4] == [
        "WebKit ended a page's process in its browser since the call began (its log):",
        "  10:57:11 Playwright: [pageProxyID=1529, webPageID=1530, PID=38790] WebPageProxy::processDidTerminate: (pid "
        "38790), reason=RequestedByNetworkProcess", "state: unread (no answer in 1 s)"], lines
    assert lines[-2:] == ["its browser still answers",
                          f"under its driver: node {driver} (100 s), Playwright {ui} (90 s)"], lines
    start = time.mktime(time.strptime(asked[0], "%Y-%m-%d %H:%M:%S"))
    assert len(asked) == 1 and began - 2 < start < began - 0.9 and took < 10, (asked, began, took)
    assert isinstance(ended.value, _page.Ended) and ended.value.lines == (lines[2].strip(),), ended.value.lines


def test_a_test_whose_page_webkit_ended_at_its_network_process_request_runs_again_once_saying_so():
    """Step 4.5s: ``_page.past_refusal`` runs a test's run again once, saying so in a warning, when its page's call
    failed as WebKit ended the page's process at its network process's request (``_page.Ended`` naming
    ``_page.REFUSED``: WebKit's own fault, run 42461371001); any other failure, a crash's end among them, fails as it
    came, and so does a second such end."""
    refused = _page.Ended("no answer in 18 s: tick", (
        "08:48:07 Playwright: [pageProxyID=14, webPageID=15, PID=58731] WebPageProxy::processDidTerminate: (pid 58731), "
        "reason=RequestedByNetworkProcess",))
    crashed = _page.Ended("no answer in 18 s: tick", (
        "08:48:07 Playwright: [pageProxyID=14, webPageID=15, PID=58731] WebPageProxy::processDidTerminate: (pid 58731), "
        "reason=Crash",))

    def runs(*failures):
        visits = []

        def run(visit):
            visits.append(visit)
            if visit < len(failures):
                raise failures[visit]
            return "passed"
        return run, visits

    run, visits = runs(refused)
    with pytest.warns(UserWarning, match=r"network process's request, so the test ran again: .*58731"):
        assert _page.past_refusal(run) == "passed"
    assert visits == [0, 1]
    for failures in ((crashed,), (AssertionError("a build's bytes differ"),), (refused, refused)):
        run, visits = runs(*failures)
        with warnings.catch_warnings(record=True), pytest.raises(type(failures[-1])) as failed:
            _page.past_refusal(run)
        assert (failed.value, visits) == (failures[-1], list(range(len(failures)))), visits


def test_a_page_call_whose_context_went_names_whether_its_page_reloaded_and_its_state(browser):
    """A page's call that fails as Playwright's "Execution context was destroyed" (``_page.LOST``: a navigation under
    it, or an error WebKit's agent answered it with) fails naming the call and its error, how long after or before the
    call the page's document began (after it: the page reloaded; before it, by the gap: its load, or a navigation begun
    before the call), its state and its driver's processes: GitHub's Intel Mac runner failed a WebKit page's evaluate
    so with nothing more (run 42406769117). Any other error is the call's own, raised as it came."""
    from playwright._impl._errors import Error
    page = browser.new_page()

    async def gone(reload: bool):
        if reload:
            await page._impl_obj.reload()
        raise Error("Execution context was destroyed, most likely because of a navigation.")
    try:
        for reload, said in ((False, "before the call: its load, or a reload or navigation begun before the call"),
                             (True, "after the call: the page reloaded or navigated")):
            with pytest.raises(AssertionError) as failed:
                _page.within(page, gone(reload), 30, "the stand-in call")
            lines = str(failed.value).splitlines()
            assert lines[0] == ("the stand-in call: Execution context was destroyed, most likely because of a "
                                "navigation.") and re.match(rf"its document began \d+\.\d\d s {said}", lines[1]), lines
            assert any(line.startswith("state: ") for line in lines) and lines[-1].startswith("under its driver: ")
        with pytest.raises(Error, match="no such thing"):
            _page.answer(page, "() => { throw new Error('no such thing'); }")
    finally:
        page.close()


def test_a_webkit_call_answered_past_its_bound_fails_though_its_log_is_still_read(monkeypatch):
    """Step 4.5f: a WebKit call on macOS takes its answer until its bound, never after: one that comes while macOS's log
    is read at the bound, or by a read begun before it and still running, fails the call there as Playwright's own
    bound did, so ``_page.ACT`` and ``_page.STALL`` are no wider than the bounds the calls had; one that comes during a
    read before the bound is taken. A stand-in call and a stand-in read that names nothing."""
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(_page, "LOOK", 0.2)

    async def answered(at):
        await asyncio.sleep(at)
        return "answered"

    def read():   # a log read that names nothing, in 0.6 s
        time.sleep(0.6)
        return []

    def watched(bound, at):   # a Playwright's loop, in a thread of its own
        with ThreadPoolExecutor(1) as pool:
            try:
                return pool.submit(asyncio.run, _page._watched(answered(at), bound, read)).result()
            except TimeoutError as error:
                return type(error)
    # past a bound under LOOK, in the read at it; past one a read began before (at 0.2 s); before one, in a read
    assert [watched(0.1, 0.4), watched(0.5, 0.65), watched(3, 0.4)] == [TimeoutError, TimeoutError, "answered"]


def test_a_browsers_close_ends_what_its_ended_browser_left_running_and_says_so(monkeypatch):
    """Step 4.4ci18: a browser's close its driver holds until a process the browser's ended parent left running ends
    (Windows' WebKit: a WebKitWebProcess.exe left by its ended browser holds the driver's pipes, out of reach of the
    driver's ``taskkill /T``; runs 41744982709, 182336a's, 41779807138) answers once the ``browser`` fixture's close
    (``conftest.close_browser``) has waited ``conftest.LEFT_S`` and ended it, and a warning names it; a browser's
    process under the driver, one that began before the driver, one of another name and the user's own Chrome
    outside Playwright's folders, each also left by an ended parent, run on."""
    from concurrent.futures import ThreadPoolExecutor

    from scripts import ci_resources
    procs = {what: subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
             for what in ("held", "under", "older", "other", "theirs")}
    gone, driver = 999_999_999, os.getpid()   # a parent id no process has
    webkit = "D:\\a\\AzurKit\\AzurKit\\.tools\\playwright\\webkit-2370\\"   # Playwright's WebKit's folder on CI
    rows = {"held": (gone, 30, "WebKitWebProcess.exe", f'"{webkit}WebKitWebProcess.exe" 2 -clientIdentifier 1'),
            "under": (driver, 50, "Playwright.exe", f"{webkit}Playwright.exe"),
            "older": (gone, 200, "WebKitWebProcess.exe", f'"{webkit}WebKitWebProcess.exe" 2 -clientIdentifier 1'),
            "other": (gone, 30, "git.exe", "C:\\Program Files\\Git\\cmd\\git.exe"),
            "theirs": (gone, 30, "chrome.exe", '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"')}
    monkeypatch.setattr(ci_resources, "processes", lambda timeout=0: [(driver, 1, 100, "node", "", 1 << 20)] + [
        (procs[what].pid, parent, age, name, command, 1 << 20) for what, (parent, age, name, command) in rows.items()
        if procs[what].poll() is None])

    async def close():   # the driver's: it answers once the held process has ended
        while procs["held"].poll() is None:
            await asyncio.sleep(0.05)
    def apart(call):   # sync Playwright's loop, a module's browser's, may run in this thread: asyncio.run in another
        with ThreadPoolExecutor(1) as pool:
            return pool.submit(asyncio.run, call).result()
    fake = types.SimpleNamespace(browser_type=types.SimpleNamespace(name="webkit"), _sync=apart,
                                 is_connected=lambda: True, _impl_obj=types.SimpleNamespace(close=close, _connection=(
                                     types.SimpleNamespace(_transport=types.SimpleNamespace(
                                         _proc=types.SimpleNamespace(pid=driver))))))
    monkeypatch.setattr(conftest, "LEFT_S", 0.5)
    monkeypatch.setattr(conftest, "EVERY_S", 0.2)
    try:
        t0 = time.monotonic()
        with pytest.warns(UserWarning) as said:
            conftest.close_browser(fake, 30)
        assert 0.5 <= time.monotonic() - t0 < 10
        assert {what: proc.poll() is None for what, proc in procs.items()} == {
            "held": False, "under": True, "older": True, "other": True, "theirs": True}
        assert [str(w.message) for w in said] == [
            "the webkit browser's close waited on what a parent that ended left running, out of its driver's kill's "
            f"reach, ended: WebKitWebProcess.exe (id {procs['held'].pid}, parent {gone}): 0 min, 1 MiB"]
    finally:
        for proc in procs.values():
            proc.kill()
            proc.wait()


STOPPED = """import asyncio, json, sys, time
from playwright.sync_api import sync_playwright
from tests import _page
_page.HEAR = _page.PROBE = 1
with sync_playwright() as playwright:
    browser = getattr(playwright, sys.argv[1]).launch(headless=True)
    page = browser.new_page()
    page.context._impl_obj.cookies = lambda: asyncio.sleep(600)   # its browser answers nothing either
    said, at = [], [time.monotonic()]
    for call in (lambda: _page.answer(page, "() => new Promise(() => {})", seconds=1), lambda: page.evaluate("1"),
                 browser.close):
        try:
            said.append(call())
        except Exception as error:
            said.append(str(error))
        at.append(time.monotonic())
print(json.dumps({"said": said, "took": [b - a for a, b in zip(at, at[1:])]}))
"""
"""A browser whose page leaves a call unanswered and that answers nothing either (its cookies), in a Playwright of its
own: the calls after the stall, an evaluate and the browser's close, said and timed."""


def test_a_browser_that_answers_nothing_fails_its_later_calls_at_once(browser):
    """D1072: a call left unanswered whose browser answers nothing either says so and closes that browser's Playwright
    connection naming the call, so the next call fails at once by that name and the browser's close returns at once:
    a module's later tests on a browser that stopped fail fast, never a silent wait. In a Python of its own, as the
    closed connection is its Playwright's, every browser's of it."""
    done = subprocess.run([sys.executable, "-c", STOPPED, browser.browser_type.name], cwd=_page.WEB.parent,
                          capture_output=True, text=True, timeout=_page.STALL)
    assert done.returncode == 0, done.stderr[-2000:]
    (stalled, later, closed), took = json.loads(done.stdout).values()
    assert stalled.splitlines()[0] == "no answer in 1 s: () => new Promise(() => {})"
    assert "its browser answers nothing either (in 1 s): every later call to it fails at once" in stalled.splitlines()
    assert "the browser stopped answering: () => new Promise(() => {})" in later and closed is None
    assert took[1] < 1 and took[2] < 1, took


def test_each_firefox_a_test_launches_takes_no_proxy_under_its_own_prefs():
    """Each Firefox the tests launch (Playwright's ``launch`` and ``launch_persistent_context``, which its sync and async
    APIs both call) takes ``network.proxy.type`` 0 under the prefs its launch gives (:data:`conftest.DIRECT`), so a
    request to a test's host never waits on the system's proxy settings: on GitHub's Windows runner a page's load of
    its 127.0.0.1 host went unanswered 30 s in Firefox, its one request heard 1 s before the failure (run 42409729869).
    Read from the call Playwright's impl is given, a coroutine never started; another browser's launch is as given."""
    from playwright._impl._browser_type import BrowserType

    def prefs(name: str, method: str = "launch", *args, **options):
        call = getattr(BrowserType, method)(types.SimpleNamespace(name=name), *args, headless=True, **options)
        try:
            return call.cr_frame.f_locals["firefoxUserPrefs"]
        finally:
            call.close()

    own = {"browser.privatebrowsing.autostart": True}
    assert prefs("firefox") == conftest.DIRECT == {"network.proxy.type": 0}
    assert prefs("firefox", "launch_persistent_context", "profile", firefoxUserPrefs=own) == conftest.DIRECT | own
    assert [prefs("chromium"), prefs("webkit", firefoxUserPrefs=own)] == [None, own]


HELD = """const made = [];
globalThis.Worker = class {   // hashedApart's worker, a stub: each one made, weakly
    constructor() { made.push(new WeakRef(this)); }
    postMessage() {}
    terminate() {}
};
const { hashedApart } = await import(%s);
const turn = () => new Promise((done) => setTimeout(done, 0));
const alive = async () => {   // after three collections
    for (let i = 0; i < 3; i++) {
        await turn();
        gc();
    }
    return Boolean(made[0].deref());
};
let settled = null;
hashedApart(new Blob([new Uint8Array(8)]), [["file:a", 0, 8]]).then((digests) => { settled = digests; });
const running = await alive();
made[0].deref()?.onmessage({ data: { digests: { "file:a": "0" } } });
await turn();
console.log(JSON.stringify([running, settled, await alive()]));
"""


def test_a_hash_worker_is_held_until_its_check_settles_so_a_collection_never_loses_its_answer(site):
    """Step 4.3r4t: ``web/hasher.mjs`` under Node (``--expose-gc``) holds the worker hashedApart starts until its
    answer comes, and lets it go then. Firefox collects a Worker object that nothing holds (its own handlers don't) and
    the messages that worker posted last never arrive: one call in about 100 of the image's check (6 runs of 32 MiB)
    never settled in Firefox, each at its last run, none of 300 with the worker held, and two full gates' characters
    tab waited 300 s for the USA image's answer, F's last word a progress."""
    run = subprocess.run(["node", "--expose-gc", "--input-type=module", "--eval",
                          HELD % json.dumps((site / "hasher.mjs").as_uri())],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    assert json.loads(run.stdout) == [True, {"file:a": "0"}, False]


AHEAD = """import { createHash } from "node:crypto";
Object.defineProperty(globalThis, "navigator", { value: { userAgent: %s }, configurable: true });   // that browser's
let settle;
Object.defineProperty(globalThis, "self", { configurable: true, value: { postMessage: (message) => {
    if ("digests" in message || "error" in message) settle(message);
} } });
await import(%s);   // hashworker.mjs: an image's check (hashedApart's worker), as in that browser
const { hashed } = await import(%s);   // the hasher.mjs it imported
const blob = new Blob([Uint8Array.from({ length: 12 << 10 }, (_, i) => (i * 7919) %% 251)]);
const bytes = new Uint8Array(await blob.arrayBuffer());
const files = Array.from({ length: 12 }, (_, i) => [`file:${i}`, i << 10, 1 << 10]);
let flying = 0, most = 0, taken = 0;
const held = [];   // the buffers read, each held until hashed() frees it (transfer(0))
const source = { slice: (start, end) => ({ arrayBuffer: async () => {
    flying += 1;
    most = Math.max(most, flying);
    taken = Math.max(taken, flying + held.filter((b) => b.byteLength).length);
    await new Promise((late) => setTimeout(late, 20));   // a slow read
    const buffer = await blob.slice(start, end).arrayBuffer();
    flying -= 1;
    held.push(buffer);
    return buffer;
} }) };
const check = () => new Promise((answer) => {
    settle = answer;
    self.onmessage({ data: { source, rows: files, longest: 1 << 10 } });
}).then(({ digests, error }) => digests ?? Promise.reject(new Error(error)));
const seen = [];
for (const hash of [check, () => hashed(source, files, () => {}, 1 << 10)]) {   // the check; a build's (worker.mjs)
    most = taken = 0;
    const digests = await hash();
    const same = files.every(([key, at, size]) =>
        digests[key] === createHash("sha256").update(bytes.subarray(at, at + size)).digest("hex"));
    seen.push([most, taken, same]);
}
console.log(JSON.stringify(seen));
"""


def test_an_images_check_reads_each_lanes_next_run_ahead_in_safari_and_a_builds_hash_reads_one_run_a_lane(site):
    """Step 4.4bg: ``web/hashworker.mjs`` (an image's check: the pick, Verify, a Save's) and ``web/hasher.mjs``'s
    hashed() as a build calls it (``worker.mjs``: the files it changed) under Node, over a slow source, as in Safari and
    in Chromium (their user agents). In Safari each of the check's three lanes has its next run's read in flight while
    it awaits or digests one (six reads at once, so a read's wait, Safari's 200 ms whatever its size, overlaps the
    lane's other: S03/lag, S41/lag and the lag Saves wait half the rounds), never more than two runs a lane read or
    being read (a Save's check 768 MiB at most, was 384). A build's hash reads one run a lane there too: it runs in the
    engine's worker beside Pyodide's heap, where reads ahead made a seed build (S24) 0.31-0.39 GiB heavier at
    capped-site's peak for no time. In Chromium both read one run a lane: its browser process reads the File for a
    Save's download as for its check, and its Saves took 0.4-0.6 s longer with reads ahead. The digests are the same."""
    seen = []
    for agent in ("AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15",   # Safari's, WebKit's
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"):   # Chromium's
        run = subprocess.run(["node", "--input-type=module", "--eval", AHEAD % (
            json.dumps(agent), json.dumps((site / "hashworker.mjs").as_uri()), json.dumps((site / "hasher.mjs").as_uri()))],
                             capture_output=True, text=True, timeout=120)
        assert run.returncode == 0, run.stderr[-2000:]
        seen.append(json.loads(run.stdout))
    assert seen == [[[6, 6, True], [3, 3, True]], [[3, 3, True], [3, 3, True]]]


GIVES_WAY = """import { createHash } from "node:crypto";
let dress = false, waited = false;   // whether a character's ask holds hasher.mjs's DRESSING, a Save its WAITED
Object.defineProperty(globalThis, "navigator", { configurable: true, value: {
    userAgent: "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15",   // Safari's: reads ahead
    locks: { query: async () => ({ held: [...dress ? [{ name: "azurkit-dressing", mode: "shared" }] : [],
                                          ...waited ? [{ name: "azurkit-rest-waited", mode: "shared" }] : []] }) } } });
let settle;
const steps = [];
Object.defineProperty(globalThis, "self", { configurable: true, value: { postMessage: (message) => {
    if ("at" in message) steps.push(message.at);
    if ("digests" in message || "error" in message) settle(message);
} } });
await import(%s);   // hashworker.mjs, hashedApart's worker
const blob = new Blob([Uint8Array.from({ length: 24 << 10 }, (_, i) => (i * 7919) %% 251)]);
const bytes = new Uint8Array(await blob.arrayBuffer());
const files = Array.from({ length: 24 }, (_, i) => [`file:${i}`, i << 10, 1 << 10]);
const dressedFor = (ms) => {
    dress = true;
    setTimeout(() => { dress = false; }, ms);
};
let reads = 0, whileDressed = 0, flying = 0, most = 0, saving = false;
const source = { slice: (start, end) => ({ arrayBuffer: async () => {
    reads += 1;
    if (dress) whileDressed += 1;
    if (reads === 6) dressedFor(300);   // a character's build starts beside it
    if (saving && reads === 12) {   // gone on one at a time after it, a Save waits on it with a dress held again
        dress = waited = true;
        most = flying;
    }
    most = Math.max(most, ++flying);
    await new Promise((late) => setTimeout(late, 20));   // a slow read
    flying -= 1;
    return blob.slice(start, end).arrayBuffer();
} }) };
const seen = [];
for (const [yields, save] of [[true, false], [false, false], [true, true]]) {   // the rest of an image (worker.mjs's
    reads = whileDressed = most = steps.length = 0;   // vouched()); an image's check, a Save's; the rest a Save waits on
    saving = save;
    dressedFor(200);   // and one before it starts
    const { digests } = await new Promise((answer) => {
        settle = answer;
        self.onmessage({ data: { source, rows: files, longest: 1 << 10, yields } });
    });
    const same = files.every(([key, at, size]) =>
        digests?.[key] === createHash("sha256").update(bytes.subarray(at, at + size)).digest("hex"));
    seen.push([whileDressed, steps.some((step) => step.includes("giving way")), most, same]);
    dress = waited = false;
}
console.log(JSON.stringify(seen));
"""


def test_an_images_rest_hashed_in_the_background_gives_way_to_a_dress_until_a_save_waits_on_it_and_a_check_never_waits(
        site):
    """Step 4.4ci25: ``web/hashworker.mjs`` under Node, as in Safari, over a slow source. The rest of an image, hashed
    after its pick for a later Save (``worker.mjs``'s vouched()), gives way to a character's dress (an ask that carries
    one holds ``DRESSING``, which ``navigator.locks`` shows): it starts no read while one is held, before it starts or
    once it has begun, and from then on keeps one read in flight, as the page holds the dress's heap after it (wasm's
    never shrinks). Its six runs in flight on top of keylord's build took the kept-dress test's WebKit page from
    1.7-1.8 to 2.7-2.9 GiB at its peak (Chromium's 2.0-2.3 to 2.5-2.6), and given way to the build only, to 2.3-2.4
    GiB as it went on after it. An image's check (the pick, Verify, a Save's) never waits and reads six at once. Once a
    Save waits on the rest (``app.mjs`` holds ``WAITED``, Step 4.4stack2) it is that Save's hash: it reads beside a dress
    and six at once again, its lanes that ended started again. The digests are the same."""
    run = subprocess.run(["node", "--input-type=module", "--eval", GIVES_WAY % json.dumps(
        (site / "hashworker.mjs").as_uri())], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    rest, check, waited = json.loads(run.stdout)
    assert rest == [0, True, 1, True] and check[0] > 0 and check[1:] == [False, 6, True], (rest, check)
    assert waited == [12, True, 6, True], waited


# The bottom bar's progress as the page shows it, each change: [the bar's value (null: a moving stripe), its line],
# or null while it is hidden
# Each look the bottom bar takes (``bars``), and how often the page wrote the bar with the look it already had
# (``redrawn``: each write draws it again)
BARS = """() => {
    globalThis.bars = [];
    globalThis.redrawn = 0;
    const row = document.getElementById("progress-row"), shows = () => row.hidden ? null
        : [document.getElementById("progress").getAttribute("value"), document.getElementById("progress-line").textContent];
    const look = () => {
        const seen = shows();
        if (JSON.stringify(seen) !== JSON.stringify(bars.length ? bars.at(-1) : null)) bars.push(seen);
    };
    new MutationObserver(look).observe(document.querySelector("footer"), { subtree: true, childList: true,
                                                                            characterData: true, attributes: true });
    let shown = JSON.stringify(shows());
    new MutationObserver(() => { const now = JSON.stringify(shows()); redrawn += now === shown; shown = now; })
        .observe(row, { subtree: true, childList: true, characterData: true, attributes: true });
}"""
# The page's clock stopped (only the bar reads it): every answer lands inside a check's moment after it is whole
STILL = "() => { const at = performance.now(); performance.now = () => at; }"
# Build, then Cancel, the moment the check's bar first shows: ``cancelled`` is [the asks then, the bar hidden after]
CANCEL = """() => new MutationObserver((_, seen) => {
    if (!document.getElementById("progress-line").textContent.startsWith("Checking your image")) return;
    seen.disconnect();
    const asks = [...azurkit.asks.values()].map((ask) => ask.kind).join();
    document.getElementById("build").click();
    document.getElementById("cancel").click();
    globalThis.cancelled = [asks, document.getElementById("progress-row").hidden];
}).observe(document.querySelector("footer"), { subtree: true, childList: true, characterData: true })"""


def test_the_bottom_bar_walks_the_images_check_by_its_percent_then_a_builds_stages(browser, site, usa_iso):
    """Step 4.3i (D980): the site's bottom bar shows the picked image's
    check (its build files hashed, ``sdk.prime``) by its percent up to 100,
    then a build's named stages as the worker posts them (``core.progress``'s
    records: its files read, each pack applied, the image laid out), and
    hides once the build is ready, never showing the check again: the
    worker's answer ends the check before it, whatever the clock says. A Cancel
    of a Build queued behind the check leaves the check running, as the read
    behind it must end, and the bar goes with its answer. The clock is stopped
    here (:data:`STILL`), as a race made it: Chromium built two packs in
    0.1 s, inside the 250 ms the check's whole bar stayed for (Step 4.3
    train). The page writes the bar only when its look changes: each write
    draws it again, in WebKit a round trip to its GPU process, which a busy
    computer starves, and its tick and the worker's records rewrote it 23
    times a second, half of them unchanged (Step 4.4ci21)."""
    served = Site(browser, site)
    try:
        page = served.open()
        page.evaluate(BARS)
        page.evaluate(STILL)
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.build(page, ["fps_unlock", "qol_skip_logo"])
        _page.built(page)
        bars = page.evaluate("() => bars")
        checked = [int(value) for value, line in filter(None, bars) if line.startswith("Checking your image")]
        assert len(checked) >= 3 and checked == sorted(checked) and checked[-1] == 100, checked
        lines = [line for _, line in filter(None, bars)]
        assert [any(line.startswith(stage) for line in lines) for stage in (
            "Reading its files", "Applying fps_unlock", "Applying qol_skip_logo", "Laying out the image")] == [True] * 4
        assert bars[-1] is None and page.evaluate("() => redrawn") == 0 and served.stray() == []
    finally:
        served.close()
    served = Site(browser, site)   # a fresh browser checks the image again
    try:
        page = served.open()
        page.evaluate(BARS)
        page.evaluate(STILL)
        page.evaluate(CANCEL)
        _page.pick(page, "#iso", usa_iso)
        assert _page.until(page, "() => globalThis.cancelled", 120) == ["check", True]
        _page.until(page, "() => azurkit.ready && azurkit.vanilla?.release === 'usa'", 300)
        assert page.evaluate("() => bars.at(-1)") is None and served.stray() == []
    finally:
        served.close()


# The bottom bar shown with ``value`` (null: no count): [the bar's look, the stripe's display, its stripe's animation and
# how often it runs, the properties each of that animation's keyframes sets]
LOOK = """(value) => {
    document.getElementById("progress-row").hidden = false;
    const bar = document.getElementById("progress"), stripe = document.querySelector("#progress-row .stripe");
    value === null ? bar.removeAttribute("value") : bar.setAttribute("value", value);
    const moving = getComputedStyle(stripe, "::before"), rules = [...document.styleSheets].flatMap((s) => [...s.cssRules]);
    const frames = rules.find((r) => r.type === CSSRule.KEYFRAMES_RULE && r.name === moving.animationName);
    return [getComputedStyle(bar).appearance, getComputedStyle(stripe).display, moving.animationName,
            moving.animationIterationCount, frames && [...frames.cssRules].map((frame) => [...frame.style])];
}"""


def test_the_bottom_bars_stripe_with_no_count_is_a_transform_its_compositor_moves(browser, site):
    """D980's moving stripe while a call has no count is a transform the browser's compositor moves, over a plain
    track, never the bar's own look with no value, which WebKit draws again each frame (60 a second, each a round trip
    to its GPU process: 4 such pages took 9 % of a core in it, 14 % in their page processes; the stripe, none of
    either: Step 4.4ci21), as Firefox does its own; with a count the stripe goes and the bar has its own look."""
    served = Site(browser, site)
    try:
        page = _page.within(served.context, served.context._impl_obj.new_page(), _page.STALL, "a new page")
        _page.load(page, f"{served.origin}/")
        assert _page.answer(page, LOOK, None) == ["none", "block", "stripe", "infinite", [["transform"], ["transform"]]]
        assert _page.answer(page, LOOK, "50")[:2] == ["auto", "none"]
        _page.close(page)
    finally:
        served.close()


# What D979 greys and the lines that say why: [Build disabled, Save disabled, the bottom bar's line, Build's title, the
# spoiler's line, how many packs' settings say their vanilla values wait on the image]
GREYED = """() => [document.getElementById("build").disabled, document.getElementById("save").disabled,
    document.getElementById("build-line").textContent, document.getElementById("build").title,
    document.getElementById("spoiler-note").textContent,
    [...document.querySelectorAll("#packs .vanilla-note")].filter((note) => !note.hidden).length]"""


def test_build_save_and_the_vanilla_values_are_greyed_with_their_lines_until_the_image_and_a_build(
        browser, site, usa_iso):
    """D979: until an image is picked, Build is greyed with "Pick your image
    (1.) to build" (its line in the bottom bar and its title), Save with it,
    the spoiler's line names the image, and each pack whose vanilla values
    the image holds says so in its settings; once the image is read, Build
    works and Save waits on a build, and once built, nothing is greyed.
    Step 4.4u1: with Randomize ticked and Obsidians unticked, whose vanilla
    spots are most of those the disc fragments and powers may take, Build
    greys with "Tick Obsidians on the Randomizer tab to build" and the tab's
    ⚠ line says why, until Obsidians is ticked again or Randomize unticked;
    a reload that restores that setup (Remember settings ticked) greys it so
    on the Patches tab too.
    D1153: the "In game" line beside the build's result names the controls
    that build adds (its save warp), hidden before a build and once a change
    forgets it."""
    vanilla = {name for name, pack in mods.PACKS.items() if any(s.catalog()["vanilla"] is None for s in pack.sliders())}
    starved = sdk.randomizer_settings({"settings": sdk.catalog()["randomizer"]["defaults"]
                                       | {"exclude_categories": ["obsidians"]}})["preflight"]
    obsidians = "() => document.querySelector('#rando-items input[data-category=obsidians]').click()"
    served = Site(browser, site)
    try:
        page = served.open()
        assert page.evaluate(GREYED) == [True, True, "Pick your image (1.) to build", "Pick your image (1.) to build",
                                         "Pick your image (1.), then build with Randomize ticked to see its spoiler.",
                                         len(vanilla)]
        assert page.evaluate(INGAME) == [True, ""]
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        assert page.evaluate(GREYED) == [False, True, "Save follows a build", "",
                                         "Build with Randomize ticked to see its spoiler.", 0]
        _page.build(page, ["fps_unlock", "qol_save_warp"])
        _page.built(page)
        _page.until(page, "() => azurkit.ready", 120)   # a worker that replaces the build's says "Preparing the engine…"
        assert page.evaluate(GREYED)[:4] == [False, False, "", ""] and served.stray() == []
        assert page.evaluate(INGAME) == [False, "In game: LT + A, B, X, Y on a save platform: town and back"]

        _page.click(page, "tab-randomizer")
        _page.until(page, SETTLED, 120)
        _page.click(page, "rando-on")
        page.evaluate(obsidians)
        _page.until(page, f"() => ({SETTLED})()?.preflight", 120)
        tick, works = "Tick Obsidians on the Randomizer tab to build", [False, True, "Save follows a build", ""]
        assert page.evaluate(GREYED)[:4] == [True, True, tick, tick]   # a change forgets the build
        assert page.evaluate(INGAME) == [True, ""]
        assert page.evaluate(WARNED)[0] == f"⚠ Can't make a seed: {starved}."
        _page.click(page, "rando-on")
        assert page.evaluate(GREYED)[:4] == works
        _page.click(page, "rando-on")
        assert page.evaluate(GREYED)[:4] == [True, True, tick, tick]
        page.evaluate(obsidians)
        assert page.evaluate(GREYED)[:4] == works   # the answer for the items as they were is stale
        _page.until(page, f"() => ({SETTLED})() && !azurkit.rando.view.preflight", 120)
        assert page.evaluate(GREYED)[:4] == works
        assert not [line for line in page.evaluate(WARNED) if line.startswith("⚠ Can't")] and served.stray() == []

        _page.click(page, "remember")
        page.evaluate(obsidians)
        _page.until(page, f"() => ({SETTLED})()?.preflight", 120)   # remembered (D915, D1156)
        _reload(page)   # restored on the first tab, Patches: Randomize ticked asks there
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, f"() => azurkit.vanilla?.release === 'usa' && ({SETTLED})()?.preflight", 300)
        assert [page.evaluate("() => azurkit.tab"), *page.evaluate(GREYED)[:4]] == ["patches", True, True, tick, tick]
        assert served.stray() == []
    finally:
        served.close()


# The "In game" line beside a build's result (D1153): [hidden, its text]
INGAME = "() => [document.getElementById('ingame').hidden, document.getElementById('ingame').textContent]"


# What the Tools tab greys until an image (D979): [Verify, Show its files and the filter disabled, Verify's title, the
# image's line]
TOOLS_GREYED = """() => [...["tools-verify", "tools-list", "tools-filter"].map((id) => document.getElementById(id).disabled),
    document.getElementById("tools-verify").title, document.getElementById("tools-image-line").textContent]"""
TOOLS_LINE = "() => document.getElementById('tools-image-line').textContent"


def test_the_tools_tab_checks_lists_and_extracts_the_image(browser, site, usa_iso):
    """Step 4.7c (D979, D982): the Tools tab greys what waits for an image
    with "Choose your image first (1.)" until one is picked; then it says
    what the image is (USA, vanilla, its build files checked); Verify every
    file walks the bottom bar by its percent to 100 and says every file
    checked; the file list holds the manifest's files, its filter narrows
    it, and Extract downloads a file of the player's own File whose size
    and sha256 are the manifest's."""
    small = min((path for path, (size, _) in gate.USA.files.items() if size and not path.startswith(gate.BUILD_FILES)),
                key=lambda path: (gate.USA.files[path][0], path))
    count = f"{len(gate.USA.files):,}"
    served = Site(browser, site)
    try:
        page = served.open()
        _page.click(page, "tab-tools")
        assert page.evaluate(TOOLS_GREYED) == [True, True, True, "Choose your image first (1.)",
                                               "Choose your image first (1.)"]
        page.evaluate(BARS)
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.tools.state.info", 300)
        assert page.evaluate(TOOLS_GREYED)[:4] == [False, False, False, ""]
        assert page.evaluate(TOOLS_LINE) == f"USA · {gate.USA.iso_size:,} B · vanilla · its build files checked"
        _page.click(page, "tools-verify")
        _page.until(page, "() => azurkit.tools.state.info.whole", 300)
        assert page.evaluate(TOOLS_LINE).endswith(" · vanilla · every file checked")
        checked = [int(value) for value, line in filter(None, page.evaluate("() => bars"))
                   if line.startswith("Checking every file") and value is not None]
        assert len(checked) >= 3 and checked == sorted(checked) and checked[-1] == 100, checked
        _page.click(page, "tools-list")
        assert _page.until(page, "() => azurkit.tools.state.files && document.getElementById('tools-count').textContent"
                           ) == f"{count} files"
        files = "() => [document.getElementById('tools-files').hidden, document.getElementById('tools-list').textContent]"
        assert page.evaluate(files) == [False, "Hide its files"]
        _page.click(page, "tools-list")
        assert page.evaluate(files) == [True, "Show its files"]
        _page.click(page, "tools-list")
        assert page.evaluate(files) == [False, "Hide its files"]
        _page.fill(page, "tools-filter", small)
        assert page.evaluate("() => document.getElementById('tools-count').textContent") == f"1 of {count} files"
        with page.expect_download(timeout=120_000) as caught:
            page.evaluate("() => document.querySelector('#tools-rows button').click()")
        download = caught.value
        try:
            saved = Path(download.path())
            with open(saved, "rb") as f:
                got = (download.suggested_filename, saved.stat().st_size, hashlib.file_digest(f, "sha256").hexdigest())
        finally:
            download.delete()
        assert got == (small.rpartition("/")[2], *gate.USA.files[small]) and served.stray() == []
    finally:
        served.close()


def test_the_tools_tab_opened_after_the_pick_says_what_the_image_is_with_no_engine_ask(browser, site, usa_iso):
    """Step 4.4be (S40, D980, D1107): the site's pick of a vanilla image
    brings the engine's info of it with its sliders' values (worker.mjs's
    vanilla: ``sdk.image_info`` of the image the pick checked), so the Tools
    tab opened after it says what the image is at once and asks the engine
    nothing (S40 was its own worker ask: 0.5-0.9 s with no bar); an image
    picked while the tab is open is asked as before (the test above)."""
    served = Site(browser, site)
    try:
        served.context.add_init_script(ASKED)
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.click(page, "tab-tools")
        _page.until(page, "() => azurkit.tools.state.info")
        assert page.evaluate(TOOLS_LINE) == f"USA · {gate.USA.iso_size:,} B · vanilla · its build files checked"
        assert page.evaluate("() => asked.filter((t) => t === 'info')") == [] and served.stray() == []
    finally:
        served.close()


# The Data tab (Step 4.7a): a cell of the view by its table and name ([its text, its classes, its note]); an edit typed
# into it and committed with Enter; one of the tab's bar buttons by its label.
DATA_FIND = """const td = [...document.querySelectorAll("#data td.cell")].find((n) => {
    const c = JSON.parse(n.dataset.cell); return c.ref[0] === table && c.name === name; });"""
DATA_CELL = f"""([table, name]) => {{ {DATA_FIND}
    return td ? [td.textContent, [...td.classList].sort().join(" "), td.title] : null; }}"""
DATA_EDIT = f"""([table, name, text]) => {{ {DATA_FIND}
    td.click(); const box = td.querySelector("input"); box.value = text;
    box.dispatchEvent(new KeyboardEvent("keydown", {{ key: "Enter", bubbles: true }})); }}"""
DATA_PRESS = """(label) => [...document.querySelectorAll("#data .data-bar button")].find((b) => b.textContent === label).click()"""
DATA_LINES = """() => [document.querySelector("#data .data-bar .note").textContent, azurkit.xbr,
    document.getElementById("xbr-note").textContent, document.querySelector("#data .data-builds").textContent]"""
# All files… (Step 4.6h): one of the tab's views by its label; the section's class, line and rows as they read; a row
# (a file, or a table under it: [file, table]) clicked.
DATA_VIEW = """(label) => [...document.querySelectorAll("#data .views button")].find((b) => b.textContent === label).click()"""
DATA_FILES = """() => { const f = document.querySelector("#data .data-files");
    return [f.className, f.querySelector(":scope > p.note").textContent,
            [...f.querySelectorAll(".data-file-list > *")].map((n) => n.textContent)]; }"""
DATA_FILE = """([file, table]) => [...document.querySelectorAll("#data .data-file-list button")].find((b) =>
    b.dataset.file === file && (b.dataset.name ?? null) === table).click()"""


def test_the_data_tab_edits_reverts_and_undoes_before_an_image(browser, site, usa_iso):
    """Step 4.7a (D986, D979): with no image the Data tab shows the Player
    view of the config.xbr AzurKit ships, Starting HP's cell marked ⚠ while
    its pack is ticked; an edit there is the engine's set operation, the
    cell tinted ● with its vanilla value in its note, counted, kept for the
    build and named in the Patches tab; a value the cell can't hold is one
    red line, the engine's words; Undo, Redo and the cell's Revert move the
    edits; unticking the pack takes its ⚠ off. Its line says the edits wait
    for the image; once one is picked, Build's config.xbr is CPython's of
    the same recipe, the D28 conflict named. All files… waits for the image,
    greyed with its line (D979); open once one is picked, it lists the
    image's .xbr files as the engine does, a level file opens to none and
    config.xbr to its 18 tables, one of which shows its grid. Two edits typed before the
    first's answer both stay, and an edit whose answer comes after Clear
    edits joins the cleared list. No CSP violation, no request but GETs of
    the site's files."""
    defaults = [p["name"] for p in sdk.catalog()["packs"] if p["default_on"]]
    packs = {name: {} for name in defaults} | {"player_max_hp": {"starting_hp": 300}}
    hp = next(c for s in sdk.data({"what": "view", "kind": "player", "packs": packs})["sections"] for b in s["blocks"]
              for _, cells in b["rows"] for c in cells if c and c.get("name") == "initial hp")
    _, col, row = hp["ref"]
    op = sdk.data_edit({"edit": {"table": "settings_foo", "col": col, "row": row, "value": "500"}})["op"]
    with pytest.raises(ValueError) as refused:
        sdk.data_edit({"edit": {"table": "settings_foo", "col": col, "row": row, "value": "2147483647.5"}})
    cell, waiting = ["settings_foo", "initial hp"], "Your edits join each build, after the packs"
    served = Site(browser, site)
    try:
        page = served.open()
        _page.tick(page, list(packs), {"player_max_hp": {"starting_hp": "300"}})
        _page.click(page, "tab-data")
        shown = _page.until(page, f"() => azurkit.data.state.answer && ({DATA_CELL})({json.dumps(cell)})")
        assert shown[:2] == [f"{hp['text']} ⚠", "cell written"] and shown[2].endswith(
            "A ticked pack's slider also writes this cell; your edit wins, and the build says so.")
        assert page.evaluate(DATA_LINES) == ["0 edits", [], "", f"{waiting}: pick your image (1.) to build."]
        page.evaluate(DATA_EDIT, [*cell, "500"])   # the edit is in once its cell is drawn again, changed
        shown = _page.until(page, f"""() => {{ const c = azurkit.data.state.ops.length && ({DATA_CELL})({json.dumps(cell)});
            return c && c[1].includes("changed") && c; }}""")
        assert shown[:2] == ["● 500 ⚠", "cell changed written"] and "Changed: vanilla 200." in shown[2]
        edited = ["1 edit", [op], "The Data tab holds 1 config.xbr edit, which each build applies.",
                  f"{waiting}: pick your image (1.) to build."]
        assert page.evaluate(DATA_LINES) == edited
        page.evaluate(DATA_EDIT, [*cell, "2147483647.5"])
        assert _page.until(page, "() => document.querySelector('#data p.refused')?.textContent") == str(refused.value)
        assert page.evaluate(DATA_LINES) == edited
        for press, n, classes in (("Undo", 0, "cell written"), ("Redo", 1, "cell changed written")):
            page.evaluate(DATA_PRESS, press)
            _page.until(page, f"() => azurkit.xbr.length === {n} && ({DATA_CELL})({json.dumps(cell)})[1] === '{classes}'")
        assert page.evaluate("() => azurkit.xbr") == [op]
        page.evaluate(f"""() => {{ const table = "settings_foo", name = "initial hp"; {DATA_FIND} td.click();
            [...td.querySelectorAll("button")].find((b) => b.textContent === "Revert").click(); }}""")
        _page.until(page, f"() => !azurkit.xbr.length && ({DATA_CELL})({json.dumps(cell)})[0] === '{hp['text']} ⚠'")
        page.evaluate(DATA_PRESS, "Undo")
        _page.until(page, "() => azurkit.xbr.length === 1")
        _page.tick(page, defaults)
        _page.click(page, "tab-data")
        assert _page.until(page, f"""() => {{ const c = ({DATA_CELL})({json.dumps(cell)});
            return c && !c[1].includes("written") && c[0]; }}""") == "● 500"
        _page.tick(page, list(packs), {"player_max_hp": {"starting_hp": "300"}})
        _page.click(page, "tab-data")
        page.evaluate(DATA_VIEW, "All tables")
        page.evaluate("() => document.querySelector('#data .data-files > summary').click()")
        assert page.evaluate(DATA_FILES) == ["data-files waits", "Pick your image (1.) to list its files.", []]
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla")
        assert page.evaluate(DATA_LINES)[3] == f"{waiting}."
        files = [f["file"].removeprefix("gamedata/") for f in sdk.data({"what": "files", "iso": str(usa_iso)})["files"]]
        assert _page.until(page, f"() => ({DATA_FILES})()[2].length && ({DATA_FILES})()") == [
            "data-files", "", [f"▸ {f}" for f in files]]
        for file in ("gamedata/a1.xbr", data.FILE):
            page.evaluate(DATA_FILE, [file, None])
        configs = [f"{'● ' * t['changed']}{t['name']}" for t in sdk.data(
            {"what": "tables", "ops": page.evaluate("() => azurkit.xbr")})["tables"]]
        rows = _page.until(page, f"() => !({DATA_FILES})()[2].some((t) => t.startsWith('Reading')) && ({DATA_FILES})()[2]")
        assert rows == ["▾ config.xbr", *configs, "▾ a1.xbr", "(no keyed tables)", *[f"▸ {f}" for f in files[2:]]]
        page.evaluate(DATA_FILE, [data.FILE, "magic"])
        assert _page.until(page, "() => azurkit.data.state.answer?.name === 'magic' && azurkit.data.state.answer.file")\
            == data.FILE
        page.evaluate(DATA_VIEW, "Player")
        _page.until(page, f"() => azurkit.data.state.answer?.kind === 'player' && ({DATA_CELL})({json.dumps(cell)})")
        page.evaluate("() => document.querySelector('#build').click()")
        built = _page.built(page)
        _, report = sdk.image({"iso": str(usa_iso), "packs": mods.normalize(packs), "xbr": [op]})
        assert [built["result"][data.FILE], built["conflicts"]] == [report["result"][data.FILE], report["conflicts"]]
        player = sdk.data({"what": "view", "kind": "player"})["sections"]
        refs = {c["name"]: c["ref"] for s in player for b in s["blocks"] for _, cells in b["rows"] for c in cells
                if c and c.get("ref", [None])[0] == "settings_foo"}

        def answer(name, text, ops):   # CPython's answer to the tab's edit of a settings_foo cell
            _, c, r = refs[name]
            return sdk.data_edit({"edit": {"table": "settings_foo", "col": c, "row": r, "value": text}, "ops": ops})
        two = f"""() => {{ for (const e of [["settings_foo", "initial fuel", "501"],
            ["settings_foo", "initial fuel cap", "502"]]) ({DATA_EDIT})(e); }}"""
        # Clear edits a microtask after the edit: its ask is out with the edits before it, and its answer, a task,
        # comes after the Clear in any browser at any pace (a timer let the answer come first)
        cleared = f"""async () => {{ ({DATA_EDIT})(["settings_foo", "initial hp", "600"]);
            await null;
            ({DATA_PRESS})("Clear edits"); }}"""
        fuel = answer("initial fuel", "501", [op])["ops"]
        for script, want in ((two, answer("initial fuel cap", "502", fuel)["ops"]),
                             (cleared, [answer("initial hp", "600", [])["op"]])):
            depth = page.evaluate("() => azurkit.data.state.undo.length")
            page.evaluate(script)
            _page.until(page, f"() => azurkit.data.state.undo.length === {depth + 2}")
            assert page.evaluate("() => azurkit.xbr") == want
        assert page.evaluate("() => azurkit.violations") == [] and served.stray() == []
    finally:
        served.close()


def test_a_modkit_mod_file_loads_in_the_tools_tab_and_the_data_tabs_changes_list_what_it_changes(browser, site,
                                                                                                  tmp_path):
    """Step 4.6i (P19b, P23): the Tools tab's Load reads Modkit's mod file
    as the engine reads it, its edits the page's xbr operations, the ticks
    and settings kept; one with a retired registry.json name is refused on the status
    line by name, nothing loaded. The Data tab's Changes lists each cell the
    edits change, its vanilla value beside it, and the byte edit, as
    CPython's view has them, before an image. No CSP violation, no request
    but GETs of the site's files."""
    mod = {"name": "m", "sections": {"damage": {"enemies": {"catalisk": {"Damage": 20.0}}}},
           "_keyed_patches": {"critters_damage": {"golem": {"hitPoints": 400}}},
           "xbr_edits": [{"op": "replace_bytes", "xbr_file": "a1.xbr", "offset": 2048, "value": "aabb",
                          "value_kind": "hex", "original": "0000"}]}
    good, bad = tmp_path / "modkit.json", tmp_path / "retired.json"
    good.write_text(json.dumps(mod), encoding="utf-8")
    bad.write_text(json.dumps({"patches": [{"section": "damage", "entity": "octo", "property": "damage",
                                            "value": 9.0}]}), encoding="utf-8")
    ops = sdk.read_mods(good.read_text(encoding="utf-8"))["xbr"]
    defaults = {p["name"]: {} for p in sdk.catalog()["packs"] if p["default_on"]}
    want = sdk.data({"what": "view", "kind": "changes", "ops": ops, "packs": defaults})["sections"]
    shown = [[s["title"], [[label, *(c.get("read") or f"● {c['text']}" + " ⚠" * bool(c.get("written")) for c in cells)]
                           for label, cells in b["rows"]]] for s in want for b in s["blocks"]]
    ticked = """() => [[...document.querySelectorAll('input[data-pack]:checked')].map((b) => b.dataset.pack),
        [...document.querySelectorAll('.pack[data-pack="player_max_hp"] input[data-slider]')].map((f) => f.value)]"""
    served = Site(browser, site)
    try:
        page = served.open()
        _page.tick(page, [*defaults, "player_max_hp"], {"player_max_hp": {"starting_hp": "300"}})
        before = page.evaluate(ticked)
        assert "300" in before[1]
        _page.click(page, "tab-tools")
        _page.pick(page, "#tools-mods-file", bad)
        assert "retired.json: Modkit mod: patches[0] damage/octo/damage: a retired registry.json name" in _page.until(
            page, "() => /Modkit mod/.test(document.getElementById('status').textContent) "
                  "&& document.getElementById('status').textContent")
        _page.pick(page, "#tools-mods-file", good)
        _page.until(page, f"() => azurkit.xbr.length === {len(ops)}", 120)
        assert page.evaluate("() => azurkit.xbr") == ops and page.evaluate(ticked) == before
        assert page.evaluate("() => document.getElementById('status').textContent") == (
            f"Loaded modkit.json's recipe: the packs as ticked and {len(ops)} config.xbr edits, marked ●. Pick your "
            "vanilla image, then Build.")
        _page.click(page, "tab-data")
        _page.until(page, "() => azurkit.data.state.answer")
        page.evaluate("""() => [...document.querySelectorAll('#data .views button')]
            .find((b) => b.textContent === 'Changes').click()""")
        _page.until(page, "() => azurkit.data.state.answer?.kind === 'changes'")
        assert page.evaluate("""() => [...document.querySelectorAll('#data .data-view section')].map((s) => [
            s.querySelector('h3').textContent, [...s.querySelectorAll('tr')].filter((r) => r.querySelector('td'))
              .map((r) => [...r.children].map((c) => c.textContent))])""") == shown
        assert page.evaluate("() => azurkit.violations") == [] and served.stray() == []
    finally:
        served.close()

def test_the_sites_worker_is_kept_after_a_small_build_and_a_refused_one_and_builds_again_as_cpython(
        browser, site, usa_iso):
    """Step 4.3i: the site keeps its engine's worker after a build whose
    heap it reports is under ``KEEP`` (a refused build's too): the page is
    ready again at once, and the same worker builds the next recipe as
    CPython does. A value the engine refuses is refused by name."""
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.build(page, ["fps_unlock"], {"fps_unlock": {"target_fps": "fast"}})
        refused = _page.until(page, "() => !azurkit.building && document.querySelector('#status').textContent")
        assert "target_fps" in refused and page.evaluate("() => [azurkit.ready, azurkit.workers]") == [True, 1]
        for values in ({"target_fps": "120"}, {}):
            _page.build(page, ["fps_unlock"], {"fps_unlock": values})
            built = _built(page)
            made, report = sdk.image({"iso": str(usa_iso), "packs": page.evaluate("() => azurkit.sent")})
            assert (built["report"], built["segments"]) == (report, _signature(made))
            assert page.evaluate("() => [azurkit.ready, azurkit.workers, azurkit.heap < 1 << 30]") == [True, 1, True]
        assert served.stray() == [] and page.evaluate("() => azurkit.violations") == []
    finally:
        served.close()


HEARD = """(() => {   // what the page's workers post that the page shows nowhere: each start, digest, write and note
    const Real = Worker;
    Object.assign(globalThis, { starts: [], colds: [], digests: [], writes: [], notes: [], compiled: [], identified: [] });
    globalThis.Worker = class extends Real {
        constructor(...args) {
            super(...args);
            this.addEventListener("message", ({ data }) => {
                if (data?.type === "ready") {
                    starts.push(data.start);
                    colds.push(data.cold ?? null);
                }
                if (data?.type === "digest") digests.push(data);
                if (data?.type === "wrote") writes.push(data);
                if (data?.type === "progress") notes.push(data.label);
                if (data?.type === "wasm") compiled.push(data.module instanceof WebAssembly.Module);
                if (data?.type === "id") identified.push(data.id);
            });
        }
    };
})();"""
"""An init script: the page's workers' starts in ``starts`` (and why each that is cold didn't start from a kept
snapshot, or null, in ``colds``), their digests (DIGESTS) in ``digests``, their build
files' writes (WROTE) in ``writes``, and the label of each record they post in ``notes``, in the order the page hears
them (the bar shows the newest ask's latest: a newer ask's line, or B's work a click takes up, can hide one); each
wasm a worker compiled itself in ``compiled`` and each image id it read in ``identified`` (the pool's own messages)."""
DIGESTS = """self.azurkitDigest = crypto.subtle.digest.bind(crypto.subtle);
crypto.subtle.digest = async (name, data) => {
    const out = await azurkitDigest(name, data);
    postMessage({ type: "digest", size: data.byteLength,
                  sha256: Array.from(new Uint8Array(out), (b) => b.toString(16).padStart(2, "0")).join("") });
    return out;
};
"""
"""The worker's first lines in the next test: it posts each WebCrypto digest (HEARD holds them)."""
def test_a_site_build_hashes_its_changed_files_in_webcrypto_and_is_cpythons_build(browser, site, usa_iso):
    """R2.6: each file a build changes gets its report's sha256 from the
    browser's WebCrypto, and the build is CPython's, byte for byte."""
    served = Site(browser, site)
    try:
        served.context.add_init_script(HEARD)
        worker = (site / "worker.mjs").read_text(encoding="utf-8")
        served.context.route("**/worker.mjs", lambda route: route.fulfill(
            body=DIGESTS + worker, content_type="text/javascript"))
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        page.evaluate("() => { digests.length = 0; }")   # the image's check's
        _page.build(page, ["fps_unlock"], {"fps_unlock": {"target_fps": "120"}})
        built = _built(page)
        made, report = sdk.image({"iso": str(usa_iso), "packs": page.evaluate("() => azurkit.sent")})
        assert (built["report"], built["segments"]) == (report, _signature(made))
        heard = {d["sha256"] for d in page.evaluate("() => digests")}
        changed = {sha for name, sha in report["result"].items() if name != "filelist.txt"}   # the manifest's own
        assert changed and changed <= heard
    finally:
        served.close()


SNAPSHOT_KEPT = """() => new Promise((done) => {
    const opened = indexedDB.open("azurkit-snapshot", 1);
    opened.onupgradeneeded = () => opened.result.createObjectStore("heap");
    opened.onsuccess = () => {
        const asked = opened.result.transaction("heap").objectStore("heap").count();
        asked.onsuccess = () => { opened.result.close(); done(asked.result === 1); };
    };
})"""
SNAPSHOT_GONE = """() => new Promise((done) => { indexedDB.deleteDatabase("azurkit-snapshot").onsuccess = () => done(true); })"""
SNAPSHOT_CUT = """() => new Promise((done) => {   // the kept record's heap cut to its first 90 %: a write cut short
    const opened = indexedDB.open("azurkit-snapshot", 1);
    opened.onsuccess = () => {
        const db = opened.result, t = db.transaction("heap", "readwrite"), store = t.objectStore("heap");
        const keys = store.getAllKeys();
        let sizes = null;
        keys.onsuccess = () => {
            const got = store.get(keys.result[0]);
            got.onsuccess = () => {
                const { heap, size } = got.result;
                store.put({ heap: heap.slice(0, Math.floor(size * 0.9)), size }, keys.result[0]);
                sizes = [Math.floor(size * 0.9), size];
            };
        };
        t.oncomplete = () => { db.close(); done(sizes); };
    };
})"""
SNAPSHOT_WHOLE = """() => new Promise((done) => {   // one record, its heap and size alone: no digest to wait on
    const opened = indexedDB.open("azurkit-snapshot", 1);
    opened.onupgradeneeded = () => opened.result.createObjectStore("heap");
    opened.onsuccess = () => {
        const asked = opened.result.transaction("heap").objectStore("heap").getAll();
        asked.onsuccess = () => {
            opened.result.close();
            const [record] = asked.result;
            done(asked.result.length === 1 && Object.keys(record).sort().join() === "heap,size"
                 && record.heap.length === record.size);
        };
    };
})"""
GROW_REFUSED = """{   // the worker's first grow of a wasm memory refused, as where memory is short (the restore's: grown())
    const grow = WebAssembly.Memory.prototype.grow;
    let refused = false;
    WebAssembly.Memory.prototype.grow = function (pages) {
        if (refused) return grow.call(this, pages);
        refused = true;
        throw new RangeError("Out of memory (the test's)");
    };
}
"""


def test_a_later_worker_starts_from_the_first_ones_snapshot_also_grown_and_builds_as_cpython(browser, site, usa_iso,
                                                                                            tmp_path):
    """R2.10: the first worker of a wheel starts cold and keeps its heap's
    snapshot, and the next starts from it, not from the fallback, whose
    catch would hide a restore that throws; that worker's build is CPython's.
    A heap grown past Pyodide's initial memory restores too (the grow hook;
    stock Pyodide throws there). Step 4.4ci37: a kept record whose heap
    isn't its size (a write cut short: one cut to 90 % held the restoring
    worker's thread for good, the page never ready and saying nothing) is
    refused by name and replaced by a record of its heap and size alone
    (no hash to wait on at a start), and a restore whose grow is refused (as
    where memory is short: Pyodide swallowed the throw and never settled its
    load) starts cold, saying why: each page gets ready. Step 4.5p: each
    page runs its one engine, F (it says 2 cores, :data:`TWO_CORES`: no B),
    and closes before the next opens, so one engine runs at a time, each
    start the claim's: on GitHub's Apple Silicon runner WebKit's page
    process crashed here in JavaScriptCore's tier-up of an engine's wasm (a
    loop's OSR entry, on its worker's thread) with memory free, while the
    test held up to four pages' eight engines (run 42435914930)."""
    served = Site(browser, site, tmp_path / "profile")   # persistent: WebKit's ephemeral storage refuses a big heap's put
    try:
        served.context.add_init_script(HEARD)
        served.context.add_init_script(TWO_CORES)
        first = served.open()
        _page.until(first, SNAPSHOT_KEPT, 60)
        assert first.evaluate("() => starts") == ["cold"]
        _page.close(first)
        again = served.open()
        assert again.evaluate("() => starts") == ["snapshot"]
        _page.pick(again, "#iso", usa_iso)
        _page.until(again, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.build(again, ["fps_unlock"], {"fps_unlock": {"target_fps": "120"}})
        built = _built(again)
        made, report = sdk.image({"iso": str(usa_iso), "packs": again.evaluate("() => azurkit.sent")})
        assert (built["report"], built["segments"]) == (report, _signature(made))
        again.evaluate(SNAPSHOT_GONE)
        _page.close(again)

        worker = (site / "worker.mjs").read_text(encoding="utf-8")
        imports = 'IMPORTS = "import azurkit\\n'
        assert worker.count(imports) == 1
        served.context.route("**/worker.mjs", lambda route: route.fulfill(
            body=worker.replace(imports, f"{imports}import sys\\nsys.azurkit_grown = bytearray(8 << 20)\\n"),
            content_type="text/javascript"))
        grew = served.open()
        _page.until(grew, SNAPSHOT_KEPT, 60)
        assert grew.evaluate("() => starts") == ["cold"]
        _page.close(grew)
        after = served.open()
        assert after.evaluate("() => starts") == ["snapshot"]
        cut, size = after.evaluate(SNAPSHOT_CUT)
        _page.close(after)
        refused = served.open()
        assert refused.evaluate("() => [starts, colds]") == [
            ["cold"], [f"the kept snapshot was refused: its heap is {cut} bytes, not {size}"]]
        _page.until(refused, SNAPSHOT_WHOLE, 60)   # replaced by a whole one
        _page.close(refused)
        served.context.unroute("**/worker.mjs")
        served.context.route("**/worker.mjs", lambda route: route.fulfill(body=GROW_REFUSED + worker,
                                                                          content_type="text/javascript"))
        short = served.open()
        assert short.evaluate("() => [starts[0], colds[0]]") == [
            "cold", "the kept snapshot didn't restore: Out of memory (the test's)"]
    finally:
        served.close()


def test_a_later_engine_worker_instantiates_the_wasm_the_first_compiled_but_in_webkit_compiles_its_own(browser, site):
    """Step 4.4bf: Pyodide's wasm is compiled once a page, by its first worker, which posts the Module; B, loaded
    after F, is sent it first and instantiates it, compiling none of its own. In WebKit no worker posts one, so each
    compiles its own (Step 4.4ci47: JavaScriptCore's wasm went wrong on CI's Apple Silicon runner after 4.4bf)."""
    served = Site(browser, site)
    try:
        served.context.add_init_script(HEARD)
        page = served.open()
        _page.until(page, "() => azurkit.pool.state().b?.loaded", 300)
        shared = [] if browser.browser_type.name == "webkit" else [True]
        assert page.evaluate("() => [starts.length, compiled]") == [2, shared]
        assert page.evaluate("() => azurkit.violations") == []
    finally:
        served.close()


def test_a_seeds_build_after_the_pick_reads_the_images_id_no_more(browser, site, usa_iso):
    """Step 4.4bf: the image's id is read once a pick (by the first worker or two its File reaches, as F checks it
    while B builds ahead), never for a later message of that File: each brings the id read, B's new worker's after
    the seed's change too. The seed's build is the engine's (logic verified)."""
    served = Site(browser, site)
    try:
        served.context.add_init_script(HEARD)
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa' && azurkit.pool.state().b?.loaded", 300)
        picked = page.evaluate("() => identified.length")
        _page.click(page, "tab-randomizer")
        _page.until(page, "() => azurkit.rando.view")
        _page.click(page, "rando-on")
        _page.fill(page, "rando-seed", "2")
        page.evaluate("() => document.querySelector('#build').click()")
        assert _page.built(page)["randomizer"]["logic_verified"] is True
        heard = page.evaluate("() => [new Set(identified).size, identified.length]")
        assert picked in (1, 2) and heard == [1, picked], (picked, heard)
        assert page.evaluate("() => azurkit.violations") == []
    finally:
        served.close()


STUB_ENGINES = """(() => {
    const { catalog, view, drawn, modes = {} } = %s, made = globalThis.made = [], sent = globalThis.sent = [],
        later = [], Real = Worker;
    globalThis.held = false;
    const writes = () => /\\/outputs\\.mjs:/.test(new Error().stack.split("\\n").find((at) => /\\.mjs:\\d/.test(at)));
    const pickers = (worker, m) => worker.say({ type: "reply", call: m.call, heap: 2 ** 28, reply: { ...view,
        chosen: { ...view.chosen, ...modes[m.given.character?.mode], weapon: m.given.character?.weapon ?? null },
        character: m.given.character } });
    globalThis.release = () => {
        held = false;
        for (const [worker, m] of later.splice(0)) pickers(worker, m);
    };
    globalThis.Worker = class {
        constructor(...args) {
            if (writes()) return new Real(...args);   // the Save's build file writer: no engine, a real one
            this.got = [];
            this.heard = [];
            this.stopped = false;
            made.push(this);
            setTimeout(() => this.say({ type: "ready", catalog, version: "0" }));
        }
        addEventListener(type, hear) { if (type === "message") this.heard.push(hear); }
        say(data) {
            this.onmessage?.({ data });
            for (const hear of this.heard) hear({ data });
        }
        postMessage(m) {
            this.got.push(m);
            sent.push(m);
            if (m.type === "preview" && !m.recipe.character.shapes) {   // a body's own pictures
                return setTimeout(() => this.say({ type: "reply", call: m.call, reply: drawn, heap: 2 ** 28 }));
            }
            if (m.type !== "pickers") return;
            if (held) later.push([this, m]);
            else pickers(this, m);
        }
        terminate() { this.stopped = true; }
    };
})();"""
"""The site's engines as stubs that load at once and answer pickers (``view``, with the weapon asked and, asked at a
mode ``modes`` names, that mode's chosen fields; held until ``release()``) and a body's own pictures (``drawn``):
``made`` holds each with what it ``got``, its ``stopped``, ``sent`` what the page posted to any of them, in order;
the test answers each reshape's preview with ``say``. The worker Firefox's build starts to write its Save's build file
(``outputs.mjs``'s ``written``, the first page module on the stack at its ``new Worker``) is no engine: a real one, not
in ``made`` (as a stub it was a third, its ``ready`` taken for a failed write, and stopped).
Left unanswered, the page's preview of the chosen model (sent whenever its first draw comes before
``characters/index.json``) held F, so the pickers after it waited on B (none on a 3-core runner, run 41521288667)
and a draw for its key while the index loaded left the model unshown."""


def test_a_sites_reshape_dress_runs_in_the_worker_the_page_grew_its_small_asks_beside_it(browser, site):
    """D1011, D1054: a shape slider's Preview shows with its pickers
    unanswered; 3.5 s after it rests the dress is a heavy ask of the page's
    engine (one heap: it runs in the worker a build grew, never in one of its
    own beside it), its records on the bar, with what this browser keeps
    installed; a shape moved meanwhile shows its Preview at once, its pickers
    answered by the other worker, and is dressed after it; a refusal leaves
    the Preview marked, saying why; a Build clicked at the change goes first,
    the dress after it, in the same worker."""
    view = sdk.pickers({"iso": None, "character": {"species": "garret4"}})
    view["chosen"] |= {"name": "booblord", "variant": "booblord", "shapes": [{"name": "bust", "title": "Bust size"}]}
    drawn = {side: base64.b64encode((_page.WEB / "characters" / f"nice_noreht.{side}.png").read_bytes()).decode()
             for side in ("front", "back")}
    served = Site(browser, site)
    served.context.add_init_script(STUB_ENGINES % json.dumps({"catalog": sdk.catalog(), "view": view, "drawn": drawn}))
    moved = """(value) => { const b = document.getElementById("char-shape:bust"); b.value = value;
        b.dispatchEvent(new Event("change")); }"""

    def shows(x: float, preview: bool) -> str:
        shape = json.dumps(json.dumps([["bust", x]], separators=(",", ":")))
        return f"""() => {{ const s = azurkit.characters.state.shown; return s?.shape === {shape} && s.preview === {json.dumps(preview)}; }}"""
    dressing = "(m) => m.type === 'preview' && m.recipe.character.shapes"   # a reshape's dress
    f = f"made.find((w) => w.got.some({dressing}))"   # the worker the page's heavy asks run in
    previews = f"({f}?.got.filter({dressing}) ?? [])"
    line = "() => document.getElementById('progress-row').hidden ? null : document.getElementById('progress-line').textContent"
    try:
        page = served.open()
        page.evaluate("() => { azurkit.file = new File(['x'], 'x.iso'); azurkit.asked = azurkit.file; "   # its image read
                      "azurkit.engine.content({ a: 1 }, { b: 1 }); }")
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view && made.length === 2", 60)
        page.evaluate("() => azurkit.characters.set({ species: 'booblord' })")
        _page.until(page, "() => azurkit.characters.state.shown?.name === 'booblord'", 60)

        page.evaluate("() => { held = true; }")
        page.evaluate(moved, "1.25")
        _page.until(page, shows(1.25, True), 10)   # its pickers unanswered
        page.evaluate("() => release()")
        _page.until(page, f"() => {previews}.length === 1", 10)
        assert page.evaluate(f"""() => [made.length, {f}.got.some((m) => m.type === "content"),
            {previews}[0].file.name, {previews}[0].recipe.character]""") == [
            2, True, "x.iso", {"species": "booblord", "shapes": {"bust": 1.25}}]
        page.evaluate(f"""() => {f}.say({{ type: "progress", stage: "dress", label: "Dressing", percent: 40 }})""")
        assert page.evaluate(line) == "Dressing… 40 %"

        page.evaluate(moved, "1.3")   # the dress runs: the Preview at once, its pickers by B, its dress after
        _page.until(page, shows(1.3, True), 10)
        assert page.evaluate(f"""() => made.some((w) => w !== {f} && w.got.some((m) => m.type === "pickers"
            && m.given.character.shapes?.bust === 1.3))""")
        page.evaluate(f"(reply) => {f}.say({{ type: 'reply', call: {previews}[0].call, reply, heap: 2 ** 30 }})", drawn)
        _page.until(page, f"() => {previews}.length === 2", 10)
        assert page.evaluate(f"() => [{previews}[1].recipe.character.shapes, azurkit.characters.state.pictures.size]") == [
            {"bust": 1.3}, 1]
        page.evaluate(f"""() => {f}.say({{ type: "reply", call: {previews}[1].call, reply: {{ refused: "no dress" }},
            heap: 2 ** 30 }})""")
        _page.until(page, "() => document.getElementById('char-preview-note').textContent === 'Preview: no dress'", 10)
        assert page.evaluate(shows(1.3, True))

        page.evaluate(moved, "1.4")   # a Build at once: it goes first, the dress after it, in the worker it grew
        _page.until(page, shows(1.4, True), 10)
        page.evaluate("() => { const b = document.getElementById('build'); b.disabled = false; b.click(); }")
        _page.until(page, f"() => {f}.got.some((m) => m.type === 'build')", 10)
        page.wait_for_timeout(4000)
        assert page.evaluate(f"() => {previews}.length") == 2
        page.evaluate(f"""() => {f}.say({{ type: "built", size: 1, segments: [], blob: new Blob(["x"]), heap: 2 ** 31,
            report: {{ label: "USA", result: {{}}, layers: [], conflicts: [], notes: [] }} }})""")
        _page.until(page, f"() => {previews}.length === 3", 10)
        page.evaluate(f"(reply) => {f}.say({{ type: 'reply', call: {previews}[2].call, reply, heap: 2 ** 31 }})", drawn)
        _page.until(page, shows(1.4, False), 10)
        assert page.evaluate("() => [made.length, made.some((w) => w.stopped)]") == [2, False]
    finally:
        served.close()


def test_a_cancel_of_a_build_queued_behind_a_reshapes_dress_dresses_the_shape_shown_again(browser, site):
    """A Cancel ends every heavy ask: a Build queued behind a reshape's
    running dress takes the dress with it (its worker replaced), and the
    shape still shown is dressed again after it, its exact pictures shown,
    not left a Preview until the shape changes."""
    view = sdk.pickers({"iso": None, "character": {"species": "garret4"}})
    view["chosen"] |= {"name": "booblord", "variant": "booblord", "shapes": [{"name": "bust", "title": "Bust size"}]}
    drawn = {side: base64.b64encode((_page.WEB / "characters" / f"nice_noreht.{side}.png").read_bytes()).decode()
             for side in ("front", "back")}
    served = Site(browser, site)
    served.context.add_init_script(STUB_ENGINES % json.dumps({"catalog": sdk.catalog(), "view": view, "drawn": drawn}))
    previews = "made.flatMap((w) => w.got.filter((m) => m.type === 'preview' && m.recipe.character.shapes))"
    exact = json.dumps(json.dumps([["bust", 1.25]], separators=(",", ":")))
    try:
        page = served.open()
        page.evaluate("() => { azurkit.file = new File(['x'], 'x.iso'); azurkit.asked = azurkit.file; }")
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view && made.length === 2", 60)
        page.evaluate("() => azurkit.characters.set({ species: 'booblord' })")
        _page.until(page, "() => azurkit.characters.state.shown?.name === 'booblord'", 60)
        page.evaluate("""() => { const b = document.getElementById("char-shape:bust"); b.value = "1.25";
            b.dispatchEvent(new Event("change")); }""")
        _page.until(page, f"() => {previews}.length === 1", 10)   # its dress runs
        page.evaluate("() => { const b = document.getElementById('build'); b.disabled = false; b.click(); }")
        _page.until(page, "() => !document.getElementById('cancel').hidden", 10)
        assert page.evaluate("() => made.some((w) => w.got.some((m) => m.type === 'build'))") is False   # queued
        page.evaluate("() => document.getElementById('cancel').click()")
        _page.until(page, f"() => {previews}.length === 2", 10)
        assert page.evaluate(f"() => [{previews}[1].recipe.character.shapes, made.filter((w) => w.stopped).length]") == [
            {"bust": 1.25}, 1]
        page.evaluate(f"""(reply) => {{ const m = {previews}[1];
            made.find((w) => w.got.includes(m)).say({{ type: "reply", call: m.call, reply, heap: 2 ** 30 }}); }}""", drawn)
        _page.until(page, f"""() => {{ const s = azurkit.characters.state.shown;
            return s?.shape === {exact} && s.preview === false; }}""", 10)
    finally:
        served.close()


def test_reset_puts_every_slider_option_and_the_weapon_back_in_its_click(browser, site):
    """D1062, Step 4.4u2: Reset shows the chosen model's defaults in its
    own click, before the engine answers it: every number (the jiggle's and
    a shape's too) at 1, every option and the Weapon box at the model's own
    (the moved mode's defaults not), and its own pictures, the shape's
    dress no longer wanted; the engine's answer, held here, changes none
    of them."""
    view = sdk.pickers({"iso": None, "character": {"species": "town_female_1"}})   # springs, its options live
    view["chosen"] |= {"name": "booblord", "variant": "booblord", "shapes": [{"name": "bust", "title": "Bust size"}]}
    weapon = next(w["name"] for w in view["chosen"]["weapons"] if w["name"])
    moved = sdk.pickers({"iso": None, "character": {"species": "town_female_1", "mode": "garret4"}})["chosen"]
    assert moved["defaults"] != view["chosen"]["defaults"]   # Balance and Ground off: a Reset holding it shows them
    drawn = {side: base64.b64encode((_page.WEB / "characters" / f"nice_noreht.{side}.png").read_bytes()).decode()
             for side in ("front", "back")}
    served = Site(browser, site)
    served.context.add_init_script(STUB_ENGINES % json.dumps({"catalog": sdk.catalog(), "view": view, "drawn": drawn,
                                                              "modes": {"garret4": {"defaults": moved["defaults"]}}}))
    shown = """() => { const c = azurkit.characters.state, $ = (id) => document.getElementById(id);
        return [c.character, [...document.querySelectorAll("#char-numbers input[type=text]")].map((b) => b.value).join(),
                $("char-weapon").value, $("char-mode").value, ["char-chain", "char-clips", "char-sounds", "char-height",
                "char-balance", "char-ground"].map((id) => $(id).checked), c.shown && [c.shown.shape, c.shown.preview]]; }"""
    answered = """() => { const c = azurkit.characters.state;
        return c.view?.asked === JSON.stringify(c.character) && Object.keys(c.character).length; }"""
    try:
        page = served.open()
        page.evaluate("() => { azurkit.file = new File(['x'], 'x.iso'); azurkit.asked = azurkit.file; }")
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view && made.length === 2", 60)
        page.evaluate("() => azurkit.characters.set({ species: 'booblord' })")
        _page.until(page, f"() => ({answered})() && azurkit.characters.state.shown?.name === 'booblord'", 60)
        own = page.evaluate(shown)
        assert own == [{"species": "booblord"}, ",".join(["1"] * 7), "", "own", [False, False, True, False, True, True],
                       ["[]", False]]
        page.evaluate(_perf.MOVE_ALL)
        assert _page.until(page, f"() => ({_perf.MOVED})() && ({_perf.PREVIEWED})() && ({shown})()", 60) == [
            {"species": "booblord", **dict.fromkeys(("scale", "attack_reach", "attack_damage", "attack_speed",
                                                     "jiggle_strength", "jiggle_stiffness"), 1.2),
             "shapes": {"bust": 1.2}, "weapon": weapon, "mode": "garret4", "chain": "any", "anims": "own",
             "sounds": "garret4", "size": "garret4", "attack_balance": False, "attack_ground": False},
            ",".join(["1.2"] * 7), weapon, "garret4", [True, True, False, True, False, False], ['[["bust",1.2]]', True]]
        page.evaluate("() => { held = true; }")
        assert page.evaluate(f"() => {{ document.getElementById('char-reset').click(); return ({shown})(); }}") == own
        assert page.evaluate(f"() => [({answered})(), azurkit.characters.state.wanted, ({_perf.RESET})()]") == [
            False, None, True]   # A81's and S66's done-state too
        page.evaluate("() => release()")
        _page.until(page, answered, 10)
        assert page.evaluate(shown) == own
    finally:
        served.close()


def test_a_sliders_drag_keeps_one_ask_in_flight_and_asks_its_last_value_once_that_answers(browser, site):
    """Step 4.4u2: the Characters tab asks the engine one ask at a time: a
    drag's input events while one runs are asked once it answers, as the
    tab's choice is then (one ask, its last value), where each event queued
    an ask of its own in the engine's worker (about 0.4 s each in WebKit) and
    every answer after them, a Reset's too, waited for them all."""
    view = sdk.pickers({"iso": None, "character": {"species": "keylord"}})
    drawn = {side: base64.b64encode((_page.WEB / "characters" / f"nice_noreht.{side}.png").read_bytes()).decode()
             for side in ("front", "back")}
    served = Site(browser, site)
    served.context.add_init_script(STUB_ENGINES % json.dumps({"catalog": sdk.catalog(), "view": view, "drawn": drawn}))
    # the image's asks in the order the page sent them, to F or B (F's list, then B's, put one B took after F's later)
    sizes = "() => sent.filter((m) => m.type === 'pickers' && m.file).map((m) => m.given.character.scale)"
    answered = "() => azurkit.characters.state.view?.asked === JSON.stringify(azurkit.characters.state.character)"
    try:
        page = served.open()
        page.evaluate("() => { azurkit.file = new File(['x'], 'x.iso'); azurkit.asked = azurkit.file; }")
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view && made.length === 2", 60)
        page.evaluate("() => azurkit.characters.set({ species: 'keylord' })")
        # keylord's answer shown, the community list read (its end asks again) and no ask in flight
        _page.until(page, f"() => ({answered})() && azurkit.characters.state.view.chosen.name === 'keylord' "
                          f"&& ({_perf.SPECIES_LISTED})() && !azurkit.characters.state.asking", 60)
        before = len(page.evaluate(sizes))
        page.evaluate("() => { held = true; }")
        page.evaluate(_perf.DRAG)
        assert page.evaluate(sizes)[before:] == [1.05]   # the first value's ask runs; the rest wait for it
        page.evaluate("() => release()")
        _page.until(page, answered, 10)
        assert page.evaluate(sizes)[before:] == [1.05, 2]
        assert page.evaluate("() => [azurkit.characters.character(), document.getElementById('char-scale').value]") == [
            {"species": "keylord", "scale": 2}, "2"]
    finally:
        served.close()


def test_the_saved_file_is_the_image_cpython_builds_and_opens_back_into_its_recipe(browser, site, usa_iso):
    """Every pack on the USA image: Save downloads ``<stem> (AzurKit).iso``,
    whose size and sha256 are those of CPython's image of the same recipe.
    Picked as the image, that build shows as an AzurKit build
    (``sdk.open_build``), and Load its recipe ticks every pack again."""
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.build(page, list(mods.PACKS))
        _page.built(page)
        with page.expect_download(timeout=600_000) as caught:
            page.evaluate("() => document.querySelector('#save').click()")
        download = caught.value
        try:
            saved = Path(download.path())
            with open(saved, "rb") as f:
                got = (download.suggested_filename, saved.stat().st_size, hashlib.file_digest(f, "sha256").hexdigest())
            made, _ = sdk.image({"iso": str(usa_iso), "packs": {name: {} for name in mods.PACKS}})
            assert got == (_page.saved_name(browser, f"{usa_iso.stem} (AzurKit).iso"), made.size, made.sha256())
            _page.tick(page, [])
            _page.pick(page, "#iso", saved)
            opened = _page.until(page, "() => azurkit.opened")
            assert opened == json.loads(json.dumps(sdk.open_build(made)))
            assert page.evaluate("() => document.querySelector('#picked').textContent").startswith(
                "◆ AzurKit build · USA · 17 packs")
            _page.click(page, "load-build")
            assert list(_page.ticked(page)) == list(mods.PACKS)
            assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
        finally:
            download.delete()
        assert served.stray() == []
    finally:
        served.close()


def test_a_build_and_its_save_stay_under_6_gib_of_firefoxs_processes(browser, site, usa_iso):
    """D1017, D1057: a build's image is the File's slices and a few bytes. Firefox's parent copied the whole image at a
    blob: URL of a Blob of many parts and held 2 GiB more over its download (keylord's 7.7 GiB): the page's Blob there is
    few parts it reads by reference. The rule is this Mac's (D1023), and WebKit's processes aren't this run's tree: the
    tree is sampled in Firefox here, and the Save runs everywhere."""
    measured = sys.platform == "darwin" and browser.browser_type.name == "firefox"
    before = {(pid, started) for pid, _, _, started in _perf.Memory.rows()} if measured else set()
    memory = _perf.Memory(lambda rows: _perf.browser_pids(rows, before)) if measured else contextlib.nullcontext()
    served = Site(browser, site)
    try:
        with memory:
            page = served.open()
            _page.pick(page, "#iso", usa_iso)
            _page.build(page, list(mods.PACKS))
            _page.built(page)
            with page.expect_download(timeout=600_000) as caught:
                page.evaluate("() => document.querySelector('#save').click()")
            caught.value.path()
            assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
            caught.value.delete()
        if measured:
            assert 0 < memory.peak <= 6 * 2**30
    finally:
        served.close()


def test_a_builds_save_is_greyed_with_its_own_bar_while_its_blob_is_made_and_never_waits_at_the_click(browser, site, usa_iso):
    """D979, D980, D1053: Firefox's Blob is made after the build's answer (its build file's hold held here), Save greyed
    and named with a bar of its own, which a worker's record doesn't take over and which counts the copy's bytes to the
    end (a keylord build's copy took 0.56-1.18 s, R14's wait: Step 4.4m). So in every browser a click's download and
    check start in its tick. Firefox's Blob reads the bytes between its kept copies from a build file of their own
    (Step 4.5q), kept while its build is and removed once a change forgets an unsaved one; no other browser makes one."""
    held = """() => { const real = LockManager.prototype.request;
        LockManager.prototype.request = function (name, ...rest) {
            if (globalThis.release || !name.startsWith("azurkit-build-") || rest[0]?.mode !== "shared") {
                return real.call(this, name, ...rest);
            }
            return new Promise((go) => { globalThis.release = go; }).then(() => real.call(this, name, ...rest));
        }; }"""
    workers = """{ const Real = Worker; globalThis.workers = [];
        globalThis.Worker = class extends Real { constructor(...on) { super(...on); workers.push(this); } }; }"""
    line = "document.getElementById('progress-line').textContent"
    ready = "Getting your image ready to save"
    served = Site(browser, site)
    try:
        served.context.add_init_script(workers)
        page = served.open()
        page.evaluate(held)
        _page.pick(page, "#iso", usa_iso)
        _page.build(page, [])
        _page.until(page, "() => azurkit.build && azurkit.ready", 300)
        if browser.browser_type.name == "firefox":
            assert page.evaluate("""() => { const save = document.getElementById('save');
                return [save.disabled, save.title, document.getElementById('progress-row').hidden]; }""") == [
                True, f"{ready}…", False]
            page.evaluate("""() => { const bar = document.getElementById('progress'); globalThis.shown = [];
                new MutationObserver(() => shown.push(bar.getAttribute('value')))
                  .observe(bar, { attributes: true, attributeFilter: ['value'] }); }""")
            page.evaluate("() => workers[0].onmessage({ data: { type: 'progress', stage: 'read', label: 'Other', percent: 5 } })")
            _page.until(page, f"() => {line}.startsWith('{ready}')")
            assert page.evaluate("() => document.getElementById('progress').getAttribute('value')") == "0"
            page.evaluate("() => globalThis.release()")
        _page.built(page)
        between = page.evaluate("() => azurkit.build.between ?? null")
        if browser.browser_type.name == "firefox":
            assert "100" in page.evaluate("() => shown")   # its bytes counted to the end
            assert between in page.evaluate(BUILD_FILES)
            _page.tick(page, ["fps_unlock"])   # a change: the build is forgotten, its file with it
            _page.until(page, f"async () => !(await ({BUILD_FILES})()).includes({json.dumps(between)})", 60)
            _page.build(page, [])
            _page.built(page)
        else:
            assert between is None
        with page.expect_download(timeout=600_000) as caught:
            assert page.evaluate("() => { document.querySelector('#save').click(); return azurkit.saveCheck; }") == "running"
        assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
        caught.value.delete()
    finally:
        served.close()


FULL = """FileSystemSyncAccessHandle.prototype.write = function () {
    throw new DOMException("The disk is full", "QuotaExceededError");
};
"""
"""flat.mjs's first lines in the next test: its build file takes no byte, as a write past a full disk's room is refused."""


@pytest.mark.parametrize("refused", ["private", "full"])
def test_a_save_holds_where_the_origins_file_system_refuses_the_build_file(browser, site, usa_iso, tmp_path, refused):
    """D1057: Firefox's private window refuses the origin's private file system, and keeps ``Response.blob()`` in
    memory, so a Blob of few parts would hold more than the plain one (7.2 GiB against 4.8): there the page makes none
    (no build file for its bytes between the copies, nor a copy of them), and the Save holds. Where the file system is
    there but takes no byte (a full disk), the build file is let go, its bytes go into a Response's Blob, Firefox's
    temporary file, as before Step 4.5q, and Save opens and holds (Step 4.5u). Only Firefox makes either."""
    firefox = browser.browser_type.name == "firefox"
    prefs = {"firefox_user_prefs": {"browser.privatebrowsing.autostart": True}} if firefox and refused == "private" else {}
    served = Site(browser, site, tmp_path / "profile", **prefs)
    try:
        if refused == "full":
            flat = (site / "flat.mjs").read_text(encoding="utf-8")
            served.context.route("**/flat.mjs", lambda route: route.fulfill(body=FULL + flat, content_type="text/javascript"))
        page = served.open()
        page.evaluate("""() => { const lock = LockManager.prototype.request, blob = Response.prototype.blob;
            globalThis.made = globalThis.copied = 0;
            LockManager.prototype.request = function (name, ...rest) {   // a build file's hold
                globalThis.made += name.startsWith("azurkit-build-") && rest[0]?.mode === "shared";
                return lock.call(this, name, ...rest); };
            Response.prototype.blob = function () {   // the page's own copy, not a fetch's
                globalThis.copied += !this.url; return blob.call(this); }; }""")
        _page.pick(page, "#iso", usa_iso)
        _page.build(page, ["fps_unlock"])   # bytes between the copies (a build of no pack has none to write)
        _page.built(page)
        with page.expect_download(timeout=600_000) as caught:
            page.evaluate("() => document.querySelector('#save').click()")
        assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
        made = int(firefox and refused == "full")
        assert page.evaluate("() => [made, copied, azurkit.build.between ?? null]") == [made, made, None]
        if refused == "full":
            _page.until(page, f"async () => (await ({BUILD_FILES})()).length === 0", 60)   # the refused file removed
        caught.value.delete()
    finally:
        served.close()


def test_a_save_fails_by_name_when_its_image_changed_after_the_build(browser, site, usa_iso, tmp_path):
    """D35: a byte of the picked image changed on disk between Build and Save (Firefox reads the new bytes silently,
    WebKit and Chromium fail the read): the Save fails with what to do and the build goes, as the page can't stop the
    browser's download."""
    image = tmp_path / usa_iso.name
    if subprocess.run(["cp", "-c", str(usa_iso), str(image)], capture_output=True).returncode:
        shutil.copyfile(usa_iso, image)
    image.chmod(0o644)   # a clone keeps the source's read-only mode
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", image)
        _page.build(page, [])
        _page.built(page)
        with iso.Reader(image) as r:   # a file the build didn't change, nor read
            at = max(r.start(e) + e.size // 2 for e in r.entries() if not e.is_dir and e.size
                     and not e.path.startswith(gate.BUILD_FILES))
        with open(image, "r+b") as f:
            f.seek(at)
            byte = f.read(1)
            f.seek(at)
            f.write(bytes([byte[0] ^ 1]))
        page.evaluate("() => document.querySelector('#save').click()")
        failed = _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck")
        assert failed.startswith("Save failed: your image changed since you picked it")
        assert page.evaluate("() => [azurkit.build, document.querySelector('#status').textContent, "
                             "document.querySelector('#status').classList.contains('error')]") == [None, failed, True]
    finally:
        served.close()


def test_a_save_hashes_only_what_the_page_hasnt_hashed_from_its_image_and_fails_once_the_image_changed(
        browser, site, usa_iso, tmp_path):
    """D35, Step 4.4ba: where a File changed on disk refuses every read (WebKit's, Chromium's), the page knows the
    sha256 of each file of the picked image hashed from it (the pick's check, then the rest, hashed after it in the
    background), so a Save hashes only the Blob's files that aren't the File's own bytes in place (the build's changed
    files), and one read of the File, refused once it changed, fails the next Save by name. Firefox reads a changed
    File silently: its Save hashes the changed files' input and every file of the Blob. The site's work ahead waits
    while a Save is checked."""
    image = tmp_path / usa_iso.name
    if subprocess.run(["cp", "-c", str(usa_iso), str(image)], capture_output=True).returncode:
        shutil.copyfile(usa_iso, image)
    image.chmod(0o644)   # a clone keeps the source's read-only mode
    files, refused = len(gate.layout(image, ("",))), browser.browser_type.name != "firefox"
    served = Site(browser, site)
    try:
        served.context.add_init_script("""{ const real = Worker.prototype.postMessage; globalThis.hashing = [];
            Worker.prototype.postMessage = function (message, ...rest) {   // each page hash's bytes
                if (message?.rows) hashing.push(message.rows.reduce((n, [, , size]) => n + size, 0));
                return real.call(this, message, ...rest); }; }""")
        page = served.open()
        _page.pick(page, "#iso", image)
        if refused:   # the rest too, hashed after the pick's check
            _page.until(page, f"() => [...azurkit.vouched.values()].some((k) => Object.keys(k).length === {files})", 300)
        page.evaluate("() => document.querySelector('#build').click()")   # the page's default packs
        _page.built(page)
        rows, given, segments = page.evaluate("() => [azurkit.build.checks.image, azurkit.build.checks.input, "
                                              "azurkit.build.segments]")
        with page.expect_download(timeout=600_000) as caught:
            page.evaluate("() => { hashing.length = 0; document.querySelector('#save').click(); }")
        assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
        written, at = [], 0   # the Blob's spans that aren't the File's own bytes there
        for segment in segments:
            if not (segment["kind"] == "copy" and segment["offset"] == at):
                written.append((at, at + segment["size"]))
            at += segment["size"]
        mine = [size for _, at, size, _, held in rows   # its files the build wrote or moved (default.xbe, filelist.txt)
                if held != at or any(start < at + size and at < end for start, end in written)]
        assert 0 < len(mine) < len(rows) and page.evaluate("() => hashing") == (
            [sum(mine)] if refused else [sum(row[2] for row in given), sum(row[2] for row in rows)])
        caught.value.delete()
        with iso.Reader(image) as r:   # a file the build didn't change, nor read
            at = max(r.start(e) + e.size // 2 for e in r.entries() if not e.is_dir and e.size
                     and not e.path.startswith(gate.BUILD_FILES))
        with open(image, "r+b") as f:
            f.seek(at)
            byte = f.read(1)
            f.seek(at)
            f.write(bytes([byte[0] ^ 1]))
        assert page.evaluate("""() => { const asked = [], real = azurkit.engine.ahead;
            azurkit.engine.ahead = (...items) => asked.push(items);
            document.querySelector('#save').click();
            azurkit.changed();   // a change while the Save is checked: no work ahead until it ends
            azurkit.engine.ahead = real;
            return [azurkit.saveCheck, asked.length]; }""") == ["running", 0]
        failed = _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck")
        assert failed.startswith("Save failed: your image changed since you picked it")
    finally:
        served.close()


def test_a_save_while_the_images_rest_is_hashed_waits_for_its_digests_and_hashes_only_the_builds_files(
        browser, site, usa_iso):
    """D35, Step 4.4bl: a Save made while the picked image's rest is hashed in the background (WebKit's, Chromium's;
    slowed here) hashes only the Blob's files that aren't the File's own bytes in place and waits for the rest's digests
    for the others, never hashing them a second time beside it; when the worker hashing the rest stops first, the Save
    hashes those files itself. Firefox has no rest: its Save hashes the input's files and every file, as before."""
    refused = browser.browser_type.name != "firefox"
    hasher = (site / "hasher.mjs").read_text(encoding="utf-8")
    read = "await source.slice(run.start, run.end).arrayBuffer()"
    assert hasher.count(read) == 1
    slow = hasher.replace(read, f"await new Promise((late) => setTimeout(late, 3000)).then(() => {read.removeprefix('await ')})")
    for stop in (False, True) if refused else (False,):
        served = Site(browser, site)
        try:
            served.context.route("**/hasher.mjs", lambda route: route.fulfill(body=slow, content_type="text/javascript"))
            served.context.add_init_script("""{ const real = Worker.prototype.postMessage; globalThis.hashing = [];
                Worker.prototype.postMessage = function (message, ...rest) {   // each page hash's bytes
                    if (message?.rows) hashing.push(message.rows.reduce((n, [, , size]) => n + size, 0));
                    return real.call(this, message, ...rest); }; }""")
            page = served.open()
            _page.pick(page, "#iso", usa_iso)
            if refused:
                _page.until(page, "() => azurkit.resting.size === 1", 300)
            page.evaluate("() => document.querySelector('#build').click()")   # the page's default packs
            _page.built(page)
            rows, given, segments = page.evaluate("() => [azurkit.build.checks.image, azurkit.build.checks.input, "
                                                  "azurkit.build.segments]")
            with page.expect_download(timeout=600_000) as caught:
                resting, known = page.evaluate("""(stop) => {
                    hashing.length = 0;
                    const resting = azurkit.resting.size, known = Object.keys(azurkit.vouched.get(azurkit.build.checks.id) ?? {});
                    document.querySelector('#save').click();
                    if (stop) for (const rest of azurkit.resting.values()) rest.worker.terminate();
                    return [resting, known]; }""", stop)
            assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
            caught.value.delete()
            written, at = [], 0   # the Blob's spans that aren't the File's own bytes there
            for segment in segments:
                if not (segment["kind"] == "copy" and segment["offset"] == at):
                    written.append((at, at + segment["size"]))
                at += segment["size"]
            mine = [row for row in rows if row[4] != row[1]
                    or any(start < row[1] + row[2] and row[1] < end for start, end in written)]
            waited = [row for row in rows if row not in mine and row[0] not in known]
            assert resting == refused and 0 < len(mine) < len(rows) and waited
            assert sorted(page.evaluate("() => hashing")) == (
                sorted([sum(r[2] for r in mine), sum(r[2] for r in waited)]) if stop
                else [sum(r[2] for r in mine)] if refused
                else sorted([sum(r[2] for r in given), sum(r[2] for r in rows)]))
            assert stop or not refused or page.evaluate(
                "(paths) => paths.every((p) => p in azurkit.vouched.get(azurkit.build.checks.id))", [r[0] for r in rows])
        finally:
            served.close()


def test_the_images_rest_is_walked_by_the_worker_that_hashes_it_and_the_other_reads_nothing_of_the_image_for_it(
        browser, site, usa_iso):
    """Step 4.4ci30: where a browser refuses a changed File's reads (WebKit's, Chromium's), the picked image's rest is
    hashed in the background by the worker whose check hashed the image (Step 4.4ba; slowed here). B, the free worker,
    primes for its first job (the image's setup built ahead) while that hash runs, and looks before it walks the image
    for the rest: with the rest's lock held, or its digests in the stamp, it reads nothing of the image after its job,
    where it walked the image's whole layout for nothing, its engine held and the File read again (and on Windows a
    File WebKit reads can't be written meanwhile). Firefox reads a changed File silently: no rest, no walk."""
    refused = browser.browser_type.name != "firefox"
    hasher, worker = ((site / name).read_text(encoding="utf-8") for name in ("hasher.mjs", "worker.mjs"))
    read = "await source.slice(run.start, run.end).arrayBuffer()"
    walk = 'const rest = mounted(loaded.py, file, (iso) => loaded.engine({ type: "layout", recipe: { iso }, whole: true }));'
    assert hasher.count(read) == 1 and worker.count(walk) == 1
    slow = hasher.replace(read, f"await new Promise((late) => setTimeout(late, 3000)).then(() => {read.removeprefix('await ')})")
    counted = worker.replace(walk, f"self.restWalks = (self.restWalks ?? 0) + 1; {walk}")   # each walk for the rest
    files = len(gate.layout(usa_iso, ("",)))
    served = Site(browser, site)
    try:
        served.context.route("**/hasher.mjs", lambda route: route.fulfill(body=slow, content_type="text/javascript"))
        served.context.route("**/worker.mjs", lambda route: route.fulfill(body=counted, content_type="text/javascript"))
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.until(page, "() => { const s = azurkit.pool.state(); return s.b?.loaded && !s.b.job && s.kept.length; }",
                    600)   # B's first job ended: the image's setup built ahead
        if refused:   # and the rest hashed
            _page.until(page, f"() => [...azurkit.vouched.values()].some((k) => Object.keys(k).length === {files})", 300)
        assert _page.checks(page, "restWalks") == (1 if refused else 0)
    finally:
        served.close()


def test_an_image_changed_between_its_pick_and_the_build_fails_the_build_or_its_save(browser, site, usa_iso, tmp_path):
    """D35: a byte of a level, outside what the seed's build reads and patches, changed after the pick and before Build.
    The changed level's sha is hashed from that File, so the build's own number agrees with it: Firefox reads the new bytes
    silently and builds, and only the release's sha of the level fails its Save; WebKit and Chromium refuse the read,
    and the build fails naming the change: the engine's read is an OSError, never a throw that Pyodide takes as fatal
    (Step 4.4ci30). The byte changes once the page holds still, its image's rest hashed (WebKit's, Chromium's, Step 4.4ba) and no worker
    on a job: on Windows WebKit opens each read of a File sharing it with readers only, so a write while one is open is
    refused by Windows itself (``PermissionError``), not by the page (Step 4.4ci30)."""
    image = tmp_path / usa_iso.name
    if subprocess.run(["cp", "-c", str(usa_iso), str(image)], capture_output=True).returncode:
        shutil.copyfile(usa_iso, image)
    image.chmod(0o644)   # a clone keeps the source's read-only mode
    with iso.Reader(image) as r:
        level = max(generator.sections(generator.prepare({"seed": "2"}, {}), r).values(), key=lambda view: view.size)
    at = level.size // 2
    while level.holds(at, at + 1):
        at += 4096
    files, refused = len(gate.layout(image, ("",))), browser.browser_type.name != "firefox"
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", image)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.until(page, f"""() => {{ const s = azurkit.pool.state();   // the File read by nothing now
            return !s.queued && !s.f?.job && (!s.b || (s.b.loaded && !s.b.job)) && (!{json.dumps(refused)}
                || [...azurkit.vouched.values()].some((k) => Object.keys(k).length === {files})); }}""", 600)
        with open(image, "r+b") as f:
            f.seek(level.start + at)
            byte = f.read(1)
            f.seek(level.start + at)
            f.write(bytes([byte[0] ^ 1]))
        _page.click(page, "tab-randomizer")
        _page.until(page, "() => azurkit.rando.view")
        _page.click(page, "rando-on")
        _page.fill(page, "rando-seed", "2")
        page.evaluate("() => { azurkit.build = null; document.querySelector('#build').click(); }")
        if _page.until(page, "() => azurkit.build ? 'built' : document.querySelector('#status').classList.contains('error') "
                             "&& 'refused'", 900) == "built":
            _page.built(page)
            _page.until(page, "() => azurkit.ready", 300)
            page.evaluate("() => document.querySelector('#save').click()")
            failed = _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck")
            assert failed.startswith("Save failed: your image changed since you picked it")
        else:   # by name (Step 4.4ci30: it was "Pyodide already fatally failed and can no longer be used")
            assert page.evaluate("() => document.querySelector('#status').textContent") == (
                "Your image changed since you picked it, so it can't be read: pick it again")
        assert page.evaluate("() => [azurkit.build, document.querySelector('#status').classList.contains('error')]") == [
            None, True]
    finally:
        served.close()


DEEP = 45
"""How many Python frames down a build's trap in :func:`_faults` is: Pyodide's dump of them (a header, then a line a
frame, innermost first) runs past the 40 lines the worker keeps, as its dump at numpy's import did (72 lines)."""


def _faults(worker: str, usa: str) -> str:
    """worker.mjs with the engine's call failing: the prime of an image that isn't ``usa`` and the build of fps_unlock
    trap the engine's wasm (a read past the heap: Pyodide's fatal error), the build's DEEP Python frames down, past
    the lines of Pyodide's dump the worker keeps, once it posted a stage at 80 %; any other build raises."""
    prime, build = '    if request.type in ("layout", "prime"):', '        if request.type == "build":   # to the pages'
    assert worker.count(prime) == worker.count(build) == 1
    return worker.replace(prime, f"""    def azurkit_fault(depth=0):
        if depth:
            return azurkit_fault(depth - 1)
        import ctypes
        ctypes.string_at(0xFFFFFFF0, 64)

    if request.type == "prime" and not str(request.recipe.iso).endswith({usa!r}):
        azurkit_fault()
{prime}""").replace(build, f"""        if request.type == "build":
            if "fps_unlock" in request.recipe.packs.to_py():
                progressed(progress.record("pack", "Applying fps_unlock", 4, 5))
                azurkit_fault({DEEP})
            raise RuntimeError("no build here")
{build}""")


def test_a_call_whose_engine_traps_or_raises_names_its_call_and_pythons_place_and_the_engine_starts_again(
        browser, site, usa_iso, europe_iso):
    """Step 4.4ci44: a page of CI's WebKit stopped saying only "access to a null reference (evaluating
    '__pyproxy_apply(t,e,n,o,s)')", a trap of the engine's wasm. A call whose engine's wasm traps names the call, the
    Python frames it was in (Pyodide's dump of them: no message of the error holds them), innermost first, and the wasm
    functions; so does every later ask of that engine (an image's check, whose failure the worker doesn't post, traps
    before the pick's read), never Pyodide's "already fatally failed", nor the image's unmount after a build's trap. A
    trap :data:`DEEP` frames down names its innermost frames, not the dump's last. Each trapped ask is sent to a new
    engine once (D1126), whose trap fails it so by name. A build that raises names its call and its traceback's frames;
    a new engine answers each next ask."""
    status = """(start) => { const s = document.querySelector("#status");
        return s.classList.contains("error") && s.textContent.startsWith(start) && s.textContent; }"""
    frame = r" < <exec> line \d+ \({}\)"
    first = r"Python at ctypes/__init__\.py line \d+ \(string_at\)" + frame.format("azurkit_fault")
    trapped = {"prime": first + frame.format("engine") + frame.format("answering"),
               "build": first + frame.format("azurkit_fault") * 2}
    served = Site(browser, site)
    try:
        worker = _faults((site / "worker.mjs").read_text(encoding="utf-8"), usa_iso.name)
        served.context.route("**/worker.mjs", lambda route: route.fulfill(body=worker, content_type="text/javascript"))
        page = served.open()
        for image, call, packs in ((europe_iso, "prime", None), (usa_iso, "build", ["fps_unlock"])):
            _page.pick(page, "#iso", image)
            if packs:
                _page.build(page, packs)
            head = f"The engine's WebAssembly failed in its {call} call: "
            got, python, wasm = _page.until(page, f"() => ({status})({head!r})").split(" · ")
            assert "fatally" not in got and re.fullmatch(trapped[call], python), (got, python)
            assert re.fullmatch(r"wasm functions \d+(, \d+){0,3}", wasm), wasm
            _page.until(page, "() => azurkit.ready", 300)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.build(page, [])
        raised = _page.until(page, f"() => ({status})('RuntimeError')").split(" · ")
        assert raised[:2] == ["RuntimeError: no build here", "in the engine's build call"] and len(raised) == 3, raised
        assert re.fullmatch(r"Python at <exec> line \d+ \(engine\) < <exec> line \d+ \(answering\)", raised[2]), raised
    finally:
        served.close()


def _rest_faults(worker: str) -> str:
    """worker.mjs whose image's rest (its whole layout, which vouched() has the engine walk after the pick's read, a
    call whose failure no ask posts) traps the engine's wasm as :func:`_faults`' do, in every browser (VOUCHING: Firefox
    hashes no rest)."""
    vouching = "const VOUCHING = /AppleWebKit/.test(navigator.userAgent)"
    layout = '            if request.type == "layout":'
    assert worker.count(vouching) == worker.count(layout) == 1
    trap = f"""{layout.replace(":", ' and getattr(request, "whole", False):')}
                import ctypes
                ctypes.string_at(0xFFFFFFF0, 64)
"""
    return worker.replace(vouching, "const VOUCHING = true").replace(layout, trap + layout)


TRAPPED_ROWS = """
    const { TRAPS } = await import("/workers.mjs");
    const trap = (message) => ({ type: "failed", message, trapped: true });
    {   // F's build traps: F goes at once, and idle B takes its place and is sent the build again, which it builds
        const heard = [];
        const { pool, f, b } = make({ restarted: (data, redo) => heard.push([data.message, redo]) });
        const built = pool.ask(build("t"), { heavy: true });
        f.say(trap("trap 1"));
        b.say({ type: "built", report: { size: 1 }, heap: 2 ** 25 });
        out.redone = [f.stopped, b.tags(), (await built).report, heard, pool.state().promoted];
    }
    {   // the job sent again traps too: it fails by name, sent no third time (no B: a new F loads each time)
        const heard = [];
        const { pool, stubs } = make({ cores: 2, restarted: (data, redo) => heard.push([data.message, redo]) });
        const built = pool.ask(build("u"), { heavy: true });
        stubs[0].say(trap("trap 1"));
        stubs[1].say({ type: "ready", n: 2 });
        stubs[1].say(trap("trap 2"));
        out.twice = [stubs[1].tags(), await built, heard, stubs.length];
    }
    {   // B's own job ahead traps: B goes, its key isn't tried again while listed, and a click asks F
        const heard = [];
        const { pool, stubs, f, b } = make({ restarted: (data, redo) => heard.push([data.message, redo]) });
        pool.want([{ key: "build v", message: build("v"), heavy: true }]);
        b.say(trap("trap b"));
        stubs[2].say({ type: "ready", n: 3 });
        const asked = pool.ask(build("v"), { key: "build v", heavy: true });
        f.say({ type: "built", report: { size: 2 }, heap: 2 ** 25 });
        out.ahead = [b.stopped, stubs[2].tags(), f.tags(), (await asked).report, heard];
    }
    {   // an idle F that traps (a shared warm-up's) is replaced, nothing sent again, TRAPS times a visit; then a trap
        // is any failure: told, its F kept
        const heard = [], told = [];
        const { stubs } = make({ cores: 2, restarted: (data, redo) => heard.push([data.message, redo]),
                                 told: (data, role) => told.push([data.message, role]) });
        for (let n = 1; n <= TRAPS + 1; n++) {
            if (n > 1) stubs.at(-1).say({ type: "ready", n });
            stubs.at(-1).say(trap(`trap ${n}`));
        }
        await null;
        out.idle = [TRAPS, heard, told, stubs.map((stub) => stub.stopped)];
    }
"""
"""The pool's restart of a worker whose engine trapped (workers.mjs's ``restart()``), on stub workers (each a scenario
of :func:`test_a_trapped_engine_is_started_again_and_the_pages_ask_sent_again_once_saying_so`)."""

TWO_CORES = "Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 2 });"
"""The page says it has 2 cores, so workers.mjs starts no B (:data:`FOUR_CORES` is the prototype's: this is the
navigator's own)."""


def test_a_trapped_engine_is_started_again_and_the_pages_ask_sent_again_once_saying_so(browser, site, usa_iso):
    """D1126: the cause of the arm64 WebKit golden's trap ("access to a null reference", Step 4.4ci44) isn't found, so
    the page recovers from such a trap. A worker whose engine trapped is replaced at once; the page's job it ran is sent
    to the next engine once (a second trap fails it by name), and the page says so; B's own job ahead is dropped, its
    key not tried again while listed; a trap with no job (a shared warm-up's) restarts it too, :data:`TRAPS` a visit,
    past which a trap is any failure. On the page, whose first engine's rest traps (:func:`_rest_faults`), its next
    :func:`_faults` and the rest plain: the shared warm-up's numpy load says the rest's trap, never Pyodide's "already
    fatally failed", and its engine starts again; a build whose engine traps ends built, said "The engine stopped and
    started again: building again" meanwhile, its bar then Building's own line, not the trapped attempt's last stage,
    and the page keeps where each trap was (``azurkit.recovered``)."""
    assert _on_stubs(browser, TRAPPED_ROWS) == {
        "redone": [True, ["build t"], {"size": 1}, [["trap 1", "build"]], 1],
        "twice": [["build u"], {"type": "failed", "message": "trap 2", "trapped": True}, [["trap 1", "build"]], 3],
        "ahead": [True, [], ["build v"], {"size": 2}, [["trap b", None]]],
        "idle": [3, [["trap 1", None], ["trap 2", None], ["trap 3", None]], [["trap 4", "f"]],
                 [True, True, True, False]],
    }
    served = Site(browser, site)
    try:
        plain = (site / "worker.mjs").read_text(encoding="utf-8")
        bodies = [_faults(plain, usa_iso.name), _rest_faults(plain)]   # each worker's, popped
        served.context.route("**/worker.mjs", lambda route: route.fulfill(body=bodies.pop() if bodies else plain,
                                                                          content_type="text/javascript",
                                                                          headers={"cache-control": "no-store"}))
        served.context.add_init_script(TWO_CORES)
        page = served.open()
        page.evaluate("""() => { const s = document.querySelector("#status");
            const line = document.querySelector("#progress-line");
            window.said = [];
            new MutationObserver(() => {   // a microtask after restarted(): the bar it left
                said.push(s.textContent);
                if (s.textContent.startsWith("The engine stopped")) window.bar = line.textContent;
            }).observe(s, { childList: true, subtree: true }); }""")
        _page.pick(page, "#iso", usa_iso)
        rest = _page.until(page, "() => azurkit.recovered[0]", 300)
        assert rest.startswith("The engine's WebAssembly failed in its layout call: ") and "fatally" not in rest, rest
        _page.build(page, ["fps_unlock"])
        _page.built(page)
        frame = r" < <exec> line \d+ \(azurkit_fault\)"
        trapped = (r"The engine's WebAssembly failed in its build call: [^·]+ · Python at ctypes/__init__\.py line \d+"
                   rf" \(string_at\){frame * 3} · wasm functions \d+(, \d+){{0,3}}")
        recovered, said, bar = page.evaluate("() => [azurkit.recovered, said, window.bar]")
        assert len(recovered) == 2 and re.fullmatch(trapped, recovered[1]), recovered
        assert "The engine stopped and started again: building again" in said and not bodies, said
        assert bar == "Building…", bar
    finally:
        served.close()


def _trapping(worker: str, call: str) -> str:
    """worker.mjs whose engine's ``call`` traps its wasm as :func:`_faults`' do, before any of its work."""
    catalog = '    if request.type == "catalog":'
    assert worker.count(catalog) == 1
    return worker.replace(catalog, f"""    if request.type == {call!r}:
        import ctypes
        ctypes.string_at(0xFFFFFFF0, 64)
{catalog}""")


def test_a_tabs_ask_whose_engine_traps_starts_the_engine_again_and_is_answered(browser, site):
    """D1126: an ask of the Characters, Tools, Tracker or Data tab answers its failure as a refusal, but a trapped
    engine's failure is no refusal (it left that engine dead, each later ask refused with the trap's text until a
    build): its engine starts again and the ask is sent to the next engine once, the page saying so, as a build's is.
    On a page (no B) whose first engine traps in the Characters tab's list (pickers) and its next in Track this seed's
    plan (plan), both are answered."""
    served = Site(browser, site)
    try:
        plain = (site / "worker.mjs").read_text(encoding="utf-8")
        bodies = [_trapping(plain, "plan"), _trapping(plain, "pickers")]   # each worker's, popped
        served.context.route("**/worker.mjs", lambda route: route.fulfill(body=bodies.pop() if bodies else plain,
                                                                          content_type="text/javascript",
                                                                          headers={"cache-control": "no-store"}))
        served.context.add_init_script(TWO_CORES)
        page = served.open()
        page.evaluate("""() => { const s = document.querySelector("#status");
            window.said = [];
            new MutationObserver(() => said.push(s.textContent)).observe(s, { childList: true, subtree: true });
            (async () => {
                const pickers = await azurkit.engine.call("pickers", { given: { iso: null } });
                const plan = await azurkit.engine.call("plan", { recipe: { seed: "azurkit" } });
                window.answered = [pickers.refused ?? "community" in pickers, plan.refused ?? plan.plan.seed];
            })(); }""")
        assert _page.until(page, "() => window.answered", 600) == [True, "azurkit"]
        recovered, said = page.evaluate("() => [azurkit.recovered, said]")
        assert [line.split(": ")[0] for line in recovered] == [f"The engine's WebAssembly failed in its {call} call"
                                                               for call in ("pickers", "plan")], recovered
        assert {"The engine stopped and started again: reading the models again",
                "The engine stopped and started again: planning the seed again"} <= set(said) and not bodies, said
    finally:
        served.close()


def test_an_engines_numpy_load_in_webkit_waits_on_no_async_wasm_instantiate(browser, site):
    """Step 4.5k: numpy's load (Pyodide's loadPackage) instantiates its 13 shared libraries with WebAssembly.instantiate,
    whose promise WebKit's worker bug 208368 (GTK) can leave unsettled for good (CI's Linux WebKit engine sat at numpy
    120 s and 596 s). In WebKit the worker's own instantiate settles by itself: with the browser's never settling there,
    the Characters tab's list (pickers, which loads numpy) is answered; elsewhere the browser's own instantiates them."""
    webkit = browser.browser_type.name == "webkit"
    served = Site(browser, site)
    try:
        own = ("const own = WebAssembly.instantiate;\nself.instantiated = 0;\nWebAssembly.instantiate = (...args) => { "
               f"self.instantiated += 1; return {'new Promise(() => {})' if webkit else 'own.apply(WebAssembly, args)'}; }};\n")
        body = own + (site / "worker.mjs").read_text(encoding="utf-8")
        served.context.route("**/worker.mjs", lambda route: route.fulfill(body=body, content_type="text/javascript",
                                                                          headers={"cache-control": "no-store"}))
        served.context.add_init_script(TWO_CORES)
        page = served.open()
        page.evaluate("""() => azurkit.engine.call("pickers", { given: { iso: null } })
            .then((pickers) => { window.answered = [pickers.refused ?? "community" in pickers]; })""")
        assert _page.until(page, "() => window.answered", 120) == [True]
        engines = [w for w in page.workers if w.evaluate("() => 'instantiated' in self")]
        assert [w.evaluate("() => self.instantiated") > 0 for w in engines] == [not webkit]
    finally:
        served.close()


def test_a_saves_check_keeps_its_bar_through_a_later_build_cancelled_and_the_engine_ready_again(browser, site, usa_iso):
    """D980, D1053: the check of a Save runs on past what ends a build's bar: a Build cancelled during it, and the new
    worker's ready (a Save at once after a build a big heap retires its worker meets the same on a slower disk)."""
    served = Site(browser, site)
    try:
        hasher = (site / "hasher.mjs").read_text(encoding="utf-8")
        read = "await source.slice(run.start, run.end).arrayBuffer()"
        assert hasher.count(read) == 1
        slow = hasher.replace(read, f"await new Promise((late) => setTimeout(late, 2000)).then(() => {read.removeprefix('await ')})")
        served.context.route("**/hasher.mjs", lambda route: route.fulfill(body=slow, content_type="text/javascript"))
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.build(page, [])
        _page.built(page)
        _page.until(page, "() => azurkit.ready", 300)
        with page.expect_download(timeout=600_000) as caught:   # every file hashed, as on a page that hashed none
            page.evaluate("() => { azurkit.vouched.clear(); document.querySelector('#save').click(); }")
        page.evaluate("() => document.querySelector('#build').click()")
        _page.click(page, "cancel")
        _page.until(page, "() => azurkit.ready", 300)
        assert page.evaluate("() => [azurkit.saveCheck, document.getElementById('progress-row').hidden, "
                             "document.getElementById('progress-line').textContent.startsWith('Saving')]") == [
            "running", False, True]
        assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
        caught.value.delete()
    finally:
        served.close()


SEEDED = "randomize-full:seed=2,default"   # G3's seed case: the packs on by default and seed 2's plan (D144's defaults)
# The Randomizer tab: [Randomize ticked, the seed, whether each of its settings' fields is disabled] (the rows that stay
# vanilla in v1 and the spoiler's buttons aside)
TAB = """() => [document.getElementById("rando-on").checked, document.getElementById("rando-seed").value,
    [...document.querySelectorAll("#rando-settings :is(input, select, button)")].filter((f) => !f.id.startsWith("spoiler")
        && f.id !== "rando-on" && !f.dataset.vanilla).map((f) => f.disabled)]"""


@functools.cache
def _seeded(path: Path) -> tuple[dict, list]:
    """CPython's report and segments of G3's seed case, as the tab sends it."""
    packs = {name: {} for name, pack in mods.PACKS.items() if pack.default_on}
    made, report = sdk.image({"iso": str(path), "packs": packs,
                              "randomizer": {"seed": "2", "settings": sdk.catalog()["randomizer"]["defaults"]}})
    return report, _signature(made)


def test_a_seed_built_from_the_randomizer_tab_is_modkits_and_its_link_spoiler_and_setup_carry_it(browser, site, usa_iso):
    """Step 4.2c1 (RANDOMIZER_PLAN §5.5): the Randomizer tab shows after
    Patches (D901, D902), at D144's defaults (Modkit's share string of them)
    with its settings locked until Randomize is ticked (D907). Ticked, with
    seed 2 and the packs on by default, Build makes G3's seed case file by
    file with its logic verified, CPython's report and segments, its
    spoiler left out; the spoiler the worker sends after it, which View
    shows and Save downloads, is the build's (Modkit's ``--spoiler`` file,
    test_randomizer's). Copy link carries the
    randomizer: a page opened with it holds Randomize ticked, the seed and
    the settings, and copies back the same link; a randomized build's
    recipe (Load its recipe) ticks it again with its seed and the settings
    of its share string. With Remember settings ticked the page remembers
    the tab (D915, D1156) until Reset to defaults unticks it. No CSP
    violation, no request but GETs of the site's files."""
    defaults = sdk.catalog()["randomizer"]["defaults"]
    report, segments = _seeded(usa_iso)
    golden = record_goldens.recorded("pipelines.json")[SEEDED]
    served = Site(browser, site)
    try:
        page = served.open()
        assert page.evaluate("() => [...document.querySelectorAll('#tabs [role=tab]')].map((t) => t.textContent)") == [
            "Patches", "Randomizer", "Characters", "Data", "Tools", "About"]
        _page.click(page, "tab-randomizer")
        view = _page.until(page, "() => azurkit.rando.view")
        assert view == sdk.randomizer_settings({"settings": defaults, "packs": mods.normalize(
            {name: {} for name, pack in mods.PACKS.items() if pack.default_on})})
        assert page.evaluate("() => document.getElementById('rando-share').value") == view["share"] == "AZR-AAEA"
        on, seed, locked = page.evaluate(TAB)
        assert (on, bool(seed), set(locked)) == (False, True, {True})
        _page.click(page, "rando-on")
        _page.fill(page, "rando-seed", "2")
        assert set(page.evaluate(TAB)[2]) == {False}
        _page.pick(page, "#iso", usa_iso)
        page.evaluate("() => document.querySelector('#build').click()")
        built = _built(page)
        assert built["report"]["result"] == {f: s for f, s in golden.items() if f != "ISO"}
        assert (built["report"], built["segments"]) == ({k: v for k, v in report.items() if k != "spoiler"}, segments)
        assert built["report"]["randomizer"]["logic_verified"] is True
        assert page.evaluate("() => azurkit.build.late") == 0   # its reads ahead: no read of its own, each 200 ms in Safari
        _page.click(page, "spoiler-view")
        assert _page.until(page, "() => !document.getElementById('spoiler').hidden "
                                 "&& document.getElementById('spoiler').textContent", 120) == report["spoiler"]
        with page.expect_download(timeout=60_000) as caught:
            _page.click(page, "spoiler-save")
        assert (caught.value.suggested_filename, Path(caught.value.path()).read_text(encoding="utf-8")) == (
            _page.saved_name(browser, f"{usa_iso.stem} (AzurKit) spoiler.txt"), report["spoiler"])
        caught.value.delete()

        _page.until(page, "() => azurkit.ready", 120)   # the site's engine, replaced after the build
        _page.click(page, "remember")
        _page.click(page, "share")
        link = _page.until(page, "() => azurkit.link")
        recipe = {"packs": page.evaluate("() => azurkit.sent"), "randomizer": {"seed": "2", "settings": defaults}}
        assert link == f"{served.origin}/{sdk.preset_encode(recipe, report)}"
        loaded = served.context.new_page()
        _page.load(loaded, link)
        _page.until(loaded, "() => globalThis.azurkit?.loaded && !azurkit.rando.load && azurkit.rando.view")
        assert loaded.evaluate(TAB)[:2] == [True, "2"]
        assert loaded.evaluate("() => document.querySelector('#randomizer .on .mark').textContent") == "●"
        _page.click(loaded, "share")
        assert _page.until(loaded, "() => azurkit.link") == f"{served.origin}/{sdk.preset_encode(recipe)}"
        _page.click(loaded, "reset")
        _page.fill(loaded, "rando-seed", "x")
        opened = {"format": "azurkit-preset", "schema_version": 1, "layers": [   # a randomized build's (sdk.open_build)
            {"tool": "randomizer", "kind": "plan", "recipe": {"seed": "2", "share": report["randomizer"]["share"]}},
            {"tool": "mods", "kind": "packs", "recipe": recipe["packs"]}]}
        loaded.evaluate("(preset) => { azurkit.opened = preset; document.getElementById('load-build').click(); }", opened)
        _page.until(loaded, "() => document.getElementById('rando-on').checked && azurkit.rando.view && !azurkit.rando.load")
        assert [*loaded.evaluate(TAB)[:2], loaded.evaluate(STATUS)] == [True, "2", (
            f"Loaded your build's recipe: {len(recipe['packs'])} packs and the randomizer (seed 2), marked ●. "
            "Pick your vanilla image, then Build.")]

        setup = {"on": True, "seed": "2", "settings": defaults}
        _remembered(page, {"ticked": [name for name in mods.PACKS if name in recipe["packs"]], "values": {}, "xbr": [],
                           "randomizer": setup})
        page.evaluate("() => history.replaceState(null, '', location.pathname)")   # Copy link's #p= would win
        _reload(page)
        assert page.evaluate(TAB)[:2] == [True, "2"]
        _page.click(page, "reset")
        assert page.evaluate(TAB)[:2] == [False, "2"]
        _remembered(page, None)
        for each in (page, loaded):
            _page.check_csp(each)
        assert served.stray() == []
    finally:
        served.close()


def test_a_europe_seed_is_built_on_the_site_with_no_read_of_its_own(browser, site, europe_iso):
    """Europe's seed asks more pages ahead than USA's (147 to 95): the worker's cache holds them all, so none is read
    one by one (200 ms each in Safari)."""
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", europe_iso)
        _page.click(page, "tab-randomizer")
        _page.until(page, "() => azurkit.rando.view")
        _page.click(page, "rando-on")
        _page.fill(page, "rando-seed", "2")
        page.evaluate("() => document.querySelector('#build').click()")
        assert _page.built(page)["randomizer"]["logic_verified"] is True
        assert page.evaluate("() => azurkit.build.late") == 0
    finally:
        served.close()


def test_a_seed_wearing_a_character_builds_on_the_site_as_cpython_builds_it(browser, site, usa_iso):
    """A link with seed azurkit, keylord and the packs on by default, built on the page: CPython's report and
    segments (its spoiler left out, as the site's build leaves it), inside the worker's 4 GiB (AZ-831: the swap held
    the seed's levels three times over, MemoryError), its bytes past the heap's first 2 GiB handed over as they are
    (AZ-832: they came out as other bytes)."""
    recipe = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
              "randomizer": {"seed": "azurkit", "settings": sdk.catalog()["randomizer"]["defaults"]},
              "character": {"species": "keylord"}}
    made, report = sdk.image(recipe | {"iso": str(usa_iso)}, spoiler=False)
    served = Site(browser, site)
    try:
        page = served.context.new_page()
        _page.load(page, f"{served.origin}/{sdk.preset_encode(recipe)}")
        _page.until(page, "() => globalThis.azurkit?.loaded && !azurkit.rando.load && azurkit.rando.view", 120)
        _page.pick(page, "#iso", usa_iso)
        page.evaluate("() => document.querySelector('#build').click()")
        built = _built(page)
        assert built == _as_cpython(built, report, made)
    finally:
        served.close()


def test_a_weapon_a_body_lifts_off_the_floor_builds_on_the_site_as_cpython_builds_it(browser, site, usa_iso):
    """keylord with the Farmer's hoe and the packs on by default, built on the page: CPython's report and segments
    (AZ-830: the hoe's floor lift turned sin and cos 1 ulp apart, macOS's libm against Pyodide's, into other
    animation words; every libm call a swap makes is ``core/fdlibm.py``'s now)."""
    recipe = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
              "character": {"species": "keylord", "weapon": "farmers_hoe"}}
    made, report = sdk.image(recipe | {"iso": str(usa_iso)})
    served = Site(browser, site)
    try:
        page = served.context.new_page()
        _page.load(page, f"{served.origin}/{sdk.preset_encode(recipe)}")
        _page.until(page, "() => globalThis.azurkit?.loaded", 120)
        _page.pick(page, "#iso", usa_iso)
        _page.click(page, "build")
        built = _built(page)
        assert built == _as_cpython(built, report, made)
    finally:
        served.close()


# The tab's rows that stay vanilla in v1 ([ticked, greyed] each); "vanilla 10" beside its box ([right of it, on its
# line]); the skip list, opened: its rows and whether it shows them all (no inner scroll).
RANDO_SHOWN = """() => {
    document.getElementById("rando-skip-list").open = true;
    const box = document.getElementById("rando-cost").getBoundingClientRect(), skips = document.getElementById("rando-skips");
    const note = document.getElementById("rando-cost-note").getBoundingClientRect();
    return [[...document.querySelectorAll("#rando-items input[data-vanilla]")].map((b) => [b.checked, b.disabled]),
            [note.left >= box.right, note.top < box.bottom && note.bottom > box.top],
            [skips.querySelectorAll(".skip").length, skips.scrollHeight <= skips.clientHeight]];
}"""
SKIP_COUNT = "() => document.querySelector('#rando-skip-list summary').textContent"
SETTLED = "() => globalThis.azurkit?.ready && !azurkit.rando.load && !azurkit.rando.waiting && azurkit.rando.view"
WARNED = "() => document.getElementById('rando-warn').textContent.split('\\n')"


def test_the_randomizer_tab_reads_as_set_warns_of_a_shares_sliders_and_loads_a_link_holding_only_a_seed(
        browser, site, tmp_path):
    """Step 4.2c1's review and looks: the rows that stay vanilla in v1 show
    greyed and unticked under "ticked: shuffled" (Modkit's are off); at
    1100 px "vanilla 10" stays beside its box and every skip shows; a share
    string made with other movement sliders warns so (AZ-383) after the tab
    reads it with its own, until the Patches tab's sliders give that share
    string (4.2c1's late review); and a link whose randomizer is a seed
    alone loads it at D144's defaults. Step 4.2c2: each item row counts
    what the base game places (Modkit's); a skip group's tick turns on all
    its skips, whatever their rating, its box what's on: unticking one
    leaves it half, "5 of 6", and a click on the half turns them all on again
    (D1061), a tick right after a Skips change by the new ceiling, not the
    last answer's; Load settings… takes a settings file's settings (D144).
    Open a plan… (P31, Modkit's ``randomize-full --plan``) shows a plan
    file's seed and settings, locked but the obsidian cost and Close plan,
    and the page's recipe (Build's, Copy link's) is the plan whole; an edited
    one is refused, naming the file; Close plan unlocks the tab again.
    Step 4.18b: the Save-point warp box starts unticked and mirrors the
    qol_save_warp pack, its tick the pack's and the settings' save_warp,
    the pack's untick its own (D1154, D1155)."""
    on = {name: {} for name, pack in mods.PACKS.items() if pack.default_on}
    other = sdk.randomizer_settings({"settings": sdk.catalog()["randomizer"]["defaults"],
                                     "packs": on | {"player_physics": {"jump_speed_scale": 1.3}}})["share"]
    note = sdk.randomizer_settings({"share": other, "packs": on})["note"]
    kept = sum(not category for category, *_ in sdk.catalog()["randomizer"]["items"])
    served = Site(browser, site, viewport={"width": 1100, "height": 700})
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        view = _page.until(page, SETTLED, 120)
        assert page.evaluate("() => document.getElementById('rando-skip-list').open") is False
        assert page.evaluate(SKIP_COUNT) == f"Specific skips · 0 of {len(view['skips'])} on"
        assert page.evaluate(RANDO_SHOWN) == [[[False, True]] * kept, [True, True], [len(view["skips"]), True]]
        page.evaluate("() => { document.getElementById('rando-skip-list').open = false; }")
        _page.click(page, "rando-on")
        page.evaluate("""(text) => { const box = document.getElementById("rando-share");
                                     box.value = text; box.dispatchEvent(new Event("change")); }""", other)
        assert _page.until(page, SETTLED, 120)["share"] == "AZR-AAEA"   # read again with the page's sliders
        assert f"⚠ {note}" in page.evaluate(WARNED)
        _page.click(page, "tab-patches")
        _page.tick(page, [*on, "player_physics"], {"player_physics": {"jump_speed_scale": "1.3"}})
        _page.click(page, "tab-randomizer")
        assert _page.until(page, SETTLED, 120)["share"] == other and f"⚠ {note}" not in page.evaluate(WARNED)
        _page.tick(page, list(on))
        warp = """() => [document.getElementById("rando-warp").checked,
                         document.querySelector("#packs input[data-pack=qol_save_warp]").checked]"""
        assert page.evaluate(warp) == [False, False]   # off by default, Randomize or not (D1155)
        _page.click(page, "rando-warp")
        view = _page.until(page, SETTLED, 120)
        assert page.evaluate(warp) == [True, True] and view["settings"]["save_warp"] is True
        assert view["share"] == sdk.randomizer_settings({"settings": view["settings"], "packs": mods.normalize(
            on | {"qol_save_warp": {}})})["share"] != "AZR-AAEA"
        _page.click(page, "tab-patches")
        _page.tick(page, list(on))
        _page.click(page, "tab-randomizer")
        assert "save_warp" not in _page.until(page, SETTLED, 120)["settings"] and page.evaluate(warp) == [False, False]

        assert page.evaluate("() => [...document.querySelectorAll('#rando-items .count')].map((c) => c.textContent)") == [
            f"{row[3]:,}" for row in sdk.catalog()["randomizer"]["items"]]
        defaults = sdk.catalog()["randomizer"]["defaults"]

        def tick(group):
            page.evaluate("(group) => document.querySelector(`#rando-groups input[data-group=${group}]`).click()", group)
            return _page.until(page, SETTLED, 120)

        def box(group):
            return page.evaluate("""(group) => { const box = document.querySelector(`#rando-groups input[data-group=${group}]`);
                return [box.checked, box.indeterminate, box.parentElement.querySelector(".note").textContent]; }""", group)

        view = tick("dark")   # Standard's movement: Hard's e7 too, and what's on is what's asked
        assert view["settings"] == defaults | {"skip_override": {"e7.dark_room_nolight": True, "w1.dark_cave_nolight": True}}
        assert box("dark") == [True, False, "2 of 2 · up to Hard"]
        opened = "() => document.getElementById('rando-skip-list').open"
        assert page.evaluate(opened) is True and page.evaluate(SKIP_COUNT) == f"Specific skips · 2 of {len(view['skips'])} on"
        page.evaluate("() => { document.getElementById('rando-skip-list').open = false; }")
        tick("dark")
        assert page.evaluate(opened) is False   # an untick leaves it shut
        view = tick("storage")
        storage = {p["id"] for g in view["groups"] if g["id"] == "storage" for p in g["picks"]}
        assert len(storage) == 6 and view["settings"] == defaults | {"skip_override": dict.fromkeys(sorted(storage), True)}
        assert view["share"] == sdk.randomizer_settings({"settings": view["settings"], "packs": mods.normalize(on)})["share"]
        assert box("storage") == [True, False, "6 of 6 · up to Standard"] and box("dark")[:2] == [False, False]
        one = min(storage)
        page.evaluate("(id) => document.querySelector(`#rando-skips input[data-skip='${id}']`).click()", one)
        view = _page.until(page, SETTLED, 120)
        assert view["settings"]["skip_override"] == dict.fromkeys(sorted(storage - {one}), True)
        assert box("storage") == [False, True, "5 of 6 · up to Standard"]
        assert tick("storage")["settings"]["skip_override"] == dict.fromkeys(sorted(storage), True)
        assert box("storage")[:2] == [True, False]
        page.evaluate("""() => { const ceiling = document.getElementById("rando-ceiling");
            ceiling.value = "2"; ceiling.dispatchEvent(new Event("change"));
            document.querySelector("#rando-groups input[data-group=storage]").click(); }""")   # before the engine answers
        assert _page.until(page, SETTLED, 120)["settings"] == defaults | {
            "skip_ceiling": 2, "skip_override": dict.fromkeys(sorted(storage), False)}   # Standard's ceiling has them on
        given = defaults | {"skip_ceiling": 3, "movement_tier": "hard", "exclude_categories": ["gems"]}
        (tmp_path / "settings.toml").write_text(sdk.randomizer_settings({"settings": given})["file"], encoding="utf-8")
        _page.pick(page, "#rando-load", tmp_path / "settings.toml")
        _page.until(page, "() => !azurkit.rando.load && document.getElementById('rando-ceiling').value === '3'", 120)
        assert _page.until(page, SETTLED, 120)["settings"] == given
        assert box("storage") == [True, False, "6 of 6 · up to Standard"]   # a loaded setting's groups show
        doc = sdk.plan({"seed": "5", "settings": given})
        (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
        (tmp_path / "edited.json").write_text(json.dumps(doc | {"seed": "6"}), encoding="utf-8")
        _page.pick(page, "#rando-plan", tmp_path / "plan.json")
        opened = _page.until(page, "() => azurkit.rando.plan && !azurkit.rando.load && !azurkit.rando.waiting "
                                   "&& azurkit.rando.view", 120)
        enabled = page.evaluate("""() => [...document.querySelectorAll('#rando-settings :is(input, select, button)')]
            .filter((f) => !f.disabled && !f.dataset.vanilla).map((f) => f.id)""")
        assert (opened["settings"], page.evaluate(TAB)[1], sorted(enabled)) == (given, "5", [
            f"rando-{id_}" for id_ in sorted(("copy", "cost", "filter", "on", "plan", "plan-close", "save"))])
        assert page.evaluate("() => document.getElementById('rando-plan-name').textContent") == (
            f"Building a plan file as it is (plan.json: seed 5, plan {doc['sha256'][:12]}): its seed and settings "
            "are locked.")
        _page.click(page, "share")
        assert _page.until(page, "() => azurkit.link") == (
            f"{served.origin}/{sdk.preset_encode({'packs': mods.normalize(on), 'randomizer': {'plan': doc}})}")
        _page.pick(page, "#rando-plan", tmp_path / "edited.json")
        assert _page.until(page, "() => !azurkit.rando.load && document.getElementById('rando-warn').textContent") == (
            "⚠ edited.json: its sha256 doesn't match its content (an edited plan)")
        _page.click(page, "rando-plan-close")
        assert _page.until(page, SETTLED, 120)["settings"] == given
        assert page.evaluate("() => [azurkit.rando.plan, document.getElementById('rando-plan-line').hidden]") == [
            None, True] and set(page.evaluate(TAB)[2]) == {False}

        packs = mods.normalize(on)
        loaded = served.context.new_page()
        _page.load(loaded, f"{served.origin}/{sdk.preset_encode({'packs': packs, 'randomizer': {'seed': '7'}})}")
        assert _page.until(loaded, SETTLED, 120)["share"] == "AZR-AAEA"
        assert loaded.evaluate(TAB)[:2] == [True, "7"]
        assert loaded.evaluate(STATUS).endswith(f": {len(packs)} packs and the randomizer (seed 7), marked ●. "
                                                "Pick your vanilla image, then Build.")
        for each in (page, loaded):
            _page.check_csp(each)
        assert served.stray() == []
    finally:
        served.close()


# The Seed difficulty select as it reads: its level, each option's [value, name, enabled, line], the line under it.
LEVELS = """() => { const s = document.getElementById("rando-difficulty");
    return [s.value, [...s.options].map((o) => [o.value, o.textContent, !o.disabled, o.title]),
            document.getElementById("rando-difficulty-line").textContent]; }"""


def test_seed_difficulty_offers_every_level_at_any_settings_loads_v1_levels_at_the_nearest_and_the_tracker_shows_the_line(
        browser, site, tmp_path):
    """Step 4.20 (D1157): the tab offers Easy, Normal, Hard and Expert at
    any settings, Normal first selected, each option's line the engine's
    and the chosen level's under the select; a level chosen rides the share
    string, and a share string's level sets the select both ways; a v1.0.0
    level loads at the nearest one and the warning line says so; the
    tracker's line under the head is the engine's measured line, the tricks
    named only with Spoiler on."""
    on = mods.normalize({name: {} for name, pack in mods.PACKS.items() if pack.default_on})
    defaults = sdk.catalog()["randomizer"]["defaults"]

    def table(tier, ceiling, level="Normal", **rest):
        return defaults | {"movement_tier": tier, "skip_ceiling": ceiling, **rest} \
            | ({"seed_difficulty": level} if level != "Normal" else {})

    def engine(*args, **rest):
        return sdk.randomizer_settings({"settings": table(*args, **rest), "packs": on})

    def choose(**fields):
        page.evaluate("""(fields) => { for (const [id, value] of Object.entries(fields)) {
            const box = document.getElementById(`rando-${id}`);
            box.value = String(value);
            box.dispatchEvent(new Event("change")); } }""", fields)
        return _page.until(page, SETTLED, 120)

    def typed(share, level):
        page.evaluate("""(text) => { const box = document.getElementById("rando-share");
                                     box.value = text; box.dispatchEvent(new Event("change")); }""", share)
        _page.until(page, f"() => !azurkit.rando.load && document.getElementById('rando-difficulty').value === '{level}'", 120)
        return _page.until(page, SETTLED, 120)

    served = Site(browser, site)
    served.context.route(f"{served.origin}/art/**", lambda route: route.fulfill(status=404, body=""))
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.until(page, SETTLED, 120)
        _page.click(page, "rando-on")
        for tier, ceiling in (("hard", 3), ("standard", 0), ("safe", 0)):
            choose(movement=tier, ceiling=ceiling)
            level, levels, line = page.evaluate(LEVELS)
            answer = engine(tier, ceiling)["difficulty"]["levels"]
            assert level == "Normal" and levels == answer and [row[0] for row in levels] == [
                "Easy", "Normal", "Hard", "Expert"] and all(row[2] for row in levels)
            assert line == answer[1][3]
        view = choose(difficulty="Expert")   # at Safe movement and no skip too
        assert view["share"] == engine("safe", 0, "Expert")["share"] and view["settings"]["seed_difficulty"] == "Expert"
        assert page.evaluate(LEVELS)[2] == engine("safe", 0, "Expert")["difficulty"]["levels"][3][3]
        assert "seed_difficulty" not in choose(difficulty="Normal")["settings"]

        share = engine("hard", 3, "Easy")["share"]
        view = typed(share, "Easy")
        assert view["share"] == share and view["settings"]["seed_difficulty"] == "Easy"
        assert page.evaluate("() => document.getElementById('rando-movement').value") == "hard"
        older = "AZR-" + base64.b32encode(bytes([4, 0x13, 0, 0, 1 << 3 | 4])).decode().rstrip("=")   # v1's Frame-perfect
        view = typed(older, "Expert")
        assert view["settings"]["seed_difficulty"] == "Expert" and view["share"] == engine("hard", 3, "Expert")["share"]
        assert any(line.startswith("⚠ Made with the older Seed difficulty Frame-perfect: it loads as Expert")
                   for line in page.evaluate(WARNED))

        doc = sdk.plan({"seed": "page", "settings": table("hard", 3, "Expert")})   # a plan no other test tracks
        (tmp_path / "shaped.json").write_text(json.dumps(doc), encoding="utf-8")
        _page.click(page, "rando-view-tracker")
        assert page.evaluate("() => document.getElementById('track-difficulty').hidden")
        _page.pick(page, "#track-open", tmp_path / "shaped.json")
        _page.until(page, f"() => azurkit.tracker.state.view?.head.sha256 === {json.dumps(doc['sha256'])} && ({TRACKED})()", 300)
        shown = """() => [document.getElementById("track-head").textContent, document.getElementById("track-difficulty").textContent,
                          document.getElementById("track-difficulty").hidden]"""
        head, spoiled = sdk.tracker({"plan": doc})["head"], sdk.tracker({"plan": doc, "spoiler": True})["head"]["difficulty"]
        assert page.evaluate(shown) == [head["text"], head["difficulty"]["text"], False]
        assert "needs tricks at" in head["difficulty"]["text"] and "needs tricks at" not in spoiled["text"]
        _page.click(page, "track-spoiler")
        _page.until(page, f"() => azurkit.tracker.state.view.head.difficulty.needs && ({TRACKED})()", 300)
        assert page.evaluate(shown) == [head["text"], spoiled["text"], False]
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


# Each message the page posts to a worker for an ask of its own, by its type (an init script: before the page's
# own); not its work ahead's (B's jobs, call 0: app.mjs's planning() and viewing(), D1007), which plan the
# Settings view's seed while Randomize is on or the Tracker view is open, ahead of Track this seed's click
ASKED = """(() => {
    const post = Worker.prototype.postMessage;
    globalThis.asked = [];
    Worker.prototype.postMessage = function (message, ...rest) {
        if (message?.call !== 0) globalThis.asked.push(message?.type);
        return post.call(this, message, ...rest);
    };
})();"""
WORLD_SHOWN = """() => [azurkit.tracker.state.view, azurkit.tracker.map.level,
    [...document.getElementById("track-body").children].filter((n) => !n.hidden).map((n) => n.id),
    document.getElementById("track-empty").hidden, azurkit.tracker.map.pictures.map((p) => [p.name, p.bitmap.width,
    p.bitmap.height]), asked.filter((t) => ["tracker", "plan", "art", "art_world"].includes(t))]"""


def _png_size(png: bytes) -> list[int]:
    return [int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")]


def test_the_site_shows_the_trackers_shipped_maps_and_with_no_plan_each_levels_vanilla_spots(browser, site, tmp_path):
    """Step 4.3f (D961): the Tracker view shows Modkit's world map, every
    level's picture on it, as soon as it shows, with no image picked and no
    plan tracked: the page reads the pictures the site ships (``art/``,
    which ``tests/test_art.py`` holds to Modkit's pixels and to the
    tracker's drawing) and asks its engine nothing for them. Step 4.4u3:
    with no plan its engine's tracker gives the vanilla game's spots (no
    image picked), and each level picked on Map (the levels by realm as
    the Table groups them) opens its map with each spot ringed plain and
    its vanilla item's icon, a spot's tip naming that item and a click on
    it marking nothing. A plan opened then shows the level browsed with
    the plan's spots, and each floor from the same files. No CSP
    violation, no request but GETs of the site's files. The view's own
    asks are counted (``ASKED``): the work ahead's plan of the Settings
    view's seed, for Track this seed, may come before the world map's
    picture does (Step 4.4ci54: a Windows runner's Firefox)."""
    shipped = site / "art" / tracking.ART_VERSION
    levels = json.loads((shipped / "maps.json").read_text(encoding="utf-8"))["levels"]
    bare = sdk.tracker({})
    served = Site(browser, site)
    served.context.add_init_script(script=ASKED)
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        _page.until(page, "() => Boolean(azurkit.tracker.map.pictures?.[0]?.bitmap)", 60)
        shown, asked = page.evaluate(WORLD_SHOWN)[:-1], page.evaluate(WORLD_SHOWN)[-1]
        assert shown == [None, None, ["track-maps"], False, [["world", *_png_size((shipped / "world.png").read_bytes())]]]
        assert set(asked) <= {"tracker"}   # the vanilla game's spots alone: no picture drawn, nothing planned
        read = [url.removeprefix(f"{served.origin}/") for _, url, _ in served.requests if "/art/" in url]
        assert {url for url in read if "icons" in url} == {"art/icons.css", f"art/{tracking.ART_VERSION}/icons.png"}
        assert [url for url in read if "icons" not in url] == [
            "art/index.json", f"art/{tracking.ART_VERSION}/maps.json", f"art/{tracking.ART_VERSION}/world.png"]
        _page.until(page, "() => !document.getElementById('track-pick').disabled", 300)
        hint = "() => document.getElementById('map-hint').textContent"
        assert page.evaluate(hint) == "Click a level to open its map. Scroll to zoom, drag to pan."
        assert page.evaluate("""() => [...document.getElementById("track-pick").children].map((n) => n.tagName === "OPTGROUP"
            ? [n.label, [...n.children].map((o) => o.value)] : [n.textContent, [n.value]])""") == [
            ["World map", [""]], *bare["levels"]]   # a realm of one level (life, town, the airship) its own row
        for level in [*sorted(levels), "e6"]:
            page.select_option("#track-pick", level)
            _page.until(page, f"() => azurkit.tracker.map.level === '{level}' "
                              "&& azurkit.tracker.map.pictures.every((p) => p.bitmap)", 60)
            at, picked, whole, spots, tips = page.evaluate(BROWSED)
            mine = sorted(loc for loc, s in bare["spots"].items() if s["level"] == level)
            main = {i["id"] for i in levels[level]["items"] + levels[level]["spots"] if i["at"][2] == levels[level]["main"]}
            assert (at, picked, whole, [m["loc"] for m in spots]) == (level, level, True, mine), level
            assert all((m["ring"], m["faint"], m["check"], bool(m["icon"])) == ("vanilla", False, None, True)
                       for m in spots), level
            assert sorted(tips) == sorted([f"{bare['spots'][loc]['name']} · {tracking.SPOT[bare['spots'][loc]['class']]}",
                                           False] for loc in main), level
        assert page.evaluate(hint) == "The vanilla game's items: click an exit to open its level. Scroll to zoom, drag to pan."
        assert page.evaluate("() => azurkit.tracker.state.marks") == {}
        (tmp_path / "plan.json").write_text(json.dumps(_profile("default")), encoding="utf-8")
        _page.pick(page, "#track-open", tmp_path / "plan.json")
        _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running", 300)
        at, _, whole, spots, tips = page.evaluate(BROWSED)
        plan = page.evaluate("() => azurkit.tracker.state.view.spots")
        assert (at, whole, page.evaluate("() => document.getElementById('track-pick-box').hidden")) == ("e6", True, True)
        assert {m["ring"] for m in spots} <= {"near", "skip", "far"} and [m["loc"] for m in spots] == sorted(
            loc for loc, s in plan.items() if s["level"] == "e6") and tips == []
        assert page.evaluate(hint) == "Click a spot to mark it collected, an exit to open its level. Scroll to zoom, drag to pan."
        calls = page.evaluate(_perf.CALLS)["calls"]   # the worker's, in the page for the perf gate's native assert
        assert calls["kernel"] > 0 and calls["twin"] == 0, calls
        assert page.evaluate("() => azurkit.tracker.map.pictures.map((p) => [p.name, p.bitmap.width, p.bitmap.height])"
                             ) == [[name, *_png_size((shipped / f"{name}.png").read_bytes())] for name in levels["e6"]["floors"]]
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


STATUS_SAYS = "() => [document.getElementById('status').textContent, document.getElementById('status').className]"
IMPORTED = "https://example.invalid/imported.css"
OWN = {"import.js": "setTimeout(() => document.head.append(Object.assign(document.createElement('link'), "
                    "{rel: 'stylesheet', href: '/own/import.css'})))",
       "import.css": f'@import url("{IMPORTED}");',
       "style.js": "setTimeout(() => document.head.append(Object.assign(document.createElement('style'), "
                   "{textContent: 'b {}'})))"}
"""Files of the page's origin (a test's routes) whose refusals are the page's own: a stylesheet a script links whose
``@import`` the policy refuses (a load checked off the script's stack: no file named in all three browsers), and a
script that inserts a ``<style>`` the policy refuses (its file named)."""


def test_the_status_line_says_the_pages_own_policy_refusals_and_only_logs_anothers(browser, site):
    """Step 4.4u4: the tracker's view with no seed refuses nothing; a refusal
    of the page's policy that isn't the page's own goes to
    ``azurkit.violations`` only (which ``_page.check_csp`` reads), the status
    line left as it was: a ``<style>`` Playwright's evaluate inserts, as an
    extension's content script does, and in WebKit a screenshot's
    (Playwright's adds ``<style>body {}</style>`` a moment: 4.4u3's WebKit
    shot of that view said "The page's security policy refused
    style-src-elem" in red). The page's own are said in red, a load that
    names no file (its stylesheet's ``@import``) as one that does."""
    served = Site(browser, site)
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        _page.until(page, "() => Boolean(azurkit.tracker.map.pictures?.[0]?.bitmap)", 60)
        _page.check_csp(page)
        page.evaluate("() => document.head.append(Object.assign(document.createElement('style'), {textContent: 'i {}'}))")
        others = 1
        if browser.browser_type.name == "webkit":
            page.screenshot()
            others = 2
        _page.until(page, f"() => azurkit.violations.length === {others}", 10)
        said, kind = page.evaluate(STATUS_SAYS)
        assert "security policy" not in said and "error" not in kind
        assert [v.startswith("page: style-src-elem inline, not the page's (") for v in page.evaluate(
            "() => azurkit.violations")] == [True] * others
        def own(route, request):
            name = request.url.rsplit("/", 1)[1]
            route.fulfill(body=OWN[name], content_type="text/css" if name.endswith(".css") else "text/javascript")

        page.route(f"{served.origin}/own/*", own)
        for n, (script, said) in enumerate([("import.js", IMPORTED), ("style.js", "inline")], others + 1):
            page.evaluate("""(src) => new Promise((done) => document.head.append(Object.assign(
                document.createElement('script'), {src, onload: done})))""", f"{served.origin}/own/{script}")
            _page.until(page, f"() => azurkit.violations.length === {n}", 10)
            assert page.evaluate("() => azurkit.violations.at(-1)") == f"page: style-src-elem {said}"
            assert page.evaluate(STATUS_SAYS) == ["The page's security policy refused style-src-elem", "error"]
    finally:
        served.close()


# The level map shown: its level, floor, whether its detail picture was drawn, and its canvas's colour at points
DETAIL_DRAWN = "() => { const f = azurkit.tracker.map.drawnFor; return [f?.level, f?.floor, f?.detail]; }"
CANVAS_AT = """(points) => { const g = document.getElementById("map-canvas").getContext("2d"), r = devicePixelRatio || 1;
    return points.map(([x, y]) => [...g.getImageData(Math.floor(x * r), Math.floor(y * r), 1, 1).data.slice(0, 3)]); }"""
TOP = "() => { const m = azurkit.tracker.map; m.view(m.top()); }"


def test_a_level_zoomed_past_its_maps_pixels_shows_its_floors_detail_picture(browser, site, tmp_path):
    """Step 4.3l (D988): a coarse level's map (``index.json``'s detail),
    zoomed within a notch of its own pixels, reads its shown floor's detail
    picture the site ships, once, and past them draws it: the canvas holds
    the detail picture's colours where the map's own differ. Nothing reads
    one before (the page's start, the world map, w1 fitted more than a notch
    under its pixels), another floor's replaces it (the one held closed),
    Fit shows the map's own pixels again, and a level with none (airship)
    reads none. No image is picked."""
    from azurkit.tools.randomizer import art

    shipped, v = site / "art" / tracking.ART_VERSION, tracking.ART_VERSION
    factors = json.loads((site / "art" / "index.json").read_text(encoding="utf-8"))["detail"]
    entry = json.loads((shipped / "maps.json").read_text(encoding="utf-8"))["levels"]["w1"]
    main, other = entry["main"], next(k for k in range(len(entry["floors"])) if k != entry["main"])
    assert "w1" in factors and "airship" not in factors
    served = Site(browser, site, viewport={"width": 900, "height": 520})

    def read() -> list[str]:
        return [url.removeprefix(f"{served.origin}/art/{v}/detail/") for _, url, _ in served.requests if "/detail/" in url]
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        (tmp_path / "plan.json").write_text(json.dumps(_profile("default")), encoding="utf-8")
        _page.pick(page, "#track-open", tmp_path / "plan.json")
        _page.until(page, TRACKED, 300)
        page.evaluate("() => azurkit.tracker.map.show('w1', true)")
        _page.until(page, "() => azurkit.tracker.map.pictures.every((p) => p.bitmap)", 60)
        assert page.evaluate("() => azurkit.tracker.map.fitted") * 1.25 <= 1 and read() == []
        page.evaluate("() => document.querySelectorAll('#map-switches input').forEach((b) => b.click())")  # bare
        page.evaluate(TOP)
        _page.until(page, "() => azurkit.tracker.map.drawnFor.detail", 60)
        assert page.evaluate(DETAIL_DRAWN) == ["w1", main, True] and read() == [f"{entry['floors'][main]}.png"]
        x0, y0, s, factor, (cw, ch) = page.evaluate(
            "() => { const m = azurkit.tracker.map; return [...m.at(0, 0), m.s, m.factor(), m.room()]; }")
        finer = art.unpng((shipped / "detail" / f"{entry['floors'][main]}.png").read_bytes())
        own = art.unpng((shipped / f"{entry['floors'][main]}.png").read_bytes())
        points, colours = [], []
        for cy in range(40, ch - 4, 5):   # below the title, each a detail pixel's middle where the map's own differs
            for cx in range(4, cw - 4, 5):
                u, w = (cx + 0.5 - x0) * factor / s, (cy + 0.5 - y0) * factor / s
                if (0.25 < u % 1 < 0.75 and 0.25 < w % 1 < 0.75 and 0 <= w < finer.shape[0] and 0 <= u < finer.shape[1]
                        and (finer[int(w), int(u)] != own[min(int(w / factor), own.shape[0] - 1),
                                                     min(int(u / factor), own.shape[1] - 1)]).any()):
                    points.append([cx, cy])
                    colours.append(finer[int(w), int(u)].tolist())
        assert len(points) > 20 and page.evaluate(CANVAS_AT, points) == colours
        page.evaluate("() => { globalThis.held = azurkit.tracker.map.detail.bitmap; }")
        page.evaluate("(k) => document.querySelector(`#map-floors input[data-floor='${k}']`).click()", other)
        _page.until(page, f"() => azurkit.tracker.map.drawnFor.detail && azurkit.tracker.map.drawnFor.floor === {other}")
        assert read()[1:] == [f"{entry['floors'][other]}.png"] and page.evaluate("() => held.width") == 0
        _page.click(page, "map-fit")
        assert page.evaluate(DETAIL_DRAWN) == ["w1", other, False]
        page.evaluate(TOP)
        assert page.evaluate(DETAIL_DRAWN) == ["w1", other, True] and len(read()) == 2
        page.evaluate("() => azurkit.tracker.map.show('airship', true)")
        _page.until(page, "() => azurkit.tracker.map.pictures.every((p) => p.bitmap)", 60)
        page.evaluate(TOP)
        assert page.evaluate(DETAIL_DRAWN)[::2] == ["airship", False] and len(read()) == 2
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


TRACKED = "() => !azurkit.tracker.state.running && !azurkit.tracker.state.queue.length && azurkit.tracker.state.view"
# The maps' model of the view shown (web/mapview.mjs's marks() for each level and badges(); the icons the engine draws),
# as one canonical JSON text: TRACKER_MAP's
ICONS = icons.names()
MAP_MODEL = """async ([levels, icons]) => {
    const { marks, badges } = await import("./mapview.mjs");
    const view = azurkit.tracker.state.view, have = (name) => icons.includes(name);
    const sorted = (v) => Array.isArray(v) ? v.map(sorted) : v && typeof v === "object"
      ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])])) : v;
    return JSON.stringify(sorted({ levels: Object.fromEntries(levels.map((lv) => [lv, marks(view, lv, have)])),
                                   badges: badges(view) }));
}"""
# The Tracker view as it reads: the counter row, the level shown (null: the world map) and its spot chips' states
SHOWN_TRACKER = """() => [document.getElementById("track-count").textContent, azurkit.tracker.state.level,
    Object.fromEntries([...document.querySelectorAll("#track-level .spot")].map((b) => [b.dataset.loc, b.className]))]"""


def test_the_tracker_gives_modkits_verdicts_and_a_click_on_a_spot_marks_it(browser, site, tmp_path):
    """Step 4.2c2 (D189, D249): the Randomizer tab's Tracker view opens a
    plan file (seed 2's default and max plans) and the engine under
    Pyodide gives Modkit's verdicts at each state (test_randomizer's
    :data:`TRACKER`; Live's kit is the app's, D882), the spoiler off and on,
    and its maps' model (``web/mapview.mjs``: each level's spots' rings,
    icons and checks, its gem dots, the world map's badges) Modkit's map
    verdicts (:data:`TRACKER_MAP`, Step 4.2c3). Where the maps can't be
    read (here the site answers none), the world map is a grid where a
    level's badge counts its spots reachable now; a
    click on the level shows its spots, and a click on a spot reachable now
    marks it collected (the counter row and the chip say so), a second
    takes it off. The Table sums each kind and level (its All rows). The
    page keeps the plan and its marks, and after a reload opens on them
    once the Tracker view shows (not as the page starts). No
    CSP violation, no request but GETs of the site's files."""
    served = Site(browser, site)
    served.context.route(f"{served.origin}/art/**", lambda route: route.fulfill(status=404, body=""))   # no maps: the grid
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        assert page.evaluate("() => [document.getElementById('rando-settings').hidden, "
                             "document.getElementById('tracker').hidden]") == [True, False]
        for name in ("default", "max"):
            doc = _profile(name)
            (tmp_path / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
            _page.pick(page, "#track-open", tmp_path / f"{name}.json")
            _page.until(page, f"() => azurkit.tracker.state.view?.head.sha256 === {json.dumps(doc['sha256'])}"
                              f" && ({TRACKED})()", 300)

            def view(doc, marks, spoiler):
                return page.evaluate("""async ([marks, spoiler, gems]) => {
                    const t = azurkit.tracker.state;
                    t.marks = marks ?? {};
                    t.spoiler = spoiler;
                    t.gems = gems;
                    await azurkit.tracker.ask();
                    return t.view;
                }""", [marks, spoiler, shows_gems(marks)])

            for state, marks, kit in tracker_states(view, doc):
                if kit:
                    continue
                for spoiler in (False, True):
                    key = f"{name}/{state}/{'spoiler' if spoiler else 'plain'}"
                    shown = view(doc, marks, spoiler)
                    assert hashlib.sha256(tracking.digest(shown).encode()).hexdigest()[:32] == TRACKER[key], key
                    drawn = page.evaluate(MAP_MODEL, [list(tracking.GRID), ICONS])
                    assert hashlib.sha256(drawn.encode()).hexdigest()[:32] == TRACKER_MAP[key], key
        view(doc, None, False)   # max, nothing marked
        world = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll("#track-world .cell")].map(
            (c) => [c.dataset.level, c.querySelector(".badge").textContent]))""")
        cpython = sdk.tracker({"plan": doc})
        reached = {lv: str(sum(s["level"] == lv and s["state"] in ("near", "skip") for s in cpython["spots"].values()))
                   for lv in cpython["status"]["levels"]}
        assert {lv: n for lv, n in world.items() if n} == reached
        near = sorted(loc for loc, s in cpython["spots"].items() if s["state"] == "near")[0]
        level = cpython["spots"][near]["level"]
        page.evaluate("(level) => document.querySelector(`#track-world .cell[data-level='${level}']`).click()", level)
        count, shown, chips = page.evaluate(SHOWN_TRACKER)
        assert (shown, chips[near], set(chips) == {loc for loc, s in cpython["spots"].items() if s["level"] == level}) == (
            level, "spot near", True)
        assert count.startswith(f"Collected 0 of {cpython['status']['total']}")
        page.evaluate("(loc) => document.querySelector(`#track-level .spot[data-loc='${loc}']`).click()", near)
        _page.until(page, f"() => ({TRACKED})() && azurkit.tracker.state.marks.collected?.length === 1")
        count, _, chips = page.evaluate(SHOWN_TRACKER)
        assert (count.startswith("Collected 1 of"), chips[near]) == (True, "spot got")
        assert sdk.tracker({"plan": doc, "toggle": near})["status"]["reachable"] == page.evaluate(
            "() => azurkit.tracker.state.view.status.reachable")
        _page.click(page, "track-table")
        sums = page.evaluate("""() => [...document.querySelectorAll(".tables tr.sum")].map((r) => [...r.children]
            .map((c) => c.textContent))""")
        assert sums == [["All", "1", str(cpython["status"]["total"] - 1), str(cpython["status"]["total"])],
                        ["All", "1", str(page.evaluate("() => azurkit.tracker.state.view.status.reachable")),
                         str(cpython["status"]["total"] - 1), str(cpython["status"]["total"])]]

        _reload(page)
        assert page.evaluate("() => azurkit.tracker.state.plan") is None   # opened once the Tracker view shows
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        _page.until(page, f"() => azurkit.tracker?.state.view?.head.sha256 === {json.dumps(doc['sha256'])}"
                          f" && ({TRACKED})()", 300)
        assert page.evaluate("() => azurkit.tracker.state.marks") == {"collected": [near]}
        page.evaluate("(level) => document.querySelector(`#track-world .cell[data-level='${level}']`).click()", level)
        page.evaluate("(loc) => document.querySelector(`#track-level .spot[data-loc='${loc}']`).click()", near)
        _page.until(page, f"() => ({TRACKED})() && !azurkit.tracker.state.marks.collected?.length")
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


# Build, then Cancel: ``seen`` is the bottom bar at once and at each change after, [the page ready, the bar's value
# (null: a moving stripe or hidden), its line (null: hidden)]
BUILD_CANCEL = """() => {
    globalThis.seen = [];
    const look = () => {
        const hidden = document.getElementById("progress-row").hidden;
        seen.push([azurkit.ready, hidden ? null : document.getElementById("progress").getAttribute("value"),
                   hidden ? null : document.getElementById("progress-line").textContent]);
    };
    new MutationObserver(look).observe(document.querySelector("footer"), { subtree: true, childList: true,
                                                                            characterData: true, attributes: true });
    document.getElementById("build").click();
    document.getElementById("cancel").click();
    look();
}"""
CANCEL_AT_THE_WORLD = f"""(() => {{   // BUILD_CANCEL, once armed, as the page takes the stage onto the tracker's ask
    const Real = Worker;
    globalThis.Worker = class extends Real {{
        get onmessage() {{ return super.onmessage; }}
        set onmessage(heard) {{   // the pool's handler first: the record it brings is on its ask after it
            super.onmessage = heard && ((event) => {{
                heard(event);
                if (globalThis.cancelAt !== "armed" || ![...azurkit.asks.values()].some((a) => a.kind === "tracker"
                    && a.record?.label?.startsWith("Reading the world map"))) return;   // its exits' note in or not
                globalThis.cancelAt = "done";
                ({BUILD_CANCEL})();
            }});
        }}
    }};
}})();"""
"""An init script: :data:`BUILD_CANCEL` in the turn the page puts the tracker's world map stage on its ask, once the
page's ``cancelAt`` is ``"armed"`` (then ``"done"``). Polled from the test, the stage (0.7 s of a 0.9 s view here)
passed between two looks on GitHub's macOS runner (run 42071325305): a busy page takes the records a worker posted
meanwhile, and the answer after them, in one go, and a look waits until they are taken."""


def test_a_cancel_during_the_trackers_first_view_shows_no_stage_of_the_stopped_worker(browser, site, usa_iso):
    """Step 4.3 train: a Build and its Cancel while the Tracker's first view
    of an opened plan reads the world map stop the site's worker. The view's
    ask is sent again to the worker that replaces it, and until that worker
    is ready the bottom bar shows no value: never the stopped worker's stage
    ("Reading the world map… 50 %", or with its exits' note, 4.3m's fold),
    which nothing runs. It hides once the view is shown. The Build and
    Cancel come as the page shows the stage (:data:`CANCEL_AT_THE_WORLD`),
    not when a look of the test's sees it (Step 4.4ci28). The plan is the
    one this browser remembers, opened as the view first shows: a view
    shown with no plan reads the world map first, for the vanilla game's
    spots (Step 4.4u3)."""
    doc = _profile("default")
    served = Site(browser, site)
    try:
        served.context.add_init_script(CANCEL_AT_THE_WORLD)
        served.context.add_init_script(script="localStorage.setItem('azurkit.tracker', %s);"
                                       % json.dumps(json.dumps({"plan": doc, "marks": {}})))
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa' && azurkit.ready && !azurkit.asks.size", 300)
        _page.click(page, "tab-randomizer")
        _page.until(page, f"() => ({SETTLED})() && !azurkit.asks.size", 300)   # the tab's read: the view's is the newest
        page.evaluate("() => { globalThis.cancelAt = 'armed'; }")
        _page.click(page, "rando-view-tracker")
        _page.until(page, f"() => azurkit.tracker.state.view?.head.sha256 === {json.dumps(doc['sha256'])}"
                          f" && ({TRACKED})()", 300)
        assert page.evaluate("() => cancelAt") == "done"   # the view's ask showed the stage, and the cancel came then
        seen = page.evaluate("() => seen")
        assert not seen[0][0] and [s for s in seen if not s[0] and s[1] is not None
                                   and not s[2].startswith("Starting the engine")] == [], seen
        assert seen[-1][1:] == [None, None] and served.stray() == [], seen
    finally:
        served.close()


# The site's two engine workers (Step 4.3y, ``web/workers.mjs``; D1006, D1007): F answers the page's asks and B works
# ahead, dropped by ``terminate()`` when the page's list changes; a click whose key is B's finished job takes its
# answer, one B is still working on follows B's records; B takes F's place only while its heap is under KEEP; one heavy
# job runs at a time, and none of B's work ahead beside F's build; the page's tally stays under its 5 GiB line. Driven
# first on stub workers (each scenario's messages by hand) on a bare page (no app.mjs: no engine of its own), then once
# on two real engine workers (``web/worker.mjs`` and the wheel), whose plan of one seed is the same on both and is
# dropped mid-way by a change.
WORKERS_BARE = b"<!doctype html><meta charset=utf-8><title>workers</title>"


def _bare_page(browser, root: Path):
    """A page that is a bare document (no app.mjs: no engine of its own), every other path served from ``root`` by a
    server of a process of its own (:class:`_page.Served`), as :class:`Site` serves it."""
    files = _page.Served(root.resolve())
    context = browser.new_context()
    context.on("close", lambda _: files.close())
    context.route(f"{files.url}/", lambda route: route.fulfill(body=WORKERS_BARE, content_type="text/html"))
    context.route(re.compile(rf"^(?!{re.escape(files.url)}/)"), lambda route: route.continue_()   # the page's own blob:
                  if route.request.url.startswith(f"blob:{files.url}/") else route.fulfill(status=404, body=""))
    page = context.new_page()
    _page.load(page, f"{files.url}/")
    return context, page


WORKERS_HARNESS = """
    const { workers, canon, KEEP, GROWN } = await import("/workers.mjs");
    const tag = (m) => [m.type, m.recipe?.seed ?? m.randomizer?.seed].filter(Boolean).join(" ");
    const plan = (seed) => ({ type: "plan", recipe: { seed } });
    const build = (seed) => ({ type: "build", packs: {}, xbr: [], ...(seed ? { randomizer: { seed } } : {}) });
    const make = (options = {}) => {
        const stubs = [], readies = [];
        class Stub {
            constructor(role) { Object.assign(this, { role, got: [], stopped: false }); stubs.push(this); }
            postMessage(message) { this.got.push(message); }
            terminate() { this.stopped = true; }
            say(data) { this.onmessage({ data }); }
            crash(message) { this.onerror({ message, preventDefault() {} }); }
            tags() { return this.got.map(tag); }
        }
        const pool = workers({ start: (role) => new Stub(role), ready: (data) => readies.push(data.n), cores: 8,
                               settle: 0, ...options });
        stubs[0].say({ type: "ready", n: 1, heap: options.heap ?? 2 ** 25 });
        stubs[1]?.say({ type: "ready", n: 2, heap: 2 ** 25 });
        return { pool, stubs, readies, f: stubs[0], b: stubs[1] };
    };
    const out = {};
"""
"""The stub tests' page: workers.mjs's exports; ``tag`` (what a stub was sent: ``type`` and seed), ``plan`` and
``build`` (two messages) and ``make(options)`` (a pool on stub workers whose messages a scenario posts by hand, F and B
loaded). Each scenario fills ``out``."""


def _on_stubs(browser, rows: str) -> dict:
    """``rows``, scenarios on :data:`WORKERS_HARNESS`'s bare page: their ``out``."""
    context, page = _bare_page(browser, web_tools.ROOT / "web")
    try:
        return page.evaluate(f"async () => {{{WORKERS_HARNESS}{rows}\n    return out;\n}}")
    finally:
        context.close()


WORKERS_ROWS = """
    {   // F answers an ask, its records heard; B (loaded after F) is sent nothing
        const { pool, f, b } = make(), records = [];
        const asked = pool.ask({ type: "tracker" }, { progress: (r) => records.push(r.stage) });
        f.say({ type: "progress", stage: "view" });
        f.say({ type: "reply", reply: { view: 1 } });
        const got = await asked;
        out.asks = [f.tags(), b.tags(), records, got.reply, pool.took(got)];
    }
    {   // B works ahead; a click whose key is B's finished job takes its answer at once: F is sent nothing
        const { pool, f, b } = make(), records = [];
        pool.want([{ key: canon({ seed: "2", share: "x" }), message: plan("2") }]);
        b.say({ type: "progress", stage: "fill" });
        b.say({ type: "reply", reply: { plan: "p2" } });
        const got = await pool.ask(plan("2"), { key: canon({ share: "x", seed: "2" }),
                                                progress: (r) => records.push(r.stage) });
        out.ahead = [b.tags(), f.tags(), got.reply, pool.took(got), records, pool.state().kept];
    }
    {   // a click whose key B is working on follows B's records, and a change after it doesn't drop B
        const { pool, f, b } = make(), records = [];
        pool.want([{ key: "plan 3", message: plan("3") }]);
        b.say({ type: "progress", stage: "logic" });
        const asked = pool.ask(plan("3"), { key: "plan 3", progress: (r) => records.push(r.stage) });
        b.say({ type: "progress", stage: "fill" });
        pool.want([]);
        b.say({ type: "reply", reply: { plan: "p3" } });
        const got = await asked;
        out.following = [records, got.reply, pool.took(got), b.stopped, f.tags()];
    }
    {   // the same list again is no change; another list drops B's running job by terminate(), the next B starts it
        const { pool, stubs, f, b } = make();
        pool.want([{ key: "plan 4", message: plan("4") }]);
        pool.want([{ key: "plan 4", message: plan("4") }]);
        const same = b.stopped;
        pool.want([{ key: "plan 5", message: plan("5") }]);
        const next = stubs[2];
        next.say({ type: "ready", n: 3 });
        out.dropped = [same, b.stopped, b.tags(), next.role, next.tags(), f.tags(), pool.state().dropped];
    }
    {   // F's build past its kept line: an idle B under KEEP takes F's place (ready again) and a new B loads
        const { pool, stubs, readies, f, b } = make();
        const built = pool.ask(build(), { heavy: true });
        f.say({ type: "built", report: {}, heap: GROWN });
        await built;
        pool.ask({ type: "tracker" });
        out.promoted = [f.stopped, readies, b.tags(), stubs.length, stubs[2].role, pool.state().promoted];
    }
    {   // a busy B (a small ask beside F's build) doesn't: a new F loads; nor does a build that reports no heap leave F
        // in place
        const { pool, stubs, readies, f, b } = make();
        const built = pool.ask(build(), { heavy: true });
        pool.ask({ type: "randomizer" }, { anywhere: true });
        f.say({ type: "built", report: {}, heap: GROWN });
        await built;
        stubs[2].say({ type: "ready", n: 3 });
        const again = pool.ask(build(), { heavy: true });
        stubs[2].say({ type: "built", report: {} });
        await again;
        out.unpromoted = [f.stopped, b.stopped, stubs[2].role, stubs[2].stopped, stubs[3].role, readies,
                          pool.state().promoted];
    }
    {   // B is retired after a job past its kept line and its answer kept; a click takes it
        const { pool, stubs, f, b } = make();
        pool.want([{ key: "build k", message: build("k"), heavy: true }]);
        b.say({ type: "built", report: { size: 1 }, heap: GROWN + 1 });
        const retired = b.stopped;
        const got = await pool.ask(build("k"), { key: "build k", heavy: true });
        out.keep = [retired, stubs[2].role, got.report, pool.took(got), f.tags(), pool.state().retired];
    }
    {   // one heap: F's build keeps its worker; a heavy job ahead swaps it out and runs in that heap, not in a second
        const { pool, f, b } = make();
        const built = pool.ask(build(), { heavy: true });
        f.say({ type: "built", report: {}, heap: KEEP + 1 });
        await built;
        pool.want([{ key: "build g", message: build("g"), heavy: true }]);
        const ran = [f.tags(), b.tags()];
        const asked = pool.ask({ type: "tracker" });   // the small one answers as F
        b.say({ type: "reply", reply: { view: 5 } });
        const again = pool.ask(build("g"), { key: "build g", heavy: true });
        f.say({ type: "built", report: { size: 6 }, heap: KEEP + 2 });
        out.oneHeapF = [f.stopped, ran, (await asked).reply, (await again).report, pool.state().promoted, pool.state().swapped];
    }
    {   // one heap: B's job ahead grew it, so a heavy click on another key swaps it in, and the small one goes on as B
        const { pool, f, b } = make();
        pool.want([{ key: "build g", message: build("g"), heavy: true }]);
        b.say({ type: "built", report: {}, heap: 2 ** 29 });
        const answered = pool.ask(build("h"), { heavy: true });
        const ran = [b.tags(), f.tags()];
        b.say({ type: "built", report: { size: 7 }, heap: KEEP + 2 });
        out.oneHeapB = [b.stopped, f.stopped, ran, (await answered).report, pool.state().swapped, pool.state().kept];
    }
    {   // one heap: B's heavy job ahead the list drops for one with no heavy job (a reshape's) goes on, its answer
        // unkept, and the next heavy click runs in its heap, and the next heavy job ahead too; for a list with a heavy
        // job it is dropped
        const { pool, f, b } = make();
        pool.want([{ key: "build r", message: build("r"), heavy: true }]);
        pool.want([]);
        const on = b.stopped;
        b.say({ type: "built", report: { size: 10 }, heap: 2 ** 29 });
        const clicked = pool.ask(build("s"), { heavy: true });
        b.say({ type: "built", report: { size: 11 }, heap: 2 ** 29 });
        const report = (await clicked).report;
        pool.want([{ key: "build t", message: build("t"), heavy: true }]);
        pool.want([{ key: "build u", message: build("u"), heavy: true }]);
        out.stale = [on, report, b.tags(), f.tags(), pool.state().kept, pool.state().swapped, b.stopped,
                     pool.state().dropped];
    }
    {   // a heavy ask waits for the heavy job a click took from B: one at a time, whichever worker runs it
        const { pool, f, b } = make();
        pool.want([{ key: "build w", message: build("w"), heavy: true }]);
        const took = pool.ask(build("w"), { key: "build w", heavy: true });
        const preview = pool.ask({ type: "preview" }, { once: true, heavy: true });
        const beside = [...f.tags()];
        b.say({ type: "built", report: { size: 9 }, heap: 2 ** 26 });
        const size = (await took).report.size;
        out.waits = [beside, size, f.tags()];
        f.say({ type: "reply", reply: {} });
        await preview;
    }
    {   // a kept answer nothing can take any more is heard, so its file goes
        const gone = [];
        const { pool, b } = make({ free: (messages) => gone.push(messages.at(-1).report) });
        pool.want([{ key: "build f", message: build("f"), heavy: true }]);
        b.say({ type: "built", report: { size: 8 }, heap: 2 ** 26 });
        pool.want([]);
        await Promise.resolve();
        out.free = gone;
    }
    {   // a CSP report goes to the page whatever the worker runs; it isn't the job's
        const told = [];
        const { pool, f } = make({ told: (data) => told.push(data.type) });
        const asked = pool.ask({ type: "tracker" });
        f.say({ type: "csp", directive: "script-src", blocked: "x" });
        f.say({ type: "reply", reply: { view: 9 } });
        out.csp = [(await asked).reply, told];
    }
    {   // one heavy job at a time: F's build drops B's, B starts nothing beside it, and works on after it
        const { pool, stubs, f, b } = make();
        pool.want([{ key: "build x", message: build("x"), heavy: true }, { key: "plan x", message: plan("x") }]);
        const busy = b.tags();
        const built = pool.ask(build("y"), { heavy: true });
        const beside = [b.stopped, stubs.length];
        f.say({ type: "built", report: {}, heap: 2 ** 26 });
        await built;
        stubs[2].say({ type: "ready", n: 3 });
        out.heavy = [busy, f.tags(), beside, f.stopped, stubs[2].tags(), pool.state().dropped];
    }
    {   // a change with a rest (the Characters tab's own) alone: B starts its heavy job as any change's (Build's head
        // start); one that follows another within the rest, no click between: only once the list has held still that
        // long, so the next move of a slider drops none; after a click one is alone again; a small job and a pick's
        // start at once
        const { pool, b } = make();
        pool.want([{ key: "build r1", message: build("r1"), heavy: true }], { rest: 200 });
        const alone = [...b.tags()];
        b.say({ type: "built", report: {}, heap: 2 ** 26 });
        const t0 = performance.now();
        pool.want([{ key: "build r2", message: build("r2"), heavy: true }], { rest: 200 });
        pool.want([{ key: "build r3", message: build("r3"), heavy: true }], { rest: 200 });
        const moving = b.tags().slice(1);
        while (b.tags().length < 2) await new Promise((r) => setTimeout(r, 10));
        const rested = [b.tags().slice(1), performance.now() - t0 >= 200];
        b.say({ type: "built", report: { size: 3 }, heap: 2 ** 26 });
        const got = await pool.ask(build("r3"), { key: "build r3", heavy: true });
        pool.want([{ key: "build r4", message: build("r4"), heavy: true }], { rest: 200 });
        const clicked = [got.report, b.tags().slice(2)];
        b.say({ type: "built", report: {}, heap: 2 ** 26 });
        pool.want([{ key: "plan r", message: plan("r") }], { rest: 200 });
        const small = b.tags().slice(3);
        b.say({ type: "reply", reply: { plan: "r" } });
        pool.want([{ key: "build p", message: build("p"), heavy: true }], { begin: true });
        out.rest = [alone, moving, rested, clicked, small, b.tags().slice(4), b.stopped, pool.state().dropped];
    }
    {   // while F builds, a small ask that may go anywhere is B's; one that may not waits for F
        const { pool, f, b } = make();
        pool.ask(build(), { heavy: true });
        const small = pool.ask({ type: "randomizer" }, { anywhere: true });
        pool.ask({ type: "restore" });
        b.say({ type: "rando", reply: { share: "s" } });
        const got = await small;
        out.spare = [f.tags(), b.tags(), got.reply, pool.took(got)];
    }
    {   // the tally: past the line an idle B is retired and none loads; under it B works and its answer's bytes count;
        // past it again a kept answer holding bytes is freed (one holding none stays)
        const { pool, stubs, b } = make({ heap: 2 ** 29 });
        pool.hold(4.5 * 2 ** 30);
        pool.want([{ key: "plan t", message: plan("t") }, { key: "build t", message: build("t"), heavy: true }]);
        const over = [b.stopped, stubs.length];
        pool.hold(2 ** 20);
        const next = stubs[2];
        next.say({ type: "ready", n: 3, heap: 2 ** 29 });   // F's: neither heap is the heavy jobs' (oneHeap)
        next.say({ type: "reply", reply: { plan: "t" } });
        next.say({ type: "built", report: {}, segments: [{ kind: "bytes", data: new Uint8Array(2 ** 20) }],
                   heap: 2 ** 29 });
        const under = [next.tags(), pool.state().kept, pool.state().tally];
        pool.hold(4 * 2 ** 30);
        out.tally = [over, under, next.stopped, pool.state().kept];
    }
    {   // Cancel: a build a click took from B, its key still listed, goes on as B's and Build again follows it; an
        // unlisted one on F stops F (the idle B takes its place) and an ask waiting behind it goes to the next F
        const { pool, readies, f, b } = make();
        pool.want([{ key: "build c", message: build("c"), heavy: true }]);   // B starts it: the click below takes it
        const took = pool.ask(build("c"), { key: "build c", heavy: true });
        pool.cancel();
        const first = (await took).type;
        const again = pool.ask(build("c"), { key: "build c", heavy: true });
        b.say({ type: "built", report: { size: 2 }, heap: 2 ** 26 });
        const second = (await again).report;
        const plain = pool.ask(build("d"), { heavy: true });
        const behind = pool.ask({ type: "tracker" });
        pool.cancel();
        const third = (await plain).type;
        b.say({ type: "reply", reply: { view: 2 } });
        out.cancel = [first, b.stopped, second, third, f.stopped, b.tags(), (await behind).reply, readies,
                      pool.state().demoted];
    }
    {   // Cancel of F's running build for a listed key: F goes on as B, the idle B takes F's place
        const { pool, readies, f, b } = make();
        const took = pool.ask(build("e"), { key: "build e", heavy: true });
        pool.want([{ key: "build e", message: build("e"), heavy: true }]);
        pool.cancel();
        const first = (await took).type;
        const again = pool.ask(build("e"), { key: "build e", heavy: true });
        f.say({ type: "built", report: { size: 3 }, heap: 2 ** 26 });
        const got = await again;
        out.swapped = [first, got.report, pool.took(got), f.stopped, f.tags(), b.tags(), readies,
                       pool.state().promoted, pool.state().demoted];
    }
    {   // a once ask made while F builds a seed waits, unsent, for the F after it (B, promoted); one a worker was
        // running when it stopped answers {type: "stopped"}, and a plain one goes to the next F
        const { pool, stubs, f, b } = make();
        const seeded = pool.ask(build("s"), { heavy: true });
        f.say({ type: "built", report: { plan: { sha256: "0" } }, heap: GROWN });   // F goes once it sends the spoiler
        const preview = pool.ask({ type: "preview" }, { once: true });
        const sent = [f.tags()];
        f.say({ type: "spoiled", text: "" });
        await seeded;
        sent.push(f.stopped, b.tags());
        b.say({ type: "reply", reply: { drawn: true } });
        const drawn = (await preview).reply;
        const match = pool.ask({ type: "match" }, { once: true });
        const view = pool.ask({ type: "tracker" });
        b.crash("");
        const stopped = (await match).type;
        stubs[2].say({ type: "ready", n: 3 });
        stubs[3].say({ type: "ready", n: 4 });
        stubs[3].crash("out of memory");
        stubs[2].say({ type: "reply", reply: { view: 3 } });
        out.once = [sent, drawn, stopped, stubs[3].tags(), stubs[2].tags(), (await view).reply];
    }
    {   // fewer than 4 cores: no B, and F answers every ask in turn: a small and an aside one wait for its build, the
        // list's work ahead never runs, and a click on a listed key asks F
        const { pool, stubs, f } = make({ cores: 2 });
        pool.want([{ key: "plan 7", message: plan("7") }]);
        const built = pool.ask(build("7"), { key: "build 7", heavy: true });
        const view = pool.ask({ type: "tracker" }, { anywhere: true });
        const listed = pool.ask({ type: "pickers" }, { anywhere: true, aside: true });
        const sent = f.tags();
        f.say({ type: "built", report: { size: 7 }, heap: 2 ** 25 });
        f.say({ type: "reply", reply: { view: 7 } });
        f.say({ type: "reply", reply: { pickers: 7 } });
        const planned = pool.ask(plan("7"), { key: "plan 7" });
        f.say({ type: "reply", reply: { plan: "p7" } });
        out.cores = [sent, f.tags(), (await built).report, (await view).reply, (await listed).reply,
                     (await planned).reply, stubs.length];
    }
    try {
        canon({ file: new Blob([]) });
    } catch (error) {
        out.canon = [canon({ b: 1, a: [2, { d: 1, c: 2 }], e: undefined }), error.message];
    }
"""
"""Each scenario of :func:`test_the_sites_second_worker_works_ahead_drops_on_a_change_and_hands_a_click_its_answer`
on stub workers, whose messages it posts by hand: what each was sent (``type`` and seed), and what the pool did."""


def test_the_sites_second_worker_works_ahead_drops_on_a_change_and_hands_a_click_its_answer(browser):
    """F answers asks, B works ahead and a click takes its answer (one that
    names B's running job follows its records, and a change after the click
    doesn't drop it); another list terminates B's job; a worker a job grew
    stays for the next heavy job and answers as F, with nothing heavy beside
    it (one heap), and B's heavy job ahead that a list with no heavy job
    drops goes on, unkept, its heap the next heavy click's; B takes F's place after a build past that worker's line
    only when idle under KEEP; B is retired after a job past the line, its
    answer kept; F's build drops B's heavy job and B
    starts nothing beside it; a small ask that may go anywhere is B's while
    F builds; a heavy job of a list with a rest that follows another
    within it, no click between, waits until the list has held still that
    long (none dropped), one alone or after a click, a small one and a
    pick's don't;
    past the 5 GiB tally B neither works nor stays, and kept bytes are freed; Cancel answers at once and demotes a listed build to
    work ahead, which Build again follows; a once ask waits, unsent, for
    the F after a seed's build past KEEP, and a stopped worker's running
    once ask answers stopped while a plain one goes to the next F; no B
    under 4 cores, where F answers every ask in turn. A key is canonical
    JSON, a File refused by name."""
    got = _on_stubs(browser, WORKERS_ROWS)
    gib = 2 ** 30
    assert got == {
        "asks": [["tracker"], [], ["view"], {"view": 1}, False],
        "ahead": [["plan 2"], [], {"plan": "p2"}, True, [], []],
        "following": [["logic", "fill"], {"plan": "p3"}, True, False, []],
        "dropped": [False, True, ["plan 4"], "b", ["plan 5"], [], 1],
        "promoted": [True, [1, 2], ["tracker"], 3, "b", 1],
        "unpromoted": [True, False, "f", True, "f", [1, 3], 0],
        "keep": [True, "b", {"size": 1}, True, [], 1],
        "oneHeapF": [False, [["build", "build g"], []], {"view": 5}, {"size": 6}, 0, 1],
        "oneHeapB": [False, False, [["build g", "build h"], []], {"size": 7}, 1, ["build g"]],
        "stale": [False, {"size": 11}, ["build r", "build s", "build t"], [], [], 2, True, 1],
        "waits": [[], 9, ["preview"]],
        "free": [{"size": 8}],
        "csp": [{"view": 9}, ["csp"]],
        "heavy": [["build x"], ["build y"], [True, 2], False, ["build x"], 1],
        "rest": [["build r1"], [], [["build r3"], True], [{"size": 3}, ["build r4"]], ["plan r"], ["build p"], False,
                 0],
        "spare": [["build"], ["randomizer"], {"share": "s"}, False],
        "tally": [[True, 2], [["plan t", "build t"], ["plan t", "build t"], 2 ** 29 + 2 ** 29 + 2 ** 20 + 2 ** 20],
                  True, ["plan t"]],
        "cancel": ["cancelled", False, {"size": 2}, "cancelled", True, ["build c", "tracker"], {"view": 2}, [1, 2], 1],
        "swapped": ["cancelled", {"size": 3}, True, False, ["build e"], [], [1, 2], 1, 1],
        "once": [[["build s"], True, ["preview"]], {"drawn": True}, "stopped", ["tracker"], ["tracker"], {"view": 3}],
        "cores": [["build 7"], ["build 7", "tracker", "pickers", "plan 7"], {"size": 7}, {"view": 7}, {"pickers": 7},
                  {"plan": "p7"}, 1],
        "canon": ['{"a":[2,{"c":2,"d":1}],"b":1}', "a key holds [object Blob] at key.file"],
    }


def test_a_job_ahead_that_failed_or_whose_worker_stopped_isnt_tried_again_while_its_key_stays_listed(browser):
    """A job ahead that fails on B, or whose B stops (out of memory, say),
    isn't sent to the next B while the page's list still holds its key
    (each B would load the engine and run it again, without end): the next
    B takes the list's next item, and a click on the key asks F, which
    shows the failure itself. A list without the key, then with it again,
    tries it again."""
    got = _on_stubs(browser, """
    {
        const { pool, stubs, f, b } = make();
        pool.want([{ key: "build k", message: build("k"), heavy: true }, { key: "plan m", message: plan("m") }]);
        b.say({ type: "failed", message: "MemoryError" });
        stubs[2].say({ type: "ready", n: 3 });
        stubs[2].crash("out of memory");
        stubs[3].say({ type: "ready", n: 4 });
        const sent = [b.tags(), stubs[2].tags(), stubs[3].tags(), stubs.length];
        const asked = pool.ask(build("k"), { key: "build k", heavy: true });
        f.say({ type: "built", report: { size: 4 }, heap: 2 ** 25 });
        const clicked = [f.tags(), (await asked).report];
        pool.want([]);
        pool.want([{ key: "build k", message: build("k"), heavy: true }]);
        out.failed = [sent, clicked, stubs[3].tags(), pool.state().retired];
    }""")
    assert got == {"failed": [[["build k"], ["plan m"], [], 4], [["build k"], {"size": 4}], ["build k"], 2]}


def test_a_second_worker_that_doesnt_load_loads_again_until_three_loads_failed(browser):
    """A B whose load fails (a fetch or the engine's start: its ``failed``, or its worker's error before ``ready``) is
    loaded again at once and works ahead, the last failure's message in the pool's state; once three B loads of a visit
    have failed the page goes on without B, F answering. One failed load left the visit without B: GitHub's Windows
    runner's Chromium page waited 600 s for the image's setup built ahead with no B, two workers started and none
    dropped, retired or promoted (run 42198913490)."""
    got = _on_stubs(browser, """
    {
        const { pool, stubs, f } = make();
        pool.want([{ key: "plan 4", message: plan("4") }]);
        pool.want([{ key: "plan 5", message: plan("5") }]);   // B's job dropped: a new B loads
        stubs[2].say({ type: "failed", message: "AzurKit didn't load: TypeError: Failed to fetch" });
        stubs[3].crash("");
        stubs[4].say({ type: "ready", n: 5 });
        const again = [stubs[2].stopped, stubs[3].stopped, stubs[4].tags(), pool.state().lost, pool.state().unloaded];
        pool.want([{ key: "plan 6", message: plan("6") }]);
        stubs[5].say({ type: "failed", message: "AzurKit didn't load: RangeError" });
        const asked = pool.ask({ type: "tracker" });
        f.say({ type: "reply", reply: { view: 6 } });
        out.unloaded = [again, stubs.length, pool.state().b, pool.state().lost, (await asked).reply, f.tags()];
    }""")
    assert got == {"unloaded": [[True, True, ["plan 5"], "The engine stopped ()", 2], 6, None,
                                "AzurKit didn't load: RangeError", {"view": 6}, ["tracker"]]}


def test_a_clicks_build_whose_key_the_list_drops_and_lists_again_before_its_answer_is_built_once(browser):
    """A click's build queued behind the image's read, whose key the page's list drops (an ahead() before the image is
    read lists no build) and lists again (the image read), is built once, by F: no worker is sent it again after its
    answer. The pool forgot F's key at the drop, so after the build one heap swapped the grown F out as B and built it
    again over the dress it had just kept (a second dress of the same visit, on GitHub's Windows runner). A key the list
    doesn't hold when its ask ends (answered or cancelled) is freed, as after a change: a list holding it again (the
    change undone, whose build the page forgot) has B build it ahead."""
    got = _on_stubs(browser, """
    const item = { key: "build k", message: build("k"), heavy: true };
    const clicked = () => {   // the click's build queued behind the image's read, and an ahead() made meanwhile
        const { pool, f, b } = make();
        const read = pool.ask({ type: "vanilla" });
        const built = pool.ask(build("k"), { key: "build k", heavy: true });
        pool.want([]);
        return { pool, f, b, read, built };
    };
    {
        const { pool, f, b, read, built } = clicked();
        f.say({ type: "vanilla" });
        await read;
        pool.want([item]);
        f.say({ type: "built", report: { size: 1 }, heap: KEEP + 1 });
        const once = [(await built).report, f.tags(), b.tags(), pool.state().swapped];
        pool.want([]);
        pool.want([item]);
        out.once = [once, f.tags(), b.tags(), pool.state().swapped];
    }
    {
        const { pool, f, b, read, built } = clicked();
        f.say({ type: "vanilla" });
        await read;
        f.say({ type: "built", report: { size: 1 }, heap: KEEP + 1 });
        await built;
        pool.want([item]);
        out.after = [f.tags(), b.tags(), pool.state().swapped];
    }
    {
        const { pool, f, b, built } = clicked();
        pool.cancel();
        const cancelled = (await built).type;
        pool.want([item]);
        out.cancelled = [cancelled, f.tags(), b.tags()];
    }""")
    assert got == {"once": [[{"size": 1}, ["vanilla", "build k"], [], 0], ["vanilla", "build k", "build k"], [], 1],
                   "after": [["vanilla", "build k", "build k"], [], 1],
                   "cancelled": ["cancelled", ["vanilla"], ["build k"]]}


def test_a_b_retired_at_the_tally_line_isnt_loaded_again_until_a_fresh_bs_heap_fits_under_it(browser):
    """At the page's 5 GiB tally an idle B is retired, and a new B loads
    only once the tally plus the last B's heap when it loaded is under the
    line: one whose load alone would cross it isn't started (each would be
    retired at its ready and another started, without end)."""
    got = _on_stubs(browser, """
    {
        const { pool, stubs } = make({ heap: 3 * 2 ** 30 });
        pool.hold(2 * 2 ** 30 - 2 ** 24);   // 16 MiB under the line without B, whose heap when it loaded is 32 MiB
        const over = [stubs[1].stopped, stubs.length, pool.state().b];
        pool.hold(2 ** 30);
        stubs[2].say({ type: "ready", n: 3, heap: 2 ** 25 });
        out.line = [over, stubs.length, pool.state().b.loaded, stubs[2].stopped, pool.state().retired];
    }""")
    assert got == {"line": [[True, 2, None], 3, True, False, 1]}


def test_fs_build_drops_bs_plan_ahead_too_so_b_runs_nothing_beside_it_and_plans_again_after(browser):
    """B's work ahead never runs beside F's build, a light job too: the
    click's build drops B's plan ahead (a dropped job, its key still
    listed), no B loads while F builds, and the B after it plans again."""
    got = _on_stubs(browser, """
    {
        const { pool, stubs, f, b } = make();
        pool.want([{ key: "plan s", message: plan("s") }, { key: "build s", message: build("s"), heavy: true }]);
        const busy = b.tags();
        const built = pool.ask(build("s"), { key: "build s", heavy: true });
        const beside = [b.stopped, stubs.length, pool.state().b];
        f.say({ type: "built", report: { size: 5 }, heap: 2 ** 26 });
        const report = (await built).report;
        stubs[2].say({ type: "ready", n: 3 });
        out.beside = [busy, f.tags(), beside, report, stubs[2].tags(), pool.state().dropped];
    }""")
    assert got == {"beside": [["plan s"], ["build s"], [True, 2, None], {"size": 5}, ["plan s"], 1]}


def test_a_click_takes_bs_finished_build_as_cpythons_and_a_change_drops_it_for_the_new_recipes(browser, site, usa_iso):
    """D1007 on the page: a settled recipe is built ahead in B, its pieces are what CPython builds, and Build takes
    them with F sent nothing. A slider's change frees that answer, and a Build right after it never gets it: it follows
    B on the new recipe, or runs its own, and gets the new recipe's bytes."""
    served = Site(browser, site)
    try:
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.until(page, "() => azurkit.vanilla?.release === 'usa' && azurkit.ready", 300)
        _page.tick(page, ["fps_unlock"])
        _page.until(page, "() => azurkit.pool.state().kept.length === 1", 300)
        page.evaluate("() => document.querySelector('#build').click()")
        built = _built(page)
        made, report = sdk.image({"iso": str(usa_iso), "packs": page.evaluate("() => azurkit.sent")})
        assert (built["report"], built["segments"]) == (report, _signature(made)) and page.evaluate("() => azurkit.took")
        assert page.evaluate("() => azurkit.pool.state().kept") == []
        _page.tick(page, ["fps_unlock"], {"fps_unlock": {"target_fps": "120"}})
        page.evaluate("() => document.querySelector('#build').click()")
        built = _built(page)
        made, report = sdk.image({"iso": str(usa_iso), "packs": page.evaluate("() => azurkit.sent")})
        assert (built["report"], built["segments"]) == (report, _signature(made))
        assert page.evaluate("() => azurkit.sent.fps_unlock.target_fps") == 120
        assert served.stray() == [] and page.evaluate("() => azurkit.violations") == []
    finally:
        served.close()


def test_a_click_never_takes_bs_build_of_a_choice_the_engines_answer_changes(browser, site, usa_iso, tmp_path):
    """B builds ahead the tab's choice; Build sends the engine's answer to it, which drops what a body locks. garret4's
    height kept across a pick of Beamlord (installed from the source) is B's refusal, and Build, keyed on the
    character it sends, doesn't take it: it builds {"species": "beamlord"}, CPython's bytes."""
    from azurkit.tools.characters import _player_variants, content

    repo = tmp_path / "repo"
    (repo / "variants/beamlord").mkdir(parents=True)
    (repo / "variants/beamlord/variant.json").write_text(json.dumps({"beamlord": json.loads(
        _player_variants.BUILTIN.read_text(encoding="utf-8"))["beamlord"]}), encoding="utf-8")
    entry = {"author": "Azurik-Modding-Hub", "licence": "MIT", "version": 1, "requires": [], "id": "beamlord",
             "kind": "variant", "title": "Beamlord", "files": [{"path": "variants/beamlord/variant.json"}]}
    (repo / "manifest.json").write_text(json.dumps(content.filled(
        {"format": content.FORMAT, "schema_version": 1, "entries": [entry]}, lambda path: (repo / path).read_bytes())))
    served = Site(browser, site)

    def source(route, request) -> None:
        rel = repo / urllib.parse.urlsplit(request.url).path.removeprefix("/content-test/")
        route.fulfill(path=str(rel)) if rel.is_file() else route.fulfill(status=404, body="")
    served.context.route(f"{served.origin}/content-test/**", source)
    try:
        served.open().evaluate("() => localStorage.setItem('azurkit.content_source', './content-test/')")
        page = served.open()
        _page.pick(page, "#iso", usa_iso)
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view?.from && azurkit.characters.state.view.community.length", 300)
        beamlord = "document.querySelector('#char-community .entry[data-entry=\"beamlord\"] {}')"
        page.evaluate(f"() => {beamlord.format('button')}.click()")
        _page.until(page, f"() => {beamlord.format('.model')}", 120)
        _page.click(page, "char-height")   # garret4's height, which a pick keeps
        page.evaluate(f"() => {beamlord.format('.model')}.click()")
        _page.until(page, "() => !azurkit.characters.waiting() && azurkit.pool.state().kept.length === 1", 600)
        assert page.evaluate("() => [azurkit.characters.choice(), azurkit.characters.character()]") == [
            {"size": "garret4", "species": "beamlord"}, {"species": "beamlord"}]
        page.evaluate("() => document.querySelector('#build').click()")
        built = _built(page)
        made, report = sdk.image({"iso": str(usa_iso), "packs": page.evaluate("() => azurkit.sent"),
                                  "character": {"species": "beamlord"}})
        assert built == _as_cpython(built, report, made) and page.evaluate("() => azurkit.took") is False
    finally:
        served.close()


BUILD_FILES = """async () => {
    const names = [];
    for await (const name of (await navigator.storage.getDirectory()).keys()) names.push(name);
    return names.filter((name) => name.startsWith("azurkit-build-"));
}"""


WROTE = """const azurkitWrite = FileSystemSyncAccessHandle.prototype.write;
FileSystemSyncAccessHandle.prototype.write = function (bytes, options) {
    postMessage({ type: "wrote", size: bytes.byteLength, copy: bytes.byteLength === bytes.buffer.byteLength });
    return azurkitWrite.call(this, bytes, options);
};
"""
"""The worker's first lines in the next test: it posts each write to a build file, and whether its bytes were a copy
of their own (HEARD holds them)."""


def test_a_characters_pieces_go_from_the_engines_heap_into_a_build_file_held_until_its_build_is_gone_and_a_crash_leaves_none(
        browser, site, usa_iso, tmp_path):
    """P7 and X10: a character's build writes its pieces into an OPFS file, the Blob's bytes CPython's, each piece
    straight from the engine's heap: no copy of it is left in the worker for a GC an idle worker doesn't ask for (in
    WebKit each build left two, 4.3r4s: about 0.5 GB a build of a page built again and again). Storage counts it;
    another tab's load leaves it while this tab holds it. A change forgets the build and removes it; a saved one stays
    past that (its download may still read it, and is whole), and the next load removes it once no page holds it, as
    it does a crashed page's. Where the browser gives no sync handle, only WebKit on Windows, the pieces are Blobs and
    no file is left. Each call to a page is bounded (``_page.answer``); a page whose process WebKit ended at its
    network process's request, WebKit's own fault (``_page.past_refusal``; run 42461371001, at the change's tick), runs
    the test again once in a browser of its own."""
    recipe = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
              "character": {"species": "keylord"}}
    made, report = sdk.image(recipe | {"iso": str(usa_iso)})
    _page.past_refusal(lambda visit: _held_build_file(browser, site, usa_iso, tmp_path / f"profile-{visit}", recipe,
                                                      made, report))


def _held_build_file(browser, site, usa_iso, profile: Path, recipe: dict, made: iso.Image, report: dict) -> None:
    """The last test's run, in a browser of its own (``profile``)."""
    served = Site(browser, site, profile)
    try:
        served.context.add_init_script(HEARD)
        worker = (site / "worker.mjs").read_text(encoding="utf-8")
        served.context.route("**/worker.mjs", lambda route: route.fulfill(
            body=WROTE + worker, content_type="text/javascript"))
        page = served.context.new_page()
        _page.load(page, f"{served.origin}/{sdk.preset_encode(recipe)}")
        _page.until(page, "() => globalThis.azurkit?.loaded", 120)
        _page.pick(page, "#iso", usa_iso)
        _page.answer(page, "() => document.querySelector('#build').click()")
        built = _built(page)
        assert built == _as_cpython(built, report, made)
        name = _page.answer(page, "() => azurkit.build.out")
        if name is None:   # WebKit on Windows makes the file but gives no sync handle to it (run 41551497620): Blobs,
            # the file removed (WebKit's IPC::SharedFileHandle::create is std::nullopt without Unix sockets)
            assert [sys.platform, browser.browser_type.name, _page.answer(page, BUILD_FILES)] == ["win32", "webkit", []]
            return
        writes = _page.answer(page, "() => writes")
        assert writes and not [w for w in writes if w["copy"]]
        assert name in _page.answer(page, BUILD_FILES)
        _page.click(page, "tab-tools")
        _page.until(page, """() => [...document.querySelectorAll("#tools-storage td")]
                                 .some((td) => td.textContent.startsWith("Built images"))""", 60)
        other = served.open()   # its load's sweep
        assert name in _page.answer(other, BUILD_FILES)
        _page.tick(page, ["fps_unlock"])   # a change: the build is forgotten
        _page.until(page, f"async () => !(await ({BUILD_FILES})()).includes({json.dumps(name)})", 60)
        _page.answer(page, "() => document.querySelector('#build').click()")
        _page.built(page)
        name = _page.answer(page, "() => azurkit.build.out")
        with page.expect_download(timeout=600_000):
            _page.click(page, "save")
        _page.tick(page, ["fps_unlock"], {"fps_unlock": {"target_fps": "120"}})   # forgotten, but saved
        assert name in _page.answer(page, BUILD_FILES)
        assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck", 600) == "held"
        _page.close(page)
        # no page holds it once its lock is gone, which a closed page's may not be yet as close() returns (Linux's
        # Chromium: the file outlived the reload's one sweep, run 41521288667)
        _page.until(other, f"async () => !(await navigator.locks.query()).held.some((l) => l.name === {json.dumps(name)})",
                    60)
        _page.load(other)
        _page.until(other, f"async () => !(await ({BUILD_FILES})()).includes({json.dumps(name)})", 60)
    finally:
        served.close()


KEPT_DRESSES = """(order) => new Promise((done) => {   // the hints azurkit-dress keeps, oldest first (its order record's), put first
    const opened = indexedDB.open("azurkit-dress", 1);
    opened.onupgradeneeded = () => opened.result.createObjectStore("dress");
    opened.onsuccess = () => {
        const store = opened.result.transaction("dress", order ? "readwrite" : "readonly").objectStore("dress");
        if (order) store.put(order, "");
        const asked = store.get("");
        asked.onsuccess = () => { opened.result.close(); done(asked.result ?? []); };
    };
})"""
DRESSED = ("Dressing keylord (reading its files)", "Dressing keylord (kept from an earlier build)")
DRESSING_HELD = """async () => (await navigator.locks.query()).held.some((lock) => lock.name === "azurkit-dressing")"""


def test_a_character_built_again_at_a_later_visit_is_dressed_from_what_this_browser_kept_as_cpython_dresses_it(
        browser, site, usa_iso, tmp_path):
    """D1067 (D1015's store on the site): a character's first build keeps its dress in this browser (azurkit-dress, by
    the build's hint), and the same build at a later visit is dressed from it (its engine's notes say so; the body's
    files aren't read again) and is the newest kept again, past a hint kept after it (the least recently built go
    first), each CPython's image. The notes are read as the page's workers post them (HEARD), not off the bar, which
    shows the newest ask's latest: on Windows' WebKit the models' ask, made after the click, held the bar past the
    first visit's "(reading its files)" (run 41678038275). While the first visit's dress is made, a worker of its holds
    the lock the image's rest, hashed in the background after the pick, gives way to (Step 4.4ci25)."""
    recipe = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
              "character": {"species": "keylord"}}
    made, report = sdk.image(recipe | {"iso": str(usa_iso)})
    served = Site(browser, site, tmp_path / "profile")
    try:
        served.context.add_init_script(HEARD)
        for visit in range(2):
            page = served.context.new_page()
            _page.load(page, f"{served.origin}/{sdk.preset_encode(recipe)}")
            _page.until(page, "() => globalThis.azurkit?.loaded", 120)
            _page.pick(page, "#iso", usa_iso)
            page.evaluate("() => document.querySelector('#build').click()")
            if not visit:
                assert _page.until(page, DRESSING_HELD, 120)
            built = _built(page)
            assert built == _as_cpython(built, report, made)
            notes = page.evaluate("() => notes")
            assert [any(note.startswith(stage) for note in notes) for stage in DRESSED] == [not visit, bool(visit)], notes
            if not visit:   # kept after the answer; then a hint kept after it
                hint, = _page.until(page, f"() => ({KEPT_DRESSES})().then((hints) => hints.length === 1 && hints)", 120)
                page.evaluate(KEPT_DRESSES, [hint, "later"])
            else:
                assert _page.until(page, f"() => ({KEPT_DRESSES})().then((hints) => hints[0] === 'later' && hints)",
                                   120) == ["later", hint]
            page.close()
    finally:
        served.close()


# Web Locks refused, as a browser that keeps no site data refuses them, query() too (Firefox with every cookie blocked:
# "SecurityError: LockManager.request: request() is not allowed in this context"), on a page and in a worker
LOCKS_REFUSED = """for (const call of ["request", "query"]) LockManager.prototype[call] = function () {
    return Promise.reject(new DOMException(`LockManager.${call}: ${call}() is not allowed in this context`,
                                           "SecurityError"));
};
"""
LOCK_ASKED = "() => navigator.locks.request('any', () => 0).then(() => '', (refused) => refused.name)"


def test_a_build_wearing_a_character_builds_as_cpython_builds_it_where_the_browser_refuses_web_locks(
        browser, site, usa_iso):
    """Step 4.4ci25's review: an ask that carries a character runs holding ``DRESSING`` (``worker.mjs``'s
    dressing()), and ran only as the lock's callback, so where the browser refuses Web Locks (Firefox with every cookie
    blocked) it never ran and the build failed by the refusal. Refused on the page and in its engine's worker, the
    ask runs without the lock and the build is CPython's."""
    recipe = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
              "character": {"species": "keylord"}}
    made, report = sdk.image(recipe | {"iso": str(usa_iso)})
    served = Site(browser, site)
    try:
        served.context.add_init_script(LOCKS_REFUSED)
        worker = (site / "worker.mjs").read_text(encoding="utf-8")
        served.context.route("**/worker.mjs", lambda route: route.fulfill(
            body=LOCKS_REFUSED + worker, content_type="text/javascript"))
        page = served.context.new_page()
        _page.load(page, f"{served.origin}/{sdk.preset_encode(recipe)}")
        _page.until(page, "() => globalThis.azurkit?.loaded", 120)
        assert page.evaluate(LOCK_ASKED) == "SecurityError"
        _page.pick(page, "#iso", usa_iso)
        page.evaluate("() => document.querySelector('#build').click()")
        built = _built(page)
        assert built == _as_cpython(built, report, made)
    finally:
        served.close()


def _site_engine(monkeypatch, tmp_path):
    """worker.mjs's engine, its Python run here under CPython (Pyodide's js
    modules stood in for): its ``ask(kind, **given)``, a request's answer."""
    js, pyodide, ffi, pyodide_js = map(types.ModuleType, ("js", "pyodide", "pyodide.ffi", "pyodide_js"))
    js.JSON, js.Object = types.SimpleNamespace(stringify=json.dumps), types.SimpleNamespace(fromEntries=dict)
    js.Blob, js.postMessage, pyodide.ffi, ffi.to_js = None, None, ffi, lambda value, **_: value
    pyodide_js.FS = types.SimpleNamespace(readFile=lambda path: Path(path).read_bytes(), unlink=os.unlink)
    for module in (js, pyodide, ffi, pyodide_js):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(characters, "CACHE", characters.CACHE)   # each as it was after
    monkeypatch.setattr(pool, "TICK", pool.TICK)
    engine = {"__name__": "worker"}
    exec((_page.WEB / "worker.mjs").read_text(encoding="utf-8").split("const ENGINE = `")[1].split("`;")[0], engine)
    engine["PIECE"] = str(tmp_path / "piece")
    return lambda kind, **given: engine["engine"](types.SimpleNamespace(type=kind, **given))


def test_the_site_engine_keeps_a_characters_build_dress_and_nothing_a_reshapes_pictures_work_out_after_a_build(
        monkeypatch, tmp_path):
    """Step 4.3r4t (D1054's one heap, D1067): worker.mjs's engine, its Python
    run here under CPython (Pyodide's js modules, sdk's build and pictures
    stood in for), hands a character's build's dress to its kept ask; after a
    build the page asks nothing of (no character, as B's ahead build of the
    default recipe), a reshape's pictures in that worker keep nothing. They
    kept each shape's dress (booblord's plan: about 117 MB) to its next build."""
    ask = _site_engine(monkeypatch, tmp_path)

    def staged(recipe, **_):   # a build, its character's dress worked out on its way
        if "character" in recipe:
            characters._kept("the dress", lambda: b"dress", bytes, bytes)
        yield {}
        return types.SimpleNamespace(segments=list, size=0), {}

    def preview(recipe):   # a reshape's pictures, its shape's dress worked out on their way
        characters._kept(json.dumps(recipe["character"]), lambda: b"plan", bytes, bytes)
        return {}

    monkeypatch.setattr(sdk, "image_staged", staged)
    monkeypatch.setattr(sdk, "image_checks", lambda image, report: [])
    monkeypatch.setattr(sdk, "preview", preview)
    for character in ({"species": "booblord"}, None):   # its asks as build() sends them
        recipe = {"iso": "x.iso", "packs": {}} | ({"character": character} if character else {})
        assert ask("build", recipe=types.SimpleNamespace(to_py=lambda: recipe)) == {"hash": [], "patched": []}
        assert ask("hashed", shas={})["size"] == 0
        if character:
            assert ask("kept") == {"the dress": b"dress"}
    for x in (1.25, 1.4):
        assert ask("preview", recipe={"character": {"species": "booblord", "shapes": {"bust": x}}}) == {}
    assert ask("kept") == {}   # what the worker holds


def test_the_site_engines_restore_reads_the_logic_before_the_page_is_ready_when_randomize_comes_back_on(
        monkeypatch, tmp_path):
    """Step 4.4bd (review D1): worker.mjs's restore, whose remembered
    randomizer is checked against the shipped skip table alone, reads the
    randomizer's logic when Randomize comes back on, before the page is
    ready, as the app's server reads it ahead (D1008's intent), so a
    reopen's Randomizer tab and tracker (S21) find it read; Randomize off,
    or none remembered, reads nothing. Without it S21 read the logic inside
    its click (WebKit 1.01 -> 1.58 s)."""
    ask, read = _site_engine(monkeypatch, tmp_path), []
    monkeypatch.setattr(randomizer, "remembered", lambda given: given)   # checked, as the shipped skip table checks it
    monkeypatch.setattr(randomizer, "kept_logic", lambda: read.append("read"))
    heard = []
    for rando in ({"on": True, "seed": "2", "settings": {}}, {"on": False, "seed": "2", "settings": {}}, None):
        out = ask("restore", setup={"ticked": []} | ({"randomizer": rando} if rando else {}))
        heard.append((out.get("randomizer"), out["dropped"], read.copy()))
        read.clear()
    assert heard == [({"on": True, "seed": "2", "settings": {}}, [], ["read"]),
                     ({"on": False, "seed": "2", "settings": {}}, [], []), (None, [], [])]


WORKERS_SMOKE = """async ({ seed }) => {
    const { workers } = await import("/workers.mjs");
    const start = () => {   // as app.mjs starts its engine: a blob: URL that imports worker.mjs
        const entry = new URL("worker.mjs", location.href).href;
        return new Worker(URL.createObjectURL(new Blob([`import ${JSON.stringify(entry)};\\n`],
                                                       { type: "text/javascript" })), { type: "module" });
    };
    const smoke = globalThis.smoke = { told: [] };
    smoke.pool = workers({ start, ready: () => smoke.ready = true, told: (data) => smoke.told.push(data.type),
                           cores: 8, settle: 0 });
}"""
"""Two real engine workers on the site's worker.mjs, kept as ``smoke`` (its pool, F's ready, what no job asked for)."""


def test_two_real_engine_workers_plan_a_seed_alike_and_a_change_drops_bs_plan_mid_way(browser, site):
    """On the site's own worker.mjs and wheel: B plans the typed seed ahead
    while F plans it for an ask with no key; the click with the key takes
    B's plan at once, and it is F's, byte for byte. Then a change while B
    plans another seed terminates B, and a new B loads."""
    context, page = _bare_page(browser, site)
    try:
        page.evaluate(WORKERS_SMOKE, {"seed": "azurkit"})
        _page.until(page, "() => smoke.ready && smoke.pool.state().b?.loaded", 300)
        page.evaluate("""() => {
            smoke.pool.want([{ key: "plan azurkit", message: { type: "plan", call: 1, recipe: { seed: "azurkit" } } }]);
            smoke.pool.ask({ type: "plan", call: 2, recipe: { seed: "azurkit" } }).then((data) => smoke.f = data);
        }""")
        _page.until(page, "() => smoke.f && smoke.pool.state().kept.includes('plan azurkit')", 600)
        took, same, planned, waited = page.evaluate("""async () => {
            const asked = performance.now();
            const got = await smoke.pool.ask({ type: "plan", call: 3, recipe: { seed: "azurkit" } },
                                             { key: "plan azurkit" });
            return [smoke.pool.took(got), JSON.stringify(got.reply) === JSON.stringify(smoke.f.reply),
                    "plan" in got.reply, performance.now() - asked < 1000];
        }""")
        assert (took, same, planned, waited) == (True, True, True, True)
        page.evaluate("""() => smoke.pool.want([{ key: "plan 2", message: { type: "plan", call: 4,
                                                                            recipe: { seed: "2" } } }])""")
        _page.until(page, "() => smoke.pool.state().b?.job === 'plan 2'", 120)
        page.evaluate("() => smoke.pool.want([])")
        _page.until(page, "() => smoke.pool.state().b?.loaded", 300)
        state = page.evaluate("() => smoke.pool.state()")
        assert (state["dropped"], state["started"], state["promoted"], state["kept"], state["f"]["job"]) == (
            1, 3, 0, [], None)
        assert page.evaluate("() => smoke.told") == ["progress"] * 4   # F's start's steps; neither B's
        page.evaluate("() => smoke.pool.close()")
    finally:
        context.close()
