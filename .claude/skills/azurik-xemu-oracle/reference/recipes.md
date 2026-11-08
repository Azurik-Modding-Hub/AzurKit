# azurik-xemu-oracle reference: recipes (§4.2-§4.7)

Part of the `azurik-xemu-oracle` skill. Here: the tick-locked trace, pokes,
the release checklist, skip confirmation, the route pilot and chains (§4.1,
code identity, is in the card). The card, `../SKILL.md`, holds the rules,
the slots and the sitting loop; the § numbers and hazard numbers are the
skill's (Step 2.216 moved this text here word for word).

## 4. Recipes

**4.2 Tick-locked physics trace.**

- Break on **0x8CCC0** (player state machine; return 0x8C382). In
  vanilla at 30 fps it hits once per tick, with rare duplicates (the
  harness drops them); dedupe on `+0x9C` and record the return address.
  On a 60 fps build every tick hits twice.
- The entity is `[esp+4]` at 0x8CCC0, or ESI at a breakpoint on
  **0x89060** (`player_jump_init`, called every tick from 0x8D15A). It
  changes per level and per boot: re-derive it per state.
- Guest time stops while halted: per-tick physics from a given state is
  deterministic; enemies and audio aren't.
- **The Training Arena freezes bbox and position** (in a roll the
  position froze for 7–15 ticks, then jumped). v0, Δvz, the airborne tick
  count and walk speed are good there; measure the apex and roll
  distance in level 1 or a D98 field state.
- **A save-loaded or level-changed entity has no usable position:** its
  +0x38..+0x40 and bbox hold constants or denormals. Measure v0 and tick
  counts there, or an apex from a field state. A level change's new
  entity spends its first 4-6 rows in state 2 at (0, 0, 0): measure from
  its first ground row.
- `oracle jump` (the harness's `capture`): waits out the
  Training Arena's intro (its player tick runs with Y ignored, then the
  welcome dialog opens about 12 s in: 20 s of steady ticks,
  `ARENA_STEADY_S`, AZ-370), presses jump
  on the first ground tick at or after tick 4, holds it 6 ticks, and
  reports v0 = vz on the first 0 → 2 tick; `$W/jump.json` holds
  `{meta, rows, hits}`, a folded duplicate counts in its row's `dups`,
  and each row has every field of `oracle.ENT` (with the return
  address and `fctrl`).
- **Measured vanilla:** jump v0 4.6432748, Δvz −0.326667 per tick, 28
  airborne ticks (the same, bit for bit, on v0.14-12 deterministic, cold
  in the arena and from `vanilla-flat`: sitting x24), apex 1.0235 m (level 1); walk = `runSpeed` × stick,
  7.00009 m/s at full stick on flat ground after 2 sub-target ticks
  (3.26691, 6.53610, then 7.00009; the stop 7.00009 → 3.73227 → 0.46353
  → 0), 6.87 m/s on the 14° level-1 slope; the roll 3.375–3.387 m in 21
  ticks; swimming approaches a 10.0 m/s target by a 0.1^dt blend. A
  k = 2 roll (a RAM poke) went ×1.835 from standing and ×1.957 from a
  run. More in `azurik-game-reference`.
- Against an obstacle the velocity fields overstate motion (0.38 m/s
  read, 0.095 m/s realized): measure realized motion from the bbox or the
  position over windows.
- Spike scripts: `jump3.py <label> <ticks> [VA=float | VA:hexbytes …]`
  (hex VAs) pokes, presses jump at tick 4, releases at 10 and writes
  `jump2_<label>.json`; `walk.py <label> <scancode> <ticks> [VA=float]`.

| Entity field | Meaning |
|---|---|
| +0x24 / +0x28 / +0x2C | vx / vy / vz (against an obstacle x/y overstate motion; at a face y's sign flips every tick) |
| +0x38 / +0x3C / +0x40 | position. **It doesn't follow the body in the air:** with no contact it doesn't change (also frozen while swimming); on a contact it jumps to the contact point. On the ground z = bbox min + 0.5 |
| +0x19C..+0x1B0 | bounding box, a 3 m cube: min (x − 1.5, y − 1.5, z − 0.5), max (x + 1.5, y + 1.5, z + 2.5). Its min z **+0x1A4** is the airborne height (in vanilla it changes on every airborne tick). It can repeat the previous tick's value (take the arc's maximum and check the apex row isn't stale), and in some entities (town, save-loaded ones) it holds constants: check that it moves before using it |
| +0x94 | state (full list: `azurik-game-reference` §2): 0 ground, 1 climb, 2 air, 3 slope, 6 swim, 7 dead (set on any tick with HP ≤ 0), 0x100 the ground attack move (A; the roll; the step-up 0x8B1D0 sets it for 5 ticks), 0x102 the air attack move (the hit handler 0x8D600 writes it at 0x8D693: 13 ticks of 0x102, then 6 of 2, then 0 after a hit). The setter 0x8BDB0 (EAX entity, ECX state, [esp+4] animation, RET 0x20) writes only the 0x100/0x101 changes: a breakpoint on it misses ground, air, slope, hit and death changes |
| +0x98 | the previous tick's state |
| +0x9C / +0x144 | state timer (0 at takeoff and landing, not at a flap; +1/30 per tick in vanilla) / jump height 1.1 (1.2 with air power, written by 0x83F90 on the jump tick) |
| +0x148 / +0x14C | hold-jump timer and its vz. **+0x148 counts −1/30 per held airborne tick; released in the air it reads 0.0 on the next row; released on the ground it keeps its value**; after each flap it reads −0.0333 for one held tick, then 0. +0x14C stayed 0.0 in every capture |
| +0x164 | peak_z, **written only on the jump tick**: input z + h, where the input's +0x54..+0x5C is the bbox centre. Flaps don't re-latch it and landing doesn't reset it, so a standing value is stale |
| +0xD8, +0x140 | flap counter (+1 per flap, 0 at landing; armor_mgr keeps no counter), air control (9.0, or 12.0 with air power, written by 0x83F90 on the jump tick) |
| Jump tick | +0x94 0 → 2, +0x9C → 0, +0x164 → input z + h, +0x140/+0x144 → 12.0/1.2 with air power, +0x150 0 → 1 (it stays 1), +0x30 → 0, +0x60 → 0xCC008000, the ControllerState+0x4B latch 0 → 1. At landing +0x30 becomes a pointer and +0x60 0xCC008050. +0x168 (the fall reference, once labelled prev_z) changes on ground ticks only |
| ControllerState | 0x37BE98 + player_index × 0x54 (`AZURIK_CONTROLLER_STATE_VA` and `ControllerState` in `shims/include/azurik.h`); port 2 = index 1. Injected A shows at +0x18 two ticks later. Input flags (input+0x20 low byte): 0x80 with Y up, 0x86 on a fresh press, 0x82 held with the latch set |

**4.3 Differential RAM pokes.** Baseline, poke with read-back, re-capture,
compare against the model's *ratio*. Pokes are RAM-only on a cloned HDD.
On the 60 fps dev snapshot (dt = 1/60):

| Poke | Measured | Model |
|---|---|---|
| none | v0 9.28655, Δvz −0.16333/tick | √(2·39.2·1.1); 9.8/60 |
| gravity 0x1980A8 = 4.9 | Δvz −0.08167; **v0 unchanged** | dev jump site reads 0x1001D8, not gravity |
| `89162:a88019` (FLD at 0x89160 back on 0x1980A8) | v0 4.643274784…, bit-identical to Unicorn | √(2·9.8·1.1) |
| 0x1001D0 = 7.0 | 6.97 m/s (ratio 0.502) | 7.0 |

The gravity row is the "bytes landed but nothing changed in game" class.
**Code pokes work on vanilla states:** a gdbstub write into `.text`
takes effect at once, and the next `loadvm` restores it (e.g. the flap's
entry cost, the `PUSH imm32` 1.0f at 0x8934E; the swim FMUL's disp32 at
0x8B7C1 repointed at 10·k in `.text`'s tail padding 0x1001D0). A RAM
rewrite of ControllerState's stick y at the input builder's entry
0x84F90 gives a partial stick the keyboard pad can't. Such a stand-in
shows a mechanism, not a build: name it so in the REPORT.

**4.4 The 5-minute release checklist.** **When:** once per packer
change, per new shim and per release. **How:** a cold boot of an ISO
built from vanilla in one pass, in the §2 sandbox; write the result into
the sitting's REPORT.

1. Boot past the logos.
2. Start a new game.
3. Walk, jump and flap in town (a new game has no air armor, Flaps = 0:
   flapping needs an air shield first).
4. Take one level transition.
5. Save and reload.

**4.5 Confirming a randomizer skip (D114).** A skip, a named and located
use of a trick (Modkit's randomizer plan, §2.15), enters the
randomizer's logic only once it is reproduced in xemu with exactly the
kit it encodes, or confirmed by the owner:

1. **The exact kit.** Poke the element levels and items to the skip's
   `requires` and no more (the other elements to 0). A skip that only
   works with more than its kit is not confirmed as encoded.
2. **Real inputs from a reachable spot.** A `loadvm`, a teleport or the
   kit poke may set up the start; the attempt itself is controller input
   through the FIFO only, with no RAM write during it.
3. **N attempts.** Record attempts, successes and the input window that
   works; the window and the rate per attempt set the difficulty (D259:
   2 standard to 4 frame-perfect, the hardest hop graded).
4. **Record it.** A pass goes into
   the randomizer plan's trick table (2026-10-10) as
   `confirmed = { by = "xemu", ref = "<sitting>/<row>" }`, and the
   REPORT says what was placed and what was real input. A failure leaves
   the skip held.

Skips seen in a speedrun video go first in the queue
(`tricks/REPORT.md` §2) but stay held until reproduced. Plain jumps and
flaps inside the measured envelope are not skips.

**4.6 Walking to a target: the route pilot (Steps X.2, X.4).** A sitting asks
`devkit/xemu/route.py` (Step 4.13d2) to walk the player there
with real pad input; set the start up first (`loadvm`, a hop, R6, the
kit), then:

```python
from devkit.xemu import route as xr
R = xr.router(iso, "e2")                           # reach model + route graph: minutes; build once (or pickle the Reach)
res = xr.walk_to(sb, R, "e2.Z006", tier="hard", air=0, ticks=2400, label="z191-z006", log="legs.jsonl")
                                                   # a zone; or "e2_z006" (a level-file node), "e2/g0/r733", (x, y, z)
res["reached"], res["why"], res["left_m"], res["end_zone"], res["legs"], res["plans"]
```

- `xr.router(iso, level, "phys")` routes over R_phys's floors when the
  logic profile has no way; walking up a slippery or (R_phys) steeper
  than 0.8 face is never planned (the body slides back). `xr.plan(sb, R,
  target)` plans without moving; `xr.last_pilot.trace` holds the
  positions (private: keep them in `$W`).
- The planner (`devkit/rando/draft/route.py`, Step 4.13c) follows walk,
  swim, jump, step, flap, drop, slide, climb, gate, door and ride (wait)
  edges; teleports, updrafts and currents are not followed. A ride that
  doesn't move in 10 s, a flight that misses twice and a stuck walk are
  replanned around (10 replans).
- **The pad (X.4):** an analog left stick, written each tick at
  `INPUT_BUILD` 0x84F90 (a `capture` hook) through `Sandbox.write_pad`
  (the one RAM pad writer, `stick_only`), inside a real pad's round gate
  (`route.stick`); buttons and the camera through the FIFO.
  `analog="pipe"` (Step X.14) sends that stick as the fork build's pipe
  `axis lx|ly` lines instead (the pad's own path, no RAM write, a tick or
  two later). `analog=False` is X.2's FIFO-only pad, for a D114 confirmation. A jump
  onto a ledge over the kit's apex less 0.15 m is a lip lift (takeoff in
  the tier's window, track through the face's middle); a ride goes to its
  decoded trigger pad first; guessed rides on machinery aren't planned
  (AZ-353); exit and camera triggers cost 120 s (they take the player
  over: input+0x30, which the pilot waits out); HP loss under 60 % of
  max retreats and holds. `log=` writes one coordinate-free JSONL line
  per leg (planned against actual, a flight's arc relative to its
  takeoff).
- **Measured (sitting x2, 2026-10-13, its evidence):**
  walks and swims of 50-300 m follow their way-points; a 0.72 m step 2 of
  2 and a 7.3 m gap jump landed 2 of 2; logic-routed zones from a field
  state 3 of 8 (lost: a lip-lift ledge, a slide off a hump after a
  landing, two hard-tier 16 m drops onto ledges under 0.5 m wide, a ride
  whose trigger isn't decoded); e2's hand connections Z028→Z000 and
  Z041→Z000 walked, Z191→Z006 and Z000→Z041 have no planned way, and
  Z000→Z003 waits on rides that don't move; w2's r1357 not reached (an ice
  ramp slides back; the climb it then needs wasn't reached).
- **Measured (sitting x4, 2026-10-13, its evidence):**
  the analog stick walks 7.0 × its magnitude along camera + atan2(-x, y);
  X.2's 15 targets 8 of 15 on the final code (X.2: 9): gained the 16 m
  drop onto e2.Z1844's narrow ledge and f6.Z609's lip lift, lost one f6
  step try (an enemy, the 450-tick budget) and e2.Z028→Z000 (the jump
  leaves the rim in slope state 3/4, vz 2.0–2.8). Lip lifts: f6.Z806's
  (0.29 m deficit) mounted 9 of 9, f6.Z804's (0.41 m, a 0.75 m-wide face)
  0 of 8 (the body glances off its corner). Still out: a climb (state 1
  reached on w2's face by hopping into it, then no climb up), the slope
  band nz 0.80–0.87 (slides off f6.Z806's hump and e2 rims), R_phys drops
  the body walks across (e2.Z003), e2.Z1408's 16 m walk-off.

**4.7 Chains: snapshot → search → replay (D172, Step X.12).** For a
playthrough or any run of segments (R1.16's golden seed), use
`devkit/xemu/chain.py` (Step 4.13d2; `docs/SIMULATOR.md` § "Chains"), not a hand loop:
`xc.boot_start(s, build, segs[0]["kit"])` (the build booted at SaveGame
#1, or `tag="vanilla-ig-new", save=2` the new-game character's save, the
plan's kit set: a placed start; never a vanilla state with the
build in the tray, which plays the HDD cache's vanilla levels, hazard 8),
then `xc.Chain(s, segs, out=...).run()`. What it guarantees
and what a sitting must not undo:

- **No tick unrecorded:** each start is `snapshot(here=True)` at the
  update entry the last replay or drain halted at; the drain writes the
  neutral pad at every player update it lets run (through a level load or
  a popup, A through the FIFO). Never `run()`/`release()` the guest
  between a replay and the next snapshot.
- **Parked starts:** `Sandbox.park(tag)` is `savevm` into W's HDD clone
  with the guest held halted (never `savevm`, which resumes it first),
  the checkpoint (hazard 13: the run goes on as every `unpark` does):
  deterministic the save alone, else `loadvm` of it with the
  guest still held (0.06 s); it also keeps an in-memory
  checkpoint (§3), which `unpark` in that xemu restores (sitting x30
  medians: park 0.10 s, unpark 0.014 s against `loadvm`'s 0.032 s); `Sandbox.unpark(tag, meta)` relaunches
  if needed, restores the checkpoint or `loadvm`s the tag (after a
  relaunch) with the guest held and checks the start. Measured in sitting x12: bit-identical
  user memory, registers and start after `loadvm` in the same xemu and
  after a relaunch (1 s), and exact replays from each; deterministic
  (sitting x22) the whole 128 MiB is the same at the start and after the
  replay, each time. A load with the guest stopped (as
  `unpark`'s) flushes translated code (1723609ea0). They outlive W
  (Step X.15): each `park` APFS-clones W's HDD (its tags inside), the
  parked discs and `parked.json` into the private L3 store's
  `parked/<W name>/`, which `down` deletes unless kept; after a reboot
  (which clears `/tmp`), a sandbox started on that drive
  (`Sandbox(hdd=<dir>/xbox_hdd.qcow2)`, or `AZURIK_XEMU_HDD`) takes them
  over with `adopt_parked(<dir>)` and `unpark`s them as before.
- **Replays with `stops`:** a level load or a stall ends a replay early
  (`{"at": "load" | "stall" | "entry"}`); the chain clears a popup and
  resumes, and checks the event clock for a lost tick.
- **Measured (sittings x12 and x12b, their evidence):**
  seed 12's sphere-1 item (`power_water_a3`, w2/g0/r1364) collected on the
  booted build by a chain from the W1_W2_Fall arrival (an R7 hop, placed):
  the walk replayed exactly, the pickup after two re-anchors (enemies near
  it push and hit the player in xemu, not in player-tick L3). The w1
  opening climb (beach to w1.Z005) wasn't found: the derive has no way up
  and every seed stalled at the same cost to go.
- **Measured (sitting x15a, Step X.15, its evidence):**
  the owner's w1 opening (along the rocks above the water, then the spout
  into W1_W2_Fall) played from `vanilla-rz-new` and replayed exactly piece
  by piece into w2 (the spout in whole steps, `"scene": true` and
  `"fall": 600` on the segment); r1364's pickup searched in whole steps
  from an update-entry join replayed exactly (817 ticks) by the enemies
  that pushed X.12's strings. Its 0.25 m drift on w1's rocks was xemu's
  frame pacing, not the world: Step X.20 pins one tick a frame
  (`pin_pace`) and X.15's rock strings replay exactly
  (sitting x20's report).
- **Measured (sitting x22, deterministic, its evidence):**
  X.15's w2 walk and r1364 pickup (1,067 whole steps by w2's enemies,
  three hits) matched L3 on every observed field every tick; its w1
  opening segment (475 player ticks, a popup cleared) in body, state and
  HP every tick (the inventory hash differs in player-tick mode, as since
  X.10).
