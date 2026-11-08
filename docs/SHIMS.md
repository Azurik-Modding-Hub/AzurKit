# C shims and kernel imports

> Ported from Azurik_Modkit's `docs/` (Step 4.11g). A path under `azurik_mod/`, `scripts/`, `tests/` or
> `shims/`, and a link to a doc this folder lacks, names Modkit's tree, where the finding was made.
> So do its commands (`azurik-mod`, `bootstrap.py --with re`), its environment variables and its "this repo" and
> "today" claims: AGENTS.md is AzurKit's rule and wins where the two differ.
> The toolchain this guide describes (zig compiling at build time, `shim_builder`, `vanilla_symbols.py`, the
> hand-written headers, `AZURIK_NO_SHIMS`) is Modkit's and isn't ported: AGENTS.md § Shims is AzurKit's rule
> (11 C shims in `src/azurkit/tools/mods/shims/`, source and object both committed) and wins where the two differ.
> AzurKit's `new-shim`, `plan-trampoline`, `shim-inspect`, `test-for-va` and `region_map.py` are
> `python -m devkit re new-shim | plan-trampoline | shim-inspect | test-for-va | region-map` (`devkit/re/README.md`).

How to write, build and pin a patch that runs code of its own inside
Azurik's `default.xbe`: a C shim compiled by zig, or a shim
hand-assembled in Python. Which packs exist and what they do is
[`PATCHES.md`](PATCHES.md); packs that edit `.xbr` files are
[`XBR_PACKS.md`](XBR_PACKS.md); reverse-engineering findings are in
[`RE_MOVEMENT.md`](RE_MOVEMENT.md), [`RE_DATA.md`](RE_DATA.md) and
[`RE_XBE.md`](RE_XBE.md). This file absorbed the shim authoring
guide and the D1-extend design note in REORG_PLAN Step 3.3c.

Two packs run code of their own today: `qol_skip_logo` (a compiled
`shim.c`, the one pack C shim, tagged `c-shim`) and `player_physics` (two
hand-assembled `shim_builder` shims: the BLACK roll at VA 0x8C745 and
the wing-flap ceiling at VA 0x89154). The player-model swap, which isn't
a pack, installs its own C shims from `azurik_mod/patches/player_model/`
(its `README.md`; X4's `roll.c` since Step 2.21b, X3's `damage_marker.c`
since Step 2.21c, X7's `hit_reaction.c` since Step 2.21d) with
`apply_trampoline_patch`.

## When to write a shim

| Change | Use |
|---|---|
| Flip a byte, or NOP out an instruction, at a known VA | `PatchSpec` |
| Change one float constant or instruction operand | `ParametricPatch` |
| Wrap or replace a function with your own logic | shim |
| Read or write a struct field conditionally | shim |
| Call a kernel API (`DbgPrint`, `NtOpenFile`, …) | shim |
| Call a vanilla Azurik function (`play_movie_fn`, …) | shim |
| Keep state across frames | shim: its `.data` / `.bss` land in `SHIMS`, marked writable (below; seen in game through X3, Step 2.21f) |

A shim costs more up front (C source, a compile step, a trampoline
declaration) but scales to any amount of logic; a byte patch doesn't.

## How a shim lands

1. The shim is a plain C function compiled to an i386 PE-COFF `.o`.
2. The pack's `TrampolinePatch` names a site in the vanilla XBE (at
   least 5 bytes, ending on an instruction boundary) and the shim's
   entry symbol.
3. At apply time `apply_trampoline_patch`
   ([`apply.py`](../azurik_mod/patching/apply.py)):
   1. parses the `.o` ([`coff.py`](../azurik_mod/patching/coff.py),
      `parse_coff`);
   2. lands every landable section (`.text`, `.rdata`, `.data`, `.bss`)
      through `carve_shim_landing`: it grows `.text` into the VA gap
      before the next section (`find_text_padding`, `grow_text_section`
      in [`xbe.py`](../azurik_mod/patching/xbe.py); Azurik has 16 bytes
      before `BINK`), and past that spills into an appended `SHIMS`
      section (`append_xbe_section`) or extends the one an earlier
      landing appended (`_extend_appended_section`). A `.data` or
      `.bss` skips the `.text` gap and lands in `SHIMS`, which then
      carries WRITABLE (AZ-220);
   3. resolves every undefined external: vanilla Azurik functions,
      kernel imports and shared-library symbols (§ Calling into the
      engine);
   4. applies the COFF relocations (`layout_coff`);
   5. writes a 5-byte `CALL rel32` (or `JMP rel32`) at the site and
      NOP-fills the rest of `replaced_bytes`.
4. The Xbox loader maps the grown sections, and the shim runs like
   hand-written assembly.

Facts the pipeline guarantees:

- **No state outside the XBE.** Every landing grows `.text` (or
  `SHIMS`) past itself, and the next one starts at the section's end as
  the header records it, so a later apply never overwrites an earlier
  shim, on the same buffer, a copy, or a file another process wrote
  (AZ-001).
- **Alignment.** Each COFF section lands at the alignment its
  `IMAGE_SCN_ALIGN_*` bits declare (zero-padded), so ALIGN_16 SSE masks
  stay 16-byte aligned (AZ-019). A `.bss` lands as zeros of its
  declared size (AZ-018). Metadata sections (`.debug$S`,
  `.llvm_addrsig`, `.drectve`, …) are dropped.
- **Unbounded size.** Appending `SHIMS` grows the section-header array
  in place: every byte after it shifts forward by 56 and every image
  header pointer that moved is rewritten. Azurik has about 880 bytes of
  header headroom (VA and on disk) for that one-time growth; the section
  itself has no cap.
- **All or nothing.** If a relocation-aware apply fails (an unresolved
  extern, a rel32 overflow), the XBE is restored byte for byte before
  `apply_trampoline_patch` returns `False` (AZ-023), and `apply_pack`
  fails the build naming the pack and site (D35).
- **Writable data.** A shim's `.data` and `.bss` land only in
  `SHIMS`, and `SHIMS` then carries the WRITABLE bit 0x1 that `.data`
  and the library code sections `D3D`, `DSOUND`, `XGRPH`, `D3DX` and
  `XPP` carry (0x7); a `SHIMS` holding code and constants only keeps
  0x6 (EXECUTABLE, PRELOAD) (AZ-220, Step 2.19e). The grown `.text`
  keeps vanilla's flags 0x36 (PRELOAD 0x2, EXECUTABLE 0x4, and 0x30,
  the head and tail page read-only bits of the XBE format), so no
  `.data` or `.bss` lands there [verified 2026-10-11: `azurik-mod xbe
  sections` on a build of a shim with a 4-byte `.data` and a 4-byte
  `.bss`: `SHIMS` 0x2C bytes, flags 0x7, `.text` not grown; pin
  `tests/test_coff_relocations.py::CoffBssLanding::test_a_shim_with_bss_lands_it_in_a_writable_section`].
  Until Step 2.21c no shipped shim wrote its own data (`qol_skip_logo`'s
  `shim.c` has no statics, the player model's X4 `roll.c` only reads its
  constants, and the `player_physics` hand shims only read theirs), so no
  shipped build changed. The player-model swap's
  X3 (`azurik_mod/patches/player_model/damage_marker.c`) is the first:
  each PlayerControl tick it rewrites the 0x34-byte damage marker in its
  `.data` [verified 2026-10-12: a flicken build's `SHIMS` (X4, then X3)
  has flags 0x7 and the marker at VA 0x39F2F8]. In game the write works
  [verified xemu, 2026-10-12: sitting modelswap's REPORT §1 and row 6]:
  the flicken player's critter+0x218 read 0x39F2F8, X3's marker, and
  its attacks dealt damage, which needs the active value X3 writes into
  that marker; its `SHIMS` in RAM differed from the build's in 13
  bytes, most likely those writes [inferred]. Before the fix such data landed in the
  grown `.text` or in a `SHIMS` without WRITABLE; in game paging is on
  with CR0.WP set, so a write to a page mapped read-only would fault
  [inferred; `RE_XBE.md` § "CPU state in game"]. A later flicken
  build's 13 differing `SHIMS` bytes were all inside the marker
  [verified xemu, 2026-10-12: sitting sight222's REPORT, finding 1], so
  a code check of a running guest must leave such data out:
  `apply.trampoline_shim_data` reads where a hooked shim's `.data` and
  `.bss` landed from the build (the hook's CALL and the shim's
  relocations), and the xemu harness's check skips those bytes (AZ-300,
  Step 2.22j).
- **Data off code.** Each writable landing in `SHIMS` has 64 zero bytes
  before and after it (`apply.CODE_GAP`), so no code lands within 64
  bytes of a shim's `.data` or `.bss` (Step X.70). xemu keeps translated
  code by 64-byte line and throws a line's code away at every store into
  it, and each shim's data used to land right after its `.text`, with
  the next shim's `.text` right after that: the xemu fork measured the
  l256_120 build storing into lines of translated code about 260 times a
  second in w1's run_stop (2,045 and 585 stores into two lines in 600
  vblanks, vanilla 14; about 0.5 ms of vCPU a flip, under icount too:
  its answer on FRAME-8bffffeb0243). Pin
  `tests/test_coff_relocations.py::CoffBssLanding::test_no_writable_shim_data_lands_within_64_bytes_of_code`.
  A build with no writable shim data (the default packs') is unchanged.

## Toolchain

[`shim_toolchain.py`](../azurik_mod/patching/shim_toolchain.py) runs
`zig cc` from the pinned `ziglang` wheel (`uv sync` installs it with the
`dev` group), the same on macOS, Linux and Windows: no bash, no host
clang, no NXDK, no linker, no CRT, and no fallback to another compiler.
Its `SHIM_CFLAGS` lists each flag with its reason. It targets the
Xbox's Pentium III (`-mcpu=pentium3`: MMX and SSE, no SSE2), so `float`
may use scalar SSE and `double` lowers to x87; the compiler never emits
SSE2, which xemu runs but real hardware faults on (AZ-021). Anything a
shim needs from outside comes in as an undefined external that the
layout pass resolves (§ Calling into the engine), never from a runtime
library. A missing compiler or a compile error fails the build and
every test that compiles the source (Q17). zig caches in
`.tools/zig-cache` unless zig's own `ZIG_GLOBAL_CACHE_DIR` /
`ZIG_LOCAL_CACHE_DIR` are set.

`apply_trampoline_patch` compiles a pack's `shim.c` itself when its
`.o` is missing or older than the source (mtime), and a failed rebuild
fails the site rather than land a stale object. The D1-extend kernel
resolver (`shims/shared/xboxkrnl_resolver.c`) is built by the same
policy (`azurik_mod.patching.apply.shim_object_error`, AZ-209). Three
variables steer it:

- `AZURIK_SHIM_FORCE_REBUILD=1` rebuilds every time;
- `AZURIK_SHIM_NO_AUTOCOMPILE=1` never compiles, for bit-for-bit runs
  from an existing local `.o` (objects are never committed:
  `shims/build/` is gitignored);
- `AZURIK_SHIM_BUILD_DIR` moves the object cache out of `shims/build/`;
  the test suite points it at a temp dir, so the tests leave
  `shims/build/` alone.

Objects are keyed by pack name (`shims/build/<pack>.o`), so two packs
whose sources are both `shim.c` can't collide. By hand:

```bash
uv run python -m azurik_mod.patching.shim_toolchain \
  azurik_mod/patches/qol_skip_logo/shim.c shims/build/qol_skip_logo.o
uv run azurik-mod shim-inspect shims/build/qol_skip_logo.o   # sections, symbols, relocations
```

Verified with `ziglang==0.16.0` (zig 0.16.0, LLVM 21.1.0): for all 9
shim sources its objects match what Apple clang 21 built with the same
flags before Step 1.28, once normalized (`tests/_coff_normalize.py`;
2026-10-09). `tests/goldens/shims.json` pins the normalized hash of
every shipped shim object, the same on every host.

## Writing a C shim pack

### Step 1: scaffold the feature folder

```bash
uv run azurik-mod new-shim my_feature --hook 0x8A095 --xbe default.xbe
# creates azurik_mod/patches/my_feature/__init__.py, shim.c and README.md
```

| Flag | Effect |
|---|---|
| `--hook VA` with `--xbe` / `--iso` | runs `plan-trampoline` and pre-fills `replaced_bytes` from the vanilla XBE |
| `--ghidra` (`--port`) | takes the hook function's calling convention from a live Ghidra and picks the matching `__attribute__(())` |
| `--category` | the category the feature registers under (default `other`) |
| `--dry-run` | prints the files instead of writing them |

The name must be a lowercase C identifier (`[a-z][a-z0-9_]*`; a leading
underscore is rejected), and the scaffold refuses to overwrite an
existing folder. `shim.c` starts with the `__attribute__((stdcall))`
entry point and the two common includes (`azurik.h`,
`azurik_vanilla.h`); add `azurik_kernel.h` for kernel calls. One folder
holds everything, so deleting the feature later means deleting the
folder:

```
azurik_mod/patches/my_feature/
  __init__.py   Feature(...) declaration, TrampolinePatch, apply helper
  shim.c        the C source
  README.md     per-feature notes
```

### Step 2: write the C body

Prefer the named fields in [`azurik.h`](../shims/include/azurik.h) over
raw `[reg + 0xNN]` offsets: its `_Static_assert`s catch struct drift at
compile time.

```c
#include "azurik.h"
#include "azurik_vanilla.h"

__attribute__((stdcall))
void c_my_feature(PlayerInputState *p) {
    if (p->flags & PLAYER_FLAG_RUNNING) {
        p->magnitude *= 1.5f;
    }
}
```

- Match the replaced call's convention exactly. A site that replaces a
  `CALL` to a `__stdcall` function needs a `__stdcall` shim, or the
  stack pops don't match and the game crashes.
- The return type matters only when the caller inspects it; most
  boot-state functions return a byte in `AL`.

### Step 3: compile and inspect

Compile as in § Toolchain, then check the `shim-inspect` output (or
`objdump -d`):

- the entry symbol you will declare (`_c_my_feature@4` here);
- no unexpected externals: a struct assignment can make clang emit a
  `_memcpy` call the layout pass can't resolve (copy per field
  instead).

### Step 4: fill in `__init__.py`

Replace the scaffold's TODOs with values from Ghidra:

```python
MY_FEATURE_TRAMPOLINE = TrampolinePatch(
    name="my_feature",
    label="Short human-readable description",
    va=0x00087654,                        # the site in the vanilla XBE
    replaced_bytes=bytes.fromhex(         # the exact bytes overwritten
        "E8 12 34 56 78 90 90 90 90 90"),
    shim_object=_SHIM.object_path("my_feature", _REPO_ROOT),
    shim_symbol="_c_my_feature@4",
    mode="call",                          # or "jmp"
)
```

`_SHIM = ShimSource(folder=_HERE, stem="shim")` is the scaffold's
helper; `object_path` puts the `.o` in the shared build cache.

**`shim_symbol`** is matched exactly against the COFF symbol table, so
it must be clang's `i386-pc-win32` mangling of the entry point. The
`@N` suffix is the total argument bytes, not the argument count:

| Convention | C entry point | COFF symbol |
|---|---|---|
| cdecl | `void c_f(void)` | `_c_f` |
| stdcall | `__attribute__((stdcall)) void c_f(void)` | `_c_f@0` |
| stdcall | `__attribute__((stdcall)) void c_f(int *p)` | `_c_f@4` |
| fastcall | `__attribute__((fastcall)) void c_f(int a)` | `@c_f@4` |

The scaffold writes a bare `"_c_<name>"` next to its stdcall prototype,
so add the `@N` by hand, or apply fails with `symbol '_c_<name>' not
found in COFF file`.

**`replaced_bytes`:** `uv run azurik-mod plan-trampoline 0x8A095 --xbe
default.xbe` decodes the site, picks the smallest byte count that fits
the 5-byte trampoline and ends on an instruction boundary, and flags
what the shim must preserve (`new-shim --hook` runs it for you). Its
decoder knows a limited opcode set (with the ModR/M forms: 0x85700
plans as 7 bytes): a site it can't decode (a prefix byte, or
`mov eax, [moffs]`) plans as "unknown" and exits 1, so read those bytes
in Ghidra or with `xbe insns`. Bytes past the fifth are NOP-filled. If the site
holds other bytes, `apply_trampoline_patch` refuses and prints both; it
never overwrites a sequence it doesn't recognise.

**An indirect call** (`call [edx+0xCC]`, a vtable slot): simulator L1
(`azurik_mod/sim/l1.py`) checks a call-replacing shim returns with its
callee's `RET N`, and can't know an indirect callee's, so it refuses that
hook. Take the inline block instead, its argument pushes and `this` load
with the call (`push eax; mov ecx, ebp; call [edx+0xCC]` at 0x548E3 in
`qol_photo_mode`): the shim makes the call itself and returns with a
plain `RET`, as the inline code it replaced.

### Step 5: register it

```python
FEATURE = register_feature(Feature(
    name="my_feature",
    description="<user-facing text for the GUI and CLI>",
    sites=[MY_FEATURE_TRAMPOLINE],
    default_on=False,
    category="qol",                  # GUI tab (a new id makes a new tab)
    tags=("c-shim",),
    shim=_SHIM,                      # lets apply compile shim.c
))
```

For plain byte patches or sliders, `sites` holds `PatchSpec` /
`ParametricPatch` entries and `shim=None`. Then add the folder to the
hand-maintained import list in `azurik_mod/patches/__init__.py`
(nothing discovers feature folders, and the scaffold doesn't edit it):

```python
import azurik_mod.patches.my_feature  # noqa: F401
```

With that line the pack shows in the GUI, in `randomize-full
--enable-pack my_feature` and in `verify-patches --strict`.

### Step 6: pin it (facts, goldens and the registry contracts)

A pack owes no byte, apply or verify test of its own (D57, Step 1.35);
only a fix owes a pin test. What pins a pack:

- **Its bytes:** the facts file `tests/facts/xbe.json` records what each
  build writes at every site (the pack at its defaults, and each XBE
  slider at twice its default), and its G1/G2 output goldens
  (`tests/goldens/packs.json`, and `tests/goldens/shims.json` for a
  shim object) record the whole build from vanilla. Record them, for
  the new pack only. `gen_facts.py` without the flag prints the facts
  diff and exits 1: check that only the new pack's sites differ before
  `--update-facts` rewrites the whole file. `-k` keeps every other
  golden case check-only:

  ```bash
  uv run --locked python scripts/gen_facts.py                 # the diff; only my_feature's sites
  uv run --locked python scripts/gen_facts.py --update-facts
  uv run --locked pytest -q tests/test_goldens.py -k my_feature --update-goldens
  ```

  Until then `tests/test_facts.py` fails naming the site and
  `test_pack_output_matches_golden[my_feature]` fails. Both files are
  protected: the reviewer reads `git diff tests/facts tests/goldens`
  before the PR gets `reviewed` (D88). A
  failure in any other pack's case is a regression to escalate, never
  something to re-record.
- **The registry contracts**, which cover every registered pack with no
  per-pack code: `tests/test_sliders.py` (each slider's track contains
  its default, and a slider passed at its default builds what leaving
  it out builds) and `tests/test_verify_patches_strict.py`
  (`verify-patches --strict` accepts every G1/G2 golden build).
- **Its behavior:** the simulator (`azurik_mod/sim`: Level 1 checks
  that the code a build patched in is well-formed, Level 2 runs the
  game's own code under Unicorn) through a behavior test in its area
  file (`tests/test_jump.py`, `tests/test_flaps.py`, `tests/test_roll.py`,
  `tests/test_boot.py`, …), and the xemu check (Step 8).

### Step 7: run the suite

```bash
uv run --locked pytest -n auto --dist loadgroup -q
```

A shim that references a vanilla function the registry lacks, or a
kernel import `xboxkrnl_ordinals.py` lacks, fails the header drift
guards with what to register.

### Step 8: boot it in xemu

The tests prove the bytes; only an emulator or real hardware proves the
behavior. Build from the vanilla ISO with only this pack:

```bash
uv run azurik-mod randomize-full --iso iso/usa.iso --output out/my_feature.iso \
    --no-randomize --enable-pack my_feature
```

`--enable-pack` turns on any registered pack by name. The
`azurik-xemu-oracle` skill has the sandboxed runbook. A black screen or
an instant crash: check in Ghidra that the site isn't mid-instruction
and that `replaced_bytes` match, then add a `DbgPrint` to the shim to
see whether it runs at all.

## Calling into the engine

| Call | Path | Cost |
|---|---|---|
| A vanilla Azurik function (`play_movie_fn`, `entity_lookup`, …) | vanilla-symbol registry (A3), declared in `azurik_vanilla.h` | a direct `CALL`, no stub |
| D3D8 / DirectSound / XGraphics / XAPI | the same registry: they are statically linked into `.text` (registered `D3D*`, `XG*`, DirectSound and XAPI functions) | a direct `CALL`; no SDK types yet (D2) |
| A kernel function Azurik imports (`DbgPrint`, `NtClose`, `KeQueryPerformanceCounter`, …) | static import (D1), declared in `azurik_kernel.h` | one indirect jump |
| Any other xboxkrnl export (`DbgBreakPoint`, `KeEnterCriticalRegion`, `MmIsAddressValid`, …) | runtime resolver (D1-extend), common ones declared in `azurik_kernel_extend.h` | the first call resolves (about 1 µs), later calls jump through a cache |

The layout session picks the path; a shim includes the header and
calls.

### Vanilla functions (A3)

`layout_coff` resolves undefined COFF symbols against
[`vanilla_symbols.py`](../azurik_mod/patching/vanilla_symbols.py), so a
`REL32`/`DIR32` relocation lands straight on the vanilla VA: no thunk.
The registry (`vanilla_symbols.all_entries()`) holds the engine,
gameplay and C-runtime functions shims call and the statically linked
`D3D*`, `XG*`, DirectSound and XAPI ones, all declared in
[`azurik_vanilla.h`](../shims/include/azurik_vanilla.h) but
`config_name_lookup` (its companion `azurik_config.h`).

```c
#include "azurik_vanilla.h"

__attribute__((stdcall))
int c_override_boot_movie(const char *requested_movie, char flag) {
    return play_movie_fn("CustomBoot.bik", flag);   /* lands on the vanilla VA */
}
```

To add one (registry and header change in one commit):

1. **Confirm it in Ghidra:** its VA, its convention and its stack
   argument bytes. Read the callee's `RET` and at least two call sites:
   `ADD ESP, N` after the call is cdecl, none is stdcall (`RET N`),
   `MOV ECX, …; MOV EDX, …; CALL` is fastcall. Inputs in other
   registers (EAX, ESI, EDI) need an asm thunk in the header, like
   `player_walk_state_call`.
2. **Register it:**

   ```python
   register(VanillaSymbol(
       name="my_fn",
       va=0x000ABCDE,
       calling_convention="stdcall",
       arg_bytes=8,
       doc="What it does; return-value meaning; gotchas."))
   ```

3. **Declare it** in `azurik_vanilla.h`:

   ```c
   /* Vanilla VA: 0x000ABCDE  (mangled: _my_fn@8) */
   __attribute__((stdcall))
   int my_fn(int a, int b);
   ```

4. **Run the drift guards:** `uv run --locked pytest -q
   tests/test_vanilla_thunks.py tests/test_va_audit.py`. They tie each
   extern's `Vanilla VA` comment to the registry entry of that name,
   compile every declaration together so the emitted symbols must equal
   the registry's mangled names, and check the declared ABI against the
   callee's `RET N`.

Add entries when a shim needs them, not speculatively.
`config_name_lookup` (`__thiscall`, declared in
[`azurik_config.h`](../shims/include/azurik_config.h)) and
`config_cell_value` (`__stdcall(16)`, in `azurik_vanilla.h`, which
`azurik_config.h` includes) are plain externs
(`tests/test_config_wrappers.py`). `gravity_integrate_raw` (0x85700) is
declared with a deliberately incomplete ABI: it is `__fastcall` with an
MSVC return-value pointer, which needs an inline-asm wrapper (the
pattern is in `docs/RE_XBE.md` "Handling MSVC-RVO ABIs"; the unused
wrapper was deleted in Step 1.10, D18).

### Kernel imports (D1 and D1-extend)

**The 151 static imports.** Azurik's thunk table at VA 0x18F3A0 holds
151 xboxkrnl imports, each a 4-byte slot the Xbox loader fills before
the game starts. All of them, 138 functions and 13 data exports, are
declared in [`azurik_kernel.h`](../shims/include/azurik_kernel.h)
(generated by `scripts/gen_kernel_hdr.py`, `docs/SCRIPTS.md`). The
layout session parses the thunk table at apply time
([`kernel_imports.py`](../azurik_mod/patching/kernel_imports.py)) and
emits one 6-byte `JMP [thunk_slot]` stub per referenced function; the
shim's `CALL` lands on the stub. A data export (`KeTickCount`,
`XboxHardwareInfo`, …) is declared `__declspec(dllimport)` and read
through its slot with no stub: `ULONG t = KeTickCount;`.

```c
#include "azurik_kernel.h"

__attribute__((stdcall))
void c_frame_time_probe(void) {
    unsigned long long now = KeQueryPerformanceCounter();
    DbgPrint("frame tick: %u\n", (unsigned)now);
}
```

`KeQueryPerformanceCounter` takes no arguments and returns a
`ULONGLONG`; the header's `LARGE_INTEGER` is a `typedef void *` stand-in
for the by-reference APIs, not a struct with `.LowPart`. Read the
prototypes rather than assuming Win32 shapes.

**Every other export: the runtime resolver.** The other 215 retail
exports have no thunk slot. Growing the table in place would shift the
library-version table right after it, and moving it would mean
rewriting every call site, so a resolver finds them at runtime instead
(§ History).
[`xboxkrnl_resolver.c`](../shims/shared/xboxkrnl_resolver.c) implements
`void *xboxkrnl_resolve_by_ordinal(unsigned ordinal)`: it walks the PE
export table of `xboxkrnl.exe`, which the retail loader maps at
`0x80010000` (`e_lfanew` at +0x3C, then data directory 0, then
`AddressOfFunctions` indexed by ordinal minus `Base`). It has no
imports, no vanilla calls and no global state. For each extended import
a shim references, the session emits a 37-byte stub:

```
 off  bytes               instruction
 0x00 A1 <cache_va:4>     MOV  EAX, [cache_va]
 0x05 85 C0               TEST EAX, EAX
 0x07 75 16               JNZ  +0x16              (to 0x1F)
 0x09 51                  PUSH ECX
 0x0A 52                  PUSH EDX
 0x0B 68 <ordinal:4>      PUSH <ordinal>
 0x10 E8 <rel32:4>        CALL xboxkrnl_resolve_by_ordinal
 0x15 83 C4 04            ADD  ESP, 4
 0x18 5A                  POP  EDX
 0x19 59                  POP  ECX
 0x1A A3 <cache_va:4>     MOV  [cache_va], EAX
 0x1F FF E0               JMP  EAX
 0x21 00 00 00 00         the cache (zero at load)
```

The first call resolves the ordinal, stores it in the stub's own cache
(`cache_va = stub_va + 0x21`) and jumps; later calls take the `JNZ`
straight to the jump. The resolver is cdecl, so the stub saves ECX and
EDX around it: a `FASTCALL` import (`@ObfReferenceObject@4`) receives
its first two arguments there.

**Dispatch.** `shim_session.stub_for_kernel_symbol` is the one entry
point for undefined kernel externs:

1. a cached mangled name reuses its stub;
2. the name maps to an ordinal through `NAME_TO_ORDINAL`; stdcall
   `_Name@N`, fastcall `@Name@N` and cdecl `_Name` all demangle
   (`kernel_imports.kernel_name_for_symbol`);
3. a `__declspec(dllimport)` reference (`__imp_<mangled>`) or a kernel
   data export (`KERNEL_DATA_EXPORTS`) resolves to its thunk slot, no
   stub; a data export must be declared dllimport and be one of
   the XBE's imports, else `ValueError` (data has no code to stub);
4. an import of this XBE (its own thunk table: Europe's imports two
   more than USA's, ordinals 46 and 354, AZ-328) gets the 6-byte static
   stub;
5. anything else gets the resolver (`_ensure_resolver_placed`, once per
   session) and a 37-byte stub (`_place_extended_kernel_stub`);
6. the stub is cached by mangled name, so every shim of the session
   that calls the same function shares one stub and one cache slot.

**Ordinal catalogue (AZ-114).**
[`xboxkrnl_ordinals.py`](../azurik_mod/patching/xboxkrnl_ordinals.py)
holds `AZURIK_KERNEL_ORDINALS` (Azurik's 151) and
`EXTENDED_KERNEL_ORDINALS` (the other 215 retail exports, functions and
data alike); their union `ALL_KERNEL_ORDINALS` covers ordinals 1–366,
one name per ordinal, so `NAME_TO_ORDINAL` and `ORDINAL_TO_NAME` are
inverses. Ordinals 367–373 are unnamed and 374–378 (`MmDbg*`) exist
only in debug kernels, so neither is listed. The source, re-derived
2026-10-09, is the `kernelExports` table in ghidra-xbe's
`XbeLoader.java` (the XBE loader this project's Ghidra uses), which
names all 151 ordinals of Azurik's thunk table exactly as
`AZURIK_KERNEL_ORDINALS` does. In the hand-curated table it replaced,
113 of 204 entries were wrong, most 1–9 ordinals low (`ObfReferenceObject`
was 249, which is `ObSymbolicLinkObjectType`; it is 251), and 16
statically imported names carried a second, wrong ordinal.

**Declaring another extended import.** Every retail export is already
catalogued, so there is no ordinal to add:

1. find the export's exact name in `EXTENDED_KERNEL_ORDINALS`;
2. declare it, with its `NTAPI` / `FASTCALL` annotation and argument
   types from `vendor/xbox-includes/include/xboxkrnl.h`, in
   [`azurik_kernel_extend.h`](../shims/include/azurik_kernel_extend.h)
   (which carries no ordinals) or in your shim source;
3. run `uv run --locked pytest -q tests/test_d1_extend.py`: its drift
   guard fails when the header declares a name the catalogue lacks.

**Limits.**

- Retail kernels only: the resolver assumes the retail base
  `0x80010000`; debug and Chihiro kernels load elsewhere.
- By ordinal only: retail xboxkrnl exports have no names to walk. An
  ordinal with no export would resolve to NULL and fault at `JMP EAX`;
  every catalogued ordinal is a retail export, so a catalogued name
  can't hit that.
- A resolved slot stays filled until the game exits.
- The cache slot is inside the stub, so the stub lands writable:
  `shim_allocator` lands an allocation named `__impext__<name>`
  (`shim_session.EXTENDED_STUB_PREFIX`) as it lands a `.data`, in
  `SHIMS` with WRITABLE, flags 0x7 (AZ-281, Step 2.22g; pin
  `tests/test_d1_extend.py::ExtendedStubLanding::test_an_extended_kernel_stubs_cache_slot_lands_in_a_writable_section`).
  Until then it landed like code, in a `SHIMS` of flags 0x6 unless a
  `.data` or `.bss` had landed there too, and the first call's store
  to the cache would have faulted [inferred] [verified 2026-10-12: a
  scratch shim that calls `DbgBreakPoint`, applied by
  `apply_trampoline_patch` at 0x05F6E5 of the vanilla XBE, gives a
  94-byte `SHIMS` at 0x39F000 with flags 0x6 before the fix and 0x7
  after].
- Each unique extended import costs 37 bytes, plus about 50 for the
  resolver once.
- No extended import has been seen working in game yet.

**Tests.** `tests/test_kernel_imports.py` covers the static path (the
table invariants, demangling, stubs). `tests/test_d1_extend.py` covers
the extended one: the catalogue (`ExtendedOrdinalTable`: 1–366 all
present, one ordinal per name, retail spot checks), the 37-byte stub
layout and its rel32 overflow error, the resolver compiling with no
undefined externs, the session's static-vs-extended dispatch and
dedup, a fastcall import's ECX/EDX reaching a fake kernel under
Unicorn on the first and the cached call, and the header drift guard.

### Shared libraries (E)

When several trampolines share helper code (common math, a lookup
table, a toggle state), put it in a standalone shim `.o` and place it
once per session; every consumer's extern then resolves to the same VA
(`tests/test_shared_library.py`).

```c
/* the library */
__attribute__((stdcall))
int shared_compute(int a, int b) { return a * 2 + b; }

/* azurik_mod/patches/my_feature_a/shim.c */
__attribute__((stdcall)) int shared_compute(int, int);   /* defined in the library */

__attribute__((stdcall))
int c_trampoline_a(int x) { return shared_compute(x, 1); }
```

```python
from azurik_mod.patching.apply import apply_trampoline_patch, shim_allocator
from azurik_mod.patching.shim_session import get_or_create_session

def apply_my_pack(xbe_data: bytearray) -> None:
    sess = get_or_create_session(xbe_data)
    sess.apply_shared_library(
        _REPO_ROOT / "shims/build/my_shared_lib.o",
        allocate=shim_allocator(xbe_data),
    )
    apply_trampoline_patch(xbe_data, TRAMPOLINE_A, repo_root=_REPO_ROOT)
    apply_trampoline_patch(xbe_data, TRAMPOLINE_B, repo_root=_REPO_ROOT)
```

`allocate(name, payload, align=1)` returns `(file_offset, vaddr)` with
`vaddr` a multiple of `align`; `layout_coff` passes each section's
alignment and kernel stubs pass only two arguments, so the default is
required. `shim_allocator(xbe_data)` is the one trampolines use: it
lands a `.data` or `.bss` (AZ-220) and a D1-extend stub (AZ-281)
writable. The session follows the
buffer: `get_or_create_session` on the same bytearray returns the same
session until `apply_pack` finishes the pack and releases it (a failed
trampoline apply rolls it back with the bytes). Code that drives
`apply_trampoline_patch` outside `apply_pack` calls
`release_session(xbe_data)` itself. A shared library may call vanilla
functions and kernel imports, but not another shared library: place
every library before its first consumer.

### One state for several hooks: a door

`apply_pack` lands a shim's object once per hook, so two hooks of one
`shim.c` share no `static` data. Where they must (and a shared library
would need `custom_apply`), one hook can be a `jmp` TrampolinePatch at a
vanilla function no code calls (check `xbe calls --to`, `xbe find-refs
--va` and `--data`, `xbe insns --mnemonic jmp --operand`): that VA is
then a fixed door into the one landing that holds the state. Register it
as a vanilla symbol with the ABI the shim gives it, and have the other
hooks (and any in-place `PatchSpec`) call the door with an op in a
register. `qol_alloc_race`'s copy gate (AZ-817) does this at 0xA66C0.

## Per-apply float injection

A slider that reaches into a compiled shim overwrites 4 bytes of the
shim's `.rdata` at apply time, so the source compiles once and each
build threads its own value through.

```c
#include "azurik.h"

AZURIK_FLOAT_PARAM(gravity_scale, 1.0f);    /* volatile const float in .rdata */

void __attribute__((used)) c_my_shim(void) {
    float g = gravity_scale;                /* a DIR32 load, never folded */
    /* ... */
}
```

`volatile` defeats constant folding, `const` keeps the shim's own code
from writing it, `used` keeps it from dead-code elimination and
`section(".rdata")` pins the layout. On the Python side, list the
params on the `TrampolinePatch`; `name` is the slider key callers pass
in `apply_pack(params={...})` and `symbol` the mangled C name:

```python
from azurik_mod.patching.spec import FloatParam, TrampolinePatch

MY_SHIM = TrampolinePatch(
    ...,
    shim_symbol="_c_my_shim",
    float_params=(FloatParam("gravity_scale", "_gravity_scale", 1.0),),
)
```

After relocation, apply finds each symbol's landed offset
(`coff.find_landed_symbol`) and writes `params[name]` there, or the
default when the key is absent (an explicit `0.0` is honoured). The
values follow the slider rule (D23): NaN/inf fail the site before any
byte is written, and a value past FLT_MAX lands as ±inf with a NOTE
(`spec.pack_f32`). A declared param the body never reads is optimised
away; that, or a symbol missing from the landed sections, fails the
site and the build (D35).
Use `ParametricPatch` to rewrite bytes at a vanilla VA (an instruction
operand or a `.rdata` float the game reads); use `FloatParam` when the
value needs shim-side logic. Fixture:
[`_float_param_test.c`](../shims/fixtures/_float_param_test.c) with
`tests/test_float_param_injection.py`.

A byte table takes the same path (Step 2.71): `AZURIK_BYTES_PARAM(name,
size)` declares a `volatile const unsigned char name[size]` of zeros in
`.rdata`, and `BytesParam(name, symbol, size)` in the patch's
`bytes_params` writes `params[name]` (bytes, at most `size`, zero-filled
to it; absent: all zeros) over the landed array. A longer table fails
the site before any byte is written. The player-model sounds shim
(`azurik_mod/patches/player_model/sounds.c`, X14) reads its per-slot
table this way.

## Re-applying, and the legacy escape hatch

Builds start from vanilla (D27). An already-installed trampoline (the
same opcode shape and trailing NOPs) is left alone, so a second apply of
the same pack stacks nothing. A shim with `float_params` or `bytes_params` raises
`PatchConflictError` instead, because its installed values aren't read
back to compare (`tests/test_reapply_contract.py`).

A feature can declare `legacy_sites=(...)`, `PatchSpec` byte patches
that `apply_pack` uses in place of every `TrampolinePatch` of the pack
when `AZURIK_NO_SHIMS=1` is set, so a host without the shim compiler
can still ship a patched XBE. One variable covers every shim-backed
pack. Without it, a shim that can't be built fails the whole build:
`PackApplyError` names the pack and every failed site, and no output is
written (D35).

## Hand-assembled shims (`shim_builder`)

[`shim_builder.py`](../azurik_mod/patching/shim_builder.py) builds a
shim from machine code emitted in Python. Choose it over C when the hook
interrupts an x87 computation and must keep or consume `ST(0..n)`
exactly, when the shim calls a `__thiscall` function with stack
arguments already pushed on the caller's frame, or when the slider
value is baked into a carved data slot (a `scale * scale * 2g`
injection, say). Choose C for ordinary logic calling registered
functions with cdecl or stdcall arguments, for late-bound floats
(§ Per-apply float injection), and whenever you want the compiler to
allocate registers.

`player_physics` ships both live examples: the roll shim (hook 0x8C745,
a `CALL`, 36-byte body) and the wing-flap ceiling shim (hook 0x89154,
the `FADD` that feeds the `peak_z` latch, 15-byte body). The pattern:

```python
from azurik_mod.patching.shim_builder import (
    HandShimSpec, install_hand_shim, whitelist_for_hand_shim,
    emit_fmul_abs32, with_sentinel,
)

def _build_body(shim_va: int, data_va: int) -> bytes:
    """(shim_va, data_va), always in this order; exactly body_size bytes."""
    ...                                # e.g. FLD [ESI+0x144]; FMUL [data_va]; FADDP; RET

_SPEC = HandShimSpec(
    hook_va=0x00089154,
    hook_vanilla=_HOOK_VANILLA,        # the bytes at hook_va, as Ghidra shows them
    trampoline_mode="call",            # or "jmp" (then set hook_return_va)
    hook_pad_nops=1,                   # hook width = 5 + 1
    body_size=15,
    data_abs32_offset=6,               # the body's FMUL [data_va] at offset 6 ...
    data_abs32_opcode=b"\xD8\x0D",     # ... lets a re-apply find the data
    build_body=_build_body,
    rel32=(),                          # body offsets of each vanilla address it holds
)                                      # (abs32=() too): the roll shim's tail JMP is rel32=(32,)

def apply_ceiling(xbe_data: bytearray, scale: float) -> bool:
    result = install_hand_shim(        # an InstalledShim, or None
        xbe_data, _SPEC,
        data_block=with_sentinel(struct.pack("<f", scale)),
        label=f"wing-flap ceiling {scale:.2f}x",
    )
    return result is not None

def dynamic_whitelist(xbe):
    return whitelist_for_hand_shim(xbe, _SPEC, data_whitelist_size=8)
```

`install_hand_shim` detects vanilla-byte drift, carves the data block
and the body with `carve_shim_landing`, writes the trampoline, and on a
re-apply follows the installed trampoline to the body and data: the
same data is "(already applied)" and writes nothing, other data raises
`PatchConflictError` (D27; without `data_abs32_offset` a re-apply
counts as drift).

**Both releases (Step RG.4b).** The hook and every address of the
vanilla image the body holds are USA VAs. On a Europe XBE the hook is
read at its address-map `site` entry (which relocates the vanilla
bytes' own addresses), and the body's `abs32`/`rel32` offsets are
relocated through the map. `tests/test_region.py` decodes each
`HandShimSpec` body with Capstone and fails while an address into the
image is left undeclared (AZ-324), or while the hook or an address has
no Europe entry (AZ-325).

A C shim's calls to registered vanilla functions resolve through the
map (`Region.symbols()`), but nothing relocates a constant in its C: a
fixed address (an `AZURIK_*_VA` define, a cast `0x...`) reads USA's on
Europe. A shim of a pack that lists Europe reads vanilla data through a
registered accessor or its hook's arguments (`qol_save_warp` reads the
pad through `active_controller_state`, Step R2.1b);
`tests/test_region.py` fails while its `.text` holds an address into
the image outside its relocations.

**Byte-correct at the hook is not upstream of the mechanic.** Five
hand-assembled packs landed their bytes cleanly and changed nothing in
game; Step 1.10 (D18) deleted them (§ History). Check that the hook runs
upstream of the state that drives the visible mechanic, and that the
slider actually reaches the pack; the `azurik-game-reference` skill
catalogues those no-effect patches.

## Pitfalls and debugging

| Symptom | Cause | Fix |
|---|---|---|
| The game crashes soon after the shim returns, or later calls get garbage arguments | the shim's convention doesn't match the call it replaced, so the stack is popped too much or too little | read the call site in Ghidra: `ADD ESP, N` after the call is cdecl (no `stdcall` on the shim); none is stdcall (`__attribute__((stdcall))`) |
| The shim reads or writes the wrong field | a raw offset, or a wrong field in `azurik.h` | use the named fields; add a missing one per § Adding fields to `azurik.h` |
| `REL32 displacement 0x… does not fit signed 32-bit` | a shim more than 2 GiB from its call site, impossible in a 4 MiB image, so the VA math is wrong | print the shim's entry VA and the site VA; the delta should be under 1 MiB |
| `test_every_shim_header_vanilla_extern_links_to_a_registry_va` lists `_foo@8`, or `test_declared_vanilla_abi_matches_callee_ret_imm16` names another pop count | the `VanillaSymbol`'s `calling_convention` or `arg_bytes` is wrong, so its mangled name differs from what the compiler emitted | recount the argument bytes (a `BOOLEAN` takes 4 on the stack; a pointer is 4); recheck cdecl vs stdcall at the call site |
| `COFF has no landable sections` | clang removed an entry point it saw as unused | mark it `__attribute__((used))` |
| `shim object not found` (then `PackApplyError` naming the pack and site) | the `.o` wasn't built | compile it by hand (§ Toolchain) to see the compiler's error, or set `AZURIK_NO_SHIMS=1` for the pack's `legacy_sites` |
| `symbol '_c_<name>' not found in COFF file` | `shim_symbol` isn't the mangled name | a no-argument stdcall entry is `_c_<name>@0`; `shim-inspect` prints the table |
| `only N bytes of header VA headroom…` / `…on-disk headroom…` | the XBE can't grow its section-header array by 56 bytes | Azurik has 880 of both; this fires only on another or already heavily modified image |
| `Unsupported COFF machine 0x…` | the object isn't i386 | check that `-target x86-windows-msvc` is still in `SHIM_CFLAGS` |
| `COFF .text has N relocations; use layout_coff()…` | you called `extract_shim_bytes()` on a relocated shim | let `apply_trampoline_patch` route it |

When a shim misbehaves, in order: run the tests with `-v` and read the
assertion; inspect the `.o` (`shim-inspect` or `objdump -d`): is the
entry symbol right, do the relocations look sane?; apply it alone to
the vanilla XBE in a short script, write the result to a temp file and
open it in Ghidra: does the site's `CALL` reach the placed shim, do the
landed bytes decode to your logic?; diff the vanilla and patched XBEs
(`verify-patches --original … --strict`) for surprise writes; boot it in
xemu with a `DbgPrint` in the shim.

## Limitations

- **No SDK types (D2).** D3D8, DirectSound, XGraphics and XAPI are
  ordinary vanilla symbols (above), called through flat `stdcall`
  externs; NXDK's real headers, structs and vtables aren't wired in,
  and no shim has needed them.
- **No chained shared libraries:** a shared library can't call another.

## Adding fields to `azurik.h`

- **Verify every offset in Ghidra before naming it.** The pass that
  added the named structs had five wrongly named `CritterData` fields
  (the `ouch*_threshold` / `ouch*_knockback` row) because they were
  named from memory. Find the `FUN_000d1420("<name>")` lookup before
  the write; if the config-key string isn't there, name the field
  `_reservedNN` or mark it `(speculative)`.
- **Add a matching `_Static_assert`** at the bottom of the header for
  every named field past an unnamed gap, so drift fails at compile
  time, not in game.
- **Use byte-typed fields for booleans** the engine writes as
  `*(bool *)(base + N)` (`use_center_basis`, `hits_through_walls`);
  a `u32 flags` loses the single-byte load and store.

## File map

| Role | Path |
|---|---|
| Feature folder (one per pack) | `azurik_mod/patches/<name>/`: `__init__.py`, optional `shim.c` and `README.md` |
| Pack import list | `azurik_mod/patches/__init__.py` (hand-maintained); `_qol_shared.py`, `_player_character.py` and `_player_damage_marker.py` are helpers; `player_model/` holds the model swap's C shims, built as `player_model_<stem>.o` |
| Scaffolder | `azurik-mod new-shim` → `azurik_mod/xbe_tools/shim_scaffolder.py` |
| Shim compiler (zig) | `azurik_mod/patching/shim_toolchain.py` |
| Compiled objects | `shims/build/<pack>.o` (gitignored) |
| Struct layouts and VA anchors | `shims/include/azurik.h` |
| Vanilla-function externs / registry | `shims/include/azurik_vanilla.h` / `azurik_mod/patching/vanilla_symbols.py` |
| Kernel externs (static / extended) | `shims/include/azurik_kernel.h` / `shims/include/azurik_kernel_extend.h` |
| Config-lookup externs | `shims/include/azurik_config.h` |
| Kernel resolver | `shims/shared/xboxkrnl_resolver.c` |
| Test-only shim sources | `shims/fixtures/_*.c` |
| Kernel ordinals / thunk-table parser | `azurik_mod/patching/xboxkrnl_ordinals.py` / `kernel_imports.py` |
| Layout session (kernel stubs, shared libraries) | `azurik_mod/patching/shim_session.py` |
| COFF reader and `layout_coff` | `azurik_mod/patching/coff.py` |
| XBE section surgery | `azurik_mod/patching/xbe.py` |
| `apply_pack`, `apply_trampoline_patch`, `carve_shim_landing` | `azurik_mod/patching/apply.py` |
| Site descriptors (`PatchSpec`, `ParametricPatch`, `TrampolinePatch`, `FloatParam`) | `azurik_mod/patching/spec.py` |
| `Feature`, `register_feature` / `ShimSource` / categories | `azurik_mod/patching/registry.py` / `feature.py` / `category.py` |
| Hand-assembled shims | `azurik_mod/patching/shim_builder.py` |

Tests by area: the dispatcher `test_apply_pack.py`; trampolines
`test_trampoline_patch.py`; section growth `test_append_xbe_section.py`;
relocations and alignment `test_coff_relocations.py`,
`test_coff_section_alignment.py`; vanilla calls `test_vanilla_thunks.py`,
`test_va_audit.py`; kernel imports `test_kernel_imports.py`,
`test_d1_extend.py`; shared libraries `test_shared_library.py`; config
wrappers `test_config_wrappers.py`; floats
`test_float_param_injection.py`; auto-compile `test_autocompile.py`;
the toolchain `test_shim_toolchain.py`; header offsets and the scaffold
`test_shim_authoring.py`, `test_scaffolder.py`; hand-assembled shims
`test_shim_builder.py`; re-apply `test_reapply_contract.py`;
`qol_skip_logo`'s object path, registry entry and `AZURIK_NO_SHIMS` bytes
`test_qol_skip_logo.py`; every pack's bytes `test_facts.py`,
`test_goldens.py`.

## History

**Merged docs.** Step 3.3c merged the shim authoring guide
(`SHIM_AUTHORING.md`) and the live parts of the D1-extend design note
into this file; the note's problem statement and the options it weighed
for reaching non-imported kernel exports (extend the thunk table in
place, move it, or resolve at runtime) are archived in
[`Finished/D1_EXTEND.md`](Finished/D1_EXTEND.md).

**Platform tiers.** Phase 1 shipped one proof-of-concept shim,
`qol_skip_logo`, behaviourally identical to the 10-NOP patch it
replaced; its "self-contained, relocation-free" limits no longer apply.
Phase 2 shipped the rest:

| ID | Tier | Status |
|---|---|---|
| A1 | `append_xbe_section` (unbounded shim size) | done |
| A2 | relocation-aware COFF loader | done |
| A3 | vanilla-function calls (registry plus layout resolution) | done |
| B1 | `azurik.h` named structs with drift asserts | done |
| B2 | a Unicorn harness for shims | superseded by the simulator, `azurik_mod/sim` (REORG_PLAN §5.4, Steps 2.7–2.10) |
| B3 | `azurik-mod new-shim` scaffolding | done |
| C1 | player-speed shim (the motivating deliverable) | done |
| C-jump | player jump velocity | done: `player_physics` `jump_speed_scale` |
| D1 | xboxkrnl imports through thunk-table stubs | done, all 151 |
| D1-extend | runtime resolver for every other export | done |
| D2 | NXDK (real Xbox SDK headers) | not started |
| E | shared-library shim layout (`ShimLayoutSession`) | done |

Ideas never started: skip `prophecy.bik` with a second C shim at
`BOOT_STATE_PLAY_PROPHECY` (`AZURIK_BOOT_STATE_VA` in `azurik.h`), and a
camera distance / FOV patch (likely a `ParametricPatch` on a `.rdata`
float).

**The deleted hand-assembled packs.** Rounds 7–8 shipped four
hand-assembled shims (`flap_at_peak`, `root_motion_roll`,
`root_motion_climb`, `slope_slide_speed`) that landed their bytes and
appeared to do nothing in game. Round 10 withdrew them as hooked too
late, a diagnosis confounded with a GUI bug (`build_randomized_iso`
forwarded only `pack_params["player_physics"]`, so every other pack
applied at 1.0); round 11.8 restored them, round 11.13 testing again saw
no effect, and Step 1.10 (D18) deleted them with
`animation_root_motion_scale` (a 38-byte vtable hook). They remain
readable as patterns: find the deleting commit with `git log
--diff-filter=D --oneline -- azurik_mod/patches/slope_slide_speed` and
read a file with `git show <commit>^:<path>`.

| Pattern | Deleted pack | Hook | Shim size |
|---|---|---|---|
| `FLD` → `FMUL` → `JMP` (the simplest) | `slope_slide_speed` | 0x8A095 (`FLD`) | 17 B |
| x87 compare-max plus instruction replay | `flap_at_peak` | 0x89409 (`FSTP`) | 43 B |
| `__thiscall` wrap, flag-gated post-scale | `root_motion_roll` | 0x866D9 (`CALL`) | 134 B |
| `__thiscall` wrap, no gate | `root_motion_climb` | 0x883FF (`CALL`) | 128 B |

The two `__thiscall` wraps re-push the caller's four stack arguments
for the inner call with four `push [esp+0x18]`: each push shifts ESP by
4, so the same operand reads the next argument in turn.
