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
  text file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
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
_SAVE_HEADERS = (b"fileversion=", b"\xff\xfe" + "Name=".encode("utf-16-le"))
_PRIVATE_KEY = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\r?\n")

# One line of an x86 listing, Intel or AT&T syntax: an optional comment leader,
# address and instruction bytes, then a mnemonic with x86 operands (a register,
# a memory operand, an immediate or a branch target), or one that takes none
# after an address or bytes, or alone on its line.
_REG = (r"%?(?:[re]?(?:ax|bx|cx|dx|si|di|sp|bp|ip)|[abcd][lh]|r(?:[89]|1[0-5])[dwb]?|"
        r"[c-gs]s|xmm\d+|ymm\d+|mm\d|st(?:\(\d\))?|cr\d|dr\d)")
_MNEMONIC = (r"(?:mov(?:zx|sx|sxd|s[sd]|ap[sd]|up[sd]|[dq]|s[bwdq])?|lea|push|pop|call|jmp|j(?:n?[ezsopcgl]|n?[ab]e?|"
             r"n?[gl]e|e?cxz|p[eo])|cmp|test|add|adc|sub|sbb|inc|dec|and|or|xor|not|neg|sh[lr]d?|sa[lr]|ro[lr]|rc[lr]|"
             r"i?mul|i?div|xchg|cmov\w{1,3}|set\w{1,3}|f\w{2,7}|(?:add|sub|mul|div|min|max|sqrt|cmp|and|or|xor|ucomi|"
             r"comi|cvt\w{3,8}|unpck\w{2,4}|shuf)(?:p[sd]|s[sd])?|pxor|por|pand|movd|stos[bwd]?|lods[bwd]?|"
             r"scas[bwd]?|cmps[bwd]?|loop\w{0,2}|bt[src]?|bs[fr]|bswap|enter|int)[lbwq]?")
_IMMEDIATE = r"\$?[-+]?(?:0x[0-9a-f]+|[0-9a-f]+h|\d+|(?=[0-9a-f]*\d)[0-9a-f]{4,})(?=\s*(?:,|\(|$|[;#]))"
_MEMORY = rf"(?:[c-gs]s:)?\[\s*(?:{_REG}\b|0x[0-9a-f]+|[0-9a-f]+h\b|\w+_[0-9a-f]+)"
_LABEL = r"(?:(?:short|near|far)\s+)?(?:sub|loc|off|unk|byte|word|dword|j|fun|lab|dat|thunk_fun|ptr)_[0-9a-f]+\b"
_OPERAND = rf"(?:{_REG}\b|(?:byte|word|dword|qword|tbyte|xmmword)\s+ptr\b|{_MEMORY}|{_IMMEDIATE}|{_LABEL})"
_NO_OPERAND = (r"(?:ret[nf]?|leave|nop|int3|cdq|cwde|cbw|pushad?|popad?|pushfd?|popfd?|sahf|lahf|hlt|cld|std|"
               r"clc|stc|emms|fwait|wait|lock|rep(?:n?[ez])?(?:\s+(?:movs|stos|lods|scas|cmps)[bwdq]?)?)")
_PREFIX = r"(?:(?:0x)?[0-9a-f]{4,16}:?\s+(?:(?:[0-9a-f]{2}\s){1,15}\s*)?|(?:[0-9a-f]{2}\s){1,15}\s*)"
_INSTRUCTION = re.compile(rf"^\s*(?:[#;/*>|-]+\s*)?(?:{_PREFIX}?{_MNEMONIC}\s+{_OPERAND}|{_PREFIX}{_NO_OPERAND}\b|"
                          rf"{_NO_OPERAND}\s*(?:[;#].*)?$)", re.IGNORECASE)


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


def disassembly(text: str) -> int | None:
    """The line number starting the first run of 4 or more x86 instruction lines, or ``None``."""
    run = 0
    for number, line in enumerate(text.splitlines(), 1):
        run = run + 1 if _INSTRUCTION.match(line) else 0
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


def scan(root: Path = ROOT) -> list[str]:
    """``"<path>: <why>"`` for every tracked or untracked, not ignored,
    regular file under ``root`` that :func:`check` refuses."""
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True, check=True, timeout=60).stdout.decode()
    problems = []
    for rel in sorted(set(filter(None, listed.split("\0")))):
        path = root / rel
        if path.is_symlink() or not path.is_file():   # a link's target isn't committed
            continue
        try:
            why = check(root, rel)
        except FileNotFoundError:   # removed since the listing
            continue
        if why:
            problems.append(f"{rel}: {why}")
    return problems


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
