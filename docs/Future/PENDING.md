# Pending work

Every task still open at the end of the 2026-11-08 session (Step 4.23), from
four sweeps of that session's log, its reports and reviews, the port's plans
and git. When it was written, `main` was v1.0.1 (fe61354c) and the port stack
`p2/next-stack` (331bf8a0) was 157 commits ahead of it. When an item is done,
drop it in the commit that does it, and add new items to the group they fit.
Step, D, AZ and Q ids are the private ledger's. Nothing here waits on the
owner except what group 7 lists (D115).

## 1. In flight now

1. **The port stack's gate and landing** (D1168, D1170): `p2/next-stack`
   holds 4.6a-q, 4.11b-f, 4.13a-d2, 4.14a2-a3, 4.15a1/a3/a4/a6, 4.18a/b,
   4.19a/b, 4.20, 4.21, 4.22, 4.5o and 4.5w. Its full gate was running when
   this was written (an earlier run was stopped). It's finished when the gate
   is green under D1170 (one rerun per flake, a perf op over budget becomes a
   debt row), the late review is done, `main` is fast-forwarded and pushed.
2. **Rows only the stack's gate runs:** test_site, test_hosts and
   test_service_worker in full in the three browsers; the vanilla tier of the
   lanes' files; `test_characters`' variant goldens, `[usa]` and `[europe]`,
   after the shipped parts' re-record; the wheel and the Pyodide and
   frozen-app checks; the goldens for `src/`, `web/` and `native/`.
3. **The perf ops the stack adds or renumbers** (A87-A121, S73-S121, with
   4.6d's, 4.6e's A100-A103/S100-S103 and the Variants editor's A92/S78):
   only the gate's perf stage times them. An op over its budget is a debt row
   (D1170).
4. **D1167 checked again on the stack:** a first Check well under a minute
   on the site was met on the 4.6p lane (S78 medians: WebKit 9.97 s, Chromium
   10.37 s, Firefox 12.86 s; the capped site 5.16 GiB). The stack then
   re-recorded the shipped parts, so S78 and A92 must hold again at its head.
5. **Ghidra in AzurKit's main checkout** (4.11d2): run
   `uv run bootstrap.py --with re` there (about 1.2 GB). test_ghidra's three
   JVM tests have never run, and a full run without Ghidra fails them by name.
6. **4.15a2, models-body** (built on the stack's head): its review found one
   defect. Two colour_preview pins, Modkit's garret4 tests ("with a look
   exports and checks its rows recoloured once" and "reads its png colours
   beside its file"), are neither ported nor named. Port both into
   `tests/test_model_authoring.py`, then add the lane to the stack and gate
   it. Two nits: the spacing in `model.py`'s `NO_SPRING =`, and the `.part`
   file that `_import` leaves behind when a write fails.
7. **4.15a5, `model edit`** (a lane with one commit): it still owes its
   review, the LOD-preview and edit-pass tests, and `--from booblord_high`
   reusing own_copy's places rule, or that call refuses (the 4.6r review's
   N2). Risk: clip import's 1e-4 tolerance.
8. **4.15a7, fit and docs** (the lane exists, no commit yet):
   `devkit models weapon-fit` (its `--write` owes the weapon goldens),
   `devkit/models/README.md` from Modkit's MODELS.md and TOOLS.md, the
   recipe-field reference in `docs/VARIANTS.md` from Modkit's PATCHES.md, and
   an AGENTS.md pointer.
9. **4.16a2, the skills** (the lane exists, no commit yet; D1083):
   azurik-change-control, -dev-environment, -testing and -orchestration,
   rewritten lean; patching-and-shims becomes an AGENTS.md subsection; and
   AGENTS.md's "skills and docs not ported yet" row changes.
10. **The deletion gate's coverage census** (G2, running): it maps every
    Modkit verb, leaf, script, folder, MCP tool, skill, role, CLAUDE.md rule,
    doc, test file and data file to an AzurKit path and its test, or to a D
    id. The rows it can't close in time are retired by name under D1171 and
    listed in 2.D.
11. **4.6r, booblord_high's own copy** (built and reviewed with no defect,
    not yet in the stack): rebase it onto the stack, re-run
    `scripts/record_shipped.py --content` on top of the stack's re-record
    with content v7, run the `[europe]` pin, then gate it. Modkit's full
    build of the copy, for comparison, must run before the delete. This
    closes 4.6p's gap: booblord_high's own copy refused.
12. **The content repo push** (4.6p, 4.6r): the published `main` is still
    v5. The clone's `p2/next-stack` holds v6, re-recorded (78 parts,
    100 MB). 4.6r's v7 (+16 MB) still sits on the older v6. Push whichever
    matches the landed stack (v7 rebuilt on the re-recorded v6 if 4.6r
    lands), and only once a site and app that read `content.later` are live:
    before that, v1.0.1's apps would fetch 99 MB of parts they don't read.
    Push by the Azurik-Modding-Hub URL, because the clone's `origin` still
    names the old archive.

## 2. The Modkit port and Modkit's deletion

D1168 runs the whole port now. D1171 deletes the local Modkit checkout this
session: it runs G11's checks inside this session, gives G12 again, and
retires by name the coverage rows that can't be ported in time (2.D). Order:
finish group 1's lanes, then A and B, then C, then the switch and the gates
(E), then the delete.

### A. Lanes not yet started

1. **4.15a8, ModelKit's re-point** (in the owner's ModelKit repo, under its
   rules): today 10-11 files and 63 `azurik_mod` references point at Modkit.
   Re-point the adapter, `kit_build.sh`, `kit_measure.sh`, the adapter test,
   the profiles, the docs and v4kit's code root at AzurKit's devkit. Rebuild
   booblord's base from AzurKit's `variants.json`, never P3. Reinstall the
   modelkit skill copy. The proof is one round (build, gate tier, sheet) on
   AzurKit's `main`. It waits for 4.15a1-a5 on `main`.
2. **4.13d1's parity bench and its x87 audit** have never run. It is one
   command, the bench's `go.sh`: about 9.6 CPU-h and 3 h of wall time, and it
   waits for the lock, the perf window and a load under 40. The bar: each
   stage's graph equals g3's kept graph edge for edge, recall reaches e7
   179/204 and a5 216/233, and at least 99.5 % of finds hold (D846). Any
   difference is a port bug until it is named.
3. **4.13e, the re-points** (the orchestrator's):
   - `$EV/tools/prune.py` still loads Modkit's l3_hold; point it at
     `devkit/sim/l3_hold.py`.
   - suite_rules' devkit rows (moot if suite_rules is retired, A4).
   - BRIEF annex A1, and the orchestration skill's reach-seat lines.
   - `docs/REACH.md` should list the open reach issues by id.
   - AGENTS.md's stale "Not ported: db-extract".
   - The src lines that name Modkit's scripts (the reach loader's and the
     proofs' re-measure lines, the planner's comments).
   - Then the ~11 GB of reach-engine records keyed to Modkit are dead
     (G4). They sit in the reach-engine cache, so prune them only once the
     owner says so (D1051).
4. **4.16b's flip** (the `$EV` tools learn AzurKit):
   - AZ_REPO's and `py`'s defaults change to AzurKit, after the ledger moves
     (A5).
   - AzurKit's `fullsuite` has no `--main` (the 1-in-5 run), no
     `--session-end`, no `--no-credit` and no main-red rule: wrap them in
     `$EV`.
   - Retire `fullsuite.py`, `suite_rules.py`, `suite_graph.py` and their
     `.before` copies with Modkit.
   - BRIEF annex X; BRIEF binds with AGENTS.md instead of CLAUDE.md.
   - Five `$EV` tools (BRIEF, `_azlib`, prune, landq, py) and the live
     workflow scripts still name Modkit's checkout.
   - 4.22's `$EV` half: land, landq and fullsuite's wrapper; the runbook
     reads "SHA is on main"; the orchestrator opens fix lanes from
     `flakes.jsonl` and `perf-debt.jsonl`.
5. **The private ledger** (D952): copy these beside PROGRAM.md before the
   flip: Modkit's issue ledger (29 open, listed below), its REORG_PLAN's open
   rows (A6), the closed and done archives, and Modkit's other plans
   (RANDOMIZER_PLAN, GUI_PLAN, HUB_MINING_PLAN, WEB_TOOL_PLAN, the commit
   map). Then make `ledger check` clean: D973, D976 and D1033 are each
   allocated twice, so annotate or renumber the second copies.
6. **REORG_PLAN rows to carry over** into the private plan:
   - The reach backlog: R1.23, R1.24, R1.25, TD.2, TD.2b, TD.5-TD.7,
     R2.19a-j, the improvement rounds, the all-level run and R2.16g. It was
     paused by D1048 and frozen by D1143, and it waits for v2 (D609) and the
     owner's reach budget (D977).
   - P7(b) and "0 logic bugs" for v1.1 (D522).
   - R1.26b: Live on Windows and Linux (ReadProcessMemory,
     process_vm_readv); it needs those machines.
   - 4.9's external tools (after v1, D31) and Level Studio's onboarding
     (D107).
   - §11.0's Q236 (ghidra-sync's variable renames) and Q77/V15 (Dependabot
     for `uv.lock`); V21 (the HDD cache) and V22 (a boot hang) carried as
     unresolved facts. The rest of §11.0 is closed as superseded.
7. **The randomizer's wish list** (RANDOMIZER_PLAN §7, R2.2-R2.15; D192,
   D194, D201, D208, D214, D216) exists only in Modkit. Move it to a
   `docs/Future` page or to the private plan before the delete.

Modkit's 29 open issues. Each moves to the private ledger or is closed by
name:

- Inherited by AzurKit:
  - AZ-009: level patches address entities by their current name, not their
    vanilla identity.
  - AZ-234: the D-pad field names in the struct header are swapped.
  - AZ-247: the index structs describe 20-byte records, but the loader
    strides 16-byte entries.
- Modkit only, closed as moot at the delete (D115):
  - AZ-274: a Windows CI leg hung at 99 %.
  - AZ-310: a child forked from a Tk-loaded xdist worker spun.
- Reach, derive and L3 (now in devkit; v2, D609):
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
- Models, named flaws under D801:
  - AZ-771, AZ-773, AZ-775 and AZ-776: clipping at big Bust, Hip and
    shape-slider sizes.

### B. Port leftovers lost with Modkit unless ported or retired

1. **test_level_graph's four tests and the fixture-DB planner tests** (the
   4.13b review): AZ-290 (the exit table), AZ-315 (the schema refuses the
   wrong release), X.102 (node types against a capstone scan), AZ-353 (world
   matrices against L2), D113's monotonicity on reachdb and escapedb,
   guardiandb's own tests, and the toydb loader and settings cases. Port
   them in one lean lane, or retire each by name.
2. **Two of test_player_jiggle's tests:** the 128 MiB weigh test (a dressed
   body against a default; 4.15a3) and the hair-catalogue test (4.15a2).
3. **AZ-300's shim-data test** (4.14a2): the shim data a build declares is
   the marker x3 writes each tick (the flicken and evil_noreht swaps). One
   test in the player-character tests.
4. **gen_node_types:** `node_types.json` ships, but nothing checks it
   against a capstone scan of either release. Add
   `devkit re node-types --check` with one vanilla test, or retire it with a
   D id.
5. **`doctor`:** its planned home, `bootstrap.py --check`, doesn't exist.
   Build it in a small lane, or retire it with a D id.
6. **`plugins list` and the external tools** (P68, Step 4.9) have no
   AzurKit home. Default (D115): defer them to an AzurKit 4.9 under D31 with
   a D id; community packs already come as data (4.3k).
7. **Rows to retire with a D id:** export_oracle (the oracle has been gone
   since 4.12), gui_use (the Tk GUI, D866) and gen_kernel_hdr (facts.kernel
   covers it). Modkit's `policy.yml` (protected paths) and `pins.yml` each
   need a written disposition. These were left out on purpose, and each
   becomes a row with its reason: the kernel-resolver stubs, roll_seed's
   process pool, AZURIK_NO_SHIMS and hand-written headers, pin_va, and
   `xbr edit`'s add-row, remove-row and grow-pool.
8. **Modkit-only docs that AzurKit cites** (about 100 lines): port
   XBR_FORMAT (after AZ-212's provenance read, since AzurKit is public),
   XBR_PACKS, SAVE_FORMAT and XEMU_ONLY, scrubbed. Rewrite or drop the cites
   of RANDOMIZER_PLAN, HUB_MINING_PLAN and `docs/RANDOMIZER.md#live` (in
   `link.py`).
9. **Modkit paths and names left in AzurKit's text:**
   - The game-reference skill and RE_XBE.md point at
     `docs/ghidra_snapshot.json`; it now lives in `devkit/re/data/`.
   - The RE docs and SHIMS.md cite Modkit's shim header.
   - About 250 lines cite `azurik-mod` commands that become devkit verbs.
   - src docstrings (jiggle_rt, the planner) and test fixtures' comments.
   - The reach port's alias cites in RANDOMIZER_DB.md.
   - OWNER_DEMO_WHO still reads "azurik-modkit" in `devkit/xemu/queue.py`;
     rename it on both sides.
   - AGENTS.md cites a tag, oracle-rando-6, that doesn't exist (C3).
10. **Checks that need Modkit, run before the delete:**
    - 4.6i's end-to-end build: Modkit's `patch` against
      `azurkit build --mods` on the USA image.
    - 4.6r's full build of the copy (1.11).
    - 4.6j's Modkit `randomize-full --plan`.
    - 4.13b's effect on the shipped database, and a 1,000-seed soak. After
      the delete this soak can only compare AzurKit with itself.
11. **The real Blender** (4.15a4): `python -m devkit models blender-check`
    has never run on Blender 5.2.2. Do one headless run under a caught
    SIGSEGV, so no crash dialog opens.
12. **The xemu fixtures default** (4.14a2): devkit's harness falls back to a
    `xemu-fixtures` link in the user data folder, and no bootstrap step makes
    it. Make the link (an environment change, with its revert), or set
    `AZURIK_XEMU_FIXTURES` in the brief.
13. **Stand-ins to record in the switch report** (D115):
    - 4.13d2's recheck of the 21 proof records ran on a stand-in; only a
      sitting per record (D108) brings their snapshots back.
    - 4.13a's record replay didn't run: all 1,337 snapshots are gone.
    - 8 levels of the frozen reach data stop at "no kept reach model's
      sample is the record's teleport".
14. **Smaller port notes** (no fix in the stack):
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
15. **A src import cycle** (4.13c, 4.13d1): importing
    `azurkit.tools.randomizer.levels` or `draft.geometry` first raises
    ImportError (geometry and art import each other). devkit's tests dodge
    it by their import order. Fix it with one test.

### C. Moves on this Mac before the delete

1. **G3, the images** (D953, D1002): both game images exist only in
   Modkit's `iso/`. Verify both, move them (not copy) to their own folder
   beside the checkouts, re-point the two user-data links, and verify again.
   Deleting Modkit first loses them.
2. **G6, memory** (D958, D1171): copy the memory folder to AzurKit's slug
   and rewrite its 37 files. Point the three `settings.local.json` pins
   (AzurKit, ModelKit, Modkit) at it, and keep the old folder. Show the
   owner the MEMORY.md diff in chat. The resume-pointer and repo-layout
   memories change with the switch.
3. **G8, tags:** create oracle-rando-6 at 8bfef0ca6 (AGENTS.md cites it)
   and modkit-final at Modkit's last commit, then push both.
4. **G9, residue:** copy Modkit's `.claude/settings.local.json` (with the 18
   hidden skills, Step 2.216) and its `.before-2.216` copy into `$EV`, and
   put the skill overrides into AzurKit's `settings.local.json`. Copy
   `.tools/ghidra-home` (Ghidra's user settings) too, if wanted.
5. **G7, outside readers:**
   - The harness's user config runs the ghidra MCP from Modkit's bridge.
     Re-register it at local scope from AzurKit; that needs 1.5.
   - ModelKit (A1), prune (A3), the `$EV` tools (A4), the fixtures default
     (B12), and the live workflow scripts.
   - Only comments may still name Modkit, in the pre-push hook and the shell
     profile.
6. **The xemu fork drive's discs** (D1051): its x68 states need their discs
   rebuilt before they're used. Four come from zips. The two fps120 states
   have no zip, and their commit 8959dcb2 is on no branch. Keep the zips
   and the README outside Modkit.

### D. Coverage rows retired under D1171

None yet. The census (1.10) adds each row it can't close in time. The open
rows known now: 1.6, 1.7, 1.8 and B1-B9.

### E. The switch (4.17), the gates and the delete

1. **4.17, the switch:** move the images (G3) and the memory (G6), set up
   the ghidra MCP and `.mcp.json` (G7), do 4.16b's flip, move the ledger,
   and bring in the 4.16a2 skills. CLAUDE.md's rules that have no AzurKit
   home move: R1 to the ghidra skill, R2 to the xemu skill, R4's environment
   list and R15 (pip.conf) to the brief, and R9's full runs to A4's wrapper.
   From then on, sessions start in AzurKit.
2. **The gates** (DEV-PORT-PLAN §8, as D1171 amends it):
   - G1, truth owned: a full receipt (vanilla and europe both at least 1)
     from a fresh AzurKit clone with no Modkit path, and CI green on Linux
     and Windows for the new devkit tests. xemu and ghidra opt out by
     marker, never by a skip.
   - G2, a coverage table with 0 open rows: 1.10, with 2.D.
   - G3, the images: C1.
   - G4, reach: the freeze is done. Still left: the stack lands
     (4.13c-d2), the bench (A2), and `prune --check` from AzurKit's hold
     (A3).
   - G5, tools and knowledge: with Modkit parked, these pass: py,
     `ledger next` and a clean `ledger check`, brief, load, keep,
     `prune --check`, waitfor, `land --queue` and wfcheck. Each role's
     first-use check passes in an AzurKit session, and every skill loads.
   - G6, memory: C2. G7, outside readers: C5. G8, history: C3. G9,
     residue: C4.
   - G10, what belongs outside Modkit is outside: done, except the two
     image links (C1).
   - G11, the parked session (D1171: inside this session): rename Modkit to
     its parked name. Then run from AzurKit: the whole suite on `main`, a
     smoke sitting, one Ghidra serve, the MCP tool list and one bench level.
     No log may show a Modkit path. To revert, rename it back.
   - G12, the owner's go: given (D1077; D1087 is met once the editor lands;
     D1171).
3. **The delete:** remove the one exact Modkit checkout path, never a glob:
   the `-fixtures` and `-lanes` folders share its prefix. Leave the
   fixtures, ghidra, ghidra-backups, `oracle-rz-*`, the evidence folder, the
   user data folder and the old memory folder alone. The reach store x7 is
   outside Modkit: its Modkit-keyed `routers/` and older-zoning models go
   with the delete, and its current-zoning models stay until A2's bench
   passes (D1171). The reach-engine cache stays until the owner says
   otherwise (D1051). Then report. The owner archives the private GitHub
   copy (D964).

## 3. Releases

1. **1.0.2** (D1159, D1088, D1134): it carries D1159's lanes (4.5o, 4.18a,
   4.18b, 4.19a, 4.19b, 4.20) plus 4.5w and the fixes for the two D1163
   flakes (4.1, 4.2). In the stack, all of these come before the Variants
   editor: the last commit before 4.6h was 61ff5b0a when this was written.
   - Default (D115, keeping D1159): split the landing there. Land the
     stack through that commit, add the 1.0.2 version commit and tag it
     (D1170 lets a tag go on any commit on `main`), then land the rest.
   - If the split costs another full gate, the other reading is to ship
     the whole stack as 1.1 once 1.4 holds, with no 1.0.2.
   - Steps: the version, then
     `scripts/devlog.py --release TITLE --remove`. Re-check the developer
     log's union merge after any rebase (the bump review). Run CI on four
     OSes (D1170: a test that passes its rerun is a flake). Then the
     runbook's scripts, the tag, the publish, and showing the notes (D1132).
     The security checklist is a quick look (D1162).
2. **1.1, the Variants editor** (D1144, D1159, D1167): 4.6a-q in the stack,
   plus 4.6r, 4.21's drop-downs and 4.22's tooling. It ships when green,
   with D1167 holding on the landed stack (1.4). D1088's "after round 5" is
   read as no gate (D115: D1144 and D1159 name 1.1's content). The content
   push (1.12) follows it.

## 4. Flaky tests and perf debt

D1170: a test that passes its one rerun is a logged flake and gets a fix
lane. A repeat, or a product failure, blocks. A perf op over its budget is a
debt row, and only a regression against the last release's receipt blocks;
memory peaks stay strict. Once the stack lands, 4.22's `flakes.jsonl` and
`perf-debt.jsonl` sit beside the receipts and hold these rows.

### Flakes, each owed a fix lane

1. `test_two_real_engine_workers_plan_a_seed_alike_and_a_change_drops_bs_plan_mid_way[webkit]`
   (D1163, a 1.0.2 lane).
2. `test_a_call_whose_page_webkit_ended_fails_at_once_naming_the_ending`
   (D1163, a 1.0.2 lane).
3. `test_randomizer.py::test_a_shaped_fills_attempts_at_once_follow_its_priority_and_a_cancel_stops_them_at_their_next_note`:
   it failed once in the stack's pure run with "DID NOT RAISE Gone", and
   passed alone and at 8 at once.
4. The site's Variants test in Chromium: the second page's view wasn't read
   within 120 s (the third 4.6c review).
5. The frozen app's page saves CPython's image `[firefox]`: the Windows
   frozen app's first load; not fixed (ci30's B).
6. Chromium site tests that failed only when slowed, with no error recorded
   (ci36; the 1.0.1 survey's 4.5h): save-hashes (367 s), images-rest-walked
   (130 s) and the seed built from the Randomizer tab (297 s). They need a
   slowed rerun that records the errors. Also unfinished: saving while the
   rest of the image is being hashed.
7. Pure-tier tests that failed only when slowed (ci27): test_hosts'
   collected-spot `[chromium]`, the track-this-seed bar `[firefox]`, the
   plan-file spoiler bar `[firefox]` (300 s), and the site's
   call-left-unanswered `[firefox]`.
8. Windows Firefox holds its first request for about 37 s (4.5l, 4.5w): the
   cause isn't shown, and DIRECT isn't shown to prevent the hold.
9. test_dev_tools' flake-stage test went red once beside 4.5d's CI run. Name
   it if it fails again.

### The watch list: name the cause the next time each one fails

10. arm64: the Europe golden `[webkit]`'s five failure modes; SIGBUS;
    WebKit's reload; the WebKit engine trap (ci44; D1126's recovery has
    landed); WebKit's JSC fault on macOS 15 (4.5p; a Playwright newer than
    1.64.1 is the lever, D1133); Firefox's timer that lost once, after which
    a lost edit still waits 600 s with no Data tab state in `hang()` (4.5g).
11. Intel: page-load stalls; ci19's extra 2 h; WebKit's drawing threads
    outranked (ci21).
12. Windows: ci34's cause; ci39's load failure; the Windows CI proof for
    the stack-only fixes (4.5w, the 4.6k review's F1, 4.13a's D1 and D2) on
    the stack's first CI run.
13. WebKit: network-process endings (ci41: a RequestedByNetworkProcess
    ending still costs 120 s); why WebKit leaves the page's process (ci18);
    what triggers the zero-headed message (4.5s: if it recurs, the site's
    character-seed test could use `_page.past_refusal`); ci31's Characters
    stall.
14. Others: ci17's three; what held ci27's GIL; ci37's CI ValueError;
    4.5m's second failure; 4.5n's frozen capped A32; S59 under 20 extra
    threads (4.4bf); WebKit's GPU threads on a 4-core runner; ps under
    `taskpolicy -b` taking 8-12 s while the efficiency cores are busy
    (ci36).

### Test-harness follow-ups

15. `_page`: `load` re-raises an Ended as a plain AssertionError, so an
    ending during a load gets no redo (4.5s, N1). An ending 1-2 s before
    the next call isn't named (N2). The redo keys on the reason alone (N3).
    `within` raises a crashed WebKit page's TargetClosedError without naming
    the cause (4.5p).
16. Silent waits:
    - `Site.__init__`'s new_context, add_init_script and route, and
      `_bare_page`'s new_page (ci14).
    - `_bare_page` callers' unbounded close (ci15).
    - 15 `page.goto` calls that keep Playwright's 30 s (ci16).
    - 372 unbounded evaluates (ci14).
    - 16-24 bare `page.goto(server.url)` calls in test_hosts (the 1.0.1
      survey's 4.5g).
    - App tests that fetch through an in-process server (37 uses, ci31).
17. AGENTS.md says a load of the site's page has `_page.STALL`, but
    test_site's two loads of a fresh page at ACT don't (4.5w).
18. The close-enough check on `icons.png` passes a red-blue swap of 6 of 59
    icons; it should judge tile by tile (ci8).
19. `tests/ci_durations.json` still names the old private-window test id.
    Refresh the shard table from a full run's log, with Apple Silicon and
    Intel times (4.5u, ci35).

### Perf debt

20. Saves over budget in fe61354's full runs, disk-bound on a full disk:
    - S06: WebKit 3.47 s, Chromium 4.15 s.
    - S49: WebKit 3.72 s, Chromium 4.46 s, lag 3.46 s.
    - S50: WebKit 3.24-3.49 s, Chromium 4.30 s, lag 3.63 s.
    - S72 in WebKit and capped froze 272 ms in the head start.
    - The goal is D1121's strict medians of 2.4 s or less (the 1.0.1
      survey's 4.5c). WebKit's writer has had no R2-a, and 4.4ci49 has no
      commit.
21. Firefox's Saves on their bar: S06 at 6.42-6.57 s, S49 and S50 at about
    6 s (r2c, round 5).
22. Round 5 never started (D1103): ROUND-5-PLAN's ten levers r5a-r5j, with
    r5a (the SND resampler) and r5c (the mesh kernels) first. Ops on the
    bar: A31 291 s, A60 201 s and S52 in Firefox 683 s (booblord reshaped
    for the first time: S52, S62, S63).
23. A71 and A80 were never read with perf.py on a busy box (ci56, ci57).
    A80's click past its plan is the build (about 1.7 CPU-s).
24. The fill (ci56, ci57):
    - A beside attempt's stop or priority takes effect only at its end.
    - The setup before attempt 0 is serial.
    - `fill.roll` (the GUI's first seed) still runs the twin.
    - A01 shows only its first stage honestly, and 75aa632 has no test of
      its own.
    - `fill.c`'s constants (MAX_REPAIRS and its kin) should come from the
      blob (a later pass).
25. The Characters tab's Reset: its info rows and list colours wait on the
    engine (0.24-1.08 s). Draw them from the held defaults (the 1.0.1
    survey's 4.5k).
26. `gc.freeze` of the kept Logic: measure gen-2 pauses first (the 1.0.1
    survey's 4.5j; ci27).
27. The Variants editor:
    - An edit's first Check is still nearly a full dress: a Scale x1.2
      edit takes 31.5 s in the app and an estimated 75-90 s on the site
      (round 6's kernels, low priority).
    - A texture or colour edit redoes both restyles and the LODs; a
      narrower key would bring it to about 15 s (4.6n).
    - No perf row times a Check after an edit; add one.
28. The site's Expert seeds: the costliest plan for about 3 s on Pyodide,
    and no site op times them (4.20).
29. Easy at Hard/Hard with the powers kept: more of its own attempts fail
    (0.74 s median, 1.68 s max native), and it does 5-9 % more fill work
    (4.20's Q1).
30. CI: about 60 SSH sessions per vanilla job, an unmeasured 1-2 min
    (4.5e). ci19's CI times were inferred, not measured.
31. The perf gate reads RSS, not footprint (4.4n's Q2, kept for 1.0.0).
    Revisit it with 5.33.

## 5. Product follow-ups and known flaws

### Known flaws (named under D835, listed until fixed)

1. **"WHITE cycles"** in the build's character log line and comments
   (4.18a): D1153 wants modern pad names (LB). Rewording moves the shipped
   plan answers' digests, so they need a re-record.
2. **Beamlord's notes show decision ids** to players (its `variant.json` in
   the content repo). Write plain notes in the next content version, as
   booblord's were (D1061).
3. **D1160 judged by key-item steps:** Easy's chain is still deeper than
   Normal's in 93 of 3,400 seeds (28 of 1,400 in the last round). Keying
   Easy's pick on steps first closes them (the third 4.20 review's Q3).
   Default (D115): a lane does this, since D1160 asks for every seed. With
   the powers kept, Easy is only 1-2 steps under Normal at the median.
4. **4.20's nits:** a plan Easy keeps from Normal records Normal's attempt
   number; the bar sits at "try 3 of 3" during `normal_plan`; the app runs
   `normal_plan` serially beside the pending attempts.
5. **The save warp and detours:** detours don't count save platforms as
   exits yet (4.20's DESIGN 1.3). 4.18b counts the warp only in D169's
   proof guard.
6. **The chain's drain hit** gives a light reaction where the game gives a
   heavy flinch.
7. **The Live tracker's 'loading' fix** (f07a354) has never been checked
   on a live xemu.
8. **Characters: a pause past REST** still starts a build that the next
   move drops (ci48; capped WebKit reached 6.50 GiB with an 8 s pause). The
   mechanism fix isn't done: a resting list's dropped heavy job should go on
   unkept.
9. **A stale first dress caught in a gap** takes the kill, and the next
   seed's click reads the logic again (45 s).
10. **Site builds without OPFS still copy twice.** Cut mode and S62's other
    mode are unproven.
11. **The arm64 WebKit engine trap:** `Error.stackTraceLimit = 0` in the
    engine worker's realm would turn the page crash into a RuntimeError that
    D1126's restart handles. A WebContent crash still takes the page with it
    (the 1.0.1 survey's 4.5a).
12. **Windows Firefox loses 6-15 GiB of temp disk** through the pack
    golden, and hangs for 60 minutes (D1105). Land a diagnostics-only
    commit first (the survey's 4.5d).
13. **`procpool._peak()` returns 0 on Windows,** so RETIRE and `room()`
    never act there. Read PeakWorkingSetSize through ctypes (the survey's
    4.5e).
14. **OPENERS:** the stale openers' compiled set leaks (in 4 of 10 trials),
    and no test asserts that what they compiled is kept for the drop.
15. **A Firefox Save whose `flat.mjs` fetch never answers stays greyed**
    (4.5u; accepted, since sw.js serves `flat.mjs` on the real site).
16. **A closed Firefox tab leaves its last build's ~835 MB file in OPFS**
    until the next load or a Clear (4.5q; accepted design).
17. **The site's Update fetches every file of an entry** before refusing an
    Update from another source; the app refuses first (ci52).
18. **The HTTPS content clone has no low-speed bound** (ci50).
19. **The Windows and Linux frozen apps are console builds:** `freeze.py`
    passes `--windowed` on macOS only (ci5).
20. **The app's own server answers over HTTP/1.0** (ci42).
21. **source_hashes** is checked against both releases' vanilla files
    (4.6i; accepted).
22. **A row's "main colour" can be a tinted near-black** (4.6e; Modkit's
    rule, accepted).
23. **The reach aim's string drifts in rare cases** (`docs/REACH.md`).

### The Variants editor (1.1)

24. Beamlord ships no Check part, so its first Check takes about 12-14 s
    native. Its parts could be recorded in a later content version
    (optional).
25. A first Check's 24.5 MB of parts download with no bar, and no pytest
    drives a real browser through a shipped fetch; S78 is the only proof.
26. The 4.6p review's minor points:
    - `worker.mjs`'s `fetched()` uses a synchronous XHR with no timeout;
      give it 60 s.
    - `shipped.part` marks a source down for 60 s on any OSError, even a
      404 for one part.
    - `sdk._later` lets `$AZURKIT_CONTENT_SOURCE` win over the entry's
      recorded source.
27. Old own copies of booblord_high (saved before 4.6r, or by Modkit) have
    no places and refuse. The stores hold reshape parts under old keys, so
    each misses once. Both are accepted (the editor isn't released yet).
28. Looks:
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
29. 4.6c's leftovers:
    - Undo is missing, and closing the app's window doesn't ask about
      unsaved edits.
    - The page sends `variants()` no manifest, so a built-in shows under
      Community only once it is installed.
    - `variant_save`'s `from` isn't checked as a name.
30. Community-only characters: `resolve()` has no third source, so
    installed recipes that aren't in `variants.json` don't resolve. Resolve
    them third, each held to its sha, and refuse a built-in's name (planned
    for after v1.0.0; it doesn't gate the delete).

### Data, mods and the randomizer

31. There's no page button for mod-template or entity diff; they are CLI
    only (4.6i's default).
32. `docs/RANDOMIZER_DB.md`'s TODOs: whether the page offers to drop a
    renamed skip toggle (4.10), the reserved keys `seed` and `[pools]`, and
    later share-string versions.

### Docs

33. AGENTS.md's perf paragraph:
    - Real Safari ends a closed tab's process in about 20-25 s, even with
      another tab open; only Playwright's WebKit keeps it (the 11-07
      real-Safari read; D1096 asked for the reason to be written there).
    - Its list of later visits misses S73.
    - Its stale lines still say the site's detailed dress may run out of
      wasm memory and that "4.4 waits until every site build fits 6 GiB";
      4.4 has shipped, and the capped site measures 5.16 GiB.

### Ideas the session ranked (after the port, D1131)

34. Support plumbing: About links to Issues and Releases, a "Copy details
    for a bug report" button, a "report it" link on D1126's restart notice,
    and an `$EV/tools/inbox` for D1075's read.
35. "Play it in xemu" help after a Save: Machine > Load Disc, and 128 MiB
    for big bodies.
36. Play and Attach have never met a real xemu or the real admin prompt
    (4.6k). Offer the owner a demo (D205) at the delete's report.
37. A headline randomizer mode and a speedrun kit (the session's idea
    ranking): D1144 made the editor 1.1's headline. When features open
    again, the open death realm (D201) comes first.

## 6. This Mac and infrastructure

1. **Disk:** 34 GiB free. ModMG's batches in `/private/tmp` are the
   owner's: never touch them (D1140). The orchestrator holds full runs
   until 60 GiB is free; that is its own guard against ModMG filling the
   disk mid-run, not a decision (D1150 starts a full run at any free disk).
2. **Ours to free after landing:** the lane worktrees still left (4.13d1,
   4.15a2, 4.15a5, 4.15a7, 4.16a2, 4.6r, next-stack, and the content
   worktrees 4.6p-content and 4.6r-content) and the 102 `p2/*` branches.
   Some branches are already stale: 4.3n-firefox-record,
   4.4n-sw-process, 4.4ci52-builtin-attempt and port-stack.
3. **Our `/tmp` leftovers:** the 4.6d measure seat's folder holds a
   registered detached worktree; `git worktree remove` it, then remove the
   folder. Also the 4.6e home folder and the 4.6f take log. An empty
   `/private/tmp/rp411` (11-06) has an unknown owner: leave it (D147).
4. **The reach store x7 (about 60 GB) and the reach-engine cache (about
   11 GB):** handle them as 2.E3 says (D1171, D1051). Before pruning, check
   that no running step names a snapshot.
5. **Six landed lane branches on the public AzurKit repo** (D1123's lane
   CI: 4.4ci36, ci37, ci39, ci41, 4.4dx5 and 4.5h): delete them.
6. **The content clone's `origin` names the Azurik-Testing archive:** push
   by the Azurik-Modding-Hub URL. Changing `origin` is a git config change,
   so leave it. The clone also has an untracked `scripts/__pycache__`.
7. **The game-data repo's environment allows `p2/*` branches** (D1123):
   keep that while lanes get CI. Its revert is in the handoff log.
8. **The `$EV` window tool:** `window take --max N` counts seconds, but
   seats read it as minutes, so tickets were dropped and runs overlapped a
   perf stage. A ticket taken from a foreground call lost its holder twice.
   Fix the tool, or name the unit.
9. **nativekit writes each library in place,** so a process that has the
   old macOS dylib loaded is killed. Write the new one beside it and rename
   (4.6c).
10. **Dev-speed levers** dx6 (changed-area gates leave the first-time
    reshape ops to the full run), dx7, and dx8 (the variant golden as one
    test per case), from the dev-speed survey.
11. **CI risks** (no work unless they recur):
    - setup-uv's own uv download sits outside the cache, so an outage can
      fail it, and the first run after a landing misses the cache on each
      OS (4.5t).
    - mcp brings in anyio, whose pytest plugin loads in every session
      (4.11f).
    - pypi.org:443 may no longer be needed in the harden-runner allow
      lists (ci55; low under D1162).
12. **Content size:** shipped parts carry the recording host's floats
    (D1016), so a swap change that moves a part needs a re-record. Each
    heavy built-in's own copy adds about 8.6 MB a release to the content
    repo.
13. **D1081:** revisit the Intel Mac app when GitHub retires its Intel Mac
    runners.

## 7. Owner decisions

None are open: nothing waits on the owner (D115, D1171). The owner may
overrule these defaults:

1. D1160 is judged by key-item steps (5.3).
2. 4.20's Q1: Easy's 5-9 % more fill work is kept (4.29).
3. 1.0.2 is split from 1.1 at the editor (3.1).
4. 4.9's plugins are deferred under D31 (2.B6).
5. ci57's defaults: no measure seat loads the Mac on purpose; cancels act
   at attempt granularity; `fill.roll` stays off the kernel; no
   sanitized-kernel check.
6. 4.13d2's stand-in is accepted (2.B13). The bench runs in the gaps, and
   its bar is equal graphs (the reach port plan's Q4 and Q5).

What only the owner does:

7. File the Chromium bug from its draft (D1111).
8. Post the Discord announcement (D1076, D1084).
9. The hub notes, only when the owner says (D134).
10. ModMG's disk use in `/private/tmp` (D1140).
11. See the MEMORY.md diff in chat (G6, D1171).
12. After the delete: archive Modkit's private GitHub repo (D964), and say
    whether to prune the caches (D1051).

## 8. Session end and the next session

1. **The handoff log** has nothing after 11-07 13:23. Add the 1.0.1 lanes
   (4.5n-4.5w), D1153-D1171's lanes, the port lanes, the stack, v1.0.1's
   publish (2026-11-09 01:33 UTC, from fe61354) and the delete.
2. **Memory:** add D1171 and the delete. The resume pointer still names
   session 4718988a. After the switch, the repo-layout memory changes too
   (2.C2 moves the folder).
3. **A next-session prompt:** the newest one is from 11-01.
4. **The brief:** its text reaches D1170, but its header still reads 11-07
   and f482ea041. Add D1171, then run `brief --redate`.
5. **The session's whole run on `main`** after the last landing. Until 2.A4,
   AzurKit's fullsuite has no `--main --no-credit` form. Modkit's own whole
   run isn't owed: its `main` hasn't moved since 11-01, and it goes.
6. Run `prune --session-end`, then `--apply` (D682), and the orphan sweep
   (`$EV/tools/orphans`).
7. Remove the lanes and branches after landing (6.2, 6.3, 6.5).
8. **At the next session's start:** D1075's read of new issues and PRs (0
   were open on both repos at this sweep). After the switch, sessions start
   in AzurKit.
