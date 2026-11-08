# devkit/reach: the reach engine (dev only)

Which floors the player reaches from which, by running the game's own
player tick (the simulator's L3) from every floor's boundary. Modkit's
engine at its freeze (D1143), ported whole (Step 4.13d1): `engine/` is the
engine, `native/` its native movement and collision kernel (`kernel.c`,
`controllers.c`) and the kernel's launch backend, `l3_fast.py` FastL3 (its
C step `fastl3_step.c`, its patched Unicorn `unicorn/`) and `l3_pool.py`
the many-at-once L3 pool. `l3-certify`, `l3-contact` and `l3-gate` (Step
4.13d2) are the L3 certification of the randomizer's spots, edges and
skips, its contact flights and the long-replay gate; their xemu side is
`devkit/xemu`'s (the chain driver, the route pilot, the minigames).
[`docs/REACH.md`](../../docs/REACH.md) has the engine, its benches and its
truth set; this page has its verbs, run from the checkout's root (`uv run
--locked python -m devkit reach VERB`). The
simulator's own verbs that run on the pool, `explore` and `conformance`,
are [`devkit/sim`](../sim/README.md)'s.

What it reads and writes, none of it in the repository:

| What | Where |
|---|---|
| Each job's outcome, the plans, targets, zones and censuses | the user cache's `AzurKit/reach-engine/<level>/` (mode 700, files 0600: they hold positions) |
| The kernel's and FastL3's C step builds, the patched Unicorn | the user cache's `AzurKit/reach-native/`, `fastl3-step/` and `unicorn-fastl3/<the patch's sha12>/`, rebuilt on first use |
| The frozen truth set (frames and R's rows) | `reach-truth/<level>/truth/` in the user data folder, read where it is |
| The engine's start snapshots | the L3 store's `reach-live/`, read where they are |
| The levels' reach models | the L3 store's `x7/reach/`, Modkit's pickles read where they are (`models.py`: a fixed module table, any other class refused; a missing one is built beside them) |
| Their route graphs | `x7/reach/routers-azurkit/`, beside them (Modkit's keys stay in its `routers/`) |
| The certification's private starts and kit snapshots | the L3 store's `x7/` (`by-dir/`) and `x11/`, mode 700 |

Cache keys hash the code at its devkit paths (`engine/cache.py`'s
`CORE_FILES`, `native/backend.py`'s `FILES`), so Modkit's records are not
reused: a fresh cache runs every job again. `unicorn/unicorn_fastl3.patch`
is GPL-2, as Unicorn is (`unicorn/NOTICE.md`); none of this ships.

## `native-trace`, `native-check`, `native-census`

Step R2.17's checks of the native kernel (`devkit/reach/native/`: the player's ticks and the game's move code in
C, zig-built, on a level's real triangles; its `kernel.c` header lists what is ported; the reach engine's launch
backend since Step R2.19d, `reach_engine.py --backend kernel`). `native_trace.py` replays
a seeded sample of the bench's cached reach-engine launches on L3 with the game's move internals hooked;
`native_census.py` asks L3's own `collision_sweep` which platforms the game's world holds (the backend's census,
`reach_native.backend.census_of`, which the kernel route makes and caches per snapshot itself); `native_check.py` runs
every traced move and launch in the kernel (with the census's absent platforms left out, the level's push and
water volumes and springboard heights in), grades each launch
AGREE / FLAGGED / SILENT against L3's end and times the kernel. Traces hold positions: private, mode 0600. Dev
tooling: never in pytest, never a CLI verb.

```bash
nice -n 10 uv run --locked python -B -m devkit reach native-trace LEVEL SNAPSHOT N_FAN N_AIM SEED OUT.pkl
nice -n 10 uv run --locked python -B -m devkit reach native-census LEVEL SNAPSHOT CENSUS.json
nice -n 10 uv run --locked python -B -m devkit reach native-check OUT.pkl --census CENSUS.json [--zones] [--out L.json]
```

## `reach-engine`

Runs the exhaustive reach engine (Steps R2.16a and R2.16b, `devkit.reach.engine`;
[`REACH.md`](../../docs/REACH.md)) on one
level, in shadow: L3 launches from every walkable region's boundary,
their edges, closure per kit and verdicts against the level's derived
modelled jump and flap zone edges, hand edges and assumed rows.

```bash
uv run --locked python -m devkit reach reach-engine sample LEVEL --plan NAME [--region N ...] [--targeted] \
    [--no-fan] [--spacing 2.0] [--min-area 4.0] [--limit N] [--refine PLAN ... --snapshot LABEL] \
    [--backstop modelled|all | --pairs [--budget CPU-H] [--slice F] [--truth NAME ...]] [--backend l3|kernel]
nice -n 19 uv run --locked python -m devkit reach reach-engine run LEVEL --plan NAME ... --snapshot LABEL \
    [--workers N] [--per-task 2] [--l3 fast|base]
nice -n 19 uv run --locked python -m devkit reach reach-engine graph LEVEL --plan NAME ... --snapshot LABEL \
    --out EDGES.json [--workers N]
nice -n 19 uv run --locked python -m devkit reach reach-engine diff LEVEL --plan NAME ... --snapshot LABEL \
    --out REPORT.json [--workers N]
nice -n 19 uv run --locked python -m devkit reach reach-engine witness LEVEL --plan NAME ... --snapshot LABEL \
    --out FILE.jsonl [--workers N]
nice -n 19 uv run --locked python -m devkit reach reach-engine rigs LEVEL --snapshot LABEL --out RIGS.json \
    [--workers N] [--truth N] [--deck NAME ...]
```

- `sample`: the plan's jobs (R0's fan: each takeoff, a boundary sample
  every `--spacing` m of each walkable region of at least `--min-area`
  m2, at 3 headings with 14 launches; `--targeted` adds the targeted
  pass's aims at each derived jump and flap zone edge's witness flight:
  its launch straight and curved either way under the predictive landing
  control at the landing moved onto its floor face (at run time onto
  the nearest point of its to-zone L3 stands a body on, where none
  stands at the target), and as R0 flew it, the stick held; while none
  hits, the same again walked at the target once down, then steered
  1.5 m short of it, then the certificate's aims at 12 and 25 degrees
  either side, then from up to 3 other points of the from-zone L3
  stands on within 2.5 m (Step R2.16d); `--region` keeps those walkable regions' takeoffs only,
  a slice), kept in the private cache with their start feet (over a
  floor face of the level, in the takeoff's zone) and the volumes and
  pickups their touches are judged against (a file by its sha12, part of
  each job's key: sample again after a change there); prints counts.
  With `--refine PLAN ... --snapshot LABEL` it samples the refinement
  of that run instead: every R0 launch, the roll jump with one and two
  rolls and a recast at each derived jump and flap edge the run left MAY,
  unattempted or found only above its kit (with `--region`, those taking
  off there; none that edge's aim job in those plans ran, and from that
  job's floor and start answers, Step R2.16e), and R0's fan
  and the roll jumps from the walkable regions under `--min-area` in
  their from-zones. Every other verb takes several plans (`--plan A B`):
  a refinement adds to its run.
- `run`: the jobs the cache doesn't hold yet, a few per task on an L3
  pool on `--snapshot` (an L3 snapshot of the level in `--store`, every
  verb's, by default the L3 store's `reach-live` folder of per-level
  start snapshots, its `README.txt` naming each; any of its rooms:
  each start tries the snapshot's cell, then the level's others nearest
  first), each job's record written atomically as it finishes, so a
  stopped run resumes (a job that raises is counted in `errors`, its
  record unwritten, and tried again on the next run; so is a job with a
  step L3's watchdog stopped for time, `runaway@` or `render timeout@`,
  the host's load and never the game's fault: `reach_engine.worker`,
  AZ-813; a hold's stops its verb with no answer cached), every worker kept
  busy to the end (no chunk waits on its slowest task); a line of counts
  every 4 tasks a worker (jobs, errors, ticks, ticks a second, how
  launches ended). `--workers` defaults to the pool's (the host's cores,
  at most 16); run it under `nice -n 19`; the pool gives way to a
  waiting xemu sitting.
- `graph`, `diff`, `witness` and `sample --refine` first hold the zone
  witnesses (Step R2.16d, `reach_engine.hold`): each zone pair keeps,
  of its 3 best witnesses a rank, the best whose body still stands or
  swims in its to-zone 60 idle ticks after its string, replayed from its
  start on an L3 pool of `--workers` for those the cache holds no answer
  for yet (an aim's hit is checked as its job runs, and since Step
  R2.19k one whose body left takes none of the 3; since Step R2.19f+ a
  witness repeating a kept one's string takes none either: its hold
  answers as its twin's; a retarget's witnesses, ids `g...`, take 3 of
  their own, so they push out no other).
- `graph`: the engine's zone edges (ids, least air rank, witness hashes,
  taint and frozen-world flags) and its closure per kit (edges, nodes,
  strongly connected components).
- `diff`: the recall report (`reach_engine.verdict.report`): the derived
  modelled jump and flap zone edges' verdicts (FOUND, MAY, N/A; NO is
  never given at R0) and recall, a find counting only at the edge's own
  kit (over all of them: the design's 85 % bar; over those attempted;
  over those the derive didn't get wrong, `graded`: no requires-false
  row, no landing or takeoff where L3 stands no body of its zone within
  2.5 m that no launch reaches, those listed in `derive`; and, apart,
  finds at any rank), the aimed edges', the probe-needed
  ones', each hand edge's and each assumed and physics row's, the
  engine's zone edges the derive lacks (with their zone-mapping flags:
  `one_region`, `takeoff_zone`, `zone_far`; those with none), and the
  run's counts (starts dropped or kept by their zone, how launches
  ended). A found witness is the evidence (D277; D661: no jitter
  replays, no may/must split).
- `witness`: each zone edge's best witness at each air rank as a
  `proofs.jsonl` `azurik-l3-proof/1` edge record (no coordinate; its xemu
  replay owed, `replay.owed` R2.16c).
- `--l3` (every verb that opens a pool; Step R2.19a): `fast`, the
  default, runs each pool's player ticks on FastL3 with the aimed jobs'
  lossless tick cuts (and, every pool on either route since Step R2.19l,
  the driver cuts: a launch's touches found once, FastL3's placement
  answers kept by feet, yaw and cell in the level's private cache folder,
  `placed/`) and, once `build_unicorn.py` has built it, the
  patched libunicorn ([`SIMULATOR.md`](../../docs/SIMULATOR.md) § "FastL3"); `base`
  runs round 1's `L3` on the stock wheel. Both gave round 1's records
  byte for byte on the bench (an unmapped write's fault site can differ,
  never a find; a fetch from a data page faults in FastL3 alone, a lost
  find, never a false one; neither happened on the bench:
  [`SIMULATOR.md`](../../docs/SIMULATOR.md)), so a record is reused whichever wrote
  it; `run` names the mode and library it ran (`l3`, `library`). Each
  record a worker writes carries `l3_impl` (Step R2.19b,
  `reach_engine.worker`: fast or base, the sha12 of FastL3's code, of the
  libunicorn loaded and its switches; a field, no key part). A fast `run`
  then audits what it ran (PLAN-v2 §1.5c): about 1 job in 500 (by key)
  again on base `L3` on the stock wheel and, with the patched library, 1
  in 1,000 on FastL3 with its x87 check mode on (softfloat beside every
  fast result; since Step R2.19m on the library's check flavour, with the
  C walk's check mode too: every face decision beside the game's), each
  record compared with the one it wrote (`l3_impl` aside; nothing
  written), printed as `audit`; any record that differs, any x87 result
  or C walk decision that differs, or an x87 audit whose workers wrote no
  count, stops it with exit 1 naming the jobs.
- `--backend kernel` (every verb; Step R2.19d, D845,
  `devkit.reach.native.backend`): the native kernel runs each
  launch, and the start's placement, kit and camera align, under the
  engine's own controllers; FastL3 runs what the kernel flags (a
  placement that flags runs whole on FastL3; a launch that flags, with
  the others of its family that flag, from its start's FastL3 twin),
  answers an aim's floor scans and other starts (the kernel's point
  where FastL3 stands a body there too, else FastL3's own scan) and
  confirms each kernel outcome before it counts: an aim's hit as it is
  found, any other zone witness at the hold, from a start FastL3 stands
  (else a `start` fault), its string and 60 idle ticks run again from
  the snapshot on the worker's timed FastL3 (a step stopped for time
  stops the verb, no answer cached: AZ-813) and the outcome re-derived
  from L3's rows (HP, flaps, trick labels, volumes, picks, taint, the
  witness hash). A kernel candidate gives no node edge, MAY
  candidate or touch itself; since Step R2.19k each confirm the hold
  reads, staying or not, gives those of FastL3's run. Since Step R2.19p
  each launch family runs in C (`reach_native/controllers.c`'s copy of
  the controllers, one call a family, the same records);
  `AZURIK_REACH_CONTROLLERS=py` runs the Python controllers, the
  reference, and the verb refuses to start the route while a Python
  source the C copies has moved since `backend.SHADOWS` pinned it
  (`docs/SIMULATOR.md`). Kernel records are keyed apart: the job's L3 key,
  the sha12 of `kernel.c`, `controllers.c`, the package, the geometry decode, the
  compiler, its flags and the host's machine, and the snapshot's
  platform census (L3's own collision sweep: the platforms the game's
  world doesn't hold there, left out of the kernel's), made once a
  snapshot into the level's cache folder. A plan named `NAME@l3` or
  `NAME@kernel` runs on that backend whatever `--backend` says; a `run`
  is one backend's. A kernel `run` prints its flags by stage (launches,
  flagged and why, their ticks on each side, confirms) and its drift
  audit (about 1 job in 100 by key: each kernel launch that settled run
  again on FastL3; `silent` over 0.5 m from the kernel's landing,
  `moving`, `dead`); a stage over 2 % silent is named, its plan to run
  with `@l3`. Every hold answer on this route carries the witness's
  `route` (the mover-contact router: the rigs, toggled gates and
  census-absent platforms its body path touches at their load pose, and
  the rigs it passes within 2 m of), which the graph's witness ids
  carry.
- `rigs` (Step R2.19h1, D845, D847; `devkit.reach.engine.rigs`,
  [`REACH.md`](../../docs/REACH.md) § "Rigs in the first all-level run"):
  the level's rig stage on a FastL3 pool. The recording, once a
  snapshot and recorder into the level's cache folder: 3,600 whole steps
  from the snapshot at rest, every rig's deck read where the game
  collides with it each tick, and each of the derive's exported rigs
  that is read (R2.19h2) but stands still poked as R2.19h2's witness
  does and recorded from the poke. Each rig's verdict: `cycles` (its
  period: every box corner back within 2 cm), `path` (it moves from
  load), `static`, `toggled` (a term of its start moved it: the link
  carries the term) or `parked` with its reason (an undecoded start, a
  read start no poke moved, no collision object: no rig link, D847).
  The recording, each poke try and each trip start on a scene FastL3
  that never ran (`l3_pool.Worker.sim(fresh=True)`): a reset doesn't
  undo all of a long run.
  Round each exported deck that moves, the native kernel with the decks
  posed at its clock (`World.movers`) runs the engine's R0 launches from
  each zone's 4 takeoffs nearest it (none standing on a deck's load
  pose) at every 15th tick of its span, at it and 25 degrees either
  side: boards, alights from a body put on its top, and links joining
  them by the ride (the board's landing ridden on the kernel to each
  later tick an alight of its kit launched from). Only FastL3 whole-step
  trips count (D845): from the snapshot (a toggled deck's pokes first),
  idle whole steps to the phase, R6 onto the start, the kit and the
  string, a link then held 60 ticks in its to-zone; a board, alight,
  link or truth board that held counts only where it holds again alone
  on another new one from the snapshot (`held_not_alone` counts those
  that didn't). `--truth N`: N random
  whole-step board trials a deck on FastL3's own controllers (a takeoff,
  a heading 40 degrees about the deck's centre, an R0 launch, a phase).
  Every whole step runs under a 120 s cap, not L3's wall-clock ones (a
  stream load's maps under load: R2.19h2). The output holds deck names,
  verdicts, counts, ticks, CPU and witness sha12s; positions, poses and
  strings stay private.
- `graph`, `diff`, `witness --rigs` (Step R2.19h1): on the kernel route,
  each zone witness the hold answers goes through the router
  (`rigs.Router`). One whose path touches a rig parked for an undecoded
  trigger is out of logic, kept or not (D847: the pair takes its next
  candidate, and the confirm's touches and node edge go too). Of those
  its frozen hold kept (no trip rescues one the hold or the kernel
  confirm dropped), one touching another parked rig keeps its witness
  and names it (`parked`, a whole-step trip's too). One that a rig moving within its
  window (the settle, kit, string and hold) in the level's rig recording
  (made first if missing) touches at its load pose, or crosses on its
  swept path (its body path replayed on FastL3 where it passes within
  6 m across of where the rig goes, as 10-tick boxes against the rig's
  posed box each row: `sweep/`), counts only where its FastL3 whole-step
  replay does: from the snapshot on a new scene FastL3 each try, idle 0,
  15, 30 ... ticks first (at most 8 tries, the phase loop), ending
  within 0.5 m of its hold's landing, settled, and held 60 ticks; its
  witness then owes that idle (`wait`; `witness` writes an `idle` step
  before its R6); else the hold falls back on the pair's next candidate.
  Answers are cached apart (`trip/`, by the hold's key, the recording's
  sha12 and the trip code); one no moving rig meets keeps its
  frozen-world witness.
- `sample --backstop modelled|all --refine PLAN ... --snapshot LABEL`
  (Step R2.19d, D846): the FastL3 backstop, an L3 plan whatever
  `--backend` says: the aims and the refinement's aims at each derived
  jump and flap zone edge of those confidences the plans leave unfound
  at their kit (every pass at a modelled edge, pass 1 at a probe-needed
  one: `aim.MORE`).
- `sample --retarget PLAN ... --snapshot LABEL [--gate-m 3.0]` (Step
  R2.19f+'s g1, `aim.retarget`): aims at what those plans' graph left,
  ids `g<class><n>`: `ga` rank 0 (k0, no flap) at a non-derived k0 pair
  of the level's truth frame (`reach_truth.py frame`'s, seed 219) the
  graph holds only above rank 0, from its witness's takeoff at its
  landing; `gb` at a zone rank the hold left with no witness (and none
  under it), at the to-zone's floor nearest its best candidate's
  rejected landing, every pass; `gc` and its twinned refinement `gd` at
  a probe-needed edge unfound at its kit whose pass-1 landing or first
  touch-down came within `--gate-m` of its to-zone's floor (read from
  the records), every pass.  A plan on `--backend`'s route.
- Hold answers (Step R2.19f+'s X1): each cached answer names what ran
  it (`l3_impl`, as a record does), and `graph`, `diff`, `witness` and
  the samples that hold re-run about 1 replayed hold in 500 on base L3
  and 1 in 1,000 under the patched library's x87 check
  (`worker.hold_audit_task`, by hold key), counting them in the graph's
  counts (`hold audit base|x87: ...`) and stopping on any difference.
- Keys hash code, not text (Step R2.19f+'s SF0, `cache.code_bytes`):
  the L3 core, the kernel's key, `l3_impl`'s code, the census file and
  the rig recorder's code key read a `.py` file's AST without
  docstrings and a `.c` file's tokens, so a comment or docstring edit
  re-keys nothing.
- `sample --pairs --refine PLAN ... --snapshot LABEL [--budget CPU-H]
  [--slice F] [--truth NAME ...]` (Step R2.19g2, PLAN-v3's g2,
  `reach_engine.candidates`): the pair stage. A pass-1 aim (ids `p<n>`;
  R's own pair aim, its edge `from>to:pair:nd`, so `aim.MORE` runs pass 1
  alone and its keys are apart from R's) at each non-derived pair of the
  level's truth frame (`reach_truth.py frame`) that the plans' graph,
  every zone witness held, has no zone witness for at its kit (k0: rank
  0; air3: rank 3 or under). Its targets go in groups of at most 32 of
  one from-zone, kit and tier (`nd-k0`; `nd-air3` at slack -20 m or less,
  "near"; the rest, "far"), in the frame's seeded order; the groups in the
  tiers' order (PLAN-v3's: nd-k0, near, far, whatever a level's rates
  say), then the frame's (so a cut within a tier is the frame's own
  seeded sample, as R's are). Each group names its expected links, the
  tier's pass-1 hit share in R's rows frozen under the `--truth` names
  whose pair the graph lacks at its kit, as the targets are (20 rows or
  more), else those rows' non-derived R-real share x 0.4,
  else a prior (k0 0.073, near 0.053, far 0), and its CPU-seconds, a
  pass-1 aim's price by `--backend` (kernel 0.26 / 0.32 CPU-s at k0 /
  air3, FastL3 0.78 / 0.99). `--slice F` keeps each non-derived stratum's first
  fraction F in the frame's order (a bench's seeded slice). `--budget`
  (CPU-hours, by those prices) ends the
  queue: the plan keeps what it took and left by tier (pairs, groups,
  expected links, CPU-hours) and the pairs left ("not searched", never
  "unreachable": D845); it prints the counts. Derived pairs stay the
  targeted pass's, the refinement's and the backstop's. No `aim.py`
  edit, so no key moves: a group is the queue's unit, each target its
  own job and record.
- `sample --escalate M --refine PLAN ... --snapshot LABEL [--kit
  k0|air3]` (Step R2.19g3, PLAN-v3's g3, `candidates.escalate`): the
  escalation at tier M metres (PLAN-v3's ladder 1, 2, 3, 5, 10). Each
  pair stage aim (`p<n>`) in those plans whose pair their graph, every
  zone witness held, still lacks at its kit and whose pass-1 landing or
  first touch-down came within M of its to-zone's landing-side points
  (the frame's; from its record, so choosing runs nothing) gets the same
  aim with every pass (`more`, ids `ea<n>`); once those plans hold that
  aim's record and the pair is still lacking, the refinement's launches
  at its target twinned to the pass-1 aim, every pass (ids `er<n>`). k0
  first, then nearest; the plan names the pairs that wait by kit and the
  tier that would take each. A tier is two samples: run the first plan,
  then sample again with it added to `--refine`; graph with every plan.
  A wider tier holds a narrower one's jobs, already run. Escalation
  witnesses take a zone pair's tries of their own, which the hold tries
  after every other. No `aim.py` edit, so no key moves.
- Plans and outcomes (where each launch settled, its witness string)
  stay in the AzurKit user cache's
  `reach-engine/<level>` (mode 700, files 0600), keyed by the L3 core
  (with the flap law's constants and the witness format; an aimed job's
  also by the targeted pass's `reach_engine/aim.py`, so an aim-only
  change re-runs only the aims, not R0's fan), the snapshot,
  the plan's targets and the start: a re-derive re-maps them with no
  run, an L3 or launch change runs them again. OUT files (mode 0600) never
  replace one there (`l3.private_out`). Shadow only (nothing writes
  `src/azurkit/tools/randomizer/data`); dev tooling, never in pytest.

## `reach-truth`

The reach engine's truth set (Step R2.19c; D825, D845, D846): R, a
denser reference search on the engine's own controllers, run on a seeded
stratified sample of a level's zone pairs, each pair's result frozen,
so the engine's recall is measured against more than its own finds
([`REACH.md`](../../docs/REACH.md)).

```bash
uv run --locked python -m devkit reach reach-truth frame LEVEL [--seed 219] --out COUNTS.json
nice -n 10 uv run --locked python -m devkit reach reach-truth run LEVEL --snapshot LABEL --name NAME \
    [--strata nd-k0 ...] (--take N [--skip K] | --quota N [--per 50] [--cap 100] [--step 20] \
    | --like NAME ... | --pairs FROM>TO:KIT ...) [--seed 219] [--workers N] [--l3 fast|base] \
    [--backend l3|kernel [--refly]] --out RUN.json
uv run --locked python -m devkit reach reach-truth recall LEVEL --name NAME ... --graph EDGES.json --out RECALL.json
uv run --locked python -m devkit reach reach-truth calib LEVEL --kernel NAME --fast NAME ... --out CALIB.json
nice -n 10 uv run --locked python -m devkit reach reach-truth generate LEVEL --snapshot LABEL --name NAME \
    [--strata nd-k0 ...] (--take N [--skip K] | --like NAME ... | --pairs FROM>TO:KIT ...) \
    [--strings 20000] [--flagged 50] [--confirms 10] [--seed 219] [--workers N] [--against NAME ...] \
    --out GEN.json
uv run --locked python -m devkit reach reach-truth chapman LEVEL --r NAME ... --gen NAME --graph EDGES.json \
    --out CHAPMAN.json
```

- `frame` (`reach_engine.candidates.frame` since Step R2.19g2, which
  `reach_engine.py sample --pairs` reads too): the ordered zone pairs
  inside a widened envelope, per kit
  (`k0`, rank 0; `air3`, the shield's rank 3): two border points of the
  zones (the logic walk's border samples and the swim water's surface,
  one a 2 m square and 1 m of height) within 1.25x the frame-perfect
  running travel at their height difference, the drop at most 40 m, the
  rise at most the kit's rise + 1 m. Strata: `dm` (a derived modelled
  jump or flap edge), `dp` (probe-needed only) and `nd` (no derived edge),
  each by kit (a derived pair's kit is the air of the edge it aims at,
  a modelled one first: k0 at 0, else air3); pairs with only other
  derived edges are counted and left out. Each stratum is in a seeded
  order, so a sample is its first N and a larger sample holds every
  smaller one. The frame is written once
  (`reach-engine/<level>/truth/frame-<zoning>-<seed>.json.gz`, private);
  another frame under the same name is refused.
- `run`: R on the next `--take` pairs of each `--strata` from `--skip`:
  an aim with all six of `reach_engine.aim`'s passes (the derived flight
  where there is one, else the two zones' points the envelope ranks
  best), and where that holds no find, the refinement's launches
  (twinned to the aim), the small regions' fan and R0's 14 launches from
  2 takeoffs of the from-zone at 3 headings facing the to-zone. A pair is
  real when a witness lands in the to-zone from a start in the from-zone
  at the kit's rank or under and stays there the hold's 60 idle ticks.
  Each pair's result (real, rank, which job found it, its jobs' keys,
  CPU-seconds and L3 ticks) goes to the private `truth/NAME.jsonl` with
  the code that made it (L3 core, aim core, this script and
  `reach_engine.candidates`, `--l3`, the library); a pair already there is never run again. The CPU and ticks
  of every job and hold a truth run ran are kept in the private
  `truth/costs.jsonl`, so a pair's price outlives the cache.
  `--quota N` (Step R2.19c3, the thin levels) runs rounds in one pool
  instead: each stratum (all six by default) takes its next pairs until
  it holds `--per` R-real links or `--cap` pairs, `--step` a round
  while it holds no R-real link, else what its real rate says it lacks; then the
  stratum with the highest real rate takes pairs until the strata hold
  N R-real links in all. FastL3 decides every pair (D845): a fast
  invocation is audited as `reach_engine.py run` is (about 1 job in 500
  again on base L3, 1 in 1,000 under the x87 check) before any of its
  pairs is frozen, and a difference freezes none. The output's `sample`
  gives each stratum's weight (its frame's pairs / its sampled ones),
  the frame's R-real links it estimates and the R-real links' Kish
  effective number. `--like NAME ...` takes the pairs frozen under those
  names (of `--strata`), `--pairs FROM>TO:KIT ...` named pairs (stratum
  `known-<kit>`; no frame needed). `--backend kernel` (Step R2.19c2a)
  runs R's jobs on the native kernel route (`reach_engine.py --backend
  kernel`'s: launches on the kernel, a flagged one on FastL3, keys apart),
  so the kernel only proposes and FastL3 still decides each pair (D845);
  each row then holds the pair's candidates before the confirm (by the
  side that flew them) and each tried one's FastL3 answer (held, a
  fault, the string's end, landed elsewhere, over the kit, left in the
  hold), and with `--refly` each kernel candidate whose confirm failed
  flies once more on FastL3 under its own closed-loop controller from
  its start's FastL3 twin (its job run again on the kernel up to that
  launch, its launch families in Python so the re-fly sees each), then
  is held from the snapshot (`refly_real`). `--strata`
  takes c1's slack-band strata too (Step R2.19c2b): `nd-air3-near` and
  `nd-air3-far`, nd-air3 split where `reach_engine.candidates` splits
  its tiers (20 m or more inside the envelope is near: every R-real
  air3 pair c1 froze lay there). A band's `--take` and `--skip` count
  its own pairs in nd-air3's order; its rows stay stratum `nd-air3`.
- `calib`: a kernel run against FastL3 rows of the same pairs, per
  stratum: the FastL3-R real pairs it keeps alone and with its re-fly
  (Wilson 95 %), those it loses, its finds FastL3-R lacks, the confirms
  by FastL3 answer, the re-fly's classes, the false-positive factor
  (pairs with a kernel candidate / its real pairs) and each side's
  CPU-seconds, L3 ticks and kernel ticks.
- `generate`: the independent generator (PLAN-v2 §1.2 item 3), which
  shares none of R's controllers: per pair `--strings` open-loop random
  strings on the kernel, each from a random border point of the
  from-zone that stands (its start and kit settled once), the camera
  turned at the pad's rate to a heading within 90 degrees of the
  bearing to the to-zone (on the camera's 3.33-degree tick grid, so a
  start's turn runs once), the stick full along it, Y after a random
  run-up of 0-30 ticks and, with air3, 0-5 flaps and 0-2 recasts on
  random ticks of the next 150; the stick rests from the first
  touch-down until the body has stood 5 ticks. A fall 2.5 m (k0) or
  8.5 m (air3) under the to-zone's lowest floor ends there. A string the
  kernel lands settled in the to-zone at the kit's rank or under is a
  candidate FastL3 confirms with the hold, fewest ticks first, at most
  `--confirms`; while none stays, at most `--flagged` of the strings the
  kernel flagged fly on FastL3 and a landing there is held. Rows go to
  the private `truth/NAME.jsonl`, the witnesses to
  `truth/NAME-witness-<time>.json.gz`. With `--against NAME ...` each
  pair the generator holds and those rows' R doesn't is classed: R's
  aim, then its refinement, from the generator's start at its landing
  find it (`targeting`) or not (`movement`).
- `chapman`: on the pairs the generator and R (`--r`, a re-fly's find
  too) share, per stratum the first capture (R or the engine,
  `--graph`'s zone edges at the kit), the second (the generator), both,
  Chapman's estimate with its interval, the links both R and the engine
  miss as a share of R's real links (B4's measure), and the generator's
  links R missed by class; pooled by the frame's weights.
- `recall`: the engine's recall against R per stratum (nd-air3 per
  slack band; Wilson 95 % intervals) and pooled over them by those
  weights (Wilson's interval on the Kish number; a pair frozen under
  several names counts once, real when any name's R held it, a re-fly's
  find too), from `reach_engine.py graph`'s zone
  edges, R's misses (the engine's finds R didn't make, never added to R's
  denominator) and the level's known-real links (`KNOWN_REAL`: D634's
  two owner-shown links). A pair frozen under more than one `--name`
  counts once, as the last name holds it.
- Outputs (mode 0600, never over a file) hold zone ids, counts, ticks and
  seconds; dev tooling, never in pytest.

## `rig-triggers`

The rigs' triggers (Step R2.19h2, D847; `devkit.reach.engine.triggers`,
[`RE_XBE.md`](../../docs/RE_XBE.md) § "Rig triggers"): what starts each moving solid,
read from its level's wiring, and the rigs-only re-run that witnesses it
in L3.

```bash
uv run --locked python -m devkit reach rig-triggers census [LEVEL ...] [--out FILE.json]
nice -n 10 uv run --locked python -m devkit reach rig-triggers witness LEVEL ... [--snapshot LABEL] \
    [--ticks 600] [--hold 6] [--rigs exported|all] [-j N] --out FILE.json
```

- `census`: every level's rigs (every solid platform a link moves) and
  the derive's exported ones (its `rigs`: each entry's owner by its
  movers and axes, `Triggers.exported`, as twins share a name), by start (`load`: it moves
  with no event; `wired`: a condition over the wiring's atoms, pads,
  items and `global:<name>` (a latch's global set by an earlier level);
  `never`; `undecoded`, with the node types it rests on, parked by name),
  and the kind of their pokes (`condition`: the start's own atoms;
  `source`: the mover's own input, where an atom has no write).
- `witness`: per level, from its `reach-live` start snapshot (or
  `--snapshot`), `--ticks` whole steps untouched (the baseline), then for
  each wired or undecoded rig the same with its pokes held at each graph
  pass's entry (a pad first released 3 ticks: the player may spawn in
  it, and a switch acts on a change), its start's terms in turn (at most
  3: an elevator called to the floor it stands at doesn't move), then the
  movers' own inputs; a rig is witnessed when its deck,
  where the game collides with it, leaves the baseline by 5 cm, and the
  run goes on until it has stood still 30 ticks (`moved_m`,
  `rest_tick`); a load rig when it moves on the baseline, and a wired
  or undecoded one that already moves there is `moves untouched`, not
  witnessed. Every step runs under a 120 s cap, not L3's wall-clock ones:
  a poke that starts a stream load passed the 5 s render cap under load
  or late in a worker, and the verdict changed from run to run. Rows
  hold names, ticks, metres moved, steps and CPU, and each try's term,
  stop and tick (`tries`); positions stay in memory. `-j` runs levels in
  parallel. Dev tooling, never in pytest.

## `build-unicorn`

Builds FastL3's patched libunicorn (Step R2.19a; [`SIMULATOR.md`](../../docs/SIMULATOR.md)
§ "FastL3"): PyPI's unicorn 2.1.4 sdist (the one uv.lock pins, its sha256
checked), x86 only, with `devkit/reach/unicorn/unicorn_fastl3.patch` beside it (GPL
as Unicorn, so outside the package: none of it ships), into the
user cache dir's `AzurKit/unicorn-fastl3/<the patch's sha12>`, and its x87
check flavour (Step R2.19m: the same source with the check code, the x87
audit's) into that folder's `check/`, then checks
that a process with `l3_fast.worker_env()` (and `worker_env(check=True)`)
set loads it (`l3_fast.probe`) and
prints both sha12s. The reach
engine's pool uses it once it is there. Needs cmake, ninja, clang and
patch; about a minute. Revert: `rm -rf` the folder it prints.

```bash
uv run --locked python -m devkit reach build-unicorn [--jobs 4] [--force]
```

## `l3-certify`
Certifies the randomizer's spots and edges with simulator Level 3 (Step
X.7; D170, D172; [`SIMULATOR.md`](../../docs/SIMULATOR.md)): a spot or an edge is
proven `by = "l3"` once an L3 input string that reaches it has replayed in
xemu tick for tick and its record is in
`src/azurkit/tools/randomizer/data/proofs.jsonl`. Dev only: never in pytest,
never a player's verb; the sandbox rules are the `azurik-xemu-oracle` skill's.

```bash
uv run --locked python -m devkit reach l3-certify plan --impact IMPACT.json [MORE.json ...] --out DIR [--top 10]
uv run --locked python -m devkit reach l3-certify plan --tour PROGRESS.json --out DIR   # R1.16: the golden tour's certify list
uv run --locked python -m devkit reach l3-certify plan --spots ID [ID ...] --out DIR   # R1.29: spots at the logic's kit
uv run --locked python -m devkit reach l3-certify sitting DIR <W> snapshots          # per level and kit: hop, kit, savevm, an L3 snapshot
uv run --locked python -m devkit reach l3-certify adopt DIR                         # R1.16: each <level>-k0 group's newest earlier snapshot, no sitting
uv run --locked python -m devkit reach l3-certify search DIR [--jobs 8] [--workers 16] [--steps 400000] [--only KEY ...] [--scene] [--dive 0.25] [--placed] [--touch 0.75] [--douse] [--plateau STEPS]
uv run --locked python -m devkit reach l3-certify sitting DIR <W> replays [--only KEY ...] [--no-chain]
uv run --locked python -m devkit reach l3-certify apply DIR --sitting NAME       # proofs.jsonl + the authoring files; then rando author
uv run --locked python -m devkit reach l3-certify recheck [--level L ...] [--write]   # after a re-derive: re-run and re-zone
uv run --locked python -m devkit reach l3-certify pickups DIR [--out FILE]         # AZ-389: the pickup proofs, judged again
uv run --locked python -m devkit reach l3-certify plan-skips --out DIR [--only ID ...]   # the skips (Step R1.8g)
uv run --locked python -m devkit reach l3-certify search-skips DIR [--jobs 6] [--steps 150000] [--only ID ...]
uv run --locked python -m devkit reach l3-certify apply-skips DIR --sitting NAME [--unreplayed] [--only ID ...] [--zoning SHA256]   # proofs.jsonl skip records
```

- `plan` reads `devkit/rando/impact.py`'s rankings: a spot starts in the arrival
  node from which the logic reaches it with nothing held, touches it and
  comes back; an edge walks from its from-node to its to-node holding its
  requirement when that is element levels; anything else (a button, a
  flag, an event, a key) is reported as not set up.
- `plan --spots` (Step R1.29, AZ-455): location ids, each from the arrival
  whose way there and back over walk edges asks the least element levels
  (a walk edge asking element levels alone counts, as the logic's own kit
  for it, and a barrier the edge goes `through` asks its crossing with
  the edge: its destroy requirement, or its bypass, AZ-517), that kit
  lowered to the most `rando check` takes a proof at (AZ-570: the logic
  may collect the spot holding less, going in or leaving with its own
  item, `Logic.kit_short`; the way's own kept as `kit_way`, and a spot
  it refuses at every kit not set up), set in L3 as a tour target's
  (group `<level>-k0`, so `adopt` serves the searches); a spot whose way
  needs a button, a flag, an event or a key
  is not set up, nor one its generated `gated_by` gates (a keylord, a
  boss, a lock or a geode gives its item, no touch; the skip names the
  gate). Its search starts at the hop's own
  arrival when that lies in the spot's arrival node (a teleport nearest
  the goal may stand on the spot, which proves nothing), else by an R6
  teleport into the node's start zone: the string must come back where
  it started (D122), and `apply`'s record says its way back was walked
  only then. After the search, its winner
  in whole steps says whether L3 took the spot's own item there
  (`l3_taken`: whole steps run the pickup's touch as the game does; the
  goal's 0.75 m touch alone doesn't, AZ-483). `search --dive SHARE` lets
  that share of the segments in the water dive (BLACK held), a spot's
  depth under a swimming row counting in its cost: many pickups lie under
  the surface, where walks and jumps never reach. A spot is at a location
  as a pickup is (Step R1.29b): its goal is its item's own touch round
  where it rests, and an R6 start stands in the item's own cell, where
  alone it spawns (AZ-488). `search --placed` starts each spot by R6 on
  its start zone's sample nearest the goal at least 2 m off the spot, or
  2 m beyond its item's touch radius, not at the hop's arrival (its
  distance band is recorded); a sample whose settle hangs in whole steps
  is passed over.
  `search --touch M` sets the goal reach around a spot's point (default
  0.75 m) only for an item whose species has no touch; the searched spots
  keep it in `targets.json`, so the end-to-end check and the replays judge
  with the reach the search used, and a later search without it puts the
  default back.
- `plan --tour` (Step R1.16, D206): the targets are a progress file's
  `certify` list (the golden seed's tour of the spheres xemu doesn't play,
  progression only, and each counted item's pickup from its node): a walk
  to its to-node's zones, an exit, a cart or a disc teleport into its
  trigger (`ExitGoal`), a pickup to its location, each from its
  from-node's zone at the tour's kit; actions and hops whose rule asks
  world state a new game plus a hop doesn't give are not set up. A tour
  target's kit is set in L3 (`Segment.kit`: the element levels, and with
  air the armor cast by LT+Y), so each level needs one snapshot from a new
  game (group `<level>-k0`, kit 0): 21 for R1.16 instead of one per level
  and kit. `adopt` gives each such group the store's newest earlier one
  (a sitting's `<name>-<level>-k0-<HHMMSS>`, format 3 first) so the
  searches need no sandbox; `sitting snapshots` takes an adopted group
  again, since a replay loads its state in the sandbox. `apply` writes
  nothing for them: the folder's results and replays are the record.
- `search`: edges first; the start is the snapshot's own spot when it lies
  in the start zone, else an R6 teleport onto the zone's floor or water
  sample nearest the goal that lands and settles (nearest by its cost to
  go; where the route graph has no way there, nearest the item, AZ-531:
  not the zone's most open samples wherever they lie; a pickup's or a counted
  item's: into the item's own cell, on the nearest sample outside its
  touch, AZ-488; an exit's: outside its trigger; where neither the item's
  cell nor the snapshot's settles there, each other cell of the level's
  list in turn, the rooms whose locations stand nearest the sample first,
  AZ-382: w1's beach is another room); the guidance is the
  logic profile's route graph, the light trick graph's at the leg's air
  when the logic has no way from there and it has (`leg_guide`, Step
  X.53, AZ-593: its sweep, one-sided recheck, hops, lifts and doubts; it
  was the phys profile's, the envelope alone), else the straight line to
  where the goal's field reaches (a goal with no vertex, a point no floor
  is under: the direct line to it); seeds are the planner's plan and
  earlier runs' winners from the same start. Every target of a level and kit runs at once on one
  persistent worker pool on its snapshot (`l3_pool.solve_many`, Step
  X.10; `--workers`, default the cores up to 16): `--jobs` derived seeds a
  leg, each to a step budget, the lowest seed index that reached wins
  (the same winners whatever the worker count); then every spot's way
  back, chained on its first leg; the winner is checked again in whole
  steps (a pickup or a counted item: its own item taken in L3 there,
  `scene_outcome`; its goal is the item's own touch, AZ-483). An end to
  end check L3 stops on the way (a render past its 5 s cap on a loaded
  host) runs once more from the snapshot, and a second stop leaves the
  target unverified and `inconclusive` with the stop's site
  (`verify_fault`), its legs kept, as a skip rung's check does (AZ-640,
  Step R1.34); `results.json` is written whole (a temp file renamed
  over it) as each target ends. A failure
  says whether every seed explored all it reached (the
  logic is wrong or the move set misses a way) or the budget ran out; a
  failure whose runs were tainted (they read what L3 doesn't model) is
  `inconclusive`, never a refutation. Each leg (Step R1.29e) searches
  strings up to 6,000 ticks a leg (`LEG_TICKS`, 2,400 before; a doused
  leg's parts together) whose branches may
  stay 210 ticks in the air (`LEG_FALL`, 120 before: 3 to 5 flaps take
  123-185), an air kit's recasting the armor in 4% of its segments; an air
  kit's way back starts with a recast at rest (`RECAST`, its string's
  first segment, its `lead`: the leg's check counts no goal row in it),
  since the way there may have spent the gauge; a way there wins only when
  the body past the spot's touch, at rest or, in the air, on the string's
  last stick, lives 10 ticks and then is settled (stands, swims or
  rests on near-flat ice: `obs.settled`, AZ-737), or lives 300
  (AZ-571, AZ-627: `l3_goal.SURVIVE`, `l3_search.LAND_CAP`; a touch on
  the way to a death, also one high over a lethal drop, is no pickup), and
  a leg whose start is dead, or off the floor and dying before it lands
  both ways, isn't searched (`its start doesn't run: the leg starts dead`,
  `... starts off the floor (state 0x2) and dies at rest and on its last
  stick before it lands`); each leg
  records and prints how many cells each seed left at the tick cap
  (`capped`). `search --scene --douse` (Step R1.29e) makes a leg through a
  barrier (a level edge of the way there, the target's `path`, or of the
  way back `plan` sets up, its walk back to its start node at the least
  kit, whose `through` names one) three in one: a search to within 3 m of
  the barrier's shape on its near side, a douse (`devkit/sim/douse.py`:
  the staff's elements cast, A on the walk through, the least element
  levels its crossing asks added to the kit), then a search on to the
  leg's goal; a leg through more barriers (Step R1.29f) crosses each in
  turn the same way before the search on from the last; the leg
  keeps its pieces as `parts` (the replays run them in turn) and the result
  lists each douse's outcome (`douse`); a barrier the to-node's cost to go
  says isn't in the way where the search reached it is crossed by nothing
  (`not_in_the_way`, as `Chain.staff`). A proof record's and `apply`'s kit
  is the one the string ran with (the douse's levels too).
  Diagnostics (Step X.52): every target prints a line, one with no
  snapshot or no start that settles too. With `--plateau STEPS` a seed
  ends after that many steps with no new best cost to go, `plateau at
  <edge>` (no part of the problem's identity; off by default, as a find
  late in a budget would be cut). A leg
  not found records its runs' faults by site (`faults`: `unmapped@EIP`,
  `runaway@EIP`, `render timeout@EIP`, `assert <file>:<line>`, `no player
  update`) and its kernel taints' game callers and files (`taint_at`),
  prints both and each seed's stall, and its runs keep each seed's
  `stall`: the region edge ahead of its least-cost cell (id, kind,
  confidence, the zones at its ends) and `plan`, the plan's level edge it
  lies at (the way there's `path` or the way back's walk); DIR's
  `stalls.json` collects them per target, for R1.23's and R1.24's
  `assumed` and `probe-needed` edges (measured candidates, never proof).
  A leg whose every seed's start raised in the workers says `its start
  doesn't run in the workers`; a worker's error stays with its seed.
  Step X.52b: a stall also names its stage (`no zone`, `off the graph`
  with the zone the fallback steers to, `walk` with its first other
  zone, `edge`), the best row's state and whether the best cost still
  fell (`last_fall`, `fall_10k_s`); a branch that fires a level exit ends
  there untainted, and a leg not found prints and keeps those branches
  by level (`exits`). `--wall-cap` defaults to `--steps` at 4 a second
  (`l3_search.WALL_RATE`), for `search` and `search-skips`.
- `replays`: a fresh snapshot, L3 reruns the string from it, then
  `Sandbox.replay` and `l3_compare`; proven when every tick's body centre,
  state and HP match; then a snapshot where the replay halted, linked to
  its parent. A skip to a pickup is also proven where xemu takes it
  (`pickup_at`): the first tick that differs differs in the inventory
  hash alone, xemu took the goal's own item (the vanilla item's
  inventory field changed, measured past the replay's own writes: not the
  kit's levels or the cast's fuel), and the body centre is equal on every
  tick before it (AZ-389: the hash once held the day clock, which
  player-tick L3 doesn't advance, so it differed from tick 1). A tour
  target's replay (AZ-474) has stops, so a level load ends it there, and
  is judged by its outcome (`judge`): an exit only when its destination
  or its movie (which plays first) loads within the string or a tail of
  up to 150 neutral ticks after it (`tail`, also after a stall: a movie
  or a fade; it ends at a load, or after 60 s with no tick of the
  player's), a pickup or a counted item's reach only when xemu takes
  the goal's own item there, each with the body, state and HP equal
  through the goal's tick (an exit's load inside the string: through the
  tick before it, never one in the settle); a walk by every tick equal.
  A placed (R6) start within 1 m of where the string first stands in the
  goal, or of where the load came when sooner, is `near` (its distance
  band is recorded) and proves no hop, unless the target is at a
  location; a tour replay judged before this rule is replayed again.
  Since AZ-483 (rule `az483`) a pickup's goal is the item's own touch
  (the body centre in its touch ellipsoid) and L3's whole-step rerun runs
  on up to 150 neutral ticks until the item is taken, so the replay
  compares those ticks too; the record's `sha12` is the string's own.
  An outcome at or before the settle's last row is `settle` (the
  placement took it: no proof, not even near; AZ-486); in whole steps an
  item's take is the row L3's own inventory gained it (`outcome_at`),
  since xemu's inventory hash then equals L3's. Since AZ-699 (an item's
  rule `az699`) a take past the settle and more than a tick before the
  goal's is another item on the way: the body must match through the
  goal's tick, and xemu's inventory must change again from the tick
  before it (or in a tail that started with the goal's fields
  unchanged). An exit's goal is the
  body centre inside its trigger mesh, and in whole steps L3 runs on to
  its levelSwitch's fire (the tail plus a timer gate's wait), which ends
  the replayed string (`outcome_at`, `outcome`: the level and movie);
  the target's own outcome (its item's field, the exit's own level)
  meets its goal even in the tail, and `scene_outcome` records it for a
  search's winner.
  A spot (`judge_spot`, Step R1.29) is proven when every tick there and
  back is L3's, xemu took its own item (its vanilla item's inventory
  field) and its start isn't a teleport within 1 m of where the string
  first stands at it (`near`; the start's band is recorded); its replay
  clears a popup on the way with A (`replay_clearing`: a first gem), the
  event clock checked. `apply` marks a spot the authoring already holds
  (a conservative-kit `requires`) in its own `[[location]]`, its note
  gaining the proof's, and the record's set-up names the kit (R2) and
  the cast. A target's private start is kept per folder (`_priv`): two
  folders searching one key no longer overwrite each other's.
- `pickups DIR` judges every recorded pickup proof in `DIR` again under
  that rule, reading the folder only (`--out FILE`, outside `DIR`: the
  result as JSON): the counts of results, replays and pickup proofs, and
  each proof that no longer holds with why. A player-tick proof recorded
  before AZ-389's fix can't be judged from its record (its first
  difference was the clock's), nor an older record's element levels
  (its raw offsets were measured before the kit's writes);
  `sitting DIR <W> replays` replays every proof that no longer holds
  again.
- The public folder `DIR` holds targets, counts, strings and hashes; the
  reach models and teleport points go to the L3 store's `x7` folder (mode
  700), beside the snapshots. The committed record names a teleport by its
  reach-model sample and the place struct's sha12, never a coordinate.
- The reach model (`_reach_path`, which `devkit/reach/l3_contact.py` and `devkit/xemu/chain.py`
  share) is the one built under the level's current zoning: `<level>.pkl`
  while its `.stamp` names that zoning, else `<level>@<sha12>.pkl` keyed by
  it, built from the vanilla ISO the first time (minutes). A re-derive
  that renumbers the zones so gets a fresh model rather than searches
  aimed at the old zones (AZ-362); the older ones stay, and `recheck`
  finds a record's teleport in the one whose sample gives its place.
  A route graph built on a model (`l3_goal.load_router`: 2 s for d1,
  16.5 s for w1) is kept, the router with its model, in `routers/`
  beside it under its content key (`router_key`: the model file's path
  and identity, the profile, the draft's code and authoring,
  `randomizer/physics.py` (the walk and swim speeds its costs divide
  by), `xbr/collision.py`, the Python and numpy versions; Step X.95), loaded
  again in 0.4-0.8 s by every process and pool worker after the first,
  the newest key a model and profile only.
- `recheck` re-runs every record's string from its kept snapshot and
  re-zones its claim under the current derive (zones are renumbered by a
  re-derive), reading a zone only where a standing or swimming body's
  feet are, on that floor or in that water (AZ-590: never in the air,
  climbing, or from the floor under a rig's tooth or a ledge's top it
  stands on; the douse's to-node reads the same way); `rando author` refuses a `[[probed]]` walk whose record's
  `zoning` (the sha256 of the level's derived `zones` section) isn't the
  level's until then.
- `replays` also adds each replay to the conformance corpus
  (`l3_conformance.py`).
- The skips (Step R1.8g; D183, D177, D178): `plan-skips` turns the
  script's `SKIPS` table (each skip's level, start zone or the snapshot's
  own spot, goal zone or pickup, way back, whether it rolls, whether it
  needs whole steps, a loadvm state other than a new game) into targets;
  the snapshots are taken with nothing held, since the kit is set in L3.
  `search-skips` runs D183's ladder per skip: its top rung (air 3, the
  armor's 5 flaps) first, then 0 flaps with no air, 1 with air 1, 2 with
  air 2 and 3 with air 3, each with the kit set at the start (R2's levels
  and the cast by LT+Y); the first rung that reaches and holds in whole
  steps (a tick-mode winner whole steps refuse is searched again in
  whole steps, seeded with it) is the skip's `requires`, its most flaps
  in one jump and its robustness (32 jittered copies) its difficulty.
  An easier variant (`rungs`) searches its own air only. After
  `sitting DIR <W> replays`, `apply-skips` writes a record per replayed
  skip (claim `kind = "skip"` with its kit and flaps), which `tricks.toml`'s
  `confirmed = { by = "l3", ref }` names. D277 (Step R1.31): with
  `--unreplayed` it writes one per winner that held in whole steps, with
  no replay (`replay.rule` D277: the simulator's run confirms a skip);
  `--zoning` names the zoning the search's reach model had, when the
  level was re-derived since (`--only` takes skip ids).

---

## `l3-gate`

The trick explorer's starts and the long-replay gate (Step TD.0, the
trick-discovery plan's T0; [`SIMULATOR.md`](../../docs/SIMULATOR.md) § "The exact
xemu replayer").

```bash
uv run --locked python -m devkit reach l3-gate states LABEL [LABEL ...] [--ticks 120] [--scene]          # L3 only
uv run --locked python -m devkit reach l3-gate start <W> TAG LABEL [--state 0] [--settle 10] [--hold] [--scene]
uv run --locked python -m devkit reach l3-gate build LABEL OUT [--ticks 5200] [--seed 1] [--radius 40] [--scene]   # L3
uv run --locked python -m devkit reach l3-gate replay <W> LABEL OUT [--scene]
uv run --locked python -m devkit reach l3-gate split LABEL IN OUT [--most 5000] [--scene]          # L3 only
```

- `--scene` (Step TD.4b): whole steps, so rigs, enemies and triggers run:
  `start --scene` snapshots the next scene tick's entry, `build --scene`
  draws and checks the string in whole steps, `replay --scene` runs L3's
  side in whole steps (xemu's per-tick replay is the same; the corpus
  keeps the record as `scene`) and the gate is then 5,000 whole steps
  replayed exactly (met in sitting TD.4c: 5,215 from town's arrival,
  [`SIMULATOR.md`](../../docs/SIMULATOR.md) § "The exact xemu replayer").
- `split`: IN (a string from LABEL's own start, as `build`'s) run in L3
  and cut into D172 pieces of at most `--most` ticks (`l3_explore.split`:
  each ends at the last settle point in its reach, 10 ticks at rest on
  the ground, else at `--most` ticks, `settled` false); OUT (mode 0600)
  lists each piece's start, ticks, `settled`, string and sha12, for a
  chained replay.

- `states`: each snapshot's player over neutral L3 ticks: the states it
  holds (counts), HP at the start and the end, taint. e6's four natural
  arrival snapshots (`x7-e6-k0-041640`, `x7-e6-k0-205552`,
  `x15g-e6-k0-070552`, `x8-e6-k0-080323`) stand in state 0 on all 120
  ticks at 200/200; `x7-w1-k0-205806` swims on every tick (2026-10-18).
- `start`: a natural start from a loadable state (the w1 beach spawn from
  `vanilla-rz-new`): neutral player ticks after the load until the player
  has stood in `--state` `--settle` ticks in a row, then an L3 snapshot of
  the next update entry (state, HP, pages, sha12 printed); `--hold` keeps
  the guest halted there for `replay`.
- `build`: a seeded string of at least `--ticks` player ticks: segments
  of 8-32 ticks (a heading in 24 sectors or the stick at rest; magnitude
  0.35, 0.7 or 1.0; Y, BLACK or nothing held; the camera turned toward the
  heading by at most 3.33° a tick, the stick along the heading under it),
  each kept only when L3 runs it with the player
  alive and unhurt, untainted, within `--radius` m of the start and at
  most 90 ticks airborne (a refused draw is drawn again; 64 refusals drop
  the last 3 segments). OUT (mode 0600): `l3.pads` segments.
- `replay`: OUT run in L3 from LABEL and replayed in xemu from its held
  start (`Sandbox.replay` with D172's stops: a load, a popup or a dialog
  ends it, and so does the first tick off L3 by any distance, state or
  HP), into the conformance corpus; prints the replayed and exact ticks,
  `gate_5000` (exit 1 unless 5,000 ticks replayed exactly) and
  `fields_differ` (per observed field, TD.0's too, the ticks off). The
  longest exact replays before it: one string of 3,061 ticks and a
  chain's run of 3,619 (R1.16's `chain-r116-s123`). Sitting TD.0
  (2026-10-18, v0.15.1): `start` from `vanilla-rz-new` stood in state 0
  from its first tick (200/200), and `build --seed 1`'s 5,214 ticks from
  there (states 0, 2, 3, 0x100 and 0x102; 687 m of path) replayed exactly
  on every observed field in 65 s: the gate passes.

Positions and strings stay in the private store; printed output is counts,
metres and hashes. Dev tooling, never in pytest.

---

## `l3-contact`
Measures the randomizer's contact flights at modified movement in L3
(Step X.11; [`SIMULATOR.md`](../../docs/SIMULATOR.md) § "Overlays"): a flight the
movement calculator can't reproduce, or that sits at its limit (a lip
lift, a roof, a curved jump, a walk-off), run by the game's own code on a
vanilla snapshot with the slider's build laid over it, to the value past
which no input string makes it.

```bash
uv run --locked python -m devkit reach l3-contact measure CASE PACK.SLIDER --out DIR [--lo X] [--hi Y] [--at V ...] [--steps N] [--seeds K] [--workers W] [--temp T] [--pursue P]
uv run --locked python -m devkit reach l3-contact walkoff --out DIR [--ledges N]
uv run --locked python -m devkit reach l3-contact apply DIR [DIR ...]     # src/azurkit/tools/randomizer/data/contact.json
```

- `measure`: per value, every string an earlier value won with is graded
  again, and `--seeds` searches (`l3_pool.search_task`, seeded only by the
  route planner's plan) run to their own ends from a teleport onto the
  flight's start zone to its landing zone, on a worker pool of the case's
  kit snapshot (its level's kit 0 snapshot, `BASES`, with air shield N
  worn, placed: `kit_snapshot`). A case (`CASES`) names the level, the
  derive's zone edge, the air rank, the hop its certificate witnesses and,
  where the zone edge has two options of that rank, the certificate's
  `dh` (`prof = "phys"`: the goal routes on the physical graph, where the
  logic graph has no way for that rank). The start is the zone's floor
  sample nearest the goal that a teleport settles on (then the nearest a
  metre from the floor's edge; else one the body slides on, state 3). The
  reach model is `devkit/reach/l3_certify.py`'s, of the level's current zoning. A value passes
  frame_perfect when any string reaches, standard when one's robustness
  (`l3_search.robustness`) is 0.5 or more (`TIERS`, D259; 0.8 until it),
  or vanilla's own where L3 rates
  vanilla lower (the best of its point and of every string won, graded at
  vanilla); a value fails only after every string the case has won with
  (rescaled to its frame rate for `target_fps`) is graded there too. At a
  frame rate F the search's tick limits (its step budget, longest string,
  segment, Y hold, air cap and the landing's ticks at rest) are F/30
  times vanilla's, the same game time (`limits_at`, `spec_at`; AZ-372). Each
  side (`--lo`, `--hi`: its far end) widens from vanilla (1/16 of the way,
  1/8, ...) until a value fails, then bisects, twice (the second pass with
  every string in). A failing value means no search found a string in
  the budget, so a range errs toward less movement. A case's `.fly` twin
  ends every branch that swims, so the string must make the flight itself
  rather than swim round and climb out.
- `walkoff`: the zones' free walk-off table (`physics.free_certs`) on real
  w1 ledges (the reach model's walk-offs where a run at full speed leaves
  within 0.5 m of the floor's end): each drop's reach past the floor's end
  against the table's gap, at vanilla and, where vanilla has room, per
  slider by bisection (one run per ledge, no search).
- `apply`: the measured ranges into `contact.json`
  ([`RANDOMIZER_DB.md`](../../docs/RANDOMIZER_DB.md) §17), with each one's evidence id;
  a side where vanilla doesn't reach, or whose values pass again past one
  that failed (a fragile flight's search luck), stays to the calculator.
- Public results (values, verdicts, counts, robustness, problem and string
  sha12s; no positions) go to `DIR`; teleports, strings and the kit
  snapshots to the private store. Dev tooling, never in pytest.

---
