---
name: azurik-change-control
description: >-
  How a change lands in AzurKit (D149's lean process, the changed-area gate,
  D1170: nothing small blocks) and what evidence each class of change owes.
  Load BEFORE committing, gating or landing a stack, cutting a release,
  deleting or moving tests, or touching a golden, the facts, a shim object,
  an allow-list or another protected path. Triggers: "commit", "land",
  "push to main", "fullsuite", "receipt", "which tests do I run", "can I
  skip this test", skipif, record_goldens, gen_facts, "ledger take",
  "before/after bytes", "release", "tag", Co-Authored-By, git add -A,
  git stash, force-push, --no-verify, "report".
---

# azurik-change-control: how changes land

AGENTS.md is the binding rule list and wins where this skill is shorter; `$EV/tools/BRIEF.md` binds
with it (`$EV`: the private evidence folder beside the main checkout). Run every command from the
checkout's root with `uv run --locked`. Ported from Modkit's skill (Step 4.16a2).

## When NOT to use this skill

- Writing a pack or shim: AGENTS.md's Packs (its Patching and shims) and `docs/SHIMS.md`. Running or
  writing tests: `azurik-testing`. uv, the images, the environment: `azurik-dev-environment`. In-game
  checks: `azurik-xemu-oracle`. The Ghidra snapshot: `azurik-ghidra-mcp`. Spawning seats:
  `azurik-orchestration`.

## 1. Owner rules (binding)

D149 (one commit per fix with its test, the changed-area gate on the stack's top, minimal
bookkeeping, land by fast-forward; speed beats verification depth, D148); D288 (a correctness review
after every code step, a skeptic after every sitting; none for a tiny docs- or test-only change, nor
for a rebase whose only conflicts are docs, the ledger or goldens, D779; beside the sitting on the
build commit, D778); D10/D37/D150 (lean tests); "failures never become skips" (an allow-list entry is
the owner's); D961 (game bytes may be committed, never the ISO, §9); D1170 (nothing small blocks,
§4); D115 (no questions, unless the owner opens an ask window; "work unattended and dont ask
questions" closes it).

## 2. Change classes: gates and evidence

Classify first; classes stack (a shim fix that moves bytes is 3 + 5).

| # | Class | Load-bearing gates while iterating | Evidence owed |
|---|---|---|---|
| 1 | Docs, skills, roles | re-run every command and path the diff adds; `pytest -q tests/test_agent_files.py tests/test_contracts.py` (`tests/test_wheel.py` for README) | the doc it owes (AGENTS.md's guide rule; `devkit/<area>/README.md` for a dev tool); anything unbuilt called planned |
| 2 | Test only | the touched tests | a deletion names what still pins the behavior |
| 3 | Output bytes (a pack, a character, the writer, the randomizer's plan) | `scripts/record_goldens.py --check <golden>`; `python -m devkit re test-for-va <pack or VA> --run` | the goldens re-recorded and named in the body (§6); a gameplay change seen once in xemu, one sitting per stack |
| 4 | An address, a game function, an ABI | `pytest -q tests/test_packs.py tests/test_shims.py`; `scripts/gen_facts.py --check` | the facts edited by hand, then gen_facts; the ABI confirmed at 2 or more call sites (stdcall callee `RET N`, cdecl callers `ADD ESP,N`) cited as VA + N; Europe's address or a named absence in `facts.europe.json` |
| 5 | Shim (`tools/mods/shims/*.c`, `tools/characters/player_model/*.c`, shimkit) | `python -m shimkit`, then the SSE2 scan below; `tests/test_shims.py` | Pentium III code only; the callee's `ret N` and return registers kept; G2 recorded; gameplay seen in xemu |
| 6 | What a player sees (`src/`, `web/`) | the area's tests; browser tests in a window (§4) | the guide's line (`docs/GUIDE.md`) on both hosts; the perf block (§4) |
| 7 | Environment, deps, CI (`pyproject.toml`, `uv.lock`, `bootstrap.py`, `.github/`, `.mcp.json`) | the whole suite | every change outside the repo listed with its revert |
| 8 | Protected (§6) | its update command; read the whole diff | the body names each protected file and why |

SSE2 scan of a shim object (any output fails it; grep's exit 1 is a pass):
`objdump -d <object>.o | grep -E 'sd[[:space:]]|cvt[a-z]*sd'`.

## 3. Output-byte evidence (class 3)

The goldens are the evidence. Before you edit, `uv run --locked python scripts/record_goldens.py
--check [GOLDEN ...]` passes on the base; after, it names each case whose bytes moved. A change meant
to move bytes re-records exactly the goldens it should (`record_goldens.py GOLDEN ...`) and its body
names each with the cases and why; a moved case of another pack is a regression, never re-recorded.
A byte-neutral change is proven by `--check` staying green. For one build by hand, `azurkit build
... --out <mktemp dir>` twice and compare sha256 per file; `python -m devkit builds verify-patches`
reads every pack site back. The same seed and settings plan the same bytes under any
`PYTHONHASHSEED` (`azurik-testing` §6). Commit bodies carry hashes, VA + length lists and counts,
never game bytes.

## 4. The gate and green

- **While you work:** targeted tests (`azurik-testing` §2).
- **The gate (the orchestrator's, or a gate seat's when asked):** `uv run --locked python
  scripts/fullsuite.py <lane> --changed [--base <branch>]`: the lint files, then under a lock the test
  files the change reaches with the smoke set (Chromium only), its flake stage and its perf stage
  (AGENTS.md's The gate); it prints a key and a receipt path, `--wait 540` waits (exit 3: issue it
  again). Without `--changed`: the whole suite in every browser.
- **Green:** no failure, no skip (the allow-list is empty), `vanilla: N run` and `europe: M run` with
  N, M at least 1, the flake stage passed and, for `src/` or `web/`, the perf block passed.
- **Nothing small blocks (D1170, Step 4.22):** a test that passes its one rerun is a recorded flake
  (the receipt's `flakes`, a fix lane) and a perf op over budget a debt row; neither blocks. A
  repeating failure, a product bug, a clear perf regression against main's last passing full run or
  a memory peak does (`azurik-testing` §1, §9).
- **The lock:** a seat's browser, perf or other heavy run goes through `$EV/tools/window take
  <step>` / `release <step>`, at `-n 2` (`azurik-testing` §9).
- **Red:** fix it, or show why the test was wrong. A test that pinned the bug you fix is replaced by
  your test; say so. A hang that takes the network down (AZ-312): stop, don't retry; report it.

## 5. Landing, CI and releases

- **Landing (the orchestrator's):** `uv run --locked python scripts/land.py <branch>` in the main
  checkout fast-forwards `main` once a passing receipt covers the branch's head (AGENTS.md's
  Landing), removes the lane and deletes the branch; a stack on an unlanded branch lands after it.
  Then the orchestrator pushes `main` to Azurik-Modding-Hub/AzurKit; lanes never push. The landing
  queue (`$EV/tools/land --queue`) takes AzurKit under `AZ_REPO=azurkit` (Step 4.16b).
- **CI** (AGENTS.md's CI): `tests.yml` (the pure tier on four runners on every push and pull
  request, the vanilla tiers as shards on a push here), `checks.yml` (the leak guard, `nativekit
  --check`), `apps.yml` (the frozen apps on `main`), `release.yml` (a `v*` tag, a publishing, a
  dispatch's dry run). Free runners only, at most two lane branches pushed at once (D1127); a job
  that never got a runner may be rerun, one that failed is fixed at its cause (D1129). No scratch
  dispatches or soaks.
- **A release is a tag on a commit that is on `main` (D1170)**; landing never waits for one. One
  commit (`feat: AzurKit X.Y.Z ...`) sets the version in `pyproject.toml`, `src/azurkit/__init__.py`
  and `uv.lock` (`uv lock`; protected, named) and joins the `docs/devlog/` files into a `## [X.Y.Z
  (date)]` section of `docs/DEVLOG.md`, deleting them; it lands like any stack; once CI on it is
  green (D1149, D1170) the orchestrator pushes the tag `vX.Y.Z` (no workflow tags); `release.yml`
  checks the tag names pyproject's version on `main` and drafts the release (apps, wheel, sdist,
  `SHA256SUMS`, attestations), and its Publish uploads to PyPI and deploys the site (D1145: as soon
  as green). The checklist is the private release runbook; the security read is a quick look
  (D1162). Fix forward after a Publish; never move a tag.

## 6. Protected paths: update commands only

The body names each protected file changed and why. A red truth means the code or the address is
suspect first; never widen an allow-list or re-record a golden to go green.

| What | How it changes |
|---|---|
| `tests/goldens/` (G1-G4, sites, resources, close, probes, matches, rando plans, tracker) | only `scripts/record_goldens.py [GOLDEN ...]`, from AzurKit's builds on the images; `tests/goldens/cases.json` is edited by hand; `python -m devkit rando restack` re-derives and re-records the randomizer's |
| The facts, `src/azurkit/core/facts.<release>.json` | a site, function, swap site or Europe address by hand, then `scripts/gen_facts.py` fills the XBE half |
| The shim objects (`*.o` beside their sources), `shimkit/` | only `python -m shimkit` |
| The native libraries `src/azurkit/core/_native/`, `web/md5.wasm`, `nativekit/` | only `python -m nativekit` |
| `tests/sdk_api.txt` | only `scripts/sdk_api.py` |
| `tests/perf_ceilings.toml` | only `scripts/perf.py --update-ceilings`, lowering a ceiling you earned, in your own commit |
| `web/tables.json`, `tests/ci_durations.json`, the shipped answers | `scripts/web_tables.py`, `scripts/ci_shards.py`, `scripts/record_shipped.py` |
| `devkit/re/data/ghidra_snapshot.json` | only `python -m devkit re ghidra-snapshot`, from a fresh serve (`azurik-ghidra-mcp`) |
| `devkit/sim/data/sim_blind_spots.toml` | by hand, never to get a test green |
| The release manifests `src/azurkit/core/manifests/` | never: each is its release's files (`tests/test_gate.py`) |
| `tests/skip_allowlist.toml` | empty; an entry is the owner's decision |
| Named in the body when changed | `tests/conftest.py`, `tests/_*.py` (the leak guard among them), `PROLOGUE_FIRST_BYTES`, `pyproject.toml`, `uv.lock`, `bootstrap.py`, `CLAUDE.md`, `.claude/` |
| Generated; never edit | `.venv/`, `.tools/`, `__pycache__/`, `dist/`, `build/`, `out/` |

## 7. The loop (D149)

1. **The step** the orchestrator gives you; a missing decision takes its default, else your
   recommendation (D115), named in the report.
2. **Lane:** `git -C <main checkout> worktree add --no-track -b p2/<step>-<slug> <lanes>/<step>
   <base>` (`main`, or the stack branch your prompt names), then `uv sync --locked` in it; never
   `bootstrap.py` there.
3. **Classify** (§2), implement the minimum, run the class's gates. Check your own work first.
4. **Commit** (§8), then the gate (§4) on the stack's top, then the orchestrator lands (§5).
5. **Report** in a few lines: what changed, hashes, the receipt, what is broken or left, defaults
   taken, environment changes with reverts. Label only claims you are unsure of.

## 8. Commits and bookkeeping

- **One commit per fix, with its one behavior-named test.** No `pin:`/`fix:` split, no red-on-parent
  proof, no mutation evidence. Feature, deletion, docs or perf work: one commit where possible.
- **Message:** a type (`fix:`, `feat:`, `docs:`, `refactor:`, `tests:`, `perf:`), the behavior in
  plain words, the step `(Step 4.16a2)`; a body of a few lines (the AZ ids, hashes for byte changes,
  `RET N` cites for ABI changes, each protected file and why). The repo-local no-reply email (D1025);
  no attribution trailer (D101).
- **Notes:** each change's developer-log entry is its own file,
  `docs/devlog/<added|changed|removed|fixed>/<step>-<slug>.md`, one bullet (never a line in
  `docs/DEVLOG.md`); a change a player notices also updates its line in `docs/GUIDE.md`.
- **Ids:** `$EV/tools/ledger take AZ "slug: one line"` (D, Q likewise); never an id or pointer by
  hand. The issue ledger is private (D952): a fix names its AZ id in its body and its devlog entry,
  and the orchestrator ticks the ledger.
- **Staging:** explicit paths only, never `git add -A` or `.`; read `git diff --cached --stat` (an
  unexpected binary or large file: stop and check it against §9). Never `git stash` (shared by every
  worktree), force-push, `--no-verify` or a git config change; add hooks of your own only, never
  touch the owner's. `main` moves by fast-forward only.

## 9. Never commit the ISO (D961)

- **Fine:** game files and bytes (an XBE or XBR file, a clip, a texture, a save, a snippet, a byte
  literal, a disassembly listing) and our own clips; `.gitignore` keeps them out against bloat, `git
  add -f` adds one on purpose (D1136: assets may ship, never the whole image). Never print game bytes
  in logs, commits or chat: lengths and `sha256[:12]`.
- **Never:** the ISO/XISO image, whole or in parts, an EEPROM dump, an xemu HDD (qcow2) image, a guest
  RAM snapshot (`AZL3SNAP`), the deploy key or any private key.
- **The leak guard** (`tests/_leak_guard.py`) refuses exactly those, in the suite, on every push (the
  `pre-push` hook `uv run bootstrap.py` writes) and in CI's `checks.yml`; `uv run --locked python -I
  tests/_leak_guard.py` scans the checkout (exit 1 names each file). Never weaken it.
- **Never** make `Azurik-Modding-Hub/AzurKit-gamedata` public, fork it or mirror it.

## 10. Closeout

`git status --short` shows only intended changes; your `/tmp` scratch is deleted by exact path
(D147) and your processes have ended; environment changes are listed with their reverts; the report
is written. Memory holds owner preferences and pointers; durable knowledge goes in the repo.
