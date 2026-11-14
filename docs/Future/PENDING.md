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

Step 4.47c brought it up to date on 2026-11-11, against the landing
queue's tail (09564439, behind 1.0.3's release commit 7a4bab60), after
the 11-10 session's steps 4.37-4.47. A done item is struck to one line
naming what closed it, so the numbers that tests and decisions cite still
point; a new item takes the next free number in its group. Groups 4 and 5
were left as they were. Step 4.47g added the 2026-11-12 session's items
(2.5, 9.43, 10.14) and brought 10.12 up to date.

## 1. First: the Variants editor's first Check (D1181, D1192)

The next session starts here (D1192), so 1.1 can follow.

1. **The target** (D1244, amending D1194 and D1201; D1204): tiered by how
   often players meet it. A Check players meet often (her own copy's first,
   after Scale, a Jiggle stiffness or a colour) takes 30 s at most in each
   of WebKit, Chromium and Firefox and 15 s in the app; a rare one (after a
   Shape edit, one with no shipped parts) and a reshape's first build and
   pictures 90 s and 45 s. The perf gate holds each op to its tier's line,
   one past it a debt row (Step 4.49a; INTERNALS.md's tiers). It is
   measured on this Mac, busy, beside other projects' load (D1107): no idle
   rerun and no line change but the owner's; on CI's runners the tests keep
   their bounds. Rounds go on until every path holds its line with margin;
   then one real-Safari first Check, in one window (D1089, D1202).
2. **Where it stands** (11-14, Steps 4.55b-4.55d's stack with its parts
   re-recorded, 4.55e's booblord v11, measured on this Mac): her own
   copy's first Check reads S78 7.9 s in WebKit and A92 4.4 s in the app
   (4.55e; main's receipts 7.5-8.4 s and 3.9-4.0 s). A Check after
   a Shape edit reads S84 57.6 s in WebKit, 60.5 s in Chromium and 80.6 s
   in Firefox, A98 21.1 s in the app; one with no parts S88 53.3, 57.2 and
   75.8 s; a reshape's first pictures S52 58.2, 58.9 and 81.5 s, A60
   30.2 s; its first build A31 22.6 s; the quick preview A95 3.3 s with a
   moving bar (main: S84 98-108 s in WebKit, A98 40-46 s, A60 43-50 s,
   A31 41-43 s, A95 9-11 s, its bar moving only sometimes). Natively and
   serially a Shape-edit Check takes 20.7-20.8 s, from 24.0-26.7 s on the
   stack below the subdivision's kernel.
3. **The plan** (4.37e's design): round 6's A (4.37e1), C (4.37e3), F
   (4.37e4) and B2 (4.37m1) landed. D1, E and D2 are built (Steps
   4.55b-4.55d: the mesh plan's position steps, the rig and the
   subdivision compiled, bit for bit their twins, and the quick preview's
   moving bar), with their parts re-recorded (4.55e: booblord's content
   v11), waiting for the gate.
   Open: G (the paint for wasm), H (the Check ahead), K (the clip import),
   round 5's pictures-first (r5g) and R7b (later by reference). 4.37e's
   forecasts are superseded by item 2's numbers; round 7 is undesigned.
4. **Levers named so far:**
   - a narrower key for a texture or colour edit, which redoes both
     restyles and the LODs (about 15 s, 4.6n): 4.37m's second lane, after
     round 6, owing a content release first;
   - beamlord has no Check parts: her Check reaches only `size`, so D1197
     published nothing (4.37m). Her own copy's first Check does the whole
     work: 2.2 s native, 5.3 s on the site's engine (4.37a);
   - perf rows that time a Check after a Shape, Scale, Jiggle or colour edit
     and one with no parts (A98, A99, A104-A106, S84-S88): 4.37e0, built,
     not yet queued.
5. **The parts' download:** a first Check's 24.5 MB of parts come with no
   bar, and no pytest drives a real browser through a shipped fetch (S78 is
   the only proof).
6. **Parts keyed by their inputs** (D1195): Step 4.37m1 keys every Check
   part on its stage's inputs alone, so the recording host's parts serve
   every platform, close enough off it (D1016); its first commit is the
   jiggle half (B2). Built, in flight: its re-record, `record_goldens.py
   --check` and two heavy pins haven't run (no window). Until it lands, the
   Intel Mac, Windows and Linux apps miss the shipped parts (4.37f's C.3;
   the site takes them), and the Intel app's first Check passes 120 s on CI
   (C.12).
7. ~~A variant's pictures, dressed~~: fixed by 4.46a1, carried in 4.55e
   (keyed on `parts.VERSION` and the drawing's files).
8. **The Firefox Shape-edit gap** (D1209, D1244): its line is a rare
   Check's 90 s (S84). With Steps 4.55b-4.55d's kernels in it reads 57.6 s
   in WebKit, 60.5 s in Chromium and 80.6 s in Firefox (11-14, one sample
   each; 11-11: 113-117, 180 and 256 s), each under 90 s with a moving
   bar, so no browser's goes under group 9's known flaws. Firefox's has
   the least margin (9.4 s).
9. **Paths with no perf row** (4.49a's design): a Check after a sound edit
   (frequent; 2.6 s natively in 4.37m1's A/B), after a texture row or
   Import PNG (about 15 s natively, 37.1 s on the site's engine), and after
   a Moves, Attacks or Effects edit. The gate can't tier what it doesn't
   time: each wants a row in `tests/_perf.py` with its tier and its line.

## 2. Releases and content

1. ~~1.0.2~~: out on 2026-11-09 (tag `v1.0.2`, 15c16383).
2. **The content push**: booblord v10 (her rework, 2a0abad) is the
   content repo's `main` since 1.1.1. v11 (Step 4.55e: her Check parts
   under the compiled kernels' `parts.VERSION`, beamlord v2's plain
   notes) goes to its `main` with 1.2.0, and CI's `CONTENT_COMMIT` with
   it (D1266, D1267). The clone's superseded branches and worktrees go
   with 11.2.
3. **1.1** (D1203, D1210, D1244): the release where group 1's tiered
   lines hold, with the Variants editor's gaps: Undo (there since 4.6e),
   the app's window asking about unsaved edits on close (4.38a, landed) and
   community-only characters resolving (9.32).
4. **1.0.3** (D1196, D1198, D1210, D1218, D1221): the release that fixes
   the Windows app's Build with a character. Its fixes: the hang (`serve`
   read its input on fd 0, where numpy's OpenBLAS waits at load: 4.37r,
   85cc0426, seen passing on Windows CI); pywin32 out of the Windows bundle
   (4.37h, fb135f4c); and the Windows Firefox save-bar test's race (4.37t,
   e2a93f07, a test fix, queued). Step 4.47b's release commit (7a4bab60:
   the version and the developer log's 1.0.3 section) lands ahead of this
   list's commit, on its full gate. It is pushed to `main` alone, and main's CI decides:
   green, or red only on the Windows Firefox save-check test and green on
   one rerun of that job, then tag `v1.0.3` there and publish at once, the
   notes shown to the owner after; red again, the tag waits for 4.37t on
   `main`. 4.38b's community-only characters, its two red tests under a fix
   seat, move to 1.1 (D1203).
5. **booblord's rework** (D1224-D1242): a refinement and optimization
   pass of booblord, booblord_high and both human variants, Fable
   designing and judging and Opus building, the owner picking each round.
   Round 1 took look A at today's coverage; round 2 the full high ponytail
   (its "cleft fine" op out), sat once in xemu (its frame cost 20.2 MB
   against shipped booblord's 31.4 MB, the cost model's line held). Round 3
   converges on one candidate: the hair one even colour with no streaks,
   drawn red irises, the back tail narrower and the backpack shallower
   (D1235-D1239), and the staff out of her body in 79 of her 81 clips.
   Then the hand-off: she is dressed as the built-in in `variants.json`,
   sat once in xemu with model_kit rows (the springs on open ground) and a
   skeptic, graded from that sitting, her goldens recorded, and a new
   content version replaces booblord in place (D1240, after 4.37m1's).
   booblord_high carries the same changes and is judged once (D1241); the
   human variants get their colour check; fixes round 3's judges owe go
   into the hand-off (D1242).
6. **Content that fits the app it reaches** (the review of 4.48b, F3):
   booblord v10 is the first built-in recipe change since 1.0.0, and
   `content.builtin_refusal` holds a built-in's sha exact, so once the
   content repo's `main` moves to v10 an AzurKit up to 1.1.0 can't newly
   install her, and 1.1.1 can't install v9. Each later recipe change does
   the same. A lane could let an entry name the AzurKit versions it fits
   (or keep one entry a release line), so an app installs the newest
   version it accepts; until then a recipe change ships with its release.

## 3. Stack 3 and 4.31's outcome

1. ~~Stack 3~~: landed (5a3b0954); 4.31 and 4.30 are in 1.0.2.
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

When this list was written, Modkit's checkout was still in place. Of
these, only 4.1's content install and proof round and 4.3's rename,
rewrite and link were done.

1. **ModelKit's re-point** (4.15a8, D1183, D1188): the lane
   `mk/4.15a8-azurkit-repoint` (17637b2, reviewed with no defect) isn't
   pushed. Done: `uv run --locked azurkit content install booblord`
   (booblord v5) and the proof round on `profiles/booblord` on AzurKit's
   `main` 6a99347f (round new, build, measure `--tier gate`, sheet: PASS,
   no fix, reviewed with no defect), which also ran `model pose`. Left, in
   order:
   - before Modkit is deleted, re-install ModelKit's leak guard
     (`hooks/leak_guard.py --install --forbidden`) with AzurKit's
     byte-equal `src/azurkit/core/manifests/usa.json` and `europe.json`.
     Its forbidden list names Modkit's manifests, so once they are gone
     every ModelKit push is refused;
   - then push the lane over SSH to ModelKit's private repo's `main`,
     fast-forward its main checkout and run `modelkit install-skill`;
   - if wanted, undo the content install: remove the user data folder's
     `content/` booblord folders (variants, clips, sounds) and its
     `installed.json`.
   Never tested there: `model rest` through `kit/rest.py` and v4kit's user
   build cache. Her new base file sits in that step's evidence, outside
   ModelKit's repo. Nit: `test_azurik_adapter`'s runner stand-in still
   handles `--export`.
2. **Memory** (D1187, D1171): copy the shared memory folder to AzurKit's
   project slug, point AzurKit's and ModelKit's `autoMemoryDirectory` at it
   (both still named Modkit's slug), keep the old folder as history, and
   show the owner the MEMORY.md diff in chat. The resume pointer (still
   session 4718988a, 11-01) and the repo-layout memory change with it.
3. **The xemu fixtures** (D1177): done: the fixtures folder is renamed
   `Azurik-fixtures` beside the checkouts, the absolute paths in its
   `xemu.toml` and that file's line in its `SHA256SUMS.txt` are rewritten,
   and the user data folder's `xemu-fixtures` link (devkit's harness
   default) points at it. Left: check the sums, then run a smoke boot (no
   record of either). 4.17a's report has the commands and the revert.
4. **Tags** (G8): `oracle-rando-6` at 8bfef0ca6 (AGENTS.md cites it) and
   `modkit-final` at Modkit's last commit, pushed to Modkit's GitHub repo
   before it is archived.
5. **The delete** (D1171, D1189): G11's checks from AzurKit inside the
   session. Then remove the one exact Modkit checkout path, never a glob
   (the `-lanes` folder and any other `Azurik_Modkit*` folder share its
   prefix), and put an empty folder back for the wrap-up; the owner removes
   it. Leave ghidra, ghidra-backups, the evidence folder, the user data
   folder and the old memory folder alone.
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

The private ledger (D952) holds Modkit's 29 open issues. After 1.1 the
work comes here and to group 9's known flaws and editor leftovers, reach
staying frozen (D1212); 4.40b's triage readies their lanes.

- Inherited by AzurKit (3):
  - ~~AZ-009: level patches address entities by their current name, not
    their vanilla identity~~: fixed by 4.41b (a move by the vanilla
    level's name or id; a rename stays refused).
  - ~~AZ-234: the D-pad field names in the struct header are swapped~~:
    fixed by 4.41a.
  - ~~AZ-247: the index structs describe 20-byte records~~: fixed by
    4.41a.
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
   run. Cause shown (4.37f): the images' move to their own folder, at
   19:44:08, fell inside the test, and D27 refused rightly. An outside
   event: no lane, unless an image moves during a run again.
2. ~~The shaped fills' cancel test~~: fixed by 4.37h (e74be8b2).
3. ~~The Variants Sounds and Effects tabs test `[webkit]`'s KeyError~~:
   fixed by 4.37g (09547c20); its other error is 35.
4. ~~The two-engine-workers test~~: fixed by 4.54a (it failed three times
   after 4.37g's fix).
5. ~~The WebKit-ending test's stand-in ids~~: fixed by 4.37k (3cd387c5).
6. ~~The Variants test's second page in Chromium~~: fixed by 4.6d
   (e7ef87a0).
7. The frozen app's page saves CPython's image `[firefox]` (the Windows
   frozen app's first load, ci30's B): it failed twice on 11-12's Windows
   CI, its rerun on a browser that had stopped answering. Since 4.54b that
   browser is launched again for the rerun and the next test, and CI's log
   prints a twice-failed test's first try, so its next hit names its cause.
   The same shape as 10.
8. Chromium site tests that stalled with no error (ci36's slowed sweep):
   4.37f's slowed rerun and six "no answer in 237-238 s: azurkit.ready"
   flakes in 4.37d's gate met a macOS privacy (TCC) prompt, not starvation
   (4.37o). Another project's headless Chromium asked for the Documents
   folder on the owner's screen, and every Chromium GPU helper launched
   while the prompt stood waited behind it. Step 4.37p, on `main` since
   11-12, runs Chromium's GPU in the browser's process and names a standing
   prompt in a stalled call: look for that line at the next Chromium stall
   (CI's one since is an arm64 `azurkit.ready` miss in test_service_worker,
   11-13). ci36's own run can't be rechecked
   (the privacy log isn't kept that long). Also unfinished: saving while
   the rest of the image is being hashed.
9. ~~The pure-tier tests that failed only when slowed (ci27)~~: fixed by
   4.4ci36 (625c2878, ede40526, 537eeb47, 0511ce67, 1bc9e663).
10. Windows Firefox holds its first request for about 37 s (4.5l, 4.5w),
    and 7 is likely the same: DIRECT isn't shown to prevent it. Windows
    CI's Firefox now logs its requests and loads, and a stalled call prints
    the log's end (4.37k, 34f9e248). The 11-12 hit's first try kept that
    end only in the failed tries' file, which nothing printed; since 4.54b
    CI's log prints a twice-failed test's first try, so the next hold names
    its cause.
11. ~~test_dev_tools' flake-stage tests on Windows~~: fixed by 4.5c
    (e9f137bb) and 4.5i (f9cddb6a).

### The watch list: name the cause the next time each one fails

12. arm64: the Europe golden `[webkit]`'s five failure modes; SIGBUS;
    WebKit's reload; the WebKit engine trap (ci44); WebKit's JSC fault on
    macOS 15 (4.5p; a newer Playwright was the lever, D1133: 4.56b takes
    1.65.1; arm64 WebKit's "Target crashed" had passed its rerun 9 times in
    33 CI runs from 11-11 to 11-13: count it again from 4.56b on). ~~Firefox's timer that lost
    once~~: fixed by 4.54a (the word-list Undo was pressed before it was
    enabled); a lost edit still waits 600 s with no Data tab state in
    `hang()` (4.5g).
13. Intel: page-load stalls; ci19's extra 2 h; WebKit's drawing threads
    outranked (ci21).
14. Windows: ci34's cause; ci39's load failure.
15. WebKit: network-process endings (ci41: a RequestedByNetworkProcess
    ending still costs 120 s); why WebKit leaves the page's process (ci18);
    what triggers the zero-headed message (4.5s: if it recurs, the call
    fails at once naming it and D1170's rerun records it; 4.37k retired
    `_page.past_refusal`'s unrecorded redo); ci31's Characters stall; the
    parts test's closed page `[webkit]` on macOS arm64 (4.37f's C.13).
16. Others: ci17's three; what held ci27's GIL; ci37's CI ValueError;
    4.5m's second failure; 4.5n's frozen capped A32; S59 under 20 extra
    threads (4.4bf); WebKit's GPU threads on a 4-core runner; ps under
    `taskpolicy -b` taking 8-12 s while the efficiency cores are busy
    (ci36); the app's Live marks test `[webkit]` on Windows (C.14: a
    flake's first try's error lines are kept now, 4.37k); the collected-spot
    test's hand click `[firefox]` on Windows (8a3128b; its failure now names
    Show collected and the fresh pickups, 4.37k).

### Test-harness follow-ups

17. ~~`_page`'s load, ending and redo gaps (N1-N3, 4.5p)~~: fixed by 4.37k
    (062dac4e, 3540afb1, 6aac6518; 2d1f3ebf retired the redo).
18. Silent waits:
    - Four bare `browser.new_context()` calls (test_hosts, test_site and
      two in test_service_worker) (ci14).
    - `_bare_page` callers' unbounded `context.close()`, two in test_site
      (ci15).
    - Direct `route`, `add_init_script` and `new_page` calls (about 40,
      30 and 50 grep hits) and the direct evaluates (ci14).
    - Two `page.goto` calls that keep Playwright's 30 s, in test_hosts and
      `_perf.py` (ci16).
    - App tests that fetch through an in-process server (37 uses, ci31); a
      call past its timeout now fails naming the call (4.37i, 323414cf).
    test_hosts' 24 bare `page.goto(server.url)` calls load through
    `_page.load` now (4.37k, 41e39159), and `Site.__init__`'s and
    `_bare_page`'s new context, init script, routes and new page are
    bounded (4.54d).
19. ~~test_site's two fresh-page loads at ACT~~: fixed by 4.37k (1f016297).
20. ~~`tests/ci_durations.json`'s old test id and stale shard table~~:
    fixed by 4.54d (measured from six CI runs' vanilla jobs).

### Perf debt

21. Rows the gate recorded:
    - A95 in the app (a warm quick preview after a Shape let-go): 9.1-10.8 s
      in 4.48b's and 1.1.1's full gates and 4.52a's run, its bar moving
      only sometimes: the preview's second step is shorter than one poll
      (group 8's rare-ops triage, 11-13). Step 4.55b builds its bar, and it
      lands with group 1's parts re-record.
    - ~~S79, a Check asked again unchanged, no progress for up to 3.4 s~~:
      fixed by 4.54e (it now shows a bar).
    - Stale: S64's 423 ms freeze (seen once, 11-09; it passes at
      0.003-0.007 s); A02 (0.61-0.91 s, with progress) and A73 (0.06 s)
      pass; Firefox's S81 is under the rare tier's line with a moving bar
      (unmeasured since 4.37b's 42.3 s). A110 is fixed (4.37d: 0.17 s).
22. **Round 5's levers** (D1103, ROUND-5-PLAN's r5a-r5j): r5a (the SND
    resampler) is done (4.6c); r5c (the mesh kernels) is done in part by
    round 6's springs and body writes, the rest being group 1's compiled
    kernels (4.55b-4.55d); r5g (a reshape's pictures ahead of the rest of
    its dress) is open; r5b, r5d-r5f and r5h-r5j weren't checked lane by
    lane. Their bar since booblord v10 (4.48b's and 1.1.1's full gates,
    4.52a's run; group 8's rare-ops triage): A31 41-43 s, A60 43-50 s
    (across its 45 s line with the load), A92 3.9-4.0 s, A95 9-12 s, and in
    WebKit S52, S62 and S63 71-76 s, S78 7.5-8.4 s and S81 13-15 s; stack
    2's run had read A31 166.5 s, A60 199.5 s and S52 140.7 s.
23. Saves (S06, S49, S50): WebKit's over 3 s are a known flaw now (9.45).
    Chromium's pass (2.13, 2.29 and 2.09 s medians in group 8's
    frequent-ops measurement, 11-13) on a thin margin: its browser process
    spends 2.5-3.2 CPU-s on a Save, so D1109 keeps it in research. A busy
    disk, not a full one, put them over (reproduced at 184-198 GiB free).
    S72's freeze isn't in the latest receipts.
24. Firefox's Saves on their bar (D1053): S06 6.54 s, S49 4.34 s and S50
    4.51 s medians (group 8's frequent-ops measurement, 11-13). Its bare
    download takes 3.3-4.6 s, three to four times a plain copy, and its
    check hashes all 1,195 files each Save.
25. ~~A71 and A80 never read on a busy box~~: read since, 0.06 s and
    0.02-0.06 s (1.1.1's full gate and 4.52a's run).
26. Not debt (A01 passes at 0.66-0.79 s in 1.1.1's full gate and 4.52a's
    run), ideas for the fill (ci56, ci57):
    - A beside attempt's stop or priority takes effect only at its end.
    - The setup before attempt 0 is serial.
    - `fill.roll` (the GUI's first seed) still runs the twin.
    - A01 shows only its first stage honestly, and 75aa632 has no test of
      its own.
    - `fill.c`'s constants (MAX_REPAIRS and its kin) should come from the
      blob (a later pass).
27. ~~The Characters tab's Reset waits on the engine~~: stale, A81 and S66
    pass at 0.007-0.008 s (1.1.1's full gate and 4.52a's run).
28. `gc.freeze` of the kept Logic: measure gen-2 pauses first (the 1.0.1
    survey's 4.5j; ci27).
29. The site's Expert seeds: the costliest plan for about 3 s on Pyodide,
    and no site op times them (4.20).
30. Not debt (no op over its line), the fill's quality: Easy at Hard/Hard
    with the powers kept: more of its own attempts fail
    (0.74 s median, 1.68 s max native), and it does 5-9 % more fill work
    (4.20's Q1, kept: 12.3).
31. ~~The Data tab's pickers fetch `characters/index.json` on open~~: not
    debt, A39 (0.07-0.09 s) and S32 (0.14-0.19 s) pass (1.1.1's full gate
    and 4.52a's run).
32. CI: about 60 SSH sessions per vanilla job, an unmeasured 1-2 min
    (4.5e). ci19's CI times were inferred, not measured.
33. The perf gate reads RSS, not footprint (4.4n's Q2, kept for 1.0.0).
    Revisit it with 9.35.

### Flakes found since, each owed a triage

34. ~~The Variants Shape tab's drag test `[chromium]`~~: fixed by 4.54a
    (a product race: a built-in's late shipped pictures wrote over the
    drag's Preview note).
35. ~~The Variants Sounds and Effects tabs test's Effects read, and its
    Sounds line read as `[[], []]` (group 8's most frequent flake: six
    times in three days, all three browsers)~~: fixed by 4.54a.

## 9. Product follow-ups and known flaws

### Known flaws (named under D835, listed until fixed)

1. ~~Refusals name Modkit's commands~~: fixed by 4.52b.
2. **"WHITE cycles"** in the build's character log line and comments
   (4.18a): D1153 wants modern pad names (LB). Rewording moves the shipped
   plan answers' digests, so they need a re-record.
3. ~~Beamlord's notes show decision ids~~: fixed by 4.52b; the content
   repo's copy follows at his next content version.
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
9. ~~Characters: a pause past REST still starts a build the next move
   drops~~: fixed by 4.53b.
10. **A stale first dress caught in a gap** takes the kill, and the next
    seed's click reads the logic again (45 s).
11. ~~Site builds without OPFS still copy twice~~: fixed by 4.53b. **Cut
    mode and S62's other mode are unproven** (4.3r4s).
12. **The arm64 WebKit engine trap:** `Error.stackTraceLimit = 0` in the
    engine worker's realm would turn the page crash into a RuntimeError that
    D1126's restart handles. A WebContent crash still takes the page with it
    (the 1.0.1 survey's 4.5a).
13. **Windows Firefox loses 6-15 GiB of temp disk** through the pack
    golden, and hangs for 60 minutes (D1105). Land a diagnostics-only
    commit first (the survey's 4.5d).
14. ~~`procpool._peak()` returns 0 on Windows~~: fixed by 4.52a.
15. ~~OPENERS: the stale openers' compiled set leaks~~: fixed by 4.52a,
    but for two calls that end within one thread switch (no lock).
16. **A Firefox Save whose `flat.mjs` fetch never answers stays greyed**
    (4.5u; accepted, since sw.js serves `flat.mjs` on the real site).
17. **A closed Firefox tab leaves its last build's ~835 MB file in OPFS**
    until the next load or a Clear (4.5q; accepted design).
18. ~~The site's Update fetches every file of an entry~~: fixed by 4.53b.
19. ~~The HTTPS content clone has no low-speed bound~~: fixed by 4.52a.
20. ~~The Windows and Linux frozen apps are console builds~~: fixed by 4.53c.
21. **The app's own server answers over HTTP/1.0** (ci42).
22. ~~A player's image named usa.iso or europe.iso in Downloads~~: fixed by 4.53c.
23. ~~A save edit's output guard doesn't fold case on macOS~~: fixed by 4.52a.
24. **source_hashes** is checked against both releases' vanilla files
    (4.6i; accepted).
25. **A row's "main colour" can be a tinted near-black** (4.6e; Modkit's
    rule, accepted).
26. **The reach aim's string drifts in rare cases** (`docs/REACH.md`).

### The Variants editor

27. Opening another variant mid-Check drops its answer, but the engine's
    in-flight dress runs on (4.28d). (After a drag during the Check, a
    pictures refusal's "Not drawn" giving way to the nearest note is no
    defect: that note is about the values now shown, 4.40b3.)
28. ~~The fits row's sha and `garret4_reference`'s hoe, unpinned~~: pinned
    by 4.27d (0d2873ec) and 4.52c.
29. ~~Old own copies of booblord_high refuse; old reshape-part keys miss
    once~~: accepted (4.6r), no lane: a copy made with New from this works.
30. Looks:
    - The status leads with the recipe hash.
    - "Built-in" and "built in" are both used.
    - `colours.mjs` rounds ties away from zero where Python rounds to even
      (the hex box only).
    - The effect colour uses the browser's picker, not Modkit's wheel.
    - Live's tab, not the editor's: at 1100 px with Live on, Live's 32rem
      status line wraps its bar onto a second line (57 px, 31 with Live
      off), and the app's Attach… pushes the line onto a third (91 px), so
      the map room is shorter (4.25; measured again in 4.53a, Chromium and
      WebKit alike).
31. ~~4.6c's leftovers~~: done, the last (`variant_save`'s `from` checked
    as a name) by 4.38b.
32. ~~Community-only characters~~: fixed by 4.38b.

### Data, mods and the randomizer

33. There's no page button for mod-template or entity diff; they are CLI
    only (4.6i's default).
34. ~~`docs/RANDOMIZER_DB.md`'s TODOs~~: fixed by 4.56a (D115's defaults:
    no drop offered, the reserved keys with no version planned).

### Docs

35. ~~The perf paragraph's Safari reason, S73 and 4.4's 6 GiB~~ (in
    INTERNALS.md, not AGENTS.md): fixed by 4.56a.
36. ~~The prose cites of Modkit's `LEARNINGS_HISTORY.md`~~: fixed by 4.56a
    (they name Modkit's archive, as does the game-reference skill's).
37. ~~DEVLOG.md's [Unreleased] link dead after `--remove`~~: fixed by 4.33
    (it is plain text now).

### Ideas the session ranked (after the port, D1131)

38. ~~Support plumbing~~: dropped, not built (D1206).
39. "Play it in xemu" help after a Save: Machine > Load Disc, and 128 MiB
    for big bodies.
40. Play and Attach have never met a real xemu or the real admin prompt
    (4.6k). The owner's demo (D205) waits for a session when the owner has
    time (D1205).
41. A headline randomizer mode and a speedrun kit (the session's idea
    ranking). When features open again, the open death realm (D201) comes
    first.

### Known flaws found since (D835)

42. **Audit pass 2's hostile-input findings** (4.45) get no lane (D1219):
    the site's manifest read has no size cap for a hostile Content from
    address (U5); two entries' paths that differ only by Unicode form or a
    trailing dot or space share a file in the content folder, and one entry
    listing both spellings fails its install part way (U3); an entry's
    `variant.json` is parsed with no depth guard (U6) and `installed.json`
    read with no cap or value check (U7); and on Windows a zip unpacked into
    the app's data folder can replace the install's key file (store F2).
43. **Covered faces removed** (E1, D1237): parked by the owner's decision
    (D1258), to revisit only if a model needs the last few percent. No
    Shape op removes faces (`docs/VARIANTS.md`), so faces a model's clothes
    always cover are drawn anyway. Measured on booblord v10 (E1's design,
    11-13): the faces covered in every frame of her 48 clips are a safe
    2.6 % (1.479x to 1.458x vanilla's heaviest vertex cost); her shadow LOD
    cut from each two-sided layer's outer side about 3 % of her bytes a
    flip (20.00 to 19.38 MB, an estimate; 1.479x to 1.433x by vertex cost),
    with no recipe change; and no Check gets faster (a fresh dress 69.1 s
    without, 70.1 s with the faces left out). The once-estimated 1.33x
    and 9-14 s don't hold: faces picked on the plan's weights leave holes
    once the rig re-weights her.
44. **booblord_human's eye-edge texel** (D1255): her rework's larger irises
    (D1252) reach one texel at her eye island's edge, magenta on
    booblord's page, that the human's +22 hue turns a dark maroon (hue
    353.5) instead of brown; no iris radius moves it. It ships as a
    known flaw: a human-only colour op for that texel would clear it.
45. **WebKit's Saves past 3 s** (S06, S49, S50): all but 9-44 ms of a
    Save is WebKit's own download of the 2.75-2.93 GB image, at a plain
    copy's speed. Alone they pass (1.29, 0.90 and 1.67 s medians); beside one
    other process writing to the disk they read 4.43, 4.32 and 4.90 s
    (1.1.1's full gate: 4.41, 4.26 and 4.54 s), and no page lever moves
    them (group 8's frequent-ops measurement, 11-13). Chromium's pass
    under the line, Firefox's on its bar (D1053).
46. **A worker's record shown on the newest ask** (4.54e): on the site,
    for up to about 2.5 s after a Check, its "Keeping the Check" records
    show on the newest ask, so an unrelated one answered meanwhile (an
    Install, a picker) shows that line; a Build clicked then does wait on
    it.
47. **A 4-45 ms flash** (4.54e): a Check asked again unchanged whose own
    steps take a few ms flashes its keeping records (one to three frames)
    before its bar hides.

## 10. Dev tools, tests and port notes

1. ~~A src import cycle~~: fixed by 4.37l (610da473), its test in
   `test_contracts.py`.
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
   `azurik-mod`); the refusals that named them are fixed (9.1, by 4.52b).
   `OWNER_DEMO_WHO` still reads "azurik-modkit" in `devkit/xemu/queue.py`.
5. **The gate's main runs:** AzurKit's `land.py` and `fullsuite.py` have no
   1-in-5 run on `main`, no session-end whole run and no main-red rule
   (4.17a's default; AzurKit's CI covers `main` today).
6. ~~`ledger check`'s three ids allocated twice~~: D973's and D976's
   results and D1033's addendum are annotations of their decisions now.
7. ~~The toydb settings tests in `test_randomizer.py`~~: moved into
   `tests/test_rando_db.py` by 4.52c.
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
12. **The suite lock's order** (D1222): macOS's flock hands a released
    lock to its first blocked waiter, even a stopped one, so a window seat
    waited hours behind every queued gate. Step 4.47a, queued last, makes
    gates and the window poll and take turns. Owed: `$EV/tools/window`
    took its .4.47a version, and every queued lane now carries 4.47a.
    Owed: `land --selftest` on `main`.
13. **The gate's P2** (D1215, two locks): its commit (8102f56e on
    `p2/4.43b-gate-cuts-p2-p1-p4`) waits for a drained queue and its trial
    pair (about an hour of window), adopted only if no perf verdict turns
    slower and the starved count doesn't grow. Rebased over 4.47a, it owes
    the test patch 4.47a's report gives. `$EV/tools/landq.py` takes its
    .4.43b version once 4.43b1 (P4 and P1) is on `main`.
14. **The landing queue's loose ends** (`$EV/tools/landq.py`, seen
    2026-11-12): a queued or running gate of an entry that was rebased,
    moved or dropped keeps its place and takes turns at the suite lock,
    and landq never ends it (the orchestrator killed each by its pid);
    landq doesn't check an entry's tip and liveness again just before it
    rebases or gates it; its runner held about 790 MB after 13 hours, and
    each poll costs CPU; one rebase stopped with "Could not execute the
    todo command" and no conflict named, where the same rebase by hand
    went clean (4.37m1); and no command holds an entry already queued
    (D1238's pause stopped the gates' runners with SIGSTOP instead).

## 11. This Mac and infrastructure

1. **Disk:** 179 GiB free at writing. ModMG's batches in `/private/tmp`
   are the owner's: never touch them (D1140).
2. **Ours to remove after landing:** the 11-10 session's lanes and their
   `p2/*` branches, each once it lands; the content worktrees 4.6p-content
   and 4.6r-content and ModelKit's 4.15a8 lane, if still there. Done: the
   worktrees 4.30, 4.31, 4.32, 4.6r, stack2 and stack3 and the 128 old
   branches (the six kept were read and deleted, D1200).
3. **Our `/tmp` leftovers:** the 4.6e home folder and the 4.6f take log.
   An empty `/private/tmp/rp411` (11-06) has an unknown owner: leave it
   (D147).
4. ~~Six landed lane branches on the public AzurKit repo~~: deleted; the
   public repo holds only `main`.
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
     lists (ci55): a security-only item, so no lane (D1162, D1219).
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
8. ~~D1076, D1084's announcement drafts~~: retired; none is drafted or
   suggested again (D1208).

What only the owner does:

9. File the Chromium bug from its draft (D1111).
10. ~~Post the announcements~~: none is drafted (D1208).
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

~~AzurKit refuses a mod file's level patches by name~~: since 4.41b a
mod file's level moves build, by the vanilla level's name or id (a rename
stays refused, by itself), pinned by test_edits'
`test_a_level_move_means_the_vanilla_generator_whether_split_across_mod_files_or_after_the_randomizer`
and the Modkit mod-file test's refusals; the tests below are struck.

- ~~`test_edit_layers.py:343`
  `test_level_patch_targets_same_slot_whether_split_across_mods_or_not`
  (D1171).~~
- ~~`test_edit_layers.py:424`
  `test_randomize_full_level_patches_mean_the_input_levels_entities`
  (D1171).~~
- ~~`test_edit_layers.py:483`
  `test_a_level_patch_float_saturates_past_float32_range_and_refuses_nan_or_inf`
  (AZ-181; D1171).~~
- ~~`test_edit_layers.py:547`
  `test_a_level_patch_name_without_a_marker_means_the_input_levels_slot`
  (AZ-183; D1171).~~
- ~~`test_edit_layers.py:584` `test_m16_missing_patch_keys_are_errors_not_keyerrors`
  (D1171).~~
- ~~`test_edit_layers.py:595` `test_l21_raw_patch_rejects_malformed_entries`
  (D1171).~~
- ~~`test_edit_layers.py:611`
  `test_l21_raw_patch_rejects_negative_and_float_offsets` (D1171).~~
- ~~`test_edit_layers.py:623` `test_l21_raw_patch_still_applies_valid_entries`
  (D1171).~~

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
