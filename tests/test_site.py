"""The site (Step 4.1d1, D866): the page in ``web/`` runs the wheel under
Pyodide 314 in a module worker, unpacked without its dependencies (WEB §3,
§6.3), here in headless Chromium and in WebKit (Safari's engine, Step
4.1d3), served from the site folder
``scripts/web_tools.py`` assembles. Each ported pack's G1 case builds its
golden on both releases, and the page's build is CPython's: the same report,
and the same segments, so the Blob it saves is the image ``sdk.image`` makes;
so is a build with a slider set on the page (Step 4.1e1), whose track holds
its vanilla value and widens, never clamps, and one of config.xbr's cells
(Step 4.1e2); the saved file of every pack is that image, byte for byte, and
opens back into its recipe. A share link carries the page's recipe and loads
it into a page it opens (Step 4.1g). Under the page's CSP (no
``'unsafe-eval'``) nothing is refused, and every request is a GET of one of
the site's own files: the image never leaves the page. The page is driven as
``tests/_page.py`` says."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import urllib.parse
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.tools import mods
from scripts import web_tools
from tests import _g1, _page

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


class Site:
    """The site served to a fresh browser context at :data:`ORIGIN` from its
    folder (Playwright's routing, no server), every request logged."""

    def __init__(self, browser, root: Path):
        self.root, self.requests = root.resolve(), []
        self.context = browser.new_context(accept_downloads=True)
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
    is written as infinity with Q110's note, which the page shows. The
    slider's track holds its default and vanilla value, and a value typed
    past its hints widens it (D23, D42); once the image is picked, a slider
    at a site of the XBE shows the image's own vanilla value
    (``sdk.vanilla``), which its track holds too. No CSP violation, no
    request but GETs of the site's files. Ticking a pack that requires
    others ticks them too (``Pack.requires``), so its page builds it with
    them, and its G1 case (the pack alone) is test_packs'."""
    path = request.getfixturevalue(f"{release.name}_iso")
    golden = _g1.cases(release)
    cases = ([(name, {}, None if pack.requires else name) for name, pack in mods.PACKS.items()]
             + [("fps_unlock", {"target_fps": "120"}, None)]
             + [("enemy_damage", {k: str(v) for k, v in golden[SLID].params.items()}, SLID)]
             + [("qol_photo_mode", {"fly_speed": "1e39"}, None)])
    served = Site(browser, site)
    try:
        pages = [served.open() for _ in cases]
        assert _page.slide(pages[-3], "fps_unlock", "target_fps", "60") == ["30", "120", "60", "60"]
        assert _page.slide(pages[-3], "fps_unlock", "target_fps", "1000") == ["30", "1000", "1000", "1000"]
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
                assert page.evaluate("() => document.querySelector('#status').textContent").endswith(f"note: {note}")
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
    tick and value it changed marked ●, and no build. A link with config.xbr
    cells (``set``) loads them for the build and copies back the same link,
    and one that isn't a link is refused by name. No CSP violation, no
    request but GETs of the site's files."""
    from azurkit import __version__
    served = Site(browser, site)
    try:
        page = served.open()
        _page.tick(page, ["fps_unlock", "player_physics", "qol_memory_budget"],
                   {"fps_unlock": {"target_fps": "120"}, "player_physics": {"gravity": "4.9"}})
        _page.click(page, "share")
        link = _page.until(page, "() => azurkit.link")
        fragment = sdk.preset_encode({"packs": {"fps_unlock": {"target_fps": 120}, "player_physics": {"gravity": 4.9},
                                                "qol_memory_budget": {}}})
        assert (link, page.evaluate("() => location.hash")) == (f"{ORIGIN}/{fragment}", fragment)
        assert page.evaluate("() => document.querySelector('#link').value") == link
        loaded = served.context.new_page()
        loaded.goto(link)
        _page.until(loaded, "() => globalThis.azurkit?.loaded")
        assert _page.ticked(loaded) == _page.ticked(page)
        assert list(_page.ticked(loaded)) == ["fps_unlock", "player_physics", "qol_memory_budget"]
        assert (_page.ticked(loaded)["fps_unlock"]["target_fps"], _page.ticked(loaded)["player_physics"]["gravity"]
                ) == ("120", "4.9")
        assert sorted(_page.marked(loaded)) == sorted([
            "fps_unlock", "fps_unlock.target_fps", "player_physics", "player_physics.gravity", "qol_memory_upper64",
            "qol_memory_upper64_gpu", "qol_alloc_race"])
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
            [cell], "The loaded recipe also sets 1 config.xbr value, which each build applies."]
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
