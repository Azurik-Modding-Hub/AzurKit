"""The app's pictures for the tracker (Step 4.2c3): drawn from the
player's image the first time the tracker needs them (``sdk.art``, one part
at a time on a thread), kept in the user cache folder (platformdirs) under
the drawing's version (``tracking.ART_VERSION``), never in the bundle, and
served to the page from there (``GET art/<version>/<name>``).

A part's files are written whole or not at all: each picture as a PNG
(``icons/<icon>.png``, each floor's ``<floor>.png``), then the part's
record last (``<part>.part.json``: a level's maps.json entry, its
world-map thumbnail beside it as ``<level>.thumb.png``), so a part whose
record is there is all there. Once every level of the world map's is, the
world map and the index (``world.png``, ``maps.json``, ``sdk.art_world``). A drawing stops
between parts when the app closes (``stop``); the next one goes on from
the parts already kept.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from azurkit import sdk
from azurkit.tools.randomizer import tracking


def folder() -> Path:
    """Where the pictures of this version are kept."""
    from platformdirs import user_cache_path
    return user_cache_path("AzurKit", appauthor=False) / "art" / tracking.ART_VERSION


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.part")
    part.write_bytes(data)
    part.replace(path)


class Drawing:
    """The pictures in :func:`folder`: :meth:`status`, and :meth:`start`, which draws what isn't there."""

    def __init__(self, where: Path | None = None):
        self._where = where
        self.lock, self.stopped = threading.Lock(), threading.Event()
        self.thread: threading.Thread | None = None
        self.part: str | None = None      # the part being drawn
        self.error: str | None = None     # why the last drawing stopped

    @property
    def where(self) -> Path:
        """The folder (platformdirs' cache folder, read when asked: a test's HOME is its own)."""
        return self._where or folder()

    def done(self) -> list[str]:
        return [p for p in tracking.ART_PARTS if (self.where / f"{p}.part.json").is_file()]

    def status(self) -> dict:
        """``{"version", "parts": [part, ...] done, "total", "drawing": the part being drawn or null, "error",
        "index": maps.json's object once the world map is drawn, else null, "levels": {level: entry} of the
        levels drawn, "icons": the icons' pictures' names once drawn, else null}``."""
        done = self.done()
        levels = {}
        for part in done:
            if part != "icons":
                levels[part] = json.loads((self.where / f"{part}.part.json").read_text(encoding="utf-8"))["entry"]
        index, icons = self.where / "maps.json", self.where / "icons.part.json"
        with self.lock:
            drawing, error = self.part, self.error
        return {"version": tracking.ART_VERSION, "parts": done, "total": len(tracking.ART_PARTS), "drawing": drawing,
                "error": error, "levels": levels,
                "icons": json.loads(icons.read_text(encoding="utf-8"))["pictures"] if "icons" in done else None,
                "index": json.loads(index.read_text(encoding="utf-8")) if index.is_file() else None}

    def start(self, iso: str) -> None:
        """Draw what isn't there from the image at ``iso``, on a thread (one at a time)."""
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.error = None
            self.thread = threading.Thread(target=self._run, args=(iso,), name="azurkit-art", daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.stopped.set()

    def _run(self, iso: str) -> None:
        try:
            for part in tracking.ART_PARTS:
                if self.stopped.is_set():
                    return
                if (self.where / f"{part}.part.json").is_file():
                    continue
                with self.lock:
                    self.part = part
                got = sdk.art(iso, part)
                for name, png in got["pictures"].items():
                    _write(self.where / f"{name}.png", png)
                if "thumb" in got:
                    _write(self.where / f"{part}.thumb.png", got["thumb"])
                record = {"entry": got["entry"]} if "entry" in got else {"pictures": sorted(got["pictures"])}
                _write(self.where / f"{part}.part.json", json.dumps(record).encode())
            if not (self.where / "maps.json").is_file() and set(tracking.GRID) <= set(self.done()):
                parts = {level: {"entry": json.loads((self.where / f"{level}.part.json").read_text("utf-8"))["entry"],
                                 "thumb": (self.where / f"{level}.thumb.png").read_bytes()} for level in tracking.GRID}
                world = sdk.art_world(parts)
                _write(self.where / "world.png", world["pictures"]["world"])
                _write(self.where / "maps.json", world["text"].encode())
        except (OSError, ValueError) as exc:   # the sdk's refusals name what and why, never game bytes
            with self.lock:
                self.error = f"The maps couldn't be drawn: {exc}"
        finally:
            with self.lock:
                self.part = None
