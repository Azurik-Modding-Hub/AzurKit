# Choices that lean on xemu

The owner's D601 (2026-10-23): "xemu only is fine, document/note where we
make these choices just in case". This page lists each choice AzurKit
makes that works only in xemu, or that only xemu has measured, so that a
move to real hardware later knows what to check. A change that makes such
a choice adds a row here and a note back where the choice is made
(ported from Azurik_Modkit's `docs/`, where each row was made).

"xemu" here is the owner's macOS fork, 0.16.4-3-g95e7ffc7ec since Step X.94, which
every sitting runs. "Hardware" means a retail Xbox (64 MiB) or one
upgraded to 128 MiB. No test checks this page: nothing in the code marks a
choice as xemu-only, so the review checklist keeps it current.

## Works only in xemu

| | Choice | Where it is made | What xemu gives it | On hardware |
|---|---|---|---|---|
| X1 | `qol_memory_upper64`: the game's virtual load runs above 64 MiB (D520's route B; on by default, D571) | [`qol_memory.py`](../src/azurkit/tools/mods/packs/qol_memory.py) (`qol_memory_upper64.c`): hooks 0xA490C and 0xBAD55 (Europe 0xA4A8C, 0xBAED5) | RAM at physical 0x04000000-0x07FFFFFF at `mem_limit` 128, which the title's kernel never manages. The shim maps it at VA 0x84000000 (PDE[0x210..0x21F]) only when NV_PFB_CSTATUS reads 128 MiB, and keeps its heap's state page at VA 0x87FFF000; since Step 2.162n (D625) it places them from that tier's top down, the GPU runs from its bottom up | Inert on 64 MiB (CSTATUS 0x04000000). Unmeasured on a 128 MiB console, where the GPU's instance memory may sit at the top of RAM, on the state page [inferred] |
| X2 | `qol_memory_upper64_gpu`: the GPU's textures, meshes and push buffers above 64 MiB (D576; on by default from Step 2.162k, D588) | [`qol_memory.py`](../src/azurkit/tools/mods/packs/qol_memory.py) (`qol_memory_upper64_gpu.c`): hooks 0xA48DD, 0xA48FA, 0xBAD46 and 0x12D552 (Europe 0xA4A5D, 0xA4A7A, 0xBAEC6, 0x12C5D7) and 22 mask sites (Europe 23) | The GPU reading above 64 MiB through D3D's DMA objects. xemu aborts on an offset past a DMA object's limit (`texture.c:100`, `:132`; `vk/vertex.c:594`; `vk/surface.c:2069-2070`; `pfifo.c:676` under null), so 0x12D552 raises the seven objects' limit from 0x03FFAFFF when CSTATUS reads 128 MiB, and the 22 D3D masks widen from 0x3FFFFFF. Since Step 2.162l both reach 256 MiB for X5 (the limit 0x0FFFEFFF, past a 128 MiB machine's RAM: X9; the masks 0x0FFFFFFF, the same output below 128 MiB). Since Step 2.162m (D616) 0xA48DD lets a run that fits the heap past the load budget's compare, so the budget holds only the runs that fall back low; since Step 2.162n (D625) a body's mesh run takes the span between the GPU runs at the upper 64 MiB's bottom and the CPU runs at its top, about 43.09 MiB at a1's save (measured: a 42.34 MiB mesh run plays a1, w1, e2, a1 and w1 whole, a 43.11 MiB one never loads) | Inert on 64 MiB. Untested on a 128 MiB NV2A, where the limit passes the RAM's end (X9) |
| X3 | Every build is for a 128 MiB machine by default: `--ram 128` with both packs, so a body may take 49.5 MiB (D588, Step 2.162k; the line since Step 2.162n) | `src/azurkit/tools/characters/model_inspect.py` (`RAMS`, `lines_for`), a character recipe's `ram` (`azurkit build --character`) | xemu at `mem_limit` 128 (the D98 fixtures' size) | On a retail Xbox a body past the 64 MiB lines (14 MiB) loses pieces and textures, and a larger one hangs loading: build with `--ram 64` |
| X4 | The randomizer's live tracker and its Play button (Steps R1.26, R1.26c; D249, D256) | `src/azurkit/tools/randomizer/live/link.py`, `live_launch.py` | It reads a running xemu's guest RAM through the fork's shared memory (`XEMU_RAM_SHM`) or QMP's HMP `x`, and Play launches xemu on the build | No path: a console has no RAM link for the tracker to read |

### Stage 3: `qol_memory_upper256`, RAM to 256 MiB (D600, Step 2.162l)

The opt-in pack [`qol_memory_upper256`](../src/azurkit/tools/mods/packs/qol_memory.py) maps physical 0x08000000-0x0FFFFFFF at VA 0x88000000 (PDE[0x220..0x23F]), the upper heap's T3, which the default packs' runs take once it is mapped, which `qol_memory_upper64_gpu`'s budget hook then counts as room, so a graphics run larger than T2's free span passes the load budget's compare there (the probe's hook 0xA48D7, Europe 0xA4A57; until Step 2.162m that hook let the run past the compare itself; [`PATCHES.md`](PATCHES.md) § `qol_memory_upper256`). Every row below leans on xemu, and no hardware runs it: the NV2A drives 128 MiB at most, so a hardware build leaves the pack off. `--ram 256` (X14) turns it on in every build that has `--ram`.

| | Choice | Where it is made | What xemu gives it | On hardware |
|---|---|---|---|---|
| X5 | RAM above 128 MiB | `qol_memory_upper256` | xemu v0.16.2 or later at `mem_limit` `'256'`, whose NV2A DMA mask is 28 bits there (D599); v0.16.1 wraps or aborts on such a state | No path: the NV2A drives 128 MiB at most |
| X6 | The probe's store above 128 MiB | `src/azurkit/tools/mods/shims/qol_memory_heap.h` (`upper256_ready`) | CSTATUS reads 128 MiB at 128 and at 256 MiB, so the size is probed by a word stored 128 MiB above the state page's W2 (through an uncached PDE, W2 written back first) | Unmeasured: the store may fold onto W2, which the probe sees and undoes, or hang |
| X7 | One probe word covers the tier | the same | xemu's RAM is contiguous from 0 | No path (X5) |
| X8 | The GPU reading physical 128-256 MiB through D3D's base-0 DMA objects | the 22 (Europe 23) masks at 0x0FFFFFFF in `qol_memory_upper64_gpu` | Offsets past the 27 bits the hardware has; 2D blits, the pusher's freeze copy and the PCRTC base follow v0.16.2's 28-bit mask; BAR1 still covers only the first 128 MiB | No path: the hardware's DMA addresses are 27 bits |
| X9 | DMA limits of 0x0FFFEFFF on a 128 MiB machine (past its RAM; in the default build) | `qol_memory_upper64_gpu`'s hook at 0x12D552 (Europe 0x12C5D7) | xemu checks only offset < limit (`nv_dma_map`'s base-plus-limit assert is commented out), so the limit is inert there; vanilla's report object already has 0x10000000 | Inert on 64 MiB (CSTATUS 0x04000000). Untested on a 128 MiB NV2A |
| X10 | Every limit raised before any offset passes it, and report objects kept in the first 16 MiB | the same; D3D's own allocations stay below 0x3FFB000 | xemu aborts on an offset past a limit rather than wrapping; GET_REPORT offsets are 24 bits | No path (X5) |
| X11 | The APU reading the tier | (DirectSound's runs in T3) | The fork's APU bounds reads only by the RAM size [read, not run] | No path (X5) |
| X12 | The cache types of the tier's PDEs | `qol_memory_heap.h` (write-back, write-combined for GPU blocks) | TCG doesn't model them | No path (X5); it would need MTRR or PAT cover past 128 MiB |
| X13 | The probe's write into unassigned space on a 128 MiB xemu | `qol_memory_heap.h` | QEMU drops it and reads 0, so the probe sees a hole and maps nothing | Unmeasured on a 128 MiB console: a fold (X6) or a hole maps nothing |
| X14 | The `--ram 256` target: the pack turned on, a body may take 127 MiB with one run up to 113.53 MiB, a warning past 48 (Step 2.162l, D610) | `src/azurkit/tools/characters/model_inspect.py` (`RAMS`, `ram_packs`, `lines_for`, `run_line_for`), a character recipe's `ram` (`azurkit build --character`) | xemu v0.16.2 or later at `mem_limit` `'256'` (X5); the lines are the largest bodies that played there | No path (X5): build for hardware with `--ram 128` or `--ram 64`. A body past the 128 MiB lines loses loads or never finishes loading at 128 MiB and loses pieces or hangs at 64 |

## Measured only in xemu

Nothing here needs xemu to work, but only xemu has measured it.

| | Choice | Where it is made | On hardware |
|---|---|---|---|
| Y1 | `qol_memory_budget`'s 42 MiB load budget (D528) | the imm32 at 0x596CC (Europe 0x5970C); `qol_memory.py`, `qol_memory_budget.c` | Unmeasured: 42 was chosen from xemu sittings at 64 and 128 MiB |
| Y2 | The body size lines: at 64 MiB refuse past 14 MiB, warn past 12; at 128 MiB refuse past 49.5 or one run past 42.34, warn past 38; at 256 MiB (X14) refuse past 127 or one run past 113.53, warn past 48 | `src/azurkit/tools/characters/model_inspect.py` (`lines_for`, `run_line_for`) | Unmeasured: each line is the largest body that played in xemu |
| Y3 | `fps_unlock`'s immediate present: the JNZ at 0x12635D NOPed, "avoiding xemu's synchronous VSync wait" | `src/azurkit/tools/mods/packs/fps_unlock.py` | Should work in principle (it may tear [inferred]); unmeasured |
| Y4 | The frame-rate warning (Step 2.173, D603, D604) | `devkit/xemu/sittings/model_kit.py` `row_cost`, `devkit/xemu/oracle.py` `frame_warning` ([`devkit/xemu/README.md`](../devkit/xemu/README.md)) | It reads xemu's NV2A counts and xemu's host time; xemu models no NV2A time, so it says nothing of a console's frame rate, which needs a console's frame timing. Sitting 2.173-fc: 2.162h's heaviest body, 22-38 times vanilla's heaviest frame in GPU work, held vanilla's real-time rate in xemu; no console measured |
| Y5 | Every "seen in xemu" grade | Modkit's pack and model notes, as each pack's and slider's text in `src/azurkit/tools/mods/packs/` and the characters' grades carry them | Not seen on a console |
| Y6 | The randomizer's xemu proofs (D114) | the authoring's proofs (`devkit/rando/draft/authoring/*.toml`, a proof's `by = "xemu"`), `src/azurkit/tools/randomizer/physics.py` (its "[verified xemu]" constants) | A skip or a constant confirmed in xemu only; unmeasured on a console |
| Y7 | The physics and HP sliders' measured numbers | the "[xemu s6]" and "[xemu p9]" notes (`docs/RE_MOVEMENT.md`; the sliders in `src/azurkit/tools/mods/packs/player_physics.py` and `player_max_hp.py`) | Unmeasured |
| Y8 | The HDD cache keyed on `filelist.txt`'s lines, which every build rewrites for each file it changes | `src/azurkit/core/filelist.py`, `src/azurkit/core/iso.py` ("xemu, 2026-10-09"; [`RE_DATA.md`](RE_DATA.md) "filelist.txt") | The game's own code, so it should hold [inferred]; unmeasured |

## The oracle (dev only; no build depends on it)

| | Choice | What it means |
|---|---|---|
| Z1 | The D98 fixtures run `mem_limit` `'128'` (their `xemu.toml`), and every sitting starts from their 32 xemu save states | Every sitting's numbers come from a 128 MiB machine, from states no console loads; a claim about a retail Xbox needs rows at `'64'`, from a cold boot |
| Z2 | The fork's own features the harness takes | Deterministic icount runs, the null renderer, the NV2A counters, PC hooks, the access log, the input queue, `picture-stale`, null-RAM pictures, the QMP watch monitor, the host profile, load verification, the guest bugcheck report and `vblank-ns` (`devkit/xemu/oracle.py`; [`devkit/xemu/README.md`](../devkit/xemu/README.md)) |

## Kept for hardware anyway

- Shims target the Pentium III (AZ-021): no SSE2. Sittings run xemu with
  `XEMU_STRICT_CPUID=1`, so code the console's CPU lacks faults in xemu too.
- Shims call only the retail kernel's exports the game imports (shimkit's
  kernel header, from the facts' `kernel`); `xboxkrnl_resolver.c` refuses
  any other by name.
