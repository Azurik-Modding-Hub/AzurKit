"""The app's Live feed (Step 4.2c2, D249; the app's alone, D882): a thread
that looks for a running xemu and reads the game through it (Modkit's
``live.Session`` on the link ``tools.randomizer.live.link`` opens), as
Modkit's tracker window's worker does: it looks every :data:`RETRY_S`
until an xemu answers, then polls it, and looks again once the link is
lost. Its events and the newest reading wait in the feed until the page's
next tracker ask (``api/tracker``) merges them into its marks
(``tracking.view``'s ``events``), the reach holding the element levels the
game holds (R1.41). Live only reads guest memory, never writes it, and
never launches xemu; nothing here prints guest bytes.

The status the page shows (Modkit's): ``connecting`` (no xemu answers
yet, and the one fix), ``waiting`` (xemu runs no Azurik), ``live``,
``warn`` (the game hasn't advanced: paused, or xemu stopped), ``lost``
(the link closed; it reconnects by itself), ``other`` (xemu runs another
seed or build) or ``stopped`` (an error ended the feed).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping

from azurkit.tools.randomizer import tracking
from azurkit.tools.randomizer.live import game, link

RETRY_S = 2.0   # s between looks for xemu while none answers, or after one is lost
NOT_AZURIK = "xemu is running, but not Azurik yet: boot the seed's ISO."
OTHER_SEED = "xemu runs another seed or build: open the tracker of the build you're playing."
PAUSED = "The game isn't advancing: paused in xemu, or xemu quit."


class Feed:
    """One plan's Live: :meth:`start` its thread, :meth:`take` what it read since, :meth:`stop` it."""

    def __init__(self, plan: Mapping, marks: Mapping | None, endpoints: str = ""):
        self.sha256 = plan["sha256"]
        t = tracking.tracker_of(plan)
        tracking.view({"plan": plan, "marks": marks})   # the journal is the page's marks'
        self.spots, self.journal = game.spot_table(t), t.journal()
        self.items = {loc: t.item(loc) for loc in t.spots}
        self.pool = t.logic.pool
        self.endpoints = endpoints
        self.lock, self.stopped = threading.Lock(), threading.Event()
        self.events: list = []
        self.reading: game.Reading | None = None   # the newest
        self.kit: dict[str, int] = {}              # the element levels the game last held (a load keeps them)
        self.seen: game.Reading | None = None      # the newest settled one with the player on a level
        self.status, self.text, self.which, self.paused, self.unpaired = "connecting", "Looking for xemu…", "", False, 0
        self.last: tuple[str, str, float] | None = None   # the last take: its item, its level, when
        self.thread = threading.Thread(target=self._run, name="azurkit-live", daemon=True)

    def start(self) -> Feed:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.stopped.set()

    def _say(self, status: str, text: str) -> None:
        with self.lock:
            self.status, self.text = status, text

    def _run(self) -> None:
        while not self.stopped.is_set():
            try:
                session = game.Session(link.open_first(link.endpoints(saved=self.endpoints)), self.spots,
                                       self.journal)
            except link.LiveError as exc:
                self._say("connecting", str(exc))
                self.stopped.wait(RETRY_S)
                continue
            except Exception as exc:   # noqa: BLE001 (the feed ends and says why, as Modkit's does)
                return self._say("stopped", f"Live stopped: {exc}")
            self.which = session.describe()
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
                self.status, self.text = "other", OTHER_SEED
            elif u.paused:
                self.status, self.text = "warn", PAUSED
            else:
                self.status, self.text = "live", self._line(r)

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
        whether they stand there now (``here``), the element levels the game last held (``kit``) and its
        inventory (``held``, the Table's In game column)."""
        with self.lock:
            events, self.events = self.events, []
            r, seen = self.reading, self.seen
            return events, {
                "status": self.status, "text": self.text, "unpaired": self.unpaired,
                "here": r is not None and r.settled and seen is r,
                "seen": None if seen is None else {"level": seen.level, "at": list(seen.at), "yaw": seen.yaw or 0.0},
                "kit": dict(self.kit), "held": dict(r.inv) if r is not None and r.inv and not r.mismatch else {}}
