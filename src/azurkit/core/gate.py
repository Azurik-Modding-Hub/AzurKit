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
writes nothing. A host may keep the images it vouched for across launches
(:data:`STAMPS`): an image with the same path, size, modification and
change times as one it passed is not read again. A stamp keeps what was
checked (``whole``): every file of an image whose build files were checked
first hashes only the rest, and is kept whole, so a check after it, of every
file or a build's, hashes nothing (the Tools tab's Verify every file).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import iso

_MANIFESTS = Path(__file__).with_name("manifests")
BUILD_FILES = ("default.xbe", "filelist.txt", "gamedata/")   # what a build reads: a stamp for a build vouches for these
STAMPS = None
"""A host's store of the images :func:`verify` passed, kept across launches
(``get(key) -> str | None``, ``put(key, str)``; the app's, in its user
cache), or ``None`` (every image is read). A key names the image's path,
size, modification and change times, what was checked and the manifests it
was checked against."""


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
    """The image isn't a release's vanilla image: ``release``, the release
    :func:`verify` checked it against, and ``why``, its first difference
    (each ``None`` where the refusal names no such check)."""

    def __init__(self, message: str, release: Release | None = None, why: str | None = None):
        super().__init__(message)
        self.release, self.why = release, why

    def __reduce__(self):   # its release and why cross a pickle (the app's engine process)
        return type(self), (str(self), self.release, self.why)


@dataclass(frozen=True)
class Stamp:
    """What :func:`verify` found: the release, and the image it checked as
    that image was then (its size, modification and change times). ``whole``:
    every file was checked (also when only a build's check was asked); else
    only :data:`BUILD_FILES`."""
    release: Release
    path: Path
    size: int
    mtime_ns: int
    whole: bool
    ctime_ns: int = 0

    def holds(self, stat: os.stat_result) -> bool:
        """Whether the image is still as it was checked (``stat``, its
        ``os.stat`` now)."""
        return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) == (self.size, self.mtime_ns, self.ctime_ns)

    def vouches(self, path: str) -> bool:
        """Whether the image's file at ``path`` was checked (every file
        when ``whole``)."""
        return self.whole or path.startswith(BUILD_FILES)


def data_path(release: Release) -> Path:
    """Where the user data folder keeps the release's image."""
    from platformdirs import user_data_path
    return user_data_path("AzurKit", appauthor=False) / f"{release.name}.iso"


def find(release: Release) -> Path | None:
    """The file the release's variable names (when it is set), else its image
    in the user data folder; ``None`` when that isn't a file."""
    path = Path(os.environ.get(release.env) or data_path(release))
    return path if path.is_file() else None


_IMAGE_NAMES = ("usa.iso", "europe.iso")   # the names a vanilla image has in a game-data folder


def require_new_output(out: str | os.PathLike, *inputs: str | os.PathLike) -> None:
    """D36 (Modkit's ``require_new_output``): ``ValueError`` unless ``out``
    may be written: it is none of ``inputs`` and inside none that is a
    folder, not a found vanilla image (either release, :func:`find`), not
    directly in the folder of one or of an input named ``usa.iso`` or
    ``europe.iso`` (any case), or in the folder such a link resolves into
    (only there: that folder may be a general one, ``AZURKIT_ISO=~/x.iso``),
    and nowhere inside such a folder named ``iso`` (a game-data folder, which
    holds only the images). Both sides are resolved (``..`` and symlinks,
    dangling ones too) and then compared by file identity, so a link, a
    hardlink or another letter case can't slip through either; an output
    that is itself a link counts where it sits too, as a write's rename
    replaces it there."""
    def same(a: Path, b: Path) -> bool:
        return a.exists() and b.exists() and os.path.samefile(a, b)

    out = Path(out)
    real = out.resolve()
    homes = (real.parent, out.parent.resolve())   # an output link's own folder too
    above = [real, *(d for h in homes for d in (h, *h.parents))]
    protected = [Path(p) for p in inputs]
    images = [p for p in protected if any(n.lower() in _IMAGE_NAMES for n in (p.name, p.resolve().name))]
    for release in RELEASES:
        if (found := find(release)) is not None:
            protected.append(found)
            images.append(found)
    folders = [d for p in images for d in (p.parent, p.resolve().parent)]
    for p in protected:
        if same(real, p):
            raise ValueError(f"output {out} is the same file as {p}; nothing is ever written over an input or "
                             f"a vanilla image")
        if p.is_dir() and any(same(d, p) for d in above):
            raise ValueError(f"output {out} is inside the input folder {p}; nothing is ever written into an input")
    for iso_dir in (d for d in folders if d.name.lower() == "iso"):
        if any(same(d, iso_dir) for d in above):
            raise ValueError(f"output {out} is inside {iso_dir}, which holds only the vanilla image")
    for folder in folders:
        if any(same(h, folder) for h in homes):
            raise ValueError(f"output {out} is inside {folder}, the vanilla ISO's folder")


def missing(release: Release) -> str:
    """Why :func:`find` found no image for the release, and what to do."""
    if named := os.environ.get(release.env):
        return f"{release.env} names no file ({named})"
    return f"set {release.env} or put it at {data_path(release)}"


def verify(path: str | os.PathLike, *, whole: bool = True, releases: tuple[Release, ...] = RELEASES,
           progress: Callable[[int, int], object] | None = None, digests: Mapping[str, str] | None = None,
           kept: Stamp | None = None) -> Stamp:
    """The :class:`Stamp` of the image at ``path`` when it is one of
    ``releases``' vanilla images: every file of it (``whole``), or every one
    a build reads (:data:`BUILD_FILES`; the rest of the image is copied as it
    is). :class:`NotVanillaError` names the first file, in path order, that
    is missing, extra, or has another size or sha256, checked against the
    release whose ``default.xbe`` the image holds, else the one whose folders
    it has (a modded image), else the first of ``releases``. It reads only on
    the caller's thread; ``progress(done, total)`` follows the bytes it
    hashes itself, from 0 to their total. ``digests`` (``{path: sha256}``)
    are a host's hashes of the files :func:`layout` gives, hashed from those
    bytes (the site's WebCrypto, the app's threads), which it compares in
    place of its own; a file they don't name it hashes. ``kept`` is a
    host's stamp of the image (its build files', the image picked); with it,
    or :data:`STAMPS`' stamp, of the image as it is now, the files that
    stamp :meth:`~Stamp.vouches` for aren't hashed again: a whole stamp, or a
    build's for a build's check, is the answer, and every file after a
    build's check hashes only the rest. Its stamp keeps ``whole``, what
    was checked."""
    path = Path(path)
    stat = path.stat()
    held = [s for s in (kept, vouched(path, whole=False, releases=releases, stat=stat))
            if s is not None and Path(s.path) == path and s.release in releases and s.holds(stat)]
    if found := max(held, key=lambda s: s.whole, default=None):
        if found.whole or not whole:
            return found
        digests = dict(digests or {}) | {p: sha for p, (_, sha) in found.release.files.items() if found.vouches(p)}
    with iso.Reader(path) as r:
        have = {e.path: e for e in r.entries()}
        release = _release(r, have, releases, digests or {})
        if why := _first_difference(r, have, release, whole, progress=progress, digests=digests or {}):
            raise NotVanillaError(f"{path} is not the vanilla {release.label} image: {why}", release, why)
    if STAMPS is not None:
        STAMPS.put(_key(path, stat, whole, releases), release.name)
    return Stamp(release, path, stat.st_size, stat.st_mtime_ns, whole, stat.st_ctime_ns)


def vouched(path: str | os.PathLike, *, whole: bool = True, releases: tuple[Release, ...] = RELEASES,
            stat: os.stat_result | None = None) -> Stamp | None:
    """The :class:`Stamp` :data:`STAMPS` holds for the image at ``path`` as
    it is now (``stat``, else its ``os.stat``), checked as :func:`verify`
    checks it (``whole``, against ``releases``), else ``None``; it reads
    nothing of the image. It keeps ``whole``: a build's check asked of an
    image whose every file was checked is a whole stamp."""
    if STAMPS is None:
        return None
    path = Path(path)
    stat = stat or path.stat()
    for checked in (True,) if whole else (True, False):
        if ((name := STAMPS.get(_key(path, stat, checked, releases)))
                and (release := next((r for r in releases if r.name == name), None))):
            return Stamp(release, path, stat.st_size, stat.st_mtime_ns, checked, stat.st_ctime_ns)
    return None


def _key(path: Path, stat: os.stat_result, whole: bool, releases: tuple[Release, ...]) -> str:
    """:data:`STAMPS`' key for the image at ``path`` as ``stat`` finds it."""
    return json.dumps([str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, whole,
                       [[r.name, _manifest_sha256(r.manifest)] for r in releases]])


@functools.cache
def _manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(path: str | os.PathLike, release: Release, changed: dict[str, str], added: tuple[str, ...] = (), *,
          whole: bool = True) -> None:
    """:class:`NotVanillaError` naming the first file, in path order, of the
    image at ``path`` that isn't ``release``'s vanilla file, or for one of
    ``changed`` (``{path: sha256}``), that sha256's; ``added`` names files
    it holds besides (an AzurKit build's root files). Every file is read
    (``whole``), else only ``changed``'s, and the tables of the folders on
    their way (``iso.Reader.lookup``), on the caller's thread."""
    with iso.Reader(path) as r:
        if whole:
            why = _first_difference(r, {e.path: e for e in r.entries()}, release, True, changed, added)
        else:
            have = {p: r.lookup(p) for p in changed}
            why = next((f"{p}: {'missing' if have[p] is None or have[p].is_dir else 'its contents differ'}"
                        for p, sha in sorted(changed.items())
                        if have[p] is None or have[p].is_dir or _sha256(r, have[p]) != sha), None)
        if why:
            raise NotVanillaError(why)


def _sha256(r: iso.Reader, entry: iso.Entry) -> str:
    digest = hashlib.sha256()
    for data in r.chunks(entry):
        digest.update(data)
    return digest.hexdigest()


def layout(path: str | os.PathLike, prefixes: tuple[str, ...] = BUILD_FILES) -> list[tuple[str, int, int]]:
    """Each file of the image at ``path`` under ``prefixes`` (:data:`BUILD_FILES`:
    what a build's :func:`verify` hashes) as ``(path, offset, size)``: the
    bytes a host hashes itself for its ``digests``."""
    with iso.Reader(path) as r:
        return [(e.path, r.base + e.sector * iso.SECTOR, e.size) for e in r.entries()
                if not e.is_dir and e.path.startswith(prefixes)]


def _release(r: iso.Reader, have: dict[str, iso.Entry], releases: tuple[Release, ...],
             digests: Mapping[str, str]) -> Release:
    """The release whose ``default.xbe`` the image holds, else the one whose
    folders it has (USA's 58 and Europe's 6 differ), else the first."""
    xbe = have.get("default.xbe")
    sha = (digests.get(xbe.path) or _sha256(r, xbe)) if xbe and not xbe.is_dir else None
    dirs = {path for path, entry in have.items() if entry.is_dir}
    return (next((rel for rel in releases if rel.files.get("default.xbe", [0, ""])[1] == sha), None)
            or next((rel for rel in releases if set(rel.dirs) == dirs), releases[0]))


def _first_difference(r: iso.Reader, have: dict[str, iso.Entry], release: Release, whole: bool,
                      changed: dict[str, str] | None = None, added: tuple[str, ...] = (), *,
                      progress: Callable[[int, int], object] | None = None,
                      digests: Mapping[str, str] = {}) -> str | None:
    files = release.files | {path: [None, sha] for path, sha in (changed or {}).items()}
    dirs = set(release.dirs)
    checked = sorted(p for p in files.keys() | dirs | have.keys() | set(added) if whole or p.startswith(BUILD_FILES))
    hashed = [p for p in checked if p in have and p in files and not have[p].is_dir and p not in digests]
    total, done = sum(have[p].size for p in hashed), [0]
    if progress is not None and total:
        progress(0, total)

    def counted(r: iso.Reader, entry: iso.Entry) -> str:
        if (sha := digests.get(entry.path)) is not None:
            return sha
        sha = _sha256(r, entry)
        if progress is not None:
            done[0] += entry.size
            progress(done[0], total)
        return sha
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
        if counted(r, entry) != sha:
            return f"{path}: its contents differ"
    return None
