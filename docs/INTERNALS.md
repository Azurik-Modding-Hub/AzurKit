# AzurKit's internals: the design under AGENTS.md's rules

[`AGENTS.md`](../AGENTS.md) holds the rules that bind, short, so every session
loads them; this file holds the design each of its sections stands on, under
the same headings: what each part of the engine, the two hosts, the gate and
CI does, how, and why (the steps, decisions and measurements behind it). Read
the section here before changing that area. AGENTS.md's rules win where the
two differ, and a change to the design updates its section here. Moved from
AGENTS.md whole at Step 4.36, so its older lines name steps and cuts as they
were then.

## Setup and tests

```bash
uv run bootstrap.py                         # once, in the main checkout: uv sync --locked, the pre-push hook, Pyodide, the browsers
uv run --locked pytest -q <files>           # targeted tests while you work
uv run --locked pytest -n 8 --dist loadgroup   # the whole suite, on 8 workers (fullsuite.py's)
uv run --locked pytest -m "not vanilla"     # the pure tier: no game data
uv run --locked python scripts/freeze.py --dist DIR   # the app (D732): DIR/AzurKit.app on macOS (a PyInstaller onedir)
uv run --locked python -m shimkit [--check]           # the prebuilt shim objects, from their sources (zig, dev only)
uv run --locked python -m nativekit [--check]         # the compiled kernels' libraries, from native/*.c, and web/md5.wasm (zig, dev only)
uv run --locked python -m devkit [AREA [VERB ...]]    # the developer side (D950, dev only): devkit/README.md
uv run --locked python -m devkit doctor               # is this machine ready? one line a check (devkit/doctor/README.md)
uv run --locked python -m devkit.mcp                  # the azurik MCP server over stdio (.mcp.json launches it): docs/MCP.md
uv run --locked python scripts/record_goldens.py [--check] [GOLDEN ...]   # tests/goldens/ from the player's images
uv run --locked python scripts/record_shipped.py [--check] [--content CLONE]  # the swap's shipped answers (D995)
uv run --locked python scripts/gen_facts.py [--check]                     # the facts' XBE half from the images
uv run --locked python scripts/web_tables.py [--check]                    # web/tables.json: each release's table pages (the site's read ahead)
uv run --locked python scripts/slider_tiers.py [--check]                  # the movement sliders' tier table, from the physics (D1066)
uv run --locked python scripts/spot_needs.py [--check]                    # what reaching each spot needs, the tracker's spot tips
uv run --locked python scripts/ci_shards.py [LABEL=]LOG ...               # tests/ci_durations.json, CI's vanilla parts' seconds, from its logs
uv run --locked --group icon python assets/icon/render.py   # the icon, from its sources (macOS, dev only)
```

- Use `uv run --locked` for everything. Never a bare `pip`, `python` or
  `python3`. Python 3.14 only.
- **Tiers (D26):** a test that reads the USA image takes the `usa_iso` fixture
  (it becomes `vanilla`). One that reads Europe's takes `europe_iso` (`europe`
  and `vanilla`). Everything else is `pure`.
  - A run that selects a vanilla or europe test without that verified image
    stops, with one message. The only opt-outs are `-m "not vanilla"` and
    `-m "not europe"`.
  - A run prints `vanilla: N run` and `europe: M run`.
  - The images are found by `AZURKIT_ISO` and `AZURKIT_ISO_EUROPE`, else as
    `usa.iso` and `europe.iso` in the user data folder (`src/azurkit/core/gate.py`).
- **The web tier:** a test that runs under Pyodide on Node (the site's
  runtime) takes the `pyodide` fixture (`tests/_pyodide.py` runs the
  `azurkit` command from the wheel alone), and one that drives the page in
  a browser takes the `browser` fixture (`tests/test_site.py`), which runs
  it in Playwright's headless Chromium, again in its WebKit, Safari's
  engine (Step 4.1d3: Safari failed where Chromium passed), and again in its
  Firefox (D994), or only in those `--browsers` names
  (`--browsers=chromium`); either becomes `web`. A run that selects one
  needs Pyodide's pinned core, Node on PATH for the first and each of its
  browsers for the second, which `uv run
  bootstrap.py` puts in the main checkout's `.tools/` for every lane
  (`scripts/web_tools.py`; `PLAYWRIGHT_BROWSERS_PATH`, never the user's
  cache). Without one the run stops with one message naming it; the opt-out
  is `-m "not web"`. The summary prints `web: K run`.
  - Chromium's headless shell never fires `requestAnimationFrame` here, so
    Playwright's actionability waits hang and `wait_for_function` needs eval,
    which the page's CSP refuses: drive the page through the DOM
    (`element.click()`) and poll with `page.evaluate`.
  - Playwright's WebKit keeps OPFS (the site's build files) in the user's
    `~/Library/WebKit/org.webkit.Playwright` for every browser it launches,
    while each browser's Web Locks are its own: a persistent WebKit context
    gets a home of its own (`CFFIXED_USER_HOME`, as `test_site.Site` does),
    or another test's page load sweeps its held build files.
  - Playwright's WebKit screenshot appends `<style>body {}</style>` a moment
    (its animation sync), which the page's CSP refuses: the page keeps it in
    `azurkit.violations` as not its own (an inline style with no file of
    its origin behind it),
    so `_page.check_csp` after a WebKit screenshot fails. The status line
    says only the page's own refusals (`web/app.mjs`'s `refusal`).
  - WebKit refuses each `<select>` a script makes (its own inline style,
    CSP's `style-src-attr`, raised from the script's file), so the page's
    selects are parsed from `index.html`, the Variants view's Gameplay box
    and its Jiggle tab's bone box too (Steps 4.6c, 4.6d); their options may
    be made by script.
  - A page's files come from a server of a process of its own
    (`tests/_page.py`'s `Served`, `tests/_static.py`: `test_site.Site`, its
    bare page and `test_service_worker.Host`), never through the test's own
    interpreter, which a plan in a thread or a full collection of a heap a
    randomizer test left holds for seconds (on GitHub's Intel runner 98 s);
    only a request elsewhere, and a test's own routes, come back to it.
  - Each Firefox a test launches takes no proxy (`tests/conftest.py`'s
    `DIRECT`, `network.proxy.type` 0, under the launch's own prefs):
    Playwright keeps 127.0.0.1 in Firefox's proxy lookup, which on Windows
    asks WinINet before each request starts, and a page's first load there
    went unanswered past its 30 s with its request not yet sent.
  - Each Chromium a test or the perf gate launches runs its GPU in the
    browser's own process (`scripts/web_tools.py`'s `CHROMIUM`,
    `--in-process-gpu`; `tests/conftest.py` adds it to every launch):
    macOS's privacy checks (TCC) judge Chromium's GPU helper on its own, as
    the headless shell the checkout's `.tools/` holds in the protected
    Documents folder, and while macOS's prompt for another program of that
    name stood unanswered, every test Chromium whose GPU helper started
    inside it waited in that helper's own check, its pages stopped
    answering at their engine's start (no answer in 238 s), and nothing
    said why. On macOS a stalled call now names each privacy prompt that
    stood since it began (`tests/_page.py`'s `stalled`,
    `scripts/ci_resources.py`'s `privacy_asked`).
  - On Windows' CI each Firefox a test launches logs its requests, loads
    and hangs to files of its own in the runner's temporary folder
    (`tests/conftest.py`'s `FIREFOX_LOG`, Firefox's `MOZ_LOG`), and a
    stalled Firefox call prints the end of the newest ones
    (`tests/_page.py`'s `stalled`): Windows' Firefox held a page's first
    request about 37 s, its cause unshown.
  - Playwright's Firefox says a request as Firefox is about to send it,
    before the host hears it, so one a stall report hears late was late in
    Firefox, never held by the test's host. A load of the site's page (it
    starts its engine) has `_page.STALL` (`test_site.Site.open`,
    `test_service_worker.VISIT`): Windows' Firefox held one past 30 s.
  - A browser that stops answering (`tests/_page.py`'s `stalled`: a call
    left unanswered, and the browser answers nothing either) has its
    Playwright connection closed naming the call, so its try fails by name
    at once (D1072); the next test that takes its module's browser, the
    stalled test's rerun too, launches it again (`tests/conftest.py`'s
    `pytest_runtest_setup`), finished first as its module's end would, and
    its close ends what an ended parent left running while its driver runs.
- **Skips:** a skip or an xfail fails the run unless `tests/skip_allowlist.toml`
  lists it, and that list is empty. Failures never become skips: no new
  `skipif`, `SkipTest` or `xfail`, and no allow-list entry to get green.
- **Nothing small blocks (D1170):** every run, the gate's and CI's, reruns a
  failed test once at once (`tests/_rerun.py`). One that passes its rerun is
  flaky: the run passes, and the summary, the receipt (`flakes`), the flake
  ledger beside the receipts and CI's job summary name it with its first
  error (the summary with its lines whole), a lane to fix it; one that
  fails twice, or a product bug, blocks. Each flaky test's line is written
  as its rerun ends and each failed try's error lines as its report comes
  (`AZURKIT_FLAKES`' sibling, `.failed.jsonl`), so a run stopped before its
  end keeps them; a pytest a test runs writes neither file. CI's log
  prints each test that failed twice with its first try's error lines
  from that file (`python -m tests._rerun --first`): pytest shows only the
  second.
  A rerun is recorded, never hidden: it is no skip. Perf timings over budget
  are debt rows, not blocks (the perf gate, below).
- **When a truth goes red, suspect the code or the address first:** a
  golden, the facts or a drift guard that fails (the prologue
  guard in `tests/test_shims.py`, a site's vanilla sha256) means the port
  or the facts' address is wrong. Fix it there; never widen
  `PROLOGUE_FIRST_BYTES`, the skip list or any other allow-list to get green.
- **A suite hang that takes the network down: stop (AZ-312).** Workers stuck
  in `close()` or `sendto` while DNS or `curl -sI https://github.com` fails
  is an XNU TCP deadlock only a reboot clears: don't kill and retry or start
  another run; report it.
- **Parallel (D991):** the gate runs the suite on xdist's workers, so a test
  never leans on another's order or process; tests that share one costly
  build take one `xdist_group` (`tests/conftest.py` groups the frozen app's).
- **Lean tests:** the fewest tests that pin a behavior, each in a
  behavior-area file. A fix gets one behavior-named test, in the same commit.

## Game data (D961: the content repo's rules)

- Game files and game bytes may be committed (D961, as Modkit's D153 and
  Azurik-Custom-Content's D960): an XBE or XBR file, a clip, a texture, a
  save, a snippet, a byte literal, a disassembly listing. They belong to the
  game's rights holders and aren't under the MIT licence (`NOTICE.md`).
  - `.gitignore` still ignores `*.xbe`, `*.xbr`, saves and extracted trees
    against accidental bloat: add a game file on purpose with `git add -f`.
- Never commit the ISO/XISO image, whole or in parts that rebuild it, a
  private key, an EEPROM dump, the BIOS pair (the MCPX boot ROM and flash
  image) or a key file, an xemu HDD (qcow2) image or a guest RAM snapshot
  (`AZL3SNAP`): all but the first two can hold console keys.
  - `tests/_leak_guard.py` refuses them in the suite and on every push,
    also inside a gzip, tar or zip file. Its rules have no allow-list.
  - Never weaken them to get green.
- Saves keep no key: `tools/saves/sign.py` derives the console's signature
  key in memory from the player's own BIOS files, which are never kept, and
  holds only the certificate key's fingerprint. Its tests sign with a random
  key found by its own fingerprint, on slots and HDD images built in
  `tmp_path`.
- Never print game bytes in logs, commits or chat: print lengths and
  `sha256[:12]`. Failure output is redacted (`tests/_byte_safe.py`).
  - Read the game's code and constants with `python -m devkit re xbe`
    (`devkit/re/README.md`): `read` prints a value and `dis` and `fn` an
    instruction's text, never their bytes; its `hexdump` is a human's.
    Ghidra's side (`ghidra-query` on a serve's copy, `ghidra-sync`, the
    snapshot) follows the skill `azurik-ghidra-mcp`; the owner's Ghidra
    project is never opened headlessly or written while a Ghidra holds it.
- Recorded results are hashes and names, a convention and not a leak rule:
  the goldens and the facts hold sha256 and length, not
  raw vanilla spans.
- The images are read-only. A build writes to an explicit output that isn't
  its input.
- **The private game-data repo,** `Azurik-Modding-Hub/AzurKit-gamedata` (the
  images' parts, for CI only): never make it public, fork or mirror it. Only
  CI's vanilla job reads it (CI, below), with its read-only deploy key, the
  `gamedata` environment's secret, and the key is never in this repository.
- **Content is untrusted input (D992):** a manifest, a recipe or a picture a
  player is handed is refused by name, quickly and with little held, before
  anything reads it whole. A refusal names the entry, the file or the
  field, never bytes (`tests/test_characters.py`'s untrusted-content table).
  - `content.check` caps a manifest (1 MiB, 1,000 entries, 10,000 files;
    an entry's files and an Install 256 MiB) and walks its requires once.
    Each path is a content path whose suffix its folder takes
    (`content.SUFFIXES`: no `.html`, `.svg` or `.js`), with no `..`, `:`
    or Windows device name.
  - An Install checks each file as it lands, into `.part-<id>/`, and an
    Update removes only the content paths `installed.json` lists.
  - A recipe's file fields name files in its folder. A PNG inflates
    through `core/inflate.py` (at most 4096x4096, and one byte past its
    rows).
  - `web/` holds no HTML sink (`tests/test_contracts.py`).
- The Data tab's engine (`src/azurkit/tools/data/`) ships the vanilla
  config.xbr, both releases' file byte for byte (`tests/test_data.py` holds
  it to both manifests), and `schema.json`, Modkit's notes on its cells by
  the file's own names, so the tab works before an image is picked. A build
  still reads the image's own config.xbr.

## The goldens

- `tests/goldens/` is AzurKit's own truth for every family: the packs and
  the core (Step 4.12a), the characters (Step 4.12c) and the randomizer
  (Step 4.12b). It is what each case of `tests/goldens/cases.json` (its
  recipe, edited by hand) builds from the vanilla images, as names and
  sha256: G1 per pack (`packs.json`, `europe/packs.json`), each XBE pack
  case's bytes at the facts' sites (`sites.json`, `europe/sites.json`), the
  shim objects (G2, `shims.json`: the packs' and the swap's
  `player_model_<stem>.o`), the Game Data editor's cells
  (`xbr_editor.json`), whole builds (G3's packs and character cases
  `pipelines.json` and `europe/pipelines.json`, G4's `gui.json`), each XBR
  resource of every G3 build that dresses the player (`resources.json`),
  the character probes no G3 case builds (`probes.json`: a variant's mesh,
  paint and jiggle without Azurik-Custom-Content's files, a townsman's and
  the air elemental's own bodies, on both releases), the Characters
  tab's match-Garret values (`matches.json`) and the randomizer's: seed
  2's plan under the strict, default and max settings (`rando_plans.json`:
  each plan's attempt, sha256 and spoiler file's sha256, the default plan
  file whole), G3's seed cases (in `pipelines.json`, Europe's in its own)
  and the item tracker's verdicts on the default and max plans at five
  states, the spoiler off and on (`tracker.json`: each view's digest and
  that of the maps' model `web/mapview.mjs` draws of it, under `node`).
  - **Off the host they were recorded on (D1016):** macOS on Apple Silicon
    with numpy on Accelerate (`tests/_hosts.py`) compares every golden byte
    for byte. Another BLAS or libm rounds otherwise (booblord: a few hundred
    of 19 MB of `banm` floats, each at most 8 ULPs or 2e-12 near zero; a
    map: a few edge pixels), so on any other host a dress's `characters.xbr`
    and `fx.xbr` are compared close enough, with no reference per platform
    and no copy of their bytes: `close.json` holds, by sha256, each changed
    resource's sketch (only a clip's length and keys are floats, their
    weighed sums within 4 ULPs each; every other word of every resource is
    exact) and each file's digest with those
    resources blanked (`record_goldens.apart`), and the shipped pictures are
    their own reference (`tests/test_art.py`'s `_apart`: the icon sheet's
    pixels exact on every host, a map's within 1/200 and 1/8 of any 40 px
    box, Step 4.4ci9). Every other file
    stays exact there. The recording host is a platform, not a machine:
    every Apple Silicon Mac on Accelerate (CI's M1 on another macOS too) is
    held byte for byte, and Accelerate's BLAS adds in each chip's and
    release's own order, so no byte a golden or a shipped picture holds
    may come from a matrix product (`@`, `dot`, `tensordot`) where a tie
    can round either way: sum in integers, or as `art.draw.dot` does
    (Step 4.4ci8: the icon sheet's menu art). A shipped answer's bytes are
    the recording host's, so only what it stands on is held off it.
  - Only `scripts/record_goldens.py` writes them, from AzurKit's own builds
    on the player's images (`--check` writes nothing); never edit them by
    hand. It records the page's shipped pictures too, by family (`art`:
    The maps; `characters`: The Characters tab, below). A commit that changes one names each golden it changed and why,
    and a gameplay byte change to a default build is seen once in xemu.
  - The first recording is Modkit's last cut (the packs and the core:
    oracle-packs-4, Modkit 28d0b4110; the characters: oracle-models-3,
    Modkit 1648692; the randomizer: oracle-rando-6, Modkit 8bfef0ca6),
    which the recorder's first run wrote back unchanged but the files
    AzurKit couldn't build until Step 4.41b's moves recorded them (AZ-009:
    G3's `seed=0,all` left out `training_room.xbr`, `filelist.txt` and
    `ISO`, as the packs' three level-patched cases did); the randomizer's plans gained their spoiler's
    sha256, `tracker.json` was recorded equal to Modkit's own tracker's
    digests, and Modkit's `rando_iso.json` (the default plan's sha256 and
    its seed build's image, both pinned above) was left out.
  - The cases that wear booblord read her files in the content folder
    (`AZURKIT_CONTENT`, `azurkit content install booblord`); the builds
    that dress the player run in `--workers` processes.
  - A new pack adds its cases to `cases.json` (its defaults in `packs.json`,
    `sites.json` and, for an XBE pack, Europe's), then records them.

## Porting from Modkit

- **The port is done** (D1168, D1171): every Modkit capability AzurKit
  keeps is AzurKit's own, in `src/azurkit` (the player's) or `devkit/`
  (the developer's), held to AzurKit's tests and goldens, and Modkit's
  checkout is deleted. Its history (commits, the closed issue ledger,
  the retired docs, D955) is the private archived repository
  `Azurik-Testing/Azurik_Modkit` (D1030), read-only; no AzurKit file,
  test or tool reads it, and a fix is made here. The cuts below record
  where each part came from.
- **The randomizer's cut** (Step 4.12b): its database, planner, writer,
  physics, movement, layer and tracker, Live's game reads and link, and
  the maps' and icons' drawing, ported at oracle-rando-6, Modkit
  `8bfef0ca6` (the last sync), and AzurKit's own since, held to
  `tests/goldens/` and `tests/test_contracts.py`; Modkit's later
  randomizer commits to its freeze came by hand. Modkit's modules map to
  AzurKit's: `azurik_mod.randomizer.X` is `azurkit.tools.randomizer.X`;
  `live` and `live_link` are `live.game` and `live.link` (`LiveError`:
  `live.errors`); `sim.pages` and `sim.recipes` are `live.pages` and
  `live.recipes`; `assets.vanilla`'s regions are `live.regions`;
  `xbr.nodes` and `xbr.toc_scan` are `azurkit.core.xbr.nodes`; the other
  `xbr` modules and the two render scripts are `tools/randomizer/art/`
  (`maps.py`, `icons.py`); `draft.reach`'s `Reach` is `art/reach.py` (its
  first stage); `xbe_layout`, `resolve_va_to_file`, `listed` and
  `XisoReader` are `tools/randomizer/ports.py`; `planner.dbcache` is
  `tools/randomizer/dbcache.py`. Left out: the seed roll's pool
  (`fill.roll_seed`), layer's build objects (`check_args`, `write_layer`,
  `check_movement`, `movement_reasons`, `judge`, `outputs`,
  `write_outputs`), physics' `SOURCE_SHA256`, movement's slider ranges,
  the tracker's file reads (`placements`, `plan_doc`), live's `connect`,
  the L2 flights (`envelope.l2_*`, devkit's since Step 4.13a), the levels
  extractor (`extract`, `write_generated`, devkit's since Step 4.13b),
  `nodes.scan_types` (devkit's `re node-types`), and the drawing's command
  lines and PNG writers.
  The perf gate times the randomizer and tracker groups, and a change to
  the writer's or the layer's bytes owes an xemu sitting.
- **The simulator's cut (Step 4.13a):** `devkit/sim` is Modkit's
  `azurik_mod/sim` (L0-L3, the search, the trick explorer and `l3_hold`) and
  the envelope's L2 flights at Modkit `f482ea041` (the folder's last commit
  is `c3ecbff70`). Each module is Modkit's code with its imports pointed at
  AzurKit's engine through `devkit/sim/ports.py` (Modkit's XBE, kernel-thunk,
  pack and image calls on AzurKit's); the few rewrites (L0's XBR check, the
  overlay's and L2's packs, the kernel's exports in `devkit/sim/data`, L3's
  engine files, the hold's proofs path) are in its developer-log entry. The
  pool and FastL3 are the reach engine's (`devkit/reach`). Modkit is frozen:
  a later fix is AzurKit's own, held to `tests/test_simulator.py` and
  `tests/test_roll.py`.
- **The database tools' cut (Step 4.13b):** `devkit/rando` is Modkit's
  `rando db-extract` (`levels.extract`, `write_generated`), `rando check`,
  `rando_bench.py`, `rando_impact.py` and `rando_soak.py` at `f482ea041`,
  with `tests/rando`'s fixture databases in `devkit/rando/data`; the few
  rewrites (the soak's profiles and builds, four dark-area plans at Fire 1)
  are in its developer-log entry. A later fix is AzurKit's own, held to
  `tests/test_rando_db.py`.
- **The derive's and the authoring's cut (Step 4.13c):** `devkit/rando` is
  Modkit's `randomizer/draft` (the reach model, flights, gates, moves,
  sites, route, L3 goals, coverage, value ranker, pictures, export and
  authoring, with the 22 authoring specs and `blocker_families.toml`) and
  its `rando derive | author | check` verbs at Modkit `f482ea041`, on the
  shipped draft's envelope, floors, geometry and wiring;
  `devkit/rando/physics.py` restores the walk-off carry and the flights'
  certificates AzurKit's physics dropped. A change to the derive bumps
  `DERIVE_VERSION`; `python -m devkit rando restack` re-derives, re-authors,
  checks and re-records the randomizer's goldens, and
  `tests/test_reach_model.py` and `tests/test_movement_envelope.py` hold it.
- **The reach engine's cut (Step 4.13d1):** `devkit/reach` is Modkit's
  `reach_engine`, `reach_native` (the kernel and its launch backend),
  FastL3 with its C step and Unicorn patch, the L3 pool and the engine's
  scripts as devkit verbs, at Modkit `f482ea041`, frozen (D1143). Its cache
  and kernel keys hash the code at its devkit paths, so Modkit's records
  aren't reused; the truth set is read from `reach-truth/` in the user data
  folder and the reach models from the L3 store's `x7/reach/`, which
  this checkout built (`devkit/reach/models.py` refuses a pickle naming
  any other module, Step 4.13f); `tests/test_reach_engine.py` holds it and
  [`docs/REACH.md`](REACH.md) describes it.
- **The certification's cut (Step 4.13d2):** `devkit/reach`'s `l3-certify`,
  `l3-contact` and `l3-gate` and `devkit/xemu`'s `chain`, `route` and
  `minigames` are Modkit's `scripts/l3_certify.py`, `l3_contact.py`,
  `l3_gate.py`, `xemu_chain.py`, `xemu_route.py` and `xemu_minigames.py`
  at `f482ea041`, each its code with its imports renamed; the level's
  reach model is `devkit/reach/models.py`'s, the route graph's builder
  `devkit/rando/derive.py`'s, and its routers are kept in `routers/`
  beside the store's reach models. `tests/test_reach_model.py` and `tests/test_simulator.py` hold
  them, and the sitting kit's selftest the chain's rate and the pilot's
  pipe.
- **Coverage:** each cut ported Modkit's tests lean, merged into AzurKit's
  behaviour-area files (D10, D37); a later change to a ported module is
  held to those tests or names the golden that pins it.
- AzurKit never imports Modkit.
- **The facts** (`src/azurkit/core/facts.<release>.json`: each release's XBE
  sha256, its sections, every patch site's size and vanilla sha256, the
  game's functions a shim may call, the kernel exports' slots, the
  player-model swap's hooks (`swap`: the vanilla spans it writes and the
  addresses its shims call), Europe's address map). `scripts/gen_facts.py`
  writes their XBE half from the player's images (the XBE's sha256, size and
  header, the sections, each site's and each swap site's vanilla sha256,
  each kernel slot); a new site's address and size, a function, the swap's
  sites (address, size, what writes it) and refs and Europe's address map
  are edited by hand, then gen_facts fills in the rest (the swap's came from
  Modkit's facts until Step 4.12c). Run it after such an edit.
  `tests/test_packs.py` holds the files to it.

## Packs

- A pack (`src/azurkit/tools/mods/packs/`) holds only what it writes: each
  site a `PatchSpec` at a USA address (Europe's comes from the facts), its
  bytes, and the offsets of the absolute addresses (`abs32`) and rel32
  branches (`rel32`) in them. The facts give each site's size and the
  sha256 of its vanilla bytes. A value the pack scales is read from the
  vanilla XBE (`Xbe.read`), each release's own.
- A `custom_apply` writes only through `Xbe.patch`, inside the footprint it
  declares (AZ-097). Errors name the site, never its bytes (D35).
- **Sliders** (`ParametricPatch`) are a pack's parameters. Each takes any
  finite number, never clamped (D23). `slider_min` and `slider_max` are
  display hints, and the track holds the default and the vanilla value
  (D42). Only an encoding's limit refuses a value (`whole`, D45).
  - A slider at a site writes `encode(value)` there. A virtual one hands its
    value to `custom_apply`, which takes exactly the pack's sliders.
  - A config.xbr slider (`XbrParametricEdit`) writes a keyed cell: its
    value into one number cell, or as a multiplier of the cells its pack
    picks from the vanilla tables (nothing at its default). Where the game
    reads the cell as an int32, a value it can't hold once rounded or
    truncated is refused (D45). Its default writes what vanilla holds, so it
    is the vanilla value the page shows.
  - `mods.normalize` is every host's one check of a recipe's packs. Unknown
    packs and sliders, NaN and inf are refused by name. A value equal to its
    default is dropped.
- `Pack.requires` names the packs a build must apply with a pack
  (`qol_memory_upper64_gpu` places its runs in `qol_memory_upper64`'s heap):
  the sdk refuses a recipe without them, by name (`mods.missing`). A person's
  choice moves them, one rule with a line for each (`mods.settle`, the words
  ending in `Pack.requires_why`, D1061): `--pack` and the page's tick add what a
  pack needs, `--no-pack` (D588) and an untick take off what needs it, a mods
  file or link completes itself upward (`settled`, which the CLI prints and
  the page says), and only `--pack X --no-pack what-X-needs` stays refused; the
  page's `linked` walks the same rule, says it beside the group and shows
  each row's Needs. A body's limit follows the same ticks: a recipe with no
  `ram` takes the lines of what its XBE carries (`model_inspect.lines_ram`:
  12-14 MiB, 47.5-49.5 with both upper packs, 125-127 with
  `qol_memory_upper256` too); the bytes never depend on it. G1 builds each
  pack alone, so such a
  pack's case is its layer's image.
- **XBR** (`core/xbr/`): `Document` parses an archive's header, TOC and
  trailer, and config.xbr's keyed tables (`keyed.py`), and `dumps()` writes
  them back (every vanilla XBR round-trips, `tests/test_xbr.py`). An edit
  (`edits.py`) is the writes `[(offset, bytes)]` that make it, planned
  against the file as parsed; every cell is 16 bytes, so nothing grows.
- **The mods file** (Q268; `edits/preset.py`'s `read`, `sdk.read_mods`,
  `azurkit build --mods`) is a preset, an AzurKit build's manifest, a
  share link or one of Modkit's mod files (`edits/modkit.py`: its config
  cells, `xbr_edits` and `level_patches` moves as `xbr` operations, each
  checked against the vanilla config.xbr as it is read, `tools/data`'s
  `preview`; its retired registry.json names refused by
  `edits/modkit_retired.json`, a `level_patches` rename by itself). Its `mods` layer is the build's packs (in place of those on by
  default), and its `data` layer's `xbr` operations (`edits/xbr.py`) apply
  in order after the packs: `set` a config.xbr cell by the file's names
  (D51's spellings), type-checked; `replace_bytes` in an XBR file, where
  vanilla holds `expected` (hex up to 32 B, else `{sha256, size}`): read it
  from the image in a test, never write it; `move` a level's
  `critterGenerator`, by its id `g<G>/r<R>` or a critter name one vanilla
  generator holds, to `x, y, z`: its parent transform's translate (RE_DATA's
  "Where a placed item stands"), planned on the vanilla level, so the name
  is the vanilla one whatever the randomizer repoints (AZ-009); a seed
  with a move is unverified (`xbr.moved`, a `why_not`). A later operation or layer that
  rewrites an earlier group's bytes wins, and the conflict names both groups
  (D28; a cell's group names the cell, AZ-130).
- **A build's manifest** (`edits/manifest.py`): an image with a layer
  carries `/azurkit.json` and `/azurkit.bin` (a change's bytes past 32 B, by
  sha256) as new root entries (`iso.read(..., add=)`: the root table rebuilt
  in its sector, every vanilla entry at its sector, Modkit's layout, which
  V10 booted). `sdk.open_build` (`azurkit open`) checks every file of an
  image against them and gives back its mods file; a drifted file is refused
  by name. Without the root entries a build is Modkit's image byte for byte
  (`tests/test_builds.py`: G3's whole image; G3's packs cases and G4's file
  by file). A build with no layer is the vanilla image.
- **The sdk's surface** is its snapshot, `tests/sdk_api.txt`: change it only
  with `uv run --locked python scripts/sdk_api.py`, and read its diff.
- **Presets** (`edits/preset.py`, `sdk.preset_encode` and `preset_decode`)
  carry a recipe's packs and `set` operations as a link's `#p=` fragment:
  names, numbers and hashes only, never an image path or a byte (Q174),
  capped as untrusted input.
- **Community packs** (D988, `tools/mods/community.py`): an
  Azurik-Custom-Content entry of kind `pack` whose one file,
  `packs/<id>/pack.json`, is a mods file of a `mods` packs layer and a
  `data` xbr layer only: release-free (no `base` or `result`), data only (no
  randomizer, character, XBE site or code), its packs carrying every pack
  they need (`check`). `refusal` is the content folder's Install check of a
  pack entry, which every Install passes (`sdk.content_refusal`,
  `content.verify`'s `refusal=`; `tools.characters` may not import
  `tools.mods`). A recipe's `community` pins one by id and its pack.json's
  sha12 (`normalize`), and `resolve` takes it only installed, untouched
  since and at the pin, naming what to Install or Update. Its built-in packs
  `merge` with the recipe's own (a pack two sources set to other values is
  refused, naming both and the slider; equal copies are one; nothing is
  unticked) and plan as ordinary pack layers; its edits are a layer of
  their own (`layer`, `community <id>`) that `sdk._plan` lays after the packs
  and the character and before the player's own `data xbr`, so a later
  layer wins, reported (D28). A build's manifest records it by id, version
  and sha256, never its bytes, and `edits.preset.from_manifest` gives it
  back as the mods file's `community` layer, `{"packs": [{"id", "sha"}]}`,
  as a link carries it; a link naming one not installed at its pin is
  refused by name, and a remembered setup keeps its id alone (`sdk.restore`
  drops one that isn't installed, by name). `azurkit build --community ID`
  builds one. The Patches tab's group (`web/community.mjs`, on `web/content.mjs`)
  lists them with Install and Update, reads the source when first opened or
  when a link or the setup ticks one, and locks the rows a ticked one sets
  (`sdk.community`: what the content folder holds). Known flaw (D835): an
  `xbr` set on a cell the movement model reads leaves a seed's verdict
  unflagged, as the Data tab's does. No pack ships (D997), so no golden
  records one: fixture packs in `tests/test_community.py` pin them, its T3
  against the same recipe written out; `tests/_perf.py`'s A33-A36 and
  S26-S29 time the group on a fixture pack.
- **Shims** (Step 4.1f1): a `TrampolinePatch` hooks a site with a CALL or
  JMP rel32 into a C shim. A shim's source and its prebuilt object sit side
  by side in `src/azurkit/tools/mods/shims/` (`<name>.c`, `<name>.o`), both
  committed, so no host compiles one: neither the site nor the app needs
  zig (AZ-045).
  - The player-model swap's 40 shims are Modkit's sources, ported and
    AzurKit's own since Step 4.12c (`tools/characters/player_model/<stem>.c`), their objects
    beside them: shimkit's header types each game function they call as
    Modkit's header does (`TYPES`), writes the asm thunks for those that take
    an argument in a register (`THUNKS`) and an `azurik.h` for the
    parameter macros. Three objects hold zeros where Modkit's hold bytes a
    build writes back as it lands them (`ports.HELD`): garret4's roll motion
    (game data: `roll.c`'s table is zeros in the source, shimkit fills
    it from the USA image to compile, then zeroes it in the object, and each
    build reads it from the player's image), and four of Modkit's own
    constants in `drain.o` and `throw.o` whose bytes, beside their
    neighbours', meet a vanilla file's by chance for longer than the object
    rule took before D961 (a 16.0 default, the aim's sides and reach, 4.9;
    kept as D961's default); restored,
    each is G2's object (`tests/test_shims.py`, and `tests/test_characters.py`
    for roll's).
  - `uv run --locked python -m shimkit` builds every object with the pinned
    zig (`ziglang` 0.16.0, the dev group) and Modkit's flags: the same
    bytes on any machine, whose normalized sha256 is G2's record
    (`tests/goldens/shims.json`, the packs' and the swap's;
    `tests/test_shims.py` holds both). Rebuild after editing a source;
    `--check` writes nothing.
  - A shim includes only the headers shimkit writes from the facts at every
    compile (`--headers DIR` writes them out to read), or one of its own
    beside it in `shims/` (`qol_memory_heap.h`): `azurik_vanilla.h`, the
    facts' functions (each one's name, convention and argument bytes, as
    32-bit words or the C types shimkit's `TYPES` gives one a shim calls
    otherwise), the types and the active pad's record, and the parameter
    macros; and `azurik_kernel.h`, the facts' kernel exports (their
    ordinals; a variable as an import). Nothing vendored (GPL) reaches a
    shim (AZ-099, Q85). A typed prototype the facts' argument bytes don't
    match mangles to a name the layout refuses.
  - `core/coff.py` lays an object out: its sections where the carve
    allocator (`core/xbe.py`'s `Carver`) gives room, its DIR32 and REL32
    relocations resolved to its own symbols and the facts' functions. The
    allocator places a shim in `.text`'s gap (USA: 16 bytes before BINK),
    else in `SHIMS`, a section appended past the last (Europe: always),
    past every claim of the layers before it. Each placement is a `Claim`
    of its layer, kept in the manifest; the header state claims derive
    (`.text`'s sizes, the appended section) is laid down by `compose`,
    never written by a layer.
  - A shim's kernel function lands as a 6-byte stub that jumps through the
    game's thunk slot for it (one a pack), a kernel variable is read
    through its slot. A function the game doesn't import (no slot: add it
    to `scripts/gen_facts.py`'s `KERNEL` with its ordinal, convention and
    argument bytes, then run it) lands a 37-byte stub of its own, writable
    for the cache it keeps, that asks the committed `xboxkrnl_resolver`
    (landed once a pack) for its address on the first call (Modkit's
    D1-extend, `engine.resolving_stub`, Step 4.24c); a variable with no
    slot is refused by name.
  - Each hook lands its own copy of its shim. A `TrampolinePatch`'s
    `floats` (`FloatParam`: a slider's value) and `tables` (`BytesParam`:
    bytes the pack makes) are written into that copy's `.rdata` at their
    symbols; a value past float32's range is written as the infinity it
    saturates to, with a note in the build's report (Q110).
  - A `custom_apply` may carve bytes of its own (`Xbe.carve`: a float a
    rewritten load reads, a hand-written shim with its data), hook a site
    to them (`Hook`) and write a span its footprint declares with a size
    (`Place(size=)`), which the facts may cover only in part (the facts'
    sites are where Modkit's cases changed bytes).
  - A new shim pack starts with `python -m devkit re new-shim NAME --hook
    VA`, then `plan-trampoline`, `shim-inspect`, `test-for-va` and
    `region-map` (`devkit/re/README.md`, Step 4.11e).
- A slider at a site of the XBE has no vanilla value in the catalog (the
  wheel holds no game constant, Q174): `sdk.vanilla` reads it from the
  player's image, and the page shows it once the image is picked (D42).
- A pack is done when its cases match their goldens: the facts' sites site
  by site, then G1 per file on both releases (`tests/test_packs.py`;
  `tests/_g1.py` reads G1, whose Europe half has no case for a
  config.xbr-only pack: the file is the same in both releases, so its USA
  cases stand for it).

### Patching and shims: what binds

Modkit's `azurik-patching-and-shims` skill, cut to the rules that still
bind (Step 4.16a2); the how-to (a hook's anatomy, calling the engine, the
kernel imports, per-apply floats, hand-assembled shims, pitfalls) is
[`docs/SHIMS.md`](SHIMS.md), rewritten for AzurKit's engine (its
header says what of Modkit's isn't AzurKit's). The packs, sliders and shims above are the
model; the swap's shims (`src/azurkit/tools/characters/player_model/`)
are the Characters section's.

- **Pentium III code only (AZ-021):** the Xbox's CPU has MMX and SSE, no
  SSE2. shimkit compiles with zig at `-mcpu=pentium3` (Modkit's flags),
  so `double` maths lowers to x87 and `float` may use scalar SSE; xemu
  runs SSE2 code anyway and only real hardware faults on it. Check an
  object: `objdump -d <object>.o | grep -E 'sd[[:space:]]|cvt[a-z]*sd'`
  prints nothing; L1 (`devkit/sim/l1.py`) refuses any instruction a
  Pentium III lacks and a misaligned m128 in patched code.
- **Keep the callee's contract:** a hook that replaces a CALL keeps the
  callee's `ret N` and return registers (a NOP'd stdcall CALL once gave a
  black screen). A game function a shim calls is a facts `functions`
  entry (its VA, convention and argument bytes), confirmed at the callee's
  `RET N` (stdcall and thiscall) or its callers' `ADD ESP,N` (cdecl) at two
  or more call sites, cited as VA + N in the commit body; an argument in
  EAX, ESI or EDI needs shimkit's thunk (`THUNKS`), and register inputs
  are checked by eye at the call sites. A new site, hook or function owes
  Europe's address or a named absence in `facts.europe.json`. The prologue
  guard (`tests/test_shims.py`) failing means a mid-function VA: fix the
  VA, never `PROLOGUE_FIRST_BYTES`.
- **A config.xbr cell is edited only once the engine is shown to consume
  it** for what the edit wants: garret4's `hitPoints` is loaded but unused
  by the player (`player_max_hp` writes `settings_foo`), `runSpeed` is the
  live walk base while `walkSpeed` is the walk-to-run threshold, and the
  old "dead armor table" is `attacks_anims` (`azurik-game-reference`).
- **A patch is done when its behavior is seen, not its bytes:** Modkit
  catalogued 14 patches whose bytes landed with no effect in game
  (`azurik-game-reference`). A gameplay change is done once (1) the facts
  hold its sites and the goldens its cases (G1 and `sites.json`; G2 for a
  shim's object; a pack owes no byte test of its own); (2) it is seen once
  in xemu, built from vanilla with only it, under conditions that reach
  its code, one sitting per stack (`azurik-xemu-oracle`), a movement
  slider also in L2 at the value the game consumes
  (`tests/test_simulator.py`); (3) its outcome is written in its
  subsystem's RE doc (`docs/RE_MOVEMENT.md`, `docs/RE_DATA.md`,
  `docs/RE_XBE.md`), or the doc says it is unverified, or the pack goes.
- **The HDD cache:** the game plays its cached copy of a prefetch-listed
  file until that file's `filelist.txt` line (md5, size) changes; every
  build writes through `core/iso.py`, which rewrites the line, and a new
  build path must too.

## The randomizer

- **The planner** (Step 4.2a; `src/azurkit/tools/randomizer/`): `plan(recipe)`
  fills the database's authored levels for a seed (any string) under the
  database's default settings (D144), a settings file's table (`settings`)
  or a share string (`share`; its movement sliders, AZ-383, pick the tier
  it is filled at, below), and returns Modkit's plan file's object;
  `spoiler(doc)` reads one back. The sdk's `plan` and `spoiler` and the CLI's
  `azurkit plan` and `azurkit spoiler` call them. A plan needs no image.
  - **Movement sliders** (D1064, D1066; `movement.py`): the logic is the
    level files' as authored, and no slider re-checks it. Moved movement
    sliders pick the tier the seed is filled at (`movement.played`): the
    one whose reach is nearest the asked tier's times their travel factor
    k, read from `data/slider_tiers.json` (each modelled slider's k at its
    points, from the physics; `scripts/slider_tiers.py [--check]` writes
    it, a test holds a point of each row to the physics), on the line
    between its points, multiplied; so the plan is that tier's seed, the
    same on every host, never refused, its file keeping the share string
    as given (`plan_doc`'s `asked`; `Plan.asked`, `Plan.settings` the
    tier's). The roll, climb and swim feed no tier. A seed with any
    gameplay slider moved isn't promised beatable: the spoiler's line, the
    tab's and a build's first `why_not` say so, and its `logic_verified`
    is false; true means every slider at its default and the plan
    verified, with no later layer over it.
  - `planner/`, `data/`, `writer.py`, `physics.py`, `movement.py`,
    `layer.py`, `tracker.py` and `live/`'s `game.py`, `link.py`, `pages.py`
    and `recipes.py` were ported from Modkit at the cut (Porting from
    Modkit, above), AzurKit's own since; `generator.py`, `tracking.py`,
    `ports.py`, `dbcache.py` (no cache on disk: a pickle read back from a
    folder the program writes runs its code) and `live/`'s `errors.py` and
    `regions.py` were written here.
  - **The shipped database** (Step 4.3g): the wheel (`web_tools.wheel`) and
    the frozen app (`scripts/freeze.py`) carry the checked database, its
    Logic's tables and its memos' types as `shipped/<key>.pickle` beside
    `dbcache.py`, written at their build by `web_tools.ship_database`
    (`dbcache.ship` in a child Python under `PYTHONHASHSEED=0`, never
    `python -I`, which ignores it, so a build gives the same bytes; the
    database's `root` dropped, so it holds no path of the checkout). It is
    generated, never in the tree. `dbcache.load` serves it for the key it
    was made for (`dbcache.entry`: the data's and the planner's files; the
    frozen app's, whose planner is in its archive, the data's alone), and
    reads it only from the wheel (its RECORD lists it) or the frozen app: a
    checkout checks the database (about 4 s). `dbcache.shipped_logic`, the
    loader's `SHIPPED` hook (the package sets it), hands `kept_logic` the
    Logic as built, a fresh one each call, so neither checks nor builds;
    what it reads is frozen out of the cycle collector's walks (`gc.freeze`:
    its million objects' full walks held the app's server 0.8 s). The file
    holds the database's skip table first (`{id: skip}`, about 14 KB), then
    the database (Step 4.4bd): `dbcache.shipped_skips` reads the table
    alone, so a page's remembered randomizer (`randomizer.remembered`, a
    launch's restore and `api/setup`) is checked without reading the logic,
    and a file of the other layout fails by name. The logic itself is read
    as a counted stream, a note each twentieth ("reading its logic, k of
    20"), which `sdk.randomizer_settings` passes on only when counted, so
    the Randomizer tab's first ask moves a bar and a later one shows none.
    `kept_logic` reads or builds one at a time (a caller meanwhile waits and
    is served it), and the app's server reads it ahead from its start on
    D1008's intent (`app._logic_ahead`; a shipped one only), the site's
    engine in a restore that brings Randomize back on, before the page is
    ready (`web/worker.mjs`), so the tab's ask or the tracker's view after
    a launch or a reopen finds it read.
  - The engine's progress notes are one stream (Step 4.3 train B3):
    `core.progress.note(text)` from the fill ("placing the items", then
    "placing the items, k of n", k the item it is placing of the n steps
    an attempt takes, each item a reach places a step and the rest, placed
    at once, its last, so the count moves as the reaches' time goes; each
    percent and at each reach), the logic's checks as
    a checkout reads it cold ("checking the levels, 5 of 15", then
    "building its logic"), the shipped logic's read ("reading its logic, k
    of 20") and the tracker's exits ("the maps' exits, k of
    22"). `core.progress.noting`, the calling thread's (`randomizer.plan`,
    `sdk.image`, `sdk.tracker`, `sdk.spoiler`, `sdk.randomizer_logic`,
    `sdk.randomizer_settings`),
    folds each into the stage the call reported last: its label and the
    note, a "k of n" note counted inside that stage's step (the tracker's
    world map, 50 % to 100 %; a plan's fill, 33 % to 66 %), and a note
    short of the furthest one told in that stage keeps that one's count,
    so a bar never goes back. Each note is a cancel point (a host's
    callback raises through it). The fill's count is one through its
    attempts: an attempt after a stuck one tells the count the stuck one
    reached until it passes it (Step 4.3 train B2). The app's engine reads
    the logic ahead with `sdk.randomizer_logic`, and a call waiting on
    that shows its records (`engine._WARMING`, the warm-up counted on a
    seed plan's scale, its first of 3 steps; Step 4.7c).
  - A fill of the same Logic, database, seed and settings digest another
    thread is making is waited on (Step 4.3u), the waiter telling its count
    every `fill.WAIT` s, and copied when it ends; one cancelled or refused
    is made again by its waiter. The engine holds no threads: the fills in
    flight are a dict whose `setdefault` is atomic, the waiter sleeps
    between looks.
  - The fill runs in the caller's thread: Modkit's seed roll in a process
    pool (`roll_seed`) isn't ported.
  - **Seed difficulty** (D1157, amending D1031, D1037, D1039;
    `planner/difficulty.py`, `planner/fill.py`, `native/fill.c`):
    `Settings.seed_difficulty` is 0 Normal (the default: it enters none of
    what follows, its plans, files and strings are today's byte for byte), 1
    Easy, 2 Hard or 3 Expert, each offered at any settings. A settings file
    and the tab's table name it (`"Easy"`, `"Hard"`, `"Expert"`) only above
    Normal, and the plan's `settings` then also holds `seed_difficulty_fill`
    (`settings.SEED_DIFFICULTY_FILL`, 2), as does share version 4's last
    byte (`fill << 3 | level`); another fill is refused by name, except
    v1.0.0's (fill 1, a file's or plan's integer: 2 Standard, 3 Hard, 4
    Frame-perfect), which loads at the nearest level now
    (`settings.OLDER_LEVELS`: Hard, Expert, Expert), the tab's `note`
    saying so. Three integer measures, no clock: a spot's *round* (the
    progression reach's, dense-ranked), its *rungs missed* (E_top .. E_2 of
    the ladder, `difficulty.ladder`, at that point of the fill: a spot behind
    an allowed trick is a hard one, so tricks follow from placement, with no
    forcing of their own) and its *detour* (`difficulty.detours`, on its
    level's node graph: 0 on a shortest way through, twice a side room's
    depth; `OFF_PATH` 2 or more is off the path). In the progression pass
    each key item takes a spot by its attempt's lean (`difficulty.lean_mode`:
    Easy the lowest (missed, round + detour), Hard weighted w * w + 1, Expert
    the highest w, w = 4 * missed + round + min(detour, 6); strict below
    `STRICT` (10), then weighted, and a level's 20 attempts past `LEANED`
    draw as today, as a strict lean repeats one placement the verify may
    refuse every time); the obsidians by detour (D1038). With the elemental
    powers kept vanilla, a realm's last fragment can open it before the kept
    power that gets the player back out (new trick-free traps), with no key
    item after them to swap. In every attempt of a level, and in Normal's
    past its first 20 (`fill._Run.past_at`: Normal has 20 more, so its plans
    stay today's and a seed whose 20 all met that gate plans too), the trap
    gate's repair then moves the realm's opener to a free spot from the kept
    power's sphere on (`_Slots.repairs`' `past`, `fill.c`'s `A_PAST` and
    `P_REPAIR_PAST`). In an Easy attempt the key items collected just
    before the traps free are no way out when the traps free without them
    all (beside the kept power, swapped, one would open its own realm early
    again), and where one way-in item alone opens the traps the repair
    takes the earliest and closest spot first (no rung missing it, a sphere
    that already collects a key item, then its sphere + min(detour, 6);
    `fill._earliest`, `P_REPAIR_EARLIEST`). Easy keeps the lowest
    `Judge.score` (key-item steps + key items off the path + twice the
    step-ups at each rating to the top) of 3 passing attempts and, last,
    Normal's own plan for the seed (`fill._Run.normal_plan`: Normal's
    attempts on the Easy run's caches), so Normal's is kept only where it
    scores below all 3 and no Easy plan scores above Normal's; Expert the
    highest of 6, the first on a tie; Hard and Normal their first. The
    kernel (`fill.c`'s `lean`, the
    call's `A_LEAN` and `A_PAST`, each location's `L_DETOUR`) and its twin
    (`fill._Lean` in `_Slots.attempt`) agree bit for bit
    (`tests/test_native.py`'s spread). Attempt k is pure, so a host may
    run those past the first at once (`fill.WIDTH` on its `fill.BESIDE`):
    the app's engine on its threads (`procpool.Beside`), the site's worker
    one at a time: the same plan at any width. Every plan's spoiler and
    tracker show one measured line (`difficulty.profile`, `line`): "Hard: 19
    key-item steps, 17 off the path, needs Roll jumps twice", the tricks
    (play_2's step-ups' openers, `difficulty.openers`, in `TRICK_NAMES`'
    short words) named only with the spoiler shown, else "needs tricks at N
    points", left out when no trick is allowed. A spoiler's openers read one
    switchable option set a tier (`Logic.reach`'s `off`), and the app's
    engine works them out ahead, low, after a plan above Normal
    (`randomizer.openers_ahead`, `engine._openers_ahead`); a View or the
    tracker's Spoiler waits on nothing and works out what isn't kept yet.
    Any change that gives the same inputs another level > 0 placement (the
    leans, the schedule, the bounds, the score, the measures) bumps
    `SEED_DIFFICULTY_FILL` and leaves `GENERATOR` alone. No movement data
    rates plain platforming, so with no trick allowed the levels differ by
    chain and off the path alone. `tests/test_randomizer.py` pins the levels'
    order, plans, strings and files; `tests/_perf.py`'s A70-A80 time the
    costliest settings, each on the seed of "0".."99" whose fill takes the
    most reaches there.
- **The generator layer** (Step 4.2b; `generator.py`): a build recipe's
  `randomizer` (the planner's recipe and an `obsidian_cost`; `azurkit build
  --seed`) is planned at the tier the build's movement sliders pick
  (`layer.plan_for`, above) and written as the build's first layer, before the packs
  (Modkit's `mod_apply` order): one group a node graph (its new strings,
  TOC size and repointed name fields land whole), one for the obsidian
  locks, and one a species for the contained touches (`contained`, AZ-834:
  a species the image holds once, on a spot a container encloses, whose
  pickup reaches further than the vanilla item's there takes that item's
  `collisionRadius` and `collisionAspectRatio` in config.xbr, so it is
  taken only once the container opens; one held more than once keeps its
  own), and one a row for an own row (`own_rows`, AZ-835: `writer.OWN_ROW`'s
  spot, a1's frag_air_1, names a spare pickup row made its item with the
  vanilla item's reach; the fill counts the plan's name, so no plan moves).
  `edits.manifest.image`'s `judge` reads the image back against the
  plan before anything is written: a difference a later layer explains (it
  wrote the location's fields or string or a touch's or own row's cells, or
  dropped its group) is a conflict and `logic_verified` false (D28), any other fails
  the build by location (D35). The movement check reads the packs' catalog (a
  gameplay slider moved, D1064, then each slider's `logic_floor`, D83(c));
  the tools never import each other. The
  report's `randomizer` and the manifest's `verdicts` carry the verdict, and
  a randomized build's mods file replays its seed and share string.
  - Not ported: Modkit's `db-extract` (`levels.py`, the generated data's
    extractor: the data comes by a port), the player-model swap's
    movement reasons (with the models, Step 4.3) and the slider tracks'
    safe ranges.
  - `tests/test_randomizer.py` holds it to its goldens: `rando_plans.json`
    (seed 2's attempt, plan sha256 and spoiler under the strict, default
    and max settings, and the default plan file byte for byte, on CPython
    and under Pyodide, the same in two processes under two hash seeds) and
    G3's seed cases file by file and whole image on both releases.
- **The tracker** (Step 4.2c2, D189, D249; `tracking.py`, `sdk.tracker`):
  Modkit's `Tracker` on a plan file's object (a randomized build's report
  carries its plan, `plan`), the marks the page keeps (Modkit's state:
  `collected`, `live`, `veto`, `slot`, `gems`) and, with Live on, the element
  levels the game holds (`kit`, R1.41): the marks after a `toggle` or a
  `reset`, the head line (with a seed difficulty above Normal its level, and
  at every level `head.difficulty`: the measured line, its counts and, only
  with `spoiler`, each step-up's tricks by name; the profile once a plan on
  the tracker's Logic, `tracker.json`'s digest excludes it; the page's line
  under the head), the counter row, each spot's state (`got`,
  `live`, `near`, `skip`: only with a skip, R1.41, `far`) and its item
  only once collected or with `spoiler`, and the Table's two trees; with
  `gems` (Step 4.2c3, R1.43, D928), each gem spot's gems (a cluster's
  yield), how many Live saw taken and its gem, each level's counts and the
  Table's Gems rows. The process keeps the last few trackers, so a click
  costs one reach. `tests/test_randomizer.py` holds its verdicts to
  `tracker.json` on seed 2's default and max plans at five states (none marked,
  three rounds of marking what is reachable, every power, Live's kit at 3,
  and Gems on with gem takes), first recorded equal to Modkit's own `Tracker`'s.
  - **What its maps draw** (Step 4.2c3): `tracking.world()`'s `maps`
    (`needs.py`, Modkit's map view's needs: each exit's ring colour by
    what using it needs, dashed one way, each barrier's, key lock's, disc
    seal's, save point's and teleporter pad's name and need, the world
    map's lines), and its `art`: the parts the pictures are drawn in and
    their `ART_VERSION`, a host's key for what it keeps.
  - **The pictures** (`art/`, Step 4.2c3): `sdk.art(iso, part)` draws
    one part from the player's image, each file it reads checked against
    its release's vanilla file (`art.Vanilla`): the icon sheet
    (`art/icons.py`: the game's 2D menu art, interface.xbr's status screen,
    for the fragments, gems, obsidian, placed keys and element orbs; its
    model at 40 px for the rest; the smash wall our drawing), or a level's floors seen
    from above, its `maps.json` entry (where its exits, items, spots,
    barriers, features and gems lie, in pixels with their floor; `frame`
    maps metres to them; an item's, a spot's and a gem's floor is the one
    holding the most ground at its height round it, `maps.Rooms`, Step 4.3's
    floors), its `floors.json` table (each pixel's storeys and their
    floors by the same rule: Live's Follow reads the floor under the
    player there) and its world-map thumbnail; `sdk.art_world`
    makes the world map and the index from the levels' parts. Modkit's
    scripts draw them (ported), on the reach model's first
    stage (`art/reach.py`, ours: Modkit's `Reach(level, flights=False)` up
    to the logic floors). `tests/test_art.py` holds every picture and the
    index to the drawing from the USA image (Modkit's committed pictures at the cut),
    and the icons and a level from Europe's (its level, character and
    effect files are USA's); it holds `ART_VERSION` to the digest of the
    drawing's sources, so a port that changes them changes the key.
  - **Live** (`live/`, the app's alone, D882): `game.py`'s reads of a
    running game and its events (Took, Level, Held, Reload), `link.py`'s
    link to xemu (the fork's shared guest RAM, or QMP; never a gdbstub,
    D257), `pages.py` and `recipes.py` (the guest's page tables and RAM
    layout); `regions.py` gives each release's addresses from the facts
    (`facts.<release>.json`'s `xbe.thunks`, the kernel thunk table's, tells
    the release a running xemu booted). The tracker imports only the
    events, so the site never loads the link.

## Characters

- **The swap** (Step 4.3a2) is Modkit's, which the models family's sync
  installed, AzurKit's own source since Step 4.12c (Modkit takes nothing
  of it since, D959): its `patches/_player_*.py` and
  the build half of its `assets/` (X.100; never `azurik_mod/authoring`) in
  `tools/characters/`, its recipes and grades (`weapons.json`,
  `variants.json`, `chains.json`, `fx_templates.json`, `*_grades.json`),
  the 40 `player_model` shims' sources (above, Shims), and in `core/xbr/`
  Modkit's node graphs (`graph.py`, Modkit's `xbr/nodes.py`, reading the
  node types from the names table `node_types.json`, X.102: no capstone) and
  its resource copier (`clone.py`); its mesh reader and drawer (`render.py`,
  `draw.py`, numpy) are the tool's. `_player_character.apply_player_model`
  dresses the player in a species' body: the body and its clips (garret4's
  retargeted where it lacks one, D131's sizes, `retarget.py`), its attacks,
  weapon, sounds and fx, and the shims it hooks into `default.xbe`.
  - What it calls of Modkit's engine is ours, `tools/characters/ports.py`:
    the staged files (`IsoStaging`, over the files the packs left and the
    vanilla `Vanilla`, each read checked against the manifest), the hooks
    (`apply_trampoline_patch` on `core.coff` and the carve allocator past
    the packs' claims, the header state laid down from the claims), a
    hook's vanilla bytes read from the player's `default.xbe` and checked
    against the facts' swap site (`xbe_site`), and config.xbr's keyed tables
    and cell edits. `pool.py` runs the swap's parallel work in order unless
    a host gives it a map (`pool.MAP`, handed each item's cost and a tick),
    a thread for `later` (`pool.LATER`) and a progress tick (`pool.TICK`),
    which both hosts set (Step 4.3m): the app's engine and the site's
    worker count the items on the stage the call in that thread reported
    last (a dress's line), each percent once.
    The app's engine process gives it `azurkit.app.procpool` (Step 4.3i):
    Modkit's split over spawned children, `min(16, the CPUs,
    $AZURKIT_CORES)` busy across the process (a `later`'s call shares them
    with the call beside it, and takes one past them rather than wait), kept for the next, but one that has peaked
    past `RETIRE` (256 MiB; `core.host.peak`: Windows' peak working set too), which
    leaves after its part so its heap goes back to the OS, through pipes alone;
    a costed call that would start a child runs its items in the engine first,
    the cheapest first, while they stay under `SMALL` (0.25 CPU-s; the G4
    match's 35 clips, Step 4.4bh), and splits the rest; the
    results are each item's in order, so no byte depends on it
    (`test_characters.py` builds G3's cases under it).
  - A recipe's `character` (`tools.characters.normalize`): `species` and
    Modkit's `randomize-full` options (`mode`, `size`, `scale`, the attack
    sliders, `anims`, `sounds`, `weapon`, `ram`, the jiggle's) and `chain`
    (D1045: `"hit"`, the default and how a recipe without it reads, the
    combo's next attack only onto the target the last one stunned; `"any"`,
    on any press, for any body): the sdk
    folds the body's size into player_physics' walk and roll first
    (Modkit's `size_params`; its `size_fold`, the speed toggle's walk and
    roll for the body, goes to player_physics as a `Pack.inputs`, never a
    recipe's slider), then plans the character layer after the packs
    (`tools.characters.plan`).
  - **A variant** (Step 4.3c1; Modkit's `_player_variants`: a recipe over a
    base species, its mesh sculpted by `mesh_edit.py`'s ops, its textures
    painted and coloured by `paint.py` and `textures.py`, its bones on
    `jiggle.py`'s springs, its clips, sounds and effects): `species` names
    one as `--player-character` does, a built-in (`variants.json`) or one of
    the recipes of the file `variant_file` names (`--player-variant-file`;
    the files a recipe names are read beside it), else with no file one of
    yours (below), its shapes sized by
    `shapes` (`--player-shape`); an option a recipe gives must be the
    variant's, its scale and attack numbers multiply the variant's
    (`tools.characters.variant`). The layer's recipe keeps the variant's
    sha, and its notes the file's name, never its folder.
  - **Your own variants** (Step 4.6a; Modkit's variant library, D372,
    D480): `tools/characters/library.py`, a folder each in the folder
    `AZURKIT_VARIANTS` names, else `variants` in the user data folder
    (Modkit's, so its saved variants open unmoved; the site's worker reads
    `variants` in its working folder, or the `ROOT` a host sets):
    `<name>/recipe.json`, `{"<name>": {recipe}}` (`variant_file`'s shape,
    one recipe), the files it names beside it. `listing` gives each folder
    its variant or its refusal (one recipe named as its folder, no
    built-in's or species' name (`species.json`), at most 64 deep, the
    loader's checks); New (`new`), Save, Save as, New from this
    (`copy_as`: of a built-in an own copy, its recipe laid whole with its
    files, `own_copy`; of one whose build places its springs by the one it
    is `from`, booblord_high, that one's mesh and jiggle as its `places`,
    Step 4.6r, so they sit where the built-in's do and its clips' rests
    hold) and Delete check first and write whole or not at all
    (D35). `_player_variants.resolve` finds a built-in, else `variant_file`'s
    recipe, else with no file yours (`library.find`; a folder that isn't a
    variant refused by name), else an installed community entry's own
    character (`content.variant`, Step 4.38b: a recipe of its
    `variants/<id>/variant.json` no built-in has the name of, read only
    once that file and its folder's are the sha256 `installed.json`
    records (an altered recipes file is never read: one row under its
    entry's id refuses it), naming only files its entry lists; a name a
    species, yours or two entries take refused by name, never worn in
    their place, so an Install or Update never changes what a link or a
    setup already wears; its dress's log names `community <id>
    v<version>`, never the folder), so a build, a link, a mods file and the
    remembered setup wear one by name (a link with its sha12, Q174); each
    key an answer for a character is kept under (`characters.cache_key`,
    `app.ahead.key`, the sdk's dresses) stands on what a build of yours
    reads (`library.stamp`: its folder's recipe and files by sha256), and
    a recipe file's on what it holds (`library.file_stamp`), never its
    path. The
    Characters view lists them as its Yours group (`custom`). Its checks
    are `tests/test_variant_library.py`'s, one a build of the probe variant
    saved as yours, its golden's file for file.
  - **A seed with a character** (Step 4.3c2, Modkit's `randomize-full
    --seed` with `--player-character`): the sdk plans the randomizer after
    the body's size is folded into the walk and roll, so the plan stands
    on them, and the swap reads the files the randomizer and the packs
    left; the body's reasons (`characters.reasons`, Modkit's
    `layer.movement_reasons`' model half word for word: a body no sitting
    graded, no melee idle swing, a weak or endless attack, a body shorter
    than garret4) join the packs' in the verdict, leaving the logic
    unverified, never refused. G3's `seed=0,all` (flicken) was Modkit's on
    both releases but `training_room.xbr` (level_patches, AZ-009) until
    D1066 made its plan its sliders' tier's seed (Frame-perfect's), its
    body's reasons Modkit's word for word.
  - **In a share link and a mods file** (Step 4.3d): the layer
    `{"tool": "characters", "kind": "characters", "recipe"}`, the build
    manifest's own (the fields less `variant_file`, a variant with its
    recipe's sha12, `"variant"`), so a link and a build's recipe share one
    shape; a `variant_file` is refused by name (Q174), and on read a
    variant whose sha isn't this AzurKit's is named, with what to Install or
    Update. The remembered setup keeps one too (`sdk.SETUP`'s `character`).
  - **The match-Garret values** (Step 4.3d, P52, D358; the G4 buttons):
    Modkit's `_player_match.py`, ported, its staging and
    packs rewritten out: `characters.match` hands its
    `garret_match` a staging of the image with the build's packs applied,
    and `sdk.match` keeps each recipe's answer for the process (a dress
    takes seconds).
  - **The Variants editor's colour views** (Step 4.6b; Modkit's
    `authoring/colour_preview.py`, moved into the package so the editor
    needs nothing of Modkit's authoring side): `tools/characters/colour_preview.py`
    draws a body from the front and from behind in a recipe's `colours`
    (each material row's texture recoloured as W38 recolours it), each
    row's tile and palette, and its rows' textures whole as the Export's
    PNGs. It writes no built byte and reads no file (the sdk hands it the
    archives), and its own sines and cosines are fdlibm's; Modkit's
    pickled `keep` and `kept` stay out (the store keeps no pickle).
  - **The Variants editor's engine calls** (Step 4.6b; Modkit's
    `variant_library` past its library's rules, on
    `tools/characters/editor.py`): an edit is `{"iso", "name", "recipe",
    "folder", "packs"}` (a built-in's by `name` alone), read as the loader
    reads a recipe file, every refusal by name. `sdk.variant_check`
    (Check with game data, a bar op) dresses it as a build does (its
    recipe written beside its files as a hidden file the dress's
    `variant_file` names, removed after; yours as saved by name, as its
    Build dresses it, so in the app the two keep one dress; the site's
    worker keeps a Check's under the Check's hint, a Build's under the
    build's) and keeps that dress
    before its colours for the process (one, as `_DRESSED`; the app's in
    its engine, `engine.JOBS`) with its answer, which holds no picture:
    `sdk.variant_pictures` draws it after (Step 4.6q, the answer first,
    and the base body it recolours is drawn then, once a Check; the app
    asks it as the answer lands, the site with the Check, an ask that
    isn't heavy waiting behind it in F's queue, so the worker that
    dressed it draws it: Step 4.37b; one that keeps no Check, a worker
    that replaced a grown one, refuses it, and the page asks the Check
    again with its pictures, once; a Check that failed, cancelled or its
    worker stopped, leaves its pictures ask to the worker that replaced
    it, which shows no line on the bar). The pool never swaps the worker
    that keeps a Check out of F (`workers.mjs`'s `KEEPS`, Step 4.46c), so
    the asks that stand on its dress reach it: one heap swapped it to B
    for Build's build ahead, and the Colours tab and the Shape tab's
    preview then asked a fresh F, which refused them; B's heavy job ahead
    waits instead while that F's heap is the bigger, and the light ones
    listed after it (the seed's plan) go on.
    A Check of what it
    checked last, unchanged (`sdk._check_key`, by content), answers at
    once, and a dress kept before (`characters.cache_key`; the site's
    worker keeps a Check's dress in IndexedDB as `build()` keeps a
    build's) is taken, so only new content dresses (D1015, D999). On it
    stand `variant_pictures`, `variant_colours` (the live recolour),
    `variant_preview` (the
    Shape tab's quick preview, no dress: a bar op, its steps told), `variant_rows` and
    `export_pngs`; `add_png`, `add_wav`,
    `base_bones`, `own_sounds`, `kit_throw` and `move_sources` (with each
    lender body's species, Step 4.6f) need no dress, nor does
    `variant_weapons` (Step 4.6f: the Attacks tab's Weapon box, the Models
    view's offers for the recipe less its weapon; every weapon by name
    with no image, D1061). The library's calls stand on Step 4.6a's library (Step 4.6c):
    `sdk.variants` (the list: built-ins, yours with each refusal, the
    species New starts on), `variant_open`, `variant_read` (a recipe as
    the library would hold it, never raised; with its mode's attack
    defaults and, for a recipe `from` another, what that one lays,
    `editor.laid`, which the Moves and Attacks tabs show), `variant_save` (Save; with
    `as`, Save as and New from this, `library.copy_as`), `variant_delete`,
    `variant_import` (an Export's zip or a recipe.json alone,
    `library.import_`: its other files left out, a path outside its folder
    or past 256 MiB refused) and `variant_export` (`library.pack`: the zip
    and the files in it that aren't yours to share).
  - **The kit and the funnel** (Step 4.3b2, D965): the townsfolk's
    bare-hands kit (`tools/characters/clips/townsfolk/`: the weaponless
    townsfolk's weapon, `bare_hands` and the spin attack,
    with its throw, thuds and whooshes) and the worn air elemental's funnel
    (`tools/characters/fx/air_elemental/`), our own work made in Blender
    on the game's rigs, ship in the package and the wheel, so neither swap
    needs a download.
  - **The content folder** (Step 4.3b, `tools/characters/content.py`): the
    files the swap reads that Azurik-Custom-Content carries, never this
    repository or the wheel (D869, D965: optional extras): booblord's clips
    and voice (`clips/booblord/`, `sounds/booblord/`). It is the folder
    `AZURKIT_CONTENT` names, else `content` in the user data folder (beside
    the images' links), read once a process (`_player_variants`' `SOUNDS`
    and `CLIPS`). Install (below) writes the folder, every file held to
    Azurik-Custom-Content's own manifest, and the five built-in variants
    stay the engine's (`variants.json`). A build that needs a file the
    folder lacks fails naming it.
  - **Install and Update** (Step 4.3d, D913, D966): `content.check` reads
    Azurik-Custom-Content's `manifest.json` (its entries, each one's
    version and files with their sha256 and size, the entries it
    requires), and `content.install` copies an entry into the content
    folder from what a host fetched (`sdk.content_install`, `azurkit
    content install`: a URL or a folder, `$AZURKIT_CONTENT_SOURCE`
    winning): each file checked as it lands, then the host's `refusal`
    (a built-in variant's recipe by default), nothing written on a fault,
    `installed.json` last. An installed copy stays at its version until its
    Update, which only goes up and only from the source it came from,
    and no install writes over a file another installed entry holds
    (`content.held_to`, SEC-8), each held before any file is read; a URL
    source is https, http only on this
    computer (`sdk._secure`, a redirect's end too). The engine opens no connection: the sdk's CPython calls fetch,
    and the site's page fetches and its worker checks
    (`sdk.content_check`).
  - **Shipped answers** (D995, `tools/characters/shipped.py`): each
    species' and built-in variant's size at its defaults and booblord's
    whole plan at the page's defaults (the packs on by default) are made
    once, on both releases: the sizes and each answer's sha256 in the
    package's `shipped.json`, her plan one `AZKP1` file a release in her
    content entry (`variants/booblord/shipped/<release>-<sha12>.azkp`, each
    whole file zstd against its vanilla file; no pickle). A row is taken in
    place of a dress only where it stands on what that dress would read (the
    release, the recipe as given, the fold, the claims before it, the
    installed content and the sha256 of each staged file it read), its file
    read only once its size and sha256 are the row's, and never kept in
    `characters.CACHE`; else the swap runs.
    - **The re-record pin:** every dress the goldens make is fresh
      (`shipped.OFF`, which `record_goldens.py` sets, and so the tests that
      import it), and `test_characters.py` holds each shipped answer a golden
      build stands on to that build's (a slider at 1.0 as the page's
      recipe, which leaves it out), and booblord's plan on both releases
      (Europe's built for it). A change to the swap's bytes is red until
      `scripts/record_shipped.py --content <a clone of
      Azurik-Custom-Content>` re-records, and her entry then takes the new
      files at a new version (and CI's `CONTENT_COMMIT`, tests.yml, that
      entry's commit). `--check` re-derives every row (the release
      check's, and the only pin of the sizes no golden builds: a stale one
      fails that body's build by name, D35, its size not the folded one).
    - A reshape's parent (R3-CP1, X11): booblord's jiggle places at her
      defaults, a child's minute of each reshape's dress, are a `places` row
      (`shipped.places`, a few hundred bytes) that stands on the parent's
      specs, her content and the staged `characters.xbr`, so a pack or
      Data-tab edit to that file works them out; USA's and Europe's files
      are one, so one row serves both. The table names its recording host
      (`host`): off it (D1016) the pin and `--check` hold a size and places
      within `shipped.ULPS` float32 steps and a plan to what it stands on
      (`shipped.agrees`), and a build takes a fresh size close to a shipped
      one (`shipped.same_size`), exact on that host.
  - **A dress's parts** (Step 4.6n, `tools/characters/parts.py`): the
    stages of a variant's dress whose output is a function of what they
    read alone (its body's W24 mesh, W29 rig and W30 paint, three parts,
    each keyed on the one before; its size, `size_shape`; B's bakes,
    `retarget.bake_kept`; W28's arms' and springs' restyles; the LOD and
    shadow cuts and their writes; each sound's ADPCM, `wave_entry`, by its
    samples, and each WAV's read, `read_wav`, by its bytes) are kept
    in the process under a key of its stage's inputs alone (Step 4.37m1,
    D1195): `parts.VERSION` (the digest of `parts.SOURCES`, what a dress
    runs, held to it as `ART_VERSION` is), the recipe fields by `repr`
    (a jiggle's real-time springs only as there: their numbers reach X41's
    table alone), each file read in its folder by its bytes, a vanilla or
    a pack's file by its sha256, the keys of the earlier stages it reads
    and the `parts.frame` (the layout, integers only) of the file it is
    pages over; never a digest or pickle of what an earlier stage wrote,
    a float the dress worked out, the variant's name, its folder or its
    recipe file's path, which reach only its sounds and its log, and
    taken in place of the stage: a copy under any name (New from this)
    dresses only the glue between them, and booblord and her own copy
    share her body. A file a part left is named by that part's key, and
    one the glue between two parts left by the last part's key and DRESS
    (`_player_character._dress_key`: the image's and the packs' files,
    the options and the recipe's fields but its body's, its sounds' and
    the late stages', `_player_variants.dress_reads`), so the same inputs
    name
    the same file on every host; a LOD cut names its LOD 0 by W29's key
    and, after a prop's write, the file's name (`_mesh`). The glue's own reads are light: a
    body's bounds as numpy columns (`characters.mesh_bounds`), its bones
    and triangle counts without its vertices
    (`read_asset(vertices=False)`). A part's file is
    kept as the 4 KiB pages where it differs from the stage's input, in
    one block, its objects pickled; the parts held are bounded
    (`parts.ROOM`, the least recently taken let go first), under the lock
    the app's engine sets (`parts.LOCK`: it dresses on a thread a call); a
    stage that raises keeps nothing, so a refusal is worked out again;
    `parts.OFF` dresses fresh, and `test_variant_editor.py` holds a copy's
    Check to a fresh one. Across visits (Step 4.6o; the glTF clips a
    recipe reads and its kit's clips are parts too, `gltf_clip` and
    `_player_kit._rig_clips`, so a later visit reads none): each part kept is
    handed to the host's `parts.STORE` as `tools/characters/part_codec.py`
    keeps it (no pickle: `None`, numbers by their bits, strings, bytes,
    containers, `array`/numpy arrays and the dataclasses of the modules a
    part holds, by their fields, the lists and dicts held twice one again;
    runs of numbers, nested rows, bytes, dicts and one frozen dataclass in
    columns; zstd at level 3; a format, a class's fields or a class no
    part holds refused by name), under its key and `characters._code()`,
    and a part the process doesn't hold is asked of it first: the app's is
    its signed `swap` kind written behind the answer
    (`app.swapcache.Parts`), the site's the parts IndexedDB the page offers
    a Check by its recipe's content (the worker's `Parts`, below). Its
    objects stay pickles in the process (`parts.dump`'s `Pickled`), made
    into the codec's only for the store, and every taker unpickles one
    through `parts.load`, which refuses any other value by its type's
    name first (Step 4.37c).
    - **Shipped parts** (Step 4.6p, the Check design's L3): every part a
      Check of each built-in variant and of its own copy (New from this)
      works out at the page's defaults, on each release, ships: a `part`
      row in `shipped.json` (its key, which is already what its stage
      reads, its `part_codec.digest`, the answer, its file, and its
      `release`, the recorder's and the pin's label and never a key: the
      first release whose Checks work the row out, which the readers that
      serve parts ignore, so a Europe Check takes the rows it shares with
      USA under USA's label; the table's `keys` is the `parts.VERSION` it
      was recorded at, and a table of another gives no part) and its
      bytes (`part_codec`'s at zstd 19) a file in the entry's
      `variants/<entry>/shipped/parts/` in Azurik-Custom-Content, named for
      their sha256 (a re-record writes only the parts that moved), listed
      with the entry but left by Install for the Check that asks for one
      (`content.later`, which `web/content.mjs`'s `later` mirrors: Install
      and the site's page start carry none of booblord's 117 MB). A part
      neither the process nor `parts.STORE` holds is read from the content
      folder (a clone's), else fetched from the source its installed entry
      came from, never `$AZURKIT_CONTENT_SOURCE` (SEC-8; the variable picks
      the source an Install reads and records), through `shipped.FETCH`
      (the sdk's `_later` on CPython, whose 60 s count only silence; the
      site worker's synchronous request, whose timeout caps the whole
      request, given 60 s plus a second a 50 KB of the part's size so a big
      part still coming slowly isn't cut, a timeout failing as any other);
      a source that can't be reached (no connection, DNS or answer in time)
      is let be for `shipped.DOWN`, one that refuses a part (a 404) never. A part
      is read no further than its size and
      held to its sha256; a fetched one is handed to the store as a part
      made there (the app's signed store, the site's IndexedDB under the
      recipe's hint), one a content folder holds never, so a first Check of
      a built-in or its own copy, under any name, dresses only the glue.
      `shipped.OFF` takes none; a fresh part is heard
      (`shipped.SEEN`) by its digest, a set's items in one order in every
      process, and the goldens' pin builds each own copy too
      (`test_characters.py`'s `_own_copies`) and asks USA's part rows on
      USA, so each is a fresh dress's part under its key until
      `scripts/record_shipped.py` re-records; Europe's rows, keyed on
      Europe's own `default.xbe` and `index.xbr`, are held to a USA twin's
      file and answer by a pure test, and `--check` at a release names a
      row no Check works out. A reshape's
      body parts are keyed on its parent's specs, never on where its
      places came from (Step 4.6r): the recorder dresses fresh and a Check
      takes the places row, the same places by the pin, so the Check
      takes the parts it shipped. With no row (a shaped copy's places are
      its own build's at its shapes' 1.0), a reshape takes them from its
      parent's own W29 part where one is held (`_held_places`, Step
      4.37e1: the rig `_parent_places` makes from the same reads), else
      works them out, first where no host's `pool.LATER` runs them in a
      child, so the preparation `mesh_edit` keeps is its own plan's, the
      one its rig asks again.
- **What a swap writes with** (Step 4.3a1): `core/xbr/append.py`
  (`append_resources`: new resources on pages after the last payload, their
  named rows, names and relocation rows; `rewrite_payloads`: a payload
  grown in place, every later one moved by whole pages; `appended`), and in
  `tools/characters/`: `characters.py` (a body and its clips),
  `body_codec.py` (a body decoded whole and written back with any
  topology) and `index_xbr.py` (`index.xbr`'s records, `add_index_records`).
  What they import of Modkit's `xbr/toc_scan.py`, `xbr/edits.py` and
  `xbr/sections.py` comes from `core/xbr/nodes.py` (`named_resources`,
  `runs`, `XbrStructuralError`, `IndexRecordsSection`).
- **The character layer** (§12.2's whole-file group): a swap grows
  `characters.xbr`, `fx.xbr` and `index.xbr`, so it writes each it changes
  whole, all one group (`tools.characters.whole_files`: `Change(...,
  whole=True)`, `before` the whole vanilla file's sha256), and the rest as
  ranges: `default.xbe`'s bytes one group, config.xbr's a group a table.
  Its shims' placements are its claims. A whole file shadows each earlier
  group whose bytes it doesn't hold (dropped whole, a conflict); a later
  range lands over it only where it kept the vanilla bytes (or holds the
  range's own), and is refused where it changed them (D35, Modkit's AZ-096:
  a grown body moved the resource there). One group per file may write it
  whole. The layer stacks after the packs and before the Data tool's `xbr`
  operations (Modkit's `mod_apply` order).
- **Its checks** (`tests/test_characters.py`): every body round-trips
  through the codec, appended resources resolve by name with the old ones
  unmoved, each G3 model case's `index.xbr` is its golden's byte for byte
  (from `resources.json`'s records, on both releases), the swap's XBE
  sites hold their vanilla bytes on both releases, a layer's whole files
  build an image that reads back, and, with an empty content folder, each
  of G3's 27 body cases (its weapon and sound cases, the bare-hands kit's
  and the funnel's, and garret4's own body among them) is its golden's file
  for file and resource for resource, its default.xbe writes inside its
  claims and the facts' swap sites (keylord's whole image too), and so is
  each probe of `probes.json` (the variant's, a townsman's and the air
  elemental's), on both releases; a build that needs booblord's clips
  fails there naming the file. With booblord installed from Azurik-Custom-Content
  into a new content folder (the `booblords` fixture: Install's own path,
  from `$AZURKIT_CONTENT_SOURCE`, else the clone beside the main checkout),
  each of G3's 7 variant cases (the five built-ins' recipes
  applied to the player's image, booblord's with her lods and with a
  weapon, and the effects case, a recipe file's fireball row made of the
  effects templates) is its golden's the same way, and the effects case on
  Europe too: 34 of G3's 34 USA model cases.
- **Authoring:** the model verbs and the how-to (Blender, budgets, LODs,
  `weapon-fit`) are `devkit/models/README.md`; a recipe's fields are
  `docs/VARIANTS.md`.

## The engine's contracts

- **Layers:** `core <- edits <- tools <- sdk <- {cli, app}`. The five tools
  (`mods`, `randomizer`, `characters`, `data`, `saves`) never import each other. import-linter
  holds this (see `pyproject.toml`).
- **AST rules:** `core`, `edits` and `tools` hold no threads, processes,
  subprocesses, prints or exits, so the web page's worker runs them as they
  are. The worker loads the wheel without its dependencies, so the engine
  imports platformdirs only where it needs the user data folder. Only `tools/characters` and the randomizer's drawing
  (`tools/randomizer/art/`, `draft/`) import numpy, and nothing imports capstone,
  unicorn, zig, Tk or `devkit` (the developer side, which never ships).
  `tests/test_contracts.py` checks these, along with import-linter's
  contracts.
- **The same transcendental bits on every platform (AZ-830):** each
  platform's libm rounds some sines, cosines and powers otherwise
  (macOS's for CPython, musl's under Pyodide), so the swap's (`tools/characters/`) and the XBR graphs'
  (`core/xbr/`) transcendental math is `core/fdlibm.py`'s: fdlibm's
  algorithms in pure Python, built from correctly rounded operations alone
  (musl's bits where musl's is fdlibm's), and a power is `fdlibm.sq`, `cube`
  or `pow` (CPython's `float ** 2` calls the platform's `pow`; numpy's
  arrays take them as they are). No `math` or numpy libm call and no `**`
  but an integer's there; the previews' drawer (`draw.py`) writes no built
  byte and keeps numpy's. `tests/test_contracts.py` holds this.
  - **Across machines the bits may differ (D1016, AZ-833 accepted):** no
    test or build requires identical float bits between machines or hosts
    (numpy's BLAS on each OS, the site's Pyodide); one host's builds stay
    exact, and so does D35's read-back. Where a build's float maths can
    differ, a test keeps a reference per platform or compares close enough
    (integer fields, sizes and layout exact, floats within a few ULPs).
- **The compiled kernels (D1009):** a hot loop may be C99 in `native/`,
  built by `python -m nativekit` with the pinned zig for six targets from
  one machine (macOS arm64 and x86_64, Linux x86_64 and aarch64 on glibc
  2.17, Windows x86_64, and the wasm32 side module the site's Pyodide
  loads) into `src/azurkit/core/_native/`, committed, with no float
  contraction (`-ffp-contract=off`: zig's default fuses a multiply and an
  add, which rounds otherwise than Python), no fast math and the targets'
  baseline CPUs; `--check` rebuilds them to the same bytes. A kernel is a
  pure function over caller buffers (no allocation, no libc).
  `core/native.py` loads this platform's library with ctypes on both hosts,
  and each kernel keeps its Python twin there, the reference: the twin runs
  without a library, when the library can't hold a call's numbers, and
  under `AZURKIT_NATIVE=0`, with the same answer bit for bit
  (`tests/test_native.py`, over seeded random inputs, natively and under
  Pyodide). The first is the randomizer's reach (`native.solve` over
  `native.Tables`): every reach the planner, the fill and the tracker ask
  runs it (`Logic._solve`; an option set's tables built once, in about
  0.02 s, by `Logic._tables` from its rules' closures' `ast`, a trace's
  spheres replayed from the kernel's rounds), on the app's CPython and,
  by the side module from the wheel, in the site's worker. The second is
  the fill's (`native/fill.c`, Step 4.4ci57, D1141): `fill._Kernel` packs
  a run's facts once (each id the reach tables'), and an attempt
  (`_Slots.attempt`, its twin: the passes, the lean, the trap gate's
  repairs and the verify, on CPython's MT19937 streams) and a seed
  difficulty's candidate's need and play (`difficulty`'s, through
  `Judge.kernel`) each
  run there whole, its reaches reach.c's, off the GIL, so the attempts
  beside each other run on their own cores; the notes the twin would tell
  are logged and told after the call in its order, so an attempt's cancel
  point is its end. The third is
  the dress's (`native/dress.c`, Step 4.3r4d4): `retarget`'s engine
  model (`pose`, `origins`, `origins_at` over many times; `jiggle`'s
  springs' chains and the clear's body at every time at once, on those
  bones alone: `_posed_at`),
  `bake_clip`'s rows (`_linear_rows`, `_chain_rows`), the damage boxes
  (`characters._boxes`), the crossfade's `sample` and `_heights`,
  `jiggle`'s skinning loops (`_skinned`, `_signed`) and the byte runs
  (`characters._runs`, compose's shadowed bytes), each twin the function it
  speeds, beside it, and a value it can't take (a key or bone not
  floats, a time not finite) the twin's; every NaN is a NaN there, its
  sign and payload not held (a compiler may take an operation's two NaN
  inputs in either order). The fourth is the mesh edit's rays
  (`native/mesh.c`, Step 4.6c): `mesh_edit._ray_at`, a round side's ray
  through a point (its form's exit, a drape's hull, the blend, the gate
  and the fades), on the side's numbers packed once (`_ray_row`); a
  division by zero, which the twin raises, is the twin's. A side's rays
  over many points are asked in one call (`az_rays`, `_rays_ahead`: the
  shares' runs, and the rounds a round at a time over every point,
  `_round_all_each`), kept in `_RAYS` for `_ray` to take as asked: under
  Pyodide a ctypes call costs some browsers more than its ray. The fifth is
  the decimator's collapses (`native/decimate.c`, Step 4.6c):
  `decimate.decimate`'s loop past its `_Work` setup (the offers, the link
  test, the cost, the max_error's rehome and the collapse, the cheapest
  first, ties by point) on its packing (`_compiled`); its sets are lists
  there (no result reads their order), a NaN or a skin the twin refuses is
  the twin's, and its pool and heap grow until they hold the cut. The
  sixth is the clip import's thinning (`native/dress.c`'s `az_thin`):
  `clip_import._thin_track`'s keys kept past its stepped test (its twin
  `_thin_kept`: each sample's value `retarget.evaluate`'s, the Hermite run
  from the last kept key checked against the samples between), a time not
  finite or not after the one before the twin's, and `jiggle._smooth`
  (`az_smooth`: a spring's path through its integer weights; a loop of
  under 2 samples or weights summing to 0 the twin's). The seventh is the
  paint's (`native/paint.c`): `textures._dxt`'s BC1 and BC2 blocks
  (integers only), `paint._raster`'s texels (a corner not finite, past
  2**40 or -0.0 the twin's) and `fdlibm.atan2` over a texture's points
  (`paint._atan2`, `_hsv`'s hue; fdlibm's constants by their bits). The
  eighth is the springs' (`native/spring.c`, Step 4.37e3): `jiggle.keyed`'s
  spring of each placed bone of a clip past its parent's pose (`az_spring`:
  the anchors' smoothed path, the drive, the Euler steps, the fit to its
  travel and turn, `pose_at` and the keyed numbers; its twin `_spring`) and
  the clear's (`az_clear`: `_clear`'s frames, each link's search of its
  least turns, their ease, a held clip's drape and the keys it rewrites,
  one call a clip; its twin `_clear`'s own loop), its glue (the poses, the
  constants, the point sets) `jiggle`'s. A division by zero, which the twin
  raises, a point set numpy refuses, a turn past fdlibm's kernels and a
  pose the engine model can't take are the twin's; the drive's integer
  weights are doubles as Python's arithmetic rounds them; a skin's normals
  are worked out only for the points found nearest, the skin points in
  the points' box are taken from the frame's buckets along its skin's
  widest axis, and each point's nearest skin point within reach is found
  in buckets along the widest axis of the box, a bucket passed only where
  its nearest value is farther than the best so far, ties to the first
  point as numpy's `argmin` takes them (a box or skin not finite searches
  every point in order). The ninth is the body writes' (`native/body.c`,
  Step 4.37e4): `body_codec`'s stripify (`az_strip`: `_stripped`'s greedy
  strips and its check that the strip draws its triangles; its twin
  `_strip_twin`), regroup's split of a group that doesn't fit
  (`az_regroup`: the bone clusters, the halving at the median, each part's
  vertices, palette and slot codes and the fit of its strip; its twin
  `_split`, the parts' groups built from its answer), `problems`' checks
  of each vertex and triangle (`az_checks`; its twin `_checks_twin`) and
  `write_asset`'s read-back compare of a group's triangles (`az_same`). On
  integers but the centres (Python's `sum` of three floats), so a dict's
  lists keep their order, a heap's unique keys pop in theirs and Python's
  `min` its first; a vertex not a tuple of floats, a triangle not three
  int64s, what the twin raises on and a centre not finite are the twin's.
- **The hosts' hooks (Step 4.3h; each `None` or off by default, today's
  behaviour):** a long call reports its named stages to a host's
  `progress(record)`, `core/progress.py`'s `{stage, label, done, total,
  percent}` (`sdk.image`, `sdk.save`, `sdk.plan`, a plan's first
  `sdk.tracker`); `sdk.image(spoiler=False)` leaves a seed's spoiler for
  `sdk.spoiler(plan, built=True)`; `sdk.save(made, out)`
  writes the image a Build made without planning it again, refused once its
  input changed since it was read (`iso.Image.origin`), its sha256 hashed as
  written or the host's (`iso.digest` on a thread of the host's, `sha256=`);
  `gate.STAMPS` is a host's store of the images it vouched for across
  launches (by path, size, modification and change times) and
  `characters.CACHE` its store of the swap's answers (`size`, `plan`, by
  `characters.cache_key`).
- **The store** (`src/azurkit/store.py`, D1015): what AzurKit keeps
  between calls and launches, one folder a kind (`store.KINDS`: plans,
  layers, dresses, pictures, memos, swap), each entry sealed whole (the
  kind, key, length and body: a sha256 by default, the app's an HMAC) and
  read back only whole, sealed and of its kind's form (a torn, altered or
  moved entry is a miss, never decoded). Its kinds keep JSON or AZKP1, never
  a pickle; `swap` keeps bytes: `characters._kept`'s (a size's hex, a plan
  as `AZKP1` at `characters.KEPT_LEVEL`, made on the writer's thread: about
  7.9 MB for booblord's 110 MB pickle, Step 4.3r4i), a dress's parts
  (`part_codec`'s, Step 4.6o: 28 MB for a booblord copy's 98 MB) and those `engine._kept`
  still pickles, until those move to `memos`/`pictures`, the plans to
  `dresses` with them (the page's Storage lists `swap`). One
  budget across the kinds (`store.BUDGET`, 5 GiB): a write past it removes
  the least recently used entry, whatever its kind. It removes only files
  of its own names in its kinds' folders, never a player's settings,
  content installs or key. It starts no thread, so the page's worker can
  run it.

## The two hosts (D866)

- **Engine halves no host calls yet** (each tested alone; its hub half wires
  it): the warm-up
  (`app/warm.py`, `web/warm.mjs`), the kept answers (`app/memo.py`,
  `web/memo.mjs`) and the service worker (`web/sw.js`).
- **The page** (`web/`): pick the image, choose packs and set their sliders
  (a box takes any value; the track widens to hold it), Build, then Save. One
  page for both hosts: `host.json` names the host's engine. It decides no
  output byte. Its CSP has no `'unsafe-eval'` and it uses no eval, and no
  host evaluates script in it (pywebview's `evaluate_js` would need eval).
  Text reaches it only through `textContent`.
  - **Its design** is A, the dense tool (D900): the toolbar's tabs are the
    catalog's (`sdk.TABS`, in D901's order: Patches, Randomizer,
    Characters, Data, Tools, About), each only once its area works (D902:
    flip its flag in the step that makes it work, with a panel in
    `index.html`); the Patches tab groups the packs by their category
    (`mods.CATEGORIES`, Modkit's), each group folding, and a pack's
    Settings opener (with the count of their rows) shows its sliders beside
    the list; a pack's settings are locked (disabled, still readable) until
    its pack is ticked, keeping their values while it is unticked (D907);
    a whole 0-or-1 setting named `toggle_<other>` shows as a small L3
    toggle at the end of `<other>`'s row, not a row of its own (D909: the
    page pairs them from the catalog, never by pack). Build and Save sit in
    a bar along the window's bottom (D903). It is dark whatever the
    system's setting until the toolbar's toggle picks light (D897),
    remembered by the site in the browser's storage and by the app in its
    config (`host.json`'s `theme`, `api/theme`: its page's address is new
    each launch). `theme.js`, a classic script in the head, sets it before
    the first paint: the site's reads the storage, and the app serves its
    own from its config and opens its window on that theme's ground. A long
    call shows its progress in the bottom bar (D980, Step 4.3i: `#progress`,
    app.mjs's `progressed()`, one renderer for both hosts): a build's, a
    save's and Track's (the seed's plan, from its click as a build's, then
    its first tracker view)
    `core.progress` records (the app's `api/progress`, polled every
    250 ms from each ask's click, any ask's record shown once it has one;
    the site's worker's `progress` posts, the image's check among
    them) as their stage's line and percent, and any other ask the engine
    hasn't answered within 1 s as its line on a moving stripe. A control
    that can't work yet is greyed with the line that says what it waits for
    (D979: app.mjs's `lines()`): Build until an image is picked (a vanilla
    one: an AzurKit build only offers its recipe) and the engine is ready
    ("Pick your image (1.) to build", `#build-line` and its title), Save
    until a build, the spoiler's line naming the image, and each pack whose
    vanilla values the image holds saying so in its settings until it is
    read. The About tab's licence and credits
    restate `LICENSE` and `NOTICE.md` (`tests/test_site.py` holds them
    to those files); its privacy line says only that AzurKit collects
    nothing and that the image never leaves the computer (D883); its
    version line names the commit AzurKit was built from, never fetched
    (`azurkit.commit`: what the wheel's or the frozen app's build wrote,
    `azurkit.STAMP`, else a git checkout's HEAD; a build or checkout
    without git says it can't name one); its platform line names where the
    engine runs (`azurkit.platform`: the system and processor, or Pyodide's
    version in a browser), as Modkit's Settings page did.
  - **The Randomizer tab** (Step 4.2c1, RANDOMIZER_PLAN §5.5): Randomize
    (off by default, the tab's one switch, which unlocks its settings,
    D907), the seed (any text; New draws 0-999999), Movement, the skip
    ceiling and the obsidian cost (vanilla 10,
    D910), with D144's defaults (`sdk.catalog`'s `randomizer`, which offers
    the Seed difficulty levels and their tip; `randomizer_settings`'
    `difficulty`: each level's `[value, name, enabled, line]`, every one
    offered at any settings: the Seed difficulty select after Skips, Normal
    first selected, says the chosen level's line under the row, and a
    v1.0.0 level loaded says on the warning line what it loads as), the share
    string (editable, Copy), Load settings… and Save settings… (D144:
    a settings file, read and written by the engine: `randomizer_settings`'
    `file`, the app's `api/settings_file`), the item rows (each a category
    it shuffles, its icons (the icon sheet's tiles), and how many the base
    game places, `tools.randomizer.base_counts`; keys and barriers stay
    vanilla), the skip groups (D258, D1061, `tools.randomizer.SKIP_GROUP`,
    every skip of the database in one: a tick turns on all its picks, whatever
    their rating, an untick all off, each by a toggle only where the ceiling
    the Skips select holds now differs (each row's `ratings`, so a click
    before the engine's answer to a Skips change reads the new ceiling); a box is derived from what's on, ticked all, half some, empty
    none, with "6 of 7 · up to Frame-perfect", so a loaded setting's show
    too) and, folded shut under "Specific skips · 3 of 36 on" until a group's
    tick opens them, the skips a setting can turn on in their groups' order (a
    click toggles one against the ceiling, and its group goes half). The page
    holds the settings as
    a settings table in format /2 (each category as it is) and asks the
    engine what they give (`sdk.randomizer_settings`; the site's worker,
    the app's `api/randomizer`): the share string with the Patches tab's
    movement sliders and the Characters tab's body's size folded into the
    walk and roll as its build folds it (`character`, sized on the picked
    image: the site's worker mounts it for the ask; with none, a ⚠ line says
    the plan stands on garret4's), so Track this seed plans a character
    build's plan, the skips, and a ⚠ line for the preflight's refusal
    (too few proven spots for the fragments and powers once rows stay
    vanilla, AZ-454: obsidians hold 32 of the 40; Build greys while
    Randomize is on, its line the row to tick, Step 4.4u1)
    and what a build would leave unverified (a loaded share string's note
    of other sliders, naming the body where a size fold is the difference,
    stays until the tab is edited or the Patches tab's sliders and body
    give that share string). With Randomize ticked, Build
    sends the build's `randomizer` (seed, settings, a cost other than
    vanilla's), planned and written first; its report carries the verdict,
    and the spoiler (Modkit's `--spoiler` file) comes after it, so the
    build shows sooner (`sdk.image(spoiler=False)`: the site's worker sends
    it once the build is posted, and replaces a worker the page doesn't
    keep only then; the app's engine makes it from the plan it kept at the
    first View or Save, `api/spoiler`), which the tab shows and saves (the
    site's download, the app's `api/spoiler` `{"out"}`). The tab's setup
    is remembered too (`randomizer`: on, seed, settings, cost) and Reset
    unticks it.
  - **The Tracker view** (Step 4.2c2, `web/tracker.mjs`): the Randomizer
    tab's second view (Settings · Tracker). It opens on a randomized
    build's plan (the report's `plan`), Track this seed (the Settings
    view's seed and share string, planned by the engine: `sdk.plan`, the
    site's worker, the app's `api/plan`), an opened build's (the Tools
    tab's Track this build: its manifest's seed and share string, planned
    the same way, nothing retyped) or a plan file, and asks the
    engine (`sdk.tracker`: the worker's `tracker` call, the app's
    `api/tracker`) what it shows, one ask at a time, each click one: the
    head line, the counter row, the world map (`tracking.GRID`, each level
    with its spots reachable now, amber when only a skip reaches them), a
    level's spots as chips (a click marks one; a spot not shown is told by
    the item vanilla puts there), and the Table. The page keeps the plan
    last tracked and the marks of the last 20 plans (the site's storage
    `azurkit.tracker`, the app's `api/tracked`, `host.json`'s `tracker`):
    names and numbers, never the image; the plan opens again when the
    Tracker view first shows (Step 4.3f: its first ask builds the tracker's
    logic, which held the page's start). **Live** is the app's alone (D882):
    `api/live` starts `azurkit.app.live`'s feed (a thread) for the plan,
    and each `api/tracker` ask merges its events and the element levels the
    game holds and returns `live` (the status, where it saw the player: the
    body, not the last point it touched the ground; while xemu runs another
    seed or build, how many of a level's item spots differ from the plan's,
    or that none was randomized, and what to check),
    which the page asks for every 0.7 s; Follow shows the player's level
    and the floor under their feet as it changes (`floors.json`'s table:
    the floor all their pixel's storeys are on, else the storey nearest
    their height; at a seam the floor they were on holds while its ground
    lies within 2 m; a floor picked by hand stays until theirs changes, and
    Follow off never switches), Find me (key F) shows it once. As Modkit's: the marks keep the saved
    slot the game last showed, each session Live opens (the link back, Live
    off and on) checks the game against their journal (that slot, the
    newest live mark's day clock), Reset with Live on reads the game again,
    and an error that ends the feed turns Live off.
  - **Play and Attach…** (the app's alone, Step 4.6k: Modkit's
    `live_launch` and `live_helper`; `web/play.mjs`): `api/play`
    (`azurkit.app.play`, `azurkit.app.xemu`) launches the player's xemu with
    the saved build and private endpoints the feed tries first, or asks
    (attach to the xemu running, which one, where); `api/attach` starts the
    macOS root helper (`azurkit.app.live_helper`, a file the app copies for
    root and never imports: stdlib only, Python 3.9) behind one admin
    prompt; `api/tray` gives the randomized AzurKit build in a running
    xemu's tray, whose seed a Live tick tracks first. Tests fake the discovery, the
    launch, the prompt and the tray (`tests/test_hosts.py`'s
    `_no_xemu_in_the_tray`): none reads this computer's xemus or prompts.
    Each Build writes a log (`azurkit.app.logs`, the user's log folder).
  - **The maps** (Step 4.2c3, R1.41, R1.43; shipped since Step 4.3f, D961;
    `web/art.mjs`, `web/mapview.mjs`): Modkit's pictures of every level's
    floors, the world map and the one icon sheet (`icons.png`), with the maps' index
    (`maps.json`) and the floor table (`floors.json`), ship with the page in `web/art/<ART_VERSION>/`, and
    `web/art/index.json` names that version and where the sheet's tiles are, and
    `web/art/icons.css`, which the page links, names them for the lists (a `.glyph`, no script, so the
    Randomizer's rows show them before any map is read; the map's canvas draws them from `icons.png`). A
    spot not shown is a plain dot, so an icon never spoils a seed; the map's gem dots stay dots; the fire
    barrier is the page's drawing. Only
    `scripts/record_goldens.py`'s `art` family writes them, drawn from the
    USA image (`sdk.art`, Modkit's drawing; `--check` writes nothing), and
    `tests/test_art.py` holds them (Modkit's committed pictures at the
    cut) to what each release's image draws: a
    change to what draws them moves `ART_VERSION`, and they are recorded
    again. No host draws them and none needs an image: the site reads
    `art/index.json` and its `maps.json`, the app `api/art`
    (`azurkit.app.art`: its bundle's folder, or the checkout's) and serves
    `art/<version>/<name>`. The Tracker view shows the world map with every
    level's picture as soon as it shows, before any plan (its badges and
    exits once one is tracked; with no plan, Step 4.4u3, `sdk.tracker({})`'s
    vanilla game's spots, asked once, open any level from Map, the level
    picker, or the world map, each spot ringed plain with its vanilla item,
    a click on it marking nothing; a plan opened then shows the level
    browsed), and a level as Modkit's map view on a canvas: its picture by floor (the floor
    buttons, each badged with its tracked spots not collected yet), its features, barriers, tracked spots and exits at their
    vanilla places (each spot's ring, icon and check as Modkit's track(), an
    exit's ring by what using it needs, `tracking.world()`'s `maps`; a
    collected spot leaves the map, and Show collected, remembered, shows
    it dimmed; a Live pickup, Live's `took`, flashes its spot a moment
    before it leaves, flashes its rows and the Got count and says "Got:
    <item> · <level>" for a few seconds, a plain highlight with reduced
    motion), a
    click marking a spot or opening an exit's level, the wheel zooming about
    the pointer, a drag panning, a double click or Fit showing it whole, the
    map filling the window as it resizes, and, with Live, the player's dot
    (Follow keeps a zoomed map on them, easing after them once they leave
    the view's middle half, so the reads' jitter never moves it, and Live's
    bar keeps its size from poll to poll; Find me centres it). The world map:
    each level's main floor, its badge of spots reachable now (amber: only
    a skip), the exits' lines. Where the pictures can't be read, the world
    map is a grid of the levels and a level's spots are chips. **Gems** (off by default, remembered: the
    tracked plan's `gems`): each gem spot not all taken a tiny dot in its
    gem's colour, under every other overlay, the gems taken and left under
    the title, on the floor buttons and on the world map, and the colour
    key; Live (the app's) reads the gem spots while Gems is on (`api/live`'s
    `gems`) and takes a dot once the game shows its gem taken.
    `web/mapview.mjs`'s `marks` and `badges` are the map's verdicts:
    `tests/test_site.py` holds them to `tracker.json`'s (`TRACKER_MAP`,
    first recorded equal to Modkit's map view's) at TRACKER's states and shows the
    shipped maps with no image and no engine call in both browsers, and
    `tests/test_hosts.py` the app's map, a click, zoom, resize, Live
    taking a gem's dot and the frozen app serving the pictures. **Detail
    pictures** (Step 4.3l, D988; Modkit's Step 2.97 rule and drawing): each
    floor of a level whose map is coarser than 1.6 px a metre (18 levels,
    `art.detail_factor`) ships again at 2 px a metre in
    `web/art/<ART_VERSION>/detail/<floor>.png` (`art.detail`, the art
    family's alone), `index.json`'s `detail` names each level's factor (the
    app's `api/art` too), and the map reads the shown floor's when its zoom
    comes within a notch of its own pixels and draws it past them (at a fit
    past them too), one held at a time; a failed read keeps the map's
    pixels and says why in the column. `tests/test_site.py` holds the page
    to it (none read before, the detail's pixels drawn, a floor's replacing
    another's, Fit, a level with none) and `tests/test_hosts.py` the app's.
  - **The Characters tab** (Step 4.3d, `web/characters.mjs`; Modkit's
    Player page): the models' list, every species the player can wear in
    its grade's colour, the 73 untested greyed and marked (D877; with no
    image, the 178 of `picker.SPECIES`, `species.json`), the 76 objects
    only with Show objects (D1034: off by default and remembered, the site's
    storage, the app's `show_objects`; an object is the engine's rule,
    `characters.object_bodies`: at most two bones and no clip but an idle or
    a sit, so the 73 pickups and the clipless statues, never the boulder;
    the count line says how many are hidden, and a model worn stays listed),
    then under it the
    community group beside Content from (D1035; D913: Azurik-Custom-Content's
    variant entries beside the species, each marked community, its state
    Install, installed vN or Update to vM, its variants once installed); the chosen
    model's two pictures (D772, D919: `picker.preview`'s draw.py, front and
    back, on both hosts; a variant's from one dress, `sdk.preview`; in the
    first frame of its idle, D1042, `tools/characters/pose.py`: the body's own
    `idle`, else the slot's pick among its clips, a recipe's `idles`' base on a
    variant, the bind pose with no clip), its
    info and its options (Gameplay, Weapon: each pick marked by its fit and
    coloured by the grade its build reads, an untested model's grey,
    AZ-807; the clips, sounds, balance, ground and height boxes; the four
    numbers, each with a G4 button, `sdk.match`; a body's jiggle and a
    variant's shapes). The engine decides it all (`sdk.pickers`:
    `tools/characters/picker.py`): the page sends the tab's choice and
    draws the answer, and Build, a link and the remembered setup take the
    view's `character` (a variant's recipe-decided options left out). Build
    refuses an uninstalled community variant that needs files, by name.
    **Shipped** (Step 4.3f, D961): `species.json` and, in `web/characters/`,
    every body's two pictures, each built-in variant's at its recipe's
    defaults (one the game's memory refuses has none) and the engine's
    no-image answer (`index.json`), which only `scripts/record_goldens.py`'s
    `characters` family writes (from both images; a variant is dressed
    again only when its recipe as it builds changes, the one it is `from`
    laid under it) and
    `tests/test_characters.py` holds to the images and the app's draw: the
    page shows that answer at the tab's first open and a model's shipped
    pictures at its click, with no image and no engine call; G4 stays greyed,
    saying the image is needed, until the engine's answer has read it (D979),
    and the Weapon box lists every weapon before that, how each fits after it
    (D1061), a pick no sitting saw marked "not tested". Preview by that box
    opens a small popup of the weapon's shipped pictures and line (the same
    family; `weapons.json`'s `previews`), no image and no engine call. Reset takes
    the sliders, options and weapon back to the chosen model's defaults and
    stays on it, shown in its click with the model's own pictures (Step 4.4u2:
    the options from the last answer at the model's mode and weapon defaults,
    which alone change them; the engine's answer follows); picking Garret
    clears them too, another model keeps the size and the numbers (D1062;
    `tests/_perf.py`'s A81 and S66 time Reset). On the site an ask made while
    the image is unread goes twice: first with no image, which B answers while F reads
    the image (`workers.mjs`'s aside asks; with no B it waits for the
    check), so an Install's list and a model's panel never wait for it once
    the tab has opened (Step 4.3r4m), and then with it; a build takes the
    second's answer, which stands if it comes first. The tab keeps one ask
    in flight: the choices made while it runs are asked once it answers, as
    they are then (Step 4.4u2: a drag queued an ask an input event; A82 and
    S67 time a drag's answer). Content from (the source; default `sdk.SOURCE`, the hub's raw URL, live
    since the content repository went public, D1027) is remembered (the
    site's storage, the app's `content_source`).
    The site reads any https address, with no warning, or its own (its
    CSP's `connect-src 'self' https:`, D1135: `web/content.mjs`'s `where`
    refuses plain http elsewhere and a folder by name, and a read that
    fails says what failed, the last list shown; `scripts/web_tools.py
    --site DIR --content CLONE` serves a clone as `./content-source/`,
    the perf's source), checks an Install in
    its worker (`sdk.content_check`, given the source: an Update only from
    where it was installed, SEC-8, asked before it fetches a file and again
    with the files; a known flaw, D835: an Install clicked while F builds
    fetches once that build ends, its first check queued behind it, as
    F's build drops B's job ahead and no B loads beside it, Step 4.53b),
    keeps the files in IndexedDB and
    writes them into its worker's `content/` once a worker; the app's
    engine installs into its content folder. A known flaw (D835): on the
    site a detailed variant's dress (booblord's) may run out of wasm
    memory; the page then says to use the app. 4.4 waits until every site
    build fits the capped profile's 6 GiB (D1021: no use-the-app fallback).
  - **The Variants view** (Step 4.6c, `web/variants.mjs`; Modkit's
    Variants page, D372, D480, D1087): the Characters tab's second view
    beside Models (`char-view-*`, as the Randomizer tab's Settings and
    Tracker). The list (built-ins, community ones marked, then yours, a
    refused one marked), New (a species from `web/picker.mjs` in the
    page's own dialog), New from this, Save, Save as, Delete (after a
    yes), Import and Export (a zip; the site's download, the app's
    Downloads folder or save dialog), Gameplay, the Body, Shape, Jiggle,
    Moves, Attacks and JSON tabs (each tab but Body's and JSON's a module of
    `web/variants/`, Step 4.6d, handed the view's `ctx`: the recipe, its
    read, an edit, the engine, the shared pictures; Shape's drag shows the
    nearest shape held marked Preview, D1011, and its let-go the quick
    preview or, unchecked, the Check; Jiggle's Add lists the last Check's
    bones, else `base_bones`; Moves and Attacks, Step 4.6f,
    `web/variants/moves.mjs` and `attacks.mjs`: Modkit's, their picks, lent
    clip names, drain, carry and held, seeks, clip numbers, weapon and
    attack numbers with no clamp, D23; the bodies' clips greyed with D979's
    line until an image; their menus in the page's own `#var-menu`),
    Check with game data (greyed with D979's line until an image; its bar
    the bottom bar's) and the status line (sha12, grade, saved, checked);
    the engine decides every recipe (`sdk.variants`, `variant_open`,
    `variant_read`, `variant_save`, `variant_delete`, `variant_import`,
    `variant_export`, `variant_check`, `move_sources`, `variant_weapons`). Unsaved edits are asked about in
    the page's own dialog (`#var-ask`, on the body: a Build's question
    comes from any tab) before another opens and before a Build of that
    variant, and the page's `beforeunload` asks before it goes where no
    window does (the site, and the app's page in a browser: no file
    dialogs, `host.json`'s `dialogs`); in the app the view tells its server whether it holds edits not saved
    (`api/unsaved`, each told once the last is answered) and the window's
    closing hook (`Server.closing`) asks Leave or Stay with pywebview's own
    dialog, on a thread of its own: the hook holds the close, Leave quits
    and closes the window, Stay keeps both (no `evaluate_js`). The
    app keeps your variants in its library (`api/variant_*`; Clear leaves
    them: they are your work, Modkit's folder too); the site keeps them
    in IndexedDB's `azurkit-variants` (`content.keeper`'s, which closes on
    a delete's version change so Clear never waits on the page), hands
    them to each worker as `{type: "library"}` (the worker's own
    `library()` writes `./variants` whole, numpy unloaded: once a worker
    and after each change; the view's calls load numpy first), and the
    work ahead's key counts each handoff. The Models view lists yours as
    its Yours group (`#char-custom`) with Edit… on a chosen variant.
    `tests/test_variant_library.py`, `test_variant_editor.py` (the Moves
    and Attacks tabs' logic under Node), `test_site.py` and `test_hosts.py`
    hold it; `tests/_perf.py`'s A87-A93, A95, A96, S73-S79, S81, S82,
    A110-A113 and S110-S113 time it. Its A98, A99, A104, A105 and S84-S87
    time a Check of booblord's copy after each edit the page makes (a Shape
    slider's let go, Scale, a Jiggle stiffness, a colour on the wheel; each
    a value no Check held, clicked the head start after it; a later page
    whose let go took no Shape Check Checks it untimed before the next
    edit, so each Check carries its own edit alone, Step 4.49a), and A106 and
    S88 one whose Content from holds none of her shipped Check parts (the
    site's `./content-unparted/`, which the perf's server answers as
    `content-source/` but each part a 404): heavy ops, each held to its
    tier's line (D1244: Commits and landing's tiers).
    Its tabs are modules of their own under `web/variants/`, so each tab's
    lane edits its own file. The Colours tab (Step 4.6e,
    `web/variants/colours.mjs`; Modkit's, D772, D809 (a)) draws on
    `sdk.variant_colours` (one ask at a time, the newest edit asked once it
    answers) and exports `pickColour`, the wheel picker another tab's colour
    takes; its Import PNG is the app's `api/add_png` (by path) and the site
    worker's `add_png` (the picked file's bytes, `PICKED`), the file kept
    in this browser beside the recipe. The view's Undo keeps 100 steps,
    edits closer than 0.6 s one (Modkit's AZ-797). `tests/_perf.py`'s
    A100-A103 and S100-S103 time the tab.
  - **The Data tab** (Step 4.7a, `web/data.mjs`; D986, Modkit's Game Data
    editor): config.xbr's cells before an image (`sdk.data`, from the
    vanilla file `tools/data` ships): the Player, Critter, Item, Armor and
    Weapon views, All tables (a grid: sort, Changed only) and Changes
    (Step 4.6i: each cell the edits change beside its vanilla value, then
    a mods file's byte edits; `azurkit diff` and `sdk.mods_diff` give a
    mods file's edits one by one, `tools/data`'s `preview`), its entities
    in the shared picker (`web/picker.mjs`, whose species list and rows
    the Characters tab uses too). A cell's edit is checked by the engine
    (`sdk.data_edit`: any finite number, D23; refused only where the
    cell's encoding can't hold it, D45) into the recipe's `xbr` `set`
    operations; a value set's editor (Step 4.24b, Modkit's Step 2.100) is
    a dropdown that greys what the cell can't take yet, a word list's a
    checklist capped at `max_words`, each grey the engine's
    (`sdk.data_edit`'s `texts`: `tools.data.needs`, a new string or a
    clear edit); the Critters and Items pickers show each one's body in
    the Characters tab's shipped picture (the index's `body`). The tab
    keeps the edits (Undo, Redo, Revert, Reset table, Clear edits), and the
    page builds with them (after the packs), remembers and links them
    (`state.xbr`; the Patches tab's line names them); ⚠ marks a cell
    a ticked pack's slider also writes (`sdk._written`: each config.xbr
    slider's spans as a build plans them; a pack a build would refuse
    marks none). The tab asks again each time it shows, so the marks
    follow the ticks; its line says the edits wait for the image to build
    (D979). **All files…** (Step 4.6h, Modkit's) under All tables' list:
    every .xbr of the picked image (`sdk.data`'s `files`, its release's
    manifest once the image is checked), each row opening to its keyed
    tables (`tables`: config.xbr's from the shipped file, another's read
    from the image no further than its TOC; no vanilla file but config.xbr
    has any), greyed with its line until an image (D979); another file's
    table shows and edits as config.xbr's (its asks carry the image: the
    app's path, the site's File mounted). `tests/test_data.py`,
    `test_site.py` and `test_hosts.py` hold it; `tests/_perf.py`'s A39-A46,
    A94, A120, A121, S32-S39, S80, S120 and S121 time it.
  - **The Tools tab** (Step 4.7c, `web/tools.mjs`; D919's list): **your
    image** (`sdk.image_info`: its release, size and kind, vanilla with how
    much of it the gate checked, an AzurKit build with its version and
    layers, or modded with its first file that differs), **Verify every
    file** (`sdk.verify_all`: the build files' check `sdk._stamp` keeps is
    reused, `gate.verify(kept=)`, so only the rest is hashed, on the app's
    threads or in the site's worker's WebCrypto, `sdk.layout(whole=True)`;
    the stamp is then whole, so asked again it hashes nothing; a vanilla
    image only; its bar the bottom bar's), its **files** (`sdk.files`, each
    with its offset) with a name filter and **Extract** (the site downloads
    a slice of the player's own File; the app's `sdk.extract` writes a part
    file renamed into place, never over the image it reads or a vanilla
    image, D36), then, needing no image, **Open a build…** (any AzurKit
    build's recipe, `sdk.open_build` of the files it changed: Load it, Save
    its mods file, and a randomized one's Track this build, greyed with why
    for one that isn't), **mods files** (`sdk.mods_file`: Load reads one as a
    link's preset is checked, keeping a `replace_bytes`; Save writes the
    page's recipe), **a plan file's spoiler** (`sdk.spoiler`; the app's
    engine process makes it, its randomizer logic read as the tab opens,
    `sdk.randomizer_logic`; the bar counts the logic's checks while it is
    read cold, then the spoiler's stage; the logic's first read in a
    launch is D1008's first-time work, so A54 and S47 are bar ops) and **the last build's
    report** (View, Save),
    and **AzurKit's storage** with Clear: the site's own named
    localStorage keys and IndexedDB databases (`tools.mjs`'s `KEPT`), the
    app's named entries (`app.kept()`: its config, the stamps, the swap's
    answers, the installed content), removed file by file, never an
    `.iso` or `.xiso` and never the folder that may hold one (SEC-10: on
    macOS the config's folder is the user data folder, where an image may
    be kept), a file it can't remove left and the rest removed; the engine's
    process, then the server's, first drop the swap answers their writers
    hold unwritten (`swapcache.clear`), so none lands after. What waits for an image is greyed with "Choose your image
    first (1.)" until one is picked, or with the engine's refusal of it
    (D979). The app's saves without a dialog go to the Downloads folder,
    through `writable` (SEC-16); a build's image is suggested in Downloads'
    `AzurKit` folder where D36 refuses Downloads (`_suggested`). `tests/test_site.py`, `test_hosts.py` and
    `test_edits.py` hold it; `tests/_perf.py`'s A47-A55 and S40-S48 time it.
    **Replace files** (Step 4.7d, `web/replace.mjs`, `edits/files.py`): a
    file from the computer stands in for one of the image's, whole, in one
    layer after every other (a group it shadows is a D28 conflict, named). A
    recipe, a build and a mods file name it by path, sha256 and size
    (`files`, read back by `read_mods` and `open_build`), never its bytes or
    where it was, and a share link refuses it by name (Q174); a recipe that
    names one builds only once it is picked again, nothing read until then
    (SEC-11). The bytes reach a build outside the recipe: `sdk.image`'s
    `picked` and, on the site, `hashed` (the worker reads the File and hashes
    it in WebCrypto for each build); the app holds the computer path the
    player picked (`api/replace`: a share or device path refused before
    anything opens), by its own record (`Server._held`), and its engine reads
    it per job. A build reads no vanilla bytes of a file only Replace files
    writes (`edits.manifest.staged`). `azurkit build --file PATH=FILE`
    builds one. `tests/_perf.py`'s A62-A63 and S54-S55 time it.
    **Saves** (Step 4.7e, `web/saves.mjs`, `tools/saves/session.py`,
    `sdk.saves`, `api/saves`; `azurkit save inspect|edit`): a slot's folder or
    an xemu HDD image's slots read-only, a text save's lines edited, the slot
    signed again with the player's BIOS files (bytes for that one ask, the
    key dropped with it, refused by size before a scan) and the game's half
    from the picked image's XBE, greyed until one is picked (D979), saved as a
    new folder (the app) or a zip (the site). What is open lives in the
    engine's process: a site worker replaced after a build asks to open it
    again, by name. `tests/test_saves.py`, `test_hosts.py` and `test_site.py`
    hold it; `tests/_perf.py`'s A64-A66 and S56-S58 time it on synthetic slots
    (signing's share is by hand: no fixture holds BIOS files).
  - **Share links** (WEB §4.1): Copy link asks the engine for
    `sdk.preset_encode`'s `#p=` fragment of the page's ticks, sliders, a
    loaded recipe's config.xbr cells and, ticked, the randomizer's seed,
    settings and cost (with the build's hashes when it is current), after
    the site's address (the app's `host.json` names the site's, D884). A
    page opened with one loads it once its engine is ready
    (`sdk.preset_decode`): exactly its packs ticked, its sliders set, its
    randomizer (Randomize ticked or not), each tick and value it changed
    marked ●, and no build; a build's recipe loads its randomizer the same
    way, from its share string. Ticking a pack ticks the packs it
    requires; unticking one unticks those that require it, each move said
    beside its group.
  - **An AzurKit build as the image:** the engine's vanilla read (the
    site's worker, the app's `api/vanilla`) falls back to
    `sdk.open_build(whole=False)` (only the files the build changed are
    checked: reading all 2.6 GB takes minutes in WebKit's worker), and the
    page shows "◆ AzurKit build" with Load its recipe, which loads it as a
    link's, to build again from a vanilla image.
  - **The remembered setup** (D915, D1156): each visit starts at the
    defaults unless Remember settings (in the bottom bar after Reset to
    defaults, off by default) is ticked. The choice itself is kept (the
    site's `azurkit.remember`; the app's `host.json` `remember`, sent with
    each `api/setup`), and unticking forgets the kept setup at once; a
    setup kept with no choice (AzurKit 1.0's) is removed unread on the
    first visit. The theme, the tracker's plan and marks, installed content
    and the caches stay kept whatever the box says. Ticked, the page keeps
    its ticks, each
    setting that differs from its default (an unticked pack's too) and a
    loaded recipe's config.xbr `set` cells, `{"ticked", "values", "xbr"}`:
    names and numbers, never the image, its path or anything read from it.
    The site keeps it in the browser's storage (`azurkit.setup`), the
    app in its config (`host.json`'s `setup`; `api/setup` refuses by name a
    setup with anything else: a pack or setting name that isn't an
    identifier, a path say, or a `replace_bytes`; a `set`'s names and text
    value are free strings that only `xbr.normalize` checks); at the defaults
    nothing is kept. A page opens with it before an image is
    picked, through `sdk.restore` (the site's worker, the app's
    `api/restore`), which leaves out and names in the status line what no
    longer normalizes (a pack renamed or retired, a setting gone, a value
    refused, a pack without one it requires); the page is ready once it is
    back. A share link or Load its recipe wins and becomes the remembered
    setup; once the page changes, its address drops the link's `#p=`.
    Reset to defaults, in the bottom bar (off at the defaults), ticks the
    packs on by default, sets every setting to its default and forgets it,
    leaving Remember settings as it is.
- **The site** is the page with Pyodide's core (and numpy's wheel, which the
  Characters tab's drawing loads: `web_tools.PACKAGES`), the wheel (with each module's
  unchecked-hash bytecode, so Pyodide doesn't compile the source, and the
  shipped database) and its `host.json` (`uv run --locked python scripts/web_tools.py --site DIR`). Its
  engine runs the wheel, unpacked without its dependencies, under Pyodide in
  module workers started from a `blob:` URL (so the page's CSP holds there),
  two of them (`web/workers.mjs`, Step 4.3r4l; D1006, D1007): F answers the
  page's asks and B works ahead on what the page lists (`aheadOnSite`: the
  typed seed's plan and first view, the settled recipe's build; never a reshape,
  which takes minutes and whose heap a change's terminate() would leave resident
  in WebKit), each key the recipe, the File by identity, what this browser keeps
  installed and the engine's version; a change drops B's job by `terminate()` (a
  heavy one goes on, unkept, while the list holds no heavy job, a reshape's, or,
  from a change of the Characters tab's own that comes `REST` or more after the
  list's last, until a pick, a Build or a Track, so its heap is the next heavy
  job's, not resident beside it; one listed sooner, a size changed a second
  after the pick, is dropped: young, its heap is small, and the change's build
  starts at once for a Build at its head start, 0.8-1.1 s at the click in
  capped WebKit where letting it go on took 2.9 s at no lower peak, Step
  4.53b; and a change of
  the Characters tab's own, a number, an option or Reset, that follows
  another within `REST` (7 s), no Build or Track between, lists its build
  with that rest before B starts it, where one alone and a pick start as any
  change, so a Build at its head start finds its build under way (`S72`): a
  slider's session of moves, a pause, a drag and Reset dropped a build ahead
  at each move, its heap resident beside the next B's, 7.2-7.4 GiB in WebKit,
  Step 4.4ci48, and a pause past `REST` started a build the next move
  dropped, 6.5 GiB, until that move let it go on, Step 4.53b), a
  click matching its finished job takes its answer and one it is still working on
  follows its records. One heavy job at a time, none of B's beside F's build. One
  heap (w-reshape): a worker a job grew stays for the next heavy job (wasm memory
  never shrinks, and WebKit keeps a terminated worker's pages resident) until its
  heap reaches 3 GiB after a job (`GROWN`; else as after a cancel, "Preparing the
  engine…", replaced, by an idle small B at once; a new F that doesn't
  load loads again, its queue waiting, as a B does, until `LOADS` loads of
  the visit failed, where one failure left the visit with no engine,
  Step 4.46c), answers as F whenever both
  are idle, and no heavy job starts beside it. A reshape's exact pictures (D1011)
  are a heavy ask too, so they run in the worker the page grew, never in one of
  their own beside it (D1054: WebKit's own peak was 7.7-8.5 GiB so), the page's
  small asks answered by B meanwhile, and the engine keeps the last reshape's
  size and dress (`sdk._reshape_kept`, no seed), so its pictures and its build
  make one dress between them, whichever comes first (in the app, where they
  can run at once, the second waits on the first's dress). A character's build writes its pieces into an OPFS file of its
  own (`web/outputs.mjs`, P7, X10): a Web Lock per file, shared by the worker and
  the page; removed only unlocked, at a build's forget (30 minutes past its Save,
  whose end a page can't see) or a page's load (a crashed page's); the Tools
  tab's Storage counts them; where OPFS refuses, Blobs. Each later worker
  starts from Pyodide's memory snapshot, which the first worker of a wheel
  makes once the engine's modules are imported (no numpy, no image) and the
  browser keeps (IndexedDB, by Pyodide's version and the wheel's integrity;
  one record of its heap and size, any other refused by name and replaced; any fault starts it cold, and
  its `ready` says which start it was and why it was cold), which reads the
  image in blocks (WebKit takes about 200 ms for each read of a File,
  whatever its size), kept from one message to the next for the last image,
  its folders' tables read ahead in awaited rounds before the engine's first
  walk (one round from `web/tables.json` on a release's root; a hint: the engine still reads and checks every byte),
  and checks each image once (Step 4.3h): its build files hashed
  in WebCrypto (`sdk.layout`, `sdk.prime`), the stamp kept in the browser
  (IndexedDB, by the File's name, size and lastModified) for the next
  visit, and a character's dress too (D1067: `characters.CACHE` is the
  worker's `Kept`, IndexedDB's `azurkit-dress` by the build's hint, the
  last 32; taken only under the engine's own key), and a Check's dress's
  parts (Step 4.6o: `parts.STORE` is the worker's `Parts`, IndexedDB's
  `azurkit-parts` through `web/parts.mjs`, each part once by its key and each hint's keys, the
  hint the image and the Check's recipe with its name, folder, labels and
  sounds left out (a built-in's its name), the last 8 hints and the parts
  they list; offered with the Check, each let go of as it is taken, and
  those it took (from the page or, `parts.STORE.used`, the worker's memory)
  and worked out kept after its answer, a refusal's too). A build's changed files are hashed there too (`sdk.image_staged`,
  `edits.staged`), one at a time, each handed over only for its digest. It posts its start's steps, a kept image's walk and a build's, a
  plan's and a tracker's stages as `core/progress.py`'s record, a Check's four keeping steps after its answer
  (its parts and its dress, each worked out, then written to IndexedDB) and its pictures each as it starts, since a
  Check asked meanwhile waits behind them (in the pool's queue for that worker, behind the pictures it holds), and its
  bar moves with them (Step 4.54e: S79), and each build's answer reports the heap,
  by which the pool keeps the worker or replaces it. A worker whose engine's wasm traps (Pyodide's fatal error: each
  later call of it fails) says so in each failure it posts (a tab's ask's too, whose other failures are refusals),
  naming the call and Python's innermost frames, and the pool replaces it at once, its job or none, and sends the page's job to the next engine once, the page saying so
  (D1126: the arm64 WebKit golden's trap, whose cause isn't found; `TRAPS` a visit). A shared message's
  untrapped failure (the warm-up's, the content's, the library's) says so (`shared`): the page is told and no ask
  ends with it (Step 4.46c: it ended the job sent next and replaced F). It joins the Blob itself, off the page's main thread, and returns the build
  as segments
  (`iso.Image.segments`), which the page joins into a Blob of slices of the
  player's file and the bytes the build writes (Blobs from the worker on, so
  the page holds none of them; a character's go into its build file straight
  from the engine's heap, `placed`, as a copy in the worker's JS stays until a
  GC, which a worker building again at once doesn't get: 4.3r4s, and with no
  build file each Blob is made from the heap too, its one copy), and Save
  downloads it.
  - **A seed's build is sparse on both hosts:** its base holds each level as
    an `iso.View` of its TOC and node sections (`generator.sections`, but a
    file another layer reads, whole), carried as patches to the image, and
    `generator.read_back`'s `sparse` reads those back through the image
    (D35), never from the patches. The site's worker asks for what it reads
    first, in two awaited rounds (`sdk.image_staged`'s `ahead`:
    `generator.heads`, `generator.pages`; 90 late pages would cost Safari
    18 s; `PAGES` holds them with the tables), and reads each level with its
    patches over it for its sha256 in WebCrypto and its md5 in wasm
    (`web/hasher.mjs`; `web/md5.wasm`, `python -m nativekit`'s, from
    `native/web/md5.c`). The app hashes on its threads.
  - **Its Save is checked (D35):** while the browser writes the Blob, the
    page hashes the same Blob's files against the build's
    (`sdk.image_checks`: its result, else the release's manifest), its bar
    moving. A File changed on disk since the pick fails the read in WebKit
    and Chromium, and reads otherwise in Firefox, silently, before the build
    as after it, so there the File's copy of each file the build changed is
    first hashed against the manifest (everywhere, S50/lag would be 4.1 s).
    The Save fails with what to do, as a page can't stop a browser's download.
  - **Its Blob in Firefox is few parts:** a blob: URL of a Blob of over about
    8 parts, or with a part of 1 MiB in memory, makes Firefox's parent copy
    the whole image into memory at once and hold about 2 GiB more over its
    download; of few parts, each a file's slice, it reads by reference. So
    after a build the three longest copies stay the File's slices and all
    between them goes into a build file of its own, the same bytes, ahead of
    the Save (app.mjs's `byReference`; `web/flat.mjs`, a worker writing it
    through a sync access handle, 3.7x less CPU than a `Response.blob()` of
    them, Step 4.5q), held and removed with its build as a character's is.
    While it is made Save stays greyed with its own moving bar (R14 and R24
    end when it opens), so a click never waits for it and a Save's page part
    stays the click's (D1053); the worker's records never land on the page's
    own waits. A test clicks Save once it opens (`_page.built`): a click on
    the greyed Save does nothing (Step 4.5u). A private window has no private
    file system (and its `Response.blob()` stays in memory, its tree higher
    than the plain Blob's), so one, told by that file system refusing it,
    keeps the plain Blob and its parent's copy. Where the writer fails (a
    full disk's quota, a refused handle, its worker stopped, each reported
    to the page) the bytes go into a `Response.blob()` as before 4.5q, so
    Save always opens (Step 4.5u).
  - **No stream through `sw.js`** (D1049, D1053; Step 4.3r4p's W-SAVE,
    keylord's and a seed's Save, three each, the Blob against the build's
    Blob streamed by `sw.js` to a hidden frame's download, its last bytes
    held for the check): the stream was neither faster nor lighter in any
    browser, so the Blob stays in all three: Chromium 2.5-2.7 s against
    2.1, the seed's tree 4.0 GiB against 3.1; Firefox 5.7-6.8 s against
    3.0-3.6, its tree 8-26 GiB, growing each Save, against 3.5-4.7;
    WebKit within the spread (1.5-2.0 s medians, a 2.5 s sample in each,
    3.8-4.8 GiB both), one page part 1.01 s.
  `tests/test_hosts.py` runs the gate under Pyodide on Node, and
  `tests/test_site.py` the packs' G1 cases and a save in Chromium, WebKit
  and Firefox.
  - The worker holds one PyProxy, its engine function, which hands back
    plain JS values: a PyProxy it dropped would be freed by Pyodide's
    FinalizationRegistry, which needs the GIL, and WebKit runs that cleanup
    inside WORKERFS's read of the image, where CPython has released the GIL
    (`NoGilError`, Step 4.1d3).
  - **The service worker** (D1013, Steps 4.3z and 4.3r4p; `web/sw.js`,
    which the site's page registers once its engine is first ready,
    `app.mjs`'s `registered()`; its `main()` stops only under a service
    worker that isn't the site's own `sw.js`): a first visit never waits
    for it (it runs uncontrolled, as before, while the release is kept;
    holding it for the install and a reload cost S01 0.5-0.97 s in every
    profile, 4.3r4p's x6b/x6c), and each later page comes from the release
    at once, cross-origin isolated (no service worker, as in a private
    window, or a refusal: uncontrolled, as before); a
    controlled page starts its workers (the engine's, a dress's, the hash's)
    from their own URLs, as Firefox sends a blob: worker's imports past the
    worker, shows "An update is ready: Reload" when the next release waits
    and asks for one every half hour; the Tools tab's Storage counts the
    release kept and Clear deletes it and unregisters `sw.js` (the page
    runs on, each file it asks for kept again, checked; the next load is
    the network's release, registered anew: kept, it came from the cleared
    release's `sw.js`, which answers 503 to each file of a release deployed
    since, and no reload mended it), but while another page `sw.js`
    controls is open (its `release` answer's `controls`) Clear keeps the
    release and says so: Chromium hands the registration it keeps for that
    page back to the reloaded page's `register()`, the cleared `sw.js` with
    it (the 4.46c review's F2). Another origin's content (the community
    source on raw.githubusercontent.com) is a CORS fetch, which
    cross-origin isolation allows as its host sends
    `Access-Control-Allow-Origin: *`; sw.js handles only its own scope's
    requests. `tests/test_site.py`'s pages block it (routing never sees a
    worker's requests). `site()` writes the release
    into it
    (`web_tools.release`: each file the site serves but `sw.js`,
    `.nojekyll` and `content-source/`, with its sha256 and size; the
    page's CSP, from `index.html`'s meta; a name its files decide). It
    keeps that release whole in one cache (`azurkit:<scope>:<name>`), each
    file checked against its sha256 as it is downloaded (one an older
    release's cache holds with the same bytes is copied, so an update
    downloads what changed; one that differs fails the install, and the
    release before stays), serves the page, its modules and its engine
    from it (a page never runs another release's engine, and needs no
    network once kept; a file cleared from it is downloaded again only if
    it is the release's, else answered 503), keeps each file with COOP,
    COEP, CORP and the page's CSP and answers with it as kept, never
    rewrapped, so the browser reads it from the cache itself (Chromium's
    return visit, S02, 0.14 s faster), adds them to the network's other
    answers, and holds an update until the page takes it (`reload`,
    refused while another of the site's pages is open). An install posts
    its outcome (`installed`, `failed`) to the site's pages; the first
    takes over at once; an activation deletes the scope's older releases'
    caches. `tests/test_service_worker.py` holds it in the
    three browsers on small sites `site()` writes and on the site itself.
- **The app** (D732) is `python -m azurkit` (`src/azurkit/__main__.py`): with
  no arguments the page in a pywebview window, else in the default browser;
  `serve` serves it without opening either (the tests' way in); any other
  arguments are the `azurkit` command. `azurkit.app` serves the page on
  127.0.0.1 to this launch's token only, and is its engine: `host.json`
  and JSON calls (`api/build`, `api/save`, ...) that run `azurkit.sdk` on
  CPython, only from the page's own origin. Its builds, saves, a seed's
  plan and the Characters tab's pictures and G4 match run in the app's
  engine process (`azurkit.app.engine.Spawned`, spawned, each call on a
  thread of its own), so the server's other answers never wait on a build;
  a save cancels itself at its next chunk. Work ahead (`azurkit.app.ahead`,
  D1007): the page's settled setup is built, its typed seed planned and that
  plan's first tracker view read before their clicks (`api/speculate`,
  `api/prefetch`; while the engine plans, the server compiles what that view
  reaches under on its own Logic, `tracking.ahead`, once a call has read it and
  while no other call or build ahead runs), each keyed by its recipe, the
  image's stamp, the content's
  `installed.json` and the version, at the page's change number, at background
  priority (with its pool parts, the threads it starts and `sdk.py`'s hash pools)
  and waiting at its records behind a call the player waits on, but for a
  seed's fill, which such a call may wait on: that comes up to normal priority
  at its records meanwhile, as a build's hash does once a Save waits on it; a
  change, or a preview or G4 match beside a build ahead (no dress runs beside
  its GiBs: D1017), stops it at its next record, Build, Track and the tracker's first ask
  take it (a repeated Build of one recipe too), and Cancel answers at once,
  the build's job going on through a seed's fill, so the engine, its Logic and
  the fill stay for the next Build. A job quiet past `ahead.GRACE` kills that
  process, unless a save runs, and the next starts: a call the player waits
  on runs again. A build's dress notes nothing (`sdk.image` holds no
  `noting` round it, `pool.each`'s notes and the serial stages' reach
  `sdk.match`'s dress alone), so a stale first dress caught in a gap of its
  records (26-30 s) takes that kill, and the next seed's click reads the
  logic again (a known flaw, measured at 45 s). A build keeps its image in
  that process (the
  last build's: a new Build drops it), hashed on a thread from the moment
  it is made (`iso.digest`), and `api/build` answers its id: Save sends it
  back, so `api/save` writes that image (`sdk.save`, the hash taken or
  waited on), or builds the recipe again (`sdk.build`) when the engine keeps
  it no more (a kill's new process) or its input changed. `main()`
  keeps, in its process and its engine's (`Spawned(stores=True)`), what
  they work out across launches (`azurkit.app.swapcache`, in platformdirs'
  cache folder): the images the gate vouched for (`gate.STAMPS`,
  `stamps.json`) and the store's kinds (`swapcache.Kept`, one folder a
  kind beside it, every kind's least recently used removed past the store's
  one budget): the swap's answers (`characters.CACHE`, `swap/`), with a
  character's pictures and G4 match under the swap's key
  (`characters.cache_key`, the packs as asked), each entry and the stamps
  signed (an HMAC-SHA256 under the install's own key, `cache.key` in the
  user data folder, mode 0600): a file not this install's, a shared cache's
  too, is a miss and never unpickled (SEC-4), and 4.3i's `swap/*.pickle`
  are never read and are removed by the next write. A put is written behind
  the answer (one daemon writer thread a process: a get meanwhile answers
  from what it holds, a quit never waits on it, and a write it cuts short
  leaves only a part file, a miss), but an answer worked out for
  `swapcache.LONG` (10 s) or more, written before its call answers, so a
  quit right after a reshape's Built never loses its dress (Step 4.4bc);
  `serve()` and `Spawned()` keep nothing past their process. In-process `app.serve()` (the tests') runs
  them on the request's thread (`engine.Here`), so a test's stand-in sdk
  call takes. Where the tests set `AZURKIT_STACKS` (`azurkit._stacks`, the
  frozen app's sandbox: a player never does), the server, its engine and
  the pool's children each dump every thread's stack to a file of their own
  every 30 s (`faulthandler`, armed first thing in the frozen app's entry),
  so a served call that never answers fails naming where each process stood
  (Step 4.37i). `serve` reads its input on a descriptor of its own and
  leaves fd 0 holding NUL (on Windows the standard input its children take
  too) before any other thread starts: on Windows a read blocked on a pipe
  holds that pipe's locks, which held the engine at its start (Step 4.4ci5)
  and numpy's BLAS, whose Fortran runtime looks at fd 0 as its DLL loads on
  the request thread of a Build with a character (Step 4.37r). A script that calls `app.main` guards it with `if __name__ ==
  "__main__"` (spawn imports the main script again). The page takes the image's path
  (remembered in platformdirs' config folder; the window adds file dialogs)
  and Save writes the build to a path, never over an existing file but one
  the save dialog chose. Closing the app (the window's close button, Cmd-Q,
  `serve`'s input ending; the window asks first while the Variants view
  holds edits not saved) cancels a build or a save: it never waits on a
  build, and waits for a save to remove its part file `app.QUIT_WAIT`
  (1.5 s) at most, then removes it itself (AZ-823, D35). The window sets
  pywebview's `text_select`, or pywebview injects a `<style>` the CSP
  refuses. `scripts/freeze.py` builds
  the app (`AzurKit.app` on macOS, a windowed onedir; on Windows a windowed
  program too, so no console window opens beside it, and `__main__.settle`
  gives the streams Windows starts it without: a command's to the console
  of the terminal it was typed in, else `app.log` in the build logs' folder,
  with `faulthandler`'s stacks; with the shipped
  database, its key checked against the bundle's data); pyinstaller and
  pywebview are the `app` dependency group, never the wheel's. The bundle is
  read-only: every write goes through platformdirs, or to the path the
  player saves to. It carries no Unicorn, zig, capstone or GPL code;
  `tests/test_hosts.py` checks each name in it and its licence, and builds
  the packs' G1 cases and a save through its page (`AzurKit serve` in
  headless Chromium, WebKit and Firefox).
- **The icon** (D891, D892) is original art that code draws, no game pixel
  (D886, D890): in `assets/icon/`, `mark.py` draws the mark (`AzurKit.svg`)
  and `tile.py` sets it on the Mac app's azure tile; `render.py` writes
  those SVGs and renders the app's `AzurKit.icns` (`scripts/freeze.py`'s
  `--icon`) and the site's favicon, the free mark (`web/favicon.ico` and
  `favicon-32.png`, which the page links). All of them are committed;
  `tests/test_icon.py` holds the SVGs to their generators.

## Commits and landing

- **Lanes:** one lane per step, a worktree in `../AzurKit-lanes/<step>` on a
  `p2/<step>` branch. Lanes commit locally, and only the orchestrator moves
  `main`.
- **Commits:** a fix is one commit with its test. Name the step in the subject
  (`fix: … (Step 4.1c)`) and keep the body to a few lines. Stage explicit paths:
  never `git add -A` or `.`.
- **Protected paths:** a commit that changes one names each in its body, and
  why: `tests/goldens/` (only `scripts/record_goldens.py` writes it),
  the facts (`src/azurkit/core/facts.<release>.json`), the release
  manifests (`src/azurkit/core/manifests/`), the shim objects (only `python
  -m shimkit`) and `shimkit/`, the native libraries
  (`src/azurkit/core/_native/`, only `python -m nativekit`) and
  `nativekit/`, `tests/sdk_api.txt` (only
  `scripts/sdk_api.py`), `tests/skip_allowlist.toml`, `tests/conftest.py`,
  `tests/_*.py` (the leak guard among them), the drift guards' tables
  (`PROLOGUE_FIRST_BYTES`), `pyproject.toml`, `uv.lock`, `bootstrap.py`,
  `CLAUDE.md` and `.claude/`. Modkit's policy workflow (a pull request
  that changed one waited for a maintainer's `reviewed` label) has no twin
  (D1179, under D1171): it ran on `pull_request_target`, which no workflow
  here uses, stacks land through the queue after their review (D288), and each file a
  command writes is held to it by a test: the goldens by their families'
  (`tests/test_packs.py`, `test_characters.py`, `test_randomizer.py`,
  `test_builds.py`), the facts by `test_packs.py`'s gen_facts test, the
  manifests by `test_gate.py`'s, the shim objects by `test_shims.py`'s G2,
  the native libraries by `test_native.py`'s and `sdk_api.txt` by
  `test_contracts.py`'s (Step 4.24c).
- **Ids:** an AZ, D or Q id comes from the private ledger: `$EV/tools/ledger
  take AZ "slug: one line"` (`ledger next` prints the next free ones). Never
  write an id or the ledger's pointer by hand. A lane whose prompt says not
  to take ids reports the loose end instead.
- **Reviews by default (D288):** a correctness review after every code step
  and a skeptic after every xemu sitting; a tiny docs- or test-only change
  skips it, and so does a rebase whose only conflicts are docs, the ledger
  or goldens (D779). A step with a sitting runs its review beside the
  sitting, both on the build commit; the record re-runs the rows whose
  image a review fix changed (D778). A builder checks its own work first; a
  reviewer never edits.
- **Never:** attribution trailers, force-pushes, `--no-verify`, `git stash` or
  git config changes.
- **Change notes:** each change adds one Markdown bullet in a file of its
  own, `docs/devlog/<added|changed|removed|fixed>/<step>-<slug>.md` (ids
  welcome there: one bullet, its further lines indented two spaces, held
  once; the lint set checks each), which a release joins into
  `docs/DEVLOG.md` and deletes (`uv run --locked python scripts/devlog.py
  --release TITLE --remove`; with no option it prints the join); a change a player would notice
  also updates the guide's features (above), in plain words. `docs/DEVLOG.md`
  merges with git's union driver (`.gitattributes`), so lanes' bullets at a
  section's end never conflict; the lint set and `scripts/land.py` refuse a
  release that holds one bullet twice (`scripts/devlog.py`: the stale copy
  union keeps of a bullet its lane edited): keep the newer.
- **The gate:** run `uv run --locked python scripts/fullsuite.py <worktree>
  --changed`. It runs the lint files (the contracts, the leak guard and the
  agent files, whose scan of every tracked file for a home path reads
  whatever a change touches) in the foreground, then the changed area
  with them and the gate's USA and Europe test (or the whole suite) in the background
  under a lock, on 8 workers (pytest-xdist, `--dist loadgroup`), and prints a key and a receipt path. Its `plan()` picks the
  test files that import what changed (relative imports too, and a module
  run by its path, as `tests/_page.py` runs `tests/_static.py`); every change under `src/` adds the
  files that run the whole package (the wheel's, and those taking the
  `pyodide`, `browser` or `frozen_app` fixture), a change under `web/` the
  site's, the app's and the icon's (and one to `web/art/`, `web/characters/`
  or `web/md5.wasm` the test that holds those files to a fresh draw or
  build), `LICENSE` and `NOTICE.md` the About
  tab's test and the wheel's, `README.md` the wheel's, a change in
  `tests/goldens/`, `.github/`, `native/` or `src/azurkit/core/_native/` the test files that read it (read by path: those
  reaching a module that names the folder, `record_goldens.GOLDENS`),
  any other file that isn't Python (a shell script, `.gitattributes`, a
  package's data) the test files reaching a module whose strings, its
  docstrings aside, hold its file name as a word, and below the top level
  one naming its folder or sitting in it (`namers`: `scripts/ci_retry.sh`
  picks `test_contracts`), one under `devkit/<area>/` the test files
  reaching that package or a module naming its file name (`devkit/re/data/x.toml`: `devkit.re`'s and
  what names `x.toml`), other docs nothing more; the suite's
  configuration, what every session runs (conftest's and its plugins' top
  levels and hooks, and every module and function they import or name,
  however deep, and the files they name; not the app, whose no-window mode
  it checks in a Python of its own), a path no rule covers and no module
  names (a Python file outside the graph's folders, `PY_DIRS`, and the root
  is one) and a deleted module (not a test file) that no module still
  names (a rename is its old path deleted) run the whole suite. What only a conftest fixture's body runs (the
  `browser` fixture's close: `scripts/ci_resources.py`) picks the test files
  that take that fixture, and a change to such a module (conftest too) that
  only touches functions the session doesn't call picks those functions'
  module's importers and the takers of the fixtures that call them. A changed-area run drives the page in
  Chromium alone, the whole suite in every browser (D970), and the receipt
  says which (`browsers`). Once a changed-area run's tests pass, its flake
  stage (Step 4.4dx2) runs each test function the stack adds or edits (a
  `def test*` whose source differs from the base's; a helper's change adds
  none) 5 times, slowed toward CI's Intel runners' pace, on 3 workers, in
  every browser its parameters name (Step 4.4dx4); one that reaches no
  module- or session-scoped fixture of the suite's own (`browser`,
  `pyodide`, `frozen_app`, `site`, `shipped_database`...; `usa_iso` and
  `europe_iso`, a path each, aside) has its 5 in the first
  run's session, each a case `<id>[...-flake-run-K]` (the plugin
  `scripts/flake_repeat.py`'s `--flake-runs`, Step 4.4dx12), the others a
  session a run: on macOS each run under
  `taskpolicy -b` and nice 19 beside 4 busy loops at nice 10 when a CPU
  probe under it ends within 3 s (a quiet box), else under `taskpolicy -c
  utility` and nice 19 beside 12 busy loops of that class (on a busy box
  `taskpolicy -b` starves: past 900 s for builds of 8 s, false failures;
  the utility clamp doesn't starve, but reaches CI's Intel pace only near
  load 60: at load 43 its runs took 1.3 times the gate's); nice 19 and 4
  loops elsewhere. Nothing built once is built slowed: the
  gate's run and the stage share one build cache (`web_tools.CACHE`,
  `<meta>.cache`), so the stage copies the run's wheel and database. A
  failure fails the receipt with the test, the run and its output's tail;
  the stage's wall is 840 s: no run starts that its longest so far won't
  fit in, a run (or the stage's collection) still going at it is ended
  with every process under it, each case that run failed so far fails the
  receipt, and each case with no passing run by then fails it by name,
  capped (a case of an xdist group by its collected id, not its worker's
  `<id>@group`); past 20 tests each runs once (the block says so); the receipt's
  `flake` block keeps the tests, runs, each run's wall time and slowing;
  `land.py` needs it passed. A whole run has none. In the run and the stage
  a failed test gets its one rerun (D1170): one that passes it is kept in the
  receipt's `flakes` and appended to `flakes.jsonl` beside the receipts. A
  run is killed past its cap, 1,800 s, scaled by the host's load per CPU up to twice that, and its log
  ends with the slowest tests. `--wait 540` waits for the result; exit 3 means
  it is still running, so issue the same command again. A queued run checks
  its worktree's HEAD and tree (the diff and untracked files its key hashed)
  again when the lock comes: one that moved while it waited (the landing
  queue rebased the lane) ends `stale`, no pytest run and exit 1, its note
  naming the command to run again (Step 4.43a).
- **The perf gate (D980-D985):** once pytest passes, the same locked run times
  the player-facing operations the changes reach (`scripts/perf.py`; the
  registry, its ids and drivers in `tests/_perf.py`): a change under `src/`
  or `web/` times its area's ops (`perf.REACH`, each narrow row standing on
  what loads its path: `_stacks.py` the app's alone; the Tracker's modules
  and `web/art/` start, image, randomizer and tracker; `parts.mjs` the site's
  start and characters, Step 4.43a; the app's, the randomizer's and the
  characters' rows as before; any other path under `src/` or `web/`, and
  the perf gate's own driver and judge, `tests/_perf.py`, `tests/_page.py`
  and `scripts/perf.py`, every op, Step 4.46a) in the app's serve mode (the worktree's wheel in a scratch venv, so
  the app reads the database the wheel ships, as a player's install does) and on the site in WebKit, and main's own full
  run times every op in four profiles (the app; the site in WebKit, Chromium
  and Firefox; the site with each File read 200 ms late,
  Safari's; capped, `AZURKIT_CORES=4` against 9 s with a 6 GiB memory peak: the
  app's process tree, and the WebKit processes launchd starts for the run's own
  browser (`launchctl print pid/N` holds the mark the run put in its PATH;
  another seat's isn't counted, one launchctl can't say about is);
  the 4-core / 8 GB computer AzurKit must run well on, D1017; Firefox's run
  logs its tree's peak in the block's `tree_peaks`, and no verdict reads it). The rule and its
  gate hold on this Mac alone; the other platforms are timed later (D1023).
  It starts once the normal-priority load is under 40, at nice 10. The
  clock is the click's (D1006): a Track or Build after a change the player
  makes (a typed seed, the Randomize tick, an image pick, a model's pick, a
  slider) is clicked 3 s after it (D1014's head start, `_perf.HEAD_START`), never
  after a Cancel, a launch, a reopen or a tab's open; work done ahead is
  free only while the page never freezes, so the page's freeze probe (a
  50 ms timer) marks a sample whose page froze over 250 ms in a gap between
  actions (a head start, a dialog's wait, the warm-up's; `froze`), naming
  the CPU the browser's processes used in that gap (a busy page told from
  one its machine kept from running), and logs the
  lateness inside an action's own wait. The site's samples each take a
  persistent browser context on a new folder, with the storage a player's
  browser has; a later visit (`S02`, `S64`) opens in that browser closed and
  opened again on the folder, as WebKit keeps a closed page's process, all it
  held resident, for the site's service worker while a page of the site is
  open (Step 4.4m). An op
  runs three times (once past 30 s) and its median decides, but a changed
  area's run times it once and the rest only when that sample is at or past
  1 s or froze (`perf.alone`, D1215: the block's `one_sample` names the cases
  one sample judged; main's every-op run keeps three). Timings are
  advisory (D1170): an op over its tier's line (3 s, a rare op's 10 s: the
  tiers, below; or over its ceiling in `tests/perf_ceilings.toml`), a heavy
  op past its bound (`beyond`), past 1 s with no progress, or whose page
  froze in a gap is a perf-debt row (the block's `debt`, printed and appended to
  `perf-debt.jsonl` beside the receipts; a Save's row carries the free disk),
  a lane, not a block, and so is an op the last release never measured that
  errs, its error the row's reason. The block fails only on a clear
  regression against the last release (`perf.blocking`): an op's median over
  its line (a frequent op's 3 s, strict on how optimized it is; a rare op's
  10 s, a heavy one's bound) and over the last release's run's for the same
  op and context
  (`fullsuite.release_reference`: the newest receipt with verdicts on the
  newest `v*` tag's commit the stack holds, a run of every op first, else
  the release's before; `perf.py --reference`) by more than 25 % and 0.5 s
  (`perf.REGRESSION`, `REGRESSION_S`), taken three more times first, or an op
  that run measured that errs; and on a memory peak, a native failure or a
  list that grows, as before. That verdict compares like with like (Step
  4.47d): a page's first Check is cold and a later one warm, so the driver
  tags each sample with its place (`first_on_page`: its op's first on its
  site page or app run, or a later one there), and each place's median is
  held to the release's same place (`perf.reference_of` reads a release
  whose samples carry no tag as it took them: three to a page, the first
  there first, an op of fresh states each on its own page); an op is
  `slower` when one place is, so a changed area's samples, spread over more
  pages than the release's, never read as a regression, and a cold or a warm
  path that really slowed still does. Its three more samples then go on, a
  page at a time, until each place holds three. The release's tree beside
  (Step 4.47e): an op that reads slower than that receipt has the release's
  own commit (the receipt's `head`, a `git archive` of its `src`, `web`,
  lock and `scripts/web_tools.py`, its wheel, site and app built by that
  `web_tools.py`, as the release built them, so a lane's change there is
  timed on the head's side alone; Pyodide's core and the browsers from the
  worktree's `.tools`) timed beside it in
  the same stage instead, page for page, the two sides alternating
  (`perf.pair`): three pages a side (an op of fresh states one sample a
  page, one repeated in one state a first and its later ones, one past 30 s
  one page), and three more for one still slower. Its regression verdict
  then holds the head's samples taken there to the release's taken there,
  place by place, by the same line (the case's `beside`); the receipt's
  verdict stands where the release's tree can't be built or driven. Each
  tree installs the content its own CI pins (Step 4.54c: its `tests.yml`'s
  `CONTENT_COMMIT`, else the content clone's newest commit at that tree's
  commit's date), unpacked by `git archive` from the clone beside the
  checkout (a commit it lacks fetched into a scratch repository of its own)
  and never its working tree, so a release whose built-in booblord isn't
  the content's isn't handed one it refuses; `--content` is the head's
  alone. The release's site checks its content with perf.py's engine, the
  head's, so it is built with no built-in recipe read
  (`content.builtin_refusal` off; its own page refuses at Install). A busy
  box moves within an hour (a Save's sample is the browser's write of a
  2.8 GB download, a Check's the cores a nice-10 process gets: the release's
  own tree read 1.5-2.6x its receipt's Saves on 11-12), so only the release
  timed in the same minutes tells a slower product from a busier box. An image's first check and the site's first engine load may pass
  3 s only with a moving bar (D982), and so may a character's first build
  in a browser (`S14`, D1067; the same build at a later visit, over its
  kept dress, `S64`, may not), and a heavy op its tier's line, past which
  it answers to its bound (the tiers, below); past 1 s an op shows progress
  unless the
  list names it a debt (D980). A download (the registry's `browser_bar`: the
  browser writes the file the page handed it, and its download indicator
  shows that) shows it when each sample's page part, the click to the
  download's start, is within 1 s or moves the page's own bar; the receipt's
  case keeps those seconds, and the whole still answers to 3 s, but Firefox's,
  which passes on that moving bar (D1053). Each page's
  engine reports its compiled kernels (`sdk.catalog`'s `native`): a run
  whose engine answers without the library the worktree ships for its
  host (this machine's, the site's side module), loaded, with those bytes'
  sha256[:12], fails, its ops with it, so the Python twins' times never
  become a ceiling; so does one whose twin answered any reach call beside
  the library (`native.report`'s `calls`, read as each page leaves: the
  app's engine process hands its counts to the server with each answer, a
  site's worker to the page). A sample past 1 s whose wall passes 1.3x the CPU seconds
  its tree used (each process's highest figure, so a child gone mid-op
  keeps its own) waited for a core: it stands as it was taken, with its tag
  (`starved`, `perf.judge` names it), and counts in its op's verdict as any
  other, never taken again or discounted (D1107, Step 4.46a); the lag run,
  whose reads wait by design, has no CPU figure. Each call the driver makes
  to a page, a context or a browser is bounded (`_perf.bounded`, through
  `_page.within`): an evaluate, a page's opening and close in `_page.STALL`
  (a wait's poll in what is left of its timeout and that), a load in
  Playwright's own 30 s, a download's write in its wait's own timeout. Past
  it, or at once as WebKit's log names a page's process it ended, the pass
  stops: its ops' error names the call, the ending's `reason=`, the run's
  WebKit processes (launchd's, outside the driver's tree) and whether its
  browser still answers, the whole failure is in the run's log, and the run
  goes on (Step 4.37s: WebKit ended its pages' processes as its GPU process
  stopped answering three times in 30 s, under an evaluate that had no
  bound, which held the perf stage and the suite lock 1 h 43 min). The list only shrinks: `perf.py
  --update-ceilings` lowers a ceiling you earned (in your own commit) and
  drops what is back under, and the gate and `land.py` fail an added op or
  debt or a raised ceiling against main's, but for a browser main's
  `perf.py` doesn't time yet (`perf.new_browsers`), whose first record
  (`--update-ceilings`, its ops as measured) may add its own ops and debts
  once (it lands a stack after the one that put `new_browsers` on main: the
  landing queue lands with main's `land.py`). A line rises only for a rare
  op, once, by the owner's tiering: both fail a stack that moves an op
  main's registry holds frequent to the rare tier, drops a heavy op's
  `heavy` (its bound), marks `heavy` an op main's registry holds plain (a
  frequent one's 3 s would become 15 s and 30 s past a moving bar), raises
  a line (the capped profile's too, which a lowered `BUDGET` raises) or
  loses the registry's tiers
  (`perf.check_tiers`, reading main's `tests/_perf.py` and `perf.py` with
  `ast`), but against a main whose registry has no tiers, the first record
  (D1244's, Step 4.49a). A new op may start at either tier, a heavy one
  only frequent (its rare bound is the owner's call).
- **The tiers (D1244):** "frequently used parts of the tool need to be
  strict about timing and how optimized they are", rarely used ones may be
  looser. Each registry op has a tier (`_perf.Op.tier`, `_perf.TIERS`):
  frequent, what a player meets every session, often or once (a launch, a
  first visit, the image's check), and every response to a drag, a
  keystroke or a pick inside an open view, wherever it sits; or rare, a
  part of the tool few players open or a one-off act inside it. A heavy op
  (`_perf.Op.heavy`, each a bar op) is a dress's work the page asks for: a
  Check, or a new shape's first build or pictures (D999). Its lines
  (`perf.BUDGET`, `RARE`, `HEAVY`; `perf.tiered` picks each op's):

  | Kind | Frequent | Rare |
  |---|---|---|
  | An op | 3 s (D981) | 10 s |
  | A heavy op (frequent: A92, A99, A104, A105, S78, S85, S86, S87; rare: A31, A60, A95, A98, A106, S52, S62, S63, S81, S84, S88) | a moving bar past 3 s; 15 s in the app, 30 s in each browser (D1194) | a moving bar past 10 s; 45 s in the app, 90 s in each browser (D1244's most) |
  | A first-time op (D982, D1008, D1067) | a moving bar past 3 s, no bound | the same |

  The capped profile answers to three times each line (D984), the lag
  profile to the browsers'; the app's heavy lines are half the browsers'
  (D1194's "well under"). Every tier keeps D980's progress past 1 s, the
  freeze probe and the 6 GiB memory line. The rare ops, by the part of the
  tool they sit in (`tests/test_dev_tools.py` holds this table to the
  registry):

  | Rare ops | Why rare |
  |---|---|
  | A97, S83 | Open a plan… on the Randomizer tab, a one-off act |
  | A31, A32, A60, A61, S52, S53, S62, S63, S65 | a reshape on the Characters tab (D999's sliders): its first build and exact pictures, and the same reshape again |
  | S13 | installing a community character |
  | A33, A34, A35, A36, S26, S27, S28, S29 | the Patches tab's community packs |
  | A90, A91, S76, S77 | a variant's zip, imported or exported |
  | A95, A98, S81, S84 | the Variants editor's Shape tab: a let go's preview and the Check after it |
  | A106, S88 | a Check with no shipped parts: new content's first (a community-only character) |
  | A102, A103, S102, S103 | the Colours tab's PNGs, exported or imported |
  | A110, A112, S110, S112 | the Moves and Attacks tabs' first opens |
  | A39, A42, A45, A46, A94, A120, A121, S32, S35, S38, S39, S80, S120, S121 | the Data tab: its first open, All tables, a build of 100 edits, a mods file of 1,000 and its Changes, All files |
  | A47, A48, A49, A50, A51, S40, S41, S42, S43, S44 | the Tools tab: the image's info, Verify every file, its file list, Extract |
  | A52, A53, A54, A55, S45, S46, S47, S48 | Open a build…, a mods file saved and loaded, a plan file's spoiler, the last build's report |
  | A62, A63, A64, A65, A66, S54, S55, S56, S57, S58 | Replace files and Saves |

- **The suite lock's turns (D1222):** macOS hands a released flock to its
  first waiter in the order they blocked, stopped or not, and no later
  taker or `LOCK_NB` try passes it (Step 4.47a's scratch run), so a seat's
  window (`$EV/tools/window`) waited behind every gate queued before it. No
  run waits in that line: a queued run tries the lock (`LOCK_EX|LOCK_NB`)
  every 0.5 s (`fullsuite.POLL`) and takes a free one only on its turn
  (`fullsuite.turn`): no older queued run waits for it (by `queued_at`, an
  older lane's `created_at`; a runner that runs, not stopped, whose command
  line names `fullsuite.py` and its meta), and no window waits for it
  (`lock.window` beside the lock, `window <ticket n> pid <pid>`, which its
  holder rewrites as it polls; gone past 10 s or once the pid is) while a
  run took it last (`lock.turn`, `gate <key>` or `window <ticket n>`, written
  by the taker while it holds the lock and runs; a run that started since,
  as an older lane's, which writes none, makes it a gate's). The window
  yields the same way while a window took it last, so a gate and a window
  seat alternate; with none waiting on the other side either goes at once.
  A gate from a lane without this still blocks in flock's line and passes
  the pollers until its lane rebases.
- **Landing:** `uv run --locked python scripts/land.py <branch>` fast-forwards
  `main` once a passing receipt covers the branch's head with `vanilla: N run`
  and `europe: M run`, N and M at least 1 (D26), and, for a stack that
  changes `src/`, `web/` or another path the perf stage times
  (`perf.select`: `scripts/web_tools.py`), a perf block in which nothing blocks
  (`perf.blocking`, read from its verdicts, as the receipt's status is: its
  debt rows never do); it refuses any stack whose
  perf list grows main's (one that changes only the list too). The landing
  queue runs one perf stage a batch (D1215's P1): it gates each entry with
  `fullsuite.py --perf-later` (pytest and the flake stage; the receipt's perf
  `deferred`, its key naming no selection), then the batch's last green entry
  with `--perf-later --perf-now` (that receipt's stage alone, its selection
  what its changes against main's head reach, `perf_base`), and `land.py`
  lands a deferred receipt's stack on a later receipt's block (`cover_for`:
  a passing clean receipt whose head holds the stack's, whose perf ran
  against main or a commit main holds, timed every op the stack's changes
  reach and blocks nothing); a block that blocks is bisected by the queue on
  the batch's middle entries. Landing never
  waits for a release (D1170): a release is a tag on a commit that is on
  `main` (`release.yml` checks that), cut from main whenever its tests pass.
- **CI (Step 4.4ci; D1022-D1024):** AzurKit is public in Azurik-Modding-Hub
  before its release so GitHub Actions tests it, and publishing isn't a
  release: only `release.yml`, below, deploys the site (Pages stays off
  until then, D1026), uploads to PyPI or makes a release, and no workflow
  tags. `.github/workflows/tests.yml` runs the
  pure tier on every push to `main` or a lane branch (`p2/*`) and every pull request on the four
  platforms the apps ship for (macOS on Apple Silicon and on Intel,
  Windows x64, Linux x64; the web tier with Node 24 and
  `scripts/web_tools.py`'s Pyodide and browsers), and on a push to `main`
  or a lane branch in this repository alone (D1123) the vanilla and europe tiers on the same four:
  Azurik-Custom-Content at the commit the content step's `CONTENT_COMMIT`
  pins (Step 4.46a: every part reads one content, whatever its main does
  meanwhile; the commit whose `record_shipped.py --content` re-record needs a
  newer entry moves it), each image rebuilt in the tier's folder (its tests'
  temp folders there too), on the runner's roomiest disk
  (`scripts/ci_resources.py --room`: short of the two images, the most the
  tier's writes took and a margin, Linux's unused toolchains go first, and
  still short of the first two the job stops by name before the images), from
  the game-data repo's parts with `GAMEDATA_DEPLOY_KEY` (the only secret a
  workflow reads), fetched over SSH on GitHub's HTTPS port
  (`ssh.github.com:443`, its host key pinned, a dead connection ending its
  try: Step 4.4ci50), each part (90 MiB) a fetch of its own, that file's
  blob fetched alone into a partial clone and then checked out with lazy
  fetching off (`GIT_NO_LAZY_FETCH=1`: Git for Windows' FSCache hides from
  a checkout the blob its own lazy fetch brought, Step 4.5h), with 6 tries
  of its own, so a macOS runner's network lost for minutes costs one part
  and not the folder (Step 4.5e), never cached, uploaded or printed, and
  deleted after, with the free disk and memory each minute and their
  lowest printed (`scripts/ci_resources.py`); on every OS the job runs
  behind harden-runner's egress block, which starts with the job (its
  pre-step), so its installs' hosts are named too, and on Linux its tests
  run with no network as well (Modkit's §12.4 hygiene), and only the
  pytest log's tail and summary are printed. A setup download with no
  retry of its own (apt under Playwright's `install-deps`, the game data's
  fetches and Azurik-Custom-Content's fetch over HTTPS, a transfer under
  1000 B/s for 60 s ending its try: Step 4.52a) runs as `retry "WHAT"
  COMMAND` (the game data's name their `--tries=6`) from
  `scripts/ci_retry.sh` (in any workflow: `tests/test_contracts.py`): 6
  tries, 7.5 min of waits, and `web_tools.download` fetches Pyodide's core
  and wheels: 6 asks, 15 s to 2 min apart, no wait starting that would end
  past 10 min from the first ask (the last ask may run on past it, each read
  up to its 2 min timeout), then a failure by name (Steps 4.4ci46 and
  4.5t: an outage of GitHub's release downloads lasts minutes). What
  `scripts/web_tools.py` fetches (Pyodide, Playwright's browsers) is kept
  in Actions' cache, keyed by the exact versions, the OS and what is kept
  (`web_tools.py --cache`), restored before its step (on a miss its folders
  go first, so a restore cut short leaves no part file) and saved after it
  on a miss, before any key or image is on the runner (Step 4.5t). Each tier runs on xdist's
  workers (`--dist=loadgroup`, as the gate does) in a number each runner's
  memory sets, in the matrix: a killed worker ends the run by name
  (`--max-worker-restart=0`), where replacing one under loadgroup hangs it.
  A failed test gets its one rerun there too (D1170): a job whose failures
  all passed their rerun is green, and its last step lists them in the
  job's summary (`AZURKIT_FLAKES`, `python -m tests._rerun`); the step
  after it prints each test that failed twice with its first try's error
  lines in the job's log (`python -m tests._rerun --first`, from that
  file's sibling `.failed.jsonl`).
  Each runner's vanilla tier runs as parts at once, a job each
  (`--shard=LABEL:K/N`, `scripts/ci_shards.py`, Step 4.4ci35): the tier's
  tests cut in their run order by that runner's seconds in
  `tests/ci_durations.json`, each `xdist_group` in one part, so every part
  takes about an hour; refresh the table from a run's logs (`gh run view RUN
  --log`) when the tier's tests or their times change much, and change a
  runner's count of parts in `scripts/ci_matrix.py` (`tests/test_tiers.py` holds each
  label's parts 1..N once). That script, the workflow's first job, writes
  both matrices from the event, the repository and the ref (Step 4.4dx5):
  GitHub runs 5 macOS jobs at once here, so on a push that runs the vanilla
  tier each macOS runner's part 1 runs its pure tier first (after the
  setup, before the key or an image, behind that job's harden-runner) and
  the pure job runs Windows' and Linux's alone: a push asks for 5 macOS
  jobs, where 7 left two waiting 20-33 min. `ci_shards` gives that part
  less of the tier by the table's `head`, the pure tier's seconds there.
  A lane branch whose name ends in a runner's word (`-arm64`, `-intel`,
  `-windows`, `-linux`: `p2/4.4ci47-webkit-arm64`) runs only that runner's
  rows and Linux's pure tier (Step 4.4dx9), so a lane chasing one runner's
  failure leaves main's macOS slots free; it tests no other runner on CI,
  while main and every other lane branch run everything, so main's run
  before a release covers all four.
  `checks.yml` runs the leak
  guard over the checkout and every commit, and `python -m nativekit
  --check` on macOS, Windows and Linux (D1019). `apps.yml` freezes the four
  apps (`scripts/freeze.py --check`, which refuses one whose compiled library
  doesn't load) on a push to `main`, each a 14-day workflow
  artifact with its sha256. `pins.yml` (Step 4.24c) runs on a push to
  `main` or a lane branch (Step 4.46a; never cancelled) and a pull request
  that changes `devkit/re/tools.toml` or `bootstrap.py`: each tools.toml
  asset the change adds or alters against the push's previous commit (a new
  branch's merge base with `main`) or the pull request's base is downloaded
  again and hashed (`bootstrap.py --verify-pins`, stdlib only). `.github/dependabot.yml`
  asks weekly for a newer release of each action pinned by commit sha and
  opens a pull request once that release is a week old. `release.yml` (Step 4.3r4j; D885) starts only
  on a `v*` tag and on a release's publishing: a tag whose name is
  pyproject's version and whose commit is on `main` builds the four apps,
  the wheel, the sdist, `SHA256SUMS`, their attestations and a draft
  release; the owner's Publish on it uploads that draft's wheel and sdist
  to PyPI by trusted publishing and then deploys the site to Pages. A
  dispatch is its dry run (D1068): from `main`, the same apps, wheel,
  sdist, site and checked `SHA256SUMS`, left as the run's own artifacts,
  and no attestation (Sigstore's log is public), draft, upload or deploy
  (`tests/test_contracts.py` reads each job's `if:` under each event). PyPI's
  pending publisher names the file and its `pypi` environment: neither
  changes. Before the first Publish, Pages' source must be GitHub Actions
  and the `github-pages` environment must admit the tag rule `v*`, or the
  deploy fails after the upload. Workflows hold `permissions: contents:
  read` (`release.yml`: none at its top, each job its own, held by
  `tests/test_contracts.py`; each of its jobs starts behind harden-runner,
  the dry run's blocking all but their hosts, attest, draft, pypi and pages
  auditing, as no dry run reaches them: Step 4.4ci9), no `pull_request_target`, and actions pinned
  by commit sha with their release beside it; `actionlint` passes on each.
  A stack still lands on the local gate (`land.py`); the other
  platforms must pass by 4.4 (D1023), with their own references or
  close-enough comparisons where float maths differ (D1016).

## Environment

- Scratch goes in `mktemp -d /tmp/azurkit-<what>.XXXXXX` (`/tmp` is shared).
  Delete it by its exact path: never a glob over `/tmp`, and never anything
  you didn't make, the images, an xemu folder or the xemu oracle's fixtures
  (`AZURIK_XEMU_FIXTURES`). Never edit what a tool writes: `.venv/`,
  `.tools/` (every lane's), `__pycache__/`, `dist/` and `build/`. Never run
  `bootstrap.py` in a lane's worktree: setup is the main checkout's, once,
  and the pre-push hook it writes is every worktree's.
- No home paths in tracked files.
- **The owner's screen (D839):** this machine is the owner's, who works on
  its screen. Seats never launch the app on it: no `open AzurKit.app`, and
  neither the bundle's executable nor `python -m azurkit` with no arguments
  (the window; `serve` and the `azurkit` commands open nothing). Nor a
  headed browser: Playwright runs headless only, and `tests/conftest.py`
  refuses any other launch. The frozen-app test runs the bundle only under
  `AZURKIT_NO_WINDOW` or as `serve`.
- **xemu only (D601):** in-game checks run in xemu. Real hardware isn't a target.
- **The xemu harness (Steps 4.14a1, 4.14a2, devkit):** `devkit/xemu/oracle.py`
  (`python -m devkit xemu oracle CMD`; `devkit/xemu/README.md`) runs
  sandboxed clones of the owner's xemu fork on the oracle's fixtures
  (`AZURIK_XEMU_FIXTURES`), never the owner's own xemu, never a visible
  window but an owner demo's, at volume 0, each admitted by its slots
  (D108). Its core needs no Unicorn: `devkit/xemu/queue.py` (the sittings'
  first-come tickets and the batch token that gives way to them),
  `devkit/xemu/warm.py` (a sitting's warm build states) and
  `devkit/sim/{snapshot,obs,inputs}.py` (the guest RAM snapshot's file and
  its private store, `l3-snapshots/` in the user data folder; the player's
  observation; the pad). It keeps Modkit's folders (`/tmp/azx-xemu-slots`,
  the owner-demo lease, the store) and its admission watches both repos'
  suite locks, so both harnesses share one D108 budget while Modkit lives.
  A sitting runs on its kit (Step 4.14a3): `python -m devkit xemu sitting`
  (a spec's cases, or a serve its drivers run in), the model-swap rows
  (`devkit/xemu/sittings/model_kit.py`: the frame's cost warned, never
  refused, D603, D604), the owner demos (`python -m devkit xemu demo`) and
  the reach engine's xemu checks (Step 4.13d2: the chain driver, `python -m
  devkit xemu chain`, the route pilot and the minigame solvers);
  its builds are AzurKit's (`sdk.build`), and how to sit is the
  `azurik-xemu-oracle` skill, which only a seat that sits loads. Agent
  save states never go on the oracle's drive (D102).
  No test launches xemu (D108): `tests/test_xemu_harness.py` reads
  synthetic memory and runs the harness's and the kit's offline
  selftests (marked `xemu`, which CI's Linux and Windows legs deselect).
- **Ask nothing (D115):** where a decision is missing, take the recorded default
  or your recommendation, and say so in your report.
