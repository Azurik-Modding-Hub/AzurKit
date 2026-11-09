# Azurik randomizer: design and implementation plan (archive)

> **Archived from Azurik_Modkit's `docs/ToDo/RANDOMIZER_PLAN.md`** (Step
> 4.24d), the plan the randomizer was built from in Modkit (Phase R1)
> and ported into AzurKit (`src/azurkit/tools/randomizer/`). AzurKit's
> code, data and docs cite it as "RANDOMIZER_PLAN §n"; this file keeps
> the sections they cite, §0, §2-§7 and §9 (risks), under their own
> numbers. Left out: the preamble's R0 records and sources, §1 (goals),
> §8 (phases and steps), §10 (owner questions) and §11 (sources); they
> stay in Modkit's history (the private archived repository). It is a
> record, not a rule: AGENTS.md and the code win where they differ, and
> its Modkit paths and verbs (`azurik_mod/`, `azurik-mod`) name what
> Modkit had when it was written. Its evidence lives outside the repo.
>
> **Labels:** [verified] read or run, with the source named; [inferred]
> reasoned from verified facts; [unverified] nobody has checked it.
> **Ids:** RQ-n owner questions (§10, left out); I-n investigations
> (§6); R0.n, R1.n the steps of Modkit's phases R0 and R1; R2.n later
> phases (§7). No game bytes: names, counts, offsets and VAs only.

---

## 0. Summary and recommendation

### What we build

We build a new item randomizer in Modkit (`azurik_mod/randomizer/`, Phase R1, D137), which AzurKit then ports (`azurkit/tools/randomizer`), in two parts with a plan file between them:

- **The planner** takes the level database, settings and seed, and produces a plan JSON. It is pure Python and needs no ISO. It consists of a level database, a solver, a fill and a spoiler.
- **The writer** turns the plan into an edit layer of byte changes (§12.2), computed from vanilla. It reads the result back with the same decoder and fails the build if any location does not hold its planned item.

The logic model is the owner's:
- powers are progressive counts;
- disc fragments are counted per disc;
- barriers have separate destroy and bypass rules;
- buttons, keys and obsidian thresholds are part of logic;
- each skip (a named, located use of a trick) carries its own difficulty (D113);
- level state is permanent. The few mechanisms that are not permanent are declared and handled (§3.1);
- the player leaves a level only through exits, so every node gets an escape check (§2.13);
- saving happens only at designated save points;
- the v1 pool is every pickup, including every gem.

**What a seed guarantees** (§2.13):
- every seed is beatable;
- every pooled location (except forfeitable ones, §2.9) is reachable and can be left again, for a player who collects in sphere order;
- a player who takes a one-way edge before holding what the far side needs can still softlock. The randomizer itself can't prevent that (it writes no code patch); the opt-in save-point warp `qol_save_warp` (R2.1, D202) is the safety net, out of logic. The spoiler lists every such edge, and a per-seed trap gate rejects seeds that open new trick-free traps.

We do not extend today's planner [verified, (private evidence) §12]:
- its model has none of these concepts;
- its forward fill is about O(n²) and already takes 70 ms for 27 items;
- its search-and-replace writer caused M3.

### Order

1. **Now, in this repo.** D71 (M3) lands: the owner reads the golden diff, and `p1/review-fixes-code` merges into `p1/stack`. Then, optionally, AZ-157 and the false CLI help texts. Then the old planner is frozen (R0.1).
2. **Now, as evidence only (no repo edits):**
   - the owner answers RQ-1 to RQ-11. RQ-7 and RQ-10 need explicit answers;
   - I-0 decodes the save fields so that test saves can be built;
   - two xemu sessions answer the investigations that block v1 (R0.4a/b);
   - an xemu session checks writer feasibility (R0.5);
   - the agent bootstraps the database and freezes its file format (R0.6);
   - the owner annotates w1 and town (R0.7). *R0 (D108, Q255):* R0.7 is now the owner's review of agent drafts (R0.6b's geometry drafts; §4.5, §8.1);
   - I-1 (the node section's wiring) runs in the background. It speeds the work up but nothing waits for it.
3. **This plan joins the Step 4.0 delta design packet** (D13, D66) before 4.10b. The packet includes a compact spec for the Randomizer tab.
4. *2026-10-12 (D137): in Modkit now, as Phase R1 (§8.2); AzurKit ports it after Step 4.9.* ~~**In AzurKit, after Step 4.2 and the Q85 review (RQ-7, recommended option b; *D79 chose (a), keep D7: this starts after Step 4.9*):**~~ the level-graph reader, then the pure planner on a toy database, then town and water.
5. **A vertical slice comes next.** The fill and plan file come first, then the writer with read-back once Steps 4.4 and 4.5 exist. The owner boots the first seed after one realm, not after five.
6. **Then:**
   - the remaining realms, each ending with a bootable slice;
   - the spoiler, settings (D144) and trap gate;
   - the movement rule and layer integration;
   - the CLI, hub tab and MCP tool;
   - the cron soak, then closing AZ-157 to AZ-161 and AZ-164 as superseded. *R0:* only AZ-160, AZ-161 and AZ-164 are left. AZ-157 was fixed (Step 2.16c), and AZ-158 and AZ-159 closed as not defects (Step 2.19h; §8.4).
7. **Later phases (§7):**
   - a safety net;
   - barrier-requirement randomization with visual indicators;
   - room, enemy and key/lock randomization;
   - powers beyond 3;
   - rewards for gem and obsidian counts;
   - the post-v1 settings.

### Where this plan refines the owner's notes, and why

| Owner's note | This plan | Why |
|---|---|---|
| "We must guarantee a 4th fragment **or a useless item** is placed there" (no-return spots) | The guardian slot keeps its vanilla 4th fragment (RQ-4). Entering the no-return region is in logic only with 3 of that disc **and** everything needed to reach and collect the slot, including the boss. The region's other locations are *forfeitable*: they hold no progression and no obsidian (§2.9). | Under exits-only, a useless item there is a permanent softlock (ADVICE). The review found three more holes [verified toy, `review-logic` CE3, CE4, CE8]: an arena whose boss isn't checked, a teleport that fires once, and re-entry after it. |
| "Collecting the 4th fragment of a disc … sends the player back to town_central" | This happens only in that disc's guardian level (a6, w3, f6, e5, life). Each of those levels has its own chain: fragment count → disk placed → exit to town [inferred, strong; (private evidence) §2]. With the vanilla 4th at the slot, the 4th fragment is always collected there. | No game code tests fragments; the level graph does [verified: a sweep of `.text` immediates found no fragment fourcc]. *R0 (§2.9): the chain is in a6, w3, f6 and e5, and in w1 (touch-gated); life has none [verified data].* |
| "Signify these as items with reqs but no node (disconnected item)" | A no-return location sits on an ordinary node inside a derived no-return region. Its only escape is a one-shot teleport (§2.9). | One reachability engine. A disconnected item would need its own code path. |
| Level state persists permanently | True for latches: destroyed barriers, pressed one-way buttons, killed overlords. Five mechanisms are not monotone and are declared, each with its own handling (§3.1): the one-shot disc teleport, toggles, the key-slot cap, w4 day/night and the minecart. | ADVICE names the cart. The logic review found the other four [verified names; effects inferred]. |
| Each node defines its gems | A node is defined by named **anchors**. `db-extract` assigns each location to a node in memory; only `location → node` is stored (§4.1). Per-node totals are derived. | In 8 levels one cell holds ≥97 % of the pickup generators: w1, w3, a1, a3, a5, a6, life, d1 [verified, `census.json` `per_cell`, recomputed 2026-10-10]. In w1, 79 of 81 pickup generators sit under generic parents [verified, `review-feasibility` `misc.py`]. So neither cells nor names give sub-regions, and coordinates may not be stored. |
| v1 pool = everything, gems included | Everything is shuffled. By default (RQ-3), gems shuffle among gem locations and everything else among the other 203 locations. | With progression on ~1,200 gem spots, every gem's node assignment could make a seed unwinnable. A 10 % knob would move only ~17 items [inferred, scope review]. |
| "Every individual gem" | The unit is a generator's **payload** (item, yield). The 1,146 single-gem generators are individual checks, including the 231 inside geodes. The 69 multi-gem clusters (396 gems, 3–21 each) are one check each (RQ-9) [verified, `review-feasibility` `gens.py`, `geo.py`]. | Splitting a cluster into single gems needs structural XBR edits that nothing supports. Retyping clusters freely could push diamonds to 268 and rubies to 264, below the 300 the third fuel upgrade needs [verified, `myield.py`]. |
| Barrier requirement "water1", "earth2+fire2" | A barrier's requirement is an **element combination** taken from its damage fourcc through config's `magic` table (ice block = fire + water). Whether a level (1/2/3) is also required is I-2. *R0: it is (I-2, §2.4).* | [verified, census §4] `logic_db.json`'s barrier map is wrong for 3 of its 7 types. |
| Barrier requirements given per direction | Destroying a barrier sets one permanent flag that opens both ways. Each barrier has a `destroy_from` list (the sides it can be destroyed from) and a directional `bypass` rule (bskip; repeatable). | ADVICE: asymmetric destruction collapses once state is permanent. Only the bypass and *where* the barrier can be destroyed from stay directional. |
| Key requirement "specific key or type" | A key is a **type with a count**. Types are shared across levels: the 6 key_battery from e7 open locks in e7, e5 and e2. A "specific" key is a type with one copy. | [verified by pattern search, census §5; the field itself is not decoded, and 4.10a pins it] The 39 keys and 39 coded locks match type for type. *R0: the type is a fourcc at the lock platform's +0x40, and a lock uses its key up (§2.6).* |
| Minecart as a shared lock | Cart edges stay in the physical graph for the trap check. They leave logic only if I-10 shows that no other edge depends on the cart's side. Otherwise logic adds a one-bit product state (§2.10). | It breaks monotonicity (ADVICE). Its mechanics are not decoded [inferred, (private evidence) §8]. *R0: two e2 gondola pairs, one to e5 and one to e7 (§2.10).* |
| No victory condition | Victory is **defeating Spideyzar** (RQ-1). It needs reach only, not escape (§2.13). | It is the game's own end trigger [verified, `loading_zones.py` `_ENDING_ZONES`]. It defines what a "useless" item is. |

### Five research facts that shaped this plan

1. **Level logic is level data, not code** [verified, (private evidence) §0].
   - Keys, seals, obsidian locks, the disc teleport and persistence are all wired as node graphs in the level XBRs.
   - The repo can read node names but not their wiring or values. I-1 closes that gap. Owner knowledge and xemu can fill in until it does. *R0: R0.3a and R0.3b decoded the wiring and the values with evidence tools (not repo code).*
2. **Spawn points share one name string per item type in a level** [verified, census F1]. Exits share destination strings the same way (F2).
   - So per-location placement must repoint each generator's reference. It must not rename the shared string; renaming shared strings is the M3 failure class.
3. **There are exactly 100 obsidians, and the 10th town lock needs all 100** [verified]. Enemies drop no gems [verified config], so obsidian counts can't be farmed from enemies; an item on one of the 12 unsaved all_fuel spots respawns on every visit (AZ-467; seen in xemu by R1.26's sitting: f4's r1540 taken twice), so since Step R1.37 the fill puts no obsidian and no progression there (§3.3).
4. **A barrier's requirement is data** [verified]: a damage fourcc combined with the `magic` table.
   - There are 122 barrier groups. That count comes from a grouping heuristic, and 29 groups have 2–5 shapes, so they need owner review [verified, `review-feasibility` `misc.py`].
   - There are 77 geodes, each made of 3 single-gem generators [verified, `geo.py`].
5. **Fuel resets to 50 on every new game or load** [verified static], and caps rise only with gems. So fuel is a difficulty setting, not a logic gate [inferred].

---

## 2. The logic model

### 2.1 Namespaces: items, counters, flags, tricks, skips

The ADVICE's main point is to keep item ids apart from requirement thresholds. Today's code mixes them: `power_water_a3` alone does not open `power_water` gates [verified, AUDIT new finding A].

| Namespace | What it is | Examples | Where it comes from |
|---|---|---|---|
| **Item** | A pickup's type, as written into a generator. Several copies can exist. | `power_air`, `power_water_a3`, `frag_water_2`, `key_battery`, `obsidian`, `sapphire` | config `critters_item_data` names [verified] |
| **Counter** | A number the logic reads. Each item adds to one or more counters. | `air`, `water`, `fire`, `earth` (power levels); `discw`, `disce`, `discf`, `disca`, `discl` (fragments held); `obsidian`; `sapphire`, `emerald`, `ruby`, `diamond`; `key.<type>`; `life`, `staff`, `ammo` | an item→counter table in the database |
| **Flag** | A world change, set once. | `w1.fbarrier1.destroyed`, `w1.keylord.killed`, `town.obsidian_lock3.open`, `a6.disc_placed` | barriers, buttons, events (§2.4–2.7) |
| **Trick** | A technique family, with no tier (D113). It names and groups skips. | `bskip`, `pstorage`, `saveanywhere`, `rjump`, `tjump`, `itrig`, `nolight` | `world.toml` |
| **Skip** | A named, located use of one or more tricks, with its own difficulty (2 standard, 3 hard, 4 frame-perfect: D259 folds 1 safe into standard). It is a setting, not state. | `w1.torpedo_skip`, `e6.tree_song_skip`, `w1.firewall01_air2_beach_town` | the settings |

Rules:

- **Powers.** `power_<elem>` and `power_water_a3` each add 1 to that element's level, as the owner's notes say. Counters are not capped at 3, so the "air4–6" extra (§7) needs no schema change.
- **Fragments.** Each disc counter counts the distinct fragment items held.
  - The inventory has 20 fragment slots, `fg{e,a,f,w,l}{1..4}`, each 0 or 1 [verified static, (private evidence) §7].
  - So a second copy of a fragment would add nothing [inferred]. Each of the 20 fragment items stays unique in the pool, and the fill never duplicates one.
- **Death disc.** `discd` is awarded at the win and is not in the pool.
- **Keys.** `key.<type>` counts the keys held. Whether a lock uses up its key is I-9; §2.6 covers both answers.
- **Gems.** Gem counters are uncapped [verified static]. The fuel tiers derived from them are covered in §2.11.

### 2.2 Requirement grammar

The stored form is one expression string. It is parsed once at load into an AST, and the parser fails closed on anything it does not know. This keeps today's fail-closed idea [verified, AUDIT §10].

```
expr     := and ( "|" and )*
and      := unary ( "&" unary )*
unary    := "(" expr ")" | atom
atom     := COUNTER ">=" INT              # air>=2  discw>=3  obsidian>=60  key.battery>=1
          | "flag:" FLAG_ID               # flag:w1.fbarrier1.destroyed
          | "skip:" SKIP_ID               # skip:w1.torpedo_skip   (holds when the settings turn it on and its own requires holds; §2.15)
          | "barrier:" ID ":" ("destroy" | "pass:" FROM "->" TO)   # indirect, expanded at load
          | "button:" ID | "event:" ID    # indirect: the object's own requirement plus its flag
          | "true" | "false"
```

**The owner's shorthand is accepted as sugar:**
- `water1` means `water>=1`;
- `discw3` means `discw>=3`;
- `earth2+fire2` means `earth>=2 & fire>=2`;
- a bare trick name such as `bskip` is refused: write the skip it means, `skip:<id>` (D113; until 2026-10-12 it meant `trick:bskip@<the object's default tier>`).

**Bare lists are not accepted.** Today's database reads `[a, b]` as AND [verified, AUDIT §2.1], while the owner's example `[water1, air1+bskip]` means OR. Requiring one explicit operator removes that ambiguity.

**Indirect references resolve through objects**, as the owner describes: barriers, then buttons, then keys.
- An edge names the barriers it passes through (`through = ["w1.fbarrier1"]`), and the solver works out "passable from A to B" (§2.4).
- Objects may reference other objects. A cycle is a load error.

### 2.3 Levels, nodes, edges, locations

**Level.** One of the 22 playable XBRs [verified list, census]:
- town;
- w1–w4;
- a1, a3, a5 and a6, plus airship;
- f1–f4 and f6;
- e2, e5, e6 and e7;
- life, d1 and d2.

`training_room` is a 23rd file. It is not reachable in play and stays out of the pool.

**Node.** A region of a level, named the owner's way: `<level>_<area>`, such as `w1_beach` or `town_central`.
- The start is `w1_beach`; today's database already uses it [verified]. The start is also the escape anchor (§2.13).
- The hub is `town_central`. Today's database calls it `town_core`, and the migration renames it.
- **Membership.** A node lists its `anchors`: named objects such as save points, exits, barrier groups, keylocks or cells. It may also override individual locations by id. `db-extract` assigns every location to the node of its nearest anchor (§4.1).
  - A cell is a usable anchor in the fire and earth levels, which have 15–32 cells each; e7 is the exception with 5 [verified, census].
  - Water and air levels need anchors inside their one big cell.
- Node fields: `anchors`, `dark` (§2.12), `hub`, `save_points` and `escape` (§2.9). `no_return` and `forfeitable` are derived (§2.9).

**Edge.** A directed move between nodes. Its `kind` is one of:
- `walk`;
- `drop`: one way, such as a fall ledge. Falls of 17 m or more are lethal [verified config, (private evidence) §12];
- `exit`: a `levelSwitch` that crosses levels. v1 keeps the vanilla destination. **An `exit` edge never lists `through`.** A barrier sits on a `walk` edge inside one level, and an exit's arrival spot is its own node;
- `teleport`: an in-level `Teleporters` (8 levels [verified]) or the disc teleport;
- `cart` (§2.10).

Edge fields:
- `requires` is the **physical** requirement, with tricks;
- `through` lists the barriers the edge passes;
- `assumes` lists flags a vanilla design expects to be set first (§2.13);
- `logic = false` marks an edge that can be taken physically but is left out of logic, such as a cart ride.

A two-way passage is two edges, which may have different requirements: the owner's "NodeA→NodeB and NodeB→NodeA".

**Location.** One pickup generator, or one consumable spawn.

| Field | Meaning |
|---|---|
| `id` | `<level>/g<graph>/r<record index>`. It is stable and contains no game name, so it survives RQ-10. Graph 1 is real: w3 keeps 74 pickups and town 95 there [verified, `misc.py`]. |
| `name` | the generator's debug name; generated, for display only |
| `class` | major / obsidian / gem / consumable |
| `vanilla` | the vanilla payload (item, yield) |
| `template` | the vanilla template name, including the `_move` variants (§5.2) |
| `yield` | 1, or 3–21 for the 69 clusters |
| `on_load` | whether it spawns when the level loads, or is triggered |
| `group` | the geode it belongs to, if any |
| `node` | assigned through anchors (§4.1) |
| `requires` | extra conditions: the barrier or geode that contains it, the event that triggers it, a button |
| `no_return`, `forfeitable` | derived (§2.9) |

### 2.4 Barriers

This follows the ADVICE's split, applied per barrier as the owner asked. The example below uses `w1/FireWall_01`.

- w1 has `FireWall_01` (`watr`) and town has `FireWall_02` (`watr`) [verified, `census.json`].
- Which of them is the owner's fbarrier1 is part of I-15. *R0 (thresholds §10, rz-b1):* most likely w1's `FireWall_01`, which sits beside where town → w1 arrives [inferred]. Which arrivals it gates, and which way vanilla passes it, stay with the owner (Q251; Q255's drafts).

```toml
[[barrier]]
id           = "w1.fbarrier1"          # owner's id; maps to the vanilla group below
group        = "FireWall_01"           # generated (census): w1, kind firewall, damage fourcc watr
damage       = "watr"                  # generated; elements via config `magic`: W
level        = 1                       # generated once I-2 decodes it, else authored
destroy      = "water>=1"              # derived from damage + level unless overridden
destroy_from = ["w1_beach", "w1_town_gate"]   # nodes it can be destroyed from
persist      = "permanent"             # or "respawn"
bypass       = { "w1_beach->w1_town_gate" = "skip:w1.firewall01_air2_beach_town" }   # one direction, repeatable, no flag; the skip itself needs air>=2
contains     = []                      # location ids freed when destroyed
required_for = []                      # events that need it destroyed (e.g. the earth guardian)

[[edge]]
from = "w1_beach"
to = "w1_town_gate"
kind = "walk"
through = ["w1.fbarrier1"]
# plus the reverse walk edge, and w1_town_gate -> town_central (kind "exit", never `through`)
```

- **Destroy is symmetric, permanent and global.**
  - Standing at a node in `destroy_from` and meeting `destroy` sets `flag:<id>.destroyed`.
  - The flag opens every edge `through` this barrier in both directions for good, and frees its `contains` locations.
- **Bypass is directional and repeatable.** It sets no flag and frees nothing. A skipped barrier is never destroyed, as the owner says. The bypass is checked on every crossing.
- **Respawning barriers** (`persist = "respawn"`) set no flag.
  - `destroy` and `bypass` are re-checked on every crossing, and the barrier's contents need `destroy` at the moment they are collected.
  - A respawning barrier with `contains` must either name the inside as a node or list it in `destroy_from`, so that escape from its alcove is checked (§2.13). Otherwise loading fails.
  - Known candidates: the 11 `crack_block_respawn` in a1 [verified names], and fire walls with `OpenNCloseToggle` [inferred]. I-8 settles them.
  - *R0 (I-8, rz-b1):* both respawn.
    - A fire wall opens on each hit and is shut again 5.8 s later. It is unsaved, so it is shut again after an exit [verified xemu; the exit half inferred]. Walking into a shut one costs 15 HP per contact and never gets through [verified xemu].
    - a1's `crack_block_respawn` breaks about 3.8 s after the player stands on it and is back about 13 s later [verified xemu].
    - Ice blocks, acid blocks and geodes latch and are saved [verified data]. The ice block and the ruby geode were also seen staying open across exits [verified xemu, placed].
- **Requirements come from data** [verified, census §4]. The damage fourcc maps to elements through config `magic`:

  | Damage | Elements | Barriers it opens |
  |---|---|---|
  | `watr` | W | fire walls |
  | `stem` | F+W | ice blocks |
  | `acid` | E+W | acid blocks |
  | `fire` | E+F | |
  | `wind` | E+A | |
  | `smsh` | E+A+F | |
  | `ice` | E+A+W | |
  | `litn` | A+F+W | |

  - There are 122 barrier groups: 39 ice blocks, 32 fire walls, 22 acid blocks, 6 crystals, 4 traps and 19 others.
  - The grouping is a heuristic. 93 groups have one shape and 29 have 2–5 shapes; none mixes fourccs [verified, `misc.py`]. The 29 multi-shape groups get owner review.
  - The hand-written `barrier_map` and the 17 hard-coded `BARRIER_OFFSETS` go away. There were 19; two were geodes, not ice blocks [verified, census F3], and Step 2.16j dropped them (AZ-207).
  - Whether the level number matters (water 1/2/3) is I-2. The `Level1/2/3_sphere` parts inside the ice-block prefab suggest it does [inferred].
  - *R0 (I-2 answered; rz-b1, thresholds §10):* it does.
    - A barrier needs its element combination **at a power level**. e7's level-2 fire wall stayed shut under level-1 water and opened at level 2 [verified xemu, placed].
    - The attack's level is the **minimum** of the selected elements' levels [verified xemu, placed; static 0x838E0].
    - Each group's level comes from its `magic` link curve [verified data]. Ice blocks: 15 at level 1, 4 at level 2, 21 at level 3. Acid blocks: 3, 11 and 7. Fire walls: 13, 2 and 2. All 77 geodes: level 1.
- **How a combination's level is computed** is I-3. ~~Examples are whirlwind 4 for e2's song and the e5 boss's `BossWhirlwindLevel_plusCombiner`.~~
  - ~~The name "plusCombiner" hints at a sum of the element levels [inferred, weak].~~
  - ~~Until I-3 answers, combination-level gates are authored by hand.~~
  - *R0 (I-3 answered; rz-b2, thresholds §6):* a combination's level is the minimum of its elements' levels, as for a barrier.
    - "Whirlwind 4" was a misreading. The 4 in `Crystal_Whirlwind4_Hit` is e6's wack-type code 4 (wind), not a level.
    - Each song crystal takes any non-zero `magic` of its combination, so level 1 of the right staff sets it [verified xemu, placed, for wind].
    - `BossWhirlwindLevel_plusCombiner` counts the melted acid blocks in e5's arena (§2.7) [verified data].
- **Geodes are containers, not barriers on edges** (census recommendation 5).
  - There are 77. Each is **3 triggered generators of 1 gem each**, 231 generators in all [verified, `geo.py`].
  - Each of the 3 is a location with `yield = 1`, `on_load = false` and `requires = <destroy of the geode's fourcc>`. The 3 share one `group` id.
  - Geode fourccs:

    | Geode | Damage |
    |---|---|
    | DiamondStone | `litn` |
    | EmeraldStone | `wind` |
    | RubyStone | `fire` |
    | SapphireStone | `ice` |

### 2.5 Buttons, switches and levers

- The engine has **no button node** [verified, (private evidence) §5]. A button is a trigger's `actionButton`, `touch`, `whack` or `magic` output, wired to a `switch`.
- The families are:
  - `ActionButton_toggle`, inside every key lock;
  - `lever_1way` in f2, f3 and f4;
  - `AirSwitch` in a1, a3 and a6;
  - teleporter toggles.

```toml
[[button]]
id       = "f1.fire_keylock"
at       = "f1_gate"                 # the node it is pressed from
requires = "key.fire1>=3"            # see §2.6 for how key counts are derived
mode     = "latch"                   # "latch" | "toggle"
sets     = "f1.fire_keylock.open"    # permanent flag for a latch
```

- An edge or location that needs a button uses `flag:<id>.open`, or `button:<id>`, which expands to the same flag.
- **`mode` is required.**
  - A `latch` sets a permanent flag.
  - A `toggle` can be undone, so it is non-monotone (§3.1). **A toggle whose "off" state gates any edge is a load error** until it is modelled as a product bit.
  - I-8 presses each family twice and compares the saves. The name `lever_1way` implies that the other levers flip back [inferred].
  - *R0 (I-8, rz-b1):* a1's `AirSwitch` is a latch: it is saved, and a second press does nothing. a1's `UpperBridgeToggle` is a toggle, flipped from each end, and is unsaved [verified xemu, placed]. `lever_1way`, the teleporter toggles and `ActionButton_toggle` were not pressed twice.
  - *R0 (R0.3a §2):* a `switch` with no `turnOff` or `toggle` input is a one-way latch. Its `lock` attribute only makes it ignore input until the output reaches its goal [verified static].
- Buttons that are whacked or take magic carry the element requirement (as `magic`), like barriers.
- Moving buttons, or changing what they need, is §7 (node-section writes).
- *Step R1.8f (2026-10-13): the progression minigames.* Seven skill puzzles gate progression: w1's periscope torpedo, w2's hose, a5's cannon, a6's lasers, e6's spotlights and tree song, and life's filament cores (`docs/RANDOMIZER.md` "Minigames"). Each is decoded from the wiring in its realm's `draft/authoring/<level>.toml`: the logic models each as the event, gate or edge it opens, with only what the game asks (a joystick, the keys that live it, the crystals and staffs of the song); the aim, timing and order are skill, not items. All can be retried (the owner, 2026-10-13; each one's reset is in its `why`), so a failed attempt is never a softlock. `scripts/xemu_minigames.py` solves each in closed loop on the xemu oracle, for the proven-spot sittings and Step R1.16's playthrough.

### 2.6 Keys and locks

- **Keys are typed counts** [verified by pattern search, census §5; 4.10a pins the decoded field].
  - There are 16 placed types and 39 instances. Four more types exist in config but are never placed: key_fire2/3 and key_water1/2.
  - There are 39 coded locks, plus 4 key-less lock rigs in e5 that need I-1.
  - Types cross levels [inferred from matching types]:
    - key_battery (6) opens 3 locks in e7, 2 in e5 and 1 in e2;
    - key_life1 (3) opens 1 lock in w1 and 2 in life.
  - *R0 (R0.3a §4):* the key type is a fourcc at the lock platform's record +0x40 [verified static and data]. e5's 4 key-less rigs are relays that coded locks drive. Types do cross levels: e7's `key_battery` opened e2's `earth_keylock2` [verified xemu, placed; rz-a].
- **A lock is a latch button** whose `requires` is a key count. The count depends on I-9: is a key used up when it opens a lock?
  - *R0 (I-9 answered; rz-a, R0.3a §9.2):* **a lock uses its key up**. It takes the action button (X); a touch does nothing [verified xemu, placed; static 0x58AD0]. So the "used up" rule below applies.
  - **Not used up:** `key.<type> >= 1`.
  - **Used up:** OoTMM-style worst-case counting, **under every setting** (D144; *was:* in every preset). It is a correctness rule, not a difficulty knob.
    - Lock L needs `key.T >= 1 + (the number of other T locks the player could open without passing L)`.
    - The database tool computes this once, from reachability with every item except passage through L, and writes it into the generated data.
    - Keys equal locks for every placed type [verified], so the worst case never exceeds what exists.
    - The count is sound, but over-strict when a key sits behind a parallel lock [verified toy, `review-logic`]. The vanilla-route check (§4.3) shows where.
    - *Step R1.8l (AZ-345), the key rule:* another lock counts only where a key spent there isn't given back on the spot: a lock with a key of its type on every way to it is matched to that key, and that key, while it lies there, counts as held (`docs/RANDOMIZER_DB.md` §5.5). Life's two keys lie ahead of its two locks, so w1's water keylock needs one key, not three.
- **Inventory capacity is a hazard.** The inventory ends with 5 empty slots that look like key slots [inferred, (private evidence) §7].
  - If a player can hold only 5 key types at once, a seed that hands out 6 or more types before any is used could lose keys.
  - I-9 tests this. **If it is real, keys stay vanilla in v1.**
  - *R0 (I-9 answered; rz-a):* it is real. There are 5 key slots [verified static 0x58090]. Holding 5 other types, a 6th type is refused and the key stays in the world [verified xemu, placed]; the popup says "You can only carry five different types of keys." [visual, not retained]. A slot whose count is 0 is reused. **So keys stay vanilla in v1** (§3.3's pre-fill).
  - Restricting keys to their own realm would not limit how many types a player carries: key_life1 and the obsidian keys already cross realms in vanilla.
- **The secondary name copies** that the key shuffle never rewrites are a writer concern (§5.2), not a logic one (AZ-158; 18 of 22 key slots [verified]). *R0 (R0.3a §5):* they are no concern. Each is a lock's pooled `characters/<key>/fx/fx_<key>` effect path (its `public_Key_effectShape`), or a transform's debug name. Nothing tied to where a key is placed reads them [verified data]. AZ-158 closes as not a defect.

### 2.7 Enemies, overlords and bosses

- **Events** are flags whose requirement is "be at this safe node and meet this":

  ```toml
  [[event]]
  id       = "w1.keylord.killed"
  at       = "w1_ocean"
  requires = "true"

  [[event]]
  id       = "e5.guard_earth.killed"
  at       = "e5_boss"
  requires = "barrier:e5.AcidBlockBossGroup:destroy"   # R0: the four arena acid blocks, and no crystal (I-17)
  ```

- **Red overlord (keylord) keys.** The key location requires `flag:<level>.keylord<N>.killed`.
  - The `keylordSystem` prefab bundles the spawner, the key and its trigger [verified names].
  - There is 1 in w1. In e7 there are either 6 (census generators) or 7 (prefab instances, engine scan); I-1 resolves the difference.
  - *R0 (R0.3a §3, §6; rz-b2):* e7 has **6** working systems. `keylordSystem5` is a remnant that nothing drives [verified data; verified xemu].
    - The kill latches `toggle2`, which takes away the solid cage at the key between 2.25 s and 6.75 s later. The key spawns at load, and the cage is collision only.
    - A keylord killed through its own damage path fires `numDead`; writing HP 0 directly doesn't [verified xemu, placed; I-18].
  - Moving only the overlord (enemy randomization) would break the link [inferred]. So in v1 enemies stay where they are, and the "enemy requirement" is just the event.
- **Bosses** [verified]:

  | Level | Boss |
  |---|---|
  | w3 | guard_water |
  | a6 | guard_air |
  | f6 | guard_fire1–3 |
  | e5 | guard_earth |
  | airship | balthazar |
  | d1 | spideyzar |

  The 4th fragments of earth, water, air and fire spawn only after their boss [verified]. Their locations need the boss event.

  *R0 (thresholds §3, §5):*
  - The 4th air and fire fragments come from `characters.xbr` graphs 16 and 21. The a6 and f6 level generators the census listed for them are dead [verified data].
  - Spideyzar spawns when d1's elevator call selects floor 9. The keyed way there is `switch9`, keyed by `death_keylock2`'s key_diamondbattery. A touch of `CallField9Shape` also selects floor 9, and whether a player can reach it is open. Killing him ends the game [verified data].
- **The earth guardian** (the owner's note):
  - The acid blocks in his arena (`AcidBlockBossGroup` [verified name]) have `contains = []` and `required_for = ["e5.guard_earth.killed"]`.
  - ~~The crystal latches `Crystal_Smash2_Hit` and `Crystal_Whirlwind4_Hit` [verified names] suggest that the fight also needs smash (E+A+F) and whirlwind at level 4 [inferred]. I-17 confirms; until then the requirement is authored by hand.~~
  - *R0 (I-17's data half; thresholds §6, rz-b2):* the crystal latches are e6's song globals and play no part in the fight.
    - The guardian sits behind `EarthBossDoor`, which e5's seal moves (earth ≥ 3).
    - He dies once all four arena acid blocks, `AcidBlock_04`–`07`, are melted, each by a `magic` of at least 2 [verified data].
    - That this means acid at power level 2 is [inferred, static].

### 2.8 Thresholds: obsidians and gems as accumulators

- **A threshold atom (`obsidian>=60`) reads a counter.** The counter is the number of those items collected from safe locations in the current fixpoint. That is the ADVICE's "max obtainable under current reachability", computed as a fixpoint.
  - Obsidians are items in the pool, so this is just counting.
  - An item collected at an unsafe node never counts.
- **Town obsidian locks** [verified thresholds]:
  - The thresholds are 10, 20, …, 90 and 99.99983, so lock 10 needs all 100.
  - Each lock is a latch button with `requires = "obsidian>=N"`. Its contents are a location that needs that button's flag.
  - The `--obsidian-cost` thresholds are a setting that rewrites both tables [verified offsets, `shufflers.OBSIDIAN_LOCK_TABLE_A/B`].
  - Unset, the setting leaves both tables as vanilla's; `--obsidian-cost 10` writes exactly 100.0 into lock 10 of each, so it is not a byte no-op (AZ-239) [verified 2026-10-11: float32 reads of both tables, where cells 1-9 equal 10k and cell 10 is 100 − 1.678e-4; and two `randomize-full --seed 1` builds with every pool off through `tests._randomize_driver.build`: unset changes no game file, 10 a non-vanilla `town.xbr`].
  - The 4.10 writer leaves a threshold untouched when the setting equals vanilla (Q243). ~~Whether a lock opens at `>=` or `>` is still undecoded (I-1, R0.3b).~~
  - *R0 (thresholds §4):* lock k opens on the action button while the player holds **at least 10k** obsidians: a step in its link curve at 10k, and lock 10's at 99.99983, so 100. `TABLE_A` is the help curve's threshold and `TABLE_B` the opening curve's [verified data].
    - A threshold written above 100 acts as 100, because each curve's last key sits at 100. So `--obsidian-cost` above 10 opens the upper locks at 100 (AZ-273) [verified data].
- **What the locks hold in vanilla**, locks 1–10 in order [verified names; lock k is matched to threshold k by order, inferred; *R0: matched by namespace, verified, thresholds §4*]: power_life, key_obsidian1, power_life, power_staff1, power_life, key_obsidian2, power_life, power_staff2, power_life, power_ammo.
  - ~~key_obsidian1 and key_obsidian2 open town's two life key locks, so the life realm probably needs at least 60 obsidians [inferred].~~
  - *R0 (R0.3a §4.2, §9.3):* key_obsidian1 and key_obsidian2 open town's infinite health and infinite fuel dispensers. The town → life exit is gated by the life seal (3 life fragments) [verified data].
  - *R0 (thresholds §4):* the staff visuals follow the lock 4 and lock 8 generators, not the item placed there [links verified; effect inferred].
- **Lock 10 and full clears.** By default, lock 10 (all 100 obsidians) and any location that needs a full clear are `excluded`: they hold only useful items or filler (RQ-5). This follows AP's rule of keeping progression off locations that need an exhaustive collection.
- **Gems.** The grammar supports `sapphire>=N` and the others, as the owner asked, although vanilla never gates on gems. Gem thresholds stay out of logic by default.
- **Farmability.** A threshold is only valid logic if its source can't be farmed.
  - [verified config] Enemy drop tables hold no gems or obsidians.
  - [inferred] One e2 arena emerald generator has a respawn-like field of 50 (I-12).
  - *R0 (I-12; R0.3a §8, §9.1, rz-b2):*
    - That 50 is `critterRange`, which the spawn budget doesn't use.
    - Broken geodes' gems don't come back after exit-and-return hops [verified xemu, placed]. Across a save and a death was not tested.
    - d2's three unsaved single-gem generators may respawn on each visit [inferred]. That is a lead.
  - A source proven farmable gets `farmable = true`. Its items then count once, and logic never relies on farming it.
- **Per-node aggregation.**
  - When a node becomes safe, all of its unconditional locations are collected in one step. Per-node, per-item totals are precomputed when the database loads.
  - Conditional locations (inside barriers or geodes, behind events, behind thresholds) are re-checked only when a flag **or counter** they reference changes.

### 2.9 Discs, the 4th fragment, seals, and no-return regions

**What the engine does** [inferred, strong; (private evidence) §2]:
- Each guardian level (a6, w3, f6, e5, life) has:
  - a fragment-count `gameState`;
  - a `<Elem>DiskPlaced` latch, which also appears in town;
  - an exit to town at the disc's spot;
  - a generator that spawns the vanilla 4th fragment after the boss. In life, `LifeFrag4_generator` spawns it.
- When the count reaches 4 in that level, the chain fires the exit. So a disc completed in any other level doesn't teleport.
- Open hazards, all part of I-7:
  - entering the guardian level already holding 4 of that disc may fire the chain at once;
  - the player may or may not be able to re-enter afterwards;
  - the chain may be *level-triggered* (it fires on any entry while 4 are held) or *edge-triggered* (it fires only on the 3→4 pickup).

**R0 corrections (2026-10-11; thresholds §5, wiring §9.4, rz-b1, rz-b2):**
- **Where the count chain is.** In **a6, w3, f6 and e5** it is count ≥ 4 AND that disc not placed, then a teleport to town [verified data].
  - **w1 has one too:** `BossDefeated` is water ≥ 4 AND a touch of `Water_Tube:Link:Public_PushShape` [verified data]: with 4 a touch loads town, and with 3 nothing happens [verified xemu, placed]. It has no placed check [verified data], so it fires on every such touch [inferred]. It doesn't set `WaterRealm_fixed`.
  - **life has none.** Its two exits to town need the beam puzzle and a touch, and `life_disk_placed` only chooses the movie [verified data].
  - So the list above and the no-return and forfeitable model for w1 and life change. 4.10c-iii re-derives them.
- **The 4th fragments.** The 4th air and fire fragments spawn from `characters.xbr` graphs 16 and 21, not from the a6 and f6 level generators, which are dead [verified data].
- **I-7 (a), (d), (e) are answered** for a6 [verified xemu, placed].
  - Entering with 4 fragments while the disc is not placed teleports the player to town 4 s later. The chain is **level-triggered**: it is live from the first tick.
  - Once the disc is placed, re-entry is safe.
  - e5's chain fires as a6's does: 4 earth fragments with the disc not placed teleport the player to town [verified xemu, placed; rz-b2 poked the count to 4 in the level]. Re-entry after placement was not run there, so e5's (d) is [inferred from data].
  - w3 and f6 have the same wiring [verified data; in game inferred]. (c) stays the owner's; (b) is answered from data (no other level wires a 4th fragment to a teleport); (f) waits for R2.11.
- **Life's exit is the touch, not the count** (Step R1.8n, D197; sitting r18n) [verified xemu, placed: the top switches and the 20 core
  switches latched]. The beam exits fire on a touch of `ToTownFieldShape` (after the level's first 0.67 s, `timer43`) while `BeamToggle`
  is on (the filament cores won); `LifeDiskReplaced_latch` only picks which of the two switches fires [verified data]. Life's
  fragment count drives only `LifeRealm_fixed_latch`, whose one output moves a dummy transform (`LatchHack`) [verified data].
  - With 4, 3 and 0 life fragments held and the disc not placed (kit 0, the warp in by real input), no count chain fired in 600
    ticks at the arrival, and a walk onto the beam's axis from the lowered pad after the cores' win took the player to town each
    time, without the fourth fragment (the counts unchanged).
  - So a later setting may move life's 4th fragment: the exit doesn't need it. Whatever lies at `life/g0/r259` is taken only by
    a drop into the beam from the crown deck (R1.8j and r18n: taken from the deck, not from the lowered pad in six tries), and
    the exit fires either way.

**Seals.** The seals read a disc's fragment count against a constant held in node data [verified names; thresholds not decoded].
- They are `DiscTrigga_Life` in a1, w1, town and f6, d1's `DiscSeals` and e5's `Seal`.
- That makes the owner's `discw3` the engine's own model.
- I-16 finds the thresholds, by owner knowledge or xemu, or exactly through I-1. They then become edge requirements.
- *R0 (I-16 answered; thresholds §2, rz-b1):*
  - Each realm seal opens on a touch while the player holds at least 3 of its disc; with 2 it shows a help popup. That covers a1, w1, town, f6 and e5.
  - d1's death seal needs a touch and at least 4 of each of the five discs.
  - The constants are link-curve keys, and the seal toggles are saved [verified data; w1 verified xemu, placed].
  - Town's seal is what gates the town → life exit.

**The no-return region** is every node whose only way out is the disc teleport.
- In vanilla these are the guardian arenas and slots (the owner: "usually in one-way spots").
- Which areas really are no-return is I-7(c), answered from owner knowledge.

**Option A, restrict placement (the owner's choice; v1):**

1. **Pre-fill.** Each guardian slot keeps its **vanilla 4th fragment** (RQ-4).
   - That means no write at those 5 slots, and the 4th fragment is always collected there.
   - A random choice of the disc's 4 fragments is a later setting; it needs I-7(f).
   - The other 3 fragments of each disc (15 in all) join the main pool. The main fill never touches the pre-filled slots.
2. **Gate (derived, never authored).** A region node is safe only when S holds 3 of that disc and the local closure from the region's entry can reach and collect the slot (§2.13).
   - On the way, the closure must meet the boss, the barriers and the buttons.
   - So the effective gate is `disc<X> >= 3 & <whatever that closure needs>`. It is computed, not written by hand, and the spoiler prints it.
   - Where a physical seal enforces the disc count (I-16), the first half is physical. Everything else is logic only, so entering early is a *trap* that the per-seed trap gate checks (§2.13).
   - Example: a6's guardian needs level 3 in all four elements in today's database [verified DB]. A player who enters with 3 air fragments but without those powers is stuck. Exhaustive play reached that dead state in 17 of 20 seeds [verified DB, `review-logic`].
3. **Escape: a one-shot teleport.** Reaching the slot with its requirements met while `disc<X>` = 3 counts as reaching the start. After the slot is collected, the region has no escape:
   - every other location in the region is **forfeitable**. It holds no progression item and no obsidian; like an excluded location, it takes only useful items or filler. It sits outside the `full` guarantee, and the spoiler marks it "collect before the fragment";
   - the region's entry edges go into the spoiler's danger list as **traps after completion**.
4. **What I-7(e) changes:**
   - **Level-triggered:** re-entering the guardian level after completion teleports at once, so the whole level is lost. All its non-slot locations become forfeitable, and no edge through it may be needed afterwards.
     - *R0:* the chain is level-triggered, but it also tests that the disc is not placed, and town sets that flag after the teleport. So re-entry after completion is safe, and the level is not lost: verified for a6 [xemu, placed], and the same by the data for e5, w3 and f6 [inferred from data] (e5's chain itself fires in xemu as a6's does).
     - Those levels hold about 33 non-gem, non-slot locations, plus their consumables [inferred from census per-level counts]. That is more than the 32 useful and filler items that RQ-3's default puts on non-gem locations.
     - In that case, forfeitable non-gem locations take single gems, and the same number of obsidians move onto plain gem spots in safe nodes. This is the only case where the default puts a progression item on a gem spot.
   - **Edge-triggered:** re-entry is a softlock, and the region's entry edges are traps after completion.
5. **Cost.** 5 slots are fixed and the forfeitable locations are restricted. No RE or game patch is needed, and it matches vanilla's own structure.

**Option B, teleport-on-pickup patch (the ADVICE's idea).** Fire the town teleport when an item is picked up at chosen locations, whatever the item is.

| | A: restrict placement | B: teleport patch |
|---|---|---|
| RE needed | none for v1; I-16 makes the gate exact | the levelSwitch activate handler (factory near 0x72422) for a shim on the pickup path, or node-section **writes** to add `gameState → combiner → levelSwitch` chains [verified: neither exists] |
| xemu proof | I-7(a, c–e) | a new shim must boot and pass the 5-minute checklist; a mid-frame level request is not known to be safe [(private evidence) §2] |
| Pool freedom | 5 slots fixed; forfeitable locations restricted | any item anywhere |
| Out-of-logic safety | unchanged | the patched slots become safe whatever the player holds |
| Composability | logic only | a shim layer that must compose with mods (AZ-001 carve rules) |
| When | v1 | R2.1, with the general safety net |

**Recommendation:** use A for v1, and plan B as part of R2.1 (§7). Once R2.1 lands, the gate can relax to a setting.

### 2.10 The minecart

**What is known** [verified names, (private evidence) §8]:
- ~~the ride rig is in e2 (`MineCarRide2`, with `Nonresettoggle` and `Topcartoggle1/2`);~~ *R0: `MineCarRide2` is a ride inside e2 (below);*
- e5 has a `MineCarToggle`;
- e2 and e5 are joined by two exit pairs.

**Not known:**
- how e5 learns where the cart is (no shared latch name was found);
- which exit pair is the ride;
- whether any other edge depends on the cart's side, such as a `cardoortoggle` door, a `Topcartoggle` or the second exit pair.

**R0 (2026-10-11; wiring §7, thresholds §12.2, rz-b2 I-10):**
- **Two gondola pairs cross levels**, and both start in e2 [verified data]:
  - `MineCar`: e2's exit `SwitchE5a` ↔ e5's `levelSwitch2`. It keeps the lock id `minecart_e2e5`.
  - `MineCar2`: e2's exit `SwitchE5a1` ↔ **e7**'s `E7_E2_switch`. It gets a new lock id, `minecart_e2e7` (a plan change). It is e7's only entry.
- **`MineCarRide2` is a ride inside e2.** It carries the player to the ice cave's generator room with no level load [verified data; verified xemu, placed].
- **The state** is e2's saved `DownToggle` and `DownToggle1` and e5's saved `MineCarToggle`. e7's arrival elevator is not saved. No latch, `gameState` or link crosses levels [verified data].
- **The circuitboard gate.** Both e2 gondolas are held until both `key_circuitboard` locks are in. With `Topcartoggle1` forced to 0, the ride ends in a `DeathFieldShape` [verified xemu, placed, for `MineCar`]. So both e2 cart edges carry `button:e2.earth_keylock & button:e2.earth_keylock1`; the `db-draft` drafts already do.
- **The ride.** `SwitchE5a` fires 3.0 s after the bucket is touched [verified xemu]. Riding back by gondola brings the e2 bucket home [verified xemu, placed].
- **The side bit is a hazard.** While the e2 bucket is on the e5 side (`DownToggle` 1), e2's dock is a lethal `DeathFieldShape` drop [verified xemu, placed].
- **A cross-level dependency.** e5's two `key_fuse` locks set the global `conveyor_on`, which starts e2's conveyors [verified data].
- **For the owner** (Q255 drafts; rz-b2 §4a): these are route questions.
  - Is the e2 → e5 gondola edge gone while the bucket is away?
  - Does the walk-through pair (`E2_E5` ↔ `E5_E2`) work with the bucket home, and in the e2 → e5 direction? Only e5 → e2 with the bucket away was run.
  - `MineCar2` was not ridden.

**The full model, for room randomization later.** The cart is a lock token held by one of two levels. Following OoTR's age model, the search graph becomes (node × cart side):
- a cart edge needs the cart on its side, and moves it across;
- every other edge keeps the cart where it is.

Reachability over that product graph still only grows as items are added, so assumed fill stays valid [inferred, prior-art recommendation 4]. The anchor is the start's component in the product graph, (w1_beach, vanilla side), not town_central on either side.

**v1:**
1. Cart edges always stay in the **physical** graph (`R_phys`, §2.13) with `logic = false`, because a player can ride them anyway.
2. They leave logic only if two things hold:
   - I-10 shows that no non-cart edge depends on the cart's side;
   - the vanilla-route check (§4.3) passes without them.
3. Otherwise, add the one-bit product state above. It roughly doubles the nodes of e2 and e5 only, which is cheap.

Either way, the schema carries `kind = "cart"` and `lock = "minecart_e2e5"` from day one.

### 2.11 Fuel

- **[verified config]**
  - Fuel starts at 50 with a cap of 50.
  - Every new game and every load sets all four fuels to 50 [verified static].
  - Casts cost fuel:

    | Use | Cost |
    |---|---|
    | armor | 3/4/6 |
    | air shield | 2/3/4 (for 1/2/5 flaps) |
    | each staff hit | 1 |
    | chromatic attack | 40/60/80 |
- **[inferred]** Each 100 gems of the matching type adds 33 to the cap, at most 3 times. Only the config values are verified; the formula is not (I-11, §7).
- **[unverified]** Which gem feeds which element lives in code. The owner's pairing is the working assumption: emerald→earth, diamond→air, sapphire→water, ruby→fire.
- **v1:** fuel is not a logic gate [inferred: with 50 fuel and a refill on every load, only long multi-cast routes and the chromatic attack are bound by fuel].
  - An edge may carry a `casts` hint, such as an air-shield route that needs 3 casts.
  - Fuel tiers in logic come after v1 (I-11).
  - Gem totals are preserved (§5.4), so all three upgrades stay available.

### 2.12 Dark levels (nolight)

- **The dark areas** [verified names] are e7's dark room (with torches and an obsidian) and w1's dark room (which holds an obsidian).
- **How light works:**
  - casting fire alone gives light for 5/10/20 s at fire levels 1/2/3 [verified config];
  - each cast costs 3/4/6 fire fuel.
- **Modelling** follows ALttP's `DarkRoomLogic` [verified, AP `worlds/alttp/Options.py`]:
  - nodes and edges marked `dark = true` need `fire>=1` at least. ~~Under the easy preset, authored "long" dark routes need `fire>=2`;~~ A dark edge needs `fire>=dark_fire` (a user option, 1–3, default 1; D144);
  - a dark edge's clause is `fire>=<its dark fire> | skip:<that area's nolight skip>`: the light requirement is dropped when the settings turn that skip on (`w1.dark_cave_nolight`, standard; `e7.dark_room_nolight`, hard; D113).
- ~~**Still open:** whether the rooms can be completed without light (I-14, by owner knowledge or xemu).~~ *Answered in the data:* each room's no-light way is its `nolight` skip, `w1.dark_cave_nolight` and `e7.dark_room_nolight`, both in logic and confirmed (D114), and with them off a dark node needs `fire>=dark_fire` (`docs/RANDOMIZER_DB.md` §7.1).
- *R0 (I-14 partly; rz-b1, rz-b2):*
  - Light gates no game logic in w1 or e7. Each dark room's nearest obsidian was picked up at fire level 0 [verified xemu, placed], and e7 has no `gameState` at all [verified data].
  - Light lasts 5, 10 or 20 s at fire 1, 2 or 3 [verified xemu, placed].
  - The routes and timings stay the owner's. So does whether w1's `W1_Town` exit is in the dark cave or by the beach (rz-b1 §4a).

### 2.13 Escape logic (exits only)

The owner's answer is that the player leaves a level only through exits, with no death warp and no save-quit to town. So **entering a region you can't leave is a softlock, whatever the region holds** (ADVICE). Today's database already has 7 edges into nodes that can't be left with the entry items [verified, AUDIT §2.2], for example `f2_core → f4_lava_river`.

**Definitions:**
- **`R(S, F)`** is forward reach from `w1_beach` over edges whose `requires`, `through` and `assumes` hold under items S and credited flags F.
  - Flags are credited in a valid play order, so R is sound for forward movement.
- **`escape(n, S)`** is a *local closure* from node n.
  1. It starts with S's items and only two kinds of flag:
     - the flags **forced on entry** to n: those that every usable in-edge of n requires, with no alternative;
     - the `assumes` flags of n's in-edges.
  2. It searches forward from n. At each node it reaches, it collects the not-yet-collected locations there, and it sets the flags and events whose requirements hold. Then it continues.
  3. `escape(n, S)` holds if the closure reaches `w1_beach`, or reaches a no-return slot whose requirements hold while that disc's count is exactly 3 (the one-shot teleport, §2.9).
- **`Safe(S, F)`** = {n ∈ R(S, F) : escape(n, S)}.
- **`R_phys(S)`** is forward reach over the **physical** graph. That includes `logic = false` edges such as cart rides, ignores `assumes` and derived gates, and allows the skips the settings turn on.

**Rules:**
1. **The anchor is the start, `w1_beach`, not the hub.** town_central joins the start's component once the beach↔town edges open. From then on, "back to the start" and "back to town" are the same test.
   - Anchoring on the hub would leave the start region unsafe before town is reachable. Vanilla would then be unbeatable: today's database gave 0 spheres and 0 of 60 solvable seeds beaten [verified DB, `review-logic` CE1].
   - A load check requires that, with all items, `w1_beach` and `town_central` reach each other.
2. **Items and flags found inside a region count toward its own escape** (the local closure).
   - During fill an empty location adds nothing, so no location is escapable only because of the item placed there. That keeps VARIA's guarantee.
   - It also allows vanilla's a6 route, whose third earth power sits inside a6. Without local items, vanilla stops at 34 items; with them, it is beatable at 37 [verified DB].
3. **Flags credited elsewhere don't count toward escape** unless they are forced on entry or assumed.
   - Otherwise a drop whose way back needs a lever on the far side would be marked safe as soon as the lever *can* be pulled. Exhaustive play reaches a dead state there [verified toy, CE2].
   - An edge may declare `assumes = ["flag:…"]` to accept a vanilla "pull the lever, then drop" design. Such an edge is in logic only once the flag is credited. The far side's escape starts with the flag, and the edge goes into the spoiler's danger list.
   - A button in another room of the same pit is still found by the closure [verified toy, CE5].
4. **Only safe nodes give items, flags or events. Terminal events (victory) need reach only**, because the game ends. Otherwise a one-way final arena could never be beaten [verified toy, CE6].
5. **A no-return region is safe only through its one-shot teleport** (§2.9).

**The algorithm** is a least fixpoint:

```
S := starting items;  F := {}
repeat
  R    := forward reach from w1_beach under S ∪ F
  Safe := {n ∈ R : escape(n, S)}
  at each n ∈ Safe: collect its open locations; credit its flags and events whose requirement holds
  at each n ∈ R:    credit terminal events (victory) whose requirement holds
until nothing changes
```

**Cost.** A naive version runs one closure per node per sphere.
- On a synthetic 600-node, ~3.2k-edge graph, one forward plus backward BFS takes 0.4 ms. A naive per-node closure adds 11 s, 53 s or 209 s with 10, 50 or 200 nodes that can't yet get back [verified bench, `review-feasibility` `bench.py`].
- **Fast path.** First run a backward search from `w1_beach` under S. In it, an edge is passable on items, forced flags and flags settable at its own source node: destroying a barrier from that side, or pressing a button there. Nodes it finds are safe without a closure.
- Only the remaining nodes in R get the full closure. It runs on the graph's strongly connected component (SCC) DAG and is cached by (SCC, item counters).
- 4.10c-iii measures the cost (§3.8).

**What this guarantees, and what it doesn't:**
- **Guaranteed:** every seed is beatable. Every location except the forfeitable ones is reachable and escapable for a player who collects in sphere order.
- **Not guaranteed:** a player who takes a one-way edge before holding what the far side needs can softlock. One-way edges include drops, one-way doors, the airship and guardian arenas. The randomizer can't prevent that; the opt-in save warp (R2.1, D202) is the safety net, out of logic.
- **Evidence** [verified DB, `review-logic`, on today's crude 43-node `logic_db.json`; its game accuracy is unverified]:
  - with every fix in this section, 60 of 60 seeds are beatable;
  - exhaustive play still finds a reachable dead state in 19 of 20 seeds: a6 in 17 and `f4_lava_river` in 12;
  - checking only at sphere states flags 7 of those 19;
  - vanilla itself has dead states at `f4_lava_river`. There, the edge `f2_core → f4_lava_river` needs air 2, and the only exit needs air 2 plus water 2.
  - Exhaustive play explored 64k–261k states per seed on 43 nodes, so it won't scale to 300–600 nodes.

**Mitigations:**
- **The per-seed trap gate.** For each sphere state S_k, `trap_k := R_phys(S_k) \ Safe(S_k)`.
  - The seed is retried if any trap is entered by a trick-free edge and is not on the owner-signed `known_traps` list. That list holds vanilla's own traps (for example `f4_lava_river`, if the game agrees) and the traps after completion (§2.9).
  - 4.10e-ii measures the retry rate. If it is high, RQ-11 chooses between a warning only and a fill rule that orders a trap's entry items after its escape items [proposal, unmeasured].
  - *Built (Step R1.12, 2026-10-13):* the fill's verify (RANDOMIZER_DB §15). "Entered by a trick-free edge" is read as a trap a player gets into with no skip at all, and vanilla's own traps are computed, every trap of the vanilla placement under the same options or the defaults (defaults taken under D115); the level files' `known_traps` stay for the owner's signatures (none yet). Its retry rate on seeds 0-50 [verified, (private evidence)]: 0.7 % of attempts under the default options and 82.6 % under the max options (ceiling 4, `frame_perfect`; every seed still fills within 20 attempts), mostly w2's pool zones when `power_water` lands outside w2. D83(b)'s re-roll stands; RQ-11's fill rule would cut max's rate.
- **The spoiler** lists, per sphere:
  - every trap, ranked like Randovania's `POINT_OF_NO_RETURN`;
  - every `assumes` edge;
  - the traps after completion;
  - the forfeitable locations.
- **The help text** tells players to keep a save from before one-way drops. The load list holds several saves [verified, (private evidence) §1].
- **The cron soak** adds a sampled explorer. It plays like a player, with random legal moves and pickups, and reports dead-state rates per settings profile (Q293; *was:* per preset).
- **R2.1** adds the real safety net: it landed as the opt-in pack `qol_save_warp` (Step R2.1a, D202), out of logic. Until its open checks pass (Step R2.1b), no settings claim to be softlock-free (RQ-8; D144, *was:* no preset).

### 2.14 Save points and saveanywhere

- **There are 43 designated save points in 22 levels** [verified ids]. f2 reuses the id `F1_2`, which f1 also uses.
- **A save stores** [verified static]:
  - the level, the player's position, and the save point's node name;
  - the inventory, the magic levels, the shared flags, and each visited level's state.
- **On load the player is back at the save platform** [verified static, R2.1a]: the save holds the platform's place, and a continue points the arrival at it (0x53487).
- **There are several saves**, not one fixed slot: the load screen has `newgame`, `delete` and `toomany` [verified strings]. Whether saving overwrites the loaded save, and whether death reloads the last save, are I-6.
- **Hazard (ADVICE):** a save point inside a region that can't be left, plus a save overwritten there, is unrecoverable.
  - In-order play never enters such a region (§2.13).
  - The spoiler lists every save point in `R_phys \ Safe` at some sphere state, and every save point where the soak's explorer found a dead state.
  - The duplicate `F1_2` id is checked in I-6. The save stores the level path plus the node name, so a clash is unlikely [inferred].
- *R0 (I-6 partly; rz-a):*
  - A death (HP 0, then gameover, then Continue) reloads the last save and reverts the current level [verified xemu, placed].
  - A new character's first save adds a save slot, and its next save overwrites that slot.
  - `W1_2`'s save point drops the player into water.
  - Not measured: the `toomany` cap and f1's and f2's shared `F1_2`.
  - *Step R1.26 (static):* a death reverts every level visited since the save: it deletes `z:\scratch\levels` and Continue reads the slot ([`RE_DATA.md`](../RE_DATA.md) § "Live pickups"). Seen in xemu by R1.26's sitting: a fragment taken in f4 after a save in w1 was back untaken after a death and Continue.
- **`saveanywhere`** is a trick family (D113). The owner's notes call it a sub-trick of `pstorage`; whether it stays one is the owner's open question.
  - Its skips are manual, and no setting turns one on in v1 (D144, Q294; *was:* "outside every preset"). ~~Turning one on is the player's own setting, and the spoiler prints a warning~~ A separate opt-in with the spoiler's warning is v2 (Q294; the ADVICE's "a difficulty flag with a warning, not a plain toggle").
  - It never counts as an escape. It only enables the edges whose clauses name its skips.
  - *2026-10-12:* "saving doesn't move you" is contradicted by (the randomizer plan's private evidence) §2: a reload starts the body 1.0 m higher, so repeated save and reload cycles in water may rise through a ceiling [video; inferred match with the RE].

### 2.15 Tricks, skips and difficulty

- **D113 (owner, 2026-10-12):** "i wouldnt rank tricks by difficulty, but rather specific skips." Difficulty belongs to each specific skip, not to a trick. This refines D108's answer to Q256 (below).
- **A trick is a technique family:** `bskip`, `pstorage`, `saveanywhere`, `rjump`, `tjump`, `itrig` and `nolight`, and since D120 (owner, 2026-10-12) `elevbounce` (elevator bounce), `iceclimb`, `ledgepop`, `elevjump` (lift jump), `botstep` and `flipcancel`, each its own family whose skips still need confirming (D114). It has no tier and no default tier. It names and groups skips, and the spoiler uses it to explain them.
- **A skip is a named, located use** of one or more tricks: the Torpedo Skip (`w1.torpedo_skip`), the w1 fire wall with air 2 (`w1.firewall01_air2_beach_town`), the d1 spires (`d1.spires`), and so on. It carries its own difficulty, the tricks it uses, its requirements (`requires`), a status, its confidence and its evidence. A clause names `skip:<id>` (§2.2).

  | Difficulty | Name |
  |---|---|
  | 1 | safe |
  | 2 | standard |
  | 3 | hard |
  | 4 | frame-perfect |

- **Settings:** a skip difficulty ceiling (0 = none) turns on every skip rated at or below it, and a per-skip toggle wins over the ceiling. A held skip is never on. `saveanywhere` skips are manual, and no setting turns one on in v1 (D144). These settings were the agent's default [inferred] (D113); since D144 (owner) they are the user's own options (below).
- **D144 (owner, 2026-10-12): no presets; the player sets the options.** Verbatim: "what if we get rid of presets, and just have skip and movement options that the user sets themselves? With the default being no skips and hard movement." The follow-up answers: dark areas default to "Fire 1"; "Yes, user-saved settings". It supersedes the preset tables of D113, D118, D129 and D142 (the randomizer plan's private evidence `1e11583` replaced `db-draft/presets/` with one settings spec and its defaults, (private evidence) §7).

  | Option | Values | Default |
  |---|---|---|
  | `skip_ceiling` | 0 none, 1 safe, 2 standard, 3 hard, 4 frame-perfect (D259: no skip is rated 1) | **0** |
  | per-skip toggles (`[skip_override]`) | skip id → on or off | none |
  | `movement_tier` | `safe`, `standard`, `hard`, `frame_perfect` (D108's envelope tiers) | **`hard`** |
  | `dark_fire` | 1, 2, 3: the fire level a dark area needs (§2.12) | **1** |

  - **Which skips are on.** A skip is on when it is in logic (so confirmed, D114) and either its toggle says on, or it has no toggle and its difficulty is at or below the ceiling. A toggle wins over the ceiling, but **a toggle never turns on a held or manual skip**; no manual skip is offered in v1 (Q294).
  - **`dark_fire`** applies to every dark area, and an enabled nolight skip lifts it for its own dark area only (§2.12).
  - **User-saved settings.** The GUI and the CLI save the chosen options to a small settings file, with every option written, and to a **share string**, its one-line text form; each seed's spoiler and build report records both (§3.6, §5.5). The database ships one settings file, `settings/defaults.toml`, holding D144's defaults.
  - **Counts.** With no toggles, ceilings 0, 1, 2, 3 and 4 turn on 0, 7, 10, 17 and 18 of today's skips [verified 2026-10-12: (the randomizer plan's private evidence) `db-draft/check.json`, unchanged since `1e11583`, `compat_presets_d142` at ceilings 0–4].
  - **Test profiles, not presets.** The plan goldens and the soak use three fixed settings: strict (ceiling 0, `safe`, `dark_fire` 2), default (0, `standard`, 1; D186, was `hard`) and max (4, `frame_perfect`, 1), plus seed-drawn settings in the soak (Q293).
- ~~**Presets** answer the owner's "difficulty scale":~~ *Retired by D144 (2026-10-12); kept as history (after D142 had re-cut these presets in (the randomizer plan's private evidence) `c05c912`, which this table never took):*

  | ~~Preset~~ | ~~Skips~~ | ~~Movement tier (D129)~~ | ~~Lenient knobs~~ |
  |---|---|---|---|
  | ~~Glitchless (D118)~~ | ~~none (ceiling 0, no toggles)~~ | ~~safe~~ | ~~dark routes need fire 2~~ |
  | ~~Easy~~ | ~~ceiling 0 (none)~~ | ~~safe~~ | ~~dark routes need fire 2~~ |
  | ~~Normal (default)~~ | ~~ceiling 1: every safe-rated skip, the six `pstorage` gate skips included (D118; *was:* with the `pstorage` skips off)~~ | ~~safe~~ | ~~dark routes need fire 1~~ |
  | ~~Hard~~ | ~~ceiling 3~~ | ~~hard~~ | |
  | ~~Expert~~ | ~~ceiling 4~~ | ~~frame-perfect~~ | |

  *D118 and D129 (owner, 2026-10-12; superseded by D144):* Normal turns on all safe skips, a new Glitchless preset has no skips at all, and each preset names its movement tier: safe for Glitchless, Easy and Normal, hard for Hard, frame-perfect for Expert. Glitchless and Easy turn on the same skips today (none); how Easy differs from Glitchless beyond its name is still open [inferred: (the randomizer plan's private evidence) `ac23bbd` gives both the same knobs]. *Moot: D144 retired the presets (`planner/settings.py`: "There are no presets").*

- **Invariant:** turning a skip on or raising the ceiling never shrinks R or Safe (§3.7) [verified toy, `review-logic`]: a skip's atom only ever appears un-negated.
- **D114 (owner, 2026-10-12):** "roll jumps do buffer, you can press the next roll jump before the previous finishes, and press the jump button before a roll jump finishes to buffer it. for unconfirmed tricks, like air 1 skipping the fire barrier, we need to confirm they work before introducing them in our logic."
  - **A skip enters logic only once it is confirmed:** reproduced in xemu with exactly the kit its `requires` encodes, or confirmed by the owner. Computed, commentary-only and inferred skips stay held. Skips seen performed in a speedrun video are strong candidates and come first in the reproduction sittings, but they stay out of logic until reproduced or confirmed, because the kit read from a video can be wrong [the agent's reading of "confirm they work"].
  - **Roll jumps buffer** [owner]: the next roll and the jump can both be pressed before the roll ends, with the button held (owner, 2026-10-12: "yes you have to hold the roll or jump button also"). This matches the static reading. The caveat "if the buffer fails, every roll jump is frame-perfect" is dropped. xemu still measures the buffer window, to rate each skip.
  - Plain derived movement edges (jumps and flaps inside the measured envelope) are not skips: they stay D108/Q255's reviewed drafts.
- **D145 (owner, 2026-10-12): a time-saver is not a skip.** Verbatim: "keep in mind some of the tricks you saw in the speedrun video are not skips, bur rather just meant to save time."
  - **A skip changes reach for its kit:** with its `requires` and at a movement tier it reaches a location, zone, item, exit or event that plain movement with the same kit doesn't, or it bypasses a requirement (a gate, key, power, switch or event). Only skips enter logic (D113, D114), count at a skip ceiling and get a per-skip toggle (D144).
  - **A time-saver doesn't:** it goes where plain movement with the same kit already goes, only faster (`e6_core` → `e6_core`, a drop in place of a ladder, a fall in place of an elevator). It gets no logic edge, no toggle and no ceiling count, and owes no xemu confirmation for logic; it is kept as a note the spoiler and the route may cite (a later "fastest route" feature may use it).
  - *Per tier* [inferred, the agent's reading]: a trick whose reach equals plain movement's at the default tier (hard then; standard since D186) but not at a lower one (safe) is still a skip for the lower tiers.
  - *Where it lands (planned):* the randomizer plan's private evidence's `tricks/tricks.toml` gets a `[[time_saver]]` table, out of the skip list, with `tricks_check`, FORMAT §5/§7 and the skip counts following; the running roll-jump sittings sit only real skips; Modkit's format (`docs/RANDOMIZER_DB.md` §12) and its imported `tricks.toml` follow at Step R1.4b (REORG §10.2a). Until then the skip counts in this section (and `rando check`'s 0, 7, 10, 17, 18 at each ceiling) still count any time-saver as a skip, and may fall [inferred]. *Recorded 2026-10-12 by Step R1.4m (REORG §1's D145).*
- **The R0 drafts** (the randomizer plan's private evidence at `603d763`, 2026-10-12): 7 families and 75 skips. 5 are in logic, all confirmed by the owner (`w1.firewall01_air2_beach_town`, `w1.torpedo_skip`, `e6.tree_song_skip`, `w1.dark_cave_nolight`, `e7.dark_room_nolight`); 70 are held (37 of them seen on video, which the sittings take first), and 6 are unrated. The presets turn on 0, 0, 5 and 5 skips [verified 2026-10-12: (private evidence) in (the randomizer plan's private evidence), 0 problems]. Before D114 the drafts had 46 in logic and the presets turned on 0, 7, 41 and 46. *Since (Step 2.22m, (the randomizer plan's private evidence) `ac23bbd`, after sittings skips-a to skips-h and D118, D120):* 13 families and 75 skips; 18 in logic (5 confirmed by the owner, 13 in xemu), 57 held, 6 unrated; the presets turn on 0, 0, 7, 17 and 18 (Glitchless, Easy, Normal, Hard, Expert) [verified 2026-10-12: `tricks_check.py`, 0 problems].
- **Difficulty for movement and skips (owner, 2026-10-11, D108's answer to Q256):** "Add difficulty settings for how frame perfect or hard movement or tricks are."
  - Both the movement envelope (§4.5) and the skips get difficulty ratings, as a randomizer setting: safe, standard, hard and frame-perfect.
  - Logic uses the rating the player picks.
  - ~~**The default is the safe tier.** That default is the agent's proposal [inferred].~~ *D144:* the movement tier defaults to hard, and the skip ceiling to 0 (above). *D186 (2026-10-13):* after R1.2b's recalibration the default tier is standard.
  - A movement tier sets the margin on every jump and flap edge: each derived edge carries its own difficulty, from its margin. The safe tier uses §4.5's human-safe envelope, and frame-perfect uses the full envelope. ~~Presets combine a movement tier with a skip ceiling.~~ *D144:* there are no presets; the player sets both.
  - ~~The names, the margins and how the presets map onto them are settled at 4.10e-ii.~~ *D144:* the names are `safe`, `standard`, `hard` and `frame_perfect` (the randomizer plan's private evidence `envelope/tiers.toml`), and R1.2 ports their margins. The same invariant holds: a higher tier never shrinks R or Safe.
  - *Until D113 (2026-10-12)* each clause named `trick:<name>@<tier>`, with tiers 1–5 (beginner, intermediate, advanced, expert, ludicrous) and a maximum tier per trick in the settings.
  - The rest of D108: Q255 lets geometry-derived and xemu-probed edges into logic as labelled drafts, which the owner reviews one picture per level. Q257 lets community knowledge (speedrun routes, the obsidian list, documented skips) seed the logic and the vanilla route, tagged `[web, unverified]` until a probe or the owner confirms it. Q258 lets several agent xemu sandboxes run at once while the machine's load allows.

---

## 3. The solver

### 3.1 State and monotonicity

- **State** is (items as a `Counter`, flags as a set, and the cart side bit if it is modelled).
  - A `Counter` fixes AZ-160. Today's set inventory collapses duplicates across the whole inventory, and fragment-only fills deadlock in 30 of 30 seeds [verified, AUDIT §4].
- **Counters** are derived from items through the database's item→counter table.
- **Items and flags only grow**, with the exceptions in the table below. For each exception, one of three things must hold:
  - data proves it harmless;
  - it is modelled as a product bit;
  - it is kept out of logic.

  **Loading refuses a database that uses one without its declared handling.**

| Mechanism | Why it is not monotone | v1 handling |
|---|---|---|
| The one-shot disc teleport | the escape exists only until the slot is collected | §2.9: forfeitable locations; traps after completion |
| A guardian level lost after completion (if I-7(e) says level-triggered) | the whole level becomes unreachable | §2.9. *R0 (I-7(e)):* level-triggered, but safe after placement, so the level is not lost (§2.9 item 4). |
| Toggles: `ActionButton_toggle`, `OpenNCloseToggle`, `PersistantToggle1`, `Topcartoggle`, `cardoortoggle` [verified names]; levers other than `lever_1way` [inferred] | closing one path may open another, which breaks assumed fill | `mode = "toggle"`. A toggle whose "off" state gates an edge is a load error. I-8 presses each family twice. *R0: fire walls and crack blocks respawn; the `AirSwitch` latches; `UpperBridgeToggle` is a toggle (§2.4, §2.5).* |
| The key-slot cap (5 slots [inferred]) | holding more key types can make pickups impossible | if I-9 confirms the cap, keys stay vanilla in v1. *R0: confirmed; keys stay vanilla (§2.6).* |
| w4 `DayNight_gameState` [verified name] | a state that flips | I-19 decides: harmless, a product bit, or out of logic. *R0 (thresholds §8): the clock is the inventory's f32 at +0x000, and nothing it drives is saved, so for logic it is a wait, not a flag [inferred]; the owner confirms.* |
| The minecart | a lock token held by one level | §2.10. *R0: two locks, `minecart_e2e5` and `minecart_e2e7`.* |

### 3.2 Reachability

Reachability is the safe-reach fixpoint of §2.13, with:
- barrier passability: the destroyed flag, or a bypass in that direction;
- button, event and lock flags;
- threshold counters;
- skips filtered by the settings (the ceiling and the per-skip toggles).

Expressions are compiled once into closures over counter, flag and skip indices, so evaluation needs no string work.

### 3.3 Fill

**Item classes** (AP's classification):

| Class | Items | Count |
|---|---|---|
| progression | 12 elemental powers, 20 fragments, 39 keys (5 fragments pre-filled) | 71 |
| progression, counted | obsidians (AP marks such items `skip_balancing` + `deprioritized`, as for HK grubs and SM64 stars) | 100 |
| useful | power_life ×5, power_staff1/2, power_ammo (unless the vanilla-route check shows that one gates something, such as a `StaffUpgrade` latch) | 8 |
| filler | 1,146 single gems, 69 cluster payloads, 24 consumables | 1,239 |

**Location classes and the default rule (RQ-3).**
- The 203 non-gem items (71 + 100 + 8 + 24) go to the 203 non-gem locations: 79 majors, 100 obsidians and 24 consumables.
- Gem payloads go to gem locations. Single gems swap among single-gem locations, and each cluster keeps its type or swaps with a cluster of equal yield.
- `progression_on_gem_spots` (§5.4) can later let the 71 majors onto single-gem spots.

**Order of passes.** Each pass has its own named random stream (§3.5).

1. **Pre-fill**, the most restricted first (OoTR's dungeon and song pools; ALttP's `fill_dungeons_restrictive`):
   - the 5 guardian slots keep their vanilla 4th fragments (§2.9);
   - if I-9 confirms the key cap, the keys stay vanilla.
2. **Progression, by assumed fill.** "Items are always considered reachable until they are removed and placed" (AP `fill_restrictive`; OoTR).
   1. Shuffle the 66 remaining progression items.
   2. For each one, remove it from the assumed set and compute the safe set, assuming every *unplaced* item is held.
   3. Choose an empty location that is safe, allowed by its item rule, and neither excluded nor forfeitable. If none qualifies, raise `FillError`.
   - **Obsidians are interchangeable, so they are placed as one counted block.** The safe set changes only when the obsidian count crosses a lock threshold, so the fill searches once per threshold band, not once per obsidian.
3. **Useful items**, the same way, weighted toward major locations.
4. **Filler.** A plain random fill of the remaining locations within the class rules. There is no search, so it costs O(L).
5. **Verify.** A full independent solve of the result checks three things:
   - victory under the settings;
   - every non-forfeitable location is safe (`full`);
   - the per-seed trap gate (§2.13).

**On failure:**
- Retry with the next derived attempt seed, up to a cap of 20 (as in OoTR's entrance retry).
- Then fail with the reason (D35). Never fill the rest arbitrarily (AZ-161).

**Item rules** (AP's `item_rule`):
- gem locations take gem payloads only (RQ-3);
- a cluster location takes only a cluster payload of the same yield;
- excluded and forfeitable locations take no progression and no obsidian;
- each node graph has a new-string budget (§5.2), and the fill never exceeds it. *R0:* the budget is the zero gap after the graph's payload, used with the TOC size grown (path (b2)); ~~beyond +1,024 B it is [inferred] (§5.2)~~ *R1.10a:* the whole gap, rounded down to 4 [verified xemu, placed, to the gap's last byte] (§5.2);
- the guardian slots are pre-filled.

**Built (Step R1.9, 2026-10-13):** `azurik_mod/randomizer/planner/fill.py` (the fill, the streams and digests) and `plan.py` (the plan file and the minimal spoiler; RANDOMIZER_DB §7.4), `azurik-mod rando plan` and `rando spoiler`. The fill covers the authored levels; a stub keeps its vanilla items, out of the pool, which is the slice. It follows the passes above, verifies the result (victory and `full`; the trap gate since Step R1.12, §2.13) and checks it with the writer's `layout`. Defaults taken under D115:
- **Vaults (Q290):** every location an obsidian lock's force field closes (town's ten lock cages: sitting rz-c found the beam on all ten vault generators, so Q290's "5 vaults" is read as the ten) holds only `power_life`, `power_staff*` or `power_ammo`, or its own vanilla item (the two `key_obsidian` cages, keys being vanilla). The eight other cages hold exactly the eight useful items, so the useful pass fills them first, and no progression item or obsidian sits behind an obsidian lock.
- **Unbounded generators** (maxGenerated 0: town's infinite health and fuel dispensers) keep their vanilla item, since anything placed there would come back endlessly.
- **Lock 10 and full clears** (D81) are computed: a location gated by an obsidian lock whose threshold is the whole pool's supply of its counter (lock 10's 100) is excluded, with the `exclude` marks and the forfeitable locations.
- **Unsaved spots** (Step R1.37, AZ-467) are excluded too: a generator on no save list (the generated file's `saved`, the graph's list a load restores, 0x65E50) comes back from its record on every visit, so its item respawns [seen in xemu: f4's r1540]. Past the prefilled ones (town's dispensers, the guardian slots) they are the 12 all_fuel spots (a1 r2350, a3 r2599, a5 r1776, a6 r903, d1 r1624, e2 r4415, e5 r5069 and r5176, f1 r2017, f4 r1538, r1540 and r1542, all g0) and d2's three single gems (r3774, r3777, r3780), which take gems only; with the eight useful items in the vaults, the 12 hold filler. Before, every one of seeds 0-99's default plans put 7-12 obsidians or progression items on them (1,027 in all: 789 obsidians; 97 plans a fragment or power); since, none does, every one of those plans changed and all still fill (private evidence).
- **Obsidian bands:** the reach is computed once per band with the band's lowest count assumed (the largest threshold at or below the count left), and each copy of the band goes on a safe spot of it. That is a subset of each copy's exact reach, so the assumed fill's rule holds, slightly more strictly than per copy.
- **Useful items lean 3 to 1 toward major spots.** An item none of whose counters the logic reads never changes the reach (`Logic.reads`).
- **On the shipped data** (realm 1 authored, 35 spots proven by data) the fill succeeds on attempt 0 under the max options and fails all 20 attempts under the defaults: with nothing placed, the start reaches three non-gem spots before any progression item (w2's vanilla `power_water` and two obsidians), none proven, so no first progression item finds a spot. Proving one of them (R1.8's proven-spot sitting) can open the default. *Step R1.8b:* sitting r18 proved `w2/g0/r1364` in xemu; under the defaults seeds 1, 2 and x now fill and seed 0 still fails all 20 attempts. *Step R1.11b:* with the fire realm's nine spots too, seeds 0 and 2 fill and seed 1 fails all 20 attempts (the test's failing seed). The other two stay unproven: `power_water` sits behind the hose puzzle (a joystick-aimed hose puts out six fires that open its blocker), and the derive finds no element-free way to `w2/g0/r1357` in its logic profile. A check before the attempts was tried and dropped: an escape picks up placed items (§2.13 rule 2), so a reach with nothing placed can understate where the first item may lie.
- **20 attempts** in all; attempt k > 0 draws from `attempt<k>/<pass>`.

### 3.4 Skips and difficulty per edge

Difficulty is covered in §2.15. The solver receives the set of skips that are on and the movement tier, and compiles away the atoms of the skips that are off and the derived edges above the tier, so the same database serves every setting.

### 3.5 Determinism (D34) and seeds

- **Sub-seeds are named streams:**

  ```
  sub_seed(name) = first 8 bytes of sha256(seed ‖ name ‖ settings_digest)
  ```

  - The streams are `prefill`, `progression`, `useful`, `filler` and `attempt<k>`.
  - Turning one pool on or off no longer moves another pool's draws. Today it does [verified, AUDIT §1, §6].
  - The database digest is **not** an input to the streams. A small database edit then changes a plan only where reachability changed, and it doesn't reshuffle every draw.
- **Only `random.Random(int).random()` is used.** Our own `randbelow`, `shuffle`, `choice` and `weighted_choice` are built on top of it.
  - CPython guarantees only that `random()` gives the same sequence for the same seed across versions. "Most of the random module's algorithms … are subject to change" [verified, docs.python.org `random`, "Notes on Reproducibility", fetched 2026-10-10].
  - This keeps plans stable across CPython versions and Pyodide (W4).
- **Ordering.**
  - Every decision iterates over sorted ids, never over a set (the D34 pattern [verified, AUDIT §6]).
  - Ties are broken by id.
- **Seed input.** A user's seed string is turned into an int with sha256.
- **The plan file records:**
  - the generator version, the settings, the seed and the attempt index;
  - `db_digest`: the sha256 of the compiled, canonical database, without comments or display names;
  - the placement (location id → payload);
  - its own sha256.
- **Replay** with a different `db_digest` is refused.

### 3.6 Playthrough and spoiler

- **Spheres** come from the final placement (AP's `create_playthrough`):
  1. compute the spheres;
  2. cull each progression item whose removal still allows victory;
  3. raise "unbeatable" if victory fails (AP does the same).
- **For each progression location**, the spoiler gives an **obtain path and a return path** (Map Rando's spoiler style). That makes every check followable in xemu.
- **Also listed:**
  - for each sphere: the traps, the `assumes` edges and the traps after completion (§2.13);
  - the forfeitable locations ("collect before the fragment");
  - the save points that are dangerous (§2.14);
  - each no-return region's computed gate (§2.9);
  - the settings: the skip ceiling, the per-skip toggles and the movement tier, with a warning if a `saveanywhere` skip is on;
  - the skips the seed's logic used, grouped by trick family.
- **The spoiler is a pure function of the plan and the database.** It can always be regenerated and is never a second source of truth.
- *Built (Step R1.9):* the minimal spoiler, `rando spoiler`. Its spheres are the solver's rounds on the whole placement, not AP's iteration over the items collected so far: an escape may pick up placed items on its way back (§2.13 rule 2), so a spot can be safe because of what lies beyond it, which that iteration misses. Each progression item gets its obtain and return paths; the culling and the rest above are R1.12's.
- *Built (Step R1.12):* the full spoiler (RANDOMIZER_DB §7.4): the settings with the share string and the skip registry tag, the skips on by trick family, D82's statement, the spheres with every progression location's paths, then the traps ranked (new trick-free, known, skip-only) with their sphere spans, the `assumes` edges with the sphere their flags are credited in, the forfeitable locations, each no-return region with its slot's sphere and its traps after completion, the dangerous saves and the excluded locations. Defaults taken under D115: no culling (with `full` accessibility every location belongs to the seed, and P5 asks for every progression location's paths), and the skips listed are those on, not those a route needs.

### 3.7 Validation

All of these are in the pure tier unless marked. They are named by the behavior they pin (D10), and each one pins something the others don't.

| Test (proposed name) | Pins |
|---|---|
| `test_vanilla_placement_is_beatable_and_fully_accessible_without_tricks` | the database encodes vanilla (§4.3). With monotonicity, this also covers "every location is safe with all items and skips" and "an empty inventory reaches the first sphere". |
| `test_vanilla_route_replays_in_order[<realm>]` | the owner's recorded vanilla route. Each listed location is safe when reached, which catches logic that is too strict. |
| `test_adding_an_item_flag_or_skip_never_shrinks_the_safe_set` | monotonicity: a seeded loop, with no Hypothesis dependency |
| `test_start_region_is_safe_before_the_hub_is_reachable` | the anchor rule (§2.13 rule 1; CE1) |
| `test_a_drop_whose_way_back_needs_a_lever_on_the_far_side_is_not_safe` | local flags only (rule 3; CE2) |
| `test_guardian_region_is_in_logic_only_with_three_of_its_disc_and_the_boss_requirements` | the derived gate and the one-shot teleport (§2.9; CE3, CE8) |
| `test_committed_valid_plans_solve_and_invalid_plans_do_not` | `tests/rando/plans/{valid,invalid}/*.json`: hand-made placements with expected verdicts (Randovania's committed-seed pattern). It starts with the review's toy cases CE1–CE8 and grows from soak failures. |
| `test_requirement_parser_accepts_owner_shorthand_and_rejects_unknown_tokens` | the grammar and the fail-closed parser |
| `test_db_references_resolve_and_every_location_has_a_node` | data integrity |
| `test_loader_refuses_an_undeclared_non_monotone_mechanism` | §3.1 |
| `test_fill_succeeds_for_three_seeds_in_the_default_and_max_settings` | that the fill completes (≤ 10 s; the cron soak goes wider) |
| `test_plan_is_identical_across_processes_and_hash_seeds` | D34 (today's determinism test pattern [verified]) |
| `test_plan_hash_matches_golden_per_settings_profile` | a protected golden updated with `--update-goldens`: one sha256 per settings profile (strict, default and max; Q293), plus one full plan JSON for the default profile. It is first recorded at R1.12 (after 4.10d-v, now R1.11d). |
| `test_fresh_extract_matches_the_committed_generated_data` (vanilla tier) | the level-graph reader. If RQ-10 says generated data can't be committed, it checks the census counts against a facts file instead: 100 obsidians, 39 keys and 39 coded locks, 20 fragments, 77 geodes, 122 barrier groups, 74 exits, 43 save points [verified counts, census]. |
| `test_built_iso_reads_back_to_the_plan` (vanilla tier) | the M3 invariant: every location holds its planned payload |
| `test_recorded_plan_builds_to_its_golden_iso_hash` (vanilla tier) | a protected golden: seed 2 under the default settings, recorded from the first build that passes in xemu (RQ-6) |

**The soak** is a scheduled CI job: cron, never per PR, after Randovania's `daily-generate`. *In Modkit (R1.15; D109, D116):* `scripts/rando_soak.py` runs it locally; the cron job waits for AzurKit's public repo.
- It generates N seeds per settings profile (Q293), plus seeds whose settings are drawn from the seed, and runs the sampled explorer (§2.13).
- Failures are kept as artifacts. After triage, each one becomes a committed valid or invalid plan.

**Performance** is a step exit, not a pytest assertion (timing asserts are flaky on CI): 4.10c-iii and 4.10e-ii record a benchmark script's numbers (§3.8).

### 3.8 Performance

Measured so far:
- [verified, `bench.py`, synthetic] On 600 nodes and ~3.2k edges:
  - one forward plus backward BFS takes 0.4 ms;
  - 30 spheres × 180 placements take about 2 s;
  - a naive per-node escape closure adds 11 s, 53 s or 209 s for 10, 50 or 200 nodes that can't yet get back.

Estimated [inferred; measured in 4.10c-iii and 4.10e-ii]:
- **Database size:** N ≈ 300–600 nodes, E ≈ 1–2k edges, L = 1,418 locations.
- **Placements searched:** 66 progression items, about 11 obsidian bands and 8 useful items, so about 85.
- **Still to count:** the fast path and cached closures (§2.13), the playthrough cull, up to 20 retries, and Pyodide's slowdown.

**Exit target:** a default-settings plan, including verify, takes ≤ 10 s on CPython and ≤ 30 s in Pyodide.
- *Measured (Step R1.12, `scripts/rando_bench.py --runs 2`, two invocations at a load of 12.6-13.6 on 24 CPUs, the data at `a8a2f63`, 17 levels authored):* seed 42's default-settings plan, 11 attempts with their verifies and trap gate, the compile included, 4.1-4.9 s (the database's load, about 2.0 s, apart), since the step compiles each option set's graph once per `Logic` instead of per reach and leaves R_phys out of the fill's own reaches (no placement changes). One reach of the shipped database under the defaults: 150-192 ms. CPython met the target on R1.12's data; Pyodide is unmeasured. *Since then (Step R1.21b, 2026-10-24): 37.96 s and 26.79 s medians at a load of 71-84 on 24 CPUs, neither met nor refuted, so REORG_PLAN §10.2b's P2 is open until v1.1's quiet bench (D522).*

**Memory:** the web plan's 4.10 target is a randomizer build that peaks below 300 MiB [`WEB_TOOL_PLAN.md` §7, inferred target].
- The planner needs no game files.
- The writer streams one level at a time.

---

## 4. The data

### 4.1 Automatic vs hand-authored

*R0 (2026-10-11, D108):* §4.5 replaces the **hand** marks below for edges, `destroy_from` and barrier levels. Barrier levels come from each group's `magic` link curve (§2.4), and edges and `destroy_from` from the `tern` geometry drafts, which the owner reviews.

| Data | Source | Automatic? |
|---|---|---|
| Locations: level, graph, record index, debug name, payload, class, template (incl. `_move`), yield, cell, on load or triggered, name-ref offset | the census decoder, then the `core/xbr` level-graph reader (4.10a) | **auto** [verified decoder fields, `census.json` `_meta`; `gens.py`] |
| Geodes: variant, damage fourcc → elements, their 3 generators | decoder + config `magic` | **auto** |
| Barrier groups: kind, damage fourcc → elements, cell | decoder + config `magic` | **auto**. Which **edge** a barrier blocks is **hand**-authored (or comes from I-1's wiring). The 29 multi-shape groups get owner review. |
| Barrier level (1/2/3) and persistence | I-2, I-8 | auto once decoded, **hand** until then |
| Key locks: key type, level | decoder (the lock trigger's platform data) | **auto** [verified by pattern search; 4.10a decodes and pins the field] |
| Keylord systems ↔ keys | decoder (namespace) | **auto** [verified for w1 and e7] |
| Save points: id, level | decoder | **auto**. Their node comes from anchors. |
| Exits: source, destination, spot, shared-string group | decoder | **auto** (74 nodes, 51 strings [verified]) |
| Bosses, `gameState` watchers (the variables read), latches (persistent flag names), teleporters | decoder / string inventory | **auto** for names; thresholds come from I-16, by owner, xemu or I-1 |
| Item → counter table, item classes | config `critters_item_data` + this plan | **auto** + one hand table |
| **Node membership** of each location | the hand-authored `anchors` and overrides; `db-extract` assigns each location to the node of its nearest anchor, in memory, using the census's transform decode (`wm`) [verified, `census.py`] | **derived**: only `location id → node` is written; no coordinates |
| Logic nodes and their anchors, edges (gaps, jumps, flaps, one-way drops), `through`, bypasses, `destroy_from`, `assumes`, buttons → what they open and their mode, dark flags, skips (each with its difficulty), `casts` hints, `known_traps`, the vanilla route | owner knowledge, xemu, and the migration of `logic_db.json`'s 43 nodes and 92 connections [verified counts] | **hand** |
| Worst-case key counts (§2.6), no-return regions, forfeitable locations, escape summaries, the save-point danger list | computed by the database tool from the above | **derived** (generated and reviewed) |

**Owner effort.** The owner maps anchors, which number dozens per level, not locations.
- The locations per realm are town + water 415, air 197, fire 386, earth 264, and life + death 156 [verified, `perlvl.py`].
- `db-extract --explain <node>` lists a node's locations by name for review.
- The agent drafts the anchors, and the owner corrects them.

### 4.2 File format: one source of truth

```
azurik_mod/randomizer/data/          (AzurKit: azurkit/tools/randomizer/data/)
  generated/<level>.json     # from `azurkit rando db-extract --iso …`: ids, names, kinds, counts, offsets, location → node
  levels/<level>.toml        # hand-authored: nodes and anchors, edges, barriers (by id → group), buttons, events, skips (each with its difficulty), known_traps, vanilla route
  items.toml                 # item → counter table, classes, display names
  settings/defaults.toml     # the default options (D144): skip ceiling, toggles, movement tier, dark_fire
```

- **One source of truth for each fact.**
  - Generated facts are never copied into the hand files. A hand file *references* generated ids, such as `group = "FireWall_01"` or `locations = ["w1/g0/r123"]` (a placeholder id).
  - Any reference that doesn't resolve is a load error.
  - `db-extract` regenerates the generated files byte-identically. A vanilla-tier test checks that the committed generated files equal a fresh extract.
- **Why TOML for the hand files:**
  - it allows comments, which the owner needs for notes like "bskip from the beach side only";
  - it gives line-oriented diffs;
  - `tomllib` in the stdlib reads it, and nothing ever writes the hand files.

  The machine files are JSON.
- **Format.**
  - R0.6 freezes the file format as a written spec ((private evidence)), and 4.10b implements it, so the drafts don't drift.
  - The runtime checks are hand-written in the loader. There is no published JSON Schema in v1 (§12.1's schema rule is for third-party contracts).
- **Reviewing changes.**
  - Files are split one per level, with sorted keys.
  - Reviews read the TOML diff plus the vanilla-playthrough spoiler.
  - A database change shows up in the plan goldens, so it surfaces for review through them.
- **Migration.**
  - The 43 nodes and 92 edges of `logic_db.json` become the first `levels/*.toml` skeleton.
  - The script marks every migrated requirement `# migrated, unverified`.
  - It also fixes the known errors:
    - power level 1 is matched by literal name (AUDIT new A);
    - the `barrier_map`;
    - `town→w1_beach` is free in the database but water1 in the owner's notes (I-15).

### 4.3 How vanilla is encoded and verified

- **The vanilla placement** is the `vanilla` field of every generated location. It needs no hand data.
- **Check 1, beatable and fully accessible:** `test_vanilla_placement_is_beatable_and_fully_accessible_without_tricks`. It fails if the logic is too strict anywhere vanilla needs it. It covers every gem location.
- **Check 2, the vanilla route replay.**
  - The owner records the order in which he collects the **non-gem** locations in a normal 100 % run: the majors, obsidians, keys and consumables, about 200 entries. It goes in the per-level TOML and is made once, then extended.
  - Each step must be safe when it is reached, which catches logic that is too strict in a specific place.
  - Do the same for each named skip at its difficulty.
- **Check 3, realm by realm while authoring (4.10d).**
  - Each realm step must pass both checks while the other realms are stubbed: each unauthored realm becomes one free node holding its vanilla items, and those items stay out of the pool.
  - That keeps errors local.
- **Logic that is too loose** (logic says passable but the game says no) is caught only in the game:
  - each realm step ends with a bootable slice once 4.10f-i exists, and the owner checks two spheres of one seed in xemu;
  - the spoiler's obtain and return paths make a reported logic bug reproducible.

### 4.4 What the data must never hold

Per CLAUDE.md, names, counts, offsets and hashes are fine. Coordinates, transforms, raw records and hexdumps are not.

- **Node membership and proximity** are computed in memory. Only `location → node` and relation names are stored.
- **Public AzurKit (RQ-10).** The generated files carry about 1,400 debug names from the game's levels, and the hand files use generated ids.
  - Q85's licensing review must decide before 4.10b's first commit whether these may be committed.
  - **If not:**
    - location ids are already name-free (`<level>/g<graph>/r<record>`);
    - `generated/` is built from the user's ISO and never committed;
    - the pure tier uses the toy database only, and the real-database tests move to the vanilla tier;
    - the hand files refer to objects only by generated ids or owner aliases.

### 4.5 Auto-derived logic: the plan for 4.10 (2026-10-11; D108)

**Source:** (private evidence), the research behind D108. Its counts are [workflow] here unless marked. The R0 work answers "can the constraints be worked out without the owner testing every barrier?" with **mostly yes, but not with no owner involvement at all**. This section replaces §4.1's assumption that the owner hand-authors every edge.

- **Gate logic is data.** R0 decoded what opens each gate: barriers, geodes, keylocks, obsidian locks, seals, disc chains, song crystals, bosses and the special gates (§2.4–§2.10). It also decoded the cross-level map: 70 live exits, each with its arrival spot under the engine's own rule [verified: `db-draft/check.json`].
  - xemu confirms the rules one family at a time, not barrier by barrier: about 15–25 probes [inferred].
  - Obsidians get nothing from data: none of the 100 has a data gate. Of the 203 non-gem spots, only 21 have exact data requirements, so 182 still need a region.
- **Collision is decoded.** The `tern` sections are the collision meshes ([`XBR_FORMAT.md`](../XBR_FORMAT.md) § "`tern` (collision)").
  - They match xemu to about 1e-5 m: six standing spots and f6's ledge [verified, `geometry/tern.py s6check`, re-run for Step 2.20j].
  - 96.5 % of the pickup generator points sit on a decoded floor.
  - So these can be computed instead of mapped by hand: each location's node, the walk and drop edges, which edge a barrier blocks (its `destroy_from`), `button.at` and `event.at` from the trigger meshes, and where each exit is.
- **The movement envelope** comes from the verified per-tick laws (jump, air control, flaps; xemu s6). On open ground, from a 7 m/s run, it gives these human-safe gaps [inferred]:

  | Kit | Gap |
  |---|---|
  | no shield | about 6.7 m |
  | shield | about 7.5 m |
  | air 1 | 11.5–16.1 m |
  | air 2 | 16.4–23.4 m |
  | air 3 | about 19–27 m |

  - Height tops out at air 1 or 2: anything more than about 2.4–2.7 m above the takeoff needs a lift, ladder, spring or updraft.
  - Falls: under 6 m is free, 6–17 m costs at most 10 HP, and 17 m or more is lethal.
  - Springs, updrafts, climbables, slippery floors and the ledge lip lift are outside the envelope until one calibration sitting measures them (R0.4c).
- **Two envelopes keep it safe.**
  - Logic reach (R) uses the human-safe envelope, excludes slippery floors, and accepts a jump only if its arc clears `tern`.
  - The trap check (R_phys, §2.13) uses the frame-perfect envelope.
  - Each edge carries a `confidence`: `assumed` < `data` or `physics` < `probed` < `owner`. Editing an edge resets it to `assumed`. Below the confidence floor (one floor for every setting since D122 and D144 [inferred]; *was:* the preset's), logic uses the stricter requirement. Raising a confidence only ever relaxes logic, so this keeps §3.1's monotonicity.
  - D108's movement tiers (§2.15) choose the margins between those two envelopes.
- **What still needs the owner:**
  - tricks and skips, which nothing in the data shows;
  - one region-and-edge picture per level to review (Q255; about 20–40 min each);
  - signing the vanilla non-gem route, which the agent drafts from community sources (Q257) and the town temple's hint order;
  - signing `known_traps`;
  - two spheres of one seed per realm slice;
  - two decisions D108 left open ((private evidence) §3 item 4, §8 action 2), ~~**Decision needed**~~ **answered 2026-10-12 by D122 and D123** (ids Q260 and Q261, allocated 2026-10-11 by Step 2.20m):
    - *Q260, §11.C, changes output:* the confidence floor per preset, and the priority-locations v0 (with (private evidence) §1.4's optional v1 narrowing: majors only on spots whose requirement is data-exact or geometry-derived with margin). Needed before 4.10e-ii, where the presets and their plan-hash goldens land; the narrowing shapes 4.10e-i's fill, so it is needed before that step if v1 takes it.
    - *Q261:* rulings on three community-reported cases [web, unverified by us]: d2's 3 vat gems respawn on every reload; skipping f4's platform cutscene softlocks the level; the fire guardian's arena can be left early. Each is needed before the realm step that authors its level (4.10d-ii…v).
    - **Answered (owner, 2026-10-12, question rounds 2–4):** *Q260 → D122:* major items (powers, keys) go only on proven spots, where the requirement is exact from data or confirmed with margin; minor items may go anywhere reachable (the v1 narrowing, taken). The per-preset confidence floor follows from it: a major's spot must be proven, whatever the preset. *Q261 → D123:* d2's vat gems are normal spots (no exclusion); f4's platform-cutscene skip is ignored (no guard); leaving the fire guardian's arena early is allowed in logic now, as normal movement, not a held skip.
    - *Until then (2026-10-12, D115, "work unattended and dont ask questions"):* neither goes to the owner as a question. When its step comes (4.10d, 4.10e), the agent takes its recommended option, recorded as "default taken under D115", and lists it in that step's report for the owner to review or overturn.
- **Tiers.** These are the plan for 4.10. *2026-10-12 (D137):* R1 runs now, in Modkit: the R0 drafts are ported in at R1.1–R1.4 and authored per realm at R1.8 and R1.11a–d.

  | Tier | What | Where it lands | The owner's part |
  |---|---|---|---|
  | **v1**: no tricks; data, geometry and the human-safe envelope | a kept `tern` reader (done: `geometry/tern.py`); HM-08's transforms; reachability with the two envelopes; regions, edges and `destroy_from` fed into the database; tags for the moving rigs (a5, w4, e6, airship, the e2/e5 gondolas); family probes and an exit-hop sweep; the calibration sitting; a picture per level; a community route draft | R0.4c, R0.4d, R0.6b, R0.7 (now a review of drafts); 4.10a (plus `tern` and regions), 4.10b (confidence labels, and a rule that no gate goes unexplained), 4.10c-ii (R_phys), 4.10d-i…v (one realm per step), 4.10f-ii (the envelope is D83(c)'s movement rule) | reviewing the decisions and the per-level pictures; signing the route; booting 5 slices |
  | **v2**: the owner's tricks and probe-relaxed edges | each skip encoded and replayed in xemu to set its difficulty, and to confirm it before it enters logic (D114); near-limit edges probed and relaxed; R2.8's movement profiles; the gem-node review, so `progression_on_gem_spots` can rise above 0 (R2.11) | 4.10e-ii (presets), 4.10h (soak), R2.8, R2.11 | describing each trick (about 15 min); confirming about 2 bot-found edges per realm |
  | **v3**: big skips and glitched logic | the community's skip catalogue (out-of-bounds routes and named skips); optionally the game's own collision sweep run on decoded `tern` in Unicorn; parallel xemu | §7's extras | confirming each skip's difficulty |

- **Cost** [inferred]: about 20–30 agent sessions and 5–8 agent xemu sittings to reach v1-quality logic. The owner's share is about 11–20 h of review, spread over the realm steps.
- **Level Studio's verdict** (D104's run, (private evidence)):
  - It decodes the visible geometry and the node-graph world transforms. Its positions equal R0's `nodegraph` on 10,062 records in 4 levels [verified].
  - It decodes **no collision**. Its overlay reads `sdsr`, which is streamed audio, and finds 0 faces on the USA disc [verified].
  - It is useful as a viewer while reviewing the per-level pictures. Nothing is ported from it (D95).
  - Its report's estimate (4–8 agent-weeks to an automatic physical graph, with collision mostly undecoded) predates the `tern` reader. The reader decodes every chunk's vertices and faces, so only the spatial structure and the face group byte are left.
  - A possible give-back, our `tern` decode as a real collision overlay in its viewer, waits for the owner (HQ-10).

---

## 5. Applying placements to the game

### 5.1 Today's writer and the M3 lesson

- **The mechanism today** [verified, AUDIT §5]:
  - an entity name refers to a global `config.xbr` template;
  - placing an item renames the name string at the scanner's slot;
  - the major step then renames every NUL-terminated copy of the old name in the level (`_rename_all_refs`).
- **M3** [verified, AUDIT §5]. A search-and-replace over a buffer that earlier operations have already changed rewrites slots that were already placed.
  - 109 of seeds 0–199 write placements that differ from the solver's, and all 109 are unwinnable.
  - Seed 42, the G3 pin, is clean.
  - D71's fix renames only what the levels held before the stage. Only the `randomize-full:seed=1,shuffles` G3 case changes [verified, commit `dfe9e20` body]. ~~It is on `p1/review-fixes-code` and not yet in `p1/stack` [verified 2026-10-10].~~ *Later on 2026-10-10:* it landed (filtered `37c4b49`), and D74 (AZ-169, Review fixes 2) re-recorded a second G3 case, `randomize-full:seed=42,all` (Q194, accepted by D92).
- **The census adds a reason** [verified, census F1]: all generators of one item type in a level point at **one** name string.
  - Renaming that string changes the type of all of them: town's 5 power_life, e7's 6 batteries, and every gem of a type.
- **The lessons:**
  - compute every write target once, **from vanilla**;
  - a plan assigns payloads to precomputed slots; it never searches a buffer that is being changed;
  - read the result back.

### 5.2 The new writer: repoint each generator, then read back

1. **Slots from vanilla.** For each location, the level-graph reader gives the generator record and its name field (length, ref) at record +0x1C/+0x20. The string it names is at ~~`record + 0x24 + ref`~~ **`record + 0x20 + ref`**, and the length excludes the NUL [verified, `review-feasibility` `gens.py`]. That field is the write target.
   - *R0 (rz-c):* the ref is relative to its own field at +0x20, so the string is at record + 0x20 + ref, not + 0x24 [verified by every test build's read-back and by the items spawning in xemu].
2. **Repoint; don't rename.** For a location whose planned item differs from vanilla, the field is set to a string that holds the new item's template name, in the **same node graph**.
   - **An existing string.** Every realm level and town already holds all four gem names and `obsidian` [verified]. So gem-to-gem and obsidian moves cost no new bytes there.
     - life, d1 and d2 have no `obsidian` string.
     - airship and training_room have no gem strings [verified, `gens.py`].
   - **A new string** (for example `power_air` in a1) is written NUL-terminated and 4-byte aligned into the zero padding after the node section that holds the generator.
     - That padding is 280 B (f3) to 6,412 B (town); w3's second graph has 312 B. The padding is all zeros, and the next section always starts on a 4 KiB boundary [verified, `gens.py`, `geo.py`].
     - The engine reads each section's size from its TOC entry [verified, XBR_FORMAT].
     - Options, tried in order:
       - **(b1)** a ref into the padding, with the TOC unchanged;
       - **(b2)** the same, and the TOC entry's size field (+4) grows by the bytes used. Nothing moves, because sections start on 4 KiB boundaries;
       - **(c)** grow the file. This needs XBR section relocation, which no code or design covers [unverified]. D30 and V14 cover moving a grown file within the ISO, not growing a section inside an XBR. Structural edits to level XBRs raise `NotImplementedError` today [verified, `edits.py`].
     - *R0.5-i (rz-c, 2026-10-11): **the path is (b2).***
       - (a) A generator repointed to an existing string spawns the new item, and the other generators that share the old string are unaffected [verified xemu, placed].
       - (b1) works only inside the bytes the loader reads anyway, up to the next 512-byte boundary: 93–504 B per graph, not the whole padding. A string 512 B past town's payload spawned nothing. The loader rounds its read length up to 512 [verified xemu, placed; static 0xA5480, 0xA5223].
       - (b2) works up to +1,024 B into w1's 4,088 B gap, and each grown level loads and plays [verified xemu, placed]. ~~That its budget is the whole gap, 280–6,412 B per graph, is [inferred]. Placing a string at a gap's end would verify it (w1 near +4,0xx, town graph 1 near +3,6xx).~~ *R1.10a (sitting r110a, (private evidence)):* a new string ending on the gap's last byte works in w1 (+4,076 to +4,088) and in town graph 1 (+3,684 to +3,696), each TOC size grown over it: the item spawns and is picked up [verified xemu, placed]. The budget is the whole gap, 280–6,412 B per graph.
       - The fallback below is not needed.
     - **Budget.** Each node graph has a new-string budget equal to its padding. The fill counts the distinct new names per graph and never exceeds the budget (§3.3). An obsidian placed in life, d1 or d2 costs budget. *R0: under (b2) the budget is the gap with the TOC size grown; ~~the whole gap is [inferred] beyond +1,024 B~~ R1.10a: the whole gap, verified to its last byte.*
   - **The fallback if (b1) and (b2) both fail.** Majors move only between unique-string generators, renamed in place with offsets computed from vanilla. Gems only change type, by repointing among the existing gem strings. v1 would still ship, with a narrower pool for majors.
3. **Clusters.** A cluster keeps its yield and its type, or swaps type with a cluster of equal yield. **No count field is written in v1**, so I-4 is off the critical path.
4. **`_move` generators.** There are 50: 46 gems and 4 `obsidian_move` [verified, `gens.py`]. Each shares its base item's inventory type.
   - A location records its `template`, and its item is the base item.
   - A gem→gem retype keeps the `_move` suffix when the level has that string.
   - I-5(g) tests a `_move` generator repointed to a plain template and to a major.
5. **Secondary copies** (AZ-158): 18 of 22 key slots and 7 of 35 major slots have a second NUL-terminated copy of the name [verified, AUDIT §5].
   - Repointing never renames a string, so the copies stay as they are. A lock checks the key type stored in its own trigger platform [verified by pattern search, census §5].
   - I-1 finds out what reads the copies (a lock's key reference or a debug name). I-5(d) checks the behavior: a key generator repointed to another key type opens that type's locks.
   - *R0:* the copies are lock effect paths and debug names; nothing placement-related reads them (R0.3a §5; AZ-158 is not a defect). I-5(d) is answered too.
     - An e2 `key_gear` generator repointed to `key_circuitboard` gives a circuitboard, which opens the circuitboard locks and not the gear lock.
     - A w1 `key_life1` generator repointed to `key_battery` gives a battery, which opens e2's battery lock [verified xemu, placed].
   - *R0 (I-5 (e)):* `power_water_a3` placed in w1 raises water [verified xemu, placed].
6. **Town vaults.** `SCALE_OFFSETS` is relative to the shared name string, so it can't address the 5 power_life vaults one by one [verified, `review-feasibility`].
   - The writer scales a vault through its generator's parent transform, or drops the scaling if repointing keeps the vault's transform.
   - I-5(c) covers an item moved into a vault, and a non-gem item at a gem spot.
   - *R0.5-i (rz-c; the vault half of I-5(c)):*
     - Items moved into a vault spawn and can be picked up [verified xemu, placed].
     - Scaling through the generator's parent transform changes nothing visible, and the old `SCALE_OFFSETS` is not a scale. It writes the generator's `lodVisibility`, `playAnimIndex` and `maxGenerated`, and `maxGenerated` 0.5 makes the vault respawn its item after every pickup (AZ-280; Step 2.20i stops the write, D110) [verified xemu, placed, for a fragment].
     - Each item keeps its model size. A fragment or `power_air` in a vault can be picked up through the closed force field, while a native `power_life` can't [verified xemu, placed].
     - So v1 needs a vault rule, for example only items no wider than the beam (keys, `power_life`, `power_staff*`, `power_ammo`). The alternative, a per-instance scale, was not found. The rule is open. *Q290's default (2026-10-12): `power_life`, `power_staff*` and `power_ammo` only. R1.10a (sitting r110a):* `power_staff1` and `power_ammo` moved into two `power_life` vaults are blocked by the closed field like the native `power_life` vault beside them: real stick input from 3 m stopped the player at 1.28, 1.23 and 1.23 m, with no pickup [verified xemu, placed start, real input].
7. **Read-back (the build gate).**
   - Decode every written level with the same reader.
   - Map location → payload, and compare the result with the plan.
   - Any difference fails the build, and no ISO is written (D35).

   This is `test_built_iso_reads_back_to_the_plan` and also a runtime check. It would have caught M3. Re-solving the read-back placement would add nothing once it equals the plan.
8. **One pass per level.** The writer streams one level at a time, as the web plan's 4.10 amendment requires.
   - The build must rewrite each changed level's `filelist.txt` line, as this repo's builds have done since 2026-10-09. Otherwise the game's HDD cache plays the old level [verified, xemu-oracle hazard 8]. *R0.5-i: every boot of an edited level re-copied it from the DVD, by the block stats [verified xemu].*
9. **Exits and the spot string are not touched in v1.**
   - Today's connection shuffle zeroes the spot, includes the 5 disc-return portals, and moves shared-string groups together [verified, AUDIT §7, census F2].
   - It is not ported.
10. **Built (Step R1.10a, 2026-10-13):** `azurik_mod/randomizer/writer.py`, a library; R1.10b wires it into `randomize-full`.
   - A placement maps pool location ids to `items.toml` names; R1.9's plan file carries it. An item whose base is the vanilla item writes nothing.
   - `layout(placement, db)` is pure. It returns each graph's repoints and new strings, and names every refusal at once (D35): an id that is no pool location (so never an exit or a spot), an item `items.toml` doesn't define, a guardian slot given another item (D81), and a graph over its budget. A graph's budget is its `padding_after` rounded down to 4, and each distinct new name costs `string_cost(name)`, its NUL rounded up to 4. The fill (R1.9) reads the same numbers.
   - `write_plan(files, placement, db)` makes one pass per level file on a `{name: bytearray}` view (an `IsoStaging`: the build's first layer). It checks every target against vanilla, records the writes, and applies them only once every file has passed.
   - `read_back(image, placement, db)` decodes every location of every level file of a final image with the generic node readers, each section cut at its TOC size, checks each level's `filelist.txt` line, and lists every difference.
   - ~~`build_iso(placement, iso, out, db)` checks the input (D27) and the output (D36), writes, packs the image with its `filelist.txt` lines (`xiso.packed`, which also repairs Europe's stale lines), reads it back and only then writes it (D35).~~ *R1.10b:* `randomize-full` does that with the packs and mods between (§5.3's built note), and `build_iso` is deleted. Both releases build (`tests/test_randomizer_writer.py`).
   - Sitting r110a (private evidence) booted the test's plan (USA): each of its 7 changed locations, 2 of them new strings, gave its planned item, none respawned, and the edited town was re-copied from the DVD [verified xemu, placed].

### 5.3 Composition with mods

- **The randomizer is a `generator` edit layer** (D6, §12.2).
  - The recipe is the plan's inputs (generator version, settings, seed, `db_digest`); the plan, with its placement, is the layer's derived record (REORG §12.2, round 2: A2-5). The recorded byte changes are the truth for replay.
  - **Layer order is canonical:** generator → packs → xbr → external [verified, REORG §12.2]. Generators declare `requires_vanilla` and run first.
  - The planner never sees mods. Conflicts with later layers are reported (D28).
- **Inputs.** It builds only from vanilla (D27). Nothing is written on any failure (D35), and the input is never edited in place (D36).
- **Read-back on the final build.**
  - A mismatch caused by a later layer that touches a placement is reported as a D28 conflict and marks the build `logic_verified = false`.
  - A mismatch that no later layer explains is a writer bug and fails the build (D35).
- **"No movement below vanilla"** (REORG §5.4) is the randomizer tool's `verify` (REORG §12.1, Tool protocol), which `build()` runs: Step 4.5 builds the hook and 4.10f-ii the check. It reads the packs recipe from the manifest and each slider's `logic_floor` from the mods catalogue it is given (round 2: A2-1).
  1. When a randomizer layer is present, each movement slider's value in the packs recipe is compared with vanilla. One registry field per slider declares the direction: `logic_floor = "min" | "max"`.
  2. A slider that lowers jump height, flap count, walk speed or air control below vanilla, or raises gravity above it, records `logic_verified = false` in the manifest and in the build report.
  3. The build is **flagged, not refused**, per REORG §5.4's wording. Whether it should refuse instead is part of RQ-11.
- **Today's gap:** physics packs are applied after placement and are never checked (N8 [verified]).
- **Built (Step R1.10b, 2026-10-13):** `randomize-full` runs plan → write → read-back (`azurik_mod/randomizer/layer.py`): its D27 input check, then the plan (a fill under the settings, or `--plan`), written as the layer `randomizer` with `--obsidian-cost`'s thresholds (none when the cost is vanilla's, Q243), then the packs, the player model and the config mod, then the read-back of the final image before it is written. A difference whose bytes a later layer wrote (the location's record, name field or string) is a D28 conflict with `logic_verified = false`; any other fails the build. A cost above vanilla's also reports `logic_verified = false` (the logic assumes vanilla's thresholds). The movement-slider check above is R1.13's (next bullet). MCP `rando_build_iso` takes the same options; the GUI's Randomize page sets the seed, D144's options and the categories (§5.5's built note).
- **Built (Step R1.13, 2026-10-13; defaults taken under D115):** the movement rule is `layer.check_movement`, which `randomize-full` runs after the packs and the player model when a plan is present: each slider of an enabled pack (`ParametricPatch` or `XbrParametricEdit`) declares `logic_floor` (`"min"`: walk, roll, swim, jump, air control, flap height, far-descent recovery, the flap ceiling and the three air shields' flaps; `"max"`: gravity, whose apex stays but whose airtime shrinks, and the per-flap fuel cost; none: the descent-penalty fuel, whose vanilla cost already empties the gauge, `fps_unlock`, which keeps the game's speed, and `player_max_hp`). A value past it, or a params name no slider of the pack has (it can't be checked), makes `logic_verified` false with the reason in the build report's `why_not`. It reads the recipe, not the final image, as item 1 says: a config mod that edits a movement cell (garret4's `runSpeed`, a shield's `Flaps`) isn't checked [inferred gap, left]. Q291's clause: a `--player-character` other than garret4 without `--player-character-standardize` (D131) is flagged the same way; a standardized body isn't. R1.10b's D28 handling was checked and covers a later layer that changes a placement on every path (CLI, MCP and the GUI build through `cmd_randomize_full`; packs, the model and each mod shape are `LayerLog` layers): no change. `test_recorded_plan_builds_to_its_golden_iso_hash` (provisional): the default plan in `tests/goldens/rando_plans.json`, built with `--plan` from the canonical USA image, gives the sha256 `tests/goldens/rando_iso.json` records (`089a8584fa2f…`, G3's `seed=42,default` ISO); Step R1.16 re-records it from the build P7(a) beats.
- **G3 follows the data (from R1.10b on):** G3's randomizer cases build plans from the committed database, so a step that changes realm data (a level file, a proven spot, a skip, items or world) changes their bytes: it re-records them with `pytest tests/test_randomize_full_golden.py --update-goldens` (serially) and lists the diff in its commit body (REORG §10.2a's G3 table). *From Step R1.12* it re-records the plan goldens with them: `pytest tests/test_randomizer_fill.py -k golden --update-goldens` rewrites `tests/goldens/rando_plans.json` (seed 42's plan sha256 under the strict, default and max profiles, Q293, and the default's whole plan; strict is its named `FillError`, marked to re-record after Step R1.2b, D156). *From Step R1.13* the same run re-records `tests/goldens/rando_iso.json` after them (the default plan's whole-ISO sha256, R1.13's note above): `pytest tests/test_randomizer_fill.py tests/test_randomizer_writer.py -k golden --update-goldens`.

### 5.4 Settings in v1: density and exclusion

| Setting | Default | Effect |
|---|---|---|
| `progression_on_gem_spots` | **0** (RQ-3) | The share of the 71 majors allowed on single-gem spots. At 0, gem locations hold only gems. Raise it only after the gem-node review. |
| `exclude_locations` | lock 10 and full-clear locations (RQ-5) | AP's ExcludeLocations: useful or filler only. Forfeitable locations (§2.9) are added automatically. |
| `obsidian_cost` | vanilla | the 10 lock thresholds (§2.8) |
| accessibility | `full` | the only mode in v1 (§1) |
| skip ceiling / toggles | 0 / none (D144) | §2.15 |
| movement tier | standard (D186; D144 had hard) | §2.15 |
| dark_fire | 1 (D144) | §2.12 |
| `exclude_categories` | none | Step R1.10b (the GUI's item rows, D151): each named category (`fragments`, `powers`, `gems`, `obsidians`, `consumables`) keeps its vanilla items, pre-filled like the keys; RANDOMIZER_DB §7.2. Keeping obsidians vanilla is refused before any fill attempt: it keeps 28 of the 39 proven spots a progression item may take, which leaves 11 for 27 progression items (Step R1.27, AZ-454; filling it is AZ-455's, R1.24) |

**Gem totals are preserved by construction.** Single gems swap among single-gem locations, and clusters keep their type or swap only with an equal yield.
- So every type keeps its vanilla total: sapphire 388, emerald 386, ruby 382 and diamond 386 [verified, census]. All three fuel upgrades stay available; they need 77–79 % of each type's total.
- Without the cluster rule, diamonds could fall to 268 and rubies to 264 [verified, `myield.py`].

### 5.5 The Randomizer tab (v1; REORG Step 4.0 round 2, S2-12)

*Default taken under D115 (Q276; accepted by the owner with Step 4.0's v1, D124). It is re-reviewed at the start of 4.10g (now
R1.14), once Q260, Q261, D108's tier names and D114's confirmed skips have settled (Q260 and Q261 have, by D122 and D123).*

*2026-10-12 (D137):* built first as the Modkit GUI's Randomize page (Tk, R1.14), then ported as the hub's tab (AzurKit 4.10d).
*2026-10-12 (D144):* there are no presets; the player sets the options below, saved as a settings file and a share string (§2.15).
*Built so far (Step R1.10b, 2026-10-13; a default taken under D115):* the Modkit page keeps Step 2.29's item-type table and its maps (D151, owner) instead of a bare switch: each live row's box is an `exclude_categories` category (ticked: shuffled; none ticked: no generator layer, so the box set is the on/off), the keys row is greyed "Keys stay vanilla (I-9)", the barrier and trap rows and the connections' box are greyed with v1's reason, and one row above holds the seed (free text, New), the skip ceiling, the movement tier and the dark-area fire. The pool `PackBrowser` tab is gone with the `rand_*` packs. Save/Load settings, the share string, the skip toggles, the spoiler and the build's conflict rows are R1.14's.
*Built (Step R1.14, 2026-10-13; defaults taken under D115):* the page, compact at 1100×700 with no scroll: two rows on top (☑ Randomize, off by default and the only switch; Seed with New; Skips; Movement; Dark areas need Fire; the obsidian cost; the share string, editable, with Copy), a ⚠ row while a build would report `logic_verified: false` (the Patches page's movement sliders and model, `layer.movement_reasons`, and an obsidian cost above vanilla's: the first reason and "+N more", each whole on hover), then the item table (its boxes now ticked by default: every category shuffles, the defaults' `AZR-AAIA`) over the skip list (the turnable skips, 5 rows, "…N more", a filter on ⌘F; a click toggles a skip against the ceiling, and a click back to the ceiling's clears the toggle; the held ones counted), and a right column with Load settings… / Save settings…, Spoiler Save…, the read-only labels and the connections. Defaults: the obsidian cost is not a settings-file or share-string key (§7.2's frozen format has none), so the settings and the share string don't carry it, and the state file keeps it beside them; the seed isn't in them either (§7.2 reserves `seed`); Spoiler Save… regenerates the spoiler from the last build's placement file, which now holds the whole plan and the build's verdict (`azurik-placements/3`); settings files go wherever the save dialog says, refusing the input, the output and `iso/`. Build & Logs shows each stage of plan → write → read-back and the build's ⚠ row. G4 gained `run_randomizer:randomize` (the page's defaults), whose files equal G3's `seed=42,default`.

One tab in the hub, with REORG §12.7's density tokens (D21): two columns, 20 px rows, collapsible
sections. It fits 1100×700 with no scroll, and GUI tests 1–2 cover it.

- **On/off.** `☑ Randomize` adds or removes the one `generator` layer. It is off by default and is the
  tab's only enable switch.
- **Settings shown (v1 only):**
  - ~~Preset: Glitchless (D118), Easy, Normal (default), Hard or Expert; it shows "Custom" once any setting changes.~~ *D144: no presets.* Settings: Save settings… / Load settings… and a share string;
  - Seed: free text with [New]; hashed to an int (§3.5).
  - Skip ceiling: None (0, the default), Standard, Hard or Frame-perfect (2–4; D144, D259: no skip is rated Safe, 1), and per-skip
    toggles; a toggle wins over the ceiling but never turns on a held or manual skip. Only confirmed skips
    are listed (D114); held ones are counted, not listed. ~~`saveanywhere` skips sit behind "Manual…" with a
    warning, and no preset turns one on (§2.14).~~ Manual skips are not offered in v1 (D144; Q294).
  - Movement tier: safe, standard, hard or frame-perfect; standard by default (D186, amending D144's hard). Dark areas need Fire 1, 2 or 3; 1 by default (D144); an enabled nolight skip lifts it for its own dark area (§2.12). ~~Set by the preset (D129: safe for Glitchless, Easy and Normal; hard; frame-perfect for Expert); the names settle at 4.10e-ii (D108).~~
  - `obsidian_cost`: vanilla by default.
- **Read-only labels:** accessibility `full`; victory, Spideyzar; exclusions as "lock 10 + full-clear ·
  N forfeitable" (editable from the CLI only in v1).
- **Not shown in v1:**
  - `progression_on_gem_spots`: no row until R2.11's gem-node review (D77);
  - `beatable`, `priority_locations`, `exclude_levels`, pool variants, fast progression, the word hash,
    `--allow-db-mismatch`, `db-diff`, cluster split, a random guardian fragment, fuel tiers;
  - entrance, enemy and start randomization (§1);
  - the confidence floor (Q260, answered by D122: majors only on proven spots) and ~~the lenient knobs, which stay preset-owned~~ (`dark_fire` is a user option, D144).
- **Settings files (D144: "Yes, user-saved settings").** Save settings… writes every option to a small file
  (the settings schema, the randomizer plan's private evidence `db-draft/FORMAT.md` §7.2, which R1.4 freezes; never into `iso/` or over the input, D36).
  Load settings… reads one and refuses it whole, naming the key, when a key is unknown or out of range or a
  toggle names a held, manual or unknown skip (D35). The share string is the same settings as one pasteable
  line. The GUI keeps the last settings in its state file (disposable). Each spoiler and build report records
  the settings and the share string.
- **Build.** The hub's one Build runs plan → apply → read-back, with the generator first (REORG §12.2).
  - A later layer that changes a placement shows as a D28 conflict, with `logic_verified = false` in the
    status line and the edits tree.
  - An unexplained read-back mismatch fails with "nothing written" (D35).
  - Movement below vanilla shows a ⚠ row: flagged, not refused (D83(c)).
- **Output.** Spoiler [Save…] goes through the OS save dialog, which refuses `iso/` and the input (D36).
  The spoiler is regenerated from the plan and the database (§3.6) and says that no settings are
  softlock-free before R2.1 (D82). There is no Plan [Save…] in the hub: the manifest is the export, and
  `azurkit rando plan` keeps the plan file.
- **Density.** The skip list shows at most 5 rows with "…N more", filtered by ⌘F.
- **Test (D10).** One GUI test at R1.14 (was 4.10g),
  `test_randomizer_page_settings_round_trip_through_the_build_recipe`; the hub's tab gets its own at AzurKit 4.10d, e.g.
  `test_randomizer_tab_settings_round_trip_through_the_generator_recipe`.
- **Web (W4).** The same settings, with no edits tree; the seed and settings travel in the `#p=` preset
  (REORG §12.2, Share projection).

---

## 6. Investigations backlog

**Tools:**
- **Data:** the census decoder and XBR reading, run in-process on the vanilla ISO.
- **Ghidra:** static analysis on the owner's project. Use read-only methods only, and never open it headlessly while the owner has it open.
- **Unicorn:** an L2 probe.
- **xemu:** the dedicated oracle HDD (D67), with states saved and loaded by name over QMP.
- **Owner:** play knowledge.

**Save states and test builds** [verified, xemu-oracle hazards 2 and 8]:
- `loadvm` restores RAM, game code included, so it discards the build you booted. A QEMU state can only replay the build it was taken on.
- So the RZ states below are for **vanilla** investigations only (R0.4).
- Writer tests (R0.5) **cold-boot each test ISO**, navigate the menus, and `savevm` into a **scratch** HDD.
  - They confirm that the edited level was re-copied from the DVD (QMP `query-blockstats`), because the game's HDD cache can hide an XBR edit.
  - Test inventories come from in-game save files (an edited `inv.sav`, re-signed with the console's key: `save edit --kernel`, AZ-338), not from QEMU states.
  - *R0.5-i (rz-c):* the builds were not cold-booted into a scratch HDD. Each was booted by xemu s6's modded-build path from `vanilla-ig-new`: a QMP medium change, a reset, then the menus to the new-game character [verified xemu]. The level re-copy was still confirmed by the block stats.
- **The save fields are only partly decoded.** `magic.sav` is unlabelled number lines (SAVE_FORMAT §4a), `inv.sav` +0x04..+0x10 has no known meaning, and the key slots are [inferred]. **I-0 comes first**; until it lands, states that need powers or keys are made by play or by RAM poke.
  - *R0 (I-0 answered; rz-a):* all four are now decoded [verified xemu, placed]. `inv.sav` is a u32 7 followed by the 0x1D4-byte inventory exactly as it is in RAM. `magic.sav` has exactly 5 value lines, and line 1 is refreshed when the game writes it. `shared.sav` holds {name length, name, value} entries from +4, with no count field. A level `.sav` is the saved nodes' records plus a tail that isn't decoded. The repo's text defects this exposed are AZ-275–AZ-277.

**Proposed RZ states** (vanilla; D67):

| State | Where | Built from |
|---|---|---|
| RZ-NEW | new game, w1_beach | vanilla |
| RZ-W1-FW | w1_beach next to FireWall_01, with water1 | play, or an edited save after I-0 |
| RZ-W1-ICE | w1 IceBlock_01 with fire1+water1, plus a variant with water only | edited save after I-0 |
| RZ-A6-3 / RZ-A6-4 | a1 next to the a1→a6 exit, with 3 or 4 air fragments | edited save after I-0 |
| RZ-E2-CART | e2 at the minecart | play |
| ~~RZ-KEYS6~~ `vanilla-rzp-keys5-w1` (R0) | ~~e2 holding 6 key types~~ w1, holding 5 key types, with `key_life1` (a 6th type) still in the world. RZ-KEYS6 can't exist, because the game caps key types at 5 (I-9). | ~~edited save after I-0~~ RAM pokes from `vanilla-rz-new` and an in-game save (rz-a), on the private drive (a private folder) (Q250) |
| RZ-E7-DARK / RZ-W1-DARK | at each dark room, with fire 0 and fire 1 | edited saves after I-0 |

**Agents run the xemu sessions (owner, 2026-10-11, D102; D92, D100).** R0.4a, R0.4b and R0.5 are agent xemu sessions on clones of D98's fixtures, never on their files in place, one xemu at a time. The owner made states on 2026-10-11 (the `vanilla-rz-*` and `vanilla-ig-*` tags on D98's drive; skill `azurik-xemu-oracle` lists them): they stand where RZ-NEW, RZ-W1-FW, RZ-W1-ICE, RZ-E2-CART and RZ-E7-DARK/RZ-W1-DARK do, but the 14 randomizer ones carry the owner's all-powers inventory, so most I-items poke the inventory first; RZ-A6-3/4 and RZ-KEYS6 are agent-made [workflow: (private evidence) §2]. D102's rules:
- **Agent-made states (Q250).** A state an agent makes (RAM-poked, saved in game) stays on a private drive, (a private folder) (outside `/tmp`, the private evidence and the repo), tagged `vanilla-rzp-*`. It never joins D98's drive without the owner's yes.
- **Placed evidence (Q251).** Evidence from placement (a RAM teleport, exit hops, RAM pokes) counts as `[verified xemu, placed]` for mechanism questions (opens, persists, teleports, spawns). Routes and reachability stay with the owner (or real play).
- **R0.5's scope (Q252).** §8.1's R0.5 row: (a), (b1), (b2), (d), (e) and the vault half of (c) now; the gem-spot half of (c), (f) and (g) wait for R2.11 (D77).
- *R0, done 2026-10-11:* four sittings ran, one xemu at a time: rz-a (R0.4a), rz-b1 (R0.4b-i), rz-b2 (R0.4b-ii) and rz-c (R0.5-i). Every sandbox's baselines were equal before and after.
  - The only agent state made is `vanilla-rzp-keys5-w1`. RZ-A6-3/4 were not needed: rz-b1 reached a6 by exit hops with fragment pokes.
  - Two deviations are recorded in the reports. rz-b2 saved four transient scratch states inside its sandbox, and rz-c wrote its ISOs into the main checkout's `out/`. The rules since then: builds go to the sitting's folder or a `mktemp -d`, never the main checkout (D110), and scratch tags that live and die with a clone are allowed.
- *D108 (Q258):* there is no fixed cap on agent sandboxes, each on its own clone. One sandbox may always run (D102); each additional one starts only while the 1- and 5-minute load averages are both below two-thirds of the CPU count and at least 8 GB of RAM is free; running sandboxes are never killed for load.

**The investigations.** "Blocks v1" says whether v1 waits for the answer.

| Id | Question | Tool | States | Blocks v1 |
|---|---|---|---|---|
| **I-0** | **The save fields.** On a vanilla save, diff `magic.sav` and `inv.sav` before and after picking up power_water (w2) and key_air1 (a1). Cross-check 0x83330 statically. | xemu + Ghidra | RZ-NEW, then play | **yes**: it enables the edited-save states and I-9 |
| **I-1** | **The level `node` section's connections and attribute values:** keylordSystem, keylock (including e5's 4 key-less rigs), the `DiscTrigga`/`DiscSeals` seals, the town obsidian locks, combiner/mathNode constants, what reads the secondary name copies, and e7's 6-vs-7 keylord systems. (World transforms are already decoded by `census.py`.) | Ghidra (the nodegraph loader, node vtables) + extend the census decoder (connections are already parsed as 24-byte records [verified layout]) | none | no. It is the most valuable **accelerator**: it makes I-16 and I-17 exact and maps barriers to edges automatically, and it is needed for R2.2–R2.5. Every value can be hand-authored meanwhile, marked [unverified]. |
| **I-2** | Does a barrier need a power **level** (water 2/3) as well as its elements? Which platform field holds it? Do the `LevelN_sphere` parts show it? | data + Ghidra (the damage compare), then xemu to confirm | RZ-W1-ICE | **yes**: the barrier `level` field |
| **I-3** | How is a combination's level computed (whirlwind 4, `BossWhirlwindLevel_plusCombiner`)? | Ghidra (the magic level) + xemu (e2's song puzzle) | E2+A2 at e2's song | no: combination gates are hand-authored meanwhile |
| **I-4** | Generator count semantics: does −1 mean one per point? Is a1's count-1, 4-point diamond worth 1? | Ghidra 0x6f570 + xemu | — | no: v1 writes no count field (§5.2) |
| **I-5** | **Writer feasibility.** (a) A generator repointed to another existing string in its node graph spawns that item. (b1) A ref into the padding after the node section works. (b2) The same works with the TOC size grown. (c) A non-gem item at a gem spot spawns, can be picked up and is scaled sanely, including in a town vault. (d) A key generator repointed to another key type opens that type's locks. (e) `power_water_a3` placed in another level raises water. (f) A non-gem item at a geode generator spawns when the geode breaks. (g) A `_move` generator repointed to a plain template and to a major works. | xemu, with ISOs built from vanilla by an evidence script (from a read-only p1/stack worktree), cold-booted, saved into a scratch HDD, with the re-copy confirmed | cold boot + in-game saves | **yes**: it chooses the §5.2 path |
| **I-6** | Saves: does saving overwrite the loaded save or make a new one? Is there a cap (`toomany`)? Does death reload the last save, and does it revert world state? Where does `gameover` lead? Do f1's and f2's shared `F1_2` ids clash? | xemu; Ghidra on 0x1C8B0 and 0x8D0C5 as a cross-check | RZ-NEW | no. It changes the wording of §2.14 and the spoiler, and R2.1's design. If death reloads, a lethal trap means lost progress, and the spoiler records that per trap. |
| **I-7** | **The 4th-fragment chain.** (a) Does entering a6 with 4 air fragments teleport at once? (b) Does a 4th fragment picked up elsewhere teleport? (c) Which post-boss areas really are no-return without the teleport? (d) Can the player re-enter after the disc is placed? (e) Is the chain level-triggered or edge-triggered? (f) Does it fire when the slot holds a fragment other than #4? | xemu (a, b, d, e, f); owner (c) | RZ-A6-3, RZ-A6-4 | **yes** for (a), (c), (d) and (e). (b) and (f) matter only if RQ-4 picks a random fragment. |
| **I-8** | **Persistence.** Diff a level's `.sav` after breaking one barrier and pressing one lock. Do `crack_block_respawn` blocks and fire walls with `OpenNCloseToggle` respawn? Press each toggle family twice and compare. | xemu | RZ-W1-FW; an a1 state | **yes**: the `persist` and `mode` fields |
| **I-9** | **Keys.** Is a key used up by its lock? Does holding more than 5 key **types** at once work? Does key_battery from e7 open e2's lock? | xemu + an edited save | ~~RZ-KEYS6~~ `vanilla-rzp-keys5-w1` (R0; RZ-KEYS6 can't exist) | **yes**: the §2.6 counts; keys vanilla or shuffled |
| **I-10** | **Minecart.** Which exit pair is the ride? Where does its state live? Can it always ride back? **Does any non-cart edge depend on the cart's side?** | xemu (ride, save, diff e2.sav/e5.sav), or I-1 | RZ-E2-CART | **yes** for the side question (§2.10); the rest only if the cart enters logic |
| **I-11** | The fuel-cap formula and the gem→element pairing; whether fuel regenerates; whether casting the shield refills the flap gauge | Unicorn L2 probe of 0x58240 (in-process); xemu S1 (`vanilla-beach-shield5`, already planned) | S1 | no (§7, R2.10) |
| **I-12** | Can anything be farmed? Is the e2 arena emerald's respawn-like field real? | xemu | play | no: gem thresholds are out of logic |
| **I-13** | The airship gate: what opens `AirshipFight_levelSwitch` in w1, and travel after the fight. Known: it is its own level, entered one way from w1, and it always exits to a3 [verified]. | owner, + I-1 | none | **yes** (owner) |
| **I-14** | Dark rooms (e7, w1): can they be done without light, and how long do the routes take? | owner, or xemu | RZ-E7-DARK, RZ-W1-DARK | **yes** (owner, or xemu) |
| **I-15** | The town↔w1_beach fire wall: is fbarrier1 w1's `FireWall_01` or town's `FireWall_02` (both `watr` [verified])? Which way does vanilla pass it, and does it stay broken? The database has town→w1_beach free, but the owner's notes say water1. | owner, and xemu if unsure | RZ-W1-FW | **yes**: the start sphere |
| **I-16** | Seal thresholds (`DiscTrigga`, `DiscSeals`, e5 `Seal`), and what gates d1 and Spideyzar | owner or xemu (does the seal open with 3?); I-1 makes it exact | none | **yes**: owner or xemu suffices |
| **I-17** | The earth guardian fight's requirements: the acid blocks, the crystal smash and whirlwind level 4 | owner, + I-1 | none | **yes** (owner) |
| **I-18** | The owner's experiment: move a red overlord, kill it, and see whether the key unlocks | needs node-section writes, so it waits for R2.5. Until then, xemu with a RAM poke of the keylord's HP while watching `numDead`. | an e7 state | no |
| **I-19** | **w4's `DayNight_gameState`:** what flips it, and does anything in logic depend on it? | owner, + I-1 | none | **yes**, before w4 is authored |

**Status after R0** (2026-10-11, recorded by Step 2.20j). `wiring`, `thresholds` and `AUTO_LOGIC` are the randomizer plan's private evidence, and `rz-*` are the sittings (private evidence). "Placed" means [verified xemu, placed]: it answers mechanism questions only (Q251).

| Id | Status | What R0 found | Evidence |
|---|---|---|---|
| I-0 | **answered** (placed) | `inv.sav`, `magic.sav`, `shared.sav` and the level `.sav` decoded (above) | rz-a §0 |
| I-1 | **answered** for R0's scope | keylordSystem and keylock wiring; the seals, obsidian locks, combiner and `gameState` constants; e7 has 6 keylord systems; AZ-158 is not a defect | wiring §0–§6, thresholds §0–§4 |
| I-2 | **answered** | a barrier needs its combination at a power level; the attack's level is the minimum of the selected elements'; each group's level is extracted (§2.4) | rz-b1 §0, §2.1; thresholds §10 |
| I-3 | **answered** | a combination's level is the minimum; "Whirlwind4" is a wack-type code; level 1 sets a song crystal (§2.4) | rz-b2 §0 |
| I-4 | static half **answered** | a negative limit −N means N × the point count; a1's 4-point diamond yields 1; the gem totals equal the census | wiring §8 |
| I-5 | (a), (b2), (d), (e) **answered**; (b1) and the vault half of (c) **partly**; the gem-spot half of (c), (f) and (g) wait for R2.11 (Q252) | **§5.2's path is (b2)**; vaults need a rule (§5.2 item 6) | rz-c §0 |
| I-6 | **partly** (placed) | a death reverts the current level to the last save; a new character's saves; `W1_2` (§2.14) | rz-a §0 |
| I-7 | (a), (d), (e) **answered** for a6 (placed); for e5 the chain fires as a6's does (placed: a poke to 4 in the level), and its (d) is [inferred from data]; (b) from data; (c) the owner's; (f) R2.11; (c) for a6, default taken under D115 at Step R1.11a: entered one way (`A6_A1` is armed only before the arrival's lift starts), left by `Killed_levelSwitch` after the guardian or the disc teleport | level-triggered, safe after placement; w1 has a touch chain and life none (§2.9) | rz-b1 §0, rz-b2 §0, thresholds §5 |
| I-8 | **answered** for six families and the ruby geodes; `lever_1way`, teleporter toggles and `ActionButton_toggle` open | fire walls and crack blocks respawn; ice blocks, the `AirSwitch`, the w1 seal and geodes latch; a1's bridge is a toggle (§2.4, §2.5) | rz-b1 §2.2, rz-b2 §0 |
| I-9 | **answered** (placed) | keys are used up by X; 5 key types at most, a 6th refused; keys stay vanilla in v1 (§2.6) | rz-a §0, wiring §9.2 |
| I-10 | mechanism **answered**; the edges are the owner's | two gondola pairs; the side bit makes e2's dock a lethal drop; `MineCarRide2` stays inside e2 (§2.10) | rz-b2 §0, wiring §7 |
| I-11 | not in R0 (R2.10) | — | — |
| I-12 | **partly** | geode gems don't respawn after exit hops; e2's "50" is `critterRange`; d2's unsaved gem generators are a lead (§2.8) | rz-b2 §0, wiring §8–§9 |
| I-13 | data half **answered**; route: **default taken under D115 at Step R1.8** (the AirshipFight switch is in logic from w1's beach once the water and earth guardians are dead; W1_A3 once Balthazar is) | the airship needs the globals `EarthRealm_fixed` and `WaterRealm_fixed` (set in e5 and w3); after the fight a one-way cycle w1 → a3 → a5 → w1 | thresholds §7 |
| I-14 | **partly** (placed) | light gates no game logic in w1 or e7; the routes, the timings and where w1's `W1_Town` exit is are the owner's (§2.12) | rz-b1 §0, rz-b2 §0 |
| I-15 | **partly** (mechanism); **default taken under D115 at Step R1.8**: fbarrier1 is w1's `FireWall_01`, passed with water 1 from either side, crossed only from where it is destroyed (it re-closes: the respawn handling) | a shut `FireWall_01` can't be walked through; one level-3 water hit lets the player through, and a level-1 hit opens the blocker; it re-closes after 5.8 s; fbarrier1 is most likely `FireWall_01` [inferred] (§2.4) | rz-b1 §0, §2.1 |
| I-16 | **answered** | realm seals: a touch with 3; d1: a touch with 4 of each disc (§2.9) | thresholds §2; rz-b1 (w1) |
| I-17 | data half **answered** | the four arena acid blocks, no crystal (§2.7) | thresholds §6 |
| I-18 | **answered** (mechanism, placed) | a kill through the keylord's own damage path opens the cage; the cage is collision only (§2.7) | rz-b2 §0 |
| I-19 | data half **answered**; **default taken under D115 at Step R1.8**: a wait, not a flag (`w4_daynight` harmless; the fan corridor by day is in logic at the hard tier) | the clock is the inventory's +0x000; nothing it drives is saved, so it is a wait, not a flag [inferred] (§3.1) | thresholds §8 |
| Q246 | **answered: close, no Modkit change** | an unknown spot falls back to `startspot`; with a movie there is no hang, but the landing spot wasn't measured | rz-b2 §0 |
| RAM recipes | C1–C7 pass; C8 settled in e7 | (private evidence)'s corrections are listed in rz-a §2 and rz-b2 §2 | rz-a §1 |

- **Re-tests owed** (the fix pass's downgrades):
  - a fire wall opened, then left within 5.8 s, then re-entered;
  - a walk through `FireWall_01` at water level 1;
  - a corrected per-record w1 `.sav` decode, saved as a capture;
  - a (b2) string at a gap's end;
  - keys and powers with `maxGenerated` 0.5;
  - the input ISO's sha256 in the build log;
  - where Q246's movie case lands;
  - the e2/e5 walk-through pair with `DownToggle` 0, in both directions;
  - `MineCar2`;
  - geodes across a save and a death.
- **The owner's questions** (Q251; drafts for review under Q255): `FireWall_01`'s gating and which way vanilla passes it; where w1's `W1_Town` exit is; the e2 → e5 gondola edge while the bucket is away; the walk-through pair; `MineCar2`; I-7 (c); I-13's and I-14's routes; I-19's confirmation.

---

## 7. Extras (later phases)

| Id | Extra | Depends on | Notes |
|---|---|---|---|
| **R2.1** | **Safety net: the save-point warp (D202).** The ritual on a save platform stores that platform as the one return point and loads town; the same ritual on town's save platform (`Temple`) returns to the stored platform. Out of logic: the logic still guarantees beatability without it. (*Was:* a "return to town" option and/or the teleport-on-pickup patch, §2.9 option B.) | a C shim pack, opt-in (`qol_save_warp`, off by default); an xemu matrix | **Landed** as Step R2.1a (below); its open checks are Step R2.1b. It removes the out-of-logic softlock class that exits-only creates (§2.13): a permanent softlock needs a save inside a trap, retail saves only on a save platform (below), and the ritual works on that platform. It is the Azurik equivalent of OoTR's save-warp and Map Rando's rolling saves. **No preset claims to be softlock-free until it lands** (RQ-8). |
| **R2.2** | Barrier-requirement randomization **with visual indicators** | I-1, I-2; per-barrier writes (today's edit is one fourcc per level class [verified]) | The ice-block prefab already holds a required-element symbol and `Level1–3_sphere` parts [verified names]. Showing a new requirement may be a visibility edit rather than new art [inferred]. **D214** (owner, 2026-10-15: "make sure we have a plan for randomizer to potentially randomize what powers barriers need to break, then we can open some areas up like this one with that option on"): the option opens areas whose barriers vanilla gates late, such as a5's islands (steam 3, D213), earlier; with D192(1). |
| **R2.3** | Key/lock type randomization; changing what a button needs | node-section **writes** | The keylock stores its key type in its trigger platform [verified by pattern search], which could be a fixed-width edit. |
| **R2.4** | Entrance (room) randomization: coupled and decoupled exits, plus the minecart's full model | per-node exit repointing (census F2); the escape logic (built in v1); OoTR's validate-after-each-placement with rollback [verified pattern] | Exits-only makes dead ends critical. One-way exits pair only with one-way exits (AP GER). |
| **R2.5** | Enemy randomization | the keylord prefab must move as a whole (I-18) | Keys gated by an enemy stay events. |
| **R2.6** | Rewards for gem and obsidian counts (the owner's idea, "to encourage collection") | the accumulator machinery (built); new locks need node writes | A cheap variant: the 10 town locks' thresholds and contents are already editable [verified offsets], so a "count rewards" setting can reuse them (D144; *was:* preset). Gem locks need `gameState` gem variables [verified to exist], wired by node writes. |
| **R2.7** | Powers beyond 3 (air4 = a cheaper flap below the peak; air5 = full velocity; air6 = ceiling ×2) | shims, the simulator (REORG §5.4 movement profile), xemu | Counters are already uncapped. Each new effect needs logic clauses, as the owner says, or "it's too easy". |
| **R2.8** | Movement-profile logic (gaps and apexes per edge) | REORG §5.4 "Later" | Hand-tagged `{apex_min, gap_min}` edges were rated high value for 3–5 days of work. **The weaker half is built** (Step R1.14b, `8687674`, D167, D168): every flight edge carries a certificate a build re-checks under its own sliders (an edge keeps its tier, moves harder or leaves the logic), and the GUI shows each slider's logic-safe range. Left: stronger movement opens no new edge before a re-derive. |
| **R2.9** | A randomized start (starting items and start location), goal presets | none of the above; a fuller power-storage model, with D190's skip work after R1.16 (with skips such as power storage w2 need not come first) | small. D198 (owner, 2026-10-15): v1 keeps the vanilla opening (water in w2's hose pool). The tracker moved to v1 (D189, Step 2.51) |
| **R2.10** | Fuel tiers in logic | I-11 (the R0.8 Unicorn probe of 0x58240, moved here from R0) | Turns `casts > 50/cost` into a fuel-tier requirement (`fuel.air>=83`, i.e. `diamond>=100`) under the chosen settings (D144; *was:* presets). |
| **R2.11** | Post-v1 settings | v1 shipped | `beatable`, `priority_locations`, `exclude_levels`, `pool.gems` variants, `pool.consumables`, fast progression, named notable tricks, the word hash, a random guardian-slot fragment (needs I-7(b, f)), `progression_on_gem_spots` > 0 after the gem-node review, splitting clusters (needs structural XBR edits) |
| **R2.12** | **Open death realm** (D201): d1's death seal opens with no discs, so d1 and d2 become mid-game areas; Spideyzar keeps his health but hits much harder and is much faster until all five discs are complete | a C shim and one xemu sitting of it; a requirement that depends on a setting (the database has none); d2's climb measured (today the conservative kit) | Step R2.12a, 2026-10-15 (private evidence):<br>• **The seal** [verified data]: town's way down is a plain elevator and touch; d1's arrival rides down into the seal's chamber (d1_core), where `discDeath` (a touch and each disc at 4) opens the chromatic field, the only way on: the outer spires, the bridge-end cutscene into d2, d2's lens door up to d1's floor 1, and the elevator to the inner floors and Spideyzar's floor 9.<br>• **Opening it is a fixed-width edit**: each of the seal's five "at least 4" tests, and the five of its help popup, is a two-key step curve on its own link; ten f32 writes through `xbr_edits` make each one true at 0 (`RE_DATA.md` § "d1's death seal and Spideyzar's floor"). In xemu the seal opened with no fragment held [verified xemu, placed: sitting r212a, (private evidence); a build from vanilla with only that edit, the new-game save, the native warp to d1, the player placed on the seal]: its five tests read 1 before the touch, the touch latched the seal, and within 10 s the field was no longer solid.<br>• **The design** (the owner's, D201): his 3000 HP stay. While any disc has fewer than 4 fragments, a shim on his think (his AI vtable's slot 0, 0x1A08C4) holds his speed factor AI+0x180 (vanilla 1.0, 1.25, 1.5 by HP) at a high value and caps his wait between attacks (AI+0x178, 3–15 s), and a shim on the player's damage call (0x8D648) multiplies the damage of each hit whose attacker carries his AI vtable. No `config.xbr` or XBE constant can depend on the discs: the damage the player takes is a per-type cell of garret4's, whoever hits (`RE_XBE.md` § "Spideyzar's speed, his attacks and the damage the player takes"). Rough cost: 1–2 lane-days: the shim (two hooks, a vtable slot and a CALL with a thunk for the message in EBX), the d1 edit, the setting and the logic below, and one sitting: the fight at 0 and at 5 discs, and whether his beam and projectile hits name him as the attacker [inferred].<br>• **Alternative (a)**, kept as a note: gate his spawn in data. His generator's enable (`DisablingElevator_andCombiner`) and the two combiners that stop the elevator at floor 9 each take a third input by a fixed-width edit (input count 2 → 3, one of the seal toggle's smoke-emitter links repointed to it), so he appears only after a five-disc seal; the seal's tests must stay, so the field's own curve opens the way instead, and the player must touch the seal with all five before he appears.<br>• **The owner** (D201): his room can't softlock the player; the bridge-end cutscene drops the player into d2, which can't be left until the keys (the six lenses) open the tower door back into d1.<br>• **What opens** (78 pool spots, all after the five discs today): d1 37 (3 `key_diamondbattery` r2147, r2169, r2193; 2 `all_fuel` r1104, r1624; 15 clusters; 17 gems); d2 41 (6 `key_lens` r3045–r3055; 3 `all_fuel` r3660–r3664; 2 clusters; 30 gems with the vat gems, D123). No power, fragment or obsidian. Keys stay vanilla (I-9), so 69 spots fill, 5 of them non-gem. Besides the seal they need air, water, fire and earth 3 (the conservative kit on d1's elevator floors and d2's climb), d1's acid blocks (earth 3, water 3) and ice block (fire 3, water 3), air 3 from d1.Z018 to the bridge, the three battery keylocks (they key the elevator switches switch4, switch7 and switch9; switch9, on floor 11, is the keyed way to floor 9) and the six lenses.<br>• **Logic** [verified: the solver on a copy of the database with the seal and town's d1 exit set to `true`]: d1's entry `true` (town's exit loses its migrated clause, four discs and the kit, which is logic only); the seal a touch; `d1.spideyzar.killed` needs the five discs at 4 as well as the kit (today the kit alone, so with the seal open victory held with no fragment); victory stays that flag, terminal (reach only). The bridge end is the no-return edge: with all but the fragments d2's arrival is safe, and with any element at 2 it is a trap; the exits-only escape (§2.13) already follows the drop and the lens door, the trap gate would count it among vanilla's own traps under the same options [inferred], and nothing is forfeitable (the lenses are inside d2, §2.13 rule 2). Missing: the setting-dependent seal and town requirements, d2's real climb (assumed at the kit), and the bridge-end field, modelled as an optional exit though it fires on a touch [inferred]. |
| **R2.13** | A randomized starting world state (D216): events done or not, such as w1's toppled tower, melted ice, machines on, opened doors | the event writes per level (the same node-section writes as R2.3); a requirement that depends on a setting (as R2.12) | D216 (owner, 2026-10-15: "I wonder if we should also support randomizing world state as an option one day."). With R2.9's starts, D192's object shuffles and D214's barrier option. |
| **R2.14** | A "warp in logic" setting: the save-point warp (R2.1, D202) counted by the logic, relaxing D81's no-return rules (a trap left by the warp is no trap) | R2.1b's checks passed; the spoiler and the trap gate read the setting | D202's recommendation. Off by default: the warp stays out of logic. |
| **R2.15** | Time-savers in the spoiler, and hints (D189: not in v1) | tricks.toml's `[[time_saver]]` tables (D145, read since R1.4b, never in logic); for in-game hints, the hub's helpnode panels (HUB_MINING HM-86) | A spoiler section lists each time-saver a seed's route can use; hints redraw existing `helpnode` popups. AzurKit 4.10. |
| not planned | Multiworld / Archipelago | AP is Python 3.11–3.13 only, and an in-game client would be needed | An apworld could later emit AzurKit's plan JSON. |

**R2.1a (2026-10-15): built and seen in xemu** as the opt-in pack `qol_save_warp` (USA; `docs/PATCHES.md`; VAs in `docs/RE_XBE.md` § "Save points, level requests and arrivals"):

- **The trigger is a fixed input, not power selection** (refinement 1). Selecting a power needs it: 0x83410 sets an element's bit only when its level and its fuel are both above 0, so a new game selects nothing. The ritual is LT held while each of A, B, X and Y is pressed (the four elements' buttons), tracked by the shim from ControllerState, so it works with no powers owned. On firing, the shim clears `armor_mgr`'s mask (+0x10) and LT byte (+0x0C) and keeps +0x0C clear until LT is released, so the gesture neither casts the selection nor drops the worn armor (a release with an empty mask drops it, 0x837A0).
- **"On a save platform"** is no flag in code (touching the platform posts a save request through its `gameSaveControl`, 0x70F90). The shim computes it: the body centre (critter +0x15C) within about 1.5 m of a save point of the current level, each save point's place built as 0x70F90 builds it (the nodes from world +0xDC, slot 15 of each node). The radius is 2 m across and 3 m in height; in xemu the body stands 0.883 m above the place on every platform tried.
- **The warp** posts a level request (movie "", the level, `startspot`) at request +0x10, as the debug menu's "Change level..." does (0x12A50), so departure and arrival run a level exit's code: the inventory, the level states and the global flags carry over. **The arrival** reuses a save load's: a second hook on the `load_level_from_path` call at 0x55F80 finds the destination's save point by id and points request +0x08 at its place, as `game_start_setup` does for a continue (0x53487). The player tick then places the body there (0x855D0). Town's arrival is its save point `Temple`, so the return ritual can be made at once. The two hooks share no data (each lands its own copy of the object): the ritual hook names the target in the request's spot, `rzwarp:<save-point id>`, which the game's spot lookup doesn't find.
- **One return point, kept in the save** (refinement 2): one dword in the global map (world +0xE4, through 0x5E690) under a name no level uses, holding the row (1-based) of a 43-row table of (level path, save-point id) built from `generated/*.json`; 0 is none. `shared.sav` writes every entry and a load zeroes and re-reads them, so a save and reload between the two warps keeps it and a new game clears it. A ritual elsewhere overwrites it; the return clears it; in town with none stored, nothing happens.
- **Retail saves only on a save platform** (refinement 4) [verified static]: `.text` writes the save request (+0x14) in three places: a save point (0x71083), cheat code 8 (0x16CC8) and the autosave (0x561F1), which is built only while the cvar `auto save on level load` is on (default 0, registered at 0x55FB7, read only at 0x55FC9). Level exits, boss deaths and the disc teleports are levelSwitches, which post only a level request. No sitting watched for an unasked save.
- **xemu** [verified xemu, partly placed]: seen in xemu (sitting r21a, 2026-10-15, (private evidence)): from w1's W1_3 (SaveGame #1's platform) to town's Temple and back, each arrival 0.883 m from the platform's place, as a save load's; the inventory unchanged; a cheat-code save in town, a death and Continue (the save reloaded), then the ritual on Temple back to W1_3; with every element level 0 (poked), both ways; out of d2 from D2_1 (reached by the debug menu's warp and a RAM placement). Walking (here: a placement) onto a platform opens its save popup first, and the ritual waits until it is answered; a warp's arrival opens none. Step R2.1b's build (sitting r21b, 2026-10-16, (private evidence)) [verified xemu]: on USA and on Europe, from W1_3 to Temple and back, each arrival 0.883 m from the platform's place, the inventory unchanged; walked 6.8 m off W1_3, the ritual posts nothing.
- **Cost:** two 5-byte CALL hooks (0x8C2EC on `player_armor_state_tick`, 0x55F80 on `load_level_from_path`), 1,328 bytes of code per hook (1,335 before Step R2.1b) and a 41-row table (every save point but town's and training_room's). **Open (Step R2.1b):** a6 with four fragments and the disc not placed (out before its level-triggered teleport, back in, the teleport still fires); the level flags after a round trip (the warp runs a level exit's code, so they should hold); a real new-game save instead of poked levels; d1's fall into d2 played; a save at a platform rather than cheat code 8. Done by Step R2.1b: Europe in `regions=`, seen in game, and the two vanilla calls through constant addresses (0x5E690, 0xA0620) and the pad's accessor 0xA2FD0 registered in `vanilla_symbols.py`.

**D192** (owner, 2026-10-14): later randomizer versions: (1) shuffle which attack or power each crystal and barrier needs; (2) move barriers, crystals and similar objects to new places.

**D194** (owner, 2026-10-14): a level randomizer may add an entrance into training_room, items inside it, and an exit elsewhere; until then training_room is on neither the maps nor the tracker (Step 2.53).

**D201** (owner, 2026-10-15): an "open death realm" option (R2.12): "Would it be possible to not require the 5 other discs to enter the death realm through d1? And then would it be possible to make spideyzar much much harder (not meant to be beaten) unless if all 5 discs are collected before we fight him? That way we can open the death realm for potential randomization area". Amended the same day, after Step R2.12a's first look: "you can't softlock yourself in spideyzar's room. but, usually when you enter d1, a cutscene plays and you fall into d2, which you can't escape unless you collect enough keys to open the tower into d1. I would prefer to keep spiderzar's health the same but increase the damage and make him super fast". Victory still needs all five discs.

---

## 9. Risks

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| 1 | Node-section RE (I-1) takes longer than planned | medium / low now (I-1 is an accelerator) | Every value it gives can be authored by hand from owner knowledge or xemu, marked [unverified]. The census decoder already reads the records that matter most [verified]. |
| 2 | The engine rejects refs into the padding (I-5 b1, b2) | medium / high | Fallback: majors renamed in place only between unique-string generators, with offsets from vanilla, and gems retyped by repointing. v1 still ships with a narrower pool for majors. Growing the file is not a fallback until XBR section relocation is designed. *R0.5-i: (b2) works, so the fallback isn't needed; ~~the budget beyond +1,024 B per graph is [inferred] (§5.2)~~ R1.10a: the whole gap is the budget, verified to its last byte (§5.2).* |
| 3 | Items at gem spots misbehave (scale, pickup, triggered generators) | medium / low in v1 | By default gem spots hold only gems (RQ-3). I-5(c, f, g) runs before `progression_on_gem_spots` rises above 0. |
| 4 | The key slots (I-9) lose keys when many types are held | unknown / high | If confirmed, keys stay vanilla in v1. *R0: confirmed (a 6th type is refused, I-9); keys stay vanilla in v1 (§2.6).* |
| 5 | Database errors give unwinnable or unfair seeds | high early / high | the vanilla and route-replay checks, invariants, the corpus, read-back, the cron soak with the explorer, xemu spot checks per realm slice, and the spoiler's paths for bug reports |
| 6 | Out-of-logic softlocks under exits-only | **high / medium**. On today's database, 19 of 20 seeds have a reachable dead state [verified DB]. | the trap gate, the danger lists, save advice, the explorer in the soak. R2.1 is the real fix, and no settings claim to be softlock-free before it lands (D144; *was:* no preset). |
| 7 | The 4th-fragment chain misbehaves (an instant teleport on entry, a teleport that fires once, a level lost after completion) | **high until I-7(d–f) and I-16 answer** / high | I-7 runs before 4.10c-iii. RQ-4's default keeps the vanilla 4th at the slot. Forfeitable locations and traps after completion are modelled (§2.9). *R0: I-7 (a, d, e) and I-16 are answered. The chain is level-triggered, but safe after placement; w1 has a touch chain and life has none (§2.9).* |
| 8 | The owner's time: most route knowledge is in his head | high / high | The agent pre-fills everything automatic (R0.6) and drafts the anchors. The owner maps anchors, not 1,418 locations. The vanilla route covers only about 200 non-gem locations. Authoring is one realm per sitting. |
| 9 | Public AzurKit plus generated files carrying about 1,400 game names (§4.4) | medium / medium | RQ-10, decided by Q85 before 4.10b. Ids are already name-free. |
| 10 | Seed drift across Python versions or runtimes | low / medium | Only `random()` is used [verified docs guarantee]. The plan pins the generator version and `db_digest`. |
| 11 | Movement mods silently invalidate logic | medium / medium | the `build()` movement check (§5.3) |
| 12 | Old seeds and the G3 randomizer goldens stop reproducing | certain / low | RQ-6: G3 randomizer parity is retired as an AzurKit oracle, and old seeds are documented as not portable. |
| 13 | Scope creep from the extras | medium / medium | §7 waits until v1 ships, with a cut list (RQ-11). The schema already carries what they need: the cart, uncapped counters and gem thresholds. |
| 14 | 1,418 locations make seeds tedious | high / medium | By default progression never hides among gems (RQ-3); spoiler paths; the skip and movement settings (D144; *was:* presets) |
| 15 | **The trap gate rejects too many seeds** | unknown / medium | Measure it in 4.10e-ii. Options: add the trap to `known_traps` with a warning, or a fill rule that orders entry items after escape items (RQ-11). |
| 16 | **I-7(e) is level-triggered**, so whole guardian levels become forfeitable | unknown / medium | the §2.9 fallback (single gems at forfeitable non-gem spots; obsidians on safe gem spots); fill retries |
| 17 | The escape closure is too slow | medium / medium | the fast path and the SCC cache (§2.13); measured at 4.10c-iii against the ≤ 10 s / ≤ 30 s exit |

---

