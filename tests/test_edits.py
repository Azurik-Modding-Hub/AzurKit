"""How a build's layers stack (``azurkit.edits``, D28), what its manifest
records, on a synthetic image (``tests/_xiso.py``: no game bytes), and how a
share preset carries a recipe (WEB §4.2, Q174)."""

from __future__ import annotations

import base64
import collections
import concurrent.futures
import functools
import hashlib
import json
import random
import re
import zlib

import pytest

from azurkit import __version__, sdk
from azurkit.core import gate, iso
from azurkit.edits import manifest as edits
from azurkit.edits import layer, preset
from azurkit.edits.layer import Change, Layer, compose
from azurkit.tools.randomizer import generator, needs, tracking
from azurkit.tools.randomizer.planner import fill as rando_fill
from tests._xiso import fill, image

BASE = {"a.bin": bytes(64), "b.bin": fill("b", 32)}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _change(file: str, at: int, data: bytes, group: str) -> Change:
    return Change(file, at, _sha256(BASE[file][at:at + len(data)]), data, group)


def _layer(name: str, *changes: Change) -> Layer:
    return Layer(f"pack {name}", "mods", "packs", {"pack": name, "params": {}}, changes)


def test_a_later_layer_wins_each_conflict_whole_groups_and_the_manifest_names_it(tmp_path):
    """A later layer that gives a byte of an earlier group another value
    wins (D28): the earlier group is dropped whole, so its other bytes, in
    any file, go back to vanilla, and the conflict names the file, the
    offset, both layers and the dropped group. A later layer that writes the
    value a byte holds overwrites nothing. The manifest lists the layers
    with their changes (their vanilla bytes by sha256), each changed file's
    sha256 and the conflicts, the same for the same recipe; a change
    planned against other bytes is refused by name."""
    src = tmp_path / "in.iso"
    src.write_bytes(image(BASE))
    stamp = gate.Stamp(gate.USA, src, src.stat().st_size, src.stat().st_mtime_ns, False)
    a = _layer("a", _change("a.bin", 0, b"AAAA", "a 1"), _change("b.bin", 8, b"aa", "a 1"),
               _change("b.bin", 0, b"Z", "a 2"))
    b = _layer("b", _change("a.bin", 2, b"BB", "b 1"))
    c = _layer("c", _change("b.bin", 0, b"Z", "c 1"))
    made, manifest = edits.image(stamp, [a, b, c])
    with iso.Reader(made) as r:
        files = {name: r.read(name) for name in BASE}
    assert files == {"a.bin": b"\0\0BB" + bytes(60), "b.bin": b"Z" + BASE["b.bin"][1:]}
    assert [str(conflict) for conflict in manifest.conflicts] == [
        "a.bin 0x2 (2 B): pack b (b 1) overwrote pack a, whose group a 1 is dropped whole"]
    assert manifest.result == {name: _sha256(data) for name, data in files.items()}
    record = manifest.to_json()
    assert record == edits.image(stamp, [a, b, c])[1].to_json()
    assert record["base"] == {"kind": "vanilla", "release": "usa", "iso_sha256": gate.USA.iso_sha256,
                              "files": _sha256(gate.USA.manifest.read_bytes())}
    assert [layer["id"] for layer in record["layers"]] == ["pack a", "pack b", "pack c"]
    assert record["layers"][1]["changes"] == [{"file": "a.bin", "offset": 2, "size": 2, "before": _sha256(bytes(2)),
                                               "after": "4242", "group": "b 1"}]
    assert record["conflicts"] == [str(manifest.conflicts[0])] and len(record["recipe_sha256"]) == 64
    stale = _layer("d", Change("b.bin", 0, _sha256(b"X"), b"Y", "d 1"))
    with pytest.raises(ValueError, match=r"^pack d \(d 1\): planned against other bytes of b\.bin at 0x0$"):
        edits.image(stamp, [stale])


def test_a_whole_file_shadows_earlier_groups_and_a_later_range_lands_only_where_it_kept_vanilla(tmp_path):
    """A file written whole (the character layer's ``characters.xbr``,
    ``fx.xbr`` and ``index.xbr``, one group, at any size) drops each earlier
    group whose bytes it doesn't hold, by name, and keeps one whose bytes it
    holds. A later range planned against the vanilla bytes lands over it
    where the whole file kept them, or already holds the range's own, and
    overwrites nothing; where the whole file changed them (a grown body moved
    the resource there), it is refused by name (D35, Modkit's AZ-096). The
    image grows the file and the manifest marks the change whole; a second
    whole write of a file, or a whole file planned against another, is
    refused by name; a file's sha256 a stamp vouches for (``known``) stands
    for its hash."""
    src = tmp_path / "in.iso"
    src.write_bytes(image(BASE))
    stamp = gate.Stamp(gate.USA, src, src.stat().st_size, src.stat().st_mtime_ns, False)
    grown = b"W" + BASE["b.bin"][1:16] + bytes(16) + b"tail" * 300
    put = Change("b.bin", 0, _sha256(BASE["b.bin"]), grown, "swap files", whole=True)
    packs = _layer("a", _change("b.bin", 0, b"Z", "a 1"), _change("a.bin", 0, b"A", "a 1"),
                   _change("b.bin", 4, BASE["b.bin"][4:6], "a 2"))
    swap = Layer("player model keylord", "characters", "characters", {"species": "keylord"},
                 (put, Change("a.bin", 0, _sha256(BASE["a.bin"]), b"whole a", "swap files", whole=True)))
    data = Layer("xbr", "xbr", "xbr", {"ops": []}, (_change("b.bin", 0, b"W", "#0"), _change("b.bin", 8, b"d", "#1")))
    made, manifest = edits.image(stamp, [packs, swap, data])
    with iso.Reader(made) as r:
        assert r.read("b.bin") == grown[:8] + b"d" + grown[9:] and r.read("a.bin") == b"whole a"
    assert [str(conflict) for conflict in manifest.conflicts] == [
        "b.bin 0x0 (1 B): player model keylord (swap files) overwrote pack a, whose group a 1 is dropped whole"]
    moved = Layer("xbr", "xbr", "xbr", {"ops": []}, (_change("b.bin", 0, b"D", "#0"),))
    with pytest.raises(ValueError, match=r"^xbr \(#0\): player model keylord \(swap files\) wrote b\.bin whole "
                                         r"with other bytes at 0x0$"):
        edits.image(stamp, [packs, swap, moved])
    assert [c.get("whole") for c in manifest.to_json()["layers"][1]["changes"]] == [True, True]
    twice = Layer("again", "characters", "characters", {}, (put,))
    with pytest.raises(ValueError, match=r"^again \(swap files\): b\.bin is written whole by player model keylord"):
        edits.image(stamp, [swap, twice])
    stale = Layer("stale", "characters", "characters", {}, (Change("b.bin", 0, _sha256(b"X"), b"Y", "s", whole=True),))
    with pytest.raises(ValueError, match=r"^stale \(s\): written whole against another b\.bin$"):
        edits.image(stamp, [stale])
    known = {name: _sha256(data) for name, data in BASE.items()}   # a stamp's: the files aren't hashed again
    assert compose(BASE, [packs, swap, data], known) == compose(BASE, [packs, swap, data])
    with pytest.raises(ValueError, match=r"written whole against another b\.bin$"):
        compose(BASE, [swap], known | {"b.bin": _sha256(b"X")})


COMPOSE_SETS = {   # each row's random layer sets: seed, sets, files and groups at most, a change's odds of being
    # written whole and of being planned against other bytes
    "ranges of two groups": (1, 1500, 2, 2, 0.0, 0.0),
    "ranges of six groups, a group again in later layers": (2, 1500, 3, 6, 0.0, 0.0),
    "whole files under and over ranges": (3, 1500, 3, 3, 0.08, 0.0),
    "refusals among them": (4, 1000, 3, 3, 0.04, 0.02),
}


def test_compose_with_runs_makes_the_files_conflicts_and_refusals_byte_by_byte_compose_makes(monkeypatch):
    """``compose`` keeps a file's range writes as runs until another
    group's write meets one (``layer.RUNS``), and over random layer sets
    (range and whole-file changes over small files of four byte values,
    overlapping or not, by the same group again or another, some planned
    against other bytes) it gives the files, the conflicts and the refusals
    it gives keeping every byte's writers (Step 4.3v)."""
    def composed(base: dict, layers: list, runs: bool) -> tuple | str:
        monkeypatch.setattr(layer, "RUNS", runs)
        try:
            files, conflicts = compose(base, layers)
        except ValueError as exc:
            return str(exc)
        return {name: bytes(data) for name, data in files.items()}, conflicts

    seen = collections.Counter()
    for row, (seed, sets, most, groups, whole, other) in COMPOSE_SETS.items():
        rng = random.Random(seed)

        def some(n: int) -> bytes:
            return bytes(rng.randrange(4) for _ in range(n))
        for k in range(sets):
            base = {f"f{n}.bin": some(rng.randint(8, 64)) for n in range(rng.randint(1, most))}
            layers = []
            for at_layer in range(rng.randint(1, 4)):
                changes = []
                for _ in range(rng.randint(1, 6)):
                    file, group = rng.choice(sorted(base)), f"g{rng.randrange(groups)}"
                    if rng.random() < whole:
                        after = some(len(base[file]) + rng.randint(-4, 4))
                        changes.append(Change(file, 0, _sha256(base[file]), after, group, whole=True))
                        continue
                    n = rng.randint(0, 12)
                    at = rng.randint(0, max(len(base[file]) - n, 0))
                    before = base[file][at:at + n] if rng.random() >= other else b"other"
                    changes.append(Change(file, at, _sha256(before), some(n), group))
                layers.append(Layer(f"layer {at_layer}", "t", "k", {}, tuple(changes)))
            runs = composed(base, layers, True)
            assert runs == composed(base, layers, False), (row, k)
            seen[row, "refused" if isinstance(runs, str) else "conflicts" if runs[1] else "clean"] += 1
    assert all(seen[row, "clean"] and seen[row, "conflicts"] for row in COMPOSE_SETS), seen
    assert seen["refusals among them", "refused"] and seen["whole files under and over ranges", "refused"], seen


def test_a_builds_image_gives_the_md5_its_layout_hashed_only_for_the_bytes_hashed(tmp_path):
    """The image a build makes keeps the md5 its layout hashed of each
    changed file (``iso.read``'s ``md5s``), so the randomizer's read-back
    hashes no level file again (Step 4.3v); ``Image.md5`` gives it for that
    file, its path matched case-blind, only when the bytes read back are
    the bytes hashed (compared, never assumed), and hashes any other."""
    src = tmp_path / "in.iso"
    src.write_bytes(image(BASE))
    stamp = gate.Stamp(gate.USA, src, src.stat().st_size, src.stat().st_mtime_ns, False)
    made, _ = edits.image(stamp, [_layer("a", _change("a.bin", 0, b"AAAA", "a 1"))])
    with iso.Reader(made) as r:
        data = r.read("a.bin")
    assert made.md5s == {iso.key("a.bin"): (hashlib.md5(data).hexdigest(), data)}
    told = iso.read(src, {"a.bin": data}, md5s={"a.bin": "0" * 32})   # a given md5, to see where it is taken
    assert told.md5("/A.BIN", data) == "0" * 32
    assert told.md5("a.bin", b"B" + data[1:]) == hashlib.md5(b"B" + data[1:]).hexdigest()
    assert told.md5("b.bin", BASE["b.bin"]) == hashlib.md5(BASE["b.bin"]).hexdigest()


def test_a_replaced_file_lands_whole_after_every_layer_and_its_recipe_names_it(tmp_path, monkeypatch):
    """Replace files (``edits.files``): a file the player picked stands in
    whole for the image's own, at any size, in one layer after every other.
    An earlier group it shadows (an ``xbr`` operation) is dropped whole and
    named (D28); one whose bytes it holds is kept; a file another layer
    writes whole (the character layer's) is refused by name. The recipe and
    the manifest name each file by path, sha256 and size, never its bytes:
    none is in /azurkit.bin, so files past its 256 MiB still make a build
    AzurKit opens. Refused by name: default.xbe, filelist.txt,
    /azurkit.json, /azurkit.bin, a path the image hasn't, a size an image's
    file can't hold, a rebuild whose file isn't picked this session or is
    another file (no sha256 echoed), and a computer path on a network share,
    a device path or under /net/ (SEC-11)."""
    import dataclasses

    from azurkit.edits import files as put
    from azurkit.edits import xbr

    game = {"default.xbe": fill("x", 64), "gamedata/config.xbr": fill("c", 96),
            "gamedata/characters.xbr": fill("h", 48), "movies/Credits.bik": fill("m", 5000)}
    (tmp_path / "usa.json").write_text(json.dumps({"dirs": ["gamedata", "movies"], "files": {
        path: [len(data), _sha256(data)] for path, data in game.items()}}))
    release = dataclasses.replace(gate.USA, manifest=tmp_path / "usa.json")
    src = tmp_path / "in.iso"
    src.write_bytes(image(game))
    stamp = gate.Stamp(release, src, src.stat().st_size, src.stat().st_mtime_ns, False)
    config, credits = b"NEW!" + game["gamedata/config.xbr"][4:] + b"grown" * 40, fill("s", 700)
    swap = Layer("player model keylord", "characters", "characters", {"species": "keylord"},
                 (Change("gamedata/characters.xbr", 0, _sha256(game["gamedata/characters.xbr"]), b"body" * 30,
                         "swap files", whole=True),))
    data = xbr.plan(xbr.normalize([
        {"op": "replace_bytes", "file": "gamedata/config.xbr", "offset": 0, "expected": "6363", "value": "4e45"},
        {"op": "replace_bytes", "file": "gamedata/config.xbr", "offset": 32, "expected": "6363", "value": "4f4c"}]),
        release, game)
    entries = put.normalize([put.entry("gamedata/config.xbr", config), put.entry("movies/Credits.bik", credits)])
    picked = {"gamedata/config.xbr": config, "movies/Credits.bik": credits}
    made, manifest = edits.image(stamp, [swap, data, put.plan(entries, picked, release)])
    with iso.Reader(made) as r:
        assert [r.read(path) for path in ("gamedata/config.xbr", "movies/Credits.bik", "gamedata/characters.xbr")] == [
            config, credits, b"body" * 30]
    assert [str(conflict) for conflict in manifest.conflicts] == [
        "gamedata/config.xbr 0x20 (2 B): files put (put gamedata/config.xbr) overwrote data xbr, whose group "
        "#2 replace_bytes gamedata/config.xbr 0x20 is dropped whole"]
    assert entries[0] == {"path": "gamedata/config.xbr", "sha256": _sha256(config), "size": len(config)}
    assert manifest.recipe()["layers"][-1] == {"id": "files put", "tool": "files", "kind": "put",
                                               "recipe": {"files": entries}}
    assert manifest.result["movies/Credits.bik"] == _sha256(credits)
    assert [c.get("whole") for c in manifest.to_json()["layers"][-1]["changes"]] == [True, True]
    iso.pack(made, tmp_path / "out.iso")
    monkeypatch.setattr(gate, "RELEASES", (release,))
    monkeypatch.setattr(edits, "MAX_BIN", 120)   # the swap's file alone, as /azurkit.bin's limit
    record = edits.load(tmp_path / "out.iso")[1]
    assert record["bin"] == {_sha256(b"body" * 30): [0, 120]}
    assert [c["after"] for c in record["layers"][-1]["changes"]] == [{"sha256": _sha256(config)},
                                                                     {"sha256": _sha256(credits)}]
    body = put.normalize([put.entry("gamedata/characters.xbr", credits)])
    with pytest.raises(ValueError, match=r"^files put \(put gamedata/characters\.xbr\): gamedata/characters\.xbr is "
                                         r"written whole by player model keylord already$"):
        edits.image(stamp, [swap, put.plan(body, {"gamedata/characters.xbr": credits}, release)])
    owned = {"default.xbe": "the packs' file, planned against its own layout, is never replaced whole",
             "filelist.txt": "the build writes it", "/azurkit.json": "a build's manifest, which the build writes",
             "/AZURKIT.BIN": "a build's manifest, which the build writes"}
    for path, why in owned.items():
        with pytest.raises(ValueError, match=f"^files 1 \\({re.escape(path)}\\): {re.escape(why)}$"):
            put.normalize([entries[0] | {"path": path}])
    refused = {
        "files 2 (gamedata/config.xbr): replaced twice (files 1 and 2)": [entries[0], entries[0]],
        "files 1: no key 'source' (its keys: path, sha256, size)": [entries[0] | {"source": "/Users/x/mine.xbr"}],
        "files 1 (gamedata/config.xbr): sha256 is not 64 lowercase hex digits": [entries[0] | {"sha256": "AB" * 32}],
        "files 1 (gamedata/config.xbr): 4,294,967,296 B is more than an image's file holds (4,294,967,295 B)":
            [entries[0] | {"size": 1 << 32}],
    }
    for why, given in refused.items():
        with pytest.raises(ValueError, match=f"^{re.escape(why)}$"):
            put.normalize(given)
    other = config[::-1]
    stops = {
        "files 1 (gamedata/new.xbr): the USA image has no gamedata/new.xbr (Replace files adds no file)":
            (put.normalize([put.entry("gamedata/new.xbr", credits)]), {"gamedata/new.xbr": credits}),
        "files 1 (gamedata/config.xbr): its file isn't picked in this session; pick it again (296 B); files 2 "
        "(movies/Credits.bik): its file isn't picked in this session; pick it again (700 B)": (entries, {}),
        "files 1 (gamedata/config.xbr): the picked file isn't the one it names (another sha256)":
            (entries[:1], {"gamedata/config.xbr": other}),
        "files 1 (gamedata/config.xbr): the picked file is 4 B, not the 296 B it names":
            (entries[:1], {"gamedata/config.xbr": b"tiny"}),
        "files: a file picked for movies/Credits.bik, which no entry replaces": (entries[:1], picked),
    }
    for why, (given, files) in stops.items():
        with pytest.raises(ValueError, match=f"^{re.escape(why)}$"):
            put.plan(given, files, release)
    for path in (r"\\host\share\mine.xbr", r"\\?\C:\mine.xbr", r"\\.\pipe\x", "//host/share/mine.xbr",
                 "/net/host/mine.xbr", "/NET/host/mine.xbr", "/net"):
        with pytest.raises(ValueError, match=r"is never read; pick a file on this computer$"):
            put.source(path)
    assert put.source(str(tmp_path / "mine.xbr")) == str(tmp_path / "mine.xbr")


def test_a_seed_builds_layout_and_read_back_report_each_file_and_a_raised_record_stops_the_build(usa_iso):
    """``edits.image``'s ``progress(done, total)`` hears each file composed,
    then each changed file hashed (``total``: the files the layers name,
    twice, then those and the changed ones), and the randomizer's read-back
    (``generator.read_back``'s) each level file it reads back, done of
    total; an exception a record raises stops the build there, so a cancel
    waits for one file's work at most (Step 4.3v)."""
    prepared = generator.prepare({"seed": "2"}, {})
    stamp = sdk._stamp(str(usa_iso))
    with iso.Reader(stamp.path) as r:
        base = {file: r.read(file) for file in generator.files(prepared)}
    planned = generator.plan_layer(prepared, base)
    laid, read = [], []

    def judge(made: iso.Image, manifest: edits.Manifest, progress=lambda done, total: read.append((done, total))):
        return {generator.TOOL: generator.read_back(prepared, made, manifest.layers, manifest.conflicts,
                                                    progress=progress)}
    _, manifest = edits.image(stamp, [planned], base, judge=judge,
                              progress=lambda done, total: laid.append((done, total)))
    n, m = len({c.file for c in planned.changes}), len(set(manifest.result) - {"filelist.txt"})
    assert laid == [(k, 2 * n) for k in range(1, n + 1)] + [(n + k, n + m) for k in range(1, m + 1)]
    assert read == [(k, read[-1][1]) for k in range(1, read[-1][1] + 1)] and read[-1][1] > 2
    assert manifest.verdicts[generator.TOOL]["logic_verified"]

    class Stop(Exception):
        pass

    def stop(at: int):
        def heard(done: int, total: int) -> None:
            if done == at:
                raise Stop(at)
        return heard
    for at in (3, n + 1):   # the third file composed, the first hashed
        with pytest.raises(Stop):
            edits.image(stamp, [planned], base, progress=stop(at))
    with pytest.raises(Stop):   # the third level file read back
        edits.image(stamp, [planned], base, judge=lambda made, manifest: judge(made, manifest, stop(3)))


def test_save_writes_the_image_a_build_made_its_stages_are_reported_and_its_spoiler_comes_on_demand(usa_iso, tmp_path,
                                                                                                    monkeypatch):
    """``sdk.image`` reports each named stage of a build as the progress
    record (``core.progress``), in order, the planner's note among the
    seed's, the fill's items placed counted inside its step and never back
    when an attempt sticks (seed 16's first does), and ``sdk.tracker`` a
    plan's first view's, the maps' exits counted inside its world map's
    step (Step 4.3m); with ``spoiler`` false
    its report leaves the spoiler out, and ``sdk.spoiler(plan, built=True)`` gives it then.
    ``sdk.save`` writes the image the build made, without planning it
    again, its sha256 the image's, following the write in the record."""
    seen, writes = [], []
    monkeypatch.setattr(sdk, "_STAMPS", {})   # the image's first check in this process: its bytes are reported
    monkeypatch.setattr(rando_fill, "_LAST_FILL", [None])   # the seed's fill not kept from another test: it fills now
    sdk.randomizer_logic()   # read before (read cold, its checks are counted in the plan stage too: test_hosts)
    made, report = sdk.image({"iso": str(usa_iso), "packs": {"qol_alloc_race": {}}, "randomizer": {"seed": "16"}},
                             progress=seen.append, spoiler=False)
    assert list(dict.fromkeys(r["stage"] for r in seen)) == ["plan", "check", "read", "pack", "layout", "judge"]
    check = [r for r in seen if r["stage"] == "check"]
    assert (check[0]["label"], check[-1]["percent"]) == ("Checking your image", 100)
    assert [r["label"] for r in seen if r["stage"] == "pack"] == ["Applying qol_alloc_race"]
    planned = [r["label"] for r in seen if r["stage"] == "plan"]   # the fill's items placed counted in its stage
    assert planned[:2] == ["Planning the seed", "Planning the seed (placing the items)"] and len(planned) > 20
    assert all(re.fullmatch(r"Planning the seed \(placing the items, \d+ of \d+\)", label) for label in planned[2:])
    percents = [r["percent"] for r in seen if r["stage"] == "plan"][2:]   # attempt 1's bar starts where 0's stuck
    assert report["plan"]["attempt"] == 1 and percents == sorted(percents)
    monkeypatch.setattr(tracking, "_KEPT", type(tracking._KEPT)())   # the plan's first view, in a process that
    for module, name in ((tracking, "world"), (needs, "overlays"), (needs, "exit_edges")):   # reads the maps' exits
        monkeypatch.setattr(module, name, functools.cache(getattr(module, name).__wrapped__))
    read = []
    sdk.tracker({"plan": report["plan"]}, progress=read.append)
    n = read[-1]["total"] // 2
    assert [(r["label"], r["done"], r["total"]) for r in read] == [
        ("Reading the seed's logic", 0, 2), ("Reading the world map", 1, 2),
        *((f"Reading the world map (the maps' exits, {k} of {n})", n + k - 1, 2 * n) for k in range(1, n + 1))]
    assert "spoiler" not in report and report["randomizer"]["logic_verified"]
    text = sdk.spoiler(report["plan"], built=True)["text"]
    lines = text.splitlines()
    assert lines[1] == "logic_verified: true" and lines[0] in sdk.spoiler(report["plan"])["lines"]
    out = tmp_path / "out.iso"
    saved = sdk.save(made, str(out), progress=writes.append)
    with open(out, "rb") as f:
        assert saved == {"out": str(out), "size": made.size, "sha256": hashlib.file_digest(f, "sha256").hexdigest()}
    assert saved["sha256"] == iso.digest(made) and (writes[0]["stage"], writes[-1]["percent"]) == ("write", 100)


def _link(value: object, raw: bytes | None = None) -> str:
    """``value`` as a link's fragment, unchecked: JSON (or ``raw``), raw deflate, base64url."""
    squeeze = zlib.compressobj(9, zlib.DEFLATED, -15)
    data = squeeze.compress(raw if raw is not None else json.dumps(value).encode()) + squeeze.flush()
    return "#p=" + base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_a_preset_round_trips_and_refuses_what_isnt_one_by_name():
    """``sdk.preset_encode`` makes a link's fragment of a recipe's packs,
    normalized, and (given its build's report) the release and the result;
    never the image's path. ``sdk.preset_decode`` gives it back from the
    fragment or a whole link, and encoding that again gives the same link.
    A fragment is untrusted (WEB §4.2): each thing that isn't a preset is
    refused by name, within the caps (8 KB a link, 64 KB inflated, 8 deep),
    alike in any thread (``core.jsondepth``: json's own depth limit is the
    C stack's, which differs by thread and platform)."""
    recipe = {"iso": "/Users/someone/games/usa.iso", "packs": {"qol_alloc_race": {}, "fps_unlock": {"target_fps": 120.0}}}
    report = {"release": "usa", "result": {"default.xbe": "ab" * 32, "filelist.txt": "cd" * 32}}
    link = sdk.preset_encode(recipe, report)
    shared = {"format": "azurkit-preset", "schema_version": 1, "azurkit": __version__,
              "base": {"kind": "vanilla", "release": "usa", "iso_sha256": gate.USA.iso_sha256},
              "layers": [{"tool": "mods", "kind": "packs",
                          "recipe": {"fps_unlock": {"target_fps": 120}, "qol_alloc_race": {}}}],
              "result": report["result"]}
    assert link.startswith("#p=") and len(link) < 400 and "someone" not in json.dumps(preset.decode(link))
    assert sdk.preset_decode(link) == sdk.preset_decode(f"https://azurkit.test/{link}") == shared
    assert preset.encode(sdk.preset_decode(link)) == link
    bare = {k: v for k, v in shared.items() if k not in ("base", "result")}
    assert sdk.preset_decode(sdk.preset_encode({"packs": recipe["packs"]})) == bare
    layer = bare["layers"][0]
    refused = {
        _link(bare | {"changes": []}): "preset: no key 'changes'",
        _link(bare | {"layers": [layer | {"recipe": {"nope": {}}}]}): "recipe: no pack 'nope'",
        _link(bare, json.dumps(bare).replace("120", "NaN").encode()): "preset: NaN is not a finite number",
        _link(bare | {"layers": [layer | {"tool": "randomizer"}]}): "preset: no tool 'randomizer' with 'packs'",
        _link(bare | {"layers": [layer, layer]}): "preset: a tool has two layers",
        _link(shared | {"base": shared["base"] | {"iso_sha256": "0" * 64}}): "preset: base is no release's vanilla",
        _link(shared | {"result": {"default.xbe": "AB"}}): "preset: result is {file: sha256}",
        _link(bare | {"azurkit": "<b>1</b>"}): "preset: azurkit is no version",
        _link(None, b" " * (64 * 1024 + 1)): "preset: inflates past 65536 B",
        _link(bare | {"x": [[[[[[[[1]]]]]]]]}): "preset: JSON nested deeper than 8",
        _link(None, b"[" * 60000): "preset: JSON nested deeper than 8",
        _link(None, b"{,}"): "preset: not JSON",
        link[:-6]: "preset: the link's data is cut short",
        "#p=@@": "preset: no #p= and base64url",
        "#p=" + "A" * 8192: "preset: no #p= and base64url of at most 8192 B",
        "fps_unlock=120": "preset: no #p=",
    }

    def refuse() -> None:
        for text, why in refused.items():
            with pytest.raises(ValueError, match="^" + re.escape(why)):
                sdk.preset_decode(text)
    refuse()
    with concurrent.futures.ThreadPoolExecutor(1) as other:   # another thread's C stack, which json's limit follows
        other.submit(refuse).result()


def test_a_mods_file_saved_from_the_setup_loads_back_the_same_recipe():
    """The Tools tab's mods file (Q268, ``sdk.mods_file``): the page's
    recipe (a pack with a slider set, a config.xbr ``set`` and a
    ``replace_bytes``, a seed and a character) saved as a mods file loads
    back, as a UI loads it, into the same packs, operations, seed and
    character, and ``azurkit build --mods`` (``sdk.read_mods``) takes it as
    that recipe. A file keeps the ``replace_bytes`` a share link refuses
    (Q174), and what it reads is checked as a link's: a pack AzurKit lacks
    is refused by name."""
    cell = {"op": "set", "file": "gamedata/config.xbr", "table": "critters_damage", "entity": "golem",
            "prop": "hitPoints", "value": 321}
    raw = {"op": "replace_bytes", "file": "gamedata/a1.xbr", "offset": 0x800, "value": "deadbeef",
           "expected": "00000000"}
    recipe = {"packs": {"fps_unlock": {"target_fps": 120}}, "xbr": [cell, raw], "randomizer": {"seed": "2"},
              "character": {"species": "keylord"}}
    text = sdk.mods_file({"recipe": recipe})["text"]
    read = sdk.read_mods(text)
    assert read == {"packs": {"fps_unlock": {"target_fps": 120}}, "xbr": [cell, raw], "randomizer": {"seed": "2"},
                    "character": read["character"]} and read["character"]["species"] == "keylord"
    loaded = {layer["tool"]: layer["recipe"] for layer in sdk.mods_file({"text": text})["preset"]["layers"]}
    assert loaded == {"randomizer": {"seed": "2"}, "mods": read["packs"], "characters": read["character"],
                      "data": {"ops": [cell, raw]}}
    assert sdk.mods_file({"recipe": read})["text"] == text
    with pytest.raises(ValueError, match=re.escape("a share link carries packs and set only (Q174), not xbr op 2")):
        sdk.preset_encode(recipe)
    with pytest.raises(ValueError, match=re.escape("recipe: no pack 'nope'")):
        sdk.mods_file({"text": text.replace('"fps_unlock"', '"nope"')})
