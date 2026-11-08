# devkit/models: the model verbs (dev only)

The `models` area holds the character-body verbs ModelKit's adapter calls,
Modkit's `azurik-mod model`, ported leaf by leaf: `dress`, `inspect`,
`export`, `jiggle`, `pose` and `rest` now; the rest (`check`, `import`,
`clips`, `chains`, `preview`, `edit`, the `fx` verb and the Blender batch)
come with their own steps. What they call is the shipped engine's
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
