# azurik-xemu-oracle reference: oracle save states and boot-build (§6)

Part of the `azurik-xemu-oracle` skill. Here: the D98 oracle save states,
agent-made states and the modded-build path. The card, `../SKILL.md`, holds
the rules, the slots and the sitting loop; the § numbers and hazard numbers
are the skill's (Step 2.216 moved this text here word for word).

## 6. Oracle save states (D67, D98)

**32 vanilla states** on D98's HDD, made by the owner by hand; agents
load them only on clones. **The list is the D98 README's "Savestates"
table** (tag, level and spot, HP, armor Level, Flaps and fuel, date,
xemu version); a tag not in it is not an oracle state. Per-state reads:
the save-state sitting of 2026-10-11.

**Agent-made states (D102).** A state an agent makes (RAM-poked, saved in
game) stays on a private drive, an `oracle-rz-<date>/` folder beside the fixtures
(outside `/tmp`, `$EV` and the repo), tagged `vanilla-rzp-*`, and never
joins D98's drive without the owner's yes (Q250). Evidence from
placement (a RAM teleport, exit hops, RAM pokes) is labelled
`[verified xemu, placed]` and answers mechanism questions only;
routes and reachability stay with the owner, or real play (Q251).

- **D67's oracle HDD is D98's** `xbox_hdd.qcow2`
  (3,757,637,632 B, sha256 `e45d3505…1188`, its `SHA256SUMS.txt`): the
  owner's saves (the all-powers character and a new-game character) and
  the 32 states. A measuring session APFS-clones it into `$W` (§2) and
  adds it to its baselines.
- **The build that made them** is v0.13.3-37-gd5ad94f4bf, kept in the D98
  folder as `xemu-v0.13.3-37-gd5ad94f4bf.app`. The fork build loads them:
  v0.15 all 32 to sitting x30's hashes but 3 ends two words apart
  (sitting x32, §2), and
  v0.15.1 all 32 to v0.15's (sitting x40), v0.16 all 32 to v0.15.1's
  (sitting x43), v0.16.1 all 32 to v0.16's (sitting x61), v0.16.2
  all 32 to v0.16.1's (sitting x66), v0.16.3 all 32 to v0.16.2's
  (sitting x71), v0.16.4 (`up`'s default from Step X.72 to X.94) all 32 to
  v0.16.3's (sitting x72) and 0.16.4-3-g95e7ffc7ec (`up`'s default since
  Step X.94) all 32 to v0.16.4's (sitting x94). A
  state saved by v0.16.1 to v0.16.4 doesn't load in v0.16 or the
  kept build (the NV2A's device section is version 5), and the four load
  each other's (v0.16.1's and v0.16.2's: the fork's PART-12 addendum;
  v0.16.3's and v0.16.4's [inferred: no device section changed
  v0.16.2..v0.16.4];
  `state_stream`): until no lane runs v0.16, no sitting on
  either writes a tag another lane loads (a private drive's, the L3
  store's parked starts), and `unpark` refuses by name a parked start
  of a newer savestate stream than its sandbox's. If a build
  refuses a state ("Unknown section", a device version), use the kept
  one (`--app kept`, `app="kept"`).
- **Loading:** QMP `loadvm <tag>` once `info usb` lists the pad (at
  once after a launch, sitting x9), with the keyboard pad on port 2 and port 1 empty. Every state runs vanilla
  `.text` and has the three cheat cvars at 0. The player tick (0x8CCC0)
  runs in the 22 field states.
- **`vanilla-ig-<level>` states are the save menu pointing at an
  in-game save** (confirm loads it; the player tick doesn't run there).
  Each keeps its own copy of the drive. Vanilla checks load it and press
  confirm.
- **The modded-build path** (verified 5 of 5 boots):
  1. build from vanilla into a scratch folder, then APFS-clone it into
     the sandbox, `cp -c <build> "$W/b-<sha12>.iso"`, so xemu opens nothing
     outside `$W`;
  2. HMP `loadvm vanilla-ig-<level>` (the save list opens on SaveGame #1);
  3. QMP `stop`;
  4. QMP `blockdev-change-medium` with `{"device": "ide0-cd1",
     "filename": "$W/mod.iso", "format": "raw"}` (no `force`);
  5. QMP `system_reset`;
  6. QMP `cont`;
  7. prophecy.bik starts about 25 s after the reset (0x5F748; check
     `.text` against the build there, §4.1); START ends it (0x5F774);
     START at the title opens the save list; A on SaveGame #1 runs
     `game_start_setup` 0x52F50 (the CALL at 0x56672), the save load
     0x58BD0 and `load_level_from_path` 0x53750 with the save's level;
  8. the player tick 0x8CCC0 is steady about 45 s after `loadvm` (by
     the event-driven walk, Step X.9: see the boot times in
     sitting x9's report), with HP at `initial hp`
     (a load sets it) and `.text` still the build's.

  The control (stop, reset, cont, no change) boots the vanilla disc, and
  §4.1's check tells them apart. The save comes from the loaded
  snapshot's drive.
  - **`oracle boot-build <W> <build> [--tag
    vanilla-ig-w1] [--save N] [--a-frame N] [--cold] [--wait S]`**
    (`Sandbox.boot_build`) runs steps 1-8 with `jump`'s movie
    checkpoints and the boot-state menu walk (§3), and checks `.text`
    and `SHIMS` against the build at the steady tick, all but the
    build's `shim_data` (§4.1); any other difference fails it. `--save
    N` loads SaveGame #N (`vanilla-ig-new` with 2: the new-game
    character, AZ-354). **Warm (Step X.9):** it then `savevm`s
    `b-<iso sha12>-<tag>` (`-s<N>` for N > 1) into
    the sandbox's own HDD clone (never D98's drive, D102), and the next
    boot of that build in that sandbox is one `loadvm` of it with the
    build in the tray (`--cold`: neither). **Shared across a sitting
    (Step X.81d):** a kit sitting's sandboxes (`Sandbox(warm_sitting=)`,
    one evidence folder) whose guest RAM is null's (null, or offscreen
    `null_ram`) publish each cold boot's drive to the sitting's warm
    store in the private L3 store, and every one starts on (`up`,
    `claim`), or relaunches in `boot-build` onto, the drive holding the
    most of its states, so each build and tag boots cold once a sitting;
    a null-saved state loads offscreen too (sitting X.81d: 7 of 7, 2.9-5.8
    s against a cold offscreen boot's 11 s at load 37, 92-352 s at load
    58-71, `.text` the build's; 150 ticks on, its entity row and picture
    byte-identical to two cold offscreen boots', its RAM not: compare
    offscreen RAM only between rows booted the same way, `fresh=True` for
    cold), but a plain offscreen sandbox publishes none (its RAM isn't
    null's). A shared state that won't load is booted cold (incident
    `warm_load`).
    On a failure (hazard 11's
    supervisor) it relaunches xemu before the next of its 3 tries; its
    JSON's `incidents` and `relaunches` say so. Each relaunch keeps the
    sandbox's slot and waits up to `--wait` seconds (default 240) for
    another launch to finish; if it runs out the xemu has quit:
    `relaunch <W> --wait S`. On v0.16 its JSON's `host_profile` holds
    the boot's host-time counters' difference (QMP
    `query-xemu-host-profile`: `translate_s` and `translations`, `apu_s`
    and `apu_ticks` under icount, `idle_s` and `idle_warps`, the guest
    time a halted vCPU skipped; `since: launch` after a relaunch: the new
    xemu's own), which the kit's rows and report keep (Step X.58; where a
    cold boot's 12 s go, the fork read's P2).
  - **On guest frames (Step X.64, AZ-675):** in a deterministic sandbox
    on v0.16.1 (`Sandbox.frame_boot`) steps 2-8 run on frames, not the
    wall clock (`Sandbox.boot_frames`; `jump`'s power-on too): the tag
    loads paused, the reset stays stopped, and each step is one QMP
    `xemu-run` that queues its presses at their frames from the reset
    (`@N`) and runs to a PC or the boot state within a budget of vblanks
    (the walk's bounds at 60 Hz). START goes a frame after the movie
    starts (held 2 frames, `SKIP_HOLD`), a frame after the title is up
    (held 8, `PRESS_HOLD`: the title reads the pad only every few
    frames, so a 2-frame press is often missed), A on the save list at
    frame `A_FRAME` (1440, held 13) or a frame after the list previewed
    the save, and A at each poll with no player tick. So a build's boot
    is the same in every process, and its JSON's `frames` is the
    schedule (`movie`, `title`, `presses`, `a`, `level_at`, `steady_at`,
    each from the reset). **AZ-695:** one A frame in a few hundred lands
    the game's allocator race and bugchecks 0x1E (0xAF173 or 0xAF32B), in
    every process: a retry presses A `A_RETRY` (4) frames later, and
    `--a-frame N` (`a_frame=`, with `tries=1`) presses a given frame for
    a sitting on the race. A real-time sandbox (a window, an owner demo)
    walks on the wall clock (§3). **Measured (sitting x64, 2026-10-23,
    v0.16.1 null deterministic; sitting x64's report):**
    main's balthazar build cold at `vanilla-ig-f6` 20 of 20 (10 fresh
    processes, 10 second boots) and the vanilla disc 10 of 10, each disc
    on one schedule (the movie at 1351, the title 1361-1362, A 1440, f6
    loading at 1453-1454, steady at 2251 and 2043) and one RAM digest at
    its halt and at frames 3000 and 3600 in every process, though a second
    boot translated 0.1 s against 0.8; an A sweep, 1420-1469 at f6, 100
    of 100 for both discs; SaveGame #2 at `vanilla-ig-new` and `jump`
    (v0 4.643274784) on frames.
  - **Put `$W/dvd.iso` back before each `loadvm`** (the harness's
    `loadvm` does it; for a warm build state it puts that build in):
    otherwise the build stays in the tray, with vanilla code in RAM and
    the build's files on the disc.
  - Each boot and load writes about 4.6 MB to the HDD clone (the level
    cache). An XBR-changing build through this path is untried; hazard
    8 applies.
- **HP is not full in most states** (S1 318/400, S3 395/400, S4 385/400,
  S5 240/400, `vanilla-exit` 185/400; only `vanilla-rz-new` is 200/200):
  a damage test sets critter+0x210 in RAM first. S1 and `vanilla-exit`
  wear air shield 3 (Level 3, Flaps 5, fuel 1.0); the others wear no
  armor.
- **Making more:** on an APFS clone of the D98 HDD in its own folder
  outside `/tmp`, with the owner's pad on port 2, port 1 empty and the
  232-256 remap off; save states by name (Snapshots menu or QMP
  `savevm`), load each once on a clone to check it, then move the drive
  in (D100). Never reuse a tag (a redo gets `-v2`), never click an
  existing Snapshots entry (that loads it), keep the save-anywhere cheat
  off (AZ-115).
- **Private.** A state holds guest RAM (game code, the kernel, console
  key material): states stay on the owner's machine; only their names
  are shared.

| Group | Tags (D98 README for the spot, HP and armor of each) |
|---|---|
| D67 S1-S5 | S1 `vanilla-beach-shield5` (w1 sloped beach, air shield 3), S2 `vanilla-ocean` (w1, floating, state 0x6), S3 `vanilla-flat`, S4 `vanilla-wall` (about 6 m before a 1.26 m ledge a running jump mounts), S5 `vanilla-enemy` (a blaze sentinel) (S3-S5 in f6) |
| More field states | `vanilla-beach-noshield`, `vanilla-exit` (w1, air shield 3), `vanilla-rz-new` (a new game in w1, HP 200/200) |
| Randomizer (`RANDOMIZER_PLAN.md` I-items) | `vanilla-rz-w1-fw`, `-w1-ice`, `-w1-dark`, `-a1-toggles`, `-a1-crackblock`, `-a1-ladder`, `-f3-zipline`, `-e2-cart` (the cart at its starting end), `-e5-crane` (walking on enters e2), `-e6-song` (the crystal song puzzle, its prerequisite crystals not activated), `-w3-ruby`, `-e7-ruby`, `-e7-keylord`, `-e7-dark` (all `vanilla-rz-` prefixed); not made: `vanilla-rz-a6-done` |
| In-game saves | `vanilla-ig-w1`, `-f6`, `-a1`, `-f3`, `-e2`, `-e5`, `-e6`, `-w3`, `-e7`, `-new` |

**Per-build save points come later:** each is made on its own modded
build after a cold boot, into a scratch HDD (a few steps before a level
exit into a level whose `.xbr` the mod changes, hazard 8; the main menu
before New Game, for starting HP).
