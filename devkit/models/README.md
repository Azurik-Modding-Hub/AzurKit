# devkit/models: the model verbs (dev only)

The `models` area holds the character-body verbs ModelKit's adapter calls,
Modkit's `azurik-mod model`, ported leaf by leaf: `dress`, `inspect`,
`export`, `jiggle`, `pose` and `rest` now; the rest (`check`, `import`,
`clips`, `chains`, `preview`, `edit` and the Blender batch) come with their
own steps. Beside it, `fx` (Modkit's `azurik-mod fx`, whole) reads, plans
and clones the fx graphs. What they call is the shipped engine's
(`src/azurkit/tools/characters/`); none of it ships.

## `model`: a character body's leafs

```bash
uv run --locked python -m devkit models model LEAF [ARGS ...] [--iso PATH]
```

A leaf reads `--iso`'s image, else the one AzurKit finds: `AZURKIT_ISO`, else
`usa.iso` in the user data folder, else Europe's (`devkit/models/image.py`).
`dress` needs a vanilla image (D27: every file a build reads is its
release's); `inspect` and `export` read any image, a build's too, or
`--characters` (a built `characters.xbr`: `dress --out`'s). What a leaf
writes (`--out`) is a game asset: a new or empty folder (`pose`'s a new
file) outside this checkout, outside each image's folder and none of the
files it reads (D36); never commit or share it. A leaf prints counts, sizes
and `sha256`, never a byte or a coordinate. A refusal is one `model LEAF: ...` line on stderr and exit 1; a usage
error exits 2.

| Leaf | What it does |
|---|---|
| `dress VARIANT --out DIR [--variant-file PATH] [--recipe FILE] [--ram 64\|128\|256] [--json]` | dresses VARIANT (a built-in, or one of `--variant-file`'s, with `--recipe`'s fields laid over its recipe, `null` dropping one, read as its own) as a build wearing it does, in memory on the packs on by default (a default build's size lines: `--ram`'s machine, 256 with `qol_memory_upper256` on too), its prop and mesh left in its body as its readers read it, and writes the dressed `characters.xbr` and `index.xbr` into `--out` only once the dress passed (D35). It prints the dress's log and the files' sizes and sha256; `--json` one object with W24's mesh plan as numbers (no coordinate), the spring rows' count and the recipe's sha |
| `inspect BODY [--characters FILE] [--memory-budget MIB] [--ram 64\|128\|256] [--json]` | BODY's (a body, or a species, which names the body it wears) bones, markers, each LOD's groups and their budgets, its extent and height, its payloads, its own load runs against the game's load budget (`--memory-budget`'s, else a built image's `default.xbe`'s, else the 42 MiB a build writes by default, D528; the lines of `--ram`'s machine, 128 by default, D588, a built image without its packs keeping its own) and every problem the writer would refuse; exit 1 on a problem or an error, a warning only prints |
| `export BODY --out DIR [--characters FILE] [--clips A,B]` | BODY as glTF 2.0 for Blender: `<body>.gltf`, `<body>.bin` and a PNG per texture, its most detailed mesh, skeleton, skin and clips (all, or `--clips`), turned from z up to glTF's y up at the root; the files are read back and checked against the game's model before they are kept, and the root's extras name the `characters.xbr` read (its sha256, and whether it is vanilla) |
| `jiggle VARIANT [--variant-file PATH] [--strength X] [--stiffness X] [--hz 30\|60] [--clip NAME\|all\|none] [--set ROLE.FIELD=VALUE ...] [--ram 64\|128\|256] [--json]` | dresses VARIANT as `dress` does (writing nothing) and drives the twin of X41's springs (`jiggle_rt`) with it: the physics scenarios (idle, the walk slot at three speeds, the run, a start, the stop, a jump, a drop, a spin, a knockback, a place, a swim stroke), then every slot's clip at the rate the game plays it (`--clip` one, or none), the climb loops in place and carried; per run and spring row the peak offset per axis (mm as drawn), its radius, the largest move in a tick and the ring's extrema, then each acceptance target pass or FAIL, the other `--hz` run for the rate target. `--set` tries a spring value without editing the recipe and prints the springs as recipe JSON to paste; the sliders take any finite number (D23). It can't run the engine's glides or aligned moves: xemu judges those. A variant with no spring row exits 1 |
| `pose VARIANT --out FILE [--variant-file PATH] [--recipe FILE] [--clips A,B] [--hz 30\|60] [--strength X] [--stiffness X] [--ram 64\|128\|256]` | dresses VARIANT as `dress` does and plays each of `--clips` (default every slot's clip) as `jiggle` plays it, X41's springs over the engine's pose, and writes `--out`, a new `.npz` (written whole, D35): `bones`, `parents`, `inverse_binds`, `sprung`, `clips`, `rates`, `loops`, `carried` and per clip i `now<i>`, `time<i>` and `worlds<i>` ((ticks, bones, 4, 4): the model frame, z up, column vectors, so a vertex skins as the sum of weight x `worlds[bone] @ inverse_binds[bone]`), then `hz`, `strength`, `stiffness` and `drawn`. A variant with no spring row exits 1 and writes nothing |
| `rest VARIANT --values FILE --out DIR [--variant-file PATH]` | prepares VARIANT's mesh once on its base's vanilla body (its subdivisions, hems, islands, tubes and cuts), then runs each `--values` item's `mesh` (a JSON list of objects with a `mesh`: a recipe's or a ModelKit round spec's) through the build's position steps on that frozen mesh, and writes `--out/<i>.npy`, float32 (vertices, 3) as the build writes them, for ModelKit's shape sliders; VARIANT's own values give its plan's positions exactly. An item whose ops aren't VARIANT's in order with the numbers the preparation laid is refused by name and nothing is written |

`dress` is the dress a build plans (`tools.characters.dressed`, the swap's
own, which the plan calls and G3's goldens pin), over the default packs'
layers, so a sculpt round's candidate is dressed as the build that wears it
would dress it. `export` and `inspect` read its files with `--characters`.

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
