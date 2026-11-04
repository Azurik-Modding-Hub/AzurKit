"""Driving the page (``web/``) in headless Chromium and WebKit, for the
site's tests (``tests/test_site.py``) and the app's (``tests/test_hosts.py``).

Chromium's headless shell never fires ``requestAnimationFrame`` on this
machine (sandboxed or not), so Playwright's actionability waits never end,
and ``wait_for_function`` would need eval, which the page's CSP refuses:
these click through the DOM (``element.click()`` runs the page's own
handlers) and poll with ``page.evaluate``, each call bounded (:func:`within`):
Playwright gives an evaluate, a page's opening and its close no bound of their
own (D1072)."""

from __future__ import annotations

import asyncio
import hashlib
import http.server
import sys
import time
from pathlib import Path

from azurkit.app import content_type

WEB = Path(__file__).resolve().parent.parent / "web"
ICONS = {"favicon.ico": "16x16 32x32 48x48", "favicon-32.png": "32x32"}   # the favicon (D892): the mark, free
STALL = 120
"""s a browser may leave one call that has no bound of its own unanswered (an evaluate, past its wait's timeout; a
page's opening or close), as long as a page has to start its engine (``test_site.Site.open``): past it the wait fails
by name with the page's state (D1072). Windows' Firefox once left an evaluate unanswered 2 h 10 min, its processes gone
and Playwright's driver unaware, until the tier's stall watch ended the run (run 41610020282)."""
HEAR = 10
"""s each read of a stalled page's state may take: a page that answers gives it in ms."""
PROBE = 10
"""s the probe of a stalled call's browser (its cookies) may take: a browser that answers gives them in ms. A bound of
its own, so a test that cuts :data:`HEAR` for a state read that must go unread leaves this one whole (GitHub's Intel
Mac runner took over 1 s for a page's read, run 41666183947)."""


class Static(http.server.SimpleHTTPRequestHandler):
    """A static host: the tests' servers answer each file with the app's type for it, never the registry's guess."""

    def guess_type(self, path) -> str:
        return content_type(str(path))


def saved_name(browser, name: str) -> str:
    """A download named ``name``'s ``suggested_filename``: WebKit on Linux gives each space in it as ``_``
    (run 41328160086's ``usa_(AzurKit)_spoiler.txt``); the page names it the same in every browser."""
    return name.replace(" ", "_") if sys.platform == "linux" and browser.browser_type.name == "webkit" else name


# What a page that timed out was waiting on (app.mjs's state): each open ask's kind, its record's stage and percent and
# its age in s; the pool's workers (workers.mjs's state(): each one's job, heap and last message with its age in ms);
# Save's check and the status line. Names and numbers only, never game bytes.
HANG = """() => {
    const s = globalThis.azurkit, now = performance.now();
    return s ? { asks: [...(s.asks?.values() ?? [])].map((a) => [a.kind, a.record?.stage ?? null, a.record?.percent ?? null,
                                                                Math.round((now - a.since) / 1000)]),
                 pool: s.pool?.state?.() ?? null, saveCheck: s.saveCheck ?? null,
                 status: document.getElementById("status")?.textContent ?? null } : null;
}"""


def _short(value, size: int = 160):
    """``value`` with each string cut to ``size`` characters (a job's key is its whole recipe)."""
    if isinstance(value, str):
        return value if len(value) <= size else f"{value[:size]}…"
    if isinstance(value, dict):
        return {k: _short(v, size) for k, v in value.items()}
    if isinstance(value, list):
        return [_short(v, size) for v in value]
    return value


def _heard(owner, call, seconds: float):
    """``call``'s answer (a coroutine of ``owner``'s Playwright object, ``owner._impl_obj``), as ``owner``'s sync call
    would give it, or TimeoutError past ``seconds``; Playwright aborts the call it cancels."""
    from playwright._impl._sync_base import mapping
    return mapping.from_maybe_impl(owner._sync(asyncio.wait_for(call, max(seconds, 0.1))))


def hang(page, last: int = 5) -> str:
    """Why a wait on ``page`` may not have ended: its :data:`HANG` state, and the last ``last`` page errors (uncaught
    exceptions and unhandled rejections) and console errors since the page opened (Playwright keeps them), each read
    in :data:`HEAR` s."""
    said = []
    for what, read in (("state", lambda: _short(_heard(page, page._impl_obj.evaluate(HANG), HEAR))),
                       ("page errors", lambda: [_short(f"{e.name}: {e.message}", 300)
                                                for e in (_heard(page, page._impl_obj.page_errors(), HEAR) or [])[-last:]]),
                       ("console errors", lambda: [_short(m.text, 300) for m in _heard(
                           page, page._impl_obj.console_messages(), HEAR) or [] if m.type == "error"][-last:])):
        try:
            said.append(f"{what}: {read()}")
        except TimeoutError:
            said.append(f"{what}: unread (no answer in {HEAR} s)")
        except Exception as error:   # a closed or crashed page: say so, and the rest
            said.append(f"{what}: unread ({_short(str(error), 200)})")
    return "\n".join(said)


def _drivers(owner) -> str:
    """The processes under ``owner``'s Playwright driver, each with its age (``scripts/ci_resources.py``'s listing,
    every OS): a browser gone from under it says it ended."""
    from scripts import ci_resources
    try:
        driver = owner._impl_obj._connection._transport._proc.pid
        return ", ".join(f"{name} {pid} ({age} s)" for _, (pid, _, age, name, _) in
                         ci_resources.tree(ci_resources.processes(), driver)) or f"none (the driver {driver} is gone)"
    except Exception as error:
        return f"unread ({_short(str(error), 200)})"


def stalled(owner, what: str, seconds: float) -> str:
    """What a call to ``owner`` (a page or a context) that went unanswered ``seconds`` s says: ``what`` it was, the
    page's state (:func:`hang`), whether its browser still answers a call of its own (its cookies, in :data:`PROBE` s)
    and the processes under its driver. A browser that answers nothing either has stopped: its Playwright connection is
    closed naming ``what``, so every later call to it fails at once by name, its module's next tests too, never a
    silent wait (D1072)."""
    page = owner if hasattr(owner, "main_frame") else None
    context = page.context if page else owner
    said = [f"no answer in {seconds:.0f} s: {_short(what)}"] + ([hang(page)] if page else [])
    try:
        _heard(context, context._impl_obj.cookies(), PROBE)
        said.append("its browser still answers")
    except TimeoutError:
        said.append(f"its browser answers nothing either (in {PROBE} s): every later call to it fails at once")
        context._impl_obj._connection.cleanup(f"the browser stopped answering: {_short(what)}")
    except Exception as error:
        said.append(f"its browser: {_short(str(error), 200)}")
    return "\n".join([*said, f"under its driver: {_drivers(context)}"])


def within(owner, call, seconds: float, what: str):
    """``call``'s answer (:func:`_heard`), or an AssertionError naming ``what`` with the page's state past ``seconds``
    (:func:`stalled`)."""
    try:
        return _heard(owner, call, seconds)
    except TimeoutError:
        raise AssertionError(stalled(owner, what, seconds)) from None


def answer(page, js: str, arg=None, seconds: float = STALL):
    """``page.evaluate(js, arg)``, unanswered for at most ``seconds`` s (:func:`within`)."""
    from playwright._impl._sync_base import mapping
    return within(page, page._impl_obj.evaluate(js, mapping.to_impl(arg)), seconds, js)


def close(page) -> None:
    """``page.close()``, in at most :data:`STALL` s (:func:`within`)."""
    within(page, page._impl_obj.close(), STALL, "the page's close")


def load(page, url: str | None = None, until: str = "load"):
    """``page.goto(url)``, or with no ``url`` ``page.reload()``, to its ``until`` (Playwright's ``wait_until``), in at
    most :data:`STALL` s (:func:`within`), not Playwright's 30 s, past which it failed naming nothing but the
    navigation (a site page's load in Firefox, run 41678038275; a reload in WebKit on 4a178cc, both on GitHub's Intel
    Mac runner): past it the failure names the page's state, whether its browser still answers and its driver's
    processes."""
    call = (page._impl_obj.reload(timeout=0, waitUntil=until) if url is None
            else page._impl_obj.goto(url, timeout=0, waitUntil=until))
    return within(page, call, STALL, "the page's reload" if url is None else f"the page's load of {url}")


def until(page, js: str, timeout: float = 600):
    """``js``'s value once it is truthy; past ``timeout`` s, a failure that says what the page was waiting on
    (:func:`hang`), and one evaluate unanswered :data:`STALL` s past it fails so too (:func:`answer`)."""
    end = time.monotonic() + timeout
    while not (value := answer(page, js, seconds=end - time.monotonic() + STALL)):
        assert time.monotonic() < end, f"timed out after {timeout} s: {js}\n{hang(page)}"
        time.sleep(0.2)
    return value


def fill(page, field: str, text: str) -> None:
    """Type ``text`` into the page's text field ``#<field>``."""
    answer(page, """([field, text]) => {
        const box = document.getElementById(field);
        box.value = text;
        box.dispatchEvent(new Event("input"));
    }""", [field, text])


def slide(page, pack: str, slider: str, text: str) -> list[str]:
    """Type ``text`` into ``pack``'s ``slider`` box, which its pack's tick
    has unlocked (D907); its track's min, max and value, and the box's
    value."""
    return answer(page, """([id, text]) => {
        const box = document.getElementById(id), track = box.previousElementSibling;
        if (box.disabled) throw new Error(`${id} is locked`);
        box.value = text;
        box.dispatchEvent(new Event("input", { bubbles: true }));
        return [track.min, track.max, track.value, box.value];
    }""", [f"{pack}.{slider}", text])


def tick(page, packs: list[str], values: dict[str, dict[str, str]] | None = None) -> None:
    """Tick exactly ``packs`` (a pack's tick links tick or untick others),
    which unlocks their settings (D907), then set each of ``values``
    (``{pack: {slider: text}}``): type it into its slider's box, or for an
    L3 toggle (D909), ``"1"`` turns it on and ``"0"`` off."""
    answer(page, """(packs) => {
        for (const box of document.querySelectorAll("#packs input[data-pack]")) {
            if (box.checked !== packs.includes(box.dataset.pack)) box.click();
        }
    }""", packs)
    for pack, sliders in (values or {}).items():
        for slider, text in sliders.items():
            answer(page, """([id, text]) => {
                const box = document.getElementById(id);
                if (box.disabled) throw new Error(`${id} is locked`);
                if (box.type !== "checkbox") {
                    box.value = text;
                    box.dispatchEvent(new Event("input", { bubbles: true }));
                } else if (box.checked !== (text === "1")) {
                    box.click();
                }
            }""", [f"{pack}.{slider}", text])


def build(page, packs: list[str], values: dict[str, dict[str, str]] | None = None) -> None:
    """:func:`tick`, then click Build (the image is picked)."""
    tick(page, packs, values)
    answer(page, "() => document.querySelector('#build').click()")


def click(page, button: str) -> None:
    """Click the page's button ``#<button>``."""
    answer(page, "(id) => document.getElementById(id).click()", button)


def ticked(page) -> dict[str, dict[str, str]]:
    """Each ticked pack in the catalog's order (the page groups them by
    category, Step 4.1h), with its sliders' boxes as they read (an L3
    toggle's ``"1"`` on, ``"0"`` off)."""
    return answer(page, """() => {
        const rows = Object.fromEntries([...document.querySelectorAll("#packs .pack")].map((i) => [i.dataset.pack, i]));
        return Object.fromEntries(azurkit.packs.packs.map((pack) => rows[pack.name])
            .filter((item) => item.querySelector("input[data-pack]").checked)
            .map((item) => [item.dataset.pack, Object.fromEntries([...item.querySelectorAll("input[data-slider]")]
                .map((box) => [box.dataset.slider, box.type === "checkbox" ? String(Number(box.checked)) : box.value]))]));
    }""")


def marked(page) -> list[str]:
    """What the page marks ● (``pack`` for a tick, ``pack.slider`` for a value)."""
    return answer(page, """() => [...document.querySelectorAll("#packs .mark")].filter((m) => m.textContent === "●")
        .map((m) => m.closest(".l3, .slider")?.querySelector("input[data-slider]").id ?? m.closest(".pack").dataset.pack)""")


def built(page) -> dict:
    """The build's report once the page has it and Save can be clicked (the page's error fails)."""
    done = until(page, """() => azurkit.build && !document.querySelector("#save").disabled ? "built"
                               : document.querySelector("#status").classList.contains("error")
                               && document.querySelector("#status").textContent""")
    assert done == "built", done
    return answer(page, "() => azurkit.build.report")


# The page as it first paints, once parsed to its foot and styled: whether app.mjs has yet to run, whether theme.js is
# a classic script in the head (so the parser runs it before it reaches the body), the theme and the ground.
FIRST = """() => {
    const ground = document.body && getComputedStyle(document.body).backgroundColor;
    return document.querySelector("footer") && ground !== "rgba(0, 0, 0, 0)" && [globalThis.azurkit === undefined,
        document.head.querySelector('script[src="theme.js"]:not([type]):not([async]):not([defer])') !== null,
        document.documentElement.dataset.theme, ground];
}"""


def first_paint(page, url: str) -> list[str]:
    """Open ``url`` in ``page`` with app.mjs held back: the theme and the
    ground the page has before its module runs, set by theme.js in the
    head, which is how it first paints (D897: a player who picked light
    never sees a dark first frame); then let app.mjs run and wait for the
    engine."""
    held = []
    page.route("**/app.mjs", lambda route: held.append(route))
    load(page, url, "commit")
    unrun, classic, *shown = until(page, FIRST, 120)
    assert (unrun, classic, len(held)) == (True, True, 1)
    held[0].fallback()
    until(page, "() => globalThis.azurkit?.ready", 120)
    return shown


def check_csp(page) -> None:
    """No CSP violation in the page (or its worker), and a CSP with no ``'unsafe-…'`` but ``'wasm-unsafe-eval'``."""
    assert answer(page, "() => azurkit.violations") == []
    assert "'unsafe-" not in answer(page, "() => document.head.firstElementChild.content").replace(
        "'wasm-unsafe-eval'", "")


def check_icons(page) -> None:
    """The page links the favicon (:data:`ICONS`), and its host serves each
    file as an image, byte for byte the checkout's ``web/`` one."""
    got = answer(page, """async () => Promise.all([...document.querySelectorAll('link[rel="icon"]')].map(
        async (link) => {
            const reply = await fetch(link.href, { cache: "no-store" });
            return [link.getAttribute("href"), link.getAttribute("sizes"), reply.status,
                    reply.headers.get("Content-Type"), [...new Uint8Array(await reply.arrayBuffer())]];
        }))""")
    assert [[href, sizes, status, (kind or "").startswith("image/"), hashlib.sha256(bytes(data)).hexdigest()]
            for href, sizes, status, kind, data in got] == [
        [name, sizes, 200, True, hashlib.sha256((WEB / name).read_bytes()).hexdigest()] for name, sizes in ICONS.items()]
