# azurik-xemu-oracle reference: driving xemu (§3: QMP, gdbstub, input)

Part of the `azurik-xemu-oracle` skill. Here: the clients, QMP and HMP,
checkpoints, screenshots, frames, RAM, the gdbstub and the input FIFO (the
sitting kit's parts of §3 are in the card). The card, `../SKILL.md`, holds
the rules, the slots and the sitting loop; the § numbers and hazard numbers
are the skill's (Step 2.216 moved this text here word for word).

## 3. Driving it

Drive ad-hoc sessions with the clients in `devkit/xemu/oracle.py`
(`uv run --locked python` from the repo root), passing paths as arguments and
writing output into `$W`:

```bash
uv run --locked python -c "from devkit.xemu.oracle import QMP; print(QMP(sys.argv[1]).hmp('info snapshots'))" "$W/qmp.sock"
# teardown: same, with .execute('quit')
```

**QMP** (`.execute(...)` / `.hmp(...)`): `loadvm` (0.08 s), `savevm`
into the scratch HDD, `info snapshots`, `info usb`, `stop`, `cont`,
`quit`, `pmemsave`, `query-blockstats`, `query-block`,
`blockdev-change-medium`, `system_reset`, and on the fork build
`screendump`, `query-xemu-frame`, `xemu-frame-advance`, `xemu-dump-ram`
and the in-memory checkpoints
`xemu-checkpoint-save`/`-restore`/`-delete` and `query-xemu-checkpoints`
(`sb.checkpoint_save(name)`, `checkpoint_restore(name)`,
`checkpoint_delete(name)`, `checkpoints()`: the whole machine in host
memory, restored as `loadvm` restores, the disk sectors the guest wrote
since put back and a halted guest kept halted, never written to the
qcow2; save 0.016 s, restore 0.014-0.039 s in sitting x30; a relaunch
loses them; a sandbox keeps the newest 8, about 70 MiB each; on v0.15
a restore is incremental, 4.5-5.8 ms against `loadvm`'s 25.5, with
`verify` since Step 2.172f (xemu's dirty log misses some writes: 132
pages after a pilot's retreat left a guest that bugchecked, AZ-821; the
cause, AZ-822, a park's HMP `savevm` leaving the log's store traps
disarmed, is fixed in 0.16.4-3-g95e7ffc7ec, where every verified restore
must miss 0 pages: `checkpoint_restore` counts each one's `pages-missed`
in `st["restores"]`, `down`'s `restores` and the kit report's
`CHECKPOINT RESTORES`, and warns a nonzero there as a fork bug,
Step X.94, drafting its request for the fork at once, Step X.96's
standing rule (the Rules above); never QMP-migrate a running sandbox holding
checkpoints, hazard 19), and
`loadvm` keeps a stopped load as `load-<tag>` and loads the tag again
by restoring it, Step X.32b: `devkit/xemu/README.md`; an HMP `loadvm` drops
every checkpoint but the tag's own load, as it reverts the disk outside
their sector records), and since
v0.15 `query-xemu-display` (a picture's age, below), the PC hooks
`xemu-hooks-set`/`-push`/`-drain`/`-clear` and `xemu-run-until` (they
collect and write guest memory at a PC with no stop; sitting x32's w2
walk through them: 8.6 ms a tick, equal to the gdbstub replay on every
tick; `Sandbox.replay` runs a light replay through them on a
deterministic sandbox, Step X.32b) and `xemu-ram-digest`, and on
v0.16 the access log `xemu-watch-start`/`-drain`/`-stop`
(`sb.watch`, Step X.58; gdbstub, below). A
deterministic sandbox keeps one QMP connection (Step X.32b); a
real-time one connects per command, as a demo's recorder shares it.
Beside QMP each sandbox has an HMP monitor on `$W/hmp.sock`
(`xo.hmp_command(path, "info status")`; Step X.32): it answers while an
advance holds QMP. **No second QMP socket (Step X.58; AZ-644's and
AZ-646's single client):** a second `-qmp` would be a listener of its
own, but QEMU runs every QMP monitor's commands in one dispatcher
coroutine (the fork's `monitor/qmp.c`, `monitor_qmp_dispatcher_co` and
`monitor_qmp_requests_pop_any_with_lock`), and `xemu-frame-advance`,
`xemu-run-until` and `xemu-run` are coroutine commands that run and
yield inside it (`qapi/qmp-dispatch.c` `qmp_dispatch`, `ui/xemu.c`
`qmp_xemu_frame_advance`), so a second socket's commands, its
`qmp_capabilities` too, wait for the advance as the first's do (its
greeting comes; no xemu command is out-of-band). Only HMP answers
meanwhile (sitting X.58's Q2, a sandbox relaunched with a second `-qmp`
in W: during a 4000-frame advance of 11.8 s the second socket greeted
at once and HMP said `running`, but its `qmp_capabilities`, sent 0.5 s
in, was answered as the advance ended). In a real-time demo (no advance) it would end the refused
connects, but a watcher's `stop` and `cont` would still have to keep out
of the harness's own stop-to-load stretch, so `QmpTurn` stays either way.
**v0.16.1's watch monitor (Step X.61, the fork's 51cbd74b46):** every
sandbox on a build with `XEMU_QMP_WATCH` opens one on
`$W/qmp-watch.sock`: its requests run on the main loop outside the
dispatcher, so it answers while an advance holds QMP, but only nine
read-only queries (`query-status`, `query-xemu-frame`,
`query-xemu-status`, `query-xemu-display`, ...; CommandNotFound for the
rest). A long command's wait asks it for the frame (hazard 15, AZ-685);
`xo.QMP(W / xo.WATCH_SOCK)` connects to it by hand (the held connection
doesn't refuse it; it serves one client at a time). Sitting x61b: 27
queries during a held 6,000-frame advance, 0.54 ms at most, the RAM the
same with and without them. Every QMP command carries an `id` and a
reply to another is skipped, and `XEMU_SOCKET_BACKLOG=64` queues a
second client for its greeting where it was refused.
**No fixed
waits on the fork build (Step X.14):** it prints `xemu: ready` on stderr
once the machine and pads exist (0.6 s after the launch in sitting x14;
`loadvm` works from then on) and `xemu: state loaded` after every
`loadvm` (or incoming migration), windowed or headless; the harness's
`await_ready` waits for the first (120 s at most) and its `loadvm` for
the second (30 s), e.g. `.hmp('loadvm vanilla-beach-shield5')` on a
clone of the D98 HDD; load only a tag its README lists (§6). An older
build (the kept one) waits until `info usb` lists the pad (sitting x9:
0.06 s after the gdbstub answered), bounded by s6's 25 s. **v0.15
says the same over QMP (Step X.33, PROMPT-7 N; the fork's 65421d2d3f;
the harness waits on it there, sitting x32):** `query-xemu-status` `{ready, loads}` and
the events `XEMU_READY`, `XEMU_STATE_LOADED {source, name, frame,
loads}` (before the load's reply) and `XEMU_DEVICE_LOST {reason, where,
vk-result}`, the lines kept. Where `query-commands` lists
`query-xemu-status` (`st["xemu_status"]`, once per launch) the harness
waits on QMP, not the log: ready when the query says so or
`XEMU_READY` arrives on that connection, a load when the count goes up.
An older build has none and keeps the lines. `QMP` keeps the events that
arrive on a connection (the last 256, `.events`; `.wait_event(name,
timeout)`).

- **Screenshots: QMP `screendump` only, never HMP's** (HMP holds the
  main lock and could deadlock). `sb.screenshot(name[, dest])` and the
  kit's `s.screenshot(name)` (into the evidence folder's `screens/`)
  write a PNG, windowed or offscreen, also with the guest halted at a
  breakpoint (sitting x14: 0.04 s), but a picture taken halted at the
  player-tick breakpoint shows a frame several ticks stale (sitting
  x275a, AZ-422): for the current frame, `frame_advance` first and take
  it paused on the frame. The null renderer (the deterministic
  default) draws nothing, so they refuse there: a sitting that needs
  pictures runs offscreen (`headless="1"`; sitting x22o: a PNG after a
  `loadvm` on v0.14-12). xemu writes it in `$W` first. **Pictures that
  reproduce** (Step X.26): offscreen deterministic
  (`headless="1", deterministic=True`), the VM paused on a frame
  (`frame_advance`) or halted; a running guest's screendump is refused
  there. RAM hashes there come from `ram_dump` (`gpu-sync` off; `gpu-sync`
  and `pmemsave` write GPU surfaces back, which changes later RAM), and
  match only on the same Mac, macOS and MoltenVK. **A picture's age
  (v0.15, AZ-452):** the screendump waits for the frame's compositor,
  and `screenshot` asks `query-xemu-display` just before it:
  `sb.last_picture` holds `flips`, `flip-frame`, `flip-loads` and
  `loads`, and `stale` is True, with an event, while the guest hasn't
  flipped since the last load (the picture is then the loaded state's
  own saved frame: advance until it flips). Azurik presents every 3
  vblanks, so a right picture can be 1-3 frames old and one-frame steps
  repeat a picture. Sitting x32: 32 pictures over 4 loads, one per
  one-frame advance, none equal to the one before across a flip or a
  load, the first fresh 1-2 frames after each load; the soak's 92
  pictures none stale. **Older builds** (v0.14-36 and before) could give
  the previous screendump's picture with no sign: retake a picture whose
  bytes equal the last one's after the world ran, a few vblanks on, and
  name it stale if it stays (sitting 2.75b S2's rule). **v0.16.1 dates it
  by `picture-stale` (Step X.61, AZ-668):** true until a GPU write into the
  buffer on screen counts since the last load *or checkpoint restore*
  (Azurik writes the same scanout every vblank, so after a restore
  `flip-loads` said fresh while the picture was the loaded RAM's frame:
  2.155c's chained A/B pairs). `screenshot` reads it where the reply has
  it: a deterministic sandbox, or any whose VM isn't running (paused, or
  halted after a load), advances one vblank at a time until it is fresh
  (12 at most; `last_picture["advanced"]`, an event: a caller counting
  frames adds them, as `model_kit`'s `pic` does), a running real-time one
  polls it for a second, and one still stale raises. So a
  chained A/B across `checkpoint_restore` is fine again (no need to take
  each picture in its own run). Sitting x61c: fresh 4 vblanks after a
  load and after a restore; restore, advance 3, picture: 1 more, the same
  picture as the restore's own 4, twice. **Pictures on null's RAM
  (v0.16.1):** `Sandbox(headless="1", deterministic=True, null_ram=True)`
  (the kit's `Sitting(..., null_ram=True)`) runs offscreen with
  `XEMU_RENDER_NULL_RAM=request`: nothing is drawn and guest RAM is the
  null renderer's until `screenshot` asks `xemu-render-next {"flips": 2}`
  (it runs the VM until 2 frames are drawn and on screen, then pauses;
  `last_picture`'s `render_flips` and `render_frames`; fewer in its
  120-vblank cap raises), so picture and number rows share one sandbox
  at about null's cost (the fork: +4.5 % a frame against +61-66 %
  drawing). Sitting x61c: X.24's string from `vanilla-flat` ended on
  null's bd3a78e10f11 there (plain offscreen: 742be81e07bb), a picture
  drew its 2 frames in 6 vblanks, and the RAM after them equalled a null
  run of the same frames. Not the default: existing offscreen rows keep
  their plain-offscreen baselines; render targets and blits earlier
  frames would have drawn are missing from the first frame drawn (as
  under null), so a first fx use checks one picture pair against plain
  offscreen. For a few pictures of a
  long null run, the fork's cheaper recipe: `savevm` at the frame, load
  it in a short offscreen deterministic run, advance a few frames,
  `screendump` (before v0.15, one `loadvm` per offscreen process: §2's
  repeated loads). Screendumps are images of the game: evidence only, never
  committed or printed.
- **Frames (fork build):** `sb.frame()` (QMP `query-xemu-frame`:
  `{frame, running}`, vblanks while the VM ran) and
  `sb.frame_advance(n)` (`xemu-frame-advance`: n vblanks, then paused;
  QMP `cont` resumes; it lets go of the gdbstub first). Deterministic, it
  stops on the vblank itself, also from `-S`. **From a halt:**
  a guest the gdbstub holds (a parked start) starts from that very
  instruction: `frame_advance` lifts the breakpoints and lets go of the
  gdbstub without a continue (`st["debug_advance"]`), so no guest time
  passes on the host clock first (x30: three unparks, then 120 vblanks,
  the same RAM); a breakpoint hit during an advance ends it with
  `debug-stop`. **Per-frame traces:** `frame_advance(n,
  trace=[{"address", "size", "virtual"}], every=K)` also returns
  `trace`, the hex bytes of up to 256 regions of 1-4096 B at every Kth
  vblank (the last always), read before the guest sees it; exact under
  icount (in real time the vCPU may be mid-update: x30's real-time trace
  ran one vblank behind the same run's replay). Not yet used by the
  chain's replay comparison, which still reads per tick by gdbstub.
  **GPU work (v0.16.1, Step X.61):** `frame_advance(n, gpu=True)` (or
  `gpu="per-flip"`) counts the advance's NV2A work in PGRAPH's method
  path (the same under null and Vulkan; RAM unchanged) and returns it as
  `gpu-counters` (`flips`, `total`, `max`: each of 44 counts' heaviest
  flip, `tail`); `xo.gpu_budget(counters)` sets its `max` against
  `GPU_CEILING`, vanilla's heaviest flip in the fork's four pack-03
  heavy scenes (sitting x61's g01, every RAM hash the fork's: 347
  begin/end pairs in e7's fight, 213,262 triangles and 1,024,084
  pushbuffer bytes in `vanilla-rz-new`; `vanilla-ig-a1`'s base frame 48
  pairs, 95 triangles, 1 clear): per counter the build's max, vanilla's,
  the ratio and `over`. `GPU_CEILING` is no upper bound (sitting x61:
  vanilla booted at `vanilla-ig-a1`, 600 vblanks, went over it in 7 of
  10 counts, 1.25-2.03x; booblord there 0.84-1.0002x its control: 72
  vertices and 24 triangles over it, which `over`, `ratio > 1`, flags,
  so read the ratios). **The frame's cost (Step 2.173; the owner's D603,
  "measure and warn, never refuse", and D604):** every model or pack
  sitting whose build changes what is drawn (a body, a variant,
  textures, fx, a level pack) runs `model_kit`'s `row_cost` on the
  vanilla disc and then on its build with `control=` that row: a1, w1
  and e2 by the warp, idle, turn, run_stop and attack phases of 300
  vblanks each, per-flip counters (`xo.frame_cost`: the first, partial
  flip dropped, steady max/p95/median by kind; a scene's whole-advance
  max can miss the body: x61's vanilla and booblord a1 maxima had the
  same vertex and surface bytes). `xo.frame_warning` puts L1 lines in
  the row's `warn` (a steady flip past `GPU_CEILING` raised by the
  control's scenes, times `BOOT_NOISE` however many controls: two
  cold vanilla boots differ by up to 1.13x, a warm one not at all),
  which the REPORT's WARNINGS block lists; where L1
  fires, a real-time offscreen sitting runs `rate_pairs` on the row's
  `heaviest` scene (3 alternated control-then-build fresh processes,
  the NV2A counters off: Step X.68, the fork's reply on
  FRAME-8bffffeb0243, whose counted arms held up to about half the
  build's frame in counter calls; flips by query-xemu-display's
  `frame-ends` where the binary has it (v0.16.3, Step X.69: a running
  total since the process's launch that no load, restore or reset
  clears, so a difference within one process; an arm across a relaunch
  counts none), else the game's present counter (the fork: the two
  agree); the det cost rows keep the counters)
  and `rate_verdict` judges L3: a drop below vanilla's flips a vblank
  in all 3 pairs by more than max(3 %, the vanilla-vs-vanilla spread)
  warns and drafts the fork's prompt into
  `xemu-fork-requests-<date>/FRAME-<sha12>-<level>-<phase>.txt` in `$EV`
  for the owner to relay (D604); counted pairs (before X.68) are
  inconclusive. Every draft states, for the rate arms and the count
  row, the xemu binary's sha256[:12], the load (state tag and drive,
  or a cold boot's recipe: a driver's own boot sets its `load`) and
  whether the scene was reached by warp or by the state (the fork's
  item 7). Never a refusal: the step's report
  and its skeptic carry the lines, the owner decides. Icount's counts
  are exact but hide the host's cost; only a real-time pair is the
  owner's frame rate. **vblank-ns:**
  v0.16.1's frame replies carry the vblank period (`st["vblank_ns"]`,
  16,666,666; 20,000,000 under its opt-in PAL `[sys] vblank_rate`, not
  taken yet); `sb.guest_s(frames)` converts with it.
- **Dumping guest RAM:** `sb.ram_dump(path)` (Step X.22): QMP
  `xemu-dump-ram` (one write of all 128 MiB, 18-42 ms in sitting x22;
  byte-identical to `pmemsave`, which a build without it gets) into a
  file the harness creates mode 0600 in `$W` (xemu's own would be 0644),
  with `gpu-sync` off so a dump never writes guest RAM; the VM is paused
  for it (a halted guest stays halted). L3 snapshots take every page from
  one (§4.7's chains, `docs/SIMULATOR.md`). To find bytes, match whole 4
  KiB pages against the file you expect; a VA scan misses most of RAM
  (the kernel doesn't map all of it at 0x80000000). Delete the dump in a
  `finally` (hazard 7).
- **Guest RAM in shared memory (Step X.31a):** on a build with
  `XEMU_RAM_SHM` (the fork build) each sandbox launches with its own name
  (`ram_shm_name(W)`, `st["ram_shm"]`; a name is global to the machine).
  With the guest halted, `sb.read` (so `capture`'s and `replay`'s
  per-tick reads, `chain`, `pad` and the kit's reads) reads it there
  with no packet: each page through the guest's page tables from CR3
  (`l3.ram_reader`, as the demo recorder walks them), checked once per
  gdbstub connection against the gdbstub's view of the page directory,
  a page past RAM through the gdbstub; else, or if the check fails,
  through the gdbstub. `sb.ram_sha256()` hashes the stopped VM's RAM
  there with no file (else a dump, deleted at once); the sittings'
  baselines are its sha256[:12]. `sb.ram_digest()` (v0.15, Step X.32b)
  asks xemu itself (`xemu-ram-digest`): XXH3-128 in about 4 ms, to tell
  runs of one sitting apart. `down` removes the
  object a killed xemu leaves (it holds console keys).
- **`query-blockstats`** gives per-drive byte counters (DVD, HDD): the
  re-copy check of hazard 8 and the frozen-boot check of hazard 9.
- **Never load the four July `vm-20260704…` tags** (hazard 1); they are
  only on the old drive in `$FX/backup-2026-10-11/` and on the owner's
  own HDD. List an HDD's tags offline on a clone, never in place:
  `cp -c "$FX/xbox_hdd.qcow2" "$W/list.qcow2"`, then the fork's
  `$XEMU_FORK/scripts/list_snapshots.py "$W/list.qcow2"`.

**gdbstub (GDB RSP, i386).** `devkit/xemu/oracle.py`'s `RSP(port)`:
`.read(va,n)`, `.write(va,bytes)`, `.u32`, `.regs()`, `.set_bp(va)` /
`.clear_bp(va)` (software `Z0`/`z0` only), `.cont()`,
`.wait_stop(timeout)` (raises `TimeoutError`), `.interrupt()`,
`.cmd(packet)`; module `arm(g, vas)` (`?`, then `Z0`; before v0.15
also an identical-byte rewrite, as older builds didn't re-translate code
already translated before a `Z0`) and `resume(g, vas[, pc])` (on v0.15
a plain `c`: the client turns on `Qxemu.stepover` where the stub offers
it, `g.stepover`, and the stub runs the instruction under the PC; older
stubs lift only the breakpoint under the PC: `z0`, `s`, `Z0`, `c`;
Steps X.31a, X.32b). `.read_many(regions)` reads several regions in one
`qxemu.read` where the stub offers it (`g.xread`), as `.read` does a
read's page pieces.
The archived `oracle.py` copies take a kind argument
that defaults to `1` (hardware): pass `0`. Reads ≈ 11.5 MB/s.

- **Attaching halts the guest.** Socket close doesn't resume it: `cont`
  or `D` first; QMP `cont` recovers.
- Attached right at launch, kernel addresses read `E14` for about 1 s:
  poll with `cont`/`interrupt` until they read.
- **A script that dies at a breakpoint leaves it armed:** the guest halts
  at the next hit and `interrupt()` hangs. Recover with a fresh `RSP()`,
  `cmd('?')` (it clears every breakpoint), `cont()`.
- **Kernel file-op tracing** works through the guest's thunk table. On
  this BIOS (Complex 4627): `NtCreateFile` 0x8001694D, `NtOpenFile`
  0x80016976, `NtQueryFullAttributesFile` 0x80016A09, `NtReadFile`
  0x80017467, `NtWriteFile` 0x80017828. Leave `NtReadFile` out: a
  breakpoint there slows the boot about 25×.
- `?` deletes every breakpoint; `Z0` stacks duplicates; a stub without
  step-over doesn't step over the breakpoint under the PC (`resume()`
  does `z0`→`s`→`Z0`→`c` for that one only; v0.15's, with step-over on,
  runs it on a plain `c`).
- Any byte sent while the guest runs stops it. Clean exit:
  `g.interrupt(); g.cmd("?"); g.cont(); g.s.close()`.
- The fork build answers an `m` of up to 4 MiB (and a
  binary `x`); the harness keeps 2 KiB reads for registers and small
  reads, and bulk RAM goes through `ram_dump` (or shared memory, §3).
- `regs()` returns the 16 integer registers plus `fctrl`, the x87 control
  word at byte 180 of this fork's 344-byte 'g' packet (0x023F in every
  vanilla dump).
- **Watchpoints work on v0.16** (the fork's fix 32b1ddf856; Step X.58
  lifted the old ban, under which `Z2`-`Z4` wedged the vCPU with QMP and
  the gdbstub silent: never set one on the kept build). X.58 checked a
  `Z2` under icount on the null renderer; `Z3`, `Z4` and real time rest
  on the fork's fix. Sitting X.58's
  W-b from `vanilla-flat`: `g.cmd(b"Z2,%x,8" % (ent + 0x18))`, `g.cont()`,
  `g.wait_stop(t)` stopped in 0.01 s (`T05`, `watch:` the field, EIP
  0xab8a4 after the store at 0xab8a1), QMP `query-status` `debug` and
  HMP `paused (debug)` answering at once; a second `c` reached the next
  store (0xab8a7); then `z2`, `?` and a 60-frame advance (0.19 s). Clear
  them (`z2`, `?`) before handing the guest back. For who touches a
  field with no stop, `sb.watch(ranges)` over `xemu-watch-*` (every load
  or store that overlaps up to 64 ranges, the game's VAs and writes by
  default, with its frame, pc, address, size and value; `with
  sb.watch([(ent + 0x18, 8)]) as w: sb.frame_advance(300)`, then
  `w.hits`; never print a hit's `value` raw). X.58's W-a: 300 frames,
  298 hits, the two dword stores from pc 0xab8a1 and 0xab8a4 on each of
  149 ticks, 0 dropped, every frame's traced value among them, the RAM
  digest the same with and without it (0.86 s against 1.02 s); after
  `stop` a drain is refused and a 60-frame advance returns.
- `RSP.read` and `.write` refuse the GPU's register window
  0xFD000000-0xFDFFFFFF before sending a packet (AZ-308: a stray read of
  NV_USER aborted xemu; the fork's write path still asserts).
- The fork build answers an `m` that runs into an unmapped page with the
  readable prefix (the old one: `E14`); `RSP.read` reads page by page and
  raises on a short reply, so no read comes back short.

**Input (keyboard pad, port 2).** Write `down <sc>`, `up <sc>` or `clear`
lines to the FIFO; open/write/close per line works, unfocused. `<sc>` is
the SDL scancode of the *keyboard key* bound to a pad button: read it
from the **scratch** toml every session. Method owner: fork skill
`xemu-testing` ("Background input injection").

```bash
uv run --locked python -I -c "import sys,tomllib; print(tomllib.load(open(sys.argv[1],'rb'))['input']['keyboard_controller_scancode_map'][sys.argv[2]])" "$W/xemu.toml" y
```

- Jump is **Y**: 235 in the scratch map; **A** gives state `0x100`.
- **Menus: confirm checkpoints; fixed delays alone fail** (the title can
  ignore START, START can fail to skip the movie). The boot state machine
  0x5F620 (`docs/RE_XBE.md` § "Boot state machine") calls `play_movie_fn`
  in state 3, which returns to **0x5F748 at once** (the movie only
  started); state 4 reaches **0x5F774** when the movie ends.
  prophecy.bik lasts 90 s. Start New Game runs the inventory reset
  **0x57B70**, but so do 6 other call sites and the save list's preview
  of a save: a hit doesn't mean a new game. **A new game is the level it
  loads:** `load_level_from_path` **0x53750** (stdcall, `[esp+8]` = the
  path) gets `levels/training_room`; movies come through it as `bink:`
  paths. **The boot state [0x1BF61C]** (`docs/RE_XBE.md`) tells the
  menus apart (sitting x9): 4 during prophecy.bik, 6 at the title (0.26 s
  after the movie ends; never 7), 8 once START opened the save list (at
  once), 9 in game. **A deterministic sandbox walks this on guest frames
  (Step X.64, §6's `boot_frames`);** the wall-clock walk, kept for a
  real-time one, is: `jump` and `boot-build` hold each press 0.5 s: START
  until 0x5F774 breaks (up to 120 s); then START once the state is 6
  (again after 2 s while it stays 6), dpad-left (`jump`) and, once it is
  8, A once the list previewed SaveGame #1 (its inventory reset 0x57B70,
  armed before START). **The list then reads the HDD for 5-25 s and takes
  A only when done** (an earlier A waits; a second A meanwhile delayed or
  lost the load), so A goes once, again only after 25 s with no
  checkpoint; letting `bink:` loads pass,
  until 0x53750 loads a level (another level fails by name; a miss
  presses B twice and retries, 3 tries); then A whenever 0x8CCC0 doesn't
  run at a poll (0.5 s apart) until it ran at every poll over 8 s of the
  player's event clock (+0x18). On the D98 HDD the save list opens on
  SaveGame #1 with Start New Game one dpad-left away and SaveGame #2
  (the new-game character) one dpad-right away. **The list drops a
  cursor move while it reads the HDD** (AZ-354), so `boot-build --save
  2` presses dpad-right again every 3 s until the list previews #2 (the
  inventory reset again, from 0x1C6A9), then A. A bare `c` after `?` at
  a breakpoint stops there again on this fork: step off it (`s`) first,
  as `resume` does, or the next armed wait reports the old stop.
- A press lands 2–4 ticks after the write: align traces on the state
  change, not the send time. In a tick-locked capture a `down` written
  while halted at row k shows in ControllerState at row k + 1, tick k + 1
  acts on it, and the state change shows at row k + 2; an `up` at k
  usually shows at k + 1. Row k's entity fields hold tick k − 1's result.
- With the window focused, real keystrokes are OR'd in; the scratch map's
  scancodes 232–256 keep them off the pad.
- **Analog and frame-tagged lines (fork build, Step X.14):** `axis
  lx|ly|rx|ry <-1..1>` and `trigger lt|rt <0..1>` (positive right/up;
  `0` hands the axis back to the keys; `clear` resets them too: X.31a's
  row c saw it release LT by the third frame, as a press
  shows, so r21a's held trigger (AZ-390, refuted) was likely read too
  soon [inferred]),
  each
  line optionally prefixed `@N ` (at frame N) or `+N ` (N frames from
  the frame xemu reads it at: hazard 13). `sb.axis(name, v, at=|after=)`,
  `sb.send(line, at=|after=)`; a capture schedule takes
  `axis <name> <v>` / `trigger <name> <v>`. The value is the raw axis
  over 32767, so `xo.pipe_axis(f)` gives the value for a
  ControllerState float past the game's ±12000 dead zone. In real
  time a frame-tagged line lands within a frame or two (the game's work
  per vblank follows host speed); deterministic (§2), a line written
  while the VM is paused, then `frame_advance`d, lands at its frame
  exactly, and an untagged one at the next vblank. Exact replays keep
  `write_pad` at the input builder (D184).
- QMP `input-send-event`: untested, inferred not to drive the pad.
- **Level 1:** a new game starts in the Training Arena; walk through the
  arch and press X at the door. Its start is deterministic,
  (76.5324, 18.1752, −0.7266), and jumps and rolls from it are
  bit-identical.
- **Dialogs and cutscenes stop the player tick** (0x8CCC0 never hits). A
  state saved at the level-1 start gives about 2–3 s of control after
  `loadvm`: start a capture within 0.3–1 s of `loadvm`.
