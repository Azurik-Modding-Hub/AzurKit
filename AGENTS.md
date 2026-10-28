# AGENTS.md: rules for agents and contributors

AzurKit is the lean, public rewrite of Azurik_Modkit. Modkit is its reference
and test oracle: a port is done when its output matches Modkit's byte for byte,
file by file. [`README.md`](README.md) says what AzurKit is. These rules bind.

## Setup and tests

```bash
uv run bootstrap.py                         # once, in the main checkout: uv sync --locked, the pre-push hook
uv run --locked pytest -q <files>           # targeted tests while you work
uv run --locked pytest                      # the whole suite
uv run --locked pytest -m "not vanilla"     # the pure tier: no game data
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

## The engine's contracts

- **Layers:** `core <- edits <- tools <- sdk <- {cli, app}`. The three tools
  (`mods`, `randomizer`, `characters`) never import each other. import-linter
  holds this (see `pyproject.toml`).
- **AST rules:** `core`, `edits` and `tools` hold no threads, processes,
  subprocesses, prints or exits, so the web page's worker runs them as they
  are. Only `tools/characters` imports numpy, and nothing imports capstone,
  unicorn, zig or Tk. `tests/test_contracts.py` checks these, along with
  import-linter's contracts.

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
  (or the whole suite) in the background under a lock, and prints a key and a
  receipt path. `--wait 540` waits for the result; exit 3 means it is still
  running, so issue the same command again.
- **Landing:** `uv run --locked python scripts/land.py <branch>` fast-forwards
  `main` once a passing receipt covers the branch's head. There is no remote
  until AzurKit goes public (D137, D91: Azurik-Modding-Hub at 4.4).

## Environment

- Scratch goes in `mktemp -d /tmp/azurkit-<what>.XXXXXX`. Delete it by its exact
  path.
- No home paths in tracked files.
- **xemu only (D601):** in-game checks run in xemu. Real hardware isn't a target.
- **Ask nothing (D115):** where a decision is missing, take the recorded default
  or your recommendation, and say so in your report.
