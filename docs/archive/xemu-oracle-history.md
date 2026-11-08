# azurik-xemu-oracle: history (archive)

The `azurik-xemu-oracle` skill's history, out of the skill (Step 4.14a3
moved Modkit's `reference/history.md` here; Modkit's names stay as they
were): the measurements of each fork-build adoption sitting, moved out of
§2, and the skill's frontmatter description before Step 2.216 (its full
trigger list). The card, `.claude/skills/azurik-xemu-oracle/SKILL.md`,
holds the rules, the slots and the sitting loop; the § numbers and hazard
numbers are the skill's.

## The skill's description before Step 2.216

```yaml
name: azurik-xemu-oracle
description: >-
  Using the owner's xemu fork ($XEMU_FORK, its checkout) as a
  DEVELOPMENT-ONLY ground-truth oracle for Azurik mods: never in pytest, not
  a CLI verb. Load when asked to "check it in xemu", "verify in-game",
  "boot-test the ISO", "measure jump height / v0 / walk speed / flap count
  for real", "calibrate the Unicorn simulator from xemu", "dump or poke
  guest RAM", "per-frame physics trace", or "the bytes landed but nothing
  changed in game". Also for gdbstub / GDB RSP, QMP, loadvm / savevm,
  booting a modded build from a vanilla-ig-* state (boot-build), the oracle
  save states (D67 on D98's HDD: vanilla-beach-shield5, S1-S5),
  XEMU_INPUT_PIPE key injection on port 2, screenshots, the deterministic
  mode (-icount, null renderer: the default), checkpoints (savevm, park,
  in-memory xemu-checkpoint-*), per-frame traces, input recording
  (XEMU_INPUT_RECORD) and RAM dumps (xemu-dump-ram),
  sandboxing xemu (the D98 fixtures or AZURIK_XEMU_FIXTURES, portable mode, baseline
  hashes), scripts/xemu_oracle.py (jump, up, loadvm, capture, boot-build,
  down, slots, selftest; Sandbox; core-admitted slots, D263), confirming a
  randomizer skip (D114), the 5-minute release checklist, the game's own
  cheat codes, debug menu and level warp (Sitting.cheat / Sitting.warp,
  "Change level..."), owner demos (a visible sandbox, the pad re-plugged
  after a load, the shared-memory recorder, the fork's owner-demo.json), and xemu's known hazards (§5's
  summary: the modded July savestates and QMP-migrating a sandbox that holds checkpoints are rules;
  loadvm restoring old code is by design; the SSE2 check, the V22 boot hang, a frame advance that
  never returns and the old crashes are handled).
```

## Section 2's adoption sittings (x32 to x94)

**Measured (sitting x32, 2026-10-16, v0.15, load 29-37, with
`XEMU_LOAD_VERIFY=1`; sitting x32's report):** all
32 states load (`.text` vanilla, the player tick in the 22 field states,
the save menu in the 10 `vanilla-ig-*`), twice in one xemu and once in
another to the same start and end RAM; every start and 29 of the 32 ends
are x30's hashes, and the other 3 (`vanilla-rz-w1-dark` 45b6a58101bc,
`vanilla-rz-e7-keylord` 23ab6ea774c0, `vanilla-rz-e7-dark` a192738a65b1)
differ from v0.14-36's in two words each, a shader layer's NaN rate whose
payload x87 now keeps (`docs/RE_XBE.md` § "The shader-instance cache";
the fork's 0ff9a1eaf7): the fork's Part 7 F numbers. No load printed a
load-verify line (a gdbstub write between a load and its start does: the
check is on). `vanilla-exit` 27 of 27 on e0af36540768, no input
2ecfe8bef739, HDD reads 202,752 or 221,184 bytes; the pipe string's
variants on X.24's hashes (start f576b2d7a6c6); the zipline load 5 of 5
on its usual start, X.30's sequence included; X.15's w2 walk exact
against L3 by gdbstub and, through PC hooks, equal to the gdbstub replay
on every tick and in its end RAM; a soak of 46 boot-builds in real-time
offscreen Vulkan (31 in one process, with a retried load after each: no
stall, no stale picture; hazard 11).
**Measured (sitting x32d, 2026-10-17, v0.15, load about 50, with
`XEMU_LOAD_VERIFY=1`; X.30's d03, d03b, d05, d08 and d09 as `e01`-`e06`):**
continuity and checkpoints on x30's hashes (hazard 13); frames from a
parked halt 1e1d27a9ef25 3 of 3 (two checkpoint restores, a loadvm after a
relaunch) and twice by a release, once a load halted on its own first
tick (AZ-509); park 0.129 s and unpark 0.028 s by checkpoint, 0.079 s by
loadvm (medians of 5); the cold `jump` (34 s: v0 4.643274784, Δvz
−0.326667, 28 airborne ticks, `.text` 0 differ); recordings (§4.9); each
moved state's own shader record held x87's default NaN at its start
(`docs/RE_XBE.md`). No load printed a load-verify line.
**Measured (sitting x40, 2026-10-17, v0.15.1, load 7-10, with
`XEMU_LOAD_VERIFY=1`; sitting x40's report):**
every hash x32 and x32d took on v0.15. The 32 states load (`.text`
vanilla, the player tick in 22, the save menu in 10), twice in one xemu
and once in another, every start and every end on v0.15's (the 3 moved
ends included); the pipe's variants; `vanilla-exit` 27 of 27 and no
input; continuity, the held keys and the park (both recipes, a relaunch)
on x32d's; a load that halts at its first tick 332c7e660a28 5 of 5, a
running VM's loads included (AZ-509); 120 frames from a parked halt
1e1d27a9ef25 5 of 5; offscreen deterministic d06's two pictures and RAM
as on v0.15, 7 loads in one process on one RAM, and AZ-452's 32 dated
pictures with none stale across a flip. No load-verify line, and no GLib
assertion in the 5 launches' logs.
**Measured (sitting x32b, 2026-10-19, v0.15.1, 7-8 cores free;
sitting x32b's report), Step X.32b's paths
against the old ones, each with the old path's result:** a load by
checkpoint 4.0 ms against HMP `loadvm`'s 23.0 (medians of 5), all 10
on one RAM 120 frames on, and another tag's `loadvm` between leaves the
tag loading by `loadvm` on that RAM; a step-over resume 6.63 ms a tick
against 7.17 (one run each at load 13.8: no measured gain), the rows
equal; the held QMP connection 0.16 ms a command
against 0.38; one `qxemu.read` of 16 x 64 B 0.22 ms against 2.18; a
300-tick light replay through PC hooks 5.14 ms a tick against 7.56 by
gdbstub stops, every tick and the end RAM equal, L3's exact; the RAM
digest 4.1 ms against `ram_sha256`'s 68. The RET-row recorder and a
demo as played (§4.9); D200's case, 16 loads (8 by checkpoint) in one
offscreen deterministic process, on one RAM (the guard warns only on
builds before v0.15's load fix, so its silence there proves nothing).
**Measured (sitting x43, 2026-10-19, v0.16, load 12-27, 3.5-10.6 cores
free, with `XEMU_LOAD_VERIFY=1`; sitting x43's report):**
every hash x40 took on v0.15.1: the 32 states twice in one xemu and once
in another, every start and end on v0.15.1's; the pipe's variants;
`vanilla-exit` 27 of 27 and no input; continuity, the held keys and the
park; the first-tick load 5 of 5; 120 frames from a parked halt 5 of 5;
offscreen d06's two pictures and RAM, 7 loads on one RAM, AZ-452's 32
dated pictures as before. X.32b's feature checks on x32b's results: the
stub offers `Qxemu.stepover` and `qxemu.read`, the PC hooks and
`xemu-ram-digest` are there, and each faster path gives the old one's
rows, bytes and RAM. An L3 conformance sample from the parked drive
`td2-starts` (51 records, 25 whole-step and 26 player-tick, 22,457 ticks,
TD.4c's three town records chained as TD.4c ran them): every record's
xemu core digests on every tick are its record's (v0.14-36's or v0.15.1's);
the 49 that passed then equal L3's core on every tick, 48 the whole
observation too (w4's 896-tick string differs in it from tick 889, as its
record did), and the 2 that failed on v0.15.1 diverge where they did. No
load printed a load-verify line.
**Measured (sitting x61, 2026-10-23, v0.16.1, load 79-87, the harness
unchanged from main, with `XEMU_LOAD_VERIFY=1`;
sitting x61's report, `results/baseline-v0.16.1.json`):**
every hash x43 took on v0.16: the 32 states twice in one xemu and once
in another (`.text` vanilla in 32, the player tick in 22), the pipe's
variants, `vanilla-exit` 27 of 27 and no input, continuity, the held keys
and the park, the first-tick load 5 of 5, 120 frames from a parked halt
5 of 5, X.32b's feature checks, offscreen d06's two pictures and RAM
(f31be3f833ee/5b05083ac8d6, dc6569a681fd/742be81e07bb: v0.16.1's draw
changes moved no picture), 7 loads on one RAM, AZ-452's 32 dated
pictures; the same 51 L3 records on their recorded xemu digests, 49 on
L3's core every tick. The GPU ceiling (g01, the fork's pack-03 inputs,
null, 2 x 300 vblanks with `gpu-counters`): every RAM hash at the load,
+300 and +600 the fork's, and the four heavy scenes' heaviest flips 347
begin/end pairs (e7's fight), 213,262 triangles and 1,024,084 pushbuffer
bytes (rz-new); `vanilla-ig-a1` 48 pairs, 95 triangles and 1 clear a
flip, RAM 745ff857e816. No load printed a load-verify line. With the
X.61b harness (sitting x61b): the 32 states on v0.16's hashes with the
watch monitor, the backlog and the bugcheck report on. With the lane's
whole X.61 harness and its default app (`sitting/REPORT.txt`): the same
hashes for a01-a03, e01-e05, f01, b01 and the 51 L3 records; b01's dated
pictures 3-4 vblanks later after each load (the screenshot advances past
`picture-stale`, Step X.61c), the 18 that pair by frame each the same
picture as main's harness's; `boot-build` of the vanilla disc from
`vanilla-ig-w1`, cold, 3 of 3 first try in USA and Europe, no bugcheck
line; with `STALL_S` set to 10 s (`record/REPORT.txt`) background
advances of 3,000 and 12,000 vblanks returned on the normal run's RAM,
and one whose watch was unreachable raised at 10 s (hazard 15).
**Measured (sitting x66, 2026-10-23, v0.16.2 by `--app`, load 65-76, main's
harness (3fe4e737, a scratch export), with `XEMU_LOAD_VERIFY=1`;
sitting x66's report, `results/cmp-adoption.txt`,
`results/cmp-conformance.txt`):** every value x61 took on v0.16.1
(`baseline-v0.16.1.json`): the 32 states twice in one xemu and once in
another (`.text` vanilla in 32, the player tick in 22), the pipe's
variants, `vanilla-exit` 27 of 27 and no input, continuity, the held
keys and the park, the first-tick load 5 of 5, 120 frames from a parked
halt 5 of 5, X.32b's feature checks, offscreen d06's two pictures and
RAM, 7 loads on one RAM, the 32 dated pictures row for row as X.61's
whole harness took them; g01's RAM hashes and every scene's GPU maxima
(the ceiling unchanged); the 51 L3 records with every verdict v0.16.1's
(on their recorded xemu digests, 49 on L3's core every tick). Cold
power-ons from `-S` (1,800 vblanks, no input): `mem_limit` `'256'`
printed the wide line after the guest RAM line, `'128'` neither; no
bugcheck. No load printed a load-verify line. Field states 168-616 fps,
median 368; save menus about 1,600; offscreen deterministic 104 fps.
With the X.66 harness (`results/lane-launch.json`): `up` on its default
app logged 0.16.2 and `nv2a_bits` 27; relaunched at `'256'`, 28 and the
launch's event.
**Measured (sitting x71, 2026-10-24, v0.16.3, the lane's harness (main's
with `FORK_APP` at v0.16.3, its default app), load 13-31, with
`XEMU_LOAD_VERIFY=1`; sitting x71's report,
`results/cmp-adoption.txt`):** every value x66 took on v0.16.2
(`baseline-v0.16.2.json`) that it reran: the 32 states twice in one xemu and
once in another, the pipe's variants, `vanilla-exit` 27 of 27 and no input,
continuity, the held keys and the park, the first-tick load, 120 frames
from a parked halt, X.32b's feature checks, offscreen d06's two pictures
and RAM, 7 loads on one RAM, the 32 dated pictures row for row as x66's,
g01's RAM hashes and the GPU ceiling, and the cold power-ons at `'256'`
and `'128'`; at `'64'` the power-on equal to a v0.16.2 control's. X.66's
51-record L3 sample couldn't run (its snapshots and parked drive were
deleted, AZ-720): a fresh one, the 22 field states' L3 snapshots and a
300-tick string replayed deep, gave per-tick digests equal to a v0.16.2
control's in 22 of 22 (a replay that ends at a stall halts after a
host-time wait, so its end RAM doesn't repeat, on either build).
Real time offscreen: `frame-ends`' difference equals the present
counter's flips in every window but each scene's first after its
`loadvm`, where it counts one more (4 of 16 windows) [inferred: a flip
queued before the state was saved], and equals the NV2A counters' flips;
a warm data folder's launch logged `vk prewarm: 424 of 424 recorded
pipelines rebuilt in 3.1 s`. No load printed a load-verify line, no
bugcheck. Field states 210-749 fps, median 484; save menus about 1,770;
offscreen deterministic 55 fps. Its `results/baseline-v0.16.3.json` (v0.16.2's
values plus the 64 MiB power-on, the fresh L3 sample and the real-time
windows) is the one X.72 compared with.
**Measured (sitting x72, 2026-10-25, v0.16.4, the lane's harness (main's
with `FORK_APP` at v0.16.4, its default app), load 71-94, with
`XEMU_LOAD_VERIFY=1`; sitting x72's report,
`results/cmp-adoption-c.txt`):** every value x71 took on v0.16.3
(`baseline-v0.16.3.json`) that it reran: the 32 states twice in one xemu and
once in another, the pipe's variants, `vanilla-exit` 27 of 27 and no input,
continuity, the held keys and the park, the first-tick load, 120 frames
from a parked halt, X.32b's feature checks, offscreen d06's two pictures
and RAM, 7 loads on one RAM, the 32 dated pictures row for row as x71's,
g01's RAM hashes and the GPU ceiling, the cold power-ons at `'256'`,
`'128'` and `'64'`, and the fresh 22-state L3 sample's per-tick digests
in 22 of 22 (the 6 replays that end at a stall again end on RAM no run
repeats). The fork's own `bench-det.py --check d98` (its tag's script,
read only, our fixtures): pack 03's four scenes at +300 and +600 on its
goldens. Real time offscreen, as on v0.16.3: `frame-ends` equals the
present counter's flips in 12 of 16 windows, one more in each scene's
first after its `loadvm`, and the NV2A counters' flips with them on. A
launch seeded from the fork's bench cache logged `vk prewarm: 405 of 405
recorded pipelines rebuilt in 3.1 s (3 new ...)`, the next from its kept
cache `428 of 428 ... in 0.1 s (0 new ...)`, though the first run had
left a `pipeline_cache.bin` of 5,495,418 B there against the seed's
21,040,486 (X.71's shrink, harmless here). No load printed
a load-verify line, no bugcheck. Field states 159-578 fps, median 391;
save menus about 1,580; offscreen deterministic 110 fps. Its
`results/baseline-v0.16.4.json` (v0.16.3's values, the bench-det lines and
both real-time runs) is the one the next adoption compares with.
**Measured (sitting x94, 2026-10-28, 0.16.4-3-g95e7ffc7ec, the lane's
harness, load 28-34, with `XEMU_LOAD_VERIFY=1`;
sitting x94's report; D610: a light
sitting, the fork having run its deterministic goldens):** the 32
states once each in one xemu, every start and end on X.72's v0.16.4
baseline (fps 187-1,889, median 537); AZ-822 through the harness's
park and unpark, 20 rounds each from `vanilla-flat` and
`vanilla-rz-new`: v0.16.4's verified restores missed 23,519 and 23,172
pages, this build's 0 and 0, on the same park RAM every round on both;
`timeout-ms`: 300 vblanks from `vanilla-flat` on one RAM with the
default bound, with none and after a timed-out advance and a reload,
a 1,000,000-vblank advance with a 0.5 s bound back paused at 0.50 s
(191 frames ran, `AdvanceTimedOut`), then an advance and a run refused
until the reload, and raw `xemu-run-until` and `xemu-run` replies of
reason `timeout` at 0.30 s; the positive control (X.58's SSE2 `pxor`
over 0x8CCC0): bugcheck 0x1e (0xc000001d, 0x8ccc0, ...) from 0x8001ca36
with KeBugCheckEx's registers, its EIP 0x80019442 and the trap EIP
0x8ccc0 decoded at esp+0x244 and +0x300 (the trap frame and the context
record), 4,096 stack bytes kept as their sha256[:12] only (no `stack`
in W's `sandbox.json`, no long hex run in it or the run logs); v0.16.4
the same bugcheck with no registers. Every teardown's sources and pref
dir unchanged; no load-verify line. Sitting s94 (the same build, the
lane's harness, `sitting/REPORT.txt`; its skeptic `skeptic.txt`):
R1.25b's g26 chain row from 2.172f's parked drive, every restore
verified: v0.16.4's move-on restore at segment 29 missed 132 pages (as
in 2.172f), this build's 0, both back on the parked RAM; this build
with `verify` off restored it by the dirty log alone and placed past it
with no bugcheck (AZ-821's crash gone). A UD2 at 0x8ccc0: KeBugCheckEx's
registers and the trap EIP 0x8ccc0 in the report, no file holding the
stack. A guest loop on the stack that makes a vblank take about 11 s of
host time: `timeout-ms` paused a 15-vblank advance at 135.0 s (the
default bound, 11-12 frames run) and a 10-vblank one at 15.0 s (an
explicit bound), QMP answering at once, the next advance and run
refused until a checkpoint restore gave the reference digest again.
With `STALL_S` scaled to 5 s the watch's stall ended a frozen 10-vblank
advance at 10 s and dropped xemu's timed-out reply (t03b), fixed by
76a1ccbda (hazard 15); the record's rerun (`record/results/t03c-new`)
came back `AdvanceTimedOut` at 15.0 s, no hang probe, the next advance
and run refused, and the reload's 300 vblanks on `e28a015d4a38`.
