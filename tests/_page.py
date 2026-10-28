"""Driving the page (``web/``) in headless Chromium, for the site's tests
(``tests/test_site.py``) and the app's (``tests/test_hosts.py``).

Chromium's headless shell never fires ``requestAnimationFrame`` on this
machine (sandboxed or not), so Playwright's actionability waits never end,
and ``wait_for_function`` would need eval, which the page's CSP refuses:
these click through the DOM (``element.click()`` runs the page's own
handlers) and poll with ``page.evaluate``."""

from __future__ import annotations

import json
import time

from azurkit.core import gate
from scripts import gen_facts

GOLDENS = {"usa": "tests/goldens/packs.json", "europe": "tests/goldens/europe/packs.json"}


def golden(release: gate.Release) -> dict[str, dict[str, str]]:
    """The release's G1 cases: each pack's files and their sha256."""
    return json.loads((gen_facts.ORACLE / "packs" / GOLDENS[release.name]).read_text(encoding="utf-8"))


def check_g1(result: dict[str, str], cases: dict[str, dict[str, str]], pack: str) -> None:
    """A build of ``pack`` alone (its ``result``: each file it changed and
    its sha256) holds the pack's G1 files (``cases``: :func:`golden`) and no
    other file but ``filelist.txt``."""
    assert {file: result.get(file) for file in cases[pack]} == cases[pack], pack
    assert result.keys() - {"filelist.txt"} == cases[pack].keys(), pack


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
    """Type ``text`` into ``pack``'s ``slider`` box; its track's min, max
    and value, and the box's value."""
    return page.evaluate("""([id, text]) => {
        const box = document.getElementById(id), track = box.previousElementSibling;
        box.value = text;
        box.dispatchEvent(new Event("input", { bubbles: true }));
        return [track.min, track.max, track.value, box.value];
    }""", [f"{pack}.{slider}", text])


def build(page, packs: list[str], values: dict[str, dict[str, str]] | None = None) -> None:
    """Tick exactly ``packs``, type each of ``values`` (``{pack: {slider:
    text}}``) into its slider's box, and click Build (the image is picked)."""
    for pack, sliders in (values or {}).items():
        for slider, text in sliders.items():
            slide(page, pack, slider, text)
    page.evaluate("""(packs) => {
        for (const box of document.querySelectorAll("#packs input[data-pack]")) {
            if (box.checked !== packs.includes(box.dataset.pack)) box.click();
        }
        document.querySelector("#build").click();
    }""", packs)


def built(page) -> dict:
    """The build's report once the page has it (the page's error fails)."""
    done = until(page, """() => azurkit.build ? "built" : document.querySelector("#status").classList.contains("error")
                               && document.querySelector("#status").textContent""")
    assert done == "built", done
    return page.evaluate("() => azurkit.build.report")


def check_csp(page) -> None:
    """No CSP violation in the page (or its worker), and a CSP with no ``'unsafe-…'`` but ``'wasm-unsafe-eval'``."""
    assert page.evaluate("() => azurkit.violations") == []
    assert "'unsafe-" not in page.evaluate("() => document.head.firstElementChild.content").replace(
        "'wasm-unsafe-eval'", "")
