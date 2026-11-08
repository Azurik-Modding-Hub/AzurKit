"""The app's Play and admin attach (Modkit's app Play button and its tracker's
attach, D256, D257, D274; the app's alone, D882), for one launch of the app.

Play (``api/play``) launches the player's xemu with the saved build in the tray
and private endpoints, which Live tries first (:meth:`Player.endpoints`), or
says what it needs first, as Modkit's does:

- the xemu Play started still runs (its private QMP socket answers), or one the
  admin helper already reads: ``{"tracking"}``, no question, no second prompt;
- another xemu of the player's runs: ``{"running", "attach"}``, Play starts no
  second one (it would fight the first for the same config and disk) and the
  page offers to attach to it where the app can (macOS), else says to quit it;
- several found: ``{"choose"}``, each with its label (and its path where two
  read alike), the one picked last first; none: ``{"none"}``, the page asks
  where xemu is;
- else ``{"launched"}``: xemu started (:func:`.xemu.spawn`), its private 0700
  folder (its QMP socket) kept until the app quits.

The attach (``api/attach``, macOS): a running xemu of the player's (a chooser
when several run; a hardened build refused, which a root helper can't read)
read through the read-only root helper behind one admin prompt
(:func:`.xemu.start_helper`); its private folder replaces an earlier helper's,
which then exits, and goes when the app quits. Each call refuses by name with
``ValueError``, never with a game byte.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import threading
from pathlib import Path

from azurkit.tools.randomizer.live.link import Endpoint, LiveError

from . import xemu

ATTACH = ("xemu is already running: attach to it? Attach reads it through a read-only admin helper (one password "
          "prompt); no xemu setting changes and no second xemu starts.")
NO_ATTACH = ("xemu is already running, and attaching to it isn't available on this system yet: quit it, then press "
             "Play to start it with this build; or start it with QMP and turn Live on.")
NONE_FOUND = "No xemu found: choose where yours is (its xemu.app, xemu.exe or program)."
NONE_RUNNING = "No running xemu found. Start xemu with the seed, then try again."
HARDENED = ("xemu's build has the hardened runtime, which a helper can't read: quit it and press Play, which starts "
            "it readable.")


def _private(prefix: str) -> Path:
    """A fresh private folder (0700) for a socket only this user reaches."""
    run_dir = Path(tempfile.mkdtemp(prefix=prefix))
    os.chmod(run_dir, 0o700)
    return run_dir


def _labels(xemus: list[xemu.Xemu]) -> list[str]:
    """Each one's label, with its path where two read alike (Modkit's chooser)."""
    labels = [x.label for x in xemus]
    return [f"{label} · {x.path}" if labels.count(label) > 1 else label for label, x in zip(labels, xemus)]


class Player:
    """Play's xemu and the admin helper of one launch of the app."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.played: list[Endpoint] = []                  # the xemu Play started: its private endpoints
        self.helper: tuple[int, Endpoint, Path] | None = None   # the attach: xemu's pid, the helper's endpoint, folder
        self.scratch: list[Path] = []                     # Play's private folders (their xemus' QMP sockets)

    def endpoints(self) -> list[Endpoint]:
        """The private endpoints Live tries first: the helper's while its socket is there, then Play's xemu's."""
        with self.lock:
            helper = [self.helper[1]] if self.helper and Path(self.helper[1].target).exists() else []
            return [*helper, *self.played]

    def play(self, iso: Path, chosen: str | None = None, remembered: str | None = None) -> dict:
        """Play the build ``iso``: ``chosen`` the path the player picked (from ``{"choose"}`` or ``{"none"}``),
        ``remembered`` the one picked last. What it did or needs (the module's list); ``"remember"`` names the
        xemu to remember (never a Flatpak id)."""
        if not iso.is_file():
            raise ValueError(f"{iso}: no saved build there: save the build first, then press Play")
        if xemu.answers(self.played):
            return {"tracking": "played"}
        found = xemu.discover(probes=xemu.Probes(remembered=Path(remembered) if remembered else None))
        running = [x for x in found if x.running]
        with self.lock:
            helped = self.helper is not None and Path(self.helper[1].target).exists() and any(
                x.pid == self.helper[0] for x in running)
        if helped:
            return {"tracking": "helper"}
        if running:
            return {"running": _labels(running), "attach": xemu.can_attach(),
                    "text": ATTACH if xemu.can_attach() else NO_ATTACH}
        if chosen:
            pick = next((x for x in found if str(x.path) == chosen), None)
            if pick is None and not Path(chosen).exists():
                raise ValueError(f"{chosen}: no xemu there")
            pick = pick or xemu.describe(Path(chosen))
        elif len(found) == 1:
            pick = found[0]
        elif not found:
            return {"none": NONE_FOUND}
        else:
            first = next((k for k, x in enumerate(found) if remembered and str(x.path) == remembered), 0)
            return {"choose": [{"label": label, "path": str(x.path)} for label, x in zip(_labels(found), found)],
                    "picked": first}
        run_dir = _private("azurik-play-")
        launch = xemu.plan_launch(pick, iso, run_dir)
        try:
            xemu.spawn(launch)
        except OSError as exc:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise ValueError(f"Can't start xemu: {exc}") from None
        with self.lock:   # Play launches only while no xemu runs: an earlier helper's goes, and it exits
            self.scratch.append(run_dir)
            self.played, old, self.helper = launch.endpoints, self.helper, None
        if old is not None:
            shutil.rmtree(old[2], ignore_errors=True)
        return {"launched": pick.label, "remember": None if pick.flatpak else str(pick.path)}

    def attach(self, pid: int | None = None) -> dict:
        """Read a running xemu of the player's through the admin attach (D257): ``pid`` the one picked from
        ``{"choose"}``. ``{"attached"}`` once the helper serves it."""
        if not xemu.can_attach():
            raise ValueError(NO_ATTACH)
        running = xemu.attachable()
        if not running:
            raise ValueError(NONE_RUNNING)
        if not (readable := [x for x in running if not x.hardened]):
            raise ValueError(HARDENED)
        if pid is None and len(readable) > 1:
            return {"choose": [{"label": label, "pid": x.pid} for label, x in zip(_labels(readable), readable)]}
        pick = next((x for x in readable if pid is None or x.pid == pid), None)
        if pick is None:
            raise ValueError("That xemu isn't running any more: attach again")
        run_dir = _private("azurik-live-")
        try:
            ep = xemu.start_helper(pick.pid, run_dir)
        except (LiveError, OSError) as exc:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise ValueError(f"Can't attach: {exc}") from None
        with self.lock:
            old, self.helper = self.helper, (pick.pid, ep, run_dir)
        if old is not None:   # an earlier helper sees its socket gone and exits
            shutil.rmtree(old[2], ignore_errors=True)
        return {"attached": pick.label}

    def close(self) -> None:
        """The app quits: each private folder goes, and the helper with its socket."""
        with self.lock:
            gone, self.scratch, self.played = [*self.scratch, *([self.helper[2]] if self.helper else [])], [], []
            self.helper = None
        for path in gone:
            with contextlib.suppress(OSError):
                shutil.rmtree(path)
