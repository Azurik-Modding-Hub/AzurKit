# The `azurik` MCP server

A [Model Context Protocol](https://modelcontextprotocol.io) server over stdio
that gives an agent (Claude Code, say) Azurik's game data offline: 8 tools on
AzurKit's own engine and sdk. It is developer-only (`devkit/mcp`), never in the
wheel, the site or the app (`devkit/README.md`), and needs no Ghidra.

## Setup

`uv sync --locked` installs it: mcp 2.3.0 is in the `devkit` dependency group,
installed by default. The checkout's `.mcp.json` declares the server:

```json
{"mcpServers": {"azurik": {"command": "uv", "args": ["run", "--locked", "python", "-m", "devkit.mcp"]}}}
```

Open Claude Code in the checkout's root and approve `azurik` once; `/mcp`
lists it with 8 tools. `uv` must be on the `PATH` Claude Code started with.
Run it by hand with `uv run --locked python -m devkit.mcp` (or `python -m
devkit mcp serve`). Its stdout carries only JSON-RPC: the server keeps a copy
of fd 1 for its replies and points fd 1 at stderr, so whatever a tool, the
engine or a child process prints goes to stderr (mcp 2's own claim of fd 1 let
a tool's print reach the wire).

A tool takes its image's path. The images are the player's own, found as the
`azurkit` command finds them: `AZURKIT_ISO` and `AZURKIT_ISO_EUROPE`, else
`usa.iso` and `europe.iso` in the user data folder.

## What every tool keeps

- **The envelope:** each answers `{"success": true, "result": ...}` or
  `{"success": false, "error": "..."}`, never a raised error. An optional
  parameter left out or sent as `null` is unset.
- **No clamp (D23):** a slider's `min` and `max` are display hints and a
  cell has no range; a value is refused only where its encoding can't hold it
  (NaN, infinity; what an int32 cell can't hold, D45).
- **Whole or nothing (D35):** a tool that fails writes nothing, and its error
  names the pack, slider, operation or file, never game bytes.
- **Never over its input (D36):** no tool writes over its input or a vanilla
  image, and a build reads only a release's vanilla image (D27): there is no
  `allow_modded_input`.

## The tools

| Tool | What it does |
|---|---|
| `entity_list(config_xbr, section=None)` | config.xbr's tables, each with its entity count; with `section`, that table's entity (column) names in file order. `config_xbr` is a config.xbr file or an image (its `gamedata/config.xbr`) |
| `entity_get(config_xbr, entity, section=None)` | An entity's values (each cell of its column that isn't empty) in one table, `{section, entity, properties}`, or in every table that has it, `{entity, sections}`. The name may be spelled as a mods file spells it (D51: case-blind, `_` for a space; a name several columns share reads its last); a table where the spelling names several columns is listed under `ambiguous` |
| `xbr_edit(inp, out, ops)` | **Writes** a modded `.xbr`: the mods file's `xbr` operations without their `file` (the file is `inp`): `{"op": "set", "table", "entity", "prop", "value"}` (optional `col`, `fill`) and `{"op": "replace_bytes", "offset", "expected", "value"}` (`edits/xbr.py`). An op a later one overwrites is dropped whole and listed in `conflicts` (D28). Returns `{output_path, ops_applied, conflicts}` |
| `pack_list(category=None, pack=None)` | Every pack (`sdk.catalog`'s: name, description, category, `default_on`, releases, requires, sliders), in their canonical order; a config.xbr slider also names the cell it writes (`xbr`: `{file, table, entity, prop}`, or `{file, table}` for a multiplier of several cells). No image needed |
| `pack_build_iso(iso, out, enable=None, params=None, config_mod=None, disable=None)` | **Writes** a build (`sdk.build`): the packs on by default and `enable`'s (with each pack they require, said in `summary.settled`), less `disable`'s, each slider `params` gives (`{pack: {slider: value}}`, for packs the build applies), then `config_mod`'s edits (a mods file: its path, JSON text or object, or a share link; its packs replace those on by default, and its seed and character come with it; one with a files layer, Replace files, is refused: the server picks no files), as `azurkit build` makes its recipe. Returns `{output_path, region, sha256, summary: {packs_applied, layers, files_changed, output_size_bytes, conflicts, notes, settled}}`, and `randomizer` when the mods file holds a seed |
| `rando_build_iso(iso, out, seed=None, options=None)` | **Writes** a randomized build: the seed's plan (any text or whole number, `"42"` by default) as its first layer, then the packs and the rest, read back against the plan before anything is written. `options`: the randomizer's `settings` (a settings file's table) or `share` (`AZR-...`) and `obsidian_cost`, `pack_build_iso`'s `enable`, `disable`, `params` and `config_mod`, the `character` the player wears (a recipe's: `{"species", "mode", ...}`) and `spoiler` (a file to write the spoiler to: not `iso`, `out` or a vanilla image); any other is refused by name. Returns `pack_build_iso`'s reply with `randomizer`, the verdict: seed, share, settings, plan (its sha256), attempt, sliders, `logic_verified`, `why_not` and `conflicts` (a placement a later layer changed, or any moved slider, leaves the logic unverified: D28, D1064) |
| `iso_extract(iso, dest, only=None)` | **Writes** an image's files (every one, or those `only` names, files or folders in any letter case) into `dest`, a missing or empty folder, whole or not at all, in the image's own spelling. A path the image hasn't, or a name no host writes as a file of its own (AZ-216), fails by name |
| `iso_repack(src, out, region=None)` | **Writes** the vanilla image of `region` (`usa` or `europe`; USA's when it is found, else Europe's), its build files checked, with each file of `src` (a tree as `iso_extract` writes it) whose bytes differ from vanilla's in its place. `filelist.txt` is derived (src's own is ignored); dotfiles are skipped; any other file the image hasn't fails by name; `out` is never inside `src`. Returns `{src, out, region, sha256, files_changed}` |

Everything else is the `azurkit` command (`docs/DEVELOPMENT.md`) and
devkit's verbs (`devkit/README.md`).

### From Modkit's server

The names are Modkit's (D64); the inputs are AzurKit's own. `xbr_edit`
takes the mods file's `set` and `replace_bytes` (Modkit's
`set_keyed_double`, `set_keyed_string`, `point_keyed_string` and
`replace_string_at` have no AzurKit operation). `rando_build_iso`'s `options`
are the build recipe's parts, not `randomize-full`'s flags: its settings are
`settings` or `share`, a pack's slider is in `params`, the body is
`character`, and a build with no seed is `pack_build_iso`'s (Modkit's
`no_randomize`); a plan file as input and `save_settings` have no option (the
verdict holds the settings). `pack_list` gives AzurKit's catalog: `releases`
for Modkit's `regions`, the track's `min`, `max` and `step`.

## The `ghidra` server

The second server, the stock GhydraMCP bridge over a live Ghidra session,
comes with devkit's Ghidra side. Its client setup: the bridge starts on port
8192 (Ghidra's front-end tool), and the CodeBrowser holding `default.xbe`
usually serves 8193, so call `instances_use(8193)` once a session, or pass
`port=8193`.

## Tests

`uv run --locked pytest -q tests/test_mcp.py`: `.mcp.json`'s command lists
the 8 tools over stdio and a tool's print never reaches the wire (pure); each
tool answers in its envelope on the USA image, `xbr_edit` writes an
out-of-range value as given and the file's one build is a seed (vanilla); a
refusal names what it refuses and writes nothing (pure).
