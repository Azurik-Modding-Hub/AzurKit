# C shims and kernel imports

> Ported from Azurik_Modkit's `docs/` (Step 4.11g) and rewritten for AzurKit's engine in Step 4.24d: Modkit's
> toolchain (zig at build time, `shim_builder`, `vanilla_symbols.py`, the hand-written headers, `AZURIK_NO_SHIMS`,
> the D1-extend stubs) isn't AzurKit's, and its history is the private archived repository (AGENTS.md § Porting
> from Modkit). AGENTS.md § Packs (its Shims and "Patching and shims: what binds") is AzurKit's rule and wins where
> the two differ; a `tests/test_*.py` or a module this checkout lacks names Modkit's tree, where a finding was made.

How to write, build and pin a patch that runs code of its own inside
Azurik's `default.xbe`: a C shim, prebuilt by shimkit, or a hand-written
one a pack's `custom_apply` carves. Which packs exist and what they do is
[`GUIDE.md`](GUIDE.md) § Patches and sliders and each pack's module in
`src/azurkit/tools/mods/packs/`; packs that edit `.xbr` files are
[`XBR_FORMAT.md`](XBR_FORMAT.md#packs-and-mods-files-that-edit-xbr-files);
reverse-engineering findings are in
[`RE_MOVEMENT.md`](RE_MOVEMENT.md), [`RE_DATA.md`](RE_DATA.md) and
[`RE_XBE.md`](RE_XBE.md).

The packs' C shims are `src/azurkit/tools/mods/shims/<name>.c`, each with
its prebuilt object `<name>.o` beside it: `qol_skip_logo`, `player_physics`
(the L3 speed toggle), `qol_photo_mode`, `qol_save_warp`, `qol_alloc_race`,
`enemy_scaling` and the four `qol_memory` shims (sharing
`qol_memory_heap.h`). `player_physics` also carves two hand-written shims
(the BLACK roll at VA 0x8C745 and the wing-flap ceiling at VA 0x89154,
§ Hand-written shims). The player-model swap, which isn't a pack, lands
its 40 shims from `src/azurkit/tools/characters/player_model/` (AGENTS.md
§ Characters). `xboxkrnl_resolver.c` is committed for kernel exports the
game doesn't import, which no shim calls yet (§ Kernel imports).

## When to write a shim

| Change | Use |
|---|---|
| Flip a byte, or NOP out an instruction, at a known VA | `PatchSpec` |
| Change one float constant or instruction operand | `ParametricPatch` (a slider) |
| Wrap or replace a function with your own logic | a C shim (`TrampolinePatch`) |
| Read or write a struct field conditionally | a C shim |
| Call a kernel API the game imports (`DbgPrint`, `NtClose`, …) | a C shim |
| Call a game function (`play_movie_fn`, …) | a C shim |
| Keep state across frames | a C shim: its `.data` / `.bss` land in `SHIMS`, marked writable (below; seen in game through the swap's X3, Step 2.21f) |
| Keep an x87 value on the FPU stack, or bake a slider into carved data | a hand-written shim (`custom_apply`: `Xbe.carve` and a `Hook`) |

A shim costs more up front (C source, a prebuilt object, a trampoline
declaration) but scales to any amount of logic; a byte patch doesn't.
All of these are in `src/azurkit/tools/mods/engine.py`.

## How a shim lands

1. The shim is a plain C function, compiled once by shimkit to an i386
   PE-COFF `.o` and committed beside its source.
2. The pack's `TrampolinePatch` names a site in the vanilla XBE (a USA
   address; its size and vanilla sha256 are the facts', at least 5 bytes,
   ending on an instruction boundary) and the shim's entry symbol.
3. At build time the engine:
   1. reads the object ([`core/coff.py`](../src/azurkit/core/coff.py));
   2. places each landable section (`.text`, `.rdata`, `.data`, `.bss`)
      where the carve allocator gives room
      ([`core/xbe.py`](../src/azurkit/core/xbe.py)'s `Carver`): in the
      gap before the section after `.text` (USA: 16 bytes before `BINK`)
      while it holds them, else in `SHIMS`, a section appended past the
      last (Europe: always), past every claim of the layers before it;
   3. resolves its DIR32 and REL32 relocations to its own symbols and the
      facts' game functions, and its kernel calls to stubs (§ Calling
      into the engine);
   4. writes its floats and tables (§ Per-apply float injection);
   5. writes a 5-byte `CALL rel32` (or `JMP rel32`) at the site and
      NOP-fills the rest.
4. Each placement is a claim of its layer, kept in the build's manifest;
   the header state the claims derive (`.text`'s sizes, the appended
   section) is laid down once, by `compose`, never by a layer.

What the pipeline guarantees (`tests/test_shims.py`):

- **No overlap.** A shim lands past every claim before it, its own
  layer's and earlier layers'; two layers' claims that meet are refused
  by name.
- **Alignment.** Each COFF section lands at the alignment its
  `IMAGE_SCN_ALIGN_*` bits declare, so ALIGN_16 SSE masks stay 16-byte
  aligned (AZ-019); a `.bss` lands as zeros of its declared size
  (AZ-018); metadata sections (`.debug$S`, `.llvm_addrsig`, `.drectve`,
  …) are dropped.
- **Writable data.** A shim's `.data` and `.bss` land only in `SHIMS`,
  which then carries the WRITABLE bit (flags 0x7, as `.data` and the
  library code sections `D3D`, `DSOUND`, `XGRPH`, `D3DX` and `XPP`); a
  `SHIMS` of code and constants keeps 0x6 (EXECUTABLE, PRELOAD) (AZ-220).
  `.text` keeps vanilla's 0x36 and never takes writable bytes: in game,
  paging is on with CR0.WP set, so a store into a read-only page faults
  [inferred; `RE_XBE.md` § "CPU state in game"]. The swap's X3
  (`player_model/damage_marker.c`) was the first shim to write its own
  data: each PlayerControl tick it rewrites the 0x34-byte damage marker in
  its `.data` [verified xemu, 2026-10-12: sitting modelswap, the flicken
  player's critter+0x218 read X3's marker and its attacks dealt damage],
  so a check of a running guest's code leaves such data out (AZ-300).
- **Data off code.** Each writable landing has 64 zero bytes before and
  after it (`core/xbe.py`'s `CODE_GAP`), so no code lands within 64 bytes
  of a shim's data (Step X.70): xemu keeps translated code by 64-byte
  line and throws a line's code away at every store into it, and the
  l256_120 build once stored into lines of translated code about 260
  times a second in w1.
- **All or nothing (D35).** A relocation that can't resolve, a symbol the
  object lacks or a site that doesn't hold its vanilla bytes fails the
  build, naming the pack and the site; nothing is written.
- **Each hook its own copy.** A pack with several hooks of one shim lands
  one copy a hook, so two hooks share no `static` data (§ One state for
  several hooks).

## The toolchain

[`shimkit`](../shimkit/__init__.py) (dev only) builds every object with
`zig cc` from the pinned `ziglang` wheel (0.16.0, the dev group), the same
on macOS, Linux and Windows: no host compiler, no NXDK, no linker, no CRT.
`FLAGS` lists each flag with its reason (Modkit's, so the objects match
its records): it targets the Xbox's Pentium III (`-mcpu=pentium3`: MMX and
SSE, no SSE2), so `float` may use scalar SSE and `double` lowers to x87;
the compiler never emits SSE2, which xemu runs but real hardware faults on
(AZ-021). Anything a shim needs from outside comes in as an undefined
external the layout resolves, never from a runtime library.

```bash
uv run --locked python -m shimkit                 # build every object (after editing a source)
uv run --locked python -m shimkit --check         # exit 1 when an object isn't its source's build
uv run --locked python -m shimkit --headers DIR   # write the headers a shim includes, to read them
uv run --locked python -m devkit re shim-inspect qol_skip_logo   # sections, symbols, relocations, calls
```

No host compiles a shim at build time: neither the site nor the app needs
zig (AZ-045). `tests/goldens/shims.json` (G2) pins each object's
normalized sha256, the same on every host, and `tests/test_shims.py` holds
every object to its source's build.

A shim includes only what shimkit writes from the facts at every compile,
or a header of its own beside it (`qol_memory_heap.h`): `azurik_vanilla.h`
(each facts function's name, convention and argument bytes, typed where
`TYPES` types it, with the types, the active pad's record and the
parameter macros), `azurik_kernel.h` (the facts' kernel exports) and an
`azurik.h` for the macros. Nothing vendored reaches a shim (AZ-099, Q85).
Modkit's struct header lives on as `devkit/re/data/structs.h` and
`anchors.toml` (the RE data, compiled with shimkit's flags in
`tests/test_re_xbe.py`); a shim names the fields it reads itself.

## Writing a C shim pack

### Step 1: scaffold it

```bash
uv run --locked python -m devkit re new-shim my_feature --hook 0x8A095
```

It writes `src/azurkit/tools/mods/packs/my_feature.py` (its `PACK`, one
`TrampolinePatch` at the hook) and `src/azurkit/tools/mods/shims/my_feature.c`
(the entry `c_my_feature` with the ABI the hook needs: a live Ghidra's with
`--ghidra`, else the facts' when the hook replaces a call to a game
function they know, else a `stdcall` `void(void)` guess), runs
`plan-trampoline` on the site, and prints what is left to do by hand
(`devkit/re/README.md` § Shim authoring). The name is a lowercase C
identifier; an existing pack, shim or file refuses it.

### Step 2: write the C body

```c
#include "azurik_vanilla.h"

__attribute__((stdcall))
void c_my_feature(void *player) {
    /* read and write the fields your hook needs; name each offset you use */
}
```

- Match the replaced call's convention exactly: a site that replaces a
  `CALL` to a `__stdcall` function needs a `__stdcall` shim, or the
  stack pops don't match and the game crashes. Keep the callee's
  `ret N` and return registers (a NOP'd stdcall `CALL` once gave a black
  screen).
- The return type matters only when the caller inspects it; most
  boot-state functions return a byte in `AL`.
- An offset you name: verify it in Ghidra first (a lookup of the
  config-key string before the write); `devkit/re/data/structs.h` holds
  the ones already verified.

### Step 3: build and inspect

`uv run --locked python -m shimkit`, then `python -m devkit re shim-inspect
my_feature`:

- the entry symbol the pack declares (`_c_my_feature@4` here);
- no unexpected externals: a struct assignment can make the compiler
  emit a `_memcpy` call the layout can't resolve (copy field by field).

### Step 4: the pack

```python
from azurkit.tools.mods.engine import Pack, TrampolinePatch

PACK = Pack(
    name="my_feature",
    description="<what a player sees on the Patches tab>",
    sites=(TrampolinePatch(label="the call it replaces", va=0x0008A095, shim="my_feature",
                           symbol="_c_my_feature@4"),),   # mode="jmp" for a jump
)
```

**`symbol`** is matched exactly against the COFF symbol table, so it is
the compiler's `i386-pc-win32` mangling of the entry. The `@N` suffix is
the total argument bytes, not the argument count:

| Convention | C entry point | COFF symbol |
|---|---|---|
| cdecl | `void c_f(void)` | `_c_f` |
| stdcall | `__attribute__((stdcall)) void c_f(void)` | `_c_f@0` |
| stdcall | `__attribute__((stdcall)) void c_f(int *p)` | `_c_f@4` |
| fastcall | `__attribute__((fastcall)) void c_f(int a)` | `@c_f@4` |

**The site:** `python -m devkit re plan-trampoline 0x8A095` decodes it,
picks the smallest byte count that fits the 5-byte jump and ends on an
instruction boundary, and flags what the shim must preserve. Its decoder
knows a limited opcode set (with the ModR/M forms: 0x85700 plans as 7
bytes): a site it can't decode plans as "unknown" and exits 1, so read
those bytes in Ghidra or with `python -m devkit re xbe dis`. The site's
address and size go into the facts by hand (Step 6); a build refuses a
site that doesn't hold its vanilla bytes.

**An indirect call** (`call [edx+0xCC]`, a vtable slot): simulator L1
(`devkit/sim/l1.py`) checks a call-replacing shim returns with its
callee's `RET N`, and can't know an indirect callee's, so it refuses that
hook. Take the inline block instead, its argument pushes and `this` load
with the call (`push eax; mov ecx, ebp; call [edx+0xCC]` at 0x548E3 in
`qol_photo_mode`): the shim makes the call itself and returns with a
plain `RET`, as the inline code it replaced.

### Step 5: register it

Add the module's `PACK` to `PACKS` in `src/azurkit/tools/mods/__init__.py`
(nothing discovers packs). It then shows on the Patches tab, in
`azurkit packs` and in `azurkit build --pack my_feature`.

### Step 6: pin it (facts, goldens, Europe)

A pack owes no byte test of its own (D57); what pins it:

- **The facts:** its site's address and size in
  `src/azurkit/core/facts.usa.json`, by hand, then `uv run --locked python
  scripts/gen_facts.py` fills in its vanilla sha256 (`--check` writes
  nothing). `tests/test_packs.py` holds the files to it and each case's
  bytes to the facts' sites.
- **The goldens:** its cases in `tests/goldens/cases.json` and
  `uv run --locked python scripts/record_goldens.py packs.json sites.json
  shims.json` (G1, the sites, G2; the Europe goldens too when the pack
  lists Europe). The commit names each golden and why (AGENTS.md § The
  goldens).
- **Europe:** the site's Europe address in `facts.europe.json`'s map, or a
  named absence; `python -m devkit re region-map check` checks the map on
  both images, and `tests/test_re_shims.py` fails while a Europe pack
  writes an address the map lacks or a shim fixes an address of the image
  (§ Both releases).
- **Its behaviour:** the simulator (`devkit/sim`: L1 checks the patched
  code is well-formed for a Pentium III, L2 runs the game's own code under
  Unicorn; `tests/test_simulator.py`) and once in xemu (Step 8).

`python -m devkit re test-for-va my_feature --run` runs the tests that
name its address or pack.

### Step 7: run the tests

```bash
uv run --locked pytest -q tests/test_packs.py tests/test_shims.py tests/test_re_shims.py tests/test_builds.py
```

### Step 8: see it in xemu

The tests prove the bytes; only the game proves the behaviour. Build from
the vanilla image with only this pack, into a new folder:

```bash
uv run --locked azurkit build --iso <vanilla image> --out "$(mktemp -d)/my_feature.iso" --no-defaults --pack my_feature
```

The `azurik-xemu-oracle` skill has the sandboxed sitting. A black screen
or an instant crash: check in Ghidra that the site isn't mid-instruction,
then add a `DbgPrint` to the shim to see whether it runs at all.

## Calling into the engine

| Call | Path | Cost |
|---|---|---|
| A game function (`play_movie_fn`, `entity_lookup`, …) | the facts' `functions`, declared in `azurik_vanilla.h` | a direct `CALL`, no stub |
| D3D8 / DirectSound / XGraphics / XAPI | the same: they are statically linked into `.text` (the facts' `D3D*`, `XG*`, DirectSound and XAPI functions) | a direct `CALL`; no SDK types (D2) |
| A kernel function the game imports (`DbgPrint`, `NtClose`, `KeQueryPerformanceCounter`, …) | the facts' `kernel`, declared in `azurik_kernel.h` | one indirect jump |
| Any other kernel export | refused by name (§ Kernel imports) | |

### Game functions

The layout resolves an undefined COFF symbol against the facts'
`functions` (`src/azurkit/core/facts.usa.json`, Europe's addresses from
its map), so a `REL32`/`DIR32` relocation lands straight on the game's
address: no thunk. Each one's notes, what it does and what a shim calling
it must know, are `devkit/re/data/function_notes.toml`.

```c
#include "azurik_vanilla.h"

__attribute__((stdcall))
int c_override_boot_movie(const char *requested_movie, char flag) {
    return play_movie_fn("CustomBoot.bik", flag);   /* lands on the game's address */
}
```

To add one (AGENTS.md § Packs, "Keep the callee's contract"):

1. **Confirm it:** its address, its convention and its stack argument
   bytes, at the callee's `RET N` (stdcall and thiscall) or its callers'
   `ADD ESP, N` (cdecl) at two or more call sites
   (`python -m devkit re xbe fn | calls --to`, Ghidra); `MOV ECX, …; MOV
   EDX, …; CALL` is fastcall. An input in EAX, ESI or EDI needs shimkit's
   asm thunk (`THUNKS`), checked by eye at the call sites.
2. **Add it** to the facts' `functions` (its name, address, convention and
   argument bytes), with its Europe address or a named absence, and its
   note in `function_notes.toml`; then `scripts/gen_facts.py`. The commit
   body cites the address and `N`.
3. **Run the guards:** `tests/test_shims.py` checks each facts function
   starts a function in its release's code (the prologue guard: a failure
   means a mid-function address; fix it, never `PROLOGUE_FIRST_BYTES`) and
   pops what its declared ABI makes its caller push (AZ-108), and that a
   shim built against the header lands each call at its facts address;
   `tests/test_re_xbe.py` holds the notes to the facts' names.

Add functions when a shim needs them, not speculatively.
`gravity_integrate_raw` (0x85700) is `__fastcall` with an MSVC
return-value pointer, which a C call can't express (`RE_XBE.md`
"Handling MSVC-RVO ABIs").

### Kernel imports

**The 151 static imports.** Azurik's thunk table at VA 0x18F3A0 holds 151
xboxkrnl imports (USA; Europe's two more, ordinals 46 and 354, AZ-328),
each a 4-byte slot the Xbox loader fills before the game starts; the
facts' `kernel` lists the ones shims use. A shim's kernel function lands
as a 6-byte `JMP [thunk_slot]` stub, one a pack, and its `CALL` lands on
the stub; a kernel variable (`KeTickCount`, `XboxHardwareInfo`, …) is
declared as an import and read through its slot, no stub:
`ULONG t = KeTickCount;`.

```c
#include "azurik_kernel.h"

__attribute__((stdcall))
void c_frame_time_probe(void) {
    unsigned long long now = KeQueryPerformanceCounter();
    DbgPrint("frame tick: %u\n", (unsigned)now);
}
```

`KeQueryPerformanceCounter` takes no arguments and returns a
`ULONGLONG`; read the header's prototypes rather than assuming Win32
shapes.

**Every other export** (the 215 retail exports the game doesn't import)
has no thunk slot, and AzurKit refuses a call to one by name. Modkit
reached them through a runtime resolver (its D1-extend: a 37-byte stub a
call that walked `xboxkrnl.exe`'s PE export table at the retail base
`0x80010000` once and cached the address; no extended import was ever
seen working in game). AzurKit keeps the resolver's source
([`xboxkrnl_resolver.c`](../src/azurkit/tools/mods/shims/xboxkrnl_resolver.c),
its object beside it) but not the stubs that would call it, until a shim
needs one.

### One state for several hooks: a door

Each hook lands its own copy of its shim, so two hooks of one shim share
no `static` data. Where they must, one hook can be a `jmp`
`TrampolinePatch` at a game function no code calls (check `python -m
devkit re xbe calls --to`, `find-refs --va` and `--data`, `insns
--mnemonic jmp --operand`): that address is then a fixed door into the
one landing that holds the state. Add it to the facts' functions with the
ABI the shim gives it, and have the other hooks (and any in-place
`PatchSpec`) call the door with an op in a register. `qol_alloc_race`'s
copy gate (AZ-817) does this at 0xA66C0.

## Per-apply float injection

A slider that reaches into a compiled shim overwrites 4 bytes of the
shim's `.rdata` as each copy lands, so the object is built once and each
build threads its own value through.

```c
#include "azurik_vanilla.h"

AZURIK_FLOAT_PARAM(gravity_scale, 1.0f);    /* volatile const float in .rdata */

void __attribute__((used)) c_my_shim(void) {
    float g = gravity_scale;                /* a DIR32 load, never folded */
    /* ... */
}
```

`volatile` defeats constant folding, `const` keeps the shim's own code
from writing it, `used` keeps it from dead-code elimination and
`section(".rdata")` pins the layout. On the pack's side, list it on the
`TrampolinePatch`: `floats=(FloatParam("gravity_scale", "_gravity_scale"),)`,
`name` the slider whose value it takes and `symbol` the mangled C name.
The values follow the slider rule (D23): NaN and infinity are refused by
name, and a value past float32's range is written as the infinity it
saturates to, with a note in the build's report (Q110). A declared param
the body never reads is optimised away, and a symbol the landed sections
lack fails the build (D35). Use a `ParametricPatch` to rewrite bytes at a
game address (an instruction operand or a `.rdata` float the game reads);
use a `FloatParam` when the value needs shim-side logic.

A byte table takes the same path (Step 2.71): `AZURIK_BYTES_PARAM(name,
size)` declares a `volatile const unsigned char name[size]` of zeros in
`.rdata`, and `BytesParam(name, symbol, size)` in the patch's `tables`
writes the pack's bytes over it, zero-filled to `size`. `player_physics`'s
speed toggle reads its table this way, and the swap's sounds shim
(`src/azurkit/tools/characters/player_model/sounds.c`, X14) its per-slot
table.

## Hand-written shims

A pack's `custom_apply` may carve bytes of its own (`Xbe.carve`: a float a
rewritten load reads, a shim's machine code with its data), hook a site to
them (`Hook`, a `CALL` or `JMP` rel32) and write a span its footprint
declares. Choose it over C when the hook interrupts an x87 computation and
must keep or consume `ST(0..n)` exactly, when the shim calls a
`__thiscall` function with stack arguments already pushed on the caller's
frame, or when the slider's value is baked into a carved data slot (a
`scale * scale * 2g`, say). Choose C for ordinary logic calling game
functions with cdecl or stdcall arguments, for late-bound floats, and
whenever you want the compiler to allocate registers.

`player_physics` holds both live examples (`_hand` in
`src/azurkit/tools/mods/packs/player_physics.py`): the roll shim (hook
0x8C745, a `CALL`, a 36-byte body) and the wing-flap ceiling shim (hook
0x89154, the `FADD` that feeds the `peak_z` latch, a 15-byte body). Each
carves its data (the scale's float) and then its body, built from the
carved addresses; the body's absolute addresses (`abs32`) and rel32
branches (`rel32`) into the image are declared, so a Europe build moves
them through the map.

**Byte-correct at the hook is not upstream of the mechanic.** Five of
Modkit's hand-assembled packs landed their bytes cleanly and changed
nothing in game; its Step 1.10 (D18) deleted them (§ History). Check that
the hook runs upstream of the state that drives the visible mechanic, and
that the slider reaches the pack; the `azurik-game-reference` skill
catalogues those no-effect patches.

## Both releases

A pack's sites and every address it writes are USA addresses; Europe's
come from `facts.europe.json`'s address map (each site's Europe address,
or a named absence). A C shim's calls to game functions resolve to each
release's facts address, but nothing moves a constant in its C: a fixed
address (a cast `0x...`) reads USA's on Europe. A shim of a pack that
lists Europe reads game data through a facts function or its hook's
arguments (`qol_save_warp` reads the pad through
`active_controller_state`); `tests/test_re_shims.py` fails while a shim
fixes an address of the image, or a pack writes an address the map lacks.

## Pitfalls and debugging

| Symptom | Cause | Fix |
|---|---|---|
| The game crashes soon after the shim returns, or later calls get garbage arguments | the shim's convention doesn't match the call it replaced, so the stack is popped too much or too little | read the call site: `ADD ESP, N` after the call is cdecl (no `stdcall` on the shim); none is stdcall (`__attribute__((stdcall))`) |
| The shim reads or writes the wrong field | a wrong offset | verify it in Ghidra; `devkit/re/data/structs.h` holds the verified ones |
| A typed call mangles to a name the layout refuses | the prototype doesn't match the facts' argument bytes | recount the argument bytes (a `BOOLEAN` takes 4 on the stack; a pointer is 4); recheck cdecl vs stdcall at the call site |
| A facts function fails the prologue or `RET N` guard | a mid-function address, or the wrong convention or argument bytes | fix the address or the ABI in the facts, never the guard |
| The object has no landable sections | the compiler removed an entry point it saw as unused | mark it `__attribute__((used))` |
| The build names a symbol the object lacks | `symbol` isn't the mangled name | a no-argument stdcall entry is `_c_<name>@0`; `shim-inspect` prints the table |
| The build names a site that doesn't hold its vanilla bytes | the address or size is wrong, or the input isn't vanilla | check the facts' site with `python -m devkit re xbe dis`; builds start from vanilla (D27) |
| `shimkit --check` fails | the object isn't its source's build | run `python -m shimkit` and commit both |

When a shim misbehaves, in order: run its tests with `-v` and read the
assertion; inspect the object (`shim-inspect`): is the entry symbol
right, do the relocations look sane?; build it alone from the vanilla
image and read the patched XBE (`python -m devkit builds verify-patches`,
`python -m devkit re xbe dis` at the site and the landing); boot it in
xemu with a `DbgPrint` in the shim.

## Limitations

- **No SDK types (D2).** D3D8, DirectSound, XGraphics and XAPI are
  ordinary game functions (above), called through flat `stdcall`
  externs; NXDK's real headers, structs and vtables aren't wired in, and
  no shim has needed them.
- **No kernel export the game doesn't import** (§ Kernel imports).
- **No shared shim library:** each hook lands its own copy; a door
  (above) shares state.

## History

**Merged docs.** Modkit's Step 3.3c merged its shim authoring guide
(`SHIM_AUTHORING.md`) and the live parts of the D1-extend design note into
this file; Step 4.24d rewrote it for AzurKit's engine (prebuilt objects,
the facts' functions and kernel, the carve allocator's claims).

**Platform tiers.** Modkit's Phase 1 shipped one proof-of-concept shim,
`qol_skip_logo`, behaviourally identical to the 10-NOP patch it replaced;
Phase 2 shipped the rest:

| ID | Tier | Status in AzurKit |
|---|---|---|
| A1 | an appended section (unbounded shim size) | `SHIMS`, the carve allocator |
| A2 | relocation-aware COFF loader | `core/coff.py` |
| A3 | game-function calls (registry plus layout resolution) | the facts' `functions` |
| B1 | named structs with drift asserts | `devkit/re/data/structs.h` (RE data) |
| B2 | a Unicorn harness for shims | the simulator, `devkit/sim` |
| B3 | scaffolding | `python -m devkit re new-shim` |
| C1 | player-speed shim (the motivating deliverable) | `player_physics` |
| D1 | xboxkrnl imports through thunk-table stubs | the facts' `kernel` |
| D1-extend | runtime resolver for every other export | the resolver's source only; calls refused |
| D2 | NXDK (real Xbox SDK headers) | not started |
| E | shared-library shim layout | not ported |

Ideas never started: skip `prophecy.bik` with a second C shim at the boot
state machine's prophecy state, and a camera distance / FOV patch (likely
a `ParametricPatch` on a `.rdata` float).

**The deleted hand-assembled packs.** Modkit's rounds 7–8 shipped four
hand-assembled shims (`flap_at_peak`, `root_motion_roll`,
`root_motion_climb`, `slope_slide_speed`) that landed their bytes and
appeared to do nothing in game. Round 10 withdrew them as hooked too late,
a diagnosis confounded with a GUI bug (only `player_physics`'s parameters
reached the build, so every other pack applied at 1.0); round 11.8
restored them, round 11.13 testing again saw no effect, and Step 1.10
(D18) deleted them with `animation_root_motion_scale` (a 38-byte vtable
hook). They remain readable as patterns in Modkit's history.
