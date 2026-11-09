"""devkit's XBR file tools, ``python -m devkit xbr`` (``devkit/xbr/``, Step
4.6l; Modkit's ``azurik-mod xbr`` verbs and their test_xbr_cli and
test_xbr_schema_lint, leanly): inspect labels each column and picks a
stride, diff reports what differs and exits 1 when anything does, edit
writes a new file only whole and never over its input, xref and verify read
the pointer graph AzurKit's parse models, and each refuses an input it
can't read in one line. The synthetic XBRs hold their TOC as the engine
reads it; config.xbr is the vanilla file AzurKit ships; the levels come
from the USA image."""

from __future__ import annotations

import json
import re
import struct
import time
from collections import Counter
from pathlib import Path

import pytest

from azurkit.core import iso
from azurkit.core.xbr import Document
from azurkit.core.xbr.nodes import parse_toc
from azurkit.tools import data, mods
from azurkit.tools.mods import Pack, XbrParametricEdit
from devkit.xbr import diff, edit, inspect, verify, xref

CONFIG = Path(data.__file__).with_name("config.xbr")


def xbr(*entries: tuple[str, bytes]) -> bytes:
    """An XBR of ``entries`` (tag, payload): the header, the TOC at 0x3C
    (each offset from the data area, its size, tag and flags), then the
    payloads in order; no trailer."""
    start = 0x3C + 16 * len(entries)
    out = bytearray(start)
    out[:4] = b"xobx"
    struct.pack_into("<II", out, 0x0C, len(entries), start)
    for k, (tag, body) in enumerate(entries):
        struct.pack_into("<II4sI", out, 0x3C + 16 * k, len(out) - start, len(body), tag.encode(), 0)
        out += body
    return bytes(out)


def run(capsys, verb, *argv) -> tuple[int, str, str]:
    code = verb.main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def one_line(err: str, verb: str) -> bool:
    return len(err.splitlines()) == 1 and err.startswith(f"xbr {verb}: ")


def test_inspect_labels_each_column_by_its_first_fitting_reading_and_refuses_by_name(tmp_path, capsys):
    """A float, a fourcc, zeros, a small whole float (an int), an XBE
    address, an offset inside the file and a big word each take their
    label; the word's bytes show only with --hex (a human's); a TOC size
    past the file's end detects a stride without raising (Modkit's H14);
    an unknown tag names the file's tags, and a folder is one line, exit 1."""
    record = struct.pack("<f4sIfII", 1.5, b"rdms", 0, 3.0, 0x12345, 0x40) + struct.pack("<I", 0xDEADBEEF)
    path = tmp_path / "surf.xbr"
    path.write_bytes(xbr(("surf", record * 2)))
    insp = inspect.inspect_xbr(path, tag="surf", entries=2, stride=len(record), fields_per_row=7)
    assert [(f.offset, f.best_type, f.value_display) for f in insp.records[0].fields] == [
        (0, "f32", "1.5"), (4, "fourcc", "rdms"), (8, "zero", "0"), (12, "int32", "3"),
        (16, "ptr", "0x00012345"), (20, "off", "+0x40"), (24, "u32", "0xDEADBEEF")]
    assert (insp.stride, insp.auto_detected_stride, len(insp.records)) == (28, False, 2)
    argv = (path, "--tag", "surf", "--stride", 28, "--entries", 1, "--fields-per-row", 7)
    code, out, _ = run(capsys, inspect, *argv)
    assert code == 0 and "[fourcc]  rdms" in out and "0xDEADBEEF" in out and "efbeadde" not in out
    code, out, _ = run(capsys, inspect, *argv, "--hex", "--json")
    assert json.loads(out)["records"][0]["fields"][6]["raw"] == "efbeadde"
    short = bytearray(xbr(("surf", bytes(16))))
    struct.pack_into("<I", short, 0x40, 1000)   # entry 0's size, past the file's end
    (tmp_path / "short.xbr").write_bytes(short)
    assert inspect.inspect_xbr(tmp_path / "short.xbr", tag="surf").stride == 16
    code, _, err = run(capsys, inspect, path, "--tag", "zzzz")
    assert code == 1 and one_line(err, "inspect") and "Available: ['surf']" in err
    code, _, err = run(capsys, inspect, tmp_path, "--tag", "node")
    assert code == 1 and one_line(err, "inspect")


def test_diff_reports_tag_sizes_strings_and_in_place_changes_and_exits_1_when_the_files_differ(tmp_path, capsys):
    """Modkit's AZ-143: a same-size value edit is an in-place change of its
    entry (its first differing offset, how many bytes), a header-only one
    still differs; a grown tag and a new string show; the same file is no
    change, exit 0; a folder or a missing file is one line, exit 1 (AZ-121)."""
    before = xbr(("tabl", bytes(16)), ("node", bytes(16)))
    node = len(before) - 16
    edited = bytearray(before)
    edited[node + 5] = edited[node + 9] = 0x40
    header = bytearray(before)
    header[0x20] = 1
    grown = xbr(("tabl", bytes(16)), ("node", b"lamppost\0".ljust(32, b"\0")))
    for name, body in (("a", before), ("b", edited), ("c", header), ("d", grown)):
        (tmp_path / f"{name}.xbr").write_bytes(body)
    a = tmp_path / "a.xbr"
    code, out, _ = run(capsys, diff, a, a)
    assert code == 0 and "(no changes detected)" in out
    code, out, _ = run(capsys, diff, a, tmp_path / "b.xbr", "--json")
    assert code == 1 and json.loads(out)["byte_changes"] == [
        {"tag": "node", "entry_index": 1, "first_offset": node + 5, "changed_bytes": 2}]
    code, out, _ = run(capsys, diff, a, tmp_path / "c.xbr")
    assert code == 1 and "differ only in bytes this diff doesn't compare" in out
    code, out, _ = run(capsys, diff, a, tmp_path / "d.xbr")
    assert code == 1 and "Size delta: +16 B" in out and "~ tag 'node'  16 → 32 B  (+16)" in out
    assert "    + 'lamppost'" in out
    for path in (tmp_path, tmp_path / "missing.xbr"):
        code, _, err = run(capsys, diff, path, a)
        assert code == 1 and one_line(err, "diff")


def test_edit_writes_strings_bytes_and_cells_into_a_new_file_only_whole(tmp_path, capsys):
    """--set-string with --tag rewrites that tag's copy only (AZ-124's
    framing); a string past its slot, bytes past the file or before it (a
    negative offset), a bad spec and a NaN are refused, one line, exit 1, with nothing written; the input is
    never the output (AZ-152, D36); config.xbr's number and string cells are
    written by the file's names, the damage table's too (Modkit's model
    couldn't, its Q160), and the result parses whole."""
    slot = b"lamp\0" + bytes(11)
    src = tmp_path / "in.xbr"
    src.write_bytes(before := xbr(("surf", slot), ("node", slot)))
    out = tmp_path / "out.xbr"
    code, log, _ = run(capsys, edit, src, out, "--set-string", "lamp=bulb", "--tag", "node")
    want = bytearray(before)
    want[len(before) - 16:len(before) - 12] = b"bulb"
    assert code == 0 and out.read_bytes() == bytes(want) and "OK  replace_string_at" in log
    for argv in (("--set-string", "lamp=lamppost"), ("--replace-bytes", f"{len(before) - 2}:AAAAAAAA"),
                 ("--replace-bytes=-2:AAAA",), ("--set-string", "lamp"), ("--set-value", "nonsense")):
        code, _, err = run(capsys, edit, src, tmp_path / "no.xbr", *argv)
        assert code == 1 and one_line(err, "edit") and not (tmp_path / "no.xbr").exists(), argv
    for at in (-10, len(before)):    # never from the end, which grew the file (Modkit's L34)
        with pytest.raises(edit.XbrEditError, match="out of range"):
            edit.XbrEditor(before).replace_string_at(at, "AB")
    code, _, err = run(capsys, edit, src, src, "--set-string", "lamp=bulb")
    assert code == 1 and one_line(err, "edit") and src.read_bytes() == before
    code, _, err = run(capsys, edit, CONFIG, tmp_path / "no.xbr", "--set-value", "damage/norm_1/Damage=nan")
    assert code == 1 and "is not a finite number" in err and not (tmp_path / "no.xbr").exists()
    code, log, _ = run(capsys, edit, CONFIG, out, "--set-value", "critters_critter_data/garret4/walkSpeed=42",
                       "--set-value", "damage/norm_1/Damage=5", "--set-keyed-string",
                       "critters_damage/garret4/name=abc")
    tables = Document(out.read_bytes()).tables
    assert code == 0 and log.count("  OK  ") == 4
    assert (tables["critters_critter_data"].number("garret4", "walkSpeed"), tables["damage"].number("norm_1", "Damage"),
            "abc" in tables["critters_damage"].cols) == (42.0, 5.0, True)
    assert run(capsys, verify, out)[0] == 0


def test_xref_and_verify_read_the_pointer_graph_the_parse_models_and_name_what_breaks_it(tmp_path, capsys,
                                                                                        monkeypatch):
    """config.xbr's 18 keyed tables hold 10,340 pointers, every one in
    them (Modkit's model counted 10,112: it read the damage and magic tables
    as records); an entry's refs are those inside it; --section-index past
    the TOC exits 2; verify passes the file and the packs' cells against the
    schema, and lists a pack's cell the schema doesn't document; a string
    pointer moved past its table is named, exit 1, and a folder or a file
    that isn't an XBR is one line, exit 1, for both (AZ-144)."""
    code, out, _ = run(capsys, xref, CONFIG)
    assert code == 0 and "Total refs: 10340" in out and "  tabl: 10340" in out and "Unmodeled" not in out
    code, out, _ = run(capsys, xref, CONFIG, "--section-index", 0, "--format", "json")
    doc = json.loads(out)
    first = Document(CONFIG.read_bytes()).entries[0]
    assert doc["ref_counts_by_tag"] == {"tabl": 10340} and doc["unmodeled_sections"] == []
    assert doc["refs"] and all(first.start <= int(r["src_offset"], 16) < first.start + first.size for r in doc["refs"])
    assert run(capsys, xref, CONFIG, "--section-index", 18)[0] == 2
    code, out, _ = run(capsys, verify, CONFIG, "--cross-check-schema")
    assert code == 0 and out.splitlines() == ["xbr verify: cross-check: OK",
                                              "xbr verify: OK  (18 TOC entries, 10340 refs, 0 unmodeled sections)"]
    loose = XbrParametricEdit(name="x", label="x", table="armor_properties", entity="Fire", prop="nowhere",
                              default=1.0, slider_min=0.0, slider_max=2.0, slider_step=0.1)
    monkeypatch.setitem(mods.PACKS, "loose", Pack(name="loose", description="", sites=(loose,)))
    code, out, _ = run(capsys, verify, CONFIG, "--cross-check-schema")
    assert code == 0 and "  - loose: armor_properties.nowhere" in out
    broken = bytearray(CONFIG.read_bytes())
    table = Document(bytes(broken)).tables["armor_hit_fx"]
    field, _ = next(table.refs())
    struct.pack_into("<I", broken, field, table.size)   # the first row name's pointer, past its table
    (tmp_path / "broken.xbr").write_bytes(broken)
    (tmp_path / "notes.txt").write_bytes(b"not an xbr file")
    for verb in (xref, verify):
        code, _, err = run(capsys, verb, tmp_path / "broken.xbr")
        assert code == 1 and "config table armor_hit_fx: row 0's name" in err
        for path in (tmp_path, tmp_path / "notes.txt"):
            code, _, err = run(capsys, verb, path)
            assert code == 1 and one_line(err, verb.__name__.rpartition(".")[2]), err


def test_the_xbr_verbs_read_the_games_level_files(usa_iso, tmp_path, capsys):
    """On the USA image's levels: a1's 2,696 entries parse whole with no
    modelled pointer (every tag but tabl and indx is unmodeled); w1's surf
    records are 16 bytes, detected; w1 against w2 shrinks, every level tag
    changes size and hundreds of strings differ. Modkit's TOC invariants: a1,
    w1 and town hold every level tag, one levl and one node (town two);
    hourglass is 20 surf entries of 52 and 1,152 B; fx holds 113 effects (a
    node, ndbg, sprv and gshd each); their nodes' strings hold a1's key_air*,
    w1's levels/, speech/ or loc/english paths, town's levels/ ways out and
    fx's *_timer names; and town's surf scan takes under 2 s of CPU (AZ-231:
    a loaded host adds waiting, not work)."""
    tags, strings = {}, {}
    with iso.Reader(usa_iso) as r:
        for name in ("a1", "w1", "w2", "town", "hourglass", "fx"):
            data = r.read(f"gamedata/{name}.xbr")
            if name in ("a1", "w1", "w2"):
                (tmp_path / f"{name}.xbr").write_bytes(data)
            toc = parse_toc(data)
            tags[name] = Counter(e.tag for e in toc), {e.size for e in toc}
            strings[name] = {text for e in toc if e.tag == "node" for _, text in diff.find_strings_in_region(
                data, e.file_offset, e.size, min_len=8 if name == "fx" else 6)}
            if name == "town":
                surf, start = [e for e in toc if e.tag == "surf"], time.process_time()
                for e in surf:
                    diff.find_strings_in_region(data, e.file_offset, e.size)
                scan = len(surf), time.process_time() - start
    level = {"levl", "node", "ndbg", "gshd", "surf", "rdms", "tern", "pbrw", "pbrc", "sprv", "wave"}
    assert [(level <= set(tags[n][0]), tags[n][0]["levl"], tags[n][0]["node"]) for n in ("a1", "w1", "town")] == [
        (True, 1, 1), (True, 1, 1), (True, 1, 2)]
    assert (dict(tags["hourglass"][0]), tags["hourglass"][1]) == ({"surf": 20}, {52, 1152})
    assert [tags["fx"][0][t] for t in ("node", "ndbg", "sprv", "gshd")] == [113] * 4
    assert any("key_air" in text for text in strings["a1"])
    assert any(re.search(r"levels/|speech/|loc/english", text) for text in strings["w1"])
    assert any(text.startswith("levels/") for text in strings["town"])
    assert any(text.endswith(("_timer", "Timer")) for text in strings["fx"])
    assert scan[0] == 349 and scan[1] < 2.0
    code, out, _ = run(capsys, xref, tmp_path / "a1.xbr")
    assert code == 0 and "Total refs: 0" in out and "  'surf': 179 entries" in out
    assert run(capsys, verify, tmp_path / "a1.xbr")[1] == (
        "xbr verify: OK  (2696 TOC entries, 0 refs, 2696 unmodeled sections)\n")
    insp = inspect.inspect_xbr(tmp_path / "w1.xbr", tag="surf")
    assert (insp.stride, insp.auto_detected_stride, len(insp.records)) == (16, True, 3)
    found = diff.diff_xbr(tmp_path / "w1.xbr", tmp_path / "w2.xbr")
    assert found.total_size_delta < 0 and {"surf", "rdms", "node", "levl"} <= set(found.size_deltas)
    assert len(found.string_changes) > 100


# --- Step 4.28g: Modkit's string scan (test_xbr_toc_scan) -----------------------------------------------------------


def test_the_string_scan_takes_nul_ended_runs_of_its_length_with_a_letter_unless_told_otherwise():
    """Modkit's ``find_strings_in_region`` (``xbr diff``'s scan): a run with no NUL after it is no string,
    ``min_len`` drops the shorter, and a run with no letter is dropped unless ``require_alpha`` is off."""
    data = b"\x00hello\x00world_foo\x00\x00hi\x00verylongstring\x00$|._\x00!@#$%^\x00unended"

    def found(**kw) -> list[tuple[int, str]]:
        return diff.find_strings_in_region(data, 0, len(data), **kw)
    assert found(min_len=4) == [(1, "hello"), (7, "world_foo"), (21, "verylongstring")]
    assert found(min_len=10) == [(21, "verylongstring")]
    assert found(min_len=4, require_alpha=False) == [(1, "hello"), (7, "world_foo"), (21, "verylongstring"),
                                                     (36, "$|._"), (41, "!@#$%^")]
