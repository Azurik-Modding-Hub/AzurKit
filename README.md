# AzurKit

<img src="assets/icon/AzurKit.svg" width="128" height="128" align="right"
alt="AzurKit's icon: a disc of the four elements broken in four, its gold air piece lifted out">

Patch packs, sliders, a randomizer and character swaps for *Azurik: Rise of
Perathia* (Xbox), built from your own copy of the game.

AzurKit is the lean rewrite of Azurik_Modkit,
the proof of concept it replaces. Modkit is also its test oracle. Every port
step is checked against Modkit's recorded outputs: per-file sha256s,
copied into [`tests/oracle/`](tests/oracle/). AzurKit never imports Modkit's
code.

**Status:** AzurKit checks your image and builds it with all 17 patch packs,
each with its sliders, on both releases: fps_unlock (with its frame-rate
slider), player_physics (gravity and the player's movement, with a left-stick
toggle), qol_gem_popups, qol_other_popups, qol_pickup_anims, qol_skip_logo,
player_max_hp, air_shield_flaps, enemy_damage, enemy_scaling (enemies' and
bosses' health, damage, speed and size), qol_save_warp, qol_photo_mode, the
four memory packs (the load budget, and RAM past 64 MiB in xemu) and
qol_alloc_race. Those on by default (qol_alloc_race, the load budget and the
two upper-64 MiB packs) start ticked. The C shims ship prebuilt: nothing
compiles on your computer. A build carries its recipe in two small files at
the image's root, `/azurkit.json` and `/azurkit.bin`, which the game never
opens: `azurkit open` reads a build back into its recipe, a mods file that
`azurkit build --mods` builds again (the page does the same when you pick a
build as the image) (it can also set config.xbr's cells by
name and replace bytes in an XBR file). It builds from the command line, in the web page (pick your image, choose
packs and set their sliders, Build, then Save, and Copy link shares the
recipe; it remembers your packs and settings until you Reset to defaults, never
your image; it runs in your browser, and nothing is uploaded) or in the app, which shows the
same page in its own window and writes the build where you save it. The page
isn't hosted and the app isn't released yet: on macOS you build the app
yourself (below). The randomizer runs from the command line: `azurkit plan
--seed 2` prints a plan, `azurkit spoiler PLAN` its spoiler, and `azurkit
build --iso PATH --out PATH --seed 2` builds a randomized image (its tab on
the page comes next). Version 1 will add that tab, and character swaps and
variants. Players will get a web page and a download-and-run app;
developers will get `uv tool install azurkit`.

## xemu only

AzurKit targets [xemu](https://xemu.app), the Xbox emulator. Every in-game
check of a build is made in xemu, and some packs rely on what xemu gives
them, such as the RAM above 64 MiB. Real Xbox hardware is not a target: a
build may work on a console, but nothing here has been checked on one.

## No game data

This repository, its wheel, the app and the site hold no game file and no
bytes taken from one: you bring your own copy of the game.

- Builds read your ISO and stay on your computer.
- Share presets (recipes), never ISOs or game files.
- Recorded results are hashes (sha256) and lengths.
- [`tests/_leak_guard.py`](tests/_leak_guard.py) refuses a game image, a
  whole game file, an XBE or XBR, a save, a disk or EEPROM image, a private
  key or a disassembly listing, also inside a gzip file. It checks the
  checkout in the test suite and every push through its `pre-push` hook.

*Unofficial fan tool. Not affiliated with or endorsed by the rights holders of
Azurik: Rise of Perathia or Xbox.*

## Development

You need [uv](https://docs.astral.sh/uv/) 0.12 or newer, which provides Python
3.14.

```bash
uv run bootstrap.py                  # uv sync --locked, the leak guard's pre-push hook, Pyodide and the browsers
uv run --locked pytest               # the suite
uv run --locked pytest -m "not vanilla"   # only the tests that need no game data
uv run --locked azurkit verify [--iso PATH]              # is it vanilla USA or Europe, every file of it?
uv run --locked azurkit packs                            # the packs, and which a build applies by default
uv run --locked azurkit build --iso PATH --out PATH [--mods FILE] [--pack NAME ...] [--no-pack NAME ...] \
    [--no-defaults] [--pack-param PACK.SLIDER=VALUE ...] # a slider takes any finite number, never clamped
uv run --locked azurkit open BUILD                       # a build's recipe, as a mods file for build --mods
uv run --locked python scripts/web_tools.py --site DIR   # the site: the page, Pyodide and the wheel
uv run --locked python -m azurkit [serve]                # the app: the page in a window (serve: only its address)
uv run --locked python scripts/freeze.py --dist DIR      # the app frozen: DIR/AzurKit.app on macOS
uv run --locked python -m shimkit [--check]              # rebuild the prebuilt shim objects (zig, dev only)
uv run --locked --group icon python assets/icon/render.py # rebuild the icon from its sources (macOS)
```

The vanilla tests read the two images, found by `AZURKIT_ISO` (USA) and
`AZURKIT_ISO_EUROPE`, or as `usa.iso` and `europe.iso` in the user data folder
(on macOS, `~/Library/Application Support/AzurKit/`). A run that selects one
of these tests without its image stops with one message: no test is quietly
skipped. The `web` tests run AzurKit under Pyodide on Node, and the page in
headless Chromium and in WebKit (Safari's engine); they need Node, and the
Pyodide, Chromium and WebKit that `uv run bootstrap.py` fetches into `.tools/`
(`-m "not web"` leaves them out).

Contributors and agents start at [`AGENTS.md`](AGENTS.md).

## License and credits

MIT ([`LICENSE`](LICENSE)). [`NOTICE.md`](NOTICE.md) credits Jett Tripp
(JTCPP), whose Elemental_Games_Modding randomizer is where Azurik_Modkit began
(none of his code is in this repository), and Azurik Perathia's Azurik Debug
Menu, the photo mode's design.
