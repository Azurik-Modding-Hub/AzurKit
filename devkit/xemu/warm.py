"""Warm build states shared by one xemu sitting's sandboxes (Step X.81d, D776; from Modkit, Step 4.14a1).

The harness's ``boot_build`` boots a build cold (a reset into its disc and the menu walk: 12 s
median null, 11 s to minutes offscreen by host load) and saves the result as a warm state, ``b-<iso sha12>-<tag>``, in its sandbox's
own HDD clone, so that sandbox boots it again by one ``loadvm`` (0.3 s; Step X.9). A sitting runs many sandboxes (a
driver run each, a serve each, a yield's new one), and each booted the sitting's builds cold again: 1,138 of 3,661
boots from 10-22 to 10-26 (6.1 h) were a (build, tag) another sandbox of the same sitting had booted
(Step X.81d).

A :class:`WarmStore` is one sitting's seat-private drive store, kept in the private snapshot store (guest RAM holds
console key material: never ``$EV``, a repo or D98's oracle drive, D102). After a cold boot the sandbox publishes
its HDD clone, the warm states inside, as a new drive that is never written again (``drive-<n>.qcow2``,
APFS-cloned), beside the discs those states name. A later sandbox of the sitting clones the drive with the most
states before its xemu starts, or at a relaunch, and adopts them (``plan``), so each (build, tag) cold-boots once a
sitting. Two sandboxes that publish at once leave two drives (an internal snapshot can't move between drives): the
next adopts the larger, and a drive whose states a newer one holds too is deleted. Two sandboxes that boot the same
(build, tag) at the same moment both boot it cold. A store is keyed by the sitting (its evidence folder), the xemu
binary, the release and determinism; one no sandbox used for ``IDLE_S`` is deleted by the next one opened. Stdlib
only; for dev tools, never the runtime.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from devkit.xemu import queue

INDEX = "warm.json"   # {"key", "n", "drives": {drive name: {state tag: {"disc", "level", "saved"}}}}
HDD = "xbox_hdd.qcow2"   # a sandbox's drive in its W
IDLE_S = 2 * 3600.0   # a store no sandbox adopted from or published to for this long goes at the next open: 99.9 %
#                       of a sitting's boots since 10-22 came within 2 h of its previous one (Step X.81d's evidence);
#                       its discs are whole build ISOs, so it isn't kept longer
_DRIVE = re.compile(r"drive-(\d+)\.qcow2")


def clone(src: Path, dst: Path) -> None:
    """``src`` as ``dst`` (replacing it): an APFS clone on macOS, a copy elsewhere; through a ``.part`` file, so no
    reader ever sees half a drive."""
    part = dst.with_name(dst.name + ".part")
    part.unlink(missing_ok=True)
    if sys.platform == "darwin":
        subprocess.run(["cp", "-c", str(src), str(part)], check=True)
    else:
        shutil.copyfile(src, part)
    os.replace(part, dst)


class WarmStore:
    """One sitting's warm drives under ``root`` (mode 700): ``key`` names the sitting, the xemu binary, the release
    and determinism (a state loads only where all four match)."""

    def __init__(self, root: Path | str, key: dict):
        self.root, self.key = Path(root), dict(key)
        self.dir = self.root / hashlib.sha256(json.dumps(self.key, sort_keys=True).encode()).hexdigest()[:16]

    @contextlib.contextmanager
    def _locked(self):
        """The store's lock and its index; a lock file ``sweep`` deleted while this waited is taken again."""
        while True:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.dir.mkdir(mode=0o700, exist_ok=True)
            fd = os.open(self.dir / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
            try:
                queue.lock(fd)
                if os.fstat(fd).st_nlink:
                    yield self._read()
                    return
            finally:
                os.close(fd)   # closing the descriptor drops its lock

    def _read(self) -> dict:
        try:
            return json.loads((self.dir / INDEX).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"key": self.key, "n": 0, "drives": {}}

    def _write(self, ix: dict) -> None:
        tmp = self.dir / f"{INDEX}.part"
        tmp.write_text(json.dumps(ix, indent=1), encoding="utf-8")
        os.replace(tmp, self.dir / INDEX)

    @staticmethod
    def _pick(drives: dict[str, dict], held: set[str], saved: set[str], need: str | None) -> str | None:
        """The drive a sandbox holding the warm states ``held`` and the tags ``saved`` swaps its own for: none while
        it saved a tag no drive holds (a parked start, a spot: the swap would lose it); for ``need``, the drive
        holding it that keeps the most of ``held`` (then the most states, then the newest); else one holding all of
        ``held`` and more (the most states, then the newest)."""
        if not saved <= {t for s in drives.values() for t in s}:
            return None
        order = {d: int(_DRIVE.fullmatch(d)[1]) for d in drives}
        if need is not None:
            fits = [d for d, s in drives.items() if need in s]
            return max(fits, key=lambda d: (len(held & set(drives[d])), len(drives[d]), order[d]), default=None)
        fits = [d for d, s in drives.items() if held < set(s)]
        return max(fits, key=lambda d: (len(drives[d]), order[d]), default=None)

    def plan(self, tag: str, held, saved) -> str:
        """How a sandbox boots the warm state ``tag``: ``"warm"`` (its drive holds it: one ``loadvm``), ``"adopt"``
        (another sandbox of the sitting published it: swap the sandbox's drive for that one with ``adopt``, then
        load it warm) or ``"cold"`` (boot it, save it, ``publish``). ``held``: the warm states the sandbox's drive
        holds; ``saved``: every tag it saved (``_pick``: one no drive holds keeps its drive)."""
        if tag in held:
            return "warm"
        with self._locked() as ix:
            return "adopt" if self._pick(ix["drives"], set(held), set(saved), tag) else "cold"

    def adopt(self, w: Path, held=(), saved=(), need: str | None = None) -> dict[str, dict]:
        """Clone the drive ``_pick`` chooses over ``w``'s, with the discs its states name; returns those states, all
        the warm states ``w``'s drive now holds ({} when none qualifies: ``w``'s drive left as it was). Only while
        ``w``'s xemu is down."""
        with self._locked() as ix:
            best = self._pick(ix["drives"], set(held), set(saved), need)
            if best is None:
                return {}
            states = ix["drives"][best]
            for m in states.values():
                if not (w / m["disc"]).exists():
                    clone(self.dir / m["disc"], w / m["disc"])
            clone(self.dir / best, w / HDD)
            os.utime(self.dir / INDEX)   # in use: not idle
            return {t: {**m, "drive": best} for t, m in states.items()}

    def publish(self, w: Path, states: dict[str, dict]) -> str:
        """``w``'s drive (its guest halted, the drive flushed) as the store's next drive holding ``states``
        ({tag: {"disc", "level", ...}}: every warm state it holds), the discs they name cloned beside it; a drive
        whose states it holds too, and a disc no drive names, deleted. Returns the new drive's name."""
        with self._locked() as ix:
            ix["n"] += 1
            name = f"drive-{ix['n']}.qcow2"
            keep = {t: {k: m[k] for k in ("disc", "level", "saved") if k in m} for t, m in states.items()}
            for m in keep.values():
                if not (self.dir / m["disc"]).exists():
                    clone(w / m["disc"], self.dir / m["disc"])
            clone(w / HDD, self.dir / name)
            for d, s in list(ix["drives"].items()):
                if set(s) <= set(keep):
                    (self.dir / d).unlink(missing_ok=True)
                    del ix["drives"][d]
            ix["drives"][name] = keep
            discs = {m["disc"] for s in ix["drives"].values() for m in s.values()}
            for p in self.dir.glob("b-*.iso"):
                if p.name not in discs:
                    p.unlink()
            self._write(ix)
            return name


def sweep(root: Path | str, idle_s: float = IDLE_S, now: float | None = None) -> list[str]:
    """Delete the stores under ``root`` no sandbox adopted from or published to for ``idle_s`` (their index's
    mtime, else the folder's), each under its own lock, taken without waiting (a store in use is left); returns
    their names."""
    now = time.time() if now is None else now
    gone = []
    for d in sorted(Path(root).glob("*")):
        if not d.is_dir():
            continue
        ix = d / INDEX
        try:
            if now - (ix if ix.exists() else d).stat().st_mtime < idle_s:
                continue
            fd = os.open(d / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        except OSError:   # gone meanwhile
            continue
        try:
            queue.lock(fd, wait=False)
            if os.name == "nt":   # no file open there can be removed: its lock file's lock ends here
                os.close(fd)
                fd = None
            shutil.rmtree(d)
            gone.append(d.name)
        except OSError:   # in use (the lock)
            continue
        finally:
            if fd is not None:
                os.close(fd)
    return gone
