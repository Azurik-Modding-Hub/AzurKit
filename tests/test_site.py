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

import contextlib
import functools
import hashlib
import http.server
import json
import mimetypes
import re
import threading
import time
import urllib.parse
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.tools import data, mods
from azurkit.tools.randomizer import tracking
from azurkit.tools.randomizer.art import icons
from scripts import record_goldens, web_tools
from tests import _g1, _page
from tests.test_randomizer import TRACKER, TRACKER_MAP, _profile, shows_gems, tracker_states

ORIGIN = "https://azurkit.test"
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]
SIGNATURE = """async () => Promise.all(azurkit.build.segments.map(async (s) => s.kind !== "bytes"
    ? (s.kind === "copy" ? ["copy", s.offset, s.size] : ["zero", s.size])
    : ["bytes", s.size, [...new Uint8Array(await crypto.subtle.digest("SHA-256", s.data))]
                          .map((b) => b.toString(16).padStart(2, "0")).join("")]))"""


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """The site, with this checkout's wheel."""
    return web_tools.site(tmp_path_factory.mktemp("site") / "site")


KINDS = (".bin", ".glb", ".gltf", ".json", ".md", ".png", ".wav")
"""The content kinds the site publishes, each served as data (mime-db's types: no page, script or rendered document)."""
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
    (root / "web/index.html").write_text("the page\n")
    (clone / "index.html").write_text("planted\n")
    (clone / "packs/x/pack.json").write_text("{}\n")
    kinds = ["packs/x/pack.json", *(f"{'packs' if s == '.md' else 'sounds' if s == '.wav' else 'fx'}/x/x{s}"
                                    for s in KINDS if s != ".json")]   # each in a folder that takes it (Step S1)
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
        files = [{"path": p, "sha256": hashlib.sha256(data := (clone / p).read_bytes()).hexdigest(), "size": len(data)}
                 for p in paths]
        (clone / "manifest.json").write_text(json.dumps({"format": content.FORMAT, "schema_version": 1, "entries": [
            {"id": "x", "kind": "pack", "title": "X", "author": "A", "licence": "MIT", "version": 1, "files": files,
             "requires": []}]}))
        return web_tools.site(out, root, built, clone)

    good = site(tmp_path / "good", *kinds)
    assert sorted(p.relative_to(good / "content-source").as_posix() for p in (good / "content-source").rglob("*")
                  if p.is_file()) == sorted(["manifest.json", *kinds])
    assert all((good / "content-source" / rel).read_bytes() == (clone / rel).read_bytes() for rel in kinds)
    assert (good / "index.html").read_text() == "the page\n" and (good / ".nojekyll").read_bytes() == b""
    with pytest.raises(SystemExit, match=re.escape(bad)):
        site(tmp_path / "bad", "packs/x/pack.json", bad)
    assert not (tmp_path / "bad").exists()


class Site:
    """The site served to a fresh browser context at :data:`ORIGIN` from its
    folder (Playwright's routing, no server), every request logged."""

    def __init__(self, browser, root: Path, **options):
        self.root, self.requests = root.resolve(), []
        self.context = browser.new_context(accept_downloads=True, **options)
        self.context.route("**/*", self._serve)

    def _serve(self, route, request) -> None:
        if request.url.startswith(f"blob:{ORIGIN}/"):   # the page's own blob: (WebKit routes them; Chromium doesn't)
            return route.continue_()
        url = urllib.parse.urlsplit(request.url)
        self.requests.append((request.method, request.url, request.post_data_buffer))
        file = (self.root / (urllib.parse.unquote(url.path).lstrip("/") or "index.html")).resolve()
        if f"{url.scheme}://{url.netloc}" != ORIGIN or not file.is_relative_to(self.root) or not file.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(path=str(file), content_type=mimetypes.guess_type(file.name)[0] or "application/octet-stream")

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


SLID = "enemy_damage:enemy_damage_neutral=2,enemy_damage_weakness=0.5,enemy_damage_immune=-1"   # a G1 slider case
FPS = ("fps_unlock", {"target_fps": "120"}, None)
# player_physics' jump height and two of its L3 toggles (D909), the toggles from the page's checkboxes
FLIPPED = ("player_physics", {"jump_speed_scale": "1.5", "toggle_jump_speed_scale": "1", "toggle_gravity": "1"}, None)
UNIT = """(id) => document.getElementById(id).parentElement.querySelector(".unit").textContent"""
TRACK = """(id) => [document.getElementById(id).previousElementSibling.min,
                    document.getElementById(id).previousElementSibling.max]"""


@pytest.mark.parametrize("release", RELEASES)
def test_each_ported_pack_builds_its_g1_golden_in_each_browser(release, browser, site, request):
    """One page per pack, one with fps_unlock's slider typed to 120 FPS,
    one with enemy_damage's sliders at a G1 case's values (config.xbr's
    cells) and one with photo mode's fly speed past float32's range, built
    at once: each page's report and segments are CPython's for the values
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
    try:
        pages = [served.open() for _ in cases]
        fps = pages[cases.index(FPS)]
        _page.tick(fps, ["fps_unlock"])   # which unlocks its settings (D907)
        assert _page.slide(fps, "fps_unlock", "target_fps", "60") == ["30", "120", "60", "60"]
        assert _page.slide(fps, "fps_unlock", "target_fps", "1000") == ["30", "1000", "1000", "1000"]
        read = sdk.vanilla(str(path))
        assert {pack: set(sliders) for pack, sliders in read["packs"].items()} == {
            name: {s.name for s in pack.sliders() if s.catalog()["vanilla"] is None and release.name in pack.releases}
            for name, pack in mods.PACKS.items() if any(s.catalog()["vanilla"] is None for s in pack.sliders())}
        for (name, values, _), page in zip(cases, pages):
            page.set_input_files("#iso", str(path))
            if name in read["packs"]:
                assert _page.until(page, "() => azurkit.vanilla") == read
                for slider, value in read["packs"][name].items():
                    low, high = page.evaluate(TRACK, f"{name}.{slider}")
                    assert float(low) <= value <= float(high)
                    assert page.evaluate(UNIT, f"{name}.{slider}").endswith(f" · vanilla {value:g}")
            _page.build(page, [name], {name: values})
        for (name, values, case), page in zip(cases, pages):
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
CHARS_LAYOUT = """() => {
    const r = (el) => el.getBoundingClientRect(), tab = document.getElementById("characters");
    const [list, info] = [".chars-list", ".chars-info"].map((s) => r(document.querySelector(s)));
    const [source, reset] = ["char-source", "char-source-reset"].map((id) => r(document.getElementById(id)));
    const g4 = [...tab.querySelectorAll(".g4")];
    return [source.right <= list.right && reset.right <= list.right && Math.abs(reset.top - source.top) < 2,
            tab.scrollWidth <= tab.clientWidth && g4.length > 0 && g4.every((b) => r(b).right <= innerWidth),
            r(document.getElementById("char-back")).right <= info.right];
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
    return [...document.querySelectorAll("#packs .group")].map((group) => [group.open,
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
    checkout's LICENSE), its credits (NOTICE.md's) and its version. No CSP
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
        assert page.evaluate("""() => [...document.querySelectorAll("#packs .group")].map((group) =>
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
        assert version == f"This is AzurKit {__version__}."
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


class _Quiet(http.server.SimpleHTTPRequestHandler):
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


def test_the_characters_tab_lists_species_variants_and_weapons_and_installs_from_the_source(
        browser, site, usa_iso, tmp_path):
    """The Characters tab (Step 4.3d, D877, D913) on the site: with the image picked it lists the 178 species the
    player can wear, the 73 untested greyed, each row's grade read without colour too (its mark and its words as its
    title); Azurik-Custom-Content's entries (its source served from the site's own
    address, the page's CSP's ``connect-src 'self'``) come first, each marked community; Install of an entry whose
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
            assert page.evaluate(CHARS_LAYOUT) == [True] * 3, width
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
        assert page.evaluate("() => azurkit.violations") == []
        assert [r for r in served.stray() if not r.startswith(f"GET {ORIGIN}/content-test/")] == []
        again = served.open()   # this browser's storage, the Characters tab never opened
        assert _page.until(again, """async () => !azurkit.characters.state.opened && (await azurkit.engine.call(
            "pickers", {given: {iso: null}})).community.map((e) => `${e.id} ${e.state}`).join() === "beamlord installed"
            """, 120)
    finally:
        served.close()


CHARS_SHOWN = """() => [document.querySelectorAll("#char-species .model").length,
    document.getElementById("char-count").textContent, ["char-front", "char-back"].map((id) => document.getElementById(id)
    .getContext("2d").getImageData(0, 0, 160, 160).data.some((v, i) => i % 4 === 3 && v > 0)),
    [...document.querySelectorAll("#char-numbers .g4")].map((b) => b.disabled), document.getElementById("char-g4-note")
    .textContent, document.getElementById("char-weapon").disabled, document.getElementById("char-weapon").textContent,
    asked.filter((t) => ["preview", "match"].includes(t))]"""


def test_the_characters_tab_shows_every_species_and_its_pictures_before_an_image(browser, site, tmp_path, usa_iso):
    """Step 4.3f (D961, D979): before an image is picked the Characters tab
    lists all 178 species the player can wear, the 73 untested among them,
    with Garret's two pictures, and a click on another shows its own at
    once: the site's shipped answer and pictures (``tests/test_characters.py``
    holds them to the images and to the app's draw), no engine call drawing
    them. G4 and the Weapon box stay greyed, saying the image is needed, and
    say so again once the engine refuses a file that is no image; the image
    picked after it, they say it is being read until its answer (Step 4.3m:
    never "Choose your image" meanwhile). No CSP violation, no request but
    GETs of the site's files."""
    served = Site(browser, site)
    served.context.add_init_script(script=ASKED)
    try:
        page = served.open()
        _page.click(page, "tab-characters")
        _page.until(page, "() => document.getElementById('char-preview-note').textContent.startsWith('From the')", 60)
        assert page.evaluate(CHARS_SHOWN) == [
            178, "178 species, 73 not yet tested · Choose your image to build, and to see each model's weapons.",
            [True, True], [True] * 4, "Choose your image to match garret4 (G4).", True,
            "Choose your image to see its weapons", []]
        page.evaluate("() => document.querySelector('#char-species .model[data-model=\"keylord\"]').click()")
        _page.until(page, "() => azurkit.characters.state.view?.chosen.name === 'keylord'", 120)
        assert page.evaluate(CHARS_SHOWN)[2:] == [[True, True], [True] * 4, "Choose your image to match garret4 (G4).",
                                                  True, "Choose your image to see its weapons", []]
        (tmp_path / "not-an-image.iso").write_bytes(bytes(64 * 1024))
        page.set_input_files("#iso", str(tmp_path / "not-an-image.iso"))
        _page.until(page, "() => !document.getElementById('char-refused').hidden", 180)
        assert page.evaluate(CHARS_SHOWN)[3:7] == [[True] * 4, "Choose your image to match garret4 (G4).", True,
                                                   "Choose your image to see its weapons"]
        page.set_input_files("#iso", str(usa_iso))
        assert page.evaluate(CHARS_SHOWN)[3:7] == [[True] * 4, "Reading your image…", True, "Reading your image…"]
        _page.until(page, "() => Boolean(azurkit.characters.state.view?.from)", 300)
        assert page.evaluate(CHARS_SHOWN)[4] == "G4 sets a number so the body matches garret4."
        index = json.loads((site / "characters" / "index.json").read_text(encoding="utf-8"))
        assert {f"characters/{index['species'][s]}.{v}.png" for s in ("garret4", "keylord") for v in ("front", "back")} <= {
            url.removeprefix(f"{ORIGIN}/") for _, url, _ in served.requests}
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


def test_kept_content_reaches_the_engine_only_at_a_content_path_holding_its_installed_sha256(browser, site):
    """What this browser keeps installed (IndexedDB, which any script of the site's origin can write) is written into
    the engine's content folder file by file only where its path is one a manifest may list and installed.json holds
    its sha256: a planted ``../`` key never reaches Pyodide's file system (one once wrote over the engine's own
    packages), nor does a file whose bytes aren't the record's; each is left out with a line naming it."""
    recipe = json.dumps({"beamlord": {}}).encode()   # lists beamlord under its entry wherever it is read
    planted = "../content/variants/planted/variant.json"   # variants/planted/variant.json, were it written
    escaped = "../../../lib/python3.14/site-packages/azurkit_planted/__init__.py"
    installed = {name: {"version": 1, "source": "", "files": {f"variants/{name}/variant.json": hashlib.sha256(recipe).hexdigest()}}
                 for name in ("kept", "planted", "swapped")}
    files = {"variants/kept/variant.json": recipe, planted: recipe, escaped: b"raise SystemExit",
             "variants/swapped/variant.json": b'{"beamlord": 1}'}
    served, lines = Site(browser, site), []
    served.context.on("console", lambda m: lines.append(m.text) if m.text.startswith("AzurKit left out") else None)
    try:
        page = served.open()
        listed = page.evaluate("""async ([files, installed]) => {
            azurkit.engine.content(Object.fromEntries(Object.entries(files).map(([k, v]) => [k, new Uint8Array(v)])),
                                   installed);
            const reply = await azurkit.engine.call("pickers", {given: {iso: null}});
            return Object.fromEntries(reply.community.map((e) => [e.id, e.variants.map((v) => v.name)]));
        }""", [{k: list(v) for k, v in files.items()}, installed])
        assert listed == {"kept": ["beamlord"], "planted": [], "swapped": []}
        end = time.monotonic() + 30
        while len(lines) < 3 and time.monotonic() < end:   # the worker's lines, as Playwright delivers them
            page.wait_for_timeout(200)
        assert sorted(re.sub(r"[0-9a-f]{12}", "#", line) for line in lines) == sorted(
            [f"AzurKit left out kept content: path {path!r} isn't a file under variants/, clips/, sounds/, fx/, packs/"
             for path in (planted, escaped)]
            + ["AzurKit left out kept content: variants/swapped/variant.json's sha256 # isn't installed.json's"])
    finally:
        served.close()


def test_the_site_serves_the_favicon_the_page_links(browser, site):
    """The page links the favicon (the mark, D892), and the site's folder,
    served as a static host serves it, gives each file the page asks for,
    byte for byte ``web/``'s. (A static server here: Playwright aborts a
    routed request whose address ends in ``/favicon.ico``.)"""
    with _static(site) as url:
        context = browser.new_context()
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
    worker's answer ends the check before it, whatever the clock says, and so
    does a Cancel during the check (its worker stopped). The clock is stopped
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
        _page.until(page, "() => azurkit.ready", 120)   # the worker that replaces the stopped one
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
    the same recipe, the D28 conflict named. No CSP violation, no request
    but GETs of the site's files."""
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
        page.evaluate(DATA_EDIT, [*cell, "500"])
        shown = _page.until(page, f"() => azurkit.data.state.ops.length && ({DATA_CELL})({json.dumps(cell)})")
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


RETIRING = """async (source) => {
    const code = source.slice(source.indexOf("const KEEP = "),
                              source.indexOf("\\n}\\n", source.indexOf("function siteEngine(")) + 3);
    const workers = [];
    class Fake {
        constructor() { this.got = []; this.stopped = false; workers.push(this); }
        postMessage(message) { this.got.push(message.type); }
        terminate() { this.stopped = true; }
    }
    const fakes = { state: { violations: [], asks: new Map() }, asking: () => 0, answered: () => {}, posted: () => {},
                    unchecked: () => {},
                    location: { href: "https://azurkit.test/" }, Blob: function () {}, Worker: Fake,
                    URL: Object.assign(function (url) { this.href = url; },
                                       { createObjectURL: () => "blob:", revokeObjectURL: () => {} }) };
    const engine = new Function(...Object.keys(fakes), `${code}\\nreturn siteEngine;`)(...Object.values(fakes))(
        { ready: () => {}, built: () => {}, refused: () => {}, failed: () => {} });
    const [first] = workers;
    first.onmessage({ data: { type: "ready", catalog: {}, version: "0" } });
    engine.build(null, {}, [], { seed: "2" }, null);
    first.onmessage({ data: { type: "built", report: { plan: { sha256: "0" } }, heap: 2 ** 31 } });   // past KEEP
    const preview = engine.call("preview", {}, { once: true });
    const seen = [first.got.includes("preview")];
    first.onmessage({ data: { type: "spoiled", text: "" } });
    const next = workers[1];
    seen.push(first.stopped, next.got.includes("preview"));
    next.onmessage({ data: { type: "ready", catalog: {}, version: "0" } });
    next.onmessage({ data: { type: "reply", call: 1, reply: { drawn: true } } });
    seen.push(next.got.includes("preview"), await preview);
    const match = engine.call("match", {}, { once: true });
    next.onerror({ preventDefault: () => {}, message: "" });
    return [...seen, await match, workers.length];
}"""
"""The site's engine (``web/app.mjs``'s ``siteEngine``) on fake workers: a seed's build whose heap the page doesn't
keep, a Characters preview asked before its spoiler arrives, the next worker's answer, then a G4 match that worker
was sent before it stopped: [the preview sent to the retiring worker, that worker stopped, the preview sent to the
next before it loads, after, the preview's answer, the match's, the workers started]."""


def test_a_characters_ask_made_while_a_seeds_worker_retires_waits_for_the_next_and_only_a_sent_one_is_refused(browser):
    """Step 4.3m (the review's D1): a worker the page doesn't keep after a
    seed's build stays until it has sent the spoiler; a once ask (a
    Characters preview or a G4 match) made meanwhile is never sent to it,
    and the worker that replaces it answers it. Only a once ask a stopped
    worker was sent is refused, as out of memory."""
    page = browser.new_page()
    try:
        assert page.evaluate(RETIRING, (web_tools.ROOT / "web" / "app.mjs").read_text(encoding="utf-8")) == [
            False, True, False, True, {"drawn": True},
            {"refused": "The engine stopped before it answered (out of memory?): try again, or use the desktop app"}, 3]
    finally:
        page.close()


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
            assert got == (f"{usa_iso.stem} (AzurKit).iso", made.size, made.sha256())
            _page.tick(page, [])
            page.set_input_files("#iso", str(saved))
            opened = _page.until(page, "() => azurkit.opened")
            assert opened == json.loads(json.dumps(sdk.open_build(made)))
            assert page.evaluate("() => document.querySelector('#picked').textContent").startswith(
                "◆ AzurKit build · USA · 17 packs")
            _page.click(page, "load-build")
            assert list(_page.ticked(page)) == list(mods.PACKS)
        finally:
            download.delete()
        assert served.stray() == []
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
        _page.click(page, "spoiler-view")
        assert _page.until(page, "() => !document.getElementById('spoiler').hidden "
                                 "&& document.getElementById('spoiler').textContent", 120) == report["spoiler"]
        with page.expect_download(timeout=60_000) as caught:
            _page.click(page, "spoiler-save")
        assert (caught.value.suggested_filename, Path(caught.value.path()).read_text(encoding="utf-8")) == (
            f"{usa_iso.stem} (AzurKit) spoiler.txt", report["spoiler"])
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
        assert _built(page) == {"report": report, "segments": _signature(made)}
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
        assert _built(page) == {"report": report, "segments": _signature(made)}
    finally:
        served.close()


# The tab's rows that stay vanilla in v1 ([ticked, greyed] each); "vanilla 10" beside its box ([right of it, on its
# line]); the skip list's rows and whether it shows them all (no inner scroll).
RANDO_SHOWN = """() => {
    const box = document.getElementById("rando-cost").getBoundingClientRect(), skips = document.getElementById("rando-skips");
    const note = document.getElementById("rando-cost-note").getBoundingClientRect();
    return [[...document.querySelectorAll("#rando-items input[data-vanilla]")].map((b) => [b.checked, b.disabled]),
            [note.left >= box.right, note.top < box.bottom && note.bottom > box.top],
            [skips.querySelectorAll(".skip").length, skips.scrollHeight <= skips.clientHeight]];
}"""
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
    what the base game places (Modkit's); a ticked skip group turns on its
    skips rated at or below the Movement tier (D258), and Load settings…
    takes a settings file's settings (D144)."""
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
        assert page.evaluate(RANDO_SHOWN) == [[[False, True]] * kept, [True, True], [len(view["skips"]), True]]
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
        page.evaluate("() => document.querySelector('#rando-groups input[data-group=storage]').click()")
        view = _page.until(page, SETTLED, 120)
        storage = {p["id"] for g in view["groups"] if g["id"] == "storage" for p in g["picks"] if max(p["levels"]) <= 2}
        defaults = sdk.catalog()["randomizer"]["defaults"]
        assert storage and view["settings"] == defaults | {"skip_override": dict.fromkeys(sorted(storage), True)}
        assert view["share"] == sdk.randomizer_settings({"settings": view["settings"], "packs": mods.normalize(on)})["share"]
        assert page.evaluate("""() => [...document.querySelectorAll("#rando-skips .skip")]
            .filter((r) => r.querySelector(".by").textContent === "group").map((r) => r.querySelector("input").dataset.skip)
            .sort()""") == sorted(storage)
        given = defaults | {"skip_ceiling": 3, "movement_tier": "hard", "exclude_categories": ["gems"]}
        (tmp_path / "settings.toml").write_text(sdk.randomizer_settings({"settings": given})["file"], encoding="utf-8")
        page.set_input_files("#rando-load", str(tmp_path / "settings.toml"))
        _page.until(page, "() => !azurkit.rando.load && document.getElementById('rando-ceiling').value === '3'", 120)
        assert _page.until(page, SETTLED, 120)["settings"] == given

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
        assert [url.removeprefix(f"{ORIGIN}/") for _, url, _ in served.requests if "/art/" in url] == [
            "art/index.json", f"art/{tracking.ART_VERSION}/maps.json", f"art/{tracking.ART_VERSION}/world.png"]
        hint = "() => document.getElementById('map-hint').textContent"
        assert page.evaluate(hint) == "Track a seed to open a level's map. Scroll to zoom, drag to pan."
        (tmp_path / "plan.json").write_text(json.dumps(_profile("default")), encoding="utf-8")
        page.set_input_files("#track-open", str(tmp_path / "plan.json"))
        _page.until(page, "() => azurkit.tracker.state.view && !azurkit.tracker.state.running", 300)
        assert page.evaluate(hint) == "Click a level to open its map. Scroll to zoom, drag to pan."
        page.evaluate("() => azurkit.tracker.map.show('e6', true)")
        _page.until(page, "() => azurkit.tracker.map.pictures.every((p) => p.bitmap)", 60)
        assert page.evaluate("() => azurkit.tracker.map.pictures.map((p) => [p.name, p.bitmap.width, p.bitmap.height])"
                             ) == [[name, *_png_size((shipped / f"{name}.png").read_bytes())] for name in entry["floors"]]
        _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


TRACKED = "() => !azurkit.tracker.state.running && !azurkit.tracker.state.queue.length && azurkit.tracker.state.view"
# The maps' model of the view shown (web/mapview.mjs's marks() for each level and badges(); the icons the engine draws),
# as one canonical JSON text: TRACKER_MAP's
ICONS = [f"icons/{name}" for name in [*icons.ICONS, *icons.DRAWN, *icons.keys()]]
MAP_MODEL = """async ([levels, icons]) => {
    const { marks, badges } = await import("./mapview.mjs");
    const view = azurkit.tracker.state.view, have = (name) => icons.includes(`icons/${name}`);
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
        assert not seen[0][0] and [s for s in seen if not s[0] and s[1] is not None] == [], seen
        assert seen[-1][1:] == [None, None] and served.stray() == [], seen
    finally:
        served.close()
