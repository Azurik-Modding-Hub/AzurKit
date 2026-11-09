"""The wheel: built from this checkout (``web_tools.wheel``), it carries
every file of the package, each module's bytecode, the checked
randomizer database (Step 4.3g) and the commit it was built from (About's,
Step 4.4rel-a), and nothing the leak guard refuses, and
installs alone in a clean venv (only its declared dependencies, at the
lock's versions, offline: ``web_tools.install``; the wheel declares
pyproject's dependencies, so the venv holds just what it declares) where
every module imports, the ``azurkit`` command runs and the database loads
as shipped, never checked again. Its metadata, PyPI's page, links the
project."""

from __future__ import annotations

import email
import hashlib
import json
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import azurkit
from azurkit import __version__
from scripts import web_tools
from tests import _leak_guard

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/Azurik-Modding-Hub/AzurKit"
IMPORT_ALL = ("import importlib, pkgutil, azurkit; "
              "[importlib.import_module(m.name) for m in pkgutil.walk_packages(azurkit.__path__, 'azurkit.')]")
DECLARED = "import json; from importlib.metadata import requires; print(json.dumps(requires('azurkit') or []))"
SHIPPED_ONLY = ("import sys; from azurkit.tools.randomizer import dbcache; "
                "from azurkit.tools.randomizer.planner.loader import DATA_DIR; "
                "dbcache.load(DATA_DIR, lambda root: sys.exit(f'{root}: checked, not the shipped database'))")


def _names(requirements: list[str]) -> list[str]:
    """The distributions the requirements name, PEP 503-normalized, sorted."""
    return sorted(re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9._-]+", r)[0]).lower() for r in requirements)


def test_pypis_page_links_the_site_the_source_the_issues_and_the_developer_log(tmp_path):
    """PyPI's page for a release never changes after its upload (Step
    4.4ci51), so the wheel's metadata links the site (the app's ``SITE``,
    which its share links open), the repository, its Issues and the
    developer log on ``main``, and its description is README, as PyPI
    shows it."""
    from azurkit import app
    with zipfile.ZipFile(web_tools.wheel(tmp_path / "dist")) as zf:
        metadata = email.message_from_string(zf.read(f"azurkit-{__version__}.dist-info/METADATA").decode("utf-8"))
    assert metadata.get_all("Project-URL") == [f"Homepage, {app.SITE}", f"Source, {REPO}", f"Issues, {REPO}/issues",
                                                f"Changelog, {REPO}/blob/main/docs/DEVLOG.md"]
    assert (ROOT / "docs" / "DEVLOG.md").is_file()
    assert metadata.get_payload() == (ROOT / "README.md").read_text(encoding="utf-8")


def test_pypis_page_calls_a_release_from_1_0_on_stable():
    """A 1.0.0 page said Pre-Alpha, and PyPI never changes it after the
    upload (Step 4.4ci51): from version 1 on the one Development Status
    classifier is Production/Stable."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert int(project["version"].split(".")[0]) >= 1
    assert [c for c in project["classifiers"] if c.startswith("Development Status ::")] == [
        "Development Status :: 5 - Production/Stable"]


def test_readmes_links_are_absolute_so_pypis_page_follows_them():
    """PyPI shows README (the description, above) with no repository round
    it, so a relative link, image or ``#`` anchor there goes nowhere (Step
    4.4ci51): each one outside code is an https URL, each into this
    repository's ``main`` names a path that is here, and each anchor into its
    page a heading of README's."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    prose = re.sub(r"```.*?```|`[^`\n]*`", "", readme, flags=re.DOTALL)
    targets = [*re.findall(r"\]\(\s*<?([^)\s>]*)", prose), *re.findall(r"""\b(?:src|href)\s*=\s*["']([^"']*)""", prose),
               *re.findall(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)", prose, flags=re.MULTILINE)]
    assert targets and [t for t in targets if not t.startswith("https://")] == []
    raw = "https://raw.githubusercontent.com/Azurik-Modding-Hub/AzurKit/main/"
    paths = [m[1] for t in targets if (m := re.match(rf"(?:{REPO}/(?:blob|tree)/main/|{raw})([^#?]+)", t))]
    assert paths and [p for p in paths if not (ROOT / p).exists()] == []
    headings = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in re.findall(r"^#+ (.+)", prose, re.M)}
    assert [t for t in targets if t.startswith(f"{REPO}#") and t.partition("#")[2] not in headings] == []


def test_readme_and_about_name_what_of_the_game_ships():
    """The package (so the app and the site) carries game files byte for
    byte (a disc file's sha256 in either release's manifest: config.xbr,
    the Data tab's), and the page pictures drawn from the game's files
    (``web/characters/``, ``web/art/``), so README's What you need (Step
    4.4ci53 moved the text there from its Game data) and the About tab name
    each such file and the pictures, and README says the player's image
    never leaves their computer (Step 4.4ci51)."""
    from azurkit.core import gate
    disc = {sha for release in gate.RELEASES for _, sha in release.files.values()}
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "src/azurkit", "web"], capture_output=True,
                             text=True, check=True).stdout.split()
    games = sorted({Path(rel).name for rel in tracked
                    if rel.startswith("src/") and hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() in disc})
    assert games and any(rel.startswith(("web/characters/", "web/art/")) and rel.endswith(".png") for rel in tracked)
    readme = (ROOT / "README.md").read_text(encoding="utf-8").partition("\n## What you need\n")[2].partition("\n## ")[0]
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    about = re.search(r'<section id="about".*?<p>(.*?)</p>', page, re.DOTALL)[1]
    for text in (" ".join(readme.split()), " ".join(about.split())):
        assert [name for name in games if name not in text] == [], text
        assert "pictures drawn from the game's files" in text, text
    assert "your image never leaves it" in " ".join(readme.split())


def test_the_wheel_carries_the_package_and_installs_alone_in_a_clean_venv(tmp_path):
    def run(*argv: str) -> str:
        return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=300).stdout
    wheel = web_tools.wheel(tmp_path / "dist")
    with zipfile.ZipFile(wheel) as zf:
        names = {n for n in zf.namelist() if not n.endswith("/")}
        assert [f"{n}: {why}" for n in sorted(names) if (why := _leak_guard.check_bytes(n, zf.read(n)))] == []
    tracked = set(run("git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard",
                      "src/azurkit").split())
    package = {rel.removeprefix("src/") for rel in tracked}
    pyc = {f"{folder}/__pycache__/{name[:-3]}.{sys.implementation.cache_tag}.pyc"
           for folder, _, name in (rel.rpartition("/") for rel in package if rel.endswith(".py"))}
    (shipped,) = {n for n in names if n.startswith(f"{web_tools.SHIPPED}/") and n.endswith(".pickle")}
    stamp = f"azurkit/{azurkit.STAMP}"   # the commit About names (the site's About test reads it)
    assert {n for n in names if not n.startswith(f"azurkit-{__version__}.dist-info/")} == (
        package | pyc | {shipped, stamp})
    python = web_tools.install(wheel, tmp_path / "venv")
    scripts = Path(python).parent
    dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    assert _names(json.loads(run(python, "-I", "-c", DECLARED))) == _names(dependencies)
    run(python, "-I", "-c", IMPORT_ALL)
    run(python, "-I", "-c", SHIPPED_ONLY)
    assert run(str(scripts / "azurkit"), "--version").strip() == f"azurkit {__version__}"


# --- Step 4.28f: Modkit's unpinned packaging pin, ported -------------------------------------------------------


def test_running_python_version_is_declared_in_classifiers():
    """The Python a run uses (3.14 only, its release's) is one pyproject's
    classifiers declare, so PyPI's page says the versions AzurKit is tested
    on (Modkit's packaging pin)."""
    classifiers = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["classifiers"]
    declared = {c.rsplit("::", 1)[1].strip() for c in classifiers
                if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", c)}
    assert f"{sys.version_info.major}.{sys.version_info.minor}" in declared, sorted(declared)
