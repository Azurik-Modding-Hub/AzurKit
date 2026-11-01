"""A body's mesh measured against what the format and the game hold
(Step 2.154, D443: ``azurik-mod model inspect``).

:func:`inspect` decodes the body ``characters/<body>`` whole
(:func:`~azurik_mod.assets.body_codec.read_asset`) and reports, counts
and sizes only: its bones and markers; per LOD and group its vertices,
triangles, palette, push buffer bytes, strip indices a triangle and
material; the totals; the mesh's extent and drawn height; its payloads'
sizes; its own load runs (:func:`own_runs`, with what a player build
bakes onto it when the file lacks that, ``bake``) against the game's
load budget (40 MiB, or what ``qol_memory_budget`` wrote: :func:`budget_of`;
Step 2.158: an ``error`` past :data:`OWN_ERROR`, a ``warning`` past
:data:`OWN_WARNING`, both moved with the budget by :func:`lines_for`, Step
2.162b; the edges :data:`EDGES`; for a 128 MiB machine with both
:data:`UPPER_PACKS`, ``ram`` 128, :data:`OWN_ERROR_128` and
:data:`OWN_WARNING_128`, Step 2.162i, and an ``error`` for one run past
:data:`RUN_ERROR_128`, :func:`run_line_for`; the edges :data:`EDGES_128`;
for a 256 MiB one with :data:`UPPER256_PACK` too, ``ram`` 256, Step 2.162l,
:data:`OWN_ERROR_256`, :data:`OWN_WARNING_256` and :data:`RUN_ERROR_256`,
the edges :data:`EDGES_256`); each
other budget, either a limit of the format (31 palette bones, 65,536
vertices a group: an ``error`` past it) or the largest vanilla runs (a push buffer's 22,392 B, 156 bones: a
``warning`` past it, the game's own bound being unmeasured); and every
problem :func:`~azurik_mod.assets.body_codec.problems`
names, plus the file's own checks: the ``bmsh``'s relocations exactly its
groups' ``gshd`` fields, the body's LOD list relocated, and the normals
that aren't unit.  A body that doesn't decode is one problem, its
reason, and an entry in no load run is one too.  Step 2.166b (D537): each
LOD's share of LOD 0's counts, its ``bmsh``'s bytes and its own runs
(:func:`lod_runs`: what dropping it frees), and with ``config_xbr`` each
wearer's switch distances and which LODs the game draws at rest, only in
a fade, only in a realtime shadow or never (:mod:`~azurik_mod.assets.lods`).  Nothing here prints a
byte or a coordinate.
"""

from __future__ import annotations

import struct

from azurkit.tools.characters import body_codec, lods
from azurkit.tools.characters.characters import height, mesh_bounds, read_body
from azurkit.tools.characters.retarget import BAKED_DIR
from azurkit.core.xbr.nodes import named_resources, parse_toc, runs

VANILLA_MAX = {"push": body_codec.PUSH_MAX, "bones": 156}
"""The largest of each that vanilla runs (Step 2.154's reads: magmar's
group 0 push buffer, the most bones of any body).  A payload's size is no
limit (Step 2.158: a ``bmsh`` of 14x vanilla's largest loads and draws)."""

MiB = 1 << 20
BUDGET = 40 * MiB
"""The game's one budget for every loaded run (level, characters, fx,
interface ...) in vanilla: the limit ``[0x1BF404]``, set once at boot to
0x2800000 (USA 0x596C6, Europe 0x59706 ``[0x1C13A4]``; the pack
``qol_memory_budget`` rewrites it, :func:`budget_of` reads it).  It
reserves nothing: ``[0x1BF400]`` counts the runs' bytes and the run
allocator 0xA4890 refuses a run that would take it past the limit,
0xA64D0 evicts runs no one references and retries, and a run it can't
place loads as 0, so the body draw skips the mesh (0x3F16D).  The memory
check 0x58D00 lowers the limit when free physical memory falls under
1 MiB (Step 2.162: never at 40 MiB in xemu; raised, to 42.38 MiB at the
lowest: 44 held through a1's inventory and fell at the e2 and w1 changes,
48-52 were cut already at a1)."""
BUDGET_PACK = "qol_memory_budget"
"""The pack whose ``budget_mib`` site rewrites :data:`BUDGET`."""
ROOM = 42 * MiB
"""The most of a raised budget the player's lines count (Step 2.162b,
D515): the lowest limit the memory check left in any raised-budget row of
Step 2.162's sittings, 42.38 MiB (``results/synth/limit_floor``), so only
42 MiB is sure to last past the tight level changes.  Not a slider
clamp: ``qol_memory_budget`` writes any value it is given."""
OWN_ERROR = 12 * MiB
"""A player build's own runs (everything :func:`own_runs` counts on the
built file, the clips it bakes onto the body included) past this fail the
build (Step 2.158b, D509 amending D507, AZ-667; Step 2.158, D491,
AZ-665).  Measured in xemu at the nine D98 saves, a1's the tightest on a
load (the inventory opened at a1's, w1's and e2's only): played from
a1's save, the inventory screen (BACK: interface.xbr's runs,
loaded while it is open) stays whole with 12.67 MiB of them and loses
pieces with 15.79 (3 of 3 boots; the budget full, no run fails), though a
fresh load there keeps full detail with 15.79 and has lost its tree's
leaf textures by 17.67, silently too; w1's and e2's saves keep their
inventory with 15.79 and the level with 19.37 and have lost their save
platform's grille by 20.89; e2 from w1 by the debug warp keeps full
detail to 21.4, and that change hangs on "Loading..." past about 23.1.
12 MiB leaves 0.67 under the in-play edge for boot-to-boot variation.
At the vanilla 40 MiB budget; :func:`lines_for` moves it with a raised one.
Whatever the species; the 13 levels with no save, and the other six
saves' inventories, weren't measured.  The same holds in Europe: its
budget is the same 40 MiB and its level XBRs, characters.xbr and fx.xbr
are USA's."""
OWN_WARNING = 10 * MiB
"""A warning past this: about where a1's save, on a load, fills the 40 MiB
and starts evicting the level's cached runs (at 10.1-10.9 MiB by its load
census: none at 10.01, some at 12.67, its full detail and inventory
kept; with its inventory open the budget is full at any size, female_2's
plain 2.41 MiB too).  At 40 MiB, like :data:`OWN_ERROR`."""
EDGES = (12.67, 15.79, 17.7, 23.1)
"""MiB of own runs at a1's save, the tightest on a load: in play its
inventory screen stays whole with the first and loses pieces with the
second (AZ-667), which a fresh load still draws at full detail; the level
has lost textures by about the third; e2 by the debug warp hangs past the
fourth (no save load hung up to 22.0).  All at the vanilla 40 MiB budget."""
RAMS = (64, 128, 256)
"""The machines a player build may be made for (Step 2.162i, D576;
``--ram``): 64 MiB, a retail Xbox's, 128 MiB (xemu at ``mem_limit``
128, :data:`DEFAULT_RAM`), where :data:`UPPER_PACKS` put the load runs
above 64 MiB, or 256 MiB (Step 2.162l, D600: xemu v0.16.2 or later at
``mem_limit`` 256, xemu only: ``docs/XEMU_ONLY.md`` X14), whose build adds :data:`UPPER256_PACK`
(:func:`ram_packs`).  At 64 and 128 the bytes built are the same and
only the own runs' lines differ."""
DEFAULT_RAM = 128
"""The machine a build and its measures are for unless ``--ram 64`` says
otherwise (the owner's D588, Step 2.162k: "Default to 128 MiB", with both
:data:`UPPER_PACKS` on by default).  A body past the 64 MiB lines then
builds and plays right only at 128 MiB: on a 64 MiB Xbox it loses
pieces and textures, and a larger one hangs loading (xemu at 64)."""
UPPER_PACKS = ("qol_memory_upper64", "qol_memory_upper64_gpu")
"""The packs that make a 128 MiB machine's room (Steps 2.162f and
2.162h): the virtual load runs and the GPU's above 64 MiB.  A 128 MiB
target takes :data:`OWN_ERROR_128` and :data:`OWN_WARNING_128` only with
both in its ``default.xbe`` (:func:`upper_of`); otherwise the 64 MiB
lines hold."""
UPPER256_PACK = "qol_memory_upper256"
"""The pack a 256 MiB target adds to the default ones (Step 2.162l, D600):
the RAM from 128 to 256 MiB as the upper heap's third tier, which takes
a mesh run larger than the room left between 64 and 128 MiB
(``qol_memory_upper64_gpu`` lets a run that fits the heap past the budget
compare, Step 2.162m).  A
256 MiB target takes :data:`OWN_ERROR_256`, :data:`OWN_WARNING_256` and
:data:`RUN_ERROR_256` only with it and both :data:`UPPER_PACKS` in its
``default.xbe`` (:func:`lines_ram`); otherwise the 128 MiB lines hold."""
OWN_ERROR_128 = 99 * MiB // 2
"""A 128 MiB target's error line at the 42 MiB budget, both
:data:`UPPER_PACKS` on (USA and Europe, xemu v0.16.2 at ``mem_limit`` 128,
cold-booted into a1's save and played at a1, w1, e2, a1 and w1 by the
warp, Step 2.162n's sitting, D625's placement): 49.5 MiB, the largest
total measured whole, 49.49 MiB (lim_k41: its 42.34 MiB mesh run above
64 MiB, uncounted, and 7.15 MiB more; the budget held 15.43-29.17 of
42 MiB).  Its upper edge is not bracketed [unmeasured]: the probe bodies
carry their mesh run and 7.05-8.28 MiB more, so each larger one also had
a run past :data:`RUN_ERROR_128` (50.34 MiB and up never finished
loading).  Before (Step 2.162m, the first fit) it was 46.5, under a
47.62 MiB body whose 40.88 MiB mesh run fell back into the budget.
:func:`lines_for` lowers it with a budget under 42 MiB, as the 64 MiB
lines.  Real hardware is unmeasured."""
OWN_WARNING_128 = 38 * MiB
"""A 128 MiB target's warning line, as :data:`OWN_ERROR_128` (D603: a
warning, never a refusal): under the largest probe body whose mesh run
stayed above 64 MiB with the first fit, 38.79 MiB (Step 2.162h).  Kept
by Step 2.162n's record: with its placement the 49.49 MiB body's run
stays high too, and its frame rate held in real-time xemu (0-0.34 %
under vanilla's at a1 in 3 alternated pairs), but its heaviest frame
(a1, turning) draws 39.90 times vanilla's vertex bytes under icount."""
RUN_ERROR_128 = 10838 * 4096
"""A 128 MiB target's line for the body's largest single own run
(:func:`own_runs`' ``largest``) at the 42 MiB budget, both
:data:`UPPER_PACKS` on: 42.34 MiB, the mesh run of Step 2.162n's
49.49 MiB probe body (10,838 pages), the largest that played a1, w1, e2,
a1 and w1 whole from a1's save (USA and Europe).  The heap places the CPU
runs from the top of the room above 64 MiB down and the GPU runs from its
bottom up (Step 2.162n, D625), so the mesh run, which asks after the
boot's runs, takes the span between them (at page 1,256 above 64 MiB in
every phase) and ``qol_memory_upper64_gpu``'s budget hook (Step 2.162m,
D616) passes it uncounted; with 0 refusals at the mode-1 compare
(0xA48E9), none at w1's 1.00 MiB ``run_pages_alloc`` user (0xBAB8F) and
no failed run allocation.  One of 43.11 MiB (11,036 pages) and up fits no
span there and passes the budget, so the compare refused it (twice) and
the save never finished loading: the edge lies between 42.34 and 43.11,
about 43.09 (11,032 pages for a GPU run, read at that stall [at the ask
inferred]).  That span ends where the CPU's four blocks above 64 MiB
begin: a save whose CPU runs take a fifth would leave 39.09 MiB
[inferred; only a1's save was measured].  Before (Step 2.162m, the first
fit) a1's save left 36 MiB there, so a body's mesh run fell back into the
budget and the line was 40.875 MiB.  Europe (its allocator the same) took
no refusal at the boot; past it its hooks had no liveness counter
[inferred from Step 2.162m's, which counted live].  :func:`run_line_for`
lowers it with a budget under 42 MiB."""
EDGES_128 = (49.49, 50.34)
"""MiB of own runs at 128 MiB with both :data:`UPPER_PACKS` (Step 2.162n):
the largest probe body played whole, its mesh run above 64 MiB, and the
smallest that never finished the save's load (its 43.11 MiB mesh run past
the span there and the budget)."""
OWN_ERROR_256 = 127 * MiB
"""A 256 MiB target's error line at the 42 MiB budget, with
:data:`UPPER256_PACK` (Step 2.162l's sitting: USA, xemu v0.16.2 at
``mem_limit`` 256, probe bodies cold-booted into a1's save and played at
a1, its inventory, w1 and e2 by the warp): every one up to 128.21 MiB of
own runs played, its mesh run in the third tier; 127 leaves 1.21 MiB
under it, as :data:`OWN_ERROR_128` leaves 1.00.  No larger total was
measured (D610: approximate).  :func:`lines_for` lowers it with a budget
under 42 MiB, as the 128 MiB lines.  Real hardware has no 256 MiB."""
OWN_WARNING_256 = 48 * MiB
"""A 256 MiB target's warning line: the frame rate (D603: warn, never
refuse).  The 48.25 MiB body (a 41.45 MiB mesh run) held vanilla's
30 fps in real-time xemu at 256 MiB, as at 128; the 128.21 MiB one ran
w1 at 19.6 fps, 34-36 % under vanilla's, in 3 alternated pairs; between
them it is unmeasured."""
RUN_ERROR_256 = 29063 * 4096
"""A 256 MiB target's line for the body's largest single own run at the
42 MiB budget, with :data:`UPPER256_PACK`: 113.53 MiB, the mesh run of
Step 2.162l's 128.21 MiB body, the largest that played.  One of 128.90
MiB fits no tier (the third hands out 124.00 MiB in one mesh span: 31
GPU blocks; block 47, T3's bitmap, stays CPU), so the budget compare
refused it and the save never finished loading; the edge lies between
113.53 and 124.00.  :func:`run_line_for` lowers it with a budget under
42 MiB."""
EDGES_256 = (48.25, 128.21, 145.27)
"""MiB of own runs at 256 MiB with :data:`UPPER256_PACK` (Step 2.162l):
the largest body measured at vanilla's frame rate, the largest that
played (its frame rate 34-36 % under vanilla's at w1), and the one that
never finished the save's load (its 128.90 MiB mesh run refused)."""
BAKE_MAX = 3.8
"""MiB the largest player build adds to its body's own runs (the
townsmen in own mode; female_2 2.05, most species with their own clips
under 0.1): what an unbuilt file lacks of a build's count."""
SOUND_DIR = "fx/sound/v/"
"""fx.xbr's variant sounds (``_player_variants.VARIANT_SOUND_DIR``):
the player's own runs there."""


def _budget_site():
    """``qol_memory_budget``'s ``budget_mib`` site and the pack, by name
    from the registry (as :func:`upper_of` finds its packs): the assets
    import no pack (Step X.100)."""
    from azurkit.tools.characters.ports import get_pack

    pack = get_pack(BUDGET_PACK)
    return next(s for s in pack.parametric_sites() if s.name == "budget_mib"), pack


def budget_of(xbe: bytes) -> int:
    """The load budget, in bytes, that ``xbe`` (a ``default.xbe`` of either
    release, vanilla or built) sets at boot: the imm32 ``qol_memory_budget``
    writes (:data:`BUDGET` in vanilla), whoever wrote it."""
    from azurkit.tools.characters.ports import xbe_site

    site, _ = _budget_site()
    _, offset, _ = xbe_site(xbe, site.va, site.original)
    return struct.unpack_from("<I", xbe, offset)[0]


def default_budget() -> int:
    """The load budget, in bytes, a build writes unless told not to (D528):
    ``qol_memory_budget``'s default (42 MiB) while the pack is on by
    default, else vanilla's :data:`BUDGET`; what a body is measured
    against when no built ``default.xbe`` says otherwise."""
    site, pack = _budget_site()
    return round(site.default * MiB) if pack.default_on else BUDGET


def ram_packs(ram: int) -> tuple[str, ...]:
    """The packs a build for a ``ram`` MiB machine turns on beside the
    default ones: :data:`UPPER256_PACK` at 256, else none."""
    return (UPPER256_PACK,) if ram == 256 else ()


def lines_for(budget: int, ram: int) -> tuple[int, int]:
    """(error, warning): the player's own-runs lines, in bytes, under a load
    budget of ``budget`` bytes (Step 2.162b, D515): :data:`OWN_ERROR` and
    :data:`OWN_WARNING`, measured at 40 MiB, both moved by
    min(``budget``, :data:`ROOM`) - :data:`BUDGET`, so 14 and 12 MiB at
    42 MiB or more and lower ones below 40.  ``ram`` 128 (Step 2.162i: a
    128 MiB target whose build has both :data:`UPPER_PACKS`, which the
    caller checks, :func:`upper_of`): :data:`OWN_ERROR_128` and
    :data:`OWN_WARNING_128`, measured at 42 MiB, moved by
    min(``budget``, :data:`ROOM`) - :data:`ROOM`: 49.5 and 38 MiB at 42 or
    more.  ``ram`` 256 (Step 2.162l, its build with :data:`UPPER256_PACK`
    too): :data:`OWN_ERROR_256` and :data:`OWN_WARNING_256`, moved as the
    128 MiB lines: 127 and 48 MiB at 42 or more."""
    if ram not in RAMS:
        raise ValueError(f"--ram {ram}: not one of {', '.join(map(str, RAMS))} (MiB)")
    if ram >= 128:
        room = min(budget, ROOM) - ROOM
        error, warning = (OWN_ERROR_256, OWN_WARNING_256) if ram == 256 else (OWN_ERROR_128, OWN_WARNING_128)
        return error + room, warning + room
    room = min(budget, ROOM) - BUDGET
    return OWN_ERROR + room, OWN_WARNING + room


def run_line_for(budget: int, ram: int = 128) -> int:
    """The largest single own run, in bytes, a 128 MiB target with both
    :data:`UPPER_PACKS` takes under a load budget of ``budget`` bytes:
    :data:`RUN_ERROR_128` (``ram`` 256: :data:`RUN_ERROR_256`) moved by
    min(``budget``, :data:`ROOM`) - :data:`ROOM`, as :func:`lines_for`'s
    128 MiB lines."""
    return (RUN_ERROR_256 if ram == 256 else RUN_ERROR_128) + min(budget, ROOM) - ROOM


def upper_of(xbe: bytes, names=UPPER_PACKS) -> bool:
    """Whether ``xbe`` (a ``default.xbe`` of either release, vanilla or
    built) carries every pack ``names`` names (both :data:`UPPER_PACKS`):
    every hook of theirs applied, whoever applied it."""
    from azurkit.tools.characters.ports import verify_trampoline_patch
    from azurkit.tools.characters.ports import get_pack

    return all(verify_trampoline_patch(xbe, hook) == "applied"
               for name in names for hook in get_pack(name).trampoline_sites())


def lines_ram(xbe: bytes, ram: int) -> int:
    """The machine whose lines a build for ``ram`` MiB takes, by what its
    ``default.xbe`` ``xbe`` carries: 256 with :data:`UPPER256_PACK` and both
    :data:`UPPER_PACKS`, 128 (at ``ram`` 128 or 256) with both
    :data:`UPPER_PACKS`, else 64."""
    if ram >= 128 and upper_of(xbe):
        return 256 if ram == 256 and upper_of(xbe, (UPPER256_PACK,)) else 128
    return 64


PROJECTILE = "characters/debug"
"""The player's projectile (W30's spare species ``debug``, placed in no
level: Steps 2.159b, 2.167b), which a build that throws one adds; in no
vanilla file."""


def own_runs(characters_xbr: bytes, body: str, fx_xbr: bytes | None = None, *, body_entry: bool = True) -> dict:
    """The load runs (:func:`~azurik_mod.xbr.toc_scan.runs`) holding any
    entry the body ``characters/<body>`` reaches or names: the body entry
    and every entry named under ``characters/<body>/`` (its meshes,
    clips, textures, its fx and the player's clone of it, and its
    shield and beam rows' graphs: Step 2.167c), and a player
    build's projectile, :data:`PROJECTILE` and every entry under it (W30's
    ``debug``: Step 2.167b, the rock, the vase or a template's body, clips
    and graphs, which the player's throws load), with everything
    their relocated fields reach; with ``fx_xbr``, also fx.xbr's runs
    holding the variant sounds (:data:`SOUND_DIR`) and what they reach.
    ``{"bytes", "runs", "largest", "by_tag"}``, each run counted once at
    its whole pages, by its head's tag; ``largest`` the largest one's.  A run shared with another body counts in
    full (vanilla's female_2: 0.367 MiB).  ``body_entry`` false (AZ-761, Step 2.198): the body entry itself
    is no root, so what only it reaches is left out: a recoloured body's where the game loads W38's copy
    (``v/skin``) alone (:func:`placed_species`)."""
    from azurkit.core.xbr.clone import closure

    index, name = body_codec._body_entry(characters_xbr, body)
    total = {"bytes": 0, "runs": 0, "largest": 0, "by_tag": {}}
    thrown = [] if name.casefold() == PROJECTILE[len("characters/"):] else [
        i for i, n in named_resources(characters_xbr).items()
        if n.casefold() == PROJECTILE or n.casefold().startswith(PROJECTILE + "/")]
    for data, prefix, extra in ((characters_xbr, f"characters/{name}/", ([index] if body_entry else []) + thrown),
                                (fx_xbr, SOUND_DIR, [])):
        if data is None:
            continue
        roots = extra + [i for i, n in named_resources(data).items() if n.casefold().startswith(prefix.casefold())]
        if not roots:
            continue
        part, toc = runs(data), parse_toc(data)
        size = {r.head: r.size for r in part.runs}
        for head in sorted({part.of[i] for i in closure(data, roots) if i in part.of}):
            total["bytes"] += size[head]
            total["runs"] += 1
            total["largest"] = max(total["largest"], size[head])
            total["by_tag"][toc[head].tag] = total["by_tag"].get(toc[head].tag, 0) + size[head]
    total["by_tag"] = dict(sorted(total["by_tag"].items(), key=lambda kv: (-kv[1], kv[0])))
    return total


_PLACED: dict[str, frozenset[str]] = {}
""":func:`placed_species` by the release it read (``Vanilla.release_key``)."""


def placed_species(iso) -> frozenset[str]:
    """The ``critters_engine`` species some level of the image ``iso``
    places (AZ-761, Step 2.198): each ``critterGenerator``'s critter in the
    node graphs of every ``gamedata/*.xbr`` (its name up to a ``:`` path,
    case-folded; about 0.25 s over the USA image's 41 files).  The USA
    image's town places town_female_3, _4 and _sleep, town_girlchild_1 and
    town_male_3, _6 and _sleep, and no level town_female_2 (D361).  Worked
    out once a release (:data:`_PLACED`), each level read with ``iso.peek``,
    so the 850 MiB of levels a dress never otherwise reads aren't held
    through it."""
    import re

    from azurkit.tools.characters.ports import XisoReader
    from azurkit.core.xbr import graph as nodes

    release = iso.release_key
    if release in _PLACED:
        return _PLACED[release]
    out = set()
    with XisoReader(iso) as rd:
        schema = nodes.Schema(bytes(rd.read_file("default.xbe")))
        for path, entry in rd.walk():
            if entry.is_dir or not re.fullmatch(r"gamedata/[^/]+\.xbr", path.lower()):
                continue
            for g in nodes.graphs(iso.peek(path), schema):
                out |= {name.split(":")[0].casefold() for i, kind in enumerate(g.types)
                        if kind == "critterGenerator" and (name := g.pstr(g.recs[i], 0x1C))}
    if release is not None:
        _PLACED[release] = frozenset(out)
    return frozenset(out)


def own_words(own: dict) -> str:
    """``own``'s size and its largest parts, in MiB."""
    parts = ", ".join(f"{tag} {n / MiB:.2f}" for tag, n in list(own["by_tag"].items())[:4])
    return f"{own['bytes'] / MiB:.2f} MiB ({parts})"


def lod_runs(characters_xbr: bytes, asset: body_codec.BodyAsset) -> list[int]:
    """Bytes, at whole pages, of the load runs only each LOD of ``asset``
    reaches (its ``bmsh`` and what that reaches, against the body, its
    other LODs and everything named under ``characters/<body>/``): what
    dropping it frees of :func:`own_runs`, its push buffers' pages in the
    body's run aside."""
    from azurkit.core.xbr.append import relocations
    from azurkit.core.xbr.clone import closure, refs_in

    data, rows = characters_xbr, sorted(relocations(characters_xbr))
    toc, part = parse_toc(data), runs(data)
    size = {r.head: r.size for r in part.runs}
    prefix = f"characters/{asset.name}/".casefold()
    named = [i for i, n in named_resources(data).items() if n.casefold().startswith(prefix)]
    lods_at = struct.unpack_from("<i", data, toc[asset.index].file_offset + 12)[0] + 12
    refs = refs_in(data, toc, asset.index, rows)

    def heads(entries) -> set[int]:
        return {part.of[i] for i in entries if i in part.of}
    out = []
    for n, lod in enumerate(asset.lods):
        rest = heads(closure(data, named + [t for at, t in refs if at != lods_at + 4 * n], rows))
        rest |= heads([asset.index])
        out.append(sum(size[h] for h in heads(closure(data, [lod.bmsh], rows)) - rest))
    return out


def _relocations(data: bytes) -> list[int]:
    h = struct.unpack_from("<15I", data, 0)
    return list(struct.unpack_from(f"<{h[7]}I", data, h[8]))


def inspect(characters_xbr: bytes, body: str, *, fx_xbr: bytes | None = None, config_xbr: bytes | None = None,
            bake: int = 0, budget: int | None = None, ram: int = DEFAULT_RAM) -> dict:
    """The report (module docstring) as a JSON-able dict; with
    ``fx_xbr``, the own runs count the variant sounds there, with
    ``config_xbr`` it names the species that wear the body (an NPC's body
    counts in the levels that place it), and ``bake`` (bytes) is what a
    player build adds to the own runs that this file lacks (``model
    edit`` measures it), counted in the budget.  ``budget`` (bytes) is the
    game's load budget the own runs' lines follow (:func:`lines_for`;
    the row names it; None: a default build's, :func:`default_budget`);
    ``ram`` the machine's MiB the lines are for (:data:`RAMS`; 128: a
    build with both :data:`UPPER_PACKS`, Step 2.162i, a default build's
    since D588, :data:`DEFAULT_RAM`; 256: one with :data:`UPPER256_PACK`
    too, Step 2.162l; the row names it; 128 and 256 add the largest run's
    row, :data:`RUN`).
    ``baked``: the file holds a player build's baked clips for the body."""
    budget = default_budget() if budget is None else budget
    toc = parse_toc(characters_xbr)
    out: dict = {"body": body, "file_bytes": len(characters_xbr), "toc_entries": len(toc), "problems": [],
                 "budgets": []}
    try:
        asset = body_codec.read_asset(characters_xbr, body)
        own = own_runs(characters_xbr, body, fx_xbr)
    except ValueError as exc:
        out["problems"].append(str(exc))
        return out
    out["own_runs"], out["bake"] = own, bake
    baked = f"characters/{asset.name}/{BAKED_DIR}".casefold()
    out["baked"] = any(n.casefold().startswith(baked) for n in named_resources(characters_xbr).values())
    orphans = runs(characters_xbr).orphans
    if orphans:
        out["problems"].append(f"{len(orphans)} TOC entries are in no load run (the first {orphans[0]}): the game "
                               "can't load them")
    worn = None
    if config_xbr is not None:
        worn = lods.wearers(config_xbr, asset.name)
        out["worn_by"] = [w.species for w in worn]
    out["body"] = asset.name
    out["toc"] = asset.index
    out["bones"] = len(asset.bones)
    out["markers"] = len(asset.markers)
    groups = []
    for n, lod in enumerate(asset.lods):
        for g, grp in enumerate(lod.groups):
            push = len(body_codec._push(grp)[0]) if len(grp.palette) <= body_codec.PALETTE_MAX else 0
            strip = body_codec._push(grp)[1] + 2 if push else 0
            groups.append({"lod": n, "group": g, "vertices": len(grp.vertices), "triangles": len(grp.triangles),
                           "palette": len(grp.palette), "push_bytes": push,
                           "indices_per_triangle": round(strip / len(grp.triangles), 3) if grp.triangles else 0.0,
                           "material": list(grp.material)})
    out["groups"] = groups
    count, own_lod = len(asset.lods), lod_runs(characters_xbr, asset)
    out["lods"] = []
    for n, lod in enumerate(asset.lods):
        row = {"lod": n, "bmsh": lod.bmsh, "groups": len(lod.groups)}
        for key in ("vertices", "triangles", "palette", "push_bytes"):
            row[key] = sum(g[key] for g in groups if g["lod"] == n)
        out["lods"].append(row | {"bmsh_bytes": toc[lod.bmsh].size, "run_bytes": own_lod[n]})
    for row in out["lods"]:
        row["share"] = {key: round(row[key] / out["lods"][0][key], 3) if out["lods"][0][key] else None
                        for key in ("vertices", "triangles", "palette", "push_bytes")}
    if worn is not None:
        out["wearers"] = []
        for w in worn:
            steady, drawn = lods.reach(w.thresholds, w.far, count)
            out["wearers"].append({"species": w.species, "thresholds": w.thresholds, "far_clip": w.far,
                                   "spans": lods.spans(w.thresholds, w.far, count), "steady": steady, "drawn": drawn,
                                   "shadow_lod": min(lods.SHADOW_LOD, count - 1) if w.shadow else None})
        steady = set().union(*(w["steady"] for w in out["wearers"])) if worn else set()
        drawn = set().union(*(w["drawn"] for w in out["wearers"])) if worn else set()
        shadow = {w["shadow_lod"] for w in out["wearers"]}
        for row in out["lods"]:
            row["drawn"] = ("steady" if row["lod"] in steady else "fade" if row["lod"] in drawn else
                            "shadow" if row["lod"] in shadow else "never")
        never = [row for row in out["lods"][1:] if row["drawn"] == "never"]
        out["never_drawn"] = {"lods": [row["lod"] for row in never], "bmsh_bytes": sum(r["bmsh_bytes"] for r in never),
                              "run_bytes": sum(r["run_bytes"] for r in never)}
    bounds = mesh_bounds(characters_xbr, asset.name)
    info = read_body(characters_xbr, asset.name)
    out["extent"] = {"width": round(bounds[1][0] - bounds[0][0], 4), "depth": round(bounds[1][1] - bounds[0][1], 4),
                     "tall": round(bounds[1][2] - bounds[0][2], 4),
                     "height": round(height(characters_xbr, info), 4)} if bounds else None
    sizes = {"body": toc[asset.index].size, "bmsh": [toc[lod.bmsh].size for lod in asset.lods]}
    out["payload_bytes"] = sizes

    def check(what: str, value: int, limit: int, kind: str, warn: int | None = None) -> None:
        level = ("warning" if kind == "vanilla" else "error") if value > limit else \
            "warning" if warn is not None and value > warn else "ok"
        out["budgets"].append({"what": what, "value": value, "limit": limit, "kind": kind, "over": level != "ok",
                               "level": level} | ({"warn": warn} if warn is not None else {}))
    error, warning = lines_for(budget, ram)
    check("own load runs bytes", own["bytes"] + bake, error, "game", warning)
    out["budgets"][-1] |= {"budget": budget, "ram": ram}
    if ram >= 128:
        check(RUN, own["largest"], run_line_for(budget, ram), "game")
    for row in groups:
        where = f"LOD {row['lod']} group {row['group']}"
        check(f"{where} palette bones", row["palette"], body_codec.PALETTE_MAX, "format")
        check(f"{where} vertices", row["vertices"], body_codec.INDEX_MAX + 1, "format")
        check(f"{where} push buffer bytes", row["push_bytes"], VANILLA_MAX["push"], "vanilla")
    check("bones", len(asset.bones), VANILLA_MAX["bones"], "vanilla")

    out["problems"] += body_codec.problems(asset, characters_xbr)
    relocs = set(_relocations(characters_xbr))
    e = toc[asset.index]
    lods_at = struct.unpack_from("<i", characters_xbr, e.file_offset + 12)[0] + 12
    for n in range(len(asset.lods)):
        if e.rel_offset + lods_at + 4 * n not in relocs:
            out["problems"].append(f"{asset.name}: LOD {n}'s bmsh index isn't relocated")
    for n, lod in enumerate(asset.lods):
        m = toc[lod.bmsh]
        inside = sorted(r - m.rel_offset for r in relocs if m.rel_offset <= r < m.rel_offset + m.size)
        if inside != [8 + 40 * g + 32 for g in range(len(lod.groups))]:
            out["problems"].append(f"{asset.name}: LOD {n}'s bmsh relocations aren't its groups' gshd fields")
    loose = sum(1 for lod in asset.lods for g in lod.groups for v in g.vertices
                if abs(sum(c * c for c in v.normal) - 1.0) > 2e-3)
    out["normals_not_unit"] = loose
    return out


RUN = "largest own load run bytes"
"""The 128 MiB target's row for the body's largest single own run
(:data:`RUN_ERROR_128`)."""


def _m(metres: float) -> str:
    return "none" if metres >= lods.FLT_MAX else f"{metres:g}"


def lod_line(report: dict, lod: dict) -> str:
    """The report's row ``lod`` (one of ``report["lods"]``) as text: its
    counts, share of LOD 0's triangles, push and ``bmsh`` bytes, own runs
    and, for a body of more than one LOD, what draws it (``model edit``'s
    passes print it too, Step 2.166e)."""
    share = lod["share"]["triangles"]
    share = f" ({share} of LOD 0's)" if lod["lod"] and share is not None else ""
    drawn = {"steady": "; drawn", "fade": "; drawn only in a fade", "shadow": "; drawn only in a realtime shadow",
             "never": "; never drawn"}.get(lod.get("drawn"), "") if len(report["lods"]) > 1 else ""
    return (f"LOD {lod['lod']} (bmsh {lod['bmsh']}): {lod['groups']} groups, {lod['vertices']} vertices, "
            f"{lod['triangles']} triangles{share}, push {lod['push_bytes']} B, palette {lod['palette']}; bmsh "
            f"{lod['bmsh_bytes']} B, its own runs {lod['run_bytes']} B{drawn}")


def lines(report: dict) -> list[str]:
    """The report as text, counts only."""
    out = [f"{report['body']}: {report.get('bones', '?')} bones, {report.get('markers', '?')} markers, "
           f"characters.xbr {report['file_bytes']} B, {report['toc_entries']} TOC entries"]
    several = len(report.get("lods", [])) > 1
    for lod in report.get("lods", []):
        out.append(lod_line(report, lod))
        for g in report.get("groups", []):
            if g["lod"] == lod["lod"]:
                out.append(f"  group {g['group']}: {g['vertices']} vertices, {g['triangles']} triangles, palette "
                           f"{g['palette']}, push {g['push_bytes']} B ({g['indices_per_triangle']} indices a "
                           f"triangle), material {tuple(g['material'])}")
    if report.get("extent"):
        b = report["extent"]
        out.append(f"the mesh spans {b['width']} wide, {b['depth']} deep and {b['tall']} tall (model units), its "
                   f"height {b['height']} (what the size option scales by)")
    if "payload_bytes" in report:
        out.append(f"payloads: body {report['payload_bytes']['body']} B, bmsh {report['payload_bytes']['bmsh']} B")
    game = next((b for b in report["budgets"] if b["kind"] == "game"), None)
    budget = game["budget"] if game else BUDGET
    ram = game.get("ram", 64) if game else 64
    if "own_runs" in report:
        bake = (f", and {report['bake'] / MiB:.2f} MiB a player build bakes onto it" if report["bake"] else
                "" if report["baked"] else f" (no player build's clips baked in: a build adds up to {BAKE_MAX} MiB, "
                "which model edit and the build count)")
        at = "" if budget == BUDGET else f" (measured at the vanilla {BUDGET // MiB} MiB)"
        out.append(f"own runs {own_words(report['own_runs'])}{bake}: the game loads every run into "
                   f"{budget / MiB:g} MiB; at a1's save, the tightest on a load, play keeps the inventory screen whole "
                   f"with {EDGES[0]} MiB of a build's and loses pieces of it with {EDGES[1]} (a fresh load still at "
                   f"full detail there), and the level has lost textures by about {EDGES[2]}; e2 by the warp hangs "
                   f"past about {EDGES[3]}{at}" if ram == 64 else
                   f"own runs {own_words(report['own_runs'])}{bake}: on a 128 MiB machine with {UPPER_PACKS[0]} and "
                   f"{UPPER_PACKS[1]} the game loads the runs above 64 MiB, and a run with no room there into the "
                   f"{budget / MiB:g} MiB budget; played from a1's save (a1, w1, e2), a body played whole with its "
                   f"mesh run high with {EDGES_128[0]:.2f} MiB and never finished loading with {EDGES_128[1]:.2f} "
                   "(its mesh run past the room there; measured at 42 MiB, in xemu)" if ram == 128 else
                   f"own runs {own_words(report['own_runs'])}{bake}: on a 256 MiB machine (xemu v0.16.2 or later at "
                   f"mem_limit 256) with {UPPER256_PACK} the game loads the runs above 64 MiB, a mesh run past the "
                   f"budget among them; played from a1's save (a1, its inventory, w1, e2), a body held vanilla's frame "
                   f"rate with {EDGES_256[0]:.2f} MiB, played with {EDGES_256[1]:.2f} (34-36 % under vanilla's frame "
                   f"rate at w1 in real time) and never finished loading with {EDGES_256[2]:.2f} (its mesh run past "
                   "the heap's largest span; measured at 42 MiB, in xemu)")
        largest = report["own_runs"]["largest"]
        if ram == 256 and game and (game["value"] > (mid := lines_for(budget, 128)[0])
                                    or largest > run_line_for(budget)):
            out.append(f"past the {mid / MiB:g} MiB (one run {run_line_for(budget) / MiB:.2f}) a 128 MiB machine "
                       "takes: this body plays right only on a 256 MiB one (xemu v0.16.2 or later at mem_limit 256); "
                       "at 128 MiB it loses loads or never finishes loading, and on a 64 MiB Xbox it loses pieces "
                       "and textures or hangs loading (--ram 128 refuses it)")
        elif ram >= 128 and game and game["value"] > (low := lines_for(budget, 64)[0]):
            on = "128 or 256 MiB one (xemu at mem_limit 128 or 256)" if ram == 256 else \
                "128 MiB one (xemu at mem_limit 128)"
            out.append(f"past the {low / MiB:g} MiB a 64 MiB machine takes: this body plays right only on a {on}; "
                       "on a 64 MiB Xbox it loses pieces and textures, and a larger one hangs loading (xemu at 64; "
                       "--ram 64 refuses it)")
    if report.get("worn_by"):
        out.append(f"worn by {', '.join(report['worn_by'])}: an NPC's body counts in the levels that place it")
    for w in report.get("wearers", []):
        at = ", ".join(f"{k} to {_m(s[1])} m" for k, s in enumerate(w["spans"]) if s)
        fades = sorted(set(w["drawn"]) - set(w["steady"]))
        out.append(f"  {w['species']} switches LODs at {', '.join(_m(t) for t in w['thresholds'])} m and culls past "
                   f"{_m(w['far_clip'])} m: LOD {at}" + (f"; its fades also draw {', '.join(map(str, fades))}"
                                                        if fades else "")
                   + (f"; its realtime shadow draws LOD {w['shadow_lod']}" if w.get("shadow_lod") is not None else ""))
    for lod in report.get("lods", [])[1:]:
        if lod.get("drawn") == "never":
            why = (f"the pick reads {lods.PICKED} switch distances, so LOD {lods.PICKED + 1} and on never draw"
                   if lod["lod"] > lods.PICKED else "no species wears the body" if not report.get("wearers") else
                   "no wearer's switch distances and farClip reach it, even in a fade")
            out.append(f"warning: LOD {lod['lod']} is never drawn ({why}): bmsh {lod['bmsh_bytes']} B, its own runs "
                       f"{lod['run_bytes']} B")
    if several:
        out.append("LODs load with the body, drawn or not: a LOD saves draw work and adds its own runs to the load "
                   "budget; dropping one the game never draws frees its own runs")
    flagged = [b for b in report["budgets"] if b["over"]]
    out.append(f"budgets: {len(report['budgets'])} checked, {len(flagged)} over")
    own = report.get("own_runs") or {"bytes": 0, "largest": 0}
    up = next((r for r in RAMS if r > ram and own["bytes"] + report.get("bake", 0) <= lines_for(budget, r)[0]
               and own["largest"] <= run_line_for(budget, r)), None)   # the smallest machine that takes the body
    up_hint = ("" if up is None else
               f"; {lines_for(budget, 128)[0] / MiB:g} MiB for a 128 MiB machine (--ram 128, {UPPER_PACKS[1]} on)"
               if up == 128 else
               f"; {lines_for(budget, 256)[0] / MiB:g} MiB, one run {run_line_for(budget, 256) / MiB:.2f}, for a "
               f"256 MiB machine (--ram 256, {UPPER256_PACK} on; xemu v0.16.2 or later at mem_limit 256)")
    machine = (f"a 256 MiB machine with {UPPER256_PACK}" if ram == 256 else
               f"a 128 MiB machine with {UPPER_PACKS[0]} and {UPPER_PACKS[1]}")
    for b in flagged:
        if b["what"] == RUN:
            out.append(f"  {b['level']}: {b['what']} {b['value'] / MiB:.2f} MiB, past the {b['limit'] / MiB:.2f} MiB "
                       f"one run may take on {machine} at a {budget / MiB:g} MiB budget "
                       + (f"(at 42 MiB the largest that played, {RUN_ERROR_256 / MiB:.2f}; one of 128.90 MiB fits no "
                          "tier of the heap and never loaded)" if ram == 256 else
                          f"(at 42 MiB the largest that kept a1, w1 and e2 whole, {RUN_ERROR_128 / MiB:.2f}, went above "
                          "64 MiB; one of 43.11 found no room there and never loaded)")
                       + up_hint)
            continue
        if b["kind"] == "game":
            raised = lines_for(ROOM, ram)[0]
            line = ((f"past the {b['limit'] / MiB:g} MiB a body may take of the game's {budget / MiB:g} MiB beside a "
                     "level loaded from a save and its menus" if ram == 64 else
                     f"past the {b['limit'] / MiB:g} MiB a body may take on {machine} at a {budget / MiB:g} MiB budget")
                    + (f" ({raised / MiB:g} MiB with qol_memory_budget at {ROOM // MiB})"
                       if budget < ROOM and b["value"] <= raised else "")
                    + up_hint
                    if b["level"] == "error" else f"past {b['warn'] / MiB:g} MiB, within {(b['limit'] - b['warn']) / MiB:g} "
                    f"MiB of the {b['limit'] / MiB:g} MiB line")
            out.append(f"  {b['level']}: {b['what']} {b['value'] / MiB:.2f} MiB, {line}")
            continue
        out.append(f"  {b['level']}: {b['what']} {b['value']}, past {'the format' if b['kind'] == 'format' else 'vanilla'}"
                   f"'s {b['limit']}")
    if report.get("normals_not_unit"):
        out.append(f"{report['normals_not_unit']} normals aren't unit")
    out.append(f"problems: {len(report['problems'])}")
    out += [f"  {p}" for p in report["problems"]]
    return out


__all__ = ["BAKE_MAX", "BUDGET", "DEFAULT_RAM", "EDGES", "EDGES_128", "EDGES_256", "OWN_ERROR", "OWN_ERROR_128",
           "OWN_ERROR_256", "OWN_WARNING", "OWN_WARNING_128", "OWN_WARNING_256", "PROJECTILE", "RAMS", "ROOM", "RUN",
           "RUN_ERROR_128",
           "RUN_ERROR_256", "UPPER256_PACK", "UPPER_PACKS", "VANILLA_MAX", "budget_of", "default_budget", "inspect",
           "lines", "lines_for", "lines_ram", "lod_line", "lod_runs", "own_runs", "own_words", "placed_species",
           "ram_packs", "run_line_for", "upper_of"]
