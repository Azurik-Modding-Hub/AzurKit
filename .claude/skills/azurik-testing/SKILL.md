---
name: azurik-testing
description: >-
  Running and writing AzurKit tests. Load BEFORE adding, changing,
  deleting or skipping a test, fixing an issue (each fix owes one
  behavior-named test), or choosing which tests to run. Holds the tiers
  and markers (pure, vanilla, europe, web, xemu, ghidra), the empty skip
  allow-list, the one rerun and flakes (D1170), goldens and facts,
  determinism, the leak guard, the simulator's levels and the reach tests,
  the perf gate's debt rows, CI's tiers and suite hangs. Triggers: "run
  the tests", "which tests should I run", -k, test-for-va, "why did this
  skip", skipif, xfail, "vanilla: N run", "flaky", -n 8, "golden",
  record_goldens, gen_facts.py, "leak guard", "behavior-named test",
  --browsers.
---

# azurik-testing: running and writing tests

AGENTS.md's Setup and tests binds; `docs/INTERNALS.md`'s holds the detail this card points into. Run every command from
the checkout's root with `uv run --locked`. A lane finds the images through `AZURKIT_ISO` and
`AZURKIT_ISO_EUROPE` (export both to the main checkout's images) or the user data folder's
`usa.iso` and `europe.iso`. Ported from Modkit's skill (Step 4.16a2).

## When NOT to use this skill

- uv, Python, the images, Node and the browsers: `azurik-dev-environment`. Gates per change class,
  commits, landing: `azurik-change-control`. Vanilla numbers a behavior test asserts:
  `azurik-game-reference`. Seeing it in game: `azurik-xemu-oracle`. `tests/mock_ghidra.py` and the
  Ghidra tests: `azurik-ghidra-mcp`.

## 1. Owner rules (binding)

- **Lean (D10, D37, D150):** the fewest tests that pin a behavior, one table-driven test rather than
  near-copies, each named by the behavior, in a behavior-area file (never a `test_bughunt_*` or
  wave-named one). Removing redundant tests is a goal; a step adding more than a handful says why. A
  new pack owes no byte test: its goldens and the facts pin it.
- **No count rule:** every behavior stays pinned by a test, a golden or a facts entry. To delete a
  test, name what it pinned and what still pins it.
- **Failures never become skips:** no new `skipif`, `SkipTest` or `xfail`, no wider guard, no
  allow-list entry. `tests/skip_allowlist.toml` is empty (Q277): any skip fails the run.
- **Nothing small blocks (D1170):** a failed test reruns once at once (`tests/_rerun.py`); one that
  passes it is a recorded flake (the summary's "flaky: N passed on their one rerun", the receipt's
  `flakes`, the flake ledger) with a fix lane, and the run passes; one that fails twice fails it. A
  rerun is recorded, never hidden, never a skip.
- **When a truth goes red, suspect the code or the address first** (a golden, the facts, the
  prologue guard in `tests/test_shims.py`); never widen `PROLOGUE_FIRST_BYTES` or re-record to get
  green.
- **Game bytes:** goldens and facts hold sha256 and lengths; a test may hold game files and bytes
  (D961), never the ISO; failure output never prints them (`tests/_byte_safe.py` redacts long bytes
  reprs and hex runs).

## 2. Running tests

```bash
uv run --locked pytest -q tests/test_packs.py                         # one file (or ::test_name, or -k word)
uv run --locked python -m devkit re test-for-va <pack|0xVA|name> [--run] # the tests holding a pack, VA or function
uv run --locked pytest -q tests/test_packs.py tests/test_shims.py      # the facts and the shim drift guards
uv run --locked python scripts/record_goldens.py --check [GOLDEN ...]   # the goldens, recorded again and compared
uv run --locked pytest -m "not vanilla"                                # the pure tier: no game data
uv run --locked pytest -m "not europe"                                 # no Europe image
uv run --locked pytest -m "not web"                                    # no Pyodide, Node or browsers
uv run --locked pytest -q tests/test_site.py --browsers=chromium -n 2  # the page in one browser (in a window, §9)
uv run --locked pytest -n 8 --dist loadgroup                           # the whole suite (fullsuite.py's)
uv run --locked python scripts/fullsuite.py <lane> --changed           # the gate: the changed area, a receipt
uv run --locked python -I tests/_leak_guard.py; echo "exit=$?"         # the leak guard alone
```

| You changed | Run |
|---|---|
| a pack, its sites, a slider | `test-for-va <pack> --run`, `tests/test_packs.py`, `record_goldens.py --check packs.json sites.json europe/packs.json europe/sites.json` |
| the facts, a game function, a shim source | `tests/test_packs.py`, `tests/test_shims.py` (after `python -m shimkit`), `gen_facts.py --check` |
| the randomizer (`tools/randomizer/`) | `azurkit plan --seed 2`, `tests/test_randomizer.py`, `tests/test_art.py`, `test_site.py -k tracker`, `record_goldens.py --check rando_plans.json tracker.json` |
| the characters, the Variants editor | `tests/test_characters.py`, `tests/test_variant_editor.py`, `tests/test_variant_library.py` |
| the page (`web/`) or the app | `tests/test_site.py`, `tests/test_service_worker.py`, `tests/test_hosts.py` (browser ones in a window) |
| `devkit/<area>/` | its test files (`test_simulator`, `test_reach_*`, `test_xemu_harness`, `test_ghidra`, `test_mcp`, `test_re_*`, `test_rando_db`, `test_model_verbs`, `test_devkit_*`) |
| `scripts/` (fullsuite, land, perf, CI's) | `tests/test_dev_tools.py`, `tests/test_tiers.py`, `tests/test_contracts.py` |
| docs, skills, roles | `tests/test_agent_files.py`, `tests/test_contracts.py`; re-run every command the change cites |
| `tests/conftest.py`, `tests/_*.py`, `pyproject.toml`, `uv.lock` | the whole suite |

- **Parallel (D991):** `-n 8 --dist loadgroup`, never in `addopts`. A test never leans on another's
  order or process; tests sharing one costly build take one `xdist_group` (conftest gives the frozen
  app's one). A grouped test's id gains `@<group>`. A killed worker ends CI's run by name
  (`--max-worker-restart=0`).
- **A test run writes only under `tmp_path`:** pytest keeps a failed test's folder, and of the failed
  sessions only the newest's (Step 4.5v2). A seat runs tests under an isolated `HOME` with an
  absolute `UV_CACHE_DIR`. The app never opens a window in a test (`AZURKIT_NO_WINDOW`, D839);
  Playwright launches headless only (conftest refuses any other).
- **A slow host:** the gate's run is killed past its cap (1,800 s, scaled by the load per CPU up to
  twice); a starved test fails on wall time. Read the load (`$EV/tools/load`); re-run the failures
  alone, by id without any `@<group>`. One that fails the same way alone is a hang: investigate it.
- **A hang that takes the network down: stop (AZ-312).** Workers stuck in `close()` or `sendto` with
  DNS or `curl -sI https://github.com` failing is an XNU TCP deadlock only a reboot clears: don't
  kill and retry or start another run; report it.
- Run tests only through pytest: `python -m tests.test_x` bypasses conftest.

## 3. Tiers, markers and the skip rule

| Marker | Means | Without it |
|---|---|---|
| `vanilla` | reads the USA image (the `usa_iso` fixture marks it) | a run selecting one stops with one message; `-m "not vanilla"` |
| `europe` | reads the Europe image (`europe_iso`; vanilla too) | the same; `-m "not europe"` |
| `pure` | everything else (conftest marks it) | |
| `web` | Pyodide on Node (`pyodide`) or the page in a browser (`browser`: Chromium, WebKit, Firefox, or `--browsers=NAME`) | stops naming what is missing; `-m "not web"` |
| `xemu` | devkit's xemu harness offline (macOS calls) | CI's Linux and Windows legs deselect it |
| `ghidra` | the GhidraScripts in the real Ghidra `bootstrap.py --with re` installs | fails naming it; `-m "not ghidra"`, as CI does |

A run prints `vanilla: N run`, `europe: M run` and `web: K run`. **Green:** no failure, no skip,
N and M at least 1 (D26). A europe test without vanilla is a usage error.

## 4. Fixtures and game data

- The images come only through `usa_iso` and `europe_iso` (paths; the identity gate checked them);
  read a file with `azurkit.core.iso`, never an extracted tree. Keep module-level code `None`-safe so
  the pure tier collects without the images.
- **Synthetic input first:** `tests/_xiso.py`'s `image({path: bytes})` builds a tiny XISO with no
  game bytes; saves, HDD images and keys are made in `tmp_path` (`tests/test_saves.py` signs with a
  random key found by its fingerprint).
- A test that drives a build writes its output under `tmp_path`, never beside an image.
- The page: drive it through the DOM (`element.click()`) and poll with `page.evaluate` (Chromium's
  headless shell fires no `requestAnimationFrame`); a WebKit context gets a home of its own; serve
  files from a process of its own (`tests/_page.py`'s `Served`); `docs/INTERNALS.md`'s web tier has the rest.

## 5. Writing ONE behavior-named test per fix

The test lands in the same commit as the fix.

1. **Name** it after the behavior, in words (`test_a_failed_test_runs_once_more_and_...`); the AZ id
   goes in the docstring.
2. **Place** it in the behavior-area file (`test_packs.py`, `test_randomizer.py`, `test_site.py`, ...).
3. **It fails for the stated reason without the fix** (check it as you write it, no proof owed),
   then passes with it.
4. **Assert exact values:** named constants, whole-buffer or whole-list equality, exact offsets.
   Not: a test that asserts nothing or only under an `if`, `len(x) >= 0`, `any(...)` or `rfind`
   over a buffer, a non-zero return code without its output, text of `inspect.getsource`, a count
   of a registry ("exactly N packs": derive the set), `except Exception` around an import, a
   toolchain probe that compiles the subject under test.
5. **The bug can't skip it:** synthetic input where it can; else the `usa_iso` fixture. Unicorn,
   capstone and mcp (the `devkit` group) are imported plainly: a broken install fails, never skips.
6. **Hermetic:** write only under `tmp_path`; pass `{**os.environ, ...}`, not a fresh `env`; give a
   subprocess explicit `cwd`, `env` and `timeout`.
7. **Style:** plain pytest functions with fixtures and `parametrize`, as the file does.

## 6. Determinism

`PYTHONHASHSEED` acts only at interpreter start: spawn one process per value, never set it in a
test, never pin one to make two runs agree.

```bash
for s in 0 1 2 3; do PYTHONHASHSEED=$s uv run --locked azurkit plan --seed 2 | shasum -a 256 | cut -c1-12; done
```

All four agree (the hash moves with the database). Pin:
`tests/test_randomizer.py::test_seed_2s_plan_is_the_same_in_two_processes_under_two_hash_seeds`.
For a build, build each seed into a `mktemp -d` output and compare `shasum -a 256`.

## 7. Goldens and facts

- `tests/goldens/` is AzurKit's truth for every family (AGENTS.md's The goldens): only
  `scripts/record_goldens.py [GOLDEN ...]` writes it (`--check` writes nothing); `cases.json` is the
  recipe, by hand. Name each golden re-recorded and why in the body; a case of another pack that
  moved is a regression.
- **Off the recording host (D1016):** Apple Silicon on Accelerate compares byte for byte; elsewhere a
  dress's float resources are compared close enough (`close.json`). No byte a golden holds may come
  from a matrix product.
- The facts (`src/azurkit/core/facts.<release>.json`): hand edits, then `scripts/gen_facts.py`;
  `tests/test_packs.py` holds them.
- The other recorded files and their writers: `azurik-change-control` §6.

## 8. The simulator and the reach tests

- `devkit/sim` (`docs/SIMULATOR.md`, dev only, USA only): L0 `static` (a build's structure), L1 `l1`
  (patched code well-formed: no SSE2 or other instruction a Pentium III lacks, m128 alignment, a
  call-replacing shim keeps `ret N`), L2 `l2` (the game's own jump, flap, walk and roll on a named
  fake state: `tests/test_simulator.py`, `tests/test_roll.py`), L3 (the game's step from a RAM
  snapshot; dev tools and sittings). Test a movement slider in L2, at the value the game consumes,
  not by its bytes; a movement feature is done only after one xemu sighting.
- **Blind spots:** `devkit/sim/data/sim_blind_spots.toml` lists what L2 can't judge (with each range's
  vanilla hash); L2 refuses a build that changes one unless the test is signed off with
  `test_simulator.py`'s `xemu_signoff("<session>")` naming a session the file lists. Edit the file by
  hand, never to get green.
- The reach engine (`devkit/reach`) and its derive run in the normal tiers with no marker
  (`tests/test_reach_engine.py`, `tests/test_reach_model.py`, `tests/test_movement_envelope.py`); a
  run past its cap is fixed for speed, never skipped.

## 9. The perf gate, the window and flakes

- `scripts/perf.py` times the player-facing ops a change reaches (`tests/_perf.py`'s registry) inside
  the gate's lock: an op over 3 s, its ceiling (`tests/perf_ceilings.toml`) or past 1 s with no
  progress is a perf-debt row (`perf-debt.jsonl` beside the receipts, a lane); only a clear
  regression against main's last passing full run, a memory peak, an error or a list that grows
  fails it (D1170). A seat runs only `perf.py <lane> --select HOST:GROUP` of its own ops.
- **The window:** browser, memory, perf or other heavy runs take `$EV/tools/window take <step>` and
  `window release <step>`, at `-n 2`, after `window status` shows no fullsuite run queued or running.
- A flake's fix lane finds its cause (a race, a timeout too tight on a busy box, a shared folder);
  never a longer sleep or a retry loop in the test.

## 10. CI's tiers

`tests.yml` runs `pytest -m "not vanilla and not ghidra"` (and `not xemu` off macOS) on the four
runners, and on a push in this repository the vanilla tier as parts (`--shard=LABEL:K/N`, cut by
`tests/ci_durations.json`, which `scripts/ci_shards.py` refreshes from a run's logs) with the images
rebuilt from the private game-data repo. A failed test gets its one rerun there too; the job's
summary lists each that passed it. `tests/test_tiers.py` and `tests/test_contracts.py` pin the
workflows.
