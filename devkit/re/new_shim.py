"""``python -m devkit re new-shim NAME``: scaffold a new shim pack (Modkit's
``azurik-mod new-shim``, rewritten in Step 4.11e for AzurKit's one-file
pack).

It writes the two files a trampoline pack is:

- ``src/azurkit/tools/mods/packs/<name>.py``: its ``PACK``, one
  ``TrampolinePatch`` at the hook site (a USA address) calling the shim's
  entry by its mangled name, USA only until Europe's map has the site;
- ``src/azurkit/tools/mods/shims/<name>.c``: the shim's entry with the
  calling convention and parameters the hook needs, including shimkit's
  ``azurik_vanilla.h``;

and prints the rest, which is edited by hand: the registry
(``tools/mods/__init__.py``), the facts site (its address and size; then
``scripts/gen_facts.py`` fills in its sha256: AzurKit's packs name no bytes,
so Modkit's ``replaced_bytes`` has no place), the object (``shimkit``), the
goldens' cases and Europe's address.

With ``--hook VA`` it reads the USA XBE (``--iso``/``--xbe``, else the USA
image) and runs :func:`devkit.re.plan_trampoline.plan_trampoline` to size the
site and warn when the hook isn't a clean instruction boundary. The entry's
ABI comes, best first, from a live Ghidra (``--ghidra``/``--port``: the
function's signature and its parameters' storage), else from the facts when
the hook replaces a direct call to a game function they know (the shim
stands in for it: its convention, argument bytes and, where ``shimkit``
types it, its C types), else a ``stdcall`` ``void(void)`` guess. Nothing is
overwritten: an existing pack, shim or file refuses the name.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import string
import struct
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKS = Path("src/azurkit/tools/mods/packs")
SHIMS = Path("src/azurkit/tools/mods/shims")
DEFAULT_SIZE = 5   # a CALL rel32's: the site's size when no XBE sizes it

__all__ = [
    "ABIGuess",
    "ScaffoldPlan",
    "abi_from_facts",
    "generate_pack_py",
    "generate_shim_c",
    "guess_abi_from_signature",
    "plan_scaffold",
    "write_scaffold",
]


# ---------------------------------------------------------------------------
# Calling-convention detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ABIGuess:
    """Inferred calling convention + parameters for a hook site.

    Attributes
    ----------
    attribute: str
        clang attribute to emit (``"stdcall"`` / ``"cdecl"`` /
        ``"fastcall"`` / ``"thiscall"``).  Plain ``"stdcall"`` is
        the safe default when the signature is unavailable.
    return_type: str
        C return type.  ``"void"`` if Ghidra reports
        ``undefined``.
    parameters: tuple[tuple[str, str], ...]
        ``(type, name)`` pairs in declaration order.  Empty tuple
        for argless functions.
    stdcall_n: int
        The ``@N`` suffix clang gives the C entry: every parameter's
        bytes, each rounded up to 4 (fastcall's ``ECX``/``EDX`` ones
        too).  Only meaningful for stdcall / fastcall; 0 otherwise.
    confidence: str
        ``"high"`` when sourced from Ghidra, ``"facts"`` from the
        facts' function the hook replaces a call to, ``"low"`` when
        guessed from defaults.
    raw_signature: str
        Original Ghidra signature string (or the facts' function's
        name), preserved for docs.
    notes: tuple[str, ...]
        Any heuristics-level caveats the scaffolder wants to
        surface to the author.
    """

    attribute: str = "stdcall"
    return_type: str = "void"
    parameters: tuple[tuple[str, str], ...] = ()
    stdcall_n: int = 0
    confidence: str = "low"
    raw_signature: str = ""
    notes: tuple[str, ...] = ()

    def symbol(self, name: str) -> str:
        """The entry ``c_<name>``'s symbol, as clang mangles C for i386
        Windows (the facts' rule): ``_c_x@N`` stdcall, ``@c_x@N`` fastcall,
        ``_c_x`` otherwise."""
        from azurkit.core.facts import Function

        return Function(f"c_{name}", 0, self.attribute, self.stdcall_n).mangled


_TYPE_SIZE = {
    "char": 1, "unsigned char": 1, "byte": 1, "signed char": 1,
    "short": 2, "unsigned short": 2, "word": 2,
    "int": 4, "unsigned int": 4, "dword": 4,
    "long": 4, "unsigned long": 4,
    "float": 4,
    "double": 8,
    "longlong": 8, "long long": 8, "unsigned long long": 8,
    "int64": 8, "uint64": 8,
}


def _translate_ghidra_type(raw: str) -> str:
    """Turn a Ghidra type string into a shim-friendly C type.

    Ghidra uses ``undefined`` / ``undefined4`` placeholders: we
    normalise them to ``void`` / ``unsigned int`` respectively
    since shim code can't reference ``undefined``.
    """
    t = raw.strip()
    if not t or t == "undefined":
        return "void"
    # undefined1..8 -> fixed-width ints
    m = re.match(r"undefined(\d+)\s*(\*?)", t)
    if m:
        width, star = int(m.group(1)), m.group(2)
        base = {
            1: "unsigned char", 2: "unsigned short",
            4: "unsigned int", 8: "unsigned long long",
        }.get(width, "unsigned int")
        return f"{base} {star}".rstrip() if star else base
    # trailing `*` stays
    return t


def _param_byte_size(type_str: str) -> int:
    """Best-effort sizeof estimate (for ``@N`` calculation)."""
    t = type_str.strip().lower()
    if t.endswith("*"):
        return 4
    return _TYPE_SIZE.get(t, 4)  # default to pointer-sized


def guess_abi_from_signature(signature: str,
                             parameters: Iterable[dict] | None = None,
                             ) -> ABIGuess:
    """Infer an :class:`ABIGuess` from Ghidra's signature string
    + the structured ``parameters`` list it returns alongside.

    ``parameters`` is the list of ``{"name", "dataType", "storage"}``
    dicts the Ghidra client gives; ``storage`` is Ghidra's
    ``ECX:4`` / ``Stack[0x4]:4`` (a bare ``ECX`` / ``stack`` reads the
    same).  When ``None`` we fall back to parsing the signature
    string alone.

    Heuristics:

    * Any register-stored param beyond ECX -> likely ``__fastcall``
      (ECX + EDX in order).
    * Single ECX-stored param, rest on stack -> likely ``__thiscall``.
    * All params on stack -> default to ``__stdcall``.  We can't
      distinguish stdcall from cdecl at the signature level
      alone; downstream tools (plan-trampoline, ``xbe dis``) can
      verify via the ``RET N`` / ``RET`` instruction.
    """
    notes: list[str] = []
    raw = signature or ""

    # Parse return type first so we can report it even when the
    # caller didn't give us parameter storage info.  Pattern:
    # ``<return> <name>(``.
    return_type = "void"
    m = re.match(r"^\s*([^\(]+?)\s+\w+\s*\(", raw)
    if m:
        return_type = _translate_ghidra_type(m.group(1))
        if return_type == "undefined":
            return_type = "void"

    if not parameters:
        notes.append(
            "No parameter metadata available; defaulting to "
            "__stdcall(void).")
        return ABIGuess(raw_signature=raw,
                        return_type=return_type,
                        notes=tuple(notes))

    params = list(parameters)
    # "ECX:4" -> "ECX", "Stack[0x4]:4" -> "STACK"
    storages = [(p.get("storage") or "").upper().split(":")[0].split("[")[0]
                for p in params]

    # Fast-path ABI rules
    reg_storages = [s for s in storages if s not in ("STACK", "")]
    attribute = "stdcall"
    if reg_storages == ["ECX"]:
        attribute = "thiscall"
    elif reg_storages and reg_storages[:2] == ["ECX", "EDX"]:
        attribute = "fastcall"
    elif reg_storages and reg_storages != ["ECX"]:
        # Mixed / unusual register storage: shim author must
        # verify by hand.
        notes.append(
            f"Unusual register storage: {reg_storages}.  Review "
            "the ABI in Ghidra before trusting the scaffolded "
            "attribute.")

    # Parse params into (type, name)
    translated: list[tuple[str, str]] = []
    for p in params:
        c_type = _translate_ghidra_type(p.get("dataType", ""))
        name = p.get("name") or f"arg{len(translated)}"
        translated.append((c_type, name))
    # clang's @N for the C entry: every parameter, each rounded up to 4
    # bytes, ECX's and EDX's included for fastcall (the facts' rule).
    arg_bytes = sum((_param_byte_size(t) + 3) // 4 * 4 for t, _ in translated)

    return ABIGuess(
        attribute=attribute,
        return_type=return_type,
        parameters=tuple(translated),
        stdcall_n=arg_bytes if attribute in ("stdcall",
                                             "fastcall") else 0,
        confidence="high",
        raw_signature=raw,
        notes=tuple(notes),
    )


def _c_params(text: str) -> tuple[tuple[str, str], ...]:
    """``"void *pc, float t"`` as ``(("void *", "pc"), ("float", "t"))``."""
    if text.strip() in ("", "void"):
        return ()
    out = []
    for part in text.split(","):
        m = re.match(r"^\s*(.*?[\s*])(\w+)\s*$", part)
        out.append((m.group(1).strip(), m.group(2)) if m else (part.strip(), f"arg{len(out)}"))
    return tuple(out)


def abi_from_facts(xbe: bytes, hook_va: int) -> ABIGuess | None:
    """The ABI of the game function the instruction at ``hook_va`` calls
    directly (``E8 rel32``), when the USA facts know it: the shim the hook
    calls instead receives its arguments, so it takes its convention and
    argument bytes, and the C types ``shimkit.TYPES`` gives it (else 32-bit
    words, as ``azurik_vanilla.h`` declares it); ``None`` otherwise."""
    import shimkit
    from azurkit.core import facts, gate
    from azurkit.core.xbe import resolve_va_to_file

    at = resolve_va_to_file(xbe, hook_va)
    if at is None or at + 5 > len(xbe) or xbe[at] != 0xE8:
        return None
    target = (hook_va + 5 + struct.unpack_from("<i", xbe, at + 1)[0]) & 0xFFFFFFFF
    fn = next((f for f in facts.of(gate.USA).functions.values() if f.va == target), None)
    if fn is None:
        return None
    words = (fn.convention == "thiscall") + fn.arg_bytes // 4
    result, params = shimkit.TYPES.get(fn.name, ("unsigned int", ", ".join(["unsigned int"] * words) or "void"))
    typed = fn.name in shimkit.TYPES
    parameters = _c_params(params) if typed else tuple(("unsigned int", f"arg{i}") for i in range(words))
    return ABIGuess(
        attribute=fn.convention, return_type=result, parameters=parameters,
        stdcall_n=fn.arg_bytes if fn.convention in ("stdcall", "fastcall") else 0,
        confidence="facts", raw_signature=fn.name,
        notes=(f"The hook replaces a call to {fn.name} (0x{fn.va:X}, {fn.convention}, {fn.arg_bytes} argument "
               f"bytes{', typed by shimkit' if typed else '; 32-bit words: shimkit types it no further'}): the shim "
               f"takes its arguments and returns what it would.",))


# ---------------------------------------------------------------------------
# Scaffold plan
# ---------------------------------------------------------------------------


@dataclass
class ScaffoldPlan:
    """Everything the scaffolder will write (dry-run-friendly)."""

    name: str
    pack_path: Path
    pack_body: str
    shim_c_path: Path
    shim_c_body: str
    abi: ABIGuess
    hook_va: int | None
    site_size: int
    site_sha256: str | None   # the vanilla site's, as gen_facts records it; None: no XBE read
    preserved: list[str] = field(default_factory=list)
    planner_warnings: list[str] = field(default_factory=list)

    @property
    def files(self) -> list[Path]:
        return [self.pack_path, self.shim_c_path]

    def summary(self) -> str:
        lines = [
            f"Scaffold plan for pack {self.name!r}",
            f"  pack:          {self.pack_path}",
            f"  shim:          {self.shim_c_path}",
            "  hook VA:       "
            + (f"0x{self.hook_va:08X} (USA)" if self.hook_va is not None
               else "(unset)"),
            f"  site:          {self.site_size} B"
            + (f" (vanilla sha256 {self.site_sha256[:12]}; it replaces "
               f"{', '.join(self.preserved) or 'nothing decoded'})" if self.site_sha256 else ""),
            f"  ABI attribute: __attribute__(({self.abi.attribute}))  "
            f"[confidence: {self.abi.confidence}]",
            f"  entry symbol:  {self.abi.symbol(self.name)}",
            f"  return type:   {self.abi.return_type}",
            "  params:        "
            + (", ".join(f"{t} {n}" for t, n in self.abi.parameters)
               if self.abi.parameters else "(none)"),
        ]
        if self.abi.notes:
            lines.append("  ABI notes:")
            for n in self.abi.notes:
                lines.append(f"    - {n}")
        if self.planner_warnings:
            lines.append("  trampoline planner warnings:")
            for w in self.planner_warnings:
                lines.append(f"    ! {w}")
        return "\n".join(lines)

    def next_steps(self) -> list[str]:
        va = f"0x{self.hook_va:08X}" if self.hook_va is not None else "0x<VA>"
        return [
            f"Edit {self.shim_c_path}: the shim's logic.",
            f"Edit {self.pack_path}: its description, the hook's label and its docstring.",
            f"Register it: import it in src/azurkit/tools/mods/__init__.py and put {self.name}.PACK in PACKS "
            f"at its place in the order builds apply them.",
            f'Its facts site: add "{va}": {{"size": {self.site_size}}} to src/azurkit/core/facts.usa.json\'s '
            f"sites, then `uv run --locked python scripts/gen_facts.py` fills in its sha256.",
            f"Build its object: `uv run --locked python -m shimkit`, then "
            f"`uv run --locked python -m devkit re shim-inspect {self.name}`.",
            f"Its goldens: add its cases to tests/goldens/cases.json (packs.json, sites.json), then "
            f"`uv run --locked python scripts/record_goldens.py packs.json sites.json shims.json`.",
            f"Europe: `uv run --locked python -m devkit re region-map find {va} {self.site_size}` gives its "
            f"address for facts.europe.json's addresses (and its site there); then add \"europe\" to its "
            f"releases and run `region-map check`.",
        ]


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


_PACK_PY_TEMPLATE = string.Template('''\
"""$name: TODO: what the pack does, in a player's words, and how.

Its hook is at $hook_va_display$hook_site_note: a CALL into its shim
(``shims/$name.c``), $abi_line. Scaffolded by
``python -m devkit re new-shim``; ``python -m devkit re plan-trampoline
$hook_va_display`` re-checks the site's boundary.
"""

from __future__ import annotations

from azurkit.tools.mods.engine import Pack, TrampolinePatch

PACK = Pack(
    name="$name",
    description="TODO: one line a player reads on the Patches tab.",
    sites=(TrampolinePatch(label="$label", va=$hook_va_literal, shim="$name", symbol="$symbol"),),
    category="$category",
    # USA only until each address it names has a Europe entry in facts.europe.json
    # (`python -m devkit re region-map find VA`); then list "europe" too.
    releases=("usa",),
)
''')


_SHIM_C_TEMPLATE = string.Template("""\
/* $name's shim: the hook at VA 0x$hook_va_hex$hook_site_note calls this.
 *
 * Calling convention: $attribute  [$confidence confidence]
$abi_notes_block *
 * It includes shimkit's headers, written from the facts:
 *   azurik_vanilla.h  the game's functions, typed where shimkit types them,
 *                     and the parameter macros;
 *   azurik_kernel.h   the kernel exports.
 * shimkit builds it into $name.o beside it. Scaffolded by
 * `python -m devkit re new-shim`.
 */

#include "azurik_vanilla.h"


/* The entry: its symbol is $symbol (the leading underscore and
 * any @N are clang's i386-windows mangling: the pack's symbol). */
__attribute__(($attribute))
$return_type c_${name}($params)
{
    /* TODO: the shim's logic.  Until then it does nothing$return_note. */$return_stmt
}
""")


def _abi_line(abi: ABIGuess) -> str:
    params = ", ".join(f"{t} {n}" for t, n in abi.parameters) or "void"
    return f"``{abi.attribute}`` ``{abi.return_type} ({params})`` [{abi.confidence} confidence]"


def generate_pack_py(name: str, *,
                     hook_va: int | None,
                     abi: ABIGuess,
                     category: str = "qol",
                     label: str | None = None,
                     ) -> str:
    """Render the pack module's body."""
    return _PACK_PY_TEMPLATE.safe_substitute(
        name=name,
        hook_va_display=f"0x{hook_va:08X}" if hook_va is not None else "0x????????",
        hook_site_note="" if hook_va is not None else " (!!! fill in the USA address)",
        hook_va_literal=f"0x{hook_va:08X}" if hook_va is not None else "0x00000000",
        abi_line=_abi_line(abi),
        label=label or f"TODO: what the hook replaces in {name}",
        symbol=abi.symbol(name),
        category=category,
    )


def generate_shim_c(name: str, *,
                    hook_va: int | None,
                    abi: ABIGuess) -> str:
    """Render the ``shims/<name>.c`` body."""
    params_str = (", ".join(f"{t} {n}" for t, n in abi.parameters)
                  if abi.parameters else "void")
    returns = abi.return_type != "void"
    return _SHIM_C_TEMPLATE.safe_substitute(
        name=name,
        hook_va_hex=f"{hook_va:08X}" if hook_va is not None else "????????",
        hook_site_note="" if hook_va is not None else "  (!!! fill in before shipping)",
        attribute=abi.attribute,
        confidence=abi.confidence,
        abi_notes_block="".join(f" * Note: {note}\n" for note in abi.notes),
        symbol=abi.symbol(name),
        return_type=abi.return_type,
        params=params_str,
        return_note=" and returns 0" if returns else "",
        return_stmt=f"\n    return ({abi.return_type})0;" if returns else "",
    )


# ---------------------------------------------------------------------------
# High-level entry points
# ---------------------------------------------------------------------------


_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def plan_scaffold(name: str, *,
                  root: Path = ROOT,
                  hook_va: int | None = None,
                  xbe_bytes: bytes | None = None,
                  ghidra_client=None,
                  category: str = "qol",
                  ) -> ScaffoldPlan:
    """Build a :class:`ScaffoldPlan` without touching disk. ``xbe_bytes`` is
    the USA XBE that sizes the site; ``ghidra_client`` anything whose
    ``get_function(va)`` gives a ``signature`` and ``parameters``.

    Raises :exc:`ValueError` on a bad name, a pack or shim of that name or
    an existing file, or an unknown category, so the CLI can refuse early.
    """
    from azurkit.tools import mods
    from azurkit.tools.mods.engine import CATEGORIES

    if not _NAME_RE.match(name):
        raise ValueError(
            f"invalid name {name!r}: must match [a-z][a-z0-9_]* "
            f"(lowercase identifier starting with a letter)")
    if category not in CATEGORIES:
        raise ValueError(f"no category {category!r} (the categories: {', '.join(CATEGORIES)})")
    if name in mods.PACKS:
        raise ValueError(f"a pack named {name!r} exists; pick another name")
    pack_path, shim_c_path = root / PACKS / f"{name}.py", root / SHIMS / f"{name}.c"
    for path in (pack_path, shim_c_path, shim_c_path.with_suffix(".o")):
        if path.exists():
            raise ValueError(f"{path} already exists; pick a different name")

    abi: ABIGuess = ABIGuess()
    size, sha, preserved, planner_warnings = DEFAULT_SIZE, None, [], []

    if hook_va is not None and xbe_bytes is not None:
        from devkit.re.plan_trampoline import plan_trampoline
        try:
            plan = plan_trampoline(xbe_bytes, hook_va, budget=DEFAULT_SIZE)
            if plan.suggested_length > 0:
                size, preserved = plan.suggested_length, plan.preserved_mnemonics
                sha = hashlib.sha256(xbe_bytes[plan.file_offset:plan.file_offset + size]).hexdigest()
            else:
                planner_warnings.append(
                    "Planner couldn't determine the instruction boundary; the site's size is a guess "
                    f"({DEFAULT_SIZE} B): fill it in after consulting Ghidra or `xbe dis`.")
            planner_warnings.extend(plan.warnings)
        except ValueError as exc:
            planner_warnings.append(f"trampoline planner refused: {exc}")
        from azurkit.core import facts, gate
        if hook_va in facts.of(gate.USA).sites:
            planner_warnings.append(f"The facts already have a site at 0x{hook_va:08X}: another pack writes it, "
                                    "so the two would conflict (D28).")
        abi = abi_from_facts(xbe_bytes, hook_va) or abi
    elif hook_va is not None:
        planner_warnings.append(f"No XBE read: the site's size is a guess ({DEFAULT_SIZE} B); "
                                "pass --iso or --xbe, or run plan-trampoline.")

    if hook_va is not None and ghidra_client is not None:
        try:
            fn = ghidra_client.get_function(hook_va)
            abi = guess_abi_from_signature(
                fn.signature or "",
                parameters=fn.parameters)
        except Exception as exc:  # noqa: BLE001 (a live server's any failure: carry on without it)
            planner_warnings.append(
                f"Ghidra ABI lookup failed: {exc}")

    if abi.confidence == "low":
        # Give a hint that the author should verify before shipping.
        abi = replace(abi, notes=abi.notes + (
            "No Ghidra or facts ABI pickup: the scaffolded attribute is "
            "a guess.  Verify against Ghidra before shipping.",))

    return ScaffoldPlan(
        name=name,
        pack_path=pack_path,
        pack_body=generate_pack_py(name, hook_va=hook_va, abi=abi, category=category),
        shim_c_path=shim_c_path,
        shim_c_body=generate_shim_c(name, hook_va=hook_va, abi=abi),
        abi=abi,
        hook_va=hook_va,
        site_size=size,
        site_sha256=sha,
        preserved=preserved,
        planner_warnings=planner_warnings,
    )


def write_scaffold(plan: ScaffoldPlan) -> None:
    """Commit a :class:`ScaffoldPlan` to disk.  Refuses to
    overwrite an existing file so multiple invocations can't
    stomp each other."""
    for path in plan.files:
        if path.exists():
            raise ValueError(f"{path} already exists; scaffold refused")
    for path, body in ((plan.pack_path, plan.pack_body), (plan.shim_c_path, plan.shim_c_body)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as f:
            f.write(body)


def _ghidra(port: int | None):
    """A live Ghidra client on ``port``, or ``None`` with a line saying why not."""
    try:
        from devkit.re.ghidra_client import GhidraClient   # the Ghidra side's (Step 4.11d2)
    except ImportError:
        print("new-shim: --ghidra: devkit has no Ghidra client yet (devkit/re/ghidra_client.py, the Ghidra "
              "side's step); continuing without ABI pickup", file=sys.stderr)
        return None
    client = GhidraClient(port=port)
    if not client.ping():
        print(f"new-shim: --ghidra / --port passed but no live Ghidra on {client.base_url}; continuing "
              "without ABI pickup", file=sys.stderr)
        return None
    return client


def main(argv: list[str]) -> int:
    """Exit 0 when written (or planned, ``--dry-run``); 1 when refused (a
    bad or taken name, an existing file); 2 on a bad ``--hook``."""
    from devkit.re import xbe as xbe_verbs

    p = argparse.ArgumentParser(
        prog="python -m devkit re new-shim",
        description="Scaffold a shim pack: src/azurkit/tools/mods/packs/<name>.py (its PACK, one TrampolinePatch) "
                    "and shims/<name>.c (the entry, with the ABI the hook needs), then print the hand edits left. "
                    "With --hook it reads the USA XBE to size the site and, when the hook replaces a call to a "
                    "facts function, takes its ABI; --ghidra takes it from a live Ghidra.")
    p.add_argument("name", help="the pack's name (a lowercase identifier: [a-z][a-z0-9_]*)")
    p.add_argument("--hook", help="the hook site's USA VA (hex like 0x5F6E5, or decimal)")
    p.add_argument("--iso", metavar="PATH", help="the USA image (or a raw XBE) to size the site from "
                   "(default: the USA image the gate finds)")
    p.add_argument("--xbe", metavar="PATH", help="a raw USA default.xbe (or an image)")
    p.add_argument("--category", default="qol", help="the pack's tab group (default qol)")
    p.add_argument("--ghidra", action="store_true", help="take the ABI from a live Ghidra (port 8193 unless --port)")
    p.add_argument("--port", type=int, default=None, help="the live Ghidra's port")
    p.add_argument("--dry-run", action="store_true", help="print the plan and the files it would write, write none")
    args = p.parse_args(argv)

    hook_va: int | None = None
    if args.hook:
        try:
            hook_va = int(args.hook, 0)
        except ValueError:
            print(f"new-shim: bad --hook value {args.hook!r} (want hex like 0x5F6E5)", file=sys.stderr)
            return 2

    xbe_bytes = None
    if hook_va is not None:
        try:
            xbe_bytes, line = xbe_verbs.load(args.iso or args.xbe, "usa")
            print(line, file=sys.stderr)
        except (OSError, ValueError) as exc:
            print(f"new-shim: no XBE ({exc}); the site's size is a guess", file=sys.stderr)

    client = _ghidra(args.port) if args.ghidra or args.port is not None else None
    try:
        plan = plan_scaffold(args.name, hook_va=hook_va, xbe_bytes=xbe_bytes, ghidra_client=client,
                             category=args.category)
    except ValueError as exc:
        print(f"new-shim: {exc}", file=sys.stderr)
        return 1

    print(plan.summary())
    print()
    if args.dry_run:
        print("--dry-run: files that WOULD be written:")
        for f in plan.files:
            print(f"  {f}")
        return 0
    try:
        write_scaffold(plan)
    except ValueError as exc:
        print(f"new-shim: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote pack {plan.name!r}:")
    for f in plan.files:
        print(f"  - {f}")
    print("\nNext steps:")
    for i, step in enumerate(plan.next_steps(), 1):
        print(f"  {i}. {step}")
    return 0
