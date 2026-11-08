"""``python -m devkit re struct-diff``: the struct layouts the RE data
declares (``devkit/re/data/structs.h``, Modkit's ``azurik.h`` structures)
against whatever Ghidra has in its Data Type Manager (Modkit's, ported in
Step 4.11d2).  Surfaces three classes of drift:

1. **Missing in Ghidra** — structs.h has ``typedef struct X {...}``
   but the Ghidra project doesn't.  Push it into Ghidra
   (``ghidra-sync --push-structs``) so the decompiler gets typed output.
2. **Missing in header** — Ghidra has a typed struct the header
   hasn't captured yet.
3. **Size / field disagreement** — same name on both sides but
   different total size or offset drift.  Fix whichever side is
   wrong.

## Parser scope (header side)

The header parser is deliberately small: it scans
``typedef struct NAME { ... } NAME;`` blocks and extracts each
field's ``offset`` + ``name`` + ``type`` from:

- an inline ``/* +0xHH ... */`` comment (primary source);
- or an inline ``// +0xHH`` line comment.

Text inside a comment is never a declaration (AZ-198).  An array
keeps its dimensions on its type (``u8 x[12]`` has ``c_type``
``u8[12]``), and a function pointer ``void (*advance)(float dt)`` is
a pointer field ``advance`` of ``c_type`` ``void (*)(float dt)``
(AZ-233).

Fields without a recognisable offset comment are captured as
``HeaderField(name="<typename>", offset=-1)`` so the diff can
still surface them (with "offset unknown" flagged) rather than
silently dropping them.

Bit-fields, unions, and nested typedefs are NOT supported —
none of the hand-written structs use them.  A deliberate
limitation; when a shim lands that needs one of those features,
we'll extend the parser then.

## Output shape

``diff_structs`` returns a :class:`StructDiffReport` whose
``entries`` list is sorted by struct name and whose top-level
counters drive the verb's summary banner.  Callers can render
either plain text (via :func:`format_report`) or JSON (via
``to_json_dict``).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .ghidra_client import GhidraClient, GhidraClientError, GhidraStruct, Refused, connect, emit

__all__ = [
    "HEADER",
    "HeaderField",
    "HeaderStruct",
    "StructDiffEntry",
    "StructDiffReport",
    "diff_structs",
    "format_report",
    "main",
    "parse_header_structs",
]

HEADER = Path(__file__).resolve().parent / "data" / "structs.h"   # the RE data's structures


# ---------------------------------------------------------------------------
# Header parser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeaderField:
    """One struct field captured from the C header.

    ``offset`` is -1 when the parser couldn't find a
    ``+0xHH``-style comment; downstream diff logic flags this
    specially so we don't confuse "missing offset in our header"
    with "drift between header and Ghidra".
    """

    name: str
    c_type: str
    offset: int
    comment: str = ""


@dataclass(frozen=True)
class HeaderStruct:
    """One ``typedef struct NAME { ... } NAME;`` block."""

    name: str
    fields: tuple[HeaderField, ...]
    declared_size: int | None = None  # filled when an explicit
    # `_Static_assert(sizeof(X) == N)` is found nearby; else None.

    def inferred_size(self) -> int | None:
        """Infer total size from the max offset seen (+ field size
        guess from ``c_type``).  Falls back to ``None`` when the
        final field has an unknown offset."""
        known = [f for f in self.fields if f.offset >= 0]
        if not known:
            return None
        tail = max(known, key=lambda f: f.offset)
        return tail.offset + _type_size_guess(tail.c_type)


_OFFSET_RE = re.compile(r"\+\s*0x([0-9A-Fa-f]+)")
_STATIC_ASSERT_RE = re.compile(
    r"_Static_assert\s*\(\s*sizeof\s*\(\s*(\w+)\s*\)\s*==\s*"
    r"(0x[0-9A-Fa-f]+|\d+)")


def parse_header_structs(source: str | Path) -> list[HeaderStruct]:
    """Extract every ``typedef struct NAME { ... } NAME;`` block
    from a C header (or path to one).

    Returns a list sorted by struct name.  Does NOT follow ``#include``
    directives — each file is parsed independently, which matches
    how the RE header is structured (one declaration per
    typedef, no cross-file typedef chains).
    """
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8", errors="replace")
    else:
        text = source

    results: list[HeaderStruct] = []
    size_hints = dict(_STATIC_ASSERT_RE.findall(text))
    # Normalise the hints to int.
    size_map: dict[str, int] = {}
    for name, tok in size_hints.items():
        try:
            size_map[name] = (int(tok, 16) if tok.startswith("0x")
                              else int(tok))
        except ValueError:
            continue

    # Walk the text manually so we can balance braces — regex-only
    # parsing gets confused by nested braces in field initialisers
    # (not used in structs.h today but trivial to hit later).
    idx = 0
    length = len(text)
    while True:
        match = re.search(
            r"typedef\s+struct\s+(?:(\w+)\s+)?\{", text[idx:])
        if not match:
            break
        body_start = idx + match.end()
        depth = 1
        j = body_start
        while j < length and depth:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            j += 1
        if depth != 0:
            break
        body = text[body_start:j - 1]
        tail_match = re.match(r"\s*(\w+)\s*;", text[j:])
        if not tail_match:
            idx = j
            continue
        struct_name = tail_match.group(1)
        fields = _extract_fields(body)
        declared_size = size_map.get(struct_name)
        results.append(HeaderStruct(
            name=struct_name,
            fields=tuple(fields),
            declared_size=declared_size))
        idx = j + tail_match.end()

    results.sort(key=lambda s: s.name)
    return results


_FIELD_LINE_RE = re.compile(
    r"([^;\n{]*?);([^\n;]*)",
    flags=re.DOTALL,
)
# A comment; an unclosed ``/*`` runs to the end of the body.
_COMMENT_RE = re.compile(r"/\*.*?(?:\*/|\Z)|//[^\n]*", flags=re.DOTALL)
# Trailing array dimensions: ``x[12]``, ``gap[0xB8 - 0xA0]``.
_DIMS_RE = re.compile(r"(?:\s*\[[^\]]*\])+\s*$")
# A dimension written as a sum or difference of integer literals.
_DIM_SUM_RE = re.compile(r"\s*[-+]?\s*\w+(?:\s*[-+]\s*\w+)*\s*")
# A function pointer ``ret (*name)(params)``.
_FUNC_PTR_RE = re.compile(r"(.*?)\(\s*\*\s*(\w+)\s*\)\s*(\(.*\))")


def _extract_fields(body: str) -> list[HeaderField]:
    """Pull one :class:`HeaderField` per field declaration.

    Walks the body line-by-line using a regex that captures
    both the declaration (everything up to the ``;``) and any
    trailing comment on the same logical line (everything up to
    the next ``\\n`` or ``;``).  This matters because the
    ``+0xHH`` offset annotation typically sits AFTER the ``;``::

        u32 feature_class_id;   /* +0x0C ... */

    The regex runs over the body with every comment blanked, so a
    ``;`` in a comment never ends a declaration (AZ-198); the offset
    and comment text are then read from the same spans of the body.
    An array's dimensions stay on its type (``u8[12]``), each one
    evaluated when it is a sum or difference of integer literals.
    """
    code = _COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), body)
    fields: list[HeaderField] = []
    for m in _FIELD_LINE_RE.finditer(code):
        decl_raw, trailing = body[m.start(1):m.end(1)], body[m.start(2):m.end(2)]
        decl_clean = m.group(1).strip()
        if not decl_clean:
            continue
        # Skip nested struct decls / bit-fields / inline typedefs —
        # our header never uses them, and parsing them is out of
        # scope.
        if "{" in decl_clean or ":" in decl_clean:
            continue
        # A function pointer is a pointer field: ``ret (*name)(params)``
        # reads as ``ret (*)(params) name`` (AZ-233).
        if fp := _FUNC_PTR_RE.fullmatch(decl_clean):
            decl_clean = f"{fp[1]}(*){fp[3]} {fp[2]}"
        dims = ""
        if found := _DIMS_RE.search(decl_clean):
            decl_clean = decl_clean[:found.start()]
            dims = "".join(f"[{_dim(d)}]" for d in
                           re.findall(r"\[([^\]]*)\]", found.group()))
        parts = decl_clean.split()
        if len(parts) < 2:
            continue
        # Collapse leading asterisks on the field-name token back
        # into the type string so ``struct Foo *records`` parses as
        # name=``records`` with c_type=``struct Foo *`` (instead of
        # name=``*records`` with the pointer spelling lost).
        raw_name = parts[-1].rstrip(",")
        leading_stars = ""
        while raw_name.startswith("*"):
            leading_stars += "*"
            raw_name = raw_name[1:]
        name = raw_name
        c_type = " ".join(parts[:-1]).rstrip()
        if leading_stars:
            c_type = f"{c_type} {leading_stars}"
        c_type += dims
        # Look for the offset annotation in EITHER the decl
        # (legacy placement) or the trailing comment (dominant
        # style in structs.h).
        offset_match = (_OFFSET_RE.search(trailing) or
                        _OFFSET_RE.search(decl_raw))
        if offset_match:
            try:
                offset = int(offset_match.group(1), 16)
            except ValueError:
                offset = -1
        else:
            offset = -1
        comment = (_extract_comment_text(trailing)
                   or _extract_comment_text(decl_raw))
        fields.append(HeaderField(
            name=name, c_type=c_type,
            offset=offset, comment=comment))
    return fields


def _dim(text: str) -> str:
    """One array dimension: ``12`` or ``0xB8 - 0xA0`` (24) as a decimal
    count; any other spelling (a macro, ``sizeof``) as written."""
    if _DIM_SUM_RE.fullmatch(text):
        try:
            return str(sum(int(t.replace(" ", ""), 0)
                           for t in re.findall(r"[-+]?\s*\w+", text)))
        except ValueError:
            pass
    return text.strip()


def _extract_comment_text(raw: str) -> str:
    m = re.search(r"/\*(.*?)\*/", raw, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"//\s*(.*)", raw)
    if m:
        return m.group(1).strip()
    return ""


_TYPE_SIZE_HINTS: dict[str, int] = {
    "u8": 1, "s8": 1, "i8": 1, "char": 1, "bool": 1,
    "u16": 2, "s16": 2, "i16": 2, "short": 2,
    "u32": 4, "s32": 4, "i32": 4, "int": 4, "long": 4, "f32": 4, "float": 4,
    "u64": 8, "s64": 8, "i64": 8, "longlong": 8, "ulonglong": 8,
    "double": 8, "f64": 8,
    "void*": 4,  # i386
}


def _type_size_guess(c_type: str) -> int:
    """Best-effort byte size inference for a C type spelling.

    Pointer types are always 4 bytes (XBE is i386); an array
    (``u8[12]``) multiplies its element's size by each dimension
    that is a number (AZ-199); unknown types collapse to 4 (the
    most common size and the least wrong for our headers).
    """
    t, bracket, dims = c_type.strip().replace("const ", "").partition("[")
    count = 1
    for d in re.findall(r"\[(\d+)\]", bracket + dims):
        count *= int(d)
    if "*" in t:
        return 4 * count
    return _TYPE_SIZE_HINTS.get(t.split()[-1], 4) * count


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructDiffEntry:
    """One struct's cross-source status.

    ``status`` is one of:

    - ``"header_only"`` — the header defines this struct but
      Ghidra doesn't.
    - ``"ghidra_only"`` — Ghidra has it but the header doesn't.
    - ``"size_mismatch"`` — both sides have the struct but their
      total size disagrees.
    - ``"field_mismatch"`` — both sides agree on size but at least
      one field differs on offset / type.
    - ``"ok"`` — structure name + size match; fields match.
    """

    name: str
    status: str
    header_size: int | None
    ghidra_size: int | None
    notes: tuple[str, ...] = ()


@dataclass
class StructDiffReport:
    """Aggregate output of :func:`diff_structs`."""

    entries: tuple[StructDiffEntry, ...]

    def to_json_dict(self) -> dict:
        return {
            "summary": self.counts(),
            "entries": [
                {"name": e.name, "status": e.status,
                 "header_size": e.header_size,
                 "ghidra_size": e.ghidra_size,
                 "notes": list(e.notes)}
                for e in self.entries
            ],
        }

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {
            "header_only": 0, "ghidra_only": 0,
            "size_mismatch": 0, "field_mismatch": 0, "ok": 0}
        for e in self.entries:
            out[e.status] = out.get(e.status, 0) + 1
        return out


def diff_structs(*, header: Path | str | list[HeaderStruct],
                 client: GhidraClient | None = None,
                 ghidra_structs: Iterable[GhidraStruct] | None = None,
                 ) -> StructDiffReport:
    """Run the cross-source diff.

    Takes either a live :class:`GhidraClient` (walks the project
    via pagination) or an explicit iterable of pre-fetched
    :class:`GhidraStruct` (useful for tests + for feeding
    snapshot-based comparisons).  At least one must be provided.
    Raises :class:`GhidraClientError` when Ghidra fails the struct
    listing or a lookup of a listed struct, except stock's 404
    ``STRUCT_NOT_FOUND`` for a struct gone since the listing (AZ-232,
    AZ-251).
    """
    if isinstance(header, (str, Path)):
        header_structs = parse_header_structs(Path(header))
    else:
        header_structs = list(header)

    ghidra_lookup: dict[str, GhidraStruct] = {}
    if ghidra_structs is not None:
        for s in ghidra_structs:
            ghidra_lookup[s.name] = s
    elif client is not None:
        listed = [summary["name"] for summary in client.iter_structs()]
        for name in listed:
            try:
                full = client.get_struct(name)
            except GhidraClientError as exc:
                if not exc.means_absent("STRUCT_NOT_FOUND"):
                    raise  # no answer isn't "absent" (AZ-232)
                continue  # gone since the listing
            ghidra_lookup[full.name] = full
    else:
        raise ValueError(
            "diff_structs requires client= or ghidra_structs=")

    entries: list[StructDiffEntry] = []
    header_by_name = {s.name: s for s in header_structs}
    all_names = set(header_by_name) | set(ghidra_lookup)
    for name in sorted(all_names):
        hs = header_by_name.get(name)
        gs = ghidra_lookup.get(name)
        if hs is None:
            entries.append(StructDiffEntry(
                name=name, status="ghidra_only",
                header_size=None,
                ghidra_size=gs.size,
                notes=(f"{len(gs.fields)} field(s) in Ghidra",)))
            continue
        if gs is None:
            entries.append(StructDiffEntry(
                name=name, status="header_only",
                header_size=(hs.declared_size
                             or hs.inferred_size()),
                ghidra_size=None,
                notes=(f"{len(hs.fields)} field(s) in header",)))
            continue
        entries.append(_compare_pair(hs, gs))

    return StructDiffReport(entries=tuple(entries))


def _compare_pair(hs: HeaderStruct,
                  gs: GhidraStruct) -> StructDiffEntry:
    header_size = hs.declared_size or hs.inferred_size()
    if header_size is not None and header_size != gs.size:
        return StructDiffEntry(
            name=hs.name, status="size_mismatch",
            header_size=header_size, ghidra_size=gs.size,
            notes=(f"header={header_size} vs ghidra={gs.size}",))
    g_fields = {f.offset: f for f in gs.fields}
    notes: list[str] = []
    for hf in hs.fields:
        if hf.offset < 0:
            notes.append(
                f"{hf.name}: offset unknown in header")
            continue
        gf = g_fields.get(hf.offset)
        if gf is None:
            notes.append(
                f"{hf.name}@0x{hf.offset:x}: missing in Ghidra")
            continue
        if _normalize_type(hf.c_type) != _normalize_type(gf.data_type):
            notes.append(
                f"{hf.name}@0x{hf.offset:x}: "
                f"header={hf.c_type!r} vs ghidra={gf.data_type!r}")
    status = "ok" if not notes else "field_mismatch"
    return StructDiffEntry(
        name=hs.name, status=status,
        header_size=header_size, ghidra_size=gs.size,
        notes=tuple(notes))


_TYPE_ALIASES = {
    "u8": "uchar", "s8": "char", "i8": "char", "bool": "uchar",
    "u16": "ushort", "s16": "short", "i16": "short",
    "u32": "uint", "s32": "int", "i32": "int", "long": "int",
    "f32": "float",
    "u64": "ulonglong", "s64": "longlong", "i64": "longlong",
    "double": "double", "f64": "double",
}


def _normalize_type(t: str) -> str:
    """Best-effort name normalisation so ``u32`` == ``uint`` etc.

    Pointer-ish types collapse to ``ptr``; an array keeps its
    dimensions (``u8[12]`` == ``uchar[12]``); unknown names pass
    through untouched so the diff shows them verbatim.
    """
    bare = t.strip().replace("const ", "").lower()
    if "*" in bare:
        return "ptr"
    base, bracket, dims = bare.partition("[")
    parts = base.split()
    if not parts:          # Ghidra can emit a field with no dataType.
        return bare
    tok = parts[-1]
    return _TYPE_ALIASES.get(tok, tok) + bracket + dims


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def format_report(report: StructDiffReport, *,
                  verbose: bool = False) -> str:
    """Pretty-print a :class:`StructDiffReport` for the verb."""
    out: list[str] = []
    summary = report.counts()
    out.append(
        "struct-diff summary: "
        f"ok={summary['ok']}  "
        f"header_only={summary['header_only']}  "
        f"ghidra_only={summary['ghidra_only']}  "
        f"size_mismatch={summary['size_mismatch']}  "
        f"field_mismatch={summary['field_mismatch']}")
    for entry in report.entries:
        if not verbose and entry.status == "ok":
            continue
        tag = entry.status.upper()
        sizes = (f"header={entry.header_size}  "
                 f"ghidra={entry.ghidra_size}")
        out.append(f"  [{tag:15}] {entry.name:32}  {sizes}")
        if verbose:
            for note in entry.notes:
                out.append(f"      - {note}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    """Exit 0 with the report; 1 when Ghidra fails the struct listing or a
    lookup of a listed struct (AZ-232, AZ-251) or the header is missing; 2
    when nothing answers on the port."""
    p = argparse.ArgumentParser(
        prog="python -m devkit re struct-diff",
        description="The structs of devkit/re/data/structs.h against Ghidra's: header_only (the header declares "
                    "it, Ghidra doesn't), ghidra_only (Ghidra has it, the header doesn't), size_mismatch and "
                    "field_mismatch (on both sides, one of them stale). --offline reads the header alone; "
                    "--verbose prints each field's difference.")
    p.add_argument("--header", default=None, help=f"the header to read (default {HEADER.parent.name}/{HEADER.name})")
    p.add_argument("--offline", action="store_true", help="skip Ghidra: the header parser alone")
    p.add_argument("--verbose", "-v", action="store_true", help="show each field's difference on a mismatch")
    p.add_argument("--port", type=int, default=None, help="Ghidra's port (default 8193)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    header = Path(args.header) if args.header else HEADER
    try:
        if not header.exists():
            raise Refused(f"header not found: {header}", code=1)
        client = None if args.offline else connect(args.port)
        try:
            report = diff_structs(header=header, client=client, ghidra_structs=() if args.offline else None)
        except GhidraClientError as exc:   # a failed listing or lookup (AZ-232, AZ-251)
            raise Refused(str(exc), code=1) from None
    except Refused as exc:
        print(f"struct-diff: {exc}", file=sys.stderr)
        return exc.code
    emit(report.to_json_dict() if args.json else format_report(report, verbose=args.verbose), args.json)
    return 0
