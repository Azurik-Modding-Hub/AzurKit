"""The site (Step 4.1d1, D866): the page in ``web/`` runs the wheel under
Pyodide 314 in a module worker, unpacked without its dependencies (WEB §3,
§6.3), here in headless Chromium, served from the site folder
``scripts/web_tools.py`` assembles. Each ported pack's G1 case builds its
golden on both releases, and the page's build is CPython's: the same report,
and the same segments, so the Blob it saves is the image ``sdk.image`` makes;
the saved file of all five packs is that image, byte for byte. Under the
page's CSP (no ``'unsafe-eval'``) nothing is refused, and every request is a
GET of one of the site's own files: the image never leaves the page.

Chromium's headless shell never fires ``requestAnimationFrame`` on this
machine (sandboxed or not), so Playwright's actionability waits never end,
and ``wait_for_function`` would need eval, which the CSP refuses: the tests
click through the DOM (``element.click()`` runs the page's own handlers) and
poll with ``page.evaluate``."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import time
import urllib.parse
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.tools import mods
from scripts import gen_facts, web_tools

ORIGIN = "https://azurkit.test"
GOLDENS = {"usa": "tests/goldens/packs.json", "europe": "tests/goldens/europe/packs.json"}
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
        _until(page, "() => globalThis.azurkit?.ready", 120)
        return page

    def stray(self) -> list[str]:
        """Each request that isn't a GET of a site file, with no body, at :data:`ORIGIN`."""
        files = {f"{ORIGIN}/{p.relative_to(self.root).as_posix()}" for p in self.root.rglob("*") if p.is_file()}
        return [f"{method} {url}" for method, url, body in self.requests
                if method != "GET" or body or (url if url != f"{ORIGIN}/" else f"{ORIGIN}/index.html") not in files]

    def close(self) -> None:
        self.context.close()


def _until(page, js: str, timeout: float = 600):
    end = time.monotonic() + timeout
    while not (value := page.evaluate(js)):
        assert time.monotonic() < end, f"timed out: {js}"
        time.sleep(0.2)
    return value


def _build(page, image: Path, packs: list[str]) -> None:
    """Pick ``image``, tick exactly ``packs`` and click Build."""
    page.set_input_files("#iso", str(image))
    page.evaluate("""(packs) => {
        for (const box of document.querySelectorAll("#packs input[data-pack]")) {
            if (box.checked !== packs.includes(box.dataset.pack)) box.click();
        }
        document.querySelector("#build").click();
    }""", packs)


def _built(page) -> dict:
    """The page's build once it is ready: its report and its segments
    (``["copy", offset, size]``, ``["bytes", size, sha256]``, ``["zero", size]``)."""
    done = _until(page, """() => azurkit.build ? "built" : document.querySelector("#status").classList.contains("error")
                                && document.querySelector("#status").textContent""")
    assert done == "built", done
    return {"report": page.evaluate("() => azurkit.build.report"), "segments": page.evaluate(SIGNATURE),
            "violations": page.evaluate("() => azurkit.violations"),
            "csp": page.evaluate("() => document.head.firstElementChild.content")}


def _signature(made: iso.Image) -> list[list]:
    return [["copy", p.offset, p.size] if isinstance(p, iso.Copy) else ["zero", p.size] if isinstance(p, iso.Zero)
            else ["bytes", p.size, hashlib.sha256(p.data).hexdigest()] for p in made.segments()]


@pytest.mark.parametrize("release", RELEASES)
def test_each_ported_pack_builds_its_g1_golden_in_chromium(release, chromium, site, request):
    """One page per pack, built at once: each page's report holds the G1
    golden's files (and only ``filelist.txt`` besides) and equals CPython's,
    and its segments are CPython's; no CSP violation, no request but GETs of
    the site's files."""
    path = request.getfixturevalue(f"{release.name}_iso")
    golden = json.loads((gen_facts.ORACLE / "packs" / GOLDENS[release.name]).read_text(encoding="utf-8"))
    served = Site(chromium, site)
    try:
        pages = {name: served.open() for name in mods.PACKS}
        for name, page in pages.items():
            _build(page, path, [name])
        for name, page in pages.items():
            built = _built(page)
            made, report = sdk.image({"iso": str(path), "packs": {name: {}}})
            result = built["report"]["result"]
            assert {file: result.get(file) for file in golden[name]} == golden[name], name
            assert result.keys() - {"filelist.txt"} == golden[name].keys(), name
            assert (built["report"], built["segments"]) == (report, _signature(made)), name
            assert built["violations"] == [] and "'unsafe-" not in built["csp"].replace("'wasm-unsafe-eval'", "")
        assert served.stray() == []
    finally:
        served.close()


def test_the_saved_file_is_the_image_cpython_builds(chromium, site, usa_iso):
    """All five packs on the USA image: Save downloads ``<stem> (AzurKit).iso``,
    whose size and sha256 are those of CPython's image of the same recipe."""
    served = Site(chromium, site)
    try:
        page = served.open()
        _build(page, usa_iso, list(mods.PACKS))
        _built(page)
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
