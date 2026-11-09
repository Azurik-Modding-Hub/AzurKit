# devkit/doctor: is this machine ready? (dev only)

Modkit's `azurik-mod doctor`, its checks pointed at AzurKit's own tools. A
command of its own (the area's package has a `main`), run from the
checkout's root:

```bash
uv run --locked python -m devkit doctor                    # one line a check; exit 1 when one fails
uv run --locked python -m devkit doctor --uninstall-hints  # every place outside the checkout AzurKit may write
```

Each check prints `ok` or `FAIL`; an optional tool is `ok` either way and
says so.

| Check | What it reads |
|---|---|
| Python 3.14 | the interpreter running it |
| uv, uv.lock in sync | `uv --version`; `uv lock --check`, then `uv sync --locked --check --inexact` (what `uv run --group re` adds isn't drift) |
| USA image, Europe image | each release's image through the resolver (`AZURKIT_ISO`, `AZURKIT_ISO_EUROPE`, else the user data folder) and the whole gate, every file read (a stamp isn't trusted); the suite needs both |
| zig | the pinned zig (`ziglang`, the dev group) building a probe as `shimkit` builds a shim, its `.text` the pinned pentium3 code (Modkit's pin), in a temporary folder |
| mcp | `devkit.mcp.serve` imports |
| libunicorn | what FastL3's workers load: the patched build `python -m devkit reach build-unicorn` makes, else the wheel's (optional) |
| web tools | Node on PATH, Pyodide's pinned core and wheels and each browser in the main checkout's `.tools` (`scripts/web_tools.py`) |
| Blender, ffmpeg | where the model verbs find them (optional) |
| xemu | the fork build in the oracle's fixtures, `AZURIK_XEMU_FIXTURES` (optional) |
| RE tools | each `.ok` stamp against `devkit/re/tools.toml` for this host, and no Ghidra extension installed twice (optional until installed) |
| Ghidra endpoint, Ghidra project | with Ghidra installed: the endpoint the RE verbs use (only something that doesn't speak JSON fails) and whether a Ghidra holds the project `ghidra-serve` last copied (the passive lock probe) |

Then the free disk where builds and tests write (`warn` under 50 GiB), the
leak-guard hook (`warn` when git runs none on a push: the pre-push
`uv run bootstrap.py` writes, or a `core.hooksPath` hook that hands each push
to it; an older text of it is said) and a checkout in a cloud-synced folder
(`warn`). It reads only: it writes no file but zig's probe in a temporary
folder, never a hook or git config. `tests/test_devkit_doctor.py` pins it.

Where it differs from Modkit's: Tk and the stray state files are gone with
the GUI and `iso/`; the web tools, Blender and xemu are new; there is no
wheel-install mode (devkit is the checkout's alone).
