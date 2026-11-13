/* structs.h: the game engine's in-memory structures, as far as they are
 * known: their fields and offsets, the player entity's field offsets and
 * flag bits, and the vanilla simulation step (dev only: no shim includes
 * it; a shim includes shimkit's headers, AGENTS.md's Packs).
 *
 * Ported from Modkit's shim header (shims/include/azurik.h) at its last
 * cut (Step 4.11d1), everything but its VA anchors, which are
 * devkit/re/data/anchors.toml, and its parameter macros, which shimkit
 * writes. A Modkit path, function or test in a comment names Modkit's tree.
 *
 * Documentation conventions:
 *
 * - Every named field carries its byte offset and the Ghidra
 *   decomp the name came from (most commonly
 *   ``load_critters_config`` (formerly ``FUN_00049480``) for
 *   ``CritterData`` and ``player_input_build`` (0x84F90) /
 *   ``player_input_tick`` (0x84940) / ``player_walk_state`` (0x85F50)
 *   for ``PlayerInputState``).
 *
 * - Fields marked ``(speculative)`` have names that fit the observed
 *   access pattern but aren't fully pinned.  Use them at your own
 *   risk; rename them when you find out what they really are.
 *
 * - ``_reservedNN`` slots are genuinely unknown — the offset is real
 *   (runtime code touches it) but its semantics aren't nailed down.
 *
 * ABI constraints:
 *
 * - i386 little-endian, 4-byte struct alignment (shimkit's flags:
 *   ``zig cc -target x86-windows-msvc -ffreestanding -nostdlib``).
 * - ``float`` is 32-bit IEEE 754, ``double`` is 64-bit.
 * - No padding is inserted beyond what's explicitly written below —
 *   every ``_Static_assert`` at the bottom of the file pins the
 *   position of at least one late field so silent drift breaks the
 *   build, not the runtime (tests/test_re_xbe.py compiles it).
 */
#ifndef AZURIK_STRUCTS_H
#define AZURIK_STRUCTS_H

#ifdef __cplusplus
extern "C" {
#endif


/* ==========================================================================
 * Fixed-width integer aliases (no stdint.h — we're freestanding)
 * ======================================================================== */
typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef signed char    i8;
typedef signed short   i16;
typedef signed int     i32;
typedef float          f32;
typedef double         f64;


/* ==========================================================================
 * Opaque handle types
 * ==========================================================================
 * Use these when a shim only needs to pass a pointer through to a
 * vanilla function without accessing any fields.  Prefer the named
 * structs below whenever you DO want to read / write specific fields. */
typedef void *EntityHandle;         /* Anything the game models as an entity  */
typedef void *ConfigTableHandle;    /* A loaded `tabl` chunk from config.xbr  */
typedef void *ScenePtr;             /* Opaque scene / world graph handle      */
/* ControllerStatePtr below is now a real struct pointer — see
 * ``ControllerState`` + ``AZURIK_CONTROLLER_STATE_VA`` (anchors.toml). */
typedef struct ControllerState *ControllerStatePtr;


/* ==========================================================================
 * CritterData
 * ==========================================================================
 * The engine's in-memory descriptor for every critter — player
 * included (garret4 is a critter under the hood).  Populated at
 * boot by ``load_critters_config`` (vanilla VA 0x00049480, formerly
 * the ``FUN_00049480`` Ghidra placeholder) which walks seven
 * ``critters_*`` keyed tables of config.xbr in sequence:
 *
 *   1. ``critters_engine``        collision + rendering fields
 *      (piVar9[0..0xD])
 *   2. ``critters_critter_data``  gameplay fields (piVar9[0xE..0x16],
 *      f.fear / walk / run / ouch* / drops)
 *   3. ``critters_damage``        hitPoints + per-damage-type table
 *      (piVar9[5] at +0x14 and piVar9[0x23] at +0x8C)
 *   4. ``critters_damage_fx``     per-damage-type FX (piVar9[0x24+])
 *   5. ``critters_sounds``        audio refs
 *   6. ``critters_item_data``     item drops
 *   7. ``critters_special_anims`` anim overrides
 *
 * Field names below track piVar9 indices from that decompilation,
 * so ``piVar9[5]`` maps directly to the ``hit_points`` slot at
 * +0x14.  Offset column (hex) is the BYTE offset from the struct
 * base.  Properties populated from ``FUN_000d1420("name")`` carry
 * their config-key name in the comment.
 *
 * Note: ``walk_speed`` / ``run_speed`` come from config.
 * load_critters_config fills them from ``critters_critter_data``
 * (TOC offset 0x008000) ``walkSpeed`` / ``runSpeed`` (key strings at
 * 0x49D55 / 0x49DAA); for the player (garret4) that is 5.0 / 7.0.
 * walk_state's FLD at VA 0x00085F65 reads ``run_speed`` as the walk
 * base (lldb read 7.0; in xemu runSpeed 14.0 walks at 14.000 m/s,
 * session 3, 2026-10-09).  ``walk_speed`` is the walk-to-run
 * animation threshold in walk_state (0x86474, 0x864AA) and a speed
 * threshold in jump_init (0x89216) and in the ground attack starter
 * 0x88A80 (0x88C14), and it is also the player's vertical swim speed:
 * player_swim_tick multiplies its up/down term by it (FMUL at
 * 0x8B8C5), which swim_speed_scale doesn't touch.  AI code reads it
 * at 0x361F7 [verified 2026-10-10, capstone; no complete reader
 * sweep].  See docs/RE_MOVEMENT.md
 * "CritterData.walkSpeed and runSpeed are live, not dead data".
 */
typedef struct CritterData {
    /* --- critters_engine identifying fields --- */
    u32 _reserved_00;                 /* +0x00 piVar9[0] — parent / vtable ptr         */
    u32 _reserved_04;                 /* +0x04 piVar9[1] — identity token              */
    u32 _reserved_08;                 /* +0x08 piVar9[2] — "sound dir" token           */
    u32 feature_class_id;             /* +0x0C piVar9[3] — from FUN_000493d0           */
    u32 use_skeleton_collision_word;  /* +0x10 piVar9[4] — contains bool at +0x13      */
    /* +0x14 piVar9[5] — ``critters_damage.hitPoints`` (int32:
     * the loader truncates the double toward zero with 0xF5A40,
     * the CRT's _ftol, and stores EAX at 0x4A4D9 [verified
     * 2026-10-10, capstone]).  config.xbr's
     * ``critters_damage`` (TOC offset 0x01A000) has a garret4
     * hitPoints cell; the old "no hitPoints column" caveat came
     * from labels shifted by one table (AZ-113).  Read only by
     * critter init 0x409C0, as the fallback when a spawn passes
     * a negative HP; live HP is critter+0x210 (current) / +0x214
     * (max), and the player's comes from settings_foo ``initial
     * hp``; see ``docs/RE_MOVEMENT.md`` (2026-10-09). */
    i32 hit_points;                   /* +0x14 piVar9[5]                               */
    f32 collision_radius;             /* +0x18 piVar9[6] — "collisionRadius"           */
    f32 collision_aspect_ratio;       /* +0x1C piVar9[7] — "collisionAspectRatio"      */
    f32 player_collision_radius;      /* +0x20 piVar9[8] — "playerCollisionRadius"     */
    f32 scale;                        /* +0x24 piVar9[9] — "scale"                     */
    u32 skin_index;                   /* +0x28 piVar9[0xA] — "skinIndex"               */
    f32 bound_radius;                 /* +0x2C piVar9[0xB] — "boundRadius"             */
    f32 far_clip;                     /* +0x30 piVar9[0xC] — "farClip"                 */
    f32 awake_distance;               /* +0x34 piVar9[0xD] — "awakeDistance"           */

    /* --- critters_critter_data: movement ---
     * Filled from config (see the struct note above): vanilla player
     * run_speed = 7.0, garret4's runSpeed, which walk_state reads at
     * VA 0x85F65 as the walk base.  Since owner decision D53
     * (2026-10-09) the walk_speed_scale slider sets that config.xbr
     * cell and patches no XBE byte, so the slot holds the scaled
     * value.  A shim that wants another base can write here after the
     * loader runs. */
    f32 walk_speed;                   /* +0x38 piVar9[0xE]  — "walkSpeed" */
    f32 walk_anim_speed;              /* +0x3C piVar9[0xF]  — "walkAnimSpeed"                                 */
    f32 run_speed;                    /* +0x40 piVar9[0x10] — "runSpeed" (vanilla=7.0 for player; see above)  */
    f32 run_anim_speed;               /* +0x44 piVar9[0x11] — "runAnimSpeed"                                  */

    /* --- critters_critter_data: damage thresholds / knockback ---
     * ouch1 is the low-damage threshold; the engine uses ouch2 and
     * ouch3 to select heavier-hit reactions.  (There is no
     * ouch1Threshold row: ouch1 is the reaction below ouch2's
     * threshold [inferred].)  The two thresholds are int32: the
     * loader truncates each double toward zero with 0xF5A40 (_ftol)
     * and stores EAX (0x49F62, 0x49F93) [verified 2026-10-10,
     * capstone].  They stay typed f32 here until the AzurKit 4.2/4.3
     * retype, so read their bits as int32.  The knockbacks from
     * +0x50 on are floats (0x49FB3 stores ouch1Knockback by FSTP). */
    f32 ouch2_threshold;              /* +0x48 piVar9[0x12] — "ouch2Threshold"         */
    f32 ouch3_threshold;              /* +0x4C piVar9[0x13] — "ouch3Threshold"         */
    f32 ouch1_knockback;              /* +0x50 piVar9[0x14] — "ouch1Knockback"         */
    f32 ouch2_knockback;              /* +0x54 piVar9[0x15] — "ouch2Knockback"         */
    f32 ouch3_knockback;              /* +0x58 piVar9[0x16] — "ouch3Knockback"         */

    /* --- critters_sounds / critters_mutate: string refs ---
     * +0x5C is not the victory animation: the species loader stores
     * critters_engine's "victory anim" as an int at +0x2FC (0x49A62),
     * past the mapped fields, and the victory poster 0x41390 reads it
     * there (0x4142A); nothing in the loader writes +0x5C [verified
     * static, Step 2.121; docs/RE_XBE.md "What posts a victory"]. */
    u32 _reserved_5C;                 /* +0x5C piVar9[0x17] — unknown                  */
    u32 shadow_texture_ref;           /* +0x60 piVar9[0x18] — transformed string       */
    u32 realm_feature_flags;          /* +0x64 piVar9[0x19] — realm | other feat | ... */

    /* --- critters_critter_data: flocking behaviour --- */
    u32 flocking_fear;                /* +0x68 piVar9[0x1A] — "f.fear"                 */
    u32 flocking_follow;              /* +0x6C piVar9[0x1B] — "f.follow"               */
    u32 flocking_attack;              /* +0x70 piVar9[0x1C] — "f.attack"               */
    u32 flocking_food;                /* +0x74 piVar9[0x1D] — "f.food"                 */

    /* --- critters_critter_data: bool flags (byte-typed) ---
     * These four bools are all written via `*(bool *)(base + N) =
     * value != 0.0` in load_critters_config (FUN_00049480).
     * The surrounding bytes are nominally 32-bit words but the
     * game only reads the low byte. */
    u8  _reserved_78;                 /* +0x78 — low byte of piVar9[0x1E]              */
    u8  use_center_basis;             /* +0x79 — "useCenterBasis"                      */
    u8  always_glued;                 /* +0x7A — "alwaysGlued"                         */
    u8  no_freeze;                    /* +0x7B — "noFreeze"                            */
    u8  hits_through_walls;           /* +0x7C piVar9[0x1F] (byte) — "hitsThroughWalls" */
    u8  _reserved_7D[3];              /* +0x7D..+0x7F — tail of piVar9[0x1F]           */

    /* --- critters_critter_data: timers --- */
    f32 drown_time;                   /* +0x80 piVar9[0x20] — "drownTime"              */
    f32 corpse_wait_time;             /* +0x84 piVar9[0x21] — "corpseWaitTime"         */
    f32 corpse_fade_time;             /* +0x88 piVar9[0x22] — "corpseFadeTime"         */

    /* --- misc scratch / links --- */
    u32 per_type_data_ptr;            /* +0x8C piVar9[0x23] — per-damage-type array     */
    u32 _reserved_90;                 /* +0x90 piVar9[0x24]                             */
    f32 shadow_size;                  /* +0x94 piVar9[0x25] — "shadowSize"             */
    f32 clip_plane_offset;            /* +0x98 piVar9[0x26] — "clipPlaneOffset"        */
    i32 shadow_texture_res;           /* +0x9C piVar9[0x27] — -1 = no shadow           */

    /* --- unmapped gap between shadow_texture_res and range[] --- */
    u8  _reserved_A0[0xB8 - 0xA0];    /* +0xA0 */

    /* --- critters_critter_data: awareness / attack ranges ---
     * Units are world-space (identical scale to collision_radius and
     * camera distances).  Used by the AI for target-acquisition,
     * line-of-sight, and attack-range gating in
     * load_critters_config (FUN_00049480). */
    f32 range;                        /* +0xB8 piVar9[0x2E] — "range" (sight radius)  */
    f32 range_up;                     /* +0xBC piVar9[0x2F] — "range up"              */
    f32 range_down;                   /* +0xC0 piVar9[0x30] — "range down"            */
    f32 attack_range;                 /* +0xC4 piVar9[0x31] — "attackRange"            */

    /* --- unmapped gap; piVar9[0x32]..[0x34] not observed in load_critters_config --- */
    u8  _reserved_C8[0xD4 - 0xC8];    /* +0xC8 */

    /* --- critters_critter_data: drop tables ---
     * Each ``drop_<n>`` slot is a resource-ID / pointer produced by
     * FUN_000d1630 at config-load time (populated via the "dropN"
     * config keys).  ``drop_chance_<n>`` is a 0..1 probability;
     * ``drop_count_<n>`` is the integer quantity dropped when the
     * chance fires.  A drop slot with a zero pointer means
     * "no drop in this slot" — the engine scans until the first
     * zero or the full 5-slot limit, whichever comes first. */
    u32 drop_1;                       /* +0xD4 piVar9[0x35] — "drop1"                  */
    u32 drop_2;                       /* +0xD8 piVar9[0x36] — "drop2"                  */
    u32 drop_3;                       /* +0xDC piVar9[0x37] — "drop3"                  */
    u32 drop_4;                       /* +0xE0 piVar9[0x38] — "drop4"                  */
    u32 drop_5;                       /* +0xE4 piVar9[0x39] — "drop5"                  */

    u32 drop_count_1;                 /* +0xE8 piVar9[0x3A] — "dropCount1"             */
    u32 drop_count_2;                 /* +0xEC piVar9[0x3B] — "dropCount2"             */
    u32 drop_count_3;                 /* +0xF0 piVar9[0x3C] — "dropCount3"             */
    u32 drop_count_4;                 /* +0xF4 piVar9[0x3D] — "dropCount4"             */
    u32 drop_count_5;                 /* +0xF8 piVar9[0x3E] — "dropCount5"             */

    f32 drop_chance_1;                /* +0xFC  piVar9[0x3F] — "dropChance1"           */
    f32 drop_chance_2;                /* +0x100 piVar9[0x40] — "dropChance2"           */
    f32 drop_chance_3;                /* +0x104 piVar9[0x41] — "dropChance3"           */
    f32 drop_chance_4;                /* +0x108 piVar9[0x42] — "dropChance4"           */
    f32 drop_chance_5;                /* +0x10C piVar9[0x43] — "dropChance5"           */

    /* --- Anything past +0x110 is not yet mapped.  Full struct is
     * several hundred bytes; attack-triggers and more config fields
     * live in that region but stay unnamed until a shim references
     * them. */
} CritterData;


/* ==========================================================================
 * ControllerState
 * ==========================================================================
 * Per-player gamepad state populated every frame by the XInput
 * polling loop (``FUN_000a2df0`` → ``FUN_000a2880``).  One
 * :class:`ControllerState` per player (up to 4) — the array lives at
 * ``DAT_0037BE98`` and striding is 0x54 bytes
 * (``AZURIK_CONTROLLER_STATE_VA + player_index * 0x54``).
 *
 * All analog axes are normalised into ``[-1.0, 1.0]`` (sticks) or
 * ``[0.0, 1.0]`` (triggers / analog buttons); digital buttons are
 * either exactly ``0.0`` or ``1.0`` — the engine never pushes
 * intermediate values.  D-pad axes are three-valued:
 * ``-1.0 / 0.0 / +1.0``.
 *
 * Edge-detection: the 12 bytes at +0x48..+0x53 are a per-button
 * "was pressed last frame" latch.  One byte per button-like field
 * in the +0x18..+0x47 range (12 fields → 12 latch bytes, matching
 * order).  Engine callers read a rising edge as
 * ``current > 0 && latch == 0`` and write ``latch = 1`` after
 * consuming the press; the polling loop clears ``latch`` when the
 * button goes back to zero.  Shims that hook per-frame logic may
 * read ``edge_state[]`` directly to avoid double-firing on held
 * buttons.
 *
 * ``DAT_001A7AE4`` holds the "active player index" (0..3), or 4 if
 * no controller is connected.  Shims that act on the active player
 * only should dereference
 * ``ControllerState *active = &players[DAT_001A7AE4]`` when
 * ``DAT_001A7AE4 != 4``.
 */

/* Stride in bytes between per-player ControllerState entries. */
#define AZURIK_CONTROLLER_STRIDE      0x54u

typedef struct ControllerState {
    /* --- Analog sticks (normalised to [-1.0, 1.0]) ---
     * XInput dead-zone processing in FUN_000a2880:
     *   raw = XINPUT_GAMEPAD.sThumb{LX,LY,RX,RY}
     *   if (raw < 0)  value = max(-1, (raw + 12000) * 4.815332e-5)
     *   else          value = min( 1, (raw - 12000) * 4.815332e-5)
     * — so anything inside ±12000 of centre reads as exactly 0.0.
     * The 4.815332e-5 factor normalises the remaining 20768 units
     * of travel into ±1.0.
     */
    f32 left_stick_x;                 /* +0x00 — sThumbLX normalised */
    f32 left_stick_y;                 /* +0x04 — sThumbLY normalised */
    f32 right_stick_x;                /* +0x08 — sThumbRX normalised */
    f32 right_stick_y;                /* +0x0C — sThumbRY normalised */

    /* --- D-pad (three-valued per axis: -1, 0, +1) ---
     * D-pad-X is derived from bits 0x04 (LEFT) / 0x08 (RIGHT);
     * D-pad-Y from 0x01 (UP) / 0x02 (DOWN) of XINPUT_GAMEPAD.wButtons:
     * X at +0x10, Y at +0x14 (0xA2B75-0xA2BA9 [verified 2026-10-11,
     * capstone]; the names were swapped until Step 4.41a, AZ-234).
     */
    f32 dpad_x;                       /* +0x10 — D-pad X: +1 right, -1 left, 0 */
    f32 dpad_y;                       /* +0x14 — D-pad Y: +1 up, -1 down, 0    */

    /* --- Analog buttons (pressure 0.0..1.0, from XINPUT analog bytes) ---
     * Dead-zone: raw < 30 reads as 0.0.
     * Scale: (raw - 30) * 0.0044444446 ≈ 1/225 gives the 1.0-cap.
     * Order matches XINPUT_GAMEPAD.bAnalogButtons[] exactly. */
    f32 button_a;                     /* +0x18 — A analog pressure        */
    f32 button_b;                     /* +0x1C — B analog pressure        */
    f32 button_x;                     /* +0x20 — X analog pressure        */
    f32 button_y;                     /* +0x24 — Y analog pressure        */
    f32 button_black;                 /* +0x28 — BLACK analog pressure    */
    f32 button_white;                 /* +0x2C — WHITE analog pressure    */
    f32 trigger_left;                 /* +0x30 — LT analog pressure       */
    f32 trigger_right;                /* +0x34 — RT analog pressure       */

    /* --- Digital buttons (exactly 0.0 or 1.0) ---
     * From XINPUT_GAMEPAD.wButtons bit flags:
     *   bit 0x40 → stick_left_click  (LEFT_THUMB)
     *   bit 0x80 → stick_right_click (RIGHT_THUMB)
     *   bit 0x10 → start_button      (START)
     *   bit 0x20 → back_button       (BACK)
     */
    f32 stick_left_click;             /* +0x38 — L-stick press             */
    f32 stick_right_click;            /* +0x3C — R-stick press             */
    f32 start_button;                 /* +0x40 — START                     */
    f32 back_button;                  /* +0x44 — BACK                      */

    /* --- Edge-detect latch bytes (12 × u8) ---
     * One per ``button_*`` / ``trigger_*`` / ``stick_*`` / ``start`` /
     * ``back`` field above (12 total, same order).  The polling loop
     * clears each byte when its corresponding button returns to 0.0,
     * which is how the engine implements "consume rising edge once
     * per press" without dedicated edge-detect state elsewhere.
     */
    u8  edge_state[12];               /* +0x48..+0x53                      */
} ControllerState;


/* ==========================================================================
 * PlayerInputState
 * ==========================================================================
 * Per-frame player-movement state the engine fills from stick input
 * and the current critter's ``CritterData`` fields.  Populated by
 * ``player_input_build`` (0x84F90); the magnitude + direction outputs
 * at the end are written by ``player_input_tick`` and consumed by
 * ``player_walk_state``
 * which computes
 *
 *     velocity = critter->run_speed * magnitude * unit_direction
 *
 * Observed writes reach at least +0x17C (animation state).  Offsets
 * we understand are named; gaps are ``_reservedNN``.  Shim authors
 * who only need the output fields (magnitude + direction_*) can
 * safely ignore everything else.
 */

/* Flag bits at offset 0x20 of PlayerInputState.flags (u8).  Both
 * bits are tested by ``FUN_00084940`` — FALLING selects the
 * physics-only branch (stick ignored, magnitude from +0x0C);
 * RUNNING multiplies the final magnitude by 3.0 (at the shared
 * constant site in vanilla; player_physics C1 redirects that to a
 * per-game constant). */
#define PLAYER_FLAG_FALLING  0x01u
#define PLAYER_FLAG_RUNNING  0x40u
/* Other bits (0x02 / 0x04 / 0x08 / 0x10 / 0x20 / 0x80) exist in the
 * engine but aren't fully classified.  Shims should treat them as
 * read-only and not clobber them on write. */

typedef struct PlayerInputState {
    u32 entity_class_ptr;             /* +0x00 piVar1 — class vtable ptr             */
    u32 frame_dt_fixed;               /* +0x04 — f32 dt copied from VA 0x1980A0:
                                       *          1/30 s vanilla, 1/60 s with
                                       *          fps_unlock.  Not a constant. */
    f32 stick_x;                      /* +0x08 — raw stick X component               */
    f32 stick_y;                      /* +0x0C — raw stick Y component (also used
                                       *          as the falling-state "delta")      */
    f32 fall_angle;                   /* +0x10 — angle used in falling branch        */
    f32 idle_angle;                   /* +0x14 — angle used when stick is neutral    */
    f32 walk_angle;                   /* +0x18 — angle used when stick is pushed     */
    f32 stick_magnitude;              /* +0x1C — sqrt(x²+y²), in [0, 1]              */

    u8  flags;                        /* +0x20 — PLAYER_FLAG_*                       */
    u8  dead;                         /* +0x21 — nonzero after death                 */
    u8  _reserved_22;                 /* +0x22                                       */
    u8  _reserved_23;                 /* +0x23                                       */

    /* +0x24..+0x2C — 3D world-space reference point, used as the
     * "self" anchor in the dead-state fpatan that faces the player
     * toward +0x3C..+0x44 when dead.  Speculative but plausibly the
     * live position; shims that need real position should prefer the
     * entity struct's +0x24..+0x2C fields. */
    f32 ref_x;                        /* +0x24 (speculative)                         */
    f32 ref_y;                        /* +0x28 (speculative)                         */
    f32 ref_z;                        /* +0x2C (speculative)                         */

    u8  _reserved_30[0x04];           /* +0x30 — orientation / rotation scratch      */
    CritterData *critter_data;        /* +0x34 — ptr to the player's CritterData     */
    u8  _reserved_38[0x04];           /* +0x38                                       */

    /* +0x3C..+0x44 — reference point used as the target-of-facing in
     * the dead-state fpatan.  Mirrors +0x24..+0x2C. */
    f32 target_x;                     /* +0x3C (speculative)                         */
    f32 target_y;                     /* +0x40 (speculative)                         */
    f32 target_z;                     /* +0x44 (speculative)                         */

    /* +0x48..+0x120 — interior of the struct we haven't reverse-
     * engineered in detail.  Animation / IK / step-detection scratch
     * lives here; player_input_build (0x84F90) copies the entity's position into
     * +0x48..+0x50.  Leave untouched unless your shim has a reason
     * to poke a specific offset — if so, document it and move it
     * out of this gap into a named field. */
    u8  _reserved_48[0x120 - 0x48];   /* +0x48 */

    /* --- magnitude + direction outputs of FUN_00084940 ---
     * The only fields player_physics C1 touches.  magnitude is the
     * final scalar (stick magnitude * 3.0 when PLAYER_FLAG_RUNNING
     * is set, otherwise just stick magnitude).  direction_xyz is a
     * unit vector derived from direction_angle, with direction_z
     * always 0 because Azurik's player movement is 2D horizontal. */
    f32 direction_angle;              /* +0x120 — output angle (radians)             */
    f32 magnitude;                    /* +0x124 — walking = stick mag; running = ×3  */
    f32 direction_x;                  /* +0x128 — -sin(direction_angle)              */
    f32 direction_y;                  /* +0x12C —  cos(direction_angle)              */
    f32 direction_z;                  /* +0x130 — always 0 (Azurik is 2D horizontal) */
} PlayerInputState;


/* ==========================================================================
 * BootState
 * ==========================================================================
 * The global boot state machine at ``DAT_001bf61c``, stepped by
 * ``FUN_0005f620`` (the function that plays the boot movies and
 * transitions to the main menu / in-game state).  Enum values are
 * the ``case N`` labels in the switch at 0x5F635.  Useful if a shim
 * wants to change boot flow (e.g. skip all movies, land directly in
 * the menu).
 */
typedef enum BootState {
    BOOT_STATE_INIT          = 0,     /* initial dispatch / resource loading        */
    BOOT_STATE_PLAY_LOGO     = 1,     /* play AdreniumLogo.bik (skip_logo sits here) */
    BOOT_STATE_POLL_LOGO     = 2,     /* polling the logo movie                     */
    BOOT_STATE_PLAY_PROPHECY = 3,     /* play prophecy.bik                          */
    BOOT_STATE_POLL_PROPHECY = 4,     /* polling prophecy                           */
    BOOT_STATE_FADE_IN       = 5,     /* post-movie transition                      */
    BOOT_STATE_MENU_ENTER    = 6,     /* enter the main menu                        */
    BOOT_STATE_MENU          = 7,     /* main menu active                           */
    BOOT_STATE_LOAD_SAVE     = 8,     /* save-selection / load flow                 */
    BOOT_STATE_INGAME        = 9,     /* in-game: engine update loop runs here      */
} BootState;

/* ==========================================================================
 * Entity — global named-object registry entry
 * ==========================================================================
 * Everything the game identifies by name (critters, pickups, shader
 * files, etc.) lives in ``ENTITY_REGISTRY`` — an array of
 * ``Entity *`` between ``AZURIK_ENTITY_REGISTRY_BEGIN_VA`` and
 * ``_END_VA``.  Looked up by the vanilla ``entity_lookup`` function.
 *
 * **Partial layout** — only the ``name`` pointer at offset 0 is
 * currently pinned.  Entity instances are extended by multiple
 * systems (animation, AI, collision) so the tail size isn't fixed.
 * Shim authors needing specific fields should declare a
 * locally-scoped ``extern``, verify via Ghidra, then consider
 * contributing a fix back here.
 */
typedef struct Entity {
    const char *name;          /* +0x00 — NUL-terminated asset key     */
    /* +0x04 .. end: opaque.  Cast to a more-specific struct
       once Ghidra identifies the subtype. */
} Entity;


/* ==========================================================================
 * ConfigTable — keyed-table config section handle (config.xbr)
 * ==========================================================================
 * Runtime handle to one of the 18 keyed tables in
 * ``config.xbr`` (critters_critter_data, critters_damage, magic,
 * etc.).  Consumed by the vanilla helpers:
 *
 *   ``config_name_lookup(this, name)``  → column index (row_idx)
 *     (__thiscall: the table in ECX, ``name`` on the stack)
 *   ``config_cell_value(grid, row, col, default_out)`` → float10
 *     (__stdcall(16): all four on the stack, the table first)
 *
 * **Header layout** (verified from ``FUN_000D1520`` / ``FUN_000D1420``
 * decomp — note the field names here follow the decompiler's
 * orientation; ``src/azurkit/core/xbr/keyed.py`` uses the
 * opposite row/col naming, kept for backward compat):
 */
typedef struct ConfigTable {
    i32 num_cols;             /* +0x00 — iteration bound used by        */
                              /* config_name_lookup; typically the      */
                              /* per-entity count                       */
    i32 col_hdr_offset;       /* +0x04 — byte offset (relative to this) */
                              /* of the 8-byte-stride column-header     */
                              /* table (``name_ptr``, ``name_off``) */
    i32 num_rows;             /* +0x08 — bound for the row-index arg    */
                              /* of config_cell_value                   */
    i32 total_cells;          /* +0x0C — num_rows * num_cols            */
    i32 cell_data_offset;     /* +0x10 — byte offset (relative to this) */
                              /* of the 16-byte-stride cell data        */
    /* Rows start at ``(u8*)this + 0x14`` */
} ConfigTable;

/* Cell record — one 16-byte slot inside the cell data array.
 * Cell stride in bytes: ``((row * num_cols) + col) * 16``.
 */
typedef struct ConfigCell {
    i32 kind;                 /* +0x00 — 0=null_default / 1=number      */
                              /*          2=string / 3=nested_ptr       */
                              /*          (0, 1 confirmed from decomp;  */
                              /*           2, 3 probable — see xbr doc) */
    u32 _reserved_04;         /* +0x04 — padding / flags                */
    f64 value;                /* +0x08 — 8-byte double when kind==1     */
} ConfigCell;


/* ==========================================================================
 * IndexEntry — a loaded run of an XBR's TOC entries (load_asset_by_fourcc)
 * ==========================================================================
 * Not index.xbr's lookup machinery, whatever the names say (AZ-247).
 * This is the 28-byte descriptor of one loaded run of an archive's
 * 16-byte TOC entries: the array at [0x37BE50], stride 0x1C (0xA59F0's
 * ``imul 0x1c``; the run builder divides by 28 at 0xA4D55).
 *
 * ``load_asset_by_fourcc`` (0xA67A0) takes a handle in EAX and a fourcc
 * on the stack.  A negative EAX returns ~EAX with no lookup (0xA67A8).
 * A handle is (archive slot << 20) | TOC index: 0xA59F0 picks the
 * archive in [0x37BE34] by bits 20-30, and its u16 table at
 * archive+0x28, indexed by the low 20 bits, gives the run (0x8000 =
 * none).  It calls 0xA59F0 with EAX = 2, which loads on demand: for a
 * handle with no run it builds one (0xA4C00), and for that run or one
 * still at 0x1000 it starts the load (0xA5480 sets 0x2000); 0xA67A0
 * then waits while 0x2000 (0xA67E1), so a call can block on a load.
 * At 0x3000, entry = records + 16 * (handle - first_record_idx)
 * (``shl eax, 4`` at 0xA683C); a hit on the fourcc at entry+8 (0xA6842)
 * returns file_base_offset - records[0].offset + entry.offset, a
 * pointer to the entry's loaded payload.  It returns 0 only on a failed
 * lookup or build, a state other than 0x3000 after the wait (0xA6830)
 * or a fourcc miss.
 * [verified 2026-10-11, capstone over the vanilla XBE]
 *
 * The types and field names stay until AzurKit 4.2/4.3 (D68): read each
 * field by its comment.
 */
typedef struct IndexEntry {
    u32 _reserved_00;         /* +0x00 — list link, next (0xA6205)       */
    u32 _reserved_04;         /* +0x04 — list link, prev (0xA6205)       */
    u32 first_record_idx;     /* +0x08 — handle of records[0] (slot << 20 | TOC index) */
    struct IndexRecord *records; /* +0x0C — the run's 16-byte TOC entries, not IndexRecords */
                              /* (offset, size, tag at +8, flags:        */
                              /* docs/XBR_FORMAT.md § "Table of contents") */
    u32 file_base_offset;     /* +0x10 — a pointer: records[0]'s loaded payload */
    u8  _reserved_14[6];      /* +0x14 .. +0x19 — +0x14 holds [0x1BE36C]; +0x18 a u16 refcount */
                              /* (+0x14 set at 0xA4DE8; +0x18 zeroed at  */
                              /* 0xA4DE0, decremented at 0xA61F4)        */
    u16 flags;                /* +0x1A — bits 0-6 entry count; 0x3000 state; bit 15 a flag */
                              /*          (flags & 0x3000) == 0x1000 ⇒ built, not loaded */
                              /*          (flags & 0x3000) == 0x2000 ⇒ loading */
                              /*          (flags & 0x3000) == 0x3000 ⇒ loaded  */
                              /*          (set at 0xA4DD9, waited on at  */
                              /*          0xA67E1, set at 0xA587C; bit   */
                              /*          15 set at 0xA4DED, cleared at  */
                              /*          0xA6251)                       */
    /* +0x1C: the end (the array's stride) */
} IndexEntry;

/* Not a layout the engine reads here (AZ-247): ``load_asset_by_fourcc``
 * reads the 16-byte TOC entries IndexEntry describes.  It is 20 bytes,
 * the size of an index.xbr record, but these fields are the framing
 * AZ-218 disproved; each comment gives what that record really holds at
 * the offset (``docs/RE_DATA.md`` § index.xbr).  The type and its
 * fields stay until AzurKit 4.2/4.3 (D68). */
typedef struct IndexRecord {
    u32 length;               /* +0x00 — index.xbr: key length (no NUL)  */
    u32 off1;                 /* +0x04 — key pointer, relative to itself */
    char fourcc[4];           /* +0x08 — not the fourcc: the archive-name length */
    u8  disc;                 /* +0x0C — the archive-name pointer's low byte */
    u8  pad[3];               /* +0x0D .. +0x0F — the rest of that pointer */
    u32 off2;                 /* +0x10 — the fourcc                      */
} IndexRecord;


/* ==========================================================================
 * MovieContext — Bink playback state (opaque w/ vtable)
 * ==========================================================================
 * Pointed to by ``AZURIK_MOVIE_CONTEXT_PTR_VA``.  Allocated by
 * ``FUN_000D00F0`` (Bink init), stepped by ``poll_movie`` each frame.
 * The internals are allocated by the Bink library and depend on
 * frame count / resolution; all the game code needs is the vtable
 * at offset 0.
 *
 * Observed vtable slots (from ``poll_movie`` + ``boot_state_tick``
 * case 2):
 *
 *   vtable[0x00] = advance(ctx, dt_seconds)     — called every tick
 *   vtable[0x04] = is_done(ctx) -> bool          — true when finished
 *   vtable[0x10] = destroy(ctx, release_flag)    — tear down
 *
 * Shims that want to observe or abort playback should call through
 * the vtable (so Bink-internal state stays coherent) rather than
 * touching struct fields directly.
 */
/* Forward declare so the vtable can name its receiver type. */
struct MovieContext;

typedef struct MovieContextVTable {
    void (*advance)(struct MovieContext *ctx, float dt_seconds);   /* +0x00 */
    u32 (*is_done)(struct MovieContext *ctx);                      /* +0x04 */
    void (*_reserved_08)(void);                                    /* +0x08 */
    void (*_reserved_0C)(void);                                    /* +0x0C */
    void (*destroy)(struct MovieContext *ctx, int release_flag);   /* +0x10 */
} MovieContextVTable;

typedef struct MovieContext {
    const MovieContextVTable *vtable;  /* +0x00 */
    /* +0x04 .. end: Bink-library-owned opaque state.  Don't touch. */
} MovieContext;
/* ==========================================================================
 * Time / frame pacing
 * ========================================================================== */

/* VANILLA simulation step only — 1/30 = 0.03333... as a 32-bit float,
 * IEEE 754 bit pattern 0x3D088889.  dt is NOT fixed: the fps_unlock
 * pack rewrites the dt sources (e.g. VA 0x1980A0, the player dt) to
 * 1/60 and raises the step cap at VA 0x059AFD / 0x059B37.  Shims that
 * scale per-tick effects (velocity integrators, timers) must read the
 * live dt, e.g. PlayerInputState.frame_dt_fixed (+0x04), and never
 * hardcode these two macros. */
#define AZURIK_SIM_DT_SECONDS_BITS   0x3D088889u
#define AZURIK_SIM_DT_SECONDS_F32    (1.0f / 30.0f)

/* Kernel tick counter — xboxkrnl exports the variable ``KeTickCount``
 * via the thunk table (ordinal 156).  Shim code that wants a monotonic
 * "ticks since boot" value should ``#include "azurik_kernel.h"``
 * and read ``KeTickCount`` (a ``__declspec(dllimport)`` variable, not
 * a function); the D1 layout pass resolves it to the thunk slot, so
 * hardcoding the thunk VA here would be brittle. */

/* ==========================================================================
 * Conveniences
 * ========================================================================== */

/* ``CONTAINER_OF(ptr, type, member)`` — get a pointer to the enclosing
 * struct from a pointer to one of its members.  Lets a shim that
 * hooks on (say) a velocity field reach the rest of the
 * PlayerInputState. */
#define CONTAINER_OF(ptr, type, member) \
    ((type *)((u8 *)(ptr) - (u32)&((type *)0)->member))


/* ==========================================================================
 * Drift-guard static asserts
 * ==========================================================================
 * Every late named field is pinned with `offsetof` so re-ordering
 * anything above it breaks the build instead of silently producing
 * wrong machine code.  If you add a new named field to a struct,
 * ADD A MATCHING ASSERT HERE. */
#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(u32) == 4,  "u32 must be 4 bytes");
_Static_assert(sizeof(u8)  == 1,  "u8 must be 1 byte");
_Static_assert(sizeof(f32) == 4,  "f32 must be 4 bytes");

_Static_assert(__builtin_offsetof(CritterData, hit_points) == 0x14,
               "CritterData.hit_points drifted — piVar9[5] slot is where "
               "load_critters_config stores the _ftol-truncated "
               "critters_damage.hitPoints value");
_Static_assert(__builtin_offsetof(CritterData, collision_radius) == 0x18,
               "CritterData.collision_radius drifted");
_Static_assert(__builtin_offsetof(CritterData, walk_speed) == 0x38,
               "CritterData.walk_speed drifted");
_Static_assert(__builtin_offsetof(CritterData, run_speed) == 0x40,
               "CritterData.run_speed drifted");
_Static_assert(__builtin_offsetof(CritterData, ouch1_knockback) == 0x50,
               "CritterData.ouch1_knockback drifted — is ouch2_threshold "
               "still at +0x48?");
_Static_assert(__builtin_offsetof(CritterData, hits_through_walls) == 0x7C,
               "CritterData.hits_through_walls drifted (byte layout around "
               "useCenterBasis / alwaysGlued / noFreeze broke)");
_Static_assert(__builtin_offsetof(CritterData, drown_time) == 0x80,
               "CritterData.drown_time drifted");
_Static_assert(__builtin_offsetof(CritterData, shadow_size) == 0x94,
               "CritterData.shadow_size drifted");
_Static_assert(__builtin_offsetof(CritterData, shadow_texture_res) == 0x9C,
               "CritterData tail drifted past shadow_texture_res");
_Static_assert(__builtin_offsetof(CritterData, range) == 0xB8,
               "CritterData.range drifted — _reserved_A0 gap size wrong?");
_Static_assert(__builtin_offsetof(CritterData, attack_range) == 0xC4,
               "CritterData.attack_range drifted — range[] layout broke");
_Static_assert(__builtin_offsetof(CritterData, drop_1) == 0xD4,
               "CritterData.drop_1 drifted — _reserved_C8 gap size wrong?");
_Static_assert(__builtin_offsetof(CritterData, drop_5) == 0xE4,
               "CritterData.drop_5 drifted");
_Static_assert(__builtin_offsetof(CritterData, drop_count_1) == 0xE8,
               "CritterData.drop_count_1 drifted");
_Static_assert(__builtin_offsetof(CritterData, drop_count_5) == 0xF8,
               "CritterData.drop_count_5 drifted");
_Static_assert(__builtin_offsetof(CritterData, drop_chance_1) == 0xFC,
               "CritterData.drop_chance_1 drifted");
_Static_assert(__builtin_offsetof(CritterData, drop_chance_5) == 0x10C,
               "CritterData.drop_chance_5 drifted");

/* ControllerState (from XInput polling in FUN_000a2880). */
_Static_assert(sizeof(ControllerState) == 0x54,
               "ControllerState must be exactly 0x54 bytes — the "
               "per-player stride the XInput poll uses");
_Static_assert(__builtin_offsetof(ControllerState, left_stick_x) == 0x00,
               "ControllerState.left_stick_x drifted");
_Static_assert(__builtin_offsetof(ControllerState, right_stick_y) == 0x0C,
               "ControllerState.right_stick_y drifted");
_Static_assert(__builtin_offsetof(ControllerState, dpad_x) == 0x10,
               "ControllerState.dpad_x drifted — 0xA2B75 writes the "
               "D-pad's X axis there");
_Static_assert(__builtin_offsetof(ControllerState, dpad_y) == 0x14,
               "ControllerState.dpad_y drifted");
_Static_assert(__builtin_offsetof(ControllerState, button_a) == 0x18,
               "ControllerState.button_a drifted");
_Static_assert(__builtin_offsetof(ControllerState, trigger_right) == 0x34,
               "ControllerState.trigger_right drifted");
_Static_assert(__builtin_offsetof(ControllerState, stick_left_click) == 0x38,
               "ControllerState.stick_left_click drifted");
_Static_assert(__builtin_offsetof(ControllerState, start_button) == 0x40,
               "ControllerState.start_button drifted");
_Static_assert(__builtin_offsetof(ControllerState, back_button) == 0x44,
               "ControllerState.back_button drifted");
_Static_assert(__builtin_offsetof(ControllerState, edge_state) == 0x48,
               "ControllerState.edge_state drifted");

_Static_assert(__builtin_offsetof(PlayerInputState, stick_magnitude) == 0x1C,
               "PlayerInputState.stick_magnitude drifted");
_Static_assert(__builtin_offsetof(PlayerInputState, flags) == 0x20,
               "PlayerInputState.flags drifted");
_Static_assert(__builtin_offsetof(PlayerInputState, critter_data) == 0x34,
               "PlayerInputState.critter_data drifted");
_Static_assert(__builtin_offsetof(PlayerInputState, direction_angle) == 0x120,
               "PlayerInputState.direction_angle drifted");
_Static_assert(__builtin_offsetof(PlayerInputState, magnitude) == 0x124,
               "PlayerInputState.magnitude drifted — C1 patch would "
               "silently clobber the wrong field");
_Static_assert(__builtin_offsetof(PlayerInputState, direction_x) == 0x128,
               "PlayerInputState.direction_x drifted");
_Static_assert(__builtin_offsetof(PlayerInputState, direction_z) == 0x130,
               "PlayerInputState.direction_z drifted");

/* ConfigTable (from FUN_000D1420 / FUN_000D1520). */
_Static_assert(__builtin_offsetof(ConfigTable, num_cols) == 0x00,
               "ConfigTable.num_cols must be first field — "
               "config_name_lookup does *(int*)this");
_Static_assert(__builtin_offsetof(ConfigTable, num_rows) == 0x08,
               "ConfigTable.num_rows drifted — config_cell_value "
               "reads param_1[2] as the row-index bound");
_Static_assert(__builtin_offsetof(ConfigTable, cell_data_offset) == 0x10,
               "ConfigTable.cell_data_offset drifted — "
               "config_cell_value reads param_1[4] for it");
_Static_assert(sizeof(ConfigTable) == 0x14,
               "ConfigTable header is exactly 20 bytes; rows start "
               "at this+0x14 per config_cell_value");
_Static_assert(sizeof(ConfigCell) == 0x10,
               "ConfigCell stride MUST be 16 bytes — the "
               "(*param_1 * row + col) * 0x10 arithmetic relies on it");

/* IndexEntry (from FUN_000A67A0): piVar3 is the run descriptor, and
 * these four offsets hold for it (AZ-247; the struct's comments). */
_Static_assert(__builtin_offsetof(IndexEntry, first_record_idx) == 0x08,
               "IndexEntry.first_record_idx drifted — "
               "load_asset_by_fourcc uses piVar3[2]");
_Static_assert(__builtin_offsetof(IndexEntry, records) == 0x0C,
               "IndexEntry.records drifted — piVar3[3]");
_Static_assert(__builtin_offsetof(IndexEntry, file_base_offset) == 0x10,
               "IndexEntry.file_base_offset drifted — piVar3[4]");
_Static_assert(__builtin_offsetof(IndexEntry, flags) == 0x1A,
               "IndexEntry.flags drifted — *(ushort*)(piVar3 + 0x1A)");

/* IndexRecord: these pin the declared layout only.  load_asset_by_fourcc
 * compares the fourcc at +8 of a 16-byte TOC entry, not of this record,
 * and an index.xbr record holds its fourcc at +0x10 (AZ-247, AZ-218).
 * The asserts stay with the type until AzurKit 4.2/4.3 (D68). */
_Static_assert(sizeof(IndexRecord) == 0x14,
               "IndexRecord must be exactly 20 bytes — the index.xbr "
               "record table uses a 20-byte stride");
_Static_assert(__builtin_offsetof(IndexRecord, off1) == 0x04,
               "IndexRecord.off1 drifted");
_Static_assert(__builtin_offsetof(IndexRecord, fourcc) == 0x08,
               "IndexRecord.fourcc drifted — this pins the declared "
               "layout only: load_asset_by_fourcc compares +8 of a "
               "16-byte TOC entry, not of an IndexRecord (AZ-247)");
_Static_assert(__builtin_offsetof(IndexRecord, off2) == 0x10,
               "IndexRecord.off2 drifted");

/* MovieContext (vtable-at-0 pattern; size not pinned — Bink-owned). */
_Static_assert(__builtin_offsetof(MovieContext, vtable) == 0x00,
               "MovieContext.vtable must be first field — poll_movie "
               "indirects through *DAT_001bcdb0 at offset 0");
#endif


/* ==================================================================
 * Player entity field offsets (April 2026 late RE pass)
 *
 * The player entity struct is reached as ``entity`` in the physics
 * state-machine dispatch (``FUN_0008CCC0``).  ESI / unaff_ESI in
 * the per-state functions is the same pointer.  Key fields and
 * their physics roles:
 *
 *   +0x20   critter object (current HP at +0x210, max HP at +0x214;
 *           the ArmorMgr chain below starts here).  Not the input
 *           state: PlayerInputState is built on the per-frame player
 *           tick's (0x8C230) stack and passed in.
 *   +0x24   velocity.x
 *   +0x28   velocity.y
 *   +0x2C   velocity.z
 *   +0x30   a pointer 0x150 bytes into an object (0x8CCC0 takes
 *           [+0x30] - 0x150 as the object; probably the one underfoot,
 *           inferred); 0 or 0x150 = none.  Not a type.
 *   +0x60   flags byte (bit 0x4 = jumped_this_frame? etc.)
 *   +0x94   state (0 ground, 1 climb, 2 air, 3/4 slope-slide,
 *                  5 zipline ride, 6 swim, 7-8 dead; bit 0x100 an attack
 *                  move, the roll or a hit reaction, not a cutscene:
 *                  player_attack_enter 0x88990 is passed 0x100 on the
 *                  ground and 0x102 in the air, the hit handler
 *                  0x8D600 sets 0x102, and a landing leaves 0x100)
 *   +0x124  magnitude (stick mag, ×3 with cheat flag 0x40 —
 *                      computed per frame by player_input_tick)
 *   +0x128..+0x130  direction vector (normalized stick dir)
 *   +0x134  attack entry index (0x7F1F0 stores it; 20 = the roll,
 *           'roll forward'); ledge-grab use unproven
 *   +0x140  air_control_speed (9.0 default, 12.0 w/ air power)
 *   +0x144  jump_height       (1.1 default, 1.2 w/ air power)
 *   +0x148/0x14C  hold-jump timer and its vz (spike; xemu read
 *                 +0x148 = -0.033, then -0.100, early in a jump)
 *   +0x150  "airborne-entered" flag byte
 *   +0x164  peak_z (max height reached this jump; used by
 *                    wing_flap for flap-height budget)
 *   +0x168  prev_z (fall-damage dispatcher input)
 *   +0x16C  misc flags (bit 0x2 = had-landed)
 *   +0xD8   flap_counter (INCREMENTED per flap; compared vs
 *                         armor.flap_count by wing_flap)
 *
 * PlayerInputState (built on 0x8C230's stack each tick, passed to
 * the state functions; entity[+0x20] does not point at it):
 *   +0x20   flags byte — bit 0x40 = developer cheat-buttons turbo
 *                                      (R3 or WHITE, only while the cvar
 *                                      "enable cheat buttons" is on; 0 in
 *                                      retail; not the roll)
 *                         bit 0x20 = BLACK (starts the roll)
 *                         bit 0x04 = JUMP button edge-triggered
 *                         bit 0x02, 0x08, 0x10 = misc inputs
 *   +0x48..+0x4D   edge-lock bytes for various button bits
 *
 * ArmorMgr chain (reached via entity[+0x20].gameplay_ptr[+0x154][+0xCC]):
 *   armor_mgr +0x20   → level_struct pointer
 *   armor_mgr +0x24   → fuel_current  (float, consumed by wing_flap)
 *   level_struct +0x08 → the slot's Level (int; no_armor_1 = 1).
 *                        Air power needs Level 1-3 AND Flaps != 0
 *   level_struct +0x38 → Flaps (int; 1/2/5 for air shields 1/2/3):
 *                        the per-jump flap cap and consume_fuel's
 *                        divisor (a flap takes 1/Flaps of the 1.0
 *                        gauge); there is no separate fuel_max
 *
 * IMPORTANT: ``DAT_001A7AE4`` is NOT the air-power level — it's
 * the active XInput CONTROLLER index (0-3 for port, 4 for
 * "no controller").  The wing_flap_count shim dispatches on
 * the level struct chain above, not on this global.
 * ================================================================== */

/* ==================================================================
 * Player-physics entity field offsets — named macros
 *
 * Typed access for shim code that wants to read / write player
 * fields without casting to a full struct.  Offsets are from the
 * base of the per-frame "entity" pointer (ESI in most physics
 * functions).  The PlayerInputState is a separate struct; see the
 * field list above.
 *
 * Each macro is meant to be used as:
 *
 *     float v = *(float *)((char *)entity + AZURIK_ENT_Z_VELOCITY);
 *
 * If you need more than a handful, declare a local struct.
 * ================================================================== */

#define AZURIK_ENT_INPUT_STATE_PTR   0x020  /* critter object, not input (misnamed) */
#define AZURIK_ENT_VELOCITY_X        0x024  /* float                     */
#define AZURIK_ENT_VELOCITY_Y        0x028  /* float                     */
#define AZURIK_ENT_VELOCITY_Z        0x02C  /* float (vertical)          */
#define AZURIK_ENT_TYPE              0x030  /* object ptr + 0x150, not a type (misnamed) */
#define AZURIK_ENT_FLAGS_BYTE        0x060  /* u8 flags                  */
#define AZURIK_ENT_STATE             0x094  /* physics state (see below) */
#define AZURIK_ENT_FLAP_COUNTER      0x0D8  /* int (used flaps so far)   */
#define AZURIK_ENT_MAGNITUDE         0x124  /* float (stick × boost)     */
#define AZURIK_ENT_DIRECTION_X       0x128  /* float (unit vec)          */
#define AZURIK_ENT_DIRECTION_Y       0x12C  /* float                     */
#define AZURIK_ENT_DIRECTION_Z       0x130  /* float (always 0 in 2D)    */
#define AZURIK_ENT_GRAB_TARGET       0x134  /* int attack entry index (20 = roll; misnamed) */
#define AZURIK_ENT_AIR_CONTROL       0x140  /* float (9.0 / 12.0)        */
#define AZURIK_ENT_JUMP_HEIGHT       0x144  /* float (1.1 / 1.2)         */
#define AZURIK_ENT_AIRBORNE_FLAG     0x150  /* u8                        */
#define AZURIK_ENT_PEAK_Z            0x164  /* float (flap ceiling)      */
#define AZURIK_ENT_PREV_Z            0x168  /* float (fall-damage in)    */
#define AZURIK_ENT_MISC_FLAGS        0x16C  /* u8                        */

/* Player physics state values (at AZURIK_ENT_STATE). */
enum PlayerPhysicsState {
    AZURIK_PPS_GROUND       = 0,  /* walking / idle            */
    AZURIK_PPS_CLIMB        = 1,  /* climbing / hanging-ledge  */
    AZURIK_PPS_AIRBORNE     = 2,  /* post-jump / pre-landing   */
    AZURIK_PPS_SLOPE_SLIDE  = 3,  /* slow slope-slide          */
    AZURIK_PPS_SLOPE_FAST   = 4,  /* fast/momentum slope-slide */
    AZURIK_PPS_PREJUMP      = 5,  /* the zipline ride (0x8A510) */
    AZURIK_PPS_SWIM         = 6,  /* swimming                  */
    AZURIK_PPS_GAMEOVER     = 7,  /* HP == 0, gameover showing */
    AZURIK_PPS_DEAD         = 8,  /* fully dead, respawning    */
    /* bit 0x100 = an attack move, the roll or a hit reaction (0x102
     * when begun in the air or by a hit; not enumerated here) */
};

/* PlayerInputState flag bits (byte at [input_state + 0x20]). */
#define AZURIK_INPUT_JUMP_EDGE      0x04  /* jump button edge-triggered */
#define AZURIK_INPUT_WHITE_BACK     0x40  /* cheat-buttons turbo (not the roll; misnamed) */


/* ==================================================================
 * ArmorMgr chain — fuel / air-power lookups
 *
 * Reached from an entity via:
 *
 *     ArmorMgr *armor_mgr =
 *         *(ArmorMgr **)(
 *             *(void **)(
 *                 *(void **)((char *)entity + 0x20) + 0x154)
 *           + 0xCC);
 *
 * (EDI in wing_flap / consume_fuel is the already-resolved
 * ArmorMgr pointer.  The chain above is only needed when starting
 * fresh from an entity.)
 * ================================================================== */

#define AZURIK_ARMOR_LEVEL_STRUCT    0x020  /* → armor level struct      */
#define AZURIK_ARMOR_FUEL_CURRENT    0x024  /* float gauge, 1.0 = full   */

/* Offsets within the level-struct pointed at by
 * ArmorMgr[+0x20].  Used by wing_flap and consume_fuel. */
#define AZURIK_LVL_AIR_POWER_LEVEL   0x008  /* int — the slot's Level (misnamed) */
#define AZURIK_LVL_FUEL_DRAIN_RATE   0x034  /* float — divisor in fuel drain */
#define AZURIK_LVL_FLAP_COUNT        0x038  /* int — Flaps: cap + fuel divisor */


#ifdef __cplusplus
}
#endif

#endif /* AZURIK_STRUCTS_H */
