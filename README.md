# AzurKit

Patch packs, sliders, a randomizer and character swaps for *Azurik: Rise of
Perathia* (Xbox), built from your own copy of the game.

AzurKit is the lean rewrite of Azurik_Modkit,
the proof of concept it replaces. Modkit is also its test oracle. Every port
step is checked against Modkit's recorded outputs: per-file sha256s,
copied into [`tests/oracle/`](tests/oracle/). AzurKit never imports Modkit's
code.

**Status:** AzurKit reads and checks your image and packs it back unchanged
(step 4.1b1), so there is nothing to play yet. Version 1 will carry the web page, the 17 patch packs and their sliders on
both releases (USA and Europe), character swaps and variants, and the
randomizer. Players will get a web page and a download-and-run app;
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
  key or a disassembly listing. It checks the checkout in the test suite and
  every push through its `pre-push` hook.

*Unofficial fan tool. Not affiliated with or endorsed by the rights holders of
Azurik: Rise of Perathia or Xbox.*

## Development

You need [uv](https://docs.astral.sh/uv/) 0.12 or newer, which provides Python
3.14.

```bash
uv run bootstrap.py                  # uv sync --locked, the leak guard's pre-push hook, and Pyodide
uv run --locked pytest               # the suite
uv run --locked pytest -m "not vanilla"   # only the tests that need no game data
uv run --locked azurkit verify [--iso PATH]              # is it vanilla USA or Europe, every file of it?
uv run --locked azurkit build --iso PATH --out PATH     # the identity build: the image, no edits yet
uv run --locked python -m azurkit                        # the app: the page in a window (a placeholder until 4.1d)
uv run --locked python scripts/freeze.py --dist DIR      # the app frozen: DIR/AzurKit, a PyInstaller onedir
```

The vanilla tests read the two images, found by `AZURKIT_ISO` (USA) and
`AZURKIT_ISO_EUROPE`, or as `usa.iso` and `europe.iso` in the user data folder
(on macOS, `~/Library/Application Support/AzurKit/`). A run that selects one
of these tests without its image stops with one message: no test is quietly
skipped. The `web` tests run AzurKit under Pyodide on Node, as the web page
will; they need Node and the Pyodide that `uv run bootstrap.py` fetches
(`-m "not web"` leaves them out).

Contributors and agents start at [`AGENTS.md`](AGENTS.md).

## License and credits

MIT ([`LICENSE`](LICENSE)). [`NOTICE.md`](NOTICE.md) credits Jett Tripp
(JTCPP), whose Elemental_Games_Modding randomizer is where Azurik_Modkit began.
None of his code is in this repository.
