# AGENTS.md: rules for agents and contributors

AzurKit is the lean, public rewrite of Azurik_Modkit, its proof of concept,
whose port is done and whose checkout is deleted (Porting from Modkit): every
family's truth is AzurKit's own (The goldens, below), first recorded at
Modkit's last cut. [`README.md`](README.md) says what AzurKit is,
[`docs/GUIDE.md`](docs/GUIDE.md) every feature in detail and
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) how to build and test it;
[`docs/Future/PENDING.md`](docs/Future/PENDING.md) lists the work still
pending. These rules bind. [`docs/INTERNALS.md`](docs/INTERNALS.md) holds the
design each section stands on, under the same headings: read its section
before changing that area (these rules win where the two differ), and a
design change updates it there.

**The guide's features:** a change a player would notice adds or updates its
line in `docs/GUIDE.md`, in the same commit, and README's short Features
list only when it changes what a line there says: README stays a page of
about 60-90 lines for players (what it is, what you need, how to use it, the
main features, help, the licence), with links absolute (PyPI shows it). Each
line is plain and short, with no step, D or AZ ids, and true on `main`.

## Where knowledge lives

| Home | Load it for |
|---|---|
| This file | the rules: setup and tests, game data, the goldens, porting from Modkit, packs (with patching and shims: what binds), the randomizer, characters, the engine's contracts, the two hosts, commits and landing |
| [`docs/INTERNALS.md`](docs/INTERNALS.md) | the design under each section here: the engine's parts, every tab of the page, the site's workers, the app's engine, the gate's plan, the perf gate and CI in full |
| `azurik-change-control` (`.claude/skills/`) | how a change lands: the change classes and the evidence each owes, the gate and green (D1170's rerun and perf debt), landing, CI and the release's shape, the protected paths and their update commands, commits, the never-commit list |
| `azurik-testing` (`.claude/skills/`) | running and writing tests: which to run for a change, the tiers and markers, the empty allow-list and flakes, fixtures, one behavior-named test a fix, determinism, goldens and facts, the simulator's levels, the perf gate's window, CI's tiers |
| `azurik-dev-environment` (`.claude/skills/`) | uv and Python 3.14, the dependency groups, `bootstrap.py` and a lane's setup, where the images and the user data live, the environment variables, devkit's areas, the MCP servers, setup hazards, the owner's environment rules |
| `azurik-orchestration` (`.claude/skills/`) | the orchestrator's: the five roles and typing a seat, the step shapes with their reviews and skeptics, the gate and the window seats share, prompts and returns, the traps, seat practice and the reach seats; load it before writing a workflow or spawning a seat |
| `azurik-game-reference` (`.claude/skills/`) | VAs, structs, ABIs, measured movement and armor numbers, patches whose bytes landed with no in-game effect |
| `azurik-xemu-oracle` (`.claude/skills/`) | the sitting card: in-game ground truth from the owner's xemu fork in a sandbox, the kit, demos, hazards and save states; only a seat that sits loads it (its history: `docs/archive/xemu-oracle-history.md`) |
| `azurik-ghidra-mcp` (`.claude/skills/`) | devkit's Ghidra side: `bootstrap.py --with re`, the ports, `ghidra-serve` copies, `ghidra-apply` (the one writer of the owner's project), `ghidra-sync`, the snapshot; read it before anything opens `Azurik Ghidra.gpr` |
| `.claude/agents/` | the seats' roles (D951's `azurik-*` names): `azurik-builder` (Opus: build, fix, gate, sitting), `azurik-reader` (Opus, read-only: RE, reads, reviews, skeptics), `azurik-judge` (Fable, the reader's rules: a round's designer, hard root-cause hunts), `azurik-scout` (Sonnet, read-only: locate and cite), `azurik-mechanic` (Haiku: a command list handed over); `tests/test_agent_files.py` pins each one's model, effort and denied tools |
| `$EV`, the private evidence folder beside the main checkout | the brief (`$EV/tools/BRIEF.md`), the decisions, the ledger, plans, evidence and the tools the seats run (D951, D952); never copied into the repo |
| Modkit's history (`Azurik-Testing/Azurik_Modkit`, private, archived, D1030) | its commits, closed issues and retired docs (D955), read-only; nothing here reads it |

Tracked files name the private folder as `$EV`, never by a home path, and
cite nothing in it but its tools (`$EV/tools/`): a comment, a data file's
note or a doc names what a claim rests on (a sitting, a step, a
measurement) in plain words (`tests/test_agent_files.py` lints both).

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
  (it becomes `vanilla`), one that reads Europe's `europe_iso` (`europe` and
  `vanilla`); everything else is `pure`. A run that selects a vanilla or
  europe test without that verified image stops, with one message; the only
  opt-outs are `-m "not vanilla"` and `-m "not europe"`. A run prints
  `vanilla: N run` and `europe: M run`. The images are found by
  `AZURKIT_ISO` and `AZURKIT_ISO_EUROPE`, else as `usa.iso` and `europe.iso`
  in the user data folder (`src/azurkit/core/gate.py`).
- **The web tier:** a test under Pyodide on Node takes the `pyodide` fixture
  (`tests/_pyodide.py`), one that drives the page the `browser` fixture
  (`tests/test_site.py`: headless Chromium, WebKit and Firefox, D994, or
  only the `--browsers` names); either becomes `web`, its tools in the main
  checkout's `.tools/` (`scripts/web_tools.py`, never the user's cache),
  its opt-out `-m "not web"`, and the summary prints `web: K run`. Drive the
  page through the DOM (`element.click()`) and poll with `page.evaluate`;
  the browsers' hazards and their workarounds: INTERNALS.md's Setup and
  tests.
- **Skips:** a skip or an xfail fails the run unless `tests/skip_allowlist.toml`
  lists it, and that list is empty. Failures never become skips: no new
  `skipif`, `SkipTest` or `xfail`, and no allow-list entry to get green.
- **Nothing small blocks (D1170):** every run, the gate's and CI's, reruns a
  failed test once at once (`tests/_rerun.py`). One that passes its rerun is
  flaky: the run passes, and the summary, the receipt (`flakes`), the flake
  ledger beside the receipts and CI's job summary name it with its first
  error, a lane to fix it; one that fails twice, or a product bug, blocks.
  A rerun is recorded, never hidden: it is no skip. Perf timings over budget
  are debt rows, not blocks (the perf gate, below).
- **When a truth goes red, suspect the code or the address first:** a
  golden, the facts or a drift guard that fails (the prologue guard in
  `tests/test_shims.py`, a site's vanilla sha256) means the port or the
  facts' address is wrong. Fix it there; never widen `PROLOGUE_FIRST_BYTES`,
  the skip list or any other allow-list to get green.
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

- Game files and game bytes may be committed (D961): an XBE or XBR file, a
  clip, a texture, a save, a snippet, a byte literal, a disassembly listing.
  They belong to the game's rights holders and aren't under the MIT licence
  (`NOTICE.md`). `.gitignore` still ignores `*.xbe`, `*.xbr`, saves and
  extracted trees against accidental bloat: add a game file on purpose with
  `git add -f`.
- Never commit the ISO/XISO image, whole or in parts that rebuild it, a
  private key, an EEPROM dump, an xemu HDD (qcow2) image or a guest RAM
  snapshot (`AZL3SNAP`): the last three can hold console keys.
  `tests/_leak_guard.py` refuses them in the suite and on every push, also
  inside a gzip file. Its rules have no allow-list; never weaken them to
  get green.
- Saves keep no key: `tools/saves/sign.py` derives the console's signature
  key in memory from the player's own BIOS files, which are never kept, and
  holds only the certificate key's fingerprint; its tests sign with a random
  key, on slots and HDD images built in `tmp_path`.
- Never print game bytes in logs, commits or chat: print lengths and
  `sha256[:12]`. Failure output is redacted (`tests/_byte_safe.py`). Read the
  game's code and constants with `python -m devkit re xbe`
  (`devkit/re/README.md`: `read`, `dis`, `fn`; its `hexdump` is a human's);
  Ghidra's side follows the skill `azurik-ghidra-mcp`, and the owner's
  Ghidra project is never opened headlessly or written while a Ghidra holds
  it.
- Recorded results are hashes and names: the goldens and the facts hold
  sha256 and length, not raw vanilla spans.
- The images are read-only. A build writes to an explicit output that isn't
  its input.
- **The private game-data repo,** `Azurik-Modding-Hub/AzurKit-gamedata` (the
  images' parts, for CI only): never make it public, fork or mirror it. Only
  CI's vanilla job reads it, with its read-only deploy key (the `gamedata`
  environment's secret), and the key is never in this repository.
- **Content is untrusted input (D992):** a manifest, a recipe or a picture a
  player is handed is refused by name, quickly and with little held, before
  anything reads it whole; a refusal names the entry, the file or the field,
  never bytes (`tests/test_characters.py`'s untrusted-content table).
  `content.check` caps a manifest and its paths (`content.SUFFIXES`), a PNG
  inflates through `core/inflate.py`, and `web/` holds no HTML sink
  (`tests/test_contracts.py`); the caps: INTERNALS.md's Game data.
- The Data tab's engine (`src/azurkit/tools/data/`) ships the vanilla
  config.xbr (`tests/test_data.py` holds it to both manifests) and
  `schema.json`; a build still reads the image's own config.xbr.

## The goldens

- `tests/goldens/` is AzurKit's own truth for every family (the packs, the
  core, the characters, the randomizer): what each case of
  `tests/goldens/cases.json` (its recipe, edited by hand) builds from the
  vanilla images, as names and sha256. Each file and what it holds:
  INTERNALS.md's The goldens.
- Only `scripts/record_goldens.py` writes them, from AzurKit's own builds on
  the player's images (`--check` writes nothing); never edit them by hand.
  It records the page's shipped pictures too, by family (`art`,
  `characters`). A commit that changes one names each golden it changed and
  why, and a gameplay byte change to a default build is seen once in xemu.
- **Off the recording host (D1016):** macOS on Apple Silicon with numpy on
  Accelerate (`tests/_hosts.py`) compares every golden byte for byte; on any
  other host a dress's `characters.xbr` and `fx.xbr` are compared close
  enough (`close.json`), with no reference per platform and no copy of
  their bytes, and every other file stays exact. No byte a golden or a
  shipped picture holds may come from a matrix product (`@`, `dot`,
  `tensordot`) where a tie can round either way: sum in integers, or as
  `art.draw.dot` does.
- The cases that wear booblord read her files in the content folder
  (`AZURKIT_CONTENT`, `azurkit content install booblord`).
- A new pack adds its cases to `cases.json` (its defaults in `packs.json`,
  `sites.json` and, for an XBE pack, Europe's), then records them.

## Porting from Modkit

- **The port is done** (D1168, D1171): every Modkit capability AzurKit keeps
  is AzurKit's own, in `src/azurkit` (the player's) or `devkit/` (the
  developer's), held to AzurKit's tests and goldens. Modkit's history is the
  private archived repository `Azurik-Testing/Azurik_Modkit` (D1030),
  read-only; no AzurKit file, test or tool reads it, AzurKit never imports
  Modkit, and a fix is made here. Each cut's provenance and Modkit's module
  map: INTERNALS.md's Porting from Modkit.
- A later change to a ported module is held to the tests it was merged into
  (D10, D37) or names the golden that pins it. A change to the randomizer's
  writer's or layer's bytes owes an xemu sitting; a change to the derive
  bumps `DERIVE_VERSION` (`python -m devkit rando restack` re-derives and
  re-records); the reach engine (`devkit/reach`) is frozen (D1143).
- **The facts** (`src/azurkit/core/facts.<release>.json`: each release's XBE
  sha256, sections, every patch site's size and vanilla sha256, the
  functions a shim may call, the kernel exports' slots, the swap's hooks,
  Europe's address map). `scripts/gen_facts.py` writes their XBE half from
  the player's images; a new site's address and size, a function, the
  swap's sites and refs and Europe's address map are edited by hand, then
  run gen_facts to fill in the rest. `tests/test_packs.py` holds the files
  to it.

## Packs

- A pack (`src/azurkit/tools/mods/packs/`) holds only what it writes: each
  site a `PatchSpec` at a USA address (Europe's comes from the facts), its
  bytes, and the offsets of its `abs32` and `rel32` fields. The facts give
  each site's size and vanilla sha256. A value the pack scales is read from
  the vanilla XBE (`Xbe.read`), each release's own.
- A `custom_apply` writes only through `Xbe.patch`, inside the footprint it
  declares (AZ-097). Errors name the site, never its bytes (D35).
- **Sliders** (`ParametricPatch`, `XbrParametricEdit`) are a pack's
  parameters. Each takes any finite number, never clamped (D23):
  `slider_min` and `slider_max` are display hints, the track holds the
  default and the vanilla value (D42), and only an encoding's limit refuses
  a value (`whole`, D45; an int32 cell's rounding). A config.xbr slider's
  default writes what vanilla holds. `mods.normalize` is every host's one
  check of a recipe's packs: unknown packs and sliders, NaN and inf refused
  by name, a value equal to its default dropped. A slider at a site of the
  XBE has no vanilla value in the catalog (the wheel holds no game
  constant, Q174): `sdk.vanilla` reads it from the player's image.
- `Pack.requires` names the packs a build must apply with it: the sdk
  refuses a recipe without them, by name (`mods.missing`), and a person's
  choice moves them by one rule (`mods.settle`, D1061; INTERNALS.md's
  Packs).
- **XBR** (`core/xbr/`): `Document` parses an archive and `dumps()` writes it
  back (every vanilla XBR round-trips, `tests/test_xbr.py`); an edit is the
  writes `[(offset, bytes)]` that make it, and nothing grows.
- **The mods file** (`edits/preset.py`, `sdk.read_mods`, `azurkit build
  --mods`) and **a build's manifest** (`edits/manifest.py`): a later
  operation or layer that rewrites an earlier group's bytes wins, and the
  conflict names both groups (D28); `sdk.open_build` refuses a drifted file
  by name; a build with no layer is the vanilla image.
- **The sdk's surface** is its snapshot, `tests/sdk_api.txt`: change it only
  with `uv run --locked python scripts/sdk_api.py`, and read its diff.
- **Presets and links** carry names, numbers and hashes only, never an image
  path or a byte (Q174), capped as untrusted input.
- **Community packs** (D988, `tools/mods/community.py`): data only and
  release-free (a `mods` packs layer and a `data` xbr layer, no randomizer,
  character, XBE site or code), pinned by id and sha12, taken only installed
  and untouched at the pin, recorded in a manifest by id, version and sha256,
  never its bytes. No pack ships (D997), so fixture packs in
  `tests/test_community.py` pin them.
- **Shims** (Step 4.1f1): a shim's source and its prebuilt object sit side
  by side and are both committed (`src/azurkit/tools/mods/shims/`, the swap's
  in `tools/characters/player_model/`), so no host compiles one (AZ-045).
  Only `uv run --locked python -m shimkit` builds the objects (pinned zig,
  the same bytes on any machine, G2's record); rebuild after editing a
  source. A shim includes only the headers shimkit writes from the facts
  (`azurik_vanilla.h`, `azurik_kernel.h`) or one of its own beside it in
  `shims/`; nothing vendored (GPL) reaches a shim (AZ-099, Q85). A new shim
  pack starts with `python -m devkit re new-shim NAME --hook VA`
  (`devkit/re/README.md`); the layout, the carver and the kernel stubs:
  INTERNALS.md's Packs.
- A pack is done when its cases match their goldens: the facts' sites site
  by site, then G1 per file on both releases (`tests/test_packs.py`).

### Patching and shims: what binds

The how-to is [`docs/SHIMS.md`](docs/SHIMS.md).

- **Pentium III code only (AZ-021):** the Xbox's CPU has MMX and SSE, no
  SSE2. shimkit compiles at `-mcpu=pentium3`; xemu runs SSE2 code anyway and
  only real hardware faults on it. Check an object: `objdump -d <object>.o |
  grep -E 'sd[[:space:]]|cvt[a-z]*sd'` prints nothing; L1
  (`devkit/sim/l1.py`) refuses any instruction a Pentium III lacks and a
  misaligned m128 in patched code.
- **Keep the callee's contract:** a hook that replaces a CALL keeps the
  callee's `ret N` and return registers (a NOP'd stdcall CALL once gave a
  black screen). A game function a shim calls is a facts `functions` entry
  (its VA, convention and argument bytes), confirmed at the callee's `RET N`
  (stdcall and thiscall) or its callers' `ADD ESP,N` (cdecl) at two or more
  call sites, cited as VA + N in the commit body; an argument in EAX, ESI or
  EDI needs shimkit's thunk (`THUNKS`), and register inputs are checked by
  eye at the call sites. A new site, hook or function owes Europe's address
  or a named absence in `facts.europe.json`. The prologue guard failing
  means a mid-function VA: fix the VA, never `PROLOGUE_FIRST_BYTES`.
- **A config.xbr cell is edited only once the engine is shown to consume
  it** for what the edit wants: garret4's `hitPoints` is loaded but unused
  by the player (`player_max_hp` writes `settings_foo`), `runSpeed` is the
  live walk base while `walkSpeed` is the walk-to-run threshold, and the
  old "dead armor table" is `attacks_anims` (`azurik-game-reference`).
- **A patch is done when its behavior is seen, not its bytes:** a gameplay
  change is done once (1) the facts hold its sites and the goldens its cases;
  (2) it is seen once in xemu, built from vanilla with only it, under
  conditions that reach its code, one sitting per stack
  (`azurik-xemu-oracle`), a movement slider also in L2 at the value the game
  consumes (`tests/test_simulator.py`); (3) its outcome is written in its
  subsystem's RE doc (`docs/RE_MOVEMENT.md`, `docs/RE_DATA.md`,
  `docs/RE_XBE.md`), or the doc says it is unverified, or the pack goes.
- **The HDD cache:** the game plays its cached copy of a prefetch-listed
  file until that file's `filelist.txt` line (md5, size) changes; every
  build writes through `core/iso.py`, which rewrites the line, and a new
  build path must too.

## The randomizer

- **The planner** (`src/azurkit/tools/randomizer/`): `plan(recipe)` fills
  the database's authored levels for a seed under its settings and needs no
  image. The same inputs give the same plan on every host and under any
  hash seed (`tests/goldens/rando_plans.json`, on CPython and Pyodide).
- **Movement sliders** (D1064, D1066) pick the tier the seed is filled at
  (`movement.played`, `data/slider_tiers.json`); a seed with any gameplay
  slider moved isn't promised beatable, says so, and its `logic_verified` is
  false.
- **The shipped database** (`dbcache.py`): generated at the wheel's and the
  frozen app's build (`web_tools.ship_database`, under `PYTHONHASHSEED=0`,
  never `python -I`), never in the tree, and never a cache on disk a program
  writes (a pickle read back runs its code).
- The fill runs in the caller's thread, and each progress note
  (`core.progress.note`) is a cancel point; a bar never goes back.
- **Seed difficulty** (D1157; `planner/difficulty.py`, `planner/fill.py`,
  `native/fill.c`): Normal enters none of it, its plans, files and strings
  byte for byte today's. Any change that gives the same inputs another
  level > 0 placement bumps `SEED_DIFFICULTY_FILL` and leaves `GENERATOR`
  alone. The kernel and its twin agree bit for bit
  (`tests/test_native.py`), and a plan is the same at any width.
- **The generator layer** (`generator.py`): a build's `randomizer` is
  written as its first layer, before the packs; `edits.manifest.image`'s
  `judge` reads the image back against the plan before anything is written:
  a difference a later layer explains is a conflict and `logic_verified`
  false (D28), any other fails the build by location (D35). The tools never
  import each other.
- **The tracker** (`tracking.py`) and the page's map are held to
  `tracker.json`'s verdicts. An item shows only once collected or with the
  spoiler: a spot not shown is a plain dot, so an icon never spoils a seed.
- **The pictures** (`art/`): only `scripts/record_goldens.py`'s `art` family
  writes `web/art/`, drawn from the USA image; `tests/test_art.py` holds
  `ART_VERSION` to the drawing's sources, so a change to what draws them
  moves it and they are recorded again. No host draws them.
- **Live** (`live/`) is the app's alone (D882): the fork's shared guest RAM
  or QMP, never a gdbstub (D257); the tracker imports only the events, so the
  site never loads the link.
- The rest in full: INTERNALS.md's The randomizer.

## Characters

- **The swap** (`tools/characters/`) is AzurKit's own since Step 4.12c:
  `_player_character.apply_player_model` dresses the player in a species'
  body, its clips, attacks, weapon, sounds, fx and the shims it hooks into
  `default.xbe`. Its parallel work (`pool.py`) gives each item's result in
  order, so no byte depends on a host's pool.
- A recipe's `character` is checked by `tools.characters.normalize`; a
  `variant_file` names files beside it, and a layer's recipe keeps the
  variant's sha and its file's name, never its folder. In a share link a
  `variant_file` is refused by name (Q174).
- **Your own variants** (`library.py`, `AZURKIT_VARIANTS`, else `variants`
  in the user data folder): New, Save, Save as, New from this and Delete
  check first and write whole or not at all (D35); every key an answer is
  kept under stands on what a build reads (`library.stamp`, by sha256),
  never a name or a path.
- **The content folder** (`content.py`, `AZURKIT_CONTENT`, else `content` in
  the user data folder): the files Azurik-Custom-Content carries, never this
  repository or the wheel (D869, D965). Install checks each file as it lands
  and writes nothing on a fault; an Update only goes up, only from the source
  it came from (SEC-8); a URL source is https (http only on this computer);
  the engine opens no connection. A build that needs a file the folder lacks
  fails naming it.
- **Shipped answers** (D995, `shipped.py`): a row is taken in place of a
  dress only where it stands on what that dress would read. The re-record
  pin: a change to the swap's bytes is red until `scripts/record_shipped.py
  --content <a clone of Azurik-Custom-Content>` re-records, and her entry
  then takes the new files at a new version; every dress the goldens make is
  fresh (`shipped.OFF`).
- **A dress's parts** (`parts.py`, `part_codec.py`) are keyed on what their
  stage reads (a file by its sha256), never the variant's name, folder or
  path; the part codec keeps no pickle.
- **The character layer:** a swap writes `characters.xbr`, `fx.xbr` and
  `index.xbr` whole, one group (`Change(..., whole=True)`), the rest as
  ranges; a later range lands over a whole file only where it kept the
  vanilla bytes, and is refused where it changed them (D35, AZ-096). It
  stacks after the packs, before the Data tool's `xbr` operations.
- **Its checks** are `tests/test_characters.py`'s. The rest in full:
  INTERNALS.md's Characters; authoring: `devkit/models/README.md`; a
  recipe's fields: `docs/VARIANTS.md`.

## The engine's contracts

- **Layers:** `core <- edits <- tools <- sdk <- {cli, app}`. The five tools
  (`mods`, `randomizer`, `characters`, `data`, `saves`) never import each
  other. import-linter holds this (`pyproject.toml`).
- **AST rules:** `core`, `edits` and `tools` hold no threads, processes,
  subprocesses, prints or exits, so the web page's worker runs them as they
  are. The worker loads the wheel without its dependencies, so the engine
  imports platformdirs only where it needs the user data folder. Only
  `tools/characters` and the randomizer's drawing (`tools/randomizer/art/`,
  `draft/`) import numpy, and nothing imports capstone, unicorn, zig, Tk or
  `devkit` (which never ships). `tests/test_contracts.py` checks these.
- **The same transcendental bits on every platform (AZ-830):** the swap's
  and the XBR graphs' transcendental math is `core/fdlibm.py`'s, and a power
  is `fdlibm.sq`, `cube` or `pow`: no `math` or numpy libm call and no `**`
  but an integer's there (`draw.py`, which writes no built byte, keeps
  numpy's). `tests/test_contracts.py` holds this.
- **Across machines the bits may differ (D1016, AZ-833):** no test or build
  requires identical float bits between machines or hosts; one host's
  builds stay exact, and so does D35's read-back. Where a build's float
  maths can differ, a test keeps a reference per platform or compares close
  enough (integer fields, sizes and layout exact, floats within a few ULPs).
- **The compiled kernels (D1009):** a hot loop may be C99 in `native/`,
  built only by `python -m nativekit` (pinned zig, six targets, committed in
  `src/azurkit/core/_native/`; `--check` rebuilds the same bytes), with no
  float contraction (`-ffp-contract=off`), no fast math and the targets'
  baseline CPUs. A kernel is a pure function over caller buffers (no
  allocation, no libc), and keeps its Python twin in `core/native.py`, the
  reference: the twin runs without a library, past the library's limits and
  under `AZURKIT_NATIVE=0`, with the same answer bit for bit
  (`tests/test_native.py`, natively and under Pyodide). Each kernel:
  INTERNALS.md's The engine's contracts.
- **The hosts' hooks** (`progress`, `gate.STAMPS`, `characters.CACHE`,
  `parts.STORE`, `pool.MAP`, ...) are each `None` or off by default.
- **The store** (`src/azurkit/store.py`, D1015): each entry sealed whole and
  read back only whole, sealed and of its kind's form (a torn, altered or
  moved entry is a miss, never decoded); its kinds keep JSON or AZKP1, not a
  pickle (`swap`'s bytes aside, INTERNALS.md); one budget (`store.BUDGET`); it removes only files of its own
  names in its kinds' folders, never a player's settings, content or key,
  and starts no thread.

## The two hosts (D866)

- **The page** (`web/`) is one page for both hosts (`host.json` names the
  host's engine) and decides no output byte; the engine decides every
  answer (the page sends the choice and draws the answer). Its CSP has no
  `'unsafe-eval'`, it uses no eval, no host evaluates script in it
  (pywebview's `evaluate_js` would need eval), and text reaches it only
  through `textContent`.
- **Its design** is A, the dense tool (D900): the tabs are the catalog's
  (`sdk.TABS`), each only once its area works (D902). A long call shows its
  progress in the bottom bar (D980), and a control that can't work yet is
  greyed with the line that says what it waits for (D979), never a blank or
  silent wait.
- The About tab restates `LICENSE` and `NOTICE.md` (`tests/test_site.py`
  holds them); its privacy line says only that AzurKit collects nothing and
  that the image never leaves the computer (D883).
- **What a page keeps or shares** (the remembered setup, D915 and D1156; the
  tracker's marks; share links) is names, numbers and hashes, never the
  image, its path or anything read from it (Q174); a share link refuses a
  replaced file by name (SEC-11), and a setup is kept only with Remember
  settings ticked, nothing at the defaults.
- **The site:** Pyodide in module workers from a `blob:` URL, the wheel
  without its dependencies; the worker holds one PyProxy, its engine
  function, which hands back plain JS values (`NoGilError`, Step 4.1d3). Its
  Save is checked against the build (D35). `web/sw.js`, the service worker,
  serves a release only whole and checked by sha256, and a page never runs
  another release's engine.
- **The app** (D732, `python -m azurkit`): it serves the page on 127.0.0.1
  to this launch's token only, from the page's own origin; builds, saves, a
  seed's plan and the Characters tab's pictures and G4 match run in its
  engine process, so the server's other answers never wait. Save writes a path, never over an
  existing file but one the save dialog chose; closing cancels a build or a
  save and never leaves a part file (AZ-823, D35). What it keeps across
  launches is signed under the install's own key, and a file not this
  install's is a miss, never unpickled (SEC-4). The bundle is read-only
  (every write through platformdirs or the player's path) and carries no
  Unicorn, zig, capstone or GPL code (`tests/test_hosts.py` checks each
  name and licence); pyinstaller and pywebview are the `app` group, never
  the wheel's. The window sets pywebview's `text_select`. A script that
  calls `app.main` guards it with `if __name__ == "__main__"`.
- **The icon** (D891, D892) is original art that code draws, no game pixel
  (`assets/icon/`); `tests/test_icon.py` holds the SVGs to their generators.
- Every tab, the site's workers and the app's engine in full: INTERNALS.md's
  The two hosts.

## Commits and landing

- **Lanes:** one lane per step, a worktree in `../AzurKit-lanes/<step>` on a
  `p2/<step>` branch. Lanes commit locally, and only the orchestrator moves
  `main`.
- **Commits:** a fix is one commit with its test. Name the step in the subject
  (`fix: … (Step 4.1c)`) and keep the body to a few lines. Stage explicit paths:
  never `git add -A` or `.`.
- **Protected paths:** a commit that changes one names each in its body, and
  why: `tests/goldens/` (only `scripts/record_goldens.py` writes it), the
  facts (`src/azurkit/core/facts.<release>.json`), the release manifests
  (`src/azurkit/core/manifests/`), the shim objects (only `python -m
  shimkit`) and `shimkit/`, the native libraries
  (`src/azurkit/core/_native/`, only `python -m nativekit`) and
  `nativekit/`, `tests/sdk_api.txt` (only `scripts/sdk_api.py`),
  `tests/skip_allowlist.toml`, `tests/conftest.py`, `tests/_*.py` (the leak
  guard among them), the drift guards' tables (`PROLOGUE_FIRST_BYTES`),
  `pyproject.toml`, `uv.lock`, `bootstrap.py`, `CLAUDE.md` and `.claude/`.
  Each file a command writes is held to it by a test (Step 4.24c).
- **Ids:** an AZ, D or Q id comes from the private ledger: `$EV/tools/ledger
  take AZ "slug: one line"` (`ledger next` prints the next free ones). Never
  write an id or the ledger's pointer by hand. A lane whose prompt says not
  to take ids reports the loose end instead.
- **Reviews by default (D288):** a correctness review after every code step
  and a skeptic after every xemu sitting; a tiny docs- or test-only change
  skips it, and so does a rebase whose only conflicts are docs, the ledger
  or goldens (D779). A sitting's review runs beside it, both on the build
  commit (D778). A builder checks its own work first; a reviewer never
  edits.
- **Never:** attribution trailers, force-pushes, `--no-verify`, `git stash` or
  git config changes.
- **Change notes:** each change adds one Markdown bullet in a file of its
  own, `docs/devlog/<added|changed|removed|fixed>/<step>-<slug>.md` (ids
  welcome there: one bullet, its further lines indented two spaces), which a
  release joins into `docs/DEVLOG.md` and deletes (`uv run --locked python
  scripts/devlog.py --release TITLE --remove`); a change a player would
  notice also updates the guide's features (above). `docs/DEVLOG.md` merges
  with git's union driver, so never autosquash over commits that edit one
  bullet; where a release holds one bullet twice, keep the newer.
- **The gate:** run `uv run --locked python scripts/fullsuite.py <worktree>
  --changed`. It runs the lint files in the foreground, then the changed
  area (its `plan()`: the test files that import or name what changed; a
  path no rule covers runs the whole suite) with the gate's USA and Europe
  test in the background under a lock, on 8 workers, and prints a key and a
  receipt path. Once a changed-area run passes, its flake stage runs each
  test function the stack adds or edits 5 times, slowed; `land.py` needs it
  passed. `--wait 540` waits for the result; exit 3 means it is still
  running, so issue the same command again. The plan's rules, the flake
  stage and the caps: INTERNALS.md's Commits and landing.
- **The perf gate (D980-D985, D1170):** once pytest passes, the same run
  times the player-facing operations the changes reach (`scripts/perf.py`,
  `tests/_perf.py`): an op over 3 s (or its ceiling in
  `tests/perf_ceilings.toml`), past 1 s with no progress, or whose page froze
  is a perf-debt row, a lane, not a block. It blocks only on a clear
  regression against the last release (25 % and 0.5 s), an op it measured
  that errs, a memory peak, a native failure or a list that grows; the list only shrinks (`perf.py
  --update-ceilings`, in your own commit).
- **Landing:** `uv run --locked python scripts/land.py <branch>` fast-forwards
  `main` once a passing receipt covers the branch's head with `vanilla: N run`
  and `europe: M run`, N and M at least 1 (D26), and, for a stack that
  changes `src/` or `web/`, a perf block in which nothing blocks (its own, or
  for a deferred one, `--perf-later`, a later receipt's of its batch covering
  it, D1215); it refuses any stack whose perf list grows main's. Landing never waits for a release
  (D1170): a release is a tag on a commit that is on `main`, cut from main
  whenever its tests pass.
- **CI (D1022-D1024):** `tests.yml` runs the pure tier on every push and
  pull request on the four platforms the apps ship for, and the vanilla and
  europe tiers on a push to `main` or a lane branch in this repository alone
  (D1123), the images rebuilt from the game-data repo's parts with
  `GAMEDATA_DEPLOY_KEY` (the only secret a workflow reads), never cached,
  uploaded or printed, and deleted after. Only `release.yml` deploys the
  site, uploads to PyPI or makes a release (on a `v*` tag whose name is
  pyproject's version and whose commit is on `main`; a dispatch is its dry
  run, D1068), and no workflow tags. Workflows hold `permissions: contents:
  read`, no `pull_request_target`, and actions pinned by commit sha with
  their release beside it; `actionlint` passes on each.
  The jobs, shards (`scripts/ci_shards.py`, `scripts/ci_matrix.py`) and
  caches in full: INTERNALS.md's Commits and landing.

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
- **The xemu harness** (`devkit/xemu/oracle.py`, `python -m devkit xemu
  oracle CMD`; `devkit/xemu/README.md`) runs sandboxed clones of the owner's
  xemu fork on the oracle's fixtures, never the owner's own xemu, never a
  visible window but an owner demo's, at volume 0, each admitted by its
  slots (D108); how to sit is the `azurik-xemu-oracle` skill. Agent save
  states never go on the oracle's drive (D102). No test launches xemu
  (D108): `tests/test_xemu_harness.py`'s are offline (marked `xemu`).
- **Ask nothing (D115):** where a decision is missing, take the recorded default
  or your recommendation, and say so in your report.
