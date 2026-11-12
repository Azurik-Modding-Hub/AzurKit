# devkit/models: the model verbs (dev only)

The `models` area holds the character-body verbs ModelKit's adapter calls,
Modkit's `azurik-mod model`, ported leaf by leaf: `dress`, `inspect`,
`export`, `check`, `import`, `clips`, `chains`, `jiggle`, `pose`, `rest` and
`preview` and `edit`, with the Blender batch and `blender-check` (Blender,
below). Beside it, `fx` (Modkit's
`azurik-mod fx`, whole) reads, plans and clones the fx graphs, and
`weapon-fit` (Modkit's `scripts/weapon_fit.py`) measures the arm turns that
keep a held prop out of a body's chest, and `clip-rest` re-rests a variant's
clip files on the bones its own build places. What they call is the shipped
engine's (`src/azurkit/tools/characters/`); none of it ships.

This page is the authors' how-to as well: a variant made in Blender
(`model edit`, below), how big a body may be, and its LODs. A variant's
recipe fields are [docs/VARIANTS.md](../../docs/VARIANTS.md); making one
with no Blender, in the Variants view, is the guide's
([docs/GUIDE.md](../../docs/GUIDE.md), Characters).

## `model`: a character body's leafs

```bash
uv run --locked python -m devkit models model LEAF [ARGS ...] [--iso PATH]
```

A leaf reads `--iso`'s image, else the one AzurKit finds: `AZURKIT_ISO`, else
`usa.iso` in the user data folder, else Europe's (`devkit/models/image.py`).
`dress` needs a vanilla image (D27: every file a build reads is its
release's), and `check`, `import` and `clips` its vanilla `characters.xbr`
(an edit is made on vanilla); `inspect`, `export` and `chains` read any
image, a build's too, or `--characters` (a built `characters.xbr`: `dress
--out`'s, `import --out`'s). What a leaf writes (`--out`) is a game asset: a
new or empty folder (`pose`'s and `import`'s a new file) outside this
checkout, outside each image's folder and none of the
files it reads (D36); never commit or share it. A leaf prints counts, sizes
and `sha256`, never a byte or a coordinate. A refusal is one `model LEAF: ...` line on stderr and exit 1; a usage
error exits 2.

| Leaf | What it does |
|---|---|
| `dress VARIANT --out DIR [--variant-file PATH] [--recipe FILE] [--ram 64\|128\|256] [--json]` | dresses VARIANT (a built-in, or one of `--variant-file`'s, with `--recipe`'s fields laid over its recipe, `null` dropping one, read as its own) as a build wearing it does, in memory on the packs on by default (a default build's size lines: `--ram`'s machine, 256 with `qol_memory_upper256` on too), its prop and mesh left in its body as its readers read it, and writes the dressed `characters.xbr` and `index.xbr` into `--out` only once the dress passed (D35). It prints the dress's log and the files' sizes and sha256; `--json` one object with W24's mesh plan as numbers (no coordinate), the spring rows' count and the recipe's sha |
| `inspect BODY [--characters FILE] [--memory-budget MIB] [--ram 64\|128\|256] [--json]` | BODY's (a body, or a species, which names the body it wears) bones, markers, each LOD's groups and their budgets, its extent and height, its payloads, its own load runs against the game's load budget (`--memory-budget`'s, else a built image's `default.xbe`'s, else the 42 MiB a build writes by default, D528; the lines of `--ram`'s machine, 128 by default, D588, a built image without its packs keeping its own) and every problem the writer would refuse; exit 1 on a problem or an error, a warning only prints |
| `export BODY --out DIR [--characters FILE] [--clips A,B]` | BODY as glTF 2.0 for Blender: `<body>.gltf`, `<body>.bin` and a PNG per texture, its most detailed mesh, skeleton, skin and clips (all, or `--clips`), turned from z up to glTF's y up at the root; the files are read back and checked against the game's model before they are kept, and the root's extras name the `characters.xbr` read (its sha256, and whether it is vanilla) |
| `export --variant NAME --out DIR [--variant-file PATH]` | a variant's textures as its build recolours them (its `colours`): one PNG a material row its LOD 0 draws with a texture, `<NAME>_row<R>.png`, at the texture's own size, of its base's body in the image (or for a recipe whose build changes the body, its `mesh`, `textures` or `texture_scale`, the body `dress` dresses before its colours: minutes for booblord), written once every row is made; each row's file and sha256 printed. An edited one, beside the recipe, is its row's first `colours` op: `{"row": R, "ops": [{"op": "png", "file": ..., "sha256": ...}]}` ([docs/VARIANTS.md](../../docs/VARIANTS.md)) |
| `check BODY FILE` | runs every check a build runs on FILE (a `.glb` or `.gltf` `export` wrote and Blender moved vertices of) against BODY's vanilla mesh: the vertex ids (`_AZ_VID`, else Blender's `TEXCOORD_1`), the skeleton and the mesh frame (glTF's y up or the model's z up), the triangles, UVs and skin unchanged, no seam torn; prints how many vertices it moves (copies merged), the normals recomputed, who wears the body and the recipe row with the file's sha256 for a variant's `"mesh": {"gltf": ...}`. Writes nothing |
| `import BODY FILE [--weights] [--out FILE]` | imports FILE (new, moved or deleted vertices and triangles, new bones, painted weights) onto BODY's vanilla mesh, matched by its bones', materials' and vertices' names and ids, through the writer (new strips, a group past 31 bones split, the file grown in place); `--weights` takes only the skin weights onto the same topology. Prints what it kept, changed, added and removed, the groups written and the recipe row (`"import": "topology"` or `"weights"`); `--out` (a new file) writes the edited `characters.xbr` whole, for `inspect` and `preview` |
| `clips BODY FILE [--clips A,B] [--out DIR]` | reads FILE's animations (all, or `--clips`) as BODY's clips: each channel on a bone's node (a `<bone>__scale` helper's scale its bone's) becomes the clip's tracks (CUBICSPLINE as it is, LINEAR as straight runs, STEP held), thinned within the engine's tolerance; an animation `export` wrote comes back byte for byte, a changed one keeps its clip's marker tracks, and every clip's pose is checked against the file's. A clip of that name is replaced, any other added under the body. Prints each clip's tracks kept and made, its keys before and after thinning, its size and its root's travel, and a `gltf` clip's recipe row each; `--out` gets the edited `characters.xbr` and `index.xbr`, written once every clip is read |
| `chains BODY [--characters FILE] [--json]` | BODY's bone chains a variant's `jiggle.springs` rows could swing on X41 (D536): its hair and cloth (loincloth panels, booblord's sash and tabard, straps), found by their bones' names; per chain its links (each one's length and mass: the LOD-0 vertices it weighs at 0.25 or more), its tip and the clips keying its first link; then the rows a recipe would need, one a link that weighs a vertex, with a starting spring of its kind to tune with `jiggle --set` (a cloth link walled 5 mm off its clip's pose), against the 32 rows X41 holds |
| `jiggle VARIANT [--variant-file PATH] [--strength X] [--stiffness X] [--hz 30\|60] [--clip NAME\|all\|none] [--set ROLE.FIELD=VALUE ...] [--ram 64\|128\|256] [--json]` | dresses VARIANT as `dress` does (writing nothing) and drives the twin of X41's springs (`jiggle_rt`) with it: the physics scenarios (idle, the walk slot at three speeds, the run, a start, the stop, a jump, a drop, a spin, a knockback, a place, a swim stroke), then every slot's clip at the rate the game plays it (`--clip` one, or none), the climb loops in place and carried; per run and spring row the peak offset per axis (mm as drawn), its radius, the largest move in a tick and the ring's extrema, then each acceptance target pass or FAIL, the other `--hz` run for the rate target. `--set` tries a spring value without editing the recipe and prints the springs as recipe JSON to paste; the sliders take any finite number (D23). It can't run the engine's glides or aligned moves: xemu judges those. A variant with no spring row exits 1 |
| `pose VARIANT --out FILE [--variant-file PATH] [--recipe FILE] [--clips A,B] [--hz 30\|60] [--strength X] [--stiffness X] [--ram 64\|128\|256]` | dresses VARIANT as `dress` does and plays each of `--clips` (default every slot's clip) as `jiggle` plays it, X41's springs over the engine's pose, and writes `--out`, a new `.npz` (written whole, D35): `bones`, `parents`, `inverse_binds`, `sprung`, `clips`, `rates`, `loops`, `carried` and per clip i `now<i>`, `time<i>` and `worlds<i>` ((ticks, bones, 4, 4): the model frame, z up, column vectors, so a vertex skins as the sum of weight x `worlds[bone] @ inverse_binds[bone]`), then `hz`, `strength`, `stiffness` and `drawn`. A variant with no spring row exits 1 and writes nothing |
| `rest VARIANT --values FILE --out DIR [--variant-file PATH]` | prepares VARIANT's mesh once on its base's vanilla body (its subdivisions, hems, islands, tubes and cuts), then runs each `--values` item's `mesh` (a JSON list of objects with a `mesh`: a recipe's or a ModelKit round spec's) through the build's position steps on that frozen mesh, and writes `--out/<i>.npy`, float32 (vertices, 3) as the build writes them, for ModelKit's shape sliders; VARIANT's own values give its plan's positions exactly. An item whose ops aren't VARIANT's in order with the numbers the preparation laid is refused by name and nothing is written |
| `preview BODY --out DIR [--views A,B] [--clip NAME [--time S]] [--size PX] [--engine workbench\|eevee] [--lod K] [--hide ROW,..] [--characters FILE] [--blender PATH]` | BODY exported (with `--clip`, posed at `--time` seconds; else its bind pose) and rendered by headless Blender: one orthographic PNG a view (`front`, `back`, `left` (her own left), `right`, the four diagonals, `top`, `below`; default `front,left,back,front_left`), framed on the posed mesh's drawn vertices, the body's own textures on it (`workbench`, the default: textured under studio light; `eevee`: its materials under a sun and a fill), `--size` pixels a side (768), as `<body>_<view>.png` with `<body>_views.json` (each view's file and the frame's size). `--hide` leaves out a material's faces (`row3`: the townswomen's vase). `--lod K` draws the body's LOD K (a vanilla one, or one a build wrote: the shadow LOD) framed on its LOD 0 posed and cut the same way, so each LOD has LOD 0's camera and light, as `<body>_lod<K>_<view>.png`; a LOD the body lacks exits 1 naming it. Female_2's four views take about 7 s |
| `edit BODY --work DIR [--variant NAME] [--variant-file FILE \| --from BUILTIN] [--base SPECIES] [--weights] [--clips A,B] [--headless [--script PY]] [--blender PATH] [--no-preview] [--build OUT.iso] [--ram 64\|128\|256]` | one verb from the vanilla body to a built image through Blender (`devkit/models/edit.py`; `devkit/models/blender/edit_session.py` runs inside Blender). It exports BODY (a species, or a body with `--base`) and only the clips `--clips` names into `--work` (a new folder outside the checkout and the images' folders, or one an earlier `edit` stamped for the same body, image, variant and import), opens it in Blender as `--work/edit.blend` and reads each save (`edit.glb`: what is seen, modifiers applied, every action) back in a pass: imported onto the vanilla body as the recipe's `mesh.gltf` (`import` topology, or `--weights`) with the recipe's ops after it, as W24 builds it, its actions as clips (`clips`, thinned and refused past their tolerance; an action of one of the body's own clips that no recipe column plays is named and left out: rename it or play it in a column), into `--work/pass-<k>/characters.xbr` and `index.xbr`; `inspect`'s budgets and problems on the body as its build leaves its LODs (worn by the player, W39's LODs and switch distances, W36's shadow LOD), its own runs with what a build of the species bakes onto it (measured once), against `--ram`'s lines, a row a LOD; `preview`'s pictures into `--work/previews/<k>/` (not with `--no-preview`); a row in `--work/log.jsonl` (sha256, counts, budgets, problems, or the refusal) and `--work/recipe.json` (read again first, so an edit made to it during the session stays: its `mesh.gltf` the save and a `gltf` clip row per action, every other key kept). A refused pass is logged and the session goes on. The recipe starts from `--variant-file` (read, never written; the files it names copied into `--work`), `--from BUILTIN` (its WAVs and clip files copied in, a weapon over its moves left out) or `{"base": SPECIES, "mode": "own"}`; `--variant` names it (a built-in's name is refused). Interactive, Blender opens with your own preferences and the session ends when it closes; it refuses to start under `$CLAUDECODE` or `$PYTEST_CURRENT_TEST`. `--headless` runs `--background --factory-startup`, `--script` (a bpy script) after the import, one save, then quits; a script that raises, or a run that saves nothing, exits 1 with no pass and no build. `--build OUT.iso` (new, outside the checkout and the images' folders) builds the last passing recipe with the sdk (`sdk.build`: the packs on by default for `--ram`'s machine, the character the recipe's variant as its `variant_file`, its combo chaining on a hit, a build's default) and prints its `Player model status` line |

`dress` is the dress a build plans (`tools.characters.dressed`, the swap's
own, which the plan calls and G3's goldens pin), over the default packs'
layers, so a sculpt round's candidate is dressed as the build that wears it
would dress it. `export` and `inspect` read its files with `--characters`.

## `model edit`: a variant made in Blender, pass by pass

```bash
uv run --locked python -m devkit models model edit town_female_2 --work DIR --variant mylord [--build OUT.iso]
uv run --locked python -m devkit models model edit town_female_2 --work DIR --variant-file seed.json --headless --script make_jab.py
```

BODY is a species (`town_female_2`) or a body with `--base SPECIES`.
`--work` is a new folder outside this checkout and the images' folders, or
one an earlier `edit` made for the same body, image and variant, to carry on.
It exports the vanilla body into `--work/export/` (with the clips
`--clips idle,walk` names, as a start for your own actions; none by
default, since Blender keys every frame of every clip it saves), opens it in
your Blender as `--work/edit.blend` (`devkit/models/blender/edit_session.py`
runs inside it) and reads every save (Ctrl+S) back in a pass:

- the save (`edit.glb`: what is seen, modifiers applied, every action)
  imported onto the vanilla body as the recipe's `mesh.gltf` (`import`
  `topology`, or with `--weights` only the painted skin weights), the
  recipe's `ops` after it, as a build makes it, into
  `--work/pass-<k>/characters.xbr` and `index.xbr`;
- each action as a clip (`clips`: thinned, its keys, size and how far its
  root moves); an action of one of the body's own clips under its own name
  that no recipe column plays is named and left out (a build stores a
  recipe's clip as `v/<name>`, which only a column plays: rename the action
  to make it a clip of your own);
- `inspect`'s budgets and problems, its own runs counting what a build
  bakes onto the body, on the body as the build leaves its LODs (a row a
  LOD), against the lines of `--ram`'s machine (128 MiB by default);
- `preview`'s pictures in `--work/previews/<k>/` (not with `--no-preview`);
- a row in `--work/log.jsonl` (sha256, counts, budgets, problems, or the
  refusal), and `--work/recipe.json` updated: its `mesh.gltf` the save and a
  `gltf` clip row per action, every other key as you wrote it (it is read
  again at each pass, so you can edit it while Blender is open).

```
pass 1: 3427 vertices, 5151 triangles, 6 groups, 93 bones, own runs 2.418 MiB as built (2.047 of it
what the build bakes); vertices 2884 kept, 543 changed, 0 added, 0 removed, clips jab; recipe
recipe.json written
```

A save the import refuses (a material that isn't the body's, a new vertex
with no weight, a budget past its error) is logged and named, and the
session goes on: fix it and save again. Closing Blender ends the session.
The edit is always of the vanilla body with the recipe's ops after it. The
recipe starts from `--variant-file` (read, never written; the files it
names copied into `--work` from beside it), `--from BUILTIN` (a built-in's,
its WAVs and clip files copied in; a weapon over its moves left out, so a
copy of booblord swings her own spins) or `{"base": SPECIES, "mode":
"own"}`; `--variant NAME` names it (a built-in's name is refused). An
action's name is the clip's: lower-case letters, digits and `_` (`jab`, not
`Jab` or `Action.001`).

Interactive, Blender opens with your own preferences, and `edit` refuses to
start under `$CLAUDECODE` or `$PYTEST_CURRENT_TEST`. Agents and tests run
`--headless --script my_edit.py`: Blender in the background (`--background
--factory-startup`, once one of the machine's Blender slots is free), the
bpy script after the import, one save, then it quits; a script that raises,
or a run that saves nothing, exits 1 with no pass and no build. `--build
OUT.iso` (a new file outside this checkout and the images' folders) builds
the variant when Blender closes, if the last pass passed, from the same
release's vanilla image (`--iso` Europe's builds Europe), as

```bash
azurkit build --iso VANILLA.iso --out OUT.iso --character '{"species": "mylord", "variant_file": "DIR/recipe.json"}'
```

does: the recipe's other files (WAVs, PNGs) are read beside it. Exit 1
names a refusal before Blender opens, or the build's. To keep the variant in
your library instead, make the session there (`--work
"<data folder>/variants/mylord" --variant mylord`, the data folder AzurKit's
user data folder, or `$AZURKIT_VARIANTS`): once a pass has written its
`recipe.json`, the app's Characters tab lists mylord under Yours, the
Variants view edits it and a build reads that file.

### An action as an attack

A Blender action plays in an attack column through the recipe. In
`--work/recipe.json`, beside the row the pass wrote:

```json
{"mylord": {"base": "town_female_2", "mode": "own", "markers": ["m_damage"],
  "clips": {"jab": {"generator": "gltf", "file": "edit.glb", "sha256": "<the pass's>", "animation": "jab",
                    "active": [0.30, 0.45], "box": {"centre": [0.0, 0.5, 1.1], "half": [0.35, 0.35, 0.35]},
                    "rate": 1.25}},
  "columns": {"basic1": "jab"}}}
```

- `active` is the hit window in **clip seconds, not frames** (Blender's 24
  frames a second: frame 7 is 0.29 s); `box` the hit box's centre and half
  size in model units (the body's frame: x right, y forward, z up; `inspect`
  prints the mesh's extent). They come together; a body without `m_damage`
  needs `"markers": ["m_damage"]`. Without them the clip keeps the hit box
  of the body's clip of the action's name (an edited `attack_1` keeps
  attack_1's); a new action with neither can't be an attack, and the build
  says so.
- `rate` is the column's playback rate (1.0 plays the clip in its own time;
  the attack-speed multiplier multiplies it).
- `columns` names the attack columns that play it (`basic1`, `basic2`,
  `basic3`, `finish`, `sweep1` ...; never the roll).
- Keep the body in place: the game moves a body by its `m_feet` marker,
  which a new clip lacks, so a root bone that travels more than 10 % of the
  body's height is refused.
- A clip poses only the bones it keys: every other bone rests at the bind
  pose (arms straight out), so key each bone the move should hold;
  `preview --clip` shows the pose first. A bone's length runs along its
  local X, so turning a limb about X twists it in place: swing it about its
  local Y or Z.
- A recipe's attack columns are its moveset: a weapon picked for it plays
  its own moves in every column (your mesh, jiggle and sounds kept), so a
  recipe that names its own `weapon` names no `clips`, `columns`, `carry` or
  `held` unless they are a moveset weapon's.

The same row works in any recipe file: `clips BODY FILE` prints it for each
animation of a `.glb`. A column that plays the base's own life drain takes
life from the one critter it picks, or with `"drain": {"targets": "all"}`
from every critter its box touches.

### Hair that swings

A body `src/azurkit/tools/characters/chains.json` lists swings its hair on
the game's live springs (X41) whenever the player wears it with no `jiggle`
of its own: the girls' ponytails (`townspeople/girlchild_1` and `_2` and
both farmer girls), the townswomen's tails (`townspeople/female_1` to `_4`)
and Balthazar's five locks (`balthazar_airship`), and so every species and
variant that wears those bodies. A recipe with a `jiggle` takes none of
them: copy its body's rows into `jiggle.springs` (`chains BODY` prints a
starting set) and tune them with `jiggle --set`. A character's
`"jiggle_strength": 0` keeps the hair as the moves pose it.

## How big a body may be

The game reads every archive in load runs (a page-aligned entry and the
entries that start in its page, as one block) into one load budget, 40 MiB
in vanilla, shared by the level, the characters, the effects and the
interface, and the player's body runs stay loaded in every level. Measured
in xemu at nine saves on a 128 MiB machine (a few fresh loads on a retail
64 MiB one too, alike), at the 40 MiB budget, a1's save the tightest; the
inventory screen loads its textures while it is open:

| A player build's own runs | What the game does |
|---|---|
| up to 10 MiB | every save loads at full detail, and a1's, w1's and e2's inventories draw whole |
| 10-12 MiB | on a load, a1's save fills the budget and drops some of the level's cache, still at full detail with its inventory whole |
| 12.67 MiB | the largest measured whose a1 inventory stays whole in play |
| by 15.79 MiB | played from a1's save, the inventory screen loses pieces, silently; a fresh load there is still at full detail, and w1's and e2's inventories stay whole |
| by about 17.7 MiB | loaded from a1's save, the tree has lost its leaves' textures, silently |
| by about 20.9 MiB | loaded from w1's or e2's save, the save platform has lost its grille |
| past about 23.1 MiB | the change to e2 by the debug warp hangs on "Loading..." |

A build's own runs hold the clips it bakes onto the body (Garret's moves on
its rig: up to 3.8 MiB by species and mode), the player's projectile
(`characters/debug` and all under it, which his throws load: about 0.1-0.6
MiB) and each shield or beam row's own graph; `inspect` of a file no build
made says what it lacks. The pack `qol_memory_budget`, on by default,
raises the budget to 42 MiB, and the build reads the budget from the
`default.xbe` it built: at 40 MiB it refuses a body past 12 MiB and warns
past 10, at 42 or more past 14 and 12 (a lower budget lowers them). Past 42
the game's own memory check cuts the budget back at the tight level
changes, so the lines don't follow it there.

Every build is one for a 128 MiB machine by default (xemu at `mem_limit`
128): with `qol_memory_upper64` and `qol_memory_upper64_gpu` (both on by
default) the level's and the body's load runs go above 64 MiB, and the
build refuses a body past 49.5 MiB, or one whose largest single run (its
mesh, as a rule) passes 42.34 MiB, and warns past 38 (at the 42 MiB budget;
a lower one lowers all three). Without either pack, or for a 64 MiB machine
(a character's `"ram": 64`, `--ram 64` here), the 64 MiB lines hold. The
bytes are the same either way, so **a body past 14 MiB plays right only at
128 MiB**: on 64 the packs do nothing, and it loses pieces and textures,
and a larger one hangs loading (real 64 MiB hardware unmeasured). Measured
in xemu with both packs, played at a1, w1 and e2:

| Own runs at 128 MiB | What the game did |
|---|---|
| 15.88-38.79 MiB | played, the body's mesh run above 64 MiB |
| past 38 MiB | the build warns |
| 48.49-49.49 MiB, a mesh run of 41.45-42.34 | played every level whole (USA and Europe), its frame rate held in real time |
| past 49.5 MiB, or one run past 42.34 | the build refuses the body |
| 50.34-61.13 MiB, a mesh run of 43.11-52.85 | never finished loading the save: the run fits no span above 64 MiB |

A build with the pack `qol_memory_upper256` too (off by default; xemu only,
at `mem_limit` 256; `--ram 256` here) is one for a 256 MiB machine: it maps
the RAM from 128 to 256 MiB as a third tier, where a mesh run too large for
the room below 128 MiB goes, so, unlike 64 and 128, it changes the bytes.
It refuses a body past 127 MiB, or one whose largest single run passes
113.53 MiB, and warns past 48 MiB, where the frame rate was last seen whole.
Measured: 49.25-105.37 MiB played (mesh runs of 42.34-92.91), 128.21 MiB
played but ran w1 at 19.6 fps against vanilla's 30, and 145.27 MiB never
finished loading (its run fits no tier).

`inspect`, `edit`'s passes, `jiggle` and a build weigh a body against the
same lines, 128 MiB's by default. A run's own size is no limit, and the
writer splits a group at the format's limits by itself (31 bones, 65,536
vertices, 22,392 B of push buffer: vanilla's largest), so the budget is a
total no split shrinks. Europe has the same budget and files. xemu doesn't
model the graphics chip's time: the heaviest body measured (1,320,358 LOD-0
triangles, 47.00 MiB of own runs) drew 22 times vanilla's heaviest frame's
triangles at a1 and real-time xemu still held vanilla's 30 fps there. A
frame past vanilla's heaviest is a warning in its sitting, never a refusal.

### LODs

`inspect` lists each of a body's LODs: its triangles and their share of
LOD 0's, its push bytes, its `bmsh`'s bytes and its own runs, and for each
species that wears the body where it switches. The game aims for LOD k
past the k-th of the species' `lodThreshold1`-`4`, culls past its
`farClip`, never draws LOD 5 and on, and fades the last LOD of a switch
over half a second, drawing two at once (`tools/characters/lods.py`). A
species with a `shadowSize` and no `shadowTextureName` casts a realtime
shadow drawn from the body's LOD 1 (LOD 0 if it has one); a LOD no wearer's
distances reach and no shadow draws is never drawn, a warning. garret4,
the player's species, switches at 1000 m, his `farClip`, so any body the
player wears stays at LOD 0 on screen, and his realtime shadow draws its
LOD 1. The game loads every LOD of a body, drawn or not.

- A one-LOD body the player wears past 20,000 triangles builds with a
  shadow LOD: a LOD 1 cut coarse from LOD 0 (within 2 cm) that only his
  shadow draws, so the body is drawn once a frame at full detail, not
  twice (a recipe's `"lods": {"shadow": false}` keeps it off).
- A recipe's `"lods": {"ratio": [...], "at": [...], "error_px": p}` cuts
  the body's LODs past LOD 0 anew from its final LOD 0 (its seams, UVs and
  palettes kept) and sets garret4's switch distances to `at`, so the
  player draws them as the camera pulls out; his shadow draws the same LOD
  1. `"ratio": []` drops a body's LODs past LOD 0. A `mesh` may edit a body
  with LODs of its own (catalisk, the golem): with no `lods` the build cuts
  them anew from its edited LOD 0 at their vanilla shares of its triangles.
- `preview --lod K` draws LOD K alone in LOD 0's frame (the same camera and
  light): a vanilla one, or one a build wrote (`--characters`).

## `fx`: the fx graphs' leafs

```bash
uv run --locked python -m devkit models fx list --match balthazar     # named graphs: archive, TOC, records, size
uv run --locked python -m devkit models fx show characters/balthazar_airship/fx/fx_default --record 35 [--json]
uv run --locked python -m devkit models fx closure characters/balthazar_airship/fx/fx_default   # index, tag, size, sha12
uv run --locked python -m devkit models fx texture characters/balthazar_airship/fx/fx_default --record 35 --png OUT.png
uv run --locked python -m devkit models fx templates                  # the named grafts and the effects templates
uv run --locked python -m devkit models fx plan --player-character beamlord [--player-variant-file RECIPES.json]
uv run --locked python -m devkit models fx clone fx/magic/fx_shield_electric1 --as fx/magic/my_shield --edits EDITS.json --out DIR
```

The fx graphs of `characters.xbr` and `fx.xbr` (`devkit/models/fx.py`),
read from `--iso`'s image, else the one AzurKit finds, as `model`'s are;
`--archive characters|fx` where a key could be either's. Each leaf prints
names, decoded numbers, sizes and sha256[:12], never a byte; a refusal is
one `fx LEAF: ...` line on stderr and exit 1, a usage error exit 2.

| Leaf | What it does |
|---|---|
| `list [--match TEXT]` | the named graphs: archive, TOC index, key, records and size |
| `show KEY [--record N] [--json]` | each record (type, parent, inherit mode, bind name, attributes by the XBE's names, a pSystem's renderer and components and a pBurstEmitter's targets), its links (plugs by name, weight, factor, curve) and what it draws: meshes with their material rows (blend, opacity, alpha reference, flags and stage textures), textures with format, size and frames, a shader's material row |
| `closure KEY` or `closure --toc N` | what a graph (or a TOC entry) reaches through relocated fields: each entry's index, tag, size and sha256[:12] |
| `texture KEY --record N --png OUT [--stage K] [--frame F]` | a renderer's texture or a platform material's `--stage` (an animated list's `--frame`) decoded to a PNG, for a recipe's `texture` `png`; OUT is outside this checkout and the images' folders (D36), a game asset: never commit it |
| `templates` | the named grafts a recipe's `fx_grafts` take (each record) and the effects templates (group, engine, anchor, sets, body, impact, hit, params with their ranges, colour; a shield's or beam's holder, bound to m_root or placed by the build, and its turn), with the shape of a recipe's `effects` row |
| `plan --player-character NAME [--player-variant-file FILE]` | a variant's (or a species' W23 overlay's) player clones built in memory, its `fx`'s (X40) and its `fx_ring.stand.fx`'s (X38's stand key): their records, edits, grafts and every new entry with its size; each `effects` row: a projectile's template with its sha, columns, values and colour, the body `debug` wears for it, its scale, the textures recoloured, the sets grafted into its fx, its break, its hit and the entries it appends (W30, X42); a shield's or beam's own graph on X38's bound key, its records and grafts, its holder bound to m_root or left where a build places it, its show writes, fade and tail (a `range` `auto` at its default); or the refusal. It writes nothing |
| `clone KEY --as NEWKEY --out DIR [--edits FILE] [--allow-modded-input]` | `DIR/gamedata/<archive>` and `DIR/gamedata/index/index.xbr` with KEY's clone added under NEWKEY, `--edits` (`{"fx": [...], "fx_grafts": [...]}`, as a recipe's) made on it and every vanilla payload kept; DIR is a new or empty folder outside this checkout and the images' folders (D36), and the archive must be a release's vanilla one unless `--allow-modded-input` (D27). `core.iso`'s `read(files=)` and `pack` lay the folder into an image |

A graph under a new key plays only when something loads it: a variant's
player clone (X40), or an `effect` record naming its key.
## Blender

Blender is a machine tool, never a dependency, and never ships: `preview`,
the batch (`devkit/models/blender/batch.py`) and `blender-check` run it, and
the scripts in `devkit/models/blender/` run inside it. Blender 5.2.2 is the
one they were measured on. Each run is headless (`--background
--factory-startup`: no window, the user's preferences untouched), and is
found as `--blender` (`blender=`), else `$AZURIK_BLENDER`, else `blender` on
`PATH`, else `/Applications/Blender.app`'s. No test runs a real Blender: the
suite's stand-ins write what it would (`tests/test_blender.py`).

**Many pictures from one Blender** (a clip's strip or MP4, a sculpt round's
sheets) go through the batch:

```python
from devkit.models.blender import batch as bb
body = bb.Body(points, uvs, triangles_by_material, textures)   # uvs v up: a game UV's 1 - v
got = bb.render(body, positions, normals, views=[[bb.View(150.0, 1.7, (0.0, 0.0, 1.12))]],
                keep=beats, mp4=out / "walk.mp4", fps=15, log=out / "render.jsonl")
```

One Blender a job: the body and its textures are built once, each frame's
positions (and normals) are set in place, and the frames come back as one
array (those `keep` names) and go straight into ffmpeg (`mp4`, which needs
ffmpeg on `PATH` or `ffmpeg=`): no OBJ, PNG or launch a frame. `got.seconds`
(and `log`) hold each stage's seconds. On vanilla female_2 a 61-frame MP4
took 82-121 s through an OBJ and a level-9 PNG a frame and 2.3-3.0 s through
the batch, with 99.8% of the pixels identical to Blender's OBJ import of the
same mesh and the rest a few levels apart. Every refusal is a `ValueError`
naming what failed (D35); a failed job writes no MP4, and an MP4 inside the
checkout or an image's folder is refused (D36).

- **Workbench for previews** (the default, the sculpt rounds' look). EEVEE
  costs about 10 times a frame and Cycles on the GPU about 45; after a
  Blender update, warm Cycles' kernels with one render before parallel jobs
  use it (the first compile took 220 s).
- **Render one loop** of a gait and let the player loop it (`ffmpeg
  -stream_loop`), not three.
- **Stop a superseded preview** before starting the next one.
- **Cache what is built from content:** `bb.cached(kind, name, write)` keeps
  a file (a dressed `characters.xbr`, a rig's glTF export) in the AzurKit
  user cache under a name holding `bb.content_key(...)` of everything it
  depends on, the code included, written by a rename so a parallel job never
  reads half of it; a work folder's name is no key. A file no job used for
  14 days goes at the next miss of its kind.
- **Evidence pictures at PNG level 6:** `draw.png_rgba(img, level=6)`
  (`azurkit.tools.characters.draw`) writes a 448 x 640 frame in about 0.06 s
  against 1.2-1.4 s at 9, which only committed pictures need.
- **At most 8 Blenders at once** on the machine: `render`, `preview` and
  every other Blender job wait for one of `$AZURIK_BLENDER_SLOTS` (8) slots,
  lock files in the AzurKit user cache's `blender-slots/`, the folder
  ModelKit's jobs share, so both repositories' Blenders count against one
  cap. Wrap any other Blender launch in `with bb.slot() as s:` and give it
  `pass_fds=s.fds`, so the slot stays taken while that Blender runs, even if
  its caller is killed. Windows has no `flock`, so no cap there.

## `blender-check`: the batch on the real Blender

```bash
uv run --locked python -m devkit models blender-check [--vertices N] [--frames N] [--engine workbench|eevee] [--blender PATH] [--out DIR]
```

Runs the batch on the real Blender, which the suite only stands in for, on a
made-up body (a textured ball, no game data): `--frames` poses (12; the last
the first again) from two views. It checks that every frame comes back, each
pose draws its own picture and the repeated one the same, the ball is drawn
and textured, a second job finds the body in the cache and the MP4 is
written (with ffmpeg), then prints each stage's seconds; `--out` keeps the
frames' sheet (PNG) and the MP4. Exit 1 names a failed check. Run it after a
Blender update or a change to `batch.py` or `batch_inside.py`;
`--vertices 45000` times a v4-size body.

## `weapon-fit`: the arm turns that keep a prop out of the chest

```bash
uv run --locked python -m devkit models weapon-fit booblord townspeople/male_6 [--write] [-j N] [--iso PATH]
uv run --locked python -m devkit models weapon-fit --all --write -j 8
```

For a body the bake maps (`townspeople/male_6`), or a built-in variant with
a mesh or arms of its own (booblord), swinging Garret's staff moves: the
turn of both `*_arm_1` in each of his attack clips that keeps the held prop
out of its chest, as a row of `src/azurkit/tools/characters/weapons.json`'s
`fits` (`{"clips": {clip: [out, forward]}}`, a variant's with its recipe's
`sha`), which a build turns those arms by (W35). Per target it dresses the
body in Balanced with the Axion staff and with the hoe and, for each of his
clips baked onto it and each turn of out 0, 10, 20, 30 by forward 0, 15
degrees, counts the ticks (30 Hz) on which a prop vertex lies more than 1
cm inside its torso (a townswoman's bust too: `_player_weapons.Chest`), the
worse prop's. Each clip takes the turn with the fewest ticks beyond
garret4's own holding the same prop (his staff reaches into his chest in
attack_3), whose prop dips no lower than min(his lowest, 0) - 1 cm with
either (his staff and the hoe on his chain go under the floor in his
elemental, smash and ledge moves); ties go to the smaller turn, and a clip
no turn improves keeps none. It prints one line a clip and the row, names
and numbers only. On `townspeople/male_6` it gives the shipped row (22
excess ticks unturned, 0 fitted, 3 clips turned) in about 3 minutes.

`--write` puts each row into `weapons.json` (a target with no clip to turn
loses its row, one it couldn't dress keeps its own; nothing is written
unless the file loads after). That file ships and every build reads it, so
a write changes the fitted bodies' builds: re-record the goldens after it
(`scripts/record_goldens.py`). Run it after a change to a mapped body's
mesh, a built-in variant's recipe (its row's `sha` goes stale, and a stale
row turns nothing) or Garret's staff moves. garret4's own reference holds
the hoe as his build does, on its carriers; Modkit's last script copied it
without them and stopped at "garret4 has no bone 'wpn_tip'".

## `clip-rest`: a variant's clips re-rested on its own build

```bash
uv run --locked python -m devkit models clip-rest booblord --recipe pick.json --out DIR [--variant-file PATH] [--iso PATH]
```

A clip file holds every bone's rest, and a build reads it only where each
node's rest is the dressed body's within 1e-5. A variant's jiggle bones sit
where the vertices they take sit, so a reshaped mesh moves them and its clips
stop holding; a recipe's `places` pins them where another mesh's build put
them (booblord_high's are booblord's). `clip-rest` takes VARIANT (a
built-in, or one of `--variant-file`'s, with `--recipe`'s fields laid over
it, `null` dropping one, as `model dress` does) and runs its build's first
stages (W24's mesh, W29's jiggle bones; no paint) twice on the vanilla body:
as its recipe places the bones (where its files hold today) and with no
`places` (where its own build puts them). Then each `.glb` its `gltf` clip
rows name, from its clip folder (a built-in's in the content folder,
`AZURKIT_CONTENT`), gets each jiggle bone's node at its new rest and that
bone's translation keys moved by as much: a key is the bone's place, so its
motion about its rest stays, and a rotation or a scale key is the same at
any rest. A rest that would turn, or a keys accessor another channel
shares, is refused by name.

Before it writes, it reads every animation of each new file on the new body
(the build's own read, with its 1e-5 check) and of the old file on the old
body, and compares them track by track: every bone that isn't a jiggle bone
must keep the old clip's tracks, or it names the clip and bone and writes
nothing (exit 1). It prints each jiggle bone's move (mm), each clip's
tracks compared, each new file's size and sha256 and the `clips` rows that
take them; with them in the content entry, the recipe drops `places`. A
contact clip's hands don't follow the moved bones: a clip whose hand
touches a jiggle bone (booblord's `bust_bounce`, `sash_fix`, `look_back`,
`sit_cross`) keeps its motion, not its contact. On booblord's two files it
takes about two of her body's builds.

## Sculpt rounds (ModelKit)

The owner's private ModelKit repository runs sculpt rounds of candidates
(built, measured, put on a sheet, judged, picked) over these verbs: its
Azurik adapter builds a candidate with `dress`, reads it with `export
--characters`, poses its springs with `pose` and sizes its shape sliders
with `rest`, all in this checkout's own environment, and its Blender jobs
share the batch's slots (above). This repository never imports ModelKit,
and ModelKit holds none of the game's files. How to run a round: its
`modelkit` skill.
