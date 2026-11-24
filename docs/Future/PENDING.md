# Pending work

Every task still open when the 2026-11-08 session ended (Step 4.32, which
rewrites Step 4.23's list). When it was written (2026-11-09, about 04:00
PST), `main` was 6a99347f: stack 2 had landed (the Variants editor, the
whole Modkit port and its test-port lanes 4.27-4.29). v1.0.1 was the last
release, and stack 3 (4.31, then 4.30) was queued on `main`. Modkit's
checkout was deleted that session (D1171). Everything Modkit had is now
AzurKit's or is retired by name in group 13.

Step, D, AZ and Q ids are the private ledger's. When an item is done, drop
it in the commit that does it, and add new items to the group they fit.
Nothing waits on the owner except the owner-only acts in group 12 (D115).

Step 4.47c brought it up to date on 2026-11-11, against the landing
queue's tail (09564439, behind 1.0.3's release commit 7a4bab60), after
the 11-10 session's steps 4.37-4.47. A done item is struck to one line
naming what closed it, so the numbers that tests and decisions cite still
point; a new item takes the next free number in its group. Step 4.47g
added the 2026-11-12 session's items (2.5, 9.43, 10.14) and brought 10.12
up to date. Step 4.59a brought groups 2-6 and 11 up to date on 2026-11-14
against `main` d1823858, after 1.2.0 (D1264's sweep). Step 4.63b brought
group 9 up to date on 2026-11-14 against `main` dd5f925a (1.3.0), D1264's
last sweep: each item still open names the lane that closes it
(4.64a-4.64g), and group 12 holds its questions' defaults. Step 4.74a
brought it up to date at the 2026-11-15 session's wrap-up (D1304), against
`main` ffa5f9ba: the death realm unlock (4.71a-e, 9.49) and 4.73a had
landed, 1.3.1 was out, and 1.4.0 was cut in the same lane (2.9). The next
session starts at group 6.

## 1. The Variants editor's first Check (D1181, D1192)

1.1 is out (2.3), and every path holds its line. What is left here is
polish, after the next session's research (group 6, D1304).

1. **The target** (D1244, amending D1194 and D1201; D1204): tiered by how
   often players meet it. A Check players meet often (her own copy's first,
   after her copy's first edit, after Scale, a Jiggle stiffness or a colour,
   and by default, as Step 4.55a's rows start, after a sound, Import PNG,
   Moves, Attacks or Effects edit) takes 30 s at most in each
   of WebKit, Chromium and Firefox and 15 s in the app; a rare one (after a
   Shape edit, one with no shipped parts) and a reshape's first build and
   pictures 90 s and 45 s. The perf gate holds each op to its tier's line,
   one past it a debt row (Step 4.49a; INTERNALS.md's tiers). It is
   measured on this Mac, busy, beside other projects' load (D1107): no idle
   rerun and no line change but the owner's; on CI's runners the tests keep
   their bounds. Rounds go on until every path holds its line with margin.
   ~~Then one real-Safari first Check, in one window (D1089, D1202)~~:
   done on 11-15 on 1.3.1's site in Safari 27.2 (the session's Safari
   read). Her copy's first Check S78 took 15.9 s, the same Check again S79
   1.9 s, a let go S81 4.9 s and the Check after it S84 41.3 s, each within
   its line with a moving bar, and the tab survived (one WebContent
   process, 2.77 GiB peak footprint). What it leaves is 1.5's.
2. **Where it stands** (main's `--all` run of 11-14 on e2881d3e, 1.3.0's
   parent, medians on this Mac): her own copy's first Check reads S78 3.9 s
   in WebKit, 3.7 s in Chromium and 5.9 s in Firefox, A92 2.2 s in the app.
   A Check after a Shape edit reads S84 37.6, 40.0 and 52.0 s, A98 14.1 s
   in the app; one with no parts S88 49.7, 53.0 and 75.8 s; a reshape's
   first pictures S52 59.5, 60.0 and 83.8 s, A60 28.4 s; its first build
   A31 22.4 s; the quick preview A95 1.3 s. The same run's release
   reference (1.1.1's) read S84 107.7 s in WebKit, A98 45.3 s, A60 50.5 s,
   A31 41.1 s and A95 10.4 s. Natively and serially a Shape-edit Check
   takes 20.7-20.8 s, from 24.0-26.7 s on the stack below the
   subdivision's kernel.
3. **The plan** (4.37e's design): round 6's A (4.37e1), C (4.37e3), F
   (4.37e4) and B2 (4.37m1) landed. D1, E and D2 landed in 1.2.0 (Steps
   4.55b-4.55d: the mesh plan's position steps, the rig and the
   subdivision compiled, bit for bit their twins, and the quick preview's
   moving bar), with their parts re-recorded (4.55e: booblord's content
   v11).
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
   - ~~perf rows that time a Check after a Shape, Scale, Jiggle or colour
     edit and one with no parts~~: done by 4.37e0 (A98, A99, A104-A106,
     S84-S88), on `main` since 1.1.
5. **The parts' download:** a first Check's 24.5 MB of parts come with no
   bar, and no pytest drives a real browser through a shipped fetch (S78 is
   the only proof). The session's Safari read (1.1) measured it once: on
   the live site real Safari's first Check took 15.9 s, against Playwright
   WebKit's 7.7 s from a local clone, its first 6.6 s an indeterminate bar
   (likely the fetch, not shown). That is within 30 s with 14 s of margin,
   so no debt row; the download's own bar is the open lever.
6. ~~Parts keyed by their inputs~~ (D1195): landed in 1.1 (4.37m1;
   e6e28279, 3683263c). Each Check part is keyed on its stage's inputs
   alone, so every app takes the recording host's parts, close enough off
   it (D1016).
7. ~~A variant's pictures, dressed~~: fixed by 4.46a1, carried in 4.55e
   (keyed on `parts.VERSION` and the drawing's files).
8. **The Firefox Shape-edit gap** (D1209, D1244): its line is a rare
   Check's 90 s (S84). On main's 11-14 `--all` it reads 37.6 s in WebKit,
   40.0 s in Chromium and 52.0 s in Firefox (one sample each; 11-11:
   113-117, 180 and 256 s), each under 90 s with a moving bar, so no
   browser's goes under group 9's known flaws. The rare Check with the
   least margin is now Firefox's S52, a reshape's first pictures, at
   83.8 s (6.2 s), then its S63 at 79.3 s and S62 at 77.2 s.
9. **Paths with no perf row** (4.49a's design): Step 4.55a timed the
   page's. A107/S89 (a sound edit: the Sound line), A108/S90 (Import PNG),
   A109/S91 (a Moves pick), A114/S92 (the Attacks tab's Damage) and A115/S93
   (an Effects row added, then its first number) time a Check of booblord's
   copy after each, at the frequent tier: `perf.check_tiers` starts a new
   heavy op frequent, and a rare line for those after Import PNG or the
   Moves, Attacks and Effects tabs is the owner's call. On 11-13 (load
   5-10) their medians were 3.0-7.4 s in the app, 5.9-17.7 s in WebKit,
   5.3-15.9 s in Chromium and 6.9-26.3 s in Firefox, each within its line;
   the closest is Firefox's Check after an Effects edit (S93: 22.0 and
   30.7 s). What is left:
   - ~~The first Check after any edit of her copy~~ worked out her whole
     dress: fixed by Step 4.60b (D1273). The page hands a recipe back
     with its numbers as JavaScript writes them (1.0 as 1, -0.0 as 0),
     and the parts' keys read a spec by its `repr`, so the first edited
     Check asked other keys than her own Check had kept. The sdk now gives
     an edit, its sha and its Save, Save as and New from this the number
     forms the saved recipe holds wherever the numbers are equal. On its
     gate A116 read 6.7 s (22-33 s before) and S94 17.2 s in WebKit (51-55
     s), her own Check unchanged (A92 4.1 s, S78 7.3 s). Left: a copy
     saved from the page under 1.2.0 or before keeps the page's forms, so
     its first Check works the dress out once more (not migrated, D115);
     ~~an edited community-only character (sent "unsaved") still checks in
     the page's forms~~: fixed by Step 4.70a (D1288), its first Check after
     an edit missing 1 part (the edit's own stage) where it missed 10.
   - **A texture row** (the recipe's `textures`) has no control on the page
     (JSON only, 4.37e's F4), so no row times it: about 21 s natively and
     37 s on the site's engine (4.37a's P5). Import PNG is a `colours` op on
     the dressed body, 2.7 s natively.

## 2. Releases and content

1. ~~1.0.2~~: out on 2026-11-09 (tag `v1.0.2`, 15c16383).
2. ~~The content push~~: the hub's `main` is booblord v12 (baef191, which
   needs 1.3.1) since 1.3.1's publish (2.8), after v11 (a3bf5e7) from
   1.2.0's (D1266); CI's `CONTENT_COMMIT` pins v13 (2.9).
3. ~~1.1~~: out on 2026-11-13 (tag `v1.1.0`, d226ddad), with 4.38a and
   4.38b.
4. ~~1.0.3~~: out on 2026-11-11 (tag `v1.0.3`, 7a4bab60), with 4.37r and
   4.37h; 4.37t went out in 1.1.0.
5. ~~booblord's rework~~: content v10 with 1.1.1 (tag `v1.1.1`, 719cfba5;
   Step 4.48b); v11 keeps her v10 recipe.
6. ~~Content that fits the app it reaches~~: done in Step 4.59b. The
   manifest's top-level `needs` (`{id: "1.3.0"}`) greys an entry too new
   for the app with "update AzurKit", and Install and Update refuse it
   before any fetch; the sdk reads it, as `content.py` is among
   `parts.SOURCES`. The content repo's `scripts/check.py` takes `needs`
   and `description` (its commit c096e10, pushed when 4.59b lands). It
   helps the apps after 1.2.0: the hub sets `needs` when its `main` moves
   at a release's publish, and an app up to 1.2.0 still refuses a moved
   recipe after the fetch, its line unchanged.
7. ~~1.3.0~~: out on 2026-11-15 (tag `v1.3.0`, dd5f925a; published
   12:18Z, D1275, D1291), the last Intel Mac app (D1290).
8. ~~1.3.1~~: out on 2026-11-15 (tag `v1.3.1`, a794cee5; published
   17:27Z; D1282, D1300). It drops Intel Macs (D1290) and carries group
   9's fixes and the polish batch 4.70a-c: the community-only forms, the
   pool's quiet stop, and the lock's cryptography cap lifted as cleanup
   (D1299), which closed the three Dependabot cryptography alerts. Content
   `main` moved to booblord v12 (baef191), which needs it. Its CI passed
   Linux's three parts at the first try (run 43730247885); main's run
   before it lost Linux's runner once (43713171050, green on its rerun;
   8.37).
9. **1.4.0**: cut by Step 4.74a with the death realm unlock (4.71a-e,
   9.49; D1301-D1306) and 4.73a's test guard (8.18), published when its CI
   is green (D1145, D1170). Booblord's content entry goes to v13 (4.71e's
   re-record, 10.18): CI's `CONTENT_COMMIT` pins cffa6e4 (v13, its needs
   still 1.3.1), and at 1.4.0's publish content `main` moves to db880f7
   (v13 needing 1.4.0), so the apps up to 1.3.1 keep v12.

## 3. Stack 3 and 4.31's outcome

1. ~~Stack 3~~: landed (5a3b0954); 4.31 and 4.30 are in 1.0.2.
2. ~~A31 and A60 were load, not code~~: stale (2026-11-14). The reference
   is 1.1.1's run (41.1 s, 50.5 s), and group 1's kernels halved them
   (4.55e's gate: 21.9 s, 27.5 s). A60 reads 28.4 s on main's 11-14
   `--all`, with a bar, under its 45 s line, and no debt row.
3. ~~4.30's perf watch~~: read 2026-11-14: `world()`'s size doesn't show.
   On stack 3's gate S19 read 0.069 s, S21 1.27 s, S70 0.357 s and A25
   0.351 s, against stack 2's 0.068, 1.40, 0.318 and 0.521; flat since.
4. **4.30's prose nits:** `characters/draw.py:299` and
   `randomizer/art/draw.py`'s module docstring and `:289` still name the
   deleted `body_preview` and `draw_previews`, and `draft/tiers.toml`'s
   comment names `tier_gap`. Each edit moves a recorded digest: the
   built-ins' picture keys (record_goldens' `DRAWN`), `ART_VERSION`, and
   with tiers.toml every level's derive stamp. So they ride on the next lane
   that re-records art and the characters' pictures, or restacks.

## 4. Modkit's delete and the switch (done 2026-11-09, D1171)

1. ~~ModelKit's re-point~~: pushed over SSH (17637b2 on ModelKit's `main`,
   D1183); its leak guard names AzurKit's two manifests, the skill is
   installed and the content install is gone. Its own nits: group 10.
2. ~~Memory~~: AzurKit's project slug holds it, both `autoMemoryDirectory`
   settings point there, the old folder is kept (D1187).
3. ~~The xemu fixtures~~: sums 8 of 8 (2026-11-14); every sitting since
   11-09 boots from them.
4. ~~Tags~~: Modkit's archived repo holds `main` (f482ea041) and 14 tags,
   `reach-freeze` among them. `oracle-rando-6` and `modkit-final` were
   never pushed; the cites carry 8bfef0ca6, `main`'s parent, by sha.
5. ~~The delete~~: done 2026-11-09 (D1171, D1189); the empty folder is gone.
6. ~~Modkit's `$EV` tools~~: its halves are out (Step 4.59c, swapped
   2026-11-14): the modkit profile, fullsuite's Modkit gate with
   `suite_rules.py` and `suite_graph.py`, landq's Modkit queue and
   self-test and the Modkit branches of prune, ledger, brief and land;
   waitfor still reads `suite-receipts`. Every tool's self-test passed on
   the live set. The `.before-*` copies were thinned to the newest each at
   the 11-15 wrap-up.
7. ~~The archive~~: archived and private (D1185).
8. ~~Checks that needed Modkit~~: retired by name under D1171 (4.6i's
   end-to-end build, 4.6r's full build, 4.6j's plan, 4.13b's soak).
9. ~~Residue~~: in the evidence folder (G9).
10. ~~The xemu fork drive's discs~~: the drive is deleted (D1190); its zips
    stay in the evidence folder.

## 5. The 2026-11-09 session's wrap-up (done)

1. ~~The handoff log~~: its 11-09 summary.
2. ~~Memory~~: D1171-D1193 and the delete.
3. ~~A next-session prompt~~: 11-09's; session 05d17dd5 started from it.
4. ~~The whole run on `main`~~: G1's full receipts up to 15c16383.
5. ~~prune and the orphan sweep~~: nothing to delete (11-11).
6. ~~The lanes and branches~~: deleted 2026-11-10 (D1200).

## 6. Reach and the randomizer's research (the next session, D1304)

The next session starts here (D1304): randomizer and reach research
loops, the reach engine open for research again. Its order: 6.6's edits,
then 6.5's four resume steps, then group 7's reach and derive ids, 9.26,
6.7, 6.8 and 9.49's next steps, 10.3, 10.11's P7(b), "0 logic bugs"
(D522), V21 and V22, then 8.29, with 3.4's nits on the first lane that
restacks or re-records the art. Beside it: D1075's read at its start
(12.7), the Linux memory lane (8.37), S82 if it repeats (8.38) and the
parts' narrower key (10.18).

1. ~~x7's route graphs~~ (D1172): 4.13f built all 44 (35.4 GiB) from
   5a3b0954 on 2026-11-09. They are stale again: the 11-10 reboot moved
   `router_key`'s device number, and 4.52b's `physics.py` edit (e9d55a12)
   moved every key. Nothing but the reach research reads them, and
   `load_router` rebuilds one on first use (0.7-54 s). The 11-15 wrap-up
   kept them (D1305); the rest is 5's.
2. ~~The 21 retired proof records~~ (D1175): 4.13f's reading stands
   (675f3e2b): records stay as history, their marks resolve and plans don't
   move (24 shipped marks rest on 18 of them). Re-proving them is 5's.
3. ~~Frozen reach data~~: stale since D1175 (675f3e2b). `recheck` passes
   over every retired record, so no level stops at the teleport. The 1,337
   conformance snapshots are 5's.
4. ~~4.13e's last re-points~~: done by 4.59d (INTERNALS' "Not ported"
   drops `db-extract`, the loader's `contact_stale` issue names `python -m
   devkit reach l3-contact`, `docs/REACH.md` points at group 7, and a
   contract test holds the engine's messages to scripts the checkout has).
   9.48's message, the last owed, is fixed by 4.64e (63837c32).
5. **The reach backlog** lives in the private plan: R1.23-R1.25, TD.2,
   TD.2b, TD.5-TD.7, R2.19a-j, the improvement rounds, the all-level run and
   R2.16g. D1048 paused it, D1143 froze it (no budget, answering D977),
   D1212 and D1278 kept it frozen, and D1304 resumes it for the next
   session's research loops (v2, D609). Resuming it also:
   - drops `st_dev` from `router_key` (`devkit/rando/draft/l3_goal.py`, with
     a test beside its router-key test);
   - rebuilds x7's graphs (`build_routers.py routers 90 ...`, nice 15, in
     place);
   - re-proves the retired records' marks;
   - re-takes the conformance snapshots.
6. ~~The unfreeze edits~~ (D1304): done by 4.75a, but for the brief's
   annex A1, the orchestrator's.
7. **toD1's door is in the sewer, not the temple** (sitting 4.71c-R1a's
   skeptic): the logic leaves toD1 from town_z020 (Z021, the temple,
   `town.toml`) and puts D1_Town's arrival there (`d1.toml`), but d1's
   elevator deck is in the sewer (Z003), which a player with no kit leaves
   only through d1 (air 1 or more). It is harmless with the death realm's
   door, whose counted realm still needs 3 of each element (`solver.py`);
   a door loosened below air 1 moves both to Z003 first.
8. **Town's plaza-to-sewer drops** (the same skeptic; read again by Step
   4.76d and its review): under each of the sitting's 4 drops the first
   solid is a LandShape (gameSolid 1.0, nothing drives it) at +12.2-12.3 m
   (the sitting's drop rays). `town_central -> town_z003` is a `physics`
   row that stands without any `sweep` edge, but four `assumed` rows into
   town_z003 rest only on `sweep` edges into the sewer (town gated with no
   pair flown drops them): town_z612's `true` and town_z009's, town_z045's
   and town_z152's `air>=3`. Of the derive's five `sweep` drops into the
   sewer, the one from town_z612 falls 12.3 or 12.7 m, as the sitting's
   did; whether it is one of the four is open. Step 4.76d's witness gate (a
   gated level's sweep edges enter logic only where the reach engine flew
   them) or a hold takes these rows, not a derive fix.

## 7. The open issues from Modkit's ledger

The private ledger (D952) holds Modkit's 29 open issues. After 1.1 the
work comes here and to group 9's known flaws and editor leftovers, reach
staying frozen (D1212) until D1304 opened it again; 4.40b's triage readies
their lanes. The reach and derive ids are this session's (group 6, D1304).

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
    33 CI runs from 11-11 to 11-13; counted again from 4.56b: 2 in 12 arm64
    vanilla jobs over main's six runs to 11-14, both in run 43617501572, a
    worker thread's SIGSEGV at 0x50 and one with no crash report, neither
    JSC's StackVisitor assertion; the `Error.stackTraceLimit = 0` lever in
    WebKit's engine worker covers only that assertion, ci47's, so try it
    only if a report names it again, 9.12). ~~Firefox's timer that lost
    once~~: fixed by 4.54a (the word-list Undo was pressed before it was
    enabled); a lost edit still waits 600 s with no Data tab state in
    `hang()` (4.5g).
13. ~~Intel: page-load stalls; ci19's extra 2 h; WebKit's drawing threads
    outranked (ci21)~~: retired by 4.67a, no Intel runner from 1.3.1 (D1290).
14. Windows: ci34's cause; ci39's load failure; Firefox's temp disk
    (9.13): it dips 4-7 GiB through a vanilla shard and is mostly given
    back (main's runs to 11-14: lowest 21.2-26.2 GiB of 27.4-30.4, at most
    4.3 GiB held at a shard's end), and the pack golden's 60-minute hang
    hasn't come back since 4.4ci18; if a shard runs short, a
    diagnostics-only commit names what holds it (the 1.0.1 survey's 4.5d).
15. WebKit: network-process endings (ci41: a RequestedByNetworkProcess
    ending still costs 120 s); why WebKit leaves the page's process (ci18);
    what triggers the zero-headed message (4.5s: if it recurs, the call
    fails at once naming it and D1170's rerun records it; 4.37k retired
    `_page.past_refusal`'s unrecorded redo); the pool's cut mode at S62 on
    the capped site (9.11: B's stale build ahead dropped at a heavy ask,
    `web/workers.mjs:358`; never sampled, 4.3r4s's review), self-reporting
    since a peak past 6 GiB blocks (the capped site read 5.76 GiB on main's
    --all run of 11-14); ci31's Characters stall; the
    parts test's closed page `[webkit]` on macOS arm64 (4.37f's C.13).
16. Others: ci17's three; what held ci27's GIL; ci37's CI ValueError;
    4.5m's second failure; 4.5n's frozen capped A32; S59 under 20 extra
    threads (4.4bf); WebKit's GPU threads on a 4-core runner; ps under
    `taskpolicy -b` taking 8-12 s while the efficiency cores are busy
    (ci36); the app's Live marks test `[webkit]` on Windows (C.14: a
    flake's first try's error lines are kept now, 4.37k); the collected-spot
    test's hand click `[firefox]` on Windows (8a3128b; its failure now names
    Show collected and the fresh pickups, 4.37k).
39. test_hosts' Variants view test
    (`test_the_apps_variants_view_keeps_your_variants_where_modkit_does_and_checks_one_on_your_image`):
    120 s timeouts `[chromium]` (11-10) and `[webkit]` (11-11), each
    passing its rerun; quiet since, with no fix named.

### Test-harness follow-ups

17. ~~`_page`'s load, ending and redo gaps (N1-N3, 4.5p)~~: fixed by 4.37k
    (062dac4e, 3540afb1, 6aac6518; 2d1f3ebf retired the redo).
18. Silent waits:
    - ~~Four bare `browser.new_context()` calls (test_hosts, test_site and
      two in test_service_worker) (ci14)~~ and ~~`_bare_page` callers'
      unbounded `context.close()`, two in test_site (ci15)~~: fixed by
      4.73a (2d6a3379: each takes `_perf.new_context` and `_perf.shut`).
    - ~~test_hosts' app-page tests left their `browser.new_page()` open
      (nine) or closed it only on success, and `Site` and `_bare_page` left
      their context open when a later setup step failed~~: fixed by 4.73a
      (0c653205, 67705df4); conftest's `_nothing_left_behind` now fails and
      closes any context or process a test leaves (dcf47935, 2b2146a7).
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
37. **Linux's vanilla part with test_site.py's Chromium tests runs short of
    memory** (part 2 of 2 under 1.3.0, part 3 of 3 since; D1293: worth
    finding as polish). It dipped to 2.2 GiB free (job 132838907070), and
    its first try lost the runner 27 min in (run 43713171050, green on its
    rerun); 1.3.0's two-part run fell to 0.9 GiB and was shut down (run
    43675884120). 1.3.1's CI passed all three Linux parts at the first try
    (run 43730247885).
    - Free memory sits near 8 GiB through the light Chromium tests, dips
      in the heavy last ones (the image walk, a save while hashing, the
      weapon, the pieces) and comes back to 12.8 GiB at the module's close.
    - Placing the cause in Chromium rests on the durations table's pace: CI
      keeps no per-test times or per-process memory. On this Mac the same
      233 tests carry nothing from test to test, and since 4.73a conftest
      fails and closes any context or process a test leaves (18).
    - ~~Step 1, Linux's minute line names Shmem and the tier's memory by
      kind~~: done by 4.75e; read it in main's next CI run.
    - Step 2, the lever, isn't built: a Chromium relaunch every 10 tests (or
      under 6 GiB free, conftest's D1260 path) or a fourth part, which
      splits the Chromium tests 34/19, chosen from that run. A relaunch
      helps only if the memory is a held floor, not the heavy tests' own
      peak.

### Perf debt

21. Rows the gate recorded:
    - ~~A95 in the app (a warm quick preview after a Shape let-go), 9.1-10.8
      s with a bar moving only sometimes~~: fixed by 4.55b's bar and group
      1's kernels (1.2.0): 1.3 s, a pass, on main's 11-14 `--all`.
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
    lane. Their bar on main's 11-14 `--all`, after group 1's kernels
    (1.2.0): A31 22.4 s, A60 28.4 s, A92 2.2 s, A95 1.3 s, and in WebKit
    S52 59.5 s, S62 54.5 s, S63 51.6 s, S78 3.9 s and S81 2.0 s, each
    within its line. 1.1.1's full gate had read A31 41-43 s, A60 43-50 s
    and S52, S62 and S63 71-76 s, and stack 2's run A31 166.5 s, A60
    199.5 s and S52 140.7 s.
23. Saves (S06, S49, S50): WebKit's are a parked known flaw (9.45), though
    main's 11-14 `--all` read them at 1.03, 1.03 and 1.18 s. Chromium's
    pass (1.73, 1.90 and 1.86 s there; 2.13, 2.29 and 2.09 s medians in
    group 8's frequent-ops measurement, 11-13) on a thin margin: its
    browser process spends 2.5-3.2 CPU-s on a Save, so D1109 keeps it in
    research. A busy disk, not a full one, put them over (reproduced at
    184-198 GiB free). S72's freeze isn't in the latest receipts.
24. Firefox's Saves on their bar (D1053): S06 3.57 s, S49 3.53 s and S50
    3.42 s on main's 11-14 `--all` (6.54, 4.34 and 4.51 s medians in group
    8's frequent-ops measurement, 11-13). Its bare
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
33. ~~The perf gate reads RSS, not footprint~~ (4.4n's Q2, kept for
    1.0.0): accepted, no lane (D115's default at the 11-15 wrap-up). The
    9.35 it waited on, INTERNALS' perf paragraph, was fixed by 4.56a with
    no change to what the gate reads, so nothing is left to revisit it
    with.
36. S21 (the tracker, a reopen) went from 0.45 s to 1.2-1.6 s within
    stack 2 (fe61354c -> aecdedf9). Cause unread; it passes its 3 s line.
38. **S82 in Firefox** (a Shape slider's drag on the checked copy): "no
    progress" at 1.27 s, under its 3 s line, on main's 11-14 `--all`, that
    run's one debt row (D1170). Not read again since: the next `--all`
    reads it, and it gets a lane if it repeats.

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
2. ~~"WHITE cycles" in the build's character note~~: fixed by 4.64e
   (63837c32): X36's clause says "LB cycles its N attack sets",
   `SETS_SAID` reads either word, so a stored answer still counts, and
   the comments under `tools/characters/` name LB.
3. ~~Beamlord's notes show decision ids~~: fixed by 4.52b, and the content
   repo's copy by his v2 (4.55e).
4. ~~Booblord's own four spin picks unwatched on the vase-less body~~: sat
   by 4.48b's record (2026-11-12: 6, 6, 6 and 30 at 1.5 m on all four);
   the irises' re-key carried with no spin build (D1256).
5. **4.20's nits:** ~~an Easy plan that keeps Normal's own records
   Normal's attempt number; the bar sits at "try 3 of 3" while Easy works
   out Normal's plan~~: fixed by 4.64d (the plan's `attempt` is documented
   as the kept candidate's, an Easy or Expert spoiler's summary line says
   so, and the bar says "comparing with Normal's plan"). Left: in the app
   Normal's attempts run serially beside the pending ones (perf only: A77
   times an Easy seed's Track, 0.06 s, but behind its head start, so no op
   times the serial work).
6. ~~The save warp and detours~~: fixed by 4.64d, the narrow way (12.19):
   with the warp counted, each save platform it leaves from is a way out
   of its level and town's platform a way in. Warp-ticked Easy, Hard and
   Expert seeds are Seed difficulty's fill 3 (`SEED_DIFFICULTY_FILL`),
   their fill 2 links and plans refused by name; seeds without the warp
   keep fill 2 (`WARPLESS_FILL`), as their placements didn't move, so
   their links still open.
7. ~~The chain's drain hit gives a light reaction~~: by design (4.3chain):
   D1045's chain on a hit needs the stun, and the game's heavy flinch
   would hold the chain's next hits for 2.58 s (AZ-765).
8. ~~The Live tracker's 'loading' fix~~ (ed1b044f): seen by 4.64g's
   sitting (2026-11-15). Main 6255372e's randomized build (76919fc26491)
   ran in a real-time oracle sandbox, Live on its shared RAM: every poll
   of the rows in w2 read in level (the session's first poll aside, by
   the 2-poll settle), 60 of 60 standing and 60 of 60 moving (swimming,
   up to 32 m), and across a level switch to w1 one "loading" poll, then
   in level. The fixtures have no w2 state, so the switch was the debug
   menu's warp, which posts a levelSwitch's request; it shows the symptom
   gone on main, with no pre-fix control run. The Play and Attach demo
   was dropped (D1306, 12.17).
9. ~~Characters: a pause past REST still starts a build the next move
   drops~~: fixed by 4.53b.
10. ~~A stale first dress caught in a gap of its records takes
    `ahead.GRACE`'s kill~~: accepted as measured by 4.64c (the app on
    this Mac, its wheel and the checkout at 24 cores and the checkout at
    4, booblord's first dress after a Shape edit; the kill's clicks on the
    wheel): the dress takes 22-24 s, its longest record gaps 5.4-5.7 s
    and 4.8-5.3 s, so only a change in a gap's first 0.7 s still kills it;
    a seed's Track clicked at that change answers before the kill, in 1.5 s
    beside the running dress (1.4 s where the dress stops clean), and the
    next new seed's in 0.6 s on the new engine
    (0.1 s on the kept one), all under the 3 s line. No records inside the
    dress, so nothing rides 4.64e.
11. ~~Site builds without OPFS still copy twice~~: fixed by 4.53b; the
    pool's unsampled cut mode is a watch line (8.15).
12. ~~The arm64 WebKit engine trap~~: a watch line (8.12); its
    `Error.stackTraceLimit = 0` lever waits for a crash report that names
    JSC's StackVisitor again.
13. ~~Windows Firefox loses 6-15 GiB of temp disk and hangs~~: the hang
    gone since 4.4ci18, the temp a watch line (8.14).
14. ~~`procpool._peak()` returns 0 on Windows~~: fixed by 4.52a.
15. ~~OPENERS: the stale openers' compiled set leaks~~: fixed by 4.52a,
    but for two calls that end within one thread switch (no lock).
16. ~~A Firefox Save whose `flat.mjs` never loads stays greyed~~: fixed
    by 4.64a (`written()` gives up on a worker silent 20 s after its
    start, and the page makes the old copy, D1164).
17. **A closed Firefox tab leaves its last build's ~835 MB file in OPFS**
    until the next load or a Clear (4.5q; accepted design, no lane: a
    Save's download may still read it, and only an unsaved build's file
    could go at pagehide, at best effort).
18. ~~The site's Update fetches every file of an entry~~: fixed by 4.53b.
19. ~~The HTTPS content clone has no low-speed bound~~: fixed by 4.52a.
20. ~~The Windows and Linux frozen apps are console builds~~: fixed by 4.53c.
21. ~~The app's own server answers over HTTP/1.0~~: fixed by 4.5b
    (fd5f5ec4).
22. ~~A player's image named usa.iso or europe.iso in Downloads~~: fixed by 4.53c.
23. ~~A save edit's output guard doesn't fold case on macOS~~: fixed by 4.52a.
24. **source_hashes** is checked against both releases' vanilla files
    (4.6i; accepted, no lane): a mods file is release-free, so only a pin
    of `index.xbr` can pass on the other release, where its operations'
    own originals still refuse other bytes.
25. ~~A row's "main colour" can be a tinted near-black~~: fixed by 4.64b
    (a value floor of 0.1, which moved 130 of the 564 palettes the bases
    offer, each from a near-black, not her row alone).
26. **The reach aim's string drifts in rare cases** (2 of f2's 8,519 aim
    jobs; `docs/REACH.md`): parked while the reach engine was frozen
    (D1143, D1278), open again (D1304); its fix rides the next change to
    `aim.py`.

### The Variants editor

27. Opening another variant mid-Check drops its answer, but the engine's
    dress runs on, so the new one's Check waits behind it (up to a first
    Check's time). Accepted (D835), no lane: a cancel for one call costs
    about what it saves (the warm engine and its kept dress, 4.40b3).
    (After a drag during the Check, a pictures refusal's "Not drawn"
    giving way to the nearest note is no defect: that note is about the
    values now shown, 4.40b3.)
28. ~~The fits row's sha and `garret4_reference`'s hoe, unpinned~~: pinned
    by 4.27d (0d2873ec) and 4.52c.
29. ~~Old own copies of booblord_high refuse; old reshape-part keys miss
    once~~: accepted (4.6r), no lane: a copy made with New from this works.
30. Looks: ~~the status's "built in" and Live's bar wrapping at 1100
    px~~: fixed by 4.64b. The rest are accepted, no lane: the status leads
    with the recipe hash (the perf gate's Check predicate and the tests
    key on it); the hex box rounds exact ties away from zero, one unit in
    the last place (4.6e's review); the effect colour keeps the browser's
    own picker (native; the Colours tab has the wheel).
31. ~~4.6c's leftovers~~: done, the last (`variant_save`'s `from` checked
    as a name) by 4.38b.
32. ~~Community-only characters~~: fixed by 4.38b.

### Data, mods and the randomizer

33. ~~No page button for mod-template or entity diff~~: CLI only, the
    owner's decision (D1287, 12.15).
34. ~~`docs/RANDOMIZER_DB.md`'s TODOs~~: fixed by 4.56a (D115's defaults:
    no drop offered, the reserved keys with no version planned).
49. **The death realm unlock** (D201, D1301-D1306; AZ-836, AZ-837), on
    `main` for 1.4.0. The pack (4.71a: 0538efd2, f43c9747, af02e39d,
    fc1f9007) opens d1's seal without the five discs and makes Spideyzar
    far harder until all five; the randomizer's tick (4.71b: 15a9f1b2,
    15a1e81a, f23d18f1), off by default, counts the realm in the logic.
    4.71d set the defaults (a0fb00a6: damage 6, speed 2.5, longest wait
    1 s, movement 2.5) and wrote the outcome (b6f5f659, 2fb8e7b1); 4.71e's
    facts moved `parts.VERSION` (bc814e11, ab7d95ed, cd5ea928, ffa5f9ba;
    10.18). Sittings 4.71c and 4.71c-R1a with their skeptics passed R1 (a,
    b, c), R3 at L3, R4's exact lines and R5; U1 is closed (town's door
    needs nothing at 0 discs, even in vanilla), and 4.71d's defaults build
    the game files the sitting ran.
    - Open: R2 (the bridge drop and d2's six lens keys); R6 (d1's moved
      gems r1056 and r1099, not collected); R7 (skipped); the optional
      re-runs (R3-L3-S1 from 5 or more fight starts, R4's times with 5 or
      more checkpoints a side, the restore path); and the design's R3
      attack line amended to "attack picks at least 3x R4's".
    - The next session's (with 6.7 and 6.8): the realm's four fuel-spot
      proofs, as tick-only marks that keep `db_digest` and unticked seeds
      as today (no d1 or d2 spot is a proven non-gem spot, so the tick
      moves no item yet); loosening the conservative kit in d1 and d2; the
      maps' settings-free tips.
    - Known flaws (D835): at L3 Spideyzar's attack starts are about 2x
      vanilla's (14.6 against 6.9 a minute), not 3x, as his approach and
      clips bound the rate; his sourceless hits aren't scaled (2.5-5.4 % of
      his damage); a player with the pack alone can drop into d2 without
      the kit (U6), d2's way back needing its six lens keys; with the tick
      on, the maps' tips still name the discs.

### Docs

35. ~~The perf paragraph's Safari reason, S73 and 4.4's 6 GiB~~ (in
    INTERNALS.md, not AGENTS.md): fixed by 4.56a.
36. ~~The prose cites of Modkit's `LEARNINGS_HISTORY.md`~~: fixed by 4.56a
    (they name Modkit's archive, as does the game-reference skill's).
37. ~~DEVLOG.md's [Unreleased] link dead after `--remove`~~: fixed by 4.33
    (it is plain text now).

### Ideas the session ranked (after the port, D1131)

38. ~~Support plumbing~~: dropped, not built (D1206).
39. ~~"Play it in xemu" help after a Save~~: added by 4.64b.
40. ~~Play and Attach have never met a real xemu or the real admin
    prompt~~ (4.6k): the owner's demo is dropped (D1306, 12.17); headless
    sittings check them.
41. ~~A headline randomizer mode and a speedrun kit~~: the practice pack,
    race code and Live autosplit are dropped (D1304); the death realm
    unlock came first and landed (49, D1301; 12.16).

### Known flaws found since (D835)

42. **Audit pass 2's hostile-input findings** (4.45): parked, no lane
    (D1219), all still open in 1.3.0: the site's manifest read takes the
    whole reply before the engine's 1 MiB cap (U5); two entries' paths
    that differ only by Unicode form or a trailing dot or space share a
    file in the content folder, and one entry listing both spellings fails
    its install part way (U3); an entry's `variant.json` is parsed with no
    depth guard (U6) and `installed.json` read with no cap or value check
    (U7); and on Windows a zip unpacked into the app's data folder can
    replace the install's key file (store F2). U3, U6 and U7 are in
    `content.py`, a parts source, so a fix there rides a parts re-record.
43. **Covered faces removed** (E1, D1237): parked by the owner's decision
    (D1258), to revisit only if a model needs the last few percent. No
    Shape op removes faces (`docs/VARIANTS.md`), so faces a model's clothes
    always cover are drawn anyway. Measured on booblord v10 (E1's design,
    11-13): the faces covered in every frame of her 48 clips are a safe
    2.6 % (1.479x to 1.458x vanilla's heaviest vertex cost); a shadow LOD
    that keeps only each two-sided layer's outer shell, about 3 % of her
    bytes a flip (20.00 to 19.38 MB, an estimate; 1.479x to 1.433x by
    vertex cost), with no recipe change; and no Check gets faster (a fresh
    dress 69.1 s without, 70.1 s with the faces left out). Faces picked on
    the plan's weights leave holes once the rig re-weights her.
44. ~~booblord_human's eye-edge texel~~ (D1255): cleared by 4.64e
    (afa9f214, ca1225ce; D1281). A swap at the end of her row 1 colours
    takes texel (76,32) alone to her iris rim's brown: her exported page
    differs only there, and DXT1 re-fits that texel's 4x4 block (14 of
    its other 15 texels moved, none farther from its own colour).
    Booblord High Human inherits the swap, which reaches no texel of her
    1024 page. The owner carried Booblord Human's grade with no build;
    Booblord High Human's build is unchanged.
45. **WebKit's Saves past 3 s** (S06, S49, S50): parked (D1263: no more
    research). Main's 11-14 `--all` read them under the line (1.03, 1.03
    and 1.18 s), so no debt row stands now. All but 9-44 ms of a Save is
    WebKit's own download of the 2.75-2.93 GB image, at a plain copy's
    speed. Alone they pass (1.29, 0.90 and 1.67 s medians); beside one
    other process writing to the disk they read 4.43, 4.32 and 4.90 s
    (1.1.1's full gate: 4.41, 4.26 and 4.54 s), and no page lever moves
    them (group 8's frequent-ops measurement, 11-13). Chromium's pass under
    the line, Firefox's on its bar (D1053).
46. ~~A worker's record shown on the newest ask~~: fixed by 4.64f
    (52ffa428, 044be507): the pool passes a worker's records with the
    asks waiting on it (its job's and those queued behind F, never one B
    takes once free), and the page shows them only there (S79 unchanged).
47. **A 4-45 ms flash** (4.54e; accepted, no lane): a Check asked again
    unchanged whose own steps take a few ms flashes its keeping records
    (one to three frames) before its bar hides. A worker-side delay of the
    first keeping record would clear it, at the cost of 4.54e's pinned
    record order and S79's bar.
48. ~~The townsfolk kit's refusal names Modkit's
    `scripts/townsfolk_kit.py`~~: fixed by 4.64e (63837c32): it says to
    reinstall AzurKit, and `OWED_SCRIPTS` is empty.
50. **An Install clicked during a Build fetches only once that Build
    ends, and the pick's build can be dropped young** when changes come in
    a burst within REST of the pick (4.53b).
51. **On Windows with no WebView2 runtime, the app's browser fallback
    can't be seen** (4.53c): Windows 11 and current Windows 10 ship the
    runtime, and the fix (a message box in place of the endless wait) is
    Windows UI that no test here or on CI reaches.
52. **Over a long load Live shows "paused", never "loading"** (4.64g's
    sitting): it reads the old level as held until the new level's first
    read. Cosmetic: a lane only if the owner wants "loading" shown during a
    load.
53. **An edited community-only character's recipe sha is the page's
    forms'** (4.70a): the page asks `variant_read` with no folder, so the
    status line's "recipe <sha>" can differ from the Check's and the Save
    as copy's. Cosmetic (no part reads it); its fix is the page sending the
    folder.

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
12. ~~The suite lock's order~~ (D1222): fixed by Step 4.47a (gates and
    the window poll and take turns); `$EV/tools/window` took its .4.47a
    version, and `land --selftest` passed on `main` (11-14).
13. ~~The gate's P2~~ (D1215, two locks): adopted (D1271: D1215's rule
    reads "no perf verdict turns worse"; its trial pair turned A107/app
    from bar to pass beside, nothing slower, the starved count down) and
    landed as Step 4.58c on an empty queue, the xemu oracle also waiting
    on a gate's `perf.lock`.
14. ~~The landing queue's loose ends~~: fixed by Step 4.58a's
    `$EV/tools/landq.py` and `waitfor.py` (11-14). landq ends a gate whose
    entry it rebases, moves, drops or holds (by its receipt's pid, checked
    first), checks an entry's tip again just before it rebases, gates or
    lands it, keeps git's whole error and retries once with `--onto` a
    rebase that stops with no conflict named (the cause: a run still
    writing in the lane), reads each gate's mode in a child process (its
    runner stays near 44 MB), and holds an entry (`land --queue hold` and
    `unhold`) in place of SIGSTOP; `waitfor` reads a gate in its flake or
    perf stage as running. It also took 4.43b's P1, one perf stage a batch.
15. **The content a run tests** (Step 4.58b): a gate unpacks `tests.yml`'s
    `CONTENT_COMMIT` from the sibling clone, but a plain `pytest` run
    still reads `AZURKIT_CONTENT_SOURCE` or the clone's working tree, and
    a stack that only moves `CONTENT_COMMIT` runs no test that reads the
    content (`fullsuite.plan` has no rule for it). A small lane.
16. **ModelKit's nits** (4.15a8): its adapter test's runner stand-in still
    handles `--export` (`tests/test_azurik_adapter.py:96`); `model rest`
    through `kit/rest.py` and v4kit's user build cache haven't run on
    AzurKit. ModelKit's next round runs them.
17. ~~No `--all` perf since 11-08~~ (911040d5): main's `--all` ran on
    11-14 on e2881d3e, 1.3.0's parent (Chromium, Firefox, the lag ops and
    the capped profile with D1017's 9 s and 6 GiB), and its perf passed
    with one debt row (8.38). fullsuite still takes `--all` only on main's
    clean whole run.
18. **`parts.VERSION` digests `core/facts.*.json` whole**
    (`parts.SOURCES`), so any pack's new facts site or function forces
    booblord's content re-record: 4.71e's death realm sites and
    `ai_think_base` re-keyed all 105 rows and took her to v13 (2.9), though
    only her two parts that hold keys changed bytes. The next session's
    lane: narrow it to the facts parts the swap reads (its functions,
    hooks and kernel slots and the swap's sites), which moves `VERSION`
    once more (a re-record and a content version). It carries what waits
    for a re-record: `parts.py`'s docstring line "the same bits
    everywhere" (4.60b), INTERNALS' "booblord and her own copy share her
    body", true only until the copy is edited or saved from the page, and
    `sdk.py`'s `needs` logic moved into `content.py` (4.59b).
19. **The landing queue's loose ends after Step 4.70d**
    (`$EV/tools/landq.py`, swapped live 11-15: a red parent's children
    are held, a plain rebase names each commit it drops, a hold costs no
    perf try and an orphaned perf stage runs again alone): a stopped (not
    red) parent's children still land alone; the entries behind a held
    child wait in order; `stacked` is read at add time only; an orphaned
    flake stage still costs a whole re-gate (`scripts/fullsuite.py` can't
    run it alone); `waitfor`'s docstring and `land.py`'s usage line lag;
    and 4.70d's swap script's `--rollback` checks no process and verifies
    no sha.

## 11. This Mac and infrastructure

1. **Disk:** the owner's Mac-wide rule, at least 100 GB free counting
   purgeable and 50 GB truly free (309 GB and 417 GB on 2026-11-14).
   ModMG's batches in `/private/tmp` are the owner's: never touch them
   (D1140).
2. ~~Ours to remove~~: the landed local branch `p2/4.37e0-held-rows`, the
   content clone's six old `p2/*` branches (main's v8-v11 supersede
   next-stack's and stack2's v6 and v7 parts), the 11-10 session's lanes,
   the content worktrees and ModelKit's 4.15a8 lane are gone (2026-11-14).
3. ~~Our `/tmp` leftovers~~: the 4.6e home folder, the 4.6f take log and
   `/private/tmp/rp411` are gone (2026-11-14).
4. ~~Six landed lane branches on the public AzurKit repo~~: deleted; the
   public repo holds only `main`.
5. **The game-data environment allows `p2/*` branches** (D1123): keep that
   while lanes get CI. Its revert is in the handoff log.
6. ~~nativekit writes each library in place~~: fixed by 4.59e (it writes
   each beside and renames it over, so a rewritten dylib is a new file).
7. ~~Dev-speed levers~~: dx7 is stale (2026-11-14). dx6 is done (Step
   4.60a, D1280): a changed area's perf stage times the heavy Check ops
   only when a characters path changed (the swap, `core/xbr`, its kernels,
   the store, the app's pool, the Characters tab's modules, `parts.mjs`,
   `web_tools.py` and the perf gate's own files); a change to `sdk.py`,
   `worker.mjs`, `workers.mjs` or `app/engine.py` leaves them to main's
   `--all`. ~~dx8, the variant golden as one test per case~~: measured,
   no split (Step 4.59f, 2026-11-14).
   - On run 43647927362 (c0532b6a) it takes 5-12 min a runner. Only
     Apple Silicon's longest part holds it (400 s of 116 min).
   - Split by case, it loses its 4-process pool: the 12 USA builds take
     324 s one at a time against 103 s here, about 1.5-3.5 min more on
     every OS's longest part.
   - Its check that each of USA's 85 shipped part rows is held by a fresh
     dress spans 5 or more builds (10 rows held by one own copy alone),
     so it holds only over the whole test.
   - The stale shard table it found (`tests/ci_durations.json` said
     `[usa]` took Apple Silicon 945 s, where the run took 400) is measured
     again from main's three latest green runs (Step 4.63a: Apple Silicon
     380 s; the Intel runner's table went in 4.67a).
8. **CI risks** (no work unless they recur):
   - setup-uv's own uv download sits outside the cache (its manifest is
     inline since 4.4ci43), so an outage can fail it, and the first run
     after a landing misses the cache on each OS (4.5t).
   - mcp brings in anyio, whose pytest plugin loads in every session
     (4.11f).
   - ~~pypi.org:443 in the harden-runner allow lists~~: security-only,
     dropped (D1162, D1219).
9. **Content size:** shipped parts carry the recording host's floats
   (D1016), so a swap change that moves a part needs a re-record. The hub
   repo is about 216 MB (2026-11-14). A whole re-record of booblord's parts
   adds about 100 MB (v6, v10), a two-part one almost nothing (v9, v11).
10. ~~D1081: revisit the Intel Mac app when GitHub retires its Intel Mac
    runners~~: D1290 drops it at 1.3.1 (4.67a): 1.3.0 is Intel Macs' last
    app, and no CI job runs on `macos-15-intel`. The lock's cryptography<49
    cap went with it in 4.70c (50.0.2; cleanup, D1299), closing its three
    Dependabot alerts.

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

9. ~~File the Chromium bug from its draft~~: dropped (D1269).
10. ~~Post the announcements~~: none is drafted (D1208).
11. The hub notes, only when the owner says (D134).
12. ModMG's disk use in `/private/tmp` (D1140).
13. ~~Remove the empty Modkit folder~~: gone by the 2026-11-10 session's
    start.
14. ~~See the MEMORY.md diff in chat~~: shown on 2026-11-09 (G6).

Group 9's questions for the owner (2026-11-14), each answered by the
default here until the owner overrules it (D115):

15. ~~4.6i's default: mod-template and entity diff stay command-line only
    (9.33)~~: decided by the owner (D1287).
16. ~~D1131's default: fixes first, no new player features until
    PENDING's lanes are done (9.41)~~: the death realm unlock came first
    and landed (9.49, D1301-D1303); the practice pack, race code and Live
    autosplit are dropped (D1304).
17. ~~The real-xemu Play and Attach demo (D205; 9.40)~~: dropped (D1306),
    with the Spideyzar fight D1303 had added: sittings and a skeptic set
    his numbers (9.49), and headless sittings check Play and Attach.
18. ~~booblord_human's eye texel (9.44, D1255)~~: cleared by 4.64e's
    colour op (afa9f214), the owner carrying her grade (D1281).
19. Seed difficulty's detours with the save warp ticked (9.6): fixed the
    narrow way (4.64d). `SEED_DIFFICULTY_FILL` goes to 3, so Easy, Hard
    and Expert share links made with the warp ticked refuse, by name;
    links without the warp keep working.
20. ~~Group 9's re-record (9.2, 9.48, 9.44; 4.64e) moves booblord's
    content to v12~~: done. 1.3.1 was cut after 4.70a-c (D1300) and
    published on 11-15 when green, and content `main` moved to v12
    (baef191) at its publish (2.8).

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
