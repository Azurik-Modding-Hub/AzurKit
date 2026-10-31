"""The site's two engine workers (Step 4.3y, ``web/workers.mjs``; D1006,
D1007): F answers the page's asks and B works ahead, dropped by
``terminate()`` when the page's list changes; a click whose key is B's
finished job takes its answer, one B is still working on follows B's
records; B takes F's place only while its heap is under KEEP; one heavy job
runs at a time; the page's tally stays under its 5 GiB line. Driven first
on stub workers (each scenario's messages by hand), then once on two real
engine workers (``web/worker.mjs`` and the wheel), whose plan of one seed
is the same on both and is dropped mid-way by a change. The page is driven
as ``tests/_page.py`` says (no actionability waits, no eval)."""

from __future__ import annotations

import mimetypes
import urllib.parse
from pathlib import Path

import pytest

from scripts import web_tools
from tests import _page

ORIGIN = "https://azurkit.test"
BARE = b"<!doctype html><meta charset=utf-8><title>workers</title>"


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """The site, with this checkout's wheel."""
    return web_tools.site(tmp_path_factory.mktemp("site") / "site")


def _page_on(browser, root: Path):
    """A page at :data:`ORIGIN` that is a bare document (no app.mjs: no
    engine of its own), every other path served from ``root``."""
    context = browser.new_context()

    def serve(route, request) -> None:
        if request.url.startswith("blob:"):   # the page's own blob: (WebKit routes them; Chromium doesn't)
            return route.continue_()
        path = urllib.parse.unquote(urllib.parse.urlsplit(request.url).path).lstrip("/")
        if not path:
            return route.fulfill(body=BARE, content_type="text/html")
        file = (root / path).resolve()
        if not request.url.startswith(f"{ORIGIN}/") or not file.is_relative_to(root.resolve()) or not file.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(path=str(file), content_type=mimetypes.guess_type(file.name)[0] or "application/octet-stream")

    context.route("**/*", serve)
    page = context.new_page()
    page.goto(f"{ORIGIN}/")
    return context, page


HARNESS = """
    const { workers, canon, KEEP } = await import("/workers.mjs");
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
    """``rows``, scenarios on :data:`HARNESS`'s bare page: their ``out``."""
    context, page = _page_on(browser, web_tools.ROOT / "web")
    try:
        return page.evaluate(f"async () => {{{HARNESS}{rows}\n    return out;\n}}")
    finally:
        context.close()


ROWS = """
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
    {   // F's build past KEEP: an idle B under KEEP takes F's place (ready again) and a new B loads
        const { pool, stubs, readies, f, b } = make();
        const built = pool.ask(build(), { heavy: true });
        f.say({ type: "built", report: {}, heap: KEEP });
        await built;
        pool.ask({ type: "tracker" });
        out.promoted = [f.stopped, readies, b.tags(), stubs.length, stubs[2].role, pool.state().promoted];
    }
    {   // a busy B (a small ask beside F's build) doesn't: a new F loads; nor does a build that reports no heap leave F
        // in place
        const { pool, stubs, readies, f, b } = make();
        const built = pool.ask(build(), { heavy: true });
        pool.ask({ type: "randomizer" }, { anywhere: true });
        f.say({ type: "built", report: {}, heap: KEEP });
        await built;
        stubs[2].say({ type: "ready", n: 3 });
        const again = pool.ask(build(), { heavy: true });
        stubs[2].say({ type: "built", report: {} });
        await again;
        out.unpromoted = [f.stopped, b.stopped, stubs[2].role, stubs[2].stopped, stubs[3].role, readies,
                          pool.state().promoted];
    }
    {   // B is retired after a job past KEEP and its answer kept; a click takes it
        const { pool, stubs, f, b } = make();
        pool.want([{ key: "build k", message: build("k"), heavy: true }]);
        b.say({ type: "built", report: { size: 1 }, heap: KEEP + 1 });
        const retired = b.stopped;
        const got = await pool.ask(build("k"), { key: "build k", heavy: true });
        out.keep = [retired, stubs[2].role, got.report, pool.took(got), f.tags(), pool.state().retired];
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
        const { pool, stubs, b } = make({ heap: 3 * 2 ** 30 });
        pool.hold(2 * 2 ** 30);
        pool.want([{ key: "plan t", message: plan("t") }, { key: "build t", message: build("t"), heavy: true }]);
        const over = [b.stopped, stubs.length];
        pool.hold(2 ** 20);
        const next = stubs[2];
        next.say({ type: "ready", n: 3, heap: 2 ** 28 });
        next.say({ type: "reply", reply: { plan: "t" } });
        next.say({ type: "built", report: {}, segments: [{ kind: "bytes", data: new Uint8Array(2 ** 20) }],
                   heap: 2 ** 29 });
        const under = [next.tags(), pool.state().kept, pool.state().tally];
        pool.hold(2 * 2 ** 30);
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
        f.say({ type: "built", report: { plan: { sha256: "0" } }, heap: KEEP });   // F goes once it sends the spoiler
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
    {   // fewer than 4 cores: no B
        const { pool, stubs } = make({ cores: 2 });
        pool.want([{ key: "plan 7", message: plan("7") }]);
        out.cores = [stubs.length];
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
    doesn't drop it); another list terminates B's job; B takes F's place
    after a build past KEEP only when idle under KEEP; B is retired after a
    job past KEEP, its answer kept; F's build drops B's heavy job and B
    starts nothing beside it; a small ask that may go anywhere is B's while
    F builds; past the 5 GiB tally B neither works nor stays, and kept
    bytes are freed; Cancel answers at once and demotes a listed build to
    work ahead, which Build again follows; a once ask waits, unsent, for
    the F after a seed's build past KEEP, and a stopped worker's running
    once ask answers stopped while a plain one goes to the next F; no B
    under 4 cores. A key is canonical JSON, a File refused by name."""
    got = _on_stubs(browser, ROWS)
    gib = 2 ** 30
    assert got == {
        "asks": [["tracker"], [], ["view"], {"view": 1}, False],
        "ahead": [["plan 2"], [], {"plan": "p2"}, True, [], []],
        "following": [["logic", "fill"], {"plan": "p3"}, True, False, []],
        "dropped": [False, True, ["plan 4"], "b", ["plan 5"], [], 1],
        "promoted": [True, [1, 2], ["tracker"], 3, "b", 1],
        "unpromoted": [True, False, "f", True, "f", [1, 3], 0],
        "keep": [True, "b", {"size": 1}, True, [], 1],
        "heavy": [["build x"], ["build y"], [True, 2], False, ["build x"], 1],
        "spare": [["build"], ["randomizer"], {"share": "s"}, False],
        "tally": [[True, 2], [["plan t", "build t"], ["plan t", "build t"], 3 * gib + 2 ** 29 + 2 ** 20 + 2 ** 20],
                  True, ["plan t"]],
        "cancel": ["cancelled", False, {"size": 2}, "cancelled", True, ["build c", "tracker"], {"view": 2}, [1, 2], 1],
        "swapped": ["cancelled", {"size": 3}, True, False, ["build e"], [], [1, 2], 1, 1],
        "once": [[["build s"], True, ["preview"]], {"drawn": True}, "stopped", ["tracker"], ["tracker"], {"view": 3}],
        "cores": [1],
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


SMOKE = """async ({ seed }) => {
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
    context, page = _page_on(browser, site)
    try:
        page.evaluate(SMOKE, {"seed": "azurkit"})
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
        assert page.evaluate("() => smoke.told") == []
        page.evaluate("() => smoke.pool.close()")
    finally:
        context.close()
