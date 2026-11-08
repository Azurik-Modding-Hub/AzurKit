# The reach engine (`devkit/reach`)

Dev only, frozen (D1143): Modkit's reach engine at its freeze, ported whole (Step 4.13d1) so that Modkit can
go; the research resumes on AzurKit later. This page is Modkit's text: its steps, decisions and measurements
are Modkit's (their reports stay in the private evidence folder, named here by their step), its scripts are
devkit verbs (`python -m devkit reach VERB`, [`devkit/reach/README.md`](../devkit/reach/README.md)) and its
paths AzurKit's: the engine is `devkit/reach/engine/`, the kernel `devkit/reach/native/`, FastL3 and the pool
`devkit/reach/l3_fast.py` and `l3_pool.py`, the simulator `devkit/sim/` ([`SIMULATOR.md`](SIMULATOR.md)).
Its outcomes stay in the user cache (`AzurKit/reach-engine/`, mode 700), the frozen truth set in the user data
folder (`reach-truth/`), and it reads the L3 store's reach models in place (`devkit/reach/models.py`). It is
shadow only: nothing here writes the randomizer's data.

Step R2.16a (the R2.16 design; D609, D610, D615) builds the tool that will find which floors are reachable from
which with the movement the game has, by running the game's own player tick (simulator Level 3) rather than a
model of it: `devkit/reach/engine/` and [`reach-engine`](../devkit/reach/README.md#reach-engine). It is
**shadow only** until the plan freeze ends (R1.17): it writes the AzurKit user cache and evidence, never
`src/azurkit/tools/randomizer/data/`, so no seed changes.

- **Nodes** are the game's own walkable regions (`floors.walk_game`: a face over nz 0.7071, wider than the
  logic's 0.8), other landable floors (slides, steep and slippery faces), the swim water and the trigger, push,
  damage and pickup volumes a body centre passes; a node's key is the hash of its cells, so it survives a
  re-derive that keeps them.
- **Launches (R0):** a takeoff every 2 m of each region's boundary (4 m2 or more) at its outward normal and 40
  degrees either side; from each, a run walk-off, a run jump and a stand jump with no element levels, and with the
  air shield (air 3) the walk-off with 1, 2 or 5 flaps and both jumps with 0, 1, 2 or 5, each flap at the last
  tick its full lift holds (the game's flap law); plus the targeted pass, three aims (straight, curved left and
  right) at each derived jump and flap zone edge's own flight. Each launch runs to settled ground, a death or a
  cap; where it settled is the edge, at the least air rank its flaps need (rank 0 without the shield; 1, 2 or 3
  for at most 1, 2 or more flaps). A landing in another of the logic's zones is a zone edge even on the region it
  took off from (one walkable region can hold several zones).
- **Aims and starts (Step R2.16b):** most of R0's misses on w1 came from where its aims started and steered, not
  from physics: the derive's 0.5 m raster column holds a floor the point itself can be off, so L3's body placed
  there falls through. A start keeps R0's point where a floor face of the level's own mesh lies under it, else
  moves to the nearest point within 0.75 m over one in the takeoff's zone, and a start that settles in the
  from-zone counts even on another walkable region. An aim's target moves onto its floor face, 0.5 m inside it. Each aim is then
  flown twice over: by the predictive landing control (each airborne tick it predicts by the air laws where the
  feet come down through the target's height with the stick at the target, at rest or away, takes the nearest,
  and flaps only while it would still land short; run jumps pressed at the takeoff, and once 0.45 m short) and as
  R0 flew it (the stick held at the target), since each finds edges the other misses. A run or roll jump presses
  when its run-up along the heading is done, and one whose body leaves the floor first is no launch of its own
  (the walk-off's).
- **The refinement (Step R2.16b):** `sample --refine` takes the derived jump and flap edges a run left MAY,
  unattempted or (Step R2.16c) found only above their kit and aims every R0 launch at each, plus the roll jump (BLACK at the takeoff, a second roll chained
  by BLACK held on the first's ticks 14-18, Y held from the last roll's tick 16 into its end: the end-tick jump,
  which in mid-air resets the fall and the flaps, D114) with one and with two rolls, and a recast (LT+Y whenever
  the gauge has emptied with flaps left: a descent flap empties it; a recast refills the gauge, not the jump's
  flap count); and it runs R0's fan and the roll jumps from the walkable regions under 4 m2 in those edges'
  from-zones, which R0's fan skips.
- **Verdicts** per derived zone edge, hand edge and level row: FOUND (a launch settled there), MAY (tried, not
  found: a finer pass's queue), NO (outside the envelope: never given at R0, which has no envelope check, so it
  refutes nothing), N/A (not tried, a derived flight whose aims' starts all fell in L3, the 0.25 m ring around
  too, or a requirement R0 holds no branch for: an event, a flag, a skip, and for a row or hand edge not found, an element level, a button or
  discs), and for a row or hand edge DATA (the derive's
  own walks, swims, gates and drops reach it with no flight, so no engine edge backs it). A hand edge is FOUND,
  DATA or N/A. A found witness is the evidence (D277): since Step R2.16c (D661) no witness is replayed under
  jitter and there is no `may`/`must` split, and each zone pair keeps its best witness a rank (untainted first,
  then fewest ticks). Since Step R2.16d that witness must hold: replayed from its start with 60 idle ticks after its
  string, the body is still settled in the to-zone (stands or swims, or since Step R1.39 rests on near-flat ice:
  `obs.settled`, AZ-737; of the 3 best a rank, the best that does; an aim's hit is
  checked as it is found, so a hit that slides off is none and the aim's later passes run). Each zone witness carries the zone-mapping flags R2.16a's skeptic named (`one_region`: its
  zones share one walkable region; `takeoff_zone`: it took off in another zone than its start's; `zone_far`: the
  logic's floor sample naming its landing's zone lies over 0.5 m off), and the report counts them over the new
  edges. Each found edge's witnesses are `proofs.jsonl` edge records whose xemu replay is still owed. Since Step
  R2.16d a derived flight whose terms add water, fire, earth or a flag to its air is FOUND by a witness at that air
  (it ran with less: w1's 31 such witnesses land the same with their elements set), and the rows the derive got
  wrong carry `derive` and leave the report's `graded` recall (the bar's `recall` still counts every row):
  `requires false` (each of w1's 6 refuted by a witness), a phantom landing (no aim stood a body in L3 in its
  to-zone within 2.5 m of its target, and no launch lands in that zone) and a phantom takeoff (no start of its aims
  stood, and L3 stands no body in its from-zone within 2.5 m of its takeoff).
- **Cost:** w1 at R0 is 70,524 jobs (62,949 from about 21,000 takeoffs, and 7,575 aims) and about 904,000
  launches, of which about 857,000 ran (the rest belonged to starts that never stood). On 2026-10-24, 8 workers
  under `nice -n 19` beside other work (load average 14 to 99 on 24 cores) ran them in 5.4 hours (97 million
  player ticks, about 5,000 a second), and the jitter replays (8 for each of 5,928 witnesses) in 24 minutes;
  three of w1's 731 regions took 37 % of the ticks, and the median region that launched 26,200 ticks. Outcomes are
  cached by the L3 core, the snapshot, the plan's targets and the start, never the derive, so a re-derive re-maps
  them without a run.
- **w1 at R0 (2026-10-24, with the skeptic's corrections):** 1,448 of w1's 3,238 derived modelled jump and flap
  zone edges found at their own kit (45 %, under the design's 85 % bar), 438 of them with a `must` witness. Most
  misses land lower than the derive's flights (817) or have no start that stands (609). 20 of the 36 assumed
  rows, 24 of the 32 physics rows and 3 of the 12 hand edges are backed, but only 5, 7 and none of them by
  `must` edges alone. The engine found 893 zone edges the derive has none for; 552 reach zones the derive's
  whole graph doesn't at that air rank, 379 of those pass the zone-mapping checks and 70 are also `must`. Its
  witnesses replay in L3 exactly (18 of 18 checked), but 2 of the 3 swimming landings checked drifted out of
  their zone within 2 seconds, so a swimming landing is never `must` yet. The three crossings of the derive's
  barriers it found (iceblock01, firewall01, statuetimer) go round or over them in the snapshot's world, not
  through a gate it left open.
- **w1's slice after Step R2.16b (2026-10-24):** the 40 walkable regions whose aims held the most R0 misses (768
  of the 1,745 with an aim), launched alone before and after (the fan from those regions and the aims taking off
  there; 1,121 derived modelled jump and flap zone edges): recall at the edge's own kit 348 (31 %) on R0's code,
  518 (46 %) with the new aims and starts (186 gained: 101 where R0's start fell through, 41 from a start moved
  onto its face, 44 by the predictive control from R0's own start; 16 lost, each to a start moved off a point L3
  stood on), and 633 (56 %) with the refinement on what stayed MAY (of the 121 edges it newly found at kit, 115
  of them the slice's, the best witness was an R0 launch at the target for 93 and a roll jump for 28; a recast
  for none). Ticks: 1.2 M before, 1.9 M after, 1.6 M for the refinement.
- **w1 after Step R2.16b (2026-10-24, with the skeptic's corrections):** the whole plan's aims (7,409 jobs) and
  the refinement on what they left MAY (4,895 jobs, 14.4 M ticks between them) ran; the snapshot was deleted
  before the fan (all but 142 of its 62,949 jobs) and the jitter replays could run, and a re-take re-keys every
  job (AZ-720), so these numbers are final for that snapshot. 2,222 of the 3,238 derived modelled jump and flap
  zone edges found at their own kit (69 %, R0's 45 %; under the 85 % bar), 1,829 (56 %) without the refinement.
  `must` is not measured, and even if every kept witness held under jitter it would be at most 1,975 (61 %):
  165 finds rest only on `zone_far` landings. Of the 745 still MAY, 312 settle under the aimed point, 212 first
  touched down on the target or in its to-zone and then left (reached, not settled), 108 have no start that
  stands and 54 fall to their death. The roll jump is the best witness for 181 finds and the only one for 73.
  The engine found 473 zone edges the derive has none for; 161 reach zones the derive's whole graph doesn't at
  that air rank, 150 of them with an unflagged witness that is untainted, off the frozen world and not a drifting
  swimmer. Replayed with no jitter on another w1 snapshot, 12 of 12 witnesses settle in their recorded zone; under
  8 jittered trials 5 of them hold none.
- **Speed (Step R2.16c, D661, 2026-10-24):** the engine measures no jitter: `robust`, `must` and the jitter replays
  are gone (a found witness is the evidence, D277), and with them the 3 witnesses a zone pair kept a rank. The
  2-second hold on a swimming landing stays: it is no jitter, and deleted with them at first, it was restored
  once the step's skeptic found 24 of 40 sampled new-reach swims leave their to-zone within it (0 of 40 standing
  landings). Macros of one start and kit that differ only in their flaps run together:
  their pads agree through the run-up, the jump and every flap up to the fewest's, so those ticks are stepped once
  and each branch goes on from its saved state (on 30 fan jobs, 20 % fewer steps, all 420 outcomes the same). An
  aim or refinement job stops at its first launch from a start in its edge's from-zone that lands in its to-zone
  at the edge's air rank (each worker names zones by a slim pickled zone map, as the graph does; a stopped job's
  cache key holds that code's sha12). The stop costs finds, since the launches after a hit also found other
  edges: on the slice it swapped 4 finds at the edge's own kit for 4 others, and finds at any rank went 728 to
  724 and zone pairs 828 to 815; replayed on the old records it lost 5 finds at kit (644 to 639) and 17 zone
  pairs; on all of w1 it cut the launch that had been R2.16b's witness for at least 15 finds at kit. It stays
  (D115; D610, D661: approximate and faster).
  An aimed job whose starts all fall tries the 8 points 0.25 m around its first in L3, kept where the body
  settles in its from-zone: the start search reads the engine's face list, which misses floors L3 stands on (the
  skeptic stood a body there for 28 of 32 sampled edges whose starts all fell, and 11 of them reached their edge
  at kit from it). An unfound derived edge whose starts all fell even so is N/A, a `takeoff` fault (AZ-723; it
  still counts as attempted, and the refinement still tries it); one whose aim lands where the engine's face list
  holds no to-zone floor within 2 m stays MAY with that `landing` fault as a flag, since the list misses floors L3
  stands on (L3 stood a body in the to-zone within 2 m of 145 of the slice's 178 such aims). The refinement also
  re-aims the edges found only above their kit: on all of w1, 19 of those 73 reach their edge at kit refined.
  `run` keeps every worker busy to the end and sizes its pool to the host (16 workers here), and snapshots come
  from the store's `reach-live` folder (`--store`). On w1's 40-region slice (snapshot `r216c-w1-k0-203922`, nice
  19, load 54 to 82 on 24 cores): run, refinement and jitter replays 4,327 s and at least 5.9 M L3 steps before
  (8 workers; the replays alone 1,640 s and 2.9 M steps), run and refinement 778 s and 2.3 M steps after: 2.6x
  fewer steps with the deleted replays, and without them 1.3x fewer steps and 1.27x less worker CPU (5,125 s to
  4,045 s), the like-for-like gain (the wall's 5.6x is also 16 workers against 8 and the host's load); recall
  at the edge's own kit 644 of 1,121 (57 %) both times, 4 of them other edges (the run alone 515 before, 509
  after: the stop; the refinement makes up the count, not the same edges). With the skeptic's fixes (the ring
  of starts, the above-kit refinement, the swim hold) the slice again: run and refinement 2.6 M steps and 4,219 s
  of worker CPU (main's code: 5.9 M steps with the replays, and 5,125 s of CPU before theirs), and 701 of 1,121
  at the edge's own kit (63 %: all 644 kept, 57 gained; aims whose starts all fell 168 to 11, refinement jobs 298
  to 12).
- **w1 after Step R2.16c (2026-10-25):** the whole plan ran on the re-taken snapshot `r216c-w1-k0-203922` (another
  world state than R2.16b's, so every job re-ran): the aims (7,476 jobs), R0's fan (62,949) and the refinement
  sampled on what both left (4,710), in 16,056 s of runs (5 h 7 min with the samples and reports; 16 workers
  under `nice -n 19` on the shared host, 1-minute loads of 64 to 99 at each stage's start and end) and 108 M player ticks,
  71 M simulator steps. R2.16b's aims and refinement alone took 15,199 s for 14.1 M ticks on 8 workers, where
  these took 2,974 s for 11.3 M on 16: a factor of the pool and the host as much as the code's (R2.16b kept no
  CPU times; per worker-second the fan and aims made 431 ticks here against R2.16a's 627); 142 of its fan's jobs
  ran (R2.16a's whole run: 5.4 hours, 97 M ticks). 2,244 of the 3,238 derived modelled jump and flap zone edges
  found at their own kit (69 %, R2.16b's 2,222; 509 short of the 85 % bar): 1,800 from the aims alone and 1,916
  with the fan. Of R2.16b's finds 2,196 stay at kit; of the 26 lost, 15 lost their witness launch to the aims'
  stop (a hit earlier in the same job) and 11 had their witness job left out of the refinement, which this run
  sampled after the fan, and the 73 edges found only above their kit got no refinement (refined since, they
  give 19 more at kit: 2,263, 70 %). Its misses barely move (7 of the 312 that settled under the aimed point and
  8 of the 212 that reached the target and left are found now): the gain is the fan and finds that had needed
  more air. Still MAY 617 (short 312, reached then left 202, fell 52); N/A 177 (132 whose aims' starts all
  fell: from the ring of starts added since, about a third reach their edge at kit, a 32-edge sample's
  estimate). The engine found 1,085 zone edges the derive has none for, 612 of them new reach (525 with no
  zone-mapping flag), about 150 of them (a sample's estimate) swimmers that drift out of the zone within 2
  seconds, which the restored swim hold rejects. The two slope pairs that rested on drifting swimmers alone have
  no witness now, since a launch settles only standing or swimming. These are the run before the skeptic's
  fixes (the above-kit refinement, the ring of starts, the swim hold), and its witnesses' refs say `r2.16b`.
- **w1 coverage (Step R2.16d, D665: w1 toward 85 % first; D661):** with those fixes all of w1 ran again on the same
  snapshot: 2,338 of 3,238 at their own kit (72.2 %). Its diagnosis found the aims' targets the main cause: for 68
  of 75 sampled misses the aimed point didn't stand in L3, though L3 stood a body in the to-zone a median 0.5 m off
  (the engine's face list misses floors L3 stands on up to a body radius past a face's edge, and the target snap
  wants a point 0.5 m inside a face). So an aim now first places a body at its target in L3 and, where it doesn't
  stand in its to-zone, steers at the nearest point of a 0.5 m grid within 2.5 m where one does (3 of its 4
  neighbours standing too). While none of a job's launches hits, it runs them again walking the body at the target
  once down (or holding it against a slide away), then steered 1.5 m short of it (the control overshoots), then the
  certificate's aims from 12 and 25 degrees either side, then from up to 3 other points of the from-zone L3 stands
  a body on within 2.5 m of the takeoff, each pass only while nothing has hit. Measured pass by pass on the
  diagnosis's seeded 145 misses and 100 control finds: 37, 45, 62, 74 and 81 of the misses found at kit, none of
  the control lost (walking at the target in place of the resting stick lost 4 of them, so it runs as a second
  pass), for 0.34, 0.21, 0.20, 0.45 and 0.61 M more simulator steps; scaled by miss class, about 2,909 at kit
  (90 %). Passes 2 to 5 run for the modelled edges only (the bar's; the probe-needed aims held 3 in 4 of the misses
  they would run for). The aims are keyed by their own code (`reach_engine/aim.py`), so a change there re-runs only
  the aims, not R0's fan (89 % of w1's ticks); the fan re-ran once for the split and gave the same records (3,000
  of 3,000 sampled jobs).
- **w1 after Step R2.16d (2026-10-25):** all of w1 again on the same snapshot with its review's and skeptic's fixes
  (an aim walked at its target once down counts no tick at rest while its stick is held; the held aims keep their
  own point where the target stands; and the hold: a witness counts only where its body still stands or swims in
  its to-zone 60 idle ticks after its string, an aim's hit checked so as it is found): the aims (7,489 jobs,
  3,879 s, on the 8 efficiency cores for about its first 20 minutes while an owner demo played, then 16 workers), R0's
  fan (62,949, the run before's records) and the refinement on what both left (4,121, 3,146 of them run, 2,648 s on
  16); 127 M player ticks, and 13,131 hold replays for 2.6 M more. 2,854 of the 3,238 derived modelled jump and
  flap zone edges found at their own kit (88.1 %: over the 85 % bar by 101; 2,338 before the step), 2,969 at any
  rank (91.7 %); 89.8 % graded (59 rows out: 6 requires false, each refuted by a witness, 36 phantom landings, 17
  phantom takeoffs). The aims alone found 2,634 and with the fan 2,670. The run before counted 2,873 at kit on the
  5-tick settle, but replayed with 60 idle ticks only 2,756 of them stayed (116 of the 117 that left were standing
  landings, the standing t8522h1, which xemu replays leaving its zone, among them); of its 2,873, 2,848 stay at kit
  now, 25 are lost (12 now reach the target and leave, 10 are found only above their kit) and 6 are gained. The
  hold took 164 zone witnesses from a later candidate and left 256 zone ranks with none. The best witnesses of the
  finds at kit: the aims 1,722, the refinement 552, R0's fans 580. The engine found 861 zone edges the derive has
  none for, 465 of them new reach (376 with no zone-mapping flag, 99 swims).
- **The envelope's flap schedule (Step R2.16e, D736):** an aim at a modelled edge whose certificate jumps with flaps
  carries the envelope's flap ticks for it (`physics.Envelope.schedule` of the certificate's rank, headroom and flap
  cap, to the target's height) and, when its five passes all miss, flies the certificate's aims from its own starts
  once more with each flap on that schedule (the sixth pass, after the others, so their launches stay as they were):
  the step's probe on 94 sampled misses with such a certificate found 49 so, and none with the flap law's timing.
  The refinement is still sampled on the aims' first five passes (`aim.unscheduled`), so the jobs it runs, whose
  launches find other edges too, are the ones they were: with the sixth pass's finds left unrefined, one such job's
  find of another edge was lost on w1. On the step's bench (w1, f2, a5, e7 at kit 0; 8,027 derived modelled jump and
  flap zone edges) the sixth pass with the refinement's twin below took the edges found at their own kit from 6,913
  to 7,142 (86.1 % to 89.0 %; w1 2,922 to 2,975, 90.3 %), none lost, for 0.4 M more aim steps (1 %).
- **The refinement repeats nothing its aim twin ran (Step R2.16e):** a refinement job at an edge whose aim job
  (the same takeoff, starts and target) the refined run holds runs none of that twin's macros and no fourth pass (the
  twin's own), and takes the twin's floor and start answers in place of searching L3 again (`aim.twinned`): the same
  launches gave the twin's outcomes, and on the bench the refinement of about the same edges took a quarter fewer
  steps (35 M to 27 M; the bench 229 M to 221 M, 33,100 to 30,900 a find at kit). L3 repeats a job's launches
  bit for bit nearly always: re-run with the same code, 2 of f2's 8,519 aim jobs gave other strings. A known flaw
  (D610): the skipped fourth pass and macros assume the twin flew them from the same cells, but where the
  refinement's own starts stood in other cells than the twin's they skip launches the twin never flew (11 of the
  bench's 1,208 refinement jobs that reach the fifth pass; no find lost); the fix, a skip only where the twin's
  starts stood in the same cells, waits for the next change to `aim.py`, since any edit there re-runs every aimed
  job.
- **Step R2.16e's bench, main against the step (2026-10-27; stopped after its first round, D821):** w1, f2, a5 and
  e7 at kit 0 on their R2.16c snapshots (8,027 derived modelled jump and flap zone edges; 12 workers at nice 10 on a
  shared host). Found at the edge's own kit, main to the step: e7 1,017 to 1,094 (84.5 % to 90.9 %; graded 85.4 %
  to 91.9 %), a5 591 to 613 (87.0 % to 90.3 %; 88.6 % to 91.9 %), f2 2,376 to 2,460 (83.3 % to 86.3 %; 92.2 % to
  95.5 %), w1 2,915 to 2,975 (88.5 % to 90.3 %; 90.0 % to 91.9 %), the bench 6,899 to 7,142 (86.0 % to 89.0 %;
  89.9 % to 93.1 %), none lost. A find took 6.63 s of wall to 6.19 (e7 7.42 to 6.35, a5 12.92 to 12.45, f2 4.51 to
  4.13, w1 6.82 to 6.55) and 40,276 outcome ticks to 38,515 (e7 22,345 to 20,221, a5 100,008 to 96,391, f2 29,023
  to 27,600, w1 43,593 to 42,342): the fan, cached by both, at main's cost, the rest re-run side by side under one
  load. In xemu (the vanilla disc, each witness placed at its start on the engine snapshot's event clock), 227 of
  the step's 243 new finds reach their zone and stay there as the engine says, and 74 of 80 sampled flap finds of
  main's own do (92.5 %), so the misses are the engine's, not the new pass's: 8 flights fly elsewhere from the
  game's start, which lies a few millimetres and a camera turn off the engine's (the engine's settle turns no
  camera), and an enemy hits the player in 7. One start is false: the game carries the body off w1 5212's start,
  where L3 stands it from the same state (its player tick runs none of that world), so w1 5212 and main's own w1
  5189 from it are no finds: w1's confirmed count is 2,973 (90.3 %).
- **FastL3 in the pool (Step R2.19a, D843, D850):** every pool the engine opens runs its player ticks on FastL3
  (`docs/SIMULATOR.md` § "FastL3": the same L3 on less host CPU, on the patched libunicorn once
  `devkit/reach/unicorn/build_unicorn.py` has built it) with the aimed jobs' lossless tick cuts (`reach_engine/fast.py`: the
  second pass resumes each first-pass launch at its first touch-down; a hit's hold runs its 60 idle ticks from the
  launch's end); `--l3 base` runs round 1's L3. On the R2.16e bench (Step R2.19a's report) every
  record of round 1's came out byte for byte (166,375 of 166,393 jobs, all 30,930 cached hold answers; the other 18,
  w1 fan jobs, are round 1's own records of steps L3's watchdog stopped on a throttled worker, AZ-813), and a find
  took 18.6 CPU-s against round 1's 41.5 (x2.23; side by side at one load x2.28 CPU, x2.20 a tick); an
  independent side-by-side sample (its measure: 3,360 jobs, 1,465 hold answers) gave 19.4 against
  40.9 (x2.11 CPU, x2.08 a tick) and 1.7 % fewer ticks a find (30,673 against 31,197). Recall at kit is round 1's.
- **Audited FastL3 runs and whole steps (Step R2.19b, D845):** a step L3's watchdog stops for time is a job's error,
  never an outcome (AZ-813: round 1's 18 such w1 records were rewritten, 252 outcomes where they held 224); each record
  names what ran it (`l3_impl`); a fast `run` re-runs about 1 job in 500 on base L3 and 1 in 1,000 with the x87 check,
  and stops on any difference. On the bench (Step R2.19b's report) the audits' 330 and
  158 jobs gave round 1's records with no x87 difference in 6.7 G fast results; R2.19a's side-by-side sample gave
  every record again at x2.33 a tick (x2.20-2.38 by level), and the independent measure's sample x2.23 (x2.17-2.34),
  19.4 CPU-s a find, 1.65 % fewer ticks a find than base and w1's recall at kit unchanged (2,975 of 3,294, 90.32 %);
  and FastL3's whole steps (a5: 3,600 at rest with every rig's pose, and 30 launches from them) were base L3's row for
  row, so a fast pool runs them on FastL3 too. These ran on the keys from before R1.39's `settled()`, which moves them all.
- **Driver cuts (Step R2.19l; PLAN-v3's R2.19l, SF1 a and c):** every pool worker on either route finds a launch's
  touches once a launch (each distinct body centre once, every volume, pickup and position tested at once), and a
  FastL3 worker keeps each placement's answer by its feet, yaw and cell, so a start try it knows falls is counted and
  not placed again and the floor and other-start scans read it; the answers persist in the level's private cache
  folder under the snapshot and the code that gave them, shared by every worker, stage and later run
  (`reach_engine/fast.py`'s `install_driver`, `docs/SIMULATOR.md` § "FastL3"). Lossless by records, so no key moves.
  The yaw stays in the answer's key: the yaw check's 10,500 plan points at 4 yaws gave the same answers, but the
  bench's first run found ledge points whose answer turns with the yaw. About 1 kept answer and 1 launch in 200 is
  done again in the run, a difference stopping it. On the bench (Step R2.19l's report,
  base and head side by side) every record, hold answer and edge of e7's whole kernel + backstop route and of a5's,
  f2's and w1's 100-job slices came out the same; e7 took 6.46 CPU-s a find against 7.00 (x1.08, its backstop x1.30;
  its measure's re-run) and 5,872 L3 steps against 6,284 (x1.07); the slices x1.03-1.14 (a bench estimate near
  x1.05). Recall: unchanged.
- **FastL3's patch lane (Step R2.19m; PLAN-v3's R2.19m, SF2-SF4):** the patched library's x87 fast path is leaner (its
  check code in a flavour of its own, the audit's), a player tick without `deep` is stepped in C (`sim/fastl3_step.c`:
  the TLB fill, the step's glue and the update's hooks; a block's exit test inline), and the static level's collision
  walk drops in C the faces the game would drop, handing the game the first it can't (`docs/SIMULATOR.md` §
  "FastL3"). Lossless by records, so no key moves; the x87 audit runs the C walk in check mode. On the bench
  (Step R2.19m's report, four commits side by side) every record, hold answer, plan and edge came out the same; a FastL3
  tick x1.82 (x1.15, x1.16 and x1.36 by step) and e7's whole kernel + backstop route 6.42 -> 3.79 CPU-s a find (x1.69)
  at the same L3 steps a find; an independent measure against main gave x1.82 a tick and 5.46 -> 3.05 CPU-s a find
  (x1.79) on e7, recall at kit equal (1,100 of 1,203, 91.44 %). Shadow doubles for the x87 registers (m3) measured no gain and are not landed. Recall:
  unchanged.
- **The truth set, wave 1 (Step R2.19c1; D825, D845, D846):** `devkit/reach/reach_truth.py` measures the engine against
  R, a denser search on its own controllers (every aim pass, the refinement, the small regions' fan and R0 from 2
  takeoffs facing the to-zone), on a seeded sample of each level's zone pairs inside 1.25x the frame-perfect reach
  (drops to 40 m, rises to the kit's rise + 1 m), stratified by derived modelled, probe-needed or not derived and by
  kit (k0, air3); each pair's result is frozen with the code that made it. Recall against R is an upper bound on
  real recall: a link none of the engine's controllers makes is missed by both. The pricing pilot
  (Step R2.19c1's report; 10 pairs a stratum on e7, a5 and w1, round 1's code on
  FastL3): 92 of 180 pairs real at 20.9 CPU-s and 27,183 ticks a real find priced in full (an empty-cache re-run;
  the pilot itself took 412 of its 1,008 jobs from round 1's cache); non-derived pairs are real at 0.1-0.4 and cost
  15-21 CPU-s each, and round 1 found 5 of the 12 real ones (every one of the 54 real derived-modelled pairs). The
  calibration (50 non-derived pairs a kit a level on AZ-737's code, frozen) puts round 1 at about 37 % (e7), 65 %
  (a5) and 60 % (w1) of the frame's non-derived real links, with real rates of 0.02-0.32, so a quota of
  300 real links a stratum needs the kernel (R2.19d) or a tighter frame: no real air3 pair lay within 20 m of the
  widened reach's edge. Its `KNOWN_REAL` names two links the owner showed in X.67's demo (D634): w2.Z050 onto the ice slide at air
  3, and w3's lake to w3.Z012.
- **The native kernel as the launch backend (Step R2.19d; D845, D846):** `devkit/reach/reach_engine.py --backend kernel`
  runs each job's placements, kits, camera aligns and launches on R2.17's native kernel (`devkit/reach/native/`,
  `docs/SIMULATOR.md`) under the engine's own controllers; FastL3 runs what the kernel flags (water, pushes, the
  step-up and lip-lift clips, the catch, the climb, the roll, ice), answers an aim's floor scans and other starts
  (the kernel's point where FastL3 stands a body there too, else FastL3's own scan, so a "no L3 floor" verdict is
  L3's) and confirms every kernel outcome before it counts (from a start FastL3 stands, its string and the hold run
  again from the snapshot, the outcome's HP, labels, volumes, picks and taint re-derived from L3's rows);
  `sample --backstop modelled` writes the FastL3 backstop (D846). On R2.16e's bench against round 1
  (Step R2.19d's report; round 1's records and grades, from before AZ-737; CPU of each
  stage's whole process tree; an independent seat's re-run, within 11 % of the builder's by level), the kernel route
  alone took 3.9-12.6 CPU-s a find (e7 5.05, a5 12.59, f2 3.89, w1 8.33, pooled 6.66; round 1 33.8-87.9 on base L3:
  x4.7-9.3; main's FastL3 route 13.95 on e7 beside it, x2.76) and 4,191-14,336 L3 steps a find (round 1
  16,597-74,187), but kept only 95.8-99.2 % of round 1's per-edge finds at kit (D846's bar is 99.5 %), so the
  backstop is on: with it every level keeps 99.8-100 % (e7 99.91, a5 100, f2 99.92, w1 99.80; 7,198 finds at kit
  against round 1's 7,142; 9 derived edges still lost) at 6.0-13.8 CPU-s a find, 8.36 pooled (x5.0 against round 1's
  41.5; the plan's bar was 6). On c1's frozen truth pairs the route found one non-derived real pair fewer than round
  1 on e7 (32 of 59) and on a5 (34 of 44) and as many on w1 (30 of 37), which no modelled backstop restores, so
  D846's condition that the truth set's recall rise is unmet. The kernel parts from L3 silently far more than
  PLAN-v2's 2 % drift bar: 10-35 % of each level's drift-audited settled kernel launches (4-50 % by stage) end over
  0.5 m from FastL3's run of their string (the confirm drops each such false candidate; the finds it costs are what
  the backstop recovers). Those numbers predate the review's fixes (the start check, AZ-813's time guard in the
  holds, the floors from FastL3), which cost e7's aims stage 19 % more CPU. The mover-contact router routes 3-13 % of each
  level's held zone witnesses to a rig or a gate at its load pose. The scale sample (e2, e5, w2: every 10th fan
  takeoff and 5 % of the aims) costs 0.4-1.0 CPU-s an edge on aims and fan, so all 22 levels would take about
  61-128 CPU-h [inferred] (159 at the bench's own rate).
- **The truth set's thin levels (Step R2.19c3; D825, D845, PLAN-v2 §1.3):** `devkit/reach/reach_truth.py run --quota
  300` froze R's verdicts on e2, e5, w2, d2 and f2, every pair decided on FastL3 (no kernel; the quota runs' and the w2/d2/f2 pilots'
  jobs audited: 27 again on base L3 and 12 under the x87 check, none differing; e2's and e5's 120 pilot pairs ran
  unaudited): each stratum to 50 R-real links or 100 pairs, then
  the derived-modelled stratum with the best rate to 300 R-real links a level (Step R2.19c3's report). 1,513 R-real links in 3,273 pairs (301-306 a level), 10.75 CPU-h of task CPU: 25.6 CPU-s and 30,807
  L3 ticks a real find (21.6-32.6 CPU-s by level). Real rates: derived modelled 0.73-0.97, probe-needed 0.02-0.47,
  not derived 0.02-0.16 (w2 the lowest outside its modelled pairs). The frames are 9,000-247,000 non-derived air3
  pairs a level, so a sampled one there weighs 92-2,468 and a level's pooled recall stands on 8-54 R-real links
  (Kish's number), not 300: the derived-modelled strata (50-224 R-real links each) are bounded closely, the
  probe-needed (2-47) and non-derived ones (2-16) loosely. Round 1 (f2, the one bench level among them) found 265 of f2's 303 (pooled by the weights 52 %, 95 %
  37-68 %; non-derived 6 of 19). The other four levels' engine side comes from the all-level run. `recall` pools by
  the weights and counts a pair frozen under two names once: R2.19d's reading counted the 20 pairs a level that c1's
  pilot and calibration share twice; counted once, round 1 found 32 of 52 (e7), 32 of 41 (a5) and 29 of 35 (w1)
  R-real pairs and the kernel route 31, 31 and 29 (the same two lost pairs). An independent re-run of 300 of the pairs
  (10 a stratum a level, on empty caches, the lane's script and main's side by side) gave the same verdict, rank,
  witness and jobs on every pair, and 27.1 CPU-s and 30,721 ticks a real find at the frozen sample's stratum mix
  (+7.6 % CPU at a 5-min load of 37-47 against the builder's 21-38; its measure).
- **The graph's two fixes (Step R2.19k; D845, D846, D893):** an aim's hit whose own hold left takes none of a zone
  pair's 3 tries (it had pushed out witnesses that may stay), and each FastL3 confirm the hold reads, staying or not,
  gives the touches, MAY candidate and node edge of FastL3's run of the string, as an L3 outcome does (judge-risk's
  X2: a kernel candidate gives none itself). Re-graded from the cached answers (Step R2.19k's report; the records' own commits with the new `graph.py`, 11 new replays over the bench), round 1 finds
  7,143 at kit (f2 one more), the D846 baseline from here on; the kernel route with the backstop finds 7,199 (f2 one
  more, 0 lost on any level), 99.87 % of it (every level 99.80 % or more), at 8.26 CPU-s and 11,925 L3 ticks a find
  (round 1 41.46 and 30,906). Its touches rise 4,415 to 4,709, its MAY candidates 5,606 to 6,246 and its node edges
  13,226 to 14,765: still 76 %, 56 % and 82 % of round 1's (6,232, 11,136, 18,072; e7 795 touches and 734 MAY
  against 1,105 and 1,642), since the kernel launches no hold confirms give none. Recall on c1's frozen truth pairs
  is unchanged (e7 31 of 52, a5 31 of 41, w1 29 of 35). Such a hit still counts as a landing in its to-zone (the
  phantom-landing guard; its review's fix). An independent re-grade beside main matched every count; the graph
  step itself costs 4.3 % more CPU with the backstop, +0.004 CPU-s a find (its measure).
- **The truth on the kernel (Step R2.19c2a; D845, PLAN-v3's c2a):** `devkit/reach/reach_truth.py run --backend kernel
  --refly` runs R on the native kernel route, the kernel proposing and FastL3 deciding every pair as the engine's
  route does; `calib` reads it against FastL3-R, `generate` is an independent generator (random open-loop strings on
  the kernel, none of R's controllers) and `chapman` the capture-recapture estimate of the links both R and the
  engine miss (Step R2.19c2a's report). On c1's 362 frozen pairs (302 non-derived,
  60 probe-needed; e7, a5, w1) kernel-R kept 70 of FastL3-R's 74 real pairs, 71 (95.9 %) with one closed-loop FastL3
  re-fly of each failed candidate: non-derived k0 29/30, air3 17/18 (94.4 %), probe-needed k0 13/14 (92.9 %), air3
  12/12; all three lost pairs' frozen FastL3 witnesses still stay on today's FastL3, so they are kernel losses, and
  it found 2 pairs FastL3-R hadn't. Of 346 kernel candidates FastL3 tried (350 in all), 37 held (the graph's hold
  confirms counted on the kernel side, its review's fix); most failures died on L3 (260: the kernel models no
  damage), and the re-fly held 24 of them but recovered one pair. On the non-derived pairs
  (priced in full on both sides) kernel-R took 8.9 CPU-s a pair against FastL3-R's 18.7 (x2.1, at different
  loads) and 57,261 L3 ticks a real find against 135,312, plus 92,644 kernel ticks. NS.2's go line (q) is not met:
  two strata sit between 90 and 95 %, and R2.19n's at-risk set is 33.8 % against its 2 %. The generator (20,000
  strings a pair on 300 non-derived pairs a thick level, 2.64 CPU-h) held 72 pairs and found 8 that R (kernel-R, its
  re-fly and c1's FastL3-R) missed, 5 that R's aim reaches when started from the generator's takeoff (targeting)
  and 3 it doesn't (movement). Chapman's estimate of the non-derived links both R and round 1's engine miss, pooled
  by the frame's weights, as a share of nd R-real (B4's measure, the review's fix): e7 1.1 % (95 % 0.1-2.1), a5
  15.3 % (-3.4-33.9), w1 57 % (6-108; 8 R-real and 6 generator links in its 300 pairs), so B4's 5 % holds only on
  e7 and NS.4's condition is met on a5 and w1 by point estimate.
  Of six known links checked (w1's fire wall both ways, its shoreline rollthrough and torpedo skip, w3's ice-climb
  flutter, `KNOWN_REAL`'s w3 lake link) R found one (the lake link, at rank 3) and the generator one (the fire wall
  town to beach, which round 1 also has). An independent measure (its measure; fresh caches, the
  lane and main side by side under one load, e7's first 50 nd-k0 and 50 nd-air3 pairs) matched every row: kernel-R
  kept 27 of FastL3-R's 29 real pairs, 28 (96.6 %) with the re-fly, at 9.42 CPU-s a pair against 20.58 (x2.18) and
  27,097 L3 ticks a real find against 65,900 (x2.61); the lane's script gave main's FastL3-R the same job keys and
  verdicts on all 100 pairs with no job run anew, so it loses no FastL3-R find; the three lost pairs are lost again
  on main with R2.19k, so q stays no go.
- **The truth set's bulk (Step R2.19c2b; D845, D876, PLAN-v3's c2b):** `devkit/reach/reach_truth.py run --strata` takes
  c1's slack-band strata, `nd-air3-near` and `nd-air3-far` (nd-air3 split at 20 m inside the envelope, as the pair
  stage's tiers are), and `recall` weighs nd-air3 by band and counts a pair real when any name's R held it
  (Step R2.19c2b's report). Priced first (D876): kernel-R took 2.40 CPU-s a pair on main
  (c2a: 8.92), so the quota fit with no cut. Kernel-R then ran 6,298 more pairs (3.8 CPU-h, 0 errors, 0 audit
  differences; its `--refly` never flew: since R2.19p the launch families run in C past the re-fly's spy, so all
  2,876 targets came back unmatched; fixed after, the frozen rows stay kernel-R alone) to at least 100 R-real
  links a non-derived stratum on each thick level: e7 nd-k0 102 of 375 pairs, near 102 of 331; a5 103 of 749 and
  130 of 894; w1 100 of 2,843 and 107 of 1,706; the far band a thin 100 pairs a level, 0, 0 and 1 R-real
  (w1.Z1104>w1.Z004, 0.76 m outside the band). The rows are frozen as
  each level's private `truth/bulk.jsonl` (sha12 e7 e610d40056c0, a5 0c2ae731df2f, w1 21e8f827f76d). Main's engine
  against them (R2.19g3's bench graphs; w1's truth rows past its 10 % slice got main's pair stage and 10 m
  escalation of their own), non-derived recall pooled by the frame's weights (Wilson 95 % on the Kish number): base
  route e7 20.9 %, a5 47.0 %, w1 22.8 %; at 2 m e7 56.0 % (47.9-63.8), a5 76.9 % (70.6-82.1); at 10 m e7 86.2 %
  (79.7-90.9), a5 92.5 % (88.1-95.4), w1 81.8 % (73.5-87.9; nd-k0 94.0 %, near 85.0 %, its far link missed);
  with c2a's calibration of kernel-R alone (it kept FastL3-R's nd-k0 29/30, nd-air3 16/18; the engine credited
  none of those it loses) 78.8, 84.2 and 73.6 %. So B3's non-derived 85 % holds at 10 m by the point on a5 and e7,
  corrected on none (a5 0.8 short), and not on w1.
- **The kernel's ports I: pushes, swimming and springboards (Step R2.19e; D835, D845, D846):** the kernel now runs the
  game's volume query each tick, the air's pushes, the swim and the springboards (`docs/SIMULATOR.md`,
  `docs/RE_MOVEMENT.md`); a push or water volume that moves or switches still flags to FastL3 (R2.19h1's). First the
  seat attributed R2.19d's losses by cause (Step R2.19e's report; round 1's witness of each lost
  edge replayed on FastL3 and on the kernel): none of its 191 kernel-alone losses, 9 backstop losses or 2 lost truth
  pairs came from a push, a current, water or a springboard, and only 1 of 47 silent held-out launches did. They are
  the aims' later passes and the refinement steering on kernel rows (66), contacts and numerics (36), slope and slide
  edges (28), clips handed to L3 (lip, step-up, roll: 34), starts (13), the hard landing (10) and other clips (4). So
  the ports buy speed, not recall. The game's exact air blend (x through a float twice: bit-equal with FastL3 for 16
  ticks against 1) lost a5.Z018>a5.Z250 even with the backstop, a knife-edge landing after a contact the kernel's face
  order only approximates, so the air outside a push volume keeps R2.19d's rounding (D835); its review found the
  swim's depth is the deepest water volume's, not the first's. On R2.16e's bench at the fixed head (R2.19l's tree,
  5-min loads 20-48) the kernel route took 5.76 CPU-s a find (R2.19d 6.66; x7.2 against round 1's 41.47) and 6,570 L3
  steps a find (9,633); w1 5.57 with its flagged launches 29.0 % -> 11.1 % (an independent side-by-side of the first
  cut: x1.20 against main under one load, all of it w1's). It keeps 97.62 % of round 1's per-edge finds alone and
  99.86 % with the backstop (7.24 CPU-s a find against 8.36), as main does with R2.19d's review fix: with the backstop
  every edge is main's (10 derived edges lost: e7 1, f2 3, w1 6), alone e7 and a5 too, f2 2 more and w1 2 fewer
  (aims whose pass-3 launch main's kernel handed to FastL3; the backstop finds them). The truth pairs are main's (e7
  31/52, a5 31/41, w1 29/35: e7.Z123>e7.Z098 and a5.Z122>a5.Z052 still lost), so D846's condition stays unmet and
  FastL3 stays the default. 16.7 % of drift-audited settled kernel launches end over 0.5 m off FastL3's run (main's
  17.7 %, another sample by key: no change); at the first cut a held-out sample of 1,600 round-1 launches from
  FastL3's own starts agreed in 1,208 (1,172), flagged 244 (280) and parted silently in 148 (148). L3's share of all
  ticks stays 11-26 % a level (the plan's 12 % bar: a5 only); e5's push slice flags pushes half as often (1,598
  against 3,498).
- **One re-key stack: the lift's clip, the updraft's rules, code keys, audited holds and the retarget stage (Step
  R2.19f+; D835, D845, D846, D851, PLAN-v3):** the kernel plays the lip lift's clip and walks on the tick after any
  clip's last row, lands nothing in an updraft, and gives a mover its own springboard height; the step-up's clip port
  was reverted (its placement is not the decision's point: it lost two finds to the parent), so step-ups, rolls and
  ice still go to FastL3. Keys hash code, every hold answer is stamped and audited (base L3 42 of 42, x87 25 of 25 the
  same), and g1's `sample --retarget` aims at what the graph left. On R2.16e's bench in a fresh cache
  (Step R2.19f+'s report): 4.07 CPU-s a find alone and 5.34 with the backstop (the
  parent's record 5.76 and 7.24, another day's load; against main at one load on e7 and a5, x1.14 and x1.20), 5,727
  L3 steps a find (6,570), 7.9 % of launches flagged (11.1 %); round 1's per-edge finds kept 97.47 % alone, 99.86 % with
  the backstop (the parent's) and 99.93 % with the retarget too (every level 99.83 % or more); against the parent's
  records 3 derived edges lost with the backstop, 2 with the retarget, which gains 24 (the parent re-run at 97821ee7d
  on e7 matched R2.19e's records edge for edge). A retarget's witnesses take a zone pair's tries of their own, so it
  never pushes out a witness that stays. Each retarget class gives 68 or more zone links a kernel CPU-h. c1's truth
  pairs: 91 of 128 with the backstop (the parent's), 94 with the retarget; e7.Z123>e7.Z098 and a5.Z122>a5.Z052 still
  lost, and only 1 of c1's 7 dp misses found (five never came within the 3 m gate: g3's tiers). Drift stays 8-33 % a
  level. D846's condition stays unmet: FastL3 stays the default.
- **The pair stage, pass 1 (Step R2.19g2; D845, PLAN-v3's g2):** `devkit/reach/engine/candidates.py` now holds the
  truth set's frame and R's pair aim, which `devkit/reach/reach_truth.py` imports: R's aim jobs are the same, job for job
  (all 342 pairs frozen on e7), the eight frames made again equal, and no frozen row or frame file changed
  (Step R2.19g2's report). `devkit/reach/reach_engine.py sample --pairs` aims pass 1 at every
  non-derived frame pair the graph lacks at its kit: R's own aim, keyed apart (`pair:nd`: no `aim.MORE` confidence, so
  pass 1 alone, and no `aim.py` edit, so no re-key), in groups of at most 32 targets of one from-zone, kit and tier
  (nd-k0; nd-air3 at slack -20 m or less; the rest), in that order (each group's expected links named: the tier's
  pass-1 hit share in R's frozen rows of pairs the graph lacks at their kit, else those rows' nd R-real share x 0.4,
  else a prior), then the frame's seeded order; `--budget` ends the queue and the plan names what it leaves by tier
  ("not searched", D845), `--slice` takes each stratum's seeded first fraction. Every level now has a frame: the 14
  new ones took 39-92 s each, 171-616 s where the level's reach model was built first (a1, f3, f4, life, w4; the
  airship's in its 87 s), and the 22 hold 240,694 nd-k0 and 1,547,402 nd-air3 pairs. A smoke on e7 (the backstop
  plan's graph, 2 workers) ran two 32-target nd-k0 groups on the kernel: 4 of the second's targets held at kit by pair
  witnesses, the rate's 3.2 expected, and none of the first's (26 of its aims' kernel hits died on FastL3's confirm).
  On R2.16e's bench after the retarget (kernel route, a fresh cache; e7 and a5 whole frames, w1 and f2 10 % slices)
  the stage aimed at 38,375 pairs for 3.5 CPU-h (0.33 CPU-s a target with its graph reads) and added 1,845 zone links,
  761 a CPU-h on e7, 396 on a5, 486 on f2 and 414 on w1 (nd-air3 "far" the lowest, 130-351), losing none (a pair job's
  witnesses take a zone pair's tries of their own, as a retarget's do: before that, three of a5's held pairs went).
  c1's nd R-recall rose from 33 to 53 % on e7 (16 of 30) and from 64 to 71 % on a5 (10 of 14); on c1's 302 nd pairs
  the kernel's pass 1 kept 17 of FastL3's 19 pass-1 finds. 66 % of the stage's kernel aim hits died on FastL3's
  confirm (the kernel models no damage), and its two graph reads took 20-55 % of its wall. A second seat's re-run of
  e7 and a5 from no pair record (the real `run`, audits on: base L3 22/22 and 27/27, x87 15/15 each, 0 differ) made
  the same graphs, witnesses included, and lost no derived jump or flap edge (a5 1,009 -> 1,020 of 1,601 found, e7
  1,890 -> 1,910 of 3,023; 380 and 724 links a CPU-h with its audits; Step R2.19g2's measure).
  Of PLAN-v3's bars e7's 50 %, 0 lost and 200 links a CPU-h are met; a5's 80 % is not, and pass 1 can't meet it: it
  can reach 11 of a5's 14 (78.6 %; e7's 17 of 30), the other three being R's pass-5 finds (g3's escalation). Nor is
  18 of the 19: e7.Z133>e7.Z198 (no kernel outcome lands in the to-zone) and a5.Z184>a5.Z015 (each of its kernel hits
  dies on FastL3's confirm). The dying confirms cost about 3-4 % of the run's CPU.
- **The controllers in C (Step R2.19p; D843, D845, D893, PLAN-v3's R2.19p, NS.1 = SF5):** the kernel route runs each
  launch family in one C call (`reach_native/controllers.c`'s copy of `macros.launches`, R0's `_Run`, `aim.Aim` and
  `aim.Sched`; `docs/SIMULATOR.md`), the Python controllers kept as the L3 route's and the reference
  (`AZURIK_REACH_CONTROLLERS=py`, pinned by `backend.SHADOWS`). C against Python on one commit
  (Step R2.19p's report; nice 15, 6 workers a side, both sides at once, 5-min loads
  16-22): e7's fan slice (843 jobs) and 5 % of its aims (138), twice, and 100 aims and 100 fan jobs each of w1, a5
  and f2: all 2,562 records the same, kernel counts and drift audits too. A launch tick cost 0.9-4.0 µs in C (6.5 at
  most with its outcome's making) against 10-82 µs in Python; e7's slice took 5.3 % less CPU (6.0 and 4.7 % by rep:
  the fan stage 6.6-8.2 %, the aims 1-2 %, whose cost is FastL3's floors, confirms and holds); after the rebase onto
  R2.19f+ e7's slice again gave 981 of 981 records the same. The first cut put `-ffp-contract=off` on the whole
  build. On R2.16e's whole bench (kernel route, modelled backstop, g1's retarget) against main at one load, each
  stage on both sides together, it took 6.06 CPU-s a find with the backstop against 6.43 (-5.8 %; alone -7.8 %, with
  the retarget -5.5 %; a5 -14.6 %, w1 -5.9, f2 -3.5, e7 -2.2; an independent re-run of e7 and a5 gave -2.9 and
  -13.5 %, the bench -5.7 %), a C kernel tick 2.0 µs with its controller (1.0-2.25 µs on the re-run's slices, 1.9-4.6
  with the outcome's making; Python's 10.8-11.8), L3 steps and kernel ticks a find within 0.5 %. But the flag moved
  the kernel's own floats too: 11-22 % of a level's aims and fan records parted from main's, and 5 derived edges
  were lost against main with the backstop (w1's; 1 of round 1's) and 8 with the retarget, 11 gained each, none of
  them the controllers' doing (the head's build with the flag dropped gave main's records and the C controllers the
  Python controllers'). So the controllers turn contraction off in their own code only (a pragma after their
  include of `kernel.c`; the build's flags are main's): on new a5 and w1 slices (fan jobs, aims with and without an
  envelope schedule, refinement and small-fan jobs; 680 records) every record is main's with the C controllers
  running (a C kernel tick 2.2 and 2.5 µs there), so the route finds main's edges, 0 lost against R2.19f+ [from
  the records], and its CPU a find is the first cut's within its C launches' and outcomes' 2.1 % of the bench's CPU
  and the 0.5 % of L3 steps the flag had saved: about 5 % less than main's [inferred: the fixed build is not
  benched]. R2.19f+'s three finds lost against its parent (AZ-826) stay as they are: p's records are R2.19f+'s (the
  first cut had found w1.Z728>w1.Z1700 again by the flag's floats).
- **The escalation (Step R2.19g3; D845, PLAN-v3's g3):** `candidates.escalate` and `devkit/reach/reach_engine.py sample
  --escalate M` take R's later stages to the pair stage's near misses: a pair the graph still lacks at its kit whose
  pass-1 landing or first touch-down came within M metres of its to-zone (PLAN-v3's ladder 1, 2, 3, 5, 10; read
  from the pass-1 record, as R2.20's map-recall gate measured it, so choosing runs nothing) gets the same aim with
  passes 2-6 (`more`), and where those fail the refinement's launches twinned to the pass-1 aim; k0 first, then
  nearest; the farther pairs wait for a wider tier, named in the plan. No `aim.py` edit, so no key moves; its
  witnesses take a zone pair's tries of their own (so it never pushes out the base's or the pair stage's). A smoke on
  e7 at 2 m (kernel route, a scratch cache, an empty base so every frame pair counts as lacking;
  Step R2.19g3's report): the pair stage's first 58 nd-k0 aims held 8 pairs at kit; of the
  50 left, 13 came within 2 m (37 wait: 4 at 3 m, 9 at 5, 9 at 10, 15 farther); their escalated aims held 6 and the
  7 refinements 2 more (8 of 13) for 27 CPU-s, 0 zone pair ranks lost. On R2.16e's bench after the pair stage
  (kernel route; e7 and a5 whole frames by tier, w1 and f2 10 % slices at 10 m in one stage; 19.9 CPU-h with the
  base; Step R2.19g3's report) each tier's band gave 57-508 zone links a kernel CPU-h (the
  lowest a5's 5 m k0 [inferred: a kit's share by its kernel ticks]; to 10 m e7 1,357 links for 3.6 CPU-h, 379 a
  CPU-h, a5 419 for 2.5, 165; w1 456, f2 503), the graph reads 40-55 % of a thick level's tier. c1's nd R-recall
  went on a5 from 71.4 % (10 of 14) to 85.7 % at 2 m and 92.9 % at 10 m, on e7 from 53.3 % (16 of 30) to 63.3 % at
  2 m and 90.0 % at 10 m (pooled 27 -> 43 of 48: D851's +33.3 points, speed x1.00 since no keyed code moved). g2's
  two kernel misses are found at 2 m, each by a FastL3-confirmed witness (e7.Z133>e7.Z198 at k0, its pass 1 0.73 m
  off; a5.Z184>a5.Z015 at air3, 0.12 m). Of c1's 48 R-real nd pairs the route to 10 m holds 43: 3 lie past 10 m and
  2 are the kernel's (FastL3 finds them; e7.Z151>Z061: no kernel outcome lands in the to-zone; e7.Z121>Z065: its one
  landing there a flagged launch that dies). No derived jump or flap edge or zone pair rank was lost against main
  (e7 1,910 -> 1,948 of 3,023 found at 10 m, a5 1,020 -> 1,043, f2 4,351 -> 4,368, w1 5,190 -> 5,216). Its measure
  (its measure) found node, touch and MAY edges lost edge by edge (e7 at 10 m 8 node edge ranks, 4 touches
  and 27 MAY; a5 at 2 m 5, 8 and 2): an escalation witness that stayed, sorted ahead of a kernel candidate main's
  hold read, ended the hold before that confirm, whose touches, MAY and node edge went. So the hold tries the
  escalation's witnesses after every other; re-read on the bench's records (its records) a5 and e7 at 2
  and 10 m lose none against main (e7 at 10 m 3,144 -> 4,360 node edges, 852 -> 1,206 touches, 963 -> 2,357 MAY;
  the same zone pairs, recall and the two finds), f2 and w1 by construction [not re-read]. B3's nd 85 % takes the
  whole ladder, both kits, k0 first: a5 meets it at 2 m, e7 only at 10 m (73.3 % at 5 m). Its all-level price
  [inferred, an upper bound: CPU a pair stage target x every level's nd frame pairs, as g2 priced its stage] is
  452-516 CPU-h (k0 alone to 10 m 160-190; 2 m k0 32), on top of the pair stage's 129-228, against B5's 111: the
  ladder doesn't fit one run, as PLAN-v3 read. A known flaw (D835, not a loss against main): a wider tier's quicker
  witnesses that leave displaced 11 zone pair ranks a narrower tier's escalation had found (e7 7, a5 4), inside the
  escalation's own 3 tries.
- **The deep pass's round 1 (Step R2.19r1; D851, PLAN-v3's rounds and B7):** a re-profile of a find on main by
  map-time's method on its 368-job slice (kernel route with the FastL3 backstop;
  Step R2.19r1's profile, its report): 2.34 CPU-s a find, FastL3 72.0 % of it (map-time's slice composed the same way 8.41,
  the bench 8.36). The largest measured share is the roll (BLACK's root-motion roll, the kernel's `STOP_ROLL`; all
  of it the refinement's roll jumps) at 16.3 %, an upper bound, since a run carries one stop code and a roll launch
  that later meets a step-up or push stays flagged; then the serial driver 14.7 % [inferred: one plan's graph build,
  scaled], SF3b's x87 data movement about 14 % [inferred], the holds and in-run confirms 13.7 and 4.9 % (D845's
  witnesses, not candidates), the backstop 12.6 % (the owner's reading: measured, not changed), cutting doomed
  flights short at most 8.7 %, idea 7's other ports step-up 5.3, push 5.1, L3-mode families 4.2 and ice 1.9 %, a
  kernel touch stage 3.1 % and idea 5 0 % of a first run's find; x87 is 28-36 % of a worker's samples (map-time's
  42-48 %). The roll port is a stack (RE of its ground and air paths, its end and the jump out of it, a measured
  root-velocity table, the kernel and controllers, FastL3 agreement probes, a key-moving bench), and no other share
  had a one-seat exact build worth a round (the serial driver's exact cuts about 1-3 % of a find; SF3b's first half
  measured slower in R2.19m; the holds are D845's; the backstop is the owner's), so the round built nothing
  [default D115]. Its check (its check) found head = main: every record's sha12 the same on the slice (336
  of 336 kernel jobs on all four levels, 92 of 92 FastL3 jobs on e7), an interleaved A/B +0.41 % on the kernel route
  (noise about ±2 %), and c2b's recall re-read byte for byte (0.0 points on the frozen set). A round that builds
  nothing doesn't count toward B7 [default D115; the letter would count it], so the count stays 0 of 2. Next: the
  roll port in its own lane, then step-up, push and the serial driver.
- **The deep pass's round 2: the roll port, reverted (Step R2.19r2; D851, D835, D846, D931, PLAN-v3's B2 and B7;
  Step R2.19r2's report, its check):** round 1's largest share, BLACK's roll, was
  measured first on map-time's slice (365 of 393 roll flags hit no other stop: 15.0 % of a find removable), then
  ported to the kernel from base L3's rows (RE_MOVEMENT's "Roll, not run" §10: 21 rows of forward root motion
  turned by the stick's yaw, all 12,659 hooked rows equal; the chain from row 19, the walk the tick after row 20).
  On the slice 342 roll launches ran on the kernel and every other outcome (1,841) and placement stayed main's, and
  an interleaved A/B at one load cut a find from 2.338 to 2.136 CPU-s, +9.4 % speed (the check's own +9.7 %;
  +7.9 % on the port's own finds). But the bench lost finds on every level: derived edges kept of main's e7 97.6 %,
  a5 99.2 %, f2 99.4 %, w1 98.3 % (173 lost; 495 zone ranks, 474 of them main's roll jumps by FastL3), and nd
  R-recall on c2b's frozen set at 10 m fell e7 86.2 -> 80.5 %, a5 92.5 -> 92.3 %, w1 81.8 -> 77.9 %, pooled
  84.58 -> 80.51 % (-4.07 points; at 2 m -3.31). One cause: the kernel's roll lands elsewhere than FastL3's run of
  the same pads (its move code rounds each of 21 ground rows' contacts differently; it models no hit reaction), so
  the pair FastL3 reached gets no candidate and is never flown. B2 fails (under 99.5 % on every level, and recall
  falls, so neither D846's allowance nor D931's trade applies [default D115]), so the port is reverted in the same
  step (D835): the kernel hands a roll to FastL3 again, its code and key main's. 0 counted kernel witnesses
  throughout (D845). The round lands no speed, so B7 stays 0 of 2 [default D115, as round 1]. Cost 16.9 CPU-h
  (bench 16.3 with w1's extension, A/Bs 0.4, the measure and gates 0.25; plan 20.7). Left for a later round: a
  kernel roll's FastL3 confirm credited to the pair FastL3 itself lands in, or the kernel's contact rounding closed
  to the game's (the walk's drift too), each then re-benched against these numbers.

Known flaws, kept for later passes (D610): rigs stand still at the snapshot's pose and enemies don't move (player
ticks), one snapshot's world (its gates and toggles) stands for all, the fan holds the stick and presses only Y
(rolls and recasts are only in the refinement; no release, air attack or catch charge: R2.16d), the predictive
control knows no walls or roofs, and a launch that settles on a narrow ledge's brink may slide off where a
player would steer. The
engine's face list misses floors L3 stands on, so the aims ask L3 itself (their targets and starts); a derived
flight none of whose aims finds a body standing in its zone near its landing or takeoff, where no launch lands
either, is the derive's phantom (AZ-723). A zone pair's hold tries its 3 best witnesses a rank, so a rank whose 3
best all leave goes even where a fourth would stay, unless an aim's hit held as it was found stays (since Step
R2.16e: that hit ended its job, so the hold falls back on it); since Step R2.19k an aim's hit whose own hold left
takes none of the 3, and since Step R2.19f+ neither does a witness repeating a kept one's string (a refinement's
twin: same place, kit and pads, so the same answer), and a retarget's witnesses (`sample --retarget`'s) take 3 of
their own, as the pair stage's do (`sample --pairs`', since Step R2.19g2: its aims that left had pushed out three of
a5's held zone pairs) and the escalation's (`sample --escalate`', Step R2.19g3), which the hold tries after every
other, so one that stays never ends a hold before a kernel confirm whose touches, MAY and node edge count. Positions
and strings stay in the private cache.

**The rigs' triggers (Step R2.19h2, D847).** What starts each moving solid is read from its level's wiring by
`devkit/reach/engine/triggers.py` (the motion nodes of [`RE_XBE.md`](RE_XBE.md) § "Rig triggers"): `load` (it
moves with no event), `wired` (a condition over the wiring's atoms, with `global:<name>` for a latch's global an
earlier level set), `never`, or `undecoded` (parked by name, with the node types it rests on).
`devkit/reach/rig_triggers.py witness` is the rigs-only re-run: in whole steps from each level's start snapshot it pokes a
start's atoms where the game's link pass writes them and counts a rig witnessed when its deck, where the game
collides with it, leaves the untouched run. The derive's exported `rigs` keep their "trigger not decoded" label
until the logic intake (R2.16g) reads these; the first all-level run's rigs (R2.19h1) park what stays undecoded.

**Rigs in the first all-level run (Step R2.19h1, D845, D847).** `devkit/reach/reach_engine.py rigs`
(`devkit/reach/engine/rigs.py`) records each level's rigs in FastL3 whole steps from its start snapshot (3,600
ticks; a read trigger that leaves a deck still is poked and recorded from the poke; the recording, each poke and each
trip on a scene FastL3 that never ran, since a reset doesn't undo all of a long run) and gives each a verdict: it
cycles (its period), moves along a path from load, stands still, is toggled by a term of its start (a link through
it carries that term), or is **parked by name** with its reason (an undecoded start, a read start no poke moved, no
collision object): a parked rig makes no rig link, and a jump or flap witness touching one parked for an undecoded
trigger is out of the logic until a rigs-only re-run decodes it. Round each exported deck that moves, the native
kernel with the decks posed at its clock orders the work (boards from each nearby zone's takeoffs at every 15th tick
of its span, alights from its top, links joined by the ride), and only a FastL3 whole-step trip, board, ride and
alight held 60 ticks in the to-zone, counts a rig link, and only where it holds again alone on a new FastL3. With
`--rigs`, a jump or flap witness its frozen hold kept that a rig moving while it flies touches at its load pose, or
crosses on its swept path, counts only where its whole-step replay holds (the phase loop: idle 0, 15, 30 ... ticks
first, at most 8 tries; the witness then owes that idle); one no moving rig meets keeps its frozen-world witness, and
one touching another parked rig names it. On R2.16e's bench (Step R2.19h1's report, the
review's and the measure's fixes in) all 33 exported decks were decided (the 4 parked before were toggled once each
poke ran on a new FastL3) and 25 rig links held alone in whole steps (5 on a5: its two bobbing chains and the
airship's control elevator; 20 on f2's geyser lid; none on e7 or w1), the same on w1 from one worker and from three.
Of the witnesses their frozen holds kept, 168 met a moving rig and 116 of those held in whole steps, 38 touching a rig
parked for an undecoded trigger left the logic, and finds at kit went from 7,198 to 7,186 (a5 7, f2 5).

