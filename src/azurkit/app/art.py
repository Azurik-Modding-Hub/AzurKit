"""The app's pictures for the tracker (Step 4.3f, D961): Modkit's level
maps (with their detail pictures, Step 4.3l), world map and item icons,
which ship with the page (``web/art/``, drawn once from the game by
``scripts/record_goldens.py``'s art family, never in the app): ``api/art`` answers :meth:`Drawing.status` and ``GET
art/<version>/<name>`` serves a picture from :func:`folder`, in the frozen
app's bundle or the checkout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from azurkit.tools.randomizer import tracking


def folder() -> Path:
    """Where the pictures of this drawing's version (``tracking.ART_VERSION``) are."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "web" / "art" / tracking.ART_VERSION


class Drawing:
    """The pictures in :func:`folder`: :meth:`status`."""

    def __init__(self, where: Path | None = None):
        self._where = where

    @property
    def where(self) -> Path:
        """The folder (:func:`folder`, read when asked)."""
        return self._where or folder()

    def status(self) -> dict:
        """``{"version", "index": maps.json's object, "icons": the icons'
        pictures' names, "detail": {level: how many times finer its detail
        pictures are}}`` (Step 4.3l: ``index.json``'s), ``index`` and
        ``icons`` null and ``detail`` empty where :attr:`where` holds no
        pictures (the page then shows the levels' grid and chips)."""
        maps, shipped = self.where / "maps.json", self.where.parent / "index.json"
        found = maps.is_file() and shipped.is_file()
        named = json.loads(shipped.read_text(encoding="utf-8")) if found else {}
        return {"version": tracking.ART_VERSION,
                "index": json.loads(maps.read_text(encoding="utf-8")) if found else None,
                "icons": named.get("icons"), "detail": named.get("detail", {})}
