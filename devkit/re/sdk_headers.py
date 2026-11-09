"""``python -m devkit re sdk-headers``: the Xbox SDK's headers as Ghidra's ``ImportHeader`` reads them (Modkit's
``vendor/xbox-includes`` with its ``_patch_xboxkrnl_ghidra.py``, Step 4.24c).

The headers (mborgerson/xbox-includes, GPL-2) are never in this repository: ``uv run bootstrap.py --with re``
fetches them, pinned by sha256 in ``devkit/re/tools.toml``, into ``.tools/xbox-includes/`` (the ``.tools``
:func:`~devkit.re.ghidra_serve.tools_dir` names: a lane's own, else the main checkout's). This verb writes their
Ghidra copy beside them, ``.tools/xbox-includes/ghidra/``, again each run: every header as fetched but
``xboxdef.h``, which is :data:`XBOXDEF` (the SDK's base types under ``XBX_`` names in standard C, so they don't meet
Ghidra's own ``ULONG``, ``HANDLE``...), with :data:`BRIDGE` (``xboxkrnl_ghidra_bridge.h``, the SDK's names defined
as those) beside it, and ``xboxkrnl.h`` as :func:`patch_text` rewrites it for Ghidra's C parser. It prints the
``ImportHeader`` arguments (the skill's "Header import"). Exit 0 written, 2 the headers aren't fetched.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from devkit.re.ghidra_serve import tools_dir

XBOXDEF = (
    '#ifndef __XBOXDEF_H__\n'
    '#define __XBOXDEF_H__\n'
    '\n'
    '// Ghidra Parse C Source ONLY: standard C keywords only (no ulong or uchar).\n'
    '// Names use XBX_ prefix so we do not collide with built-in LPCVOID, PVOID, HANDLE, ULONG, etc.\n'
    '// Map XBX_* to SDK names in Data Type Manager when applying to the XBE.\n'
    '\n'
    'typedef unsigned int XBX_PVOID;\n'
    'typedef unsigned int XBX_LPVOID;\n'
    'typedef unsigned int XBX_LPCVOID;\n'
    'typedef unsigned int XBX_HANDLE;\n'
    'typedef unsigned int XBX_PHANDLE;\n'
    '\n'
    'typedef unsigned char XBX_BOOLEAN;\n'
    'typedef unsigned int XBX_PBOOLEAN;\n'
    '\n'
    'typedef signed char XBX_SCHAR;\n'
    'typedef unsigned int XBX_PSCHAR;\n'
    '\n'
    'typedef char XBX_CHAR;\n'
    'typedef unsigned int XBX_PCHAR;\n'
    'typedef char XBX_CCHAR;\n'
    'typedef unsigned int XBX_LPCH;\n'
    'typedef unsigned int XBX_PCH;\n'
    'typedef char XBX_OCHAR;\n'
    'typedef unsigned int XBX_POCHAR;\n'
    'typedef short XBX_SHORT;\n'
    'typedef unsigned int XBX_PSHORT;\n'
    'typedef short XBX_CSHORT;\n'
    'typedef int XBX_INT;\n'
    'typedef unsigned int XBX_PINT;\n'
    'typedef unsigned int XBX_LPINT;\n'
    'typedef long XBX_LONG;\n'
    'typedef unsigned int XBX_PLONG;\n'
    'typedef unsigned int XBX_LPLONG;\n'
    'typedef long long XBX_LONGLONG;\n'
    'typedef unsigned int XBX_PLONGLONG;\n'
    '\n'
    'typedef unsigned char XBX_UCHAR;\n'
    'typedef unsigned int XBX_PUCHAR;\n'
    'typedef unsigned short XBX_USHORT;\n'
    'typedef unsigned int XBX_PUSHORT;\n'
    'typedef unsigned short XBX_WORD;\n'
    'typedef unsigned short XBX_WCHAR;\n'
    'typedef unsigned int XBX_PWSTR;\n'
    'typedef unsigned int XBX_UINT;\n'
    'typedef unsigned int XBX_PUINT;\n'
    'typedef unsigned int XBX_LPUINT;\n'
    'typedef unsigned int XBX_DWORD;\n'
    'typedef unsigned int XBX_PDWORD;\n'
    'typedef unsigned int XBX_LPDWORD;\n'
    'typedef unsigned int XBX_ULONG;\n'
    'typedef unsigned int XBX_PULONG;\n'
    'typedef unsigned long long XBX_ULONGLONG;\n'
    '\n'
    '#define XBX_MAXDWORD 0xFFFFFFFFU\n'
    '\n'
    'typedef long XBX_LONG_PTR;\n'
    'typedef unsigned int XBX_ULONG_PTR;\n'
    'typedef unsigned int XBX_DWORD_PTR;\n'
    'typedef unsigned int XBX_SIZE_T;\n'
    'typedef unsigned int XBX_PSIZE_T;\n'
    '\n'
    'typedef int XBX_BOOL;\n'
    'typedef unsigned int XBX_PBOOL;\n'
    'typedef unsigned int XBX_PCSZ;\n'
    'typedef unsigned int XBX_PCSTR;\n'
    'typedef unsigned int XBX_LPCSTR;\n'
    'typedef unsigned int XBX_LPWSTR;\n'
    '\n'
    'typedef struct XBX_STRING {\n'
    '    XBX_USHORT Length;\n'
    '    XBX_USHORT MaximumLength;\n'
    '    XBX_PVOID Buffer;\n'
    '} XBX_STRING;\n'
    'typedef unsigned int XBX_PSTRING;\n'
    '\n'
    'typedef struct XBX_STRING XBX_ANSI_STRING;\n'
    'typedef unsigned int XBX_PANSI_STRING;\n'
    '\n'
    'typedef union XBX_LARGE_INTEGER {\n'
    '    struct {\n'
    '        XBX_ULONG LowPart;\n'
    '        XBX_LONG HighPart;\n'
    '    } u;\n'
    '    XBX_LONGLONG QuadPart;\n'
    '} XBX_LARGE_INTEGER;\n'
    'typedef unsigned int XBX_PLARGE_INTEGER;\n'
    '\n'
    'typedef union XBX_ULARGE_INTEGER {\n'
    '    struct {\n'
    '        XBX_ULONG LowPart;\n'
    '        XBX_ULONG HighPart;\n'
    '    } u;\n'
    '    XBX_ULONGLONG QuadPart;\n'
    '} XBX_ULARGE_INTEGER;\n'
    'typedef unsigned int XBX_PULARGE_INTEGER;\n'
    '\n'
    'typedef struct XBX_LIST_ENTRY {\n'
    '    XBX_PVOID Flink;\n'
    '    XBX_PVOID Blink;\n'
    '} XBX_LIST_ENTRY;\n'
    'typedef unsigned int XBX_PLIST_ENTRY;\n'
    '\n'
    'typedef struct XBX_RTL_CRITICAL_SECTION {\n'
    '    union {\n'
    '        struct {\n'
    '            XBX_UCHAR Type;\n'
    '            XBX_UCHAR Absolute;\n'
    '            XBX_UCHAR Size;\n'
    '            XBX_UCHAR Inserted;\n'
    '            XBX_LONG SignalState;\n'
    '            XBX_LIST_ENTRY WaitListHead;\n'
    '        } Event;\n'
    '        XBX_ULONG RawEvent[4];\n'
    '    } Synchronization;\n'
    '    XBX_LONG LockCount;\n'
    '    XBX_LONG RecursionCount;\n'
    '    XBX_PVOID OwningThread;\n'
    '} XBX_RTL_CRITICAL_SECTION;\n'
    'typedef unsigned int XBX_PRTL_CRITICAL_SECTION;\n'
    '\n'
    '#endif\n'
)
"""``xboxdef.h`` for Ghidra: the SDK's base types as ``XBX_`` types of standard C (Modkit's)."""

BRIDGE = (
    '/* Auto-used when parsing xboxkrnl for Ghidra: maps SDK names to XBX_* from xboxdef.h.\n'
    ' * Do not include in real Xbox builds. */\n'
    '\n'
    '#ifndef XBOXKRNL_GHIDRA_BRIDGE_H\n'
    '#define XBOXKRNL_GHIDRA_BRIDGE_H\n'
    '\n'
    '#define __stdcall\n'
    '#define __cdecl\n'
    '#define __fastcall\n'
    '\n'
    '#define CHAR           XBX_CHAR\n'
    '#define SHORT          XBX_SHORT\n'
    '#define LONG           XBX_LONG\n'
    '#define SCHAR          XBX_SCHAR\n'
    '#define OCHAR          XBX_OCHAR\n'
    '#define CCHAR          XBX_CCHAR\n'
    '#define UCHAR          XBX_UCHAR\n'
    '#define USHORT         XBX_USHORT\n'
    '#define ULONG          XBX_ULONG\n'
    '#define WCHAR          XBX_WCHAR\n'
    '\n'
    '#define PSCHAR         XBX_PSCHAR\n'
    '#define POCHAR         XBX_POCHAR\n'
    '#define PUCHAR         XBX_PUCHAR\n'
    '#define PUSHORT        XBX_PUSHORT\n'
    '#define PSHORT         XBX_PSHORT\n'
    '#define PINT           XBX_PINT\n'
    '#define LPINT          XBX_LPINT\n'
    '#define PLONG          XBX_PLONG\n'
    '#define LPLONG         XBX_LPLONG\n'
    '#define PLONGLONG      XBX_PLONGLONG\n'
    '#define PBOOLEAN       XBX_PBOOLEAN\n'
    '#define PDWORD         XBX_PDWORD\n'
    '#define LPDWORD        XBX_LPDWORD\n'
    '#define PULONG         XBX_PULONG\n'
    '#define PUINT          XBX_PUINT\n'
    '#define LPUINT         XBX_LPUINT\n'
    '#define PBOOL          XBX_PBOOL\n'
    '#define PVOID          XBX_PVOID\n'
    '#define HANDLE         XBX_HANDLE\n'
    '#define PHANDLE        XBX_PHANDLE\n'
    '#define LPVOID         XBX_LPVOID\n'
    '#define LPCVOID        XBX_LPCVOID\n'
    '#define BOOLEAN        XBX_BOOLEAN\n'
    '#define STRING         XBX_STRING\n'
    '#define ANSI_STRING    XBX_ANSI_STRING\n'
    '#define LIST_ENTRY     XBX_LIST_ENTRY\n'
    '#define LARGE_INTEGER  XBX_LARGE_INTEGER\n'
    '#define ULARGE_INTEGER XBX_ULARGE_INTEGER\n'
    '#define DWORD          XBX_DWORD\n'
    '#define BOOL           XBX_BOOL\n'
    '#define INT            XBX_INT\n'
    '#define UINT           XBX_UINT\n'
    '#define PCHAR          XBX_PCHAR\n'
    '#define PLIST_ENTRY    XBX_PLIST_ENTRY\n'
    '#define PSTRING        XBX_PSTRING\n'
    '#define PANSI_STRING   XBX_PANSI_STRING\n'
    '#define PLARGE_INTEGER XBX_PLARGE_INTEGER\n'
    '#define PULARGE_INTEGER XBX_PULARGE_INTEGER\n'
    '#define RTL_CRITICAL_SECTION XBX_RTL_CRITICAL_SECTION\n'
    '#define PRTL_CRITICAL_SECTION XBX_PRTL_CRITICAL_SECTION\n'
    '#define LONGLONG       XBX_LONGLONG\n'
    '#define ULONGLONG      XBX_ULONGLONG\n'
    '#define CSHORT         XBX_CSHORT\n'
    '#define WORD           XBX_WORD\n'
    '#define DWORD_PTR      XBX_DWORD_PTR\n'
    '#define SIZE_T         XBX_SIZE_T\n'
    '#define LONG_PTR       XBX_LONG_PTR\n'
    '#define ULONG_PTR      XBX_ULONG_PTR\n'
    '#define PSIZE_T        XBX_PSIZE_T\n'
    '#define LPCH           XBX_LPCH\n'
    '#define PCH            XBX_PCH\n'
    '#define LPWSTR         XBX_LPWSTR\n'
    '#define PWSTR          XBX_PWSTR\n'
    '\n'
    '#endif\n'
)
"""``xboxkrnl_ghidra_bridge.h``: each SDK name ``xboxkrnl.h`` uses, defined as its ``XBX_`` type (Modkit's)."""


def patch_text(text: str) -> str:
    """``xboxkrnl.h`` (the SDK's, as fetched) as Ghidra's C parser reads it with :data:`XBOXDEF` and
    :data:`BRIDGE`: the bridge included after ``xboxdef.h``, no ``#pragma``, no ``extern "C"`` block, each
    typedef of a type and its pointer (``} T, *PT;``) split in two, the string and ``UNICODE_STRING`` pointers
    as the bridge's, and no ``noreturn`` attribute (Modkit's ``_patch_xboxkrnl_ghidra.py``)."""
    if "GHIDRA_PARSED_PATCH" not in text:
        text = (
            "/* GHIDRA_PARSED_PATCH: for Ghidra Parse C Source only (with xboxdef XBX_*).\n"
            " * The fetched original is ../include/xboxkrnl.h: use it for real builds.\n"
            " */\n\n"
        ) + text

    if '#include "xboxkrnl_ghidra_bridge.h"' not in text:
        text = text.replace(
            '#include "xboxdef.h"',
            '#include "xboxdef.h"\n#include "xboxkrnl_ghidra_bridge.h"',
            1,
        )

    text = re.sub(r"(?m)^\s*#pragma\b.*\n", "", text)

    text = text.replace(
        "#if defined(__cplusplus)\nextern \"C\"\n{\n#endif\n",
        "/* Ghidra: extern C omitted */\n",
    )
    text = text.replace(
        "#if defined(__cplusplus)\n}\n#endif\n",
        "/* Ghidra: end extern C omitted */\n",
    )

    repls = [
        (
            "typedef ULONG PHYSICAL_ADDRESS, *PPHYSICAL_ADDRESS;",
            "typedef ULONG PHYSICAL_ADDRESS;\ntypedef ULONG *PPHYSICAL_ADDRESS;",
        ),
        (
            "typedef UCHAR KIRQL, *PKIRQL;",
            "typedef UCHAR KIRQL;\ntypedef UCHAR *PKIRQL;",
        ),
        (
            "typedef ULONG PFN_NUMBER, *PPFN_NUMBER;",
            "typedef ULONG PFN_NUMBER;\ntypedef ULONG *PPFN_NUMBER;",
        ),
        (
            "typedef const char *PCSZ, *PCSTR, *LPCSTR;",
            "typedef XBX_PCSZ PCSZ;\ntypedef XBX_PCSTR PCSTR;\ntypedef XBX_LPCSTR LPCSTR;",
        ),
        (
            "typedef char *PSZ, *PSTR;",
            "typedef XBX_PCHAR PSZ;\ntypedef XBX_PCHAR PSTR;",
        ),
        (
            "typedef CONST WCHAR *LPCWSTR, *PCWSTR;",
            "typedef XBX_LPWSTR LPCWSTR;\ntypedef XBX_PWSTR PCWSTR;",
        ),
        (
            "typedef ULONG ACCESS_MASK, *PACCESS_MASK;",
            "typedef ULONG ACCESS_MASK;\ntypedef ULONG *PACCESS_MASK;",
        ),
        (
            "typedef STRING OBJECT_STRING, *POBJECT_STRING;",
            "typedef XBX_STRING OBJECT_STRING;\ntypedef XBX_PVOID POBJECT_STRING;",
        ),
    ]
    for a, b in repls:
        text = text.replace(a, b)

    def split_typedef_line(m: re.Match[str]) -> str:
        ind, name, pname = m.group(1), m.group(2), m.group(3)
        return ind + "} " + name + ";\n" + ind + "typedef " + name + " *" + pname + ";"

    text = re.sub(
        r"^(\s*)\}\s*(\w+)\s*,\s*\*(\w+)\s*;\s*$",
        split_typedef_line,
        text,
        flags=re.MULTILINE,
    )

    pat3 = re.compile(
        r"^\}\s*(\w+)\s*,\s*\*(\w+)\s*,\s*\*RESTRICTED_POINTER\s+(\w+)\s*;\s*$",
        re.MULTILINE,
    )

    def split_rest(m: re.Match[str]) -> str:
        a, b, c = m.group(1), m.group(2), m.group(3)
        return f"}} {a};\ntypedef {a} *{b};\ntypedef {a} *{c};"

    text = pat3.sub(split_rest, text)

    oldf = "} __attribute__((packed)) FLOATING_SAVE_AREA, *PFLOATING_SAVE_AREA;"
    newf = "} FLOATING_SAVE_AREA;\ntypedef FLOATING_SAVE_AREA *PFLOATING_SAVE_AREA;"
    text = text.replace(oldf, newf)

    text = text.replace(
        "typedef UNICODE_STRING *PUNICODE_STRING;",
        "typedef XBX_PVOID PUNICODE_STRING;",
    )
    text = text.replace(
        "typedef CONST UNICODE_STRING *PCUNICODE_STRING;",
        "typedef XBX_PVOID PCUNICODE_STRING;",
    )

    text = text.replace(
        "XBAPI VOID NTAPI __attribute__ ((noreturn)) PsTerminateSystemThread",
        "XBAPI VOID NTAPI PsTerminateSystemThread",
    )

    return text


def write(include: Path, out: Path) -> Path:
    """The Ghidra copy of the fetched headers in ``include``, written to ``out`` afresh."""
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    for p in sorted(include.glob("*.h")):
        shutil.copyfile(p, out / p.name)
    (out / "xboxdef.h").write_text(XBOXDEF, encoding="utf-8")
    (out / "xboxkrnl_ghidra_bridge.h").write_text(BRIDGE, encoding="utf-8")
    text = (include / "xboxkrnl.h").read_text(encoding="utf-8", errors="replace")
    (out / "xboxkrnl.h").write_text(patch_text(text), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit re sdk-headers", description=__doc__.split("\n\n")[0])
    ap.parse_args(argv)
    include = tools_dir() / "xbox-includes" / "include"
    if not (include / "xboxkrnl.h").is_file():
        print(f"sdk-headers: no Xbox SDK headers in {include.parent}: run `uv run bootstrap.py --with re`",
              file=sys.stderr)
        return 2
    out = write(include, include.parent / "ghidra")
    print(f'ImportHeader args: ["/Cat", "{(out / "xboxkrnl.h").as_posix()}", "-I{out.as_posix()}"]')
    return 0
