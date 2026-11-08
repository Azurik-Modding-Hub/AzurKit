"""The app's Live feed (Step 4.2c2, D249; the app's alone, D882): a thread
that looks for a running xemu and reads the game through it (Modkit's
``live.Session`` on the link ``tools.randomizer.live.link`` opens), as
Modkit's tracker window's worker does: it looks every :data:`RETRY_S`
until an xemu answers, then polls it, and looks again once the link is
lost. It tries the private endpoints of the xemu Play started and of the
admin attach's helper first (``launch``, :mod:`.xemu`), then the Endpoints
box's. Its events and the newest reading wait in the feed until the page's
next tracker ask (``api/tracker``) merges them into its marks
(``tracking.view``'s ``events``), the reach holding the element levels the
game holds (R1.41). Live only reads guest memory, never writes it, and
never launches xemu (Play does); nothing here prints guest bytes.

The status the page shows (Modkit's): ``connecting`` (no xemu answers
yet, and the one fix), ``waiting`` (xemu runs no Azurik), ``live``,
``warn`` (the game hasn't advanced: paused, or xemu stopped), ``lost``
(the link closed; it reconnects by itself), ``other`` (xemu runs another
seed or build: its line names the level and how many of the item spots
Live read differ, or an image no seed wrote, and what to check) or
``stopped`` (an error ended the feed).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping

from azurkit.tools.randomizer import tracking
from azurkit.tools.randomizer.live import game, link

RETRY_S = 2.0   # s between looks for xemu while none answers, or after one is lost
NOT_AZURIK = "xemu is running, but not Azurik yet: boot the seed's ISO."
OTHER_SEED = "xemu runs another seed or build"
CHECK = ("check the seed, the share string's settings, the packs' movement and the body worn on the Characters tab "
         "(its size folds into the walk and roll) against the build's, or track the build itself (Tools: Open a "
         "build…, Track this build)")
PAUSED = "The game isn't advancing: paused in xemu, or xemu quit."
NO_XEMU = f"No xemu answers. Start xemu with {link.QMP_ARG}, or enter where yours listens in Endpoints."


def page_text(text: str) -> str:
    """The link's ``text`` as the page can act on it. The link names its
    Tk window's controls (Modkit's tracker: a right-click menu with the
    macOS admin attach and Endpoints…, a click that copies the QMP launch
    line); the page has only its Endpoints box, so its no-xemu line (any
    OS's) is :data:`NO_XEMU` and the others name the box and the QMP
    argument itself."""
    if text in {link.no_xemu(platform) for platform in ("darwin", "linux", "win32")}:
        return NO_XEMU
    return (text.replace("Endpoints… (right-click)", "Endpoints")
            .replace("(right-click copies the line)", f"({link.QMP_ARG})"))


class Feed:
    """One plan's Live: :meth:`start` its thread, :meth:`take` what it read since, :meth:`stop` it."""

    def __init__(self, plan: Mapping, marks: Mapping | None, endpoints: str = "", gems: bool = False,
                 launch: list[link.Endpoint] | None = None):
        tracking.view({"plan": plan, "marks": marks})   # the plan and marks checked; the journal is the marks'
        t = tracking.tracker_of(plan)
        self.sha256, self.seed, self.share = plan["sha256"], plan["seed"], plan["share"]
        # the gem spots too while the tracker shows them (R1.43: each read is one more of a poll's)
        self.spots, self.journal = game.spot_table(t, gems=gems), t.journal()
        self.items = {loc: t.item(loc) for loc in t.spots}
        self.pool = t.logic.pool
        self.endpoints = endpoints
        self.launch = list(launch or [])   # Play's xemu's and the admin helper's private endpoints, tried first
        self.lock, self.stopped = threading.Lock(), threading.Event()
        self.events: list = []
        self.reading: game.Reading | None = None   # the newest
        self.kit: dict[str, int] = {}              # the element levels the game last held (a load keeps them)
        self.seen: game.Reading | None = None      # the newest settled one with the player on a level
        self.status, self.text, self.which, self.paused, self.unpaired = "connecting", "Looking for xemu…", "", False, 0
        self.last: tuple[str, str, float] | None = None   # the last take: its item, its level, when
        self.session: game.Session | None = None          # the one reading the game now (None: none)
        self.thread = threading.Thread(target=self._run, name="azurkit-live", daemon=True)

    def start(self) -> Feed:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.stopped.set()

    def resync(self) -> None:
        """The tracker was reset: the game is read again (Modkit's ``Session.resync``)."""
        with self.lock:
            if self.session is not None:
                self.session.resync()

    def keep(self, journal: Mapping) -> None:
        """The tracker's journal after an ask (its saved slot, its newest live mark), which the next session
        opens on (Modkit's, refreshed at every change)."""
        with self.lock:
            self.journal = dict(journal)

    def _endpoints(self) -> list[link.Endpoint]:
        """The private endpoints first, then the box's (or the defaults); a box Live can't read leaves the private
        ones alone (Modkit's tracker worker)."""
        try:
            return [*self.launch, *link.endpoints(saved=self.endpoints)]
        except link.LiveError:
            if not self.launch:
                raise
            return list(self.launch)

    def _say(self, status: str, text: str) -> None:
        with self.lock:
            self.status, self.text = status, text

    def _run(self) -> None:
        while not self.stopped.is_set():
            with self.lock:
                journal = self.journal
            try:
                session = game.Session(link.open_first(self._endpoints()), self.spots, journal)
            except link.LiveError as exc:
                self._say("connecting", page_text(str(exc)))
                self.stopped.wait(RETRY_S)
                continue
            except Exception as exc:   # noqa: BLE001 (the feed ends and says why, as Modkit's does)
                return self._say("stopped", f"Live stopped: {exc}")
            self.which = session.describe()
            with self.lock:
                self.session = session
            try:
                while not self.stopped.is_set():
                    self._update(session.poll())
                    self.stopped.wait(session.period)
            except link.LinkLost as exc:
                self._say("lost", f"Lost xemu at {time.strftime('%H:%M')} ({exc}). Live reconnects by itself when "
                                  "it's back.")
                self.stopped.wait(RETRY_S)
            except Exception as exc:   # noqa: BLE001
                return self._say("stopped", f"Live stopped: {exc}")
            finally:
                with self.lock:
                    self.session = None
                session.close()

    def _update(self, u: game.Update) -> None:
        r = u.reading
        with self.lock:
            self.events += u.events
            for e in u.events:
                if isinstance(e, game.Took):
                    self.last = (self.items.get(e.loc, ""), self.pool.get(e.loc, ""), time.monotonic())
            self.reading, self.paused, self.unpaired = r, u.paused, u.unpaired
            if r.kit is not None:
                self.kit = r.kit
            if r.settled and r.at is not None and r.level in tracking.GRID:
                self.seen = r
            if r.state == "waiting":
                self.status, self.text = "waiting", NOT_AZURIK
            elif r.mismatch:
                self.status, self.text = "other", self._other(r)
            elif u.paused:
                self.status, self.text = "warn", PAUSED
            else:
                self.status, self.text = "live", self._line(r)

    def _other(self, r: game.Reading) -> str:
        """What differs while xemu runs another seed or build, and what to check: the level's item spots Live
        read that hold other items than the plan's, or, when each holds the base game's, an image no seed wrote."""
        n, of, vanilla = r.odd or (0, 0, False)
        where = f" in {r.level}" if r.level else ""
        if vanilla:
            return (f"{OTHER_SEED}: the {of} item spots Live read{where} hold the base game's items, so the image "
                    "isn't randomized: boot the randomized build you track.")
        differ = f": {n} of the {of} item spots Live read{where} hold other items" if of else ""
        return f"{OTHER_SEED}{differ} than seed {self.seed}'s plan (share string {self.share}): {CHECK}."

    def _line(self, r: game.Reading) -> str:
        """``<level> · <release> · <which xemu> · last: <item> (<level>), <m:ss> ago`` (Modkit's)."""
        where = r.state if r.state in ("menus", "loading") else r.level if r.level in tracking.GRID else r.path or "menus"
        last = "none yet"
        if self.last:
            item, level, at = self.last
            s = int(time.monotonic() - at)
            last = f"{tracking.item_name(item)} ({level}), {s // 60}:{s % 60:02d} ago"
        return f"{where} · {r.region.label if r.region else '?'} · {self.which} · last: {last}"

    def take(self) -> tuple[list, dict]:
        """The events since the last take, and what the page shows of Live: the status and its line, where
        Live last saw the player (``seen``: the level, the place in metres and the way they face; None) and
        whether they stand there now (``here``: not once the link is lost; on another seed or build too, as
        Modkit places them), the element levels the game last held (``kit``), its inventory (``held``, the
        Table's In game column) and the saved slot the newest reading shows (``slot``; None: none), which the
        tracker's journal keeps (Modkit's)."""
        with self.lock:
            events, self.events = self.events, []
            r, seen = self.reading, self.seen
            return events, {
                "status": self.status, "text": self.text, "unpaired": self.unpaired,
                "here": r is not None and r.settled and seen is r and self.status in ("live", "warn", "other"),
                "seen": None if seen is None else {"level": seen.level, "at": list(seen.at), "yaw": seen.yaw or 0.0},
                "took": [e.loc for e in events if isinstance(e, game.Took)],   # the fresh pickups, the page's flash
                "kit": dict(self.kit), "held": dict(r.inv) if r is not None and r.inv and not r.mismatch else {},
                "slot": r.slot if r is not None and game.is_slot(r.slot) else None}
