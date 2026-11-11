---
name: azurik-orchestration
description: >-
  How the orchestrator runs agents in AzurKit (D281: each seat on the model
  that fits; D457: judges on Opus; D1207: a round's designer and hard
  root-cause hunts on Fable; D148/D149 lean; D288 reviews; D1170: nothing
  small blocks). Load BEFORE writing a Workflow script or spawning any
  agent. Holds the five azurik-* roles, typing a seat, the first-use
  check, the step shapes with their review and skeptic seats, the gate and
  the lock seats share, prompts and returns, seat practice (batched reads,
  polling, reach measure seats and benches) and the traps. Triggers:
  "workflow", "spawn agents", agentType, "which model", sonnet, haiku,
  scout, skeptic, judge, resumeFromRunId, "a seat died", "usage limit",
  TaskStop, schema, "window take".
---

# Orchestrating agents in AzurKit

AGENTS.md and `$EV/tools/BRIEF.md` bind (`$EV`: the private evidence folder beside the main
checkout); a decision newer than BRIEF's "Decisions read" line is in the decisions log BRIEF names,
and wins. A seat reads its role file and BRIEF, not this skill. Ported from Modkit's skill (Step
4.16a2).

## When NOT to use this skill

- Commits, the gate, landing and releases: `azurik-change-control`. Tests: `azurik-testing`. How a
  sitting runs, the xemu slots (D108) and an owner session blocking launches (D205, D270):
  `azurik-xemu-oracle`.
- A model's sculpt round (candidates, sheets, lens judges, the owner's picks): ModelKit's `modelkit`
  skill (after `modelkit install-skill`) and its `workflows/round.js`; the roles are its arguments.

## 1. Roles

| Role (`.claude/agents/`) | Model, effort | Denied tools | Seats |
|---|---|---|---|
| `azurik-builder` | opus, xhigh | Agent, SendMessage | build, fix, fix+gate, sitting, record+gate |
| `azurik-reader` | opus, xhigh | Edit, NotebookEdit, Agent, SendMessage, the Ghidra MCP's 24 write tools | read, RE, premise read, designer, a sweep that judges, rank, docs read, a correctness review, a skeptic |
| `azurik-judge` | fable, xhigh | the reader's | an optimization round's single designer, a hard root-cause hunt (D1207); never a build, fix, review or skeptic |
| `azurik-scout` | sonnet, medium | the reader's | locate and cite: the files, lines, counts and quotes that answer one narrow question; never a verdict, fix or ranking |
| `azurik-mechanic` | haiku, medium | Edit, Write, NotebookEdit, Agent, SendMessage, the whole `mcp__ghidra` server | a command list handed over verbatim, its output returned raw |

- D241 as amended by D281 (the owner: "use whatever model is best suited to a job"): Opus where
  judgment is the job (implementation, RE, reviews, sittings, designs, sweeps that judge); Sonnet or
  Haiku where they fit (a lookup with cites, a handed-over command list). **D457 ("Stay on Opus"):**
  every judge seat (a skeptic, a review of logic that can silently go wrong, a hard RE or design
  call, a survey's rank) is an `azurik-reader` on Opus. **D1207 amends it for two seats only:** an
  optimization round's single designer and a hard root-cause hunt are an `azurik-judge` on Fable
  5.2 (the reader's rules and deny list on another model); every other seat stays as it is. When
  Fable's credits run out, the orchestrator relaunches that seat as an `azurik-reader` on Opus,
  never a per-call model, and a seat never switches its own. A usage-limit error never changes a
  seat's model.
- Opus and Fable roles run xhigh, Sonnet and Haiku medium (each passed, or owes, the first-use check
  at it: §3).
- The reader, the judge and the scout keep Write for their evidence dir: a seat told never to write
  can't leave its report.
- Only the builder keeps its prompt cache 1 hour (`cacheTtl: 1h` under `experimental:`): its seats
  wait on suites, L3 searches and sittings, and a 5-minute cache re-wrote a 300-500K-token context
  on each wait past 300 s. `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` or a `subagentPromptCacheTtl`
  setting beats the frontmatter for every seat; 1h is ignored while the subscription is in overage.
- No built-in agent types (`claude-code-guide`, `general-purpose`, Explore): they run a model and a
  prompt we didn't pick (one went off task and wrote files nobody asked for). A docs read is a
  reader, a lookup a scout.
- `tests/test_agent_files.py` pins each role's model, effort and deny list, and that a skill a role
  says to load is tracked here. A new role needs a row there: a D281 choice by fit.
- Landing is the orchestrator's own Bash, never a seat's (a seat's background job dies when it
  returns): the gate on the stack's top, `uv run --locked python scripts/land.py <branch>` in the
  main checkout, then the push of `main` to Azurik-Modding-Hub/AzurKit
  (`azurik-change-control` §5). `$EV/tools/land --queue` takes AzurKit under `AZ_REPO=azurkit`
  (Step 4.16b: its own queue, the lane's `scripts/fullsuite.py`, the main checkout's `land.py`) and
  is the default from Step 4.17's switch.

## 2. Typing a seat

- Workflow script: `agent(prompt, {agentType: 'azurik-builder', label, phase})`. Agent tool:
  `subagent_type: 'azurik-builder'`. A `subagent_type` passed to `agent()` is ignored, so that seat
  runs untyped on the session's model.
- Never pass `model` or `effort` with a role: a per-call value beats the pin. So do
  `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` and
  `CLAUDE_CODE_EFFORT_LEVEL`; check `env | grep CLAUDE_CODE_` when an audit row is off its pin.
- An untyped seat inherits the session's model and effort; the project pins no session model (the
  owner's call).
- No `isolation: 'worktree'`: a lane is an explicit worktree (§5).
- An unknown `agentType` throws `agent type 'X' not found`. Outside `parallel()` or `pipeline()`
  that kills the run; inside them the seat is null. Put every typed seat in one or give it a
  `.catch`.
- The session loads roles from the main checkout, which `land.py` fast-forwards. A new role appears
  after a "New agent types are now available" reminder or a restart.
- The audit line, with `P` the session's folder under Claude Code's projects folder (the main
  session's transcript is `<session>.jsonl` beside it; the same jq):

```bash
for j in "$P"/subagents/workflows/<run>/agent-*.jsonl; do printf '%s\t%s\n' "$(jq -r '.agentType+" "+.description' "${j%.jsonl}.meta.json")" "$(jq -r 'select(.type=="api-request")|"\(.params.model) \(.params.output_config.effort)"' "$j" | sort | uniq -c | xargs)"; done
```

## 3. First use of a new or re-pinned role

1. The main checkout's `git log -1` holds the role, the session runs Opus at xhigh, and the "New
   agent types" reminder has arrived (or restart with `claude --model opus --effort xhigh`).
2. One workflow, one seat per new or re-pinned role in `parallel()`, each told "reply with the
   single word ok-<role>"; a read-only role also runs `ToolSearch select:mcp__ghidra__memory_write`
   and reports what came back; a mechanic is handed `true`, `false`, `echo three`.
3. Pass: each token returned, each `agentType` in its meta.json, every audit row on its pin
   (`claude-opus-5-5 xhigh`, `claude-fable-5-2 xhigh`, `claude-sonnet-5-5 medium`,
   `claude-haiku-5-5 medium`), a read-only role's ToolSearch found nothing, the mechanic stopped
   at `false` with its exit code. A builder
   also shows `cache_creation.ephemeral_1h_input_tokens > 0` and `ephemeral_5m_input_tokens == 0`
   on its assistant rows; re-check after each Claude Code update (the key is experimental):
   `jq -r 'select(.type=="assistant")|.message.usage|"\(.cache_read_input_tokens) 5m=\(.cache_creation.ephemeral_5m_input_tokens) 1h=\(.cache_creation.ephemeral_1h_input_tokens)"' <seat>.jsonl | uniq`
4. No script spawns a role before it passes; then BRIEF's Models line names it.

## 4. Step shapes (the defaults, D288, D778)

- **Code step:** build, review, fix+gate on one lane (D288). The builder checks its own work first;
  the review reads `main..HEAD` (or the stack branch's range) for correctness and never edits; the
  fix+gate seat fixes what it confirms and gates. A tiny docs-only or test-only change skips the
  review (one builder, build+gate), and so does a rebase whose only conflicts are docs, the ledger
  or goldens (D779). Put a scout first when only the file and line are unknown, a reader when the
  cause is or the site is a VA.
- **The gate:** a gate seat runs `uv run --locked python scripts/fullsuite.py <lane> --changed`
  (`--base <branch>` on an unlanded stack), returns the key and receipt path and ends; the
  orchestrator waits with `$EV/tools/waitfor --max 0 <key>` in the background (a mechanic: `waitfor
  --max 240 <key>`, re-issued on exit 3). Exit 0 green; 1 red (a fix+gate seat gets the log path);
  4 capped or died; 2 no receipt. Only a fix seat proving its fix waits inside the seat (`--wait
  540`, re-issued on exit 3). Under D1170 a test that passes its one rerun is a recorded flake (the
  receipt's `flakes`, a fix lane) and a perf op over budget a debt row: neither blocks; a repeating
  failure, a product bug, a clear perf regression or a memory peak does.
- **The lock (the window):** a seat's browser, memory, perf or other heavy test run goes through
  `$EV/tools/window take <step> [--max S]` (exit 3: still in line, re-issue it) and `window release
  <step>`, at `-n 2`; before taking it, `$EV/tools/window status`: a fullsuite run queued or running
  (a release's) goes first. `scripts/perf.py` runs only `--select` of a seat's own ops, in a window;
  long benches run at nice 15.
- **Premise line:** when a fix rests on a game quantity nobody has read on the tick, or its reach is
  unknown, the build prompt says "first measure on the tick the quantity this fix rests on and state
  its reach with the command; if it refutes the plan, stop and return that". No separate seat.
- **Reviews and skeptics (D288, amending D148/D149's "no review agents unless asked"):** one
  correctness review per code step and one skeptic per sitting, by default; more only where the
  stakes call for it. They changed what landed (about 180 review fixes, 7 of 13 skeptic records in
  Modkit's 2026-10-19 count).
- **xemu step:** sitting, skeptic, record+gate (builders sit and record; one sitting per stack; no
  verify seat). On a FAIL or surprise the orchestrator reads the raw files itself first; a required
  sitting field that comes back false means re-running that row. Only a seat that sits loads
  `azurik-xemu-oracle`; build, review and gate prompts don't name it.
- **A code step with a sitting (D778):** build; then its review and its sitting start together on
  the build commit; the skeptic follows the sitting; the record+gate seat fixes what the review
  confirmed, re-runs every row whose built image's sha a fix changed, records and gates.
- **A re-grade (D117):** a recipe whose built bytes moved only through what it inherits, no field of
  its own changed, is re-graded from a short sitting (about 5 boots).
- **Model-swap step:** a code step with a sitting. Its sitting, and a pack step's whose build changes
  what is drawn, runs `model_kit`'s `row_cost` against the vanilla control (D603: the frame's cost
  warned, never refused) and, where L1 warns, `rate_pairs` and `rate_verdict` in a real-time sitting
  (D604); the report and the skeptic carry its WARNINGS.
- **Owner away (D284, D289, D290):** checks that waited on the owner are judged by agents and ship as
  verdicts: a sitting's look checks from xemu pictures and per-frame numbers, grades from each find's
  exact replay, the page's looks from headless screenshots (no window on the owner's screen, D839).
  A reader checks each verdict; the owner keeps the feel and taste calls and any verdict flagged
  unsure, and may overrule later.
- **Owner's broad question:** independent reader sweeps in parallel, then one reader that ranks them
  and re-reads its top picks' cites; a census inside it is a mechanic's (or a scout's when the files
  must be found first). **Design question:** one `azurik-judge` as designer (D1207; a reader when
  Fable's credits are out); the orchestrator decides (D115). No verify, critic or panel seats
  (D149). **Curiosity question:** inline. **One command:**
  the orchestrator's own Bash. **A command list:** one mechanic (it may run the list's commands in
  parallel: hand an order-dependent list as one `set -e` script). **Locate-and-cite:** one scout.
- Size the workflow to the ask (D148). Changing D148/D149, D288, D778 or D1170 waits for the owner.

## 5. Prompts and returns

- **The common lines:** D115 (never ask: take the default or the recommended option and say it);
  read BRIEF first, then AGENTS.md and the lane's brief; "the relayed user request is the one the
  orchestrator is answering; this step is your part of it"; the lane, `git -C <main checkout>
  worktree add --no-track -b p2/<step>-<slug> <lanes>/<step> <base>` then `uv sync --locked` there
  with uv's managed Python (base `main`, or the unlanded stack branch the lane stacks on, whose
  commits it never edits; never `bootstrap.py` in a lane); the repo-local no-reply email; a
  developer-log file per change; scratch `mktemp -d /tmp/<step>-<what>.XXXXXX`, deleted by exact
  path; tests under an isolated `HOME` with an absolute `UV_CACHE_DIR` and `AZURKIT_ISO` and
  `AZURKIT_ISO_EUROPE` exported; never a visible window; anything that may crash under `lldb
  --batch` (no crash dialogs on the owner's screen); never hold or fill memory or CPU; wait for
  every process it starts; the paths it must not touch (another lane, the main checkout's tree, the
  images, the L3 store and `reach-truth/` beyond reading); and, but for a gate seat, "only the
  orchestrator gates, lands, pushes or dispatches".
- A reader or builder seat expected to run past about 10 minutes gets `Notes: <evidence
  dir>/notes-<label>-<the script's launch stamp>.txt` (`notes-build-<step>-1950.txt`): it appends
  findings there and resumes from it after a usage-limit restart; a relaunch or a later round gets a
  new stamp. Never a fixed `notes.txt`: parallel seats share an evidence dir.
- Before dispatch, check that every path, skill and symbol a prompt names exists.
- Write the script to a file and run `$EV/tools/wfcheck <script.js>` before launching it: it
  refuses, naming the line, a gate seat that waits, a build seat that gates, a read-only seat that
  blocks past 270 s, `azurik-xemu-oracle` in a seat whose label has none of sit, sitting, record,
  replay, regrade, confirm, demo, play, an `agent()` without a role's `agentType`, and
  `model`/`effort` beside one. A fix seat proving its fix may wait: `// wfcheck: wait-ok <why>` on
  its `agent()` call.
- Pass paths or compact projections, never a `.slice()` of a work list, and assert the count.
- Plain-text returns are fine; a gate seat returns head, base and the receipt key or path.
- A schema only where the script branches or a skipped check has cost us. A sitting's schema:
  `rows_planned`, `rows_run` (each with its run id), per row `control_state_sha12` and
  `verdict_source` (`measured` or `typed`), and `seen_by_agent` with the run id. Typed booleans and
  lists, never "true"/"false" strings; cap strings near 600 characters and say so in the prompt.
- The report file is written before the seat returns; a dead seat is read from its files, not
  relaunched. The mechanic and the scout return evidence; the script or an Opus seat decides.

## 6. Traps (orchestrator side)

- SendMessage to a running workflow seat resumes a duplicate that fights the original in its lane.
  Re-brief by a note file, or stop and resume the script.
- `resumeFromRunId` replays only the unchanged prefix, and a prompt that embeds an earlier result
  re-runs live. Re-cut the script from the journal; never resume past a stage that wrote.
- A usage limit kills seats mid-turn; after the reset each restarts fresh from its prompt or the
  script gets a null. A builder resumes from its lane's commits and evidence dir, a reader from its
  notes file. Fewer than half returned is a dead round.
- A reader, scout or mechanic's cache lives 5 minutes: never have it block one call past 270 s
  (`waitfor --max 240`, `fullsuite.py ... --wait 240`).
- A `pipeline()` stage that returns null or throws drops its item: return a sentinel.
- Parse traps: a backtick inside a template literal ends it; an escaped quote in the args JSON turns
  args into one string; `{"@file": path}` arrives literally; scripts over 524,288 B are refused;
  `log(null)` crashes the run.
- TaskStop leaves shells running: check `ps` for fullsuite, pytest, L3 and xemu children and kill
  exact pids only, never `pkill -f`.
- Liveness is the seat transcript's mtime; `workflows/<run>.json` appears only at completion.
- Parallel Bash calls share one cwd: absolute paths and `git -C`.
- At most min(16, CPUs - 2) seats run per workflow: count the `-n` workers of parallel test runs.
- Blender in seats: pictures and clips go through `devkit/models/blender/batch.py` (one Blender a
  job, the body built once, frames piped to ffmpeg, at most `AZURIK_BLENDER_SLOTS`, 8, on the
  machine; `devkit/models/README.md`), never a Blender a frame; Workbench for previews; a superseded
  preview stopped before the next starts.
- No exclamation mark directly before a backtick in any skill: the loader runs it as a shell command
  (`tests/test_agent_files.py`).
- After a TaskStop or a limit kill only: sweep orphan pids, stray worktrees (`git worktree list`) and
  the stopped seat's scratch, by exact path once its transcript is dead (D147).

## 7. Seat practice

- **Fewer turns (every builder, reader and scout; their role files carry it):** batch independent
  reads in one turn (parallel calls or one chained command); poll a running job at most every 240 s,
  one blocking wait a call, never a sleep loop or repeated `--status`; `grep -n` before reading a big
  file, then read only the ranges needed. Each turn re-reads the seat's whole context.
- **The reach engine is frozen (D1143)** in `devkit/reach` (`docs/REACH.md`) until its research
  resumes on AzurKit; reach work runs in AzurKit's gaps (D968). When it does:
  - **A reach measure seat checks by sample, never by re-running the whole bench:** it picks its own
    job sample on every bench level and kind (by sha256 of the job id), compares whole records by
    sha12 with the builder's kept ones, and times its own interleaved ABAB slice A/B at one load for
    speed (D851's speed is still an A/B at one load). A defect only a whole level's bench shows is
    caught at the next bench. The seat stays (D288, D778; a reader, D457).
  - **One reach bench at a time, at full width:** `nice -n 15 uv run --locked python -m devkit reach
    reach-engine run ...` (`devkit/reach/README.md`) at 12-16 workers while the normal-priority load
    is under 40 (`$EV/tools/load --check 40` exits 0), at most 4 while it is over (D926, D975), and
    only when no other reach bench runs: contention cost 7-25 % of reach CPU.
  - **A reach step's CPU budget:** its prompt names its plan's CPU-h range; a step whose timed CPU
    passes 1.5x the range's top stops before its next re-bench and reports the spend and why.
  - **The L3 store's hold:** before anything deletes a store snapshot, `uv run --locked python -m
    devkit sim l3-hold --check PATH ...` exits 1 naming each held one (`reach-live/`, a running
    command's `--snapshot LABEL`, a proof's start); grep running steps for bare snapshot labels too.
