"""Driving the page (``web/``) in headless Chromium and WebKit, for the
site's tests (``tests/test_site.py``) and the app's (``tests/test_hosts.py``).

Chromium's headless shell never fires ``requestAnimationFrame`` on this
machine (sandboxed or not), so Playwright's actionability waits never end,
and ``wait_for_function`` would need eval, which the page's CSP refuses:
these click through the DOM (``element.click()`` runs the page's own
handlers) and poll with ``page.evaluate``."""

from __future__ import annotations

import hashlib
import http.server
import time
from pathlib import Path

from azurkit.app import content_type

WEB = Path(__file__).resolve().parent.parent / "web"
ICONS = {"favicon.ico": "16x16 32x32 48x48", "favicon-32.png": "32x32"}   # the favicon (D892): the mark, free

class Static(http.server.SimpleHTTPRequestHandler):
    """A static host: the tests' servers answer each file with the app's type for it, never the registry's guess."""

    def guess_type(self, path) -> str:
        return content_type(str(path))


def until(page, js: str, timeout: float = 600):
    """``js``'s value once it is truthy."""
    end = time.monotonic() + timeout
    while not (value := page.evaluate(js)):
        assert time.monotonic() < end, f"timed out: {js}"
        time.sleep(0.2)
    return value


def fill(page, field: str, text: str) -> None:
    """Type ``text`` into the page's text field ``#<field>``."""
    page.evaluate("""([field, text]) => {
        const box = document.getElementById(field);
        box.value = text;
        box.dispatchEvent(new Event("input"));
    }""", [field, text])


def slide(page, pack: str, slider: str, text: str) -> list[str]:
    """Type ``text`` into ``pack``'s ``slider`` box, which its pack's tick
    has unlocked (D907); its track's min, max and value, and the box's
    value."""
    return page.evaluate("""([id, text]) => {
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
    page.evaluate("""(packs) => {
        for (const box of document.querySelectorAll("#packs input[data-pack]")) {
            if (box.checked !== packs.includes(box.dataset.pack)) box.click();
        }
    }""", packs)
    for pack, sliders in (values or {}).items():
        for slider, text in sliders.items():
            page.evaluate("""([id, text]) => {
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
    page.evaluate("() => document.querySelector('#build').click()")


def click(page, button: str) -> None:
    """Click the page's button ``#<button>``."""
    page.evaluate("(id) => document.getElementById(id).click()", button)


def ticked(page) -> dict[str, dict[str, str]]:
    """Each ticked pack in the catalog's order (the page groups them by
    category, Step 4.1h), with its sliders' boxes as they read (an L3
    toggle's ``"1"`` on, ``"0"`` off)."""
    return page.evaluate("""() => {
        const rows = Object.fromEntries([...document.querySelectorAll("#packs .pack")].map((i) => [i.dataset.pack, i]));
        return Object.fromEntries(azurkit.packs.packs.map((pack) => rows[pack.name])
            .filter((item) => item.querySelector("input[data-pack]").checked)
            .map((item) => [item.dataset.pack, Object.fromEntries([...item.querySelectorAll("input[data-slider]")]
                .map((box) => [box.dataset.slider, box.type === "checkbox" ? String(Number(box.checked)) : box.value]))]));
    }""")


def marked(page) -> list[str]:
    """What the page marks ● (``pack`` for a tick, ``pack.slider`` for a value)."""
    return page.evaluate("""() => [...document.querySelectorAll("#packs .mark")].filter((m) => m.textContent === "●")
        .map((m) => m.closest(".l3, .slider")?.querySelector("input[data-slider]").id ?? m.closest(".pack").dataset.pack)""")


def built(page) -> dict:
    """The build's report once the page has it (the page's error fails)."""
    done = until(page, """() => azurkit.build ? "built" : document.querySelector("#status").classList.contains("error")
                               && document.querySelector("#status").textContent""")
    assert done == "built", done
    return page.evaluate("() => azurkit.build.report")


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
    page.goto(url, wait_until="commit")
    unrun, classic, *shown = until(page, FIRST, 120)
    assert (unrun, classic, len(held)) == (True, True, 1)
    held[0].fallback()
    until(page, "() => globalThis.azurkit?.ready", 120)
    return shown


def check_csp(page) -> None:
    """No CSP violation in the page (or its worker), and a CSP with no ``'unsafe-…'`` but ``'wasm-unsafe-eval'``."""
    assert page.evaluate("() => azurkit.violations") == []
    assert "'unsafe-" not in page.evaluate("() => document.head.firstElementChild.content").replace(
        "'wasm-unsafe-eval'", "")


def check_icons(page) -> None:
    """The page links the favicon (:data:`ICONS`), and its host serves each
    file as an image, byte for byte the checkout's ``web/`` one."""
    got = page.evaluate("""async () => Promise.all([...document.querySelectorAll('link[rel="icon"]')].map(
        async (link) => {
            const reply = await fetch(link.href, { cache: "no-store" });
            return [link.getAttribute("href"), link.getAttribute("sizes"), reply.status,
                    reply.headers.get("Content-Type"), [...new Uint8Array(await reply.arrayBuffer())]];
        }))""")
    assert [[href, sizes, status, (kind or "").startswith("image/"), hashlib.sha256(bytes(data)).hexdigest()]
            for href, sizes, status, kind, data in got] == [
        [name, sizes, 200, True, hashlib.sha256((WEB / name).read_bytes()).hexdigest()] for name, sizes in ICONS.items()]
