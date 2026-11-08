# devkit/sim: the simulator (dev only)

The game's own code under Unicorn, from a build's structure (L0) to its
movement in a running game (L3), with L3's search and trick explorer.
[`docs/SIMULATOR.md`](../../docs/SIMULATOR.md) has the levels, the API, the
xemu validation and the limits. Its modules are Modkit's `azurik_mod/sim`
at its cut (Step 4.13a), their imports pointed at AzurKit's engine through
`ports.py`; `data/` holds the code L2 can't judge (`sim_blind_spots.toml`)
and the kernel's exports L2 and L3 stub (`kernel.toml`).

## `l3-hold`: the snapshots no cleanup deletes

```bash
uv run --locked python -m devkit sim l3-hold [--store DIR] [--checkout DIR ...] [--check PATH ...]
```

A snapshot in the L3 store (`l3-snapshots/` in the user data folder, or
`--store`) is held when it is in a `reach-live` folder (the reach engine's
starts), named by a running process's command line, or the start of a
`proofs.jsonl` record in a checkout (each `--checkout`, by default this
checkout's worktrees). Without `--check` it counts the held snapshots by
why; with it, it names each held snapshot at or under a PATH and exits 1 if
there is one, so a cleanup asks it first. It reads the standard library
only (`$EV/tools/prune` loads the file by its path).

## `conformance`

Re-runs the local L3 conformance corpus offline after an engine change
(Step X.10; [`SIMULATOR.md`](../../docs/SIMULATOR.md)). Every xemu replay of an L3
string (`xemu_oracle.py replay`, the sitting kit's `l3_replay`,
`l3_certify.py`'s replays) is kept in the private store's
`conformance.jsonl`; this runs each string in L3 again from its kept
snapshot and compares the new trace with xemu's per-tick digests.

```bash
uv run --locked python -m devkit sim conformance [--store DIR] [--workers N] [--only LABEL ...] [--disc ISO ...] [--json PATH]
```

- One coordinate-free line per record: its snapshot label and metadata
  hash, mode, ticks, whether it passed then (`passed`, the body centre,
  state and HP equal on every tick, D170) and now (`passes_now`), where
  it diverges now, and the first tick L3's own trace changed
  (`l3_changed_at`); then the counts. Exit 1 on a regression (passed,
  now not).
- `--workers N`: a worker pool per snapshot (`devkit/reach/l3_pool.py`);
  by default it runs in this process. A record whose snapshot is gone is
  counted as `missing`.
- A record keeps the disc in the tray: the snapshot's `iso_sha12` and the
  image's path (AZ-380). A build's record runs on that image's XBE with
  the game's file reads served from it; once the image moved, `--disc`
  names where it is now (matched by sha256[:12]); a record whose disc is
  gone is `missing`, by its sha12 and path. Vanilla's records run on the
  verified ISO, as before.
- Both verdicts compare the CORE digests (body centre, state, HP): AZ-389
  changed the whole observation's (the inventory hash starts past the day
  clock), so an older record's whole digests no longer compare with a new
  trace; `obs_divergence` stays as recorded.
- The corpus is private (a teleport's request in a string holds a
  position); dev tooling, never in pytest (the snapshots are local).

## `explore`

Runs the trick explorer (Step TD.1, D253; [`SIMULATOR.md`](../../docs/SIMULATOR.md)
§ "The trick explorer") on L3 snapshots: one problem, or a batch.

```bash
uv run --locked python -m devkit sim explore run LABEL --level L [--start PRIVATE.json] [--kit air=1 ... | snapshot] \
    [--goal ZONE ... | --location ID [--touch M] | --exit ID] [--sites] [--steps 2000000] [--seeds 1] \
    [--out OUT.json] [--digest]
uv run --locked python -m devkit sim explore bench SPEC.json --out OUT.json [--workers 8] [--digest]
uv run --locked python -m devkit sim explore census LEVEL [--kit air=2] [--runs PRIVATE.json ...] --out OUT.json \
    [--rank]
```

- A problem: a start (the snapshot `LABEL`, a natural start; with
  `--start` a private file holding an R6 `teleport`, as `l3_certify.py`'s
  `x7/<key>.json`, a placed start whose finds are `partial`), a kit
  (element levels set in L3 by R2, 0 for each it doesn't name, so an
  empty kit is kit 0; `snapshot` keeps the snapshot's own levels, AZ-528;
  the air armor cast by input) and a target
  (`--goal` zones or a level-file node, `--location` a pickup by its
  item's own touch: `l3_goal.make_trick_goal`, the light trick graph;
  `--exit` a level exit's trigger, with a cost from out of bounds:
  `make_trick_exit_goal`, Step TD.4b) or none (a discovery problem:
  `l3_goal.make_zone_guide`, novelty picks only); `--sites` adds the
  mined sites' prior (`draft.sites.Prior`); `--seeds` derived seeds to
  `--steps` emulated ticks each. A start from an `x36-*` snapshot, or a
  `--start` file under an `x36-*` folder, is refused before the file is
  read or a pool loads the snapshot (the blind protocol).
- `bench SPEC`: a JSON list of problems (`key`, `snapshot`, `level`,
  `start`, `kit`, `goal`, `location` and `touch` or `exit`, `sites`,
  `steps`, `seeds`, `limits` (e.g. `{"ablate": ["speed"]}`: the pilot's
  ablations, `speed`, `options`, `sites`; any other name is refused),
  `scene` (whole steps), `prefix` (private found files whose strings run
  first, in order: a start chained on them, Step TD.2; each must be a find
  from the spec's own snapshot, kit and mode after the files before it,
  else the bench refuses it by name) and `score`: zones
  whose first reach is reported), each in a process and on
  a pool of its own (a worker per seed, at most `--workers`; its own
  batch token), at most `--workers` workers at once. A SIGTERM or Ctrl-C
  stops every run at its next round and removes the bench's scratch.
  `--digest` adds each run's archive digest (every cell and its two
  strings' hashes: the determinism check).
- OUT: per problem its verdict (`found`, `saturated`, `not found within
  budget`, `inconclusive` when tainted), `partial`, the steps, the found
  string's ticks and sha12, the scored zones' first reach (standing or
  swimming in it: the string's ticks, the steps spent) and per run the cells (place, dynamic), entries,
  pseudo-regions, settles outside every zone, state classes, top speed,
  rise above the start (m), ticks/s, the saturation curve, the faces
  touched, the zone transitions and the saturated regions (counts). A found
  string (`l3.pads` segments, the camera as f32 pairs), the first
  string that stood in each zone (only `score`'s, with one) and opened
  each pseudo-region (a find's seed for its confirmation), the faces the
  runs touched and the trigger, push and damage volumes they entered per
  state class, the faces a find used, the transitions, the
  saturated zones, the zones stood in and the regions visited go to the
  private store's `td1/` (mode 700, files 0600).
- `census LEVEL` (Step TD.4): the level's site miner at the kit
  (`draft.sites.mine`) and census (`sites.census`: per surface class the
  faces, m², share, touched, touched in the class's state, used; per site
  class the sites, m², share, tried (a face touched or a volume entered),
  `unmeasured` (a volume, when a run file predates the volume record) and
  their ids; the exits, those with no logic way in at the kit and of each
  those reached), with the private run files' touches and entries, the
  zones stood in (and those no logic edge enters) and the probe list
  (`sites.probes`: the logic edges out of a saturated zone no transition
  reproduced), written to OUT. `--rank` writes the value ranker's
  queue (`draft.value`) to the private store's `td1/`, never to OUT.
- OUT (`run`, `bench`, `census`; mode 0600) never replaces a file: a
  second run under the first's name writes `OUT.2.json`, then
  `OUT.3.json`, and says so on stderr (`l3.private_out`, Step X.51).

Positions and strings stay in the private store; output is verdicts,
counts, metres, zone ids and hashes. Dev tooling, never in pytest.
