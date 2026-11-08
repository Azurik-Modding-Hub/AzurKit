# azurik-xemu-oracle reference: cheat codes, debug menu and level warp (§4.8)

Part of the `azurik-xemu-oracle` skill. Here: the game's own cheat codes and
the level warp. The card, `../SKILL.md`, holds the rules, the slots and the
sitting loop; the § numbers and hazard numbers are the skill's (Step 2.216
moved this text here word for word).

**4.8 The game's own cheat codes and the level warp (Step X.17).** Ten
button codes work on vanilla retail with no patch (sitting x17,
2026-10-14, sitting x17's report; what
each does: `docs/RE_XBE.md` § "Native cheat UI"). `s.cheat(name)` enters
one through the pipe, frame by frame at the cheat handler 0x15DA0;
`s.warp(level, spot=None)` (a spec's `start.warp`) opens the debug menu,
walks "Change level..." to the level and presses START.

- **Use the warp** to reach any level from a running game without
  walking or the save list (AZ-354's SaveGame #2): 7.5-15 s, all real
  input. The game posts the request a levelSwitch posts, so the arrival
  is a level exit's: it matched an R7 `hop` to the same spot exactly
  (arrival, HP, inventory but the clock; the cheat owner back at 0, the
  cvars untouched). The menu always posts `startspot`; another `spot`
  is one RAM write into the posted request (`spot_written`: placed). It
  keeps the inventory of whatever save is loaded: set a plan's kit
  after it (R2). It loads the disc in the tray: with a build, warp after
  `boot` or `xc.boot_start`, never from a vanilla state with the build
  in the tray (hazard 8). A chain may start a segment with it; the
  warp's own ticks aren't recorded (a placed start, as R7).
- **What the codes change.** Refill (`refill`: HP and the four element
  fuels to max), `gems` (gem mode: each update A/X/Y/BLACK/B is held adds
  a gem; WHITE ends it) and the menu's "Game state..." rows (an element
  level +1, 3 wrapping to 0) change the inventory; `no_damage`,
  `debug_lighting` and `fast_clock` toggle cvars; `big_head` and
  `regen_fx` are cosmetic toggles; `save_anywhere` saves the game to the
  sandbox's HDD clone at once (never on D98's drive, D102); the free
  camera and the menu pause the world. All are guest RAM: a `loadvm`
  undoes them. The cheat code writes no "cheated" flag (`docs/RE_XBE.md`).
- **Driving the menu.** D-pad up/down moves a row, START's edge runs it
  two updates later, BACK hides the menu but keeps it (code 0 shows it
  again as left; `warp` walks from wherever the cursor is). A code
  needs the owner idle (state 0, not gem mode) and no popup: a dialog
  stops the cheat tick (`no cheat tick`).
