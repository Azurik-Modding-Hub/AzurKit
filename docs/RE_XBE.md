# RE notes: the XBE

> Ported from Azurik_Modkit's `docs/` (Step 4.11g). A path under `azurik_mod/`, `scripts/`, `tests/` or
> `shims/`, and a link to a doc this folder lacks, names Modkit's tree, where the finding was made.

`default.xbe` itself: the Ghidra project, the section map and the
notable functions (from the old DECOMP notes), the boot state
machine, kernel imports, XBE and COFF layout, VAs versus file offsets,
vanilla functions with unusual calling conventions, the native cheat
UI, the FPS unlock's step cap and the 60 FPS audit. Each finding
cites the function or VA it came from so you can re-verify.

Split from the old LEARNINGS notes (History, at the end, has the path)
in REORG_PLAN Step 3.3d (2026-10-10) without rewording, so "above" or
"below" may mean a section that is
now in [`RE_MOVEMENT.md`](RE_MOVEMENT.md) (player movement),
[`RE_DATA.md`](RE_DATA.md) (data files) or
[`Finished/LEARNINGS_HISTORY.md`](Finished/LEARNINGS_HISTORY.md)
(superseded findings and retired attempts).

## Decompilation & Analysis

For anyone doing reverse-engineering work on `default.xbe`: this document points at the external Ghidra project (how to set it up, and the plugin it needs), gives the XBE section map, and enumerates the functions that matter for the patch packs shipped in this repo.  Findings you accumulate belong in [`RE_MOVEMENT.md`](RE_MOVEMENT.md), [`RE_DATA.md`](RE_DATA.md) and [`RE_XBE.md`](RE_XBE.md); the exported symbol state lives in [`ghidra_snapshot.json`](ghidra_snapshot.json).

### Ghidra project

The live Ghidra project is NOT committed to this repo (it's a multi-megabyte binary directory).  To continue analysis:

1. `uv run bootstrap.py --with re` installs Ghidra 12.1.2, its JDK, the ghidra-xbe loader (needed to import an XBE) and the stock GhydraMCP plugin into `.tools/`; start it with `.tools/ghidra/ghidraRun`.
2. Open your project (the owner's `Azurik Ghidra.gpr`, with its `.rep`, lives outside the checkout), or create a new one.
3. Import `default.xbe` from a legitimately-owned copy of Azurik.
4. Run auto-analysis.  Everything comes out as `FUN_xxxxxxxx`.
5. Apply the committed names instead of renaming by hand (`azurik-mod ghidra-sync --apply --target '<project>:/default.xbe'` pushes the second source's names into the live Ghidra serving that programId; [`TOOLS.md`](TOOLS.md#ghidra-sync--push-our-knowledge-into-ghidra)) — this repo already ships two canonical sources:
   - [`docs/ghidra_snapshot.json`](ghidra_snapshot.json) — the 525 functions and 1,083 labels the working project names (Ghidra's own `FUN_*`/`s_*`/… names left out), plus 10 structs (509 and 1,067 until D94's names were added, 2026-10-11). Since D94 it and the registry name three functions differently until AzurKit 4.2/4.3 (D68): 0x88A80, 0x5E620 and 0x52F50. The snapshot has the newer names.
   - [`azurik_mod/patching/vanilla_symbols.py`](../azurik_mod/patching/vanilla_symbols.py) — the subset shims may call into, with calling convention, stack-argument bytes and per-function notes.

For AI-assisted RE, the same bootstrap installs the stock [GhydraMCP](https://github.com/starsong-consulting/GhydraMCP) v3.0.0-rc.1 bridge and prints the `claude mcp add` line for it.  Client-side setup (port `8193`, `instances_use(8193)`) lives in [`MCP.md`](MCP.md).

### XBE section map

Azurik's XBE has **23 sections**, hard-coded as `(va_start, raw_start)` pairs in [`azurik_mod.patching.xbe.XBE_SECTIONS`](../azurik_mod/patching/xbe.py).  Every patch VA resolves through `va_to_file(va)` against that table, which is the single source of truth — a hand-copied 9-row mirror used to live here and drifted, returning offsets into the wrong section for every VA past BINK.  To dump the live table use `azurik-mod xbe sections`, or `parse_xbe_sections(xbe_data)` from the same module on your own `default.xbe`.

The two boundaries that matter most for the notes below: `.rdata` spans VA `0x18F3A0`–`0x1A299F`, and `.data` starts at VA `0x1A29A0`.

### Notable functions

Names are `FUN_<VA>` in Ghidra's default auto-analysis output.  Where a row shows a second name in parentheses, that's the canonical name from `ghidra_snapshot.json` / `vanilla_symbols.py` — prefer it.

#### Main loop and timing (FPS patch territory)

| Function          | Role |
|-------------------|------|
| `FUN_00058e40`    | Top-level main loop: builds dt, calls sim steps, drives renderer.  Home of the step-count FMUL + FISTP that Patch 4 rewrites. |
| `FUN_0008fbe0`    | Present wrapper (manual VBlank pacer).  Patch 1a sets N = ceil(60/F) at VA 0x08FD19 (1 at 60; F = `target_fps`). |
| `FUN_001262d0`    | D3D buffer-flip push-buffer builder.  Writes 0x300 (immediate) vs 0x304 (vsync).  Patch 1b NOPs the JNZ at VA 0x12635D to force the immediate path. |
| `FUN_0005f620` (`boot_state_tick`) | Boot-state machine — decides which movie / logo plays next.  `__stdcall`, takes dt as its one stack arg; forwards it to `FUN_00018d30` (`poll_movie`) etc.  Full signature notes in `vanilla_symbols.py`. |
| `FUN_00058d00`    | Scheduler pump; increments `DAT_001be36c` (per-step counter) and services cross-thread queues. |

#### Input

| Function       | Role |
|----------------|------|
| `FUN_000a2df0` (`xinput_device_poll`) | Outer input tick: calls XGetDeviceChanges, opens/closes controllers, iterates `FUN_000a2880` for each pad. |
| `FUN_000a2880` | Per-controller poll: reads XInputGetState, normalises axes / triggers / buttons into `DAT_0037BE98+`. Stateless — no edge detection here. |

#### Collision / physics (solver impulse patches)

| Function       | Role |
|----------------|------|
| `FUN_00047380` | Collision solver main routine.  Holds the bounce limit (patched 2→4 at VA 0x47EEF) and the correction cap (patched at VA 0x1AA230 in .data). |
| `FUN_00085f50` (`player_walk_state`) | Ground walking state.  Reads the probe offset whose pointer we re-target at VA 0x86162 from 0x1A2674 (0.1) to 0x1A268C (0.05, alignment padding nothing reads) — both in .rdata.  Until Step 2.27 the 0.05 went into 0x1A2690, the low half of the double FLT_EPSILON the plane-plane test reads at 0xBDA6D (AZ-330). |

#### Player attacks and the damage pass (Step 2.21c, 2026-10-12)

[verified 2026-10-12: a `ghidra-serve` copy on port 8207 and `azurik-mod xbe fn|insns|calls`]

| Function | Role |
|----------|------|
| `FUN_0008c230` | The PlayerControl tick, `__fastcall` (ECX = PlayerControl), scheduled every 1/30 s.  Writes critter+0x220 / +0x224 (damage type, the attack's Damage multiplier), runs `player_physics_state_machine` (0x8CCC0), stores the playing clip's time over its length at +0x178 (0x8C3AA), then calls 0x8C8A0 (`PUSH EDI` at 0x8C3A9, the CALL at 0x8C3B0, AL ignored: 0x8C3B5 is `MOV ESI, EDI` before `CALL 0x8C520`).  At its end +0x98 := the state at its start, and +0x9C (time in state) grows by dt while +0x94 is unchanged, else drops to 0. |
| `FUN_0008c8a0` (`player_staff_wall_check`) | The staff-hits-wall clank: `__stdcall(PlayerControl)`, `RET 4` on all three returns, one caller (0x8C3B0).  Runs only while the cvar `combat/staff hits walls` is on and +0x94 has the attack bit 0x100. Then, unless the critter's hit timer +0x1E0 is positive, it samples the body's marker `m_attacklevel` (0xCB2A0) and goes on only while its z is above 0.01 (0x8C98F; a body without the marker reads zeros); it poses the node `staff_center2slide` (looked up once per boot by 0xCA1D0 into 0x38DFF0; garret4's bone 119, 0x4077) through 0xCCDF0 into a stack matrix, takes the staff's ends 0.9 and 0.95 along its x row (0x1A2794, 0x1A2790) times the critter's world matrix (0x42200, then 0xA3860 scales its rows 0-2 by the critter's +0x188, loaded once at 0x8C9CC, Europe 0x8C97C; 0xE91BB), records them on the first open tick and casts three level sweeps (0x60870) from each later one. A hit (0x8CC21) stops the active layer (rate 0, time back to the contact), clears 0x100 (0x8CC9E) and plays `fx/sound/hits/clank1` and `*/fx/fx_staffcollision`, so the move ends with no damage pass. For a node the body lacks 0xCA1D0 returns 0 and 0xCCDF0 writes no matrix, so the sweep casts whatever the stack held: the player-model swap's X17 turns the cvar off on such a body (Step 2.75d, AZ-441) [verified 2026-10-16: capstone]. So the staff swept is the drawn one, × the model scale in length and place; X30 loads 1.0 at 0x8C9CC on a Garret drawn larger (Step 2.126, AZ-575) [verified 2026-10-21: `xbe dis` on both releases]. |
| `FUN_00088990` (`player_attack_enter`) | EDI = PlayerControl.  Plays the attack's clip (`anim_change`), sets its time to Move start × its length and its end mark to Move end2 × its length, and +0x94 := the new state (0x100).  A combo calls it again from inside state 0x100 (0x8CCC0, when the clip passes Move end1 and `player_ground_attack_start` takes a new input), so +0x9C runs on through a combo. |
| `0x0008D452` in `player_physics_state_machine` (0x8CCC0), `attack_transition_search` (0x7EF10) and the AI hit handler's stun (0x30BD0) | The combo's chain (Step 2.103, AZ-496, AZ-525) [verified static 2026-10-19: a `ghidra-serve` copy and `xbe dis`; sitting 2.103 saw the chain come at +0xFC's fraction and never onto an unstunned target, and the stun rule with a breakpoint on 0x30BD0]: in state 0x100, once the active clip's time over its length (0xCB020) reaches PlayerControl+0xFC (Move end1's fraction of whatever clip plays; the only `+0xfc]` read in 0x7E000–0x8EFFF) it calls `player_ground_attack_start(0)`, which takes an A press recorded under 0.3 s before (0x88A80; the press times at +0xA0/+0xA8/+0xB0, written each tick in state 0x100); with none the attack runs to its end and +0x134 := −1. 0x7EF10 takes the last move from +0x134: the rows basic1 → basic2, basic2 → basic3, basic3 → finish/finish3 and any → finish2 need target features `stunned frozen` (0x8000 \| 0x10000, the names at 0x1A9E8C) on the target 0x7EBB0 finds (the critter nearest the facing whose distance less its radius is at most 3.0 m, 0x1A25BC; not dead), else the last row, A → basic1. A hit stuns an AI critter only when the attack's `Damage multiplier` (the hit record's +0xC) is under 1.0 (0x30BD0, the compare at 0x30C11: level 1); otherwise its level comes from the damage against the target's ouch thresholds, and level 2 or 3 sets the hit timer and no stun (0x38ECE; stunned is set at 0x38EFF/0x38F04). One light hit left a keylord stunned 10–28 ticks [measured; what clears it unread]. A level 2 or 3 hit also clears a stun the target has: 0x37A70 clears 0x58000 before it sets the hit timer, so a heavy hit inside a light hit's stun un-stuns the target (Step 2.104, AZ-525; sitting 2.103's A5, town_male_farmer_1's basic2 at 1.363). 0x30BD0's only callers are 0x38D85 (the AI handler) and 0x8D66B (the player's); at 0x30C11 ECX is the hit record, built by the damage pass at 0x43BF3-0x43C13 (+0 3, +4 the attacking critter, +8 and +0xC its +0x220 and +0x224, the attack row's damage type and `Damage multiplier`, which 0x8C2F4 copies from PlayerControl+0xEC each tick), and EDI the target, whose world (+0x154) holds the player critter at +0xBC and +0xC0 (0x53F48, 0x53F5B: the scene's +0x30); the game tells the player's hits by `[hit+4] == [world+0xBC]` (0x38F20, the rumble) [verified static, Step 2.104]. X18 (`player_model/light_hit.c`) makes the player's melee hit in a column garret4 hits light level 1. Sitting 2.104 measured the rest [measured: breakpoints on 0x30C26, 0x7EF85 and 0x7F1A8]: a level-1 hit sets no hit timer, so a box that stays on a target hits it again every 10 ticks (guard_water own's basic1 at swing ticks 22, 32 and 42); one light hit stunned 32-64 ticks with the target's HP held; the search took basic3 → finish3 at 0.47-0.572 m (distance less radius) and → finish from 0.68 m, and counted no target 3.6 m out that the swing had hit and stunned. 0x7EBB0 (`attack_target_find`, __stdcall(12), RET 0xC; Step 2.105) [verified static: `xbe dis`]: its only caller is 0x7EF80; it queries the critters in a cube of ±3.0 round the critter's bounds centre (vtable +0x80; 0x60700) and keeps each whose +0x168 has 0x4040 and not 0x10000000 and whose distance less radius (the bounds centres' distance less its vtable +0x90) is at most 3.0 (0x7EDA4), counting them (+0); of those the one nearest the facing angle fills the 0x38-byte result: direction +4, angle +0x10, angle off +0x14, distance less radius +0x18, its +0x168 +0x1C, its bounds +0x20..+0x34. The angle test starts at 2π (0x198188), so any bearing passes; the candidates are what 0x60700 returns for the cube from the world's +0xAC tree (its list at [esp+0x64], count [esp+0x6C] at 0x7EC9C), a tree over the whole level, not a cell: the world-object constructor 0x60E40 inserts every object's leaf (object+0xF8) into it at 0x60F1B whatever its cell, 0xB8030 walks it, and the cells (+0x158, [[world+0xD4]+0x28] + 0xB4 x i, each an object vector) are a separate structure 0x60700 never reads [verified static 2026-10-22: Step 2.153b's design reads]. In Step 2.153's record (X37's 16 m calls) it never listed a stun-held sleeth 7.5-10.5 m behind the player (3 of 3) while it listed those near him out to 16.6 m [verified xemu: the list read at 0x7EC9C]; that sleeth was absent from the tree with +0x158 null, the state the object destructor 0x60F80 leaves (its leaf removed at 0x60FCA, its cell cleared through 0x61028 -> 0x611D0(0)), and the same rows read freed memory elsewhere [the game deletes it (the object destructor 0x60F80 from the world's deferred-delete sweep 0x563A7, called from the frame loop at 0xA2919) 60 ticks after the player is put 10-15 m behind it (f6's sentinel at 15, 12 and 10 m; w1's sleeth, which walks in, at 15 m only), and a live enemy there is picked on the window's first evaluation [verified in xemu, Step 2.153b's sitting R0 and record R1; what queues the delete is unread]] (AZ-663). The seven reads of 0x1A25BC (0x7EC10, 0x7EC20, 0x7EC36 the cube's top, 0x7EC53, 0x7EC5D, 0x7EC67 its bottom, 0x7EDA4 the test) are its only ones of that constant, which 35 instructions share. X21 (`player_model/target_search.c`) takes the CALL at 0x7EF80 and points the seven at its own radius. |
| `0x0008D44D`, `0x000CB020` `anim_layer_fraction`, `0x00030BD0`'s knock (Step 2.153) | [verified static 2026-10-22: Step 2.153's reads R3 and the critique, `xbe dis`] The chain check's `mov edx, [edi]; mov ecx, [edx+0x17C]; call 0xCB020` (Europe 0x8D3FD, `call 0xCB1A0`) runs in state 0x100 only (0x102 takes `test ah,1; jne 0x8D397`, the airborne tick); 0xCB020 (fastcall ECX the anim object, plain RET, clobbers EAX and ECX) returns the top layer's (anim + 0x40 x ([anim+0x10] + 1)) time (+0x18, clip s) over its clip's (+4) length (+0x10), 0.0 with no clip. A soft landing in the air attack makes 0x102 0x100 (the classifier 0x85920), and the clip plays on to its end; no damage box meets the floor (the hit sender 0x460B0 sends to objects). The knock: 0x30BD0 picks level 1/2/3 from the damage against the target's CritterData ouch2Threshold (+0x48) and ouch3Threshold (+0x4C), one up when the hit killed, but level 1 (a stun, the velocity zeroed) when the hit's multiplier is under 1.0 ([0x1A250C]); it writes the target's controller velocity (+0x24) v along (target − attacker) and 0.5 v up, v = sqrt(9.8 x ouch<level>Knockback), so the flight is that many metres (a sleeth's K2 2 m, K3 4 m); the AI handler 0x38C60 passes it its controller's +0x24 (0x38D73) and never reads it again, and the platform's send (0x7A1CA) runs it inside the send, so X37 zeroes +0x24 and +0x28 after a drain hit that took HP: the target hops where it stands (Step 2.153c, AZ-672). X39 jumps the air blast's clip to its impact at 0x8D44D. |
| `0x0008D39A`, `0x00085A7C`, `0x00085B65`, `0x0008B100` `player_hard_land` (Step 2.153b) | [verified static 2026-10-22: Step 2.153b's design reads] In state 0x102 the state machine skips wing_flap and the air search (`test ah, 1` at 0x8D372) and its last call every airborne tick is `push edi; mov edi, ebp; call 0x89480` (player_airborne_tick: EDI the PlayerControl, the input on the stack, RET 4) at 0x8D39A (Europe 0x8D34A, callee 0x89430). The player tick calls the state machine at 0x8C37D, then the staff-wall check 0x8C8A0 at 0x8C3B0, whose CALL at 0x8C8F7 runs the anim step 0x43A00 [verified static 2026-10-22: `xbe fn 0x8C37D`, `xbe fn 0x43A00`]: 0xCB730 advances the layers by the frame's dt, then 0xCBC80 samples the markers, so a layer time written in the state machine is advanced once before the fx and boxes read it (beamlord's blast: 0.1 clip s a 30 Hz tick, sitting 2.153's E1). player_land_classify (0x85920) calls the hard landing 0x8B100 at 0x85A7C (`mov eax, ecx; mov ecx, esi`) and 0x85B65 (EDX the input reloaded), each followed by the epilogue alone (Europe 0x85A2C, 0x85B15, callee 0x8B0B0), when the state less its 0x100 bit is nonzero, the fall speed passed [0x38B0C4] and 0.5 s or more were airborne; else the soft landing at 0x85A8A writes PC+0x16C |= 4 and PC+0x94 := the state's 0x100 bit. 0x8B100 (EAX the move result, ECX the PlayerControl, EDX the input; plain RET; keeps EBX and ESI) writes PC+0x94 := 0x100, clears +0x16C's bit 3, copies the result's +0xC0 vector into PC+0x24, plays slot 11 (touchdown) through 0x42430 at 0x8B18C and a landing sound (0xA5CA0, 0xA1C70); no fall damage there [inferred: no other call], but `fall_damage_dispatch` reads that vector's z as the fall speed later in the same tick (0x8C15F, reached 0x89982 -> 0x8998D 0x8BF90 -> 0x8C066 `player_landing` -> 0x8C173) [verified static 2026-10-22: Step 2.153b's review]. X39 holds the air blast's bolt at 0x8D39A and turns its hard landing soft at 0x85A7C and 0x85B65, keeping the velocity copy. |
| `0x0007EF10` `attack_transition_search`: its last move and its direction (Step 2.135) | [verified static 2026-10-21: `xbe dis`, Step 2.135's read R2/R3 and its design's J2] __stdcall(24) (the PlayerControl's +0xDC, the facing F = input+0x14, the stick heading H = input+0x38, the button 1/2/3, a move flag, the near-cliff byte) with AL (moving faster than walkSpeed) and CL (1: the air search, last move −4 'jump') register inputs, RET 0x18; callers 0x88D78 (the ground search) and 0x88FB2 (the air search). The last move is PC+0x134 (0x7EF29), −2 or −3 (AL) with none; 0x88A80(1) writes −1 there each state-0 tick without a stamped press (0x88B61). The direction: when the finder found a target (0x7EF90's `je` not taken) one above or below the body's middle is up (5) or down (6) (0x7EF92-0x7EFE4); else, or past that test, the target's bearing B (result +0x10) when it lies within 60 degrees of H ([0x38BC6C], made at 0xFB360), else H (B := 1e5), against F: under 45 degrees forward (1), past 135 back (4), else right (2) or left (3) (0x7F06A, 0x7F08B, 0x7F09B, 0x7F0AA). The first matching row (16-byte rows at [0x38BC74]) is copied by `attack_anim_record_copy` (0x7F1F0: ECX the record's home, EAX the column; the column to +0x58, the 0x58-byte `attacks_anims` record from [0x38BC60] + col × 0x58, the yaw to +0x5C: B, else H when B is 1e5, less the column's Aim angle × pi/180 ([0x38BC50]), or H alone for an empty Aim; RET 8); none matches → column 0. Rows 15-26 (up, down, back, right, left) need no target, so a sideways stick plays right1/left1. X36 (`player_model/attack_sets.c`, Step 2.135) makes the `je` a `jmp` and the three imm32 1 on a swapped body, and remaps the combo's columns after the search. |
| `0x000B7210` `world_text_add`, `0x000B72E0` `world_text_list`, `0x00050500`, `0x00050950` (Step 2.135) | The world-text list, the game's only text line that doesn't pause the world (its messages are popup images that stop the world tick) [verified static 2026-10-21: Step 2.135's read R5]: 0xB72E0 returns the vector 0x38DD00 (begin, end, capacity; Europe 0xB7460, 0x38FCA8), made empty on its first call; 0xB7210 (EAX a 4x4, translation at +0x30; ECX the point; ESI an RGBA of 4 floats; EDI the vector; the text on the stack; RET 4; Europe 0xB7390) appends a 0x6C-byte entry, the text up to 79 characters at +0x1C (0xB71A0), `\n` splitting lines; 0x50500 (its one caller 0x5519C, ungated) draws every entry each frame as a camera-facing billboard in `interface/courier18b` at 0.02 m a font pixel ([0x1A27E0]); 0x50950 clears the list once per world update, at 0x55FF5, right before the world update 0xAB980. In retail only cvar-gated debug code fills it (a critter's HP at 0x2747F, AI state labels at 0x26094). X36 showed the attack set's line through it until Step 2.153 (sitting 2.135 saw it drawn over the head). |
| `0x0001B2B0`, `0x0001B110` `hud_list_draw`, `0x000D09E0` `hud_font`, `0x000D0830` `hud_anchor`, `0x00097420`, `0x000D0D60` `font_draw_text` (Step 2.153) | The HUD's 2D text path [verified static 2026-10-22: Step 2.153's read R1 and its critique]: the frame draw's 2D phase (0x551AE calls 0xD0720: an ortho projection of the 640x480 frame, origin at the centre, y up) draws the HUD under the 'Show UI' cvar (0x5545C), then saving.tif, the test pattern, the 'show profile' overlay 0x22170 (0x55759) and the text panel 0x1F130, each anchoring itself first. The health/power HUD 0x1B2B0 anchors 6 (right|bottom) for the power HUD 0x1ACE0 and 5 (left|bottom) for the health bar 0x1AD60, 0x1AF20 and its list 0x1B110 (0x18-byte image entries, each anchoring itself at 0x1B151), its last call at 0x1B306. `hud_anchor` (stdcall(flags, scale[2]), RET 8; Europe 0xD0B30) sets D3DTS_WORLD to the scale plus an offset to a title-safe edge (flags & 3: x -0.4 W or +0.4 W; flags & 0xC: y -0.4 H or +0.4 H), so 9 (left|top) puts the origin 64 px from the left and 48 px from the top; of its 18 callers only 0x22170 anchors top-left. `hud_font` (no args; Europe 0xD0CE0) returns `interface/courier18b` (+0 its texture handle, +4 the line step, +8 the top) or 0. 0x97420 (Europe 0x974F0) sets the 2D material: ESI the RGBA, EDI the texture handle's address (the font itself), stdcall(0, 1) for text, RET 8, AL 0 on failure; its first instruction is `MOV EAX, 0x380C18`. `font_draw_text` (ESI a 9-float pen: the position, the up and the advance vectors; stdcall(font, text), RET 8; Europe 0xD1060) draws a string glyph by glyph, `\n` as a glyph. 0x22170 draws its lines with the pen at x 2, y -2 - font[+8], stepped by -font[+4]. X36 draws the attack set's line this way after 0x1B110 (Step 2.153). [unsure: seen in no sitting yet] |
| `0x0008C37D`, `0x0005545A`, `0x00052F50`, `0x000A30D0` `button_pressed_once` with ECX 8 (Step 2.186) | The speed toggle's hooks and its button [verified static 2026-10-25: `xbe dis`, `xbe fn`, `xbe calls --to`, a dword scan of the XBE for 0x1B2B0]: the PlayerControl tick calls `player_physics_state_machine` (0x8CCC0; [esp+4] the PlayerControl, EAX the input built at [esp+0x24], RET 4) only at 0x8C37D (Europe 0x8C32D, callee 0x8CC70), right after `push edi`; the frame draw's `mov edx, [ecx]; call [edx+8]` at 0x5545A (ECX scene+0x48, behind `test bl, bl` at 0x55440 and the 'Show UI' cvar at 0x55444) calls slot +8 of the vtable at 0x1A1858, the only dword in the XBE holding 0x1B2B0, the HUD draw (thiscall, no argument, plain RET at 0x1B30F); `game_start_setup` (0x52F50, 5 callers: 0x52947, 0x55C9E the continue, 0x55CCB, 0x55EFD the 'last-save-spot' reload, 0x56672 the menu load) opens with the position-free `sub esp, 0x138` and writes EAX, ECX and EDX before reading them (0x52F56, 0x52F6B, 0x52F6E). The poll's latch loop (0xA28EC-0xA290C) clears all 12 latches (+0x48 + i) while its button reads 0.0, so `button_pressed_once` with ECX 8 is L3's fresh press (+0x38, latch +0x50). The same VAs in Europe below 0x58CE1. [verified xemu 2026-10-25, sitting 2.186 and its fix's: each click flips the tick after its release, a held one once, none with R3 down on one of its ticks; photo mode opens on the chord's update with no player tick between, so an R3 a tick after L3 reaches only the cheat owner (no flip there; that the toggle's KeTickCount gap is what drops it is read from `speed_toggle.c`, not sat without it); the note draws after the HUD; a game over's Continue runs the start hook; Europe the same] |
| `FUN_0007e2e0` (`load_attacks_anims_config`) | Reads `attacks_anims`: each row's Move start / end1 / end2 become fractions of its clip, (value − Anim start) / (Anim end − Anim start), defaults 0, 1, 1.  The playing row is copied to PlayerControl+0xDC: +0xE0 its anim id, +0xEC Damage multiplier, +0xF8 Move start, +0xFC Move end1, +0x100 Move end2, +0x104 Rate; +0x134 is the column playing (−1 none, 20 the roll). |
| `FUN_00043a80` | The per-critter damage pass (vtable 0x19FC00, the critter's +0xD8 task): for critter+0x218 and +0x21C, a marker with active ≥ 0.5 and length > 0 makes a box (0xCA390), scaled by critter+0x188 and placed by the critter's world matrix, and 0x460B0 sends its hits.  The only reader of those two slots; critter_init (0x409C0) is the only writer. |

#### How the player's hit deals damage (Step 2.61, 2026-10-15)

[verified static 2026-10-15: decompiles from a `ghidra-serve` copy on port 8203 and `azurik-mod xbe dis|insns` (capstone); not measured in game]

| Function or site | Role |
|----------|------|
| `0x0008C230` | Each tick, before the state machine: critter+0x220 := `armor_mgr`+0x18 (`armor_mgr` = [[critter+0x154]+0xCC]), a pointer to a damage-type record, and critter+0x224 := PlayerControl+0xEC, the playing (or last) attack's `Damage multiplier`. |
| `0x000464D0` | Loads `config/damage` into 0x20-byte records at [0x38C364] (count [0x38C368]): +0 name, +4 `Type` as a fourcc, +8 `Level`, +0xC `Damage`, +0x10 `Delay` (s, default 1.0), +0x14 `Cost`, +0x18 `Freeze`, +0x1C the R/G/B colour. `Level`, `Damage` and `Cost` (0x46730) are truncated to int32 by 0xF5A40, which keeps the low 32 bits of a 64-bit truncation, so a value outside int32 wraps rather than saturates (Step 2.91a; `Cost` was missing here). |
| `0x00046A30` | The record of a type (EDI, a fourcc) and level (the stack), else NULL. |
| `0x000838E0` | Selecting a power (elements E A F W as bits 1 2 4 8) finds its `magic` row; for a `staff` row `armor_mgr`+0x18 := the record of the row's `Damage` type at level min(the selected elements' levels), held to 1–3. `0x83460` / `0x83600` (no power): the `none` row's type `norm` at level [[armor_mgr]+0xE0]+0x94 + 1, that field being inventory slot 10's value, which 0x57B70 tags `spow` (the plain staff's upgrades): the player's plain staff reaches `norm_1`–`norm_3`, never `norm_4`, which only keylord's and air_elemental's `damageType` name (Step 2.91a; this said "not traced"). |
| `0x0007E2E0` | `load_attacks_anims_config`'s defaults for an empty cell: `Damage multiplier` 1.0, `Fuel multiplier` 1.0, `Rate` 1.0, `Aim angle` 100000.0. |
| `0x00088990` | `player_attack_enter` sets the new layer's rate (layer +0x20) := `Rate` (+0x104) and the crossfade time anim+0x14 := 0.1 s, so an attack's clip outweighs the one before it from its second tick. |
| `0x00043B47` | The damage pass's `CALL 0xCA390` (`anim_marker_box`; the player-model swap's X13 shim takes it, Step 2.70): ECX = the box's 4×4 matrix (rotation from the marker's quaternion +0x10 through `0xA0770`, which builds R(q) for a row vector, so a model-space point is R(q) p; translation +0x30 = the marker's position +0x04), EAX = the box's local min/max (six floats, ±(extents +0x20 × length +0x2C)), EDX = the marker; EBX = the task (critter+0xD8) throughout the two-marker loop, ESI is reused after 0x43BA2.  Then 0x43B4C–0x43B8F scale the translation and 0xB7160 the min/max by critter+0x188, and 0x42200 / 0xE91BB place the box in the world. |
| `0x000460B0` | Sends the hit (message type 3: +4 the attacker, +8 critter+0x220, +0xC critter+0x224) to every entity in the box but the attacker that its vtable +0xA4 test accepts (a critter's is `0x41AE0`: when the species' byte +0x13 is set, `0xCCA10` on its model [inferred: per-bone volumes]; else a sphere of radius vtable +0x90 at its position +0x15C taken into the box's frame, plus two more along its up axis when the species' +0x1C exceeds 1.0 [inferred: a capsule], each tested against the box's min/max by `0xB6A70`, which takes any min/max, not only a symmetric one), unless a team check (attacker vtable +0x74) refuses it. |
| `0x00043210` | A critter's message slot (vtable 0x19FC08 + 0xB4).  A type-3 hit is ignored while the target's timer critter+0x1E0 is above 0, while its HP (+0x210) is 0, or when attacker and target share a `damageGroup` (S+0x5C); else it goes to the AI's slot +0x18 (critter+0x180), and a nonzero damage back from it sets +0x1E4 and +0x1E0 := the record's `Delay` (0.33 s for every player type; `FLD [EAX+0x10]; FST [EDX+0x1E4]` at 0x43584, `FSTP [EDX+0x1E0]` at 0x43591, the same VAs in Europe; a hit on the player never gets there, his own handler setting his +0x1E0 to 2.0 first at 0x8D6C2) and sends the attacker a type-4 message.  +0x1E4's one critter reader is the draw's hit tint (0x3EAB8-0x3EBB4) [verified static 2026-10-21]; the player-model swap's X31 shortens the player's hits' value by the attack speed (Step 2.126, AZ-573).  The damage pass's other phase takes 1/30 s off +0x1E0 each tick, so one target takes a hit at most every 10 ticks however long a box stays on it. |
| `0x00038C60` | The common AI hit handler: damage = ceil(S+0x8C[type index] × the multiplier), where S+0x8C holds the target species' `critters_damage` cell for each damage type (an empty cell: the type's base `Damage`); 0 does nothing; else `apply_damage` (HP − damage), the reaction 0x30BD0, and `_small` / `_big` rumbles for a multiplier below / above 1.0.  Bosses have their own (Balthazar's 0x279B0, which falls through to it at 0x27A37).  The hit's sound is S+0xB4[index] (0xA2630 at 0x38D2F) and its visual S+0x90[index] (0x38FEA-0x39006: the victim species' `critters_damage_fx` key for the hit's record, index its place in config `damage`, played by `critter_play_fx` 0x440F0 on the victim), so the visual is the attacker's damage type's, and the player's (armor_mgr+0x18: norm_1-norm_3 or a power's) shows `fx_norm_N` whatever body he wears; the player-model swap's X32 swaps the key for the worn species' type (Step 2.132, D333) [verified static 2026-10-21, both releases]. The sound: 0x38D1C-0x38D2F push 0, the victim's point (its vtable +0x80) and the handle, XOR EAX (0xA1C70's third argument) and call `sound_play_at` 0xA2630 (stdcall, RET 0xC; Europe 0xA27B0), the handle from `asset_find` 0xA5CA0 (thiscall: ECX the name, kind and flag on the stack, RET 8, -1 when no asset has it; Europe 0xA5E20); the bare-hands kit's X43 plays its thud there for the player's plain hits (Step 2.159a, D502) [verified static 2026-10-22: `xbe dis 0x38CF0:40`, `0xA2630:30`, `0xA5CA0:40`, `calls --to`, both releases' `region_map.py find`]. |

**Thrown critters** (Step 2.159b, X42; static reads of the 2.159 design's seats, seen in xemu in its B0 probe):

- `critter_spawn` (0x45C10, stdcall 12, the same VA in Europe) builds a critter from a 0x40-byte descriptor (+0 its owner object, +4 the owner's slot, +8 the species record, +0xC the cell, +0x10 the point, +0x1C the quaternion, +0x30 and +0x34 its HP pair, -1 the species') in the world it is given; it queues the spawn when the world's +0x100 vtable +4 says so (0x45C28-0x45C59), returning 0, and sets its third argument's int to 1 both when it builds the critter now and when it queues it (0x45E18-0x45E20: the flag is EAX != 0 there), so "queued" is EAX 0 with the flag 1 [verified static; 0 queued in about 95 probe spawns].
- **The owner link.** The critter ctor links the node critter+0x1EC into the list headed at owner+4 (node+0 = &owner+4, node+4 the old head) and sets +0x1F4 := the slot (0x40494-0x404C6); at HP 0 `apply_damage` calls the owner's slot +4 (the slot) and then unlinks the node (0x446C3-0x44719); the destructor unlinks with no notify (0x412B0-0x412EF), so "its node is still in the owner's list" is a liveness test that reads no freed critter [the probe: the engine had unlinked every flying or held critter before the next tick over five level changes and a death].
- **The owner's interface**, thiscall on the owner: +0x00 (out, slot) the home point, RET 8; +0x04 (slot) the death notify, RET 4; +0x08 (slot, out point, out 4x4) the held point and its rotation with the translation zeroed, RET 0xC (the held update 0x37AE9); +0x0C (out, slot) the leash (0x45F30, the game's, zeros: no leash), RET 8; +0x10 (slot) held?, RET 4 (0x37A13, 0x38A4D); +0x14 (slot) the held clip, RET 4; +0x18 0 (0x46060, plain RET). A critter the owner holds sits at its held point each tick: the probe's rock and vase sat exactly at X42's palm on every held tick at 30 and 60 fps (the critter thinks after the PlayerControl).
- **Message 10** {10, the sender, a velocity, -, a clip slot or -1, a landing state} through the critter's vtable +0xB4 (0x38AE4: the AI, `[critter+0x180]`, takes the velocity at +0x24..+0x2C, the clip through `anim_change`, the landing state at +0x13C and state 23 at +0xB4) throws it, and its clip plays in flight (X42's `debug`: anim 1 held, 9 flying, its layer's time running) [measured: Step 2.167c's sitting]; each tick state 23 (0x3A249) moves it through 0x30220, which first takes `[0x198740]` (9.8) × `[0x19873C]` (the tick, 1/30 s) off the AI's +0x2C and then moves the critter by the velocity (0x30350), so a velocity change made between ticks holds [inferred: 0x30350's own writes to +0x24 not read] (X42's arc, Step 2.167b, gives part of that back each tick) [the rest verified static 2026-10-24: `xbe dis 0x38AE4:60`, `0x3A1F0:90`, `0x30220:120`, `read 0x198740 --as f32`]; landing state 23 (0x3A249) ends it on contact with `apply_damage` on itself, which plays its `die`; the boulder's `die` keys `m_alpha` translateX 1 and z 0 over 0-0.333 s and its fx_default's `m_alpha.translateX -> breakEffectShape.loadEffect` link loads `fx_boulder_break` detached where it dies, the body hidden: the guardian's boulders and X42's projectile break so (the probe: every death played the clip and loaded the break). The break's `damageFieldShape` (`rock_shard`, 25 HP, every critter) is driven by timer1's link to its `damage` as well as its own value, so W30's clone zeroes both.
- **The hit sender's box** (0x460B0's first argument): +0x00 its world 4x4 (row 3 the translation), +0x80 the local min, +0x8C the local max (0xB6C70 reads them; X42 fills +0x40 with the inverse too, whose reader is not traced); the sender skips its source (0x461E7) and runs the wall test 0x46070 from the source to the hit point unless the source's species +0x7C (hitsThroughWalls) is set (0x4621D-0x46243). A type-3 hit's point is the victim's +0x260 (0x432E6-0x43309), `m_hitLocation` to its fx (0x44397-0x443BD), so a thrown critter's hit shows the victim's hit effect where it lands. The player's own hit messages reach a thrown critter every tick (689 in the probe) and its +0x1E0 window drops them.

So the player's hit on a common critter costs it ceil(D × M) HP: D the target's `critters_damage` value for the selected power's type and level (`norm_1` 10 … `norm_4` 25, an element 15/25/40 by level, `elemental_N` 100/200/400), M the attack column's `Damage multiplier` (`attacks_anims`, read only by the player).  A swapped body (Step 2.21a, mechanism B) changes neither D nor M, only the box and the move's length.  0x38CD6–0x38CF8 take ceil(D × M), and a hit whose damage comes to 0 (M 0: `--player-attack-damage 0`) returns there with nothing dealt [verified static, Step 2.123's attack read].

**Where a lunge's box is sent** (Step 2.197b, AZ-766; the vanilla disc in xemu, sitting 2.197b's G4V row): the damage pass places each box by the critter's model matrix, whose origin is the drawn origin, and an attack's aligned node (`m_feet`) keeps that origin back from the body by the playing clip's horizontal `m_feet`; so a box the clip keys at p(t) is sent at the body plus p(t) less `m_feet`(t), its x and y both. garret4's own staff, measured from his centre at each send: basic2 (attack_9) reaches 2.737 m where his clip holds 3.218, basic3 (attack_3) 2.322 (2.840), the finish (attack_10) 2.466 (3.306), sweep2 (`360_sweep`) 1.930 (4.130); every corner of all 34 boxes sent in a combo and two sweeps to the millimetre; X3's fixed box the same (Step 2.198). The listing, the balance (W14) and the logic read boxes so since Steps 2.198 and 2.197b.

**The transition search's long range** (Step 2.197b, W40) [verified static 2026-10-27: `xbe dis 0x7EF10`]: 0x7EF10 sets its long-range byte to 1 when its target's distance less radius (the finder's result +0x18, at [esp+0x30]) is above the f32 at 0x1A2730 (0.6 m, read only by the `fcomp` at 0x7F0BA; Europe 0x1A49D8), else 0; a row whose `long range` cell holds 0 or 1 matches only that byte (the row's byte at +0xB of its 16, 0x7F16C). Vanilla's one such row is 30, basic3 -> finish3 within 0.6 m (row 31, basic3 -> finish, any range). The finder writes +0x18 only for a target it keeps (0x7EE58), so with none (a row whose `target features` X36 cleared) the byte reads what the search's stack held there [inferred]. That distance is the bounds centres' in three dimensions, so it counts the height between them, where the player's blast hits a target whose side its box's face reaches on the level, whatever the heights [measured, Step 2.202b's sitting: f6's blaze sentinel (radius 1.0 m, its centre 1.0 m over the player's; town_male_6's 1.244 m), the long-range line poked past every gap, 0.1 m steps: the blast hit while the sentinel's side on the level stood within the box's far face and missed past it on town_male_6 (1.275 / 1.375 m against 1.302), Balthazar (1.50 / 1.60 against 1.574), Balthazar x0.7 (1.05 / 1.15 against 1.102) and keylord (1.00 missed against 0.995), its height over the box's top notwithstanding (Balthazar x0.7's box tops out 0.71 m under the sentinel's centre)]; X50 (Step 2.202b, AZ-803) compares the line with it on the level.

#### The player's hit reaction (Step 2.21d, 2026-10-12)

[verified 2026-10-12: a `ghidra-serve` copy on port 8205 and `azurik-mod xbe dis|calls|find-refs`]

| Function | Role |
|----------|------|
| `0x0008d600` | The player's hit handler, a PlayerControl vtable slot (0x19BC84), `__thiscall` (ECX = PlayerControl) with the hit on the stack (RET 4).  It lets 0x30BD0 pick the reaction, plays it through the CALL of 0x42750 at **0x8D682** (flags 4, node `m_feet`), sets +0x94 := 0x102, clears 0x8 in +0x16C, takes the damage off the critter's HP (critter+0x210, through 0x44640) and returns the damage (0 when none).  On landing the state stays 0x100, in which `player_ground_attack_tick` integrates gravity with no desired velocity (the stick isn't read), until `player_physics_state_machine`'s exit check (0x8CF56) sees the active layer's clip end (flag 0x20) or stop; so the reaction lasts its clip's length at rate 1 (AZ-291). |
| `FUN_00030bd0` | The hit-reaction chooser (the critter AI's hit handler `FUN_00038c60`, vtable 0x19FB00, calls it too, at 0x38D85): level 1-3 from the damage against the species' thresholds (S+0x48, S+0x4C), anim 0x24 + level (37 `ouch_1`, 38 `ouch_2`, 39 `ouch_3`), stepped down while the species' slot is −1 to 37; at 37, by the hit's direction, 40 `ouch_1r`, 41 `ouch_1l` or 42 `ouch_1b` when the body has it.  Also writes the knock-back velocity. |
| `0x00042750` (`anim_change_at_node`) | `__stdcall(16)`: the critter, the anim index, the flags, a node name (RET 0x10).  Plays the clip in species slot +0x124 + 4 × index on a fresh layer (0xCAD40: rate 1.0, end = the clip's length; anim+0x10 := that layer), after sampling the node in it (0xCAB80); critter+0x200 := index, +0x204 := the clip.  A slot of −1 plays nothing and leaves the clip already playing.  Its only caller is 0x8D682; the player-model swap's X7 shim takes that CALL. |

The clip names behind every anim index below 0x52 are the XBE's base clip
table at **0x1A9F78** (82 × {name pointer, phase-sync group}: 1 `idle`,
8 `walk`, 9 `run`, 37-42 the hit reactions, …), resolved per species
into S+0x124 + 4 × index against its body when the species loads
(0x4B8E0 → 0x4B600: the name as a full asset key, else
`characters/<body>/<name>`); 0x52 + i are the `attacks_anims` Anim
cells.  No `config.xbr` cell names a base clip: `critters_special_anims`
holds per-species extras (town talk and sit clips, boss specials) and
`attacks_transitions` the attack chains.  An anim layer is 0x40 bytes at
anim+0x40 + 0x40 × n (n = anim+0x10, the active one; three): +0 the
handle, +4 the clip, +8 the flags, +0x18 the time, +0x20 the rate,
+0x24 the end; a clip's length is its +0x10.

#### A critter's first clip and the player's walk-state clips (Step 2.22l, 2026-10-12)

[verified 2026-10-12: `azurik-mod xbe fn|dis|calls|find-refs` (capstone) on the vanilla XBE]

| Function or site | Role |
|----------|------|
| `0x00040CBB` in `critter_init` (0x409C0) | The CALL of `anim_change` (0x42910) that plays a new critter's first clip, flags 2 (looping): anim 0 (`initial`) when the spawn record's byte +0x39 is set and the species' slot 0 has a clip, else anim 2 (`idle_1`) when slot 2 has one, else anim 1 (`idle`). The player-model swap's X6 shim took it (AZ-303) until X11 (Step 2.66) filled the swapped body's idle slots at 0x4B948. |
| `0x00042910` (`anim_change`) | `__stdcall(12)`: the critter, the anim index, the flags (RET 0xC). With flags bit 2 it does nothing when critter+0x200 already holds the index; otherwise it sets +0x200 := index, and plays the species slot's clip (S+0x124 + 4 × index) on a fresh layer through 0xCAD40, setting +0x204 := the clip. A slot of −1 plays nothing and leaves the clip already playing, though +0x200 still changes. |
| `0x000864DA` in `player_walk_state` (0x85F50) | Each tick it asks `anim_change` for the clip its speed wants, unless critter+0x200 already holds it: when standing, the index `0x85C60` returns, 1 (`idle`, flags 2) or, after a while on `idle`, what 0x309A0 picks (flags 4; an `idle_1`–`idle_6` fidget [measured: sitting 2.168 saw X45's picks of slots 3-7 play here]); when moving, 8 (`walk`) or 9 (`run`) by the speed against a threshold, or 13 and 14 (`walk_backwards`, `run_backwards`) when an input flag asks, flags 2. |
| `0x0004B8E0` | Resolves a species' base clips once, when it loads: for each index 0–0x51 of the base clip table 0x1A9F78, 0x4B600 looks the name up as a whole asset key, else as `characters/<S+4>/<name>` (−1 when neither exists), into S+0x124 + 4 × index. `critters_special_anims` (0x4B185) and `attacks_anims` (`load_attacks_anims_config`, 0x7E2E0) write only slots 0x52 and up, so no `config.xbr` cell reaches slots 0–0x51. The CALL of 0x4B600 is at 0x4B948 (EAX the name, EDI the out, the species pushed, RET 4; ESI the index; the loop reads only EAX after it); the player-model swap's X11 shim takes it (Step 2.66). Before the clips it binds the species' body, once (the flag S+0x12, set at 0x4B906): `push 0x19F270` at 0x4B900 ('characters/%s', Europe 0x1A1428 at the same VA, the string's only user) formats the key from the body string S+4 into a stack buffer (ECX, pushed at 0x4B905) and `asset_find` (0xA5CA0) at 0x4B91A's result goes to S+0x120, the body every critter of the species draws; at 0x4B900 EBP is the species, EAX (the string, pushed) and EDX are dead and no flag is read before the snprintf at 0x4B90A; its four callers (0x37099, 0x3714E, 0x37192, 0x45E44) look the species up first (0x4B510) [verified static, Step 2.170b: `xbe fn`; the design's reads]. The swap's X47 (Step 2.170b) takes the push: the player's species (flag 0x20 in S+0x64, X11's test) binds W38's copy, `characters/<body>/v/skin` [not yet seen in game]. |

So a body with no `idle` and no `idle_1` starts every level with no clip at all, and draws its bind pose until some anim change finds a filled slot (xemu sitting modelswap3: town_male_6, walk only, until its first roll, attack or hit).

**The anim layers' crossfade (Step 2.22l, 2026-10-12)** [verified static: capstone on 0xCAD40 and the layer update around 0xCB3C9; the blend rule inferred from xemu sitting modelswap3's fight captures]. An anim layer's +8 flags are 0 for a free layer, with 0x8 while it fades in, 0x10 while it fades out and 0x2 to loop (the anim change's flags 2), and its +0x1C is its weight. 0xCAD40 (the clip change behind 0x42910 and 0x42750) marks every playing layer fading out (`&= ~8, |= 0x10`), starts the new clip on a free layer at weight 0.01 with flags `(the change's flags & ~0x10) | 9`, makes it anim+0x10, and sets anim+0x14 := 0.25 s (0x197564). Each tick the update moves a fading layer's weight by dt / anim+0x14 (in up to 1.0, 0x1A250C; out down to 0, where it writes flags 0) and advances every playing layer's time by dt × rate, a fading one's too. A body marker's value is the layers' blend: inside a hit reaction the sitting's m_damage read 0.990, 0.858, 0.726, 0.594, 0.462, 0.330, 0.198, 0.066, which is w_old / (w_old + w_new) with w_old = 1 − n/7.5 and w_new = 0.01 + n/7.5, whenever the interrupted attack's clip was inside its damage window, and 0 when it wasn't (AZ-304). The pose blends the same way: each bone's rotation summed by the layers' normalised weights, then normalised, its translations lerped, so a blend can sweep a limb below both poses; each layer's rotation is first normalised and negated where its w is negative (0xCBB33-0xCBB9C: the scale 1/|q| changes sign at 0xCBB6D-0xCBB7C, `fcomp [0x1A2508]`, `test ah, 5`, before the layer's q goes to 0xA0B70 at 0xCBBE8), so two layers holding one turn in opposite signs blend as that turn, not the long way round [verified static 2026-10-29, Step 2.207c: `azurik-mod xbe dis 0xCBAE0:110`. Offline with that turn: keylord + hoe's idle_1 into die_2 dips 0.098 model units at the 5th tick, the game 0.098 (0.197 m drawn at x2) at the 6th (Step 2.207b's record, DIE2-KH), the raw sum 0.278 at the 6th; his attack's end into idle_1 0.101 at the 4th, the game 0.175 at the 5th (ROLLR-KH); since Step 2.207d (AZ-825) `_player_crossfade` (X48's gate, X28's tables) turns each layer so too, where it summed the raw components: booblord's raw sum dipped 0.284 m between her idle and jump_standing, the turn 0.081 at most (walk into fall), and X28's hang_start table from her walk and her run 0.21 and 0.29 m deep against 0.15 and 0.16 (from her sit_cross 0.34 against 0.43)]. 0xA0B70 itself is no weighted sum but a swing-twist blend: each input's x axis from 0xA0990, the swing onto the two axes' bisector, the twist r^-1 q1 raised to t by 0xA0A00 (2 acos(w) wrapped to [-pi, pi) by the CRT fmod at 0xF5EF6), so it goes the short way whatever the inputs' signs and the w >= 0 turn changes nothing in it; the model's turn-then-sum matches it where the turned layers' dot is 0 or more (booblord's and beamlord's tables to 0.1 mm), not under it (AZ-827) [verified static 2026-10-30, Step 2.207d's review: `azurik-mod xbe dis 0xA0B70`, `0xA0990`, `0xA0A00`]; sitting 2.118's frame-scored `hang_start` frames fit it with the new layer k − 1 ticks in at the k-th tick and the fading layer's time advancing (guard_air own × 2's placed h1-h8 at rms 0.08 m, 3.11 m under its origin at h4 where neither clip goes under it; kingkong own × 2's at 0.003) [measured: Step 2.118c; `azurik_mod/patches/_player_crossfade.py`].

**The anim step and its marker sampler (Step 2.149, 2026-10-22)** [verified static: `azurik-mod xbe fn|dis|calls`, both releases]. 0x43A00 (ESI the critter, a register input: `push ecx; mov ecx,[esi+0x17c]`) advances the anim clock (0xCB730, at 0x43A51), then calls `anim_sample_markers` (0xCBC80, Europe 0xCBE00; the anim and a flags pointer, RET 8) at 0x43A62, which runs once per clock change (anim+0x30 against [[anim+4]+0x10], f64): the layer update 0xCB370 (a layer's time += (clock − its last time, f64 at +0x10) × its rate +0x20) and the markers' blend. 0x43A00's callers are the critter task 0x43AAD (task state 6) and the player code 0x8C8F7 (Europe 0x8C8A7; gated on PlayerControl +0x94 bit 8 and [critter+0x1E0] > 0), so the player's step can run twice a tick. 0xCBC80's other caller, 0x4030B, is `aligned_node_offset`'s re-sample. An anim's +0x10 is the layer the last clip change took and +0x14 its crossfade (0.25 s; 0.1 s from `player_attack_enter`, stored at 0x88A33 from 0x1980A4); a layer's fade-in bit 0x8 stays for its life. `player_attack_enter`'s CALL of `quat_from_euler` (0x4FF10, three floats, ESI the out quaternion, RET 0xC) at 0x88A5E comes after the clip change (0x889A6) and the rate (0x889BB) on every path; the ring of X38 (`player_model/README.md` § `fx_ring.c`) hooks both 0x88A5E and 0x43A62.

**The player hit handler's apply_damage call, and where 0x4030B runs (Step 2.155, 2026-10-22)** [verified static: `azurik-mod xbe dis|calls`, both releases]. The player hit handler 0x8D600 (thiscall, `mov esi, ecx` at 0x8D608: the PlayerControl, its vtable slot 0x19BC84) makes X7's CALL of `anim_change_at_node` at 0x8D682 (Europe 0x8D632), runs 0x8D687-0x8D6AE with no branch (move state 0x102, PlayerControl+0x16C bit 3 cleared, the critter's HP less the damage) and calls `apply_damage` (0x44640, `__stdcall(12)`: the critter [esi+0x20], the new HP, 0; one of its 14 callers) at 0x8D6AF (Europe 0x8D65F); after it EAX and ECX are reloaded (0x8D6B4, 0x8D6B7) and EDX is never read. The marker re-sample at 0x4030B (`aligned_node_offset` 0x402E0, whose one caller is 0x42253 in `critter_model_matrix` 0x42200) runs inside fx instance ticks: 0x42200's caller 0x444ED is in 0x444E0, slot +0x10 of the bind interface's vtable 0x19FBCC, which the bind set 0x62C40 calls at 0x62D45 when its +0xC bit 29 is set (the root node's matrix := the critter's). So a hit's clip change lands after both anim steps' sampler (0x43A62) and before the re-samples of the tick's bound instances, and a detach or spawn at 0x4030B would run inside that bind set's walk; X38's hit landing (AZ-650) is at 0x8D6AF [measured: Step 2.155's sitting R1, the armed gust copy let go on the hit row at 11.313 m, main's re-sampled to 0.142 m first].

#### Every clip the player asks for (Step 2.60, 2026-10-15)

[verified static 2026-10-15: every direct CALL of 0x42910, 0x42430, 0x42750 and 0x8BDB0 in 0x83000–0x8F000, decompiles from a `ghidra-serve` copy and `azurik-mod xbe dis|calls|insns`; nothing references 0x42910 or 0x42430 as data]. "Aligned" is 0x42430, reached through the move-state setter 0x8BDB0 (its CALL at 0x8BDF3), which sets the state first; such a clip ends on the layer's flag 0x80. Each of the setter's six callers then sets the active layer's rate through 0x30940 (EAX the PlayerControl, its +0x20 the critter; RET 4): 1.5 (0x1980E0) for the hoist (0x86D9E) and the ladder's moves, `step_up`'s from the speed (0x8B6CD), so garret4's 4.4 s `hoist` (t0 0, t1 1) holds 0x100 88 ticks (89 in the sittings); the direct calls (`touchdown`, `hang_start`) set none, so theirs play at rate 1 [verified static 2026-10-18, Step 2.96: capstone]. `step_up`'s is 2.8 (0x1A28AC) × the stick's magnitude (input +0x124 [inferred]) + 0.2, at least 1.0 (0x8B65F-0x8B682), so 3.0 at full tilt; the climb tick sets its loop's after its `anim_change` (0x30940 at 0x883D7): `climb_idle` 1.0 (0x882C5), the four climb loops 0x1980E4's 2.0 × [ebp+0x1C] (0x88357; the stick's component along the wall [inferred]), so 2.0 at full tilt; a swapped body's jiggle is baked at these (Step 2.143, AZ-648; xemu sitting 2.143 read 1.5 and 2.0 on a1's ladder) [verified static 2026-10-22, Step 2.143: capstone].

| Site | Index (base clip) | When |
|---|---|---|
| 0x864DA (walk state) | 1 `idle`, or a fidget 2–7 that 0x85C60 / 0x309A0 picks among the filled slots from 1 (from 2 when 1 is empty) after 10 s standing (0x85C60: the timer 0x38DC50, Europe 0x38FBF8, + the tick while slot 1 plays, drawn U(0, 6) on every tick a fidget plays and U(0, 3) after a move; past 10.0 s `[0x1A25B4]` and once 0x308F0 says the clip ended (sticky on a looping layer: its +8 flags 0xb until its first wrap, then 0x2b on each of the 19,326 base ticks after it, USA and Europe, 0x20 never cleared [measured: sitting 2.168 and its skeptic]), 0x309A0's even pick over the run of filled slots up to the first empty one, at most 7; a pick of 1 is made again on the next tick, so a fidget comes 10 s less its seed after the last, 7–10 s after walking, and not before the base layer's first wrap: 4–10 s on booblord's 4 s `hip_idle`, garret4's 8.03–10.1 s [measured: sitting 2.190; his base's wrap inferred]; the spawn plays slot 2, critter_init 0x40CA9 [verified static 2026-10-23, Step 2.168: `azurik-mod xbe dis`]; a variant's `idles` replace the pick's CALL at 0x85CD7 with X45); 8 `walk` or 9 `run` by speed against walkSpeed (an empty 9 doesn't fall back to 8); 13 / 14 backwards with RT | ground movement |
| 0x8A167 (slope tick) | 12 `slide` (state 4); 1 or 8 on a slope (state 3) | slopes |
| 0x89254 (jump_init) | 15 `jump` when faster than walkSpeed, else 16 `jump_standing`; 20 `climb_drop` from a climb | jump |
| 0x89412 (wing_flap) | 17 `superjump` | the Flaps air jump |
| 0x898B6 (airborne tick) | 18 `fall` (walked off, dropped); 21 `fall_big` once a 15–20 clip ends; 19 `fall_attack` once an air attack's clip ends; 22 `hover` in an updraft [inferred] | in the air |
| 0x8B0D4, 0x8B18C | 11 `touchdown`, aligned, state 0x100 | a hard landing: a vertical speed change of at least sqrt(2g × 2.9) = 7.539 m/s at the contact (0x85B31–0x85B42 against [0x38B0C4], written at boot by 0xFBAC0 from gravity and 0x1980F0), the PlayerControl at least 0.5 s old (0x85B44); a soft one plays nothing (AZ-540) |
| 0x8B6C1 | 53 `step_up`, aligned, state 0x100 | walking up a step of up to about 0.6 m |
| 0x86D91 | 65 `hoist` (ledge about 0.9 m up) or 66 `hoist_waist` (about 0.1 m), aligned, state 0x100 | mantling a ledge from the air or water |
| 0x870E9, 0x87436, 0x8791B | 60 `climb_start` (walking into a wall), 64 `climb_from_jump` (from the air or water), 62 `climb_down_edge` (off a ledge onto a wall below), aligned, state 0x101 | latching onto a climb wall |
| 0x883CB, 0x88733, 0x887A8 | 55 `climb_idle`, 56–59 `climb_up` / `_down` / `_left` / `_right` by the stick; 18 when the wall is lost | climbing |
| 0x87F47 | 63 `climb_up_edge`, aligned, state 0x100 | over the top of a wall |
| 0x8A4E3, 0x8AA89 | 68 `hang_start` (aligned, state 0x105), then 67 `hang` | hanging from an overhead surface: the set-up 0x8A200 has one caller, the ground state's case at 0x8D149 (after the swim, the use and the landing checks, before the jump), so a grab starts from the ground; it writes state 0x105 (0x8A48D), plays `hang_start` at 0x8A4E3 and calls the state's landing 0x8C080 at 0x8A4F0 (EAX the PlayerControl, RET 8), the tick drawn first at the glide's start; each later tick of state 0x105 the dispatcher 0x8CFA0 runs its case at 0x8D091 (only there: no jump lands on 0x8D091 or 0x8D096), whose CALL 0x43170 at 0x8D4AB runs only while PlayerControl +0x30 holds an object (0x8D096, 0x8D4A3): 0x43170 adds a moving object's delta to +0x1B0, +0x1BC and the centre (the carry). The hang's clip starts through the layers' crossfade, but where it is the clip `hang_start`'s layer holds (an X9 stand-in in both slots) 0xCAD40 plays it on that layer, going on from its time at the hang's rate, no crossfade [measured: sitting 2.118's ride frames to 1 mm, Step 2.118c]; the swap's X28 holds the drawn body over the floor at all three landings (Step 2.118c) |
| 0x8BCCA, 0x8BC26 (swim tick) | 70 `swim_idle`, 71 rising, 72 sinking; 74 `swim_2` with the stick past 0.1 | swimming |
| 0x88951 (aligned, state 0x100) | 75–80 `victory_1`–`_6` after an item pickup or a guardian's or boss's death (below), 81 `use` at an object; an empty slot drops the request (0x888C2) | victory, use |
| 0x889A6 (player_attack_enter) | 0x52 + the `attacks_anims` column (20 the roll) | attacks and the roll |
| 0x8D682 → 0x42750 | 37–39 by the damage, stepped down to 37 while empty, then 40–42 by direction when filled | a hit |
| 0x8CF2D (state machine) | 21 for a fall death, 27 `drowning` in water, else a filled 23–26 (`die`, `die_1`–`_3`) at random; state 7, then 8 when the clip ends | death |

**What posts a victory (Step 2.121, 2026-10-20).** [verified static: Step 2.121's game-side read, `azurik-mod xbe dis|calls|find-refs` on both releases] The request is the dword `[[critter+0x154]+0xD8]+4` (+0x154 is the world, which the level camera also reads at 0x8135E). Its one writer is the base critter's vtable slot +0xB8, 0x41390 (in the vtables 0x19FC08 and 0x1A1B18), run once per critter (flag 0x10000000 in +0x168): request := max(request, species+0x2FC), where the species loader stores `critters_engine`'s `victory anim` as an int (0x49A62; `shims/include/azurik.h` and the Ghidra snapshot name CritterData +0x5C `victory_anim_token`, which nothing writes). The values: v1 the obsidians, v2 the 20 keys, v3 the fragments 1–3, v4 each element's fragment 4, v5 the powers, v6 guard_air, guard_earth, guard_fire3, guard_water, balthazar and spideyzar; no other critter posts one, so a victory celebrates an item pickup (0x46FE0 calls the slot at 0x470F0) or a guardian's or boss's death, never an ordinary kill. Only the ground state consumes it (0x887D0 at 0x8D128; Europe 0x88780); swimming (state 6) drops a pending v1 or v2 every tick (0x8D188, 0x8D18E; Europe 0x8D138) and every other state leaves it waiting. 0x887D0 clears it, turns nothing, and plays slot 74+v aligned (0x42430, both nodes `m_feet`, the target 1 m below the place), state 0x100, the hit timer +0x1E0 and +0x1E4 the clip's length; 0x8CF56 ends the move on the layer's end flag, a tick past the clip (garret4's victory_1 and _6, 70 and 158 ticks of clip, hold 0x100 71 and 159 in xemu, sitting 2.117b). The clip's `m_feet` places the body and is its root motion (0x8C630) and its `m_damage` deals damage (0x43A80), so a swapped body's victory clip holds both off (`docs/PATCHES.md` W21). Measured on the tick (sitting 2.181, 2026-10-25, main's booblord, a real key pickup: w1's key_life1 [placed: R6 at its point]): the key is counted and the request (2) posted on the touch tick, while she is still in the air (the first-pickup popup there too, holding the player tick until A), the move starts on her first ground tick and clears the request; through its 121 ticks the state timer +0x9C counts 0 to 4.0, the hit timer +0x1E0 3.967 to −0.033 (+0x1E4 4.0, no flash), the stick is read (input +0x1C 1.0 from the push) and ignored, input +0x30 and +0x21 stay 0 and the camera's yaw (input +0x10) doesn't move; on the tick after the end flag she runs (slot 9). A victory posted during an attack (0x46FE0 defers a pickup only while +0x1E0 > 0) waits in 0x100 and starts on the tick the attack ends (0x8CF8C, the ground state, 0x887D0 in one tick), so +0x9C, zeroed only when the state differs across a tick (0x8C3CC), carries the attack's time (sitting 2.181's second: 0.267 after an 8-tick attack); its own clock is +0x1E4 − +0x1E0. Balthazar's real death (sitting 2.181's re-run, his HP written low [placed], then real hits) posted no victory: from the kill his death camera stood second on the world's stack with the freeze byte 1 and input +0x30 set for 239 ticks (8.0 s), and then the airship's EndFight switch took the player to a3 before any request reached the block. So nothing waits on the move's later ticks; X46 (`player_model/victory_cancel.c`, Step 2.181) ends a recipe's at a push of the stick.

**An aligned move at a scale (Step 2.106, AZ-529).** 0x42430 glides the drawn origin from +0x1B0 to +0x1BC over the move's window (+0x1A0, from t0 at +0x1A8; 0x42070 draws the straight-line blend while the glide mode +0x19C is 2, which a sitting reading +0x1B0 alone misreads as where the body is drawn). The start is 0x41E50's world place of the start node (+0x1FC; every ladder latch sets it to `m_grab`: 0x870AC, 0x873FC, 0x878DE): the drawn origin plus the node sampled by 0xCAB80 on the playing clip, times the critter's scale +0x188 (the FMULs from 0x41E97), turned by +0x18C (0xA1420); 0x42430 then takes off the new clip's start node at t0 unscaled. The end is the target less the end node at t1, unscaled. Neither 0x42E40 nor 0x42430 reads +0x188 otherwise, so a body drawn at D ≠ 1 starts an aligned move (D − 1) × its node too high and ends it (D − 1) × its end node off the target: a baked body drawn × 2.3 on `climb_up_edge` 2.950 m over the control's start (1.3 × `m_grab`'s 2.269 m; sitting 2.105 to the mm), its drawn feet that far over the top floor at the end, then the stance's drop (X23 in `azurik_mod/patches/player_model/README.md` § `over_top.c`) [verified static 2026-10-19: capstone]. The top dismount 0x87950 makes the setter call at 0x87F47 (state 0x100, anim 0x3F), its rate at 0x87F55 and the state's landing 0x8C080 (EAX the PlayerControl, two stack arguments, RET 8) at 0x87F65. **Into the stance (Step 2.116).** `critter_model_matrix` (0x42200) puts row 3 at `glide_origin` (0x42070, __stdcall(8), the critter and the out, RET 8: by +0x19C 2 the straight-line blend of +0x1B0 and +0x1BC by (layer time − +0x1A8) / +0x1A0 clamped to 0..1, 1 the same by another clock, else +0x1B0) plus `aligned_node_offset` (0x402E0, its only caller the CALL at 0x42253: EAX the critter, EDI the out, a plain RET; the node named at +0x1F8 in the clip at +0x204 at the top layer's time less the same node in the blended pose, after the pose update 0xCBC80; zeros with no anim object, node or clip), added by 0xA36E0 unscaled. When the climb's layer ends (0x8CF8C drops 0x100) state 0's walk places `m_feet` through 0x42E40 at 0x866D9 (blend 0: +0x1B0 = +0x1BC, +0x19C 0, +0x1F8 := `m_feet`), and through the crossfade the term holds the drawn origin back by 1 × the climb pose's `m_feet`; with the bones × D a body drawn at D ≠ 1 is held (D − 1) × `m_feet` short, so it pops up (D − 1) × 2.647 m at the switch and settles over the crossfade (town_male_6 × 2-3.3 3.04-6.68 m, sitting 2.107 C; an earlier "2.95 m drop in a tick" read +0x1B0) [verified static: capstone, 2026-10-20; measured]. X26 (`player_model/stance_term.c`) scales the term on X23's bodies. **The hoist (Step 2.127, AZ-572).** 0x86920 (from the airborne tick 0x897A0 and the swim tick 0x8BAC6) picks `hoist` (anim 0x41, written at 0x86C15) or `hoist_waist` (0x42, at 0x86C42) and sets state 0x100 with it through the setter at 0x86D91, its rate at 0x86D9E and the state's landing 0x8C080 at 0x86DAE (Europe 0x86D41, 0x86D4E, 0x86D5E; 0x42430 has written the move's turn to +0x18C at 0x426CC by then); both aligned nodes are `m_feet` (the string pushed twice at 0x86D63-0x86D70). So the glide ends at the ledge less the clip's `m_feet` at t1, unscaled (garret4's `hoist` (0, 1.223, 1.774), `hoist_waist` (0, 0.701, 1.003); `hoist` starts at (0, −0.003, 0.111), `hoist_waist` at (0, 0.211, −0.192)), and its start is `m_feet` on the clip that was playing, × +0x188 (the jump's 0.035-0.100 m, `swim_start`'s (0, −0.203, −0.406)). A body drawn × D ended the move D × (L1 + pad) − Fz(t1) + c over the ledge's floor (L1 + pad its lowest drawn point at t1; sitting 2.123's h65 within 0.02 m on garret4, 0.054 m on keylord own), and the 8 ticks after it are the stance's crossfade above, drawn (D − 1) × 2.155 m / 7.575 a tick off the floor (× 2 0.27, × 0.5 −0.11 measured), not a glide [verified static 2026-10-21: capstone, both releases; computed]. X23's second landing ends it on the floor; X26 and X8 take its stance.

The walking clips' rate is 0x30D90's: the speed over the critter's scale (+0x188) times its species' `critters_critter_data` `walkAnimSpeed` (S+0x3C; indices 8 and 13) or `runAnimSpeed` (S+0x44; 9 and 14), else 1.0; the player's are garret4's 1.5 and 5.25, whatever body it wears (W7 writes a worn body's own there, on garret4's calibration since Step 2.133: his cells are 2.00 × and 1.48 × his walk's and run's stance foot speed, so the rate follows the speed and the drawn scale with no byte). 0x896F4 plays 50 `fly` only with the cheat buttons' input flag 0x40 (never set in retail). The player never asks for 0, 10, 28–36, 43–49, 51, 52, 54, 61, 69 or 73. An empty slot: 0x42910 leaves the clip playing (critter+0x200 still changes); 0x42430 plays and aligns nothing while the state is already set, so the move ends when the old clip ends, without its motion [inferred: no lift onto a ledge]; only the use and victory check, the death and idle pickers and the hit chooser fall back. Each 0x1xx state drops its 0x100 bit when the active layer ends (0x8CF50), death moves on at the clip's end, and a looping layer's end flag sticks after its first wrap, so with an empty slot no wait hangs [inferred from the layer update 0xCB431–0xCB4C4]. No usable body but garret4's has any of 11, 12, 16, 17, 19–22, 27, 53, 55–60, 62–68, 70–72, 74–81.

#### The fx bind interface and the air armor's wings (Step 2.77, 2026-10-15)

[verified static 2026-10-15: `azurik-mod xbe fn|dis|calls|find-refs` (capstone) on the vanilla XBE; not yet run in xemu]. An fx transform with a bind name follows a node of the body that casts it (`docs/RE_DATA.md`: the staff, the air armor's wings).

| Function or site | Role |
|----------|------|
| `0x00062A20` | Binds an fx instance when it is built (called only at 0x627B7 and 0x627C9): for each named transform it asks the critter's bind interface (critter+0x170, its vtable 0x19FBCC or 0x1A1ADC; both hold slot 0 = 0x44250, 1 = 0x44270, 2 = 0x44370, the only pointers to those two) with `call [eax+4]` at 0x62B2D, keeps any nonzero result as the transform's index (all 32 bits) and drops a 0 (0x62B30). |
| `0x000625D0` | Builds an instance's bind block ([instance+0x54], B) when it is built, before 0x62A20 binds its two lists (B+0x24, B+0x14, at 0x627B7 and 0x627C9): for each record whose bind object (vtable +0x20) names one ([obj+0xF8]), the name `effectOrigin` (0x19DE7C, 13 bytes with its NUL; `repe cmpsb` at 0x6263B) makes it the instance's root, B+0xC (one only: the assert at 0x6265E), and any other name joins the list the binder asks the critter for. 0x62A20 sets a list's +0xC bit 29 when the interface's slot 3 says so and no other list took it (B+0x10 bit 1); 0x62C40 then, with B+0xC set, writes the critter's model matrix (slot 4, 0x444E0 -> `critter_model_matrix` 0x42200) into that root every frame through 0x68FA0 (the matrix at +0x70, inherit mode 6 at +0xF0, dirty bit 30), so the graph's DAG hangs on the wearer. With no `effectOrigin` record nothing writes it, and every node sits at its own transform in the world [verified xemu: Step 2.167d's BIND rows: X38's bound copies of Step 2.167c had B+0xC 0 with the critter's list's bit 29 set, each holder's world its own local transform 0-1.08 m from the level's origin, 56.4-56.6 m from the player; with an `effectOrigin` root each root sat on the model's origin 1.0 m from his centre]. 108 of 113 characters.xbr and 103 of 113 fx.xbr fx graphs root one (AZ-709). |
| `0x00044270` (slot 1) | thiscall(name), RET 4: `m_hitLocation` −1, `m_waterSurface` −2, `m_staffCollision` −3, else, with an anim object (interface +0xC), `anim_node_by_name` (0xCA1D0, the CALL at 0x44355). The swap's X16 takes that CALL. |
| `0x000CA1D0` (`anim_node_by_name`) | thiscall(name), RET 4: the body's markers first (i \| 0x8000), then its bones (i \| 0x4000), byte for byte; else 0. Callers 0x28489, 0x2849B, 0x44355, 0x8C918. |
| `0x00062C40` | Each frame, for each bound transform: slot 2 (0x62CBB), then 0x68DE0 (0x62CC9), which writes each changed translate component into the node and marks it dirty; with +0x68 clear it writes nothing (a +0x69 bone matrix aside). Its callers are 0x6332B and 0x63335, one per bind list, in the fx update 0x632D0, which then runs the graph pass (0x664E0 at 0x6333C: dirty nodes in index order, each node's update and then its links). 0x62820's pair (0x62828, 0x62832) has no caller and no pointer anywhere in the XBE [inferred: dead]. |
| `0x00044370` (slot 2) | thiscall(index, &record), RET 8: −1, −2 and −3 have their own paths, other values ≤ 0 clear +0x68, and an index above 0 goes to `anim_node_transform` (0xCCDF0, the CALL at 0x44389; ECX the anim object, EDX the index, EAX the record). The swap's X16 takes that CALL. |
| `0x000CCDF0` (`anim_node_transform`) | A marker (0x8000): its T, Q and S into the record's +0x50, +0x40 and +0x5C, +0x68 = 1, +0x69 = 0; a bone (0x4000): the same and its matrix (+0x69 = 1); anything else (0, 0xC000) clears +0x68 and +0x69. Plain RET. |
| `0x00089300` (`wing_flap`) | Adds 1 to the flap counter (entity +0xD8, 0x8937B) and asks for anim 17 `superjump` (0x89412). The entity is the critter's PlayerControl, critter+0x180 = the bind interface's +0x10. |

On garret4 the bind finds his marker `m_jump`, and `superjump`'s Z pulse resets `Wing_timer` on each flap; on any other body slot 1 returns 0 and the wings never restart. X16 (`azurik_mod/patches/player_model/README.md` § `wings.c`) returns 0xC000 from the first CALL for the player's `m_jump` and poses it from the second: (x, −4, 5) on the first evaluation after a flap, (x, −4, 0) otherwise, x garret4's own X in the anim the critter plays (critter+0x200, written at 0x4296C: 2 in 17, 1 in 15 and 16, 0 else; Step 2.134b). `Wing_timer`'s update (0x6BAD0, esi its attributes: +0 start, +4 stop, +8 rate, +0x14 reset, +0x18 current) stores current := start while the reset is nonzero (0x6BAF5) and current := stop once at or past stop (0x6BB9C-0x6BBAA), both without the dirty bit; only a step under stop sets it (`or [edi+0x10], 0x80000000`, 0x6BB6E) [verified static]. So with X held at 2 the window stays [1.8, 10.333] and the stroke ends 4.27 s after a flap in its raised end pose.

#### How a pose is built (Step 2.87, 2026-10-15)

[verified static: the 2.78 retarget research's three studies (read-only `ghidra-serve` copies, capstone), the call order re-read with `azurik-mod xbe dis` for Step 2.87; the rule checked in Python against every garret4 and balthazar_airship bone's inverse bind (`docs/RE_DATA.md` § "Character bodies")]. The player-model swap's bake (`azurik_mod/assets/retarget.py`, `docs/PATCHES.md` § "Player model swap", B) models these exactly.

| VA | What it does |
|---|---|
| `0x000CB730` | The bone pose pass (argument the anim; callers 0x40CE7, 0x43A51, 0x8CC85). Per layer (EBP), in order: fills the layer's scratch with each bone's rest values from the posed body's records (+0x30..+0x54: T, q, S); evaluates each bound track (table index not −1) with 0xD8300 at 0xCBA75 into scratch[10 × bone + component], so an unkeyed component keeps the posed body's rest; normalises q; then blends the layers by weight (T and S a weighted sum, q through 0xA0B70's slerp at 0xCBBE8) and builds the matrices (0xCB550 at 0xCBC62). |
| `0x000CB550` | Per bone, the local matrix from the blended T, q, S (0xCA470 at 0xCB5CB, RET 4). |
| `0x000CA470` | The local rotation JO × q × RA, Hamilton, JO the record's +0x20 and RA its +0x10 (two calls of 0xA03F0, at 0xCA4B1 and 0xCA4BE, which returns its operands' product in reverse order), to a matrix (0xA0770); its rows scaled by S and the translation in the last row; world = parent world × local (−1: the root matrix). Callers 0xCAAC0 and 0xCB5CB. |

**The per-bone CALL, and 0x42200 inside the pose (Step 2.156, 2026-10-22)** [verified static: capstone, both releases; L2: `tests/test_player_jiggle.py`]. 0xCB550 (stdcall(4)) has two callers, the pose's blend path at 0xCBC62 and the rest path 0xCB5F0's at 0xCB725 (from the pose pass 0xCB7F9 and the marker pass 0xCBD12, when no layer is weighted); its loop calls `anim_bone_matrix` (0xCA470, Europe 0xCA5F0) at 0xCB5CB (Europe 0xCB74B) with EBX the anim, ESI the bone's offset (0 at bone 0: `xor esi, esi` at 0xCB563; the root path's JMP at 0xCB5A4, Europe 0xCB724, lands on the CALL), EAX the runtime bone, EDI the parent's scale and the parent's world pushed; 0xCA470 keeps EBX, ESI, EDI and EBP, pops it (RET 4) and leaves the x87 stack empty, and 0xCB550 reads no other register after. `critter_model_matrix` (0x42200) isn't read-only: its aligned-node term 0x402E0 runs the marker pass 0xCBC80 on the critter's own anim (0x4030B) when +0x17C, +0x1F8 and +0x204 are all set (every climb-over and hoist), so a call inside the pose stamps anim+0x30, re-runs the layer update 0xCB370 at the same clock and, with a layer weighted, builds no bones (the anim step's own marker pass at 0x43A62 then skips); with none weighted it rebuilds every bone through 0xCB5F0 -> 0xCB550 [L2: the nested 0xCB550 counted]. X26's hook at 0x42253 rewrites its two latch words on every call. The stack allocator's arena is 64 KB (0x58EEC mallocs 0x10000 for 0x1BF3F0 and 0x1BF3F4; its other writer 0xB78C0 has no caller), against a nested marker pass's markers × 48 B on a pose's 40 B a bone. X41 (`azurik_mod/patches/player_model/README.md` § `jiggle.c`) hooks 0xCB5CB. An anim layer's rate is its +0x20 (0x30940 writes the active one's, the walk slots' each tick through 0x30D90). In L2 the vanilla pose pass costs 65,065 instructions for booblord's rigged female_2 (an NPC's 506 more through X41's tail calls).

#### The load runs and the 40 MiB budget (Step 2.158, 2026-10-22; Step 2.162)

[verified static on USA's XBE with the `xbe` verbs; the budget measured in xemu, Step 2.158's reads and Step 2.162's; `docs/XBR_FORMAT.md` § "Load runs and the 40 MiB budget" has the format side and the levels' numbers]

| VA | What it does |
|---|---|
| `0x000A4C00` | The run builder: back by TOC index to the nearest page-aligned row (0xA4C30-0xA4C3D), forward while a row starts in that page (0xA4C60-0xA4C71), the head's offset to the last member's end read as one block (0xA4CF4). |
| `0x000A4890` | The run allocator (mode, level): the size rounded up to 4 KiB; mode 1 contiguous write-combined (MmAllocateContiguousMemoryEx at 0xF4EB0), mode 0 virtual (0xBAB60); both refused when `[0x1BF400]` (used) plus the size passes `[0x1BF404]` (the limit). A refusal (0xA4920) evicts and retries, so with the limit full a session refuses thousands of runs and no load fails: a1's save, its menus and inventory, e2 and w1 with a 15.79 MiB player body took 21,107-26,814 refusals at 40 MiB and 8,342-8,759 at 42, its inventory holding 0.80-1.49 MiB of interface.xbr against 2.78-3.46 (Steps 2.162 and 2.162b). Mode 1's compare (0xA48E5, Europe 0xA4A65) precedes its CALL at 0xA48FA, which `qol_memory_upper64_gpu` hooks, so with that pack a run is weighed against what the low runs leave of the limit though it would go high [measured: Step 2.162k's sitting at 128 MiB and 42: a 42.34 MiB player mesh run refused at 0xA48E9 with `[0x1BF400]` 0, the save's load never finishing; with a 41.45 MiB one fallen back low, w1's 0.65 MiB runs refused, 58 times, 29 of their loads failing; at w1 `[0x1BF400]` holds 1.00 MiB that no run accounts for, 0xB54FB's `run_pages_alloc` [inferred]]. Since Step 2.162m (D616) the pack also hooks the compare's rounding `and esi, 0xFFFFF000` at 0xA48DD (6 bytes; Europe 0xA4A5D; no branch into 0xA48DE-0xA48E2), where a run that fits the upper heap gets ECX := -size, so 0xA48E3's `add ecx, esi` gives 0 and the compare passes; a run that fits nowhere high is weighed as vanilla's [L2: `tests/test_memory.py`; measured: Step 2.162m's premise rows at 128 MiB, the 41.45 MiB body 0 refusals at 0xA48E9 at w1 (54 without the hook, Step 2.162l's sitting), w1's 1.00 MiB `run_pages_alloc` user (0xB54FB, held to 0xBAB8B's compare) refused 11 times at 0xBAB8F by the re-measure sitting, each retry (0xB5510) freeing resident runs to no effect (0xA6450), so w1 held 18.10 MiB of mode-1 runs high against 30.82 with the 40.88 MiB run's body, which kept a1, w1 and e2 whole; no body's mesh run went high at 128 MiB, only the level's runs; Europe's 41.45 MiB body 0 refusals at 0xA4A69, 0xBAD0F and 0xA4E8F, its mode-1 CALL 0xA4A7A counting 2,384 calls past the boot, the 42.34 MiB run, larger than the heap's 36 MiB free span at a1's save, still refused twice at 0xA48E9 and the save never loading]. |
| `0x000BAB60` | `run_pages_alloc` (stdcall 4, the size): a mode-0 run's memory, the size rounded up to 4 KiB, refused (0) past the budget, VirtualAlloc's reserve (64 KiB-rounded) and commit, the size added to `[0x1BF400]`. Callers: the run allocator's mode-0 path at 0xA490C (the spinlock `[0x1BF538]` held, 0xA48A0-0xA4918) and 0xB54FB, 0xBACF8. Europe 0xBACE0 (0xA4A8C). |
| `0x000BAD10` | The run free (ESI the run, EAX its size, `[esp+4]` the mode; RET 4), under the same spinlock: mode 1 `MmFreeContiguousMemory` (0xBAD46), else `VirtualFree` (0xE0B48) at 0xBAD55 (Europe 0xBAED5); either way the rounded size comes off `[0x1BF400]` (0xBAD5A-0xBAD6D) before the lock's release at 0xBAD72. Nine callers (0xA4F17 ... 0xB545C). |
| `0x000B5CC0` | The stream pump's start, from a stream open (0xB5D00's one call, 0xB5F79): the wake event `[0x1BF548]` made once (CreateEventA), then `CreateThread` (0x8000-byte stack, the pump 0xB5940) at 0xB5CED (Europe 0xB5E6D), its handle stored at `[0x1BEFEC]` and `[0x1BF544]` := 1 unchecked (0xB5CF2-0xB5CFE). The pump exits after 2 s idle (0xB5AA6) and clears `[0x1BF544]`; an open while it runs only sets the event. A NULL thread (free memory near 0 at a level change) leaves the flag set with no pump: the main thread waits in the run loader (0xB13B0 from 0xA4FB4), the stream reader in 0xB5740, "Loading..." for good (AZ-687) [measured: Step 2.162c, rows RH5 and FR-cnull; a retry at 0xB5CED released it, FR-cretry]. The stream open holds the stream lock `[0x1BF540]` (0xB5F04-0xB5F85) across this call. `qol_memory_budget` retries the call for up to about 5 s (Step 2.162e). |
| The upper 64 MiB | On a 128 MiB machine NV_PFB_CSTATUS (0xFD10020C) reads 0x08000000 (0x04000000 at 64), but our kernel manages 64 MiB and leaves PDE[0x210..0x21F] (VA 0x84000000-0x87FFFFFF, at 0xC0300840 through the self-map) 0, so phys 0x04000000-0x07FFFFFF is unused. The guest reaches it by writing those PDEs (4 MiB pages, 0x040000E3 + k × 4 MiB) and reloading CR3; NV2A BAR1's upper half (0xF4000000) is not CPU-reachable as booted (the AGP bridge's window ends at 0xF3FFFFFF). DirectSound translates high run addresses for the APU (`MmGetPhysicalAddress`), which reads RAM addresses fine; D3D translated none (mode-0 runs only) [measured: Step 2.162c's routes and sitting]. `qol_memory_upper64` (Step 2.162e, D520) hooks 0xA490C and 0xBAD55 to place mode-0 runs there outside `[0x1BF400]`; seen in xemu at Step 2.162e's sitting (`d7cac9740`: at 128 MiB 11-15 MiB of runs above 64 MiB, uncounted, every level up; at 64 MiB nothing changes) and as a default at Step 2.162f's (`08f71b6f3`). Since Step 2.162n (D625) the heap (`heap.h`) places a mode-0 run at the highest free pages of its blocks (from 0x87FFE000 down) and a mode-1 run at the lowest (from 0x84000000 up), so a body's mesh run takes the span between them. |
| The 128-256 MiB tier (T3) | xemu at `mem_limit` 256 (v0.16.2) has RAM to 0x0FFFFFFF, but NV_PFB_CSTATUS reads 0x08000000 there as at 128 and BAR1 stays 0xF0000000-0xF7FFFFFF, so no register tells 128 from 256 [the fork's PART-12 answer, s2]; the kernel still manages 64 MiB and leaves PDE[0x220..0x23F] (VA 0x88000000-0x8FFFFFFF, 0xC0300880 through the self-map) 0. `qol_memory_upper256` (Step 2.162l, D600) probes a word: through PDE[0x23F] := 0x0FC000FB (uncached) it stores at phys 0x0FFFF7FC, 128 MiB above the upper heap's W2 (0x07FFF7FC), reads it back and checks W2 after each store; RAM answers at 256, a hole (writes dropped, reads 0) at 128 in xemu, and a machine that folds at 128 MiB would put it on W2. Where RAM answers it maps the 32 PDEs (0x08000000 + k × 4 MiB, 0x...E3) and the default packs place runs there after T2. Its hook is the mode-1 path's `lea esi, [edi+0xfff]` at 0xA48D7 (6 bytes; Europe 0xA4A57), the size's rounding inside the straight-line budget compare 0xA48CC-0xA48E7 (`mov ecx, [0x1BF400]`, `mov eax, [0x1BF404]`, the lea, `and esi, 0xFFFFF000`, `add ecx, esi`, `cmp ecx, eax`, `jbe 0xA48ED`; no branch into 0xA48D8-0xA48DC), under the spinlock held 0xA48A0-0xA4911: the probe runs there, just before `qol_memory_upper64_gpu`'s hook on the `and` at 0xA48DD gives a run that fits the heap, T3 included once mapped, ECX := -size, so the compare sees 0 (Step 2.162m; until then the hook at 0xA48D7 did both) [verified static: `xbe dis 0xA48D7:3`, `region_map.py find 0xA48D7 6`; L2: `tests/test_memory.py`]. |
| `0x000F4EB0` | `XPhysicalAlloc` (stdcall 16: size, address, alignment, protect): MmAllocateContiguousMemoryEx(size, 0, -1 or the address's top, alignment, protect), SetLastError(8) on NULL. The run allocator's mode-1 path calls it at 0xA48FA (size, -1, 0x1000, 0x404: PAGE_READWRITE \| PAGE_WRITECOMBINE), the only live run path to contiguous memory; the run free's mode-1 arm calls `XPhysicalFree` (0xF4F09, the import thunk of MmFreeContiguousMemory) at 0xBAD46. The budget compare (0xA48CC-0xA48E7) runs before the call; 0xA4903 adds ESI (the rounded size) to `[0x1BF400]` and 0xA492F pops it. Europe 0xF51D0 (0xA4A7A), 0xF5229 (0xBAEC6) [verified static: `xbe dis`, Step 2.162g's design]. `qol_memory_upper64_gpu` (Step 2.162h, D576) hooks both CALLs. |
| `0x001249A0` | `D3DResource_Register` (stdcall 8: the resource, a base): Data := (Data + base) & 0x3FFFFFF, except a push buffer's (common & 0x70000 = 0x20000), whose Data stays a VA. The game calls it at 14 sites with base a self-relative pointer into run memory, so a run at VA 0x84xxxxxx gets offset 0x00xxxxxx, low RAM, unless the mask is widened. `pbrw` runs are registered as 0x20001 and run by `D3DDevice_RunPushBuffer` (game calls 0x8EE42, 0x90F4F), which pushes a JUMP to (Data & 0xFFFFFFF) + 1 (0x1252DC). D3D holds 22 `and reg, 0x3FFFFFF` (Europe 23, its KickOff's second PUT path 0x129111): live are SetTile 0x11F8F8 (ECX; Europe 0x1203D8, EDX), D3D_CreateTexture 0x121390, the level surfaces 0x123EE5 and 0x1240D3, 0x123F2C, 0x123FBD, 0x124047, CreateVertexBuffer 0x124360, Register 0x1249BD, KickOff 0x12A3B8 and the DMA classifier 0x12D497; the other 11 have no reference. Only Register's and the level surfaces' see run memory; the CPU turns an offset back with `or reg, 0x80000000` (45 operands), so 0x04xxxxxx becomes 0x84xxxxxx, the heap's VA [verified static: Step 2.162g's design]. `qol_memory_upper64_gpu` widens all of them to 0x0FFFFFFF (0x7FFFFFF until Step 2.162l; the same output for every input below 128 MiB, and a T3 run's right offset to 256 MiB: the forms `or 0x80000000`, `& 0x0FFFFFFF` and `(VA & 0xF0000000) == 0x80000000` hold for a 1:1 map to 256 MiB). |
| `0x0012D4AB` | `CMiniport_CreateCtxDmaObject` (ECX the miniport; handle, class, base, limit, out): stores the limit `[ebp+0x14]` at RAMIN + 4 (`mov eax, [ebp+0x14]; mov [ecx+0x700004], eax`, 0x12D552-0x12D55A; Europe 0x12C539, 0x12C5D7). D3D creates 11 objects at 0x12B32B-0x12B45C: handles 3, 4, 5, 6, 9, 0xA and 0xB with base 0 and limit 0x03FFAFFF (pushed at 0x12B31E, 0x12B335, 0x12B34F, 0x12B366, 0x12B385, 0x12B3AA, 0x12B44F; Europe 0x12A2F6-0x12A421), 2 and 7 limit 0x1F, 8 limit 0x20, 0xC base 0x80000000 limit 0x10000000. Bindings (0x12AB43): NOTIFIES 2, DMA_A, DMA_B, VERTEX_A and VERTEX_B 3, STATE 4, COLOR 9, ZETA 0xA, SEMAPHORE 8, REPORT 0xC; handle 6 is the channel's push buffer object (0x12B468 into 0x12D073, written to NV_PFIFO_CACHE1_DMA_INSTANCE at 0x12FBB8). xemu (v0.16.1) cuts only a DMA base to 27 bits and asserts an offset under the limit: textures (`texture.c:100`) and vertices (`vk/vertex.c:594`) under a real renderer, the pusher ("Dma value is out of range") under any, so data past 0x03FFAFFF aborts it [verified static: Step 2.162g's design and its skeptic]. `qol_memory_upper64_gpu` hooks 0x12D552 and gives 0x03FFAFFF 0x0FFFEFFF on a 128 MiB machine (0x07FFEFFF until Step 2.162l; past a 128 MiB machine's RAM, inert in xemu, whose `nv_dma_map` checks no base plus limit and whose readers check only offset < limit). Seen in xemu (Step 2.162h's sitting, runs above 64 MiB): with the seven limits as given xemu aborts at `texture.c:100` under Vulkan and at `pfifo.c:676` under the null renderer; with only handle 6's raised the null renderer runs and Vulkan still aborts at `texture.c:100`, so the pusher reads through 6 and the textures through another (3 by the bindings). |
| `0x0012C18B`, `0x0012C1E8`, `0x0012C289` | D3D's surface locks with the TILED flag 0x40 OR 0xF0000000 into the pointer here (Europe 0x12B18B, 0x12B1E8, 0x12B289; Lock2DSurface 0x12C1A0 and Lock3DSurface 0x12C240 [Step 2.162g's names]), BAR1's view, whose AGP window ends at 0xF3FFFFFF, so a resource above 64 MiB locked TILED would get a pointer whose stores drop. The game's TILED locks: 0x8F971 (a surface D3D makes at 0x8FDA9, allocated below 0x3FFB000), 0xF58CE (the XPR writer), D3DX 0x168C7C and 0x169297. D3D's own allocations (15 sites a release, HighestAcceptable 0x3FFB000; the kernel clamps to page 0x3FDF) stay low, as do SetTile's tiles [verified static: Step 2.162g's design and its skeptic]. In Step 2.162h's sitting (boot, inventory, pause, a save anywhere, a warp) a save ran 0xF58CE twice and the D3DX two twice each, all on low VAs, and 0x8F930 (with its lock 0x8F971) never ran. |
| `0x000596C6` | Sets `[0x1BF404]` to 0x2800000 (40 MiB) once at boot, holding the spinlock `[0x1BF538]`. Europe: 0x59706, `[0x1C13A4]`. The limit reserves nothing: `[0x1BF400]` counts the resident runs' bytes, each run is its own kernel allocation, and every compare on the two is unsigned. `qol_memory_budget` (Step 2.162b, D515) rewrites the imm32 at 0x596CC (Europe 0x5970C). |
| `0x00058D00` | The memory check (5 calls in the game loop, 0x59BB2-0x59CB3; it also advances the run-use stamp `[0x1BE36C]`): lowers the limit by (1 MiB - free physical) and evicts when GlobalMemoryStatus's free physical memory is under 1 MiB (the trim line: the 0x100000 of the instructions at 0x58D1F, 0x58D30 and 0x58E24; Europe 0x58D3F, 0x58D50, 0x58E44). It never fires at 40 MiB in xemu (64 and 128 MiB machines). With a raised limit (44-52 MiB, Step 2.162's rows) it cuts the limit, to 42.38 MiB at the lowest, and nothing raises it again that session: 44 held through a1's inventory and fell to 42.38-42.49 at the e2 and w1 changes; 48-52 were cut already at a1, some 48 rows keeping 43.07-43.64 to the end. At 42 it never fired (Step 2.162b's sitting: 16 rows and 10 save loads, all 22 levels, USA and Europe): the lowest free physical memory at an allocation or a check was 1.14 MiB, at w1's load after e2 with a 15.79 MiB player body, against 3.13-3.46 at 40 (the same load) and 0.00-0.01 at 44 (e2's load, where the check cut the limit). A per-vblank read of the free pages misses that low (2.62-2.64 MiB in the same rows): the level loads inside the warp, before the frames read. |
| `0x000FC930` | The run descriptor pool's static initializer: `mov eax, 0x1388` at 0xFC931, 5000 descriptors (constructor 0xA6BD0, list head 0x37BE48); every resident run takes one, and with none free 0xA4CB4 evicts and retries. Descriptor ids are int16 (0x8000 none), so at most 32767. At the runs' average size it binds only past about 90 MiB of runs [inferred]. Europe 0xFCC61 (constructor 0xA6D50, pool 0x37DDE8). |
| XBE header +0x124 | The init flags: 0x5 in both releases; 0x4 is XINIT_LIMIT_DEVKIT_MEMORY [SDK]. The title has 64.0 MiB on xemu's 128 MiB machine as on its 64 (GlobalMemoryStatus's total too), and clearing 0x4 changes nothing: our flash's kernel is built for 64 MiB (TotalPhysicalPages 0x4000 at 128) [measured: Step 2.162's LIVE rows; static: PAST128.txt]. So a budget's room comes out of 64 MiB. |
| `0x000A64D0` | Eviction: runs no one references (refcount +0x18 = 0) and not used this frame, first the list 0x1AA7F0, then (level >= 3) the 30-slot expiry wheel 0x37BD00-0x37BDF0, then the allocation is retried; with nothing to evict the run builder returns 0 and sets `[0x1BF5A0]` = 2. |
| `0x0003F16D` | The body draw's `test edi, edi; je 0x3FFFE`: a LOD whose `bmsh` lookup (0xA67A0, or 0xA6860 for a resident run) is 0 isn't drawn. A missing `gshd` skips its group (0x3F227). |

#### STLport's node allocator and the sound thread's race (Step 2.172, AZ-695)

[verified static on both releases with the `xbe` verbs; the race seen by the xemu fork's QMP access log (AZ-628's reply, 2026-10-23); L2: `tests/test_memory.py`; seen fixed in xemu v0.16.1, Step 2.172's sitting (AZ-695's entry)]

| VA | What it does |
|---|---|
| `0x001AAC20` | STLport's 16 global free lists, one head per 8-byte size class (8-128 B; `[0x1AAC20 + 4 * ((n - 1) >> 3)]`, the 32-byte list's at `[0x1AAC2C]`), and before them `_S_chunk_alloc`'s heap size, pool end and start (`[0x1AAC14]`, `[0x1AAC18]`, `[0x1AAC1C]`). Europe +0x1F98 (`[0x1ACBC4]`). No lock: every pop and push is inline, a load of the head and a store; 1329 instructions per release address them. |
| `0x000185E0` | `__node_alloc::_S_refill` (EAX = size, ECX kept): 20 blocks from `_S_chunk_alloc` 0x18730 (which takes malloc's memory, unlocked too), the head stored at 0x18613 and the other 19 linked after it. The hub calls it "vector allocate". |
| `0x000AB5B0`, `0x000AB580` | `malloc` (cdecl, the size) and `free` (EAX = the block; a NULL returns), RtlAllocateHeap / RtlFreeHeap on the process heap `[0x390A78]`, made at 0xE6AC8 with flags 2 (HEAP_GROWABLE, no HEAP_NO_SERIALIZE): the heap takes its lock (0xE499A). STLport's deallocate frees a block over 128 B with it (0xC49E2). Europe 0xAB730, 0xAB700. |
| `0x000AE450` | The sound thread (made at 0xADFC9 by the DirectSound init): waits on its event, enters the critical section `[0x1BEFAC]` and calls each stream's +0x40 update, which keeps the `std::map` at 0x37BC24 (a 3-dword key, 32-byte nodes). The map's only list sites at run time: `_M_insert`'s pop at 0xAF322 (in 0xAF2D0, its refill call 0xAF33A), `create_node`'s at 0xAF3B0 (refill 0xAF3C8) and `erase`'s push at 0xAE76C (in 0xAE750); its header node comes from the list once at startup (0xAE6E7), and 0xFFABC (the atexit destructor) and 0xAF050 run only at exit. Seven more sites of the module are dead code. The thread's code reaches no other list. Europe's module is +0x180. |
| `0x000C49ED` | The load thread's free of an 8-pointer vector's block to its list (ECX the list): the head loaded at 0xC49ED and stored at 0xC49FD. The fork caught a thread switch between them: the sound thread popped the head for a map node, the stale head went back, and the map's lookup 0xAF160 later followed a pointer the load thread wrote, bugcheck 0x1E at 0xAF173 (0xAF32B on the retail disc, about 1 schedule in 320; both threads at IRQL 0 with interrupts on, so a console can take it [the fork's inference]). |

`qol_alloc_race` (on by default) rewrites the map's three spans in place to call `malloc(0x20)` and `free`, so the sound thread uses only the serialized heap and shares no list with any thread: 71 bytes, no shim. The heap path is the one vanilla's refill already takes from this thread (refill, `_S_chunk_alloc`, malloc), under the same critical section.

**The two other threads with list sites share no list either (Step 2.172b, AZ-729)** [verified static on USA: direct calls and switch tables followed]. 0xB0C70 is the disc cache's copy thread (made at 0xB0F04 by the file system's init 0xB0DE0): it copies a file from the DVD to `z:\gamedata\` through a `DvdStream` (vtable 0x19A71C, opened by 0xB5D00). 0xD12B0 is the loading screen's draw thread (made at 0xD1021 by 0xD0EE0 at the first loading screen, the title's at boot): while `[0x1BF50C]` > 0 it draws a frame every 20 ms, and after 4 s the loading picture and hourglass through the sprite draw 0x97420. Their list sites sit on two paths, plus a fatal-only one (below the table), and neither of the two runs after the CRT's C++ static initializers (the table 0x1A29B0-0x1A41A4, walked at 0xE730D), which run before either thread exists:

| Path | Why it touches no list at run time |
|---|---|
| The resource-type map `[0x1BEF78]`'s `operator[]` 0xAA140 (the 16-byte pop at 0xAA17E; the rehash 0xAA9C0 and its buckets 0xAAD70), from the run eviction 0xA6450 (the copy stream's buffer retry 0xB5490), the run free 0xA4E60, the run touch 0xA6530 and the run builder 0xA4C00 | 829 of the 830 registrations (0xA92C0) are static initializers; the 830th (0x11773) is in a stub that nothing calls, jumps to or points at. Each registration ends with a lookup at its final count, so the buckets stay above the count and the rehash test (0xAA9DB) never passes again. A missing key is fatal (0xA9100, "unknown resource typecode"). |
| The cvar registry's growth 0x9FDC0, from 0x9D270's "low-res textures" cvar (once per boot, guard `[0x38E05C]`) | 58 static initializers register 58 distinct cvars first, so the registry has 64 slots (256 B), and its growth allocates and frees on the serialized heap (blocks over 128 B), never on the lists. |

Their indirect calls reach no other list except on that fatal path. The `DvdStream` slots touch none. The out-of-memory handler table `[0x1BEF80]` holds only 0xA66A0 (the run eviction, as above; its other registrar 0xAB4A0 has no caller). A type's load callback +0xC (called at 0xA586A, where the loading thread drains the pending-run list `[0x1AA7F8]` through 0xA58A0) and unload callback +0x14 (called at 0xA6425 by the copy thread's eviction) have dead setters (0xA9950 and 0xA99A0) and are zeroed by 0xA92C0, but main sets them by direct stores after the file system's init [verified static: review.txt D1, results/review_*]: unload 0x9C8E0 at 0x597FE, 0x9D1D0 at 0x5983F and 0xC5900 at 0x5987A, and in 0xD5860 (called at 0x59884) one type's load 0xD5830 at 0xD58A9 and unload 0xD5850 at 0xD58E0. The first three only wait on `D3DResource_BlockUntilNotBusy`. 0xD5850 (0xA61B0) reaches only the map's lookups above. 0xD5830 (0xA6110) touches the 24-byte list `[0x1AAC28]` (0xA6020 -> 0xA71F0) only when its asset is missing, on its way to the fatal 0xA9100, which loops on Sleep forever: the fatal-only path. The rest is kernel, XAPI, CRT and D3D code [inferred: none of it uses STLport's pool].

**The copy thread does share the run lists with main, unlocked (Step 2.172c, AZ-814; its buffer path fixed by `qol_alloc_race` since Step 2.172d, the rest AZ-817)** [verified static on USA with the `xbe` verbs; Europe's sites scanned only]. A resident run's descriptor links (+0/+4) put it on one list at a time: a slot of the 30-slot expiry wheel 0x37BD00-0x37BDEF (circular, 8-byte heads, the cursor `[0x1BE324]`), the expired list 0x1AA7F0, the held list 0x1AA7E8 or the free descriptors 0x37BE48. None of the list operations takes a lock: the touch 0xA6530 (a run whose refcount +0x18 is 0 goes to slot (cursor + horizon) % 30; 0xA6594 skips any other), main's advance 0xA62B0 every frame (the cursor's slot onto 0x1AA7F0), the pin 0xA6110 (refcount + 1, onto 0x1AA7E8, which no eviction walks), the run free 0xA4E60 and the evict 0xA6450. The spinlock `[0x1BF538]` covers only the pages and the budget, and every holder releases it before it evicts (0xA4918, 0xB5507, 0x58DDD).

| Thread | How it reaches the lists |
|---|---|
| 0xB0C70, the copy thread | Every stream open (0xB5D00 at 0xB06C5, after 0xB0D8F releases the queue mutex `[0x1BEFE0]`) takes a 1 MiB buffer through 0xB5490 (0xB5ED5). When `run_pages_alloc` (0xB54FB) refuses it against the budget, it evicts the expired list (0xB5519) and, if that freed nothing, the wheel's slots from slot 0 until the buffer's size is freed (0xB5524-0xB5546), each run unlinked and freed (0xA6450 -> 0xA4E60) while main advances, touches and evicts the same lists. Its stream's heap failure (0xB5D35) evicts the wheel through 0xA66A0 too. Copies are queued by the level load (0x538AF) and the run loader 0xB13B0, while main's own loads fill the budget [inferred]. The retry runs in xemu: 11 at 0xB5510 in Step 2.162m's skeptic rows, its thread not recorded. |
| 0xD12B0, the loading screen | Its draw looks up only the loading picture and the hourglass, which 0xD0EE0 pins (0xD0EFD, 0xD0F25, 0xD0FC0) before it starts the thread (0xD1021) and nothing unpins, so its touches skip them and never relink. It reaches the lists only on out-of-memory paths (D3D's 0x906A0 once per boot, guard `[0x1AAB59]`; malloc's handler 0xA66A0) and through the pending-run drain 0xA58A0 (0xA67F0 -> 0xD5830 -> the pin) while a pinned picture's first read is undrained, at the first loading screen [inferred]. |

Any thread whose malloc fails evicts the wheel the same way (malloc 0xAB5B0 -> 0xAB4C0 -> 0xA66A0 -> 0xA64D0). A run freed or relinked by one thread while another walks or relinks its list can lose nodes, leave a freed descriptor linked or put a run on two lists, its pages freed while a list holds it [inferred, not seen]. Europe has the wheel at +0x1FA0 (0x37DCA0, the cursor `[0x1C02C4]`), the expired list at +0x1F90 (0x1AC780) and the copy stream's slot walk at 0xB56A4.

**The fix (Step 2.172d, `qol_alloc_race`)** [verified static, in L2 and in xemu v0.16.4]: the copy thread's stream is the only one 0xB5490 serves with read-ahead 0 (0xB06C5; the movie opener 0xD0074, on main, asks for 0x200000; 0xB5FA0, 0xB5FC0 and 0xCF8F0 have no caller), and 0xB06B0 treats a NULL stream as fatal (0xB06D0 -> 0xA9100), so the open must get its buffer. The pack rewrites the buffer loop 0xB54D0-0xB5554 (133 bytes; Europe 0xB5650): a refused read-ahead-0 buffer enters `run_pages_alloc` past its budget test (0xBAB94: ECX = the size rounded to 64 KiB, [esp+4] = the page-rounded size; Europe 0xBAD14) inside the same page lock, so its pages are committed past the budget, counted in `[0x1BF400]` and freed by the stream's close (0xB5420 -> 0xBAD10) as vanilla's are, and the copy thread evicts nothing. Every budget reader compares used + size <= limit, and the memory check 0x58D00 skips its limit lowering while used is past the limit (0x58DA6), so none breaks; a run main allocates while used is past the limit evicts on main's own thread. One copy stream is open at a time, so the overshoot is at most 1 MiB, and the stream's close returns it. Only when the kernel refuses that commit too does vanilla's eviction run (the same liveness as vanilla's). Rejected: a sleep and retry (main waits on the copy in the run loader 0xB13B0, SignalObjectAndWait at 0xB14E1, and at exit on the thread's handle, 0x59F2E: a hang), a lock around the run manager (0xA67A0 waits on an event while it drains) and failing the open (fatal). With the pack the loop's call of `run_pages_alloc` is at 0xB54ED, the past-budget call at 0xB5505 and the evictions at 0xB5523 and 0xB5539. Left (AZ-817): the out-of-memory evictors off main (0xB5D35 and any thread's malloc through 0xA66A0, D3D's 0x906A0) and the refused commit's fallback; while main waits on a copy its memory check doesn't run, so the 1 MiB stays past the budget for the copy's life. Seen in xemu (Step 2.172d's sitting; its skeptic upheld every row): with the limit poked down to used at a copy's first `run_pages_alloc` call, each refused copy buffer ran 0xB5505 -> 0xBAB94 with 0 evictions from the copy thread, where the parent build evicted 19 times; vanilla's own 40 MiB refusal went 0.17 MiB past the budget (main's memory check saw it, lowered nothing and evicted nothing), a forced one 1.0 MiB for four frames while main sat in 0xB14E1, and each time the stream's close took it back, not main; the 33 lists' walk stayed whole (5000 descriptors) and every load ticked at the parent's frame; 0xA66A0 and 0x906A0's evicts stayed at 0 on both builds.

**The copy gate (Step 2.172g, `qol_alloc_race`, AZ-817)** [verified static on USA with the `xbe` verbs, in L2; Europe by `scripts/region_map.py check`]. Out-of-memory evictions run on whatever thread failed: the handler table `[0x1BEF80]` (count `[0x1BEFA8]`, 1: the only live registrar is 0xA6B9A in the run manager's init 0xA6B20, called once from 0x597BC; 0xAB4A0 has no caller) holds 0xA66A0 (`push 3; push ecx; call 0xA64D0`), which 163 inlined `operator new` loops (`call [esi*4 + 0x1BEF80]`), malloc's 0xAB4C0 and the stream object's loop 0xB5D23-0xB5D4C call with ECX = the bytes; 0xA64D0(size, level) evicts the expired list and, at level 3, the wheel's slots until the size is freed. 0xB5D00 (the stream object, 0x34 bytes from the process heap) has two live callers, the copy thread's open 0xB06C5 and the movie's 0xD0074 (on main); 0xB5FA0 and 0xB5FC0 have none. The copy thread 0xB0C70 releases its mutex `[0x1BEFE0]` before each copy (0xB0D10, 0xB0D8F) and pulses `[0x1BEFD8]` after it (0xB0D49, 0xB0DBE); main's only wait on it in play, 0xB13B0's loop, waits on that event with the mutex released (SignalObjectAndWait at 0xB14E1), so main can't wake while the copy thread is inside an open; it can be woken just before one (the pulse after the previous copy) and not yet have run, so "main asleep" read from main's own flags may be stale (Step 2.172g's late review: the gate holds main at its wake until such an eviction ends). The main loop (0x59A60) ticks the run manager once a frame at 0x59C85-0x59CAE (the counter `[0x1BE36C]`, 0xA58A0, the wheel advance 0xA62B0 at 0x59C90, the expired list's evict at 0x59CA9, 0xA5120), after its sound section (0x59C2E-0x59C5D, under the sound lock `[0x1BEFAC]`). 0xA66B0, 0xA66C0 and 0xA66E0 are dead (no call, jump, immediate or data word). An eviction calls each asset type's unload callback (0xA63C0's `call esi`, from the type map `[0x1BEF78]`, whose lookup 0xAA140 can refill STLport's pool, 0x185E0), so it may take locks its thread doesn't hold. The pack sends the copy thread's two evictions (0xB5D35 and its buffer's refused commit) to 0xA66C0, jumped to a gate: on main or before main's first frame it evicts at once; while main sleeps at 0xB14E1 the copy thread evicts at once, main held at its wake until done; else main's tick at 0x59C90 evicts for it while it sleeps, at most 500 sleeps of 1 ms before it evicts itself. The copy thread holds no lock at either site, so main's eviction can't wait on it. Other threads' evictions stay on their own thread: the sound thread works under `[0x1BEFAC]`, which an unload may need, so main evicting for it could deadlock. Seen in xemu 0.16.4-3 in real time (Step 2.172g's sittings r2 and r3) [verified xemu, forced]: a pulse that finds main asleep at 0xB14E1 readies it (KTHREAD+0x2C 5 -> 1) but the copy thread runs on: its next open reached 0xB5D19 (the stream object's alloc) before main ran in 9 of 10 tries (r3; r2's boots 4 of 6), while the buffer's commit (0xBABDA) came only after main had got past its wait in 8 of 8; a 1 MiB eviction forced there (54 runs) ran to its end with main ready and its context-switch count (KTHREAD+0x4C) unchanged, 9 of 9 over two builds. Deterministic (icount) runs never reached the window: main ran first at every such pulse.

#### The camera's target (Step 2.23c, 2026-10-12)

[verified static 2026-10-12: decompiles from a `ghidra-serve` copy of the project, `azurik-mod xbe dis|calls|find-refs|insns` (capstone) and reads of the vanilla XBE's vtables and constants; in game, xemu sitting modelswap3's frames, labelled]

| Function or site | Role |
|----------|------|
| `0x00080820` | The camera base constructor: vtable 0x19C4B8, +0x18C := 70.0 (the field of view [inferred]). Its three subclasses: the level camera (`0x80A90`, vtable 0x19C3D8, built by `load_level_from_path` at 0x53E64), the free camera (`0x82680`, vtable 0x19C218; § "Native cheat UI" below) and a third (`0x822C0`, vtable 0x19C2F8, built by 0x6B5F0). The level camera's target entity is its +0x190; on the free camera +0x190 is a float, the field of view its X restores (§ "The free camera and photo mode" below; Step 2.160). |
| `0x00081240` | The level camera's per-frame update (its vtable slot +0xCC). It asks the target for its camera point through the target's vtable slot +0xB0 (0x81271), reads the active controller (0x37BE98), rewrites its yaw +0x194, pitch +0x198 and distance +0x19C each tick from where it ends (0x81BEF-0x81C81: the yaw from the committed orientation's forward through 0xA08D0 and `fpatan`, 0x81C03-0x81C1D; the pitch from the same orientation through 0x50440, 0x81C2E-0x81C37; the distance |P − camera|, 0x81C3D-0x81C81; the pitch the input block leaves at 0x81B0B feeds 0x4FF10's quaternion at 0x81B17) [verified static: capstone, Step 2.116b's design A, 2026-10-20], and places itself (+0x15C) through 0x80C40 and 0x80FB0 [inferred: collision]. Its clamps: the distance 6–12 m (0x198170 and 0x38BBE0 at 0x814B2) or 0.5–12 m (0x198158, 0x19815C at 0x8190B), the pitch −50° to −35° (0x38BC14, 0x38BC0C at 0x81556) or −81° to +63° (0x38BC18, 0x38BC24 at 0x817FA). Static initializers at 0xFB3A0–0xFB66C set those globals from `.rdata` constants and 0x38BBEC = π/180, so no `config.xbr` cell reaches them. Which branch runs when [verified static: capstone, Step 2.116b's read of the input block 0x813A0-0x81B22, 2026-10-20]: with RT held ([esi+0x34], 0x8147A) and no zoom input the distance eases into 6-12 m (6s-12s under X25) at up to 20 m/s, and with no stick pitch input the pitch eases into −50° to −35° at most 120°/s (0x81548-0x815D3; from the rest's −30° RT goes to −35°); the stick (0x817E6-0x81822) moves the pitch 60°/s × its deflection, clamped −81° to +63°, and writes the wanted pitch +0x1A0; at rest (0x8183D-0x818DC) the wanted pitch is the target's room's +0x2C when its +0x28 flag is set, eased at min(30°/s × the sticks' sum, 60°/s). The distance recovers only while a stick is held (Step 2.104, AZ-520) [verified static]: 0x81952–0x81A02 moves the current distance +0x19C toward the wanted one +0x1A4 at min(10 × the sum of the stick deflections, 10) m/s × dt (the deflections summed at 0x81416–0x81474; 10.0 at 0x198168 and 0x198164), the pitch +0x198 the same way (0x81872), and 0x81C81 resets the distance each tick to the real camera-to-point distance, so a camera pulled in at rest stays in (X25's NOP changes that in a swapped build: § "The rig" below). 0x80FB0 (ESI the camera, ECX the point it aims at; its wanted place is that point less the camera's forward, EDI's quaternion through 0xA08D0, times the distance on the stack: Step 2.107's correction of "ECX its wanted place") sweeps a 0.096 m ellipsoid (`collision_sweep`, 0x60870; radii [0x38BC00], mask 0x40) from the target's body centre (camera+0x190's +0x15C) to the point (0x81061; on a hit the point moves to it) and from the point to the wanted place (0x810F3), and on a hit puts the camera at the hit (0x810FC on: from + (to − from) × the record's +0x18); critters' shape test 0x418B0 ignores mask 0x40 and the zipline cable's 0x8013 faces lack it, so neither stops the camera [verified static]. Its order of work (Step 2.105, AZ-520) [verified static]: 0x80C40, the slide, sweeps the camera's own move (AL at 0x80D71) and puts the camera where the line from the point to the new place crosses the hit plane, failing when that crossing factor falls outside 0.0–1.0 (0x80E34, 0x80E45: 0x1A2508, 0x1A250C) or after 4 slides; a failed slide runs 0x80FB0 at the wanted distance; after one that holds, 0x80C10 sweeps from the camera to the point (`collision_sweep`, mask 0x40, AL at 0x80C3A, RET 8), and 0.8 s blocked (0x19817C, compared at 0x81BAA) runs 0x80FB0 at the current distance. X19 (`player_model/eye_sweep.c`) takes the CALL at 0x810F3, X20 (`player_model/eye_hang.c`) the 10 bytes at 0x81292, where every path goes on from the point's CALL at 0x81271 (into ESP + 0x50). |
| vtable slot +0xB0 | A critter's camera point. Only camera code calls that slot: 0x80A23, 0x81271, 0x821B4 (the level camera's slot +0xC8) and 0x825C3 (the 0x19C2F8 camera's update) are the only `call [reg + 0xB0]` in `.text` (`xbe insns --mnemonic call --operand '+ 0xb0]'`: 4 found). |
| `0x00041F40` | The critter's slot +0xB0 (vtable 0x19FC08): the position and rotation (0x61430), then the body's marker `m_head` (its name pointer 0x1AA2DC, read only at 0x41F57) through `anim_marker_position` (0xCB2A0, the CALL at 0x41F67), 0.5 m lower when `[[0x380E04] + 4]` isn't 0, then into the world by the critter's matrix (0x42200) scaled by its +0x188 (0xA3860 scales the 3×3), then the object at +0x180's slot +0x10 when there is one. |
| `0x000CB2A0` (`anim_marker_position`) | ECX the anim object, EAX float out[3], the name on the stack (RET 4), out back in EAX: the runtime marker (anim+0xC, 0x34-byte entries) whose body record has that name, compared byte for byte, or zeros when the body has none. Callers 0x40320, 0x41F67, 0x4442C, 0x8C986. |
| `0x00081E10` | The level camera's water push (Step 2.23f), called at 0x81BEA every frame, after the camera is placed: `[ESP+4]` the camera, EAX the target point, RET 4. It asks 0x60BD0 for the water depth a0 at the camera's position less 0.4 m (0x198150) in z; when 0 < a0 < 0.8 (the camera within 0.4 m of the surface) it moves the camera in z only to 0.5 m (0.4 + 0.1, 0x198154) on the surface's other side (above when it was under, under when it was above), keeps the new point only if the sweep 0x60870 from the old one is clear (else the other side's, else nothing), then re-aims through 0x820E0 [verified static: capstone, and 0x81E10 run under Unicorn with 0x60BD0 stubbed to report a0 and the sweep clear, 2026-10-12: with the surface 0–0.35 m below the camera (a0 0.05–0.4) it went 0.5 m under the surface, with the surface 0.01–0.39 m above it (a0 0.41–0.79) 0.5 m over it, and a0 0, 0.8 or −50 left it]. Its two candidates are built on the probe point (cam.x, cam.y, cam.z − 0.4, its frame's +0x30..+0x38), so over the surface (a0 ≤ 0.4, 0x81F45) the first is c1.z = (a0 − 0.5) + probe.z = surface − 0.5 (the other side) and the second c2.z = (a0 + 0.4) + probe.z = surface + 0.4 (its own side), under it (0x81EFD) surface + 0.5, then surface − 0.4, x and y the camera's; each goes through 0x81DB0 (`camera_reach`), the first at 0x81FEB (EAX = &c1 at [ESP+0x2C], c2 at [ESP+0x20], ESI = the point's copy at [ESP+0x14], EDI = the out at [ESP+0x50]), the fallback at 0x82036 reading [ESP+0x20]; a clear sweep commits the place to +0x170 (0x8208D), 0x61100 tracks its room and 0x820E0 re-aims. The band and step constants 0x198150 (0.4) and 0x198154 (0.1) are read only inside it (0x81E37–0x81F81). Europe: 0x81DC0, called at 0x81B9A, its candidates' CALLs at 0x81F9B and 0x81FF2 [verified static: capstone, 2026-10-20, Step 2.116b's reads]. X29 (`player_model/water_push.c`, Step 2.116b) takes the CALL at 0x81FEB. `camera_water_push` (a vanilla symbol since Step 2.116e: stdcall(4) with EAX the point, keeps EBX, ESI, EDI and EBP, the x87 stack empty after): its one caller is the update's CALL at 0x81BEA, every tick (Europe 0x81B9A), which X29's latch entry takes (R1) [verified static: capstone, 2026-10-20, Step 2.116d's design `static-callers`]. |
| `0x00081DB0` (`camera_reach`) | The push's candidate place within its reach of the point: out = P + (c − P) as 0x81CA0 clamps the offset (at most [0x19815C], 12 m; at least [0x19816C], 2 m horizontally, read at 0x81D3C; both X25-scaled). A register ABI: EAX = float c[3], ESI = float P[3], EDI = float out[3], a plain RET, EAX = EDI back, ECX and EDX clobbered, the x87 stack balanced. Callers 0x81FEB and 0x82042 (Europe 0x81D60, from 0x81F9B and 0x81FF2) [verified static: capstone, 2026-10-20]. |
| `0x00060BD0` | The volume query (RET 0x18; callers 0x379AC, 0x81EBB, 0x85587, 0x86635, 0x86D32): every volume at a point whose slot +0xA0 answers ORs its flags into the caller's word, and the largest depth below the surface among those with flag 0x100 (water [inferred: the input's swim gate, input+0x135 & 1, is that bit]) goes to its fifth argument, −50 when there is none. The input builder's call at 0x85587 writes the flags into input+0x134 and the depth into input+0x14C, which `player_swim_tick` (0x8B700) reads. The ground, swim, slope, zipline and air cases and the hit's 0x102 call it (0x8D118, 0x8D1CB, 0x8D221, 0x8D26B, 0x8D2B5, 0x8D35F), but climb and the attack moves don't. It swims, writing state 6 at 0x8BD35, when the swim gate is set and either the depth is at least 0.25 m (0x198110) or the player already swims; otherwise it returns 0 [verified static: capstone; xemu, Step 2.23f's probe: input+0x14C read 1.1263 and 2.9596 while swimming and −50 on land]. `volume_query` (a vanilla symbol since Step 2.116e): __stdcall(24) (the tree, float point[3], the asker, the 24-byte flags record, float *depth, touch), RET 0x18 at 0x60E1C and 0x60E2E, no caller cleaning the stack; it fills the flags record itself (0x60BEA-0x60C1A, so the caller's values don't matter), skips the asker in its list (0x60CBE), sends each volume found the touch message (its slot +0xB4, 0x60D6C) only when touch isn't 0 (0x60D1A), writes *depth only when the pointer isn't 0, and nests its scratch list at 0x1BF3F8 (saved and put back). The level camera's water push asks it with the camera as the asker and touch 0 (0x81E41-0x81EBB); X29's latch entry (R1) asks it the same way at the camera's rest place. Europe 0x60B80, the same five callers and frame [verified static: capstone, 2026-10-20, Step 2.116e's design `static-volume-query`, `static-volume-query-europe`]. |
| `0x000820E0` | Re-aims the camera (EBX) at a point (EAX) through 0x821E0, which sets its orientation (+0x17C), yaw +0x194, pitch +0x198 and distance +0x19C, and the wanted pitch +0x1A0 and distance +0x1A4 to the same values (0x8225A, 0x822A8; 0x820E0 writes +0x1A4 again at 0x8218A). So after a push the camera wants the pushed distance and pitch and doesn't ease back to the old ones [verified xemu, Step 2.23f's probe: in the water the wanted pitch and distance equal the current ones, and per frame only 0x80C40's placement, its 0x81B6C path and 0x81E10 ran]. Callers 0x813A8 (the update) and 0x820C4 (the push); 0x821E0's are 0x8215F and 0x821C2; Europe 0x82090 (from 0x81358 and 0x82074) [verified static: capstone, 2026-10-20]. The wanted pitch and distance have no other writers but the pitch stick (+0x198 := clamp(+0x198 − rate × stick), then +0x1A0 := +0x198 at 0x8182C/0x81832, so the wanted pitch it writes is the committed one moved), the room's pitch (0x81855, its +0x2C), the reset (0x8120F, 0x81215; 0x811E0 from 0x81387), the D-pad zoom (+0x1A4 := +0x19C at 0x81943) and these re-aims; right after the push the update re-derives the yaw, pitch and distance from the committed place every tick (0x81C1D, 0x81C37, 0x81C81), and it eases +0x198 toward +0x1A0 only in its input block (0x8185F-0x818DC, with no pitch stick) by [0x38BBE4] (30°/s) × the sticks' sum ([ESP+0x20]), at most [0x38BBF4] (60°/s), skipped when the two are equal (on all 56024 water ticks of 2.116b's rows), so with no stick a pushed camera keeps the push's pitch for good [verified static: capstone, Step 2.116d's design `static-81BEF-81CA0`, `want-scan` and its critique, 2026-10-20]; X29's ease entry (Step 2.116e, R1) takes the dt multiply at 0x81891. |

So the camera aims at a critter's `m_head`, and at its feet when its body has none. Of the 158 bodies only garret4's (at 1.993 m, the top of its 2.01 m bind pose), balthazar_airship's (1.993 m, which none of its clips moves) and fire_elemental's (0 m at rest, but each of its 11 clips moves it, 0.75–2.28 m up) have one [verified: `azurik_mod.assets.characters.read_body` over every body; the clips' `m_head` z tracks, 2026-10-12]. In game (xemu sitting modelswap3, 2026-10-12) [viewed, 1280×960 frames]: the control's head is at the picture's centre at the w1 start, a town_child_1 player's feet are there, and a guard_air player's body, which rises to 5.54 m in its bind pose, shows only its tail at the top of the picture. The player-model swap's X8 shim takes the CALL at 0x41F67 (Step 2.23c, AZ-304; `azurik_mod/patches/player_model/README.md`).

**Where the point lands, and the water (Step 2.23f, 2026-10-12).** On land the world point (`[ESP+0x50]` at 0x81277) is the body's point times its scale less 1 m above the critter's +0x15C, the control's too: its `m_head` (1.9925 m) lands 0.9925 m above it [verified xemu, sitting sight223: every body it ran, the control included]. The level camera then sits at its distance and pitch from it, 5.0 m and −30° when nothing has moved them. It has no swim mode: in the water only the push 0x81E10 acts, and the pushed distance and pitch stick (0x820E0), so whether the camera ends under the surface, where a submerged body shows, depends on how the point and the camera's track meet the surface. A swimming garret4's point is 0.45 m above +0x15C (sight223 and the probe: 0.4487–0.4577); on sight223's route the control's camera ended 0.91 m under the surface at 4.62 m and −20.43° with its body in frame, and loaded from `vanilla-ocean` (the player 1.13 m under the surface) it stayed above the water at 4.98 m and −29.57° with the body out of frame [verified xemu, Step 2.23f's probe; frames viewed, not kept]. X8's top lifted a swapped body's point in the water (keylord 1.97 m, guard_air 2.49 m) and its camera stayed above the surface (sight223: 5.0 m, −30°, the body out of frame), so since Step 2.23f X8 gives a swimming player the game's own point (AZ-307; `azurik_mod/patches/player_model/README.md`). A critter's water depth lives at its +0x27C, a float: how far its +0x15C is under the surface, −50 out of the water. The player's input builder stores its volume query's depth there every tick (0x85587 queries at +0x15C, 0x85593 stores the result; `[esp+0x10]` is the PlayerControl's +0x20, the critter), and 0x379AC's query at +0x15C does too (0x379BF); 0x8664E writes that depth less 1.0 (0x1A9C88) from another query (0x86635) [verified static: capstone, 2026-10-15; which writer runs last in a swimming tick, the input builder, is inferred]. A critter none of those writers queries keeps no depth there: Step 2.159b's thrown `debug` (a boulder copy) read 0, -1, 1.1 to 30.3 and 5.8e31 in flight over land and deep water, never -50 [verified xemu, Step 2.159b's sitting B]. Since Step 2.80 X8 reads it in the water to tell a body taller than the water line (AZ-311). The point is placed by the critter's model matrix, `critter_model_matrix` (0x42200; ESI = a 16-byte aligned float[16], the critter on the stack, RET 4): rows 0–2 the rotation 0xA0770 builds from the quaternion +0x18C, row 3 the model origin 0x42070 interpolates between +0x1B0 and +0x1BC by the glide mode +0x19C (mode 0: +0x1B0), moved by 0x402E0's aligned-node offset (the node named at +0x1F8 in the clip at +0x204) through 0xA36E0, unscaled [verified static: capstone, 2026-10-15]. So the world point less the point × scale above is that origin less +0x15C: −1 m on land, and in the water −1.54 m (garret4), −3.07 m (guard_air) and 0 (keylord, guard_fire1) in sight223b. The swim tick sets it (AZ-445, Step 2.116): `player_swim_tick` 0x8B700 loads `[0x1A9C54]` ("m_root") at 0x8BD56 and calls `anim_apply_translation` (0x42E40) at 0x8BD79 with the position and the origin argument the same local and no glide, which puts +0x1B0 = +0x1BC = +0x15C less the node sampled in the playing clip (0xCAB80) and turned by +0x18C, unscaled; a body without the node samples zeros, so its origin is +0x15C. 12 of the 158 bodies have `m_root`: garret4's, guard_air's (bosses/air_guardian), splinter's, air_elemental, air_octopus, bot, bot_evil, firedrake, ice_shard, rock_shard, gargoyle and skrit [verified static: the bodies' markers, Step 2.134b's read, 2026-10-21; this line said three usable ones], so a baked body's root sat at +0x15C, drawn D × its swim pose's root height over it, until Step 2.134b's W27 keyed a grown `m_root` at it in the swim slots' copies, and +0x15C rests 1.041 m under the surface on garret4 and town_male_6 own × 2 alike (sitting 2.107 B's CAL4) [measured]. Since Step 2.80b X8 calls 0x42200 itself and measures the body from that origin (AZ-413).

**The rig: what the level camera measures in metres (Step 2.107, 2026-10-19).** [verified static: Step 2.107's panel, the sites read on both releases (USA `7d1fb519f53d`, Europe `72e0cf6af079`); the eight constants' readers and the regrow block re-read by its build with `azurik-mod xbe find-refs|dis`; seen in game by sittings 2.107 B and C] The eye sits 0.11 m behind the camera's place along its view (0x80B90: the forward from +0x17C through 0xA08D0 times 0x19813C, 0.11, which 0xFB4E0 also uses for the sweep radius at 0x38BC00), so at rest it sees the point from 5.11 m. The projection is 70° across at 4:3 (a 0.75 aspect, 55.4° vertical; +0x18C), the near plane 0.11 m (0x198414, read at 0x52D4D and 0x54AFB), the far 10000 (0x1A9DE0). A room can carry its own camera pitch (room +0x28/+0x2C, loaded at 0xC07FD/0xC080E); −30° is the pitch the camera rests at in the rooms the sittings measured. Eight f32 constants, each read only by the camera module (0x80820–0x82680) or its boot copy, hold every metre it moves by:

| USA | Europe | Value | Readers (USA) |
|---|---|---|---|
| 0x19814C | 0x19A2F4 | 5.0 | 0x811FD only: the reset 0x811E0 (level creation 0x80AEA, the spawn and teleport request 0x81387) sets the distance +0x19C and the wanted one +0x1A4 |
| 0x198158 | 0x19A300 | 0.5 | 0x8190B: the D-pad zoom's least |
| 0x19815C | 0x19A304 | 12.0 | 0x81911 (the zoom's most); 0x81CA3, 0x81CA9 (the water push's reach, squared); 0xFB550 (Europe 0xFB880) copies it to 0x38BBE0, RT's most (read at 0x814B8) |
| 0x198160 | 0x19A308 | 3.0 | 0x819DD: the most past the wanted distance |
| 0x198164 | 0x19A30C | 10.0 | 0x818F7 (the zoom's rate, which RT's ±2 at 0x814DC/0x814E8, Europe 0x8148C/0x81498, feeds as zoom inputs); 0x81973, 0x81982 (the regrow's cap) |
| 0x198168 | 0x19A310 | 10.0 | 0x81969: the regrow per unit of stick |
| 0x19816C | 0x19A314 | 2.0 | 0x81D3C, 0x81D42, 0x81D71: the water push's least horizontal distance |
| 0x198170 | 0x19A318 | 6.0 | 0x814B2: RT's least |

The input block runs 0x813BA–0x81B00 (its one entry at 0x813A0; it leaves at 0x81B07, Europe 0x81AB7). In it, while the D-pad zoom input is 0 and the distance isn't the wanted one, the regrow 0x81952–0x81A04 steps +0x19C toward +0x1A4 by min([0x198168] × S, [0x198164]) × dt, S the sticks' sum at [ESP+0x20] multiplied in at 0x8196F (Europe 0x8191F: `fmul dword ptr [esp+0x20]`), then caps it at the wanted + [0x198160]; the pitch eases the same way, its stick multiply at 0x81878 (Europe 0x81828). +0x1B4 is the line-of-sight blocked timer. After the input block (0x81B22): with the camera in no room (+0x158 0) 0x80FB0 places it at the wanted distance +0x1A4; else the slide 0x80C40 moves it at its distance +0x19C; a slide returning AL 0 (a failed slide: a 6th hit, 0x80D7E, or a crossing factor at most 0 or over 1, 0x80E3F and 0x80E50, to 0x80F96; Step 2.116's correction of "clear [inferred]") also ends in 0x80FB0 at +0x1A4 (0x81B4A) and clears the timer (0x81B64), and one returning AL set (a sweep that ended clear, 0x80F86, hit on the way or not) tests the line of sight (0x80C10, called once at 0x81B80: collision_sweep, its CALL at 0x80C35, Europe 0x80BE5, from the camera's +0x15C to the point): blocked, 0x81B94 adds dt, and past [0x19817C] = 0.8 s 0x80FB0 places the camera at +0x19C (0x81BC6), pulling it to the point's hit, and clears the timer (0x81BCF); clear, 0x81BDB clears it. So a camera whose slide fails jumps to the wanted distance in one tick (0x80FB0's own sweep still holds it), which the regrow's rate doesn't limit [verified static; seen in sitting 2.107 C: a 10.1 m step on a1's ladder at × 3.3]. The player is drawn three times a frame: first at 0x3E887 through an orthographic projection (its shadow), then twice at 0x3F075 through the camera's (Step 2.116, AZ-541: the camera pass 0x3EA00 skips any critter whose box centre, the draw list's entry+8 from 0xC1BB0, is under 1.0 m from the render eye, 0x3EA69 and 0x3EC6B against [0x1A250C], and fades its alpha +0x28C, read at 0x3EAA8, by 2(d − 1) up to 1.5 m, 0x3ECA7, while "movie mode" [[0x380E04]+4] is 0 (Europe 0x382DA4; its loads at 0x3EA57 and 0x3EC58) under a camera whose slot +0xD0 is true (the level camera's 0x807B0); the player's box centre is +0x15C, garret4's collision centre, so a body drawn tiny is hidden with the eye inside 1 m of it [verified static: capstone, 2026-10-20]; X27 takes the two loads); there the view is right-handed (it looks down −z), its row 3 puts the eye 0.110 m behind the camera's place, and the world matrix's row 3 is the drawn origin +0x1B0, its rows' norm the drawn scale [measured: sitting 2.107 B's calibration, `model_kit.py`'s frame score]. The render takes the view and projection at 0x54EE9 and a drawn critter's world matrix at 0x3F075 (the critter at [ESP+0x18]) and 0x3E887 ([ESP+8]); the matrices are at USA 0x387890, 0x389B00 and 0x387B00 (Europe 0x389830, 0x38BAA0, 0x389AA0). Since everything the camera moves by is in metres and perspective doesn't change under a scaling, the player-model swap's X25 scales those eight constants by the drawn body's size over garret4's and NOPs the stick multiply at 0x8196F, so a swapped body is framed as garret4 is at × 1 and a camera pulled in grows back at rest (`azurik_mod/patches/player_model/README.md` § "X25").

#### The frame outside the step: the render and the random numbers (Step X.20, 2026-10-14)

[verified static: decompiles from a `ghidra-serve` copy, `azurik-mod xbe dis|insns`; in game: xemu sitting x20a (breakpoints on the generator and the main loop, two replays of one string); in L3: the render run under Unicorn]

| Function or site | Role |
|----------|------|
| `0x000B61B0` | The game's random float in [a, b) (`[ESP+4]`, `[ESP+8]`): an R250 generator, 250 words at 0x37B4B8 and the index at 0x37B8A0, `x[i] ^= x[i - 147 mod 250]`. Its siblings 0xB6140, 0xB6280 and 0xB63A0 and the particles' inlined copy in 0xDA810 step the same state. Critters' AI, the particles (0xD9DE0-0xDB710), the player's walk, attacks and state machine (0x8665E, 0x88DD4, 0x88FE8, 0x8CF1F) and the render draw from it. |
| `0x000B70E0` | A random point in a box (three draws); 0xB7B00 makes it a Morton key and 0xB7E30 inserts the box into a tree ordered by that key. |
| `0x000C14D0` | The render's draw pass (on `[pd+0xD4]`): each item of its draw lists (+0x338C, +0x3398) whose slot +0x44 returns 0 goes into a local such tree, three draws an item: 146 items and 438 draws a frame by town's rope bridge. |
| `0x00054800` | The scene's render (scene, the frame's dt; RET 8), called by 0x5F930 in boot state 9, once a frame from the main loop's CALL at 0x59C73, after the frame's scene ticks. Its head updates the active camera (the last of the stack `[[pd+0xA8]]`, slot +0xCC) and `[scene+0x34]`'s, then the animated textures 0xD5610; with the rumble state 0x38DE44 on (+0x1D) and a shake (+0x14, +0x18 through 0xBB3A0) it draws two more numbers (0x54BE1, 0x54D0D). It ends with the flush 0x90C80 (0x55820) and the present 0x8FBE0 (0x55825), which waits on the vertical blank. |
| `0x00059AD0`-`0x00059B53` | The main loop's ticks a frame: round((the clock - its sim time) × 30), at least 1, at most 2 (above 2: 2, and the sim time is reset); the frame's locals: `[ESP+0x14]` the ticks, `[ESP+0x18]` their dt so far (f32, summed before each tick), 8 bytes above the return address 0x59BAA from inside a tick. With the cvar "slow motion" (`[0x38C058]+4`, made at 0xF9CA0; the command line's `-clock1`/`-clock2`) at 1 every frame runs one tick, at 2 one tick and `Sleep(250)`. |
| D3D's device `[0x135420]` | (0x132890 on the USA disc) +0x1C its push time, +0x3F0 the address of the time the GPU has reached (in contiguous memory), which its waits compare with (0x12A557). The NV2A's registers at 0xFD000000: a kickoff writes the push buffer's DMA PUT (0x800040); space checks read GET (0x800044, and 0x324C); 0x12A38C sets bit 0x10000 of 0x100410 and waits for the GPU to clear it. |

So the render draws from the same random numbers as the game's AI, three for each item it draws, and xemu, which runs slower than the game under load, runs two scene ticks to most frames (a mix that varies from run to run), so the numbers between two ticks, and every critter that draws from them (town's rope-bridge insects, w2's enemies by r1364), differ from run to run: two replays of one input string from one parked start parted in the generator at tick 5 and in the player at tick 281. With "slow motion" at 1 (placed) two replays were identical tick for tick, and simulator L3, which runs this render after each frame (`docs/SIMULATOR.md`), matched them (AZ-358, AZ-361).

#### The shader-instance cache and its animated layers (Step X.32, 2026-10-16)

[verified static: `azurik-mod xbe dis|fn|find-refs`; in game: xemu sitting x32 on the fork's v0.15, collect-only PC hooks on the two stores, the same runs' end RAM on v0.14-36, and sitting x32d's start words]

| Address | Role |
|---|---|
| `0x001C5550` | 2000 (0x7D0) records of 0x380 bytes in `.data`'s zero-filled tail, to 0x37AD50: one per instance of a `gshd` resource (the XBR shader, `docs/XBR_FORMAT.md`) |
| `0x001BF780` | Their keys, 2000 × 12 bytes (to 0x1C5540): two words that name the resource and its index, and the owner |
| `0x001A7AA0` | The next record to reuse, round robin (-1 before the first: 0xD7F90 then zeroes the keys) |
| `0x000D7F90` | Find or make a record (EAX a record to try first; the key on the stack; RET 0xC): a key not found takes the next record, releases what it held (0xA61B0, the pool free 0x99DD0 at 0x3807E0), zeroes it and takes a reference on the resource (0xA6110, fourcc `gshd`). Nine callers (0x3F1EF-0x3FDF1, 0x7C471, 0xC3093, 0xC3960, 0xCC7BA) |
| `0x000D8140` | Release and zero every record (one caller, 0xC0C6B) |
| `0x001BF4E8` | The animated textures' clock, a float32 in seconds: 0xD5610, from the scene's render each frame, adds the frame's dt (the last dt at 0x1BF4EC) |
| `0x000D5A90` | A record's layer animation (on the stack: the record, the layer index, the layer's definition): with the definition's +0x30/+0x34 nonzero, the UV offsets frac(clock × rate) through the CRT's `floor` (0xEC80C), else its +0x28/+0x2C; then, with +0x10 nonzero, the record's `+0x44 + 32 × (layer + 9)` = clock × (+0x10) and `+0x168 + 32 × layer` = +0x10 (the stores at 0xD5B61 and 0xD5B65), else +0x14 and 0 (0xD5B7A, 0xD5B81). Nineteen callers, 0xD6293-0xD75AA |

Layer 0's two words are a record's +0x164 and +0x168. In `vanilla-rz-w1-dark` (record 2), `vanilla-rz-e7-keylord` (record 0) and `vanilla-rz-e7-dark` (record 1) that layer's +0x10 holds a NaN (sign set, quiet, payload 0x3FFF8C), which the `fcomp` against 0.0 finds unordered, so 0xD5A90 takes the first branch and writes NaN to both words, 1, 2 and 8 times in a 120-vblank run [verified xemu, v0.15 hooks]. x87 propagates an operand's NaN with its payload, so the words get +0x10's own pattern; the fork's builds through v0.14-36 wrote the x87 default NaN there (sign set, quiet, payload 0) [verified xemu: v0.14-36's end RAM differs from v0.15's in exactly those two words in each of the three runs], as v0.13.3-37 did when the states were saved (each state's own record holds that NaN in both words at its start [verified xemu: sitting x32d, a dump at each paused load]). The fork's 0ff9a1eaf7 (x87 NaN payloads kept in its inline x87 code, in v0.15) is that change: the game reads a NaN either way, and these are the only bytes of the 32 D98 states' runs it moves.

#### Balthazar's AI and adaptive armor (2026-10-12)

[verified static,
every VA re-derived by a second pass; the vtable's three slots and
0x1989C8's two readers re-read on 2026-10-12 with a read of the
vanilla XBE and `azurik-mod xbe find-refs --va 0x1989C8`. In game:
xemu, placed, 13 runs.]

His armor is AI code, not an `armor_properties` row. Balthazar's
`critters_engine` row has `ai` = `balthazar`, whose vtable 0x1A0C3C
holds his think 0x273B0 (slot 0), hit handler 0x279B0 (slot 6) and
state machine 0x27530 (slot 9). The AI object is `[critter+0x180]`, and
its +0x20 points back at the critter.

| Field or function | Role |
|----------|------|
| AI +0x164, +0x168 | the current and the desired armor: −1 none, 0 air, 1 water, 2 fire, 3 earth |
| AI +0x16C | the armor-switch timer in seconds, 3.0 at first; the think subtracts the AI tick time at 0x1989C8 (1/30; `fps_unlock`'s `balthazar_ai_tick`, AZ-288) from it on every tick, unclamped (0x2746F–0x27479; the constant's two readers are 0x273B6 and 0x27407) |
| AI +0x158 | the armor fx handle |
| `FUN_000272e0` | the armor mapper, polled every AI tick on the fourcc of the staff power the player has selected (`armor_mgr`+0x18): `wind` and `litn` air, `watr` and `ice` water, `fire` and `stem` fire, `smsh` and `acid` earth, anything else (`norm`, `elem`, …) none |

A damaging hit zeroes the timer; he then takes the desired group (the
shield clip, the fx, and the commit at 58 % of the clip) and blocks
every hit of that group with no damage and a laugh. In xemu he switched
about 2.0–2.8 s after a damaging hit and blocked 19 of 19 same-group
contacts while the other groups landed 74 of 74; plain staff and EAFW
(`elem`) are never blocked. An empty `critters_damage` cell takes the
damage type's base `Damage`. The final boss, spideyzar, uses the same
scheme (vtable 0x1A08C4) [verified static, partial].

#### Spideyzar's speed, his attacks and the damage the player takes (Step R2.12a, 2026-10-15)

[verified static 2026-10-15: `azurik-mod xbe fn|dis|find-refs` (capstone)
and decompiles from a `ghidra-serve` copy (port 8205), constants read from
the vanilla XBE; nothing here has been seen in game]

His AI's vtable 0x1A08C4 (written by his constructor at 0x2B919) holds
his think 0x2B9D0 (slot 0: `__thiscall`, ECX = the AI, plain `RET`;
it ends by calling the base think 0x37950), his hit handler 0x2C790
(slot 6) and his state machine 0x2BC10 (slot 9). Data: `critters_damage`
gives him 3000 `hitPoints`, `damageType` norm_3 and `damageGroup` boss;
`critters_critter_data` `walkSpeed` and `runSpeed` 7.0 (`walkAnimSpeed`,
`runAnimSpeed` 1.3); `critters_walking` an `attack anim rate` of 1.0.

| Field or site | Role |
|----------|------|
| AI +0x180 | His speed: every clip his state machine starts plays at AI+0x180 × the attack's own rate, which 0x30940 (EAX = the AI) writes into the critter's active anim layer's rate. 1.0 at spawn (0x1987B0, read only by his constructor, 0x2B967); his think raises it to 1.25 (0x1987B4) below 2/3 of his HP and to 1.5 (0x1987B8) below 1/3 (0x2BAD5–0x2BB37) and never lowers it. The three constants have no other reader. |
| AI +0x178 | The wait before his next attack, in seconds; the think takes dt (0x198788, 1/30) off it each tick. When it runs out, state 7 picks an attack (`0xB6280(8)`, +1 between 2/3 and 1/3 of his HP, +2 below; entry 9 below 161 HP) and sets the wait to a random value in that entry's range (0xB61B0). |
| 0x1987C0 | His attack table, read only inside his state machine (0x2BE4C–0x2C033): 10 entries of 0x28 bytes, +0 the damage type's name, +4 and +8 two clips, +0x10 and +0x14 rate factors, +0x18 a per-tick attack function (entries 6 and 9: 0x2B850, 0x2B860), +0x1C and +0x20 the wait's range, +0x24 a flag. The types: norm_1, norm_2 (wait 3–10 s), wind_3, acid_3, steam_3, ice_3, fire_3, smash_3, lightning_3, norm_3 (10–15 s). |
| State 0x1E | Starts an attack: critter+0x220 := the damage record of the entry's name (0x469B0), critter+0x224 := 1.0, and its clip at AI+0x180 × the entry's rate. His jump smash (state 0x20) sets `smash_3` the same way. |

**What the player takes does not depend on who hits.** The player's hit
handler 0x8D600 returns 0 at once while the cvar `combat/no player
damage` is on (§ "Native cheat UI"), then calls 0x83FE0(armor_mgr,
msg+8) at **0x8D648**: garret4's own `critters_damage` cell for the
hit's damage type (the type's `Damage` when empty), less the armor's
protection. It never reads msg+0xC, the attacker's multiplier, and takes
the result off the HP (`apply_damage`, 0x8D6AF). The hit message is +0
its type (3, a hit), +4 its source, +8 the damage record, +0xC the
multiplier; the critter message handler 0x43210 gets the attacking
critter from the source's vtable slot +0x74 (0x4327E). A body-marker
hit comes from the damage pass 0x43A80, the only caller (0x43C1B) of the
hit sender 0x460B0: its source is the critter itself and its record and
multiplier the critter's +0x220 and +0x224 (his ranged attacks, the
spells his special clips name, aren't traced). So a
`config.xbr` edit can speed him up (the speeds and `attack anim rate`
above) or raise a damage type for every critter that uses it, and an
XBE edit can change the constants and the attack table above, which are
his alone. None of them can depend on what the player holds: that takes
code, such as a shim on his think (slot 0) and on the CALL at 0x8D648
(`docs/ToDo/RANDOMIZER_PLAN.md` § 7, R2.12).

The disc counts such code reads are the `gameState` variables `earth
fragments` … `life fragments` (21–25): 0x711C0 counts the non-zero
values among a disc's four inventory fragment slots, inventory + 0xAC +
0x30·d + 0xC·k (d = 0–4 for earth, air, fire, water, life; k = 0–3), the
inventory being `[pd+0xE0]` with pd = `[[0x1BF63C]+0x2C]`. d1's seal
opens at 4 of each (`RE_DATA.md` § "d1's death seal and Spideyzar's
floor").

#### The bosses that size themselves (Step 2.205b, 2026-10-27, AZ-786)

[verified static 2026-10-27: `azurik-mod xbe dis|calls|insns|vtable|read`
(capstone) and decompiles from a `ghidra-serve` copy (port 8209), USA;
Europe has the same code VAs, its constants at 0x1A47AC, 0x19A918,
0x1A491C, 0x1A4830; the scales under L2 and
in xemu (main's builds): water_tentacle1
from 0.001 to 1.0 in 69-95 ticks, guard_fire1 from 0.5 back to 1.0 in
150 ticks and from 2.0 in 300, then 1.8 at 1 HP of 5.] A critter's scale is its +0x188, filled from its
species' `critters_engine` `scale` at init (0x40608); every write that
changes it after calls the critter's vtable +0xC0. In the boss AIs' code
(0x25000-0x2FB00) only three such writes exist (the other +0x188 stores
there, 0x27FD5, 0x2B979, 0x2BB47, 0x2C349, are AI fields: earthboss's
and spideyzar's constructors and spideyzar's timer): the tentacles'
constructor's at 0x2F2D0 and two in a think (vtable slot 0,
`__thiscall`, ECX = the AI, [AI+0x20] the critter) that runs every
tick:

| AI | Think | What it does to the scale |
|---|---|---|
| `watertentacle1`-`3` (factories 0x2DFD0, 0x2E180, 0x2E330 → constructor 0x2F280 with 0, 1, 2; vtable 0x1A080C) | 0x2F440 | The constructor sets tentacle 0's (water_tentacle1's) scale to 0.001 (0x2F2D0); 1 and 2 keep their species'. Each tick a scale under 1.0 (`fcom [0x1A250C]` at 0x2F4B0) grows by 1/3 (0x198770, its only reader, `fld` at 0x2F4BD) × dt (0x198758) and is capped at 1.0 (0x2F4C9, 0x2F4D8), stored at 0x2F4E0: a tentacle grows to 1.0 in 3 s (90 ticks) and one at 1.0 or above is left alone |
| `fireboss1`-`3` (factories 0x29980, 0x29B30, 0x29CE0 → constructor 0x29E90; vtable 0x1A0A4C) | 0x29F40 | Each tick (0x2A019-0x2A080) the scale moves toward 2.0 (`fsubr [0x1A2588]` at 0x2A04C) − HP / max HP (critter +0x210 / +0x214, × 1.0 at 0x2A046) by at most 0.1 (`fmul [0x1A2674]` at 0x2A020) × dt (0x198968) a tick: 1.0 at full HP, growing to 1.8 at 1 HP of 5 |

So a config `scale` reaches neither for long: the tentacles end at 1.0
(or keep a scale above it: tentacles 2 and 3 only) and a fire guardian
goes back to 2 − HP / max HP at 0.1 a second (from a `scale` of 2.0 in
10 s). The 1.0, the 2.0 and the 0.1
are shared (382, 31 and 16 `.text` readers), so `enemy_scaling`'s boss
size (`docs/PATCHES.md`) points those seven instructions' `[abs32]` at
floats of its own, each constant × k. The other bosses' code (the air
guardian and its clone, the earth guardian, the water guardian itself,
Balthazar, spideyzar; the boulder, the rock shards and the air
elementals run the shared walking AI, and the shared AI code
0x30000-0x3C000 holds one +0x188 store, 0x32DA7, a zero-fill of a new
object's fields) only reads a scale (the attack range 0x256B0,
the earth guardian's model matrix 0x2949A), and the critter vtable
+0xC0 calls in 0x25000-0x3C000 are the three above, so they keep the
cell's.

#### Per-frame globals

| Address           | Role |
|-------------------|------|
| `DAT_001a9c0c`    | Per-Present frame counter (++ each present). Read by `FUN_000916a0` for texture "last frame seen" cache invalidation. The pacer's frame end `FUN_0008fbe0` adds 1 at 0x8FD49-0x8FD52, after its `D3DDevice_Present` call (0x8FD44), and also when it skips that call (`[[0x38780C]+4]` nonzero). Europe 0x1ABB8C. The xemu harness's rate arms count flips by it (Step X.68). |
| `DAT_0038dd14`    | Last-seen VBlank for the manual pacer.  Read/written by `FUN_0008fbe0`. |
| `DAT_001be36c`    | Per-step counter (++ each `FUN_00058d00` call). 23 xrefs. |
| `DAT_001bf404`    | The load runs' limit (40 MiB, set at boot by 0x596C6), lowered only by the memory check 0x58D00 when free physical memory is under 1 MiB (§ "The load runs and the 40 MiB budget"). |

#### Constants (.rdata anchors for fps math)

| VA        | Original | Patched | Notes |
|-----------|----------|---------|-------|
| 0x1983E8  | 1/30     | 1/60    | Main dt; 3 xrefs in `FUN_00058e40`. |
| 0x1A28C8  | double 30.0 | double 60.0 | Rate multiplier; 1 xref at `FUN_00058e40` + 0x59AF7. |
| 0x1A2650  | float 30.0 | float 60.0 | Shared velocity / rate; 23 readers: 5 that must keep 30.0 (four 30° angles, the hit-flash flicker 0x3EBD3) are redirected to 0x1A2524, the high half of the double 2^32 at 0x1A2520, which nothing writes. |
| 0x1A2740  | float 1/30 | float 1/60 | `anim_blend2`. |
| 0x1A2750  | double 1/30 | double 1/60 | Anim scheduler accumulator. |

### Analysis scripts

The four 60 FPS scan scripts in `scripts/analysis/` and their Ghidra hex dumps of 0x198280–0x198E80 were retired on 2026-10-09 (REORG_PLAN Step 1.30). `azurik-mod xbe find-floats` covers the float-constant scan and `xbe hexdump` the dumps; the imm8 30/60 instruction scan and the disp32 frame-counter xref scan have no CLI replacement.

---

## Boot state machine

### Boot state is `DAT_001BF61C`, stepped by `FUN_0005F620`

The game has a 10-state boot state machine (mirrored as
`enum BootState` in `shims/include/azurik.h`):

| State | Name                      | Meaning                              |
|-------|---------------------------|--------------------------------------|
| 0     | BOOT_STATE_INIT           | initial dispatch / resource loading  |
| 1     | BOOT_STATE_PLAY_LOGO      | play AdreniumLogo.bik                |
| 2     | BOOT_STATE_POLL_LOGO      | polling the logo movie               |
| 3     | BOOT_STATE_PLAY_PROPHECY  | play prophecy.bik                    |
| 4     | BOOT_STATE_POLL_PROPHECY  | polling prophecy                     |
| 5     | BOOT_STATE_FADE_IN        | post-movie transition                |
| 6     | BOOT_STATE_MENU_ENTER     | enter the main menu                  |
| 7     | BOOT_STATE_MENU           | main menu active                     |
| 8     | BOOT_STATE_LOAD_SAVE      | save-selection / load flow           |
| 9     | BOOT_STATE_INGAME         | in-game: engine update loop runs here |

`FUN_0005F620` is the state-dispatch function.  Writing directly to
`DAT_001BF61C` from a shim lets you skip forward (e.g. straight to
`BOOT_STATE_MENU`); backward jumps work but may produce visible
glitches.

### `play_movie_fn` returns `AL` to signal "enter poll state"

`FUN_00018980` (`play_movie_fn`) is the movie starter.  Its `AL`
return value tells the boot state machine what to do next:

- `AL == 1`: movie loaded, state machine advances to POLL_* to
  drive `poll_movie` per frame.
- `AL == 0`: movie didn't start, state machine skips ahead.

The `qol_skip_logo` shim exploits this: it returns `AL == 0` from
a naked `XOR AL, AL; RET 8` so the game believes the logo loaded
AND ended, skipping straight to the next state.

✅ **Learning**: before replacing any state-machine function, map
out its **return-value contract** — in this game, the boot state
machine is driven entirely by `AL` returns, and getting one wrong
produces a black screen with no error.

Reference: `azurik_mod/patches/qol_skip_logo/shim.c` — the five-line fix that replaced
the original 10-NOP byte patch.

---

## Kernel imports

### 151 kernel functions imported; thunk table at VA 0x0018F3A0

The XBE's kernel thunk table starts at virtual address `0x0018F3A0`
(after XOR-decrypting the image-header field at file offset `0x158`
with the retail key `0x5B6D40B6`).  151 four-byte slots, null-
terminated at `0x0018F5FC`.  Each slot's high bit is set, low 16
bits give the xboxkrnl export ordinal.

### No trailing slack — extending the table is hard, but D1-extend sidesteps it

There are 8 bytes of zero padding after the last thunk; the
library-version table starts at `0x0018F604` (`b1 ae cc 3b` = a
timestamp).  Can't append new thunks without moving or overwriting
that data.

D1-extend gets around this entirely via a **runtime export
resolver**: shims that need a non-imported xboxkrnl function get a
stub that walks xboxkrnl.exe's PE export table at the fixed retail
base `0x80010000` on first call and caches the result inline.
Zero XBE header surgery; zero call-site rewriting.  See
[`docs/SHIMS.md` § Kernel imports](SHIMS.md#kernel-imports-d1-and-d1-extend).

### Xbox retail kernel is mapped at VA 0x80010000

The retail Xbox kernel (`xboxkrnl.exe`) is always loaded at
`0x80010000`.  Its PE image header lives at that base; `e_lfanew`
at `+0x3C` gives the PE header offset; the data-directory entry 0
(EXPORT) gives the RVA of the export table.  This layout is
stable across every retail kernel revision and every retail game —
the resolver hardcodes `0x80010000` without concern.

Debug and Chihiro kernels use different bases; the shim platform
targets retail only.

Reference: `shims/shared/xboxkrnl_resolver.c`.

### Each static import is called via `FF 15 <thunk_va>` (6-byte indirect)

The game's own kernel calls use `FF 15 <thunk_va>` — a 6-byte
indirect jump through the thunk slot.  Our D1 path reproduces this
exactly: we generate the same 6-byte stub in the shim landing
region and resolve the shim's `CALL _Foo@N` REL32 to the stub.

### D1-extend stubs are 37 bytes with inline cache

For imports NOT in Azurik's static 151, the D1-extend resolving
stub is 37 bytes (33 bytes of code + 4-byte cache slot).  First call:
`PUSH ECX; PUSH EDX`, `CALL xboxkrnl_resolve_by_ordinal`, `POP EDX;
POP ECX`, cache + `JMP EAX`.  The cdecl resolver clobbers ECX and EDX
(it leaves kernel_base+RVA in ECX), so before Step 1.17 (AZ-041) a
`FASTCALL` import's first call reached the kernel with the wrong
arguments; the 33-byte stub of that time didn't save them.  Subsequent calls: `MOV EAX,[cache]; TEST
EAX,EAX; JNZ tail; JMP EAX` — three instructions, cache-hot after
the first call.  Same API surface to shim authors as D1; the
dispatch in `shim_session.stub_for_kernel_symbol` picks the path
automatically.

### Data exports exist alongside functions

Some kernel "imports" aren't functions at all — they're data:

- `ExEventObjectType`, `ExMutantObjectType`, `ExSemaphoreObjectType`,
  `ExTimerObjectType`, `PsThreadObjectType`: `POBJECT_TYPE` pointers
  used by `ObReferenceObjectByHandle` type checks.
- `XboxHardwareInfo`: DWORD with hardware revision flags.
- `XboxHDKey`, `XboxSignatureKey`: 16-byte keys.
- `KeTickCount`, `KeTimeIncrement`: DWORDs readable directly.
- `LaunchDataPage`: pointer to a page preserved across title launches.

A data import's thunk slot holds the variable's *address*, so a read
needs one more indirection than a call: `azurik_kernel.h` declares them
`__declspec(dllimport)`, the shim references `__imp__KeTickCount`, and
the session resolves that to the slot itself (Step 1.17, AZ-020).  Read
them as plain `KeTickCount`, never `KeTickCount()`.  Before the fix the
header said "read via `&Name`", and both spellings read the 6-byte
`FF 25` stub instead (the value came back as the stub's opcode bytes).
Data exports Azurik doesn't import (`XboxKrnlVersion`, `KeSystemTime`,
…) have no slot and D1-extend only serves functions, so the apply
refuses them.

---

## XBE structure

### Azurik has 23 sections; `.text` is the only executable R-X one

From `parse_xbe_sections` (the header region is not one of them):
```
.text  BINK  BINK32  BINK32A  BINK16  BINK4444  BINK5551
BINK16MX  BINK16X2  BINK16M  BINK32MX  BINK32X2  BINK32M
D3D  DSOUND  XGRPH  D3DX  XPP  .rdata  .data  BINKDATA  DOLBY
$$XTIMAGE
```

`D3D`, `DSOUND`, `XGRPH`, `D3DX`, `DOLBY` are RWX statically-linked
library code.  `.text` is the game's own code.  `.rdata` holds
read-only constants + the kernel thunk table.

### `.text` has a 16-byte VA gap before BINK

`.text` runs `0x11000..0x1001D0`; BINK starts at `0x1001E0`.  The
16-byte gap is our "small shim" landing zone (used by `skip_logo`,
the `player_physics` injected floats, and kernel-import stubs).

Larger shims trigger `append_xbe_section`, which adds a new
executable `SHIMS` section at EOF and shifts the XBE's header-pool
content forward by 56 bytes (the size of one section-header entry).

### Header growth: section-header array is contiguous, pointers auto-fixup

When `append_xbe_section` adds a section, it:
1. Shifts all bytes from `end-of-section-header-array` to
   `size_of_headers` forward by 56.
2. Re-writes every pointer in the image header that now points into
   shifted data (the debug path, file name and Unicode file name, the
   library-version table, the kernel and XAPI library versions, the
   logo bitmap; each section's name_addr and head/tail refs).  The
   certificate (header offset 0x178) sits before the section-header
   array (0x348), so it never moves and cert-addr (0x118) isn't
   rewritten [verified 2026-10-11: `_POST_ARRAY_POINTER_FIELDS` in
   `azurik_mod/patching/xbe.py` and the vanilla header; HM-59].
3. Writes the new section-header entry into the vacated 56 bytes.
4. Updates `num_sections`, `size_of_headers`, `size_of_image`.

Azurik has **880 bytes of on-disk headroom** between
`size_of_headers` (`0xC90`) and `.text`'s raw start (`0x1000`) —
that's the quantity `append_xbe_section` actually checks — so the
56-byte growth comfortably fits.  (The VA-side headroom before the
first section is the same 880 bytes; the slack between the end of
the section-header array and `size_of_headers` is 1088.)  **If
Azurik ever ships an XBE with tighter headers, this room calculation
needs redoing.**

Reference: `azurik_mod/patching/xbe.py::append_xbe_section`.

### CPU state in game: paging on, PAE off, so no NX (xemu, 2026-10-09)

[verified, xemu session 1: the gdbstub's system registers at 0x89060
in vanilla level 1; the bit names are the x86 architecture's]

- **cr0 = 0x80010031**: paging (PG), write protect (WP), NE, ET and
  protected mode (PE) are on.
- **cr3 = 0xF000**, the page directory.
- **cr4 = 0x610**: PAE (bit 5) is off, so there is no NX bit and every
  mapped page can execute.  That is how session 1 ran its poked roll
  shim from the zero tail of the XBE header page (0x10F00, inside
  0x10C90–0x10FFF).

So a section's EXECUTABLE flag doesn't decide whether its bytes can
run.  Whether a missing WRITABLE flag stops writes depends on how the
kernel maps the section, which is untested [inferred; `SHIMS.md`,
AZ-220].

---

## COFF + layout

### Auxiliary symbol records must stay in the symbol list

PE-COFF's symbol table has aux records (size-of-function info, etc.)
interleaved with primary symbols.  Relocation entries index into the
RAW symbol stream, aux records included.

✅ **Learning**: preserve aux records as placeholder `CoffSymbol`
entries (with empty name) so the symbol-index arithmetic in
relocation entries stays correct.  Eliding them breaks REL32
resolution in non-obvious ways.

### `extern_resolver` is the extension point

`layout_coff` takes an optional `extern_resolver: Callable[[str],
int | None]`.  The resolution order for undefined externals:

1. `vanilla_symbols` dict (A3).
2. `extern_resolver` callback (D1 + E).
3. Raise `ValueError` with a helpful message.

Returning `None` from the resolver means "not mine — keep asking".
The `ShimLayoutSession.make_extern_resolver` closure implements the
typical "shared libraries first, then kernel stubs" order.

---

## VAs vs file offsets — the player-character trap

Spotted during a post-reorganisation header audit:
``AZURIK_PLAYER_CHAR_NAME_VA`` was set to ``0x001976C8`` and labelled
as a VA in ``azurik.h``, but it's actually the **file offset** of
the 8-byte ``"garret4\0"`` name slot in ``default.xbe``.  The real VA
of that slot is ``0x0019EA68`` (``.rdata``); the separate drive-root
string ``"d:\\"`` follows it at VA ``0x0019EA70`` (AZ-016).

The bug went undetected for two reasons:

1. The runtime Python code (``_player_character.py``) indexed
   ``xbe_data[PLAYER_CHAR_OFFSET:...]`` directly — it used the value
   as a file offset, which is what it actually is, so the patch
   worked.  (Since Step 2.21a nothing writes the slot: the
   player-model swap writes ``config.xbr`` and ``fx.xbr``, D112, and
   for most bodies the X4 roll shim at 0x8C6AE, Step 2.21b, for
   some the X3 shim at 0x8C3B0, Step 2.21c, and for every body with
   clips the X7 shim at 0x8D682, Step 2.21d.)
2. No shim had yet tried to reference the constant through a DIR32
   relocation — which would have resolved to the **wrong memory
   address** at runtime and read garbage ``.rdata`` bytes.

Fix (current): ``azurik.h`` exposes the real VA,
``AZURIK_PLAYER_CHAR_NAME_VA = 0x0019EA68``, for shim use; the file-offset
spelling it once had beside it, used by nothing, is gone (AZ-329, Step
RG.4a): an address that is USA's file offset has no meaning on Europe.
Any shim that references this anchor via ``DIR32`` gets the correct
runtime address.

General rule: anything named ``_VA`` should survive ``va_to_file(va)``
without changing meaning.  If the raw value passes unchanged into
``xbe_data[raw_value:]`` indexing, it's a file offset and should be
named accordingly.

## Vanilla-function exposure — __fastcall edge cases

When adding functions to `vanilla_symbols.py`, `__fastcall` works
cleanly in clang as long as the function TRULY is fastcall.  The
callers' register-setup pattern is the authoritative signal:

- `MOV ECX, <arg1>; XOR/MOV EDX, <arg2>; CALL` → __fastcall, 2
  register args + optional stack args.
- `PUSH ...; PUSH ...; MOV ECX, this; CALL` → __thiscall, 1
  register arg (ECX=this) + N stack args.  **clang's
  `__attribute__((thiscall))` works on i386-pc-win32 but emits
  ``@name@N`` mangling that doesn't match what Ghidra / vanilla
  Azurik emitted** — you need a naked-asm wrapper that shuffles
  registers before the call.  Deferred.

Working example: `FUN_0004B510` (entity_lookup) — both callers
confirmed pure __fastcall (ECX=name, EDX=fallback).  Now registered
at `entity_lookup@8`.

### Handling MSVC-RVO ABIs (ECX + EDX + EAX + ESI + stack float)

`FUN_00085700` (gravity integration) is the poster child for an
ABI clang can't express directly:

- ECX = config (fastcall arg 1)
- EDX = velocity pointer (fastcall arg 2)
- EAX = output struct pointer (MSVC RVO — implicit)
- ESI = caller-provided entity context (callee-saved, but the
  vanilla function relies on the caller having set it)
- `[ESP+4]` = float gravity_dt_product (callee pops via RET 4)

Solution pattern, shipped as `shims/shared/gravity_integrate.c` +
`shims/include/azurik_gravity.h` until REORG_PLAN Step 1.10 (D18)
deleted the unused wrapper on 2026-10-09 (read it from git history):

1. **Register the part C can express**.  In `vanilla_symbols.py`,
   declare `fastcall(12)`: ECX, EDX and the stack float the callee
   pops (`RET 4`).  Mangled name becomes `@name@12`.  (Until
   REORG_PLAN Step 1.31 it was registered as `fastcall(8)`, which
   left the stack 4 bytes off; `test_declared_vanilla_abi_matches_callee_ret_imm16`
   now rejects any declaration whose pops differ from the callee's
   `RET N`.)
2. **Write a C wrapper that uses inline asm** to set up the
   extra registers right before the CALL.  Key constraint:
   every register load + the CALL must live inside ONE atomic
   `__asm__ volatile` block — clang can't reorder anything
   inside a single asm block, so EAX survives to the CALL.
3. **Clobber list declares every touched register** (`"eax",
   "ecx", "edx", "esi"`) so clang's allocator saves/restores
   as needed around the block.
4. **Satisfy `__fltused` locally** via an asm-label override:
   ``int __fltused __asm__("__fltused") = 0;`` — stops clang
   emitting an undefined external for the float linker marker.

The wrapper exposes a clean `stdcall(N)` C API to shim authors
who just call it like any other function.  It was tested
end-to-end in `tests/test_gravity_wrapper.py` (deleted with it).

This pattern generalises to any vanilla function with "weird"
register setup (thiscall, custom calling conventions, implicit
register inputs).  When adding a new one, copy
`shims/shared/gravity_integrate.c` from git history and adjust the
register constraints.

## Native cheat UI — cheats.cpp (April 2026)

Separate from selector.xbr, Azurik has an **in-game cheat UI**
compiled from `\Elemental\src\game\cheats.cpp`.  The April-2026
notes put it behind the `enable cheat buttons` cvar; it isn't behind
any cvar: button codes open it ("Activation" below; seen in xemu
2026-10-14, Step X.17).  Its root menu, titled "Azurik build 11016
(Release) M9", has three rows [verified xemu, sitting x17]:

- `"Change level..."`: one row per `levl` key of index.xbr but
  `levels/training_room` and `levels/selector` (22 levels and 9
  `movies/scenes/` cut-scenes), sorted by label; there is no start-spot
  picker: every row posts the spot `"startspot"` ("The level warp" below)
- `"Play Movie..."`: the `movies\*.bik` files, by name
- `"Game state..."`: four rows, `"%s magic level: %d"` for Earth, Air,
  Fire and Water; START on one adds 1 to that element's level, 3
  wrapping to 0 (inventory +0x04..+0x10; 0x134F0).  Nothing else.
- also in cheats.cpp: `"cheatsave"` (code 8), `"srcSpecies"`, `"foc"`
  / `"cam"`, and the uncalled handler's `"enable debug camera"` and
  `"enable snapshot"`

### CVar layout

Each of the three cheat cvars is a record created at boot by
`cvar_get_or_create` (0x9F630) from a small static initialiser; the
game reads the cvar's value as the dword at record+4, through the
record pointer [verified 2026-10-10: capstone over the initialisers
and an imm32 scan of `.text` for each record pointer]:

| CVar                    | Record pointer | Registered at | Default | Read at |
|-------------------------|---------------:|--------------:|--------:|---------|
| `enable cheat buttons`  | `0x38CA80` | `0xF63E0` | 0 | 0x82854, 0x850EA, 0x851CE, 0x8CFDC; `-nocheat` loads it at 0x58FEF and writes 0 at 0x58FF9 |
| `enable debug camera`   | `0x38CA70` | `0xF6410` | 0 | 0x17302 |
| `enable snapshot`       | `0x38CA68` | `0xF6440` | 0 | 0x175D7 |

The record pointers live in `.data` past its file bytes, so they're 0
in the XBE and filled at boot.  Each initialiser pushes 0, 2, 0, the
default, the name and the record, then calls `cvar_get_or_create`, so
the default is the call's third stdcall argument; for `enable cheat
buttons` it is the `push 0` at 0xF63E6, whose imm8 is at VA 0xF63E7
(file 0xE63E7, `azurik-mod xbe addr 0xF63E7`) [verified 2026-10-11:
capstone; HM-48].  `Show UI` (string 0x19EDB8, record pointer
0x39011C) is registered lazily at 0x55413, behind bit 2 of 0x390124,
with default 1 (`push 1` at 0x55419); it is read at 0x55444
[verified 2026-10-11: capstone, `xbe find-refs --va 0x39011C`].
`combat/staff hits walls` (string 0x19C0B4, record pointer 0x38BB80)
is registered the same way at 0xFB9D0 with default 1 (`push 1` at
0xFB9D6; Europe 0xFBD06) and read only at 0x8C8AC, the staff-hits-wall
check 0x8C8A0 (the table of functions above); the player-model swap's
X17 makes it 0 (Step 2.75d) [verified 2026-10-16: capstone, `xbe
find-refs` on both releases].  Europe's record pointer is 0x38DB20
(USA + 0x1FA0), read from the check's own operand in game, 1 on
vanilla and 0 on an X17 build; in game the check stays off while the
hit timer +0x1E0 is up [verified xemu 2026-10-16, sitting 2.75d].
The input builder's two reads (0x850EA,
0x851CE) gate input flag 0x40, the developer turbo that R3 or a WHITE
press sets ("Roll, not run" in [`RE_MOVEMENT.md`](RE_MOVEMENT.md);
AZ-115).  The read at 0x8CFDC is below.  The read at 0x82854 is in
0x827E0, the free camera's per-frame update (slot +0xCC of the camera
vtable 0x19C218 [verified 2026-10-11]); with the cvar on it gates an L3
branch there [hub verifier, HM-48].

**What the cheat flag does** [verified 2026-10-10: Ghidra decompiles
from the roll research's approach B, re-checked with capstone on the vanilla XBE]:

- **Turbo.** Flag 0x40 makes the `FMUL [0x1A25BC]` at 0x849E4 scale
  the stick magnitude by 3.0 ("Roll, not run" point 3).
- **Hover.** In the airborne tick 0x89480 (`test cl, 0x40` at
  0x89664) the flag clamps vz to ≥ 0, so the player can't fall.
- **Fly boost.** With the jump-edge flag 4 as well (0x8969A) it adds
  the 8.0 at 0x1A25C0 to vz (`FADD` at 0x896EA, the no-effect
  catalogue's flap v1 site, `azurik-game-reference` §6 #2), plays
  animation 0x32 ("fly", `push 0x32` at 0x896BD), plays
  `fx/sound/player/flap` (0x896FD) and sets entity+0x168 to −FLT_MAX
  (0x8972F).
- **Revive.** In case 8 of the state machine 0x8CCC0 (the `gameover`
  popup at 0x8D0C5 sets state 8, so it is the dead state [inferred]),
  0x8CFDC reads the cvar; with it on and R3 (ControllerState+0x3C)
  pressed, it writes 2.0 to critter+0x1E0 and +0x1E4 and 1 to
  +0x1E8, posts an event through the critter's vtable (+0xB4), resets
  the ground normal (entity+0xB8..+0xC0 = 0, 0, 1.0) and sets state 0.
  That reads as a cheat revive [inferred, approach B].

**Correction (2026-10-10, AZ-116).**  This table used to list
"storage" 0x37AF20 / 0x37B148 / 0x37AFA0 and "getters" 0xFFFC0 /
0xFFFD0 / 0xFFFE0.  Those are something else: each "getter" is a
three-instruction thunk (`PUSH` of the static's address, `CALL
0xCE150`, `RET`) that the static initialisers at 0xFE2A0 / 0xFE2D0 /
0xFE300 register with `atexit` (0xEB358) right after constructing
static objects at those addresses, so they are [inferred] destructors.
They are not cvar getters, and nothing in the cvar path calls them.

### Forcing a cvar on

There are no stored bytes in the XBE to flip: the record is built at
boot with default 0.  Forcing `enable cheat buttons` would mean
writing 1 to `[[0x38CA80]+4]` after registration (a shim) or setting
the default's imm8 at 0xF63E7 to 1, a one-byte PatchSpec [site verified
2026-10-11; effect untested].  Turned on, the cvar is global: R3 or a
WHITE press sets the developer turbo, the input builder consumes
WHITE's rising-edge latch (+0x4D, at 0x85202) [hub, inferred], an R3 press
in the dead state revives, and the free camera gets its L3 branch
(HM-49).  Setting `Show UI`'s default (0x55419) to 0 should start the
game with the HUD hidden [inferred, untested; docs only, Q226].
The April-2026 `qol_enable_dev_menu` patch instead rewrote the start
of the 0xFFFC0 thunk to return 1; since that thunk isn't the getter,
it could not have worked, and the pack was retired
([`Finished/LEARNINGS_HISTORY.md`](Finished/LEARNINGS_HISTORY.md) §
"enable_dev_menu — retired as unshippable").

### Activation (in-game)

**Button codes open it; no cvar gates them** [verified static
2026-10-11 with `azurik-mod xbe calls --to`, `xbe find-refs --va` and
capstone; first mapped by the hub mining, `docs/ToDo/HUB_MINING_PLAN.md`
HM-47; all ten codes decoded by its round 2, HM-88; every code entered
in xemu on vanilla USA with the pipe pad, sitting x17 2026-10-14]:

- **The handler.** The cheat owner, `[[0x1BF63C]+0x40]` (the scene's
  +0x40) [verified xemu], is ticked by 0x15DA0 once per game update
  while no popup holds the game (its only caller is 0x55BB9; EDI =
  owner, `ret 8`).  It switches on owner+0x1C: 0 idle (0x16D40, called
  at 0x15DC2); 1 free camera, where BACK (latch +0x53) runs 0x15E0D,
  which calls the camera destructor 0x827B0 (at 0x15E10); 2 menu update
  (0x1F590); 3 pop the menu; 4 clear the menu stack and destroy the
  camera (0x15EB1–0x15EBD, its call at 0x15EB8).  In states 1–3 the
  world is paused: the player tick doesn't run [verified xemu].
- **Codes.** State 0 walks the table at `.data` 0x1AA5A8 (Europe
  0x1AC530; read at 0x16FC9 and 0x17030): 10 codes of 5–8 steps, the
  same in both releases.  The matcher 0x15C10 (called at 0x16FE9 and
  0x17073) needs the 12 buttons (+0x18..+0x44) to match exactly and
  checks a stick or D-pad direction (bits 20–31) only when it is set,
  against 0.1 at `.rdata` 0x1A1C6C.  A wrong input never resets a code:
  only time does.  Each step must come within 1.0 s of the last
  (owner+0x08 against the 1.0 at 0x1AAC60); the timer runs while idle
  too and the first step doesn't reset it, so the second step gets only
  what is left of the current second.  Gem mode (below) stops the walk.
- **Dispatch.** A finished code i plays `interface/ingame/magic_powerup`
  and calls 0x16610 (at 0x17060), whose 10-entry jump table is at
  0x16D14.  The cheats.cpp code (0x11000–0x1708D) writes no global flag
  a save could record: its absolute writes are the request buffers,
  the cheat-save place and a counter [verified static: capstone].

| Code | Buttons (in order) | Case | What it does [verified xemu] |
|---|---|---|---|
| 0 | LS right + RS left; LS left + RS right; A; B; R3; L3 | 0x16636 | Opens the debug menu (the factory 0x138D0; owner state 2) |
| 1 | RS right + D-pad left; RS right + RS up + D-pad left; RS up + D-pad left; RS left + RS up + D-pad left; RS left + D-pad left; A; X | 0x16A82 | Refill: the four element fuel slots (inventory +0x1C/+0x28/+0x34/+0x40) to their caps and HP to max (0x44640) |
| 2 | X; BLACK; WHITE; LT + RT; L3 + R3 | 0x16AD8 | Toggles the cvar `combat/no player damage` (record 0x38BB7C), which the hit handler 0x8D600 checks first (0x8D601) [the toggle verified; no damage was provoked to see it] |
| 3 | RT; D-pad down, up, down, up; R3; L3 | 0x16812 | Free camera (0x82680 at owner+0x2C, state 1): the sticks fly it, BACK ends it |
| 4 | D-pad right, left; A; B; A; B; D-pad right, left | 0x16AE3 | Gem mode (owner+0x0C): each update A, X, Y, BLACK or B is held adds an emerald, sapphire, diamond, obsidian or ruby (0x587B0); WHITE, LT, RT, START or BACK ends it |
| 5 | R3; RT; D-pad down, up; A | 0x16B77 | Big head: toggles owner+0x0D and sets three floats under the player's model (`[[[critter+0x17C]+8]+0xDC0]+0x4C..+0x54`) to 3.0, or back to 1.0 |
| 6 | D-pad down, right; BLACK + WHITE; R3; L3; LS right + RS left; B; Y | 0x16AF4 | Toggles `fx/magic/fx_regen1` on the player (owner+0x10), drawn as a dark ball at the head; HP unchanged over 150 updates |
| 7 | A; R3; B; R3; L3 | 0x16BCF | Toggles the cvar `Render/debug lighting` (record 0x37AEB0): flat, bright lighting |
| 8 | WHITE; D-pad up, down; A; B; R3 | 0x16BDA | Save anywhere: a place struct at 0x390198 (the body centre, facing, cell, name `cheatsave`) posted at request block +0x14; the game saves at once (150,528 B written to the HDD, no popup) |
| 9 | BLACK; L3; R3; A; B; D-pad up; R3 | 0x16CDC | Toggles the cvar `time just flies` (record 0x38C0E8): the clock (0x55920) runs about 20 times faster, a day in 30 s instead of 600 s |

Europe: the same ten codes at 0x1AC530; the code from 0x11000 to
0x58CE1 is the same as USA's, so every VA in this section below 0x58CE1
holds in Europe too (`region_europe.json` maps 0x12A50, 0x15DA0 and
0x16610 for the xemu kit) [codes: HM-88's decode of both XBEs; Europe
in game: not run].

- **The menu's input** (0x1F590, the active pad): D-pad up/down (or
  either stick's y) moves a row, repeating while held after about
  0.3 s; RT and LT page down and up; START's rising edge runs the row two updates later, whether
  START is still held or not; BACK hides the menu but leaves it on the
  owner's stack, so code 0 shows it again as it was left.  A submenu
  row (callback 0x12890) opens or closes in place.
- **The level warp.** A "Change level..." row's action 0x12A50 copies
  its key into 0x38D940's three 0x104-byte slots (movie, level, spot):
  the level and `"startspot"` (a `movies/scenes/` key goes in the movie
  slot instead), points request block +0x10 at them and sets owner
  state 3.  A levelSwitch's fire 0x6F050 does the same with its own
  buffer 0x38D320, so the load that follows is the one a level exit
  runs: the player arrives at `startspot` (or `startspotShape`, else the
  origin).  In xemu a warp from `vanilla-beach-shield5` matched an R7
  hop to the same level and spot exactly (the same arrival point, HP and
  inventory but the clock, the cheat owner back at 0, the three cvars
  untouched); `scripts/xemu_sitting.py`'s `warp` drives it.
- **0x17090 has no caller.**  This developer handler (`ret 0xc`) opens
  the menu on L3+START (its call to 0x138D0 at 0x1729B, the factory's
  only other caller), runs a debug camera (0x17302 reads `enable debug
  camera`; 0x82680 is called at 0x17528) and a snapshot (0x175D7 reads
  `enable snapshot`).  `xbe calls --to 0x17090` and `xbe find-refs --va
  0x17090` find nothing, so those two cvars are inert in retail
  [inferred: no indirect reference was found either].
- **No cvar gate.** None of `enable cheat buttons`' six references
  (`xbe find-refs --va 0x38CA80`: 0x58FEF, 0x82854, 0x850EA, 0x851CE,
  0x8CFDC, 0xF63ED) lies in 0x15C10–0x1708D or 0x55B60–0x55BB9.
- **The world-pause predicate.** 0x15F60 (EAX = owner in, AL out; true
  in states 1–3) is called at 0x54964, 0x55FE3 and 0x562DE; its
  sibling 0x15F40 has no caller.

### The free camera and photo mode (Step 2.160)

[verified static 2026-10-22: `azurik-mod xbe fn|dis|calls|find-refs` on
both vanilla images, Step 2.160's READ and DESIGN; the update's speeds and
stick signs, the frozen world and the pack seen in game on both releases
(sitting 2.160)]

- **Case 3** (0x16812, `cheat_owner_action`'s action 3): the world (the
  scene's vfunc 0); the active camera, the last entry of world+0xA8.
  With none, or one whose +0x158 is 0, it returns at 0x16D04 having made
  nothing (only a failed allocation ends in the `push 0xa; call 0xe1218`
  loop at 0x169A8).  Else a 0x198-byte free camera (0x82680, vtable
  0x19C218; it appends itself to world+0xA8 and sets its live byte
  +0x195 = 1) at the game camera's place and orientation, the game
  camera's field of view (vfunc +0xC0) in both +0x18C and +0x190
  (0x16A40-0x16A48), its HUD flag +0x194 := the game camera's (vfunc
  +0xD4); owner+0x2C := it, owner+0x1C := 1.  No sound: the code walker
  plays `magic_powerup` before it calls 0x16610.  The destructor 0x827B0
  (ESI = the camera) removes it from world+0xA8 (0x4F580, through its
  +0x154 world) and frees it through its slot +0xB8.
- **Its update 0x827E0** (`free_camera_update`, slot +0xCC, the dword at
  0x19C2E4; Europe 0x82790, the same 438 lines; thiscall, dt on the
  stack, RET 4) reads the active pad: LS y moves it along its heading
  flattened to the ground plane, RS x sideways along its own side axis,
  RT + WHITE − BLACK − LT (clamped to [−1, 1]) straight up or down, each
  × dt × 10.0 m/s (0x1A25B4, 10 readers; Europe 0x1A485C); LS x turns it
  about world up, RS y pitches it, D-pad left/right rolls it, each × dt ×
  90°/s (0x1A2764 × π/180 at 0x38BBEC; 4 readers).  Measured (sitting
  2.160): LS up moves forward, LS right turns right, RS right moves
  right, RS up pitches the view down (flight-style); the pitch has no
  stop, so past straight down or up the view rolls over (RS up held
  from about −63° read −72°/s of pitch with yaw and roll flipped);
  D-pad up/down moves
  the field of view +0x18C by ∓45°/s × dt (0x1A2738, 2 readers), kept in
  [1, 179] (0x82D9D, 0x82DAB).  A's edge (latch +0x48) toggles +0x194,
  which hides the HUD (its vfunc +0xD4 is 0x80810, `mov al,
  [ecx+0x194]`; the scene's HUD draw 0x553E1-0x55402 honours it); X's
  edge (latch +0x4A) restores +0x18C from +0x190 and levels the roll.
  With `enable cheat buttons` on and L3 held, A and X are skipped
  (0x8287C).  It reads no B, Y, START, BACK, L3 or R3, and no collision:
  it flies through walls [inferred].  dt reaches only the move
  (0x82975), the turn (0x82AC2) and the zoom (0x82DBE).
- **Where it runs.** The frame function updates the active camera
  through slot +0xCC at 0x548E6 (EBP = the camera, `push eax` of dt at
  0x548E3, `mov ecx, ebp` at 0x548E4; after it EDX and ECX are reloaded
  and EAX isn't read) and scene+0x34's camera at 0x54908, the only two
  `call [reg + 0xCC]`; both are skipped in owner states 2 and 3 (a menu,
  0x5485A-0x54868), while scene+0x4C (the pulled-controller pause, set
  at 0x55CDB; START clears it) is set, while world+0xD8's save request
  +0x14 is set (0x548AF-0x548BB) and while scene+0x50 isn't 0.  So in
  state 1 the camera flies while the world doesn't step.  The game
  camera stays where it was: its update 0x81240 (at 0x54908) compares
  the active camera's slot +0x8C (the free camera's 0x807F0 returns 0)
  with its own target (0x807A0, `mov eax, [ecx+0x190]`) and returns at
  0x812D5, reading no stick or D-pad [static, Step 2.160's skeptic].
- **Around the tick.** Before 0x55BB4 scene_state_tick returns for the
  pause menu (scene+0x54), a world+0xEC sequence, scene+0x44's screen
  and the scene+0x50 fade; after the
  tick an in-engine cutscene (scene+0x168, its 'end-of-cut-scene' skip
  on A or START, 0x55C09-0x55C77) and, at 0x55D0D, START's edge opens
  the pause menu (scene+0x54 := 1; button 10's latch through `button_pressed_once`, 0xA30D0),
  from which a quit or load frees the world under a live free camera
  (0x827B0 reads its +0x154): so vanilla code 3's camera with START is
  a hazard the photo mode pack closes.
- **The photo mode pack** (`qol_photo_mode`, D489) takes the CALL of
  0x15DA0 at 0x55BB9 and the inline `push eax; mov ecx, ebp; call
  [edx+0xCC]` at 0x548E3 (L1 can't know an indirect callee's ret N, so
  the shim makes the thiscall itself and returns with a plain RET), the
  same VAs in Europe.  Before the tick a fresh L3 + R3, or START, in
  state 1 sets state 4, so 0x15DA0 destroys the camera and sets state 0
  in that call; after it a fresh L3 + R3 in state 0 calls action 3,
  sets +0x194 (HUD hidden) and empties the world text (0x50950: its one
  caller, 0x55FF5, is skipped by 0x55FE3 while the world is paused, and
  0x50500 draws the list every frame at 0x5519C), unless a cheat code's
  next step makes the chord (the walker's code and steps, owner+0x04
  and +0x00, at (2, 4), code 2's L3 + R3, or at (0, 5), (3, 6), (6, 4),
  (7, 4) or (9, 2), the second of two stick clicks in a row: the matcher
  0x15C10 wants all 12 buttons exactly and a miss keeps the steps,
  0x17073-0x17088, so with the second click pressed before the first is
  let go the code finishes when the first is), gem mode (owner+0x0C), a
  cutscene (scene+0x168), the pulled pad (scene+0x4C), no world
  (scene+0x2C), player (world+0xC0) or request block (world+0xD8), or a
  level or save request (+0x10, +0x14).  Each
  change takes every held button's latch (+0x48..+0x53).  At 0x548E3 the
  free camera's dt is × the `fly_speed` slider, × 0.25 with B held, × 4
  with Y held; the constants above are never written.  Seen in xemu
  (sitting 2.160, USA): entry on the chord's own update, 0 player ticks
  over 60 frozen updates, each exit resuming the player as it was (a
  mid-air jump tick for tick), B 2.5 and Y 40 m/s, codes 0, 3, 6, 7 and
  9 with the clicks overlapping finished by the walker; Europe the same
  for the entry, the L3 + R3 and BACK exits, the speeds and code 3.

The April-2026 notes' other lead, a LEFT TRIGGER path, exists but is
not this menu [verified 2026-10-10: capstone]: inside 0x83D80, which
the snapshot names `player_armor_state_tick`, a non-zero LT makes a
rising edge of A, Y, B or X (ControllerState+0x18 / +0x24 / +0x1C /
+0x20, each with its latch at +0x48..+0x4B) call 0x83410 with 0, 1, 2
or 3 (calls at 0x83EAE, 0x83ED3, 0x83EFB, 0x83F23), and 0x83D80 never
references the cvar record (imm32 scan).

### Why we previously patched selector.xbr instead

The pre-April-2026 `qol_enable_dev_menu` patched two `JZ`
instructions in `0x52F50` (`game_start_setup` in Ghidra since D94, 2026-10-11; `dev_menu_flag_check` in the registry) to force `levels/selector`
(the selector.xbr level-loader hub) to load at game start.
That's a DIFFERENT feature: selector.xbr is a static level
room with portal plaques to every level + cutscene, loaded by
the engine's standard level loader once the JZ checks are
bypassed.  It does NOT enable any runtime cheats — no
magic-level editing, no game-state tools.  Users reported the
patch as *"doesn't do anything"* because:

1. The selector.xbr load only triggers on the New-Game flow.
2. Without actually pressing "New Game", the JZ NOPs are
   invisible.
3. Even when you do reach selector.xbr, it's a ONE-WAY trip
   to a level — none of the UI overlay cheats are accessible.

The cvar-"getter" patch that replaced it targeted an `atexit` thunk
("CVar layout" above) and did nothing either.  All four attempts
(JZ NOPs, the thunk, the validator short-circuit, the `FUN_00053750`
trampoline) landed their bytes with no in-game effect, and the pack
was retired
([`Finished/LEARNINGS_HISTORY.md`](Finished/LEARNINGS_HISTORY.md) §
"enable_dev_menu — retired as unshippable").

### Controller-table offsets (Azurik convention)

Reverse-engineering the cheat-activation combo required
mapping `&DAT_0037be98 + ctrl_idx * 0x54` to XInput slots.
The authoritative layout is the single table in
[§ControllerState struct](RE_MOVEMENT.md#controllerstate-struct-xinput-polling--pinned-2026-04-18)
in `RE_MOVEMENT.md` — it matches the `_Static_assert`s in
`shims/include/azurik.h` and is guarded by
`tests/test_shim_authoring.py::test_controller_state_fields_resolve_to_expected_offsets`.
This section used to carry a second copy of the same struct that
had drifted (it listed START at `+0x38` / BACK at `+0x3C`; the
real offsets are `+0x40` and `+0x44`, with the thumb clicks at
`+0x38` / `+0x3C`).  Don't reintroduce a duplicate.

The slots that matter for cheat / movement gating:

| Offset | Field           | Azurik meaning            |
|-------:|:----------------|:--------------------------|
| +0x28  | `button_black`  | **BLACK** — the roll (`roll forward`, input flag 0x20) |
| +0x2C  | `button_white`  | **WHITE** — cheat-buttons turbo (flag 0x40, with R3; cvar `enable cheat buttons` only) |
| +0x30  | `trigger_left`  | **LEFT TRIGGER** — the LT + face-button path in 0x83D80 (not cvar-gated; see "Activation"); held, it blocks the BLACK roll |
| +0x44  | `back_button`   | **BACK** — not read by the flag-0x40 builder |

✅ **Learning**: Azurik's button semantics are non-standard.
Any speed/cheat/etc. patch that gates on a controller-table
slot MUST be named after its physical button (WHITE, LT,
BACK), not its Azurik-internal label (`piVar7[0xf]`).  Both
the roll-rename and cheat-UI discoveries came from reading
`FUN_000a2880` side-by-side with the consuming state
handlers.

## PAL (EU) cross-reference (2026-10-10)

The Azurik Debug Menu and Azurik Level Studio target the PAL release
(`default.xbe` 72e0cf6a…, 1,798,144 B; ours, USA, is 7d1fb519…,
1,785,856 B).  The hub mining mapped every address the Debug Menu uses
to USA (`docs/ToDo/HUB_MINING_PLAN.md` HM-46: of the Debug Menu's six
PAL signatures, parsed as text, three match USA exactly at the same
VA, two with their absolute operand wildcarded, and one is a bare
pointer).  VAs only; "re-checked" means
Step 2.16l confirmed the USA site's role with `xbe calls`, `xbe
find-refs` or capstone on 2026-10-11, "hub" means only the hub's
verifier did.  The region study (2026-10-12) checked 33 of the PAL
values against the Europe XBE (`iso/europe.iso`): 30 held, and the rows
marked AZ-323 carry its three corrections and the one row it filled.
Europe's full address map is `azurik_mod/assets/region_europe.json`.

| Item | PAL | USA | Label |
|---|---|---|---|
| menu factory; its epilogue (a 7-byte `mov eax, [esp+…]`, then pops and `ret`) | 0x138D0; 0x13E6D | same | re-checked (callers 0x167DB, 0x1729B) |
| pause predicates | 0x15F60, 0x15F40 | same | re-checked (callers) |
| cheat state handler | 0x15DA0 (targets 0x15DB6 … 0x15E7B) | same | re-checked (caller 0x55BB9) |
| action dispatcher; case 3 | 0x16610; 0x16812 | same | re-checked (jump table 0x16D14) |
| menu update; row registration; row constructor | 0x1F590; 0x1FBB0; 0x1FC40 | same | hub |
| camera destructor; player tick | 0x82760; 0x8C1E0 | 0x827B0; 0x8C230 | re-checked (USA = PAL + 0x50) |
| heap getter; allocator | 0xE67CD; 0xE4C9F | 0xE647C; 0xE494E | re-checked (both called in cases 0 and 3; USA = PAL − 0x351) |
| `enable cheat buttons` default | file 0xE6717 | VA 0xF63E7 (file 0xE63E7) | USA site re-checked; the pairing hub |
| PlayerPhysics, camera, action-row vtables | 0x19DE24, 0x19E3D0, 0x1A3C08 | 0x19BC6C, 0x19C218, 0x1A1BDC | re-checked (slot 0 = 0x8C230; slot +0xCC = 0x827E0) |
| the 0.0 used by the FCOMP | 0x1A47A8 | 0x1A2508 | re-checked (holds 0.0) |
| ControllerState array; active controller; `Show UI` record pointer | 0x37DE38; 0x1A9A64; 0x3920D0 | 0x37BE98; 0x1A7AE4; 0x39011C | hub (0x39011C re-checked) |
| a levelSwitch's level request; Continue's saved place (`azurik_mod/sim/recipes.py` `LEVEL_BUF`, `PLACE_BUF`; § "Save points, level requests and arrivals") | 0x38F2C8; 0x392100 | 0x38D320; 0x39014C | the Europe XBE (`region_europe.json`'s witnesses: the fire's 0x6F019, 0x6F032 and 0x6F0E0, USA = PAL + 0x50; the continue's 0x53434 and 0x53487, the same VAs) |
| `critters_engine` sites | 0x3F049, 0x40602, 0x496DA, 0x49913 | same | re-checked ([`RE_DATA.md`](RE_DATA.md) § "`critters_engine`"; its +0x188 write at 0x40608 is another site); 0x40602 is the same code in both, not a shift (AZ-323) |
| +0x188 reader's callee | 0xA39E0 | 0xA3860 | re-checked (called at 0x3F054; USA = PAL − 0x180) |
| a caller and its callee (a Level Studio comment) | 0xA5CDC → 0xF5D3A | 0xA5B5C → 0xF5A1A | hub, inferred |
| mip-bit use; body renderer | 0x9CB30 (test at 0x9CC10); 0xCC2C0/0xCC890 | 0x9CA50 (test at 0x9CB30); 0xCC140/0xCC710 | the mip-bit pair: the Europe XBE (AZ-323; USA = PAL − 0xE0); the renderers: hub, inferred |
| a body-renderer callee | 0xD3550 | 0xD3250 | the Europe XBE (AZ-323) |
| vertex-declaration row 0x80004111 | 0x1A9BF8 | 0x1A7C78 | re-checked (holds 0x80004111; USA = PAL − 0x1F80); the PAL row: the Europe XBE (AZ-323) |

The shift is piecewise and not monotonic: 0 up to 0x58CE1 (`.text`
is the same code, instruction for instruction, for its first 107,621
instructions; 0x58CE1 is the clock's first difference), mixed in the
main loop to 0x59B90, +0x50 from 0x59B90 to 0x8E5EE (0x6EC56 and 0x6FFE5
included), −0xE0 at 0x9Cxxx, −0x180 at 0xA3xxx, −0x351 at
0xE4xxx–0xE6xxx, −0x202C to −0x22A0 in `.rdata`, −0x1F80 to −0x1FB4 in
BSS [`.text` to 0x8E5EE: the region study's byte comparison,
2026-10-12, AZ-323; the rest: the anchors above].  Never
copy a PAL VA into the registry, the headers or the facts as a USA one:
a Europe address goes in `region_europe.json` (D146).

### Debug Menu 1.0.0's addresses (2026-10-14)

The second hub mining (`docs/ToDo/HUB_MINING_PLAN.md` § "Round 2
(2026-10-14)", HM-81) searched each of Debug Menu 1.0.0's 55 PAL code VAs as a masked
Europe signature in the USA XBE: 54 map uniquely (0x61D60 has 2
matches), with the shifts above (0 up to 0x562DB, +0x50 for
0x60DF0–0x8D960, −0x180 for 0xAB920–0xCB4F0, −0x351 for
0xE4C9F–0xE67CD).  The 5 that `region_europe.json` holds agree, as do its
3 data VAs; the 49 new pairs stay out of it until a pack uses them.
"Signature" below means only that unique match; "re-checked" means the
USA site's role was also confirmed with `azurik-mod xbe dis` or `xbe
calls --to` on 2026-10-14; the roles are the hub's names.

| Item [hub] | PAL | USA | Label |
|---|---|---|---|
| root-menu title: the build-stamp call | 0x1395F | same | signature |
| state 1 (free camera): the controls site | 0x15DE8 | same | signature |
| vector allocate (STLport's `__node_alloc::_S_refill`, Step 2.172: § "STLport's node allocator") | 0x185E0 | same | signature |
| registry add | 0x4F510 | same | re-checked (the camera's call at 0x826AE) |
| generic entity constructor; its +0x154 store | 0x60DF0; 0x60E99 | 0x60E40; 0x60EE9 | re-checked (6 callers: 0x40395, 0x64F5D, 0x78360, 0x790B5, 0x7B107, 0x80827) |
| detached camera constructor; its vtable store | 0x82630; 0x82640 | 0x82680; 0x82690 | re-checked (callers 0x169E8, 0x17528) |
| PlayerPhysics constructor; its vtable store | 0x84D00; 0x84D27 | 0x84D50; 0x84D77 | re-checked (one caller, 0x8D8ED) |
| input builder: the blocked-input branch; Debug Menu 1.0.0's hook (a 6-byte `jmp` site); its resume | 0x84FFE; 0x8500D; 0x85013 | 0x8504E; 0x8505D; 0x85063 | signature |
| player-tick callees | 0x8C400, 0x8C4D0 | 0x8C450, 0x8C520 | re-checked (called at 0x8C3C3, 0x8C3B7) |
| "frame re-registration" A, B; "animation boundary" | 0xAB920, 0xAB9B0; 0xCB4F0 | 0xAB7A0, 0xAB830; 0xCB370 | re-checked as 0x8C230's callees; the roles hub |
| current-level name accessor | 0x8D960 | 0x8D9B0 | signature |

This table is 1.0.0's.  Debug Menu 1.1.0 (commit `d807b8d`, read in
Step 2.160) adds a live hook at the cheat-owner tick's entry 0x15DA0
(the same VA in both), a CALL retarget at Europe 0x66497 (USA
0x664E7) for its deferred popup, voice and key actions, and a vtable
slot at Europe 0x1A3C24 (USA 0x1A1A5C: not the 0x1A1BF8 the −0x202C
`.rdata` shift predicts, so that shift doesn't hold there), and puts
`enable cheat buttons`' default back to 0 [verified static: both
images].

Their Unicorn tests' stop addresses (USA 0x21CE0, 0x7E7C0, 0x84A40,
0xB7E30) and the three sites that call the world-pause predicate (near
0x54964, 0x55FE3 and 0x562DE) also map; they add no role.

**The entity → world → camera chain** [USA; the stores and calls
re-checked 2026-10-14 with `xbe dis` and `xbe calls --to`; HM-82]:

- **Component → entity.** A component's +0x20 is its entity (stored at
  0x2FE2A).  The hub calls 0x8C230's ECX the PlayerPhysics component;
  our registry calls the same object PlayerControl.
- **Entity → world.** Entity+0x154 is stored at 0x60EE9 by 0x60E40, a
  generic entity constructor with 6 callers.  The hub calls the object
  GameWorld.  Since every entity built there gets it, it is probably
  the world all entities share, with the ArmorMgr at its +0xCC
  [inferred]; `shims/include/azurik.h` calls it `gameplay_ptr`, and
  `azurik_mod/sim/obs.py` and `scripts/xemu_oracle.py` call it `pd`,
  the player data.
- **World → cameras.** The camera constructor 0x82680 reads its world
  from its own +0x154 (0x8268A), loads world+0xA8 (0x826A7) and adds
  itself to that list with 0x4F510 (0x826AE).  The active camera is
  the list's last entry [hub].
- **The detached camera.** 0x198 bytes, vtable 0x19C218 (stored at
  0x82690), +0x154 its world; its byte +0x195 is cleared at 0x827C5 in
  the destructor 0x827B0 (the hub's "enabled").
- **PlayerPhysics.** Constructor 0x84D50, which stores vtable 0x19BC6C
  at 0x84D77.  The tick 0x8C230 calls, in order: 0x84F90
  (`player_input_build`), 0x61360 twice, 0x83D80
  (`player_armor_state_tick`), 0xAB7A0, 0xAB830, 0xCB370, 0x8CCC0
  (`player_physics_state_machine`), 0x8C8A0 (`player_staff_wall_check`),
  0x8C520 and 0x8C450.

**Names a later `ghidra-apply` plan could add.**  The snapshot names
none of these USA functions; the names are proposals, from the roles
above and § "Activation":
`cheat_menu_create` 0x138D0, `cheat_sequence_match` 0x15C10,
`cheat_owner_tick` 0x15DA0, `cheat_menu_pause_predicate` 0x15F40,
`cheat_world_pause_predicate` 0x15F60, `cheat_action_dispatch` 0x16610,
`cheat_dev_input_handler` 0x17090, `node_alloc_refill` 0x185E0 (the hub's
"vector allocate" is STLport's `_S_refill`),
`menu_update` 0x1F590, `menu_row_register` 0x1FBB0,
`menu_action_row_ctor` 0x1FC40, `registry_add` 0x4F510, `entity_ctor`
0x60E40, `freecam_ctor` 0x82680, `freecam_dtor` 0x827B0,
`freecam_update` 0x827E0, `player_control_ctor` 0x84D50,
`player_control_tick` 0x8C230, `current_level_name` 0x8D9B0,
`heap_alloc` 0xE494E and `heap_get` 0xE647C.  0xAB7A0, 0xAB830 and
0xCB370 wait for a read of their own: their roles are only the hub's.

## Level node graph: the engine side (2026-10-10)

Keys, locks, seals, save points, exits and spawns are data: a node
graph in each level XBR ([`XBR_FORMAT.md`](XBR_FORMAT.md) § "Level
node graph").  What the XBE holds for it [verified 2026-10-10: capstone,
string and pointer scans of the vanilla XBE; first found by the
randomizer plan's engine facts]:

- **Node types.** The node factory registers the type names from
  code in 0x721B0–0x72800 (engine facts).  Re-checked for four types,
  each loaded there once and once more by a static initialiser in
  0xFD000–0xFF000: `critterGenerator` (0x723A6, 0xFE2DB),
  `levelSwitch` (0x72421, 0xFDFDB), `gameSaveControl` (0x726B1,
  0xFE3FB) and `gameState` (0x72703, 0xFE42B)
  (`azurik-mod xbe find-refs --string critterGenerator --iso
  iso/usa.iso`, and the same for the others).  Debug strings: two
  that contain `initializing nodegraph`, 0x19DBE0 (pushed at 0x65E8C)
  and 0x19DC04 (pushed at 0x65E81), and `nodes.cpp` (0x6F5EB)
  (`--string` exits 2 listing both nodegraph strings, `--va` takes one;
  re-checked 2026-10-11).
- **Attribute names.** Each type's attribute names sit in tables of
  16-byte records in `.rdata` 0x19580C–0x197600 (engine facts); the
  records for `actionButtonPressure` (0x195A6C), `teleported`
  (0x195D7C), `numGenerated` (0x19683C), `maxGenerated` (0x19686C),
  `doSave` (0x19722C) and `value0` (0x19727C) all lie inside it.  For
  example `critterGenerator`: `playAnimIndex numGenerated numAlive
  numDead maxGenerated maxAlive critterRange emitDelay enable`;
  `gameSaveControl`: `doSave active restored clearRestored`;
  `gameState`: `value0` … `value9`.
- **`gameState` variables.** A `gameState` node reads player
  variables by name: `0x71120` looks the name up in the
  null-terminated pointer table at `.data` 0x1A9D30 (its only code
  reference) and returns the index, or −1.  The table holds 31 names:
  `health`, `health max`; `earth fuel`, `air fuel`, `fire fuel`,
  `water fuel` and the four `… fuel max`; `emeralds`, `diamonds`,
  `rubies`, `sapphires`, `obsidians`; `earth level` … `water level`;
  `day night timer`, `current day`; `earth fragments` … `life
  fragments`; `armor type`, `armor level`, `damage type`, `damage
  level` and `armor fraction`.  (The engine facts counted 35 and left
  out `armor fraction`.)  So a level script can test HP, fuel, gem
  counts, power levels and fragments per disc.
- **`critterGenerator` code.** Its method `0x6F570` (vtable slot
  `.rdata` 0x19D6BC) reads a count at record +0x2C and steps 12-byte
  points, the gen-point list.  `0x6F960` (called from 0x6F874 and
  0x6FBC0) spawns through the critter builder `0x45C10` with −1 HP, so
  generated critters get their species' `critters_damage` `hitPoints`
  ([`RE_MOVEMENT.md`](RE_MOVEMENT.md) § "Player HP comes from
  settings_foo").  That both belong to `critterGenerator` is inferred
  from the engine facts and their place next to each other.  *The
  randomizer's R0 (2026-10-11) confirms it:* 0x6F570 is the
  `critterGenerator` loader, slot 1 of vtable 0x19D6B8, and 0x6F960
  places a spawn at the parent's matrix times the point (the table
  below).

### The loader and the logic nodes (USA VAs; the randomizer's R0, 2026-10-11)

The VAs `azurik_mod/xbr/nodes.py` and `azurik_mod/randomizer/levels.py`
rest on (Step R1.1), from the R0 reports on the wiring, the thresholds and the RAM
recipes.  "Lane" means an R0 lane read it (a capstone listing or a
decompile of a read-only Ghidra copy); "re-read" means the reports'
check pass read it again with capstone.  The data layouts are in
[`XBR_FORMAT.md`](XBR_FORMAT.md) § "Links, curves and logic nodes".

| VA | What it is | Label |
|---|---|---|
| 0x53750 → 0x53B53 | `load_level_from_path` calls the node-graph initialiser; its other caller is 0x633FA, in 0x633B0 | static, re-read |
| **0x65E50** | **Node-graph initialiser.** For each record: 0x65CB0 (the type name → its factory, from the table at 0x1BCDE0, filled from 0x721B0), then 0x65880 (copies the attribute block, asserting the type's count). Then the save list (header +0x0C/+0x10), the level `.sav` restore (version 2, a count equal to the list's, then per node its attribute block and a call to its vtable slot 4), the third list (+0x14/+0x18), and last slot 1 (each type's loader), then slot 2 (the link loader) on every node | static, lane |
| 0xCE0B0 | Node-type registration: 44 static initialisers in 0xFD000–0xFF000 call it with the type's attribute chunk, count, name and parent | static (`nodes.Schema` reads them, 2026-10-12) |
| **0x658F0** | **Link loader** (vtable slot 2, every type): 24-byte links, stride 0x18 (0x65975), plugs read as u16 (0x65950, 0x65956); a curve ref goes to 0xD87E0 (0x6593E) | static, re-read |
| 0x663B0 | Per-frame propagation over dirty nodes: update (slot 5), then each link's `curve(source × weight) × factor` into its target | static, lane |
| 0xD87E0 / 0xD8300 | Curve copy / evaluation (pre and post modes, step keys, cubic Hermite) | static, lane |
| 0x69BF0 / 0x69C10 | Combiner loader (+0x18 input count, +0x1C function) / update (jump table 0x6A008) | static, lane |
| 0x6A0F0 | Switch update (vtable 0x19CF30 slot 5; factory 0x738E0); its tick is 0x1981E0 = 1/30 | static, lane; the constant re-read |
| 0x71120 / 0x71160 / 0x711C0 | `gameState`: the name lookup in the 31-name table at 0x1A9D30, the loader, the update (variable kinds by the byte table 0x714CC and jump table 0x71498; marks itself dirty again at 0x714FB) | static, lane; the update re-read |
| 0x6A2E0 / 0x6A350 | Latch loader (binds a named latch to a global through 0x5E690) / update | static, re-read |
| 0x5E690 / 0x5E980 | The global map's find-or-create (called only from the `shared.sav` reader 0x5E980 and the latch loader) / the `shared.sav` reader | static, re-read |
| **0x6A490** | **Platform loader** (vtable 0x19D308 slot 1; factory 0x73FB0): the key fourcc at +0x40 (read at 0x6A9D1); `open` sets `key` to 1, otherwise an unused `key` (0x6AA39) registers the requirement through 0x79660 | static, lane; the key path re-read |
| 0x79F80 | Collision-object events (jump table 0x7A264): the key path (0x7A01D–0x7A08B) uses up one key through 0x58AD0 (at 0x7A060) and sets `key`; event 3 (0x7A1DA) sets `whack`, and `magic` from the attack's integer when the damage fourccs match | static, lane; 0x7A060 and event 3 re-read |
| 0x7A280 | Resets `whack`, `magic` and `touch` (pulses) | static, lane |
| 0x6ABB0 / 0x6AD20 | Platform update: collision flags from `gameSolid`, `slippery`, `climbable`, `water`, `springboard` and `damage` | static, lane |
| 0x58090 | Finds or claims an inventory slot for a tag: 12 fixed slots at +0x18, 20 fragment slots at +0xA8, 5 key slots at +0x198 | static, re-read |
| 0x58AD0 | Uses up a key (its only caller is 0x7A060, one key) | static, re-read |
| 0x587B0 | Inventory add (from the pickup 0x46FE0): no free key slot shows the `6keys` popup and adds nothing | static, re-read |
| 0x587B0's hints; 0x55B37 | A first pickup's hint popup: shown through `[[inv+0x1D8]+0xEC]` vfunc +4, after setting its bit in the inventory's +0x14 (bit n for the slot table at 0x1A9E0C: 0 earth, 1 air, 2 fire, 3 water power-up ("The Blue Globes…"), 4-7 the gems, 8 obsidians; 0x200 health ("The circle with the red cross…"), 0x4000 chromatic, 0x8000 key). While that popup manager (`[vfunc0(scene)+0xEC]`) reports active (+8), the scene tick 0x55AB0 exits at 0x55B37 after calling its +0xC, skipping the world (0x55BB4: the cheat tick 0x15DA0, then the player tick) until A (Step 2.75e, AZ-472) | static, lane; the exit and the water and health bits xemu |
| 0x6F570 | `critterGenerator` loader (vtable 0x19D6B8 slot 1; factory 0x74860; constructor 0x6F180) | static, lane |
| 0x6FD40 | Generator update: the spawn budget (a negative limit −N is N × the point count, 0x6FE4A–0x6FE95) | static, lane; the negative branch re-read |
| 0x6FBB0 / 0x6F960 | Spawn one item at the round-robin cursor / place it at the parent's matrix times the point | static, lane |
| 0x6F920 / 0x6F390 | Write / read a generator's spawn state into the level `.sav` (slots 3 and 4) | static, lane |
| 0x67F80, 0x68BE0, 0xBC630, 0x681E0 | Transform loader, local-matrix builder, Euler routine, inherit modes (PAL 0x67F30, 0x68B90 and 0x68190: USA = PAL + 0x50) | static, lane |
| 0x54172 → 0x5FF70; 0x54190; 0x541B0 | Where a level request puts the player: the first `playerLocation` of the main graph whose name equals the spot or the spot + `Shape`, else `startspot`, else the origin | static, re-read |
| 0x55920 / 0x535A0 | The clock (inventory +0x000) gains (1/30)/600 per update, so a day is 600 s; a new game starts it at 0, not at dawn, 0.25, as the static reading gave (in xemu the new-game setup after a death in the training room read 0.0, and a New Game's first settle there 0.0004-0.007: Step R1.26's sittings, AZ-478) | static, re-read; xemu |

### Rig triggers: the motion nodes and the graph in RAM (Step R2.19h2, 2026-10-28)

What starts a moving solid (`azurik_mod/reach_engine/triggers.py`; `scripts/rig_triggers.py`, D847) [verified
static 2026-10-28: `azurik-mod xbe fn|dis|vtable|calls` on the USA XBE;
the graph layout and the pokes also by L3 runs]:

| VA | What it is |
|---|---|
| 0x6BAD0 | `timer` update (vtable slot 5): attributes start +0, stop +4, rate +8, enable +0xC, repeat +0x10, reset +0x14, current +0x18; reset non-zero holds current at start; enable 0 does nothing; else current += rate × 1/30 (0x1981E0), wrapped into [start, stop) by fmod (0xF5EF6) with repeat, else held at stop; a step still short of stop re-dirties the node (0x6BB6E) |
| 0x70260 | `randomNumber` update (vtable 0x19D658, factory 0x74F60): while `enable`, its clock (+0x20) gains 1/30; at `updateTime` a new number in [`minNumber`, `maxNumber`] from the R250 generator 0xB61B0 (the last kept at +0x1C); `output` is the new number, or with `smoothTransition` the blend from the last; it re-dirties itself every update |
| 0x6BBE0 | `damper` update (vtable 0x19CEA8, factory 0x73C40): while `enable`, `output` steps toward `goal` by `rate` × 1/30, clamped at it; `distance` := output − goal, re-dirtied while non-zero |
| 0x70370 / 0x70390 | `blendWeighted` loader (node +0x18 := the record's count, as a combiner's) / update (vtable 0x19D618, factory 0x75110): `output` := Σ `input[i]` × `weight[i]` over the count, unnormalised |
| 0x6A0F0 | `switch` update (attributes pause, turnOn, turnOff, toggle, lock, onTime, offTime, output, goal): pause skips it; unlocked, a non-zero turnOn sets goal 1, else turnOff 0, else a toggle whose dirty bit (3) is set flips it; locked, only while output equals goal, and the toggle first, then turnOn, then turnOff; output then ramps to goal by (1/30)/onTime or offTime. So a toggle acts only on a change, and with lock linked to the same pad as the toggle a pad toggles the switch past a turnOn |
| 0x69C10 (fn 4, 5) | A max's or min's update starts from the input at its clamped `index` and moves the index to each input that passes it (0x69CEF-0x69D25), then writes the output (+0x44) and the index (+0x40, 0x69FFB): the index remembers the last input that rose above the rest (a3's floor calls: the selector's index) |
| 0x6A2E0 / 0x6A350 / 0x5ED70 | A named `latch`: bound to the global of its name (world +0xE4, 0x5E690) at load, its output := the global's value; while `update` its output := `input` and the global := input, whose other latches 0x5ED70 tells (slot 0) |
| 0x65880 | Copies a record's attribute block to the node's floats at `[node+0x08]` (the count asserted against `[[node+0x14]+0xC]`) |
| 0x663B0 | The graph pass (`[esp+4]` the graph; RET 4): for each node of the vector +0x24..+0x28 whose dirty mask (+0x10) is non-zero, the mask cleared, its update (vtable +0x14) with the mask, then each link (+0x0C list: +0 next, +4 source plug or 0xFFFF for the whole node, +6 target plug, +8 target node, +0xC weight, +0x10 curve, +0x14 factor) writes `curve(source × weight) × factor` and, if the value changed, sets the target's bit (the plug's for plugs under 30, else bit 31). A node's update runs in its pass, so a target later in the vector acts in the same frame |
| 0x54238 / 0x54258; 0x664E0 | The load's pass over world +0xDC (the level's graph: the XBR's `node` section, in record order) and over each graph of the vector world +0x108..+0x10C; 0x664E0, the scheduled event that runs a graph's pass every 1/30 s |
| 0x6A953 → 0x79310 | The platform loader makes the node's collision object (vtable 0x19C810, its second vtable 0x19C808 at +0xD8): node +0x20 → the object, object +0x294 → the node, world matrix at +0x170 |
| 0x7A280 | The collision object's +0xD8 slot (0x19C808): zeroes the node's `whack`, `magic` and `touch` (indices 1, 4, 5) when set, with their dirty bits, so a pad's touch is a pulse that a body standing in the pad sets again each frame |

In L3 the poke is the link pass's own write: a node attribute and its dirty bit, at the pass's entry for that graph
(`Runtime.hold`). Seen in the runs: a5's control elevator rises 3.87 m from a poke of CallControlElevatorUp's touch
(the prototype's figure from placing the body), e7's mine elevator (the E2_E7 arrival's) starts at its
GoTriggerField's touch only after the pad is released first: the player spawns standing in GoTriggerField and
CallField, so the switch's toggle is already 1 and a toggle acts on a change (why the R2.17 prototype's blind sweep,
which put the body in GoTriggerField, moved nothing). On the derive's 166 exported rigs (`rig_triggers.py witness`,
two runs that agree row for row) 37 load rigs moved untouched, 10 never rigs
stood still, 108 wired ones moved under their own condition's pokes and 9 only under their mover's own input (8
whose atoms are items or armour, which have no write, and d1's undecoded elevator); not seen: airship's control
elevator (its switch's `pause` reads 1.0 in the snapshot with no link into it) and town's grate elevator (moving
13.4 m untouched already). e2's 31 drill and tower rigs, which the first run lost to a render timeout (30 at
0xF4EDF), move under their condition: the poke starts a stream load whose 270-330 `MmAllocateContiguousMemoryEx`
calls (0xF4ED9) passed L3's wall-clock render cap of 5 s under load; not a spin ([`SIMULATOR.md`](SIMULATOR.md)
§ "Logic pokes in whole steps").

### Save points, level requests and arrivals (Step R2.1a, 2026-10-15)

What a save-point warp (D202, `docs/ToDo/RANDOMIZER_PLAN.md` §7 R2.1)
reuses (the pack `qol_save_warp`).  All [verified static 2026-10-15:
capstone (`azurik-mod xbe dis/fn/calls/find-refs`) and decompiles of
a read-only Ghidra copy]; the pack built on them was seen in xemu (sitting r21a, 2026-10-15): from w1's W1_3 (SaveGame #1's platform) to town's Temple and back, each arrival 0.883 m from the platform's place, as a save load's; the inventory unchanged; a cheat-code save in town, a death and Continue (the save reloaded), then the ritual on Temple back to W1_3; with every element level 0 (poked), both ways; out of d2 from D2_1 (reached by the debug menu's warp and a RAM placement).

- **The world.** The scene is `[0x1BF63C]`; its +0x2C is the world
  (the same object as an entity's +0x154).  World +0x00: the current
  level path (`load_level_from_path` copies 0x50 bytes there); +0x50:
  the loaded save's save-point id; +0xC0: the player critter (its body
  centre at +0x15C); +0xCC: `armor_mgr`, whose +0x00 points back at the
  world; +0xD8: the request block; +0xDC: the main node graph (node
  pointers from +0x24 to +0x28); +0xE0: the inventory; +0xE4: the
  global map (`shared.sav`).
- **The request block** (world +0xD8): +0x08 the arrival place, +0x10
  the level request, +0x14 the save request (+0x01 and +0x02 are
  bytes `scene_state_tick` 0x55AB0 turns into a continue).
- **A place** is 30 bytes: f32 position[3], f32 quaternion[4] (w
  last), u16 cell.  A save request's place adds the save-point id (up
  to 80 bytes) at +0x1E, 0x6E bytes in all.
- **A level request** is three 0x104-byte slots: movie +0x000, level
  +0x104, spot +0x208.  The debug menu's "Change level..." (0x12A50)
  fills 0x38D940, a levelSwitch's fire (0x6F050) fills 0x38D320, and
  each points request +0x10 at it.  `scene_state_tick` takes it:
  a movie plays first; a level of `last-save-spot` (0x19ECD8, compared
  at 0x55EDF) re-runs `game_start_setup`, i.e. reloads the save;
  anything else is `load_level_from_path(scene, level, spot, 0)`
  (stdcall, `ret 0x10`), whose call there is **0x55F80**.
- **The arrival.** `load_level_from_path` sets request +0x08 through
  0x5FF70 (the spot, or the spot + `Shape`, else `startspot`): 0x6ECE0
  writes the spot's place at 0x38DCCC (0x6EDB9); with neither, the
  origin 0x390128 (0x541EA).  **A continue** (`game_start_setup`
  0x52F50) reads `loc.sav` (the level line, then 12, 16 and 2 bytes:
  the place; then the save-point id into world +0x50; 0x5312B–0x531EA),
  loads with no spot (0x53406), then points request +0x08 at the saved
  place 0x39014C (0x53487) and sets `restored` on the save point whose
  id equals world +0x50.  So a load puts the player on the save
  platform because the save holds that platform's place.  **The player
  tick consumes it:** 0x855D0 (called at 0x8CE6A, in 0x8CCC0) moves the
  body to the place (plus the `m_feet` offset) facing its quaternion,
  sets state 2, h 1.1 and air control 9.0, clears request +0x08 and
  keeps the pointer at +0x0C.  It never writes the velocity
  (PlayerControl +0x24..+0x2C), so a moving player keeps its speed
  through a place (AZ-437: after the debug warp onto a1's tree lift,
  rising at 17-18 m/s, a place flew 6.8 m up; the sitting kit's place
  zeroes it).  So any place written to request +0x08
  after the load and before the new player's first tick is where the
  player arrives.
- **`gameSaveControl`** (factory 0x76930: 0x74 bytes, vtable 0x19D1B8).
  Its loader 0x70EE0 (slot 1) keeps the save-point id (up to 0x51
  bytes) at +0x22, the cell at +0x20 and the parent transform at +0x18,
  and sets `restored` when the id equals world +0x50.  Slot 15
  (0x671B0, `mov eax, ecx`) returns the object; other node types
  return 0 there (0x65710), which is how 0x52F50 finds the save points.
  Its update 0x70F90 (slot 5), on a rising edge of `doSave` (attribute
  +0x10, latch +0x73), builds the place at 0x38DC58: the parent's
  matrix (`[+0x18]` + 0x30, else the identity at 0x1AA800) times the
  node's attributes +0x04..+0x0C (0xA3E50: EAX the 4×4 matrix, ECX the
  vector in, EDX out, plain `ret`), the matrix's quaternion (0xA0620:
  ECX the matrix, EBX out), the cell and the id; then it posts it at
  request +0x14 (**0x71083**).  The level data drive `doSave`: town's
  is `and(switch{on = touch(temple:SavePlatform:GlassShape)},
  LoadDisable_timer)` (`azurik_mod/randomizer/data/generated/town.json`).
  No code flag says "on a save platform": touching it posts a save
  request, and a save point's place can be computed from its node.
- **Saving happens only on a request at +0x14,** and `.text` has three
  writers: the save point (0x71083), the cheat code 8 (0x16CC8, place
  0x390198) and the autosave (0x561F1, place 0x3902B8).  The autosave
  is built only while the cvar `auto save on level load` is on: record
  pointer 0x390634, registered lazily at 0x55FB7 with default 0 (the
  `push 0` at 0x55FA3); its only other reference is the read at
  0x55FC9, which arms a 0.25 s timer at scene +0x374.  0x52A50 (called
  at 0x5620D) reads the request (0x52A60); 0x54800 holds the world
  while one is pending (0x548B8); 0x554CF drops one.  Level exits, boss
  deaths and the disc teleports are levelSwitches, which post only a
  level request.  So retail saves only on a save platform, or with
  cheat code 8.
- **Power selection needs the power.** 0x83D80
  (`player_armor_state_tick`, stdcall(`armor_mgr`), `ret 4`; its one
  call is 0x8C2EC, in the player tick 0x8C230; ControllerState from
  0x1A7AE4, 4 meaning slot 0): LT (+0x30) ≠ 0 sets `armor_mgr` +0x0C;
  a rising edge of A, Y, B or X (+0x18, +0x24, +0x1C, +0x20; latches
  +0x48, +0x4B, +0x49, +0x4A) calls 0x83410 with ECX 0, 1, 2 or 3 (ESI
  = `armor_mgr`).  0x83410 clears bit 1 << i of the mask +0x10 if it is
  set; it sets it only when that element's level (inventory +0x04 +
  4i) and fuel (inventory +0x1C + 0xC·i) are both above 0, and
  otherwise sets 0x40.  When LT is released, 0x838B0 casts the mask
  through 0x838E0, or with an empty mask drops the worn armor (0x837A0,
  pstorage's "a bare LT tap drops it"), then clears +0x10 and +0x0C
  (0x83F32–0x83F54).  So a new game (all levels 0) can select nothing.
  A cast staff (+0x1C) lasts at every element level 0: a stored steam
  cast at 0/0/0/0 kept mask 12 for 42.9 s of play and three hits; and
  entering water drops it: the tick after the body's state went 6 the
  mask read 0, at levels 0 and at fire 1 + water 1 alike [verified
  xemu, Step X.92b, rows C11-C14].
  0xA2FD0 (`active_controller_state`, no argument, plain `ret`;
  callers 0x55BCF, 0x8D3DC, 0x8D3FA, 0x8D41B) returns the same pad:
  0x37BE98 + 0x54·i for the index at 0x1A7AE4, slot 0 when it is 4.
- **A spare saved variable.** The global map at world +0xE4 is a
  name → record map: 0x5E690 (stdcall(map, name), `ret 8`) returns the
  record (its value dword at +0), creating it; the `shared.sav` writer
  0x5E8A0 (called by the save 0x52A50 at 0x52B0F) writes every entry
  ({length, name, value}); the reader
  0x5E980 zeroes every value, then reads the file's entries, creating
  any name it doesn't have; a new game resets it (0x5EC70, called at
  0x53031).  A name no
  level uses is a variable the save keeps and a new game clears.

## Collision (`tern`): the engine side (2026-10-11)

The collision meshes are the XBR `tern` sections
([`XBR_FORMAT.md`](XBR_FORMAT.md) § "`tern` (collision)").  The
loader references below come from the randomizer research's `tern`
reader (D110) [verified static 2026-10-11, Step
2.20j, with the commands named, each run as `uv run --locked
azurik-mod xbe … --iso iso/usa.iso`; all USA VAs]:

- **Static world collision.**  The level loader loads the assert text
  `level->collisionSectionID.valid() || asCutScene` (VA 0x19EE00) at
  0x53CB5 and calls 0x653C0 at 0x53CD1.  0x653C0 allocates a
  0x178-byte object (`push 0x178` at 0x653C7) and calls 0x64F50 at
  0x65566.  0x64F50 stores the `tern` TOC index at object +0x170 and
  the locked resource at +0x174 (`xbe find-refs --va 0x19EE00`;
  `xbe calls --to 0x653C0`, `--to 0x64F50`; `xbe insns --operand
  0x178`, `--operand 0x170`, `--operand 0x174`; no `ret` lies between
  0x653C0 and its `ret 8` at 0x65572, `xbe insns --mnemonic ret`).
  0x64F50 sets the object's vtable to 0x19DCD8 at 0x64F66 (0x6506C
  stores it too; `xbe find-refs --va 0x19DCD8`).  A projectile that
  ends on the world's collision holds this object's +0x150 as its
  contact (its controller's +0x30) [verified xemu: Step 2.167d's
  sitting, rows A8I-A8L:
  10 arrows' contacts read; A8K's 6 stopped where a collision sweep
  found a vertical face in their line].
- **Platform collision.**  The platform loader 0x6A490 reads record
  +0x24, the platform's `tern` index, at 0x6A943 and passes it to
  0x79310 at 0x6A953.  0x79310 keeps the index at +0x2A0 and the
  resource at +0x2A4 (`xbe insns --operand 'esi + 0x24]'`; `xbe calls
  --to 0x79310`; `xbe insns --operand 0x2a0`, `--operand 0x2a4`).
- **The collision word.**  0x6AD20 (called at 0x6AA22, 0x6AA57 and
  0x6AC75; `xbe calls --to 0x6AD20`) builds a platform's collision
  word from its attributes.  The reader gives these bits:
  - 0x10 `gameSolid` (attribute 11), 0x01 `slippery` (12), 0x02
    `climbable` (13), 0x100 `water` (14), 0x04 `autoSpring` (16) and
    0x08 `pushEnable` (18);
  - 0x40 on a solid word, unless `slippery` and `climbable` are both
    set;
  - 0x20 on a non-solid word with `water`, `pushEnable`, `damage`,
    the field-fog start or end, or a runtime flag;
  - byte 2 is the integer `damage` and byte 3 is 0xCC;
  - `springboard`, `pushX`/`Y`/`Z` and `pushRadial` are stored beside
    the word, not in it.

  The OR masks 0x01, 0x02, 0x08, 0x20, 0x40 and 0x100 are re-read in
  0x6AD20–0x6AF40 (`xbe insns --mnemonic or`); the attribute numbers
  and the rest are the reader's reading.  A static chunk's flags
  (0x8050 and the others) fit the same layout [inferred, strong].
- **A body's default fx, and its damage fields.**  The critter init
  0x408F8 calls 0x43700, which formats `characters/%s/fx/fx_default`
  (0x19FD34, pushed at 0x43719) with the species' body string
  (`[[critter+0x178]+4]`) and instantiates that fx on the critter
  (+0x230, through 0x649E0), so a player wearing another body
  (`--player-character`) gets that body's default fx.  A `platform`'s
  `damage` (attribute 17) is its damage level, byte 2 of the collision
  word above, and the fourcc at record +0x44 its damage type: the
  `damage` table's column with that `Type` and `Level` (tesla_tree's
  `Damage_FieldShape`: level 1, `tela`, the `tesla` column, 25 HP every
  0.33 s).  The victim's hit handler 0x8D600 takes the damage from
  0x83FE0 (called at 0x8D648): the victim species' `critters_damage`
  cell for the type, the type's `Damage` when the cell is empty; at 0 or
  less it returns before the reaction, the knock-back and
  `apply_damage` (0x8D64F, 0x84059).  The swap's W16 gives garret4 the
  species' cell for a field nothing switches off (Step 2.75d, AZ-450)
  [verified 2026-10-16: capstone at 0x43719 and 0x8D648; the rest is
  Step 2.75d's static read].
  0x43700 is the format's one user and 0x408F8 its one caller, in both
  releases (Europe's format 0x1A1EEC, the same code at the same VAs).
  At 0x43719 EAX holds the species record and is reloaded at 0x43727,
  ECX (the body string, already pushed) is dead, EDX unused before
  0x4373A, and no flag is read before 0x43722.  The species record's
  +0xC is its `ai` cell's class: the loader 0x496C0 looks the cell's
  name up in the registry (0x4972C -> 0x493D0, which returns the
  entry's value) and stores it at 0x4973D; the boot fills the registry
  with 21 calls to 0x49370 {name, value} (0x3675A-0x36886), 'player'
  (0x19F154) -> 0x8D750 at 0x3686D (Europe 0x8D700), `player_ai_factory`.
  Only garret4 and the unplaced noship have ai player, so +0xC tells the
  player's critter from every NPC wearing the same body: X40 (Step
  2.157, D446) formats `characters/%s/v/fx/fx_default`, the build's
  clone, for it [static: Step 2.157's read and design; L2: `tests/test_player_character.py::
  test_the_player_alone_plays_its_bodys_fx_clone`].
  Nothing asks whether the body has a default fx: 0x408F8's call is
  unconditional, 0x43700 formats the key for every critter, and
  `fx_instantiate` (0x649E0) looks it up in the asset registry
  (`asset_find` 0xA5CA0, kind 0, flag 2, at 0x64AAC) and returns at -1
  having made nothing (0x64AB6).  So a body with none (every
  townsperson) simply has no fx, and under X40 the player's critter
  loads the clone at `characters/<body>/v/fx/fx_default` whenever the
  build adds it to `characters.xbr` and `index.xbr`, as on a body with
  one: Step 2.161c's magic on the townsfolk needs no fallback key
  (Europe: 0x43792 calls 0x64990, whose `asset_find` 0xA5E20 at 0x64A5C
  returns at -1 the same way) [static: Step 2.161c's read; verified xemu,
  sitting 2.161c W-B's B1 and B5 (USA and Europe): a town_male_6 player
  with the magic holds an instance at +0x230, state 2, with the clone's
  64 records].
- **A body's default fx that scripts a scene** (Step 2.131, AZ-603).  Three bodies' `fx_default` hold a game
  camera and critter generators that a marker turns on: a transform
  bound to `m_dying` links to bosses/air_guardian's
  `deathCam_gameCameraShape.enable` and, through a switch (onTime
  7.667 s), the `critterGenerator` of `frag_air_4` (the air disc
  fragment, maxGenerated 1); bosses/fire_guardian's and
  balthazar_airship's to a switch (`DeathCam_toggle` 2.5 s,
  `deathCam_toggle` 20 s) on a death camera; fire_guardian's
  `m_shards` drives the `fire_shard` generator `splinterGenShape`.
  Each body's `die` keys `m_dying` at 1.0 for its whole length.  The
  camera (class vtable 0x19C2F8, built by 0x822C0) is pushed, once
  enabled, on the world's camera stack (`[pd+0xA8]`, 0x82510 through
  0x4F510; the level camera is 0x19C3D8), and its per-frame slot +0xCC
  (0x82580) writes its `freezePlayer` (1.0) into the world's freeze
  byte `[[pd+0xD8]]`, which the input builder turns into no pad input
  (0x84FBD-0x84FCB) and the hit handler into no damage (0x8D630,
  0x8D711).  The engine never names `m_dying` (`azurik-mod xbe strings
  dying`: none); the marker only drives the graph.  The player wearing
  such a body ran the boss's scene at its own death (xemu, 15 guard_air
  deaths: the camera second on the stack and the freeze byte 1 from the
  first death tick to the continue, the fragment spawned on death tick
  231); W22 plays it a copy of the clip without those tracks
  (`docs/PATCHES.md`).  [Measured in xemu for air_guardian; the graph
  links are a static read of `characters.xbr`; the camera path's VAs
  are that read's disassembly, not re-checked here.]
- **Who a damage platform hits** (Step 2.75e, AZ-453) [verified static
  2026-10-16: `azurik-mod xbe dis`, `fn`, `calls` and `insns` on the
  vanilla USA XBE]: whoever
  passes its mask, its owner too.
  - Each tick the player's volume query 0x60BD0 (called at 0x85587)
    walks the collision objects near him, skips only the querier
    (`cmp esi, edi` at 0x60CBE), tests each through its vtable +0xA0 and
    sends each that passes a type-2 (touch) message.
  - A platform's test 0x79D30 (vtable 0x19C810) checks its collision
    word, its `tern` resource (+0x2A4) and `[toucher+0x168] &
    [platform+0x278]`, the mask 0x50D80 parses from the record's flag
    string (+0x28; names at 0x1A9E68: `player` 0x20, `critter` 0x40,
    `all` 0x7FFFFFFF).
  - Its message slot 0x79F80 (vtable +0xB4) takes a touch at 0x7A147:
    with a damage level (+0x27E) it looks up the record for its fourcc
    (+0x280; 0x46A30 at 0x7A1A1) and sends the toucher a type-3 hit with
    itself as the source (0x7A1CB). It reads no owner, and drops the
    victim's "you dealt damage" reply (types above 3: `ja` at 0x79F90).
  - The victim's slot 0x43210 drops a hit only while +0x1E0 > 0, at HP
    0, or when attacker and target share a `damageGroup`; it asks the
    source for its critter through vtable +0x74 (0x4327E), which on a
    platform is 0x606A0 (`xor eax, eax; ret`), so a platform's hit
    always passes (0x43283 to 0x432D3).
  - Inherit mode 7 (0x681E0's case 0x68A43, jump table 0x68BBC) places
    a transform at `[[[node+4]+0x44]+0xC0]`, the player critter.
    `[node+4]` is the node's fx instance: its load (0x633F4) passes the
    instance's world (+0x50, the constructor 0x62E10's argument) to the
    graph loader 0x65E50, which stores it at +0x44 (0x65E5B), allocates
    the node table (+0x24, 0x65EAE) and calls each node's init (vtable
    +4, 0x66167) with a context whose first word is the instance (0x66124)
    [verified static 2026-10-22, Step 2.153c: `xbe dis`; the init's store
    at +4 inferred]; the handle `fx_instantiate` returns points at its
    +0x20 (0x64C81), so X38's copy is `[node+4]` for its nodes (X37 reads
    EDX there since Step 2.153c, AZ-653). The instance's +0x4C is its
    graph's asset (the index `asset_find` gave for its key: 0x63250
    stores its second argument there at 0x6325C), so the player's own
    instance and X38's copies of it share one and the airship boss's
    differs; a `platform` an fx node made holds that node at +0x294
    [verified xemu, sitting 2.161c W-B's RE1 at levels/air/airship: record
    46's +4 its instance and its platform's +0x294 record 46, on the
    player's own instance, a bound and a held X38 copy and the boss's; of
    an instance's first 0x100 bytes only +0x44 and +0x50 (its world) name
    a pointer read, no critter]. X37 tells the player's graph by that
    asset (Step 2.161c). The node is then placed
    through `glide_origin` (0x42070, called at 0x68AA5 with the
    critter), which reads that critter's +0xE4 at 0x42137: handed a
    critter the game had destroyed (the destructor 0x60F80 writes the
    base vtable 0x19DF08; the freed object still read HP 30 and +0xE4
    0) it faults at 0x4213D reading 0x10 and the kernel halts, EIP
    0x800151EF with IF clear [verified xemu, Step 2.153c's record RR1
    and RR2, AZ-682]. What tells a kept critter from a deleted or new
    one (Step 2.153d's read)
    [verified static, `xbe dis`/`fn`]: the delete is the deleting
    destructor 0x40930 (the critter destructor 0x40FA0, which writes
    0x19FC08 at 0x40FAE and calls 0x60F80 at 0x41305, then the heap free
    0xE6465 at 0x4094C); 0x60F80 writes the base vtable 0x19DF08 at
    0x60F94 before every clear it makes (+0xE8 through 0xAB7A0, +0xE4 at
    0x60FA5, +0x158 := 0 through 0x611D0(0) at 0x61028); the HP (+0x210)
    and the species (+0x178) are never written by it, so neither shows a
    delete, and +0x158 is also 0 for a critter in no cell [inferred]. The world object's
    constructor 0x60E40 (called at 0x40395 by the critter's, 0x40380)
    stores +0xE0 := the global counter 0x1BF588 + 1, masked to 24 bits
    (0x60E9E-0x60ECD); the delete never writes it, and the top byte is a
    tag the game ORs in later (0x791C6), so +0xE0's low 24 bits are the
    object's serial: a block the heap gives again holds another one. A
    critter's vtable and serial together therefore change at its delete
    and at any reuse of its block (X37 keeps both, AZ-682). The +0xD8
    sub-object (vtable 0x19DF04, +0xE4 its scheduler, world+0xA4, and
    +0xE8 its queued flag) is a timer entry the scheduler keeps sorted by
    its time (+0xF0, 0xAB6D0), not a registry of live objects.
    balthazar_airship's `damageBox` (`norm`
    level 2, mask `all`) hangs under `onPlayer`, mode 7, and only his
    `attack_2` switches it on (`m_lifedrainswitch`), so it is his drain
    on the player and never touches him; on a player wearing his body it
    sat on the wearer. The swap's W17 gives Skin only a copy of that clip
    without the switch; own body's X37 (Step 2.135) moves the node onto
    the enemy the drain picks and drops the wearer's touch. Only the
    airship's and the spider's `fx_default` hold mode-7 nodes (Step 2.135's
    scan of characters.xbr, fx.xbr and interface.xbr). An AI critter's
    volume query passes touch 1 too (0x37981 `push 1` before the query at
    0x379AC), so an enemy standing in a platform's box touches it as the
    player does [verified static, Step 2.135's design R7].
  - `attack_target_find` (0x7EBB0) keeps no critter pointer in its result
    (+0 the count, +4..+0xC the target's point less the searcher's
    bounds centre, its vtable +0x80, +0x10 the angle, +0x14 the angle off
    the facing, +0x18 distance less radius, +0x1C the target's +0x168,
    +0x20..+0x34 the target's +0xF8..+0x10F, not its bounds): the
    candidate is ESI where it records a better one (0x7EE16-0x7EE58; X37
    reads it at 0x7EE3B) [verified static, Step 2.135]; it takes the
    candidate nearest the facing angle, not the nearest one, and any
    critter but the searcher whose +0x168 holds 0x4040 and not 0x10000000,
    with no HP, owner or team test (0x7ECFB-0x7ED19), so a thrown critter
    of the player's own was the target of his next chained swing (27 of
    27 chained presses in Step 2.159b's B0 probe, none of 9 fresh ones)
    until X42 cleared those bits on it [observed xemu, the B0 probe's
    reads after 0x7EF80; the +4 and +0x20 layouts read there].
- **Debug cvar.**  `show collision debug` is at 0x198D28 (`xbe
  strings 'show collision'`); what it draws is not checked.

## FPS unlock

Moved from "Simulation tick rate" in Step 3.3d (2026-10-10) to sit
with the 60 FPS re-audit below; the dt that `fps_unlock` halves stays
in [`RE_MOVEMENT.md`](RE_MOVEMENT.md#dt-is-130-s-in-vanilla-160-s-with-fps_unlock).

### FPS unlock operates at VA 0x059AFD + 0x059B37

Two sites control the sim-per-frame cap:
- `0x059AFD`: `CMP ESI, 0x2` → `CMP ESI, 0x4` (cap 2 → 4 steps)
- `0x059B37`: `MOV ESI, 2` → `PUSH 4; POP ESI` (byte-length-
  preserving substitute — vanilla never had a `PUSH` here), plus
  a second `FADD ST0,ST0` so the catch-up remainder becomes
  `raw_delta − 4·dt`.

Cap 4 is required to preserve real-time game speed at 60 Hz sim
down to 15 FPS rendered (vanilla's 30 Hz sim + cap 2 covers the
same 15-FPS window).  A lower cap makes game time drift below
real time whenever rendered FPS dips under 30.  The on-death
BSOD that originally motivated a cap=2 experiment **also
reproduces on unpatched 30-FPS Azurik** — it's a pre-existing
engine bug, not a consequence of the cap.  Don't go higher than 4
without xemu testing.

Reference: `azurik_mod/patches/fps_unlock/__init__.py`.

## 60 FPS patch re-audit (April 2026)

Second-pass audit of ``fps_unlock`` against every frame-rate-
adjacent constant in ``default.xbe``'s ``.rdata``, motivated by
the fx.xbr record-layout RE + the new ``azurik-mod xbe
find-floats`` tooling.

### Scope

Exhaustive scan of ``.rdata`` for any IEEE 754 constant in the
``1/30``, ``30.0``, ``60.0``, or ``1/60`` neighbourhoods —
plus float64 counterparts for each.  Every hit cross-referenced
against ``FPS_DATA_PATCHED_VAS`` to classify:

- **Patched** ⇒ halved at apply time (no action needed).
- **Unpatched + frame-rate-dependent** ⇒ BUG, needs patching.
- **Unpatched + not frame-rate-dependent** ⇒ needs documenting
  so the regression guard doesn't flip on it.

### Findings

| Category    | Count | Status                                    |
|-------------|-------|-------------------------------------------|
| 1/30 f32    | 29    | 29/29 patched ✅                           |
| 1/30 f64    | 1     | 1/1 patched ✅                             |
| 30.0 f32    | 5     | 1 patched + 4 classified non-rate (2026-10-12) |
| 30.0 f64    | 1     | 1/1 patched ✅                             |
| 60.0 f32    | 6     | all 6 classified non-rate ✅               |
| 1/60 f32/64 | 0     | no baked-in "60 FPS assumed" math ✅       |

**Zero missed patches** was the April claim; the October audit
below corrects it.  The unpatched 30.0 constants and all 6 of the
60.0 constants are in rendering / UI / threshold code paths:

- ``0x0019FD98`` — threshold in ``FUN_0003EA00``
  (``if (30.0 < *(float*)(param_2 + 8))``) — speed / angle test,
  not a rate multiplier.
- ``0x001A2524`` — not a float literal: the high half of the double
  2^32 at 0x1A2520 (20 qword readers).  `fps_unlock`'s keep-30
  redirects read it as 30.0f.
- ``0x00198B7C`` and ``0x00198A74`` — seconds to 30ths of a second
  in HUD code (AZ-331, AZ-332; see below).
- All 6 × 60.0 — FOV defaults (``FUN_00054800``) + screen-space
  UI scale math (``FUN_0005AC80`` etc.).  Decoded pattern:
  ``fVar13 = (float10)60.0; fptan(fVar13 * 0.5)`` — the classic
  camera-projection ``tan(fov/2)`` setup.

### fx.xbr-specific audit

The 3 ``fx_magic_timer`` XBE callsites (discovered during the
earlier fx.xbr audit) were re-decompiled:

- **``FUN_00083000``** — update: "if new > max, store".  No dt.
- **``FUN_00083050``** — spawn: reads stored max into new
  effect.  No dt.
- **``FUN_00083230``** — serialise: writes effects to save.
  No dt.

The effect-timer system stores values as *numbers*, not as
frame counts.  60 FPS unlock is SAFE w.r.t. fx.xbr.

### Regression guard

``tests/test_fps_coverage.py`` (new) pins the exact vanilla
counts so any future re-dump of the XBE that introduces a new
frame-rate constant (or drops one) flips red immediately.  The
April cases are six:

1. Every 1/30 f32 is patched
2. Every 1/30 f64 is patched
3. Every 30.0 f32 is patched OR classified as non-rate
4. Every 60.0 f32 is classified as non-rate
5. No 1/60 constants exist (the game is 30 FPS native)
6. Vanilla counts match the audit's ground truth

If (3) or (4) flips red, add the new VA to either the fps_unlock
patch set or the ``_NOT_FRAMERATE_*`` dict (with a Ghidra-xref
note in the comment).  If (1), (2), or (5) flips red, the
discovered constant IS a genuine frame-rate dep that needs
patching.

## 60 FPS audit (October 2026, Step 2.27)

The April audit classified constants by value; the October audit
(2026-10-12) classified every *reader* of each site the pack writes
(static, Capstone and a read-only Ghidra serve) and measured the
pack against vanilla in xemu from the D98 field states.  Parity held
for the game clock, jump, gravity, walk, roll, flaps, attacks,
damage per hit, AI fire intervals, hit recovery, knockback and the
camera turn rate; the 3.7% higher jump apex is the discrete Euler
step at half the dt, not a missed site.  It found seven deviations,
fixed in Step 2.27:

| Id | Site | What it was | Fix |
|----|------|-------------|-----|
| AZ-330 | 0x1A2690 | the pack's 0.05 slot was the low half of the double FLT_EPSILON (fcom qword at 0xBDA6D) | 0.05 moved to 0x1A268C, padding |
| AZ-331 | 0x198B7C | a HUD list entry ages by 30 × dt to a 25.0 life; doubled, entries lasted 0.42 s, not 0.83 s | left at 30.0 |
| AZ-332 | 0x198A74 | seconds × 30 → a HUD flipbook frame; doubled, it played 2× | left at 30.0 |
| AZ-333 | 0x19862C | the hit-flash fade window in seconds (only read); halved, 83 ms | left at 1/6 |
| AZ-334 | 0x3EBD3 | the hit-flash flicker index, int(timer × [0x1A2650]) & 7, cycled 2× | operand redirected to 0x1A2524 (30.0) |
| AZ-335 | 0x2A0BA, 0x2A0CB | the fire bosses' think: vx, vy × 0.85 per run (0x1A2774 is also a threshold) | each FMUL reads √0.85 at 0x1A2704 |
| AZ-336 | 0x2BB53 | Spideyzar's hurt meter × 0.9885 per think; half-life 2.0 s → 1.0 s | the FMUL reads √0.9885 at 0x1A2724 |

The audit also found that the scheduler quantum `[ctx+0xC]` is not a
limitation: the world clock copies it from 0x198410 (patched) when
it is built (0x51BFB).  Melee hit messages per swing double at 60
Hz, but damage per swing doesn't (the critter's own seconds timer
gates it).  The new constants sit in literal-pool alignment padding
that no vanilla instruction or pointer reads; a seventh case of
`tests/test_fps_coverage.py` pins each reader's 60 fps value and
that the slots are unread.  Xemu sitting fps227 (a fixed build
booted into the f6 save, triggers placed in RAM) saw a HUD list
entry live 0.833 s and the hit flash keep a 1/6 s fade and 30
flicker steps per second, as vanilla does; no saved state reaches
the fire bosses or Spideyzar, so AZ-335 and AZ-336 rest on the code.

## History

Until REORG_PLAN Step 3.3d (2026-10-10) these notes were sections of
`docs/LEARNINGS.md`, and "Decompilation & Analysis" was
`docs/DECOMP.md`; `git log -- docs/LEARNINGS.md docs/DECOMP.md`
shows their earlier history.
