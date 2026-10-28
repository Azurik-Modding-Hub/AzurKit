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
uv run --locked python scripts/freeze.py --dist DIR   # the app (D732): DIR/AzurKit, a PyInstaller onedir
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
  runtime) takes the `pyodide` fixture (it becomes `web`; `tests/_pyodide.py`
  runs the `azurkit` command from the wheel alone). A run that selects one
  needs Node on PATH and Pyodide's pinned core, which `uv run bootstrap.py`
  puts in the main checkout's `.tools/` for every lane
  (`scripts/web_tools.py`). Without them the run stops with one message; the
  opt-out is `-m "not web"`. The summary prints `web: K run`.
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
  either release's `default.xbe`, by file, line and length
  (`tests/test_leak_guard.py`).
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
- Describe patch bytes in prose: four or more comment lines that read as
  x86 instructions are a disassembly listing to the leak guard.
- A port is done when its cases match the oracle: the facts site by site,
  then G1 per file on both releases (`tests/test_packs.py`).

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

- **The site** runs the wheel under Pyodide in a worker; `tests/test_hosts.py`
  runs the gate there.
- **The app** (D732) is `python -m azurkit` (`src/azurkit/__main__.py`): with
  arguments the `azurkit` command, with none the page (`web/`) in a
  pywebview window, else the default browser, served by `azurkit.app` on
  127.0.0.1 to this launch's token only. `scripts/freeze.py` builds its
  PyInstaller onedir; pyinstaller and pywebview are the `app` dependency
  group, never the wheel's. The bundle is read-only: every write goes
  through platformdirs. It carries no Unicorn, zig, capstone or GPL code;
  `tests/test_hosts.py` checks each name in it and its licence.

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
  and `europe: M run`, N and M at least 1 (D26). There is no remote
  until AzurKit goes public (D137, D91: Azurik-Modding-Hub at 4.4).

## Environment

- Scratch goes in `mktemp -d /tmp/azurkit-<what>.XXXXXX`. Delete it by its exact
  path.
- No home paths in tracked files.
- **xemu only (D601):** in-game checks run in xemu. Real hardware isn't a target.
- **Ask nothing (D115):** where a decision is missing, take the recorded default
  or your recommendation, and say so in your report.
