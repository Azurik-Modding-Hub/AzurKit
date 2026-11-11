# Developing AzurKit

How to build and test AzurKit from a checkout. The rules contributors and agents follow are in
[`AGENTS.md`](../AGENTS.md), and the design they stand on in [`INTERNALS.md`](INTERNALS.md); the player's side is in
[README](../README.md) and the [guide](GUIDE.md).

## How it fits together

AzurKit is the lean rewrite of Azurik_Modkit, the proof of concept it replaces.
The truth of the packs, the characters and the randomizer is AzurKit's own:
[`tests/goldens/`](../tests/goldens/), per-file sha256s it records from its own
builds and plans, first recorded from Modkit's.
AzurKit never imports Modkit's code. A build's recipe is the two files at its
image's root, `/azurkit.json` and `/azurkit.bin`.

## Setup and commands

You need [uv](https://docs.astral.sh/uv/) 0.13 or newer, which provides Python
3.14.

```bash
uv run bootstrap.py                  # uv sync --locked, the leak guard's pre-push hook, Pyodide and the browsers
uv run --locked python -m devkit doctor   # is this machine ready? one line a check
uv run --locked pytest               # the suite
uv run --locked pytest -m "not vanilla"   # only the tests that need no game data
uv run --locked azurkit verify [--iso PATH]              # is it vanilla USA or Europe, every file of it?
uv run --locked azurkit packs                            # the packs, and which a build applies by default
uv run --locked azurkit build --iso PATH --out PATH [--mods FILE ...] [--pack NAME ...] [--no-pack NAME ...] \
    [--no-defaults] [--pack-param PACK.SLIDER=VALUE ...] \
    [--seed SEED [--settings FILE | --share STRING] | --plan FILE] [--obsidian-cost N] [--character JSON] \
    [--spoiler FILE] [--save-settings FILE]
uv run --locked azurkit open BUILD                       # a build's recipe, as a mods file for build --mods
uv run --locked azurkit plan --seed SEED [--settings FILE | --share STRING] [--out FILE]   # a plan; needs no game
uv run --locked azurkit spoiler PLAN                     # that plan's spoiler
uv run --locked azurkit content [install ID | update ID] [--source URL|DIR]   # Azurik-Custom-Content's entries
uv run --locked python scripts/web_tools.py --site DIR [--content CLONE]   # the site: the page, Pyodide, the wheel
uv run --locked python -m azurkit [serve]                # the app: the page in a window (serve: only its address)
uv run --locked python scripts/freeze.py --dist DIR      # the app frozen: DIR/AzurKit.app on macOS, else DIR/AzurKit
uv run --locked python -m shimkit [--check]              # rebuild the prebuilt shim objects (zig, dev only)
uv run --locked python -m nativekit [--check]            # rebuild the compiled kernels' libraries (zig, dev only)
uv run --locked --group icon python assets/icon/render.py # rebuild the icon from its sources (macOS)
```

## Tests

The vanilla tests read the two images, found by `AZURKIT_ISO` (USA) and
`AZURKIT_ISO_EUROPE`, or as `usa.iso` and `europe.iso` in the user data folder
(on macOS, `~/Library/Application Support/AzurKit/`). A run that selects one
of these tests without its image stops with one message: no test is quietly
skipped. The `web` tests run AzurKit under Pyodide on Node, and the page in
headless Chromium, in WebKit (Safari's engine) and in Firefox; they need Node,
and the Pyodide, Chromium, WebKit and Firefox that `uv run bootstrap.py` fetches into `.tools/`
(`-m "not web"` leaves them out). A test that fails runs once more at once: if it
passes then, the summary lists it as flaky and the run passes; if it fails
again, the run fails.

## Game data in the repository

- No ISO image, whole or in parts, is ever in this repository.
- Game files and bytes (an XBE or XBR file, a clip, a texture, a save, a
  snippet) may be committed here. They belong to the game's rights holders,
  not to this project's licence ([`NOTICE.md`](../NOTICE.md)).
- Recorded results are hashes (sha256) and lengths, by convention.
- [`tests/_leak_guard.py`](../tests/_leak_guard.py)
  refuses an ISO image or a part of one, an xemu disk, an EEPROM dump, a
  BIOS or key file, a guest RAM snapshot or a private key, also inside a
  gzip, tar or zip file.
  It checks the checkout in the test suite and every push through its
  `pre-push` hook.
