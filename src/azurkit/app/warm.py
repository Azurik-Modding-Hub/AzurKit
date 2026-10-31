"""D1008's warm-up (Step 4.3x; warm-up WU1 with WU3's kept answers): what
the page's next calls will read, worked out ahead on one queue while no call
is in flight (D1007: background work, dropped on a change), in two phases:

- phase A (:func:`phase_a`), at ready, on intent only (Randomize on in the
  remembered setup, a tracked plan remembered, or the Randomizer tab
  opened; warming at every launch would cost the capped profile's memory):
  the randomizer's logic, the tracker's world map, the remembered plan's
  tracker and its view, the Randomizer tab's answer for the remembered
  setup and, with Randomize on, the remembered seed's plan, the answers kept
  (:mod:`.memo`: the plan store among them);
- phase B (:func:`phase_b`), after the first pick of an image: its read
  (the gate's check and the Characters tab's pickers) and the remembered
  character dressed at the current packs (the swap's own store keeps it).

The species' and the tracker's pictures ship with the page (Step 4.3f):
nothing to warm for them.

:class:`Queue` runs its items one at a time on a thread of its own, each
under the host's ``background`` (its low priority, D1007). A call in
flight (:meth:`Queue.call`) holds the next item back and pauses the running
one at its next progress record until no call is in flight: the GIL is
shared, so a low-priority thread is one that waits. An item that reports
no record (the logic, about 0.4 s) runs to its end; a ``pooled`` one (a
dress, its work in the pool's children, which a pause would strand) is never
paused or stopped once it runs, only started while no call is in flight.
A change (:meth:`Queue.put` of an item of the same name for other inputs,
:meth:`Queue.drop`) drops a queued item and stops a running one at its next
record (:class:`Dropped`), so it writes nothing it hadn't. A call that
needs an item (:meth:`Queue.need`) moves it to the front and waits for it,
the records of what runs meanwhile on its own bar; no item pauses for a
call that waits on the queue. A tab opened moves its items first
(:meth:`Queue.first`). :meth:`Queue.status` is the bottom bar's quiet row;
:meth:`Queue.idle` waits for the queue to empty. The site's twin is
``web/warm.mjs``."""

from __future__ import annotations

import contextlib
import dataclasses
import threading
from collections.abc import Callable, Mapping

from azurkit.core.progress import record

from .memo import Memo

QUEUED, RUNNING, DONE, FAILED, DROPPED = "queued", "running", "done", "failed", "dropped"


class Dropped(BaseException):
    """An item a change dropped, raised from its progress at its next record."""


@dataclasses.dataclass(eq=False)
class Item:
    """One thing to warm: ``run(progress)`` does it (``progress(record)``
    its pause and drop points, ``core.progress`` records); ``key`` what it is
    worked out for (an item of its name and key is the same item); ``stage``
    and ``label`` its line on the bar; ``pooled``: its work runs in the
    pool's children (never paused or stopped once it runs)."""
    name: str
    stage: str
    label: str
    run: Callable[[Callable[[dict], None]], object]
    key: object = None
    pooled: bool = False
    state: str = QUEUED
    last: dict | None = None   # the record it reported last
    stop: bool = False
    needed: int = 0            # the calls waiting on it (Queue.need), which hold no item back until it ends


class Queue:
    """The warm-up's queue (the module's docstring); ``background()`` a
    context its items run in (the host's low priority; none by default)."""

    def __init__(self, background: Callable[[], contextlib.AbstractContextManager] | None = None):
        self._background = background or contextlib.nullcontext
        self._cond = threading.Condition()
        self._queued: list[Item] = []
        self._running: Item | None = None
        self._ended: dict[str, Item] = {}   # each name's item that ended last
        self._round: list[Item] = []        # the items since the queue was last idle: the row's "k of n"
        self._calls = self._waiting = 0
        self._closed = False
        threading.Thread(target=self._loop, name="azurkit-warm", daemon=True).start()

    def _busy(self) -> bool:
        return self._calls > self._waiting

    def put(self, items) -> None:
        """Queue ``items`` in order, each in place of a queued or running one
        of its name for another key (that one dropped); one of its name and
        key that is queued, running or done already stands."""
        with self._cond:
            if self._running is None and not self._queued:
                self._round = []
            for item in items:
                if (ended := self._ended.get(item.name)) is not None and ended.state == DONE and ended.key == item.key:
                    continue
                if (running := self._running) is not None and running.name == item.name:
                    if running.key == item.key and not running.stop:
                        continue
                    self._stop(running)
                at = next((k for k, q in enumerate(self._queued) if q.name == item.name), None)
                if at is not None and self._queued[at].key == item.key:
                    continue
                if at is not None:
                    self._forget(self._queued.pop(at))
                    self._queued.insert(at, item)
                else:
                    self._queued.append(item)
                self._round.append(item)
            self._cond.notify_all()

    def _stop(self, item: Item) -> None:
        if not item.pooled:
            item.stop = True
            self._forget(item)

    def _forget(self, item: Item) -> None:
        item.state = DROPPED if item.state == QUEUED else item.state
        if item.state == DROPPED:
            self._release(item, item.needed)
        if item in self._round:
            self._round.remove(item)

    def drop(self, *names: str) -> None:
        """A change (D1007): drop the queued items of ``names`` (none: every
        one) and stop the running one at its next record."""
        with self._cond:
            for item in [q for q in self._queued if not names or q.name in names]:
                self._queued.remove(item)
                self._forget(item)
            if (running := self._running) is not None and (not names or running.name in names):
                self._stop(running)
            self._cond.notify_all()

    def first(self, *names: str) -> None:
        """Move the queued items of ``names`` to the front, in that order (a tab opened)."""
        with self._cond:
            ahead = [q for name in names for q in self._queued if q.name == name]
            self._queued = ahead + [q for q in self._queued if q not in ahead]

    @contextlib.contextmanager
    def call(self):
        """A call in flight while inside: no item starts, the running one pauses at its next record."""
        with self._cond:
            self._calls += 1
        try:
            yield
        finally:
            with self._cond:
                self._calls -= 1
                self._cond.notify_all()

    def need(self, name: str, progress: Callable[[dict], object] | None = None) -> bool:
        """Wait for the item ``name``, moved to the front; ``progress``
        hears its line, then each record of what runs until it ends (an
        exception it raises, a cancel, ends the wait, not the item). Whether
        it ended done (``False``: none queued or running and none done, or
        it failed or was dropped: the call does the work itself)."""
        with self._cond:
            item = self._running if self._running is not None and self._running.name == name else next(
                (q for q in self._queued if q.name == name), None)
            if item is None:
                return (ended := self._ended.get(name)) is not None and ended.state == DONE
            if item in self._queued:
                self.first(name)
            item.needed += 1
            self._waiting += 1
            self._cond.notify_all()
        heard = None
        try:
            if progress is not None:
                progress(record(item.stage, item.label))
            while True:
                with self._cond:
                    if item.state not in (QUEUED, RUNNING):
                        return item.state == DONE
                    step = self._running.last if self._running is not None else None
                    if step is heard or step is None:
                        self._cond.wait(0.25)
                        continue
                heard = step
                if progress is not None:
                    progress(step)
        finally:
            with self._cond:
                self._release(item, 1)

    def _release(self, item: Item, count: int) -> None:
        """``count`` of the calls waiting on ``item`` (all at its end) hold the queue back again."""
        count = min(count, item.needed)
        item.needed -= count
        self._waiting -= count
        self._cond.notify_all()

    def _progress(self, item: Item, step: dict) -> None:
        with self._cond:
            item.last = step
            self._cond.notify_all()
            if item.pooled:
                return
            while not (item.stop or self._closed) and self._busy():
                self._cond.wait()
            if item.stop or self._closed:
                raise Dropped

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._closed and (not self._queued or self._busy()):
                    self._cond.wait()
                if self._closed:
                    return
                item = self._queued.pop(0)
                item.state, self._running = RUNNING, item
            try:
                with self._background():
                    item.run(lambda step: self._progress(item, step))
                state = DROPPED if item.stop else DONE   # a stopped item that reported no record since: its rest
            except Dropped:
                state = DROPPED
            except BaseException:   # a refusal: the page's own call names it
                state = FAILED
            with self._cond:
                item.state, self._running = state, None
                self._release(item, item.needed)
                if state != DROPPED:
                    self._ended[item.name] = item
                self._cond.notify_all()

    def status(self) -> dict:
        """The bottom bar's row: ``{"done", "total", "stage", "label",
        "percent", "ready"}`` over the items since the queue was last idle
        (``label`` the running item's, ``percent`` its last record's;
        ``ready``: nothing queued or running)."""
        with self._cond:
            running, ready = self._running, self._running is None and not self._queued
            done = sum(item.state in (DONE, FAILED) for item in self._round)
            return {"done": done, "total": len(self._round), "stage": running.stage if running else None,
                    "label": running.label if running else "", "ready": ready,
                    "percent": running.last.get("percent") if running is not None and running.last else None}

    def idle(self, timeout: float | None = None) -> bool:
        """Wait until nothing is queued or running (``timeout`` seconds at most); whether it is."""
        with self._cond:
            return self._cond.wait_for(lambda: self._running is None and not self._queued, timeout)

    def close(self) -> None:
        """Drop everything and end the queue's thread (a running item at its next record)."""
        with self._cond:
            self._closed = True
            for item in self._queued:
                self._forget(item)
            self._queued.clear()
            self._cond.notify_all()


def intent(setup: object = None, tracked: object = None, opened: bool = False) -> bool:
    """Whether phase A starts: Randomize on in ``setup`` (host.json's
    remembered setup), a plan in ``tracked`` (its tracker), or the
    Randomizer tab ``opened``."""
    rando = setup.get("randomizer") if isinstance(setup, Mapping) else None
    plan = tracked.get("plan") if isinstance(tracked, Mapping) else None
    return bool(opened or isinstance(rando, Mapping) and rando.get("on") is True or isinstance(plan, Mapping))


def phase_a(memo: Memo, setup: object = None, tracked: object = None, tab: Mapping | None = None,
            opened: bool = False, guard: contextlib.AbstractContextManager | None = None) -> list[Item]:
    """Phase A's items, none without :func:`intent`: the randomizer's logic,
    the world map; with ``tracked`` (host.json's tracker: the plan last
    tracked and each plan's marks) that plan's tracker and view, as the page
    asks it on reopening; with ``tab`` (the Randomizer tab's ask for the
    remembered setup, as the page makes it) the tab's answer and, Randomize
    on with a seed, that seed's plan at the answer's share string (Track's
    recipe). Each answer is kept in ``memo`` under its own key. ``guard``
    (the host's lock on the trackers its calls share): the tracker item
    holds it, then reports no record (a pause inside it would hold the call
    it waits for)."""
    from azurkit import sdk
    from azurkit.tools import randomizer
    from azurkit.tools.randomizer import tracking

    if not intent(setup, tracked, opened):
        return []
    items = [Item("logic", "plan", "Reading the randomizer's logic", lambda progress: randomizer.kept_logic()),
             Item("world", "plan", "Reading the world map", lambda progress: tracking.world())]
    doc = tracked.get("plan") if isinstance(tracked, Mapping) else None
    if isinstance(doc, Mapping) and isinstance(doc.get("sha256"), str):
        marks = tracked.get("marks") if isinstance(tracked.get("marks"), Mapping) else {}
        given = {"plan": doc, "marks": marks.get(doc["sha256"]), "gems": bool(tracked.get("gems"))}
        def viewed(progress: Callable[[dict], None]) -> object:
            with guard if guard is not None else contextlib.nullcontext():
                heard = None if guard is not None else progress
                tracking.tracker_of(doc, heard)   # kept for the process, whatever the memo holds
                return memo.answer("tracker", given, lambda: sdk.tracker(given, progress=heard))
        items.append(Item("tracker", "plan", "Reading the seed's logic", viewed, key=memo.key("tracker", given)))
    if isinstance(tab, Mapping):
        items.append(Item("tab", "plan", "Reading the randomizer's settings", lambda progress: memo.answer(
            "randomizer", tab, lambda: sdk.randomizer_settings(tab)), key=memo.key("randomizer", tab)))
        rando = setup.get("randomizer") if isinstance(setup, Mapping) else None
        if isinstance(rando, Mapping) and rando.get("on") is True and isinstance(rando.get("seed"), str) \
                and rando["seed"].strip():
            seed = rando["seed"].strip()

            def planned(progress: Callable[[dict], None]) -> object:
                share = memo.answer("randomizer", tab, lambda: sdk.randomizer_settings(tab))[0]["share"]
                recipe = {"seed": seed, "share": share}
                return memo.answer("plan", recipe, lambda: sdk.plan(recipe, progress=progress))
            items.append(Item("plan", "plan", f"Planning seed {seed}", planned, key=(memo.key("randomizer", tab),
                                                                                    seed)))
    return items


def phase_b(iso: str, setup: object = None, packs: Mapping | None = None,
            match: Callable[[Mapping, Callable[[dict], None]], object] | None = None) -> list[Item]:
    """Phase B's items, after the first pick of the image at ``iso``: its
    read (the gate's check and the Characters tab's pickers, as the pictures
    read it) and, when ``setup`` remembers a character other than
    garret4, that character dressed at ``packs`` (the Patches tab's) by
    ``match(recipe, progress)`` (the G4 match, whose dress the swap keeps:
    the host's engine call; ``sdk.match`` by default), pooled."""
    from azurkit import sdk

    items = [Item("image", "read", "Reading your image", lambda progress: sdk.pickers({"iso": iso}), key=iso)]
    character = setup.get("character") if isinstance(setup, Mapping) else None
    if isinstance(character, Mapping) and character.get("species") not in (None, "garret4"):
        recipe = {"iso": iso, "character": dict(character), "packs": dict(packs or {})}
        dress = match or (lambda recipe, progress: sdk.match(recipe))
        items.append(Item("character", "dress", f"Dressing {character['species']}",
                          lambda progress: dress(recipe, progress), key=repr(sorted(recipe.items())), pooled=True))
    return items
