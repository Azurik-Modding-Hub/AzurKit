---
name: azurik-game-reference
description: >-
  Reverse-engineering index for Azurik's player movement and armor: the
  function map with ABIs and VAs, entity offsets, the jump, flap and gravity
  math with measured vanilla numbers, config.xbr's armor tables, and patches
  whose bytes landed with no in-game effect. Load before writing or
  debugging a mod, shim, slider or behavior test on jump, gravity, flaps,
  air control, walk or swim speed, roll, fuel, shields, HP, damage, death,
  ledges or dt. Triggers: "what VA / offset", "entity +0x field",
  PlayerInputState, armor_mgr, peak_z, "dt 1/30 vs 1/60", "my patch landed
  but nothing changed in game".
---

# Azurik game reference: player movement, armor, and patches that did nothing

The reverse-engineering facts you need before a movement mod or a behavior
test. Ground truth is the vanilla USA `default.xbe` (md5
`ae67bd444260be00be48ee3567997baa`, read from the USA image); every VA
here is the USA build's (Europe's are its facts' address map, `addresses`
in `src/azurkit/core/facts.europe.json`).

Source tags: **[spike]** = the 2026-10-08 Unicorn/xemu spike; **[xemu sN]**
= measured in game by sandboxed xemu session N (its report is in the
private evidence folder; s6's REPORT section where named);
**[inferred]** = reasoning only. Untagged facts are static reads (capstone
over the vanilla XBE) or L2 runs. A call site is the CALL instruction
(`python -m devkit re xbe calls --to <VA>`); s6's captures name a breakpoint's caller
by its return address, the instruction after the CALL.

**Paths.** This reference came from Modkit, the toolkit AzurKit was ported
from and replaced (its history is the private archived repository, AGENTS.md
§ Porting from Modkit). A test, header or module it names that AzurKit lacks
(`vanilla_symbols.py`, `shims/include/…`, a `tests/test_*.py` not in
`tests/`) names Modkit's tree, where the finding was made: Modkit's
`azurik.h` is `devkit/re/data/structs.h` and `anchors.toml`, its
`azurik_vanilla.h` the one shimkit writes from the facts, and its verbs
`python -m devkit AREA VERB` (`devkit/README.md`).
AzurKit's homes today: the callable functions, their ABIs and every patch
site are the facts (`src/azurkit/core/facts.<release>.json`, whose
`functions` shimkit writes into `azurik_vanilla.h`); the packs are
`src/azurkit/tools/mods/packs/` (`player_physics.py`, `fps_unlock.py`,
`air_shield_flaps.py`, `player_max_hp.py`); config.xbr's tables are read
by `src/azurkit/core/xbr/keyed.py`; the prologue drift guard is
`tests/test_shims.py`.

D961 (Modkit's D153): game assets and snippets may go in the repo; the ISO
may not, and game bytes are never printed in logs or chat.

## When NOT to use this skill

- Writing, applying or verifying a pack, slider or C shim: AGENTS.md's Packs (its "Patching and shims: what binds") and `docs/SHIMS.md`.
- Measuring in xemu (gdbstub, input pipe, snapshots): `azurik-xemu-oracle`.
- Ghidra or the MCP server: `azurik-ghidra-mcp`. Setup and Python version: `azurik-dev-environment`.
- The `.xbr` byte format or authoring an XBR pack: `docs/XBR_FORMAT.md` (its § "Packs and mods files that edit `.xbr` files").
- Fixing a confirmed bug: the issue ledger (`$EV/tools/ledger`) and AGENTS.md § Commits and landing.
- Test tiers, the simulator design or the edit contract: AGENTS.md (§ Setup and tests, § The engine's contracts) and `docs/SIMULATOR.md`.
- Fps-unlock internals: `docs/RE_XBE.md` § "FPS unlock" and § "60 FPS patch re-audit (April 2026)", and `src/azurkit/tools/mods/packs/fps_unlock.py`.

## 1. Where the depth lives

| Need | Go to |
|---|---|
| RE narrative per subsystem | `docs/RE_MOVEMENT.md` (movement, armor, fuel, HP, roll, tick rate, gravity, ControllerState), `docs/RE_DATA.md` (config.xbr, prefetch lists, `filelist.txt` and the HDD cache, level loading), `docs/RE_XBE.md` (boot, kernel imports, XBE and COFF layout, cvars, FPS unlock); superseded findings in `docs/Finished/LEARNINGS_HISTORY.md`. Anchors: `grep -n '^#' docs/RE_*.md`. |
| Section map, main loop, fps constants | `docs/RE_XBE.md` § "Decompilation & Analysis" |
| Field and VA `#define`s for shims | `devkit/re/data/structs.h` (Modkit's `azurik.h`): the `AZURIK_ENT_*`, `AZURIK_ARMOR_*` and `AZURIK_LVL_*` macros, the ArmorMgr-chain comment and `ControllerState`; the VA anchors are `devkit/re/data/anchors.toml` |
| Callable vanilla functions and their ABI notes | the facts' `functions` (`src/azurkit/core/facts.usa.json`; the `azurik_vanilla.h` shimkit writes from them) and their notes in `devkit/re/data/function_notes.toml`, under the same names (`player_jump_init`, `wing_flap`, `consume_fuel`, `player_walk_state`, `gravity_integrate_raw`, …) |
| Function and label names (525 / 1,083; no ABIs or bounds), plus 10 structs with sizes and fields | `devkit/re/data/ghidra_snapshot.json` |
| Slider and pack catalogue | `docs/GUIDE.md` § Patches and sliders; code in `src/azurkit/tools/mods/packs/` (`player_physics.py` for movement) |

## 2. Player-movement function map

Isolation ratings are [spike]. "—" means unnamed in `ghidra_snapshot.json`.

| VA | Snapshot name | Calling convention / notes | Isolation [spike] |
|---|---|---|---|
| 0x8C230 | — (per-frame player tick, vtable slot .rdata 0x19BC6C) | ECX = entity; builds a 0x150-byte input struct on its stack; plain RET | HARD as a whole (379 reachable fns, 110 indirect calls) |
| 0x84F90 | `player_input_build` | Reads ControllerState 0x37BE98 + idx·0x54 (idx at 0x1A7AE4). Copies dt from 0x1980A0 into input+0x04 (load 0x85041, store 0x85049) | MEDIUM |
| 0x84940 | `player_input_tick` | plain RET, no callees | EASY |
| 0x8CCC0 | `player_physics_state_machine` | [esp+4] = entity, EAX = input (held in EBP / EDI inside); RET 4. Only direct caller is 0x8C37D | — |
| 0x89060 | `player_jump_init` | ESI = entity, EAX = input; result in AL; plain RET | EASY (4 stubs) |
| 0x83F90 | `player_airborne_reinit` | EAX = armor_mgr in, ECX = &entity+0x140 out; plain RET. Runs once per jump and per flap: its only direct callers are 0x89147 (jump) and 0x89348 (flap) | EASY |
| 0x89300 | `wing_flap` | ESI = entity, [esp+4] = input; RET 4. Only direct caller is 0x8D37A, in the state machine's air case | EASY |
| 0x842D0 | `consume_fuel` | thiscall: ECX = armor_mgr, float cost on the stack; RET 4. Callers 0x89354 (cost 1.0) and 0x893D4 (cost 100.0) | EASY |
| 0x85F50 | `player_walk_state` | EAX = entity, [esp+4] = input; RET 4 | MEDIUM up to its 0x860C8 call, HARD after |
| 0x85700 | `gravity_integrate_raw` | ESI = entity, ECX = input, EDX = &desired velocity, EAX = RVO output, [esp+4] = g; RET 4. Full note in its `vanilla_symbols.py` entry | EASY itself, but calls 0x47380 at 0x857FE |
| 0x88990 / 0x8C7D0 → 0x8C630 | `player_attack_enter` / `player_ground_attack_tick` → `player_attack_root_motion` (the attack-move entry and tick; the roll) | 0x88990: EDI = entity, [esp+4] = input, [esp+8] = new state (0x100 ground, 0x102 air); RET 8; runs the first tick. 0x8C7D0: EDI = input, [esp+4] = entity; RET 4; calls 0x8C630 (entity, input, &heading quaternion; RET 0xC), which hands the root-motion velocity to 0x85700 at 0x8C745 | EASY with 5 stubs (`PlayerSim.roll()`) |
| 0x47380 | — (collide/move) | 836 insns; sweep calls 0x94210/0x944B0. Also holds the ground-acceleration ramp and the landing result, plus 3 fps_unlock sites | HARD |
| 0x89480 | `player_airborne_tick` | EDI = entity, [esp+4] = input; RET 4; reads gravity at 0x8950B | MEDIUM-HARD |
| 0x89A70 / 0x87F80 / 0x8B700 | `player_slope_slide_tick` / `player_climb_tick` / `player_swim_tick` | 0x87F80: EAX = entity, [esp+4] = input; RET 4. 0x8B700 the other way round: **EAX = input, [esp+4] = entity**; RET 4. Its 6 callers: the ground, swim (0x8D1CB), slope, zipline and air cases and the hit's 0x102 (0x8D118, 0x8D1CB, 0x8D221, 0x8D26B, 0x8D2B5, 0x8D35F), not climb (0x8D3A9) or the attack moves (0x100, 0x101). It writes state 6 at 0x8BD35 while the swim gate (input+0x135 & 1) is set and either the depth input+0x14C is at least 0.25 m (0x198110) or the player already swims (`docs/RE_XBE.md`, 0x60BD0's row). State 1 (climb) is written only inside 0x87F80 and 0x88490, and 0x88490's only caller is 0x87F80 (0x88473) | HARD |
| 0x8BDB0 | — (the move-state setter) | EAX = entity, ECX = state, EDI = input (its +0x1C tested at 0x870E1 and 0x8B6C1 [inferred]), [esp+4] = animation, 8 stack dwords in all; RET 0x20; writes +0x94 and +0x16C. Six callers: 0x86920, 0x86DD0, 0x87120, 0x87470, 0x87950, 0x8B1D0 | — |
| 0x8B1D0 | — (the step-up check) | `player_walk_state` calls it at 0x8613E only after a walk-move contact with f32 `[esp+0x1A8]` < 0.8 (`[0x1980CC]`) and the stick pushed (input+0x1C ≠ 0). A return of 1 sets, through 0x8B6C1, state 0x100 with animation 0x35 for 5 rows [xemu s6 §5: only on S4's lip, contact 0.7922; at the vertical face 0.0, returned 0] | — |
| 0x8D600 | — (the player's hit handler, virtual) | ECX = entity, [esp+4] = the message. amount = 0x83FE0(armor_mgr, damage type); then knockback 0x30BD0, animation 0x42750, state **0x102** written directly at 0x8D693, and `apply_damage(critter, HP − amount, 0)` at 0x8D6AF | — |
| 0x44640 | `apply_damage` | stdcall(critter, new absolute HP, flag): clamps to [0, critter+0x214] and writes +0x210; on a > 0 → ≤ 0 change it calls 0x61360 and 0x43FA0 | — |
| 0x8CE77–0x8CF35 | (inside `player_physics_state_machine`) | The per-tick death check: HP ≤ 0 and state ∉ {7, 8} → a death animation and state 7. HP poked to 0 dies on the next tick with no `apply_damage` call [xemu s6 §6] | — |
| 0x42E40 | `anim_apply_translation` | ECX = four floats it copies to anim_obj+0x18C and normalises, 16 stack bytes (RET 0x10), plus EAX (`player_walk_state` sets it at 0x866D2; forwarded to 0x61100), probably a hidden output buffer [inferred] | HARD (needs animation assets) |
| 0x3C700 | `load_armor_properties_config` | Reads `config/armor_properties` through 0xD1420/0xD1520/0xD1630; float→int 0xF5A40. Ran with 7 stubs, including asset lookup 0xA67A0 [spike] | HARD unstubbed |
| 0xA9000 | — (assert handler) | [esp+4] = source file, [esp+8] = line, EDI = expression, EAX = message or 0 (all 125 direct call sites). Never returns: spins Sleep → KeDelayExecutionThread | L2 hooks it (`ProbeError` with file and line) |
| 0x58E40 | — (main loop) | main dt 0x1983E8, rate double 30.0 at 0x1A28C8 | — |

- **State dispatch:** jump table at 0x8D4BC indexed by entity+0x94: 0
  ground 0x8D10C, 1 climb 0x8D3A9, 2 air 0x8D335, 3/4 slope
  0x8D202/0x8D25F, 5 zipline ride 0x8D2A9 (the ride 0x8A510, which it
  calls at 0x8D2E4, is state 5's only writer, at 0x8AB4B; Step 2.121),
  not a prejump, 6 swim 0x8D179, 7/8 dead 0x8D0A9/0x8CFC3. A `true`
  return from a handler ends the frame, so the tick that jumps or flaps
  skips that frame's airborne integration [spike].
- **Stub pop counts** (first-RET scan): 0x42910 `anim_change` 12, 0x42E40
  16, 0x8BE00 `fall_death_dispatch` 4, 0xA5CA0 8, 0xA1C70 16, 0x837A0
  `armor_reset_out_of_fuel` 4, 0x8D4E0 8. The scan fails on noreturn
  0xA9000 (it picks up a neighbour's `ret`).

## 3. Struct fields

**Entity** (ESI/EBP/EDI depending on the function):

| Offset | Meaning |
|---|---|
| +0x20 | Start of the armor chain (the critter; see below) |
| +0x24/+0x28/+0x2C | Velocity x/y/z [spike]. Against an obstacle the x/y field overstates motion (0.376-0.387 m/s read while 0.095 m/s was realized; at a face its y sign flips every tick): measure realized motion from the bbox or the position over windows [xemu s6 §9(e)] |
| +0x30 | A pointer 0x150 bytes into an object with a vtable, not a type (`azurik.h` keeps the misleading name `AZURIK_ENT_TYPE`). The player tick 0x8CCC0 calls the object's vtable+0x88, and with no object it zeroes input+0x60..+0x74 instead (+0x74 is the support vz jump_init adds), so probably the object underfoot [inferred]. 0 or 0x150 (no object) takes jump_init's straight-up path; jump_init never dereferences it |
| +0x38/+0x3C/+0x40 | Position. **It doesn't follow the body in the air:** with no contact it doesn't change at all (also while swimming), and on a contact it jumps to the contact point (a ledge edge, a wall); it holds the last contact point [inferred]. On the ground z = bbox min + 0.5 [xemu s1, s6 §9(b)] |
| +0x60 | Flags (bit0 forces the slope-projection path) |
| +0x68 | Charged-jump height (copied into +0x144) |
| +0x94 | State (§2's jump table). The setter 0x8BDB0's six callers each pass an attack-move state, 0x100 or 0x101; the ground, air and slope changes, the hit handler's 0x102 (13 ticks, then 6 of state 2, then 0) and the death check's 7 are written elsewhere, so a breakpoint on 0x8BDB0 misses them [xemu s6 §5, §6] |
| +0x98 | The previous tick's state [xemu s6] |
| +0x9C | State timer; += dt each tick: 1/30 per tick in vanilla. 0 at takeoff and at landing, not at a flap [xemu s1, s6 §1(d)] |
| +0xB8..+0xC0 | Ground normal. jump_init's slope test uses only nz (+0xC0); the projection then scales v0 by all three |
| +0xD8 | Flap counter. +1 at 0x8937B; zeroed at 0x892E0 (jump), 0x8C182 (landing) and 0x84DF2 (the reset block that also clears peak_z). In game 0 → 5 over a 5-flap jump and 0 at landing; armor_mgr keeps no counter [xemu s6 §1(a)] |
| +0x140 | Air control (9.0, or 12.0 with air power) |
| +0x144 | Jump/flap height h (1.1, or 1.2 with air power) |
| +0x148/+0x14C | Hold-jump timer and its vz [spike]. **+0x148 counts −1/30 per held airborne tick; released in the air it reads 0.0 on the next row; released on the ground it keeps its value** (S1 stands at a stale −0.5667 with air power); after each flap it reads −0.0333 for one held tick, then 0. +0x14C stayed 0.0 in every s6 capture, and without air power holding Y changed nothing in the arc; the cause is [inferred] (the airborne tick clears it on a release; no ground tick does), so REORG_PLAN N3's cause stays open. 0x83F90 zeroes them only without air power; the airborne tick 0x89480 reads +0x148 first [xemu s6 §9(a)] |
| +0x150 | 0 → 1 on the jump tick and stays 1; a level change's new entity starts at 0 (with h 1.1 and air control 9.0) until its first jump. Meaning unknown [xemu s6 §1(d), §2] |
| +0x164 | peak_z. Written only at 0x8915A (z0 + h) and the reset at 0x84E16, so in play **only on the jump tick**: flaps don't re-latch it and landing doesn't reset it. jump_init returns at 0x89078 unless input flag 0x04 or entity+0x60 bit 2 is set, so a standing value is stale (S1 stands at −17.5038). z0 is input+0x5C, which wing_flap also subtracts (0x89381), so both use the input position's frame, the bounding-box centre (z + 1.0 = +0x1A4 + 1.5): 1.3734 = 0.2734 + h at the level-1 start, with jump ×1.5 too [xemu s1, s2, s6 §1(d)] |
| +0x168 | The fall reference (was labelled prev_z): the z a fall counts from. Each floor contact sets it to the floor's z (0x8C17C), so it changes on ground ticks only (19 of 20 ground rows, 0 of 50 airborne) [xemu s6 §1(d)]; −FLT_MAX while no fall counts (0x84E1C, 0x856D8, 0x8972F); `fall_death_dispatch` 0x8BE00 reads it [verified static, Step TD.0; RE_MOVEMENT.md § "Fall damage"]. `obs.Obs.fall_ref` |
| +0x16C | Flags byte; bit 2 rides into gravity_integrate_raw's move request |
| +0x1A4 | Bounding box: the usable position proxy in xemu. +0x19C..+0x1B0 is a 3 m cube, min (x−1.5, y−1.5, z−0.5) to max (x+1.5, y+1.5, z+2.5), centred on z + 1.0; in vanilla at 30 fps it changed on all 28 airborne ticks of s1's jump. Caveats [xemu s6 §9(c)]: it can repeat the previous tick (take the arc's maximum, and check the apex row isn't stale), and in some entities it isn't a box (`vanilla-exit`'s w1 entity, town, and every save-loaded entity hold constants or denormals): check that it moves before using it. In the Training Arena the box doesn't move and position can freeze for 7–15 ticks, then jump, so measure an apex or a roll distance on level 1 or a D98 field state |

**Input struct** (EAX/EDI/stack) [spike]: +0x00 body pointer (the input
builder's copy of entity+0x20) and +0x3C..+0x44 a second copy of the
position, both handed to the move code by 0x85700; +0x04 dt; +0x20 flags
(0x04 jump edge, 0x02 jump held, 0x20 BLACK = the roll, 0x40 the developer
cheat-buttons turbo: R3 or WHITE, built only while the cvar `enable cheat
buttons` is on, 0 in retail; bit 0 = RT, which with the stick pulled back
makes walk_state's full-speed backpedal [xemu s6 §4]; the low byte read
0x80 with Y up, 0x86 on a fresh press and 0x82 while held with the latch
set [xemu s6 §1(d)]); +0xD0 heading quaternion; +0x34 `CritterData*`
(CritterData+0x40 = base walk speed = garret4 `runSpeed` 7.0 from
`config.xbr`, filled by the loader 0x49480; +0x38 = `walkSpeed` 5.0, the
walk→run animation threshold, and more, see below); +0x54..+0x5C position,
the bounding-box centre (x, y, z + 1.0) [xemu s1]; +0x74 support-surface
vz; +0x124 stick magnitude (the keyboard pad's diagonal gives √2, not
clamped [xemu s6]); +0x128..+0x130 direction; +0x134 & 8 selects the slow
air-blend rate. In the swim tick: +0x135 & 1 is the swim gate (an input
flag, not an entity one: 0x8B700 gets the input in EAX), +0x140/+0x144 a
horizontal and +0x148 a vertical offset added to the desired velocity, and
+0x14C reads like a depth [inferred]. Flag 0x04 means "Y held AND latch
ControllerState+0x4B == 0"; wing_flap sets the latch through
`mark_armor_feature_used` 0x846D0, and jump_init sets it itself
(0x890AB–0x890B2) when ControllerState[idx]+0x24, the analog Y, is ≠ 0.
Jump is the **Y** button; A puts the player in state 0x100.

CritterData+0x38 (`walkSpeed`) has five known readers (no complete sweep):
walk_state's walk→run animation threshold (0x86474, 0x864AA); a
horizontal-speed threshold that picks jump_init's animation (0x89216: 0xF
above it, 0x10 below, 0x14 from state 1); a speed test in the ground attack
starter 0x88A80 (0x88C14); the **vertical swim speed**, the FMUL at 0x8B8C5
in player_swim_tick (its up/down term, max X/Y/WHITE − max A/B/BLACK, times
walkSpeed), which `swim_speed_scale` (the stroke FMUL at 0x8B7BF) doesn't
touch; and AI code at 0x361F7 (`docs/RE_MOVEMENT.md` "`CritterData.walkSpeed`
and `runSpeed` are live, not dead data"). s6 read CritterData +0x38 = 5.0
and +0x40 = 7.0 on all 940 rows of its V11 captures [xemu s6 §7].
walk_state's animation choice [xemu s6 §4]: idle 1 at or below
0.1·`walkSpeed` with no stick, walk 8 at or below `walkSpeed`, run 9 above
it (so 5.0 is the walk/run threshold at stick 5/7), and 13/14 the same with
the RT flag and the stick back; the index is critter+0x200. Poking
`walkSpeed` 5.0 → 10.0 changed only the animation, not the speed.

**Critter** = `[entity+0x20]`: +0x178 species (`CritterData*`, the same
pointer as input+0x34); +0x200 the animation index [xemu s6]; **+0x210
current HP, +0x214 max HP** (int32). The player's come from the inventory
`hlth` slot (inv+0x88/+0x8C), set from `settings_foo` `initial hp` at a new
game (0x57B70) and on every game start/continue (0x532A7); the HUD bar's
length is max / `settings_foo` `max hp` (400) and its fill current / `max
hp`, so vanilla's 200/200 is a half-length bar, full [xemu s3]. A
`starting_hp` 777 build starts a new game at (777, 777) [xemu s3];
`starting_hp` 1 starts at (1, 1), and the player stays alive and
controllable; `health_bar_full_scale` 50 (200/50 = 4.0) draws a full tube
that doesn't overflow [xemu s4]. `docs/RE_MOVEMENT.md` "Player HP comes from
settings_foo `initial hp`, not garret4 `hitPoints`". What s6 measured
(REPORT §2, §6):
- **A level change** carries current and max HP over unchanged (185/400
  both ways; 321/456, above `max hp`, too): at the exit 0x54327 (in
  0x542E0) copies critter+0x210/+0x214 into the slot, the next spawn
  copies the slot into its params (0x53F05–0x53F1E) and critter init
  0x409C0 writes them (0x409F1/0x40A0D); 0x532A7 and 0x52AAE don't run
  (0x52AAE is in 0x52A50, whose only direct caller is 0x5620D; the event
  that takes it is unmeasured). **The slot is stale mid-level** (200/400
  while the critter had 185/400) until an exit syncs it. armor_mgr and the
  slot outlive a level; the entity and the critter are rebuilt.
- **A continue or a menu load sets current HP to `initial hp`**:
  `game_start_setup` 0x52F50 (the CALL at 0x55C9E for the continue,
  0x56672 for the menu load) runs the save load 0x58BD0 (at 0x530A6), then
  0x532A7 writes round(`initial hp`) = 200 over the save's value, and
  critter init writes 200 (captured for the menu load; for the continue
  seen live, not captured). Critter init doesn't clamp current to max (a
  negative param takes species+0x14), so a max below `initial hp` spawns
  over it [inferred].
- **Damage:** a `blaze` hit costs a fixed 25 whatever the current HP or
  max (all 14 player `apply_damage` calls across 9 captures pass HP − 25);
  the type is index 41 of the table at `[0x38C364]` (that it is `blaze`'s
  Damage 25.0 row is [inferred]). A hit knocks the player back (v =
  (5.777, 2.414, 3.130)) in state 0x102 (§2's 0x8D600).
- **Death needs no hit:** any tick with HP ≤ 0 sets state 7 (§2's
  0x8CE77). So `starting_hp` 0 (−0.5…0.5) gives 0 HP and death at once (a
  build at 0: its third tick, xemu p9); only values below −0.5 fall back to
  garret4 `hitPoints` (a build at −5 played at 200/400, p9). After a death
  a dialog offers "Continue (A)", and the continue sets HP to `initial hp`
  again, so a `starting_hp` that rounds to 0 dies on every continue (p9:
  0.24 s after it; Q253: documented, no warning).
- **The HUD's `max hp` cache** is the f64 at 0x1AAA50, with its flag byte
  at 0x1AAA4C; 0x1AAA48 is the lookup record naming `max hp` (read 400.0,
  flag 1). The bar is recomputed only when max HP rises (0x1A596–0x1A5A1).
  Writing 0.0 there drew a full-length, all-red tube and −400.0 drew no
  tube (s6, a RAM stand-in); builds of `health_bar_full_scale` 0 and −400
  did the same (p9).

**Armor chain**: entity+0x20 → +0x154 → +0xCC = `armor_mgr`;
armor_mgr+0x20 → level struct (the equipped armor slot), armor_mgr+0x24 =
fuel (float); level+0x08 = the slot's Level (no_armor_1 = 1); level+0x38 =
Flaps (also the fuel divisor; no_armor_1 = 0). Air power needs Level 1–3
**and** Flaps ≠ 0 (§4 "Air control"). `azurik.h`'s ArmorMgr-chain comment
and `AZURIK_LVL_*` offsets are correct (0x83F90 first loads [eax+0x20]).
Per-slot array at 0x38C4D4 (`RE_MOVEMENT.md` "Flap count lives in
armor_properties[level][0xE]").

**Globals:**

| VA | Meaning |
|---|---|
| 0x1980A0 | f32 1/30, the player dt source. fps_unlock rewrites it to 1/60 (entry `character_fsm`). Shims read dt from input+0x04 and never hard-code `AZURIK_SIM_DT_SECONDS_F32` |
| 0x1980A8 | f32 9.8 gravity. 16 raw refs in .text. 0x85700 does NOT read it: g arrives as an argument |
| 0x198704, 0x198740 | Two more 9.8 floats. Not what jump, flap or the airborne tick read |
| 0x198598 | 0.70709997, the jump-slope threshold |
| 0x37BE98 | ControllerState[4], stride 0x54 (snapshot label `g_controller_state`) |
| 0x1A7AE4 | Active controller index (0–3, 4 = none; 4 is its value in the XBE, and 4 reads ControllerState[0]). NOT the air-power level |
| 0x1A25B4 | f32 10.0, the swim stroke's target speed (the FMUL at 0x8B7BF, `swim_speed_scale`'s site). 11 disp32 readers: 10 in `.text` (0x2F136, 0x2F166, 0x2FF5E, 0x47B51 inside the move code 0x47380, 0x71424, 0x814F4, 0x81598, 0x8297D, 0x85CB6, 0x8B7BF) and 1 in DSOUND (0x13A84B), so the slider redirects its FMUL instead of editing the constant |
| 0x1A25B8 | f32 6.0, the descent-flap threshold (`FCOMP` at 0x893C0; snapshot label `g_flap_subsequent_threshold_6m`) |
| 0x1AAA48 / 0x1AAA4C / 0x1AAA50 | The HUD's `max hp` lookup record (it points at the name) / the cache's flag byte / the cached f64 (400.0 in vanilla) [xemu s6 §6] |
| 0x1989C8 | f32 1/30, Balthazar's AI tick time (readers 0x273B6 and 0x27407, both in his think 0x273B0); fps_unlock's `balthazar_ai_tick` entry rewrites it to 1/60 |
| 0x38CA80 / 0x38CA70 / 0x38CA68 | The cvar records `enable cheat buttons` / `enable debug camera` / `enable snapshot`, all default 0, value at record+4 (`RE_XBE.md` § "CVar layout"). 0xFFFC0/0xFFFD0/0xFFFE0 are atexit thunks, not getters |

**x87 control word: 0x023F** (53-bit precision, round-to-nearest, all exceptions masked).
- The game calls `_controlfp(_PC_53, _MCW_PC)` at 0x59684 (helper 0xEBE3E), and the CRT does the same at 0xF0E1F.
- Every xemu dump read 0x023F [xemu s1, s4].
- The CRT math helpers compare against 0x27F (0xED713) and take a reload path otherwise. Results are identical [spike].

## 4. Movement math and measured vanilla numbers

**Jump** (0x89160): `FLD [0x1980A8]` × h, ×2, FSQRT, so v0 = √(2gh).
- h = 1.1 → **v0 = 4.6433**. Unicorn and xemu agree bit-for-bit: 4.643274784088135.
- h = 1.2 (air power) → **4.8497**; charged h = 3 → 7.6681 [spike].
- Slope projection runs only when +0x30 ∉ {0, 0x150}, (+0x60 bit0 set, or nz ≤ 0.70709997), and a local flag in BL is 0. Otherwise vz = input+0x74 + v0. A 45° slope gives 3.2833 [spike].

**Integration** [spike; xemu s1, s2]: semi-implicit Euler inside 0x85700, vz −= g·dt.
- The discrete apex is about v0²/2g − v0·dt/2: **1.0235 m at 30 Hz** and **1.0616 m at 60 Hz**, not h.
- In vanilla at 30 Hz xemu measured exactly the model: v0 4.6432748, Δvz −0.326667 per tick (9.8/30), 28 airborne ticks, apex 1.0235 m on +0x1A4 [xemu s1, and s6 outside the arena, tapped or held alike]. A `gravity` 4.9, `jump_speed_scale` 1.5 build reached an apex of 2.3933 m (60 airborne ticks), the model's 2.393270 (k²h = 2.475 is the continuous value) [xemu s2].
- With air power (S1, h 1.2) v0 is 4.849742, 29 airborne ticks, apex 1.1199 m on a sloped beach [xemu s6].
- The spike's dev snapshot (60 Hz) gave about 1.06 m, with Δvz = −0.16333 per tick.

**Gravity slider** [spike]: with jump scale 1.0, G = 4.9 gives v0 = 3.2833 (×0.7071) and the same apex; G only changes airtime. The jump and flap sliders k inject G·k² from the same gravity value (D16), so the closed-form height is k²·h at every G and k: 1.1 for a jump, 1.2 for a flap with air power (`test_gravity_composes_with_jump_and_flap`). At G = 0 a jump launches at 0.

**Wing flap** (0x89300; measured numbers [spike], then [xemu s6]):
- v0f = √(2g·min(max(peak_z + h − z, 0), h)), with z = input+0x5C. The gravity FLD is at 0x893AE.
- v0f is halved (×0.5 at 0x893DD) on a **descent flap**: d = peak_z + h − input+0x5C > 6.0 (`FCOMP [0x1A25B8]` at 0x893C0), i.e. the input z more than 6 − 2h = 3.6 m below takeoff at h 1.2. A flap after the apex of an ordinary jump never qualifies; a late flap on a long downhill fall does (s6: d 6.7979, vz −11.337715 + 1.5·2.424871 = −7.700408, measured exactly) [xemu s6 §1(c)].
- All 5 flaps of S1's 5-flap jump fit the model and the vz rule below; the highest point was 2.3819 m above takeoff, under the cap z0 + 2h = 2.4 [xemu s6 §1(a)].
- New vz = min(v0f, vz + 1.5·v0f); the 1.5 is at 0x893EB.
- peak_z is latched once per jump, so the vanilla altitude cap is about z0 + 2h. Flaps buy distance, not height.
- **`jump_speed_scale` k doesn't move the latch** (Q228, D93): peak_z stays z0 + h, but a jump with k > √2 rises past z0 + 2h. A flap up there has no lift (v0f = 0, so the new vz is min(0, vz)): it stops a rising player, leaves a falling one falling, and still spends a flap and its fuel (L2). Pair the jump slider with `wing_flap_ceiling_scale` K ≥ k² − 1, which moves the cap to z0 + (K + 1)h ≥ z0 + k²h (L2: k = 1.5, K = 1.25 gives √(2g·0.2) = 1.9799 at z0 + 2.5 m and 0 at z0 + 2.7 m).
- `wing_flap_ceiling_scale` K latches peak_z = z0 + K·h, so the cap becomes z0 + (K + 1)h: hovering half a height under it (1.5h vanilla, 3.5h at K = 3), a flap gets √(g·h) = 3.4293 (`test_flap_ceiling_lifts_above_vanilla_ceiling`).
- Measured: full-budget flap vz 4.8497; far below peak 2.4249.
- The next tick's airborne code leaves vz alone (its air blend targets vz itself) and 0x85700 hands the move code vz − g·dt: 4.5231 after a full flap at 1/30 (L2).

**Flap gating:**
- Input flag 0x04 is tested first (0x89308). Flaps = 0 refuses silently.
- The counter check at 0x89328 compares +0xD8 against level+0x38. Over the limit, it calls 0x837A0 and refuses.
- `consume_fuel` refuses only with no slot, Flaps 0 or a gauge of exactly 0; it subtracts cost / Flaps from the 1.0 gauge; under half a step left it empties the gauge and calls 0x837A0, and still returns 1. Each flap calls `consume_fuel(1.0)` (the CALL at 0x89354); a refusal stops the flap. A plain jump spends nothing [xemu s6]. A descent flap also calls `consume_fuel(100.0)` (0x893D4) and ignores its result.
- **Spending the gauge's last step drops the shield** [xemu s6 §1]: in vanilla the 5th flap of a 5-flap shield (gauge 1.0 → 0.8 → … → 0.2 → 0.0) runs `consume_fuel(1.0)` at gauge 0.2, which zeroes the gauge and calls 0x837A0 itself (the CALL at 0x8431E). The slot becomes the no-armor slot (Level 3 → 1, Flaps 5 → 0); that flap still lifts (AL 1), the next jump is plain (v0 4.643275, h 1.1) and its flap presses are refused silently. The wings and the fuel tube vanish.
- **The descent flap drops it too** [xemu s6 §1(c)]: at the vanilla scale `consume_fuel(100.0)` drains the whole gauge and calls 0x837A0; the flap still lifts at half v0f. Lower `flap_descent_fuel_cost_scale` values drop it only when the drain empties the gauge [inferred].
- **Air power doesn't need the gauge** [xemu s6]: with the gauge poked to 0.0 and the shield on, a jump still gets h 1.2 and air control 12.0 (0x83F90 tests only Level and Flaps); each held tick of a refused flap calls 0x83F90 and `consume_fuel(1.0)` (AL 0), 0x837A0 is never called, and the shield stays.
- **No refill found in play.** The only refill the spike found sets fuel = 1.0 at 0x83BC3 (armor equip; scan limited to 0x82000–0x84A00). A gauge is Flaps flaps in total across jumps: landing resets the counter +0xD8 but not the gauge [xemu s1, s6: no refill on landing, over 30 s of ground ticks or across a level change; the gauge and shield carry over a level change both ways]. The armor tick 0x83D80 only drains, by 1/30 ÷ level+0x34 per tick when level+0x34 ≠ 0 [inferred from its decompile]; the loader gives level+0x34 = 0 for all three air shields (5/10/20 only for light_armor_1-3). Still unmeasured: a refill through a real equip or re-cast (0x83BC3), a pickup or a save platform (REORG_PLAN N7, Q124).
- A press past the cap calls `armor_reset_out_of_fuel` 0x837A0 before refusing; it swaps in the level-1 slot of the config's default "Armor" type and zeroes the gauge (in game the no-armor slot, Level 1, Flaps 0). Vanilla never reaches it with gauge left; with `flap_entry_fuel_cost` 0 it does, and **in game the press drops the shield and empties the gauge** (5 flaps keep the gauge at 1.0, the 6th press takes 0x89330 → 0x837A0, the gauge goes 1.0 → 0.0 and the next jump is plain) [xemu s6 §1(b); Q123 closed]. Ten flaps over two jumps, never past the cap, kept the gauge, the slot, Level 3 and Flaps 5.

**Air control:** 0x83F90 writes 12.0/1.2 when level+0x38 ≠ 0 and level+0x08 ∈ [1, 3], and 9.0/1.1 otherwise. A charged (+0x68 ≠ 0) or zipline (state 5) takeoff (0x890F9) skips 0x83F90 and keeps jump_init's own 9.0 (imm32s at 0x890EA, 0x89126), even with air power; air_control ×2 gives 18/24 and 18 there (L2).

**Airborne horizontal velocity** [spike]: an exponential blend, not a constant speed.
- v = target + (v_old − target)·rate^dt, with target = +0x140 × stick.
- rate = 0.6/s (factor 0.983117 at 1/30), or 0.3/s when input+0x134 & 8 (factor 0.960662).
- It goes through CRT pow 0xED6E8.
- Constant-speed reach models overestimate by 1.3–1.5× with a run-up.

**Roll** (`tests/test_roll.py`; the roll research of 2026-10-09):
- BLACK starts the attack move `roll forward`: config.xbr `attacks_anims` entry 20 (TOC entry 2, offset 0x4000), Rate 1.5, Move start/end1/end2 0.1/0.9/1.0. 0x7F1F0 sets entity+0x134 = 20 and copies the record to entity+0xDC; 0x88990 enters state 0x100.
- Distance is root motion: each tick 0x8C630 hands `R(heading) · (m_feet(t + Rate·dt) − m_feet(t)) · [0x1A2650]` (30.0; 60.0 under fps_unlock) to 0x85700 at the CALL at 0x8C745. 0x42E40 runs after the move and only places the model.
- On L2's fake root track the roll lasts 21 ticks, as in game: L2 follows the active animation layer n = [anim+0x10] (the flags at anim+0x48 + 0x40·n, the clip at anim+0x44 + 0x40·n) and uses the game's roll clip length, 1.1666666 s. Under fps_unlock it is unmeasured. `roll_speed_scale` k gives ×k horizontal displacement in the same ticks, z and other moves unchanged.
- In game, 30 fps, flat ground: 21 ticks of state 0x100 from every start, vanilla 3.387 m from standing [xemu s1; s6 3.375 m]. The move code 0x47380 caps ground acceleration at about 3.27 m/s per tick, so the speed is ×k only from the 5th tick: k = 2 rolls ×1.838 **from standing** (a built k = 2 ISO: 6.2259 m against 3.3866 m [xemu s2]), k = 0.5 ×0.524, k = 0 in place, k = −1 reversed; jab and sweep unchanged. Down a slope from the level-1 start, 5.3666 m against 3.3867 m (×1.585, ending airborne) [xemu s2]. From a 7 m/s run there is no ramp (Σ v·dt 3.55038 m) and k = 2 gives **×1.957** (emulated at 0x85700) [xemu s6 §4, §7]. The stick isn't read during 0x100 and walk_state doesn't run. **Deceleration is capped too:** a walk release loses 3.268 m/s per tick and the k = 2 roll's tail exactly 2.9665. Against an obstacle the speed drops to about 0.06-0.51 m/s, but the state stays 0x100 for the full 21 ticks [incidental].
- Not yet seen: 60 fps (Q159), a controlled wall roll, the air roll, a k = 2 roll on a slope in S1.
- **The sample and other bodies** (X4): the `m_feet` sample is `0xCACD0` (`anim_root_motion_delta`: EDI = clip, ESI = `float out[3]`, anim object, node name, t0, t1 on the stack, RET 0x10, EAX = out), called only at 0x8C6AE; 0x8C630's entity is then at [ESP + 0x1B4]. garret4's `roll_forward` moves `m_feet` only forward (component 1), 3.5326 m over the roll's 0.1–1.0 window; no other body's roll clip moves it, so a swapped model (`--player-character`) without X4 rolls 0.003–0.005 m. The X4 shim at 0x8C6AE returns garret4's motion over the same clip fraction; under L2 a flicken build rolls 3.5326 m in 14 ticks, and in game 2.75 m from standing and 2.98 m from a run (the seven swapped bodies 2.75–3.09 m, garret4 3.05–3.07 m) [xemu sittings modelswap, modelswap2].

**Walk** [xemu s6 §4]:
- Velocity handed to 0x85700 = **7.0 × stick**, i.e. `runSpeed` × stick: in game 7.00009 m/s at full stick, 3.50016 at 0.5 (walk animation) and 5.25012 at 0.75 (run). `walkSpeed` sets no speed, only the animation (§3 "Input struct"). LT, WHITE, L3 and RT with the stick forward change nothing; RT with the stick back is a full-speed backpedal (animation 14, no turn). The 7.0 is CritterData+0x40: garret4 `runSpeed` in config.xbr `critters_critter_data` (double at file 0xCEF4), filled by the loader 0x49480. `runSpeed` 14.0 walks at 14.000 m/s [xemu s3]; the walk slider's k = 0.5 build walks at 3.49998 m/s [xemu s4].
- On a slope the vector is projected, (0, 5.6, 4.2), with the magnitude kept.
- **The ramp from rest is 2 sub-target ticks** on flat ground in vanilla: 3.26691, 6.53610, then 7.00009; the stop is 7.00009 → 3.73227 → 0.46353 → 0 (so deceleration is capped as well). The desired speed is 7.0 from the first stick tick, so the ramp is inside 0x85700/0x47380. The ramp mostly gains 3.2667 m/s per tick, sometimes more (`runSpeed` 14.0 went 3.2667, 6.5334, 10.357, 13.623, then 14.0 [xemu s3]); session 3's unpoked vanilla run in the arena went 3.866 then 7.0, and why the arena differs is unproven.
- **The `walk_speed_scale` slider sets that cell to k × 7.0 (D53)** and writes no XBE byte; k = 1 writes nothing. Its build with k = 2 has the same `config.xbr` (sha256 `1ec7b64b…553183`) as xemu's runSpeed-14 ISO. Garret4 is the player's species, so the other +0x40 readers (slope-slide animation rate 0x89C19, AI 0x30259 / 0x346FA / 0x37E88) see it too [unmeasured]. The walk code reads the player entity's own CritterData row (`[EBP+0x34]`), and the player stays species garret4 whatever body `randomize-full --player-character` dresses it in (D112), so the slider sets the player's walk with any model.

**Swim** (state 6, `player_swim_tick` 0x8B700) [xemu s6 §3, S2 `vanilla-ocean`]:
- The stroke is the stick magnitude input+0x124 × `FMUL [0x1A25B4]` (10.0) at 0x8B7BF, once per swim tick: **a target speed in m/s, not a distance per frame**. Desired horizontal velocity = (input+0x128, +0x12C)·stroke + (input+0x140, +0x144); desired vertical = (max(X, Y, WHITE) − max(A, B, BLACK))·`walkSpeed` + input+0x148. Then v = desired + (v_old − desired)·0.1^dt per component (0.926119 per tick at 1/30: 90 % in 1 s), handed to the move code 0x47380.
- Measured: v_h = 10·(1 − 0.1^(n/30)) within 1.1e-6 (0.73881 at n = 1, 9.000 at 30, 9.990 at 90; the asymptote 10.000 m/s, τ 0.434 s); after a release v decays ×0.926119 per tick. A dives toward −5.0 m/s and X rises toward +5.0 (±`walkSpeed`), which `swim_speed_scale` doesn't touch.
- `swim_speed_scale` k, emulated by a RAM poke of its own redirect (the FMUL's disp32 at 0x8B7C1 pointed at 10·k in `.text`'s tail padding): speed ∝ k on every held tick, the time constant unchanged; a built ISO wasn't booted. The redirect is the right design: 0x1A25B4 has 10 other readers (§3 "Globals").
- The swim case calls 0x837A0 once per swim tick (99/99); whether that drops a worn armor is unmeasured (S2 wears none).

**Ledges and the step-up** [xemu s6 §5, S4 `vanilla-wall`]:
- S4's ledge top is 1.2578 m above the floor, 0.2343 m above the plain apex. **No grab, hang or climb state** in 28 captures: state 1 never appeared, 0x87F80 and 0x88490 never ran, and the air checks 0x86920, 0x87120 and 0x87470 always returned 0. That FUN_00088490 grabs ledges is unproven: its only caller is `player_climb_tick` (§2).
- A running jump from 0.89-3.69 m before the blocked spot mounts the ledge with **no state change** (0 → 2 → 0 on the top): at the edge vz rises well above the request (e.g. 1.0499 → 3.7414) and the horizontal speed drops. The lift is applied after the move code returns, outside the player tick; which code applies it is [inferred]. From 4.39 m or more the lift is too small and the body slides down the face.
- At 0.65 m the body lands on the lip and the step-up 0x8B1D0 sets state 0x100 with animation 0x35 for 5 ticks (§2). At 0.42 m or less, or standing at the face, the body hits the face low, slides up it, spends 4–6 ticks in state 3 on the lip and slides back to the floor.

**Vanilla Flaps**: 1/2/5 for air shields 1/2/3 (config.xbr). With `air_shield_flaps` at 3/7/12, the game's own loader plus the real `wing_flap` allow exactly 3/7/12 (L2). From vanilla `config.xbr` the loader builds 19 slots, `no_armor_1` first.

## 5. config.xbr armor tables

Section labels are config.xbr's own table names (`KEYED_SECTION_OFFSETS` in
`src/azurkit/core/xbr/keyed.py`; full list in `docs/XBR_FORMAT.md` § "Table
names"; all 18 checked by `tests/test_xbr_sections.py`). Old labels (before
AZ-113 every label was shifted one table) aren't aliased and have no
migrator (D43). Every TOC reader uses the engine's layout (entry k at 0x3C +
16k: offset from `header[0x10]`, size, fourcc, flags;
`src/azurkit/core/xbr/nodes.py`), so `attacks_anims` is entry 2 and
`critters_critter_data` entry 4.

| Section | TOC offset (payload) | Engine use |
|---|---|---|
| `armor_properties` | 0x2000 (0x3000; `RE_MOVEMENT.md`'s "0x3000 table") | Loaded by 0x3C700 as `config/armor_properties` |
| `attacks_anims` | 0x4000 (0x5000) | The attack animations (`roll forward` is entry 20); `config/attacks_anims` is referenced at 0x7E301 (§4 Roll) |

- **Rows** (`load_all_tables`): Name, Type, Level, Strong/Weak vs, Strong/Normal protection, Strong/Normal protection hp, Cost, Hits, Time, Flaps, Features; each armor (`no_armor_1`, …, `air_shield_1..3`, …) is a column. There is no `fuel_max` row.
- **Flaps conversion**: the cell is a double. 0xF5A40 truncates it toward zero (2.7 gives 2, -2.7 gives -2) into slot+0x38, which wing_flap reads at 0x89321; a value int32 can't hold wraps (3e9 gave -1294967296), so `air_shield_flaps` refuses one (D73; `tests/test_flaps.py`).
- **Vanilla air shields 1/2/3**: Level 1/2/3, Flaps 1/2/5. Shield 3 also has Cost 4.0, protections 0.25 and hp 40.
- **Editing hazards:**
  - Duplicate column names: an edit without a column index (`col`) lands on the last match.
  - Interned strings: the three earth armors share one `Type` string, so a text `set` refuses to rewrite it in place (it may point the cell at another string its table holds; `docs/XBR_FORMAT.md`).
  - config-mod refuses any cell but a type-1 (double). Every config-mod shape names cells by config.xbr's own table / column (row-0 name) / row names through `Table.find` (`src/azurkit/core/xbr/keyed.py`; aliases: case, `_` = space, `color_r/g/b` = R/G/B); the old registry's names fail by name (`src/azurkit/edits/modkit_retired.json`, D50, D72).
- **Edits are planned writes**: an `xbr` operation or a config.xbr slider is the writes `[(offset, bytes)]` that make it, planned against the vanilla file as parsed (`src/azurkit/core/xbr/edits.py`), and a layer applies them; nothing edits a file in place (Modkit's pipeline swapped a new bytearray into its `xbr_files` dict instead).
- **Balthazar's adaptive armor is AI code, not an `armor_properties` row** (the Balthazar armor study of 2026-10-12: a static read and 13 xemu runs). His `critters_engine` row has `ai` = `balthazar`: vtable 0x1A0C3C (think 0x273B0, hit handler 0x279B0, state machine 0x27530); the AI object is `[critter+0x180]`, and its +0x20 points back at the critter.
  - **AI fields:** +0x164 the current armor and +0x168 the desired one (−1 none, 0 air, 1 water, 2 fire, 3 earth); +0x16C the switch timer in seconds (3.0 at first; the think subtracts 0x1989C8 each AI tick); +0x158 the armor fx handle.
  - **Armor groups** (mapper 0x272E0, on the fourcc of the staff power the player has *selected*, `armor_mgr`+0x18, polled every AI tick): `wind` and `litn` air; `watr` and `ice` water; `fire` and `stem` fire; `smsh` and `acid` earth; anything else (`norm`, `elem`, …) none.
  - **The switch and the block:** a damaging hit zeroes the timer; he then takes the desired group (the shield clip, the fx and the commit at 58 % of it) and blocks every hit of that group with no damage and a laugh. In xemu he switched about 2.0–2.8 s after a damaging hit and blocked 19 of 19 same-group contacts while the other groups landed 74 of 74; plain staff and EAFW (`elem`) are never blocked.
  - An empty `critters_damage` cell takes the damage type's base `Damage` (the default `config_cell_value` returns). The final boss, spideyzar, uses the same scheme (vtable 0x1A08C4) [partial].

## 6. Bytes landed, no in-game effect: the catalogue

Common lesson: test the value where the game **consumes** it, not where you patched it.

For XBR-side results there is a second suspect: the game plays its HDD-cached copy of a file whose `filelist.txt` line is unchanged (`docs/RE_DATA.md` § "filelist.txt — the integrity manifest and the HDD-cache key"). Every build now rewrites the line of each file it changes; an XBR null result tested before 2026-10-09 may have been that cache [inferred]; re-test it with a current build.

| # | Attempt | Why it did nothing | Status |
|---|---|---|---|
| 1 | Jump v1: five 9.0 imm32 writes (0x84ED3, 0x856D4, 0x890EA, 0x89126, 0x8D322) | Those set air control (+0x140), not jump speed | Fixed by the FLD at 0x89160 |
| 2 | Flap v1: `FADD [0x1A25C0]` at 0x896EA | A boost in the airborne tick behind input flag 0x40, the cheat-buttons flag never built in retail. wing_flap never reads 0x1A25C0 | Fixed by the FLD at 0x893AE |
| 3 | config.xbr `walkSpeed`/`runSpeed` | Thought dead; **both are live**. `runSpeed` (CritterData+0x40) is the walk base; `walkSpeed` (+0x38) is the walk→run animation threshold, two more speed tests and the vertical swim speed (§3). The old null result: the slider wrote the mislabelled table (AZ-113), or wrote `walkSpeed`, or a warm HDD cache (AZ-112) | The walk slider sets `runSpeed` (D53); seen in game at k = 2 and 0.5 [xemu s3, s4] |
| 4 | Air control v1 (the five static sites only) | 0x83F90 rewrites +0x140 on every jump and flap | Fixed (`RE_MOVEMENT.md` "Air-control speed has TWO dominant writer sites") |
| 5 | Roll v1–v4 (FMUL at 0x849E4, v2 forcing flag 0x40, v3's slope-slide constant 0x1AAB68), `root_motion_roll` shim at 0x866D9 | The roll is BLACK's attack move `roll forward` (state 0x100), driven by root motion in 0x8C630. The 0x849E4 FMUL is the cheat-buttons turbo and scales stick magnitude, which the roll never reads; 0x866D9 wraps walk_state, which state 0x100 never runs | Fixed (D29): a 36-byte shim at the CALL at 0x8C745, ×k on the desired velocity's x/y when entity+0x134 == 20; seen in game [xemu s2] |
| 6 | Climb: constant 0x1980E4, shim at 0x883FF | Cause not established; the 2.0 does move the body on the rungs (2.0 × dt a tick, xemu sitting 2.185), so the old test likely missed it | Back since Step 2.185: `climb_speed_scale` hooks the 2.0's two readers and the 1.5's (0x1980E0) five, seen in game |
| 7 | `flap_at_peak` v1 0x89381, v2 0x8939F, v3 shim 0x89409 | The patch only changes vz when z > peak_z, i.e. on the 2nd and later flaps; a 1-flap shield with no gauge refill never gets a 2nd flap, so the null result is plausibly a test-condition artifact [spike] | **Unresolved**; deleted (D18) |
| 8 | Slope slide: 0x1AAB68, shim at 0x8A095 | The runtime value at 0x3902A0 is a turn rate (500·π/180), not a speed [inferred] | Deleted (D18) |
| 9 | `animation_root_motion_scale` hook at 0x43066 | No effect at any scale; the real commit site is unknown | Deleted (D18) |
| 10 | XBR Editor edits to `armor_properties.Flaps` | They targeted 0x4000, which is `attacks_anims` (no `air_shield_N` column or `Flaps` row), so they matched no cell | Fixed: 0x2000 is labelled `armor_properties` (AZ-113) |
| 11 | Every non-`player_physics` slider (GUI) | The backend forwarded only `pack_params["player_physics"]` | Fixed |
| 12 | `walk_scale=0.0` | The allocator reused its own all-zero output, cross-linking two sliders | Fixed: the carve floor is `.text`'s raw end (AZ-001); explicit 0.0 scales reach the patcher (AZ-025) |
| 13 | Walk patch injecting a raw value | It wasn't vanilla × scale (3.0 became 43% speed) | Fixed |
| 14 | `player_max_hp` writing `critters_damage` garret4 `hitPoints` | The player never uses it: critter init 0x409C0 reads species+0x14 only when a spawn passes a negative HP, and the player's spawn passes the inventory `hlth` slot (from `settings_foo` `initial hp`) | Retargeted to `initial hp` (Starting HP) + `max hp` (HUD scale), D44/D45; seen in game [xemu s3, s4] |

**Open:** `flap_entry_fuel_cost=0` (D17). The per-jump cap stays at Flaps (1/2/5), and flaps within it leave the gauge at 1.0, so a second jump flaps as often as the first (`test_flap_fuel_cost_semantics`). "Infinite" is wrong per jump, and two things still drop the shield [xemu s6 §1(b), §1(c)]: **a press past the cap** (0x89330 → 0x837A0; L2 stubs it and reports the call) and **a descent flap** (d > 6.0, §4) at the vanilla `flap_descent_fuel_cost`. At entry cost 0 a descent flap would still drop it, because its cost is a separate PUSH (0x893CE) [inferred]. So "unlimited across jumps" holds only while every jump stays within its cap and above the descent threshold; the user-facing texts say so.

## 7. Doc and header errors still open

- **Misleading macro names** keep their names until AzurKit 4.2/4.3 (P3-Q6); their comments are right: `AZURIK_ENT_INPUT_STATE_PTR` (+0x20 is the critter that starts the armor chain), `AZURIK_ENT_TYPE` (+0x30, §3), `AZURIK_ENT_GRAB_TARGET` (+0x134 is the attack entry index, 20 = the roll), `AZURIK_LVL_AIR_POWER_LEVEL`, `AZURIK_ROLL_BOOST_*`, `AZURIK_PPS_PREJUMP` (state 5 is the zipline ride, §2), `AZURIK_INPUT_WHITE_BACK`, `AZURIK_DEV_MENU_FLAG_VA` (the BSS dword 0x1BCDD8 doesn't pick the level: at 0x52F95 a virtual call's AL result picks `selector` or `training_room`, and the dword only sets ESI on the selector branch; the selector is the developer level-select hub, not the `cheats.cpp` UI).
- **AZ-116, by name:** AzurKit's facts name 0x88A80 `player_ground_attack_start`. In Modkit it is `player_ground_land_tick` in `vanilla_symbols.py`, `azurik_vanilla.h` and `tests/facts/xbe.json`, but it is the ground attack starter (EAX = entity, ESI = input, [esp+4] = reset flag, RET 4; it never calls `player_slope_slide_tick`, whose callers are the slope cases 0x8D250/0x8D29A and 0x8AE10): call it by its VA. The snapshot names it `player_ground_attack_start`, 0x5E620 `settings_get_double` (a `settings_foo` lookup), 0x52F50 `game_start_setup` and 0x37BE98 `g_controller_state`, so `ghidra-sync` lists those as renames: never `--force` them (`azurik-ghidra-mcp` §6). The registry and header renames wait for AzurKit 4.2/4.3 (registry + header in one commit → `--update-facts`).
- **AZ-234 and AZ-247, renamed by Step 4.41a:** `devkit/re/data/structs.h` names these fields for what the game keeps there; `ghidra_snapshot.json` keeps the old names (`dpad_y` at +0x10, `IndexEntry`, `IndexRecord`) until the project holds the new ones and `ghidra-snapshot` reads them back (`azurik-ghidra-mcp`). `ghidra-sync --push-structs` creates the three new structs but keeps any struct Ghidra already has, so `ControllerState`'s two D-pad fields are renamed by hand, or by `--recreate-structs` (it deletes and recreates every header struct Ghidra has, wiping the types of the variables that used them), and `IndexEntry` and `IndexRecord` are deleted in the project by hand.
  - `ControllerState`'s D-pad fields: `dpad_x` (+0x10) holds the X axis (+1 for wButtons 0x08 RIGHT, -1 for 0x04 LEFT), and `dpad_y` (+0x14) the Y axis (+1 for 0x01 UP, -1 for 0x02 DOWN).
  - `XbrTocRun` (once `IndexEntry`): the 28-byte descriptor at [0x37BE50] of a loaded run of an XBR's 16-byte TOC entries (`XbrTocEntry`), which `load_asset_by_fourcc` (0xA67A0) reads: the first handle (+0x08), the entries (+0x0C), the loaded payload (+0x10) and the count and state (+0x1A). A call loads on demand (it can block) and returns 0 only on a failed lookup or build, a failed load or a fourcc miss.
  - `IndexXbrRecord` (once `IndexRecord`): index.xbr's 20-byte record, its fourcc at +0x10, which that loader doesn't read (`docs/RE_DATA.md` § index.xbr, "The run descriptor").
  - `tests/test_re_shims.py` asserts each field's offset by name, so a swapped name fails it.
- **Calling the register-ABI functions** (`vanilla_symbols.py` and `azurik_vanilla.h` declare the stack part honestly; register inputs no C convention passes are documented, and three have naked asm thunks):
  - `player_walk_state` (EAX = entity) and `player_airborne_tick` (EDI = entity): `stdcall(4)` with input on the stack; call them through `player_walk_state_call(entity, input)` / `player_airborne_tick_call(entity, input)`.
  - `player_jump_init` (ESI = entity, EAX = input, plain RET): `cdecl(void)`; call it through `player_jump_init_call(entity, input)`.
  - `player_climb_tick` (EAX = entity): `stdcall(4)`; no thunk. `wing_flap`: `stdcall(4)` plus ESI = entity; no thunk. `player_airborne_reinit`: `fastcall(4)` (ECX) plus EAX = armor_mgr; no thunk.
  - `consume_fuel`: `thiscall(armor_mgr, float cost)`, `arg_bytes = 4` (RET 4).
  - `anim_change` (0x42910): `stdcall(anim_obj, index, flags)`, RET 0xC. `anim_apply_translation` (0x42E40): `thiscall(rotation, anim_obj, blend_time, reference_name, ref_pos)`, RET 0x10, plus EAX; no thunk. `calculate_save_signature`: `thiscall(save_slot)`.
- **What the drift guards check: the stack part.** `test_declared_vanilla_abi_matches_callee_ret_imm16` compares each registry ABI with the callee's `RET N`; the link test (`test_every_shim_header_vanilla_extern_links_to_a_registry_va`) requires each header prototype's mangled name, convention and stack bytes to equal the registry's (thiscall, cdecl and undecorated names carry no `@N`); the VA audit reads `azurik.h`'s values; the symbol guard ties each extern's VA to its own name. They can't see register inputs, and a `RET N` can't tell thiscall from stdcall, so whether ECX/EAX/ESI/EDI carry an input is checked by eye at the call sites.
- **Outside the repo:** s1's REPORT §5 "deceleration is not capped" and s5's "+0x148 is 0 otherwise" are wrong (§4 Roll, §3).

## 8. Known hazards for behavior tests and simulator work

- **The simulator levels.** L0: structure checks in `devkit/sim/static.py` (section table, entry point, image size, kernel thunks, TLS; touched XBRs), behavior tests 1 (`tests/test_iso_roundtrip.py`: `default.xbe` md5 `ae67bd444260be00be48ee3567997baa`, `config.xbr` md5 `e64676d154cddb051e38b4d7503afe25`) and 3 (`tests/test_build_validity.py`). L1: static Capstone checks in `devkit/sim/l1.py`, behavior test 4. L2: `devkit/sim/l2.py` runs game code under Unicorn. `PlayerSim(xbe, player)` runs probes in order on one memory: `jump()` (0x89060), `flap()` (0x89300 with the real consume_fuel and airborne_reinit; 0x837A0 stubbed and reported), `fall()` (the next tick's 0x89480 up to 0x85700's move call 0x857FE), `walk()` (0x85F50 up to 0x860C8) and `roll()` (the entry 0x88990, then 0x8C7D0 each tick until the clip reaches Move end2; the root sampler 0xCACD0 reads a fake track, the move code 0x47380 records the desired velocity); `set(**fields)` moves or lands the player between them. `armor_slots(xbe, config_xbr)` runs the loader 0x3C700 on any `config.xbr` bytes. Tests: `tests/test_jump.py`, `tests/test_walk.py`, `tests/test_flaps.py`, `tests/test_roll.py`. The fake state `STANDING` in `l2.py` is an xemu dump at 0x89060 (level-1 start in a new game: Level 1, Flaps 0, an empty gauge; controller port 2; facing yaw 130°) plus the press each probe models, with s6's CritterData, body and animation-layer fields (CritterData +0x38 5.0 and +0x40 7.0; `STANDING` layer n 1, flags 0xB, an 8.0 s clip; the roll clip 1.1666666 s, flags 0xD, on n 1 or 2). `SHIELD_2` is the same player with air shield 2 and a full gauge. Any read of an entity/input/armor field, ControllerState or 0x1A7AE4 that `Player` doesn't name fails the probe. `boot_tick(xbe, state)` runs one tick of the boot state machine 0x5F620 (play_movie_fn 0x18980 and poll_movie 0x18D30 stubbed; state [0x1BF61C]: 1 starts AdreniumLogo.bik, 3 prophecy.bik): `tests/test_simulator.py`. The code L2 can't judge is a committed fact, `tests/facts/sim_blind_spots.toml`: a probe may stub only a listed function, and `Sim` refuses a build that changes a listed range unless the test carries `@pytest.mark.xemu_signoff("<session>")` naming a session listed there whose `spots` hold that range; `tests/test_simulator.py` replays historical cases 1, 2, 4 and 10 (§6). Unicorn is in the default `dev` dependency group; capstone is a runtime dependency (AZ-810).
- **Pin the control word to 0x023F.** Unicorn starts at 0x0, and a single-precision CW (0x7F) differs from 0x27F by 1 ulp in about 10–14% of random h values. Use `rel=1e-6`.
- **Hook 0xA9000 to fail fast** (L2 does). An unstubbed 0x42E40 on a zeroed fixture reaches the assert call at 0xC3C01 (return address 0xC3C06; Renderer.cpp line 2171, expression "start") and spins forever; under L2's read guard it fails earlier, on the unnamed read of body+0x158.
- **Keep fixtures off comparator thresholds.** A 0.7071 normal is bit-identical to 0.70709997.
- **Flap fixtures are biased.** Forcing flag 0x04 bypasses the per-press latch, and fuel = 1.0 hides the gauge budget.
- **A function-level pass is not an in-game effect.** `flap_at_peak` and the 0x866D9 roll shim both pass in isolation, so `tests/facts/sim_blind_spots.toml` lists them and L2 refuses builds that change them (the 0x8C745 roll shim is checked across the attack-move entry and ticks, but the move code is a stub: in game its acceleration cap makes k = 2 roll ×1.838 from standing and ×1.957 from a run, not ×2). Assert at the next tick. A movement feature isn't done until it has been seen once in xemu.
- **Assert the discrete apex** (with its dt), not h. Remember the frozen jump/flap tick.
- **Don't replace 0x47380 with Python.** It owns the ground ramp and landing. Stub only its geometry sweeps.
- **The owner's own xemu snapshots aren't vanilla.** The four on the owner's HDD come from `Azurik_dev.iso`: walk 14.0, jump/flap gravity 39.2, dt 1/60. The vanilla states are on D98's oracle HDD (`azurik-xemu-oracle` §6). Compare guest .text with the intended XBE before trusting a capture.
- **xemu capture quirks.** A breakpoint at 0x8CCC0 hits once per tick at 30 fps, but captures on the 60 fps dev snapshot sampled every tick twice, and s6 saw up to 2 duplicate hits in one capture: dedupe on +0x9C. +0x1A4 can repeat a tick and the velocity field overstates motion against an obstacle (§3); a level-changed or save-loaded entity's position and bbox aren't world positions, and a new level entity's first 4-6 rows are state 2 at (0, 0, 0) before it is placed. Full recipe: `azurik-xemu-oracle`.

## 9. Read-only verification commands

AzurKit's verbs, from the checkout's root; every one reads the image in
place (no extracted tree), the USA one by default (`AZURKIT_ISO`, else the
user data folder's).

```bash
uv run --locked python -c 'import hashlib; from azurkit.core import gate, iso; r = iso.Reader(gate.find(gate.USA)); print(hashlib.md5(r.read("default.xbe")).hexdigest())'   # expect ae67bd444260be00be48ee3567997baa
uv run --locked python -m devkit builds inspect-physics --iso BUILT.iso      # each slider site's value in a build
uv run --locked python -m devkit re xbe addr 0x1980A0                       # VA -> file offset + section (file 0x190D00, .rdata)
uv run --locked python -m devkit re xbe find-floats 9.7 9.9                 # expect 3 hits: 0x1980A8, 0x198704, 0x198740
uv run --locked azurkit data armor_properties air_shield_3                  # Flaps = 5.0
uv run --locked python -c "import json;d=json.load(open('devkit/re/data/ghidra_snapshot.json'));print([f['name'] for f in d['functions'] if f['address']=='0x00089300'])"   # ['wing_flap']
```

- Callers and references: `python -m devkit re xbe calls --to <VA>`, `xbe find-refs --va <VA>`, `xbe fn <VA>`, `xbe dis <VA>:<n>`.
- For RET forms and operands, write a throwaway capstone script under a `mktemp -d`. Report conclusions in the repo; a short excerpt of the listing may back them (D87), never the whole dump.
- Header lines: `grep -n 'AZURIK_ENT_INPUT_STATE_PTR\|AZURIK_LVL_\|frame_dt_fixed' devkit/re/data/structs.h` and `grep -n PATCH_FLAP_ENTRY devkit/re/data/anchors.toml`.
