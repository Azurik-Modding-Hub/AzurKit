# Pending work

Every task still open when the 2026-11-08 session ended (Step 4.32, which
rewrites Step 4.23's list). When it was written (2026-11-09, about 04:00
PST), `main` was 6a99347f: stack 2 had landed (the Variants editor, the
whole Modkit port and its test-port lanes 4.27-4.29). v1.0.1 was the last
release, and stack 3 (4.31, then 4.30) was queued on `main`. Modkit's
checkout was still on this Mac, to be deleted this session (D1171).
Everything Modkit had is now AzurKit's or is retired by name in group 13.
Groups 4 and 5 hold what this session meant to finish before it closed:
check each one before acting on it.

Step, D, AZ and Q ids are the private ledger's. When an item is done, drop
it in the commit that does it, and add new items to the group they fit.
Nothing waits on the owner except the owner-only acts in group 12 (D115).

## 1. First: the Variants editor's first Check (D1181, D1192)

The next session starts here (D1192), so 1.1 can follow.

1. **The target** (D1167, D1181): a first Check with game data takes well
   under a minute on the site. It is measured on the busy box, beside other
   projects' load (D1107): no idle rerun and no budget change. Optimization
   rounds go on until it holds with margin.
2. **Where it stands:** 60 s in the app (A92) and 113 s in WebKit (S78) at
   load ~67, in `main`'s full run before stack 2. Stack 2's full run read
   97 s and 102 s. Both runs read the content repo as published (booblord
   v5), which ships no Check parts.
3. **What the shipped parts do:** with booblord's Check parts installed
   (content v7, 2.2), the 4.6p lane measured S78 at 9-16 s in WebKit,
   Chromium and Firefox (medians 10-13 s), A92 at 4.7 s and the capped site
   at 5.16 GiB. So D1167 was met for her. A first Check with no parts is
   nearly a full dress (about 103 s native), and beamlord, community
   variants and every own copy but booblord_high's get no parts. Recommended first round (D115): push
   the parts with 1.0.2 (2.2), measure S78 and A92 with them on the busy
   box, then cut the no-part path.
4. **Levers named so far:**
   - round 6's kernels: an edit's first Check is nearly a full dress (a
     Scale x1.2 edit takes 31.5 s in the app, an estimated 75-90 s on the
     site);
   - a narrower key for a texture or colour edit, which redoes both
     restyles and the LODs (about 15 s, 4.6n);
   - beamlord's Check parts in a later content version (12-14 s native
     now; optional);
   - no perf row times a Check after an edit: add one.
5. **The parts' download:** a first Check's 24.5 MB of parts come with no
   bar, and no pytest drives a real browser through a shipped fetch (S78 is
   the only proof).
6. **4.6p's minor points:** `worker.mjs`'s `fetched()` uses a synchronous
   XHR with no timeout (give it 60 s); `shipped.part` marks a source down
   for 60 s on any OSError, even a 404 for one part; `sdk._later` lets
   `$AZURKIT_CONTENT_SOURCE` win over the entry's recorded source.

## 2. Releases and content

1. **1.0.2, if it didn't go out this session** (D1180, D1186): it ships
   from `main` with the Variants editor as it is. Its conditions are met:
   stack 2 and 4.27-4.29 are on `main`, and stack 2's full run passed every
   test (1,993; vanilla 887, europe 66). Its perf stage failed only A31 and
   A60 against the release (3.2).
   - Steps: the version commit, then
     `scripts/devlog.py --release TITLE --remove`. Run CI on four OSes
     (D1170: a test that passes its one rerun is a flake). Then the
     runbook's scripts, the tag, the publish, and showing the owner the
     notes (D1132). The security checklist is a quick look (D1162).
   - After any rebase, re-check the developer log's union merge.
   - This CI is the first on the port's code (D1176 waived CI before the
     delete). Read the Windows proof rows there: 4.5w, the 4.6k review's
     F1, and 4.13a's D1 and D2.
2. **The content push** (4.6p, 4.6r): the published content `main` is still
   v5. The content clone's local branch `p2/stack2` (f68aa69) holds v7:
   booblord's 84 Check parts, 117 MB of her entry's 133. Push it once a
   released site and app read `content.later` (1.0.2); before that,
   v1.0.1's apps would fetch parts they don't read. Push by the
   Azurik-Modding-Hub URL: the clone's `origin` still names the old
   Azurik-Testing archive, and changing it is a git config change, so
   leave it. Its `p2/next-stack` (v6) and the 4.6p and 4.6r content
   worktrees are superseded. The clone also holds an untracked
   `scripts/__pycache__`.
3. **1.1** follows once group 1's target holds (D1192).

## 3. Stack 3 and 4.31's outcome

1. **Stack 3**, if not landed: `p2/stack3` is 4.31's perf.py fix, then
   4.30's port leftovers (the drop-in WAV folder deleted, Modkit's
   dead-code guard, the resolver's reach refusal, the spot-need tips), on
   `main`. Its gate is changed-area: its `src/` and `web/` changes pull in
   the wheel, Pyodide, browser and frozen-app files and the perf gate's
   characters, randomizer and tracker groups. This list (4.32) lands after
   it.
2. **A31 and A60 were load, not code** (4.31): stack 2's receipt failed
   D1170's release rule on them (A31 166.5 s against the release's 118.8 s,
   A60 199.5 s against 115.0 s). 4.31's paired runs in one window put stack
   2's CPU at or under `main`'s (A31 82.8 against 103.3 CPU-s, A60 102.2
   against 107.4), while the wall time swung with other projects' load.
   - 4.31 also fixed perf.py's rerun, which dropped the first sample (a
     rerun's samples now join the first ones). With that fix, stack 2's run
     would still have read A31 at 204.7 s and A60 at 174.1 s at that load.
   - So a gate on a busy box can fail these two again. The cure is round 5
     (8.22), never an idle rerun or a changed budget (D1107).
3. **4.30's perf watch:** every tracker op now sends `world()` with the
   spot needs: 108,878 B of JSON, 69,392 B of it needs, 2.8 times what it
   was. Read S18-S22, S70 and A23-A25 on stack 3's gate.
4. **4.30's prose nits:** `characters/draw.py:299` and
   `randomizer/art/draw.py`'s module docstring and `:289` still name the
   deleted `body_preview` and `draw_previews`, and `draft/tiers.toml`'s
   comment names `tier_gap`. The art file's edit moves ART_VERSION, so it
   goes with the next art re-record; `tiers.toml` is in the derive stamp.

## 4. Modkit's delete and the switch, if this session didn't finish them

When this list was written, Modkit's checkout was still in place and none
of these was done.

1. **ModelKit's re-point** (4.15a8, D1183, D1188): the lane
   `mk/4.15a8-azurkit-repoint` (17637b2, reviewed with no defect) isn't
   pushed. In order:
   - before Modkit is deleted, re-install ModelKit's leak guard
     (`hooks/leak_guard.py --install --forbidden`) with AzurKit's
     byte-equal `src/azurkit/core/manifests/usa.json` and `europe.json`.
     Its forbidden list names Modkit's manifests, so once they are gone
     every ModelKit push is refused;
   - `uv run --locked azurkit content install booblord`, or every booblord
     build is refused (her clips and sounds aren't installed);
   - one proof round on `profiles/booblord` on AzurKit's `main`: round new,
     build, measure `--tier gate`, sheet (headless Blender);
   - then push the lane over SSH to ModelKit's private repo's `main`,
     fast-forward its main checkout and run `modelkit install-skill`.
   Never tested there: `model pose`, `model rest` through `kit/rest.py`, and
   v4kit's user build cache. Her new base file sits in that step's
   evidence, outside ModelKit's repo. Nit: `test_azurik_adapter`'s runner
   stand-in still handles `--export`.
2. **Memory** (D1187, D1171): copy the shared memory folder to AzurKit's
   project slug, point AzurKit's and ModelKit's `autoMemoryDirectory` at it
   (both still named Modkit's slug), keep the old folder as history, and
   show the owner the MEMORY.md diff in chat. The resume pointer (still
   session 4718988a, 11-01) and the repo-layout memory change with it.
3. **The xemu fixtures** (D1177): rename the fixtures folder to
   `Azurik-fixtures` beside the checkouts. Rewrite the absolute paths in
   its `xemu.toml` and that file's line in its `SHA256SUMS.txt`. Make the
   user data folder's `xemu-fixtures` link (devkit's harness default),
   check the sums, then run a smoke boot. 4.17a's report has the commands
   and the revert.
4. **Tags** (G8): `oracle-rando-6` at 8bfef0ca6 (AGENTS.md cites it) and
   `modkit-final` at Modkit's last commit, pushed to Modkit's GitHub repo
   before it is archived.
5. **The delete** (D1171, D1189): G11's checks from AzurKit inside the
   session. Then remove the one exact Modkit checkout path, never a glob
   (the `-fixtures` and `-lanes` folders share its prefix), and put an
   empty folder back for the wrap-up; the owner removes it. Leave ghidra,
   ghidra-backups, the evidence folder, the user data folder and the old
   memory folder alone.
6. **Modkit's `$EV` tools** retire with it: fullsuite.py's Modkit path,
   suite_rules.py, suite_graph.py, the modkit profile, landq's Modkit half
   and the `.before-*` copies. Keep the evidence folder's suite-receipts:
   waitfor reads Modkit's old receipts there.
7. **The archive** (D1185): once Modkit's `main` and tags are confirmed
   pushed, archive its private GitHub repo (it stays private, read-only).
8. **Checks that needed Modkit and never ran:** once its checkout is gone
   they are retired by name under D1171, and AzurKit's own goldens stand.
   - 4.6i's end-to-end build: Modkit's `patch` against
     `azurkit build --mods` on the USA image.
   - 4.6r's full build of booblord_high's own copy.
   - 4.6j's Modkit `randomize-full --plan`.
   - 4.13b's effect on the shipped database, and a 1,000-seed soak. After
     the delete the soak can compare AzurKit only with itself.
9. **Residue** (G9): copy Modkit's git-ignored `.claude/settings.local.json`
   and its `.before-2.216` copy into the evidence folder, if wanted.
   AzurKit's own already hides the 18 skills (D1191).
10. **The xemu fork drive's discs** (D1051): its x68 states need their
    discs rebuilt before they're used. Four come from zips. The two fps120
    states have no zip, and their commit 8959dcb2 is on no branch. Keep the
    zips and the README outside Modkit.

## 5. The session's wrap-up, if it didn't run

1. **The handoff log** has nothing after 11-07 13:23. Add the 1.0.1 lanes
   (4.5n-4.5w), D1153-D1193's lanes, the port lanes, stacks 2 and 3,
   v1.0.1's publish (2026-11-09 01:33 UTC, from fe61354) and the delete.
2. **Memory:** add D1171-D1193 and the delete (with 4.2).
3. **A next-session prompt** (the newest is 11-01): it starts in AzurKit,
   with group 1 (D1192) and D1075's read (12.7).
4. **The session's whole run on `main`** after the last landing. AzurKit's
   fullsuite has no `--main --no-credit` form (10.5): run its whole suite
   on a worktree at `main`.
5. Run `prune --session-end`, then `--apply` (D682), and the orphan sweep
   (`$EV/tools/orphans`).
6. Remove the lanes and branches after landing (11.2-11.4).

## 6. Reach

1. **x7's route graphs** (D1172): the L3 store's x7/reach holds AzurKit's
   22 current reach models (13 GB), and route graphs for airship, a6 and
   life only. 4.30's `physics.py` edit moves every route graph's key, so
   once stack 3 lands all 22 are to build: 19 have none and the three go
   stale.
   - Build them from a checkout at `main`, at nice 15, with 4.13f's
     `build_routers.py` (kept in that step's evidence, not tracked):
     `build_routers.py routers 25 a1 a3 a5 airship a6 d1 d2 e2 e5 e6 e7 f1
     f2 f3 f4 f6 life town w1 w2 w3 w4`.
   - About 29 GB, seconds a level. It keeps 25 GiB of disk free, keeps a
     current key and replaces a stale one.
   - Until then `load_router` builds a missing graph on first use
     (2-16.5 s), so nothing breaks.
2. **The 21 retired proof records** (D1175): 33 L3 marks still resolve to
   17 of them, and the planner still counts them as proofs. That was
   4.13f's default (records stay as history, D1173). Reading D1175 as "the
   marks stop resolving" would fail those 33 marks and move plans.
3. **Frozen reach data:** 8 levels stop at "no kept reach model's sample
   is the record's teleport". 4.13a's record replay can't run: all 1,337
   snapshots are gone.
4. **4.13e's last re-points:**
   - AGENTS.md's "Not ported: Modkit's `db-extract`" is stale: devkit's
     `rando db-extract` is ported.
   - The planner loader's refusal says "re-measure: scripts/l3_contact.py",
     Modkit's script.
   - `docs/REACH.md` names only AZ-720, 723, 737, 813 and 826, not the open
     reach issues (7).
5. **The reach backlog** lives in the private plan: R1.23-R1.25, TD.2,
   TD.2b, TD.5-TD.7, R2.19a-j, the improvement rounds, the all-level run and
   R2.16g. D1048 paused it and D1143 froze it. It waits for v2 (D609) and the
   owner's reach budget (D977).

## 7. The open issues from Modkit's ledger

The private ledger (D952) holds Modkit's 29 open issues.

- Inherited by AzurKit (3):
  - AZ-009: level patches address entities by their current name, not
    their vanilla identity (AzurKit refuses a mod file's level patches by
    name).
  - AZ-234: the D-pad field names in the struct header are swapped.
  - AZ-247: the index structs describe 20-byte records, but the loader
    strides 16-byte entries.
- Reach, derive and L3 (20, now in devkit; v2, D609):
  - AZ-342: a touch teleport whose landing hangs in the air is dropped.
  - AZ-373: a gate's sides are misread around a sliver zone.
  - AZ-374: no takeoff or landing on slippery slopes.
  - AZ-376: life's critter blocker is taken for a wall.
  - AZ-382: an L3 search can't start in another room.
  - AZ-395: w2's rope-bridge decks have no floor.
  - AZ-487: town's r1617 exhausts L3.
  - AZ-498: d1's elevator approach finds no route.
  - AZ-527: a w2 search read high pages as zeros.
  - AZ-531: l3_certify's start for an off-graph spot.
  - AZ-538: e5's gear deck and its dock.
  - AZ-579: five e2 edges that no explorer seed makes.
  - AZ-581: e5's jump #3701.
  - AZ-582: hop 5 stands over e6.Z043.
  - AZ-583: town.Z340 is never reached.
  - AZ-626: e2.Z643>e2.Z027 with no logic edge.
  - AZ-723: derived edges on columns with no floor face.
  - AZ-745: no climb out of water.
  - AZ-826: R2.19f+ loses 2-3 finds.
  - AZ-827: the crossfade model's last gaps.
- Models, named flaws under D801 (4, no fix owed): AZ-771, AZ-773, AZ-775
  and AZ-776, clipping at big Bust, Hip and shape-slider sizes.
- Modkit's own, closed as moot with its delete (2): AZ-274 (a Windows CI
  leg hung at 99 %) and AZ-310 (a child forked from a Tk-loaded xdist
  worker spun).

## 8. Flaky tests and perf debt

D1170: a test that passes its one rerun is a logged flake and gets a fix
lane; a repeat or a product failure blocks. A perf op over its budget is a
debt row, and only a regression against the last release's run blocks;
memory peaks stay strict. The gate writes both kinds of row to
`flakes.jsonl` and `perf-debt.jsonl` beside the receipts.

### Flakes, each owed a fix lane

1. `test_characters.py::test_each_variant_case_is_its_goldens_file_for_file_and_resource_for_resource[usa]`:
   "usa.iso: it changed after it was checked (D27)", in the 11-08 20:08
   run. That run overlapped the images' move to their own folder, the
   likely cause [unsure].
2. `test_randomizer.py::test_a_shaped_fills_attempts_at_once_follow_its_priority_and_a_cancel_stops_them_at_their_next_note`:
   "DID NOT RAISE Gone", in the same run; it passed alone and at 8 at once.
3. `test_site.py::test_the_variants_sounds_and_effects_tabs_write_the_rows_and_wavs_the_build_reads_and_grey_what_it_refuses[webkit]`:
   a KeyError on the projectile row's label, in aecdedf9's full run.
4. `test_two_real_engine_workers_plan_a_seed_alike_and_a_change_drops_bs_plan_mid_way[webkit]`
   (D1163).
5. `test_a_call_whose_page_webkit_ended_fails_at_once_naming_the_ending`
   (D1163).
6. The site's Variants test in Chromium: the second page's view wasn't read
   within 120 s (the third 4.6c review).
7. The frozen app's page saves CPython's image `[firefox]`: the Windows
   frozen app's first load (ci30's B).
8. Chromium site tests that failed only when slowed, with no error recorded
   (ci36): save-hashes (367 s), images-rest-walked (130 s) and the seed built
   from the Randomizer tab (297 s). They need a slowed rerun that records
   the errors. Also unfinished: saving while the rest of the image is being
   hashed.
9. Pure-tier tests that failed only when slowed (ci27): test_hosts'
   collected-spot `[chromium]`, the track-this-seed bar `[firefox]`, the
   plan-file spoiler bar `[firefox]` (300 s), and the site's
   call-left-unanswered `[firefox]`.
10. Windows Firefox holds its first request for about 37 s (4.5l, 4.5w): the
    cause isn't shown, and DIRECT isn't shown to prevent the hold.
11. test_dev_tools' flake-stage test went red once beside 4.5d's CI run.
    Name it if it fails again.

### The watch list: name the cause the next time each one fails

12. arm64: the Europe golden `[webkit]`'s five failure modes; SIGBUS;
    WebKit's reload; the WebKit engine trap (ci44); WebKit's JSC fault on
    macOS 15 (4.5p; a Playwright newer than 1.64.1 is the lever, D1133);
    Firefox's timer that lost once, after which a lost edit still waits
    600 s with no Data tab state in `hang()` (4.5g).
13. Intel: page-load stalls; ci19's extra 2 h; WebKit's drawing threads
    outranked (ci21).
14. Windows: ci34's cause; ci39's load failure.
15. WebKit: network-process endings (ci41: a RequestedByNetworkProcess
    ending still costs 120 s); why WebKit leaves the page's process (ci18);
    what triggers the zero-headed message (4.5s: if it recurs, the site's
    character-seed test could use `_page.past_refusal`); ci31's Characters
    stall.
16. Others: ci17's three; what held ci27's GIL; ci37's CI ValueError;
    4.5m's second failure; 4.5n's frozen capped A32; S59 under 20 extra
    threads (4.4bf); WebKit's GPU threads on a 4-core runner; ps under
    `taskpolicy -b` taking 8-12 s while the efficiency cores are busy
    (ci36).

### Test-harness follow-ups

17. `_page`: `load` re-raises an Ended as a plain AssertionError, so an
    ending during a load gets no redo (4.5s, N1). An ending 1-2 s before
    the next call isn't named (N2). The redo keys on the reason alone (N3).
    `within` raises a crashed WebKit page's TargetClosedError without naming
    the cause (4.5p).
18. Silent waits:
    - `Site.__init__`'s new_context, add_init_script and route, and
      `_bare_page`'s new_page (ci14).
    - `_bare_page` callers' unbounded close (ci15).
    - 15 `page.goto` calls that keep Playwright's 30 s (ci16).
    - 372 unbounded evaluates (ci14).
    - 24 bare `page.goto(server.url)` calls in test_hosts.
    - App tests that fetch through an in-process server (37 uses, ci31).
19. AGENTS.md says a load of the site's page has `_page.STALL`, but
    test_site's two loads of a fresh page at ACT don't (4.5w).
20. `tests/ci_durations.json` still names the old private-window test id.
    Refresh the shard table from a full run's log, with Apple Silicon and
    Intel times (4.5u, ci35); the port's tests added many minutes to the
    vanilla tier (4.27b alone about 8 CPU-min).

### Perf debt

21. Rows the gate recorded: A110 in the app at 3.18 s, over its 3 s, and
    S64 in WebKit froze 423 ms in the head start (stack 2's run); A02
    (1.10 s) and A73 (1.52 s) in the app run past 1 s with no progress shown
    (D980; aecdedf9's run).
22. **Round 5 never started** (D1103): ROUND-5-PLAN's ten levers r5a-r5j,
    with r5a (the SND resampler) and r5c (the mesh kernels) first. On their
    bar in stack 2's run: A31 166.5 s, A60 199.5 s, A92 97.5 s, A95 45.0 s,
    and in WebKit S52 140.7 s, S62 139.4 s, S63 138.1 s, S78 102.1 s and
    S81 8.0 s (the first-time reshaped booblord, the Check, group 1).
23. Saves over budget in fe61354's full runs, disk-bound on a full disk:
    - S06: WebKit 3.47 s, Chromium 4.15 s.
    - S49: WebKit 3.72 s, Chromium 4.46 s, lag 3.46 s.
    - S50: WebKit 3.24-3.49 s, Chromium 4.30 s, lag 3.63 s.
    - S72 in WebKit and capped froze 272 ms in the head start.
    - The goal is D1121's strict medians of 2.4 s or less (the 1.0.1
      survey's 4.5c). WebKit's writer has had no R2-a, and 4.4ci49 has no
      commit.
24. Firefox's Saves on their bar: S06 at 6.42-6.57 s, S49 and S50 at about
    6 s (r2c, round 5).
25. A71 and A80 were never read with perf.py on a busy box (ci56, ci57).
    A80's click past its plan is the build (about 1.7 CPU-s).
26. The fill (ci56, ci57):
    - A beside attempt's stop or priority takes effect only at its end.
    - The setup before attempt 0 is serial.
    - `fill.roll` (the GUI's first seed) still runs the twin.
    - A01 shows only its first stage honestly, and 75aa632 has no test of
      its own.
    - `fill.c`'s constants (MAX_REPAIRS and its kin) should come from the
      blob (a later pass).
27. The Characters tab's Reset: its info rows and list colours wait on the
    engine (0.24-1.08 s). Draw them from the held defaults (the 1.0.1
    survey's 4.5k).
28. `gc.freeze` of the kept Logic: measure gen-2 pauses first (the 1.0.1
    survey's 4.5j; ci27).
29. The site's Expert seeds: the costliest plan for about 3 s on Pyodide,
    and no site op times them (4.20).
30. Easy at Hard/Hard with the powers kept: more of its own attempts fail
    (0.74 s median, 1.68 s max native), and it does 5-9 % more fill work
    (4.20's Q1, kept: 12.3).
31. The Data tab's Critters and Items pickers fetch `characters/index.json`
    (31.6 KB) beside the index on open; estimated, never measured
    (4.24b; A39/S32).
32. CI: about 60 SSH sessions per vanilla job, an unmeasured 1-2 min
    (4.5e). ci19's CI times were inferred, not measured.
33. The perf gate reads RSS, not footprint (4.4n's Q2, kept for 1.0.0).
    Revisit it with 9.35.

## 9. Product follow-ups and known flaws

### Known flaws (named under D835, listed until fixed)

1. **Refusals name Modkit's commands:** six messages tell the player
   "`azurik-mod model clips` (or `check`, `import`, `export`) prints it"
   (`_player_variants.py`, `mesh_edit.py`); devkit's are
   `python -m devkit models model ...`. The glTF writer's generator string
   and the generated level data's headers say `azurik-mod` too (changing
   those moves goldens).
2. **"WHITE cycles"** in the build's character log line and comments
   (4.18a): D1153 wants modern pad names (LB). Rewording moves the shipped
   plan answers' digests, so they need a re-record.
3. **Beamlord's notes show decision ids** to players (its `variant.json` in
   the content repo). Write plain notes in the next content version, as
   booblord's were (D1061).
4. **Booblord's own four spin picks** carry their grades across the vase
   drop ("her mesh, not her moves"); no sitting has watched them on the
   vase-less body (4.27d; D835, D856: the owner may want one).
5. **4.20's nits:** a plan Easy keeps from Normal records Normal's attempt
   number; the bar sits at "try 3 of 3" during `normal_plan`; the app runs
   `normal_plan` serially beside the pending attempts.
6. **The save warp and detours:** detours don't count save platforms as
   exits yet (4.20's DESIGN 1.3). 4.18b counts the warp only in D169's
   proof guard.
7. **The chain's drain hit** gives a light reaction where the game gives a
   heavy flinch.
8. **The Live tracker's 'loading' fix** (f07a354) has never been checked
   on a live xemu.
9. **Characters: a pause past REST** still starts a build that the next
   move drops (ci48; capped WebKit reached 6.50 GiB with an 8 s pause). The
   mechanism fix isn't done: a resting list's dropped heavy job should go on
   unkept.
10. **A stale first dress caught in a gap** takes the kill, and the next
    seed's click reads the logic again (45 s).
11. **Site builds without OPFS still copy twice.** Cut mode and S62's other
    mode are unproven.
12. **The arm64 WebKit engine trap:** `Error.stackTraceLimit = 0` in the
    engine worker's realm would turn the page crash into a RuntimeError that
    D1126's restart handles. A WebContent crash still takes the page with it
    (the 1.0.1 survey's 4.5a).
13. **Windows Firefox loses 6-15 GiB of temp disk** through the pack
    golden, and hangs for 60 minutes (D1105). Land a diagnostics-only
    commit first (the survey's 4.5d).
14. **`procpool._peak()` returns 0 on Windows,** so RETIRE and `room()`
    never act there. Read PeakWorkingSetSize through ctypes (the survey's
    4.5e).
15. **OPENERS:** the stale openers' compiled set leaks (in 4 of 10 trials),
    and no test asserts that what they compiled is kept for the drop.
16. **A Firefox Save whose `flat.mjs` fetch never answers stays greyed**
    (4.5u; accepted, since sw.js serves `flat.mjs` on the real site).
17. **A closed Firefox tab leaves its last build's ~835 MB file in OPFS**
    until the next load or a Clear (4.5q; accepted design).
18. **The site's Update fetches every file of an entry** before refusing an
    Update from another source; the app refuses first (ci52).
19. **The HTTPS content clone has no low-speed bound** (ci50).
20. **The Windows and Linux frozen apps are console builds:** `freeze.py`
    passes `--windowed` on macOS only (ci5).
21. **The app's own server answers over HTTP/1.0** (ci42).
22. **A player's image named usa.iso or europe.iso in Downloads** (or one
    `AZURKIT_ISO` names there) refuses the default Save beside it; the
    player picks another folder (4.28a).
23. **A save edit's output guard doesn't fold case on macOS,** so an `--out`
    naming the slot in another case passes (4.28g; Modkit's too; optional).
24. **source_hashes** is checked against both releases' vanilla files
    (4.6i; accepted).
25. **A row's "main colour" can be a tinted near-black** (4.6e; Modkit's
    rule, accepted).
26. **The reach aim's string drifts in rare cases** (`docs/REACH.md`).

### The Variants editor

27. Opening another variant mid-Check drops its answer, but the engine's
    in-flight dress runs on (4.28d). After a drag during the Check, a
    pictures refusal's "Not drawn" note gives way to the nearest note
    (4.29).
28. No test pins that a built-in variant's fits row sha is its recipe's, so
    a stale row changes nothing silently; `garret4_reference`'s hoe fix is
    unpinned too (4.15a7).
29. Old own copies of booblord_high (saved before 4.6r, or by Modkit) have
    no places and refuse. The stores hold reshape parts under old keys, so
    each misses once. Both are accepted.
30. Looks:
    - Save sits 260 px below Save as and Delete.
    - The status leads with the recipe hash.
    - The Notes box has 5 rows.
    - The "colours:" label is lowercase.
    - "Built-in" and "built in" are both used.
    - The search box moves.
    - At 860 px the Models view's Custom row sits under the bottom bar.
    - `colours.mjs` rounds ties away from zero where Python rounds to even
      (the hex box only).
    - Export PNGs isn't greyed before an image loads (D979).
    - 4.21's LEGEND comment; a search typed before the list answers opens
      no fold.
    - The effect colour uses the browser's picker, not Modkit's wheel.
31. 4.6c's leftovers:
    - Undo is missing, and closing the app's window doesn't ask about
      unsaved edits.
    - The page sends `variants()` no manifest, so a built-in shows under
      Community only once it is installed.
    - `variant_save`'s `from` isn't checked as a name.
32. Community-only characters: `resolve()` has no third source, so
    installed recipes that aren't in `variants.json` don't resolve. Resolve
    them third, each held to its sha, and refuse a built-in's name.

### Data, mods and the randomizer

33. There's no page button for mod-template or entity diff; they are CLI
    only (4.6i's default).
34. `docs/RANDOMIZER_DB.md`'s TODOs: whether the page offers to drop a
    renamed skip toggle (4.10), the reserved keys `seed` and `[pools]`, and
    later share-string versions.

### Docs

35. AGENTS.md's perf paragraph:
    - Real Safari ends a closed tab's process in about 20-25 s, even with
      another tab open; only Playwright's WebKit keeps it (the 11-07
      real-Safari read; D1096 asked for the reason to be written there).
    - Its list of later visits misses S73.
    - It still says the site's detailed dress may run out of wasm memory,
      and that "4.4 waits until every site build fits 6 GiB"; 4.4 has
      shipped, and the capped site measures 5.16 GiB.
36. Eight prose cites in `docs/RE_DATA.md`, `RE_MOVEMENT.md` and
    `RE_XBE.md` name Modkit's archived `LEARNINGS_HISTORY.md`, which AzurKit
    has no copy of (4.28f).
37. After a release's `--remove`, `docs/devlog/` is empty and git drops it,
    so DEVLOG.md's [Unreleased] link to it is dead until the next entry
    (Modkit's behaviour too).

### Ideas the session ranked (after the port, D1131)

38. Support plumbing: About links to Issues and Releases, a "Copy details
    for a bug report" button, a "report it" link on D1126's restart notice,
    and an `$EV/tools/inbox` for D1075's read.
39. "Play it in xemu" help after a Save: Machine > Load Disc, and 128 MiB
    for big bodies.
40. Play and Attach have never met a real xemu or the real admin prompt
    (4.6k). Offer the owner a demo (D205).
41. A headline randomizer mode and a speedrun kit (the session's idea
    ranking). When features open again, the open death realm (D201) comes
    first.

## 10. Dev tools, tests and port notes

1. **A src import cycle** (4.13c, 4.13d1): importing
   `azurkit.tools.randomizer.levels` or `draft.geometry` first raises
   ImportError (`art.maps` imports both while they are half loaded).
   devkit's tests dodge it by their import order. Fix it with one test.
2. **The real Blender:** `python -m devkit models blender-check` (4.15a4)
   and `model edit`'s Blender session (4.15a5) have never run on Blender
   5.2.2. lldb can't attach to the hardened Blender.app, so run it under a
   caught SIGSEGV (no crash dialog), or leave it to a seat allowed to run
   it bare.
3. **devkit/rando/impact.py's `Ctx.fill`** tries only Normal's first 20
   attempts, not 4.20's 20 more past a kept way out, so its fill counts can
   undercount for a seed only that repair plans (4.25). A small lane.
4. **Modkit names left as provenance:** src and devkit docstrings cite
   Modkit's module paths (about 530 lines name `azurik_mod` or
   `azurik-mod`); the ones players see are 9.1. `OWNER_DEMO_WHO` still
   reads "azurik-modkit" in `devkit/xemu/queue.py`.
5. **The gate's main runs:** AzurKit's `land.py` and `fullsuite.py` have no
   1-in-5 run on `main`, no session-end whole run and no main-red rule
   (4.17a's default; AzurKit's CI covers `main` today).
6. **`ledger check`** reports 3 problems: PROGRAM.md allocates D973, D976
   and D1033 twice each. Annotate or renumber the second copies.
7. **The toydb settings tests** sit in `test_randomizer.py`, which a change
   to only `generated/t1.json` doesn't pick; moving them into
   `tests/test_rando_db.py` fixes that and drops the second TOYDB (4.28f).
8. **4.24c's span lists:** only X3's tick writes are pinned in the shim
   data test, not every player-model shim's span size (a D10 judgement).
9. **4.15a2's nits:** the spacing in `model.py`'s `NO_SPRING =`, and the
   `.part` file `_import` leaves when a write fails.
10. **Smaller port notes:**
    - qol_alloc_race's 8 sites lost Modkit's per-site labels (4.11d1).
    - drawn_settings drops Modkit's dark_fire draw, so every later draw
      moves (4.13b).
    - 4.13c's nits: an unused kept_logic import in test_reach_model; w3.toml
      in the agent-files HASHED list; the reach-port alias isn't caught by
      the cite lint; a test name that outlives half its claim;
      `derive --svg`'s output guard is narrower than Modkit's; SIMULATOR.md's
      ENGINE_FILES text.
    - The realm cases cache their plans per process, not across xdist
      workers (about 4 CPU-min).
    - The Europe region map can't tell a moved entry in repeating data
      (4.11e).
    - The xemu selftest on CI's macOS legs has never run on a runner
      (4.14a2).
11. **The private plan's other open rows:** P7(b) and "0 logic bugs" for
    v1.1 (D522); R1.26b, Live on Windows and Linux (it needs those
    machines); 4.9's external tools (after v1, D31) and Level Studio's
    onboarding (D107); Q236 (ghidra-sync's variable renames) and Q77/V15
    (Dependabot for `uv.lock`); V21 (the HDD cache) and V22 (a boot hang)
    as unresolved facts.

## 11. This Mac and infrastructure

1. **Disk:** 179 GiB free at writing. ModMG's batches in `/private/tmp`
   are the owner's: never touch them (D1140).
2. **Ours to remove after landing:** the AzurKit worktrees 4.30, 4.31,
   4.32, 4.6r, stack2 and stack3, the content worktrees 4.6p-content and
   4.6r-content, the 128 local `p2/*` branches, and ModelKit's 4.15a8 lane
   once pushed.
3. **Our `/tmp` leftovers:** the 4.6e home folder and the 4.6f take log.
   An empty `/private/tmp/rp411` (11-06) has an unknown owner: leave it
   (D147).
4. **Six landed lane branches on the public AzurKit repo** (D1123's lane
   CI: 4.4ci36, ci37, ci39, ci41, 4.4dx5 and 4.5h): delete them.
5. **The game-data repo's environment allows `p2/*` branches** (D1123):
   keep that while lanes get CI. Its revert is in the handoff log.
6. **nativekit writes each library in place,** so a process that has the
   old macOS dylib loaded is killed. Write the new one beside it and rename
   (4.6c).
7. **Dev-speed levers** dx6 (changed-area gates leave the first-time
   reshape ops to the full run), dx7, and dx8 (the variant golden as one
   test per case), from the dev-speed survey.
8. **CI risks** (no work unless they recur):
   - setup-uv's own uv download sits outside the cache, so an outage can
     fail it, and the first run after a landing misses the cache on each
     OS (4.5t).
   - mcp brings in anyio, whose pytest plugin loads in every session
     (4.11f).
   - pypi.org:443 may no longer be needed in the harden-runner allow
     lists (ci55; low under D1162).
9. **Content size:** shipped parts carry the recording host's floats
   (D1016), so a swap change that moves a part needs a re-record. Each
   heavy built-in's own copy adds about 8.6 MB a release to the content
   repo.
10. **D1081:** revisit the Intel Mac app when GitHub retires its Intel Mac
    runners.

## 12. Owner decisions and standing asks

None is open: nothing waits on the owner (D115). The owner may overrule
these defaults:

1. D1178: Modkit's plugin loader isn't ported; community content repos are
   AzurKit's extension point.
2. D1179: Modkit's policy.yml isn't ported (13).
3. 4.20's Q1: Easy's 5-9 % more fill work at Hard/Hard with the powers kept
   stays (8.30).
4. ci57's defaults: no measure seat loads the Mac on purpose; cancels act
   at attempt granularity; `fill.roll` stays off the kernel; no
   sanitized-kernel check.
5. D1175 is a record field: the retired records still resolve (6.2).
6. devkit's `models edit --build` keeps AzurKit's chain default "hit"
   (D1045), not Modkit's "any" (4.15a5).

Standing asks:

7. **D1075:** every session start reads AzurKit's new issues and pull
   requests (gh, read-only), reproduces each, fixes what reproduces in a
   lane and reports a summary. No public reply, label, close or merge from
   the owner's account.
8. **D1076, D1084:** a short Discord announcement draft in the owner's
   voice for a release (1.0.2's, with the Variants editor, if it ships);
   nothing is posted.

What only the owner does:

9. File the Chromium bug from its draft (D1111).
10. Post the announcements (D1084).
11. The hub notes, only when the owner says (D134).
12. ModMG's disk use in `/private/tmp` (D1140).
13. Remove the empty Modkit folder after closing the session (D1189).
14. See the MEMORY.md diff in chat when the memory moves (4.2, D1171).

## 13. Retired by name with Modkit's delete (D1171)

Each Modkit test or feature with no AzurKit home, by area, with the id that
retires it. The census rows older decisions retired (the Tk GUI's, D866;
the retired authoring scripts', D955; and D956, D457, D1061, D133, D181,
D329, D43, D1123) aren't repeated here.

### Features

- The drop-in WAV folder for a variant's sounds
  (`--player-variant-sounds`): no host reached it, so Step 4.30 deleted
  it; a recipe's `wavs` (the Variants editor's Add WAV) take its place
  (D1184).
- The shim toolchain's shared libraries: no consumer but its own fixture;
  AzurKit lands each pack's objects itself (D1184).
- Modkit's entry-point plugin loader (`plugins list`, its plugins doc and
  about 20 tests: test_plugins, test_audio_and_plugins' plugin discovery,
  test_categories' and the pack browser's plugin rows): community content
  repos are the extension point (D1178).
- Modkit's `policy.yml` (a pull request changing a protected path waits for
  a 'reviewed' label) and test_ci_workflows' three policy tests: it ran on
  pull_request_target, which AzurKit never uses; `pins.yml` is ported
  (D1179).

### Packs, mods and the engine

- `test_apply_pack.py:254` `test_no_shims_env_swaps_in_legacy_sites`: no
  AZURIK_NO_SHIMS legacy path; the shim ships prebuilt (D1171).
- `test_apply_pack.py:359` `test_non_patchpack_raises`: a type check of
  Modkit's apply_pack API; `engine.plan` takes a Pack (D1171).
- `test_apply_pack.py:363` `test_unknown_site_type_raises`: `Pack.sites` is
  typed (D1171).
- `test_legacy_pack_migration.py:27`
  `test_legacy_name_resolves_with_deprecation_warning`: no pack aliases; a
  remembered setup names and drops a renamed pack (D1171).
- `test_legacy_pack_migration.py:45`
  `test_legacy_name_warns_only_once_per_process`: as above (D1171).
- `test_float_param_injection.py:148` `test_returns_none_for_missing_symbol`:
  Modkit's internal lookup; AzurKit's engine raises instead (D1171).
- `test_float_param_injection.py:152`
  `test_returns_none_for_undefined_symbol`: as above (D1171).
- `test_mcp_game_tools.py:533`
  `test_l3_config_mod_offset_guard_covers_the_full_8_byte_write`: Modkit's
  raw-offset cell writer; AzurKit writes cells by name (D1171).
- `test_qol_skip_logo.py:98` `test_legacy_mode_writes_corrected_bytes`: no
  AZURIK_NO_SHIMS (D1171).
- `test_xbr_pack_dispatch.py:143` `test_missing_xbr_files_raises`:
  apply_pack's xbr_files plumbing; `mods.plan` always takes the image's
  files (D1171).
- `test_xbr_pack_dispatch.py:235` `test_contains_and_get`: IsoStaging's API;
  AzurKit has no staging object (D1171).
- `test_xbr_schema_lint.py:104` `test_unchecked_xbr_sites_suppresses_warning`:
  no pack opts out of the cross-check (D1171).
- `test_patch_loader.py:117` `test_patch_pack_fields`: trivial, `engine.Pack`
  is a frozen dataclass (D150).

### Level patches (AZ-009)

AzurKit refuses a mod file's level patches by name, pinned by test_edits'
Modkit mod-file test.

- `test_edit_layers.py:343`
  `test_level_patch_targets_same_slot_whether_split_across_mods_or_not`
  (D1171).
- `test_edit_layers.py:424`
  `test_randomize_full_level_patches_mean_the_input_levels_entities`
  (D1171).
- `test_edit_layers.py:483`
  `test_a_level_patch_float_saturates_past_float32_range_and_refuses_nan_or_inf`
  (AZ-181; D1171).
- `test_edit_layers.py:547`
  `test_a_level_patch_name_without_a_marker_means_the_input_levels_slot`
  (AZ-183; D1171).
- `test_edit_layers.py:584` `test_m16_missing_patch_keys_are_errors_not_keyerrors`
  (D1171).
- `test_edit_layers.py:595` `test_l21_raw_patch_rejects_malformed_entries`
  (D1171).
- `test_edit_layers.py:611`
  `test_l21_raw_patch_rejects_negative_and_float_offsets` (D1171).
- `test_edit_layers.py:623` `test_l21_raw_patch_still_applies_valid_entries`
  (D1171).

### Shims, the XBE and the kernel

- `test_goldens.py:338`
  `test_normalized_shim_object_hash_ignores_timestamp_and_debug_records_only`:
  shims rebuild byte for byte (`shimkit --check`), no normalizer (D1171).
- `test_xbe_tools.py:779` `test_pin_failure_has_structured_attrs`: Modkit's
  pin_va helper; `anchors.toml` and its test replace it (D1171).
- `test_xbe_tools.py:792` `test_load_vanilla_xbe_cached`: Modkit's test
  helper's cache (D1171).
- `test_xbe_tools_repo_root.py:10`
  `test_find_repo_root_outside_source_checkout_raises_instead_of_returning_cwd`:
  AzurKit reads its data beside its modules (D1171).
- `test_append_xbe_section.py:206` `test_append_rejected_when_name_too_long`:
  AzurKit appends only SHIMS, a fixed name (D1171).
- `test_append_xbe_section.py:211` `test_append_rejected_on_empty_name`: as
  above (D1171).
- `test_autocompile.py:54` `test_build_stem_maps_to_feature_folder_shim`:
  prebuilt objects beside their sources, no guessing (D895).
- `test_autocompile.py:68` `test_sibling_fallback_when_not_in_build_dir`: as
  above (D1171).
- `test_autocompile.py:78` `test_no_repo_root_still_returns_sibling`: as
  above (D1171).
- `test_autocompile.py:107`
  `test_shim_feature_outside_repo_compiles_its_declared_shim_c`: no
  out-of-tree shim; objects are committed (D895).
- `test_autocompile.py:140` `test_kernel_resolver_obeys_no_autocompile`: no
  autocompile; the resolver is a committed object (D895).
- `test_autocompile.py:228` `test_stale_c_triggers_rebuild_decision`: no
  rebuild at build time (D895).
- `test_autocompile.py:238` `test_fresh_o_does_not_trigger_rebuild`: as
  above (D1171).
- `test_autocompile.py:244` `test_force_rebuild_env_rebuilds_fresh_o`: as
  above (D1171).
- `test_d1_extend.py:440` `test_every_extended_extern_has_catalogue_entry`:
  no hand header; the kernel header is written from the facts (Q85).
- `test_kernel_imports.py:99` `test_stdcall_strips_prefix_and_suffix`:
  AzurKit never demangles; each facts function and kernel export carries
  its mangled name (D1171).
- `test_kernel_imports.py:104` `test_stdcall_rejects_cdecl_shape`: as above
  (D1171).
- `test_kernel_imports.py:107` `test_stdcall_rejects_missing_underscore`: as
  above (D1171).
- `test_kernel_imports.py:110` `test_stdcall_rejects_nondigit_arg_bytes`: as
  above (D1171).
- `test_kernel_imports.py:113` `test_cdecl_strips_prefix_only`: as above
  (D1171).
- `test_kernel_imports.py:116` `test_cdecl_rejects_stdcall_shape`: as above
  (D1171).
- `test_kernel_imports.py:119` `test_cdecl_rejects_empty_name`: as above
  (D1171).
- `test_kernel_imports.py:122` `test_kernel_name_for_symbol_tries_both_shapes`:
  as above (D1171).
- `test_kernel_imports.py:130` `test_kernel_name_for_symbol_rejects_unknown`:
  as above (D1171).
- `test_kernel_imports.py:148` `test_rejects_out_of_range`: a slot comes
  from the facts, never an argument (D1171).
- `test_scaffolder.py:245` `test_planner_failure_leaves_placeholder_bytes`:
  the scaffold writes no replaced bytes; an `--xbe` it can't read exits 2
  (D1171).
- `test_scaffolder.py:388` `test_va_wins_over_string`: find-refs takes
  `--va` or `--string`, never both (D1171).
- `test_shared_library.py:73` `test_apply_places_library_and_returns_exports`:
  no shared libraries (D1184).
- `test_shared_library.py:82` `test_second_apply_is_no_op`: as above (D1184).
- `test_shared_library.py:97` `test_export_vas_lie_inside_placed_region`: as
  above (D1184).
- `test_shared_library.py:117`
  `test_apply_library_with_no_externals_is_rejected`: as above (D1184).
- `test_shared_library.py:155`
  `test_shared_library_export_in_second_rdata_section_points_at_its_own_bytes`:
  as above (D1184).
- `test_shared_library.py:185`
  `test_get_or_create_session_returns_same_session_for_same_bytearray`: as
  above (D1184).
- `test_shared_library.py:243` `test_both_consumers_resolve_to_same_helper_va`:
  as above (D1184).
- `test_shared_library.py:266`
  `test_shared_lib_not_re_placed_between_consumers`: as above (D1184).
- `test_shim_builder.py:82` `test_rejects_bad_mode`: no HandShimSpec;
  player_physics writes its hand shims through `Xbe.carve`, pinned by its
  golden cases (D1171).
- `test_shim_builder.py:90` `test_rejects_wrong_vanilla_length`: as above
  (D1171).
- `test_shim_builder.py:100` `test_defaults_hook_return_va`: as above
  (D1171).
- `test_shim_builder.py:110` `test_explicit_hook_return_va`: as above
  (D1171).
- `test_shim_builder.py:171` `test_install_lands_trampoline`: as above
  (D1171).

### XBR files

- `test_assets_manifest.py:61` `test_empty_file_rejected`: a build reads only
  the manifest-pinned vanilla filelist.txt (D1171).
- `test_orphan_xbrs.py:120` `test_contains_f7_and_e4`: no KNOWN_CUT_LEVELS
  constant (D1171).
- `test_orphan_xbrs.py:125` `test_frozen`: as above (D1171).
- `test_xbr_cli.py:172` `test_add_row_surfaces_blocker`: `xbr edit` has no
  add-row op (D1171).
- `test_xbr_cli.py:185` `test_blocker_checked_before_legal_edits_run`: as
  above; whole-or-nothing stays pinned (D1171).
- `test_xbr_keyed_structural.py:330`
  `test_keyed_table_growth_blockers_point_at_an_open_backlog_item`: no
  add-row, remove-row or grow-pool (D1171).
- `test_xbr_keyed_structural.py:352` `test_add_level_entity_raises_with_blocker`:
  as above (D1171).
- `test_xbr_keyed_structural.py:358` `test_resize_toc_entry_raises_with_blocker`:
  as above (D1171).
- `test_xbr_pointer_graph.py:87` `test_shift_before_origin_and_target_noop`:
  AzurKit never grows a file in place; it appends (D1171).
- `test_xbr_pointer_graph.py:98` `test_shift_between_origin_and_target_patches`:
  as above (D1171).
- `test_xbr_pointer_graph.py:128` `test_shift_both_moves_noop_for_selfrelative`:
  as above (D1171).
- `test_xbr_pointer_graph.py:143` `test_file_absolute_ref_rewrites_on_target_move`:
  as above (D1171).
- `test_xbr_sections.py:59` `test_filter_returns_only_requested`: no
  `sections=` filter; each table parses on demand (D1171).
- `test_xbr_sections.py:69` `test_empty_filter_returns_empty_dict`: as above
  (D1171).
- `test_xbr_sections.py:74` `test_unknown_section_silently_ignored`: as above
  (D1171).
- `test_xbr_sections.py:82` `test_mix_known_and_unknown`: as above (D1171).

### Images, setup and packaging

- `test_iso_roundtrip.py:382`
  `test_extract_refuses_an_entry_name_windows_reads_as_a_drive_stream_or_device`:
  AzurKit makes no path from an entry name (AZ-216; D1171).
- `test_iso_roundtrip.py:397`
  `test_the_xiso_command_reports_a_missing_or_refused_image_in_one_line`:
  no xiso command (AZ-245; D1171).
- `test_packaging.py:42` `test_documented_pip_extras_are_shell_quoted`: no
  extras (D1171).
- `test_setup.py:25`
  `test_bootstrap_iso_refuses_a_dump_that_fails_the_vanilla_gate_and_places_nothing`:
  AzurKit's bootstrap places no image (D953; D1171).
- `test_setup.py:35`
  `test_bootstrap_links_each_iso_into_the_user_data_folder_and_leaves_another_file_there_alone`:
  AzurKit's bootstrap makes no links (D1171).

### Saves

- `test_save_format.py:105` `test_set_updates_existing_field`: AzurKit's
  save editor edits text saves' lines and never writes SaveMeta.xbx (D1171).
- `test_save_format.py:111` `test_get_default_on_missing`: a trivial default
  argument; AzurKit's get returns None (D1171).
- `test_save_format.py:300` `test_summary_partitions_root_vs_level`: AzurKit
  lists each file by path (D1171).
- `test_save_format.py:509` `test_h10_set_appends_utf16_terminator`: AzurKit
  never writes SaveMeta.xbx (D1171).

### The randomizer

- `test_gui_randomizer_slider_wiring.py:157`
  `test_randomize_full_builds_pack_params_json_values_and_refuses_a_conflicting_flag`:
  no per-slider flags to conflict with a recipe (AZ-148; D1171).
- `test_randomizer_fill.py:577`
  `test_restack_moves_the_d185_seed_at_every_site_that_cites_it_or_at_none`:
  Modkit's lane tool `scripts/restack.py` (D1171).
- `test_randomizer_settings.py:225`
  `test_a_slider_builds_spoiler_and_placement_file_read_its_plan_on_its_logic`,
  its placement-file half: the build report holds the plan (D1171).
- `test_randomizer_writer.py:143`
  `test_a_build_that_does_not_randomize_drops_the_placement_file_an_earlier_build_left`:
  no placement file (D1171).
- `test_gui_pages.py:3266`
  `test_the_patches_page_shows_no_tags_ranges_or_notes_and_a_safe_hint_only_while_randomizing`,
  its per-slider safe-hint half: movement's slider ranges were dropped; the
  warning line says what a build leaves unverified (D1171).
- `test_gui_pages.py:506`
  `test_a_ticked_skip_group_turns_on_its_skips_up_to_the_movement_difficulty_and_a_pick_wins`,
  its "up to the movement difficulty" half: a ticked group no longer stops
  there (D1061).
- `test_randomizer_logic.py:1174`
  `test_physical_reach_takes_the_edges_out_of_logic_and_only_the_skips_that_are_on`,
  its dark_fire 3 case: a dark area always needs Fire 1 (D1061).

### Characters

- `test_player_variants.py:2274`
  `test_booblords_gait_turns_her_sash_flap_out_over_a_thigh_swinging_through_where_it_hangs`:
  it tests an authoring script D955 retired; her clips' bytes are in the
  goldens (D955).
- `test_player_variants.py:2345`
  `test_booblords_borrowed_hit_and_fall_clips_turn_her_sash_flaps_out_at_least_as_far_as_each_tick_needs`:
  as above (D955).
- `test_player_variants.py:1266`
  `test_a_drop_in_wav_replaces_a_variants_sound_by_its_role`: the drop-in
  WAV folder is deleted (D1184).
- `test_player_character.py:10572`
  `test_a_player_model_build_leaves_no_shim_session_holding_its_xbe`: the
  swap keeps no shim session (D1171).
- `test_player_character.py:10608`
  `test_player_models_json_names_its_mode_and_the_counts_its_text_ends_with`:
  no player-models verb; the list is the Characters tab's (D866/D882).
- `test_player_weapons.py:163`
  `test_the_attack_listing_shows_what_the_build_installs`, its printed-line
  half: the listing has no home; its data is ported (D866/D882).

### Tests, CI and lane tooling

- `test_goldens.py:375`
  `test_restack_flags_a_re_recorded_case_only_when_the_lane_changes_none_of_its_sources`:
  AzurKit's restack records the randomizer only (D1171).
- `test_goldens.py:407`
  `test_restack_authors_from_the_kept_result_while_every_file_the_authoring_read_is_unchanged`:
  its restack keeps no author result (D1171).
- `test_ci_workflows.py:106`
  `test_three_os_yml_never_spells_an_owner_grep_phrase_so_only_check_output_can_match`:
  Modkit's workflow (D1171).
- `test_ci_workflows.py:129`
  `test_full_tier_dispatch_checks_the_pr_before_checking_out_its_code`:
  AzurKit's vanilla tier runs only on pushes to `main` and lane branches
  (D1171).
- `test_ghidra_harness.py:496` `test_ping_and_program_info`: a live Ghidra
  smoke Modkit skipped by its allow-list; AzurKit's allow-list is empty
  (D1171).
- `test_ghidra_harness.py:504` `test_get_known_function_if_default_xbe`: as
  above (D1171).
- `test_randomize_full_golden.py:403`
  `test_a_kept_build_is_a_cold_builds_output_and_a_changed_input_misses`:
  Modkit's test build cache (D1171).
- `test_retired_names.py:165` `test_no_examples_dir`: Modkit's layout
  (D1171).
- `test_retired_names.py:179` `test_no_azurik_cli_references`: Modkit's
  console-script name; the agent-files lint guards Modkit text (D1171).
- `test_retired_names.py:250` `test_whats_new_is_short_and_plain`: no
  CHANGELOG.md; the guide holds the features (D1171).
- `test_skip_budget.py:109`
  `test_default_xbe_check_may_skip_when_live_ghidra_serves_another_program`:
  no live-Ghidra check, so no skip (D1171).
- `test_skip_budget.py:131`
  `test_ci_full_fails_a_narrowed_run_no_vanilla_run_and_an_allowlisted_skip_that_never_skipped`:
  no `--ci-full`; a receipt is fullsuite's own selection (D1171).
- `test_test_for_va.py:59` `test_requires_exactly_one_of_va_or_pack`:
  `find_matches` takes one target (D1171).
- `test_test_for_va.py:66` `test_hit_lines_are_sorted`: an internal list's
  order (D1171).
- `test_test_hermeticity.py:151`
  `test_a_result_kept_across_runs_is_served_only_while_what_it_read_is_unchanged_and_only_an_opted_in_run_keeps_it`:
  Modkit's session cache (D1171).
- `test_worker_processes.py:15`
  `test_workers_run_this_checkouts_code_whatever_package_the_cwd_holds`:
  AzurKit's engine holds no processes (D1171).
- `test_worker_processes.py:33`
  `test_a_failed_workers_items_are_redone_here_and_raise_what_a_loop_would_first`:
  as above (D1171).

## How this list was made

Step 4.32 rewrote Step 4.23's list at the session's end. It read 4.23's
four sweeps of the session's log, reports, plans and git with that list's
sources, the decisions through D1193, every step report and review written
after 19:00 on 2026-11-08 (4.13f to 4.31), the coverage and test censuses,
4.30's list of retired rows, the gate's receipts with their flake and
perf-debt rows, the private ledger, and the state of `main`, the lanes, the
L3 store and this Mac at 04:00. It dropped what was done: the port lanes
and their review fixes, stack 2's landing, the x7 rebuild, the reach bench,
the `$EV` tools' flip, the brief, the census gaps and the cleanups already
made. A sources file beside the step's report gives each item's evidence.
