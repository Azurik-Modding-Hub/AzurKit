"""The site's service worker (D1013, Step 4.3z): ``web/sw.js``, with the
release ``scripts/web_tools.py``'s ``site()`` lists in it, keeps that
release whole in one cache, each file checked against the list's sha256,
serves the page, its modules and its engine from it, isolates what it serves
(COOP, COEP, CORP and the page's CSP) and holds an update until the page
takes it. Here on small sites of its own that ``site()`` writes (a page that
starts as the site's page is to start, an engine that reads ``host.json``
and fetches the wheel by its integrity, as the site's worker does), served
on 127.0.0.1 (a secure context; Playwright's routing doesn't see a service
worker's own requests) with GitHub Pages' ``max-age=600``, in Chromium,
WebKit and Firefox."""

from __future__ import annotations

import contextlib
import functools
import hashlib
import http.server
import json
import re
import shutil
import threading
import time
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError

from scripts import web_tools
from tests import _page

WEB = Path(__file__).resolve().parent.parent / "web"
META = re.search(r'<meta http-equiv="Content-Security-Policy"[^>]*>', (WEB / "index.html").read_text()).group(0)
CSP = web_tools.CSP.search(META).group(1)
WHEEL = "azurkit-0-py3-none-any.whl"
PAGE = f"""<!doctype html>
<html lang="en">
<head>
{META}
<meta charset="utf-8">
<title>{{label}}</title>
<script type="module" src="page.mjs"></script>
</head>
<body></body>
</html>
"""
# The page's start under the worker, as web/app.mjs's main() is to take it (the hub's turn): register sw.js; on a page
# it doesn't control, wait for its release to be kept and active and reload once (a sessionStorage guard; a failed
# install, which sw.js posts, runs the page as it is); then the engine, a module worker from its own URL. sw.* drive
# it for the tests.
START = """const sw = navigator.serviceWorker;
const loads = Number(sessionStorage.getItem("loads") ?? 0) + 1;
sessionStorage.setItem("loads", String(loads));
const ask = (worker, message) => new Promise((done) => {
  const channel = new MessageChannel();
  channel.port1.onmessage = ({ data }) => done(data);
  worker.postMessage(message, [channel.port2]);
});
const engine = () => new Promise((done) => {
  const worker = new Worker("engine.mjs", { type: "module" });
  worker.onmessage = ({ data }) => done(data);
  worker.onerror = (e) => { e.preventDefault(); done({ error: "the engine didn't start" }); };
});
const HEADERS = ["cross-origin-opener-policy", "cross-origin-embedder-policy", "cross-origin-resource-policy",
                 "content-security-policy"];
const outcome = () => new Promise((done) => {   // the next install's, as sw.js posts it: "installed" or "failed"
  sw.addEventListener("message", ({ data }) => ["installed", "failed"].includes(data?.type) && done(data.type));
  setTimeout(done, 20000, "none");
});
sw.startMessages();
globalThis.sw = {
  engine,
  update: async () => {   // the registration looks for a new release: its install's outcome
    const [reg, told] = [await sw.getRegistration(), outcome()];
    await reg.update();
    return told;
  },
  check: async () => {   // the page's own check (the hub's, every 30 min): its answer, and a found release's outcome
    const told = outcome(), answer = await ask(sw.controller, { type: "check" });
    return { ...answer, told: answer.update ? await told : "none" };
  },
  take: async () => {   // the update line's Reload: the waiting release takes over, and the page reloads on it
    const reg = await sw.getRegistration(), reload = () => location.reload();
    if (!reg.waiting) return { type: "reload", ok: false, others: null };   // not shown yet (Firefox shows it late)
    sw.addEventListener("controllerchange", reload);
    const answer = await ask(reg.waiting, { type: "reload" });
    if (!answer.ok) sw.removeEventListener("controllerchange", reload);
    return answer;
  },
  release: () => ask(sw.controller, { type: "release" }),
  caches: async () => (await caches.keys()).filter((key) => key.startsWith("azurkit:")),
};
async function main() {
  if (!sw.controller && !sessionStorage.getItem("reloaded")) {
    const failed = new Promise((done) => sw.addEventListener("message", ({ data }) => data?.type === "failed" &&
      done()));
    await sw.register("sw.js");
    if (await Promise.race([sw.ready.then(() => true), failed.then(() => false)])) {
      sessionStorage.setItem("reloaded", "1");
      return location.reload();
    }
  }
  const reply = await fetch("host.json");
  globalThis.probe = { page: document.title, loads, isolated: crossOriginIsolated,
                       controller: sw.controller?.scriptURL ?? null, engine: await engine(),
                       headers: Object.fromEntries(HEADERS.map((h) => [h, reply.headers.get(h)])) };
}
main();
"""
ENGINE = """const host = await (await fetch("host.json")).json();
const wheel = await (await fetch(host.wheel, { integrity: host.integrity })).text();
postMessage({ engine: "LABEL", wheel });
"""


def listed(site: Path) -> dict:
    """The release ``site``'s ``sw.js`` lists."""
    lines = (site / web_tools.WORKER).read_text().splitlines()
    return json.loads(next(line for line in lines if line.startswith("const RELEASE =")).removeprefix("const RELEASE =")
                      .removesuffix(";"))


def _site(tmp: Path, label: str, page: str = PAGE, worker: str | None = None, content: Path | None = None) -> Path:
    """A site of release ``label`` (its page's title, its engine's and its wheel's text), ``site()``'s (with
    ``content``), ``web/sw.js`` replaced by ``worker``; Pyodide's core one file (:func:`unfetched`)."""
    root = tmp / f"root-{label}"
    (root / "web").mkdir(parents=True)
    (root / "web/index.html").write_text(page.format(label=label))
    (root / "web/page.mjs").write_text(START)
    (root / "web/engine.mjs").write_text(ENGINE.replace("LABEL", label))
    (root / "web/art/v1").mkdir(parents=True)
    (root / "web/art/v1/a map.png").write_bytes(b"a picture")   # a path with a space: URL-escaped by the page
    (root / "web/sw.js").write_text(worker if worker is not None else (WEB / "sw.js").read_text())
    (root / "pyodide").mkdir()
    (root / "pyodide/pyodide.mjs").write_text(f"// the {label} core\n")
    (built := tmp / f"wheel-{label}" / WHEEL).parent.mkdir()
    built.write_text(f"the {label} wheel")
    return web_tools.site(tmp / f"site-{label}", root, built, content)


def unfetched(mp) -> None:
    """``site()`` takes a root's own ``pyodide/`` for Pyodide's core."""
    mp.setattr(web_tools, "missing", lambda _root: [])
    mp.setattr(web_tools, "pyodide_dir", lambda root: root / "pyodide")


@pytest.fixture(scope="module")
def releases(tmp_path_factory) -> dict[str, Path]:
    """Sites of releases one, two and three (the same files at the same addresses, each its own bytes); restyled:
    one with only its page changed (one's wheel, so one's host.json); half: two's half deployed (two's sw.js and list,
    one's engine.mjs)."""
    tmp = tmp_path_factory.mktemp("releases")
    with pytest.MonkeyPatch.context() as mp:
        unfetched(mp)
        made = {label: _site(tmp, label) for label in ("one", "two", "three")}
        made["restyled"] = _site(tmp / "restyled", "one", page=PAGE.replace("<body>", "<body><p>restyled</p>"))
    made["half"] = shutil.copytree(made["two"], tmp / "site-half")
    shutil.copy2(made["one"] / "engine.mjs", made["half"] / "engine.mjs")
    return made


class Host:
    """``root`` (settable: a deploy) served on 127.0.0.1 as GitHub Pages serves it (``Cache-Control: max-age=600``),
    every answer whole (no 304), or each a 503 while ``down``; ``workers`` counts the requests for ``sw.js``."""

    def __init__(self, root: Path):
        self.root, self.down, self.workers = root, False, 0
        host = self

        class Handler(http.server.SimpleHTTPRequestHandler):
            extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript",
                              ".js": "text/javascript", ".json": "application/json"}

            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(host.root), **kwargs)

            def send_head(self):
                host.workers += self.path == f"/{web_tools.WORKER}"
                if host.down:
                    self.send_error(503)
                    return None
                del self.headers["If-Modified-Since"]
                return super().send_head()

            def end_headers(self):
                self.send_header("Cache-Control", "max-age=600")
                super().end_headers()

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@contextlib.contextmanager
def hosted(browser, root: Path):
    """A fresh browser context and the host serving ``root``."""
    host, context = Host(root), browser.new_context()
    try:
        yield host, context
    finally:
        context.close()
        host.close()


def started(page, after: int = 0, timeout: float = 60) -> dict:
    """The page's probe once it has started on a load past its tab's ``after``-th (a reload under it is waited out)."""
    end = time.monotonic() + timeout
    while True:
        with contextlib.suppress(PlaywrightError):
            if (got := page.evaluate("() => globalThis.probe ?? null")) and got["loads"] > after:
                return got
        assert time.monotonic() < end, f"the page didn't start: {page.url}"
        time.sleep(0.1)


def settled(page, host: Host, timeout: float = 30) -> None:
    """Once the browser's own update check after a first visit's reload (1 to 3 s after it, by browser) has asked for
    ``sw.js`` and ended: a deploy after it is the page's to find, as a check joined to one that read the last release's
    ``sw.js`` would answer that no release is new."""
    end = time.monotonic() + timeout
    while host.workers < 2:   # the registration's and that check's
        assert time.monotonic() < end, "the browser didn't check for an update after the page's reload"
        time.sleep(0.05)
    page.evaluate("async () => { await (await navigator.serviceWorker.getRegistration()).update(); }")


def opened(context, host: Host, path: str = "") -> tuple:
    page = context.new_page()
    page.goto(host.url + path)
    return page, started(page)


def runs(label: str) -> dict:
    """What a page of release ``label`` shows: its own page and engine, isolated."""
    return {"page": label, "isolated": True, "engine": {"engine": label, "wheel": f"the {label} wheel"}}


def shown(got: dict) -> dict:
    return {key: got[key] for key in ("page", "isolated", "engine")}


def take(page) -> dict | None:
    """The page's Reload answer, or ``None`` when the page reloaded under it (the release took over)."""
    try:
        return page.evaluate("sw.take()")
    except PlaywrightError:
        return None


def test_the_sites_worker_lists_every_file_the_site_serves_with_its_sha256(tmp_path, monkeypatch):
    """``site()`` writes ``web/sw.js`` with its release on its one
    ``RELEASE_LINE``: every file the site serves (but ``sw.js``,
    ``.nojekyll`` and ``content-source/``) with its sha256 and size, the
    page's CSP from ``web/index.html``'s meta, and a name its files decide
    (equal for the same files, new when one changes). A worker without the
    line or a page without its one CSP meta is refused by name, before the
    site's first file is written (D35)."""
    unfetched(monkeypatch)
    monkeypatch.setattr(web_tools, "content_files", lambda clone: {"manifest.json": b"{}", "packs/x/x.json": b"{}"})
    site = _site(tmp_path, "one", content=tmp_path)
    release = listed(site)
    files = {p.relative_to(site).as_posix(): p.read_bytes() for p in sorted(site.rglob("*")) if p.is_file()}
    assert {rel: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for rel, data in files.items()
            if rel not in ("sw.js", ".nojekyll") and not rel.startswith("content-source/")} == release["files"]
    assert {"art/v1/a map.png", "engine.mjs", "host.json", "index.html", "page.mjs", "pyodide/pyodide.mjs",
            WHEEL} == set(release["files"]) and "content-source/manifest.json" in files
    assert release["csp"] == CSP
    template = (WEB / "sw.js").read_text()
    assert files["sw.js"].decode() == template.replace(web_tools.RELEASE_LINE,
                                                       f"const RELEASE = {json.dumps(release, sort_keys=True)};")
    assert listed(_site(tmp_path / "again", "one"))["name"] == release["name"] != listed(_site(tmp_path, "two"))["name"]
    for fault, page, worker, says in [("no release line", PAGE, template.replace(web_tools.RELEASE_LINE, ""), "sw.js"),
                                      ("no CSP", PAGE.replace(META, ""), None, "Content-Security-Policy")]:
        with pytest.raises(SystemExit, match=says):
            _site(tmp_path / fault, "one", page=page, worker=worker)
        assert not (tmp_path / fault / "site-one").exists(), fault


def test_the_page_is_isolated_after_one_reload_and_every_later_page_at_once(browser, releases):
    """A first visit installs the release and reloads once onto it:
    controlled by ``sw.js``, cross-origin isolated (COOP and COEP), every
    answer carrying CORP and the page's CSP, the engine (a worker from its
    own URL) the release's. A second page in that browser is isolated with
    no reload."""
    with hosted(browser, releases["one"]) as (host, context):
        page, got = opened(context, host)
        assert got == {**runs("one"), "loads": 2, "controller": f"{host.url}sw.js", "headers": {
            "cross-origin-opener-policy": "same-origin", "cross-origin-embedder-policy": "require-corp",
            "cross-origin-resource-policy": "same-origin", "content-security-policy": CSP}}
        assert page.evaluate("sw.release()") == {"type": "release", "name": listed(releases["one"])["name"], "files": 7,
                                                 "cached": 7, "bytes": sum(f["size"] for f in
                                                                           listed(releases["one"])["files"].values())}
        assert opened(context, host, "index.html?again")[1]["loads"] == 1


def test_an_update_waits_until_the_page_takes_it(browser, releases):
    """A deploy found while a page runs installs beside it and waits: the
    page's own check finds one that changes only the page (``host.json``
    unchanged); a half-done deploy (a file not the list's) fails its
    install and the release before stays; a whole one waits, and while it
    does the open page's new engine and a page opened then are still the
    open release's, though the network serves the next. Reload is refused
    while another page of the site is open, naming how many."""
    with hosted(browser, releases["one"]) as (host, context):
        page, got = opened(context, host)
        assert shown(got) == runs("one")
        settled(page, host)
        restyled, one = releases["restyled"], releases["one"]
        assert (restyled / "host.json").read_bytes() == (one / "host.json").read_bytes()
        assert listed(restyled)["name"] != listed(one)["name"]
        host.root = restyled
        assert page.evaluate("sw.check()") == {"type": "checked", "update": True, "offline": False, "told": "installed"}
        host.root = releases["half"]
        assert page.evaluate("sw.update()") == "failed"
        host.root = releases["two"]
        assert page.evaluate("sw.update()") == "installed"
        assert page.evaluate("sw.engine()") == runs("one")["engine"]
        other, got = opened(context, host)
        assert shown(got) == runs("one")
        assert _page.until(other, "async () => (await navigator.serviceWorker.getRegistration()).waiting !== null", 10)
        assert other.evaluate("sw.take()") == {"type": "reload", "ok": False, "others": 1}


def test_a_page_of_the_next_release_never_runs_the_last_ones_engine(browser, releases):
    """Once the page takes the waiting release it reloads onto it whole:
    its page and engine are the new release's, the last release's cache is
    deleted, and a page opened with the host down is the new release's from
    its cache alone. With the cache cleared (the Tools tab's Clear) and the
    host on the release after, a file the page asks for again is refused,
    never that release's bytes, and kept again once the host serves its
    own."""
    with hosted(browser, releases["one"]) as (host, context):
        page, got = opened(context, host)
        settled(page, host)
        host.root = releases["two"]
        assert page.evaluate("sw.update()") == "installed"
        for _ in range(40):
            if (answer := take(page)) is None or answer["ok"]:
                break
            time.sleep(0.25)
        got = started(page, after=got["loads"])
        assert shown(got) == runs("two")
        assert page.evaluate("sw.caches()") == [f"azurkit:{host.url}:{listed(releases['two'])['name']}"]
        host.down = True
        assert shown(opened(context, host)[1]) == runs("two")
        host.down = False
        page.evaluate("async () => Promise.all((await sw.caches()).map((key) => caches.delete(key)))")
        host.root = releases["three"]
        assert page.evaluate("sw.engine()") == {"error": "the engine didn't start"}
        host.root = releases["two"]
        assert page.evaluate("sw.engine()") == runs("two")["engine"]
