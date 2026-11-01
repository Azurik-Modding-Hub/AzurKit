# AGENTS.md: rules for agents and contributors

AzurKit is the lean, public rewrite of Azurik_Modkit. Modkit is its reference
only: every family's truth is AzurKit's own (The goldens, below), the core's
and the packs' since Step 4.12a, the characters' since Step 4.12c and the
randomizer's since Step 4.12b, each first recorded at Modkit's last cut. A
later Modkit result reaches AzurKit as a hand port (Porting from Modkit).
[`README.md`](README.md) says what AzurKit is. These rules bind.

**README's features:** a change a player would notice adds or updates its
line in README.md's Features (and Highlights if it earns one), in the same
commit. Each line is plain and short, with no step, D or AZ ids, and true on
`main`.

## Where knowledge lives

| Home | Load it for |
|---|---|
| This file | the rules: setup and tests, game data, the goldens, porting from Modkit, packs, the randomizer, characters, the engine's contracts, the two hosts, commits and landing |
| `azurik-game-reference` (`.claude/skills/`) | VAs, structs, ABIs, measured movement and armor numbers, patches whose bytes landed with no in-game effect |
| `.claude/agents/` | the seats' roles (D951's `azurik-*` names): `azurik-builder` (Opus: build, fix, gate, sitting), `azurik-reader` (Opus, read-only: RE, reads, reviews, skeptics), `azurik-scout` (Sonnet, read-only: locate and cite), `azurik-mechanic` (Haiku: a command list handed over); `tests/test_agent_files.py` pins each one's model, effort and denied tools |
| `$EV`, the private evidence folder beside the main checkout | the brief (`$EV/tools/BRIEF.md`), the decisions, the ledger, plans, evidence and the tools the seats run (D951, D952); never copied into the repo |
| Modkit (`$AZURKIT_MODKIT`, else `Azurik_Modkit` beside the main checkout) | the reference: its skills and docs not ported yet |

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
uv run --locked python -m nativekit [--check]         # the compiled kernels' libraries, from native/*.c (zig, dev only)
uv run --locked python -m devkit [AREA [VERB ...]]    # the developer side (D950, dev only): devkit/README.md
uv run --locked python scripts/record_goldens.py [--check] [GOLDEN ...]   # tests/goldens/ from the player's images
uv run --locked python scripts/record_shipped.py [--check] [--content CLONE]  # the swap's shipped answers (D995)
uv run --locked python scripts/gen_facts.py [--check]                     # the facts' XBE half from the images
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
- **Skips:** a skip or an xfail fails the run unless `tests/skip_allowlist.toml`
  lists it, and that list is empty. Failures never become skips: no new
  `skipif`, `SkipTest` or `xfail`, and no allow-list entry to get green.
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
  private key, an EEPROM dump, an xemu HDD (qcow2) image or a guest RAM
  snapshot (`AZL3SNAP`): the last three can hold console keys.
  - `tests/_leak_guard.py` refuses them in the suite and on every push,
    also inside a gzip file. Its rules have no allow-list.
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
  - Only `scripts/record_goldens.py` writes them, from AzurKit's own builds
    on the player's images (`--check` writes nothing); never edit them by
    hand. It records the page's shipped pictures too, by family (`art`:
    The maps; `characters`: The Characters tab, below). A commit that changes one names each golden it changed and why,
    and a gameplay byte change to a default build is seen once in xemu.
  - The first recording is Modkit's last cut (the packs and the core:
    oracle-packs-4, Modkit 28d0b4110; the characters: oracle-models-3,
    Modkit 1648692; the randomizer: oracle-rando-6, Modkit 8bfef0ca6),
    which the recorder's first run wrote back unchanged but the files
    AzurKit can't build (AZ-009: G3's `seed=0,all` leaves out
    `training_room.xbr`, `filelist.txt` and `ISO`, as the packs' three
    level-patched cases do); the randomizer's plans gained their spoiler's
    sha256, `tracker.json` was recorded equal to Modkit's own tracker's
    digests, and Modkit's `rando_iso.json` (the default plan's sha256 and
    its seed build's image, both pinned above) was left out.
  - The cases that wear booblord read her files in the content folder
    (`AZURKIT_CONTENT`, `azurkit content install booblord`); the builds
    that dress the player run in `--workers` processes.
  - A new pack adds its cases to `cases.json` (its defaults in `packs.json`,
    `sites.json` and, for an XBE pack, Europe's), then records them.

## Porting from Modkit

- **The cut:** the randomizer (its database, planner, writer, physics,
  movement, layer and tracker, Live's game reads and link, and the maps'
  and icons' drawing) was ported from Modkit at oracle-rando-6, Modkit
  `8bfef0ca6` (Step 4.12b, the last sync), and is AzurKit's own since:
  edit it here, held to `tests/goldens/` and `tests/test_contracts.py`.
  Modkit's later randomizer results (R2.16g's tiers and skips, a fix) come
  by hand, in these steps; the orchestrator runs the first at each AzurKit
  randomizer step.
  1. **The to-do:** Modkit's commits on the ported paths since the cut
     (`planner/dbcache.py` is AzurKit's own `tools/randomizer/dbcache.py`;
     the reach engine's code, `reach_native/`, `draft/reach.py` and the
     flights, isn't ported: its results arrive through `data/`):
     ```bash
     git -C "$MODKIT" log --oneline 8bfef0ca6..origin/main -- azurik_mod/randomizer/{data,planner} \
       azurik_mod/randomizer/{writer,physics,movement,layer,tracker,live,live_link,levels}.py \
       azurik_mod/randomizer/draft/{__init__,envelope,geometry,floors,wiring}.py azurik_mod/randomizer/draft/tiers.toml \
       azurik_mod/sim/{pages,recipes}.py azurik_mod/xbr/{nodes.py,node_types.json,tern.py,collision.py,render.py,draw.py} \
       scripts/render_{level_maps,model_icons}.py gui/assets/{maps,icons} tests/goldens/{rando_plans,pipelines,europe/pipelines}.json
     ```
  2. **Data** (`data/**`, `draft/tiers.toml`): copy each file as Modkit has
     it (`git -C "$MODKIT" show <ref>:<path>`), new and removed files too.
  3. **Code:** apply Modkit's diff of the file (`git -C "$MODKIT" diff
     8bfef0ca6..<ref> -- <file>`) by hand to AzurKit's module, with
     AzurKit's imports: `azurik_mod.randomizer.X` is
     `azurkit.tools.randomizer.X`; `live` and `live_link` are `live.game`
     and `live.link` (`LiveError`: `live.errors`); `sim.pages` and
     `sim.recipes` are `live.pages` and `live.recipes`; `assets.vanilla`'s
     regions are `live.regions`; `xbr.nodes` and `xbr.toc_scan` are
     `azurkit.core.xbr.nodes`; the other `xbr` modules and the two render
     scripts are `tools/randomizer/art/` (`maps.py`, `icons.py`);
     `draft.reach`'s `Reach` is `art/reach.py` (its first stage);
     `xbe_layout`, `resolve_va_to_file`, `listed` and `XisoReader` are
     `tools/randomizer/ports.py`; `planner.dbcache` is
     `tools/randomizer/dbcache.py`. Leave out what AzurKit dropped: the
     seed roll's pool (`fill.roll_seed`), layer's build objects
     (`check_args`, `write_layer`, `check_movement`, `movement_reasons`,
     `judge`, `outputs`, `write_outputs`), physics' `SOURCE_SHA256`,
     movement's slider ranges, the tracker's file reads (`placements`,
     `plan_doc`), live's `connect`, the L2 flights (`envelope.l2_*`), the
     levels extractor (`extract`, `write_generated`), `nodes.scan_types`,
     and the drawing's command lines and PNG writers. A Modkit import with
     no AzurKit home is ported into an AzurKit module first
     (`tests/test_contracts.py` holds the layers: no threads and no libm in
     byte paths).
  4. **Check:** `azurkit plan --seed 2` (the database loads), then
     `tests/test_randomizer.py`, `tests/test_art.py` and
     `tests/test_site.py`'s tracker tests.
  5. **Record:** `scripts/record_goldens.py rando_plans.json pipelines.json
     europe/pipelines.json tracker.json`, and `art` when `ART_VERSION`
     moved (`data/generated`, `draft/`, `art/` or `levels.py` changed: a
     new `web/art/<version>/`). The commit names each golden and why.
  6. **Cross-check** (evidence, not a test): the re-recorded
     `rando_plans.json` rows (attempt, sha256, the default plan file) and
     G3's seed rows equal Modkit's at `<ref>` (`git -C "$MODKIT" show
     <ref>:tests/goldens/...`; AZ-009's files aside). A difference is a
     port bug until it is named.
  7. **What a player sees**, on both hosts: README's Randomizer lines (the
     skips, tiers, levels and locations), the Randomizer tab's lists where
     the database doesn't give them, and old `AZR-` share strings, each
     still decoding or refused by name.
  8. The perf gate times the randomizer and tracker groups: a ceiling
     crossed is the port's to fix (D835). It owes an xemu sitting only when
     the writer's or the layer's bytes change.
  9. Move the cut above to `<ref>`.
- **Coverage:** Modkit's planner tests don't guard AzurKit's copy. A step
  that edits a module from the cut ports the Modkit tests that pin what it
  changes, or names the golden that pins it.
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
  the sdk refuses a recipe without them, by name (`mods.missing`); the CLI
  leaves out a pack on by default with one it requires (D588); the page ticks
  them with it and unticks it with them. G1 builds each pack alone, so such a
  pack's case is its layer's image.
- **XBR** (`core/xbr/`): `Document` parses an archive's header, TOC and
  trailer, and config.xbr's keyed tables (`keyed.py`), and `dumps()` writes
  them back (every vanilla XBR round-trips, `tests/test_xbr.py`). An edit
  (`edits.py`) is the writes `[(offset, bytes)]` that make it, planned
  against the file as parsed; every cell is 16 bytes, so nothing grows.
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
- **Community packs** (D988, `tools/mods/community.py`): an
  Azurik-Custom-Content entry of kind `pack` whose one file,
  `packs/<id>/pack.json`, is a mods file of a `mods` packs layer and a
  `data` xbr layer only: release-free (no `base` or `result`), data only (no
  randomizer, character, XBE site or code), its packs carrying every pack
  they need (`check`). `refusal` is the content folder's Install check of a
  pack entry, for `content.verify`'s `refusal=` hook (S1's), which the sdk
  passes from the hub half (H3); until then a pack entry installs with only
  the size, sha256 and disc-image checks (`tools.characters` may not import
  `tools.mods`). A recipe pins one by id and its pack.json's
  sha12 (`normalize`), and `resolve` takes it only installed, untouched
  since and at the pin, naming what to Install or Update. Its built-in packs
  `merge` with the recipe's own (a pack two sources set to other values is
  refused, naming both and the slider; equal copies are one; nothing is
  unticked) and plan as ordinary pack layers; its edits are a layer of
  their own (`layer`, `community <id>`) for the sdk to lay after the packs
  and the character and before the player's own `data xbr`, so a later
  layer wins, reported (D28). A build's manifest records it by id, version
  and sha256, never its bytes, and `edits.preset.from_manifest` gives it
  back as the mods file's `community` layer, `{"packs": [{"id", "sha"}]}`.
  No pack ships (D997), so no golden records one: fixture packs in
  `tests/test_community.py` pin them.
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
- A pack is done when its cases match their goldens: the facts' sites site
  by site, then G1 per file on both releases (`tests/test_packs.py`;
  `tests/_g1.py` reads G1, whose Europe half has no case for a
  config.xbr-only pack: the file is the same in both releases, so its USA
  cases stand for it).

## The randomizer

- **The planner** (Step 4.2a; `src/azurkit/tools/randomizer/`): `plan(recipe)`
  fills the database's authored levels for a seed (any string) under the
  database's default settings (D144), a settings file's table (`settings`)
  or a share string (`share`; its movement sliders re-check the logic the
  fill reads, AZ-383), and returns Modkit's plan file's object;
  `spoiler(doc)` reads one back. The sdk's `plan` and `spoiler` and the CLI's
  `azurkit plan` and `azurkit spoiler` call them. A plan needs no image.
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
    its million objects' full walks held the app's server 0.8 s).
  - The engine's progress notes are one stream (Step 4.3 train B3):
    `core.progress.note(text)` from the fill ("placing the items", then
    "placing the items, k of n", k the item it is placing of the n steps
    an attempt takes, each item a reach places a step and the rest, placed
    at once, its last, so the count moves as the reaches' time goes; each
    percent and at each reach), the logic's checks as
    a checkout reads it cold ("checking the levels, 5 of 15", then
    "building its logic") and the tracker's exits ("the maps' exits, k of
    22"). `core.progress.noting`, the calling thread's (`randomizer.plan`,
    `sdk.image`, `sdk.tracker`, `sdk.spoiler`, `sdk.randomizer_logic`),
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
- **The generator layer** (Step 4.2b; `generator.py`): a build recipe's
  `randomizer` (the planner's recipe and an `obsidian_cost`; `azurkit build
  --seed`) is planned on the logic re-checked under the build's movement
  sliders (Modkit's `layer.plan_for`: a run under garret4's falls back to
  his, AZ-606) and written as the build's first layer, before the packs
  (Modkit's `mod_apply` order): one group a node graph (its new strings,
  TOC size and repointed name fields land whole), one for the obsidian
  locks, and one a species for the contained touches (`contained`, AZ-834:
  a species the image holds once, on a spot a container encloses, whose
  pickup reaches further than the vanilla item's there takes that item's
  `collisionRadius` and `collisionAspectRatio` in config.xbr, so it is
  taken only once the container opens; one held more than once keeps its
  own). `edits.manifest.image`'s `judge` reads the image back against the
  plan before anything is written: a difference a later layer explains (it
  wrote the location's fields or string or a touch's cells, or dropped its
  group) is a conflict and `logic_verified` false (D28), any other fails
  the build by location (D35). The movement check reads the packs' catalog (each
  slider's `logic_floor`, D83(c)); the tools never import each other. The
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
  `reset`, the head line, the counter row, each spot's state (`got`,
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
    its release's vanilla file (`art.Vanilla`): the icons (every item's and
    barrier's, the game's own model at 20 px), or a level's floors seen
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
    with the call beside it), kept for the next, but one that has peaked
    past `RETIRE` (256 MiB; not on Windows, which has no peak to read), which
    leaves after its part so its heap goes back to the OS, through pipes alone; the
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
    the files a recipe names are read beside it), its shapes sized by
    `shapes` (`--player-shape`); an option a recipe gives must be the
    variant's, its scale and attack numbers multiply the variant's
    (`tools.characters.variant`). The layer's recipe keeps the variant's
    sha, and its notes the file's name, never its folder.
  - **A seed with a character** (Step 4.3c2, Modkit's `randomize-full
    --seed` with `--player-character`): the sdk plans the randomizer after
    the body's size is folded into the walk and roll, so the plan stands
    on them, and the swap reads the files the randomizer and the packs
    left; the body's reasons (`characters.reasons`, Modkit's
    `layer.movement_reasons`' model half word for word: a body no sitting
    graded, no melee idle swing, a weak or endless attack, a body shorter
    than garret4) join the packs' in the verdict, leaving the logic
    unverified, never refused. G3's `seed=0,all` (flicken) is Modkit's on
    both releases but `training_room.xbr` (level_patches, AZ-009), its
    verdict Modkit's word for word.
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
    Update. The engine opens no connection: the sdk's CPython calls fetch,
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
      files at a new version. `--check` re-derives every row (the release
      check's, and the only pin of the sizes no golden builds: a stale one
      fails that body's build by name, D35, its size not the folded one).
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

## The engine's contracts

- **Layers:** `core <- edits <- tools <- sdk <- {cli, app}`. The four tools
  (`mods`, `randomizer`, `characters`, `data`) never import each other. import-linter
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
  by the side module from the wheel, in the site's worker.
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
  a pickle; `swap` keeps the bytes `characters._kept` and `engine._kept`
  still pickle, until they move to `dresses` and `memos`/`pictures`. One
  budget across the kinds (`store.BUDGET`, 5 GiB): a write past it removes
  the least recently used entry, whatever its kind. It removes only files
  of its own names in its kinds' folders, never a player's settings,
  content installs or key. It starts no thread, so the page's worker can
  run it.

## The two hosts (D866)

- **Engine halves no host calls yet** (each tested alone; its hub half wires
  it): the work ahead (`app/ahead.py`, `web/workers.mjs`), the warm-up
  (`app/warm.py`, `web/warm.mjs`), the kept answers (`app/memo.py`,
  `web/memo.mjs`), the service worker (`web/sw.js`), community packs
  (`tools/mods/community.py`, `web/content.mjs`), Replace files
  (`edits/files.py`) and Saves (`tools/saves/`).
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
    250 ms; the site's worker's `progress` posts, the image's check among
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
    nothing and that the image never leaves the computer (D883).
  - **The Randomizer tab** (Step 4.2c1, RANDOMIZER_PLAN §5.5): Randomize
    (off by default, the tab's one switch, which unlocks its settings,
    D907), the seed (any text; New draws 0-999999), Movement, the skip
    ceiling, the fire dark areas need and the obsidian cost (vanilla 10,
    D910), with D144's defaults (`sdk.catalog`'s `randomizer`), the share
    string (editable, Copy), Load settings… and Save settings… (D144:
    a settings file, read and written by the engine: `randomizer_settings`'
    `file`, the app's `api/settings_file`), the item rows (each a category
    it shuffles, its icons, the page's own drawings, and how many the base
    game places, `tools.randomizer.base_counts`; keys and barriers stay
    vanilla), the skip groups (D258, `tools.randomizer.SKIP_GROUP`, every
    skip of the database in one: a ticked group turns on its picks rated at
    or below the Movement tier, as toggles the page adds where the ceiling
    doesn't; a loaded setting shows them as toggles, the groups unticked)
    and the skips a setting can turn on (a click toggles one against the
    ceiling and the groups). The page holds the settings as
    a settings table in format /2 (each category as it is) and asks the
    engine what they give (`sdk.randomizer_settings`; the site's worker,
    the app's `api/randomizer`): the share string with the Patches tab's
    movement sliders and the Characters tab's body's size folded into the
    walk and roll as its build folds it (`character`, sized on the picked
    image: the site's worker mounts it for the ask; with none, a ⚠ line says
    the plan stands on garret4's), so Track this seed plans a character
    build's plan, the skips, and a ⚠ line for the preflight's refusal
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
  - **The maps** (Step 4.2c3, R1.41, R1.43; shipped since Step 4.3f, D961;
    `web/art.mjs`, `web/mapview.mjs`): Modkit's pictures of every level's
    floors, the world map and the item icons, with the maps' index
    (`maps.json`) and the floor table (`floors.json`), ship with the page in `web/art/<ART_VERSION>/`, and
    `web/art/index.json` names that version and the icons. Only
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
    exits once one is tracked), and a level as Modkit's map view on a canvas: its picture by floor (the floor
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
    back, on both hosts; a variant's from one dress, `sdk.preview`), its
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
    pictures at its click, with no image and no engine call, and G4 and the
    Weapon box stay greyed, saying the image is needed, until the engine's
    answer has read it (D979). Content from (the source; default `sdk.SOURCE`, the hub's raw URL, live
    since the content repository went public, D1027) is remembered (the
    site's storage, the app's `content_source`).
    The site reads a source on its own address only (its CSP's
    `connect-src 'self'`; `scripts/web_tools.py --site DIR --content
    CLONE` serves a clone as `./content-source/`), checks an Install in
    its worker (`sdk.content_check`), keeps the files in IndexedDB and
    writes them into its worker's `content/` once a worker; the app's
    engine installs into its content folder. A known flaw (D835): on the
    site a detailed variant's dress (booblord's) may run out of wasm
    memory; the page then says to use the app. 4.4 waits until every site
    build fits the capped profile's 6 GiB (D1021: no use-the-app fallback).
  - **The Data tab** (Step 4.7a, `web/data.mjs`; D986, Modkit's Game Data
    editor): config.xbr's cells before an image (`sdk.data`, from the
    vanilla file `tools/data` ships): the Player, Critter, Item, Armor and
    Weapon views and All tables (a grid: sort, Changed only), its entities
    in the shared picker (`web/picker.mjs`, whose species list and rows
    the Characters tab uses too). A cell's edit is checked by the engine
    (`sdk.data_edit`: any finite number, D23; refused only where the
    cell's encoding can't hold it, D45) into the recipe's `xbr` `set`
    operations, which the tab keeps (Undo, Redo, Revert, Reset table,
    Clear edits) and the page builds with (after the packs), remembers and
    links (`state.xbr`; the Patches tab's line names them); ⚠ marks a cell
    a ticked pack's slider also writes (`sdk._written`: each config.xbr
    slider's spans as a build plans them; a pack a build would refuse
    marks none). The tab asks again each time it shows, so the marks
    follow the ticks; its line says the edits wait for the image to build
    (D979). `tests/test_data.py`, `test_site.py` and `test_hosts.py` hold
    it; `tests/_perf.py`'s A39-A46 and S32-S39 time it.
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
    be kept). What waits for an image is greyed with "Choose your image
    first (1.)" until one is picked, or with the engine's refusal of it
    (D979). The app's saves without a dialog go to the Downloads folder,
    through `writable` (SEC-16). `tests/test_site.py`, `test_hosts.py` and
    `test_edits.py` hold it; `tests/_perf.py`'s A47-A55 and S40-S48 time it.
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
    requires; unticking one unticks those that require it.
  - **An AzurKit build as the image:** the engine's vanilla read (the
    site's worker, the app's `api/vanilla`) falls back to
    `sdk.open_build(whole=False)` (only the files the build changed are
    checked: reading all 2.6 GB takes minutes in WebKit's worker), and the
    page shows "◆ AzurKit build" with Load its recipe, which loads it as a
    link's, to build again from a vanilla image.
  - **The remembered setup** (D915): the page keeps its ticks, each
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
    packs on by default, sets every setting to its default and forgets it.
- **The site** is the page with Pyodide's core (and numpy's wheel, which the
  Characters tab's drawing loads: `web_tools.PACKAGES`), the wheel (with each module's
  unchecked-hash bytecode, so Pyodide doesn't compile the source, and the
  shipped database) and its `host.json` (`uv run --locked python scripts/web_tools.py --site DIR`). Its
  engine runs the wheel, unpacked without its dependencies, under Pyodide in
  a module worker started from a `blob:` URL (so the page's CSP holds there),
  one worker, kept after a build while the heap its answer reports is under
  1 GiB (Step 4.3i: wasm memory never shrinks; app.mjs's `KEEP`), else
  replaced, as after a cancel ("Preparing the engine…"), which reads the
  image in blocks (WebKit takes about 200 ms for each read of a File,
  whatever its size), kept from one message to the next for the last image,
  and checks each image once (Step 4.3h): its build files hashed
  in WebCrypto (`sdk.layout`, `sdk.prime`), the stamp kept in the browser
  (IndexedDB, by the File's name, size and lastModified) for the next
  visit. It posts a build's, a plan's and a tracker's stages as
  `core/progress.py`'s record, and each build's answer reports the heap,
  by which the page keeps the worker or replaces it. It returns the build
  as segments
  (`iso.Image.segments`), which the page joins into a Blob of slices of the
  player's file and the bytes the build writes, and Save downloads it.
  `tests/test_hosts.py` runs the gate under Pyodide on Node, and
  `tests/test_site.py` the packs' G1 cases and a save in Chromium, WebKit
  and Firefox.
  - The worker holds one PyProxy, its engine function, which hands back
    plain JS values: a PyProxy it dropped would be freed by Pyodide's
    FinalizationRegistry, which needs the GIL, and WebKit runs that cleanup
    inside WORKERFS's read of the image, where CPython has released the GIL
    (`NoGilError`, Step 4.1d3).
  - **The service worker** (D1013, Step 4.3z; `web/sw.js`, which no page
    registers yet: the hub's turn, which must also lift `app.mjs`'s `main()`
    stop on a page a service worker controls): `site()` writes the release
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
    it is the release's, else answered 503), adds COOP, COEP, CORP and the
    page's CSP to what it serves, and holds an update until the page takes
    it (`reload`, refused while another of the site's pages is open). An
    install posts its progress and its outcome (`installed`, `failed`) to
    the site's pages; the first takes over at once; an activation deletes
    the scope's older releases' caches. `tests/test_service_worker.py` holds it in the
    three browsers on small sites `site()` writes.
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
  Cancel kills that process mid-build and spawns the next (a save cancels
  itself at its next chunk). A build keeps its image in that process (the
  last build's: a new Build drops it), hashed on a thread from the moment
  it is made (`iso.digest`), and `api/build` answers its id: Save sends it
  back, so `api/save` writes that image (`sdk.save`, the hash taken or
  waited on), or builds the recipe again (`sdk.build`) when the engine keeps
  it no more (a cancel's new process) or its input changed. `main()`
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
  leaves only a part file, a miss);
  `serve()` and `Spawned()` keep nothing past their process. In-process `app.serve()` (the tests') runs
  them on the request's thread (`engine.Here`), so a test's stand-in sdk
  call takes. A script that calls `app.main` guards it with `if __name__ ==
  "__main__"` (spawn imports the main script again). The page takes the image's path
  (remembered in platformdirs' config folder; the window adds file dialogs)
  and Save writes the build to a path, never over an existing file but one
  the save dialog chose. Closing the app (the window's close button, Cmd-Q,
  `serve`'s input ending) cancels a build or a save: it never waits on a
  build, and waits for a save to remove its part file `app.QUIT_WAIT`
  (1.5 s) at most, then removes it itself (AZ-823, D35). The window sets
  pywebview's `text_select`, or pywebview injects a `<style>` the CSP
  refuses. `scripts/freeze.py` builds
  the app (`AzurKit.app` on macOS, a windowed onedir; with the shipped
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
  `CLAUDE.md` and `.claude/`.
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
  welcome there), which a release joins; a change a player would notice
  also updates README's Features (above), in plain words.
- **The gate:** run `uv run --locked python scripts/fullsuite.py <worktree>
  --changed`. It runs the lint files in the foreground, then the changed area
  with the gate's USA and Europe test (or the whole suite) in the background
  under a lock, on 8 workers (pytest-xdist, `--dist loadgroup`), and prints a key and a receipt path. Its `plan()` picks the
  test files that import what changed; every change under `src/` adds the
  files that run the whole package (the wheel's, and those taking the
  `pyodide`, `browser` or `frozen_app` fixture), a change under `web/` the
  site's, the app's and the icon's, `LICENSE` and `NOTICE.md` the About
  tab's test and the wheel's, `README.md` the wheel's, a change in
  `tests/goldens/` the test files that read it (read by path: those
  reaching a module that names the folder, `record_goldens.GOLDENS`),
  other docs nothing more; the suite's configuration, what `tests/conftest.py` imports (it
  checks the app's no-window mode in a Python of its own) and a path no
  rule covers run the whole suite. A changed-area run drives the page in
  Chromium alone, the whole suite in every browser (D970), and the receipt
  says which (`browsers`). A run is killed past its
  cap, 1,800 s, scaled by the host's load per CPU up to twice that, and its log
  ends with the slowest tests. `--wait 540` waits for the result; exit 3 means
  it is still running, so issue the same command again.
- **The perf gate (D980-D985):** once pytest passes, the same locked run times
  the player-facing operations the changes reach (`scripts/perf.py`; the
  registry, its ids and drivers in `tests/_perf.py`): a change under `src/`
  or `web/` times its area's ops in the app's serve mode (the worktree's
  wheel in a scratch venv, so the app reads the database the wheel ships, as
  a player's install does) and on the site in WebKit, and main's own full
  run times every op in four profiles (the app; the site in WebKit and
  Chromium, and Firefox once its first record lands; the site with each File read 200 ms late,
  Safari's; capped, `AZURKIT_CORES=4` against 9 s with a 6 GiB memory peak: the
  app's process tree, and the WebKit processes launchd starts for the run's own
  browser (`launchctl print pid/N` holds the mark the run put in its PATH;
  another seat's isn't counted, one launchctl can't say about is);
  the 4-core / 8 GB computer AzurKit must run well on, D1017). The rule and its
  gate hold on this Mac alone; the other platforms are timed later (D1023).
  It starts once the normal-priority load is under 40, at nice 10. The
  clock is the click's (D1006): a Track or Build after a change the player
  makes (a typed seed, the Randomize tick, an image pick, a model's pick, a
  slider) is clicked 3 s after it (D1014's head start, `_perf.HEAD_START`), never
  after a Cancel, a launch, a reopen or a tab's open; work done ahead is
  free only while the page never freezes, so the page's freeze probe (a
  50 ms timer) fails a sample whose page froze over 250 ms in a gap between
  actions (a head start, a dialog's wait, the warm-up's), and logs the
  lateness inside an action's own wait. The site's samples each take a
  persistent browser context on a new folder, with the storage a player's
  browser has. An op
  runs three times (once past 30 s) and its median decides: over 3 s it
  fails, unless `tests/perf_ceilings.toml` lists it, when it fails over its
  ceiling; an image's first check and the site's first engine load may pass
  3 s only with a moving bar (D982); past 1 s an op shows progress unless the
  list names it a debt (D980). A download (the registry's `browser_bar`: the
  browser writes the file the page handed it, and its download indicator
  shows that) shows it when each sample's page part, the click to the
  download's start, is within 1 s or moves the page's own bar; the receipt's
  case keeps those seconds, and the whole still answers to 3 s. Each page's
  engine reports its compiled kernels (`sdk.catalog`'s `native`): a run
  whose engine answers without the library the worktree ships for its
  host (this machine's, the site's side module), loaded, with those bytes'
  sha256[:12], fails, its ops with it, so the Python twins' times never
  become a ceiling. A sample past 1 s whose wall passes 1.3x the CPU seconds
  its tree used (each process's highest figure, so a child gone mid-op
  keeps its own) waited for a core: it is taken once more and, starved again
  or past 30 s, stands with its tag (`starved`, `perf.judge` names it and no
  verdict reads it; `retook` keeps the first take's seconds); the lag run,
  whose reads wait by design, has no CPU figure. An op over
  runs three more times and fails only if the median of all six is still over. The list only shrinks: `perf.py
  --update-ceilings` lowers a ceiling you earned (in your own commit) and
  drops what is back under, and the gate and `land.py` fail an added op or
  debt or a raised ceiling against main's, but for a browser main's
  `perf.py` doesn't time yet (`perf.new_browsers`), whose first record
  (`--update-ceilings`, its ops as measured) may add its own ops and debts
  once: the landing queue lands with main's `land.py`, so Firefox joins
  `perf.py`'s `BROWSERS`, with its record, a stack after `new_browsers`.
- **Landing:** `uv run --locked python scripts/land.py <branch>` fast-forwards
  `main` once a passing receipt covers the branch's head with `vanilla: N run`
  and `europe: M run`, N and M at least 1 (D26), and, for a stack that
  changes `src/` or `web/`, a passing perf block; it refuses any stack whose
  perf list grows main's (one that changes only the list too); `--release`
  refuses while the list holds anything (it is empty for 4.4).
- **CI (Step 4.4ci; D1022-D1024):** AzurKit is public in Azurik-Modding-Hub
  before its release so GitHub Actions tests it, and publishing isn't a
  release: no workflow deploys the site (Pages stays off, D1026), uploads
  to PyPI, tags or makes a release. `.github/workflows/tests.yml` runs the
  pure tier on every push to `main` and every pull request on the four
  platforms the apps ship for (macOS on Apple Silicon and on Intel,
  Windows x64, Linux x64; the web tier with Node 24 and
  `scripts/web_tools.py`'s Pyodide and browsers), and on a push to `main`
  in this repository alone the vanilla and europe tiers on the same four:
  each image rebuilt in the tier's folder, on the runner's largest disk, from
  the game-data repo's parts with `GAMEDATA_DEPLOY_KEY` (the only secret a
  workflow reads), never cached, uploaded or printed, and deleted after, with
  the free disk and memory each minute and their lowest printed
  (`scripts/ci_resources.py`); on every OS the job runs
  behind harden-runner's egress block, which starts with the job (its
  pre-step), so its installs' hosts are named too, and on Linux its tests
  run with no network as well (Modkit's §12.4 hygiene), and only the
  pytest log's tail and summary are printed. `checks.yml` runs the leak
  guard over the checkout and every commit, and `python -m nativekit
  --check` on macOS, Windows and Linux (D1019). `apps.yml` freezes the four
  apps (`scripts/freeze.py --check`, which refuses one whose compiled library
  doesn't load) on a push to `main`, each a 14-day workflow
  artifact with its sha256. Workflows hold `permissions: contents: read`,
  no `pull_request_target`, and actions
  pinned by commit sha with their release beside it; `actionlint` passes
  on each. A stack still lands on the local gate (`land.py`); the other
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
- **The xemu core (Step 4.14a1, devkit):** `devkit/xemu/queue.py` (the
  sittings' first-come tickets and the batch token that gives way to them),
  `devkit/xemu/warm.py` (a sitting's warm build states) and
  `devkit/sim/{snapshot,obs,inputs}.py` (the guest RAM snapshot's file and
  its private store, `l3-snapshots/` in the user data folder; the player's
  observation; the pad) need no Unicorn. They keep Modkit's folders
  (`/tmp/azx-xemu-slots`, the owner-demo lease, the store), so both
  harnesses share one D108 budget until Step 4.14a2 ports the harness. No
  test launches xemu (D108): `tests/test_xemu_harness.py` reads synthetic
  memory alone.
- **Ask nothing (D115):** where a decision is missing, take the recorded default
  or your recommendation, and say so in your report.
