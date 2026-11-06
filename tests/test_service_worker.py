"""The site's service worker (D1013, Step 4.3z): ``web/sw.js``, with the
release ``scripts/web_tools.py``'s ``site()`` lists in it, keeps that
release whole in one cache, each file checked against the list's sha256,
serves the page, its modules and its engine from it, isolates what it serves
(COOP, COEP, CORP and the page's CSP) and holds an update until the page
takes it. Here on small sites of its own that ``site()`` writes (a page that
registers it and reloads once onto its release, an engine that reads
``host.json`` and fetches the wheel by its integrity, as the site's worker
does), and on the site itself (``web/app.mjs`` registers it behind a first
visit), served on 127.0.0.1 (a secure
context; Playwright's routing doesn't see a service worker's own requests)
with GitHub Pages' ``max-age=600``, in Chromium, WebKit and Firefox."""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import shutil
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
# A test page's start under the worker (app.mjs registers it behind a first visit): tell the host the load it is
# (loaded?N: a GET of no listed file, so the network's, whichever release runs); register sw.js; on a page it doesn't
# control, wait for its release to be kept and active and reload once (a sessionStorage guard; a failed install, which
# sw.js posts, runs the page as it is); then the engine, a module worker from its own URL. sw.* drive it for the tests.
START = """const sw = navigator.serviceWorker;
const loads = Number(sessionStorage.getItem("loads") ?? 0) + 1;
sessionStorage.setItem("loads", String(loads));
fetch(`loaded?${loads}`).catch(() => {});
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
    every answer whole (no 304), or each a 503 while ``down``, by a server of a process of its own
    (:class:`_page.Served`): a server of this process's waited on its interpreter, and a plan or a full collection here
    held a first visit's install past 60 s on GitHub's Intel runner (run 42071325305). ``workers`` counts the requests
    for ``sw.js``."""

    def __init__(self, root: Path):
        self.served = _page.Served(root, pages=True)
        self.url = f"{self.served.url}/"

    root = property(lambda self: self.served.root, lambda self, root: setattr(self.served, "root", root))
    down = property(lambda self: self.served.down, lambda self, down: setattr(self.served, "down", down))

    @property
    def workers(self) -> int:
        return sum(path == f"/{web_tools.WORKER}" for _, path, _ in self.served.log())

    def close(self) -> None:
        self.served.close()


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
    ``sw.js`` and ended, and any install before it has ended: a deploy after it is the page's to find, as a check joined
    to one that read the last release's ``sw.js`` would answer that no release is new. So is an update joined to an
    install: its job ends a moment after the outcome it posts, and Chromium joins an update to it until then, resolved
    at once, asking the host nothing. So this asks until the host sees an update of its own, which finds what it runs
    on (the host must still serve the release last installed)."""
    end = time.monotonic() + timeout
    while host.workers < 2:   # the registration's and that check's
        assert time.monotonic() < end, "the browser didn't check for an update after the page's reload"
        time.sleep(0.05)
    asked = host.workers
    while True:
        page.evaluate("async () => { await (await navigator.serviceWorker.getRegistration()).update(); }")
        if host.workers > asked:
            return
        assert time.monotonic() < end, "the browser's install didn't end"
        time.sleep(0.05)


def opened(context, host: Host, path: str = "") -> tuple:
    page = context.new_page()
    _page.load(page, host.url + path)
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


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """The site, with this checkout's wheel."""
    return web_tools.site(tmp_path_factory.mktemp("site") / "site")


def ready(page, timeout: float = 120) -> None:
    """Once the site's page has its engine ready (a reload under it is waited out)."""
    end = time.monotonic() + timeout
    while True:
        with contextlib.suppress(PlaywrightError):
            if page.evaluate("() => globalThis.azurkit?.ready === true"):
                return
        assert time.monotonic() < end, f"the page's engine wasn't ready: {page.url}"
        time.sleep(0.2)


KEPT_ROW = """() => [...document.querySelectorAll("#tools-storage td")].map((td) => td.textContent)
  .includes("AzurKit itself, kept for offline use")"""


def test_the_sites_page_keeps_its_release_behind_a_first_visit_and_later_pages_run_isolated_on_it_offline_too(
        browser, site):
    """The site's own page (``web/app.mjs``) registers ``sw.js`` once its
    engine is ready: the first visit runs as before, uncontrolled, while the
    release is kept; a later page comes from it at once, cross-origin
    isolated, its engine's workers started from their own URLs (Firefox
    sends a blob: worker's imports past the worker), with the Tools tab's
    Storage counting the release; with the host down another starts its
    engine from the release alone."""
    with hosted(browser, site) as (host, context):
        first = context.new_page()
        _page.load(first, host.url)
        ready(first)
        assert first.evaluate("() => [crossOriginIsolated, Boolean(navigator.serviceWorker.controller)]") == [False, False]
        assert _page.until(first, "async () => Boolean((await navigator.serviceWorker.getRegistration())?.active)", 60)
        page = context.new_page()
        _page.load(page, host.url)
        ready(page)
        assert page.evaluate("() => [crossOriginIsolated, navigator.serviceWorker.controller?.scriptURL, "
                             "azurkit.violations]") == [True, f"{host.url}sw.js", []]
        assert f"{host.url}worker.mjs" in [worker.url for worker in page.workers]
        page.evaluate("() => document.getElementById('tab-tools').click()")
        assert _page.until(page, KEPT_ROW, 60)
        host.down = True
        other = context.new_page()
        _page.load(other, host.url)
        ready(other)
        assert other.evaluate("() => crossOriginIsolated")


RELOADED = 60
"""s a first visit may take to keep its release and start again on it: :func:`started`'s bound for a page's start. Here
the reload began 0.2-0.7 s after the first load at the runner's pace (``taskpolicy -b``, nice 19, 4 CPU loops); on
GitHub's Windows runner Firefox's reload once had its timeOrigin past a 5 s hold's end (run 42168608453: a late reload
or its clock, not shown)."""


def test_a_first_visit_keeps_its_release_and_reloads_on_it_while_this_process_holds_its_interpreter(
        browser, releases):
    """A first visit's install fetches its release from the host's own process (:class:`Host`), never this one: with
    this interpreter held (its GIL, as a plan or a full collection here held it, when an install past 60 s on GitHub's
    Intel runner waited on a server of this process's, run 42071325305) until the host hears the reloaded page start
    (``_page.Served.held``), the page registers ``sw.js``, the release is kept and the page reloads onto it."""
    with hosted(browser, releases["one"]) as (host, context):
        page = context.new_page()
        _page.load(page, host.url)
        heard = host.served.held("/loaded?2", RELOADED)
        got = started(page, after=1)
        assert (heard, got["loads"], got["controller"]) == (True, 2, f"{host.url}sw.js")


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


WAITING = """async () => { const reg = await navigator.serviceWorker.getRegistration();
  return await new Promise((done) => { const c = new MessageChannel(); c.port1.onmessage = ({ data }) => done(data.name);
    reg.waiting.postMessage({ type: "release" }, [c.port2]); }); }"""


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
        settled(page, host)
        host.root = releases["half"]
        assert page.evaluate("sw.update()") == "failed"
        assert _page.until(page, "async () => (await navigator.serviceWorker.getRegistration()).installing === null", 10)
        assert page.evaluate(WAITING) == listed(restyled)["name"], "the half release is waiting"
        host.root = restyled
        settled(page, host)
        host.root = releases["two"]
        assert page.evaluate("sw.update()") == "installed"
        assert page.evaluate("sw.engine()") == runs("one")["engine"]
        other, got = opened(context, host)
        assert shown(got) == runs("one")
        assert _page.until(other, "async () => (await navigator.serviceWorker.getRegistration()).waiting !== null", 10)
        assert other.evaluate("sw.take()") == {"type": "reload", "ok": False, "others": 1}


def test_a_check_waits_for_a_found_release_to_show_on_its_workers_registration(browser):
    """``registration.update()`` can resolve before the worker's own registration shows the release it found (WebKit's,
    a worker restarted after its 30 s idle, about one check in four, on every slower machine's first one too): the
    check still says so; with none found it says none, a moment later."""
    context = browser.new_context()
    try:
        answers = context.new_page().evaluate("""async (source) => {
          const check = (shows) => new Promise((done) => {
            const handlers = {}, reg = { scope: "https://x/", installing: null, waiting: null, update: async () => {
              if (shows) setTimeout(() => { reg.installing = {}; }, 300);
            } };
            new Function("self", source)({ registration: reg, addEventListener: (name, f) => { handlers[name] = f; } });
            handlers.message({ data: { type: "check" }, ports: [{ postMessage: done }] });
          });
          return [await check(true), await check(false)];
        }""", (WEB / web_tools.WORKER).read_text(encoding="utf-8"))
    finally:
        context.close()
    assert [answer["update"] for answer in answers] == [True, False]


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
