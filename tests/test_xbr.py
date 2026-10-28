"""The data archives (``azurkit.core.xbr``, Step 4.1e2): every vanilla XBR
of both releases parses and writes back to its manifest's sha256;
config.xbr's keyed cells (written new from the format, AZ-212) take the
Game Data editor's two edits as Modkit made them (the oracle's
``xbr_editor`` goldens); and, on a synthetic archive (no game bytes), an
edit writes only its cell and refuses by name, and a config.xbr slider
(``XbrParametricEdit``) writes any finite value but what the game's int32
can't hold."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import struct

import pytest

from azurkit.core import gate, iso
from azurkit.core.xbr import Document, edits
from azurkit.tools import mods
from azurkit.tools.mods import engine
from scripts import gen_facts

RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


def _sha256(data) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("release", RELEASES)
def test_every_vanilla_xbr_round_trips_to_its_manifest_hash(release, request):
    """Each ``.xbr`` of the release's manifest (42 USA, 44 Europe) parses
    (its header, TOC, trailer and names, and config.xbr's 18 keyed tables)
    and, written back from what was parsed, is its own sha256."""
    files = {path: sha for path, (_, sha) in release.files.items() if path.endswith(".xbr")}
    assert len(files) == {"usa": 42, "europe": 44}[release.name]
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        for path, sha in sorted(files.items()):
            doc = Document(r.read(path))
            assert _sha256(doc.dumps()) == sha, path
            if path == mods.engine.CONFIG:
                assert len(doc.tables) == 18 and doc.names()[0] == "config/armor_hit_fx"


def test_the_game_data_editors_two_edits_build_their_goldens(usa_iso):
    """The oracle's ``xbr_editor`` cases, each one edit of vanilla
    config.xbr: a number cell takes its value, and a string cell its text
    (rewritten in place: no cell of its table holds it), each giving the
    file Modkit's editor saved."""
    golden = json.loads((gen_facts.ORACLE / "packs/tests/goldens/xbr_editor.json").read_text(encoding="utf-8"))
    recipes = json.loads((gen_facts.ORACLE / "packs/cases.json").read_text(encoding="utf-8"))
    recipes = recipes["tests/goldens/xbr_editor.json"]
    with iso.Reader(usa_iso) as r:
        data = r.read(mods.engine.CONFIG)
    doc = Document(data)
    assert len(golden) == 2
    for case, files in golden.items():
        (table, entity, prop, value), = recipes[case]["edits"]
        writes = (edits.set_text(doc.tables[table], data, entity, prop, value) if isinstance(value, str)
                  else edits.set_number(doc.tables[table], entity, prop, value))
        assert {"config.xbr": _sha256(_apply(data, writes))} == files, case


def _apply(data: bytes, writes) -> bytes:
    out = bytearray(data)
    for at, new in writes:
        out[at:at + len(new)] = new
    return bytes(out)


def _archive(tables: dict[str, list[list[object]]], rows: dict[str, list[str]]) -> bytes:
    """A synthetic config archive (the layout ``core.xbr`` reads): each
    table's columns, each a list of cells (``None`` empty, a number, or a
    string, its first the column's name), its strings interned as the
    game's are (one copy each), named ``config/<table>``."""
    payloads = []
    for name, cols in tables.items():
        n_rows, cells = len(rows[name]), [cell for col in cols for cell in col]
        grid = 0x14 + 8 * n_rows
        texts = {}
        for text in [*rows[name], *(c for c in cells if isinstance(c, str))]:
            texts.setdefault(text, grid + 16 * len(cells) + sum(len(t) + 1 for t in texts))
        out = bytearray(struct.pack("<5I", n_rows, 0x10, len(cols), len(cells), grid - 0x10))
        for r, row in enumerate(rows[name]):
            out += struct.pack("<II", len(row), texts[row] - (0x14 + 8 * r + 4))
        for k, cell in enumerate(cells):
            at = grid + 16 * k
            out += (bytes(16) if cell is None else struct.pack("<IId", 1, 0, cell) if not isinstance(cell, str)
                    else struct.pack("<IIII", 2, 0, len(cell), texts[cell] - (at + 12)))
        out += b"".join(t.encode() + b"\0" for t in texts) + bytes(-len(out) % 8)
        payloads.append(bytes(out))
    data_start = 0x1000
    body, toc = bytearray(), bytearray()
    for payload in payloads:
        toc += struct.pack("<II4sI", len(body), len(payload), b"tabl", 8)
        body += payload
    trailer = data_start + len(body) + (-len(body) % 0x1000)
    pool = b"".join(f"config/{name}".encode() + b"\0" for name in tables)
    named = b"".join(struct.pack("<II", k, sum(len(f"config/{n}") + 1 for n in list(tables)[:k]))
                     for k in range(len(tables)))
    tail = struct.pack("<4sI", b"tabl", 1) + named + pool
    named_at = trailer + 8
    header = struct.pack("<4s14I", b"xobx", 4, 0, len(tables), data_start, 1, trailer, 0, named_at, 0, named_at,
                         len(tables), named_at, named_at + len(named), len(pool))
    out = header + toc + bytes(data_start - len(header) - len(toc)) + body
    return bytes(out + bytes(trailer - len(out)) + tail)


ROWS = {"t": ["name", "hp", "kind", "note"], "u": ["name", "hp"]}
TABLES = {"t": [["a", 1.0, "fire", "slack"], ["b", None, "fire", None], ["b", 3.0, "ice", "x"]],
          "u": [["c", 5.0], ["d", None]]}


def test_a_cell_edit_writes_only_its_cell_and_refuses_by_name():
    """On a synthetic archive: it parses and writes back to itself; a
    number cell takes any finite value; an empty one only with ``fill``,
    and not in a row of strings; a name finds its last column, an index
    another; a text the table holds is pointed at, a new one rewrites an
    unshared string in place if it fits; and every refusal names the
    table, cell and why. A file that isn't an archive, or whose TOC or
    trailer runs off it, is refused by what runs off."""
    data = _archive(TABLES, ROWS)
    doc = Document(data)
    assert doc.dumps() == data and list(doc.tables) == ["t", "u"] and doc.tables["t"].cols == ("a", "b", "b")
    t = doc.tables["t"]

    def after(writes) -> Document:
        made = _apply(data, writes)
        changed = [k for k in range(len(data)) if made[k] != data[k]]
        assert all(any(at <= k < at + len(new) for at, new in writes) for k in changed)
        return Document(made)

    assert after(edits.set_number(t, "a", "hp", -1e300)).tables["t"].number("a", "hp") == -1e300
    assert after(edits.set_number(t, "b", "hp", 7)).tables["t"].number("b", "hp") == 7.0   # the last b
    assert after(edits.set_number(t, "b", "hp", 7, col=1, fill=True)).tables["t"].cell(1, 1).value == 7.0
    assert after(edits.set_text(t, data, "a", "kind", "ice")).tables["t"].find("a", "kind").value == "ice"
    assert after(edits.set_text(t, data, "b", "note", "ice", col=1, fill=True)).tables["t"].cell(1, 3).value == "ice"
    grown = after(edits.set_text(t, data, "a", "note", "salt"))
    assert grown.tables["t"].find("a", "note").value == "salt" and grown.tables["t"].find("b", "note").value == "x"
    assert edits.set_text(t, data, "a", "kind", "fire") == []
    for edit, why in (
            (lambda: edits.set_number(t, "b", "hp", 1, col=1), "config table t b/hp is an empty cell, not a number"),
            (lambda: edits.set_number(t, "a", "kind", 1), "config table t a/kind is a string cell, not a number"),
            (lambda: edits.set_number(t, "a", "hp", math.nan), "config table t a/hp: nan is not a finite number"),
            (lambda: edits.set_number(t, "b", "note", 1, col=1, fill=True),
             "config table t b/note is empty and its row holds only strings, so it can't take a number"),
            (lambda: edits.set_number(t, "z", "hp", 1), "config table t has no column 'z'"),
            (lambda: edits.set_number(t, "a", "hp", 1, col=2), "config table t: column 2 isn't named 'a'"),
            (lambda: edits.set_number(t, "a", "mp", 1), "config table t has no row 'mp'"),
            (lambda: edits.set_text(t, data, "a", "note", "a longer text"),
             "config table t a/note: 'a longer text' needs 14 B, and its string's slot holds 6 B"),
            (lambda: edits.set_text(t, data, "a", "kind", "ash"),
             "config table t a/kind: its string is shared with 1 other reference(s)"),
            (lambda: edits.set_text(t, data, "b", "note", "new", col=1, fill=True),
             "config table t b/note: no cell of the table holds 'new'"),
            (lambda: edits.set_text(t, data, "a", "hp", "x"), "config table t a/hp is a number cell, not a string"),
            (lambda: edits.set_text(t, data, "a", "note", "é"), "config table t a/note: 'é' is not ASCII")):
        with pytest.raises((LookupError, ValueError), match=f"^{re.escape(why)}"):
            edit()
    for broken, why in ((b"XBEH" + data[4:], "not an XBR: no xobx header"),
                        (data[:0x48], r"TOC entry 0 \(0x3C, 16 B\) runs off the 72 B file"),
                        (data[:-1], r"the name pool \(0x2018, 1 x 18 B\) ends at 0x202A, not at 0x2029")):
        with pytest.raises(ValueError, match=f"^{why}$"):
            Document(broken)


def test_a_config_slider_writes_any_finite_value_and_refuses_what_the_games_int32_cant_hold(tmp_path, monkeypatch):
    """A config.xbr slider (``XbrParametricEdit``) on a synthetic archive,
    the release's manifest naming it: one cell takes any finite value, far
    past its track (D23), unless the game rounds it to an int32 that can't
    hold it (D45, refused by the slider); a multiplier's cells become k x
    base as the game truncates them (an empty one filled), nothing at its
    default, and one that int32 can't hold fails the pack, naming the cell.
    An archive that isn't the release's vanilla one is refused by size and
    sha256."""
    data = _archive(TABLES, ROWS)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"dirs": [], "files": {engine.CONFIG: [len(data), _sha256(data)]}}))
    release = dataclasses.replace(gate.USA, manifest=manifest)
    monkeypatch.setattr(engine.facts_, "of", lambda r: pytest.fail("an XBR-only pack reads no XBE"))

    def slider(name, **kw):
        return engine.XbrParametricEdit(name=name, label=name, table="t", prop="hp", default=kw.pop("default", 1.0),
                                        slider_min=0, slider_max=2, slider_step=1, **kw)
    one = engine.Pack("one", "", sites=(slider("hp", entity="a", int32="round"), slider("free", entity="b")))
    many = engine.Pack("many", "", sites=(slider("k", entity="all", int32="trunc", cells=lambda tables: [
        ("a", 0, "hp", 1.0), ("b", 1, "hp", 10.0), ("b", 2, "hp", 3.0)]),))
    assert one.files() == (engine.CONFIG,) and one.sliders()[0].catalog()["vanilla"] == 1.0

    def planned(pack, **params):
        layer = mods.plan(pack, release, {engine.CONFIG: data}, params)
        made = Document(_apply(data, [(c.offset, c.after) for c in layer.changes])).tables["t"]
        return {c.group for c in layer.changes}, [made.cell(c, 1).value for c in range(3)]

    assert planned(one, hp=2147483647.4, free=1e300) == ({"one t/a/hp", "one t/b/hp (column 2)"},
                                                         [2147483647.4, None, 1e300])
    assert planned(many) == (set(), [1.0, None, 3.0])
    assert planned(many, k=-2.75) == ({"many t/a/hp", "many t/b/hp (column 1)", "many t/b/hp (column 2)"},
                                      [-2.0, -27.0, -8.0])
    for pack, params, why in (
            (one, {"hp": 2147483647.5}, "hp: 2.14748e+09 doesn't fit the game's 32-bit integer once rounded "
                                        "(-2147483648..2147483647) (its parameters: hp, free)"),
            (many, {"k": 3e8}, "1 site(s) failed: k: t b/hp: 3e+09 doesn't fit the game's 32-bit integer once "
                               "truncated (-2147483648..2147483647)")):
        with pytest.raises(mods.PackError, match=f"^pack '{pack.name}': {re.escape(why)}$"):
            mods.plan(pack, release, {engine.CONFIG: data}, params)
    other = _archive(TABLES | {"u": [["c", 6.0], ["d", None]]}, ROWS)
    with pytest.raises(mods.PackError, match=re.escape(
            f"pack 'one': gamedata/config.xbr <{len(other)} B, sha256 {_sha256(other)[:12]}> is not the vanilla USA one")):
        mods.plan(one, release, {engine.CONFIG: other})
