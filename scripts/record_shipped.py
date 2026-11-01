"""Record the swap's shipped answers (D995; ``src/azurkit/tools/characters/
shipped.py``) from fresh dresses on the player's images, on both releases:
each species' and built-in variant's size at its defaults (``shipped.json``'s
``size`` rows), the jiggle places of a parent those dresses work out
(``places`` rows) and the whole plan of each of :data:`PLANS` at the page's
defaults, the packs on by default (its ``plan`` rows, each answer an
``AZKP1`` file in a clone of Azurik-Custom-Content, ``--content``).

    uv run --locked python scripts/record_shipped.py [--check] [--content CLONE] [--workers N]

Re-record when ``tests/test_characters.py``'s pin is red (a change to the
swap's bytes or to what it reads): each answer file is written to
``CLONE/variants/<entry>/shipped/<release>-<sha12>.azkp`` (that folder's
other answers removed), and its entry then takes them at a new version
(``azurkit content check --write`` there, the version bumped by hand).
``--check`` writes nothing and exits 1 naming each row a fresh dress
doesn't give and, with ``--content``, each answer file there that isn't
its row's (the release check's); off the table's recording host a row holds
close enough (D1016, ``shipped.agrees``). The images are the ones the gate finds;
the plans, and the sizes of the variants that wear booblord, read her files
in the content folder (``AZURKIT_CONTENT``: ``azurkit content install
booblord``). The dresses run in ``--workers`` processes (4). No game byte
is printed: lengths and sha256[:12].
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.tools import characters, mods
from azurkit.tools.characters import _player_variants as variants
from azurkit.tools.characters import picker, ports, shipped

shipped.OFF = True   # every dress fresh, in each process that imports this
PLANS = ({"species": "booblord"},)
"""The plans shipped: booblord's at the page's defaults (RS2's L1; the
built-in species' are left out of v1.0 until their total size is known)."""
_VANILLA: dict[str, ports.Vanilla] = {}


def recipes() -> list[dict]:
    """The recipes whose size is shipped: each species the Characters tab
    lists and each built-in variant, at its defaults."""
    names = [row[0] for row in picker.species_list()] + list(variants.builtins())
    return [characters.normalize({"species": name}) for name in dict.fromkeys(names)]


def _release(name: str) -> gate.Release:
    return next(r for r in gate.RELEASES if r.name == name)


def _vanilla(name: str, path: str) -> ports.Vanilla:
    """The release's image, checked once a process."""
    if name not in _VANILLA:
        stamp = gate.verify(Path(path), whole=False, releases=(_release(name),))
        _VANILLA[name] = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
    return _VANILLA[name]


def _size(job: tuple) -> tuple[dict | None, list[dict]]:
    """``(recipe, release, image)``'s size row, ``None`` for a body the swap refuses (a build of it is refused the
    same way), and the places rows of the parent its dress worked out."""
    recipe, name, path = job
    shipped.SEEN = []
    try:
        value = characters.size(recipe, _vanilla(name, path))
    except ValueError:
        return None, []
    finally:
        seen, shipped.SEEN = shipped.SEEN, None
    return shipped.size_row(recipe, _release(name), value), [s["places"] for s in seen if "places" in s]


def _plan(job: tuple) -> tuple[dict, bytes]:
    """``(recipe, release, image)``'s plan row and its answer file, through the
    sdk's own build at the page's defaults; refused unless the file decodes
    to the answer."""
    recipe, name, path = job
    release, packs = _release(name), {p.name: {} for p in mods.PACKS.values() if p.default_on}
    shipped.SEEN = []
    try:
        sdk._plan({"iso": path, "packs": packs, "character": recipe})
        seen = next(s for s in shipped.SEEN if "plan" in s)
    finally:
        shipped.SEEN = None
    with iso.Reader(path) as r:
        base = {f: r.read(f) for f in characters.FILES}
    blob = shipped.encode(*seen["found"], base)
    if shipped._decode(blob, base, recipe)[1] != seen["plan"]["answer"]:
        raise SystemExit(f"{shipped.name('plan', seen['plan'])}: its file doesn't decode to its answer")
    owner = sorted(shipped.entries(recipe))
    if len(owner) != 1:
        raise SystemExit(f"{shipped.name('plan', seen['plan'])}: reads {len(owner)} content entries, not one")
    sha = hashlib.sha256(blob).hexdigest()
    rel = f"variants/{owner[0]}/shipped/{release.name}-{sha[:12]}.azkp"
    return seen["plan"] | {"blob": {"path": rel, "sha256": sha, "size": len(blob)}}, blob


def _key(row: dict) -> tuple:
    return row["release"], json.dumps(row["recipe"], sort_keys=True)


def _differs(kind: str, old: dict | None, new: dict | None, exact: bool) -> bool:
    """Whether a row (but its file) a fresh dress gave isn't the table's (:func:`shipped.agrees`)."""
    if old is None or new is None:
        return True
    answer = shipped.ANSWERS[kind]
    return ({k: v for k, v in old.items() if k != answer} != {k: v for k, v in new.items() if k != answer}
            or not shipped.agrees(kind, old[answer], new[answer], exact))


def text(table: dict) -> str:
    return json.dumps(table, indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 naming each row that differs")
    ap.add_argument("--content", type=Path, metavar="CLONE",
                    help="a clone of Azurik-Custom-Content: the answer files' (needed to record)")
    ap.add_argument("--workers", type=int, default=4, help="processes for the dresses (4)")
    args = ap.parse_args(argv)
    if not args.check and args.content is None:
        ap.error("recording writes the answer files into a content clone: give --content")
    paths = {}
    for release in gate.RELEASES:
        if (path := gate.find(release)) is None:
            raise SystemExit(f"recording needs the {release.label} image: {gate.missing(release)}")
        paths[release.name] = str(path)
    if lost := [r["species"] for r in PLANS if not shipped.entries(r)]:
        raise SystemExit(f"the content folder holds no {', '.join(lost)}: azurkit content install {lost[0]}")
    start = time.perf_counter()
    with ProcessPoolExecutor(args.workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        planned = [pool.submit(_plan, (r, name, path)) for r in PLANS for name, path in paths.items()]
        sized = [pool.submit(_size, (r, name, path)) for name, path in paths.items() for r in recipes()]
        plans = [f.result() for f in planned]
        done = [f.result() for f in sized]
    sizes = [row for row, _ in done if row is not None]
    places = {_key(row): row for _, heard in done for row in heard}
    made = {"host": shipped.host(), "places": sorted(places.values(), key=_key),
            "plan": sorted((row for row, _ in plans), key=_key), "size": sorted(sizes, key=_key)}
    held, drift = shipped.table(), []
    for kind in ("places", "plan", "size"):
        new = {_key(r): {k: v for k, v in r.items() if k != "blob"} for r in made[kind]}
        old = {_key(r): {k: v for k, v in r.items() if k != "blob"} for r in held.get(kind, ())}
        drift += [shipped.name(kind, (new.get(k) or old[k])) for k in sorted(new.keys() | old.keys())
                  if _differs(kind, old.get(k), new.get(k), held.get("host") == shipped.host())]
    if args.check:
        for row in held.get("plan", ()) if args.content else ():
            with iso.Reader(paths[next(r.name for r in gate.RELEASES if r.iso_sha256 == row["release"])]) as r:
                base = {f: r.read(f) for f in characters.FILES}
            blob = shipped._blob(row["blob"], args.content)
            if blob is None or shipped._decode(blob, base, row["recipe"])[1] != row["answer"]:
                drift.append(f"{shipped.name('plan', row)}'s file {row['blob']['path']} in {args.content}")
    else:
        for row, blob in plans:
            out = args.content / row["blob"]["path"]
            out.parent.mkdir(parents=True, exist_ok=True)
            for old in out.parent.glob(f"{out.name.split('-')[0]}-*.azkp"):
                if old != out:
                    old.unlink()
            out.write_bytes(blob)
            print(f"wrote: {row['blob']['path']} ({len(blob):,} bytes, {row['blob']['sha256'][:12]})")
        if text(made) != (shipped.TABLE.read_text(encoding="utf-8") if shipped.TABLE.is_file() else None):
            shipped.TABLE.write_text(text(made), encoding="utf-8")
            print(f"wrote: {shipped.TABLE.name} ({len(made['plan'])} plans, {len(made['size'])} sizes, "
                  f"{len(made['places'])} places)")
    for line in drift:
        print(f"{'differs' if args.check else 'changed'}: {line}")
    print(f"{len(plans)} plans and {len(sizes)} sizes in {time.perf_counter() - start:.0f} s")
    return 1 if args.check and drift else 0


if __name__ == "__main__":
    sys.exit(main())
