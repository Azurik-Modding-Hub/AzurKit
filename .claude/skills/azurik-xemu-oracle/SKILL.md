---
name: azurik-xemu-oracle
description: >-
  The sitting card for Azurik's xemu oracle (the owner's xemu fork, dev-only,
  never in pytest). Load only in a seat that sits or re-runs sitting rows (a
  sitting, a record that re-runs rows, an owner demo, a calibration or
  skip-confirming sitting); build, review and gate seats don't, even when
  their step mentions xemu. Triggers: "check it in xemu", "verify in-game",
  "boot-test the ISO", boot-build, a sitting, model_kit rows, measure jump /
  walk speed / flaps for real, "the bytes landed but nothing changed in
  game", confirming a randomizer skip (D114), an owner demo.
---

# Azurik xemu oracle: dev-only ground truth

A sandboxed copy of the owner's macOS xemu fork, attached over the QEMU
gdbstub and QMP and driven through the fork's input FIFO. It shows what the
game *actually does* with a build (launch speed, gravity per tick, walk
speed, which constant a patched site really reads); byte tests can't.
`$EV` is the private evidence folder beside the main checkout (AGENTS.md,
"Where knowledge lives"); each sitting's results are in
its sitting's `REPORT.txt` in `$EV` (`xemu-oracle-<date>-<name>/`).

**This card and its reference files (Step 2.216).** This file is what
every sitting needs: the rules, the slots, the harness's sandbox, the
sitting kit, the code-identity check, the hazards' summary and the
checks. The rest of the skill sits beside it in `reference/`, moved
there word for word with its § numbers unchanged, so a "§6" or "hazard
13" anywhere still names the same text. Read a reference file only when
the task needs that section, and grep it first (`grep -n 'checkpoint'
reference/driving.md`) rather than reading it whole.

| § | What | File |
|---|---|---|
| 0, 1, 2 (steps 1-4, deterministic mode) | what exists, where things live (the fork build, the D98 fixtures, the owner's xemu: never a source), the sandbox by hand | `reference/sandbox.md` |
| 3 (not the sitting parts below) | QMP and HMP, checkpoints, screenshots and a picture's age, frames, per-frame traces, GPU counters and the frame's cost, RAM dumps and shared memory, the gdbstub and watchpoints, the input FIFO, analog lines, the menu and boot walk | `reference/driving.md` |
| 4.2-4.7 | the tick-locked trace and the entity fields, RAM and code pokes, the 5-minute release checklist, confirming a skip (D114), the route pilot, chains (park, unpark, replays) | `reference/recipes.md` |
| 4.8 | the game's cheat codes, debug menu and level warp (`Sitting.cheat`, `Sitting.warp`) | `reference/cheats-warps.md` |
| 4.9 | owner demos: the visible sandbox, re-plugging the pad, the recorder, the warm shader cache | `reference/demos.md` |
| 5 (entries 1-19, still open) | each hazard's history and handling | `reference/hazards.md` |
| 6 | the 32 oracle save states, agent-made states (D102), `boot-build` (the modded-build path), warm and shared states, frame boots | `reference/save-states.md` |
| history | the version-adoption sittings' measurements (x32 to x94) and this skill's description before Step 2.216 | `docs/archive/xemu-oracle-history.md` (not the skill's) |

`$FX` is the fixtures folder (the one `AZURIK_XEMU_FIXTURES` names, else
the user data folder's `xemu-fixtures` link; D98's folder, outside every
checkout), `$XEMU_FORK` the owner's xemu fork checkout (its source; never
run its `dist/` build in place) and `$W` a sandbox's own
`mktemp -d` folder. Every sandbox runs the fork build
`$FX/xemu-v0.16.4-3-g95e7ffc7ec.app` (`FORK_APP`; `--app kept` the
v0.13.3-37 build that made the D98 states; §1). A build is tested by
`boot-build` from a `vanilla-ig-*` state (§6), never by a `loadvm` of a
vanilla state with the build in the tray (hazards 2 and 8).

**Rules.**
- Dev tool only (devkit, never a player's `azurkit` verb): pytest runs only
  the offline selftests, which launch no xemu (D11).
- Only for changes to gameplay bytes: **one sitting per stack**, before it
  lands, with no verify agent (D149). Other uses: simulator calibration,
  confirming a randomizer skip (§4.5), the release checklist (§4.4).
- **Sandboxed clones only** (§2), from D98's fixtures; never the owner's
  own xemu files, never the owner's app bundle in place. Sound off
  (`volume_limit = 0.0`). Sandboxes start only when a slot admits them (D108).
- Agent-made save states stay off D98's oracle drive (D102, §6).
- RAM dumps and states hold console key material: keep them in `$W`,
  never in `$EV`, a repo or the gamedata repo.
- The fork and its dist build change often: read their version at run
  time (§7), record it in the sitting's REPORT, never edit the fork.
- **Standing rule (Step X.96, the fork session's, D894): a finding that
  points at xemu goes to the fork session at once,** with the state (the
  build and its binary's sha12, the tag or checkpoint and its disc), the
  call sequence and the counts; never work around it silently (2.172f
  worked around AZ-822's missed pages without telling the fork). Any
  nonzero `pages-missed` on a build with AZ-822's fix drafts its own
  request (`PAGES-MISSED-*.txt`, §3); any other finding (a crash, a hang
  probe, a value that differs from the fork's goldens) gets a draft by
  hand in `xemu-fork-requests-<date>/` in `$EV`. Either way the step's report
  names the draft first, for the orchestrator to relay.

## When NOT to use this skill

- **Writing a test.** Nothing in `tests/` may launch xemu; function-level
  behavior belongs to the Unicorn tier, `devkit/sim/l2.py` (jump,
  flaps, walk and air control).
- **Building/perf-testing xemu**: fork skills `xemu-build-and-env`,
  `xemu-run-and-operate`, `xemu-testing`.
- **`loadvm` "Unknown section …usb-hub" or CLI `-loadvm` failing**: fork
  skill `xemu-debugging-playbook` (load over QMP/monitor after boot).
- **Movement VAs, offsets, formulas**: `azurik-game-reference`.
- **Saves out of a qcow2**: `azurkit save inspect <HDD>` (read-only; `docs/GUIDE.md`).
- **Which seat runs a sitting and what it returns**: `azurik-orchestration`.

## 2. The sandbox: the harness, the slots, proof and teardown

Section 2's reasons, its manual steps 1-4 and the deterministic mode are
in `reference/sandbox.md`.

**`oracle up` and `jump` (a sandbox on the fork build,
null and deterministic; `--headless 1` offscreen, `--app kept` the build
that made the D98 states, `--window` a visible one) run steps 1–6 for
you** (`down` is step 6).
They also baseline the app's `xemu` binary, the disc and every pref-dir
entry; clone the HDD, EEPROM, boot ROM and BIOS the fixtures' toml names
(refusing one outside the fixtures folder) and point all five
`[sys.files]` paths, `games_dir` and `screenshot_dir` at `$W`; boot their
own disc (`jump --iso`; a sandbox's default is `$FX/vanilla.iso`), never
the toml's `dvd_path`; run deterministic (`XEMU_HEADLESS=null` and `-S -icount shift=2,align=off,sleep=off`; offscreen `XEMU_HEADLESS=1` with `--headless 1`, a 640x480 window with `--window`); bind the 25 port-2 pad
inputs to SDL scancodes 232–256 (no real key there, so only the FIFO
drives the pad) and drop the F5–F8 snapshot shortcuts; take a slot and a
free gdb port; launch under `nice -n 10` (an owner demo at normal priority;
beside one, at background priority: hazard 16); fail on any absolute path in
the launch line outside `$W`; wait up to 180 s for the launch log line
and again for the gdbstub; and quit over QMP, killing only their own
process if it lingers. A changed source file is an incident (`down` keeps
`$W` and exits 1); a changed pref-dir listing only warns (the owner may
have run xemu). The manual steps (`reference/sandbox.md`) are the reference for ad-hoc
sessions.

**Parallel sandboxes (D108, amended by D174 and D263).** No fixed cap.
Two sandboxes may always run, whatever the load (D174, 2026-10-13; D108
had one); each one after them (`up`, `jump`, a `relaunch` whose slot was
reclaimed) starts only while no full test suite runs (nothing holds
`/tmp/az-fullsuite.lock`), at least 4 CPU cores are free and at least
8 GiB of RAM is free. Free cores (D263, 2026-10-17, on the fork's
advice: a load-average gate of 16 left most of the fork's measured
throughput unused, 196 f/s with 1 instance, 1358 with 8, 2100 with 16)
are the CPU count times the idle share over 1 s (mach `host_statistics`,
`HOST_CPU_LOAD_INFO`; niced time counts as busy), not the load average:
one core for the new xemu (each uses about one) and three to spare
(`MIN_FREE_CORES`). Where that call fails (not macOS) D174's old load
test decides and the verdict says so. A running sandbox is an xemu whose app is in
a `/tmp/azx-*` folder, or a registered slot whose process still runs.
Waiting sittings start first come, first served (Step X.8): each takes a
ticket in `/tmp/azx-xemu-slots/queue/` and only the earliest live one
may start when the rule allows. Every new
sandbox also waits while another is launching
(`/tmp/azx-xemu-slots/launch.lock`) and while an xemu runs that isn't a
sandbox (`pgrep -x xemu`: the owner's own copy). An xemu whose command
holds `-name xemu-fork-auto` is the fork's automation (D248; its
launchers take one of `XEMU_FORK_SLOTS` (default 4) slots and a lease in
`/tmp/xemu-leases/`, but a hand-written launch and an orphan whose
launcher was killed hold no slot, so they aren't capped): it counts
through the cores it uses, never as the owner's, and `slots` lists it.
It checks every 5 s
for `--wait` seconds (default 240; scripts pass `Sandbox(..., wait_s=)`
or `Sandbox.attach(W, wait_s=)`), then stops with `STOP: <why>` having
started nothing. No running sandbox is ever stopped for load. Each
records its W, pid, gdb port and QMP socket (`$W/qmp.sock`) in
`/tmp/azx-xemu-slots/<W name>.json` until `down`; `slots` lists them, the
queue, `free_cores` (measured), `free_ram_gib` and the current verdict. A slot's lease (its file's mtime) is
renewed by its launch, every attach and every check that sees its xemu
run; once its xemu stops without `down` the slot is kept 10 minutes
after the last renewal (and still counts), then reclaimed. A relaunch
(`relaunch`, `boot-build`'s) on a W that still holds its slot keeps it:
no ticket, no admission test, only the launch lock and a foreign xemu. While a
ticket waits for free cores (its `cores`; not for RAM, a suite or a hold:
AZ-620), the batch jobs holding a `BatchToken` (`rando derive -j`,
`rando_soak.py`, `rando_impact.py`; `slots` lists them) keep one task in
flight, so cores come free for it. A kit sitting (`sitting`)
holding its sandbox past its lease (45 min) while a ticket waits downs it
between cases and queues again at the back (the voluntary yield).
`attach <W>` drives the W `up` recorded, whatever
path form you type. With a full suite running, a third sandbox often
waits.

**Step 5. Prove the sandbox first.**
`grep -E 'config path|base path|Created QEMU launch' "$W/run.log"` must show
`$W/` for the config, the base path (`…/xemu.app/Contents/Resources/`,
or `$W/xemu-data/` where the harness set `XEMU_BASE_PATH`),
`bootrom=` (boot ROM), `smbus-storage,file=` (EEPROM), `-bios`,
`media=disk` and `media=cdrom`. Any real path means: quit at once. The null renderer
never prints a base path (only the renderer's caches ask for it; sitting
x14), so a null-mode log needs none, but any it shows must be `$W`'s.

**Step 6. Tear down.** QMP `quit` (§3), then kill only *your* PID, only if
it's still your binary (never `pkill`/`killall xemu`: the owner may have a
session open): `P=$(cat "$W/xemu.pid"); ps -p "$P" -o command= | grep -q "$W/xemu.app" && kill "$P"`.
Re-run only the `ORIG=`/`for` lines of steps 1-2 (`reference/sandbox.md`; same `FX`, `ISO`) into
`baseline_after.txt`; `diff "$W"/baseline_{before,after}.txt`. **Any
difference is an incident: report it.** Then `rm -rf "$W"` (D147) unless
you keep it to read.

## 3. Driving it: a sitting

The rest of section 3 (QMP, HMP, checkpoints, pictures, frames, RAM, the
gdbstub, input) is in `reference/driving.md`.

**A sitting through the kit (Step X.9, the default).** `devkit/xemu/sitting.py`
(`devkit/xemu/README.md`): `with xs.Sitting(name, step=...) as s:` queues for a
slot, keeps positions in a private folder, writes public rows and scrubbed
captures to `xemu-oracle-<date>-<name>/` in `$EV` and always tears down (`down`,
the generated `REPORT.txt` header, the private folder deleted). Helpers:
`boot`, `loadvm`, `record_spot`/`place` (R6; hazard 14), `hop` (R7),
`kit`/`frags`/`keys` (R2), `set_hp`/`hold_hp`, `hold_targets` (a target's HP
held only while its vtable and +0x178 are the run's start's: AZ-530, the
unchecked hold wrote into freed critters and stopped the guest), `capture`,
`clear_dialog`, `l3_replay`, `screenshot`, `result`, `guest_str` (a string
from the guest: a known name or its sha12, never game bytes). `boot` and
`loadvm` are quiet by default (every first-pickup popup marked seen, as
the chain's `boot_start` does; an owner demo's aren't: `quiet=`), and a
capture that stops for want of the player tick names what held it
(`meta["held_by"]`: the census `popup`, `dialog`, `hold` or `tick`, AZ-484);
`with s.watch():` ends the row there instead (`s.Hold`, its census and one
EIP sample). An unlabelled capture writes no public copy. For many short driver calls (an agent's Bash call
is capped at 10 minutes and keeps no state) run `python -m devkit xemu
sitting serve <name>` in the background and send drivers with `exec <sock> FILE`; `exec
--end` tears down. `queue <file> <name>... --ev DIR` runs a queue file's
drivers on several serves at once (a worker per serve takes the next line
under the file's lock; `queue <file> --add LINE...` appends, never `>>`);
serves sharing one `--ev` write one `results/runs.jsonl`, every row
tagged with its sandbox, and each keeps `results/generated-<name>.txt`.
Write findings below the report's generated part. **Re-runs reuse the
sandbox (Step X.81d):** a run's end holds its sandbox 300 s (W, its
drive's warm states and its slot; xemu quit, sources checked), and the
sitting's next run with the same `Sitting` arguments takes it with a
relaunch: no queue, no setup, no cold boot, unless a sitting waits in
the queue: that one goes first and takes the held slot. A version-adoption sitting passes `fresh=True` (`serve
--fresh`, a spec's `fresh = true`): fresh sandboxes, cold boots.

**A model-swap sitting (Step X.45).** `from devkit.xemu.sittings import
model_kit as mk; k = mk.kit(s)` in a driver,
then `k.row_zip(...)`, `k.row_ladder(...)`, `k.row_combo(...)`,
`k.row_sentinel(...)` (each in the last row's xemu process unless a
relaunch is due: a lost process, a bugcheck or hung advance in it, a
wall-clock boot, a rate row; Step X.96; its build booted and its sha12
checked, watched) or their parts; a step's own rows go in a
short driver beside them. **Never copy an earlier step's `drivers/`**
(2.105's were 10,123 lines copied forward since 2.75b, and their unchecked
HP hold was filed as a game issue, AZ-530). **A kit fix found in a sitting
goes into `devkit/xemu/sittings/model_kit.py` in that step's record commit**, not a per-step
override or a monkeypatch of `capture`, `tick` or `clear_dialog`. **More
than one sandbox:** a model sitting holds the model slot (D235) and may run
more sandboxes through D263's free-core admission for independent rows
(a lane row and the main row its trace is compared with, `k.trace_cmp`,
share one serve: the traces stay in its private folder):
one serve per tree and release (USA lane, USA main and Europe at once),
each with its own baselines and teardown, sharing the step's evidence
folder (every `runs.jsonl` row tagged with its sandbox, each sandbox's
generated report in `results/generated-<sandbox>.txt`), its rows run by
`queue`; the niced L3 pools slow meanwhile, which fits the priorities.
Europe rows need each VA the kit breaks on in the facts' Europe map (`src/azurkit/core/facts.europe.json`)
(`Sitting._va` raises on an unmapped one: no USA fallback).
**Prefer a spec** when the sitting is the usual shape (start, kit, place,
act, measure): `python -m devkit xemu sitting run spec.toml [--dry-run]` builds from
vanilla before the slot, runs each case into `results/cases.jsonl`
(resumable, one row per attempt, an error costs the row) and fills the
report's CASES table; examples in `devkit/xemu/sittings/`.

**A sitting on save states, by hand:** `up <group>` prints the sandbox's state as
its last line (`W`, `gdb_port`, ...); then `loadvm`, `status`, `press`,
`savevm`, `boot-build` and `down` take that W (`devkit/xemu/README.md`), or a
script drives it (keep each python call under about 9 minutes):

```python
from devkit.xemu import oracle as xo
with xo.Sandbox("flat", out=OUT) as sb:          # up ... down; xo.Sandbox.attach(W) drives one `up` left running
    sb.loadvm("vanilla-flat")                    # halts at its own first player tick (AZ-509)
    cap = sb.capture(40, {4: "down y", 10: "up y"}, label="flat-jump")   # -> OUT/flat-jump.json
    print(xo.jump_summary(cap["rows"]))
```

**The disc a load puts in the tray (AZ-465):** `sb.loadvm(tag)` without
`disc=` puts back the disc the tag was saved with, as the sandbox
recorded it (the tray at its `savevm`, a warm build state's build, a
parked start's disc), else `dvd.iso` (the D98 states and private-drive
tags are vanilla); its event and result name the disc. An owner demo
(`owner_pad`) refuses a load whose disc it didn't record: name it
(`disc=`, the CLI's `loadvm --disc`, `record_spot(tag, disc=)`).

## 4.1 Code identity

Sections 4.2-4.9 are in `reference/recipes.md`, `reference/cheats-warps.md`
and `reference/demos.md`.

**4.1 Code identity: always first.** `loadvm` restores RAM, code included
(hazard 1). Compare guest `.text` with the XBE you meant to test:

```bash
uv run --locked python - "$PORT" path/to/default.xbe <<'PY'   # from the repo root; $PORT = the -gdb port
from devkit.xemu.oracle import RSP, code_identity
g = RSP(int(sys.argv[1])); print(code_identity(g, open(sys.argv[2], "rb").read())); g.cont(); g.s.close()
PY
```

`jump` and `boot-build` run this check (`.text` and `SHIMS`) on every
boot, leaving out the data the build's shims write while the game runs
(`Sandbox.shim_data`: X3's 0x34-byte damage marker; qol_alloc_race's
copy gate's 28-byte state, in every default build, AZ-817). The bare
`code_identity(g, xbe)` above compares every byte, so for such a build
pass `skip=sb.shim_data(name)` (or both of `_player_character.shim_data`
and `qol_alloc_race.shim_data` of the XBE). Vanilla `.text` is `0x11000`, `0xef1d0` (979,408 B)
and a cold boot matches every byte; `.rdata` differs only in the 452
kernel-thunk bytes (0x18F3A0–0x18F5FA).

## 5. Known hazards: the summary

The numbered entries and the open measurements are in `reference/hazards.md`.

**Summary (Step X.96; the fork session's reading, 2026-10-28).** What is still a hazard and what a build or the
harness handles; the numbered entries (`reference/hazards.md`) hold the history.

| # | Hazard | State |
|---|---|---|
| 1 | the four July `vm-20260704…` savestates are modded | **a rule:** never load one |
| 2 | `loadvm` restores the code a state holds | **by design:** test a build by `boot-build` (§6) |
| 3 | TCG doesn't check the SSE2 CPUID bit | **handled** since Step X.58: every sandbox runs `XEMU_STRICT_CPUID=1` (SSE2 `#UD`s, `CpuidFault`) |
| 4, 5 | the build or the comparison isn't what you think | **rules:** §4.1's code identity; like with like |
| 7, 14, 19 | key material in dumps; placements; QMP-migrating a sandbox holding checkpoints | **rules** (19 is the open gap X.94's build left) |
| 8 | the game's HDD cache hides an XBR edit | **the game's:** builds rewrite `filelist.txt`; check the re-copy |
| 9 | the intermittent boot hang (V22) | **fixed** in v0.16.1 (858e2af19f); any halt is named by `XEMU_GUEST_BUGCHECK` with registers and the trap EIP (Step X.94) |
| 10, 11, 12 | USB SIGSEGV, a lost GPU device, the flip-stall hang, an nv2a abort | **fixed** in the fork build (v0.15's exits instead of spinning); `boot-build`'s supervisor relaunches what's left (a dead pad, a Continue that never runs) |
| 13 | a run continued past a `savevm` | **handled:** `Sandbox.savevm` and `park` make every save a checkpoint |
| 15 | an advance that never returns (AZ-451) | **fixed** in the fork's 29a024b18e (v0.14-37, in v0.15); since Step X.94 xemu bounds every advance and run itself (`timeout-ms`) |
| 16, 17 | beside an owner demo; a RAM size xemu can't run | **handled:** background priority (D526); `ram_refusal` at launch |
| 18 | a bugcheck after a fast level load with a renderer (AZ-708) | **fixed** in v0.16.3 (3ca6af93d4) |

**Already in the harness** (no need to ask the fork for them): the live-pad replay (`--live-pads`, a demo
replayed tick for tick, §4.9), guest RAM in shared memory (`XEMU_RAM_SHM`, §3), the access log
(`xemu-watch-start`, `sb.watch`, §3), `mem_limit` `'64'` (a retail-size machine; the D98 states need 128,
hazard 17), PC hooks and `xemu-run`, in-memory checkpoints with verified restores and their `pages-missed`
(§3), and X.94's `timeout-ms` (hazard 15) and bugcheck registers (hazard 9).

## 7. Checks

Absolute paths (agent cwd resets); harness commands from the repo root.

- Fork, dist and fork-build versions (record in the REPORT; a sitting's header names the build it ran): `F=$XEMU_FORK; git -C $F log --oneline -1; git -C $F describe --tags; for b in $F/dist/xemu.app $FX/xemu-v0.16.4-3-g95e7ffc7ec.app; do strings -a $b/Contents/MacOS/xemu | grep -m1 -E '^v?0\.[0-9]+(\.[0-9]+)?(-[0-9]+-g[0-9a-f]+)?$'; done` (a tag's build prints the bare tag: the owner's `v0.15.1`, the release CI's `0.16.4`, its commit on the next line; a local build past a tag its describe, `0.16.4-3-g95e7ffc7ec`; never run the dist's binary in place, even for `--version`)
- Fork anchors: `F=$XEMU_FORK; grep -n 'config_path\|atexit(xemu_settings_save)' $F/ui/xemu.c; grep -n 'vm_stop' $F/gdbstub/system.c; grep -n 'Test-input channel\|^static void test_input_poll' $F/ui/xemu-input.c; grep -n 'xemu_settings_detect_portable_mode' $F/ui/xemu-settings.cc`
- Fixtures unchanged, the small files: `cd "$FX" && grep -v -e ' xbox_hdd.qcow2$' -e ' vanilla.iso$' SHA256SUMS.txt | shasum -a 256 -c` (expect a line `OK` each: the four small files and each kept fork build's binary); the whole set: `shasum -a 256 -c SHA256SUMS.txt` there.
- The sources `jump` clones, dry: `uv run --locked python -c "from devkit.xemu.oracle import fixture_files; print(fixture_files())"` (4 paths, all in the fixtures folder).
- The harness, offline: `uv run --locked python -m devkit xemu oracle selftest` (`selftest: PASS`), `... sitting selftest` and `python -m devkit.xemu.sittings.model_kit selftest` (all three: `uv run --locked pytest -q -m xemu tests/test_xemu_harness.py`); `... slots` (registered sandboxes, running pids, non-sandbox xemus, the admission verdict); `... tags` (the D98 README's 32 tags).
- Snapshots, on a clone: `W=$(mktemp -d /tmp/azx-snap.XXXXXX); cp -c "$FX/xbox_hdd.qcow2" "$W/"; /opt/homebrew/bin/python3.14 -I "$XEMU_FORK/scripts/list_snapshots.py" "$W/xbox_hdd.qcow2"; rm -rf "$W"` (expect the README's 32 `vanilla-*` tags).
- Vanilla XBE: `uv run --locked python -c 'import sys,hashlib; from azurkit.core import iso; print(hashlib.sha256(iso.Reader(sys.argv[1]).read("default.xbe")).hexdigest())' "$AZURKIT_ISO"` (expect `7d1fb519…3f23fdd5`).
