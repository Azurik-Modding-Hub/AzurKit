# devkit: AzurKit's developer side (dev only)

`devkit/` holds what AzurKit's developers use and players never get (D950,
D990): Modkit's developer side, ported area by area. Run it from the
checkout's root:

```bash
uv run --locked python -m devkit                        # the areas
uv run --locked python -m devkit AREA                   # an area's verbs
uv run --locked python -m devkit AREA VERB [ARGS ...]   # run one
```

## The areas

Each area is a subpackage, `devkit/<area>/`, with its verb reference in its
own `README.md`. Its `__init__.py` imports only the standard library
(`reach`'s also the randomizer's art, which its import order needs) and
names its verbs in `VERBS` (`{verb: its line}`); the verb `v` is the module
`devkit.<area>.v` (a hyphen in `v` is an underscore there), whose
`main(argv) -> int` runs it. An unknown area or verb exits 2.

Each arrives with its own step (`re`'s XBE verbs, data and shim authoring,
`xemu`'s harness, sitting kit, demos and chain driver, `sim`'s levels,
`mcp`, `rando`'s database tools, derive and authoring, `reach`'s engine
and certification and `models`' first model verbs are here; the rest come after the first release,
4.4); this is what each will hold:

| Area | What it holds |
|---|---|
| `xemu` | the in-game oracle: the harness, its slots and queue, the sittings and demos, the chain driver, the route pilot and the minigame solvers |
| `sim` | the simulator: the snapshot, observations and inputs, its levels on Unicorn, L3's search and trick explorer |
| `re` | the XBE verbs, the Ghidra side and its data, shim authoring |
| `mcp` | the `azurik` MCP server (`.mcp.json` launches it; `docs/MCP.md`) |
| `rando` | the randomizer database's tools and benches, the reach model's derive and the realm authoring |
| `reach` | the reach engine, its native kernel and the patched Unicorn; the L3 certification of the randomizer's spots, edges, skips and contact flights |
| `models` | the model and effect verbs ModelKit's adapter calls |
| `xbr` | the XBR file tools: inspect, diff, edit, xref and verify (here) |
| `movies` | a Bink movie's header and frame table, its frames by ffmpeg (here) |
| `audio` | an XBR's waves written out with their WAVs and a manifest (here) |
| `doctor` | is this machine ready: one line a check of AzurKit's tools, the images and the RE install (a command of its own, here) |
| `builds` | any build's pack sites and physics sliders read back: verify-patches, inspect-physics; the release manifests written from the vanilla images: write-manifest (here) |

## Its dependencies

The `devkit` group in `pyproject.toml`, installed by default so that a broken
install fails devkit's tests rather than skipping them:

- capstone 5.0.9 (BSD): the disassembler;
- Unicorn 2.1.4 (GPL-2): the simulator's CPU;
- mcp 2.3.0 (MIT): the MCP server. It brings cryptography, which pywebview
  imports when it is installed, so `scripts/freeze.py` leaves cryptography
  out of the app by name.

zig, which builds the native code, is the `dev` group's.

## Why none of it ships

- **The wheel:** `uv_build` packs only `src/azurkit`, and `tests/test_wheel.py`
  holds the wheel to exactly that folder's files. Dependency groups never
  reach the wheel's metadata, so installing AzurKit never installs this
  group.
- **The site** runs that wheel.
- **The app:** `scripts/freeze.py` gives PyInstaller `--paths src` and
  `src/azurkit/__main__.py`, so it collects only what `azurkit` imports, and it
  leaves Unicorn, capstone, zig and cryptography out by name.
- **The contract:** nothing under `src/azurkit` imports `devkit`, capstone,
  Unicorn, zig, mcp or Tk (`tests/test_contracts.py`).

## What stays out of the repository, and where it lives

AzurKit's repository is public, though not released yet. These never enter
the repository; devkit reaches each where it lives.

| What | Where it lives | Why |
|---|---|---|
| The game images, whole or in parts | the developer's own: `AZURKIT_ISO` and `AZURKIT_ISO_EUROPE`, else `usa.iso` and `europe.iso` in the user data folder; CI's parts only in the private `Azurik-Modding-Hub/AzurKit-gamedata` repository, never made public, forked or mirrored | D153, D953, D961 |
| The xemu oracle's fixtures: its drive (`xbox_hdd.qcow2`, with the oracle's save states), `eeprom.bin`, the BIOS and the boot ROM | outside the checkout, reached through `AZURIK_XEMU_FIXTURES`, else the user data folder's `xemu-fixtures` link; their README, SHA256SUMS and checklist stay with them | D98; they hold console keys |
| Guest RAM snapshots (`AZL3SNAP`) and the warm drives | `l3-snapshots/` in the user data folder | D961 |
| The reach engine's frozen truth set | `reach-truth/` in the user data folder, not the cache, which can be purged | |
| The Ghidra project and its backups | outside the checkout: the owner's | |
| The ghidra-xbe loader, which has no licence, and GPL headers | fetched into `.tools/`, never vendored | |
| The process records: decisions, plans, the issue ledger, the agents' memory and handoffs | private, outside the repository | D952, D958 |
| Caches | the user cache folder; rebuilt on demand | |

The leak guard (`tests/_leak_guard.py`) refuses an image or a part of one, an
xemu disk, an EEPROM dump, a guest RAM snapshot and a private key in the suite
and on every push (the pre-push hook `uv run bootstrap.py` installs).
