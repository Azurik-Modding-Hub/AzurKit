# RE notes: game data files

> Ported from Azurik_Modkit's `docs/` (Step 4.11g); its paths, verbs and links point at AzurKit's since Step
> 4.24d. A `scripts/`, `tests/` or `shims/include/` path, a module or a doc that AzurKit lacks (often written
> "Modkit's") names Modkit's tree, where the finding was made; its history is the private archived repository
> (AGENTS.md § Porting from Modkit). Modkit's `azurik.h` is AzurKit's `devkit/re/data/structs.h` and `anchors.toml`,
> its `azurik_vanilla.h` and kernel headers are the ones shimkit writes from the facts (`src/azurkit/core/facts.*.json`,
> the functions' notes in `devkit/re/data/function_notes.toml`), and `python -m devkit AREA VERB` is the developer
> side's (`devkit/README.md`). Its "this repo" and "today" claims are Modkit's at the time: AGENTS.md is AzurKit's
> rule and wins where the two differ.

What the engine reads from its data files: `config.xbr`'s keyed
tables, `hourglass.xbr` and `fx.xbr` (with the wave codec),
`prefetch-lists.txt`, `filelist.txt` and the HDD cache, `selector.xbr`,
`index.xbr`, and the level-loading zones. Each finding cites the
function or VA it came from so you can re-verify.

Split from the old LEARNINGS notes (History, at the end, has the path)
in REORG_PLAN Step 3.3d (2026-10-10) without rewording, so "above" or
"below" may mean a section that is
now in [`RE_MOVEMENT.md`](RE_MOVEMENT.md) (player movement),
[`RE_XBE.md`](RE_XBE.md) (the XBE itself) or
Modkit's `Finished/LEARNINGS_HISTORY.md`
(superseded findings and retired attempts).

---

## Config / keyed tables

### `config.xbr` uses a custom keyed-table format

Each named table has:
1. A column-name row (string tokens).
2. Rows of data, each cell typed by the column name's `.n` / `.s` /
   `.f` / `.b` suffix.

At runtime 0xD1420 (`config_name_lookup`) finds a row by name:
`__thiscall`, the table in ECX and the name on the stack (`RET 4`).
0xD1520 (`config_cell_value`) reads a cell by index:
`__stdcall(16)`, `(grid, row, col, default_out)` on the stack
(`RET 0x10`), the value returned in ST(0); it panics on a row or
column out of range.  Both are registered vanilla symbols a shim can
call (`azurik_config.h`, `azurik_vanilla.h`); offline,
`src/azurkit/core/xbr/keyed.py` reads the tables.

### Duplicate column names: which one the game reads (V20, Step 2.84)

[verified 2026-10-15: a static read with capstone and `python -m devkit re xbe
calls|find-refs`, USA]: the engine's two by-name lookups take the
**first** match.  0xD1420 (rows; `config_name_lookup`) and 0xD1490
(columns, `__stdcall(grid, name)`, `RET 8`, 19 callers: each column's
row-0 string by 0xD1630, compared case-sensitively) both return the
first index whose name is equal, -1 for none.  The tables that repeat a
column name are read otherwise:

- `critters_flocking` (`good_noreht`, columns 12 and 19): its loader
  0x353F0 walks every column in order, finds the critter by the
  column's name (0x4B510) and stores a fresh record at critter+0xD0
  each time, so the **last** column wins and column 12 is dead data.
  The repo's last-match rule (`XBR_FORMAT.md` § Duplicate entity names)
  edits the live one.
- `critters_maya_stuff` (six pairs): never loaded.  The XBE holds no
  `maya` string; every other table's `config/<name>` is loaded by name.
- `critters_mutate` (`good_noreht` 0 and 1, `overlord` 4 and 5): its
  loader (0x36906) flags each named critter (+0x78 = 1) for every
  column, and the mutation check 0x36A3A accepts any column whose
  name and two more cells match, so both duplicates are live.
- `armor_hit_fx` and `attacks_transitions` repeat their row-0 strings
  (an fx path, a letter), which name no column; not traced.

So an edit to an earlier duplicate (AZ-012's `col`) lands in dead data
in `critters_flocking` and `critters_maya_stuff`, and is live in
`critters_mutate`; the edit path stays.

### `critters_engine`: `body` and `scale` (2026-10-11)

The engine reads the column names at fixed sites [verified 2026-10-11:
`python -m devkit re xbe find-refs --va 0x19FD50` (the
string `body`), and `--va` 0x19F668 (`scale`), 0x19F708 (`sound dir`)
and 0x1A07DC (`AICookie/`); capstone; HM-14]: `body` is pushed at
0x496DA (and loaded at 0x420A9) and `sound dir` at 0x496F6, with 0x496E3 calling
the row lookup 0xD1420; `scale` is pushed at 0x49913, with 0x49933
calling 0xD1420.  Entity+0x188 is written at 0x40608 and read at
0x3F049, just before 0x3F054 calls 0xA3860 (the hub mining called
0x3F049 a write; it is a read).  `AICookie/` is pushed at 0x6F728 and
a `:` compared at 0x6F750.

Per Azurik Level Studio's PAL comments [inferred for USA]: `body` names
`characters/<body>`, looked up case-folded; `scale` is a uniform render
scale (1.0 when empty), copied to entity+0x188 and applied to the
matrix basis only; an archetype string splits at its first `:`.

The data [verified 2026-10-11: `keyed_tables.load_all_tables` and the
archives' named-resource tables]: 184 archetypes, 180 with a `body`,
178 of which name a resource; `town_elder` → `townspeople/elder` and
`noship` → `test/cind_e_ship` name none (don't place them; no file of
the USA ISO holds either name but config.xbr, nor an `elder` or
`cind_e_ship` resource in any `.xbr` [verified 2026-10-19, Step 2.99]).  121
explicit scales take 14 values from 0.5 to 5.0; 63 are empty.

### Character bodies, their clips and the damage marker (2026-10-12)

What the player-model swap (`src/azurkit/tools/characters/_player_character.py`,
D112) relies on.  The static RE is the four angle reports (weapon,
roll-anims, attacks, species-survey) [workflow]; the counts below were
re-read with `azurkit.tools.characters.characters` [verified 2026-10-12: its
`read_body` over all 158 bodies equals the attacks angle's damage clips
and the survey's clip lists].

- **Where a clip comes from.** A species loads `characters/<body>`; the
  engine looks a clip `<name>` up as a full key, then as
  `characters/<body>/<name>` (0x4B600, case-blind).  A clip addresses bones
  and markers by raw index, so another body's clips can't be played as
  they are (below, "How a clip binds to a body").
  When the clip is missing, `anim_change` (0x42910) keeps the clip
  already playing: an attack or the roll then lasts 30 × (Move end2 −
  Move start) × L / Rate ticks, L that clip's length, which froze a
  flicken roll on its 5.6 s idle for 101 ticks (AZ-284).
- **Hit reactions** (Step 2.21d).  A hit plays anim 37-42 (`ouch_1`,
  `ouch_2`, `ouch_3`, `ouch_1r`, `ouch_1l`, `ouch_1b`), named by the XBE's
  base clip table, not by `config.xbr` (`RE_XBE.md` § "The player's hit
  reaction"); the clip plays at rate 1 and, on the ground, holds the
  player until it ends.  garret4 has `ouch_1` and its three directional
  twins, all 0.4 s.  56 of the 105 usable species wear a body with an
  `ouch_1`: garret4 and 55 others (0.67-3 s; `ouch_2` and `ouch_3` run
  to 5 s).  The other 49 wear a body with none of the six, so a hit
  plays no clip on them: 3 have no clips at all (gargoylestone,
  tesla_tree, tesla_tree_x), and barnacle's body has only an `ouch`,
  which no anim index names [verified 2026-10-12: each clip's length,
  `banm` +0x10, read with `azurkit.core.xbr.nodes`].  The player-model
  swap's X7 shim plays every reaction in garret4's 0.4 s (AZ-291,
  Modkit's `PATCHES.md`).
- **`body` layout.** +0 bone count and +4 a self-relative pointer to
  160-byte bone records, whose +0x60 is the bone's inverse bind matrix
  (16 f32 by rows, the translation in the last row; a bone's bind-pose
  position p solves p M = 0) [verified 2026-10-12: garret4's root joint's
  rest translation +0x30 (0, 0.05, 1.15) against its matrix's (0, −0.05,
  −1.15), and its highest bone 2.01 m against its `m_head` 1.993 m;
  `azurkit.tools.characters.characters.Body.top`]; +0x18 marker count and +0x1C a pointer to
  0x38-byte marker records: +0 name length, +4 name pointer, then 12
  f32 defaults (position, rotation, scale), of which +0x30 is the
  length and +0x34 the active value.  A bone record (Step 2.87;
  `azurkit.tools.characters.characters.BoneRecord`): +0 its name's length
  [verified 2026-10-21, Step 2.143: every bone of female_2 and garret4;
  +0xA and +0xC are 0 and +0x58 holds one value in every record, the
  exporter's], +4 a self-relative pointer
  to its name, +8 its parent's index (i16; −1 the root matrix), +0xB
  the segment-scale-compensate flag, +0x10 the rotate-axis quaternion
  RA (identity in every body), +0x20 the joint-orient quaternion JO,
  +0x30 the rest translation, +0x3C the rest rotation q, +0x4C the rest
  scale (quaternions x, y, z, w), +0x60 the inverse bind.  The local
  rotation is JO × q × RA (Hamilton; 0xCA470, `RE_XBE.md`), the rows
  scaled by S, the translation last, world = parent world × local
  [verified 2026-10-15: composing the rest values puts every bone of
  garret4 and balthazar_airship at the position its inverse bind gives,
  to 1e-5 m (`azurkit.tools.characters.retarget.Rig`); the 2.78 research
  composed the inverse binds themselves to 6e-7 on every garret4 and
  keylord bone and all but two balthazar_airship cheek bones, whose rest
  scale isn't 1].  A bone whose +0xB flag is set first has its matrix's
  columns divided by its parent's scale (0xCA4EC–0xCA51E, 0xA38C0; the
  caller 0xCB560–0xCB5CB passes the parent's, (1, 1, 1) for a root), so
  local = S × R × S_parent⁻¹ × T; an unkeyed scale is the rest scale
  (0xCB730 copies each record's T, q and S before the tracks) [verified
  2026-10-21, Step 2.139's review, `xbe fn` / `xbe dis`; the glTF export
  composes it so to 4e-6 m on every body and clip].  A leaf bone that
  weights no vertex, has no child and no clip keys (female_2 has 13: the
  `joint` ends under her jaw, brows and fingers; no relocation lies in
  their records) can take another parent and pose in place, the table's
  order (each parent before its child) kept: W29 re-parents `joint32`
  and `joint39` for a variant's jiggle bones (Step 2.143), and a
  palette's entry freed of a leaf child that rides its parent (no clip
  keys it) is exact to merge into the parent's [verified in game:
  sitting 2.143's J1, both bones at their records' rest on every idle
  tick].
- **Which bones a mesh group follows** (Step 2.106, AZ-491). Each
  `bmsh` group's +4 is a count and +8 an i32 self-relative pointer to
  that many i32 bone indices (`azurkit.tools.characters.characters.MeshGroup`);
  the body draw loads, for each entry, that bone's world matrix times its
  inverse bind (the loops at 0x3F2D2–0x3F34F and 0xCC8B7–0xCC92D, through
  0xE91BB and 0x9B320), and a vertex's four bone-slot bytes (+56) index
  that list, one per blend weight (+12): byte b names entry b-1 for 1–12
  and b-2 for 14–32, never 13 [verified 2026-10-19: data and capstone;
  the right-hand group lists the right-hand bones, the townswomen's vase
  group `vase_joint`; the slot bytes verified 2026-10-21, Step 2.130:
  every one of the 545,661 non-zero weights of every LOD decodes inside
  its group's palette]. The
  townsmen farmers' hoe is a group of their own mesh: on
  `townspeople/male_farmer_1`–`6` the 5th group of 5 (6th of 6 on
  farmer_6), 276 vertices, 1.88 m long along the model's y, every vertex
  weighted 1.0 on `root_joint` alone, 1.16 m to the right at hip height
  in the bind pose; their 89 bones have no hoe or prop bone, and no clip
  holds it (their own `hoe`, `idle_1` and `talk` keep the hands 0.66–1.72
  m off it, while `hoe` keeps the hands 0.14–0.22 m apart: a two-handed
  grip whose tie to the hoe the asset lost). The six `hoe` clips are
  identical; Europe's `characters.xbr` is byte-identical to the USA's;
  no level places a farmer, so no NPC binds one to copy. W20 skinned the
  group to `right_hand` in that grip (Step 2.106); since Step 2.134b W26
  carries it on one of the farmers' twelve free end joints (`joint19`,
  `joint10`, the ten finger ends `joint74` … `joint109`: no vertex, no
  clip key, no role, the same on all six), re-parented to `right_hand`
  and keyed along garret4's staff in every baked clip (Modkit's `PATCHES.md`
  W26). The farmers' 87 bones garret4 also has sit where his do within
  0.0007 units (joint81 the most), their bind turns 3.16° off his on the
  arms, which the bake re-poses: his clips baked onto farmer_1 put its
  right hand within 0.054° and 0.0000 units of his [verified static,
  Step 2.134b's design and critique]. garret4's staff is its own root chain:
  `staff_constraint` (b118, rest (3.067, 0, 0.55)) → `staff_center2slide`
  (b119) → `m_staffbottom` (b120) and `m_stafftop` (b121), 1.55 units
  apart, mesh group #7 (104 vertices), keyed in model space in every
  clip; against his right hand it turns up to 178.8° (attack_10), slides
  1.35–3.0 units and leaves the hand in smash_attack_1, attack_14,
  attack_15 and the casts; at idle's t 0 his `m_stafftop` sits at
  (0.074, 0.803, −0.032) in his right hand's frame, the right hand's mean
  grip over his 19 melee windows 0.442 of the way bottom to top [verified
  static, Step 2.134b's read]. No other wearable body holds a
  weapon-like prop: balthazar_airship's hand-skinned group #3 is his left
  arm (it ends 0.03 past the fingertip), the townswomen's vase and the
  water elemental's blob are props, not weapons.
- **A body written back whole** (Step 2.154, D443). Every body and its
  LODs' `bmsh` payloads follow one layout (the header, bone records,
  marker records, LOD pairs, names, the LOD list, then per LOD its records
  and push buffers; a push buffer one strip ended by a zero dword its
  Size counts), so `src/azurkit/tools/characters/body_codec.py` decodes a body whole
  and encodes it back byte for byte [verified 2026-10-22: all 158,
  `tests/test_model_write.py`], and writes one with new or removed
  vertices, triangles, groups and bones: a group past 31 palette bones,
  65,536 vertices or vanilla's largest push buffer (22,392 B) is split,
  and the payloads grow in place by whole pages
  (`docs/XBR_FORMAT.md` § "Graphics resources", § "Appending
  resources") [not yet seen in xemu].  Since Step 2.166a (D537) it adds
  a LOD as a new unnamed `bmsh`, named only by the body's relocated LOD
  list, writes one over a `bmsh` the body has, and drops LODs (the count
  falls, the old `bmsh` stays in the file unreferenced), and
  `src/azurkit/tools/characters/decimate.py` cuts a LOD from the one before it
  [not yet seen in xemu].  A new bone
  (`src/azurkit/tools/characters/skeleton.py`) goes after the last, so no clip
  track, palette entry or pose slot moves (they index bones; markers are
  their own table) and the pose reaches its parent first; its record is
  its parent's with parent, no compensation, RA and q the identity, JO
  its bind rotation in its parent's bind frame, t its bind origin there,
  S 1 and the inverse bind that bind's inverse, so at rest it skins as
  the identity and every clip, which keys none of it, holds it there
  [verified 2026-10-22: the export's checks pass on female_2 with one,
  `tests/test_model_write.py`; not yet seen in xemu].  A rename changes
  no index; only lookups by name (an fx bind, the swap's hand binds, a
  recipe) see it.
- **Which LOD a critter draws** (Step 2.166b, D537;
  `src/azurkit/tools/characters/lods.py`). `load_critters_config` reads a species'
  `critters_engine` `lodThreshold1`-`4` into its CritterData
  +0x110..+0x11C (0x49AD0-0x49B3E): a missing cell is FLT_MAX, the first
  at least 0, each later one at least the one before. The critter draw
  0x3EA00 culls past `farClip` (+0x30, 0x3EA1F; a missing cell is 0, the
  loader's default at 0x49999, so such a critter is never drawn); it aims
  for as many of
  the first min(LODs - 1, 4) thresholds as its distance (+0x184, stored by the
  critter draw at 0x3EA16: in xemu the camera's place to its centre plus
  0.11 m, sitting 2.166d) strictly passes in a row (0x3EE73-0x3EECB; the cvar "LOD
  on" off: 0), so LOD 5 and on are never drawn, and eases critter +0x284
  toward that target by
  2/fps a frame, clamped to [target - 1, target] going out
  (0x3EF93-0x3EFD5) and [target, target + 1] coming in (0x3EFDD-0x3F023):
  it snaps to within one LOD and fades the last over 0.5 s, drawing LODs
  k and k + 1 at a fractional value (0x3F3F4, 0x3F719), in xemu not an
  even cross-fade: mostly LOD k until its last third (sitting 2.166d: 7 % of
  LOD 1's difference from LOD 0 at 0.53, 84 % at 1, at most 69 of her 269
  px a frame); a recipe's LODs
  (W39, Step 2.166d) write garret4's four cells, of which the pick reads
  only the first LODs - 1. A species with a
  `shadowSize` above 0 (+0x94, 0x499EA; a missing cell 0) and no
  `shadowTextureName` (+0x9C -1, 0x49A8E) casts a realtime shadow drawn
  from its LOD 1 (LOD 0 for a one-LOD body): the critter constructor
  0x40380, the player's too (0x12463), makes a shadow (0x406C2-0x40886)
  that 0xC00F0 gives the -1 (+0x68) and the critter as a caster; while
  `render/shadows/realtime` is on (default 1, 0xFDAF6), 0xBF99F calls
  0xC57E0 and 0xC54E0, which draws each caster's vtable +0x58 with pass
  0x800 (0xC55B4; 0x3E830 in both critter vtables, 0x19FC08 and
  0x1A1B18); that pass calls 0xCC330 at LOD 1.0 (0x3E8B1), clamped to
  LODs - 1 and floored (0xCC351-0xCC3F9). A shadow that names a texture
  draws no mesh (0xC54F2). In vanilla only garret4 and noship (its body
  test/cind_e_ship doesn't decode) cast one. 2 of the 80 LOD1+ are never
  drawn (golem's LOD 3 past its 70 m `farClip`, female_0_base's unworn
  LOD 1: 106,600 B of `bmsh`, 110,592 B of own runs), fire_elemental's
  LODs 1-2 are drawn only in fades and garret4's LOD 1 only in his
  shadow (without it the shadow draws LOD 0: 6,625 triangles for 1,654)
  [verified static, Step 2.166b's census through `model inspect` and its
  review; the player slot's rule seen in xemu on booblord's shadow LOD,
  Step 2.166c's sitting (`382b074c1`): the shadow draws LOD 1, the
  screen LOD 0 at every distance; garret4's own LOD 1 not pictured].
  Every LOD is its own load run, loaded
  with the body, so a LOD adds to the load budget.
- **`banm` layout.** A 0x14-byte header: +0 the bone-track count, +4 a
  self-relative pointer to them (0x10: they follow the header), +8 the
  marker-track count, +0xC a pointer to theirs (after the bone tracks),
  +0x10 the clip's length in seconds.  A track is 0x14 bytes: +0 and +2
  its pre- and post-infinity modes (u16), +4 its key count, +8 a
  self-relative pointer to its 16-byte keys (f32 time, value,
  in-tangent, out-tangent), +0xC the target bone's or marker's index,
  +0x10 the component: a bone's 0–2 translation, 3–6 the rotation
  quaternion, 7–9 scale (Step 2.60); a marker's 10 length, 11 active
  (its twelve below).  Every vanilla clip is that header, its tracks and
  then their keys in track order: size = 0x14 + 0x14 × tracks + 16 ×
  keys for all 710, every track has 2 or more keys and modes (0, 0), no
  relocation points into one, and each starts on a page (Step 2.87:
  `azurkit.tools.characters.retarget.read_clip` / `write_clip`) [verified
  2026-10-15: every clip's bone indices fall inside its own body's
  bones; garret4's `idle` has 221 bone tracks on 83 of its 122 bones;
  the key counts, the modes and that no garret4 rotation key is a step
  key re-read for Step 2.87; the size rule, the pages and the
  relocations are the 2.78 bake research's].  A rotation track may key only
  some of q's four components: the pose takes the others from the
  posed body's rest q, so a clip's values mean something only against
  its own body's rests and joint frames.
- **garret4's clips baked onto another rig** (Steps 2.87-2.89; D226, D239).
  `src/azurkit/tools/characters/retarget.py` rewrites a garret4 clip for a body
  `retarget.MAPS` lists, at build time: the role map takes garret4's
  bones by name family on garret4's side of the body's bind pose (x
  sign), the body's bind re-poses so each mapped segment points along
  garret4's, and each mapped bone's rotation becomes A × (JO q RA along
  garret4's path from its mapped ancestor) × C with A and C constant.
  A Hermite curve is linear in its values and tangents and the pose
  normalises q, so where the path is one bone the baked keys are a
  constant 4×4 matrix on garret4's, split at the union of the
  components' key times, and exact; where the path folds an animated
  bone the body lacks it is sampled.  The model sits at the entity
  minus the clip's `m_feet` (0x42E40), so the root's translation keeps
  garret4's horizontal motion and scales his height over `m_feet` by
  the hip-height ratio, the thighs' bind height over his (the feet ride
  `m_feet` as his do; an elemental's `tail` root sits off its thighs'
  height, so the root's own height ratio falls 3-10% short of its
  legs'); his marker tracks are kept by name, those of `m_feet`,
  `m_grab` and `m_attacklevel` it lacks added to the body's marker
  table in place (the old
  records first, so their indices hold).  [verified 2026-10-15, the
  engine model: on balthazar_airship 67 of 135 bones map, and every
  baked clip moves each one from its re-posed bind within 0.02° of
  garret4's from his at 30 Hz; the segment directions of the arms, legs,
  spine and neck agree to 0.0°.  Step 2.88: keylord's 44 of 66 (overlord
  wears its rig), an elemental's 53, a townswoman's 66 of 93 and a
  child's 60 of 79, each within 0.08° (an elemental's foot in
  `step_up`, sampled where its chain folds garret4's animated
  `foot_1`).  Step 2.89: a townsman's 68 of 89, within 0.0001° (his
  own rig: no fold, hip ratio 1.0); a body with no clips maps no bone,
  so its baked clips are timers.  Step 2.88b: the townswomen's
  `vase_joint` is a second root at the model's origin; their own clips
  carry it on the head (0.125 m from `head` in every sample) at x0.4 on
  town_female_4 and at x0 on the others, and the water elemental's
  blob chain, another root, rides its left hand at x0 but mid-throw;
  a baked clip scales both to zero.  Step 2.134a (D355): the golem's
  rig (kingkong's body), 35 of 41 bones, hip ratio 1.208: its side sits
  mid-name (`arm_left_1`, `leg_right_2`, so the `left_`/`right_`
  families find nothing and an override names every bone), its torso
  is two bones (`torso_bottom`, `torso_top`) with no neck or head (the
  head left unmapped on purpose), its ankle `foot_X_1` and hand
  `hand_X_1` with four two-joint fingers, and its shins slant back, so
  the re-pose turns them 41.6° and the ankles 30.9°; the baked feet then
  depend on the pose (lowest mapped bone less `m_feet`: g4/idle −0.136,
  g4/jump −0.166 at its start and +0.017 at its end, the hoist's end
  −0.495, against its own idle's −0.004), so its baked root rises a
  constant 0.07 (`retarget.LIFTS`), which splits the cuts from its own
  idle into the jump and back (−0.10 / +0.09).  Its
  baked roll tucks its long arms 2.20 units under the floor (its ends a
  toe 0.08 and 0.19 under), so `retarget.floored` raises its root
  through that clip by what its lowest bone (any but a hidden prop's)
  is under the floor, keyed at 60 Hz from a 240 Hz need with monotone
  slopes (D420, AZ-629; `retarget.FLOORED`): the built roll's lowest
  bone 0.000 at 240 Hz in both modes and sizes, its root up to 2.2
  units higher mid-tuck and 0.08 / 0.19 at its ends.
  Since D421 a lender's clips bake the same way (`Retarget(lender=...)`,
  Balthazar's attacks onto a townsperson): each of the body's bones
  takes the lender's bone of the same garret4 role (both role maps; a
  child's 60 roles all on his, a townsman's 66 of 68, his one clavicle
  leaving its `*_shoulder_2` to follow its parent), the re-pose aiming
  each segment along his and his root's height scaled by the thighs'
  ratio to his; each mapped bone then turns from its re-posed bind
  within 1° of how his turns from his at 30 Hz.  Since Step 2.159a
  the lender's clips may be given in memory (`bake_body(given=...)`):
  the bare-hands kit's, read from a `.glb` onto its family's rig
  (`townspeople/male_6`, `female_1`, `child_1`) and baked onto each body
  of that family the same way.  In
  game: Modkit's `PATCHES.md` § "Player model swap", B.]
- **A damage marker's box** (Step 2.61) [verified 2026-10-15 from the
  data with the rule below and the damage pass's code (`RE_XBE.md` §
  "How the player's hit deals damage"): garret4's `attack_1` evaluates
  to X3's box, and balthazar_airship's `attack_3` to the 7.4 m beam
  tilted 24° down that sitting x224f's notes give].  A marker's twelve
  components (a track's +0x10) are its position 0–2, a rotation
  quaternion 3–6 (x, y, z, w), extents 7–9, length 10 and active 11.
  The box is centred at the position, its half extents are extents ×
  length, turned by the quaternion, in model space (x right, y forward,
  z up, the feet at 0), then × the critter's scale.  garret4's
  `attack_1` is on 0.25–0.33 s of its 0.667 s (ticks 5–6 of `basic1`'s
  13.3 at `Rate` 1.5) and spans y −0.29 to 2.76 m, z −0.13 to 1.26 m.  Of
  the usable bodies with their own damage clips, 15 have a clip whose
  box stays above 0.5 m, over sleeth's 0.53 m top (balthazar_airship's
  `attack_1` 1.23–1.77 m, keylord's two from 1.11 m, overlord's, the
  water and fire elementals', …).
- **How a track is read** (Step 2.21b) [verified 2026-10-12: a serve's
  decompile of 0xD8300 and 0xCAB80, and a Unicorn run of 0xCACD0 on
  garret4's `roll_forward`].  A track's +0 and +2 are its pre- and
  post-infinity modes (u16; 0 holds the first or last key's value, 1
  extends its tangent, 2–4 wrap t back into the keys' range
  [inferred: fmod-like calls]), and a key is (time, value,
  in-tangent, out-tangent).  `0xD8300` (ESI = the track; t and an
  `int *` key-index cache on the stack, RET 8; the value in ST0)
  evaluates a cubic Hermite between the keys around t, its tangents
  times the keys' spacing (a +inf out-tangent holds the key's value).
  `0xCAB80` finds a marker by name in the body (case-blind), starts from
  its defaults and lets the clip's tracks on components 0–2 (the
  translation) override them; a body without the marker gives zeros.
  `0xCACD0`, the root-motion sample (RE_MOVEMENT § "Roll, not run"
  item 7), is that at t1 minus that at t0.  Components 0–2 of `m_feet`
  are root motion: a clip that moves them on 0 or 1 travels
  (`azurkit.tools.characters.characters.moves_root`).
- **How a clip binds to a body** (Step 2.60) [verified static
  2026-10-15: a `ghidra-serve` copy's decompiles of 0x4B8E0, 0x4B600,
  0xA5CA0, 0xCAD40, 0xCB080, 0xCB730, 0xCBC80 and 0xCAB80; the bodies
  read with `azurkit.tools.characters.characters`].  By index, never by name:
  - A species slot (S+0x124 + 4 × index) holds an asset handle.  The
    base slots are resolved once when the species loads (0x4B8E0, its
    CALL of 0x4B600 at 0x4B948 with EAX the name and EDI the out),
    through 0xA5CA0, the global asset registry by name, which loads the
    asset's archive when it isn't yet; so any clip, another body's
    included, can be named by its full key (`characters/garret4/run`).
  - The clip change 0xCAD40 resolves the handle (`banm`), starts it on a
    layer, and calls 0xCB080 at 0xCAF6B (EAX = the anim object), which
    copies each bone track's +0xC into the new layer's table at +0x28
    and each marker track's into +0x34 (8 bytes per track: the index,
    then the key cache), unchanged: no name lookup and no check against
    the body's counts.
  - The pose passes 0xCB730 (bones: callers 0x40CE7, 0x43A51, 0x8CC85)
    and 0xCBC80 (markers: 0x4030B, 0x43A62) evaluate every track whose
    table index isn't −1 into a scratch array sized by the anim's own
    body (bone count body+0, marker count body+0x18) at index × 10
    (× 12 for markers) + component.  The marker sampler 0xCAB80 finds
    the marker by name in the body and then takes the clip's tracks
    whose raw +0xC equals that body index.
  - So another body's clip drives whichever bone or marker of this body
    has the same index, and an index past this body's count writes past
    its scratch slice: not playable as it is.  A remap of the two layer
    tables after 0xCB080 (and of 0xCAB80's marker index) by name would
    play it.  Of the usable bodies only the townspeople's 29 share
    garret4's rig: 74–87
    of their 79–93 bones carry garret4's names, the 22 core bones (root,
    hips, legs, spine, neck, head, shoulders, arms, hands) sit within
    3.1° of garret4's bind rotations, and the men's (`male_*`,
    `male_farmer_*`) 87 shared bones sit within 0.6 mm of garret4's bind
    positions (the women's within 0.15 m; the children's within 0.58 m,
    their `root_joint` at 0.73 m against 1.15 m).
    Every other body differs in the core (balthazar's `spine_1` and
    `*_arm_1` by 166–180°, keylord's legs by 147–169°), and of them only
    garret4's has any climb, hang, hoist, swim, landing or victory clip.
  - Step 2.67 [verified 2026-10-15: capstone, L2 on a town_male_6 build,
    and `characters.xbr` read with `azurkit.tools.characters.characters`]:
    0xCB080 (EAX = the anim, a plain RET) binds nothing when the active
    layer's flags (+8) are 0, sizes the tables through 0xCD4F0 (ECX the
    vector, EDX the count, the −1 fill pushed, RET 4); the tables are
    vectors (+0x28 begin, +0x2C end). By the 22 core bones within 15°
    the townspeople family is 34 bodies (the 29 usable and five
    `*_0_base` rigs); the men keep 87 of garret4's 122 bones by name, the
    women 84, the children 74; `townspeople/male_6` and `male_0_base`
    have one marker, `m_feet`, the rest none. No garret4 clip shares its
    bone-track count, marker-track count and length with another body's
    clip, so those tell a borrowed clip at run time. Of the garret4 clips
    a townsman borrows only `jump` moves `m_feet` (in z). The
    player-model swap's X12 (Modkit's `PATCHES.md`) did the remap until Step
    2.89 (D239), which bakes garret4's clips onto the townsmen's rig
    instead (B, `src/azurkit/tools/characters/retarget.py`; hip ratio 1.0, 68 of
    their 89 bones mapped), and onto a body with no clips as timers (no
    bone track, his length and markers).
  - Step 2.67's fixes [verified 2026-10-15: capstone on 0xCAD40 and
    0xCB730, L2 on keylord and town_child_1 builds]: 0xCAD40 with flag
    4 clear first looks for a layer already holding the clip
    (0xCAE20); one that is playing or fading becomes active again with
    flags `(the change's & ~0x10) | 9`, rate 1.0 (0xCAEA7) and its time
    going on, and the change returns at 0xCAF70 without 0xCB080, its
    tables as they were (a free one is bound afresh). anim_change
    (0x42910) passes its flags through, so a flags-2 change (the fall
    0x12 at 0x887A8, `swim_2` at 0x8BC26) to a slot holding the clip
    already playing takes that path. The bone pose pass 0xCB730 (its
    argument the anim, EBP the layer) evaluates each bound track at
    0xCBA75 (0xD8300: ESI the track, the time and the track's key cursor
    pushed, RET 8, the value in ST0) and stores it at
    scratch[10 × bone + component] (0xCBA8F), components 0-2 the
    translation, seeded per bone from the body's bind (+0x30); a
    root's translation is in model space, so garret4's `root_joint` z
    is his hips' height (`idle` 1.11 m, `die` down to 0.12 m,
    `swim_idle` 1.53-1.59 m), which puts the feet of a rig with other
    hips above or below the ground. The women's root sits at 0.96 of his, the children's
    at 0.64.
- **A hit needs a damage marker.** critter_init caches the body's
  `m_damage` / `m_damage2` at critter+0x218 / +0x21C (0xCA2B0, by
  name); the per-critter damage pass (0x43A80) builds a hit box from
  one only while its active value is at least 0.5 and its length above
  0, which only an attack clip's marker tracks switch on.  37 of the
  158 bodies have `m_damage`, and 33 a clip that switches it on; flicken
  has only `m_feet`, so a flicken player never hits.  Only the damage
  pass reads critter+0x218 / +0x21C (critter_init writes them), and it
  reads a marker's +0x04..+0x30 only: position, rotation quaternion,
  extents, length, active (0xCA390); the pose update resets only the
  markers in the model's own array.  So a marker outside the model
  keeps what is written to it: the player-model swap's X3 shim (Step
  2.21c, Modkit's `PATCHES.md`) gives a body whose clips switch no damage
  marker on such a marker of garret4's `attack_1` box (position (0.1625,
  1.2341, 0.564), extents (0.2412, 3.0497, 1.3889), length 0.5) [verified
  2026-10-12: Ghidra serve, capstone, and the shim run under Unicorn].
- **`attacks_anims` is the player's alone.** The PlayerControl ctor
  loads it (0x84E95), once per boot (the flag at 0x1AAB7E); no other
  caller is reachable, so a swap's `Anim` edits move only the player.
- **The staff.** Its blades are fx, not the body: 60 `fx.xbr`
  `transform` records, two in each of 30 graphs (the 28
  `fx/magic/fx_staff_*` and `fx_shield_electric2`/`3`), are bound by
  name to `m_stafftop` / `m_staffbottom` (a bind name is the (length,
  pointer) at record +0x20 when +0x1C isn't 0; attributes 7-9 are the
  scale).  garret4 has those bones, and the bind overwrites each
  transform's translation, rotation and scale every frame (0x68DE0);
  any other body leaves them at garret4's bind pose, about 3 units to
  the player's side, upright.  With no power on the staff wears
  `fx/magic/fx_staff_normal1`, the Axion's own head: a blade under each
  end and, under group transforms at scale 0 that the graph's
  `fx_magic_timer` scales up (its 0-1 s intro), six spikes and a brace,
  and four extra blades (24 meshes; the graph also holds
  `StaffUpgrade1_latch` and `StaffUpgrade2_latch`, [inferred from their
  names] the staff upgrades showing them; read from the graph, Step
  2.206b: on garret4's hoe it drew as a stray dark spiky piece, AZ-782; hidden there, the piece is gone
  [verified in xemu, Step 2.206b's sitting and record]).  Scaling those 60 to 0.001 hides them on
  every body but garret4's [verified in xemu, sitting swapb,
  2026-10-12: no floating staff on keylord or flicken; the elemental
  staffs' `pEmitter` particles were not exercised].  Those particles
  are children of the two transforms, so they stayed 3 m to the side
  (the owner's X.29 play of Balthazar, Step 2.24f).  A name the body
  has binds: the target's slot 1 (0x44270) finds it through 0xCA1D0 as
  a named node (i | 0x8000) or a bone (i | 0x4000), and each frame
  0x62C40 calls slot 2 (0x44370, `thiscall(index, &xf)`, RET 8) and
  then 0x68DE0 (EDI = xf, ESI = the fx transform).  For a named node
  0xCCDF0 fills only the xf's local quaternion (+0x40), translation
  (+0x50) and scale (+0x5C), from the runtime marker's (anim+0xC, 0x34 bytes each) quaternion
  (+0x10), position (+0x04) and extents (+0x20); for a bone it also copies the bone's
  runtime matrix (its record +0x70) into xf +0x00..+0x3F and sets
  +0x69, and 0x68DE0 then hands that matrix to the transform (0x68FA0:
  its +0x70, inherit mode 6), so a bone-bound transform follows the
  bone in the model, not its local offset.  The swap's W6 binds the two
  ends to the body's hand bones and shrinks the meshes under them
  instead [verified in xemu, sitting x224f, 2026-10-15: Balthazar's
  `left_w` and `right_w` matrices at (0.42, 0.24, 1.05) and (−0.39,
  0.17, 1.04) m while idle; their local T read (0.32, 0, 0) and
  (0, 0, 0)].  A named node's extents scale the transform about its
  own scale pivot (the record's +0x2C, which 0x68DE0 never writes: it
  writes T, R and S only), its local matrix T(t + rp) R T(sp - rp) S
  T(-sp) (`nodes.local_matrix`), so with no turn its origin sits at
  t + (1 - S) sp and moves, with every child, as S grows: beamlord's air blast keys its aim [12] (`m_balth_lightning`) to
  extents 26.6-243.5, and at 179 the aim's world matrix (record +0x30)
  and the floor dome's under it sat 27.7 m out from his centre and
  48.2 m under his feet, its rows 179 long; with the xf's scale written
  1 at 0x68DE0 (ESI the aim) both sat at his feet and the dome drew
  round them [verified in xemu, Step 2.153b's record R4, 2026-10-22:
  the dome platform's render object at its draw 0x79760 (ECX the
  object, [esp+4] the category; its world matrix at +0x170), collected
  and drawn in four category passes either way]; the aim [12] of
  balthazar_airship's `fx_default` has sp = rp = (0.1551, 0.0154,
  0.2709) units, so at S 179 the shift (1 - S) sp is 27.74 out and 48.22
  down, R4's numbers [verified static 2026-10-22: Step 2.153c's design; the graph's other bound transforms have no pivot]
  (AZ-669). Since Step 2.153c the air blast keys the aim's translation
  over the blast to (E - 1) sp (`_player_variants.scale_pivot`), so its
  origin, and the dome's, stays at his feet as E grows [static: the
  clip's keys through `local_matrix`; not yet seen in xemu]. In the
  bolt phase (S 1, the aim turned R) the same pivot puts the bolt's
  emitter (I - R) rp, (0, -0.25, +0.23) units, off the hands' mean
  [static; not built].
- **The air armor's wings (Step 2.77).** They are fx too, not the
  body: `config.xbr` `magic` row A casts `fx/magic/fx_jump1/2/3`, whose
  `fx_jumpWings:Wing_timer` drives the six wing joints' rotate and scale
  and the enables of `sfx_flap`, `sfx_fly1` and `sfx_flyloop` (0.53 at
  timer time 1.8, 0 elsewhere). The timer is authored with start 1.8,
  stop 10.333, rate 2, current 1.0 and no repeat; its update (0x6BAD0)
  sets current := start while its reset is nonzero, else adds dt × rate
  and holds at stop. Its only inputs are the transform `m_jump`
  (record 17 in `fx_jump2`/`3`, 19 in `fx_jump1`; no children, authored
  translate (2, −4, 0)), bound by name to the body marker `m_jump`: its
  translate X sets the timer's start and stop through step curves
  (X < 0.5: 1.0 to 1.0; 0.5–1.5: 1.0 to 1.333; ≥ 1.5: 1.8 to 10.333),
  and its translate Z (× 0.01) the reset of `Wing_timer` and
  `Rumble_timer`. Only garret4's body has the marker (index 15, default
  T (0, −4, 0); none of the other 157 bodies, by exact or case-blind
  name). Its `superjump` (anim 17, 8.733 s, which `wing_flap` asks for
  each flap at 0x89412) keys X = 2 and Z 5 at 0 s falling to 0 by
  0.033 s, so each flap restarts the stroke at 1.8; `jump` and
  `jump_standing` key X = 1 (wings folded), `fall_big` Z = 1. On any
  other body the bind finds nothing (0x62A20 drops a 0 from slot 1),
  the transform keeps (2, −4, 0), and the timer runs once from 1.0
  after the cast and holds its 10.333 pose, wings out (shoulder scale
  0.45 against 0.4 at 1.0) [verified static, 2026-10-15: the fx graphs
  and clips read from `iso/usa.iso`; Hermite evaluation of the wing
  curves]. The swap's X16 gives the player a virtual `m_jump` that
  pulses on each flap (`docs/RE_XBE.md` § "The fx bind interface and
  the air armor's wings") [not yet seen in xemu].
- **Where an armor sits on another body (Step 2.77b).** The armors'
  graphs (`fx_jump1`-`3`, `fx_light1`-`3`, the four shields' 1-3) hang
  every piece from a transform bound to a node of garret4's body:
  `m_skull` (his bone, authored at (0, 0.05, 1.867), its bind pose),
  `m_chest` (0, −0.033, 1.5), `m_root` (0, 0.05, 1.15), `m_waist`, the
  shoulders, wrists and ankles; his markers all rest at (0, 0, 0) with
  extents 1, so his clips place them. All 99 sit under the graph's root
  (`effectOrigin`, which binds nothing and stays the identity) at
  inherit mode 0 with no pivots. Of the 719 transforms below them 686
  inherit at mode 0, 27 billboards at mode 3 (0x6880A: the camera's
  rotation at the parent's x-axis length, so its scale) and 6 at mode 1
  (0x682A2: only the translation that carries the anchor `t + rp`,
  dropping the parent's scale): the force shield's `ForceField` and the
  electric shield's `Zaps`, children of the `m_root` transforms
  [verified static, 2026-10-15]. A body without the node leaves the
  transform at its authored point in the player's model, which the
  critter's scale scales, so the pieces stand at garret4's height on
  any body [verified xemu, sitting 2.75a, 2026-10-15: the air shield's
  wing skeleton well above keylord at × 2, 0.99 units tall, and above
  flicken, 0.68; on Balthazar, 2.11, the wings spread on his back]. The
  swap's W15 scales each such transform's translate and scale, and those
  mode-1 children's scale, by the body's height over garret4's
  (Modkit's `PATCHES.md`) [not yet seen in
  xemu].

### Not every `.xbr` cell is referenced

See [`RE_MOVEMENT.md`](RE_MOVEMENT.md) § "`CritterData.walkSpeed` and
`runSpeed` are live, not dead data" (the columns turned out live; the
player-side "looks live, does nothing" cell is garret4 `hitPoints`, see
§ "Player HP comes from settings_foo").
More broadly: `.xbr` tables often have historical columns from
editor workflows that the shipped engine ignores.  ALWAYS trace the
populating function before trusting a column.

### Zero bytes in `config.xbr` are not free padding (xemu, 2026-10-09)

xemu session 1's `mods5` build wrote a 16-byte marker into a run of
zero bytes at `config.xbr` file offset 0x15F80, rewrote its
`filelist.txt` line, and the game then sat on "Loading..." for over
40 s with looping HDD reads and no DVD reads
[xemu session 1, 2026-10-09].  Session 2 showed a real same-size value edit loads in
about 8 s, so the marker, not the re-copy, caused the stall
[inferred].

The zeros were empty cells: 0x15F80 is inside `critters_critter_data`'s
cell grid, the pad word of `town_female_sleep`'s `drop1` cell, so the
marker also overwrote the type code of the next cell, `dropCount1`
[verified 2026-10-10: offsets and config.xbr's own table, column and
row names, read with `config.keyed_tables`].  An empty cell still
carries a type code, 0; [inferred] the loader met a code that is none
of 0, 1 or 2 and looped.  So write only a cell's 8-byte value, as
every config-mod writer does, never "unused" zeros.

### Damage records, levels, the attack multipliers, Auto and the value sets (Step 2.91a, 2026-10-17)

[verified static, unless marked: Step 2.91a's research
and its verify pass, capstone on the USA
`default.xbe` and the vanilla `config.xbr`.]

- **`damage` holds every damage source, 57 records**: the player's
  (`norm_1`–`norm_3`, the 9 staff spells × 3 levels, the electro shield's
  `shield_lightning_1`–`3`), the hazards (`kill`, `lava_1`–`3`, `drown`,
  `fire_wall`), 16 critter-only attacks (`blaze`, `golem`, `octo`,
  `tesla`, `sleeth`, …) and `norm_4` and `wind_4`, which only keylord's and
  air_elemental's `damageType` name (`wind_4`'s `Level` is 3, so a
  (type, level) lookup always finds `wind_3` first). A critter's
  `critters_damage` `damageType` names the record its attacks deal: 29
  entries use `norm_1` (garret4, `test` and `debug` among them).
  [data, untraced] water_tentacle1–3's `damageType`, `watr_2`, names no
  record.
- **The player's record** is the first with the (type, level) asked
  (0x46A30). The plain staff asks level `spow` + 1, 1–3 (RE_XBE.md's
  0x838E0 row); a spell, the lowest level among its elements, held to
  1–3 (0x83994–0x839A5). More records (`wind_5`) would load (the loader
  allocates and scans them all), but the player never asks above 3.
- **A hit carries one record** (0x460B0) with one `Type` fourcc (0x464D0),
  so a staff deals one type; magic's `Damage` cell keeps only its first 4
  characters. **Damage to a critter** = ceil(its `critters_damage` cell for
  the record × the move's `Damage multiplier`); the cell is absolute HP,
  not a multiplier: empty means the record's `Damage`, 0 immune, negative
  heals. **Fuel per hit** = ceil(the record's `Cost` × the move's `Fuel
  multiplier`), from each element of the spell. [computed] `norm_1` (10)
  deals 5 with basic1 (×0.5) and 25 with finish (×2.5).
- **How the cells are read** (Step 2.184) [verified static: `xbe dis`
  on USA]: the critter loader truncates each cell (default: the record's
  int `Damage`, record+0xC) through 0xF5A40 (0x4A569) into the species'
  int32 table, CritterData+0x8C, one slot per record; its only readers
  are the player's hit (0x84003, garret4's), the AI hit handler 0x38C60
  (0x38CD6: FILD the slot, FMUL the hit's float multiplier, FSTP to
  float32, then ceil by FRNDINT and ADC; a result of 0 returns before
  any sound, knockback or `apply_damage`, so 0 is no hit at all) and
  the hit rumble (0x38F6D–0x38F8A; it runs for a hit whose source is
  the player's [inferred from 0x38F20]): 0x4BB40 is "slot < 0" and
  appends `_strength`, 0x4BB90 "slot > the record's `Damage`" and
  appends `_weakness` to `fx/damage/rumbles/fx_hit`, the game's own
  names for a heal and a weakness. A critter's table is copied with its
  species (0x4C425). The census (Step 2.184):
  over the 33 records the player deals and the 70 columns that aren't
  garret4's or a townsperson's (`critters_engine` `ai` `town`, each
  immune to all 33), 102 weakness cells (above `Damage`: 30/50/80 at
  levels 1–3, the tentacles' steam 399), 444 immune (0; 207 of them the
  electro shield's), 99 heals (about −`Damage`, the critter's own
  element: `_strength`),
  24 between 0 and `Damage` (Balthazar's and spideyzar's staff,
  guard_air's and the air bosses' EAFW, the tentacles' ice) and 1,641
  empty; no cell equals its record's `Damage`. The `enemy_damage` pack
  scales them (Modkit's `PATCHES.md`; seen in xemu by Step 2.184's
  sitting, there).
- **A hit on the player** (0x83FE0) ignores the move's multiplier. Its base
  is garret4's `critters_damage` cell for the record (default: its
  `Damage`). A type in the armor's `Weak vs` breaks the armor at once and
  isn't reduced; otherwise the armor absorbs round(base × `Normal
  protection`), at most `Normal protection hp` per hit, and a type in
  `Strong vs` uses `Strong protection` and `Strong protection hp` instead.
  `Strong vs` and `Weak vs` hold up to 2 space-separated codes each; a third
  fails the `vi < MAX_VS_COUNT` assert (0x3C905, 0x3CA24).
- **`attacks_anims`' empty cells** take the loader's defaults:
  `Damage multiplier` and `Fuel multiplier` 1.0, `Aim angle` 100000, "no
  aiming" (0x7E478, 0x7E4A4, 0x7F202). The table holds at most 31 moves
  (0x7E398); vanilla has 24.
- **magic `Auto` is one-shot.** Casting a spell sets the magic handler's
  +0x64 := (`Auto` ≠ 0) (0x83A06–0x83A30), which skips the drop back to the
  plain staff on empty fuel (0x83E5B) and the cast-on-release (0x83F39).
  [not re-derived] The next ground-attack start then fires one attack by
  itself (`attacks_transitions` rows 1–3, elemental_N → elementalN, no
  button) and the staff reverts to plain (0x83460). Only EAFW has `Auto`
  = 1.
- **The int32 cells:** fall damage 1–3, `damage`'s `Level`, `Damage` and
  `Cost` (0x46730), armor's `Level`, both `protection hp`, `Cost` and
  `Hits`, and critters' `hitPoints` and per-record cells go through 0xF5A40, which keeps the low
  32 bits of a 64-bit truncation: a value outside int32 wraps (AZ-513).
- **Settings no code reads:** the six `lev N obs` / `lev N hp` cells (no
  "lev " string and no "%d obs" format in the XBE) and the transitions'
  `search order` row. `max hp` is only the HUD bar's full scale; each
  power_life adds its `invAmount` (40) to max and current HP (0x435E7–
  0x4360E), so vanilla tops out at 200 + 5 × 40 = 400.
- **The value sets** a column accepts:

| Kind | Columns | Values |
|---|---|---|
| Feature lists (parser 0x50D80, 28 names) | `Features`, `realm`, `size`, `other features`, `f.fear` / `follow` / `attack` / `food`, `target features` | any number of words, ORed into a bitmask; an unknown name sets bit 0x80000000. The names are the (mask, name) pairs from 0x1A9E68 to a null name: none, all, tiny, small, normal, large, huge, obstacle, fixme, ride, good, light, player, critter, item, camera, death, life, earth, air, fire, water, waterwalker, dead, stunned, frozen, mutating, tasty (`schema.json`'s `value_sets`) |
| Damage type codes | `Strong vs`, `Weak vs` (2 each), magic `Damage` (a type at levels 1–3) | the 4-letter codes |
| Damage record names (57) | `damageType`, transitions' `damage type`, armor_hit_fx's `damage type` | `damage`'s records |
| Names from another table | `drop1`–`5` (pickups), armor_hit_fx's `armor type`, magic `Armor`, transitions' `last move` / `next move` | that table's names |
| Small fixed sets | magic `Type` (staff, armor), `button` (1/2/3/any), `target direction` (6 + any), `touch` (light, heavy), `near cliff` / `long range` (any, 0, 1), `ai` (20), `invType` (58) | as listed |
| Yes/no | `Auto`, `noFreeze`, `hitsThroughWalls` | 0 or 1: each is kept as (value ≠ 0.0) with 0.0 the default an empty cell reads (`noFreeze` 0x49E9A → critter+0x7B, `hitsThroughWalls` 0x49EE2 → +0x7C, `Auto` 0x83A06 → the handler's +0x64), so any nonzero is yes |

### What scales an enemy: health, damage, attack speed, movement, size (Step 2.205, 2026-10-27)

[verified static 2026-10-27: capstone (`xbe dis|fn|calls|find-refs`) and
decompiles from a `ghidra-serve` copy (port 8207), USA; the cell counts
from vanilla `config.xbr`;
what the sitting saw in game is the last bullet.] The `enemy_scaling` pack's ten
sliders (Modkit's `PATCHES.md`) write these cells and hook these reads;
"enemies" are the `critters_engine` columns whose `ai` isn't `player`,
`town` or `item`, less `debug` (unplaced; the throw kit's projectile,
W30), and the bosses below take their own five (D817).

- **The AIs.** The species load (0x36750-0x36886) binds each `ai` name
  to a factory: `walk`, `overlord` and `test` 0x3A460; `flocking`
  0x35240; `herd` 0x36560; `splinter` 0x37270; `town` 0x3B5A0; the
  bosses their own (`airboss` 0x258D0, `airbossclone` 0x25A80,
  `earthboss` 0x27D70, `fireboss1-3` 0x29980/0x29B30/0x29CE0, `waterboss`
  0x2DE20, `watertentacle1-3` 0x2DFD0/0x2E180/0x2E330, `balthazar`
  0x27130, `spideyzar` 0x2B640); `jellyfish` names none. The walking
  state machine 0x39020 (`__fastcall`, the AI in ECX; its state AI+0xB4)
  is shared: the bosses' state machines (0x25C50, 0x27530, 0x28420,
  0x2A290, 0x2BC10, 0x2E5B0, 0x2F510), the flock's 0x34FA0 and the herd's
  0x36140 call it.
- **What a boss is** (Step 2.205's BUILD 2, D817): the game reads three things as a boss. Its `ai`
  (above): 12 names each bound to a factory of its own, one boss's
  (guard_air, guard_air_clone, guard_earth, guard_fire1-3, guard_water,
  water_tentacle1-3, balthazar, spideyzar; every other enemy AI is
  shared); its body's folder, `characters/bosses/` (the guardians, the
  tentacles and `boulder`, the earth guardian's thrown rock; the XBE's
  own paths `characters/bosses/<guardian>/fx/...`, 0x1A0894-0x1A0E18);
  and the names a boss AI spawns by, `rock_shard_boss` (0x1A0BC8, read
  at 0x28D1F in the earth guardian's AI) and `air_elemental_boss`
  (0x1A0DA8, at 0x26953 in the air guardian's): 15 critters,
  `enemy_scaling.BOSSES`. Balthazar's and spideyzar's bodies
  (`balthazar_airship`, `balthazar_spider`) aren't in the folder; their
  AIs are bosses'. The species record's +0 is its `critters_engine`
  `name` cell (row 0, the species load's first read, stored at 0x496E1),
  equal to its column name for all 184, so a shim tells a boss by that
  name.
- **Health: `critters_damage` `hitPoints`.** The loader truncates it
  (0xF5A40; empty 0.0, the double at 0x195790) into the species' +0x14
  (0x4A4D9); critter init (0x409C0) gives a spawn passing a negative HP
  that, current and max (0x409EE, 0x40A0A), and every critterGenerator
  passes −1 (0x6F9A3), bosses included (spideyzar 3000, Balthazar 1000;
  `RE_MOVEMENT.md` § "Player HP"). `apply_damage` kills only on a fall
  from above 0 to 0 or less, so a critter spawned with 0 HP (the birds
  and fish, vanilla) no hit kills [inferred from its doc]. Thresholds
  the AIs read as a share of max (spideyzar's 2/3 and 1/3) follow it;
  spideyzar's "below 161 HP" attack entry is absolute; the fire guards
  (5 HP) lose one per hit at 0x2ACBF [inferred]. The builder 0x45C10's
  other nine callers (a boss's clones) are untraced.
- **Damage to the player: garret4's `critters_damage` column.** A hit
  on the player is the player's hit handler (0x8D600) → 0x83FE0, whose
  base is the player's species' (garret4's, D112) cell for the hit's
  damage record (CritterData+0x8C, 0x84003; empty: the record's
  `Damage`), before the armor's share; the move's multiplier is ignored
  (§ "Damage records" above). A critter's hit carries its `damageType`
  record, or one its AI sets (spideyzar's table's `norm_1`-`norm_3`,
  `wind_3`…, critter+0x220 through 0x469B0). BUILD 1 scaled garret4's
  cell for every record but the hazards' (`kill`, `lava_1`-`lava_3`,
  `drown`, `fire_wall`), 48 cells, all empty in vanilla but the electro
  shield's three 0s (immune, kept); the pack now hooks 0x8D648 instead
  (below). No enemy
  damages the player through another path: `apply_damage`'s 14 callers
  are the player's handler (0x8D6AF), the zipline's and fall's (0x8AD9B,
  0x8BF59, hazards), the cheats (0x16AC6) and the AIs' own HP.
  The records are shared: `norm_1` is the `damageType` of guard_earth,
  guard_fire1-3 and guard_water and of 23 other enemies, so no
  `config.xbr` cell scales one boss's hits and not an enemy's (D817's
  BUILD 2 moved both damage sliders to a shim). **Who deals a hit** is
  the game's own answer at the player's handler: 0x8D600 calls 0x83FE0
  (armor_mgr, the record; stdcall 8) at 0x8D648 (Europe 0x8D5F8) with
  EBX the hit message (+4 its source) and ESI the PlayerControl; the
  source's vtable +0x74 gives its critter (0x11D20, `mov eax, ecx`, on a
  critter; 0x606A0, `xor eax, eax`, on a platform), as 0x4327E asks.
  0x83FE0's base is the player's species' slot for the record
  (`[[[armor+4] - 0x150 + 0x178] + 0x8C]`, index = (record − [0x38C364])
  / 0x20 inside the array, else −1: a record outside it reads the int
  before the table, 0x84044); a slot of 0 or less returns it at once
  (0x84059 → 0x842C8: 0 no hit, below 0 a heal). **Damage platforms**
  name no critter, so only their record tells whose they are: the census
  of every damage platform on the disc (each `platform` with a `damage` level or a link into it, its type
  fourcc at record +0x44, in every XBR) finds, in `characters.xbr`,
  spideyzar's (`norm`, linked) and Balthazar's (`norm` 2, linked) own
  effects, the fire guardian's and spideyzar's `fx_firewall` (`fire` 1:
  `fire_1`), the water guardian's `fx_geyser` (`watr` 2: `water_2`), the
  boulder's `fx_boulder_break` (`rosh` 1: `rock_shard`) and the tesla
  tree's field (`tela` 1: `tesla`), the only enemy's; the levels' (lava,
  `kill`, the `wall` fire walls: `fire_wall`, acid, lightning, smash,
  wind, fire 3, e5's `octo`, d2's `watr` 3 and `heal`) are traps
  [inferred: placed level geometry, not a critter's attack], but for
  a5's one linked `norm` platform and town's linked `fire` (from level
  0), which, if their links raise them to `norm_1`-`3` or `fire_1`, read
  as the bosses' records do [not traced].
- **Attack speed: `critters_walking` `attack anim rate`.** The walking
  record is species+0xCC (0x3A845, 0x48 bytes); `attack anim rate` is
  its +0x34 (0x3AABE, empty 1.0) and has one reader: 0x39020's attack
  state (10) plays a random attack slot (0x2B-0x31) by `anim_change`
  and writes the cell into the active layer's rate (0x39E3F → 0x30940,
  EAX the AI). The state waits for the clip's end, then (state 0xB)
  flees by `flee after attack chance` or closes in again and swings as
  soon as it is in range (0x37F20, 0x38680 hold no cooldown), so the
  cell sets the swing and its recovery alike; the stalk and ambush times
  are the waits before a fight, not between swings. The AIs that call
  0x39020 attack through it. Balthazar's state machine plays its own
  table's clip and rate (0x2776C, the entry's +0xC) and spideyzar's his
  (§ "Spideyzar's speed" in `RE_XBE.md`): XBE data (AZ-777).
  **The bosses' attacks** (BUILD 2, `xbe insns` of the AI state writes):
  the boss state machines set their own attack states (0x1A-0x21 at
  AI+0xB4; only spideyzar's 0x2C2B0 sets the walking AI's state 10), so
  `attack anim rate` reaches spideyzar's walking-AI swings and the spawns
  only. Their attack clips are the base table's `attack`-`attack_6`
  (anim 0x2B-0x31: the guardians' `attack_1` and `attack_2`, 0x2C and
  0x2D, at 0x286F3, 0x28729, 0x2A485, 0x2A4DC, 0x2ED28, 0x2ED68; every
  entry of Balthazar's table at 0x1989E0, 0x18 bytes each: `norm_2` 0x2C,
  `smash_3` 0x2E, `norm_2` 0x2D, rate 1) and the species slots from 0x52
  on, past the base table's 0x52 names (spideyzar's table at 0x1987C0,
  0x28 bytes each: 0x2C, 0x2D, 0x54, 0x31, 0x2E, 0x2F, 0x30, `jump` 0x0F
  for his smash's take-off, 0x52, 0x53, and second clips 0x58, 0x56,
  0x55, 0x59, 0x57; the air guardian's 0x52 at 0x261E9 [inferred: an
  attack]). anim_change (0x42910) records the index at critter+0x200
  (0x4296C) and, when the species' slot for it isn't -1
  (species+0x124[index], 0x42980), starts it at rate 1 through
  anim_play_clip (0xCAD40, its CALL at 0x429DA, whose return the
  player-model swap's X12 reads, so the shim leaves it); both ways meet
  at 0x429F7 (`mov edx, [esp + 0x18]; mov ecx, [esp + 0x1C]`: the
  critter and the index), where the shim lands. The layer-rate setter
  0x30940 (EAX the AI, the rate pushed, RET 4) then writes Balthazar's
  and spideyzar's table rates and the walking AI's cell into the active
  layer, anim+0x60 + 0x40 × [anim+0x10]. One store skips it:
  spideyzar's message handler 0x2C790 (its one reference .rdata
  0x1A08DC) plays slot 0x59 (0x2C7CD) and stores his speed, AI+0x180,
  into the active layer (`fld` at 0x2C7E2, `fstp` at 0x2C7EB). So the
  boss slider's shim scales the rate at all three for a boss whose index
  is an attack clip's; the waits between a boss's attacks (spideyzar's
  0x1987C0 +0x1C/+0x20 ranges, the guardians' states' timers) are left,
  so a boss swings faster, no more often.
- **Movement: `critters_critter_data` `walkSpeed`, `runSpeed`;
  `critters_flocking`'s accelerations.** The loader keeps `walkSpeed`
  (empty 1.0) at species+0x38 and `runSpeed` (empty 0.0) at +0x40, and an
  empty `walkAnimSpeed`/`runAnimSpeed` takes the speed's value (0x49D85,
  0x49DDA; no enemy's is empty). A walker's move (0x37E40) takes
  `walkSpeed` for its walk (anim 8) and `runSpeed` for its run (9, 10)
  as its speed (AI+0x108) and plays the clip at speed ÷ (scale ×
  anim speed) (0x30D90), so the legs keep up; a `runSpeed` of 0 makes
  0x30250 hold the critter on its spot (0x30110). A flock or herd
  (0x346B0 every 1/6 s) clamps its steering to `max xy accel`, `max
  accel up` and `max accel down` (or `max brake down` while it falls;
  flocking +0x3C-+0x48, empty 0.0) and its speed to the species'
  `runSpeed` (0x34520); `initial velocity` (+0x58) is a spawn's. So the
  speeds and the accelerations together scale a walker's, a flyer's and
  a swimmer's pace; the turn rates (`max turn rate`) stay, so a fast
  enemy turns wider [inferred].
- **Size: `critters_engine` `scale`.** The species' +0x24 (empty 1.0,
  0x49913) is the critter's +0x188 (0x40608), which the game itself
  applies to the drawn model (0x42200 through 0xA3860), the collision
  radius (vtable +0x90: species +0x18 × +0x188, 0x11D00; the AI's world
  moves (0x30350) and the shape tests, `collisionAspectRatio` and
  `playerCollisionRadius` being ratios of it), the damage boxes
  (0x43B4C-0x43B8F), the shadow (0x40876), the attack range (0x256B0:
  max(+0x188, 1) × `attackRange`) and the walk cycle's rate (0x30D90).
  `boundRadius` (+0x2C) it doesn't scale everywhere: the bounds box of a
  critter without skeleton collision is its position ± the cell
  (0x41832) and one with it grows by the cell less the scaled radius
  (0x4170C), while the animation LOD reads +0x188 × it (0x43A00). So a
  bigger enemy is drawn, collides, takes hits and swings bigger, needs a
  wider way through the level (paths it fitted it may stop at), starts
  attacking from further (above × 1 only) and walks at the same speed
  with slower strides; a smaller one's attack range stays its × 1 range,
  so it may swing short of the player (the golem at 0.5 landed no hit in
  Step 2.205's sitting). The range's callers are the walking AI's chase
  and attack checks (0x393D9 attacks inside the range, 0x39B61 keeps on
  inside twice it, 0x39C51 hands it to the walker's move 0x37E40 as the
  distance to stop at) and the air guardian's (0x26182, into 0x26410),
  and the walking think 0x39020 is called by the bosses', the flocks',
  the herds', the townspeople's and the items' AIs, so `enemy_scaling`
  doesn't edit `attackRange` or the shared 1.0: its reach hook (AZ-788,
  Step 2.205c) runs 0x256B0 with the floor the critter's own size slider
  (a boss's, another enemy's, else 1). In xemu (Step 2.205c's record, a
  breakpoint on 0x256B0):
  e2's catalisk_baby reads it through all three walking callers
  (0x393D9, 0x39B61 and 0x39C51), while the fire
  guardian's fight read it 0 times in 600 ticks and the water
  guardian's 3 times in 900 (one critter, gone by the end, not the
  guardian), so neither guardian's attacks go through it.
  **D816 (the owner's "Look, hits and body")**, confirmed from these
  reads: the model, its hit boxes, its collision and (above 1) its
  attack reach follow the one cell, and the effects bound to it too
  (the bind interface's model matrix, 0x444E0, passes +0x188 to 0xA3860);
  below 1 the reach follows through the pack's reach hook (AZ-788).
  What doesn't follow: the walk speed (the
  strides slow), the effects a critter leaves detached (the boulder's
  break, a fire wall, a geyser keep their size) and a boss's scripted
  distances (its states' own constants) [inferred].
- **Seen in xemu** (Step 2.205's sitting and record, v0.16.4 offscreen
  deterministic, USA): each cell and hook does what the reads above say on f6's
  blaze sentinel, e7's golem and w3's water guardian (Modkit's `PATCHES.md`
  § `enemy_scaling`). Two things the reads didn't show: the tentacles'
  own AI sets their scale every tick (water_tentacle1 1.0 under boss
  size 0.5, 1 and 2, AZ-786: their think grows them to 1.0, and the fire
  guardians' heads for 2 − HP / max HP, `RE_XBE.md` § "The bosses that
  size themselves"; boss size scales both since Step 2.205b), though
  their HP follows `hitPoints` (200 / 400 / 800); and with its attack
  clips twice as fast the guardian started 7 attacks in 900 ticks
  against main's 5 (its waits stay, so the next comes round sooner).

## hourglass.xbr + fx.xbr — data-file scope + XBE hooks

Cross-referenced findings from opening the two data files in
Ghidra alongside ``default.xbe``.  Both are **DATA-only**
(Ghidra won't find functions in them directly), but each has
specific code paths in the XBE that reference their contents.

### hourglass.xbr — UI loading spinner, NOT a timing resource

Despite the suggestive name, ``hourglass.xbr`` is just **sprite
geometry for the UI hourglass icon** that appears during loading
screens.  37 KB total:

- 20 ``surf`` entries, 1,152 bytes each.  Each is one frame of
  the spinning hourglass animation.
- No timing / scheduler data.  The 60 FPS patch does not interact
  with this file.

Source-path leak at VA ``0x00198E93`` confirms the module
identity: ``C:\Elemental\src\mud\hourglass.cpp``.  The loader
path pushes ``"interface/hourglass/..."`` at VA ``0x000D0F08``
(inside ``FUN_000D0EE0``), which is the only in-XBE site that
references the data file.

**Takeaway**: nothing actionable for modding unless someone
wants to replace the loading spinner graphic.  No action taken.

### fx.xbr — Maya-exported particle-system effect library

36.5 MB visual-effects library.  3,572 TOC entries with 113
distinct effect graphs (each has matching ``node``, ``ndbg``,
``sprv``, ``gshd`` sections).  Built from Maya source files
visible in the blob as paths like
``c:\Elemental\gamedata\fx\damage\fx_acid_2.ma``.

Effect graph shape (from the string-table dump):

- **Named timers**: ``AcidHit_timer``, ``EarthHit_timer``,
  ``fx_magic_timer`` — per-effect countdown / max-value
  accumulators.
- **Particle-system nodes**: Maya standard names
  (``pEmitterTop``, ``pRendererShape``, ``pSystem``, ``pSink``,
  ``pAccelerator``) preserved in the runtime graph.
- **Lifecycle**: ``Unload_effectControl`` nodes for cleanup,
  ``effectOrigin`` / ``effectControl`` for graph roots.

Source-path leak at VA ``0x0019DE34`` confirms the module
identity: ``C:\Elemental\src\mud\effectGraph.cpp``.

**XBE hooks** into the effect system (found by grepping .text
for pushed string-VAs):

- **``FUN_00066830``** — "find effect node by name".  Takes a
  ``this`` pointer in EAX (!) and a name on the stack; returns
  the matching node or NULL.  Called from 3 sites referencing
  ``fx_magic_timer`` (VA ``0x19C1AC``).  Unusual ABI (EAX-this
  instead of ECX-this) — would need a gravity-style inline-asm
  wrapper to expose via ``vanilla_symbols.py``.  Not currently
  exposed — no shim has asked for effect playback yet.
- **``FUN_00083000``** — "update effect timer max" method.
  Reads the magic-timer node via ``FUN_00066830``, compares a
  float argument against the stored max, updates if greater +
  sets a dirty flag.  Called from a dispatch table (VTABLE-
  style) at VA ``0x19C174``.

**For 60 FPS investigations**: no frame-rate-dependent pattern
found in the callers examined.  The effect timers receive
``dt``-scaled floats from their callers (not raw frame counts),
so the 60 FPS patch's simulation cap should not break effect
timing.  If future testing reveals visual-effect speed drift at
60 FPS, re-examine the effect-update dispatcher at
``0x830E0..0x832A1`` for the specific ``dt`` multiplier.

**Takeaway**: effect-by-name lookup is a potential future
vanilla-symbol addition (wraps around the Maya-name graph for
shim authors who want to trigger specific effects).  Deferred
until a concrete shim needs it; the inline-asm wrapper cost
(à la gravity) isn't worth paying speculatively.

### fx.xbr wave codec — the full RE trail (April 2026, final)

``fx.xbr`` contains **700** ``wave`` TOC entries.  The April 2026
Ghidra walk pinned the complete pipeline and proved there's **no
custom codec** to reverse — Xbox DirectSound decodes everything
in hardware.

**Static call chain** (walked over Ghidra's xref graph; the direct
calls into each step reproduce offline with ``python -m devkit re xbe calls
--to <VA>``):

::

    symbolic name (fx/sound/...)               ← to a handle in EAX: not traced
        ↓
    load_asset_by_fourcc(0x65766177, 1)        @ VA 0x000A67A0
        ↓  called from
    FUN_000A20C0 (per-frame sound tick)        @ VA 0x000A20C0
        ↓  allocates sound object
    FUN_000AE030 (factory)                     @ VA 0x000AE030
        ↓  vtable slot [+0x34] → init method
    FUN_000AC6F0                               @ VA 0x000AC6F0
        ↓  delegates header parse
    FUN_000AC400                               @ VA 0x000AC400
        ↓  fills WAVEFORMATEX
    DSOUND::DirectSoundCreateBuffer
    DSOUND::IDirectSoundBuffer_SetBufferData(buf, wave_entry + 16, N)

**Engine-canonical 16-byte wave header** (as read by
``FUN_000AC400`` byte-for-byte):

::

    offset 0x00  u32  sample_rate       (22050 / 32000 / 44100 / …)
    offset 0x04  u32  sample_count      (0xAC6F0 sizes the buffer from
                                         it, below)
    offset 0x08  u8   channels          (1 or 2)
    offset 0x09  u8   bits_per_sample   (PCM: 8 or 16; XADPCM: 4)
    offset 0x0A  u8   streamed (1: entry is 20 B, u32 at 0x10 = TOC index of
                      the sdsr holding the codec payload; HM-83)
    offset 0x0B  u8   codec_id          (0 = PCM, 1 = Xbox ADPCM)
    offset 0x0C  u32  (unused — padding)
    offset 0x10  ...  codec payload fed to DirectSound

``FUN_000AC400`` returns 0 (rejection) for any entry with
``codec_id`` outside ``{0, 1}``; it checks no rate or channel count.
``FUN_000AC6F0`` checks that return value and silently aborts the
sound alloc on failure — the game NEVER attempts to decode those
bytes as audio.  It hands ``SetBufferData`` a length the header
makes, not the TOC size (0xAC7B2..0xAC7C4): Xbox ADPCM
``(sample_count >> 6) * ch * ch * 36`` bytes (``nBlockAlign`` =
``ch * 36``, 64 samples a block), PCM ``bits * ch * sample_count >> 3``.
A mono entry's count is 64 × its 36-byte blocks; a stereo one's holds
half its frames (32 × its 72-byte blocks), so the length is its
payload, a spare block past it on 5 of the 9 [verified 2026-10-21, Step
2.141's read: all 660 inline mono entries and the 9 stereo].

**Distribution** (vanilla ``fx.xbr``, TOC read as the engine reads it;
``python -m devkit audio dump``, a streamed entry read from its ``sdsr``)
[verified 2026-10-21, AZ-124, AZ-624]:

| Classification      | Count | Notes                                  |
|---------------------|------:|----------------------------------------|
| ``xbox-adpcm``      |   700 | 678 mono + 22 stereo; WAV wrapper works |
| ``pcm-raw``         |     0 | Code path exists; no entries use it    |
| ``likely-animation``|     0 | 4-byte TOC tags in first 64 bytes      |
| ``non-audio``       |     0 | Fails engine header check; not audio   |
| ``too-small``       |     0 | < 64 byte payload                      |

669 are inline (660 mono + 9 stereo) and 31 streamed (18 mono + 13
stereo: a 20-byte entry whose samples are an ``sdsr``'s, HM-83).
Rates: 22050 Hz × 472, 32000 × 110, 44100 × 60, 11025 × 32, 12000 ×
19, 8000 × 6 and 8192 × 1 (``fx/sound/ruby/ruby``, which the dump read
as non-audio until AZ-624).

**Correction (AZ-124, 2026-10-09).**  This section used to report
103 / 0 / 9 / 557 / 31 and call the 557 ``non-audio`` entries
leftover payloads the engine skips.  They were a misread TOC: every
reader took the rows at 0x40 instead of the engine's 0x3C, pairing
each entry's size with the next entry's offset, and used that offset
without the data-area base (``header[0x10]``), so most ``wave``
slices were the wrong bytes.  Read as the engine reads it
(``src/azurkit/core/xbr/nodes.py``), 2,219 of the ISO's 2,266 ``wave``
entries carry a header the parser accepts.

**Why the audio "decoder RE" problem evaporated**: Xbox
DirectSound handles ``WAVE_FORMAT_XBOX_ADPCM`` (0x0069) natively
in hardware.  ``FUN_000AC6F0`` just builds a ``WAVEFORMATEX``
from the 16-byte header and hands the raw payload at
``wave_entry + 16`` to ``IDirectSoundBuffer_SetBufferData``.  No
game-side codec exists to reverse.  Our ``audio dump`` tool's
RIFF/WAVE wrappers use the same format tag so ffmpeg / vgmstream
/ Audacity decode identically to what DirectSound plays.

**Ruled out during the investigation** (kept for reference; all
three ran on the misframed slices, so they say nothing about the
real payloads):

- Straight 16-bit / 8-bit PCM reinterpretation of the non-audio
  blobs: mean ``|Δ|`` between adjacent int16 samples ≈ 30 000
  (near-uniform-random).
- Headerless IMA / MS / Xbox ADPCM decode with either zero
  start-state or first-4-bytes-as-header: all produce noise.
- Non-standard block size (36 / 72 / 140 bytes) for the
  non-audio entries: 0 of 557 sizes divide cleanly.

**Takeaways**:

1. The ``--raw-previews`` CLI flag is kept as a generic
   "inspect any high-entropy binary blob in Audacity" helper but
   is NOT an audio-recovery path.  Most users can leave it off.
2. ``duplicate_of`` detection in the manifest still has value —
   surfaces 213 redundant entries in vanilla fx.xbr where the
   same bytes appear under multiple indices.
3. Engine-side vanilla symbols worth registering for future
   shim authoring: ``FUN_000AC400`` (header parser),
   ``FUN_000AC6F0`` (wave-init vtable slot), ``FUN_000AE030``
   (sound-object factory).  Not added yet — deferred until a
   concrete shim needs them.

### How a critter's sounds are chosen (Step 2.62, 2026-10-15)

[verified 2026-10-15: capstone (`python -m devkit re xbe dis|calls|find-refs`)
and a read-only `ghidra-serve` copy's decompiles on the vanilla USA
XBE; names and counts from the archives' named-resource tables and
`config.xbr`'s tables.]

**Play by name.** A sound name resolves to an asset handle through
0xA5CA0 (ECX = the name, stack `0, 2`; −1 when no asset has it), and
0xA1C70(0x1AA8E0, handle, 0, 3-D flag) makes the sound, which the
caller starts through its vtable (+0x30, +0x44).  The names are the
named waves of `fx.xbr` (574), `english.xbr` (234) and `interface.xbr`
(8); the lookup matches names whose case differs [inferred: every
`critters_sounds` cell of the Overlord, Bot, Golem, … spells a folder
in capitals that `fx.xbr` names in lower case].

**The species record** (`load_critters_config`, 0x49480, one per
`critters_engine` column): +0 name, +4 `body`, +8 `sound dir`.  From
`critters_sounds` (from 0x4A7E1; a column names its species) it takes
handles: +0xA0 `idle`, +0xA4 `attack`, +0xA8 `ouch`, +0xAC `foot_left`,
+0xB0 `foot_right`, +0x2F4 `ambient`, and at +0xB4 an array with one
handle per hit row (`norm_1` … `fire_wall`, 46 rows), plus
`soundMinDist` (+0x2EC), `soundMaxDist` (+0x2F0) and
`ambientCutoffDistance` (+0x2F8).  `soundMaxDist` is read from entity 1's
column (`push 1` at 0x4ABF0; air_elemental's, empty), so every species
gets the default 100.0 and guard_earth's 200.0 is never read.  An empty
role cell falls back to `fx/sound/%s/%s_%s` (0x19F750) with the sound
dir in both `%s`, a name no wave has.

**Who plays them.** 0x30AC0 plays `idle`, `attack` or `ouch` (+0xA0 +
4 × role) within the species' +0x30 of the listener; only AI code
calls it (0x27530 and 0x2BC10, vtable methods, and 0x39020).  The AI
walker 0x37F20 plays `foot_left`/`foot_right` at its walk phase.  The
damage pass plays the victim species' hit-row sound for the damage row
(0x841E1) and then its `ouch` (0x84246, when the victim critter's
+0x210 is positive); 0x38C60 does the same.  The critter method 0x43A80
(vtables 0x19FC00 and 0x1A1B10) loops `ambient`.  [inferred: the damage
pass and 0x43A80 run for the player's critter too.]

**Clip sounds.** 0x4B680 (stdcall `slot, clip`, EDI = the species
record) binds `<sound dir>/<clip>` and `<sound dir>/<clip>_a` …
`_s` (`%s/%s` at 0x19F28C, `%s/%s_%c` at 0x19F280: 20 names) to the
slot, in the species' map at +0x2E8.  It runs for the 82 base clips of
0x1A9F78 as slots 0–81 (0x4B93C, once per species, from 0x4B8E0), for
each `attacks_anims` `Anim` as slot 0x52 + column (0x7E3DD in
`load_attacks_anims_config`), for each `critters_special_anims` clip
(0x4B2AE) and for a clip a level names (0x4B840 from 0x6F410, which
splits a comma list; slots up to 0x70; it looks the clip up on the
species' body first, 0x4B600, and binds nothing when the body has no
clip of that name, −1 at 0x4B864).  `anim_change` (0x42910) and
`anim_change_at_node` (0x42750) pick one of the slot's sounds at random
(0x4B730) and play it (0x42A30, which stops the one before: critter
+0x208 holds the playing one, +0x20C the one before).  The binding
reads only the slot's name and the species' sound dir, never the
body, so a slot's sound plays even when the body has no clip there.
No `characters.xbr` clip carries a sound: its 11 waves belong to three
fx graphs' `soundEffect` nodes (fire_guardian's `fx_firewall`,
water_guardian's `fx_geyser`, obsidian's `fx_default`).

**The player (garret4).**  Its `sound dir` is
`loc/english/speech/azurik_speech` (30 waves in `english.xbr`); 26 match
a base clip (`touchdown`, `slide`, the `climb_*`, `hoist`,
`hoist_waist`, `hang`, `step_up`, `step_down`, `ouch_1`, `ouch_1r`,
`ouch_1l`, `ouch_1b`, `victory_1`–`_6`); `ouch_1t`, `wow`, `whoa` and
`this_must_be_important` match none.  `wow` is a token in 15 levels'
`levl` resources and no body has a clip of that name, so it isn't a
0x4B840 clip [inferred: a level's `soundEffect` node, scripted speech;
Step 2.141's judge].
Its `critters_sounds` role cells are empty and its hit rows name
`fx/sound/hits/flesh1`/`flesh2`.  Its attack shouts are the
`attacks_anims` `Sound` … `Sound 4` cells (`fx/sound/speech/attack_1` …;
21 of the 24 columns name one or more): `load_attacks_anims_config`
keeps up to four names per attack (attack record +0x2C count, +0x30
names; an empty cell reads as NULL and is skipped), and
`player_ground_attack_start` (0x88DD9) and `player_air_attack_start`
(0x88FED) play one at random.  The rest are paths in the XBE, each a
`mov ecx|edi, <string>` before 0xA5CA0:

| `fx/sound/…` | String | Site | Function |
|---|---|---|---|
| `player/walkl`, `walkr` | 0x19BFFC, 0x19BFE4 | 0x8656D, 0x865C8 (and `walkl` at 0x8B002) | `player_walk_state` 0x85F50 (0x8AE10) |
| `player/walkl_water`, `walkr_water` | 0x19BFC8, 0x19BFAC | 0x86665, 0x8666C | `player_walk_state` |
| `player/jump` | 0x19BF34 | 0x892AD, 0x89466 | `player_jump_init` 0x89060, `wing_flap` 0x89300 |
| `player/flap` | 0x19BF1C | 0x896FD | the airborne tick's cheat fly boost (`RE_XBE.md`) |
| `player/landing` | 0x19BE30 | 0x8B0DB, 0x8B195 | 0x8AE10, 0x8B100 |
| `player/ouch` | 0x19BE48 | 0x8ADC2 | `fall_damage_dispatch` 0x8AB70 |
| `player/fallingdeath` | 0x19BD70 | 0x8BF61 | `fall_death_dispatch` 0x8BE00 |
| `player/climbr`, `climbl`, `climbu`, `climbd` | 0x19BF94, 0x19BF7C, 0x19BF64, 0x19BF4C | 0x882EB, 0x882FD, 0x88323, 0x88335 | `player_climb_tick` 0x87F80 |
| `player/swim2_start`, `swim2`, `misc/splash` | 0x19BDFC, 0x19BDE4, 0x19BDA0 | 0x8BC14, 0x8BC84, 0x8BD03 | `player_swim_tick` 0x8B700 |
| `player/swim_ambient` | 0x19BD48 | 0x8C470 | 0x8C450 (a loop kept at PlayerControl +0x170) |
| `hits/clank1` | 0x19BCE4 | 0x8CC99 | the staff-wall check 0x8C8A0 |

Each caller skips the sound when 0xA5CA0 finds no wave of the name:
`cmp eax, -1` after the CALL at 0x8ADCC (`ouch`) and 0x8B19F
(`landing`), and 0x8D4E0's at 0x8D4EC for 0x8BF61 (`fallingdeath`) and
0x8B0DB (`landing`) [verified 2026-10-21, Step 2.141's read:
`python -m devkit re xbe dis`]; a variant's silent voice points the first two at
names no wave has.
No XBE string names `fx/sound/player/` `funk`, `gethit1`–`3`,
`stepup`, `stepdown`, `vaultup` or `vaultdown`.  A level's
`soundEffect` node whose name starts with `loc/english/speech/`
(0x19DB30) plays at 1.2 instead of 1.0 (0x6B3B6).

**The language.**  0xA5CA0 finds a name through 0xA5B10 (Europe
0xA5E20 through 0xA5C90), which lower-cases it and, while the language
global [0x1BF598] (Europe [0x1C1538]) is set, looks a name that starts
with `loc/english/` (0x19AE80) up first as `loc/<language>/<the rest>`
(`loc/%s/%s`, 0x19AE74) and, when no resource has that name, as written
[verified 2026-10-22, Step 2.159a: `python -m devkit re xbe dis` 0xA5B57-0xA5BFE,
Europe 0xA5CD7-0xA5D6C]. Europe's `French.xbr` and `German.xbr` hold
`loc/french/...` and `loc/german/...` (330 and 328 named resources,
`english.xbr` 359), so a townsperson's speech (`loc/english/speech/<dir>`
in `critters_engine`) plays in the language, and a wave a build adds
only under `loc/english/speech/<dir>/` (X14's `t_whoosh`, Step 2.159a)
plays from its English key [not seen in game under French or German:
the EEPROM that sets the language is in every save state, the fork's
`hw/xbox/smbus_storage.c` keeping its bytes, so a sandbox's `vanilla-ig-*`
load brings the English one back].

**The model swap.**  Under mechanism B the player stays garret4, so
every slot binds garret4's sound dir: without help a swapped body speaks
Garret's lines and attack shouts, and none of its species' sounds play;
on 13 species W3 gives attack columns the clip `ouch_1`, so those attacks
also played Garret's `ouch_1` line (AZ-392).  Since Step 2.72
`--player-character-sounds own` (the default, D231) binds the species'
own per role through X14, empties the shouts it replaces and gives
garret4's `critters_sounds` the species' `ouch`, `ambient` and hit rows
(W9-W11), and repoints the jump and step paths above where the species
has those waves (X15); Modkit's `PATCHES.md` § "Player model swap".  Not yet
seen in game.  Since Step 2.141 (D328) a roll with no sound of its own
takes its first attack column's, so its grunt (`attack_9`) gives way too.
A variant (Step 2.141, D386) binds from its own dir, `fx/sound/v/<variant>`
in `fx.xbr` (no vanilla key starts so), sounds the build makes and
appends with their `index.xbr` records; booblord's voice is silent but
for the owner's WAVs (her hurt, roll, jump, long fall, climb and
finishers; Step 2.144) and her effects Garret's (Modkit's `PATCHES.md` §
"Variants").  Seen in xemu at volume 0 (sittings 2.141 and 2.144, from
the game's sound calls): her bound slots, the fall's ouch and the jump
play her dir's waves, a slot or path with no wave of hers plays
nothing, and the wing flap and her effects play Garret's.

**Rolls and the sounds no player role binds (D328, Step 2.141).**
[verified 2026-10-21 on both releases' archives and config.xbr, which
agree.]  Of the 177 usable species (a body in
`characters.xbr`, garret4 aside), 12 roll with a sound of their own,
the wave named as the roll's clip: channeler's and shard's are attack
sounds, and boulder's (run), fire_bot's (idle) and golem's, kingkong's,
ice_shard's, lava_shard's, overlord and golem's and the three rock
shards' (walk) are not, kept as D328's wording reads (the owner may
place others).  48 have attack sounds and no roll sound, so they now
roll with their first attack column's (balthazar, keylord and
spideyzar `attack_1`, guard_air `attack_arc`, town_female_3 `talk_b`, …);
the other 117 have neither (flicken's attacks bind none, AZ-392) and keep
Garret's roll shout.  The species' sound dirs hold 102 names in 35 dirs
that no player role binds: 45 a clip slot of the NPC binds, 8 a
`critters_sounds` cell, 13 one of those for some of the species that
list them and neither for the rest, and 36 neither.
Of those 36, 26 are named nowhere in the game's 46 files (no key, no
token), the sounds the game never plays, for the owner to place (TOC
entry bytes; 20 B is a streamed entry, its samples in an `sdsr`):

| Dir (`fx/sound/…`) | Never named |
|---|---|
| `air_elemental` | `air_elemental_attack_1` 32848, `_attack_2` 33352, `_attack_3` 20, `air_elemental_die` 20 |
| `balthazar_spider` | `attack_not_used_1` 26332, `attack_not_used_2` 22768, `source_spider_sound` 20 |
| `bird` | `extend_wings` 6424 |
| `bosses/air_guardian` | `walk_left` 58984, `walk_right` 30544 |
| `bosses/earth_guardian` | `metal4attack` 20 |
| `bosses/fire_guardian` | `fire_start` 20 |
| `gargoyle` | `telltale` 19348 |
| `golem` | `golem_attack` 25288 |
| `golem_ol` | `golem_attack` 25288, `golem_ouch` 10996 |
| `harvester` | `harvester_die` 31408, `harvester_ouch_1` 24496, `harvester_run` 7468, `harvester_walk` 21292 |
| `rock_shard` | `rock_shard_idle` 41380, `rock_shard_ouch` 18376 |
| `water_lizard` | `sleeth_attack` 34252, `sleeth_ouch` 17332 |
| `water_lizardx` | `sleeth_mama_attack` 34252, `sleeth_mama_ouch` 17332 |

The other 10 of the 36 are named somewhere but bound by no table this
census reads: 4 by full key in another species' `config.xbr` cell
(`catalisk_ouch`, `flicken_die`, golem's `golem_ouch`, `obsidian`) and 6
only as a common token (`ambient`, `fire1`, `firewall`, `hop`, `lives`,
`ruby`).

## prefetch-lists.txt — the level manifest goldmine

Azurik's ISO ships with a plain-text **level manifest** at
``prefetch-lists.txt`` (ISO root, not inside ``gamedata/``).  For a
long time the old randomizer hard-coded its own level tables (deleted
with it at Step R1.10c); ``tests/test_assets_manifest.py`` reads the
canonical manifest's ``tag=`` and ``neighbor=`` lines and pins
``azurik_mod.assets.KNOWN_CUT_LEVELS`` against it (since Step 1.35 no
parser exists). The counts below are facts of the vanilla
manifest, which the identity gate fixes by sha256, so no test re-checks
them.

### File format

Stanza-based INI:

    tag=always
    file=index\\index.xbr
    file=hourglass.xbr
    file=%LANGUAGE%.xbr
    file=interface.xbr
    file=config.xbr
    file=fx.xbr
    file=characters.xbr

    tag=a1
    file=A1.xbr
    neighbor=a6
    neighbor=e6

    tag=a6-extra
    file=diskreplace_air.xbr
    file=diskreplchars.xbr

Four stanza shapes:

- ``tag=always`` — **7 globals** the streaming loader keeps
  resident across all levels.  ``%LANGUAGE%`` is substituted at
  runtime to ``english``/``french``/….
- ``tag=default`` — build-system alias for ``training_room``.
  Not a playable level in its own right.
- ``tag=<level>`` — **24 playable levels** (a1, a3, a5, a6,
  airship, airship_trans, d1, d2, e2, e5, e6, e7, f1, f2, f3,
  f4, f6, life, town, training_room, w1-w4).
- ``tag=<level>-extra`` — **5 extras packs** (``a6-extra``,
  ``e5-extra``, ``f6-extra``, ``life-extra``, ``w3-extra``)
  containing the per-element ``diskreplace_*.xbr`` bundles.

### The XBE's reader (2026-10-11)

[verified 2026-10-11: `python -m devkit re xbe find-refs --va 0x19A9D8`, the same for 0x19A984 and 0x19AA00, capstone; HM-30,
which cited the message string as the file name]  The file
name `prefetch-lists.txt` (0x19A9D8) is loaded by a `mov` at 0xB03A9,
and the message "Strange entry in prefetch-lists.txt: %s" (0x19A984)
is pushed at 0xB0577, both in the function starting near 0xB03A0
[inferred]; `filelist.txt` (0x19AA00) is loaded at 0xB007F, in the
function near 0xB0070.  Each reader has 0x104 immediates (0xB046F,
0xB0482; 0xB013C, with 0x103 at 0xB0259), which fit Level Studio's
0x104-byte line buffer [inferred].  `load_level_from_path` (0x53750)
pushes `/` (0x2F) at 0x53894, which fits taking a level's tag from
the last segment of its path [inferred].  Level Studio states, for
PAL: only `tag=`, `file=` and `neighbor=` lines, no comment lines,
lines of at most 259 characters and tags of at most 63, `%LANGUAGE%`
the only substitution, and a missing tag still loads [unverified on
USA].  The tag limit has a USA site: `mov edi, 0x3f` at 0xAF661 heads a
byte-copy loop [verified 2026-10-14: `python -m devkit re xbe dis`; PAL 0xAF7E1
at −0x180; HM-92], which fits a 63-byte tag [inferred from the loop].

### Key insight: the graph is DIRECTED, not symmetric

The ``neighbor=`` edges are **streaming-loader prefetch hints**,
not portal declarations.  Out of ~70 edges in the vanilla
manifest, at least 15 are asymmetric:

    a6 → town               # town → life, e2, f1, d1, w1 only
    w1 → airship_trans      # airship_trans has ZERO neighbors
    training_room → w1      # w1 doesn't list training_room back

``airship_trans`` is the extreme case — every airport-adjacent
zone prefetches it, it prefetches nothing.

This matters because **the randomizer can't use this graph as a
reachability solver input**.  For that we still scrape the
portal strings out of the level XBRs themselves.  The manifest
is useful for:

- Authoritative level-set enumeration (24 tags)
- Classification: is this XBR a level, a global, or an alias?
- Integrity check: does every file mentioned here exist on disk?
- Orphan detection: which XBRs on disk aren't in any stanza?
  (Answer: ``selector.xbr`` + ``loc.xbr`` — dev/UI artefacts.)

### The levels with no portal string

Two manifest levels have no ``levels/...`` destination string: the old
randomizer's hard-coded level table (deleted at Step R1.10c) left out
``training_room`` (no save-path prefix; it's bootstrapped through the
``default`` alias) and ``airship_trans`` (every entry is
cutscene-driven).

Cut content surfaces too: ``f1 → f7`` references a cut level
that has no ``tag=f7`` stanza; the randomizer's generated exit table
leaves it out (AZ-290, Step R1.1).

## filelist.txt — the integrity manifest and the HDD-cache key

Sibling file at the ISO root.  DOS-ish format:

    \\
    f <md5> <bytes> a1.xbr
    f <md5> <bytes> a3.xbr
    ...
    d index

    \\index\\
    f <md5> <bytes> index.xbr

``azurkit.core.filelist`` parses it and exposes
``rewrite`` for builds (below: the game's HDD cache keys on
these lines).  A full MD5 scan of the vanilla 951 MB dump ran in ~1.5 s
on an M1 SSD.

Until Step 1.4a Modkit exposed it as ``iso-verify
<unpacked-iso-dir> [--no-md5] [--graph]``. AzurKit's ``azurkit verify``
checks the vanilla image itself: every file against its release's
manifest, ``src/azurkit/core/manifests/usa.json`` or ``europe.json``.

### Path-scoping gotcha

``filelist.txt`` declares paths relative to the **``gamedata/``
subdirectory** (its top-level scope line is just ``\\``).  But
the file itself lives at the ISO root, one level up from
``gamedata/``.  ``FilelistManifest._resolve_root`` auto-detects
this mismatch by probing the first three entries against both
candidate roots and using whichever matches more files.  If
Microsoft's ISO layout ever changes this could need extending,
but the heuristic has zero false positives today.

### Extracted trees

Builds extract nothing since Step 1.24b: they read the input ISO in
place (Modkit's ``IsoStaging``; AzurKit's ``azurkit.core.iso.read``) and pack it with
``azurkit.core.iso.pack``, so the size-only scan that used to follow
every unpack is gone. Its last user, the MCP ``iso_verify`` check
of an extracted tree, went in Step MCP-1 (it passed an empty folder and
missed same-size edits), and ``FilelistManifest.verify`` with it.
Whether a build's files are vanilla is ``iso-verify``'s identity gate
(``azurkit.core.gate``). Size-only scan cost was ~3 ms for 42
entries on an M1 SSD, vs ~1.5 s for the full MD5 pass.

### The game's HDD cache keys on it (xemu, 2026-10-09)

[verified in xemu, 2026-10-09: the dev-oracle's
session 1] Azurik copies the files `prefetch-lists.txt` lists to an
HDD cache and plays them from there: the `tag=always` globals
`config.xbr`, `characters.xbr`, `interface.xbr` and `fx.xbr`, and each
level XBR under its own tag. It keeps using a cached copy as long as the
file's `filelist.txt` line (md5 and size) matches; a changed md5 or size
makes it re-copy the file from the DVD. Measured with QMP block
counters and a guest-RAM page match:

- A same-size `config.xbr` edit with the vanilla line left in place: RAM
  held the vanilla page, so the edit was **ignored**.
- The same edit with its md5 rewritten: `config.xbr` was re-copied
  (+570,880 B of HDD writes by the title screen) and the edited page was
  resident.
- `training_room.xbr` grown by 64 KiB and relocated: with a stale line
  the game read 0 DVD bytes for it and played the old cached copy; with
  the line updated it re-copied the file (4,694,016 B read from the DVD)
  and played the grown one. The game doesn't check a file's size against
  its directory record.
- [inferred] The cache is on the Xbox utility partition. Open: which
  partition, whether the game compares a stored md5 or recomputes it, and
  how it behaves with a cold cache.

Session 2 answered part of that [verified unless labelled; kernel
file-call breakpoints and QMP block counters]:

- **At boot** the game reads `d:\filelist.txt`, creates
  `z:\gamedata\` and `z:\gamedata\index\`, reads
  `d:\prefetch-lists.txt`, and then opens every cached file in
  `prefetch-lists.txt` order (the `tag=always` files, then `default`,
  then the level tags), each for a time in proportion to its size, at
  5–8 MB/s.  So it re-reads, and presumably re-hashes, the whole cache
  at every boot rather than trusting a stored md5 [inferred from the
  timing and the volume read].
- **`Z:`** is the title's utility drive; the game opens
  `\Device\Harddisk0\Partition5\` just before its first `\??` path, so
  it is probably partition 5 [inferred].
- **A re-copy** opens the cached `z:\gamedata\config.xbr` for delete,
  writes `z:\gamedata\config.new` from the DVD copy (35 `NtWriteFile`
  calls, 565,818 B, the whole file) and renames it [the rename is
  inferred from the access mask].
- **A fresh clone of the owner's HDD** re-copies `training_room.xbr`
  once on its first boot (4,623,360 B written) [verified]; [inferred]
  the owner's cache held a copy that didn't match `filelist.txt`.

The cold cache, and added and missing files: below (Step X.77). Still
open: proof that the game hashes the files (it reads each whole).

So **every build rewrites the line of each listed file it changes**,
with `azurkit.core.filelist.rewrite` (same format; the
size stays right-aligned in its column). `azurkit.core.iso.pack` does
it for its overrides: `filelist.txt` becomes an implicit override, and
an explicit `filelist.txt` override is the text that gets rewritten.
Since Step 1.24b every build packs through it (`patch`, `randomize-full`
with the GUI and MCP `rando_build_iso` that run it, `apply-physics`, MCP
`pack_build_iso` and `iso_repack`),
and none writes its input (D36). A file `filelist.txt` doesn't list (for
example `default.xbe`) changes nothing, so XBE-only builds such as
`apply-physics` from vanilla still carry vanilla's `filelist.txt`.

**Re-test old null results.** Until 2026-10-09 no builder rewrote
`filelist.txt`. An XBR edit tested on a console or emulator whose cache
already held that file may have done nothing because of the cache, not
the edit [inferred]. Any "bytes landed, no in-game effect" result on
`config.xbr` or a level XBR is worth repeating with a current build.
As of 2026-10-10 no catalogued XBR null result is left: each has
another cause, and the corrected edit has since been seen to reach the
game in xemu (walk speed via garret4 `runSpeed`; air-shield `Flaps`
edits, which hit the wrong table before AZ-113; player HP via
settings_foo `initial hp`, D44) [inferred; `azurik-game-reference` §6
rows #3, #10 and #14].  The rule stands for any result not in that
catalogue.

### Added and missing files (xemu, Step X.77)

[verified in xemu v0.16.4, 2026-10-25, unless labelled: each build from
a vanilla image, cold-booted from a D98 save-menu state at its save, the
kernel's file calls traced by the fork's PC hooks;
Step X.77's sitting and its re-run] A cold cache here is the
D98 drive with its cache database (HDD sector 4, the title's entry)
zeroed, so the kernel formats the title a fresh utility partition, as on
a new drive.

- **Root files nothing names are never opened.** `/azurkit.json` and
  `/azurkit.bin` added at the root (`xiso.pack(..., add=)`, Modkit's `TOOLS.md`)
  boot first try and play at w1 and a1 (USA) and w1 (Europe), on
  vanilla's boot frames and file calls.
- **Where it reads.** `default.xbe`, `filelist.txt`,
  `prefetch-lists.txt`, `english.txt`, `minimal.bin` and the movies come
  from the disc; every gamedata file both lists name plays from
  `z:\gamedata\`. At boot the `tag=always` files and `training_room.xbr`
  are read whole from the cache and re-copied from the disc where they
  don't match their line; a cold cache copies all eight (184 MiB) before
  the movie. A level's file is copied at its load if the cache lacks it,
  then read from `z:`; the copier then works through the level's
  neighbors in the background (w1, cold: 235 MiB read from the disc in
  its first 300 frames, by the drive's block counter).
- **A file with no `filelist.txt` line is skipped.** Added with no line
  (`gamedata/x77.xbr`, under its own prefetch tag or in `tag=always`), it
  is never opened, cold or warm, and nothing breaks. A cached copy of a
  file whose line is gone is opened for delete at boot [inferred from the
  access mask], and a level whose file has no line never loads: w1's save
  stops on a black screen before `load_level_from_path`, warm or cold.
- **An added file with its line is copied.** The same `x77.xbr` with its
  own md5 and size line, in `tag=always`, is copied whole from the disc at
  boot into `z:\gamedata\x77.new` and renamed [the rename inferred from
  the access mask], warm (the cache lacks it) and cold, and w1 plays on.
- **A listed file missing from the disc** (`a1.xbr` renamed, its line
  kept): with a warm cache a1's save plays a1 from the cache's old copy,
  never asking the disc (RAM the same as vanilla's at the steady tick);
  with a cold cache the load gets 0xC0000034 opening `d:\gamedata\a1.xbr`
  and hangs on "Loading...". With its line dropped too (its prefetch tag
  and neighbor lines kept), the warm cache's copy is deleted at boot and
  a1's save never loads, warm or cold. With its line kept and every
  prefetch reference to it dropped (the `a1` tag and both `neighbor=a1`
  lines), nothing opens it and w1 plays, warm and cold, opening the
  files vanilla opens.

So an added gamedata file needs its own line and a prefetch reference
(AzurKit's derived `filelist.txt`, Step 4.4): with both it is copied at
boot, without the line never. A removed one must lose every reference to
it (its prefetch `file=` and `neighbor=` lines, and [inferred] a level's
portal), or a warm cache hides the removal and a cold one hangs (Step
4.9's `file.remove`). Its line should go with them: a kept line is inert
[measured at w1 only], and a dropped one has the copier delete a warm
cache's stale copy at boot.

## selector.xbr — the developer level-select hub

Discovered during the filelist/prefetch cross-check: 2 MB level
XBR that IS on disk, IS referenced by the XBE, but is NOT in
``prefetch-lists.txt``.

### What it is

``selector.xbr`` is a legitimate, playable in-game level built on
the same layout as every other level (``node``, ``levl``, ``surf``,
``rdms``, etc.).  Its ``node`` section carries **35 portal
strings** that between them reach every live level in the game,
plus direct cutscene triggers:

- 22 regular level portals — ``levels/fire/f1`` through
  ``levels/water/w4``, ``levels/life``, ``levels/town``, etc.
- 1 self-reference (``levels/selector``)
- 1 portal to a **cut level** (``levels/earth/e4``) — the only
  on-disk reference to this level anywhere
- 10 movie-scene triggers (``movies/scenes/prophecy``,
  ``movies/scenes/training1``, …``disksdestroyed``,
  ``catalisks``, ``airship2``, ``death1``, ``deathmeeting2``,
  ``disks_restoredall``, ``newdeath``)

So it's a developer level-select hub: loading this level gives you
single-click access to every level + cutscene.  It is not the in-game
cheat UI (`cheats.cpp`, [`RE_XBE.md`](RE_XBE.md) § "Native cheat
UI").

### How to activate it

Nobody has.  The XBE has 4 ``.text`` references to the
``"levels/selector"`` string at ``VA 0x1A1E3C``:

- ``VA 0x12C56``  — probably init/boot-path
- ``VA 0x52FA7, 0x533E3, 0x53400`` — inside ``0x52F50``
  (`game_start_setup` in Ghidra since D94, 2026-10-11;
  `dev_menu_flag_check` in the registry until AzurKit 4.2/4.3, D68).

[verified 2026-10-10: capstone over 0x52F50–0x52FC0] At 0x52F95
the choice between ``levels/selector`` and ``levels/training_room``
(0x1A1E4C) follows the AL result of a virtual call at 0x52F90; it
is **not** gated by the BSS dword at ``0x001BCDD8``.  That dword only
sets ESI on the selector branch (3 when it holds −1, otherwise its
value; the training-room branch sets ESI to 1), and what ESI means
is unknown.  Even the chosen candidate is only the second stage of a
three-stage validator chain whose first stage, the caller's own level
string, almost always wins.  The third stage is ``levels/selector``
again: 0x533E3 hands it to 0x54520, the check every stage makes, and
0x53400 pushes it for ``load_level_from_path`` (the call at 0x53406),
so the hub loads when 0x54520 refuses the first two [verified
2026-10-12: `xbe dis 0x53360:50`, `xbe fn 0x52F50`].  The selector
branch is taken only when the virtual call at 0x52F79 returns
non-zero too; when it returns zero, the code at 0x5307F runs and
makes neither string the stage-2 candidate.

Earlier notes (and `azurik.h`) said a single store of a non-−1 value
into ``0x001BCDD8`` would load the hub; the disassembly above says
otherwise, and it was never tried.  The four April-2026 attempts to
force the hub (JZ NOPs, a cvar thunk, the validator short-circuit, a
``FUN_00053750`` trampoline) all landed their bytes with no in-game
effect (Modkit's `Finished/LEARNINGS_HISTORY.md`
§ "enable_dev_menu — retired as unshippable").

### Why it's a prefetch-manifest orphan

The streaming loader doesn't see it because it's never on a
level's ``neighbor=`` list.  It's loaded directly by
``0x52F50`` (`game_start_setup`) which bypasses the prefetch system entirely.
It is a prefetch-manifest orphan alongside ``loc.xbr`` (both are in
``filelist.txt`` but in no stanza; the identity gate fixes both
manifests by sha256, so since Step 1.35 no test re-checks it) — both
are legitimate, both are unused by the normal game flow.

### Cut-level discoveries

Two cut levels are now documented as ``KNOWN_CUT_LEVELS``:

- ``f7`` — referenced only by ``f1``'s ``neighbor=`` list in
  ``prefetch-lists.txt``.  The randomizer's
  ``EXCLUDE_TRANSITIONS`` already knows about it.
- ``e4`` — referenced only by ``selector.xbr``'s portal list.
  No XBE code paths reference it.

Both are useful flags for a future "randomizer finds all known
dead portals" audit pass.

## index.xbr — the global asset-path index

Second orphan-looking file that's actually in the ``always``
stanza of ``prefetch-lists.txt`` — the streaming loader keeps
it resident throughout the game.

### Structure (AZ-218, 2026-10-11)

[verified 2026-10-11: `azurkit.tools.characters.index_xbr.load_index_xbr` and
`tests/test_index_xbr.py` on the vanilla ISO; first found by the hub
mining, Modkit's `HUB_MINING_PLAN.md` HM-03.] One TOC entry, `indx`,
its payload at file offset 0x1000 (0x2713F bytes):

```
payload+0x0000  u32  count           3072
payload+0x0004  i32  table pointer   relative to its own field: payload+8
payload+0x0008  3072 records of 20 bytes (to payload+0xF008), sorted
                and unique by key, then the NUL-terminated strings
```

| Record offset | Type | Field |
|---|---|---|
| +0 | u32 | key length (no NUL) |
| +4 | i32 | key pointer, relative to its own field |
| +8 | u32 | archive-name length |
| +12 | i32 | archive-name pointer, relative to its own field |
| +16 | char[4] | fourcc |

**Tags:** surf 1099, wave 816, banm 712, node 230, body 160, levl
33, tabl 18, font 4, across 40 archives.  The 33 `levl` keys are 24
under `levels/` (including `levels/selector`) and 9 under
`movies/scenes/`; 28 keys in all sit under `levels/` (4 are `node`
keys).

**What a record says.** Each one repeats a row of its archive's own
named-resource table ([`XBR_FORMAT.md`](XBR_FORMAT.md) § "The
trailer"): all 3072 do, and the only named row with no record is
index.xbr's own `index`.  No record holds a TOC index; the archive's
table maps the name to its TOC entry.  So index.xbr says which archive
holds a named asset, and the archive says where (below).  A mod that
adds a named asset must add its record, in key order, as well as its
archive's named row (`src/azurkit/core/xbr/append.py` and
`add_index_records`, [`XBR_FORMAT.md`](XBR_FORMAT.md) § "Appending
resources"); in-place edits of existing assets need neither.

### How a name resolves (Step 2.86)

[verified static 2026-10-15: capstone (`python -m devkit re xbe fn|calls`) on
the vanilla USA XBE; first traced by the bake research.]

1. **At boot, 0xA6A70** (one caller, 0xA6B89) reads the loaded `indx`
   payload ([0x1BE370]: the count at +0, the table pointer at +4),
   sizes the name map 0x37BE00 for count + 1 (0xA8140), and for each
   record registers its archive by file name (0xA4940) and inserts the
   key (0xA8030) as a node: the archive, the handle −1 and the record's
   fourcc.
2. **When an archive opens**, its state machine (0xA5700: the header
   check 0xBDBB0 at 0xA5735, then the trailer read on its own from
   `header[0x18]`, sized as 0xBDC10 computes it) calls 0xA56B0 once,
   which runs **0xA54F0** and then **0xA5570**:
   - 0xA54F0 looks up each per-tag row's fourcc in the engine's tag
     registry (0xAA140) and compares its version (the row's u32).  An
     unknown tag, or a version mismatch ("incorrect resource versions
     in %s", 0xA56DB), goes to the fatal error 0xA9100, which formats
     the message and sleeps in a loop forever: the game hangs.
   - 0xA5570 walks every named row (`header[0x2C]` rows), finds the
     row's name in the name map (0xA7580) and, when a node exists,
     sets its handle to the archive's slot base + the row's TOC index
     (slot << 20 | index).  A row with no index record is ignored.
3. **A lookup, 0xA5CA0** (ECX the name; stack: a fourcc filter, 0 for
   any, and the wait mode): 0xA5B10 lowercases the name and finds its
   node; no node, or a fourcc other than the filter, returns −1.  It
   opens the node's archive if it isn't (0xA5350, waiting), then
   returns the node's handle: −1 for a record whose archive has no
   named row of that name.
4. **Loading the payload:** a handle's run comes from the run builder
   **0xA4C00**, which starts a run at a page-aligned TOC offset (the
   run descriptor below); every vanilla `banm` starts on a page.

So a new key needs both its index record (the node) and its archive's
named row (the handle); its payload starts on a page and its tag must
already have a per-tag row.  A grown characters.xbr built this way:
see `XBR_FORMAT.md` § "Appending resources" for what was seen in xemu.

**`load_asset_by_fourcc` (0xA67A0) doesn't read these records**
[verified 2026-10-11: capstone].  It strides 16 bytes (`shl eax, 4`)
from the table at descriptor+0x0C, compares the fourcc at +8 and
returns `[descriptor+0x10] − [entry 0] + [entry]`: the loaded
archive's TOC, read as the engine reads it at 0xA5619 ([`XBR_FORMAT.md`](XBR_FORMAT.md)
§ "Table of contents").

**The run descriptor** [verified 2026-10-11 by Step 2.17f: capstone].
EAX carries a handle, (archive slot << 20) | TOC index, and a negative
one returns `~EAX` with no lookup (0xA67A8).  0xA59F0 picks the archive
in [0x37BE34] by bits 20–30, and the archive's u16 table at +0x28,
indexed by the low 20 bits, gives the run (0x8000 = none).  Each run
has a 28-byte descriptor in the array at [0x37BE50]: 0xA59F0 indexes it
with `imul 0x1c`, and the run builder divides by 28 at 0xA4D55.

| Offset | Type | Field |
|---|---|---|
| +0x00, +0x04 | ptr | list links (next, prev); unlinked and re-linked at 0xA6205 |
| +0x08 | u32 | the handle of the run's first TOC entry (stored at 0xA4DB5) |
| +0x0C | ptr | the run's first 16-byte TOC entry; the builder counts (end − start) >> 4 |
| +0x10 | ptr | where that entry's payload was loaded |
| +0x14 | u32 | the value of [0x1BE36C] (0xA4DE8, 0xA5A5E) |
| +0x18 | u16 | a reference count: 0 at 0xA4DE0, decremented at 0xA61F4 |
| +0x1A | u16 | bits 0–6 the entry count; `& 0x3000` the state: 0x1000 as built (0xA4DD9; 0xA59F0 takes it as not loaded, 0xA5A4F), 0x2000 while loading (0xA67A0 waits), 0x3000 loaded (0xA587C); bit 15 a flag (0xA4DED, 0xA6251) |

**A call loads on demand and can block.** `load_asset_by_fourcc`
passes EAX = 2 to 0xA59F0.  For a handle with no run (0x8000) or a
run still at 0x1000, that takes the load path: the TOC-entry lookup
0xA5980 (which also waits when EAX ≥ 2), the run builder 0xA4C00 when
there is no run, then 0xA5480, which starts the load and sets 0x2000
(0xA54D4).  0xA67A0 then waits while the state is 0x2000
(0xA67E1–0xA681C).  So a hit returns a pointer to the entry's loaded
payload, and 0 comes back only on a failed lookup or build (0xA5A79,
0xA5A9D), a state other than 0x3000 after the wait (0xA6830) or a
fourcc miss (0xA6845).
`devkit/re/data/structs.h` declares this descriptor as `XbrTocRun`,
its 16-byte entries as `XbrTocEntry` and index.xbr's 20-byte record as
`IndexXbrRecord`.  Until Step 4.41a they were Modkit's `IndexEntry` and
`IndexRecord`, with index.xbr's names and, for the record, a layout the
engine doesn't read here (AZ-247).

### Until AZ-218

The parser and `IndexRecordsSection` read a 16-byte header and found
3071 records, so every field they named was another one: "version 4"
was the table pointer, "header_hint 24" record 0's key length,
"pool_hint 0xEFFC" record 0's key pointer (it lands at payload+0xF008,
the table's end), and "pool magic 0x1812D" / "pool tag `levl`" the last
record's archive pointer and fourcc (`movies/scenes/wirlpoolfixed`).
The "discriminator byte" was the low byte of the next record's key
length, and the earlier tag list (`gems`, `indx`) came from strings,
not records.

## Level loading

Moved from the level loading-zone audit in Step 3.3d (2026-10-10),
keeping its section numbers. The audit's per-level breakdown,
side-file and implicit zones, Ghidra sync and method stayed in Modkit's
archive (AzurKit has no copy of the audit).
The catalogue module (`loading_zones.py`) and its tests went with the
old randomizer at Step R1.10c; the randomizer's exit table is generated
from the levels (Step R1.1).

### 1. What counts as a "loading zone"

Anything that ends up calling `load_level_from_path` with a
non-empty level path string, or that sets the destination keyword
`return-to-shell`, which `scene_state_tick` answers by returning
instead of loading a level (§ 7).  There are **five** distinct
sources in the shipped game:

| # | Source                           | Lives in        | Examples                                          | Randomizable? |
| - | -------------------------------- | --------------- | ------------------------------------------------- | ------------- |
| 1 | `levelSwitch` buckets            | level XBRs      | `town -> life`, `f3 -> w4`                        | ✅            |
| 2 | `selector.xbr` level-select hub  | `selector.xbr`  | developer level-select (23 slots)                 | ⛔ (developer hub) |
| 3 | `diskreplace_*.xbr` cutscene tails | cutscene XBRs | `diskreplace_earth -> town`                       | ⛔ (cutscene)  |
| 4 | Hardcoded XBE literals           | `default.xbe`   | `levels/water/w1` (tutorial end), `levels/selector` (developer hub) | ⛔ (code) |
| 5 | Ending-cutscene chain            | `d1.xbr`        | Spideyzar-kill credits → Xbox shell               | ⛔ (end-game) |

A `levelSwitch` node holds three (length, field-relative pointer)
strings: a movie at +0x18, a destination at +0x20 and a spot at +0x28
([`XBR_FORMAT.md`](XBR_FORMAT.md) § "Level node graph").  Destination
strings are pooled, so several switches can share one.  Switches that
aren't portals of their own are catalogued separately
(`implicit_zones()`, AZ-221): named switches that point at a
catalogued portal's string, and the cutscene files' switches with a
keyword destination (`end-of-cut-scene`, `start-playing`) or none.

### 2. Headline numbers (post-deep-pass)

| Category                | Count | Note |
| ----------------------- | ----- | ---- |
| Randomizable zones      | **50** | the old randomizer's connection shuffle (retired at Step R1.10b; exits stay vanilla in v1) |
| `selector.xbr` zones    | **23** | developer hub only; **includes the cut level `e4` + the `levels/selector` self-re-entry** |
| Cutscene-return zones   | 3      | `diskreplace_earth`, `diskreplace_water`, `wirlpoolfixed` → `town` |
| Hardcoded XBE zones     | 4      | `w1` for a stored `start-playing` + the selector / training_room candidates in `dev_menu_flag_check` + the `return-to-shell` destination |
| Ending-cutscene zones   | **1**  | `d1` Spideyzar credits chain → shell (new, 2026 deep-pass) |
| Switches that aren't portals | **21** | 10 named switches sharing a portal's `levels/` string; 11 cutscene enders (`end-of-cut-scene`, `start-playing` or none) |

**Total catalogued destinations (sources 1–5): 81.**

#### The switches that aren't portals (AZ-221, 2026-10-11)

[verified 2026-10-11: a decode of every `levelSwitch` node on the
vanilla ISO, names through each graph's `ndbg`, and which portal
string each points at by file offset; HUB_MINING_PLAN
HM-09.]  The ISO has 124 `levelSwitch` nodes: 110 with a `levels/`
destination, 10 with a keyword (`end-of-cut-scene`, `return-to-shell`,
`start-playing`) and 4 with none.  A vanilla test (deleted with the
catalogue at Step R1.10c) decoded these nodes and checked all 21
catalogue rows below against them.

**Named switches sharing a portal's string.**  Each points at the
very string `_find_level_transitions` reports for a catalogued zone in
the same file, so the randomizer's rewrite of that string moves it
too; its own spot and movie stay.

| Source | Switch | Movie | Destination / spot | Shares with |
|---|---|---|---|---|
| `a6` | `Killed_levelSwitch` | — | `levels/town` / `air_disk_loc` | `PlaceAirDisk_levelSwitch` (the a6 → town portal) |
| `a6` | `PlaceAirDisk_levelSwitch` | `movies/scenes/diskreplace_air` | `levels/town` / `air_disk_loc` | `Killed_levelSwitch` |
| `airship` | `EndFight_levelSwitch` | `movies/scenes/airship_docking` | `levels/air/a3` / `W1_A3` | (the airship → a3 portal's only switch) |
| `d1` | `D2_movie_levelSwitch` | `bink:death.bik` | `levels/death/d2` / `D1_D2_Fall` | `D1_D2_levelSwitch` (spot `D1_D2`) |
| `e5` | `DiskReplaced_levelSwitch` | `movies/scenes/diskreplace_earth` | `levels/town` / `earth_disk_loc` | (the e5 → town portal's only switch) |
| `f6` | `BackToTown_levelSwitch` | — | `levels/town` / `fire_disk_loc` | `PlaceFireDisk_levelSwitch` |
| `life` | `Movie_levelSwitch` | `movies/scenes/diskreplace_life` | `levels/town` / `life_disk_loc` | `Town_levelSwitch` |
| `w1` | `AirshipFight_levelSwitch` | `bink:airship2.bik` | `levels/air/airship` / `startspot` | (the w1 → airship portal's only switch) |
| `w1` | `BossDefeated_levelSwitch` | — | `levels/town` / `water_disk_loc` | `W1_Town`, `W1_Town_levelSwitch2` (spot `W1_Town_Waterfall`) |
| `diskreplace_earth` | `AirShipLanding_levelSwitch` | `movies/scenes/airship_docking_water` | `levels/town` / `earth_disc_loc` | (the cutscene-return zone's switch) |

Other switches share strings too (w1's six `levels/water/w3`
switches, e5's three `levels/earth/e2`); the catalogue lists only the
ones the deep-pass audit took for destination-less.  The w1 → airship
portal's catalogued spot stays "": the portal scanner reads the string
after the destination, and `startspot` is pooled elsewhere.

**Cutscene enders.**  `training_room`'s `EndTutorial_levelSwitch`
plays `bink:training.bik;possessed.bik;disksdestroyed.bik` with the
destination `start-playing` and the spot `startspot`; for a stored
`start-playing`, `scene_state_tick` takes the XBE's `levels/water/w1`
/ `Town_W1_Movie` (§ 6).  The
`levelSwitch1`/`levelSwitch2` of `airship_docking`,
`airship_docking_water`, `airship_trans`, `diskreplace_air`,
`diskreplace_fire` and `diskreplace_life`, `diskreplace_earth`'s
`BacktoTown_levelSwitch` and `wirlpoolfixed`'s `levelSwitch_endscene`
have the destination `end-of-cut-scene`, except `diskreplace_air`'s
and `diskreplace_life`'s `levelSwitch1`, which play
`movies/scenes/newdeath` with none.

**Until AZ-221** the catalogue called 18 switches "implicit", with
"NO destination string", found by scanning for `<Name>_levelSwitch\0`
strings: the 11 named ones above and 7 "anonymous" ones (the cutscene
files' `levelSwitch1`/`levelSwitch2`, and a separate "training_room
movie chain" that is `EndTutorial_levelSwitch` itself).  It also had
`diskreplace_earth` backwards: `BacktoTown_levelSwitch` ends the
cutscene and `AirShipLanding_levelSwitch` carries `levels/town`.

### 6. Hardcoded XBE zones

Three `levels/...` path literals and the `return-to-shell` keyword,
baked into `default.xbe` itself.  Code loads or stores them, not XBR
data, so they bypass every data-side editor.  Documented with Ghidra
VAs so future analysis can find the sites:

| Destination             | Spot               | Fires from                          | Function VA  | Data VA of string |
| ----------------------- | ------------------ | ----------------------------------- | ------------ | ----------------- |
| `levels/water/w1`       | `Town_W1_Movie`    | `scene_state_tick` (a stored `start-playing`, 0x55E9A) | `0x00055AB0` | `0x0019ECF8` |
| `levels/selector`       | —                  | `game_start_setup` (registry: `dev_menu_flag_check`), stage-2 candidate and stage-3 fallback | `0x00052F50` | `0x001A1E3C` |
| `levels/training_room`  | —                  | `game_start_setup` (registry: `dev_menu_flag_check`), stage-2 | `0x00052F50` | `0x001A1E4C` |
| `return-to-shell` (keyword) | —              | `level_teleport_helper` (non-zero byte flag, § 6a) | `0x00052950` | `0x0019EEDC` |

[verified 2026-10-11: capstone on the vanilla `default.xbe`, `xbe
find-refs --va` and `xbe calls --to`.]  Until AZ-260 the last row was
"(any)" with the spot `return-to-shell`.  Their three functions are
registered in
the facts' `functions`
([`facts.usa.json`](../src/azurkit/core/facts.usa.json)) and declared in
the `azurik_vanilla.h` shimkit writes from them.
They have been renamed in the live Ghidra project and carry plate
comments pointing back to this audit; those comments predate AZ-250
and AZ-260 and may still give the old account.

#### 6a. `level_teleport_helper` calling-convention quirk

Discovered during the 2026 deep-pass: `level_teleport_helper`
(VA `0x00052950`) pops one stack byte flag (`RET 4`, declared
`stdcall(4)` in `vanilla_symbols.py` and `azurik_vanilla.h` since
REORG_PLAN Step 1.31), but it also reads two registers its caller
sets [verified 2026-10-11: capstone]:

- `EDI` → the scene state (`gScene`, the pointer at `0x1BF63C`)
- `EBX` → a movie path, which it hands to `0x54520` and then plays

When `0x54520` refuses the movie it returns 0.  Otherwise it
releases and clears the object at scene+0x28, copies
`return-to-shell` (flag non-zero: `test al, al` at `0x5297F`) or an
empty string (flag zero) into scene+0x169, the slot where
`scene_state_tick` stores a fired switch's destination (`0x55DB2`),
calls `load_level_from_path(scene, movie, NULL, 1)` (`0x529BD`,
`0x529F3`) and returns 1.  So it plays a movie and sets the
destination that follows it.  Its callers are `0x5F678` (flag 0; EBX
is the start path the pointer at `0x1BCDD0` holds, after a compare
with `movies/scenes/` at `0x5F658`) and a wrapper at `0x56680` that sets
`EDI` and passes its own caller's `EBX`; who calls the wrapper isn't
traced, and the death handler and debug-console exit older notes
named are unverified.

Shim authors calling `level_teleport_helper` directly need to set
up those registers before the call; no plain-call equivalent is
verified.  Until AZ-260 this section said `EBX` was a destination
level path (`0` for shell-return) and advised passing `NULL` and
`"return-to-shell"` to `load_level_from_path`: two arguments to a
four-argument `stdcall`, naming the keyword as a path.

Logged as a warning in both `vanilla_symbols.py` and
`azurik_vanilla.h` so future shim reviewers can't accidentally
call it through its declaration.

### 7. Ending-cutscene zones — the Spideyzar credits chain

The `EndGame_levelSwitch` node in `d1.xbr` is the terminal
loading zone of the game.  Its movie is a semicolon-delimited
`bink:` chain of seven movies:

```
bink:spideyzardeath.bik;disksrestored.bik;newdeath.bik;credits.bik;credits2.bik;credits3.bik;credits4.bik
```

its destination is the keyword `return-to-shell`, and it has no spot
[verified 2026-10-11: the node decode of the catalogue's vanilla test,
deleted at Step R1.10c].

`scene_state_tick` compares a destination with `return-to-shell`
and returns instead of loading a level [verified 2026-10-11:
capstone].  A switch whose movie `0x54520` accepts has its
destination stored at scene+0x169 while the movie loads
(`0x55D7F`–`0x55E2F`); after `end-of-cut-scene`, a stored
`return-to-shell` that `0x54520` refuses makes it return 5
(`0x55E7B`).  A switch whose movie it refuses and whose destination
is `return-to-shell` makes it return 2 (`0x55F07`).
`level_teleport_helper` (§ 6a) stores the same keyword.  [inferred:
`0x54520` refuses the keyword, the credits take the first path, and
the end of the game follows from the callers (`0x566DC`,
`0x5F882`); what they do with 2 and 5 isn't traced.]

Catalogued as the single entry in `_ENDING_ZONES`, with
`return-to-shell` as its destination (until AZ-260, as its spot).
Not randomizable (destination is the shell, not a level).

### 8. d1's death seal and Spideyzar's floor (Step R2.12a, 2026-10-15)

[verified data 2026-10-15: `azurkit.core.xbr.nodes` on the vanilla
`d1.xbr` and `town.xbr`, and the R0 decode; in game where marked]

- **Nothing before d1 asks for a disc.** Town's way down is its grate
  elevator (`D1EntranceElevator_toggle`, toggled by the elevator's
  touch) and `toD1_levelSwitch`, a plain touch of `TownExitFieldShape`.
  d1's arrival rides its own grate elevator into the seal's chamber
  (13.6 m across and 42 m below `startspotShape`).
- **The seal.** `discDeath:SealActivate_andCombiner` (record 389) is a
  touch of `discDeath:SealShape` AND five links from
  `discDeath:SealFragmentNumber_gameState` (388), each disc's count
  through a step curve that is 1 at 4 or more; it turns on
  `discDeath:Seal_toggle` (390, saved), whose goal turns on
  `ChromaticGate_toggle` (391, saved, onTime 6 s). Its output drives
  `FieldShape.gameSolid` (1264, 7 m from the seal; stored 1.0) through
  a step that is solid below 0.5. Five more links from 388 feed the help
  popup's NOR.
- **The thresholds are one f32 each.** Each of 388's ten links has its
  own two-key curve, keys (0, 0) and (4, 1) with a held step; its first
  key's y is at `d1.xbr` file offset 0x1AB2F8C + 0x20·k for the five
  AND links (k = 0–4, links 0–4) and 0x1AB358C + 0x20·k for the five
  help links. Writing 1.0 there makes the test true at any count, a
  fixed-width `xbr_edits` `replace_bytes` with its `expected` 0.0.
  On such a build (only those ten writes, from vanilla), booted at the
  new-game save with no fragment and warped to d1, the five AND inputs
  read 1.0 before any touch; a placement onto the seal fired its touch,
  `Seal_toggle` and `ChromaticGate_toggle` went to goal 1, and 10 s
  later `FieldShape.gameSolid` read 0.0, the help NOR staying 0 [verified
  xemu, placed: sitting r212a].
  Writing 0 into the first key's y of the field's link instead
  (`ChromaticGate_toggle`'s link 2, keys (0, 1), (0.5, 0), (1, 0) at
  file 0x1AADA18) would leave the field open with no touch at all
  [inferred from the curve rule].
- **Floor 9.** `spideyzarGeneratorShape.enable` (799, saved) is
  `DisablingElevator_andCombiner` (795): the elevator call
  `CallFloor_orCombiner` (787) in [8.5, 9.5) AND a positional link from
  the elevator. The same floor test feeds `DisableElevator_nandCombiner`
  (645: the elevator's rate and its red, green and blue switches) and
  `DisableElevator_andCombiner` (1781: the switches' turn-offs), so the
  elevator stops at floor 9. The keyed call there is `switch9` on floor
  11 (death_keylock2's battery), or a touch of `CallField9Shape`.
  Spideyzar's `numDead` drives `EndGame_and` (with `death_disk_placed`
  0) and the global `DeathRealm_fixed`. A combiner's attribute block
  always holds `inputs[0]`..`inputs[15]` and its record +0x18 is the
  count it reads, so giving one a third input is a fixed-width edit.
- **The central elevator** (Step R1.16c's intake of X.34, read with
  `azurkit.tools.randomizer.levels` on the vanilla `d1.xbr`; [observed]
  where marked: the owner's clean run 1). Its deck's three buttons (SwitchShape r644 red, r700 green,
  r731 blue) send it to the floor its colour holds (`timesCombiner_*` →
  `CallFloor_orCombiner` → `Elevator_damper`); the stored programs are
  red 1, green 3 and blue 5 (`RedFloorSwitch`, `GreenFloorSwitch`,
  `BlueFloorSwitch_maxCombiner`, saved with the nine Floor toggles).
  Each floor switch flips its `FloorNtoAorB` toggle and sets its colour
  to the toggle's new floor, and the program holds [observed]: red by
  `switch` (on floor 2: 1 or 7), `switch5` (floor 6: 1 or 10) and
  `switch6` (floor 7: 1 or 8); green by `switch7` (floor 8: 3 or 2),
  `switch4` (floor 5: 3 or 4), `switch3` (floor 4: 4 or 6) and `switch8`
  (floor 10: 4 or 11); blue by `switch2` (floor 3: 5 or 7) and `switch9`
  (floor 11: 5 or 9). `switch7`, `switch4` and `switch9` are keyed:
  their `Key_toggle` starts at 0 and death_keylock1 (r656), death_keylock
  (r669) and death_keylock2 (r719) turn it on; every other starts at 1.
  `CallField1`–`11` call it to the floor touched. So floor 9 needs
  death_keylock2 and, by the elevator alone, death_keylock;
  death_keylock1 only sends green to floor 2 (the logic asks all three,
  AZ-476).
- **The elevator's wiring as records** (Step R1.16d, read from the
  vanilla `d1.xbr`'s graph g0; the chain driver's `LIFT_*` tables in
  `devkit/xemu/chain.py`). A floor switch is
  `switchN:public_switchShape` (X, `actionButton`) AND its `Key_toggle`;
  that combiner toggles its `FloorNtoAorB_toggle` and pulses two ANDs
  with the toggle's goal, one through an inverting curve, into its
  colour's maxCombiner input of that floor (the curved one by way of
  the colour's `Red1`, `Green3`, `Green4` or `Blue5_orCombiner`): goal
  1 gives the floor of the AND with no curve (`Floor7to8_andCombiner`:
  8), goal 0 the other. The names list the two floors in that order
  but for `Floor2to7or1`, whose goal 1 gives 7. Each colour's
  maxCombiner `index` reaches its `timesCombiner_*` `inputs[1]` with no
  curve (the colour's floor; that the attribute block holds it live is
  [inferred]), and the deck's button (`public_*Switch_andCombiner`, gated
  by `DisableElevator_nandCombiner`) its `inputs[0]`. `CallFieldN`'s
  touch reaches `CallFloor_orCombiner` (787) through a curve giving N
  (CallField1, 7 and 11 through `Floor1`, `StartTown` and `StartTop`
  or-combiners), whose output feeds back into its own `inputs[14]` and,
  through a curve to a height, `Elevator_damper`'s goal; the damper's
  output drives `public_Elevator`'s translateZ.
- **Spideyzar killed in xemu** (Step R1.16c; [observed, assisted]: the
  game's no-damage and refill cheats on). The elevator rode about 330 ticks to floor 9 after
  `CallField9Shape`'s touch. In sitting r116c-a he spawned from his
  generator (r799) 774 ticks after the touch; EAFW swung in closed loop
  took his HP from 3,000 to 0 in 2,860 ticks; the generator's `numDead`
  read 0 before the fight and 1 after, and the level path then named
  the victory's movie chain (`spideyzardeath` … `credits2`; null
  renderer, not watched).

## Live pickups: what guest RAM says of a seed being played (Step R1.26, 2026-10-16)

What the tracker's Live (`src/azurkit/tools/randomizer/live/game.py`, D249) reads, and
why each read means what it says. USA VAs; Europe's through
`region_europe.json` (the scene global 0x1C15DC; the three vtables below
by their constructors' witnesses). [static] is the USA `default.xbe`
(capstone, a read-only Ghidra serve); [RAM] is offline reads of the
private L3 store's snapshots of real xemu sessions. [xemu] is Step R1.26's two sittings
(2026-10-16; the fork v0.14-36 on a randomize-full seed build of each
release, and upstream v0.8.136 cold-booting the USA one): Live's own `Session` over shared RAM, QMP and the
gdbstub (a link Step 2.91b has since deleted, D257), which agreed field
by field; [placed] marks a set-up written
into RAM (a pad state, HP, a count, a start spot); what they didn't
reach stays [inferred].

- **The chain.** `pd = [[0x1BF63C]+0x2C]`; `[scene+0x28]` is the save
  device (vtable 0x19E240). pd: +0x00 the level path (`levels/water/w2`,
  0x50 B), +0xC0 the player critter, +0xDC the level's main graph (the
  one its save list holds), +0xE0 the inventory (0x1D4 saved bytes,
  `SAVE_FORMAT.md` § 4e; +0x1D8 points back at pd). The critter: +0x180
  its entity (+0x18 the event clock, f64 s; +0x20 back to the critter;
  +0x38 the last contact point, not the player: it holds still in the air
  and while swimming), +0x15C the body centre (1 m over the feet: where
  Live places the player), +0x18C its facing quaternion, +0x210 HP and
  +0x214 max HP (i32). True on 5 snapshots [RAM], and live in USA and
  Europe; the page directory sat at physical 0xF000 in both [xemu]. The
  contact point stood still 14 m from the body through a fall in w2 while
  the body moved, read from a play session's guest RAM (Step 4.3, 2026-10-31).
- **The release.** The kernel loads the XBE header at 0x10000 and
  decodes its kernel-thunk word (+0x158) in place: guest RAM holds the
  release's thunk table address itself (USA 0x18F3A0), not the file's
  XOR-encoded word [verified xemu, sitting r1.26: v0.14-36, the vanilla
  save menu and a booted seed]. With no disc, upstream's dashboard sits
  there (title id 0xFFFF0002), and Live reads it as waiting, keeping the
  link [xemu].
- **A tracked spot is a node.** `<level>/g<G>/r<R>` is record R of the
  main graph's node vector `[graph+0x24, graph+0x28)` (one pointer a
  record; its length is the generated graph's record count: w1, w2, a3,
  f3, d1, d2 and town [RAM]). Its critterGenerator node: vtable 0x19D6B8;
  +8 the attributes, f32 k at +4k (numGenerated +0x18, numAlive +0x1C,
  numDead +0x20, maxGenerated +0x24, maxAlive +0x28, emitDelay +0x30,
  enable +0x34); +0x40 the owner sub-object (vtable 0x19D698), +0x44 its
  spawned critters' links, +0x48 the species, whose +0 is its name: the
  item the build placed there (vanilla snapshots, and a randomized one's
  town/g1/r90 holding power_ammo) [static: 0x6FBB0, 0x6F390, 0x6F570; RAM
  on 11 snapshots in 7 levels]. So the same reads check that the game runs
  the tracker's seed, against the name the writer gives the spot's item: a
  `_move` spot left its vanilla item keeps its template (a5's and w4's
  obsidians read `obsidian_move`), and one given another item takes its
  `<item>_move` name when its graph holds one. Every spot matched its
  plan in a1, a3, a5, d1, f4, life, town, w1 and w2 (USA) and f4, f6 and
  w1 (Europe) [xemu].
- **A pickup kills its generator's critter.** 0x46ED0 (the pickup
  entity's slot 1) passes a touch to 0x46FE0, which acts for the player
  only, while `critter+0x1E0 <= 0`. `heal` heals; `lpow` (power_life)
  adds the item's amount (40) to max HP and HP with no clamp
  (0x435E7-0x4360E); anything else goes to the inventory's add 0x587B0,
  which returns what it added. The pickup stays in the world, numDead
  unchanged, when nothing is added: every fuel at its cap (all_fuel), a
  fragment held (cap 1), spow 2 or mpow 1, an element at level 3 (0x58190
  clamps), a sixth key type (0x58090). Otherwise 0x41390 kills it and calls
  the owner's slot 1, 0x6FC90: numAlive - 1, numDead + 1 [static]. Seen:
  w2/g0/r1355 (power_air) 1/1/0 -> 1/0/1 in the interval the inventory's
  air level went 0 -> 1 [RAM]. Other paths into numDead (a timed despawn,
  which no pool item has; 0x2F510, an AI method; damage, 0x44640) aren't
  known to reach a pickup, so Live counts a rise only with its item's
  inventory or HP change. [xemu]: an obsidian, a key, a power, a
  fragment, all_fuel (after the fuel was lowered in RAM [placed]) and
  all_health at full HP each rose numDead with the change by the next
  running poll, and all_fuel at full fuel stayed out with numDead
  unchanged; no rise went unpaired in either sitting. power_life (a
  town vault spot, its lock opened at 10 obsidians [placed]) raised max
  HP and HP 200 -> 240 and paired as one Took, twice. A pickup needs a
  touch: the player placed (R6) onto an item takes nothing; walking into
  it does, and so does a fall onto it from 3, 8 or 12 m (upstream's
  takes were such falls [placed start]).
- **Saved and unsaved spots.** 187 of the 201 tracked spots in level
  files are on their level's save list: numDead comes back on every
  visit. The other 14 (12 all_fuel spots and town's two unbounded
  dispensers) are restored from their record on each load (0x65E50
  restores only the save list), so their numDead restarts at 0 and their
  item respawns [xemu: f4's r1540 and r1538 came back at 0 with their
  items, and r1540's obsidian was taken again; AZ-467]. a6's and f6's
  4th fragments sit in characters graphs the boss spawns; the fragment
  count alone names them.
- **Gems are read the same way** (Step R1.43, the tracker's Gems). The
  1215 gem spots (1146 gems, 69 clusters holding 3 to 21 each: 1542
  gems) are critterGenerators in their level's main graph, all but d2's
  three on its save list. A take raised its spot's numDead 0 -> 1, its
  gem's count (`emer`, `diam`, `ruby`, `sapp`) rising by the next running
  poll, and a death's Continue or a reload put numDead back to 0 with the
  rest of the level [measured: Live's own Follower replayed on the
  recorder's rows of X.92's demo and X.98's play, 33 of 33 takes paired,
  0 unpaired].
  A cluster's numDead counts its gems one a take, to its yield [measured:
  the same replay on X.78's logic-review demo, 120 takes, 44 of them from
  8 clusters, each paired, 0 false removals]. Live checks no gem's species,
  only its node's vtables.
- **Level state lives in files.** A level exit, `0x542E0(scene, 0)`,
  writes the level's save-list state through 0x52A10 into
  `z:\scratch\levels\...\<level>.sav` (device slot 0x14, 0x5BEB0); a load
  reads `z:\scratch` first, else the slot; a save (0x52A50) copies the
  scratch levels into the slot (0x5C240) and signs it (0x5C920). Only the
  loaded level's state is in RAM.
- **A death reverts every level visited since the save.** Death
  (`0x542E0(scene, 1)`) unloads without writing, device slot 0x1C
  (0x5C370) deletes `z:\scratch\levels` (0x5B300: FindFirst/Next,
  DeleteFile, recurse, RemoveDirectory), and Continue reads `inv.sav`,
  `shared.sav`, `loc.sav` and `magic.sav` from the slot [static; xemu
  rz-a saw the current level revert, RANDOMIZER_PLAN § 2.14]. [xemu]: a
  fragment taken in f4 after a save in w1, then a death and Continue:
  f4's spot read untaken on re-entry and the fragment's count 0. A
  death before a new game's first save (HP 0 [placed] in the training
  room) runs the new-game setup and loads the room again at day 0.
- **The day clock is the reload signal.** The inventory's f32 at +0
  (days; 0x55920 adds (1/30)/600 a tick) only grows in play; a reload
  sets the save's, and a new game (0x535A0) clears the inventory
  (0x57B70) and sets its clock to 0 [xemu]. Live reads a fall of more
  than a second of game time as a reload. [xemu]: a Continue's and a
  Load Game's first player tick reads the slot's `inv.sav` clock (read
  from the drive) to the bit, then +1 a tick; Live's Reload carries its
  first settled poll's clock, 1-18 ticks later (inside EPS, 30 ticks),
  so a mark taken up to about 48 ticks (1.6 s) after the save outlives
  the reload. The pause menu, a pickup popup and a dialog stop both
  clocks; the day clock runs through a between-levels movie
  (airship_trans, diskreplace_air), and an in-level camera scene stops
  neither: in the training room's intro, about 12.5 s with the player's
  input taken over (+0x30 of the input state the player tick gets), the
  tick and both clocks ran and Live read running (the scene's camera,
  vtable 0x19C2F8, over the level camera, from one run; that it is the
  room's camera node is [inferred]). A New Game's first settle is in
  `levels/training_room` at 0.0004-0.007 days (not after the 0.25 dawn
  the static reading gave), with every element at level 1, so Live takes
  a fall of the day clock into the training room on no saved slot (a
  New Game, a death there before the first save), or a session's first
  settle there, as a new game (AZ-478; seen on the fork and upstream,
  every live mark and veto dropped). A level request into the room
  before the first save runs the clock on: the same game (AZ-481).
- **The slot path.** The device's path at +0x20A is `u:\<12-character
  id>\` on a played save and empty on a new game not yet saved [RAM]. Its
  one writer is the device's constructor 0x5AFC0 (the `lea` at 0x5AFDB),
  through 0x52910, called at 0x55D41 and 0x55F68; 0x5C240 tests it for a
  `z:` drive [static]. A new game's path stays empty until its first
  save writes `u:\<id>\` [xemu]; a save made in the training room (the
  save-anywhere cheat, the only way there) writes it too, and a Load
  Game of that save keeps the slot [xemu].
- **Fragments are never spent.** The disc chains and d1's seal read each
  disc's count at 4 or more after it is placed (§ 8 above), so a held
  fragment's count never drops back to 0 [xemu: with the four air
  fragments written 1 [placed], a6's PlaceAirDisk and the diskreplace_air
  scene placed the disc, and all four still read 1 after; a6 entered
  again gave no second teleport].

## Pickups and exit triggers: what the game tests (Step R1.16e, 2026-10-16)

Why L3's goals and xemu's outcomes parted in R1.16d (AZ-483). USA VAs;
[static] is capstone over the vanilla `default.xbe`; [L3] is the game's
own code in L3 whole steps from the private store's R1.16d snapshots;
offsets only, no positions.

- **A pickup is touched in the player's own tick.** 0x8C520 (called at
  0x8C3B7 in the player update 0x8C230; it skips a player with HP 0)
  queries the world's collision tree (`[[critter+0x154]+0xAC]`, 0x60870)
  with a 1 m ellipsoid round the body centre (critter+0x15C; radii
  `[0x1980BC]`, 1.0) and sends the nearest hit a type-2 message (0x8C61D)
  with the player's critter as the toucher. A critter's shape test
  0x418B0 (vtable 0x19FC08 +0x9C) takes the query when the body centre
  lies in the ellipsoid of horizontal radius R = r · pcr / cr + 1 and
  half-height Z = r · aspect + 1 round its bounds' centre (vtable +0x80,
  the middle of +0xF8..+0x10C), where r = collisionRadius × scale
  (vtable +0x90: species +0x18 × critter +0x188), aspect the species'
  +0x1C and pcr its +0x20 (`critters_engine`'s `collisionRadius`,
  `collisionAspectRatio`, `playerCollisionRadius`, read by 0x49480 at
  0x497FC-0x49881; defaults 1.0, 1.0 and collisionRadius). The message
  goes 0x43210 → the entity's slot 1 0x46ED0 → 0x46FE0 (RE_DATA "Live
  pickups"). No pickup species sets `playerCollisionRadius` (37 other
  species do, townsfolk among them), so a pickup's R = r + 1. Obsidian
  and the gems: R 1.45 m, Z 1.9 m; the element power-ups 1.45 and 1.45
  (power_life, the staffs and ammo 1.05); the fragments 2.2
  (frag_water_1 1.8, frag_life_4 2.0, frag_fire_4 1.2, frag_air_1 6.0);
  the keys 1.1-5.0 [static; L3: placed at offsets from the centre, 7
  items of 6 species, every offset with the metric at most 1 taken on
  its first tick and none above it].
- **The query's two radii are separate args** (Step 2.133). The MOV EDX
  at 0x8C553 (Europe 0x8C503, `[0x19A264]`) loads the one constant and
  pushes it twice: collision_sweep's arg 6 (the push at 0x8C55F) widens
  the box in x and y and becomes the shape test's horizontal term
  (0x60913-0x60966, the struct's +8 that 0x4195E adds), arg 7 (0x8C55E)
  the z term (0x60941, 0x60975; +0xC, 0x41968) [static]. X34
  (`player_model/touch.c`) takes that window for a worn body's size.
- **An item rests where it falls.** It spawns at its generator's point
  and falls onto the surface below, its bounds' centre hz = r · aspect
  over it, unless its bottom already reaches that surface [L3: 4 items
  of 4 species within 4 mm; a key gear's and a key fuse's centre sat
  0.5 m over the point, not fallen: unexplained, not modelled].
- **An item exists only in its room.** Its generator spawns it (0x409C0
  on the generator's species) only while the player is in the
  generator's cell and near it [L3: with the player placed 6 m over it
  in its cell it spawned within 8 ticks, 40 m over it never]. So
  player-tick L3, which runs no generator, can't take an item at all,
  and a player placed (R6) with the cell he stood in before (the
  snapshot's) never sees one in another cell: in R1.16d's replays 60 of
  the 66 items xemu didn't take never spawned [L3, each replay's string
  and 150 neutral ticks in whole steps]; the same string placed in the
  item's own cell took it in the settle (AZ-488).
- **A container holds in only what the game can't touch through it**
  (Step 4.3 contained items, AZ-834). An ice or acid block, a force
  field, a gem rock or a gate's region (derived `enclosed_by`) is no
  wall to the touch, and the randomizer's writer keeps each location's
  vanilla point, so an item wider than the vanilla one there was taken
  from beside the block (w2/g0/r1359's IceBlock_01: frag_air_3, R 2.2,
  where the obsidian's is 1.45). The generator layer gives a species the
  image holds once, on a contained spot whose touch isn't inside the
  vanilla item's (both resting on one floor: Z <= Zv and R² / Z <= Rv² /
  Zv), that item's `collisionRadius` (at its own scale) and
  `collisionAspectRatio` in `critters_engine`: it touches, collides and
  rests as that item did (a fragment's centre 0.3 m lower), its model
  unchanged. A species held more than once keeps its own touch (the
  widest the fill puts in a container, the fuels' 1.56 m, is inside the
  1.8 m the blocks hold). In xemu the fragment was taken from 11 of 14
  points round w2's block before and none after, and once the ice
  melted; frag_air_1 (6.0 m) in f1's acid block from 10 of 13, even 14 m
  below it, before and none after, and once it dissolved [xemu, the
  research's probe].
- **One spot's item needs the vanilla item's reach** (Step 4.3az835,
  AZ-835, D1041). a1/g0/r1102 is frag_air_1's, R 6, Z 6, 8.5 m over its
  platform: a wind (Vac2, then the chamber's push fields, where air
  control is 0.1 x) carries the player past it, 4.6 m across and 3 m
  under on the first pass, and on up to the chamber's one-way roof, and
  items there stay at their point instead of falling [xemu]. Seed 1's
  obsidian (R 1.45, Z 1.9) was taken on 1 input of 87. Obsidian has 99
  other copies, so its row can't change; the node names a spare row,
  `small_chromatic_fuel`, which no location, enemy drop or other cell
  names: every cell but its name and the reach's is the placed item's,
  the strings by reference, so config.xbr doesn't grow, with
  `collisionRadius` and `collisionAspectRatio` at frag_air_1's touch and
  `useCenterBasis` as frag_air_1's, 1.0. That cell moves the touch: an
  item with it set has its centre at the point, one with it empty
  collisionRadius x aspect over it (obsidian 0.3 x 2 = 0.6 m; 3.33 x 1
  with the reach, which the pass then takes 23 ticks later) [xemu, frag_air_1,
  obsidian and both rows read]. `critters_sounds` has no such row, so that obsidian
  lacks the hum of within 3 m [from the table; xemu's at volume 0].
- **An exit's trigger is touched at the body centre.** The player's
  input build calls the volume query 0x60BD0 at 0x85587 with the body
  centre (critter+0x15C) as a point: the objects whose tree bounds hold
  it (0x60700), each tested through vtable +0xA0 and sent a type-2
  message when it passes (0x60D6C). A platform's test 0x79D30 (its
  collision word must hold 0x20, and the toucher's mask +0x168 its
  +0x278) takes the point into the platform's frame and asks its `tern`
  0xD2A40, which casts a ray straight up (10,000 m) and returns 1 when
  the first triangle it meets faces down ((v1 − v0) × (v2 − v0) has
  z < 0: the meshes' winding), so the point must lie inside the mesh.
  The message sets the node's `touch` (attribute 5) to 1.0 at 0x7A167
  and schedules its reset 1/30 s on (0x1981B8, the reset 0x7A280)
  [static; the box centres of 47 of 49 exit triggers in 10 levels hit a
  face pointing down first]. So a goal of the feet in the column under
  the mesh (2 m below its lowest point) took spots the game never
  touches: in R1.16d's 52 exit replays the body centre was inside the
  trigger on some tick of every one whose exit loaded during the string
  or the settle, and of the 12 that never loaded only on a1/g0/r2655's
  (its two-touch timer) [L3, each replay's own mode].
- **The fire is the levelSwitch's own.** The node graph (0x663B0, in the
  scene tick) runs the gate and calls 0x6F050 with the levelSwitch in
  EDI: it copies its movie (+0x18), level (+0x1C) and spot (+0x20) into
  0x38D320 and posts the request; the load follows. L3's whole steps run
  it: on 2 replays whose exit loaded in xemu's tail, L3 fired 36 and 70
  neutral ticks after the string where xemu loaded 37 and 72 ticks after
  it [L3]. A gate's switch and timer (a1/g0/r2655:
  `currentTime{>=8}`, 8 s) only whole steps advance.

### Where a placed item stands: what a move writes (Step 4.41b, 2026-11-13)

[static, unverified in game until its sitting] USA VAs, capstone over the
vanilla `default.xbe`; counts over the USA image's level files, no
positions.

- **A spawn stands at its parent's matrix times its gen point.** The
  `critterGenerator` loader 0x6F570 copies the record's gen points (+0x2C
  count, +0x30 ref, 12 B each) as they are into the generator's own list
  (0x6F6A0-0x6F6CB), and 0x6F960 places each spawn at the parent's world
  matrix (the parent object's +0x30, the identity with none) times the
  point at its cursor (0x6FA0E-0x6FA5C). The generator's own
  `localPositionX..Z` attributes are read by neither, so a write there
  moves nothing.
- **So a move writes the parent transform's translate.** The `xbr`
  operation `move` (`edits/xbr.py`) writes the three f32 `translateX..Z`
  (the parent `transform`'s attributes 1-3, 12 B, which the transform
  loader 0x67F80 reads into its local matrix), found by attribute name.
  All 3,132 generators on the USA disc have a `transform` parent that
  parents nothing else, at inherit mode 0, so the move carries that one
  generator and all of its gen points (140 have more than one); for the
  ones whose ancestors are the identity (training_room's fuels, say) the
  translate is the item's world position. 10 have a translate a link
  drives, which the game sets again as each node starts dirty: a move of
  one is refused.

## A creature fx graph's links and its blast dome (Step 2.145, 2026-10-21)

- **Links.** A node record's outgoing links are 24-byte entries in its
  list at +0x10: {weight f32, curve, factor f32, source plug u16, pad,
  destination plug u16, pad, destination record u32}; a plug is the
  index of the type's attribute in the XBE's node schema. The graph tick
  0x663B0 walks each record whose dirty word (+0x10 of the live record)
  is set, clears it, calls the record's update (vtable +0x14) and then
  walks its links: a destination plug 0xFFFF marks the destination dirty
  (+0x10 |= 0x80000000); any other writes curve(source × weight) × factor
  (the curve 0xD8300; none, the product) into the destination, only when
  it differs [static].
  So a disabled timer's out-links still run after its update, and a
  linked currentTime holds: on all 27 ticks of beamlord v3's nova timer2
  read 0.4583 × the switch's z within 0.00001, enable 0, with no free
  run [measured, sitting 2.145 S-E3].
- **The airship's blast dome** (`characters/balthazar_airship/fx/fx_default`,
  64 records): [21] `blastdome`, a transform under [12] the aim marker
  `m_balth_lightning`, inherit mode 0, s (0.394, 0.394, 0.252); [22] its
  platform, mesh rdms 108 (120 vertices, 56 triangles), a bowl of radius
  0.5 with its rim at local z 0 and its pole at −0.5, no collision
  (+0x24 = −1); drawn at his hands as a disc up to 1.32 m across facing
  down the beam. [20] `timer2` (start 0, stop 1.25, rate 1, repeat 1)
  free-runs from the instance's birth and drives [21]'s scaleX and scaleY
  through two 28-key curves (0.394 at 0, 2.637 at 0.458 s, then jumping
  between 0.7 and 3.0 to 2.5 s), so nothing of an attack sets the dome's
  size. [16] `m_balth_lightningswitch` (the clip's switch, its
  translateZ) has three links: [17] the stream's emitRate (weight 100, no
  curve; [17]'s stored rate 0), [22] gameVisible and [24] the bolts'
  enable (weight 100, a 0 → 1 curve over 0..1: on from z 0.01)
  [data]. Beamlord's v3 keys the dome on the switch
  (Modkit's `PATCHES.md` § beamlord): in sitting 2.145 its record read a
  2.801 m radius and gameVisible 1.0 at z 1, yet no dome drew on the
  player, as the unkeyed one on main draws none (AZ-631).
- **What the dome draws** (Step 2.146). Nothing in the engine draws an
  NPC's fx and not the player's: the platform's render object is
  collected in the player's cell every frame [probe].
  gameVisible is a float opacity scale: the platform object passes it
  (0x79560) to each sub-object's setter 0xC5DA0, which stores it
  unclamped at +0x120 and below 1.0 sets the translucent category bit
  (|4); the sub-object draw 0xC3660 skips at lod × gameVisible ≤ 0 and
  otherwise draws at gameVisible × the distance fade [static]. The
  material's own opacity multiplies that, and the dome's material (gshd 95
  row 0: blend 5, opacity 0.1, alpha reference 0.1, its one texture surf
  101, 128 × 128, mean grey 37 of 255) caps it at a tenth: the gameVisible
  link's curve clamps at 1.0. Only [22] draws rdms 108, and only rdms 108
  names that row (spideyzar's blast dome [84] has another material, also
  at 0.1). Every rdms in characters.xbr (289) and fx.xbr (866) has black
  vertex RGB, the visible blend-5 effects included, so the vertex colours
  are not the cause [data]. How the draw combines the material's opacity with the
  sub-object's (0xD7A80/0xD7C60) is unread; blend 5 is (SRCALPHA, ONE),
  an add (Step 2.155e, § "How an fx material blends" below).
  Beamlord's recipe sets the row's opacity to 1.0 in place (`material`,
  Modkit's `PATCHES.md` § beamlord), and the dome draws: a flat radial
  starburst of white streaks on the floor round his feet, about 2.8 m
  out, not a bowl round him (5.4-11.9 % of the frame against main's at
  clip 0.43-0.60 s, its box 619 → 738 px wide as the radius reads 2.28 →
  2.80 m; main's 0.1 dome no pixel); at the beams' switch 0.02 it adds at
  most 10/255 on 0.2 % of the pixels [measured, sitting 2.146 S-E1,
  S-E2].
- **Spideyzar's funnel on the player** (Steps 2.145, 2.146). Played on
  the worn air elemental through `critter_play_fx` (0x440F0) into the
  hit-fx slot (+0x23C), spideyzar's [220] `funnelShape` and [225]
  `cloudShape` pSystems (updateRate 1.0) are fed and stepped every tick:
  3 and 4 particles born a tick through the whirlwind trigger (69 and 92
  at its end), [225] losing 4 a tick after it, [220]'s pool moving
  0.18-0.22 m every tick; so updateRate is not their step period (2 to 30
  set in RAM give byte-identical frames). They draw faintly (0.10-0.81 %
  of the frame) and strung along the gust's path (the pool 26 × 27 ×
  5.7 m at the arrival + 1.5 s), never as a funnel round the moving box
  [measured, sitting 2.146 S-D1]. A
  node copies its record's attributes per instance (0x65880); writing
  updateRate 30 into the player's copies and marking them dirty hung the
  game 2 of 2, spinning in a tree walk at 0x326C0 some 27-40 ticks after
  the write landed, cause not established [measured]. Step 2.146 took X35 out (AZ-639).
- **Balthazar's attack_3 stream** (Step 2.146). The switch [16] feeds
  [17] (pEmitter, 100/s at z 1) into [14] (pSystem, renderer [11]): on a
  plain balthazar own build [14] holds 6 / 30 / 50 particles at clip
  1.00 / 1.28 / 1.52 s, collected every tick, its far edge 2.9 / 7.0 /
  10.5 m ahead (X.29's build the same), yet it shows only as 5-6 violet
  blobs within 1-2 m of his hands. Its pool reaches 1-3 m under the floor
  within 0.3 s of the switch (the emitter 2.94 m up), so the far
  particles most likely draw under it [inferred] (AZ-643). That lead,
  and Step 2.153's G1 ("[17]'s lift moves the far edge, not the lowest
  point"), read the pool's cached bounds (+0x100), which 0xD4840 builds
  as the box of the particles' pool-local positions (0x24 bytes each,
  +0xBC..+0xC0) grown by half the largest sprite, then boxed through the
  pool's matrix (0xD490D): its lowest corner is the newest particle's
  birth height and can't show a tilt. velocityBaseZ is applied: 0xDA010-
  0xDA09D builds each axis as base + rand(±variance) and 0xD8B60 turns
  position and velocity through the emitter-in-pool matrix (0xD9E00:
  the pool's inverted, times the emitter's) [verified static 2026-10-22]. The look's cause is the renderer [11]: born
  about 2.4 m up at his levitating hands (attack_3 lifts them to
  2.85-2.92 model units) and pitched down 20 degrees, each sprite dims to
  (0.22, 0.04, 0.28) by age 0.4 s (blend 5) while it swells to 1.1-1.9 m,
  and [14] steps its pool at 15 Hz (1.2 m apart at 18.2 m/s), so only the
  first 1-2 m reads [inferred from the data; Step 2.153b brightens [11]
  and steps [14] at 30 Hz in his own build; seen in xemu, sitting
  2.153b: a dotted line of bright violet sprites about 0.5 m apart from
  his hands toward the target, its 30 and 50 particles reaching 5.94 and
  9.41 m at 1.25 and 1.5 s, where main's 3-4 faint blobs stay at his
  hands; no band (AZ-643)]. A pSystem not
  collected that frame (the player outside its cell; the airship boss
  out of view) held no particles, so one likely steps only while
  collected [inferred]. The bolts ([24] → [37]) are
  what shows of the beam; their dotted zigzags fanning into the floor at
  the target are the "particles at the very end of the range" of the
  owner's 2.147 note [measured, sitting 2.146 S-S1, S-S2].
- **So** nothing in the draw path tells an NPC's fx from the player's:
  the player's dome, stream, bolts and funnel wisps all draw, and what
  decided each was data (the dome's material opacity, the funnel's
  spread, the stream's path into the floor).

## A critter's fx instances: spawn, bind, detach, end (Step 2.149, 2026-10-22)

[verified static 2026-10-21/22: `python -m devkit re xbe fn|dis|calls` on both
vanilla images; the attribute indices from the XBE's node
schema]

- **Handles and instances.** A handle is 12 bytes {+0 the instance's
  handle-list head (instance+0x20), +4 the next handle, +8 its flags}; a
  critter has three: +0x230 its `fx_default` (0x43700 at init), +0x23C the
  played or hit fx (`critter_play_fx` 0x440F0), +0x248 its `*/fx/...` one
  (0x437A0). `fx_instantiate` (0x649E0, Europe 0x64990; nine stack
  arguments, RET 0x24: handle, key, world, cell index, flags, bind
  interface, 0, 0, 0) first releases the handle (0x64CE0: flags bit 0 the
  old instance's stop 0x63440, bit 1 its detach, 0 an unlink alone), then
  allocates the instance, binds it and runs its first tick (the graph
  loaded, state 2 at +0xA0, unless the load defers to state 1) and links
  the handle with +8 := flags. `critter_play_fx` passes flags 1, the
  world (+0x154), the cell's index ((+0x158 − [[world+0xD4]+0x28]) / 0xB4,
  0xFFFF unplaced) and the bind interface +0x170. Instances outlive
  handles: nothing bounds how many a critter has alive.
- **Bound.** Each instance tick the two bind sets copy the critter's
  runtime markers (by name) into the bound transforms' attributes 1..9,
  dirtying only what changed; a node follows its marker one tick late, no
  smoothing. Particles live in their pSystem's local space (born at the
  emitter's place over the system's inverse world matrix, drawn with the
  system's world matrix), so a system under a bound marker carries its
  whole cloud with the marker (the air elemental's `CompressedAir` [5]
  under `m_turbulence`), one under the root stays in the critter's frame.
  A pSystem's components are its list at +0x30 (count i32, a
  self-relative ref at +0x34 to u32 record indices).
- **The records' pass** (0x663B0): only a record whose dirty word (+0x10)
  is set runs its update and its links, and a link writes its target only
  when the value differs (setting bit 1 << plug). So a write to an
  attribute no link targets sticks, and on a detached copy, whose bound
  transforms are never dirtied again, a write to a linked one sticks too
  (unless a timer upstream dirties its source).
- **Detach** (`fx_instance_detach` 0x634B0, Europe 0x63460; ESI the
  instance, plain RET, EAX, ECX and EDX clobbered): both bind sets
  unlinked from the critter's interface list and emptied (0x62860); every
  node keeps its last transform, the instance ticks on where it is,
  emitters keep their rates, timers run; deferred (bit 0x10000) in state 1.
- **End.** Bit 0 of instance+0x2C: the instance skips its tick; the scene
  tick's sweep (predicate 0x55900 `test [inst+0x2C],1`, at 0x5634D)
  deletes it (0x63170: the unbind 0x62510, the records 0x66280, then
  0xA4420 zeroes +0 and +4 of every handle on its list). The level
  teardown 0x542E0 deletes every instance in one loop.
- **Attributes X38 writes.** pComponent (pEmitter, pBurstEmitter) and
  pSystem `enable` 4, emitters' `emitRate` 5, platform `lodVisibility` 0,
  `gameVisible` 10, `gameSolid` 11, `damage` 17; a node's attributes are
  f32 at [node+8], its type's count at [[node+0x14]+0xC]. A pSystem's
  `enable` 0 blanks its particles at once: its update 0x6C400 copies
  enable > 0 into the pool (+0xFC), and the pool's update (0xD4380) and
  draw (0xD44AB-0xD44BF) skip a pool where it is 0. A platform's mesh
  draws only while `gameVisible` × `lodVisibility` > 0 (0xC3128-0xC313F,
  0xC3681-0xC3698): the platform update 0x6ABB0 forwards both (dirty bits
  0x400 and 0x1) to each render sub-object (vtable 0x19C8D0), whose
  setters 0xC5DA0 and 0xC5DE0 keep them at +0x120 and +0x124 (1.0 from
  0xC26D0). X38 (`src/azurkit/tools/characters/player_model/fx_ring.c`) plays each ranged attack's effects in its own bound
  instance (flags 0) and detaches it at the next clip change.
- **A detached copy's switch write fires its links** (Step 2.155, D434;
  [static,
  0x663E6-0x664A5; measured: Step 2.155's sitting R8, the detached
  copy's trigger 0.4375/0.75/1 at +0.2/0.4/0.8 s, its funnel's particles
  from +5 ticks, its emitters' rates 0 again at +1.833 s]). The records
  pass 0x663B0 runs a node's out-links only while its dirty word (+0x10)
  is non-zero, and writes a link's destination only when the value
  differs; once detached, an instance has no bind left to overwrite a
  bound transform (0x62860 empties its bind sets). So X38's stand copy writes
  spideyzar's [34] `m_whirlwind_trigger` translateZ (attribute 3, dirty
  bit 3) by value and his graph's own links do the rest: the seven
  funnel and cloud emitters' `emitRate` (35 z) and group1's scale
  (0.5 + 0.5 z). [34] is no link's destination and holds no child; the
  destinations are pEmitters and a transform, so no pSystem attribute is
  dirtied (the pSystem handler's 0x60 path, 0x6C400, where Step 2.146's
  updateRate write hung, is never reached). X38's drain row (Step 2.153c,
  AZ-653) closes the same way: its detached copy's [42]
  `m_lifedrainswitch` translateZ := 0 at the window's end (dirty bit 3),
  and its links take the stream [44]'s `enable` and the box [46]'s
  `damage` to 0 (a pEmitter and a platform: no pSystem attribute); the
  pool [2] keeps its enable, so its particles age out [static; not yet
  seen in xemu].
- **What moves a particle** (Step 2.155d; [static: the vanilla USA XBE; a stdlib model
  of these steps reproduces Step
  2.155c's measured per-height radii and speeds within about 0.3 m and
  1 m/s]). A pSystem's components are its list at +0x30/+0x34 (u32
  record indices). Births (0xD9DE0): position the emitter's
  ± `positionVariance`, velocity `velocityBase` ± `velocityVariance`,
  through the emitter's matrix (its local x scaled by its transform; its
  origin its pivots', not its translate). Forces (the pool update
  0xD4380: each component's +0x10, then its +8): a pVortex (0xDC850)
  turns a particle about D, the vortex node's local Z through its world
  matrix times the pool's inverse, not normalised, so |D| is the
  vortex's world scale; with |D| = 1 a particle keeps its orbit at any
  speed, with |D| > 1 the grip weakens with height and the velocity
  turns against the orbit, so a stream swings out, in and out again and
  flies off its tangent (spideyzar's clone at x 1.25 showed it as an X).
  pGravity (0xDC010) adds mag (G − P) dt / (|G − P|² + 0.001); a pSink
  (0xDCE90) culls past `maxAge`; a pool holds at most 1000. A
  `pRendererB` with `useDepthSort` set sorts its pool by view depth
  before drawing (0xDE000 tests bit 2 of the renderer's +0x54 flags and
  calls 0xDDD00, which writes each 36-byte particle's view depth at +0x20
  and sorts). A
  timer's link onto a
  transform's rotateZ spins an emitter group: the game does it 26 times
  (frag_air_1's `EffectSpin_timer` onto `Emitter_Group1`).
- **How an fx material blends** (Step 2.155e, D525; [static: the vanilla
  USA XBE]). The blend switch 0x9DE00 (its one caller
  0x9E808, after `CreatePixelShader` on the same record) turns blending
  off where the record's +0xF0 is 0, else sets D3DRS_SRCBLEND (0x40344)
  and DESTBLEND (0x40348) through its table at 0x9DFFC: 1 (DESTCOLOR,
  ZERO), 2 (DESTCOLOR, SRCCOLOR), 3 (ONE, ONE), 4 (SRCALPHA,
  INVSRCALPHA), 5 (SRCALPHA, ONE), 6 (ONE, INVSRCALPHA). That a `gshd`
  row's blend is that +0xF0 is [inferred] (the census: `Glow_s` 3, the
  force hits 5, the `Splatt_s` decal 4), and xemu agrees [measured
  in its rounds 2 and 3]: spideyzar's blast dome re-meshed as the
  air elemental's funnel greys what it covers on blend 4 and lays a
  pink glass over the floor on 5; on blend 4 the mesh a driver hid by
  lodVisibility 0 drew solid black (its alpha kept, its colour 0); a `pRendererB` set to `blendMode` 4 drew
  each puff as an opaque white block, its texture's alpha edge lost
  (round 3's candidate M). The dome's one LOD switches at FLT_MAX, so
  its lodVisibility stays 1 at the camera's farthest.
- **A clone's entries load at their first draw, one a frame** (Step
  2.155g, AZ-690; [static: `python -m devkit re xbe fn 0x9E630`, `0x9D270`,
  `0xA6860`, `0xA59F0`; measured: xemu, PC hooks at 0x9E6AD and 0xA68CC
  and the run descriptors per tick]). Every entry an fx
  clone appends is a run of its own (page-aligned,
  `toc_scan.runs`), built and read only when something looks it up. In
  play [0x1BF59C] is 0, so the draw's lookups go through 0xA6860, which
  starts the run's read (0xA59F0 with EAX 1: 0xA4C00, 0xA5480) and
  returns 0 until it is loaded. A mesh's material apply 0x9E630 binds
  each stage's texture from 0x9D270 (a list's frames each looked up
  again), and a stage with none is drawn untextured (0x9E6DA marks it;
  0xD7C60 draws anyway). So the air elemental's funnel mesh, drawn
  first at its let-go, asked for its `rdms` and push buffer that frame,
  its texture list the next and the list's texels the one after, and
  drew its first two presents untextured: on blend 4 black, its alpha
  kept, over the floor (luma 29/16 against 58/51 under it); its later
  gusts, the runs still loaded, drew grey at once. A platform drawn
  while its copy is bound loads them early: X38 draws a stand's
  trigger-shown platform at gameVisible 1/1024 once the bound copy's
  crossfade is over (a write at its spawn tick was taken back two ticks
  on, by the trigger's link as the markers blend [inferred]), too faint
  to pass its alpha test, and the four runs are in before the let-go.

## fx clones, grafts and shader records (Step 2.157, 2026-10-22)

Read for D443/D446 ("duplicate any effect, material or texture under a
new name bound to one body ... and author new ones from templates";
Step 2.157's read, design and critique).

- **A copy is bytes plus rows.** Every cross-resource field is a TOC
  index the trailer's relocation table lists; the run loader 0xA55F0
  adds the archive's slot base to each when its run loads, a handle
  [static]. Everything else inside a node payload is self-relative: all
  34,693 decoded references of the 226 fx graphs land inside their own
  payload [data]. Every relocated field of every fx graph is one a record
  type owns (a platform's LOD pairs and `tern` +0x24, a `pRendererB`'s
  and a `shader`'s +0x18, a `stereoSound`'s +0x18, a `soundEffect`'s and
  a `polyTrail`'s +0x1C) or the header's ndbg (+0x1C) [data: Step 2.157's
  census, `fx_edit.owned_fields`].
- **What graphs share.** No `rdms`, `pbrc`, `pbrw`, `tern`, `ndbg`,
  `gshd` or `sprv` is reached by two named graphs in either archive;
  only textures (`surf`) and fx.xbr's sounds are; every `sprv` has one
  `gshd` referrer [data: the critique's `referrers`]. So a clone
  (`src/azurkit/tools/characters/fx_edit.py`) shares the textures and copies the
  rest, and a shader edit never writes another graph's material.
- **An effect record names its graph by key.** Type `effect` holds the
  graph it loads as a (length, self-relative) string at +0x1C (the
  boulder's fx_default [3] `breakEffectShape`:
  `characters/bosses/boulder/fx/fx_boulder_break`, 45 characters), so
  `fx_edit`'s `graph` edit points a clone's effect at another graph by
  writing the new key over that string with its length, nothing grown
  (Step 2.159b: the thrown rock's and vase's break, seen loaded in xemu
  in the B0 probe).
- **Shader records drive a material's animation.** Type `shader`
  (attributes texture1-4 CurrentFrame / FrameRate / Scale / Rotation /
  TranslateU/V / URate, the lighting colours, ShaderAlpha, alphaRef, four
  constants): +0x18 a relocated `gshd`, +0x1C its row (0, 1 and 3 on gshd
  1602; 2, 3 and 4 on gshd 68 and 98), +0x20..+0x2C four -1 words (35 of
  35). The electric shield's `StaticField_s` (fx_shield_electric1 [5])
  plays its row 0's two textures at 5 and 10 frames a second, tiled 5x
  and 2.5x, ShaderAlpha 0.165 (the row's own opacity), and a
  `randomNumber` ([4]) turns texture 2 by -30..30 degrees every 0.067 s;
  so a frame list's rate is a shader's, where the graph has one
  [inferred], and a graft of the mesh alone would draw the textures
  frozen and 5x coarser [data: Step 2.157's design].
- **Grafts.** {9, 12, 5, 4} of fx_shield_electric1 (`StaticFieldBase`
  inherit 3, `StaticFieldBaseShape` its platform, the shader, the
  randomNumber) are closed under their links; {5, 7} of fx_force_hit_1
  (`ForceGlobe`, inherit 0, and its platform, a full sphere of radius
  1.15; its gameVisible never above 0.3 in vanilla, so it always draws
  with 0xC5DA0's translucent bit) likewise [data: Step 2.157's design
  and its critique]. A platform also holds two class strings
  and its descriptors a sub-bounds block, and a transform a child list,
  each self-relative (`docs/XBR_FORMAT.md` § "Level node graph"), so a
  graft appends the donor's whole node payload as one block and remaps
  only record indices and rows (`fx_edit.Clone.graft`; the named grafts
  are `src/azurkit/tools/characters/fx_templates.json`'s since Step 2.167a;
  `force_globe` stays for beamlord's dome).
- **Inherit mode 3** (0x6880A) is decoded: the anchor where the parent
  puts it, the axes the top camera's (`docs/XBR_FORMAT.md`); the game's
  shields (30 mode-3 transforms in fx graphs) face the camera so. A
  shield's own translateZ didn't raise it, so its height comes from its
  parent: beamlord's sits under his `spine_2` [observed xemu, sitting
  2.157; which frame the
  node's own translate runs in is unread].
- **Who wears the airship body.** Only the `balthazar` species wears
  `balthazar_airship` (spideyzar wears `balthazar_spider`): NPC Balthazar
  and the airship boss are one critter, at levels/air/airship [data: Step 2.157's design]. Since Step 2.157 his graph stays vanilla in a
  beamlord build: the player plays `characters/balthazar_airship/v/fx/
  fx_default` (X40, `docs/RE_XBE.md` § "A body's default fx").
- **ShaderAlpha wins over the row's opacity** for the electric shield's
  StaticField_s: E3 dome builds with ShaderAlpha 0.7 and the material
  row at 0.165 or 0.7 drew byte-identical pictures from behind and the
  side, and the row at 0.7 under ShaderAlpha 0.165 drew as faint as the
  donor (0.001-0.003 % of the frame past 24, against 3.6-4.2 %), so an
  E3 shield's opacity writes ShaderAlpha alone since Step 2.167f (AZ-719)
  [measured xemu].
  The airship dome's gshd 95 row 0 (AZ-631), whose own opacity capped it,
  has no shader record. Unread: the 23 non-square textures' chain rule.

## Particle grafts and the effect record (Step 2.167a, 2026-10-23)

Read for D538 (effects templates).

- **Where each type's loader is.** The node factory 0x721B0 fills the
  type table at 0x1BCDE0 with (name, factory); each factory allocates the
  node and installs its vtable, whose slot 1 is the type's loader and
  slot 2 its link loader (0x658F0 unless the type adds to it) [static].
  So every record-index field a type holds is read in one of the two:
  the DAG parent (+0x18, 0x67E70's pattern), the links, a pSystem's
  renderer (+0x20) and components (+0x30 list; slot 2, 0x6C210, which
  stores each component's object in the pool at +0xD0 and the renderer's
  at +0xDC) and a pBurstEmitter's targets (+0x1C list; slot 2, 0x6D580,
  into the emitter's +0x118 list). The emitters, sinks, forces and pNull
  read their parent alone; a pRendererB its texture (+0x18); a timer
  nothing; a combiner its input count and function; a polyTrail its
  parent, its material (`gshd`, +0x1C) and row (+0x20) and a u16 cell
  list, as a pSystem does (+0x28: the cells it draws in [inferred], the
  instance's cell added). `docs/XBR_FORMAT.md` § "Level node graph" has
  the layouts; `fx_edit.index_fields` reads them.
- **Census.** In the 226 fx graphs every pSystem's renderer is a
  pRendererB (421 of 421) and every component a `pComponent` (1,701);
  the burst targets are 135 pNulls and 2 pEmitters; no u16 cell list is
  used (471 records); no two lists share storage; no fx graph has a save
  list [data]. So a graft (`fx_edit.Clone.graft`) takes the particle
  types, timers, combiners, polyTrails and effects: it remaps their
  lists and refuses a set that leaves one out (a pSystem without its
  renderer or a component, a burst without a target), or a record that
  holds a cell list. An `effectControl` (its `forceUnload` unloads the
  whole instance) still doesn't graft.
- **Binds.** All 770 bound transforms of the fx graphs hold 1 at +0x1C
  and a bind name equal to their record name, NUL-terminated at its
  length; the loader 0x67F80 copies the name at +0x20 (0x680D5) when
  +0x1C isn't 0 [static, data: `bind_flags_usa`].
- **The effect record** (vtable 0x19D5D8; update 0x70900). When its
  `loadEffect` (attribute 4) turns non-zero it instantiates the graph
  its key names (0x7099D: `fx_instantiate` with its handle at +0x2C, the
  key copied at load into +0x28, the graph's world, the record's cell or
  the instance's, flags `autoStop` | `autoDetach` << 1, its bind list),
  adds 1.0 (0x1A250C) to `fxTotal` and sets `fxActive` to 1 when the
  record has a link on that plug (0x708B0); turning
  0 releases the handle (0x64CE0); `stopEffect` and `detachEffect` stop
  (0x64D50) and detach (0x64D80) it. Ten of the twelve fx effect records
  name a graph of fx.xbr or characters.xbr; the airship's two name
  `characters/Balthazar_airship/fx/fx_fireball`, which neither holds
  [static, data].
- **A polyTrail's width is in its node's units** (Step 2.202, M11)
  [verified static 2026-10-27: `xbe fn 0x718C0`, `xbe fn 0x7C1A0`]. Its
  factory 0x76E60 installs vtable 0x19D4E0, whose slot 5 (0x718C0) copies
  the attributes into its trail object (node +0x20): lineLength x 0.5
  into +0x254, maxDistance +0x258, maxAge +0x25C, the colours and alphas,
  and on a matrix change the node's world matrix into +0x1F0 (rows
  +0x1F0, +0x200, +0x210, +0x220: x, y, z, translation). 0x7C1A0 lays each
  sample's two ends at the translation -/+ 0.5 lineLength x row z: the
  segment scales with the node's world scale. So W6's power heads, whose
  map scales each trail's transform by the head's size s, draw a trail
  of 0.55 x s with lineLength kept (0.55 x s squared when it took the
  size too, Steps 2.182-2.202).

## History

Until REORG_PLAN Step 3.3d (2026-10-10) these notes were sections of
`docs/LEARNINGS.md`; `git log -- docs/LEARNINGS.md` shows their
earlier history.
