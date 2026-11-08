"""devkit's offline XBE reads, ``python -m devkit re xbe`` (``devkit/re/xbe.py``,
Step 4.11c; Modkit's ``azurik-mod xbe`` and its test_xbe_tools and
test_xbe_sections, leanly): each address maps through the XBE's own sections,
the scans and listings find what they say and print no byte (but
``hexdump``'s), a refusal is one line and exit 2, the verbs read the image of
the release asked for and name it, and a listing names what that release's
facts, the Ghidra project's snapshot, the anchors and the packs know. The RE
data (``devkit/re/data``, Step 4.11d1; Modkit's test_va_audit, its anchor and
header guards, leanly) holds each anchor checkably, both releases' XBEs
holding what it says, its structures compiling and a note for each function
of the facts. The synthetic XBEs are neither release's; the rest read both
images."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

import shimkit
from azurkit.core import facts, gate, iso
from devkit.re import xbe

ROOT = Path(__file__).resolve().parent.parent
HOLDS = {"f32": lambda v: struct.pack("<f", v), "u32": lambda v: struct.pack("<I", v),   # an anchor's value's bytes
         "cstr": lambda v: v.encode("ascii") + b"\0", "wstr": lambda v: v.encode("utf-16-le") + b"\0\0", "zero": bytes}
TEXT, RDATA, DATA = 0x11000, 0x14000, 0x15000   # the synthetic XBE's sections: at file 0x1000, 0x4000 and none


def synthetic(text: bytes = b"", rdata: bytes = b"") -> bytearray:
    """An XBE with ``.text`` at VA 0x11000 (file 0x1000), ``.rdata`` at 0x14000
    (file 0x4000) and a ``.data`` of 16 zero-filled bytes at 0x15000; its
    header names no release's thunk table."""
    out = bytearray(0x6000)
    out[0:4] = b"XBEH"
    struct.pack_into("<III", out, 0x104, 0x10000, 0, 0)
    struct.pack_into("<II", out, 0x11C, 3, 0x10140)
    names = 0x5F00
    for i, (name, va, size, raw) in enumerate(((b".text", TEXT, len(text), 0x1000),
                                               (b".rdata", RDATA, len(rdata), 0x4000), (b".data", DATA, 0, 0x5000))):
        struct.pack_into("<6I", out, 0x140 + 56 * i, 0x36, va, max(size, 0x10), raw, size, 0x10000 + names)
        out[names:names + len(name) + 1] = name + b"\0"
        names += len(name) + 1
    out[0x1000:0x1000 + len(text)] = text
    out[0x4000:0x4000 + len(rdata)] = rdata
    return out


def run(capsys, *argv: str) -> tuple[int, str, str]:
    """``python -m devkit re xbe ARGV``, in this process."""
    code = xbe.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_an_address_maps_through_the_xbes_own_sections_as_a_va_or_a_file_offset():
    """AZ-140: an address maps through the section table of the XBE read, so
    a moved section (an appended SHIMS) maps right, a VA in a section's
    zero-filled tail has no file offset and dumps the loader's zeros, and an
    address no section maps has none; a value from the base address up reads
    as a VA, under it as a file offset, unless told."""
    rdata = bytes(range(1, 17))
    data = synthetic(text=bytes(16), rdata=rdata)
    struct.pack_into("<I", data, 0x140 + 56 + 4, 0x39F000)       # .rdata's VA
    struct.pack_into("<I", data, 0x140 + 112 + 8, 0x2000)        # .data's virtual size (no file bytes)
    data = bytes(data)
    where = lambda *a: dataclasses.astuple(xbe.address(data, *a))   # noqa: E731
    assert [where(0x11000), where(0x1000), where(0x1000, "va"), where(0x39F000), where(0x16000),
            where(0xFFFFFFFF)] == [
        (0x11000, "va", 0x11000, 0x1000, ".text"), (0x1000, "file", 0x11000, 0x1000, ".text"),
        (0x1000, "va", None, None, None), (0x39F000, "va", 0x39F000, 0x4000, ".rdata"),
        (0x16000, "va", 0x16000, None, ".data"), (0xFFFFFFFF, "va", None, None, None)]
    assert [(r.va, r.file_offset, r.raw) for r in xbe.hexdump(data, 0x39F000, 32)] == [(0x39F000, 0x4000, rdata)]
    assert [(r.file_offset, r.raw) for r in xbe.hexdump(data, 0x16000, 16)] == [(None, bytes(16))]
    assert xbe.hexdump(data, 0x400000, 16) == []


def test_find_refs_lists_each_text_instruction_holding_the_va_as_an_immediate_or_a_displacement(tmp_path, capsys):
    """AZ-219: Capstone's imm and disp fields must equal the VA where the
    instruction encodes it: a ``push``, a ``mov`` to memory, an absolute and
    a based read and an indirect ``jmp`` hold 0x14003; a 0x68 that ends one
    instruction with the VA's bytes opening the next, and a PUSH opcode just
    before ``.text`` whose first bytes are the VA (L30), do not."""
    va = struct.pack("<I", 0x14003)
    text = (b"\x68" + va                       # 0x11000 push 0x14003
            + b"\xC7\x06" + va                 # 0x11005 mov dword ptr [esi], 0x14003
            + b"\xA1" + va                     # 0x1100B mov eax, dword ptr [0x14003]
            + b"\x8B\xB8" + va                 # 0x11010 mov edi, dword ptr [eax + 0x14003]
            + b"\xFF\x25" + va                 # 0x11016 jmp dword ptr [0x14003]
            + b"\xC6\x05\x00\x00\x02\x00\x68"  # 0x1101C mov byte ptr [0x20000], 0x68
            + b"\x03\x40\x01\x00\xC0")         # 0x11023 add eax, dword ptr [eax + 1]; add al, al
    path = tmp_path / "synthetic.xbe"
    path.write_bytes(synthetic(text=text))
    code, out, _ = run(capsys, "find-refs", "--va", "0x14003", "--xbe", str(path), "--json")
    assert (code, [(r["va"], r["file_offset"], f"{r['mnemonic']} {r['operands']}") for r in json.loads(out)]) == (0, [
        (0x11000, 0x1000, "push 0x14003"), (0x11005, 0x1005, "mov dword ptr [esi], 0x14003"),
        (0x1100B, 0x100B, "mov eax, dword ptr [0x14003]"), (0x11010, 0x1010, "mov edi, dword ptr [eax + 0x14003]"),
        (0x11016, 0x1016, "jmp dword ptr [0x14003]")])
    before = synthetic(text=va + b"\x90" * 4)
    before[0xFFF] = 0x68   # a PUSH opcode in the padding before .text
    assert xbe.va_refs(bytes(before), 0x14003) == []


def test_find_refs_by_string_takes_the_one_equal_string_and_refuses_several_with_their_vas(tmp_path, capsys):
    """AZ-249: the string equal to the text wins over one that holds it;
    several that hold it (none equal), or several equal copies, are one
    refusal listing their VAs, exit 2."""
    rdata = b"cannot read foo.txt\0foo.txt\0bar\0bar\0"   # 0x14000, 0x14014, 0x1401C, 0x14020
    path = tmp_path / "synthetic.xbe"
    path.write_bytes(synthetic(text=b"\x68\x14\x40\x01\x00" b"\xB8\x00\x40\x01\x00", rdata=rdata))
    code, out, _ = run(capsys, "find-refs", "--string", "foo.txt", "--xbe", str(path))
    assert (code, out.splitlines()) == (0, ["# the string 'foo.txt' at VA 0x14014",
                                            "1 .text instruction(s) hold VA 0x14014:",
                                            "  VA 0x00011000  file 0x001000  push 0x14014"])
    for text, vas in (("foo", ("0x00014000", "0x00014014")), ("bar", ("0x0001401C", "0x00014020"))):
        code, out, err = run(capsys, "find-refs", "--string", text, "--xbe", str(path))
        refusal = [line for line in err.splitlines() if not line.startswith(" ")]
        assert (code, out, refusal[-1].startswith("xbe: "), all(va in err for va in vas)) == (2, "", True, True)


def test_the_scans_find_floats_but_zero_and_strings_by_length_pattern_case_and_limit():
    """find-floats finds an unaligned float32 and never zero (``.rdata``'s
    zero runs would give thousands); strings keeps those ``min_len`` long or
    more, takes a regex and ignores case when asked, and returns at most
    ``limit`` (AZ-151: ``limit=0`` returned one)."""
    floats = bytes(synthetic(rdata=b"\0\0" + struct.pack("<f", 9.82) + bytes(64)))
    assert [(h.va, h.width) for h in xbe.find_floats(floats, 9.8, 9.9, (4,))] == [(0x14002, 4)]
    assert xbe.find_floats(bytes(synthetic(rdata=bytes(64))), -1.0, 1.0) == []
    data = bytes(synthetic(rdata=b"ab\0hello\0levels/fire/f1\0levels/water/w1\0Alpha_one\0alpha_two\0"))
    texts = lambda *a, **k: [h.text for h in xbe.find_strings(data, *a, **k)]   # noqa: E731
    assert (texts("", min_len=5)[:2], texts(r"levels/\w+/[fw]", regex=True), texts("ALPHA"),
            texts("ALPHA", ignore_case=True), [len(texts("lpha", limit=n)) for n in (0, 1, 2)]) == (
        ["hello", "levels/fire/f1"], ["levels/fire/f1", "levels/water/w1"], [], ["Alpha_one", "alpha_two"],
        [0, 1, 2])


CODE = bytes.fromhex(
    "E80B000000"   # 0x11000 call 0x11010
    "D84E10"       # 0x11005 fmul dword ptr [esi + 0x10]
    "F20F58C1"     # 0x11008 addsd xmm0, xmm1   (SSE2)
    "F30F58C1"     # 0x1100C addss xmm0, xmm1   (SSE: a Pentium III has it)
    "660FEFC1"     # 0x11010 pxor xmm0, xmm1    (SSE2)
    "0FEFC1"       # 0x11014 pxor mm0, mm1      (MMX)
    "F390"         # 0x11017 pause              (a NOP on a Pentium III)
    "DF0E"         # 0x11019 fisttp word ptr [esi] (SSE3, which capstone leaves ungrouped)
    "C3")          # 0x1101B ret


def test_insns_calls_and_sse2_find_their_instructions_and_what_a_pentium3_lacks(tmp_path, capsys):
    """insns matches a mnemonic and operand text case-blind; calls lists each
    direct call and its callee (or those to one VA); sse2 lists SSE2, its
    successors and the ungrouped fisttp, not SSE, MMX or pause (AZ-021)."""
    path = tmp_path / "synthetic.xbe"
    path.write_bytes(synthetic(text=CODE))
    lines = lambda *argv: run(capsys, *argv, "--xbe", str(path))[1].splitlines()   # noqa: E731
    assert (lines("insns", "--mnemonic", "FMUL", "--operand", "DWORD PTR [ESI + 0x10]"),
            lines("insns", "--operand", "xmm1"), lines("calls"), lines("calls", "0x11005"), lines("sse2")) == (
        ["0x00011005  fmul dword ptr [esi + 0x10]", "(1 found)"],
        ["0x00011008  addsd xmm0, xmm1", "0x0001100C  addss xmm0, xmm1", "0x00011010  pxor xmm0, xmm1",
         "(3 found)"],
        ["0x00011000  call 0x00011010", "(1 found)"], ["(0 found)"],
        ["0x00011008  addsd xmm0, xmm1", "0x00011010  pxor xmm0, xmm1", "0x00011019  fisttp word ptr [esi]",
         "(3 found)"])


def test_dis_and_fn_list_each_instruction_without_its_bytes(tmp_path, capsys):
    """dis VA[:N] lists N instructions from VA, stopping at the section's end
    (a byte capstone can't decode, a cut-off one too, is ``(bad)``); fn VA
    lists what VA reaches without a call, in address order: both arms of a
    branch and a loop once, up to each ``ret``, but not the padding a ``jmp``
    skips or the next function. A line is ``0xVA  mnemonic operands``, never
    the instruction's bytes (D87)."""
    code = bytes.fromhex(
        "55"      # 0x11000 push ebp
        "85C0"    # 0x11001 test eax, eax
        "7403"    # 0x11003 je 0x11008
        "31C0"    # 0x11005 xor eax, eax
        "C3"      # 0x11007 ret
        "EB01"    # 0x11008 jmp 0x1100b
        "CC"      # 0x1100A int3: padding the jmp skips
        "48"      # 0x1100B dec eax
        "75FD"    # 0x1100C jne 0x1100b
        "5D"      # 0x1100E pop ebp
        "C3"      # 0x1100F ret
        "90"      # 0x11010 nop: the next function
        "E8")     # 0x11011 a call cut off by the section's end
    path = tmp_path / "synthetic.xbe"
    path.write_bytes(synthetic(text=code))
    out = lambda *argv: run(capsys, *argv, "--xbe", str(path))[1]   # noqa: E731
    dis, fn = out("dis", "0x1100A:2"), out("fn", "0x11000")
    assert (dis.splitlines(), out("dis", "0x11010", "--count", "5").splitlines()) == (
        ["0x0001100A  int3", "0x0001100B  dec eax"], ["0x00011010  nop", "0x00011011  (bad)"])
    assert fn.splitlines() == [
        "0x00011000  push ebp", "0x00011001  test eax, eax", "0x00011003  je 0x11008", "0x00011005  xor eax, eax",
        "0x00011007  ret", "0x00011008  jmp 0x1100b", "0x0001100B  dec eax", "0x0001100C  jne 0x1100b",
        "0x0001100E  pop ebp", "0x0001100F  ret"]
    assert json.loads(out("fn", "0x11000", "--json"))[2] == {"va": 0x11003, "mnemonic": "je", "operands": "0x11008"}
    assert not re.search(r"[0-9A-Fa-f]{9}", dis + fn)


def test_a_file_that_is_no_xbe_or_whose_section_table_runs_off_it_is_one_line_and_exit_2(tmp_path, capsys):
    """Modkit's test_xbe_sections, on core.xbe: a file that is neither an
    image nor an XBE, a header too short for its table or one that claims
    2^31 sections, an address no section maps and a ``--regex`` that
    doesn't compile (a bad pattern, a repeat count past re's limit, nesting
    deeper than its parser recurses), are each one ``xbe:`` line on stderr
    and exit 2, with nothing on stdout."""
    def header(count: int) -> bytes:
        out = bytearray(0x200)
        out[0:4] = b"XBEH"
        struct.pack_into("<I", out, 0x104, 0x10000)
        struct.pack_into("<II", out, 0x11C, count, 0x10180)
        return bytes(out)

    good = tmp_path / "synthetic.xbe"
    good.write_bytes(synthetic())
    refused = []
    for name, data, argv in (("zz.bin", b"ZZZZ" + bytes(0x400), ["sections"]), ("short.xbe", header(100), ["sections"]),
                             ("huge.xbe", header(0x7FFFFFFF), ["sections"]), (good.name, None, ["read", "0x400000"]),
                             (good.name, None, ["strings", "[", "--regex"]),
                             (good.name, None, ["strings", "a{4294967296}", "--regex"]),
                             (good.name, None, ["strings", "(" * 100000 + ")" * 100000, "--regex"])):
        path = tmp_path / name
        if data is not None:
            path.write_bytes(data)
        code, out, err = run(capsys, *argv, "--xbe", str(path))
        refused.append((code, out, err.splitlines()[-1].startswith("xbe: "),
                        sum(line.startswith("xbe: ") for line in err.splitlines())))
    assert refused == [(2, "", True, 1)] * 7


def test_python_m_devkit_runs_the_re_areas_xbe_verb_and_names_an_xbe_of_neither_release(tmp_path):
    """The area dispatcher lists the re area's xbe verb and runs it; stderr
    names the file read, ``neither release`` for a synthetic XBE, and its
    ``sha256[:12]``, and stdout is the verb's."""
    path = tmp_path / "synthetic.xbe"
    path.write_bytes(data := synthetic())
    listed = subprocess.run([sys.executable, "-m", "devkit", "re"], cwd=ROOT, capture_output=True, text=True)
    done = subprocess.run([sys.executable, "-m", "devkit", "re", "xbe", "sections", "--xbe", str(path)], cwd=ROOT,
                          capture_output=True, text=True)
    assert (listed.returncode, "  xbe  " in listed.stdout, done.returncode, done.stderr,
            done.stdout.splitlines()[2].split()[:2]) == (
        0, True, 0, f"synthetic.xbe: neither release (default.xbe sha256 {hashlib.sha256(data).hexdigest()[:12]})\n",
        [".text", "0x00011000"])


def test_the_verbs_read_the_image_of_the_release_asked_for_and_name_it(usa_iso, europe_iso, tmp_path, monkeypatch,
                                                                       capsys):
    """With neither --iso nor --xbe a verb reads the image of --region's
    release, USA's by default, and names it, the release and its XBE's
    ``sha256[:12]`` on stderr; a build of a release is named so; a --region
    an --iso isn't, or no image where the release's variable points, is one
    ``xbe:`` line and exit 2."""
    monkeypatch.setenv(gate.USA.env, str(usa_iso))
    monkeypatch.setenv(gate.EUROPE.env, str(europe_iso))
    with iso.Reader(usa_iso) as r:
        built = bytearray(r.read("default.xbe"))
    built[0x1000] ^= 0xFF
    (tmp_path / "built.xbe").write_bytes(built)
    err = lambda *argv: run(capsys, "sections", *argv)[::2]   # noqa: E731
    named = [err(), err("--region", "europe"), err("--xbe", str(tmp_path / "built.xbe"))]
    assert named == [
        (0, f"{usa_iso.name}: the USA release (default.xbe sha256 {facts.of(gate.USA).sha256[:12]})\n"),
        (0, f"{europe_iso.name}: the Europe release (default.xbe sha256 {facts.of(gate.EUROPE).sha256[:12]})\n"),
        (0, f"built.xbe: a build of the USA release (default.xbe sha256 {hashlib.sha256(built).hexdigest()[:12]})\n")]
    assert err("--iso", str(europe_iso), "--region", "usa") == (
        2, f"xbe: --region usa, but {europe_iso.name} is the Europe release\n")
    monkeypatch.setenv(gate.USA.env, str(tmp_path / "none.iso"))
    code, why = err("--region", "usa")
    assert (code, why.count("\n"), why.startswith(f"xbe: no image: {gate.USA.env} names no file")) == (2, 1, True)


def test_the_reads_print_values_and_the_listings_name_what_the_facts_ghidra_the_anchors_and_packs_know(
        usa_iso, europe_iso, capsys):
    """read prints a value at a VA, never its bytes (``bss`` where the loader
    zero-fills; a pointer's target section and its name or data C string,
    never code bytes as a string; FLT_MAX's shortest text, AZ-659); vtable
    lists the slots up to the next vtable an instruction stores, and says when
    the section ends short of --slots; find-refs --data finds the data dwords
    holding a VA; insns and calls take --range and --in-fn, strings -i ignores
    case, dis --count N is VA:N, and the source flags go before the verb too.
    A listing line names the address its operands hold: the release's facts'
    function (``_alldiv``, not the snapshot's ``__alldiv``) or kernel import's
    slot, else the Ghidra project's function or data label, an anchor or a
    pack's site (a ``custom_apply``'s by its pack), Europe's at its own
    address. sections is the table the facts hold, for both releases."""
    usa, europe = ["--iso", str(usa_iso)], ["--iso", str(europe_iso)]
    rows = [
        (["read", "0x1980A8", "--as", "f32", *usa], ["0x001980A8  f32   9.8"]),
        (["read", "0x1A2540", "--as", "f32", *usa], ["0x001A2540  f32   3.4028235e+38"]),
        (["read", "0x1BCDD8", *usa], ["0x001BCDD8  u32   bss"]),
        (["read", "0x1AA2DC", "--as", "ptr", *usa], ["0x001AA2DC  ptr   0x0019C164  .rdata  'm_head'"]),
        (["read", "0x19E278", "--as", "ptr", *usa], ["0x0019E278  ptr   0x0005C920  .text  calculate_save_signature"]),
        (["read", "0x190990", "--as", "ptr", *usa], ["0x00190990  ptr   0x0002B461  .text"]),
        (["read", "0x2B461", "--as", "cstr", *usa], []),
        (["read", "0x19ECF8:2", "--as", "cstr", *usa],
         ["0x0019ECF8  cstr  'levels/water/w1'", "0x0019ED08  cstr  'start-playing'"]),
        (["vtable", "0x19C3D8", *usa], ["+0x0CC  0x00081240  .text", "(55 slots)"]),
        (["vtable", "0x19CAE0", *usa], ["+0x040  0x000EB3E7  .text", "(17 slots)"]),
        (["vtable", "0x1A2980", "--slots", "10", *usa], ["(4 of 10 slots: the section ends)"]),
        (["find-refs", "--va", "0x81240", "--data", *usa],
         ["1 data dword(s) hold VA 0x81240:", "  VA 0x0019C4A4  .rdata"]),
        (["find-refs", "--string", "fx_magic_timer", *usa],
         ["3 .text instruction(s) hold VA 0x19C1AC:", "  VA 0x00083006  file 0x073006  push 0x19c1ac"]),
        (["find-floats", "9.7", "9.9", "--width", "float", *usa],
         ["3 float(s) in [9.7, 9.9]:", "  VA 0x001980A8  file 0x190D08  width=4  value=9.8"]),
        (["calls", "0xCB2A0", "--in-fn", "0x41F40", *usa],
         ["0x00041F67  call 0x000CB2A0  ; anim_marker_position", "(1 found)"]),
        (["calls", "--in-fn", "0x41F40", "--section", ".text", *usa], []),
        (["insns", "--mnemonic", "call", "--operand", "+ 0xb0]", "--range", "0x81000:0x82000", *usa],
         ["0x00081271  call dword ptr [eax + 0xb0]", "(1 found)"]),
        (["insns", "--operand", "[0x18f3e4]", "--range", "0xDF000:0xE0000", *usa],
         ["0x000DF998  call dword ptr [0x18f3e4]  ; MmFreeContiguousMemory", "(1 found)"]),
        (["strings", "-i", "LEVELS/WATER/W1", *usa], ["  VA 0x0019ECF8  file 0x197958  len=  15  'levels/water/w1'"]),
        ([*usa, "dis", "0x41F67", "--count", "1"], ["0x00041F67  call 0xcb2a0  ; anim_marker_position"]),
        (["dis", "0x8B763", "--count", "1", *usa], ["0x0008B763  test eax, 0x10000"]),
        ([*europe, "dis", "0x41F67:1"], ["0x00041F67  call 0xcb420  ; anim_marker_position"]),
        (["calls", "0xED000", *usa], ["0x000E6C9D  call 0x000ED000  ; _alldiv"]),
        (["calls", "0x9F630", *usa], ["0x000120AC  call 0x0009F630  ; cvar_get_or_create"]),
        (["dis", "0x18A2C:1", *usa], ["0x00018A2C  push 0x187bc0  ; g_DeviceType_MU"]),
        (["dis", "0x859DC:1", *usa], ["0x000859DC  fld dword ptr [0x1980a8]  ; gravity"]),
        (["dis", "0x8598C:1", *europe], ["0x0008598C  fld dword ptr [0x19a250]  ; gravity"]),
        (["dis", "0x59B37:1", *usa], ["0x00059B37  fld dword ptr [0x1983e8]  ; fps_unlock"]),
    ]
    missing = []   # each row whose exit isn't 0 with its lines (or 2, a refusal, with none)
    for argv, want in rows:
        code, out, _ = run(capsys, *argv)
        if code != (0 if want else 2) or not set(want) <= set(out.splitlines()):
            missing.append((argv, code))
    tables = [json.loads(run(capsys, "sections", "--json", *src)[1]) for src in (usa, europe)]
    assert (missing, tables) == ([], [[dataclasses.asdict(s) for s in facts.of(r).sections] for r in gate.RELEASES])


def test_the_re_data_holds_each_anchor_checkably_its_structures_compiling_and_a_note_per_facts_function(tmp_path):
    """Modkit's header guards (test_va_audit's AnchorCoverageDrift): each
    anchor names its USA address and section and, outside .text, one thing
    the vanilla XBE holds there, so the next test checks every one; the
    anchors live in anchors.toml alone (structs.h defines none); structs.h
    compiles with the shims' flags, its offset asserts holding; and the
    notes name exactly the facts' functions."""
    unchecked = [name for name, a in xbe.anchors().items()
                 if not (isinstance(a["va"], int) and set(a) - {"note"} - set(HOLDS) == {"va", "section"}
                         and len(set(a) & set(HOLDS)) == (a["section"] != ".text"))]
    structs = (xbe.DATA / "structs.h").read_text(encoding="utf-8")
    probe = tmp_path / "probe.c"
    probe.write_text(f'#include "{(xbe.DATA / "structs.h").as_posix()}"\n', encoding="utf-8")
    compiled = bool(shimkit.compile(probe))
    notes = tomllib.loads((xbe.DATA / "function_notes.toml").read_text(encoding="utf-8"))
    assert (unchecked, re.findall(r"#define\s+AZURIK_\w+_VA\b", structs), compiled, sorted(notes)) == (
        [], [], True, sorted(facts.of(gate.USA).functions))


def test_each_anchor_holds_what_anchors_toml_says_in_both_releases(usa_iso, europe_iso):
    """Modkit's anchor guards (test_va_audit's VaAnchorAudit and
    PhysicsAnchorsLandInText, AZ-079), over both releases: each anchor's
    address (Europe's from the facts' address map) lands in its section, and
    a data anchor's bytes, as the game sees them, are its value (a float32
    exactly), its string to the NUL, or its zero bytes."""
    wrong = []
    for release, path in ((gate.USA, usa_iso), (gate.EUROPE, europe_iso)):
        with iso.Reader(path) as r:
            data = r.read("default.xbe")
        known = facts.of(release)
        for name, a in xbe.anchors().items():
            va = known.va(a["va"])
            section = xbe.address(data, va, "va").section
            want = b"".join(HOLDS[k](v) for k, v in a.items() if k in HOLDS)
            if section != a["section"] or b"".join(row.raw for row in xbe.hexdump(data, va, len(want))) != want:
                wrong.append((release.name, name, f"0x{va:08X}", section))
    assert wrong == []
