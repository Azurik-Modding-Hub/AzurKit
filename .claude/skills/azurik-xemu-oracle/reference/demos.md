# azurik-xemu-oracle reference: owner demos (§4.9)

Part of the `azurik-xemu-oracle` skill. Here: owner demos (the owner plays,
we record). The card, `../SKILL.md`, holds the rules, the slots and the
sitting loop; the § numbers and hazard numbers are the skill's (Step 2.216
moved this text here word for word).

**4.9 Owner demos: the owner plays, we record (Steps X.27, X.31a; D205, D207).**
For a route or skip only the owner can show
(demo x27's report,
demo x28's report). The kit is in the repo
(Step X.31a, AZ-397): `--owner-pad PORT` on `up` or the kit's `serve`,
and `devkit/xemu/demo.py`'s recorder and re-plug watcher
(`devkit/xemu/README.md`). The one case for a visible window on the owner's
screen.

- **A warm shader cache (Step X.69; the fork's FRAME-8bffffeb0243
  answer: a first fire-armor cast compiled 1.9-2.3 s cold, 45-190 ms
  warm, and x67demo's empty base compiled 679 variants):** every window
  (`--window`, so every owner demo) starts from its build's kept cache,
  `~/Library/Caches/AzurKit/xemu-shader-cache/<binary sha12>/`, seeded
  once by `cp -c` from the fork's `~/Library/Caches/xemu-fork-bench`
  (read only) with only what that build reads (its pipeline caches,
  v0.16.3's `vk_prewarm-*` lists, its version's `spirv_cache_v*`
  folders), cloned into `$W/xemu-data` before the launch; `down` clones
  back what its xemu wrote or changed (`st["shader_cache"]`, an event
  each way), so the next demo of that build starts warmer. It is W's own
  copy: the sources' baselines don't move. Null and offscreen sandboxes,
  deterministic or real time (the rate pairs too), keep an empty base.
- **Set up and switch bodies (Step X.56): no drivers.** Never copy an
  earlier demo's `drivers/` (2.137, 2.142 and 2.147 each copied
  build.sh, d00-d03, a lib and load_tag.py forward). From the demo's
  worktree, `AZURKIT_ISO` exported, launched from bash (hazard (c)
  below):
  1. `serve <name> --step S --ev <folder> --window --owner-pad 1 --record
     1` in the background; its socket is `logs/sock-<name>.txt`, W the
     `serving` line's. On v0.16 a window's scratch config has frame
     interpolation off (the fixtures' `'2x'` hung v0.16's windowed
     boots); on v0.16.1 (188ff96260: a present waits at most 100 ms for a
     drawable, then drops frames and keeps serving input and
     screendumps) it keeps the owner's `'2x'`, and `down` keeps the run
     log's present stalls (`st["present_stalls"]`; QMP
     `XEMU_PRESENT_STALL`); a relaunch keeps the lease (hazard 16).
  2. The watchers at once, before any row, each detached from bash:
     `demo record <W> <private>/trace.jsonl` (meta: W's
     `demo-meta.json`) and `demo replug <W> <private>/replug.log`.
     They talk QMP only between the serve's requests (W's QMP turn,
     AZ-644: each exec request holds it), so they run for the whole demo
     and are never stopped for a boot, a tag or a load; the recorder's
     meta line comes at its first pass with the turn.
  3. `demo add-body <sock> --vanilla --no-load` (C0, the control),
     then `demo add-body <sock> <body> [--mode own|garret4]
     [--size own|garret4] [--level w1|f6] [-- <more randomize-full
     args>]` per body: built from the worktree's tree (it prints HEAD
     and says when it isn't origin/main) into the serve's private
     `builds/`, booted quiet at the level's save, 60 ticks at rest,
     tagged `<name>-<sha12>-<level>` with the level checked at the save
     (AZ-645), and loaded, the guest running: the ready state. It prints
     `TAG <tag>`. The first load waits for the owner's pad. A boot or
     tag that fails loads the body before it again (else lets the guest
     run) and says why.
  4. **The quick switch** (the owner, 2026-10-21: "switch the play
     session to play as a air elemental quickly"): `add-body <sock>
     air_elemental`, one command, the owner playing on until its load
     (sitting X.56, offscreen with both watchers running: 42.8-59.0 s
     from the command to the load by body, the air elemental 42.8-47.6 s
     with its build 9.3-12.7 s and its boot 31.2-32.4 s, balthazar up to
     50.2 s, booblord at f6 59.0 s; 2.147's by hand about 2.5 min).
     **The switch back** to a
     body tagged before: the same command (its build and tag reused: one
     load, 0.1-0.2 s). Each add-body load is named by its own tag; the
     boot's own reloads, which move no clock, are marked on a request's
     first drained row with the tray's disc then (`tag` null).
  5. **Teardown:** a `STOP` file beside the trace (delete it after the
     `end` line), replug's own pid ended, `exec <sock> --end`; copy
     `W/demo-meta.json`, `W/input-record*.txt` and the trace into the
     private store; delete W and the private folder by their exact
     paths.
- **Set up first:** each spot's start placed and saved (`loadvm`, R7
  `hop` or the warp, R2 kit, R6, `savevm <spot>-start`, or
  `demo.note_tag(sb, tag, meta)`, which also records the tag's
  clock and level so the recorder names a load of it), plus a retry
  state after a failed jump; `demo.note_level(sb, iso, meta)` once
  per level writes its switch and timer nodes. One windowed real-time
  sandbox, volume 0: `serve <name> --window --owner-pad PORT --record
  PORT` (or `up`; `Sandbox(owner_pad=)`, `Sitting(owner_pad=)`), which
  binds the owner's pad in the sandbox's own `xemu.toml` (the fixtures'
  GUIDs: the first on PORT, the other on port 3, `auto_bind` on) and
  refuses any other display or a deterministic run. A demo's `serve`
  never idles out or yields its sandbox to a waiting sitting, and keeps
  W (`input-record.txt`, the HDD clone with its states) and the private
  folder unless `--no-keep`: after `exec --end`, copy what you keep,
  then delete both by their exact paths.
- **Which port:** the binding holds for the sandbox's life (`up` writes
  its `xemu.toml`) and the pipe drives only the keyboard pad.
  `--owner-pad 1` keeps the keyboard pad on port 2, so the warp,
  `cheat` and `boot_build`'s menu walk still run in the demo sandbox,
  with `demo replug` after each load (X.27, X.28: measured): a
  demo of a modded build (2.76) takes this one. `--owner-pad 2`
  replaces the keyboard pad, so the pipe drives nothing there: set up
  with RAM and monitor verbs only (`loadvm`, `hop`, the kit, `place`,
  `savevm`; a dialog `hop` meets waits for the owner's A), or first in
  a `--keep` sandbox with the keyboard pad, its tags named
  `vanilla-rzp-*`, then start the demo on its drive
  (`AZURIK_XEMU_HDD=<that W>/xbox_hdd.qcow2`, Q250; vanilla disc only:
  a booted build's state needs its disc in the tray).
- **The demo's own hazards (AZ-466, X.34 and X.35), which the kit
  handles:** (a) a state saved with the owner's pad holds its hub
  (USB 1.3 for port 1; 1.4 for port 2): a `loadvm` before the pad is
  connected fails ("Unknown section ... usb-hub"), so a demo's
  `loadvm`/`unpark` waits for `Port 1.3,` in `info usb` (`OWNER_PAD_S`,
  15 min, the wait in an event: connect the pad), and plugs the
  replug watcher's demo hub (1.1, its pad reading port 1) first when
  the state was saved here with it (`tag_usb`; `plug_pad`). (b) xemu's
  Snapshots menu (v0.15+) loads a state without asking when the tray
  holds its disc: the saved path, or the same image by the fingerprint
  a v0.15+ save keeps (X.67's `vanilla-rzp-*`) or its saved image file;
  else it asks ("DVD Drive Image": Load Anyway, Load With Tray Disc,
  Cancel; D98's states, no fingerprint, their image gone). It refuses
  none (Step X.104, from the fork's source). A demo's `savevm` saves
  under a disc in W and says the path; a load of a state saved
  elsewhere says when the menu asks (savevm it in the demo). The menu
  never runs headless: the HUD (menu, F5-F8, the dialog) is drawn only
  in a window, and states saved headless have no menu thumbnail.
  (c) zsh's `bg_nice` runs a `&` job at nice 5 and xemu inherits it
  (only root renices to 0): `up` and `relaunch` refuse an owner demo
  from a niced process (launch from bash, after `setopt no_bg_nice`, or in the
  foreground); `st["xemu_nice"]` records what xemu got. (d) An R6
  placement far from the loaded area shows no geometry (X.35's a5 hub
  and island): start a demo at a level's arrival or a save platform.
- **Re-plug the pad after every load (port 1):** a `loadvm` restores the
  guest's USB state as saved, so a pad xemu attached before it is gone
  for the game. `demo replug <W> <log>` watches the game's pad
  handles through shared memory and, 3 s after a load left slot 2 empty,
  `device_del`s the old hub and `device_add`s `{"driver": "usb-hub",
  "port": "1.1", "ports": 3, "id": "demohub"}` and `{"driver":
  "usb-xbox-gamepad", "index": 0, "port": "1.1.1", "id": "demopad"}`;
  the game opens it and takes it on the first press (`--once`: now). A
  state saved with the hub holds it: a fresh sandbox may need the same
  `device_add` before its `loadvm`.
- **Record without stopping the guest:** `demo record <W>
  <trace.jsonl> --meta <meta>` writes one JSONL row per change of the
  player's event clock (entity +0x18, a double). **On v0.15 (Step
  X.32b, AZ-518)** each row is taken at the player update's RET by the
  fork's PC hook (`HookRows`: one `xemu-hooks-drain` every 50 ms; the
  meta line says `rows: ret`, each row `ret: 1`), so every field is the
  same tick's and the pad is the builder's; the level's nodes and
  generators come from collect hooks whose regions are address
  expressions from their record indices, evaluated every tick, so a
  respawn or a reload is followed from the next tick (AZ-479; sitting
  x32b: a 60 s agent-driven real-time demo, 1,892 rows, all at the RET,
  replayed per tick with its camera within 0.0001 m, state and HP exact;
  sitting x49: a death in d1, the game's own respawn after one A on its
  popup, the nodes at a RET halt equal to the trace's, a kill's numDead
  row). A load is marked once, on the row its clock
  jump marks, with the run log's count read there (AZ-522, Step X.49;
  a load with no clock jump on the row after the 2 s flush reads the
  count, an in-game reload's jump with no count): a run starts at the
  clock jump. On an
  older build it polls guest RAM through the sandbox's `XEMU_RAM_SHM`
  every 2 ms, as below. A row holds: state, body, facing,
  velocity, flaps used, HP, armor, air gauge, the contact normal
  (+0xB8), the fall reference (+0x168), the animation index, the active
  ControllerState, inventory changes, the level's switch and timer
  nodes and every critterGenerator's numDead (a boss's too) on change
  (numbers only, never game bytes); missed ticks
  (`gap_ticks`, at the game's own rate) and each load (the tag named:
  by clock, level and the tray's disc, AZ-612; none when two builds'
  tags share the clock and the disc can't be read).
  After every load or clock jump (a Snapshots load, an in-game reload)
  it resolves the nodes again from their record indices (X.28's kept
  stale addresses after a reload), and after the game's own respawn,
  which moves them with neither (X.34's Spideyzar: a watched node's
  pointer changed, the row's `moved`; AZ-479). **Per-tick pads
  (AZ-475):** the pad is read first at every poll, exact, with the read
  before the tick kept as `pad_alt` where it differs (the builder read
  one of the two); `demo.tick_pads(rows)` gives a per-tick replay
  its float blocks (written at `INPUT_BUILD`, the latches the game's),
  since a real-time demo's vblank-tagged record drifts once its ticks
  run long (R1.16c: from n 7864). **The camera (AZ-508, Step TD.0):**
  the builder reads it from a stack local at 0x85276, which shared
  memory can't see, so `record` arms the fork's PC hook there (v0.15's
  `xemu-hooks-set`, collecting [esp+0x14] and the clock through EBP) and
  drains it over QMP at each row (`cam`, the hit's frame `cf`, and
  `cam_gap` for the ticks it missed). The fork installs a hook only on
  a stopped VM, so the recorder pauses a running guest for the call
  (`stop`, `cont`); the meta line must say `"cam_hook": "armed"`; it
  clears only its own hook, on a re-arm and at the end. Start it before
  the load a replay starts from (it marks only loads it sees).
  `demo replay` replays a run tick by tick (the pad block at the
  update entry, the camera at 0x85276) and `fit-cams` fits an older
  trace's camera in L3 (`devkit/xemu/README.md`). Sitting TD.0 (2026-10-18,
  v0.15.1, a 60 s real-time offscreen demo with stick and camera turns,
  jumps, flaps and rolls): 1,959 ticks replayed, every compared tick
  within 0.0006 m with the state exact (HP unchanged) but 3 rows the
  recorder read mid-update (AZ-518: a row can hold the tick before's
  state, state time or body, its state time even advancing); X.36's M2, recorded without the hook, isn't exact even with
  `fit-cams` (torn rows at its landing and catch). The RET rows (above)
  can't tear; for a poller's trace `replay` and `fit-cams` mark a row
  that holds the replay's tick before's state and state time `torn` and
  skip it (Step X.32b). A `STOP` file beside
  the trace (checked every 2 s: delete it after the `end` line) or a
  SIGTERM ends it. Marks per attempt stay the driver's.
- **Record the pad (Step X.30):** run the demo sandbox with
  the recorder (`serve --record PORT`, `Sitting(record=PORT)`, `up
  --record PORT`): every vblank xemu writes what that port's pad gave
  the guest as pipe lines tagged `+N` from the last load into
  `W/input-record.txt` (a relaunch keeps the last as
  `input-record.<n>.txt`; copy it into the private store before `down`),
  one `# load` section per load (the owner's Snapshots loads included).
  **A demo as played (v0.15, Step X.32b, AZ-475):** `serve <name>
  --window --owner-pad 2 --record 2 --live-pads` (`Sandbox(live_pads=True)`)
  runs the window under `-icount shift=2,align=on,sleep=on` with
  `XEMU_ICOUNT_LIVE_PADS=1`: the owner's gamepad drives the pad as in
  real time, read once a vblank, so the run stays deterministic and the
  recording holds exactly what the guest got; its section, replayed by
  `play_recording` after a paused load of the same state in a
  deterministic sandbox, ends on the session's RAM, tick for tick
  (sitting x32b, the agent's pad: a 30 s offscreen session, 1,785 frames,
  replayed in another process onto its end RAM, no per-frame trace
  compared, the state's port-1 hub
  plugged by `XEMU_LOADVM_ADD_PADS` alone; the owner's gamepad unsat). The
  owner's gamepad takes port 2's pad (the keyboard pad's, which the D98
  states hold) by QMP `xemu-input-bind` once xemu is ready, so nothing is
  plugged and no load needs a re-plug (the pad follows its port; the
  pipe then drives nothing there: set up with RAM and monitor verbs, as
  `--owner-pad 2`); a scene the host can't run at full speed plays slower
  (stderr says by how much). Every sandbox on v0.15 loads with
  `XEMU_LOADVM_ADD_PADS=1`, so a state holding pads the replay sandbox
  lacks plugs them itself. An agent-driven one (`--headless 1
  --live-pads --record 2`, no owner) drives the pad through the pipe.
  **Seen with the owner's pad (Step x.92b, AZ-475; the X.92 demo,
  windowed, 0.16.4-3):** each section replayed **offscreen
  deterministic** (`Sandbox(headless="1", deterministic=True)`, the
  frames the window drew) equalled his trace on every tick and field
  (A: 5,715 of 5,715 ticks through a save platform's save, two quits,
  Start New Game, the store, the reload, the carry, a pause and the
  melt; B: 2,224 of 2,224), one frame offset each. In a **null**
  sandbox the same sections drifted (A from tick 740, B from 718): the
  frames a menu or a load takes differ without a renderer, so a later
  line lands a tick off [inferred]. Replay a windowed demo offscreen,
  from the tag as saved: a state written first (levels poked to 0)
  drifted offscreen just as the null replay did.
  **Without `--live-pads`, real time:** under plain icount the fork
  ignores physical pads, so the demo stays a normal real-time window,
  whose recording replays within a vblank, not tick for tick; a session whose game ran slower than
  its vblanks (X.36: 59.6 s of game clock in 139.6 s) lands its input later in game time, so its
  trace compares only up to the first input (sitting x49). **Bind the owner's pad on port 2** where
  its setup allows (above; `--owner-pad 2 --record 2`; where the D98
  states were made with it, so no re-plug [inferred, not yet tried with
  the owner's pad]; X.27/X.28 bound it on port 1 and re-plugged a hub)
  and record port 2: the harness's keyboard pad on port 2, with the
  scratch map the recording names, then replays it. **A port-1
  recording (AZ-439)** replays on the keyboard pad bound on port 1:
  `Sandbox(pad_port=1)` (`up`/`serve --pad-port 1`; nothing on port 2).
  **Replay:** a deterministic sandbox (offscreen for a windowed demo, above) on the demo's HDD clone
  (`hdd=`), `sb.adopt_tags(meta["tags"])` (`note_tag`'s meta: each tag's
  disc, the USB pads it holds, the recorded port), `xo.recording_sections(path)`,
  `loadvm(<the section's state>, paused=True)` (it plugs the pad hubs
  the state holds that the machine lacks first: port 2's neutral, the
  demo hub's reading player 1), `play_recording(section, frames,
  port=<the recorded port>, trace=...)` (another port than the keyboard
  pad's is refused; it writes each `+N` line as `@<base+N>`, base the
  paused load's frame, as a pipe `+N` counts from the frame xemu reads
  it at: AZ-510, the fork's PROMPT-9 07; a section past 8 KiB goes a window at a time, AZ-539; on
  v0.16.1 the whole section goes in one `xemu-input-queue` call, then one advance, Step X.61: sitting
  x61c replayed X.30's icount recording from `vanilla-flat` that way onto its 7c2e0f8363b2). A
  section recorded on a build before v0.16.1 that crosses a `system_reset` (a demo's boot of a
  build) replays only with v0.16's reset: `Sandbox(legacy_reset=True)` (`XEMU_NV2A_RESET_IRQ=0`;
  `xo.needs_legacy_reset(<its sandbox's xemu_version>)`); sections that start from a load and
  cross no reset need nothing.
  The port-1 replay (sitting x49, X.36's 4,836-line section on `pad_port=1`): the game's active pad
  went from port 2's to the demo hub's (index 2, reading port 1's binding) at the first input, as
  in the session, and the body moved with it; on port 2 the same section drove index 1 identically. Measured (sitting x30, the keyboard pad standing in for
  the owner's): recorded in real time, 240 vblanks, the replay gives the
  same RAM every time and the player's position, box and velocity
  exactly the session's (one vblank apart in the session's real-time
  trace; the fork measured within 0.001 units over 240 frames); the RAM
  differs from the session's (its guest time followed the host clock).
  Recorded under icount, a replay in another process ends on the same
  128 MiB. Sitting x32d (v0.15, load about 52): three real-time sessions,
  each recording's replays on one RAM (twice x30's 0c11f31659c6); against
  its session the replay was exact on every frame once, a frame apart in a
  few frames once (the end equal), and 0.27 m apart from frame 50 to the
  end once [inferred: that session's guest time followed the loaded host's
  clock, which its recorded pad doesn't hold]; recorded under icount, x30's
  7c2e0f8363b2 in both processes.
- **Keep:** the HDD clone with the demo's states and the recording in
  the private L3 store (never `$EV` or a repo). Next: each section
  replayed headless deterministic (`play_recording`), then in L3; then
  the logic intake (D177/D178).
