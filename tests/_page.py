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
import errno
import hashlib
import http.server
import json
import subprocess
import sys
import textwrap
import time
import urllib.parse
from pathlib import Path

from azurkit.app import CONTENT_TYPES, content_type

WEB = Path(__file__).resolve().parent.parent / "web"
ICONS = {"favicon.ico": "16x16 32x32 48x48", "favicon-32.png": "32x32"}   # the favicon (D892): the mark, free
STALL = 120
"""s a browser may leave one call that has no bound of its own unanswered (an evaluate, past its wait's timeout; a
page's opening or close), as long as a page has to start its engine (``test_site.Site.open``): past it the wait fails
by name with the page's state (D1072). Windows' Firefox once left an evaluate unanswered 2 h 10 min, its processes gone
and Playwright's driver unaware, until the tier's stall watch ended the run (run 41610020282)."""
ACT = 30
"""s a page's load, reload or file pick may take (:func:`load`, :func:`pick`): Playwright's own bound for them, which
they had, past which it named nothing but the call. A load takes 0.1-0.2 s here, a reload 26-68 ms and a pick ms; a
page's first load, which starts its engine (``test_site.Site.open``), has :data:`STALL`."""
HEAR = 10
"""s each read of a stalled page's state may take: a page that answers gives it in ms."""
PROBE = 10
"""s the probe of a stalled call's browser (its cookies) may take: a browser that answers gives them in ms. A bound of
its own, so a test that cuts :data:`HEAR` for a state read that must go unread leaves this one whole (GitHub's Intel
Mac runner took over 1 s for a page's read, run 41666183947)."""
LOOK = 15
"""s a WebKit page's call may go unanswered before macOS's log is read (in 2-3 s here, in at most :data:`HEAR`), then
again each :data:`LOOK` s and at the call's bound, for a page of its browser whose process WebKit ended since the call
began (:func:`within`), which fails the call at once by that name: on GitHub's Intel Mac runner WebKit ended a live
page's process at its network process's request (``reason=RequestedByNetworkProcess``, run 42198913490) and told
Playwright nothing, so the read-back's evaluate waited out its :data:`STALL` and its state went unread, naming nothing.
A call answered in that time reads no log."""
LOG = sys.platform == "darwin"
"""Whether WebKit's log can be read (macOS's ``log``: ``scripts/ci_resources.py``'s ``webkit_said``)."""
CLOSED = 2
"""s a worker whose evaluate failed may stay in ``page.workers`` before Playwright hears its close (:func:`checks`):
Firefox fails an evaluate in flight as the worker's thread closes (Juggler's worker debugger ``onClose`` ends the
call's channel) but tells the driver the worker is gone only at its unregister, later. Its close came 1.6-3.1 ms after
the error here (9 runs of 200), at most 21 ms slowed by ``taskpolicy -b`` and nice 19 (6 of 200): about 100 times that.
A running worker's error waits it out once before it is raised."""


class Static(http.server.SimpleHTTPRequestHandler):
    """A static host: the tests' servers answer each file with the app's type for it, never the registry's guess."""

    def guess_type(self, path) -> str:
        return content_type(str(path))


HOLD = 5
"""s a test holds this interpreter (:func:`hold`) while its page fetches from a :class:`Served` server (a few small
files: tens of ms here)."""


def hold(seconds: int = HOLD) -> None:
    """Hold this interpreter's GIL ``seconds`` s, idle: a C call that keeps it (``ctypes.PyDLL``), as a full collection
    of a big heap holds it."""
    import ctypes
    if sys.platform == "win32":
        ctypes.PyDLL("kernel32").Sleep(seconds * 1000)
    else:
        ctypes.PyDLL(None).sleep(seconds)


def _held_byte(fd: int) -> bytes:
    """One byte of ``fd`` (none at its end), read by a C call that keeps this interpreter's GIL until it comes, as
    :func:`hold` keeps it."""
    import ctypes
    data = ctypes.create_string_buffer(1)
    if sys.platform == "win32":
        import msvcrt
        size = ctypes.c_ulong(0)
        ctypes.PyDLL("kernel32").ReadFile(ctypes.c_void_p(msvcrt.get_osfhandle(fd)), data, 1, ctypes.byref(size), None)
        return data.raw[:size.value]
    libc = ctypes.PyDLL(None, use_errno=True)
    while (size := libc.read(fd, data, ctypes.c_size_t(1))) < 0 and ctypes.get_errno() == errno.EINTR:
        pass
    return data.raw[:max(size, 0)]


class Served:
    """``root`` served on 127.0.0.1 (``url``, no trailing ``/``) from a process of its own (``tests/_static.py``), so a
    page's files never wait on this interpreter: they did when this process served them and the site's routes fetched
    them through it, and a plan or a full collection here beside the page held them (on GitHub's Intel runner a
    reshape's picture 98 s and a service worker's install past 60 s, run 42071325305). ``pages``: as GitHub Pages
    serves (``max-age=600``). ``root`` and ``down`` are settable (a deploy, a host that answers 503); :meth:`log` is
    every request it heard."""

    def __init__(self, root: Path, pages: bool = False):
        self.process = subprocess.Popen(
            [sys.executable, "-I", str(Path(__file__).with_name("_static.py")), str(root), json.dumps(CONTENT_TYPES),
             *(["--pages"] if pages else [])], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")
        if not (port := self.process.stdout.readline().strip()).isdigit():
            self.process.kill()
            raise AssertionError(f"tests/_static.py didn't start: {port!r}")
        self.url, self._root, self._down = f"http://127.0.0.1:{port}", Path(root), False

    def _ask(self, line: str) -> str:
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        return self.process.stdout.readline().rstrip("\n")

    @property
    def root(self) -> Path:
        return self._root

    @root.setter
    def root(self, root: Path) -> None:
        assert self._ask(f"root {root}") == "ok"
        self._root = Path(root)

    @property
    def down(self) -> bool:
        return self._down

    @down.setter
    def down(self, down: bool) -> None:
        assert self._ask(f"down {int(bool(down))}") == "ok"
        self._down = bool(down)

    def log(self) -> list[tuple[str, str, int]]:
        """Each request so far: its method, path (with its query) and body's size."""
        return [tuple(row) for row in json.loads(self._ask("log"))]

    def held(self, path: str, seconds: float) -> bool:
        """Whether it heard a request for ``path`` (with its query) in at most ``seconds`` s, at once if it had, with
        this interpreter held all the while, idle, as :func:`hold` holds it: its answer is read by C calls that keep
        the GIL."""
        self.process.stdin.write(f"heard {seconds} {path}\n")
        self.process.stdin.flush()
        said = b""
        while not said.endswith(b"\n") and (byte := _held_byte(self.process.stdout.fileno())):
            said += byte
        return said.strip() == b"heard"

    def close(self) -> None:
        """Ends it (it ends as its stdin closes, so also with this process)."""
        try:
            self.process.stdin.close()
            self.process.wait(10)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait()
        finally:
            self.process.stdout.close()


def saved_name(browser, name: str) -> str:
    """A download named ``name``'s ``suggested_filename``: WebKit on Linux gives each space in it as ``_``
    (run 41328160086's ``usa_(AzurKit)_spoiler.txt``); the page names it the same in every browser."""
    return name.replace(" ", "_") if sys.platform == "linux" and browser.browser_type.name == "webkit" else name


# What a page that timed out was waiting on (app.mjs's state): each open ask's kind, its record's stage and percent and
# its age in s; the pool's workers (workers.mjs's state(): each one's job, heap and last message with its age in ms);
# Save's check, the page's last 5 refusals of its security policy (app.mjs's violations: what was refused and from
# where, which the status line names only for the page's own) and the status line. Names and numbers only, never game
# bytes.
HANG = """() => {
    const s = globalThis.azurkit, now = performance.now();
    return s ? { asks: [...(s.asks?.values() ?? [])].map((a) => [a.kind, a.record?.stage ?? null, a.record?.percent ?? null,
                                                                Math.round((now - a.since) / 1000)]),
                 pool: s.pool?.state?.() ?? null, saveCheck: s.saveCheck ?? null,
                 violations: s.violations?.slice(-5) ?? null,
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


STATUS = 1200
"""Characters of a stalled page's status line its failure prints at most: its `` · `` parts whole, in order, while
they fit (a build's ends with its changed files, which run long), the rest counted; one part past them alone is cut."""
WIDTH = 200
"""Characters a line of that status takes at most: CI's log cuts each line at 240 (tests.yml), past pytest's ``E``
prefix of 12, and cut the state's one line inside the status of run 42168608453's load failure."""


def _status(text) -> list[str]:
    """The lines a stalled page's status line ``text`` prints as (:data:`STATUS`, :data:`WIDTH`): ``status: `` and its
    first piece, then each next piece of it indented by two, broken at spaces, so read joined by spaces it is whole."""
    if not isinstance(text, str):
        return [f"status: {text!r}"]
    parts, kept = text.split(" · "), []
    while len(kept) < len(parts) and (not kept or len(" · ".join([*kept, parts[len(kept)]])) <= STATUS):
        kept.append(parts[len(kept)])
    said = " · ".join(kept)
    said = said if len(said) <= STATUS else f"{said[:STATUS]}…"
    if left := len(parts) - len(kept):
        said += f" · …and {left} more of its parts ({len(text) - len(' · '.join(kept))} characters)"
    lines = textwrap.wrap(said, WIDTH - len("status: "), break_on_hyphens=False, replace_whitespace=False) or [""]
    return [f"status: {lines[0]}", *(f"  {line}" for line in lines[1:])]


class _Ended(TimeoutError):
    """A call left unanswered whose browser's WebKit ended a page's process since it began: its log's lines on it."""


async def _watched(call, seconds: float, look):
    """``call``'s answer, or TimeoutError past ``seconds``, or :class:`_Ended` with what ``look`` (a read of WebKit's
    log, :func:`_ended`) says ended, read in a thread of its own, in at most :data:`HEAR` s and one at a time, once the
    call went :data:`LOOK` s unanswered, each :data:`LOOK` s after and at ``seconds``: an answer is taken as it
    comes."""
    task, end, reading = asyncio.ensure_future(call), time.monotonic() + seconds, None
    try:
        while True:
            await asyncio.wait([task], timeout=min(LOOK, max(end - time.monotonic(), 0)))
            if not task.done():
                if reading is None or reading.done():
                    reading = asyncio.ensure_future(asyncio.to_thread(look))
                await asyncio.wait([task, reading], timeout=HEAR, return_when=asyncio.FIRST_COMPLETED)
            if task.done():
                return task.result()
            if reading.done() and (lines := reading.result()):
                raise _Ended(tuple(lines))
            if time.monotonic() >= end:
                raise TimeoutError
    finally:
        if not task.done():
            task.cancel()
            await asyncio.wait([task])


def _heard(owner, call, seconds: float, look=None):
    """``call``'s answer (a coroutine of ``owner``'s Playwright object, ``owner._impl_obj``), as ``owner``'s sync call
    would give it, or TimeoutError past ``seconds``, with ``look`` (:func:`_watched`) :class:`_Ended` once it names
    what ended; Playwright aborts the call it cancels."""
    from playwright._impl._sync_base import mapping
    seconds = max(seconds, 0.1)
    return mapping.from_maybe_impl(owner._sync(_watched(call, seconds, look) if look
                                               else asyncio.wait_for(call, seconds)))


def _ended(owner):
    """A read of WebKit's lines in macOS's log since a time (seconds since the epoch) on a page of ``owner``'s browser
    (a page's or a context's) whose process it ended (``scripts/ci_resources.py``'s ``webkit_said`` and ``ENDED``: the
    browser's own UI process, by the processes under its driver), none if the log is unread; or None outside WebKit on
    macOS (:data:`LOG`)."""
    context = owner.context if hasattr(owner, "main_frame") else owner
    if not LOG or context.browser is None or context.browser.browser_type.name != "webkit":
        return None
    from scripts import ci_resources

    def said(since: float) -> list[str]:
        try:
            driver = context._impl_obj._connection._transport._proc.pid
            browsers = {pid for _, (pid, *_) in ci_resources.tree(ci_resources.table(), driver)}
            return [line for line in ci_resources.webkit_said(since, browsers) if ci_resources.ENDED in line]
        except Exception:   # an unread listing names nothing
            return []
    return said


def hang(page, last: int = 5) -> str:
    """Why a wait on ``page`` may not have ended: its :data:`HANG` state, its status line on lines of its own, whole
    (:func:`_status`), and the last ``last`` page errors (uncaught exceptions and unhandled rejections) and console
    errors since the page opened (Playwright keeps them), each read in :data:`HEAR` s."""
    said = []

    def state():
        read = _heard(page, page._impl_obj.evaluate(HANG), HEAR)
        if not isinstance(read, dict):
            return read
        status = read.pop("status", None)
        return "\n".join([str(_short(read)), *_status(status)])

    for what, read in (("state", state),
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
        return ", ".join(f"{name} {pid} ({age} s)" for _, (pid, _, age, name, *_) in
                         ci_resources.tree(ci_resources.table(), driver)) or f"none (the driver {driver} is gone)"
    except Exception as error:
        return f"unread ({_short(str(error), 200)})"


def stalled(owner, what: str, seconds: float, ended: tuple[str, ...] = ()) -> str:
    """What a call to ``owner`` (a page or a context) that went unanswered ``seconds`` s says: ``what`` it was, WebKit's
    log's lines on a page of its browser whose process it ended since the call began (``ended``, :func:`_ended`), each
    on a line of its own, the page's state (:func:`hang`), whether its browser still answers a call of its own (its
    cookies, in :data:`PROBE` s) and the processes under its driver. A browser that answers nothing either has stopped:
    its Playwright connection is closed naming ``what``, so every later call to it fails at once by name, its module's
    next tests too, never a silent wait (D1072)."""
    page = owner if hasattr(owner, "main_frame") else None
    context = page.context if page else owner
    said = [f"no answer in {seconds:.0f} s: {_short(what)}"]
    if ended:
        said += ["WebKit ended a page's process in its browser since the call began (its log):",
                 *(f"  {line}" for line in ended)]
    said += [hang(page)] if page else []
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
    (:func:`stalled`); in WebKit on macOS also at once, naming it, as its log says WebKit ended the process of a page
    of the call's browser since the call began (from a second before it: the log's times are whole seconds), read once
    the call went :data:`LOOK` s unanswered, each :data:`LOOK` s after and at ``seconds`` (:func:`_ended`)."""
    look, since, began = _ended(owner), time.time() - 1, time.monotonic()
    try:
        return _heard(owner, call, seconds, look and (lambda: look(since)))
    except _Ended as ending:
        raise AssertionError(stalled(owner, what, time.monotonic() - began, ending.args[0])) from None
    except TimeoutError:
        raise AssertionError(stalled(owner, what, seconds)) from None


def answer(page, js: str, arg=None, seconds: float = STALL):
    """``page.evaluate(js, arg)``, unanswered for at most ``seconds`` s (:func:`within`)."""
    from playwright._impl._sync_base import mapping
    return within(page, page._impl_obj.evaluate(js, mapping.to_impl(arg)), seconds, js)


def checks(page, counter: str = "azurkitChecks") -> int:
    """The image checks the page's workers ran (worker.mjs's ``self.azurkitChecks``, or another ``counter`` a worker
    keeps: a test's own, in a worker.mjs it routed), over those still running: a
    worker the page ends as its answer comes (the one it starts once the pick's check is done) fails its evaluate,
    with TargetClosedError in Chromium and WebKit (run 41981438506's Linux tier; 1 in 5 runs here, its close heard
    3.6 ms after the read), in Firefox with a plain Error, "Worker was closed" once the driver heard the worker end,
    or "Execution context was destroyed, most likely because of a navigation." before (run 42156372553's Linux tier;
    Juggler fails the call as the worker's thread closes, the driver's rewrite of that error). Its checks went with
    it. A worker is told ended by its own close, which takes it out of ``page.workers``, whichever comes first: one
    whose evaluate failed counts none once its close is heard, within :data:`CLOSED` s, and one still listed past
    them is running and raises its error."""
    from playwright._impl._errors import Error
    found = 0
    for worker in page.workers:
        try:
            found += worker.evaluate(f"() => self.{counter} ?? 0")
        except Error:
            end = time.monotonic() + CLOSED
            while worker in page.workers:
                if time.monotonic() >= end:
                    raise
                page.wait_for_timeout(10)   # Playwright hears the close only while its loop runs
    return found


def close(page) -> None:
    """``page.close()``, in at most :data:`STALL` s (:func:`within`)."""
    within(page, page._impl_obj.close(), STALL, "the page's close")


def load(page, url: str | None = None, until: str = "load", seconds: float | None = None):
    """``page.goto(url)``, or with no ``url`` ``page.reload()``, to its ``until`` (Playwright's ``wait_until``), in at
    most ``seconds`` s, :data:`ACT` unless given (:func:`within`), where past Playwright's own 30 s it failed naming
    nothing but the navigation (a site page's load in Firefox, run 41678038275; a reload in WebKit on 4a178cc, both on
    GitHub's Intel Mac runner): past it the failure names the page's state, whether its browser still answers and its
    driver's processes, then the requests the page made since the call that neither finished nor failed, each one's
    method, address with no query (the app's page carries its token in it) and age, or none: the frozen app's page in
    Firefox on GitHub's Windows runner went past Playwright's 30 s at its first load, the app running, its stderr empty,
    the failure naming no file (tests.yml run 42122369507)."""
    asked, ended = [], set()

    def asking(request) -> None:
        asked.append((request, time.monotonic()))

    def answered(request) -> None:
        ended.add(request._impl_obj)

    heard = (("request", asking), ("requestfinished", answered), ("requestfailed", answered))
    for event, handler in heard:
        page.on(event, handler)
    call = (page._impl_obj.reload(timeout=0, waitUntil=until) if url is None
            else page._impl_obj.goto(url, timeout=0, waitUntil=until))
    try:
        return within(page, call, ACT if seconds is None else seconds,
                      "the page's reload" if url is None else f"the page's load of {url}")
    except AssertionError as stall:
        now, waiting = time.monotonic(), []
        for request, at in asked:
            if request._impl_obj not in ended:
                where = urllib.parse.urlsplit(request.url)._replace(query="", fragment="").geturl()
                waiting.append(f"{request.method} {_short(where)} ({now - at:.0f} s)")
        raise AssertionError(f"{stall}\nits requests unanswered: {', '.join(waiting[-10:]) or 'none'}") from None
    finally:
        for event, handler in heard:
            page.remove_listener(event, handler)


def pick(page, selector: str, path) -> None:
    """``page.set_input_files(selector, path)``: the file at ``path`` picked in the page's file input ``selector``, in
    at most :data:`ACT` s (:func:`within`), the bound its driver gave it, now this side's too: the pack golden's Firefox
    page on GitHub's Windows runner left a call that had no bound of this side's unanswered an hour, its browser gone
    and its driver unaware (run 41744982709), its picks among those calls. Past it the failure names the pick, the
    page's state and its driver's processes."""
    within(page, page._impl_obj.set_input_files(selector, str(path), timeout=0), ACT,
           f"the pick of {Path(path).name} in {selector}")


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
