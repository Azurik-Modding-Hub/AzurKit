# azurik-xemu-oracle reference: fixtures and sandboxing (§0, §1, §2)

Part of the `azurik-xemu-oracle` skill. Here: what exists, where things live
and the sandbox recipe by hand (steps 1-4 and the deterministic mode; the
harness's summary, the slots and steps 5-6 are in the card). The card,
`../SKILL.md`, holds the rules, the slots and the sitting loop; the §
numbers and hazard numbers are the skill's (Step 2.216 moved this text here
word for word).

## 0. Exists vs planned

| Thing | State |
|---|---|
| `devkit/xemu/oracle.py` | **Exists** (`devkit/xemu/README.md`; stdlib, `platformdirs` and AzurKit's core; `uv run --locked python -m devkit xemu oracle <cmd>` from the repo root). `jump [--iso ISO] --ticks N` runs §2 end to end from the D98 fixtures, cold-boots the ISO (default: the resolver's vanilla ISO), walks to the Training Arena with breakpoint-confirmed checkpoints (§3), checks `.text`/`SHIMS` (§4.1), captures a tick-locked jump (§4.2) and prints v0 (vanilla: 4.6433; `$W/baseline_{before,after}.txt` identical). The sitting harness: `up`, `loadvm`, `status`, `press`, `savevm`, `hmp`, `boot-build` (§6), `relaunch`, `down [--keep]`, `tags`, `slots`, `selftest` (offline logic check), and simulator Level 3's `snapshot` (guest RAM into the private store, never `$EV` or a repo) and `replay` (an L3 input string replayed exactly; `docs/SIMULATOR.md`); Python API `Sandbox`, `capture`, `write_pad` (the one RAM pad writer), `snapshot`, `replay`, `ram_dump`, `jump_summary`, and on the fork build `screenshot`, `frame`, `frame_advance`, `axis`. Sandboxes run the fork build null and deterministic by default (§2, Step X.22); offscreen for pictures (D184). `AZURIK_XEMU_HDD` clones a private drive whose `vanilla-rzp-*` tags then load (D102); `--out` names the captures folder; a breakpoint the guest is halted at is stepped off. pytest runs only its offline `selftest` (`tests/test_xemu_harness.py`); `tests/test_contracts.py` keeps devkit out of `src/azurkit`. |
| `devkit/xemu/route.py` | **With the reach engine** (Step 4.13d2; Modkit's Steps X.2, X.4): the route pilot, a library sitting scripts call on a sandbox (§4.6); the planner is `devkit/rando/draft/route.py` (Step 4.13c). |
| `l3_certify` | **With the reach engine** (Step 4.13d2; Modkit's Step X.7; D170, D172; `docs/SIMULATOR.md`): the L3 certification pipeline: `sitting <DIR> <W> snapshots` (per level and kit: `loadvm vanilla-rz-new`, an R7 hop, the R2 kit, `savevm`, an L3 snapshot), `search` (offline, `devkit/sim/l3_search.py`), `sitting <DIR> <W> replays` (`Sandbox.replay` tick for tick, then `snapshot(here=True)` where it halted), `apply` (proof records into `src/azurkit/tools/randomizer/data/proofs.jsonl` and the authoring files). Sitting x7 (2026-10-13): its report. |
| `devkit/xemu/sitting.py` | **Exists** (Step X.9; Step 4.14a3): the sitting kit (§3, "A sitting through the kit"): `Sitting` (queue, private folder, guaranteed teardown, generated `REPORT.txt` header), the R2/R6/R7 recipes (`src/azurkit/tools/randomizer/live/recipes.py`), HP holds, captures with a scrubbed public copy, `screenshot`, the native cheat codes and level warp (`cheat`, `warp`, §4.8, Step X.17), and the exec server (`serve`/`exec`), the `queue` that N serves pull from (Step X.45). **Don't copy helpers into an evidence folder**: import the kit. |
| `devkit/xemu/sittings/model_kit.py` | **Exists** (Step X.45, D11: dev-only): the model-swap sitting's row families, once each, from Step 2.105's last working drivers: f3's zipline set (teleport, walk-in, the placed ride, the ride to the cable's end, let-go, let-go plus flap, pictures), a1's ladder, e7's combo, f6's lone sentinel, the floor cast, the camera-point readers (0x81277, 0x8129C) and their judge; Step 2.107's frame score (`row_frame`, `frame_on`: per tick the player's drawn box in NDC, the point, the eye's distance and step, the eye over the surface) and `row_swim`, with 2.104's and 2.105's f6, a1 and w1 families (`ground_cam`, `jump`, `runoff`, `pit`, `wall_rest`, `swim_rest`, `swim_sink`, `waterjump`); §3, "A model-swap sitting". |
| `devkit/xemu/chain.py` | **With the reach engine** (Step 4.13d2; Modkit's Step X.12, D172; `docs/SIMULATOR.md` § "Chains"): the chain driver (§4.7): a plan's spoiler paths as segments, each played snapshot → L3 search → exact replay → drain in one sandbox, every start parked (`Sandbox.park`/`unpark`: `savevm`/`loadvm` with the guest held halted, bit-identical, sitting x12) so xemu may quit during a search; `chain.json` per run. |
| `devkit/xemu/demo.py` | **Exists** (Step X.31a, AZ-397; Step 4.14a3; `devkit/xemu/README.md`, §4.9): the owner-demo kit beside a `--window --owner-pad PORT` sandbox: `record` (a JSONL row per player tick, taken at the update's RET by the fork's PC hooks on v0.15, else polled from `XEMU_RAM_SHM`; the level's nodes followed through loads and respawns) and `replug` (the owner's pad on port 1 after a load drops it); `note_level` and `note_tag` for a demo's setup driver. X.27's and X.28's copies in `$EV` are superseded. |
| Not ported | s6's group scripts and their `README.md` (the API, the scancode map, the quirks: row timing, input latency, the shared armor chain) stay in sitting s6's evidence; the R0 notes behind the recipes (`ramrec.py`: node reads, save requests, targets) stay in `$EV` too. |
| The spike's `oracle.py` and helpers (`jump2/jump3/walk/capture_jump/explore/trybuttons/shot/xbe.py`) | **Outside git only**: the spike's archive in `$EV`. Never copy the archive into the repo wholesale (it holds whole ISO files the leak guard refuses); a snippet may be committed (D87). They hard-code `/tmp/sim-spike/xemu`, FIFO `/tmp/xsim.fifo`, gdb port `12345`, breakpoint `0x8CCC0`, `ENT=0x15d5900` and (jump scripts) scancode `44`; `jump2/jump3/walk` write JSON to the cwd. |
| `game_live_*` MCP tools | **Deferred** (Modkit's MCP roadmap; `docs/MCP.md` has the 8 tools). |
| Vanilla gameplay states | **32** on D98's HDD (§6). |

- A row's `ret` and a REPORT's "caller" are return addresses (the
  instruction after the CALL); the skills cite the CALL
  (`python -m devkit re xbe calls --to <VA>`).
- Python: the harness under `uv run --locked python`; the spike's helper
  clients under Homebrew `/opt/homebrew/bin/python3.14 -I`.
- Name helpers in `$W` so they can't shadow a stdlib module (a `dis.py`
  did once). zsh doesn't word-split `for s in "a b c"`: loop in a bash
  script.

## 1. Where things live

| What | Path |
|---|---|
| Fork source | `$XEMU_FORK`, the owner's fork checkout (branch `macos-optimizations`) |
| Built app (**the owner's bundle: never run it in place, never plant files in it**) | `$XEMU_FORK/dist/xemu.app` (2026-10-23: `0.16-48-gb44bb02f9b` by its strings, neither the v0.16.1 tag's build nor v0.16.2's; binary `31d2ba96ea8b`). `build.sh`'s `package_macos` does `rm -rf dist`. |
| **The fork build every sandbox runs** (D184; Steps X.14, X.22, X.26, X.30, X.32, X.40, X.43, X.61, X.66, X.71, X.72, X.94) | `$FX/xemu-v0.16.4-3-g95e7ffc7ec.app` since Step X.94 (D894): the owner's local PGO arm64 build three commits past v0.16.4, from the fork session's artifacts of 2026-10-28 (`cp -Rc` as built, ad-hoc signed, 16 files), binary sha256[:12] `eb749faf0807`; it logs `xemu_version: 0.16.4-3-g95e7ffc7ec`. Over v0.16.4: 39d8f4e002 (AZ-822: HMP `savevm`'s migration dirty sync re-arms the store traps of every page it takes, by ram_addr, so after a park an incremental checkpoint restore misses no page; the fork's repro 26,408 and 30,537 pages missed on v0.16.4, 0 and 0 here), ef33705322 (`XEMU_GUEST_BUGCHECK`'s QMP event carries `regs` and 4 KiB of `stack`, stderr a registers line: hazard 9), 95e7ffc7ec (`timeout-ms` on `xemu-frame-advance`, `xemu-run-until` and `xemu-run`: hazard 15); deterministic goldens and RAM hashes equal to v0.16.4, speed parity, no savestate section changed; the open gap: hazard 19. `$FX/xemu-v0.16.4.app` (the fork's v0.16.4 release, binary `5c4f4ce6472a`, logs `xemu_version: 0.16.4`) stays while the lanes that run it end (`--app` its path). What each build from v0.14-8 to v0.16.4 brought, the retired copies' hashes and each adoption's drivers and baselines: Modkit's `docs/archive/skills-history.md` (its archived repository) § azurik-xemu-oracle ("The v0.14 builds' history", "The v0.15.1 and v0.16 rows", "Section 1's fork-build row, v0.16.1 to v0.16.4"). **A newer owner build:** `cp -Rc` its dist into `$FX/xemu-v<the version it logs>.app` when its strings name the tag (an older dist without the owner's code: the fork skill `xemu-operate`'s "refresh a clone's binary" recipe; a dist that isn't the tag's build: the release's macOS zip, `gh release download <tag> -R MichaelJSr/xemu-macos -p 'xemu-<version>-macos-universal-unsigned.zip'` (by its whole name: `*macos-universal*` also takes the `-dbg-` zip) into its own empty `mktemp -d` folder, unzipped there, nothing run there), its sha256 into the fixtures' README and `SHA256SUMS.txt`, run §2's checks on it with `--app <path>` first (each sitting `fresh=True`, `serve --fresh`: cold boots, no shared states, Step X.81d; X.72's drivers, X.72's drivers, against its `results/baseline-v0.16.4.json`, and the fork's `bench-det.py --check d98` from a read-only copy of its tag's scripts), then point `FORK_APP` at it, keeping the previous build's copy while lanes on it end. A deterministic screenshot advances itself past a stale picture (Step X.61c, `last_picture["advanced"]`): add those vblanks before comparing per-frame picture rows with an older baseline. |
| **Oracle fixtures: the only sandbox source** (D98) | the folder `AZURIK_XEMU_FIXTURES` names, else the user data folder's `xemu-fixtures` link (`$FX` below; D98's folder, outside every checkout). `README.md` (the "Savestates" table, §6) and `SHA256SUMS.txt`; `xemu.toml` (its five `[sys.files]` paths inside the folder, `dvd_path` at `vanilla.iso`), `xbox_hdd.qcow2` (D67's oracle HDD, §6), `eeprom.bin`, `mcpx_1.0.bin` (MCPX boot ROM), `Complex_4627v1.03.bin` (flash BIOS), `vanilla.iso` (the same disc as the repo's), the fork build `xemu-v0.16.4-3-g95e7ffc7ec.app` (the default since Step X.94, above), v0.16.4's release `xemu-v0.16.4.app` (while the lanes that run it end; v0.16.3's to v0.16's are retired, D678, D683) and the kept build `xemu-v0.13.3-37-gd5ad94f4bf.app` (the fallback, `--app kept`). **No measurement runs on them in place.** Agents may maintain the folder (README, `SHA256SUMS.txt`, kept builds, a drive the owner approves; D100); new states are made on a clone, checked, then moved in (§6). |
| The fork's test fixtures: **not a source** | the fork's own `fixtures/` beside its checkout (set up for the fork's modded disc). Never point `AZURIK_XEMU_FIXTURES` at them. |
| The owner's own xemu: **never a source** | the owner's Xemu folder (`OWNER_XEMU`) and `~/Library/Application Support/xemu/xemu/` (live `xemu.toml`, `eeprom.bin`, caches). Personal play changes them. No sandbox reads, clones or launches from them; `jump` only lists the pref dir (mtime, size) before and after, to show the caches stayed in `$W`. |
| Vanilla ISO | through the resolver (`AZURKIT_ISO`, then the user data folder's `usa.iso`; Europe: `AZURKIT_ISO_EUROPE`, then its `europe.iso`) and its identity check (`azurkit.core.gate`). A disc inside the fixtures folder boots only if it passes that check (`boot_disc`), so `$FX/vanilla.iso` boots and a modded disc there is refused. Builds go to a `mktemp -d` folder. |
| Vanilla XBE | inside the ISO only: `default.xbe` sha256 `7d1fb519…3f23fdd5` (the facts' XBE sha256, `src/azurkit/core/facts.usa.json`; `uv run --locked azurkit verify --iso <image>`). |

The D98 `xemu.toml` still sets things a harness must never inherit
(`background_input_capture = true`, `fullscreen_on_startup`,
`fullscreen_exclusive`, `port1` bound to a real pad, a non-zero
`volume_limit`). The scratch toml (§2 step 3) overrides every one.

## 2. Mandatory sandbox recipe

Why: `atexit(xemu_settings_save)` in the fork's `ui/xemu.c` writes back
whichever config was loaded, so launch **only** with `-config_path`
(parsed in the same file) on a copy. Caches go to the real pref dir
unless portable mode is on (`xemu_settings_detect_portable_mode` in
`ui/xemu-settings.cc`: an `xemu.toml` in the *copied* app's
`Contents/Resources/`). v0.15 (0babe23fbc) reads `XEMU_BASE_PATH=<dir>`
ahead of portable mode (check with `grep -qa XEMU_BASE_PATH <binary>`);
the harness points it at `$W/xemu-data` there (Step X.33, PROMPT-7 A(4)),
so on v0.15 every sandbox's data dir is its own (sitting x32: the pref
dir's listing unchanged in every teardown), and never passes an
inherited one on, nor the fork's other run-changing variables
(`NOT_INHERITED`: traces, block, voice and audio logs, live pads, strict
CPUID, which the harness sets itself: hazard 3). The
player's `[automation]` table never applies to a sandbox (the fork's
rule: no `-config_path`, no `XEMU_BASE_PATH`, not portable, not `-name
xemu-fork-auto`; sitting x32: a sandbox toml holding one printed
`ignored (-config_path names the config)` for both keys).
The HDD is opened `locked=on` and written. Agent
shells don't keep variables: re-set `W=` in every call.

**Steps 1–2. Baseline the sources (re-run at teardown and `diff`), then
clone** (APFS clones: instant, writes stay in `$W`). Run from the repo
root (in a lane, set `AZURKIT_ISO` first). Compare the D98 files with
their `SHA256SUMS.txt` (§7); the HDD's line changes whenever the owner
adds a state.

```bash
W=$(mktemp -d /tmp/azx-oracle.XXXXXX); echo "$W"
FX="${AZURIK_XEMU_FIXTURES:-$HOME/Library/Application Support/AzurKit/xemu-fixtures}"   # D98
ISO=$(uv run --locked python -c 'from devkit.xemu.oracle import vanilla_iso; print(vanilla_iso())') && echo "$ISO"   # or a build, or "$FX/vanilla.iso" (the same disc)
ORIG=("$FX/xbox_hdd.qcow2" "$FX/xemu.toml" "$FX/eeprom.bin" "$FX/mcpx_1.0.bin" "$FX/Complex_4627v1.03.bin" "$ISO")
for f in "${ORIG[@]}"; do printf '%s %s %s %s\n' "$(shasum -a 256 "$f" | cut -d' ' -f1)" \
  "$(stat -f %m "$f")" "$(stat -f %z "$f")" "$f"; done > "$W/baseline_before.txt"
cp -Rc "$FX/xemu-v0.16.4-3-g95e7ffc7ec.app" "$W/xemu.app"   # the fork build (D184); never the owner's dist in place
cp -c "$FX/xbox_hdd.qcow2" "$FX/eeprom.bin" "$W/"
cp -c "$FX/mcpx_1.0.bin" "$W/bootrom.bin"; cp -c "$FX/Complex_4627v1.03.bin" "$W/flashrom.bin"
cp -c "$ISO" "$W/dvd.iso"
```

**Step 3. Write the scratch config, plant the portable marker, copy the
scripts.** `scratch_toml()` removes `port1` (the states were saved with
only the port-2 keyboard pad), binds that pad to scancodes 232–256, drops
the F5–F8 snapshot shortcuts, turns off background input capture,
fullscreen and sound (`[audio] volume_limit = 0.0`; it refuses a config
without it), points all five `[sys.files]` paths (HDD, EEPROM, boot ROM,
BIOS, DVD) and both folders at `$W`, and asserts the result via
`tomllib`.

```bash
uv run --locked python - "$W" <<'PY'
import pathlib
from devkit.xemu.oracle import FIXTURES, scratch_toml
w = sys.argv[1]; s = scratch_toml((FIXTURES / "xemu.toml").read_text(), w)
for p in ("xemu.toml", "xemu.app/Contents/Resources/xemu.toml"): pathlib.Path(w, p).write_text(s)
PY
SPIKE=<the spike's xemu folder, sim-spike/xemu in $EV>   # read only
cp "$SPIKE"/{oracle,jump3,walk}.py "$W/"   # screenshots: QMP screendump (section 3)
sed -i '' "s#/tmp/sim-spike/xemu#$W#g; s#/tmp/xsim.fifo#$W/input.fifo#g" "$W"/{jump3,walk}.py
```

The `sed` leaves `ENT=0x15d5900` and scancode `44` (Y is 235 in the
scratch map); fix them once known (§3 input, §4.2).

**Step 4. Launch, recording your own PID.** Create the FIFO *before*
launch: xemu tries it once (`O_RDONLY|O_NONBLOCK`, first poll) and
disables injection for the session if that fails (`test_input_poll` in
`ui/xemu-input.c`).

```bash
mkfifo -m 600 "$W/input.fifo"
lsof -nP -iTCP:12345 -sTCP:LISTEN && echo "port 12345 busy: pick another and edit the scripts"
XEMU_HEADLESS=null XEMU_INPUT_PIPE="$W/input.fifo" nohup "$W/xemu.app/Contents/MacOS/xemu" -config_path "$W/xemu.toml" \
  -gdb tcp:127.0.0.1:12345 -qmp "unix:$W/qmp.sock,server,nowait" -S -icount shift=2,align=off,sleep=off > "$W/run.log" 2>&1 &
echo $! > "$W/xemu.pid"
```

**Deterministic by default (Step X.22; D184's headless modes).** The
harness passes `XEMU_HEADLESS=null` (no window and the null renderer;
vblank and flip timing still run; the saved renderer setting is restored
at exit) and, on a build that has it (the fork build: `st["deterministic"]`),
`-S -icount shift=2,align=off,sleep=off`: guest time follows executed
instructions, not the host clock, and runs as fast as the host allows
(v0.16.1, sitting x61 at load 79-87: 160-663 fps in the D98 field states,
median 399, save menus about 1,830, offscreen deterministic 46 fps;
v0.16, sitting x43 at load 19-25: 192-667 fps in the D98 field states,
median 446, save menus about 1,820, offscreen deterministic 34 fps; v0.15.1,
sitting x40 at load 7-10: 194-704 fps in the D98 field states,
median 472, save menus about 1,690, offscreen 46.5 fps; v0.15, sitting x32 at load 29-37:
98-576 fps in the D98 field states, median 244, save menus about 1,140, a player tick by breakpoint 23.4 ms
and by PC hooks 8.6 ms in X.15's w2 walk). The same state, input and QMP and
gdbstub calls then give bit-identical guest RAM in any run or process
(sitting x32, below). `-S` holds the guest until the first `loadvm`
(each load resets the host's device state); a `loadvm` without
`halt_at_tick` then runs it, `run()` starts a cold boot, and `jump` and
`boot-build` work as before. Pads change only at a vblank and only from
the pipe (physical pads are ignored: the fork never starts SDL's
gamepad subsystem under icount); each load drops the queued pipe lines
(write a run's input after its load: `loadvm(tag, paused=True)`, then
`send`, then `frame_advance`; a load or save that drops a line the
harness wrote logs a warning), and a state saved under icount
brings back the keys and axes the pipe held, one saved without (the D98
states) a neutral pad; host audio is off. **The RTC is fixed already
(Step X.58):** under any `-icount` v0.16 runs it on the virtual clock
from 2001-01-01T00:00:00 unless `-rtc` says otherwise (the fork's
ed21e852cf: `system/vl.c`, `configure_rtc_deterministic` in
`system/rtc.c`), and a load continues from the date its snapshot saved
(`rtc_post_load` in `hw/rtc/mc146818rtc.c`), so the harness passes no
`-rtc` (`base=...,clock=vm` would change nothing). Sitting X.58
(offscreen deterministic; sitting x58): two
power-on boots from `-S`, no input, each on a fresh HDD clone, gave the
same picture and RAM at frames 900 and 1800, the RTC
2001-01-01T00:00:14 and :29 in both; a second power-on in the same W
differs (its RAM from frame 900, its picture by 1800) because the first
wrote the drive's cache (4.6 MB by frame 1800, the second 512 B), and
repeats in turn. `boot-build`'s cold boots went by wall clock (X.58's
two reached the steady tick 72 frames apart, 2129 and 2201, pictures
29.7 % of pixels apart; AZ-675); since Step X.64 a deterministic one
runs on guest frames (§6, `boot_frames`) and repeats in every process.
A `savevm` is a checkpoint
(hazard 13). Keep the network, XMU, USB passthrough and
pad hot-plug off (they follow the host). `1` (`--headless 1`,
`headless="1"`): offscreen (a hidden window, no Dock icon, no focus, no
menus, overlays or popups; the game renders on the GPU; xemu adds
`-audio none` and opts out of App Nap), for a sitting that needs
pictures: in real time unless asked (`--deterministic`,
`deterministic=True`, a spec's `deterministic = true`): then
offscreen Vulkan under the same `-S -icount`, every GPU report in RAM
before the GPU rests, so a screendump taken paused is the same PNG in
every run and process (sitting x30: two PNGs and the RAM byte-identical
in three processes, one load each; v0.15, sitting x32: the first load
in a fresh process gave x30's very PNGs and RAM), at about 48 fps on
v0.15 (the kit's report says which). **Repeated loads there:** on
v0.14-36 a repeated `loadvm` in one long-lived offscreen Vulkan process
diverged about 1 time in 7 (the fork's known issue, 2026-10-15); v0.15
fixed icount loads (PROMPT-7 E(1)), and seven loads in one such process
ended on the same RAM in sittings x32, x40 (v0.15.1) and x43 (v0.16). D200's guard
(Step X.31a) keeps warning by name on each load after the first there
(an event and a `warning: D200:` line) only on a build before that fix,
one without `XEMU_LOAD_VERIFY` (Step X.32b). `0` (`--window`): a visible window, never
deterministic, for visual work an agent must watch.
`Sandbox(deterministic=False)` runs null in real time.
The build prints `xemu: headless mode: offscreen|null` at startup (the
sandbox records it as `headless`); unset, empty or 0 changes nothing.
The kept v0.13.3 build has no headless or deterministic mode: it opens
its window. Screenshots need a renderer: offscreen or windowed (QMP
`screendump`, §3); the null renderer's are refused.

(The version-adoption sittings' measurements that stood here, x32 on v0.15
to x94 on 0.16.4-3-g95e7ffc7ec, are in `history.md`.)
