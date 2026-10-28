"""How a build's layers stack (``azurkit.edits``, D28), what its manifest
records, on a synthetic image (``tests/_xiso.py``: no game bytes), and how a
share preset carries a recipe (WEB §4.2, Q174)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import zlib

import pytest

from azurkit import __version__, sdk
from azurkit.core import gate, iso
from azurkit.edits import manifest as edits
from azurkit.edits import preset
from azurkit.edits.layer import Change, Layer
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
    refused by name, within the caps (8 KB a link, 64 KB inflated, 8 deep)."""
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
    for text, why in refused.items():
        with pytest.raises(ValueError, match="^" + re.escape(why)):
            sdk.preset_decode(text)
