"""The app's build logs (Modkit's Build page's, kept on disk): each Build the
page asks for writes a log in this user's log folder (platformdirs': on macOS
``~/Library/Logs/AzurKit``), so a run can be opened, compared or attached to a
bug report after the app closes. ``build-<time>[-seed<seed>].log`` holds its
header (when, AzurKit's version, the image, the packs, the randomizer's seed and
share string, the whole recipe), then the build's report (the seed's plan left
out) or why it failed, and each save of it. Nothing in a log is a game byte:
the recipe's names and numbers, the report's sites, sizes and sha256s. The
logs stay until Storage's Clear (``kept``'s ``logs``). The Tools tab opens the
folder or the last log (:func:`reveal`)."""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from azurkit import __version__, commit


def folder() -> Path:
    """Where the logs go (not made until the first one is written)."""
    from platformdirs import user_log_path
    return user_log_path("AzurKit", appauthor=False)


def last() -> Path | None:
    """The newest log, or None."""
    logs = sorted(folder().glob("build-*.log"), key=lambda p: p.stat().st_mtime) if folder().is_dir() else []
    return logs[-1] if logs else None


def _seed(recipe: Mapping) -> str | None:
    rando = recipe.get("randomizer")
    return str(rando.get("seed")) if isinstance(rando, Mapping) and rando.get("seed") is not None else None


def start(recipe: Mapping) -> Path | None:
    """A new log for a build of ``recipe``, its header written; None when it can't be written (the build goes on
    with no log, as Modkit's)."""
    now = datetime.datetime.now()
    seed = _seed(recipe)
    safe = "" if seed is None else "-seed" + "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in seed)[:40]
    packs = ", ".join(sorted(recipe.get("packs") or {})) or "(none)"   # the packs ticked, each with its settings
    rando = recipe.get("randomizer") if isinstance(recipe.get("randomizer"), Mapping) else None
    head = (f"# AzurKit build log\n# started   : {now.isoformat(timespec='seconds')}\n"
            f"# AzurKit   : {__version__}{f' (commit {c[:12]})' if (c := commit()) else ''}\n"
            f"# image     : {recipe.get('iso')}\n# packs     : {packs}\n"
            f"# randomizer: {f'seed {seed}, share {rando.get('share')}' if rando else '(none)'}\n"
            f"# recipe    : {json.dumps({k: v for k, v in recipe.items() if k != 'iso'}, sort_keys=True, default=str)}\n# ---\n")
    try:
        folder().mkdir(parents=True, exist_ok=True)
        for n in range(1, 100):   # two builds in one second each get their own
            path = folder() / f"build-{now:%Y%m%d-%H%M%S}{safe}{'' if n == 1 else f'-{n}'}.log"
            try:
                with open(path, "x", encoding="utf-8") as log:
                    log.write(head)
                return path
            except FileExistsError:
                continue
    except OSError:
        pass
    return None


def add(path: Path | None, text: str) -> None:
    """``text`` at the end of the log ``path`` (None: none was written); a log that can't be written is let be."""
    if path is not None:
        with contextlib.suppress(OSError), open(path, "a", encoding="utf-8") as log:
            log.write(text if text.endswith("\n") else text + "\n")


def built(path: Path | None, report: Mapping, size: int) -> None:
    """The build's report (its plan left out: the seed and share string replay it) and size."""
    add(path, f"built: {size} bytes\nreport: {json.dumps({k: v for k, v in report.items() if k != 'plan'}, indent=1)}\n"
              f"# ---\n# finished: {datetime.datetime.now().isoformat(timespec='seconds')}")


def failed(path: Path | None, why: str) -> None:
    add(path, f"failed: {why}\n# ---\n# finished: {datetime.datetime.now().isoformat(timespec='seconds')}")


def reveal(path: Path, platform: str = sys.platform) -> None:
    """Open ``path`` (the folder, or a log) in this computer's file manager or text viewer; ``OSError`` when it
    can't."""
    if platform == "win32":
        os.startfile(path)   # noqa: S606 (the player's own folder or log)
        return
    try:
        subprocess.run(["open" if platform == "darwin" else "xdg-open", str(path)], check=True, timeout=30,
                       stdin=subprocess.DEVNULL, capture_output=True)
    except subprocess.SubprocessError as exc:
        raise OSError(f"can't open {path}: {exc}") from None
