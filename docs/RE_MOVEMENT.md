# RE notes: player movement

> Ported from Azurik_Modkit's `docs/` (Step 4.11g); its paths, verbs and links point at AzurKit's since Step
> 4.24d. A `scripts/`, `tests/` or `shims/include/` path, a module or a doc that AzurKit lacks (often written
> "Modkit's") names Modkit's tree, where the finding was made; its history is the private archived repository
> (AGENTS.md § Porting from Modkit). Modkit's `azurik.h` is AzurKit's `devkit/re/data/structs.h` and `anchors.toml`,
> its `azurik_vanilla.h` and kernel headers are the ones shimkit writes from the facts (`src/azurkit/core/facts.*.json`,
> the functions' notes in `devkit/re/data/function_notes.toml`), and `python -m devkit AREA VERB` is the developer
> side's (`devkit/README.md`). Its "this repo" and "today" claims are Modkit's at the time: AGENTS.md is AzurKit's
> rule and wins where the two differ.

How the engine moves the player: walking and the shared 3.0, wing
flaps and their ceiling, fuel, armor and HP, air control, the jump,
the roll, swimming, springboards, updrafts and the lip lift, fall
damage, contacts (the move's loop, the classifier, the catch), the
simulation tick rate, gravity and the ControllerState struct. Check here before a Ghidra session; each
finding cites the function or VA it came from so you can re-verify.

Split from the old LEARNINGS notes (History, at the end, has the path)
in REORG_PLAN Step 3.3d (2026-10-10) without rewording, so "above" or
"below" may mean a section that is
now in [`RE_DATA.md`](RE_DATA.md) (data files),
[`RE_XBE.md`](RE_XBE.md) (the XBE itself) or
Modkit's `Finished/LEARNINGS_HISTORY.md`
(superseded findings and retired attempts).

---

## Player movement

### The shared `3.0` run-multiplier (VA 0x001A25BC) is read from 45 sites

The `.rdata` float at VA `0x001A25BC` holds the value `3.0`.  It's
the FMUL factor the flag-0x40 branch of `FUN_00084940` uses to
boost the player's magnitude — the developer cheat-buttons turbo,
never on in retail, not a run or a roll (see "Roll, not run"
below).  **But**: the same constant is read
from 44 other sites across the XBE (audio mixing, collision, AI,
unrelated physics) — touching the shared constant would affect
every reader.

✅ **Learning**: when patching a constant you think is player-
specific, always grep for every xref.  If the constant is shared,
use the C1-style redirect (rewrite the instruction at the call site
to reference a freshly-injected per-game constant) instead of
mutating the shared value.

Reference: `src/azurkit/tools/mods/packs/player_physics.py` (the swim speed's scale; Modkit's `apply_swim_speed`)
(the walk slider used the same redirect until D53, when it moved to
`config.xbr`'s `runSpeed`).

### `CritterData.walkSpeed` and `runSpeed` are live, not dead data (corrected 2026-10-09)

Both `critters_critter_data` values are read [verified: static
disassembly plus Unicorn on the real loader and walk_state against the
real `config.xbr`].

- **The loader.**  `load_critters_config` (`0x49480`) reads
  `config/critters_critter_data` (string reference at 0x49B86) and
  looks up the `walkSpeed` and `runSpeed` keys (0x49D55 / 0x49DAA).  It
  stores garret4's `walkSpeed` (5.0) at CritterData+0x38 and `runSpeed`
  (7.0) at **+0x40**.
- **The reader.**  The input builder (`0x85294`) puts the player
  critter's species in input+0x34, and walk_state reads +0x40 with the
  `FLD` at `0x85F65`.  So **garret4 `runSpeed` is the live walk base**,
  the "hard-coded 7.0" that the old walk slider's rewrite at `0x85F62`
  replaced.
- **Seen in game.**  In xemu `runSpeed` 14.0 walks at 14.000 m/s
  against vanilla's 7.000, and poking +0x40 back to 7.0 gives 7.000
  (session 3, 2026-10-09).  Since owner decision D53 (2026-10-09) the
  walk slider sets `runSpeed` to k × 7.0 and writes no XBE byte (no
  carve, so no AZ-001 exposure).
- **`walkSpeed`** (+0x38) has five known readers [verified static
  2026-10-10: capstone on the vanilla XBE; the fifth 2026-10-11]:
  - walk_state `0x86474` / `0x864AA` (species from input+0x34, loaded
    at `0x86404`): the walk→run animation threshold; 0.1 × it is the
    idle threshold;
  - jump_init `0x89216` (species from input+0x34 at `0x8920A`, then
    `add eax, 0x38`): the take-off animation, 0xF when the horizontal
    speed is above it and 0x10 otherwise;
  - player_swim_tick `0x8B8C5`: it is the **vertical swim speed**
    (§ "Swim speed lives in FUN_0008b700" below);
  - `0x361F7`, in a method of the vtable at `.rdata` 0x1A0510 [inferred:
    AI flock/herd movement; HP research approach A];
  - the ground attack starter `0x88A80`, at `0x88C14` (species from
    `[[entity+0x20]+0x178]`, `edi` = the entity the state machine passes
    in `eax`, then `add eax, 0x38` at `0x88C11`): a flag on its stack
    (`[esp+0xD]`) is set when the length of the vector at
    entity+0x24..+0x2C is above `walkSpeed` (it compares the squares).
    It is `attack_transition_search`'s (0x7EF10) AL, read only at
    0x7EF37: with no last move (PlayerControl+0x134 −1, a fresh start
    from state 0) the search's from-key is −3 when it is set, else −2;
    with a last move (every chain: 0x8D43C skips the chain at −1) the key
    is that move and AL is unread. Vanilla `attacks_transitions` keys one
    row on −3, row 27 (last move `run`, B → `sweep2`); A's row 35 has no
    last move, so the flag picks only a fresh B's sweep: `sweep2`
    running, `sweep1` (row 36) else [verified static, `xbe dis 0x7EF10`;
    measured, Step 2.145's sitting re-run:
    30 chain calls each keyed on its last move; garret4 × 0.5 on a
    full-stick run (4.95 m/s) set it against walkSpeed 3.54 (Step 2.145,
    D422) and swept with `sweep2`, unset against main's 5.0 and swept
    with `sweep1`].

  No complete reader sweep has been done: jump_init's read goes
  through a register that `add eax, 0x38` set, which an operand search
  for `+ 0x38]` misses.  A sweep for that form (`add <reg>, 0x38`, then
  an x87 load or arithmetic through `[<reg>]` within 4 instructions)
  finds only `0x89216` and `0x88C14` [verified 2026-10-11].
  **Corrected 2026-10-10:** this bullet used to
  say `walkSpeed` is only the animation threshold and "not a speed",
  and REORG_PLAN N18 and AZ-137's evidence call it AI-only; the swim
  read was found by the evidence sweep (HP-01).
  The player-model swap writes garret4's `walkSpeed` 5.0 × √s for a
  body of size s other than 1 (Step 2.145, D422, AZ-617), beside the
  size fold's runSpeed × √s, so all five player readers see a speed
  scaled as the run is.

Until 2026-10-09 these notes called both columns dead and +0x40 a
default of 1.0 (the no-effect catalogue's #3).  That was wrong: the
old config slider wrote the table then labelled `attacks_transitions`
(AZ-113), or wrote `walkSpeed`, or a warm HDD cache served a stale
`config.xbr` (AZ-112).

✅ **Learning**: in keyed-table-backed config, a column existing
in the `.xbr` doesn't prove the engine reads it, and a null in-game
result doesn't prove it doesn't.  Find the loader's reference to the
key string, then measure where the value is consumed.

### FUN_00085F50 is the walking state; FUN_00088490 / FUN_00087F80 are climbing

Four functions call into `FUN_00085F50` — the velocity-from-magnitude
computation.  Two are quickly identifiable by their embedded sound-
path strings:

| Function       | Identifying strings                          | Purpose          |
|----------------|----------------------------------------------|------------------|
| FUN_00085F50   | `fx/sound/player/walkl`, `fx/sound/player/walkr` | Walking / running |
| FUN_00087F80   | `fx/sound/player/climb[u/d/l/r]`             | Climbing         |
| FUN_00088490   | `PTR_s_m_grab_001a9c60`                       | The climb with the stick at rest (its only caller `player_climb_tick`, 0x88473): while the ladder is still in front it loops `climb_idle` (anim_change at 0x88733) and places the model so its `m_grab` marker sits on the rung point (0x42E40 at 0x8875B), else it falls (anim 0x12) [verified static, Ghidra serve, 2026-10-15, Step 2.63; the onto- and off-ladder moves are the setter 0x8BDB0's aligned clip changes, `src/azurkit/tools/characters/player_model/climb.c`]. It never ran when the player jumped at a ledge (xemu s6, 2026-10-11). Was "Grabbing ledges" |
| FUN_00084A40   | `PTR_s_m_root_001a9c54`, `m_feet`, `m_grab`, the guard byte 0x1AAB7D | `player_move_offsets_init`: once per boot (the PlayerPhysics constructor's CALL at 0x84E59) it samples `m_root`, `m_feet` and `m_grab` (0xCAB80) at t 0 and at the clip's length for each of the player's 113 clip slots into three BSS arrays of 0x18 bytes a slot (USA 0x38A610, 0x389B78, 0x38B0D0; Europe +0x1FA0), zeros for an empty slot or a marker the body lacks. The ladder latches read them for their sweep height (0x38B678 less 0x38ABB8: `m_grab` over `m_root` at `climb_start`'s start, garret4 2.269 and 1.073) and their targets, as do the top moves (0x87470, 0x87950) and the overhead hang (0x8A200, slot 0x44) [verified static, capstone, and L2: the vanilla code on garret4's clips gives the values xemu 2.75a's control read; Step 2.63b] |
| FUN_0008CCC0   | State-machine dispatch (calls via case 0 / 6) | Per-frame switcher |

✅ **Learning**: embedded sound-path or animation-ref strings are
the fastest way to label a movement-state function.

**Seen in xemu, meaning unproven** (session 4, 2026-10-09): at a 4 mm floor bump in the Training Arena (x ≈ −20.5),
walks at 3.5 m/s show one tick of state 0x3 (slope) with the state
timer reset.  One 7.0 m/s walk on the HP-1 ISO showed it too; the
7.0 m/s run poked in the same boot as the 3.5 m/s runs did not.  No
investigation is planned.

### Vanilla base-speed value + independence math (April 2026)

`CritterData.run_speed` at offset `+0x40` is the player's walk base,
and its vanilla runtime value is **`7.0`**: garret4's
`critters_critter_data` `runSpeed`, filled by the critters loader
(see "`CritterData.walkSpeed` and `runSpeed` are live, not dead
data").  With the developer cheat-buttons turbo on (input flag 0x40,
never in retail), `FUN_00084940` triples the stick magnitude before
walk_state multiplies it by this field (see "Roll, not run").

How it was pinned: an lldb breakpoint at VA `0x00085F65`, the `FLD`
of CritterData+0x40 that follows the load of input+0x34 in
`FUN_00085F50`, read 7.0 at +0x40.

So vanilla walking is `7.0 × raw_stick`.

**Seen in xemu** (agent session s6, 2026-10-11, flat ground in level
f6):

- **Walk speed = `runSpeed` × stick.**  A full stick walks at 7.00009
  m/s; with the stick rewritten in RAM (not a real pad, the dead zone
  bypassed) 0.5 gives 3.50016 m/s and 0.75 gives 5.25012.  The desired
  speed is 7.0 from the first stick tick, and the move code ramps to
  it in 2 ticks below target: 3.26691, 6.53610, then 7.00009.
- **`walkSpeed` (5.0) only picks the animation here.**  Poked to 10.0,
  it turned the animation from 9 to 8 and left the speed unchanged.
  walk_state's animation indices [verified static: 0x86474, 0x864AA]:
  1 idle (no stick and a speed at or below 0.1 × `walkSpeed`), 8 walk
  (at or below `walkSpeed`), 9 run (above it), and 13 / 14 the same
  two with the RT flag (input+0x20 bit 0, the right trigger) and the
  stick pulled back.  Critter+0x200 holds the current animation index
  (the roll's is 0x66).
- **RT with the stick back is a backpedal:** animation 14, full speed
  (7.0 m/s), no turn.  LT, WHITE, L3, and RT with the stick forward,
  change nothing.
- **The move code caps deceleration too.**  A release stops in 3
  ticks, 7.00009 → 3.73227 → 0.46353 → 0, losing about 3.27 m/s per
  tick, as the ramp gains.  An emulated k = 2 roll's tail loses 2.9665
  m/s per tick ("Roll, not run" §5); which cap applies when is not
  measured.

The April-2026 "independence math" that injected a walk base and a
roll multiplier so two sliders could scale one field is archived in
Modkit's `Finished/LEARNINGS_HISTORY.md` §
"Walk/roll independence math".  Neither leg ships: since Step 2.12
the roll slider is a shim at 0x8C745 ("Roll, not run" below), and
since owner decision D53 (2026-10-09) the walk slider sets
`config.xbr` garret4 `runSpeed` to `walk_scale × 7.0` and injects
nothing; pinned by
`tests/test_player_speed.py::test_walk_slider_sets_garret4_run_speed_in_config_xbr_and_no_xbe_byte`
and `tests/test_walk.py`.

⚠️ **Trap**: scale the vanilla value, never inject a literal.  The
pre-April-2026 walk patch wrote the slider value itself, so
`walk_scale=3` dropped the player to `3.0/7.0 ≈ 43%` of vanilla
speed.  A patch that layers on `CritterData.run_speed` must keep
vanilla at scale 1.

### Wing flap = FUN_00089300, NOT FUN_00089480 (April 2026)

The mid-air "wing flap" (Air-power double-jump) is its own
function: ``FUN_00089300``.  Entry conditions:

1. Input-flag bit 0x04 of ``PlayerInputState.flags`` is set
   (the JUMP button was pressed THIS frame, edge-triggered).
2. ``armor.flap_count`` (``[EDX+0x38]``) is non-zero.
3. ``entity.flap_counter`` (``[ESI+0xD8]``) is less than
   ``armor.flap_count``.

When all three hold, the function:
- Calls ``FUN_00083F90(&entity[0x140])`` which WRITES
  ``[ESI+0x140] = 12.0`` (air control) and
  ``[ESI+0x144] = 1.2`` (flap height) when the slot's Flaps
  (level+0x38) is non-zero and its Level (level+0x08) is 1-3,
  else ``9.0`` / ``1.1``.
- Consumes fuel via ``FUN_000842D0(this, 1.0)``.
- Increments ``entity.flap_counter``.
- Computes ``v0 = sqrt(2g · min(max(peak_z + h − z, 0), h))``; the
  gravity `FLD` is at VA 0x893AE.
- Sets the new vz to ``min(v0, vz + 1.5·v0)``; the 1.5 is the shared
  `FMUL [0x001A26C4]` at VA 0x893EB.
- Sets state = 2 (airborne) and plays "fx/sound/player/jump".

**Pre-April-2026 patch target (VA 0x896EA, `FADD [0x001A25C0]`)
was inside FUN_00089480 (airborne per-frame physics), NOT
FUN_00089300.**  That FADD runs only when input flags have BOTH
bit 0x40 AND bit 0x04 (JUMP) set (the 0x40 test is at 0x89664), so
our user-facing "flap_height" slider appeared to do nothing.  Bit
0x40 is the developer cheat-buttons flag (AZ-115): the input builder
sets it only while the cvar `enable cheat buttons` is on (its value
is the dword at record+4 of the cvar record whose pointer is at
0x38CA80; default 0, and `-nocheat` clears it), so it is never set
in retail (see "Roll, not run").

The v2 patch at VA 0x893AE mirrors the initial-jump pattern:
rewrite the gravity FLD to reference an injected
``g × flap_scale²`` (g = the gravity slider's value, 9.8 when
unset; D16, Step 1.19a) so the sqrt yields ``flap_scale × v0``.

### Wing-flap v0 cap — vanilla anti-infinite-altitude design

Vanilla `wing_flap` (FUN_00089300) at VAs 0x89368-0x89393:

```
fVar1 = peak_z + flap_height - current_z
if fVar1 <= 0: fVar1 = 0
fVar2 = min(fVar1, flap_height)
v0 = sqrt(2 × g × fVar2)
```

``peak_z`` is latched to ``z_at_jump + flap_height`` in
`player_jump_init` at VA 0x8915A and is **never refreshed** by
`player_airborne_tick`.  Consequence: **subsequent flaps
cannot exceed `initial_flap_z + flap_height`**.  Below-peak
flaps are a supported recovery mechanic — the 0.5× halving at
`flap_below_peak_scale` is a clean byte-patch of a real
vanilla constant.  At-or-above-peak flaps are **intentional
anti-infinite-altitude design**: once the player has recovered
their altitude budget, further flaps produce zero v0.  A jump
boosted past √2× by `jump_speed_scale` already rises above that
cap ("A boosted jump needs a raised ceiling" below).

**Three separate patch attempts have been abandoned** (rounds
7–10); no above-peak v0 injection currently ships:

- **v1** NOPed `FSUB [EBX+0x5C]` at 0x89381 so `fVar1 = peak+fh`
  (always large).  Landed cleanly but `fVar1 > 6m` tripped the
  halving path at 0x893C0 AND `consume_fuel(100)` at 0x893D4
  — fuel drained to zero within 1-2 flaps.
- **v2** rewrote `FLD ST(1)` → `FLD ST(0)` at 0x8939F so the
  `min(fVar1, fh)` compare became `min(fh, fh)`.  Byte-level
  verification showed the patch landed; in-game testing
  reported no observable effect.  The engine re-derives the
  cap downstream.
- **v3** (round 8) shipped a hand-assembled shim at 0x89409
  (the final `FSTP [ESI+0x2C]`) that enforced
  `max(vanilla_v0, sqrt(2g*fh)*scale)`.  Also ineffective
  in-game — `player_airborne_tick` or subsequent physics
  integration re-clamps vz before it manifests as motion.

Round 10 deleted the `flap_at_peak` pack and made
`apply_flap_at_peak` a no-op.  What works instead:

- Scaling `flap_height_scale` (the gravity FLD inside
  `wing_flap` at 0x893AE) affects EVERY flap's v0 because
  `wing_flap` runs for first + subsequent flaps alike.  But
  when `fVar2 = 0` (the ceiling case), `v0 = scale * 0 = 0`.
- Scaling `flap_below_peak_scale` (the halving FMUL at 0x893DD)
  only fires for flaps taken more than 6 m below the flap ceiling
  (peak_z + h).
- **Round 11: `wing_flap_ceiling_scale`** — scales the peak_z
  latch at the source instead of fighting downstream state.
  See "Wing-flap ceiling — shim at jump_init" below.

### Wing-flap ceiling — shim at jump_init (round 11)

The `peak_z` latch in `player_jump_init` is the **source of
truth** for the wing-flap altitude cap.  It has exactly one
writer: the `FSTP [ESI+0x164]` at VA 0x8915A, fed by the
`FADD [ESI+0x144]` at VA 0x89154 that adds the per-jump
`flap_height` field to `entity.z` (loaded by the `FLD [EDI+0x5C]`
at VA 0x8914C).  Nothing else in the binary writes
`[ESI+0x164]` for the player-shape state struct (verified by
scanning the full `.text` section for FSTP/FST/MOV patterns at
that offset; one incidental hit at VA 0x026615 writes a
different struct's field of the same offset, confirmed via
absence of `[ESI+0x144]` / `[ESI+0x5C]` touches in that
function — and via the Ghidra decompilation showing both uses
in isolation).

**Vanilla math** (from the `wing_flap` decompilation at VA
0x89300):

```c
fVar1 = peak_z + flap_height - current_z;   // clamped >= 0
fVar2 = min(fVar1, flap_height);
v0    = sqrt(2 * g * fVar2);                // g = 9.8 in vanilla
```

With the vanilla `peak_z = entity.z_at_jump + flap_height`:

- `fVar1 = entity.z_at_jump + 2·flap_height − current_z`
- Hard ceiling where `fVar1 = 0`:
  `current_z = entity.z_at_jump + 2·flap_height`

So the vanilla altitude envelope above the ground the player
jumped from is **2·flap_height**, not one — `wing_flap` adds
`flap_height` again on top of `peak_z` inside its own formula.

**Round 11 shim** at VA 0x89154 rewrites the FADD source with
a scaled flap_height.  Ceiling becomes:

```
peak_z_patched = entity.z_at_jump + K · flap_height
fVar1_patched  = (K + 1) · flap_height − (current_z − entity.z_at_jump)
ceiling_patched = entity.z_at_jump + (K + 1) · flap_height
```

- `K = 1` → `2·flap_height` (vanilla)
- `K = 2` → `3·flap_height` (≈1.5× vanilla ceiling headroom)
- `K = 5` → `6·flap_height` (≈3×)
- `K = 10` → `11·flap_height` (≈5.5×)
- `K = 20` (the track's end, a display hint, not a limit: D23) →
  `21·flap_height` (≈10.5×)

i.e. the "multiplier" applies to `peak_z`, and the observable
ceiling grows as `(K+1)/2` relative to vanilla.  Users who want
"double the ceiling" should set `K ≈ 3`, not `K = 2`.

**A boosted jump needs a raised ceiling** (Q228, D93) [verified, L2
2026-10-10; details in skill `azurik-game-reference` §4]:
`jump_speed_scale` k leaves the latch at `z_at_jump + flap_height`,
but the jump's apex is `k²·flap_height` above take-off, past the
`2·flap_height` ceiling once k > √2.  A flap above the ceiling gets
v0 = 0, so the new vz is min(0, vz): it stops a rising player, leaves
a falling one falling, and still spends a flap and its fuel.  Pair
the jump slider with K ≥ k² − 1: the ceiling `(K + 1)·flap_height`
then reaches the apex.  In L2 (`SHIELD_2`, flap_height 1.2 m, k = 1.5,
apex 2.7 m): at K = 1 a flap 2.5 m above take-off gives vz 0; at
K = 1.25 = k² − 1 it gives √(2g·0.2) = 1.98 m/s there, and 0 at the
apex.

Because there's no downstream re-derivation of `peak_z`, this
scaling propagates cleanly into every subsequent `wing_flap`
invocation: a bigger `peak_z` widens `fVar1`, `fVar2 = min(…,
flap_height)` stays positive further above ground, and the
`sqrt(2g·fVar2)` v0 formula produces a real impulse instead of
0 near-vanilla-peak.

Why rounds 7–10 all failed and this one doesn't: the earlier
shims hooked **downstream** of the peak_z computation (at the
min-cap in `wing_flap` itself, or at the final vz FSTP, or at
animation root-motion commit).  Every one of those sites had a
consumer that re-clamped or re-computed the value we'd
written.  Round 11 hooks **upstream** — we change what
"peak" *means*, not what `wing_flap` *does* with it, so every
reader downstream observes the new value with vanilla
semantics unchanged.

**Shim implementation** (15 bytes, hand-assembled via
`shim_builder`): an `FLD` of flap_height (`[ESI+0x144]`), an `FMUL`
by the carved ceiling scale, an `FADDP` that adds the product to the
`entity.z` already on the x87 stack, and a `RET` that resumes at
0x8915A.

Installed at VA 0x89154 (the vanilla FADD site) as a 5-byte
`CALL rel32` + 1-byte NOP.  On shim entry ST(0) = `entity.z`
(loaded by the vanilla FLD at 0x8914C and preserved across the
CALL's return-address push).  After RET the shim returns to
the unchanged `FSTP [ESI+0x164]` at 0x8915A, which writes the
adjusted sum to `peak_z`.

The slider is orthogonal to `flap_height_scale` (per-flap v0)
and `flap_below_peak_scale` (the descent-flap halving) — the three
compose cleanly.

**Design intent check**: this IS a workaround to vanilla's
intentional anti-infinite-altitude clamp.  The game caps
subsequent-flap altitude on purpose, and scaling the ceiling
past 5x or so is clearly outside the designer's intent.  The
slider defaults to 1.0 (vanilla) and is opt-in.

### Wing-flap descent-penalty fuel drain (round 11.7)

A second anti-recovery mechanic lives inside `wing_flap`
itself, independent of `peak_z`.  From the decompilation:

```c
if (6.0 < fVar1) {                 // fell > 6m below peak envelope
    consume_fuel(this, 100.0);     // result ignored
    param_1 = param_1 * 0.5;       // halve v0
}
```

`fVar1` is d = peak_z + h − z, with z the input position
(input+0x5C), so the branch runs on a flap more than 6 m below the
flap ceiling (takeoff + 2h): the input z more than 3.6 m below
takeoff at h 1.2 [verified, capstone over 0x89380–0x893E7: `FCOMP
[0x1A25B8]` at 0x893C0].  A flap after the apex of an ordinary jump
never qualifies; a late flap on a long downhill fall does.

The 100-cost call is what clears the air-power gauge in a
single flap: 100 / Flaps is far more than the 1.0 gauge, so
`consume_fuel` empties it and calls `armor_reset_out_of_fuel`
(0x837A0; see "Fuel consumption" below), which **drops the air
shield**: the slot becomes the no-armor slot (Level 1, Flaps 0), so
later flaps are refused and the next jump is plain.  The flap itself
still lifts, at half v0 [verified xemu s6, 2026-10-11: a natural
drop (d 6.80, the gauge 0.4 → 0.0) and a poked peak_z (d 7.40, 0.8
→ 0.0), each followed by 0x837A0, called at 0x8431E].  Users who
pair a high `wing_flap_ceiling_scale` with deep descent see this as
"first descent flap works, then the wings are gone".  A lower
`flap_descent_fuel_cost_scale` drops the shield only when its drain
still empties the gauge: a build at 0.01 took 0.2 of air shield 3's
gauge for the descent (1.0 → 0.6 with the flap's own 0.2) and kept the
shield [verified xemu p9, 2026-10-13].

Three sites compose the branch:

| VA | Instruction | Role |
|---|---|---|
| 0x893C0 | `FCOMP [0x001A25B8]` | `6.0 < fVar1` test (constant has 19 readers — can't overwrite) |
| 0x893CD | `PUSH 0x42C80000` | pushes 100.0f as the fuel-cost argument |
| 0x893DD | `FMUL [0x001A2510]` | ×0.5 halving (targeted by `flap_below_peak_scale`) |

The `flap_descent_fuel_cost_scale` slider rewrites the 4-byte
PUSH immediate at VA 0x893CE (bytes 1..4 after the 0x68 PUSH
opcode).  Setting to 0.0 pushes 0.0f instead of 100.0f;
`consume_fuel(this, 0.0)` is then a legal no-op that drains
nothing but still returns 1 (success) — so the flap proceeds
and the gauge stays intact.  Pair with
`flap_below_peak_scale = 2.0` if you also want to cancel the
v0 halving that runs in the same branch.

Unlike the `peak_z` latch, the 6.0 threshold constant at VA
0x001A25B8 is shared across 19 unrelated readers in the binary
(movement / physics / input / audio — not all of them obvious
consumers of a height threshold; probably a deduplicated
numeric literal in the original source).  Overwriting the
constant would corrupt all 18 unrelated sites.  The
PUSH-immediate approach is surgical to this one call site.

This patch is CODE-surgical rather than DATA-surgical, which
generalises: if you ever need to scale a numeric argument
passed to a callee, and the literal is a `PUSH imm32` sourced
directly in the caller (not an `FLD [shared_const]`), you can
rewrite the 4-byte immediate in place without any relocation
or shim machinery — see `apply_flap_descent_fuel_cost` for the
2-line apply function.

### Wing-flap ENTRY fuel drain + `consume_fuel` threshold (round 11.11)

The descent-penalty drain at 0x893CE is only the second of
**two** fuel-consuming sites in `wing_flap`.  The first fires
unconditionally on every flap: at 0x8934D `wing_flap` pushes the
cost 1.0f (a `PUSH imm32` whose immediate is at 0x8934E), passes the
armor manager in ECX (`__thiscall`) and calls `consume_fuel` at
0x89354; a zero AL (`TEST AL, AL` then `JZ` at 0x8935B) aborts the
flap.

`flap_entry_fuel_cost_scale` rewrites that 4-byte immediate from
1.0f to `scale * 1.0f`:

| Scale | Behaviour |
|---|---|
| 1.0  | Vanilla: each flap takes 1/Flaps of the gauge (air1 = 1 flap per gauge, air3 = 5 flaps), and the flap that spends the last step drops the air shield (below) |
| 0.1  | Each flap takes a tenth as much; the gauge lasts about 10× as many flaps, until a press past the per-jump cap drops the shield (next paragraph) [inferred from `consume_fuel` 0x842D0–0x8432C] |
| 0.0  | Flaps never drain the gauge, but each jump still allows only Flaps flaps (the counter check at 0x89328), so it is **not** infinite per jump (D17). A press past the cap calls `armor_reset_out_of_fuel` 0x837A0 (the CALL at 0x89331), which drops the shield and empties the gauge [verified xemu s6, 2026-10-11, Q123: 5 flaps kept the gauge at 1.0, and the 6th press in the same jump took it to 0.0 with the no-armor slot; 10 flaps over two jumps, never past the cap, kept the gauge, the slot, Level 3 and Flaps 5] |
| -1.0 | Each flap **adds** 1/Flaps to the gauge (see below); a press past the per-jump cap still drops the shield [inferred from `consume_fuel` 0x842D0–0x8432C] |

**A press past the per-jump cap drops the shield whenever the gauge
outlasts the cap: from a full gauge at a scale at or below
2·Flaps/(2·Flaps+1)** (2/3, 0.8 and 10/11 for air1/2/3), **or at any
negative scale** [verified xemu s6 at 0.0 (the 0.0 row); the bound
inferred from `consume_fuel` 0x842D0–0x8432C, below].  `wing_flap` checks the counter
before it pushes the cost [verified 2026-10-11, capstone over
0x89300–0x8935B]: after the press test at 0x89308 and the Flaps = 0
exit at 0x89326, `CMP [ESI+0xD8], EAX` at 0x89328 compares the
counter with Flaps and `JL 0x89340` goes on to the flap; otherwise
it calls 0x837A0 at 0x89331 and returns 0.  The cost PUSH comes later
(0x8934D), on the `JL` path only, so the scale doesn't change this
path.  In vanilla it is never reached with the shield on [inferred]:
the last allowed flap empties a full gauge and 0x837A0 drops the
shield, leaving Flaps 0 (xemu s6: the 5th flap of air shield 3 did,
and the 6th and 7th presses took no 0x89330 and no 0x837A0).  From a
full gauge the last allowed flap leaves 1 − scale, and `consume_fuel`
empties the gauge when less than half a step (scale/Flaps) is left,
so above 2·Flaps/(2·Flaps+1) that flap still empties the gauge and
drops the shield, as in vanilla (the L2 simulator agrees at Flaps 1,
2 and 5 on each side of the bound [verified 2026-10-11, the stack's
review: `PlayerSim` with `build_physics(flap_entry_fuel_cost_scale=…)`]).
At or below the bound, or at a negative scale, the gauge outlasts the
cap, so the next press past it drops the shield.

`consume_fuel` (FUN_000842D0; `__thiscall`, ECX = armor manager,
float cost on the stack, `RET 4`) [verified 2026-10-10: capstone over
0x842D0–0x8432C, constants read from the XBE]:

- It returns 0 (refuse) when the armor manager has no slot
  (+0x20), when the slot's Flaps (level+0x38) is 0, or when the gauge
  (+0x24) is exactly 0.0.
- Otherwise it subtracts `step = cost / Flaps` from the gauge (a full
  gauge is 1.0; Flaps is 1 / 2 / 5 for air1 / air2 / air3).
- If what's left is under half a step, it sets the gauge to 0 and
  calls `armor_reset_out_of_fuel` (0x837A0).
- It returns 1 on every path past the refusals, including the one
  that empties the gauge.

**0x837A0 drops the air shield** [verified xemu s6, 2026-10-11].  It swaps the equipped slot for the no-armor slot
(Level 1, Flaps 0) and zeroes the gauge; the next jump is plain (v0
4.643 instead of 4.850) and its flap presses are refused silently.
So in vanilla the flap that spends the gauge's last step drops the
shield: with air shield 3 (Flaps 5) the gauge stepped 1.0 → 0.8 → …
→ 0.2, and the 5th flap's `consume_fuel(1.0)` emptied it and called
0x837A0 (the CALL at 0x8431E).  That flap still lifted (AL 1).  In
`wing_flap` three paths reach 0x837A0: that last step, a press past
the per-jump cap (the CALL at 0x89331; with
`flap_entry_fuel_cost_scale` 0 it is the only per-flap path, Q123),
and a descent flap more than 6 m below the ceiling at the vanilla
descent cost ("Wing-flap descent-penalty fuel drain" above).  The
descent flap still drops the shield at entry cost 0, because its
cost is the separate PUSH at 0x893CE [inferred from xemu session s6; no
cost-0 descent run].
The gauge doesn't refill on landing, over 30 s on the ground, or
across a level change; an equip, a pickup and a save platform are
still unmeasured (REORG_PLAN N7, Q124).

So a positive cost empties a full gauge in one call when
`step > 2/3`.  For the descent cost `100 × scale` that is
`scale > Flaps / 150` (above 0.0067 for air1, 0.033 for air3), which
is why `flap_descent_fuel_cost_scale`'s useful values are within
`[-0.05, +0.05]` (0.001 steps; since 2026-10-09 its track runs to the
vanilla 1.0, D42).  A negative cost refunds, because the subtract
flips sign, and never takes the empty-the-gauge branch.

The entry cost (1.0f) only empties the gauge on the flap that uses
its last step, so `flap_entry_fuel_cost_scale` has the much wider
track `[-5.0, +5.0]` step `0.1` (1.0 = vanilla, 0.0 = no drain but
still capped per jump, negative = refund; at or below
2·Flaps/(2·Flaps+1), or negative, a press past the cap drops the
shield, above).  Tracks are display hints;
any finite value is accepted (D23).  The two sliders compose:
entry-cost governs the cheap per-flap drain, descent-cost governs the
punishment for trying to flap more than 6 m below the flap ceiling.

### Player HP comes from settings_foo `initial hp`, not garret4 `hitPoints` (2026-10-09)

**Status:** the read path is verified by static disassembly and by
Unicorn runs on the real code against the real `config.xbr`, and
seen in game [verified, xemu session 3, 2026-10-09].  A build with `starting_hp` 777 and
`health_bar_full_scale` 800 starts a new game with
`[entity+0x20]+0x210/+0x214` = (777, 777), against (200, 200) for
vanilla, and its HUD tube is about 97% of full length and completely
full.  Session 4 saw
`starting_hp` 1 start a new game at (1, 1), alive and controllable,
and `health_bar_full_scale` 50 draw a full-length tube.

- **The chain.**  The settings lookup `0x5E620` reads
  `config/settings_foo` by column (the setting name), row `Value`.
  The new-game inventory reset `0x57B70` fills the `hlth` slot
  (inv+0x84 tag, +0x88 current, +0x8C max) with round(`initial hp`)
  (inline FISTP, round to nearest even under CW 0x023F).  The game
  start/continue setup `0x52F50` sets current to it again on both
  paths (`0x532A7`).  The player spawn in `0x53750` copies
  inv+0x88/+0x8C into the spawn params (+0x30/+0x34), and critter
  init `0x409C0` writes **critter+0x210 (current HP) and +0x214
  (max HP)**, with critter = `[entity+0x20]`.  A walk-through level
  exit copies them back through `0x54327` (in `0x542E0`) only, and
  the next spawn copies the slot into its params (`0x53F05`–`0x53F1E`),
  so HP and max carry over unchanged, 321/456 (above `max hp`)
  included [verified xemu s6, 2026-10-11, three exits].  `0x52AAE`
  (in `0x52A50`, whose only direct caller is `0x5620D`) didn't run in
  any of them; which event takes it is open.  Mid-level the slot is
  stale: it read 200/400 while the critter had 185/400, until the
  exit synced it [xemu s6].
- **garret4 `hitPoints` doesn't reach the player.**  The critters
  loader reads it from `critters_damage` (`0x4A4B7`) and truncates it
  into species+0x14, whose only readers are `0x409EE`/`0x40A0A` in
  critter init: a fallback for a spawn that passes a negative HP.
  The player's spawn passes the `hlth` slot, so until 2026-10-09 the
  `player_max_hp` slider (which wrote this cell) did nothing for the
  player.  The `cheats.cpp` spawn `0x13FE0` passes −1 and does use it.
- **Level critters do use `hitPoints`.**  A critterGenerator spawns
  through `0x6F960`, which stores −1 at params+0x30 and +0x34
  (`0x6F9A3`–`0x6F9B6`) and calls the critter builder `0x45C10` at
  `0x6FB64`; so critter init gives each generated critter its
  species' `critters_damage` `hitPoints` [verified static 2026-10-10:
  capstone; `0x6F960` sits in the critterGenerator code beside
  `0x6F570`, inferred; not seen in game].  Every placed pickup and
  enemy is a critterGenerator (§ "Level node graph" in
  [`XBR_FORMAT.md`](XBR_FORMAT.md)).  `0x45C10` has 11 direct callers
  (`python -m devkit re xbe calls --to 0x45C10`); the player
  spawn (`0x53F2C`) and the generator (`0x6FB64`) are traced, the
  other nine aren't.
- **`max hp`** (vanilla 400) is read only by the HUD (`0x1A570`,
  `0x1AD60`): the bar's length is max HP / `max hp` and its fill
  current HP / `max hp`, each clamped to [0, 1], so vanilla's 200/200
  shows a half-length bar, full (xemu session 3, 2026-10-09).  It is
  not a cap: 50 with 200/200 (a ratio of 4.0) draws a full-length tube
  that doesn't overflow (xemu session 4).  The HUD looks it up
  through the record `0x1AAA48` (a pointer to the name `max hp`) and
  caches it as the f64 at **`0x1AAA50`**, with its filled flag at
  `0x1AAA4C` [verified xemu s6: 400.0 and flag 1, unchanged 40 ticks
  later]; session 4's "cache `0x1AAA48` reads 0 at the first player
  tick" read the record, not the cache.  The bar is recomputed only
  when the critter's max HP rises above the HUD's last value
  [verified static, 0x1A596–0x1A5A1].  With the cache set to 0.0 the
  HUD drew a full-length, completely red tube, with no divide fault,
  and with −400.0 no tube; the game ran on [xemu s6, a RAM stand-in;
  builds of `health_bar_full_scale` 0 and −400 did the same, xemu p9].
- **Edges** (Unicorn): 350.6 → 351; 0 → 0 HP; −5 → slot −5, then the
  spawn falls back to garret4 `hitPoints`; |v| ≥ 2^31 → INT_MIN (x87
  integer indefinite), then the same fallback.  The pack refuses a
  value int32 can't hold (D45).  The conversion rounds half to even,
  so −0.5 … 0.5 gives 0 HP and anything below −0.5 the fallback
  [inferred from the rounding mode; Unicorn ran 0.4 and −5].
- **Seen in game, as builds:** 777 (session 3), 1 (session 4), 0 and
  −5 (p9, 2026-10-13: 0 died at once and after every continue, −5
  played on at 200/400).
  The agent session s6 (2026-10-11, vanilla code, HP poked in RAM) saw:
  - **Death needs no hit.**  The state machine's per-tick check
    (`0x8CE77`–`0x8CF35`) picks a death animation and sets state 7 on
    any tick with HP ≤ 0, unless the state is already 7 or 8 [verified
    static].  HP poked to 0 gave state 7 on the next tick, with no
    `apply_damage` call; HP 1 and one hit died two ticks after the hit,
    and a "Press the A button to continue" dialog followed (seen on
    screen, not retained).  So a Starting HP of −0.5 … 0.5 gives 0 HP
    and death on the first tick [xemu s6 by an HP poke; a build at 0
    died on its third tick, xemu p9].  `apply_damage` (`0x44640`, stdcall(critter, new HP,
    flag)) clamps to [0, max] and, on a > 0 → ≤ 0 transition, also
    calls `0x61360` and `0x43FA0`, which are not traced.
  - **A continue and a menu load reset current HP.**  Both run
    `game_start_setup` `0x52F50` (the CALL at `0x55C9E` for the
    continue, `0x56672` for a save loaded from the menu), whose save load
    (`0x58BD0`) restores the slot, then `0x532A7` writes round(`initial
    hp`), 200, and critter init writes it into the new player critter.
    The first player row after a menu load reads 200/400 in every
    capture of the modded-build path; for the continue the 200 was seen
    live, not captured.  So a save's current HP never survives a menu
    load [verified xemu s6], nor a continue, and a Starting HP that
    rounds to 0 dies at once after every continue [verified xemu p9: a
    build at 0 died again 0.24 s after Continue].  The pack accepts it and doesn't warn
    (D23; Q253's default).
  - **Damage is a fixed 25 per `blaze` hit**, whatever the current HP
    (1 to 777, poked) or max (14 hits over 9 captures).  The player's
    hit handler `0x8D600` (virtual; ECX = entity) gets the amount from
    `0x83FE0` (armor_mgr, damage type), applies knockback (`0x30BD0`), writes
    state **0x102**, the air attack-move state (§ "Roll, not run"),
    for 13 ticks, then 2 for 6, and calls `apply_damage(critter, HP −
    amount, 0)` at `0x8D6AF` [verified static + xemu s6].
  - **Current above max** holds until the next hit clamps it: HP
    poked to 200/150 stayed 200/150 until a hit's 175 was clamped to
    150.  Critter init copies max with no clamp, so a continue with
    max below Starting HP spawns at 200/150 [inferred].

  **Not seen yet:** what triggers `0x52AAE`. (Builds with
  `starting_hp` 0 and −5 and `health_bar_full_scale` 0 and −400 were
  seen in sitting p9, above.)
- **Why xemu session 2 (§5.5) saw nothing:** it edited garret4
  `hitPoints` (see above) and poked 0x453528, which is inv+0x88, a
  copy the HUD doesn't read: session 3 found the `hlth` tag at
  0x453524 (inv = 0x4534A0) [xemu s3 §3.1].  That address holds only
  while the entity sits at 0x481C60; in session 4's boots with the
  entity at 0x481C90 it held other data, so find the slot through the
  inventory, not by address [xemu s4 §3].
- **The rest of the HP path** (labels as in the HP research's
  approaches A and B):
  - HP operations [verified static]: the pickup handler near
    `0x435E7` (an upgrade adds n to max and to current; a heal sets
    current to clamp(current + n, 0, max)); `0x43659` sets current to
    max; `apply_damage` `0x44640` sets current to clamp(v, 0, max).
  - The inventory [verified static + Unicorn]: 12 slots of 12 bytes
    (tag, value, cap) at inv+0x18, written by `0x58020` (`RET 8`, 12
    call sites, re-checked 2026-10-10); `hlth` is slot 9.  `0x57B70`
    also reads settings_foo `initial fuel` and `initial fuel cap`, and
    `0x52F50` sets the value of the four element-fuel slots
    (inv+0x1C + 12i, i = 0..3) to round(`initial fuel`) after its HP
    reset, on both paths (`0x532BD`–`0x53360`) [verified static
    2026-10-10, capstone].
  - `0x57B70` has 7 direct callers: `0x52FD0` and `0x530C7` (in
    `0x52F50`), `0x58BDB` (the save-load fallback, approach B), and
    `0x52133`, `0x535B1`, `0x1C6A9` and `0x57B62`, which are
    unexplained (`python -m devkit re xbe calls --to 0x57B70`).
    The title's save list runs it when it previews a save, so a hit
    doesn't mean a new game [verified xemu s5, 2026-10-11; the caller
    is not traced] (AZ-254).
  - The player's species: the spawn looks it up (`0x45E30`) by the
    name in the global `0x1BCDCC`, which `0x58E80` sets to `garret4`;
    `0x5946F` overwrites it right after `0x59449` pushes the string
    `-player` [verified static 2026-10-10: the four instructions that
    name `0x1BCDCC`, `python -m devkit re xbe insns --operand 0x1bcdcc`; that `-player` is a command-line switch is
    inferred].
  - Leads, no step: `initial fuel` / `initial fuel cap` are a possible
    config-only starting-fuel knob, and the `-player` override bears on
    `randomize-full --player-character` [inferred].
- `lev 2..4 hp` / `lev 2..4 obs` have no string in the XBE: unused.
- **Now:** `player_max_hp` writes `initial hp` ("Starting HP") and
  `max hp` ("Health bar full scale"), owner decisions D44/D45.  Like
  any same-size `config.xbr` edit it needs `filelist.txt` rewritten
  (every build does since 2026-10-09; "filelist.txt" below), or a warm
  HDD cache keeps the old file (AZ-112).

### Armor config loader — engine reads the 0x3000 table, not old TOC row 1 (round 11.13)

`load_armor_properties_config` at VA 0x3C700 populates the
per-armor-slot struct array at `DAT_0038C4D4` at boot.  It
loads the asset by string name `config/armor_properties`
(string at 0x19FEC8), then reads the rows `Name`, `Type`,
`Level`, `Strong vs`, `Weak vs`, `Strong protection`,
`Normal protection`, `Flaps`, `Features`, etc. of each armor
column via `config_cell_value`.

The two tables the old notes confused, as the engine and
`azurkit.core.xbr.nodes` read them [verified 2026-10-10:
`parse_toc` and `load_all_tables` over the vanilla `config.xbr`]:

| Payload offset | TOC entry (offset) | Table | Rows × columns | Engine use |
|---|---|---|---|---|
| 0x3000 | 1 (0x2000) | `armor_properties` | 15 × 19: rows Name, Type, Level, Strong vs, Weak vs, …, Cost, Hits, Time, Flaps, Features; columns `no_armor_1`, `earth_armor_1`, …, `air_shield_1..3`, `electro_shield_3` | Loaded as `config/armor_properties` |
| 0x5000 | 2 (0x4000) | `attacks_anims` | 16 × 24: rows name, Anim, Damage multiplier, Fuel multiplier, Rate, …, Sound 4 | The attack animations (`roll forward` is entry 20, "Roll, not run" below) |

Until 2026-10-09 the repo's labels were shifted by one table
(AZ-113): 0x3000 was called `armor_properties_real` and 0x5000 a dead
`armor_properties_unused`, so a "shared name" looked like the reason
edits went missing.  The labels now come from config.xbr's own
`config/<name>` strings, and the TOC is read as the engine reads it
(AZ-124).  The Game Data editor and the `air_shield_flaps` pack write
`armor_properties`, the table on the engine's read path.

Flaps conversion: `config_cell_value` reads the 8-byte double
at cell+8, `FUN_000F5A40` (FPU FISTP) converts to int64, truncating
toward zero (2.7 gives 2, -2.7 gives -2), and the low 32 bits land at
`puVar1[0xE]` (struct offset 0x38), so a value int32 can't hold wraps
(3e9 gave -1294967296) [L2, whole-stack review, 2026-10-10];
`air_shield_flaps` refuses one (D73).  The wing-flap runtime read at
VA 0x89321 (`MOV EAX, [EDX+0x38]`) picks up whatever we wrote
[verified xemu sight224b, 2026-10-15: a build with `air_shield_1` 3
and `air_shield_2` 4 flapped 3 and 4 times per jump against vanilla's
1 and 2, each flap taking 1/Flaps of the gauge and the last dropping
the shield; p9 saw `air_shield_3` 7 give 7].

Users can verify their edits round-trip: `azurkit open built.iso`
checks every file of the build against its manifest and gives its mods
file back, and a developer reads the cells from the build's own
`config.xbr` (`azurkit files built.iso --extract gamedata/config.xbr
--out config.xbr`, then `python -m devkit xbr diff` against the vanilla
one).

### Air-control speed has TWO dominant writer sites — FUN_00083F90 (April 2026)

``entity[+0x140]`` is the airborne horizontal-control scalar
consumed every frame by ``FUN_00089480``'s horizontal physics.
Static jump-entry code (FUN_00089060 and 4 sibling paths)
writes it with `MOV [reg+0x140], 0x41100000` = 9.0.

But during normal gameplay (player has air power, or triggers
a wing flap), the DOMINANT writer is ``FUN_00083F90`` — a
re-initialiser that runs once per jump and once per flap (its
only direct callers are the main jump and the wing flap; it is
not a per-frame tick).  It writes 12.0 when the slot's Flaps
(level+0x38) is non-zero and its Level (level+0x08) is 1-3, and 9.0
otherwise: two `MOV DWORD [ECX], imm32` stores at 0x83FAA (12.0, the
immediate at 0x83FAC) and 0x83FCC (9.0, the immediate at 0x83FCE).

Pre-April-2026 the `air_control_scale` slider only patched the
5 static sites — users with air power equipped saw no effect
because FUN_00083F90 overwrote ``entity[+0x140]`` on every jump
and flap.  Since the April-2026 fix the slider writes **7 sites**:
the 5 static imm32s (0x84ED3, 0x856D4, 0x890EA, 0x89126, 0x8D322)
and the two in FUN_00083F90 (0x83FAC, 0x83FCE), each as its own
vanilla value × scale (12.0 → 12 × scale, 9.0 → 9 × scale), so the
slider is observable regardless of which code path set the field
(`AIR_CONTROL` in `src/azurkit/tools/mods/packs/player_physics.py`).

### Flap count lives in armor_properties[level][0xE]

The number of wing flaps per jump is loaded from
``config/armor_properties.tabl``'s ``"Flaps"`` column at boot
into offset ``0xE * 4 = 0x38`` of the per-armor-slot struct
at ``DAT_0038C4D4``.  The runtime slot is indexed by the
active armor type.  ``FUN_00089300`` reads it fresh at VA
0x89321 (``MOV EAX, [EDX+0x38]``), compares against
``entity.flap_counter`` (``[ESI+0xD8]``), and enforces the
per-jump budget.

**Key insight for modding:** because the read is fresh at
each flap attempt (not cached in the entity), the 5-byte
`MOV EAX, [EDX+0x38] ; TEST EAX, EAX` can be hooked with a
trampoline + dispatch shim that walks the level-struct chain
(``level_struct + 0x08`` = the slot's Level) and substitutes a
user-chosen value.  That's how the (now-deleted)
``wing_flap_count`` pack worked; the shipping replacement is
the `air_shield_flaps` XBR pack.

⚠️ An earlier draft of this section said the shim dispatches on
``DAT_001A7AE4`` "(the current air-power level, 1/2/3/4)".  That
is wrong: `DAT_001A7AE4` is the **active XInput controller index**
(0-3, or 4 for "no controller") — see `AZURIK_ACTIVE_PLAYER_INDEX_VA`
in `shims/include/azurik.h`, which calls the mislabelling out
explicitly.

### Fuel consumption is a single short function (FUN_000842D0)

``FUN_000842D0(__thiscall, float cost)`` (`consume_fuel`)
decrements the gauge ``armor_mgr+0x24``: the store at VA 0x84300
writes ``gauge − cost / Flaps``, where Flaps is the slot's
``level+0x38`` (1 / 2 / 5 for air1 / air2 / air3) and a full gauge
is 1.0.  It returns 0 ("refused") only when there is no slot, Flaps
is 0 or the gauge is exactly 0.0; when less than half a step is left
it empties the gauge and calls `armor_reset_out_of_fuel` (0x837A0),
which drops the air shield (xemu s6), and it still returns 1.  Full
rules under "Wing-flap ENTRY fuel drain" above.

Its only direct callers are `wing_flap`'s two calls, 0x89354 (cost
1.0) and 0x893D4 (cost 100.0) [verified 2026-10-10: a linear sweep of
`.text` for `CALL 0x842D0`; indirect calls weren't excluded].  The
sustained drain of timed armors is separate, in
`player_armor_state_tick` (0x83D80).  The deleted `infinite_fuel` pack
forced this function to return 1 without consuming
(Modkit's `Finished/LEARNINGS_HISTORY.md` §
"Retired physics sliders").

### Air fluttering: a mid-air recast gives the flaps back (2026-10-24, Step R2.18)

The owner's name for it is "air fluttering" (D630). A flap spends the
armor's flaps: at air 1 the gauge goes 1.0 -> 0 and the armor's
[level, flaps] goes [1, 1] -> [1, 0]. LT+Y in mid-air casts the armor
again: [1, 1], the gauge back at 1.0, for 2 air fuel. The next flap
then works as one from the ground. So a flight's flaps are limited by
the air fuel, not by the armor's Flaps (about 25 casts on a full gauge
[inferred: 50 / 2]). The witness is the f2 life fragment's last flight:
10 flaps (1 + 9 casts), the air fuel 50 -> 32, with no refill. His
flights reached 19 flaps in f4, 14 in f2, 12 in w1, 10 in w3, and 9
and 8 in e6. The air fuel also comes back 2 at a time, at intervals,
with no cast [verified xemu, the owner's real input: the X.67 demo's
per-tick trace, read in Step R2.18's intake]. The cast
path behind the recast is not traced here.

The randomizer's tricks.toml makes it the `flutter` family. A flutter
skip's kit is the armor level held, so D183's air-by-flaps rule (a
skip's air level from its most flaps in one flight) does not bound it.
The reach engine's per-flight flap budget assumes the armor's count,
and flutter breaks that assumption (left for v2, D609).

### Roll, not run — the roll is BLACK's attack move `roll forward` (Step 2.12, 2026-10-09)

The slider that shipped as `run_speed_scale` was renamed
`roll_speed_scale` in April 2026 because Azurik has **no run**:
walking is `CritterData.run_speed × stick` (the field name is an
internal misnomer).  That part holds.  The rest of this section's old
text did not: WHITE/BACK is not the roll, and the 3.0 at
`0x001A25BC` is not a roll boost.  Corrected facts, from the
2026-10-09 roll research:

1. **The roll is an attack move** [verified static, the roll research].
   BLACK (ControllerState+0x28) with LT released sets input flag
   `0x20` (input builder `0x84F90` `player_input_build`, 0x85195–0x851CB;
   this list's function names are D94's, in Ghidra since 2026-10-11).  The ground
   attack starter `0x88A80` (`player_ground_attack_start` in Ghidra and
   the snapshot since D94, 2026-10-11; the registry's
   `player_ground_land_tick` is a misnomer kept until AzurKit 4.2/4.3,
   D68) maps it to button 4, and the transition search
   `0x7EF10` (`attack_transition_search`) picks the only button-3 row, which leads to config.xbr
   attacks entry **20, `roll forward`** (Anim `roll_forward`, Rate 1.5,
   Move start/end1/end2 0.1/0.9/1.0; the table is `attacks_anims`,
   labelled `armor_properties_unused` until AZ-113, see the
   section-name note below).
   `0x7F1F0` (`attack_anim_record_copy`) sets entity+0x134 = 20 and copies the record to
   entity+0xDC; the entry `0x88990` (`player_attack_enter`) sets state 0x100 (0x102 in the
   air), the animation layer's rate to Rate, and runs the first tick.  The swing's yaw
   (entity+0x138: the stick heading, or the bearing of a target within 60° of it and 3 m,
   less the Aim angle; 0x7F1F0) is loaded at 0x88A3A (`mov eax, [edi+0x138]`, Europe
   0x889EA), made a quaternion (`quat_from_euler` 0x4FF10 at 0x88A5E) and handed to that
   first tick (`player_attack_root_motion` 0x8C630 at 0x88A6A), whose `0x42E40` at 0x8C7AF
   turns the body by it; later ticks keep the body's own orientation (+0xD0) [verified
   static, Step 2.194b; X49
   takes the load; seen in xemu, sitting 2.194b: a yaw X49 turned by +30.03° turned
   the body on the entry tick and held for the swing].
   Each later ground tick runs `0x8C7D0` (`player_ground_attack_tick`)
   → `0x8C630` (`player_attack_root_motion`).
2. **The distance is root motion** [verified, Unicorn L2].  `0x8C630`
   computes `v = R(heading) · (m_feet(t + Rate·dt) − m_feet(t)) ·
   [0x1A2650]` (30.0 = 1/dt; `fps_unlock` makes it 60.0) and hands `v`
   (EDX) to `gravity_integrate_raw` 0x85700 with the `CALL` at
   **0x8C745**, which passes it on to the move code 0x47380.
   `anim_apply_translation` 0x42E40 runs afterwards (0x8C7AF) and only
   places the model; `player_walk_state` is not on this path.
3. **The `FMUL [0x1A25BC]` at 0x849E4 is a developer cheat**
   [verified, the roll research].  Input flag `0x40` is built only while
   the cvar `enable cheat buttons` is non-zero (its value is
   `[[0x38CA80]+4]`; registered at 0xF63E0 with default 0; `-nocheat`
   clears it; AZ-115, and `RE_XBE.md` § "CVar layout"); it then means R3
   held or a WHITE press.  Even with the cvar on, the FMUL scales the
   stick magnitude (input+0x124), which the roll never reads.  So
   every earlier roll slider (v1/v4 at 0x849E4, v2's forced flag 0x40,
   v3's slope-slide constant 0x1AAB68, the `root_motion_roll` shim at
   0x866D9, which wraps walk_state behind the same flag) landed bytes
   with no effect.
4. **The fix** (D29, Step 2.12): a 36-byte x87 shim replaces the
   `CALL 0x85700` at 0x8C745: if entity+0x134 == 20 it multiplies the
   desired velocity's x and y by k (the hop in z stays vanilla), then
   tail-jumps to 0x85700, whose `RET 4` returns to 0x8C74A.  General
   registers are untouched; the x87 stack is empty at the hook.
   [verified, Unicorn L2, 2026-10-09:
   `tests/test_roll.py::Roll::test_roll_slider_scales_roll_distance`
   runs the real entry and ticks on a fake root track, heading 30°
   off +y: ×k displacement along x and y (k = 2, 0, −1) in the same
   21 ticks, the game's count (Step 2.18b, AZ-270: L2 reads the
   active layer's flags and clip at anim+0x48/+0x44 + 0x40·n and has
   the measured roll clip, 1.1666666 s, xemu s6 §7; the spike's 1.2 s
   clip gave 22); basic1 and the vertical motion unchanged.  Under
   `fps_unlock` the count is unmeasured: Step 2.12's 44 came from the
   1.2 s clip, and L2 hasn't run it since Step 2.10, as `fps_unlock`
   changes the L2 blind spot 0x47380.]  The roll never runs FUN_00084940, so the old 0x849E4
   rewrite cannot reach it [verified static, the roll research: flag 0x40
   is built only while the cheat cvar is on, and the roll never reads
   input+0x124].
5. **Seen in xemu.**  Session 1 poked the
   shim into vanilla's RAM (level 1, 30 fps, flat ground): the speed
   is ×k from the roll's 5th tick, and because the move code caps
   ground acceleration at about 3.27 m/s per tick, k = 2 rolls ×1.838
   from standing.
   Session 2 booted a **built** k = 2 ISO (`roll_speed_scale` 2.0,
   ISO A): on flat ground it rolled 6.2259 m against 3.3866 m at
   k = 1 (equal to vanilla), ×1.838, in 21 ticks each, bit-identical
   to session 1 [verified].  From the level-1 start the same build rolled down a
   slope, 5.3666 m against vanilla's 3.3867 m (×1.585), and ended
   airborne: one run, confounded by the terrain [xemu s2 §3].
   **The ratio depends on the entry speed:** agent session s6
   (2026-10-11, flat ground in level f6) emulated k = 2 with a
   breakpoint at 0x85700 (D29's semantics, not the built shim): ×1.835
   from standing (Σ v·dt), close to the ×1.838 above, but **×1.957
   from a 7 m/s run**; the vanilla roll lasted 21 ticks and covered
   3.375 m from standing by session 1's method [verified].
   So ×1.838 holds from standing only.  The cap also limits
   deceleration: the emulated k = 2 roll's tail lost 2.9665 m/s per
   tick (the walk text in "Vanilla base-speed value" above).
   **In the air** BLACK enters state 0x102, and statically only that
   entry tick goes through 0x8C630 [verified static].  In game
   (session 1, k = 2 poked, a standing jump) the state was 0x102 with
   +0x134 = 20 and no horizontal speed, then 0x100 for the last 3
   ticks after landing; the shim ran 4 times (the entry tick and those
   3), so it scaled only the post-landing tail, 0.14 → 0.28 m/s
   [verified].
   **Not seen yet:** 60 fps, walls, a controlled slope run, and an air
   roll with horizontal speed.
6. **`Rate` sets the roll's speed, not its distance** [verified,
   Unicorn L2 on a fake root track, roll research Exp C].  The entry
   `0x88990` makes `attacks_anims` `Rate` (1.5 for `roll forward`) the
   animation layer's rate, and 0x8C630's root-motion window is
   `Rate · dt`, so Rate 3.0 rolls the same distance in 11 ticks instead
   of 21 (L2 with the measured clip, Step 2.18b, 2026-10-11; 22 on the
   spike's 1.2 s clip).  A Rate ≤ 0 never reaches Move end1/end2, so state 0x100
   may never end, a soft-lock [inferred, unmeasured].  The Entity
   Editor, `xbr edit` and config mods can all write the cell, with no
   clamp (D23).  Other attacks whose distance is root motion should
   behave the same [inferred].  The entry reads the column's `Rate`
   once, at 0x889BB, and 0x8C630 reads no critter+0x188, so a body drawn
   at a Model size lunges its × 1 distance while its hit boxes grow
   (0x43B4C–0x43B8F) [verified static, Step 2.123's attack read].
7. **The sampler, and a model whose roll doesn't move** (Step 2.21b,
   X4).  The `m_feet` sample is `0xCACD0` (`anim_root_motion_delta` in
   the registry): EDI = the clip, ESI = `float out[3]`, and the anim
   object, the node name, t0 and t1 on the stack (RET 0x10; EAX = out);
   it samples the node's translation at each time with `0xCAB80` and
   writes the difference.  Its one caller is the `CALL` at **0x8C6AE**
   in `0x8C630`, whose own first argument, the entity, is then at
   [ESP + 0x1B4] [verified 2026-10-12: capstone, and a serve's
   decompile of 0x8C630 and 0xCACD0 with their xrefs].  garret4's
   `roll_forward` moves `m_feet` 4.0655 m forward (component 1 only; 8
   keys), 3.5326 m of it inside the roll's 0.1–1.0 window; no other
   body's roll clip moves it (`moves_root`: none of the 101 species with
   clips), which is why a swapped model's roll ended without moving
   (sitting swapb: 0.003–0.005 m).  The player-model swap's X4 shim
   replaces that `CALL`: during `roll forward` it returns garret4's
   `m_feet` motion over the same fraction of its clip (the keys
   evaluated as `0xD8300` does, `docs/RE_DATA.md` § "Character
   bodies"), so the roll covers garret4's distance in the model's own
   roll time (flicken's run: 14 ticks).  It composes with
   `roll_speed_scale` at 0x8C745 [verified, Unicorn L2, 2026-10-12:
   `tests/test_player_character.py::test_a_model_whose_roll_clip_has_no_root_motion_rolls_garret4s_roll`,
   each tick equal to the game's own sampler on garret4's clip within
   1e-6 m].  In game the seven swapped bodies rolled 2.75–3.09 m
   against garret4's 3.05–3.07 m, and flicken's 14-tick roll came up
   a little short at 2.75–2.98 m [verified xemu, 2026-10-12:
   sittings modelswap and modelswap2]: in fewer ticks the desired speed peaks
   higher (about 11 m/s for flicken against garret4's 7.3), and the
   ground acceleration cap of about 3.27 m/s per tick cuts it
   [inferred].
8. **An attack takes no stick, so the player stops for every swing**
   (Steps 2.132 and 2.137, X33; D334, D351).  In state 0x100 the input
   builder still runs every tick (0x8C2A0 → 0x854B4: input+0x124 the
   stick's magnitude, +0x128/+0x12C its world direction, +0x7C the
   walk's rate-limited heading, 0x84710), but `walk_state` doesn't, and
   0x8C630's velocity is the clip's root motion alone, facing the
   critter's own orientation (+0xD0, which 0x852B6 re-copies each tick)
   [verified static].  0x8C630's free `CALL 0x307E0`
   (`move_query_clear`, EAX = the move query's struct) at **0x8C728**
   (Europe 0x8C6D8) comes after that velocity is at [ESP+0x20] and before
   the `CALL 0x85700` at 0x8C745; X33 adds runSpeed × the stick there and
   copies +0x7C over +0xD0 for the columns a build flags [verified,
   Unicorn L2:
   `tests/test_player_character.py::test_a_flagged_attack_column_carries_the_stick_and_turns_the_body`;
   in game: booblord's spins move 0.2333 m a tick (7.0 m/s) with the
   stick, facing where she moves, and stop within 3 ticks of a release,
   USA and Europe].
   0x8C7D0's other branch (0x8C801–0x8C835, taken when PlayerControl
   +0x16C & 8 is clear) is not the air (AZ-625, Step 2.140; earlier
   notes here and in X33's source called it so): only
   `player_attack_enter` 0x88990 sets that bit (0x88A50), and 0x8BDB6
   (the aligned-move setter), the hard landing (0x8B150) and the hit
   handler (0x8D690) clear it, so the branch, which writes v = 0 at
   0x8C81D–0x8C82D and calls 0x85700 at 0x8C835, ticks an aligned
   move's glide (hoists, ladder tops, the hard landing).  An air attack
   is state 0x102, ticked by `player_airborne_tick` 0x89480 (the state
   machine's 0x8D082 → 0x8D353 → 0x8D39A, which skips `wing_flap` and
   0x88E70 for it at 0x8D375) [verified static: Step 2.140's read].
9. **Presses are latched edges, so a held button was one press; an
   attack refused the jump; an air attack played on frozen after its
   landing** (Step 2.140; D377, D380, D381, D383) [verified static:
   Step 2.140's read, R1–R5].  `button_pressed_once` 0xA30D0 (EDX the pad, ECX the
   button: 0 A, 1 B, 3 the jump, 4 BLACK, ControllerState +0x18 + 4 ×
   ECX) is true for an analog value above 0 with its latch (+0x48 + ECX)
   clear, which it sets; the poll clears the latch on release.  State
   0x100 (0x8D3D5, skipped while input+0x30 is set) stamps A, B and
   BLACK's fresh presses with the clock ([[PC+0xC]+0x10], f64) into
   PC+0xA0, +0xA8 and +0xB0 (ECX 0, 1 and 4: +0xB0 is BLACK's, not the
   jump's), and at Move end1's fraction its chain `player_ground_attack_start(0)`
   0x88A80 takes a stamp under 0.3 s old (0x1A28C0) or an input flag
   (+0x20 & 8/0x10/0x20), writing it −1.0 (0x88BC7) and setting the
   latch (0x88BFB).  The state never calls `player_jump_init` 0x89060
   (states 0, 1, 3, 4, 5 and 0x101 do), so a jump waits for the swing's
   end.  In the air (state 2) `player_air_attack_start` 0x88E70 (EAX PC,
   [esp+4] the input, RET 4; its one caller 0x8D38A) takes the same
   stamps, consumes one (0x88F4D) and its latch (0x88F87), picks the air
   row (rows 12–13, `jump attack`, column 13) and enters it in 0x102;
   that entry's one 0x8C630 tick writes the move's result over
   PC+0x24..+0x2C from root motion alone (0x8C767–0x8C783), so a clip
   with no `m_feet` track stops the jump dead.  Later 0x102 ticks are
   0x89480's, which steers by the stick (9.0 × it, 0x894FB–0x89539) and,
   with +0x16C & 8 set, faces by the walk's +0x7C (0x89952 → 0x42E40);
   the 0x43170 delta path (0x89917–0x8994B) is the hit reaction's 0x102
   (the bit clear).  On landing `player_land_classify` 0x85920 (ESI PC,
   three stack args, RET 0xC; called at 0x89982) writes the state's 0x100
   bit alone (0x85A94: 0x102 → 0x100), so the air clip plays on in the
   attack state until its Move end2, or, falling 7.54 m/s or more
   (0x38B0C4 = sqrt(2 × 9.8 × 2.9), set at boot) after 0.5 s airborne,
   plays the 13-tick hard landing 0x8B100.  X33's entries (Step 2.140,
   `player_model/attack_carry.c`, X33's mask only): at 0x8D3E5/0x8D406 a
   held A or B in a carried root-motion swing is stamped 0.25 s back (the
   latch kept, AL the game's 0; Step 2.145, AZ-633), so the chain's 0.3 s
   window (0x88A80, `fcomp [0x1A28C0]` at 0x88A9B/0x88ABA/0x88AD2; and
   0x88E70's at 0x88E88/0x88EA3/0x88EBC) takes it on its tick and the next
   at 30 fps (ages 0.25 and 0.283; 4 ticks at 60 fps): a button held at
   the chain point chains, a tap released 2 ticks or more before it
   doesn't (stamped now, a tap's last held tick chained a second swing);
   at 0x8D38A, with
   column 13 carried, a held A or B is stamped before 0x88E70, so the
   air attack starts after a take-off and again each time one ends; at
   0x8D46F a jump press on the ground (PC+0x30 set: state 0x100 can be
   airborne, its tick never runs the classifier and 0x8C080 relinks the
   contact each tick, so the hook tests it as the game's own jump does
   at 0x8D1D8) calls `player_jump_init` and goes on as the air
   attack (column 13 carried) or consumes every stamp (else, so the next
   tick's 0x88E70 takes none and the jump stands), skipping that tick's
   0x8C7D0; at 0x89982 a carried air attack the classifier lands becomes
   state 0 at once with a held button stamped, so state 0's 0x88A80(1)
   at 0x8D13B chains on the ground; and the 0x8C728 entry adds the
   current velocity to an air entry's root motion, so the jump's arc
   carries [verified, Unicorn L2:
   `tests/test_player_character.py::test_a_carried_bodys_held_button_jump_and_landing_keep_it_attacking`;
   verified xemu, sitting 2.140 and its record: the held chain, the jump
   cancel (0x102 on the takeoff tick, a plain jump's arc and landing
   within a tick), the cut landing (state 0 on the landing tick) and the
   contact test (no jump from the air in 38 presses)].  A carried swing
   that ends in the air is state 0 (0x8CF8C drops 0x100 to 0 and
   dispatches state 0 that tick), and state 0's case calls
   `player_jump_init` at 0x8D15A (EAX the input, ESI PC; 0x8D156-0x8D15F)
   with no contact test, so a press on that tick jumped from the air
   (AZ-630; since Step 2.132); vanilla reaches state 0 without a contact
   only on such a bypassed tick (walk_state's classifier makes it |2 at
   once: 0x85941-0x85951).  X33's sixth entry (Step 2.145, D413) at
   0x8D15A returns AL 0 with PC+0x30 0 or 0x150 (the game's two forms of
   none, 0x8C0E5-0x8C121), so walk_state classifies the air that tick
   [verified, Unicorn L2: the same test's row (f)].
10. **The roll's root motion, measured for the reach kernel** (Step
   R2.19r2, D843).  On garret4 every `roll forward`
   row's local root velocity (0x8C6FB's EDX) is forward only, one
   float32 a row (21 rows; 637 entries on e7, a5, f2 and w1, each row's
   value the same); the turn is the swing's yaw, the stick's heading as
   a float32, through `quat_from_euler` 0x4FF10 (sin and cos of its
   half, float32) and 0xA1420's matrix 0xA0770 (float32 cells, the
   products exact on x87): world = (F(−F(2zw)·v), F(F(1 − 2z²)·v), 0),
   equal to 0x8C745's desired velocity on all 12,659 rows hooked.  The
   state stays 0x100 off an edge (no classifier), the stored normal
   (+0xB8) is kept, and 0x8C080 relinks a contact each tick (none: a
   jump at the end is straight up, the fall's speed dropped).  The chain
   enters on row 19, the end is the tick after row 20 (405 of 405)
   [verified, base L3, Step R2.19r2].  A roll that turns into 0x102 mid-clip in that set
   was the hit reaction (HP 200 → 160, anim 40), not a roll law.  The
   kernel still hands a roll to FastL3 (`STOP_ROLL`): this step's port
   of these rows was bit for bit until the move met a contact, but its
   rolls landed elsewhere than FastL3's often enough (the move code's
   contact rounding over 21 ground rows) to lose 4.07 points of pooled
   R-recall, so it was reverted (D835).

**Section names:** the attack table is `attacks_anims`, TOC entry 2 at
0x4000, and critter data is `critters_critter_data`, entry 4 at
0x8000.  Until AZ-113 (2026-10-09) the repo's labels were shifted by
one table, so the attack table was labelled `armor_properties_unused`;
labels now come from the file's own `config/<name>` strings
(`docs/XBR_FORMAT.md` § "Table names"), and AZ-124 reads the TOC as
the engine does.  Re-check any old finding that relied on the old
labels.

### The roll's clock and the climb's pace (Step 2.185, 2026-10-25)

**The roll's time rests on one FLD** [verified static, capstone; xemu
sitting 2.185]: `player_attack_enter` (0x88990, EDI the entity) gives
the move's clip layer its rate with `FLD [EDI+0x104]` at 0x889BB
(Europe 0x8896B), entity+0x104 being the Rate of the attacks record
0x7F1F0 copies to entity+0xDC (`roll forward` 1.5), and its window
from Move start and Move end2 × the clip's length (+0x18, +0x24).  The
layer update advances its time by dt × rate and state 0x100 ends when
it crosses the end; each tick 0x8C630 samples `m_feet` from t to t +
rate × dt (0x8C67C-0x8C6AE).  So the roll lasts 30 × (end2 − start) ×
length / rate ticks, 21 in vanilla (1.1667 s × 0.9 / 1.5 × 30), and its
velocity is rate-proportional: `roll_time_scale` k at that FLD gave 11
ticks at k = 2 and 43 at 0.5 in game, the same distance from a 7 m/s
run (3.600 and 3.568 m against 3.582) and less from standing at k > 1
(2.826 m against 3.375 at 2), where the move code's ground-acceleration
cap holds the first ticks back (Modkit's `PATCHES.md` § Roll speed).

**The climb's pace rests on two constants** [verified static, find-refs;
xemu sitting 2.185]: 2.0 at 0x1980E4 (Europe 0x19A28C), read only by
`player_climb_tick` (0x87F80): the rung step 2.0 × dt × the stick (the
FLD at 0x87FA7, so the body moves 2.0 m/s on the rungs at full stick:
0.0667 m a tick in game, up and down) and the rung clips' rate 2.0 ×
|stick| (the FLD at 0x88357, then 0x30940 at 0x883D7); and 1.5 at
0x1980E0 (Europe 0x19A288), read only by the five aligned climb moves'
callers right after the setter 0x8BDB0 (the hoist 0x86D96,
`climb_start` 0x870EE, `climb_from_jump` 0x8743B, `climb_down_edge`
0x87920, `climb_up_edge` 0x87F4C), each the move's clip rate.  In
vanilla on a1's ladder: `climb_start` 34 ticks, 142 rung ticks up, the
climb over the top 70 ticks; `climb_from_jump` 16 ticks, and the hoist
onto w1's 1.7 m ledge 89.  Both scaled by k (`climb_speed_scale`)
halve every count at 2 (17, 71, 35 ticks; 0.1333 m a tick; the jump-in
8, the hoist 45 over the same 2.776 m rise) and double it at 0.5.  The old climb slider's "no effect" (catalogue #6) didn't
hold for the rungs: the step constant moves the body.

### Jump velocity: the v2 correction (April 2026)

`FUN_00089060` is the main jump initiation (plays
`fx/sound/player/jump` and transitions into state 2).  My v1
analysis was **wrong**: I saw 5 `MOV [reg+0x140], 0x41100000`
(9.0) imm32 writes and assumed those set the jump velocity.
They don't.  `entity + 0x140` is the **horizontal air-control
speed** — used by `FUN_00089480` (the per-frame airborne physics
function) as a multiplier on stick input for mid-air steering.

The actual jump-velocity formula is at VA `0x89160` inside
`FUN_00089060`: an `FLD` of the gravity constant at `0x001980A8`
(g = 9.8) at 0x89160, an `FMUL` by `[ESI+0x144]` (h, the jump height)
at 0x89166, an `FADD ST0, ST0` (× 2) at 0x8916C, an `FSQRT` at
0x8916E and an `FSTP` of v₀ to the stack at 0x89170.

Classic projectile formula `v₀ = sqrt(2gh)`.  `entity + 0x144`
is populated from `FUN_00083F90` for standard jumps or
`*(entity+0x68)` for charged jumps; the imm32 `0x3F8CCCCD`
(1.1) writes around it are transient initializer values that
get immediately overwritten.

**v2 patch**: rewrite the FLD at `0x89160` to
`FLD [inject_va]` where `inject_va` holds
`g × jump_scale²`, g being the gravity slider's value (9.8 when
unset).  The SQRT then produces
`sqrt(2 × g × jump_scale² × h) = jump_scale × sqrt(2gh)` —
linear scaling on initial velocity, and a peak height of
`jump_scale² × h` at any gravity (because `max_h = v₀² / (2g)`).

Critical property: the shared gravity constant at
`0x001980A8` is NOT touched.  The gravity slider continues to
own that constant (16 references in `.text`; the airborne tick
loads it at 0x8950B and passes g to `FUN_00085700` as an argument,
see "Gravity" below).  Gravity changes only launch speed and airtime,
never the height (D16, Step 1.19a; before that the injected
constant was a fixed `9.8 × jump_scale²`, AZ-017).

✅ **Learning**: **imm32s written to entity fields around
physics sites are NOT always the physics parameter**.  Some are
transient init values that get overwritten before use.  Always
trace the RELEVANT FORMULA (the FPU chain that produces the
output) to find the actual parameter, not just the stored
fields near it.

✅ **Learning**: **the post-mortem is the patch**.  v1 shipped
with correct byte manipulation against the WRONG site and the
user's "doesn't work" report was 100% accurate — my assumption
about what `+0x140` meant was the bug.  Spending 10 minutes on
the disassembly of the consuming formula BEFORE picking the
target would have avoided v1 entirely.

### Swim speed lives in FUN_0008b700 (April 2026)

The player has a dedicated swim state handler, `FUN_0008b700`
(`player_swim_tick`: EAX = input, [esp+4] = entity, RET 4, result in
AL).  The state machine calls it from its ground, air, slope,
zipline and swim cases (0x8D118, 0x8D35F, 0x8D221, 0x8D26B, 0x8D2B5,
0x8D1CB), each with `PUSH EBP` (the entity) and `MOV EAX, EDI` (the
input), and a non-zero AL ends the frame [verified static
2026-10-11, capstone; live in xemu s6, ESI was the input on 0x8C230's
stack and EBX the entity].  Inside, ESI is the input, so the "in
water" gate is **input+0x135** bit 0 (`TEST BYTE [ESI+0x135], 1` at
0x8B712): while it is clear the function zeroes the timer
`[0x1AAB64]` and returns 0.  While it is set the timer adds dt each
tick, and at 4.0 s (`[0x1A25CC]`) it only decides whether the
one-time `"loc/english/popups/swim"` popup (the call at 0x8B77F) is
shown; both branches rejoin at 0x8B782 [verified static 2026-10-11,
capstone over 0x8B700–0x8B7C9].  The speed
calculation is an `FLD` of the stick magnitude `[ESI+0x124]` at
0x8B7B9, an `FMUL` by the float at `0x001A25B4` (10.0) at 0x8B7BF and
an `FSTP` of the stroke to the stack at 0x8B7C5.

**The stroke is a target speed, not a distance per frame** [verified
xemu s6, 2026-10-11, `vanilla-ocean`].  The desired
horizontal velocity is the direction (input+0x128, +0x12C) × the
stroke plus input+0x140/+0x144 (0.0 in the captures), and each tick
v = desired + (v_old − desired)·0.1^dt per component (`pow` of
`[0x1980B4]` = 0.1; ×0.926119 per tick at dt 1/30), handed to the move
code 0x47380.  With a full stick v_h = 10·(1 − 0.1^(n/30)) to within
1.1e-6: 9.000 m/s after 1 s, 9.900 after 2 s, and an asymptote of
**10.000 m/s**; the box moved Σ v·dt.  After the release v decays
×0.926119 per tick.  The FMUL runs once per swim tick.

The shared `10.0` at VA `0x001A25B4` has 11 disp32 readers
(10 in `.text`, 1 in DSOUND), so 10 besides the slider's site; most
are unrelated to player movement, but one, the `FLD` at 0x47B51, is
inside the move code 0x47380, so editing the constant in place would
change the move code too [verified static 2026-10-11: `python -m devkit re xbe
insns --operand 0x1a25b4`].  We patch only the player
site (VA `0x0008B7BF`) by rewriting the `FMUL [abs32]` to
point at an injected `10.0 × swim_scale`.  With that redirect poked
into RAM (10·k in `.text`'s tail padding), the speed was ×k on every
held tick and the time constant unchanged: 25.83 / 35.38 / 51.65 m
over 3 s at k = 1 / 1.37 / 2 [verified xemu s6; a built ISO was not
booted].

Because swim is a separate state + separate constant, its horizontal
stroke has **no coupling** with walk or roll — the independence math
is trivial: `inject_swim_mult = 10 × swim_scale` and you're done.

Note the second-order coupling: the magnitude read by
`FUN_0008b700` at `+0x124` is still the output of
`FUN_00084940`, so the cheat-buttons turbo (flag 0x40, cvar
`enable cheat buttons` on) triggers the 3.0 boost BEFORE the swim
10.0 stroke.  The vanilla target speed is `10 × raw_stick` m/s (30×
with the turbo).  The `swim_speed_scale` slider multiplies BOTH.

**Vertical swimming is `walkSpeed`, which the slider doesn't touch**
[verified static 2026-10-10: capstone over 0x8B7B9–0x8B918; found
by the evidence sweep, HP-01]:

- Unless the byte at input+0x30 is set (`0x8B7FA`; then the term is
  0), the tick takes the largest of the X, Y and WHITE pressures
  (ControllerState+0x20/+0x24/+0x2C) minus the largest of A, B and
  BLACK (+0x18/+0x1C/+0x28) and multiplies it by the species'
  `walkSpeed` (`FMUL [EDX+0x38]` at `0x8B8C5`; EDX =
  `[[EBX+0x20]+0x178]`, loaded at `0x8B82E`).  The result is added to
  input+0x148 to form the desired z (`0x8B90E`–`0x8B918`).
- The stroke coefficient that `swim_speed_scale` scales (stored at
  `0x8B7C5`) multiplies only the horizontal direction, input+0x128 and
  +0x12C (`0x8B8D8`, `0x8B8EA`).  It is also passed to `0x85D80` on
  the branch at `0x8B7CB`, which is unexplored.
- So the slider leaves vertical swimming at vanilla, garret4's
  `walkSpeed` (5.0) sets the vertical swim speed, and a `walkSpeed`
  edit changes it [inferred from the code]; `randomize-full
  --player-character` didn't from Step 2.21a (the player stays
  garret4, D112) until Step 2.145 (D422): a body of size s other than 1
  dives and rises at 5.0 × √s.  `walk_speed_scale` writes `runSpeed`, not
  `walkSpeed` (D53), so it doesn't.
- **Measured** [verified xemu s6, 2026-10-11, vanilla]: A dives
  toward −5.0 m/s (−`walkSpeed`) and X rises toward +5.0, with the
  same 0.1^dt blend (−4.5 after 1 s); the state stays 6.  That the
  vertical speed stays ±5.0 at any `swim_speed_scale` is [inferred
  from the code: the vertical term doesn't use the stroke].

### The swim's drawn origin and garret4's camera point (2026-10-22, Step 2.150)

In the swim `player_swim_tick` places the drawn origin at the centre +0x15C less the playing clip's `m_root`,
unscaled (0x42E40 at 0x8BD79), and the camera point (0x41F40) is that origin plus `m_head` × +0x188. Garret4's
`m_head` is one height per swim clip, the record's 1.9925 where a clip keys none, while his `m_root` moves, so his
point over his drawn root (the centre) bobs with the root:

| Clip | `m_head` z | `m_root` z | Point over the centre | Camera over the surface at 1.126 m deep |
|---|---|---|---|---|
| swim_idle | 1.9925 (unkeyed) | 1.533-1.589 | 0.404-0.459 | 1.778-1.833 |
| swim_idle_up | 0.700 | 0.219-0.282 | 0.418-0.481 | 1.792-1.855 |
| swim_idle_down | 1.9925 (unkeyed) | 1.150 | 0.843 | 2.217 |
| swim_1 | 0.664 | 0.290-0.311 | 0.352-0.374 | 1.726-1.748 |
| swim_2 | 0.519 | 0.211-0.330 | 0.189-0.308 | 1.563-1.682 |

[computed from vanilla `characters.xbr`, the camera 2.5 m over its point at rest; Step 2.134b's sitting measured
1.783-1.835 at rest and 1.563-1.682 in the stroke (row C)].
X8 puts a W27 body's swim point there over its own drawn root (W27's `m_eye`, Step 2.150, AZ-642).

### Springboards, updrafts, flap timing and the lip lift (2026-10-12)

The xemu calibration sitting measured these on sandboxed clones
(2026-10-11 PDT). "Placed" means measured after a RAM teleport or
poke: it shows the mechanism, not where it happens in a level (Q251).
The randomizer's movement envelope
(`src/azurkit/tools/randomizer/draft/envelope.py`, Step R1.2) models each one.

- **A springboard launch** [verified xemu, placed; verified static
  `0x890B6`-`0x890F7`, `0x8917F`-`0x891D6`]. jump_init (`0x89060`) also
  runs when the contact word has bit 0x04 (autoSpring), on every contact
  tick; a non-zero contact springboard `[ent+0x68]` (S, in m) takes the
  `0x890C6` path. The launch sets h := S and v0 = √(2·g·S) exactly (S 24,
  25, 44 and 100 gave 21.68870735, 22.13594437, 29.36664772 and
  44.27188873 m/s), air control 9.0 even with an air shield (`0x83F90`
  isn't called), and peak_z := input z + S; an autoSpring pad launches
  straight up and keeps the horizontal velocity. The feet rose 23.63984,
  24.63206 and 99.26343 m for S 24, 25 and 100, as the 30 Hz model
  gives. Every solid springboard on the disc is autoSpring [verified
  ISO].
- **Flaps after a launch** [verified xemu, placed]. The first flap resets
  h to 1.2 (and air control to the kit's 12 [verified L2:
  `tests/test_movement_envelope.py`'s springboard case]), then
  d = S + 1.2 − rise: above 6 m
  it is a descent flap (vz 2.42487, the gauge empties and the shield
  drops); otherwise vz := min(4.84974, vz + 1.5·v0f), so a flap during
  the climb cuts the speed. With flaps at the apex the ceiling is
  S + 1.2 (25.18 m for S 24).
- **Updrafts (pushZ)** [verified xemu, placed]. Airborne inside a pushZ
  volume, vz′ = vz + c·(pushZ/0.9 − vz) with c = 0.035404 per tick, and
  gravity doesn't act: vz tends to pushZ/0.9 (fit residual ≤ 1.9e-6 m/s
  for pushZ 10, 30 and 60). w1's pushZ 100 volumes are chained
  water-spout rides and f3's pushZ 30 volumes are water tubes (swim
  state 6), not air updrafts.
- **Flap timing** [verified xemu]. Over ten captures of air shield 3
  the game's response to any flap timing equals the per-tick model's
  to f32 precision (largest |Δvz| 7.9e-6 m/s, apex within 1e-4 m), and
  flaps pressed every 2nd tick (one released tick between presses) all
  register.
- **A stale peak_z** [verified xemu, placed]. A flap after a fall with
  no jump uses the last jump's peak_z; above that ceiling it lifts
  nothing but still costs a flap and fuel.
- **The lip lift** [verified xemu, placed: the plain jump on one ledge;
  [inferred] for an air shield's jump or a flap]. On S4's ledge (lip
  1.2578 m), with the plain-jump height immediate at `0x83FC5` poked to
  vary lip − apex, a running jump mounts up to lip − apex = 0.4987 m and
  fails at 0.5232 m. The takeoff window narrows as that deficit grows:
  0.2343 m mounts from 0.65-3.69 m before the face (s6), 0.4271 m from
  takeoff rows 22-28, 0.4745 m from 23-27 and 0.4987 m from 25-27 (its
  far edge not measured); rows were sampled 2 apart, so each edge is
  ±1 row (7/30 m).

### The volume query, pushes, swimming and springboards in the code (Step R2.19e, 2026-10-28)

[verified static: `python -m devkit re xbe fn|dis|read` on the USA XBE; the native kernel's port of each agrees with FastL3
tick by tick on R2.16e's bench (the game's words, push and depth read at
0x85599 on 44,000-50,000 ticks a level, none differing where the kernel models the volume; the depth in two
overlapping water volumes from its review's FastL3 check on w1: the deeper on 58 of 59 points).]

- **The volume query** 0x60BD0 runs once a player tick in the input build (0x85587), at the body centre
  (critter+0x15C) as the tick starts. Each field platform holding the point (its word has 0x20; the test 0x79D30 casts
  a ray straight up through its `tern`, 0xD2A40, and holds it when the first face met faces down) ORs its word into
  input+0x134 (0x08 push, 0x100 water) and adds its push to input+0x140/+0x144/+0x148: a pushEnable platform's
  pushX/Y/Z turned by its world matrix's rows (0x79EFE; a non-zero +0x298 instead pushes horizontally along the
  point's offset from its box's centre, 0x79E48 [static only: its attribute isn't named, and the kernel doesn't port
  it]), any other's raw. input+0x14C, the depth the swim reads, is the up-ray's distance to that
  face, the greatest over the holding platforms with the water bit (from -50: 0x60DA8 tests the word's 0x100, which
  overwrites the status of the +0x284 maximum just before it; 0x60DCB-0x60DDE keep the larger depth), so of two
  overlapping pools the deeper one's. No push bit, no push (0x855A6).
- **Pushes act in the air and the water only** (input+0x140 has no other reader). Airborne (0x89515) with the push
  bit, the air control target is cut to 0.1 x (air control x stick) and the push added, and the blend's base is 0.3
  (`[0x1980B0]`) for 0.6; with pushZ non-zero T_z = 0.1 vz + pushZ, gravity is 0 and the fall reference drops to the
  feet. Hence the measured updraft law: vz' = vz + (1 - 0.3^dt) x 0.9 x (pushZ / 0.9 - vz), c = 0.035404. A walk, a
  slope or a slide in a push volume is untouched. The blend (0x89613) stores x and z through a float twice,
  T + float((v - T) k), and y once: on one a5 stand jump that keeps the kernel's x velocity bit-equal with FastL3's
  for 16 air ticks, against 1 with one store each; the kernel's air
  outside a push volume keeps the one store (D835: the exact blend moved a knife-edge landing after an inexact
  contact and lost a find), until the sweep's face order is ported.
- **The swim tick** 0x8B700 runs first in the walk, air, slope and swim cases (0x8D118-0x8D35F) while input+0x135 bit 0
  (water) is set; out of state 6 it needs the depth at least 0.25 m (`[0x198110]`). Its target is the stick's
  direction x (10 x the stick's magnitude) plus the push, and vertically (max(X, Y, WHITE) - max(A, B, BLACK)) x
  walkSpeed plus pushZ, the blend 0.1^dt; within 0.25 m of the surface vz is capped at pushZ. The move is a 1 m
  sphere (0x8B9A9: rh = rv = 1) with w = v and no gravity; a contact then tries the catch 0x87120 and the lip lift
  0x86920 with 0.5 m more reach (1.736 m ahead: climbing out); the velocity is the move's. 0x85D80 is the surface's
  splash and ripples only. Out of the water state 6 walks (0x85F50) if attached, else runs the airborne tick, with no
  jump or flap that tick.
- **A springboard** is jump_init's (0x89060) autoSpring path on a ground tick: the attach word's 0x04 runs it with
  no Y, h := the face's springboard height (air control 9; 0 takes the kit's h), straight up (the slope branch is
  skipped), keeping v_xy.

### A roof stops the rise (2026-10-14)

[verified L3, Step X.21: a roof probe on a6's kit 0
snapshot, standing jumps with `jump_speed_scale` 2 and 3 under roofs
3.3-4.3 m over the feet, the derive's own roof query.] When the head
meets a roof, the step's collision (collide/move `0x47380` [inferred])
holds the body there and takes away the speed into it: on that tick the
feet stop about 1.9 m under the roof (1.86-1.93 m over flat roofs,
1.77 m at the fastest jump), vz drops from 6-12 m/s to 0.5-1.1 m/s (what
a slanted roof leaves) and the rest turns sideways (1.7-3.4 m/s), then
the arc falls on under gravity as any other. The flight doesn't end
there: a taller jump under a low roof only lands sooner. The
randomizer's calculator (`physics.Physics.arc`'s `cap`, AZ-364) stops
the feet at the certificate's headroom less 2.0 m (the derive's headroom
has its 0.1 m head tolerance in it), as one flat roof over the whole
flight, with no vertical speed left; since Step R1.24a (AZ-387) the
roof over the arc's first and last quarter is kept apart and a taller arc
rising into it there is clipped by it, over the whole flight. That is
conservative [verified L3, Step R1.24a: 8
seeds of 40,000 steps a value on the reach engine's kit 0 snapshots]: of
six of the golden seed's roof flights, the three the clip drops between
jump x1.2 and x1.4 (f2_z103 > f2_z052, f6_z877 > f6_z093 and f1_z077 >
f1_town_side, which the flat roof drops at x1.4 too) and three it keeps
(w3_z076 > w3_z099, e6_z049 > e6_z047, e5_z017 > e5_z122), the game made
all six at x1.2 and x1.4, at standard robustness but w3's (hard to
frame_perfect, as at vanilla).

### A walk-off carries less than a jump's arc; slippery slopes slide back (2026-10-14)

[verified L3, Step X.16; player
tick, vanilla.]

- **A walk-off** (running off a ledge without a jump): of 38 walk-off
  ledges on 9 levels, 28 were clean (no speed lost in the air); on the
  11 with a level lip the body left 0.1-0.5 m before the floor's end and
  landed its centre 0.28-0.94 m short of the calculator's carry past the
  takeoff floor's end, at every drop up to 10 m. The randomizer counts a
  walk-off's carry from there (`physics.WALKOFF_SLACK` = −0.95 m, AZ-357).
  A lip that slopes down carries 0.8-1.8 m less again at a 1 m drop:
  the body leaves along the slope at its run speed, 0.7-2.9 m/s of it
  falling. Taken as the walk-off's first fall speed (the rest of the run
  ahead), the calculator's carry plus the slack lies within L3's reach on
  233 of the 234 clean (ledge, drop) rows, where the carry from rest
  passed it on 124 (the one left: e7.Z022, 0.59 m, at a lip leaving at
  only 0.48 m/s down) [verified L3 data, Step R1.24a].
  The randomizer reads the slope from the lip's top triangle (AZ-365).
- **A slippery slope slides the body back.** A 3 s walk up the fall line
  from a settled stand makes 1 m or more of headway in 81-100 % of the
  samples from nz 0.998 up, 68 % at 0.995-0.998 and under 20 % below
  0.995 (w2, w1 and town). So a slippery face under nz 0.998 is no floor
  for the logic, only a one-way slide down its fall line
  (`floors.SLIP_FLAT_NZ`, AZ-359), and no takeoff. Even flat slippery
  floor slides while walked (82-90 of 90 ticks, 6-8 m in 3 s), so a
  running jump from ice has no full-speed run-up: until the ice run is
  measured the randomizer takes a jump from it as a standing one (AZ-366,
  Step R1.24a).

### Fall damage: three tiers on a floor, a death check elsewhere, no armor (2026-10-17)

[verified static, Step 2.91a's research:
capstone on the USA `default.xbe`; the 10 HP of a height-2 fall (`fall damage 2`) measured in xemu earlier.]

- **The fall reference** is entity+0x168. Each floor contact sets it to the
  floor's z (0x8C17C), and so do swimming (0x8BD86), climbing (0x88430)
  and a slope slide (0x8AB55). The input reset (0x84E1C),
  `player_input_build` (0x856D8) and the fly cheat (0x8972F) set it to
  −FLT_MAX, so no fall counts. While a volume push with a vertical part
  acts on the player (input+0x134 bit 3, 0x895B8–0x895E7) the airborne tick
  lowers it to min(itself, z − 1) [inferred: updrafts and currents]. A
  jump's rise never raises it.
- **Landing on a floor** (`player_landing` 0x8C080 → `fall_damage_dispatch`
  0x8AB70; a floor is a contact whose normal z is above 0.6, 0x8C12F, and
  a steeper one neither costs HP nor resets the reference): only a landing
  below the reference, at a vertical speed (relative to what you land on)
  of at least `fall min velocity`, costs HP. The highest tier the drop
  reaches (height 3, then 2, then 1) sets HP to HP − (int)`fall damage N`
  through the clamped HP setter 0x44640 (0x8AD87–0x8AD9B), then plays the
  fall rumble and "ouch". The damage is truncated to int32 by 0xF5A40 (a
  value outside int32 wraps: 3e9 heals instead of killing [computed]); 0
  makes a tier harmless and a negative one heals up to max HP. **Armor
  never reduces it:** the path doesn't reach the armor code.
- **`fall height 4`** is `fall_death_dispatch` (0x8BE00), which a fall
  ending on a floor never reaches. It runs at a jump start (0x892A0), a
  wing flap (0x8945E), a contact with no floor object (0x8C095 [inferred:
  water or the world's edge]) and 0x856E2, right after the reset to
  −FLT_MAX (so that call can't kill). When min(drop, v²/2g) is above
  `fall height 4` (v the downward speed, g the 9.8 at 0x1980A8, which the
  gravity slider rewrites, D16) it sets HP to 0 whatever the HP, plays
  `fx/sound/player/fallingdeath` and sets the death flag (entity+0x16C
  bit 0).
- **Game over** follows any death (state 7, the death clip, the continue
  popup). In vanilla (heights 6 / 8 / 17 / 65 m, damage 5 / 10 / 1000,
  min velocity 10 m/s) any drop of 17 m or more onto a floor kills (1000 is
  over the 400 HP of a full upgrade), heights 1 and 2 only hurt, and a
  flap, a jump or a no-floor contact more than 65 m below the reference
  kills. To never die from a fall, zero the three damages and raise
  `fall height 4` (the config-editor workaround that replaced the deleted
  `no_fall_damage` pack).

### Contacts: the move code's loop, the classifier, the jump, the catch and the fall rule (2026-10-18)

[Step TD.0, from the trick-discovery design's §1, the tjump study's §1
and xemu sitting skips-a; USA VAs; labels as there:
[verified static] code read, [verified xemu]/[verified L2] measured, [inferred] a reading.]

- **The body is an ellipsoid, 0.5 m across and 1.0 m up** (Step R2.17's collision map, landed with Step R2.19d's
  native kernel): `gravity_integrate_raw` writes the move request's +4 := `[0x1A9C84]` 0.5 (the horizontal radius)
  and +8 := `[0x1A9C88]` 1.0 (the vertical) at 0x8570D-0x8571C, constants, not config; the centre (critter +0x15C)
  is 1 m over the feet. The step-up sweeps the same body (its pushes at 0x8B298/0x8B2A1) [verified static]; the lip
  lift 0x86920 reads the same two constants round its three sweeps [inferred]. The face test 0xB9E60 sweeps a
  sphere of the horizontal radius in a space whose z is halved (rh / rv), which is what `devkit/reach/native`'s
  kernel runs. `randomizer/physics.py`'s `BODY_HEIGHT` 2.0 [inferred] is twice the 1.0 m semi-axis.
- **The static level's walk, its face loop** (Step R2.19m; FastL3's C walk, `devkit/reach/fastl3_step.c`'s
  `h_walk`): collision_sweep reaches the tern's walk 0xD1B80, which for each chunk of its BVH whose flags pass the
  move's mask cuts the faces to the query's x range (0xD18D0) and runs the loop 0xD1E80-0xD22FD over them, its index
  in ECX and `[esp+0x14]`, its end `[esp+0x30]`, the chunk in EBX (byte +6 the vertex count n, the i16 vertices
  x, y, z from +0x16, then a face a 4-byte record, its vertex indices at +0, +1, +2). Each of the three vertices goes
  through the query's matrix at `[esp+0x80..0xB8]` with the x87 at 53 bits: x' = ((m80 X + mA0 Z) + m90 Y) + mB0,
  y' = ((mA4 Z + m94 Y) + m84 X) + mB4, z' = ((mA8 Z + m98 Y) + m88 X) + mB8, each stored as float32 (`[esp+0x40..
  0x48]`, `[0x34..0x3C]`, `[0x24..0x2C]`, copied to `[0xF0..0x110]` and `[0x12C..0x14C]`); a face whose three
  vertices all lie below one of `[esp+0x18, 0x1C, 0x20]` or all above one of `[esp+0xCC, 0xE8, 0xEC]` is dropped
  (to 0xD22EE), else the face test 0xB9E60 runs from 0xD22B0, a hit cutting tmax `[ebp+0x10]`. On 56 fan and aimed
  jobs of seven levels about 240 faces a tick reach the loop and 20.3 M decisions in C matched the game's, every one
  [verified L3, the C walk's check mode]. The loop is 41 % of a FastL3 tick's guest instructions on e7, the face test
  3 % [measured, 6 bench jobs].
- **The contact loop.** The move code 0x47380 sweeps the body (0xB9E60) and on a contact projects the velocity
  onto the face, v' = v − (v·n)n; later contacts in the same move bounce (restitution 0.25, then 0.5). A face
  stops motion only into its front (0xB9FA5): one-sided faces, open wall tops and overlapping sheets let a body
  through from behind, which the derive's both-sides rule doesn't model [verified static].
- **The classifier 0x85920** runs after the move (called from walk 0x8672A, airborne 0x89982 and slope 0x8A1E2)
  and writes the stored contact normal entity +0xB8..+0xC0: (0, 0, 1) at 0x85A34, else the move's contact normal at
  0x85AC3; slope landing (0x8B040), the dead state (0x8D04E) and init (0x84DC3) write it too, and nothing in the
  climb, catch or grab code does, so in the air it holds the last ordinary contact's normal [verified static,
  0x80000-0x90000 scanned]. `obs.Obs.normal` reads it; `devkit/sim/faces.py` finds the face it belongs to (the
  entity keeps no face pointer). Its arguments (Step R2.19f+'s read) are the input (EDX: +0x148 the push's z), the
  move request (ECX: +0x1C the velocity asked, +0x60 the one left) and the contact record (EBP: +0x38 its hit
  object). No hit object: a fast slide (state 4) stays one while its timer +0xD4 is under 0.5 s **and pushZ is 0**
  (0x8596E; the timer gains the float dt 0x1980A0), else the air. A hit: the dead stop first (all three velocities
  left 0, the asked vz under -0.5 g dt and under -0.866 |v|: the normal (0, 0, 1) at 0x85A34, then a walk, or the
  hard landing 0x8B100 off any other state when the speed change reaches `[0x38B0C4]` and the clock less entity
  +0x88, a double, passes 0.5 s); then, **with pushZ over 0, the air, no normal stored** (0x85AA7: in an updraft a
  contact lands nothing); else the contact's normal at 0x85AC3 and the nz classes [verified static; the kernel ports
  both pushZ rules since Step R2.19f+].
- **The lip lift's and the step-up's clips, as FastL3 plays them** (Step R2.19f+'s probe of e7's flagged launches): on the tick the lift 0x86920 decides, the body centre is
  put 1.236 m ahead of the tick's start at the ledge's height (the decision's swept point), its velocity 0, in state
  0x100 with animation 65 (a ledge whose feet sit about 0.9 m over the centre) for 89 rows or 66 (about 0.1 m) for
  37, settling in place, then a walk (state 0; on a slope 3). A step-up 0x8B1D0 puts it on the step that tick and
  plays animation 53 for 5 rows in state 0x100; where on the step is not the decision's down-sweep point (the kernel's
  port put it 0.16-0.19 m across and 5-8 cm lower, 0 of 17 within 2 cm on a5's and f2's aims, `stepup-a5`,
  `stepup-f2`; the lift's within 2 cm 118 of 127 times), so the kernel still hands the step-up to L3 [unread:
  0x8B1D0's placement]. The tick after a clip's last 0x100 row is the walk's own (its move, or a jump on Y), for the
  hard landing's 13 rows of animation 11 too [measured FastL3, a5's first 150 aims: `hard-exit-a5`; the kernel spent
  one more tick in place until Step R2.19f+'s fix]. The roll is state 0x100 with animation 102 for 21 rows (40 when
  chained) and moves the body (root motion; not ported) [measured FastL3, e7: 47 lifts, 41 step-ups, 190 rolls].
- **What a contact does, by the face** (the game's thresholds [verified static unless marked]):

  | Surface class | What the game does | Tricks it enables |
  |---|---|---|
  | nz ≤ 0.6 (walls, ramps 0.3-0.6) | no landing (0x8C12F); the contact projects the velocity; later contacts bounce | speed turned into lift, launches |
  | 0.6 < nz ≤ 0.7071, or any slippery face | state 3/4, no friction; a jump goes along the normal and keeps the slide speed (0x89060); state 4 keeps horizontal speed | slope hops, slide carry |
  | 0.7071 < nz < 0.8 | walkable (friction 10, step-ups 0x8B1D0); the logic's floor rule (nz ≥ 0.8) excludes it | steep walks and step-up chains |
  | 0.80-0.87 | the logic walks it; bodies slid off f6 and e2 rims in sittings [sitting note only] | to measure in L3 |
  | climbable, \|nz\| < 0.2588 | the catch (0x87120); each Y in the catch adds 4.6434 m/s along the stored normal [verified xemu skips-a] | the tree-jump charge (e6.tree_song_skip) |
  | one-sided faces, open wall tops, overlapping sheets | a face stops motion only into its front | climbing out of bounds and back in |
  | trigger meshes poking through the shell | the body centre inside the mesh fires it, even in mid-air | itrig (w1.torpedo_skip's town trigger) |
  | springs, push fields, moving solids | spring height (+0x68), push, surface velocity | springs and push fields act in player ticks: the autoSpring launch is jump_init's, whose six callers (0x8D15A-0x8D48B) are the player's state ticks [verified static], and updrafts gave the same rows in both modes [verified L3, Step X.15]; moving solids need whole-scene steps |

- **The jump 0x89060** (`player_jump_init`; ESI = entity, EAX = input) fires on input+0x20 bit 0x04 (Y's edge) or
  entity+0x60 bit 2 (the attach word's autoSpring). h is the surface's springboard height +0x68 when non-zero, 0
  in state 5, else `airborne_reinit`'s 1.1 (1.2 with an air shield); peak_z = z + h, v0 = √(2gh). Attached
  (+0x30 not 0 or 0x150), autoSpring clear and the face slippery or nz ≤ 0.7070999742, it takes the normal branch
  (0x8917F-0x891D6): vx += v0·nx, vy += v0·ny, vz = input+0x74 + v0·nz, so a slope jump keeps the slide speed
  and a jump off a wall's stored normal adds speed along it; else vz = input+0x74 + v0 [verified static, L2]. It
  runs before anything else on every tick of the climb (1) and catch (0x101) states (0x8D3B6, 0x8D48B).
- **The catch 0x87120** runs from the airborne tick 0x89480 when the move reported a contact, entity vz ≤ g·dt/2
  (0.16333 m/s, `[0x38B0C0]`) and the contact's nz ≤ 0.6, after the lip lift 0x86920: it needs the stick up
  (input+0x0C > 0) and a forward probe (0x60870) on a word with (word & 3) == 2 and |nz| < 0.2588, plus two
  clearance sweeps; it sets state 0x101 with animation 0x40 (0x8BDB0) and writes no velocity, and a catch returns
  at 0x89992, before the move's result is committed (0x897BC) and before the classifier, so that tick neither
  applies gravity nor clips the velocity [verified static, L2]. Hence the charge: each Y inside the catch adds
  4.6434 m/s (4.8497 with air 1) horizontally along the stored normal and sets vz 0; 0x101 lasts 16 rows, the
  window k 2-17; the climb tick 0x87F80 wipes the charge (velocity := the surface's) [verified xemu skips-a]. The
  slippery+climbable 0x8013/0xC013 class fails the (word & 3) == 2 test [verified static].
- **The mid-air fall rule** is `fall_death_dispatch` 0x8BE00 (§ "Fall damage" above): at a jump start, a wing
  flap or a contact with no floor object, min(drop below the fall reference +0x168, v²/2g) above `fall height 4`
  (65 m in vanilla) kills, whatever the HP; a landing on a floor takes the damage tiers instead.

### The drawn origin and the centre on the zipline, the let-go and the cable's end (2026-10-19, Step 2.105)

The model is drawn from its own origin, which isn't the collision centre (AZ-529) [verified static, capstone and a
read-only `ghidra-serve` copy, Step 2.105's read]:

- **Two points.** The centre +0x15C is where the body collides (0x61100 writes it; the critter's bounds, vtable
  +0xC0 = 0x41570, are taken round it with the orientation +0x18C); the model matrix comes from the origin
  +0x1B0/+0x1BC by the glide mode +0x19C (0x42070 through `critter_model_matrix` 0x42200: mode 0 the origin, 1 a
  timed glide from +0x1B0 to +0x1BC on the clock at [critter+0xE4]+0x10, 2 the aligned move's). Movement keeps the
  offset between them: 0x43170 adds one delta to +0x1B0, +0x1BC and, through 0x61100, the centre.
- **`anim_apply_translation` 0x42E40** (ECX the turn, EAX the new centre's buffer; the critter, a blend time, a
  marker's name and a point; RET 0x10) sets the centre := *EAX (0x61100 at 0x42E61), then the origin := the point
  less the turned marker: with a blend of 0 (every caller's) +0x1B0 = +0x1BC and mode 0; above 0 a mode-1 glide.
  The marker's name goes to +0x1F8/+0x1FC.
- **The ride (state 5, 0x8A510).** The centre is the cable contact plus its normal × 1.0 less 1.0 m up (the EAX
  buffer at 0x8AB2E), and the fall reference +0x168 its z (0x8AB55); the origin is the cable point less the turned
  `m_grab` (0x8AB32, which X9 moves down: Step 2.103, 2.104). So the drawn body never moves the centre: at a model
  scale × 2 the origin rides 5.38-5.63 m under it (× 1: 1.69-1.94) [measured, sitting 2.104].
- **The let-go and the cable's end.** In state 5 the state machine (0x8CCC0) calls `player_jump_init` first
  (0x8D2C6); its state-5 branch adds no impulse, places `m_feet` at the centre less 1.0 m (0x42E40 at 0x89290) and
  sets state 2, and the tick ends there (AL 1, 0x8D2CD). Else 0x8AE10 (a ray 1 m down from
  the centre, mask 0x10; on a hit it places `m_feet` on the floor at 0x8AFAF, 0x8B026 or 0x8B0B2 and touchdown
  glides) and then the ride; a ride that returns 0 (its 1.5 m upward sweep misses the cable, or the path sweep hits)
  gets state 2 and `player_airborne_tick` in the same tick, which places `m_feet` at the centre less 1.0 m every
  tick (0x42E40 at 0x8996D) unless the state has 0x100 (then 0x43170 at 0x8994B). In state 2 a wing flap's tick
  (0x89300, its placement at 0x8944E) ends before the airborne tick. So each moves the origin to its stance in one
  tick: 4.55-4.64 m at × 2, the control's 0.85 m [measured, sitting 2.104]. X22
  (`src/azurkit/tools/characters/player_model/hang_ease.c`, Step 2.105) eases those three placements at most 0.847 m a tick
  for a body drawn at a model scale other than 1 [measured, sitting 2.105: at most 0.847 m a tick, the stance in 6
  ticks at × 2, the centre and +0x168 the game's to 0 mm].
- **`hang_start` (0x8A200)** sweeps an ellipsoid up; on a cable hit it sets state 0x105 and 0x42430 sets the centre
  to the hit's sphere centre and glides the origin from where the body stands (+0x1B0) to the end (+0x1BC), which X9
  puts at the target less X × garret4's end `m_grab`; the standing origin sits 3.793 m under the cable point, so ×
  2's end (6.398 m under it) is 2.6 m under f3's start floor [measured]. **The ladder** puts `m_grab` on the rung
  point (0x883FF in 0x87F80, 0x8875B in 0x88490), which X9 moves by an unscaled garret4 `m_grab` (−1.196 to −1.269 m
  at × 2 [measured]); its latch and top moves are 0x42430 glides from the body's current drawn origin (+0x1B0 :=
  0x41E50(start node) less the turned start-node offset) [formula verified static; the stand-in's start inferred].

---

## Simulation tick rate

### dt is 1/30 s in vanilla, 1/60 s with fps_unlock

The vanilla per-tick delta is 1/30 second, stored as IEEE 754 float
`0x3D088889` in several private `.rdata` copies.  dt is **not**
fixed: the `fps_unlock` pack rewrites those copies to 1/60
(including VA `0x1980A0`, the player dt that `0x84F90` copies into
`PlayerInputState+0x04`) and also raises the CAP on how many
simulation steps run per render frame.  Shims must read the live dt
(input `+0x04`), never hard-code 1/30.

A long air-3 flight keeps its reach at any of these rates [verified
xemu, Step X.24: f3_z042 > f3_z235, 32.3 m to +2.2 m with 2-3 flaps,
made on each build booted at 30, 60, 77, 90 and 120 fps, the player
standing on the landing a second later],
as the calculator's exact flap search says (X.23).  A search for it
must count time, not ticks (AZ-372).

---

## Gravity

### The master gravity constant is a single `.rdata` float at VA 0x001980A8

Gravity value is `9.8` as a 32-bit float at VA `0x001980A8`.
`FUN_00085700` (`gravity_integrate_raw`) integrates
`velocity.z -= g * dt`, but it does **not** read this constant: g
arrives as its stack argument, which the airborne tick loads from
`0x001980A8` at 0x8950B [verified 2026-10-09].

The constant has **16 references in `.text`** [verified 2026-10-10:
an imm32 scan of the vanilla XBE]: the jump (0x89160) and flap
(0x893AE) `FLD`s, the airborne tick, walk_state, the slope-slide
tick, the attack-move/roll code around 0x8C72F/0x8C80C and others,
plus three static initialisers (0xFBAA0, 0xFBAC0, 0xFBAE0) that
derive globals from it at boot.  The gravity slider rewrites it in
place (`ParametricPatch`), so every reader sees the new g, non-player
falling entities included; that is intended (gravity applies
uniformly).  The jump and flap sliders read the same gravity value
and inject `g × k²` at their own sites (D16).  There is no single
"effective reader": an old claim that 0x85700 was the only one was
wrong.

Reference: `src/azurkit/tools/mods/packs/player_physics.py`'s `GRAVITY`.

## ControllerState struct (XInput polling) — pinned 2026-04-18

Per-player gamepad state lives at `DAT_0037BE98 + player_idx * 0x54`
(up to 4 players).  Populated every frame by the XInput polling loop
`FUN_000a2df0 → FUN_000a2880` which calls `XInputGetState` and
normalises the raw XInput fields into floats:

| Offset | Type | Field |
|:--|:--|:--|
| 0x00 | f32 | left_stick_x (sThumbLX normalised to [-1, 1]) |
| 0x04 | f32 | left_stick_y |
| 0x08 | f32 | right_stick_x |
| 0x0C | f32 | right_stick_y |
| 0x10 | f32 | dpad_x: +1 right (wButtons 0x08), -1 left (0x04), 0 |
| 0x14 | f32 | dpad_y: +1 up (0x01), -1 down (0x02), 0 |
| 0x18..0x34 | f32 × 8 | button_a, button_b, button_x, button_y, button_black, button_white, trigger_left, trigger_right (analog 0..1) |
| 0x38 | f32 | stick_left_click (digital 0 / 1) |
| 0x3C | f32 | stick_right_click |
| 0x40 | f32 | start_button |
| 0x44 | f32 | back_button |
| 0x48..0x53 | u8 × 12 | edge_state[] — latches that the polling loop clears when the corresponding button returns to 0.0, so the engine can implement "consume rising edge once per press" |

Active-player index at `DAT_001A7AE4` (0..3, or 4 = "no controller").
Stick dead zone is raw-unit ±12000 of centre.  Analog-button dead zone is raw-unit 30.

Declared as `ControllerState` in `devkit/re/data/structs.h`, with
`_Static_assert`s pinning every late field, and in the
`azurik_vanilla.h` shimkit writes for every shim.  The D-pad axes are
read off 0xA2B75–0xA2BA9 [verified 2026-10-11: capstone]; the two
names were swapped until Step 4.41a (AZ-234).
`tests/test_re_shims.py::test_the_structures_a_shim_or_the_re_data_declares_hold_each_field_at_ghidras_offset`
compiles each field's offset by name against both headers.

Reference: `FUN_000a2880` decomp (the XInput-write side of the
polling loop) — each `DAT_0037be{9c,a0,a4,a8,ac,b0...}` target maps
1:1 to a struct field in this table.

## History

Until REORG_PLAN Step 3.3d (2026-10-10) these notes were sections of
`docs/LEARNINGS.md`; `git log -- docs/LEARNINGS.md` shows their
earlier history.
