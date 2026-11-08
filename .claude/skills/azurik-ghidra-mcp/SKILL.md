---
name: azurik-ghidra-mcp
description: >-
  The Ghidra side of AzurKit's devkit (dev only) and the stock GhydraMCP
  bridge (the `ghidra` MCP server). Load to install or debug Ghidra 12.1.2
  in .tools/ (bootstrap --with re), choose a port (8192 vs 8193, a serve's
  8212-8229, instances_use), run ghidra-serve, ghidra-query, ghidra-apply,
  ghidra-backup, ghidra-sync, ghidra-snapshot or struct-diff, refresh
  devkit/re/data/ghidra_snapshot.json, import SDK headers, find callers
  without Ghidra (devkit re xbe insns or calls), or when the ghidra MCP
  server "failed to connect". Read it before anything opens "Azurik
  Ghidra.gpr".
---

# AzurKit's Ghidra side

The RE half of devkit (`devkit/re/`, dev only: none of it ships): a live
Ghidra, the stock GhydraMCP plugin that serves it over HTTP, the one Python
client (`devkit/re/ghidra_client.py`), the verbs on it, the four
GhidraScripts (`devkit/re/ghidra_scripts/`) and the committed snapshot of
Ghidra's names. Ghidra is optional: nothing that builds, tests or ships
needs it. It runs at 12.1.2 on Temurin JDK 25, on **stock parts** only
(12.1.3 and 12.1.4 ship no macOS decompiler; D89). Ported from Modkit's
skill in Step 4.11d2; the verb reference is `devkit/re/README.md`.

Every verb is `uv run --locked python -m devkit re VERB [ARGS ...]`, run
from the checkout's root.

## When NOT to use this skill

- **The `azurik` MCP server's game-data tools:** `docs/MCP.md`.
- **Facts by VA, ABI or struct field:** `azurik-game-reference`, the facts
  (`src/azurkit/core/facts.<release>.json`) and the RE data
  (`devkit/re/data/`: the anchors, `structs.h`, the function notes). A
  Ghidra VA is not a file offset: convert with `devkit re xbe addr`.
  Ghidra's `EXTERNAL:NNN` is a display index, not the kernel ordinal (the
  facts' `kernel` holds each slot).
- **A new shim or a hook site:** `devkit re new-shim`, `plan-trampoline`
  and AGENTS.md's Packs.

## 1. Install and run

- **Install:** `uv run bootstrap.py --with re` (in the main checkout; a
  lane uses the main checkout's `.tools/`, unless it installed its own to
  try a new pin) fetches the five `devkit/re/tools.toml` entries for the
  host, checks each sha256 before unpacking it, and writes
  `.tools/<name>/.ok` = `"<version> <sha256>"`; a re-run fetches only what
  changed. It installs `.tools/ghidra/` and `.tools/jdk/` and unzips
  GhydraMCP and ghidra-xbe (no licence: downloaded only, never committed)
  into `.tools/ghidra/Ghidra/Extensions/`. Each run rewrites the end of
  `.tools/ghidra/support/launch.properties`: `JAVA_HOME_OVERRIDE`; the
  settings, cache and user-scripts folders under `.tools/ghidra-home/`;
  `-Dghidra.mcp.bind.host=127.0.0.1`;
  `-Dghidra.mcp.cors.origin=http://127.0.0.1:1`; and
  `-Dghydra.dev.allowScripts=true` only with `--allow-scripts`. The paths
  are absolute: each checkout installs its own, never a copy of another's.
- **Start it:** `.tools/ghidra/ghidraRun`; accept the User Agreement once;
  open the project and `default.xbe` in the CodeBrowser, then enable the
  plugin there once: File > Configure > Developer, listed as GhydraPlugin
  (until then only the project window serves, with no program; AZ-196).
  Agents that only read need no window: `ghidra-serve` (§2 rule 2).
  **Never** use File > Install Extensions: a second copy in
  `.tools/ghidra-home/.../Extensions/` stops Ghidra from starting. No
  project ships with the repo: a contributor creates one and imports
  `default.xbe` (the ghidra-xbe loader reads it).
- **MCP:** bootstrap prints `claude mcp add --scope local ghidra -e
  GHIDRA_HYDRA_HOST=127.0.0.1 -- uv run --script
  <checkout>/.tools/ghydra-bridge/bridge_mcp_hydra.py` and never runs it.
  The bridge runs in the environment its own script header pins (mcp 1,
  requests), never AzurKit's (mcp 2 is devkit's). `GHIDRA_HYDRA_HOST`
  pins it to the IPv4 loopback (its default `localhost` tries `::1`
  first). It starts on 8192: call `instances_use(8193)` (the owner's
  CodeBrowser) or a serve's port once per session (§3).
- **Header import and equates:** `scripts_run(source=<text of
  devkit/re/ghidra_scripts/ImportHeader.java>, args=["/Cat", "<abs
  header.h or inline C>", "-I<abs dir>"])` and `scripts_run(source=<text of
  CreateEquate.java>, args=["0x11e51", "1", "NAME"])`. `scripts_run` needs
  `--allow-scripts` (arbitrary Java: run bootstrap again without it
  afterwards). Types land at `/Cat/T` (signatures in `/Cat/functions/`,
  `#define` enums in `/Cat/defines/`), never `/Cat/<file>.h/T` (AZ-036). A
  re-import keeps existing types; a missing `.h`, a parse error or a
  conflicting same-name type fails the run with nothing imported. The Xbox
  SDK's headers (GPL-2; Modkit's `vendor/xbox-includes`, patched for this
  import) are not in AzurKit and nothing fetches them yet: never vendor
  them; import a header from a copy outside the repository.
- **A VA in the middle of a function:** the bridge's `functions_decompile`
  and `functions_get` answer "Function not found" for any VA that isn't an
  entry point; `functions_get_containing` finds the function that holds it.
- **Without Ghidra:** `devkit re xbe insns --mnemonic M --operand S`, `xbe
  calls [--to VA]`, `xbe dis`, `xbe fn` and `xbe read` (capstone; their
  listings name addresses from the facts, the snapshot and the anchors).

## 2. Hard rules for the owner's live project

The owner's project (`Azurik Ghidra.gpr` and `.rep`, program `default.xbe`,
image base `0x00010000`) lives outside every checkout, as do its backups;
its path is the owner's and never written in a tracked file. Pass it as
`--project`.

1. **Never open the owner's project headlessly, or write it on disk, while
   a Ghidra holds it** (`analyzeHeadless`, pyghidra, any script that opens
   `Azurik Ghidra.gpr`). Check with the passive lock probe, not `pgrep` (a
   serve matches it):
   ```bash
   uv run --locked python -c "import sys; from pathlib import Path; from devkit.re.ghidra_project import lock_state; print(lock_state(Path(sys.argv[1])))" "<the .gpr>"
   ```
   `held` (with the PID): stop, use HTTP. `free` or `stale`: nothing holds
   it. `unknown` (Windows): treat as held. `ghidra-serve status` prints the
   same answer. The one headless writer is `ghidra-apply --apply` (rule 2),
   which refuses by itself while the project is held. Never open the
   project in a Ghidra newer than 12.1.2 without a backup: 12.1.4 upgrades
   the x86 language on open and 12.1.2 then refuses it.
2. **Headless work uses a copy, through `ghidra-serve`.** `devkit re
   ghidra-serve start --project "<the .gpr>" [--port N]` copies the project
   (reading it only; it may copy while the GUI holds it, checking the
   content fingerprint before and after) into `ghidra-serve/<port>/` in the
   user cache folder and serves it read-only on 127.0.0.1 (not under
   `.tools`, and not under a hidden folder: Ghidra refuses a project path
   with a dot-folder). `GET /program`'s `programId` is
   `AzurikServe:/default.xbe` for a serve's copy and `Azurik
   Ghidra:/default.xbe` for the owner's GUI: read it before any write. A
   write to a serve changes only its in-memory copy until `stop` (`status`
   says DIRTY). Agents' serves use ports 8212-8229 (the default 8212;
   `--port N`, then `instances_use(N)`), never 8192/8193 (Modkit's agents
   took 8194-8211).
   **`ghidra-apply` is the only thing that writes the real project
   headlessly:**
   1. `devkit re ghidra-apply --plan P --project GPR` is a dry run on a
      copy: each plan line (`rename` of a function, `rename_label`, each
      with the name expected now; `comment`; `delete_equate`;
      `delete_category`, with what uses the category's types;
      `create_function`, which `ghidra-sync --emit-plan` writes) is
      `pending` with what it overwrites, or `in effect`; then the plan's
      sha256 and the `--apply` command. Read every line.
   2. Check the lock probe says `free` or `stale`.
   3. Run the printed `devkit re ghidra-apply --apply --plan P --plan-sha256
      <sha256> --project GPR`. `--project` is required. It refuses another
      sha256, a missing Ghidra or a held project before writing (exit 2);
      backs the project up into `ghidra-backups/` beside its folder (a
      verified apply keeps only its own backup; a failed one deletes none);
      applies the plan in one transaction (`ApplyPlan.java`); verifies it on
      a copy; and after any failure, timeout or Ctrl-C ends its process
      group and puts the backup back byte-identical (exit 1). Under a
      Ghidra that holds the project it never restores: exit 3, naming the
      backup to restore by hand. `ghidra-backup list|restore <name>|prune`
      handles backups (`restore` and `prune` need `--project`; a restore
      moves the current project aside).

   Run `--apply` only with the sha256 of a dry run you have read, and never
   against the owner's project to test the verb (test on an APFS clone in a
   `mktemp -d` with no dot-folder in its path).
3. **HTTP writes change the project the port serves; on 8193 that is
   usually the owner's real project.** They include `ghidra-sync --apply`
   and every bridge write tool (renames, creates, deletes including
   `programs_delete`, `*_set_*`, `*_update_*`, `comments_set`,
   `memory_write`, `analysis_run`, `scripts_run`). Dry-run and read first,
   then write. `ghidra-sync --apply` writes only to the program its
   `--target` names (anything else, or no `--target`: exit 2, nothing
   written; AZ-197) and only on the USA program (AZ-326). It keeps every
   plate comment that lacks its line `Auto-generated by azurik-mod
   ghidra-sync.` (Modkit's words, kept so it refreshes the comments
   Modkit's sync wrote; `--force` replaces the rest, Q204): read the plan's
   `plate comments` block before an apply and quote it in your report. The
   bridge's write tools have no such check: read `programId` first.
   `ghidra-sync --push-structs --recreate-structs` deletes and recreates
   structs, wiping the types of variables that used them.
4. **Name throwaway write-test artifacts `AZURIK_SMOKETEST_*` or
   `AzurikSmokeTest*`.** Undo removes them only in the session that made
   them; after a restart, delete them by name.
5. **Snippets of disassembly or decompiler output may be committed (game
   assets may be, D961; the image never);** the Ghidra project stays out
   of the repository, and game bytes are never printed.

## 3. Ports (AZ-034: one client, one default)

| Consumer | Port | Notes |
|---|---|---|
| GhydraMCP inside Ghidra | The project window takes **8192**, so the CodeBrowser holding `default.xbe` usually gets **8193** | Bound to `127.0.0.1`. Nothing pins 8193: the plugin takes the first free port from 8192 |
| `devkit re ghidra-serve` | **8212** unless `--port N`; a busy port is refused (exit 2), no fallback | Listens on `127.0.0.1` only. Agents' serves: 8212-8229 |
| `devkit re ghidra-query` | **8212** (a serve's) | Reads only a serve's copy; any other program refuses (exit 2) |
| The stock bridge (`ghidra` MCP server) | Starts on **8192** | Call `instances_use(8193)` or a serve's port once per session |
| `ghidra-sync`, `ghidra-snapshot`, `struct-diff`, `new-shim --ghidra` | **8193** on `127.0.0.1`; `--port N` changes it | `ghidra_client.py` is the only client; no env vars, no `--host`; always the IPv4 loopback (AZ-153). They exit 2 when nothing answers; `new-shim` carries on without ABI pickup |

## 4. The verbs and the snapshot

| Verb | Needs | Notes |
|---|---|---|
| `ghidra-serve start\|status\|stop` | `.tools/ghidra`, not a running Ghidra | A read-only copy served headlessly (§2 rule 2); `status` says alive, clean or DIRTY, current or STALE, and the project's lock |
| `ghidra-query decompile\|disasm\|xrefs-to VA` | a serve | Only GETs; `disasm` never prints bytes (D87) |
| `ghidra-apply --plan P --project GPR [--apply --plan-sha256 <sha256>]` | `.tools/ghidra`; Ghidra **closed** for `--apply` | §2 rule 2; exit 2 refusal, 1 failure (project as before), 3 could not be put back |
| `ghidra-backup list\|restore <name>\|prune [--keep N]` | nothing | `restore` refuses while a Ghidra holds the project |
| `struct-diff [--offline]` | a live Ghidra unless `--offline` | `devkit/re/data/structs.h` against Ghidra's Data Type Manager |
| `ghidra-sync [--apply --target <programId>] [--push-structs] [--emit-plan FILE]` | a live Ghidra | A dry run by default: every VA the facts' functions, the anchors and the packs name whose Ghidra name differs; keeps names someone chose and hand-written plate comments; `--force` overwrites both |
| `ghidra-snapshot devkit/re/data/ghidra_snapshot.json` | a live Ghidra | The **only** writer of the snapshot (AZ-111); refuses a dirty or stale serve and a program that isn't the USA XBE (exit 2) |

They call stock routes only (`/program`, `/functions...`, `/xrefs`,
`/memory/{addr}/comments/{kind}`, `/symbols`, `/structs...`). Stock shapes
the client handles: names are namespace-qualified (the client returns bare
names plus the parent namespace); list endpoints cap `limit` at 1000;
`/program` has no memory size; parameter storage reads `ECX:4` /
`Stack[0x4]:4`; an unknown route gets Javalin's 404 body.

The facts take the owner's project's names (D94: 0x88A80
`player_ground_attack_start`, 0x5E620 `settings_get_double`, 0x52F50
`game_start_setup`), so `ghidra-sync` plans them as kept.

**The snapshot.** `devkit/re/data/ghidra_snapshot.json` (schema 1:
functions, *named* labels and the structs in Ghidra's root category `/`;
names Ghidra made up itself are dropped) names the `devkit re xbe`
listings' addresses. Refresh it when it is stale (after a change on the
Ghidra side, such as an applied plan) from a fresh serve:
```bash
uv run --locked python -m devkit re ghidra-serve start --project "<the .gpr>" --port N
uv run --locked python -m devkit re ghidra-serve status --port N        # clean and current
uv run --locked python -m devkit re ghidra-snapshot devkit/re/data/ghidra_snapshot.json --port N
uv run --locked python -m devkit re ghidra-serve stop --port N
uv run --locked pytest -q tests/test_re_xbe.py
```
Read the diff (it should change only what the Ghidra-side change did) and
name the file in the commit body.

**Tests.** `tests/test_ghidra.py`: the client and the verbs against
`tests/mock_ghidra.py` (an in-process stand-in for the stock plugin's routes
and shapes), `ghidra-serve` with a fake `analyzeHeadless` serving the mock,
`ghidra-apply` around a fake headless run, and `bootstrap.py --with re` on
fake assets. The three tests marked `ghidra` run the GhidraScripts,
`ghidra-serve` and `ghidra-apply` headless in `.tools/ghidra` on zero-blob
projects: without it a run that selects them fails, naming `uv run
bootstrap.py --with re`; `-m "not ghidra"` deselects them (CI does). None
opens a live Ghidra. The stock bridge is upstream code with no tests here.

## Known hazards

- Any headless open of the live project risks the owner's work (§2).
- The stock bridge starts on 8192, not 8193: `instances_use(...)` (§3).
- A serve's copy and the owner's GUI can both answer on 8193 if a serve
  took it: read `programId` before any write (§2, §3).
- `scripts_run` executes arbitrary Java: `--allow-scripts` only while you
  need it (§1).
- `ghidra-apply --apply` writes the real project: only after reading its
  dry run, with Ghidra closed, `--project` naming it (§2).
- A Linux user cache under `~/.cache` is a hidden folder Ghidra refuses:
  `ghidra-serve start` says so (a known limit; macOS's and Windows' caches
  are fine).
