---
name: azurik-dev-environment
description: >-
  Set up, check and fix an AzurKit dev environment. Load for first-time
  setup and Python 3.14, uv sync --locked and uv.lock, the dependency
  groups (dev, app, devkit, icon), bootstrap.py (the hook, Pyodide and the
  browsers in .tools/, --with re), a lane's setup, where the USA and Europe
  images live (AZURKIT_ISO, the user data folder, azurkit verify), the
  environment variables, zig (shimkit, nativekit), devkit's areas, the
  azurik MCP server failing to connect, pytest stopping on a missing
  image, Node or browser, the private game-data repo, and the owner's
  environment rules.
---

# AzurKit's dev environment: set up, check, troubleshoot

Run every command from the checkout's root with `uv run --locked`. Players install from README;
contributors set up with `docs/DEVELOPMENT.md`; AGENTS.md's Setup and tests and Environment bind.
Ported from Modkit's skill (Step 4.16a2).

## When NOT to use this skill

- Running and writing tests: `azurik-testing`. Ghidra, the bridge, `--with re`'s tools in depth:
  `azurik-ghidra-mcp`. xemu: `azurik-xemu-oracle`. Packs and shims: AGENTS.md's Packs.

## 1. Python 3.14 through uv (D22)

`pyproject.toml` requires Python 3.14 and uv 0.12 or newer, `.python-version` says 3.14, and
`uv.lock` is committed (protected). uv provides the interpreter; nothing is installed globally.

| Group (`[dependency-groups]`) | Holds | Synced |
|---|---|---|
| `dev` | pytest, pytest-xdist, import-linter, playwright, ziglang 0.16.0 (zig: shimkit, nativekit) | by default |
| `app` | PyInstaller, pywebview (the frozen app, `scripts/freeze.py`) | by default |
| `devkit` | capstone, Unicorn 2.1.4 (GPL, never shipped), mcp 2.3.0 | by default, so a broken install fails devkit's tests rather than skipping them |
| `icon` | resvg-py, Pillow (`assets/icon/render.py`, macOS) | `--group icon` |

The wheel's only dependencies are platformdirs and numpy. Never a bare `pip`, `python` or `python3`
(a host's pip config may let a bare pip write into the system Python); `--locked` stops on a stale
lock instead of re-locking it. Run `uv lock` only when your step owns `pyproject.toml`.

## 2. Install and lanes

```bash
uv run bootstrap.py [--no-hooks] [--no-web] [--with re [--allow-scripts]]   # the main checkout, once
uv sync --locked                                                            # a lane, with uv's managed Python
uv run --locked python -m devkit [AREA [VERB ...]]                          # devkit's areas and verbs
```

- **`bootstrap.py`** (stdlib): `uv sync --locked`, the leak guard's `pre-push` hook in the common git
  dir (every worktree's; it never changes git config or another's hook), Pyodide's pinned core and
  Playwright's headless Chromium, WebKit and Firefox into the main checkout's `.tools/`
  (`scripts/web_tools.py`, `PLAYWRIGHT_BROWSERS_PATH`, never the user's cache), which every lane
  uses; `--with re` adds Ghidra 12.1.2, its JDK and the stock GhydraMCP (about 1.2 GB) and prints,
  never runs, the `claude mcp add` line. **Never run it in a lane.**
- A lane: `git -C <main checkout> worktree add --no-track -b p2/<step>-<slug> <lanes>/<step> <base>`,
  then `uv sync --locked` in it; `git worktree remove` it when done.
- `devkit/` is the developer side (D950, D990: dev only, never in the wheel, the site or the app;
  `tests/test_contracts.py` bars `src/` from importing it): `re`, `builds`, `xbr`, `rando`, `sim`,
  `reach`, `xemu`, `models`, `mcp`, `movies`, `audio`, each verb in its `devkit/<area>/README.md`.
- The web tier needs Node 24 on PATH; the frozen app's tests build it with PyInstaller.

## 3. Sanity check

```bash
uv run --locked azurkit verify          # each image: vanilla USA or Europe, every file of it
uv run --locked python -m devkit        # the areas import
uv run --locked python -m shimkit --check && uv run --locked python -m nativekit --check   # zig rebuilds match
uv run --locked pytest -q tests/test_gate.py tests/test_leak_guard.py
```

## 4. Game data: where it lives

| What | Where | Read by |
|---|---|---|
| The USA and Europe images | `AZURKIT_ISO`, `AZURKIT_ISO_EUROPE`, else `usa.iso` and `europe.iso` in the user data folder (`src/azurkit/core/gate.py`); read-only | the gate, every build, the vanilla and europe tests. A lane exports both to the main checkout's images |
| Content (booblord, community packs) | `AZURKIT_CONTENT`, else `content` in the user data folder; the source `AZURKIT_CONTENT_SOURCE` | `azurkit content`, the goldens that wear booblord |
| Variants | `AZURKIT_VARIANTS`, else `variants` in the user data folder | the characters |
| xemu fixtures (drive, EEPROM, BIOS) | `AZURIK_XEMU_FIXTURES`, else the user data folder's `xemu-fixtures` link | `devkit/xemu` only |
| The L3 store, `reach-truth/` | `l3-snapshots/` and `reach-truth/` in the user data folder | `devkit/sim`, `devkit/reach` (read in place) |
| Caches, receipts | the user cache folder; receipts in the common git dir's `azurkit-receipts/` (`AZURKIT_RECEIPTS`) | rebuilt on demand |
| Builds | an explicit output that isn't the input, scratch in `mktemp -d` | |

Other switches: `AZURKIT_NATIVE=0` runs the compiled kernels' Python twins; `AZURKIT_CORES` and
`AZURKIT_RAM` play a smaller computer (the perf gate's 4-core profile); `AZURKIT_NO_WINDOW` keeps
the app shut (conftest sets it); `AZURIK_BLENDER`, `AZURIK_BLENDER_SLOTS` find and bound Blender.

## 5. MCP servers

- `.mcp.json` launches the `azurik` server: `uv run --locked python -m devkit.mcp` (`docs/MCP.md`).
  "Failed to connect": run `uv run --locked python -c "import devkit.mcp"` from a shell (a stale
  lock, or a PATH without uv); never change the owner's MCP registration.
- The `ghidra` server is the stock bridge in `.tools/`: `azurik-ghidra-mcp`.

## 6. Known hazards

| Symptom | Fix |
|---|---|
| ``The lockfile at `uv.lock` needs to be updated, but `--locked` was provided`` | `uv lock` only when your step owns `pyproject.toml`; never drop `--locked` |
| "vanilla tests need the verified ... image", nothing ran | export `AZURKIT_ISO` and `AZURKIT_ISO_EUROPE`, or `-m "not vanilla"` / `-m "not europe"` |
| A run stops naming Pyodide, Node or a browser | `uv run bootstrap.py` in the main checkout, Node on PATH, or `-m "not web"` |
| The network goes down mid-suite (AZ-312) | stop and report: only a reboot clears it |
| A crash dialog on the owner's screen | run anything that may crash under `lldb --batch` |

## 7. The owner's environment rules

- **Minimal, reversible changes:** list each change outside the repo with its revert; system-wide
  installs only when a step needs one. Keep only the newest stable version of a tool, pinned; check
  what depends on an old one before removing it.
- **`/tmp` is shared:** `mktemp -d /tmp/<step>-<what>.XXXXXX`; delete your own by exact path
  (D147), never a glob, never what you didn't make, the images, an xemu folder or its fixtures.
- **The owner's screen (D839):** no window, no headed browser, no `open AzurKit.app`; the app runs
  only under `AZURKIT_NO_WINDOW` or as `serve`. Never hold or fill memory or CPU to mimic a smaller
  machine: measure peaks.
- **Never commit** the ISO, whole or in parts, EEPROMs, HDD images, RAM snapshots or keys
  (`azurik-change-control` §9).
- **The private game-data repo,** `Azurik-Modding-Hub/AzurKit-gamedata` (D1028): the images' parts
  for CI alone, read with the `gamedata` environment's read-only deploy key (`GAMEDATA_DEPLOY_KEY`).
  Never make it public, fork or mirror it, print or upload its bytes; its key procedure is private.
