# AGENTS.md: rules for agents and contributors

AzurKit is the lean, public rewrite of Azurik_Modkit. Modkit is its reference
and, for the randomizer until Step 4.12b, its test oracle: a port is done
when its output matches Modkit's byte for byte, file by file. Every other
family's truth is AzurKit's own (The goldens, below): the core's and the
packs' since Step 4.12a, the characters' since Step 4.12c.
[`README.md`](README.md) says what AzurKit is. These rules bind.

**README's features:** a change a player would notice adds or updates its
line in README.md's Features (and Highlights if it earns one), in the same
commit. Each line is plain and short, with no step, D or AZ ids, and true on
`main`.

## Setup and tests

```bash
uv run bootstrap.py                         # once, in the main checkout: uv sync --locked, the pre-push hook, Pyodide
uv run --locked pytest -q <files>           # targeted tests while you work
uv run --locked pytest                      # the whole suite
uv run --locked pytest -m "not vanilla"     # the pure tier: no game data
uv run --locked python scripts/freeze.py --dist DIR   # the app (D732): DIR/AzurKit.app on macOS (a PyInstaller onedir)
uv run --locked python -m shimkit [--check]           # the prebuilt shim objects, from their sources (zig, dev only)
uv run --locked python scripts/record_goldens.py [--check] [GOLDEN ...]   # tests/goldens/ from the player's images
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
  it in Playwright's headless Chromium and again in its WebKit, Safari's
  engine (Step 4.1d3: Safari failed where Chromium passed), or only in those
  `--browsers` names (`--browsers=chromium`); either becomes `web`. A run that selects one needs Pyodide's pinned core, Node on PATH
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
- Never print game bytes in logs, commits or chat: print lengths and
  `sha256[:12]`. Failure output is redacted (`tests/_byte_safe.py`).
- Recorded results are hashes and names, a convention and not a leak rule:
  the goldens, the oracle's bundle and the facts hold sha256 and length, not
  raw vanilla spans.
- The images are read-only. A build writes to an explicit output that isn't
  its input.

## The goldens

- `tests/goldens/` is AzurKit's own truth for every family but the
  randomizer's: the packs and the core (Step 4.12a) and the characters
  (Step 4.12c). It is what each case of `tests/goldens/cases.json` (its
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
  the air elemental's own bodies, on both releases) and the Characters
  tab's match-Garret values (`matches.json`).
  - Only `scripts/record_goldens.py` writes them, from AzurKit's own builds
    on the player's images (`--check` writes nothing); never edit them by
    hand. A commit that changes one names each golden it changed and why,
    and a gameplay byte change to a default build is seen once in xemu.
  - The first recording is Modkit's last cut (the packs and the core:
    oracle-packs-4, Modkit 28d0b4110; the characters: oracle-models-3,
    Modkit 1648692), which the recorder's first run wrote back unchanged
    but the files AzurKit can't build (AZ-009: G3's `seed=0,all` leaves out
    `training_room.xbr`, `filelist.txt` and `ISO`, as the packs' three
    level-patched cases do).
  - The cases that wear booblord read her files in the content folder
    (`AZURKIT_CONTENT`, `azurkit content install booblord`); the builds
    that dress the player run in `--workers` processes.
  - A new pack adds its cases to `cases.json` (its defaults in `packs.json`,
    `sites.json` and, for an XBE pack, Europe's), then records them.

## The oracle

- `tests/oracle/<family>/` is Modkit's bundle for a family (`rando`, the
  one left until Step 4.12b), cut at a Modkit tag. `tests/oracle/ORACLE.toml` records
  each family's tag, its commit and every file's sha256, and
  `tests/test_oracle.py` holds them to it.
  - Only `scripts/oracle_sync.py` changes these files; never edit them by hand.
  - A tag bump prints Modkit's commits since the last sync. That list is the
    port's to-do.
  - **Modkit's source a sync installs** (`oracle_sync.SOURCES`): the rando
    family's sync also installs the randomizer's database
    (`src/azurkit/tools/randomizer/data/`, our own logic data, copied
    verbatim, and `draft/tiers.toml`, the movement tiers' margins), its
    planner (`.../randomizer/planner/`) and its `writer.py`, `physics.py`,
    `movement.py` and `layer.py`, each module through `port()`: `REWRITES`'
    imports (what they import of Modkit's engine points at ours:
    `core/xbr/nodes.py`, `tools/randomizer/ports.py`), and the top-level
    statements `DROPS` names taken out, such as the seed roll's process pool
    and Modkit's build objects (a script's `if __name__ == "__main__":`
    block is dropped as `"__main__"`). It installs the maps' and icons'
    drawing too (Step 4.2c3): Modkit's `scripts/render_level_maps.py` and
    `render_model_icons.py` as `tools/randomizer/art/maps.py` and
    `icons.py`, its XBR readers they draw from (`xbr/nodes.py` with the
    node-type names table `node_types.json`, P3: no capstone; `tern.py`,
    `collision.py`, `render.py`, `draw.py`) in `art/`, and the reach
    model's geometry, floors, wiring and envelope in `draft/` and the level
    semantics they read (`levels.py`, its extractor dropped). ORACLE.toml's
    `source` table holds each installed file's sha256 and `tests/test_oracle.py`
    refuses a hand edit: a Modkit fix arrives by the next sync. Its `art`
    table holds the pixel digest of each picture Modkit commits of what it
    draws from the image (`gui/assets/maps/*.png`, `icons/*.png`;
    `maps.json`'s sha256), never a picture. A module
    that still imports Modkit after the rewrites, or a statement `DROPS`
    names that is gone, stops the sync by name before anything is written:
    port what it imports into an AzurKit module, then add a rewrite.
    `tests/test_oracle.py` ports the sources again at the recorded commit
    and holds them to import-linter's contracts, so the suite reads Modkit's
    history (`$AZURKIT_MODKIT`, else `Azurik_Modkit` beside the main
    checkout).
  - The models family's sync (until Step 4.12c, oracle-models-3, Modkit
    1648692) installed the swap and the archive writers it builds on (see
    Characters below); they are AzurKit's own source since, and its truth
    AzurKit's goldens.
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
    and `recipes.py` are Modkit's, installed by the sync (above): never edit
    them by hand. `generator.py`, `tracking.py`, `ports.py`, `dbcache.py`
    (no cache on disk: a pickle read back from a writable folder runs its
    code) and `live/`'s `errors.py` and `regions.py` are ours.
  - The fill runs in the caller's thread: Modkit's seed roll in a process
    pool (`roll_seed`) isn't ported.
- **The generator layer** (Step 4.2b; `generator.py`): a build recipe's
  `randomizer` (the planner's recipe and an `obsidian_cost`; `azurkit build
  --seed`) is planned on the logic re-checked under the build's movement
  sliders (Modkit's `layer.plan_for`: a run under garret4's falls back to
  his, AZ-606) and written as the build's first layer, before the packs
  (Modkit's `mod_apply` order): one group a node graph (its new strings,
  TOC size and repointed name fields land whole) and one for the obsidian
  locks. `edits.manifest.image`'s `judge` reads the image back against the
  plan before anything is written: a difference a later layer explains (it
  wrote the location's fields or string, or dropped its graph) is a
  conflict and `logic_verified` false (D28), any other fails the build by
  location (D35). The movement check reads the packs' catalog (each
  slider's `logic_floor`, D83(c)); the tools never import each other. The
  report's `randomizer` and the manifest's `verdicts` carry the verdict, and
  a randomized build's mods file replays its seed and share string.
  - Not ported: Modkit's `db-extract` (`levels.py`, the generated data's
    extractor: the data comes by the sync), the player-model swap's
    movement reasons (with the models, Step 4.3) and the slider tracks'
    safe ranges.
  - `tests/test_randomizer.py` holds it to the oracle: `rando_plans.json`
    (seed 2's attempt and plan sha256 under the strict, default and max
    settings, and the default plan file byte for byte, on CPython and under
    Pyodide), G3's seed cases file by file and whole image on both releases
    and `rando_iso.json`.
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
  Modkit's on seed 2's default and max plans at five states (none marked,
  three rounds of marking what is reachable, every power, Live's kit at 3,
  and Gems on with gem takes), each digest from Modkit's own `Tracker`.
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
    maps metres to them) and its world-map thumbnail; `sdk.art_world`
    makes the world map and the index from the levels' parts. Modkit's
    scripts draw them (installed by the sync), on the reach model's first
    stage (`art/reach.py`, ours: Modkit's `Reach(level, flights=False)` up
    to the logic floors). `tests/test_art.py` holds every picture and the
    index to Modkit's committed pictures' digests, drawn from the USA image,
    and the icons and a level from Europe's (its level, character and
    effect files are USA's); it holds `ART_VERSION` to the digest of the
    drawing's sources, so a sync that changes them changes the key.
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
    a host gives it a map (`pool.MAP`).
  - A recipe's `character` (`tools.characters.normalize`): `species` and
    Modkit's `randomize-full` options (`mode`, `size`, `scale`, the attack
    sliders, `anims`, `sounds`, `weapon`, `ram`, the jiggle's): the sdk
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
    winning): every file checked first, nothing written on a mismatch,
    `installed.json` last. An installed copy stays at its version until its
    Update. The engine opens no connection: the sdk's CPython calls fetch,
    and the site's page fetches and its worker checks
    (`sdk.content_check`).
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

- **Layers:** `core <- edits <- tools <- sdk <- {cli, app}`. The three tools
  (`mods`, `randomizer`, `characters`) never import each other. import-linter
  holds this (see `pyproject.toml`).
- **AST rules:** `core`, `edits` and `tools` hold no threads, processes,
  subprocesses, prints or exits, so the web page's worker runs them as they
  are. The worker loads the wheel without its dependencies, so the engine
  imports platformdirs only where it needs the user data folder. Only `tools/characters` and the randomizer's drawing
  (`tools/randomizer/art/`, `draft/`) import numpy, and nothing imports capstone,
  unicorn, zig or Tk. `tests/test_contracts.py` checks these, along with
  import-linter's contracts.
- **The same bits on every platform (AZ-830):** each platform's libm rounds
  some sines, cosines and powers otherwise (macOS's for CPython, musl's
  under Pyodide), so the swap's (`tools/characters/`) and the XBR graphs'
  (`core/xbr/`) transcendental math is `core/fdlibm.py`'s: fdlibm's
  algorithms in pure Python, built from correctly rounded operations alone
  (musl's bits where musl's is fdlibm's), and a power is `fdlibm.sq`, `cube`
  or `pow` (CPython's `float ** 2` calls the platform's `pow`; numpy's
  arrays take them as they are). No `math` or numpy libm call and no `**`
  but an integer's there; the previews' drawer (`draw.py`) writes no built
  byte and keeps numpy's. `tests/test_contracts.py` holds this.

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
    movement sliders, the skips, and a ⚠ line for the preflight's refusal
    and what a build would leave unverified (a loaded share string's note
    of other sliders stays until the tab is edited or the Patches tab's
    sliders give that share string). With Randomize ticked, Build
    sends the build's `randomizer` (seed, settings, a cost other than
    vanilla's), planned and written first; its report carries the verdict
    and the spoiler (Modkit's `--spoiler` file), which the tab shows and
    saves (the site's download, the app's `api/spoiler`). The tab's setup
    is remembered too (`randomizer`: on, seed, settings, cost) and Reset
    unticks it.
  - **The Tracker view** (Step 4.2c2, `web/tracker.mjs`): the Randomizer
    tab's second view (Settings · Tracker). It opens on a randomized
    build's plan (the report's `plan`), Track this seed (the Settings
    view's seed and share string, planned by the engine: `sdk.plan`, the
    site's worker, the app's `api/plan`) or a plan file, and asks the
    engine (`sdk.tracker`: the worker's `tracker` call, the app's
    `api/tracker`) what it shows, one ask at a time, each click one: the
    head line, the counter row, the world map (`tracking.GRID`, each level
    with its spots reachable now, amber when only a skip reaches them), a
    level's spots as chips (a click marks one; a spot not shown is told by
    the item vanilla puts there), and the Table. The page keeps the plan
    last tracked and the marks of the last 20 plans (the site's storage
    `azurkit.tracker`, the app's `api/tracked`, `host.json`'s `tracker`):
    names and numbers, never the image. **Live** is the app's alone (D882):
    `api/live` starts `azurkit.app.live`'s feed (a thread) for the plan,
    and each `api/tracker` ask merges its events and the element levels the
    game holds and returns `live` (the status, where it saw the player),
    which the page asks for every 0.7 s; Follow shows the player's level,
    Find me (key F) shows it once. As Modkit's: the marks keep the saved
    slot the game last showed, each session Live opens (the link back, Live
    off and on) checks the game against their journal (that slot, the
    newest live mark's day clock), Reset with Live on reads the game again,
    and an error that ends the feed turns Live off.
  - **The maps** (Step 4.2c3, R1.41, R1.43; `web/art.mjs`,
    `web/mapview.mjs`): the first time the Tracker view shows with an image,
    its pictures are drawn from it (`sdk.art`, one part at a time) and kept
    under `ART_VERSION`: the site draws them in a worker of their own (the
    engine with numpy, Pyodide's pinned wheel from the site) into this
    browser's storage (IndexedDB `azurkit-art`, PNG bytes: WebKit's private
    storage keeps no Blob), the app on a thread into platformdirs' cache
    folder (`api/art`, `art/<version>/<name>`; `azurkit.app.art`). A level
    drawn shows as Modkit's map view on a canvas in place of its chips (the
    world map once every level is): its picture by floor (the floor
    buttons), its features, barriers, tracked spots and exits at their
    vanilla places (each spot's ring, icon and check as Modkit's track(), an
    exit's ring by what using it needs, `tracking.world()`'s `maps`), a
    click marking a spot or opening an exit's level, the wheel zooming about
    the pointer, a drag panning, a double click or Fit showing it whole, the
    map filling the window as it resizes, and, with Live, the player's dot
    (Follow keeps a zoomed map on them; Find me centres it). The world map:
    each level's main floor, its badge of spots reachable now (amber: only
    a skip), the exits' lines. **Gems** (off by default, remembered: the
    tracked plan's `gems`): each gem spot not all taken a tiny dot in its
    gem's colour, under every other overlay, the gems taken and left under
    the title, on the floor buttons and on the world map, and the colour
    key; Live (the app's) reads the gem spots while Gems is on (`api/live`'s
    `gems`) and takes a dot once the game shows its gem taken.
    `web/mapview.mjs`'s `marks` and `badges` are the map's verdicts:
    `tests/test_site.py` holds them to Modkit's (`TRACKER_MAP`, its map
    view's rules on its own Tracker) at TRACKER's states; the site's drawing
    in both browsers to Modkit's pictures (the icons and e6); and
    `tests/test_hosts.py` the app's map, a click, zoom, resize and Live
    taking a gem's dot. A known flaw (D835): under Pyodide (wasm32, its
    numpy 2.4.6) 16 of the 162 pictures differ from Modkit's in at most 135
    pixels each (airship, a3, a5, town and e2: a pixel taking another
    face's colour), while every `maps.json` entry is the same; the app's
    (CPython) are Modkit's pixel for pixel.
  - **The Characters tab** (Step 4.3d, `web/characters.mjs`; Modkit's
    Player page): the models' list, the community group first (D913:
    Azurik-Custom-Content's variant entries beside the species, each marked
    community, its state Install, installed vN or Update to vM, its
    variants once installed), then every species the player can wear in its
    grade's colour, the 73 untested greyed and marked (D877); the chosen
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
    Content from (the source; default `sdk.SOURCE`, the hub's raw URL, live
    at 4.4) is remembered (the site's storage, the app's `content_source`).
    The site reads a source on its own address only (its CSP's
    `connect-src 'self'`; `scripts/web_tools.py --site DIR --content
    CLONE` serves a clone as `./content-source/`), checks an Install in
    its worker (`sdk.content_check`), keeps the files in IndexedDB and
    writes them into its worker's `content/` once a worker; the app's
    engine installs into its content folder. A known flaw (D835): on the
    site a detailed variant's dress (booblord's) may run out of wasm
    memory; the page then says to use the app.
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
  tracker's maps load: `web_tools.PACKAGES`), the wheel and its
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
- **Never:** attribution trailers, force-pushes, `--no-verify`, `git stash` or
  git config changes.
- **The gate:** run `uv run --locked python scripts/fullsuite.py <worktree>
  --changed`. It runs the lint files in the foreground, then the changed area
  with the gate's USA and Europe test (or the whole suite) in the background
  under a lock, and prints a key and a receipt path. Its `plan()` picks the
  test files that import what changed; every change under `src/` adds the
  files that run the whole package (the wheel's, and those taking the
  `pyodide`, `browser` or `frozen_app` fixture), a change under `web/` the
  site's, the app's and the icon's, `LICENSE` and `NOTICE.md` the About
  tab's test and the wheel's, `README.md` the wheel's, a change in
  `tests/oracle/` or `tests/goldens/` the test files that read it (read by
  path: those reaching a module that names the folder, such as
  `oracle_sync.ORACLE`), other docs nothing more; the suite's configuration, what `tests/conftest.py` imports (it
  checks the app's no-window mode in a Python of its own) and a path no
  rule covers run the whole suite. A changed-area run drives the page in
  Chromium alone, the whole suite in both browsers (D970), and the receipt
  says which (`browsers`). A run is killed past its
  cap, 4,500 s, scaled by the host's load per CPU up to twice that, and its log
  ends with the slowest tests. `--wait 540` waits for the result; exit 3 means
  it is still running, so issue the same command again.
- **The perf gate (D980-D985):** once pytest passes, the same locked run times
  the player-facing operations the changes reach (`scripts/perf.py`; the
  registry, its ids and drivers in `tests/_perf.py`): a change under `src/`
  or `web/` times its area's ops in the app's serve mode and on the site in
  WebKit, and main's own full run times every op in four profiles (the app;
  the site in WebKit and Chromium; the site with each File read 200 ms late,
  Safari's; capped, `AZURKIT_CORES=4` against 9 s with a 6 GiB memory peak: the
  app's process tree, and the site's WebKit processes that start during the run).
  It starts once the normal-priority load is under 40, at nice 10. An op
  runs three times (once past 30 s) and its median decides: over 3 s it
  fails, unless `tests/perf_ceilings.toml` lists it, when it fails over its
  ceiling; an image's first check and the site's first engine load may pass
  3 s only with a moving bar (D982); past 1 s an op shows progress unless the
  list names it a debt (D980). An op over runs three more times and fails
  only if the median of all six is still over. The list only shrinks: `perf.py
  --update-ceilings` lowers a ceiling you earned (in your own commit) and
  drops what is back under, and the gate and `land.py` fail an added op or
  debt or a raised ceiling against main's.
- **Landing:** `uv run --locked python scripts/land.py <branch>` fast-forwards
  `main` once a passing receipt covers the branch's head with `vanilla: N run`
  and `europe: M run`, N and M at least 1 (D26), and, for a stack that
  changes `src/` or `web/`, a passing perf block; it refuses any stack whose
  perf list grows main's (one that changes only the list too); `--release`
  refuses while the list holds anything (it is empty for 4.4). There is no remote
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
