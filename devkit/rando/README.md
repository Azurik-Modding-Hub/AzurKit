# devkit/rando: the randomizer database's tools and benches (dev only)

The randomizer's database lives in `src/azurkit/tools/randomizer/data/`: a
generated half, decoded from the vanilla image, and the hand-authored level
files, items, skips, settings and vanilla route. These verbs make the
generated half, check the whole, and measure the planner on it. They are
Modkit's `rando db-extract` and `rando check` and its `rando_bench.py`,
`rando_impact.py` and `rando_soak.py` at its cut (Step 4.13b), their imports
pointed at AzurKit's engine through `ports.py`. `data/` holds the fixture
databases the tests, the impact ranking and the solver's plan corpus run on
(`toydb`, `reachdb`, `escapedb`, `guardiandb`, `impactdb`, and the plans in
`plans/valid` and `plans/invalid`). The reach model's `derive` and `author`
come with the authoring's own step. None of them prints a game byte.

## `db-extract`: the generated level data

```bash
uv run --locked python -m devkit rando db-extract --out src/azurkit/tools/randomizer/data/generated   # refresh the shipped data
uv run --locked python -m devkit rando db-extract --out DIR --iso IMAGE                             # elsewhere; either release
```

Writes `<out>/<level>.json` for the 22 playable levels and `training_room`:
each level's pickup locations (with their yield, cell, save flag and the
file offsets of their name fields), barriers and geodes, key locks and
keylords, town's obsidian locks, seals, save points, exits (with the spot
each one arrives at under the engine's own lookup), spots, teleporter pairs
(with the reset pads each route needs touched first), bosses, latches and
`gameState` links, as `azurkit.tools.randomizer.levels`' rules decode them.
It holds names, ids, counts and decoded values only: no coordinates and no
game bytes. The shipped copy is `src/azurkit/tools/randomizer/data/generated/`,
the same from either release, and
`tests/test_rando_db.py::test_db_extract_writes_the_committed_generated_data_byte_for_byte_from_either_image`
fails on any difference, so a change to the node readers
(`tools/randomizer/art/nodes.py`) or the level rules (`levels.py`) shows as
a reviewed data diff.

- **Input:** `--iso`, else the USA image `AZURKIT_ISO` or the user data
  folder names (else Europe's); it must pass the identity gate, every file
  of it (the data describes vanilla).
- **Output:** `--out` is a required folder (created when missing). It is
  checked before the image is read: none of the files it would hold may be
  a vanilla image or sit beside one or inside an `iso/` folder holding one
  (D36), and an `--out` that is a file is refused. Every level is extracted,
  then written into a temporary folder inside `--out`, before any file is
  replaced, so a failure leaves `--out`'s files as they were (D35). The
  same image gives the same bytes under any `PYTHONHASHSEED`.
- An exit to a level that isn't on the disc (f1's `levelSwitch3`, to `f7`)
  is left out.

## `check`: load a database and say what is open

```bash
uv run --locked python -m devkit rando check                  # the shipped database
uv run --locked python -m devkit rando check --db path/to/db  # another database folder (a copy you are editing)
uv run --locked python -m devkit rando check --json           # the whole summary and every error, as JSON
```

Loads the database with every check of the format (formats, keys, the
requirement grammar, every reference, the bindings of the generated gates,
the declared non-monotone mechanisms (a disc teleport with the one guardian
slot that spends it), that only the victory reads a terminal event, the
skips and their confirmations, `tricks.toml`, the time-savers (never in
logic), the settings, the route and, once all of that passes, that the
start and the hub reach each other with every item) and prints what is
still open: the levels that are stubs, the TODO fields, the pool locations
with no node, the undecoded gates, the proven spots by kind and the
non-gem ones by realm with their total, the skips on at each
`skip_ceiling` from 0 to 4, the time-savers by level, each settings file
with its share string, and the draft route's open references. Then
`errors: N` and one line per error, naming the file, the object and the
field. It reads no game data and writes nothing. Exits 0 with no error, 1
otherwise. A draft level's open fields are counted, not errors; an
`authored` level has none. On the shipped database it counts what Modkit's
`rando check` counted at its freeze (`tests/test_rando_db.py`).

## `bench`: the solver's cost

```bash
uv run --locked python -m devkit rando bench                  # 600 nodes, 3,200 edges, 5 runs, seed 1
uv run --locked python -m devkit rando bench --nodes 300 --edges 1500 --runs 3
```

Times the planner's solver: the load with every check, the compile
(`Logic`) and one reach, the median and the fastest of `--runs` runs, on
the shipped database (with a default-settings plan of `--plan-seed`,
default `42`: the fill, its retries and its verify) and on a synthetic
authored database of the planned size that it writes to a temporary folder
and deletes (one level, `--nodes` rooms in a corridor plus one-way drops up
to `--edges`, 1,418 spots, 12 element powers and 40 buttons, every need
placed before both its ends, so at the default size the vanilla placement
wins). It reads no game files.

**When to use:** a step that changes the solver's cost records its numbers
(at least 2 invocations, with the load) in its commit body; timings are
never a pytest assertion.

## `impact`: rank the unknowns by their effect on the default fill

```bash
uv run --locked python -m devkit rando impact --out DIR                 # seeds 0-49, 12 processes
uv run --locked python -m devkit rando impact --out DIR --db devkit/rando/data/impactdb --seeds 0-3 --jobs 1
```

Ranks the randomizer's unknowns by their impact on the default fill, to
order the spot proofs and the edge walks in xemu. Over a fixed seed sample
(`--seeds`, default `0-49`), under the database's default settings:

- **spots:** each unproven candidate spot (one a progression item could
  take once proven) is ranked by two cheap proxies, how many failing seeds'
  stuck reaches hold it and which progression items alone on it make it a
  first-sphere spot (collected with nothing else held), then by its sphere
  in vanilla's playthrough; the top `--singles` are pretended proven one at
  a time and the fill re-run on every seed (the gain). A greedy set then
  adds the proof that fixes most failing seeds per round until `--target`
  (99 %) of the seeds fill, `--rounds` or no candidate is left;
- **edges:** each `assumed` edge is removed and the logic recompiled: does
  vanilla still win and collect everything, how many locations every item
  no longer reaches (a cut fails every fill's verify, so its fill rate is 0
  with no run), how many vanilla collects later, and how many proven spots
  the fill's opening loses; the `--edge-fills` other edges with most effect
  get the fill re-run. Edges rank by tier: breaks vanilla, cuts locations,
  lowers the fill rate, changes the playthrough, no effect (it can wait).

It writes `impact.json` and `impact.txt` (the greedy set and the top
`--top` spots and edges, each with its level, its place and why) to
`--out`, and prints each stage's wall time. A place is named from the realm
authoring's node names (`devkit/rando/draft/authoring/`, which the
authoring's step brings; until then by its zones and what it holds).
`--jobs` processes (default 12) each compile the database once and
recompile only with an edge removed; while an xemu sitting waits for a slot
they run one unit at a time (`devkit/xemu/queue.py`'s batch token). It
reads no game files. Its test runs it on `data/impactdb`.

**When to use:** before a spot-proof or edge-walk sitting, and after one
lands (proofs and walks change the ranking).

## `soak`: the seed soak

```bash
uv run --locked python -m devkit rando soak --out "$(mktemp -d /tmp/soak.XXXXXX)"
uv run --locked python -m devkit rando soak --out DIR --seeds 50 --builds 1 --hash-sample 5   # a quick look
```

Fills seeds 0 to `--seeds` - 1 (default 1,000) on the shipped database
under each of three profiles, strict (ceiling 0, `safe`), default (0,
`standard`) and max (4, `frame_perfect`), plus as many seeds whose settings
are drawn from the seed (ceiling and tier uniform; a toggle on each
confirmed skip and each excluded category with chance 1/8; the seed
difficulty stays Any), in `--jobs` spawned processes (default 12; one seed
at a time while an xemu sitting waits for a slot). For each group it
records the plans, the `FillError` rate after the fill's 20 attempts with
each failing seed and its last reason, the independent verify of every plan
(the plan file read back and solved again on a second load of the
database), and the trap gate's retry rate (the attempts it refused, of all
attempts). Then it builds the first `--builds` seeds (default 10) with a
plan of each profile with `azurkit build --seed --share` from the vanilla
image (`--iso`, else the USA one) into a temporary folder: the build's plan
must be the soak's, its logic verified, and the written image read back
against the plan before it is deleted. It re-runs the first
`--hash-sample` drawn seeds (default 50) in two pools under
`PYTHONHASHSEED` 1 and 2, comparing each outcome with the main run's. It
writes `soak.json` (every number and each seed's outcome) and `soak.txt`
(the table it prints) into `--out`, a new or empty folder, and exits 0 when
all of that holds (no verify failure, no cross-process difference, at most
1 % `FillError` for strict and default, every build good), 1 naming each
clause that doesn't. It prints no game bytes (hashes only).

**When to use:** at a step that changes the planner or the data (the run's
table goes in the commit body). It runs locally only. Modkit's full run
took about two hours, most of it the fills, on 24 CPUs under load.
