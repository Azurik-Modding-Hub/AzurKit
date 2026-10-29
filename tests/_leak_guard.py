"""Leak guard: nothing taken from the game in a file this repository tracks,
could commit or pushes (D3; Q273: D87's rules and the web plan's disassembly
rule, repo-wide, with no allow-list).

Stdlib only. ``tests/test_leak_guard.py`` runs it in the pure tier, the
``pre-push`` hook that ``bootstrap.py`` writes runs it on every push, and it
runs directly::

    python3 -I tests/_leak_guard.py                 # exit 1 and one line per file on a hit
    python3 -I tests/_leak_guard.py --pre-push <remote> < <git's ref lines>

The first reads every tracked and untracked, not ignored, file. The hook reads
every file the pushed commits add or change, in the commits no remote-tracking
ref of ``<remote>`` reaches (a new remote: the whole history), so a file
committed and deleted again is caught too. Refused:

- a whole game file under any name: 16 B or more whose size and sha256 match an
  entry of either release's manifest (``tests/oracle/core/``);
- a game image or a game file of its kind, modded or not: an XISO or its first
  part (``MICROSOFT*XBOX*MEDIA`` at 0x10000), an ``.iso``/``.xiso``/``.iso.NNN``
  name, an XBE (``XBEH`` at 0) or an XBR (``xobx`` at 0);
- personal data: an Xbox save (a ``.sav`` or ``.xbx`` name, or ``fileversion=``
  or a SaveMeta.xbx's BOM and UTF-16 ``Name=`` at 0), an xemu disk (qcow2), an
  EEPROM (an ``eeprom`` name ending ``.bin``), a guest RAM snapshot
  (``AZL3SNAP`` at 0) or a private key;
- a disassembly listing: 4 or more consecutive lines of x86 instructions in a
  text file, each at its line's start or in its trailing comment (after
  ``#``, ``//``, ``/*`` or ``;``).

One more rule needs the game itself, so the vanilla tier runs it
(``tests/test_leak_guard.py``, with both releases' :data:`VANILLA_FILES`
read from the images), and so does ``scripts/land.py`` over every commit it
lands (:func:`vanilla_runs_in_commits`), but neither the hook nor the
command line: no byte or hex literal in a source file (:data:`SOURCE_DIRS`)
holds :data:`VANILLA_RUN` or more bytes in a row of a vanilla
``default.xbe`` or ``gamedata/config.xbr`` (:func:`vanilla_runs`). Such a
run is read from the player's image at its address instead. The literals (:func:`byte_literals`) are a Python file's
bytes literals, ``bytes.fromhex`` and hex strings, lists of byte-sized ints
and the concatenations and repeats of these, and in any text file runs of
hex byte pairs, ``\\xNN`` escapes or ``0xNN, ...`` or decimal lists. A run
of one byte value repeated isn't counted, nor is text (a str that isn't
hex): a format's marker, a save's ``fileversion=`` say, is written as text.

A committed shim object (a ``.o`` there) is read too: each section with
file bytes of an i386 COFF one (:func:`object_sections`), for
:data:`OBJECT_RUN` or more bytes in a row in code and
:data:`OBJECT_DATA_RUN` in the rest, and the whole file for
:data:`OBJECT_RUN`, so bytes outside its sections, and an object that
doesn't parse, are read as well. What the compiler makes from a shim's
source shares shorter runs with the game by chance (its code's instruction
idioms, up to 20 B, and its float constants, up to 10 B, over Modkit's 43
built objects), and the source itself is read at :data:`VANILLA_RUN`. A
window of text (printable ASCII or NUL: a string's) or of at most 3 byte
values (a constant such as the identity matrix) isn't counted there.
"""

from __future__ import annotations

import ast
import bisect
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from array import array
from collections.abc import Iterator, Mapping
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = (ROOT / "tests/oracle/core/azurik_mod/assets/vanilla_manifest.json",
             ROOT / "tests/oracle/core/azurik_mod/assets/europe_manifest.json")
MAGIC_SPAN = 0x10020
MIN_WHOLE_FILE = 16      # a smaller whole file is no use on its own (D87)
MAX_TEXT = 16 << 20      # a text file past this is read for its head only
DISASSEMBLY_RUN = 4
_ISO_NAME = re.compile(r"\.x?iso(\.\d+)?$")
_SAVE_NAMES = (".sav", ".xbx")
_SAVE_HEADERS = ("fileversion=".encode("ascii"), b"\xff\xfe" + "Name=".encode("utf-16-le"))   # markers, as text
_PRIVATE_KEY = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\r?\n")

# One line of an x86 listing, Intel or AT&T syntax: an optional comment leader,
# address and instruction bytes, then a mnemonic with x86 operands (a register,
# a memory operand, an immediate or a branch target), or one that takes none
# after an address or bytes, or alone on its line or comment. It is matched at
# the line's start and after each comment marker (_COMMENT).
_REG = (r"%?(?:[re]?(?:ax|bx|cx|dx|si|di|sp|bp|ip)|[abcd][lh]|r(?:[89]|1[0-5])[dwb]?|"
        r"[c-gs]s|xmm\d+|ymm\d+|mm\d|st(?:\(\d\))?|cr\d|dr\d)")
_MNEMONIC = (r"(?:mov(?:zx|sx|sxd|s[sd]|ap[sd]|up[sd]|[dq]|s[bwdq])?|lea|push|pop|call|jmp|j(?:n?[ezsopcgl]|n?[ab]e?|"
             r"n?[gl]e|e?cxz|p[eo])|cmp|test|add|adc|sub|sbb|inc|dec|and|or|xor|not|neg|sh[lr]d?|sa[lr]|ro[lr]|rc[lr]|"
             r"i?mul|i?div|xchg|cmov\w{1,3}|set\w{1,3}|f\w{2,7}|(?:add|sub|mul|div|min|max|sqrt|cmp|and|or|xor|ucomi|"
             r"comi|cvt\w{3,8}|unpck\w{2,4}|shuf)(?:p[sd]|s[sd])?|pxor|por|pand|movd|stos[bwd]?|lods[bwd]?|"
             r"scas[bwd]?|cmps[bwd]?|loop\w{0,2}|bt[src]?|bs[fr]|bswap|enter|int)[lbwq]?")
_IMMEDIATE = r"\$?[-+]?(?:0x[0-9a-f]+|[0-9a-f]+h|\d+|(?=[0-9a-f]*\d)[0-9a-f]{4,})(?=\s*(?:,|\(|$|[;#]|\*/))"
_MEMORY = rf"(?:[c-gs]s:)?\[\s*(?:{_REG}\b|0x[0-9a-f]+|[0-9a-f]+h\b|\w+_[0-9a-f]+)"
_LABEL = r"(?:(?:short|near|far)\s+)?(?:sub|loc|off|unk|byte|word|dword|j|fun|lab|dat|thunk_fun|ptr)_[0-9a-f]+\b"
_OPERAND = rf"(?:{_REG}\b|(?:byte|word|dword|qword|tbyte|xmmword)\s+ptr\b|{_MEMORY}|{_IMMEDIATE}|{_LABEL})"
_NO_OPERAND = (r"(?:ret[nf]?|leave|nop|int3|cdq|cwde|cbw|pushad?|popad?|pushfd?|popfd?|sahf|lahf|hlt|cld|std|"
               r"clc|stc|emms|fwait|wait|lock|rep(?:n?[ez])?(?:\s+(?:movs|stos|lods|scas|cmps)[bwdq]?)?)")
_PREFIX = r"(?:(?:0x)?[0-9a-f]{4,16}:?\s+(?:(?:[0-9a-f]{2}\s){1,15}\s*)?|(?:[0-9a-f]{2}\s){1,15}\s*)"
_INSTRUCTION = re.compile(rf"\s*(?:[#;/*>|-]+\s*)?(?:{_PREFIX}?{_MNEMONIC}\s+{_OPERAND}|{_PREFIX}{_NO_OPERAND}\b|"
                          rf"{_NO_OPERAND}\s*(?:(?:[;#]|\*/).*)?$)", re.IGNORECASE)
_COMMENT = re.compile(r"#|//|/\*|;")


@cache
def _whole_files() -> dict[int, dict[str, str]]:
    """size -> {sha256: "<release> ISO's <path>"} over both manifests."""
    by_size: dict[int, dict[str, str]] = {}
    for manifest in MANIFESTS:
        release = manifest.name.removesuffix("_manifest.json")
        for iso_path, (size, sha256) in json.loads(manifest.read_text(encoding="utf-8"))["files"].items():
            if size >= MIN_WHOLE_FILE:
                by_size.setdefault(size, {})[sha256] = f"{release} ISO's {iso_path}"
    return by_size


def _instruction(line: str) -> bool:
    """An x86 instruction at the line's start or after one of its comment markers."""
    return any(_INSTRUCTION.match(line, pos) for pos in (0, *(m.end() for m in _COMMENT.finditer(line))))


def disassembly(text: str) -> int | None:
    """The line number starting the first run of 4 or more x86 instruction lines, or ``None``."""
    run = 0
    for number, line in enumerate(text.splitlines(), 1):
        run = run + 1 if _instruction(line) else 0
        if run == DISASSEMBLY_RUN:
            return number - DISASSEMBLY_RUN + 1
    return None


def check_blob(rel: str, head: bytes, size: int, sha256: str | None, text: str | None) -> str | None:
    """Why a file ``rel`` of ``size`` bytes can't be committed, or ``None``.
    ``head`` is its first :data:`MAGIC_SPAN` bytes, ``sha256`` its digest
    (``None`` when no game file has its size) and ``text`` its text (``None``
    for a binary file)."""
    if sha256 and (whole := _whole_files().get(size, {}).get(sha256)):
        return f"the {whole} (same size and sha256)"
    name = rel.lower().rsplit("/", 1)[-1]
    if head[0x10000:0x10014] == b"MICROSOFT*XBOX*MEDIA":
        return "XISO volume descriptor at 0x10000"
    if _ISO_NAME.search(name):
        return "ISO image or part (.iso/.xiso/.iso.NNN name)"
    if head[:4] == b"XBEH":
        return "XBE magic at 0"
    if head[:4] == b"xobx":
        return "XBR magic at 0"
    if name.endswith(_SAVE_NAMES) or head.startswith(_SAVE_HEADERS):
        return "Xbox save (.sav/.xbx name or save header at 0)"
    if head[:4] == b"QFI\xfb":
        return "qcow2 disk image (an xemu HDD) at 0"
    if "eeprom" in name and name.endswith(".bin"):
        return "EEPROM (eeprom*.bin name)"
    if head[:8] == b"AZL3SNAP":
        return "guest RAM snapshot (console keys) at 0"
    if _PRIVATE_KEY.match(head):
        return "private key at 0"
    if text is not None and (line := disassembly(text)) is not None:
        return f"x86 disassembly: {DISASSEMBLY_RUN} or more instruction lines from line {line}"
    return None


def _text(data: bytes) -> str | None:
    return None if b"\0" in data[:8192] else data.decode("utf-8", errors="replace")


def check_bytes(rel: str, data: bytes) -> str | None:
    """:func:`check_blob` for a whole file's bytes."""
    sha = hashlib.sha256(data).hexdigest() if len(data) in _whole_files() else None
    return check_blob(rel, data[:MAGIC_SPAN], len(data), sha, _text(data[:MAX_TEXT]))


def check(root: Path, rel: str) -> str | None:
    """Why ``root/rel`` can't be committed, or ``None`` (a file past
    :data:`MAX_TEXT` is checked by its head and digest only)."""
    path = root / rel
    if (size := path.stat().st_size) <= MAX_TEXT:
        return check_bytes(rel, path.read_bytes())
    with open(path, "rb") as f:
        head = f.read(MAGIC_SPAN)
        f.seek(0)
        sha = hashlib.file_digest(f, "sha256").hexdigest() if size in _whole_files() else None
    return check_blob(rel, head, size, sha, None)


def _listed(root: Path) -> list[str]:
    """Every tracked or untracked, not ignored, regular file under ``root``
    (a link's target isn't committed)."""
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True, check=True, timeout=60).stdout.decode()
    return [rel for rel in sorted(set(filter(None, listed.split("\0"))))
            if not (root / rel).is_symlink() and (root / rel).is_file()]


def scan(root: Path = ROOT) -> list[str]:
    """``"<path>: <why>"`` for every tracked or untracked, not ignored,
    regular file under ``root`` that :func:`check` refuses."""
    problems = []
    for rel in _listed(root):
        try:
            why = check(root, rel)
        except FileNotFoundError:   # removed since the listing
            continue
        if why:
            problems.append(f"{rel}: {why}")
    return problems


SOURCE_DIRS = ("src/", "tests/", "scripts/", "web/")
VANILLA_FILES = ("default.xbe", "gamedata/config.xbr")   # the game files the code reads bytes of
VANILLA_RUN = 8   # bytes in a row of one of them that a literal may not hold
OBJECT_RUN = 32        # bytes in a row of one of them that a shim object's code, or the whole object, may not hold
OBJECT_DATA_RUN = 16   # and that its other sections may not hold
_HEX_TEXT = re.compile(r"(?<![0-9A-Za-z_])(?:[0-9A-Fa-f]{2})+(?:[ \t]+(?:[0-9A-Fa-f]{2})+)*(?![0-9A-Za-z_])")
_ESCAPES = re.compile(r"(?:\\x[0-9A-Fa-f]{2})+")
_BYTE_LIST = re.compile(r"(?<![\w.])0x[0-9A-Fa-f]{1,2}(?:\s*,\s*0x[0-9A-Fa-f]{1,2})+(?![\w.])")
_DECIMAL = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_DECIMAL_LIST = re.compile(rf"(?<![\w.]){_DECIMAL}(?:\s*,\s*{_DECIMAL})+(?![\w.])")
_HEX_STRING = re.compile(r"\s*(?:[0-9A-Fa-f]{2}\s*)+")


def _byte(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and 0 <= node.value <= 0xFF


def _pieces(node: ast.AST) -> list[bytes | None] | None:
    """The bytes a Python expression makes from literals, as the literal
    runs between the parts that come from elsewhere (``None``), or ``None``
    when it makes no bytes from a literal."""
    match node:
        case ast.Constant(value=bytes() as value):
            return [value]
        case ast.Constant(value=str() as value) if _HEX_STRING.fullmatch(value):
            return [bytes.fromhex(value)]
        case ast.Call(func=ast.Attribute(value=ast.Name(id="bytes" | "bytearray"), attr="fromhex"),
                      args=[ast.Constant(value=str() as value)]):
            try:
                return [bytes.fromhex(value)]
            except ValueError:
                return None
        case ast.Call(func=ast.Name(id="bytes" | "bytearray"), args=[ast.List() | ast.Tuple() as seq]):
            return [bytes([e.value]) if _byte(e) else None for e in seq.elts] or None
        case ast.List() | ast.Tuple() | ast.Set() if len(node.elts) > 1 and all(map(_byte, node.elts)):
            return [bytes(e.value for e in node.elts)]
        case ast.BinOp(op=ast.Add()):
            left, right = _pieces(node.left), _pieces(node.right)
            return None if left is None and right is None else (left or [None]) + (right or [None])
        case ast.BinOp(op=ast.Mult(), left=left, right=ast.Constant(value=int() as times)) if 0 < times <= 1 << 16:
            made = _pieces(left)
            return [made[0] * times] if made and len(made) == 1 and made[0] is not None else None
    return None


def _runs(pieces: list[bytes | None]) -> Iterator[bytes]:
    run = b""
    for piece in [*pieces, None]:
        if piece is None:
            if run:
                yield run
            run = b""
        else:
            run += piece


def byte_literals(rel: str, text: str) -> list[tuple[int, bytes]]:
    """``(line, bytes)`` for each byte or hex literal in the source file
    ``rel``: in Python, each literal expression's bytes (a bytes literal, a
    ``bytes.fromhex`` or hex string, a list of byte-sized ints, and their
    ``+`` and ``*``), the runs a part from elsewhere splits; in any file,
    each run of hex byte pairs, ``\\xNN`` escapes or ``0xNN`` or decimal
    items. A literal of fewer than :data:`VANILLA_RUN` bytes isn't listed."""
    found = []
    if rel.endswith(".py"):
        def visit(node: ast.AST, folded: bool) -> None:
            pieces = _pieces(node)
            if pieces is not None and not folded:
                found.extend((node.lineno, run) for run in _runs(pieces))
            for child in ast.iter_child_nodes(node):
                visit(child, pieces is not None)
        try:
            visit(ast.parse(text), False)
        except SyntaxError:
            pass
    lines = [0, *(m.end() for m in re.finditer("\n", text))]
    for pattern, value in ((_HEX_TEXT, lambda s: bytes.fromhex(s)),
                           (_ESCAPES, lambda s: bytes.fromhex(s.replace("\\x", ""))),
                           (_BYTE_LIST, lambda s: bytes(int(x, 16) for x in s.split(","))),
                           (_DECIMAL_LIST, lambda s: bytes(int(x) for x in s.split(",")))):
        for m in pattern.finditer(text):
            found.append((bisect.bisect_right(lines, m.start()), value(m.group())))
    return [(line, data) for line, data in found if len(data) >= VANILLA_RUN]


def _repeated(window: bytes) -> bool:
    """A window of one byte value repeated, which no rule counts."""
    return window.count(window[0]) == len(window)


def _plain(window: bytes) -> bool:
    """A window an object's run isn't counted at: text (printable ASCII,
    tab, newline or NUL) or at most 3 byte values."""
    return len(set(window)) <= 3 or all(32 <= b < 127 or b in b"\0\t\n\r" for b in window)


def _windows(data: bytes, skip=_repeated) -> Iterator[int]:
    """Each :data:`VANILLA_RUN`-byte window of ``data`` as an int, but a
    window ``skip`` passes."""
    for i in range(len(data) - VANILLA_RUN + 1):
        window = data[i:i + VANILLA_RUN]
        if not skip(window):
            yield int.from_bytes(window, sys.byteorder)


def _longest(data: bytes, haystack: bytes, skip=_repeated, held: set[int] | None = None) -> int:
    """The longest run of ``data`` from a window ``skip`` doesn't pass that
    ``haystack`` holds, when it is :data:`VANILLA_RUN` bytes or more; else 0.
    ``held``, when given, holds every window of ``haystack`` (as
    :func:`_windows` gives them) that ``data`` has: only those are searched."""
    best = 0
    for i in range(len(data) - VANILLA_RUN + 1):
        window = data[i:i + VANILLA_RUN]
        if (skip(window) or (held is not None and int.from_bytes(window, sys.byteorder) not in held)
                or window not in haystack):
            continue
        end = i + VANILLA_RUN
        while end < len(data) and data[i:end + 1] in haystack:
            end += 1
        best = max(best, end - i)
    return best


def object_sections(data: bytes) -> list[tuple[str, bytes, bool]] | None:
    """``(name, bytes, code)`` of each section with file bytes of the i386
    COFF object ``data`` (a shim's ``.o``), ``code`` when its flags say it
    holds code, or ``None`` when it isn't one."""
    try:
        machine, count, _, symbols_at, symbol_count, optional, _ = struct.unpack_from("<HHIIIHH", data, 0)
        if machine != 0x014C:
            return None
        strings = data[symbols_at + 18 * symbol_count:]
        sections = []
        for i in range(count):
            at = 20 + optional + 40 * i
            raw_size, raw, flags = *struct.unpack_from("<II", data, at + 16), struct.unpack_from("<I", data, at + 36)[0]
            name = data[at:at + 8].split(b"\0")[0]
            if name[:1] == b"/" and name[1:].isdigit():
                name = strings[int(name[1:]):].split(b"\0")[0]
            if raw_size and not flags & 0x80 and raw + raw_size <= len(data):   # 0x80: no file bytes
                sections.append((name.decode("ascii", "replace") or f"#{i + 1}", data[raw:raw + raw_size],
                                 bool(flags & 0x20)))   # IMAGE_SCN_CNT_CODE
        return sections
    except struct.error:
        return None


def vanilla_named(files: Mapping[tuple[str, str], bytes]) -> dict[str, bytes]:
    """``{name: bytes}``, the files a literal is checked against, from
    ``{(release label, path): its vanilla bytes}`` (each release's
    :data:`VANILLA_FILES`): named ``"<release> <path>"``, or by the path
    alone, once, when every release holds the same file (config.xbr)."""
    out = {}
    for (label, path), data in files.items():
        out[path if all(d == data for (_, p), d in files.items() if p == path) else f"{label} {path}"] = data
    return out


def _held(literals: list[tuple[str, bytes]], files: Mapping[str, bytes],
          parts: list[tuple[str, bytes, str, int]] = ()) -> list[str]:
    """``"<where>: a <n> B literal holds <m> B in a row of the <file>"`` for
    each ``(where, literal)`` that holds :data:`VANILLA_RUN` or more bytes
    in a row of one of ``files`` (:func:`vanilla_named`), in the literals'
    order, then ``"<where>: a <n> B <what> holds ..."`` for each of an
    object's ``parts`` (``(where, bytes, what, least)``, :func:`_read`) that
    holds ``least`` or more (text and windows of at most 3 byte values
    aside). Lengths only, never the bytes."""
    kinds = [(where, data, "literal", _repeated, VANILLA_RUN) for where, data in literals]
    kinds += [(where, data, what, _plain, least) for where, data, what, least in parts]
    wanted = {w for _, data, _, skip, _ in kinds for w in _windows(data, skip)}
    held: dict[str, set[int]] = {}
    for name, haystack in files.items():
        held[name] = set()
        for k in range(VANILLA_RUN):   # every window of the file, as ints, VANILLA_RUN at a time
            words = array("Q")
            words.frombytes(haystack[k:k + (len(haystack) - k) // 8 * 8])
            held[name] |= wanted.intersection(words)
    problems = []
    for where, data, what, skip, least in kinds:
        for name, haystack in files.items():
            if (not held[name].isdisjoint(_windows(data, skip))
                    and (run := _longest(data, haystack, skip, held[name])) >= least):
                problems.append(f"{where}: a {len(data)} B {what} holds {run} B in a row of the {name}")
    return list(dict.fromkeys(problems))


def _read(rel: str, data: bytes, where: str) -> tuple[list[tuple[str, bytes]], list[tuple[str, bytes, str, int]]]:
    """The literals (``"<rel>:<line><where>"``) of a source file ``rel``,
    or the parts of a shim object (:func:`_held`): each section
    (``"<rel> (<section>)<where>"``), at :data:`OBJECT_RUN` for code and
    :data:`OBJECT_DATA_RUN` for the rest, and the whole file (``"<rel>
    (file)<where>"``) at :data:`OBJECT_RUN`, parsed or not."""
    if rel.endswith(".o"):
        return [], [*((f"{rel} ({name}){where}", body, "section", OBJECT_RUN if code else OBJECT_DATA_RUN)
                      for name, body, code in object_sections(data) or ()),
                    (f"{rel} (file){where}", data, "file", OBJECT_RUN)]
    if (text := _text(data[:MAX_TEXT])) is not None:
        return [(f"{rel}:{line}{where}", lit) for line, lit in byte_literals(rel, text)], []
    return [], []


def vanilla_runs(root: Path, files: Mapping[str, bytes]) -> list[str]:
    """``"<path>:<line>: a <n> B literal holds <m> B in a row of the
    <file>"`` for each literal (:func:`byte_literals`) in a source file
    under :data:`SOURCE_DIRS` that holds :data:`VANILLA_RUN` or more bytes
    in a row of one of ``files`` (:func:`vanilla_named`), and ``"<path>
    (<section>): a <n> B section holds ..."`` for each section of a shim
    object there that holds :data:`OBJECT_RUN` or more (:data:`OBJECT_DATA_RUN`
    in a section that isn't code), and ``"<path> (file): a <n> B file holds
    ..."`` for each that holds :data:`OBJECT_RUN` or more anywhere. Lengths
    only, never the bytes."""
    literals, parts = [], []
    for rel in _listed(root):
        if rel.startswith(SOURCE_DIRS):
            found = _read(rel, (root / rel).read_bytes(), "")
            literals += found[0]
            parts += found[1]
    return sorted(_held(literals, files, parts))


def _git(root: Path, *args: str, stdin: bytes = b"") -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, check=True,
                          timeout=600).stdout


def _added(root: Path, revs: list[str]) -> dict[tuple[str, str], str]:
    """``{(path, blob): the first commit adding it}`` for every regular file
    a commit of ``git rev-list revs`` adds or changes, oldest commit first."""
    commits = _git(root, "rev-list", "--reverse", *revs)
    raw = _git(root, "diff-tree", "--stdin", "-r", "-m", "--root", "--no-renames", "-z", stdin=commits)
    first: dict[tuple[str, str], str] = {}
    commit, fields = "", iter(raw.split(b"\0"))
    for field in fields:
        if field.startswith(b":"):
            _, mode, _, blob, status = field.decode().split()
            path = os.fsdecode(next(fields))
            if status != "D" and mode in ("100644", "100755"):   # files; not links or submodules
                first.setdefault((path, blob), commit)
        elif field:
            commit = field.decode()
    return first


def _blobs(root: Path, blobs: list[str]) -> Iterator[bytes]:
    """Each blob's content, in order."""
    with subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as cat:
        for blob in blobs:
            cat.stdin.write(f"{blob}\n".encode())
            cat.stdin.flush()
            size = int(cat.stdout.readline().split()[2])   # "<oid> blob <size>\n<content>\n"
            yield cat.stdout.read(size + 1)[:size]
        cat.stdin.close()


def vanilla_runs_in_commits(root: Path, revs: list[str], files: Mapping[str, bytes]) -> list[str]:
    """:func:`vanilla_runs` over history: ``"<path>:<line> in <commit>: a <n>
    B literal holds <m> B in a row of the <file>"`` for each
    literal in a source file under :data:`SOURCE_DIRS` that a commit of
    ``git rev-list revs`` (``[top, "--not", base]``, say) adds or changes,
    and ``"<path> (<section> or file) in <commit>: ..."`` for each shim
    object it adds or changes, named with the first commit adding it,
    oldest first. A run that a later commit removes again is still named:
    it stays in the history. Lengths only, never the bytes."""
    added = [(path, blob, commit) for (path, blob), commit in _added(root, revs).items()
             if path.startswith(SOURCE_DIRS)]
    literals, parts = [], []
    for (path, _, commit), data in zip(added, _blobs(root, [blob for _, blob, _ in added]), strict=True):
        found = _read(path, data, f" in {commit[:12]}")
        literals += found[0]
        parts += found[1]
    return _held(literals, files, parts)


def scan_push(root: Path, remote: str, updates: str) -> list[str]:
    """``"<path> in <commit>: <why>"`` for every file a commit being pushed
    adds or changes that :func:`check_bytes` refuses, named with the first
    such commit. ``remote`` and ``updates`` are a ``pre-push`` hook's first
    argument and stdin; the commits are those the pushed oids reach and no
    ``refs/remotes/<remote>/`` ref does."""
    tips = [oid for oid in (line.split()[1] for line in updates.splitlines() if line.strip()) if oid.strip("0")]
    if not tips:   # only deletions
        return []
    added = list(_added(root, [*tips, "--not", f"--remotes={remote}"]).items())
    problems = []
    for ((path, _), commit), data in zip(added, _blobs(root, [blob for (_, blob), _ in added]), strict=True):
        if why := check_bytes(path, data):
            problems.append(f"{path} in {commit[:12]}: {why}")
    return problems


def main() -> int:
    if sys.argv[1:2] == ["--pre-push"]:
        problems = scan_push(ROOT, sys.argv[2], sys.stdin.read())
    else:
        problems = scan(ROOT)
    for problem in problems:
        print(f"leak guard: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
