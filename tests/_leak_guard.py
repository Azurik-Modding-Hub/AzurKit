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
(``tests/test_leak_guard.py``, with both releases' ``default.xbe`` read from
the images) and neither the hook nor the command line does: no byte or hex
literal in a source file (:data:`SOURCE_DIRS`) holds :data:`VANILLA_RUN` or
more bytes in a row of a vanilla ``default.xbe`` (:func:`vanilla_runs`). Such
a run is read from the player's image at its address instead. The literals
(:func:`byte_literals`) are a Python file's bytes literals, ``bytes.fromhex``
and hex strings, lists of byte-sized ints and the concatenations and repeats
of these, and in any text file runs of hex byte pairs, ``\\xNN`` escapes or
``0xNN, ...`` lists. A run of one byte value repeated isn't counted, nor is
text (a str that isn't hex): a format's marker, a save's ``fileversion=``
say, is written as text.
"""

from __future__ import annotations

import ast
import bisect
import hashlib
import json
import os
import re
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
VANILLA_RUN = 8   # bytes in a row of a vanilla default.xbe that a literal may not hold
_HEX_TEXT = re.compile(r"(?<![0-9A-Za-z_])(?:[0-9A-Fa-f]{2})+(?:[ \t]+(?:[0-9A-Fa-f]{2})+)*(?![0-9A-Za-z_])")
_ESCAPES = re.compile(r"(?:\\x[0-9A-Fa-f]{2})+")
_BYTE_LIST = re.compile(r"(?<![\w.])0x[0-9A-Fa-f]{1,2}(?:\s*,\s*0x[0-9A-Fa-f]{1,2})+(?![\w.])")
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
    each run of hex byte pairs, ``\\xNN`` escapes or ``0xNN`` items. A
    literal of fewer than :data:`VANILLA_RUN` bytes isn't listed."""
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
                           (_BYTE_LIST, lambda s: bytes(int(x, 16) for x in s.split(",")))):
        for m in pattern.finditer(text):
            found.append((bisect.bisect_right(lines, m.start()), value(m.group())))
    return [(line, data) for line, data in found if len(data) >= VANILLA_RUN]


def _windows(data: bytes) -> Iterator[int]:
    """Each :data:`VANILLA_RUN`-byte window of ``data`` as an int, but a
    window of one byte value repeated."""
    for i in range(len(data) - VANILLA_RUN + 1):
        window = data[i:i + VANILLA_RUN]
        if window.count(window[0]) != VANILLA_RUN:
            yield int.from_bytes(window, sys.byteorder)


def _longest(data: bytes, haystack: bytes) -> int:
    """The longest run of ``data`` (one byte value repeated aside) that
    ``haystack`` holds, when it is :data:`VANILLA_RUN` bytes or more; else 0."""
    best = 0
    for i in range(len(data) - VANILLA_RUN + 1):
        window = data[i:i + VANILLA_RUN]
        if window.count(window[0]) == VANILLA_RUN or window not in haystack:
            continue
        end = i + VANILLA_RUN
        while end < len(data) and data[i:end + 1] in haystack:
            end += 1
        best = max(best, end - i)
    return best


def vanilla_runs(root: Path, xbes: Mapping[str, bytes]) -> list[str]:
    """``"<path>:<line>: a <n> B literal holds <m> B in a row of the <release>
    default.xbe"`` for each literal (:func:`byte_literals`) in a source file
    under :data:`SOURCE_DIRS` that holds :data:`VANILLA_RUN` or more bytes
    in a row of one of ``xbes`` (``{release label: its vanilla
    default.xbe}``). Lengths only, never the bytes."""
    literals = []
    for rel in _listed(root):
        if rel.startswith(SOURCE_DIRS) and (text := _text((root / rel).read_bytes()[:MAX_TEXT])) is not None:
            literals += [(rel, line, data) for line, data in byte_literals(rel, text)]
    wanted = {w for *_, data in literals for w in _windows(data)}
    held: dict[str, set[int]] = {}
    for label, xbe in xbes.items():
        held[label] = set()
        for k in range(VANILLA_RUN):   # every window of the XBE, as ints, VANILLA_RUN at a time
            words = array("Q")
            words.frombytes(xbe[k:k + (len(xbe) - k) // 8 * 8])
            held[label] |= wanted.intersection(words)
    problems = []
    for rel, line, data in literals:
        for label, xbe in xbes.items():
            if not held[label].isdisjoint(_windows(data)) and (run := _longest(data, xbe)):
                problems.append(f"{rel}:{line}: a {len(data)} B literal holds {run} B in a row of the {label} "
                                f"default.xbe")
    return sorted(set(problems))


def scan_push(root: Path, remote: str, updates: str) -> list[str]:
    """``"<path> in <commit>: <why>"`` for every file a commit being pushed
    adds or changes that :func:`check_bytes` refuses, named with the first
    such commit. ``remote`` and ``updates`` are a ``pre-push`` hook's first
    argument and stdin; the commits are those the pushed oids reach and no
    ``refs/remotes/<remote>/`` ref does."""
    def git(*args: str, stdin: bytes = b"") -> bytes:
        return subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, check=True,
                              timeout=600).stdout
    tips = [oid for oid in (line.split()[1] for line in updates.splitlines() if line.strip()) if oid.strip("0")]
    if not tips:   # only deletions
        return []
    commits = git("rev-list", "--reverse", *tips, "--not", f"--remotes={remote}")
    raw = git("diff-tree", "--stdin", "-r", "-m", "--root", "--no-renames", "-z", stdin=commits)
    first: dict[tuple[str, str], str] = {}   # (path, blob) -> the first commit adding it
    commit, fields = "", iter(raw.split(b"\0"))
    for field in fields:
        if field.startswith(b":"):
            _, mode, _, blob, status = field.decode().split()
            path = os.fsdecode(next(fields))
            if status != "D" and mode in ("100644", "100755"):   # files; not links or submodules
                first.setdefault((path, blob), commit)
        elif field:
            commit = field.decode()
    problems = []
    with subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as cat:
        for (path, blob), added in first.items():
            cat.stdin.write(f"{blob}\n".encode())
            cat.stdin.flush()
            size = int(cat.stdout.readline().split()[2])   # "<oid> blob <size>\n<content>\n"
            data = cat.stdout.read(size + 1)[:size]
            if why := check_bytes(path, data):
                problems.append(f"{path} in {added[:12]}: {why}")
        cat.stdin.close()
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
