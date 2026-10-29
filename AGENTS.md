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
  - `tests/_leak_guard.py` refuses them in the suite and on every push. Its
    rules have no allow-list.
  - Never weaken them to get green.
- Never write a run of vanilla bytes as a literal in code or tests (a bytes
  literal, `bytes.fromhex`, a hex string, a list of byte values): read it from
  the player's image at its address. The vanilla tier refuses a literal under
  `src/`, `tests/`, `scripts/` or `web/` holding 8 or more bytes in a row of
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
- **XBR** (`core/xbr/`): `Document` parses an archive's header, TOC and
  trailer, and config.xbr's keyed tables (`keyed.py`), and `dumps()` writes
  them back (every vanilla XBR round-trips, `tests/test_xbr.py`). An edit
  (`edits.py`) is the writes `[(offset, bytes)]` that make it, planned
  against the file as parsed; every cell is 16 bytes, so nothing grows.
  The keyed cells are written new from the format, never from the code
  NOTICE.md credits (AZ-212, D95).
- **Presets** (`edits/preset.py`, `sdk.preset_encode` and `preset_decode`)
  carry a recipe as a link's `#p=` fragment: names, numbers and hashes only,
  never an image path or a byte (Q174), capped as untrusted input.
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
- **The site** is the page with Pyodide's core, the wheel and its
  `host.json` (`uv run --locked python scripts/web_tools.py --site DIR`). Its
  engine runs the wheel, unpacked without its dependencies, under Pyodide in
  a module worker started from a `blob:` URL (so the page's CSP holds there),
  one worker per build. It returns the build as segments
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
  the save dialog chose. The window sets pywebview's `text_select`, or
  pywebview injects a `<style>` the CSP refuses. `scripts/freeze.py` builds
  the app (`AzurKit.app` on macOS, a windowed onedir); pyinstaller and
  pywebview are the `app` dependency group, never the wheel's. The bundle is
  read-only: every write goes through platformdirs, or to the path the
  player saves to. It carries no Unicorn, zig, capstone or GPL code;
  `tests/test_hosts.py` checks each name in it and its licence, and builds
  the packs' G1 cases and a save through its page (`AzurKit serve` in
  headless Chromium and WebKit).

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
  under a lock, and prints a key and a receipt path. `--wait 540` waits for the
  result; exit 3 means it is still running, so issue the same command again.
- **Landing:** `uv run --locked python scripts/land.py <branch>` fast-forwards
  `main` once a passing receipt covers the branch's head with `vanilla: N run`
  and `europe: M run`, N and M at least 1 (D26), and no commit it lands adds
  a vanilla run (by commit, file, line and length). There is no remote
  until AzurKit goes public (D137, D91: Azurik-Modding-Hub at 4.4).

## Environment

- Scratch goes in `mktemp -d /tmp/azurkit-<what>.XXXXXX`. Delete it by its exact
  path.
- No home paths in tracked files.
- **xemu only (D601):** in-game checks run in xemu. Real hardware isn't a target.
- **Ask nothing (D115):** where a decision is missing, take the recorded default
  or your recommendation, and say so in your report.
