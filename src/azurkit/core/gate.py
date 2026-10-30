"""The two releases AzurKit builds from, USA and Europe: where the player
keeps each one's image, and the gate that says whether an image is one of
them, unchanged.

Each image is the file its release's variable names (``AZURKIT_ISO``,
``AZURKIT_ISO_EUROPE``), or when that is unset, ``usa.iso`` or
``europe.iso`` in the user data folder (``platformdirs``'
``user_data_dir("AzurKit")``, imported only to find it: the web page's
worker loads the wheel without its dependencies and passes the image's path).

:func:`verify` is the gate (D27). It tells the release by the sha256 of the
image's ``default.xbe`` (else by its folders), then checks the image's files against that
release's manifest (``manifests/<release>.json``: each folder, and each
file's size and sha256, Modkit's at its last cut, AzurKit's own since Step 4.12a), one :data:`iso.CHUNK` read
at a time on the caller's thread, and names the first file (in path order)
that differs. A dump that isn't the whole vanilla image (another trim, or a
whole disc) passes when its files match. It returns a :class:`Stamp`; it
writes nothing.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import iso

_MANIFESTS = Path(__file__).with_name("manifests")
BUILD_FILES = ("default.xbe", "filelist.txt", "gamedata/")   # what a build reads: a stamp for a build vouches for these


@dataclass(frozen=True)
class Release:
    name: str        # "usa" or "europe": its image's file name and its pytest marker
    label: str       # how messages name it
    iso_sha256: str  # the whole vanilla image
    iso_size: int
    env: str         # the variable that names its image
    manifest: Path   # each folder of its image, and each file's [size, sha256]

    @property
    def files(self) -> dict[str, list]:
        return _manifest(self.manifest)["files"]

    @property
    def dirs(self) -> list[str]:
        return _manifest(self.manifest)["dirs"]


USA = Release("usa", "USA", "6989c84e96ebcb5d668ccdd9942f737d2e36843e7db459996ed077e6161d84be",
              2_747_006_976, "AZURKIT_ISO", _MANIFESTS / "usa.json")
EUROPE = Release("europe", "Europe", "77fb736e5656333080733ba894ceb1c505a83e53339441c8ac563fcccbc37e99",
                 2_313_027_584, "AZURKIT_ISO_EUROPE", _MANIFESTS / "europe.json")
RELEASES = (USA, EUROPE)


@functools.cache
def _manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class NotVanillaError(ValueError):
    """The image isn't a release's vanilla image."""


@dataclass(frozen=True)
class Stamp:
    """What :func:`verify` found: the release, and the image it checked as
    that image was then (its size and modification time). ``whole``: every
    file was checked; else only :data:`BUILD_FILES`."""
    release: Release
    path: Path
    size: int
    mtime_ns: int
    whole: bool


def data_path(release: Release) -> Path:
    """Where the user data folder keeps the release's image."""
    from platformdirs import user_data_path
    return user_data_path("AzurKit", appauthor=False) / f"{release.name}.iso"


def find(release: Release) -> Path | None:
    """The file the release's variable names (when it is set), else its image
    in the user data folder; ``None`` when that isn't a file."""
    path = Path(os.environ.get(release.env) or data_path(release))
    return path if path.is_file() else None


def missing(release: Release) -> str:
    """Why :func:`find` found no image for the release, and what to do."""
    if named := os.environ.get(release.env):
        return f"{release.env} names no file ({named})"
    return f"set {release.env} or put it at {data_path(release)}"


def verify(path: str | os.PathLike, *, whole: bool = True, releases: tuple[Release, ...] = RELEASES) -> Stamp:
    """The :class:`Stamp` of the image at ``path`` when it is one of
    ``releases``' vanilla images: every file of it (``whole``), or every one
    a build reads (:data:`BUILD_FILES`; the rest of the image is copied as it
    is). :class:`NotVanillaError` names the first file, in path order, that
    is missing, extra, or has another size or sha256, checked against the
    release whose ``default.xbe`` the image holds, else the one whose folders
    it has (a modded image), else the first of ``releases``. It reads only on
    the caller's thread."""
    path = Path(path)
    stat = path.stat()
    with iso.Reader(path) as r:
        have = {e.path: e for e in r.entries()}
        release = _release(r, have, releases)
        if why := _first_difference(r, have, release, whole):
            raise NotVanillaError(f"{path} is not the vanilla {release.label} image: {why}")
    return Stamp(release, path, stat.st_size, stat.st_mtime_ns, whole)


def check(path: str | os.PathLike, release: Release, changed: dict[str, str], added: tuple[str, ...] = (), *,
          whole: bool = True) -> None:
    """:class:`NotVanillaError` naming the first file, in path order, of the
    image at ``path`` that isn't ``release``'s vanilla file, or for one of
    ``changed`` (``{path: sha256}``), that sha256's; ``added`` names files
    it holds besides (an AzurKit build's root files). Every file is read
    (``whole``), else only ``changed``'s, on the caller's thread."""
    with iso.Reader(path) as r:
        have = {e.path: e for e in r.entries()}
        if whole:
            why = _first_difference(r, have, release, True, changed, added)
        else:
            why = next((f"{p}: {'missing' if p not in have or have[p].is_dir else 'its contents differ'}"
                        for p, sha in sorted(changed.items())
                        if p not in have or have[p].is_dir or _sha256(r, have[p]) != sha), None)
        if why:
            raise NotVanillaError(why)


def _sha256(r: iso.Reader, entry: iso.Entry) -> str:
    digest = hashlib.sha256()
    for data in r.chunks(entry):
        digest.update(data)
    return digest.hexdigest()


def _release(r: iso.Reader, have: dict[str, iso.Entry], releases: tuple[Release, ...]) -> Release:
    """The release whose ``default.xbe`` the image holds, else the one whose
    folders it has (USA's 58 and Europe's 6 differ), else the first."""
    xbe = have.get("default.xbe")
    sha = _sha256(r, xbe) if xbe and not xbe.is_dir else None
    dirs = {path for path, entry in have.items() if entry.is_dir}
    return (next((rel for rel in releases if rel.files.get("default.xbe", [0, ""])[1] == sha), None)
            or next((rel for rel in releases if set(rel.dirs) == dirs), releases[0]))


def _first_difference(r: iso.Reader, have: dict[str, iso.Entry], release: Release, whole: bool,
                      changed: dict[str, str] | None = None, added: tuple[str, ...] = ()) -> str | None:
    files = release.files | {path: [None, sha] for path, sha in (changed or {}).items()}
    dirs = set(release.dirs)
    checked = sorted(p for p in files.keys() | dirs | have.keys() | set(added) if whole or p.startswith(BUILD_FILES))
    for path in checked:
        entry = have.get(path)
        if entry is None:
            return f"{path}: missing"
        if path in added and not entry.is_dir:
            continue
        if path in dirs:
            if not entry.is_dir:
                return f"{path}: a file, where vanilla has a folder"
            continue
        if path not in files:
            return f"{path}: not in the vanilla image"
        size, sha = files[path]
        if entry.is_dir or (size is not None and entry.size != size):
            return f"{path}: {'a folder' if entry.is_dir else f'{entry.size:,} B'}, where vanilla has {size:,} B"
        if _sha256(r, entry) != sha:
            return f"{path}: its contents differ"
    return None
