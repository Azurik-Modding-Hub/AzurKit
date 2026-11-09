"""AzurKit: patch packs, sliders, a randomizer and character swaps for
Azurik: Rise of Perathia, built from the player's own copy of the game.

The layers run ``core <- edits <- tools <- sdk <- {cli, app}``
(``pyproject.toml``'s import-linter contracts; ``tests/test_contracts.py``).
"""

import functools
import sys
from pathlib import Path

__version__ = "1.0.2"

STAMP = "commit.txt"
"""The file beside this one in a wheel or the frozen app that names the
commit its build was made from (``scripts/web_tools.py``'s ``wheel``,
``scripts/freeze.py``); a source tree has none."""


def platform() -> str:
    """Where this engine runs, which About names (Modkit's Settings page's
    Platform line): the system and the processor (``Darwin arm64``,
    ``Windows AMD64``), or in a browser Pyodide's version and WebAssembly."""
    if sys.platform == "emscripten":
        import pyodide
        return f"Pyodide {pyodide.__version__}, WebAssembly"
    import platform as host
    return f"{host.system()} {host.machine()}"


def head(root: Path) -> str | None:
    """The commit checked out at ``root`` when ``root`` is the top of a git
    work tree and this computer's git answers (asked here, nothing fetched),
    else None."""
    import subprocess
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel", "HEAD"],
                              capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        top, sha = done.stdout.splitlines() if done.returncode == 0 else ("", "")
        return sha if top and Path(top).samefile(root) else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


@functools.cache
def commit() -> str | None:
    """The commit this AzurKit was built from, which About shows beside the
    version: the one its wheel's or frozen app's build wrote (:data:`STAMP`),
    else, run from a git checkout of AzurKit, its HEAD (:func:`head`); None
    from a build or source tree without git (the site's Pyodide and the
    frozen app ask no git)."""
    here = Path(__file__).resolve().parent
    if (stamp := here / STAMP).is_file():
        return stamp.read_text(encoding="utf-8").strip() or None
    if getattr(sys, "frozen", False) or sys.platform == "emscripten":
        return None
    return head(here.parent.parent)
