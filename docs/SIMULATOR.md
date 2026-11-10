# The simulator (`devkit/sim`)

Four levels, dev only (Unicorn is the `devkit` group's, GPL, and nothing
under `src/azurkit` imports it; `devkit/README.md` says why none of it
ships). Every level runs the USA release's code only (D146). Ported from
Modkit's `devkit/sim` at its cut (Step 4.13a): each module is Modkit's
code with its imports pointed at AzurKit's (`devkit/sim/ports.py`).

| Level | Module | Runs | Used by |
|---|---|---|---|
| L0 | `sim/static.py` | structure checks of a build in pure Python | dev tools |
| L1 | `sim/l1.py` | static checks that patched code is well-formed | dev tools |
| L2 | `sim/l2.py` | the game's own jump, flap, walk and roll code on a named fake state | `tests/test_simulator.py`, `tests/test_roll.py` |
| L3 | `sim/l3.py` | the game's own player update or whole simulation step from a RAM snapshot of a running game | dev tools and sittings (Steps X.5-X.7, D168, D170) |

L0-L2 are described in the `azurik-game-reference` skill (§ "The
simulator levels"). The rest of this page is L3. The worker pool, FastL3,
the native kernel and the reach engine are `devkit/reach` (Step 4.13d1,
[`REACH.md`](REACH.md)), the trick explorer's and the conformance corpus's
commands `python -m devkit sim explore` and `conformance`
([`devkit/sim/README.md`](../devkit/sim/README.md)). The commands it names
by Modkit's script names are devkit's: the xemu harness, its sitting kit
and the owner demos `devkit/xemu` (Steps 4.14a2-a3,
[`devkit/xemu/README.md`](../devkit/xemu/README.md)), the certification
`python -m devkit reach l3-certify`, `l3-contact` and `l3-gate`, and the
chain driver, the route pilot and the minigame solvers `devkit/xemu`'s
(Step 4.13d2).

## L3: the game's own step from a snapshot

A **snapshot** is every present user page (VA below 0x80000000, about
5,100 pages, 21 MB) of a running game in xemu, the halted CPU's registers
and metadata. `L3` maps it under Unicorn and runs the game's code,
unchanged:

- **player-tick mode** (the default): the player's per-frame update
  0x8C230 (input build, armor, animation, the state machine, the move code
  0x47380 and its collision), with the scheduler's clock set as
  scheduler_run 0xAB980 sets it. Everything else in the world stands
  still, which is exact on static geometry. 1,000-2,200 ticks per second
  per core (34-75x real time);
- **whole-step mode** (`scene=True`): scene_state_tick 0x55AB0, so every
  critter, rig, trigger and node graph moves too; the per-frame audio
  update 0xADCA0 is stubbed. 80-190 steps per second (2.5-6x real time).
  On a snapshot taken at the scene tick, or (Step X.15) at the player's
  update entry when it holds that thread's stack (format 3, below): the
  first step then finishes the frame the snapshot stopped in, from the
  snapshot's own registers on its own stack (the player's update, the rest
  of the scheduler's events, scene_state_tick's return at 0x566E1 or
  0x5F887 pointed at L3's stop), and the next are whole scene ticks. So a
  chain's joins (update entries) serve both modes. Since Step X.20 a
  whole step also runs the frame's render after the frame's scene ticks
  (below: it moves the cameras and draws from the game's random numbers),
  which costs about 2.5x: 10-17 steps per second a core at load 40-80.

Kernel imports return 0, except NtAllocateVirtualMemory and
MmAllocateContiguousMemory(Ex), which map zeroed regions, and the game's
file reads. Memory at 0x80000000 and above is the snapshot's (format 3:
the thread's stack and the RAM window, mapped page by page as a step
touches them, as taken); elsewhere, or in an older snapshot, a zero page
that taints the run `high:<reader VA>`.
RDTSC reads a virtual clock (733 MHz, a frame a step, 1,000 cycles more a
read in a step), not host time.

**File reads (Step X.15).** In a step the game reads files only through
its stream module (every read in runs from all 46 store snapshots, both modes:
pages of `characters.xbr` and `fx.xbr`, a few KiB each, e.g. after an
attack): 0xA51C0 queues a request on the pending list 0x1AA7F8 and calls
ReadFile (overlapped) on `Z:\gamedata\<name>`, the HDD cache of the
disc's `gamedata` files, and the main loop's poll 0xA58A0 (once a frame)
hands each finished request to its owner, which may read again (into
contiguous memory) or allocate. L3 serves such a read from the disc's file
at the offset asked, at once (the bytes, the OVERLAPPED's status and
count; past the end STATUS_END_OF_FILE), completes the requests a
snapshot holds in flight when it loads, and runs the poll at the start of
each frame after the snapshot's (Step X.20; one a step once frames are
pinned to a tick). The disc is `L3(..., disc=)` (a path to the image in
the tray, or `read(path, off, n)`); by default the vanilla ISO when the
snapshot's disc is vanilla's (`iso_sha12`), and the chain driver passes
the build. A read L3 can't serve (another reader, no disc, a file the disc
lacks) stays zeros and taints the run `read`. On the store's snapshots
the reads now taint nothing and leave every player-tick row as it was.

**The frame outside the step (Step X.20).** After a frame's scene ticks
the main loop 0x58E40 renders the scene (0x5F930 calls 0x54800 with the
scene and the frame's dt), and the render moves the game too: it updates
the active cameras (the level camera 0x81240 follows the player) and
draws from the game's random numbers, the R250 generator 0xB61B0 (250
words at 0x37B4B8, its index at 0x37B8A0) that critters' AI draws from as
well: three numbers for each item it sorts into its draw lists (0xC14D0's
randomized tree, 0xB7E30; by town's rope bridge 146 items, 438 numbers a
frame), the cameras' own and, while a hit shakes the camera, two more.
Whole steps on a format 3 snapshot therefore run the render after each
frame's scene ticks, up to 0x55820 (before its last flush 0x90C80 and
the present 0x8FBE0), with the frame's dt. The GPU is a stub that has done
all it was given: the NV2A's registers (0xFD000000) read 0, but for the
push buffer's GET (0x800044, 0x324C), which reads the last PUT the CPU
wrote (0x800040), and at each such kickoff D3D's GPU time (the dword at
`[[0x135420]+0x3F0]`) becomes its CPU time (`[[0x135420]+0x1C]`), so
D3D's waits for the GPU end at once. The first render comes after the
snapshot's own frame: the main loop's frame on the snapshot's stack (the
slot holding 0x59BAA, 8 bytes above it the loop's locals: +0x14 the
frame's ticks, +0x18 their dt so far) says how many of its ticks are left,
and the main loop's polls (the latches, the stream) wait for that frame's
end too; later frames are one tick each, as the replayer pins xemu's
(below). A snapshot without high memory (formats 1-2) can't render: its
whole steps taint `render`.

**xemu's frame pacing.** The main loop runs as many scene ticks a frame
as the clock asks, up to two (0x59AD0-0x59B53). xemu, slower than the
game under load, runs two to most frames, a mix that varies from run to
run, so the render's numbers fall between different ticks each run: two
replays of one string from one parked start (sitting x20a) parted in the
generator at tick 5 and in the player at tick 281, where town's bridge
insects, which fly on those numbers, met it. Given one such replay's frame
boundaries (its render entries), L3 with the render and the stream poll
once a frame matched it exactly (491 ticks, the generator at every
tick); with the poll each tick it parted at tick 274, since the main
loop's stream poll is once a frame too, so a page streamed during a
frame's first tick reaches its owner a tick later than a poll each tick
gives it. `Sandbox.snapshot` and
`Sandbox.replay` pin it to one tick a frame with the game's own "slow
motion" cvar (0x38C058, +4 at 1; the command line's `-clock1`;
`xemu_oracle.pin_pace`, placed), as a console at full speed runs: two
pinned replays of that string were identical tick for tick, generator
included, and a snapshot taken pinned ends its frame.

**Deterministic xemu (Step X.22).** Sandboxes run the fork build's null
renderer under `-icount shift=2,align=off,sleep=off` by default (the
`azurik-xemu-oracle` skill): guest time follows executed instructions,
not the host clock, so a replay is a function of its start and its input
alone. Sitting x22 (v0.14-12, load 33-39 on 24 CPUs): three replays of
X.12's beach string (106 ticks) from one parked start, two in one xemu
and one after a relaunch, began and ended on the same 128 MiB of RAM
(sha256 of a full dump) and matched L3 in body, state and HP every tick
(the inventory hash differed every tick in player-tick mode, as it had
since X.10: the inventory's first word is the day clock, which the
player's update doesn't advance; since AZ-389 the hash starts past it);
X.15's w1 opening segment (475 player ticks) matched L3 the same way, and
X.15's w2 walk and r1364 pickup (1,067 whole steps by w2's enemies, three
hits) matched it on every observed field every tick. The pacing pin
stays: L3 renders after each whole step, one tick a frame. Replays ran
40-66 ms a tick.

### Integrity and taint (Step X.10)

A wrong positive is caught by the xemu replay; a wrong negative ("no
witness within budget") is not, so L3 guards the ways it can be silently
wrong:

- **The snapshot's code is the XBE's.** Given the XBE, `L3` checks every
  executable, read-only section's present pages against it (the kernel
  thunk slots aside) and refuses another build by name (`the snapshot's
  .text differs from the XBE's in N bytes`): a modded or stale snapshot
  would run code L3 doesn't have. All 38 snapshots in the store passed.
- **The CPU state is the snapshot's.** Each step starts from the
  snapshot's general registers, EFLAGS, x87 control and status words,
  an empty x87 stack and its MXCSR (format 2 records `fstat`, `ftag` and
  `mxcsr` from the gdbstub's 'g' packet; a format 1 file falls back to
  CW 0x023F and MXCSR 0x1F80), so a step is a function of the memory
  and the pad, whatever ran before it.
- **Taint.** `L3.taint` is the set of things the run since the last reset
  read that L3 doesn't model; each `Row` and each saved `State` carries
  it: `read` (a file read L3 couldn't serve: zeros), `time` (a kernel clock: a call or the
  `KeTickCount`/`KeTimeIncrement` variables, whose reads are seen by
  pointing their thunk slots at pages L3 maps on first read), `rdtsc`
  (outside `TSC_UNTAINTED`, the scheduler's event timer 0x21E30, whose
  reads leave every row unchanged at any clock rate), `high:<reader VA>`
  (a zero page at or above 0x80000000), `render` (a whole step on a
  snapshot without high memory: no render, so neither the cameras nor the
  frame's random numbers move; Step X.20) and `kernel:<name>` (a call
  outside `MODELLED`: NtAllocateVirtualMemory, NtFreeVirtualMemory, the
  critical sections (guest code since Step X.42, `NATIVE`), the contiguous
  allocations and RtlInitAnsiString, which are faithful in a
  single-threaded step; and none inside `QUIET` code, the stream
  module's idle handshake 0xB1620 with the HDD-cache prefetch thread).
- **Where a kernel taint came from (Step X.52).** `L3.taint_at` names
  each `kernel:<name>` taint's sites since the last reset (each saved
  `State` carries them): the first return address in the game's own
  code, 0x11000-0xDF660, on an EBP walk from the call (the call's own
  return, then each frame's `[ebp+4]`), so neither an XAPI wrapper
  (CreateFile, WriteFile and their kind, from 0xDF660), a C-library
  frame (fopen, fwrite, fclose, after XAPI in `.text`) nor a word that
  isn't code is the answer; and for NtCreateFile the object name it
  opens; a kernel variable read through its thunk, the reading EIP. At
  most 8 sites a taint.
- **Searches carry it.** A search `Result` holds the union of every
  explored run's taint; `devkit/reach/l3_certify.py` reports a not-found leg whose runs
  were tainted as `inconclusive`, never as a refutation. Measured over
  70 runs from the store: player-tick runs
  were clean or `read` (16 of them, from tick 60 on); every whole-step run
  read high pages (0xDD4A0 searches an array in contiguous memory). Since
  Step X.15 served reads leave those player-tick runs clean, and whole
  steps from a format 3 snapshot read contiguous memory, the stack, the
  TLS and the KPCR as taken: 184 whole steps by w2's enemies tainted
  nothing, so whole-step searches can
  refute too.

### Overlays: a modded build on a vanilla snapshot (Step X.11)

A snapshot holds the build that ran when it was taken. `devkit/sim/overlay.py`
lays another build over it, so L3 runs a modded build's movement from any
vanilla snapshot, at any slider value, with no sitting:

```python
from devkit.sim import overlay
ov = overlay.build(vanilla_xbe, {"player_physics": {"jump_speed_scale": 1.25, "gravity": 4.9}})
ov = overlay.Overlay(built_xbe, (("critters_critter_data", "garret4", "runSpeed", 10.5),))   # or a built XBE and cells
sim = L3(snap, vanilla_xbe, overlay=ov)                    # the snapshot is checked against vanilla first
```

- **The XBE:** every byte a section of the build holds otherwise than
  vanilla's (code, `.rdata` constants, a section the carve allocator grew
  into its padding) is written where the snapshot holds what vanilla's
  loader put there, through `L3.write` (so no stale translation runs);
  each section the build appends (`SHIMS`) is mapped where the XBE loader
  puts it. Refused by name: a changed byte the snapshot holds otherwise
  (live `.data`, or another build's snapshot), an appended section over a
  page the snapshot or L3 maps, a change at an instruction L3 hooks by
  address, a moved or dropped section. The XBE header (the section table,
  which the kernel's loader reads, not the step) stays the snapshot's.
- **The config cells:** config.xbr was read at boot, so a slider's cell is
  poked where the game holds it (`overlay.CELLS`): garret4's `runSpeed`
  into its CritterData (+0x40, f32; the player's species
  `[critter+0x178]`) and each air shield's `Flaps` into its row of the
  armor slot vector 0x38C4D4 (+0x38, the int32 the loader 0xF5A40
  truncates to). Another config slider is refused by name.
- **Whole steps** pass the main loop's timestep from memory (0x1983E8,
  fps_unlock's Patch 3) instead of 1/30.
- **Searches:** a `Segment`'s `overlay` runs its search on that build
  (part of the problem's identity); a pool worker keeps the simulators of
  its last four overlays, so a bisection over slider values reuses its
  pool. `devkit/reach/l3_contact.py` measures the randomizer's contact flights
  that way ([`devkit/reach/README.md`](../devkit/reach/README.md#l3-contact)).
- **The copies:** a constant the game copied out when the world was built
  is rewritten where it went, where the snapshot holds vanilla's value
  (`overlay.COPIES`): the world clock's quantum, copied from 0x198410 into
  the player's scheduler at 0x51BFB, which 0xAB830 snaps event times to.
  fps_unlock sets it to 1/F; left at vanilla's 1/30, a ledge mount's state
  0x100 (the step-up) never ended at 60 fps, while on the real 60 fps
  build's own snapshot it ends after 176 ticks, as now on the overlay.
  Another copy goes unseen, and level files are the snapshot's own.

Checked against numbers xemu measured on built ISOs (no sitting): at
`jump_speed_scale` 1.5 and gravity 4.9 the jump's apex is 2.3933 m in 60
airborne ticks (xemu s2: the same), launch 4.9249 m/s; vanilla's 1.0235 m
in 28 ticks; on f6's flat ground the walk ramps 3.2669, 6.5361, 7.0001
m/s (xemu s6) and at `walk_speed_scale` 2.0 3.2669, 6.5361, 9.8028,
13.0715, 13.9999 (the ground acceleration cap, then runSpeed 14).

**Validation (sitting x11, 2026-10-14):** the vanilla disc and each
build booted at `vanilla-ig-w1`'s SaveGame #1; a check string (a teleport
onto the vanilla boot's spot, 30 ticks at rest, a 40-tick walk, a running
jump, a landing, a stop: 151 ticks) ran in L3 on the vanilla boot's
snapshot with the build laid over it (the very ISO xemu booted: its
`default.xbe` and its config.xbr cells) and in xemu on the real build:

| Build | Ticks | Max error (m) | States, HP | The overlaid memory against the build's own snapshot |
|---|---|---|---|---|
| `jump_speed_scale` 1.25, gravity 4.9 | 151 | 0.0 | equal every tick | `.text` (979,412 B, the carve's 4 B tail too) and `.rdata`: 0 bytes differ |
| `fps_unlock` 60 | 151 (60 a second) | 0.0 | equal | `.text`, `.rdata` and `D3D`: 0 bytes differ |
| `walk_speed_scale` 1.5, air shield 1 `Flaps` 3 | 151 | 0.0 | equal | the same, and `runSpeed` 10.5 and `Flaps` 3: the cells the build loaded |

Only the inventory's hash differed (the day clock of two boots). The
replayer counts ticks at the main loop's rate (0x1A28C8: 30, or
fps_unlock's F), so a 60 fps build replays too.

### Snapshots and the private store

Guest RAM holds console key material, so snapshots are private:

- they live only in the **store**, by default the user data dir's
  `AzurKit/l3-snapshots` (macOS: `~/Library/Application
  Support/AzurKit/l3-snapshots`), or a folder you give (`--store`,
  `l3.store(folder)`). The store is made mode 700 and a folder anyone else
  may enter is refused; each file is mode 0600;
- never committed: `.gitignore` lists `l3-snapshots/` and `*.l3snap`, and
  the leak guard (`tests/_leak_guard.py`, the pre-push hook) refuses any
  file that starts with the snapshot magic `AZL3SNAP`, whatever its name;
- never printed: tools print lengths and `sha256[:12]`; positions stay in
  the file. Tests use synthetic snapshots only;
- never deleted while something starts from them (AZ-720, Step X.83): a
  cleanup deleted the start a running reach-engine run read by its bare
  label (`--snapshot LABEL`: `lsof` sees nothing open between jobs) and
  every start `proofs.jsonl` names. `devkit.sim.l3_hold` holds each
  snapshot in the store's `reach-live` folder (the reach engine's
  per-level starts, all 22 levels since X.83 took airship's on xemu
  0.16.4) or a `reach-live-*` folder beside it, each one a running
  process's command line names (bare or as a path) and each start the
  `proofs.jsonl` of the main checkout or a lane names (`git worktree
  list`). `$EV/tools/prune` reads it (its R5 rows;
  `--apply` never deletes a path holding one), and any other cleanup of
  the store asks first: `uv run --locked python -m devkit sim l3-hold
  --check PATH ...` (or `prune --check`) exits 1 naming each held
  snapshot at or under a PATH. A start that is gone can't be restored: a
  re-take has another `meta_sha12` (it hashes the clock and the xemu
  build), so the reach engine's cache re-keys that level's jobs, and a
  proof (none of the 21 starts `proofs.jsonl` names was left on
  2026-10-24) is re-taken from its record's recipe, not its file: a
  sitting runs the record's `start.setup` up to the snapshot (the load,
  the R7 hop, the R2 kit; `python -m devkit reach l3-certify sitting DIR W snapshots`), its
  string re-runs in L3 from the new
  snapshot and replays in xemu (`sitting DIR W replays`), and `apply`
  writes the record with its new ref (`<sitting>/<string
  sha12>@<new meta sha12>`) and the authoring's `proven` mark.

The file is `AZL3SNAP`, a u32 header length, a JSON header (`format`,
`regs`, `runs` as `[va, size]`, `meta`), zeros to the next 4 KiB boundary
and the pages (format 2, Step X.10). Format 3 (Step X.15, the default of
`Sandbox.snapshot(high=True)`) adds runs at or above 0x80000000 after the
user pages: the halted thread's stack (present pages from ESP's to the
TIB's StackBase, fs:[4]) and guest RAM as the kernel's window at
0x80000000 maps it (two pages checked against the gdbstub's view): 128 MiB
on the D98 config, kernel memory, private like the rest. Since Step X.22
every page comes from one dump of guest RAM (QMP `xemu-dump-ram` into W,
mode 0600, deleted at once), each user page through the page tables the
dump holds (`l3.ram_reader`): 152 MB in 0.16 s where reading the user
pages over the gdbstub took 1.9 s, the same file byte for byte. `read_snapshot` maps a format 2 or 3
file's pages read-only instead of reading them, so every worker that loads
one snapshot shares one copy in the page cache; L3 copies only the user
pages up front. A format 1 file (no `format`, the pages right after the
header) still reads, and an unknown format is refused by name. `meta` holds the label, `at`
(`update` or `scene`), the player's `entity`, the `level`, the body
centre `pos`, `state`, `hp`, the event clock `clock` and `start_sha12` (a
hash of the entity and body: the replayer's start check), the loadvm
`tag`, the `xemu` build, the disc's `iso_sha12` and the time.

Take one in a sitting (the `azurik-xemu-oracle` skill's sandbox):

```bash
uv run --locked python -m devkit xemu oracle loadvm <W> vanilla-rz-new
uv run --locked python -m devkit xemu oracle snapshot <W> w1-start [--scene] [--hold] [--store DIR]
```

It runs to the player's next update entry (`--scene`: the next scene tick
entry) and writes `<store>/w1-start.l3snap`; a label is never reused.

### The API

```python
from devkit.sim import l3
from devkit.sim.l3 import L3, Pad

snap = l3.read_snapshot(l3.snapshot_path("w1-start"))     # l3.read_meta(path): the header only
sim = L3(snap, xbe, zone_at=router.zone_at)                # xbe: the vanilla USA default.xbe
sim.teleport(feet, yaw)                                    # the game's own R6 place request; cell= the room
start = sim.save()                                         # this state, to come back to
rows = sim.run([Pad((0.0, 1.0))] * 30 + [Pad((0.0, 1.0), frozenset({"y"}))] * 4,
               until=lambda r: r.zone == "w1.Z013")
sim.reset(start)                                           # milliseconds; sim.reset() = the snapshot
```

- **Inputs:** one `Pad(stick, buttons, yaw, cam)` per tick: the left stick
  (x right, y forward, the pad's -1..1 floats), the buttons held (`a b x y
  black white lt rt lstick rstick start back`) and the camera yaw in
  radians (the game's: yaw a looks along (-sin a, cos a)); `yaw=None`
  keeps the step before's camera, at first the snapshot's; `cam`, the
  camera as the exact f32 pair the input builder reads, wins over `yaw`
  (a recorded string's). `l3.pads()` builds a string from run-length
  segments `{"n", "stick", "buttons", "yaw" | "cam"}`, the JSON form
  `replay` and the proof records hold. What a real pad gives (the round
  gate, the axis snap, the camera's 3.33° a tick) is
  `devkit/sim/inputs.py`.
- **How they enter the game:** the pad's floats go into the active
  ControllerState at the player update's entry; from the second step on,
  L3 first does what the main loop's poll 0xA2880 does with no pad held:
  a button whose float read 0 on the frame before gets its latch cleared,
  so a held Y fires once until a frame after its release. The latches are
  otherwise the game's. The camera, which the game moves outside the step,
  is the ground direction the input builder reads at 0x85276 (two f32 at
  [esp+0x14]; its yaw is atan2(-x, y)).
- **Steps:** `step(pad)` runs one frame; `run(pads, until=)` a string,
  stopping after the first row `until` accepts (a goal reached, a death).
- **The trace:** each step returns a `Row`: `k` (0 = the snapshot's own
  tick), `pos` the body centre critter+0x15C (the feet + 1 m), `state`
  entity+0x94, `hp` critter+0x210, `zone` (`zone_at(feet)`, e.g. the
  route planner's `Router.zone_at`), what a replay needs: `writes`
  (the VA and bytes written at the update's entry) and `cam` (the camera
  direction the input builder read); then `taint` and `obs`.
- **One observation reader (Step X.10):** `obs` is an
  `devkit/sim/obs.py` `Obs`, read through any `read(va, n)` by the one
  field table both backends use at the same RET: the body centre (and
  `feet`, 1 m under it), the velocity entity+0x24, state, HP and its
  maximum, the flaps used entity+0xD8, the camera direction the input
  builder read (and `cam_yaw`), and (Step TD.0, in the light read the
  search's workers use too, for the trick explorer's cells and detectors)
  the stored contact normal entity+0xB8 (`normal`: the classifier 0x85920
  writes it; in the air it holds the last contact's), the fall reference
  +0x168 (`fall_ref`), the state time +0x9C (`state_t`), the animation
  index critter+0x200 (`anim`), the air gauge armor_mgr+0x24 (`gauge`) and
  the equipped armor's Level and Flaps (`armor_level`, `flaps`); with
  `deep` (the default; a search's workers go without, about 40 reads a
  tick), the element levels (the kit), a hash of the inventory's 0x1D4 saved
  bytes past its day clock (the first word, which player-tick L3 doesn't
  advance; AZ-389) and a hash of the global latches (the flags: the map at
  `[pd+0xE4]`, a tree of name and value pointer the shared.sav writer
  0x5E8A0 walks). `obs.digest` hashes one (coordinate-free) and
  `obs.compare` two traces field by field (its `first_diff`, which a
  pickup proof reads, judged on the fields before TD.0's: `obs.JUDGED`).
  A whole-`Obs` digest from before TD.0's fields doesn't compare with a
  new one (the corpus compares the CORE digests).
- **The face a contact touched (Step TD.0):** the entity keeps the
  normal but no face, so `devkit/sim/faces.py`'s `Faces` (a level's
  collision triangles in memory, from `geometry.Level`: `Faces.read(iso,
  level)` or `Faces.of_level(lv)`) answers `face(point, normal)`: of the
  solid faces (`gameSolid` in the word: no water, push, damage or trigger
  volume) within 1.5 m of the point (the body centre) whose front normal
  agrees within 2° and that the point is in front of, the nearest, as a
  `Face` (its id in the level's
  triangle order, owner, collision word, `slippery`, `climbable`,
  `spring`, nz and distance; no coordinates), or None (an edge or vertex
  contact, or a moving platform away from its load-time place). About
  0.2 ms a query on e6 and w1 (194k and 237k faces).
- **A kit:** `kit_writes({"air": 1, ...})` are R2's element-level writes
  into the inventory (`recipes.element_levels`, RAM_RECIPES §3) for a step's `writes`, so the
  replayer writes them too; the armor itself is cast by input, LT+Y for
  a tick (on the tick after the release: Level 1-3, Flaps 1/2/5, gauge
  1.0, 2 air fuel at air 1). Each flap spends 1/Flaps of the gauge and
  the last one drops the shield; a recast (LT+Y, in the air too) refills
  the gauge but not the jump's flap count, so a jump never flaps more
  than Flaps times.
- **Teleport:** `teleport(feet, yaw, cell=None)` writes the place struct
  to Continue's buffer 0x39014C and the request R+8 (RAM_RECIPES §5.2);
  0x855D0 consumes it in that step's player tick and puts the body centre
  1 m over `feet`, airborne, in `cell` (default: the player's current
  cell, `[critter+0x158]`). One snapshot per level serves many starts.
- **Reset:** L3 owns the guest memory: one buffer mapped page for page
  (`mem_map_ptr`), compared with the snapshot's pages and copied back with
  numpy in place. `save()` keeps the pages that differ from the snapshot (a
  few dozen after a hundred steps) and the regions mapped since;
  `reset(state)` unmaps the regions, rewrites only the pages that differ
  and drops their translations, so unchanged code keeps its translations.
  A rerun after a reset is bit-identical. 1-2 ms (4-6 ms before X.10).
- **Writes and translations:** Unicorn 2.1.4 keeps running code it
  translated before a host write (the engine review's smc bench), so
  `write()` and `reset()` call `ctl_remove_cache` over what they rewrite
  (about 1.7 µs a page): a code poke takes effect on the next step, a
  reset brings the old code back.
- **The step's timeout** wakes no thread per step (Step X.42): `arm`
  stores the step's deadline under a lock no thread waits on, and one
  thread per `L3`, looking every 25 ms, stops a step past its deadline
  with `emu_stop`, so a runaway raises `L3Error` at most a period late.
  The thread checks the deadline again and stops under that lock, so a
  stop never lands in a later step: a stop from another thread is
  inexact (EIP can rest on a read-modify-write whose write landed), so a
  stopped step can't resume. Unicorn's `emu_start(timeout=)` starts a
  thread per call (92-205 µs against 4-12 µs in the engine review's
  bench1); before X.42 a notify woke the watchdog every step. The thread
  holds its `L3` weakly and ends with it. `meta_sha12(meta)` names a
  snapshot's state (its metadata without the label and time).
- **Two kernel calls run as guest code** (Step X.42, `NATIVE`):
  RtlEnterCriticalSection and RtlLeaveCriticalSection are
  `mov eax, 0; ret 4` written at their kernel addresses, unhooked: the
  hook's return (EAX 0, the argument popped, the flags kept) without a
  Python call: a whole step's kernel calls fell from 458 to 0.8 (f6) and
  from 910 to 2.8 (town). A step runs the game's one thread, so no other
  thread holds or waits on a section; they no longer count in
  `kernel_calls`.

**Throughput (Step X.42).** One process under `nice -n 15`, the same
snapshots before and after, runs interleaved, the rows identical: 2,000
player ticks (walk, jump, turn; `deep=False`) on `x6-side-153803` and
40 whole steps each on `x15g-f6-k0-070644` and `x15g-town-k0-070703`,
after a 5-step warm-up (Step X.42; the
ratio is of the means):

| Load (1 min, 24 CPUs) | Player ticks/s | f6 whole steps/s | town whole steps/s |
|---|---|---|---|
| 19-20, before | 934, 750, 740 | 21.8, 21.9, 21.7 | 11.9, 11.8, 11.8 |
| 19-20, after | 992, 785, 992 (1.14x) | 24.4, 24.4, 23.5 (1.11x) | 13.4, 13.5, 13.2 (1.13x) |
| 37-42, before | 206, 282, 271 | 9.8, 7.7, 11.3 | 5.2, 6.1, 7.1 |
| 37-42, after | 290, 425, 597 (1.73x) | 10.0, 12.2, 14.6 (1.28x) | 6.2, 8.1, 8.3 (1.23x) |
| 21-25, before | 435, 432, 410 | 16.0, 15.6, 18.5 | 8.5, 9.9, 10.0 |
| 21-25, after | 823, 775, 657 (1.76x) | 19.1, 21.5, 17.7 (1.16x) | 9.3, 11.4, 9.5 (1.06x) |

The 19-20 and 37-42 rows' "after" ran a watchdog whose stop took no
lock; the 21-25 rows run the code as it is.

The conformance corpus re-ran unchanged: each of the 588 records whose
snapshot and disc are still kept (407 whole-step and 101 player-tick
passing ones among them) gave the same trace before and after, four
workers at a time, except whole-step records on three x8 snapshots
whose first, cold render passed its 5 s cap at that load (four in a
run, up to six); re-run alone (tick 0 in 0.4-0.9 s), those six passed
with the same trace before and after. Since Step X.52 an `L3`'s first
render (its code not yet translated) gets 60 s and every later one 5 s.

**Faults by site (Step X.52).** An `L3Error`'s `site` names it by kind
and place: `assert <file>:<line>`, `unmapped@<EIP>` (another CPU error:
its Unicorn name, e.g. `insn_invalid@<EIP>`), `runaway@<EIP>`, `render
timeout@<EIP>`, `no player update`, `no scene return` or `place not
consumed` (`other` for one raised without a site); it survives pickling,
so a pool worker's error keeps it.

**Level exits (Step X.52b).** A levelSwitch's fire (0x6F050, the switch
in EDI) only posts the level request (its movie, level and spot into
0x38D320); a tick or two later the scene tick takes it and unloads the
level, 0x542E0(scene, 0) (from 0x55F46, or 0x55EF3 for 'last-save-spot'; a death is
0x542E0(scene, 1)), which writes the level's state to `z:\scratch`
(0x52A10) and loads the next level, whose loader waits on threads L3
doesn't run, each wait spinning to the step's cap: Step X.52 traced
TD.2's exit-tainted misses there (6 seeds by their callers and files,
the other 28 by the same taint signature). So L3 records each fire (`L3.fires`,
`(step, level, movie)` since the last reset) on its step's row
(`Row.exit`, the level and movie paths) and lets the tick finish; a step
that reaches 0x542E0 with flag 0 stops at its entry and raises
`LevelExit` (an `L3Error`, site `level exit`): no save, load, wait or
taint. A search and the explorer end a branch on a fire's row (the goal
still tests that row) or at that stop, like a death: no fault, no taint,
counted by the level it loads (`Result.exits`; `unload` for the stop),
and a miss's verdict names them (`the step budget ran out; 12 branches
fired levels/earth/e2`): no branch that stayed in the level reached the
goal. No exit is a hop's arrival (every hop's goal is in its snapshot's
own level), so ending there loses nothing.

**The engine version (Step X.52b).** A problem id hashes the start, the
goal's spec and the search's shape, never code, and Step X.52 found 12
engine commits that moved TD.2's runs under the same ids. So every
search's and exploration's summary, and each problem's result from
`solve_many` and `explore_many`, carries `l3.engine()`: `sha12`, sha256
of the engine's code and data (`l3.ENGINE_FILES` under the checkout:
`devkit/sim/` and the randomizer's `draft/`, `data/`, `physics.py`,
`art/collision.py` and `live/`'s `pages.py` and `recipes.py`, a folder's `.py`, `.toml`, `.json` and `.gz` files at
any depth; a goal names its reach model only by its pickle's path, which
follows the level's zoning, so a model fix that keeps the zoning keeps
the problem id; `proofs.jsonl`, which no run reads, isn't hashed) and
Unicorn's version; `unicorn`; and
`caps`, the wall-time caps a step runs under (the scene tick's 10 s, the
player update's 2 s, a render's 5 s and the first one's 60 s, the stream
poll's 2 s, the watchdog's 25 ms period). `l3.comparable(a, b)` holds
only for the same `sha12` and no fault on either side: a fault is a cap
or a step L3 can't run, so a run with faults isn't reproducible even on
one engine, under another load (X.52's fault-free d2 and a3 re-runs
gave R1.29f's costs exactly; its re-runs of TD.2 differed only in the
problems with faults).

### Searching (Step X.7, D170)

`devkit/sim/l3_search.py` searches an input string from a start to a
goal under the game's own code: Go-Explore over cells (a zone, a 2 m grid,
1.5 m in height, in the air or not), seeded by the route planner's plan and
earlier winners, guided by a goal's cost to go and heading (the
randomizer's goal is Modkit's `randomizer/draft/l3_goal.py`'s
`RouteGoal`: Dijkstra back from the goal over the level's route graph, or
the straight line to where that field reaches when the derive modelled no
way), each segment `n` ticks of one heading with Y held for a jump. It
knows only a simulator (`step`, `save`, `reset`), rows and the `Goal`
protocol; `sim` imports nothing from the randomizer.

- **A pickup's goal is the game's touch (Step R1.16e, AZ-483):** with
  `touch` (`l3_goal.item_touch`: the species' radii from config.xbr's
  `critters_engine`; a number instead is the disc's radius, R1.29's
  `search --touch`), `RouteGoal` takes a location when the body centre,
  HP above 0, in any state, lies in the item's own touch ellipsoid round
  where it rests (`item_centre`: fallen onto the surface below its
  point), not 0.75 m round the point (docs/RE_DATA.md "Pickups and exit
  triggers"). Only whole steps run the item: its generator spawns it
  while the player is in its cell and near it, and player-tick L3 never
  takes one, so `devkit/reach/l3_certify.py`'s whole-step check reads L3's own
  inventory (`outcome_at`, `scene_outcome`).
- **An exit's goal is the game's trigger test (AZ-483):** `ExitGoal`
  takes the body centre inside one of the trigger meshes its gate hint
  touches (`l3_goal.inside_mesh`: the first triangle straight above it
  faces down), not the feet in the column under them; a gate beyond the
  touch (a switch, a timer's `{>=N}` seconds, its `wait`) only whole
  steps run: there `l3_certify._verify` ends at the levelSwitch's fire
  (0x6F050, `L3.fires`) as the exit's outcome, after a neutral tail (plus
  the timer's wait) when the string alone doesn't fire it; a fire of the
  exit's own level in that tail meets the leg (`outcome_own`). `ObjectGoal(inside=True)` is the same touch of any shape: the
  chain's touch events take it only for a shape a standing body centre can be inside (`l3_goal.holds_body`, a trigger
  volume); a platform the player stands on (d1's walkway generators' bases) is stood on, the event's object is the
  record its flag names (`chain.event_object`: d1 has four `BeamShape`s), and it counts done on its own touch,
  or when a toggle its touch drives (`chain.toggles`) rose, off before the approach, at a tick the toggle's OR
  reads its input from this touch on (AZ-501: d1's are 3 s switches each fed by a beam and two walkways, so a
  toggle on alone doesn't show the event's own touch). Sitting R1.16e: the inside approach took the body centre into d1's
  walkway bases and `BeamShape` r451 only falling past their sides, 3 of 3 to the player's death [inferred].
- **Flap flights (Step R1.29e):** in the air `RouteGoal.toward` follows the
  flight the body is on (a flight of the goal's cheapest ways whose
  takeoff floor is the fall reference's height, entity+0x168, and whose
  track passes within 2 m: toward its landing) and flaps by the
  descent-flap rule: falling, a flap left in the jump and gauge, inside
  the flap ceiling and the descent bound the game's own peak_z sets
  (entity+0x164, `Obs.peak_z`: d = peak_z + 1.2 − z, z the body centre,
  over 0 and under 6; for a jump from a floor 2.4 m over the takeoff and
  3.6 m under it; a lower flap is a descent flap, half its lift, the gauge
  emptied and the shield dropped, RE_MOVEMENT; a walk-off keeps the last
  jump's peak_z, a springboard's is its launch's), and short of the landing
  (under it, or falling to it at 7 m/s would stop short). Near a flap
  flight's takeoff with the gauge under 1 it asks for a cast (a fourth
  item, True; at the takeoff itself, at rest), which the search runs as a
  3-tick segment of LT+Y; its cells keep the flaps left in a jump (in the
  air) and whether the gauge is full, so a string that spent its flaps
  stands in for none that kept them. The trick explorer's guides
  (`TrickGoal`, `TrickExitGoal`) inherit the flaps but ask no cast
  (`casts = False`: its moves have none, so a takeoff keeps its heading
  and jump).
- **A climb's cost (Step R1.29e):** a body climbing (state 1) stands on no
  vertex, so its cost was the floor under it plus the way up to it at walk
  speed (or the nearest vertex and 2 s, or the far fallback and 4 s) and
  rose as it climbed, and the cell picker shunned climbs (a5/g0/r1773's
  way back). `RouteGoal` now gives it the climb edge's own cost (the
  goal's climb link within 4 m of it whose ends' heights hold the feet)
  interpolated by height, from the foot's cost to the top's, and heads it
  into the face.
- **No row undercuts the start (Step X.53, AZ-578, AZ-581, AZ-582):** the
  searchers anchor the goal at their start (`RouteGoal.anchor`, from
  `l3_search.search` and the explorer's root): when the goal's field
  reaches the start, a row the field holds only by a vertex nearby (2 s
  more) or the far fallback costs at least the start's cost plus 4 s, so
  the straight line through air, walls and floors no longer undercuts
  the graph (L18a's best fell 18.7 m under the dock at 15.9 s against the
  dock's 23.5 s; at hop 13, 55% of sampled off-graph vertices cost less
  than the start). A row standing or swimming takes only the vertex and
  the zone at its feet (`Router.locate`'s and `zone_at`'s `fallback`
  off, the explorer's zone rule): a body on a top the model doesn't hold
  (hop 5's gear, 6.5 m over e6.Z043) is on no floor, not credited with the
  floor under it, and reaches no zone goal there. A row in the air on one
  of the goal's flights (as `toward` follows it) costs the flight's
  landing plus the time still to land, and its stall names that flight
  (`flying #k`), not the floor under it (AZ-581's #3701), only while its
  arc can still land there (Step X.54, AZ-621: `l3_goal.air_time`, its
  rise and the flaps left under the flap ceiling up to the landing's
  floor less the 0.8 m rim step-up, the gap within walk speed of the time
  it has, 1 m given; a descent flap lifts a quarter of a flap, the game
  halving its launch speed). The time is the gap at walk speed or the fall
  onto the landing, whichever is longer, so a body over the landing costs
  more than one standing there, and over it the guide heads on along the
  track; one that can't land (a spent flap under the ledge) costs and is
  named by the floor it falls to, and steers toward the cheapest vertex
  near it. Best
  costs before and after this step don't compare; stalls compare by edge
  id and zone.
- **Rides, teleports and held rigs (Step X.53, AZ-592):** the guide
  stands at a ride's source vertex (within 0.8 m) instead of running at
  the deck, and a body standing in one of the goal's rides' columns with
  no floor of the model at its feet is on the ride: it costs the far
  end's cost plus the ride's rest by height (as a climb does), stands
  until its feet are within the router's step of the far floor's height,
  then heads onto it (stage `riding`). The route graph links a teleport
  (`Reach.teleport_edges`, confidence data; skipped before) from the
  source node's vertex nearest the pad its `why` names to the
  destination's vertex nearest the playerLocation's spot, costing the
  walk into the pad plus `TELEPORT_S` (1 s); the guide heads into the pad,
  and a plan's teleport leg walks into it. The light trick graph doubts a
  teleport that fires only once other pads were touched (its `flags`,
  `pads first`: e2's catalisk pair), since an explorer's start may not
  have them. The probe-needed rides of the
  rigs a level's authoring holds (`[rig_held]`, as `author` keeps them
  out of logic) are out of the logic and phys route graphs (certify's
  guides) and doubted in the light trick graph (`held rig`), whose job
  is finding what the logic lacks (f3/r1002's guide way no longer rides
  PlatformShape's held #14695).
- **Reproducible:** the budget is emulated steps (`Limits.steps`;
  `wall_cap_s` is a safety net whose verdict, `wall-cap`, is never a proof
  of absence; by default, Step X.52b, the steps at 4 a second,
  `WALL_RATE`, under the slowest whole steps measured, 5.8-6.2 a second,
  which R1.29f's fixed 4,000 s cap cut at 23-30 k of 30 k steps; the
  explorer's the same), the stream is `random.Random(seed)` and the archive iterates
  in insertion order, so the same start, goal, limits and seed give the
  same string. `solve()` runs one search per seed in parallel processes,
  seed `i` derived from the problem (the snapshot's metadata hash, the
  start, the goal factory's spec, the search's shape), and merges in seed
  order: the lowest index that reached wins, whatever finished first (on
  the worker pool below).
- **Faults:** a rollout whose step raises `L3Error` (a game assert, a
  fault, a runaway) ends only that branch; they are counted, and by site
  (`Result.fault_sites`, Step X.52; the explorer's `Result` too). A level
  exit is no fault (Step X.52b, above): its branch ends, counted in
  `Result.exits`.
- **Taint:** the result's `taint` is every explored run's (above), with
  its kernel calls' sites (`taint_at`): a search that found nothing
  refutes only when `taint` is empty.
- **Stalls (Step X.52):** a search keeps its best cost to go every
  `Limits.steps / 20` steps (`Result.curve`), and one that ends without
  the goal names its stall (`Result.stall`): the least-cost cell's cost
  and ticks and, from a goal with `ahead(row)` (`RouteGoal`'s), its zone
  and the first region edge on the goal's cheapest way from it, by index
  in the router's `edges`, kind and confidence and the zones at its ends
  (kind `walk` when the way crosses none, `off the graph` when no vertex
  near it has a cost); no positions. `Limits.plateau` ends a seed after
  that many steps without its best cost to go falling by 0.1 s, `plateau
  at #24 jump (assumed) f3.Z012>f3.Z254`: a cut of the same run (seeds
  and strings unchanged until it), so like `steps` it is no part of the
  problem's identity. Since Step X.52b the record (`l3_search.stall_of`)
  also names its `stage`: `flying` (in the air on the goal's flight, its
  edge named, Step X.53; one its arc can still land, Step X.54), `on no floor` (it stands or swims on no floor of
  the model, Step X.53), `no zone` (the cell stands or swims where the
  zone rule reads none: AZ-538's rig decks and arrivals), `off the graph`
  (with `steer`, the zone of the vertex the far fallback heads for, and
  the way on from there), `walk` (with `into`, the first other zone on
  the walk) or `edge`; the best row's `state`; and whether the best cost
  still fell: `last_fall`, the step of its last 0.1 s fall, and
  `fall_10k_s`, its fall over the run's last 10,000 steps.
  `stall_name` puts it in words (`in no zone: off the graph, steered to
  <zone>: the walk to the goal into <zone>`). The
  explorer's `Result.stall` is the same record for a target problem's
  seed that didn't find.
- **Verdicts:** `reached` (confirmed from the start, `settle` ticks at
  rest still in the goal), `a seed string`, `exhausted` (no new cell in
  `exhaust` rounds: the logic is wrong or the move set misses a way), `the
  step budget ran out`, `wall-cap`; the result counts the cells it left at
  the tick cap (`capped`, Step R1.29e: their strings reached
  `Limits.ticks`, so they are never picked again). `robustness()` grades a winner under
  jitter (each jump a 30 fps tick off, `round(F / 30)` ticks at the
  build's F fps, AZ-388; each heading 2° off).
- **The move set and a flap budget (Step R1.8g, D183):** a segment
  holds Y for a jump (in the air, a flap), taps BLACK for a roll
  (`Limits.roll`: the share of segments that start with one; Y during
  it is a roll jump) or holds LT+Y for an armor cast (`Limits.cast`: a
  recast refills a spent gauge). Swimming, a segment may hold BLACK
  throughout: a dive (`Limits.dive`, Step R1.29: A, B and BLACK sink at
  walkSpeed, X and Y rise, RE_MOVEMENT), for a pickup under the surface;
  `RouteGoal(dive=True)` then counts a swimming row's depth still to go
  at 5 m/s, since the route graph's water is its surface.
  `Limits.flaps` caps the flaps in any one jump: the search never
  presses Y in the air at the cap, a branch past it ends, and a
  winner's `Result.flaps` is the most it used in one jump.
  `Segment.kit` is the kit set at the start (R2's levels, then the cast
  when it has air), so one snapshot serves every kit. The budget, the
  move shares and the kit join the problem's identity only when set (an
  X.7 problem keeps its own). `devkit/reach/l3_certify.py`'s skip ladder
  (`plan-skips`, `search-skips`, `apply-skips`) searches each skip at
  0 flaps with no air, then 1 flap with air 1, 2 with air 2 and 3 or
  more with air 3 (its top rung first: is it reachable at all?); the
  first rung that reaches and holds in whole steps sets the air its
  `requires` asks, and its robustness its difficulty (D177, D259: 0.50
  standard, 0.05 hard, else frame-perfect; P13's 0.95/0.80/0.50 until D259).
- **Chained segments (D172):** a `Segment` names its start: a snapshot, a
  teleport, settle ticks and earlier strings as a prefix (and, Step R1.29e,
  a `tail` of fixed pads after it, `l3.pads` segments: a douse and the
  strings after it; the camera ends at its last yaw; it joins the
  problem's identity). The loop is
  snapshot in xemu, search here, replay the winner there from the same
  halted state, then `Sandbox.snapshot(label, here=True, parent=...)`
  exactly where the replay halted (the next tick's update entry), so no
  tick between two segments goes unrecorded; `devkit/xemu/chain.py`
  drives it (§ "Chains" below).

### A douse in whole steps (Step R1.29e)

`devkit/sim/douse.py` is `devkit/xemu/chain.py`'s `Chain.staff` recipe
as a closed-loop controller on L3: from a row, it turns to the barrier's
shape (12 ticks at a 0.15 stick toward its centre), casts the staff's
elements (LT from tick 14, each element's button for a tick from tick 16,
3 ticks apart, LT released after the last), then walks toward the shape's
mirror point, A held 4 ticks every 24, until the feet stand in the
crossing's to-node for 8 ticks (at most 300 ticks of walking). Each tick's
pad is decided from the row before it, so a start gives one fixed pad
string, which xemu replays as it is (D170). Only whole steps run a
barrier's node graph, so it runs in whole steps. `devkit/reach/l3_certify.py
search --scene --douse` makes a leg through a barrier on the logic's way
(a level edge's `through`, on the way there or back) three in one: a
search to within 3 m of the shape on its near side (`ObjectGoal`), the
douse, a search on to the leg's goal (`Segment.tail` holds the douse);
the leg keeps the three as `parts`. A barrier not in the way where the
search reached it (`douse.in_the_way`: crossing to the body's mirror point
through the shape's centre doesn't lower the to-node's cost to go, as
`Chain.staff`) is crossed by nothing.
First run (f1/g0/r1693, f1.flameSpout15, water 1, 600 steps a leg, one
seed): 39 ticks to the wall, the douse through in 78 ticks with 2 attacks,
194 on to the obsidian; R1.29c's search without it plateaued 7.4 s short
at 60,000 steps. Standing still, one basic swing opens that wall from
2.70 m of its mesh (the feet, horizontally) and not from 2.77 m, under
the derive's `ATTACK_REACH` of 3.0 m (AZ-416).

### Logic pokes in whole steps (Step R2.19h2)

`devkit/reach/engine/triggers.py`'s `Runtime` finds a level's node graphs in an L3 sim (world +0xDC and
+0x108..+0x10C; a graph's nodes in record order: `docs/RE_XBE.md` § "Rig triggers") and `Runtime.hold(pokes)`
writes each poke (a node attribute and its dirty bit, as a link does) at the entry of every pass over its graph
(0x663B0, a code hook added from outside, so `CORE_FILES` and the reach engine's cache keys are unchanged) until
`hold([])`: a pad's touch, which the collision object zeroes each frame, is seen by the pass. `Runtime.deck` reads a
platform's collision object (node +0x20) and `Runtime.pose` its world matrix. `devkit reach rig-triggers witness`
runs on them.

L3's step caps are wall-clock, so a slow step's fault depends on the machine's load and on the process's past. A
poke that starts a stream load (e6's mirror switches: 330 `MmAllocateContiguousMemoryEx` calls in one step, each
mapped as a Unicorn region of its own) spends most of its time in those maps, whose cost grows with the regions the
process has mapped (the high pages stay mapped across resets): e6's took 0.75 s of wall in a fresh process and 2.4 s
after a 600-tick baseline and one poked run, at a load near 40, and under more load or later in a worker it passed
the 5 s render cap ("render timeout@0xF4EDF", the allocator's return), which the first all-level witness took for a
dead try. A run that needs its verdicts repeatable passes `step(timeout_us=)` past any finite step (the witness: 120
s). A contiguous pool mapped once would make the maps flat; it is a `CORE_FILES` change, so the cache keys move, and
it is left.

### The worker pool (Step X.10)

`devkit/reach/l3_pool.py`: `Pool(label, xbe, store=, workers=)` starts
its processes once (`spawn`; by default the cores, at most 16); each loads
the snapshot once (a format 2 file is a shared read-only mapping), builds
an `L3` per mode on first use and keeps goals by their spec, then serves
tasks from one queue: `pool.map(fn, argses)` for any module-level
`fn(worker, *args)` (`trace` runs an input string; `pids` names the
worker). Every task starts from the snapshot and every step from the
snapshot's CPU state, so a task's result doesn't depend on which worker
ran it: one worker and sixteen give the same rows and the same winners.
`solve_many(pool, problems)` runs many search problems at once (every
seed of every `Problem` a task; a problem's winner is decided once every
lower seed index has finished, and its seeds still running stop between
rounds); `l3_search.solve` is one problem on a pool, and `devkit/reach/l3_certify.py
search` runs every target of a level and kit on one. The pool runs under
`xemu_queue.BatchToken`: one task in flight while an xemu sitting waits
for free cores, and while an owner demo plays its workers at background
priority, at most the demo's budget of tasks (D526).
Errors stay with their seed (Step X.52): a seed whose start raises
`L3Error` in its worker is a run that failed at its start (`why`
`start: <the error>`, its site counted), any other error a task raises is
that seed's run (`error: <type>: <text>`, its site counted) or its
trial's (`trial_errors` on the winner, whose robustness is the share of
the trials that ran), and the batch goes on; only a broken pool ends it.
A failed run is tainted `failed:start` or `failed:error`, so it refutes
nothing. The explorer's seeds too (Step X.52b): a start that raises in
`explore_task` fails that seed's run (`start: <the error>`, its site
counted, `failed:start`), the problem's verdict when every seed's did. A `Pool` made while a spawned process still imports its
parent's main module (a driver script without an `if __name__ ==
"__main__":` guard, which each worker runs again) raises at once, naming
the guard.

Measured on a private snapshot at load 55-58 on 24 CPUs
(48 strings of 300 ticks):
296 ticks/s on 1 worker, 1,172 on 4 (4.0x), 1,970 on 8 (6.7x), 2,991 on
16 (10.1x), the same rows at every count; a pool starts in 0.2-0.6 s.

`devkit/reach/l3_certify.py` is the pipeline for the randomizer's spots and
edges (`docs/SCRIPTS.md`): a proof is the string's exact xemu replay, and
its record goes into `src/azurkit/tools/randomizer/data/proofs.jsonl`
(`src/azurkit/tools/randomizer/planner/proofs.py`: the claim, the start as a
recipe, the string with the camera as f32 pairs, the outcome, the replay;
no coordinates, no RAM; `docs/RANDOMIZER_DB.md` §4.6).

Measured (sitting x7, 2026-10-13):
5 of 5 strings that reached in L3 replayed in xemu tick for tick (0.0 m,
states and HP equal): town's Z370 -> Z004 hand edge (7,782 steps, 435
ticks), e7's Z059 -> Z000 (29 ticks), and X.4's three contact cases the
closed-loop pilot failed (e2's Z028 -> Z000 rim jump, 2,113 steps, 107
ticks; f6.Z804's narrow lip lift, 3,396 steps; f6.Z806's 34° hump, 9,476
steps). e2's other hand edges ran out of a 6 x 200,000-step budget with
their cost to go 20-40 s nearer; town's W1_Town arrival is a ~100-cell
pocket in both modes (AZ-351's rope bridge). 250-800 steps/s per process
in tick mode and 42 in whole-step mode at the machine's load that day.

### FastL3 (Step R2.19a)

`devkit/reach/l3_fast.py`: `FastL3(snap, xbe, ...)` is `L3` with the
same steps, rows and memory on less host CPU (from R2.17's emulator
prototype). Unicorn 2.1.4 sent every guest store through its slow path
(L3 maps every page R+W+X under an unmapped hook over all of memory, so
no TLB entry was ever clean: about a third of a tick's CPU). FastL3 fills
Unicorn's virtual TLB from a hook (code pages R+W+X, every other page
R+W, so a data entry is cleaned by its first store), maps data pages
without exec, bounds the unmapped hook to L3's high pages and drops
translations over code pages only. It takes no overlay, so `Pool(...,
fast=True)` builds it for every simulator with no overlay, player ticks
and whole steps, and keeps `L3` for an overlay; a fast pool also runs its
`setup` once in each worker. Whole steps (`scene`: rigs, lifts, the
render, MMIO, high pages) were checked in Step R2.19b: on a5's reach-live
snapshot, base `L3` on the stock wheel and FastL3 on the patched library
gave the same row and the same pose of each of 444 platform owners at
every one of 3,600 whole steps at rest, the same memory after (9,134
pages) and the same rows in 30 launches from ticks along them (R6, the
settle, the kit, the camera turn and an R0 launch: 4,406 rows), at x2.40
CPU over the 3,600 steps.

The patched library: `python -m devkit reach build-unicorn` builds PyPI's unicorn
2.1.4 sdist (uv.lock's, sha-checked), x86 only, with
`devkit/reach/unicorn/unicorn_fastl3.patch` (GPL as Unicorn: never in the wheel) into
the user cache dir's
`AzurKit/unicorn-fastl3/<the patch's sha12>` (about a minute; cmake,
ninja, clang). A process that sets `l3_fast.worker_env()` before it
imports unicorn loads it with three switches on (none set: it runs as
stock): `UC_SKIP_MEM_EXIT_CHECK=1` drops the exit check after every guest
load and store (kept after code hooks and at each block's start),
`UC_TLB_BITS=12` keeps a 4,096-entry TLB (the 256-entry one thrashed), and
`UC_X87_FAST=1` an exact x87 fast path (add, sub, mul, div, sqrt, loads,
stores, compares) where the control word is 53-bit round-to-nearest and
the operands are doubles exactly; there the host's double result is
softfloat's bit for bit, and anything else takes softfloat. Since Step
R2.19m's lean path (m1) the path's helpers are inlined into each op's
helper, the 53-bit round-to-nearest test is a flag the CPU state keeps,
set where the control word's precision and rounding are set
(`update_fp_status`), and the library comes in two flavours from the one
patch: the fast one (the workers') has no check code, and the check
flavour (`-DUC_X87_CHECK_BUILD`, built beside it into the folder's
`check/`, `l3_fast.worker_env(check=True)`, the x87 audit's workers) with
`UC_X87_CHECK=1` runs softfloat beside every fast result
and prints how many differ when the process exits. A fault can name
another site than `L3`'s, never a find: an unmapped write below L3's high
pages (outside the bounded hook) names a stale EIP, on the stock wheel too
(Unicorn syncs EIP only inside a hook covering the address; with the exit
check skipped, the block's end), and a fetch from a page outside the code
pages faults (`fetch_prot`: data pages are mapped without exec) where `L3`
runs the code, a lost find. The bench had neither: its only fault ends
were 14 `fault:runaway`.

The reach engine runs every pool on FastL3 by default
(`devkit reach reach-engine --l3 fast`; `--l3 base` is round 1's `L3` on the
stock wheel), with the aimed jobs' lossless tick cuts
(`devkit/reach/engine/fast.py`: the second aim pass resumes each
first-pass launch at its first touch-down, and a hit's hold runs its 60
idle ticks from the launch's end, reporting the replay's tick count), and
the patched library once it is built. Records are the gate, so neither
file nor the patch is in the reach cache's key: on Step R2.19a's bench every record of round 1's
four levels came out byte for byte (166,375 of 166,393 jobs and all
30,930 cached hold answers; the other 18 are round 1's own records of
steps its watchdog stopped on a throttled worker, which base `L3` re-runs
as FastL3 does: AZ-813). A find took 18.6 CPU-s against round 1's 41.5
(x2.23; the same 352 jobs and 444 holds side by side, base and fast at one
load: x2.28 CPU, x2.20 a tick, 1,646 ticks a core-second against 743). An
independent sample side by side (3,360 jobs and their 1,465 cached hold
answers, the lane and main at one load) gave 19.4 CPU-s a find
against 40.9 (x2.11 CPU, x2.08 a tick) and 30,673 ticks a find against
31,197 (-1.7 %: the aims -6 to -9 %, the fan and holds unchanged), every
record and hold answer round 1's. Recall at kit is round 1's, record for
record. On the stock wheel FastL3 gave e7's sample's records too, at about
x1.75; the x87 check mode saw 635 M fast results on 8 e7 jobs, none
differing. The cuts pin the code they copy (`fast.SHADOWS`: sha256[:12]
of each source); `fast.install` refuses once one moves, until `fast.py`
is edited beside it and the new hash pinned.

Since Step R2.19m (m2) FastL3 steps in C where it can: `devkit/reach/fastl3_step.c`, built by the
ziglang wheel's `zig cc` into the user cache's `AzurKit/fastl3-step/` (`l3_fast.step_lib`) and called with ctypes,
fills the virtual TLB, and for a player tick without `deep` (every reach engine simulator) runs `L3.step`'s glue
(the pad's address, the poll between frames, the scheduler clock, the return slot, the register batch, the watchdog,
`emu_start`) and the update's entry, camera and exit hooks natively, through Unicorn's public C API (whichever
libunicorn the process loaded); the exit hook copies out the blocks `obs.read` reads and the row is decoded by
`obs.read` itself. Whole steps, `deep` ticks and a tick that meets a pending stream request run the Python step
with the Python hooks (swapped in and out as the mode changes; `FastL3(native=False)` keeps them). The patched
library's fourth switch, `UC_TB_EXIT_INLINE=1`, tests the exit request at each block's start with QEMU's own inline
load and branch instead of a helper call (a request seen there leaves with EIP the block's start, as the helper's
restore gives). A record's `l3_impl` names the C step's source in its code sha and `step` (`c` or `python`).
`FASTL3_STEP=python` (`l3_fast.step_on`, set before a run starts) turns the C step off in every FastL3 a run builds,
the face loop below with it, and `l3_fast.worker_env` then leaves `UC_TB_EXIT_INLINE` out: R2.19a's FastL3 on
R2.19b's switches. X1's re-proof (PLAN-v3) runs with it, since the C walk's finds count under D845 only once that
re-proof, run with it off, gives them again.

Since Step R2.19m (m4) the C step also runs the static level's collision walk's face loop (0xD1B80's
0xD1E80-0xD22FD, `docs/RE_MOVEMENT.md`): a code hook at the loop's head works out, in C with the game's x87
operations in its order (doubles, no fused multiply-add: the x87 runs at 53 bits round-to-nearest), which faces
from the current one on the game would drop for lying wholly outside the query's box, and moves the loop's index
past them to the first it can't drop (one the face test gets, one outside the exact envelope: a non-normal
intermediate, a float32 store outside 2..253, another control word, a failed read; or the range's last face). The
game runs that face itself, and since every face writes the same locals, registers and x87 slots, the state it
leaves is the whole loop's. `FASTL3_WALK=0` turns it off, `check` decides every face in C without moving the
index and counts the decisions that differ from the game's (`FastL3.walk`); a record's `l3_impl` names the mode
(`walk`). The face test 0xB9E60 and the face range 0xD18D0 stay the game's code. A fast `run`'s x87 audit (1 job
in 1,000) runs with the walk in check mode: its workers write the decisions checked and differing as they exit
beside the x87 count (`worker.x87_counts`), and one that differs stops the run as an x87 difference does.

On Step R2.19m's bench (the lane's base and its m1, m2 and m4 commits side by side, every stage
on every side at once, each in its own scratch cache) every record (e7's whole kernel + backstop route, 14,231;
a5's, f2's and w1's 100-job slices of each kind, 1,199), hold answer (4,271; 1,942), sampled plan and graph edge
set came out the same at every step. A FastL3 tick (the backstop stage, 4.0 M ticks over the four levels) went from
799 us to 696 (m1, x1.15), 600 (m2, x1.16) and 440 (m4, x1.36): x1.82 in all; e7's whole route from 6.42 CPU-s a
find to 3.79 (x1.69) at the same 5,872 L3 steps a find (recall unchanged), the slices x1.68-1.86. R2.19a's e7 gate
for the head's l3_impl (every job of e7's aims and fan plans on the L3 route and each one's first hold, base and head
side by side) gave all 11,488 records and 10,678 hold answers again at x1.98 CPU. The x87 check on
the head's library saw 3.65 G fast results on 56 fan and aimed jobs of seven levels (the bench's four, e2, e5, w2)
and the C walk's check 20.3 M face decisions there, none differing; a5's whole-step compare (3,600 steps, 444
platform owners, the end memory, 30 trials) gave base `L3`'s at every commit. PLAN-v3's m3, shadow doubles for the
x87 registers, was built and measured x0.98 a tick (and TCG's no-globals call flag for the pure x87 helpers, tried in
its place, x0.96): both exact, neither faster, so neither landed. An independent measure of the head against
origin/main (side by side, 6 workers a side; `measure.txt` beside the report) gave the same: a FastL3 tick 695 ->
382 us (x1.82), e7's route 5.46 -> 3.05 CPU-s a find (x1.79, x1.75 a step) at 5,873 L3 steps a find, the slices
x1.65-1.75, every hold answer, plan and edge equal and recall at kit equal (e7 1,100 of 1,203, 91.44 %; no find
lost). The RDTSC hook stays L3's Python one (PLAN-v3 listed a native one): no RDTSC ran in 6,021 e7 bench ticks.

Since Step R2.19l every pool worker on either route (`worker.setup`, so
the kernel route's too) also takes `fast.py`'s driver cuts
(`fast.install_driver`): a launch's touches (`runner.outcome`'s
`Touch.at` of each row's body centre) are found once a launch, each
distinct position once and `Touch.at` only where a volume's box or a
pickup's radius holds it (`fast.touched`: the same comparisons and
elementwise float operations for every volume, pickup and position at
once); and a FastL3 worker keeps each placement's answer (R6 and the
20-tick settle from the snapshot: the settled body's position, state and
`settled`, or a fault) by its feet, yaw and cell, so a start try whose kept
answer falls is counted and not placed again, a stand test of the aims'
floor and other-start scans (and the kernel route's FastL3 stand tests)
reads it, and a try that stands is placed again (its state starts the
launches). The answers persist, private, in the level's cache folder
(`placed/<snapshot meta sha12>-<sha12 of the l3_impl without its kernel
and the L3 core>/`, one store for the kernel route and plain FastL3;
a file a worker process, each worker reading the others' new answers
every 2 s, a file's size taken from the file: Windows' folder listing keeps
the size it had when last closed), so every worker, stage and later run on
the same code shares them. The yaw is part of the key (`fast.YAW_KEYED`): the yaw check placed 10,500 points
sampled from the engine's own plans on seven levels (the bench's four and
e2, e5, w2: aim floor scans, other-start scans, job starts) at 4 yaws each
on FastL3 and every answer was the same bit for bit (the saved pages
differ: the facing is stored), but the bench's first e7 run with the yaw
left out stopped on 2 of its 10,260 stored points, which two workers had
placed at other yaws: placed again at 36 yaws each gives 12 answers (a
body hanging off a ledge, state 257, at 11; none stands; each yaw repeats
its own). About 1 kept answer in 200 is placed again
and 1 launch in 200 tested row by row; a difference (or two answers for
one key) stops the run (`fast.Drift`, a `SystemExit` no
job keeps as its error). Base `L3`
places every time, so the base audit stays the reference. The cuts pin
what they copy or lean on in `fast.SHADOWS` too (`fast.DRIVER_SHADOWS`:
`runner.outcome`, `Touch`, `Volumes.holding`, `faces._spans`,
`find_start`, `place`, `aim.stands`); a moved one stops every pool, base
too, where a moved tick-cut copy stops only `--l3 fast`. On Step R2.19l's bench
(the lane's base and head
side by side at one load, each in its own scratch cache) every record
(e7's whole kernel + backstop route, 14,231; a5's, f2's and w1's 100-job
slices of each kind, 1,199), hold answer (4,271; 1,942) and graph edge set
came out the same. e7 took 6.46 CPU-s a find against 7.00 (x1.08, from
the independent re-run at one load, `measure.txt`; the first run's x1.10
held about 2 points of load noise) and 5,872 L3 steps against 6,284
(x1.07): its backstop x1.30 (71 %, 58 % and
40 % of its floor-scan, other-start and start-try lookups answered from
the store, 1,750 tries not placed), its fan x1.03 and refinement x1.05
from the touches. The slices, whose backstop has no whole stage's answers
before it, gave x1.03-1.14 CPU and x1.03-1.12 steps; weighted by R2.19d's
stage costs they put the bench near x1.05 (an estimate, under PLAN-v3's
x1.07 bar). Recall: unchanged.

Since Step R2.19b each pool worker the reach engine opens runs
`devkit/reach/engine/worker.py`'s `setup`: a step L3's watchdog stops
for time (`runaway@`, `render timeout@`; a worker the host starves) raises
`StepTimeout`, which no launch, start, kit or hold takes as the game's
fault, so the job is an error and runs again next time (AZ-813); and each
record carries `l3_impl`, what ran it (fast or base, the sha12 of
`l3_fast.py` and `fast.py`, of the libunicorn loaded, `l3_fast.loaded()`,
and the switches). A fast `run` audits itself as it ends: about 1 job in
500 again on base `L3` on the stock wheel, and with the patched library 1
in 1,000 on FastL3 with `UC_X87_CHECK=1` on the check flavour (each audit
worker writes the check's count to a file as it exits), every record compared with the run's
(`l3_impl` aside); a difference stops it. `devkit/reach/l3_fast.py`'s
`probe()` names the library a FastL3 worker loads (a fresh process started
with `worker_env()`; Modkit's `doctor` printed it). On the bench
the audits over every job of the four levels' buckets, 330 on base `L3` and
158 with the x87 check (fan and aimed jobs on each level), gave round 1's
records, and none of the check's 6.7 G fast results differed; R2.19a's
side-by-side sample (352 jobs, 444 hold answers, base and fast at one
load of 32-46) gave every record and answer again at x2.33 a tick (x2.20
w1 to x2.38 e7) and x2.41 CPU. The independent measure's own sample (1,698
fast jobs, 858 on base, at loads of 39-50; `measure.txt`) gave every record
again, x2.23 a tick pooled (x2.17-2.34 by level), 19.4 CPU-s a find and
1.65 % fewer ticks a find than base. Every bench number here ran on the
cache keys from before R1.39's `settled()` (core `360d68fd1861`).

### The native kernel as the reach engine's launch backend (Step R2.19d)

Modkit's `reach_native/` (Step R2.17's prototype, landed) ports the player's ground and air ticks and the game's
move code to C (`kernel.c`, whose header lists what is ported: the face test 0xB9E60's ellipsoid sweep, the level
walk, the move 0x47380, the walk, jump, flap and airborne ticks, slopes and fast slides, the classifier and the hard
landing, and the step-up and lip-lift decisions), built by the pinned ziglang wheel's `zig cc -O3 -march=native`
into the AzurKit user cache and run through ctypes on a level's solid triangles at their load pose, less the
platforms a census finds the game's world doesn't hold at the snapshot (L3's own `collision_sweep`). It is not
bit-exact (doubles with the game's float32 stores against x87), and it stops where the game does what it doesn't
port: the step-up's and lip lift's clips, the catch, the climb (out of the water too), the roll, other states, ice,
and a push or water volume that moves or switches (R2.19h1 records them). Since Step R2.19e it ports the volume query
(each tick's push and water volumes at the body centre, `docs/RE_MOVEMENT.md`), the air's pushes (updrafts,
downdrafts, currents: the 0.3^dt blend toward 0.1 x the stick term plus the push, no gravity with pushZ), swimming
(state 6: the 10 m/s stroke and walkSpeed's vertical at 0.1^dt, a 1 m sphere, the surface's cap) and springboards
(an autoSpring face's height as the jump's h).

`devkit reach reach-engine --backend kernel` (`devkit/reach/native/backend.py`) runs each job on a `KernelSim`, the kernel
under L3's interface: R6's placement (its tick moves nothing and keeps the snapshot's velocity, flap latch and
camera, so a kernel start ends within 0.1 mm of L3's), the settle, the kit as state, the camera align and every
launch run on the kernel under the engine's own controllers. FastL3 runs what the kernel flags (a start whole; a
launch from its start's FastL3 twin), answers an aim's floor scans (the kernel's point where FastL3 stands a body
there too, else FastL3's own scan) and confirms each kernel outcome before it counts in the logic (D845): from a
start FastL3 stands, its string and the hold's 60 idle ticks run again from the snapshot, the outcome re-derived
from L3's rows. A drift audit (1 job in 100) runs every kernel launch that settled again on FastL3. The mover-contact
router names the rigs, toggled gates and census-absent platforms each held witness's body path touches at their
load pose, and the rigs it passes within 2 m of. Records are keyed by the kernel's code, compiler and census.
On R2.16e's bench (measured twice) the route took 6.66 CPU-s a
find against round 1's 41.47 (x6.2) and FastL3's 13.95 on e7 measured beside it (x2.76; 9,633 L3 steps and 27,026
kernel ticks a find against round 1's 30,910 L3 steps), with 11-29 % of its launches flagged to FastL3 (w1's water
most); it kept 97.3 % of round 1's per-edge finds, 99.87 % with the FastL3 backstop (8.36 CPU-s a find). Taking the
floors from FastL3 then cost e7's aims stage 19 % more CPU. The kernel is far from exact: 10-35 % of each level's
settled kernel launches end over 0.5 m from FastL3's run of their pads (slope and slide edges, contacts the game
doesn't make, the stored normal in the air), which the confirm catches and the backstop pays for. Since Step R2.19k
each confirm the graph's hold reads, staying or not, also gives the touches, MAY candidate and node edge of FastL3's
run (with the backstop on the bench: 7 % more touches, 11 % more MAY candidates, 12 % more node edges, still 76 %,
56 % and 82 % of round 1's: a kernel launch no hold confirms gives none).

Step R2.19c2a (`devkit reach reach-truth`) measured the route against FastL3 on the truth set's frozen pairs: R on the
kernel kept 95.9 % of FastL3-R's real pairs with a closed-loop FastL3 re-fly of each failed candidate, and most of the
candidates FastL3 refused died there (260 of 309: the kernel models no damage, so a landing in a death volume is a
kernel find). Its independent generator drives the kernel open-loop: `World.run`'s pad batch (`p_run`) flies each
random string in 16-tick calls while the body is in the air, the touch-down's call run again to that tick before the
stick rests: about 58 kernel ticks a string; 15.5 M strings on e7, a5 and w1 took 2.64 CPU-h with their FastL3
confirms and flagged flights (0.6 ms a string).

Step R2.19e's ports checked the volume query against the game's own at
0x85599 on 187,000 ticks of 1,600 held-out round-1 launches: the words, push and depth agree wherever the kernel
models the volume (the depth is the deepest of the water volumes holding the point, which its review found on w1's
overlapping pools; the held-out ticks never sat in two). On w1, 44 swimming launches went from all flagged to 28
agreeing within 0.5 m (13 flag on a push volume that moves or switches, 2 on a roll, 1 parts after an earlier slope
contact), and the bench's flagged launches there fell from 29 % to 11 %: 5.76 CPU-s and 6,570 L3 steps a find over
the bench (main 7.60 and 10,124 under a heavier load), every per-edge find with the backstop and every truth pair
main's. The air outside a push volume keeps R2.19d's rounding: the game's exact blend lost a find, a knife-edge
landing after a contact the kernel's face order only approximates (D835).

Step R2.19f+ (one re-key stack) ports the lip lift's clip as
FastL3 plays it (RE_MOVEMENT: the body put on the ledge that tick, then state 0x100 in place for 89 or 37 rows), walks
on the tick after any clip's last row (the hard landing's 13 too: the kernel had spent one more tick in place), ports
the classifier's two updraft rules (0x85AA7, 0x8596E) and gives a mover its own springboard height. The step-up's
clip was ported and reverted: where the game puts the body on the step is not the decision's point (0.16-0.19 m
across, 0 of 17 within 2 cm), so a step-up still hands the launch to FastL3, as do the roll (BLACK's root motion), ice
(a fast slide on a slippery walkable face), the catch, the climb and the lift out of the water. On R2.16e's bench the
kernel route costs 4.07 CPU-s a find alone and 5.34 with the backstop (R2.19e's record 5.76 and 7.24, another day's
load; against main at one load on e7 and a5, x1.14 and x1.20 with the backstop), 5,727 L3 steps and 28,965 kernel
ticks a find (6,570 and 28,508), with 7.9 % of its launches flagged (11.1 %).
The record's keys hash code (`cache.code_bytes`: a docstring or comment edit re-keys nothing), and every hold answer
names what ran it and goes into the base-L3 and x87 audits as a record does.

### The launch controllers in C (Step R2.19p)

Since Step R2.19p the kernel route runs each launch family in C: `reach_native/controllers.c` (built with `kernel.c`
as one unit, which it includes) copies `macros.launches` and its three controllers (R0's `macros._Run`, `aim.Aim` and
`aim.Sched`: the run-up and press lead, the roll's buttons, `flap_due`, the recast, the predictive landing control
with its curve, hold, home and brake, the envelope's schedule, and the ends), and `p_launches` runs a family in one
call: each tick's pad from the row before, the ticks the family's pads share stepped once, a pad that parts going on
from that tick's saved `Player`, as Python does. It hands back each launch's end, the rows an outcome reads (the
last, the first touch-down, the takeoff) and its pads as the witness's run-length segments, from which
`backend.c_outcome` makes the record `backend.outcome` makes of the Python run's rows, byte for byte. The Python
controllers stay the L3 route's and the reference (`AZURIK_REACH_CONTROLLERS=py`): `backend.SHADOWS` pins the
sha12 of each Python source the C copies, and the route refuses to start while one has moved; every named constant
is passed in from its module (`backend._consts`). The float rule: doubles in Python's order with nothing contracted
(a `#pragma STDC FP_CONTRACT OFF` after its `#include "kernel.c"`, so the kernel's own floats keep the build's
contraction and step a body bit for bit as `kernel.c` built alone does; the pragma is in `kernel_sha12`), libm's
`sin`, `cos`, `atan2` and `pow` called through pointers (no sincos merge or `pow(x, 2)` rewrite: the calls CPython
makes, which equal libm's on 300,000 random inputs each; on Windows the UCRT's, through `__imp_sin` and `__imp_cos`,
since zig cc links its own `sin` and `cos`, compiler_rt's ported from musl, ahead of them and they part in the last
bit; `c_libm` exports each call, which the test holds to `math`'s first), and CPython's own `math.hypot` (its
`vector_norm`),
`round`, float `%`, `atan2` special cases and `sum` ported: libm's `hypot` differs from `math.hypot` on 16 % of random
pairs. Where Python would raise (a non-finite heading at the stick, a non-finite landing time) the family runs in
Python and raises as before. `tests/test_reach_engine.py` runs R0's fan, the aims, the refinement and the scheduled
aims on the kernel both ways and requires every record and kernel count equal, and steps a body over its platforms
on the controllers' build and on `kernel.c` built alone and requires every row and state field equal.
On R2.16e's whole bench against main at one load the first cut, `-ffp-contract=off` on the whole
build, took 5.8 % less CPU a find with the backstop and a C kernel tick cost 2.0 µs with its controller, but the
flag moved the kernel's own floats too (11-22 % of a level's aims and fan records against main's, none of them the
controllers') and lost 5 of main's derived edges; with the pragma 680 of 680 a5 and w1 records are main's.

### Moving solids in the kernel, and rig trips in whole steps (Step R2.19h1)

The kernel's world holds movers (`World.movers`): each rig's triangles in its own frame and a pose table, one row a
tick, read from FastL3's whole steps where the game collides with it (the platform node's collision object, its
world matrix at +0x170, R2.19h2's `Runtime.deck`), cycling (the row wraps at its period) or a path held at its last
row, and a present mask. A sweep meets each present mover at the clock's row (`World.clock`; a run sets it to the
tick's end) and names it in its contact (`src`); a body whose last floor contact was a mover rides it: before each
tick its position takes the rigid move of the mover's frame from one row to the next. A world with no movers runs as
before, so the launch route's records don't move. The kernel's rig hops only order work: a rig link counts only
from a FastL3 whole-step trip (`reach_engine.rigs`, D845): the snapshot stepped at rest to the phase (a toggled
deck's pokes held first at the graph pass, R2.19h2's rule), R6 onto the start, the kit and the string, the feet
checked against the deck's live top each tick. Every whole step of the stage runs under a 120 s cap, not L3's
wall-clock 5 s render cap: a teleport into a part of the level the stream hasn't loaded maps each of its allocations
as a Unicorn region, slower the more a process has mapped, so under load such a step passed the 5 s cap and the trip
ended at a fault no game made (a fifth of a5's first truth trials). A reset doesn't undo all of a long whole-step run:
on w1's start snapshot a poke of polySurfaceShape459's switch moved the deck on a new scene FastL3, again on the same
one after that, and not on one that had run the 3,600-step recording first (cause unlocated), so the stage's pool
results hung on what each worker had run. The recording, every poke try and every trip start on a new scene FastL3
(`l3_pool.Worker.sim(fresh=True)`, about 1.4 CPU-s with its first steps), and a stage trip that held counts only where
it holds again alone on another from the snapshot.

### The trick explorer (Step TD.1, D253)

`devkit/sim/l3_explore.py` is the trick-discovery plan's search
engine (its §3.2), beside
`l3_search` (whose problems keep their identities). Like it, it knows a
simulator, rows and a guide passed in by name; the randomizer's guides
are `l3_goal.make_zone_guide` (a discovery problem: the zone, the floor
region the feet are on, the column's highest floor) and
`l3_goal.make_trick_goal` (a target problem: `RouteGoal`'s goal test,
cost to go and heading over the light trick graph below).

- **Zones:** a body on a floor or swimming is in the zone of the logic
  floor its feet are on (`Router.locate`'s 1.0 m under to 0.5 m over) or
  of the water holding it, never of a floor under a top it stands on
  (`zone_at(..., fallback=False)`); one in the air, climbing or in the
  catch is in the zone under it. A zone counts as reached standing or
  swimming in it.
- **Cells:** a state's place cell is (region, 2 m, 2 m, 1.5 m of feet
  height), the region its zone, else the phys floor region it stands on
  (a pseudo-region's match: a merge or a later settle never re-keys a
  place), else `oob`; its dynamic cell, at a 4 m place (3 m high), adds
  the state class (ground, slope 3, slide 4, air, catch 0x101, climb,
  swim, 0x100), a log speed bucket up to 300 m/s (in the catch linear in
  the charge, the velocity along the stored wall normal's horizontal, at
  0.95 × 4.6434 m/s: the catch keeps the entry's speed into the wall, so
  the speed itself isn't monotone in the presses, and each charging Y is
  a new cell), the sign of vz in the air, the flaps left and whether the
  gauge is full. A state is new when either cell is.
- **Two strings per cell:** the shortest and the one of most potential
  (speed, the charge in the catch, then flaps left, then gauge), so a
  charged hang is never replaced by a quicker plain climb
  (`Archive.offer`).
- **Moves:** primitives of 1-32 ticks (8 most often): a world heading in
  24 sectors with noise or the stick at rest, magnitude 0.35, 0.7 or 1.0,
  at most one press (Y, BLACK, a cast: LT+Y the air shield or LT+Y+B the
  lightning shield, air 1 + fire 1, the armor's type mask 2 or 6 in L3 in
  player ticks and whole steps for a press held 1, 6 or 12 ticks; A, B, X or RT at
  low weight) at any
  offset held 1-12 ticks (cut at the 32nd), a dive in the water; on a goal pick
  `Limits.pursue` of the moves follow the guide instead (`toward`, as
  `l3_search`'s: its heading at full stick for the run-up's ticks, Y held
  6 ticks where it says jump); the camera turns 3.33° a tick toward the
  heading and the stick is solved under it. Options (`Option`; Step
  TD.3's four below, registered by default) are closed-loop moves by spec
  (`Limits.options`) that fire where their runtime precondition holds
  (`Limits(options=())` explores without them). A bandit per state class shares the draws among
  the press kinds and the options by the new cells per tick each found.
- **Limits:** each arm's airborne allowance (a primitive's 300 ticks),
  the run's cap the largest since the takeoff, at most 2,000; the game's
  own deaths (states 7 and 8, HP 0: the mid-air fall rule among them)
  and an `L3Error` end a branch; strings to 12,000 ticks; saved states
  in a compressed LRU (`Limits.lru`; 36-49 KB each measured), saved at
  once every 64 ticks along a string, else on a pick, an evicted one
  rebuilt from its nearest saved ancestor.
- **Selection:** a target problem mixes goal picks (cost to go:
  `exp(-(c - best) / temp)` over `sqrt(1 + visits)`) and novelty picks
  half and half; a discovery problem makes novelty picks only:
  `1 / sqrt(1 + visits)` times recent productivity times the priors
  (height above the column's highest floor, outside every zone, a rare
  state class, high speed; with the guide's `sites`, an unvisited mined
  site's nearness, `draft.sites.Prior`: up to twice the weight within
  8 m of a site's anchor point, a site visited once a row comes within
  2 m, the visited set each exploration's own; sites only add weight,
  never steer), half of
  them among the strings the place cells hold and half among the
  dynamic cells' (the finer table swamped the frontier: 3.5 k place
  cells to 36 k dynamic ones in f6 over 2 M ticks).
- **Pseudo-regions:** a settle outside every zone (state 0, 10 ticks
  under 0.5 m/s) opens one, matched to the phys floor region it stands
  on; settles a walking string joins merge. They are counted; nothing is
  exported (intake is R1.24/R1.25's). The first string that stood in each
  zone and the one that opened each pseudo-region are kept for the
  private store (`Result.firsts`: a find's seed for its confirmation).
- **Starts:** a `Segment` as `l3_search`'s; a placed start (an R6
  teleport) makes a find `partial` (D119, Q267). A start chained on
  earlier finds (Step TD.2) is the natural start with their strings as
  the segment's `prefix` (`l3.pads` segments, each tick's camera the
  exact f32 pair it read): `start_of` runs them after the settle and the
  kit, so the chained hop starts where the last find ended, and one xemu
  replay of the whole chain from the natural start proves every link.
  `devkit sim explore` takes a spec's `prefix` files only when each is
  a find from the spec's own start, kit and mode after the files before
  it, and refuses any other by name.
  A problem runs in whole steps (`Segment.scene`) where a rig, a ride or
  a trigger the player update alone doesn't run is on the way (w1's
  electric arch follows the armor only there).
- **Verdicts:** `found` (confirmed from the start, `settle` ticks at rest
  still in the goal), `saturated` (no new cell in `Limits.exhaust`
  rounds, at this cell resolution and move set), `not found within
  budget` (`inconclusive` when a run is tainted; a discovery problem's
  `budget spent`), `wall-cap`, `cancelled`; a problem's verdict over
  seeds none of which found names the branches that left the level
  (`; 12 branches fired levels/earth/e2`, Step X.52b), which end on the
  fire's row untainted. A seed gives the same cells and strings
  (`Archive.digest`); `explore_many(pool, problems)` runs every seed of
  every problem on an `l3_pool.Pool` under the batch token, the winner
  the lowest seed index that found; a problem's totals count the seeds up
  to it (all when none found), so they don't depend on the worker count,
  and over seeds none of which found it is `saturated` only when every
  seed is (else a wall cap or a cancel if any seed ended so, else the
  budget's verdict). A task gives way between rounds while an xemu
  sitting waits for a slot (`xemu_queue.give_way`, which the wall cap
  doesn't count), and every seed still running stops at its next round
  when `explore_many` exits, however it exits.

**The light trick graph** (`l3_goal.TrickRouter`, guidance only, never
logic): the phys profile's route graph for the kit's air level (every
landable face; its flights by the envelope alone), its walks costed by
the game's own walk (`floors.PROFILES["walk_game"]`: a non-slippery face
over nz 0.7071, a slippery one at 0.998, the 0.65 m step-up; the reach
model never builds it, `floors.DERIVED`, so `rando derive --all --check`
is unchanged), each flight rechecked against the solid faces one-sided
(`OneSided`: dropped only where each of five paths, a box, two arches,
a bend by the ends' heights and the straight line, crosses a face into
its front; of f6's 8,916 logic flights the derive's two-sided sweep
clears, 129 are dropped, 425 with one path), with no edge a
`tricks.toml` skip made or ranked (`l3_goal.named_skip`: a confirmed
skip's atom, a barrier bypass, a hand current crossing; the blind
protocol, the plan §4; w1's `shoreline_rollthrough` crossing is the one
such phys edge in w1, e2, f1, town and e6), plus
slope hops (from a slope or slippery floor, a rise of h nz² plus the
kit's flaps, within 4 m, 7 m with flaps) and lip and rim lifts (from a
floor's border onto a ledge up to the kit's apex plus the 0.8 m rim
step-up, within 2.5 m). Every edge is optimistic; launches and descents
are the explorer's to find. e2 at air 1: 172 k phys flights, 309 k slope
hops and 131 k lifts added; 40-70 s and 3.9 GB to build.

Since Step X.53 (AZ-591, AZ-577) the trick graph drops no edge it
doubts: a doubtful edge costs `DOUBT_S` (60 s) more, over the 30-230 s
ways measured at the stalls, so a measured way wins where there is one
and no start loses its way, and a stall names the doubt
(`#k jump (geometry, doubted: ...)`). Doubted: a flight every path of
which crosses a face into its front (`blocked`), or that only paths
crossing faces from behind keep while its body band (0.4 m to each side,
the feet + 0.6 and + 1.4 m) doesn't clear (`one-sided`); a hop or lift
past the rise the game's jump gives from its takeoff face
(`l3_goal.jump_doubt`, the jump 0x89060: a slippery face or one of nz
<= 0.7071 takes the normal branch, 0x8917F-0x891D6, and rises h nz² plus
the kit's flaps; any other face the kit's apex), plus, for a lift, the
measured lip lift (0.4987 m) or the 0.8 m rim step-up where
`flights._rim` finds a sloped rim before the ledge (`past the jump's
rise`); and a slope hop landing behind its face's normal
(`against the takeoff's normal`). A flight whose ends lie under half a
cell apart across (a drop straight down off a floor's edge, every test
path through the takeoff's own floor) is kept untested: e2's phys graph
had 1,929 of its 2,373 such drops dropped, #7812 (the only way into
e2.Z005) among them. Water of two swim regions within 1.5 m (3-D) gets a
swim link both ways (w1's bay lies 1.4 m from w1.Z216's water). The
plain router (`route.Router._widen`, every profile's) moves a flight's
witness sideways only while its rise stays within 0.1 m of the
derive's (e2: 55 jumps passed the plain apex and 365 drops 17 m only by
widening).

Measured (Step TD.1): 290
ticks/s per worker, 2,055 on 8 workers at load 15-75 on 24 CPUs (510-860
a worker at load 5-11). A seed gives one archive on 1 and 2 workers.
With novelty picks only and a zone counted only on its own floor, x7's
e2 rim jump came back (stood in after 59 k ticks from x7's R6 start, its
136-tick first string replayed into the zone and held there); f6's 34°
hump and its lip lift did not in two seeds of 2 M ticks from the
vanilla-flat spot (13-14 zones each, 6.3-6.4 k place and 53 k dynamic
cells), though x7's own strings stand in both: a budget miss for TD.3's
options (the first run's two f6 finds were scored with the zone
fallback, which counts a body above the floor, and kept no string). Of 20 of R1.16's flap-and-jump budget misses outside w1 and e6,
at 1 M ticks each from R1.16's own R6 starts (its search had 60 k): 3
found (e5 Z018 to Z005 in 1,538 ticks, f4 Z288 to Z013 in 577, town Z045
to Z001/Z053 in 484; each still ends standing in its goal and holds
there under the strict rule), 17 not found, none tainted or saturated;
town/g1/r140's search stood at its cost field's zero without the item's
touch (R1.16's "near").

Measured (Step TD.2, X.36's sitting A;
TD.1's explorer with chained starts, before TD.3's options): each of the
25 hops goal-directed from its spot's natural arrival (every element at
0 in L3) or a start chained on found strings, 8 seeds of 400 k player
ticks, or of 40 k whole steps where a rig, ride or trigger is on the way.
1 found and replayed in xemu every tick equal, standing in the goal: w1's
bay into the w1_z110 node (ending in w1.Z157; 4,355 ticks). e5's E2_E5
arrival never stands on the gear deck it lands on: at rest it falls into
e5.Z014 (L3 and xemu), and hop 22's 181-step find is that fall (replayed
exactly, its from-zone never stood in), so the hop stays the owner's.
14 not found within the base budget, every archive still adding cells
(5-17% of them in its last tenth: none saturated), 5 of them
inconclusive (4 tainted, and hop 17's goal unreadable at the dock); 9
not attempted, with no start made. Two legs replayed exactly in whole
steps too, one chained on the arrival's fall (986 steps from the
arrival's parked tag). e5's grinder room moves only in whole steps: its
player-tick strings split from xemu at ticks 499 and 970. Whole steps
ran 6-21 a second a worker (player ticks 194-630) at load 14-63 on 24
CPUs. The strict zone rule reads no zone at e5's gear-deck or dock
arrivals (AZ-538), so a hop from or to a rig floor can't be judged by
the zone there.

Measured (Step TD.2b, D285; the explorer with TD.3's
options and X.52b's exits, stalls and engine version, one engine
throughout): TD.2's 24 unfound hops, 2 seeds each at TD.2's per-seed
budget, then up to 6 more seeds of 1-1.5 M player ticks or 100 k whole
steps for those whose best cost still fell in its last 100 k
tick-equivalents; 82 seed runs, 56.7 M tick-equivalents. None found. No
miss is tainted: the 755 branches of the runs from e5's deck arrival
(and its chain) that took the e2 exit ended there clean. Every stall is
filed by its place (AZ-577 to AZ-583): off the logic graph (w1's bay
swimming, e2.Z002 toward e2.Z005, e2 toward e2.Z006, town.Z002), a
modelled or geometry jump or drop edge no seed makes (e2, e5), a
probe-needed rig in e2.Z019 that whole steps don't open either, and no
zone 0.8 s from town.Z340 (on the grate elevator [inferred]). Hop 5's
best rows, 1.3 s from e6.Z043, stand 6.5 m over its floor where the
level's collision has no face under the feet (a surface the reach model
doesn't hold there): not a zone-read miss. The misses at e5's deck and
dock (17, 21, 23 and the dock's leg) stay inconclusive by the zone rule
(AZ-538). The longer seeds lowered some best costs by 0.2-3.1 s (hop 15
from 9.6 to 6.5 s, hop 3 from 10.1 to 7.5 s in whole steps, hop 10 from
6.5 to 5.8 s); four problems' last seeds still fell 0.1-0.5 s at their
ends (3, 6 in whole steps, 15, 20), the rest ended flat. The disc room's
start (the R7 request, from a new game, to the spot w1's live switch
posts, town's water_disk_loc) stands in town.Z020, and its leg to
town.Z015 replayed in xemu every tick equal (633 whole steps). A batch
whose token fell to 1 while an xemu ticket waited kept one task in
flight until a task ended (AZ-563; since Step X.53 it takes its workers
back within a poll).

Measured (Step X.53,
`results/table.tsv`; the guide's changes above, one engine, 20089c1dca71):
20 of TD.2b's hop problems (2 seeds each at its per-seed budget, more
seeds or steps where a stall still fell or moved within 10 s of the
goal), 22 of R1.29h's spot legs (certify, 30-90 k whole steps) and 6
probes from R6 starts at single edges; 101 seed runs, 43.9 M
tick-equivalents, 54.0 worker-hours. No hop and no spot leg found. Three
probes found and replayed in xemu every tick equal, the kit exact and
the body standing in the goal: e5.Z397 to e5.Z046 at kit 0 and at air 1
(the logic's #18219: the check passes, AZ-587) and e2.Z643 to e2.Z027 at
kit 0, an edge the logic lacks (R1.25's proposal, AZ-626); a fourth,
e5.Z013 to e5.Z005, replays exactly from a start where a body at rest
drifts 110.8 m and dies, so it proves nothing. Every stall but hop 21's
(#24129) moved: no best row is off the graph or stands on a top the
model lacks, and the best cell of 34 of the 47 unfound problems is a
body in flight on a goal flight, priced as if it lands (AZ-621). One
miss is tainted: hV2b's seed 1 (two high-page reads), and a re-run on
the same engine reads the same taint and stall, so only its seed 0 is
clean evidence. The explorer's tasks slept about 2 h behind xemu tickets
an owner demo kept from starting (AZ-620).

Measured (Step X.54,
`results/table.tsv`, `skeptic/REPORT.txt`; the guide that prices a
flight only while its arc can still land and the touch that counts only
once the body lands alive, one engine, 1aeeb00415bd): X.53's nearest
misses again with their seeds and two new ones each, 6 hop and probe
problems and 18 spot targets; 83 seed runs, 37.3 M tick-equivalents,
55.2 worker-hours. Two spots came back and replayed in xemu every tick
equal with their own item taken: a5/g0/r735 (air 3, 3 of 4 seeds) and
a3/g0/r2591 (3 of 3, its way back on the light trick graph), P1's 53rd
and 54th (AZ-455). Hop 39 at kit 0 was found in player ticks (3,648
ticks), but xemu splits from it at tick 3,042 and ends swimming in
e2.Z002, not e2.Z027 [a rig or an enemy a player-tick string holds
still, inferred], so it proves nothing. f3/g0/r2547's way there was
found and its way back stalls off both graphs, 7.1-8.0 s in 4 seeds.
Hop 5 (0.2 s, 6 seeds) and hop 17 (3.2 s, 6 seeds) did not move; hV2b
ends in town.Z340 itself, 0.1 s, no seed tainted; a3/g0/r1500 stops
0.2 s short, flat. By stall name 11 of the 21 unfound problems end on a
flight, but by the rows' own state 16 of the 21 are in the air: a body
whose arc can't land is named by the floor it falls to, so the drop
from X.53's 34 of 47 is mostly that renaming. A render timeout in
certify's end-to-end verify lost one run whose legs both reached; its
re-run found them again (AZ-640).

**Contacts, regions and transitions (Step TD.4).** Each explored row's
touched face is `obs.contact(row.obs, faces)`: the face its stored
contact normal belongs to (`faces.Faces` on the guide's `level`, the
reach model's collision; none in the air with the classifier's
no-contact normal (0, 0, 1)), tallied per face and state class
(`Result.touched`, private: face ids locate a body with the game file),
and so are the trigger, push and damage volumes its body centre is in
(`faces.Volumes`: a mesh with a face of it straight above the point and
one straight below; `Result.entered`, by each volume's lowest face);
a find's rows give its `used` faces. Per region (a zone, a
pseudo-region's `R<n>`, `oob`) the explorer counts the new cells and the
picks since its last one, and a region is saturated after `Limits.idle`
(400) picks with none (`Result.regions`; a report, never a stop). Each
step from a zone stood in to another zone stood in, checked row by row,
is a transition (`Result.transitions`: its count, the first string's
ticks and the steps spent), the record a saturated zone's unreproduced
logic edges are read against (the probe list). The face lookup costs
about 70 µs a row (e6, 2026-10-19: a one-off timing, not recorded),
about 2% of a player tick at the explorer's 280 ticks/s.

**Sites and the census** (Modkit's `randomizer/draft/sites.py`, the
plan §3.4 and §3.6; one rule for every level, nothing named): the
surface classes are the contact rules' (`docs/RE_MOVEMENT.md`): `wall`
(nz ≤ 0.6, not climbable), `slope` (0.6-0.7071, not slippery), `slide`
(slippery under 0.998), `steep` (0.7071-0.8), `rim` (0.8-0.87), `floor`,
`climb` ((word & 3) == 2, |nz| < 0.2588), `spring` (autoSpring), `rig`,
`thin` (an upright wall with nothing solid 1 m behind it and a floor
there within 3.4 m under it: passable from behind; the outer shell,
with no floor behind, isn't) and `open` (a wall whose top edge no other
solid face shares). The miner's sites: slope, slide and steep patches
(faces joined by shared edges, 1 m² and more), climb columns (3 m and
taller, every rim edge kept, no back-wall test), lips (a wall patch
under a ledge, taller than the 0.65 m step-up and within the kit's apex
plus the 0.8 m rim step-up), thin and open patches (thin walls and
open edges), triggers (an exit's touch mesh
with an inside point a straight 60 m path in one of 24 directions leaves
crossing no solid face, open air outside every shell, and no floor lies
within 3.4 m under: reached only through the air; `void`, the share of
the open-air points that are so), speed sources (a
spring patch, a push volume, a rig) and `oob` (a phys floor region of
4 m² and more no logic floor lies in: outside every zone). Ids are
`<level>.<class>.<n>`: patches, lips and speed sources numbered in the
order of their lowest faces, triggers in their exits' id order, `oob`
sites in phys-region order; never by value.
`sites.census` counts per surface class the faces, m², share of the
solid area, faces touched, touched in the class's state (`IN_STATE`: a
wall in the air, a slope or slide in states 3/4, a climb in the catch or
the climb, a steep face standing) and used by a find; per site class the
sites, m², share and those tried (a face touched or a volume entered;
an `oob` site's region visited; runs from before the volume record leave
a site with no solid face `unmeasured`), and the level's exits, those
with no logic way in at the kit and of each those reached.
`sites.probes` lists the logic edges out of a saturated zone no
transition reproduced (a probe list, never a refutation). The value
ranker (`draft/value.py`) scores a zone by what reaching it adds at the
kit (3 per location the logic doesn't reach, 2 per exit with no logic
way in, 1 if no logic edge enters it, 1 per gate it is on a side of) and
a site by the zones whose floors lie within 6 m of its anchor points; it
orders the queue and never filters it (past a cut: "not attempted",
with the rank). `devkit sim explore census LEVEL` writes the census
to `--out` from runs' private files; `--rank` writes the queue to the private store
only (the blind protocol keeps the pilot's levels' ranks out of reports).

**The pilot's prerequisites (Step TD.4b).** `l3_goal.TrickExitGoal`
(`make_trick_exit_goal`, a spec's `exit`): an exit's trigger on the
light trick graph, met when the body centre is inside one of its meshes
in any state, with a cost from out of bounds: a row outside every zone
costs the least of the graph's cost and the straight way to the nearest
mesh (its horizontal gap at walk speed plus the height still to rise to
its bottom at 1 m/s; a fall into it is free), and its guidance heads
there, so a body on a top over the trigger isn't pulled back to the
floors. Ablations (`Limits.ablate`: `speed` keys the dynamic cell
without its speed bucket, `options` draws no option, `sites` ignores
the site prior), in the problem's identity only when set; any other
name is refused. The blind protocol: the explorer refuses a start from
an `x36-*` snapshot, a store or a start file under an `x36-*` folder,
in any case (`l3_explore.blind`, from `explore_many`, each pool task
and the script's specs before a start file is read or a pool loads
it). `l3_explore.split(rows)` cuts a
long string into D172 pieces of at most 5,000 ticks (the long-replay
gate), each ending at the last settle point in its reach (10 ticks at
rest on the ground), else at 5,000 ticks marked unsettled (a join in
motion, which counts only from the snapshot where the last piece's
replay halted); `python -m devkit reach l3-gate split` applies it to a stored string.

`python -m devkit sim explore` runs problems ([`devkit/sim/README.md`](../devkit/sim/README.md)).

### The explorer's options and the trick detectors (Step TD.3, D253)

`devkit/sim/l3_options.py` holds the plan's options (§3.2), built
from the dev sources only (the blind protocol: nothing from w1's
torpedo skip or e6's tree-song skip). `l3_explore.OPTIONS` registers all
four by spec as `Limits.options`' default; each reacts to every tick's
row (state, speed, the stored contact normal, flaps left), never to a
site constant, and draws its plan from the explorer's random stream, so
a seed still gives one archive. `Limits.options` enters `Limits.shape()`,
so the default changed every explorer problem's id: a problem recorded
before Step TD.3 reproduces with `Limits(options=())`. `explore()` itself
takes the built `Option`s (`options=`, none by default): `explore_task`
builds them from `limits.options`, and a direct call passes its own.

- **`Hoist`** (`hoist`): from the ground, a run-up of 0-24 ticks along a
  drawn heading, cut short when a full stick stalls under 1.5 m/s
  (against a face), then a jump with the stick held on (turned into a
  face the air contact reports; in the air against a face, that push
  alone) through the ledge hoist, state 0x100 straight from the air
  (0x86920, clips 65 and 66), to its end [X.35's 35 hoist starts, each
  from the air with the stick forward; f6's section 81 has one from a
  standing jump, one from a run-up and one from a slide off a slope with
  no jump, which this option doesn't make].
- **`SlopeHop`** (`slope_hop`): on the slope or slide state (3, 4), a jump
  (along the face's normal, keeping the slide speed, 0x89060) steered
  uphill or across, a flap at a drawn tick while flaps are left and an
  LT+Y recast at another, to the landing [`tricks.toml` bskip method 2].
- **`SteepWalk`** (`steep_walk`): on a face of 0.6 < nz < 0.8 (to 0.7071
  the slope state 3/4 with no friction, then walkable with step-ups; all
  of it off the logic's floor rule, nz ≥ 0.8), the stick at a drawn
  magnitude and angle off the uphill direction the stored normal gives,
  re-aimed each tick.
- **`RollChain`** (`roll_chain`): BLACK, a press on a drawn roll tick
  12-20 for each further roll (one every 19 ticks), and on 60 % of
  firings Y held from the last roll's drawn tick into its end tick, the
  end-tick jump [`tricks.toml` rjump; skips-a A1-A5].
- **Not built:** `CatchCharge` and `Release` wait for Step TD.4's
  climb-column miner (the only charge site measured is the pilot's e6
  tube); `AimedDescent` waits for a landing target (TD.4b's exit goal),
  and its air-steering decay was measured at a pilot site (skips-e).

`devkit/sim/tricks_detect.py` (§3.5) names the tricks a string
used, the same way for an L3 string (`from_l3(rows, pads)`) and an
owner's demo trace (`from_trace`: `devkit/xemu/demo.py`'s recorder
rows; older traces have no stored normal or clip, and the rules that
need them fall back or stay silent). `mine(ticks)` counts each button's
presses, takeoffs (entries into the air), slope contacts (entries into
state 3), slides, hoists and every label; `detect(ticks)` gives each
label at its key tick: `HOIST` (0x100 from the air), `STEP_UP` (0x100
from the ground, clip 53), `ROLL_CHAIN` (one 0x100 run of two or more
rolls), `ROLL_JUMP_AIR` / `ROLL_JUMP` (the end-tick jump: Y held on the
roll's last tick or the next; in mid-air when the body fell during the
roll; a roll off an edge with no Y isn't one), `SLOPE_HOP` / `SLOPE_RECAST_HOP`
(a jump off state 3 or 4, with a recast in its flight), `STEEP_WALK`
(ten or more walking ticks on a 0.6-0.8 face, rising 0.5 m),
`TJUMP_CHARGE` (two or more charging presses in the catch: the plan's
declared leak, the charge law) and `DEFLECT_LAUNCH` (lift off a steep
face with no press), and `CANDIDATE`, the plan's candidate new option:
an 0x100 run no rule names and no attack press explains, with the state
before it and its clip (no other unrecognised signature is mined).
`AIMED_DESCENT` is a control pattern, not a game
event, and `ITRIG` needs the trigger meshes in whole steps (TD.4).
Labels never steer a search.

Measured (Step TD.3, with its
reviews' fixes): on X.35's f6 air-1 run (section 81, from its load to
the fire power) the miner gives the hand counts exactly: 0 BLACK
presses, 22 takeoffs, 10 slope contacts, 3 hoists (and one candidate,
an 0x100 run entered from the slope state). In L3 from the vanilla-flat
spot, `RollChain` gives skips-a A1's roll (21 rows of 0x100, the
end-tick jump at vz +4.643275 m/s) and A4/A5's period-19 chain, a press
on any roll tick 12-20 chaining. `Hoist`, placed on X.35's run-up to its
f6.Z112 to f6.Z202 hoist, makes the same short hoist (clip 66) and
stands in f6.Z202 at 7 or 8 of 13 headings for each run-up of 12-24
ticks; it doesn't make X.35's standing-jump hoist (f6.Z615 to f6.Z082,
0 of 13), and it mounts x7's L3 lip lift (f6.Z821) at one heading of 13
for each of two run-ups. `SlopeHop`, placed on X.35's slide, lands in
f6.Z357 as the owner's hop did, at one heading of nine. `SteepWalk` has
no dev instance: X.35's trace holds no stored normal, and x7's hump
string reaches f6.Z778 by a step-up and a jump, not a steep walk (the
option finishes that climb in 11 of 48 draws). f6's hump (f6.Z778) and
lip-lift zone (f6.Z821), which TD.1 missed in 2 seeds of 2 M ticks, with
the options at the same budget, a find counted only if it stands 30
ticks at rest: at kit 0 (every level written 0, x7's set-up) both in one
seed (1.15 M and 1.01 M ticks in; f6.Z821 by roll jumps, not a hoist),
neither in the other; at the vanilla-flat snapshot's own levels
(3/3/3/3, TD.1's set-up: an LT+Y casts air 3) the hump in both seeds
(0.74 M and 1.20 M), f6.Z821 in neither. The `vanilla-flat` snapshot
holds every element at 3, so a problem that names no kit explores with
air 3 castable (AZ-528).

### The exact xemu replayer

`python -m devkit xemu oracle replay <W> <label> <inputs.json>` runs the input
string in L3 from the snapshot, then replays it in xemu from the same
start and prints the comparison (errors, state and HP mismatches, xemu's
state changes; no positions). The guest must still be halted where
`snapshot --hold` left it: the replayer checks the stop, the entity, its
event clock and `start_sha12`. At each of the player's update entries it
writes the tick's pad (`Sandbox.write_pad`, the one RAM pad writer, with
L3's encoding) and the row's other writes (a teleport's request); at
0x85276 the row's camera direction; at the update's RET it reads the
same `Obs` L3's rows hold, with the same reader (`deep=True` by default),
and `l3_compare` reports, besides the body centre, state and HP, each
field's mismatched ticks and the first tick that differs. The poll and
the latches are the game's own; the frames are pinned to one scene tick
each (`pin_pace`, Step X.20), as L3 renders. In a sitting script: `sb.snapshot(label)`,
then `rows = L3(...).run(pads)`, then
`xo.l3_compare(rows, sb.replay(pads, rows, snap.meta))`.

**Long strings (Step TD.0's gate).** The longest replayed exactly so far:
one string of 3,061 ticks and a chain's exact run of 3,619 (R1.16's
`chain-r116-s123`), then sitting TD.0's one string of 5,214 player ticks
from the w1 beach spawn (2026-10-18: exact on every observed field, every
tick's observation distinct). `python -m devkit reach l3-gate build` draws a seeded safe string
of 5,000 ticks or more from a snapshot (alive, unhurt, untainted, near its
start) and `python -m devkit reach l3-gate replay` replays it with D172's stops, ending at the
first tick off L3 by any distance, state or HP: the gate passes at 5,000
exact ticks. With `--scene` (Step TD.4b) the start is taken at the
scene tick's entry and the string is drawn and run in whole steps, so
the gate is 5,000 whole steps replayed exactly: met in sitting TD.4c
(2026-10-19, v0.15.1) by a 5,215-whole-step string from town's arrival
(`x8-town-k0-080803`, unparked from its parked start), every observed
field equal on every tick, and by the same string's two `split` pieces
(4,946 ticks ending at a settle point, then 269) chained exactly: the
second from `Sandbox.snapshot(here=True)` where the first's replay
halted, L3 finishing that frame on the snapshot's stack. The CLI's
`replay` lets the guest run when it ends, so a chained replay is a
driver's (`l3_gate.replay`, then `snapshot(here=True)`, per piece).
**Demo traces (AZ-475, AZ-508)** replay per tick with
`python -m devkit xemu demo replay`: the trace's pad block at each update entry
and its camera (recorded by the fork's PC hook at 0x85276, or fitted in L3
by `fit-cams` for an older trace) at 0x85276, as above. A trace recorded
with the hook replays exactly but on rows the recorder read mid-update
(AZ-518); an older one can't be fitted exactly through its torn rows
(sitting TD.0: X.36's M2). On v0.15 the recorder takes each row at the
update's RET (Step X.32b), and the replay and `fit-cams` skip a
poller's row that holds the tick before's.

### Chains: the D172 driver (Step X.12)

`devkit/xemu/chain.py` plays a list of segments in one sandbox,
snapshot → L3 search → xemu replay, each segment starting exactly where
the one before halted, with every player update under a recorded pad.
The segments are a plan's spoiler paths
(`src/azurkit/tools/randomizer/planner/plan.py`'s `chain_segments`: per hop of
an item's obtain path the level-file edge the logic takes there, then the
pickup, then with `back=True` the hops of its return path), each with its
kind (walk, exit, pickup), goal, kit and tier. Per segment:

1. **Start:** an L3 snapshot where the chain stands (the first after the
   start's set-up; then `here=True` at the update entry the last replay or
   drain halted at), its metadata linked to its parent (the parent start's
   `meta_sha12`, the string's sha12, the ticks drained), then **parked**:
   `Sandbox.park(tag)` saves the halted guest into the sandbox's own HDD
   clone (`savevm`, never D98's drive) without resuming it, then loads it
   back (Step X.26's checkpoint), so the run goes on from the saved state
   and a later unpark matches it (xemu saves no audio resampler or filter
   history).
2. **Search** (`l3_search.solve` on a worker pool kept for the start):
   the walk's to-node, the pickup's location (`RouteGoal` with the item's
   touch, AZ-483), or the exit's
   trigger (`l3_goal.ExitGoal`: the body centre inside the trigger mesh,
   the game's own test, AZ-483), seeded by the planner's
   route and earlier strings. While it runs the sandbox may be released
   (`release=True`: xemu quits; the slot is kept for its lease) and
   brought back by `Sandbox.unpark` (relaunch, `loadvm` with the guest
   held halted, the replayer's start check).
3. **Replay** (`Sandbox.replay(..., stops=)`): a level load, a stall or
   the first tick whose body centre, state or HP isn't L3's ends it early
   (halted at the next entry) instead of raising; a popup on the way (a
   first gem) is cleared with A through the pad FIFO and the replay
   resumes at the next tick (the event clock checked: no tick lost); each
   replay goes into the conformance corpus. Strings up to `DEEP_TICKS` (600)
   read the deep observation, longer ones the core (X.10's 40 extra reads
   a tick). The outcome: a walk's replay equal to L3 (body, state, HP
   every tick) or xemu's last tick in the goal; an exit's destination
   loaded; a pickup's own inventory field changed (`power_water`: the water
   level; a gem picked up on the way doesn't count).
4. **Drain:** from where the replay halted, the neutral pad at each of
   the player's updates (each counted), through a level load and any popup,
   until the player has stood `SETTLE` (6) ticks in the new level or after
   the pickup; it halts at an update entry, the next start. A walk whose
   replay took the next segment's exit on the way counts that exit as done.
5. **Repair:** a search that found nothing tries again on a ladder (4x
   the budget, skipped when every seed stalled at one cost to go; a
   broader exploration, `temp` 30 and `pursue` 0.3; the phys profile's
   graph); a replay that diverged or missed its goal is re-anchored (a new
   snapshot where it halted, its ticks kept as a piece of the chain) or,
   when the player died or left the level, undone (the parked start back);
   after `repairs` (2) the chain stops and `chain.json` names the segment
   and why.

`chain.json` (public, in the sitting's evidence folder): the plan's
sha256, seed and share, the build's hashes, and per segment its starts
(hashes, parent, parked tag), each attempt (search counts, seconds, taint,
robustness and the tier it supports, the replay's comparison and seconds
a tick, the outcome, the drain) and its string (run-length pads, the
camera as f32 pairs, `input = "analog-ram"`) with its sha12: no position,
no RAM. Snapshots stay in the private store; parked states outlive W
(below).

```python
from devkit.xemu import sitting as xs, chain as xc
segs, ident = xc.plan_segments(plan, sphere=1, item=0)        # back=True: the return path too
with xs.Sitting("chain", step="R1.16") as s:
    xc.park_check(s)                                          # optional: the measurement below
    xc.boot_start(s, build, segs[0]["kit"])                   # the build booted, the plan's kit (R2)
    rec = xc.Chain(s, segs, out=s.ev / "results" / "chain.json", ident=ident).run()
```

`boot_start` boots the build (`Sandbox.boot_build`, by default SaveGame #1
of the `vanilla-ig-w1` drive: the all-powers character on w1's save
platform nearest the beach; `tag="vanilla-ig-new", save=2`: the D98
drive's new-game character in w1, AZ-354), sets the plan's kit (R2:
those element levels, the others 0) and, with `quiet` (the default),
marks every first-pickup popup
seen, as `devkit/reach/l3_certify.py`'s kit does: a popup's wall-clock time to clear
let the world drift between two replays of one string near enemies. It is
a placed start. The build must boot: a vanilla state `loadvm`'d with the
build in the tray plays the levels its own boot cached on the HDD
(hazard 8; sitting x12b collected vanilla's obsidian at w2/g0/r1364 that
way).

Releasing costs the slot: a released sandbox keeps it for its lease (10
min), then a relaunch queues like a new one (D108). Under load the
validation's relaunches waited 33 min once; `--release waiting` (the
default) releases only while another sitting waits.

**Parked starts outlive W (Step X.15).** W lives in `/tmp`, which a
reboot clears. So `Sandbox.park` also APFS-clones W's HDD (its `savevm`
tags inside; the guest is halted, the VM stopped and its drive flushed),
each parked disc and `parked.json` into the private L3 store's
`parked/<W name>/` (a tenth of a second); `down` deletes that folder unless
kept. After a reboot a sitting started on that drive
(`Sandbox(hdd=<dir>/xbox_hdd.qcow2)` or `AZURIK_XEMU_HDD`) takes the
starts over with `Sandbox.adopt_parked(<dir>)` and `unpark`s them; the L3
snapshots are in the store already.

**Whole steps in a chain (Step X.15).** `Chain(scene=...)`: `True` searches
and runs every segment in whole steps, `False` none, and `"diverged"` (the
default) switches a segment to whole steps once a replay of it left L3's
trajectory (the world moved the player: an enemy's push or hit), from the
re-anchored start; since Step X.19 only when it left within `SCENE_AFTER`
(300) ticks, else the re-anchor searches in player ticks again (a long
approach's remaining 1,500 ticks in whole steps found nothing in 2 h). Joins stay update entries: a format 3 start holds its
thread's stack, so L3 finishes that frame and runs whole steps after it.
A whole-step search's budget is the steps over `SCENE_COST` (10).

**Hints, tours and actions (Step X.19, R1.16's driver).** Each hop of
`chain_segments` and `tour_segments` carries hints the planner reads from
the data, never from a seed:

- `mech`: what the hop passes, the edge kinds of the cheapest derived
  zone path the level-file edge was contracted from (at the hop's kit and
  flags, through no zone another node anchors), or `hand` when there is
  none (a hand edge, an exit the authoring moved);
- `scene` (whole steps) when that path rides a rig (a lift, a moving
  platform, a gondola) or a teleporter's wiring, or touches a switched
  (timed) push volume, and for carts and teleports; a from-node with
  several zones counts each zone's own path too, as the hop starts where
  the last segment ended (w1_cove > w1_beach from W2_W1b's arrival in
  w1.Z009 goes up a teleporter's field to w1.Z120);
- `fall` (`RIDE_FALL`, 600 ticks) when it rides an updraft, for a cart,
  and for a hand hop whose from-node touches a push volume (an updraft or
  a current: the derived events' touch platforms), which is also a `ride`
  with a seed recipe `{"ride": volume, "every": 8}`: the driver walks onto
  the volume's foot (the planner's walk to the walk vertices under it) and
  jumps every 8 ticks for the fall's length (X.15's spout string);
- `seeds` with `{"proof": ref}` for `proofs.jsonl`'s edge proofs between
  the hop's zones. The driver also seeds each search with the winners of
  earlier chains' segments of the same kind, level, from-node and goal
  (every `results/chain*.json` in the evidence folder).

So w1's spout exit (a hand exit from w1.Z180, where the timed
SpoutPush1Shape is touched) is a ride in whole steps with a 600-tick fall
and a seed onto the spout's foot; enemies have no data, so `"diverged"`
still switches a segment to whole steps after a push or hit.

`tour_segments(plan, logic, spheres, back=True)` (`devkit/xemu/chain.py
--tour`) plays whole spheres as one chain (each segment names its
`sphere`; `counted=False` leaves the obsidians out; `victory=True` ends
at the victory flag's event, d1's Spideyzar killed, in place of the way
back; Step R1.16): from the start to each item a
sphere collects (its progression items and the counted ones), the nearest
next first, then home by the last item's spoiler return path (by what the
round's escape picks up where the logic has none). Before a hop it plays
what the logic only credits: a `barrier` segment for each barrier the
edge crosses (its shapes and the staff's elements; a permanent one once)
and an action for each button or event the rule, a location's gate or an
`assumes` needs (`button`, `minigame` for the solvers' events and gates,
`event` with `how`: touch, hit, action, killed), each after the path to
its node. A pickup whose requirement names a minigame's event (w2's
power_water, `w2.hose.won`, Step R1.8o) gets the minigame first, unless
the tour played it on the way. A one-shot exit (`plan.one_shot`: its
gate's switch only ever turns off, d1's bridge-end cutscene into d2) is
taken once; after it the tour's ways leave it out, and where the logic
then has none it takes a ride the logic leaves out (`plan.RIDES`,
`kind = "ride"`: d1's elevator from floor 7 back to floor 1, X34's
RP-F; Step R1.16d, AZ-477). On the
golden seed the whole game is 1,199 segments (171 pickups, 57 barriers,
50 events, 31 buttons, 4 minigames, 4 carts, 1 disc teleport).
Step R1.16 (plan `0920ab9bc045`, 23 spheres): 1,212 segments to the
victory, 954 once `merge_walks` joins each run of plain walks of a level
and sphere (no whole steps, fall, ride or escape) into one search of up to
four hops. A minigame played at two stations starts at the first (w2's
hose: the console's `w2.hose.on`, then the joystick's `w2.hose.won`), and
an action's way there uses no flag the tour hasn't set where it stands (d1's
walkway opens by touches at its far end). A pool search grades only its
winner, its robustness trials as tasks across the pool; a winner is
searched again for robustness only where the plan's tier is needed (the
hop's level-file edge has a `difficulty` above safe).

The driver plays `cart` and `teleport` as exits; `minigame`, `barrier`,
`button` and `event` walk up to their object (an `l3_goal.ObjectGoal`,
searched and replayed as a walk) and then act with real pad input in
closed loop: `devkit/xemu/minigames.py`'s solvers, a barrier's staff cast
(LT, each element's button, release), three attacks and the walk
through (sitting r113's recipe), X at a button (a seal, whose toggle
fires on a touch of its shape, is stood on instead: d1's), a touch pad
entered (the body centre inside its shape, then its `touch` read:
AZ-483), a hit; a boss fight (`killed`: d1's Spideyzar) waits for
the critter on his generator's list (touching the call field his enable
names when none comes), enters the game's no-damage and refill cheats
with the pad ([assisted]: the placed kit lacks a playthrough's HP and
fuel), selects EAFW (an armor AI blocks no `elem` hit) and swings in
closed loop on his body and HP until it reads 0, then drains into the
kill's outcome (his generator's `numDead`, the victory's movies); a ride on
d1's elevator (`rig`, Step R1.16d) presses the floor switches and rides
the colours its wiring plans from the elevator's live state. A minigame played at more than
one place has stations (`STATIONS`: the hose's console, then its joystick
about 95 m away and the fires), each an approach, its part of the solver
and a drain. A search whose start the logic profile's cost field doesn't
reach (and the phys one's does: the hose's console from the pool) runs on
the phys graph from its first rung. A re-anchor farther from the goal
than its parent (the goal's cost to go, plus 2 s) is dropped and the
parked start brought back instead (sitting x19: a mover pushed the player
off w1's ridge into the water, where the search would climb the rocks
again); so is a re-anchor where every run of a failed search keeps
`STUCK_CELLS` (8) cells or fewer, the body stuck (w2's slippery ice-cave
stairs: 4 cells in 2 h of whole steps). `warp` is `Sitting.warp`'s
debug-menu level warp (placed: only where the plan allows a placed
start). An action's ticks are counted by the player's event clock; its
input is real but no replayed string. A winner whose robustness supports
a harder tier than the plan's is searched again in other shapes
(`ROBUST`, `--robust`; each try capped at `ROBUST_S`, 600 s) and the most
robust replayed; not a whole-step winner, whose re-search and trials cost
about half an hour (its robustness takes `SCENE_TRIALS`, 8, trials). The sandbox is held
by default (`release=False`).

**Parked starts (sitting x12, 2026-10-13):**
on `vanilla-beach-shield5`, a snapshot's start parked by `savevm` in
0.39 s (the guest stayed halted, status `debug`); brought back by
`loadvm` in the same xemu (0.09 s) and after quitting xemu and
relaunching it on the same W (relaunch 1.0 s, `loadvm` 0.08 s), the
guest was bit-identical to the snapshot each time: every user page
(4,441 pages, the snapshot's sha256), the registers, the start hash and
the entity's five-page neighbourhood; and the beach string (106 ticks)
replayed exactly from each (0.0 m, states and HP equal every tick) in
9.0-11.5 s (deep reads); the same again on the fork build 0.14-8 (sitting
x12b: `loadvm` 0.07 s, relaunch 0.6 s). So the sandbox need not be held
during a search: a chain parks every start and may quit xemu while L3
searches.

**Validation (sittings x12 and x12b, 2026-10-14):** the golden seed 12's
sphere 1 under the R1.2b defaults (plan `8a10695a046e`, `AZR-AAEA`; build
`abed5e8497a4`, vanilla code): `power_water_a3` at w2/g0/r1364, obtain
path w1_beach > w1_z005 > w2_z002 > w2_z006.

| Segment | Search | Replay in xemu | Robustness |
|---|---|---|---|
| walk w1_beach > w1_z005 (the opening climb, an assumed hand edge) | 1,603 s, 16 x 400,000 steps: no string; every seed stalled 30.7 s short (straight-line guidance: the derive has no way up from the beach), tainted `read`: inconclusive | not played | |
| exit W1_W2_Fall | not reached; an R7 hop to its arrival instead (placed) | | |
| walk w2_z002 > w2_z006 | 71 s, 249 ticks | exact: 250 ticks, 0.0 m, 23 s (93 ms a tick, deep) | 0.875 (standard) |
| pickup w2/g0/r1364 | 472 s, then 599 s, then 221 s (two re-anchors) | diverged at tick 113 (0.34 m: pushed), then at tick 5 (hit: state and HP), each re-anchored where it stopped; then exact: 789 ticks, 0.0 m, 27 s (34 ms a tick, core); water 0 -> 1 | 0.06 (frame_perfect) |
| walk w2_z006 > w2_z041 (return) | 810 s: no string, best 2.3 s short; stopped by hand | | |

Every join was an exact `here` snapshot linked to its parent; the
pickup's three starts chain through the two failed pieces. Earlier runs
on vanilla-cached w2 (a `loadvm`'d vanilla state with the build in the
tray, hazard 8) replayed the same walk exactly three times, cleared a
first-gem popup mid-replay and resumed exactly, and replayed a 925-tick
pickup string exactly onto r1364's vanilla obsidian (refused as not the
plan's item). Enemies near r1364 push and hit the player in xemu but not
in player-tick L3; the same string from the same bit-identical start
diverged the same way at tick 152 twice, then differently (12.5 m and
8.0 m at most), a popup cleared by wall clock in between [inferred cause;
hence `quiet`].

**Validation (sitting x15a, 2026-10-14,
fork build 0.14-8, the vanilla disc):**

- **File reads and modes:** at w2's and e2's arrivals (R7 hops) a 184-tick
  string with jumps and attacks ran in L3 three ways (player ticks with the
  reads served, player ticks with reads as zeros, whole steps) and was
  replayed once in xemu: every trace 0.0 m off, states and HP equal; the
  whole steps read two `characters.xbr` pages from the disc and, from a
  format 3 snapshot, nothing L3 doesn't hold (no taint). 530-580 player
  ticks and 41-66 whole steps a second on one core at load 20-35.
- **Whole steps by enemies:** X.12's pickup at w2/g0/r1364 (vanilla's
  obsidian), searched in whole steps from its update-entry join (16 seeds
  of 40,000 steps, 1,150 s, mostly on one worker while other sittings
  waited): 817 ticks replayed exactly (46 ms a tick), by the enemies that
  pushed and hit X.12's player-tick strings.
- **The w1 opening** as the owner gave it (2026-10-14: along the rocks
  above the water, then a jump into the spout): from `vanilla-rz-new` (a
  new game on the beach), beach > w1.Z026 (the first rock's rim, 474
  ticks, robustness 0.94) exact; Z026 > Z046 along the rocks: a mover
  there pushed the player off L3's trajectory three times (player ticks at
  tick 125; whole steps at 155 and 348, after matching an enemy's hit,
  state and HP, tick for tick), each piece re-anchored and kept, then
  exact; Z046 > Z180 (the rock in the spout, 448 ticks) exact; Z180 >
  W1_W2_Fall in whole steps (156 ticks, robustness 1.0: a walk onto the
  spout's foot and a jump every 8 ticks while its timer lifts the player
  179 m along the push cylinders into the trigger) exact, then w2 loaded
  and the drain settled there. The search needed the segment's `fall`
  (600: the ride is about 150 ticks in the air) and a seed string.
- The rocks' 0.25 m drifts came after exact hits; Step X.20 found the frame
  outside the step (the render's random numbers, the polls once a frame,
  xemu's free pacing) and its sitting replayed these strings exactly
  (below, "Validation (sitting x20a)").

**Dress rehearsal (Step X.19, sittings x19, x19d, x19e, 2026-10-14):** sphere 1's tour from a real new game
(`vanilla-ig-new`, SaveGame #2), every segment searched and replayed
exactly or re-anchored. Sphere 1 is the same 14 hops on every golden plan
of the day (seed 42; seed 2 before and after R1.8m's fill): the w1 opening
along the rocks, the spout into w2, w2/g0/r1346 behind the hose,
w2/g0/r1364, FireWall_02, back by W2_W1b and the cove.

- x19 (xemu 0.14-8, real time, L3 before X.20, seed 42): the beach climb
  exact (1,114 ticks); a mover on the rocks and the ridge pushed four
  player-tick replays and two whole-step ones off L3 (one into the water:
  the lost-ground rule), each repaired; the spout exact in whole steps (240
  ticks, robustness 1.0, from a ride seed); the hose console not reached
  (below); the w2 walk exact; r1364 pushed by enemies three times.
- x19e (xemu 0.14-12 deterministic, X.20's L3, seed 2 under R1.8m's fill,
  plan `0169689deb99`): beach 7.6 min (a late divergence at tick 558, then
  player ticks again, 358 ticks exact, robustness 0.94); rocks 35 min
  (player ticks pushed at tick 141, then 605 whole steps exact by the
  mover); ridge 2.7 min; spout 5.9 min (193 ticks exact, robustness 1.0);
  the w2 walk 1.3 min (252 exact); r1364 37 min (pushed at tick 29, then
  1,209 whole steps exact by w2's enemies, power_water taken). With X.20
  and X.22 every whole-step replay was exact; only player-tick strings by
  movers and enemies left L3, as designed.
- The hose (w2/g0/r1346's minigame) wasn't played: the logic reaches its
  console (w2.Z073) only with air 1 at frame-perfect and its joystick
  (w2.Z022) only by the ice-cave stairs R1.8k removed; a 2,700-tick
  phys-graph approach from the pool left L3 at tick 1,139 on those stairs,
  where no search moves the body. The later tours leave it out.

### The conformance corpus (Step X.10)

Every xemu replay of an L3 string (`python -m devkit xemu oracle replay`, the sitting
kit's `l3_replay`, `devkit/reach/l3_certify.py`'s replays) appends a record to the
private store's `conformance.jsonl` (`devkit/sim/corpus.py`): the
snapshot's label and metadata hash, the mode, the string (segments with
the camera as the f32 pairs L3 read, and its other writes, a teleport's
request among them), and per tick both backends' digests of the body
centre, state and HP and of the whole `Obs`. Its summary is
coordinate-free: passed (every tick's body centre, state and HP equal,
D170), the first diverging tick, the first tick any observed field
differs. After a change to `l3.py`, Unicorn or macOS,
`python -m devkit sim conformance` runs every string in L3 again from its kept
snapshot and compares with xemu: a record that passed and now diverges is
a regression (exit 1), and a change in L3's own trace is named by its
first tick. The corpus starts empty at X.10: it fills with the next
sittings' replays (the earlier ones kept no per-tick xemu observations).

### Validation (sitting x6, 2026-10-13)

Each string was run in L3 from a fresh snapshot, then replayed in xemu
from that start, on the kept build 0.13.3-37-gd5ad94f4bf. Every tick matched bit for bit:

| String | Start | L3 mode | Ticks | Path (m) | Max error (m) | States (xemu) | L3 ticks/s |
|---|---|---|---|---|---|---|---|
| walk: full, diagonal 0.6/0.6, half stick, release | `vanilla-rz-new` (w1), update entry | player tick | 120 | 18.3 | 0 | 0 | 1,134 |
| jump: run, Y 6 ticks, land, an air-steered second jump | `vanilla-rz-new`, update entry | player tick | 130 | 28.6 | 0 | 0, 2, 0, 2, 0 | 1,766 |
| sideways: a teleport, then the stick right with the camera yaw turning 3.33° a tick | `vanilla-flat` (f6), scene entry | player tick | 121 | 25.5 | 0 | 2, 0 | 779 |
| the same | the same | whole step | 121 | 25.5 | 0 | 2, 0 | 192 |
| CLI `replay`: walk, jump, partial stick, yaw 1.0 | `vanilla-beach-shield5` (w1 slope) | player tick | 106 | 27.6 | 0 | 0, 2, 0 | |

HP and state matched on every tick; a rerun after a reset was identical;
a reset took 4-6 ms.

### Validation (sitting x20a, 2026-10-14: the frame outside the step)

Step X.20 (AZ-358, AZ-361),
xemu 0.14-8 offscreen, every start placed (`vanilla-rz-new` and an R7 hop,
the popup bits), replays pinned to one tick a frame unless marked free.
"Exact" is every tick's every observed field; the generator and the camera
were compared at every player-update entry too.

| String | Ticks | Old L3 (no render) | L3 with the render |
|---|---|---|---|
| r18k2's bridge walk from the W1_Town arrival (AZ-361), pinned twice (the two replays identical) | 491 | parts at 293, never hit | exact, the insect's hit at 298 (HP 200 to 185); the generator equal every tick |
| the same, free: two replays, which part from each other at 281 | 491 | parts at 281 and 301 | given the second's frame boundaries, exact with the stream poll once a frame (at 274 with it each tick) |
| a new bridge walk found in L3 from a pinned start, across into the plaza | 564 | parts at 277 | exact, one insect hit; generator and camera equal every tick |
| X.15's w2 walk and r1364 pickup, end to end, by w2's enemies | 1,067 | parts at 396 | exact, a hit (HP 185); generator and camera equal every tick |
| X.15's w1 rocks attempts 2 and 3 (AZ-358), pinned; free twice; from X.15's re-taken root | 156-505 | exact | exact through the mover's hits (HP 200 to 185 to 175) |

### Limits

- The camera direction the player's input reads is an input: a string
  sets its yaw per tick, or keeps the snapshot's. The cameras themselves
  move in whole steps (the render, Step X.20), not in player ticks.
- In player-tick mode nothing else moves: rigs, platforms and enemies
  need whole-step mode. Push volumes and updrafts are the player's own
  update's (a teleport into each of w1's 14 updraft volumes gave the same
  rows in both modes for 45 ticks, Step X.15), and so are springs: the
  autoSpring launch is jump_init 0x89060's, whose six callers
  (0x8D15A-0x8D48B) are the player's own state ticks [verified static].
- Only the stream module's file reads are served (the only reads seen in
  a step); the prefetch thread and the rest of the main loop don't run:
  the sound list's update, DirectSound, the cache pump 0x58D00 and the
  present (none drew a random number or changed a replay in sitting
  x20a).
- USA only (D146); a Europe XBE is refused by name.
