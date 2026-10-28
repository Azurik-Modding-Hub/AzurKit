"""The site (Step 4.1d1, D866): the page in ``web/`` runs the wheel under
Pyodide 314 in a module worker, unpacked without its dependencies (WEB §3,
§6.3), here in headless Chromium and in WebKit (Safari's engine, Step
4.1d3), served from the site folder
``scripts/web_tools.py`` assembles. Each ported pack's G1 case builds its
golden on both releases, and the page's build is CPython's: the same report,
and the same segments, so the Blob it saves is the image ``sdk.image`` makes;
so is a build with a slider set on the page (Step 4.1e1), whose track holds
its vanilla value and widens, never clamps; the saved file of all five
packs is that image, byte for byte. Under the
page's CSP (no ``'unsafe-eval'``) nothing is refused, and every request is a
GET of one of the site's own files: the image never leaves the page. The
page is driven as ``tests/_page.py`` says."""

from __future__ import annotations

import hashlib
import mimetypes
import urllib.parse
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.tools import mods
from scripts import web_tools
from tests import _page

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
        return [f"{method} {url}" for method, url, body in self.requests
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


@pytest.mark.parametrize("release", RELEASES)
def test_each_ported_pack_builds_its_g1_golden_in_each_browser(release, browser, site, request):
    """One page per pack, and one with fps_unlock's slider typed to 120
    FPS, built at once: each page's report and segments are CPython's for
    the values it sent, and the packs at their defaults hold the G1
    golden's files (and only ``filelist.txt`` besides). The slider's track
    holds its default and vanilla value, and a value typed past its hints
    widens it (D23, D42). No CSP violation, no request but GETs of the
    site's files."""
    path = request.getfixturevalue(f"{release.name}_iso")
    golden = _page.golden(release)
    cases = [(name, {}) for name in mods.PACKS] + [("fps_unlock", {"target_fps": "120"})]
    served = Site(browser, site)
    try:
        pages = [served.open() for _ in cases]
        assert _page.slide(pages[-1], "fps_unlock", "target_fps", "60") == ["30", "120", "60", "60"]
        assert _page.slide(pages[-1], "fps_unlock", "target_fps", "1000") == ["30", "1000", "1000", "1000"]
        for (name, values), page in zip(cases, pages):
            page.set_input_files("#iso", str(path))
            _page.build(page, [name], {name: values})
        for (name, values), page in zip(cases, pages):
            built, sent = _built(page), page.evaluate("() => azurkit.sent")
            assert sent == {name: {s.name: float(values.get(s.name, s.default)) for s in mods.PACKS[name].sliders()}}
            made, report = sdk.image({"iso": str(path), "packs": sent})
            if not values:
                _page.check_g1(built["report"]["result"], golden, name)
            assert (built["report"], built["segments"]) == (report, _signature(made)), (name, values)
            _page.check_csp(page)
        assert served.stray() == []
    finally:
        served.close()


def test_the_saved_file_is_the_image_cpython_builds(browser, site, usa_iso):
    """All five packs on the USA image: Save downloads ``<stem> (AzurKit).iso``,
    whose size and sha256 are those of CPython's image of the same recipe."""
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
        finally:
            download.delete()
        assert served.stray() == []
    finally:
        served.close()
