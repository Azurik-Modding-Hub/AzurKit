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
rows (D909), light's faint text readable and a light first frame; and it
remembers its setup between visits until Reset to defaults (Step 4.1j, D915),
its faint text readable in dark too. Under the
page's CSP (no ``'unsafe-eval'``) nothing is refused, and every request is a GET of one of the site's own files: the image
never leaves the page. The page is driven as
``tests/_page.py`` says."""

from __future__ import annotations

import base64
import contextlib
import functools
import hashlib
import http.server
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.tools import data, mods
from azurkit.tools.randomizer import generator, tracking
from azurkit.tools.randomizer.art import icons
from scripts import record_goldens, web_tables, web_tools
from tests import _g1, _hosts, _page, _perf
from tests.test_randomizer import TRACKER, TRACKER_MAP, _profile, shows_gems, tracker_states

ORIGIN = "https://azurkit.test"
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
    """The site served to a fresh browser context at :data:`ORIGIN` from its
    folder (Playwright's routing, no server), every request logged. Its
    service worker is blocked: routing never sees a service worker's own
    requests, so these pages run uncontrolled, as a browser without one does
    (``tests/test_service_worker.py`` holds the site under ``sw.js``). A
    ``profile`` makes it persistent; in WebKit with a home of its own
    (``<profile>-home``), as Playwright's WebKit keeps OPFS, the build files,
    in the user's ``~/Library/WebKit/org.webkit.Playwright`` for every browser
    it launches while each browser's Web Locks are its own, so another test's
    page load swept this one's held build file (the gate on 3fd00b2: its
    Save's check failed reading it). CoreFoundation's ``CFFIXED_USER_HOME``
    moves it (macOS)."""

    def __init__(self, browser, root: Path, profile: Path | None = None, **options):
        self.root, self.requests = root.resolve(), []
        options = {"service_workers": "block", **options}
        if profile and browser.browser_type.name == "webkit":
            home = profile.with_name(f"{profile.name}-home")
            home.mkdir(parents=True, exist_ok=True)
            options = {"env": {**os.environ, "CFFIXED_USER_HOME": str(home)}} | options
        self.context = (browser.browser_type.launch_persistent_context(str(profile), headless=True, accept_downloads=True,
                                                                       **options) if profile
                        else browser.new_context(accept_downloads=True, **options))
        self.context.add_init_script(FOUR_CORES)
        self.context.route("**/*", self._serve)

    def _serve(self, route, request) -> None:
        if request.url.startswith(f"blob:{ORIGIN}/"):   # the page's own blob: (WebKit routes them; Chromium doesn't)
            return route.continue_()
        url = urllib.parse.urlsplit(request.url)
        self.requests.append((request.method, request.url, request.post_data_buffer))
        file = (self.root / (urllib.parse.unquote(url.path).lstrip("/") or "index.html")).resolve()
        if f"{url.scheme}://{url.netloc}" != ORIGIN or not file.is_relative_to(self.root) or not file.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(path=str(file), content_type=_page.content_type(file.name))

    def open(self):
        """A new page, its engine loaded."""
        page = self.context.new_page()
        page.goto(f"{ORIGIN}/")
        _page.until(page, "() => globalThis.azurkit?.ready", 120)
        return page

    def stray(self) -> list[str]:
        """Each request that isn't a GET of a site file, with no body, at :data:`ORIGIN`."""
        files = {f"{ORIGIN}/{p.relative_to(self.root).as_posix()}" for p in self.root.rglob("*") if p.is_file()}
        bare = ((method, url.partition("#")[0], body) for method, url, body in self.requests)   # a link's fragment
        return [f"{method} {url}" for method, url, body in bare
                if method != "GET" or body or (url if url != f"{ORIGIN}/" else f"{ORIGIN}/index.html") not in files]

    def close(self) -> None:
        self.context.close()


def _built(page) -> dict:
    """The page's build once it is ready: its report and its segments
    (``["copy", offset, size]``, ``["bytes", size, sha256]``, ``["zero", size]``)."""
    return {"report": _page.built(page), "segments": page.evaluate(SIGNATURE)}


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
    as many at once as the host has cores: each page's report and segments are CPython's for the values
    it sent, and the packs at their defaults and the slider case hold their
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
        # A page and its engine a core: all 21 open on a 3-core runner, Firefox's next ran out of its 120 s to start
        for group in itertools.batched(cases, max(2, os.cpu_count() or 2)):
            pages = [served.open() for _ in group]
            for (name, values, case), page in zip(group, pages):
                if (name, values, case) == FPS:
                    _page.tick(page, ["fps_unlock"])   # which unlocks its settings (D907)
                    assert _page.slide(page, "fps_unlock", "target_fps", "60") == ["30", "120", "60", "60"]
                    assert _page.slide(page, "fps_unlock", "target_fps", "1000") == ["30", "1000", "1000", "1000"]
                page.set_input_files("#iso", str(path))
                if name in read["packs"]:
                    assert _page.until(page, "() => azurkit.vanilla") == read
                    for slider, value in read["packs"][name].items():
                        low, high = page.evaluate(TRACK, f"{name}.{slider}")
                        assert float(low) <= value <= float(high)
                        assert page.evaluate(UNIT, f"{name}.{slider}").endswith(f" · vanilla {value:g}")
                _page.build(page, [name], {name: values})
            for (name, values, case), page in zip(group, pages):
                built, sent = _built(page), page.evaluate("() => azurkit.sent")
                assert sent == {other: {s.name: float(values.get(s.name, s.default) if other == name else s.default)
                                        for s in mods.PACKS[other].sliders()}
                                for other in (name, *mods.PACKS[name].requires)}
                made, report = sdk.image({"iso": str(path), "packs": sent})
                if case:
                    _g1.check(built["report"]["result"], golden[case], case)
                if values.get("fly_speed") == "1e39":
                    note = "qol_photo_mode fly_speed: 1e+39 is past float32's range: written as inf (Q110)"
                    assert built["report"]["notes"] == [note]
                    assert f" · note: {note} · changed: " in page.evaluate(STATUS)   # before the files, which run long
                assert (built["report"], built["segments"]) == (report, _signature(made)), (name, values)
                _page.check_csp(page)
                page.close()
        assert served.stray() == []
    finally:
        served.close()


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
        assert (link, page.evaluate("() => location.hash")) == (f"{ORIGIN}/{fragment}", fragment)
        assert page.evaluate("() => document.querySelector('#link').value") == link
        loaded = served.context.new_page()
        loaded.goto(link)
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
        with_cell = f"{ORIGIN}/{sdk.preset_encode({'packs': {'qol_alloc_race': {}}, 'xbr': [cell]})}"
        again = served.context.new_page()
        again.goto(with_cell)
        _page.until(again, "() => globalThis.azurkit?.loaded")
        assert again.evaluate("() => [azurkit.xbr, document.querySelector('#xbr-note').textContent]") == [
            [cell], "The Data tab holds 1 config.xbr edit, which each build applies."]
        assert _locks(again)["fps_unlock"] == [False, "locked"]
        _page.click(again, "share")
        assert _page.until(again, "() => azurkit.link") == with_cell
        bad = served.context.new_page()
        bad.goto(f"{ORIGIN}/#p=@@")
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
        assert _page.first_paint(later, f"{ORIGIN}/") == LIGHT
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
            page.goto(f"{ORIGIN}/")
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
    page.reload()
    _page.until(page, "() => globalThis.azurkit?.ready", 120)


def test_the_page_remembers_its_setup_until_reset_and_names_what_it_drops(browser, site):
    """D915: the page keeps its ticks and settings in the browser's storage
    (each setting changed from its default, an unticked pack's too, D907:
    names and numbers, nothing of the image), and a reload brings them back
    before an image is picked, unmarked and locked as they were, and says
    so. Reset to defaults, in the bottom bar and off while the page is at
    them, ticks the packs on by default, sets every setting to its default
    and forgets the setup, so a reload opens at the defaults. A remembered
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
        assert [page.evaluate(STATUS), _page.marked(page), page.evaluate(RESET)] == [
            "Restored your last setup: 1 pack on. Reset to defaults clears it.", [], False]
        assert [_locks(page)[name] for name in ("fps_unlock", "player_physics")] == [[True, "open"], [False, "locked"]]

        _page.click(page, "reset")
        assert [list(_page.ticked(page)), page.evaluate(FIELDS, "player_physics"), page.evaluate(RESET)] == [
            defaults, fresh, True]
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
        linked.goto(f"{ORIGIN}/{sdk.preset_encode({'packs': {'qol_alloc_race': {}}})}")
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


class _Quiet(_page.Static):
    def log_message(self, *args) -> None:
        pass


@contextlib.contextmanager
def _static(root: Path):
    """``root`` served as a static host does, at an address on 127.0.0.1."""
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root))) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{httpd.server_port}/"
        finally:
            httpd.shutdown()


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
        page.set_input_files("#saves-hdd", str(hdd))
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
        page.set_input_files("#iso", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla?.release === 'usa' && !document.getElementById('replace-path').disabled", 300)
        page.evaluate("() => { document.getElementById('replace-path').value = 'default.xbe'; }")
        page.set_input_files("#replace-file", str(mine))
        _page.until(page, "() => /default.xbe isn't replaced: .*the packs' file/.test(document.getElementById('status').textContent)", 120)
        page.evaluate(f"""() => {{ document.getElementById('replace-path').value = {json.dumps(name)};
            const bar = document.getElementById('progress'), line = document.getElementById('progress-line');
            globalThis.readBar = [];
            new MutationObserver(() => bar.hasAttribute('value') && readBar.push(line.textContent))
              .observe(bar, {{ attributes: true, attributeFilter: ['value'] }}); }}""")
        page.set_input_files("#replace-file", str(mine))
        _page.until(page, "() => azurkit.replace.entries().length === 1", 120)
        assert page.evaluate("() => azurkit.replace.entries()") == [entry]
        shown = page.evaluate("() => readBar")
        assert shown[0] == "Reading mine.bin… 0 %" and shown[-1] == "Reading mine.bin… 100 %", shown
        page.evaluate("() => document.getElementById('share').click()")
        _page.until(page, "() => /never carries a replaced file/.test(document.getElementById('status').textContent)", 60)
        page.evaluate("() => document.getElementById('tab-patches').click()")
        page.evaluate("() => document.getElementById('build').click()")
        _page.until(page, "() => azurkit.build || document.getElementById('status').classList.contains('error')", 600)
        assert page.evaluate("() => azurkit.build.report.result") == expected["result"]
        with page.expect_download(timeout=600_000) as caught:
            page.evaluate("() => document.getElementById('save').click()")
        with open(caught.value.path(), "rb") as f:
            assert hashlib.file_digest(f, "sha256").hexdigest() == want
        caught.value.delete()
        _page.until(page, "() => azurkit.ready", 300)
        mods = tmp_path / "mods.json"
        mods.write_text(sdk.mods_file({"recipe": {"packs": defaults, "files": [entry]}})["text"], encoding="utf-8")
        fresh = served.open()
        fresh.set_input_files("#iso", str(usa_iso))
        _page.until(fresh, "() => azurkit.vanilla?.release === 'usa'", 300)
        fresh.evaluate("() => document.getElementById('tab-tools').click()")
        fresh.set_input_files("#tools-mods-file", str(mods))
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
    served.context.route(f"{ORIGIN}/content-test/**", content)
    row = """document.querySelector('.cpack[data-community="hard"]')"""
    hp = """document.getElementById("player_max_hp.starting_hp")"""
    locked = f"() => {hp}.value === '150' && {hp}.disabled && {hp}.closest('.pack').classList.contains('owned')"
    try:
        page = served.open()
        page.evaluate("() => localStorage.setItem('azurkit.content_source', './content-test/')")
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
        page.set_input_files("#iso", str(usa_iso))
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
        page.goto(link)
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
    address, the page's CSP's ``connect-src 'self'``) come under the species, beside Content from (D1035), each marked
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
        served.requests.append((request.method, request.url, request.post_data_buffer))
        rel = urllib.parse.urlsplit(request.url).path.removeprefix("/content-test/")
        route.fulfill(path=str(repo / rel)) if (repo / rel).is_file() else route.fulfill(status=404, body="")
    served.context.route(f"{ORIGIN}/content-test/**", source)
    try:
        page = served.open()
        page.evaluate("() => localStorage.setItem('azurkit.content_source', './content-test/')")
        page = served.open()
        page.set_input_files("#iso", str(usa_iso))
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
        assert [r for r in served.stray() if not r.startswith(f"GET {ORIGIN}/content-test/")] == []
        again = served.open()   # this browser's storage, the Characters tab never opened
        assert _page.until(again, """async () => !azurkit.characters.state.opened && (await azurkit.engine.call(
            "pickers", {given: {iso: null}})).community.map((e) => `${e.id} ${e.state}`).join() === "beamlord installed"
            """, 120)
    finally:
        served.close()


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
    served.context.route(f"{ORIGIN}/content-test/**", lambda route, request: route.fulfill(
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
        page.set_input_files("#iso", str(usa_iso))
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
        page.set_input_files("#iso", str(tmp_path / "not-an-image.iso"))
        _page.until(page, "() => !document.getElementById('char-refused').hidden", 180)
        assert page.evaluate(CHARS_SHOWN)[3:7] == [[True] * 4, "Choose your image to match garret4 (G4).", False, 6]
        page.set_input_files("#iso", str(usa_iso))
        assert page.evaluate(CHARS_SHOWN)[3:7] == [[True] * 4, "Reading your image…", False, 6]
        _page.until(page, "() => Boolean(azurkit.characters.state.view?.from)", 300)
        assert page.evaluate(CHARS_SHOWN)[4] == "G4 sets a number so the body matches garret4."
        index = json.loads((site / "characters" / "index.json").read_text(encoding="utf-8"))
        assert {f"characters/{index['species'][s]}.{v}.png" for s in ("garret4", "keylord") for v in ("front", "back")} <= {
            url.removeprefix(f"{ORIGIN}/") for _, url, _ in served.requests}
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
    byte for byte ``web/``'s. (A static server here: Playwright aborts a
    routed request whose address ends in ``/favicon.ico``.)"""
    with _static(site) as url:
        context = browser.new_context(service_workers="block")   # its icons, not sw.js's first visit (its own file's)
        try:
            page = context.new_page()
            page.goto(url)
            _page.check_icons(page)
        finally:
            context.close()


def test_the_pick_and_the_characters_tab_check_the_image_once_and_a_page_opened_again_keeps_its_stamp(
        browser, site, usa_iso):
    """The site's worker checks the image's build files once a File (hashed in WebCrypto, ``sdk.prime``): picking it
    and then opening the Characters tab hash them once, and a page opened again, the same File picked, hashes them no
    more (the browser keeps the last image's stamp by its name, size, lastModified and a sample of its bytes)."""
    served = Site(browser, site)

    def hashed(page) -> int:
        return sum(w.evaluate("() => self.azurkitChecks ?? 0") for w in page.workers)
    try:
        page = served.open()
        page.set_input_files("#iso", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.click(page, "tab-characters")
        _page.until(page, "() => azurkit.characters.state.view?.species.length === 178", 300)
        assert hashed(page) == 1
        page.close()
        again = served.open()
        again.set_input_files("#iso", str(usa_iso))
        _page.until(again, "() => azurkit.vanilla?.release === 'usa'", 300)
        assert hashed(again) == 0 and again.evaluate("() => azurkit.violations") == []
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
        page.set_input_files("#iso", str(usa_iso))
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
        assert sum(w.evaluate("() => self.azurkitChecks ?? 0") for w in page.workers) == 2   # the pick's, the look-alike's
    finally:
        served.close()


# The bottom bar's progress as the page shows it, each change: [the bar's value (null: a moving stripe), its line],
# or null while it is hidden
BARS = """() => {
    globalThis.bars = [];
    const look = () => {
        const seen = document.getElementById("progress-row").hidden ? null
            : [document.getElementById("progress").getAttribute("value"), document.getElementById("progress-line").textContent];
        if (JSON.stringify(seen) !== JSON.stringify(bars.length ? bars.at(-1) : null)) bars.push(seen);
    };
    new MutationObserver(look).observe(document.querySelector("footer"), { subtree: true, childList: true,
                                                                            characterData: true, attributes: true });
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
    train)."""
    served = Site(browser, site)
    try:
        page = served.open()
        page.evaluate(BARS)
        page.evaluate(STILL)
        page.set_input_files("#iso", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.build(page, ["fps_unlock", "qol_skip_logo"])
        _page.built(page)
        bars = page.evaluate("() => bars")
        checked = [int(value) for value, line in filter(None, bars) if line.startswith("Checking your image")]
        assert len(checked) >= 3 and checked == sorted(checked) and checked[-1] == 100, checked
        lines = [line for _, line in filter(None, bars)]
        assert [any(line.startswith(stage) for line in lines) for stage in (
            "Reading its files", "Applying fps_unlock", "Applying qol_skip_logo", "Laying out the image")] == [True] * 4
        assert bars[-1] is None and served.stray() == []
    finally:
        served.close()
    served = Site(browser, site)   # a fresh browser checks the image again
    try:
        page = served.open()
        page.evaluate(BARS)
        page.evaluate(STILL)
        page.evaluate(CANCEL)
        page.set_input_files("#iso", str(usa_iso))
        assert _page.until(page, "() => globalThis.cancelled", 120) == ["check", True]
        _page.until(page, "() => azurkit.ready && azurkit.vanilla?.release === 'usa'", 300)
        assert page.evaluate("() => bars.at(-1)") is None and served.stray() == []
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
    works and Save waits on a build, and once built, nothing is greyed."""
    vanilla = {name for name, pack in mods.PACKS.items() if any(s.catalog()["vanilla"] is None for s in pack.sliders())}
    served = Site(browser, site)
    try:
        page = served.open()
        assert page.evaluate(GREYED) == [True, True, "Pick your image (1.) to build", "Pick your image (1.) to build",
                                         "Pick your image (1.), then build with Randomize ticked to see its spoiler.",
                                         len(vanilla)]
        page.set_input_files("#iso", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        assert page.evaluate(GREYED) == [False, True, "Save follows a build", "",
                                         "Build with Randomize ticked to see its spoiler.", 0]
        _page.build(page, ["fps_unlock"])
        _page.built(page)
        _page.until(page, "() => azurkit.ready", 120)   # a worker that replaces the build's says "Preparing the engine…"
        assert page.evaluate(GREYED)[:4] == [False, False, "", ""] and served.stray() == []
    finally:
        served.close()


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
        page.set_input_files("#iso", str(usa_iso))
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


def test_the_data_tab_edits_reverts_and_undoes_before_an_image(browser, site, usa_iso):
    """Step 4.7a (D986, D979): with no image the Data tab shows the Player
    view of the config.xbr AzurKit ships, Starting HP's cell marked ⚠ while
    its pack is ticked; an edit there is the engine's set operation, the
    cell tinted ● with its vanilla value in its note, counted, kept for the
    build and named in the Patches tab; a value the cell can't hold is one
    red line, the engine's words; Undo, Redo and the cell's Revert move the
    edits; unticking the pack takes its ⚠ off. Its line says the edits wait
    for the image; once one is picked, Build's config.xbr is CPython's of
    the same recipe, the D28 conflict named. Two edits typed before the
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
        page.set_input_files("#iso", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla")
        assert page.evaluate(DATA_LINES)[3] == f"{waiting}."
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
        cleared = f"""async () => {{   // the worker busy with three grids, so the edit's answer comes after the Clear
            for (let i = 0; i < 3; i++) {{
                azurkit.engine.call("data", {{ given: {{ what: "table", table: "critters_damage" }} }}); }}
            ({DATA_EDIT})(["settings_foo", "initial hp", "600"]);
            await new Promise((r) => setTimeout(r, 0));
            ({DATA_PRESS})("Clear edits"); }}"""
        fuel = answer("initial fuel", "501", [op])["ops"]
        for script, want in ((two, answer("initial fuel cap", "502", fuel)["ops"]),
                             (cleared, [answer("initial hp", "600", [])["op"]])):
            depth = page.evaluate("() => azurkit.data.state.undo.length")
            page.evaluate(script)
            assert _page.until(page, f"() => azurkit.data.state.undo.length === {depth + 2} && azurkit.xbr") == want
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
        page.set_input_files("#iso", str(usa_iso))
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


HEARD = """(() => {   // what the page's workers post that the page shows nowhere: each start, digest and write
    const Real = Worker;
    Object.assign(globalThis, { starts: [], digests: [], writes: [] });
    globalThis.Worker = class extends Real {
        constructor(...args) {
            super(...args);
            this.addEventListener("message", ({ data }) => {
                if (data?.type === "ready") starts.push(data.start);
                if (data?.type === "digest") digests.push(data);
                if (data?.type === "wrote") writes.push(data);
            });
        }
    };
})();"""
"""An init script: the page's workers' starts in ``starts``, their digests (DIGESTS) in ``digests``, their build
files' writes (WROTE) in ``writes``."""
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
        page.set_input_files("#iso", str(usa_iso))
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


def test_a_later_worker_starts_from_the_first_ones_snapshot_also_grown_and_builds_as_cpython(browser, site, usa_iso,
                                                                                            tmp_path):
    """R2.10: the first worker of a wheel starts cold and keeps its heap's
    snapshot, and the next starts from it, not from the fallback, whose
    catch would hide a restore that throws; that worker's build is CPython's.
    A heap grown past Pyodide's initial memory restores too (the grow hook;
    stock Pyodide throws there)."""
    served = Site(browser, site, tmp_path / "profile")   # persistent: WebKit's ephemeral storage refuses a big heap's put
    try:
        served.context.add_init_script(HEARD)
        first = served.open()
        _page.until(first, SNAPSHOT_KEPT, 60)
        again = served.open()
        assert first.evaluate("() => starts[0]") == "cold" and set(again.evaluate("() => starts")) == {"snapshot"}
        again.set_input_files("#iso", str(usa_iso))
        _page.until(again, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.build(again, ["fps_unlock"], {"fps_unlock": {"target_fps": "120"}})
        built = _built(again)
        made, report = sdk.image({"iso": str(usa_iso), "packs": again.evaluate("() => azurkit.sent")})
        assert (built["report"], built["segments"]) == (report, _signature(made))
        again.evaluate(SNAPSHOT_GONE)
        first.close()
        again.close()

        worker = (site / "worker.mjs").read_text(encoding="utf-8")
        imports = 'IMPORTS = "import azurkit\\n'
        assert worker.count(imports) == 1
        served.context.route("**/worker.mjs", lambda route: route.fulfill(
            body=worker.replace(imports, f"{imports}import sys\\nsys.azurkit_grown = bytearray(8 << 20)\\n"),
            content_type="text/javascript"))
        grew = served.open()
        _page.until(grew, SNAPSHOT_KEPT, 60)
        after = served.open()
        assert grew.evaluate("() => starts[0]") == "cold" and set(after.evaluate("() => starts")) == {"snapshot"}
    finally:
        served.close()


STUB_ENGINES = """(() => {
    const { catalog, view, drawn } = %s, made = globalThis.made = [], later = [];
    globalThis.held = false;
    const pickers = (worker, m) => worker.say({ type: "reply", call: m.call, reply: { ...view, character: m.given.character },
                                                heap: 2 ** 28 });
    globalThis.release = () => {
        held = false;
        for (const [worker, m] of later.splice(0)) pickers(worker, m);
    };
    globalThis.Worker = class {
        constructor() {
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
"""The site's engines as stubs that load at once and answer pickers (held until ``release()``) and a body's own
pictures (``drawn``): ``made`` holds each with what it ``got``, its ``stopped``; the test answers each reshape's preview
with ``say``. Left unanswered, the page's preview of the chosen model (sent whenever its first draw comes before
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


def test_the_saved_file_is_the_image_cpython_builds_and_opens_back_into_its_recipe(browser, site, usa_iso):
    """Every pack on the USA image: Save downloads ``<stem> (AzurKit).iso``,
    whose size and sha256 are those of CPython's image of the same recipe.
    Picked as the image, that build shows as an AzurKit build
    (``sdk.open_build``), and Load its recipe ticks every pack again."""
    served = Site(browser, site)
    try:
        page = served.open()
        page.set_input_files("#iso", str(usa_iso))
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
            page.set_input_files("#iso", str(saved))
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
            page.set_input_files("#iso", str(usa_iso))
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
    """D979, D980, D1053: Firefox's Blob is made after the build's answer (the Response held here), Save greyed and named
    with a bar of its own, which a worker's record doesn't take over. So in every browser a click's download and check
    start in its tick."""
    held = """() => { const real = Response.prototype.blob;
        Response.prototype.blob = function () {
            if (this.url) return real.call(this);   // a fetch's, not the page's own Blob's
            return new Promise((go) => { globalThis.release = go; }).then(() => real.call(this));
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
        page.set_input_files("#iso", str(usa_iso))
        _page.build(page, [])
        _page.until(page, "() => azurkit.build && azurkit.ready", 300)
        if browser.browser_type.name == "firefox":
            assert page.evaluate("""() => { const save = document.getElementById('save');
                return [save.disabled, save.title, document.getElementById('progress-row').hidden]; }""") == [
                True, f"{ready}…", False]
            page.evaluate("() => workers[0].onmessage({ data: { type: 'progress', stage: 'read', label: 'Other', percent: 5 } })")
            _page.until(page, f"() => {line}.startsWith('{ready}')")
            assert page.evaluate("() => document.getElementById('progress').hasAttribute('value')") is False
            page.evaluate("() => globalThis.release()")
        _page.built(page)
        with page.expect_download(timeout=600_000) as caught:
            assert page.evaluate("() => { document.querySelector('#save').click(); return azurkit.saveCheck; }") == "running"
        assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
        caught.value.delete()
    finally:
        served.close()


def test_a_private_window_keeps_the_plain_blob_its_save_reads(browser, site, usa_iso, tmp_path):
    """D1057: in Firefox's private window ``Response.blob()`` stays in memory, so the Blob of few parts would hold more
    than the plain one (7.2 GiB against 4.8): there the page makes none, and the Save holds."""
    prefs = {"firefox_user_prefs": {"browser.privatebrowsing.autostart": True}} if browser.browser_type.name == "firefox" else {}
    served = Site(browser, site, tmp_path / "profile", **prefs)
    try:
        page = served.open()
        page.evaluate("""() => { const real = Response.prototype.blob; globalThis.made = 0;
            Response.prototype.blob = function () { globalThis.made += !this.url; return real.call(this); }; }""")
        page.set_input_files("#iso", str(usa_iso))
        _page.build(page, [])
        _page.built(page)
        with page.expect_download(timeout=600_000) as caught:
            page.evaluate("() => document.querySelector('#save').click()")
        assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck") == "held"
        assert page.evaluate("() => globalThis.made") == 0
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
        page.set_input_files("#iso", str(image))
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


def test_an_image_changed_between_its_pick_and_the_build_fails_the_build_or_its_save(browser, site, usa_iso, tmp_path):
    """D35: a byte of a level, outside what the seed's build reads and patches, changed after the pick and before Build.
    The changed level's sha is hashed from that File, so the build's own number agrees with it: Firefox reads the new bytes
    silently and builds, and only the release's sha of the level fails its Save; WebKit and Chromium refuse the read."""
    image = tmp_path / usa_iso.name
    if subprocess.run(["cp", "-c", str(usa_iso), str(image)], capture_output=True).returncode:
        shutil.copyfile(usa_iso, image)
    image.chmod(0o644)   # a clone keeps the source's read-only mode
    with iso.Reader(image) as r:
        level = max(generator.sections(generator.prepare({"seed": "2"}, {}), r).values(), key=lambda view: view.size)
    at = level.size // 2
    while level.holds(at, at + 1):
        at += 4096
    served = Site(browser, site)
    try:
        page = served.open()
        page.set_input_files("#iso", str(image))
        _page.until(page, "() => azurkit.vanilla?.release === 'usa'", 300)
        _page.click(page, "tab-randomizer")
        _page.until(page, "() => azurkit.rando.view")
        _page.click(page, "rando-on")
        _page.fill(page, "rando-seed", "2")
        with open(image, "r+b") as f:
            f.seek(level.start + at)
            byte = f.read(1)
            f.seek(level.start + at)
            f.write(bytes([byte[0] ^ 1]))
        page.evaluate("() => { azurkit.build = null; document.querySelector('#build').click(); }")
        if _page.until(page, "() => azurkit.build ? 'built' : document.querySelector('#status').classList.contains('error') "
                             "&& 'refused'", 900) == "built":
            _page.built(page)
            _page.until(page, "() => azurkit.ready", 300)
            page.evaluate("() => document.querySelector('#save').click()")
            failed = _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck")
            assert failed.startswith("Save failed: your image changed since you picked it")
        assert page.evaluate("() => [azurkit.build, document.querySelector('#status').classList.contains('error')]") == [
            None, True]
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
        page.set_input_files("#iso", str(usa_iso))
        _page.build(page, [])
        _page.built(page)
        _page.until(page, "() => azurkit.ready", 300)
        with page.expect_download(timeout=600_000) as caught:
            page.evaluate("() => document.querySelector('#save').click()")
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
    of its share string. The page remembers the tab (D915) until Reset to
    defaults unticks it. No CSP violation, no request but GETs of the
    site's files."""
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
        page.set_input_files("#iso", str(usa_iso))
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
        _page.click(page, "share")
        link = _page.until(page, "() => azurkit.link")
        recipe = {"packs": page.evaluate("() => azurkit.sent"), "randomizer": {"seed": "2", "settings": defaults}}
        assert link == f"{ORIGIN}/{sdk.preset_encode(recipe, report)}"
        loaded = served.context.new_page()
        loaded.goto(link)
        _page.until(loaded, "() => globalThis.azurkit?.loaded && !azurkit.rando.load && azurkit.rando.view")
        assert loaded.evaluate(TAB)[:2] == [True, "2"]
        assert loaded.evaluate("() => document.querySelector('#randomizer .on .mark').textContent") == "●"
        _page.click(loaded, "share")
        assert _page.until(loaded, "() => azurkit.link") == f"{ORIGIN}/{sdk.preset_encode(recipe)}"
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
        page.set_input_files("#iso", str(europe_iso))
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
        page.goto(f"{ORIGIN}/{sdk.preset_encode(recipe)}")
        _page.until(page, "() => globalThis.azurkit?.loaded && !azurkit.rando.load && azurkit.rando.view", 120)
        page.set_input_files("#iso", str(usa_iso))
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
        page.goto(f"{ORIGIN}/{sdk.preset_encode(recipe)}")
        _page.until(page, "() => globalThis.azurkit?.loaded", 120)
        page.set_input_files("#iso", str(usa_iso))
        page.evaluate("() => document.querySelector('#build').click()")
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
    last answer's; Load settings… takes a settings file's settings (D144)."""
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
        page.set_input_files("#rando-load", str(tmp_path / "settings.toml"))
        _page.until(page, "() => !azurkit.rando.load && document.getElementById('rando-ceiling').value === '3'", 120)
        assert _page.until(page, SETTLED, 120)["settings"] == given
        assert box("storage") == [True, False, "6 of 6 · up to Standard"]   # a loaded setting's groups show

        packs = mods.normalize(on)
        loaded = served.context.new_page()
        loaded.goto(f"{ORIGIN}/{sdk.preset_encode({'packs': packs, 'randomizer': {'seed': '7'}})}")
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
    return [Number(s.value), [...s.options].map((o) => [Number(o.value), o.textContent, !o.disabled, o.title]),
            document.getElementById("rando-difficulty-line").textContent]; }"""


def test_seed_difficulty_greys_what_the_settings_cant_ask_moves_down_with_them_and_the_tracker_says_what_a_seed_needs(
        browser, site, tmp_path):
    """Step 4.3sd-b (D1031, D1037-D1039; its design's 1.4 and 4.2): the
    tab's four levels read the engine's answer, each greyed where it can't
    be asked, with the chosen level's line and why the first greyed one is;
    a level moves down, saying so, when an edit takes it off offer, and
    stays through one that doesn't; a share string's level sets the select
    both ways, a loaded one that greys there kept and said; the tracker's
    line under the head is the engine's, each step-up's third only with
    Spoiler on."""
    on = mods.normalize({name: {} for name, pack in mods.PACKS.items() if pack.default_on})
    defaults = sdk.catalog()["randomizer"]["defaults"]

    def table(tier, ceiling, level=0, **rest):
        return defaults | {"movement_tier": tier, "skip_ceiling": ceiling, **rest} \
            | ({"seed_difficulty": level} if level else {})

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
    served.context.route(f"{ORIGIN}/art/**", lambda route: route.fulfill(status=404, body=""))
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.until(page, SETTLED, 120)
        assert page.evaluate(LEVELS)[0] == 0   # Any, D1039
        _page.click(page, "rando-on")
        for tier, ceiling, offered in (("hard", 3, [0, 2, 3]), ("frame_perfect", 4, [0, 2, 3, 4]), ("standard", 2, [0, 2]),
                                       ("standard", 0, [0]), ("hard", 0, [0, 2, 3])):
            choose(movement=tier, ceiling=ceiling)
            level, levels, line = page.evaluate(LEVELS)
            answer = engine(tier, ceiling)["difficulty"]["levels"]
            assert level == 0 and levels == answer and [row[0] for row in levels if row[2]] == offered
            assert line == " ".join([answer[0][3], *[row[3] for row in answer if not row[2]][:1]])

        choose(movement="frame_perfect", ceiling=4)
        view = choose(difficulty=3)
        assert view["share"] == engine("frame_perfect", 4, 3)["share"] and view["settings"]["seed_difficulty"] == 3
        assert page.evaluate(LEVELS)[2] == engine("frame_perfect", 4, 3)["difficulty"]["levels"][2][3]
        pick = next(skip["id"] for skip in view["skips"] if skip["ceiling"] is True)
        page.evaluate("(id) => document.querySelector(`#rando-skips input[data-skip='${id}']`).click()", pick)
        assert _page.until(page, SETTLED, 120)["share"] \
            == engine("frame_perfect", 4, 3, skip_override={pick: False})["share"]   # asked again at the level kept
        _page.click(page, "rando-clear")
        _page.until(page, SETTLED, 120)
        assert choose(movement="standard", ceiling=2)["share"] == engine("standard", 2, 2)["share"]
        level, _, line = page.evaluate(LEVELS)
        assert level == 2 and line.startswith("Moved down from Hard. ")
        assert choose(ceiling=0)["share"] == engine("standard", 0)["share"]
        level, _, line = page.evaluate(LEVELS)
        assert level == 0 and line.startswith("Moved down from Standard. ")
        # A group's tick lifts what Seed difficulty offers (D1061), and its untick moves the level down, no refusal
        click = "() => document.querySelector('#rando-groups input[data-group=bounds]').click()"
        page.evaluate(click)
        view = _page.until(page, SETTLED, 120)
        top = max(row[0] for row in view["difficulty"]["levels"] if row[2])
        assert top > 0 and view["settings"]["skip_override"] == dict.fromkeys(
            sorted(p["id"] for g in view["groups"] if g["id"] == "bounds" for p in g["picks"]), True)
        assert choose(difficulty=top)["settings"]["seed_difficulty"] == top
        page.evaluate(click)
        view = _page.until(page, SETTLED, 120)
        assert view["share"] == engine("standard", 0)["share"] and page.evaluate(LEVELS)[0] == 0
        assert page.evaluate(LEVELS)[2].startswith("Moved down from ") and page.evaluate(WARNED) == [""]
        choose(ceiling=2)
        assert not page.evaluate(LEVELS)[2].startswith("Moved")

        share = engine("hard", 3, 3)["share"]
        view = typed(share, 3)
        assert view["share"] == share and view["settings"]["seed_difficulty"] == 3
        assert page.evaluate("() => document.getElementById('rando-movement').value") == "hard"
        share = engine("standard", 0, 2)["share"]
        view = typed(share, 2)
        level, levels, line = page.evaluate(LEVELS)
        assert view["share"] == share and level == 2 and not levels[1][2]   # a loaded level that greys here stays
        assert engine("standard", 0, 2)["difficulty"]["note"] in line

        doc = sdk.plan({"seed": "page", "settings": table("hard", 3, 3)})   # a plan no other test tracks: the tracker is kept
        (tmp_path / "shaped.json").write_text(json.dumps(doc), encoding="utf-8")
        _page.click(page, "rando-view-tracker")
        assert page.evaluate("() => document.getElementById('track-requires').hidden")
        page.set_input_files("#track-open", str(tmp_path / "shaped.json"))
        _page.until(page, f"() => azurkit.tracker.state.view?.head.sha256 === {json.dumps(doc['sha256'])} && ({TRACKED})()", 300)
        shown = """() => [document.getElementById("track-head").textContent, document.getElementById("track-requires").textContent,
                          document.getElementById("track-requires").hidden]"""
        head, spoiled = sdk.tracker({"plan": doc})["head"], sdk.tracker({"plan": doc, "spoiler": True})["head"]["requires"]
        thirds = ", ".join(spoiled["thirds"])
        assert page.evaluate(shown) == [head["text"], head["requires"]["text"], False] and thirds not in head["requires"]["text"]
        _page.click(page, "track-spoiler")
        _page.until(page, f"() => azurkit.tracker.state.view.head.requires.thirds && ({TRACKED})()", 300)
        assert page.evaluate(shown) == [head["text"], spoiled["text"], False] and f": {thirds}" in spoiled["text"]
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


# Each message the page posts to a worker, by its type (an init script: before the page's own)
ASKED = """(() => {
    const post = Worker.prototype.postMessage;
    globalThis.asked = [];
    Worker.prototype.postMessage = function (message, ...rest) {
        globalThis.asked.push(message?.type);
        return post.call(this, message, ...rest);
    };
})();"""
WORLD_SHOWN = """() => [azurkit.tracker.state.view, azurkit.tracker.map.level,
    [...document.getElementById("track-body").children].filter((n) => !n.hidden).map((n) => n.id),
    document.getElementById("track-empty").hidden, azurkit.tracker.map.pictures.map((p) => [p.name, p.bitmap.width,
    p.bitmap.height]), asked.filter((t) => ["tracker", "plan", "art", "art_world"].includes(t))]"""


def _png_size(png: bytes) -> list[int]:
    return [int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")]


def test_the_site_shows_the_trackers_shipped_maps_with_no_image_and_no_engine_call(browser, site, tmp_path):
    """Step 4.3f (D961): the Tracker view shows Modkit's world map, every
    level's picture on it, as soon as it shows, with no image picked and no
    plan tracked: the page reads the pictures the site ships (``art/``,
    which ``tests/test_art.py`` holds to Modkit's pixels and to the
    tracker's drawing) and asks its engine nothing for them; its hint says
    a level opens once a seed is tracked. A tracked plan's level shows its
    own map, each floor from the same files. No CSP violation, no request
    but GETs of the site's files."""
    shipped = site / "art" / tracking.ART_VERSION
    entry = json.loads((shipped / "maps.json").read_text(encoding="utf-8"))["levels"]["e6"]
    served = Site(browser, site)
    served.context.add_init_script(script=ASKED)
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        _page.until(page, "() => Boolean(azurkit.tracker.map.pictures?.[0]?.bitmap)", 60)
        assert page.evaluate(WORLD_SHOWN) == [None, None, ["track-maps"], False,
                                              [["world", *_png_size((shipped / "world.png").read_bytes())]], []]
        read = [url.removeprefix(f"{ORIGIN}/") for _, url, _ in served.requests if "/art/" in url]
        assert {url for url in read if "icons" in url} == {"art/icons.css", f"art/{tracking.ART_VERSION}/icons.png"}
        assert [url for url in read if "icons" not in url] == [
            "art/index.json", f"art/{tracking.ART_VERSION}/maps.json", f"art/{tracking.ART_VERSION}/world.png"]
        hint = "() => document.getElementById('map-hint').textContent"
        assert page.evaluate(hint) == "Track a seed to open a level's map. Scroll to zoom, drag to pan."
        (tmp_path / "plan.json").write_text(json.dumps(_profile("default")), encoding="utf-8")
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running", 300)
        assert page.evaluate(hint) == "Click a level to open its map. Scroll to zoom, drag to pan."
        calls = page.evaluate(_perf.CALLS)["calls"]   # the worker's, in the page for the perf gate's native assert
        assert calls["kernel"] > 0 and calls["twin"] == 0, calls
        page.evaluate("() => azurkit.tracker.map.show('e6', true)")
        _page.until(page, "() => azurkit.tracker.map.pictures.every((p) => p.bitmap)", 60)
        assert page.evaluate("() => azurkit.tracker.map.pictures.map((p) => [p.name, p.bitmap.width, p.bitmap.height])"
                             ) == [[name, *_png_size((shipped / f"{name}.png").read_bytes())] for name in entry["floors"]]
        _page.check_csp(page)
        assert served.stray() == []
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
        return [url.removeprefix(f"{ORIGIN}/art/{v}/detail/") for _, url, _ in served.requests if "/detail/" in url]
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        (tmp_path / "plan.json").write_text(json.dumps(_profile("default")), encoding="utf-8")
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
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
    served.context.route(f"{ORIGIN}/art/**", lambda route: route.fulfill(status=404, body=""))   # no maps: the grid
    try:
        page = served.open()
        _page.click(page, "tab-randomizer")
        _page.click(page, "rando-view-tracker")
        assert page.evaluate("() => [document.getElementById('rando-settings').hidden, "
                             "document.getElementById('tracker').hidden]") == [True, False]
        for name in ("default", "max"):
            doc = _profile(name)
            (tmp_path / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
            page.set_input_files("#track-open", str(tmp_path / f"{name}.json"))
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


def test_a_cancel_during_the_trackers_first_view_shows_no_stage_of_the_stopped_worker(browser, site, usa_iso, tmp_path):
    """Step 4.3 train: a Build and its Cancel while the Tracker's first view
    of an opened plan reads the world map stop the site's worker. The view's
    ask is sent again to the worker that replaces it, and until that worker
    is ready the bottom bar shows no value: never the stopped worker's stage
    ("Reading the world map… 50 %", or with its exits' note, 4.3m's fold),
    which nothing runs. It hides once the view is shown."""
    served = Site(browser, site)
    try:
        page = served.open()
        page.set_input_files("#iso", str(usa_iso))
        _page.until(page, "() => azurkit.vanilla?.release === 'usa' && azurkit.ready && !azurkit.asks.size", 300)
        _page.click(page, "tab-randomizer")
        _page.until(page, f"() => ({SETTLED})() && !azurkit.asks.size", 300)   # the tab's read: the view's is the newest
        _page.click(page, "rando-view-tracker")
        doc = _profile("default")
        (tmp_path / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, "() => [...azurkit.asks.values()].some((a) => a.kind === 'tracker'"   # the stage, its exits'
                          " && a.record?.label?.startsWith('Reading the world map'))", 300)   # note folded in or not
        page.evaluate(BUILD_CANCEL)
        _page.until(page, f"() => azurkit.tracker.state.view?.head.sha256 === {json.dumps(doc['sha256'])}"
                          f" && ({TRACKED})()", 300)
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
    """A page at :data:`ORIGIN` that is a bare document (no app.mjs: no
    engine of its own), every other path served from ``root``."""
    context = browser.new_context()

    def serve(route, request) -> None:
        if request.url.startswith("blob:"):   # the page's own blob: (WebKit routes them; Chromium doesn't)
            return route.continue_()
        path = urllib.parse.unquote(urllib.parse.urlsplit(request.url).path).lstrip("/")
        if not path:
            return route.fulfill(body=WORKERS_BARE, content_type="text/html")
        file = (root / path).resolve()
        if not request.url.startswith(f"{ORIGIN}/") or not file.is_relative_to(root.resolve()) or not file.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(path=str(file), content_type=_page.content_type(file.name))

    context.route("**/*", serve)
    page = context.new_page()
    page.goto(f"{ORIGIN}/")
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
    F builds; past the 5 GiB tally B neither works nor stays, and kept
    bytes are freed; Cancel answers at once and demotes a listed build to
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
        page.set_input_files("#iso", str(usa_iso))
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
    served.context.route(f"{ORIGIN}/content-test/**", source)
    try:
        served.open().evaluate("() => localStorage.setItem('azurkit.content_source', './content-test/')")
        page = served.open()
        page.set_input_files("#iso", str(usa_iso))
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
    it does a crashed page's."""
    recipe = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
              "character": {"species": "keylord"}}
    made, report = sdk.image(recipe | {"iso": str(usa_iso)})
    served = Site(browser, site, tmp_path / "profile")
    try:
        served.context.add_init_script(HEARD)
        worker = (site / "worker.mjs").read_text(encoding="utf-8")
        served.context.route("**/worker.mjs", lambda route: route.fulfill(
            body=WROTE + worker, content_type="text/javascript"))
        page = served.context.new_page()
        page.goto(f"{ORIGIN}/{sdk.preset_encode(recipe)}")
        _page.until(page, "() => globalThis.azurkit?.loaded", 120)
        page.set_input_files("#iso", str(usa_iso))
        page.evaluate("() => document.querySelector('#build').click()")
        built = _built(page)
        assert built == _as_cpython(built, report, made)
        writes = page.evaluate("() => writes")
        assert writes and not [w for w in writes if w["copy"]]
        name = page.evaluate("() => azurkit.build.out")
        assert name in page.evaluate(BUILD_FILES)
        _page.click(page, "tab-tools")
        _page.until(page, """() => [...document.querySelectorAll("#tools-storage td")]
                                 .some((td) => td.textContent.startsWith("Built images"))""", 60)
        other = served.open()   # its load's sweep
        assert name in other.evaluate(BUILD_FILES)
        _page.tick(page, ["fps_unlock"])   # a change: the build is forgotten
        _page.until(page, f"async () => !(await ({BUILD_FILES})()).includes({json.dumps(name)})", 60)
        page.evaluate("() => document.querySelector('#build').click()")
        _page.built(page)
        name = page.evaluate("() => azurkit.build.out")
        with page.expect_download(timeout=600_000) as caught:
            _page.click(page, "save")
        _page.tick(page, ["fps_unlock"], {"fps_unlock": {"target_fps": "120"}})   # forgotten, but saved
        assert name in page.evaluate(BUILD_FILES)
        assert _page.until(page, "() => azurkit.saveCheck !== 'running' && azurkit.saveCheck", 600) == "held"
        page.close()
        # no page holds it once its lock is gone, which a closed page's may not be yet as close() returns (Linux's
        # Chromium: the file outlived the reload's one sweep, run 41521288667)
        _page.until(other, f"async () => !(await navigator.locks.query()).held.some((l) => l.name === {json.dumps(name)})",
                    60)
        other.reload()
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


def test_a_character_built_again_at_a_later_visit_is_dressed_from_what_this_browser_kept_as_cpython_dresses_it(
        browser, site, usa_iso, tmp_path):
    """D1067 (D1015's store on the site): a character's first build keeps its dress in this browser (azurkit-dress, by
    the build's hint), and the same build at a later visit is dressed from it (its bar says so; the body's files aren't
    read again) and is the newest kept again, past a hint kept after it (the least recently built go first), each
    CPython's image."""
    recipe = {"packs": {name: {} for name, pack in mods.PACKS.items() if pack.default_on},
              "character": {"species": "keylord"}}
    made, report = sdk.image(recipe | {"iso": str(usa_iso)})
    served = Site(browser, site, tmp_path / "profile")
    try:
        for visit in range(2):
            page = served.context.new_page()
            page.goto(f"{ORIGIN}/{sdk.preset_encode(recipe)}")
            _page.until(page, "() => globalThis.azurkit?.loaded", 120)
            page.evaluate(BARS)
            page.set_input_files("#iso", str(usa_iso))
            page.evaluate("() => document.querySelector('#build').click()")
            built = _built(page)
            assert built == _as_cpython(built, report, made)
            lines = [line for _, line in filter(None, page.evaluate("() => bars"))]
            assert [any(line.startswith(stage) for line in lines) for stage in DRESSED] == [not visit, bool(visit)], lines
            if not visit:   # kept after the answer; then a hint kept after it
                hint, = _page.until(page, f"() => ({KEPT_DRESSES})().then((hints) => hints.length === 1 && hints)", 120)
                page.evaluate(KEPT_DRESSES, [hint, "later"])
            else:
                assert _page.until(page, f"() => ({KEPT_DRESSES})().then((hints) => hints[0] === 'later' && hints)",
                                   120) == ["later", hint]
            page.close()
    finally:
        served.close()


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
