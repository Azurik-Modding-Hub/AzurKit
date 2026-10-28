"""How a build's layers stack (``azurkit.edits``, D28) and what its manifest
records, on a synthetic image (``tests/_xiso.py``: no game bytes)."""

from __future__ import annotations

import hashlib

import pytest

from azurkit.core import gate, iso
from azurkit.edits import manifest as edits
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
