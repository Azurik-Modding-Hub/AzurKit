# Randomizer database format, version 1

- **What this is.** The file layout, fields, id scheme and requirement grammar of the randomizer's logic database, `src/azurkit/tools/randomizer/data/`. The planner's loader (`src/azurkit/tools/randomizer/planner/loader.py`) implements it, its solver (`solver.py`) reads it as §15 says, `python -m devkit rando check` runs it ([`devkit/rando/README.md`](../devkit/rando/README.md)), and Step R1.1's `rando db-extract` writes its generated half (`RANDOMIZER_PLAN.md` §4.2). Modkit's text (Step 4.13c brought it): its steps, decisions and records are Modkit's, its `azurik-mod rando VERB` is `python -m devkit rando VERB`, its paths AzurKit's (the derive and the authoring are `devkit/rando/draft/`, the shipped draft `src/azurkit/tools/randomizer/draft/`); `RANDOMIZER_PLAN.md`, `TOOLS.md` and `SCRIPTS.md` are Modkit's, and the database tools' fixtures and benches (`tests/rando/`, `scripts/rando_*.py`) arrive with their own lane.
- **Status.** Version 1, frozen at Step R1.4 (2026-10-12) from the R0 draft 0 (`$RP/db-draft/FORMAT.md` at `$RP` commit `4b8f3f3`, which includes D144's settings, `1e11583`, and Q280, `4b8f3f3`). §14 lists every change from draft 0. Every file carries a `format` key ending in `/1`, and the loader refuses any other. Steps R1.5-R1.7 amended version 1 additively before it reached `main` (§14); since it landed, an additive change, one every older file still loads under with its meaning (Steps R1.8, R1.11c, R1.31, R2.18b, §14), keeps version 1, and any other change bumps it.
- **`$RP`** is the R0 evidence repo, `randomizer-plan-2026-10-10/` in the private evidence folder (`$EV`; local git, with a private backup, D127, D140). A path written `$RP/…` is there, not in this repository; so are the R0 tools this text names (`db_check.py`, `tricks_check.py`, `db_extract.py`, …), whose checks the loader now applies (§9).
- **Section numbers** are draft 0's, so the data's comments, which cite "FORMAT §n" and `db-draft/`, point at this text and at `src/azurkit/tools/randomizer/data/`. A reference to AzurKit Step 4.10a–h in dated text means Phase R1's step (D137): 4.10a → R1.1–R1.3, 4.10b → R1.4, 4.10c → R1.5–R1.7, 4.10d → R1.8 and R1.11, 4.10e → R1.9 and R1.12, 4.10f → R1.10 and R1.13.
- **Built on.** [`RANDOMIZER_PLAN.md`](archive/RANDOMIZER_PLAN.md) §2 (the model), §3.1 (non-monotone mechanisms), §3.5 (`db_digest`) and §4.1–§4.5 (the data). Decisions D76 (victory), D77 (gems), D78 (clusters), D80 (names may be committed), D81 (vanilla 4th fragment), D93 (`full` accessibility), D113 and D114 (skips), D122 and D143 (proven spots) and D144 (settings). The R0 evidence: `$RP/r0/PREP.md`, `$RP/r0/RAM_RECIPES.md`, and the raw outputs of the R0.3a lane (`$RP/wiring/`) and the R0.3b lane (`$RP/thresholds/`).
- **R0.3a and R0.3b are done.** Their reports, `$RP/wiring/REPORT.md` and `$RP/thresholds/REPORT.md`, were saved later on 2026-10-11 (`$RP` `61179be`; `RANDOMIZER_PLAN.md`'s R0 record, Step 2.20j), after draft 0 found neither (the harness had refused the lanes' writes). This text cites their raw outputs by file, and `$RP/r0/tools/r03_raw_outputs.sh` remakes every one of them (History).
- **The database's files** (Step R1.4 imported the hand files from `$RP` at `4b8f3f3`: `db-draft/levels/`, `items.toml`, `world.toml` and `settings/defaults.toml`, `tricks/tricks.toml` and `route/vanilla_route.toml`, changing only their `format` keys, one header line and the level files' `status` comment; Step R1.4b re-imported `tricks.toml`, `world.toml` and the 19 level files that changed from `$RP` at `7530b0b`, which lands D145's time-savers, `e2411cb`, and sitting rjc5's three confirmations, by applying `$RP`'s diff from `4b8f3f3` to the imported files, §14):
  - `generated/<level>.json`: 23 files (the 22 playable levels and `training_room`), from Step R1.1's extract;
  - `levels/<level>.toml`: 22 files, all `authored` since Step R1.8d (2026-10-13; §4.10, §10), the stubs of the import (§4.1) all replaced;
  - `items.toml`, `world.toml`, `tricks.toml` (§12), `route.toml` (§13) and `settings/defaults.toml` (D144; the five `presets/*.toml` are retired, §7.6).
- **Labels.** [verified] gives the command, or the raw file and the tool that writes it. [verified static] is a read of the USA `default.xbe` (a VA and the `ramdis.py` command, or a RAM_RECIPES section). [inferred, static] marks a reading of decoded data that an xemu sitting must confirm; draft 0 gave each a `TODO(R0.4…)`, and R0.4's sittings and Step R1.8's defaults have answered them (§11). [workflow] is a lane's result that wasn't re-run. [inferred] is reasoning. A design rule carries no label.

## 1. Layout

```
src/azurkit/tools/randomizer/data/
  generated/<level>.json   machine-written by `rando db-extract` (Step R1.1); never edited by hand
  levels/<level>.toml      the level layer: nodes, edges, barriers, buttons, events, location overrides, skips, route
                           (a stub's by hand; an authored level's written by `rando author` from its derived file and
                           draft/authoring/<level>.toml, the realm step's hand decisions, §4.10; Step R1.8)
  derived/<level>.json.gz  machine-written by `rando derive` (Step R1.3c; gzip since R1.3d): the reach model's zones, edges and gates (§16)
  movement/<level>.json    machine-written by `rando author` beside an authored level's file (Step R1.14b): what of its logic
                           rests on a modelled flight, for a build to re-check under its own movement (§17); outside `db_digest`
  contact.json             machine-written by `python -m devkit reach l3-contact apply` (Step X.11): flights of the movement files
                           measured in L3 at modified movement, each slider's range (§17); outside `db_digest`
  items.toml               item -> counters, classes
  world.toml               start, hub, victory, trick families, time-savers (D145), non-monotone mechanisms
  tricks.toml              the trick families, every skip and every time-saver, with their review material (§12)
  route.toml               the vanilla non-gem route (§13)
  settings/defaults.toml   the default options (D144): skip ceiling, movement tier, dark_fire, per-skip toggles
  proofs.jsonl             the L3 proof records every `proven = { by = "l3" }` mark resolves to (D170, Step X.7; §4.6):
                           written by `python -m devkit reach l3-certify apply`, one JSON record per line, sorted by ref; evidence,
                           outside `db_digest` (`src/azurkit/tools/randomizer/planner/proofs.py`)
```

- **Nothing else.** The loader refuses any other file or folder in the database (dot files aside), and a leftover `presets/` (§7.2).
- **New against the plan's §4.2:**
  - `world.toml` holds the facts that belong to no level: the start, the hub, victory (D76), the trick families and the mechanism declarations (§3.1 "the loader refuses a database that uses one without its declared handling").
  - `derived/` is where §4.1's "derived (generated and reviewed)" data goes. Since Step R1.3c it holds the reach model's output per level (§16); the worst-case key counts, no-return regions, forfeitable locations, escape summaries and the save-point danger list stay computed in memory by the solver (§15).
- **Encoding.** All files are UTF-8 with LF line ends.
- **JSON files** are written with sorted keys, one-space indentation and a trailing newline. A key repeated in one object is refused (`tomllib` already refuses one in TOML). Every list is sorted by id, comparing the file stem, then the graph and record numbers as integers. Same input, same bytes [verified, History].
- **TOML files** are read with `tomllib`. Only `rando author` writes any (an authored level's file, and the `to` of a stub's exits into it, §4.10); the stubs' files are hand-written, so their comments are safe.
- **One level per file.** An object lives in the file of the level it belongs to (§4.6).
- **Unknown keys fail.** The loader refuses any key this text doesn't define, any enum value outside its list, a missing required key and a value of the wrong type (fail closed, the plan's §2.2 rule; §9, rule 1).

## 2. Ids and names

### 2.1 Generated ids

- **Form:** `<file>/g<G>/r<R>`.
  - `<file>` is the XBR's stem: the level's name, or `characters` for the two 4th fragments that a boss's character graph spawns (§3.4).
  - `G` is the index of the node section among the file's `node` TOC entries, in TOC order, from 0.
  - `R` is the record index inside that section.
- **Every generated object has one**, keyed by one record:

  | Object | Its key record |
  |---|---|
  | location | the critterGenerator |
  | barrier, geode | the group's lowest damage platform |
  | keylock | the trigger platform (key fourcc at +0x40), or the `LockToggle` for an e5 relay |
  | keylord | the keylord critterGenerator (the namespace's first record for e7's remnant) |
  | obsidian lock | its `OpenLock_andCombiner` |
  | seal | its `Seal_toggle` switch |
  | save point | the gameSaveControl |
  | exit | the levelSwitch |
  | spot | the playerLocation |
  | teleporter | its lowest locator playerLocation |
  | boss | the boss critterGenerator |
  | latch, game state | the record itself |

- **Stability.** The ids are stable for the game data this repo supports: since D146 (superseding D39) the USA and the Europe release. The generated files are extracted from the USA ISO, and a Europe build places by the same ids and reads back to its plan (G3's Europe seed case; Step R1.16's D188 sighting). They hold no game name, so they don't depend on RQ-10, although D80 allows names.

### 2.2 Hand ids

- **Node:** `<level>_<area>`, using only `[a-z0-9_]` and starting with its level's name. Examples: `w1_beach`, `town_central`.
- **Object** (barrier, button, event): `<level>.<part>[.<part>…]`, each part `[A-Za-z0-9_]+`. The first part is the file's level.
  - The draft derives an alias from the debug name, for example `w1.FireWall_01` and `e2.earth_keylock3`. The owner may rename it, for example to `w1.fbarrier1`.
  - Event ids name their state: `w1.keylordSystem.killed`, `e5.guard_earth.killed`.
- **Skip** (D113): `<level>.<slug>`, the slug `[a-z0-9_]+`, the level being the one the skip is performed in: `w1.torpedo_skip`, `w1.firewall01_air2_beach_town` (§4.8).
- **Time-saver** (D145): the same scheme. An id is a skip's or a time-saver's, never both (§4.9); a skip that turned out to be a time-saver keeps its id.

### 2.3 Flags

A flag is set once and never cleared (§3.1). It comes only from objects:

| Source | Flag | Set when |
|---|---|---|
| `[[barrier]]` with permanent persistence (§4.4) | `<id>.destroyed` | destroyed from a `destroy_from` node |
| `[[button]]` with `mode = "latch"` | `<id>.open` | pressed at its `at` node with its requirement met |
| `[[event]]` | `<id>` | its requirement holds at its `at` node |
| a named latch (`generated.latches[].global`) | `global.<name>` | [reserved] the global's value becomes non-zero. `thresholds/latches.txt` (`latches.py`) lists 29 global names; their writers are events today, so the draft doesn't use these flags yet |

### 2.4 Counters, items and tricks

- **Counters:**
  - `air`, `water`, `fire` and `earth`: element levels;
  - `disca`, `discw`, `discf`, `disce` and `discl`: fragments of that disc held;
  - `obsidian`, `sapphire`, `emerald`, `ruby` and `diamond`;
  - `life`, `staff` and `ammo`;
  - `key.<type>`, one per key item, named after it without `key_`: `key.battery`, `key.life1`.
- **Gem counters count gems collected, not the in-game value.** A gem pickup can run the fuel-cap upgrade, which subtracts a config amount from that gem slot (0x58639–0x58642) and adds one to the paired fuel cap (0x586BB) [verified static, `ramdis.py dis 0x585f0:70`; the amounts, 100 gems for 33 cap, are RAM_RECIPES §2.1]. So the game's own gem values (and any gameState on `emeralds`, `diamonds`, `rubies` or `sapphires`) go down. The database's `sapphire`, `emerald`, `ruby` and `diamond` counters only grow, but a data gate that reads the in-game gem value is non-monotone: `world.toml` declares it (`gem_fuel_upgrade`, kind `spend`), and gems stay out of v1 logic (plan §2.8). This breaks R2.6's gem rewards and R2.10's `diamond>=100` fuel tier as the plan writes them (§11).
- **Items** are config.xbr `critters_item_data` names. There are 73 [verified, `census.json` `config.item_inv_types`]. A `_move` template counts as its base item.
- **Tricks** are technique families named in `world.toml` (§7). Since D113 (owner, 2026-10-12: "i wouldnt rank tricks by difficulty, but rather specific skips") a trick has no tier. A **skip** is a named, located use of one or more tricks that carries its own difficulty (§4.8); requirements name skips, never tricks (§5.1).

## 3. `generated/<level>.json`

`db-extract` writes one file per level, including `training_room`, whose locations have `pool = false`. The content rules (RANDOMIZER_PLAN §4.4): names, ids, kinds, counts, decoded values, file offsets of write targets, and requirement strings derived from decoded data. Never coordinates, transforms, raw records or bytes.

### 3.1 Top level

| Key | Type | Meaning |
|---|---|---|
| `_meta` | object | `format` (`azurik-rando-generated/1`), `generator`, `date`, and `source {file, size, sha256_12}` of the level XBR |
| `level`, `kind` | str | the level, and one of `realm`, `hub` (town), `boss` (airship) or `tutorial` (training_room) |
| `cells` | [str] | the `levl` cell names, by index |
| `graphs` | [object] | per node section: `g`, `toc_index`, `ndbg_toc_index`, `records`, `links`, `saved_nodes` (the save list's length), and `padding_after` (the zero bytes after the section, which is the new-string budget of plan §5.2) |
| `locations`, `geodes`, `barriers`, `keylocks`, `keylords`, `obsidian_locks`, `seals`, `save_points`, `exits`, `spots`, `teleporters`, `bosses`, `latches`, `game_states` | [object] | §3.2–§3.13 |
| `counts` | object | the lengths of those lists, and the pool locations by class |

### 3.2 `locations`: one per pickup critterGenerator

| Key | Meaning | Source |
|---|---|---|
| `id`, `name` | the id (§2.1) and the debug name | ndbg |
| `class` | `major` (key, fragment or power), `obsidian`, `gem` (yield 1), `cluster` (a gem with yield > 1) or `consumable` | critter name |
| `item`, `template` | the base item, and the name as written (`sapphire_move`) | record +0x1C/+0x20 |
| `yield`, `unbounded` | maxGenerated < 0 gives \|maxGenerated\| × points; > 0 gives maxGenerated; 0 gives `null` with `unbounded: true` | the rule `gen_yield.py` states for 0x6FD40 [workflow, not re-read]; its gem totals equal the census [verified, `wiring/gen_yield.txt`] |
| `points` | the number of gen points | +0x2C/+0x30 |
| `on_load` | `enable` (attribute 13) ≠ 0 | 0x6FD40 |
| `enabled_by` | each link into `enable`, as `"<id> <name>.<plug>"` | the link table |
| `dead` | `enable` is 0 and nothing links into it, so it never spawns | — |
| `gated_by` | the generated objects its spawn or its access depends on: a geode, a keylord, an obsidian lock or a boss (§5.6) | relations below |
| `geode`, `keylord`, `obsidian_lock`, `inside_barrier` | the relation that put an id in `gated_by` | census grouping, namespaces |
| `guardian_slot` | `true` on the 5 vanilla 4th-fragment slots (RQ-4/D81): the solver keeps its vanilla fragment whatever a placement names, refuses another item there, and collecting it spends its disc's teleport (§15) | — |
| `saved` | in the level's save list | node header +0x0C (0x65E50) |
| `cell`, `parent`, `namespace` | the cell name, the parent's debug name, and the Maya namespace | +0x34, DAG |
| `name_ref` | `{field, string, length}`: the XBR file offsets of the (length, ref) name field and of the string it names. This is the writer's target (plan §5.2) | — |
| `pool` | `false` for `training_room` and for dead generators | — |
| `note` | free text, only on the two `characters` slots | — |

- **The pool** [verified, `db_extract.py`]: 1,418 locations, which are 79 majors, 100 obsidians, 1,146 gems, 69 clusters and 24 consumables. This equals the plan's G1.
- **Six locations are out of the pool:** training_room's 4, and the dead a6 `AirFragmentGeneratorShape` and f6 `old_firefragmentGeneratorShape`.
- **a6's and f6's 4th fragments** are `characters/g16/r102` and `characters/g21/r154`. They are spawned by the boss's character graph, and the a6 and f6 level generators are dead [verified, `thresholds/disc_chains.txt`, sections `=== a6`, `=== f6` and `=== characters`]. Their `gated_by` names that level's boss (`guard_air`, `guard_fire3`); that the air guardian's death drives graph 16 is [inferred] from the graph's node names (the R0.3b lane's reading).

### 3.3 `geodes` and `barriers`

- **Grouping.** These are damage platforms (fourcc at +0x38 other than `none`) grouped as `census.py` does: the nearest `…:all` ancestor, else the namespace, else the record's own name. A group whose name matches `(Diamond|Emerald|Ruby|Sapphire)Stone` is a geode. [verified: 122 barrier groups and 77 geodes, equal to the census]

| Key | Meaning |
|---|---|
| `id`, `name`, `kind` | `kind` is one of `firewall`, `iceblock`, `acidblock`, `crystal`, `trap`, `other` or `geode` |
| `damage`, `damage_mix`, `elements` | the fourcc, a count per fourcc if the group mixes them (none does), and its config `magic` combo (`stem` → `FW`) |
| `level`, `levels_seen` | **[inferred, static]; I-2 answered by R0.4b** (a barrier needs its combination at a power level, §11). The smallest value L in 1..4 that, fed into each shape's `magic` plug and followed through its links (at most two combiners), turns a target on; `null` when no shape has a `magic` link. The walk is `barrier_levels.py`'s, and its per-group results are `thresholds/barrier_levels.txt` |
| `persist` | **[inferred, static]; I-8 answered by R0.4b for six families, I-15 (the town↔beach wall) a default at Step R1.8** (§11). `permanent` (every target switch is saved and has no stored `turnOff`), `timed` (every target has a stored `turnOff`, read as "it closes again"), `level_reset` (it latches but isn't saved), `mixed`, or `unknown` (no `magic` link) |
| `requires` | **[inferred, static]; I-2 answered by R0.4b** (§11). The derived destroy requirement: each element of the combo ≥ `level`. `null` when `level` is null |
| `shapes`, `switches` | the platform ids, and the switches their `magic` links reach |
| `contains` (barriers) | locations in the same group (none on the disc) |
| `near_locations` (barriers) | pool locations with a gen point within 4 units of the group's centre. This is a relation only; the distance is computed in memory and dropped |
| `variant`, `locations`, `contents` (geodes) | the stone, its 3 locations (same group, or enabled by its `magic`), and their items |

- **What is decoded and what is read into it.** The data gives the `magic` links, their curves' thresholds, the save list and each switch's stored `turnOff` [verified, `thresholds/barrier_levels.txt`, `wiring/saved_nodes.json`]. On a hit whose damage fourcc equals the platform's (+0x38), the handler sets attribute 4 (`magic`) to an integer the attack carries at +8 [verified static, `ramdis.py dis 0x7a1c0:45`]; that this integer is the config `damage` Level (1–3) is the R0.3b lane's reading [workflow]. A combination's level is the minimum of its elements' levels, at most 3 [verified static, 0x838E0, RAM_RECIPES §3]. Everything past that is inference: that the curve threshold is the power level a barrier needs, that a combination needs each element at that level, and that a stored `turnOff` means the barrier respawns. So `level`, `persist` and `requires` don't answer I-2, I-8 or I-15 by themselves; R0.4b's sittings answered I-2 and I-8, and I-15 took a default at Step R1.8 (§11).
- **Counts** [verified, `db_extract.py`]:
  - barrier `persist`: 72 `permanent`, 35 `timed` (all 32 FireWall groups among them), 4 `level_reset` (w3's traps), 6 `mixed` (the crystals) and 5 `unknown` (e6's four song-pedestal `Detect_*` platforms and w2's `HoseStuff`, which have no `magic` link);
  - every geode is `permanent` at level 1.

### 3.4 `keylocks` and `keylords`

- **keylock**, one per `*_keylock<N>` namespace (43; 39 coded) [verified, `wiring/prefabs_summary.txt` and `wiring/keylocks.json`, written by `prefabs.py`]: `id`, `namespace`, `records`,
  - `coded`;
  - `trigger`, `key_fourcc` (platform +0x40; 39 platforms carry a key fourcc [verified, `wiring/platform_fields.txt`]; that the platform loader 0x6A490 reads it as the key requirement is the R0.3a lane's read [workflow]) and `key_type`;
  - `consumes` (`key.<type>`; 0x58AD0 uses up one key [verified static, RAM_RECIPES §4]);
  - `requires` (`key.<type>>=1`);
  - `lock_toggle` and `saved`;
  - `drives` (terminal classes reached, with counts) and `drives_out` (the plugs it sets outside the prefab).
- **e5's 4 relays** have `coded: false` and `relay_of` (the coded lock that drives them).
- **keylord**, one per `keylordSystem<N>` namespace (8): `complete`, `keylord`, `key_location`, `key_item`, `cage` (the `open` platform), `latch_toggle` (`toggle2`) and `event` (`<level>.<namespace>.killed`). `id` and `namespace` too. e7's `keylordSystem5` has `complete: false`: 2 records, no generator [verified, `wiring/prefabs_summary.txt`].

### 3.5 `obsidian_locks` and `seals`

- **obsidian lock** (town, 10): `id`, `namespace`, `lock` (1–10), `threshold`, `requires` (`obsidian>=N`), `open_combiner`, `lock_toggle`, `saved` and `locations`.
  - The threshold is the smallest integer count at which the counter → `OpenLock_and` link is non-zero (curve(count × weight) × factor, the curve evaluated by the rules `logic.py` gives for 0xD8300). Thresholds 10, 20 … 90, and lock 10's is 100 (its key is at 99.99983) [verified, `thresholds/obsidian_tables.txt`, written by `obsidian_tables.py`, and `generated/town.json`].
- **seal** (6) [verified, `thresholds/seals.txt` (the `logic_dump.py` runs in `r03_raw_outputs.sh`) and `generated/*.json`: a1, w1, f6, e5 and town need touch + 3 of their disc; d1 needs touch + 4 of each disc]: `id`, `name`,
  - `activate`;
  - `requires`: the gameState conditions on its `SealActivate_andCombiner`, mapped to counters;
  - `touch`: the platform plug the same AND reads;
  - `saved`, `sets_globals`, `drives` and `activate_also_drives` (for example f6's `Jaw_toggle`).

### 3.6 `save_points`, `exits`, `spots` and `teleporters`

- **save point** (43): `id`, `name`, `save_id`, `saved`, and `do_save` (a hint, §3.8).
- **exit** (every levelSwitch whose destination is on the disc; 75):
  - `kind` is one of:
    - `exit` (72);
    - `teleport` (same level; 1);
    - `ending` (`return-to-shell`);
    - `start` (`start-playing`).
  - f1's `levelSwitch3` names `levels/fire/f7`, which is not on the disc: `db-extract` leaves it out (AZ-290), so draft 0's 76th exit and its kind `dead_dest` are gone (§14).
  - `id`, `name`, `dest`, `dest_level`, `spot` and `movie`.
  - `arrival`, `arrival_by` and `arrival_graph_known`: where the engine puts the player. The rule [verified static, 2026-10-11: `ramdis.py fn 0x5ff70`, `dis 0x6004d:40`, `dis 0x54160:30`, `dis 0x6eaf0:30`, `str 0x19e090`, `str 0x1a1e74`]: `load_level_from_path` calls 0x5FF70(spot) at 0x54172. It walks the node vector of the main graph `[pd+0xDC]` in record order and takes the first playerLocation whose node+0x20 string equals the spot or the spot + `Shape`, comparing bytes case-sensitively; node+0x20 is a copy of the record's +0x1C string (0x6EB15–0x6EB27). On a miss it retries with `startspot` (0x54190); on a second miss the player goes to the origin (0x541B0).
    - `arrival` is that playerLocation's id (`null` for the origin), and `arrival_by` is `spot`, `spot+Shape`, `startspot` or `origin`.
    - Of the 72 `exit`s, 66 resolve by their spot (59 `spot`, 7 `spot+Shape`) and **6 fall back to `startspot`**: a3 `A3_A5_levelSwitch` (spot `A3_A5`), a6 `A6_A1_levelSwitch` (`A6_A1`), w1 `W1_A3_levelSwitch` and airship `EndFight_levelSwitch` (`W1_A3`), town `temple:Town_L1_levelSwitch` (`Town_L1`) and town `toD1_levelSwitch` (`Town_D1`). The last is the route to the victory level: the draft's first version put its arrival at d1's `Town_DShape1` by a looser match, but the engine uses d1's `startspotShape` [verified, `db_extract.py`; `generated/town.json`]. None falls back to the origin.
    - **Multi-graph levels.** In town, w3 and training_room only one graph holds playerLocations, and the draft assumes it is `[pd+0xDC]`; which graph that is stays open (RAM_RECIPES §10, point 5). `arrival_graph_known` is `false` for the 20 exits into those levels.
  - `dest_string_shared_by`: how many levelSwitches in the graph point at the same destination string (census F2).
  - `live`: the gate reaches at least one input the game can change. 3 are not live [verified]: w1 `W1_W3b`, e5 `levelSwitch1` and f3 `LevelSwitch_F3_F1_Backup`.
  - `gate_hint` (§3.8).
  - `disc_teleport` names the disc on the count-triggered teleports to town [verified, `thresholds/disc_chains.txt` and `generated/*.json` gate hints]:
    - a6 `PlaceAirDisk`, w3 `PlaceWaterDisk`, f6 `PlaceFireDisk` and e5 `DiskReplaced`: that disc's count ≥ 4 AND NOT `global[<elem>_disk_placed]`;
    - w1 `BossDefeated`: water fragments ≥ 4 AND a touch of `Water_Tube:Link:Public_PushShape`, with no placed check;
    - **life has none.** Its `Movie_levelSwitch` and `Town_levelSwitch` are gated by a beam puzzle (`BeamToggle`, fed by particle-sink `justSunk` events), a timed `ToTownFieldShape` touch and `global[life_disk_placed]` (nand for the movie exit, plain for the other), not by a fragment count.
    - **This contradicts RANDOMIZER_PLAN §0 and §2.9**, which say the count chain exists in the five guardian levels a6, w3, f6, e5 and life. In the data, life has no count-triggered teleport and w1 has one. The no-return and forfeitable model for life and w1, and the Q246 rider (w1 `BossDefeated` → `water_disk_loc`), depend on this; the R0 record step updates §2.9 (§11).
    - **Level- or edge-triggered is not decoded here: [inferred, static]; I-7(a, d, e) answered by R0.4b** (placed): level-triggered and safe after placement in a6, and e5's chain fires as a6's (§11). The gameState is refreshed every frame (0x711C0 [verified static, RAM_RECIPES §8]).
- **spot** (226): `id`, `name`, and `teleport_gate`, the hint of what drives its `teleport` plug.
- **teleporter** (9 in 8 levels in Step R1.1's data, which found e2's pair; R0's draft had 8 namespaces in 7 levels, and the plan's "8 levels" counted w1's two): `id`, `namespace`, `locators` (required) and `routes` (required; Step R1.1). Each route is `{ to, touch, needs }`: touching the field pad `touch` sends the player to the locator `to` once every reset pad in `needs` has been touched (a pair whose beams start on needs none). R1.1's `db-extract` decodes them from each pair's and-combiner and refuses any other wiring. The loader checks that `to` is one of the teleporter's `locators` and that each pad is a `<level>/g<G>/r<R>` id of the teleporter's level; pads are in no generated table, so nothing more is resolved. Every teleporter carries routes in R1.1's data [verified 2026-10-12, its lane at `53720ec`, which the rebase onto `d67da6b` made `be6d314` with the same tree change].

### 3.7 `bosses`, `latches` and `game_states`

- **boss** (8): `id`, `name`, `critter`, `saved`, `on_load`, `enabled_by` (a hint), `num_dead_drives` and `event` (`<level>.<critter>.killed`).
- **latch** (69 in levels): `id`, `name`, `global` (the `shared.sav` name, or `null`), `saved`, and the `update` and `input` hints.
- **game state** (69 in levels): `id`, `name`, `vars`, and `links` `{var, when, to}`.
  - `when` is where on the variable's own domain the link's value, curve(value × weight) × factor, is non-zero (`logic.nonzero_when`):
    - for integer variables (counts, levels, fragments, health, fuel, current day, armor and damage type and level), the set of integers: `>=N`, `<=N`, `in{…}`, `always` or `never`;
    - for the two real variables, `day night timer` (frac(clock), [0, 1)) and `armor fraction` (the f32 armor gauge, taken as [0, 1] [inferred]), a union of intervals such as `[0.25,0.75)` or `[0,0.25)|[0.75,1)`, or `always` / `never`. A `~` prefix marks a Hermite curve that was sampled (none on the disc today).
    - Which variables are real comes from 0x711C0's cases [verified static, 2026-10-11: `ramdis.py fn 0x711c0` and `u32 0x714cc 8`]: every variable is a `fild` of an integer, a sum of 1.0s or a constant, except `day night timer` (two fmods by 1.0, at 0x71260) and `armor fraction` (a `fld` of armor_mgr+0x24, at 0x7145D).
    - **Fixed 2026-10-11.** The first version sampled every variable at integers only, and ignored the link's weight and factor, so the 185 day/night links in levels came out `never` (54) or `always` (131); 167 of them change under the fixed rule [verified, the old and new `generated/*.json` compared in memory]. For example w4's `fanHinge`…`fanHinge4:DayNight_gameState` → `ActivatePlats_andCombiner` now read `[0.25,0.75)`: the fan platforms unfold by day, every day [verified, `generated/w4.json`; the raw curve `step{[0.25,0.75): 1}` is in `thresholds/w4_daynight.txt`]. `thresholds/gamestates.{txt,json}` were remade with the same rule.
  - Links into transform plugs are dropped (§4.4 of the plan).

### 3.8 Hints (`gate_hint`, `do_save`, `teleport_gate`, `enabled_by`, `update`, `input`)

- **What a hint is:** a display string that explains what drives a plug, walked back through logic nodes up to 6 deep.
  - The loader never parses it.
  - A database must never depend on one. Authors read it; the loader checks only its type.
- **The language:**
  - `and(…)`, `or(…)`, `nand(…)` and the other combiner functions (the function code at record +0x1C, `logic.COMBINER_FN`; the R0.3b lane's read of 0x69BF0/0x69C10 [workflow]; `thresholds/combiner_census.txt` counts them), with an unlinked input shown as its stored constant;
  - `switch[name]{on=…; off=…; toggle=…}.output|goal`, where `=const` means a stored non-zero input;
  - `touch(…)`, `actionButton(…)`, `key(…)`, `magic(…)`: platform events;
  - `gs[var]>=N`;
  - `global[name]`;
  - `numDead(critter@name)`;
  - `teleported(spot …)`;
  - `timer[name](…)`;
  - `pos(name.plug)`, a moving part, written without its interval;
  - a step condition in braces, `{<=0}`, and `{w=…,f=…}` for a non-unit link weight or factor. A `gs[…]` condition uses the domain rule of §3.7; any other source's condition samples the integers 0–10 only (display text, so its approximation never reaches logic).

## 4. `levels/<level>.toml`

### 4.1 Top-level keys

| Key | Required | Meaning |
|---|---|---|
| `format` | yes | `azurik-rando-level/1` |
| `level` | yes | equals the file stem |
| `status` | yes | `draft` (a stub, below) or `authored` (its realm step, R1.8 or R1.11a–d, authored it) |
| `default_node` | no | the node that every unanchored location and object of this level belongs to. Meant for single-node levels |
| `known_traps` | no | the owner-signed trap list (plan §2.13): `[{node = "…", note = "…"}]` |
| `route` | no | the owner's non-gem vanilla route, as location ids in collection order (plan §4.3). An authored level with no pool location (the airship) has none (Step R1.11a) |

**Stubs (v1; default taken under D115, Q301).** A `draft` level, and a generated level with no level file (`training_room` today), is a stub: the loader applies every check to what it holds, but counts its open fields (§8) and its pool locations with no node (§4.2) as open instead of refusing them, and an undecoded barrier it binds (§4.4) as an open gate. The solver treats a stub as one free node holding its vanilla items, which stay out of the pool (plan §4.3, check 3). Today no level file is a stub: all 22 are `authored`, and `training_room` has no file (§10). An `authored` level has none of the three: each is a load error. Draft 0's second value, `owner-reviewed` (R0.7's mark), is gone: since D115 the owner's review is offered, not waited for, and R0.7 closes into the realm steps' picture reviews (R1.8).

### 4.2 `[[node]]`

| Key | Default | Meaning |
|---|---|---|
| `id` | required | §2.2 |
| `anchors` | `[]` | generated ids (a save point, exit, spot, barrier, keylock, seal, obsidian lock or teleporter), `cell:<cell name>`, or `zone:<zone id>`, a zone of the level's `derived/<level>.json.gz` (§16; Step R1.8): the node is made of those zones, and no zone is anchored by two nodes |
| `locations` | `[]` | explicit membership: location ids that belong here whatever the anchors say |
| `start`, `hub` | `false` | the one start and the one hub; they must match `world.toml` |
| `dark` | `false` | needs light (plan §2.12): `true`, or the id of the `nolight` skip that lifts the need for this dark area (§7.1; Step R1.5): a skip of this level and, when its `tricks.toml` row names a `dark_node`, this node. Everything done at a dark node (a location collected, a button pressed, an event, a barrier destroyed) needs the light |
| `note` | — | free text |

**Location → node.** The first rule that applies wins:
1. the location is in some node's `locations`;
2. its `cell` is some node's `cell:` anchor;
3. the zone `derived/<level>.json.gz` puts it in (its `locations[].zone`, the reach model's nearest floor to its first gen point, computed in memory and never stored as a coordinate) is some node's `zone:` anchor (Step R1.8: this is the draft's "nearest point anchor", done by the derive);
4. `default_node`;
5. otherwise loading fails.

A location the derive places on no floor (`zone` null: over water, in a hazard, or in a transform the derive doesn't follow) needs rule 1.

### 4.3 `[[edge]]`

| Key | Default | Meaning |
|---|---|---|
| `from`, `to` | required | node ids. The edge lives in `from`'s level file |
| `kind` | required | one of the following: |
| | | `walk`; |
| | | `drop` (one way); |
| | | `exit` (a levelSwitch); |
| | | `teleport` (a same-level levelSwitch, a teleporter or the disc teleport); |
| | | `cart` (the e2–e5 and e2–e7 gondolas: e2 `SwitchE5a` ↔ e5 `levelSwitch2`, lock `minecart_e2e5`, and e2 `SwitchE5a1` ↔ e7 `E7_E2_switch`, lock `minecart_e2e7` [verified, `wiring/exits_e2.txt`, `exits_e5.txt`, `exits_e7.txt`]) |
| `requires` | `"true"` | the physical requirement, skips included (§5) |
| `exit` | — | required for `exit` and `cart`, and for a levelSwitch `teleport`: a generated exit id in this level |
| `teleporter` | — | for a `teleport` through a `Teleporters` prefab: a generated teleporter id |
| `disc` | — | for the disc teleport: `air`, `water`, `fire`, `earth` or `life`. One shot (plan §2.9; §15): no edge of the reach, an escape takes it only until that disc's guardian slot is collected; the disc needs exactly one guardian slot in the pool (§9 rule 14) |
| `through` | `[]` | barrier ids passed. Never on `exit` (plan §2.3) |
| `assumes` | `[]` | flags a vanilla design expects to be set first (plan §2.13 rule 3): the edge is in logic once they are credited, they count toward the far side's escape as forced on entry (§15), and R_phys ignores them |
| `logic` | `true` | `false` keeps the edge physical only (plan §2.10) |
| `lock` | — | for `cart`: a `world.toml` mechanism id |

- **The gondolas** [verified data unless marked; `uv run --locked python -I $R0/tools/logic_dump.py e2 '<names>'`, `wiring.py e2 '<names>'` and `saved_nodes.py e2|e5 '<names>'`, 2026-10-11]:
  - e2 → e5: touching `Trigger1Shape` (on `MineCar`) latches `Non_PersistantToggle` (unsaved); then touching `TriggerShape`, which sits in the gondola under `MineCar/LockMove/Transformf/…`, turns on `DownToggle` and fires `SwitchE5a` (spot `E2a_E5a`). `DownToggle` (saved) turns off only on `E5a_E2a.teleported` AND a `TriggerShape` touch, that is, after returning by e5's `levelSwitch2`. e5's `MineCarToggle` (saved) turns on from `E2a_E5a.teleported` and off from `mineplat:BucketFloorShape`.
  - e2 → e7: the same pattern with `Trigger3Shape`, `Non_PersistantToggle1`, `Trigger2Shape` (under `MineCar2/LockMove/Transform/Public_Bottom_ZTrans/…`), `DownToggle1` (saved) and `SwitchE5a1` (spot `E2_E7`); `DownToggle1` turns off on `E7_E2.teleported` AND a `Trigger2Shape` touch. e7's only exit, `E7_E2_switch`, lands at `E7_E2`, and `SwitchE5a1` is the only exit into e7 [verified, `generated/*.json`].
  - Both `LockMove` transforms (and both gondola doors) are moved only by `Topcartoggle1`/`Topcartoggle2` (saved), which turn on only from `MineCarRide2:andCombiner1` = AND of the two `key_circuitboard` locks' `LockToggle.goal` (e2 `earth_keylock`, `earth_keylock1`) [verified, `wiring/prefabs_summary.txt` and `wiring.py e2 '^Topcartoggle[12]$'`]. That neither gondola can be ridden before both locks are used is **[inferred, physical]** (I-10's mechanism answered by R0.4b-ii, §11), so the drafts put `button:e2.earth_keylock & button:e2.earth_keylock1` on both e2 cart edges; Step R1.11c authored MineCar2 (e2 ↔ e7, `minecart_e2e7`) in logic with both locks and kept MineCar (`minecart_e2e5`) out.
  - `MineCarRide2`'s own ride (`MoveTog2` → `andCombiner2` → `CarMoveTimer`) reaches no levelSwitch within 4 link hops [verified, `wiring.py e2 '^MineCarRide2:(MoveTog2|andCombiner2|CarMoveTimer|cardoortoggle|Nonresettoggle)$' --hops 4 | grep -c levelSwitch` → 0]: it is an in-level ride, not the e2–e5 rig plan §2.10 assumed.
  - The one-bit side state of each gondola is real (R0.4b-ii: it makes e2's dock a lethal drop), so the side matters to the logic for MineCar, which stays out of it (§11).
| `dark`, `casts` | `false`, — | the light requirement (`true`, or the id of the `nolight` skip that lifts it, as for a node, §4.2, with the skip's `dark_node`, when it has one, at one of the edge's ends), and a cast-count hint (plan §2.11) |
| `confidence` | `assumed` | v1 (plan §4.5): how the edge is known, `assumed` < `data` or `physics` < `probed` < `owner`. Editing an edge resets it to `assumed`; raising it never tightens logic. Since D122 it sets no option (the proven-spot rule replaced the confidence floor, §4.7); `rando check` counts the edges per value |
| `proven` | none | D170: the walk that makes a `probed` edge, `{ by = "l3" \| "xemu", ref = "..." }` (an `l3` ref resolves to a `proofs.jsonl` record whose edge claim names this node pair: a node id or one of its zone anchors at each end, in this level, and whose kit, what the string held, is no more than the edge asks: AZ-544, Step R1.29i: under the most lenient options, with every flag credited and every other counter in full, the edge's own rule, its `requires`, barriers, `assumes` and light, never holds with a counter a band below the kit's); refused on an edge that isn't `probed`. `rando author` writes it from the authoring's `[[probed]]` |
| `difficulty` | `1` | a derived jump or flap edge's movement difficulty, from its margin (D113): 1 safe, 2 standard, 3 hard, 4 frame-perfect, the lowest `envelope/tiers.toml` tier whose margins the edge clears, or 0 when only the `phys` tier's do (`draft/tiers.toml`'s `[phys]`, difficulty 0; Step R1.6): such an edge is in R_phys only, never in logic (§15). The edge is usable when its difficulty is from 1 up to the number of the settings' `movement_tier` (§7.1; plan §2.15, D108, D129, D144), which is a separate option from the skip ceiling. It is not a skip: a derived edge that uses a trick family is written as a generated skip (§4.8). The planner reads the tiers only through this number; it never imports `draft/` (Phase R1's contract, pinned by `tests/test_movement_envelope.py::test_movement_tiers_are_the_planners_and_monotone_and_their_lip_lift_windows_nest`) |

### 4.4 `[[barrier]]`

| Key | Meaning |
|---|---|
| `id`, `of` | the hand id, and the generated barrier it binds (exactly one hand barrier per generated barrier) |
| `destroy_from` | the nodes it can be destroyed from |
| `bypass` | `{ "A->B" = "<expr>" }`: one direction, repeatable, no flag (plan §2.4) |
| `requires` | an extra destroy condition, ANDed with the generated `requires` |
| `override_requires`, `override_reason` | replace the generated `requires`; the reason is mandatory |
| `persist`, `persist_reason` | override the generated value; the reason is mandatory |
| `contains`, `required_for` | extra location ids freed when it is destroyed, and the event ids that need it destroyed |

- **Semantics** (plan §2.4):
  - With `persist = permanent`, destroying it sets `<id>.destroyed`, which opens every edge `through` it in both directions.
  - Any other value means respawn semantics: no flag, and the destroy requirement is re-checked on every crossing. The player destroys it where they stand (plan §2.4), so a crossing from A needs A in `destroy_from`, and its `contains` locations and the events of its `required_for` need their own node there (Step R1.5).
- **A generated barrier with `requires = null`** (5 `unknown` groups) needs `override_requires` before an edge may pass `through` it, and before any expression names it (`barrier:<id>:…`): "no gate goes unexplained" (plan §4.5). `override_requires = "false"`, with its reason, declares it out of logic. Until then it is an open gate in a stub and a load error in an authored level.
- **R0.4b answered I-2 and I-8** (§11). The generated `level`, `persist` and `requires` an edge relies on stay [inferred, static] per group (§3.3); draft 0's `TODO(R0.4b) I-2/I-8` line marks went when the realm steps authored every level (§4.10).

### 4.5 `[[button]]`

| Key | Meaning |
|---|---|
| `id` | §2.2 |
| `of` | optional: a generated keylock (coded), seal or obsidian lock. Each of those must be bound exactly once. Hand-only buttons, such as levers, have no `of` |
| `at` | the node it is pressed from |
| `mode` | `latch` (sets `<id>.open`) or `toggle` (non-monotone; plan §2.5 makes a toggle whose off state gates an edge a load error) |
| `requires` | extra, ANDed with the generated `requires` (the key, disc or obsidian count) |
| `override_requires`, `override_reason` | as for barriers |

A button bound to a generated gate whose `requires` is null (e5's four uncoded keylocks, the relays its coded locks drive) needs `override_requires`, as an undecoded barrier does (§4.4); until then it is never pressed (Step R1.5).

### 4.6 `[[event]]`

| Key | Meaning |
|---|---|
| `id` | the flag it sets (§2.3) |
| `of` | optional: a generated keylord (complete) or boss. Each of those must be bound exactly once |
| `at` | the node it happens at |
| `requires` | its condition (plan §2.7) |
| `terminal` | `true` for victory events: credited where they are reached, safe or not (plan §2.13 rule 4; §15). The game ends there, so nothing but `world.toml`'s `victory` may read one (§9 rule 21). The shipped `d1.spideyzar.killed` is one (D76; Step R1.6) |

### 4.7 `[[location]]` (optional overrides)

| Key | Meaning |
|---|---|
| `id` | a generated location id in this level |
| `requires` | an extra condition, ANDed |
| `exclude` | holds only useful items or filler (RQ-5/D81) |
| `farmable` | its source can be farmed, so it counts once (plan §2.8) |
| `proven` | D122: `{ by = "data", ref = "<the file or command that derives it>" }` (its requirement is exact from decoded data), `{ by = "xemu", ref = "<sitting>/<row>" }` (confirmed in xemu with margin), `{ by = "route", ref = "<the route step>" }` (D169: the vanilla route's kit there is within the logic's requirement, checked by the loader; with `unless = [<picks>]` and `only = [<items>]` when a skip outdoes it, AZ-725) or, D170, `{ by = "l3", ref = "<sitting>/<input string sha12>@<snapshot meta sha12>" }` (an L3 input string reaches it and comes back, and xemu replayed that string tick for tick: `devkit/reach/l3_certify.py`, `docs/SIMULATOR.md`). An `l3` ref resolves to a record in `proofs.jsonl` (`azurik-l3-proof/1`: the claim with the level's `zoning` (the sha256 of its derived `zones` section), the start as a recipe (loadvm, R7, R2, an R6 teleport named by its reach sample and the place struct's sha12, settle), the input string as run-length segments with the camera as f32 pairs, the L3 mode, the outcome (states, zones, least HP, the way back walked), the robustness and the matching replay, and an optional `retired` string marking a record whose start snapshot is gone (D1175: it still resolves; `l3-certify recheck` names it and passes over it); no coordinates, no RAM) whose claim is this location with the way back. Unmarked means not proven |
| `note` | free text |

- **Major items go only on proven spots** (D122, owner, 2026-10-12, answering Q260). The fill (Step R1.9) places a major item only on a pool location whose `proven` is set; a minor item may go on any reachable pool location.
  - A **major** is an item of class `progression` (§6): the element powers, the keys and the disc fragments. D122 names powers and keys; counting the disc fragments too is a default taken under D115 (they gate the seals and the disc teleports as keys gate locks), which the owner may narrow. **Minor** items are the rest: `progression_counted` (obsidians), `useful` and `filler`.
  - `by = "data"`: the location's whole effective requirement (§5.3: its node's reach, its `gated_by` and its `requires`) is exact from decoded data, with no [inferred] step. `by = "xemu"`: a sitting reached it with exactly the kit that requirement encodes, with margin (not at the edge of what the kit allows). `by = "route"` (D169, Step R1.8e): `route.toml` collects it at a step that replayed ok, and leaves it, holding no more than the logic requires there: under the most lenient options (every in-logic skip, every movement tier), for each counter the logic reads and in its bands (a count matters only at the thresholds the logic compares it with), the logic collects it neither with that counter a band below the route's kit before the step, every other counter in full, nor a band below the kit plus the spot's vanilla item when its escape picks up any progression item (`Logic.mark_short`, through `Logic.kit_short`). The vanilla run got there and back with that kit, so whatever the logic lets the fill do there, the run did with no more. A prefilled spot (a guardian slot, a key's spot, an unbounded generator) leaves holding its own item alone, since the fill puts no other there. `by = "l3"` (AZ-543, Step R1.29g): the record's string ran from a new game holding only its kit, so its kit is held to the same rule, the kit going in and the kit plus the spot's vanilla item leaving: a string must run at the logic's kit there or below, never at a convenient superset. The loader re-checks every route mark (a mark that fails is `bad_proven`), and the authoring writes one on each spot that passes and has no other mark. *AZ-725 (Step R2.18b):* a walk the logic outdoes only with some in-logic skips on still proves the spot where they are off: its mark names their picks, `unless` (D275's: a batch or a lone skip; the fewest a deletion over them in order keeps), checked with them toggled off and every other option at its most lenient, and `only`, the progression items whose counts still give the walk's way out with them on, each checked under the most lenient options with the spot holding that item alone. The fill's spot then takes any progression item under options that turn none of those skips on, and only the `only` items under options that do (`fill._Slots.holds`), so a skip changes no mark below its own tier.
  - No mark is inferred: a location without `proven` is not proven, whatever its evidence. *2026-10-25* [verified, `rando check`, §10]: 70 carry one (56 `by = "data"`, 11 `by = "l3"`, 2 `by = "xemu"`, 1 `by = "route"`), 54 of them non-gem spots (air 2, earth 9, fire 15, life and death 0, town and water 28). *On 2026-10-13,* 51 carried one: 50 `by = "data"`, realm 1's 33 (Step R1.8; Step R1.8c took the two behind w1's torpedo, w1's dark-cave obsidian and town's frag_water_2, whose hand requirement drops it, AZ-344), a3's two hub clusters (Step R1.11a), the fire realm's nine (Step R1.11b), d1's floor-1 sapphire cluster (Step R1.11d) and the earth realm's five (Step R1.11c: e2's circuitboard `e2/g0/r735`, all_fuel `e2/g0/r4415` and three clusters), and one `by = "xemu"`, w2's `w2/g0/r1364` (Step R1.8b) [verified: `rando check`, 2026-10-13]. *Step R1.8e:* one `by = "route"`, w2's `w2/g0/r1346` (vanilla power_water, route step 1: nothing held going in, and the logic lets no one leave the hose pool without water but by `w2.firewall02_air3` at air 3, which its mark names in `unless`, holding with it on for `power_water` and `power_water_a3` alone: AZ-725); of the route's 203 steps on authored pool spots (f2 and e5 included), it and `w2/g0/r1355` (already by data) pass, and the rest hold more than the logic asks (most often a power the logic opens the spot without, disc fragments, or obsidians past a lock's threshold; f2's and e5's conservative kits name only elements, and their power spots the logic leaves without the power the run left with). A `proven` mark on a location out of the pool is refused (it is never placed), so a fill on this draft can place no major outside the pre-filled guardian slots (RQ-4). It then fails whole (D35), naming the majors and the proven spots, and never falls back to an unproven spot. *Step R1.9:* with town and w1-w4 authored and 35 spots proven by data (20 of them open to a progression item: the others are town's ten obsidian-lock cages, its two dispensers and three gem clusters), the fill hosts the max options (ceiling 4, `frame_perfect`); under the defaults every attempt fails: with nothing placed the start reaches three non-gem spots before any progression item, all in w2 and none proven, so the fill fails naming the progression items and the proven spots (`tests/test_randomizer_fill.py`). *Step R1.8b:* sitting r18 proved one of the three, `w2/g0/r1364`, so the defaults fill when an attempt keeps that spot for the right item: seeds 1, 2 and x fill, and seed 0's 20 attempts all fail [verified: `tests/test_randomizer_fill.py`, 2026-10-13]. *Step R1.29:* the first five `by = "l3"` location marks (D170, AZ-455): `devkit/reach/l3_certify.py plan --spots` plans each spot from an arrival at the element kit its way there and back asks, and a mark is written only when xemu replays the string tick for tick and takes the spot's own item, from a start in the arrival node that isn't a teleport within 1 m of it, and the string comes back to that node; `apply` puts the mark in a conservative-kit spot's own `[[location]]`, beside its `requires`. With them `rando check` counts 48 proven non-gem spots (air 0, earth 9, fire 11, life_death 0, town_water 28) [verified: `rando check`, 2026-10-16]. *Step R2.18:* `w2.firewall02_air3` (the owner's X.67 run) stays held to keep that mark: in logic a player leaves w2's main body at air 3 with no water, so the logic would collect power_water's spot holding less than the route did, and with a rolled body (whose xemu proofs drop, AZ-607) no seed fills (AZ-725).
  - **D143 (owner, 2026-10-12):** "disc fragments count as major items", which confirms the default above: D122's proven-spot rule covers every `progression` item.
  - It is not an option: every settings file uses it (Q260's "confidence floor per preset" became this one rule; D144 retired the presets).

### 4.8 `[[skip]]` (D113)

A skip is a named, located use of one or more tricks (owner, 2026-10-12). It lives in the file of the level it is performed in. `tricks.toml` is the review superset: it adds each skip's difficulty reason, confidence, evidence, source and the clause it plugs into, and the loader checks that the keys below match it (§12).

| Key | Default | Meaning |
|---|---|---|
| `id` | required | §2.2 |
| `name` | required | the display name; the community's name where one exists ("Torpedo Skip", "Tree Song Skip") |
| `tricks` | required | the families it uses (`world.toml` names), at least one |
| `requires` | `"true"` | the items and powers it needs (§5); it may name other skips, with no cycle |
| `difficulty` | required unless `held` | 2 standard, 3 hard, 4 frame-perfect: movement's three tiers (D259, owner, 2026-10-18: "Yes, re-rate as proposed"; Safe, 1, folds into Standard, and the loader still reads a 1, which only the test databases hold). The hardest recoverable unit is graded (per hop, D254), the lower tier where sources disagree: standard is no precise timing, or windows of 3+ ticks and ±2.7° of aim, or 50%+ per attempt; hard a 2-tick window or ±1.3–2.7°, or 5–50%; frame-perfect a 1-tick window or under ±1.3°, or under 5% from the real retry point, or an exact string only. It replaces `tricks.toml`'s "the higher kept" rule and P13's robustness thresholds (the L3 tools' `TIERS`: 0.50 standard, 0.05 hard). A tjump or itrig skip is hard or above. A held skip may be unrated |
| `status` | required | `in_logic` (the settings may turn it on, by the ceiling or a toggle, §7.1), `held` (nothing turns it on until its hold is lifted; it evaluates false) or `manual` (outside the ceiling and the toggles; only a separate opt-in of the player's, with a spoiler warning, TODO §7.2). A skip using `saveanywhere` is `manual` or `held`, and a `manual` skip uses `saveanywhere` |
| `confirmed` | required | D114 (owner, 2026-10-12: "for unconfirmed tricks, like air 1 skipping the fire barrier, we need to confirm they work before introducing them in our logic"): `{ by = "xemu", ref = "<sitting>/<row>" }` (reproduced in xemu with exactly the kit its `requires` encodes; the row is one of `$RP/tricks/REPORT.md` §2, `<row>:<skip id>` for its per-skip templates), `{ by = "owner", ref = "<one of tricks.toml's owner_refs>" }` (the owner's words say it works as encoded; `owner_refs` lists the headings of `$RP/tricks/OWNER_TRICKS.md`, §12), `{ by = "l3", ref = "<sitting>/<input string sha12>@<snapshot meta sha12>" }` (D177, Step R1.8g: an L3 input string performs it with the kit its `requires` encodes and xemu replayed that string tick for tick; the ref resolves to a `proofs.jsonl` record whose claim is this skip, its kit and the most flaps it made in one jump, D183, and the kit is no more than the skip asks: its rule, the options and its `requires`, never holds with a counter a band below the kit's, as an `l3` edge's, AZ-544; since D277, owner, 2026-10-18: "any skip done by the simulator or agent is confirmed always", the L3 run alone, holding in whole steps, with no xemu replay owed: its record's `replay` is `{ rule = "D277" }`, Step R1.31) or `"no"`. An agent's or the owner's xemu sitting with that kit confirms it as `xemu` (D277). An `in_logic` or `manual` skip is never `"no"`: an unconfirmed skip is `held`, whatever its evidence |
| `from`, `to` | `""` | the edge it bypasses, as node ids (`""` = not yet placed) |
| `gates` | `[]` | the hand objects (barriers, buttons, events) it gets past |
| `tiers` | every tier | D145: the movement tiers (`safe`, `standard`, `hard`, `frame_perfect`; at least one, distinct, in that order) at which the skip adds reach over plain movement with its kit. A record, not a gate: turning a skip on at a tier where plain movement already reaches its target changes nothing, so the loader only checks the list. One skip carries it (`a6.rjump_platforms`: `hard`, `frame_perfect`) |
| `batch`, `batch_name` | — | D275 (owner, 2026-10-18: "i want to batch skips that are for the same thing (such as w1 fire wall to town) but have multiple entries (such as air 1 versus air 2) under the same skip"): the id (`<level>.<slug>`, no skip's or time-saver's) and display name of the batch this skip is a variant of. A batch's variants cross the same thing (one level, the same `from`, `to`, `gates` and `tricks`) and differ only in kit; there are two or more, under one name (`bad_batch`, rule 18). The player sees and picks the batch (one GUI row, one toggle, one share-string index, §7.2, §7.3); each variant keeps its own `requires`, `difficulty`, `status`, `confirmed` and evidence, the ceiling admits each by its own tier, and the logic and the fill read the variants (a clause names `skip:<variant id>`). Five batches: `w1.firewall01_beach_town` (air 2, air 1), `e2.steam_group` (air 2, air 1) and `e6.acidblock02` (air 2; air 1 and water 1 since Step R2.18) (Step R1.31), `f6.terraces` (air 2, air 1; Step R1.31b) and `e6.upper_ring_flutter` (air 2; air 1 and water 1; Step R2.18). Step R2.18 dropped Step R1.31's `w1.torpedo`: the owner refuted its air-1 variant (D628), which left the database |
| `note` | — | free text |

- **Where it is used.** An edge's `requires`, a barrier's `bypass` or `override_requires`, or any other expression names it as `skip:<id>` (§5.1). The `skip:` atom holds when the settings turn the skip on and its own `requires` holds (§5.4).
- **Generated skips.** A derived edge that uses a trick family (an rjump drop, a bskip pass, a stored air flap) is written as a skip with a generated id, such as `<level>.rjump.<from>.<to>.<kit>`, its difficulty taken from its envelope cell (`tricks.toml` `[[skip_rule]]`). Since D114 it is written `held` with `confirmed = "no"` until its own instance is reproduced or the owner confirms it.
- **What makes a skip (D145, owner, 2026-10-12)**, verbatim: "keep in mind some of the tricks you saw in the speedrun video are not skips, bur rather just meant to save time." A skip changes what is reachable: with its kit (`requires`) at a movement tier it reaches a location, zone, item, exit or event that plain movement with the same kit doesn't, or it bypasses a requirement (a gate, key, power, switch, event or darkness). A trick that only goes where plain movement with the same kit already goes, faster, is a time-saver (§4.9): no skip, and out of logic. Each `tricks.toml` skip says why it is one (`d145`, §12).

### 4.9 Time-savers (D145)

A time-saver goes where plain movement with the same kit already goes, only faster: a core-to-core shortcut, a ladder replaced by a drop, an elevator replaced by a fall. It gets no logic edge, no toggle and no ceiling count, and it owes no xemu confirmation. It is kept as a note the spoiler and the route may cite.

- **Where it lives.** `tricks.toml`'s `[[time_saver]]` holds each one in full (§12): what it replaces, its families and kit, the video refs, the time it saves, the plain route that reaches the same place, its evidence, its former skip state and the verdict (`d145`), and optionally what would make it a skip again (`reopen`). `world.toml` lists each one as `[[time_saver]]` with `id`, `name`, `level` and `tricks`, all required (§7), and the loader checks that list equals `tricks.toml`'s.
- **Never in logic, never in a level file.** The loader refuses a `skip:` atom naming a time-saver in any expression, a settings toggle naming one, and a level file that names one anywhere, comments included, so no level `[[skip]]` has a time-saver's id (§9 rule 22). A time-saver has none of a skip's logic keys (`status`, `confirmed`, `difficulty`, `requires`, `clause`, …): they are unknown keys, so nothing can turn it on. The solver reads only the level files' skips (§15), so it never sees one.
- **Back to a skip.** When the database changes so that a time-saver reaches something plain movement doesn't (keys are vanilla in v1, I-9; a modelled spring), it moves back to `[[skip]]`, held until confirmed (D114).
- **Today:** 39 (a1 3, a5 2, a6 4, d1 1, e2 8, e5 6, e6 3, f3 3, f6 1, town 1, w1 1, w2 1, w3 5) [verified, `rando check`, 2026-10-24]. 34 were skips before D145 (two of them in logic, `e6.firewall01_air1` and `w3.iceblock024_air1`), `a6.rjump_platforms_green` is the green-key instance split off `a6.rjump_platforms`, `e5.rjump_conveyor_ladder_air1` was a held skip until the owner's X.35 C3 reached its spot with air 1 by plain movement (Step R1.31b), and `w3.botstep_icebergs` until the owner called it a time save (D657, Step R2.17b). Step R2.18 moved two held skips the owner called time-savers at his X.67 demo: `f6.seal_skip` (D655: the in-logic terraces skips reach the fire guardian's fight without the seal) and `a5.rings_air_power3` (D656: his X.35 C1 run takes air power 3 with air 2).

### 4.10 Authored levels: `rando author` (Step R1.8)

An authored level's file, and its movement file (§17), are written by `python -m devkit rando author <levels>` (`devkit/rando/draft/author.py`; `docs/TOOLS.md`), every authored level together (one left out is named), from four inputs: its generated file, its derived file (§16), `tricks.toml` (its skips, projected as they are) and `devkit/rando/draft/authoring/<level>.toml`, the realm step's hand decisions. The file says so in its header; an edit goes into those inputs and the verb runs again (`--check` exits 1 unless every file is current, and `tests/test_reach_model.py` runs it).

- **Nodes are zones.** Only the zones that hold something logic reads are kept: a pool location, an exit's switch or an arrival, a button, an event, a barrier's `destroy_from`, a respawning barrier's far side, a zone the authoring names. Every other zone is a place a path passes through, so the zone graph is contracted onto the kept ones: between two kept zones, each movement tier's requirement is the union, over every path through zones that are not kept, of the conjunction of its edges' requirements (antichains of terms). Kept zones the safe tier joins both ways with no item, over floors and decoded gates alone, are one node, named after the authoring's name for one of its zones, else `<level>_z<NNN>` after its lowest zone. A node anchors its zones (`zone:`, §4.2), so the derive's location -> zone map gives each location its node (rule 3); a location the derive places on no floor gets one by the authoring (`[members]`, rule 1).
- **Edges.** A tier's requirement is written as one edge per difficulty (§4.3), holding only the terms that tier adds over the tier below. A term another path already gives, at a tier no higher, with a kit it meets and a confidence no weaker, is dropped (a transitive reduction, one term at a time against what is left, so every kit still reaches what it reached). `confidence` is `data` for floors and decoded gates, `physics` for a term that needs a modelled flight of the measured envelope, and `assumed` for a term that needs a probe-needed derived edge the authoring admits (its `probe` list names classes; `"<class>+1"` admits one a movement tier harder) or a hand edge; a probe-needed edge it doesn't admit stays out of logic (`logic = false`, R_phys only), and so does an admitted `rig` edge of a rig the authoring holds (`[rig_held]`, Step R1.11b: a ride whose decoded trigger, a seal or a kill, the probe edge doesn't carry, such as f6's Jaw), and any derived edge the authoring holds by itself (`[[held]]`, Step R1.31c: its `from` and `to` zones, with `via` one rig's ride; such as f3's archway door, pCubeShape283, whose rides up onto the archway's top a run from the pit measured out of reach while its other rides stay); a rig whose trigger the derive leaves undecoded and the authoring reads (`[rig_requires]`, Step X.16) carries it on every edge of its ride, R_phys's too, as life's final joystick pad (PlatShape) carries both top switches and e2's in-level minecart (MineCarRide2's car, Step R1.28) both circuitboard locks. A respawning barrier's crossing stands in for no other term, since its term leaves the barrier's destroy requirement out (Step R1.11b: the reduction had dropped f1's confirmed skip past flameSpout6). A generated skip the derive holds (D114) is false; a confirmed one stays a `skip:` atom, which places it.
- **Barriers.** Crossing a permanent barrier needs its `.destroyed` flag; a respawning one is crossed only from its `destroy_from` side, by a `through` edge (§4.4, §5.3); the barrier's own requirement leaves the crossing either way. `destroy_from` is the derive's, plus the authoring's.
- **The objects.** Each exit's edge leaves from the zone its switch overlaps (one that holds an arrival first, else the one it overlaps most) and ends at the node of its arrival in an authored level, else at the stub's node; the stubs' exits into an authored level get the `to` of their arrival's node the same way (the verb rewrites that one line of a stub's file). A button is pressed from its object's zone, a derived event (a pad touched, an arrival) is credited at the lowest zone that sets it, and the bosses, keylords and placements are the authoring's `[[event]]`s.
- **What the authoring holds** (each entry with its reason): `[names]` (node id -> one of its zones; the world's start and hub, and any node `tricks.toml` names), `probe`, `[rig_held]` (rig name -> reason), `[rig_one_way]` (rig name -> `way`, "up" or "down", and `why`: a rig whose movers only rise or only sink, a timer that doesn't repeat; its admitted guessed rides at least 1 m against that way stay out of logic, R_phys keeping them, since no ride carries the player that way and a drop beside a rising rig is kept only once L3 lands it alive, as a hand edge: AZ-589, Step R1.24a), `[[held]]` (a derived edge held out of logic, R_phys keeping it: `from` (none: every derived edge into `to`, Step R1.24b: f4's lava river), `to`, `via`, `why`, and `difficulty` to hold only the tiers from it up, which then read the tier below's requirement, AZ-532; with `pair = true`, every path between the two kept zones through zones that aren't kept, the authoring's own `[[edge]]` between them kept, Step R1.24b: d1's floor 7 to floor 6; one that matches no derived edge is an issue), `[rig_requires]` (rig name -> `requires`, `why`), `[gates]` (the requirement of a gate the derive left undecoded), `[gates_or]` (a confirmed skip's alternative to a decoded gate), `[members]`, `[[edge]]` (between zones, `assumed`), `[[event]]` (zone, requirement, `of`), `[exit."<id>"]` (`from`, `to` as a zone or a node, `requires`, `disc`), `[barrier."<id>"]` (overrides, `persist`, `destroy_from` zones), `[button]` (zones), `[dark]` (node -> `true` or its nolight skip), `[[location]]` overrides and `[[probed]]` walks (D170: `from` and `to` zones, the `kit` held, `proven`; each assumed or physics term of that node pair asking at least the kit becomes `probed`, at its tier, in a row of that walk's own, so its record backs every term of the row, AZ-544, and counts as exact for the data proofs below when its record's robustness under jitter is at least 0.80 (D187, owner, 2026-10-13; X.7's default was 0.95: a fragile string proves the connection, not that a player walks it safely); an xemu walk always counts). An L3 walk's record must claim the same zones under the level's current zoning (its derived `zones` section's sha256, which `rando author` never changes): zones are renumbered by a re-derive, so a stale walk is an authoring issue, never applied, until `python -m devkit reach l3-certify recheck --write` re-runs its string in L3 from the kept snapshot and re-zones it.
- **Proven by data** (D122): the tool marks each non-gem pool location `proven = { by = "data", … }` whose requirement is exact from decoded data: on a floor the derive placed it on, with no hand placement or extra requirement, and whose node a path of safe-tier edges that need no probe-needed or hand edge (floors, decoded gates and the measured envelope's safe flights) joins both ways with the level's arrivals and exits (a `probed` edge counts as exact when its walk's robustness is at least 0.80, D187, above). The authoring adds the `by = "xemu"` and `by = "l3"` marks of its sittings, then the `by = "route"` marks (D169) over the database the new files make.
- **What the derive needs beyond a zone** (Step R1.11a): a pool location the derive reaches only by a jump from its zone's floor (`how = jump`) gets that jump's requirement as its `requires` (the zone alone would make it free); one the derive holds over its zone (`requires = false`: floating with no spring, updraft or ledge it models, or walled) is an authoring error until a `[[location]]` `requires` or a `[members]` zone decides it.
- **The conservative-kit rule** (Step R1.11a's realm; default taken under D115; `draft/authoring/a1.toml`'s header): a pool location the derive places on no floor, reaches in no rung, or reaches only where it models no way back to an exit (a rig, a rotating ring, an air-landing teleport it drops) is joined to the level's arrival node and requires the elements the vanilla run holds when `route.toml` collects it (off the route: at the level's last step), plus that level's route actions before it (keylocks, seals). The vanilla run collects it with that kit, so the logic never asks for less than the game needs; the realm's probe sitting owes the mechanism.
- **The route.** An authored level's `route` is `route.toml`'s location steps in it, in order (§13).

## 5. Requirements

### 5.1 Grammar

```
expr     := and ( "|" and )*
and      := unary ( "&" unary )*
unary    := "(" expr ")" | atom
atom     := COUNTER ">=" INT                      # water>=2  disca>=3  obsidian>=60  key.battery>=1
          | "flag:" OBJ_ID                        # flag:w1.keylordSystem.killed  flag:town.obsidian_lock3.open
          | "skip:" SKIP_ID                       # skip:w1.torpedo_skip   (D113: a named, located use; §4.8)
          | "barrier:" OBJ_ID ":" ( "destroy" | "pass:" NODE "->" NODE )
          | "button:" OBJ_ID                      # = flag:<id>.open
          | "event:" OBJ_ID                       # = flag:<id>
          | "true" | "false"
COUNTER  := "air" | "water" | "fire" | "earth" | "disca" | "discw" | "discf" | "disce" | "discl"
          | "obsidian" | "sapphire" | "emerald" | "ruby" | "diamond" | "life" | "staff" | "ammo"
          | "key." KEYTYPE
OBJ_ID   := LEVEL ( "." PART )+                   # PART = [A-Za-z0-9_]+
SKIP_ID  := LEVEL ( "." SLUG )+                    # SLUG = [a-z0-9_]+ (§2.2); generated ids have more parts (§4.8)
```

- **Precedence:** `&` binds tighter than `|`. There is no negation: logic is monotone (plan §3.1). A data gate with a NOT, such as the disc teleport's "town has not placed the disc", is a declared mechanism (§7), not an expression. Counters are monotone because they count items collected; the game's gem values are not (§2.4).
- **Whitespace** is free. Tokens never contain spaces.
- **Fail closed.** An unknown token, an unknown counter or skip, or an id that doesn't resolve is a load error that names the file, the object and the field. The retired `trick:<name>@<tier>` atom and a bare trick name are parse errors that say to name a skip instead (D113).

### 5.2 The owner's shorthand

It is accepted on input. The database tool writes only the canonical form above.

| Shorthand | Canonical |
|---|---|
| `water1` | `water>=1` |
| `discw3` | `discw>=3` |
| `a+b` | `a & b` |
| `bskip` (a bare trick name) | refused since D113 (a trick has no tier): write the skip, `skip:<level>.<slug>` |

Bare lists (`[a, b]`) are refused (plan §2.2).

### 5.3 Where requirements come from

| Object | Effective requirement |
|---|---|
| barrier destroy | generated `requires` (or `override_requires`) `&` the hand `requires` |
| barrier pass A→B | `<id>.destroyed` (permanent), or the destroy requirement and the light at A when A is in `destroy_from` (respawn), `\|` the `bypass["A->B"]` expression |
| keylock button | generated `requires` (`key.<t>>=1`) `&` the hand `requires`; the key part is counted by §5.5 |
| seal / obsidian-lock button | generated `requires` `&` the hand `requires` |
| other button, event, edge | its own `requires` |
| location | its node is safe `&` each `gated_by` (§5.6) `&` the `[[location]]` `requires` |

### 5.4 Indirect atoms

- `barrier:` expands to the barrier's destroy or pass requirement (§5.3).
- `button:X` is `flag:X.open`, and `event:X` is `flag:X`.
- `skip:X` is true when the settings turn X on and X's own `requires` holds (§4.8). The settings turn X on when its status is `in_logic` (which needs a confirmation, D114, §4.8) and either the settings' `[skip_override]` says `true`, or it says nothing and X's difficulty is at or below `skip_ceiling` (§7.1); a `manual` skip only by the player's separate opt-in (TODO, §7.2); a `held` skip never. The atom appears only un-negated, so raising the ceiling or turning a skip on never shrinks R or Safe (plan §2.15).
- References may chain: barriers to buttons to keys. A cycle is a load error.

### 5.5 Keys

- **Consumed keys.** A lock uses up one key [verified static, 0x58AD0: RAM_RECIPES §4; re-read by the verifier, 2026-10-11]. In-game confirmation is I-9 (R0.4a).
- **The worst-case rule.** So the database tool replaces each coded keylock's `key.<t>>=1` with OoTMM-style worst-case counting (plan §2.6): `key.<t> >= 1 + (the other <t> locks reachable without passing this one)`, reachable in R_phys (§15): `logic = false` edges, every cart and every movement tier count, `assumes` don't, and toggles are pressed, since a player can do all of that anyway (plan §2.10, §2.13; Step R1.6).
- **The key rule** (Step R1.8l, AZ-345). Another lock L' spends none of lock L's keys when a key spent at L' is given back on the spot: a `<t>` key's pool location K (no `gated_by`, no container, not at a dark node) lies on every way to L' in R_phys (with every item, L never pressed: every path from the start to L''s node passes K's node), and every edge that leaves K's node toward L' without coming back asks at least K's own requirement (each conjunct, a counter at least as high), so whoever opens L' stood where K is with what taking it needs; when L' stands at K's node, K needs nothing. Each such L' is matched to its own K (a matching), and L needs `key.<t>` plus one for each matched K the placement puts there and nobody has taken yet `>= 1 +` the other locks. *Sound:* a player at L who opened a set S of the others collected the logic's keys and, for each matched L' in S, its own K too (that K, if the logic hadn't counted it yet, is one of the "still there" ones), so the keys left are at least the logic's count less the unmatched locks in S, at least 1; adding an item never lowers the left side (taking K adds one key and drops its one), so D113's monotonicity holds. Today it matches life's two `key_life1` (in life's hub, ahead of its two locks), so w1's water keylock opens with the bay keylord's key alone; d2's five lenses, d1's, e2's, f1's and f3's keys lying ahead of their own locks are matched the same way.
- **Where the counts go.** Draft 0 proposed `derived/keys.json`, for the owner to review and a test to re-derive; `derived/` holds only the reach model's files (§16), so the solver computes the counts in memory each time it compiles a database (§15; §9's "Not checked in v1").

### 5.6 `gated_by`

Each generated id in a location's `gated_by` becomes one atom:

| Gate | Atom |
|---|---|
| geode | the geode's generated `requires`, evaluated at the location's node (plan §2.4: containers, not barriers on edges) |
| keylord | `event:<the hand event bound to it>` |
| obsidian lock | `button:<the hand button bound to it>` |
| boss | `event:<the hand event bound to it>` |

A gate no hand object binds (e7's incomplete `keylordSystem5`) is false. The hand event's id need not be the generated `event`, which is only the draft's name for it (§2.2; Step R1.5).

Pool locations [verified, `db_extract.py`]:

| Spawns | Gated | Count |
|---|---|---|
| on load | no | 1,166 |
| on load | yes (keylord keys, obsidian-lock contents) | 17 |
| triggered | yes (231 geode gems, and the 4 boss-spawned 4th fragments) | 235 |
| triggered | no | 0 |

## 6. `items.toml`

- `format`.
- `[counters]`: name = description, for the fixed counters. `key.<type>` counters are implied by the key items.
- `[[item]]`, one per config item: `name`, `base` (for `_move` templates), `counters` (an inline table of counter → increment) and `class`.
  - `class` is one of `progression`, `progression_counted`, `useful` or `filler` (plan §3.3).
- The number of vanilla copies is a generated fact. It appears only in comments.

## 7. `world.toml` and `settings/`

- **`world.toml`:**
  - `format`;
  - `start` (`w1_beach`) and `hub` (`town_central`);
  - `victory` (an expression: `flag:d1.spideyzar.killed`, D76);
  - `starting_items`;
  - `[[trick]]`: `name` and `description`, a technique family with no tier (D113; `default_tier` is refused);
  - `[[time_saver]]`: `id`, `name`, `level` and `tricks` (D145, §4.9): listed for the spoiler, never in logic;
  - `[[mechanism]]`: `id`, `kind`, `handling` and `note`.
    - `kind` is one of `one_shot_teleport`, `respawn`, `toggle`, `capacity`, `cycle`, `cart` or `spend` (a counter the game decreases, such as the gems the fuel-cap upgrade spends, §2.4).
    - `handling` is one of `forfeitable`, `product_bit`, `out_of_logic`, `harmless` or `keys_vanilla`.
    - A cart edge's `lock`, a toggle button, a non-permanent barrier on an edge and the disc teleport each need a declared mechanism, or loading fails (plan §3.1).

### 7.1 The options (D144)

**D144 (owner, 2026-10-12)**, verbatim: "what if we get rid of presets, and just have skip and movement options that the user sets themselves? With the default being no skips and hard movement." The follow-up answers: dark areas default to "Fire 1"; "Yes, user-saved settings". There are no built-in presets. The player sets these options, and each has a default:

| Option | Values | Default | What it does |
|---|---|---|---|
| `skip_ceiling` | 0 none, 1 safe, 2 standard, 3 hard, 4 frame-perfect (D259 amends D144(1)'s scale: no skip is rated 1, so 1 turns on none; the format keeps it) | **0** | the `in_logic` skips rated at or below it are on (§4.8, §5.4) |
| `movement_tier` | `safe`, `standard`, `hard`, `frame_perfect` | **`standard`** (D186; `hard` until Step R1.2b, D144) | the `envelope/tiers.toml` tier for ordinary jumps and flaps: an edge whose `difficulty` (§4.3) is at or below the tier's number (1–4) is usable |
| `dark_fire` | 1, 2, 3 | **1** | a dark node or edge (§4.2, §4.3) needs `fire>=<dark_fire>`; an enabled nolight skip lifts that for its own dark area |
| `[skip_override]` | skip id → `true` or `false` | empty | the per-skip toggles; they win over the ceiling, but `true` never turns on a `held` or `manual` skip |

- **Which skips are on.** A skip is on when its status is `in_logic` (so it is confirmed, D114) and either its toggle says `true`, or it has no toggle and its difficulty is at or below `skip_ceiling`. A `held` skip is never on. A `false` toggle on a held skip is allowed: it keeps the skip off once it is confirmed. With the defaults no skip is on, and the skips on at ceiling 0, 1, 2, 3 and 4 with no toggle number 0, 0, 19, 39 and 41 [verified, `rando check`, 2026-10-25, with R2.18's and R2.18b's skips (§10); 0, 0, 17, 25 and 26 at Step R2.17b, 2026-10-24; 0, 0, 16, 23 and 24 after Step R1.31b; 0, 0, 15, 21 and 22 after Step R1.31; 0, 0, 15, 20 and 21 after D259's re-rating, Step R1.30, 2026-10-18; 0, 6, 9, 18 and 21 before it, 2026-10-14, after Step R1.8g's two L3 confirmations; 0, 6, 9, 17 and 19 before them; 0, 7, 10, 17 and 18 before D145 and sitting rjc5, §14].
- **`dark_fire` and the nolight skips.** A `dark` edge, and everything done at a `dark` node, needs `fire>=<dark_fire>`; when its `dark` names a nolight skip, `fire>=<dark_fire> | skip:<that skip>` (the `nolight` family's `clause_rule` in `tricks.toml`, adopted at Step R1.5: `dark = "<skip id>"`, §4.2; two nodes set it, w1's `w1_dark_cave` with `w1.dark_cave_nolight` and e7's `e7_dark_room` with `e7.dark_room_nolight`). A nolight skip the settings turn on, by the ceiling or a toggle, lifts the fire requirement for its own dark area only (the loader refuses it on another level's node or edge, or away from its `tricks.toml` `dark_node`, §9 rule 3), and every other dark area still needs `dark_fire`. The two nolight skips in logic are `w1.dark_cave_nolight` (2) and `e7.dark_room_nolight` (3), so the defaults lift neither.
  - The range is 1–3 [inferred: the light armor has three levels, 5/10/20 s per cast at fire 1/2/3, the `nolight` family's `mechanism`]. 0 is refused, because it would open every dark area without a confirmed nolight skip (default taken under D115).
- **Monotone.** Raising `skip_ceiling` or `movement_tier`, or turning a skip on, never shrinks R or Safe, because the `skip:` atom appears only un-negated (plan §2.15). Raising `dark_fire` never grows them [inferred].
- **Not options:** the proven-spot rule for majors (§4.7), `saveanywhere` (its skips are only `manual` or `held`) and the per-trick maximum tier (retired by D113).

### 7.2 Settings files (`settings/*.toml`)

A settings file holds one set of options. The database ships one, `settings/defaults.toml`, with D144's defaults. `randomize-full` (Step R1.10b) starts from it, reads a user-saved file (`--settings`) or a share string (`--share`), lets each option flag override them, and writes the build's settings to a user-saved file with the same schema (`--save-settings`; D144: "Yes, user-saved settings"); MCP `rando_build_iso` takes the same options, and its build report records the settings (this table) and their share string. `rando plan` reads a `--settings` file or a `--share` string through the same reader (Step R1.12). The GUI's Randomize page sets the options, the toggles and the excluded categories, shows the share string (and takes a typed or pasted one), and reads and writes settings files with Load settings… and Save settings… (Step R1.14). `rando check` checks every settings file.

| Key | Required | Meaning |
|---|---|---|
| `format` | yes | `"azurik-rando-settings/1"`, or `/2` (Step 2.90a), which differs only in `exclude_categories`' `powers` (below) |
| `skip_ceiling` | yes | an integer 0–4 (§7.1) |
| `movement_tier` | yes | `safe`, `standard`, `hard` or `frame_perfect` |
| `dark_fire` | yes | an integer 1–3 |
| `[skip_override]` | no (empty) | a pick → `true` or `false`: a batch's id (D275, §4.8), which turns its in-logic variants on or off, or a lone skip's. An old per-variant id loads as its batch, `true` when any of its ids is (the batch's own id, given too, wins); a file is written with the batch's id |
| `exclude_categories` | no (empty) | the item categories whose items keep their vanilla places (Step R1.10b; the Randomize page's unticked item rows, `--exclude-category`): a list of `fragments` (disc fragments; the guardians' 4th stay vanilla anyway, D81), `powers` (the 12 elemental powers), `gems` (single gems and clusters), `obsidians`, `consumables` (fuel and health) and `upgrades` (Step 2.90a: the 8 upgrades, `power_life`, `power_staff1`, `power_staff2` and `power_ammo`), each at most once, in that order. In format `/1`, `powers` keeps the upgrades too (every `power_*`, its meaning before Step 2.90a), so both kept are written `["powers"]` and their `settings_digest` and plans are unchanged; only the elemental powers kept without the upgrades are written in `/2`, where `powers` is the 12 alone. Keys stay vanilla whatever it says (I-9) |

- **Every option is written,** `defaults.toml` included. A saved file never leans on the defaults, so it means the same thing after a default changes (the default preset changed with D118 and D142, and D144 replaced it). Default taken under D115. `exclude_categories` is the exception: absent means empty (every category shuffles), `--save-settings` writes it always, and a plan's settings table holds it only when it names a category, so a setting without one keeps its `settings_digest` and its plans (default taken under D115, Step R1.10b).
- **Fail closed,** like every database file (§9 rules 1 and 12). Each of these is refused, naming the file, the key and the skip id:
  - an unknown key, including the retired preset keys `name`, `default`, `[knobs]` and `[tricks]`;
  - a missing option, or an option out of range;
  - a toggle naming a skip the database doesn't have;
  - a `true` toggle on a `held` or `manual` skip.

  A file saved against an older database is refused if one of its toggles names a skip that has since been renamed or removed. TODO (4.10): whether the GUI offers to drop that toggle.
- **`defaults.toml` holds D144's defaults exactly**, with D186's tier (0, `standard`, 1, no toggle). The loader refuses any difference (`defaults_differ_from_d144`), so a new default needs a recorded decision.
- **A leftover `presets/` file is refused** (`retired_presets`): it would look like a setting.
- **Where user-saved files live:** wherever the player saves them: the GUI's Save settings… asks through the OS save dialog, which refuses the input ISO, the output and `iso/` (D36; Step R1.14, default taken under D115). The proposal for AzurKit is one file per saved set, named by the player, in the user data dir (the one the ISO resolver uses, §6a.5). The loader checks every `settings/*.toml`, so a user-saved file put there is checked too.
- **Reserved, TODO.** The v1 loader refuses these as unknown keys until a later version defines them:
  - `seed`: the seed (its type and range are TODO);
  - `[pools]`: which item classes and pools are shuffled beyond `exclude_categories` (plan §3.3; TODO);
  - the opt-in for a `manual` skip. The proposal is a separate `[manual_skip]` table (skip id → `true`): the player's own choice, with a spoiler warning, never reached by the ceiling or `[skip_override]` (D144: a toggle never turns on a held or manual skip). Two skips are `manual`, `w1.hidden_airship_saveanywhere` and `w3.water_guardian_no_seal` (both manual since Step R2.18) [verified, `rando check`, 2026-10-25: 41 `in_logic`, 2 `held`, 2 `manual`], and v1 offers no opt-in (Q294), so no setting turns them on.

### 7.3 The share string

The share string is a settings file's compact, versioned and lossless text form, short enough to paste in chat. `src/azurkit/tools/randomizer/planner/settings.py` implements it (`share_encode`, `share_decode`), and the loader round-trips every settings file. Decoding checks the options and toggles as a settings file's are (§7.2), so a string can't turn on a held or manual skip either.

- **Text:** `AZR-`, then the payload in RFC 4648 base32, upper case, with no `=` padding. A decoder accepts lower case and surrounding spaces.
- **Payload, version 0** (no excluded category), **version 1** (Step R1.10b: version 0's fields, then one more byte), **version 2** (AZ-383, Step R1.19: version 1's fields, then the build's movement sliders) **and version 3** (Step 2.90a: version 2's fields, the slider count may be 0, and the mask's `powers` bit is the elemental powers alone):

  | Bytes | Field |
  |---|---|
  | 0 | the version: `0` for this layout, `1` with the category mask below, `2` with the mask and the movement sliders, `3` as `2` when the elemental powers are kept without the upgrades; a decoder refuses any other |
  | 1 | bits 0–2 `skip_ceiling` (0–4); bits 3–4 `movement_tier` (0 safe, 1 standard, 2 hard, 3 frame_perfect); bits 5–6 `dark_fire` − 1 (0–2); bit 7 set when toggles follow |
  | 2–5 | only with bit 7: the skip registry tag, the first 4 bytes of the sha256 of the database's picks (D275: each batch's id once and every other `[[skip]]`'s id, any status), sorted, each followed by LF |
  | then | only with bit 7: the toggle count n ≥ 1 (unsigned LEB128), then n LEB128 values, each `gap << 1 \| value`. `value` is 1 for `true` and 0 for `false`; the pick's index in the sorted registry is the previous index + `gap` + 1, counting from −1, so the indices strictly increase |
  | then | only in versions 1–3: `exclude_categories` as a mask, bit i for the i-th of `fragments`, `powers`, `gems`, `obsidians`, `consumables`, `upgrades` (bit 5, Step 2.90a: append only); no bit past them, and in version 1 never 0 (that is version 0). In versions 1 and 2 the `powers` bit keeps the upgrades too (a format `/1` file's meaning), so both kept set bit 1 alone (bits 1 and 5 together are not canonical) and the upgrades alone set bit 5; version 3 holds the elemental powers kept alone |
  | then | only in versions 2 and 3: the count n of movement sliders (n ≥ 1 in version 2) set otherwise than vanilla (one byte), then n of: the slider's index in `settings.SHARE_SLIDERS` (one byte; the 15 of `physics.SLIDERS`, append only) and its value (float64, little-endian), indices strictly increasing. The logic of the plan is re-checked under them (Step R1.14b), so the string replays the plan; a settings file can't hold them (it stays `/1`), a plan file's `share` and a build's placement file (`sliders`) do |

- **Canonical.** A decoder refuses an out-of-range field, trailing bytes, and any string that doesn't re-encode to itself, so each set of options has exactly one string.
- **The registry tag.** It ties a string with toggles to the database it was made for: another database refuses it ("made for another skip registry: load the settings file instead"). A string with no toggle carries no tag and works with any database. The settings file is the durable form; the string is the compact one. A string made before its batches (Step R1.31: the tag of every skip's own id, sorted, `710ca8a0` for that step's 42) still decodes against the same skips: its indices name the variants, and each loads as its batch (§7.2); the string is canonical against that registry.
- **Sizes.** With no toggle the payload is 2 bytes: `AZR-` and 4 characters. The defaults are `AZR-AAEA` (D186's standard movement; `AZR-AAIA`, D144's hard, still decodes) [verified, `rando check`, 2026-10-13]. Toggles add a 4-byte tag and a count, then 1 byte each while the gap from the previous toggle is under 64 skips (2 bytes under 8,192); a scratch example's 4 toggles, each 1 byte, made 22 characters in all [verified, a round trip through `share_encode` and `share_decode`, 2026-10-12].
- **Later versions** append the seed and the item pools after the sliders and change byte 0 (TODO, with §7.2's reserved keys). Version 1 leaves every version-0 string as it was: a setting with no excluded category keeps its string (`AZR-AAIA` for the defaults); version 2 is written only with a slider off vanilla, so every other string stays as it was (`AZR-AAEA`).
- **Why indices and not ids** (default taken under D115): a sorted id list is lossless across database versions, but costs about 30 characters a skip. The settings file already carries the ids, so the string takes the compact form, and the tag guards it.

### 7.4 The spoiler (D144)

Each seed's spoiler records:
- the options as set: every option, each toggle by skip id, and the excluded categories ("kept vanilla");
- the share string and the skip registry tag;
- the `db_digest` (§9);
- the skips that are on, by id.

**The plan file** (Step R1.9; `src/azurkit/tools/randomizer/planner/plan.py`): one JSON object, sorted keys, one-space indentation, a trailing newline: `format` (`azurik-rando-plan/1`), `generator` (the fill's version, `azurik-rando-fill/4` since Step R1.37 kept progression and obsidians off unsaved spots, `/3` since Step R1.8m's repairs, `/2` since Step R1.12's trap gate, bumped when the same inputs give another placement), `seed` (the user's string), `attempt` (the first of up to 20 that passed), `settings` (the options as a settings file holds them, §7.2), `share` (§7.3), `settings_digest` (the sha256 of that settings table's canonical JSON), `db_digest` (§9), `placement` (every authored level's pool location -> its `items.toml` name; the writer's input, `writer.layout`, and `randomize-full`'s layer 1, Step R1.10b) and `sha256` (of the canonical JSON of the rest: sorted keys, no spaces, ASCII). Reading one refuses another format or generator, a sha256 that doesn't match and a different `db_digest` (plan §3.5). The streams: `sub_seed(name)` is the first 8 bytes of sha256(seed, name, settings_digest), NUL-separated; the passes draw from `progression` (the progression items, then the obsidians), `useful` and `filler`, and attempt k > 0 from `attempt<k>/<pass>`; the pre-fill draws nothing.

**The spoiler** (Steps R1.9, R1.12; `rando spoiler`, `planner/plan.py`'s `spoiler_lines`), a pure function of the plan and the database. In order: the plan's sha256, seed, attempt and generator; the settings (every option, each toggle by pick, a batch's or a skip's id, D275, the categories kept vanilla) with the share string and the skip registry tag; the `db_digest` and the authored levels the plan places; the skips that are on, grouped by trick family, a batch once with the kits of its variants on (which of them a route needs isn't computed: default taken under D115); D82's statement that no settings are softlock-free before R2.1. Then the spheres, the solver's rounds on the whole placement (`Logic.reach`'s `trace`), each with its progression items and its obsidian count, and for each progression item an obtain path (start to its node, the state its round starts from) and a return path (its node to the start, with the item; when that finds none, the state the round's escape reaches, which picks up what it passes, §15). Every progression location gets its paths: with `full` accessibility every location belongs to the seed, so AP's culled playthrough isn't printed (default taken under D115). Then the danger list: the traps (§15), ranked new trick-free (the trap gate refuses them), known, then those only a skip gets into, each with the spheres at whose state it is one ("with everything collected" when only the last round finds it); each `assumes` edge with the first sphere whose state credits its flags; the forfeitable locations with their region; each no-return region with its nodes, the sphere its slot is collected in and the disc count then (its gate is computed per node, §15) and its traps after completion; the dangerous saves, the save points at a trap or a trap after completion (a save point's node is the node anchoring it or its derived zone, or a stub's one node; an unplaced one, such as w1's `w1_1` on its rig, has none); and the excluded locations (RQ-5: marked `exclude`, or behind a lock that needs a full clear, lock 10, or a spot the level doesn't save, AZ-467). `randomize-full --spoiler FILE` writes it for a build, with the build's `logic_verified` on its second line (Step R1.10b).

### 7.5 Compatibility example: the retired presets as option sets

This is what each retired preset (D142's table, the last) would turn on today as a set of options [verified, `db_check`'s `compat_presets_d142` and `tricks_check`'s `compat_presets_d142_on`, 2026-10-12, recomputed at `$RP` `7530b0b` after D145 and sitting rjc5]. It is an example, not settings: nothing loads it.

| Was preset | `skip_ceiling` | `movement_tier` | `dark_fire` | Skips on | Nolight skips on | Share string |
|---|---|---|---|---|---|---|
| glitchless | 0 | hard | 2 | 0 | 0 | `AZR-AAYA` |
| easy | 1 | safe | 2 | 6 | 0 | `AZR-AAQQ` |
| normal | 2 | standard | 1 | 9 | 1 | `AZR-AAFA` |
| hard | 3 | hard | 1 | 17 | 2 | `AZR-AAJQ` |
| expert | 4 | frame_perfect | 1 | 19 | 2 | `AZR-AAOA` |
| **the defaults (D186; D144 until Step R1.2b)** | **0** | **standard** (was hard) | **1** | **0** | 0 | `AZR-AAEA` (was `AZR-AAIA`) |

- The defaults are the old glitchless with `dark_fire` 1 instead of 2.
- Before D145 and rjc5 the skips on were 7, 10, 17 and 18. D145 took out `e6.firewall01_air1` (rated 1) and `w3.iceblock024_air1` (rated 2), time-savers now (§4.9); rjc5 put in `w4.rjump_leaves` (2), `a6.rjump_platforms` (4) and `life.rjump_second_switch` (3). The share strings are unchanged (no toggle, so no registry tag).

### 7.6 History: from presets to settings (D113 → D144)

- **R0.6 (2026-10-11):** four presets, easy, normal (the default), hard and expert. Each had a `[tricks]` table (trick → maximum tier, 0 = off) and `[knobs] dark_fire`.
- **D113 (2026-10-12):** a skip ceiling plus per-skip overrides replaced `[tricks]`.
- **D118 and D129 (2026-10-12):** a fifth preset, glitchless, with no skips at all; normal turned on every safe-rated skip; every preset recorded a `movement_tier`.
- **D142 (2026-10-12):** glitchless became the default, with hard movement; easy turned on the safe skips and normal the skips up to standard.
- **D144 (2026-10-12):** no presets. The player sets the options of §7.1; D144's defaults are in `settings/defaults.toml`; the choices are saved to a settings file (§7.2) and a share string (§7.3), and the spoiler records them (§7.4).

**The preset files' values over time** (from their comments, before D144 deleted them):

| Preset | R0.6 `[tricks]` | D113 | D118 | D129 `movement_tier` | D142 | `dark_fire` |
|---|---|---|---|---|---|---|
| easy | every trick 0 | `skip_ceiling` 0 | unchanged | safe | ceiling 1 | 2 |
| normal (the default until D142) | bskip 1, nolight 1, the rest 0 | ceiling 1, with `false` overrides keeping pstorage off (the two air flaps; the six gates were added after the skips-b/-c sittings, default taken under D115) | ceiling 1, the eight overrides removed | safe | ceiling 2, standard | 1 |
| hard | every trick 3, saveanywhere 0 | ceiling 3 | unchanged | hard | unchanged | 1 |
| expert | every trick 5, saveanywhere 0 | ceiling 4 | unchanged | frame_perfect | unchanged | 1 |
| glitchless | — | — | new: ceiling 0, no override | safe | the default, hard | 2 |

> **Superseded by D144 (kept for the record).** No preset file exists and none is loaded; a leftover one is refused (§7.2). What follows is §7's preset text as of D142.

- **`presets/<name>.toml`:** `format`, `name`, `default` (true on exactly one), `skip_ceiling` (0 none, or 1–4: the skips rated at or below it are on), `movement_tier` (required, D129: `safe`, `standard`, `hard` or `frame_perfect`, the `envelope/tiers.toml` tier for ordinary jumps and flaps, numbered 1–4 like an edge's `difficulty`, §4.3), `[skip_override]` (skip id → `true` or `false`, which wins over the ceiling; it never turns on a `held` or `manual` skip, so `saveanywhere` stays outside every preset) and `[knobs]` (`dark_fire`). The per-trick `[tricks]` table (trick → maximum tier) is retired (D113).
- **The five presets** (D118 and D129, owner, 2026-10-12) [verified, `db_check`'s `presets_skips_on` and `presets_movement_tier`, 2026-10-12, before D144 removed both keys]:

  | Preset | `default` | `skip_ceiling` | `movement_tier` | `dark_fire` | Skips on today |
  |---|---|---|---|---|---|
  | glitchless | **true** | 0 | hard | 2 | 0 |
  | easy | false | 1 | safe | 2 | 7 |
  | normal | false | 2 | standard | 1 | 10 |
  | hard | false | 3 | hard | 1 | 17 |
  | expert | false | 4 | frame_perfect | 1 | 18 |

  - **D142 (owner, 2026-10-12)**, verbatim: "make the default glitchless, also make glitchless allow hard movement difficulty while not allowing skips. easy will allow skips but have safe movement difficulty". The follow-up answer: "Easy safe skips; Normal standard".
    - Glitchless is the default: no skips, hard movement.
    - Easy turns on the safe-rated skips, with safe movement.
    - Normal turns on skips up to standard, with standard movement.
    - Hard and Expert are unchanged.
    - This supersedes the D118/D129 rows below where they differ.
  - **D118:** normal turns on every safe-rated skip: ceiling 1 with no `false` override, so the six pstorage gate skips are on with `e6.firewall01_air1` (the eight overrides that kept pstorage off are removed). Glitchless has no skips at all: ceiling 0 and no `true` override, with easy's lenient knobs. Glitchless and easy are equal in effect today; glitchless stays at 0 by definition.
  - **D129:** glitchless, easy and normal use the safe envelope for ordinary jumps and flaps, hard the hard one and expert the frame-perfect one.

## 8. Draft conventions

- **Line marks** (the R0.6 drafts only):
  - `# migrated, unverified`: the line came from `logic_db.json` v3 (main @ `0e048a3`, sha256[:12] `7fdccfff3784`), with its requirement translated (§8.1);
  - `# prefilled`: written from `generated/` (decoded data) or a recorded decision;
  - `TODO(...)`: the owner (R0.7) or an xemu sitting (R0.4/R0.5) fills it.
- **Empty strings** (`from = ""`, `exit = ""`, `at = ""`) mark an open field, and so do an empty `destroy_from`, a node with no `anchors` and a level with no `route`. The loader counts them in a stub and refuses them in an authored level (§4.1); `rando check` prints the counts.

### 8.1 The migration's translation

| logic_db | Draft |
|---|---|
| `power_<e>` | `<e>>=1`. Level 1 now counts any power of that element, which fixes AUDIT new A (`power_water_a3`) |
| `power_<e>_L<n>` | `<e>>=<n>` |
| named fragments `frag_<d>_k` | `disc<x>>=<how many were named>` (the owner's counting model) |
| `disc_<d>` | `disc<x>>=4` |
| `drill_key` | `key.battery>=1` [inferred; e2 `earth_keylock2` takes key_battery and drives `DrillToggle`, `wiring/prefabs_summary.txt`] |
| events | flags, renamed (`event_defeat_w1_keylord` → `w1.keylordSystem.killed`) |
| `town_core` | `town_central` |
| `barrier_map` | dropped: barrier requirements come from data (§3.3) |
| victory | `flag:d1.spideyzar.killed` (D76) |
| a sealed node's edge to town | `kind = "teleport"` with `disc` |

Each draft line keeps the original requirement in its comment.

## 9. Load checks (Step R1.4)

`check_database` (`src/azurkit/tools/randomizer/planner/loader.py`) applies every rule below and names each problem by file, object and field, with a stable code; `load_database` raises one error that holds them all (its `issues`); `python -m devkit rando check` prints them and exits 1. The loader refuses:
1. a file whose `format` it doesn't know, an unknown key, a missing required key, a value of the wrong type, or an enum value outside its list (`kind`, `status`, `mode`, `class`, `handling`, `persist`, `arrival_by`, `movement_tier`, `confidence`, `disc`, `difficulty`); an unknown file or folder in the database (§1);
2. a parse error in any expression (§5), the generated requirements included;
3. an unresolved id: a node, a generated id (of the right kind, in the right level), a cell, barrier, button, event, flag, counter, item, trick family, skip or mechanism; an edge's `from`, or a walk or drop edge's `to`, in another level; an exit edge whose `to` is in another level than its exit's destination; a teleporter route whose `to` is not one of its locators, or a pad that is not an id of its level (§3.6); a generated location's `item` that `items.toml` doesn't define (`unknown_item`); a node's or edge's `dark` that names no skip, a skip outside the `nolight` family (`dark_skip_not_nolight`), a skip of another level (`dark_skip_other_level`), or a skip whose `tricks.toml` `dark_node` is not the node or one of the edge's ends (`dark_skip_other_area`, §4.2); a `zone:` anchor that is no zone of the level's derived file (`unresolved_zone`), or a zone two nodes anchor (`zone_in_two_nodes`, §4.2);
4. a generated gate object that isn't bound exactly once (§4.4–§4.6); a live exit that no edge, or two edges, bind; an edge that binds a dead exit;
5. a node id or object id whose level prefix doesn't match its file;
6. an `exit` edge with `through`;
7. a `cart` edge without a declared `lock` (a `world.toml` mechanism of kind `cart`);
8. a toggle button gating an edge in logic: named in the edge's `requires` (`button:<id>` or `flag:<id>.open`), or reached through its `barrier:` and `skip:` expansions or the barriers it passes;
9. a pool location with no node (§4.2) in an authored level (a stub's are counted, §4.1);
10. a `start` or `hub` that isn't the one node marked so; a start and hub that don't reach each other with every item (plan §2.13 rule 1; `start_hub_apart`, Step R1.6): with every counter at its maximum, no skip and the `safe` tier, the solver must find the hub safe (§15), that is reached from the start and able to get back to it, so it holds under any options. It runs only when every other check passes;
11. a `derived/` file (§16) that is not a gzip-compressed `<level>.json.gz` holding a JSON object with `_meta.format` `azurik-rando-derived/1`, a playable level that has generated data (`derived_unknown_level`) and a sha256 `_meta.stamp` (`derived_no_stamp`); whether the stamp is current is the derive's own check (`rando derive --check`, and `tests/test_reach_model.py`), which needs the draft tools the planner never imports;
12. a settings file (§7.2, D144) with a missing option, `skip_ceiling` outside 0–4, a `movement_tier` outside its four values (D129), `dark_fire` outside 1–3, a toggle naming an unknown skip, or a `true` toggle on a `held` or `manual` skip; a `settings/defaults.toml` that is missing or differs from D144's defaults; a leftover `presets/` file; a skip with an unknown family, no difficulty while not `held`, a difficulty outside 1–4, a `saveanywhere` family while not `manual` or `held`, or a reference cycle through other skips; a skip with no or a malformed `confirmed`, an xemu ref not of the form `<sitting>/<row>[:<skip id>]`, an owner ref that `tricks.toml`'s `owner_refs` doesn't list, an `l3` ref with no `proofs.jsonl` record claiming that skip, or one whose record's kit holds more than the skip asks (AZ-544; checked once the rest loads), or an `in_logic` or `manual` skip whose `confirmed` is `"no"` (D114), in a level file or on any `tricks.toml` row;
13. a `[[location]]` whose `proven` is not `{ by = "data" | "xemu" | "l3" | "route", ref = <a non-empty string> }` (D122; an `l3` ref is `<sitting>/<string sha12>@<meta sha12>`, D170), or an `[[edge]]` whose `proven` is not `{ by = "xemu" | "l3", ref }` or isn't `probed`. A `proven` mark on a location out of the pool is refused too, and so is a `by = "route"` mark the route doesn't prove (D169, §4.7; an `unless` that names no in-logic skip's pick, or an `only` that names no progression item, AZ-725; `unless` and `only` on any other mark; checked once the rest loads), or a `by = "l3"` location or edge mark whose record's kit names a counter that isn't one or that the logic asks less than there (AZ-543 for a location, the same check; AZ-544 for an edge, by its own rule). An `l3` ref that resolves to no `proofs.jsonl` record, or to a record claiming another location or edge, is refused (`bad_proven`); a `proofs.jsonl` line that is no record (malformed, a location claim without the way back, a kit that doesn't map counters to non-negative integers, a coordinate, a repeated ref) is refused (`bad_proof`);
14. an undeclared non-monotone mechanism (plan §3.1, §7): a toggle button with no `toggle` mechanism, a non-permanent barrier an edge passes with no `respawn` mechanism, a disc teleport with no `one_shot_teleport` mechanism, or whose disc has not exactly one guardian slot (a pool location with `guardian_slot` whose item is one of that disc's fragments; `disc_teleport_slot`, Step R1.7: the slot is what spends the teleport);
15. an unexplained gate (plan §4.5): an undecoded barrier (§4.4) that an expression names or an edge passes, or that an authored level binds without `override_requires`;
16. an open field in an authored level (§8);
17. a reference cycle through `barrier:` or `skip:` expansions (§5.4);
18. a `tricks.toml` rule (§12), and a level `[[skip]]` that differs from its projection; a batch (D275, §4.8) with one variant, variants of other levels, other ends, gates or tricks, a variant naming `batch` without `batch_name` or with another name, or an id that is a skip's or a time-saver's or not `<level>.<slug>` (`bad_batch`);
19. a `route.toml` rule (§13); a draft route's unresolved references, and the locations it misses or repeats, are counted, not refused, but a step whose item or class differs from the vanilla data is refused in a draft route too;
20. a non-integer number or a repeated key in a generated file (no coordinates, plan §4.4), and in any TOML file a coordinate-like number triple or a run of 16 or more hex digits (D87);
21. a terminal event (§4.6) that anything the solver reads, other than `world.toml`'s `victory`, reads: a requirement (`flag:` or `event:`) or an `assumes` in a level file, or a location `gated_by` the gate the event is bound to (§5.6) (`terminal_event_read`, Step R1.6; plan §2.13 rule 4: the game ends there, so nothing can follow it; default taken under D115: refused, not ignored, D35). The route and `tricks.toml`'s pending changes are no solver input.
22. a time-saver in logic (D145, §4.9): a `skip:` atom naming one in any expression (`time_saver_in_logic`, `tricks.toml`'s own clauses and a time-saver's `kit` included), a settings toggle naming one (`time_saver_in_logic`), or a level file naming one anywhere, comments included (`time_saver_named_in_level_file`); a `[[time_saver]]` whose id is another's or a skip's (`time_saver_id_duplicate`), whose id's level prefix is not its `level` file, with a skip's logic key (an unknown key, rule 1), no or an unregistered family, a video ref not `<video id>@mm:ss` (`bad_video_ref`), an empty `saves`, `plain`, `was` or `d145` (`empty_field`), a `from`, `to` or gate that doesn't resolve, or a `kit` that names a skip (`time_saver_kit_names_skip`); a `world.toml` time-saver list that doesn't list each of `tricks.toml`'s once with its name, level and tricks (`time_saver_projection_differs`); a `tricks.toml` skip with an empty `d145`; and a skip whose `tiers` is not a non-empty list of distinct movement tiers in tier order (`bad_tiers`), in a level file or in `tricks.toml`.

23. a `movement/` file (§17) that isn't a `<level>.json` holding `format` `azurik-rando-movement/1` and its six keys, that isn't an authored level's, or whose edge row (from, to, difficulty, confidence and `through`, its terms joined as the level file's `requires`), node or jumped-to location the level file or the level's pool doesn't have (`movement_stale`: re-run `rando author`; Step R1.14b); a `contact.json` that isn't `format` `azurik-rando-contact/1` with `flights` and `free`, or a flight whose certificate is in no movement file of its level (`contact_stale`: re-measure with `devkit/reach/l3_contact.py`; Step X.11).

- **Not checked in v1:** §5.5's worst-case key counts, the no-return regions and the forfeitable locations as reviewed `derived/` files (the solver computes them in memory, §15).
- **The tests these feed** (plan §3.7), in `tests/test_randomizer_logic.py` and `tests/test_randomizer_settings.py`, on the toy database `tests/rando/toydb/` (t1 authored, t2 a stub):
  - `test_requirement_parser_accepts_owner_shorthand_and_rejects_unknown_tokens` (1–2);
  - `test_loader_refuses_each_rule_a_database_breaks_naming_where`, one case per refusal in its `_REFUSALS` table (1, 3, 4, 7–10, 12–16, 18–21; D114, D122, D143), after the toy database loads clean with a node for each authored pool location;
  - `test_settings_refuse_a_toggle_that_turns_on_a_held_or_manual_skip` (12; D144: a settings file and a share string, which counts only against its own skip registry);
  - `test_a_time_saver_is_read_but_never_reaches_logic_a_toggle_or_a_ceiling_count` (22; D145: the shipped time-savers are no skips, and the toy database's one is refused in each way into logic);
  - `test_rando_check_prints_what_is_open_and_exits_1_naming_each_error` (the verb);
  - `test_committed_database_loads_with_no_error_and_counts_what_is_open` (the shipped database, with Step R1.1's generated files: 0 errors, §10's open counts, and its skips and defaults);
  - `tests/test_packaging.py::test_the_wheel_ships_every_file_of_the_randomizer_database` (a wheel install finds the database);
  - `test_fresh_extract_matches_the_committed_generated_data` (Step R1.1, vanilla tier: the generated files' byte equality);
  - the solver's, on `tests/rando/reachdb/`, `tests/rando/escapedb/` and `tests/rando/guardiandb/` (§15): `test_committed_valid_plans_solve_and_invalid_plans_do_not`, `test_adding_an_item_flag_or_skip_never_shrinks_the_safe_set`, `test_guardian_region_is_in_logic_only_with_three_of_its_disc_and_the_boss_requirements`, `test_a_toggle_or_a_respawning_barrier_is_in_logic_only_while_its_mechanism_is_harmless_and_physically_always`, `test_physical_reach_takes_the_edges_out_of_logic_and_only_the_skips_that_are_on` (with a dark edge at fire 1 whatever `dark_fire`, and a node out of logic that a player gets back from, no trap) and `test_solver_refuses_a_placement_item_flag_or_option_it_cannot_honour`;
  - `tests/test_movement_envelope.py::test_movement_tiers_are_the_planners_and_monotone_and_their_lip_lift_windows_nest` (the planner's movement tiers and an edge's `difficulty` values are `draft/tiers.toml`'s, §4.3).
- **The `db_digest`** (plan §3.5; Step R1.9, `planner/fill.py`'s `db_digest`) is the sha256 of the canonical JSON of what the solver and the fill read: the generated files without `_meta`, the level files, `items.toml`, `world.toml` and each location's node, with every `note`, `description`, hint (§3.8) and the `name` of anything that has an `id` dropped (TOML comments never load). `tricks.toml`'s review material, `route.toml` and the settings files are not in it.

## 10. Verification of version 1

[verified 2026-10-25, Step X.76, on Modkit main `ba1aeb24c`'s data; its `rando check` record] Today `rando check` prints 0 errors and: levels 22 authored, 0 stubs, `training_room` without a file; nodes 755, edges 2,466 (assumed 1,078, data 658, physics 715, probed 15, owner 0), live exits 70; hand objects: barrier 117, button 55, event 233; open: 0 TODO fields, 0 pool locations with no node, 0 undecoded gates; proven pool locations: data 56, l3 11, route 1, xemu 2 (54 non-gem: air 2, earth 9, fire 15, life and death 0, town and water 28); skips 45 (41 `in_logic`, 2 `held`, 2 `manual`), confirmed by xemu 33, the owner 7, l3 3, not 2; 40 picks in 5 batches, registry tag `67741703`; on at `skip_ceiling` 0-4 with no toggle: 0, 0, 19, 39 and 41; time-savers 39 (§4.9); `settings/defaults.toml` 0, `standard`, 1, no toggle, `AZR-AAEA`; the route's 277 steps, `draft`, 0 open references. The blocks below are dated records.

[verified 2026-10-12, Step R1.4] On the committed database (the imported hand files and the 23 generated files `rando db-extract` writes), `uv run --locked python -m devkit rando check` printed 0 errors and:
- levels: 22 with a level file, all stubs, and `training_room` without one;
- nodes 43, edges 131 (all `assumed`), live exits 70; hand objects: 117 barriers, 55 buttons, 27 events;
- open: 330 TODO fields (`edge.from` 39, `edge.to` 39, `edge.exit` 20, `button.at` 42, `event.at` 8, `barrier.destroy_from` 117, `node.anchors` 43, `level.route` 22); 856 pool locations with no node; 5 undecoded gates (w2's `HoseStuff` and e6's four `Detect_*` pedestals, §3.3);
- proven pool locations: data 0, xemu 0;
- skips: 75 (18 `in_logic`, 57 `held`), confirmed by xemu 13, by the owner 5, not 57; skip registry tag `434ed23c`; on at `skip_ceiling` 0, 1, 2, 3 and 4 with no toggle: 0, 7, 10, 17 and 18;
- `settings/defaults.toml`: 0, `standard` (D186), 1, no toggle; 0 skips on; `AZR-AAEA`;
- route: 277 steps, `draft`, 11 open references (below).

[verified 2026-10-13, Step R1.4b] After the re-import from `$RP` `7530b0b` (D145 and sitting rjc5), `rando check` prints 0 errors and the same counts but for the skips: 41 (19 `in_logic`, 22 `held`), confirmed by xemu 14, by the owner 5, not 22; registry tag `e62ddb47`; on at `skip_ceiling` 0–4 with no toggle: 0, 6, 9, 17 and 19; and the time-savers, listed apart: 35 (§4.9). These equal `$RP`'s `db-draft/check.json` at `7530b0b`.

Where draft 0's `db_check.py` and `tricks_check.py` count the same things, the numbers are theirs (History); `$RP`'s own generated files at `4b8f3f3` gave the same counts before v1 required the teleporters' `routes` (which R0's extract didn't write). `$RP/tricks/tricks_mutation.py`'s 24 cases, replayed against the loader on copies of that folder: 23 caught, each by its own rule (a made-up owner ref by `bad_confirmed`, since `tricks.toml` carries `owner_refs`), and the control passed with 0 issues. The one missed case needs the computed cells of `$RP/tricks/bskip/bskip_draft.toml` (`tricks_check.py` rule 4), which stays in `$RP` until Step R1.3 ports reach; so do `tricks_check.py`'s other checks against R0 evidence files: that `evidence` paths exist, a nolight skip's rating against `nolight.toml`, and the `[envelope]` tables against `rjump_tiers.toml` and the tjump law.

[verified 2026-10-13, Step R1.8d] With f2 and e5 authored too (22 authored, no stub; AZ-343), `rando check` prints 0 errors and: nodes 737, edges 2,693 (assumed 1,217, data 662, physics 814); hand objects: barrier 117, button 55, event 208; open: 0 TODO fields, 0 pool locations with no node, 0 undecoded gates; proven by data 55 (e5's 5 new), by xemu 1; the route's 277 steps (nine moved, §13) with 0 open references. The vanilla placement is fully accessible at the default tier and every realm's steps replay in order.

[verified 2026-10-13, Step R1.11d] With life, d1 and d2 authored too (17 authored, 5 stubs), `rando check` prints 0 errors and: nodes 537, edges 1794 (assumed 748, data 518, physics 528); hand objects: barrier 117, button 55, event 153; open: 94 TODO fields (the realm's 29 before, 0 now), 283 pool locations with no node (the realm's 0 before and after: its stubs had a `default_node`) and 4 undecoded gates (the realm's 0); proven pool locations: data 47, xemu 1; the route's open references 11 -> 2 (below).

[verified 2026-10-13, Step R1.11c] With e2, e6 and e7 authored too (20 authored, 2 stubs: e5 stays one with f2, AZ-343), `rando check` prints 0 errors and: nodes 661, edges 2,320 (assumed 1,032, data 611, physics 677); hand objects: barrier 117, button 55, event 187; open: 34 TODO fields (the realm's 59 before, 0 now, and one of e5's filled), 164 pool locations with no node (the realm's 119 before, e2's 33 and e7's 86, 0 now; e5's 85 and f2's 79 remain) and 0 undecoded gates (e6's four song pedestals, declared out of logic); proven pool locations: data 52, xemu 1; the route's open references 2 -> 0 (below).

[verified 2026-10-13, Step R1.8] With town and w1-w4 authored (`rando author`, §4.10), `rando check` prints 0 errors and: levels 5 authored (town, w1, w2, w3, w4), 17 stubs and `training_room` without a file; nodes 216, edges 659 (confidence: assumed 266, data 222, physics 171); hand objects: barrier 117, button 55, event 71; open: 232 TODO fields (the realm's 93 before, 0 now), 623 pool locations with no node (the realm's 233 before, 0 now) and 4 undecoded gates (the realm's one, w2's `HoseStuff`, now explained); proven pool locations: data 35, xemu 0; the skips, settings and route counts as before.

**The route's open references** (a draft route is a stub, §13): steps 104 and 112 set `flag:e2.crystal_lightning.hit` and `flag:e5.crystal_smash.hit`, which nothing in the database sets (the first is the pending `[[db_change]]` `e2-lightning-crystal-event` of `tricks.toml`; the database's e5 smash crystal event is `e5.crystal_pulse.hit`), and steps 259–267 gave `level = "d1"` for nine d2 locations (Step R1.11d moved steps 259–273, d2's locations and locks, to `level = "d2"`). Step R1.11c resolved the two flags (e2 gained the event, the `[[db_change]]` applied; step 110, as numbered now, names `e5.crystal_pulse.hit`), so none remains (AZ-309).

## 11. Choices draft 0 made beyond the plan's text

- `world.toml` and `derived/` are added (§1).
- Every generated object gets a record id, not just locations (§2.1).
- Barrier and keylock requirements are derived in `generated/` and bound by `of` (§4.4–§4.5). The plan's TOML example writes `damage` and `level` into the hand file, but its own one-source rule forbids copying generated facts.
- `persist` has five generated values; the solver sees only permanent vs respawn (§4.4).
- `default_node` lets the 10 single-node levels resolve every location without anchors (§4.1).
- Membership rule order (§4.2): explicit `locations`, then a `cell:` anchor, then the nearest point anchor, then `default_node`.
- Global latches are reserved as `global.<name>` flags (§2.3). Modelling the cross-level ones, such as `conveyor_on` (written in e5, read in e2 [verified, `thresholds/latches.txt`]), is an authoring choice for 4.10d.
- The gondolas are two cart locks, `minecart_e2e5` (the plan's id, kept) and `minecart_e2e7` (new), and both e2 cart edges carry the two circuitboard buttons [inferred, physical] (§4.3).
- `world.toml` declares the gem spend as a mechanism, with the new kind `spend` (§2.4, §7).
- **D113 (2026-10-12):** skips live in the level file they are performed in (§4.8), with the one-level rule, so that generated skips scale; `world.toml` keeps only the families. Presets carry a skip ceiling plus per-skip overrides instead of a maximum tier per trick (§7; since D144 the settings carry them, §7.1). A derived edge carries its own `difficulty` (§4.3), which replaces the proposed `trick:move@N` pseudo-trick.
- **D114 (2026-10-12):** a skip's `confirmed` projects into the level file with its status (§4.8), so the loader can refuse an unconfirmed `in_logic` skip without reading `$RP/tricks/`. Draft 0 left the owner ref to `tricks_check.py`, against OWNER_TRICKS.md's headings; v1 carries those headings as `tricks.toml`'s `owner_refs` and checks every ref against them (§12).
- **D118, D129 (2026-10-12):** a fifth preset, glitchless, and a required `movement_tier` on every preset (the presets are superseded by D144; `movement_tier` stays, as an option, §7.1). The tier is a name, as in `envelope/tiers.toml`, while an edge's `difficulty` stays a number (1–4); the two meet by that numbering.
- **D144 (2026-10-12):** no presets (§7). Where D144 is silent these are defaults taken under D115: the options are top-level keys of a settings file (`dark_fire` leaves `[knobs]`); every option is required in a file; `dark_fire` is 1–3; `defaults.toml` is pinned to D144's values by the check; `seed`, `[pools]` and a `[manual_skip]` opt-in are reserved as TODO; the share string carries registry indices with a tag, not skip ids (§7.3).
- **D122 (2026-10-12):** the proven mark lives on the hand layer's `[[location]]`, shaped like a skip's `confirmed` (`{ by, ref }`), with `by` = `data` or `xemu`; majors are the `progression` class, fragments included (default taken under D115, §4.7).
- **D169 (2026-10-13, a default taken under D115):** a proof source, `by = "route"`, checked mechanically (§4.7). Defaults taken with it: the check runs under the most lenient options so a mark holds whatever the user sets; it compares counts in the logic's bands; and a spot's way out counts the spot's vanilla item in the route's kit, so a spot the logic leaves freely but the run left holding a power is not proven by it. *Amended by Step R2.18b (AZ-725, a default taken under D115):* a mark may hold only where some skips are off (`unless`) and, with them on, for some items (`only`); each claim is checked under the most lenient options it covers, so a mark still holds whatever the user sets, as its terms say.

**Still open in the format itself:**
- **Arrivals into multi-graph levels.** Town, w3 and training_room arrivals assume the graph that holds the playerLocations is `[pd+0xDC]` (RAM_RECIPES §10, point 5); `arrival_graph_known` is `false` for them (§3.6).
- **Thresholds above 100.** `obsidian_cost` above 100 per lock behaves as 100: every lock curve's last key is at x = 100, and the in-memory simulation opens costs 11, 15 and 20 at 100 for the higher locks [verified, `thresholds/obsidian_tables.txt`]. The setting's text must say so, and it changes no format field.
- **Gem thresholds** and fuel stay out of logic in v1 (plan §2.8, §2.11). The grammar already accepts `sapphire>=N`, which counts gems collected (§2.4).

**Not answered by data, whatever the drafts prefilled;** each is answered since, by R0.4's sittings or a default at Step R1.8 (`RANDOMIZER_PLAN.md` §6's status table, Step 2.20j's R0 record):
- I-2 (does a barrier need a level): `level` and `requires` are [inferred, static] (§3.3). *Answered (rz-b1):* a barrier needs its combination at a power level, and an attack's level is the minimum of its elements'.
- I-7(a, d, e) (the disc teleport on entry, re-entry, level- or edge-triggered): [inferred, static] (§3.6). *Answered for a6 (placed):* level-triggered, safe after placement; e5's chain fires as a6's.
- I-8 and I-15 (persistence; fbarrier1 and whether it stays broken): `persist` is [inferred, static] (§3.3); fbarrier1 = w1 `FireWall_01` is [inferred] from distances. *I-8 answered for six families:* fire walls and crack blocks respawn; ice blocks, the `AirSwitch`, the w1 seal and geodes latch. *I-15, a default at Step R1.8:* fbarrier1 is `FireWall_01`, passed with water 1 and crossed only from where it is destroyed (it re-closes after 5.8 s).
- I-10 (the cart side and its circuitboard gate): [inferred, static and physical] (§4.3). *Mechanism answered (rz-b2):* two gondola pairs, the side bit makes e2's dock a lethal drop, and `MineCarRide2` stays inside e2; Step R1.11c put MineCar2 in logic and kept MineCar out.
- I-19 (w4 day/night): the fans' window is decoded (§3.7); "nothing latches on the clock" and "harmless" are [inferred]. *A default at Step R1.8:* a wait, not a flag (`w4_daynight` harmless).

**For the R0 record step (plan changes these findings owe);** *done by Step 2.20j (2026-10-11): `RANDOMIZER_PLAN.md` §0, §2.9, §2.10, §3.1 and §6 carry them, and R0.3a's and R0.3b's reports are saved:*
- **§0 and §2.9:** life has no count-triggered teleport, and w1 has one (`BossDefeated`, water ≥ 4, no placed check) (§3.6). Update §2.9's list, the life and w1 no-return/forfeitable model, and the Q246 rider.
- **§2.10:** two gondolas, not one rig; `MineCarRide2` is an in-level ride; add the lock `minecart_e2e7` (§4.3).
- **§3.1 and §7:** the game's gem values are not monotone (the fuel-cap upgrade spends them); add it to §3.1's exception table, and revise R2.6's gem rewards and R2.10's `diamond>=100` fuel tier (§2.4).
- **§6:** I-2, I-7(e), I-8, I-10, I-15 and I-19 stay open (above); R0.3a and R0.3b stay not done until their reports are saved with [verified] labels.

## 12. `tricks.toml`

The review superset of the skips (D113, D114): the trick families with their mechanism, confidence and evidence; every skip with its difficulty reason, confidence, evidence, source, the clause it plugs into, its hold and why it is a skip (`d145`); every time-saver (D145, §4.9); the generated-skip rules; families still candidates; pending database changes. The loader reads the keys of the "Read" column and refuses any key in neither column; it never reads a review value.

| Table | Read | Review only (any value) |
|---|---|---|
| top level | `format` (`azurik-rando-tricks/1`), `owner_refs` (required: the headings of `$RP/tricks/OWNER_TRICKS.md`, the owner's words verbatim, that an owner confirmation may cite), `[[trick]]`, `[[skip]]`, `[[skip_rule]]`, `[[time_saver]]`, `[[candidate]]`, `[[db_change]]` | `made`, `corrected`, `restructured`, `gated`, `decided`, `decided_<n>`, `xemu_applied`, `xemu_applied_<n>`, `difficulty_names`, `difficulty_rule`, `skip_status`, `confirmation_rule`, `envelope_rule`, `time_saver_rule`, `superseded`, `video_notes`, `[envelope]` |
| `[[trick]]` | `name`, `description`, `mechanism`, `confidence`, `evidence`, all required; `default_tier`, `tiers` and `requires` are refused (D113) | `needs`, `difficulty_basis`, `buffering`, `video_limits`, `questions`, `measured_xemu`, `answered`, `superseded`, `entry_paths`, `carry_rule`, `interactions`, `negatives`, `release_hypothesis`, `corrections`, `site_rule`, `candidates`, `clause_rule`, `uses`, `source`, `registered` |
| `[[skip]]` | required: `id`, `name`, `level`, `bypasses`, `tricks`, `requires`, `difficulty_reason`, `status`, `confirmed`, `confidence`, `evidence`, `source`, `d145` (D145: why it is a skip); optional: `from`, `to`, `gates`, `tiers`, `batch`, `batch_name` (§4.8), `difficulty`, `held_reason`, `priority`, `clause`, `plugs_into`, `xemu`, `xemu_ref`, `zones`, `dark_node`, `rolls` (proven at garret4's x1 roll: a roll other than his flags the build when it is on, Step 2.133) | `superseded`, `note`, `method` |
| `[[time_saver]]` (D145, §4.9) | required: `id`, `name`, `level`, `replaces`, `tricks`, `kit` (what the technique needs, an expression naming no skip), `video` (`<video id>@mm:ss` refs), `source`, `saves`, `plain` (the plain route to the same place), `evidence`, `d145_evidence` (paths under `$EV`), `was` (its former skip state), `d145` (the verdict); optional: `from`, `to`, `gates`, `zones`, `reopen` (what would make it a skip again). A skip's logic keys are refused | — |
| `[[skip_rule]]` | `id`, `tricks`, `id_pattern`, `applies`, `requires_rule`, `difficulty_rule`, `status`, `once_confirmed`, `confirmed_rule`, `source` | `example`, `superseded`, `note` |
| `[[candidate]]` | `name`, `skips` | `description`, `note` |
| `[[db_change]]` | `id`, `file`, `what`, `confidence`; `adds_flags`, `removes_flags`, `requires` | — |

**Rules** (`$RP/tricks/tricks_check.py`'s, as the loader applies them):
- The families' names and descriptions equal `world.toml`'s `[[trick]]` (14: D120's 13 and Step R2.18's `flutter`, D630); a candidate is no registered family.
- A `[[db_change]]` adds only flags the database lacks and removes only flags it has (else it is stale). Its flags resolve this file's expressions, never the level files'.
- A skip's id is `<level>.<slug>` of a level that has a file. Its families are registered, or candidates (then it is held). A held skip has a `held_reason`. An unconfirmed (`"no"`) skip is held, its reason starting `unconfirmed (D114)`, or `failed in xemu (` when its `xemu = "failed: …"` says why. Every row, projected or not, gets a level skip's checks: its `confirmed` is `"no"`, an xemu ref `<sitting>/<row>[:<skip id>]` or an owner ref that `owner_refs` lists, its `from` and `to` are nodes and its `gates` hand objects. `priority` is only `"video"`, on an unconfirmed skip whose `source` names a video. Only a held skip is unrated, its reason starting `unrated`. A tjump or itrig skip is rated 3 or more, and an in-logic rjump skip from a video 2 or more. `requires` and `clause` parse and resolve, and an in-logic skip's clause names the skip.
- A `[[skip_rule]]`'s families are registered, its `id_pattern` starts `<level>.`, and its generated skips start held, then become `in_logic` (`manual` for saveanywhere) once confirmed.
- A candidate's listed skips are held skips that name it.
- **Time-savers (D145, §4.9; rule 22):** an id is `<level>.<slug>` of a level that has a file and no skip's or other time-saver's; the families are registered; `from`, `to` and `gates` resolve; the `kit` parses and names no skip; the video refs are `<video id>@mm:ss`; `saves`, `plain`, `was` and `d145` are not empty; `world.toml` lists each one once with the same `name`, `level` and `tricks`; and no expression, toggle or level file names one. A skip's `d145` is not empty. Not ported: that the `evidence` and `d145_evidence` paths exist (they are in `$RP` and `$EV`).
- **Projection (§4.8):** every skip whose families are all registered is in its level's file with the same `name`, `tricks`, `requires`, `difficulty`, `status`, `confirmed`, `from`, `to`, `gates`, `tiers`, `batch` and `batch_name`, and the level files hold no other skip.
- No string holds a `trick:` atom outside `superseded` or `answered` text (D113).

## 13. `route.toml`

The draft vanilla non-gem route (plan §4.3, check 2), which `$RP/route/build_route.py` wrote on 2026-10-11: the order a glitchless run collects every non-gem pool location, with the actions between them.

| Key | Meaning |
|---|---|
| `format` | `azurik-rando-route/1` |
| `status` | `draft` (a stub: what doesn't resolve yet is counted, not refused) or `authored` |
| `variant`, `matches_temple_order`, `power_order` | text; a flag; the power order, each a counter atom (`water1`) |
| `location_steps`, `action_steps`, `replay_problems` | the number of location steps, of action steps, and of steps whose `ok` is false |
| `[sources]`, `[area_to_level]` | the sources cited; each community area name's level, as `{ level, evidence }` |
| `[[step]]` | `step` (1..N in order), `leg`, `level`, `kind` (`location` or `action`), `requires`, `ok`, `sources`; a location step's `id`, `item` and `class` (its vanilla item and class); an action step's `action` (`use_keylock`, `kill`, `open_obsidian_lock`, `touch_seal` or `hit_crystal`), `sets` (one `button:`, `event:` or `flag:` atom) and `consumes` (a key counter); optional `community` (an int or a list of ints), `match`, `pool` and `note` |

- **Rules.** The counts match the steps; every non-gem pool location is a step exactly once; a location step's id is a pool location of its `level` that holds its `item` and `class` in vanilla; every expression parses and resolves. In a `draft` route an unresolved reference, a location in another level, and a missed or repeated location are counted (`rando check` lists each); in an `authored` one they are refused. A step whose item or class differs from the vanilla data contradicts the generated files rather than waiting on authoring, so it is refused in a draft route too (default taken under D115), as is any malformed entry.
- The per-level `route` key (§4.1) is the level's location steps of `route.toml`, in order, in an authored level (`rando author` writes it, §4.10); `test_vanilla_route_replays_in_order[<realm>]` reads `route.toml` itself, since a realm's run interleaves its levels with the others'. Step R1.8 moved one step (w2's waterfall-top obsidian, after the w1 air-3 obsidians: the derive reaches it only with air 3; its note says why). Step R1.11d moved w1's water keylock (was step 68) after life's two key_life1 (step 249): with life authored its two key_life1 locks count in the keylock's worst-case key count (§5.5), so it needs all three key_life1, sound but over-strict (life's own keys sit by its locks; RANDOMIZER_PLAN §2.6), and it gates nothing in the authored logic (AZ-344 asks whether town's frag_water_2 should read it). Step R1.8d (AZ-343, with f2 and e5 authored, so no stub hands out an early `power_air`) moved nine more, each with a `note`: w1's dark-cave obsidian after the bay keylord's kill (the torpedo, AZ-344), w2's WaterfallView obsidian after f2's air 2, f3's earth power before its keys (it stands in the main cavern; the speedrun takes it with no lock used), town's third obsidian lock and its life upgrade to the 40-obsidian visit, f3's frag_earth_2, f1's frag_water_3 and w1's seal after air 2 (the derive reaches both fragments only with air 2), f2's frag_life_3 to the acid-3 visit (AcidBlock_04, level 3) and an e5 fuel after air 3. Step R1.8l (AZ-345) moved w1's water keylock back after the bay key (step 64), before the torpedo's two spots that now read it: the key rule (§5.5) counts neither of life's two locks against it.

## 14. Changes in version 1 (Step R1.4, 2026-10-12)

Each is a default taken under D115 unless a decision is cited.
- Every `format` key ends `/1` (`tricks.toml`'s `1-draft` too). The share string's payload keeps version 0, so `AZR-AAIA` and every string draft 0 made still decode (§7.3).
- `status` is `draft` (a stub) or `authored`; `owner-reviewed` is gone (§4.1; Q301).
- `[[edge]]` gains `confidence` (plan §4.5's labels; §4.3).
- `tricks.toml` and `route.toml` join the database (§12, §13), each loaded with its own rules; `check.json` does not (`rando check --json` prints the same summary).
- `derived/` was reserved, and the loader refused any file in it (§1), until Step R1.3c defined it (§16).
- Draft 0's checks are kept, and the loader adds: missing required keys and wrong types; unknown files; a generated id not of the form `<file>/g<G>/r<R>`; an unexplained gate (§4.4); a toggle gating an edge and the other undeclared mechanisms (rules 8 and 14, which draft 0 left to 4.10b); live exits not bound exactly once and bound dead exits; an exit edge's `to` in another level than its destination; the references draft 0 left unchecked (anchors, cells, `teleporter`, `assumes`, `contains`, `required_for`, `known_traps` and the per-level `route`); `barrier:` and `skip:` reference cycles; `proven` on a location out of the pool; generated requirements that don't parse; non-integer generated numbers, coordinate-like triples and long hex runs.
- A teleporter is keyed by a locator that is also a spot (§3.6), so teleporters have their own registry instead of colliding with the spots.
- A teleporter's `locators` and Step R1.1's `routes` are required (§3.6), so R0's generated files, which have no `routes`, no longer load.
- `tricks.toml` gains `owner_refs` (§12), the headings of `$RP/tricks/OWNER_TRICKS.md`, so the loader checks an owner ref without reading `$RP`; every `tricks.toml` row gets a level skip's checks, projected or not.
- A key repeated in one generated JSON object is refused (§1), and a draft route's step whose item or class differs from the vanilla data is refused (§13).
- An exit's `kind` loses `dead_dest`: Step R1.1's extract leaves an exit to a level that isn't on the disc out of the table (AZ-290; §3.6), so the generated data has 75 exits, not draft 0's 76.

**Step R1.5 (2026-10-12, before version 1 lands; default taken under D115).** A node's or edge's `dark` also takes the id of the `nolight` skip that lifts its light need (§4.2, §7.1): the `nolight` family's `clause_rule` proposal, which D144's "an enabled nolight skip lifts it" for its own area needs, since `true` names no skip. The loader also refuses such a skip on another level's node or edge, or away from the `dark_node` its `tricks.toml` row names, and a generated location's item that `items.toml` doesn't define. Every shipped file still loads with the same meaning and no file sets `dark` yet, and version 1 is not on `main`, so it stays version 1.

**Step R1.6 (2026-10-12, before version 1 lands; default taken under D115).** An edge's `difficulty` also takes 0, the envelope's `phys` tier (`draft/tiers.toml` `[phys]`, difficulty 0): an edge only that tier's margins clear is in R_phys and never in logic (§4.3, §15). The loader runs rule 10's reachability and refuses a terminal event that anything but the victory reads (rule 21, §9). The shipped `d1.spideyzar.killed` gains `terminal = true` (D76: the kill ends the game, plan §2.7 [verified data]), which changes no reach while d1 is a stub. No shipped edge sets `difficulty`, and version 1 is not on `main`, so it stays version 1.

**Step R1.3c (2026-10-12, before version 1 lands).** `derived/<level>.json` is defined (§16) and loaded with rule 11; nothing else changes, so it stays version 1.

**Step R1.3d (2026-10-13, before version 1 lands).** A derived file is `derived/<level>.json.gz`, compact JSON with sorted keys, gzip-compressed: the seven committed levels' 40.3 MB of text is 27.0 MB after the cuts below and 1.4 MB compressed (no cut that keeps the edges' reasons brought the text near 10 MB). An edge loses `tiers` (`draft/export.py`'s `tiers_of` gives it from `requires`, `options` and `difficulty`, equal for all 83,179 edges), `skip_ids` (the skip atoms of `requires` and `options`), `trick` (always `bskip`, where `bskip` is) and `support` (a count nothing read). The stamp holds the derive version instead of the derive's code (§16). Nothing reads the derived data but its own checks, so it stays version 1.

**Step R1.4b (2026-10-13, before version 1 lands; D145).** `tricks.toml` gains `[[time_saver]]` and `time_saver_rule`, its `[[skip]]` the required `d145` and the optional `tiers`, which a level `[[skip]]` takes too (projected), and `world.toml` gains `[[time_saver]]` (§4.8, §4.9, §7, §12); the loader refuses a time-saver in logic (rule 22). The re-import from `$RP` `7530b0b` moves 34 skips to `[[time_saver]]` and splits a 35th off `a6.rjump_platforms`, and sitting rjc5 confirms three skips: the skips go from 75 (18 in logic) to 41 (19 in logic), and the skips on at ceilings 0–4 from 0, 7, 10, 17, 18 to 0, 6, 9, 17, 19 (§7.5). Every other count is unchanged (§10). A level's derive stamp reads its level file and `tricks.toml` (§16), so the seven derived files are re-derived with it. Additive, like Step R1.3c's change, so it stays version 1 (default taken under D115).

**Step R1.8 (2026-10-13; additive, so it stays version 1, default taken under D115).** A node's `anchors` take `zone:<zone id>` (§4.2), resolved against the level's derived file (rule 3: `unresolved_zone`, `zone_in_two_nodes`), and a location's derived zone gives its node (§4.2 rule 3, which draft 0 left to "the nearest point anchor"). An authored level's file is written by `rando author` (§4.10). A stub's locks no longer count in another lock's worst-case key count (§15). Town and w1-w4 are authored; `tricks.toml`'s realm-1 skips name their new nodes, and the applied `[[db_change]]` w1-airship-gate is gone; `route.toml` moves one step (§13).

**Step R1.11c (2026-10-13; additive, so it stays version 1, default taken under D115).** An authoring's `[exit."<id>"]` takes `cart` (a `world.toml` lock) and `logic`, which `rando author` writes as the gondola edge's `kind = "cart"`, `lock` and `logic` (§4.3, §4.10). e2, e6 and e7 are authored; `tricks.toml`'s applied `[[db_change]]` e2-lightning-crystal-event is gone (e2 gains `e2.crystal_lightning.hit`, e6 loses `e6.crystal_lightning.hit`); `route.toml` names e5's smash crystal `e5.crystal_pulse.hit` and moves e2's fire power after the two circuitboard locks (§13). The derive (version 3) reads a gate direction its own leak check finds reached past the shut gate as not separated (e6's AcidBlock_02, from e6.Z049), so every derived file passes the consumer's barrier guarantee (§16).

**Step R1.31 (2026-10-18; D275, additive, so it stays version 1, default taken under D115).** A `[[skip]]` takes `batch` and `batch_name` (§4.8, §12): the four batches of variants that differ only in kit. A toggle and the share string's registry name picks, a batch's id or a lone skip's (§7.2, §7.3), so the registry tag moves from `710ca8a0` to that of the 38 picks; an old per-variant id, in a file or in a string made for the old registry, loads as its batch. The derived files are re-derived (their stamps read `tricks.toml`, §16) and the level files re-authored; a plan's `db_digest` moves with the level files (§9).

**Step R1.31b (2026-10-19; no key changes).** A fifth batch, `f6.terraces` (`f6.rjump_terraces`, air 2, and `f6.rjump_terraces_air1`, air 1), and one skip fewer, `e5.rjump_conveyor_ladder_air1`, now a time-saver: the registry tag moves to that of the 37 picks (`c52e13d1`), and a string with toggles made for the 38 picks is refused as made for another registry (§7.3). The derived files are re-derived (stamps) and the level files re-authored.

**Step R1.32 (2026-10-19; no key changes).** A derived file's stamp hashes `derive_inputs` (§16 `_meta`) in place of the whole level file and `tricks.toml`, and reach reads the database only through it; the 22 derived files are restamped once, their content unchanged.

**Step R2.17b (2026-10-24; no key changes).** `d1.elevator_bounce` is the located floor 8 -> floor 9 bounce, in logic, and `d1.elevator_bounce_f10` (floor 7 -> floor 10) is new; `w3.botstep_icebergs` is a time-saver (D657). Still 37 picks, but other ones: the registry tag moves to `2da36b7e`, and a string with toggles made for the old picks is refused as made for another registry (§7.3). d1 and w3 are re-authored.

**Step R2.18 (2026-10-24; no key changes).** The owner's X.67 demo adds five skips (`w1.hidden_airship_saveanywhere`, `w4.rjump_frag_earth1`, the batch `e6.upper_ring_flutter`'s two variants and `f2.rjump_interior`), removes `w1.torpedo_skip_air1` (with it the batch `w1.torpedo`, so a settings file naming it is refused as unknown) and makes `f6.seal_skip` and `a5.rings_air_power3` time-savers: 39 picks, and the registry tag moves to `46ae2220`; a string with toggles made for the old picks is refused as made for another registry (§7.3). The levels whose skips changed are re-derived (stamps) and re-authored.

**Step R2.18b (2026-10-25; additive, so it stays version 1, default taken under D115).** A by-route `proven` mark takes `unless` and `only` (AZ-725, §4.7): w2's `w2/g0/r1346` names `w2.firewall02_air3`, which enters logic. The tiers move (D674), and `f6.mound_climb_air1` is new (D654, D671): 40 picks, and the registry tag moves to `67741703`; a string with toggles made for the old picks is refused as made for another registry (§7.3). w2, f6 and the levels whose skips' tiers moved are re-derived (stamps) and re-authored.

**Step 2.90a (2026-10-17; D261, default taken under D115).** The upgrades (`power_life`, `power_staff1`, `power_staff2`, `power_ammo`) leave `powers` for a category of their own, `upgrades`, appended as the share string's mask bit 5 (§7.2, §7.3): the Randomize page's Powers row splits into Elemental powers and Upgrades. An old setting keeps its meaning: a format `/1` file's and a version 0–2 string's `powers` keeps both rows, so its share string, its `settings_digest` and its plans are unchanged; the elemental powers kept without the upgrades take settings format `/2` and share version 3. A `--exclude-category` flag names its category alone (`powers` is the 12 elemental powers).

**Step R1.7 (2026-10-12, before version 1 lands).** No key changes. The loader refuses a disc teleport whose disc has not exactly one guardian slot in the pool (rule 14, `disc_teleport_slot`); the shipped four (a6, w3, f6, e5) each have theirs. The solver reads the disc teleport as one shot, the no-return regions and the forfeitable locations (§15).

## 15. The solver: reach, escape, R_phys and the no-return regions (Steps R1.5-R1.7)

`src/azurkit/tools/randomizer/planner/solver.py` (stdlib only, like the loader) reads a loaded database. `Logic(db)` compiles it once; `Logic.reach(settings, placement, items, flags)` returns the least fixpoint of plan §2.13's safe-reach loop as a `Reach`: the nodes reached in logic (R), the safe ones, the nodes of R_phys, the traps, the locations collected, the flags credited and whether victory holds. Each round, a sphere, reads the state it starts with: R, forward reach from `world.toml`'s start over the edges in logic; Safe, the nodes of R whose escape holds; then every location at a safe node and every flag or event at a safe node whose requirement holds is collected or credited, and every terminal event at a node of R; until a round adds nothing. `victory` is `world.toml`'s victory expression on the result. Expressions are compiled into closures once per option set, with the skips that are off and the edges above the movement tier compiled away (plan §3.2, §3.4).

- **State** (plan §3.1): the items held (a `Counter`, AZ-160), the counters they add (`items.toml`; a location adds its `yield` copies; a disc counter counts distinct fragments, plan §2.1) and the credited flags. Nothing is taken away.
- **The escape** (plan §2.13 rules 1–3, Step R1.6) of a node n is a local closure. From n, with the items held, the flags credited from the start (`reach`'s `flags`) and those of n's forced flags (below) that are credited, it walks forward over the edges in logic, collects the locations not yet collected (an empty spot adds nothing, so no location is escapable because of what a fill puts there) and credits the flags and events whose requirement holds wherever it gets, until it reaches the start, or nothing more. A node is **safe** when its escape reaches the start: the anchor is the start, never the hub (rule 1, CE1). A flag credited elsewhere doesn't count (rule 3, CE2: a player may drop in before pressing a lever on the far side), but one found on the way does (CE5), and so does an item (rule 2).
- **Forced on entry** (plan §2.13): a flag f is forced on n when no way into n does without it: with no skip, every player tier's edge (`frame_perfect`) and every counter at its maximum, n can't be reached from the start while f is never credited. An edge's requirement, its barriers' crossings and its `assumes` all count as needs, and the whole path counts, not just the last edge (a room behind a lock is forced the lock's flag even when an edge comes back into it from a room further in). Every flag that reach credits is tried, so neither the order of an `|`'s operands nor a flag read only by another flag's requirement (a button that needs an event) hides one. Read once per database, so it depends on neither the state nor the options. The traps read a second set, forced on entry over R_phys's skip-free graph (below), where `assumes` is no need and an edge out of logic is a way in. **A forced flag counts toward an escape only once credited:** a node that a skip alone gets into isn't safe by the flags its skip-free ways in set (default taken under D115; plan §2.13 writes "every usable in-edge", which, read per state or per option set, would let Safe shrink as items or options grow, against D113's invariant; a skip used to get into a node without such a flag is the player's risk, as D83(b)'s trap gate treats skips).
- **Terminal events** (rule 4, CE6): an event with `terminal = true` is credited at any node of R, safe or not, since the game ends there; only safe nodes give anything else. Nothing but the victory reads one (§9 rule 21), so crediting it lets nothing else follow.
- **R_phys** (plan §2.13): where a player can physically get with the items held, a fixpoint of the reach and the flags a player can set where it gets. It takes every edge, those out of logic too (`logic = false`, every cart, every movement `difficulty` including 0, the `phys` tier, whatever the movement tier), ignores `assumes`, reads a dark edge or node at `fire>=1` whatever `dark_fire` (a logic option, like the movement tier; plan §2.12's floor, and the area's nolight skip still lifts it when the options turn it on; default taken under D115, though R0 picked up each dark room's nearest obsidian at fire 0), presses toggles, crosses a respawning barrier where its destroy requirement holds whatever the mechanism's handling, opens a lock with one key (no worst-case count) and takes only the skips the options turn on. It has no derived gate to ignore: a no-return region's gate (plan §2.9) is its nodes' escape (below), never an edge.
- **Traps** (plan §2.13's trap gate, CE7): a node of R_phys outside Safe whose escape on R_phys's graph fails at some sphere's state. That escape walks the physical graph (the edges out of logic, toggles, respawns and the skips that are on) and starts with the flags forced on entry physically that a player can set there (so a room whose every skip-free way in sets a flag isn't a trap while logic has yet to credit it, but a drop that only `assumes` its way back's flag is one until the flag is credited: a player can take it first). `Reach.traps` is the union over the spheres. A node out of logic that a player can get back from, even only by edges out of logic, is no trap (default taken under D115; the plan's `R_phys \ Safe`, read literally, would call every node out of logic a trap). A trap is **trick-free** when, at that state, a player gets into it with no skip at all (R_phys with every skip off; `Reach.free_traps`; default taken under D115: "entered by a trick-free edge" read as the whole way in, since a skip anywhere on it is the player's risk). Each `trace` sphere carries the traps at its state and the trick-free ones (with those of the rounds since the last sphere), the spoiler's spans.
- **The trap gate** (plan §2.13, D83(b); Step R1.12, `fill.verify`): a placement fails the verify, and the fill retries with the next attempt's streams, when its solve has a trick-free trap that isn't known and isn't a trap after completion. **Known** (`fill.known_traps`): the level files' `known_traps` (§4.1, owner-signed; none yet) and vanilla's own, every trap of the vanilla placement under the same options or under the defaults, however it is entered (default taken under D115: computed rather than listed by hand; a node vanilla traps a player in, f4's lava river or town's pits that a skip gets into early, is vanilla's whatever the options, so the plan's "vanilla's own traps" is read per node). `Fill.failed` keeps each failed attempt's reason. The retry rate on seeds 0-50 at `a8a2f63`'s data [verified 2026-10-13, Step R1.12's seed run]: default options, 4 of 587 attempts (0.7 %) refused by the gate, 4 seeds retried once (38 of 51 fill; the 13 that don't fail on the proven-spot rule, 3 of them with one gated attempt among their 20); max options (ceiling 4, `frame_perfect`), 246 of 298 attempts (82.6 %), 43 seeds retried up to 16 times, every seed filling, mostly w2's pool zones (w2_z002-w2_z025: with `power_water` placed outside w2 a player walks in and can't leave) and a few f6 and air-realm zones; strict (no skip, `safe`, `dark_fire` 2), none, since no attempt gets past the proven-spot rule (D156, Step R1.2b). RQ-11's alternative, a fill rule ordering a trap's entry items after its escape items, would cut max's rate; D83(b)'s re-roll stands. *Step R1.8m:* the fill repairs before it re-rolls (`fill._Slots.repairs`, a form of RQ-11's rule): when only the gate refuses an attempt's placement (its progression items and obsidians: nothing the later passes add is read), the first sphere with new trick-free traps (t) and the first after it free of them (u) give a swap, a progression item collected in sphere u-1 (the way out) for one collected last before t (the way in, those without which the traps don't start first), or, with none before t, for a spot at a trap node (the ways out that free the traps from there first: w2's hose pool and the water); the obsidians are placed again and the placement checked again, up to `MAX_REPAIRS` (8) swaps, and a swap that breaks the placement goes back to the last one. The fill also puts a progression item first on a spot it opens by lying there (a reached node not safe without it, whose escape picks it up: under the defaults and strict, no plan without a water in the hose pool passes the gate, and the assumed fill never put the last water there), and an item with no spot trades places with one placed before it. Seeds 0-99 then fill on their first attempt at max (137 repairs), and 96 and 93 of them at default and strict (all 100 by the second) [verified 2026-10-14, Step R1.8m's fill-failure run].
- **The disc teleport** (plan §2.9, D81; Step R1.7): an edge with `disc` is one shot. It is no edge of R, R_phys or any other reach, since it fires once; an escape (Safe's and a trap's) takes it, to its `to`, once it reaches its `from` with its requirement holding, while that disc's guardian slot is not collected before the sphere (the disc not yet placed: in the game, 4 fragments with the disc not placed fire it, level-triggered, R0's I-7). The slot keeps its vanilla fragment whatever the placement names (pre-filled, RQ-4), so the escape of a region's node holds once it can reach the slot with 3 of the disc and whatever the slot's gate and the way there need (the boss included; CE3, CE8): that is the region's derived gate, computed per node, never written. Once the slot is collected, no escape takes the teleport, so a region node not safe by then never is.
- **No-return regions** (plan §2.9): a disc's region is the nodes that, with every item, every flag the reach credits, no skip and every player tier's edge, the start reaches, that don't get back to the start (the teleports aside) and that reach that disc's teleport. They are read once per database, like the forced flags (default taken under D115: the plan's "only way out" read with every item and no skip, so a room a skip or an item gets out of is no region, and its traps are the per-sphere ones). On Step R1.7's database the one region was a6's stub, which got back only by the air disc's teleport (its other exits led to `""` while it was a stub); at Step R1.11c, with a6 authored, it was the water guardian's arena (Monotone, below).
- **Forfeitable locations** (plan §2.9, D81, CE4): an authored level's pool locations at a region's nodes, other than its slot: what a placement puts there never counts (default taken under D115: a plan that breaks the fill's rule fails rather than being refused; the fill puts no progression or obsidian there, R1.10), since a player who takes the slot first never gets back to them. A stub's locations keep their vanilla items. `Logic.forfeitable` lists them.
- **Traps after completion** (plan §2.9, §2.13): `Reach.after_completion` is the nodes of R_phys in each region whose slot is collected: a player who goes back in after the teleport has no way out. A region node that was never safe can be in `traps` too (entered too early, before what its escape needs).
- **Options** (§7.1, D144): a `skip:` atom holds when `skips_on` turns the skip on (never a held or manual one) and its own `requires` holds; an edge whose `difficulty` is 0 or above the movement tier's number is out of logic; `dark` adds the light need (§4.2, §4.3), `fire>=dark_fire` in logic and `fire>=1` in R_phys.
- **Edges:** `requires`, the crossing of each barrier in `through` from `from` to `to`, each `assumes` flag and the light need. `logic = false` keeps an edge out; a `cart` edge is in logic only when its `lock` mechanism's handling is `harmless`.
- **Barriers** (§4.4, §5.3): a permanent one sets `<id>.destroyed` when its destroy requirement and the node's light need hold at a safe `destroy_from` node; the flag opens every crossing, its `contains` locations and the events of its `required_for`. Any other `persist` respawns: it sets no flag, and it is destroyed where the player stands (plan §2.4), so a crossing from A needs A in `destroy_from`, the destroy requirement and the light at A, and its contents and events need the same at their own node; all of it only when every `respawn` mechanism is `harmless` (else never). A bypass crosses in its own direction only, sets no flag and frees nothing. An undecoded barrier's destroy requirement is false.
- **Buttons:** a latch sets `<id>.open` at its `at` node, once safe, needing its generated requirement (or the override), its hand one and the light need. A toggle is pressed in logic only when every `toggle` mechanism is `harmless` (plan §3.1); the shipped `toggles` is `out_of_logic`, so none is. A button with no `of` has only its hand requirement; one bound to a gate whose generated requirement is null (an uncoded keylock, a relay) is never pressed until `override_requires` explains it (§4.5).
- **Keys used up** (plan §2.6, §5.5): a coded keylock whose generated `consumes` names `key.<t>` needs `key.<t> >= 1 + k`, k being the other `key.<t>` locks pressed in R_phys (above: `logic = false` edges, every cart and every movement tier, `assumes` ignored, toggles pressed) with every item, every in-logic skip (ceiling 4) and this lock never pressed. A stub's locks are pressed free (§4.1), so they spend no key and count for no other lock (Step R1.8: w1's water keylock and life's two locks share `key.life1`, and counting life's stub locks made the w1 lock wait for life). The key rule (§5.5, Step R1.8l, AZ-345): another lock a key lying on every way to it gives back is matched to that key, and each matched key the placement puts on its spot and nobody has taken counts toward the lock as held (a pending counter, one per refund key, that taking the key clears as it adds the key). The counts and the matching depend on neither the options nor the placement, and taking a refund key adds one key and clears one pending, so the reach stays monotone.
- **Events:** credited at their `at` node, once safe (or reached, for a terminal one), when their `requires`, the light need and every barrier whose `required_for` names them hold. A location `gated_by` a keylord or boss needs the hand event bound to it (§5.6), whatever its id.
- **Locations:** a pool location is collected at its node (§4.2), once safe, when each `gated_by` atom (§5.6), its `[[location]]` `requires`, every barrier that `contains` it and its node's light need hold; it adds what the placement put there.
- **Stubs** (§4.1): a stub is one node, named by its level; reaching any of its nodes reaches it, and it is safe when its edges, or its disc teleport while its slot isn't collected, get back to the start. Its pool locations give their vanilla items, and its objects their flags, with no requirement (their gates and open fields aside), but a respawning barrier sets no flag there either; its edges keep their requirements, one with `from = ""` leaves from the stub, and one with `to = ""` leads nowhere. A respawning barrier on a stub's edge is crossed only from a `destroy_from` node too, and the stubs leave `destroy_from` open, so none is (no shipped edge passes a barrier yet).
- **The placement** maps each pool location of an authored level to an item or to nothing; a location it doesn't name is empty, and `Logic.vanilla_placement()` gives vanilla. A stub's location, an unknown location or item, an unknown starting item or flag, and options a settings file couldn't hold (§7.2) are refused, each by name.
- **Monotone** (plan §2.15, D113): adding an item or a flag, raising `skip_ceiling` or the movement tier, or turning a toggle on never shrinks the reach, the safe set, the locations, the flags or victory; lowering `dark_fire` neither. The escape keeps it so: its closure only grows with the state and the options, and the flags forced on entry are read once (above). The traps are not monotone, and neither is the disc teleport's one shot, plan §3.1's declared exception: a region node whose way to the slot comes only after the slot is collected (guardiandb's nook, when the water comes later) loses its escape, and its spots are forfeitable for that reason. `test_adding_an_item_flag_or_skip_never_shrinks_the_safe_set` checks it in a seeded loop on `tests/rando/reachdb/` and `tests/rando/escapedb/`, which have no region. Since Step R1.11c (town, w1-w4, a1, a3, a5, a6, the airship, f1, f3, f4, f6, life, d1, d2, e2, e6 and e7 authored, e5 and f2 stubs), the shipped database's vanilla placement, under the default options (no skip, `hard`), reaches 593 nodes, 537 of them safe, all 1,418 locations and victory (Spideyzar on d1's floor 9); its one no-return region is the water guardian's arena (`w3_sealed`, the trap after completion once its slot is collected), and 89 nodes are traps: realm 1's six (town's four pits on FireWall_02's far side, w2's waterfall-top ledge `w2_z051` and the 1 m² ledge `w2_z757`), the fire realm's eight (f3's drops `f3_z025`, `f3_z296` and `f3_z308`, f4's F2_F4a arrival `f4_lava_river`, f6's ledges `f6_z032`, `f6_z077`, `f6_z571` and `f6_z583`; the fire guardian's arena is left before the kill, D123, so it is no region), the earth realm's nine (e2's `e2_z013`, `e2_z196`, `e2_z626` and `e2_z1432`, e6's pit `e6_z004`, FireWall_02's far ledge `e6_z094`, `e6_z011`, `e6_z046` and `e6_z164`), 50 of the air realm's, places the derive reaches with no way back it models (a1's far side, whose Flower and Filter teleports land in the air; a3's slides, a5's sub-mains, a6's key islands), and 16 of life and death's (life's arrival and floor until the final joystick can be armed, its beam exits being the tower's only way out; d1's floating diamond's zone; d2's 13 lab floors below the fall, whose way back up the derive doesn't model), which hold no spot (the conservative-kit rule, §4.10): R1.12's trap gate reads them. a6 is entered one way (its `A6_A1` is out of logic) and left by `Killed_levelSwitch` after the guardian or the disc teleport. At `frame_perfect` 604 nodes, the same locations; at `standard` victory does not hold (936 locations: besides realm 1's four w4 gems and the air realm's spots at the hard tier, the fire realm's ways in and out, f1's cavern, f3's key area and f4's main area, are curved jumps and flaps the derive rates hard, so the fire disc is never whole); at `safe` neither (183 locations): the safe tier's margins refuse jumps the vanilla run needs (P4's strict profile, §10.2b, owes that). `test_vanilla_placement_is_beatable_and_fully_accessible_without_tricks` checks the default's full reach and `test_vanilla_route_replays_in_order` the route (§13).
- **For the fill and the spoiler** (Step R1.9): `Logic.reads(settings)` gives the counters the compiled logic reads, each with its thresholds (an item none of whose counters is there never changes the reach, and the obsidian thresholds are the fill's bands); `reach(..., trace=[])` appends each round that collects something as a `Sphere` (its locations and the state it read), the spoiler's spheres.
- **The corpus** (plan §3.7): `tests/rando/plans/{valid,invalid}/*.json` are plans with their verdicts, each a JSON object with `db` (a database folder under `tests/rando/`), `pins` (what it pins), and optionally `placement` (the spots that differ from vanilla; `null` leaves a spot empty, as during a fill), `settings` (the options that differ from the database's defaults), `items` and `flags` (held and credited from the start), and `traps` and `after_completion` (the traps and the traps after completion it expects, exactly). A valid plan reaches victory and an invalid one doesn't. Step R1.5's plans run on `tests/rando/reachdb/`, whose victory is holding its one `power_life`: each plan moves it onto the spot whose reach it tests. Step R1.6's escape plans run on `tests/rando/escapedb/`, one room off its ledge per counter-example, whose victory is D76's shape: a terminal event in a one-way final arena that needs the one `power_life`. The review's counter-examples (plan §2.13, `$RP/review-logic/`) are CE1 `start_region_is_safe_before_the_hub_is_reachable`, CE2 `a_drop_whose_way_back_needs_a_lever_on_the_far_side_is_not_safe` (these two are plan §3.7's named tests), CE5 `pit_whose_way_back_needs_a_button_in_its_other_room_is_safe`, CE6 `victory_event_in_a_one_way_final_arena_needs_reach_only` and `location_in_a_one_way_final_arena_is_never_collected`, and CE7 `drop_into_a_pit_that_needs_water_to_leave_is_a_trap_until_the_water` (valid, with its traps). Step R1.7's run on `tests/rando/guardiandb/`, one guardian region (a hall's drop with 3 of the air disc into an arena whose boss needs the fire and opens the altar, whose slot fires the teleport, and a nook off the arena that needs the water, which a vault holds once the disc is whole), whose victory is the whole disc and the water: CE3 `guardian_slot_behind_a_one_way_boss_arena_gets_back_by_its_one_shot_teleport` (valid, with its traps and traps after completion), CE4 `progression_beside_a_guardian_slot_never_counts` and CE8 `guardian_boss_that_needs_what_only_its_region_holds_is_a_trap` (invalid); plan §3.7's `test_guardian_region_is_in_logic_only_with_three_of_its_disc_and_the_boss_requirements` is a test of its own, which also pins the one shot (the nook). escapedb's tank pins the escape cache (`node_a_failing_escape_reaches_by_a_skip_keeps_its_own_forced_flags`). `test_committed_valid_plans_solve_and_invalid_plans_do_not` runs the whole corpus and names each plan whose verdict is wrong.
- **Cost** (plan §2.13, §3.8; Step R1.7): each round is a breadth-first search, the escapes of the nodes of R not yet safe and of R_phys outside Safe, an R_phys fixpoint and a pass over every location and flag. Two things keep the escapes cheap, neither changing a result:
  - **the fast path:** a backward search from the start, in which an edge is passable on the items held, the flags credited from the start and the flags its own source node can set on them (a button pressed or a barrier destroyed there), finds the nodes that get back with no closure (each one's closure would take the same path);
  - **the cache:** in a round the counters are fixed, so a closure that fails fails every node it saw whose starting flags it held (their closures are inside its own), and those need none. The plan's "cached by (SCC, item counters)" is this, per round, on the nodes a closure saw rather than on a precomputed SCC graph.

  `scripts/rando_bench.py` (`docs/SCRIPTS.md`) times the load, the compile and a reach on the shipped database and on a synthetic authored one of the plan's size (600 nodes, 3,200 edges, 1,418 locations). At Step R1.7, five runs each, two invocations of each solver at a load of 44–60 on 24 CPUs [verified 2026-10-12, Step R1.7's solver bench]: the synthetic reach's median went from 224–287 ms (R1.6's solver) to 67–72 ms, its compile stayed at 124–136 ms (126–131 ms with the regions), and the shipped database's stayed at about 20 ms to compile and 3–4 ms to reach. Every result is the same (595 of 600 nodes safe, 19 traps, victory).

## 16. `derived/<level>.json.gz` (Steps R1.3c, R1.3d)

`python -m devkit rando derive LEVEL` (`docs/TOOLS.md`) runs the reach model (`src/azurkit/tools/randomizer/draft/`, ported from the randomizer evidence's reach v6) on one level of the vanilla ISO and writes this file, compact JSON with sorted keys, gzip-compressed with no name or time in its header; nothing edits it by hand. Its top-level keys:

- `_meta`: `format` `azurik-rando-derived/1`, `generator`, `level`, and `stamp` (`draft/export.py`'s `stamp`; Steps R1.3d, R1.32), the sha256 over the derive version (`DERIVE_VERSION`, which a change to the derive's output bumps), the draft tables, the level's generated file and `derive_inputs`, the only other data its derive reads: the level's `tricks.toml` `[[skip]]` entries, its level file's `node`, `button` and `barrier` arrays and every generated exit into it. A file whose stamp is not the current one is stale; an edit to another level's skip, a `[[skip_rule]]`, a level file's edges or locations, or a comment leaves it fresh.
- `level`, `params` (the cell size, the tiers, the probe ladder, the spawn spots, the envelope's sha256: the movement and the tiers it was derived under) and `counts` (triangles, owners, samples, regions, zones, edges by kind and confidence, flights, water, the barrier cut).
- `zones`: each zone (a strongly connected component of the regions under free movement: safe tier, no item, no gate, data or geometry confidence), its proposed node id, area, anchors, locations and cells. A zone is kept when it holds something, is at least 25 m² or an edge touches it.
- `edges`: zone to zone, aggregated by gates, confidence, probe class, skips, items, pads, kind and current. Each carries §5.1 `requires` with its `difficulty` (§4.3; gate, pad and skip atoms included) and `options` when a harder tier needs less: a movement tier's requirement is that of its hardest option whose difficulty the tier allows (`draft/export.py`'s `tiers_of`). It also carries `logic = false` on a probe-needed edge, `held` past an undecoded gate, and its `kind`, `confidence`, `probe`, `dh`, `gap` and `why`. A jump, flap, drop or step edge's `requires` (or each of its `options`) carries a `cert` (Step R1.2b, D167, D168): what its witness flight physically needs, `rank` (the air rank it flies with), `gap` (edge to edge; a walk-off's run off the edge), `dh`, `run` (a running takeoff), `runup` (the takeoff floor before its edge on the track), `headroom` (the roof over it, m above the takeoff; absent under open sky), `room_start` and `room_end` (the least room over the witness body's head, its 0.1 m tolerance in, under the roof over the arc's first and last quarter, m; absent where that end is open sky: the headroom's profile, which the re-check flies a taller arc against, AZ-387), `walk_off` or `lip`, a walk-off's `slope` (m its takeoff floor falls a metre along the run at the edge, from the top triangle under the last walk sample before it: the body leaves with that part of its run speed falling, AZ-365; absent on a level or rising lip), and `rim` when it lands under the far floor's top by the rim step-up (AZ-352: a sloped rim at the floor's edge, or a riser the floors meet at, lifts the body on; `dh` is then the level the feet reach), so another movement re-checks it (`physics.holds`). A sloped slippery floor (nz under 0.998) is no takeoff: the logic walks it only down, as a slide (AZ-347, AZ-359: the body slides back down it). A jump from a near-flat slippery one (nz 0.998 and up) is a standing jump, `run` false (AZ-366: a run from a stand slides there, 6-8 m in 3 s against 20 m), until L3 measures the ice run.
- `gates`: every gate (toggled solid, driven damage volume, door, static hazard), its members, driver, requirement and where it comes from (`requires_from`: a generated gate, its blocker family, or the wiring; `requires_undecoded` when none), the zones it separates, and its `bypasses`: per direction the far zones and the generated or confirmed skips its crossings need.
- `skips`: the held generated skips (D113, D114): `<level>.bskip.<barrier>.<from>.<to>.<kit>` for a barrier crossing and `<level>.current.<volume>` against a current, each `held` with `confirmed = "no"`, its requirement, difficulty and a witness route. `confirmed_skips` and `hand_skips` are the `tricks.toml` skips the export uses.
- `events`: the pads, pickups and arrivals reach sets, with the zones that set them (`event:` atoms).
- `mechanisms` (teleports, rides, updrafts, currents, spring blockers), `rigs`, `doors`, `objects` (each anchor's zones), `locations` (each pool location's zone, region and requirement, its least air per tier and its least flap flights) and `regions`.
- `coverage`: per tier, how many pool locations each rung of the ladder (nothing, air, the confirmed skips, gates open, then each probe class) reaches from the spawn, the side rows, R_phys, and the exits' least air.

Ids, names, counts, areas, relative heights and distances only, never a coordinate (plan §4.4); the consumer's check (`draft/export.py`'s `check_doc`, run by `tests/test_reach_model.py` over every committed file) refuses any number under a key it doesn't know as coordinate-free. The list sections (each list of objects) are written one entry per line, so a diff of two decompressed files stays readable.

## 17. `movement/<level>.json` (Step R1.14b; D167, D168)

`rando author` writes one beside each authored level's file (`draft/author.py`'s `movement_doc`; `tests/test_reach_model.py` checks each equals its authoring): what of the level's logic rests on a modelled flight, so a build re-checks it under its own movement sliders (`src/azurkit/tools/randomizer/movement.py`; [`GUIDE.md`](GUIDE.md#randomizer)'s "Works with movement mods"). One object, one certificate, row or node per line:

- `certs`: the level's certificates (§16's `cert`, each once, sorted), which the rest index;
- `edges`: each level edge row in logic (`from`, `to`, `difficulty`, `confidence`, `through`) with a term that needs a flight: per term of its `requires` (all of them, so a build can regroup them), the term's text and its **witness**: the certificates of the flights on the zone path, through zones that aren't kept, with the fewest certified hops, that gives the term at its tier (§4.10's contraction; a `probed` term's path may use its assumed or physics edges);
- `nodes`: each node of more than one kept zone with the certificates of the safe-tier, no-item paths that join its zones both ways (§4.10's join; data and geometry edges, so walk-offs and steps);
- `jumps`: each pool location the derive reaches by a jump from its zone's floor (`how = jump`), with its height above standing reach (`dz` less 1.5 m).

The loader reads the folder as `Database.movement`, outside `db_digest` (a plan's digest names the logic at vanilla movement), and refuses a stale file (§9 rule 23). A build at vanilla movement never reads it.

**`contact.json`** (Step X.11, D173's T6): flights of the movement files measured in simulator Level 3, the game's own code, with each slider's build laid over a vanilla snapshot (`devkit/reach/l3_contact.py`, [`SIMULATOR.md`](SIMULATOR.md) § "Overlays"), where the calculator models only arcs (a lip lift, a roof, a curved jump the derive admitted on assumption). Per flight: its `level`, `hop` (the level edge whose witness it is), the derive's zone `edge`, the `kit`, its `cert` (a certificate of that level's movement file, else stale: §9 rule 23) and, per Movement field (`run_speed` in m/s, `jump_scale`, `gravity`, `fps`, the flaps per shield `flaps1`-`flaps3`, ...) and measured tier (`frame_perfect`: any string reaches; `standard`: one whose robustness under jitter is at least 0.8, the floor the shipped ranges were measured at; a new `devkit/reach/l3_contact.py measure` uses D259's 0.5), the range `[lo, hi]` in which a string still makes it (`null`: that side not measured), with each field's `evidence` id (`l3:<evidence folder>:<pack.slider>@<snapshot metadata sha12>/<side>:<string sha12>`, the string that last passed). `free` is for the zones' free movement (none measured yet). `movement.measured` reads it; where exactly one movement field differs from vanilla and the flight has a range for it on that side, the range decides at standard and hard (the standard one) and at frame_perfect (its own, else the standard one), instead of the calculator; safe has none, so the calculator decides there inside the standard range and the flight fails past it (Step X.21: a flight L3 fails at standard fails at safe); two sliders moved at once go to the calculator. A certificate found in more than one level's movement file isn't matched (a measurement is of one flight).

## History

### Draft 0's verification (R0.6, 2026-10-11 and 2026-10-12)

Re-run 2026-10-11 after the fixes, from a detached worktree of main @ `0e048a3` with `AZURKIT_ISO` set to the main checkout's ISO.

- **The raw R0.3a/R0.3b outputs** [verified]. `sh $RP/r0/tools/r03_raw_outputs.sh <scratch>` remakes all 37 files of `$RP/wiring/` (11) and `$RP/thresholds/` (26). Before the fixes, `cmp` against the evidence copies gave 34 byte-identical; the other three were:
  - `wiring/prefabs_summary.txt`, which differed only in the order of its `moved={…}` dicts: `prefabs.py` built them from a set, so the order varied run to run. `prefabs.py` now sorts them, and the file was remade with the same content (checked with the dicts compared as sorted lists);
  - `thresholds/gamestates.{txt,json}`, remade on purpose with the fixed `when` rule (§3.7).

  After the fixes a fresh run gives 37 of 37 byte-identical.
- **The extract** [verified]. `uv run --locked python -I $RP/r0/tools/db_extract.py generated`.
  - It reproduces the census counts: 1,418 pool locations (79/100/1,146/69/24), 122 barriers, 77 geodes, 43 keylocks, 8 keylord systems (7 complete), 43 save points, 10 obsidian locks, 6 seals and 76 levelSwitches.
  - Against the first draft, only these change: 6 exits' `arrival` (§3.6), the new `arrival_by` and `arrival_graph_known` keys, 167 day/night `when` values (§3.7), and the citation in the two `characters` notes [verified, the old and new files compared in memory].
  - Two runs gave identical sha256 for all 23 files.
- **The migration and the check** [verified]:
  - `python3 -I $RP/r0/tools/db_migrate.py <worktree>/src/azurkit/tools/randomizer/logic_db.json generated . $RP/r0/out/census.json`, then `python3 -I $RP/r0/tools/db_check.py . --json check.json`.
  - Every TOML file parses, and all 159 expressions parse.
  - **0 issues** (rule 1 included). That is not "nothing open": 856 pool locations have no node yet (rule 9 would refuse them at load; 12 multi-node levels wait for R0.7's anchors), and 330 TODO fields remain (117 empty `destroy_from`, 42 `button.at`, 39 `edge.from`, 39 `edge.to`, 20 `edge.exit`, 8 `event.at`, 22 `route`, 43 `anchors`) [verified, `check.json`]; 0 since Step R1.8d (§10).
  - A second run of extract and migrate gives identical sha256 for every file.
- **D113 re-run (2026-10-12)** [verified, `python3 -I $RP/r0/tools/db_check.py . --json check.json` through `$EV/tools/py`]: 225 expressions parse (the 159 above plus 66 skip `requires`), **0 issues**; 66 skips in 18 level files (46 `in_logic`, 20 `held`), and the presets turn on 0 (easy), 7 (normal), 41 (hard) and 46 (expert). Mutations of a copy are each reported: a `trick:` atom or a bare trick name (`parse_error`), an unknown skip (`unresolved_skip`), a preset turning on a held skip, `skip_ceiling = 5`, a leftover `[tricks]` table or `default_tier` (`unknown_key`), an unknown family, a skip cycle, an edge `difficulty = 0` and an unrated in-logic skip.
- **D114 re-run (2026-10-12)** [verified, `$RP/r0/tools/db_check.py . --json check.json` and `$RP/tricks/tricks_check.py`, both through `$EV/tools/py`]: **0 issues** and **0 problems**. Every skip carries `confirmed`; of the 66 skips in the level files 4 are owner-confirmed and `in_logic`, 62 are `"no"` and `held` (the 9 candidate-family skips stay in `tricks.toml` only, all held). The presets turn on 0 (easy), 0 (normal), 4 (hard) and 4 (expert). A mutation run on copies (`$RP/tricks/tricks_mutation.py`) was caught 12 of 12 times: an unconfirmed skip put `in_logic` (both checks: `skip_in_logic_unconfirmed`), an `in_logic` skip with no `confirmed` (`skip_without_confirmed`), `by = "video"` and `confirmed = "yes"` (`bad_confirmed`), an owner ref that is no OWNER_TRICKS.md heading, an xemu ref that is not `<sitting>/<row>`, a held_reason without "unconfirmed (D114)", `priority` on a confirmed skip or on a skip with no video source, a `[[skip_rule]]` left `in_logic`, the same change made in db-draft only, and a preset override turning on an unconfirmed skip. The control (the Torpedo Skip `in_logic` with `{ by = "xemu", ref = "s7/F4" }` in both files) passes both checks with 0.
- **D118/D120/D122/D123/D129 re-run (2026-10-12)** [verified, `$RP/r0/tools/db_check.py . --json check.json`, `$RP/tricks/tricks_check.py` and `$RP/tricks/tricks_mutation.py`, all through `$EV/tools/py`]: **0 issues** and **0 problems**. 234 expressions parse (225 plus the 9 newly projected skip `requires`). 75 skips in 19 level files (18 `in_logic`, 57 `held`): D120's six families project their 9 skips, all held and unconfirmed. The presets turn on 0 (glitchless), 0 (easy), 7 (normal), 17 (hard) and 18 (expert), with movement tiers safe, safe, safe, hard and frame_perfect; `locations_proven` is 0 and 0. The mutation run catches 16 of 16, the control passing; its new cases are a preset with no `movement_tier`, a preset with `movement_tier = "easy"`, and a `[[location]]` with `proven = "yes"`.
- **D144 re-run (2026-10-12)** [verified, `$RP/r0/tools/db_check.py . --json check.json`, `$RP/tricks/tricks_check.py` and `$RP/tricks/tricks_mutation.py`, all through `$EV/tools/py`]: **0 issues** and **0 problems**. `presets/` is gone, and `settings/defaults.toml` holds D144's defaults (`skip_ceiling` 0, `movement_tier` hard, `dark_fire` 1, no toggle): it turns on 0 skips, share string `AZR-AAIA`. Both checks compute the retired presets' option sets as before: 0 (glitchless), 7 (easy), 10 (normal), 17 (hard) and 18 (expert). 234 expressions parse; 75 skips (18 `in_logic`, 57 `held`); the skip registry tag is `434ed23c`. The mutation run catches 24 of 24, and the control passes with a valid user-saved file (two toggles) added. The three preset cases now target a user-saved settings file, and the eight new cases are `skip_ceiling = 5`, `dark_fire = 0`, no `dark_fire`, a leftover `[knobs]`, the old preset `format`, a toggle on an unknown skip, a `presets/` file put back, and `defaults.toml` with `movement_tier = "standard"`.
- **No coordinates** [verified]. `generated/` holds no non-integer JSON number. Decimals appear only inside strings: link weights and factors in hints (0.01–5.67) and clock fractions in `when`.
