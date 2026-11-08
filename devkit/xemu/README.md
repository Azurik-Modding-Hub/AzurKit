# devkit xemu: the in-game oracle (dev only)

xemu is AzurKit's in-game oracle (D601): sandboxed copies of the owner's
macOS xemu fork, never the owner's own xemu, never a visible window but an
owner demo's, at volume 0 (D108). Its verb:

```bash
uv run --locked python -m devkit xemu oracle CMD [ARGS ...]   # the harness (below); also python -m devkit.xemu.oracle
```

- `oracle.py`: the harness (Step 4.14a2, Modkit's `scripts/xemu_oracle.py`
  ported): its sandboxes, slots, QMP, gdbstub and pad, its boots and
  captures, and its offline `selftest`.
- `shim_ranges.py`: the data a build's shims write while the game runs
  (the player-model shims', AZ-300; the copy gate's, AZ-817), read from
  the build, which `boot-build`'s code check leaves out.
- `queue.py` and `warm.py` (Step 4.14a1): the sittings' first-come tickets
  and the batch token that gives way to them; a sitting's warm build
  states.

The sitting kit, its model checks, the owner demos' recorder and the
`azurik-xemu-oracle` skill come with Step 4.14a3; the chain, route and
minigame sittings with the reach engine. Until then the sittings run
Modkit's kit; both harnesses share the slots folder, the owner-demo lease
and the private store, so they keep one D108 budget.

## The harness: `python -m devkit xemu oracle`
Dev-only ground truth from the owner's macOS xemu fork (REORG_PLAN
Step 2.11, D11): sandboxed copies of xemu, driven over the gdbstub,
QMP and the fork's input FIFO. Since Step 2.20l it is also agent
session s6's harness (sandboxes on the oracle's save states,
tick-locked captures, the modded-build path; it was s6's own
library), and its sandboxes take slots admitted by free cores (D108,
D263). It is devkit's: nothing under `src/azurkit` imports it
(`tests/test_contracts.py`), and pytest runs only its offline `selftest`
(`tests/test_xemu_harness.py`, marked `xemu`, which CI's Linux and Windows
legs deselect). macOS only; the standard library, `platformdirs` and
AzurKit's core and facts.

It clones the oracle's own fixtures (D98) in the folder
`AZURIK_XEMU_FIXTURES` names, else the user data folder's `xemu-fixtures`
(a link to them; they live outside every checkout, `devkit/README.md`):
their `xemu.toml` names the HDD, EEPROM, boot ROM and BIOS it clones,
and it refuses one outside that folder. No measurement runs on its
files in place; agents may maintain the folder (D100), and new save
states are made on a clone, checked, then moved in (its `README.md`
lists them; its `SHA256SUMS.txt` holds each file's sha256). It never
clones or launches from the owner's own xemu files (`OWNER_XEMU`,
xemu's pref dir, which it only lists) or from the xemu fork's own
fixtures (set up for a modded disc);
never point `AZURIK_XEMU_FIXTURES` at either (D98).
`AZURIK_XEMU_HDD=<qcow2>` clones that HDD instead: an agent's private
drive of `vanilla-rzp-*` states (Q250), never one of the owner's own
xemu files. Every sandbox (`up`, `jump`, the kit) clones the fork build
kept in the fixtures folder as `xemu-v0.16.4-3-g95e7ffc7ec.app` (Steps
X.14, X.22, X.26, X.30, X.32, X.40, X.43, X.61, X.66, X.71, X.72, X.94;
D184, D894: the owner's local PGO arm64 build three commits past the
fork's v0.16.4, binary sha256[:12] `eb749faf0807`: the
headless mode, the readiness lines, QMP `screendump` and frame stepping,
analog and frame-tagged pipe input, the USB crash fix, the deterministic
`-icount` fast-forward, QMP `xemu-dump-ram`, the Vulkan freed-surface fix,
deterministic offscreen pictures, since v0.14-36 icount saves that carry
what a continued run depends on, in-memory checkpoints, per-frame traces,
frame-advance from a gdbstub stop and input recording, and since v0.15
`query-xemu-status`, `XEMU_BASE_PATH`, an advance that ends on any stop,
dated screendumps, PC hooks and `xemu-run-until`, a failed Vulkan call
that exits, a socket path no second listener takes, and x87 NaN payloads
kept (sitting x32: the same guest RAM as v0.14-12 to v0.14-36 in 29 of
the 32 D98 states' runs, the other 3 two words apart for that reason,
`docs/RE_XBE.md`), and since v0.15.1 null-renderer runs that get the
scheduling they ask for on a loaded Mac (faster, the same RAM), offscreen
pictures whose rounding can differ from v0.15's by a few pixels, and no
GLib assertion at a QMP quit (sitting x40: every D98 hash, the pipe,
`vanilla-exit` and the offscreen check as on v0.15), and since v0.16 an
opt-in KosmicKrisp Vulkan driver (MoltenVK stays the default), fewer
pipeline compiles and faster offscreen Vulkan, with the same guest RAM
(sitting x43: every D98 hash, the pipe, `vanilla-exit`, the parks, the
offscreen check and the gdbstub features as on v0.15.1, and 51 L3
conformance records replayed on their recorded xemu digests), and since
v0.16.1 the QMP watch monitor, a listen backlog, the guest bugcheck
report, `picture-stale`, `XEMU_RENDER_NULL_RAM`, `xemu-input-queue`, NV2A
workload counters, `vblank-ns`, a bounded windowed present, RAM above 128
MiB and the reset and OHCI fixes (sitting x61:
every hash and check x43 took on v0.16, the same 51 records, and the
offscreen pictures and RAM unchanged), and since v0.16.2 28-bit NV2A DMA
addresses whenever guest RAM is 256 MiB or more (its init line; a launch
above 128 MiB records the bits, `nv2a_bits`; sitting x66:
every value x61 took, at 128 MiB),
and since v0.16.3 a disc or USB DMA that writes a dirty GPU surface back
first (AZ-708's bugcheck after a fast level load in real time),
`query-xemu-display`'s `frame-ends`, shader prewarm lists and half the
memory (sitting x71), and since v0.16.4 a GPU
command thread that fuses register and vertex commands (its opt-out
`XEMU_PFIFO_FUSE=0` never inherited), the shader prewarm on up to 4
workers and a DSP frame that never ends cut off, with the same guest RAM
(sitting x72), and since 0.16.4-3-g95e7ffc7ec
a park's `savevm` that re-arms the checkpoints' dirty log (AZ-822: a
verified restore after it finds no page missed), the bugcheck event's
registers and stack and `timeout-ms` on the advances and runs
(sitting x94);
the D98 states load in it, and a state it saves loads in v0.16.1 to
v0.16.4 and back [inferred: no device section changed v0.16.2 to
0.16.4-3] but not in v0.16 or the kept build (v0.16.1 made the
NV2A's device section version 5; `state_stream`). v0.16.4's release
copy, `xemu-v0.16.4.app`, stays in the folder while the lanes that run
it end (`--app` its path; v0.16.3's to v0.16's are retired, D678,
D683). `--app kept`
(`Sandbox(app="kept")`, a spec's `app = "kept"`) clones the build that
made the D98 states, `xemu-v0.13.3-37-gd5ad94f4bf.app`, the fallback
should a state refuse the fork build, and `--app PATH` any bundle. An
app named `xemu-v<version>.app` must log that version (a tag's build logs
the bare version: `xemu_version: 0.16.2`). A disc inside the
fixtures folder boots only if it passes the vanilla identity check, so
the folder's `vanilla.iso` (a sandbox's default disc) boots and a
modded disc there is refused.
Every launch (`up`, `relaunch`) checks the guest RAM size its argv's
`-m` and its two `xemu.toml`s' `[sys] mem_limit` ask for before xemu
starts (`ram_refusal`, Step X.60) and refuses, by name and with the
reason, one the build can't run: a size at or below 128 MiB that isn't
a power of two (NV2A BAR1 aliases all guest RAM and `pci_register_bar`
asserts a power-of-two BAR, so xemu aborts with SIGABRT from
`nv2a_init`), one below 64 MiB (the flash's kernel is built for 64),
one above 128 MiB on a build without the fork's experimental large RAM
(`5f105ce472`, from v0.16.1; `BIG_RAM_MARK`: v0.16 and the kept build
lack it) or, on one with it, not a multiple of 16 MiB up to 3840, and
a `mem_limit` outside the build's values (`'64'`, `'128'`; `'256'`,
`'512'` with the large RAM), which xemu would ignore for its default
64 MiB. The D98 states are 128 MiB machines (`mem_limit '128'`, the
fixtures' config); a savestate loads only on a machine of its size.
Its guest VAs (the player tick and its return address, `player_jump_init`,
the pad state, the boot checkpoints, `SCENE_PTR`) are USA's; a sandbox
takes them to its disc's release through that release's address map
(`use_release`, Step RG.5), so a Europe disc's sandbox breaks at
Europe's own addresses, and `boot-build` refuses a build of another
release than the disc's (its save states are that release's).

```bash
uv run --locked python -m devkit xemu oracle selftest                  # offline checks: no xemu, no fixtures
uv run --locked python -m devkit xemu oracle slots                     # the running sandboxes; may a new one start now?
uv run --locked python -m devkit xemu oracle jump --ticks 30           # deterministic; vanilla prints v0 = 4.6433 m/s
uv run --locked python -m devkit xemu oracle jump --iso <build>.iso --ticks 30   # a build made from vanilla
uv run --locked python -m devkit xemu oracle up <group> [--out DIR] [--headless null|1|0 | --window] [--deterministic] [--app fork|kept|PATH] [--record PORT] [--owner-pad PORT] [--pad-port PORT]
                                                                        # prints {"W": ..., "gdb_port": ...}; xemu keeps running
uv run --locked python -m devkit xemu oracle loadvm <W> vanilla-flat [--disc NAME]   # prints the first player tick's row
uv run --locked python -m devkit xemu oracle status <W>                # alive, QMP status, one player-tick row
uv run --locked python -m devkit xemu oracle press <W> a 0.5           # a wall-clock press, the guest running
uv run --locked python -m devkit xemu oracle savevm <W> <tag>          # a checkpoint into W's HDD clone only (deterministic: savevm alone)
uv run --locked python -m devkit xemu oracle hmp <W> 'info snapshots'  # not loadvm, savevm or delvm
uv run --locked python -m devkit xemu oracle boot-build <W> <build.iso> [--tag vanilla-ig-w1] [--save N] [--a-frame N] [--wait S]
uv run --locked python -m devkit xemu oracle relaunch <W> [--wait S]   # after xemu died (the skill's hazard 10); keeps its slot; loadvm again
uv run --locked python -m devkit xemu oracle snapshot <W> <label> [--scene] [--hold] [--store DIR]   # an L3 snapshot
uv run --locked python -m devkit xemu oracle replay <W> <label> <inputs.json> [--scene] [--store DIR] # L3, then xemu
uv run --locked python -m devkit xemu oracle down <W> [--keep]         # exit 1 on an incident
uv run --locked python -m devkit xemu oracle tags                      # the oracle tags
```

**Slots (D108, Q258; D174, D263).** A new sandbox (`up`, `jump`, `relaunch`, and
`boot-build`'s relaunch before a retry) starts only while:
- no sitting that asked earlier still waits (Step X.8): each takes a
  numbered ticket in `/tmp/azx-xemu-slots/queue/` and they start in
  ticket order, not by who checks first after cores come free; a
  waiter renews its ticket at every check, and a ticket whose process
  is gone or that went unrenewed for 2 minutes is removed;
- no other sandbox is launching (`/tmp/azx-xemu-slots/launch.lock`);
- no xemu runs but sandboxes: an xemu whose app isn't in a `/tmp/azx-*`
  folder is the owner's or someone's own copy, unless its command holds
  `-name xemu-fork-auto`: that is the fork's automation (D248), which
  counts only through the cores it uses, and `slots` lists it as
  `fork_auto_xemus`;
- an owner demo that runs lets it start beside it (Step X.37, PROMPT-8
  F(2); D526, the owner, 2026-10-22: "Yes, background priority"): while
  `/tmp/xemu-leases/owner-demo.json` names a live pid (`slots` shows it
  as `owner_demo`), a window of ours waits (a relaunch keeping its slot
  too), as the fork's launchers wait; a headless sandbox (null or
  offscreen) starts beside it at macOS background priority while fewer
  than the demo's budget of ours run there (`xemu_queue.demo_budget()`:
  the efficiency cores, 8 on this M2 Ultra, where macOS runs background
  work on Apple silicon [inferred: a background process ran 0.44x the
  work per CPU second of a normal one, Step X.59], so the demo keeps the
  performance cores; the demo's own xemu isn't counted) and the rule
  below admits it; a
  relaunch keeping its slot starts at once. Such a launch is set to
  background priority right after it starts (`setpriority`'s
  `PRIO_DARWIN_BG` from the launcher, what `taskpolicy -b -p` does: every
  thread at priority 4 and throttled disk I/O; its event says so), and
  every sandbox of ours that ran before the demo moves there too: at our
  demo's start, at each admitted launch and at `slots` (for a demo of the
  fork's or the owner's). The demo's end (our demo's, or the next launch
  or `slots` after one that ended otherwise) takes them all back out. The
  demo's own xemu (the file's pid, or a sandbox whose `sandbox.json` names
  an `owner_pad`) and its watchers are never touched. Guest time under
  `-icount` doesn't follow the host, so a deterministic run gives the
  same RAM at either priority (sitting X.59: `vanilla-flat`'s 600-frame
  advance on one digest at both), but slower: 203 s against 2.04 s at
  load about 105; since Step X.61 an advance on v0.16.1 waits as long as
  the guest's frame moves, AZ-685, below). `slots` adds
  `demo_budget` and `background_pids` while a demo runs. An owner demo's
  launch waits for none, nor, while one runs, for the earlier tickets
  that wait for it, and no other launch waits behind a ticket held only
  for the demo's end (a window of ours, or any launch of an older
  harness): those are first again once it ends. An owner demo (`--owner-pad`) writes that file right
  after its xemu starts (`{"pid": <its xemu>, "who": "azurik-modkit",
  "purpose": <its group>}`, a temp file renamed into place) and removes
  it once that xemu is gone, only while the file still names that pid:
  a thread of the launching process waits for the xemu (an exited xemu
  left unreaped is a zombie, which the fork's launchers count as
  running), and so do `down`, a failed launch and a death the harness
  sees. A record of ours whose pid is no xemu (a zombie, or a pid
  reused after a CLI `up`'s demo ended with no `down`) counts as no
  demo, and the next launch or `slots` removes it. A demo's relaunch
  (`boot-build`'s retries, the model kit's fresh process) keeps it
  (AZ-601): before the quit it names the relaunching process with
  `relaunch_of` the old xemu, which counts while that pid runs the
  command it recorded (`relaunch_cmd`: a reused pid is none), and
  the new xemu's launch replaces it; a relaunch that never launches, and
  `down`, remove it. An agent sandbox never writes the file;
- at least 30 GiB of disk is free on the sandbox's volume
  (`MIN_FREE_DISK`, Step X.65b): a sitting takes 10-27 GiB as its disk
  image and pictures grow, so it never fills the disk mid-sitting;
- fewer than two sandboxes run (two may always run, whatever the load:
  D174, amending D108's one), or all of these hold:
  - no full test suite runs: nothing holds `/tmp/az-fullsuite.lock`,
    which agents' full runs take with `lockf -k` (the first two
    sandboxes aren't held back by it: suites queue on the lock);
  - at least 4 CPU cores are free (D263, amending D174's load test on
    the fork's advice): the CPU count times the share of CPU time idle
    over 1 s (mach `host_statistics`, `HOST_CPU_LOAD_INFO`, two samples;
    niced time counts as busy), not the load average, which held a third
    sandbox back at 16 while most of the cores were free. Four is one
    for the new xemu (each uses about one) and three to spare
    (`MIN_FREE_CORES`). Where the call fails (not macOS) the old test
    decides, and the verdict says so: the 1- and 5-minute load averages
    both below two-thirds of the CPU count;
  - at least 8 GiB of RAM is free (`vm_stat`'s free and speculative
    pages).

A running sandbox is an xemu whose app is in a `/tmp/azx-*` folder
or a registered slot whose process still runs; a
slot held with no xemu running (launching, or kept, below) counts as one
too.

It checks every 5 s for `--wait` seconds (default 240; each of those
four commands takes it, and `Sandbox.attach(W, wait_s=...)` in Python),
printing why it waits, then stops with `STOP: <why>` having started
nothing (its ticket goes either way). `slots` lists the queue. There is no fixed cap, and no running sandbox is ever stopped
for load. Each
sandbox has its own gdb port and QMP socket (`$W/qmp.sock`), recorded
with its W and pid in `/tmp/azx-xemu-slots/<W name>.json` until `down`.
That slot has a lease (Step X.8), the file's mtime: its launch, every
command that attaches to its W and every check that sees its xemu run
renew it. When its xemu stops without `down` (a crash, or `boot-build`'s
quit before a relaunch) the slot is kept for 10 minutes after its last
renewal, then reclaimed: the file is removed and `$W` left alone. A slot
whose launcher died before its xemu started is reclaimed at once.
`slots` shows each slot's state (`running`, `launching`, or `kept` with
its seconds left), the batch jobs giving way, the cores free now
(`free_cores`, measured over 1 s, beside `cpus` and `min_free_cores`),
`free_ram_gib` and the verdict.

**Batch jobs give way (Step X.8).** The CPU that kept sittings waiting
went mostly to batch jobs no rule schedules, and niced CPU time counts
as busy. So the CPU-heavy
batch jobs (`rando derive` with `-j`, `rando_soak.py`, `rando_impact.py`;
the L3 search pools once Step X.7 lands) take a token,
`devkit/xemu/queue.py`'s `BatchToken` (`/tmp/azx-xemu-slots/batch/<pid>.json`):
while a ticket waits for free cores (refused by the free-core test, or
D174's load test where that can't be measured: the ticket's `cores`),
each starts no new task until it is down to one in flight, and takes its
workers back once no such ticket waits, so cores come free and the rule
admits the sitting as written. A ticket that waits for anything freed
cores can't give it (RAM, a full suite's lock, an earlier ticket, an
xemu not ours) is not given way to (AZ-620: the trick explorer slept an
hour behind a ticket an owner demo held); a wait for another launch's
lock leaves the ticket's `cores` as it was. A record of ours whose pid
is no xemu is no demo for a token either. While an
owner demo runs (D526) each job keeps at most the demo's budget of tasks
in flight (`demo_budget()`) and puts every process under it (its pool's
workers, one started since within a poll; never the job's own process,
whose children would inherit background priority for good) at background
priority, as the sandboxes beside the demo run; once the demo ends it
takes them back out and its workers back. Its token's file says
`background`. The
token is inert off macOS and under pytest (a full suite already holds a
third sandbox back). A relaunch on a W that still holds its slot keeps it
(it replaces that sandbox, it doesn't add one): it takes no ticket and
no admission test, and waits only for another launch or a foreign xemu; on a
W whose slot was reclaimed it queues like a new sandbox.

A sandbox (`up`, and `jump` inside):
1. takes a slot;
2. records sha256, mtime and size of the HDD, EEPROM, boot ROM, BIOS,
   the fixtures' `xemu.toml`, the app's `xemu` binary and the disc,
   plus the mtime and size of every entry of xemu's pref dir, in
   `$W/baseline_before.txt` (`$W` = a new `/tmp/azx-<group>.*`), and
   notes any fixtures `SHA256SUMS.txt` line those hashes don't match
   (since Step X.95 each sha256 is `file_sha256`'s: a source standing
   as it was last hashed, by its content key, its path with its device,
   inode, size, mtime_ns and ctime_ns, is not read again; the keys are in
   `~/Library/Caches/AzurKit/xemu-sha256.json`; since Step X.96 `down`'s
   `baseline_after.txt`, D98's proof, reads a source whole only when its
   content key moved since `up` (`st["source_keys"]`, `baseline_keys`: a
   write or a metadata change moves the ctime, which no tool sets back,
   and a replaced file is another inode): 3.2-3.5 s of reads for the
   6.5 GB of sources became 0.01 s. The trade-off: the proof that no
   source changed rests on that key, and an unchanged source's digest on
   both lines is `up`'s, which may be the cache's, so a wrong cache entry
   (one is kept only when the key stood across its read) no longer shows
   at `down` as a whole read showed it, nor at `up`'s `SHA256SUMS.txt`
   check, which compares the same (maybe cached) digests; deleting the
   cache file makes the next `up` read every source; a staged
   or adopted build disc's `disc_sha12` is its source's at the clone, not
   a second read of the clone);
3. APFS-clones the app, those four files and the disc into `$W` and
   writes a scratch `xemu.toml` (no pad on port 1; the port-2 pad on SDL
   scancodes 232-256, where SDL3 defines no key, so only the FIFO
   drives it and typing into the window can't; no F5-F8 snapshot
   shortcuts; no background input capture; windowed, and a window's
   `frame_interpolation = 'off'` (the fixtures' `'2x'` hung v0.16's
   windowed boots, AZ-601; on v0.16.1, whose present waits at most 100 ms
   for a drawable and drops frames past it, a window keeps the owner's
   `'2x'`, `PRESENT_STALL_MARK`, and `down` keeps the run log's present
   stalls, `st["present_stalls"]`, Step X.61); `volume_limit =
   0.0`, a float, the owner's preference; every file it reads or writes
   in `$W`), also into the copied app's `Contents/Resources` (portable
   mode, so caches stay in `$W`); on a build with `XEMU_BASE_PATH` (v0.15
   and on; the name in its binary, Step X.33, PROMPT-7
   A(4)) it also sets that to `$W/xemu-data`, which then holds the
   shader and pipeline caches ahead of portable mode (empty, but a
   window's, Step X.69: an owner demo or any `--window` sandbox starts
   from its build's kept cache, `~/Library/Caches/AzurKit/xemu-shader-cache/<the
   binary's sha256[:12]>/`, seeded once by `cp -c` from the fork's bench
   cache `~/Library/Caches/xemu-fork-bench` (read only) with only the
   files that build reads: its pipeline caches, v0.16.3's
   `vk_prewarm-*` lists and its own version's `spirv_cache_v<version>-*`
   folders; cloned into `$W/xemu-data` before the launch, and `down`
   clones back what its xemu wrote or changed, `st["shader_cache"]`, and
   drops from the kept folder a `vk_prewarm-*` list the fork set aside
   (its `.bad`, or a dead launch's `.running` marker); the
   fork measured a first fire-armor cast at 1.9-2.3 s of compiling cold,
   45-190 ms warm; null and offscreen sandboxes, deterministic or real
   time, the rate pairs too, keep it empty; an inherited
   `XEMU_BASE_PATH` is never passed on, nor are the fork's other
   variables a shell may hold that change a run or write outside `$W`:
   `XEMU_TRACE_RECORD`/`_REGIONS`, `XEMU_BLOCK_LOG`, `XEMU_VOICE_LOG`,
   `XEMU_AUDIO_WAV` and `XEMU_ICOUNT_LIVE_PADS`, as the fork's own
   launchers drop them, and v0.16.1's own: its watch monitor and backlog,
   the bugcheck report, the renderer's RAM mode, the language, a smaller
   RAM's loads, the old reset, OHCI and render-pass orders, the AGP
   decode, CSTATUS and the present bound; `NOT_INHERITED`, Steps X.32 and
   X.61); on a build with
   `XEMU_STRICT_CPUID` (v0.16; Step X.58) it sets that to 1, so code the
   Pentium III lacks (SSE2, SSE3's FISTTP and LFENCE) raises `#UD` as on
   the console (AZ-021, the skill's hazard 3): `boot-build` then stops
   with `CpuidFault` naming each fault's pc and feature from the run log
   (never retried, never the opcode bytes), `down` keeps every launch's
   faults (`cpuid_faults`) and the kit's report lists them; on v0.16.1
   (Step X.61; each by its mark in the binary) it also opens the QMP watch
   monitor on `$W/qmp-watch.sock` (`XEMU_QMP_WATCH`: a second monitor
   whose read-only queries answer while an advance holds QMP), sets
   `XEMU_SOCKET_BACKLOG=64` (a second client queues for its greeting
   instead of being refused) and `XEMU_GUEST_BUGCHECK=1` (the run log
   names each guest bugcheck, `xemu: guest bugcheck 0x<code> (<p1..p4>)
   from <ret>`, and each halt with interrupts off; RAM unchanged:
   sitting x61b, the 32 D98 states on v0.16's hashes with all three on):
   `down` keeps every launch's (`bugchecks`, `st["bugchecks"]`) and the
   kit's report lists them (`GUEST BUGCHECKS`); on 0.16.4-3-g95e7ffc7ec
   (Step X.94) each bugcheck also carries KeBugCheckEx's registers (its
   run log's registers line) and, where the sandbox's QMP heard the
   event, KeBugCheckEx's EIP, the trap frame's EIP decoded from the
   event's stack in memory (`trap_eip`, `trap_at`) and that stack's
   length and sha256[:12]; the stack itself, guest memory, is taken out
   of every QMP message as it arrives (`scrub_event`) and never written;
4. launches it under `nice -n 10` (an owner demo, `--owner-pad`, at normal priority: `up` and `relaunch` refuse one from a
   niced process, as zsh's `bg_nice` makes a `&` job, AZ-466) with the input FIFO (`XEMU_INPUT_PIPE`), a free gdb port,
   its QMP socket and an HMP monitor (`$W/hmp.sock`, Step X.32: its `info status` answers while an advance holds
   QMP; `hmp_command`), and quits at once if the run log shows any path
   outside `$W` (the base path must be `$W/xemu-data/` where it set
   `XEMU_BASE_PATH`, else the app's `Contents/Resources/`; the null
   renderer prints no base path, so a null-mode log needs none, but any
   it shows must be that one); an xemu that quits before that proof
   fails by its exit code and `exit_cause` (QEMU's error on a launch
   option too, such as a taken `-qmp` port, AZ-480), and the failed `up`
   still compares the sources and the pref dir with their baseline, as
   `down` does, before it deletes `$W` by its path (or keeps it, with
   `keep` or when a source changed; the kit's report lists that sandbox). It waits up to 180 s
   for that log line and up to 180 s more for the gdbstub: under load
   (session s5, load about 40 on 24 cores) the old build took 90 s and
   110 s; the fork build took 0.4 s and 0.6 s (sitting x14, load 50).

**Deterministic by default (Step X.22).** Every sandbox passes
`XEMU_HEADLESS` to xemu: `null` by default (no window and the null
renderer: logic, RAM, the gdbstub and QMP only), `1` offscreen (a hidden
window, no Dock icon, never the focus, no menus or audio; the guest
renders, and xemu opts out of App Nap: D184's old default, now for a
sitting that needs pictures) or `0`, a visible window (`--window`). `up
--headless null|1|0`, `jump`, `Sandbox(headless=)`, the kit's
`Sitting(headless=)`, `serve` and a spec's `headless` take it. The build
says which it runs at startup (`xemu: headless mode: offscreen|null`; the
sandbox records it as `headless`, None for a window); a build without the
mode (the kept v0.13.3 build) opens its window, and the sandbox notes it
was asked. With the null renderer on a build that has it (the fork build;
`st["deterministic"]`, the kit's report says so) xemu also runs
`-S -icount shift=2,align=off,sleep=off`: guest time follows executed
instructions, not the host clock, as fast as the host allows (v0.15:
98-576 fps across the D98 field states, median 244, and about 1,140 in
their save menus at load 29-37, sitting x32; v0.14-36: median 89 and
about 260 at load 6-20, sitting x30), so the same
state, input and QMP and gdbstub calls give the same guest RAM in any run
or process (sittings x22, x24, x26, x30, x32: every D98 state, two runs in one
xemu and one in another, end on the same 128 MiB, the same hashes on
v0.14-12, v0.14-27 and v0.14-36, and on v0.15 but for 3 states whose ends
moved two words, a NaN's payload x87 now keeps, `docs/RE_XBE.md`). `-S` keeps the guest stopped until the first `loadvm` (a
`loadvm` without `halt_at_tick` then runs it; `run()` starts a cold boot;
`jump` and `boot-build` work unchanged: 25.6 s, first try, in x22).
`Sandbox(deterministic=False)` runs null in real time; a window never is
deterministic, offscreen only when asked (below), and the kept build
hasn't the mode. Pipe lines apply at a vblank in this mode, and pads
change only from the pipe (physical pads are ignored). Every load drops
the pipe lines still queued, so write a run's input after its load
(`loadvm(tag, paused=True)`, then `send`/`axis`, then `frame_advance`);
a load or save that would drop one the harness wrote logs a warning
(`_load_drops_input`). A state saved under icount keeps the keys and axes
the pipe holds; one saved without (the D98 states) starts from a neutral pad.
The guest's RTC needs no `-rtc` (Step X.58): under any `-icount` the fork
runs it on the virtual clock from 2001-01-01 unless `-rtc` says
otherwise, and a load continues from its snapshot's date. A cold boot
(`boot-build`, `jump`) in a deterministic sandbox runs on guest frames
(Step X.64, AZ-675: below), so it repeats in every process.
**Checkpoints (Steps X.26, X.30).** `Sandbox.savevm` and `park` are
checkpoints: the run that goes on is the one every later load of the
tag gives. Deterministic on v0.14-36 (`st["continuity"]`) the save alone
does it: an icount save carries the host-side state a continued run
depends on (the resampler, filter and HRTF history, the APU schedule,
AC'97, the RTC's phase, the field pin, the pad reports and held pipe
input), so a bare `savevm` continued 300 vblanks equals two loads and two
checkpoint restores (sitting x30). Otherwise (real time, an older build,
or a pipe line the harness wrote that hasn't reached the pad yet) they
reload as Step X.26 did: `savevm`, then `loadvm` of it (`_reload`; a
halted guest stays halted), then on. A deterministic guest the gdbstub
holds halted is saved where it is and stays held, as `park` saves
(AZ-732, Step R1.36): letting it go first ran it for as long as the
QMP stop took on the host, past a player tick on a loaded host, so a
cold `boot-build`'s warm save halted about 1 boot in 20 one to three
ticks late. The chain's parks and re-anchors and `l3_certify.py`'s
snapshots go through them.
**In-memory checkpoints (v0.14-36):** `Sandbox.checkpoint_save(name)`,
`checkpoint_restore(name)`, `checkpoint_delete(name)` and `checkpoints()`
(QMP `xemu-checkpoint-*`): the whole machine in host memory, restored as
`loadvm` restores (the disk sectors the guest wrote since put back, a
halted guest kept halted), never written to the qcow2; a relaunch loses
them, and a sandbox keeps the newest 8 (`CHECKPOINTS_KEPT`, about 70 MiB
each). `park` keeps one beside its `savevm` (which a relaunch still
needs), and `unpark` in that xemu restores it. Sitting x30's medians:
park 0.10 s (savevm 0.047 s, checkpoint 0.016 s; Step X.26's recipe on
the same build 0.08 s, on v0.14-27 0.35 s), unpark 0.014 s by checkpoint
against 0.032 s by `loadvm` (v0.14-27: 0.06 s). A checkpoint restore that
fails `unpark`'s start check is dropped and the tag loaded from the qcow2
(the result's `missed`; AZ-694); a replay through PC hooks whose start's
checkpoint misses its start stops (AZ-703).
**v0.15's speed-ups (Step X.32b; the fork's PROMPT-8 advice).** On a
build with incremental restores (`st["incremental"]`) `checkpoint_restore`
writes back the pages written since the last save or restore (the fork:
4.5-5.8 ms against `loadvm`'s 25.5) and, since Step 2.172f, compares
every other page too (`verify`, a few ms more): xemu's dirty log misses
some writes (132 pages after a route pilot's retreat, the start check
passing, the guest then bugchecking 0x1E; AZ-821), and the pages it
missed are named in an event. Since Step X.94 each verified restore is
counted (`st["restores"]`: how many, the pages missed in all and the
first 32 that missed any; `down`'s `restores` and the kit report's
`CHECKPOINT RESTORES` line): the cause, AZ-822 (a park's HMP `savevm`
left the log's store traps disarmed), is fixed in 0.16.4-3-g95e7ffc7ec,
so there every restore must miss 0, and a nonzero is warned as a fork
bug. Since Step X.96 (the standing rule: a finding that points at xemu
goes to the fork session at once) that nonzero also drafts the fork's
request, `PAGES-MISSED-<W name>-<n>.txt` in
`xemu-fork-requests-<date>/` in `$EV`, the private evidence folder
(`EV` names it, else `evidence` beside the main checkout;
`fork_requests_dir`), named in the
warning, the event and `st["restores"]["requests"]`: the build and its
binary's sha12, the sandbox, the checkpoint and the restore's counts,
and the call sequence since the checkpoint's save (the last 256
guest-touching calls a sandbox keeps in memory, `_note_call`: QMP and HMP
commands by name with their frame counts and checkpoint names, no
`query-*`, the gdbstub's memory writes counted, never an argument's
data); the orchestrator relays it (D894). A
`loadvm` that leaves the VM stopped (`paused`, or the default halt at
the first tick) keeps its load as the checkpoint `load-<tag>` and loads
the tag again in that xemu by restoring it (the result's `how`: `loadvm`
or `checkpoint`); a `savevm` or `park` of the tag drops it, and an owner
demo keeps none. An HMP `loadvm` (of another tag, or an `unpark` from
the qcow2) first drops every checkpoint but the tag's own load: it
reverts the disk outside the fork's checkpoints, which keep only the
sectors the guest writes through IDE, so a restore after it would put
one state's RAM over another's disk (the save files a level exit
writes). The restore's dirty log can't see writes another process makes
through `XEMU_RAM_SHM`, and nothing here makes one (the sandbox's reads,
the demo recorder and replug watcher only read it, Live through a
read-only view; a writer would need a full restore). The gdbstub client
turns on `Qxemu.stepover` where the stub offers it, so `resume` is a plain `c` (1.8 ms a stop against
z0/s/Z0/c's 4.2) and `arm` drops its identical-byte rewrite (v0.15
compiles a `Z0` into the translated code; the rewrite invalidated the
page's 230-odd blocks again); `RSP.read` sends a read's page pieces, and
`read_many` several regions, in one `qxemu.read` (16 x 64 B in 0.12 ms
against 1.6). A deterministic sandbox keeps one QMP connection (0.13
against 0.34 ms a command; one per W in a process, whichever `Sandbox`
object sends; opened again when xemu closed it, dropped when a command
breaks, a command never sent twice); the kit's exec server lets it go
after each request, so a command from another process (an `attach`)
drives the sandbox between requests, never during one; any other driver
holds it for its life (another process's command fails, as during an
advance, and `down` ends that xemu by SIGTERM; a second `QMP(W/qmp.sock)`
in the holding process is refused at once, "held by another client", not
after its timeout: send on the held one, `Sandbox.qmp(cmd)`, Step X.45). A real-time,
recorded or owner-demo sandbox connects per command, as the demo
recorder and replug watcher share W's one QMP (between the serve's
requests: W's QMP turn, AZ-644); a connect refused there (ECONNREFUSED:
nothing sent) is tried again for 3 s, the refusals an event (AZ-646:
Step X.56's sitting met one with no other client). No second `-qmp`
socket (Step X.58): QEMU runs every QMP monitor's commands in one
dispatcher coroutine, which a frame advance (a coroutine command) holds
until it ends, so a second socket's commands would wait as the first's
do (only HMP answers meanwhile), and W's QMP turn would still have to
keep a watcher's `stop` and `cont` out of the harness's own stop-to-load
stretch. `Sandbox.replay` of a light
observation (`deep=False`) from an update-entry start runs through the
fork's PC hooks on a deterministic v0.15 sandbox (`st["hooks"]`): the
start kept as a checkpoint, the pad queue written at the update entry,
the camera at 0x85276, the observation collected at the RETs by address
expressions and read back as `obs.read` reads it, a chunk of vblanks a
call with no stop (`xemu-run-until` to the level load with `stops`); a
diverge stop it ran past runs again from the checkpoint to the entry
after the first tick off, and anything it can't vouch for (a dropped
record, a missed camera hit, an unread region, the active pad moving)
goes back to the start for the gdbstub replay (sitting x32: 8.6 ms a
tick against 23.4, equal on every tick). A deep one keeps the gdbstub
(the latches' map is a tree no fixed region holds).
**Frame counts from a parked start (v0.14-36):** `frame_advance` from a
guest the gdbstub holds halted starts from that instruction (its
breakpoints lifted, the gdbstub let go without a continue), so no guest
time passes on the host clock first; x30: three unparks then 120
vblanks, the same RAM. `frame_advance(n, trace=[{"address", "size",
"virtual"}], every=K)` also returns the bytes of up to 256 regions at
every Kth vblank (the last always), read before the guest sees it.
**Input recording (v0.14-36):** `up --record PORT`,
`Sandbox(record=PORT)` or the kit's `serve --record PORT` (an owner
demo adds `--window --owner-pad PORT`, `xemu_demo.py`) set
`XEMU_INPUT_RECORD`: every vblank, what that port's pad gave the guest,
as pipe lines tagged `+N` from the last load into `W/input-record.txt`
(a relaunch keeps the last as `input-record.<n>.txt`), a `# load` line
opening each load's section. `recording_sections(path)` splits it;
`Sandbox.play_recording(lines, frames, port=)` replays a section after
`loadvm(tag, paused=True)` of the state it was recorded from (each
`+N` line written as `@<base+N>`, base the frame the paused load left:
on the pipe `+N` counts from the frame xemu reads the line at, so a raw
`+N` read late lands late, AZ-510), on the keyboard pad on that port (port 2 in the scratch map; `--pad-port 1`,
`Sandbox(pad_port=1)`, binds it on port 1 and nothing on port 2, for a
demo recorded on the owner's port 1, AZ-439; `port=` refuses a
recording of another port; a section past `PIPE_WINDOW`, 8 KiB, goes
a window at a time, each followed by an advance that drains the pipe a
paused xemu doesn't read, AZ-539; on v0.16.1, whose QMP lists
`xemu-input-queue`, the section goes in one call instead, every line
accepted, then one advance, Step X.61: sitting x61c replayed X.30's icount
recording onto its RAM that way). A section recorded on a build before
v0.16.1 that crosses a `system_reset` replays only with v0.16's reset
(`Sandbox(legacy_reset=True)`: `XEMU_NV2A_RESET_IRQ=0`;
`needs_legacy_reset(<its build's xemu_version>)`). `unpark` refuses a
start parked by a build of a newer savestate stream than its sandbox's
(`state_stream`: v0.16.1's to v0.16.4's states don't load in v0.16 or
the kept build, and load in each other). A replay sandbox runs on a clone of the
demo's drive (`hdd=`) and takes its tags from `note_tag`'s meta
(`sb.adopt_tags(meta["tags"])`: each tag's disc, the USB pads it holds
and the recorded port); a `loadvm` of one plugs the pad hubs the state
holds that the machine lacks before it loads (`plug_pad`: port 2's
neutral, the replug watcher's demo hub reading player 1). Recorded under
icount it replays bit-identically (x30); recorded in real time (an owner
demo: icount ignores physical pads) it replays the same RAM every time
and, in x30's 240-vblank test, the player's position, box and velocity
the session's exactly, one vblank apart in the session's trace (the fork
measured within 0.001 units); the RAM differs, as guest time followed
the host clock. **A demo as played (v0.15, Step X.32b, AZ-475):**
`--live-pads` (`up`, the kit's `serve`; `Sandbox(live_pads=True)`)
runs a window (or offscreen) under `-icount shift=2,align=on,sleep=on`
with `XEMU_ICOUNT_LIVE_PADS=1`, so host pads drive their ports read once
a vblank and the run stays deterministic: its recording replays tick for
tick, ending on the session's RAM. With `--owner-pad 2` the owner's
gamepad takes port 2's pad (the keyboard pad's) by QMP
`xemu-input-bind` once xemu is ready, so nothing is plugged and a load
needs no re-plug; without it the pipe drives the pad (an agent's run).
Every sandbox on a build with it loads with `XEMU_LOADVM_ADD_PADS=1`: a
load of a state holding a pad the machine lacks plugs it and loads
again, so a demo's state loads in a replay sandbox whatever pads it
holds.

**Waits on the build's own lines (Step X.14).** A build that prints
`xemu: ready` and `xemu: state loaded` (the sandbox records
`ready_line`) is waited on by them: a launch's first `loadvm` waits for
`xemu: ready` (its machine and pads exist; 0.6 s after the launch in
sitting x14; `TimeoutError` after 120 s), and each `loadvm` must print
`xemu: state loaded` within 30 s, else it fails naming the line (or why
xemu stopped). An older build keeps Step X.9's wait (below). **Over QMP
on a later fork build (Step X.33, PROMPT-7 N):** a build whose QMP
offers `query-xemu-status` (its `query-commands`, asked once per launch;
the sandbox records `xemu_status`; v0.14-36 has none and keeps the
lines) is waited on over QMP, not its run log: the first `loadvm` until
`query-xemu-status` says `ready` or `XEMU_READY` arrives on that
connection, and each load (`loadvm`, a reload, `unpark`, a checkpoint
restore) by its `loads` count going up (`XEMU_STATE_LOADED` goes out
before the load's reply). The harness's QMP client (`QMP`) keeps the
asynchronous events that arrive on its connection, the last 256
(`QMP.events`); `QMP.wait_event(name, timeout)` takes a kept one or
waits for the next. A connect that fails says which case it is (Step
X.37, PROMPT-8 E, AZ-464): the socket file gone (`removed (ENOENT)`), or
there and refusing (`ECONNREFUSED`: the QMP chardev serves one client
with a listen backlog of 1, so it is held by another client or a held
advance, taken over by another listener, or left by an xemu that died),
or connected and never greeted in its timeout (the first client past a
held one waits in the backlog: held, or xemu's main loop is stuck); the
error stays the `OSError` (`TimeoutError`) it was. With
`XEMU_SOCKET_BACKLOG` (v0.16.1, Step X.61) a refusal means no listener
(raised at once, not retried) and an ungreeted connect is queued behind
a held client. Every command carries an `id` and a reply to another (a
late one, to a command whose wait timed out) is skipped
(`QMP.send`/`reply`); the watch socket is a monitor of its own, so a
deterministic sandbox's held connection doesn't refuse it.
**Screenshots** are QMP `screendump` (never HMP's, which holds the main
lock): `Sandbox.screenshot(name[, dest])` writes a PNG (xemu writes it in
`$W`, then it moves to `dest`, default `<out or W>/<name>.png`), windowed
or offscreen; the null renderer draws nothing, so its PNG is whatever the
framebuffer holds, so a screenshot there is refused: a sitting that needs
pictures runs offscreen (`headless="1"`, real time). **Picture age
(v0.15, AZ-452):** the fork's screendump now waits for the frame's
compositor (older builds could return the previous screendump's picture:
retake one whose bytes equal the last one's), and on a build whose QMP
offers `query-xemu-display` (`st["display_query"]`) `screenshot` asks it
just before the screendump: `Sandbox.last_picture` holds the reply
(`frame`, `loads`, `flips`, `flip-frame`, `flip-loads`) and `stale` is
True, with an event, while the guest hasn't flipped since the last load
(the picture is then the loaded state's own saved frame: advance until
it flips; Azurik presents every 3 vblanks, so a right picture can be 1-3
frames old). **On v0.16.1 (Step X.61, AZ-668)** the reply's
`picture-stale` dates it instead, a checkpoint restore counted too
(`flip-loads` missed one): a deterministic sandbox, or any whose VM isn't
running (paused, or halted after a load), advances one vblank at a time
until it is fresh (at most 12, `last_picture["advanced"]`: a caller that
counts frames adds them, as `model_kit`'s `pic` does), a running real-time
one polls it for a second, and one still stale raises.
`Sandbox(headless="1", deterministic=True, null_ram=True)` (v0.16.1's
`XEMU_RENDER_NULL_RAM=request`) keeps the null renderer's RAM and draws
only for a screenshot (`xemu-render-next`, 2 frames). **Deterministic
pictures (Step X.26):** `up --headless 1 --deterministic`,
`Sandbox(headless="1", deterministic=True)`, the kit's
`Sitting(..., deterministic=True)` or a spec's `deterministic = true` run
offscreen Vulkan under the same `-S -icount` on a build whose renderer
has the mode (v0.14-27, `OFFSCREEN_DETERMINISTIC_MARK`): a screendump
taken with the VM paused (after `frame_advance`, or halted) is the same
PNG in every run and process (sitting x30: two PNGs and the RAM
byte-identical in three processes, screendumps leaving RAM unchanged;
the RAM isn't null's, as the GPU writes its surfaces into it), and a
running guest's is refused. On a build before v0.15 load once per
process: on the fork's word a repeated `loadvm` in one long-lived
offscreen Vulkan process diverged about 1 time in 7 there, so each load
after the first (`loadvm`, a reload, `unpark`, a checkpoint restore) is
warned by name in the sandbox's events and log (D200's guard, Step
X.31a); v0.15 fixed icount loads, and seven such loads in one process
ended on one RAM in sittings x32 and x40, so on a build with its
`XEMU_LOAD_VERIFY` mark the guard says nothing (Step X.32b). It runs at about 25 fps, under a third of null's
speed, so a long null run that
needs a few pictures can `savevm` at the frame and load that tag in a
short offscreen deterministic run instead (the fork's README). **Frames:**
`Sandbox.frame()` (QMP `query-xemu-frame`: vblanks while the VM ran) and
`frame_advance(n)` (`xemu-frame-advance`: run n vblanks, then pause; QMP
`cont` resumes; on v0.16.1 both keep the reply's `vblank-ns` as
`st["vblank_ns"]`, which `guest_s(frames)` converts by, and
`frame_advance(n, gpu=True)` returns the advance's NV2A work as
`gpu-counters`, its `max` set against vanilla's heaviest flip by
`gpu_budget(counters)`, `GPU_CEILING` from sitting x61's pack-03 scenes:
347 begin/end pairs, 213,262 triangles, 1,024,084 pushbuffer bytes, Step
X.61; no upper bound, as vanilla at a1 goes over it, so a build is set
against its own vanilla control's, `ceiling=`; `over` is `ratio > 1`, so
read the ratios: booblord at a1 was 72 vertices and 24 triangles over its
control, 1.0002x). **Frame cost (Step 2.173, D603, D604):** with
`gpu="per-flip"`, `frame_cost(counters, frames)` drops the advance's
first flip (partial) and gives every counter's steady max, p95 and
median by kind (draws, geometry, pushbuffer, textures, surfaces,
reports, memory); `timed_advance(sb, n, play=lines)` runs one phase
timed (host ms a vblank, the process's CPU seconds by `ps`, the host
profile's difference, and under icount the guest's busy ns a flip:
the vblanks' guest time less `idle-ns`); with `gpu=False` (a rate arm's,
Step X.68: the fork found the counters, called for every index word,
cost l256_120's arms an estimated 18-26 ms of a 51 ms frame) it runs
no NV2A counters and counts flips by `flip_count`: query-xemu-display's
`frame-ends` where the binary's reply has that key (Step X.69; the fork's
v0.16.3: the guest's frame ends, NV097 FLIP_STALL, counted with the
counters on or off, a running total since the process's launch that no
loadvm, checkpoint restore or reset clears, so an arm takes its
difference within one xemu process and counts none across a relaunch),
else the game's present counter (0x1A9C0C, Europe 0x1ABB8C, +1 once per
pacer frame end, after its `D3DDevice_Present` or in place of a skipped
one; the fork found the two agree), its source in
`flips_by`; `frame_warning(build_scenes,
control_scenes, ceiling=, rt=, noise=)` warns where a steady flip
passes vanilla's heaviest (L1: `GPU_CEILING` raised by the control's
own scenes), notes each scene against its control (L2) and, given
real-time pairs, warns where the build flipped less than vanilla in
all `RT_PAIRS` (3) by more than max(3 %, the vanilla-vs-vanilla
`rate_spread`), inconclusive under 0.49 flips a vblank (a loaded
host), on deterministic pairs or on counted ones (`flips_by`
`gpu-counters`, or none: pairs from before Step X.68); never a refusal.
Where that fires, `fork_request` fills `FORK_REQUEST`, the fork's draft
prompt (counts, times, sha12s), stating for the rate arms and the count
row each the xemu binary's sha256[:12], the load (the state tag and
drive, or a cold boot's recipe) and whether the scene was reached by
warp or by the state (the fork's item 7: a draft without them, or
with one "not recorded", an older row's, is refused by name). The
kit's `row_cost` and `rate_pairs` run them. On v0.15 (29a024b18e; PROMPT-8 D, Steps X.37 and X.32:
in sitting x32 a gdbstub attach mid-advance ended it after 843 of 6,000
frames) an advance also ends early on any VM stop it didn't make, its
reply's `stopped` naming the run state (`paused`: a gdbstub client
attached, sent ^C or a stray byte; `debug`: a breakpoint; `shutdown`:
SIGTERM; `restore-vm`: a failed loadvm): `frame_advance` records an
event with the frames that ran (`ran`, or `ran_at_most` when the VM ran
before the advance began), returns on a breakpoint's stop and raises
`AdvanceStopped` on any other. v0.14-36 instead waits through such a
stop for good, holding QMP (AZ-451); an advance with no reply in 600 s
first samples the xemu, before any later QMP call, gdbstub attach or
signal (`hang_probe`: `sample <pid> 5`, then `ps`, `lsof -p` and HMP
`info status` on `$W/hmp.sock`, into W's `hang-<pid>-<time>.sample.txt`
and `.txt`; `down` keeps that W),
then raises `TimeoutError` naming the sample. **On v0.16.1 (Step X.61,
AZ-685)** a long command (`xemu-frame-advance`, `xemu-run-until`) waits
for its reply in 5 s slices on its connection and asks the watch
monitor `query-xemu-frame` between them (`Sandbox._long_qmp`): while the
frame moves the guest is alive however slowly it runs (a sandbox at
background priority beside an owner demo, D526), and it is taken for a
hang (the same probe, then `TimeoutError`) only once no frame moved for
120 s (`STALL_S`; a watch that doesn't answer counts as none) or after 4
hours (`LONG_CAP_S`); `ADVANCE_S` is then unused. Sitting x61b: the
watch answered 27 queries (0.54 ms at most) during a held 6,000-frame
advance, the RAM digest the same with and without them. Sitting x61's
record row (`STALL_S` set to 10 s, the xemu at background priority):
3,000 and 12,000 frames returned in 32 s and 155 s on the
normal-priority digests, a later frame at each 5 s slice, and with the
watch unreachable the 3,000 raised `TimeoutError` 10 s in. **On
0.16.4-3-g95e7ffc7ec (Step X.94)** each advance and run also carries
`timeout-ms` (`advance_bound_s`: 120 s plus 1 s a vblank, at most 4
hours; `frame_advance(timeout_s=)`): xemu pauses one still short of its
frame there and replies `timed-out` (a run's reason `timeout`), which
raises `AdvanceTimedOut` with the frames that ran (kept in `down`'s
`timeouts`); a deterministic sandbox then refuses to advance or run
until a checkpoint restore or a load, since the pause is at a host-time
point. While the watch answers, an advance whose frame stopped waits for
that reply (one slice past the bound) rather than the 120 s stall.
Launch-to-ready and load waits (`READY_S`, `LOADED_S`) are 4 times longer
while an owner demo runs (`BACKGROUND_SCALE`; the fork measured up to
111 s to ready and 24.5 s a load under `taskpolicy -b`), and so are a
capture's and `Sitting.tick`'s player-tick waits (Step 2.175a: at load 70-80
beside a demo a combo row's 5 s tick wait ran out while the tick came, its
boots taking 506-758 s against 10-50 s), and the cheat tick's, the cheat code's and
the level warp's (Step 2.177d: a cost row's warp to w1 ran out at the menu's
5 s cheat tick wait, its sandbox about 16 times slower than alone). **Analog pipe input:** `Sandbox.axis("lx"|"ly"|"rx"|"ry",
v)` and `("lt"|"rt", v)` send the pipe's `axis`/`trigger` lines (the
pad's own path, no RAM write; `pipe_axis(f)` gives the raw-axis value for
a ControllerState float past the game's dead zone); `send(line, at=N |
after=N)` applies a line at frame N or N frames on (in real time within
a frame or two; deterministic, written while the VM is paused and then
`frame_advance`d, at its frame exactly; the replayer keeps `write_pad`;
a `down`/`up` line takes a scancode, `sb.code(name)`, and a button's
name is refused: the pipe would ignore it);
a capture's schedule takes
`axis <name> <v>` and `trigger <name> <v>` actions and puts any axis left
off rest back at its end. **A lost GPU device:** a headless fork build
prints `xemu: Vulkan device lost; exiting` and exits; its known cause
(the compositor sampling freed surfaces after a flush) is fixed since
v0.14-12, and the null renderer has no GPU device. `boot-build`'s
supervisor treats it as any crash (`xemu_died`, the run log's cause
naming it) and relaunches, and the kit's spec runner reruns the case.
v0.15 (3147640b9b; PROMPT-7 P, AZ-293)
also ends on any other failed Vulkan call, where earlier builds trapped
forever (the flip-stall hang): it names the call (`vk_result = N in
<function> (<file>:<line>)`), then a headless one prints `xemu: Vulkan
call failed; exiting` (a fence wait's timeout too) and exits 1;
`exit_cause` names either exit line with the call or fence wait, and a
windowed abort by its call; an assertion's abort by its line and the one
before it (`abort: Unknown vs param: 0x0; Assertion failed: ...`, nv2a's
vsh-prog.c in sitting 2.105, Step X.45). `relaunch` tells our own quit
(`_quit`: a fresh process per row, a retry) from a death: its event reads
`relaunch after pid N quit`, or `died (<exit code>, <exit_cause>)` with
the dead run log's tail copied to the sitting's `logs/` (`Sandbox(logs=)`)
before W goes; a death right before `down` keeps its tail too (`down
after pid N died (...)`).
**gdbstub reads:**
the fork build answers a partly readable `m` with its readable prefix;
`RSP.read` reads page by page and fails on a short reply, so no read
comes back short. `RSP.read` and `.write` refuse the GPU's register
window 0xFD000000-0xFDFFFFFF before sending a packet (AZ-308: a stray
read of NV_USER aborted xemu). **Guest RAM in shared memory (Step
X.31a):** on a build with `XEMU_RAM_SHM` each sandbox launches with its
own name (`ram_shm_name(W)`), and a halted guest's reads (`Sandbox.read`,
so `capture`'s and `replay`'s per tick, `chain`, `pad`, the kit's) come
from it through the guest's page tables from CR3 with no packet, checked
once per gdbstub connection against the gdbstub's page directory (a page
past RAM, a build without it or a failed check: the gdbstub);
`Sandbox.ram_sha256()` hashes the stopped VM's RAM there with no file
(else a dump, deleted at once); the sittings' baselines hold its
sha256[:12]. `Sandbox.ram_digest()` (v0.15, Step X.32b) asks xemu itself
(QMP `xemu-ram-digest`) for its XXH3-128 (32 hex digits, about 4 ms for
128 MiB) to tell runs of one sitting apart. `Sandbox.watch(ranges,
max_hits=)` (v0.16, Step X.58) starts xemu's access log (QMP
`xemu-watch-start`): every CPU load or store that overlaps up to 64
ranges (`watch_ranges`: `(address, size[, access[, virtual]])` or
dicts, the game's VAs and writes by default, 1 B to 16 MiB below 4 GiB)
with its frame, pc, address, physical address, size, access and value,
the VM never stopped and the run the same under icount; start it paused
or halted, run, then `drain()` or `stop()` the returned `Watch` (`with`
stops it); a hit's `value` is guest memory, never printed raw. gdbstub
watchpoints work on v0.16 too (sitting X.58 checked a `Z2` and lifted
the skill's ban; `Z3` and `Z4` rest on the fork's 32b1ddf856).
`down` removes the object a
killed xemu leaves.

`down` quits it over QMP (SIGTERM, then SIGKILL, to its own process
only, if it lingers 20 s; a QMP that never answers fails the quit at
10 s, and an xemu that ignores SIGTERM, the flip-stall hang of builds
through v0.14-36, AZ-293, ends by the SIGKILL 5 s later), writes
`$W/baseline_after.txt` and compares:
a changed source file is an incident to report (W is kept and `down`
exits 1); a changed pref-dir listing only warns (the owner may have
run xemu). It frees the slot and deletes `$W` (D147) unless `--keep`. With
`--out DIR`, labelled captures and both baselines go to `DIR`.

`loadvm` loads only the fixtures README's tags (its Savestates table),
tags `savevm` saved in that sandbox (they live and die with its HDD
clone, D110) and, with `AZURIK_XEMU_HDD`, `vanilla-rzp-*` tags; never a
July `vm-*` state. A launch's first `loadvm` waits for the build's
`xemu: ready` (above); on an older build only until QMP says the guest
runs and `info usb` lists the port-2 pad (Step X.9: 0.06 s after the
gdbstub answered in sitting x9; s6's fixed 25 s stays as that build's
bound, and a first `loadvm` that fails before it is tried again there).
It puts the tag's
disc in the tray first if another is in (`disc=`, else the disc the tag
was saved with as the sandbox recorded it: the tray at its `savevm`, a
warm build state's build, a parked start's disc; else `$W/dvd.iso`; an
owner demo refuses a load whose disc it can't name, AZ-465: `--disc`; a medium
change outlives `loadvm`; the event names the disc), and runs to its own first player tick (a running VM is
stopped first, so every load of a tag halts on the same machine, AZ-509): the CLI
prints that tick's row and lets the guest run on, `Sandbox.loadvm`
stays halted there. Scripts drive a sandbox from Python
(`sys.path.insert(0, "scripts")`):
`with Sandbox(group) as sb:` (up, then down), `Sandbox.attach(W)` (any
path to W: it drives the W `up` recorded, the path `ps` shows),
`sb.capture(n, {k: "down y", ...})` (tick-locked on 0x8CCC0; duplicate
hits folded; breakpoints, readers and pokes per tick; `hooks={va: f}`
run f on every hit of va with nothing logged, as the route pilot's
analog stick does at `INPUT_BUILD`; JSON rows of decoded values),
`read_*`/`write_*` (read back), `entity_row`, `chain`,
`pad`, `player`, `code_identity` and `jump_summary`; the docstrings
hold the details. `player()` and `wait_bp` step off a breakpoint the
guest is halted at, which the stub would otherwise report again
(found in sitting rz-a). Where boots run on guest frames and xemu bounds
a run's host time (`_frame_waits`: a deterministic sandbox on
0.16.4-3-g95e7ffc7ec, Step X.96) `wait_bp`'s timeout is guest seconds:
one `xemu-run` to the PCs within that many vblanks, carrying
`timeout-ms`, in place of breakpoints, the host's clock and a ^C, so a
hit is the same and a miss ends on the same frame in every run and
process whatever the load; the gdbstub client (a caller's `g` too) is
attached again after it (`RSP.reconnect`).

`snapshot` and `replay` are simulator Level 3's (Step X.6,
[`SIMULATOR.md`](SIMULATOR.md)). `snapshot` runs to the player's next
update entry 0x8C230 (`--scene`: the next scene tick entry 0x55AB0) and
writes every present user page of guest RAM, the registers and metadata
(level, entity, the start's event clock and hash, the loadvm tag, the
xemu build, the disc's sha256[:12]) to `<label>.l3snap` in the private
store (default the user data dir's `AzurKit/l3-snapshots`, mode 700;
guest RAM holds console keys, so it is never committed or printed), and
since Step X.15 (format 3) the halted thread's stack, its KTHREAD page and
guest RAM as the kernel's window at 0x80000000, so L3
can run whole steps from an update entry; `--hold` leaves the guest
halted there. Every page comes from one dump of guest RAM (Step X.22:
`Sandbox.ram_dump`, QMP `xemu-dump-ram` into `$W` with `gpu-sync` off,
mode 0600, deleted at once; `pmemsave` on a build without it), each user
page through the page tables the dump holds (`l3.ram_reader`), checked
against the gdbstub's view of the page directory and the entity's page:
152 MB in 0.16 s (the dump 0.02 s) where the gdbstub's page reads took
1.9 s, byte for byte the same file (sitting x22). The gdbstub reads the
registers and the metadata. `replay` runs an input string
(JSON run-length segments `{"n", "stick", "buttons", "yaw" | "cam"}`) in
L3 from that snapshot, then replays it in xemu from the same start,
writing the pad (`Sandbox.write_pad`, the one RAM pad writer), a
teleport's request and the camera direction at the instructions L3 wrote
them, reads each tick's observation with L3's own reader
(`devkit.sim.obs`: velocity, flaps, camera, the kit, inventory and
flag hashes) and prints the comparison (errors in metres, state and HP
mismatches, each observed field's mismatched ticks and the first tick
that differs; no positions). Both pin the game's frame pacing first
(`pin_pace`, Step X.20: its own "slow motion" cvar at 1, one scene tick a
frame, as L3 renders; placed), since xemu's catch-up frames (one or two
ticks, varying from run to run) move the render's random numbers between
ticks. Scripts call `sb.snapshot(label)`,
`sb.replay(pads, rows, meta)` and `l3_compare(rows, got)`;
`sb.snapshot(label, here=True, parent={...})` takes the next snapshot
exactly where a replay halted (the next tick's update entry, no tick run
in between: D172's chain), keeping the parent's hashes in its metadata.

`boot-build` is the modded-build path (the `azurik-xemu-oracle` skill,
section 6): it clones the build into `$W/b-<sha256[:12]>.iso`, loads a
`vanilla-ig-*` state (a save menu), then QMP `stop`,
`blockdev-change-medium` to the build, `system_reset` and `cont`;
presses START past prophecy.bik, then START once the boot state (0x1BF61C)
shows the title (6; again after 2 s while it stays there) and, once it
moved on (8, the save list), A once the list has previewed SaveGame #1
(the preview runs the inventory reset 0x57B70, armed before START);
`--save N` (`save=`) first moves the list's cursor right N - 1 times, each
move pressed again every 3 s until the list previews the save it moved to
(a move pressed while the list reads the HDD is dropped; the walk steps
off each preview's stop and lets the last preview's stops pass before a
press, or it takes them for the move's: AZ-354), and names its warm state
`b-<iso sha12>-<tag>-s<N>`. On the D98 drive save 2 is the new-game
character (`--tag vanilla-ig-new --save 2`: w1, elements 0, HP 200/200,
2 boots of 2 in sitting x15-az354). The
list then reads the HDD for 5-25 s (about 8.5 MB/s, sitting x9) and takes
an A pressed meanwhile only when it is done, so A is pressed once and
again only after 25 s with no checkpoint (a second A while it read
delayed or lost the load),
until `load_level_from_path` (0x53750) loads the save's level; waits for
steady play (the player tick at every poll, 0.5 s apart, over 8 s of the
player's event clock: guest time, so a loaded host waits longer, not less;
each tick its polls stop at puts the player's HP back to the first one's:
e7's enemies attack during them, AZ-305) and checks `.text` and `SHIMS`
against the build. No fixed sleep is left in it (Step X.9).

**On guest frames (Step X.64, AZ-675).** In a deterministic sandbox on
v0.16.1 (`Sandbox.frame_boot`: `xemu-run` and a debug advance) the walk
above runs on frames, not the wall clock (`Sandbox.boot_frames`; `jump`'s
power-on too): the tag loads paused, the reset stays stopped
(`reset_into(name, cont=False)`), and each step is one QMP `xemu-run`
that queues its presses at their frames (`@N`, counted from the reset)
and runs to a PC (`PROPHECY_STARTED`, `INV_RESET`, `LOAD_LEVEL`,
`PLAYER_TICK`, ...) or the boot state, within a budget of vblanks (the
walk's bounds at 60 Hz). So a build's boot is the same in every process,
a process's first or its second (AZ-628's split was the wall clock: a
second boot, its translations cached, pressed A later in guest time).
START goes a frame after the movie starts (held 2 frames), a frame
after the title is up (held 8: the title reads the pad only every few
frames), A on the save list at `A_FRAME` (1440; held 13 frames) or a
frame after the list previewed the save, and A at each poll the player
tick doesn't run. One A frame in a few hundred hits the game's own
allocator race (AZ-695) and bugchecks 0x1E, in every process (the fork's
sweeps: balthazar at f6 at 1459 of 1428-1477, the vanilla disc at one of
320 schedules), so a retry presses A `A_RETRY` (4) frames later per try.
`--a-frame N` (`a_frame=`) presses A at frame N (`tries=1` keeps it: a
sitting on AZ-695). The JSON's `frames` is the schedule (`movie`,
`skips`, `title`, `presses`, `a`, `level_at`, `polls`, `steady_at`,
each from the reset). A real-time sandbox (a window, an owner demo)
walks on the wall clock as before.

**Warm boots (Step X.9).** A booted build's state is then saved into the
sandbox's own HDD clone as `b-<iso sha12>-<tag>` (never D98's drive,
D102; it lives and dies with `$W`), and the next `boot-build` of the same
build in that sandbox is one `loadvm` of it with the build in the tray,
checked the same way (JSON `warm: true`); on v0.16 the JSON's
`host_profile` holds the boot's host-time counters' difference (QMP
`query-xemu-host-profile`, `Sandbox.host_profile`, `host_delta`:
`translate_s`/`translations`, `apu_s`/`apu_ticks`, `idle_s`/`idle_warps`;
`since: launch` after a relaunch), kept in the kit's boot records and
report (Step X.58); `--cold` (`warm=False`) boots
from the menu and saves nothing. **Shared across a sitting (Step X.81d):**
a sandbox made with `warm_sitting=` (the kit's sittings: their evidence
folder) joins that sitting's warm store (`devkit/xemu/warm.py`,
in the private L3 store's `warm/`, keyed by the sitting, the xemu
binary, the release, determinism and the drive it started from): `up`
clones the store's drive holding the most of the sitting's warm states
over W's before the launch (a held sandbox's `claim` too), a cold boot
in a sandbox whose guest RAM is the null renderer's (null, or offscreen
`null_ram`) publishes W's drive as the store's next drive
(`warm_published`; at the halt, as `park` copies its drive; not after a
`savevm` that failed), and a build another sandbox of the sitting booted
since is taken by a relaunch onto the drive holding it (`boot-build`
itself: `warm_drive` in its JSON; a plain `relaunch` keeps W's drive),
so each build and tag boots cold once a sitting. A shared state the
xemu refuses to load is booted cold instead (an incident `warm_load`).
Plain offscreen sandboxes load the null-born states but publish none
(their RAM isn't null's, so a null row never starts from one). A state
saved null loads offscreen: sitting X.81d,
a flicken build's null warm state in an offscreen deterministic sandbox,
2.9-5.8 s against cold offscreen boots' 11 s at load 37 and 92-352 s
at load 58-71, its `.text` the build's; stepped 150 player ticks from
there, its entity row and its picture 6 frames on were byte-identical to
two cold offscreen boots' at that tick (which equal each other), its
guest RAM not (it started from null's RAM; X.81d's fix
sitting): a row comparing
offscreen RAM with a cold offscreen baseline boots both the same way
(`fresh=True`: every boot cold). A sandbox that
saved a tag no store drive holds (a parked start, a spot) keeps its own
drive; a store idle 2 hours goes at the next one's open (it holds the builds' ISOs). **Self-healing:** each try's failure is
classified once (`failure_class`: `dead_pad`, `no_continue`, `boot_hang`
for V22, `menu_miss`, `no_steady_tick` (its incident's `diag`: the
polls, how many saw the tick, the entities, the longest steady run and
the EIPs of the last 8 polls with no tick, AZ-628, and at a halt in the
kernel's halt loop 0x800151EF the code and p1-p4 KeBugCheckEx stored at
0x8003AB20, `bugcheck_data`, Step X.61), `bugcheck` (v0.16.1's
`XEMU_GUEST_BUGCHECK` line, Step X.61: a try's waits ask the run log every
poll and end the try at once on a bugcheck or dead halt it gained, its
items in the incident's `bugchecks`, instead of the 4-minute wait), `xemu_died` with the run log's
cause (a headless fork build's exit on a lost GPU device among them),
`stalled` with a `sample` of the process saved into `$W`) and
relaunches xemu on its W before the next try, 3 tries in all; the JSON's
`incidents` lists them and `relaunches` counts them (AZ-628, sitting x61:
a balthazar build's f6 bugcheck came only in a process's second or later
boot, so its retry, in a fresh process, booted). A refusal (no slot),
a wrong save or a build that doesn't run its code isn't retried.
The check leaves out the data the build's shims write while the game
runs (X3 rewrites its player-model 0x34-byte damage marker every tick,
AZ-300; qol_alloc_race's copy gate, on in every build, its 28-byte
state from main's first frame, AZ-817), found from the build before the
boot (each hook's CALL and its shim's relocations; the JSON's
`shim_data` lists it); any other difference fails it. 10 START presses that don't skip the movie
are a dead pad (AZ-296: 2 of sitting modelswap2's 11 e7 boots by this
path, after which nothing loaded a level; a `loadvm` in the same xemu hung
once after one, AZ-293), and A on the save that builds the scene (its
inventory reset, the CALL at 0x52133) with no Continue (0x52F50) within
10 s is AZ-302 (2 of sitting modelswap3's 43 boots, with the pad live),
named with the EIP it halted at and whether the scene pointer 0x1BF63C was
set: both relaunch before the next try, as above. Each relaunch keeps the sandbox's slot
(Step X.8) and waits up to `--wait` seconds, only for another launch or
a foreign xemu (AZ-301: before Step X.8 it queued like a new sandbox, and
sitting sight222's waited 11.2 min); if it runs out the xemu has already
quit (`relaunch <W> --wait S` then starts it again).

`jump` boots `--iso` (by default the vanilla ISO the resolver finds:
`AZURKIT_ISO`, then the user data folder's `usa.iso`;
identity-checked) in a sandbox (the fork build, null and deterministic,
unless `--app`/`--headless`/`--deterministic` say otherwise), held at the gdbstub's first stop, then:
1. walks to the Training Arena by FIFO key presses (each held 0.5 s).
   Breakpoints confirm three checkpoints: the movie's end, the level
   the new game loads and a steady player tick. The presses between
   them still run on fixed delays, so each route is retried as a whole:
   START every 1.5 s from the moment prophecy.bik starts (0x5F748)
   until the boot state machine sees it end (0x5F774), for up to 120 s
   (the movie is 90 s, so it can also play out); then, once the boot
   state shows the title, the route START (it opens the save list),
   dpad-left (Start New Game, one step left of where s5's list opened), A, until
   `load_level_from_path` (0x53750) loads a level within 20 s, letting
   movie loads (`bink:` paths) pass. The level must be
   `levels/training_room`: any other level (a save the walk opened)
   fails the run by name. On a miss it presses B twice to get back to
   the title and runs the route again (3 tries in all). Then it polls
   the player tick (0x8CCC0) every 0.5 s, pressing A whenever it doesn't
   run, until it ran at every poll over 20 s of game time (its first
   tick comes during the arena's intro, which ignores Y, and the welcome
   dialog opens about 12 s in: AZ-370). It prints
   one `menu:` line per checkpoint;
2. checks the guest's `.text` (and `SHIMS`, less its shims' data, as
   `boot-build` does) against the ISO's
   `default.xbe`, presses jump on a ground tick, prints v0 (the vz of
   the first airborne tick) and writes the capture to `$W/jump.json`
   (`{meta, rows, hits}`; each row has the hold-jump fields
   `hold_t`/`hold_vz` (+0x148/+0x14C) and `peak_z` (+0x164), which
   REORG_PLAN N3 still contests);
3. always runs `down` keeping `$W`; a changed source file fails the run
   (exit 1).

Output is line-buffered, so a redirected log shows each line as it
happens. Trash a kept `$W` when done. The `RSP`, `QMP`, `arm`,
`resume`, `send_keys` and `code_identity` helpers also serve ad-hoc
sessions. The sandbox rules, RAM map and hazards are in the
`azurik-xemu-oracle` skill.

**When to use**: a movement or gameplay change isn't done until it
has been seen once in xemu; also to seed or calibrate the simulator,
and for the randomizer's xemu sittings.

**Known issues**: the 2026-10-09 xemu session 4 ran the owner test
above 3 times on vanilla (v0 = 4.6433 every time, baselines equal).
Its fixed menu delays then went off-script on 3 of 5 boots of
edited-config ISOs, so a checkpointed walk replaced them. The agent's
xemu session s5 (2026-10-11) ran that walk on the fork's fixtures,
whose HDD holds a save: the movie checkpoints held, but its new-game
checkpoint, the inventory reset 0x57B70, also runs when the save list
previews a save, so it measured in the save's level (AZ-254), and its
20 s and 10 s launch waits ran out under load. The level check and the
longer waits are the fix; it reached the arena on the D98 fixtures on
2026-10-11 (try 1, v0 4.6433, baselines equal; the D98 HDD then held
two save slots). If a save list ever puts Start New Game somewhere
other than one dpad-left from where it opens, the run fails naming the
save's level. A run that stops with "the game never started
prophecy.bik" (the guest froze before the movie) or "prophecy.bik
never ended" (during it) may have hit the intermittent boot hang (V22,
2 of about 35 launches in sessions 1-4); both messages say so: run it
again. Step 2.20l moved s6's harness in and rebuilt `jump` on it
without launching xemu: `selftest` passed, and so did a run of every
command (`jump` and `boot-build` included) against a scripted stand-in
for xemu kept outside the repo (real processes, sockets and FIFO; a
second `up` refused at loads of 25-42 while one ran). The first live sitting
still owes one `jump` and s6's S1 jump on a clone (v0 4.849742 from
`vanilla-beach-shield5`). pytest runs only `selftest`,
its offline checks of its own logic (D11).
