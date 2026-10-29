# AGENTS.md: rules for agents and contributors

AzurKit is the lean, public rewrite of Azurik_Modkit. Modkit is its reference
and test oracle: a port is done when its output matches Modkit's byte for byte,
file by file. [`README.md`](README.md) says what AzurKit is. These rules bind.

## Setup and tests

```bash
uv run bootstrap.py                         # once, in the main checkout: uv sync --locked, the pre-push hook, Pyodide
uv run --locked pytest -q <files>           # targeted tests while you work
uv run --locked pytest                      # the whole suite
uv run --locked pytest -m "not vanilla"     # the pure tier: no game data
uv run --locked python scripts/freeze.py --dist DIR   # the app (D732): DIR/AzurKit.app on macOS (a PyInstaller onedir)
uv run --locked python -m shimkit [--check]           # the prebuilt shim objects, from their sources (zig, dev only)
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
  it in Playwright's headless Chromium and again in its WebKit, Safari's
  engine (Step 4.1d3: Safari failed where Chromium passed); either becomes
  `web`. A run that selects one needs Pyodide's pinned core, Node on PATH
  for the first and both browsers for the second, which `uv run
  bootstrap.py` puts in the main checkout's `.tools/` for every lane
  (`scripts/web_tools.py`; `PLAYWRIGHT_BROWSERS_PATH`, never the user's
  cache). Without one the run stops with one message naming it; the opt-out
  is `-m "not web"`. The summary prints `web: K run`.
  - Chromium's headless shell never fires `requestAnimationFrame` here, so
    Playwright's actionability waits hang and `wait_for_function` needs eval,
    which the page's CSP refuses: drive the page through the DOM
    (`element.click()`) and poll with `page.evaluate`.
- **Skips:** a skip or an xfail fails the run unless `tests/skip_allowlist.toml`
  lists it, and that list is empty. Failures never become skips: no new
  `skipif`, `SkipTest` or `xfail`, and no allow-list entry to get green.
- **Lean tests:** the fewest tests that pin a behavior, each in a
  behavior-area file. A fix gets one behavior-named test, in the same commit.

## Game data (D3: public, no game bytes ever)

- Never commit an ISO or any file taken from the game, whole or in part: no
  XBE, XBR, save, disk or EEPROM image, key, or disassembly listing.
  - `tests/_leak_guard.py` refuses them in the suite and on every push,
    also inside a gzip file (its inner bytes are read by every rule, the
    vanilla-run rule's too). Its rules have no allow-list.
  - Never weaken them to get green.
- Never write a run of vanilla bytes as a literal in code or tests (a bytes
  literal, `bytes.fromhex`, a hex string, a list of byte values): read it from
  the player's image at its address. The vanilla tier refuses a literal under
  `src/`, `tests/`, `scripts/`, `web/` or `assets/` holding 8 or more bytes in a row of
  either release's `default.xbe` or `gamedata/config.xbr` (its
  `VANILLA_FILES`: add a game file there once the code reads its bytes),
  by file, line and length
  (`tests/test_leak_guard.py`), and `scripts/land.py` refuses a stack any of
  whose commits adds one, even when a later commit removes it again: the
  history keeps it. Rewrite the commit that adds it.
  - Both read a committed shim object (`.o`) there too, for 32 or more
    bytes in a row in a code section or anywhere in the file, and 16 in a
    data section: compiled code and constants share shorter runs with the
    game by chance (up to 20 B and 10 B measured), and its source is read
    at 8. Text, and a constant of at most 3 byte values, aren't counted in
    an object.
- Never print game bytes in logs, commits or chat: print lengths and
  `sha256[:12]`. Failure output is redacted (`tests/_byte_safe.py`).
- Recorded results are hashes and names. The facts hold sha256 and length,
  never raw vanilla spans.
- The images are read-only. A build writes to an explicit output that isn't
  its input.

## The oracle

- `tests/oracle/<family>/` is Modkit's bundle for a family (`core`, `packs`,
  `rando`, `models`), cut at a Modkit tag. `tests/oracle/ORACLE.toml` records
  each family's tag, its commit and every file's sha256, and
  `tests/test_oracle.py` holds them to it.
  - Only `scripts/oracle_sync.py` changes these files; never edit them by hand.
  - A tag bump prints Modkit's commits since the last sync. That list is the
    port's to-do.
  - **Modkit's source a sync installs** (`oracle_sync.SOURCES`): the rando
    family's sync also installs the randomizer's database
    (`src/azurkit/tools/randomizer/data/`, our own logic data, copied
    verbatim) and its planner (`.../randomizer/planner/`, each module through
    `port()`: `REWRITES`' imports, and the top-level statements `DROPS` names
    taken out, such as the seed roll's process pool). ORACLE.toml's `source`
    table holds each installed file's sha256 and `tests/test_oracle.py`
    refuses a hand edit: a Modkit fix arrives by the next sync. A module
    that still imports Modkit after the rewrites, or a statement `DROPS`
    names that is gone, stops the sync by name before anything is written:
    port what it imports into an AzurKit module, then add a rewrite.
- AzurKit never imports Modkit, and nothing NOTICE.md credits to JTCPP is
  ported (D95). `tests/test_provenance.py` checks that.
- **The facts** (`src/azurkit/core/facts.<release>.json`: each release's XBE
  sha256, its sections, every patch site's size and vanilla sha256, Europe's
  address map) are derived from the oracle by `scripts/gen_facts.py`; run it
  after a packs or core sync, never edit them by hand. `tests/test_packs.py`
  holds them to it.

## Packs

- A pack (`src/azurkit/tools/mods/packs/`) holds only what it writes: each
  site a `PatchSpec` at a USA address (Europe's comes from the facts), its
  bytes, and the offsets of the absolute addresses (`abs32`) and rel32
  branches (`rel32`) in them. The facts give each site's size and the
  sha256 of its vanilla bytes; never put vanilla bytes or game constants in
  a pack: read a value the pack scales from the vanilla XBE (`Xbe.read`).
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
  the sdk refuses a recipe without them, by name (`mods.missing`); the CLI
  leaves out a pack on by default with one it requires (D588); the page ticks
  them with it and unticks it with them. G1 builds each pack alone, so such a
  pack's case is its layer's image.
- **XBR** (`core/xbr/`): `Document` parses an archive's header, TOC and
  trailer, and config.xbr's keyed tables (`keyed.py`), and `dumps()` writes
  them back (every vanilla XBR round-trips, `tests/test_xbr.py`). An edit
  (`edits.py`) is the writes `[(offset, bytes)]` that make it, planned
  against the file as parsed; every cell is 16 bytes, so nothing grows.
  The keyed cells are written new from the format, never from the code
  NOTICE.md credits (AZ-212, D95).
- **The mods file** (Q268; `edits/preset.py`'s `read`, `sdk.read_mods`,
  `azurkit build --mods`) is a preset, an AzurKit build's manifest or a
  share link. Its `mods` layer is the build's packs (in place of those on by
  default), and its `data` layer's `xbr` operations (`edits/xbr.py`) apply
  in order after the packs: `set` a config.xbr cell by the file's names
  (D51's spellings), type-checked; `replace_bytes` in an XBR file, where
  vanilla holds `expected` (hex up to 32 B, else `{sha256, size}`): read it
  from the image in a test, never write it. A later operation or layer that
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
- **Shims** (Step 4.1f1): a `TrampolinePatch` hooks a site with a CALL or
  JMP rel32 into a C shim. A shim's source and its prebuilt object sit side
  by side in `src/azurkit/tools/mods/shims/` (`<name>.c`, `<name>.o`), both
  committed, so no host compiles one: neither the site nor the app needs
  zig (AZ-045).
  - `uv run --locked python -m shimkit` builds every object with the pinned
    zig (`ziglang` 0.16.0, the dev group) and Modkit's flags: the same
    bytes on any machine, whose normalized sha256 is the oracle's G2 record
    (`tests/test_shims.py` holds both). Rebuild after editing a source;
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
    through its slot; one the game doesn't import (no slot) is refused by
    name: no ported shim calls one, so the resolving stubs that would call
    the committed `xboxkrnl_resolver` aren't ported yet.
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
- A slider at a site of the XBE has no vanilla value in the catalog (the
  wheel holds no game constant, Q174): `sdk.vanilla` reads it from the
  player's image, and the page shows it once the image is picked (D42).
- Describe patch bytes in prose: four or more comment lines that read as
  x86 instructions are a disassembly listing to the leak guard.
- A port is done when its cases match the oracle: the facts site by site,
  then G1 per file on both releases (`tests/test_packs.py`; `tests/_g1.py`
  reads G1, whose Europe half has no case for a config.xbr-only pack: the
  file is the same in both releases, so its USA cases stand for it).

## The randomizer

- **The planner** (Step 4.2a; `src/azurkit/tools/randomizer/`): `plan(recipe)`
  fills the database's authored levels for a seed (any string) under the
  database's default settings (D144), a settings file's table (`settings`)
  or a share string (`share`), and returns Modkit's plan file's object;
  `spoiler(doc)` reads one back. The sdk's `plan` and `spoiler` and the CLI's
  `azurkit plan` and `azurkit spoiler` call them. A plan needs no image.
  - `planner/` and `data/` are Modkit's, installed by the sync (above):
    never edit them by hand. `writer.py` (the string rules the fill reads:
    Modkit's writer up to `layout`, which Step 4.2b extends with the writes
    and the read-back) and `dbcache.py` (no cache on disk: a pickle read
    back from a writable folder runs its code) are ours.
  - The fill runs in the caller's thread: Modkit's seed roll in a process
    pool (`roll_seed`) isn't ported. Settings with movement sliders (a share
    string's) are refused by name until Step 4.2b ports the logic's re-check
    under them (physics and movement).
  - `tests/test_randomizer.py` holds it to the oracle's `rando_plans.json`:
    seed 2's attempt and plan sha256 under the strict, default and max
    settings, and the default plan file byte for byte, on CPython and under
    Pyodide. The page's Randomizer tab stays hidden until Step 4.2c (D902).

## The engine's contracts

- **Layers:** `core <- edits <- tools <- sdk <- {cli, app}`. The three tools
  (`mods`, `randomizer`, `characters`) never import each other. import-linter
  holds this (see `pyproject.toml`).
- **AST rules:** `core`, `edits` and `tools` hold no threads, processes,
  subprocesses, prints or exits, so the web page's worker runs them as they
  are. The worker loads the wheel without its dependencies, so the engine
  imports platformdirs only where it needs the user data folder. Only `tools/characters` imports numpy, and nothing imports capstone,
  unicorn, zig or Tk. `tests/test_contracts.py` checks these, along with
  import-linter's contracts.

## The two hosts (D866)

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
    own from its config and opens its window on that theme's ground. The About tab's licence and credits
    restate `LICENSE` and `NOTICE.md` (`tests/test_site.py` holds them
    to those files); its privacy line says only that AzurKit collects
    nothing and that the image never leaves the computer (D883).
  - **Share links** (WEB §4.1): Copy link asks the engine for
    `sdk.preset_encode`'s `#p=` fragment of the page's ticks, sliders and a
    loaded recipe's config.xbr cells (with the build's hashes when it is
    current), after the site's address (the app's `host.json` names the
    site's, D884). A page opened with one loads it once its engine is ready
    (`sdk.preset_decode`): exactly its packs ticked, its sliders set, each
    tick and value it changed marked ●, and no build. Ticking a pack ticks
    the packs it requires; unticking one unticks those that require it.
  - **An AzurKit build as the image:** the engine's vanilla read (the
    site's worker, the app's `api/vanilla`) falls back to
    `sdk.open_build(whole=False)` (only the files the build changed are
    checked: reading all 2.6 GB takes minutes in WebKit's worker), and the
    page shows "◆ AzurKit build" with Load its recipe, which loads it as a
    link's, to build again from a vanilla image.
  - **The remembered setup** (D915): the page keeps its ticks, each
    setting that differs from its default (an unticked pack's too) and a
    loaded recipe's config.xbr `set` cells, `{"ticked", "values", "xbr"}`:
    names and numbers, never the image, its path or anything read from it
    (D3). The site keeps it in the browser's storage (`azurkit.setup`), the
    app in its config (`host.json`'s `setup`; `api/setup` refuses by name a
    setup with anything else anywhere in it, a path, say); at the defaults
    nothing is kept. A page opens with it before an image is
    picked, through `sdk.restore` (the site's worker, the app's
    `api/restore`), which leaves out and names in the status line what no
    longer normalizes (a pack renamed or retired, a setting gone, a value
    refused, a pack without one it requires); the page is ready once it is
    back. A share link or Load its recipe wins and becomes the remembered
    setup; once the page changes, its address drops the link's `#p=`.
    Reset to defaults, in the bottom bar (off at the defaults), ticks the
    packs on by default, sets every setting to its default and forgets it.
- **The site** is the page with Pyodide's core, the wheel and its
  `host.json` (`uv run --locked python scripts/web_tools.py --site DIR`). Its
  engine runs the wheel, unpacked without its dependencies, under Pyodide in
  a module worker started from a `blob:` URL (so the page's CSP holds there),
  one worker per build, which reads the image in blocks (WebKit takes about
  200 ms for each read of a File, whatever its size). It returns the build as segments
  (`iso.Image.segments`), which the page joins into a Blob of slices of the
  player's file and the bytes the build writes, and Save downloads it.
  `tests/test_hosts.py` runs the gate under Pyodide on Node, and
  `tests/test_site.py` the packs' G1 cases and a save in Chromium and
  WebKit.
  - The worker holds one PyProxy, its engine function, which hands back
    plain JS values: a PyProxy it dropped would be freed by Pyodide's
    FinalizationRegistry, which needs the GIL, and WebKit runs that cleanup
    inside WORKERFS's read of the image, where CPython has released the GIL
    (`NoGilError`, Step 4.1d3).
- **The app** (D732) is `python -m azurkit` (`src/azurkit/__main__.py`): with
  no arguments the page in a pywebview window, else in the default browser;
  `serve` serves it without opening either (the tests' way in); any other
  arguments are the `azurkit` command. `azurkit.app` serves the page on
  127.0.0.1 to this launch's token only, and is its engine: `host.json`
  and JSON calls (`api/build`, `api/save`, ...) that run `azurkit.sdk` on
  CPython, only from the page's own origin. The page takes the image's path
  (remembered in platformdirs' config folder; the window adds file dialogs)
  and Save writes the build to a path, never over an existing file but one
  the save dialog chose. Closing the app (the window's close button, Cmd-Q,
  `serve`'s input ending) cancels a build or a save: it never waits on a
  build, and waits for a save to remove its part file `app.QUIT_WAIT`
  (1.5 s) at most, then removes it itself (AZ-823, D35). The window sets
  pywebview's `text_select`, or pywebview injects a `<style>` the CSP
  refuses. `scripts/freeze.py` builds
  the app (`AzurKit.app` on macOS, a windowed onedir); pyinstaller and
  pywebview are the `app` dependency group, never the wheel's. The bundle is
  read-only: every write goes through platformdirs, or to the path the
  player saves to. It carries no Unicorn, zig, capstone or GPL code;
  `tests/test_hosts.py` checks each name in it and its licence, and builds
  the packs' G1 cases and a save through its page (`AzurKit serve` in
  headless Chromium and WebKit).
- **The icon** (D891, D892) is original art that code draws, no game pixel
  (D3, D890): in `assets/icon/`, `mark.py` draws the mark (`AzurKit.svg`)
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
- **Never:** attribution trailers, force-pushes, `--no-verify`, `git stash` or
  git config changes.
- **The gate:** run `uv run --locked python scripts/fullsuite.py <worktree>
  --changed`. It runs the lint files in the foreground, then the changed area
  with the oracle's USA and Europe test (or the whole suite) in the background
  under a lock, and prints a key and a receipt path. A run is killed past its
  cap, 1,800 s, scaled by the host's load per CPU up to twice that, and its log
  ends with the slowest tests. `--wait 540` waits for the result; exit 3 means
  it is still running, so issue the same command again.
- **Landing:** `uv run --locked python scripts/land.py <branch>` fast-forwards
  `main` once a passing receipt covers the branch's head with `vanilla: N run`
  and `europe: M run`, N and M at least 1 (D26), and no commit it lands adds
  a vanilla run (by commit, file, line and length). There is no remote
  until AzurKit goes public (D137, D91: Azurik-Modding-Hub at 4.4).

## Environment

- Scratch goes in `mktemp -d /tmp/azurkit-<what>.XXXXXX`. Delete it by its exact
  path.
- No home paths in tracked files.
- **The owner's screen (D839):** this machine is the owner's, who works on
  its screen. Seats never launch the app on it: no `open AzurKit.app`, and
  neither the bundle's executable nor `python -m azurkit` with no arguments
  (the window; `serve` and the `azurkit` commands open nothing). Nor a
  headed browser: Playwright runs headless only, and `tests/conftest.py`
  refuses any other launch. The frozen-app test runs the bundle only under
  `AZURKIT_NO_WINDOW` or as `serve`.
- **xemu only (D601):** in-game checks run in xemu. Real hardware isn't a target.
- **Ask nothing (D115):** where a decision is missing, take the recorded default
  or your recommendation, and say so in your report.
