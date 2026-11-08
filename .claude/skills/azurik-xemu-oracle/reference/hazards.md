# azurik-xemu-oracle reference: the hazards list (§5's entries)

Part of the `azurik-xemu-oracle` skill. Here: the numbered hazards and what
is still open (the summary table is in the card). The card, `../SKILL.md`,
holds the rules, the slots and the sitting loop; the § numbers and hazard
numbers are the skill's (Step 2.216 moved this text here word for word).

## 5. Known hazards

1. **The four July savestates (`vm-20260704…`) aren't vanilla:** they
   come from a modded build (patched movement sites, a shim call, a 60 fps
   unlock). Never load one. Vanilla runs at dt 1/30. The D98 HDD's own
   states are vanilla (taken on `vanilla.iso`, cold-booted, cheat off). A
   run that needs vanilla code cold-boots (`jump` does) or loads a D98
   state; a run that tests an XBE mod cold-boots its build (hazard 2).
2. **`loadvm` discards the build you booted** (it restores RAM, code
   included). To test a build, use §6's modded-build path
   (`boot-build`): load a `vanilla-ig-*` state, change the DVD medium to
   the build and reset. The medium isn't part of a snapshot, so put
   `$W/dvd.iso` back before each later `loadvm` (the harness's `loadvm`
   does).
3. **"Boots in xemu" ≠ "works on hardware".** TCG doesn't check the SSE2
   CPUID bit by default, so SSE2 code runs there and `#UD`s on the
   Pentium III (AZ-021; shims target pentium3). **Since Step X.58** every
   sandbox on a build with it (v0.16, the fork's 2b17215fb7) runs
   `XEMU_STRICT_CPUID=1`: SSE2 (and SSE3's FISTTP and LFENCE) `#UD`s as
   on the console, the run log says `strict CPUID: #UD at <pc> ... needs
   <feature>` and QMP sends `XEMU_CPUID_FAULT` (the first 32 per launch;
   the kernel then usually bugchecks). `boot-build` stops with
   `CpuidFault` naming each fault's pc and feature (never retried, never
   the opcode bytes), `down` keeps every launch's faults in
   `st["cpuid_faults"]` and the kit's report lists them; its header says
   `strict CPUID`. The fork says retail Azurik and its cold boot never
   trip it and its deterministic goldens match with it on. Sitting
   X.58: the vanilla disc at w1 and a booblord build from main at a1
   booted first try with it on, and the sitting's seven other boots and
   power-ons ran with no `#UD`; an SSE2 `pxor` written over 0x8CCC0 logged `#UD` at 0x8ccc0
   needing SSE2, which `cpuid_faults` and the report's `STRICT CPUID
   FAULTS` line named. The
   flash BIOS likely skips digest checks, so stale digests boot.
4. **The build may not contain what you think.** Build from vanilla in
   one pass and run §4.1 first.
5. **Compare like with like.** The discrete apex for h = 1.1 is 1.0235 m
   at 30 Hz and 1.0616 m at 60 Hz.
6. **Cost/platform.** macOS arm64 only. The fork build launches to
   `xemu: ready` in under a second, null and deterministic by default
   (sitting x14's costs per display mode:
   sitting x14's report; x22's in the archive, §1's pointer).
7. **Secrets.** RAM dumps and `eeprom.bin` hold per-console key material.
   `.gitignore` covers `eeprom.bin`, `*.eeprom`, `*.qcow2`, **not**
   arbitrary `.bin` dumps: keep dumps in `$W`.
8. **The game's HDD cache can hide an XBR edit.** Azurik plays
   prefetch-listed files (`config.xbr`, `characters.xbr`,
   `interface.xbr`, `fx.xbr`, every level XBR) from an HDD cache and
   re-copies one from the DVD only when its `filelist.txt` line (md5,
   size) changes. Every build rewrites the line of each file it changes
   (`docs/RE_DATA.md`); an ISO patched by hand doesn't, and a same-size
   edit then "does nothing". For an XBR check, confirm the re-copy (QMP
   `query-blockstats` DVD bytes) or that the edited page is resident.
9. **The intermittent boot hang (V22):** occasionally a boot (more
   often a build's first boot) idle at EIP 0x800151EF with every I/O
   counter frozen, during the intro movies or on the Microsoft logo.
   Watch `query-blockstats`; QMP `quit` and relaunch. `jump` stops with
   "the game never started prophecy.bik" or "prophecy.bik never ended",
   then "possibly the intermittent boot hang (V22); run it again";
   `boot-build` relaunches and boots again itself (`boot_hang`, Step
   X.9). Every retry so far booted. **Named by the fork (its PART-11
   answer 2.4b):** 0x800151EF is the 4627 kernel's halt loop (`cli; hlt;
   jmp 0x800151ED`), where KeBugCheckEx (export 96, 0x80019442) ends after
   storing its code and p1-p4 at 0x8003AB20 and the double fault halts
   with zeros there. V22 was bugcheck 0xA (IRQL_NOT_LESS_OR_EQUAL;
   0x7ffffff8, 0x2, 0x0, 0x18d0fc) in the XDK OHCI driver's DPC, a USB
   done queue lost because xemu raised its interrupt before writing the
   HCCA back: real-time boots only (0 of 148 icount null boots, 2 of 73
   real-time), fixed in v0.16.1 (858e2af19f; `XEMU_OHCI_HCCA_FIRST=0` the
   old order). **On v0.16.1 every sandbox sets `XEMU_GUEST_BUGCHECK=1`**
   (Step X.61): the run log says `xemu: guest bugcheck 0x<code> (<p1>,
   <p2>, <p3>, <p4>) from <ret>` per KeBugCheckEx call and `xemu: guest
   halted with interrupts disabled at <eip> (esp <esp>)` per dead halt
   (QMP `XEMU_GUEST_BUGCHECK`, `XEMU_GUEST_HALTED`), and the harness reads
   them (`xo.bugchecks`; `v22` flags 0xA with that p4): `down` keeps
   them, the kit's report lists them, a boot try ends on one at once
   (hazard 11's `bugcheck`), and a no-tick poll at the halt loop reads
   the five dwords (`diag["bugcheck_data"]`, on v0.16 too). Classify a
   halt by its line, not by the EIP: AZ-628's 2.153c halts at 0x800151EF
   ran null deterministic on v0.16, where V22's cause can't occur.
   Sitting x61b's positive control: X.58's SSE2 `pxor` over 0x8CCC0 gave
   the `#UD`, then bugcheck 0x1e (0xc000001d, 0x8ccc0, ...) from
   0x8001ca36 and a halt at 0x800151ef, the five dwords the same.
   **Registers and the trap frame (0.16.4-3-g95e7ffc7ec, Step X.94):**
   each bugcheck line is followed by `xemu: guest bugcheck registers:
   eax=... eflags=... (stack: N bytes in the event)`, which `bugchecks`
   reads into the item's `regs` and `stack_bytes`; the QMP event adds
   `regs` (with EIP, KeBugCheckEx itself) and `stack`, up to 4 KiB of
   guest memory from KeBugCheckEx's ESP in hex. **The stack is guest
   data:** `QMP` takes it out of every message as it arrives
   (`scrub_event`), keeping its length, sha256[:12] and the trap frame's
   EIP decoded in memory (`trap_frame`: the EIP, CS 0x0008, EFLAGS
   triples, for a 0x1E only those whose EIP is p2; `trap_eip`, `trap_at`
   offsets from ESP), and `Sandbox.bugchecks` joins those to the run
   log's item by launch and count (only on a connection that heard the
   event: a deterministic sandbox's held one, or a real-time sandbox's
   per-command connection open when it came, such as an advance's;
   otherwise its items have the log's registers alone).
   `bugcheck_list` (the kit's `GUEST BUGCHECKS`) names the trap EIP and
   the registers. Never write the raw stack to a log, report or commit.
10. **xemu can crash (SIGSEGV) in its USB controller** (`ohci_service_ed_list`
    or `ohci_frame_boundary`, a pointer-authentication fault): the fork's
    bug, fixed in the fork build; the kept build still has it.
    A crash loses only unsaved state: snapshot often, relaunch on the
    same W and `loadvm` the last tag. **A lost GPU device:** a headless
    fork build prints `xemu: Vulkan device lost; exiting` and exits at
    once (a windowed one crashes with a report). Its root cause, the
    display compositor sampling freed textures after a flush (`loadvm`,
    reset) or under several offscreen instances, is fixed in the fork build
    (24465976a6; MoltenVK's log level now shows such GPU errors before a
    loss; OpenGL avoided it but runs about 3x slower), and the null
    renderer (the default) has no GPU device. Should one still happen,
    `boot-build`'s supervisor treats it as any crash (`xemu_died`, the
    incident's log naming it) and relaunches; the spec runner reruns the
    case. v0.15 (3147640b9b) also exits 1
    on any other failed Vulkan call (`vk_result = N in <function>
    (<file>:<line>)`, then `xemu: Vulkan call failed; exiting`, a fence
    timeout too); `exit_cause` names the exit line and the call.
11. **Flip-stall hang after a `loadvm` (AZ-293; builds through
    v0.14-36):** in real time on Vulkan (windowed or offscreen; the null
    renderer has no GPU device) the next QMP handshake timed out: the
    pfifo thread spun in `pgraph_vk_finish` (sitting modelswap2's
    `sample`), both times as a flicken build booted at `vanilla-ig-e7`.
    **Cause (the fork, 3147640b9b, PROMPT-7 P):** a failed Vulkan call
    hit `VK_CHECK`'s trap on a thread that blocks SIGTRAP, which macOS
    re-runs forever, so the pfifo thread spun holding `pgraph.lock` and
    the main loop never ran: QMP dead, SIGTERM ignored. **v0.15 exits
    instead** (hazard 10's line), and sitting x32's soak saw no stall:
    46 boot-builds in real-time offscreen Vulkan (10 cold, 36 warm; the
    flicken build at `vanilla-ig-e7` cold 4 times and warm 12), each
    followed by an advance, a picture and a retried load
    (`vanilla-rz-f3-zipline`), 31 of them in one process (its two
    relaunches were a dead pad and a boot hang, below). On an older
    build that hangs: save macOS `sample <pid>`'s output outside the
    repo first; then stop only your own pid (it ignores SIGTERM; `down`
    sends SIGTERM, then SIGKILL, to its own process only; `down --keep`
    keeps W). A relaunch on the same W boots.
    **A dead pad after the reset (AZ-296):** START doesn't skip the
    movie and no level loads. `boot-build` treats 10 START presses that
    don't skip the movie as `DEAD_PAD`, quits that xemu, relaunches on
    the same W and boots again. A sitting script that drives the
    boot itself should do the same (relaunch, not `loadvm` again).
    **A Continue that never runs (AZ-302, cause open):** A on the save
    builds the scene (the reset 0x57B70 from the CALL at 0x52133) but
    `game_start_setup` 0x52F50 never runs. `boot-build` breaks on
    0x52133 and 0x52F50; if Continue doesn't follow within 10 s
    (`CONTINUE_S`) it raises `NoContinue` (naming the EIP and whether the
    scene pointer 0x1BF63C was set), relaunches and boots again.
    It strikes the unmodded control too. **`boot-build`'s supervisor
    (Step X.9)** classifies each try's failure once (`dead_pad`,
    `no_continue`, `boot_hang`, `menu_miss`, `no_steady_tick`,
    `bugcheck` (Step X.61: the run log gained a guest bugcheck or dead
    halt, hazard 9; the try's waits ask every poll and end it at once,
    its items in the incident's `bugchecks`), `xemu_died` with the run
    log's cause, `stalled` with a `sample` into
    `$W`), relaunches on its W (keeping the slot) and tries again, 3 tries
    in all; its JSON's `incidents` lists them. A `no_steady_tick`
    incident's `diag` says where the guest was (AZ-628, Step X.58: 6 of
    896 f6 cold boots, about 0.7 %, 4 of them in one 20-minute window;
    sitting x61: a balthazar build cold at f6 bugchecks 0x1E at 0xAF173,
    on v0.16.1 and v0.16 alike, only as the second or later boot in one
    xemu process: 33 of 149 such tries in its soak and 11 of 40 in its
    record row, against 0 of 34 and 0 of 40 a fresh process's first, with
    no trend by host load; the vanilla disc 0 of 10 second boots; the RAM
    a `loadvm` of f6 gives the same after a boot as fresh; the cause, the
    fork's AZ-628 answer of 2026-10-23: the game's own allocator race
    AZ-695, decided by A's frame on the save list, which the wall-clock
    presses put later in a second boot; since Step X.64 a deterministic
    boot presses on guest frames, the same in every process):
    the polls, how many saw the tick, the
    entities, the longest steady run and the EIPs of the last 8 polls
    with no tick, and at the halt loop KeBugCheckEx's five dwords
    (`bugcheck_data`, Step X.61). The spec runner relaunches
    and reruns a case whose xemu died.
12. **An nv2a assertion abort (AZ-308):** "Failed to enter DMA mode -
    entered PIO mode" (`hw/xbox/nv2a/user.c:64`), no `.ips`: an access
    into the GPU's NV_USER window (the fork's fix names a gdbstub read
    that strayed to 0xFD800000). The fork build reads an unsupported
    channel there as 0 (a6d0fdcb79), but still asserts
    on a read past the 32 channels (0xFDA00000-0xFDFFFFFF) and on a
    write in PIO mode (the same message); the kept build (`--app kept`, v0.13.3-37) has the
    original assert. v0.15's gdbstub reaches RAM and ROM only: a raw
    `m` at 0xFD800000 or 0xFDA00000 answers E14 and xemu runs on
    (sitting x32). Never read or write 0xFD000000-0xFDFFFFFF through
    the gdbstub all the same (`RSP` refuses it, for the older builds and
    the kept one). On an abort, relaunch on the same W and redo the step.
13. **A run continued past a `savevm` is the run a load of it gives
    only when the save was made under icount**
    (daf8bd8017): such a save carries the host-side state a later run
    depends on (the resampler, filter and HRTF history, the APU
    schedule, AC'97, the RTC's sub-second phase, the field pin, the pad
    reports and the pipe's held keys and axes). Sitting x30: a bare
    `savevm` continued 300 vblanks equals two loads and two checkpoint
    restores, held keys and stick across a save too, and a park run on
    equals its unparks before and after a relaunch. Sitting x32d on v0.15
    (whose icount saves also carry PGRAPH method state, 143356c8a2, and
    whose gdb breakpoints are PC hook sites, 21f9186fa7): the same three on
    x30's hashes (a9ffd91827e1, 882eccef7dc8, bd62be85c4f7, the last by
    either park recipe). A save made without
    icount (a real-time sitting, an owner demo, the D98 states)
    starts that state fresh at each load, and so do pipe lines still
    queued at a save (a load drops them; the continued run applies
    them). `Sandbox.savevm` and `park` handle both: deterministic with
    no pipe line pending they save alone
    (`_keeps_run`), otherwise they reload (`savevm T`, `loadvm T`, then
    on: `_reload`, 0.02-0.08 s), so the chain's parks and re-anchors and
    `l3_certify.py`'s snapshots stay checkpoints. Frame numbers count
    the current process's vblanks, not the state's: after a load a
    recorded or remembered `@N` is wrong; tag a line `@<frame()+N>`
    (`at=`), as `play_recording` does. `+N` (`after=`) counts from the
    frame xemu reads the line at, so it fits a line xemu reads at once;
    `+N` lines written a window ahead while it runs land late (AZ-510;
    a short section written at once while paused landed on time in
    jobs 04-a and 10-a's raw controls, Step X.39).
14. **Placements and inventory writes (sittings X.28, x275a):** each
    gave a wrong start once.
    - **Keys:** a value-only write to the key slots gave a wrong key
      (X.28: "some weird green key"). Write the tag too, `s.keys({fourcc:
      n})` (`recipes.keys`: the key's `invType` fourcc and its count), or
      take the key by the game's own pickup.
    - **An exit's volume:** a placement inside a level exit's volume
      fires the exit (e6's `E2_E6` arrival lies in the e2 exit's, which
      a real arrival disarms: every R6 there went back to e2). Place
      outside it, or arrive by a real hop (R7).
    - **A launcher:** R6 2.3 m from e6's steam vent was launched (its
      spring reaches past its mesh), and the state saved there flew on
      load. Keep a placement only once 60 ticks with no input stay
      grounded within 0.5 m.
    - **Unsaved states:** a `loadvm` drops every state you built and
      didn't `savevm` (X.28 lost a toppled w1 tower and rebuilt it).
    - **A kit written beside a save platform** (AZ-824): the first touch
      of the platform saves the game, the written kit included, into the
      loaded slot, so a later reload of it has the kit (X.92's starts A
      and B: the owner's walk saved fire 1 + water 1 into SaveGame #2).
      Write a kit where a run won't touch a save platform, or after the
      run's last touch; a `loadvm` puts the disk back, so the drive
      shows such a save only until the next load.
    - **The stick after a place in a1** (AZ-422): the input builder
      ignores the stick (input+0x30 set) for 230-810 ticks and the
      camera swings back. Before a run, wait until input+0x30 is clear
      and the camera's yaw is back (`model_kit`'s `placed`: `free` and
      `cam_back`).
15. **An advance that never returns (AZ-451; v0.14-36 and older):**
    there `xemu-frame-advance` ends early only on a breakpoint; any
    other VM stop (a gdbstub client attaching, or sending ^C or a stray
    byte; a failed loadvm; an IDE ENOSPC) leaves it waiting for good
    under icount, holding QMP: a new client gets no greeting, then
    ECONNREFUSED, xemu sits at 0% CPU and SIGTERM never ends it. **From
    v0.15** (29a024b18e) any stop the advance didn't make ends it, its
    reply's `stopped` naming the run state (`paused`, `debug`,
    `shutdown`, `restore-vm`): `frame_advance` records the frames that
    ran (at most, when the VM ran before the advance) and raises
    `AdvanceStopped` unless a breakpoint made it (sitting x32: a gdbstub
    attach mid-advance ended it after 843 of 6,000 frames, the VM left
    paused). **If an advance hangs anyway** (a blocked vCPU, a stuck main
    loop; the fork's recipe, PROMPT-8 D): (1) `sample <pid> 5 -file F`
    (F outside the repo) **before** any gdbstub attach, QMP call or
    signal; (2) `lsof -p <pid>` and `ps -o %cpu= -p <pid>`; (3) HMP
    `info status` on `$W/hmp.sock`, which every sandbox now has
    (`xemu_argv`, Step X.32; sitting x32: it said `running` while an
    advance held QMP). `frame_advance` does all three itself after 600 s
    with no reply (on v0.16.1, once no frame moved for 120 s: below),
    before anything else touches that xemu (`hang_probe`
    into W's `hang-<pid>-<time>.sample.txt` and `.txt`; `down` keeps
    that W), then raises `TimeoutError` naming the sample: read it
    before any relaunch. The stacks that tell the cases apart [the
    fork's word]: the old bug: `qemu_main` idles in `g_poll`,
    `rr_cpu_thread_fn` waits in `qemu_cond_wait_bql`, the status is
    paused and gdb answers; a blocked vCPU: `rr_cpu_thread_fn` in
    `pfifo_icount_sync`, `blk_wait_in_flight` or `qemu_event_wait` (read
    the pfifo thread's stack too); a deadlocked main loop: `qemu_main`
    waits on a mutex such as `nv2a_lock_fifo`, `mcpx_apu_wait_for_idle`
    or the BQL (find its holder). Then stop only your own pid (`down`:
    SIGTERM, then SIGKILL). **A QMP connect that fails** says which case
    it is: the socket file removed (ENOENT), or there and refused (held
    by another client or a held advance, taken over, or a dead xemu's
    leftover), or connected and never greeted (the first client past a
    held one waits in the backlog; sitting x32 saw it during an advance,
    and ENOENT for a socket moved away). From v0.15 no second listener
    takes a live socket's path (12a4085249: sitting x32's `chardev-add`
    on `$W/qmp.sock` failed "in use by a live listener", our QMP
    untouched), so only something outside xemu can remove it (AZ-464).
    With v0.16.1's `XEMU_SOCKET_BACKLOG=64` (every sandbox on it, Step
    X.61) a held client queues instead, so a refusal means no listener
    (raised at once, not retried) and an ungreeted connect is "queued
    behind a held client". **A slow advance isn't a hung one (AZ-685,
    Step X.61):** on v0.16.1 a long command (`xemu-frame-advance`,
    `xemu-run-until`) waits in 5 s slices and asks the watch monitor
    (§3) for the frame between them; while it moves the wait goes on (a
    background sandbox beside an owner demo, hazard 16), and only 120 s
    with no frame (`STALL_S`; a watch that doesn't answer counts as none)
    or 4 hours (`LONG_CAP_S`) end it as a hang, with the probe above
    (`ADVANCE_S` is unused there). Sitting x61's record row, `STALL_S` set
    to 10 s and the xemu at background priority, from `vanilla-flat`:
    3,000 and 12,000 frames returned in 32 s and 155 s on the
    normal-priority digests, the watch giving a later frame at each 5 s
    slice (6 and 31 answers), and with the watch's socket name pointed at
    none the 3,000 raised `TimeoutError` ("no frame moved in 10 s") 10 s
    in. **An advance xemu bounds itself (0.16.4-3-g95e7ffc7ec, Step
    X.94):** on a build with `timeout-ms` (`TIMEOUT_MARK`) every
    `frame_advance`, boot `_run` (`xemu-run`) and hooks replay chunk asks
    xemu to pause it after `advance_bound_s(frames)` host seconds (120 s,
    `STALL_S`, plus 1 s a vblank, `FRAME_BOUND_S`: about 3 times sitting
    X.59's 0.34 s a vblank at background priority; at most `LONG_CAP_S`;
    `frame_advance(timeout_s=)` sets another, `False` none). One still
    short of its frame comes back paused wherever it was (`timed-out`, a
    run's reason `timeout`) and QMP is free: `AdvanceTimedOut` (an
    `AdvanceStopped`) names the frames that ran, `down` and the kit's
    report keep it (`timeouts`, `TIMED-OUT ADVANCES`), and a boot try
    retries it from a relaunch (`timed_out`). That pause is at a host-time
    point, so a deterministic sandbox then refuses every advance and run
    until a checkpoint restore or a load (restore one: the run from the
    pause isn't the run a load gives). While the watch answers, an
    advance whose frame stopped (a guest looping inside a frame) waits for
    that reply, up to one slice past the bound, instead of the watch's
    120 s stall (sitting s94's t03b, where the stall had dropped it); a
    deadlock that holds the BQL leaves the watch mute, which timeout-ms
    can't end: the watch's 120 s stall raises then, as above.
16. **Owner demos: our windows wait, our headless sandboxes and batches
    run beside them in the background (PROMPT-8 F(2), Step X.37; D526,
    Step X.59):** while `/tmp/xemu-leases/owner-demo.json` names a live
    pid, the fork's launchers start no xemu (`lease: owner demo running
    (...): no new xemu until it ends; waiting`, once a minute) and
    `take_slot` holds a window of ours (`--window`, a relaunch keeping
    its slot too: the screen is the owner's), but D526 (the owner,
    2026-10-22: "Yes, background priority (Recommended)", over Step
    X.37's hold of every launch, AZ-620's two hours of idle workers a
    long demo) admits a headless sandbox (null or offscreen) beside it
    while fewer than `queue.demo_budget()` of ours run there (the
    efficiency cores, 8 on this M2 Ultra; the demo's own xemu not
    counted) and D263's rule admits it (a relaunch keeping its slot: at
    once). It runs at macOS background priority: right after its launch
    the launcher sets it (`setpriority` `PRIO_DARWIN_BG` on its pid, what
    `taskpolicy -b -p` does: every thread at priority 4 in `ps -M`,
    throttled disk I/O; its event says `launched at background priority
    beside an owner demo`), and every sandbox of ours already running
    moves there too (our demo's start, each admitted launch, `slots`);
    the demo's end (ours; else the next launch or `slots`) takes them
    all back out. The batch tokens do the same for their pools' workers
    (at most the budget of tasks, the token's file `background`); the
    demo's own xemu (the file's pid, or a `sandbox.json` naming an
    `owner_pad`) and its recorder and replug watchers are never touched.
    Set by another process it is that process's external policy, which
    an exec keeps and which can be lifted; never set it on a process
    itself (its children inherit a background they can't leave:
    measured 2026-10-22). A background process ran 0.44x the work per
    CPU second of a normal one (on the efficiency cores [inferred]) and
    got about 6 % of a core at load 55
    (X.59's E-core rate probe), so a
    real-time row beside a demo runs slower and a long advance takes
    longer; a deterministic run's RAM doesn't follow the host. Sitting
    X.59 (2026-10-23, null deterministic, a plain headless sandbox
    holding a private demo file, load 104-119, 0 of 24 cores free;
    sitting x59's report): every
    thread of a sandbox running before the demo went to 4 at its start
    and back (31-46) at its end, the demo's own xemu's never; one
    launched beside it was admitted (its waits named the queue, the
    launch lock, a foreign xemu and cores, never the demo) with every
    thread at 4; `vanilla-flat`'s 600-frame advance gave the same RAM
    digest at background priority as at normal, but took 203 s against
    2.04 s (its `loadvm` 3.7 s against 0.14): at that load an advance
    past about 1,770 frames would have passed `ADVANCE_S` and been taken
    for a hang (AZ-685; fixed by Step X.61 on v0.16.1: the wait follows
    the frame, hazard 15, seen there live, and `READY_S` and `LOADED_S`
    are 4 times longer while a demo runs, and since Step 2.175a a capture's and
    `Sitting.tick`'s player-tick waits too: at load 70-80 the 5 s wait ran out while the tick came). `slots`
    shows `owner_demo`, `demo_budget` and `background_pids`. A sitting
    that checks this simulates a demo in its own process: point
    `oracle.OWNER_DEMO` and `queue.OWNER_DEMO` at a private
    file naming a plain headless sandbox's xemu, never the real one
    (other lanes and the fork's launchers read that), and run no `slots`
    or launch in another process meanwhile (it reads the real file, sees
    no demo and takes the sandboxes back out). A demo's own launch waits
    for none, nor, while one runs, behind the tickets that wait for it,
    and no other launch waits behind a ticket held only for the demo's
    end (a window of ours, any launch of an older harness). An
    owner demo (`owner_pad`) writes the file right after its xemu
    starts (`{"pid", "who": "azurik-modkit", "purpose": <its group>}`,
    a temp file renamed in) and removes it once that xemu is gone, only
    while it still names that pid (a demo's relaunch keeps it, AZ-601:
    from its quit to the new launch it names the relaunching process
    and its command, `relaunch_of` the old xemu): a thread of the launching process
    reaps the xemu (an unreaped one is a zombie, which `kill(pid, 0)`
    and `ps -p` count as running), as do `down`, a failed launch and a
    death `alive()` sees. A record of ours whose pid is no xemu (a
    zombie, or a pid reused after a CLI `up`'s demo ended with no
    `down`) is no demo (for a batch token either) and goes at the next
    launch or `slots`. Never
    write or delete it by hand. The fork's automated xemus (`-name
    xemu-fork-auto`) are load (D248). The pref dir's changes during
    X.34's clean run and X.35 (`pipeline_cache.bin` at 02:49:58) were
    the fork's old binaries without `XEMU_BASE_PATH` (PROMPT-8 F(3);
    no `xemu.toml` or EEPROM change; its `xemu_lease.py run` now refuses
    such a binary): on a `pref_dir_equal` False with no owner xemu,
    suspect a fork launch first.
17. **A guest RAM size xemu can't run (Step X.60):** NV2A BAR1 aliases
    all guest RAM up to 128 MiB and `pci_register_bar` asserts a
    power-of-two BAR (`hw/pci/pci.c:1494`), so at or below 128 MiB a
    size that isn't a power of two aborts xemu at start (SIGABRT from
    `nv2a_init`; the xemu fork's own `-m 192` probe on v0.16 hit it, no
    sandbox of ours has). Below 64 MiB the flash's kernel (built for 64)
    can't run. Above 128 MiB only a build
    with the fork's experimental large RAM (`5f105ce472`, from v0.16.1;
    not v0.16 or the kept build) runs it, and only a multiple of 16 MiB
    up to 3840 (`hw/xbox/xbox.c`); v0.16 aborts at 192 and leaves BAR1
    unmapped at 256 and 512. `-m` wins over `[sys] mem_limit`, an enum
    (`'64'`, `'128'`; `'256'`, `'512'` with the large RAM): any other
    value is ignored for the default 64 MiB. Every sandbox launch checks
    both before xemu starts (`ram_refusal`) and refuses such a size by
    name with its reason. Set a size by `mem_limit` in both of W's
    `xemu.toml`s after quitting that xemu (`sb._quit()`: its exit writes
    back the config it loaded, so an edit made while it runs is lost;
    sitting x61c's first try), then `relaunch`; the D98 states are 128 MiB machines
    and load only at 128 ("Size mismatch: xbox.ram"; on v0.16.1 also
    into 64 MiB with `XEMU_LOADVM_SHRINK_RAM=1` when nothing above 64 MiB
    is in use, an option not taken yet; never into more). From v0.16.1
    `mem_limit` `'256'` launches past `ram_refusal` (`BIG_RAM_MARK`):
    sitting x61c, `-m 256` on the launch line and `xemu-ram-digest`'s
    `ram-size` 256 MiB.
    **The GPU above 128 MiB (v0.16.2, Step X.66, D599; the fork's PART-12
    answer and its addendum, §1's row):** the NV2A's DMA address mask (every
    DMA object's base, the PCRTC start, NV062's offsets, the surface base
    checks) is 28 bits whenever guest RAM is 256 MiB or more and 27 below,
    latched at init: at 144-240 MiB a base past 128 MiB still wraps, and at
    512 MiB one past 256 MiB does. Its init line, `xemu: NV2A wide
    addressing: 28 bits (guest RAM 256 MiB or more)`, follows pfb_init's
    `xemu: guest RAM N MiB (experimental above 128 MiB)`; a launch above
    128 MiB records the bits it runs with (`nv2a_bits`, `st["nv2a_bits"]`,
    an event that warns at 27). Earlier builds are 27 bits at every size: a
    base above 128 MiB wraps for textures, vertices and the push buffer and
    aborts xemu as a render target. `XEMU_NV2A_WIDE` (1eecc99e56's opt-in,
    never released) is gone: setting it does nothing. On every build an
    offset keeps the hardware's field width (textures 32 bits, vertices 31,
    3D surfaces 28, reports 24: `NV097_GET_REPORT_OFFSET` is 0x00FFFFFF, so
    a base-0 report object reaches only the first 16 MiB), and an offset
    past its DMA object's limit aborts xemu rather than wrapping, in release
    builds too (`texture.c:100`, `:132`, `vk/vertex.c:594`,
    `vk/surface.c:2069-2070`): raise a DMA object's limit before any
    offset past 0x3FFAFFF goes through it (`qol_memory_upper64_gpu`'s limit
    hook does at 128 MiB). BAR1 and VGA still cover the first 128 MiB, and
    CSTATUS reports 128 MiB (`XEMU_CSTATUS_FULL_RAM=1`, never inherited, the
    whole size). No savestate change: 256 MiB states load across v0.16.1
    and v0.16.2 both ways, and v0.16.1 runs one at 27 bits. Our default
    stays 128 MiB (D588), so nothing we build changes. Sitting x66 (cold
    power-ons from `-S`, 1,800 vblanks, no bugcheck): `'256'` launched
    `-m 256`, `ram-size` 256 MiB, and printed both lines; `'128'` neither.
18. **A bugcheck after a fast level load, in real time with a renderer
    (AZ-708, AZ-698; builds through v0.16.2):** 0x1E (0xC0000005 at
    0xA5A0D, a read of 0x28), then a dead halt, in an offscreen or windowed
    Vulkan sandbox in real time: X.67's R7 hops into w4 from `vanilla-rz-new`
    19 of 22, and 3 of the owner's game-over Continues in his demo (the same
    write-back [inferred by the fork]). **Cause (the fork's BUGCHECK-A5A0D
    answer):** the disc's DMA landed under a 256x256 colour target w1 draws
    into every frame, still dirty on the GPU (0x0293E000-0x0297DFFF), and
    the game's first read wrote that target back over
    the new level data (0x00FFFFFF, its white pixels), which the load's
    fixups then rebased; the first hop in a process mostly passed (the
    5-flip expiry had written the target back first). Null and `-icount`
    runs never had it (no GPU surfaces; icount's DMA hook wrote back first),
    and a savestate holds no GPU surface, so no state carries it. **Fixed
    in v0.16.3** (3ca6af93d4: mapped DMA trips the access callbacks in every
    mode, so a dirty surface reaches RAM before the device's bytes; the
    fork's hop 0 of 25, 7 of 10 before; det pictures and RAM unchanged).
    **Seen fixed here (sitting x71's crash rows, 2026-10-25, offscreen Vulkan
    in real time at normal priority: the harness's nice 10, no owner demo;
    X.71's crash report, `results/counts`,
    as its skeptic corrected them):** X.67's w4 hops from `vanilla-rz-new`
    on v0.16.3, on a D98 drive clone, 0 of 33 over 3 processes, 0 of the 30
    that weren't a process's first hop (a first hop passes even unfixed);
    on v0.16.2, in a separate sitting the same night on the demo drive's
    clone (x71c), 2 of 6, 2 of 5 past the first. No hop row records
    `vanilla-rz-new`'s start RAM. The owner's demo states with his recorded
    presses went 0 of the 22 runs that reached a Continue or reload, and
    rapid A and START every 2, 3 and 6 frames on his game-over popup 0 of
    the 85 that did; neither has a crashing control (v0.16.2's replays of
    his stalls 0 of 15, no rapid run on v0.16.2), so no build reproduced
    his w1 stall, and that it was this write-back stays the fork's reading.
    So D115's AZ-708 default is lifted on the w4 hop row and the fork's
    mechanism alone: demos and sittings may start from D98-lineage states
    such as `vanilla-rz-new` and their `vanilla-rzp-*` children again.
19. **Never QMP-migrate a running sandbox that holds checkpoints (the
    gap 0.16.4-3-g95e7ffc7ec left open, Step X.94):** AZ-822's fix
    (39d8f4e002) re-arms the dirty log's store traps when HMP `savevm`'s
    migration sync takes a page, with the VM stopped, as every `park`,
    `savevm` and warm save of ours is (covered: a verified restore after
    one finds no page missed). A live QMP `migrate` (or `migrate` to a
    file) of a running VM syncs that log while the guest stores on, which
    the fork didn't check, so a later incremental restore could miss
    pages again. Nothing in the harness migrates; a sitting that must
    first stops the VM, or deletes the sandbox's checkpoints
    (`checkpoint_delete`) or relaunches, and `checkpoint_restore`'s
    `pages-missed` (§3) says if one slipped through.

**Still open** (measurements not yet made): fuel refill through a real
equip or re-cast of the shield, a pickup or a save platform (Q124;
landing, time on the ground and a level change are ruled out); whether
swimming drops a worn armor; the roll at 60 fps (Q159) and into a wall;
HP-03 (an enemy with edited
`hitPoints`); a real analog pad (partial stick, diagonals); the climb
caller and a ledge grab (`vanilla-rz-a1-ladder`); why the emulated
k = 2 roll's ramp differs from level 1's; level-load cache traffic
(V21); an XBR-changing build through §6's path (V10's ISO with
`/azurkit.json` + `/azurkit.bin` boots and plays: Step X.77). The read-set of one
jump (which fields and globals it reads) was dropped (Q122) while
watchpoints livelocked the fork; v0.16's `sb.watch` (`access` `r`) can
take it now (Step X.58), not yet done.
